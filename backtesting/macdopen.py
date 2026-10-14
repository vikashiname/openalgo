"""
OpenAlgo MACD Strategy Backtest with yfinance
---------------------------------------------
- Symbol: RELIANCE (RELIANCE.NS), TCS (TCS.NS)
- Timeframe: Daily ('1d')
- Data Source: yfinance (Yahoo Finance API)
- Indicator: MACD (8, 21, 5)
- Execution: Signal at candle close, entry at next candle Open (No lookahead bias)
- Framework: Modular Research-Grade Backtesting Engine (Phases 1 - 7)
"""

try:
    from openalgo import api
    client_available = True
except ImportError:
    client_available = False
    api = None

import sys
import time
import os
import builtins
import base64
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Optional, Any
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib
matplotlib.use('Agg')  # Headless backend for report generation
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import webbrowser

# Add project root to sys.path for modular backtesting package imports
_curr = os.path.abspath(os.path.dirname(__file__))
for _ in range(3):
    if os.path.exists(os.path.join(_curr, "backtesting")):
        if _curr not in sys.path:
            sys.path.insert(0, _curr)
        break
    _curr = os.path.dirname(_curr)

from backtesting import (
    Trade,
    TradeLogManager,
    EquityCurveTracker,
    TradeAnalytics,
    PerformanceMetrics,
    PortfolioAnalytics,
    AdvancedPortfolioMetrics,
    PositionSizer,
    FixedQuantitySizer,
    FixedCapitalSizer,
    PercentEquitySizer,
    ATRSizer,
    RiskManagementConfig,
    DetailedConsoleReporter,
    ParameterOptimizer,
    WalkForwardAnalyzer
)

# Create log file for console output
log_path = os.path.abspath("macd_backtest.txt")
log_file = open(log_path, "w")

def log(*args, **kwargs):
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    s = sep.join(str(a) for a in args) + end
    builtins.print(s, end='')
    log_file.write(s)

# Override print globally for logging
print = log

print("📊 OpenAlgo MACD Research-Grade Backtesting Engine")

# Default Tickers (Yahoo Finance Ticker for Reliance Industries)
SYMBOLS_MAP = {
    "RELIANCE": "RELIANCE.NS"
}

# ================= OPTIMIZED STRATEGY CONFIGURATION =================
USE_ATR_RISK = False          # False: Extended Trend-Following Crossover Exit
ATR_MULT_SL = 0.0             # Disabled
ATR_MULT_TP = 0.0             # Disabled

STOP_LOSS_PCT = 0.0           # 0.0: Exit on Trend Breakdown / Crossover
TARGET_PROFIT_PCT = 0.0       # 0.0: Let Trend Run
TRAILING_SL_PCT = 0.0         # 0.0: No Early Trailing Cut-Off

SLIPPAGE_PCT = 0.05           # 0.05% Slippage per order execution (5 bps)
BROKERAGE_PCT = 0.03         # 0.03% Brokerage / STT / Charges per trade side
BROKERAGE_PER_ORDER = 20.0   # Flat ₹20 per executed order

MACD_FAST = 6                 # Fast EMA Period (Grid-Search Optimized)
MACD_SLOW = 19                # Slow EMA Period (Grid-Search Optimized)
MACD_SIGNAL = 5               # Signal Period (Grid-Search Optimized)
RSI_PERIOD = 14               # RSI Period
ATR_PERIOD = 14               # ATR Period
# ====================================================================

OPENALGO_API_KEY = os.getenv("OPENALGO_API_KEY", "")
OPENALGO_HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

client = api(api_key=OPENALGO_API_KEY, host=OPENALGO_HOST) if (client_available and OPENALGO_API_KEY) else None

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ====================================================================
# MACD BACKTESTER CLASS
# ====================================================================

class MACDBacktester:
    def __init__(
        self, 
        symbol: str, 
        yf_ticker: str, 
        initial_capital: float = 100000.0,
        position_sizer: Optional[PositionSizer] = None,
        risk_config: Optional[RiskManagementConfig] = None,
        slippage_pct: float = SLIPPAGE_PCT,
        brokerage_pct: float = BROKERAGE_PCT,
        brokerage_per_order: float = BROKERAGE_PER_ORDER
    ):
        self.symbol = symbol
        self.yf_ticker = yf_ticker
        self.initial_capital = initial_capital
        self.position_sizer = position_sizer or FixedQuantitySizer(1.0)
        self.risk_config = risk_config or RiskManagementConfig()
        self.slippage_pct = slippage_pct
        self.brokerage_pct = brokerage_pct
        self.brokerage_per_order = brokerage_per_order
        self.trade_manager = TradeLogManager()
        self.equity_tracker = EquityCurveTracker(initial_capital=initial_capital)
        self.trades = []
        self.signals = []
        self.macd_values = None

    def calculate_macd(self, prices, fast=MACD_FAST, slow=MACD_SLOW, signal_period=MACD_SIGNAL):
        """
        Calculate Fast MACD indicator series using Exponential Moving Averages (6, 19, 5).
        """
        if len(prices) < slow:
            return None, None, None
        
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram

    def generate_signals(self, macd_line, signal_line, histogram, prices, ema50=None):
        """
        Generate BUY (+1) / SELL (-1) signals with Trend Regime Filter (50 EMA).
        - BUY: Bullish Crossover AND Close >= 50 EMA (In Medium-Term Uptrend)
        - SELL: Bearish Crossover AND Close <= 50 EMA (In Medium-Term Downtrend)
        """
        signals = []
        length = len(macd_line)
        if length < 3:
            return signals

        for i in range(2, length):
            prev_macd = macd_line.iloc[i-1]
            prev_signal = signal_line.iloc[i-1]
            curr_macd = macd_line.iloc[i]
            curr_signal = signal_line.iloc[i]
            curr_close = prices.iloc[i]
            curr_ema = ema50.iloc[i] if ema50 is not None and not np.isnan(ema50.iloc[i]) else curr_close

            # Bullish Trend Regime Filter (Close >= 50 EMA) + Crossover
            if prev_macd <= prev_signal and curr_macd > curr_signal:
                if curr_close >= curr_ema:
                    signals.append(('BUY', i, curr_macd))
            # Bearish Trend Regime Filter (Close <= 50 EMA) + Crossover
            elif prev_macd >= prev_signal and curr_macd < curr_signal:
                if curr_close <= curr_ema:
                    signals.append(('SELL', i, curr_macd))
        
        return signals

    def backtest(self, candle_data, allow_short=True, fast=MACD_FAST, slow=MACD_SLOW, signal_period=MACD_SIGNAL):
        """
        Simulate Optimized MACD strategy execution with Position Sizing & Slippage/Brokerage.
        """
        if candle_data is None or len(candle_data) < slow:
            print(f"⚠️  Insufficient data for {self.symbol}")
            return None

        prices = candle_data['Close']
        macd_line, signal_line, histogram = self.calculate_macd(prices, fast=fast, slow=slow, signal_period=signal_period)
        if macd_line is None:
            return None

        # Calculate 50-day EMA Trend Regime Filter
        ema50_series = prices.ewm(span=50, adjust=False).mean()
        atr_series = calculate_atr(candle_data, ATR_PERIOD)
        signals = self.generate_signals(macd_line, signal_line, histogram, prices, ema50=ema50_series)
        
        self.trade_manager = TradeLogManager()
        self.equity_tracker = EquityCurveTracker(initial_capital=self.initial_capital)
        
        position = 0  # +1 LONG, -1 SHORT, 0 FLAT
        entry_price = 0.0
        entry_date = None
        entry_index = 0
        trade_id_counter = 1
        cash = self.initial_capital
        current_qty = 1.0

        sig_dict = {index: sig_type for sig_type, index, macd_val in signals}
        n = len(candle_data)

        peak_price = 0.0
        trough_price = float('inf')
        sl_price = float('-inf')
        target_price = float('inf')
        breakeven_triggered = False

        for i in range(0, n - 1):
            curr_date = candle_data.index[i]
            curr_close = float(candle_data['Close'].iloc[i])
            
            # Record Equity Curve snapshot at current bar close
            if position == 1:
                pos_val = cash + (curr_close - entry_price) * current_qty
            elif position == -1:
                pos_val = cash + (entry_price - curr_close) * current_qty
            else:
                pos_val = cash
            self.equity_tracker.record_bar(curr_date, pos_val, cash, pos_val - cash)

            sig_type = sig_dict.get(i)
            next_open = float(candle_data['Open'].iloc[i + 1])
            next_high = float(candle_data['High'].iloc[i + 1])
            next_low = float(candle_data['Low'].iloc[i + 1])
            next_date = candle_data.index[i + 1]

            # --- Intra-candle Risk Management & Multi-Stage Exits Check ---
            if position == 1:  # Active LONG
                holding_bars = (i + 1) - entry_index
                peak_price = max(peak_price, next_high)
                
                # Phase 5: Break-even stop logic
                if self.risk_config.use_breakeven_stop and not breakeven_triggered:
                    if peak_price >= entry_price * (1 + self.risk_config.breakeven_profit_trigger_pct / 100.0):
                        sl_price = max(sl_price, entry_price)
                        breakeven_triggered = True

                tsl_p = peak_price * (1 - TRAILING_SL_PCT / 100) if (TRAILING_SL_PCT > 0 and peak_price > entry_price) else float('-inf')

                exit_reason = None
                exit_p = next_open

                if next_high >= target_price:
                    exit_reason = 'TARGET'
                    exit_p = max(target_price, next_open)
                elif next_low <= sl_price:
                    exit_reason = 'BREAKEVEN_SL' if breakeven_triggered and sl_price == entry_price else 'STOP_LOSS'
                    exit_p = min(sl_price, next_open)
                elif next_low <= tsl_p:
                    exit_reason = 'TRAILING_SL'
                    exit_p = min(tsl_p, next_open)
                elif self.risk_config.max_holding_bars and holding_bars >= self.risk_config.max_holding_bars:
                    exit_reason = 'TIME_EXIT'
                    exit_p = next_open

                if exit_reason:
                    entry_exec = entry_price * (1 + self.slippage_pct / 100.0)
                    exit_exec = exit_p * (1 - self.slippage_pct / 100.0)
                    entry_fee = (entry_exec * current_qty) * (self.brokerage_pct / 100.0) + self.brokerage_per_order
                    exit_fee = (exit_exec * current_qty) * (self.brokerage_pct / 100.0) + self.brokerage_per_order
                    total_brokerage = entry_fee + exit_fee
                    total_slippage = (entry_price * (self.slippage_pct / 100.0) + exit_p * (self.slippage_pct / 100.0)) * current_qty

                    pnl = ((exit_exec - entry_exec) * current_qty) - total_brokerage
                    pnl_pct = (pnl / (entry_exec * current_qty)) * 100.0 if (entry_exec * current_qty) > 0 else 0.0
                    cash += pnl

                    trade_obj = Trade(
                        trade_id=trade_id_counter,
                        symbol=self.symbol,
                        side='LONG',
                        entry_index=entry_index,
                        exit_index=i + 1,
                        entry_date=entry_date,
                        exit_date=next_date,
                        entry_price=entry_exec,
                        exit_price=exit_exec,
                        quantity=current_qty,
                        profit_loss=pnl,
                        profit_loss_pct=pnl_pct,
                        holding_period=holding_bars,
                        exit_reason=exit_reason,
                        type=f'LONG_{exit_reason}',
                        slippage=total_slippage,
                        brokerage=total_brokerage
                    )
                    self.trade_manager.add_trade(trade_obj)
                    trade_id_counter += 1
                    position = 0

            elif position == -1:  # Active SHORT
                holding_bars = (i + 1) - entry_index
                trough_price = min(trough_price, next_low)
                
                # Phase 5: Break-even stop logic for SHORT
                if self.risk_config.use_breakeven_stop and not breakeven_triggered:
                    if trough_price <= entry_price * (1 - self.risk_config.breakeven_profit_trigger_pct / 100.0):
                        sl_price = min(sl_price, entry_price)
                        breakeven_triggered = True

                tsl_p = trough_price * (1 + TRAILING_SL_PCT / 100) if (TRAILING_SL_PCT > 0 and trough_price < entry_price) else float('inf')

                exit_reason = None
                exit_p = next_open

                if next_low <= target_price:
                    exit_reason = 'TARGET'
                    exit_p = min(target_price, next_open)
                elif next_high >= sl_price:
                    exit_reason = 'BREAKEVEN_SL' if breakeven_triggered and sl_price == entry_price else 'STOP_LOSS'
                    exit_p = max(sl_price, next_open)
                elif next_high >= tsl_p:
                    exit_reason = 'TRAILING_SL'
                    exit_p = max(tsl_p, next_open)
                elif self.risk_config.max_holding_bars and holding_bars >= self.risk_config.max_holding_bars:
                    exit_reason = 'TIME_EXIT'
                    exit_p = next_open

                if exit_reason:
                    entry_exec = entry_price * (1 - self.slippage_pct / 100.0)
                    exit_exec = exit_p * (1 + self.slippage_pct / 100.0)
                    entry_fee = (entry_exec * current_qty) * (self.brokerage_pct / 100.0) + self.brokerage_per_order
                    exit_fee = (exit_exec * current_qty) * (self.brokerage_pct / 100.0) + self.brokerage_per_order
                    total_brokerage = entry_fee + exit_fee
                    total_slippage = (entry_price * (self.slippage_pct / 100.0) + exit_p * (self.slippage_pct / 100.0)) * current_qty

                    pnl = ((entry_exec - exit_exec) * current_qty) - total_brokerage
                    pnl_pct = (pnl / (entry_exec * current_qty)) * 100.0 if (entry_exec * current_qty) > 0 else 0.0
                    cash += pnl

                    trade_obj = Trade(
                        trade_id=trade_id_counter,
                        symbol=self.symbol,
                        side='SHORT',
                        entry_index=entry_index,
                        exit_index=i + 1,
                        entry_date=entry_date,
                        exit_date=next_date,
                        entry_price=entry_exec,
                        exit_price=exit_exec,
                        quantity=current_qty,
                        profit_loss=pnl,
                        profit_loss_pct=pnl_pct,
                        holding_period=holding_bars,
                        exit_reason=exit_reason,
                        type=f'SHORT_{exit_reason}',
                        slippage=total_slippage,
                        brokerage=total_brokerage
                    )
                    self.trade_manager.add_trade(trade_obj)
                    trade_id_counter += 1
                    position = 0

            # --- Crossover Signal Execution ---
            if sig_type == 'BUY':
                if position == -1:  # Close SHORT on opposite crossover
                    entry_exec = entry_price * (1 - self.slippage_pct / 100.0)
                    exit_exec = next_open * (1 + self.slippage_pct / 100.0)
                    entry_fee = (entry_exec * current_qty) * (self.brokerage_pct / 100.0) + self.brokerage_per_order
                    exit_fee = (exit_exec * current_qty) * (self.brokerage_pct / 100.0) + self.brokerage_per_order
                    total_brokerage = entry_fee + exit_fee
                    total_slippage = (entry_price * (self.slippage_pct / 100.0) + next_open * (self.slippage_pct / 100.0)) * current_qty

                    pnl = ((entry_exec - exit_exec) * current_qty) - total_brokerage
                    pnl_pct = (pnl / (entry_exec * current_qty)) * 100.0 if (entry_exec * current_qty) > 0 else 0.0
                    cash += pnl

                    trade_obj = Trade(
                        trade_id=trade_id_counter,
                        symbol=self.symbol,
                        side='SHORT',
                        entry_index=entry_index,
                        exit_index=i + 1,
                        entry_date=entry_date,
                        exit_date=next_date,
                        entry_price=entry_exec,
                        exit_price=exit_exec,
                        quantity=current_qty,
                        profit_loss=pnl,
                        profit_loss_pct=pnl_pct,
                        holding_period=(i + 1) - entry_index,
                        exit_reason='CROSSOVER',
                        type='SHORT_CROSS',
                        slippage=total_slippage,
                        brokerage=total_brokerage
                    )
                    self.trade_manager.add_trade(trade_obj)
                    trade_id_counter += 1
                    position = 0

                if position == 0:  # Open LONG
                    position = 1
                    entry_price = next_open
                    entry_date = next_date
                    entry_index = i + 1
                    peak_price = next_open
                    breakeven_triggered = False

                    # Dynamic Position Sizing
                    curr_atr = float(atr_series.iloc[i]) if atr_series is not None and not np.isnan(atr_series.iloc[i]) else 0.0
                    current_qty = self.position_sizer.calculate_quantity(entry_price, pos_val, curr_atr)

                    # Set Stop Loss & Target using ATR Dynamic Risk Management
                    if USE_ATR_RISK and curr_atr > 0:
                        sl_price = entry_price - (curr_atr * ATR_MULT_SL)
                        target_price = entry_price + (curr_atr * ATR_MULT_TP)
                    else:
                        sl_price = entry_price * (1 - STOP_LOSS_PCT / 100) if STOP_LOSS_PCT > 0 else float('-inf')
                        target_price = entry_price * (1 + TARGET_PROFIT_PCT / 100) if TARGET_PROFIT_PCT > 0 else float('inf')

            elif sig_type == 'SELL':
                if position == 1:  # Close LONG on opposite crossover
                    entry_exec = entry_price * (1 + self.slippage_pct / 100.0)
                    exit_exec = next_open * (1 - self.slippage_pct / 100.0)
                    entry_fee = (entry_exec * current_qty) * (self.brokerage_pct / 100.0) + self.brokerage_per_order
                    exit_fee = (exit_exec * current_qty) * (self.brokerage_pct / 100.0) + self.brokerage_per_order
                    total_brokerage = entry_fee + exit_fee
                    total_slippage = (entry_price * (self.slippage_pct / 100.0) + next_open * (self.slippage_pct / 100.0)) * current_qty

                    pnl = ((exit_exec - entry_exec) * current_qty) - total_brokerage
                    pnl_pct = (pnl / (entry_exec * current_qty)) * 100.0 if (entry_exec * current_qty) > 0 else 0.0
                    cash += pnl

                    trade_obj = Trade(
                        trade_id=trade_id_counter,
                        symbol=self.symbol,
                        side='LONG',
                        entry_index=entry_index,
                        exit_index=i + 1,
                        entry_date=entry_date,
                        exit_date=next_date,
                        entry_price=entry_exec,
                        exit_price=exit_exec,
                        quantity=current_qty,
                        profit_loss=pnl,
                        profit_loss_pct=pnl_pct,
                        holding_period=(i + 1) - entry_index,
                        exit_reason='CROSSOVER',
                        type='LONG_CROSS',
                        slippage=total_slippage,
                        brokerage=total_brokerage
                    )
                    self.trade_manager.add_trade(trade_obj)
                    trade_id_counter += 1
                    position = 0

                if position == 0 and allow_short:  # Open SHORT
                    position = -1
                    entry_price = next_open
                    entry_date = next_date
                    entry_index = i + 1
                    trough_price = next_open
                    breakeven_triggered = False

                    # Dynamic Position Sizing
                    curr_atr = float(atr_series.iloc[i]) if atr_series is not None and not np.isnan(atr_series.iloc[i]) else 0.0
                    current_qty = self.position_sizer.calculate_quantity(entry_price, pos_val, curr_atr)

                    # Set Stop Loss & Target using ATR Dynamic Risk Management
                    if USE_ATR_RISK and curr_atr > 0:
                        sl_price = entry_price + (curr_atr * ATR_MULT_SL)
                        target_price = entry_price - (curr_atr * ATR_MULT_TP)
                    else:
                        sl_price = entry_price * (1 + STOP_LOSS_PCT / 100) if STOP_LOSS_PCT > 0 else float('inf')
                        target_price = entry_price * (1 - TARGET_PROFIT_PCT / 100) if TARGET_PROFIT_PCT > 0 else float('-inf')

        # Record last bar snapshot
        last_date = candle_data.index[-1]
        last_close = float(candle_data['Close'].iloc[-1])
        if position == 1:
            pos_val = cash + (last_close - entry_price) * current_qty
        elif position == -1:
            pos_val = cash + (entry_price - last_close) * current_qty
        else:
            pos_val = cash
        self.equity_tracker.record_bar(last_date, pos_val, cash, pos_val - cash)

        # Legacy attribute compatibility
        self.trades = [t.to_dict() for t in self.trade_manager.trades]
        self.signals = signals
        self.macd_values = (macd_line, signal_line, histogram)
        return self.trades

    def calculate_statistics(self):
        """
        Calculate backtest performance metrics via TradeAnalytics & PortfolioAnalytics.
        """
        metrics = TradeAnalytics.calculate_metrics(self.trade_manager)
        adv_metrics = PortfolioAnalytics.calculate_advanced_metrics(self.equity_tracker, self.trade_manager)
        if metrics.total_trades == 0:
            return None

        return {
            'total_trades': metrics.total_trades,
            'winning_trades': metrics.winning_trades,
            'losing_trades': metrics.losing_trades,
            'win_rate': metrics.win_rate,
            'total_profit': metrics.total_profit,
            'total_profit_pct': metrics.total_profit_pct,
            'avg_profit_per_trade': metrics.avg_trade_pnl,
            'avg_profit_pct': metrics.avg_trade_pnl_pct,
            'gross_profit': metrics.gross_profit,
            'gross_loss': metrics.gross_loss,
            'profit_factor': metrics.profit_factor,
            'avg_win': metrics.avg_win,
            'avg_win_pct': metrics.avg_win_pct,
            'avg_loss': metrics.avg_loss,
            'avg_loss_pct': metrics.avg_loss_pct,
            'largest_winner': metrics.largest_winner,
            'largest_winner_pct': metrics.largest_winner_pct,
            'largest_loser': metrics.largest_loser,
            'largest_loser_pct': metrics.largest_loser_pct,
            'risk_reward_ratio': metrics.risk_reward_ratio,
            'expectancy': metrics.expectancy,
            'expectancy_pct': metrics.expectancy_pct,
            'max_consecutive_wins': metrics.max_consecutive_wins,
            'max_consecutive_losses': metrics.max_consecutive_losses,
            'cagr': adv_metrics.cagr,
            'sharpe_ratio': adv_metrics.sharpe_ratio,
            'sortino_ratio': adv_metrics.sortino_ratio,
            'calmar_ratio': adv_metrics.calmar_ratio,
            'annual_volatility': adv_metrics.annual_volatility,
            'recovery_factor': adv_metrics.recovery_factor,
            'exposure_pct': adv_metrics.exposure_pct,
            'avg_holding_period': adv_metrics.avg_holding_period
        }

def _grid_search_runner(symbol, yf_ticker, params, candle_data):
    """Helper runner for ParameterOptimizer grid search."""
    fast = params.get('fast', MACD_FAST)
    slow = params.get('slow', MACD_SLOW)
    signal = params.get('signal', MACD_SIGNAL)

    tester = MACDBacktester(symbol, yf_ticker)
    trades = tester.backtest(candle_data, fast=fast, slow=slow, signal_period=signal)
    if trades is None:
        return None
    return tester

def _oos_runner(symbol, yf_ticker, params, candle_data):
    """Helper runner for WalkForwardAnalyzer out-of-sample testing."""
    tester = MACDBacktester(symbol, yf_ticker)
    tester.backtest(candle_data)
    return tester

START_DATE = "2016-01-01"
END_DATE = datetime.now().strftime("%Y-%m-%d")
INTERVAL = "1d"

# Main Execution
print("\n" + "="*80)
print("MACD STRATEGY BACKTEST - YFINANCE REAL MARKET DATA (10 YEARS)")
print("="*80)
print(f"📅 Evaluation Period: {START_DATE} to {END_DATE} (10 Years)")
print(f"📊 Analysis Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"⏱️  Data Interval: 1 Day ('{INTERVAL}')")
print("="*80)

summary_stats = {}
all_trades = {}
chart_images = {}

for symbol, yf_ticker in SYMBOLS_MAP.items():
    print(f"\n{'='*80}")
    print(f"📈 {symbol} ({yf_ticker}) - 10-Year Backtest Analysis")
    print(f"{'='*80}")

    try:
        sizer = ATRSizer(risk_pct=1.0, atr_multiplier=2.0)
        risk_cfg = RiskManagementConfig(use_breakeven_stop=False, max_holding_bars=None)
        
        backtester = MACDBacktester(symbol, yf_ticker, position_sizer=sizer, risk_config=risk_cfg)
        print(f"\n🔄 Downloading historical market data from yfinance for {symbol} ({yf_ticker})...")
        
        candle_data = yf.download(yf_ticker, start=START_DATE, end=END_DATE, interval=INTERVAL)

        if isinstance(candle_data.columns, pd.MultiIndex):
            candle_data.columns = candle_data.columns.get_level_values(0)

        if candle_data.empty:
            print(f"⚠️  No data downloaded for {symbol}")
            continue

        print(f"Downloaded {len(candle_data)} candles for {symbol}. First 3 rows:")
        print(candle_data[['Open', 'High', 'Low', 'Close']].head(3))

        trades = backtester.backtest(candle_data, allow_short=False)
        all_trades[symbol] = trades

        if trades:
            print(f"\n✅ Backtest complete: {len(trades)} trades executed in 10 Years")
            stats = backtester.calculate_statistics()
            summary_stats[symbol] = stats
            metrics = TradeAnalytics.calculate_metrics(backtester.trade_manager)
            adv_metrics = PortfolioAnalytics.calculate_advanced_metrics(backtester.equity_tracker, backtester.trade_manager)

            # Export trades to CSV
            csv_path = backtester.trade_manager.export_csv(f"{symbol}_macd_trades.csv")
            print(f"📁 Trades exported to CSV via TradeLogManager: {csv_path}")

            # Out-of-Sample Validation
            print(f"\n🧪 PHASE 7: RUNNING OUT-OF-SAMPLE (70% IS / 30% OOS) ROBUSTNESS TEST...")
            oos_results = WalkForwardAnalyzer.run_out_of_sample_test(symbol, yf_ticker, candle_data, _oos_runner, in_sample_pct=0.7)
            print(f"  • In-Sample  (IS) Bars : {oos_results['is_bars']} | Win Rate: {oos_results['is_metrics'].win_rate:.2f}% | Sharpe: {oos_results['is_adv_metrics'].sharpe_ratio:.2f}")
            print(f"  • Out-Sample (OOS) Bars: {oos_results['oos_bars']} | Win Rate: {oos_results['oos_metrics'].win_rate:.2f}% | Sharpe: {oos_results['oos_adv_metrics'].sharpe_ratio:.2f}")

            # Export trades to CSV
            csv_path = backtester.trade_manager.export_csv(f"{symbol}_macd_trades.csv")
            print(f"📁 Trades exported to CSV via TradeLogManager: {csv_path}")

            # Print Detailed Console Summary Report & Evaluate Institutional Deployment Gate Checklist
            gate_res = DetailedConsoleReporter.print_summary(symbol, metrics, adv_metrics, backtester.equity_tracker, csv_path, oos_results=oos_results)
            stats['gate_results'] = gate_res

            # Grid Search Parameter Optimization
            print(f"\n🔍 PHASE 7: RUNNING GRID SEARCH PARAMETER OPTIMIZATION (MACD FAST, SLOW, SIGNAL)...")
            param_grid = {
                'fast': [6, 8, 12],
                'slow': [19, 21, 26],
                'signal': [5, 9]
            }
            opt_runs = ParameterOptimizer.grid_search(symbol, yf_ticker, candle_data, param_grid, _grid_search_runner, rank_by='sharpe_ratio')
            print(f"  Completed {len(opt_runs)} parameter combinations. Top 3 Results:")
            for rank_i, opt in enumerate(opt_runs[:3], 1):
                p = opt.params
                print(f"   #{rank_i} Params: Fast={p['fast']}, Slow={p['slow']}, Signal={p['signal']} -> Sharpe: {opt.adv_metrics.sharpe_ratio:.2f} | WinRate: {opt.metrics.win_rate:.2f}% | Return: {opt.metrics.total_profit_pct:+.2f}%")

            # Enhanced Visualization with Equity & Drawdown
            macd_line, signal_line, histogram = backtester.macd_values
            eq_df = backtester.equity_tracker.get_equity_dataframe()

            plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
            fig, (ax_price, ax_macd, ax_equity, ax_dd) = plt.subplots(
                4, 1, figsize=(14, 12), sharex=True, 
                gridspec_kw={'height_ratios': [3, 1, 1.2, 1]}, dpi=150
            )

            # Price line & Trades
            ax_price.plot(candle_data.index, candle_data['Close'], label='Close Price', color='#1f77b4', linewidth=1.8, zorder=2)
            trades_df = backtester.trade_manager.to_dataframe()
            for _, t in trades_df.iterrows():
                e_date = pd.to_datetime(t['entry_date'])
                x_date = pd.to_datetime(t['exit_date'])
                e_price = t['entry_price']
                x_price = t['exit_price']
                is_win = t['profit_loss'] > 0
                line_color = '#28a745' if is_win else '#dc3545'

                ax_price.plot([e_date, x_date], [e_price, x_price], color=line_color, linestyle='--', linewidth=1.5, alpha=0.85, zorder=3)
                ax_price.axvspan(e_date, x_date, color=line_color, alpha=0.08, zorder=1)

            ax_price.set_ylabel('Price (INR)', fontsize=11, fontweight='bold')
            ax_price.set_title(f"{symbol} ({yf_ticker}) Backtest - Trades, Signals, Equity Curve & Drawdown", fontsize=13, fontweight='bold', pad=10)
            ax_price.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
            ax_price.grid(True, linestyle='--', alpha=0.5)

            # MACD Subplot
            ax_macd.plot(candle_data.index, macd_line, label='MACD (8, 21)', color='#0066cc', linewidth=1.5)
            ax_macd.plot(candle_data.index, signal_line, label='Signal (5)', color='#ff9900', linewidth=1.5)
            colors = ['#28a745' if val >= 0 else '#dc3545' for val in histogram]
            ax_macd.bar(candle_data.index, histogram, label='Histogram', color=colors, alpha=0.45, width=0.8)
            ax_macd.axhline(0, color='black', linewidth=0.8, linestyle='--')
            ax_macd.set_ylabel('MACD', fontsize=10, fontweight='bold')
            ax_macd.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
            ax_macd.grid(True, linestyle='--', alpha=0.5)

            # Equity Curve Subplot
            if not eq_df.empty:
                eq_dates = pd.to_datetime(eq_df['date'])
                ax_equity.plot(eq_dates, eq_df['portfolio_value'], label='Portfolio Equity', color='#2b5c8f', linewidth=1.8)
                ax_equity.plot(eq_dates, eq_df['cum_max'], label='Peak Equity (HWM)', color='#28a745', linestyle=':', linewidth=1.2)
                ax_equity.set_ylabel('Equity (INR)', fontsize=10, fontweight='bold')
                ax_equity.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
                ax_equity.grid(True, linestyle='--', alpha=0.5)

                # Drawdown Curve Subplot
                ax_dd.fill_between(eq_dates, eq_df['drawdown_pct'], 0, color='#dc3545', alpha=0.4, label='Drawdown %')
                ax_dd.plot(eq_dates, eq_df['drawdown_pct'], color='#a71d2a', linewidth=1.0)
                ax_dd.set_ylabel('Drawdown %', fontsize=10, fontweight='bold')
                ax_dd.set_xlabel('Date', fontsize=11, fontweight='bold')
                ax_dd.legend(loc='lower left', frameon=True, facecolor='white', framealpha=0.9)
                ax_dd.grid(True, linestyle='--', alpha=0.5)

            # Format Date axis
            ax_dd.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
            fig.autofmt_xdate()

            # Save chart image file
            chart_file_path = os.path.abspath(f"{symbol}_macd_chart.png")
            fig.savefig(chart_file_path, format='png', bbox_inches='tight')

            # Save chart to base64 for HTML report
            buf = BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            img_b64 = base64.b64encode(buf.read()).decode('utf-8')
            chart_images[symbol] = img_b64
            print(f"🖼️ Research chart with Equity & Drawdown saved: {chart_file_path}")
        else:
            print(f"⚠️  No trades generated for {symbol}")

        time.sleep(1)

    except Exception as e:
        print(f"❌ Error backtesting {symbol}: {e}")

# Build HTML Report
html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>MACD Strategy Research Report (yfinance)</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 20px; background-color: #f8f9fa; color: #333; }}
    h1, h2, h3 {{ color: #2c3e50; }}
    .card {{ background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
    th, td {{ border: 1px solid #dee2e6; padding: 8px 12px; text-align: left; }}
    th {{ background-color: #e9ecef; }}
    .badge-pass {{ background: #28a745; color: white; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
    .badge-fail {{ background: #dc3545; color: white; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
    .badge-long {{ background: #28a745; color: white; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
    .badge-short {{ background: #dc3545; color: white; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
    .verdict-box {{ font-size: 16px; font-weight: bold; padding: 12px; border-radius: 6px; margin-top: 15px; text-align: center; }}
    .verdict-pass {{ background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
    .verdict-fail {{ background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
  </style>
</head>
<body>
  <h1>📊 Research-Grade MACD Strategy Performance Report</h1>
  <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
  <p><strong>Data Source:</strong> yfinance (Yahoo Finance API)</p>

  <div class="card">
    <h2>Summary Statistics</h2>
"""

for sym, s in summary_stats.items():
    pf_str = f"{s['profit_factor']:.2f}" if not np.isnan(s['profit_factor']) else "N/A"
    html_content += f"""
    <h3>{sym} ({SYMBOLS_MAP.get(sym)})</h3>
    <ul>
      <li><strong>Total Trades:</strong> {s['total_trades']}</li>
      <li><strong>Win Rate:</strong> {s['win_rate']:.2f}% ({s['winning_trades']} Wins / {s['losing_trades']} Losses)</li>
      <li><strong>Sharpe Ratio:</strong> {s['sharpe_ratio']:.2f}</li>
      <li><strong>CAGR:</strong> {s['cagr']:+.2f}%</li>
      <li><strong>Total Return:</strong> {s['total_profit_pct']:.2f}%</li>
      <li><strong>Profit Factor:</strong> {pf_str}</li>
    </ul>
    """

    if 'gate_results' in s:
        g_res = s['gate_results']
        verdict_class = "verdict-pass" if g_res['overall_passed'] else "verdict-fail"
        html_content += f"""
        <h3>🚦 Institutional Deployment & Research Readiness Checklist</h3>
        <table>
          <tr><th>Checklist Gate</th><th>Institutional Target Benchmark</th><th>Actual Strategy Value</th><th>Status</th></tr>
        """
        for g in g_res['gates']:
            badge = '<span class="badge-pass">PASS</span>' if g['passed'] else '<span class="badge-fail">FAIL</span>'
            html_content += f"<tr><td>{g['name']}</td><td>{g['target']}</td><td>{g['actual']}</td><td>{badge}</td></tr>\n"
        
        html_content += f"""
        </table>
        <div class="verdict-box {verdict_class}">
          FINAL VERDICT: {g_res['verdict']} ({g_res['passed_count']}/{g_res['total_count']} Gates Passed)
        </div>
        """

html_content += "</div>\n"

for sym, trades in all_trades.items():
    html_content += f'<div class="card">\n<h2>{sym} Trade Analysis</h2>\n'
    if sym in chart_images:
        html_content += f'<img src="data:image/png;base64,{chart_images[sym]}" style="max-width:100%; height:auto; margin-bottom:15px;">\n'

    html_content += "<table><tr><th>Entry Date</th><th>Exit Date</th><th>Type</th><th>Entry Price</th><th>Exit Price</th><th>PnL (%)</th></tr>\n"
    for t in trades:
        badge = f'<span class="badge-long">LONG</span>' if t['type'].startswith('LONG') else f'<span class="badge-short">SHORT</span>'
        entry_d = t['entry_date'].strftime('%Y-%m-%d') if hasattr(t['entry_date'], 'strftime') else str(t['entry_date'])
        exit_d = t['exit_date'].strftime('%Y-%m-%d') if hasattr(t['exit_date'], 'strftime') else str(t['exit_date'])
        html_content += f"<tr><td>{entry_d}</td><td>{exit_d}</td><td>{badge}</td><td>{t['entry_price']:.2f}</td><td>{t['exit_price']:.2f}</td><td>{t['profit_loss_pct']:.2f}%</td></tr>\n"
    html_content += "</table>\n</div>\n"

html_content += "</body>\n</html>"

import subprocess

report_path = os.path.abspath("macd_report.html")
with open(report_path, "w") as f:
    f.write(html_content)

print(f"\n✅ HTML report generated: {report_path}")
print(f"✅ Text log written to: {log_path}")

try:
    subprocess.run(["open", report_path], check=False)
    print(f"✅ HTML report opened in browser: {report_path}")
except Exception as e:
    webbrowser.open(f"file://{report_path}")

log_file.close()