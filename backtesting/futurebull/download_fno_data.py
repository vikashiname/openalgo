#!/usr/bin/env python3
"""
================================================================================
7-YEAR DATA ACQUISITION & VALIDATION HARNESS — FUTURES BULL & BEAR SCANNER
================================================================================
Fetches and caches clean historical daily OHLCV data for 46 liquid F&O stocks
across the 2019-2026 timeframe (~7-8 years, ~1,940 daily sessions per symbol)
via OpenAlgo API.
================================================================================
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
DATA_DIR = CURRENT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(), override=False)
except ImportError:
    pass

try:
    from openalgo import api
    OPENALGO_AVAILABLE = True
except ImportError:
    OPENALGO_AVAILABLE = False
    api = None

LIQUID_FNO_UNIVERSE = [
    'RELIANCE', 'HDFCBANK', 'ICICIBANK', 'INFY', 'TCS', 'SBIN', 'BHARTIARTL',
    'ITC', 'LT', 'AXISBANK', 'KOTAKBANK', 'TATASTEEL', 'HINDALCO', 'BAJFINANCE',
    'MARUTI', 'SUNPHARMA', 'ADANIENT', 'ADANIPORTS', 'NTPC', 'POWERGRID',
    'TITAN', 'COALINDIA', 'BPCL', 'EICHERMOT', 'DRREDDY', 'CIPLA', 'JINDALSTEL',
    'HCLTECH', 'M&M', 'WIPRO', 'TECHM', 'VEDL', 'DLF', 'CANBK', 'PNB',
    'APOLLOHOSP', 'INDUSINDBK', 'GRASIM', 'ULTRACEMCO', 'HEROMOTOCO',
    'DIVISLAB', 'BAJAJFINSV', 'CHOLAFIN', 'TVSMOTOR', 'HINDUNILVR', 'BAJAJ-AUTO'
]


def download_7yr_universe():
    if not OPENALGO_AVAILABLE:
        sys.exit("Error: openalgo python client is not installed.")

    api_key = os.getenv("OPENALGO_API_KEY")
    host = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")
    client = api(api_key=api_key, host=host)

    start_date = "2019-01-01"
    end_date = "2026-11-01"

    print("================================================================================")
    print(f"📥 DOWNLOADING 7-YEAR LIQUID F&O DATASET ({len(LIQUID_FNO_UNIVERSE)} SYMBOLS: {start_date} to {end_date})")
    print("================================================================================")

    audit_records = []

    for i, symbol in enumerate(LIQUID_FNO_UNIVERSE, 1):
        target_parquet = DATA_DIR / f"{symbol}.parquet"
        target_csv = DATA_DIR / f"{symbol}.csv"

        # Check if 7-year data is already downloaded (>= 1800 candles)
        if target_parquet.exists():
            df = pd.read_parquet(target_parquet)
            if len(df) >= 1800 and df.index[0].year <= 2019:
                print(f"[{i:02d}/{len(LIQUID_FNO_UNIVERSE)}] {symbol:<12}: Cached 7-yr ({len(df)} candles: {df.index[0].date()} to {df.index[-1].date()})")
                audit_records.append({
                    "symbol": symbol,
                    "candles": len(df),
                    "start": str(df.index[0].date()),
                    "end": str(df.index[-1].date()),
                    "status": "CACHED_7YR"
                })
                continue

        try:
            res = client.history(symbol=symbol, exchange="NSE", interval="D", start_date=start_date, end_date=end_date)
            if isinstance(res, pd.DataFrame) and not res.empty:
                res.columns = [str(c).lower() for c in res.columns]
                if not isinstance(res.index, pd.DatetimeIndex):
                    if "timestamp" in res.columns:
                        res["timestamp"] = pd.to_datetime(res["timestamp"])
                        res = res.set_index("timestamp")
                    elif "date" in res.columns:
                        res["date"] = pd.to_datetime(res["date"])
                        res = res.set_index("date")
                    else:
                        res.index = pd.to_datetime(res.index)
                res = res.sort_index()

                for c in ["open", "high", "low", "close", "volume"]:
                    if c in res.columns:
                        res[c] = pd.to_numeric(res[c], errors="coerce")
                res = res.dropna(subset=["close"])

                res.to_parquet(target_parquet)
                res.to_csv(target_csv)

                print(f"[{i:02d}/{len(LIQUID_FNO_UNIVERSE)}] {symbol:<12}: Downloaded {len(res)} candles ({res.index[0].date()} to {res.index[-1].date()})")
                audit_records.append({
                    "symbol": symbol,
                    "candles": len(res),
                    "start": str(res.index[0].date()),
                    "end": str(res.index[-1].date()),
                    "status": "DOWNLOADED_7YR"
                })
            else:
                print(f"[{i:02d}/{len(LIQUID_FNO_UNIVERSE)}] {symbol:<12}: Empty data returned")
                audit_records.append({"symbol": symbol, "candles": 0, "start": "", "end": "", "status": "EMPTY"})
        except Exception as e:
            print(f"[{i:02d}/{len(LIQUID_FNO_UNIVERSE)}] {symbol:<12}: Failed ({e})")
            audit_records.append({"symbol": symbol, "candles": 0, "start": "", "end": "", "status": f"ERROR: {e}"})

        time.sleep(0.05)

    audit_df = pd.DataFrame(audit_records)
    audit_df.to_csv(DATA_DIR / "DATA_AUDIT_7YR_REPORT.csv", index=False)
    print("\n--------------------------------------------------------------------------------")
    print(f"✅ 7-Year Data Acquisition Complete: {len(audit_df[audit_df['candles'] >= 1800])}/{len(LIQUID_FNO_UNIVERSE)} symbols with ~7-8 full years.")
    print(f"Audit log saved to: {DATA_DIR / 'DATA_AUDIT_7YR_REPORT.csv'}")
    print("================================================================================\n")


if __name__ == "__main__":
    download_7yr_universe()
