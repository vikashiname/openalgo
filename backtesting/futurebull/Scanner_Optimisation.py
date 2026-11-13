#!/usr/bin/env python3
"""
================================================================================
PHASE 4: FILTER OPTIMISATION & STRATEGY VARIANT SYNTHESIS
================================================================================
Directory   : backtesting/futurebull/
Role        : Conducts controlled parameter threshold experiments (RSI, Volume,
              Bollinger Bands, EMA regimes) and constructs the 4 optimized variants:
                1. Original Scanner (29 conditions)
                2. Optimized Scanner (Eliminates exhaustion trap + tautologies)
                3. Simplified Scanner (5-factor clean model)
                4. High-Frequency Scanner (Fast swing momentum)
                5. High-Quality Breakout Scanner (Volume surge + multi-week high)
Outputs:
  - reports/PHASE4_PARAM_SENSITIVITY_EXPERIMENTS.csv
  - reports/PHASE4_SCANNER_VARIANTS_COMPARISON.csv
================================================================================
"""

import sys
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from scanner_engine import compute_all_filters, compute_rsi, compute_bollinger_bands, compute_macd_14_5_3

DATA_DIR = CURRENT_DIR / "data"
REPORTS_DIR = CURRENT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def evaluate_signal_subset(df_all: pd.DataFrame, mask: pd.Series, name: str) -> Dict[str, Any]:
    sub = df_all[mask == True]
    n = len(sub)
    if n == 0:
        return {"variant": name, "signals": 0, "win_rate_5d": 0.0, "win_rate_10d": 0.0, "avg_ret_5d": 0.0, "avg_ret_10d": 0.0, "edge_ratio": 0.0}

    ret_5d = sub["fwd_ret_5d"].mean()
    ret_10d = sub["fwd_ret_10d"].mean()
    win_5d = (sub["fwd_ret_5d"] > 0).mean() * 100.0
    win_10d = (sub["fwd_ret_10d"] > 0).mean() * 100.0
    mfe = sub["mfe_10d_pct"].mean()
    mae = sub["mae_10d_pct"].mean()
    edge = abs(mfe / mae) if abs(mae) > 0 else 1.0

    return {
        "variant": name,
        "signals": n,
        "frequency_pct": round((n / len(df_all)) * 100.0, 2),
        "win_rate_5d": round(win_5d, 2),
        "win_rate_10d": round(win_10d, 2),
        "avg_ret_5d": round(ret_5d, 3),
        "avg_ret_10d": round(ret_10d, 3),
        "avg_mfe_10d": round(mfe, 2),
        "avg_mae_10d": round(mae, 2),
        "edge_ratio": round(edge, 2)
    }


def run_phase4_optimisation():
    print("================================================================================")
    print("🔬 RUNNING PHASE 4: FILTER OPTIMISATION & CONTROLLED EXPERIMENTS")
    print("================================================================================")

    data_files = sorted(list(DATA_DIR.glob("*.parquet")))
    all_dfs = []
    for f in data_files:
        df = pd.read_parquet(f)
        all_dfs.append(compute_all_filters(df))
    combined = pd.concat(all_dfs, ignore_index=True)

    c = combined["close"]
    h = combined["high"]
    l = combined["low"]
    o = combined["open"]
    v = combined["volume"]

    # --------------------------------------------------------------------------
    # EXPERIMENT 1: RSI Threshold Sensitivity (45, 50, 55, 60)
    # --------------------------------------------------------------------------
    rsi_14 = compute_rsi(c, 14)
    exp_rsi_results = []
    for thresh in [45.0, 50.0, 55.0, 60.0]:
        mask = (rsi_14 > thresh) & combined["COMBO_A"]
        exp_rsi_results.append(evaluate_signal_subset(combined, mask, f"RSI14_GT_{int(thresh)}"))

    # --------------------------------------------------------------------------
    # EXPERIMENT 2: Volume Threshold Sensitivity (50k, 100k, 150k, 200k)
    # --------------------------------------------------------------------------
    exp_vol_results = []
    for vol in [50000, 100000, 150000, 200000]:
        mask = (v > vol) & (c > c.ewm(span=20, adjust=False).mean())
        exp_vol_results.append(evaluate_signal_subset(combined, mask, f"Volume_GT_{vol//1000}K"))

    # --------------------------------------------------------------------------
    # EXPERIMENT 3: Bollinger Band Excursion Fix
    # Comparing: Close >= Upper BB vs Close < Upper BB (Inside BB Trend Breakout)
    # --------------------------------------------------------------------------
    _, bb_upper, _ = compute_bollinger_bands(c, 20, 2.0)
    exp_bb_results = [
        evaluate_signal_subset(combined, (c >= bb_upper), "BB_Overextended_Close_GTE_Upper"),
        evaluate_signal_subset(combined, (c < bb_upper) & (c > c.ewm(span=20, adjust=False).mean()), "BB_Sustainable_Close_Below_Upper_Above_Mid"),
    ]

    all_sensitivity = exp_rsi_results + exp_vol_results + exp_bb_results
    sens_df = pd.DataFrame(all_sensitivity)
    sens_out = REPORTS_DIR / "PHASE4_PARAM_SENSITIVITY_EXPERIMENTS.csv"
    sens_df.to_csv(sens_out, index=False)
    print(f"✓ Exported parameter sensitivity experiments to: {sens_out}")

    # --------------------------------------------------------------------------
    # CONSTRUCT CANDIDATE SCANNER ARCHITECTURES
    # --------------------------------------------------------------------------
    sma_vol_20 = v.rolling(20).mean()
    ema_5 = c.ewm(span=5, adjust=False).mean()
    ema_20 = c.ewm(span=20, adjust=False).mean()
    ema_50 = c.ewm(span=50, adjust=False).mean()
    _, _, macd_hist = compute_macd_14_5_3(c)
    high_20 = h.rolling(20).max().shift(1)  # 20-day high breakout

    # 1. Original Baseline (29 conditions)
    mask_original = combined["COMBO_ALL_ORIGINAL"]

    # 2. Optimized Scanner:
    # Drops redundant MACD, drops redundant Stoch, replaces Upper BB exhaustion with sustainable momentum
    mask_optimized = (
        (sma_vol_20 >= 100000) &
        (v > 100000) &
        (c > o) &                         # Green candle
        (c > ema_20) & (ema_20 > ema_50) &# Trend alignment
        (rsi_14 > 52.0) & (rsi_14 < 75.0)&# Prime momentum zone (not overbought)
        (macd_hist >= 0.0) &              # MACD confirmation (clean single check)
        (c < bb_upper)                    # Sustainable (not overextended into upper BB)
    )

    # 3. Simplified Scanner:
    # Clean 5-factor model: Liquidity + EMA(20>50) + RSI(14)>50 + MACD Hist >= 0 + Green Candle
    mask_simplified = (
        (sma_vol_20 >= 100000) &
        (c > ema_20) &
        (ema_20 > ema_50) &
        (rsi_14 > 50.0) &
        (macd_hist >= 0.0) &
        (c > o)
    )

    # 4. High-Frequency Scanner:
    # Fast swing trigger: EMA(5) > EMA(20) + RSI(10) > 50 + Volume > 100K + Green Candle
    mask_high_freq = (
        (sma_vol_20 >= 100000) &
        (ema_5 > ema_20) &
        (compute_rsi(c, 10) > 50.0) &
        (c > o)
    )

    # 5. High-Quality Breakout Scanner:
    # Multi-week breakout + Volume Expansion (Volume >= 1.5x SMA20) + EMA(20>50)
    mask_hq_breakout = (
        (sma_vol_20 >= 100000) &
        (v >= 1.5 * sma_vol_20) &         # Volume surge
        (c >= high_20) &                  # 20-day price breakout
        (c > ema_50) &
        (rsi_14 > 55.0) & (rsi_14 < 80.0)
    )

    variants = [
        evaluate_signal_subset(combined, mask_original, "1_Original_Scanner_29Cond"),
        evaluate_signal_subset(combined, mask_optimized, "2_Optimised_Scanner"),
        evaluate_signal_subset(combined, mask_simplified, "3_Simplified_Scanner_5Factor"),
        evaluate_signal_subset(combined, mask_high_freq, "4_High_Frequency_Scanner"),
        evaluate_signal_subset(combined, mask_hq_breakout, "5_High_Quality_Breakout_Scanner"),
    ]

    variants_df = pd.DataFrame(variants)
    variants_out = REPORTS_DIR / "PHASE4_SCANNER_VARIANTS_COMPARISON.csv"
    variants_df.to_csv(variants_out, index=False)
    print(f"✓ Exported scanner variants comparison to: {variants_out}")

    print("\n--------------------------------------------------------------------------------")
    print("🏆 PHASE 4: 5 SCANNER VARIANTS FORWARD PERFORMANCE:")
    print("--------------------------------------------------------------------------------")
    for _, r in variants_df.iterrows():
        print(f"  {r['variant']:<33} | Signals: {r['signals']:<6} ({r['frequency_pct']:>5.2f}%) | 10d Ret: {r['avg_ret_10d']:>+5.2f}% | Win: {r['win_rate_10d']:>5.1f}% | Edge: {r['edge_ratio']:>4.2f}")
    print("================================================================================")


if __name__ == "__main__":
    run_phase4_optimisation()
