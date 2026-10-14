#!/usr/bin/env python3
"""
================================================================================
AGY Futures OI Auto-Research System — Phase 1: Raw Data Audit Engine
================================================================================
Performs automated auditing, schema normalization, integrity validation,
and rollover inspection on raw NSE Futures exchange archives.

Architecture:
  RAW -> VALIDATED -> NORMALIZED -> FEATURES -> BACKTEST
================================================================================
"""

import os
import io
import zipfile
import urllib.request
from datetime import datetime
import pandas as pd
import numpy as np

# Canonical Schema Definition for Futures Raw / Validated Layer
CANONICAL_COLUMNS = [
    "trade_date",       # YYYY-MM-DD
    "symbol",           # Underlying ticker (e.g. NIFTY, BANKNIFTY, RELIANCE)
    "exchange",         # NSE
    "instrument_type",  # FUTIDX, FUTSTK
    "contract_symbol",  # Standardized identifier (e.g. NIFTY-2024-05-30-FUT)
    "expiry_date",      # YYYY-MM-DD
    "days_to_expiry",   # Integer days
    "open",             # Opening traded price
    "high",             # High traded price
    "low",              # Low traded price
    "close",            # Official exchange closing price (30m VWAP)
    "last_price",       # Last traded price (LTP) where available
    "settle_price",     # Daily settlement price
    "traded_contracts", # Volume in number of contracts traded
    "turnover_lakh",    # Traded value in Lakhs INR
    "open_interest",    # Number of open contracts
    "oi_change",        # Change in OI from prior trading day
    "underlying_price", # Spot / underlying price where available
    "is_traded"         # Boolean flag: contracts > 0
]


def parse_bhavcopy_archive(zip_filepath: str) -> tuple[str, pd.DataFrame]:
    """
    Parse an official NSE F&O Bhavcopy ZIP archive (supports legacy and UDiFF formats).
    Returns (format_name, canonical_futures_dataframe).
    """
    with zipfile.ZipFile(zip_filepath) as z:
        csv_filename = z.namelist()[0]
        with z.open(csv_filename) as f:
            df = pd.read_csv(f)

    if "INSTRUMENT" in df.columns:
        fmt = "NSE_LEGACY"
        fut = df[df["INSTRUMENT"].isin(["FUTIDX", "FUTSTK"])].copy()
        
        trade_date = pd.to_datetime(fut["TIMESTAMP"], format="%d-%b-%Y")
        expiry_date = pd.to_datetime(fut["EXPIRY_DT"], format="%d-%b-%Y")
        dte = (expiry_date - trade_date).dt.days
        
        symbol = fut["SYMBOL"].astype(str).str.strip()
        instrument = fut["INSTRUMENT"].astype(str).str.strip()
        contract = symbol + "-" + expiry_date.dt.strftime("%Y-%m-%d") + "-FUT"
        
        open_p = pd.to_numeric(fut["OPEN"], errors="coerce").fillna(0.0)
        high_p = pd.to_numeric(fut["HIGH"], errors="coerce").fillna(0.0)
        low_p = pd.to_numeric(fut["LOW"], errors="coerce").fillna(0.0)
        close_p = pd.to_numeric(fut["CLOSE"], errors="coerce").fillna(0.0)
        settle_p = pd.to_numeric(fut["SETTLE_PR"], errors="coerce").fillna(close_p)
        contracts = pd.to_numeric(fut["CONTRACTS"], errors="coerce").fillna(0).astype(int)
        turnover = pd.to_numeric(fut["VAL_INLAKH"], errors="coerce").fillna(0.0)
        oi = pd.to_numeric(fut["OPEN_INT"], errors="coerce").fillna(0).astype(int)
        oi_chg = pd.to_numeric(fut["CHG_IN_OI"], errors="coerce").fillna(0).astype(int)
        
        canonical = pd.DataFrame({
            "trade_date": trade_date.dt.strftime("%Y-%m-%d"),
            "symbol": symbol,
            "exchange": "NSE",
            "instrument_type": instrument,
            "contract_symbol": contract,
            "expiry_date": expiry_date.dt.strftime("%Y-%m-%d"),
            "days_to_expiry": dte,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "last_price": close_p,
            "settle_price": settle_p,
            "traded_contracts": contracts,
            "turnover_lakh": turnover,
            "open_interest": oi,
            "oi_change": oi_chg,
            "underlying_price": np.nan,
            "is_traded": contracts > 0
        })
    else:
        fmt = "NSE_UDIFF"
        fut = df[df["FinInstrmTp"].isin(["IDF", "STF"])].copy()
        
        trade_date = pd.to_datetime(fut["TradDt"])
        expiry_date = pd.to_datetime(fut["XpryDt"])
        dte = (expiry_date - trade_date).dt.days
        
        symbol = fut["TckrSymb"].astype(str).str.strip()
        instrument = fut["FinInstrmTp"].map({"IDF": "FUTIDX", "STF": "FUTSTK"})
        contract = symbol + "-" + expiry_date.dt.strftime("%Y-%m-%d") + "-FUT"
        
        open_p = pd.to_numeric(fut["OpnPric"], errors="coerce").fillna(0.0)
        high_p = pd.to_numeric(fut["HghPric"], errors="coerce").fillna(0.0)
        low_p = pd.to_numeric(fut["LwPric"], errors="coerce").fillna(0.0)
        close_p = pd.to_numeric(fut["ClsPric"], errors="coerce").fillna(0.0)
        last_p = pd.to_numeric(fut["LastPric"], errors="coerce").fillna(close_p)
        settle_p = pd.to_numeric(fut["SttlmPric"], errors="coerce").fillna(close_p)
        contracts = pd.to_numeric(fut["TtlTradgVol"], errors="coerce").fillna(0).astype(int)
        turnover = pd.to_numeric(fut["TtlTrfVal"], errors="coerce").fillna(0.0) / 100000.0
        oi = pd.to_numeric(fut["OpnIntrst"], errors="coerce").fillna(0).astype(int)
        oi_chg = pd.to_numeric(fut["ChngInOpnIntrst"], errors="coerce").fillna(0).astype(int)
        underlying = pd.to_numeric(fut["UndrlygPric"], errors="coerce")
        
        canonical = pd.DataFrame({
            "trade_date": trade_date.dt.strftime("%Y-%m-%d"),
            "symbol": symbol,
            "exchange": "NSE",
            "instrument_type": instrument,
            "contract_symbol": contract,
            "expiry_date": expiry_date.dt.strftime("%Y-%m-%d"),
            "days_to_expiry": dte,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "last_price": last_p,
            "settle_price": settle_p,
            "traded_contracts": contracts,
            "turnover_lakh": turnover,
            "open_interest": oi,
            "oi_change": oi_chg,
            "underlying_price": underlying,
            "is_traded": contracts > 0
        })

    return fmt, canonical


def validate_canonical_dataset(df: pd.DataFrame) -> dict:
    """
    Execute rigorous validation rules on canonical futures dataset.
    """
    total = len(df)
    traded = df[df["is_traded"]].copy()
    untraded = df[~df["is_traded"]].copy()
    
    invalid_hl = (traded["high"] < traded["low"]).sum()
    invalid_ho = (traded["high"] < traded["open"]).sum()
    invalid_hc = (traded["high"] < traded["close"]).sum()
    invalid_lo = (traded["low"] > traded["open"]).sum()
    invalid_lc = (traded["low"] > traded["close"]).sum()
    zero_prices_in_traded = ((traded["open"] <= 0) | (traded["high"] <= 0) | (traded["low"] <= 0) | (traded["close"] <= 0)).sum()
    
    untraded_zero_ohl = ((untraded["open"] == 0) & (untraded["high"] == 0) & (untraded["low"] == 0)).sum()
    untraded_has_settle = (untraded["settle_price"] > 0).sum()
    
    negative_oi = (df["open_interest"] < 0).sum()
    zero_oi = (df["open_interest"] == 0).sum()
    positive_oi = (df["open_interest"] > 0).sum()
    
    negative_contracts = (df["traded_contracts"] < 0).sum()
    negative_turnover = (df["turnover_lakh"] < 0).sum()
    
    past_expiry = (df["days_to_expiry"] < 0).sum()
    dte_min = df["days_to_expiry"].min() if total > 0 else 0
    dte_max = df["days_to_expiry"].max() if total > 0 else 0
    
    return {
        "total_records": total,
        "traded_records": len(traded),
        "untraded_records": len(untraded),
        "traded_ratio_pct": round(len(traded) / total * 100, 2) if total > 0 else 0,
        "price_violations_high_low": int(invalid_hl),
        "price_violations_high_open": int(invalid_ho),
        "price_violations_high_close": int(invalid_hc),
        "price_violations_low_open": int(invalid_lo),
        "price_violations_low_close": int(invalid_lc),
        "zero_prices_in_traded": int(zero_prices_in_traded),
        "untraded_expected_ohl_zero": int(untraded_zero_ohl),
        "untraded_with_valid_settle": int(untraded_has_settle),
        "negative_oi_count": int(negative_oi),
        "zero_oi_count": int(zero_oi),
        "positive_oi_count": int(positive_oi),
        "negative_contracts_count": int(negative_contracts),
        "negative_turnover_count": int(negative_turnover),
        "past_expiry_records": int(past_expiry),
        "min_days_to_expiry": int(dte_min),
        "max_days_to_expiry": int(dte_max),
    }


def run_audit(raw_dir: str = "research/oi/raw/sample_nse") -> dict:
    """
    Run full audit across all raw files in directory.
    """
    files = sorted([f for f in os.listdir(raw_dir) if f.endswith(".zip")])
    audit_results = {}
    
    for f in files:
        fp = os.path.join(raw_dir, f)
        fmt, df = parse_bhavcopy_archive(fp)
        metrics = validate_canonical_dataset(df)
        audit_results[f] = {
            "format": fmt,
            "trade_date": df["trade_date"].iloc[0] if len(df) > 0 else None,
            "metrics": metrics,
            "symbols_count": df["symbol"].nunique(),
            "indices_count": df[df["instrument_type"] == "FUTIDX"]["symbol"].nunique(),
            "stocks_count": df[df["instrument_type"] == "FUTSTK"]["symbol"].nunique(),
        }
    return audit_results


if __name__ == "__main__":
    results = run_audit()
    for fname, data in results.items():
        print("\n========================================================")
        print(f"Audit Result: {fname} ({data['format']}) - Date: {data['trade_date']}")
        print("========================================================")
        print(f"Total Futures Contracts: {data['metrics']['total_records']}")
        print(f"  Traded: {data['metrics']['traded_records']} ({data['metrics']['traded_ratio_pct']}%) ")
        print(f"  Untraded (far months/illiquid): {data['metrics']['untraded_records']}")
        print(f"Symbols: {data['symbols_count']} (Indices: {data['indices_count']}, Stocks: {data['stocks_count']})")
        print(f"Traded Price Sanity:")
        print(f"  High < Low: {data['metrics']['price_violations_high_low']}")
        print(f"  High < Open: {data['metrics']['price_violations_high_open']}")
        print(f"  High < Close: {data['metrics']['price_violations_high_close']}")
        print(f"  Low > Open: {data['metrics']['price_violations_low_open']}")
        print(f"  Low > Close: {data['metrics']['price_violations_low_close']}")
        print(f"OI Sanity:")
        print(f"  Negative OI: {data['metrics']['negative_oi_count']}")
        print(f"  Zero OI: {data['metrics']['zero_oi_count']}")
        print(f"  Positive OI: {data['metrics']['positive_oi_count']}")
        print(f"Expiry Range: {data['metrics']['min_days_to_expiry']} to {data['metrics']['max_days_to_expiry']} DTE")
