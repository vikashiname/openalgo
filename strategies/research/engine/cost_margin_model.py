import numpy as np

class IndianDerivativesCostModel:
    """
    Implements verified statutory transaction costs and taxes for Indian markets:
    - Brokerage
    - STT (Pre/Post Oct 1, 2024 revision)
    - Exchange Transaction Charges
    - SEBI Turnover Charges
    - Stamp Duty
    - GST (18%)
    - Bid/Ask Slippage
    """
    def __init__(self, cost_multiplier=1.0, slippage_multiplier=1.0):
        self.cost_multiplier = cost_multiplier
        self.slippage_multiplier = slippage_multiplier
        self.brokerage_per_order = 20.0 * cost_multiplier
        self.exchange_txn_rate = 0.0003503 * cost_multiplier
        self.sebi_turnover_rate = 0.0000010 * cost_multiplier  # Rs 10 per crore
        self.stamp_duty_buy_rate = 0.00003 * cost_multiplier    # 0.003% on buy
        self.gst_rate = 0.18

    def calculate_option_costs(self, trade_date, action, price, lot_size, contracts=1, is_index=True):
        """
        Computes all statutory costs and execution slippage for an option order.
        action: 'BUY' or 'SELL'
        """
        premium_turnover = price * lot_size * contracts
        
        # STT Schedule
        # Oct 1, 2024 rate hike to 0.10% on sell premium
        if action.upper() == 'SELL':
            if str(trade_date) >= '2024-10-01':
                stt_rate = 0.0010 * self.cost_multiplier
            else:
                stt_rate = 0.000625 * self.cost_multiplier
            stt = premium_turnover * stt_rate
            stamp_duty = 0.0
        else:
            stt = 0.0
            stamp_duty = premium_turnover * self.stamp_duty_buy_rate

        exchange_fee = premium_turnover * self.exchange_txn_rate
        sebi_fee = premium_turnover * self.sebi_turnover_rate
        brokerage = self.brokerage_per_order * contracts
        
        gst = (brokerage + exchange_fee + sebi_fee) * self.gst_rate
        statutory_total = brokerage + stt + exchange_fee + sebi_fee + stamp_duty + gst

        # Realistic execution slippage model
        # Base slippage: 1.0% of premium for Index, 1.8% for Single Stock
        base_slip_pct = 0.010 if is_index else 0.018
        effective_slip_pct = base_slip_pct * self.slippage_multiplier
        min_slip_pts = (0.25 if is_index else 0.10) * self.slippage_multiplier
        slippage_points = max(price * effective_slip_pct, min_slip_pts)
        slippage_inr = slippage_points * lot_size * contracts

        return {
            'brokerage': brokerage,
            'stt': stt,
            'exchange_fee': exchange_fee,
            'sebi_fee': sebi_fee,
            'stamp_duty': stamp_duty,
            'gst': gst,
            'statutory_total': statutory_total,
            'slippage_inr': slippage_inr,
            'total_friction': statutory_total + slippage_inr,
            'effective_fill_price': price - slippage_points if action.upper() == 'SELL' else price + slippage_points
        }

    def calculate_equity_delivery_costs(self, action, price, quantity):
        """Statutory charges for cash equity / ETF delivery leg."""
        turnover = price * quantity
        brokerage = 20.0 * self.cost_multiplier
        stt = turnover * (0.0010 * self.cost_multiplier)  # 0.1% on buy & sell delivery
        exchange_fee = turnover * (0.0000297 * self.cost_multiplier)
        sebi_fee = turnover * (0.0000010 * self.cost_multiplier)
        stamp_duty = turnover * (0.00015 * self.cost_multiplier) if action.upper() == 'BUY' else 0.0
        gst = (brokerage + exchange_fee + sebi_fee) * self.gst_rate
        dp_charges = (13.50 * 1.18) if action.upper() == 'SELL' else 0.0

        statutory = brokerage + stt + exchange_fee + sebi_fee + stamp_duty + gst + dp_charges
        slippage = max(turnover * 0.0005 * self.slippage_multiplier, 0.05 * quantity)

        return statutory + slippage

def calculate_required_margin(strategy_name, underlying_price, strike, lot_size, spread_width=0.0):
    """
    Computes required capital / margin under Indian exchange rules:
    - Covered Call: Full notional equity value (S * L)
    - Cash-Secured Put: Strike * Lot (Full cash collateral)
    - Naked Put Write (SPAN+Exposure): 14% of notional
    - Defined Risk Spreads (Bull Put / Iron Condor): Max Spread Width * Lot
    - Call Calendar / Diagonal: Calendar margin relief ~ ₹45,000 for NIFTY, ₹60,000 for BANKNIFTY
    """
    notional = underlying_price * lot_size
    strat = strategy_name.lower()

    if 'covered_call' in strat:
        return notional  # 100% notional equity holding
    elif 'cash_secured_put' in strat or 'csp' in strat:
        return strike * lot_size  # 100% cash collateral
    elif 'naked_put' in strat or 'put_write' in strat:
        return max(0.14 * notional, strike * lot_size * 0.12)
    elif 'spread' in strat or 'iron_condor' in strat:
        return max(spread_width * lot_size, 35000.0)
    elif 'calendar' in strat:
        # SPAN calendar margin relief
        return 45000.0 if notional < 1500000.0 else 65000.0
    elif 'diagonal' in strat:
        return 55000.0 if notional < 1500000.0 else 75000.0
    else:
        return notional
