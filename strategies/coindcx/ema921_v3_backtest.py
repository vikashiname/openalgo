#!/usr/bin/env python3
"""
Strategy V3: EMA 9/21 Crossover with 4H EMA 200 Regime Filter + 1H ADX(14) Trend Strength Filter
=============================================================================================
Hypothesis:
"Adding a 1H ADX trend-strength filter to the validated V2 framework will further reduce
 low-momentum/choppy EMA crossover trades and improve expectancy and Profit Factor while
 maintaining or improving OOS robustness."

Rules:
1. Base strategy: EMA 9/21 on BTCUSDT 1H.
2. V2 Regime Filter: Completed 4H EMA 200.
3. New V3 Variable: 1H ADX(14) > 20.
4. Long Entry: 4H Close > 4H EMA 200 AND 1H EMA 9 crosses above EMA 21 AND 1H ADX(14) > 20.
5. Short Entry: 4H Close < 4H EMA 200 AND 1H EMA 9 crosses below EMA 21 AND 1H ADX(14) > 20.
6. Zero look-ahead bias: Signals calculated at bar close, executed at next 1H Open.
7. Realistic friction: 0.10% fee + 0.05% slippage.
8. Exact Walk-Forward Split:
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
logger = logging.getLogger("EMA921_V3_Backtester")

# Default Paths
DEFAULT_DATA_PATH = os.path.expanduser("~/backtesting/coindcx_data/BTCUSDT_1h_2023-01-01_2026-08-30.csv")
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/backtesting/research/v3_adx_filter")


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Compute standard Wilder's Average Directional Index (ADX)."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    pos_dm = pd.Series(pos_dm, index=close.index)
    neg_dm = pd.Series(neg_dm, index=close.index)

    # Wilder's Smoothing: alpha = 1 / period
    tr_smooth = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    pos_dm_smooth = pos_dm.ewm(alpha=1.0 / period, adjust=False).mean()
    neg_dm_smooth = neg_dm.ewm(alpha=1.0 / period, adjust=False).mean()

    pos_di = 100.0 * (pos_dm_smooth / tr_smooth.replace(0, np.nan)).fillna(0.0)
    neg_di = 100.0 * (neg_dm_smooth / tr_smooth.replace(0, np.nan)).fillna(0.0)

    dx = 100.0 * ((pos_di - neg_di).abs() / (pos_di + neg_di).replace(0, np.nan)).fillna(0.0)
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    return adx


class StrategyV3Backtester:
    """Auditing and Research Engine comparing Strategy V1, V2, and V3."""

    def __init__(
        self,
        data_path: str = DEFAULT_DATA_PATH,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        fast_ema: int = 9,
        slow_ema: int = 21,
        htf_ema: int = 200,
        adx_period: int = 14,
        adx_threshold: float = 20.0,
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
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
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
        self.results_v3: Dict[str, Any] = {}
        self.equity_v1: Optional[pd.DataFrame] = None
        self.equity_v2: Optional[pd.DataFrame] = None
        self.equity_v3: Optional[pd.DataFrame] = None
        self.trades_v1: Optional[pd.DataFrame] = None
        self.trades_v2: Optional[pd.DataFrame] = None
        self.trades_v3: Optional[pd.DataFrame] = None

    def load_and_prepare_data(self) -> pd.DataFrame:
        """Load CSV, parse timestamps, construct 4H bars & ADX with zero look-ahead bias."""
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
        # 1H Indicators: EMA 9, EMA 21, and ADX(14)
        # ---------------------------------------------------------
        close = df["close"]
        df["ema_fast"] = close.ewm(span=self.fast_ema, adjust=False).mean()
        df["ema_slow"] = close.ewm(span=self.slow_ema, adjust=False).mean()
        df["adx"] = compute_adx(df["high"], df["low"], df["close"], self.adx_period)

        fast_above = df["ema_fast"] > df["ema_slow"]
        fast_above_prev = df["ema_fast"].shift(1) > df["ema_slow"].shift(1)

        # Raw 1H Crossover Triggers
        df["bull_cross"] = (fast_above) & (~fast_above_prev)
        df["bear_cross"] = (~fast_above) & (fast_above_prev)

        # Burn-in: allow 4H EMA 200 sufficient candles
        burn_in = max(self.slow_ema * 2, self.htf_ema * 4)

        # ---------------------------------------------------------
        # V1 Position State Generation (Baseline)
        # ---------------------------------------------------------
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

        # ---------------------------------------------------------
        # V2 Position State Generation (4H EMA 200 Filter)
        # ---------------------------------------------------------
        target_state_v2 = np.zeros(len(df), dtype=int)
        curr_v2 = 0
        for i in range(burn_in, len(df)):
            b_cross = df.loc[i, "bull_cross"]
            s_cross = df.loc[i, "bear_cross"]
            reg_bull = df.loc[i, "regime_bull"]
            reg_bear = df.loc[i, "regime_bear"]

            if b_cross:
                if reg_bull:
                    curr_v2 = 1
                elif curr_v2 == -1:
                    curr_v2 = 0
            elif s_cross:
                if reg_bear:
                    curr_v2 = -1
                elif curr_v2 == 1:
                    curr_v2 = 0
            target_state_v2[i] = curr_v2
        df["target_state_v2"] = target_state_v2
        df["position_v2"] = df["target_state_v2"].shift(1).fillna(0).astype(int)

        # ---------------------------------------------------------
        # V3 Position State Generation (4H EMA 200 + 1H ADX > 20 Filter)
        # ---------------------------------------------------------
        target_state_v3 = np.zeros(len(df), dtype=int)
        curr_v3 = 0
        for i in range(burn_in, len(df)):
            b_cross = df.loc[i, "bull_cross"]
            s_cross = df.loc[i, "bear_cross"]
            reg_bull = df.loc[i, "regime_bull"]
            reg_bear = df.loc[i, "regime_bear"]
            adx_ok = df.loc[i, "adx"] > self.adx_threshold

            if b_cross:
                if reg_bull and adx_ok:
                    curr_v3 = 1
                elif curr_v3 == -1:
                    curr_v3 = 0
            elif s_cross:
                if reg_bear and adx_ok:
                    curr_v3 = -1
                elif curr_v3 == 1:
                    curr_v3 = 0
            target_state_v3[i] = curr_v3
        df["target_state_v3"] = target_state_v3
        df["position_v3"] = df["target_state_v3"].shift(1).fillna(0).astype(int)

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
        """Execute full backtest suite for V1, V2, and V3 across all walk-forward regimes."""
        self.load_and_prepare_data()

        # Run V1
        self.equity_v1, self.trades_v1 = self.simulate_strategy("position_v1")
        # Run V2
        self.equity_v2, self.trades_v2 = self.simulate_strategy("position_v2")
        # Run V3
        self.equity_v3, self.trades_v3 = self.simulate_strategy("position_v3")

        # Slice Walk-Forward Regimes for V1, V2 & V3
        for tag, equity_df, trades_df, target_dict in [
            ("V1", self.equity_v1, self.trades_v1, self.results_v1),
            ("V2", self.equity_v2, self.trades_v2, self.results_v2),
            ("V3", self.equity_v3, self.trades_v3, self.results_v3),
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
        # 1. Save V3 Trades CSV
        v3_trades_path = os.path.join(self.output_dir, "trades_v3.csv")
        self.trades_v3.to_csv(v3_trades_path, index=False)
        logger.info(f"Saved V3 trades to: {v3_trades_path}")

        # 2. Save Comparative Plot (4 Panels)
        chart_path = os.path.join(self.output_dir, "equity_curve_v3.png")
        plt.style.use("dark_background")
        fig, axes = plt.subplots(4, 1, figsize=(14, 15), gridspec_kw={"height_ratios": [3, 1.2, 1.2, 1.2]}, sharex=True)

        dates = self.equity_v3["datetime"]

        # Panel 1: V1 vs V2 vs V3 vs Benchmark Equity Curve
        ax1 = axes[0]
        ax1.plot(dates, self.equity_v3["strategy_equity"], label="Strategy V3 (1H EMA 9/21 + 4H EMA 200 + ADX>20)", color="#00E676", linewidth=2.0)
        ax1.plot(dates, self.equity_v2["strategy_equity"], label="Strategy V2 (1H EMA 9/21 + 4H EMA 200)", color="#29B6F6", linewidth=1.5, linestyle="-.")
        ax1.plot(dates, self.equity_v1["strategy_equity"], label="Strategy V1 (Baseline EMA 9/21)", color="#FF5252", linewidth=1.2, linestyle="--")
        ax1.plot(dates, self.equity_v3["benchmark_equity"], label="Buy & Hold BTC Benchmark", color="#FFB300", linewidth=1.2, linestyle=":", alpha=0.85)

        ax1.axvline(self.oos_start_date, color="#00B0FF", linestyle=":", linewidth=2.0, label="OOS Split (2026-01-01)")
        ax1.set_title("Strategy Evolution: V1 (Baseline) vs V2 (4H Filter) vs V3 (4H Filter + 1H ADX>20 Filter)", fontsize=14, fontweight="bold", pad=12)
        ax1.set_ylabel("Portfolio Equity (₹)", fontsize=11, labelpad=8)
        ax1.grid(True, linestyle="--", alpha=0.25)
        ax1.legend(loc="upper left", frameon=True, facecolor="#1E1E1E", edgecolor="#333333")
        ax1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: f"₹{x:,.0f}"))

        # Panel 2: Underwater Drawdown Comparison
        ax2 = axes[1]
        ax2.plot(dates, self.equity_v3["drawdown_pct"], label="Strategy V3 Drawdown", color="#00E676", linewidth=1.2)
        ax2.plot(dates, self.equity_v2["drawdown_pct"], label="Strategy V2 Drawdown", color="#29B6F6", linewidth=1.0, linestyle="-.")
        ax2.plot(dates, self.equity_v1["drawdown_pct"], label="Strategy V1 Drawdown", color="#FF5252", linewidth=0.8, linestyle="--", alpha=0.7)
        ax2.axvline(self.oos_start_date, color="#00B0FF", linestyle=":", linewidth=2.0)
        ax2.set_ylabel("Drawdown (%)", fontsize=11, labelpad=8)
        ax2.grid(True, linestyle="--", alpha=0.25)
        ax2.legend(loc="lower left", frameon=True, facecolor="#1E1E1E", edgecolor="#333333")

        # Panel 3: 1H ADX(14) with Threshold Line
        ax3 = axes[2]
        ax3.plot(dates, self.df["adx"], color="#AB47BC", linewidth=1.0, label="1H ADX(14)")
        ax3.axhline(self.adx_threshold, color="#FFD54F", linestyle="--", linewidth=1.2, label=f"Threshold ({self.adx_threshold})")
        ax3.axvline(self.oos_start_date, color="#00B0FF", linestyle=":", linewidth=2.0)
        ax3.set_ylabel("ADX Value", fontsize=11, labelpad=8)
        ax3.grid(True, linestyle="--", alpha=0.25)
        ax3.legend(loc="upper left", frameon=True, facecolor="#1E1E1E", edgecolor="#333333")

        # Panel 4: Position Exposure State
        ax4 = axes[3]
        ax4.step(dates, self.equity_v3["position"], where="post", color="#7C4DFF", linewidth=1.2, label="V3 Position (+1 Long, -1 Short, 0 Flat)")
        ax4.axhline(0, color="#666666", linestyle="-", linewidth=0.8)
        ax4.axvline(self.oos_start_date, color="#00B0FF", linestyle=":", linewidth=2.0)
        ax4.set_ylabel("Position State", fontsize=11, labelpad=8)
        ax4.set_yticks([-1, 0, 1])
        ax4.set_yticklabels(["Short (-1)", "Flat (0)", "Long (+1)"])
        ax4.grid(True, linestyle="--", alpha=0.25)
        ax4.legend(loc="upper left", frameon=True, facecolor="#1E1E1E", edgecolor="#333333")

        axes[3].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        axes[3].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        fig.autofmt_xdate()

        fig.subplots_adjust(left=0.08, right=0.95, top=0.95, bottom=0.06, hspace=0.15)
        fig.savefig(chart_path, dpi=300)
        plt.close(fig)
        logger.info(f"Saved comparative chart to: {chart_path}")

        # 3. Save Standalone HTML Performance Report
        self.generate_html_report(chart_path)

    def generate_html_report(self, chart_path: str):
        """Generate comprehensive standalone HTML comparison report."""
        report_path = os.path.join(self.output_dir, "performance_report_v3.html")

        chart_base64 = ""
        if os.path.exists(chart_path):
            with open(chart_path, "rb") as f:
                chart_base64 = base64.b64encode(f.read()).decode("utf-8")

        v1_f, v2_f, v3_f = self.results_v1["full"], self.results_v2["full"], self.results_v3["full"]
        v1_is, v2_is, v3_is = self.results_v1["in_sample"], self.results_v2["in_sample"], self.results_v3["in_sample"]
        v1_oos, v2_oos, v3_oos = self.results_v1["out_of_sample"], self.results_v2["out_of_sample"], self.results_v3["out_of_sample"]

        trades_removed_v3_vs_v2 = v2_f["total_trades"] - v3_f["total_trades"]
        trades_reduction_pct_vs_v2 = (trades_removed_v3_vs_v2 / v2_f["total_trades"]) * 100.0 if v2_f["total_trades"] > 0 else 0.0

        trades_removed_v3_vs_v1 = v1_f["total_trades"] - v3_f["total_trades"]
        trades_reduction_pct_vs_v1 = (trades_removed_v3_vs_v1 / v1_f["total_trades"]) * 100.0 if v1_f["total_trades"] > 0 else 0.0

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Strategy V3 Experiment Report: 4H EMA 200 + 1H ADX(14)>20 Filter</title>
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
            --accent-purple: #BA68C8;
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
            border-left: 5px solid var(--accent-purple);
            background-color: rgba(186, 104, 200, 0.1);
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
            <h1>Strategy V3 Experiment: 4H EMA 200 + 1H ADX(14) > 20 Filter</h1>
            <div class="meta-grid">
                <div class="meta-item"><strong>Asset / Pair:</strong> BTCUSDT (1-Hour)</div>
                <div class="meta-item"><strong>Regime Filter:</strong> 4H EMA 200 + 1H ADX(14) > 20</div>
                <div class="meta-item"><strong>Initial Capital:</strong> ₹{self.initial_capital:,.2f}</div>
                <div class="meta-item"><strong>Fee Model:</strong> 0.10% + 0.05% Slippage</div>
                <div class="meta-item"><strong>Execution:</strong> Next 1H Candle Open (Zero Look-Ahead)</div>
                <div class="meta-item"><strong>Positioning:</strong> Long & Short (1.0x, No Leverage)</div>
            </div>
        </div>

        <div class="alert">
            <h3 style="margin-top:0; color:var(--accent-gold);">Hypothesis Test & Scientific Evaluation</h3>
            <p><strong>Hypothesis:</strong> "Adding a 1H ADX trend-strength filter to the validated V2 framework will further reduce low-momentum/choppy EMA crossover trades and improve expectancy and Profit Factor while maintaining or improving OOS robustness."</p>
            <p><strong>Audit Outcome:</strong> The 1H ADX(14) > 20 filter removed an additional <strong>{trades_removed_v3_vs_v2} trades ({trades_reduction_pct_vs_v2:.1f}% reduction vs V2, {trades_reduction_pct_vs_v1:.1f}% reduction vs V1)</strong>. Exposure dropped to {v3_f['market_exposure_pct']:.1f}%. Full comparative metrics detailed below.</p>
        </div>

        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-title">V3 Net Return</div>
                <div class="kpi-value {'positive' if v3_f['total_return_pct'] >= 0 else 'negative'}">{v3_f['total_return_pct']:+.2f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">₹{v3_f['final_equity']:,.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Trades Filtered (vs V1)</div>
                <div class="kpi-value positive">-{trades_reduction_pct_vs_v1:.1f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">{v3_f['total_trades']} Total Trades</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Max Drawdown</div>
                <div class="kpi-value negative">{v3_f['max_drawdown_pct']:.2f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">V1 {v1_f['max_drawdown_pct']:.1f}% | V2 {v2_f['max_drawdown_pct']:.1f}%</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Profit Factor</div>
                <div class="kpi-value {'positive' if v3_f['profit_factor'] >= 1.0 else 'negative'}">{v3_f['profit_factor']:.2f}</div>
                <div style="font-size: 12px; color: var(--text-secondary);">V1 {v1_f['profit_factor']:.2f} | V2 {v2_f['profit_factor']:.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Expectancy</div>
                <div class="kpi-value {'positive' if v3_f['expectancy_pct'] >= 0 else 'negative'}">{v3_f['expectancy_pct']:+.2f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">per trade</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Market Exposure</div>
                <div class="kpi-value neutral">{v3_f['market_exposure_pct']:.1f}%</div>
                <div style="font-size: 12px; color: var(--text-secondary);">V1 {v1_f['market_exposure_pct']:.1f}% | V2 {v2_f['market_exposure_pct']:.1f}%</div>
            </div>
        </div>

        <h2 class="section-title">Comprehensive Tri-Party Comparison: V1 vs V2 vs V3</h2>
        <table>
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>Strategy V1 (Baseline)</th>
                    <th>Strategy V2 (4H Filter)</th>
                    <th>Strategy V3 (4H + ADX Filter)</th>
                    <th>Delta (V3 vs V2)</th>
                    <th>Delta (V3 vs V1)</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Final Equity (₹)</strong></td>
                    <td>₹{v1_f['final_equity']:,.2f}</td>
                    <td>₹{v2_f['final_equity']:,.2f}</td>
                    <td>₹{v3_f['final_equity']:,.2f}</td>
                    <td class="{'positive' if v3_f['final_equity'] >= v2_f['final_equity'] else 'negative'}">{v3_f['final_equity'] - v2_f['final_equity']:+,.2f}</td>
                    <td class="positive">+{v3_f['final_equity'] - v1_f['final_equity']:+,.2f}</td>
                </tr>
                <tr>
                    <td><strong>Net Return (%)</strong></td>
                    <td class="negative">{v1_f['total_return_pct']:+.2f}%</td>
                    <td class="negative">{v2_f['total_return_pct']:+.2f}%</td>
                    <td class="negative">{v3_f['total_return_pct']:+.2f}%</td>
                    <td class="{'positive' if v3_f['total_return_pct'] >= v2_f['total_return_pct'] else 'negative'}">{v3_f['total_return_pct'] - v2_f['total_return_pct']:+.2f}%</td>
                    <td class="positive">{v3_f['total_return_pct'] - v1_f['total_return_pct']:+.2f}%</td>
                </tr>
                <tr>
                    <td><strong>CAGR (%)</strong></td>
                    <td>{v1_f['cagr_pct']:.2f}%</td>
                    <td>{v2_f['cagr_pct']:.2f}%</td>
                    <td>{v3_f['cagr_pct']:.2f}%</td>
                    <td class="{'positive' if v3_f['cagr_pct'] >= v2_f['cagr_pct'] else 'negative'}">{v3_f['cagr_pct'] - v2_f['cagr_pct']:+.2f}%</td>
                    <td class="positive">{v3_f['cagr_pct'] - v1_f['cagr_pct']:+.2f}%</td>
                </tr>
                <tr>
                    <td><strong>Max Drawdown (%)</strong></td>
                    <td class="negative">{v1_f['max_drawdown_pct']:.2f}%</td>
                    <td class="negative">{v2_f['max_drawdown_pct']:.2f}%</td>
                    <td class="negative">{v3_f['max_drawdown_pct']:.2f}%</td>
                    <td class="{'positive' if v3_f['max_drawdown_pct'] >= v2_f['max_drawdown_pct'] else 'negative'}">{v3_f['max_drawdown_pct'] - v2_f['max_drawdown_pct']:+.2f}%</td>
                    <td class="positive">{v3_f['max_drawdown_pct'] - v1_f['max_drawdown_pct']:+.2f}%</td>
                </tr>
                <tr>
                    <td><strong>Profit Factor</strong></td>
                    <td>{v1_f['profit_factor']:.2f}</td>
                    <td>{v2_f['profit_factor']:.2f}</td>
                    <td>{v3_f['profit_factor']:.2f}</td>
                    <td class="{'positive' if v3_f['profit_factor'] >= v2_f['profit_factor'] else 'negative'}">{v3_f['profit_factor'] - v2_f['profit_factor']:+.2f}</td>
                    <td class="positive">+{v3_f['profit_factor'] - v1_f['profit_factor']:+.2f}</td>
                </tr>
                <tr>
                    <td><strong>Win Rate (%)</strong></td>
                    <td>{v1_f['win_rate_pct']:.1f}%</td>
                    <td>{v2_f['win_rate_pct']:.1f}%</td>
                    <td>{v3_f['win_rate_pct']:.1f}%</td>
                    <td>{v3_f['win_rate_pct'] - v2_f['win_rate_pct']:+.1f}%</td>
                    <td>{v3_f['win_rate_pct'] - v1_f['win_rate_pct']:+.1f}%</td>
                </tr>
                <tr>
                    <td><strong>Expectancy (%)</strong></td>
                    <td>{v1_f['expectancy_pct']:+.2f}%</td>
                    <td>{v2_f['expectancy_pct']:+.2f}%</td>
                    <td>{v3_f['expectancy_pct']:+.2f}%</td>
                    <td class="{'positive' if v3_f['expectancy_pct'] >= v2_f['expectancy_pct'] else 'negative'}">{v3_f['expectancy_pct'] - v2_f['expectancy_pct']:+.2f}%</td>
                    <td class="positive">{v3_f['expectancy_pct'] - v1_f['expectancy_pct']:+.2f}%</td>
                </tr>
                <tr>
                    <td><strong>Sharpe Ratio</strong></td>
                    <td>{v1_f['sharpe_ratio']:.2f}</td>
                    <td>{v2_f['sharpe_ratio']:.2f}</td>
                    <td>{v3_f['sharpe_ratio']:.2f}</td>
                    <td>{v3_f['sharpe_ratio'] - v2_f['sharpe_ratio']:+.2f}</td>
                    <td>{v3_f['sharpe_ratio'] - v1_f['sharpe_ratio']:+.2f}</td>
                </tr>
                <tr>
                    <td><strong>Sortino Ratio</strong></td>
                    <td>{v1_f['sortino_ratio']:.2f}</td>
                    <td>{v2_f['sortino_ratio']:.2f}</td>
                    <td>{v3_f['sortino_ratio']:.2f}</td>
                    <td>{v3_f['sortino_ratio'] - v2_f['sortino_ratio']:+.2f}</td>
                    <td>{v3_f['sortino_ratio'] - v1_f['sortino_ratio']:+.2f}</td>
                </tr>
                <tr>
                    <td><strong>Total Trades Count</strong></td>
                    <td>{v1_f['total_trades']}</td>
                    <td>{v2_f['total_trades']}</td>
                    <td>{v3_f['total_trades']}</td>
                    <td class="positive">-{trades_removed_v3_vs_v2} (-{trades_reduction_pct_vs_v2:.1f}%)</td>
                    <td class="positive">-{trades_removed_v3_vs_v1} (-{trades_reduction_pct_vs_v1:.1f}%)</td>
                </tr>
                <tr>
                    <td><strong>Market Exposure (%)</strong></td>
                    <td>{v1_f['market_exposure_pct']:.1f}%</td>
                    <td>{v2_f['market_exposure_pct']:.1f}%</td>
                    <td>{v3_f['market_exposure_pct']:.1f}%</td>
                    <td class="positive">{v3_f['market_exposure_pct'] - v2_f['market_exposure_pct']:.1f}%</td>
                    <td class="positive">{v3_f['market_exposure_pct'] - v1_f['market_exposure_pct']:.1f}%</td>
                </tr>
                <tr>
                    <td><strong>Long Profit Factor</strong></td>
                    <td>{v1_f['long_pf']:.2f}</td>
                    <td>{v2_f['long_pf']:.2f}</td>
                    <td>{v3_f['long_pf']:.2f}</td>
                    <td>{v3_f['long_pf'] - v2_f['long_pf']:+.2f}</td>
                    <td>{v3_f['long_pf'] - v1_f['long_pf']:+.2f}</td>
                </tr>
                <tr>
                    <td><strong>Short Profit Factor</strong></td>
                    <td>{v1_f['short_pf']:.2f}</td>
                    <td>{v2_f['short_pf']:.2f}</td>
                    <td>{v3_f['short_pf']:.2f}</td>
                    <td>{v3_f['short_pf'] - v2_f['short_pf']:+.2f}</td>
                    <td>{v3_f['short_pf'] - v1_f['short_pf']:+.2f}</td>
                </tr>
                <tr>
                    <td><strong>Total Fees (₹)</strong></td>
                    <td>₹{v1_f['total_fees']:,.2f}</td>
                    <td>₹{v2_f['total_fees']:,.2f}</td>
                    <td>₹{v3_f['total_fees']:,.2f}</td>
                    <td>-₹{v2_f['total_fees'] - v3_f['total_fees']:,.2f}</td>
                    <td>-₹{v1_f['total_fees'] - v3_f['total_fees']:,.2f}</td>
                </tr>
                <tr>
                    <td><strong>Total Slippage (₹)</strong></td>
                    <td>₹{v1_f['total_slippage']:,.2f}</td>
                    <td>₹{v2_f['total_slippage']:,.2f}</td>
                    <td>₹{v3_f['total_slippage']:,.2f}</td>
                    <td>-₹{v2_f['total_slippage'] - v3_f['total_slippage']:,.2f}</td>
                    <td>-₹{v1_f['total_slippage'] - v3_f['total_slippage']:,.2f}</td>
                </tr>
            </tbody>
        </table>

        <h2 class="section-title">Comparative Equity, Drawdown & ADX Filter Charts</h2>
        <div class="chart-box">
            <img src="data:image/png;base64,{chart_base64}" alt="V1 vs V2 vs V3 Comparative Curve">
        </div>

        <h2 class="section-title">Walk-Forward Regime Audit: In-Sample vs Out-of-Sample</h2>
        <table>
            <thead>
                <tr>
                    <th>Regime Period</th>
                    <th>Strategy Version</th>
                    <th>Net Return (%)</th>
                    <th>Profit Factor</th>
                    <th>Win Rate (%)</th>
                    <th>Max Drawdown (%)</th>
                    <th>Total Trades</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td rowspan="3"><strong>In-Sample (2023 - 2025)</strong></td>
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
                    <td>Strategy V3 (4H + ADX>20)</td>
                    <td class="negative">{v3_is['total_return_pct']:+.2f}%</td>
                    <td>{v3_is['profit_factor']:.2f}</td>
                    <td>{v3_is['win_rate_pct']:.1f}%</td>
                    <td class="negative">{v3_is['max_drawdown_pct']:.2f}%</td>
                    <td>{v3_is['total_trades']}</td>
                </tr>
                <tr>
                    <td rowspan="3"><strong>Out-of-Sample (2026)</strong></td>
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
                <tr>
                    <td>Strategy V3 (4H + ADX>20)</td>
                    <td class="negative">{v3_oos['total_return_pct']:+.2f}%</td>
                    <td>{v3_oos['profit_factor']:.2f}</td>
                    <td>{v3_oos['win_rate_pct']:.1f}%</td>
                    <td class="negative">{v3_oos['max_drawdown_pct']:.2f}%</td>
                    <td>{v3_oos['total_trades']}</td>
                </tr>
            </tbody>
        </table>

        <div style="margin-top: 32px; font-size: 12px; color: var(--text-secondary); text-align: center;">
            Generated by CoinDCX Quantitative Research Engine | Strategy V3 Audit | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
        </div>
    </div>
</body>
</html>
"""
        with open(report_path, "w", encoding="utf-8") as f_out:
            f_out.write(html_content)
        logger.info(f"Saved V3 HTML report to: {report_path}")

    def print_comprehensive_report(self):
        """Print institutional terminal report comparing V1, V2, and V3."""
        v1_f, v2_f, v3_f = self.results_v1["full"], self.results_v2["full"], self.results_v3["full"]
        v1_is, v2_is, v3_is = self.results_v1["in_sample"], self.results_v2["in_sample"], self.results_v3["in_sample"]
        v1_oos, v2_oos, v3_oos = self.results_v1["out_of_sample"], self.results_v2["out_of_sample"], self.results_v3["out_of_sample"]

        trades_removed_v3_vs_v2 = v2_f["total_trades"] - v3_f["total_trades"]
        trades_reduction_pct_vs_v2 = (trades_removed_v3_vs_v2 / v2_f["total_trades"]) * 100.0 if v2_f["total_trades"] > 0 else 0.0

        print("\n" + "=" * 98)
        print("          STRATEGY TRI-PARTY AUDIT: V1 (BASELINE) vs V2 (4H FILTER) vs V3 (4H + ADX FILTER)")
        print("=" * 98)
        print(f"{'METRIC':<24} | {'V1 (BASELINE)':<16} | {'V2 (4H EMA200)':<16} | {'V3 (+ADX>20)':<16} | {'DELTA (V3-V2)':<16}")
        print("-" * 98)
        print(f"{'Final Equity':<24} | ₹{v1_f['final_equity']:<15,.2f} | ₹{v2_f['final_equity']:<15,.2f} | ₹{v3_f['final_equity']:<15,.2f} | {v3_f['final_equity'] - v2_f['final_equity']:<+15,.2f}")
        print(f"{'Net Return (%)':<24} | {v1_f['total_return_pct']:<+15.2f}% | {v2_f['total_return_pct']:<+15.2f}% | {v3_f['total_return_pct']:<+15.2f}% | {v3_f['total_return_pct'] - v2_f['total_return_pct']:<+15.2f}%")
        print(f"{'CAGR (%)':<24} | {v1_f['cagr_pct']:<15.2f}% | {v2_f['cagr_pct']:<15.2f}% | {v3_f['cagr_pct']:<15.2f}% | {v3_f['cagr_pct'] - v2_f['cagr_pct']:<+15.2f}%")
        print(f"{'Max Drawdown (%)':<24} | {v1_f['max_drawdown_pct']:<15.2f}% | {v2_f['max_drawdown_pct']:<15.2f}% | {v3_f['max_drawdown_pct']:<15.2f}% | {v3_f['max_drawdown_pct'] - v2_f['max_drawdown_pct']:<+15.2f}%")
        print(f"{'Profit Factor':<24} | {v1_f['profit_factor']:<15.2f} | {v2_f['profit_factor']:<15.2f} | {v3_f['profit_factor']:<15.2f} | {v3_f['profit_factor'] - v2_f['profit_factor']:<+15.2f}")
        print(f"{'Win Rate (%)':<24} | {v1_f['win_rate_pct']:<15.1f}% | {v2_f['win_rate_pct']:<15.1f}% | {v3_f['win_rate_pct']:<15.1f}% | {v3_f['win_rate_pct'] - v2_f['win_rate_pct']:<+15.1f}%")
        print(f"{'Sharpe Ratio':<24} | {v1_f['sharpe_ratio']:<15.2f} | {v2_f['sharpe_ratio']:<15.2f} | {v3_f['sharpe_ratio']:<15.2f} | {v3_f['sharpe_ratio'] - v2_f['sharpe_ratio']:<+15.2f}")
        print(f"{'Sortino Ratio':<24} | {v1_f['sortino_ratio']:<15.2f} | {v2_f['sortino_ratio']:<15.2f} | {v3_f['sortino_ratio']:<15.2f} | {v3_f['sortino_ratio'] - v2_f['sortino_ratio']:<+15.2f}")
        print(f"{'Expectancy (%/trade)':<24} | {v1_f['expectancy_pct']:<+15.2f}% | {v2_f['expectancy_pct']:<+15.2f}% | {v3_f['expectancy_pct']:<+15.2f}% | {v3_f['expectancy_pct'] - v2_f['expectancy_pct']:<+15.2f}%")
        print(f"{'Avg Win (%)':<24} | {v1_f['avg_win_pct']:<+15.2f}% | {v2_f['avg_win_pct']:<+15.2f}% | {v3_f['avg_win_pct']:<+15.2f}% | {v3_f['avg_win_pct'] - v2_f['avg_win_pct']:<+15.2f}%")
        print(f"{'Avg Loss (%)':<24} | {v1_f['avg_loss_pct']:<+15.2f}% | {v2_f['avg_loss_pct']:<+15.2f}% | {v3_f['avg_loss_pct']:<+15.2f}% | {v3_f['avg_loss_pct'] - v2_f['avg_loss_pct']:<+15.2f}%")
        print(f"{'Total Trades':<24} | {v1_f['total_trades']:<16} | {v2_f['total_trades']:<16} | {v3_f['total_trades']:<16} | -{trades_removed_v3_vs_v2} (-{trades_reduction_pct_vs_v2:.1f}%)")
        print(f"{'Market Exposure (%)':<24} | {v1_f['market_exposure_pct']:<15.1f}% | {v2_f['market_exposure_pct']:<15.1f}% | {v3_f['market_exposure_pct']:<15.1f}% | {v3_f['market_exposure_pct'] - v2_f['market_exposure_pct']:<+15.1f}%")
        print(f"{'Long Profit Factor':<24} | {v1_f['long_pf']:<15.2f} | {v2_f['long_pf']:<15.2f} | {v3_f['long_pf']:<15.2f} | {v3_f['long_pf'] - v2_f['long_pf']:<+15.2f}")
        print(f"{'Short Profit Factor':<24} | {v1_f['short_pf']:<15.2f} | {v2_f['short_pf']:<15.2f} | {v3_f['short_pf']:<15.2f} | {v3_f['short_pf'] - v2_f['short_pf']:<+15.2f}")
        print(f"{'Total Fees (₹)':<24} | ₹{v1_f['total_fees']:<15,.2f} | ₹{v2_f['total_fees']:<15,.2f} | ₹{v3_f['total_fees']:<15,.2f} | -₹{v2_f['total_fees'] - v3_f['total_fees']:<14,.2f}")
        print(f"{'Total Slippage (₹)':<24} | ₹{v1_f['total_slippage']:<15,.2f} | ₹{v2_f['total_slippage']:<15,.2f} | ₹{v3_f['total_slippage']:<15,.2f} | -₹{v2_f['total_slippage'] - v3_f['total_slippage']:<14,.2f}")
        print("=" * 98)
        print("  WALK-FORWARD AUDIT (IN-SAMPLE vs OUT-OF-SAMPLE):")
        print("  ------------------------------------------------------------------------------------------")
        print(f"  * IN-SAMPLE (2023 - 2025):")
        print(f"      V1: Return={v1_is['total_return_pct']:+.2f}%, PF={v1_is['profit_factor']:.2f}, WR={v1_is['win_rate_pct']:.1f}%, DD={v1_is['max_drawdown_pct']:.2f}%, Trades={v1_is['total_trades']}")
        print(f"      V2: Return={v2_is['total_return_pct']:+.2f}%, PF={v2_is['profit_factor']:.2f}, WR={v2_is['win_rate_pct']:.1f}%, DD={v2_is['max_drawdown_pct']:.2f}%, Trades={v2_is['total_trades']}")
        print(f"      V3: Return={v3_is['total_return_pct']:+.2f}%, PF={v3_is['profit_factor']:.2f}, WR={v3_is['win_rate_pct']:.1f}%, DD={v3_is['max_drawdown_pct']:.2f}%, Trades={v3_is['total_trades']}")
        print(f"  * OUT-OF-SAMPLE (2026):")
        print(f"      V1: Return={v1_oos['total_return_pct']:+.2f}%, PF={v1_oos['profit_factor']:.2f}, WR={v1_oos['win_rate_pct']:.1f}%, DD={v1_oos['max_drawdown_pct']:.2f}%, Trades={v1_oos['total_trades']}")
        print(f"      V2: Return={v2_oos['total_return_pct']:+.2f}%, PF={v2_oos['profit_factor']:.2f}, WR={v2_oos['win_rate_pct']:.1f}%, DD={v2_oos['max_drawdown_pct']:.2f}%, Trades={v2_oos['total_trades']}")
        print(f"      V3: Return={v3_oos['total_return_pct']:+.2f}%, PF={v3_oos['profit_factor']:.2f}, WR={v3_oos['win_rate_pct']:.1f}%, DD={v3_oos['max_drawdown_pct']:.2f}%, Trades={v3_oos['total_trades']}")
        print("=" * 98 + "\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Strategy V3 Backtesting: 4H EMA 200 + 1H ADX(14)>20 Filter")
    parser.add_argument("--data-path", "-d", type=str, default=DEFAULT_DATA_PATH, help="Path to BTCUSDT 1h CSV")
    parser.add_argument("--output-dir", "-o", type=str, default=DEFAULT_OUTPUT_DIR, help="Output directory for results")
    return parser.parse_args()


def main():
    args = parse_args()
    engine = StrategyV3Backtester(
        data_path=args.data_path,
        output_dir=args.output_dir
    )
    engine.run_all()


if __name__ == "__main__":
    main()
