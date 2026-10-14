"""
OpenAlgo & yfinance MACD Strategy Backtester
-------------------------------------------
- Data Source: yfinance (Yahoo Finance API)
- Indicator: MACD (12, 26, 9)
- Signal Execution: Enter on Open price of next candle (No lookahead bias)
- Supports: LONG and SHORT positions, Stop Loss & Take Profit, Matplotlib chart output
"""

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime


def calculate_macd(df, fast=12, slow=26, signal=9):
    """
    Calculate MACD indicator series on pandas DataFrame.
    """
    ema_fast = df['Close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=slow, adjust=False).mean()
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    df['MACD'] = macd_line
    df['Signal'] = signal_line
    df['Histogram'] = histogram
    return df


def generate_macd_signals(df):
    """
    Generate crossover signals:
    +1: Bullish crossover (BUY / LONG)
    -1: Bearish crossover (SELL / SHORT)
     0: No crossover
    """
    df['Prev_MACD'] = df['MACD'].shift(1)
    df['Prev_Signal'] = df['Signal'].shift(1)
    
    # Bullish Crossover: MACD crosses above Signal
    bullish = (df['Prev_MACD'] <= df['Prev_Signal']) & (df['MACD'] > df['Signal'])
    
    # Bearish Crossover: MACD crosses below Signal
    bearish = (df['Prev_MACD'] >= df['Prev_Signal']) & (df['MACD'] < df['Signal'])
    
    df['Signal_Type'] = 0
    df.loc[bullish, 'Signal_Type'] = 1
    df.loc[bearish, 'Signal_Type'] = -1
    return df


def backtest_macd_strategy(df, allow_short=False, stop_loss_pct=None, take_profit_pct=None):
    """
    Simulate strategy execution without lookahead bias.
    Trade entry occurs on Open[i+1] when Signal[i] fires.
    """
    trades = []
    position = 0  # +1 for LONG, -1 for SHORT, 0 for FLAT
    entry_price = 0.0
    entry_time = None
    entry_idx = 0
    
    n = len(df)
    for i in range(1, n - 1):
        sig = df['Signal_Type'].iloc[i]
        curr_time = df.index[i]
        next_open = float(df['Open'].iloc[i + 1])  # Next candle open price (No lookahead bias)
        next_time = df.index[i + 1]
        
        # Check Stop Loss / Take Profit if in position
        if position != 0 and (stop_loss_pct or take_profit_pct):
            curr_high = float(df['High'].iloc[i])
            curr_low = float(df['Low'].iloc[i])
            
            pnl_pct_high = ((curr_high - entry_price) / entry_price) * position * 100
            pnl_pct_low = ((curr_low - entry_price) / entry_price) * position * 100
            
            exit_needed = False
            exit_price = 0.0
            reason = ""
            
            if stop_loss_pct:
                if position == 1 and pnl_pct_low <= -stop_loss_pct:
                    exit_needed, exit_price, reason = True, entry_price * (1 - stop_loss_pct / 100), "Stop Loss"
                elif position == -1 and pnl_pct_high <= -stop_loss_pct:
                    exit_needed, exit_price, reason = True, entry_price * (1 + stop_loss_pct / 100), "Stop Loss"
                    
            if not exit_needed and take_profit_pct:
                if position == 1 and pnl_pct_high >= take_profit_pct:
                    exit_needed, exit_price, reason = True, entry_price * (1 + take_profit_pct / 100), "Take Profit"
                elif position == -1 and pnl_pct_low >= take_profit_pct:
                    exit_needed, exit_price, reason = True, entry_price * (1 - take_profit_pct / 100), "Take Profit"
                    
            if exit_needed:
                pnl = (exit_price - entry_price) * position
                pnl_pct = (pnl / entry_price) * 100
                trades.append({
                    'type': 'LONG' if position == 1 else 'SHORT',
                    'entry_date': entry_time,
                    'exit_date': curr_time,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'exit_reason': reason
                })
                position = 0
                continue

        # Crossover Entry/Exit Logic
        if sig == 1:  # Bullish Crossover
            if position == -1:  # Close SHORT
                pnl = (next_open - entry_price) * -1
                pnl_pct = (pnl / entry_price) * 100
                trades.append({
                    'type': 'SHORT',
                    'entry_date': entry_time,
                    'exit_date': next_time,
                    'entry_price': entry_price,
                    'exit_price': next_open,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'exit_reason': 'Signal Reversal'
                })
                position = 0
                
            if position == 0:  # Open LONG
                position = 1
                entry_price = next_open
                entry_time = next_time
                entry_idx = i + 1

        elif sig == -1:  # Bearish Crossover
            if position == 1:  # Close LONG
                pnl = (next_open - entry_price) * 1
                pnl_pct = (pnl / entry_price) * 100
                trades.append({
                    'type': 'LONG',
                    'entry_date': entry_time,
                    'exit_date': next_time,
                    'entry_price': entry_price,
                    'exit_price': next_open,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'exit_reason': 'Signal Reversal'
                })
                position = 0
                
            if position == 0 and allow_short:  # Open SHORT
                position = -1
                entry_price = next_open
                entry_time = next_time
                entry_idx = i + 1

    return pd.DataFrame(trades)


def calculate_performance_metrics(trades_df, initial_capital=10000.0):
    """
    Calculate summary performance metrics.
    """
    if trades_df.empty:
        return {}
    
    total_trades = len(trades_df)
    winning_trades = len(trades_df[trades_df['pnl'] > 0])
    losing_trades = len(trades_df[trades_df['pnl'] < 0])
    win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
    
    total_pnl = trades_df['pnl'].sum()
    total_pnl_pct = trades_df['pnl_pct'].sum()
    
    gross_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
    gross_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.nan
    
    # Cumulative Drawdown
    equity_curve = initial_capital + trades_df['pnl'].cumsum()
    peak = equity_curve.cummax()
    drawdown = (equity_curve - peak) / peak * 100
    max_drawdown = drawdown.min()
    
    return {
        'Total Trades': total_trades,
        'Winning Trades': winning_trades,
        'Losing Trades': losing_trades,
        'Win Rate (%)': round(win_rate, 2),
        'Total Return (%)': round(total_pnl_pct, 2),
        'Profit Factor': round(profit_factor, 2) if not np.isnan(profit_factor) else 'N/A',
        'Max Drawdown (%)': round(max_drawdown, 2),
        'Average Trade Return (%)': round(trades_df['pnl_pct'].mean(), 2)
    }


def plot_macd_strategy(df, trades_df, symbol="Ticker"):
    """
    Plot price with Buy/Sell markers and MACD indicator subpanel.
    """
    fig, (ax_price, ax_macd) = plt.subplots(2, 1, figsize=(14, 9), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    
    # Plot Price
    ax_price.plot(df.index, df['Close'], label='Close Price', color='#1f77b4', alpha=0.7)
    
    # Overlay Trades
    if not trades_df.empty:
        long_entries = trades_df[trades_df['type'] == 'LONG']
        short_entries = trades_df[trades_df['type'] == 'SHORT']
        
        ax_price.scatter(long_entries['entry_date'], long_entries['entry_price'], marker='^', color='green', s=100, label='BUY (Long Entry)', zorder=5)
        ax_price.scatter(short_entries['entry_date'], short_entries['entry_price'], marker='v', color='red', s=100, label='SELL (Short Entry)', zorder=5)
    
    ax_price.set_title(f"{symbol} - MACD Strategy Backtest Chart", fontsize=14, fontweight='bold')
    ax_price.set_ylabel('Price', fontsize=12)
    ax_price.grid(True, linestyle='--', alpha=0.5)
    ax_price.legend(loc='upper left')
    
    # Plot MACD Subpanel
    ax_macd.plot(df.index, df['MACD'], label='MACD (12,26)', color='blue', linewidth=1.5)
    ax_macd.plot(df.index, df['Signal'], label='Signal (9)', color='orange', linewidth=1.5)
    
    # Color histogram bars
    colors = ['green' if val >= 0 else 'red' for val in df['Histogram']]
    ax_macd.bar(df.index, df['Histogram'], color=colors, alpha=0.4, label='Histogram', width=0.8)
    
    ax_macd.axhline(0, color='black', linestyle='--', linewidth=0.8)
    ax_macd.set_ylabel('MACD', fontsize=12)
    ax_macd.set_xlabel('Date', fontsize=12)
    ax_macd.grid(True, linestyle='--', alpha=0.5)
    ax_macd.legend(loc='upper left')
    
    plt.tight_layout()
    plt.show()


# ==========================================
# Run Strategy
# ==========================================
if __name__ == "__main__":
    SYMBOL = "RELIANCE.NS"  # Reliance Industries Share on NSE via Yahoo Finance
    START_DATE = "2023-01-01"
    END_DATE = "2026-01-01"
    INTERVAL = "1d"         # 1d, 1h, 15m, 5m
    
    print(f"📥 Fetching historical data for {SYMBOL} via yfinance ({START_DATE} to {END_DATE})...")
    df = yf.download(SYMBOL, start=START_DATE, end=END_DATE, interval=INTERVAL)
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    if df.empty:
        print("❌ Error: No data fetched from yfinance.")
    else:
        # Step 1: Calculate MACD
        df = calculate_macd(df, fast=12, slow=26, signal=9)
        
        # Step 2: Generate Signals
        df = generate_macd_signals(df)
        
        # Step 3: Run Backtest
        trades_df = backtest_macd_strategy(df, allow_short=True)
        
        # Step 4: Display Statistics
        print("\n" + "="*50)
        print(f"📊 BACKTEST RESULTS FOR {SYMBOL}")
        print("="*50)
        metrics = calculate_performance_metrics(trades_df)
        for k, v in metrics.items():
            print(f"{k:<30}: {v}")
            
        print("\n===== SAMPLE TRADES (FIRST 10) =====")
        if not trades_df.empty:
            print(trades_df.head(10).to_string(index=False))
        else:
            print("No trades generated.")
            
        # Step 5: Plot Results
        # plot_macd_strategy(df, trades_df, symbol=SYMBOL)
