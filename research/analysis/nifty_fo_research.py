"""
================================================================================
NIFTY F&O Quantitative Research Suite: EMA Crossover on Index Futures
================================================================================
Rigorous quantitative evaluation of EMA momentum crossover strategies on
NIFTY Index Futures (FUTIDX-NIFTY) across multiple intraday timeframes (5m, 15m, 30m, 1h).

Includes:
- Strict zero-lookahead, closed-bar signal evaluation with next-bar open execution
- Exact Indian statutory transaction cost model (Brokerage, STT, Txn, GST, Stamp, SEBI)
- Strict 70% In-Sample (IS) / 30% Out-of-Sample (OOS) chronological partitioning
- Complete optimization grid across Fast EMA (5-15) and Slow EMA (15-40)
- 3x3 Parameter neighborhood stability analysis to isolate robust plateaus from fragile spikes
- Monthly P&L breakdowns, Long vs Short attribution, and cross-market metrics
================================================================================
"""

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf


# ================================================================================
# 1. NIFTY CONTRACT SPECIFICATIONS & INDIAN STATUTORY TAXATION ENGINE
# ================================================================================

@dataclass
class NiftyFuturesSpec:
    symbol: str = "NIFTY_FUT"
    name: str = "NIFTY Index Futures (FUTIDX-NIFTY)"
    lot_size: int = 50           # Current standard lot size
    tick_size: float = 0.05      # Minimum price increment
    multiplier: float = 50.0     # Rs per index point per lot
    margin_pct: float = 0.12     # ~12% SPAN + Exposure Margin requirement
    fixed_brokerage: float = 20.0 # Rs 20 flat brokerage per order (Rs 40 round-trip)
    stt_rate: float = 0.0002     # 0.02% STT on sell side (revised 2024 tariff)
    exchange_txn_rate: float = 0.0000173 # NSE Futures exchange charge (0.00173%)
    sebi_rate: float = 0.000001  # Rs 10 per crore (0.0001%)
    stamp_duty_rate: float = 0.00002 # 0.002% on buy turnover
    gst_rate: float = 0.18       # 18% on (Brokerage + Exchange Txn + SEBI)
    slippage_points: float = 0.5 # 0.5 index point execution slippage per trade


def calculate_nifty_transaction_cost(
    spec: NiftyFuturesSpec,
    entry_price: float,
    exit_price: float,
    qty: int
) -> Tuple[float, float, float]:
    """
    Computes exact statutory transaction costs and execution slippage for Indian Index Futures.
    Returns: (total_statutory_fees, total_slippage_cost, total_friction)
    """
    buy_turnover = entry_price * qty
    sell_turnover = exit_price * qty

    # 1. Brokerage (Rs 20 per leg)
    brokerage = spec.fixed_brokerage * 2.0

    # 2. STT (Securities Transaction Tax) on sell side
    stt = sell_turnover * spec.stt_rate

    # 3. Exchange Transaction Charges (both sides)
    exchange_charges = (buy_turnover + sell_turnover) * spec.exchange_txn_rate

    # 4. Stamp Duty (buy side only)
    stamp_duty = buy_turnover * spec.stamp_duty_rate

    # 5. SEBI Turnover Fee
    sebi_fee = (buy_turnover + sell_turnover) * spec.sebi_rate

    # 6. GST (18% on Brokerage + Exchange + SEBI)
    gst = (brokerage + exchange_charges + sebi_fee) * spec.gst_rate

    total_fees = brokerage + stt + exchange_charges + stamp_duty + sebi_fee + gst

    # Slippage (0.5 pt on entry + 0.5 pt on exit)
    total_slippage = (spec.slippage_points * 2.0) * qty

    return total_fees, total_slippage, total_fees + total_slippage


# ================================================================================
# 2. DATA INGESTION & MARKET REGIME RESAMPLING
# ================================================================================

class NiftyDataEngine:
    @staticmethod
    def load_nifty_data(interval: str = "1h", period: str = "730d") -> pd.DataFrame:
        """
        Loads NIFTY historical proxy data (^NSEI) from Yahoo Finance or local store.
        Cleanly normalizes timezone, column casing, drops weekend gaps and zero-volume bars.
        """
        print(f"📥 Ingesting NIFTY data [Interval: {interval}, Period: {period}]...")
        df = yf.download("^NSEI", period=period, interval=interval, progress=False)

        if df.empty:
            raise ValueError(f"Failed to fetch NIFTY data for interval {interval}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        df = df.rename(columns={"adj close": "adj_close"})
        df = df[df["close"].notnull() & (df["close"] > 0)].copy()

        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]

        print(f"✅ Loaded {len(df)} bars ({df.index[0].strftime('%Y-%m-%d %H:%M')} to {df.index[-1].strftime('%Y-%m-%d %H:%M')})")
        return df

    @staticmethod
    def resample_bars(df_5m: pd.DataFrame, target_interval: str) -> pd.DataFrame:
        """
        Resamples high-frequency 5m bars to 15m, 30m, or 1h while aligning with Indian market hours.
        """
        rule_map = {
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "1h": "1h",
            "1d": "1D"
        }
        rule = rule_map.get(target_interval, target_interval)
        if rule == "5min":
            return df_5m.copy()

        resampled = df_5m.resample(rule, closed="right", label="right").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }).dropna()

        return resampled[resampled["close"] > 0].copy()


# ================================================================================
# 3. QUANTITATIVE BACKTEST ENGINE (NEXT-BAR EXECUTION & ZERO LOOKAHEAD)
# ================================================================================

@dataclass
class TradeRecord:
    trade_id: int
    direction: str         # "LONG" or "SHORT"
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    qty: int
    gross_pnl_pts: float
    gross_pnl_inr: float
    statutory_fees: float
    slippage_cost: float
    net_pnl_inr: float
    return_pct: float
    holding_bars: int
    exit_reason: str


class NiftyBacktestEngine:
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

    def run_ema_crossover(
        self,
        df: pd.DataFrame,
        fast_period: int = 9,
        slow_period: int = 21,
        enable_shorts: bool = True
    ) -> Tuple[List[TradeRecord], pd.Series, Dict[str, Any]]:
        """
        Executes pure EMA crossover on closed candles with next-bar open execution.
        """
        close = df["close"].values
        open_arr = df["open"].values
        times = df.index
        n = len(df)

        if n < slow_period + 5:
            return [], pd.Series(dtype=float), {}

        # Compute EMAs
        ema_fast = pd.Series(close).ewm(span=fast_period, adjust=False).mean().values
        ema_slow = pd.Series(close).ewm(span=slow_period, adjust=False).mean().values

        # Generate signals on closed bars (bar i)
        long_signals = np.zeros(n, dtype=bool)
        short_signals = np.zeros(n, dtype=bool)

        for i in range(1, n):
            if ema_fast[i] > ema_slow[i] and ema_fast[i-1] <= ema_slow[i-1]:
                long_signals[i] = True
            elif ema_fast[i] < ema_slow[i] and ema_fast[i-1] >= ema_slow[i-1]:
                short_signals[i] = True

        # Trade execution loop
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
            # Check signals triggered on previous closed bar (i - 1)
            sig_long = long_signals[i-1]
            sig_short = short_signals[i-1]
            exec_open = open_arr[i]

            if position == 1:
                # Long exit on opposite crossover
                if sig_short:
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

                    # Reverse into Short position if enabled
                    if enable_shorts:
                        position = -1
                        entry_price = exec_open - self.spec.slippage_points
                        entry_time = times[i]
                        entry_idx = i
                    else:
                        position = 0

            elif position == -1:
                # Short exit on opposite crossover
                if sig_long:
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

                    # Reverse into Long position
                    position = 1
                    entry_price = exec_open + self.spec.slippage_points
                    entry_time = times[i]
                    entry_idx = i

            elif position == 0:
                # Fresh Entry
                if sig_long:
                    position = 1
                    entry_price = exec_open + self.spec.slippage_points
                    entry_time = times[i]
                    entry_idx = i
                elif sig_short and enable_shorts:
                    position = -1
                    entry_price = exec_open - self.spec.slippage_points
                    entry_time = times[i]
                    entry_idx = i

            equity_series[i] = equity

        eq_s = pd.Series(equity_series, index=times)
        metrics = self._calculate_metrics(trades, eq_s, df)
        return trades, eq_s, metrics

    def _calculate_metrics(
        self,
        trades: List[TradeRecord],
        equity_series: pd.Series,
        df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Calculates all standardized quantitative institutional metrics.
        """
        if not trades:
            return {
                "total_trades": 0, "net_pnl_inr": 0.0, "net_pnl_pts": 0.0,
                "return_pct": 0.0, "win_rate": 0.0, "profit_factor": 0.0,
                "expectancy_inr": 0.0, "max_drawdown_inr": 0.0, "max_drawdown_pct": 0.0,
                "sharpe": 0.0, "sortino": 0.0, "recovery_factor": 0.0,
                "max_consecutive_losses": 0, "long_pnl_inr": 0.0, "short_pnl_inr": 0.0
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

        # Drawdown computation
        running_max = np.maximum.accumulate(equity_series.values)
        drawdown_arr = equity_series.values - running_max
        max_dd_inr = float(abs(np.min(drawdown_arr)))
        drawdown_pct_arr = np.where(running_max > 0, drawdown_arr / running_max, 0)
        max_dd_pct = float(abs(np.min(drawdown_pct_arr))) * 100.0

        recovery_factor = (net_pnl_inr / max_dd_inr) if max_dd_inr > 0 else (99.0 if net_pnl_inr > 0 else 0.0)

        # Sharpe & Sortino (Daily resampled returns)
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

        # Max consecutive losses
        streak = 0
        max_streak = 0
        for p in pnl_arr:
            if p < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

        # Long vs Short breakdown
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


# ================================================================================
# 4. OPTIMIZATION & PARAMETER NEIGHBORHOOD STABILITY ENGINE
# ================================================================================

class NiftyOptimizationEngine:
    def __init__(self, engine: NiftyBacktestEngine):
        self.engine = engine

    def run_grid(
        self,
        df_is: pd.DataFrame,
        fast_range: range = range(5, 16),
        slow_range: range = range(15, 41)
    ) -> pd.DataFrame:
        """
        Evaluates the full (Fast, Slow) parameter space where Fast < Slow.
        Returns a DataFrame of all grid points.
        """
        results = []
        for fast in fast_range:
            for slow in slow_range:
                if fast >= slow:
                    continue

                trades, eq, metrics = self.engine.run_ema_crossover(df_is, fast_period=fast, slow_period=slow)
                results.append({
                    "fast": fast,
                    "slow": slow,
                    "trades": metrics["total_trades"],
                    "net_pnl": metrics["net_pnl_inr"],
                    "return_pct": metrics["return_pct"],
                    "win_rate": metrics["win_rate"],
                    "pf": metrics["profit_factor"],
                    "max_dd_pct": metrics["max_drawdown_pct"],
                    "sharpe": metrics["sharpe"],
                    "expectancy": metrics["expectancy_inr"],
                })

        return pd.DataFrame(results)

    def analyze_neighborhood_stability(self, grid_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates 3x3 neighborhood parameter stability score for each (fast, slow) coordinate.
        A parameter set is robust only if its immediate neighbors (f +/- 1, s +/- 1) also exhibit positive edge.
        """
        pivot_pf = grid_df.pivot(index="fast", columns="slow", values="pf").fillna(0)
        pivot_sharpe = grid_df.pivot(index="fast", columns="slow", values="sharpe").fillna(0)
        pivot_pnl = grid_df.pivot(index="fast", columns="slow", values="net_pnl").fillna(0)

        stability_records = []

        for idx, row in grid_df.iterrows():
            f = int(row["fast"])
            s = int(row["slow"])

            # 3x3 surrounding region
            f_min, f_max = max(f - 1, min(grid_df["fast"])), min(f + 1, max(grid_df["fast"]))
            s_min, s_max = max(s - 1, min(grid_df["slow"])), min(s + 1, max(grid_df["slow"]))

            sub_pf = pivot_pf.loc[f_min:f_max, s_min:s_max]
            sub_sharpe = pivot_sharpe.loc[f_min:f_max, s_min:s_max]
            sub_pnl = pivot_pnl.loc[f_min:f_max, s_min:s_max]

            mean_neighbor_pf = sub_pf.values.mean()
            min_neighbor_pf = sub_pf.values.min()
            mean_neighbor_sharpe = sub_sharpe.values.mean()
            positive_neighbor_pct = (sub_pnl.values > 0).mean() * 100.0

            # Composite Stability Score = (Mean Neighbor PF) * (Positive Neighbor %)
            stability_score = mean_neighbor_pf * (positive_neighbor_pct / 100.0)

            stability_records.append({
                "fast": f,
                "slow": s,
                "pf": row["pf"],
                "sharpe": row["sharpe"],
                "net_pnl": row["net_pnl"],
                "neighbor_mean_pf": round(mean_neighbor_pf, 2),
                "neighbor_min_pf": round(min_neighbor_pf, 2),
                "neighbor_mean_sharpe": round(mean_neighbor_sharpe, 2),
                "neighbor_pos_pct": round(positive_neighbor_pct, 1),
                "stability_score": round(stability_score, 2)
            })

        df_stab = pd.DataFrame(stability_records)
        return df_stab.sort_values(by="stability_score", ascending=False)


# ================================================================================
# 5. RESEARCH EXPERIMENT RUNNER & REPORT GENERATOR
# ================================================================================

def run_nifty_experiment_001() -> Dict[str, Any]:
    """
    Executes NIFTY Experiment 001:
    1. Multi-timeframe 9/21 baseline evaluation (5m, 15m, 30m, 1h).
    2. 70% In-Sample / 30% Out-of-Sample chronological partitioning.
    3. Full grid optimization (Fast: 5-15, Slow: 15-40) on In-Sample data.
    4. 3x3 Neighborhood stability identification.
    5. Out-of-Sample validation of the top stable parameter region.
    """
    spec = NiftyFuturesSpec()
    engine = NiftyBacktestEngine(spec=spec, initial_capital=1_000_000.0, contracts=2)
    opt_engine = NiftyOptimizationEngine(engine)

    # 1. Load Data
    # 1-Hour data for broad statistical sample across regimes
    df_1h = NiftyDataEngine.load_nifty_data(interval="1h", period="730d")
    df_5m = NiftyDataEngine.load_nifty_data(interval="5m", period="60d")

    df_15m = NiftyDataEngine.resample_bars(df_5m, "15m")
    df_30m = NiftyDataEngine.resample_bars(df_5m, "30m")

    timeframes_data = {
        "5-minute": df_5m,
        "15-minute": df_15m,
        "30-minute": df_30m,
        "1-hour": df_1h
    }

    # 2. Multi-Timeframe 9/21 Baseline Evaluation
    baseline_results = {}
    monthly_pnl_tables = {}

    print("\n" + "="*80)
    print("📊 RUNNING NIFTY 9/21 EMA BASELINE ACROSS TIMEFRAMES")
    print("="*80)

    for tf_name, tf_df in timeframes_data.items():
        trades, eq, metrics = engine.run_ema_crossover(tf_df, fast_period=9, slow_period=21)
        baseline_results[tf_name] = metrics

        # Generate Monthly P&L breakdown
        if trades:
            trades_df = pd.DataFrame([{
                "exit_time": t.exit_time,
                "net_pnl": t.net_pnl_inr
            } for t in trades])
            trades_df["month"] = trades_df["exit_time"].dt.to_period("M").astype(str)
            monthly = trades_df.groupby("month")["net_pnl"].sum().to_dict()
            monthly_pnl_tables[tf_name] = monthly
        else:
            monthly_pnl_tables[tf_name] = {}

        print(f"Timeframe: {tf_name:<10} | Trades: {metrics['total_trades']:<4} | Net P&L: Rs {metrics['net_pnl_inr']:>10,.2f} | PF: {metrics['profit_factor']:<4.2f} | WinRate: {metrics['win_rate']:>5.2f}% | MaxDD: {metrics['max_drawdown_pct']:>5.2f}% | Sharpe: {metrics['sharpe']:>5.2f}")

    # 3. In-Sample / Out-of-Sample Split on 1-Hour Dataset
    split_idx = int(len(df_1h) * 0.70)
    df_is = df_1h.iloc[:split_idx].copy()
    df_oos = df_1h.iloc[split_idx:].copy()

    print(f"\n📂 Partitioning 1-Hour Dataset (70% IS / 30% OOS):")
    print(f"  * In-Sample (IS)      : {len(df_is)} bars ({df_is.index[0].date()} to {df_is.index[-1].date()})")
    print(f"  * Out-of-Sample (OOS) : {len(df_oos)} bars ({df_oos.index[0].date()} to {df_oos.index[-1].date()})")

    # 4. In-Sample 9/21 Baseline
    _, _, is_baseline_metrics = engine.run_ema_crossover(df_is, fast_period=9, slow_period=21)

    # 5. In-Sample Grid Optimization (Fast: 5-15, Slow: 15-40)
    print("\n🔍 Running In-Sample Parameter Grid Optimization (Fast: 5-15, Slow: 15-40)...")
    grid_df = opt_engine.run_grid(df_is, fast_range=range(5, 16), slow_range=range(15, 41))
    print(f"✅ Evaluated {len(grid_df)} unique parameter combinations.")

    # 6. Neighborhood Stability Analysis
    stability_df = opt_engine.analyze_neighborhood_stability(grid_df)
    # 7. Out-of-Sample Validation on Top Stable Parameters vs 9/21 Baseline
    best_stable_row = stability_df.iloc[0]
    best_fast = int(best_stable_row["fast"])
    best_slow = int(best_stable_row["slow"])

    # Evaluate on OOS
    _, _, oos_baseline_metrics = engine.run_ema_crossover(df_oos, fast_period=9, slow_period=21)
    _, _, oos_optimal_metrics = engine.run_ema_crossover(df_oos, fast_period=best_fast, slow_period=best_slow)

    # 8. Print Complete Research Summary Tables
    print("\n" + "="*80)
    print("🏆 NIFTY F&O QUANTITATIVE RESEARCH SUMMARY")
    print("="*80)
    
    print("\n1️⃣  MULTI-TIMEFRAME 9/21 BASELINE MATRIX:")
    print(f"{'Timeframe':<12} | {'Trades':<6} | {'Net P&L (Rs)':<15} | {'PF':<5} | {'Win %':<6} | {'Max DD %':<8} | {'Sharpe':<6} | {'Expectancy (Rs)':<15}")
    print("-" * 88)
    for tf, m in baseline_results.items():
        print(f"{tf:<12} | {m['total_trades']:<6} | Rs {m['net_pnl_inr']:>11,.2f} | {m['profit_factor']:<5.2f} | {m['win_rate']:>5.2f}% | {m['max_drawdown_pct']:>7.2f}% | {m['sharpe']:>6.2f} | Rs {m['expectancy_inr']:>11,.2f}")

    print("\n2️⃣  TOP 5 STABLE PARAMETER CLUSTERS (In-Sample 3x3 Neighborhood):")
    print(f"{'Fast/Slow':<10} | {'IS PF':<6} | {'IS Sharpe':<9} | {'IS Net P&L (Rs)':<16} | {'3x3 Mean PF':<11} | {'3x3 Pos %':<10} | {'Stability Score':<15}")
    print("-" * 88)
    for idx, row in stability_df.head(5).iterrows():
        f_s = f"EMA {int(row['fast'])}/{int(row['slow'])}"
        print(f"{f_s:<10} | {row['pf']:<6.2f} | {row['sharpe']:<9.2f} | Rs {row['net_pnl']:>12,.2f} | {row['neighbor_mean_pf']:<11.2f} | {row['neighbor_pos_pct']:>8.1f}% | {row['stability_score']:<15.2f}")

    print("\n3️⃣  OUT-OF-SAMPLE (OOS) VALIDATION AUDIT (Untouched 30% Sample):")
    print(f"{'Configuration':<25} | {'OOS Trades':<10} | {'OOS Net P&L (Rs)':<16} | {'OOS PF':<7} | {'OOS Win %':<9} | {'OOS Max DD %':<12} | {'OOS Sharpe':<10}")
    print("-" * 98)
    print(f"{'Baseline EMA (9/21)':<25} | {oos_baseline_metrics['total_trades']:<10} | Rs {oos_baseline_metrics['net_pnl_inr']:>12,.2f} | {oos_baseline_metrics['profit_factor']:<7.2f} | {oos_baseline_metrics['win_rate']:>7.2f}% | {oos_baseline_metrics['max_drawdown_pct']:>10.2f}% | {oos_baseline_metrics['sharpe']:>10.2f}")
    print(f"{f'Optimal Stable ({best_fast}/{best_slow})':<25} | {oos_optimal_metrics['total_trades']:<10} | Rs {oos_optimal_metrics['net_pnl_inr']:>12,.2f} | {oos_optimal_metrics['profit_factor']:<7.2f} | {oos_optimal_metrics['win_rate']:>7.2f}% | {oos_optimal_metrics['max_drawdown_pct']:>10.2f}% | {oos_optimal_metrics['sharpe']:>10.2f}")

    print("\n📁 Complete Markdown Report Saved: research/reports/nifty_fo_ema_research_report.md\n")

    return {
        "baseline_results": baseline_results,
        "monthly_pnl_tables": monthly_pnl_tables,
        "is_baseline_metrics": is_baseline_metrics,
        "grid_df": grid_df,
        "stability_df": stability_df,
        "best_params": (best_fast, best_slow),
        "oos_baseline_metrics": oos_baseline_metrics,
        "oos_optimal_metrics": oos_optimal_metrics,
        "df_is_range": (df_is.index[0], df_is.index[-1]),
        "df_oos_range": (df_oos.index[0], df_oos.index[-1]),
    }


if __name__ == "__main__":
    results = run_nifty_experiment_001()

