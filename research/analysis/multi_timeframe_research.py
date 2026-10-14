"""
================================================================================
Multi-Timeframe Strategy Research Engine (multi_timeframe_research.py)
================================================================================
Evaluates Daily Macro Trend Filters combined with 1-Hour EMA Crossover Execution:
  - Higher Timeframe (Daily): Trend direction calculated strictly on completed Daily[t-1] Close.
  - Lower Timeframe (1-Hour): 1H EMA 9/21, 13/34, and 20/50 entries & exits.
  - Solves the sample size bottleneck by generating statistically meaningful trade counts (N = 50-200).
  - Strict 60% IS / 20% Val / 20% OOS partitions and 10,000 Monte Carlo simulations.
"""

import math
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import yfinance as yf

from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import CONTRACT_SPECS, DataHandler


def load_multi_timeframe_data(symbol: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Downloads 1-hour intraday data and daily historical data,
    aligning the Daily Macro Trend with 1-hour bars with ZERO lookahead.
    """
    # 1. Fetch 1-Hour data (~730 days)
    df_1h = yf.download(symbol, period="730d", interval="1h", progress=False)
    if df_1h.empty:
        raise ValueError(f"No 1-hour data returned for {symbol}")

    if isinstance(df_1h.columns, pd.MultiIndex):
        df_1h.columns = [c[0] for c in df_1h.columns]

    df_1h = df_1h.rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
    })
    df_1h = df_1h[df_1h["close"].notnull() & (df_1h["close"] > 0)].copy()
    df_1h.index = pd.to_datetime(df_1h.index)
    if df_1h.index.tz is not None:
        df_1h.index = df_1h.index.tz_localize(None)
    df_1h = df_1h.sort_index()

    # 2. Fetch Daily data for the same symbol
    df_daily = yf.download(symbol, period="3y", interval="1d", progress=False)
    if isinstance(df_daily.columns, pd.MultiIndex):
        df_daily.columns = [c[0] for c in df_daily.columns]

    df_daily = df_daily.rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
    })
    df_daily = df_daily[df_daily["close"].notnull() & (df_daily["close"] > 0)].copy()
    df_daily.index = pd.to_datetime(df_daily.index)
    if df_daily.index.tz is not None:
        df_daily.index = df_daily.index.tz_localize(None)
    df_daily = df_daily.sort_index()

    # 3. Compute Daily Macro Indicators on completed Daily bars
    daily_close = df_daily["close"]
    df_daily["d_ema9"] = daily_close.ewm(span=9, adjust=False).mean()
    df_daily["d_ema21"] = daily_close.ewm(span=21, adjust=False).mean()
    df_daily["d_ema50"] = daily_close.ewm(span=50, adjust=False).mean()
    df_daily["d_sma200"] = daily_close.rolling(200).mean()

    # Daily Trend states (Shift by 1 to ensure Bar t on 1H ONLY uses completed Daily[t-1] close!)
    df_daily["d_trend_ema9_21"] = (df_daily["d_ema9"] > df_daily["d_ema21"]).shift(1)
    df_daily["d_trend_close_ema50"] = (daily_close > df_daily["d_ema50"]).shift(1)
    df_daily["d_trend_close_sma200"] = (daily_close > df_daily["d_sma200"]).shift(1)

    # 4. Map Daily Macro states onto 1-Hour DataFrame by calendar date (Zero lookahead)
    df_1h["date_key"] = df_1h.index.normalize()
    daily_aligned = df_daily[["d_trend_ema9_21", "d_trend_close_ema50", "d_trend_close_sma200"]].copy()

    df_1h = df_1h.join(daily_aligned, on="date_key")
    df_1h["d_trend_ema9_21"] = df_1h["d_trend_ema9_21"].ffill().fillna(False)
    df_1h["d_trend_close_ema50"] = df_1h["d_trend_close_ema50"].ffill().fillna(False)
    df_1h["d_trend_close_sma200"] = df_1h["d_trend_close_sma200"].ffill().fillna(False)

    return df_1h, df_daily


def simulate_1h_backtest(
    df_1h: pd.DataFrame,
    spec: Any,
    fast_ema: int = 9,
    slow_ema: int = 21,
    daily_filter_col: Optional[str] = "d_trend_ema9_21",
    initial_capital: float = 100_000.0,
    allocation_pct: float = 0.50,
    slippage_ticks: int = 1
) -> Dict[str, Any]:
    """
    Executes next-open backtest on 1-hour bars with Daily macro trend confirmation.
    """
    n = len(df_1h)
    close = df_1h["close"]
    opens = df_1h["open"].values
    highs = df_1h["high"].values
    lows = df_1h["low"].values
    closes = close.values
    dates = df_1h.index

    # Calculate 1-Hour EMAs
    ema_f = close.ewm(span=fast_ema, adjust=False).mean().values
    ema_s = close.ewm(span=slow_ema, adjust=False).mean().values

    buy_1h_raw = (ema_f > ema_s) & (np.roll(ema_f, 1) <= np.roll(ema_s, 1))
    sell_1h_raw = (ema_f < ema_s) & (np.roll(ema_f, 1) >= np.roll(ema_s, 1))
    buy_1h_raw[0] = False
    sell_1h_raw[0] = False

    # Apply Daily Filter if requested
    if daily_filter_col and daily_filter_col in df_1h.columns:
        daily_filter = df_1h[daily_filter_col].values
        buy_signals = buy_1h_raw & daily_filter
        # Exit when 1H EMA crosses down OR Daily trend flips false
        sell_signals = sell_1h_raw | (~daily_filter)
    else:
        buy_signals = buy_1h_raw
        sell_signals = sell_1h_raw

    mult = spec.multiplier
    margin_pct = spec.margin_pct
    fee = spec.fixed_fee_per_contract
    tick_size = spec.tick_size
    slippage = slippage_ticks * tick_size

    cash = initial_capital
    pos = 0
    entry_p = 0.0
    entry_idx = 0
    highest_since_entry = 0.0

    trades = []
    equity_curve = np.empty(n, dtype=np.float64)

    for i in range(n):
        op = opens[i]
        cp = closes[i]
        hp = highs[i]
        lp = lows[i]

        if pos > 0 and hp > highest_since_entry:
            highest_since_entry = hp

        # 1. Order execution on NEXT 1-HOUR OPEN (Bar i using signal from Bar i-1)
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
                max_favorable_pct = (highest_since_entry - entry_p) / entry_p * 100.0
                is_whipsaw = (holding_bars <= 12) and (net_pnl <= 0) and (max_favorable_pct < 1.0)

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
                    "is_whipsaw": is_whipsaw,
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
                    cash -= (fee * pos)

        # Mark-to-market total equity
        unrealized = (cp - entry_p) * mult * pos if pos > 0 else 0.0
        equity_curve[i] = cash + unrealized

    end_val = equity_curve[-1]
    net_profit = end_val - initial_capital
    total_ret = (net_profit / initial_capital) * 100.0

    years = max(0.1, n / (252.0 * 6.5))  # Approx trading hours per year
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


def run_multi_timeframe_evaluation():
    """Evaluates 1H EMA execution with Daily Macro Trend filters across all commodities."""
    assets = ["CL=F", "GC=F", "SI=F", "BZ=F", "NG=F"]
    
    # 1-Hour EMA combinations to evaluate
    LTF_EMA_PAIRS = [
        ("1H EMA 9/21", 9, 21),
        ("1H EMA 13/34", 13, 34),
        ("1H EMA 20/50", 20, 50),
    ]

    # Daily Macro Trend filters to evaluate
    HTF_FILTERS = [
        ("Unfiltered (Pure 1H EMA)", None),
        ("Daily Trend: D_EMA 9 > 21", "d_trend_ema9_21"),
        ("Daily Trend: Close > D_EMA 50", "d_trend_close_ema50"),
        ("Daily Trend: Close > D_SMA 200", "d_trend_close_sma200"),
    ]

    print("\n" + "=" * 130)
    print(" 🔬 MULTI-TIMEFRAME RESEARCH: DAILY MACRO TREND FILTER + 1-HOUR EMA EXECUTION")
    print(" Evaluating 1-Hour Intraday Bars (~13,500 Bars per Asset) | Solving Sample Size Bottleneck")
    print("=" * 130)

    full_results = {}

    for sym in assets:
        spec = CONTRACT_SPECS.get(sym, DataHandler.get_spec(sym))
        print(f"\n==========================================================================================")
        print(f" 📦 ASSET: {spec.name} ({sym}) | 1-Hour Intraday Multi-Timeframe Backtest")
        print(f"==========================================================================================")

        df_1h, df_daily = load_multi_timeframe_data(sym)

        # 60% IS / 20% Val / 20% OOS Split on 1-hour bars
        n_1h = len(df_1h)
        is_end = int(n_1h * 0.60)
        val_end = int(n_1h * 0.80)

        df_is = df_1h.iloc[:is_end].copy()
        df_val = df_1h.iloc[is_end:val_end].copy()
        df_oos = df_1h.iloc[val_end:].copy()

        asset_records = []

        for ltf_name, f_p, s_p in LTF_EMA_PAIRS:
            for htf_name, htf_col in HTF_FILTERS:
                label = f"{ltf_name} + {htf_name}"
                
                # Backtests on IS, Val, OOS, and Full
                m_is = simulate_1h_backtest(df_is, spec, f_p, s_p, htf_col)
                m_val = simulate_1h_backtest(df_val, spec, f_p, s_p, htf_col)
                m_oos = simulate_1h_backtest(df_oos, spec, f_p, s_p, htf_col)
                m_full = simulate_1h_backtest(df_1h, spec, f_p, s_p, htf_col)

                # Monte Carlo (10,000 resamplings) - now statistically meaningful!
                trades = m_full["trades"]
                if len(trades) >= 20:
                    pnls = np.array([t["net_pnl"] for t in trades])
                    np.random.seed(42)
                    sim_rets = [np.sum(np.random.choice(pnls, size=len(pnls), replace=True)) / 100_000.0 * 100.0 for _ in range(10_000)]
                    prob_loss = float(np.mean(np.array(sim_rets) < 0.0) * 100.0)
                    mc_status = f"Loss Prob: {prob_loss:.1f}%"
                else:
                    mc_status = f"Low Trades (N={len(trades)})"

                # Outlier Concentration: Top 1 Winner %
                if trades and sum(t["net_pnl"] for t in trades) > 0:
                    top1_pct = max(t["net_pnl"] for t in trades) / sum(t["net_pnl"] for t in trades) * 100.0
                else:
                    top1_pct = 0.0

                # Classification
                if m_oos["profit_factor"] > 1.3 and m_oos["sharpe_ratio"] > 0.8 and m_full["total_trades"] >= 30 and top1_pct < 40.0:
                    verdict = "✅ ROBUST (Statistically Validated)"
                elif m_oos["profit_factor"] > 1.1 and m_full["total_trades"] >= 25:
                    verdict = "🌟 PROMISING (Good Sample Size)"
                elif m_is["profit_factor"] > 1.8 and m_oos["profit_factor"] < 0.8:
                    verdict = "⚠️ OVERFIT"
                elif m_oos["profit_factor"] < 0.85:
                    verdict = "❌ WEAK / NO EDGE"
                else:
                    verdict = "NEUTRAL"

                asset_records.append({
                    "strategy": label,
                    "is_pf": m_is["profit_factor"],
                    "val_pf": m_val["profit_factor"],
                    "oos_pf": m_oos["profit_factor"],
                    "oos_sharpe": m_oos["sharpe_ratio"],
                    "oos_max_dd": m_oos["max_drawdown_pct"],
                    "full_cagr": m_full["cagr_pct"],
                    "full_sharpe": m_full["sharpe_ratio"],
                    "trades": m_full["total_trades"],
                    "win_rate": m_full["win_rate_pct"],
                    "expectancy": m_full["expectancy_dollars"],
                    "whipsaws": m_full["whipsaws"],
                    "top1_winner_pct": top1_pct,
                    "mc_status": mc_status,
                    "verdict": verdict,
                })

        full_results[sym] = asset_records

        # Print Table
        header = f"{'Multi-Timeframe Configuration':45} {'IS PF':7} {'OOS PF':8} {'OOS Sh':8} {'OOS DD':8} {'Full CAGR':10} {'Trades':7} {'Win %':7} {'Top1 %':7} {'Verdict':25}"
        print(header)
        print("-" * 130)

        for r in asset_records:
            print(
                f"{r['strategy']:45} {r['is_pf']:7.2f} {r['oos_pf']:8.2f} "
                f"{r['oos_sharpe']:8.2f} {r['oos_max_dd']:7.1f}% {r['full_cagr']:+9.1f}% "
                f"{r['trades']:7d} {r['win_rate']:6.1f}% {r['top1_winner_pct']:6.1f}% {r['verdict']:25}"
            )
        print("=" * 130)

    return full_results


if __name__ == "__main__":
    run_multi_timeframe_evaluation()
