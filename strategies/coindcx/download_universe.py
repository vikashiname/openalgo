#!/usr/bin/env python3
"""
CoinDCX Quantitative Research Universe Downloader & Validator
============================================================
Expands the quantitative research dataset universe for:
BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT, ADAUSDT, DOGEUSDT, AVAXUSDT, LINKUSDT, DOTUSDT

Period: 2023-01-01 to 2026-08-30 (1-Hour Timeframe)
Outputs clean CSVs and DATASET_MANIFEST.md / DATASET_MANIFEST.csv
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

import pandas as pd
import numpy as np

# Add strategy directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from coindcx_historical_data import CoinDCXDownloader, DataValidator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("UniverseDownloader")

DATA_DIR = os.path.expanduser("~/backtesting/coindcx_data")
os.makedirs(DATA_DIR, exist_ok=True)

UNIVERSE = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "BNBUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "DOTUSDT",
]

START_DATE = "2023-01-01 00:00:00"
END_DATE = "2026-08-30 00:00:00"
INTERVAL = "1h"
INTERVAL_MS = 60 * 60 * 1000


def validate_dataset(df: pd.DataFrame, symbol: str, pair: str, file_path: str, start_ms: int, end_ms: int) -> Dict[str, Any]:
    """Perform deep institutional audit on OHLCV dataset."""
    if df.empty:
        return {
            "symbol": symbol,
            "pair": pair,
            "timeframe": INTERVAL,
            "start_date": "N/A",
            "end_date": "N/A",
            "candle_count": 0,
            "expected_candles": 0,
            "missing_candles": 0,
            "gaps_count": 0,
            "gaps_summary": "No data",
            "duplicates": 0,
            "invalid_ohlc": 0,
            "zero_volume": 0,
            "negative_volume": 0,
            "validation_status": "FAILED (Empty)",
            "file_path": file_path,
        }

    total_candles = len(df)
    first_dt = df["timestamp"].iloc[0]
    last_dt = df["timestamp"].iloc[-1]
    first_epoch = int(df["epoch_ms"].iloc[0])
    last_epoch = int(df["epoch_ms"].iloc[-1])

    # Check duplicates
    duplicate_count = int(df.duplicated(subset=["epoch_ms"]).sum())

    # Check expected candles over actual span
    actual_span_ms = last_epoch - first_epoch
    expected_candles = int(actual_span_ms / INTERVAL_MS) + 1 if actual_span_ms >= 0 else total_candles

    # Check gaps
    diffs = df["epoch_ms"].diff().dropna()
    gap_mask = diffs > (INTERVAL_MS * 1.5)
    gaps_count = int(gap_mask.sum())
    missing_count = 0
    gaps_details = []

    if gaps_count > 0:
        gap_indices = df.index[1:][gap_mask]
        for idx in gap_indices:
            prev_t = df.loc[idx - 1, "timestamp"]
            curr_t = df.loc[idx, "timestamp"]
            jump_ms = int(df.loc[idx, "epoch_ms"] - df.loc[idx - 1, "epoch_ms"])
            miss = int(jump_ms / INTERVAL_MS) - 1
            missing_count += miss
            gaps_details.append(f"{prev_t} -> {curr_t} ({miss} bars)")

    # OHLC Integrity Checks
    inv_hl = (df["high"] < df["low"]).sum()
    inv_ho = (df["high"] < df["open"]).sum()
    inv_hc = (df["high"] < df["close"]).sum()
    inv_lo = (df["low"] > df["open"]).sum()
    inv_lc = (df["low"] > df["close"]).sum()
    non_pos = ((df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)).sum()
    nulls = df[["open", "high", "low", "close", "volume"]].isnull().sum().sum()

    total_invalid_ohlc = int(inv_hl + inv_ho + inv_hc + inv_lo + inv_lc + non_pos + nulls)
    zero_vol = int((df["volume"] == 0).sum())
    neg_vol = int((df["volume"] < 0).sum())

    # Validation verdict
    is_valid = (total_invalid_ohlc == 0) and (duplicate_count == 0) and (gaps_count == 0) and (neg_vol == 0)
    if is_valid:
        status = "PASSED (Complete & Valid)"
    elif total_invalid_ohlc == 0 and duplicate_count == 0 and gaps_count <= 2:
        status = f"ACCEPTABLE ({gaps_count} minor gaps, {missing_count} missing)"
    else:
        status = f"FAILED ({gaps_count} gaps, {total_invalid_ohlc} invalid OHLC)"

    gaps_summary = f"{gaps_count} gap(s) [{missing_count} missing candles]" if gaps_count > 0 else "0 gaps"

    return {
        "symbol": symbol,
        "pair": pair,
        "timeframe": INTERVAL,
        "start_date": first_dt,
        "end_date": last_dt,
        "candle_count": total_candles,
        "expected_candles": expected_candles,
        "missing_candles": missing_count,
        "gaps_count": gaps_count,
        "gaps_summary": gaps_summary,
        "gaps_details": gaps_details,
        "duplicates": duplicate_count,
        "invalid_ohlc": total_invalid_ohlc,
        "zero_volume": zero_vol,
        "negative_volume": neg_vol,
        "validation_status": status,
        "file_path": file_path,
    }


def main():
    downloader = CoinDCXDownloader(request_delay=0.20, max_retries=5)
    start_ms = CoinDCXDownloader._parse_to_epoch_ms(START_DATE)
    end_ms = CoinDCXDownloader._parse_to_epoch_ms(END_DATE)

    manifest_records = []

    logger.info("=" * 80)
    logger.info(f"COINDCX QUANTITATIVE RESEARCH UNIVERSE EXPANSION ({len(UNIVERSE)} PAIRS)")
    logger.info(f"Target Period: {START_DATE} to {END_DATE} (1-Hour Timeframe)")
    logger.info("=" * 80)

    for idx, sym in enumerate(UNIVERSE, 1):
        pair = downloader.resolve_symbol(sym)
        file_name = f"{sym}_{INTERVAL}_2023-01-01_2026-08-30.csv"
        file_path = os.path.join(DATA_DIR, file_name)

        logger.info(f"\n[{idx}/{len(UNIVERSE)}] Processing {sym} (CoinDCX Pair: {pair})...")

        if sym == "BTCUSDT" and os.path.exists(file_path):
            logger.info(f"Preserving existing BTCUSDT dataset at {file_path} (No modification).")
            df = pd.read_csv(file_path)
        elif os.path.exists(file_path):
            logger.info(f"Found existing dataset at {file_path}. Loading and auditing...")
            df = pd.read_csv(file_path)
        else:
            logger.info(f"Downloading historical 1H candles for {pair}...")
            df = downloader.download_data(
                symbol=sym,
                interval=INTERVAL,
                start_time=start_ms,
                end_time=end_ms
            )
            if not df.empty:
                df.to_csv(file_path, index=False)
                logger.info(f"Saved {len(df):,} candles to {file_path}")
            else:
                logger.error(f"Failed to download data for {sym}")

        # Perform audit
        audit = validate_dataset(df, sym, pair, file_path, start_ms, end_ms)
        manifest_records.append(audit)

        logger.info(
            f"Audit Result for {sym}: Status={audit['validation_status']} | "
            f"Candles={audit['candle_count']:,} | Gaps={audit['gaps_count']} | ZeroVol={audit['zero_volume']}"
        )

    # Generate Manifest DataFrame
    manifest_df = pd.DataFrame(manifest_records)
    
    # Save CSV Manifest
    manifest_csv_path = os.path.join(DATA_DIR, "DATASET_MANIFEST.csv")
    manifest_df.drop(columns=["gaps_details"]).to_csv(manifest_csv_path, index=False)
    logger.info(f"Saved DATASET_MANIFEST.csv to: {manifest_csv_path}")

    # Save JSON Manifest
    manifest_json_path = os.path.join(DATA_DIR, "DATASET_MANIFEST.json")
    with open(manifest_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest_records, f, indent=2)
    logger.info(f"Saved DATASET_MANIFEST.json to: {manifest_json_path}")

    # Save Markdown Manifest
    manifest_md_path = os.path.join(DATA_DIR, "DATASET_MANIFEST.md")
    md_content = generate_markdown_manifest(manifest_records)
    with open(manifest_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info(f"Saved DATASET_MANIFEST.md to: {manifest_md_path}")

    print("\n" + "=" * 90)
    print("                    COINDCX DATASET MANIFEST SUMMARY")
    print("=" * 90)
    print(f"{'SYMBOL':<10} | {'PAIR':<12} | {'CANDLES':<8} | {'START (IST)':<19} | {'END (IST)':<19} | {'STATUS':<20}")
    print("-" * 90)
    for r in manifest_records:
        print(f"{r['symbol']:<10} | {r['pair']:<12} | {r['candle_count']:<8,} | {r['start_date']:<19} | {r['end_date']:<19} | {r['validation_status']:<20}")
    print("=" * 90 + "\n")


def generate_markdown_manifest(records: List[Dict[str, Any]]) -> str:
    """Generate professional GitHub-style Markdown manifest."""
    lines = [
        "# CoinDCX Quantitative Research Universe Manifest",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        "**Timeframe:** 1-Hour (`1h`)  ",
        "**Target Date Range:** `2023-01-01 00:00:00 UTC` to `2026-08-30 00:00:00 UTC`  ",
        f"**Storage Directory:** `{DATA_DIR}`  ",
        "",
        "---",
        "",
        "## Universe Datasets Overview",
        "",
        "| Symbol | CoinDCX Pair | Candles | Gaps | Zero Volume | Start Date (IST) | End Date (IST) | Validation Status | File Path |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in records:
        fp = r["file_path"]
        lines.append(
            f"| **{r['symbol']}** | `{r['pair']}` | {r['candle_count']:,} | {r['gaps_count']} | {r['zero_volume']} | {r['start_date']} | {r['end_date']} | **{r['validation_status']}** | [{os.path.basename(fp)}](file://{fp}) |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Detailed Integrity Audit",
        ""
    ])

    for r in records:
        lines.extend([
            f"### {r['symbol']} (`{r['pair']}`)",
            f"- **File Path:** [{r['file_path']}](file://{r['file_path']})",
            f"- **Total Candles:** {r['candle_count']:,} (Expected: {r['expected_candles']:,})",
            f"- **Time Coverage:** {r['start_date']} to {r['end_date']}",
            f"- **Missing Candles:** {r['missing_candles']}",
            f"- **Timestamp Duplicates:** {r['duplicates']}",
            f"- **Invalid OHLC Records:** {r['invalid_ohlc']}",
            f"- **Zero-Volume Bars:** {r['zero_volume']}",
            f"- **Negative-Volume Bars:** {r['negative_volume']}",
            f"- **Status:** {r['validation_status']}",
        ])
        if r.get("gaps_details"):
            lines.append("- **Gap Incidents:**")
            for g in r["gaps_details"]:
                lines.append(f"  - `{g}`")
        else:
            lines.append("- **Gap Incidents:** None (Continuous time series)")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
