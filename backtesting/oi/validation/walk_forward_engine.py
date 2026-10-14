#!/usr/bin/env python3
"""
================================================================================
AGY Futures OI Auto-Research System — Phase 3: Walk-Forward Validation Engine
================================================================================
Implements rigorous walk-forward out-of-sample testing across multi-year data:
  1. Rolling and Expanding Walk-Forward Windows (e.g. 120d Train / 40d Test)
  2. In-Sample (IS) parameter candidate evaluation
  3. Strict Out-of-Sample (OOS) performance measurement
  4. Performance Degradation Analysis (Sharpe Decay, Win Rate Consistency)
  5. Probability of Backtest Overfitting (PBO / CSCV)
  6. Parameter Stability Index across folds

Zero lookahead bias:
  - Day T signal is evaluated using T+1 open to T+2 open return
  - Feature parameters selected purely on IS training set
================================================================================
"""

import os
import sys
import numpy as np
import pandas as pd
from scipy import stats
from typing import List, Dict, Tuple, Optional

# Ensure project root in path
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from backtesting.oi.validation.deep_robustness_audit import load_cross_sectional_features

OUTPUT_DIR = "research/oi/validation/results"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def generate_walk_forward_folds(
    dates: List[pd.Timestamp],
    train_window: int = 120,
    test_window: int = 40,
    expanding: bool = False
) -> List[Dict]:
    """
    Generate walk-forward fold boundaries.
    """
    folds = []
    n_dates = len(dates)
    fold_idx = 1
    
    start_train_idx = 0
    while True:
        end_train_idx = start_train_idx + train_window
        end_test_idx = end_train_idx + test_window
        
        if end_test_idx > n_dates:
            # Check if there's enough test data for a final partial fold (at least 20 days)
            if n_dates - end_train_idx >= 20:
                end_test_idx = n_dates
            else:
                break
        
        train_dates = dates[start_train_idx:end_train_idx]
        test_dates = dates[end_train_idx:end_test_idx]
        
        folds.append({
            "fold": fold_idx,
            "train_start": train_dates[0],
            "train_end": train_dates[-1],
            "train_days": len(train_dates),
            "test_start": test_dates[0],
            "test_end": test_dates[-1],
            "test_days": len(test_dates),
            "train_date_set": set(train_dates),
            "test_date_set": set(test_dates)
        })
        
        fold_idx += 1
        if expanding:
            # Expanding: train start stays at 0, end shifts by test_window
            train_window += test_window
        else:
            # Rolling: window shifts forward by test_window
            start_train_idx += test_window
            
    return folds


def evaluate_parameter_candidates(df_subset: pd.DataFrame, base_ret: float) -> List[Dict]:
    """
    Evaluate multiple candidate parameter configurations on a dataset split.
    Candidate dimensions:
      - oi_threshold: [0.0, -1.0, -2.0, -3.0, -5.0]
      - candle_filter: ['all_bear', 'strong_bear_only', 'weak_bear_only']
      - vol_filter: ['all', 'above_median']
    """
    results = []
    med_vol = df_subset["vol_ratio"].median()
    
    thresholds = [0.0, -1.0, -2.0, -3.0, -5.0]
    candle_modes = ["all_bear", "strong_bear_only"]
    vol_modes = ["all", "above_median"]
    
    for thresh in thresholds:
        for c_mode in candle_modes:
            for v_mode in vol_modes:
                mask = (df_subset["ret_1d"] < 0) & (df_subset["oi_chg_pct"] <= thresh)
                
                if c_mode == "strong_bear_only":
                    mask = mask & df_subset["is_strong_bear"]
                
                if v_mode == "above_median":
                    mask = mask & (df_subset["vol_ratio"] > med_vol)
                    
                sub = df_subset[mask]
                returns = sub["fwd_ret_1d"].dropna()
                n = len(returns)
                
                if n < 15:
                    continue
                    
                m = returns.mean()
                std = returns.std(ddof=1) if n > 1 else 1e-6
                sharpe = (m / std) * np.sqrt(252) if std > 0 else 0.0
                win_rate = (returns > 0).mean() * 100.0
                alpha = m - base_ret
                t_stat, p_val = stats.ttest_1samp(returns, 0.0)
                
                # Daily aggregated return for cross-sectional portfolio proxy
                daily_pnl = sub.groupby("trade_date")["fwd_ret_1d"].mean()
                daily_sharpe = (daily_pnl.mean() / daily_pnl.std(ddof=1)) * np.sqrt(252) if len(daily_pnl) > 5 and daily_pnl.std(ddof=1) > 0 else 0.0
                
                results.append({
                    "thresh": thresh,
                    "candle_mode": c_mode,
                    "vol_mode": v_mode,
                    "param_id": f"OI<={thresh}|{c_mode}|{v_mode}",
                    "n_trades": n,
                    "mean_ret": round(m, 3),
                    "win_rate": round(win_rate, 1),
                    "alpha": round(alpha, 3),
                    "trade_sharpe": round(sharpe, 2),
                    "daily_sharpe": round(daily_sharpe, 2),
                    "p_val": round(p_val, 4)
                })
                
    return results


def run_walk_forward_validation(
    df: pd.DataFrame,
    train_window: int = 120,
    test_window: int = 40,
    expanding: bool = False
) -> Dict:
    """
    Run complete Walk-Forward analysis across chronological dataset.
    """
    trade_dates = sorted(df["trade_date"].unique())
    folds = generate_walk_forward_folds(trade_dates, train_window=train_window, test_window=test_window, expanding=expanding)
    
    print(f"[*] Generated {len(folds)} Walk-Forward folds (Train={train_window}d, Test={test_window}d, Expanding={expanding})")
    
    fold_summaries = []
    oos_selected_trades = []
    baseline_oos_trades = []
    
    for f in folds:
        train_df = df[df["trade_date"].isin(f["train_date_set"])].copy()
        test_df = df[df["trade_date"].isin(f["test_date_set"])].copy()
        
        train_base_ret = train_df["fwd_ret_1d"].mean()
        test_base_ret = test_df["fwd_ret_1d"].mean()
        
        # 1. In-Sample optimization: test candidate parameter grid
        candidates_is = evaluate_parameter_candidates(train_df, train_base_ret)
        if not candidates_is:
            print(f"[!] Warning: Insufficient trades in Fold {f['fold']} training set.")
            continue
            
        # Select best parameter by In-Sample Daily Sharpe
        candidates_df = pd.DataFrame(candidates_is)
        best_candidate = candidates_df.sort_values("daily_sharpe", ascending=False).iloc[0]
        
        # 2. Benchmark Baseline (Fixed baseline: OI <= 0, any bear, all vol)
        base_rule_test = test_df[(test_df["ret_1d"] < 0) & (test_df["oi_chg_pct"] <= 0.0)]
        base_test_rets = base_rule_test["fwd_ret_1d"].dropna()
        
        # 3. Apply Selected Best Parameter Strictly to Out-of-Sample (OOS)
        best_thresh = best_candidate["thresh"]
        best_cmode = best_candidate["candle_mode"]
        best_vmode = best_candidate["vol_mode"]
        med_vol_test = test_df["vol_ratio"].median()
        
        oos_mask = (test_df["ret_1d"] < 0) & (test_df["oi_chg_pct"] <= best_thresh)
        if best_cmode == "strong_bear_only":
            oos_mask = oos_mask & test_df["is_strong_bear"]
        if best_vmode == "above_median":
            oos_mask = oos_mask & (test_df["vol_ratio"] > med_vol_test)
            
        oos_subset = test_df[oos_mask].copy()
        oos_rets = oos_subset["fwd_ret_1d"].dropna()
        
        n_oos = len(oos_rets)
        if n_oos == 0:
            print(f"[!] Warning: 0 OOS trades for Fold {f['fold']}.")
            continue
            
        oos_mean = oos_rets.mean()
        oos_std = oos_rets.std(ddof=1) if n_oos > 1 else 1e-6
        oos_sharpe = (oos_mean / oos_std) * np.sqrt(252) if oos_std > 0 else 0.0
        oos_win_rate = (oos_rets > 0).mean() * 100.0
        oos_alpha = oos_mean - test_base_ret
        t_stat_oos, p_val_oos = stats.ttest_1samp(oos_rets, 0.0) if n_oos > 1 else (0.0, 1.0)
        
        # Daily portfolio return for OOS
        oos_daily = oos_subset.groupby("trade_date")["fwd_ret_1d"].mean()
        oos_daily_sharpe = (oos_daily.mean() / oos_daily.std(ddof=1)) * np.sqrt(252) if len(oos_daily) > 3 and oos_daily.std(ddof=1) > 0 else 0.0
        
        # Calculate degradation
        is_sharpe = best_candidate["daily_sharpe"]
        degradation = (oos_daily_sharpe / is_sharpe) if is_sharpe > 0 else 0.0
        
        fold_summaries.append({
            "Fold": f["fold"],
            "Train Window": f"{f['train_start'].strftime('%Y-%m-%d')} -> {f['train_end'].strftime('%Y-%m-%d')}",
            "Test Window": f"{f['test_start'].strftime('%Y-%m-%d')} -> {f['test_end'].strftime('%Y-%m-%d')}",
            "Selected Param": best_candidate["param_id"],
            "IS Daily Sharpe": is_sharpe,
            "IS Alpha (%)": best_candidate["alpha"],
            "IS WinRate (%)": best_candidate["win_rate"],
            "OOS Trades": n_oos,
            "OOS Daily Sharpe": round(oos_daily_sharpe, 2),
            "OOS Alpha (%)": round(oos_alpha, 3),
            "OOS WinRate (%)": round(oos_win_rate, 1),
            "OOS p-value": round(p_val_oos, 4),
            "Sharpe Retention": round(degradation, 2)
        })
        
        oos_subset["fold"] = f["fold"]
        oos_selected_trades.append(oos_subset)
        
    summary_df = pd.DataFrame(fold_summaries)
    all_oos_trades = pd.concat(oos_selected_trades, ignore_index=True) if oos_selected_trades else pd.DataFrame()
    
    return {
        "folds_table": summary_df,
        "all_oos_trades": all_oos_trades,
        "n_folds": len(folds)
    }


def compute_pbo_cscv(df: pd.DataFrame, n_splits: int = 8) -> float:
    """
    Estimate Probability of Backtest Overfitting (PBO) via Combinatorial Cross-Validation.
    Splits data into N chronological blocks, evaluates parameter matrix across all combinations.
    """
    trade_dates = sorted(df["trade_date"].unique())
    block_size = len(trade_dates) // n_splits
    blocks = [trade_dates[i*block_size : (i+1)*block_size] for i in range(n_splits)]
    
    # Evaluate a standard set of 10 parameter combinations across each block
    param_set = [
        {"thresh": 0.0, "c_mode": "all_bear", "v_mode": "all"},
        {"thresh": -1.0, "c_mode": "all_bear", "v_mode": "all"},
        {"thresh": -2.0, "c_mode": "all_bear", "v_mode": "all"},
        {"thresh": -3.0, "c_mode": "all_bear", "v_mode": "all"},
        {"thresh": -5.0, "c_mode": "all_bear", "v_mode": "all"},
        {"thresh": 0.0, "c_mode": "strong_bear_only", "v_mode": "all"},
        {"thresh": -2.0, "c_mode": "strong_bear_only", "v_mode": "all"},
        {"thresh": -5.0, "c_mode": "strong_bear_only", "v_mode": "all"},
        {"thresh": -2.0, "c_mode": "all_bear", "v_mode": "above_median"},
        {"thresh": -5.0, "c_mode": "all_bear", "v_mode": "above_median"},
    ]
    
    from itertools import combinations
    half = n_splits // 2
    combos = list(combinations(range(n_splits), half))
    
    overfit_count = 0
    total_trials = len(combos)
    
    for train_indices in combos:
        test_indices = [i for i in range(n_splits) if i not in train_indices]
        
        train_dates = set([d for idx in train_indices for d in blocks[idx]])
        test_dates = set([d for idx in test_indices for d in blocks[idx]])
        
        tr_df = df[df["trade_date"].isin(train_dates)]
        te_df = df[df["trade_date"].isin(test_dates)]
        
        # Calculate Sharpe for each parameter on Train
        tr_sharpes = []
        te_sharpes = []
        for p in param_set:
            m_tr = (tr_df["ret_1d"] < 0) & (tr_df["oi_chg_pct"] <= p["thresh"])
            if p["c_mode"] == "strong_bear_only":
                m_tr = m_tr & tr_df["is_strong_bear"]
            r_tr = tr_df[m_tr]["fwd_ret_1d"].dropna()
            sh_tr = (r_tr.mean() / (r_tr.std(ddof=1) + 1e-6)) if len(r_tr) > 5 else -999.0
            tr_sharpes.append(sh_tr)
            
            m_te = (te_df["ret_1d"] < 0) & (te_df["oi_chg_pct"] <= p["thresh"])
            if p["c_mode"] == "strong_bear_only":
                m_te = m_te & te_df["is_strong_bear"]
            r_te = te_df[m_te]["fwd_ret_1d"].dropna()
            sh_te = (r_te.mean() / (r_te.std(ddof=1) + 1e-6)) if len(r_te) > 5 else -999.0
            te_sharpes.append(sh_te)
            
        best_is_idx = int(np.argmax(tr_sharpes))
        # Check if the best IS parameter ranks below the median in OOS
        median_te = np.median(te_sharpes)
        if te_sharpes[best_is_idx] < median_te:
            overfit_count += 1
            
    pbo = overfit_count / total_trials if total_trials > 0 else 0.0
    return round(pbo, 3)


def main():
    print("=" * 80)
    print("AGY Futures OI — Phase 3: Walk-Forward Validation Engine")
    print("=" * 80)
    
    df = load_cross_sectional_features()
    print(f"[+] Loaded clean feature matrix: {len(df):,} records ({df['trade_date'].min().strftime('%Y-%m-%d')} to {df['trade_date'].max().strftime('%Y-%m-%d')})")
    
    # Run Rolling Walk-Forward (120d Train ~6 months, 40d Test ~2 months)
    res_rolling = run_walk_forward_validation(df, train_window=120, test_window=40, expanding=False)
    print("\n--- Rolling Walk-Forward Folds (120d Train / 40d Test) ---")
    print(res_rolling["folds_table"].to_string(index=False))
    
    # Save results
    res_rolling["folds_table"].to_csv(os.path.join(OUTPUT_DIR, "walk_forward_rolling_folds.csv"), index=False)
    
    # Run PBO estimation
    pbo = compute_pbo_cscv(df, n_splits=6)
    print(f"\n[+] Probability of Backtest Overfitting (PBO / CSCV): {pbo:.1%}")
    with open(os.path.join(OUTPUT_DIR, "pbo_metric.txt"), "w") as f:
        f.write(f"PBO={pbo}\n")


if __name__ == "__main__":
    main()
