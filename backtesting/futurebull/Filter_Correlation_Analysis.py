#!/usr/bin/env python3
"""
================================================================================
PHASE 2 & 3: COMBINED GROUP ANALYSIS & FILTER REDUNDANCY / CORRELATION ENGINE
================================================================================
Directory   : backtesting/futurebull/
Role        : Evaluates hierarchical filter combinations (A, A+B, A+B+C, A+B+D, All),
              computes Pearson/Spearman correlation matrices across the 29 filters,
              and identifies redundant indicator clusters.
Outputs:
  - reports/PHASE2_COMBINED_GROUP_METRICS.csv
  - reports/PHASE3_CORRELATION_MATRIX.csv
  - reports/PHASE3_REDUNDANCY_REPORT.csv
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


def run_phase2_and_3():
    print("================================================================================")
    print("🔬 RUNNING PHASE 2 & 3: COMBINED GROUPS & FILTER REDUNDANCY ANALYSIS")
    print("================================================================================")

    data_files = sorted(list(DATA_DIR.glob("*.parquet")))
    all_dfs = []
    for f in data_files:
        df = pd.read_parquet(f)
        all_dfs.append(compute_all_filters(df))
    combined = pd.concat(all_dfs, ignore_index=True)
    total_bars = len(combined)

    # --------------------------------------------------------------------------
    # PHASE 2: COMBINED GROUP EXPERIMENTS
    # --------------------------------------------------------------------------
    combos = {
        "A_Liquidity_InitialTrend": "COMBO_A",
        "AB_Liquidity_Trend": "COMBO_AB",
        "ABC_Liquidity_Trend_MACD": "COMBO_ABC",
        "ABD_Liquidity_Trend_Momentum": "COMBO_ABD",
        "E_Original_All_29_Conditions": "COMBO_ALL_ORIGINAL"
    }

    combo_results = []
    for name, col in combos.items():
        sub = combined[combined[col] == True]
        n_signals = len(sub)
        freq_pct = (n_signals / total_bars) * 100.0

        if n_signals > 0:
            ret_1d = sub["fwd_ret_1d"].mean()
            ret_3d = sub["fwd_ret_3d"].mean()
            ret_5d = sub["fwd_ret_5d"].mean()
            ret_10d = sub["fwd_ret_10d"].mean()
            ret_20d = sub["fwd_ret_20d"].mean()
            win_5d = (sub["fwd_ret_5d"] > 0).mean() * 100.0
            win_10d = (sub["fwd_ret_10d"] > 0).mean() * 100.0
            mfe_10d = sub["mfe_10d_pct"].mean()
            mae_10d = sub["mae_10d_pct"].mean()
            edge = abs(mfe_10d / mae_10d) if abs(mae_10d) > 0 else 1.0
        else:
            ret_1d = ret_3d = ret_5d = ret_10d = ret_20d = win_5d = win_10d = mfe_10d = mae_10d = edge = 0.0

        combo_results.append({
            "combination": name,
            "signal_column": col,
            "total_signals": n_signals,
            "frequency_pct": round(freq_pct, 2),
            "avg_ret_1d_pct": round(ret_1d, 3),
            "avg_ret_3d_pct": round(ret_3d, 3),
            "avg_ret_5d_pct": round(ret_5d, 3),
            "avg_ret_10d_pct": round(ret_10d, 3),
            "avg_ret_20d_pct": round(ret_20d, 3),
            "win_rate_5d_pct": round(win_5d, 2),
            "win_rate_10d_pct": round(win_10d, 2),
            "avg_mfe_10d_pct": round(mfe_10d, 2),
            "avg_mae_10d_pct": round(mae_10d, 2),
            "edge_ratio": round(edge, 2),
        })

    combo_df = pd.DataFrame(combo_results)
    combo_out = REPORTS_DIR / "PHASE2_COMBINED_GROUP_METRICS.csv"
    combo_df.to_csv(combo_out, index=False)
    print(f"✓ Exported Phase 2 group metrics to: {combo_out}")

    print("\n--------------------------------------------------------------------------------")
    print("📊 PHASE 2 COMBINED EXPERIMENT RESULTS:")
    print("--------------------------------------------------------------------------------")
    for _, r in combo_df.iterrows():
        print(f"  {r['combination']:<30} | Signals: {r['total_signals']:<6} ({r['frequency_pct']:>5.2f}%) | 10d Ret: {r['avg_ret_10d_pct']:+.2f}% | Win: {r['win_rate_10d_pct']:.1f}% | Edge: {r['edge_ratio']:.2f}")

    # --------------------------------------------------------------------------
    # PHASE 3: CORRELATION & REDUNDANCY ANALYSIS
    # --------------------------------------------------------------------------
    filter_cols = list(FILTER_NAMES.keys())
    bool_matrix = combined[filter_cols].astype(float)
    corr_matrix = bool_matrix.corr(method="pearson")
    corr_out = REPORTS_DIR / "PHASE3_CORRELATION_MATRIX.csv"
    corr_matrix.to_csv(corr_out)
    print(f"\n✓ Exported Phase 3 correlation matrix to: {corr_out}")

    # Key Paired Redundancy Investigations (Explicitly required in Section 7)
    investigation_pairs = [
        ("B2_RSI10_GTE_20", "D1_RSI14_GT_50", "RSI(10) vs RSI(14)"),
        ("B4_STOCHRSI10_GTE_20", "D2_STOCHRSI14_GT_50", "Stoch RSI(10) vs Stoch RSI(14)"),
        ("B14_FAST_STOCH_K_GTE_D", "B13_SLOW_STOCH_K_GTE_D", "Fast vs Slow Stochastic"),
        ("D8_EMA5_GT_EMA20", "D9_EMA20_GT_EMA50", "EMA(5/20) vs EMA(20/50)"),
        ("B15_CLOSE_GTE_SMA10", "B10_CLOSE_GTE_EMA14", "SMA(10) vs EMA(14)"),
        ("C1_MACD_LINE_GTE_SIG", "C2_MACD_HIST_GTE_0", "MACD Line vs MACD Histogram"),
        ("B8_ICHI_CONV_GTE_BASE", "B9_ICHI_SPANA_GTE_SPANB", "Ichimoku Conv/Base vs Span A/Span B"),
        ("B11_ADX_DIP_GTE_DIM", "B12_AROON_UP_GTE_DOWN", "ADX Directional vs Aroon Indicators"),
        ("D4_CLOSE_GTE_UPPER_BB", "D8_EMA5_GT_EMA20", "Bollinger Breakout vs EMA Trend"),
    ]

    redundancy_records = []
    for f1, f2, pair_name in investigation_pairs:
        corr = corr_matrix.loc[f1, f2]
        overlap = ((bool_matrix[f1] == 1.0) & (bool_matrix[f2] == 1.0)).sum()
        total_either = ((bool_matrix[f1] == 1.0) | (bool_matrix[f2] == 1.0)).sum()
        jaccard = (overlap / total_either) if total_either > 0 else 0.0

        redundancy_records.append({
            "pair": pair_name,
            "filter_1": f1,
            "filter_2": f2,
            "pearson_correlation": round(corr, 3),
            "jaccard_similarity": round(jaccard, 3),
            "verdict": "CRITICALLY_REDUNDANT" if corr > 0.85 or jaccard > 0.85 else "HIGHLY_CORRELATED" if corr > 0.65 else "DISTINCT_INFORMATION"
        })

    red_df = pd.DataFrame(redundancy_records)
    red_out = REPORTS_DIR / "PHASE3_REDUNDANCY_REPORT.csv"
    red_df.to_csv(red_out, index=False)
    print(f"✓ Exported Phase 3 redundancy report to: {red_out}")

    print("\n--------------------------------------------------------------------------------")
    print("🔍 PHASE 3 PAIRED REDUNDANCY FINDINGS:")
    print("--------------------------------------------------------------------------------")
    for _, r in red_df.iterrows():
        print(f"  {r['pair']:<35} | Corr: {r['pearson_correlation']:>+5.2f} | Jaccard: {r['jaccard_similarity']:.2f} | {r['verdict']}")
    print("================================================================================\n")


if __name__ == "__main__":
    run_phase2_and_3()
