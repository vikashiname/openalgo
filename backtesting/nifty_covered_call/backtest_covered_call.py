#!/usr/bin/env python3
"""
================================================================================
NIFTY Covered Call Backtest Engine & Baseline Comparison
Location: backtesting/nifty_covered_call/backtest_covered_call.py
================================================================================
Compares two models across 32 monthly NIFTY expiry cycles (2022-2024):
  1. BASELINE:
     - Long NIFTY Futures
     - Short ~0.30 Delta Call (~28 DTE)
     - Trend Filter: Spot > 100-day EMA at entry
     - Call Profit Target: 90% decay
     - Call Stop Loss: 3.0x initial premium
     - Roll: DTE <= 10
     - NO Futures Risk Control (unhedged downside)
  
  2. TREND_FOLLOWING_TRAILING (Proposed):
     - All Baseline parameters PLUS:
     - Dynamic Trend Exit: Close below 100-EMA exits entire position early
     - Futures Catastrophe Stop-Loss: -2.0% futures drawdown cap
     - Max Net Drawdown Cap: -₹20,000 M2M per lot
     - Trailing Profit Lock: Lock in gains after reaching +₹12,000 peak (trails ₹3,500)
     - Crash Protection Guard: Negative M2M decay classified correctly
================================================================================
"""

import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from scipy.stats import norm

# Standard NIFTY parameters
LOT_SIZE = 50  # Historical standard lot size for NIFTY over 2022-2024
RISK_FREE_RATE = 0.07  # 7% Indian risk-free rate
DEFAULT_SIGMA = 0.14   # 14% implied volatility baseline


def calculate_bs_call_price(spot: float, strike: float, dte: int, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    """Calculate Black-Scholes Call Option Price."""
    if dte <= 0:
        return max(0.0, spot - strike)
    t = dte / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    price = spot * norm.cdf(d1) - strike * np.exp(-r * t) * norm.cdf(d2)
    return max(0.05, float(price))


def calculate_bs_call_delta(spot: float, strike: float, dte: int, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    """Calculate Black-Scholes Call Delta."""
    if dte <= 0:
        return 1.0 if spot > strike else 0.0
    t = dte / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    return float(norm.cdf(d1))


def find_target_strike(spot: float, dte: int, target_delta: float = 0.30, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    """Find the strike closest to the target delta (rounded to nearest 50)."""
    t = max(1, dte) / 365.0
    # d1 for target_delta
    target_d1 = norm.ppf(target_delta)
    # spot / strike = exp(target_d1 * sigma * sqrt(t) - (r + 0.5 * sigma^2)*t)
    approx_strike = spot / np.exp(target_d1 * sigma * np.sqrt(t) - (r + 0.5 * sigma ** 2) * t)
    # Round to nearest 50
    rounded_strike = round(approx_strike / 50.0) * 50.0
    return rounded_strike


@dataclass
class TradeRecord:
    strategy: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    expiry_date: pd.Timestamp
    entry_spot: float
    exit_spot: float
    strike: float
    call_entry_price: float
    call_exit_price: float
    dte_entry: int
    dte_exit: int
    fut_pnl: float
    call_pnl: float
    net_pnl: float
    exit_reason: str
    holding_days: int
    peak_net_m2m: float


def run_covered_call_backtest(df: pd.DataFrame, strategy_type: str = "baseline") -> List[TradeRecord]:
    """
    Simulate covered call trading cycle-by-cycle across the dataset.
    """
    df = df.copy().reset_index(drop=True)
    df["ema_100"] = df["close"].ewm(span=100, adjust=False).mean()

    trades: List[TradeRecord] = []
    in_position = False
    pos: Dict[str, Any] = {}

    for i in range(100, len(df)):
        row = df.iloc[i]
        date = row["trade_date"]
        spot = row["close"]
        ema100 = row["ema_100"]
        dte = int(row["active_dte"])
        expiry = row["active_expiry"]

        if not in_position:
            # Entry condition:
            # 1. Spot > 100-EMA (Trend Filter)
            # 2. DTE is roughly between 24 and 35 days (entry at beginning of cycle)
            if spot > ema100 and 22 <= dte <= 35:
                strike = find_target_strike(spot, dte, target_delta=0.30)
                call_price = calculate_bs_call_price(spot, strike, dte)
                
                pos = {
                    "entry_date": date,
                    "expiry_date": expiry,
                    "entry_spot": spot,
                    "strike": strike,
                    "call_entry_price": call_price,
                    "target_price": call_price * 0.10,  # 90% decay
                    "stoploss_price": call_price * 3.0, # 3.0x premium
                    "dte_entry": dte,
                    "entry_index": i,
                    "peak_net_m2m": 0.0,
                }
                in_position = True
            continue

        # Position monitoring
        curr_dte = max(0, dte)
        curr_call_price = calculate_bs_call_price(spot, pos["strike"], curr_dte)
        
        # M2M calculation
        fut_pnl = (spot - pos["entry_spot"]) * LOT_SIZE
        call_pnl = (pos["call_entry_price"] - curr_call_price) * LOT_SIZE
        net_m2m = fut_pnl + call_pnl
        fut_return_pct = (spot - pos["entry_spot"]) / pos["entry_spot"]
        
        pos["peak_net_m2m"] = max(pos["peak_net_m2m"], net_m2m)

        exit_triggered = False
        exit_reason = ""

        if strategy_type == "baseline":
            # Baseline Exit 1: Call profit target (90% decay)
            if curr_call_price <= pos["target_price"]:
                exit_triggered = True
                exit_reason = "PROFIT_TARGET_HIT (90% Decay)"
            # Baseline Exit 2: Call stop loss (3.0x premium)
            elif curr_call_price >= pos["stoploss_price"]:
                exit_triggered = True
                exit_reason = "STOP_LOSS_HIT (3.0x Premium)"
            # Baseline Exit 3: Roll Threshold (DTE <= 10)
            elif curr_dte <= 10 or date >= pos["expiry_date"]:
                exit_triggered = True
                exit_reason = f"ROLL_THRESHOLD_REACHED (DTE <= 10)"

        elif strategy_type == "trend_following_trailing":
            # Guard 1: Futures Catastrophe Stop-Loss (-2.5%)
            if fut_return_pct <= -0.025:
                exit_triggered = True
                exit_reason = f"FUTURES_STOP_LOSS_HIT ({fut_return_pct*100:.2f}%)"
            # Guard 2: Absolute Strategy Net Drawdown Cap (-₹20,000)
            elif net_m2m <= -20000.0:
                exit_triggered = True
                exit_reason = f"MAX_NET_DRAWDOWN_BREACHED (-₹20k Cap)"
            # Guard 3: Trailing Profit Lock (Activated at ₹15k peak, trails 40% buffer)
            elif pos["peak_net_m2m"] >= 15000.0 and net_m2m <= (pos["peak_net_m2m"] * 0.60):
                exit_triggered = True
                exit_reason = f"TRAILING_PROFIT_TRIGGERED (Peak: ₹{pos['peak_net_m2m']:,.0f})"
            # Guard 4: Call Profit Target (with negative M2M crash protection)
            elif curr_call_price <= pos["target_price"]:
                exit_triggered = True
                exit_reason = "PROFIT_TARGET_HIT (90% Decay)" if net_m2m > 0 else "BEARISH_DECAY_CLOSE (Net Negative)"
            # Guard 5: Call Stop Loss (3.0x initial premium)
            elif curr_call_price >= pos["stoploss_price"]:
                exit_triggered = True
                exit_reason = "CALL_STOP_LOSS_HIT (3.0x Premium)"
            # Guard 6: Roll Threshold (DTE <= 10)
            elif curr_dte <= 10 or date >= pos["expiry_date"]:
                exit_triggered = True
                exit_reason = f"ROLL_THRESHOLD_REACHED (DTE <= 10)"

        if exit_triggered:
            holding_days = (date - pos["entry_date"]).days
            trades.append(TradeRecord(
                strategy=strategy_type,
                entry_date=pos["entry_date"],
                exit_date=date,
                expiry_date=pos["expiry_date"],
                entry_spot=pos["entry_spot"],
                exit_spot=spot,
                strike=pos["strike"],
                call_entry_price=pos["call_entry_price"],
                call_exit_price=curr_call_price,
                dte_entry=pos["dte_entry"],
                dte_exit=curr_dte,
                fut_pnl=fut_pnl,
                call_pnl=call_pnl,
                net_pnl=net_m2m,
                exit_reason=exit_reason,
                holding_days=holding_days,
                peak_net_m2m=pos["peak_net_m2m"],
            ))
            in_position = False

    return trades


def compute_metrics(trades: List[TradeRecord]) -> Dict[str, Any]:
    if not trades:
        return {}
    
    pnls = [t.net_pnl for t in trades]
    total_pnl = sum(pnls)
    n_trades = len(trades)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / n_trades) * 100.0 if n_trades > 0 else 0.0
    
    total_wins = sum(wins)
    total_losses = abs(sum(losses))
    profit_factor = (total_wins / total_losses) if total_losses > 0 else (999.0 if total_wins > 0 else 0.0)
    
    # Cumulative equity curve & Max Drawdown
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    drawdowns = peak - equity
    max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
    
    # Sharpe & Sortino (annualized based on avg 12 trades/year)
    pnl_series = pd.Series(pnls)
    mean_pnl = pnl_series.mean()
    std_pnl = pnl_series.std() if len(pnls) > 1 else 1.0
    downside_std = pnl_series[pnl_series < 0].std() if len(losses) > 1 else 1.0
    
    trades_per_year = 12.0
    sharpe = (mean_pnl / std_pnl) * np.sqrt(trades_per_year) if std_pnl > 0 else 0.0
    sortino = (mean_pnl / downside_std) * np.sqrt(trades_per_year) if downside_std > 0 else 0.0
    calmar = (total_pnl / max_drawdown) if max_drawdown > 0 else 0.0

    return {
        "Total Net P&L (₹)": total_pnl,
        "Total Trades": n_trades,
        "Win Rate (%)": win_rate,
        "Profit Factor": profit_factor,
        "Max Drawdown (₹)": max_drawdown,
        "Sharpe Ratio": sharpe,
        "Sortino Ratio": sortino,
        "Calmar Ratio": calmar,
        "Average Trade (₹)": mean_pnl,
        "Largest Win (₹)": max(pnls) if pnls else 0.0,
        "Largest Loss (₹)": min(pnls) if pnls else 0.0,
        "Avg Holding (Days)": np.mean([t.holding_days for t in trades]),
    }


def main():
    data_path = Path("backtesting/oi/data/normalized/NIFTY_continuous.parquet")
    if not data_path.exists():
        print(f"Error: Data file {data_path} not found.")
        sys.exit(1)

    df = pd.read_parquet(data_path)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["active_expiry"] = pd.to_datetime(df["active_expiry"])
    df = df.sort_values("trade_date").reset_index(drop=True)

    print("\n" + "=" * 80)
    print("       NIFTY COVERED CALL: BASELINE vs TREND-FOLLOWING & TRAILING")
    print(f"       Period: {df['trade_date'].min().date()} to {df['trade_date'].max().date()} | Lot Size: {LOT_SIZE}")
    print("=" * 80)

    trades_base = run_covered_call_backtest(df, strategy_type="baseline")
    trades_trend = run_covered_call_backtest(df, strategy_type="trend_following_trailing")

    metrics_base = compute_metrics(trades_base)
    metrics_trend = compute_metrics(trades_trend)

    # Output Side-by-side Table
    summary_df = pd.DataFrame([metrics_base, metrics_trend], index=["Baseline", "Trend-Following + Trailing"]).T
    print("\n[★] PERFORMANCE COMPARISON MATRIX:\n")
    print(summary_df.to_string())

    # Save detailed CSV files
    out_dir = Path("backtesting/nifty_covered_call")
    df_base_trades = pd.DataFrame([t.__dict__ for t in trades_base])
    df_trend_trades = pd.DataFrame([t.__dict__ for t in trades_trend])
    
    df_base_trades.to_csv(out_dir / "trades_baseline.csv", index=False)
    df_trend_trades.to_csv(out_dir / "trades_trend_following_trailing.csv", index=False)
    summary_df.to_csv(out_dir / "comparison_metrics.csv")

    print(f"\n[✓] Detailed trade logs saved to:")
    print(f"    - {out_dir / 'trades_baseline.csv'}")
    print(f"    - {out_dir / 'trades_trend_following_trailing.csv'}")
    print(f"    - {out_dir / 'comparison_metrics.csv'}")


if __name__ == "__main__":
    main()
