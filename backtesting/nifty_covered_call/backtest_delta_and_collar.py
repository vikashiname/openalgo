#!/usr/bin/env python3
"""
================================================================================
NIFTY Covered Call: Delta Sensitivity & Collar Strategy Backtest Engine
================================================================================
Performs rigorous simulation across 32 monthly NIFTY expiry cycles (2022-2024):
1. DELTA SENSITIVITY STUDY:
   - Call Delta: 0.20, 0.25, 0.30, 0.35, 0.40
   - Evaluates Baseline & Trend-Following + Trailing guards for each delta.

2. COLLAR STRATEGY STUDY:
   - Long NIFTY Future + Short OTM Call (~0.30 / 0.25 Delta) + Long OTM Put
   - Put Protection Tiers:
     a. Far OTM (~0.07 Delta, ~₹20-25 cost, tail-risk hedge)
     b. Mid OTM (~0.12 Delta, ~₹45-50 cost, moderate hedge)
     c. Tight OTM (~0.18 Delta, ~₹75-85 cost, tight hedge)
   - Variations:
     * With -2.5% Futures Stop
     * Without Futures Stop (relying on synthetic Put hedge to let trades breathe)
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

LOT_SIZE = 50
RISK_FREE_RATE = 0.07
DEFAULT_SIGMA = 0.14


def calculate_bs_call_price(spot: float, strike: float, dte: int, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    if dte <= 0:
        return max(0.0, spot - strike)
    t = dte / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    price = spot * norm.cdf(d1) - strike * np.exp(-r * t) * norm.cdf(d2)
    return max(0.05, float(price))


def calculate_bs_call_delta(spot: float, strike: float, dte: int, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    if dte <= 0:
        return 1.0 if spot > strike else 0.0
    t = dte / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    return float(norm.cdf(d1))


def find_call_strike(spot: float, dte: int, target_delta: float, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    t = max(1, dte) / 365.0
    target_d1 = norm.ppf(target_delta)
    approx_strike = spot / np.exp(target_d1 * sigma * np.sqrt(t) - (r + 0.5 * sigma ** 2) * t)
    return round(approx_strike / 50.0) * 50.0


def calculate_bs_put_price(spot: float, strike: float, dte: int, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    if dte <= 0:
        return max(0.0, strike - spot)
    t = dte / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    price = strike * np.exp(-r * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)
    return max(0.05, float(price))


def calculate_bs_put_delta(spot: float, strike: float, dte: int, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    if dte <= 0:
        return -1.0 if spot < strike else 0.0
    t = dte / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    return float(norm.cdf(d1) - 1.0)


def find_put_strike(spot: float, dte: int, target_delta_abs: float, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    t = max(1, dte) / 365.0
    d1 = -norm.ppf(target_delta_abs)
    approx_strike = spot * np.exp(-(d1 * sigma * np.sqrt(t) - (r + 0.5 * sigma ** 2) * t))
    return round(approx_strike / 50.0) * 50.0


@dataclass
class TradeResult:
    config_name: str
    call_delta: float
    put_delta: Optional[float]
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    expiry_date: pd.Timestamp
    entry_spot: float
    exit_spot: float
    call_strike: float
    call_entry_price: float
    call_exit_price: float
    put_strike: Optional[float]
    put_entry_price: Optional[float]
    put_exit_price: Optional[float]
    dte_entry: int
    dte_exit: int
    fut_pnl: float
    call_pnl: float
    put_pnl: float
    net_pnl: float
    exit_reason: str
    holding_days: int
    peak_net_m2m: float


def run_simulation(
    df: pd.DataFrame,
    config_name: str,
    call_delta: float = 0.30,
    put_delta: Optional[float] = None,
    use_trailing: bool = True,
    use_futures_stop: bool = True,
    futures_stop_pct: float = -0.025,
    max_net_dd_cap: float = -20000.0,
    trail_peak_threshold: float = 15000.0,
    trail_drawdown_ratio: float = 0.60,
    call_target_decay: float = 0.10,
    call_sl_multiple: float = 3.0,
) -> List[TradeResult]:
    df = df.copy().reset_index(drop=True)
    df["ema_100"] = df["close"].ewm(span=100, adjust=False).mean()

    trades: List[TradeResult] = []
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
            if spot > ema100 and 22 <= dte <= 35:
                c_strike = find_call_strike(spot, dte, target_delta=call_delta)
                c_entry_price = calculate_bs_call_price(spot, c_strike, dte)

                p_strike = None
                p_entry_price = 0.0
                if put_delta is not None and put_delta > 0:
                    p_strike = find_put_strike(spot, dte, target_delta_abs=put_delta)
                    p_entry_price = calculate_bs_put_price(spot, p_strike, dte)

                pos = {
                    "entry_date": date,
                    "expiry_date": expiry,
                    "entry_spot": spot,
                    "call_strike": c_strike,
                    "call_entry_price": c_entry_price,
                    "call_target_price": c_entry_price * call_target_decay,
                    "call_sl_price": c_entry_price * call_sl_multiple,
                    "put_strike": p_strike,
                    "put_entry_price": p_entry_price,
                    "dte_entry": dte,
                    "peak_net_m2m": 0.0,
                }
                in_position = True
            continue

        # Position monitoring
        curr_dte = max(0, dte)
        curr_call_price = calculate_bs_call_price(spot, pos["call_strike"], curr_dte)
        curr_put_price = 0.0
        if pos["put_strike"] is not None:
            curr_put_price = calculate_bs_put_price(spot, pos["put_strike"], curr_dte)

        # M2M components
        fut_pnl = (spot - pos["entry_spot"]) * LOT_SIZE
        call_pnl = (pos["call_entry_price"] - curr_call_price) * LOT_SIZE
        put_pnl = (curr_put_price - pos["put_entry_price"]) * LOT_SIZE if pos["put_strike"] is not None else 0.0
        net_m2m = fut_pnl + call_pnl + put_pnl
        fut_return_pct = (spot - pos["entry_spot"]) / pos["entry_spot"]

        pos["peak_net_m2m"] = max(pos["peak_net_m2m"], net_m2m)

        exit_triggered = False
        exit_reason = ""

        # Guard evaluation order
        if use_futures_stop and fut_return_pct <= futures_stop_pct:
            exit_triggered = True
            exit_reason = f"FUTURES_STOP_LOSS_HIT ({fut_return_pct*100:.2f}%)"
        elif max_net_dd_cap is not None and net_m2m <= max_net_dd_cap:
            exit_triggered = True
            exit_reason = f"MAX_NET_DD_BREACHED (Cap: ₹{max_net_dd_cap:,.0f})"
        elif use_trailing and pos["peak_net_m2m"] >= trail_peak_threshold and net_m2m <= (pos["peak_net_m2m"] * trail_drawdown_ratio):
            exit_triggered = True
            exit_reason = f"TRAILING_PROFIT_TRIGGERED (Peak: ₹{pos['peak_net_m2m']:,.0f})"
        elif curr_call_price <= pos["call_target_price"]:
            exit_triggered = True
            exit_reason = "PROFIT_TARGET_HIT (90% Decay)" if net_m2m > 0 else "BEARISH_DECAY_CLOSE (Net Negative)"
        elif curr_call_price >= pos["call_sl_price"]:
            exit_triggered = True
            exit_reason = f"CALL_STOP_LOSS_HIT ({call_sl_multiple}x Premium)"
        elif curr_dte <= 10 or date >= pos["expiry_date"]:
            exit_triggered = True
            exit_reason = "ROLL_THRESHOLD_REACHED (DTE <= 10)"

        if exit_triggered:
            holding_days = (date - pos["entry_date"]).days
            trades.append(TradeResult(
                config_name=config_name,
                call_delta=call_delta,
                put_delta=put_delta,
                entry_date=pos["entry_date"],
                exit_date=date,
                expiry_date=pos["expiry_date"],
                entry_spot=pos["entry_spot"],
                exit_spot=spot,
                call_strike=pos["call_strike"],
                call_entry_price=pos["call_entry_price"],
                call_exit_price=curr_call_price,
                put_strike=pos["put_strike"],
                put_entry_price=pos["put_entry_price"] if pos["put_strike"] is not None else None,
                put_exit_price=curr_put_price if pos["put_strike"] is not None else None,
                dte_entry=pos["dte_entry"],
                dte_exit=curr_dte,
                fut_pnl=fut_pnl,
                call_pnl=call_pnl,
                put_pnl=put_pnl,
                net_pnl=net_m2m,
                exit_reason=exit_reason,
                holding_days=holding_days,
                peak_net_m2m=pos["peak_net_m2m"],
            ))
            in_position = False

    return trades


def compute_metrics(trades: List[TradeResult]) -> Dict[str, Any]:
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

    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    drawdowns = peak - equity
    max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    pnl_series = pd.Series(pnls)
    mean_pnl = pnl_series.mean()
    std_pnl = pnl_series.std() if len(pnls) > 1 else 1.0
    downside_std = pnl_series[pnl_series < 0].std() if len(losses) > 1 else 1.0

    trades_per_year = 12.0
    sharpe = (mean_pnl / std_pnl) * np.sqrt(trades_per_year) if std_pnl > 0 else 0.0
    sortino = (mean_pnl / downside_std) * np.sqrt(trades_per_year) if downside_std > 0 else 0.0
    calmar = (total_pnl / max_drawdown) if max_drawdown > 0 else 0.0

    # Put drag calculation if applicable
    put_pnls = [t.put_pnl for t in trades]
    total_put_pnl = sum(put_pnls)

    return {
        "Total Net P&L (₹)": round(total_pnl, 2),
        "Total Trades": n_trades,
        "Win Rate (%)": round(win_rate, 2),
        "Profit Factor": round(profit_factor, 2),
        "Max Drawdown (₹)": round(max_drawdown, 2),
        "Sharpe Ratio": round(sharpe, 2),
        "Sortino Ratio": round(sortino, 2),
        "Calmar Ratio": round(calmar, 2),
        "Average Trade (₹)": round(mean_pnl, 2),
        "Largest Win (₹)": round(max(pnls), 2) if pnls else 0.0,
        "Largest Loss (₹)": round(min(pnls), 2) if pnls else 0.0,
        "Put Net Impact (₹)": round(total_put_pnl, 2),
        "Avg Holding (Days)": round(float(np.mean([t.holding_days for t in trades])), 1),
    }


def main():
    data_path = Path("backtesting/oi/data/normalized/NIFTY_continuous.parquet")
    if not data_path.exists():
        print(f"Error: {data_path} not found.")
        sys.exit(1)

    df = pd.read_parquet(data_path)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["active_expiry"] = pd.to_datetime(df["active_expiry"])
    df = df.sort_values("trade_date").reset_index(drop=True)

    print("=" * 80)
    print("  EXPERIMENT 1: CALL DELTA SENSITIVITY (0.20 vs 0.25 vs 0.30 vs 0.35 vs 0.40)")
    print("=" * 80)

    delta_results = {}
    all_delta_trades = []

    for delta in [0.20, 0.25, 0.30, 0.35, 0.40]:
        cfg_name = f"Covered_Call_Delta_{int(delta*100)}"
        trades = run_simulation(
            df,
            config_name=cfg_name,
            call_delta=delta,
            put_delta=None,
            use_trailing=True,
            use_futures_stop=True,
        )
        delta_results[f"Delta {delta:.2f}"] = compute_metrics(trades)
        all_delta_trades.extend([t.__dict__ for t in trades])

    df_delta_summary = pd.DataFrame(delta_results).T
    print("\n--- DELTA SENSITIVITY COMPARISON MATRIX ---")
    print(df_delta_summary[["Total Net P&L (₹)", "Win Rate (%)", "Profit Factor", "Max Drawdown (₹)", "Sharpe Ratio", "Average Trade (₹)", "Largest Loss (₹)"]].to_string())

    print("\n" + "=" * 80)
    print("  EXPERIMENT 2: COLLAR STRATEGY COMPARISON (PROTECTIVE PUT TIERS)")
    print("=" * 80)

    collar_configs = [
        # Benchmark Covered Call
        {"name": "Covered Call (No Put)", "c_delta": 0.30, "p_delta": None, "trail": True, "fut_sl": True},
        
        # Collar with ~₹25 Put (0.07 Delta Put - OTM Tail Risk Protection)
        {"name": "Collar (~₹25 Put, With Fut SL)", "c_delta": 0.30, "p_delta": 0.07, "trail": True, "fut_sl": True},
        {"name": "Collar (~₹25 Put, NO Fut SL)", "c_delta": 0.30, "p_delta": 0.07, "trail": True, "fut_sl": False},

        # Collar with ~₹45 Put (0.12 Delta Put - Moderate Protection)
        {"name": "Collar (~₹45 Put, With Fut SL)", "c_delta": 0.30, "p_delta": 0.12, "trail": True, "fut_sl": True},
        {"name": "Collar (~₹45 Put, NO Fut SL)", "c_delta": 0.30, "p_delta": 0.12, "trail": True, "fut_sl": False},

        # Collar with ~₹75 Put (0.18 Delta Put - Tight Protection)
        {"name": "Collar (~₹75 Put, With Fut SL)", "c_delta": 0.30, "p_delta": 0.18, "trail": True, "fut_sl": True},
        {"name": "Collar (~₹75 Put, NO Fut SL)", "c_delta": 0.30, "p_delta": 0.18, "trail": True, "fut_sl": False},

        # Optimal Delta Combination: 0.25 Delta Call + ~₹25 Put
        {"name": "Collar 0.25C + 0.07P (With Fut SL)", "c_delta": 0.25, "p_delta": 0.07, "trail": True, "fut_sl": True},
        {"name": "Collar 0.25C + 0.07P (NO Fut SL)", "c_delta": 0.25, "p_delta": 0.07, "trail": True, "fut_sl": False},
    ]

    collar_results = {}
    all_collar_trades = []

    for cfg in collar_configs:
        trades = run_simulation(
            df,
            config_name=cfg["name"],
            call_delta=cfg["c_delta"],
            put_delta=cfg["p_delta"],
            use_trailing=cfg["trail"],
            use_futures_stop=cfg["fut_sl"],
        )
        collar_results[cfg["name"]] = compute_metrics(trades)
        all_collar_trades.extend([t.__dict__ for t in trades])

    df_collar_summary = pd.DataFrame(collar_results).T
    print("\n--- COLLAR STRATEGY COMPARISON MATRIX ---")
    print(df_collar_summary[["Total Net P&L (₹)", "Win Rate (%)", "Profit Factor", "Max Drawdown (₹)", "Sharpe Ratio", "Put Net Impact (₹)", "Largest Loss (₹)"]].to_string())

    # Export to disk
    out_dir = Path("backtesting/nifty_covered_call")
    df_delta_summary.to_csv(out_dir / "delta_sensitivity_metrics.csv")
    pd.DataFrame(all_delta_trades).to_csv(out_dir / "trades_delta_sensitivity.csv", index=False)
    
    df_collar_summary.to_csv(out_dir / "collar_comparison_metrics.csv")
    pd.DataFrame(all_collar_trades).to_csv(out_dir / "trades_collar_comparison.csv", index=False)

    print(f"\n[✓] Results successfully exported to {out_dir}/:")
    print("    - delta_sensitivity_metrics.csv")
    print("    - trades_delta_sensitivity.csv")
    print("    - collar_comparison_metrics.csv")
    print("    - trades_collar_comparison.csv")


if __name__ == "__main__":
    main()
