"""
Statistical Predictive Analysis Engine
File: backtesting/emacrossopen/predictive_research.py

Evaluates whether Candle, Volume, EMA, MACD, and Volatility features
have predictive power for future MFE, MAE, and Target-before-SL probability.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

def run_predictive_analysis():
    csv_path = Path(__file__).resolve().parent / "v2_trades_with_features.csv"
    if not csv_path.exists():
        print("Trades CSV not found! Run feature_extractor.py first.")
        return

    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} trades for predictive factor research.")

    # 1. Stop Loss Distribution / Adverse Excursion Analysis
    sl_thresholds = [0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.50, 3.00, 3.50, 4.00, 5.00]
    sl_rows = []
    for sl in sl_thresholds:
        hit_all = (df["mae_pct"] >= sl).mean() * 100.0
        hit_long = (df[df["direction"] == "LONG"]["mae_pct"] >= sl).mean() * 100.0
        hit_short = (df[df["direction"] == "SHORT"]["mae_pct"] >= sl).mean() * 100.0
        hit_is = (df[df["sample"] == "IS"]["mae_pct"] >= sl).mean() * 100.0
        hit_oos = (df[df["sample"] == "OOS"]["mae_pct"] >= sl).mean() * 100.0
        survival = 100.0 - hit_all
        sl_rows.append({
            "SL_Level_Pct": f"-{sl:.2f}%",
            "Hit_Rate_All_Pct": round(hit_all, 2),
            "Survival_Rate_Pct": round(survival, 2),
            "Hit_Rate_Long_Pct": round(hit_long, 2),
            "Hit_Rate_Short_Pct": round(hit_short, 2),
            "Hit_Rate_IS_Pct": round(hit_is, 2),
            "Hit_Rate_OOS_Pct": round(hit_oos, 2),
        })
    sl_dist_df = pd.DataFrame(sl_rows)
    sl_dist_path = Path(__file__).resolve().parent / "research_sl_distribution.csv"
    sl_dist_df.to_csv(sl_dist_path, index=False)
    print("\n--- ADVERSE EXCURSION (STOP LOSS) DISTRIBUTION ---")
    print(sl_dist_df.to_string(index=False))

    # 2. Target Potential / MFE Distribution
    tp_thresholds = [0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.50, 3.00, 3.50, 4.00, 5.00]
    tp_rows = []
    for tp in tp_thresholds:
        reach_all = (df["mfe_pct"] >= tp).mean() * 100.0
        reach_long = (df[df["direction"] == "LONG"]["mfe_pct"] >= tp).mean() * 100.0
        reach_short = (df[df["direction"] == "SHORT"]["mfe_pct"] >= tp).mean() * 100.0
        reach_is = (df[df["sample"] == "IS"]["mfe_pct"] >= tp).mean() * 100.0
        reach_oos = (df[df["sample"] == "OOS"]["mfe_pct"] >= tp).mean() * 100.0
        tp_rows.append({
            "Target_Level_Pct": f"+{tp:.2f}%",
            "Reach_Rate_All_Pct": round(reach_all, 2),
            "Reach_Rate_Long_Pct": round(reach_long, 2),
            "Reach_Rate_Short_Pct": round(reach_short, 2),
            "Reach_Rate_IS_Pct": round(reach_is, 2),
            "Reach_Rate_OOS_Pct": round(reach_oos, 2),
        })
    tp_dist_df = pd.DataFrame(tp_rows)
    tp_dist_path = Path(__file__).resolve().parent / "research_tp_distribution.csv"
    tp_dist_df.to_csv(tp_dist_path, index=False)
    print("\n--- FAVORABLE EXCURSION (TARGET) DISTRIBUTION ---")
    print(tp_dist_df.to_string(index=False))

    # 3. Correlation Analysis between Setup Factors and Outcomes
    feature_cols = [
        "f_body_to_range",
        "f_close_location",
        "f_candle_atr_norm",
        "f_body_atr_norm",
        "f_rel_volume",
        "f_vol_expansion",
        "f_vol_ratio_prev",
        "f_ema_sep",
        "f_ema_sep_atr",
        "f_ema_expanding",
        "f_macd_xover_str",
        "f_hist_value",
        "f_hist_expanding",
        "f_atr_pct",
        "f_strength_score",
    ]

    target_cols = ["mfe_pct", "mae_pct", "mfe_atr", "mae_atr", "baseline_pnl_pct"]

    corr_rows = []
    for f in feature_cols:
        row = {"Feature": f}
        for t in target_cols:
            valid_mask = ~df[f].isna() & ~df[t].isna()
            p_corr, p_val = stats.pearsonr(df.loc[valid_mask, f], df.loc[valid_mask, t])
            s_corr, s_val = stats.spearmanr(df.loc[valid_mask, f], df.loc[valid_mask, t])
            row[f"{t}_pearson"] = round(p_corr, 4)
            row[f"{t}_p_val"] = round(p_val, 4)
            row[f"{t}_spearman"] = round(s_corr, 4)
        corr_rows.append(row)

    corr_df = pd.DataFrame(corr_rows)
    corr_path = Path(__file__).resolve().parent / "research_feature_correlations.csv"
    corr_df.to_csv(corr_path, index=False)
    print("\n--- FACTOR CORRELATIONS WITH OUTCOMES ---")
    summary_corr = corr_df[["Feature", "mfe_pct_spearman", "mae_pct_spearman", "baseline_pnl_pct_spearman"]]
    print(summary_corr.to_string(index=False))

    # 4. Strength Score Stratification Analysis
    print("\n--- STRENGTH SCORE STRATIFICATION ANALYSIS ---")
    strat_rows = []
    for score in sorted(df["f_strength_score"].unique()):
        sub = df[df["f_strength_score"] == score]
        win_rate = (sub["baseline_pnl_pct"] > 0).mean() * 100.0
        avg_ret = sub["baseline_pnl_pct"].mean()
        med_ret = sub["baseline_pnl_pct"].median()
        avg_mfe = sub["mfe_pct"].mean()
        avg_mae = sub["mae_pct"].mean()
        mfe_mae_ratio = avg_mfe / max(avg_mae, 1e-4)

        # Target-before-SL reach probability (Target +1.50% vs SL -1.50%)
        t_before_s = ((sub["mfe_pct"] >= 1.50) & (sub["mae_pct"] < 1.50)).mean() * 100.0
        both_hit = ((sub["mfe_pct"] >= 1.50) & (sub["mae_pct"] >= 1.50)).mean() * 100.0
        sl_only = ((sub["mfe_pct"] < 1.50) & (sub["mae_pct"] >= 1.50)).mean() * 100.0
        neither = ((sub["mfe_pct"] < 1.50) & (sub["mae_pct"] < 1.50)).mean() * 100.0

        strat_rows.append({
            "Strength_Score": int(score),
            "Trade_Count": len(sub),
            "Pct_of_Trades": round(len(sub) / len(df) * 100.0, 1),
            "Win_Rate_Pct": round(win_rate, 2),
            "Avg_Return_Pct": round(avg_ret, 3),
            "Median_Return_Pct": round(med_ret, 3),
            "Avg_MFE_Pct": round(avg_mfe, 2),
            "Avg_MAE_Pct": round(avg_mae, 2),
            "MFE_MAE_Ratio": round(mfe_mae_ratio, 2),
            "T_before_SL_1.5pct": round(t_before_s, 2),
            "Both_Reached_1.5pct": round(both_hit, 2),
            "SL_Only_1.5pct": round(sl_only, 2),
            "Neither_1.5pct": round(neither, 2),
        })

    strat_df = pd.DataFrame(strat_rows)
    strat_path = Path(__file__).resolve().parent / "research_strength_stratification.csv"
    strat_df.to_csv(strat_path, index=False)
    print(strat_df.to_string(index=False))

    # Statistical significance of Strength Score
    high_str = df[df["f_strength_score"] >= 3]["baseline_pnl_pct"]
    low_str = df[df["f_strength_score"] <= 1]["baseline_pnl_pct"]
    t_stat, p_val = stats.ttest_ind(high_str, low_str, equal_var=False)
    u_stat, u_pval = stats.mannwhitneyu(high_str, low_str)
    print(f"\nStatistical Test (High Score >=3 vs Low Score <=1 Return):")
    print(f"  - Welch's t-test: t={t_stat:.4f}, p={p_val:.4e}")
    print(f"  - Mann-Whitney U test: U={u_stat:.1f}, p={u_pval:.4e}")

    # Also test high score vs low score on MFE
    high_mfe = df[df["f_strength_score"] >= 3]["mfe_pct"]
    low_mfe = df[df["f_strength_score"] <= 1]["mfe_pct"]
    t_mfe, p_mfe = stats.ttest_ind(high_mfe, low_mfe, equal_var=False)
    print(f"Statistical Test (High Score >=3 vs Low Score <=1 MFE):")
    print(f"  - Welch's t-test on MFE: t={t_mfe:.4f}, p={p_mfe:.4e}")

    print(f"\nPredictive analysis completed. Results saved to CSV files in {Path(__file__).parent}")

if __name__ == "__main__":
    run_predictive_analysis()
