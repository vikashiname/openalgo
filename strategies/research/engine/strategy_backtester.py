import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from .cost_margin_model import IndianDerivativesCostModel, calculate_required_margin
from .metrics import calculate_income_metrics
from .options_math import bs_price_and_greeks

class OptionsIncomeBacktester:
    def __init__(self, options_df, features_df, symbol='NIFTY', cost_multiplier=1.0, slippage_multiplier=1.0):
        self.symbol = symbol
        self.options_df = options_df
        self.features_df = features_df
        self.cost_model = IndianDerivativesCostModel(cost_multiplier, slippage_multiplier)
        self.is_index = symbol in ['NIFTY', 'BANKNIFTY']
        
        # Build available contracts index by (trade_date, option_type)
        print(f"[*] Indexing options contracts for {symbol} ({len(options_df):,} rows)...")
        self.contracts_by_date = {}
        for (t_dt, opt_typ), grp in options_df.groupby(['trade_date', 'option_type']):
            sub = grp[['expiry_date', 'strike', 'settle_price', 'volume', 'open_interest', 'lot_size', 'underlying_price']].copy()
            sub['dte'] = (pd.to_datetime(sub['expiry_date']) - pd.to_datetime(t_dt)).dt.days
            self.contracts_by_date[(t_dt, opt_typ)] = sub

        # Memory-efficient lazy lookup for settle prices (builds cache on demand, zero memory overhead)
        class _LazyOptionsLookup:
            def __init__(self, contracts_by_date):
                self._cbd = contracts_by_date
                self._cache = {}
            def get(self, key, default=None):
                if key in self._cache:
                    return self._cache[key]
                t_dt, exp, strk, opt_typ = key
                df_sub = self._cbd.get((t_dt, opt_typ))
                if df_sub is not None:
                    m = df_sub[(df_sub['expiry_date'] == exp) & (df_sub['strike'] == strk)]
                    if not m.empty:
                        res = (m['settle_price'].iloc[0], 0, 0, 0, 0)
                        self._cache[key] = res
                        return res
                return default

        self.opt_lookup = _LazyOptionsLookup(self.contracts_by_date)
        self.all_trade_dates = sorted(list(features_df.index))
        print(f"[✓] Backtester ready for {symbol}. Total dates: {len(self.all_trade_dates)}")

    def find_contract(self, trade_date, option_type, target_dte, strike_mode='moneyness', strike_param=0.02, dte_tolerance=10):
        """
        Finds the best contract matching target DTE and strike criteria.
        strike_mode: 
          - 'moneyness': strike_param is OTM pct (e.g. 0.02 = 2% OTM)
          - 'delta': strike_param is target delta (e.g. 0.25)
          - 'deep_itm': strike_param is ITM pct (e.g. 0.05 = 5% ITM for diagonal long leg)
        """
        key = (trade_date, option_type)
        if key not in self.contracts_by_date:
            return None

        contracts = self.contracts_by_date[key]
        # Filter DTE range
        valid_dte = contracts[(contracts['dte'] >= max(1, target_dte - dte_tolerance)) & 
                              (contracts['dte'] <= target_dte + dte_tolerance) &
                              (contracts['settle_price'] > 0.5)]
        if valid_dte.empty:
            return None

        # Pick the expiry closest to target_dte
        best_dte = (valid_dte['dte'] - target_dte).abs().min()
        exp_contracts = valid_dte[(valid_dte['dte'] - target_dte).abs() == best_dte].copy()
        if exp_contracts.empty:
            return None

        spot = exp_contracts['underlying_price'].iloc[0]
        if pd.isna(spot) or spot <= 0:
            spot = self.features_df.loc[trade_date, 'spot']

        if strike_mode == 'moneyness':
            if option_type == 'CE':
                target_strike = spot * (1.0 + strike_param)
            else:
                target_strike = spot * (1.0 - strike_param)
            # Find closest strike
            best_idx = (exp_contracts['strike'] - target_strike).abs().idxmin()
            return exp_contracts.loc[best_idx]

        elif strike_mode == 'delta':
            # Compute approx delta for each strike
            t_years = exp_contracts['dte'].iloc[0] / 365.0
            r = 0.065
            sigma = self.features_df.loc[trade_date, 'atm_iv'] if trade_date in self.features_df.index else 0.16
            
            # Vectorized approx BS delta
            k_vals = exp_contracts['strike'].values
            d1 = (np.log(spot / k_vals) + (r + 0.5 * sigma ** 2) * t_years) / (sigma * np.sqrt(t_years))
            from scipy.stats import norm
            if option_type == 'CE':
                deltas = norm.cdf(d1)
                diff = np.abs(deltas - strike_param)
            else:
                deltas = norm.cdf(d1) - 1.0
                diff = np.abs(np.abs(deltas) - strike_param)
            best_pos = np.argmin(diff)
            return exp_contracts.iloc[best_pos]

        elif strike_mode == 'deep_itm':
            # For diagonal long leg: deep ITM Call (e.g. 5% to 8% ITM)
            target_strike = spot * (1.0 - strike_param)
            best_idx = (exp_contracts['strike'] - target_strike).abs().idxmin()
            return exp_contracts.loc[best_idx]

        return None

    def run_strategy(self, strategy_type, params, start_date=None, end_date=None):
        """
        Executes a strategy simulation given a parameter dict.
        Supported strategy_types:
        - 'COVERED_CALL'
        - 'CALL_CALENDAR'
        - 'CALL_DIAGONAL'
        - 'CASH_SECURED_PUT'
        - 'BULL_PUT_SPREAD'
        - 'BUY_AND_HOLD'
        """
        dates = [d for d in self.all_trade_dates if (start_date is None or d >= start_date) and (end_date is None or d <= end_date)]
        if not dates:
            return None, None, None

        target_dte = params.get('target_dte', 28)
        strike_mode = params.get('strike_mode', 'moneyness')
        strike_param = params.get('strike_param', 0.02)
        profit_target_pct = params.get('profit_target_pct', 0.60)  # exit when 60% premium captured
        stop_loss_mult = params.get('stop_loss_mult', 2.5)          # exit if loss > 2.5x credit
        roll_dte = params.get('roll_dte', 1)                        # roll if <= 1 DTE
        trend_filter = params.get('trend_filter', False)            # only trade with trend
        iv_filter_min = params.get('iv_filter_min', 0.0)            # IV percentile filter
        min_premium = params.get('min_premium', 25.0)               # Minimum option premium floor
        net_aware_target = params.get('net_aware_target', True)     # Ensure profit target covers all frictions

        trades = []
        daily_records = []
        
        active_position = None
        # Track portfolio equity
        initial_capital = params.get('initial_capital', 1500000.0)
        current_capital = initial_capital

        i = 0
        while i < len(dates):
            current_date = dates[i]
            feat = self.features_df.loc[current_date]
            spot = feat['spot']

            # If no active position, check entry conditions
            if active_position is None:
                # Check filters
                if trend_filter:
                    if strategy_type in ['COVERED_CALL', 'CASH_SECURED_PUT', 'BULL_PUT_SPREAD', 'CALL_DIAGONAL']:
                        if not feat['trend_bullish']:
                            i += 1
                            continue
                if iv_filter_min > 0:
                    if feat['iv_percentile'] < iv_filter_min:
                        i += 1
                        continue

                # Initiate Position
                if strategy_type == 'BUY_AND_HOLD':
                    # Single continuous hold
                    lot_size = self.options_df[self.options_df['trade_date'] == current_date]['lot_size'].iloc[0]
                    active_position = {
                        'type': 'BUY_AND_HOLD',
                        'entry_date': current_date,
                        'entry_spot': spot,
                        'lot_size': lot_size,
                        'capital_deployed': spot * lot_size
                    }

                elif strategy_type == 'COVERED_CALL':
                    # Short OTM Call + Long Underlying Notional
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

                elif strategy_type == 'CASH_SECURED_PUT':
                    # Short OTM Put backed by cash collateral
                    c_short = self.find_contract(current_date, 'PE', target_dte, strike_mode, strike_param)
                    if c_short is not None and c_short['settle_price'] > 1.0:
                        lot = c_short['lot_size']
                        short_costs = self.cost_model.calculate_option_costs(
                            current_date, 'SELL', c_short['settle_price'], lot, 1, self.is_index
                        )
                        cap_req = calculate_required_margin('cash_secured_put', spot, c_short['strike'], lot)
                        active_position = {
                            'type': 'CASH_SECURED_PUT',
                            'entry_date': current_date,
                            'entry_spot': spot,
                            'lot_size': lot,
                            'short_strike': c_short['strike'],
                            'short_expiry': c_short['expiry_date'],
                            'short_entry_price': short_costs['effective_fill_price'],
                            'short_initial_costs': short_costs['statutory_total'] + short_costs['slippage_inr'],
                            'capital_deployed': cap_req
                        }

                elif strategy_type == 'CALL_CALENDAR':
                    # Near OTM Call (e.g. 10-18 DTE) + Next Month Call at same strike (e.g. 35-50 DTE)
                    c_short = self.find_contract(current_date, 'CE', target_dte, strike_mode, strike_param)
                    if c_short is not None:
                        # Find matching long contract at next expiry
                        long_dte_target = target_dte + params.get('calendar_gap_dte', 25)
                        key = (current_date, 'CE')
                        if key in self.contracts_by_date:
                            contracts = self.contracts_by_date[key]
                            match_long = contracts[(contracts['strike'] == c_short['strike']) & 
                                                   (contracts['dte'] >= long_dte_target - 12) & 
                                                   (contracts['dte'] <= long_dte_target + 15)]
                            if not match_long.empty:
                                c_long = match_long.iloc[0]
                                lot = c_short['lot_size']
                                s_costs = self.cost_model.calculate_option_costs(current_date, 'SELL', c_short['settle_price'], lot, 1, self.is_index)
                                l_costs = self.cost_model.calculate_option_costs(current_date, 'BUY', c_long['settle_price'], lot, 1, self.is_index)
                                cap_req = calculate_required_margin('calendar', spot, c_short['strike'], lot)
                                active_position = {
                                    'type': 'CALL_CALENDAR',
                                    'entry_date': current_date,
                                    'entry_spot': spot,
                                    'lot_size': lot,
                                    'strike': c_short['strike'],
                                    'short_expiry': c_short['expiry_date'],
                                    'long_expiry': c_long['expiry_date'],
                                    'short_entry_price': s_costs['effective_fill_price'],
                                    'long_entry_price': l_costs['effective_fill_price'],
                                    'initial_costs': s_costs['total_friction'] + l_costs['total_friction'],
                                    'capital_deployed': cap_req
                                }

                elif strategy_type == 'CALL_DIAGONAL':
                    # Long deeper DTE ITM Call + Short near DTE OTM Call
                    c_short = self.find_contract(current_date, 'CE', target_dte, strike_mode, strike_param)
                    if c_short is not None:
                        long_dte_target = target_dte + params.get('diagonal_long_dte', 45)
                        c_long = self.find_contract(current_date, 'CE', long_dte_target, 'deep_itm', params.get('itm_param', 0.04))
                        if c_long is not None and c_long['strike'] < c_short['strike']:
                            lot = c_short['lot_size']
                            s_costs = self.cost_model.calculate_option_costs(current_date, 'SELL', c_short['settle_price'], lot, 1, self.is_index)
                            l_costs = self.cost_model.calculate_option_costs(current_date, 'BUY', c_long['settle_price'], lot, 1, self.is_index)
                            cap_req = calculate_required_margin('diagonal', spot, c_short['strike'], lot)
                            active_position = {
                                'type': 'CALL_DIAGONAL',
                                'entry_date': current_date,
                                'entry_spot': spot,
                                'lot_size': lot,
                                'short_strike': c_short['strike'],
                                'short_expiry': c_short['expiry_date'],
                                'long_strike': c_long['strike'],
                                'long_expiry': c_long['expiry_date'],
                                'short_entry_price': s_costs['effective_fill_price'],
                                'long_entry_price': l_costs['effective_fill_price'],
                                'initial_costs': s_costs['total_friction'] + l_costs['total_friction'],
                                'capital_deployed': cap_req
                            }

                elif strategy_type == 'BULL_PUT_SPREAD':
                    # Short OTM Put + Long further OTM Put (protective wing)
                    c_short = self.find_contract(current_date, 'PE', target_dte, strike_mode, strike_param)
                    if c_short is not None:
                        wing_width = params.get('wing_width', 300.0 if self.is_index else (spot * 0.03))
                        long_strike_target = c_short['strike'] - wing_width
                        key = (current_date, 'PE')
                        if key in self.contracts_by_date:
                            contracts = self.contracts_by_date[key]
                            match_wing = contracts[(contracts['expiry_date'] == c_short['expiry_date']) & 
                                                   (contracts['strike'] <= long_strike_target)]
                            if not match_wing.empty:
                                c_long = match_wing.sort_values('strike', ascending=False).iloc[0]
                                lot = c_short['lot_size']
                                s_costs = self.cost_model.calculate_option_costs(current_date, 'SELL', c_short['settle_price'], lot, 1, self.is_index)
                                l_costs = self.cost_model.calculate_option_costs(current_date, 'BUY', c_long['settle_price'], lot, 1, self.is_index)
                                cap_req = calculate_required_margin('spread', spot, c_short['strike'], lot, spread_width=(c_short['strike'] - c_long['strike']))
                                active_position = {
                                    'type': 'BULL_PUT_SPREAD',
                                    'entry_date': current_date,
                                    'entry_spot': spot,
                                    'lot_size': lot,
                                    'short_strike': c_short['strike'],
                                    'long_strike': c_long['strike'],
                                    'expiry_date': c_short['expiry_date'],
                                    'short_entry_price': s_costs['effective_fill_price'],
                                    'long_entry_price': l_costs['effective_fill_price'],
                                    'initial_costs': s_costs['total_friction'] + l_costs['total_friction'],
                                    'capital_deployed': cap_req
                                }

            # If position is active, monitor daily MTM and check exit/roll conditions
            if active_position is not None:
                pos_type = active_position['type']
                exit_triggered = False
                exit_reason = None
                pnl = 0.0

                if pos_type == 'BUY_AND_HOLD':
                    if i == len(dates) - 1:
                        # Close on final date
                        pnl = (spot - active_position['entry_spot']) * active_position['lot_size']
                        exit_triggered = True
                        exit_reason = 'FINAL_DATE'

                elif pos_type == 'COVERED_CALL':
                    # Look up current short call settle price
                    s_key = (current_date, active_position['short_expiry'], active_position['short_strike'], 'CE')
                    s_data = self.opt_lookup.get(s_key)
                    curr_opt_price = s_data[0] if s_data else 0.0
                    dte_remaining = (pd.to_datetime(active_position['short_expiry']) - pd.to_datetime(current_date)).days

                    # Check profit target on short call (e.g. 60% decay)
                    premium_gain = (active_position['short_entry_price'] - curr_opt_price) / active_position['short_entry_price']
                    
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
                    elif dte_remaining <= roll_dte:
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

                elif pos_type == 'CASH_SECURED_PUT':
                    s_key = (current_date, active_position['short_expiry'], active_position['short_strike'], 'PE')
                    s_data = self.opt_lookup.get(s_key)
                    curr_opt_price = s_data[0] if s_data else 0.0
                    dte_remaining = (pd.to_datetime(active_position['short_expiry']) - pd.to_datetime(current_date)).days

                    premium_gain = (active_position['short_entry_price'] - curr_opt_price) / active_position['short_entry_price']
                    if premium_gain >= profit_target_pct:
                        exit_triggered = True
                        exit_reason = 'PROFIT_TARGET'
                    elif curr_opt_price >= (active_position['short_entry_price'] * stop_loss_mult):
                        exit_triggered = True
                        exit_reason = 'STOP_LOSS'
                    elif dte_remaining <= roll_dte:
                        exit_triggered = True
                        exit_reason = 'EXPIRY_ROLL'

                    if exit_triggered or i == len(dates) - 1:
                        exit_costs = self.cost_model.calculate_option_costs(
                            current_date, 'BUY', curr_opt_price, active_position['lot_size'], 1, self.is_index
                        )
                        opt_pnl = (active_position['short_entry_price'] - exit_costs['effective_fill_price']) * active_position['lot_size']
                        total_costs = active_position['short_initial_costs'] + exit_costs['statutory_total'] + exit_costs['slippage_inr']
                        pnl = opt_pnl - total_costs

                elif pos_type == 'CALL_CALENDAR':
                    s_key = (current_date, active_position['short_expiry'], active_position['strike'], 'CE')
                    l_key = (current_date, active_position['long_expiry'], active_position['strike'], 'CE')
                    s_data = self.opt_lookup.get(s_key)
                    l_data = self.opt_lookup.get(l_key)
                    
                    curr_s_price = s_data[0] if s_data else 0.0
                    curr_l_price = l_data[0] if l_data else active_position['long_entry_price'] * 0.95
                    dte_remaining = (pd.to_datetime(active_position['short_expiry']) - pd.to_datetime(current_date)).days

                    short_gain = (active_position['short_entry_price'] - curr_s_price) / active_position['short_entry_price']
                    if short_gain >= profit_target_pct:
                        exit_triggered = True
                        exit_reason = 'PROFIT_TARGET'
                    elif dte_remaining <= roll_dte:
                        exit_triggered = True
                        exit_reason = 'EXPIRY_ROLL'

                    if exit_triggered or i == len(dates) - 1:
                        s_exit_costs = self.cost_model.calculate_option_costs(current_date, 'BUY', curr_s_price, active_position['lot_size'], 1, self.is_index)
                        l_exit_costs = self.cost_model.calculate_option_costs(current_date, 'SELL', curr_l_price, active_position['lot_size'], 1, self.is_index)
                        s_pnl = (active_position['short_entry_price'] - s_exit_costs['effective_fill_price']) * active_position['lot_size']
                        l_pnl = (l_exit_costs['effective_fill_price'] - active_position['long_entry_price']) * active_position['lot_size']
                        total_costs = active_position['initial_costs'] + s_exit_costs['total_friction'] + l_exit_costs['total_friction']
                        pnl = s_pnl + l_pnl - total_costs

                elif pos_type == 'CALL_DIAGONAL':
                    s_key = (current_date, active_position['short_expiry'], active_position['short_strike'], 'CE')
                    l_key = (current_date, active_position['long_expiry'], active_position['long_strike'], 'CE')
                    s_data = self.opt_lookup.get(s_key)
                    l_data = self.opt_lookup.get(l_key)
                    
                    curr_s_price = s_data[0] if s_data else 0.0
                    curr_l_price = l_data[0] if l_data else active_position['long_entry_price'] * 0.95
                    dte_remaining = (pd.to_datetime(active_position['short_expiry']) - pd.to_datetime(current_date)).days

                    short_gain = (active_position['short_entry_price'] - curr_s_price) / active_position['short_entry_price']
                    if short_gain >= profit_target_pct:
                        exit_triggered = True
                        exit_reason = 'PROFIT_TARGET'
                    elif dte_remaining <= roll_dte:
                        exit_triggered = True
                        exit_reason = 'EXPIRY_ROLL'

                    if exit_triggered or i == len(dates) - 1:
                        s_exit_costs = self.cost_model.calculate_option_costs(current_date, 'BUY', curr_s_price, active_position['lot_size'], 1, self.is_index)
                        l_exit_costs = self.cost_model.calculate_option_costs(current_date, 'SELL', curr_l_price, active_position['lot_size'], 1, self.is_index)
                        s_pnl = (active_position['short_entry_price'] - s_exit_costs['effective_fill_price']) * active_position['lot_size']
                        l_pnl = (l_exit_costs['effective_fill_price'] - active_position['long_entry_price']) * active_position['lot_size']
                        total_costs = active_position['initial_costs'] + s_exit_costs['total_friction'] + l_exit_costs['total_friction']
                        pnl = s_pnl + l_pnl - total_costs

                elif pos_type == 'BULL_PUT_SPREAD':
                    s_key = (current_date, active_position['expiry_date'], active_position['short_strike'], 'PE')
                    l_key = (current_date, active_position['expiry_date'], active_position['long_strike'], 'PE')
                    s_data = self.opt_lookup.get(s_key)
                    l_data = self.opt_lookup.get(l_key)

                    curr_s_price = s_data[0] if s_data else 0.0
                    curr_l_price = l_data[0] if l_data else 0.0
                    dte_remaining = (pd.to_datetime(active_position['expiry_date']) - pd.to_datetime(current_date)).days

                    net_initial_credit = active_position['short_entry_price'] - active_position['long_entry_price']
                    curr_spread_cost = curr_s_price - curr_l_price
                    credit_captured = (net_initial_credit - curr_spread_cost) / max(0.1, net_initial_credit)

                    if credit_captured >= profit_target_pct:
                        exit_triggered = True
                        exit_reason = 'PROFIT_TARGET'
                    elif curr_spread_cost >= (net_initial_credit * stop_loss_mult):
                        exit_triggered = True
                        exit_reason = 'STOP_LOSS'
                    elif dte_remaining <= roll_dte:
                        exit_triggered = True
                        exit_reason = 'EXPIRY_ROLL'

                    if exit_triggered or i == len(dates) - 1:
                        s_exit_costs = self.cost_model.calculate_option_costs(current_date, 'BUY', curr_s_price, active_position['lot_size'], 1, self.is_index)
                        l_exit_costs = self.cost_model.calculate_option_costs(current_date, 'SELL', curr_l_price, active_position['lot_size'], 1, self.is_index)
                        s_pnl = (active_position['short_entry_price'] - s_exit_costs['effective_fill_price']) * active_position['lot_size']
                        l_pnl = (l_exit_costs['effective_fill_price'] - active_position['long_entry_price']) * active_position['lot_size']
                        total_costs = active_position['initial_costs'] + s_exit_costs['total_friction'] + l_exit_costs['total_friction']
                        pnl = s_pnl + l_pnl - total_costs

                if exit_triggered:
                    trade_record = {
                        'strategy': strategy_type,
                        'symbol': self.symbol,
                        'entry_date': active_position['entry_date'],
                        'exit_date': current_date,
                        'holding_days': (pd.to_datetime(current_date) - pd.to_datetime(active_position['entry_date'])).days,
                        'exit_reason': exit_reason,
                        'capital_deployed': active_position['capital_deployed'],
                        'net_pnl': pnl,
                        'return_on_capital': pnl / active_position['capital_deployed']
                    }
                    trades.append(trade_record)
                    current_capital += pnl
                    active_position = None  # Ready for next cycle

            i += 1

        trades_df = pd.DataFrame(trades)
        if trades_df.empty:
            return None, None, None

        # Build monthly P&L and rent summary
        trades_df['month'] = pd.to_datetime(trades_df['exit_date']).dt.strftime('%Y-%m')
        monthly_df = trades_df.groupby('month').agg(
            net_pnl=('net_pnl', 'sum'),
            capital_deployed=('capital_deployed', 'mean'),
            trades_count=('net_pnl', 'count')
        ).reset_index()

        metrics = calculate_income_metrics(trades_df, monthly_df, initial_capital)
        return trades_df, monthly_df, metrics
