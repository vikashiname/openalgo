#!/usr/bin/env python3
"""
Baseline Reproduction Script for NIFTY Covered Call Optimization
Location: ~/backtesting/covered call/research/reproduce_baseline.py

Reproduces the frozen mechanical baseline:
- Short-call target delta: 0.30
- Premium-decay exit target: 90% (0.90)
- Stop loss: 3.0x entry premium
- Roll threshold: 10 DTE
- Target DTE: 28
- Trend filter: True (100 EMA)
- Initial capital: ₹15,00,000
- Data: /Users/mac/backtesting/options_income_autoresearch/data/nifty_options_daily.parquet
"""

import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure research modules are accessible
WORKSPACE_ROOT = Path("/Users/mac/Desktop/openalgo")
if str(WORKSPACE_ROOT / "strategies" / "research") not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT / "strategies" / "research"))

from nifty_covered_call import load_options_dataset, compute_underlying_features
from engine.strategy_backtester import OptionsIncomeBacktester
from engine.cost_margin_model import IndianDerivativesCostModel

OPTIONS_DATA_PATH = Path("/Users/mac/backtesting/options_income_autoresearch/data/nifty_options_daily.parquet")

def compute_daily_mtm(bt, trades_df, features_df, params, initial_capital=1500000.0):
    dates = sorted(list(features_df.index))
    target_dte = params.get('target_dte', 28)
    strike_mode = params.get('strike_mode', 'delta')
    strike_param = params.get('strike_param', 0.30)
    cost_model = IndianDerivativesCostModel()
    
    trade_meta = {}
    for idx, tr in trades_df.iterrows():
        c_short = bt.find_contract(tr['entry_date'], 'CE', target_dte, strike_mode, strike_param)
        if c_short is not None:
            s_costs = cost_model.calculate_option_costs(
                tr['entry_date'], 'SELL', c_short['settle_price'], c_short['lot_size'], 1, True
            )
            entry_spot = features_df.loc[tr['entry_date'], 'spot']
            trade_meta[tr['trade_id']] = {
                'strike': c_short['strike'],
                'expiry': c_short['expiry_date'],
                'lot_size': c_short['lot_size'],
                'entry_spot': entry_spot,
                'short_entry_price': s_costs['effective_fill_price'],
                'initial_costs': s_costs['statutory_total'] + s_costs['slippage_inr']
            }
        else:
            trade_meta[tr['trade_id']] = None

    active_by_date = {}
    for _, tr in trades_df.iterrows():
        t_dates = [d for d in dates if tr['entry_date'] <= d <= tr['exit_date']]
        for td in t_dates:
            active_by_date[td] = tr

    daily_records = []
    for d in dates:
        spot = features_df.loc[d, 'spot']
        tr = active_by_date.get(d)
        unrealized_pnl = 0.0
        
        if tr is not None:
            meta = trade_meta.get(tr['trade_id'])
            if d == tr['exit_date']:
                unrealized_pnl = 0.0
            elif meta is not None:
                s_key = (d, meta['expiry'], meta['strike'], 'CE')
                s_data = bt.opt_lookup.get(s_key)
                curr_opt_price = s_data[0] if s_data else meta['short_entry_price']
                
                spot_mtm = (spot - meta['entry_spot']) * meta['lot_size']
                opt_mtm = (meta['short_entry_price'] - curr_opt_price) * meta['lot_size']
                unrealized_pnl = spot_mtm + opt_mtm - meta['initial_costs']

        past_closed = trades_df[trades_df['exit_date'] <= d]['net_pnl'].sum()
        current_nav = initial_capital + past_closed + unrealized_pnl
        is_invested = (tr is not None and d != tr['exit_date'])
        
        daily_records.append({
            'trade_date': d,
            'spot': spot,
            'is_invested': is_invested,
            'active_trade_id': tr['trade_id'] if tr is not None else None,
            'unrealized_pnl': unrealized_pnl,
            'cumulative_realized_pnl': past_closed,
            'nav': current_nav
        })
        
    daily_df = pd.DataFrame(daily_records)
    daily_df['cummax'] = daily_df['nav'].cummax()
    daily_df['drawdown'] = (daily_df['nav'] - daily_df['cummax']) / daily_df['cummax']
    return daily_df, trade_meta

def main():
    print("=" * 80)
    print("REPRODUCING FROZEN MECHANICAL BASELINE")
    print("=" * 80)
    
    df = load_options_dataset(OPTIONS_DATA_PATH)
    features = compute_underlying_features(df)
    features['ema_100'] = features['spot'].ewm(span=100, adjust=False).mean()
    features['trend_bullish'] = features['spot'] > features['ema_100']
    
    bt = OptionsIncomeBacktester(df, features, symbol='NIFTY')
    
    params_base = {
        'strike_mode': 'delta',
        'strike_param': 0.30,
        'profit_target_pct': 0.90,
        'stop_loss_mult': 3.0,
        'roll_dte': 10,
        'trend_filter': True,
        'target_dte': 28,
        'iv_filter_min': 0.0,
        'min_premium': 1.0,
        'net_aware_target': False
    }
    
    trades_df, monthly_df, raw_metrics = bt.run_strategy('COVERED_CALL', params_base)
    trades_df['trade_id'] = [f"BASE_T{i+1:03d}" for i in range(len(trades_df))]
    
    start_dt = pd.to_datetime(features.index.min())
    end_dt = pd.to_datetime(features.index.max())
    calendar_years = (end_dt - start_dt).days / 365.25
    
    total_net_pnl = trades_df['net_pnl'].sum()
    initial_capital = 1500000.0
    final_nav = initial_capital + total_net_pnl
    calendar_cagr = ((final_nav / initial_capital) ** (1.0 / calendar_years)) - 1.0
    avg_cap = trades_df['capital_deployed'].mean()
    true_calendar_yield = (total_net_pnl / calendar_years) / avg_cap if avg_cap > 0 else 0.0
    
    daily_df, trade_meta = compute_daily_mtm(bt, trades_df, features, params_base, initial_capital)
    true_daily_max_dd = abs(daily_df['drawdown'].min())
    exposure_pct = (daily_df['is_invested'].sum() / len(daily_df)) * 100.0
    win_rate = (trades_df['net_pnl'] > 0).mean() * 100.0
    profit_factor = raw_metrics.get('profit_factor', 0.0)
    worst_trade_pnl = trades_df['net_pnl'].min()
    worst_trade_pct = trades_df['return_on_capital'].min() * 100.0
    
    print("\n--- BASELINE METRICS REPRODUCED ---")
    print(f"Data Date Range: {features.index.min()} to {features.index.max()} ({len(features)} trading days, {calendar_years:.2f} cal years)")
    print(f"Total Trades: {len(trades_df)}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Total Net PnL: ₹{total_net_pnl:,.2f}")
    print(f"Calendar CAGR: {calendar_cagr*100:.2f}%")
    print(f"True Calendar Yield: {true_calendar_yield*100:.2f}%")
    print(f"Reported Rent Yield: {raw_metrics.get('annual_rent_yield', 0.0)*100:.2f}%")
    print(f"Reported Sharpe: {raw_metrics.get('sharpe', 0.0):.2f}")
    print(f"Reported Max Drawdown: {raw_metrics.get('max_drawdown', 0.0)*100:.2f}%")
    print(f"True Daily MTM Max Drawdown: {true_daily_max_dd*100:.2f}%")
    print(f"Profit Factor: {profit_factor:.2f}")
    print(f"Market Exposure: {exposure_pct:.2f}%")
    print(f"Worst Trade PnL: ₹{worst_trade_pnl:,.2f} ({worst_trade_pct:.2f}%)")
    print("=" * 80)

if __name__ == "__main__":
    main()
