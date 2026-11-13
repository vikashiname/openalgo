#!/usr/bin/env python3
"""
================================================================================
PHASE 1: INDIVIDUAL FILTER PERFORMANCE & PREDICTIVE POWER ANALYSIS
================================================================================
Evaluates each of the 29 individual scanner conditions independently across
the full 46 liquid F&O stocks universe (66,470 bar-days, 2021-2026).

Calculates for every filter:
  - Total signal count
  - Signal frequency (% of universe bars)
  - Avg 1-day, 3-day, 5-day, 10-day, 20-day forward return (%)
  - Win rate (% of profitable signals at 5d / 10d)
  - Max Favorable Excursion (MFE 10d %)
  - Max Adverse Excursion (MAE 10d %)
  - Predictive Score & Ranking (Strongest vs Weakest / Redundant)
================================================================================
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from scanner_engine import compute_all_filters, FILTER_NAMES

DATA_DIR = CURRENT_DIR / "data"
REPORTS_DIR = CURRENT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def run_phase1_analysis():
    print("================================================================================")
    print("🔬 RUNNING PHASE 1: INDIVIDUAL FILTER PREDICTIVE POWER ANALYSIS (29 FILTERS)")
    print("================================================================================")

    data_files = sorted(list(DATA_DIR.glob("*.parquet")))
    if not data_files:
        sys.exit("Error: No data files found in data/ directory. Run download_fno_data.py first.")

    all_dfs = []
    print(f"Loading and computing indicators across {len(data_files)} F&O stock datasets...")
    for f in data_files:
        df = pd.read_parquet(f)
        symbol = f.stem
        df["symbol"] = symbol
        processed = compute_all_filters(df)
        all_dfs.append(processed)

    combined = pd.concat(all_dfs, ignore_index=True)
    total_bars = len(combined)
    print(f"Total Universe Bars Evaluated: {total_bars:,}")

    metrics = []

    for f_code, f_name in FILTER_NAMES.items():
        sub = combined[combined[f_code] == True]
        n_signals = len(sub)
        pct_universe = (n_signals / total_bars) * 100.0

        if n_signals > 0:
            avg_ret_1d = sub["fwd_ret_1d"].mean()
            avg_ret_3d = sub["fwd_ret_3d"].mean()
            avg_ret_5d = sub["fwd_ret_5d"].mean()
            avg_ret_10d = sub["fwd_ret_10d"].mean()
            avg_ret_20d = sub["fwd_ret_20d"].mean()

            win_rate_5d = (sub["fwd_ret_5d"] > 0).mean() * 100.0
            win_rate_10d = (sub["fwd_ret_10d"] > 0).mean() * 100.0

            avg_mfe_10d = sub["mfe_10d_pct"].mean()
            avg_mae_10d = sub["mae_10d_pct"].mean()
            edge_ratio = abs(avg_mfe_10d / avg_mae_10d) if abs(avg_mae_10d) > 0 else 1.0
        else:
            avg_ret_1d = avg_ret_3d = avg_ret_5d = avg_ret_10d = avg_ret_20d = 0.0
            win_rate_5d = win_rate_10d = 0.0
            avg_mfe_10d = avg_mae_10d = 0.0
            edge_ratio = 0.0

        # Note flags for anomalies
        flags = []
        if f_code == "B3_EMA20_GT_20":
            flags.append("PASS_THROUGH_ABSOLUTE_PRICE_THRESHOLD")
        elif pct_universe > 95.0:
            flags.append("NEAR_ZERO_SELECTIVITY")
        elif pct_universe < 2.0:
            flags.append("HYPER_RESTRICTIVE")

        metrics.append({
            "filter_code": f_code,
            "filter_description": f_name,
            "total_signals": n_signals,
            "frequency_pct": round(pct_universe, 2),
            "avg_ret_1d_pct": round(avg_ret_1d, 3),
            "avg_ret_3d_pct": round(avg_ret_3d, 3),
            "avg_ret_5d_pct": round(avg_ret_5d, 3),
            "avg_ret_10d_pct": round(avg_ret_10d, 3),
            "avg_ret_20d_pct": round(avg_ret_20d, 3),
            "win_rate_5d_pct": round(win_rate_5d, 2),
            "win_rate_10d_pct": round(win_rate_10d, 2),
            "avg_mfe_10d_pct": round(avg_mfe_10d, 2),
            "avg_mae_10d_pct": round(avg_mae_10d, 2),
            "edge_ratio": round(edge_ratio, 2),
            "flags": "; ".join(flags) if flags else "NORMAL"
        })

    metrics_df = pd.DataFrame(metrics)
    # Sort by 10-day forward return
    metrics_df = metrics_df.sort_values(by="avg_ret_10d_pct", ascending=False).reset_index(drop=True)

    out_csv = REPORTS_DIR / "PHASE1_INDIVIDUAL_FILTER_METRICS.csv"
    metrics_df.to_csv(out_csv, index=False)
    print(f"\n✓ Exported Phase 1 metrics to: {out_csv}")

    print("\n--------------------------------------------------------------------------------")
    print("🏆 TOP 5 STRONGEST FILTERS (BY 10-DAY FORWARD RETURN):")
    print("--------------------------------------------------------------------------------")
    for i, r in metrics_df.head(5).iterrows():
        print(f"  {r['filter_code']:<25} | 10d Ret: {r['avg_ret_10d_pct']:+.2f}% | WinRate: {r['win_rate_10d_pct']:.1f}% | Freq: {r['frequency_pct']:.1f}% | {r['filter_description']}")

    print("\n--------------------------------------------------------------------------------")
    print("⚠️ 5 WEAKEST / LEAST SELECTIVE FILTERS:")
    print("--------------------------------------------------------------------------------")
    for i, r in metrics_df.tail(5).iterrows():
        print(f"  {r['filter_code']:<25} | 10d Ret: {r['avg_ret_10d_pct']:+.2f}% | WinRate: {r['win_rate_10d_pct']:.1f}% | Freq: {r['frequency_pct']:.1f}% | Flags: {r['flags']}")
    print("================================================================================\n")


if __name__ == "__main__":
    run_phase1_analysis()
