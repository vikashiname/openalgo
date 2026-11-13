#!/usr/bin/env python3
"""
================================================================================
AGY EXPERIMENT EXECUTION SUITE — NIFTY COVERED CALL OPTIMIZATION
Location: ~/backtesting/covered call/research/run_experiments.py
================================================================================
Executes controlled sweeps:
  - Experiment 0: Frozen Mechanical Baseline
  - Experiment 1: Delta Selection (0.15, 0.20, 0.25, 0.30, 0.35, 0.40)
  - Experiment 2: Premium-Decay Exit Target (50%, 60%, 70%, 80%, 90%, 95%, 99%)
  - Experiment 3: Stop-Loss Multiples (1.5x, 2.0x, 2.5x, 3.0x, 4.0x, 5.0x, No SL)
  - Experiment 4: Roll Timing (3, 5, 7, 10, 14 DTE, and 4, 7, 10 Trading Sessions)
  - Experiment 5: Volatility Regime Gate (ATM IV >= 18%, 16%, 20%)
  - Experiment 6: Parameter Interactions (Top Candidate Combinations)

Saves CSV artifacts in research directory for auditability and reporting.
================================================================================
"""

import sys
import os
import time
from pathlib import Path
import pandas as pd
import numpy as np

# Research imports
RESEARCH_DIR = Path(__file__).resolve().parent
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

from optimization_engine import (
    ExtendedOptionsBacktester,
    evaluate_experiment,
    run_chronological_splits,
    run_walk_forward_rolling,
    run_stress_tests,
    load_options_dataset,
    compute_underlying_features,
    OPTIONS_DATA_PATH,
    INITIAL_CAPITAL
)

def build_experiment_manifest():
    """Defines the full catalog of isolated and interaction experiments."""
    base_params = {
        'strike_mode': 'delta',
        'strike_param': 0.30,
        'profit_target_pct': 0.90,
        'stop_loss_mult': 3.0,
        'roll_dte': 10,
        'roll_mode': 'calendar',
        'roll_trading_sessions': 7,
        'trend_filter': True,
        'target_dte': 28,
        'iv_filter_min': 0.0,
        'atm_iv_min': 0.0,
        'min_premium': 1.0,
        'net_aware_target': False
    }

    experiments = []

    # -------------------------------------------------------------------------
    # 0. FROZEN MECHANICAL BASELINE
    # -------------------------------------------------------------------------
    experiments.append({
        'id': 'EXP-000-BASE',
        'category': '0. Baseline Benchmark',
        'name': 'Frozen Mechanical Baseline (Delta 0.30, Target 90%, SL 3.0x, Roll 10 DTE)',
        'params': base_params.copy()
    })

    # -------------------------------------------------------------------------
    # 1. DELTA SWEEP (OTM CALL SELECTION)
    # -------------------------------------------------------------------------
    deltas = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
    for d in deltas:
        p = base_params.copy()
        p['strike_param'] = d
        tag = f"EXP-01{int(d*100):02d}-D{int(d*100):02d}"
        experiments.append({
            'id': tag,
            'category': '1. Delta Sweep',
            'name': f"OTM Selection: Target Delta {d:.2f}",
            'params': p
        })

    # -------------------------------------------------------------------------
    # 2. PROFIT TARGET SWEEP (PREMIUM DECAY EXIT)
    # -------------------------------------------------------------------------
    targets = [0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.99]
    for t in targets:
        p = base_params.copy()
        p['profit_target_pct'] = t
        tag = f"EXP-02{int(t*100):02d}-T{int(t*100):02d}"
        experiments.append({
            'id': tag,
            'category': '2. Exit Target Sweep',
            'name': f"Premium Decay Exit Target: {int(t*100)}%",
            'params': p
        })

    # -------------------------------------------------------------------------
    # 3. STOP LOSS MULTIPLES SWEEP
    # -------------------------------------------------------------------------
    sl_mults = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 999.0]
    for sl in sl_mults:
        p = base_params.copy()
        p['stop_loss_mult'] = sl
        sl_name = "No Stop Loss" if sl > 10.0 else f"Stop Loss {sl:.1f}x"
        tag = f"EXP-03{int(sl*10):02d}-SL{int(sl*10):02d}" if sl < 10.0 else "EXP-0399-SLNOSL"
        experiments.append({
            'id': tag,
            'category': '3. Stop Loss Sweep',
            'name': sl_name,
            'params': p
        })

    # -------------------------------------------------------------------------
    # 4. ROLL TIMING SWEEP (CALENDAR DTE & TRADING SESSIONS)
    # -------------------------------------------------------------------------
    cal_dtes = [3, 5, 7, 10, 14]
    for rd in cal_dtes:
        p = base_params.copy()
        p['roll_dte'] = rd
        p['roll_mode'] = 'calendar'
        tag = f"EXP-04{rd:02d}-R{rd:02d}CAL"
        experiments.append({
            'id': tag,
            'category': '4. Roll Timing (Calendar)',
            'name': f"Roll Threshold: {rd} Calendar DTE",
            'params': p
        })

    trading_sessions = [4, 7, 10]
    for ts in trading_sessions:
        p = base_params.copy()
        p['roll_mode'] = 'trading_sessions'
        p['roll_trading_sessions'] = ts
        tag = f"EXP-04{ts:02d}-R{ts:02d}TS"
        experiments.append({
            'id': tag,
            'category': '4. Roll Timing (Trading Sessions)',
            'name': f"Roll Threshold: {ts} Trading Sessions (Holiday-Aware)",
            'params': p
        })

    # -------------------------------------------------------------------------
    # 5. VOLATILITY REGIME GATES (ATM IV FILTER)
    # -------------------------------------------------------------------------
    iv_thresholds = [0.16, 0.18, 0.20]
    for iv in iv_thresholds:
        p = base_params.copy()
        p['atm_iv_min'] = iv
        tag = f"EXP-05{int(iv*100):02d}-IV{int(iv*100):02d}"
        experiments.append({
            'id': tag,
            'category': '5. Volatility Regime',
            'name': f"Volatility Gate: ATM IV >= {int(iv*100)}%",
            'params': p
        })

    # -------------------------------------------------------------------------
    # 6. MULTI-FACTOR PARAMETER INTERACTIONS (CANDIDATE SYNTHESES)
    # -------------------------------------------------------------------------
    interactions = [
        # Candidate 1: Delta 0.25 + Target 80% + SL 3.0x + Roll 10 DTE
        ('EXP-060-INT1', 'Delta 0.25 + Target 80% + SL 3.0x + Roll 10 DTE', {
            'strike_param': 0.25, 'profit_target_pct': 0.80, 'stop_loss_mult': 3.0, 'roll_dte': 10, 'roll_mode': 'calendar'
        }),
        # Candidate 2: Delta 0.25 + Target 80% + SL 2.5x + Roll 7 DTE
        ('EXP-061-INT2', 'Delta 0.25 + Target 80% + SL 2.5x + Roll 7 DTE', {
            'strike_param': 0.25, 'profit_target_pct': 0.80, 'stop_loss_mult': 2.5, 'roll_dte': 7, 'roll_mode': 'calendar'
        }),
        # Candidate 3: Delta 0.20 + Target 80% + SL 3.0x + Roll 7 DTE
        ('EXP-062-INT3', 'Delta 0.20 + Target 80% + SL 3.0x + Roll 7 DTE', {
            'strike_param': 0.20, 'profit_target_pct': 0.80, 'stop_loss_mult': 3.0, 'roll_dte': 7, 'roll_mode': 'calendar'
        }),
        # Candidate 4: Delta 0.25 + Target 90% + SL 2.5x + Roll 7 DTE
        ('EXP-063-INT4', 'Delta 0.25 + Target 90% + SL 2.5x + Roll 7 DTE', {
            'strike_param': 0.25, 'profit_target_pct': 0.90, 'stop_loss_mult': 2.5, 'roll_dte': 7, 'roll_mode': 'calendar'
        }),
        # Candidate 5: Delta 0.25 + Target 80% + SL 3.0x + Roll 7 TS (Trading Sessions)
        ('EXP-064-INT5', 'Delta 0.25 + Target 80% + SL 3.0x + Roll 7 Trading Sessions', {
            'strike_param': 0.25, 'profit_target_pct': 0.80, 'stop_loss_mult': 3.0, 'roll_mode': 'trading_sessions', 'roll_trading_sessions': 7
        }),
        # Candidate 6: Delta 0.20 + Target 90% + SL 3.0x + Roll 10 DTE
        ('EXP-065-INT6', 'Delta 0.20 + Target 90% + SL 3.0x + Roll 10 DTE', {
            'strike_param': 0.20, 'profit_target_pct': 0.90, 'stop_loss_mult': 3.0, 'roll_dte': 10, 'roll_mode': 'calendar'
        }),
        # Candidate 7: Delta 0.25 + Target 80% + SL 3.0x + ATM IV >= 18%
        ('EXP-066-INT7', 'Delta 0.25 + Target 80% + SL 3.0x + ATM IV >= 18%', {
            'strike_param': 0.25, 'profit_target_pct': 0.80, 'stop_loss_mult': 3.0, 'roll_dte': 10, 'atm_iv_min': 0.18
        }),
        # Candidate 8: Delta 0.20 + Target 80% + SL 2.5x + Roll 7 TS
        ('EXP-067-INT8', 'Delta 0.20 + Target 80% + SL 2.5x + Roll 7 Trading Sessions', {
            'strike_param': 0.20, 'profit_target_pct': 0.80, 'stop_loss_mult': 2.5, 'roll_mode': 'trading_sessions', 'roll_trading_sessions': 7
        })
    ]

    for c_id, c_name, custom_p in interactions:
        p = base_params.copy()
        p.update(custom_p)
        experiments.append({
            'id': c_id,
            'category': '6. Parameter Interactions',
            'name': c_name,
            'params': p
        })

    return experiments


def main():
    print("=" * 80)
    print("  STARTING NIFTY COVERED CALL OPTIMIZATION RESEARCH SUITE")
    print(f"  Research Directory: {RESEARCH_DIR}")
    print(f"  Reference Capital:  ₹{INITIAL_CAPITAL:,.2f}")
    print("=" * 80)

    # 1. Load Data
    t0 = time.time()
    print("\n[*] Loading dataset...")
    df = load_options_dataset(OPTIONS_DATA_PATH)
    print("[*] Computing underlying spot features, ATM IV, and trend EMA...")
    features = compute_underlying_features(df)
    features['ema_100'] = features['spot'].ewm(span=100, adjust=False).mean()
    features['trend_bullish'] = features['spot'] > features['ema_100']

    bt = ExtendedOptionsBacktester(df, features, symbol='NIFTY')
    print(f"[✓] Backtester ready in {time.time() - t0:.2f}s")

    manifest = build_experiment_manifest()
    print(f"[*] Total Experiments to Execute: {len(manifest)}")

    results_list = []
    splits_list = []
    wf_list = []
    stress_list = []

    for idx, exp in enumerate(manifest):
        e_id = exp['id']
        e_name = exp['name']
        e_cat = exp['category']
        e_params = exp['params']

        print(f"\n[{idx+1}/{len(manifest)}] Running {e_id}: {e_name}...")
        res = evaluate_experiment(bt, features, e_id, e_name, e_params)

        results_list.append({
            'Experiment ID': e_id,
            'Category': e_cat,
            'Name': e_name,
            'Trades': res['trades'],
            'Win Rate (%)': res['win_rate'],
            'Total Net PnL (₹)': res['total_net_pnl'],
            'Calendar CAGR (0% Cash) (%)': res['calendar_cagr'],
            'Calendar CAGR (4.8% Cash) (%)': res['cagr_liquid'],
            'Return on Total Cap (%)': res['annual_ret_total_cap'],
            'Return on Deployed Cap (%)': res['annual_ret_deployed'],
            'Daily MTM Max DD (%)': res['true_daily_max_dd'],
            'Daily MTM Max DD (4.8% Cash) (%)': res['max_dd_liquid'],
            'Sharpe Ratio': res['sharpe'],
            'Sharpe CI 90% Lower': res['sharpe_ci'][0],
            'Sharpe CI 90% Upper': res['sharpe_ci'][1],
            'Profit Factor': res['profit_factor'],
            'Worst Trade PnL (₹)': res['worst_trade_pnl'],
            'Worst Trade Ret (%)': res['worst_trade_pct'],
            'Market Exposure (%)': res['market_exposure_pct'],
            'Avg Capital Deployed (₹)': res['avg_capital_deployed']
        })

        # Chronological Splits
        sp = run_chronological_splits(bt, features, e_params, e_id)
        splits_list.extend(sp)

        # Walk-Forward Rolling
        wf = run_walk_forward_rolling(bt, features, e_params, e_id)
        wf_list.extend(wf)

        # Stress Tests (using net delta 0.70 for delta 0.30, 0.75 for delta 0.25, 0.80 for delta 0.20)
        c_delta = e_params.get('strike_param', 0.30)
        net_delta = 1.0 - c_delta if e_params.get('strike_mode') == 'delta' else 0.70
        st = run_stress_tests(res['trades_df'], e_id, net_delta=net_delta)
        stress_list.extend(st)

    # -------------------------------------------------------------------------
    # SAVE AUDIT DATASETS
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  SAVING AUDIT ARTIFACTS IN RESEARCH DIRECTORY")
    print("=" * 80)

    res_df = pd.DataFrame(results_list)
    res_path = RESEARCH_DIR / "optimization_results_matrix.csv"
    res_df.to_csv(res_path, index=False)
    print(f"[✓] Saved results matrix: {res_path}")

    splits_df = pd.DataFrame(splits_list)
    splits_path = RESEARCH_DIR / "optimization_chronological_splits.csv"
    splits_df.to_csv(splits_path, index=False)
    print(f"[✓] Saved chronological splits: {splits_path}")

    wf_df = pd.DataFrame(wf_list)
    wf_path = RESEARCH_DIR / "optimization_walk_forward_matrix.csv"
    wf_df.to_csv(wf_path, index=False)
    print(f"[✓] Saved walk-forward matrix: {wf_path}")

    stress_df = pd.DataFrame(stress_list)
    stress_path = RESEARCH_DIR / "optimization_stress_test_matrix.csv"
    stress_df.to_csv(stress_path, index=False)
    print(f"[✓] Saved stress test matrix: {stress_path}")

    # Build sensitivity summary for each parameter
    sens_rows = []
    # Delta sensitivity
    delta_exps = res_df[res_df['Category'] == '1. Delta Sweep']
    for _, r in delta_exps.iterrows():
        sens_rows.append({
            'Dimension': 'Short Delta',
            'Value': r['Name'].replace('OTM Selection: Target Delta ', ''),
            'Trades': r['Trades'],
            'Win Rate (%)': f"{r['Win Rate (%)']:.1f}%",
            'Net PnL (₹)': f"{r['Total Net PnL (₹)']:,.2f}",
            'CAGR (%)': f"{r['Calendar CAGR (0% Cash) (%)']:.2f}%",
            'CAGR (+Liquid) (%)': f"{r['Calendar CAGR (4.8% Cash) (%)']:.2f}%",
            'Daily Max DD (%)': f"{r['Daily MTM Max DD (%)']:.2f}%",
            'Sharpe': f"{r['Sharpe Ratio']:.2f}",
            'Profit Factor': f"{r['Profit Factor']:.2f}"
        })
    # Target sensitivity
    target_exps = res_df[res_df['Category'] == '2. Exit Target Sweep']
    for _, r in target_exps.iterrows():
        sens_rows.append({
            'Dimension': 'Profit Target',
            'Value': r['Name'].replace('Premium Decay Exit Target: ', ''),
            'Trades': r['Trades'],
            'Win Rate (%)': f"{r['Win Rate (%)']:.1f}%",
            'Net PnL (₹)': f"{r['Total Net PnL (₹)']:,.2f}",
            'CAGR (%)': f"{r['Calendar CAGR (0% Cash) (%)']:.2f}%",
            'CAGR (+Liquid) (%)': f"{r['Calendar CAGR (4.8% Cash) (%)']:.2f}%",
            'Daily Max DD (%)': f"{r['Daily MTM Max DD (%)']:.2f}%",
            'Sharpe': f"{r['Sharpe Ratio']:.2f}",
            'Profit Factor': f"{r['Profit Factor']:.2f}"
        })
    # SL sensitivity
    sl_exps = res_df[res_df['Category'] == '3. Stop Loss Sweep']
    for _, r in sl_exps.iterrows():
        sens_rows.append({
            'Dimension': 'Stop Loss Multiplier',
            'Value': r['Name'],
            'Trades': r['Trades'],
            'Win Rate (%)': f"{r['Win Rate (%)']:.1f}%",
            'Net PnL (₹)': f"{r['Total Net PnL (₹)']:,.2f}",
            'CAGR (%)': f"{r['Calendar CAGR (0% Cash) (%)']:.2f}%",
            'CAGR (+Liquid) (%)': f"{r['Calendar CAGR (4.8% Cash) (%)']:.2f}%",
            'Daily Max DD (%)': f"{r['Daily MTM Max DD (%)']:.2f}%",
            'Sharpe': f"{r['Sharpe Ratio']:.2f}",
            'Profit Factor': f"{r['Profit Factor']:.2f}"
        })
    # Roll sensitivity
    roll_exps = res_df[res_df['Category'].str.contains('4. Roll Timing')]
    for _, r in roll_exps.iterrows():
        sens_rows.append({
            'Dimension': 'Roll Timing',
            'Value': r['Name'].replace('Roll Threshold: ', ''),
            'Trades': r['Trades'],
            'Win Rate (%)': f"{r['Win Rate (%)']:.1f}%",
            'Net PnL (₹)': f"{r['Total Net PnL (₹)']:,.2f}",
            'CAGR (%)': f"{r['Calendar CAGR (0% Cash) (%)']:.2f}%",
            'CAGR (+Liquid) (%)': f"{r['Calendar CAGR (4.8% Cash) (%)']:.2f}%",
            'Daily Max DD (%)': f"{r['Daily MTM Max DD (%)']:.2f}%",
            'Sharpe': f"{r['Sharpe Ratio']:.2f}",
            'Profit Factor': f"{r['Profit Factor']:.2f}"
        })

    sens_df = pd.DataFrame(sens_rows)
    sens_path = RESEARCH_DIR / "optimization_sensitivity_matrix.csv"
    sens_df.to_csv(sens_path, index=False)
    print(f"[✓] Saved sensitivity matrix: {sens_path}")

    print("\n" + "=" * 80)
    print("  OPTIMIZATION SUITE RUN COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()
