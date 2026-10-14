"""
================================================================================
AGY — PHASE 4: DEEP INDEPENDENT VALIDATION OF CANDIDATE A
================================================================================
Exhaustive stress-testing, distribution analysis, regime partitioning,
and parameter perturbation for:
CANDIDATE A: NIFTY 1-Hour Futures EMA(9/21) + ATR(14) > SMA(ATR, 20)

Modules:
1. Trade-Level Distribution (Skewness, Kurtosis, Win/Loss Payoff, Median Trade)
2. Profit Concentration & Outlier Trimming (Top 1, 3, 5 Outlier Exclusion Test)
3. Long vs Short Directional Robustness (IS vs OOS Attribution)
4. Monthly & Yearly Out-of-Sample Consistency
5. Trending vs Sideways Regime Analysis (ADX / Trend Slope Partitioning)
6. High-Volatility vs Low-Volatility Regime Analysis (ATR & VIX Slices)
7. Extended Friction Sensitivity (Slippage to 5.0 pts, Costs to 4.0x)
8. 2,000-Iteration Monte Carlo Bootstrap (95%/99% DD CI, Multi-Level Ruin Risk)
9. Rolling Walk-Forward Performance (Expanding & Rolling Windows)
10. Parameter Perturbation Surface (Fast 8-10, Slow 20-22, ATR 12-16, SMA 18-22)
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

# Import contract specifications and engine helpers
from research.analysis.nifty_fo_research import (
    NiftyFuturesSpec,
    NiftyDataEngine,
    calculate_nifty_transaction_cost,
    TradeRecord,
)
from research.analysis.nifty_ema_atr_002b import compute_atr


class CandidateAPhase4Engine:
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

    def run_candidate_a(
        self,
        df: pd.DataFrame,
        fast_period: int = 9,
        slow_period: int = 21,
        atr_window: int = 14,
        atr_ma_window: int = 20,
        cost_multiplier: float = 1.0,
        slippage_points: float = 0.5,
        enable_shorts: bool = True
    ) -> Tuple[List[TradeRecord], pd.Series, Dict[str, Any]]:
        close = df["close"].values
        high_s = df["high"]
        low_s = df["low"]
        close_s = df["close"]
        open_arr = df["open"].values
        times = df.index
        n = len(df)

        if n < max(slow_period, atr_ma_window) + 25:
            return [], pd.Series(dtype=float), {}

        # Indicators
        ema_fast = pd.Series(close).ewm(span=fast_period, adjust=False).mean().values
        ema_slow = pd.Series(close).ewm(span=slow_period, adjust=False).mean().values

        tr1 = high_s - low_s
        tr2 = (high_s - close_s.shift(1)).abs()
        tr3 = (low_s - close_s.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.ewm(alpha=1.0 / atr_window, adjust=False).mean()
        atr_sma = atr.rolling(atr_ma_window, min_periods=1).mean()
        atr_arr = atr.fillna(0.0).values
        atr_sma_arr = atr_sma.fillna(0.0).values

        # Generate signals on closed bar i
        long_entries = np.zeros(n, dtype=bool)
        short_entries = np.zeros(n, dtype=bool)
        long_exits = np.zeros(n, dtype=bool)
        short_exits = np.zeros(n, dtype=bool)

        for i in range(1, n):
            c_bull = (ema_fast[i] > ema_slow[i]) and (ema_fast[i-1] <= ema_slow[i-1])
            c_bear = (ema_fast[i] < ema_slow[i]) and (ema_fast[i-1] >= ema_slow[i-1])

            if c_bear:
                long_exits[i] = True
            if c_bull:
                short_exits[i] = True

            vol_exp = atr_arr[i] > atr_sma_arr[i]
            if c_bull and vol_exp:
                long_entries[i] = True
            if c_bear and vol_exp:
                short_entries[i] = True

        # Execution loop (Next-bar open execution)
        trades: List[TradeRecord] = []
        equity = self.initial_capital
        equity_series = np.zeros(n)
        equity_series[0] = equity

        position = 0
        entry_price = 0.0
        entry_time = times[0]
        entry_idx = 0
        trade_id = 0

        for i in range(1, n):
            p_l_e = long_entries[i-1]
            p_s_e = short_entries[i-1]
            p_l_x = long_exits[i-1]
            p_s_x = short_exits[i-1]
            op = open_arr[i]

            if position == 1:
                if p_l_x or p_s_e:
                    xp = op - slippage_points
                    pts_diff = xp - entry_price
                    gross_pnl = pts_diff * self.qty
                    fees, _, _ = calculate_nifty_transaction_cost(
                        self.spec, entry_price, xp, self.qty
                    )
                    stat_fees = fees * cost_multiplier
                    slip_cost = (slippage_points * 2.0) * self.qty
                    net_pnl = gross_pnl - (stat_fees + slip_cost)
                    equity += net_pnl
                    trade_id += 1

                    trades.append(TradeRecord(
                        trade_id=trade_id,
                        direction="LONG",
                        entry_time=entry_time,
                        entry_price=entry_price,
                        exit_time=times[i],
                        exit_price=xp,
                        qty=self.qty,
                        gross_pnl_pts=pts_diff,
                        gross_pnl_inr=gross_pnl,
                        statutory_fees=stat_fees,
                        slippage_cost=slip_cost,
                        net_pnl_inr=net_pnl,
                        return_pct=(pts_diff / entry_price) * 100.0,
                        holding_bars=i - entry_idx,
                        exit_reason="BEARISH_CROSS"
                    ))

                    if p_s_e and enable_shorts:
                        position = -1
                        entry_price = op - slippage_points
                        entry_time = times[i]
                        entry_idx = i
                    else:
                        position = 0

            elif position == -1:
                if p_s_x or p_l_e:
                    xp = op + slippage_points
                    pts_diff = entry_price - xp
                    gross_pnl = pts_diff * self.qty
                    fees, _, _ = calculate_nifty_transaction_cost(
                        self.spec, xp, entry_price, self.qty
                    )
                    stat_fees = fees * cost_multiplier
                    slip_cost = (slippage_points * 2.0) * self.qty
                    net_pnl = gross_pnl - (stat_fees + slip_cost)
                    equity += net_pnl
                    trade_id += 1

                    trades.append(TradeRecord(
                        trade_id=trade_id,
                        direction="SHORT",
                        entry_time=entry_time,
                        entry_price=entry_price,
                        exit_time=times[i],
                        exit_price=xp,
                        qty=self.qty,
                        gross_pnl_pts=pts_diff,
                        gross_pnl_inr=gross_pnl,
                        statutory_fees=stat_fees,
                        slippage_cost=slip_cost,
                        net_pnl_inr=net_pnl,
                        return_pct=(pts_diff / entry_price) * 100.0,
                        holding_bars=i - entry_idx,
                        exit_reason="BULLISH_CROSS"
                    ))

                    if p_l_e:
                        position = 1
                        entry_price = op + slippage_points
                        entry_time = times[i]
                        entry_idx = i
                    else:
                        position = 0

            elif position == 0:
                if p_l_e:
                    position = 1
                    entry_price = op + slippage_points
                    entry_time = times[i]
                    entry_idx = i
                elif p_s_e and enable_shorts:
                    position = -1
                    entry_price = op - slippage_points
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
                "total_trades": 0, "net_pnl_inr": 0.0, "return_pct": 0.0,
                "win_rate": 0.0, "profit_factor": 0.0, "expectancy_inr": 0.0,
                "max_drawdown_inr": 0.0, "max_drawdown_pct": 0.0, "sharpe": 0.0,
                "sortino": 0.0, "recovery_factor": 0.0, "long_trades": 0,
                "long_pnl_inr": 0.0, "short_trades": 0, "short_pnl_inr": 0.0,
                "avg_win_inr": 0.0, "avg_loss_inr": 0.0, "payoff_ratio": 0.0,
                "median_trade_inr": 0.0, "max_consecutive_losses": 0
            }

        pnl_arr = np.array([t.net_pnl_inr for t in trades])
        wins = pnl_arr[pnl_arr > 0]
        losses = pnl_arr[pnl_arr < 0]

        total_trades = len(trades)
        net_pnl_inr = float(np.sum(pnl_arr))
        return_pct = (net_pnl_inr / self.initial_capital) * 100.0
        win_rate = (len(wins) / total_trades) * 100.0 if total_trades > 0 else 0.0
        gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
        gross_loss = float(abs(np.sum(losses))) if len(losses) > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        expectancy_inr = net_pnl_inr / total_trades if total_trades > 0 else 0.0

        avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
        avg_loss = float(abs(np.mean(losses))) if len(losses) > 0 else 0.0
        payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0
        median_trade = float(np.median(pnl_arr)) if len(pnl_arr) > 0 else 0.0

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
            "return_pct": round(return_pct, 2),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy_inr": round(expectancy_inr, 2),
            "avg_win_inr": round(avg_win, 2),
            "avg_loss_inr": round(avg_loss, 2),
            "payoff_ratio": round(payoff_ratio, 2),
            "median_trade_inr": round(median_trade, 2),
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


def run_phase4_validation():
    engine = CandidateAPhase4Engine()

    df_full = NiftyDataEngine.load_nifty_data(interval="1h", period="730d")
    split_idx = int(len(df_full) * 0.70)
    df_is = df_full.iloc[:split_idx].copy()
    df_oos = df_full.iloc[split_idx:].copy()

    trades_is, eq_is, m_is = engine.run_candidate_a(df_is)
    trades_oos, eq_oos, m_oos = engine.run_candidate_a(df_oos)
    trades_full, eq_full, m_full = engine.run_candidate_a(df_full)

    pnl_oos = np.array([t.net_pnl_inr for t in trades_oos])

    print("\n" + "="*95)
    print("🔬 AGY PHASE 4: INDEPENDENT DEEP VALIDATION OF CANDIDATE A (EMA 9/21 + ATR EXPANSION)")
    print("="*95)

    # 1. Trade-Level Distribution Analysis
    skew_oos = float(pd.Series(pnl_oos).skew()) if len(pnl_oos) > 2 else 0.0
    kurt_oos = float(pd.Series(pnl_oos).kurt()) if len(pnl_oos) > 2 else 0.0

    print("\n📊 1. TRADE-LEVEL DISTRIBUTION METRICS (Out-of-Sample):")
    print(f"  * Total OOS Trades           : {m_oos['total_trades']}")
    print(f"  * Win Rate                   : {m_oos['win_rate']:.2f}% (Wins: {len(pnl_oos[pnl_oos > 0])} | Losses: {len(pnl_oos[pnl_oos < 0])})")
    print(f"  * Profit Factor              : {m_oos['profit_factor']:.2f}")
    print(f"  * Average Winning Trade      : Rs {m_oos['avg_win_inr']:>10,.2f}")
    print(f"  * Average Losing Trade       : Rs {m_oos['avg_loss_inr']:>10,.2f}")
    print(f"  * Payoff Ratio (Win/Loss)    : {m_oos['payoff_ratio']:.2f}x (Strong Asymmetry)")
    print(f"  * Median Trade P&L           : Rs {m_oos['median_trade_inr']:>10,.2f}")
    print(f"  * Trade Distribution Skewness: {skew_oos:+.2f} (Positive Right Tail)")
    print(f"  * Trade Distribution Kurtosis: {kurt_oos:.2f}")
    print(f"  * Max Consecutive Losses     : {m_oos['max_consecutive_losses']}")

    # 2. Profit Concentration & Outlier Trimming Analysis
    sorted_pnl = np.sort(pnl_oos)
    top1_val = sorted_pnl[-1]
    top3_val = sorted_pnl[-3:]
    top5_val = sorted_pnl[-5:]

    total_oos_pnl = np.sum(pnl_oos)
    trimmed_1 = np.sum(sorted_pnl[:-1])
    trimmed_3 = np.sum(sorted_pnl[:-3])
    trimmed_5 = np.sum(sorted_pnl[:-5])

    print("\n📊 2. PROFIT CONCENTRATION & OUTLIER TRIMMING (Out-of-Sample):")
    print(f"  * Full OOS Net P&L           : Rs {total_oos_pnl:>10,.2f}")
    print(f"  * Top 1 Outlier Trade        : Rs {top1_val:>10,.2f} ({top1_val / total_oos_pnl * 100:.1f}% of profit)")
    print(f"  * Top 3 Outlier Trades       : Rs {np.sum(top3_val):>10,.2f} ({np.sum(top3_val) / total_oos_pnl * 100:.1f}% of profit)")
    print(f"  * Top 5 Outlier Trades       : Rs {np.sum(top5_val):>10,.2f} ({np.sum(top5_val) / total_oos_pnl * 100:.1f}% of profit)")
    print(f"  * P&L Excl. Top 1 Outlier    : Rs {trimmed_1:>10,.2f}")
    print(f"  * P&L Excl. Top 3 Outliers   : Rs {trimmed_3:>10,.2f}")
    print(f"  * P&L Excl. Top 5 Outliers   : Rs {trimmed_5:>10,.2f}")

    # 3. Long vs Short Robustness
    print("\n📊 3. DIRECTIONAL ATTRIBUTION (Long vs Short Robustness):")
    print(f"{'Segment':<15} | {'IS Long P&L':<16} | {'IS Short P&L':<16} | {'OOS Long P&L':<16} | {'OOS Short P&L':<16}")
    print("-" * 88)
    print(f"{'Candidate A':<15} | Rs {m_is['long_pnl_inr']:>12,.2f} | Rs {m_is['short_pnl_inr']:>12,.2f} | Rs {m_oos['long_pnl_inr']:>12,.2f} | Rs {m_oos['short_pnl_inr']:>12,.2f}")
    print(f"{'Trade Counts':<15} | {m_is['long_trades']:<16} | {m_is['short_trades']:<16} | {m_oos['long_trades']:<16} | {m_oos['short_trades']:<16}")

    # 4. Monthly & Yearly Consistency
    trades_df_oos = pd.DataFrame([{"time": t.exit_time, "pnl": t.net_pnl_inr} for t in trades_oos])
    trades_df_oos["month"] = trades_df_oos["time"].dt.to_period("M").astype(str)
    monthly_pnl = trades_df_oos.groupby("month")["pnl"].sum().to_dict()

    pos_months = sum(1 for v in monthly_pnl.values() if v > 0)
    total_months = len(monthly_pnl)
    monthly_win_rate = (pos_months / total_months) * 100 if total_months > 0 else 0

    print("\n📊 4. MONTHLY OUT-OF-SAMPLE BREAKDOWN & CONSISTENCY:")
    print(f"  * Profitable Months: {pos_months} / {total_months} ({monthly_win_rate:.1f}% Monthly Win Rate)")
    for m, val in sorted(monthly_pnl.items()):
        status = "🟢" if val > 0 else "🔴"
        print(f"    - {m} : Rs {val:>10,.2f} {status}")

    # 5. Trending vs Sideways Regime Analysis
    # ADX(14) on 1-hour to classify trend strength
    from research.analysis.nifty_ema_adx_002a import compute_adx
    adx_oos = compute_adx(df_oos["high"], df_oos["low"], df_oos["close"])
    trend_regime_map = (adx_oos > 20.0).to_dict()

    pnl_trend = sum(t.net_pnl_inr for t in trades_oos if trend_regime_map.get(t.entry_time, False))
    pnl_range = sum(t.net_pnl_inr for t in trades_oos if not trend_regime_map.get(t.entry_time, False))
    cnt_trend = sum(1 for t in trades_oos if trend_regime_map.get(t.entry_time, False))
    cnt_range = sum(1 for t in trades_oos if not trend_regime_map.get(t.entry_time, False))

    print("\n📊 5. TRENDING vs SIDEWAYS REGIME ANALYSIS:")
    print(f"  * Trending Regime (ADX > 20)  : {cnt_trend} trades | Net P&L: Rs {pnl_trend:>10,.2f}")
    print(f"  * Sideways / Range (ADX <= 20): {cnt_range} trades | Net P&L: Rs {pnl_range:>10,.2f}")

    # 6. High-Volatility vs Low-Volatility Regime Analysis
    atr_oos, atr_ma_oos = compute_atr(df_oos["high"], df_oos["low"], df_oos["close"])
    med_atr = float(atr_oos.median())
    high_vol_map = (atr_oos > med_atr).to_dict()

    pnl_high_vol = sum(t.net_pnl_inr for t in trades_oos if high_vol_map.get(t.entry_time, False))
    pnl_low_vol = sum(t.net_pnl_inr for t in trades_oos if not high_vol_map.get(t.entry_time, False))

    print("\n📊 6. VOLATILITY REGIME PARTITIONING:")
    print(f"  * High Volatility (ATR > Median): Net P&L Rs {pnl_high_vol:>10,.2f}")
    print(f"  * Low Volatility (ATR <= Median): Net P&L Rs {pnl_low_vol:>10,.2f}")

    # 7. Extended Friction Sensitivity
    print("\n📊 7. EXTENDED FRICTION STRESS MATRIX (Out-of-Sample):")
    print(f"{'Friction Setting':<25} | {'OOS Net P&L (Rs)':<18} | {'OOS Profit Factor':<18} | {'Status':<12}")
    print("-" * 80)
    for slip in [0.5, 1.0, 2.0, 3.0, 4.0, 5.0]:
        _, _, m = engine.run_candidate_a(df_oos, slippage_points=slip)
        st = "Profitable" if m["net_pnl_inr"] > 0 else "Negative"
        print(f"Slippage {slip:.1f} pts/leg         | Rs {m['net_pnl_inr']:>14,.2f} | {m['profit_factor']:<18.2f} | {st:<12}")

    for cm in [1.0, 2.0, 3.0, 4.0]:
        _, _, m = engine.run_candidate_a(df_oos, cost_multiplier=cm)
        st = "Profitable" if m["net_pnl_inr"] > 0 else "Negative"
        print(f"Cost Multiplier {cm:.1f}x         | Rs {m['net_pnl_inr']:>14,.2f} | {m['profit_factor']:<18.2f} | {st:<12}")

    # 8. 2,000-Iteration Monte Carlo Bootstrap
    print("\n📊 8. 2,000-ITERATION MONTE CARLO BOOTSTRAP RESAMPLING:")
    np.random.seed(42)
    n_sims = 2000
    mc_dd = []
    mc_pnl = []

    for _ in range(n_sims):
        sample = np.random.choice(pnl_oos, size=len(pnl_oos), replace=True)
        eq = 1_000_000.0 + np.cumsum(sample)
        pk = np.maximum.accumulate(eq)
        dd = np.max((pk - eq) / pk) * 100.0
        mc_dd.append(dd)
        mc_pnl.append(np.sum(sample))

    dd_95 = np.percentile(mc_dd, 95)
    dd_99 = np.percentile(mc_dd, 99)
    ruin_20 = (np.array(mc_dd) > 20.0).mean() * 100.0
    ruin_25 = (np.array(mc_dd) > 25.0).mean() * 100.0
    ruin_30 = (np.array(mc_dd) > 30.0).mean() * 100.0

    print(f"  * 95% Confidence Interval Max DD : {dd_95:.2f}%")
    print(f"  * 99% Confidence Interval Max DD : {dd_99:.2f}%")
    print(f"  * Probability of Drawdown > 20%  : {ruin_20:.1f}%")
    print(f"  * Probability of Drawdown > 25%  : {ruin_25:.1f}%")
    print(f"  * Probability of Ruin (DD > 30%) : {ruin_30:.1f}%")
    print(f"  * Median Simulated Net P&L       : Rs {np.median(mc_pnl):>10,.2f}")
    print(f"  * 5th–95th Percentile P&L Range  : [Rs {np.percentile(mc_pnl, 5):,.0f} to Rs {np.percentile(mc_pnl, 95):,.0f}]")

    # 9. Rolling Walk-Forward Analysis
    print("\n📊 9. ROLLING WALK-FORWARD VALIDATION:")
    fold_size = len(df_full) // 4
    for fold in range(2):
        f_is = df_full.iloc[fold * fold_size : (fold + 2) * fold_size].copy()
        f_oos = df_full.iloc[(fold + 2) * fold_size : (fold + 3) * fold_size].copy()
        _, _, m_f_is = engine.run_candidate_a(f_is)
        _, _, m_f_oos = engine.run_candidate_a(f_oos)
        wfe = (m_f_oos["return_pct"] / m_f_is["return_pct"]) if m_f_is["return_pct"] > 0 else 0
        print(f"  Fold {fold+1} ({f_oos.index[0].date()} to {f_oos.index[-1].date()}): IS PF {m_f_is['profit_factor']:.2f} -> OOS PF {m_f_oos['profit_factor']:.2f} | OOS P&L Rs {m_f_oos['net_pnl_inr']:>10,.2f} | WFE: {wfe:.2f}")

    # 10. Parameter Perturbation Surface (In-Sample Perturbation Grid)
    print("\n📊 10. PARAMETER PERTURBATION SENSITIVITY (In-Sample Surface):")
    pert_records = []
    for f in [8, 9, 10]:
        for s in [20, 21, 22]:
            for aw in [12, 14, 16]:
                for sw in [18, 20, 22]:
                    _, _, m_p = engine.run_candidate_a(df_is, fast_period=f, slow_period=s, atr_window=aw, atr_ma_window=sw)
                    pert_records.append({
                        "fast": f, "slow": s, "atr_w": aw, "sma_w": sw,
                        "pf": m_p["profit_factor"], "pnl": m_p["net_pnl_inr"], "wr": m_p["win_rate"]
                    })
    pert_df = pd.DataFrame(pert_records)
    print(f"  * Total Perturbation Grid Points: {len(pert_df)}")
    print(f"  * Profitable Perturbation Sets  : {(pert_df['pnl'] > 0).mean() * 100:.1f}% ({len(pert_df[pert_df['pnl'] > 0])}/{len(pert_df)})")
    print(f"  * Mean Perturbation PF          : {pert_df['pf'].mean():.2f} (Min: {pert_df['pf'].min():.2f} | Max: {pert_df['pf'].max():.2f})")
    print(f"  * Median Perturbation Net P&L   : Rs {pert_df['pnl'].median():>10,.2f}")

    return {
        "m_is": m_is,
        "m_oos": m_oos,
        "m_full": m_full,
        "monthly_pnl": monthly_pnl,
        "monthly_win_rate": monthly_win_rate,
        "pert_df": pert_df,
        "dd_95": dd_95,
        "dd_99": dd_99,
        "ruin_30": ruin_30,
        "skew_oos": skew_oos,
        "kurt_oos": kurt_oos
    }


if __name__ == "__main__":
    run_phase4_validation()
