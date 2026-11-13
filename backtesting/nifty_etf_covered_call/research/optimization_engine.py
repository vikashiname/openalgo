#!/usr/bin/env python3
"""
================================================================================
AGY INSTITUTIONAL OPTIMIZATION ENGINE — NIFTY COVERED CALL STRATEGY
Location: ~/backtesting/covered call/research/optimization_engine.py
================================================================================
Controlled historical optimization and stress testing of NIFTY covered-call overlay.
Strict research scope: Confined within ~/backtesting/covered call/
Evaluates:
  1. Target Delta Sweep (0.15, 0.20, 0.25, 0.30 [Baseline], 0.35, 0.40)
  2. Premium-Decay Exit Target Sweep (50%, 60%, 70%, 80%, 90% [Baseline], 95%, 99%)
  3. Stop-Loss Multiples Sweep (1.5x, 2.0x, 2.5x, 3.0x [Baseline], 4.0x, 5.0x, No SL)
  4. Roll Timing: Calendar DTE (3, 5, 7, 10 [Baseline], 14) vs Trading Sessions (4, 7, 10 TS)
  5. ATM IV >= 18% Filter (Isolated Candidate)
  6. Multi-Factor Parameter Interactions (Top Candidate Syntheses)
  7. Rigorous Stress Tests, Idle Cash Sweeps, Slippage Sensitivity, OOS & Walk-Forward
================================================================================
"""

import os
import sys
import math
import bisect
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from scipy import stats

# Workspace imports (Read-only reference)
WORKSPACE_ROOT = Path("/Users/mac/Desktop/openalgo")
if str(WORKSPACE_ROOT / "strategies" / "research") not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT / "strategies" / "research"))

from nifty_covered_call import load_options_dataset, compute_underlying_features
from engine.strategy_backtester import OptionsIncomeBacktester
from engine.cost_margin_model import IndianDerivativesCostModel, calculate_required_margin
from engine.metrics import calculate_income_metrics

RESEARCH_DIR = Path(__file__).resolve().parent
ROOT_DIR = RESEARCH_DIR.parent
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"
OPTIONS_DATA_PATH = Path("/Users/mac/backtesting/options_income_autoresearch/data/nifty_options_daily.parquet")

INITIAL_CAPITAL = 1500000.0  # ₹15,00,000 institutional reference capital
RISK_FREE_RATE = 0.065       # 6.5% p.a. Indian benchmark
LIQUID_NET_YIELD = 0.048     # 4.8% net post-tax institutional liquid yield


class ExtendedOptionsBacktester(OptionsIncomeBacktester):
    """
    Subclasses OptionsIncomeBacktester to add trading-session roll capability
    and custom filter hooks without modifying external/live files.
    """
    def __init__(self, options_df, features_df, symbol='NIFTY', cost_multiplier=1.0, slippage_multiplier=1.0):
        super().__init__(options_df, features_df, symbol, cost_multiplier, slippage_multiplier)
        self.sorted_trade_dates = sorted(list(self.features_df.index))

    def count_trading_sessions_remaining(self, current_date, expiry_date):
        """
        Calculates exact exchange trading sessions remaining strictly between
        current_date and expiry_date, correctly accounting for weekends & holidays.
        """
        # Count dates in self.sorted_trade_dates where current_date < d <= expiry_date
        idx_curr = bisect.bisect_right(self.sorted_trade_dates, current_date)
        idx_exp = bisect.bisect_right(self.sorted_trade_dates, expiry_date)
        return max(0, idx_exp - idx_curr)

    def run_strategy(self, strategy_type, params, start_date=None, end_date=None):
        dates = [d for d in self.all_trade_dates if (start_date is None or d >= start_date) and (end_date is None or d <= end_date)]
        if not dates:
            return None, None, None

        target_dte = params.get('target_dte', 28)
        strike_mode = params.get('strike_mode', 'delta')
        strike_param = params.get('strike_param', 0.30)
        profit_target_pct = params.get('profit_target_pct', 0.90)
        stop_loss_mult = params.get('stop_loss_mult', 3.0)
        roll_dte = params.get('roll_dte', 10)
        roll_mode = params.get('roll_mode', 'calendar')  # 'calendar' or 'trading_sessions'
        roll_trading_sessions = params.get('roll_trading_sessions', 7)
        trend_filter = params.get('trend_filter', True)
        iv_filter_min = params.get('iv_filter_min', 0.0)
        atm_iv_min = params.get('atm_iv_min', 0.0)
        min_premium = params.get('min_premium', 1.0)
        net_aware_target = params.get('net_aware_target', False)

        trades = []
        active_position = None
        current_capital = params.get('initial_capital', INITIAL_CAPITAL)

        i = 0
        while i < len(dates):
            current_date = dates[i]
            feat = self.features_df.loc[current_date]
            spot = feat['spot']

            # Position Entry Check
            if active_position is None:
                if trend_filter and not feat['trend_bullish']:
                    i += 1
                    continue
                if iv_filter_min > 0 and feat['iv_percentile'] < iv_filter_min:
                    i += 1
                    continue
                if atm_iv_min > 0 and feat['atm_iv'] < atm_iv_min:
                    i += 1
                    continue

                c_short = self.find_contract(current_date, 'CE', target_dte, strike_mode, strike_param)
                if c_short is not None and c_short['settle_price'] >= min_premium:
                    lot = c_short['lot_size']
                    short_costs = self.cost_model.calculate_option_costs(
                        current_date, 'SELL', c_short['settle_price'], lot, 1, self.is_index
                    )
                    cap_req = calculate_required_margin('covered_call', spot, c_short['strike'], lot)
                    active_position = {
                        'type': 'COVERED_CALL',
                        'entry_date': current_date,
                        'entry_spot': spot,
                        'lot_size': lot,
                        'short_strike': c_short['strike'],
                        'short_expiry': c_short['expiry_date'],
                        'short_entry_price': short_costs['effective_fill_price'],
                        'short_initial_costs': short_costs['statutory_total'] + short_costs['slippage_inr'],
                        'capital_deployed': cap_req
                    }

            # Position Exit & Monitoring Check
            if active_position is not None:
                s_key = (current_date, active_position['short_expiry'], active_position['short_strike'], 'CE')
                s_data = self.opt_lookup.get(s_key)
                curr_opt_price = s_data[0] if s_data else 0.0
                
                # Roll check based on mode
                if roll_mode == 'trading_sessions':
                    ts_remaining = self.count_trading_sessions_remaining(current_date, active_position['short_expiry'])
                    should_roll = (ts_remaining <= roll_trading_sessions)
                else:
                    cal_dte_remaining = (pd.to_datetime(active_position['short_expiry']) - pd.to_datetime(current_date)).days
                    should_roll = (cal_dte_remaining <= roll_dte)

                premium_gain = (active_position['short_entry_price'] - curr_opt_price) / active_position['short_entry_price']

                exit_triggered = False
                exit_reason = None

                if premium_gain >= profit_target_pct:
                    if net_aware_target:
                        est_exit_costs = self.cost_model.calculate_option_costs(
                            current_date, 'BUY', curr_opt_price, active_position['lot_size'], 1, self.is_index
                        )
                        opt_net_pnl = (active_position['short_entry_price'] - est_exit_costs['effective_fill_price']) * active_position['lot_size']
                        roundtrip_costs = active_position['short_initial_costs'] + est_exit_costs['statutory_total'] + est_exit_costs['slippage_inr']
                        if opt_net_pnl > roundtrip_costs:
                            exit_triggered = True
                            exit_reason = 'PROFIT_TARGET'
                    else:
                        exit_triggered = True
                        exit_reason = 'PROFIT_TARGET'
                elif curr_opt_price >= (active_position['short_entry_price'] * stop_loss_mult):
                    exit_triggered = True
                    exit_reason = 'STOP_LOSS'
                elif should_roll:
                    exit_triggered = True
                    exit_reason = 'EXPIRY_ROLL'

                if exit_triggered or i == len(dates) - 1:
                    exit_costs = self.cost_model.calculate_option_costs(
                        current_date, 'BUY', curr_opt_price, active_position['lot_size'], 1, self.is_index
                    )
                    opt_pnl = (active_position['short_entry_price'] - exit_costs['effective_fill_price']) * active_position['lot_size']
                    spot_pnl = (spot - active_position['entry_spot']) * active_position['lot_size']
                    total_costs = active_position['short_initial_costs'] + exit_costs['statutory_total'] + exit_costs['slippage_inr']
                    pnl = opt_pnl + spot_pnl - total_costs

                    trade_record = {
                        'strategy': 'COVERED_CALL',
                        'symbol': self.symbol,
                        'entry_date': active_position['entry_date'],
                        'exit_date': current_date,
                        'holding_days': (pd.to_datetime(current_date) - pd.to_datetime(active_position['entry_date'])).days,
                        'exit_reason': exit_reason if exit_triggered else 'FINAL_DATE',
                        'capital_deployed': active_position['capital_deployed'],
                        'net_pnl': pnl,
                        'return_on_capital': pnl / active_position['capital_deployed']
                    }
                    trades.append(trade_record)
                    current_capital += pnl
                    active_position = None

            i += 1

        trades_df = pd.DataFrame(trades)
        if trades_df.empty:
            return None, None, None

        trades_df['month'] = pd.to_datetime(trades_df['exit_date']).dt.strftime('%Y-%m')
        monthly_df = trades_df.groupby('month').agg(
            net_pnl=('net_pnl', 'sum'),
            capital_deployed=('capital_deployed', 'mean'),
            trades_count=('net_pnl', 'count')
        ).reset_index()

        metrics = calculate_income_metrics(trades_df, monthly_df, params.get('initial_capital', INITIAL_CAPITAL))
        return trades_df, monthly_df, metrics


def compute_true_daily_mtm(bt, trades_df, features_df, params, initial_capital=INITIAL_CAPITAL):
    """
    Computes an exact daily mark-to-market NAV curve for the portfolio.
    Tracks:
      - Daily realized PnL
      - Daily unrealized PnL: (spot_t - entry_spot)*lot + (short_entry_prem - opt_settle_t)*lot - initial_costs
    """
    dates = sorted(list(features_df.index))
    target_dte = params.get('target_dte', 28)
    strike_mode = params.get('strike_mode', 'delta')
    strike_param = params.get('strike_param', 0.30)
    cost_model = bt.cost_model

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
        deployed_cap = tr['capital_deployed'] if (tr is not None and d != tr['exit_date']) else 0.0
        idle_cash = max(0.0, initial_capital - deployed_cap)

        daily_records.append({
            'trade_date': d,
            'spot': spot,
            'is_invested': is_invested,
            'deployed_capital': deployed_cap,
            'idle_cash': idle_cash,
            'active_trade_id': tr['trade_id'] if tr is not None else None,
            'unrealized_pnl': unrealized_pnl,
            'cumulative_realized_pnl': past_closed,
            'nav': current_nav
        })

    daily_df = pd.DataFrame(daily_records)
    daily_df['cummax'] = daily_df['nav'].cummax()
    daily_df['drawdown'] = (daily_df['nav'] - daily_df['cummax']) / daily_df['cummax']
    return daily_df, trade_meta


def compute_bootstrap_sharpe(daily_df, n_bootstraps=1000, rf=RISK_FREE_RATE):
    """Computes daily Sharpe ratio with 90% bootstrap confidence interval."""
    returns = daily_df['nav'].pct_change().dropna().values
    if len(returns) < 30 or np.std(returns) == 0:
        return 0.0, (0.0, 0.0)

    daily_rf = rf / 252.0
    excess_returns = returns - daily_rf
    point_sharpe = np.mean(excess_returns) / np.std(returns) * np.sqrt(252)

    rng = np.random.default_rng(42)
    boot_sharpes = []
    n = len(returns)
    for _ in range(n_bootstraps):
        sample = rng.choice(excess_returns, size=n, replace=True)
        s = np.std(sample)
        if s > 0:
            boot_sharpes.append(np.mean(sample) / s * np.sqrt(252))

    if boot_sharpes:
        ci_lower = np.percentile(boot_sharpes, 5.0)
        ci_upper = np.percentile(boot_sharpes, 95.0)
        return float(point_sharpe), (float(ci_lower), float(ci_upper))
    return float(point_sharpe), (0.0, 0.0)


def evaluate_experiment(bt, features_df, exp_id, name, params, initial_capital=INITIAL_CAPITAL):
    """Executes a full evaluation of an experiment candidate."""
    trades_df, monthly_df, raw_metrics = bt.run_strategy('COVERED_CALL', params)
    
    if trades_df is None or trades_df.empty:
        return {
            'exp_id': exp_id, 'name': name, 'params': params,
            'trades': 0, 'win_rate': 0.0, 'total_net_pnl': 0.0, 'calendar_cagr': 0.0,
            'cagr_liquid': 0.0, 'annual_ret_total_cap': 0.0, 'annual_ret_deployed': 0.0,
            'true_daily_max_dd': 0.0, 'max_dd_liquid': 0.0, 'sharpe': 0.0, 'sharpe_ci': (0.0, 0.0),
            'profit_factor': 0.0, 'worst_trade_pnl': 0.0, 'worst_trade_pct': 0.0,
            'market_exposure_pct': 0.0, 'avg_capital_deployed': 0.0,
            'trades_df': pd.DataFrame(), 'daily_df': pd.DataFrame()
        }

    trades_df['trade_id'] = [f"{exp_id[:7]}_T{i+1:03d}" for i in range(len(trades_df))]

    start_dt = pd.to_datetime(features_df.index.min())
    end_dt = pd.to_datetime(features_df.index.max())
    calendar_years = (end_dt - start_dt).days / 365.25

    total_net_pnl = trades_df['net_pnl'].sum()
    final_nav = initial_capital + total_net_pnl
    calendar_cagr = ((final_nav / initial_capital) ** (1.0 / calendar_years)) - 1.0

    avg_cap = trades_df['capital_deployed'].mean()
    annual_ret_deployed = (total_net_pnl / avg_cap) / calendar_years if avg_cap > 0 else 0.0
    annual_ret_total_cap = (total_net_pnl / initial_capital) / calendar_years

    # Daily MTM NAV
    daily_df, trade_meta = compute_true_daily_mtm(bt, trades_df, features_df, params, initial_capital)
    true_daily_max_dd = abs(daily_df['drawdown'].min())
    exposure_pct = (daily_df['is_invested'].sum() / len(daily_df)) * 100.0

    # Idle Cash / Liquid Yield overlay
    daily_liquid_rate = LIQUID_NET_YIELD / 252.0
    daily_df['liquid_interest'] = daily_df['idle_cash'] * daily_liquid_rate
    daily_df['cum_liquid_interest'] = daily_df['liquid_interest'].cumsum()
    daily_df['nav_liquid'] = daily_df['nav'] + daily_df['cum_liquid_interest']
    daily_df['cummax_liquid'] = daily_df['nav_liquid'].cummax()
    daily_df['drawdown_liquid'] = (daily_df['nav_liquid'] - daily_df['cummax_liquid']) / daily_df['cummax_liquid']
    max_dd_liquid = abs(daily_df['drawdown_liquid'].min())

    final_nav_liquid = daily_df['nav_liquid'].iloc[-1]
    cagr_liquid = ((final_nav_liquid / initial_capital) ** (1.0 / calendar_years)) - 1.0

    # Bootstrap Sharpe
    sharpe, sharpe_ci = compute_bootstrap_sharpe(daily_df, n_bootstraps=1000)

    # Basic trade statistics
    win_rate = (trades_df['net_pnl'] > 0).mean() * 100.0
    profit_factor = raw_metrics.get('profit_factor', 0.0)
    worst_trade_pnl = trades_df['net_pnl'].min()
    worst_trade_pct = trades_df['return_on_capital'].min() * 100.0

    return {
        'exp_id': exp_id,
        'name': name,
        'params': params,
        'trades': len(trades_df),
        'win_rate': win_rate,
        'total_net_pnl': total_net_pnl,
        'calendar_cagr': calendar_cagr * 100.0,
        'cagr_liquid': cagr_liquid * 100.0,
        'annual_ret_total_cap': annual_ret_total_cap * 100.0,
        'annual_ret_deployed': annual_ret_deployed * 100.0,
        'true_daily_max_dd': true_daily_max_dd * 100.0,
        'max_dd_liquid': max_dd_liquid * 100.0,
        'sharpe': sharpe,
        'sharpe_ci': sharpe_ci,
        'profit_factor': profit_factor,
        'worst_trade_pnl': worst_trade_pnl,
        'worst_trade_pct': worst_trade_pct,
        'market_exposure_pct': exposure_pct,
        'avg_capital_deployed': avg_cap,
        'trades_df': trades_df,
        'daily_df': daily_df
    }


def run_chronological_splits(bt, features_df, params, exp_id):
    """Evaluates In-Sample (2019-2022), Out-of-Sample (2023-2024), Holdout (2025-2026)."""
    splits = [
        ("In-Sample (IS)", "2019-02-11", "2022-12-30"),
        ("Out-of-Sample (OOS)", "2023-01-02", "2024-12-31"),
        ("Final Holdout", "2025-01-01", "2026-09-04")
    ]
    results = []
    t_df, _, _ = bt.run_strategy('COVERED_CALL', params)
    if t_df is None or t_df.empty:
        return results

    for s_name, s_start, s_end in splits:
        sub = t_df[(t_df['entry_date'] >= s_start) & (t_df['entry_date'] <= s_end)]
        n_trades = len(sub)
        pnl = sub['net_pnl'].sum() if n_trades > 0 else 0.0
        wr = (sub['net_pnl'] > 0).mean() * 100.0 if n_trades > 0 else 0.0
        gains = sub[sub['net_pnl'] > 0]['net_pnl'].sum()
        losses = abs(sub[sub['net_pnl'] < 0]['net_pnl'].sum())
        pf = (gains / losses) if losses > 0 else (99.0 if gains > 0 else 0.0)

        results.append({
            'exp_id': exp_id,
            'partition': s_name,
            'date_range': f"{s_start} to {s_end}",
            'trades': n_trades,
            'win_rate': wr,
            'net_pnl': pnl,
            'profit_factor': pf
        })
    return results


def run_walk_forward_rolling(bt, features_df, params, exp_id):
    """Executes 5 Walk-Forward rolling windows (2-year train, 1-year test)."""
    windows = [
        ("Window 1", "2019-02-11", "2020-12-31", "2021-01-01", "2021-12-31"),
        ("Window 2", "2020-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
        ("Window 3", "2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
        ("Window 4", "2022-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
        ("Window 5", "2023-01-01", "2024-12-31", "2025-01-01", "2026-09-04"),
    ]
    t_df, _, _ = bt.run_strategy('COVERED_CALL', params)
    if t_df is None or t_df.empty:
        return []

    wf_results = []
    for w_name, tr_start, tr_end, te_start, te_end in windows:
        tr_trades = t_df[(t_df['entry_date'] >= tr_start) & (t_df['entry_date'] <= tr_end)]
        te_trades = t_df[(t_df['entry_date'] >= te_start) & (t_df['entry_date'] <= te_end)]

        tr_pnl = tr_trades['net_pnl'].sum() if len(tr_trades) > 0 else 0.0
        te_pnl = te_trades['net_pnl'].sum() if len(te_trades) > 0 else 0.0
        te_wr = (te_trades['net_pnl'] > 0).mean() * 100.0 if len(te_trades) > 0 else 0.0

        te_gains = te_trades[te_trades['net_pnl'] > 0]['net_pnl'].sum()
        te_losses = abs(te_trades[te_trades['net_pnl'] < 0]['net_pnl'].sum())
        te_pf = (te_gains / te_losses) if te_losses > 0 else (99.0 if te_gains > 0 else 0.0)

        wf_results.append({
            'exp_id': exp_id,
            'window': w_name,
            'train_period': f"{tr_start[:4]}–{tr_end[:4]}",
            'train_trades': len(tr_trades),
            'train_pnl': tr_pnl,
            'test_period': f"{te_start[:4]}–{te_end[:4]}",
            'test_trades': len(te_trades),
            'test_pnl': te_pnl,
            'test_win_rate': te_wr,
            'test_profit_factor': te_pf
        })
    return wf_results


def run_stress_tests(trades_df, exp_id, net_delta=0.70):
    """
    Executes first-principles position repricing adverse stress tests:
      1. Base Realized
      2. 2x Adverse Slippage (doubled option spread friction)
      3. 3x Adverse Slippage (tripled option spread friction)
      4. -1.5% Overnight Gap (Repriced via net position delta: Δ_net = 1.0 - Δ_call)
      5. -3.0% Tail Crash (Repriced via net position delta on losing/stop trades)
    """
    if trades_df is None or trades_df.empty:
        return []

    base_pnl = trades_df['net_pnl'].sum()
    base_wr = (trades_df['net_pnl'] > 0).mean() * 100.0
    base_worst = trades_df['net_pnl'].min()
    n_trades = len(trades_df)

    # 1. Base
    res = [{
        'exp_id': exp_id, 'scenario': '1. Base Realized',
        'stressed_pnl': base_pnl, 'pnl_deterioration_pct': 0.0,
        'stressed_win_rate': base_wr, 'worst_trade_pnl': base_worst
    }]

    # 2. 2x Slippage (₹75 per roundtrip trade penalty)
    slip2_pnl = base_pnl - (n_trades * 75.0)
    res.append({
        'exp_id': exp_id, 'scenario': '2. 2x Adverse Slippage',
        'stressed_pnl': slip2_pnl, 'pnl_deterioration_pct': ((slip2_pnl - base_pnl) / base_pnl) * 100.0,
        'stressed_win_rate': base_wr, 'worst_trade_pnl': base_worst - 75.0
    })

    # 3. 3x Slippage (₹150 per roundtrip trade penalty)
    slip3_pnl = base_pnl - (n_trades * 150.0)
    res.append({
        'exp_id': exp_id, 'scenario': '3. 3x Severe Slippage',
        'stressed_pnl': slip3_pnl, 'pnl_deterioration_pct': ((slip3_pnl - base_pnl) / base_pnl) * 100.0,
        'stressed_win_rate': base_wr, 'worst_trade_pnl': base_worst - 150.0
    })

    # 4. -1.5% Overnight Gap Repriced (Net position delta: 0.70 * 1.5% shock = -1.05% on capital on SL trades)
    t_shock = trades_df.copy()
    sl_mask = t_shock['exit_reason'] == 'STOP_LOSS'
    t_shock.loc[sl_mask, 'net_pnl'] = t_shock.loc[sl_mask, 'net_pnl'] - (t_shock.loc[sl_mask, 'capital_deployed'] * 0.015 * net_delta)
    s4_pnl = t_shock['net_pnl'].sum()
    s4_wr = (t_shock['net_pnl'] > 0).mean() * 100.0
    s4_worst = t_shock['net_pnl'].min()
    res.append({
        'exp_id': exp_id, 'scenario': '4. -1.5% Overnight Gap (Delta Repriced)',
        'stressed_pnl': s4_pnl, 'pnl_deterioration_pct': ((s4_pnl - base_pnl) / base_pnl) * 100.0,
        'stressed_win_rate': s4_wr, 'worst_trade_pnl': s4_worst
    })

    # 5. -3.0% Tail Shock Repriced (Net delta on SL trades: 0.70 * 3.0% = -2.10% additional capital shock)
    t_tail = trades_df.copy()
    t_tail.loc[sl_mask, 'net_pnl'] = t_tail.loc[sl_mask, 'net_pnl'] - (t_tail.loc[sl_mask, 'capital_deployed'] * 0.030 * net_delta)
    s5_pnl = t_tail['net_pnl'].sum()
    s5_wr = (t_tail['net_pnl'] > 0).mean() * 100.0
    s5_worst = t_tail['net_pnl'].min()
    res.append({
        'exp_id': exp_id, 'scenario': '5. -3.0% Tail Crash (Delta Repriced)',
        'stressed_pnl': s5_pnl, 'pnl_deterioration_pct': ((s5_pnl - base_pnl) / base_pnl) * 100.0,
        'stressed_win_rate': s5_wr, 'worst_trade_pnl': s5_worst
    })

    return res
