"""
================================================================================
Research Data Handler & Contract Specifications
================================================================================
Handles clean OHLCV data ingestion, timezone alignment, and contract specifications
for MCX/Global commodity futures: CL=F, BZ=F, GC=F, SI=F, NG=F.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import pandas as pd
import yfinance as yf


@dataclass
class ContractSpec:
    symbol: str
    name: str
    multiplier: float       # Dollar / Rupee value per point move (per contract)
    lot_size: int           # Standard lot units
    tick_size: float        # Minimum price fluctuation
    margin_pct: float       # SPAN + Exposure margin approx (e.g. 0.15 for 15%)
    currency: str           # USD or INR
    fixed_fee_per_contract: float  # Brokerage + exchange clearing per side


# Precise Contract Specifications for Commodity Futures
CONTRACT_SPECS: Dict[str, ContractSpec] = {
    "CL=F": ContractSpec(
        symbol="CL=F",
        name="Crude Oil (WTI) Futures",
        multiplier=1000.0,      # 1,000 barrels per contract ($1 move = $1,000)
        lot_size=1,
        tick_size=0.01,
        margin_pct=0.12,        # ~12% margin requirement
        currency="USD",
        fixed_fee_per_contract=2.00,  # $2.00 per contract per side
    ),
    "BZ=F": ContractSpec(
        symbol="BZ=F",
        name="Brent Crude Oil Futures",
        multiplier=1000.0,      # 1,000 barrels per contract ($1 move = $1,000)
        lot_size=1,
        tick_size=0.01,
        margin_pct=0.12,
        currency="USD",
        fixed_fee_per_contract=2.00,
    ),
    "GC=F": ContractSpec(
        symbol="GC=F",
        name="Gold Futures (COMEX)",
        multiplier=100.0,       # 100 troy ounces per contract ($1 move = $100)
        lot_size=1,
        tick_size=0.10,
        margin_pct=0.10,        # ~10% margin requirement
        currency="USD",
        fixed_fee_per_contract=2.50,
    ),
    "SI=F": ContractSpec(
        symbol="SI=F",
        name="Silver Futures (COMEX)",
        multiplier=5000.0,      # 5,000 troy ounces per contract ($1 move = $5,000)
        lot_size=1,
        tick_size=0.005,
        margin_pct=0.15,        # ~15% margin requirement
        currency="USD",
        fixed_fee_per_contract=2.50,
    ),
    "NG=F": ContractSpec(
        symbol="NG=F",
        name="Natural Gas Futures (NYMEX)",
        multiplier=10000.0,     # 10,000 mmBtu per contract ($1 move = $10,000)
        lot_size=1,
        tick_size=0.001,
        margin_pct=0.20,        # ~20% margin requirement
        currency="USD",
        fixed_fee_per_contract=2.00,
    ),
    "NIFTY_FUT": ContractSpec(
        symbol="NIFTY_FUT",
        name="NIFTY Index Futures (FUTIDX-NIFTY)",
        multiplier=50.0,        # Rs 50 per point per lot (Standard NIFTY lot)
        lot_size=50,
        tick_size=0.05,
        margin_pct=0.12,        # ~12% SPAN + Exposure margin
        currency="INR",
        fixed_fee_per_contract=20.0,  # Rs 20 flat brokerage per side
    ),
    "^NSEI": ContractSpec(
        symbol="^NSEI",
        name="NIFTY 50 Index (Futures Proxy)",
        multiplier=50.0,        # Rs 50 per point per lot
        lot_size=50,
        tick_size=0.05,
        margin_pct=0.12,
        currency="INR",
        fixed_fee_per_contract=20.0,
    ),
}


class DataHandler:
    @staticmethod
    def load_ohlcv(
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "3y",
        interval: str = "1d"
    ) -> pd.DataFrame:
        """
        Load and clean historical OHLCV data from Yahoo Finance.
        Ensures proper timestamp index, monotonic ordering, and eliminates duplicate/null bars.
        """
        if start_date and end_date:
            df = yf.download(symbol, start=start_date, end=end_date, interval=interval, progress=False)
        else:
            df = yf.download(symbol, period=period, interval=interval, progress=False)

        if df.empty:
            raise ValueError(f"No data returned for symbol '{symbol}'.")

        # Flatten multi-index columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]

        # Standardize column casing
        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        })

        # Drop invalid / zero close bars
        df = df[df["close"].notnull() & (df["close"] > 0)].copy()

        # Datetime index cleaning
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df = df.sort_index()

        # Remove duplicate timestamps if any
        df = df[~df.index.duplicated(keep="last")]

        return df

    @staticmethod
    def get_spec(symbol: str) -> ContractSpec:
        """Retrieve contract specifications for an asset."""
        if symbol in CONTRACT_SPECS:
            return CONTRACT_SPECS[symbol]
        # Generic default spec
        return ContractSpec(
            symbol=symbol,
            name=symbol,
            multiplier=1.0,
            lot_size=1,
            tick_size=0.01,
            margin_pct=0.20,
            currency="USD",
            fixed_fee_per_contract=2.00,
        )
