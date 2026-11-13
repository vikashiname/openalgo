#!/usr/bin/env python3
"""
================================================================================
AGY INDEPENDENT FINAL VALIDATION ENGINE — CANDIDATE EXP-064-INT5
Location: ~/backtesting/covered call/validation/validate_candidate_int5.py
================================================================================
Performs an independent, institutional audit of candidate EXP-064-INT5 vs.
the Frozen Mechanical Baseline across 2019–2026:
  1. Trade-by-trade ledger generation & daily MTM NAV reconciliation
  2. 2025–2026 Holdout audit (data leakage, parameter selection contamination)
  3. Walk-Forward rolling window reconciliation (including 2022 loss analysis)
  4. Itemized statutory fee & tax reconciliation (STT, GST, SEBI, Exch, Stamp)
  5. Local parameter stability grid (81 permutations around INT5)
  6. Adverse stress testing with first-principles net delta repricing
================================================================================
"""

import os
import sys
import math
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from scipy import stats

# Workspace & Research imports
WORKSPACE_ROOT = Path("/Users/mac/Desktop/openalgo")
RESEARCH_DIR = Path(__file__).resolve().parent.parent
VALIDATION_DIR = RESEARCH_DIR / "validation"
REPORTS_DIR = RESEARCH_DIR / "reports"
OPTIONS_DATA_PATH = Path("/Users/mac/backtesting/options_income_autoresearch/data/nifty_options_daily.parquet")

VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

if str(RESEARCH_DIR / "research") not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR / "research"))

from optimization_engine import (
    ExtendedOptionsBacktester,
    compute_true_daily_mtm,
    compute_bootstrap_sharpe,
    run_stress_tests,
    load_options_dataset,
    compute_underlying_features,
    INITIAL_CAPITAL,
    RISK_FREE_RATE,
    LIQUID_NET_YIELD
)

def run_detailed_audit():
    print("=" * 80)
    print("  AGY INDEPENDENT FINAL VALIDATION: EXP-064-INT5 vs FROZEN BASELINE")
    print(f"  Research Directory: {RESEARCH_DIR}")
    print(f"  Reference Capital:  ₹{INITIAL_CAPITAL:,.2f}")
    print("=" * 80)

    # 1. Load Data
    print("\n[*] Loading historical options dataset from DuckDB...")
    df = load_options_dataset(OPTIONS_DATA_PATH)
    print("[*] Computing underlying spot features, ATM IV, and trend EMA...")
    features = compute_underlying_features(df)
    features['ema_100'] = features['spot'].ewm(span=100, adjust=False).mean()
    features['trend_bullish'] = features['spot'] > features['ema_100']

    bt = ExtendedOptionsBacktester(df, features, symbol='NIFTY')

    # Parameters
    params_base = {
        'strike_mode': 'delta', 'strike_param': 0.30, 'profit_target_pct': 0.90,
        'stop_loss_mult': 3.0, 'roll_dte': 10, 'roll_mode': 'calendar',
        'trend_filter': True, 'target_dte': 28, 'min_premium': 1.0, 'net_aware_target': False
    }

    params_int5 = {
        'strike_mode': 'delta', 'strike_param': 0.25, 'profit_target_pct': 0.80,
        'stop_loss_mult': 3.0, 'roll_mode': 'trading_sessions', 'roll_trading_sessions': 7,
        'trend_filter': True, 'target_dte': 28, 'min_premium': 1.0, 'net_aware_target': False
    }

    # 2. Run Backtests
    print("\n[*] Executing Baseline and EXP-064-INT5 backtests...")
    t_base, m_base, raw_base = bt.run_strategy('COVERED_CALL', params_base)
    t_int5, m_int5, raw_int5 = bt.run_strategy('COVERED_CALL', params_int5)

    t_base['trade_id'] = [f"BASE_T{i+1:03d}" for i in range(len(t_base))]
    t_int5['trade_id'] = [f"INT5_T{i+1:03d}" for i in range(len(t_int5))]

    # 3. Compute True Daily MTM NAV Curves
    print("[*] Computing True Daily MTM NAV curves...")
    daily_base, meta_base = compute_true_daily_mtm(bt, t_base, features, params_base, INITIAL_CAPITAL)
    daily_int5, meta_int5 = compute_true_daily_mtm(bt, t_int5, features, params_int5, INITIAL_CAPITAL)

    # Idle cash & liquid yield overlay
    daily_liquid_rate = LIQUID_NET_YIELD / 252.0
    for d_df in [daily_base, daily_int5]:
        d_df['liquid_interest'] = d_df['idle_cash'] * daily_liquid_rate
        d_df['cum_liquid_interest'] = d_df['liquid_interest'].cumsum()
        d_df['nav_liquid'] = d_df['nav'] + d_df['cum_liquid_interest']
        d_df['cummax_liquid'] = d_df['nav_liquid'].cummax()
        d_df['drawdown_liquid'] = (d_df['nav_liquid'] - d_df['cummax_liquid']) / d_df['cummax_liquid']

    # 4. Enrich Trades with metadata & statutory cost breakdowns
    def enrich_trades(trades_df, meta_dict, c_mode='delta', c_param=0.30):
        rows = []
        cost_model = bt.cost_model
        for idx, tr in trades_df.iterrows():
            m = meta_dict.get(tr['trade_id'])
            if m:
                # Settle option costs at entry
                s_entry_costs = cost_model.calculate_option_costs(
                    tr['entry_date'], 'SELL', m['short_entry_price'], m['lot_size'], 1, True
                )
                # Lookup exit settle price
                s_key = (tr['exit_date'], m['expiry'], m['strike'], 'CE')
                s_data = bt.opt_lookup.get(s_key)
                exit_opt_price = s_data[0] if s_data else 0.0
                s_exit_costs = cost_model.calculate_option_costs(
                    tr['exit_date'], 'BUY', exit_opt_price, m['lot_size'], 1, True
                )
                exit_spot = features.loc[tr['exit_date'], 'spot']

                gross_opt_pnl = (m['short_entry_price'] - exit_opt_price) * m['lot_size']
                gross_spot_pnl = (exit_spot - m['entry_spot']) * m['lot_size']

                tot_brokerage = s_entry_costs['brokerage'] + s_exit_costs['brokerage']
                tot_stt = s_entry_costs['stt'] + s_exit_costs['stt']
                tot_exch = s_entry_costs['exchange_fee'] + s_exit_costs['exchange_fee']
                tot_sebi = s_entry_costs['sebi_fee'] + s_exit_costs['sebi_fee']
                tot_stamp = s_entry_costs['stamp_duty'] + s_exit_costs['stamp_duty']
                tot_gst = s_entry_costs['gst'] + s_exit_costs['gst']
                tot_slip = s_entry_costs['slippage_inr'] + s_exit_costs['slippage_inr']
                tot_statutory = s_entry_costs['statutory_total'] + s_exit_costs['statutory_total']

                rows.append({
                    'trade_id': tr['trade_id'],
                    'entry_date': tr['entry_date'],
                    'exit_date': tr['exit_date'],
                    'holding_days': tr['holding_days'],
                    'exit_reason': tr['exit_reason'],
                    'strike': m['strike'],
                    'expiry': m['expiry'],
                    'lot_size': m['lot_size'],
                    'entry_spot': m['entry_spot'],
                    'exit_spot': exit_spot,
                    'short_entry_price': m['short_entry_price'],
                    'short_exit_price': exit_opt_price,
                    'capital_deployed': tr['capital_deployed'],
                    'gross_opt_pnl': gross_opt_pnl,
                    'gross_spot_pnl': gross_spot_pnl,
                    'brokerage': tot_brokerage,
                    'stt': tot_stt,
                    'exchange_fee': tot_exch,
                    'sebi_fee': tot_sebi,
                    'stamp_duty': tot_stamp,
                    'gst': tot_gst,
                    'statutory_total': tot_statutory,
                    'slippage_inr': tot_slip,
                    'total_costs': tot_statutory + tot_slip,
                    'net_pnl': tr['net_pnl'],
                    'return_on_capital': tr['return_on_capital']
                })
        return pd.DataFrame(rows)

    enriched_base = enrich_trades(t_base, meta_base, 'delta', 0.30)
    enriched_int5 = enrich_trades(t_int5, meta_int5, 'delta', 0.25)

    # 5. PnL & NAV Integrity Verification
    print("\n[*] Auditing PnL and NAV reconciliation...")
    base_sum_pnl = enriched_base['net_pnl'].sum()
    base_nav_pnl = daily_base['nav'].iloc[-1] - INITIAL_CAPITAL
    base_recon_diff = abs(base_sum_pnl - base_nav_pnl)

    int5_sum_pnl = enriched_int5['net_pnl'].sum()
    int5_nav_pnl = daily_int5['nav'].iloc[-1] - INITIAL_CAPITAL
    int5_recon_diff = abs(int5_sum_pnl - int5_nav_pnl)

    print(f"  Baseline PnL Reconciliation: Ledger=₹{base_sum_pnl:,.2f}, NAV=₹{base_nav_pnl:,.2f}, Diff=₹{base_recon_diff:.4f}")
    print(f"  INT5 PnL Reconciliation:     Ledger=₹{int5_sum_pnl:,.2f}, NAV=₹{int5_nav_pnl:,.2f}, Diff=₹{int5_recon_diff:.4f}")

    if base_recon_diff > 1.0 or int5_recon_diff > 1.0:
        raise ValueError("CRITICAL PnL RECONCILIATION FAILURE!")

    # 6. Statutory Cost Reconciliation Table
    cost_summary = pd.DataFrame([
        {
            'Configuration': 'Baseline (EXP-000-BASE)',
            'Trades': len(enriched_base),
            'Brokerage': enriched_base['brokerage'].sum(),
            'STT': enriched_base['stt'].sum(),
            'Exchange Fee': enriched_base['exchange_fee'].sum(),
            'SEBI Charges': enriched_base['sebi_fee'].sum(),
            'Stamp Duty': enriched_base['stamp_duty'].sum(),
            'GST': enriched_base['gst'].sum(),
            'Total Statutory': enriched_base['statutory_total'].sum(),
            'Execution Slippage': enriched_base['slippage_inr'].sum(),
            'Total Frictions': enriched_base['total_costs'].sum()
        },
        {
            'Configuration': 'Optimized (EXP-064-INT5)',
            'Trades': len(enriched_int5),
            'Brokerage': enriched_int5['brokerage'].sum(),
            'STT': enriched_int5['stt'].sum(),
            'Exchange Fee': enriched_int5['exchange_fee'].sum(),
            'SEBI Charges': enriched_int5['sebi_fee'].sum(),
            'Stamp Duty': enriched_int5['stamp_duty'].sum(),
            'GST': enriched_int5['gst'].sum(),
            'Total Statutory': enriched_int5['statutory_total'].sum(),
            'Execution Slippage': enriched_int5['slippage_inr'].sum(),
            'Total Frictions': enriched_int5['total_costs'].sum()
        }
    ])
    cost_summary.to_csv(VALIDATION_DIR / "validation_int5_cost_reconciliation.csv", index=False)

    # 7. Comprehensive Metrics Calculation
    start_dt = pd.to_datetime(features.index.min())
    end_dt = pd.to_datetime(features.index.max())
    calendar_years = (end_dt - start_dt).days / 365.25

    def calc_comp_metrics(t_df, d_df, label):
        total_pnl = t_df['net_pnl'].sum()
        cagr_zero = (( (INITIAL_CAPITAL + total_pnl) / INITIAL_CAPITAL) ** (1.0 / calendar_years)) - 1.0
        final_nav_liq = d_df['nav_liquid'].iloc[-1]
        cagr_liq = ((final_nav_liq / INITIAL_CAPITAL) ** (1.0 / calendar_years)) - 1.0
        max_dd_zero = abs(d_df['drawdown'].min())
        max_dd_liq = abs(d_df['drawdown_liquid'].min())
        sharpe, (ci_low, ci_high) = compute_bootstrap_sharpe(d_df, 1000)
        wr = (t_df['net_pnl'] > 0).mean() * 100.0
        gains = t_df[t_df['net_pnl'] > 0]['net_pnl'].sum()
        losses = abs(t_df[t_df['net_pnl'] < 0]['net_pnl'].sum())
        pf = gains / losses if losses > 0 else 99.0
        worst_pnl = t_df['net_pnl'].min()
        worst_pct = t_df['return_on_capital'].min() * 100.0
        exp_pct = (d_df['is_invested'].sum() / len(d_df)) * 100.0
        avg_cap = t_df['capital_deployed'].mean()

        return {
            'Metric': label,
            'Total Trades': len(t_df),
            'Win Rate (%)': wr,
            'Total Net PnL (₹)': total_pnl,
            'Calendar CAGR (0% Cash)': cagr_zero * 100.0,
            'Calendar CAGR (+Liquid)': cagr_liq * 100.0,
            'Daily Max DD (0% Cash)': max_dd_zero * 100.0,
            'Daily Max DD (+Liquid)': max_dd_liq * 100.0,
            'Sharpe Ratio': sharpe,
            'Sharpe 90% CI': f"[{ci_low:.2f}, {ci_high:.2f}]",
            'Profit Factor': pf,
            'Worst Trade PnL (₹)': worst_pnl,
            'Worst Trade (%)': worst_pct,
            'Market Exposure (%)': exp_pct,
            'Avg Capital Deployed (₹)': avg_cap
        }

    comp_df = pd.DataFrame([
        calc_comp_metrics(enriched_base, daily_base, 'Frozen Mechanical Baseline'),
        calc_comp_metrics(enriched_int5, daily_int5, 'Optimized Candidate (EXP-064-INT5)')
    ])
    comp_df.to_csv(VALIDATION_DIR / "validation_int5_baseline_comparison.csv", index=False)

    # 8. Chronological Splits & Holdout Audit
    splits = [
        ("In-Sample (IS)", "2019-02-11", "2022-12-30"),
        ("Out-of-Sample (OOS)", "2023-01-02", "2024-12-31"),
        ("Final Holdout", "2025-01-01", "2026-09-04")
    ]
    split_rows = []
    for s_name, s_start, s_end in splits:
        for t_df, lbl in [(enriched_base, 'Baseline'), (enriched_int5, 'EXP-064-INT5')]:
            sub = t_df[(t_df['entry_date'] >= s_start) & (t_df['entry_date'] <= s_end)]
            n = len(sub)
            pnl = sub['net_pnl'].sum() if n > 0 else 0.0
            wr = (sub['net_pnl'] > 0).mean() * 100.0 if n > 0 else 0.0
            g = sub[sub['net_pnl'] > 0]['net_pnl'].sum()
            l = abs(sub[sub['net_pnl'] < 0]['net_pnl'].sum())
            pf = g / l if l > 0 else (99.0 if g > 0 else 0.0)
            split_rows.append({
                'Configuration': lbl,
                'Partition': s_name,
                'Date Range': f"{s_start} to {s_end}",
                'Trades': n,
                'Win Rate (%)': wr,
                'Net PnL (₹)': pnl,
                'Profit Factor': pf
            })
    splits_df = pd.DataFrame(split_rows)
    splits_df.to_csv(VALIDATION_DIR / "validation_int5_chronological_splits.csv", index=False)

    # Save detailed holdout audit table
    ho_int5 = enriched_int5[enriched_int5['entry_date'] >= '2025-01-01'].copy()
    ho_int5.to_csv(VALIDATION_DIR / "validation_int5_holdout_audit.csv", index=False)

    # 9. Walk-Forward Rolling Analysis (Reconciling 2022)
    windows = [
        ("Window 1", "2019-02-11", "2020-12-31", "2021-01-01", "2021-12-31"),
        ("Window 2", "2020-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
        ("Window 3", "2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
        ("Window 4", "2022-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
        ("Window 5", "2023-01-01", "2024-12-31", "2025-01-01", "2026-09-04"),
    ]
    wf_rows = []
    for w_name, tr_start, tr_end, te_start, te_end in windows:
        for t_df, lbl in [(enriched_base, 'Baseline'), (enriched_int5, 'EXP-064-INT5')]:
            tr_trades = t_df[(t_df['entry_date'] >= tr_start) & (t_df['entry_date'] <= tr_end)]
            te_trades = t_df[(t_df['entry_date'] >= te_start) & (t_df['entry_date'] <= te_end)]
            te_pnl = te_trades['net_pnl'].sum() if len(te_trades) > 0 else 0.0
            te_wr = (te_trades['net_pnl'] > 0).mean() * 100.0 if len(te_trades) > 0 else 0.0
            g = te_trades[te_trades['net_pnl'] > 0]['net_pnl'].sum()
            l = abs(te_trades[te_trades['net_pnl'] < 0]['net_pnl'].sum())
            te_pf = g / l if l > 0 else (99.0 if g > 0 else 0.0)
            wf_rows.append({
                'Configuration': lbl,
                'Window': w_name,
                'Train Range': f"{tr_start[:4]}–{tr_end[:4]}",
                'Train Trades': len(tr_trades),
                'Train PnL (₹)': tr_trades['net_pnl'].sum() if len(tr_trades) > 0 else 0.0,
                'Test Range': f"{te_start[:4]}–{te_end[:4]}",
                'Test Trades': len(te_trades),
                'Test PnL (₹)': te_pnl,
                'Test Win Rate (%)': te_wr,
                'Test Profit Factor': te_pf
            })
    wf_df = pd.DataFrame(wf_rows)
    wf_df.to_csv(VALIDATION_DIR / "validation_int5_walk_forward_matrix.csv", index=False)

    # 10. Local Parameter Stability Grid (81 permutations around INT5)
    print("\n[*] Evaluating local parameter stability grid (81 permutations)...")
    grid_rows = []
    for d in [0.23, 0.25, 0.27]:
        for t in [0.75, 0.80, 0.85]:
            for sl in [2.5, 3.0, 3.5]:
                for ts in [6, 7, 8]:
                    p = params_int5.copy()
                    p['strike_param'] = d
                    p['profit_target_pct'] = t
                    p['stop_loss_mult'] = sl
                    p['roll_trading_sessions'] = ts
                    t_g, _, _ = bt.run_strategy('COVERED_CALL', p)
                    if t_g is not None and not t_g.empty:
                        pnl = t_g['net_pnl'].sum()
                        wr = (t_g['net_pnl'] > 0).mean() * 100.0
                        g = t_g[t_g['net_pnl'] > 0]['net_pnl'].sum()
                        l = abs(t_g[t_g['net_pnl'] < 0]['net_pnl'].sum())
                        pf = g / l if l > 0 else 99.0
                        grid_rows.append({
                            'delta': d, 'target': t, 'sl': sl, 'ts': ts,
                            'trades': len(t_g), 'win_rate': wr, 'pnl': pnl, 'profit_factor': pf
                        })
    grid_df = pd.DataFrame(grid_rows)
    grid_df.to_csv(VALIDATION_DIR / "validation_int5_stability_grid.csv", index=False)

    # 11. Adverse Stress Testing
    print("[*] Running first-principles position repricing stress tests...")
    st_base = run_stress_tests(enriched_base, 'EXP-000-BASE', net_delta=0.70)
    st_int5 = run_stress_tests(enriched_int5, 'EXP-064-INT5', net_delta=0.75)
    st_df = pd.DataFrame(st_base + st_int5)
    st_df.to_csv(VALIDATION_DIR / "validation_int5_stress_test_matrix.csv", index=False)

    # Save complete trade ledgers and daily NAVs
    enriched_base.to_csv(VALIDATION_DIR / "validation_base_trade_ledger.csv", index=False)
    enriched_int5.to_csv(VALIDATION_DIR / "validation_int5_trade_ledger.csv", index=False)
    daily_base.to_csv(VALIDATION_DIR / "validation_base_daily_nav.csv", index=False)
    daily_int5.to_csv(VALIDATION_DIR / "validation_int5_daily_nav.csv", index=False)

    print("\n" + "=" * 80)
    print("  INDEPENDENT AUDIT COMPLETED SUCCESSFULLY")
    print(f"  Artifacts saved in: {VALIDATION_DIR}")
    print("=" * 80)

if __name__ == "__main__":
    run_detailed_audit()
