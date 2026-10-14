#!/usr/bin/env python3
"""
================================================================================
AGY Futures OI Auto-Research System — Signal Specification Contracts
================================================================================
Formal specification contract for all testable signals in accordance with Rule 17.
Each signal must define explicit entry, exit, holding period, and friction models.
================================================================================
"""

from dataclasses import dataclass
from typing import Callable
import pandas as pd
import numpy as np


@dataclass
class SignalContract:
    signal_id: str
    hypothesis_id: str
    name: str
    trade_direction: str          # 'LONG' or 'SHORT'
    timeframe: str                # 'Daily'
    entry_generator: Callable     # df -> pd.Series[bool] (signal generated at bar t Close)
    exit_bars: int                # Number of bars to hold after entry
    stop_loss_pct: float          # Stop loss percentage (e.g. 1.5 for 1.5%)
    slippage_pct: float           # 0.03%
    transaction_cost_pct: float   # 0.02% (round-trip exchange/STT/brokerage)
    description: str


# -----------------------------------------------------------------------------
# 1. SIG-OI-001: Long Unwinding Dip Rebound (from HYP-OI-0002)
# -----------------------------------------------------------------------------
def entry_sig_oi_001(df: pd.DataFrame) -> pd.Series:
    """Long entry after price dip with falling OI (selling exhaustion)."""
    return (
        (df["oi_state"] == "LONG_UNWINDING") &
        (df["volatility_ratio"] < 1.5) &
        (df["near_dte"] > 2) # Exclude final 2 days of rollover
    )

CONTRACT_SIG_OI_001 = SignalContract(
    signal_id="SIG-OI-001",
    hypothesis_id="HYP-OI-0002",
    name="Long Unwinding Selling Exhaustion Rebound",
    trade_direction="LONG",
    timeframe="Daily",
    entry_generator=entry_sig_oi_001,
    exit_bars=1,
    stop_loss_pct=1.5,
    slippage_pct=0.03,
    transaction_cost_pct=0.02,
    description="Buys pullbacks where OI contracted, signaling lack of aggressive shorting and selling exhaustion."
)


# -----------------------------------------------------------------------------
# 2. SIG-BENCH-001: Price-Only Dip Benchmark (No OI)
# -----------------------------------------------------------------------------
def entry_sig_bench_001(df: pd.DataFrame) -> pd.Series:
    """Pure price dip benchmark without considering OI."""
    return (
        (df["ret_1d"] < 0) &
        (df["volatility_ratio"] < 1.5) &
        (df["near_dte"] > 2)
    )

CONTRACT_SIG_BENCH_001 = SignalContract(
    signal_id="SIG-BENCH-001",
    hypothesis_id="BASELINE_COMPARATOR_001",
    name="Pure Price Dip Benchmark (No OI Filter)",
    trade_direction="LONG",
    timeframe="Daily",
    entry_generator=entry_sig_bench_001,
    exit_bars=1,
    stop_loss_pct=1.5,
    slippage_pct=0.03,
    transaction_cost_pct=0.02,
    description="Control benchmark: buys every price dip without Open Interest confirmation to isolate OI value-add."
)


# -----------------------------------------------------------------------------
# 3. SIG-OI-002: Short Covering Fade / Reversal (from HYP-OI-0001)
# -----------------------------------------------------------------------------
def entry_sig_oi_002(df: pd.DataFrame) -> pd.Series:
    """Short entry after price rally with falling OI (forced covering, no sponsorship)."""
    return (
        (df["oi_state"] == "SHORT_COVERING") &
        (df["dist_sma20_pct"] > 0) & # Above 20 SMA (extended)
        (df["near_dte"] > 2)
    )

CONTRACT_SIG_OI_002 = SignalContract(
    signal_id="SIG-OI-002",
    hypothesis_id="HYP-OI-0001",
    name="Short Covering Exhaustion Fade",
    trade_direction="SHORT",
    timeframe="Daily",
    entry_generator=entry_sig_oi_002,
    exit_bars=1,
    stop_loss_pct=1.5,
    slippage_pct=0.03,
    transaction_cost_pct=0.02,
    description="Shorts rallies where OI contracted, exploiting the subsequent stall due to lack of buyer follow-through."
)


# -----------------------------------------------------------------------------
# 4. SIG-BENCH-002: Pure Price Rally Short Fade (No OI)
# -----------------------------------------------------------------------------
def entry_sig_bench_002(df: pd.DataFrame) -> pd.Series:
    """Pure price rally fade without considering OI."""
    return (
        (df["ret_1d"] > 0) &
        (df["dist_sma20_pct"] > 0) &
        (df["near_dte"] > 2)
    )

CONTRACT_SIG_BENCH_002 = SignalContract(
    signal_id="SIG-BENCH-002",
    hypothesis_id="BASELINE_COMPARATOR_002",
    name="Pure Price Rally Fade (No OI Filter)",
    trade_direction="SHORT",
    timeframe="Daily",
    entry_generator=entry_sig_bench_002,
    exit_bars=1,
    stop_loss_pct=1.5,
    slippage_pct=0.03,
    transaction_cost_pct=0.02,
    description="Control benchmark: shorts every price rally above 20 SMA without Open Interest confirmation."
)


# -----------------------------------------------------------------------------
# 5. SIG-OI-003: Multi-Day Trend Accumulation Long (from HYP-OI-0003)
# -----------------------------------------------------------------------------
def entry_sig_oi_003(df: pd.DataFrame) -> pd.Series:
    """Multi-day trend following long when OI expands with price above 20 SMA."""
    return (
        (df["oi_state"] == "LONG_BUILDUP") &
        (df["close"] > df["sma20"]) &
        (df["vol_rel_ratio"] > 1.0) & # Above average volume
        (df["near_dte"] > 5)          # At least 5 days to expiry for 5-day hold
    )

CONTRACT_SIG_OI_003 = SignalContract(
    signal_id="SIG-OI-003",
    hypothesis_id="HYP-OI-0003",
    name="Multi-Day Trend Accumulation Long",
    trade_direction="LONG",
    timeframe="Daily",
    entry_generator=entry_sig_oi_003,
    exit_bars=5,
    stop_loss_pct=2.0,
    slippage_pct=0.03,
    transaction_cost_pct=0.02,
    description="Rides multi-day institutional capital accumulation over a 5-day holding period."
)

ALL_CONTRACTS = [
    CONTRACT_SIG_OI_001,
    CONTRACT_SIG_BENCH_001,
    CONTRACT_SIG_OI_002,
    CONTRACT_SIG_BENCH_002,
    CONTRACT_SIG_OI_003
]
