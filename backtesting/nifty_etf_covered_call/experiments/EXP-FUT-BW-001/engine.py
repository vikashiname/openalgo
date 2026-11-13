#!/usr/bin/env python3
"""
================================================================================
AGY INSTITUTIONAL RESEARCH ENGINE — EXP-FUT-BW-001
Location: ~/backtesting/covered call/experiments/EXP-FUT-BW-001/engine.py
================================================================================
Experiment ID: EXP-FUT-BW-001
Strategy: NIFTY Synthetic Futures Buy-Write with Liquid Treasury Yield Overlay
Underlying Leg: Long 1 Lot FUTIDX NIFTY (Matching Expiry & Lot Size)
Option Leg: Short 1 Lot OPTIDX NIFTY CE (Delta 0.25, 80% Exit, 3.0x SL, 7-TS Roll)
Collateral / Treasury Leg: Overnight Liquid TREPS / Cash ETF Yield Overlay (4.8% net p.a.)

Strict research scope: Confined within ~/backtesting/covered call/experiments/EXP-FUT-BW-001/
================================================================================
"""

import os
import sys
import json
import math
import bisect
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm
import duckdb

# Path setup
EXPERIMENT_DIR = Path(__file__).resolve().parent
RESEARCH_DIR = EXPERIMENT_DIR.parent.parent
WORKSPACE_ROOT = Path("/Users/mac/Desktop/openalgo")
DATA_PATH = Path("/Users/mac/backtesting/options_income_autoresearch/data/nifty_options_daily.parquet")

if str(RESEARCH_DIR / "research") not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR / "research"))

from optimization_engine import (
    ExtendedOptionsBacktester,
    compute_underlying_features,
    load_options_dataset,
    compute_bootstrap_sharpe,
    INITIAL_CAPITAL,
    RISK_FREE_RATE,
    LIQUID_NET_YIELD
)

# Load configuration
CONFIG_PATH = EXPERIMENT_DIR / "config.json"
with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)

INITIAL_CAP = CONFIG["capital"]["initial_capital_inr"]
NET_LIQUID_YIELD = CONFIG["capital"]["liquid_net_yield_pa"]
DAILY_LIQUID_RATE = NET_LIQUID_YIELD / 252.0


def build_synthetic_futures_table(data_path: Path):
    """
    Extracts empirical synthetic futures prices across all historical trade dates
    and expiries using Put-Call Parity: F_t = median(K + C(K) - P(K)) at ATM strikes.
    """
    print("[*] Extracting historical synthetic futures curve via DuckDB...")
    con = duckdb.connect(':memory:')
    query = f"""
        WITH atm_options AS (
            SELECT 
                CAST(trade_date AS VARCHAR) AS trade_date,
                CAST(expiry_date AS VARCHAR) AS expiry_date,
                CAST(strike AS FLOAT) AS strike,
                option_type,
                CAST(settle_price AS FLOAT) AS settle_price,
                CAST(underlying_price AS FLOAT) AS underlying_price
            FROM read_parquet('{data_path}')
            WHERE settle_price > 0.1
              AND ABS(strike - underlying_price) <= underlying_price * 0.025
              AND date_diff('day', CAST(trade_date AS DATE), CAST(expiry_date AS DATE)) BETWEEN 0 AND 75
        ),
        pivoted AS (
            SELECT 
                trade_date,
                expiry_date,
                strike,
                underlying_price,
                MAX(CASE WHEN option_type = 'CE' THEN settle_price END) as ce_price,
                MAX(CASE WHEN option_type = 'PE' THEN settle_price END) as pe_price
            FROM atm_options
            GROUP BY trade_date, expiry_date, strike, underlying_price
            HAVING ce_price IS NOT NULL AND pe_price IS NOT NULL
        )
        SELECT 
            trade_date,
            expiry_date,
            underlying_price,
            MEDIAN(strike + ce_price - pe_price) AS f_synth
        FROM pivoted
        GROUP BY trade_date, expiry_date, underlying_price
    """
    fut_df = con.execute(query).df()
    con.close()
    
    fut_lookup = {}
    for _, row in fut_df.iterrows():
        fut_lookup[(row['trade_date'], row['expiry_date'])] = row['f_synth']
    
    print(f"[✓] Extracted {len(fut_lookup):,} empirical futures pricing points.")
    return fut_lookup


def calculate_futures_costs(trade_date, action, price, lot_size):
    """
    Computes verified statutory transaction costs and execution slippage for NIFTY Futures.
    action: 'BUY' or 'SELL'
    """
    turnover = price * lot_size
    brokerage = CONFIG["futures_frictions"]["brokerage_per_order_inr"]
    exchange_fee = turnover * CONFIG["futures_frictions"]["exchange_txn_fee_rate"]
    sebi_fee = turnover * CONFIG["futures_frictions"]["sebi_turnover_rate"]
    gst = (brokerage + exchange_fee + sebi_fee) * CONFIG["futures_frictions"]["gst_rate"]
    
    slippage_pts = CONFIG["futures_frictions"]["slippage_points"]
    slippage_inr = slippage_pts * lot_size
    
    if action.upper() == 'BUY':
        stamp_duty = turnover * CONFIG["futures_frictions"]["stamp_duty_buy_rate"]
        stt = 0.0
        eff_price = price + slippage_pts
    else:
        stamp_duty = 0.0
        stt_rate = CONFIG["futures_frictions"]["stt_sell_post_oct2024"] if str(trade_date) >= '2024-10-01' else CONFIG["futures_frictions"]["stt_sell_pre_oct2024"]
        stt = turnover * stt_rate
        eff_price = price - slippage_pts
        
    statutory = brokerage + stt + exchange_fee + sebi_fee + stamp_duty + gst
    return {
        'turnover': turnover,
        'brokerage': brokerage,
        'stt': stt,
        'exchange_fee': exchange_fee,
        'sebi_fee': sebi_fee,
        'stamp_duty': stamp_duty,
        'gst': gst,
        'statutory_total': statutory,
        'slippage_inr': slippage_inr,
        'total_friction': statutory + slippage_inr,
        'effective_fill_price': eff_price
    }


def calculate_dynamic_margin(spot, call_price, lot_size, atm_iv):
    """
    Calculates combined SPAN + Exposure margin for Long Future + Short Call (Buy-Write).
    Under NCL SPAN rules:
      - Price Scan Range (PSR) dynamically scales with ATM volatility (min 8%, expands up to 16%+ in crashes).
      - Downside Scan Risk: max(0, (PSR * Spot - CallPrice) * Lot).
      - Extreme Loss Margin (ELM): 2.0% of notional (0.02 * Spot * Lot).
    """
    daily_vol = atm_iv / np.sqrt(252.0)
    psr = max(CONFIG["margin_model"]["base_psr"], CONFIG["margin_model"]["vol_scaling_factor"] * daily_vol)
    
    scan_risk = max(0.0, (psr * spot - call_price) * lot_size)
    elm = CONFIG["margin_model"]["elm_rate"] * spot * lot_size
    total_margin = scan_risk + elm
    return total_margin, psr


def run_experiment():
    print("=" * 80)
    print("  AGY INSTITUTIONAL EXPERIMENT: EXP-FUT-BW-001")
    print("  Strategy: NIFTY Futures Buy-Write with Liquid Treasury Yield Overlay")
    print(f"  Initial Capital: ₹{INITIAL_CAP:,.2f} | Net Liquid Yield: {NET_LIQUID_YIELD*100:.1f}% p.a.")
    print("=" * 80)

    # 1. Ingestion
    print("\n[*] Loading historical dataset...")
    df = load_options_dataset(DATA_PATH)
    features = compute_underlying_features(df)
    features['ema_100'] = features['spot'].ewm(span=100, adjust=False).mean()
    features['trend_bullish'] = features['spot'] > features['ema_100']

    fut_lookup = build_synthetic_futures_table(DATA_PATH)
    bt = ExtendedOptionsBacktester(df, features, symbol='NIFTY')
    cost_model = bt.cost_model

    dates = sorted(list(features.index))
    target_dte = CONFIG["strategy_rules"]["target_dte_days"]
    target_delta = CONFIG["strategy_rules"]["target_delta"]
    profit_target_pct = CONFIG["strategy_rules"]["profit_target_decay_pct"]
    stop_loss_mult = CONFIG["strategy_rules"]["stop_loss_multiple"]
    roll_ts = CONFIG["strategy_rules"]["roll_threshold_trading_sessions"]

    # 2. Simulation Loop
    print("\n[*] Executing Futures Buy-Write simulation engine...")
    trades = []
    active_position = None
    i = 0

    while i < len(dates):
        current_date = dates[i]
        feat = features.loc[current_date]
        spot = feat['spot']
        atm_iv = feat['atm_iv']

        # Entry Check
        if active_position is None:
            if not feat['trend_bullish']:
                i += 1
                continue

            c_short = bt.find_contract(current_date, 'CE', target_dte, 'delta', target_delta)
            if c_short is not None and c_short['settle_price'] >= CONFIG["strategy_rules"]["min_option_premium_inr"]:
                lot = c_short['lot_size']
                exp = c_short['expiry_date']
                
                # Option entry costs
                opt_entry = cost_model.calculate_option_costs(
                    current_date, 'SELL', c_short['settle_price'], lot, 1, True
                )
                
                # Futures entry costs
                f_entry_settle = fut_lookup.get((current_date, exp), spot)
                fut_entry = calculate_futures_costs(current_date, 'BUY', f_entry_settle, lot)
                
                # Margin at entry
                margin_entry, _ = calculate_dynamic_margin(spot, c_short['settle_price'], lot, atm_iv)

                active_position = {
                    'entry_date': current_date,
                    'short_strike': c_short['strike'],
                    'short_expiry': exp,
                    'lot_size': lot,
                    'entry_spot': spot,
                    'entry_atm_iv': atm_iv,
                    'short_entry_settle': c_short['settle_price'],
                    'short_entry_fill': opt_entry['effective_fill_price'],
                    'short_entry_statutory': opt_entry['statutory_total'],
                    'short_entry_slippage': opt_entry['slippage_inr'],
                    'short_entry_brokerage': opt_entry['brokerage'],
                    'short_entry_stt': opt_entry['stt'],
                    'short_entry_exchange': opt_entry['exchange_fee'],
                    'short_entry_sebi': opt_entry['sebi_fee'],
                    'short_entry_stamp': opt_entry['stamp_duty'],
                    'short_entry_gst': opt_entry['gst'],
                    'fut_entry_settle': f_entry_settle,
                    'fut_entry_fill': fut_entry['effective_fill_price'],
                    'fut_entry_statutory': fut_entry['statutory_total'],
                    'fut_entry_slippage': fut_entry['slippage_inr'],
                    'fut_entry_brokerage': fut_entry['brokerage'],
                    'fut_entry_stt': fut_entry['stt'],
                    'fut_entry_exchange': fut_entry['exchange_fee'],
                    'fut_entry_sebi': fut_entry['sebi_fee'],
                    'fut_entry_stamp': fut_entry['stamp_duty'],
                    'fut_entry_gst': fut_entry['gst'],
                    'entry_basis': f_entry_settle - spot,
                    'entry_margin': margin_entry
                }

        # Exit & Monitoring Check
        if active_position is not None:
            exp = active_position['short_expiry']
            lot = active_position['lot_size']
            
            # Lookup current prices
            s_key = (current_date, exp, active_position['short_strike'], 'CE')
            s_data = bt.opt_lookup.get(s_key)
            curr_opt_price = s_data[0] if s_data else 0.0
            
            if current_date == exp:
                curr_fut_price = spot
            else:
                curr_fut_price = fut_lookup.get((current_date, exp), spot)

            # Roll check (Trading Sessions remaining)
            ts_remaining = bt.count_trading_sessions_remaining(current_date, exp)
            should_roll = (ts_remaining <= roll_ts)

            premium_gain = (active_position['short_entry_fill'] - curr_opt_price) / active_position['short_entry_fill']

            exit_triggered = False
            exit_reason = None

            if premium_gain >= profit_target_pct:
                exit_triggered = True
                exit_reason = 'PROFIT_TARGET'
            elif curr_opt_price >= (active_position['short_entry_fill'] * stop_loss_mult):
                exit_triggered = True
                exit_reason = 'STOP_LOSS'
            elif should_roll:
                exit_triggered = True
                exit_reason = 'EXPIRY_ROLL'

            if exit_triggered or i == len(dates) - 1:
                # Option exit costs
                opt_exit = cost_model.calculate_option_costs(
                    current_date, 'BUY', curr_opt_price, lot, 1, True
                )
                # Futures exit costs
                fut_exit = calculate_futures_costs(current_date, 'SELL', curr_fut_price, lot)

                # Option PnL
                gross_opt_pnl = (active_position['short_entry_fill'] - opt_exit['effective_fill_price']) * lot
                opt_statutory = active_position['short_entry_statutory'] + opt_exit['statutory_total']
                opt_slippage = active_position['short_entry_slippage'] + opt_exit['slippage_inr']
                net_opt_pnl = gross_opt_pnl - opt_statutory

                # Futures PnL
                gross_fut_pnl = (fut_exit['effective_fill_price'] - active_position['fut_entry_fill']) * lot
                fut_statutory = active_position['fut_entry_statutory'] + fut_exit['statutory_total']
                fut_slippage = active_position['fut_entry_slippage'] + fut_exit['slippage_inr']
                net_fut_pnl = gross_fut_pnl - fut_statutory

                total_net_pnl = net_opt_pnl + net_fut_pnl
                holding_days = (pd.to_datetime(current_date) - pd.to_datetime(active_position['entry_date'])).days

                trade_record = {
                    'trade_id': f"FUT_T{len(trades)+1:03d}",
                    'entry_date': active_position['entry_date'],
                    'exit_date': current_date,
                    'holding_days': holding_days,
                    'exit_reason': exit_reason if exit_triggered else 'FINAL_DATE',
                    'strike': active_position['short_strike'],
                    'expiry': exp,
                    'lot_size': lot,
                    'entry_spot': active_position['entry_spot'],
                    'exit_spot': spot,
                    'entry_basis': active_position['entry_basis'],
                    'exit_basis': curr_fut_price - spot,
                    'fut_entry_settle': active_position['fut_entry_settle'],
                    'fut_entry_fill': active_position['fut_entry_fill'],
                    'fut_exit_settle': curr_fut_price,
                    'fut_exit_fill': fut_exit['effective_fill_price'],
                    'opt_entry_settle': active_position['short_entry_settle'],
                    'opt_entry_fill': active_position['short_entry_fill'],
                    'opt_exit_settle': curr_opt_price,
                    'opt_exit_fill': opt_exit['effective_fill_price'],
                    'entry_margin': active_position['entry_margin'],
                    'gross_fut_pnl': gross_fut_pnl,
                    'fut_statutory': fut_statutory,
                    'fut_slippage': fut_slippage,
                    'fut_total_frictions': fut_statutory + fut_slippage,
                    'net_fut_pnl': net_fut_pnl,
                    'gross_opt_pnl': gross_opt_pnl,
                    'opt_statutory': opt_statutory,
                    'opt_slippage': opt_slippage,
                    'opt_total_frictions': opt_statutory + opt_slippage,
                    'net_opt_pnl': net_opt_pnl,
                    'total_statutory': fut_statutory + opt_statutory,
                    'total_slippage': fut_slippage + opt_slippage,
                    'total_frictions': fut_statutory + fut_slippage + opt_statutory + opt_slippage,
                    'net_pnl': total_net_pnl,
                    'return_on_capital': total_net_pnl / INITIAL_CAP
                }
                trades.append(trade_record)
                active_position = None

        i += 1

    trades_df = pd.DataFrame(trades)
    print(f"[✓] Simulation finished. Total trades executed: {len(trades_df)}")

    # 3. Daily Mark-to-Market NAV and Capital Ledger
    print("\n[*] Constructing Daily MTM NAV and Capital Ledger...")
    trade_meta = {tr['trade_id']: tr for _, tr in trades_df.iterrows()}
    active_by_date = {}
    for _, tr in trades_df.iterrows():
        t_dates = [d for d in dates if tr['entry_date'] <= d <= tr['exit_date']]
        for td in t_dates:
            active_by_date[td] = tr

    daily_records = []
    capital_records = []

    for d in dates:
        spot = features.loc[d, 'spot']
        atm_iv = features.loc[d, 'atm_iv']
        tr = active_by_date.get(d)

        unrealized_opt = 0.0
        unrealized_fut = 0.0
        deployed_margin = 0.0
        psr_val = 0.0

        if tr is not None and d != tr['exit_date']:
            exp = tr['expiry']
            lot = tr['lot_size']

            # Option mtm
            s_key = (d, exp, tr['strike'], 'CE')
            s_data = bt.opt_lookup.get(s_key)
            curr_opt = s_data[0] if s_data else tr['opt_entry_settle']

            # Futures mtm
            if d == exp:
                curr_fut = spot
            else:
                curr_fut = fut_lookup.get((d, exp), spot)

            # Option unrealized (entry_fill - curr_settle - initial costs)
            unrealized_opt = (tr['opt_entry_fill'] - curr_opt) * lot - (tr['opt_statutory'] / 2.0)
            # Futures unrealized (curr_settle - entry_fill - initial costs)
            unrealized_fut = (curr_fut - tr['fut_entry_fill']) * lot - (tr['fut_statutory'] / 2.0)

            # Combined Margin
            deployed_margin, psr_val = calculate_dynamic_margin(spot, curr_opt, lot, atm_iv)

        past_closed = trades_df[trades_df['exit_date'] <= d]['net_pnl'].sum()
        trading_nav = INITIAL_CAP + past_closed + unrealized_opt + unrealized_fut
        eligible_cash = max(0.0, trading_nav - deployed_margin)
        daily_yield = eligible_cash * DAILY_LIQUID_RATE
        margin_util_pct = (deployed_margin / trading_nav) * 100.0 if trading_nav > 0 else 0.0
        is_shortfall = deployed_margin > trading_nav

        daily_records.append({
            'trade_date': d,
            'spot': spot,
            'atm_iv': atm_iv,
            'is_invested': (tr is not None and d != tr['exit_date']),
            'active_trade_id': tr['trade_id'] if (tr is not None and d != tr['exit_date']) else None,
            'unrealized_opt_pnl': unrealized_opt,
            'unrealized_fut_pnl': unrealized_fut,
            'unrealized_total_pnl': unrealized_opt + unrealized_fut,
            'cumulative_realized_pnl': past_closed,
            'trading_nav': trading_nav,
            'deployed_margin': deployed_margin,
            'eligible_cash': eligible_cash,
            'daily_cash_yield': daily_yield,
            'psr': psr_val,
            'margin_utilization_pct': margin_util_pct,
            'is_shortfall': is_shortfall
        })

    daily_df = pd.DataFrame(daily_records)
    daily_df['cum_cash_yield'] = daily_df['daily_cash_yield'].cumsum()
    daily_df['total_portfolio_nav'] = daily_df['trading_nav'] + daily_df['cum_cash_yield']

    # Drawdowns
    daily_df['cummax_trading'] = daily_df['trading_nav'].cummax()
    daily_df['drawdown_trading'] = (daily_df['trading_nav'] - daily_df['cummax_trading']) / daily_df['cummax_trading']

    daily_df['cummax_total'] = daily_df['total_portfolio_nav'].cummax()
    daily_df['drawdown_total'] = (daily_df['total_portfolio_nav'] - daily_df['cummax_total']) / daily_df['cummax_total']

    # 4. PnL Reconciliation Verification
    sum_trade_pnl = trades_df['net_pnl'].sum()
    nav_trading_pnl = daily_df['trading_nav'].iloc[-1] - INITIAL_CAP
    recon_diff = abs(sum_trade_pnl - nav_trading_pnl)
    print(f"\n[*] PnL Integrity Audit:")
    print(f"    - Trade Ledger Sum:  ₹{sum_trade_pnl:,.2f}")
    print(f"    - Daily NAV Trading: ₹{nav_trading_pnl:,.2f}")
    print(f"    - Discrepancy:       ₹{recon_diff:.6f}")

    if recon_diff > 0.05:
        raise ValueError(f"FATAL: Ledger and NAV discrepancy of ₹{recon_diff} exceeds tolerance!")
    print("    [✓] Zero-discrepancy reconciliation validated successfully.")

    # 5. Save Ledgers
    trades_df.to_csv(EXPERIMENT_DIR / "trade_ledger.csv", index=False)
    daily_df.to_csv(EXPERIMENT_DIR / "daily_nav.csv", index=False)
    
    capital_df = daily_df[['trade_date', 'spot', 'is_invested', 'trading_nav', 'deployed_margin', 'eligible_cash', 'daily_cash_yield', 'cum_cash_yield', 'total_portfolio_nav', 'margin_utilization_pct', 'is_shortfall']]
    capital_df.to_csv(EXPERIMENT_DIR / "capital_ledger.csv", index=False)

    # 6. Comprehensive Metrics
    start_dt = pd.to_datetime(features.index.min())
    end_dt = pd.to_datetime(features.index.max())
    calendar_years = (end_dt - start_dt).days / 365.25

    def compute_metrics(nav_col, dd_col):
        total_pnl = daily_df[nav_col].iloc[-1] - INITIAL_CAP
        cagr = (((INITIAL_CAP + total_pnl) / INITIAL_CAP) ** (1.0 / calendar_years)) - 1.0
        max_dd = abs(daily_df[dd_col].min())
        
        # Bootstrap Sharpe
        rets = daily_df[nav_col].pct_change().dropna().values
        daily_rf = RISK_FREE_RATE / 252.0
        excess = rets - daily_rf
        pt_sharpe = np.mean(excess) / np.std(rets) * np.sqrt(252) if np.std(rets) > 0 else 0.0
        
        rng = np.random.default_rng(42)
        boot_sharpes = []
        for _ in range(1000):
            sample = rng.choice(rets, size=len(rets), replace=True)
            std_s = np.std(sample)
            if std_s > 0:
                boot_sharpes.append(np.mean(sample - daily_rf) / std_s * np.sqrt(252))
        ci_low, ci_high = (np.percentile(boot_sharpes, 5.0), np.percentile(boot_sharpes, 95.0)) if boot_sharpes else (0.0, 0.0)
        
        return {
            'total_pnl': total_pnl,
            'cagr': cagr,
            'max_dd': max_dd,
            'sharpe': pt_sharpe,
            'ci_low': ci_low,
            'ci_high': ci_high
        }

    m_trading = compute_metrics('trading_nav', 'drawdown_trading')
    m_total = compute_metrics('total_portfolio_nav', 'drawdown_total')

    win_trades = trades_df[trades_df['net_pnl'] > 0]
    loss_trades = trades_df[trades_df['net_pnl'] < 0]
    win_rate = len(win_trades) / len(trades_df) * 100.0
    profit_factor = win_trades['net_pnl'].sum() / abs(loss_trades['net_pnl'].sum()) if len(loss_trades) > 0 else 99.0
    worst_trade = trades_df['net_pnl'].min()
    worst_trade_ret = trades_df['return_on_capital'].min() * 100.0

    print("\n" + "=" * 80)
    print("  EXP-FUT-BW-001 PERFORMANCE SUMMARY")
    print("=" * 80)
    print(f"  Total Trades Executed:       {len(trades_df)}")
    print(f"  Win Rate:                    {win_rate:.2f}%")
    print(f"  Profit Factor:               {profit_factor:.2f}")
    print(f"  Worst Trade Loss:            ₹{worst_trade:,.2f} ({worst_trade_ret:.2f}%)")
    print(f"  Maximum Margin Deployed:     ₹{daily_df['deployed_margin'].max():,.2f} (Peak Util: {daily_df['margin_utilization_pct'].max():.2f}%)")
    print(f"  Capital Shortfalls:          {daily_df['is_shortfall'].sum()} days")
    print(f"  Cumulative Cash Yield:       ₹{daily_df['cum_cash_yield'].iloc[-1]:,.2f}")
    print("-" * 80)
    print("  TRADING-ONLY (Without Treasury Yield Overlay):")
    print(f"    - Net PnL:                 ₹{m_trading['total_pnl']:,.2f}")
    print(f"    - Calendar CAGR:           {m_trading['cagr']*100:.2f}%")
    print(f"    - Max Daily MTM Drawdown:  {m_trading['max_dd']*100:.2f}%")
    print(f"    - Daily Sharpe (90% CI):   {m_trading['sharpe']:.2f} [{m_trading['ci_low']:.2f}, {m_trading['ci_high']:.2f}]")
    print("-" * 80)
    print("  TOTAL PORTFOLIO (With Liquid Treasury Yield Overlay):")
    print(f"    - Net PnL:                 ₹{m_total['total_pnl']:,.2f}")
    print(f"    - Calendar CAGR:           {m_total['cagr']*100:.2f}%")
    print(f"    - Max Daily MTM Drawdown:  {m_total['max_dd']*100:.2f}%")
    print(f"    - Daily Sharpe (90% CI):   {m_total['sharpe']:.2f} [{m_total['ci_low']:.2f}, {m_total['ci_high']:.2f}]")
    print("=" * 80)

    # 7. Chronological Partition Analysis
    print("\n[*] Evaluating Chronological Partitions and Walk-Forward Windows...")
    partitions = [
        ('In-Sample (Training)', '2019-02-11', '2022-12-30'),
        ('Out-of-Sample (Validation)', '2023-01-02', '2024-12-31'),
        ('Untouched Holdout', '2025-01-01', '2026-09-04'),
        ('WF Window 1 (2021)', '2021-01-01', '2021-12-31'),
        ('WF Window 2 (2022)', '2022-01-01', '2022-12-31'),
        ('WF Window 3 (2023)', '2023-01-01', '2023-12-31'),
        ('WF Window 4 (2024)', '2024-01-01', '2024-12-31'),
        ('WF Window 5 (2025-2026)', '2025-01-01', '2026-09-04')
    ]

    part_records = []
    for pname, s_dt, e_dt in partitions:
        sub_t = trades_df[(trades_df['exit_date'] >= s_dt) & (trades_df['exit_date'] <= e_dt)]
        sub_d = daily_df[(daily_df['trade_date'] >= s_dt) & (daily_df['trade_date'] <= e_dt)]
        if len(sub_t) == 0 or len(sub_d) == 0:
            continue
        
        t_pnl = sub_t['net_pnl'].sum()
        y_pnl = sub_d['daily_cash_yield'].sum()
        tot_pnl = t_pnl + y_pnl
        sub_wr = (sub_t['net_pnl'] > 0).mean() * 100.0
        
        d_dd_trading = abs((sub_d['trading_nav'] - sub_d['trading_nav'].cummax()).min() / sub_d['trading_nav'].cummax().max()) * 100.0
        d_dd_total = abs((sub_d['total_portfolio_nav'] - sub_d['total_portfolio_nav'].cummax()).min() / sub_d['total_portfolio_nav'].cummax().max()) * 100.0
        
        part_records.append({
            'Partition': pname,
            'Start Date': s_dt,
            'End Date': e_dt,
            'Trades': len(sub_t),
            'Win Rate %': sub_wr,
            'Trading Net PnL': t_pnl,
            'Cash Yield': y_pnl,
            'Total Portfolio PnL': tot_pnl,
            'Max DD Trading %': d_dd_trading,
            'Max DD Total %': d_dd_total
        })

    part_df = pd.DataFrame(part_records)
    part_df.to_csv(EXPERIMENT_DIR / "chronological_partitions.csv", index=False)
    print(part_df.to_string(index=False))

    # 8. Nonlinear Adverse Stress Testing
    print("\n[*] Conducting Nonlinear Adverse Stress Tests...")
    # Reference position for stress test: active position at end of backtest or median trade
    # Spot = 25,000, Lot = 75, Strike = 25,600 (Delta 0.25), Call Prem = 180, Fut Basis = +80, ATM IV = 0.14
    ref_spot = 25000.0
    ref_lot = 75
    ref_strike = 25600.0
    ref_dte = 21 / 365.0
    ref_iv = 0.14
    ref_rf = 0.065
    ref_call = 180.0
    ref_basis = 80.0
    ref_fut = ref_spot + ref_basis
    
    stress_scenarios = [
        {
            'Scenario': 'S1: Flash Crash (-15% Gap, +100% IV, Basis Collapse)',
            'spot_shock': -0.15, 'iv_shock': 1.00, 'basis_shift': -200.0,
            'psr_mult': 2.0, 'slip_mult': 3.0, 'available': True
        },
        {
            'Scenario': 'S2: Budget Rally (+8% Gap, -30% IV Crush, Basis Expand)',
            'spot_shock': 0.08, 'iv_shock': -0.30, 'basis_shift': +60.0,
            'psr_mult': 1.0, 'slip_mult': 2.0, 'available': True
        },
        {
            'Scenario': 'S3: Prolonged Bear Grind (-25% over 6mo, IV 28%)',
            'spot_shock': -0.25, 'iv_shock': 1.00, 'basis_shift': -50.0,
            'psr_mult': 1.8, 'slip_mult': 1.5, 'available': True
        },
        {
            'Scenario': 'S4: Hyper-Vol Sideways Churn (+/-5% whip, IV 35%)',
            'spot_shock': 0.00, 'iv_shock': 1.50, 'basis_shift': 0.0,
            'psr_mult': 2.2, 'slip_mult': 2.5, 'available': True
        },
        {
            'Scenario': 'S5: Liquidity Freeze (5x Spread, Backwardation)',
            'spot_shock': -0.05, 'iv_shock': 0.50, 'basis_shift': -150.0,
            'psr_mult': 1.5, 'slip_mult': 5.0, 'available': True
        }
    ]

    stress_results = []
    for sc in stress_scenarios:
        if not sc['available']:
            stress_results.append({
                'Scenario': sc['Scenario'], 'Status': 'INCONCLUSIVE',
                'Simulated Spot': np.nan, 'New Call Price': np.nan, 'New Fut Price': np.nan,
                'Opt PnL': np.nan, 'Fut PnL': np.nan, 'Total Stress Loss': np.nan,
                'Portfolio Impact %': np.nan, 'Expanded Margin': np.nan, 'Capital Adequacy': 'INCONCLUSIVE'
            })
            continue

        new_spot = ref_spot * (1.0 + sc['spot_shock'])
        new_iv = max(0.05, ref_iv * (1.0 + sc['iv_shock']))
        new_basis = ref_basis + sc['basis_shift']
        new_fut = new_spot + new_basis

        # Nonlinear BS Option Repricing
        d1 = (np.log(new_spot / ref_strike) + (ref_rf + 0.5 * new_iv**2) * ref_dte) / (new_iv * np.sqrt(ref_dte))
        d2 = d1 - new_iv * np.sqrt(ref_dte)
        new_call_bs = new_spot * norm.cdf(d1) - ref_strike * np.exp(-ref_rf * ref_dte) * norm.cdf(d2)
        new_call_bs = max(0.0, new_call_bs)

        # Slippage shock
        add_slip_opt = 1.0 * sc['slip_mult']
        add_slip_fut = 1.0 * sc['slip_mult']

        opt_loss = (ref_call - (new_call_bs + add_slip_opt)) * ref_lot
        fut_loss = ((new_fut - add_slip_fut) - ref_fut) * ref_lot
        tot_loss = opt_loss + fut_loss
        pct_impact = (tot_loss / INITIAL_CAP) * 100.0

        # Margin expansion
        daily_v = new_iv / np.sqrt(252.0)
        exp_psr = max(0.08, 3.5 * daily_v) * sc['psr_mult']
        exp_margin = max(0.0, (exp_psr * new_spot - new_call_bs) * ref_lot) + (0.02 * new_spot * ref_lot)
        adequacy = "ADEQUATE (NO SHORTFALL)" if exp_margin < (INITIAL_CAP + tot_loss) else "MARGIN DEFICIT"

        stress_results.append({
            'Scenario': sc['Scenario'],
            'Status': 'EVALUATED',
            'Simulated Spot': round(new_spot, 2),
            'New Call Price': round(new_call_bs, 2),
            'New Fut Price': round(new_fut, 2),
            'Opt PnL': round(opt_loss, 2),
            'Fut PnL': round(fut_loss, 2),
            'Total Stress Loss': round(tot_loss, 2),
            'Portfolio Impact %': round(pct_impact, 2),
            'Expanded Margin': round(exp_margin, 2),
            'Capital Adequacy': adequacy
        })

    stress_df = pd.DataFrame(stress_results)
    stress_df.to_csv(EXPERIMENT_DIR / "stress_matrix.csv", index=False)
    print("\nStress Test Matrix:")
    print(stress_df[['Scenario', 'Opt PnL', 'Fut PnL', 'Total Stress Loss', 'Portfolio Impact %', 'Expanded Margin', 'Capital Adequacy']].to_string(index=False))

    # 9. Cost and Comparison Reconciliation Table
    recon_table = pd.DataFrame([
        {
            'Configuration': 'Baseline (EXP-000-BASE)',
            'Architecture': 'Spot Basket + Short Call',
            'Underlying Vehicle': 'Frictionless Spot',
            'Trades': 118,
            'Total Net PnL': 719301.20,
            'Calendar CAGR %': 5.76,
            'Max Daily DD %': 6.84,
            'Daily Sharpe': 0.13,
            'Worst Trade': -75043.10,
            'Total Frictions': 23908.52,
            'Cash Yield': 0.0,
            'Total Portfolio PnL': 719301.20
        },
        {
            'Configuration': 'Optimized (EXP-064-INT5)',
            'Architecture': 'Spot Basket + Short Call',
            'Underlying Vehicle': 'Frictionless Spot',
            'Trades': 132,
            'Total Net PnL': 794842.27,
            'Calendar CAGR %': 6.22,
            'Max Daily DD %': 5.21,
            'Daily Sharpe': 0.22,
            'Worst Trade': -50374.65,
            'Total Frictions': 24046.24,
            'Cash Yield': 0.0,
            'Total Portfolio PnL': 794842.27
        },
        {
            'Configuration': 'EXP-FUT-BW-001 (Trading Only)',
            'Architecture': 'Futures Buy-Write (No Yield)',
            'Underlying Vehicle': 'FUTIDX NIFTY',
            'Trades': len(trades_df),
            'Total Net PnL': m_trading['total_pnl'],
            'Calendar CAGR %': m_trading['cagr'] * 100.0,
            'Max Daily DD %': m_trading['max_dd'] * 100.0,
            'Daily Sharpe': m_trading['sharpe'],
            'Worst Trade': worst_trade,
            'Total Frictions': trades_df['total_frictions'].sum(),
            'Cash Yield': 0.0,
            'Total Portfolio PnL': m_trading['total_pnl']
        },
        {
            'Configuration': 'EXP-FUT-BW-001 (Total Portfolio)',
            'Architecture': 'Futures Buy-Write + Liquid Yield',
            'Underlying Vehicle': 'FUTIDX NIFTY + TREPS',
            'Trades': len(trades_df),
            'Total Net PnL': m_total['total_pnl'],
            'Calendar CAGR %': m_total['cagr'] * 100.0,
            'Max Daily DD %': m_total['max_dd'] * 100.0,
            'Daily Sharpe': m_total['sharpe'],
            'Worst Trade': worst_trade,
            'Total Frictions': trades_df['total_frictions'].sum(),
            'Cash Yield': daily_df['cum_cash_yield'].iloc[-1],
            'Total Portfolio PnL': m_total['total_pnl']
        }
    ])
    recon_table.to_csv(EXPERIMENT_DIR / "cost_margin_reconciliation.csv", index=False)
    print("\nBenchmark Comparison Reconciliation Table:")
    print(recon_table[['Configuration', 'Trades', 'Total Net PnL', 'Calendar CAGR %', 'Max Daily DD %', 'Daily Sharpe', 'Cash Yield', 'Total Portfolio PnL']].to_string(index=False))

    print("\n[✓] All experiment files and ledgers successfully saved to:")
    print(f"    {EXPERIMENT_DIR}")

if __name__ == '__main__':
    run_experiment()
