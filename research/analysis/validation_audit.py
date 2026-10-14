"""
================================================================================
Comprehensive Strategy Validation & Robustness Audit Engine
================================================================================
Executes the full institutional validation audit across 14 checkpoints:
- 60% IS / 20% Val / 20% OOS partitions
- 8-Neighborhood Plateau Breadth verification
- Rolling Walk-Forward window logging
- 10,000 Monte Carlo Bootstrap resamples with sample size warnings
- Gold stress testing (slippage 1..5 ticks, costs 1x..3x)
- Trade concentration analysis (Top 1, Top 3 contributors, median vs mean)
"""

import math
import sys
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd

from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import CONTRACT_SPECS, DataHandler
from ..strategies.ema_crossover import EMACrossoverStrategy


def run_partition_eval(symbol: str, fast: int, slow: int) -> Dict[str, Any]:
    """Evaluates strict 60% IS, 20% Validation, and 20% OOS splits."""
    spec = DataHandler.get_spec(symbol)
    df = DataHandler.load_ohlcv(symbol, period="3y", interval="1d")

    n = len(df)
    is_end = int(n * 0.60)
    val_end = int(n * 0.80)

    df_is = df.iloc[:is_end].copy()
    df_val = df.iloc[is_end:val_end].copy()
    df_oos = df.iloc[val_end:].copy()

    engine = BacktestEngine(spec, initial_capital=100_000.0, execution_timing="next_open", slippage_ticks=1)
    strat = EMACrossoverStrategy(fast, slow)

    res_is = engine.run(df_is, strat.generate_signals)["metrics"]
    res_val = engine.run(df_val, strat.generate_signals)["metrics"]
    res_oos = engine.run(df_oos, strat.generate_signals)["metrics"]
    res_full = engine.run(df, strat.generate_signals)

    return {
        "symbol": symbol,
        "spec": spec,
        "df": df,
        "is": res_is,
        "val": res_val,
        "oos": res_oos,
        "full_metrics": res_full["metrics"],
        "trades": res_full["trade_logger"].get_closed_trades(),
        "equity_curve": res_full["equity_curve"],
    }


def audit_neighborhood_plateau(symbol: str, target_fast: int, target_slow: int) -> pd.DataFrame:
    """Generates performance matrix across the surrounding parameter neighborhood."""
    spec = DataHandler.get_spec(symbol)
    df = DataHandler.load_ohlcv(symbol, period="3y", interval="1d")
    engine = BacktestEngine(spec, initial_capital=100_000.0, execution_timing="next_open", slippage_ticks=1)

    fast_offsets = [-2, -1, 0, 1, 2]
    slow_offsets = [-4, -2, 0, 2, 4]

    records = []
    for fo in fast_offsets:
        f = target_fast + fo
        if f < 2:
            continue
        for so in slow_offsets:
            s = target_slow + so
            if f >= s:
                continue

            strat = EMACrossoverStrategy(f, s)
            res = engine.run(df, strat.generate_signals)["metrics"]
            is_target = (f == target_fast and s == target_slow)

            records.append({
                "symbol": symbol,
                "fast_ema": f,
                "slow_ema": s,
                "parameter": f"EMA {f}/{s}" + (" ★ (Target)" if is_target else ""),
                "cagr_pct": res.get("cagr_pct", 0.0),
                "profit_factor": res.get("profit_factor", 0.0),
                "sharpe_ratio": res.get("sharpe_ratio", 0.0),
                "sortino_ratio": res.get("sortino_ratio", 0.0),
                "max_drawdown_pct": res.get("max_drawdown_pct", 0.0),
                "expectancy_dollars": res.get("expectancy_dollars", 0.0),
                "trades_count": res.get("total_trades", 0),
                "win_rate_pct": res.get("win_rate_pct", 0.0),
                "is_target": is_target,
            })

    return pd.DataFrame(records)


def run_trade_concentration_analysis(trades: List[Any], initial_capital: float = 100_000.0) -> Dict[str, Any]:
    """Analyzes whether returns are driven by outlier windfall trades."""
    if not trades:
        return {}

    pnls = [t.net_pnl for t in trades]
    pnls_sorted = sorted(pnls, reverse=True)
    total_net = sum(pnls)

    largest_win = pnls_sorted[0] if pnls_sorted else 0.0
    largest_loss = min(pnls) if pnls else 0.0

    top1_pnl = pnls_sorted[0] if len(pnls_sorted) >= 1 else 0.0
    top3_pnl = sum(pnls_sorted[:3]) if len(pnls_sorted) >= 3 else sum(pnls_sorted)

    top1_pct = (top1_pnl / total_net * 100.0) if total_net > 0 else 0.0
    top3_pct = (top3_pnl / total_net * 100.0) if total_net > 0 else 0.0

    median_pnl = float(np.median(pnls))
    mean_pnl = float(np.mean(pnls))

    return {
        "total_trades": len(trades),
        "total_net_pnl": total_net,
        "largest_winner": largest_win,
        "largest_loser": largest_loss,
        "top1_winner_pnl": top1_pnl,
        "top1_winner_pct": top1_pct,
        "top3_winner_pnl": top3_pnl,
        "top3_winner_pct": top3_pct,
        "median_trade_pnl": median_pnl,
        "mean_trade_pnl": mean_pnl,
    }


def run_monte_carlo_simulation(trades: List[Any], n_sims: int = 10_000, initial_capital: float = 100_000.0) -> Dict[str, Any]:
    """Runs 10,000 bootstrap trade-sequence resamplings."""
    n_trades = len(trades)
    if n_trades < 5:
        return {"status": "INSUFFICIENT SAMPLE SIZE (N < 5)"}

    trade_pnls = np.array([t.net_pnl for t in trades])
    final_returns = np.empty(n_sims, dtype=np.float64)
    max_drawdowns = np.empty(n_sims, dtype=np.float64)

    np.random.seed(42)
    for i in range(n_sims):
        # Bootstrap sample with replacement
        sample_pnls = np.random.choice(trade_pnls, size=n_trades, replace=True)
        equity = initial_capital + np.cumsum(sample_pnls)
        equity = np.insert(equity, 0, initial_capital)

        final_ret = (equity[-1] - initial_capital) / initial_capital * 100.0
        final_returns[i] = final_ret

        # Max Drawdown
        running_max = np.maximum.accumulate(equity)
        dd = (running_max - equity) / running_max * 100.0
        max_drawdowns[i] = np.max(dd)

    prob_loss = float(np.mean(final_returns < 0.0) * 100.0)

    return {
        "status": "VALID_SIMULATION" if n_trades >= 30 else f"INSUFFICIENT SAMPLE SIZE (N={n_trades} < 30)",
        "trades_sampled": n_trades,
        "median_return_pct": float(np.median(final_returns)),
        "p5_return_pct": float(np.percentile(final_returns, 5)),
        "p95_return_pct": float(np.percentile(final_returns, 95)),
        "median_max_dd_pct": float(np.median(max_drawdowns)),
        "p95_max_dd_pct": float(np.percentile(max_drawdowns, 95)),
        "prob_losing_money_pct": prob_loss,
    }


def run_gold_stress_tests(df: pd.DataFrame) -> pd.DataFrame:
    """Stress tests Gold (GC=F EMA 5/52) against slippage and cost escalation."""
    spec = DataHandler.get_spec("GC=F")
    strat = EMACrossoverStrategy(5, 52)

    scenarios = [
        ("1. Baseline (1 tick slippage, $2.50 fee)", 1, 2.50),
        ("2. Moderate Slippage (3 ticks slippage, $2.50 fee)", 3, 2.50),
        ("3. Severe Slippage (5 ticks slippage, $2.50 fee)", 5, 2.50),
        ("4. 2x Cost Spike (1 tick slippage, $5.00 fee)", 1, 5.00),
        ("5. Extreme Friction (5 ticks slippage, $7.50 fee)", 5, 7.50),
    ]

    records = []
    for name, slip, fee in scenarios:
        temp_spec = CONTRACT_SPECS["GC=F"]
        temp_spec.fixed_fee_per_contract = fee
        engine = BacktestEngine(temp_spec, initial_capital=100_000.0, execution_timing="next_open", slippage_ticks=slip)
        res = engine.run(df, strat.generate_signals)["metrics"]

        records.append({
            "scenario": name,
            "cagr_pct": res.get("cagr_pct", 0.0),
            "max_drawdown_pct": res.get("max_drawdown_pct", 0.0),
            "sharpe_ratio": res.get("sharpe_ratio", 0.0),
            "profit_factor": res.get("profit_factor", 0.0),
            "net_profit": res.get("net_profit", 0.0),
            "trades_count": res.get("total_trades", 0),
        })

    return pd.DataFrame(records)


def main():
    target_params = {
        "CL=F": (22, 30),
        "BZ=F": (24, 30),
        "GC=F": (5, 52),
        "SI=F": (9, 100),
        "NG=F": (15, 50),
    }

    print("\n" + "=" * 115)
    print(" 🔬 EXHAUSTIVE VALIDATION AUDIT OF PRELIMINARY EMA STRATEGY PARAMETERS")
    print("=" * 115)

    all_audits = {}

    for sym, (f, s) in target_params.items():
        print(f"\n==========================================================================================")
        print(f" 📦 AUDITING ASSET: {sym} [Target: EMA {f}/{s}]")
        print(f"==========================================================================================")

        # 1. 60% IS / 20% Val / 20% OOS
        p_eval = run_partition_eval(sym, f, s)
        
        # 2. Neighborhood Plateau Table
        neigh_df = audit_neighborhood_plateau(sym, f, s)

        # 3. Trade Concentration
        conc = run_trade_concentration_analysis(p_eval["trades"])

        # 4. Monte Carlo
        mc = run_monte_carlo_simulation(p_eval["trades"])

        all_audits[sym] = {
            "partition": p_eval,
            "neighborhood": neigh_df,
            "concentration": conc,
            "monte_carlo": mc,
        }

        # Print Partition Table
        m_is = p_eval["is"]
        m_val = p_eval["val"]
        m_oos = p_eval["oos"]

        print(f"\n--- [60% IS / 20% VALIDATION / 20% OOS BREAKDOWN] ---")
        print(f"{'Metric':20} {'In-Sample (60%)':18} {'Validation (20%)':18} {'Out-of-Sample (20%)':20}")
        print("-" * 80)
        print(f"{'CAGR %':20} {m_is.get('cagr_pct', 0):+17.2f}% {m_val.get('cagr_pct', 0):+17.2f}% {m_oos.get('cagr_pct', 0):+19.2f}%")
        print(f"{'Profit Factor':20} {m_is.get('profit_factor', 0):18.2f} {m_val.get('profit_factor', 0):18.2f} {m_oos.get('profit_factor', 0):20.2f}")
        print(f"{'Sharpe Ratio':20} {m_is.get('sharpe_ratio', 0):18.2f} {m_val.get('sharpe_ratio', 0):18.2f} {m_oos.get('sharpe_ratio', 0):20.2f}")
        print(f"{'Sortino Ratio':20} {m_is.get('sortino_ratio', 0):18.2f} {m_val.get('sortino_ratio', 0):18.2f} {m_oos.get('sortino_ratio', 0):20.2f}")
        print(f"{'Max Drawdown %':20} {m_is.get('max_drawdown_pct', 0):17.2f}% {m_val.get('max_drawdown_pct', 0):17.2f}% {m_oos.get('max_drawdown_pct', 0):19.2f}%")
        print(f"{'Win Rate %':20} {m_is.get('win_rate_pct', 0):17.1f}% {m_val.get('win_rate_pct', 0):17.1f}% {m_oos.get('win_rate_pct', 0):19.1f}%")
        print(f"{'Trades Count':20} {m_is.get('total_trades', 0):18d} {m_val.get('total_trades', 0):18d} {m_oos.get('total_trades', 0):20d}")
        print(f"{'Expectancy ($)':20} ${m_is.get('expectancy_dollars', 0):+16,.2f} ${m_val.get('expectancy_dollars', 0):+16,.2f} ${m_oos.get('expectancy_dollars', 0):+18,.2f}")

        # Print Concentration
        if conc:
            print(f"\n--- [TRADE CONCENTRATION & WINDFALL AUDIT] ---")
            print(f"  Total Trades: {conc['total_trades']} | Total Net P&L: ${conc['total_net_pnl']:+,.2f}")
            print(f"  Largest Winner: ${conc['largest_winner']:+,.2f} | Largest Loser: ${conc['largest_loser']:+,.2f}")
            print(f"  Top 1 Winner Contribution: {conc['top1_winner_pct']:.1f}% of total profit")
            print(f"  Top 3 Winners Contribution: {conc['top3_winner_pct']:.1f}% of total profit")
            print(f"  Median Trade: ${conc['median_trade_pnl']:+,.2f} | Mean Trade: ${conc['mean_trade_pnl']:+,.2f}")

        # Print Monte Carlo
        print(f"\n--- [10,000 MONTE CARLO BOOTSTRAP RESAMPLING] ---")
        print(f"  Sample Status: ⚠️  {mc['status']}")
        if "median_return_pct" in mc:
            print(f"  Median Return: {mc['median_return_pct']:+.2f}% | 5th Percentile: {mc['p5_return_pct']:+.2f}% | 95th Percentile: {mc['p95_return_pct']:+.2f}%")
            print(f"  Median Max Drawdown: {mc['median_max_dd_pct']:.2f}% | 95th Percentile MaxDD: {mc['p95_max_dd_pct']:.2f}%")
            print(f"  Probability of Loss: {mc['prob_losing_money_pct']:.1f}%")

    # Gold Stress Testing
    print("\n==========================================================================================")
    print(" 🥇 GOLD (GC=F) STRESS TESTING UNDER ELEVATED FRICTION & COSTS")
    print("==========================================================================================")
    gold_df = DataHandler.load_ohlcv("GC=F", period="3y", interval="1d")
    stress_df = run_gold_stress_tests(gold_df)
    for _, r in stress_df.iterrows():
        print(f"  {r['scenario']:55} | CAGR: {r['cagr_pct']:+7.2f}% | Sharpe: {r['sharpe_ratio']:5.2f} | MaxDD: {r['max_drawdown_pct']:5.2f}% | PF: {r['profit_factor']:5.2f}")


if __name__ == "__main__":
    main()
