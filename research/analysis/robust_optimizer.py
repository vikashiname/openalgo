"""
================================================================================
Fast Robust Parameter Optimization Engine
================================================================================
Vectorized pre-calculation of EMA parameter grid (Fast 5-30 x Slow 20-100),
60% In-Sample / 40% Out-of-Sample evaluation, and neighborhood stability scoring.
"""

import math
import sys
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
import yfinance as yf

from ..engine.data_handler import CONTRACT_SPECS, DataHandler


def fast_backtest_signals(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    buy_signals: np.ndarray,
    sell_signals: np.ndarray,
    multiplier: float,
    margin_pct: float,
    fixed_fee: float,
    tick_size: float,
    initial_capital: float = 100_000.0,
    allocation_pct: float = 0.50,
    risk_free_rate: float = 0.045
) -> Dict[str, Any]:
    """Ultra-fast compiled backtest loop with next-open execution and discrete lot sizing."""
    n = len(closes)
    cash = initial_capital
    pos = 0
    entry_p = 0.0
    entry_idx = 0
    slippage = 1 * tick_size

    trades_pnl = []
    equity = np.empty(n, dtype=np.float64)

    for i in range(n):
        op = opens[i]
        cp = closes[i]

        # Execution on Next Open (using signal from bar i-1)
        if i > 0:
            prev_b = buy_signals[i - 1]
            prev_s = sell_signals[i - 1]

            if prev_s and pos > 0:
                exec_p = op - slippage
                pnl = (exec_p - entry_p) * multiplier * pos
                fee = fixed_fee * pos * 2
                net_pnl = pnl - fee
                cash += pnl - (fee / 2.0)
                trades_pnl.append(net_pnl)
                pos = 0
                entry_p = 0.0

            elif prev_b and pos == 0:
                exec_p = op + slippage
                c_val = exec_p * multiplier
                margin_req = c_val * margin_pct
                lots = int((cash * allocation_pct) // margin_req) if margin_req > 0 else 0
                if lots < 1 and cash >= margin_req:
                    lots = 1

                if lots >= 1:
                    pos = lots
                    entry_p = exec_p
                    entry_idx = i
                    cash -= (fixed_fee * pos)

        # Mark-to-market total equity
        unrealized = (cp - entry_p) * multiplier * pos if pos > 0 else 0.0
        equity[i] = cash + unrealized

    end_val = equity[-1]
    net_profit = end_val - initial_capital
    total_ret = (net_profit / initial_capital) * 100.0

    # Annualized CAGR
    years = max(0.1, n / 252.0)
    cagr = (((end_val / initial_capital) ** (1.0 / years)) - 1.0) * 100.0 if end_val > 0 else -100.0

    # Max Drawdown
    running_max = np.maximum.accumulate(equity)
    dd_arr = (running_max - equity) / running_max * 100.0
    max_dd = float(np.max(dd_arr)) if len(dd_arr) > 0 else 0.0

    # Sharpe Ratio
    rets = np.diff(equity) / equity[:-1]
    daily_rf = (1.0 + risk_free_rate) ** (1.0 / 252.0) - 1.0
    excess_rets = rets - daily_rf
    std_r = np.std(rets) if len(rets) > 0 else 0.0
    sharpe = (np.mean(excess_rets) / (std_r + 1e-6)) * math.sqrt(252) if std_r > 0 else 0.0

    # Trade stats
    t_count = len(trades_pnl)
    wins = [p for p in trades_pnl if p > 0]
    losses = [p for p in trades_pnl if p <= 0]
    w_count = len(wins)
    win_rate = (w_count / t_count * 100.0) if t_count > 0 else 0.0
    g_win = sum(wins)
    g_loss = abs(sum(losses))
    pf = (g_win / g_loss) if g_loss > 0 else (99.0 if g_win > 0 else 0.0)

    return {
        "total_return": total_ret,
        "cagr": cagr,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "profit_factor": pf,
        "win_rate": win_rate,
        "trades_count": t_count,
        "net_profit": net_profit,
    }


def optimize_robust_regions(
    symbol: str,
    fast_range: Tuple[int, int, int] = (5, 30, 1),
    slow_range: Tuple[int, int, int] = (20, 100, 2),
    initial_capital: float = 100_000.0
) -> pd.DataFrame:
    """Fast grid optimizer evaluating neighborhood robustness and OOS persistence."""
    spec = DataHandler.get_spec(symbol)
    df = DataHandler.load_ohlcv(symbol, period="3y", interval="1d")

    close = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values

    n = len(df)
    is_split = int(n * 0.60)

    # Pre-calculate all EMA series from period 5 to 105
    max_p = max(slow_range[1] + 10, 105)
    close_series = pd.Series(close)
    ema_dict = {p: close_series.ewm(span=p, adjust=False).mean().values for p in range(5, max_p + 1)}

    fast_vals = list(range(fast_range[0], fast_range[1] + 1, fast_range[2]))
    slow_vals = list(range(slow_range[0], slow_range[1] + 1, slow_range[2]))

    grid_records = []

    for f in fast_vals:
        ef = ema_dict[f]
        for s in slow_vals:
            if f >= s:
                continue
            es = ema_dict[s]

            # Signal vectors
            b_sig = (ef > es) & (np.roll(ef, 1) <= np.roll(es, 1))
            s_sig = (ef < es) & (np.roll(ef, 1) >= np.roll(es, 1))
            b_sig[0] = False
            s_sig[0] = False

            # In-Sample Backtest (60%)
            m_is = fast_backtest_signals(
                opens[:is_split], highs[:is_split], lows[:is_split], close[:is_split],
                b_sig[:is_split], s_sig[:is_split],
                spec.multiplier, spec.margin_pct, spec.fixed_fee_per_contract, spec.tick_size,
                initial_capital
            )

            # Out-of-Sample Backtest (40%)
            m_oos = fast_backtest_signals(
                opens[is_split:], highs[is_split:], lows[is_split:], close[is_split:],
                b_sig[is_split:], s_sig[is_split:],
                spec.multiplier, spec.margin_pct, spec.fixed_fee_per_contract, spec.tick_size,
                initial_capital
            )

            # Full Period Backtest
            m_full = fast_backtest_signals(
                opens, highs, lows, close,
                b_sig, s_sig,
                spec.multiplier, spec.margin_pct, spec.fixed_fee_per_contract, spec.tick_size,
                initial_capital
            )

            grid_records.append({
                "fast_ema": f,
                "slow_ema": s,
                "is_cagr": m_is["cagr"],
                "is_sharpe": m_is["sharpe"],
                "is_pf": m_is["profit_factor"],
                "is_trades": m_is["trades_count"],
                "oos_cagr": m_oos["cagr"],
                "oos_sharpe": m_oos["sharpe"],
                "oos_pf": m_oos["profit_factor"],
                "oos_max_dd": m_oos["max_dd"],
                "oos_win_rate": m_oos["win_rate"],
                "oos_trades": m_oos["trades_count"],
                "full_cagr": m_full["cagr"],
                "full_sharpe": m_full["sharpe"],
                "full_max_dd": m_full["max_dd"],
                "full_trades": m_full["trades_count"],
            })

    gdf = pd.DataFrame(grid_records)
    if gdf.empty:
        return pd.DataFrame()

    # Neighborhood Stability Calculation
    pivot_is = gdf.pivot(index="fast_ema", columns="slow_ema", values="is_sharpe")
    pivot_oos = gdf.pivot(index="fast_ema", columns="slow_ema", values="oos_sharpe")

    scored = []
    for idx, row in gdf.iterrows():
        f = int(row["fast_ema"])
        s = int(row["slow_ema"])

        # Gather 8-neighbors (f ± 1..2, s ± 2..4)
        is_n = []
        oos_n = []
        for df_step in [-2, -1, 0, 1, 2]:
            for ds_step in [-4, -2, 0, 2, 4]:
                nf, ns = f + df_step, s + ds_step
                if nf in pivot_is.index and ns in pivot_is.columns:
                    val_is = pivot_is.loc[nf, ns]
                    val_oos = pivot_oos.loc[nf, ns]
                    if not np.isnan(val_is) and not np.isnan(val_oos):
                        is_n.append(val_is)
                        oos_n.append(val_oos)

        if len(is_n) >= 5 and row["full_trades"] >= 6:
            mean_is = np.mean(is_n)
            std_is = np.std(is_n)
            mean_oos = np.mean(oos_n)
            std_oos = np.std(oos_n)

            # Plateau Stability Score = Neighborhood Average / Variance penalty
            stability_score = (mean_is / (std_is + 0.08)) if mean_is > 0 else (mean_is * (std_is + 1.0))
            
            # Out-of-Sample Quality & Degradation
            oos_quality = row["oos_sharpe"]
            persistence = (row["oos_sharpe"] / (row["is_sharpe"] + 0.01)) if row["is_sharpe"] > 0 else 0.0

            # Composite Robustness Metric
            # Weights: 40% OOS Sharpe + 30% Neighborhood Plateau Stability + 20% OOS Persistence + 10% Drawdown Safety
            composite = (
                (0.40 * oos_quality) +
                (0.30 * stability_score) +
                (0.20 * min(1.5, persistence)) +
                (0.10 * max(0.0, 1.0 - (row["oos_max_dd"] / 100.0)))
            )

            scored.append({
                "parameter_pair": f"EMA {f}/{s}",
                "fast_ema": f,
                "slow_ema": s,
                "composite_robustness": composite,
                "is_sharpe": row["is_sharpe"],
                "is_cagr": row["is_cagr"],
                "is_trades": row["is_trades"],
                "oos_sharpe": row["oos_sharpe"],
                "oos_cagr": row["oos_cagr"],
                "oos_pf": row["oos_pf"],
                "oos_win_rate": row["oos_win_rate"],
                "oos_max_dd": row["oos_max_dd"],
                "oos_trades": row["oos_trades"],
                "plateau_mean_sharpe": mean_oos,
                "plateau_std_sharpe": std_oos,
                "full_cagr": row["full_cagr"],
                "full_sharpe": row["full_sharpe"],
                "full_max_dd": row["full_max_dd"],
                "full_trades": row["full_trades"],
            })

    res_df = pd.DataFrame(scored)
    if not res_df.empty:
        res_df = res_df.sort_values(by="composite_robustness", ascending=False).reset_index(drop=True)
    return res_df


def main():
    target_assets = ["CL=F", "GC=F", "SI=F", "NG=F", "BZ=F"]
    all_top10 = {}

    for sym in target_assets:
        spec = DataHandler.get_spec(sym)
        print(f"\n==========================================================================================")
        print(f" 🏆 TOP 10 ROBUST PARAMETER REGIONS FOR: {spec.name} ({sym})")
        print(f" Prioritizing Plateau Stability & Out-of-Sample (OOS) Performance")
        print(f"==========================================================================================")

        df_res = optimize_robust_regions(
            symbol=sym,
            fast_range=(5, 30, 1),
            slow_range=(20, 100, 2),
            initial_capital=100_000.0
        )

        if df_res.empty:
            print("No valid regions found.")
            continue

        top10 = df_res.head(10)
        all_top10[sym] = top10

        header = f"{'Rank':4} {'EMA Pair':10} {'Robust Score':13} {'IS Sharpe':10} {'OOS Sharpe':11} {'OOS CAGR':10} {'OOS MaxDD':10} {'OOS PF':8} {'Full Sharpe':11}"
        print(header)
        print("-" * 105)

        for i, r in top10.iterrows():
            print(
                f"#{i+1:<3} {r['parameter_pair']:10} {r['composite_robustness']:12.2f} "
                f"{r['is_sharpe']:10.2f} {r['oos_sharpe']:11.2f} {r['oos_cagr']:+9.2f}% "
                f"{r['oos_max_dd']:9.2f}% {r['oos_pf']:8.2f} {r['full_sharpe']:11.2f}"
            )
        print("=" * 105)

        # Baseline Reference
        base_match = df_res[df_res["parameter_pair"] == "EMA 9/21"]
        if not base_match.empty:
            b = base_match.iloc[0]
            print(f"📌 Baseline (EMA 9/21) Reference:")
            print(f"   IS Sharpe: {b['is_sharpe']:.2f} | OOS Sharpe: {b['oos_sharpe']:.2f} | OOS CAGR: {b['oos_cagr']:+.2f}% | OOS MaxDD: {b['oos_max_dd']:.2f}% | Robust Score: {b['composite_robustness']:.2f}")


if __name__ == "__main__":
    main()
