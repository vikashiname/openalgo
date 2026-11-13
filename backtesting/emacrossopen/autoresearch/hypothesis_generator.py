"""
Hypothesis Generator for AutoResearch
File: backtesting/emacrossopen/autoresearch/hypothesis_generator.py

Sequences and generates quantitative hypothesis batches across:
  1. Benchmark Controls (Reversal & Fixed Target Baseline)
  2. Target-to-Runner High-Water-Mark (HWM) Pullback Trailing Sweeps
  3. Early Profit Milestone + Break-Even Stop Loss Activation
  4. Catastrophe Stop-Loss Calibration
  5. Asymmetric Target Milestone Grid
  6. Fast / Slow EMA Parameter Sensitivity on Upgraded Architecture
  7. MACD Timing & Signal Line Sensitivity
  8. Guaranteed Runner Profit Floor Clamping
"""

from typing import Any, Dict, List


def generate_experiment_suite() -> List[Dict[str, Any]]:
    """Generates a structured list of hypotheses for the AutoResearch loop."""
    experiments = []

    # --------------------------------------------------------------------------
    # BENCHMARK CONTROLS
    # --------------------------------------------------------------------------
    experiments.append({
        "hypothesis_name": "Control_1h_Asym_Reversal_Only",
        "timeframe": "1h",
        "direction_mode": "ASYMMETRIC",
        "exit_type": "REVERSAL",
        "fast_ema": 9, "slow_ema": 26,
        "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
        "notes": "Control: Pure V2-2 reversal exits on 1H Asymmetric universe",
    })

    experiments.append({
        "hypothesis_name": "Control_1h_Asym_FixedTarget_V3_Baseline",
        "timeframe": "1h",
        "direction_mode": "ASYMMETRIC",
        "exit_type": "TARGET_SL",
        "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
        "enable_runner": False,
        "fast_ema": 9, "slow_ema": 26,
        "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
        "notes": "Control: Production V3.0 Fixed Target (+3.0%/-1.5%) + -6% SL",
    })

    # --------------------------------------------------------------------------
    # BATCH 1: TARGET-TO-RUNNER HWM TRAIL SWEEP (+3.0% / +1.5% target converts to runner)
    # --------------------------------------------------------------------------
    for trail in [0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.75, 1.00]:
        experiments.append({
            "hypothesis_name": f"Runner_HWM_Trail_{trail:.2f}pct",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "TARGET_RUNNER",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "enable_runner": True,
            "runner_trail_pct": trail,
            "runner_profit_floor_pct": 0.50,
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Target-to-Runner: {trail:.2f}% HWM pullback trail once TP hit",
        })

    # --------------------------------------------------------------------------
    # BATCH 2: EARLY PROFIT MILESTONE + BREAK-EVEN STOP-LOSS (with 0.35% HWM Runner)
    # --------------------------------------------------------------------------
    early_pairs = [
        (1.0, 0.8),
        (1.2, 1.0),
        (1.5, 1.2),
        (1.8, 1.2),
        (2.0, 1.5),
    ]
    for e_long, e_short in early_pairs:
        experiments.append({
            "hypothesis_name": f"EarlyTP_{e_long}L_{e_short}S_BE_Runner035",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "EARLY_TP_RUNNER",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "enable_runner": True,
            "runner_trail_pct": 0.35,
            "runner_profit_floor_pct": 0.50,
            "early_long_tp_pct": e_long,
            "early_short_tp_pct": e_short,
            "move_sl_to_be": True,
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Early TP (+{e_long}%/-{e_short}%) moves SL to BE; 0.35% HWM runner",
        })

    # --------------------------------------------------------------------------
    # BATCH 2B: EARLY PROFIT MILESTONE + BREAK-EVEN STOP-LOSS WITH FIXED TARGET EXIT
    # (Capital protection at early milestone + 100% full profit banked at target, no trail giveback)
    # --------------------------------------------------------------------------
    for e_long, e_short in early_pairs:
        experiments.append({
            "hypothesis_name": f"EarlyTP_{e_long}L_{e_short}S_BE_FixedTarget",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "TARGET_SL",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "enable_runner": False,
            "early_long_tp_pct": e_long,
            "early_short_tp_pct": e_short,
            "move_sl_to_be": True,
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Early TP (+{e_long}%/-{e_short}%) moves SL to BE + Fixed Target (+3.0%/-1.5%)",
        })

    # --------------------------------------------------------------------------
    # BATCH 2C: FIXED TARGET + BE STOP-LOSS ACROSS EMA MATRIX
    # --------------------------------------------------------------------------
    for f_ema, s_ema in [(8, 24), (9, 26), (10, 26), (10, 28), (11, 28), (11, 29), (12, 30)]:
        experiments.append({
            "hypothesis_name": f"FixedTarget_BE_EMA_{f_ema}_{s_ema}",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "TARGET_SL",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "enable_runner": False,
            "early_long_tp_pct": 1.5,
            "early_short_tp_pct": 1.2,
            "move_sl_to_be": True,
            "fast_ema": f_ema, "slow_ema": s_ema,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"EMA {f_ema}/{s_ema} + Early TP BE + Fixed Target (+3.0%/-1.5%)",
        })

    # --------------------------------------------------------------------------
    # BATCH 2E: FINE-GRAINED PLATEAU CONFIRMATION FOR CHAMPION EMA (11, 29) & (10, 28)
    # --------------------------------------------------------------------------
    for f_ema, s_ema in [(10, 27), (10, 28), (11, 27), (11, 28), (11, 29), (11, 30), (12, 29)]:
        experiments.append({
            "hypothesis_name": f"PlateauConfirm_EMA_{f_ema}_{s_ema}",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "TARGET_SL",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "enable_runner": False,
            "fast_ema": f_ema, "slow_ema": s_ema,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Plateau confirmation around champion: EMA {f_ema}/{s_ema}",
        })

    # Target ratio optimization on Champion EMA (11, 29)
    for l_tp, s_tp in [(2.5, 1.25), (3.0, 1.20), (3.0, 1.50), (3.5, 1.50), (3.5, 1.75), (4.0, 1.50), (4.0, 2.00)]:
        experiments.append({
            "hypothesis_name": f"Champion_Target_Sweep_EMA11_29_TP{l_tp}_{s_tp}",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "TARGET_SL",
            "long_tp_pct": l_tp, "short_tp_pct": s_tp, "sl_pct": 6.0,
            "enable_runner": False,
            "fast_ema": 11, "slow_ema": 29,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Target sensitivity on Champion EMA 11/29: +{l_tp}% / +{s_tp}%",
        })

    # MACD timing on Champion EMA (11, 29)
    for mf, ms, msig in [(10, 22, 7), (11, 24, 8), (12, 26, 9), (13, 27, 9), (14, 28, 9)]:
        experiments.append({
            "hypothesis_name": f"Champion_MACD_Sweep_EMA11_29_{mf}_{ms}_{msig}",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "TARGET_SL",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "enable_runner": False,
            "fast_ema": 11, "slow_ema": 29,
            "macd_fast": mf, "macd_slow": ms, "macd_sig": msig,
            "notes": f"MACD timing on Champion EMA 11/29: {mf}/{ms}/{msig}",
        })

    # --------------------------------------------------------------------------
    # BATCH 3: CATASTROPHE STOP-LOSS CALIBRATION (Early TP 1.5/1.2 + 0.35% Runner)
    # --------------------------------------------------------------------------
    for sl in [2.0, 3.0, 4.0, 5.0, 6.0, 8.0]:
        experiments.append({
            "hypothesis_name": f"Catastrophe_SL_{sl:.1f}pct",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "EARLY_TP_RUNNER",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": sl,
            "enable_runner": True,
            "runner_trail_pct": 0.35,
            "runner_profit_floor_pct": 0.50,
            "early_long_tp_pct": 1.5,
            "early_short_tp_pct": 1.2,
            "move_sl_to_be": True,
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Catastrophe SL {sl:.1f}% on Early TP + Runner architecture",
        })

    # --------------------------------------------------------------------------
    # BATCH 4: ASYMMETRIC MAIN TARGET MILESTONES (Where Runner Engages)
    # --------------------------------------------------------------------------
    target_combos = [
        (2.5, 1.25),
        (3.0, 1.20),
        (3.0, 1.50),
        (3.5, 1.50),
        (3.5, 1.75),
        (4.0, 1.50),
        (4.0, 2.00),
    ]
    for l_tp, s_tp in target_combos:
        experiments.append({
            "hypothesis_name": f"MainTarget_{l_tp}L_{s_tp}S_Runner035",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "EARLY_TP_RUNNER",
            "long_tp_pct": l_tp, "short_tp_pct": s_tp, "sl_pct": 6.0,
            "enable_runner": True,
            "runner_trail_pct": 0.35,
            "runner_profit_floor_pct": 0.50,
            "early_long_tp_pct": 1.5,
            "early_short_tp_pct": 1.2,
            "move_sl_to_be": True,
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Main TP Milestone +{l_tp}%/-{s_tp}% before runner activation",
        })

    # --------------------------------------------------------------------------
    # BATCH 5: EMA PARAMETER SENSITIVITY ON UPGRADED RUNNER & BE ARCHITECTURE
    # --------------------------------------------------------------------------
    ema_pairs = [
        (7, 21),
        (8, 24),
        (9, 21),
        (9, 26),
        (10, 26),
        (10, 28),
        (11, 28),
        (11, 29),
        (12, 30),
    ]
    for f_ema, s_ema in ema_pairs:
        experiments.append({
            "hypothesis_name": f"EMA_Sens_{f_ema}_{s_ema}_RunnerBE",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "EARLY_TP_RUNNER",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "enable_runner": True,
            "runner_trail_pct": 0.35,
            "runner_profit_floor_pct": 0.50,
            "early_long_tp_pct": 1.5,
            "early_short_tp_pct": 1.2,
            "move_sl_to_be": True,
            "fast_ema": f_ema, "slow_ema": s_ema,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"EMA {f_ema}/{s_ema} timing on Early TP + Runner architecture",
        })

    # --------------------------------------------------------------------------
    # BATCH 6: MACD PARAMETER SENSITIVITY
    # --------------------------------------------------------------------------
    macd_triplets = [
        (8, 21, 6),
        (10, 22, 7),
        (12, 26, 9),
        (14, 28, 9),
        (15, 30, 9),
    ]
    for mf, ms, msig in macd_triplets:
        experiments.append({
            "hypothesis_name": f"MACD_Sens_{mf}_{ms}_{msig}_RunnerBE",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "EARLY_TP_RUNNER",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "enable_runner": True,
            "runner_trail_pct": 0.35,
            "runner_profit_floor_pct": 0.50,
            "early_long_tp_pct": 1.5,
            "early_short_tp_pct": 1.2,
            "move_sl_to_be": True,
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": mf, "macd_slow": ms, "macd_sig": msig,
            "notes": f"MACD {mf}/{ms}/{msig} confluence timing on Runner architecture",
        })

    # --------------------------------------------------------------------------
    # BATCH 7: GUARANTEED RUNNER PROFIT FLOOR SWEEP
    # --------------------------------------------------------------------------
    for floor in [0.0, 0.25, 0.50, 0.75, 1.00]:
        experiments.append({
            "hypothesis_name": f"Floor_{floor:.2f}pct_RunnerBE",
            "timeframe": "1h",
            "direction_mode": "ASYMMETRIC",
            "exit_type": "EARLY_TP_RUNNER",
            "long_tp_pct": 3.0, "short_tp_pct": 1.5, "sl_pct": 6.0,
            "enable_runner": True,
            "runner_trail_pct": 0.35,
            "runner_profit_floor_pct": floor,
            "early_long_tp_pct": 1.5,
            "early_short_tp_pct": 1.2,
            "move_sl_to_be": True,
            "fast_ema": 9, "slow_ema": 26,
            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9,
            "notes": f"Guaranteed profit floor clamped at +{floor:.2f}% once runner active",
        })

    return experiments
