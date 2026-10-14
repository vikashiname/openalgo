"""
Data Manager for EMACROSSOPEN Research
File: backtesting/emacrossopen/data_manager.py

Downloads and caches 1-Hour OHLCV data for 30 high-liquidity NFO instruments
covering 2 full years (730 days) of completed candles.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List
import pandas as pd
import yfinance as yf

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 30 Core Liquid NFO Derivatives across Sectors + Benchmark Indices
SYMBOL_TICKER_MAP = {
    # Benchmark Indices
    "NIFTY": {"yf_ticker": "^NSEI", "lot_size": 25, "sector": "INDEX"},
    "BANKNIFTY": {"yf_ticker": "^NSEBANK", "lot_size": 15, "sector": "INDEX"},
    # Banking & Financials
    "HDFCBANK": {"yf_ticker": "HDFCBANK.NS", "lot_size": 550, "sector": "FINANCIALS"},
    "ICICIBANK": {"yf_ticker": "ICICIBANK.NS", "lot_size": 700, "sector": "FINANCIALS"},
    "SBIN": {"yf_ticker": "SBIN.NS", "lot_size": 750, "sector": "FINANCIALS"},
    "AXISBANK": {"yf_ticker": "AXISBANK.NS", "lot_size": 625, "sector": "FINANCIALS"},
    "KOTAKBANK": {"yf_ticker": "KOTAKBANK.NS", "lot_size": 400, "sector": "FINANCIALS"},
    "BAJFINANCE": {"yf_ticker": "BAJFINANCE.NS", "lot_size": 750, "sector": "FINANCIALS"},
    # IT Services
    "TCS": {"yf_ticker": "TCS.NS", "lot_size": 175, "sector": "IT"},
    "INFY": {"yf_ticker": "INFY.NS", "lot_size": 400, "sector": "IT"},
    "HCLTECH": {"yf_ticker": "HCLTECH.NS", "lot_size": 350, "sector": "IT"},
    "WIPRO": {"yf_ticker": "WIPRO.NS", "lot_size": 1500, "sector": "IT"},
    # Energy, Oil & Power
    "RELIANCE": {"yf_ticker": "RELIANCE.NS", "lot_size": 250, "sector": "ENERGY"},
    "ONGC": {"yf_ticker": "ONGC.NS", "lot_size": 2250, "sector": "ENERGY"},
    "NTPC": {"yf_ticker": "NTPC.NS", "lot_size": 1500, "sector": "ENERGY"},
    "POWERGRID": {"yf_ticker": "POWERGRID.NS", "lot_size": 1800, "sector": "ENERGY"},
    "BPCL": {"yf_ticker": "BPCL.NS", "lot_size": 1975, "sector": "ENERGY"},
    # Automobiles
    "M&M": {"yf_ticker": "M&M.NS", "lot_size": 200, "sector": "AUTO"},
    "MARUTI": {"yf_ticker": "MARUTI.NS", "lot_size": 100, "sector": "AUTO"},
    "EICHERMOT": {"yf_ticker": "EICHERMOT.NS", "lot_size": 100, "sector": "AUTO"},
    "BAJAJ-AUTO": {"yf_ticker": "BAJAJ-AUTO.NS", "lot_size": 75, "sector": "AUTO"},
    # Metals & Mining
    "TATASTEEL": {"yf_ticker": "TATASTEEL.NS", "lot_size": 2750, "sector": "METALS"},
    "JINDALSTEL": {"yf_ticker": "JINDALSTEL.NS", "lot_size": 625, "sector": "METALS"},
    "HINDALCO": {"yf_ticker": "HINDALCO.NS", "lot_size": 700, "sector": "METALS"},
    "COALINDIA": {"yf_ticker": "COALINDIA.NS", "lot_size": 1350, "sector": "METALS"},
    # Pharmaceuticals
    "SUNPHARMA": {"yf_ticker": "SUNPHARMA.NS", "lot_size": 350, "sector": "PHARMA"},
    "CIPLA": {"yf_ticker": "CIPLA.NS", "lot_size": 375, "sector": "PHARMA"},
    "DRREDDY": {"yf_ticker": "DRREDDY.NS", "lot_size": 625, "sector": "PHARMA"},
    # Industrial, Telecom & FMCG
    "LT": {"yf_ticker": "LT.NS", "lot_size": 175, "sector": "INFRA"},
    "BHARTIARTL": {"yf_ticker": "BHARTIARTL.NS", "lot_size": 475, "sector": "TELECOM"},
    "ITC": {"yf_ticker": "ITC.NS", "lot_size": 1600, "sector": "FMCG"},
    "ADANIENT": {"yf_ticker": "ADANIENT.NS", "lot_size": 309, "sector": "CONGLOMERATE"},
    "ADANIPORTS": {"yf_ticker": "ADANIPORTS.NS", "lot_size": 475, "sector": "INFRA"},
}

def load_or_download_all_data(force_refresh: bool = False) -> Dict[str, pd.DataFrame]:
    """Downloads or loads cached 1H data for the 30 instruments."""
    data_map = {}
    print(f"Loading/Downloading 1-Hour data for {len(SYMBOL_TICKER_MAP)} symbols...")
    
    symbols_to_fetch = []
    for sym, meta in SYMBOL_TICKER_MAP.items():
        cache_file = DATA_DIR / f"{sym}_1h.parquet"
        if cache_file.exists() and not force_refresh:
            try:
                df = pd.read_parquet(cache_file)
                if len(df) > 500:
                    data_map[sym] = df
                    continue
            except Exception:
                pass
        symbols_to_fetch.append(sym)
        
    if symbols_to_fetch:
        print(f"Fetching {len(symbols_to_fetch)} symbols from yfinance...")
        tickers = [SYMBOL_TICKER_MAP[s]["yf_ticker"] for s in symbols_to_fetch]
        raw_data = yf.download(tickers, period="730d", interval="1h", progress=False, group_by="ticker")
        
        for sym in symbols_to_fetch:
            tick = SYMBOL_TICKER_MAP[sym]["yf_ticker"]
            try:
                if len(tickers) == 1:
                    df = raw_data.copy()
                else:
                    df = raw_data[tick].copy()
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.dropna()
                # Standardize columns
                df.columns = [c.capitalize() for c in df.columns]
                # Ensure Open, High, Low, Close, Volume
                req = ["Open", "High", "Low", "Close", "Volume"]
                if all(c in df.columns for c in req) and len(df) >= 500:
                    cache_file = DATA_DIR / f"{sym}_1h.parquet"
                    df.to_parquet(cache_file)
                    data_map[sym] = df
                    print(f"  [OK] {sym} ({tick}): {len(df)} candles ({df.index[0]} to {df.index[-1]})")
                else:
                    print(f"  [WARN] {sym} ({tick}) had insufficient rows ({len(df)})")
            except Exception as e:
                print(f"  [ERROR] {sym} ({tick}): {e}")
                
    print(f"Successfully loaded {len(data_map)}/{len(SYMBOL_TICKER_MAP)} instrument series.")
    return data_map

if __name__ == "__main__":
    load_or_download_all_data()
