"""
================================================================================
AGY — PHASE 2 / EXPERIMENT 002D
NIFTY F&O EMA (9/21) + Trading Session Filter (09:45–14:45 IST) Research
================================================================================
Controlled single-variable experiment comparing:
- CONTROL  : Pure EMA(9/21) Crossover
- TREATMENT: EMA(9/21) Crossover + Trading Session Filter (09:45 to 14:45 IST)

Uses:
- Identical 1-Hour NIFTY Futures proxy dataset (730 days / 5057 bars)
- Identical 70% In-Sample / 30% Out-of-Sample chronological split
- Zero look-ahead: Signals on closed bar t, execution on Open of bar t+1
- Identical Indian statutory transaction costs (Brokerage, STT, Txn, GST, Stamp, SEBI)
- Identical slippage (0.5 index points per leg)
================================================================================
"""

import os
import sys
from dataclasses import dataclass
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Import contract specifications and data handler from research suite
from research.analysis.nifty_fo_research import (
    NiftyFuturesSpec,
    NiftyDataEngine,
    calculate_nifty_transaction_cost,
    TradeRecord,
)


class NiftySessionBacktestEngine:
    def __init__(
        self,
        spec: NiftyFuturesSpec = NiftyFuturesSpec(),
        initial_capital: float = 1_000_000.0,
        contracts: int = 2
    ):
        self.spec = spec
        self.initial_capital = initial_capital
        self.contracts = contracts
        self.qty = contracts * spec.lot_size

    def run_backtest(
        self,
        df: pd.DataFrame,
        fast_period: int = 9,
        slow_period: int = 21,
        use_session_filter: bool = False,
        session_start: dtime = dtime(9, 45),
        session_end: dtime = dtime(14, 45),
        enable_shorts: bool = True
    ) -> Tuple[List[TradeRecord], pd.Series, Dict[str, Any]]:
        close = df["close"].values
        open_arr = df["open"].values
        times = df.index
        n = len(df)

        if n < slow_period + 10:
            return [], pd.Series(dtype=float), {}

        # Indicators
        ema_fast = pd.Series(close).ewm(span=fast_period, adjust=False).mean().values
        ema_slow = pd.Series(close).ewm(span=slow_period, adjust=False).mean().values

        # Generate signals on closed bar i
        long_entries = np.zeros(n, dtype=bool)
        short_entries = np.zeros(n, dtype=bool)
        long_exits = np.zeros(n, dtype=bool)
        short_exits = np.zeros(n, dtype=bool)

        for i in range(1, n):
            crossover_bull = (ema_fast[i] > ema_slow[i]) and (ema_fast[i-1] <= ema_slow[i-1])
            crossover_bear = (ema_fast[i] < ema_slow[i]) and (ema_fast[i-1] >= ema_slow[i-1])

            if crossover_bear:
                long_exits[i] = True
            if crossover_bull:
                short_exits[i] = True

            if crossover_bull:
                long_entries[i] = True
            if crossover_bear:
                short_entries[i] = True

        # Execution loop (Next-bar Open execution)
        trades: List[TradeRecord] = []
        equity = self.initial_capital
        equity_series = np.zeros(n)
        equity_series[0] = equity

        position = 0  # 1 for Long, -1 for Short, 0 for Flat
        entry_price = 0.0
        entry_time = times[0]
        entry_idx = 0
        trade_id = 0

        for i in range(1, n):
            prev_long_entry = long_entries[i-1]
            prev_short_entry = short_entries[i-1]
            prev_long_exit = long_exits[i-1]
            prev_short_exit = short_exits[i-1]
            exec_open = open_arr[i]
            bar_time = times[i].time()

            # Session timing filter for fresh entry execution
            session_permitted = True
            if use_session_filter:
                session_permitted = (bar_time >= session_start) and (bar_time <= session_end)

            if position == 1:
                # Exit Long
                if prev_long_exit or prev_short_entry:
                    exit_p = exec_open - self.spec.slippage_points
                    pts_diff = exit_p - entry_price
                    gross_pnl = pts_diff * self.qty
                    fees, slippage, friction = calculate_nifty_transaction_cost(
                        self.spec, entry_price, exit_p, self.qty
                    )
                    net_pnl = gross_pnl - friction
                    equity += net_pnl
                    trade_id += 1

                    trades.append(TradeRecord(
                        trade_id=trade_id,
                        direction="LONG",
                        entry_time=entry_time,
                        entry_price=entry_price,
                        exit_time=times[i],
                        exit_price=exit_p,
                        qty=self.qty,
                        gross_pnl_pts=pts_diff,
                        gross_pnl_inr=gross_pnl,
                        statutory_fees=fees,
                        slippage_cost=slippage,
                        net_pnl_inr=net_pnl,
                        return_pct=(pts_diff / entry_price) * 100.0,
                        holding_bars=i - entry_idx,
                        exit_reason="BEARISH_CROSS"
                    ))

                    if prev_short_entry and enable_shorts and session_permitted:
                        position = -1
                        entry_price = exec_open - self.spec.slippage_points
                        entry_time = times[i]
                        entry_idx = i
                    else:
                        position = 0

            elif position == -1:
                # Exit Short
                if prev_short_exit or prev_long_entry:
                    exit_p = exec_open + self.spec.slippage_points
                    pts_diff = entry_price - exit_p
                    gross_pnl = pts_diff * self.qty
                    fees, slippage, friction = calculate_nifty_transaction_cost(
                        self.spec, exit_p, entry_price, self.qty
                    )
                    net_pnl = gross_pnl - friction
                    equity += net_pnl
                    trade_id += 1

                    trades.append(TradeRecord(
                        trade_id=trade_id,
                        direction="SHORT",
                        entry_time=entry_time,
                        entry_price=entry_price,
                        exit_time=times[i],
                        exit_price=exit_p,
                        qty=self.qty,
                        gross_pnl_pts=pts_diff,
                        gross_pnl_inr=gross_pnl,
                        statutory_fees=fees,
                        slippage_cost=slippage,
                        net_pnl_inr=net_pnl,
                        return_pct=(pts_diff / entry_price) * 100.0,
                        holding_bars=i - entry_idx,
                        exit_reason="BULLISH_CROSS"
                    ))

                    if prev_long_entry and session_permitted:
                        position = 1
                        entry_price = exec_open + self.spec.slippage_points
                        entry_time = times[i]
                        entry_idx = i
                    else:
                        position = 0

            elif position == 0:
                if prev_long_entry and session_permitted:
                    position = 1
                    entry_price = exec_open + self.spec.slippage_points
                    entry_time = times[i]
                    entry_idx = i
                elif prev_short_entry and enable_shorts and session_permitted:
                    position = -1
                    entry_price = exec_open - self.spec.slippage_points
                    entry_time = times[i]
                    entry_idx = i

            equity_series[i] = equity

        eq_s = pd.Series(equity_series, index=times)
        metrics = self._calculate_metrics(trades, eq_s)
        return trades, eq_s, metrics

    def _calculate_metrics(
        self,
        trades: List[TradeRecord],
        equity_series: pd.Series
    ) -> Dict[str, Any]:
        if not trades:
            return {
                "total_trades": 0, "net_pnl_inr": 0.0, "net_pnl_pts": 0.0,
                "return_pct": 0.0, "win_rate": 0.0, "profit_factor": 0.0,
                "expectancy_inr": 0.0, "max_drawdown_inr": 0.0, "max_drawdown_pct": 0.0,
                "sharpe": 0.0, "sortino": 0.0, "recovery_factor": 0.0,
                "max_consecutive_losses": 0, "long_trades": 0, "long_pnl_inr": 0.0,
                "short_trades": 0, "short_pnl_inr": 0.0
            }

        pnl_arr = np.array([t.net_pnl_inr for t in trades])
        pts_arr = np.array([t.gross_pnl_pts for t in trades])
        wins = pnl_arr[pnl_arr > 0]
        losses = pnl_arr[pnl_arr < 0]

        total_trades = len(trades)
        net_pnl_inr = float(np.sum(pnl_arr))
        net_pnl_pts = float(np.sum(pts_arr))
        return_pct = (net_pnl_inr / self.initial_capital) * 100.0

        win_rate = (len(wins) / total_trades) * 100.0 if total_trades > 0 else 0.0
        gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
        gross_loss = float(abs(np.sum(losses))) if len(losses) > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        expectancy_inr = net_pnl_inr / total_trades if total_trades > 0 else 0.0

        # Drawdown
        running_max = np.maximum.accumulate(equity_series.values)
        drawdown_arr = equity_series.values - running_max
        max_dd_inr = float(abs(np.min(drawdown_arr)))
        drawdown_pct_arr = np.where(running_max > 0, drawdown_arr / running_max, 0)
        max_dd_pct = float(abs(np.min(drawdown_pct_arr))) * 100.0
        recovery_factor = (net_pnl_inr / max_dd_inr) if max_dd_inr > 0 else (99.0 if net_pnl_inr > 0 else 0.0)

        # Sharpe & Sortino
        daily_equity = equity_series.resample("1D").last().ffill().dropna()
        daily_returns = daily_equity.pct_change().dropna()
        rf_daily = 0.045 / 252.0
        excess_returns = daily_returns - rf_daily

        if len(daily_returns) > 1 and daily_returns.std() > 1e-9:
            sharpe = float((excess_returns.mean() / daily_returns.std()) * np.sqrt(252))
        else:
            sharpe = 0.0

        downside_std = daily_returns[daily_returns < 0].std()
        if len(daily_returns) > 1 and downside_std > 1e-9:
            sortino = float((excess_returns.mean() / downside_std) * np.sqrt(252))
        else:
            sortino = 0.0

        streak = 0
        max_streak = 0
        for p in pnl_arr:
            if p < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

        long_trades = [t for t in trades if t.direction == "LONG"]
        short_trades = [t for t in trades if t.direction == "SHORT"]
        long_pnl_inr = sum(t.net_pnl_inr for t in long_trades)
        short_pnl_inr = sum(t.net_pnl_inr for t in short_trades)

        return {
            "total_trades": total_trades,
            "net_pnl_inr": round(net_pnl_inr, 2),
            "net_pnl_pts": round(net_pnl_pts, 2),
            "return_pct": round(return_pct, 2),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy_inr": round(expectancy_inr, 2),
            "max_drawdown_inr": round(max_dd_inr, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "sharpe": round(sharpe, 2),
            "sortino": round(sortino, 2),
            "recovery_factor": round(recovery_factor, 2),
            "max_consecutive_losses": max_streak,
            "long_trades": len(long_trades),
            "long_pnl_inr": round(long_pnl_inr, 2),
            "short_trades": len(short_trades),
            "short_pnl_inr": round(short_pnl_inr, 2)
        }


def run_experiment_002d():
    spec = NiftyFuturesSpec()
    engine = NiftySessionBacktestEngine(spec=spec, initial_capital=1_000_000.0, contracts=2)

    # Ingest Identical Dataset
    df_1h = NiftyDataEngine.load_nifty_data(interval="1h", period="730d")

    # Identical 70% IS / 30% OOS Split
    split_idx = int(len(df_1h) * 0.70)
    df_is = df_1h.iloc[:split_idx].copy()
    df_oos = df_1h.iloc[split_idx:].copy()

    # 1. In-Sample Control (EMA 9/21)
    trades_is_ctrl, eq_is_ctrl, m_is_ctrl = engine.run_backtest(df_is, fast_period=9, slow_period=21, use_session_filter=False)

    # 2. In-Sample Treatment (EMA 9/21 + 09:45-14:45 IST Session Gate)
    trades_is_trt, eq_is_trt, m_is_trt = engine.run_backtest(df_is, fast_period=9, slow_period=21, use_session_filter=True, session_start=dtime(9, 45), session_end=dtime(14, 45))

    # 3. Out-of-Sample Control (EMA 9/21)
    trades_oos_ctrl, eq_oos_ctrl, m_oos_ctrl = engine.run_backtest(df_oos, fast_period=9, slow_period=21, use_session_filter=False)

    # 4. Out-of-Sample Treatment (EMA 9/21 + 09:45-14:45 IST Session Gate)
    trades_oos_trt, eq_oos_trt, m_oos_trt = engine.run_backtest(df_oos, fast_period=9, slow_period=21, use_session_filter=True, session_start=dtime(9, 45), session_end=dtime(14, 45))

    # Print Comparative Matrix
    print("\n" + "="*90)
    print("🔬 EXPERIMENT 002D: NIFTY 1-HOUR EMA(9/21) vs EMA(9/21) + SESSION FILTER (09:45–14:45 IST)")
    print("="*90)

    print("\n📊 1. IN-SAMPLE RESULTS (70% Dataset: 2023-09-20 to 2025-10-09):")
    print(f"{'Metric':<25} | {'Control (EMA 9/21)':<22} | {'Treatment (+ Session)':<25} | {'Delta / Change':<18}")
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

    print("\n📊 2. OUT-OF-SAMPLE RESULTS (30% Dataset: 2025-10-09 to 2026-08-31):")
    print(f"{'Metric':<25} | {'Control (EMA 9/21)':<22} | {'Treatment (+ Session)':<25} | {'Delta / Change':<18}")
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

    return {
        "m_is_ctrl": m_is_ctrl,
        "m_is_trt": m_is_trt,
        "m_oos_ctrl": m_oos_ctrl,
        "m_oos_trt": m_oos_trt,
    }


if __name__ == "__main__":
    run_experiment_002d()
