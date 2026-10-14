"""
================================================================================
AGY — EXPERIMENT 003
NIFTY F&O EMA 9/26 Baseline Research
================================================================================
Controlled single-variable experiment comparing:
- CONTROL  : Pure EMA(9/21) Crossover
- TREATMENT: Pure EMA(9/26) Crossover (Standard 26 Slow Period)

Uses:
- Identical 1-Hour NIFTY Futures proxy dataset (730 days / 5057 bars)
- Identical 70% In-Sample / 30% Out-of-Sample chronological split
- Zero look-ahead: Signals on closed bar t, execution on Open of bar t+1
- Identical Indian statutory transaction costs (Brokerage, STT, Txn, GST, Stamp, SEBI)
- Identical slippage (0.5 index points per leg)
- No additional filters
================================================================================
"""

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Import contract specifications and engine helpers from research suite
from research.analysis.nifty_fo_research import (
    NiftyFuturesSpec,
    NiftyDataEngine,
    NiftyBacktestEngine,
    calculate_nifty_transaction_cost,
    TradeRecord,
)


def run_experiment_003():
    spec = NiftyFuturesSpec()
    engine = NiftyBacktestEngine(spec=spec, initial_capital=1_000_000.0, contracts=2)

    # Ingest Identical 1-Hour Dataset
    df_1h = NiftyDataEngine.load_nifty_data(interval="1h", period="730d")

    # Identical 70% IS / 30% OOS Split
    split_idx = int(len(df_1h) * 0.70)
    df_is = df_1h.iloc[:split_idx].copy()
    df_oos = df_1h.iloc[split_idx:].copy()

    # 1. In-Sample Control (EMA 9/21)
    trades_is_ctrl, eq_is_ctrl, m_is_ctrl = engine.run_ema_crossover(df_is, fast_period=9, slow_period=21)

    # 2. In-Sample Treatment (EMA 9/26)
    trades_is_trt, eq_is_trt, m_is_trt = engine.run_ema_crossover(df_is, fast_period=9, slow_period=26)

    # 3. Out-of-Sample Control (EMA 9/21)
    trades_oos_ctrl, eq_oos_ctrl, m_oos_ctrl = engine.run_ema_crossover(df_oos, fast_period=9, slow_period=21)

    # 4. Out-of-Sample Treatment (EMA 9/26)
    trades_oos_trt, eq_oos_trt, m_oos_trt = engine.run_ema_crossover(df_oos, fast_period=9, slow_period=26)

    # Monthly OOS performance for Control & Treatment
    monthly_oos_ctrl = {}
    if trades_oos_ctrl:
        df_t_ctrl = pd.DataFrame([{"time": t.exit_time, "pnl": t.net_pnl_inr} for t in trades_oos_ctrl])
        df_t_ctrl["month"] = df_t_ctrl["time"].dt.to_period("M").astype(str)
        monthly_oos_ctrl = df_t_ctrl.groupby("month")["pnl"].sum().to_dict()

    monthly_oos_trt = {}
    if trades_oos_trt:
        df_t_trt = pd.DataFrame([{"time": t.exit_time, "pnl": t.net_pnl_inr} for t in trades_oos_trt])
        df_t_trt["month"] = df_t_trt["time"].dt.to_period("M").astype(str)
        monthly_oos_trt = df_t_trt.groupby("month")["pnl"].sum().to_dict()

    # Print Comparative Matrix
    print("\n" + "="*90)
    print("🔬 EXPERIMENT 003: NIFTY 1-HOUR EMA(9/21) vs EMA(9/26) BASELINE")
    print("="*90)

    print("\n📊 1. IN-SAMPLE RESULTS (70% Dataset: 2023-09-20 to 2025-10-09):")
    print(f"{'Metric':<25} | {'Control (EMA 9/21)':<22} | {'Treatment (EMA 9/26)':<25} | {'Delta / Change':<18}")
    print("-" * 95)
    trade_diff_is = m_is_trt['total_trades'] - m_is_ctrl['total_trades']
    trade_pct_is = (trade_diff_is / m_is_ctrl['total_trades']) * 100.0 if m_is_ctrl['total_trades'] > 0 else 0
    print(f"{'Total Trades':<25} | {m_is_ctrl['total_trades']:<22} | {m_is_trt['total_trades']:<25} | {trade_diff_is:+d} ({trade_pct_is:+.1f}%)")
    print(f"{'Net P&L (Rs)':<25} | Rs {m_is_ctrl['net_pnl_inr']:>16,.2f} | Rs {m_is_trt['net_pnl_inr']:>19,.2f} | Rs {m_is_trt['net_pnl_inr'] - m_is_ctrl['net_pnl_inr']:>+14,.2f}")
    print(f"{'Profit Factor':<25} | {m_is_ctrl['profit_factor']:<22.2f} | {m_is_trt['profit_factor']:<25.2f} | {m_is_trt['profit_factor'] - m_is_ctrl['profit_factor']:>+6.2f}")
    print(f"{'Win Rate %':<25} | {m_is_ctrl['win_rate']:>20.2f}% | {m_is_trt['win_rate']:>23.2f}% | {m_is_trt['win_rate'] - m_is_ctrl['win_rate']:>+6.2f}%")
    print(f"{'Expectancy (Rs/trade)':<25} | Rs {m_is_ctrl['expectancy_inr']:>16,.2f} | Rs {m_is_trt['expectancy_inr']:>19,.2f} | Rs {m_is_trt['expectancy_inr'] - m_is_ctrl['expectancy_inr']:>+14,.2f}")
    print(f"{'Max Drawdown %':<25} | {m_is_ctrl['max_drawdown_pct']:>20.2f}% | {m_is_trt['max_drawdown_pct']:>23.2f}% | {m_is_trt['max_drawdown_pct'] - m_is_ctrl['max_drawdown_pct']:>+6.2f}%")
    print(f"{'Sharpe Ratio':<25} | {m_is_ctrl['sharpe']:<22.2f} | {m_is_trt['sharpe']:<25.2f} | {m_is_trt['sharpe'] - m_is_ctrl['sharpe']:>+6.2f}")
    print(f"{'Sortino Ratio':<25} | {m_is_ctrl['sortino']:<22.2f} | {m_is_trt['sortino']:<25.2f} | {m_is_trt['sortino'] - m_is_ctrl['sortino']:>+6.2f}")
    print(f"{'Long P&L (Rs)':<25} | Rs {m_is_ctrl['long_pnl_inr']:>16,.2f} | Rs {m_is_trt['long_pnl_inr']:>19,.2f} | Rs {m_is_trt['long_pnl_inr'] - m_is_ctrl['long_pnl_inr']:>+14,.2f}")
    print(f"{'Short P&L (Rs)':<25} | Rs {m_is_ctrl['short_pnl_inr']:>16,.2f} | Rs {m_is_trt['short_pnl_inr']:>19,.2f} | Rs {m_is_trt['short_pnl_inr'] - m_is_ctrl['short_pnl_inr']:>+14,.2f}")

    print("\n📊 2. OUT-OF-SAMPLE RESULTS (30% Dataset: 2025-10-09 to 2026-08-31):")
    print(f"{'Metric':<25} | {'Control (EMA 9/21)':<22} | {'Treatment (EMA 9/26)':<25} | {'Delta / Change':<18}")
    print("-" * 95)
    trade_diff_oos = m_oos_trt['total_trades'] - m_oos_ctrl['total_trades']
    trade_pct_oos = (trade_diff_oos / m_oos_ctrl['total_trades']) * 100.0 if m_oos_ctrl['total_trades'] > 0 else 0
    print(f"{'Total Trades':<25} | {m_oos_ctrl['total_trades']:<22} | {m_oos_trt['total_trades']:<25} | {trade_diff_oos:+d} ({trade_pct_oos:+.1f}%)")
    print(f"{'Net P&L (Rs)':<25} | Rs {m_oos_ctrl['net_pnl_inr']:>16,.2f} | Rs {m_oos_trt['net_pnl_inr']:>19,.2f} | Rs {m_oos_trt['net_pnl_inr'] - m_oos_ctrl['net_pnl_inr']:>+14,.2f}")
    print(f"{'Profit Factor':<25} | {m_oos_ctrl['profit_factor']:<22.2f} | {m_oos_trt['profit_factor']:<25.2f} | {m_oos_trt['profit_factor'] - m_oos_ctrl['profit_factor']:>+6.2f}")
    print(f"{'Win Rate %':<25} | {m_oos_ctrl['win_rate']:>20.2f}% | {m_oos_trt['win_rate']:>23.2f}% | {m_oos_trt['win_rate'] - m_oos_ctrl['win_rate']:>+6.2f}%")
    print(f"{'Expectancy (Rs/trade)':<25} | Rs {m_oos_ctrl['expectancy_inr']:>16,.2f} | Rs {m_oos_trt['expectancy_inr']:>19,.2f} | Rs {m_oos_trt['expectancy_inr'] - m_oos_ctrl['expectancy_inr']:>+14,.2f}")
    print(f"{'Max Drawdown %':<25} | {m_oos_ctrl['max_drawdown_pct']:>20.2f}% | {m_oos_trt['max_drawdown_pct']:>23.2f}% | {m_oos_trt['max_drawdown_pct'] - m_oos_ctrl['max_drawdown_pct']:>+6.2f}%")
    print(f"{'Sharpe Ratio':<25} | {m_oos_ctrl['sharpe']:<22.2f} | {m_oos_trt['sharpe']:<25.2f} | {m_oos_trt['sharpe'] - m_oos_ctrl['sharpe']:>+6.2f}")
    print(f"{'Sortino Ratio':<25} | {m_oos_ctrl['sortino']:<22.2f} | {m_oos_trt['sortino']:<25.2f} | {m_oos_trt['sortino'] - m_oos_ctrl['sortino']:>+6.2f}")
    print(f"{'Long P&L (Rs)':<25} | Rs {m_oos_ctrl['long_pnl_inr']:>16,.2f} | Rs {m_oos_trt['long_pnl_inr']:>19,.2f} | Rs {m_oos_trt['long_pnl_inr'] - m_oos_ctrl['long_pnl_inr']:>+14,.2f}")
    print(f"{'Short P&L (Rs)':<25} | Rs {m_oos_ctrl['short_pnl_inr']:>16,.2f} | Rs {m_oos_trt['short_pnl_inr']:>19,.2f} | Rs {m_oos_trt['short_pnl_inr'] - m_oos_ctrl['short_pnl_inr']:>+14,.2f}")

    print("\n📅 3. MONTHLY OUT-OF-SAMPLE PERFORMANCE (Oct 2025 to Aug 2026):")
    all_months = sorted(list(set(list(monthly_oos_ctrl.keys()) + list(monthly_oos_trt.keys()))))
    print(f"{'Month':<10} | {'Control (9/21) Net P&L':<24} | {'Treatment (9/26) Net P&L':<26} | {'Delta':<15}")
    print("-" * 80)
    for m in all_months:
        c_val = monthly_oos_ctrl.get(m, 0.0)
        t_val = monthly_oos_trt.get(m, 0.0)
        print(f"{m:<10} | Rs {c_val:>18,.2f} | Rs {t_val:>20,.2f} | Rs {t_val - c_val:>+12,.2f}")

    return {
        "m_is_ctrl": m_is_ctrl,
        "m_is_trt": m_is_trt,
        "m_oos_ctrl": m_oos_ctrl,
        "m_oos_trt": m_oos_trt,
        "monthly_oos_ctrl": monthly_oos_ctrl,
        "monthly_oos_trt": monthly_oos_trt,
    }


if __name__ == "__main__":
    run_experiment_003()
