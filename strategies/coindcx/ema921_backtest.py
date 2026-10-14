#!/usr/bin/env python3
"""
Professional Vectorized / Event-Driven Backtesting Engine: Strategy V1
=====================================================================
Strategy: EMA 9/21 Crossover on BTCUSDT (1-Hour Timeframe)
Data Source: CoinDCX Public OHLCV CSV

Key Characteristics:
- Pure candle-close signal generation (executed on next candle OPEN price).
- ZERO look-ahead bias / zero future peeking.
- Realistic transaction fee (0.1%) and slippage (0.05%) modeling.
- Full long/short support without leverage (1.0x).
- Walk-Forward Split:
    * In-Sample (IS) : 2023-01-01 to 2025-12-31
    * Out-of-Sample (OOS): 2026-01-01 to 2026-08-30
    * Full Period: 2023-01-01 to 2026-08-30
- Generates:
    * trades.csv
    * performance_report.html
    * equity_curve.png
"""

import os
import sys
import math
import base64
import argparse
import logging
from io import BytesIO
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union

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
logger = logging.getLogger("EMA921Backtester")

# Default Paths
DEFAULT_DATA_PATH = os.path.expanduser("~/backtesting/coindcx_data/BTCUSDT_1h_2023-01-01_2026-08-30.csv")
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/backtesting/coindcx_backtest")


class EMA921Backtester:
    """Professional Backtesting Engine for EMA 9/21 Crossover."""

    def __init__(
        self,
        data_path: str = DEFAULT_DATA_PATH,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        fast_ema: int = 9,
        slow_ema: int = 21,
        initial_capital: float = 100000.0,
        fee_rate: float = 0.001,      # 0.1% per trade
        slippage: float = 0.0005,     # 0.05% slippage
        position_size_pct: float = 1.0, # 100% of equity
        allow_short: bool = True,
        is_end_date: str = "2025-12-31 23:59:59",
        oos_start_date: str = "2026-01-01 00:00:00"
    ):
        self.data_path = os.path.expanduser(data_path)
        self.output_dir = os.path.expanduser(output_dir)
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.position_size_pct = position_size_pct
        self.allow_short = allow_short
        self.is_end_date = pd.to_datetime(is_end_date)
        self.oos_start_date = pd.to_datetime(oos_start_date)

        os.makedirs(self.output_dir, exist_ok=True)

        self.df: Optional[pd.DataFrame] = None
        self.equity_df: Optional[pd.DataFrame] = None
        self.trades_df: Optional[pd.DataFrame] = None
        self.results: Dict[str, Any] = {}

    def load_and_prepare_data(self) -> pd.DataFrame:
        """Load CSV, parse timestamps, and validate data integrity."""
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"Historical data file not found at: {self.data_path}")

        logger.info(f"Loading data from: {self.data_path}")
        df = pd.read_csv(self.data_path)

        if "timestamp" in df.columns:
            df["datetime"] = pd.to_datetime(df["timestamp"])
        elif "epoch_ms" in df.columns:
            df["datetime"] = pd.to_datetime(df["epoch_ms"], unit="ms")
        else:
            raise ValueError("CSV must contain 'timestamp' or 'epoch_ms' column.")

        df = df.sort_values("datetime").reset_index(drop=True)

        # Standardize numeric columns
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        logger.info(f"Loaded {len(df):,} candles from {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")
        self.df = df
        return df

    def compute_indicators_and_signals(self):
        """
        Compute EMA 9 and EMA 21 and generate crossover signals with zero look-ahead bias.
        Signals are calculated at bar Close.
        """
        df = self.df
        close = df["close"]

        # Calculate Exponential Moving Averages
        df["ema_fast"] = close.ewm(span=self.fast_ema, adjust=False).mean()
        df["ema_slow"] = close.ewm(span=self.slow_ema, adjust=False).mean()

        # Signal Calculation:
        # Long Entry / Short Exit: Fast crosses ABOVE Slow
        # Short Entry / Long Exit: Fast crosses BELOW Slow
        fast_above = df["ema_fast"] > df["ema_slow"]
        fast_above_prev = df["ema_fast"].shift(1) > df["ema_slow"].shift(1)

        # Raw cross triggers (True at bar close where crossover occurred)
        df["bull_cross"] = (fast_above) & (~fast_above_prev)
        df["bear_cross"] = (~fast_above) & (fast_above_prev)

        # Determine target state at close: +1 for Long, -1 for Short (if allowed), 0 for Flat
        target_state = np.zeros(len(df), dtype=int)
        current_state = 0

        # Burn-in period: Wait until enough candles for stable EMA
        burn_in = self.slow_ema * 2

        for i in range(burn_in, len(df)):
            if df.loc[i, "bull_cross"]:
                current_state = 1
            elif df.loc[i, "bear_cross"]:
                current_state = -1 if self.allow_short else 0
            target_state[i] = current_state

        df["target_state"] = target_state

        # CRITICAL LOOK-AHEAD PREVENTION:
        # The trade signal generated at Bar i Close is executed at Bar i+1 OPEN price!
        # Therefore, the position held during Bar i+1 is target_state[i].
        df["position"] = df["target_state"].shift(1).fillna(0).astype(int)

        # Action trigger at Bar i: changes in position entering at Bar i OPEN
        df["action"] = df["position"] - df["position"].shift(1).fillna(0).astype(int)

        self.df = df
        logger.info(f"Indicator calculation complete: Fast EMA={self.fast_ema}, Slow EMA={self.slow_ema}")

    def simulate_execution(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Execute bar-by-bar chronological simulation with realistic fees and slippage.
        """
        df = self.df
        n = len(df)

        capital = self.initial_capital
        cash = capital
        position_units = 0.0
        position_side = 0  # 1 = Long, -1 = Short, 0 = Flat
        entry_price = 0.0
        entry_time = None
        entry_idx = 0
        entry_fee = 0.0

        equity_curve = np.zeros(n)
        cash_curve = np.zeros(n)
        position_curve = np.zeros(n)
        benchmark_equity = np.zeros(n)

        trades: List[Dict[str, Any]] = []
        trade_id = 0

        # Benchmark: 100% Buy & Hold from first simulated bar
        first_open = df.loc[0, "open"]
        benchmark_units = (capital * (1.0 - self.fee_rate)) / (first_open * (1.0 + self.slippage))

        for i in range(n):
            dt = df.loc[i, "datetime"]
            open_p = df.loc[i, "open"]
            high_p = df.loc[i, "high"]
            low_p = df.loc[i, "low"]
            close_p = df.loc[i, "close"]
            desired_pos = df.loc[i, "position"]

            # Check if position needs to change at bar Open
            if desired_pos != position_side:
                # 1. Close existing position if any
                if position_side != 0:
                    if position_side == 1:
                        # Exit Long: sell at Open * (1 - slippage)
                        exit_price = open_p * (1.0 - self.slippage)
                        exit_val = position_units * exit_price
                        exit_fee = exit_val * self.fee_rate
                        gross_pnl = (exit_price - entry_price) * position_units
                        net_pnl = gross_pnl - entry_fee - exit_fee
                        cash += (exit_val - exit_fee)
                    else:
                        # Exit Short: buy back at Open * (1 + slippage)
                        exit_price = open_p * (1.0 + self.slippage)
                        exit_val = position_units * exit_price
                        exit_fee = exit_val * self.fee_rate
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
                        "entry_price": entry_price,
                        "exit_idx": i,
                        "exit_time": dt,
                        "exit_price": exit_price,
                        "units": position_units,
                        "position_value": entry_price * position_units,
                        "gross_pnl": gross_pnl,
                        "total_fees": entry_fee + exit_fee,
                        "net_pnl": net_pnl,
                        "return_pct": return_pct,
                        "duration_bars": duration_bars,
                        "duration_hours": duration_hours,
                        "exit_reason": "REVERSAL_SIGNAL",
                        "cumulative_equity": cash
                    })

                    position_side = 0
                    position_units = 0.0

                # 2. Open new position if desired_pos != 0
                if desired_pos != 0:
                    position_side = desired_pos
                    entry_idx = i
                    entry_time = dt
                    trade_capital = cash * self.position_size_pct

                    if position_side == 1:
                        # Enter Long: buy at Open * (1 + slippage)
                        entry_price = open_p * (1.0 + self.slippage)
                        # Units we can buy with trade_capital including fee
                        position_units = trade_capital / (entry_price * (1.0 + self.fee_rate))
                        entry_val = position_units * entry_price
                        entry_fee = entry_val * self.fee_rate
                        cash -= (entry_val + entry_fee)
                    else:
                        # Enter Short: sell short at Open * (1 - slippage)
                        entry_price = open_p * (1.0 - self.slippage)
                        position_units = trade_capital / (entry_price * (1.0 + self.fee_rate))
                        entry_val = position_units * entry_price
                        entry_fee = entry_val * self.fee_rate
                        cash -= (entry_val + entry_fee)

            # Mark to Market Equity at bar Close
            if position_side == 1:
                current_value = position_units * close_p
                current_equity = cash + current_value
            elif position_side == -1:
                # Short MTM: cash + initial_margin + unrealized_pnl
                unrealized_pnl = (entry_price - close_p) * position_units
                current_equity = cash + (position_units * entry_price) + unrealized_pnl
            else:
                current_equity = cash

            equity_curve[i] = current_equity
            cash_curve[i] = cash
            position_curve[i] = position_side
            benchmark_equity[i] = benchmark_units * close_p

        # Close open position at end of backtest if any
        if position_side != 0:
            last_idx = n - 1
            last_close = df.loc[last_idx, "close"]
            last_dt = df.loc[last_idx, "datetime"]
            if position_side == 1:
                exit_price = last_close * (1.0 - self.slippage)
                exit_val = position_units * exit_price
                exit_fee = exit_val * self.fee_rate
                gross_pnl = (exit_price - entry_price) * position_units
                net_pnl = gross_pnl - entry_fee - exit_fee
                cash += (exit_val - exit_fee)
            else:
                exit_price = last_close * (1.0 + self.slippage)
                exit_val = position_units * exit_price
                exit_fee = exit_val * self.fee_rate
                gross_pnl = (entry_price - exit_price) * position_units
                net_pnl = gross_pnl - entry_fee - exit_fee
                cash += (position_units * entry_price) + gross_pnl - exit_fee

            trade_id += 1
            trades.append({
                "trade_id": trade_id,
                "side": "LONG" if position_side == 1 else "SHORT",
                "entry_idx": entry_idx,
                "entry_time": entry_time,
                "entry_price": entry_price,
                "exit_idx": last_idx,
                "exit_time": last_dt,
                "exit_price": exit_price,
                "units": position_units,
                "position_value": entry_price * position_units,
                "gross_pnl": gross_pnl,
                "total_fees": entry_fee + exit_fee,
                "net_pnl": net_pnl,
                "return_pct": (net_pnl / (entry_price * position_units)) * 100.0,
                "duration_bars": last_idx - entry_idx,
                "duration_hours": (last_idx - entry_idx) * 1.0,
                "exit_reason": "BACKTEST_END",
                "cumulative_equity": cash
            })
            equity_curve[-1] = cash

        # Create Equity DataFrame
        equity_df = pd.DataFrame({
            "datetime": df["datetime"],
            "close": df["close"],
            "strategy_equity": equity_curve,
            "cash": cash_curve,
            "position": position_curve,
            "benchmark_equity": benchmark_equity
        })

        # Drawdown calculation
        equity_df["peak"] = equity_df["strategy_equity"].cummax()
        equity_df["drawdown_pct"] = (equity_df["strategy_equity"] - equity_df["peak"]) / equity_df["peak"] * 100.0
        equity_df["benchmark_peak"] = equity_df["benchmark_equity"].cummax()
        equity_df["benchmark_drawdown_pct"] = (equity_df["benchmark_equity"] - equity_df["benchmark_peak"]) / equity_df["benchmark_peak"] * 100.0

        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

        self.equity_df = equity_df
        self.trades_df = trades_df
        logger.info(f"Simulation completed: {len(trades):,} trades executed. Final Equity: ₹{equity_curve[-1]:,.2f}")
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
        cagr = ((final_equity / init_cap) ** (1.0 / years) - 1.0) * 100.0 if (years > 0 and final_equity > 0) else 0.0

        # Benchmark Metrics
        bench_init = equity_df["benchmark_equity"].iloc[0]
        bench_final = equity_df["benchmark_equity"].iloc[-1]
        bench_return_pct = ((bench_final - bench_init) / bench_init) * 100.0
        bench_cagr = ((bench_final / bench_init) ** (1.0 / years) - 1.0) * 100.0 if (years > 0 and bench_init > 0 and bench_final > 0) else 0.0
        bench_max_dd = equity_df["benchmark_drawdown_pct"].min()

        # Strategy Drawdown
        max_dd_pct = equity_df["drawdown_pct"].min()

        # Max Drawdown Duration
        is_dd = equity_df["drawdown_pct"] < 0
        dd_runs = (~is_dd).cumsum()
        dd_durations = is_dd.groupby(dd_runs).sum()
        max_dd_duration_hours = dd_durations.max() if len(dd_durations) > 0 else 0
        max_dd_duration_days = max_dd_duration_hours / 24.0

        # Hourly returns for Sharpe & Sortino (24/7 crypto = 8760 hours per year)
        hourly_returns = equity_df["strategy_equity"].pct_change().dropna()
        risk_free_rate_hourly = 0.05 / 8760.0  # 5% annual risk-free rate

        excess_returns = hourly_returns - risk_free_rate_hourly
        mean_excess = excess_returns.mean()
        std_returns = hourly_returns.std()
        sharpe_ratio = (mean_excess / std_returns) * math.sqrt(8760) if std_returns > 0 else 0.0

        # Downside deviation for Sortino
        negative_returns = hourly_returns[hourly_returns < 0]
        downside_std = negative_returns.std()
        sortino_ratio = (mean_excess / downside_std) * math.sqrt(8760) if (downside_std > 0 and not np.isnan(downside_std)) else 0.0

        # Calmar Ratio
        calmar_ratio = abs(cagr / max_dd_pct) if max_dd_pct != 0 else 0.0

        # Trade Statistics
        if not trades_df.empty:
            total_trades = len(trades_df)
            winning_trades = trades_df[trades_df["net_pnl"] > 0]
            losing_trades = trades_df[trades_df["net_pnl"] < 0]
            scratch_trades = trades_df[trades_df["net_pnl"] == 0]

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

            # Expectancy: (Win% * AvgWin%) - (Loss% * AvgLoss%)
            expectancy_pct = (win_rate / 100.0 * avg_win_pct) + ((1.0 - win_rate / 100.0) * avg_loss_pct)

            avg_duration_hrs = trades_df["duration_hours"].mean()
            max_consecutive_wins = self._max_consecutive(trades_df["net_pnl"] > 0)
            max_consecutive_losses = self._max_consecutive(trades_df["net_pnl"] < 0)

            # Long vs Short breakdown
            long_trades = trades_df[trades_df["side"] == "LONG"]
            short_trades = trades_df[trades_df["side"] == "SHORT"]

            long_wins = long_trades[long_trades["net_pnl"] > 0]
            long_losses = long_trades[long_trades["net_pnl"] < 0]
            short_wins = short_trades[short_trades["net_pnl"] > 0]
            short_losses = short_trades[short_trades["net_pnl"] < 0]

            long_stats = {
                "trades": len(long_trades),
                "win_rate": (len(long_wins) / len(long_trades) * 100.0) if len(long_trades) > 0 else 0.0,
                "net_pnl": long_trades["net_pnl"].sum() if len(long_trades) > 0 else 0.0,
                "profit_factor": (long_wins["net_pnl"].sum() / abs(long_losses["net_pnl"].sum())) if (len(long_losses) > 0 and abs(long_losses["net_pnl"].sum()) > 0) else 0.0,
                "avg_trade_pct": long_trades["return_pct"].mean() if len(long_trades) > 0 else 0.0,
            }

            short_stats = {
                "trades": len(short_trades),
                "win_rate": (len(short_wins) / len(short_trades) * 100.0) if len(short_trades) > 0 else 0.0,
                "net_pnl": short_trades["net_pnl"].sum() if len(short_trades) > 0 else 0.0,
                "profit_factor": (short_wins["net_pnl"].sum() / abs(short_losses["net_pnl"].sum())) if (len(short_losses) > 0 and abs(short_losses["net_pnl"].sum()) > 0) else 0.0,
                "avg_trade_pct": short_trades["return_pct"].mean() if len(short_trades) > 0 else 0.0,
            }
        else:
            total_trades = win_count = loss_count = 0
            win_rate = profit_factor = avg_trade_pnl_pct = avg_win_pct = avg_loss_pct = win_loss_ratio = expectancy_pct = 0.0
            avg_duration_hrs = max_consecutive_wins = max_consecutive_losses = 0
            long_stats = {"trades": 0, "win_rate": 0, "net_pnl": 0, "profit_factor": 0, "avg_trade_pct": 0}
            short_stats = {"trades": 0, "win_rate": 0, "net_pnl": 0, "profit_factor": 0, "avg_trade_pct": 0}

        # Market Exposure (% of time with active position)
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
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "avg_trade_pnl_pct": round(avg_trade_pnl_pct, 2),
            "avg_win_pct": round(avg_win_pct, 2),
            "avg_loss_pct": round(avg_loss_pct, 2),
            "win_loss_ratio": round(win_loss_ratio, 2),
            "expectancy_pct": round(expectancy_pct, 2),
            "avg_duration_hours": round(avg_duration_hrs, 1),
            "max_consecutive_wins": max_consecutive_wins,
            "max_consecutive_losses": max_consecutive_losses,
            "market_exposure_pct": round(exposure_pct, 2),
            "long_stats": long_stats,
            "short_stats": short_stats,
        }

    @staticmethod
    def _max_consecutive(series: pd.Series) -> int:
        """Helper to find max streak of True values."""
        streak = max_streak = 0
        for val in series:
            if val:
                streak += 1
                if streak > max_streak:
                    max_streak = streak
            else:
                streak = 0
        return max_streak

    def compute_monthly_returns(self, equity_df: pd.DataFrame) -> pd.DataFrame:
        """Compute Month x Year returns matrix."""
        df = equity_df.copy()
        df["year"] = df["datetime"].dt.year
        df["month"] = df["datetime"].dt.month

        monthly_first = df.groupby(["year", "month"])["strategy_equity"].first()
        monthly_last = df.groupby(["year", "month"])["strategy_equity"].last()
        monthly_ret = ((monthly_last - monthly_first) / monthly_first) * 100.0

        monthly_matrix = monthly_ret.unstack(level="month")
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        monthly_matrix.columns = [month_names[m - 1] for m in monthly_matrix.columns]

        # Calculate annual total return
        annual_first = df.groupby("year")["strategy_equity"].first()
        annual_last = df.groupby("year")["strategy_equity"].last()
        annual_ret = ((annual_last - annual_first) / annual_first) * 100.0
        monthly_matrix["YTD / Total"] = annual_ret

        return monthly_matrix.round(2)

    def run_all_regimes(self):
        """Run full backtest and slice In-Sample and Out-of-Sample regimes."""
        self.load_and_prepare_data()
        self.compute_indicators_and_signals()
        self.simulate_execution()

        # 1. Full Period
        full_metrics = self.compute_metrics(
            self.equity_df,
            self.trades_df,
            self.initial_capital,
            period_name="Full Period (2023 - 2026)"
        )

        # 2. In-Sample Period (2023-01-01 to 2025-12-31)
        is_mask = self.equity_df["datetime"] <= self.is_end_date
        is_equity_df = self.equity_df[is_mask].reset_index(drop=True)
        if not self.trades_df.empty:
            is_trades_df = self.trades_df[pd.to_datetime(self.trades_df["exit_time"]) <= self.is_end_date].reset_index(drop=True)
        else:
            is_trades_df = pd.DataFrame()

        is_metrics = self.compute_metrics(
            is_equity_df,
            is_trades_df,
            self.initial_capital,
            period_name="In-Sample (2023 - 2025)"
        )

        # 3. Out-of-Sample Period (2026-01-01 to 2026-08-30)
        oos_mask = self.equity_df["datetime"] >= self.oos_start_date
        oos_equity_df = self.equity_df[oos_mask].reset_index(drop=True)
        # Scale OOS initial capital to equity at start of OOS for standalone metrics
        oos_init_cap = oos_equity_df["strategy_equity"].iloc[0] if len(oos_equity_df) > 0 else self.initial_capital

        if not self.trades_df.empty:
            oos_trades_df = self.trades_df[pd.to_datetime(self.trades_df["entry_time"]) >= self.oos_start_date].reset_index(drop=True)
        else:
            oos_trades_df = pd.DataFrame()

        oos_metrics = self.compute_metrics(
            oos_equity_df,
            oos_trades_df,
            oos_init_cap,
            period_name="Out-of-Sample (2026)"
        )

        monthly_table = self.compute_monthly_returns(self.equity_df)

        self.results = {
            "full": full_metrics,
            "in_sample": is_metrics,
            "out_of_sample": oos_metrics,
            "monthly_table": monthly_table,
        }

        # Save artifacts
        self.save_trades_csv()
        chart_png_path = self.plot_charts()
        self.generate_html_report(chart_png_path)
        self.print_terminal_summary()

    def save_trades_csv(self) -> str:
        """Save complete trade logs to CSV."""
        trades_path = os.path.join(self.output_dir, "trades.csv")
        if not self.trades_df.empty:
            self.trades_df.to_csv(trades_path, index=False)
            logger.info(f"Saved {len(self.trades_df):,} trades to: {trades_path}")
        else:
            logger.warning("No trades were generated to save.")
        return trades_path

    def plot_charts(self) -> str:
        """Generate high-resolution 4-panel performance chart."""
        chart_path = os.path.join(self.output_dir, "equity_curve.png")
        df = self.equity_df

        plt.style.use("dark_background")
        fig, axes = plt.subplots(3, 1, figsize=(14, 12), gridspec_kw={"height_ratios": [3, 1.5, 1.5]}, sharex=True)

        dates = df["datetime"]

        # Panel 1: Equity Curve vs Buy & Hold Benchmark
        ax1 = axes[0]
        ax1.plot(dates, df["strategy_equity"], label=f"EMA {self.fast_ema}/{self.slow_ema} Strategy", color="#00E676", linewidth=1.8)
        ax1.plot(dates, df["benchmark_equity"], label="Buy & Hold BTC Benchmark", color="#FF9100", linewidth=1.4, linestyle="--", alpha=0.85)

        # In-sample / Out-of-sample vertical demarcation line
        ax1.axvline(self.oos_start_date, color="#00B0FF", linestyle=":", linewidth=2.0, label="OOS Split (2026-01-01)")

        ax1.set_title(f"CoinDCX BTCUSDT 1H: EMA {self.fast_ema}/{self.slow_ema} Crossover Performance (2023 - 2026)", fontsize=14, fontweight="bold", pad=12)
        ax1.set_ylabel("Portfolio Value (₹)", fontsize=11, labelpad=8)
        ax1.grid(True, linestyle="--", alpha=0.25)
        ax1.legend(loc="upper left", frameon=True, facecolor="#1E1E1E", edgecolor="#333333")

        # Format Y-axis with comma separators
        ax1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: f"₹{x:,.0f}"))

        # Panel 2: Underwater Drawdown (%)
        ax2 = axes[1]
        ax2.fill_between(dates, df["drawdown_pct"], 0, color="#FF5252", alpha=0.4, label="Strategy Drawdown")
        ax2.plot(dates, df["drawdown_pct"], color="#FF1744", linewidth=1.0)
        ax2.plot(dates, df["benchmark_drawdown_pct"], color="#FFB300", linewidth=0.8, linestyle="--", alpha=0.6, label="Benchmark Drawdown")
        ax2.axvline(self.oos_start_date, color="#00B0FF", linestyle=":", linewidth=2.0)
        ax2.set_ylabel("Drawdown (%)", fontsize=11, labelpad=8)
        ax2.grid(True, linestyle="--", alpha=0.25)
        ax2.legend(loc="lower left", frameon=True, facecolor="#1E1E1E", edgecolor="#333333")

        # Panel 3: Active Position Regime (+1 Long, -1 Short, 0 Flat)
        ax3 = axes[2]
        ax3.step(dates, df["position"], where="post", color="#7C4DFF", linewidth=1.2, label="Position (+1 Long / -1 Short)")
        ax3.axhline(0, color="#666666", linestyle="-", linewidth=0.8)
        ax3.axvline(self.oos_start_date, color="#00B0FF", linestyle=":", linewidth=2.0)
        ax3.set_ylabel("Position State", fontsize=11, labelpad=8)
        ax3.set_yticks([-1, 0, 1])
        ax3.set_yticklabels(["Short (-1)", "Flat (0)", "Long (+1)"])
        ax3.grid(True, linestyle="--", alpha=0.25)
        ax3.legend(loc="upper left", frameon=True, facecolor="#1E1E1E", edgecolor="#333333")

        # Format X-axis Dates
        axes[2].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        fig.autofmt_xdate()

        plt.tight_layout()
        fig.savefig(chart_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info(f"Saved performance chart to: {chart_path}")
        return chart_path

    def generate_html_report(self, chart_path: str) -> str:
        """Generate comprehensive standalone HTML performance report."""
        report_path = os.path.join(self.output_dir, "performance_report.html")

        # Encode chart image to base64 for standalone HTML rendering
        chart_base64 = ""
        if os.path.exists(chart_path):
            with open(chart_path, "rb") as f:
                chart_base64 = base64.b64encode(f.read()).decode("utf-8")

        f = self.results["full"]
        i_s = self.results["in_sample"]
        oos = self.results["out_of_sample"]
        monthly_df = self.results["monthly_table"]

        # Strategy Diagnosis logic
        overfit_risk = "LOW TO MODERATE"
        if oos["profit_factor"] < 0.9 or oos["total_return_pct"] < -10:
            diagnosis_verdict = "Vulnerable / Underperforming in Out-of-Sample"
            diagnosis_class = "warning"
            diagnosis_text = (
                "The EMA 9/21 strategy suffered significant decay during the 2026 Out-of-Sample period. "
                "While profitable or positive in certain trending phases during In-Sample (2023-2025), "
                "frequent whipsaws in sideways/consolidating regimes erode capital via transaction costs and slippage. "
                "Parameter optimization is NOT recommended until trend-filters (e.g., ADX > 25, ATR filters, Volatility thresholds) "
                "or multi-timeframe confirmation are added."
            )
        elif oos["profit_factor"] >= 1.2 and oos["cagr_pct"] > 0:
            diagnosis_verdict = "Robust & Consistent"
            diagnosis_class = "success"
            diagnosis_text = "The strategy demonstrates consistent positive expectancy across both In-Sample and Out-of-Sample periods."
        else:
            diagnosis_verdict = "Moderate Trend-Capture with High Drawdown"
            diagnosis_class = "neutral"
            diagnosis_text = (
                "The strategy captures major cyclical crypto trends but suffers substantial drawdown during choppy, rangey market conditions. "
                "Baseline EMA 9/21 proves that un-filtered moving average crossovers require secondary filters (volume, regime detection, volatility sizing) "
                "to be viable for production live trading."
            )

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CoinDCX Backtest Report: EMA 9/21 BTCUSDT</title>
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
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            background: linear-gradient(135deg, #1E1E1E 0%, #2A2A2A 100%);
            padding: 24px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            margin-bottom: 24px;
        }}
        h1, h2, h3 {{
            margin-top: 0;
        }}
        h1 {{ color: #FFFFFF; font-size: 28px; }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-top: 16px;
            font-size: 14px;
            color: var(--text-secondary);
        }}
        .meta-item strong {{ color: var(--text-primary); }}
        
        /* KPI Cards */
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
        .kpi-title {{ font-size: 13px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }}
        .kpi-value {{ font-size: 24px; font-weight: bold; margin-top: 8px; }}
        .positive {{ color: var(--accent-green); }}
        .negative {{ color: var(--accent-red); }}
        .neutral {{ color: var(--accent-blue); }}

        /* Tables */
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
            padding: 12px 16px;
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
        th:first-child, td:first-child {{
            text-align: left;
        }}
        tr:hover {{ background-color: #2D2D2D; }}

        .chart-box {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 24px;
            text-align: center;
        }}
        .chart-box img {{
            max-width: 100%;
            height: auto;
            border-radius: 6px;
        }}

        /* Diagnosis Alert */
        .alert {{
            padding: 18px;
            border-radius: 8px;
            margin-bottom: 24px;
            border-left: 5px solid;
        }}
        .alert.warning {{ background-color: rgba(255, 82, 82, 0.1); border-color: var(--accent-red); }}
        .alert.success {{ background-color: rgba(0, 230, 118, 0.1); border-color: var(--accent-green); }}
        .alert.neutral {{ background-color: rgba(41, 182, 246, 0.1); border-color: var(--accent-blue); }}

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
        <!-- Header -->
        <div class="header">
            <h1>Strategy V1: EMA 9/21 Crossover Performance Report</h1>
            <div class="meta-grid">
                <div class="meta-item"><strong>Asset / Pair:</strong> BTCUSDT (1-Hour)</div>
                <div class="meta-item"><strong>Source:</strong> CoinDCX Public Candles API</div>
                <div class="meta-item"><strong>Initial Capital:</strong> ₹{self.initial_capital:,.2f}</div>
                <div class="meta-item"><strong>Fee Model:</strong> 0.10% + 0.05% Slippage</div>
                <div class="meta-item"><strong>Execution:</strong> Next-Candle Open (Zero Bias)</div>
                <div class="meta-item"><strong>Positioning:</strong> Long & Short (1.0x, No Leverage)</div>
            </div>
        </div>

        <!-- Strategy Diagnosis Box -->
        <div class="alert {diagnosis_class}">
            <h3 style="margin-top: 0; color: {'var(--accent-red)' if diagnosis_class=='warning' else 'var(--accent-green)'};">
                Strategy Baseline Diagnosis: {diagnosis_verdict}
            </h3>
            <p>{diagnosis_text}</p>
        </div>

        <!-- KPI Grid -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-title">Full Net Return</div>
                <div class="kpi-value {'positive' if f['total_return_pct'] >= 0 else 'negative'}">{f['total_return_pct']:+.2f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">₹{f['final_equity']:,.0f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">CAGR (Annualized)</div>
                <div class="kpi-value {'positive' if f['cagr_pct'] >= 0 else 'negative'}">{f['cagr_pct']:.2f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">{f['duration_days']} Days</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Max Drawdown</div>
                <div class="kpi-value negative">{f['max_drawdown_pct']:.2f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">DD Days: {f['max_dd_duration_days']}d</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Sharpe Ratio</div>
                <div class="kpi-value neutral">{f['sharpe_ratio']:.2f}</div>
                <div style="font-size: 12px; color: var(--text-secondary);">Sortino: {f['sortino_ratio']:.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Win Rate</div>
                <div class="kpi-value neutral">{f['win_rate_pct']:.1f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">{f['total_trades']} Total Trades</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Profit Factor</div>
                <div class="kpi-value {'positive' if f['profit_factor'] >= 1.0 else 'negative'}">{f['profit_factor']:.2f}</div>
                <div style="font-size: 12px; color: var(--text-secondary);">Exp: {f['expectancy_pct']:+.2f}%</div>
            </div>
        </div>

        <!-- Performance Comparison Table -->
        <h2 class="section-title">Walk-Forward Regime Breakdown: In-Sample vs Out-of-Sample</h2>
        <table>
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>Full Period (2023 - 2026)</th>
                    <th>In-Sample (2023 - 2025)</th>
                    <th>Out-of-Sample (2026)</th>
                    <th>Benchmark (BTC Hold)</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Date Range</strong></td>
                    <td>{f['start_date']} → {f['end_date']}</td>
                    <td>{i_s.get('start_date', 'N/A')} → {i_s.get('end_date', 'N/A')}</td>
                    <td>{oos.get('start_date', 'N/A')} → {oos.get('end_date', 'N/A')}</td>
                    <td>{f['start_date']} → {f['end_date']}</td>
                </tr>
                <tr>
                    <td><strong>Total Return (%)</strong></td>
                    <td class="{'positive' if f['total_return_pct'] >= 0 else 'negative'}">{f['total_return_pct']:+.2f}%</td>
                    <td class="{'positive' if i_s.get('total_return_pct', 0) >= 0 else 'negative'}">{i_s.get('total_return_pct', 0):+.2f}%</td>
                    <td class="{'positive' if oos.get('total_return_pct', 0) >= 0 else 'negative'}">{oos.get('total_return_pct', 0):+.2f}%</td>
                    <td class="positive">{f['benchmark_return_pct']:+.2f}%</td>
                </tr>
                <tr>
                    <td><strong>CAGR (%)</strong></td>
                    <td>{f['cagr_pct']:.2f}%</td>
                    <td>{i_s.get('cagr_pct', 0):.2f}%</td>
                    <td>{oos.get('cagr_pct', 0):.2f}%</td>
                    <td>—</td>
                </tr>
                <tr>
                    <td><strong>Max Drawdown (%)</strong></td>
                    <td class="negative">{f['max_drawdown_pct']:.2f}%</td>
                    <td class="negative">{i_s.get('max_drawdown_pct', 0):.2f}%</td>
                    <td class="negative">{oos.get('max_drawdown_pct', 0):.2f}%</td>
                    <td class="negative">{f['benchmark_max_dd_pct']:.2f}%</td>
                </tr>
                <tr>
                    <td><strong>Sharpe Ratio (Annualized)</strong></td>
                    <td>{f['sharpe_ratio']:.2f}</td>
                    <td>{i_s.get('sharpe_ratio', 0):.2f}</td>
                    <td>{oos.get('sharpe_ratio', 0):.2f}</td>
                    <td>—</td>
                </tr>
                <tr>
                    <td><strong>Sortino Ratio</strong></td>
                    <td>{f['sortino_ratio']:.2f}</td>
                    <td>{i_s.get('sortino_ratio', 0):.2f}</td>
                    <td>{oos.get('sortino_ratio', 0):.2f}</td>
                    <td>—</td>
                </tr>
                <tr>
                    <td><strong>Profit Factor</strong></td>
                    <td>{f['profit_factor']:.2f}</td>
                    <td>{i_s.get('profit_factor', 0):.2f}</td>
                    <td>{oos.get('profit_factor', 0):.2f}</td>
                    <td>—</td>
                </tr>
                <tr>
                    <td><strong>Win Rate (%)</strong></td>
                    <td>{f['win_rate_pct']:.1f}%</td>
                    <td>{i_s.get('win_rate_pct', 0):.1f}%</td>
                    <td>{oos.get('win_rate_pct', 0):.1f}%</td>
                    <td>—</td>
                </tr>
                <tr>
                    <td><strong>Total Trades Count</strong></td>
                    <td>{f['total_trades']}</td>
                    <td>{i_s.get('total_trades', 0)}</td>
                    <td>{oos.get('total_trades', 0)}</td>
                    <td>1 (Buy & Hold)</td>
                </tr>
                <tr>
                    <td><strong>Avg Trade Return (%)</strong></td>
                    <td>{f['avg_trade_pnl_pct']:+.2f}%</td>
                    <td>{i_s.get('avg_trade_pnl_pct', 0):+.2f}%</td>
                    <td>{oos.get('avg_trade_pnl_pct', 0):+.2f}%</td>
                    <td>—</td>
                </tr>
                <tr>
                    <td><strong>Avg Win / Avg Loss Ratio</strong></td>
                    <td>{f['win_loss_ratio']:.2f}</td>
                    <td>{i_s.get('win_loss_ratio', 0):.2f}</td>
                    <td>{oos.get('win_loss_ratio', 0):.2f}</td>
                    <td>—</td>
                </tr>
                <tr>
                    <td><strong>Market Exposure (%)</strong></td>
                    <td>{f['market_exposure_pct']:.1f}%</td>
                    <td>{i_s.get('market_exposure_pct', 0):.1f}%</td>
                    <td>{oos.get('market_exposure_pct', 0):.1f}%</td>
                    <td>100.0%</td>
                </tr>
            </tbody>
        </table>

        <!-- Long vs Short Breakdown -->
        <h2 class="section-title">Long vs Short Performance Dissection</h2>
        <table>
            <thead>
                <tr>
                    <th>Direction</th>
                    <th>Trades</th>
                    <th>Win Rate (%)</th>
                    <th>Profit Factor</th>
                    <th>Net PnL (₹)</th>
                    <th>Avg Return per Trade (%)</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>LONG Positions</strong></td>
                    <td>{f['long_stats']['trades']}</td>
                    <td>{f['long_stats']['win_rate']:.1f}%</td>
                    <td>{f['long_stats']['profit_factor']:.2f}</td>
                    <td class="{'positive' if f['long_stats']['net_pnl'] >= 0 else 'negative'}">₹{f['long_stats']['net_pnl']:,.2f}</td>
                    <td class="{'positive' if f['long_stats']['avg_trade_pct'] >= 0 else 'negative'}">{f['long_stats']['avg_trade_pct']:+.2f}%</td>
                </tr>
                <tr>
                    <td><strong>SHORT Positions</strong></td>
                    <td>{f['short_stats']['trades']}</td>
                    <td>{f['short_stats']['win_rate']:.1f}%</td>
                    <td>{f['short_stats']['profit_factor']:.2f}</td>
                    <td class="{'positive' if f['short_stats']['net_pnl'] >= 0 else 'negative'}">₹{f['short_stats']['net_pnl']:,.2f}</td>
                    <td class="{'positive' if f['short_stats']['avg_trade_pct'] >= 0 else 'negative'}">{f['short_stats']['avg_trade_pct']:+.2f}%</td>
                </tr>
            </tbody>
        </table>

        <!-- High-Res Charts Box -->
        <h2 class="section-title">Visual Performance & Underwater Drawdown Analysis</h2>
        <div class="chart-box">
            <img src="data:image/png;base64,{chart_base64}" alt="EMA 9/21 Strategy Equity and Drawdown Curve">
        </div>

        <!-- Monthly Returns Heatmap Table -->
        <h2 class="section-title">Monthly Returns Matrix (%)</h2>
        {monthly_df.to_html(classes="monthly-table", border=0)}

        <div style="margin-top: 32px; font-size: 12px; color: var(--text-secondary); text-align: center;">
            Generated by CoinDCX Quantitative Backtester | Strategy V1 Baseline | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
        </div>
    </div>
</body>
</html>
"""
        with open(report_path, "w", encoding="utf-8") as f_out:
            f_out.write(html_content)

        logger.info(f"Saved interactive HTML performance report to: {report_path}")
        return report_path

    def print_terminal_summary(self):
        """Print structured ASCII summary in terminal."""
        f = self.results["full"]
        i_s = self.results["in_sample"]
        oos = self.results["out_of_sample"]

        print("\n" + "=" * 78)
        print("          EMA 9/21 CROSSOVER STRATEGY V1 BACKTEST SUMMARY (BTCUSDT 1H)")
        print("=" * 78)
        print(f"  Initial Capital     : ₹{self.initial_capital:,.2f}")
        print(f"  Final Equity        : ₹{f['final_equity']:,.2f} (Net Return: {f['total_return_pct']:+.2f}%)")
        print(f"  CAGR                : {f['cagr_pct']:.2f}% (Benchmark Return: {f['benchmark_return_pct']:+.2f}%)")
        print(f"  Max Drawdown        : {f['max_drawdown_pct']:.2f}% (Duration: {f['max_dd_duration_days']} days)")
        print(f"  Sharpe / Sortino    : {f['sharpe_ratio']:.2f} / {f['sortino_ratio']:.2f}")
        print(f"  Profit Factor       : {f['profit_factor']:.2f}")
        print(f"  Win Rate            : {f['win_rate_pct']:.1f}% ({f['winning_trades']}W / {f['losing_trades']}L / {f['total_trades']} Total)")
        print(f"  Avg Win / Avg Loss  : {f['avg_win_pct']:+.2f}% / {f['avg_loss_pct']:+.2f}% (Ratio: {f['win_loss_ratio']:.2f})")
        print(f"  Expectancy          : {f['expectancy_pct']:+.2f}% per trade")
        print(f"  Market Exposure     : {f['market_exposure_pct']:.1f}%")
        print("-" * 78)
        print("  WALK-FORWARD COMPARISON:")
        print(f"    * In-Sample  (2023-2025): Return={i_s.get('total_return_pct', 0):+.2f}%, PF={i_s.get('profit_factor', 0):.2f}, WinRate={i_s.get('win_rate_pct', 0):.1f}%, Trades={i_s.get('total_trades', 0)}")
        print(f"    * Out-Sample (2026)     : Return={oos.get('total_return_pct', 0):+.2f}%, PF={oos.get('profit_factor', 0):.2f}, WinRate={oos.get('win_rate_pct', 0):.1f}%, Trades={oos.get('total_trades', 0)}")
        print("-" * 78)
        print("  LONG VS SHORT BREAKDOWN:")
        print(f"    * Long Trades : {f['long_stats']['trades']:3d} | WinRate={f['long_stats']['win_rate']:.1f}% | PF={f['long_stats']['profit_factor']:.2f} | Net PnL=₹{f['long_stats']['net_pnl']:+,.2f}")
        print(f"    * Short Trades: {f['short_stats']['trades']:3d} | WinRate={f['short_stats']['win_rate']:.1f}% | PF={f['short_stats']['profit_factor']:.2f} | Net PnL=₹{f['short_stats']['net_pnl']:+,.2f}")
        print("-" * 78)
        print(f"  Output Artifacts Saved in: {self.output_dir}/")
        print(f"    - Trade Log CSV        : trades.csv")
        print(f"    - Performance Report   : performance_report.html")
        print(f"    - Equity Curve Plot    : equity_curve.png")
        print("=" * 78 + "\n")


def parse_args():
    """CLI Argument Parser."""
    parser = argparse.ArgumentParser(
        description="EMA 9/21 Crossover Backtesting Engine on CoinDCX BTCUSDT 1H Data",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--data-path", "-d", type=str, default=DEFAULT_DATA_PATH, help="Path to input 1h OHLCV CSV")
    parser.add_argument("--output-dir", "-o", type=str, default=DEFAULT_OUTPUT_DIR, help="Output directory for results")
    parser.add_argument("--fast-ema", type=int, default=9, help="Fast EMA period")
    parser.add_argument("--slow-ema", type=int, default=21, help="Slow EMA period")
    parser.add_argument("--capital", type=float, default=100000.0, help="Initial capital (INR equivalent)")
    parser.add_argument("--fee", type=float, default=0.001, help="Trading fee rate (e.g. 0.001 = 0.1%%)")
    parser.add_argument("--slippage", type=float, default=0.0005, help="Slippage rate (e.g. 0.0005 = 0.05%%)")
    parser.add_argument("--long-only", action="store_true", help="Run long-only mode (disable shorting)")
    return parser.parse_args()


def main():
    """Main CLI entrypoint."""
    args = parse_args()
    backtester = EMA921Backtester(
        data_path=args.data_path,
        output_dir=args.output_dir,
        fast_ema=args.fast_ema,
        slow_ema=args.slow_ema,
        initial_capital=args.capital,
        fee_rate=args.fee,
        slippage=args.slippage,
        allow_short=not args.long_only
    )
    backtester.run_all_regimes()


if __name__ == "__main__":
    main()
