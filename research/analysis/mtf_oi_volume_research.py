"""
================================================================================
Comprehensive MTF Robustness & OI + Volume Research Engine
================================================================================
Executes the full 13-phase quantitative study on Multi-Timeframe (Daily + 1H):
  - Phase 1: Frozen MTF_BASELINE_V1
  - Phase 2: 60% IS / 20% Val / 20% OOS degradation metrics
  - Phase 3: Parameter perturbation (Fast ±1..2, Slow ±2..5) -> Robustness vs Fragility
  - Phase 4: Cost (1x..3x) & Slippage (1..3 ticks) stress test
  - Phase 5: Trade concentration (Top 1, Top 3, Top 5, Median, Mean)
  - Phase 6: Regime testing (Bull, Bear, Sideways, High/Low Volatility)
  - Phase 7-9: Standalone Price + OI + Volume quadrant statistical analysis
  - Phase 10-13: Incremental filter evaluation (Baseline vs +Vol vs +OI vs +OI+Vol)
"""

import math
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import yfinance as yf

from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import CONTRACT_SPECS, DataHandler


# ==============================================================================
# PHASE 1: FROZEN MTF_BASELINE_V1 SPECIFICATIONS
# ==============================================================================
MTF_BASELINE_V1 = {
    "GC=F": {
        "name": "Gold Futures (COMEX)",
        "fast_ema": 9,
        "slow_ema": 21,
        "daily_filter": "d_trend_ema9_21",
        "filter_name": "Daily Trend: D_EMA 9 > 21",
        "multiplier": 100.0,
        "margin_pct": 0.10,
        "fixed_fee": 2.50,
        "tick_size": 0.10,
    },
    "SI=F": {
        "name": "Silver Futures (COMEX)",
        "fast_ema": 20,
        "slow_ema": 50,
        "daily_filter": "d_trend_ema9_21",
        "filter_name": "Daily Trend: D_EMA 9 > 21",
        "multiplier": 5000.0,
        "margin_pct": 0.15,
        "fixed_fee": 2.50,
        "tick_size": 0.005,
    },
    "CL=F": {
        "name": "Crude Oil (WTI)",
        "fast_ema": 9,
        "slow_ema": 21,
        "daily_filter": "d_trend_close_ema50",
        "filter_name": "Daily Trend: Close > D_EMA 50",
        "multiplier": 1000.0,
        "margin_pct": 0.12,
        "fixed_fee": 2.00,
        "tick_size": 0.01,
    },
    "BZ=F": {
        "name": "Brent Crude",
        "fast_ema": 20,
        "slow_ema": 50,
        "daily_filter": "d_trend_close_ema50",
        "filter_name": "Daily Trend: Close > D_EMA 50",
        "multiplier": 1000.0,
        "margin_pct": 0.12,
        "fixed_fee": 2.00,
        "tick_size": 0.01,
    },
    "NG=F": {
        "name": "Natural Gas",
        "fast_ema": 9,
        "slow_ema": 21,
        "daily_filter": "d_trend_close_ema50",
        "filter_name": "Daily Trend: Close > D_EMA 50",
        "multiplier": 10000.0,
        "margin_pct": 0.20,
        "fixed_fee": 2.00,
        "tick_size": 0.001,
    },
}


def load_and_enrich_data(symbol: str) -> pd.DataFrame:
    """Loads 1H and Daily data, aligns Daily trend, and computes Volume & OI indicators."""
    # 1. 1-Hour Intraday
    df_1h = yf.download(symbol, period="730d", interval="1h", progress=False)
    if isinstance(df_1h.columns, pd.MultiIndex):
        df_1h.columns = [c[0] for c in df_1h.columns]
    df_1h = df_1h.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    df_1h = df_1h[df_1h["close"].notnull() & (df_1h["close"] > 0)].copy()
    df_1h.index = pd.to_datetime(df_1h.index)
    if df_1h.index.tz is not None:
        df_1h.index = df_1h.index.tz_localize(None)
    df_1h = df_1h.sort_index()

    # 2. Daily Data
    df_daily = yf.download(symbol, period="3y", interval="1d", progress=False)
    if isinstance(df_daily.columns, pd.MultiIndex):
        df_daily.columns = [c[0] for c in df_daily.columns]
    df_daily = df_daily.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    df_daily = df_daily[df_daily["close"].notnull() & (df_daily["close"] > 0)].copy()
    df_daily.index = pd.to_datetime(df_daily.index)
    if df_daily.index.tz is not None:
        df_daily.index = df_daily.index.tz_localize(None)
    df_daily = df_daily.sort_index()

    # Daily trend indicators (Strictly shifted by 1 to eliminate lookahead)
    d_close = df_daily["close"]
    df_daily["d_ema9"] = d_close.ewm(span=9, adjust=False).mean()
    df_daily["d_ema21"] = d_close.ewm(span=21, adjust=False).mean()
    df_daily["d_ema50"] = d_close.ewm(span=50, adjust=False).mean()
    df_daily["d_sma200"] = d_close.rolling(200).mean()

    df_daily["d_trend_ema9_21"] = (df_daily["d_ema9"] > df_daily["d_ema21"]).shift(1)
    df_daily["d_trend_close_ema50"] = (d_close > df_daily["d_ema50"]).shift(1)
    df_daily["d_trend_close_sma200"] = (d_close > df_daily["d_sma200"]).shift(1)

    # Align Daily Trend with 1H bars
    df_1h["date_key"] = df_1h.index.normalize()
    daily_subset = df_daily[["d_trend_ema9_21", "d_trend_close_ema50", "d_trend_close_sma200"]].copy()
    df_1h = df_1h.join(daily_subset, on="date_key")
    df_1h["d_trend_ema9_21"] = df_1h["d_trend_ema9_21"].ffill().fillna(False)
    df_1h["d_trend_close_ema50"] = df_1h["d_trend_close_ema50"].ffill().fillna(False)
    df_1h["d_trend_close_sma200"] = df_1h["d_trend_close_sma200"].ffill().fillna(False)

    # 3. Volume Indicators (1-Hour)
    vol = df_1h["volume"]
    vol_sma20 = vol.rolling(20).mean()
    df_1h["vol_sma20"] = vol_sma20
    df_1h["rvol"] = vol / (vol_sma20 + 1e-6)
    df_1h["vol_change_pct"] = vol.pct_change() * 100.0

    # 4. Open Interest (OI) Approximation & Dynamic Flow
    # Approximates daily/intraday futures OI dynamics from volume turnover & cumulative flow
    daily_vol = df_daily["volume"]
    df_daily["d_obv"] = (np.sign(df_daily["close"].diff()) * daily_vol).fillna(0).cumsum()
    df_daily["d_oi_trend"] = (df_daily["d_obv"] > df_daily["d_obv"].rolling(10).mean()).shift(1)
    
    df_1h = df_1h.join(df_daily[["d_oi_trend"]], on="date_key")
    df_1h["d_oi_trend"] = df_1h["d_oi_trend"].ffill().fillna(False)

    # Price & Volume changes
    df_1h["price_change"] = df_1h["close"].diff()
    df_1h["vol_change"] = df_1h["volume"].diff()

    # 4 Quadrant Classification
    p_up = df_1h["price_change"] > 0
    v_up = df_1h["vol_change"] > 0
    oi_up = df_1h["d_oi_trend"]

    quadrants = []
    for i in range(len(df_1h)):
        if p_up.iloc[i] and oi_up.iloc[i] and v_up.iloc[i]:
            quadrants.append("1. Price_Up + OI_Up + Vol_Up (Long Buildup)")
        elif p_up.iloc[i] and (not oi_up.iloc[i]) and v_up.iloc[i]:
            quadrants.append("2. Price_Up + OI_Down + Vol_Up (Short Covering)")
        elif (not p_up.iloc[i]) and oi_up.iloc[i] and v_up.iloc[i]:
            quadrants.append("3. Price_Down + OI_Up + Vol_Up (Short Buildup)")
        elif (not p_up.iloc[i]) and (not oi_up.iloc[i]) and v_up.iloc[i]:
            quadrants.append("4. Price_Down + OI_Down + Vol_Up (Long Unwinding)")
        else:
            quadrants.append("5. Low/Normal Volume")

    df_1h["poi_quadrant"] = quadrants

    # Volatility & Market Regimes
    tr = np.maximum(
        df_1h["high"] - df_1h["low"],
        np.maximum(
            (df_1h["high"] - df_1h["close"].shift(1)).abs(),
            (df_1h["low"] - df_1h["close"].shift(1)).abs()
        )
    )
    df_1h["atr14"] = tr.rolling(14).mean()
    df_1h["atr_pct"] = (df_1h["atr14"] / df_1h["close"]) * 100.0
    vol_70th = df_1h["atr_pct"].quantile(0.70)
    vol_30th = df_1h["atr_pct"].quantile(0.30)

    regimes = []
    for i in range(len(df_1h)):
        ap = df_1h["atr_pct"].iloc[i]
        d_tr = df_1h["d_trend_close_ema50"].iloc[i]
        if np.isnan(ap):
            regimes.append("Warmup")
        elif ap >= vol_70th:
            regimes.append("High Volatility")
        elif ap <= vol_30th:
            regimes.append("Low Volatility")
        elif d_tr:
            regimes.append("Bull Regime")
        else:
            regimes.append("Sideways / Bear")
    df_1h["regime"] = regimes

    return df_1h


def simulate_mtf_strategy(
    df_1h: pd.DataFrame,
    cfg: Dict[str, Any],
    fast_ema: int,
    slow_ema: int,
    daily_filter_col: str,
    extra_filter_fn: Optional[Callable[[pd.DataFrame], pd.Series]] = None,
    initial_capital: float = 100_000.0,
    allocation_pct: float = 0.50,
    slippage_ticks: int = 1,
    fee_multiplier: float = 1.0,
    slippage_multiplier: float = 1.0
) -> Dict[str, Any]:
    """Next-Open execution simulator with excursion and whipsaw tracking."""
    n = len(df_1h)
    close = df_1h["close"]
    opens = df_1h["open"].values
    highs = df_1h["high"].values
    lows = df_1h["low"].values
    closes = close.values
    dates = df_1h.index

    ema_f = close.ewm(span=fast_ema, adjust=False).mean().values
    ema_s = close.ewm(span=slow_ema, adjust=False).mean().values

    buy_1h_raw = (ema_f > ema_s) & (np.roll(ema_f, 1) <= np.roll(ema_s, 1))
    sell_1h_raw = (ema_f < ema_s) & (np.roll(ema_f, 1) >= np.roll(ema_s, 1))
    buy_1h_raw[0] = False
    sell_1h_raw[0] = False

    daily_filter = df_1h[daily_filter_col].values if daily_filter_col in df_1h.columns else np.ones(n, dtype=bool)
    buy_signals = buy_1h_raw & daily_filter
    sell_signals = sell_1h_raw | (~daily_filter)

    if extra_filter_fn is not None:
        extra_mask = extra_filter_fn(df_1h).values
        buy_signals = buy_signals & extra_mask

    mult = cfg["multiplier"]
    margin_pct = cfg["margin_pct"]
    fee = cfg["fixed_fee"] * fee_multiplier
    tick_size = cfg["tick_size"]
    slippage = slippage_ticks * tick_size * slippage_multiplier

    cash = initial_capital
    pos = 0
    entry_p = 0.0
    entry_idx = 0
    highest_since_entry = 0.0
    lowest_since_entry = 0.0

    trades = []
    equity_curve = np.empty(n, dtype=np.float64)

    for i in range(n):
        op = opens[i]
        cp = closes[i]
        hp = highs[i]
        lp = lows[i]

        if pos > 0:
            if hp > highest_since_entry:
                highest_since_entry = hp
            if lp < lowest_since_entry:
                lowest_since_entry = lp

        # Order Execution on Next Open (using signal confirmed at bar i-1)
        if i > 0:
            prev_b = buy_signals[i - 1]
            prev_s = sell_signals[i - 1]

            # Exit execution
            if prev_s and pos > 0:
                exec_p = op - slippage
                pnl = (exec_p - entry_p) * mult * pos
                total_fees = fee * pos * 2
                net_pnl = pnl - total_fees
                return_pct = (exec_p - entry_p) / entry_p * 100.0
                holding_bars = i - entry_idx

                mfe_pct = (highest_since_entry - entry_p) / entry_p * 100.0
                mae_pct = (entry_p - lowest_since_entry) / entry_p * 100.0
                is_whipsaw = (holding_bars <= 12) and (net_pnl <= 0) and (mfe_pct < 1.0)

                cash += pnl - fee
                trades.append({
                    "entry_date": dates[entry_idx],
                    "exit_date": dates[i],
                    "entry_price": entry_p,
                    "exit_price": exec_p,
                    "contracts": pos,
                    "net_pnl": net_pnl,
                    "return_pct": return_pct,
                    "holding_bars": holding_bars,
                    "holding_days": (dates[i] - dates[entry_idx]).total_seconds() / 86400.0,
                    "mfe_pct": mfe_pct,
                    "mae_pct": mae_pct,
                    "is_whipsaw": is_whipsaw,
                    "regime_at_entry": df_1h["regime"].iloc[entry_idx],
                    "poi_at_entry": df_1h["poi_quadrant"].iloc[entry_idx],
                })
                pos = 0
                entry_p = 0.0

            # Entry execution
            elif prev_b and pos == 0:
                exec_p = op + slippage
                contract_val = exec_p * mult
                margin_req = contract_val * margin_pct
                lots = int((cash * allocation_pct) // margin_req) if margin_req > 0 else 0
                if lots < 1 and cash >= margin_req:
                    lots = 1

                if lots >= 1:
                    pos = lots
                    entry_p = exec_p
                    entry_idx = i
                    highest_since_entry = op
                    lowest_since_entry = op
                    cash -= (fee * pos)

        # Mark to market
        unrealized = (cp - entry_p) * mult * pos if pos > 0 else 0.0
        equity_curve[i] = cash + unrealized

    end_val = equity_curve[-1]
    net_profit = end_val - initial_capital
    total_ret = (net_profit / initial_capital) * 100.0

    years = max(0.1, n / (252.0 * 6.5))
    cagr = (((end_val / initial_capital) ** (1.0 / years)) - 1.0) * 100.0 if end_val > 0 else -100.0

    running_max = np.maximum.accumulate(equity_curve)
    dd_series = (running_max - equity_curve) / running_max * 100.0
    max_dd = float(np.max(dd_series)) if len(dd_series) > 0 else 0.0

    daily_eq = pd.Series(equity_curve, index=dates).resample("1D").last().dropna()
    daily_rets = daily_eq.pct_change().dropna()
    daily_rf = (1.0 + 0.045) ** (1.0 / 252.0) - 1.0
    excess_rets = daily_rets - daily_rf
    std_r = daily_rets.std() if len(daily_rets) > 0 else 1e-6
    sharpe = (excess_rets.mean() / std_r) * math.sqrt(252) if std_r > 0 else 0.0

    downside = np.minimum(0.0, excess_rets.values)
    downside_dev = math.sqrt(np.mean(downside ** 2)) if len(downside) > 0 else 1e-6
    sortino = (excess_rets.mean() / downside_dev) * math.sqrt(252) if downside_dev > 0 else 0.0

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
    g_win = sum(t["net_pnl"] for t in wins)
    g_loss = abs(sum(t["net_pnl"] for t in losses))
    pf = (g_win / g_loss) if g_loss > 0 else (99.0 if g_win > 0 else 0.0)

    whipsaws = [t for t in trades if t["is_whipsaw"]]
    expectancy = (net_profit / len(trades)) if trades else 0.0

    return {
        "total_return_pct": total_ret,
        "cagr_pct": cagr,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "profit_factor": pf,
        "win_rate_pct": win_rate,
        "total_trades": len(trades),
        "expectancy_dollars": expectancy,
        "whipsaws": len(whipsaws),
        "trades": trades,
        "equity_curve": pd.Series(equity_curve, index=dates),
    }


def run_full_study():
    """Executes all 13 phases across all 5 assets."""
    print("\n" + "=" * 135)
    print(" 🔬 FULL MTF ROBUSTNESS & OI + VOLUME CONFIRMATION RESEARCH")
    print(" Strategy: MTF_BASELINE_V1 (Daily Macro Trend Filter + 1-Hour Intraday Execution)")
    print("=" * 135)

    study_summary = {}

    for sym, cfg in MTF_BASELINE_V1.items():
        print(f"\n==========================================================================================")
        print(f" 📦 ASSET: {cfg['name']} ({sym})")
        print(f" Frozen Config: 1H EMA {cfg['fast_ema']}/{cfg['slow_ema']} | {cfg['filter_name']}")
        print(f"==========================================================================================")

        df_1h = load_and_enrich_data(sym)
        n = len(df_1h)
        is_end = int(n * 0.60)
        val_end = int(n * 0.80)

        df_is = df_1h.iloc[:is_end].copy()
        df_val = df_1h.iloc[is_end:val_end].copy()
        df_oos = df_1h.iloc[val_end:].copy()

        # ----------------------------------------------------------------------
        # PHASE 2: OOS Robustness (60% IS / 20% Val / 20% OOS)
        # ----------------------------------------------------------------------
        m_is = simulate_mtf_strategy(df_is, cfg, cfg["fast_ema"], cfg["slow_ema"], cfg["daily_filter"])
        m_val = simulate_mtf_strategy(df_val, cfg, cfg["fast_ema"], cfg["slow_ema"], cfg["daily_filter"])
        m_oos = simulate_mtf_strategy(df_oos, cfg, cfg["fast_ema"], cfg["slow_ema"], cfg["daily_filter"])
        m_full = simulate_mtf_strategy(df_1h, cfg, cfg["fast_ema"], cfg["slow_ema"], cfg["daily_filter"])

        pf_deg = (m_oos["profit_factor"] - m_is["profit_factor"]) / (m_is["profit_factor"] + 1e-6) * 100.0

        print(f"\n[PHASE 2: OOS ROBUSTNESS EVALUATION]")
        print(f"{'Metric':20} {'In-Sample (60%)':18} {'Validation (20%)':18} {'Out-of-Sample (20%)':20}")
        print("-" * 80)
        print(f"{'CAGR %':20} {m_is['cagr_pct']:+17.2f}% {m_val['cagr_pct']:+17.2f}% {m_oos['cagr_pct']:+19.2f}%")
        print(f"{'Profit Factor':20} {m_is['profit_factor']:18.2f} {m_val['profit_factor']:18.2f} {m_oos['profit_factor']:20.2f}")
        print(f"{'Sharpe Ratio':20} {m_is['sharpe_ratio']:18.2f} {m_val['sharpe_ratio']:18.2f} {m_oos['sharpe_ratio']:20.2f}")
        print(f"{'Max Drawdown %':20} {m_is['max_drawdown_pct']:17.2f}% {m_val['max_drawdown_pct']:17.2f}% {m_oos['max_drawdown_pct']:19.2f}%")
        print(f"{'Trades Count':20} {m_is['total_trades']:18d} {m_val['total_trades']:18d} {m_oos['total_trades']:20d}")
        print(f"{'Expectancy ($)':20} ${m_is['expectancy_dollars']:+16,.2f} ${m_val['expectancy_dollars']:+16,.2f} ${m_oos['expectancy_dollars']:+18,.2f}")
        print(f"-> OOS/IS PF Ratio: {m_oos['profit_factor'] / (m_is['profit_factor'] + 1e-6):.2f} | PF Degradation: {pf_deg:+.1f}%")

        # ----------------------------------------------------------------------
        # PHASE 3: Parameter Perturbation (Fast ±1..2, Slow ±2..5)
        # ----------------------------------------------------------------------
        f_base, s_base = cfg["fast_ema"], cfg["slow_ema"]
        perturb_results = []
        for f_delta in [-1, 0, 1, 2]:
            f_test = f_base + f_delta
            for s_delta in [-2, 0, 2, 5]:
                s_test = s_base + s_delta
                if f_test >= s_test or f_test < 2:
                    continue
                res_p = simulate_mtf_strategy(df_1h, cfg, f_test, s_test, cfg["daily_filter"])
                perturb_results.append(res_p["profit_factor"])

        mean_p_pf = np.mean(perturb_results)
        std_p_pf = np.std(perturb_results)
        stability_ratio = mean_p_pf / (std_p_pf + 1e-6)
        perturb_label = "PARAMETER ROBUST" if stability_ratio > 3.0 and mean_p_pf > 1.2 else "PARAMETER FRAGILE"
        print(f"\n[PHASE 3: PARAMETER PERTURBATION]")
        print(f"  Neighborhood Mean PF: {mean_p_pf:.2f} | Std Dev: {std_p_pf:.2f} | Stability Ratio: {stability_ratio:.2f} -> {perturb_label}")

        # ----------------------------------------------------------------------
        # PHASE 4: Cost & Slippage Stress Tests
        # ----------------------------------------------------------------------
        print(f"\n[PHASE 4: COST & SLIPPAGE STRESS TESTING]")
        for c_mult, s_mult in [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]:
            res_stress = simulate_mtf_strategy(
                df_1h=df_oos,
                cfg=cfg,
                fast_ema=f_base,
                slow_ema=s_base,
                daily_filter_col=cfg["daily_filter"],
                extra_filter_fn=None,
                fee_multiplier=c_mult,
                slippage_multiplier=s_mult
            )
            print(f"  {c_mult:.0f}x Fee / {s_mult:.0f}x Slip -> OOS PF: {res_stress['profit_factor']:.2f} | OOS CAGR: {res_stress['cagr_pct']:+.2f}% | OOS MaxDD: {res_stress['max_drawdown_pct']:.2f}%")

        # ----------------------------------------------------------------------
        # PHASE 5: Trade Concentration Analysis
        # ----------------------------------------------------------------------
        trades = m_full["trades"]
        pnls = sorted([t["net_pnl"] for t in trades], reverse=True)
        tot_profit = sum(pnls)
        top1_pct = (pnls[0] / tot_profit * 100.0) if tot_profit > 0 and len(pnls) >= 1 else 0.0
        top3_pct = (sum(pnls[:3]) / tot_profit * 100.0) if tot_profit > 0 and len(pnls) >= 3 else 0.0
        top5_pct = (sum(pnls[:5]) / tot_profit * 100.0) if tot_profit > 0 and len(pnls) >= 5 else 0.0

        print(f"\n[PHASE 5: TRADE CONCENTRATION ANALYSIS]")
        print(f"  Total Trades: {len(trades)} | Cumulative Net Profit: ${tot_profit:+,.2f}")
        print(f"  Top 1 Winner: {top1_pct:.1f}% | Top 3 Winners: {top3_pct:.1f}% | Top 5 Winners: {top5_pct:.1f}%")
        print(f"  Median Trade: ${np.median(pnls):+,.2f} | Mean Trade: ${np.mean(pnls):+,.2f} | Expectancy: ${m_full['expectancy_dollars']:+,.2f}")

        # ----------------------------------------------------------------------
        # PHASE 6: Regime Breakdown
        # ----------------------------------------------------------------------
        print(f"\n[PHASE 6: MARKET REGIME PERFORMANCE BREAKDOWN]")
        regime_stats = {}
        for t in trades:
            reg = t["regime_at_entry"]
            if reg not in regime_stats:
                regime_stats[reg] = []
            regime_stats[reg].append(t["net_pnl"])

        for reg, p_list in regime_stats.items():
            w = [p for p in p_list if p > 0]
            l = [p for p in p_list if p <= 0]
            pf_r = (sum(w) / abs(sum(l))) if l and sum(l) != 0 else (99.0 if w else 0.0)
            print(f"  {reg:20} -> Trades: {len(p_list):3d} | Win%: {len(w)/len(p_list)*100:4.1f}% | Total PnL: ${sum(p_list):+9,.0f} | PF: {pf_r:5.2f}")

        # ----------------------------------------------------------------------
        # PHASE 7-9: Standalone Price + OI + Volume Quadrant Statistics
        # ----------------------------------------------------------------------
        print(f"\n[PHASE 7-9: PRICE + OI + VOLUME QUADRANT BREAKDOWN]")
        poi_stats = {}
        for t in trades:
            quad = t["poi_at_entry"]
            if quad not in poi_stats:
                poi_stats[quad] = []
            poi_stats[quad].append(t["net_pnl"])

        for quad, p_list in poi_stats.items():
            w = [p for p in p_list if p > 0]
            l = [p for p in p_list if p <= 0]
            pf_q = (sum(w) / abs(sum(l))) if l and sum(l) != 0 else (99.0 if w else 0.0)
            print(f"  {quad:48} -> Trades: {len(p_list):3d} | Win%: {len(w)/len(p_list)*100:4.1f}% | Net PnL: ${sum(p_list):+9,.0f} | PF: {pf_q:5.2f}")

        # ----------------------------------------------------------------------
        # PHASE 10-13: Incremental Filter Comparison (Baseline vs +Vol vs +OI vs +OI+Vol)
        # ----------------------------------------------------------------------
        filters_to_compare = [
            ("1. MTF Baseline (No Filter)", None),
            ("2. MTF + Volume (RVOL > 1.2)", lambda d: d["rvol"] > 1.2),
            ("3. MTF + OI (OI Expanding Trend)", lambda d: d["d_oi_trend"]),
            ("4. MTF + OI + Volume (Confirmed Buildup)", lambda d: (d["rvol"] > 1.0) & d["d_oi_trend"]),
        ]

        print(f"\n[PHASE 10-13: INCREMENTAL FILTER COMPARISON]")
        header = f"{'Strategy / Filter':45} {'IS PF':7} {'OOS PF':8} {'OOS CAGR':10} {'OOS Sh':8} {'OOS DD':8} {'Trades':7} {'Exp ($)':10} {'Whipsaws':9} {'Verdict':25}"
        print(header)
        print("-" * 135)

        for f_name, f_fn in filters_to_compare:
            res_is_f = simulate_mtf_strategy(df_1h=df_is, cfg=cfg, fast_ema=f_base, slow_ema=s_base, daily_filter_col=cfg["daily_filter"], extra_filter_fn=f_fn)
            res_val_f = simulate_mtf_strategy(df_1h=df_val, cfg=cfg, fast_ema=f_base, slow_ema=s_base, daily_filter_col=cfg["daily_filter"], extra_filter_fn=f_fn)
            res_oos_f = simulate_mtf_strategy(df_1h=df_oos, cfg=cfg, fast_ema=f_base, slow_ema=s_base, daily_filter_col=cfg["daily_filter"], extra_filter_fn=f_fn)
            res_full_f = simulate_mtf_strategy(df_1h=df_1h, cfg=cfg, fast_ema=f_base, slow_ema=s_base, daily_filter_col=cfg["daily_filter"], extra_filter_fn=f_fn)

            # Verdict Logic
            if res_full_f["total_trades"] < 20:
                v = "HARMFUL (Destroys Sample Size)"
            elif res_oos_f["profit_factor"] > (m_oos["profit_factor"] + 0.1) and res_oos_f["max_drawdown_pct"] <= m_oos["max_drawdown_pct"]:
                v = "STRONG (Increases OOS PF & Cuts DD)"
            elif res_oos_f["profit_factor"] >= 1.2 and res_full_f["whipsaws"] < m_full["whipsaws"]:
                v = "PROMISING (Reduces Whipsaws)"
            elif res_oos_f["profit_factor"] < 0.85:
                v = "WEAK / HARMFUL"
            else:
                v = "NO SIGNIFICANT VALUE ADDED"

            print(
                f"{f_name:45} {res_is_f['profit_factor']:7.2f} {res_oos_f['profit_factor']:8.2f} "
                f"{res_oos_f['cagr_pct']:+9.2f}% {res_oos_f['sharpe_ratio']:8.2f} {res_oos_f['max_drawdown_pct']:7.1f}% "
                f"{res_full_f['total_trades']:7d} ${res_full_f['expectancy_dollars']:+9,.0f} {res_full_f['whipsaws']:9d} {v:25}"
            )
        print("=" * 135)


if __name__ == "__main__":
    run_full_study()
