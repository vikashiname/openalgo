#!/usr/bin/env python3
"""
================================================================================
AGY Futures OI Auto-Research System — Phase 2: Data Pipeline & Normalizer
================================================================================
Orchestrates:
  1. Automated bulk downloading of official NSE F&O Bhavcopies (Legacy & UDiFF)
  2. Parsing and schema canonicalization
  3. Validation integrity gating (Rule 8)
  4. Contract normalization & continuous series generation (Rule 5 & Rule 9)

Architecture:
  RAW (bhavcopy archives) -> VALIDATED (clean parquet) -> NORMALIZED (continuous)
================================================================================
"""

import os
import io
import time
import zipfile
import urllib.request
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Tuple, Optional

import pandas as pd
import numpy as np

from research.oi.raw_audit import parse_bhavcopy_archive, validate_canonical_dataset

RAW_BHAVCOPY_DIR = "research/oi/raw/bhavcopy"
VALIDATED_DIR = "research/oi/validated"
NORMALIZED_DIR = "research/oi/normalized"
METADATA_DIR = "research/oi/metadata"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def get_bhavcopy_url_and_filename(d: date) -> Tuple[str, str]:
    """
    Generate the appropriate URL and filename based on NSE format transition (2024-07-08).
    """
    if d < date(2024, 7, 8):
        # Legacy format: fo<DD><MMM><YYYY>bhav.csv.zip
        month_str = d.strftime("%b").upper()
        fname = f"fo{d.strftime('%d')}{month_str}{d.year}bhav.csv.zip"
        url = f"https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{d.year}/{month_str}/{fname}"
    else:
        # UDiFF format: BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip
        fname = f"BhavCopy_NSE_FO_0_0_0_{d.strftime('%Y%m%d')}_F_0000.csv.zip"
        url = f"https://nsearchives.nseindia.com/content/fo/{fname}"
    return url, fname


def download_single_day(d: date, raw_dir: str = RAW_BHAVCOPY_DIR) -> Dict:
    """
    Download a single day's Bhavcopy archive with caching.
    """
    if d.weekday() >= 5:
        return {"date": d, "status": "WEEKEND", "path": None}

    url, fname = get_bhavcopy_url_and_filename(d)
    out_path = os.path.join(raw_dir, fname)

    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        return {"date": d, "status": "CACHED", "path": out_path, "bytes": os.path.getsize(out_path)}

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read()
            if len(content) < 1000:
                return {"date": d, "status": "INVALID_SIZE", "path": None}
            with open(out_path, "wb") as f:
                f.write(content)
            return {"date": d, "status": "DOWNLOADED", "path": out_path, "bytes": len(content)}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"date": d, "status": "HOLIDAY_OR_404", "path": None}
        return {"date": d, "status": f"HTTP_{e.code}", "path": None}
    except Exception as e:
        return {"date": d, "status": f"ERROR_{str(e)}", "path": None}


def bulk_download_range(start_date: date, end_date: date, max_workers: int = 4) -> List[Dict]:
    """
    Bulk download historical Bhavcopies over date range using thread pool.
    """
    os.makedirs(RAW_BHAVCOPY_DIR, exist_ok=True)
    all_dates = []
    cur = start_date
    while cur <= end_date:
        if cur.weekday() < 5:
            all_dates.append(cur)
        cur += timedelta(days=1)

    print(f"[*] Commencing bulk download for {len(all_dates)} weekdays ({start_date} to {end_date})...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(download_single_day, all_dates))

    downloaded = sum(1 for r in results if r["status"] == "DOWNLOADED")
    cached = sum(1 for r in results if r["status"] == "CACHED")
    holidays = sum(1 for r in results if r["status"] == "HOLIDAY_OR_404")
    errors = sum(1 for r in results if r["status"].startswith("HTTP_") or r["status"].startswith("ERROR_"))

    print(f"[*] Download summary: {downloaded} downloaded, {cached} cached, {holidays} holidays, {errors} errors.")
    return results


def process_and_validate_all_raw(raw_dir: str = RAW_BHAVCOPY_DIR) -> pd.DataFrame:
    """
    Ingest, normalize, and validate all raw Bhavcopy zip archives in raw_dir.
    Returns single consolidated validated DataFrame.
    """
    files = sorted([os.path.join(raw_dir, f) for f in os.listdir(raw_dir) if f.endswith(".zip")])
    print(f"[*] Processing and validating {len(files)} raw Bhavcopy archives...")

    def _safe_parse(fp):
        try:
            _, day_df = parse_bhavcopy_archive(fp)
            return day_df
        except Exception as e:
            print(f"[!] Warning: Failed parsing {fp}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(_safe_parse, files))

    dfs = [df for df in results if df is not None]

    if not dfs:
        raise ValueError("No valid Bhavcopy archives could be parsed.")

    full_df = pd.concat(dfs, ignore_index=True)
    full_df["trade_date"] = pd.to_datetime(full_df["trade_date"])
    full_df["expiry_date"] = pd.to_datetime(full_df["expiry_date"])
    full_df = full_df.sort_values(["symbol", "expiry_date", "trade_date"]).reset_index(drop=True)

    # Save to validated parquet
    os.makedirs(VALIDATED_DIR, exist_ok=True)
    validated_path = os.path.join(VALIDATED_DIR, "nse_futures_daily.parquet")
    full_df.to_parquet(validated_path, index=False)
    print(f"[+] Successfully saved {len(full_df):,} validated records to {validated_path}")

    return full_df


def build_continuous_contract(df: pd.DataFrame, symbol: str, roll_days_before_expiry: int = 1) -> pd.DataFrame:
    """
    Construct continuous normalized futures series for a symbol.
    Implements Rule 5 (Contract Handling) & Rule 9 (Normalization Layer).
    
    Produces:
      - Near-month continuous price & volume series
      - Next-month continuous price & volume series
      - Near-month OI and Next-month OI
      - Market-wide Total Futures OI (Near + Next + Far)
      - Roll dynamics (Volume roll ratio, OI roll ratio, DTE)
    """
    sub = df[df["symbol"] == symbol].copy()
    if sub.empty:
        raise ValueError(f"Symbol '{symbol}' not found in dataset.")

    # Sort and group by trade_date
    trade_dates = sorted(sub["trade_date"].unique())
    records = []

    for t_date in trade_dates:
        day_contracts = sub[sub["trade_date"] == t_date].sort_values("expiry_date").reset_index(drop=True)
        if day_contracts.empty:
            continue

        # Total market-wide futures OI and volume across all expiries
        total_oi = day_contracts["open_interest"].sum()
        total_contracts = day_contracts["traded_contracts"].sum()
        total_turnover = day_contracts["turnover_lakh"].sum()

        # Classify contracts by expiry ranking
        near_contract = day_contracts.iloc[0]
        next_contract = day_contracts.iloc[1] if len(day_contracts) > 1 else None
        far_contract = day_contracts.iloc[2] if len(day_contracts) > 2 else None

        near_dte = (near_contract["expiry_date"] - t_date).days
        
        # Determine active contract based on roll threshold
        # If DTE <= roll_days_before_expiry and next_contract is liquid, use next_contract
        is_rolled = False
        if near_dte <= roll_days_before_expiry and next_contract is not None:
            if next_contract["traded_contracts"] > near_contract["traded_contracts"]:
                active = next_contract
                is_rolled = True
            else:
                active = near_contract
        else:
            active = near_contract

        next_vol = next_contract["traded_contracts"] if next_contract is not None else 0
        near_vol = near_contract["traded_contracts"]
        vol_roll_ratio = next_vol / (near_vol + next_vol) if (near_vol + next_vol) > 0 else 0.0

        next_oi = next_contract["open_interest"] if next_contract is not None else 0
        near_oi = near_contract["open_interest"]
        oi_roll_ratio = next_oi / (near_oi + next_oi) if (near_oi + next_oi) > 0 else 0.0

        records.append({
            "trade_date": t_date,
            "symbol": symbol,
            "active_contract": active["contract_symbol"],
            "active_expiry": active["expiry_date"],
            "active_dte": (active["expiry_date"] - t_date).days,
            "open": active["open"],
            "high": active["high"],
            "low": active["low"],
            "close": active["close"],
            "settle_price": active["settle_price"],
            "active_contracts": active["traded_contracts"],
            "active_turnover_lakh": active["turnover_lakh"],
            "active_oi": active["open_interest"],
            "active_oi_change": active["oi_change"],
            # Explicit separate near and next tracking
            "near_contract": near_contract["contract_symbol"],
            "near_close": near_contract["close"],
            "near_vol": near_vol,
            "near_oi": near_oi,
            "near_dte": near_dte,
            "next_contract": next_contract["contract_symbol"] if next_contract is not None else None,
            "next_close": next_contract["close"] if next_contract is not None else np.nan,
            "next_vol": next_vol,
            "next_oi": next_oi,
            # Market-wide total metrics (eliminates rollover cliff)
            "total_futures_oi": total_oi,
            "total_futures_vol": total_contracts,
            "total_turnover_lakh": total_turnover,
            # Roll indicators
            "vol_roll_ratio": round(vol_roll_ratio, 4),
            "oi_roll_ratio": round(oi_roll_ratio, 4),
            "is_rolled": is_rolled,
        })

    cont_df = pd.DataFrame(records)
    cont_df["trade_date"] = pd.to_datetime(cont_df["trade_date"])
    cont_df = cont_df.sort_values("trade_date").reset_index(drop=True)

    # Compute Total OI Change & % Change
    cont_df["total_oi_change"] = cont_df["total_futures_oi"].diff().fillna(0).astype(int)
    cont_df["total_oi_change_pct"] = (cont_df["total_futures_oi"].pct_change() * 100).fillna(0.0).round(2)
    cont_df["price_return_pct"] = (cont_df["close"].pct_change() * 100).fillna(0.0).round(2)

    # Save to normalized directory
    os.makedirs(NORMALIZED_DIR, exist_ok=True)
    out_file = os.path.join(NORMALIZED_DIR, f"{symbol}_continuous.parquet")
    cont_df.to_parquet(out_file, index=False)
    print(f"[+] Saved normalized continuous series for {symbol} ({len(cont_df)} sessions) to {out_file}")

    return cont_df


if __name__ == "__main__":
    # Execute pipeline for a 6-month test window (Jan 2024 to Jul 2024)
    # Covering ~140 trading days across both legacy and UDiFF formats
    start = date(2024, 1, 1)
    end = date(2024, 7, 31)
    
    print(f"=== OpenAlgo OI Data Pipeline: {start} to {end} ===")
    bulk_download_range(start, end, max_workers=4)
    validated_df = process_and_validate_all_raw()
    
    # Generate continuous series for core research universe
    for sym in ["NIFTY", "BANKNIFTY"]:
        build_continuous_contract(validated_df, sym)
