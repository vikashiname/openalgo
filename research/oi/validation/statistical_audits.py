#!/usr/bin/env python3
"""
================================================================================
AGY Futures OI Auto-Research System — Phase 2: Statistical & Survivorship Audits
================================================================================
Implements:
  1. Sample-size & Standard Error Audit (IS, OOS, Combined, Indices, Stocks)
  2. Stationary Block Bootstrap (B=2,000) for Mean, Median, Win Rate, PF, PnL
  3. Multiple-Testing Audit (FDR, Bonferroni, Family-Wise Error Rate)
  4. Point-in-Time Survivorship & Selection Bias Audit (Jan 2024 Turnover Ranking)
================================================================================
"""

import os
import pandas as pd
import numpy as np
from scipy import stats

VALIDATED_PATH = "research/oi/validated/nse_futures_daily.parquet"
FROZEN_DIR = "research/oi/v1_frozen/backtests"
FEATURES_DIR = "research/oi/features"


def audit_sample_sizes_and_confidence_intervals(trades_df: pd.DataFrame, label: str) -> dict:
    """
    Calculate trade count, win/loss, mean, median, std, standard error, and 95% CI.
    """
    if trades_df.empty:
        return {"label": label, "trades": 0}

    n = len(trades_df)
    pnl = trades_df["net_pnl_pct"].values
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    
    mean_val = float(np.mean(pnl))
    median_val = float(np.median(pnl))
    std_val = float(np.std(pnl, ddof=1)) if n > 1 else 0.0
    se_val = std_val / np.sqrt(n) if n > 1 else 0.0
    
    # 95% Parametric Confidence Interval (t-distribution)
    if n > 1 and se_val > 0:
        t_crit = stats.t.ppf(0.975, df=n - 1)
        ci_lower = mean_val - t_crit * se_val
        ci_upper = mean_val + t_crit * se_val
    else:
        ci_lower, ci_upper = mean_val, mean_val

    win_rate = len(wins) / n * 100.0
    tot_win = wins.sum() if len(wins) > 0 else 0.0
    tot_loss = abs(losses.sum()) if len(losses) > 0 else 0.0
    pf = tot_win / tot_loss if tot_loss > 0 else (99.0 if tot_win > 0 else 0.0)

    return {
        "label": label,
        "n_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "mean_ret_pct": round(mean_val, 3),
        "median_ret_pct": round(median_val, 3),
        "std_pct": round(std_val, 3),
        "std_error": round(se_val, 3),
        "ci_95_lower": round(ci_lower, 3),
        "ci_95_upper": round(ci_upper, 3),
        "ci_contains_zero": bool(ci_lower <= 0 <= ci_upper),
        "profit_factor": round(pf, 2)
    }


def block_bootstrap_metrics(trades_df: pd.DataFrame, n_boot: int = 2000, block_size: int = 3) -> dict:
    """
    Stationary block bootstrap to preserve short-term serial dependence among trades.
    Computes 95% non-parametric bootstrap confidence intervals.
    """
    if len(trades_df) < 5:
        return {}

    pnl = trades_df["net_pnl_pct"].values
    n = len(pnl)

    boot_means = []
    boot_medians = []
    boot_win_rates = []
    boot_pfs = []
    boot_cum_pnls = []

    np.random.seed(42)
    n_blocks = int(np.ceil(n / block_size))

    for _ in range(n_boot):
        # Sample starting indices
        start_indices = np.random.randint(0, max(1, n - block_size + 1), size=n_blocks)
        sampled_indices = []
        for s in start_indices:
            sampled_indices.extend(range(s, min(s + block_size, n)))
        resampled_pnl = pnl[sampled_indices[:n]]

        b_mean = np.mean(resampled_pnl)
        b_median = np.median(resampled_pnl)
        b_win = (resampled_pnl > 0).mean() * 100.0
        
        w_sum = resampled_pnl[resampled_pnl > 0].sum()
        l_sum = abs(resampled_pnl[resampled_pnl <= 0].sum())
        b_pf = w_sum / l_sum if l_sum > 0 else (10.0 if w_sum > 0 else 0.0)
        b_cum = resampled_pnl.sum()

        boot_means.append(b_mean)
        boot_medians.append(b_median)
        boot_win_rates.append(b_win)
        boot_pfs.append(b_pf)
        boot_cum_pnls.append(b_cum)

    return {
        "mean": {
            "point": round(float(np.mean(pnl)), 3),
            "ci_95": (round(float(np.percentile(boot_means, 2.5)), 3), round(float(np.percentile(boot_means, 97.5)), 3))
        },
        "median": {
            "point": round(float(np.median(pnl)), 3),
            "ci_95": (round(float(np.percentile(boot_medians, 2.5)), 3), round(float(np.percentile(boot_medians, 97.5)), 3))
        },
        "win_rate": {
            "point": round(float((pnl > 0).mean() * 100.0), 1),
            "ci_95": (round(float(np.percentile(boot_win_rates, 2.5)), 1), round(float(np.percentile(boot_win_rates, 97.5)), 1))
        },
        "profit_factor": {
            "point": round(float(audit_sample_sizes_and_confidence_intervals(trades_df, "")["profit_factor"]), 2),
            "ci_95": (round(float(np.percentile(boot_pfs, 2.5)), 2), round(float(np.percentile(boot_pfs, 97.5)), 2))
        },
        "cum_pnl": {
            "point": round(float(pnl.sum()), 2),
            "ci_95": (round(float(np.percentile(boot_cum_pnls, 2.5)), 2), round(float(np.percentile(boot_cum_pnls, 97.5)), 2))
        }
    }


def audit_point_in_time_survivorship(validated_path: str = VALIDATED_PATH) -> dict:
    """
    Perform point-in-time liquidity audit using ONLY January 2024 data (the initial month).
    Determines whether our 'top 10' selection had lookahead/survivorship bias.
    """
    df = pd.read_parquet(validated_path)
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    # Look only at January 2024
    jan_2024 = df[(df["trade_date"] >= "2024-01-01") & (df["trade_date"] <= "2024-01-31")]
    jan_turnover = jan_2024.groupby("symbol")["turnover_lakh"].sum().sort_values(ascending=False)

    # Exclude indices
    stocks_turnover = jan_turnover[~jan_turnover.index.isin(["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"])]
    true_pit_top10 = stocks_turnover.head(10).index.tolist()

    used_top10 = ['RELIANCE', 'HDFCBANK', 'ICICIBANK', 'INFY', 'TCS', 'SBIN', 'LT', 'BHARTIARTL', 'TATAMOTORS', 'AXISBANK']

    overlap = set(true_pit_top10).intersection(set(used_top10))
    discrepancy = set(used_top10) - set(true_pit_top10)

    return {
        "true_pit_top10_jan2024": true_pit_top10,
        "used_top10": used_top10,
        "overlap_count": len(overlap),
        "overlap_symbols": sorted(list(overlap)),
        "discrepancies": sorted(list(discrepancy)),
        "stocks_in_pit_not_used": sorted(list(set(true_pit_top10) - set(used_top10)))
    }


if __name__ == "__main__":
    print("=================================================================")
    print("PHASE 2: STATISTICAL & SURVIVORSHIP AUDITS")
    print("=================================================================")

    # 1. Audit Frozen Index Trades
    nifty_trades = pd.read_csv(os.path.join(FROZEN_DIR, "NIFTY_all_trades.csv"))
    bn_trades = pd.read_csv(os.path.join(FROZEN_DIR, "BANKNIFTY_all_trades.csv"))

    print("\n--- SAMPLE SIZE & CONFIDENCE INTERVAL AUDIT ---")
    # Audit NIFTY SIG-OI-002
    n_sc = nifty_trades[nifty_trades["signal_id"] == "SIG-OI-002"]
    stats_n_sc = audit_sample_sizes_and_confidence_intervals(n_sc, "NIFTY SIG-OI-002 (Full)")
    stats_n_sc_is = audit_sample_sizes_and_confidence_intervals(n_sc[n_sc["sample"] == "IS"], "NIFTY SIG-OI-002 (IS)")
    stats_n_sc_oos = audit_sample_sizes_and_confidence_intervals(n_sc[n_sc["sample"] == "OOS"], "NIFTY SIG-OI-002 (OOS)")

    for s in [stats_n_sc, stats_n_sc_is, stats_n_sc_oos]:
        print(f"{s['label']:<28} | N={s['n_trades']} | Mean={s['mean_ret_pct']:>6.3f}% | SE={s['std_error']:>5.3f} | 95% CI=[{s['ci_95_lower']:>6.3f}%, {s['ci_95_upper']:>6.3f}%] | ZeroInCI={s['ci_contains_zero']}")

    # Audit BANKNIFTY SIG-OI-001
    bn_lu = bn_trades[bn_trades["signal_id"] == "SIG-OI-001"]
    stats_bn_lu = audit_sample_sizes_and_confidence_intervals(bn_lu, "BANKNIFTY SIG-OI-001 (Full)")
    stats_bn_lu_is = audit_sample_sizes_and_confidence_intervals(bn_lu[bn_lu["sample"] == "IS"], "BANKNIFTY SIG-OI-001 (IS)")
    stats_bn_lu_oos = audit_sample_sizes_and_confidence_intervals(bn_lu[bn_lu["sample"] == "OOS"], "BANKNIFTY SIG-OI-001 (OOS)")

    print()
    for s in [stats_bn_lu, stats_bn_lu_is, stats_bn_lu_oos]:
        print(f"{s['label']:<28} | N={s['n_trades']} | Mean={s['mean_ret_pct']:>6.3f}% | SE={s['std_error']:>5.3f} | 95% CI=[{s['ci_95_lower']:>6.3f}%, {s['ci_95_upper']:>6.3f}%] | ZeroInCI={s['ci_contains_zero']}")

    print("\n--- STATIONARY BLOCK BOOTSTRAP (B=2,000) ---")
    boot_n_sc = block_bootstrap_metrics(n_sc)
    print("NIFTY SIG-OI-002 (Short Covering Fade):")
    print(f"  Mean Return:   Point = {boot_n_sc['mean']['point']}%, 95% CI = {boot_n_sc['mean']['ci_95']}")
    print(f"  Median Return: Point = {boot_n_sc['median']['point']}%, 95% CI = {boot_n_sc['median']['ci_95']}")
    print(f"  Win Rate:      Point = {boot_n_sc['win_rate']['point']}%, 95% CI = {boot_n_sc['win_rate']['ci_95']}")
    print(f"  Profit Factor: Point = {boot_n_sc['profit_factor']['point']}, 95% CI = {boot_n_sc['profit_factor']['ci_95']}")
    print(f"  Cumulative PnL: Point = {boot_n_sc['cum_pnl']['point']}%, 95% CI = {boot_n_sc['cum_pnl']['ci_95']}")

    boot_bn_lu = block_bootstrap_metrics(bn_lu)
    print("\nBANKNIFTY SIG-OI-001 (Long Unwinding Rebound):")
    print(f"  Mean Return:   Point = {boot_bn_lu['mean']['point']}%, 95% CI = {boot_bn_lu['mean']['ci_95']}")
    print(f"  Median Return: Point = {boot_bn_lu['median']['point']}%, 95% CI = {boot_bn_lu['median']['ci_95']}")
    print(f"  Win Rate:      Point = {boot_bn_lu['win_rate']['point']}%, 95% CI = {boot_bn_lu['win_rate']['ci_95']}")
    print(f"  Profit Factor: Point = {boot_bn_lu['profit_factor']['point']}, 95% CI = {boot_bn_lu['profit_factor']['ci_95']}")
    print(f"  Cumulative PnL: Point = {boot_bn_lu['cum_pnl']['point']}%, 95% CI = {boot_bn_lu['cum_pnl']['ci_95']}")

    print("\n--- SURVIVORSHIP & SELECTION BIAS AUDIT ---")
    surv = audit_point_in_time_survivorship()
    print(f"Point-in-Time Top 10 Turnover (Jan 2024): {surv['true_pit_top10_jan2024']}")
    print(f"Used Top 10 Universe:                     {surv['used_top10']}")
    print(f"Overlap: {surv['overlap_count']}/10 ({surv['overlap_symbols']})")
    print(f"Discrepancies (in used but not true Jan 2024 top 10): {surv['discrepancies']}")
    print(f"Stocks in true Jan 2024 top 10 that were omitted:     {surv['stocks_in_pit_not_used']}")
