"""
Master AutoResearch Runner
File: backtesting/emacrossopen/autoresearch/runner.py

Orchestrates the Karpathy-style autonomous research loop:
  1. Preloads and caches multi-timeframe data
  2. Generates candidate hypotheses across timeframes, directions, and exits
  3. Executes chronological multi-symbol backtests
  4. Passes results through strict overfitting gates
  5. Records all results to research_leaderboard.csv
  6. Identifies and announces the Pareto-optimal Champion
"""

import sys
import time
from pathlib import Path
from typing import Dict
import pandas as pd

# Add parent directory to path so imports work cleanly
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from resampler import load_resampled_dataset
from backtest_harness import run_portfolio_backtest
from overfitting_gate import evaluate_candidate
from leaderboard import ExperimentLeaderboard
from hypothesis_generator import generate_experiment_suite


def precompute_htf_biases(datasets: Dict[str, Dict[str, pd.DataFrame]]) -> Dict[str, Dict[str, pd.Series]]:
    """
    Precomputes Higher-Timeframe (HTF) trend bias for each symbol:
      - 1d bias: 1 if Close > EMA26 else -1
      - 125m bias: 1 if Close > EMA26 else -1
    """
    biases = {}
    for htf in ["1d", "125m"]:
        biases[htf] = {}
        ds = datasets.get(htf, {})
        for sym, df in ds.items():
            close = df["Close"]
            ema26 = close.ewm(span=26, adjust=False).mean()
            bias = pd.Series(0, index=df.index)
            bias[close > ema26] = 1
            bias[close < ema26] = -1
            biases[htf][sym] = bias
    return biases


def main():
    print("=" * 85)
    print("🤖 STARTING OPENALGO AUTORESEARCH ENGINE (KARPATHY-STYLE QUANT LOOP)")
    print("=" * 85)

    start_time = time.time()
    leaderboard = ExperimentLeaderboard()

    # Step 1: Preload multi-timeframe datasets
    print("\n[Step 1/3] Preloading multi-timeframe datasets into memory...")
    timeframes = ["1h", "75m", "125m", "4h", "1d"]
    datasets = {}
    for tf in timeframes:
        t0 = time.time()
        datasets[tf] = load_resampled_dataset(tf)
        print(f"  ✓ Cached {tf:4s}: {len(datasets[tf])} symbols in {time.time() - t0:.2f}s")

    # Step 2: Precompute HTF biases for Dual MTF experiments
    print("\n[Step 2/3] Precomputing Higher-Timeframe (HTF) trend bias series...")
    htf_biases = precompute_htf_biases(datasets)
    print("  ✓ Daily and 125m trend filters ready.")

    # Step 3: Generate and execute hypotheses
    suite = generate_experiment_suite()
    print(f"\n[Step 3/3] Executing {len(suite)} autonomous quantitative experiments...\n")

    champion = None
    champion_pf = 0.0

    print(f"{'Run ID':<8} | {'Hypothesis Name':<38} | {'TF':<5} | {'Mode':<11} | {'IS PF':<6} | {'OOS PF':<6} | {'OOS Ret':<8} | {'MaxDD':<7} | {'Status'}")
    print("-" * 115)

    for idx, exp in enumerate(suite, start=1):
        run_id = f"EXP_{idx:03d}"
        tf = exp.get("timeframe", "1h")
        target_ds = datasets.get(tf, {})

        # HTF filter if specified
        htf_filter_name = exp.get("htf_filter")
        htf_bias_map = htf_biases.get(htf_filter_name) if htf_filter_name else None

        # Execute Backtest
        overall, is_m, oos_m = run_portfolio_backtest(
            dataset=target_ds,
            fast_ema=exp.get("fast_ema", 9),
            slow_ema=exp.get("slow_ema", 26),
            macd_fast=exp.get("macd_fast", 12),
            macd_slow=exp.get("macd_slow", 26),
            macd_sig=exp.get("macd_sig", 9),
            direction_mode=exp.get("direction_mode", "SYMMETRICAL"),
            exit_type=exp.get("exit_type", "REVERSAL"),
            long_tp_pct=exp.get("long_tp_pct", 3.0),
            short_tp_pct=exp.get("short_tp_pct", 1.5),
            sl_pct=exp.get("sl_pct", 6.0),
            atr_mult=exp.get("atr_mult", 2.0),
            htf_bias_map=htf_bias_map,
        )

        # Evaluate against Overfitting Gates
        is_accepted, gate_reason = evaluate_candidate(overall, is_m, oos_m)

        status = "REJECTED"
        if is_accepted:
            if oos_m["profit_factor"] > champion_pf:
                status = "CHAMPION"
                champion = (run_id, exp, overall, is_m, oos_m)
                champion_pf = oos_m["profit_factor"]
            else:
                status = "ACCEPTED"

        # Record in Leaderboard CSV
        leaderboard.record_experiment(
            run_id=run_id,
            hypothesis_name=exp["hypothesis_name"],
            config=exp,
            overall=overall,
            in_sample=is_m,
            out_of_sample=oos_m,
            status=status,
            notes=f"{exp.get('notes', '')} | {gate_reason}",
        )

        # Formatted console output
        hypo_name = exp["hypothesis_name"][:36]
        mode_str = exp.get("direction_mode", "SYM")[:10]
        status_icon = "🏆 CHAMPION" if status == "CHAMPION" else ("✅ ACCEPTED" if status == "ACCEPTED" else "❌ REJECTED")
        print(
            f"{run_id:<8} | {hypo_name:<38} | {tf:<5} | {mode_str:<11} | "
            f"{is_m['profit_factor']:<6.2f} | {oos_m['profit_factor']:<6.2f} | "
            f"{oos_m['total_return']:+7.1f}% | {overall['max_drawdown']:<6.1f}% | {status_icon}"
        )

    total_time = time.time() - start_time
    print("=" * 115)
    print(f"\n🎉 AUTORESEARCH COMPLETE in {total_time:.2f} seconds!")
    print(f"Results saved to: {leaderboard.csv_path}")

    # Top Champions Leaderboard
    print("\n" + "=" * 85)
    print("🏆 TOP 5 AUTORESEARCH STRATEGY CHAMPIONS (Ranked by Out-of-Sample PF)")
    print("=" * 85)
    top_df = leaderboard.get_top_champions(5)
    if not top_df.empty:
        disp_cols = ["run_id", "hypothesis_name", "timeframe", "direction_mode", "exit_type", "is_pf", "oos_pf", "oos_return", "overall_pf", "max_drawdown"]
        print(top_df[disp_cols].to_string(index=False))
    else:
        print("No models survived the strict acceptance gates.")
    print("=" * 85)


if __name__ == "__main__":
    main()
