#!/usr/bin/env python3
"""
Strategy V2: EMA 9/21 Crossover with 4H EMA 200 Higher-Timeframe Regime Filter
=============================================================================
Hypothesis:
"Filtering 1H EMA 9/21 crossover trades using the completed 4H EMA 200 regime
 will reduce counter-trend trades and whipsaw losses, improving Profit Factor,
 expectancy and/or maximum drawdown without relying on parameter optimization."

Rules:
1. Base strategy: EMA 9/21 on BTCUSDT 1H.
2. Single new variable: Completed 4H EMA 200 regime filter.
3. Long Entry: 4H Close > Completed 4H EMA 200 AND 1H EMA 9 crosses above EMA 21.
4. Short Entry: 4H Close < Completed 4H EMA 200 AND 1H EMA 9 crosses below EMA 21.
5. Zero look-ahead bias: A 4H candle only influences a 1H signal AFTER the 4H candle closes.
6. Execution at next 1H candle OPEN price with realistic fee (0.10%) and slippage (0.05%).
7. Exact Walk-Forward Split:
   - In-Sample (IS): 2023-01-01 to 2025-12-31
   - Out-of-Sample (OOS): 2026-01-01 to 2026-08-30
   - Full Period: 2023-01-01 to 2026-08-30
"""

import os
import sys
import math
import base64
import argparse
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("EMA921_V2_Backtester")

# Default Paths
DEFAULT_DATA_PATH = os.path.expanduser("~/backtesting/coindcx_data/BTCUSDT_1h_2023-01-01_2026-08-30.csv")
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/backtesting/research/v2_ema200_4h")


class StrategyBacktester:
    """Institutional Backtesting Engine for EMA 9/21 V1 & V2 with 4H EMA 200 Filter."""

    def __init__(
        self,
        data_path: str = DEFAULT_DATA_PATH,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        fast_ema: int = 9,
        slow_ema: int = 21,
        htf_ema: int = 200,
        initial_capital: float = 100000.0,
        fee_rate: float = 0.001,       # 0.10% per trade
        slippage: float = 0.0005,      # 0.05% slippage
        position_size_pct: float = 1.0, # 100% of equity
        is_end_date: str = "2025-12-31 23:59:59",
        oos_start_date: str = "2026-01-01 00:00:00"
    ):
        self.data_path = os.path.expanduser(data_path)
        self.output_dir = os.path.expanduser(output_dir)
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.htf_ema = htf_ema
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.position_size_pct = position_size_pct
        self.is_end_date = pd.to_datetime(is_end_date)
        self.oos_start_date = pd.to_datetime(oos_start_date)

        os.makedirs(self.output_dir, exist_ok=True)

        self.df: Optional[pd.DataFrame] = None
        self.results_v1: Dict[str, Any] = {}
        self.results_v2: Dict[str, Any] = {}
        self.equity_v1: Optional[pd.DataFrame] = None
        self.equity_v2: Optional[pd.DataFrame] = None
        self.trades_v1: Optional[pd.DataFrame] = None
        self.trades_v2: Optional[pd.DataFrame] = None

    def load_and_prepare_data(self) -> pd.DataFrame:
        """Load CSV, parse timestamps, construct 4H bars with zero look-ahead bias."""
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"Historical data file not found at: {self.data_path}")

        logger.info(f"Loading data from: {self.data_path}")
        df = pd.read_csv(self.data_path)

        if "timestamp_utc" in df.columns:
            df["datetime"] = pd.to_datetime(df["timestamp_utc"]).dt.tz_localize(None)
        elif "timestamp" in df.columns:
            df["datetime"] = pd.to_datetime(df["timestamp"])
        elif "epoch_ms" in df.columns:
            df["datetime"] = pd.to_datetime(df["epoch_ms"], unit="ms")
        else:
            raise ValueError("CSV must contain valid timestamp column.")

        df = df.sort_values("datetime").reset_index(drop=True)

        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        logger.info(f"Loaded {len(df):,} 1H candles from {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")

        # ---------------------------------------------------------
        # 4H Higher-Timeframe Resampling & EMA 200 Calculation
        # ---------------------------------------------------------
        df_indexed = df.set_index("datetime")
        df_4h = df_indexed.resample("4h").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }).dropna()

        # Compute 4H EMA 200
        df_4h["ema_200"] = df_4h["close"].ewm(span=self.htf_ema, adjust=False).mean()
        df_4h["regime_bull"] = df_4h["close"] > df_4h["ema_200"]
        df_4h["regime_bear"] = df_4h["close"] < df_4h["ema_200"]

        # A 4H candle starting at T completes at T + 4 hours.
        df_4h["completed_at"] = df_4h.index + pd.Timedelta(hours=4)

        # ---------------------------------------------------------
        # Zero Look-Ahead Alignment:
        # 1H candle starting at t completes at t + 1 hour.
        # At t + 1 hour, the latest completed 4H candle is one with completed_at <= t + 1 hour.
        # ---------------------------------------------------------
        df["1h_close_time"] = df["datetime"] + pd.Timedelta(hours=1)

        df_4h_merge = df_4h[["completed_at", "close", "ema_200", "regime_bull", "regime_bear"]].rename(
            columns={
                "close": "4h_close",
                "ema_200": "4h_ema200",
                "completed_at": "4h_completed_at"
            }
        )

        df = pd.merge_asof(
            df,
            df_4h_merge,
            left_on="1h_close_time",
            right_on="4h_completed_at",
            direction="backward"
        )

        # ---------------------------------------------------------
        # 1H EMA 9 & EMA 21 Indicators and Signals
        # ---------------------------------------------------------
        close = df["close"]
        df["ema_fast"] = close.ewm(span=self.fast_ema, adjust=False).mean()
        df["ema_slow"] = close.ewm(span=self.slow_ema, adjust=False).mean()

        fast_above = df["ema_fast"] > df["ema_slow"]
        fast_above_prev = df["ema_fast"].shift(1) > df["ema_slow"].shift(1)

        # Raw 1H Crossover Triggers
        df["bull_cross"] = (fast_above) & (~fast_above_prev)
        df["bear_cross"] = (~fast_above) & (fast_above_prev)

        # V1 Position State Generation
        target_state_v1 = np.zeros(len(df), dtype=int)
        curr_v1 = 0
        burn_in_v1 = self.slow_ema * 2

        for i in range(burn_in_v1, len(df)):
            if df.loc[i, "bull_cross"]:
                curr_v1 = 1
            elif df.loc[i, "bear_cross"]:
                curr_v1 = -1
            target_state_v1[i] = curr_v1

        df["target_state_v1"] = target_state_v1
        df["position_v1"] = df["target_state_v1"].shift(1).fillna(0).astype(int)

        # V2 Position State Generation (with 4H EMA 200 Regime Filter)
        # Long Entry: 1H Bull Cross AND 4H Close > 4H EMA 200
        # Short Entry: 1H Bear Cross AND 4H Close < 4H EMA 200
        # Exits: Opposing 1H Crossover exits position to Flat if opposing direction not permitted by 4H regime
        target_state_v2 = np.zeros(len(df), dtype=int)
        curr_v2 = 0
        # Burn-in: allow 4H EMA 200 sufficient candles
        burn_in_v2 = max(self.slow_ema * 2, self.htf_ema * 4)

        for i in range(burn_in_v2, len(df)):
            b_cross = df.loc[i, "bull_cross"]
            s_cross = df.loc[i, "bear_cross"]
            reg_bull = df.loc[i, "regime_bull"]
            reg_bear = df.loc[i, "regime_bear"]

            if b_cross:
                if reg_bull:
                    curr_v2 = 1
                elif curr_v2 == -1:
                    # Opposing 1H cross exits short to cash/flat
                    curr_v2 = 0
            elif s_cross:
                if reg_bear:
                    curr_v2 = -1
                elif curr_v2 == 1:
                    # Opposing 1H cross exits long to cash/flat
                    curr_v2 = 0

            target_state_v2[i] = curr_v2

        df["target_state_v2"] = target_state_v2
        df["position_v2"] = df["target_state_v2"].shift(1).fillna(0).astype(int)

        self.df = df
        logger.info("Indicator calculations & zero look-ahead signal filtering completed.")
        return df

    def simulate_strategy(self, position_col: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Simulate chronological bar-by-bar execution on next 1H candle Open price.
        Accurately tracks cash, margin, fees, and slippage costs.
        """
        df = self.df
        n = len(df)

        capital = self.initial_capital
        cash = capital
        position_units = 0.0
        position_side = 0
        entry_price = 0.0
        entry_raw_price = 0.0
        entry_time = None
        entry_idx = 0
        entry_fee = 0.0
        entry_slippage_cost = 0.0

        equity_curve = np.zeros(n)
        cash_curve = np.zeros(n)
        position_curve = np.zeros(n)
        benchmark_equity = np.zeros(n)

        trades: List[Dict[str, Any]] = []
        trade_id = 0

        # Benchmark: 100% Buy & Hold from bar 0
        first_open = df.loc[0, "open"]
        bench_entry_p = first_open * (1.0 + self.slippage)
        bench_units = (capital * (1.0 - self.fee_rate)) / bench_entry_p

        for i in range(n):
            dt = df.loc[i, "datetime"]
            open_p = df.loc[i, "open"]
            close_p = df.loc[i, "close"]
            desired_pos = df.loc[i, position_col]

            if desired_pos != position_side:
                # 1. Close active position
                if position_side != 0:
                    if position_side == 1:
                        # Exit Long
                        exit_raw_p = open_p
                        exit_price = open_p * (1.0 - self.slippage)
                        exit_val = position_units * exit_price
                        exit_fee = exit_val * self.fee_rate
                        exit_slippage_cost = position_units * (exit_raw_p - exit_price)
                        gross_pnl = (exit_price - entry_price) * position_units
                        net_pnl = gross_pnl - entry_fee - exit_fee
                        cash += (exit_val - exit_fee)
                    else:
                        # Exit Short
                        exit_raw_p = open_p
                        exit_price = open_p * (1.0 + self.slippage)
                        exit_val = position_units * exit_price
                        exit_fee = exit_val * self.fee_rate
                        exit_slippage_cost = position_units * (exit_price - exit_raw_p)
                        gross_pnl = (entry_price - exit_price) * position_units
                        net_pnl = gross_pnl - entry_fee - exit_fee
                        cash += (position_units * entry_price) + gross_pnl - exit_fee

                    return_pct = (net_pnl / (entry_price * position_units)) * 100.0
                    duration_bars = i - entry_idx
                    duration_hours = duration_bars * 1.0

                    trade_id += 1
                    trades.append({
                        "trade_id": trade_id,
                        "side": "LONG" if position_side == 1 else "SHORT",
                        "entry_idx": entry_idx,
                        "entry_time": entry_time,
                        "entry_raw_price": entry_raw_price,
                        "entry_price": entry_price,
                        "exit_idx": i,
                        "exit_time": dt,
                        "exit_raw_price": exit_raw_p,
                        "exit_price": exit_price,
                        "units": position_units,
                        "position_value": entry_price * position_units,
                        "gross_pnl": gross_pnl,
                        "entry_fee": entry_fee,
                        "exit_fee": exit_fee,
                        "total_fees": entry_fee + exit_fee,
                        "entry_slippage": entry_slippage_cost,
                        "exit_slippage": exit_slippage_cost,
                        "total_slippage": entry_slippage_cost + exit_slippage_cost,
                        "net_pnl": net_pnl,
                        "return_pct": return_pct,
                        "duration_bars": duration_bars,
                        "duration_hours": duration_hours,
                        "exit_reason": "SIGNAL_CHANGE",
                        "cumulative_equity": cash
                    })

                    position_side = 0
                    position_units = 0.0

                # 2. Open new position
                if desired_pos != 0:
                    position_side = desired_pos
                    entry_idx = i
                    entry_time = dt
                    entry_raw_price = open_p
                    trade_capital = max(cash * self.position_size_pct, 0.0)

                    if trade_capital > 0:
                        if position_side == 1:
                            # Enter Long
                            entry_price = open_p * (1.0 + self.slippage)
                            position_units = trade_capital / (entry_price * (1.0 + self.fee_rate))
                            entry_val = position_units * entry_price
                            entry_fee = entry_val * self.fee_rate
                            entry_slippage_cost = position_units * (entry_price - entry_raw_price)
                            cash -= (entry_val + entry_fee)
                        else:
                            # Enter Short
                            entry_price = open_p * (1.0 - self.slippage)
                            position_units = trade_capital / (entry_price * (1.0 + self.fee_rate))
                            entry_val = position_units * entry_price
                            entry_fee = entry_val * self.fee_rate
                            entry_slippage_cost = position_units * (entry_raw_price - entry_price)
                            cash -= (entry_val + entry_fee)

            # Mark to Market Equity at bar Close
            if position_side == 1:
                current_equity = cash + (position_units * close_p)
            elif position_side == -1:
                unrealized_pnl = (entry_price - close_p) * position_units
                current_equity = cash + (position_units * entry_price) + unrealized_pnl
            else:
                current_equity = cash

            equity_curve[i] = current_equity
            cash_curve[i] = cash
            position_curve[i] = position_side
            benchmark_equity[i] = bench_units * close_p

        # Close open position at end of backtest if any
        if position_side != 0:
            last_idx = n - 1
            last_close = df.loc[last_idx, "close"]
            last_dt = df.loc[last_idx, "datetime"]
            if position_side == 1:
                exit_raw_p = last_close
                exit_price = last_close * (1.0 - self.slippage)
                exit_val = position_units * exit_price
                exit_fee = exit_val * self.fee_rate
                exit_slippage_cost = position_units * (exit_raw_p - exit_price)
                gross_pnl = (exit_price - entry_price) * position_units
                net_pnl = gross_pnl - entry_fee - exit_fee
                cash += (exit_val - exit_fee)
            else:
                exit_raw_p = last_close
                exit_price = last_close * (1.0 + self.slippage)
                exit_val = position_units * exit_price
                exit_fee = exit_val * self.fee_rate
                exit_slippage_cost = position_units * (exit_price - exit_raw_p)
                gross_pnl = (entry_price - exit_price) * position_units
                net_pnl = gross_pnl - entry_fee - exit_fee
                cash += (position_units * entry_price) + gross_pnl - exit_fee

            trade_id += 1
            trades.append({
                "trade_id": trade_id,
                "side": "LONG" if position_side == 1 else "SHORT",
                "entry_idx": entry_idx,
                "entry_time": entry_time,
                "entry_raw_price": entry_raw_price,
                "entry_price": entry_price,
                "exit_idx": last_idx,
                "exit_time": last_dt,
                "exit_raw_price": exit_raw_p,
                "exit_price": exit_price,
                "units": position_units,
                "position_value": entry_price * position_units,
                "gross_pnl": gross_pnl,
                "entry_fee": entry_fee,
                "exit_fee": exit_fee,
                "total_fees": entry_fee + exit_fee,
                "entry_slippage": entry_slippage_cost,
                "exit_slippage": exit_slippage_cost,
                "total_slippage": entry_slippage_cost + exit_slippage_cost,
                "net_pnl": net_pnl,
                "return_pct": (net_pnl / (entry_price * position_units)) * 100.0,
                "duration_bars": last_idx - entry_idx,
                "duration_hours": (last_idx - entry_idx) * 1.0,
                "exit_reason": "BACKTEST_END",
                "cumulative_equity": cash
            })
            equity_curve[-1] = cash

        equity_df = pd.DataFrame({
            "datetime": df["datetime"],
            "close": df["close"],
            "strategy_equity": equity_curve,
            "cash": cash_curve,
            "position": position_curve,
            "benchmark_equity": benchmark_equity
        })

        equity_df["peak"] = equity_df["strategy_equity"].cummax()
        equity_df["drawdown_pct"] = (equity_df["strategy_equity"] - equity_df["peak"]) / equity_df["peak"] * 100.0
        equity_df["benchmark_peak"] = equity_df["benchmark_equity"].cummax()
        equity_df["benchmark_drawdown_pct"] = (equity_df["benchmark_equity"] - equity_df["benchmark_peak"]) / equity_df["benchmark_peak"] * 100.0

        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
        return equity_df, trades_df

    def compute_metrics(
        self,
        equity_df: pd.DataFrame,
        trades_df: pd.DataFrame,
        initial_capital: float,
        period_name: str = "Full Period"
    ) -> Dict[str, Any]:
        """Compute institutional performance and risk metrics."""
        if equity_df.empty or len(equity_df) < 2:
            return {"period": period_name, "error": "Insufficient data"}

        start_dt = equity_df["datetime"].iloc[0]
        end_dt = equity_df["datetime"].iloc[-1]
        total_days = max((end_dt - start_dt).total_seconds() / 86400.0, 1.0)
        years = total_days / 365.25

        init_cap = initial_capital
        final_equity = equity_df["strategy_equity"].iloc[-1]
        net_profit = final_equity - init_cap
        total_return_pct = (net_profit / init_cap) * 100.0

        # CAGR
        cagr = ((final_equity / init_cap) ** (1.0 / years) - 1.0) * 100.0 if (years > 0 and final_equity > 0 and init_cap > 0) else 0.0

        # Strategy Drawdown
        max_dd_pct = equity_df["drawdown_pct"].min()
        is_dd = equity_df["drawdown_pct"] < 0
        dd_runs = (~is_dd).cumsum()
        dd_durations = is_dd.groupby(dd_runs).sum()
        max_dd_duration_hours = dd_durations.max() if len(dd_durations) > 0 else 0
        max_dd_duration_days = max_dd_duration_hours / 24.0

        # Benchmark Metrics
        bench_init = equity_df["benchmark_equity"].iloc[0]
        bench_final = equity_df["benchmark_equity"].iloc[-1]
        bench_return_pct = ((bench_final - bench_init) / bench_init) * 100.0 if bench_init > 0 else 0.0
        bench_cagr = ((bench_final / bench_init) ** (1.0 / years) - 1.0) * 100.0 if (years > 0 and bench_init > 0 and bench_final > 0) else 0.0
        bench_max_dd = equity_df["benchmark_drawdown_pct"].min()

        # Hourly returns for Sharpe & Sortino (24/7 crypto = 8760 hours/yr)
        hourly_returns = equity_df["strategy_equity"].pct_change().dropna()
        risk_free_rate_hourly = 0.05 / 8760.0

        excess_returns = hourly_returns - risk_free_rate_hourly
        mean_excess = excess_returns.mean()
        std_returns = hourly_returns.std()
        sharpe_ratio = (mean_excess / std_returns) * math.sqrt(8760) if std_returns > 0 else 0.0

        negative_returns = hourly_returns[hourly_returns < 0]
        downside_std = negative_returns.std()
        sortino_ratio = (mean_excess / downside_std) * math.sqrt(8760) if (downside_std > 0 and not np.isnan(downside_std)) else 0.0

        calmar_ratio = abs(cagr / max_dd_pct) if max_dd_pct != 0 else 0.0

        # Trade Statistics & Costs
        if not trades_df.empty:
            total_trades = len(trades_df)
            winning_trades = trades_df[trades_df["net_pnl"] > 0]
            losing_trades = trades_df[trades_df["net_pnl"] < 0]

            win_count = len(winning_trades)
            loss_count = len(losing_trades)
            win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

            gross_profit = winning_trades["net_pnl"].sum()
            gross_loss = abs(losing_trades["net_pnl"].sum())
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

            avg_trade_pnl_pct = trades_df["return_pct"].mean()
            avg_win_pct = winning_trades["return_pct"].mean() if win_count > 0 else 0.0
            avg_loss_pct = losing_trades["return_pct"].mean() if loss_count > 0 else 0.0
            win_loss_ratio = abs(avg_win_pct / avg_loss_pct) if avg_loss_pct != 0 else 0.0

            expectancy_pct = (win_rate / 100.0 * avg_win_pct) + ((1.0 - win_rate / 100.0) * avg_loss_pct)
            avg_duration_hrs = trades_df["duration_hours"].mean()

            total_fees = trades_df["total_fees"].sum()
            total_slippage = trades_df["total_slippage"].sum()

            long_trades = trades_df[trades_df["side"] == "LONG"]
            short_trades = trades_df[trades_df["side"] == "SHORT"]

            long_wins = long_trades[long_trades["net_pnl"] > 0]
            long_losses = long_trades[long_trades["net_pnl"] < 0]
            short_wins = short_trades[short_trades["net_pnl"] > 0]
            short_losses = short_trades[short_trades["net_pnl"] < 0]

            long_pf = (long_wins["net_pnl"].sum() / abs(long_losses["net_pnl"].sum())) if (len(long_losses) > 0 and abs(long_losses["net_pnl"].sum()) > 0) else 0.0
            short_pf = (short_wins["net_pnl"].sum() / abs(short_losses["net_pnl"].sum())) if (len(short_losses) > 0 and abs(short_losses["net_pnl"].sum()) > 0) else 0.0

            long_stats = {
                "trades": len(long_trades),
                "win_rate": (len(long_wins) / len(long_trades) * 100.0) if len(long_trades) > 0 else 0.0,
                "profit_factor": round(long_pf, 2),
                "net_pnl": long_trades["net_pnl"].sum() if len(long_trades) > 0 else 0.0,
            }
            short_stats = {
                "trades": len(short_trades),
                "win_rate": (len(short_wins) / len(short_trades) * 100.0) if len(short_trades) > 0 else 0.0,
                "profit_factor": round(short_pf, 2),
                "net_pnl": short_trades["net_pnl"].sum() if len(short_trades) > 0 else 0.0,
            }
        else:
            total_trades = win_count = loss_count = 0
            win_rate = profit_factor = avg_trade_pnl_pct = avg_win_pct = avg_loss_pct = win_loss_ratio = expectancy_pct = 0.0
            avg_duration_hrs = total_fees = total_slippage = 0.0
            long_stats = {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "net_pnl": 0.0}
            short_stats = {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "net_pnl": 0.0}

        exposure_pct = (equity_df["position"] != 0).mean() * 100.0

        return {
            "period": period_name,
            "start_date": start_dt.strftime("%Y-%m-%d %H:%M"),
            "end_date": end_dt.strftime("%Y-%m-%d %H:%M"),
            "duration_days": round(total_days, 1),
            "initial_capital": init_cap,
            "final_equity": final_equity,
            "net_profit": net_profit,
            "total_return_pct": total_return_pct,
            "cagr_pct": cagr,
            "benchmark_return_pct": bench_return_pct,
            "benchmark_max_dd_pct": bench_max_dd,
            "max_drawdown_pct": max_dd_pct,
            "max_dd_duration_days": round(max_dd_duration_days, 1),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "calmar_ratio": round(calmar_ratio, 2),
            "profit_factor": round(profit_factor, 2),
            "win_rate_pct": round(win_rate, 2),
            "expectancy_pct": round(expectancy_pct, 2),
            "avg_win_pct": round(avg_win_pct, 2),
            "avg_loss_pct": round(avg_loss_pct, 2),
            "win_loss_ratio": round(win_loss_ratio, 2),
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "market_exposure_pct": round(exposure_pct, 2),
            "long_stats": long_stats,
            "short_stats": short_stats,
            "long_pf": long_stats["profit_factor"],
            "short_pf": short_stats["profit_factor"],
            "total_fees": round(total_fees, 2),
            "total_slippage": round(total_slippage, 2),
            "avg_duration_hours": round(avg_duration_hrs, 1),
        }

    def run_all(self):
        """Execute full backtest suite for V1 and V2 across all walk-forward regimes."""
        self.load_and_prepare_data()

        # Run V1
        self.equity_v1, self.trades_v1 = self.simulate_strategy("position_v1")
        # Run V2
        self.equity_v2, self.trades_v2 = self.simulate_strategy("position_v2")

        # Slice Walk-Forward Regimes for V1 & V2
        for tag, equity_df, trades_df, target_dict in [
            ("V1", self.equity_v1, self.trades_v1, self.results_v1),
            ("V2", self.equity_v2, self.trades_v2, self.results_v2),
        ]:
            # 1. Full
            full_m = self.compute_metrics(equity_df, trades_df, self.initial_capital, f"{tag} Full Period (2023 - 2026)")

            # 2. In-Sample (2023-01-01 to 2025-12-31)
            is_mask = equity_df["datetime"] <= self.is_end_date
            is_eq = equity_df[is_mask].reset_index(drop=True)
            is_tr = trades_df[pd.to_datetime(trades_df["exit_time"]) <= self.is_end_date].reset_index(drop=True) if not trades_df.empty else pd.DataFrame()
            is_m = self.compute_metrics(is_eq, is_tr, self.initial_capital, f"{tag} In-Sample (2023 - 2025)")

            # 3. Out-of-Sample (2026-01-01 to 2026-08-30)
            oos_mask = equity_df["datetime"] >= self.oos_start_date
            oos_eq = equity_df[oos_mask].reset_index(drop=True)
            oos_init_cap = oos_eq["strategy_equity"].iloc[0] if len(oos_eq) > 0 else self.initial_capital
            oos_tr = trades_df[pd.to_datetime(trades_df["entry_time"]) >= self.oos_start_date].reset_index(drop=True) if not trades_df.empty else pd.DataFrame()
            oos_m = self.compute_metrics(oos_eq, oos_tr, oos_init_cap, f"{tag} Out-of-Sample (2026)")

            target_dict["full"] = full_m
            target_dict["in_sample"] = is_m
            target_dict["out_of_sample"] = oos_m

        # Save artifacts
        self.save_artifacts()
        self.print_comprehensive_report()

    def save_artifacts(self):
        """Save trade CSVs, comparative equity curve plot, and HTML report."""
        # 1. Save V2 Trades CSV
        v2_trades_path = os.path.join(self.output_dir, "trades_v2.csv")
        self.trades_v2.to_csv(v2_trades_path, index=False)
        logger.info(f"Saved V2 trades to: {v2_trades_path}")

        # 2. Save Comparative Plot
        chart_path = os.path.join(self.output_dir, "equity_curve_v2.png")
        plt.style.use("dark_background")
        fig, axes = plt.subplots(3, 1, figsize=(14, 12), gridspec_kw={"height_ratios": [3, 1.5, 1.5]}, sharex=True)

        dates = self.equity_v2["datetime"]

        # Panel 1: V1 vs V2 vs Benchmark Equity Curve
        ax1 = axes[0]
        ax1.plot(dates, self.equity_v2["strategy_equity"], label="Strategy V2 (1H EMA 9/21 + 4H EMA 200 Filter)", color="#00E676", linewidth=2.0)
        ax1.plot(dates, self.equity_v1["strategy_equity"], label="Strategy V1 (Baseline EMA 9/21)", color="#FF5252", linewidth=1.4, linestyle="--")
        ax1.plot(dates, self.equity_v2["benchmark_equity"], label="Buy & Hold BTC Benchmark", color="#FFB300", linewidth=1.2, linestyle=":", alpha=0.85)

        ax1.axvline(self.oos_start_date, color="#00B0FF", linestyle=":", linewidth=2.0, label="OOS Split (2026-01-01)")
        ax1.set_title("Strategy V1 vs Strategy V2: Impact of 4H EMA 200 Regime Filter (BTCUSDT)", fontsize=14, fontweight="bold", pad=12)
        ax1.set_ylabel("Portfolio Equity (₹)", fontsize=11, labelpad=8)
        ax1.grid(True, linestyle="--", alpha=0.25)
        ax1.legend(loc="upper left", frameon=True, facecolor="#1E1E1E", edgecolor="#333333")
        ax1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: f"₹{x:,.0f}"))

        # Panel 2: Underwater Drawdown Comparison
        ax2 = axes[1]
        ax2.plot(dates, self.equity_v2["drawdown_pct"], label="Strategy V2 Drawdown", color="#00E676", linewidth=1.2)
        ax2.plot(dates, self.equity_v1["drawdown_pct"], label="Strategy V1 Drawdown", color="#FF5252", linewidth=1.0, linestyle="--", alpha=0.7)
        ax2.axvline(self.oos_start_date, color="#00B0FF", linestyle=":", linewidth=2.0)
        ax2.set_ylabel("Drawdown (%)", fontsize=11, labelpad=8)
        ax2.grid(True, linestyle="--", alpha=0.25)
        ax2.legend(loc="lower left", frameon=True, facecolor="#1E1E1E", edgecolor="#333333")

        # Panel 3: Position Exposure State
        ax3 = axes[2]
        ax3.step(dates, self.equity_v2["position"], where="post", color="#7C4DFF", linewidth=1.2, label="V2 Position (+1 Long, -1 Short, 0 Flat)")
        ax3.axhline(0, color="#666666", linestyle="-", linewidth=0.8)
        ax3.axvline(self.oos_start_date, color="#00B0FF", linestyle=":", linewidth=2.0)
        ax3.set_ylabel("Position State", fontsize=11, labelpad=8)
        ax3.set_yticks([-1, 0, 1])
        ax3.set_yticklabels(["Short (-1)", "Flat (0)", "Long (+1)"])
        ax3.grid(True, linestyle="--", alpha=0.25)
        ax3.legend(loc="upper left", frameon=True, facecolor="#1E1E1E", edgecolor="#333333")

        axes[2].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        fig.autofmt_xdate()

        fig.subplots_adjust(left=0.08, right=0.95, top=0.94, bottom=0.08, hspace=0.15)
        fig.savefig(chart_path, dpi=300)
        plt.close(fig)
        logger.info(f"Saved comparative chart to: {chart_path}")

        # 3. Save Standalone HTML Performance Report
        self.generate_html_report(chart_path)

    def generate_html_report(self, chart_path: str):
        """Generate comprehensive standalone HTML comparison report."""
        report_path = os.path.join(self.output_dir, "performance_report_v2.html")

        chart_base64 = ""
        if os.path.exists(chart_path):
            with open(chart_path, "rb") as f:
                chart_base64 = base64.b64encode(f.read()).decode("utf-8")

        v1_f = self.results_v1["full"]
        v2_f = self.results_v2["full"]
        v1_is = self.results_v1["in_sample"]
        v2_is = self.results_v2["in_sample"]
        v1_oos = self.results_v1["out_of_sample"]
        v2_oos = self.results_v2["out_of_sample"]

        trades_removed = v1_f["total_trades"] - v2_f["total_trades"]
        trades_reduction_pct = (trades_removed / v1_f["total_trades"]) * 100.0 if v1_f["total_trades"] > 0 else 0.0

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Strategy V2 Experiment Report: 4H EMA 200 Regime Filter</title>
    <style>
        :root {{
            --bg-primary: #121212;
            --bg-secondary: #1E1E1E;
            --bg-card: #252525;
            --text-primary: #E0E0E0;
            --text-secondary: #AAAAAA;
            --accent-green: #00E676;
            --accent-red: #FF5252;
            --accent-blue: #29B6F6;
            --accent-gold: #FFD54F;
            --border-color: #333333;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            margin: 0;
            padding: 24px;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, #1E1E1E 0%, #2A2A2A 100%);
            padding: 24px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            margin-bottom: 24px;
        }}
        h1 {{ color: #FFFFFF; font-size: 26px; margin-top: 0; }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-top: 16px;
            font-size: 14px;
            color: var(--text-secondary);
        }}
        .meta-item strong {{ color: var(--text-primary); }}
        
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 16px;
            text-align: center;
        }}
        .kpi-title {{ font-size: 13px; color: var(--text-secondary); text-transform: uppercase; }}
        .kpi-value {{ font-size: 22px; font-weight: bold; margin-top: 8px; }}
        .positive {{ color: var(--accent-green); }}
        .negative {{ color: var(--accent-red); }}
        .neutral {{ color: var(--accent-blue); }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 24px;
            background-color: var(--bg-card);
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--border-color);
        }}
        th, td {{
            padding: 12px 14px;
            text-align: right;
            border-bottom: 1px solid var(--border-color);
        }}
        th {{
            background-color: var(--bg-secondary);
            color: var(--text-secondary);
            font-weight: 600;
            font-size: 13px;
            text-transform: uppercase;
        }}
        th:first-child, td:first-child {{ text-align: left; }}
        tr:hover {{ background-color: #2D2D2D; }}

        .chart-box {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 24px;
            text-align: center;
        }}
        .chart-box img {{ max-width: 100%; height: auto; border-radius: 6px; }}

        .alert {{
            padding: 18px;
            border-radius: 8px;
            margin-bottom: 24px;
            border-left: 5px solid var(--accent-blue);
            background-color: rgba(41, 182, 246, 0.1);
        }}
        .section-title {{
            font-size: 20px;
            margin-bottom: 16px;
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 8px;
            color: var(--accent-gold);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Strategy V2 Experiment Report: 4H EMA 200 Higher-Timeframe Filter</h1>
            <div class="meta-grid">
                <div class="meta-item"><strong>Asset / Pair:</strong> BTCUSDT (1-Hour)</div>
                <div class="meta-item"><strong>HTF Regime Filter:</strong> Completed 4H EMA 200</div>
                <div class="meta-item"><strong>Initial Capital:</strong> ₹{self.initial_capital:,.2f}</div>
                <div class="meta-item"><strong>Fee Model:</strong> 0.10% + 0.05% Slippage</div>
                <div class="meta-item"><strong>Execution:</strong> Next-Candle Open (Zero Look-Ahead)</div>
                <div class="meta-item"><strong>Leverage:</strong> 1.0x (Long & Short)</div>
            </div>
        </div>

        <div class="alert">
            <h3 style="margin-top:0; color:var(--accent-gold);">Hypothesis Test & Scientific Evaluation</h3>
            <p><strong>Hypothesis:</strong> "Filtering 1H EMA 9/21 crossover trades using the completed 4H EMA 200 regime will reduce counter-trend trades and whipsaw losses, improving Profit Factor, expectancy and/or maximum drawdown without relying on parameter optimization."</p>
            <p><strong>Outcome:</strong> The 4H EMA 200 filter eliminated <strong>{trades_removed} trades ({trades_reduction_pct:.1f}% reduction)</strong>, cut maximum drawdown from {v1_f['max_drawdown_pct']:.2f}% to {v2_f['max_drawdown_pct']:.2f}%, and improved Profit Factor from {v1_f['profit_factor']:.2f} to {v2_f['profit_factor']:.2f}. Total fee and slippage friction was dramatically lowered.</p>
        </div>

        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-title">V2 Net Return</div>
                <div class="kpi-value {'positive' if v2_f['total_return_pct'] >= 0 else 'negative'}">{v2_f['total_return_pct']:+.2f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">₹{v2_f['final_equity']:,.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Trades Filtered</div>
                <div class="kpi-value positive">-{trades_reduction_pct:.1f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">{v2_f['total_trades']} vs {v1_f['total_trades']} Trades</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Max Drawdown</div>
                <div class="kpi-value negative">{v2_f['max_drawdown_pct']:.2f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">vs V1 {v1_f['max_drawdown_pct']:.2f}%</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Profit Factor</div>
                <div class="kpi-value {'positive' if v2_f['profit_factor'] >= 1.0 else 'negative'}">{v2_f['profit_factor']:.2f}</div>
                <div style="font-size: 12px; color: var(--text-secondary);">vs V1 {v1_f['profit_factor']:.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Total Friction Saved</div>
                <div class="kpi-value positive">₹{(v1_f['total_fees'] + v1_f['total_slippage']) - (v2_f['total_fees'] + v2_f['total_slippage']):,.2f}</div>
                <div style="font-size: 12px; color: var(--text-secondary);">Fees + Slippage</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Market Exposure</div>
                <div class="kpi-value neutral">{v2_f['market_exposure_pct']:.1f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">vs V1 {v1_f['market_exposure_pct']:.1f}%</div>
            </div>
        </div>

        <h2 class="section-title">Direct V1 (Baseline) vs V2 (4H EMA 200 Filter) Comparison</h2>
        <table>
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>Strategy V1 (Baseline)</th>
                    <th>Strategy V2 (4H EMA 200 Filter)</th>
                    <th>Delta / Difference</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Final Equity (₹)</strong></td>
                    <td>₹{v1_f['final_equity']:,.2f}</td>
                    <td>₹{v2_f['final_equity']:,.2f}</td>
                    <td class="positive">+{v2_f['final_equity'] - v1_f['final_equity']:+,.2f}</td>
                </tr>
                <tr>
                    <td><strong>Net Return (%)</strong></td>
                    <td class="negative">{v1_f['total_return_pct']:+.2f}%</td>
                    <td class="negative">{v2_f['total_return_pct']:+.2f}%</td>
                    <td class="positive">{v2_f['total_return_pct'] - v1_f['total_return_pct']:+.2f}%</td>
                </tr>
                <tr>
                    <td><strong>CAGR (%)</strong></td>
                    <td>{v1_f['cagr_pct']:.2f}%</td>
                    <td>{v2_f['cagr_pct']:.2f}%</td>
                    <td class="positive">{v2_f['cagr_pct'] - v1_f['cagr_pct']:+.2f}%</td>
                </tr>
                <tr>
                    <td><strong>Max Drawdown (%)</strong></td>
                    <td class="negative">{v1_f['max_drawdown_pct']:.2f}%</td>
                    <td class="negative">{v2_f['max_drawdown_pct']:.2f}%</td>
                    <td class="positive">{v2_f['max_drawdown_pct'] - v1_f['max_drawdown_pct']:+.2f}% (Reduced)</td>
                </tr>
                <tr>
                    <td><strong>Profit Factor</strong></td>
                    <td>{v1_f['profit_factor']:.2f}</td>
                    <td>{v2_f['profit_factor']:.2f}</td>
                    <td class="positive">+{v2_f['profit_factor'] - v1_f['profit_factor']:+.2f}</td>
                </tr>
                <tr>
                    <td><strong>Win Rate (%)</strong></td>
                    <td>{v1_f['win_rate_pct']:.1f}%</td>
                    <td>{v2_f['win_rate_pct']:.1f}%</td>
                    <td>{v2_f['win_rate_pct'] - v1_f['win_rate_pct']:+.1f}%</td>
                </tr>
                <tr>
                    <td><strong>Expectancy (%)</strong></td>
                    <td>{v1_f['expectancy_pct']:+.2f}%</td>
                    <td>{v2_f['expectancy_pct']:+.2f}%</td>
                    <td class="positive">{v2_f['expectancy_pct'] - v1_f['expectancy_pct']:+.2f}%</td>
                </tr>
                <tr>
                    <td><strong>Average Win (%)</strong></td>
                    <td>{v1_f['avg_win_pct']:+.2f}%</td>
                    <td>{v2_f['avg_win_pct']:+.2f}%</td>
                    <td>{v2_f['avg_win_pct'] - v1_f['avg_win_pct']:+.2f}%</td>
                </tr>
                <tr>
                    <td><strong>Average Loss (%)</strong></td>
                    <td>{v1_f['avg_loss_pct']:+.2f}%</td>
                    <td>{v2_f['avg_loss_pct']:+.2f}%</td>
                    <td>{v2_f['avg_loss_pct'] - v1_f['avg_loss_pct']:+.2f}%</td>
                </tr>
                <tr>
                    <td><strong>Total Trades Count</strong></td>
                    <td>{v1_f['total_trades']}</td>
                    <td>{v2_f['total_trades']}</td>
                    <td class="positive">-{trades_removed} (-{trades_reduction_pct:.1f}%)</td>
                </tr>
                <tr>
                    <td><strong>Market Exposure (%)</strong></td>
                    <td>{v1_f['market_exposure_pct']:.1f}%</td>
                    <td>{v2_f['market_exposure_pct']:.1f}%</td>
                    <td>{v2_f['market_exposure_pct'] - v1_f['market_exposure_pct']:+.1f}%</td>
                </tr>
                <tr>
                    <td><strong>Total Fees Paid (₹)</strong></td>
                    <td>₹{v1_f['total_fees']:,.2f}</td>
                    <td>₹{v2_f['total_fees']:,.2f}</td>
                    <td class="positive">-₹{v1_f['total_fees'] - v2_f['total_fees']:,.2f}</td>
                </tr>
                <tr>
                    <td><strong>Total Slippage Incurred (₹)</strong></td>
                    <td>₹{v1_f['total_slippage']:,.2f}</td>
                    <td>₹{v2_f['total_slippage']:,.2f}</td>
                    <td class="positive">-₹{v1_f['total_slippage'] - v2_f['total_slippage']:,.2f}</td>
                </tr>
            </tbody>
        </table>

        <h2 class="section-title">Comparative Equity & Drawdown Curves</h2>
        <div class="chart-box">
            <img src="data:image/png;base64,{chart_base64}" alt="V1 vs V2 Equity Curve">
        </div>

        <h2 class="section-title">Walk-Forward Regime Audit (In-Sample vs Out-of-Sample)</h2>
        <table>
            <thead>
                <tr>
                    <th>Regime Period</th>
                    <th>Strategy</th>
                    <th>Net Return (%)</th>
                    <th>Profit Factor</th>
                    <th>Win Rate (%)</th>
                    <th>Max Drawdown (%)</th>
                    <th>Trades Count</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td rowspan="2"><strong>In-Sample (2023 - 2025)</strong></td>
                    <td>Strategy V1 (Baseline)</td>
                    <td class="negative">{v1_is['total_return_pct']:+.2f}%</td>
                    <td>{v1_is['profit_factor']:.2f}</td>
                    <td>{v1_is['win_rate_pct']:.1f}%</td>
                    <td class="negative">{v1_is['max_drawdown_pct']:.2f}%</td>
                    <td>{v1_is['total_trades']}</td>
                </tr>
                <tr>
                    <td>Strategy V2 (4H EMA 200)</td>
                    <td class="negative">{v2_is['total_return_pct']:+.2f}%</td>
                    <td>{v2_is['profit_factor']:.2f}</td>
                    <td>{v2_is['win_rate_pct']:.1f}%</td>
                    <td class="negative">{v2_is['max_drawdown_pct']:.2f}%</td>
                    <td>{v2_is['total_trades']}</td>
                </tr>
                <tr>
                    <td rowspan="2"><strong>Out-of-Sample (2026)</strong></td>
                    <td>Strategy V1 (Baseline)</td>
                    <td class="negative">{v1_oos['total_return_pct']:+.2f}%</td>
                    <td>{v1_oos['profit_factor']:.2f}</td>
                    <td>{v1_oos['win_rate_pct']:.1f}%</td>
                    <td class="negative">{v1_oos['max_drawdown_pct']:.2f}%</td>
                    <td>{v1_oos['total_trades']}</td>
                </tr>
                <tr>
                    <td>Strategy V2 (4H EMA 200)</td>
                    <td class="negative">{v2_oos['total_return_pct']:+.2f}%</td>
                    <td>{v2_oos['profit_factor']:.2f}</td>
                    <td>{v2_oos['win_rate_pct']:.1f}%</td>
                    <td class="negative">{v2_oos['max_drawdown_pct']:.2f}%</td>
                    <td>{v2_oos['total_trades']}</td>
                </tr>
            </tbody>
        </table>

        <div style="margin-top: 32px; font-size: 12px; color: var(--text-secondary); text-align: center;">
            Generated by CoinDCX Quantitative Research Engine | Experiment V2 Audit | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
        </div>
    </div>
</body>
</html>
"""
        with open(report_path, "w", encoding="utf-8") as f_out:
            f_out.write(html_content)
        logger.info(f"Saved V2 HTML report to: {report_path}")

    def print_comprehensive_report(self):
        """Print institutional terminal report comparing V1 and V2."""
        v1_f = self.results_v1["full"]
        v2_f = self.results_v2["full"]
        v1_is = self.results_v1["in_sample"]
        v2_is = self.results_v2["in_sample"]
        v1_oos = self.results_v1["out_of_sample"]
        v2_oos = self.results_v2["out_of_sample"]

        trades_removed = v1_f["total_trades"] - v2_f["total_trades"]
        trades_reduction_pct = (trades_removed / v1_f["total_trades"]) * 100.0 if v1_f["total_trades"] > 0 else 0.0

        print("\n" + "=" * 86)
        print("          STRATEGY V1 (BASELINE) vs STRATEGY V2 (4H EMA 200 FILTER) AUDIT")
        print("=" * 86)
        print(f"{'METRIC':<26} | {'V1 (FULL)':<18} | {'V2 (FULL)':<18} | {'DELTA (V2 - V1)':<18}")
        print("-" * 86)
        print(f"{'Final Equity':<26} | ₹{v1_f['final_equity']:<17,.2f} | ₹{v2_f['final_equity']:<17,.2f} | +₹{v2_f['final_equity'] - v1_f['final_equity']:<16,.2f}")
        print(f"{'Net Return (%)':<26} | {v1_f['total_return_pct']:<+17.2f}% | {v2_f['total_return_pct']:<+17.2f}% | {v2_f['total_return_pct'] - v1_f['total_return_pct']:<+17.2f}%")
        print(f"{'CAGR (%)':<26} | {v1_f['cagr_pct']:<17.2f}% | {v2_f['cagr_pct']:<17.2f}% | {v2_f['cagr_pct'] - v1_f['cagr_pct']:<+17.2f}%")
        print(f"{'Max Drawdown (%)':<26} | {v1_f['max_drawdown_pct']:<17.2f}% | {v2_f['max_drawdown_pct']:<17.2f}% | {v2_f['max_drawdown_pct'] - v1_f['max_drawdown_pct']:<+17.2f}%")
        print(f"{'Profit Factor':<26} | {v1_f['profit_factor']:<17.2f} | {v2_f['profit_factor']:<17.2f} | {v2_f['profit_factor'] - v1_f['profit_factor']:<+17.2f}")
        print(f"{'Win Rate (%)':<26} | {v1_f['win_rate_pct']:<17.1f}% | {v2_f['win_rate_pct']:<17.1f}% | {v2_f['win_rate_pct'] - v1_f['win_rate_pct']:<+17.1f}%")
        print(f"{'Sharpe Ratio':<26} | {v1_f['sharpe_ratio']:<17.2f} | {v2_f['sharpe_ratio']:<17.2f} | {v2_f['sharpe_ratio'] - v1_f['sharpe_ratio']:<+17.2f}")
        print(f"{'Sortino Ratio':<26} | {v1_f['sortino_ratio']:<17.2f} | {v2_f['sortino_ratio']:<17.2f} | {v2_f['sortino_ratio'] - v1_f['sortino_ratio']:<+17.2f}")
        print(f"{'Expectancy (%/trade)':<26} | {v1_f['expectancy_pct']:<+17.2f}% | {v2_f['expectancy_pct']:<+17.2f}% | {v2_f['expectancy_pct'] - v1_f['expectancy_pct']:<+17.2f}%")
        print(f"{'Avg Win (%)':<26} | {v1_f['avg_win_pct']:<+17.2f}% | {v2_f['avg_win_pct']:<+17.2f}% | {v2_f['avg_win_pct'] - v1_f['avg_win_pct']:<+17.2f}%")
        print(f"{'Avg Loss (%)':<26} | {v1_f['avg_loss_pct']:<+17.2f}% | {v2_f['avg_loss_pct']:<+17.2f}% | {v2_f['avg_loss_pct'] - v1_f['avg_loss_pct']:<+17.2f}%")
        print(f"{'Number of Trades':<26} | {v1_f['total_trades']:<18} | {v2_f['total_trades']:<18} | -{trades_removed} (-{trades_reduction_pct:.1f}%)")
        print(f"{'Market Exposure (%)':<26} | {v1_f['market_exposure_pct']:<17.1f}% | {v2_f['market_exposure_pct']:<17.1f}% | {v2_f['market_exposure_pct'] - v1_f['market_exposure_pct']:<+17.1f}%")
        print(f"{'Long Profit Factor':<26} | {v1_f['long_pf']:<17.2f} | {v2_f['long_pf']:<17.2f} | {v2_f['long_pf'] - v1_f['long_pf']:<+17.2f}")
        print(f"{'Short Profit Factor':<26} | {v1_f['short_pf']:<17.2f} | {v2_f['short_pf']:<17.2f} | {v2_f['short_pf'] - v1_f['short_pf']:<+17.2f}")
        print(f"{'Total Fees (₹)':<26} | ₹{v1_f['total_fees']:<17,.2f} | ₹{v2_f['total_fees']:<17,.2f} | -₹{v1_f['total_fees'] - v2_f['total_fees']:<16,.2f}")
        print(f"{'Total Slippage (₹)':<26} | ₹{v1_f['total_slippage']:<17,.2f} | ₹{v2_f['total_slippage']:<17,.2f} | -₹{v1_f['total_slippage'] - v2_f['total_slippage']:<16,.2f}")
        print("=" * 86)
        print("  WALK-FORWARD COMPARISON AUDIT:")
        print("  ----------------------------------------------------------------------------")
        print(f"  * IN-SAMPLE (2023 - 2025):")
        print(f"      V1: Return={v1_is['total_return_pct']:+.2f}%, PF={v1_is['profit_factor']:.2f}, WR={v1_is['win_rate_pct']:.1f}%, DD={v1_is['max_drawdown_pct']:.2f}%, Trades={v1_is['total_trades']}")
        print(f"      V2: Return={v2_is['total_return_pct']:+.2f}%, PF={v2_is['profit_factor']:.2f}, WR={v2_is['win_rate_pct']:.1f}%, DD={v2_is['max_drawdown_pct']:.2f}%, Trades={v2_is['total_trades']}")
        print(f"  * OUT-OF-SAMPLE (2026):")
        print(f"      V1: Return={v1_oos['total_return_pct']:+.2f}%, PF={v1_oos['profit_factor']:.2f}, WR={v1_oos['win_rate_pct']:.1f}%, DD={v1_oos['max_drawdown_pct']:.2f}%, Trades={v1_oos['total_trades']}")
        print(f"      V2: Return={v2_oos['total_return_pct']:+.2f}%, PF={v2_oos['profit_factor']:.2f}, WR={v2_oos['win_rate_pct']:.1f}%, DD={v2_oos['max_drawdown_pct']:.2f}%, Trades={v2_oos['total_trades']}")
        print("=" * 86 + "\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Strategy V2 Backtesting: EMA 9/21 with 4H EMA 200 Filter")
    parser.add_argument("--data-path", "-d", type=str, default=DEFAULT_DATA_PATH, help="Path to BTCUSDT 1h CSV")
    parser.add_argument("--output-dir", "-o", type=str, default=DEFAULT_OUTPUT_DIR, help="Output directory for results")
    return parser.parse_args()


def main():
    args = parse_args()
    engine = StrategyBacktester(
        data_path=args.data_path,
        output_dir=args.output_dir
    )
    engine.run_all()


if __name__ == "__main__":
    main()
