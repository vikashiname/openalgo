"""
Hypothesis Generator for AutoResearch
File: backtesting/emacrossopen/autoresearch/hypothesis_generator.py

Sequences and generates mutation batches across Timeframe, Direction, Exit, and Parameters.
Includes advanced Asymmetric Universe and Parameter Sensitivity suites.
"""

from typing import Any, Dict, List


def generate_experiment_suite() -> List[Dict[str, Any]]:
    """Generates a structured list of hypotheses for the AutoResearch loop."""
    experiments = []

    # --------------------------------------------------------------------------
    # BATCH 1: TIMEFRAME SHOOTOUT (Baseline Reversal Only)
    # --------------------------------------------------------------------------
    for tf in ["1h", "75m", "125m", "4h", "1d"]:
        experiments.append({
            "hypothesis_name": f"TF_Shootout_{tf}_Symmetrical",
            "timeframe": tf,
            "direction_mode": "SYMMETRICAL",
            "exit_type": "REVERSAL",
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Benchmark baseline reversal on {tf}",
        })

    # --------------------------------------------------------------------------
    # BATCH 2: DIRECTIONAL ASYMMETRY (Long-Only vs Asymmetric vs Symmetrical)
    # --------------------------------------------------------------------------
    for tf in ["1h", "75m", "125m", "1d"]:
        experiments.append({
            "hypothesis_name": f"Directional_{tf}_LongOnly",
            "timeframe": tf,
            "direction_mode": "LONG_ONLY",
            "exit_type": "REVERSAL",
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Long-Only trend following on {tf}",
        })
        experiments.append({
            "hypothesis_name": f"Directional_{tf}_AsymmetricUniverse",
            "timeframe": tf,
            "direction_mode": "ASYMMETRIC",
            "exit_type": "REVERSAL",
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Asymmetric filtered universe on {tf}",
        })

    # --------------------------------------------------------------------------
    # BATCH 3: DUAL-TIMEFRAME (MTF) TREND FILTERING
    # --------------------------------------------------------------------------
    experiments.append({
        "hypothesis_name": "MTF_DailyFilter_1HTrigger_Symmetrical",
        "timeframe": "1h",
        "htf_filter": "1d",
        "direction_mode": "SYMMETRICAL",
        "exit_type": "REVERSAL",
        "fast_ema": 9, "slow_ema": 26,
        "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
        "notes": "Daily EMA26 trend filter with 1H entry triggers",
    })
    experiments.append({
        "hypothesis_name": "MTF_DailyFilter_75mTrigger_Symmetrical",
        "timeframe": "75m",
        "htf_filter": "1d",
        "direction_mode": "SYMMETRICAL",
        "exit_type": "REVERSAL",
        "fast_ema": 9, "slow_ema": 26,
        "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
        "notes": "Daily EMA26 trend filter with 75m entry triggers",
    })

    # --------------------------------------------------------------------------
    # BATCH 4: EXIT ARCHITECTURES (Fixed Target + Catastrophe SL on Symmetrical)
    # --------------------------------------------------------------------------
    for tf in ["1h", "75m", "125m"]:
        experiments.append({
            "hypothesis_name": f"Exit_TargetSL_{tf}_Symmetrical",
            "timeframe": tf,
            "direction_mode": "SYMMETRICAL",
            "exit_type": "TARGET_SL",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Asymmetric Target (+3%/-1.5%) + -6% SL on {tf} (Sym)",
        })

    # --------------------------------------------------------------------------
    # BATCH 5: ELITE COMBINATION (Asymmetric Universe + Target & Catastrophe SL)
    # --------------------------------------------------------------------------
    for tf in ["1h", "75m", "125m"]:
        experiments.append({
            "hypothesis_name": f"Champion_AsymUniverse_TargetSL_{tf}",
            "timeframe": tf,
            "direction_mode": "ASYMMETRIC",
            "exit_type": "TARGET_SL",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Asymmetric Universe + Target (+3%/-1.5%) + -6% SL on {tf}",
        })

    # Target variations on 1h and 75m
    for l_tp, s_tp in [(2.5, 1.25), (3.5, 1.75), (4.0, 2.0)]:
        experiments.append({
            "hypothesis_name": f"Target_Sweep_1h_TP{l_tp}_{s_tp}",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "TARGET_SL",
            "long_tp_pct": l_tp, "short_tp_pct": s_tp, "sl_pct": 6.0,
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Target Sweep: +{l_tp}% / +{s_tp}% on 1h Asym",
        })

    # Parameter sensitivity (Fast / Slow EMA) on Champion Asymmetric 1h
    for f_ema, s_ema in [(7, 21), (8, 24), (9, 26), (10, 28), (12, 30)]:
        experiments.append({
            "hypothesis_name": f"EMA_Sensitivity_1h_{f_ema}_{s_ema}",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "TARGET_SL",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "fast_ema": f_ema, "slow_ema": s_ema,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"EMA Sensitivity: {f_ema}/{s_ema} on 1h Asym",
        })

    return experiments
