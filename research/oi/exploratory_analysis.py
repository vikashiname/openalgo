#!/usr/bin/env python3
"""
================================================================================
AGY Futures OI Auto-Research System — Phase 3: Exploratory Data Analysis (EDA)
================================================================================
Empirically tests the primary research question:
  "Does the combination of PRICE + OI + OI CHANGE + VOLUME + SEQUENCE
   provide statistically significant predictive information for future price movement?"

Order of Execution:
  1. Unconditional baseline distribution
  2. 4-State Price/OI classification (Long Buildup, Short Buildup, Short Covering, Long Unwinding)
  3. Conditional forward return distributions (t+1, t+2, t+3, t+5)
  4. Two-sample statistical tests (Welch's t-test, Mann-Whitney U) vs unconditional baseline
  5. Sequence persistence analysis (consecutive states)
  6. Volume confluence filtering
================================================================================
"""

import os
import pandas as pd
import numpy as np
from scipy import stats

NORMALIZED_DIR = "research/oi/normalized"
REPORTS_DIR = "research/oi/reports"


def load_normalized_series(symbol: str) -> pd.DataFrame:
    """Load normalized continuous dataset for symbol."""
    fp = os.path.join(NORMALIZED_DIR, f"{symbol}_continuous.parquet")
    if not os.path.exists(fp):
        raise FileNotFoundError(f"Continuous series not found at {fp}")
    df = pd.read_parquet(fp)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def engineer_eda_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute forward returns and state classifications.
    Uses Total Futures OI to eliminate contract rollover cliffs.
    """
    df = df.copy()

    # 1. Forward Returns (Predictive targets)
    df["fwd_ret_1d"] = (df["close"].shift(-1) / df["close"] - 1.0) * 100.0
    df["fwd_ret_2d"] = (df["close"].shift(-2) / df["close"] - 1.0) * 100.0
    df["fwd_ret_3d"] = (df["close"].shift(-3) / df["close"] - 1.0) * 100.0
    df["fwd_ret_5d"] = (df["close"].shift(-5) / df["close"] - 1.0) * 100.0

    # 2. Daily Price and OI Changes
    df["price_chg_pct"] = (df["close"] / df["close"].shift(1) - 1.0) * 100.0
    df["oi_chg_pct"] = (df["total_futures_oi"] / df["total_futures_oi"].shift(1) - 1.0) * 100.0
    df["vol_chg_pct"] = (df["total_futures_vol"] / df["total_futures_vol"].shift(1) - 1.0) * 100.0

    # 3. Volume 5-day SMA relative ratio
    df["vol_sma5"] = df["total_futures_vol"].rolling(5).mean()
    df["vol_rel_ratio"] = df["total_futures_vol"] / df["vol_sma5"]

    # 4. Classical 4-State Classification (Descriptive labels, not signals)
    # Price UP + OI UP   -> Long Buildup
    # Price DOWN + OI UP -> Short Buildup
    # Price UP + OI DOWN -> Short Covering
    # Price DOWN + OI DOWN -> Long Unwinding
    conditions = [
        (df["price_chg_pct"] > 0) & (df["oi_chg_pct"] > 0),
        (df["price_chg_pct"] < 0) & (df["oi_chg_pct"] > 0),
        (df["price_chg_pct"] > 0) & (df["oi_chg_pct"] < 0),
        (df["price_chg_pct"] < 0) & (df["oi_chg_pct"] < 0),
    ]
    states = ["LONG_BUILDUP", "SHORT_BUILDUP", "SHORT_COVERING", "LONG_UNWINDING"]
    df["market_state"] = np.select(conditions, states, default="NEUTRAL")

    # 5. Sequence Persistence (Consecutive state count)
    state_series = df["market_state"]
    persistence = []
    current_count = 1
    for i in range(len(state_series)):
        if i == 0:
            persistence.append(1)
        elif state_series.iloc[i] == state_series.iloc[i-1]:
            current_count += 1
            persistence.append(current_count)
        else:
            current_count = 1
            persistence.append(1)
    df["state_persistence"] = persistence

    # 6. Prior Day State
    df["prev_state"] = df["market_state"].shift(1)
    df["two_bar_sequence"] = df["prev_state"] + "->" + df["market_state"]

    return df


def analyze_unconditional_baseline(df: pd.DataFrame) -> dict:
    """Compute benchmark unconditional return distributions."""
    valid_1d = df["fwd_ret_1d"].dropna()
    valid_2d = df["fwd_ret_2d"].dropna()
    valid_3d = df["fwd_ret_3d"].dropna()
    valid_5d = df["fwd_ret_5d"].dropna()

    return {
        "n_samples": len(valid_1d),
        "fwd_1d": {
            "mean": float(valid_1d.mean()),
            "std": float(valid_1d.std()),
            "median": float(valid_1d.median()),
            "win_rate": float((valid_1d > 0).mean() * 100.0),
        },
        "fwd_3d": {
            "mean": float(valid_3d.mean()),
            "std": float(valid_3d.std()),
            "median": float(valid_3d.median()),
            "win_rate": float((valid_3d > 0).mean() * 100.0),
        },
        "fwd_5d": {
            "mean": float(valid_5d.mean()),
            "std": float(valid_5d.std()),
            "median": float(valid_5d.median()),
            "win_rate": float((valid_5d > 0).mean() * 100.0),
        }
    }


def evaluate_state_predictive_power(df: pd.DataFrame, horizon: str = "fwd_ret_1d") -> pd.DataFrame:
    """
    Test whether market states predict forward returns with statistical significance.
    Applies Welch's two-sample t-test against the unconditional population.
    """
    clean = df.dropna(subset=[horizon, "market_state"]).copy()
    baseline = clean[horizon]
    base_mean = baseline.mean()

    results = []
    for state in ["LONG_BUILDUP", "SHORT_BUILDUP", "SHORT_COVERING", "LONG_UNWINDING"]:
        subset = clean[clean["market_state"] == state][horizon]
        n = len(subset)
        if n < 5:
            continue

        mean_ret = subset.mean()
        std_ret = subset.std()
        median_ret = subset.median()
        win_rate = (subset > 0).mean() * 100.0
        
        # Two-sample Welch t-test vs baseline
        t_stat, p_val = stats.ttest_ind(subset, baseline, equal_var=False)
        # Mann-Whitney non-parametric test
        u_stat, u_pval = stats.mannwhitneyu(subset, baseline, alternative="two-sided")

        # Effect size (Cohen's d)
        pooled_std = np.sqrt(((n - 1) * std_ret**2 + (len(baseline) - 1) * baseline.std()**2) / (n + len(baseline) - 2))
        cohens_d = (mean_ret - base_mean) / pooled_std if pooled_std > 0 else 0.0

        is_significant = p_val < 0.05

        results.append({
            "state": state,
            "count": n,
            "frequency_pct": round(n / len(clean) * 100.0, 1),
            "mean_fwd_ret": round(mean_ret, 3),
            "median_fwd_ret": round(median_ret, 3),
            "win_rate_pct": round(win_rate, 1),
            "alpha_vs_baseline": round(mean_ret - base_mean, 3),
            "cohens_d": round(cohens_d, 3),
            "t_statistic": round(t_stat, 3),
            "p_value": round(p_val, 4),
            "mann_whitney_p": round(u_pval, 4),
            "statistically_significant": is_significant
        })

    return pd.DataFrame(results)


def evaluate_sequence_predictive_power(df: pd.DataFrame, horizon: str = "fwd_ret_1d") -> pd.DataFrame:
    """
    Test whether sequence persistence (e.g. 2 consecutive days of Long Buildup)
    creates stronger predictive edges than single-bar states.
    """
    clean = df.dropna(subset=[horizon, "two_bar_sequence"]).copy()
    baseline = clean[horizon]
    base_mean = baseline.mean()

    results = []
    # Test top sequences with sufficient observations
    seq_counts = clean["two_bar_sequence"].value_counts()
    eligible_seqs = seq_counts[seq_counts >= 5].index.tolist()

    for seq in eligible_seqs:
        subset = clean[clean["two_bar_sequence"] == seq][horizon]
        n = len(subset)
        mean_ret = subset.mean()
        win_rate = (subset > 0).mean() * 100.0

        t_stat, p_val = stats.ttest_ind(subset, baseline, equal_var=False)

        results.append({
            "sequence": seq,
            "count": n,
            "mean_fwd_ret": round(mean_ret, 3),
            "win_rate_pct": round(win_rate, 1),
            "alpha_vs_base": round(mean_ret - base_mean, 3),
            "p_value": round(p_val, 4),
            "significant_at_05": p_val < 0.05
        })

    return pd.DataFrame(results).sort_values("count", ascending=False)


def run_full_eda(symbol: str = "NIFTY") -> dict:
    """Execute complete EDA pipeline and generate summary report."""
    raw_norm = load_normalized_series(symbol)
    df = engineer_eda_features(raw_norm)

    baseline = analyze_unconditional_baseline(df)
    eval_1d = evaluate_state_predictive_power(df, "fwd_ret_1d")
    eval_3d = evaluate_state_predictive_power(df, "fwd_ret_3d")
    eval_5d = evaluate_state_predictive_power(df, "fwd_ret_5d")
    seq_eval = evaluate_sequence_predictive_power(df, "fwd_ret_1d")

    return {
        "symbol": symbol,
        "n_sessions": len(df),
        "baseline": baseline,
        "states_1d": eval_1d,
        "states_3d": eval_3d,
        "states_5d": eval_5d,
        "sequences": seq_eval,
        "df_featured": df
    }


if __name__ == "__main__":
    for sym in ["NIFTY", "BANKNIFTY"]:
        res = run_full_eda(sym)
        print(f"\n================================================================")
        print(f"EXPLORATORY ANALYSIS: {sym} ({res['n_sessions']} Sessions)")
        print(f"================================================================")
        b1 = res["baseline"]["fwd_1d"]
        print(f"Unconditional 1D Baseline: Mean = {b1['mean']:.3f}%, Win Rate = {b1['win_rate']:.1f}%")
        
        print("\n--- 1-Day Forward State Evaluation ---")
        print(res["states_1d"][["state", "count", "frequency_pct", "mean_fwd_ret", "win_rate_pct", "alpha_vs_baseline", "p_value", "statistically_significant"]])

        print("\n--- 3-Day Forward State Evaluation ---")
        print(res["states_3d"][["state", "count", "mean_fwd_ret", "win_rate_pct", "alpha_vs_baseline", "p_value", "statistically_significant"]])

        print("\n--- 5-Day Forward State Evaluation ---")
        print(res["states_5d"][["state", "count", "mean_fwd_ret", "win_rate_pct", "alpha_vs_baseline", "p_value", "statistically_significant"]])

        print("\n--- Two-Bar Sequence Performance (Top 5) ---")
        print(res["sequences"].head(5)[["sequence", "count", "mean_fwd_ret", "win_rate_pct", "alpha_vs_base", "p_value"]])
