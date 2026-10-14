"""
================================================================================
Regime & Confirmation Filter Research Engine (regime_filter_research.py)
================================================================================
Evaluates one confirmation filter at a time on top of frozen EMA baselines:
  - Phase 2: ADX Trend Strength Filter (>15, >20, >25, >30)
  - Phase 3: ATR / Volatility Regime Filter (Expansion, ATR%, Volatility bands)
  - Phase 4: EMA Separation Filter (% distance threshold)
  - Phase 5: Volume Confirmation Filter (RVOL > 1.0, > 1.2, > 1.5, > 2.0)
  - Phase 6: Price / Volume / OI Interaction Quadrants
  - Phase 7: Higher-Timeframe Macro Trend (Close > SMA50, Close > SMA200, SMA50 > SMA200)

Validation Standards:
  - Strict 60% IS / 20% Validation / 20% OOS Splits
  - Whipsaw Tracking (Trades <= 7 bars with loss and MFE < 1.5%)
  - Zero Lookahead: Confirmed on Close[t-1], executed on Open[t]
"""

import math
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import CONTRACT_SPECS, DataHandler
from ..engine.metrics import MetricsEngine


# FROZEN EMA BASELINE CONFIGURATIONS
FROZEN_EMA_CONFIGS = {
    "CL=F": {"fast": 22, "slow": 30, "name": "Crude Oil (WTI)"},
    "GC=F": {"fast": 5, "slow": 52, "name": "Gold Futures"},
    "SI=F": {"fast": 9, "slow": 100, "name": "Silver Futures"},
    "BZ=F": {"fast": 24, "slow": 30, "name": "Brent Crude"},
    "NG=F": {"fast": 15, "slow": 50, "name": "Natural Gas"},
}


def compute_indicators(df: pd.DataFrame, fast_p: int, slow_p: int) -> pd.DataFrame:
    """Computes all technical indicators, volatility, ADX, and volume series on clean OHLCV."""
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # 1. Frozen EMAs
    ema_f = close.ewm(span=fast_p, adjust=False).mean()
    ema_s = close.ewm(span=slow_p, adjust=False).mean()
    df["ema_fast"] = ema_f
    df["ema_slow"] = ema_s

    # Raw EMA crossover signals (confirmed on close)
    df["ema_buy_raw"] = (ema_f > ema_s) & (ema_f.shift(1) <= ema_s.shift(1))
    df["ema_sell_raw"] = (ema_f < ema_s) & (ema_f.shift(1) >= ema_s.shift(1))

    # 2. True Range & ATR(14)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    df["atr14"] = atr14
    df["atr_pct"] = (atr14 / close) * 100.0
    df["atr_sma20"] = atr14.rolling(20).mean()
    df["atr_expansion"] = atr14 > df["atr_sma20"]

    # 3. Wilder's ADX(14)
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).mean() / (atr14 + 1e-6))
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).mean() / (atr14 + 1e-6))
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-6))
    df["adx14"] = dx.rolling(14).mean()

    # 4. EMA Separation %
    df["ema_separation_pct"] = ((ema_f - ema_s).abs() / close) * 100.0

    # 5. Volume Indicators (RVOL)
    vol_sma20 = volume.rolling(20).mean()
    df["vol_sma20"] = vol_sma20
    df["rvol"] = volume / (vol_sma20 + 1e-6)

    # 6. Price-Volume Dynamics
    price_up = close > close.shift(1)
    vol_up = volume > volume.shift(1)
    df["pv_bull_confirm"] = price_up & vol_up

    # 7. Higher Timeframe / Macro Trend SMAs
    df["sma50"] = close.rolling(50).mean()
    df["sma200"] = close.rolling(200).mean()
    df["htf_bull_50"] = close > df["sma50"]
    df["htf_bull_200"] = close > df["sma200"]
    df["htf_golden_cross"] = df["sma50"] > df["sma200"]

    return df


def simulate_filter_backtest(
    df: pd.DataFrame,
    spec: Any,
    buy_condition: pd.Series,
    sell_condition: pd.Series,
    initial_capital: float = 100_000.0,
    allocation_pct: float = 0.50,
    slippage_ticks: int = 1
) -> Dict[str, Any]:
    """
    Executes backtest with next-open execution and detailed whipsaw diagnostics.
    """
    n = len(df)
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    dates = df.index

    buy_sig = buy_condition.fillna(False).values
    sell_sig = sell_condition.fillna(False).values
    buy_sig[0] = False
    sell_sig[0] = False

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

        # Update MFE tracker during holding
        if pos > 0:
            if hp > highest_since_entry:
                highest_since_entry = hp

        # Order execution on NEXT OPEN (using signal confirmed at bar i-1)
        if i > 0:
            prev_b = buy_sig[i - 1]
            prev_s = sell_sig[i - 1]

            # Exit execution
            if prev_s and pos > 0:
                exec_p = op - slippage
                pnl = (exec_p - entry_p) * mult * pos
                total_fees = fee * pos * 2
                net_pnl = pnl - total_fees
                return_pct = (exec_p - entry_p) / entry_p * 100.0
                holding_bars = i - entry_idx
                max_favorable_pct = (highest_since_entry - entry_p) / entry_p * 100.0

                # Whipsaw Definition: Held <= 7 bars, Loss <= 0, and never exceeded 1.5% profit
                is_whipsaw = (holding_bars <= 7) and (net_pnl <= 0) and (max_favorable_pct < 1.5)

                cash += pnl - fee
                trades.append({
                    "entry_date": dates[entry_idx],
                    "exit_date": dates[i],
                    "entry_price": entry_p,
                    "exit_price": exec_p,
                    "net_pnl": net_pnl,
                    "return_pct": return_pct,
                    "holding_bars": holding_bars,
                    "max_favorable_pct": max_favorable_pct,
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

    years = max(0.1, n / 252.0)
    cagr = (((end_val / initial_capital) ** (1.0 / years)) - 1.0) * 100.0 if end_val > 0 else -100.0

    running_max = np.maximum.accumulate(equity_curve)
    dd_series = (running_max - equity_curve) / running_max * 100.0
    max_dd = float(np.max(dd_series)) if len(dd_series) > 0 else 0.0

    daily_rets = np.diff(equity_curve) / (equity_curve[:-1] + 1e-6)
    daily_rf = (1.0 + 0.045) ** (1.0 / 252.0) - 1.0
    excess_rets = daily_rets - daily_rf
    std_r = np.std(daily_rets) if len(daily_rets) > 0 else 1e-6
    sharpe = (np.mean(excess_rets) / std_r) * math.sqrt(252) if std_r > 0 else 0.0

    downside = np.minimum(0.0, excess_rets)
    downside_dev = math.sqrt(np.mean(downside ** 2)) if len(downside) > 0 else 1e-6
    sortino = (np.mean(excess_rets) / downside_dev) * math.sqrt(252) if downside_dev > 0 else 0.0

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
    g_win = sum(t["net_pnl"] for t in wins)
    g_loss = abs(sum(t["net_pnl"] for t in losses))
    pf = (g_win / g_loss) if g_loss > 0 else (99.0 if g_win > 0 else 0.0)

    # Whipsaw diagnostics
    whipsaws = [t for t in trades if t["is_whipsaw"]]
    whipsaw_count = len(whipsaws)
    whipsaw_loss = abs(sum(t["net_pnl"] for t in whipsaws))
    avg_loss = (g_loss / len(losses)) if losses else 0.0

    # Max consecutive losses
    max_consec_losses = 0
    cur_consec = 0
    for t in trades:
        if t["net_pnl"] <= 0:
            cur_consec += 1
            if cur_consec > max_consec_losses:
                max_consec_losses = cur_consec
        else:
            cur_consec = 0

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
        "whipsaw_count": whipsaw_count,
        "whipsaw_loss_dollars": whipsaw_loss,
        "avg_loss_dollars": avg_loss,
        "max_consecutive_losses": max_consec_losses,
        "trades": trades,
    }


def evaluate_filter_candidate(
    symbol: str,
    filter_name: str,
    buy_filter_fn: Callable[[pd.DataFrame], pd.Series],
    df: pd.DataFrame
) -> Dict[str, Any]:
    """
    Evaluates a single filter candidate against strict 60% IS / 20% Val / 20% OOS partitions.
    """
    cfg = FROZEN_EMA_CONFIGS[symbol]
    spec = DataHandler.get_spec(symbol)

    n = len(df)
    is_end = int(n * 0.60)
    val_end = int(n * 0.80)

    df_is = df.iloc[:is_end].copy()
    df_val = df.iloc[is_end:val_end].copy()
    df_oos = df.iloc[val_end:].copy()

    # Generate filtered signals
    buy_sig_full = buy_filter_fn(df)
    sell_sig_full = df["ema_sell_raw"]

    res_is = simulate_filter_backtest(df_is, spec, buy_sig_full.iloc[:is_end], sell_sig_full.iloc[:is_end])
    res_val = simulate_filter_backtest(df_val, spec, buy_sig_full.iloc[is_end:val_end], sell_sig_full.iloc[is_end:val_end])
    res_oos = simulate_filter_backtest(df_oos, spec, buy_sig_full.iloc[val_end:], sell_sig_full.iloc[val_end:])
    res_full = simulate_filter_backtest(df, spec, buy_sig_full, sell_sig_full)

    # Classify Filter Verdict
    is_pf = res_is["profit_factor"]
    oos_pf = res_oos["profit_factor"]
    oos_sharpe = res_oos["sharpe_ratio"]
    oos_dd = res_oos["max_drawdown_pct"]
    trades_full = res_full["total_trades"]

    # Baseline comparison (no filter)
    base_buy = df["ema_buy_raw"]
    res_base_full = simulate_filter_backtest(df, spec, base_buy, sell_sig_full)
    base_oos = simulate_filter_backtest(df_oos, spec, base_buy.iloc[val_end:], sell_sig_full.iloc[val_end:])

    if trades_full < 4:
        verdict = "HARMFUL (Destroys Trade Count)"
    elif oos_pf > (base_oos["profit_factor"] + 0.5) and oos_sharpe > (base_oos["sharpe_ratio"] + 0.2) and oos_dd < base_oos["max_drawdown_pct"]:
        verdict = "STRONG (Improves OOS & Reduces DD)"
    elif oos_sharpe > base_oos["sharpe_ratio"] and res_full["whipsaw_count"] < res_base_full["whipsaw_count"]:
        verdict = "PROMISING (Reduces Whipsaws)"
    elif is_pf > 3.0 and (oos_pf < 0.8 or oos_sharpe < 0):
        verdict = "OVERFIT (IS Illusion, Fails OOS)"
    elif oos_pf < base_oos["profit_factor"] or oos_dd > base_oos["max_drawdown_pct"]:
        verdict = "HARMFUL (Degrades Performance)"
    else:
        verdict = "NO SIGNIFICANT IMPROVEMENT"

    return {
        "symbol": symbol,
        "filter_name": filter_name,
        "is_pf": is_pf,
        "val_pf": res_val["profit_factor"],
        "oos_pf": oos_pf,
        "oos_sharpe": oos_sharpe,
        "oos_max_dd": oos_dd,
        "expectancy": res_full["expectancy_dollars"],
        "full_cagr": res_full["cagr_pct"],
        "full_sharpe": res_full["sharpe_ratio"],
        "full_max_dd": res_full["max_drawdown_pct"],
        "trades": trades_full,
        "whipsaws": res_full["whipsaw_count"],
        "whipsaw_loss": res_full["whipsaw_loss_dollars"],
        "verdict": verdict,
        "res_full": res_full,
        "res_oos": res_oos,
    }


def run_full_regime_study():
    """Runs complete 12-phase filter evaluation suite across all 5 assets."""
    # Define Filter Suite
    FILTERS = [
        ("0. Baseline (Pure EMA, No Filter)", lambda d: d["ema_buy_raw"]),
        # ADX Trend Strength
        ("1. ADX > 15 (Early Trend)", lambda d: d["ema_buy_raw"] & (d["adx14"] > 15)),
        ("2. ADX > 20 (Moderate Trend)", lambda d: d["ema_buy_raw"] & (d["adx14"] > 20)),
        ("3. ADX > 25 (Strong Trend)", lambda d: d["ema_buy_raw"] & (d["adx14"] > 25)),
        ("4. ADX > 30 (Very Strong Trend)", lambda d: d["ema_buy_raw"] & (d["adx14"] > 30)),
        # ATR / Volatility
        ("5. ATR Expansion (ATR > ATR_SMA20)", lambda d: d["ema_buy_raw"] & d["atr_expansion"]),
        ("6. Volatility Filter (ATR% > 1.5%)", lambda d: d["ema_buy_raw"] & (d["atr_pct"] > 1.5)),
        ("7. Low Vol Rejection (ATR% > 1.0%)", lambda d: d["ema_buy_raw"] & (d["atr_pct"] > 1.0)),
        # EMA Separation
        ("8. EMA Separation > 0.2%", lambda d: d["ema_buy_raw"] & (d["ema_separation_pct"] > 0.2)),
        ("9. EMA Separation > 0.5%", lambda d: d["ema_buy_raw"] & (d["ema_separation_pct"] > 0.5)),
        ("10. EMA Separation > 1.0%", lambda d: d["ema_buy_raw"] & (d["ema_separation_pct"] > 1.0)),
        # Volume Confirmation
        ("11. RVOL > 1.0 (Above Avg Volume)", lambda d: d["ema_buy_raw"] & (d["rvol"] > 1.0)),
        ("12. RVOL > 1.2 (Volume Surge)", lambda d: d["ema_buy_raw"] & (d["rvol"] > 1.2)),
        ("13. RVOL > 1.5 (Volume Breakout)", lambda d: d["ema_buy_raw"] & (d["rvol"] > 1.5)),
        ("14. Price_Up + Vol_Up Confirmed", lambda d: d["ema_buy_raw"] & d["pv_bull_confirm"]),
        # HTF Macro Trend
        ("15. HTF Trend: Close > SMA50", lambda d: d["ema_buy_raw"] & d["htf_bull_50"]),
        ("16. HTF Trend: Close > SMA200", lambda d: d["ema_buy_raw"] & d["htf_bull_200"]),
        ("17. HTF Regime: SMA50 > SMA200", lambda d: d["ema_buy_raw"] & d["htf_golden_cross"]),
    ]

    print("\n" + "=" * 125)
    print(" 🔬 REGIME & CONFIRMATION FILTER RESEARCH (ONE FILTER AT A TIME)")
    print(" Evaluating: ADX, ATR Volatility, EMA Separation, RVOL Volume, and HTF Macro Trend")
    print("=" * 125)

    all_filter_results = {}

    for sym in ["CL=F", "GC=F", "SI=F", "BZ=F", "NG=F"]:
        cfg = FROZEN_EMA_CONFIGS[sym]
        print(f"\n==========================================================================================")
        print(f" 📦 ASSET: {cfg['name']} ({sym}) | Frozen Baseline: EMA {cfg['fast']}/{cfg['slow']}")
        print(f"==========================================================================================")

        df_raw = DataHandler.load_ohlcv(sym, period="3y", interval="1d")
        df = compute_indicators(df_raw, cfg["fast"], cfg["slow"])

        asset_results = []
        for name, fn in FILTERS:
            res = evaluate_filter_candidate(sym, name, fn, df)
            asset_results.append(res)

        all_filter_results[sym] = asset_results

        # Print Table
        header = f"{'Filter Candidate':36} {'IS PF':7} {'OOS PF':8} {'OOS Sharpe':11} {'OOS MaxDD':10} {'Expectancy':12} {'Trades':7} {'Whipsaws':9} {'Verdict':25}"
        print(header)
        print("-" * 125)

        for r in asset_results:
            print(
                f"{r['filter_name']:36} {r['is_pf']:7.2f} {r['oos_pf']:8.2f} "
                f"{r['oos_sharpe']:11.2f} {r['oos_max_dd']:9.2f}% "
                f"${r['expectancy']:+10,.0f} {r['trades']:7d} {r['whipsaws']:9d} {r['verdict']:25}"
            )
        print("=" * 125)

    return all_filter_results


if __name__ == "__main__":
    run_full_regime_study()
