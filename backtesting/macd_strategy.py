"""
MACD Strategy Standalone Backtest with HTML Popup Report
Uses ta.trend MACD indicator with entries/exits printed to console and popup
"""

from ta.trend import MACD
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import os
import webbrowser
from io import BytesIO
import base64
import builtins

# setup logging to file
log_path = os.path.abspath("macd_backtest_strategy.txt")
log_file = open(log_path, "w")

def log(*args, **kwargs):
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    s = sep.join(str(a) for a in args) + end
    builtins.print(s, end='')
    log_file.write(s)

print = log

# The strategy function expected by result.py
# It receives a DataFrame with at least a "Close" column
# and returns two boolean series: entries and exits.

def strategy(data):
    close = data["Close"].squeeze()

    macd = MACD(close, 26, 12, 9)

    macd_line = macd.macd()
    macd_signal = macd.macd_signal()
    macd_hist = macd.macd_diff()

    # =========================
    # ENTRY CONDITIONS
    # =========================

    # 1️⃣ MACD bullish crossover
    macd_cross_up = (
        (macd_line > macd_signal) &
        (macd_line.shift(1) <= macd_signal.shift(1))
    )

    # 2️⃣ Histogram above zero
    hist_above_zero = macd_hist > 0

    # 3️⃣ Histogram rising
    hist_rising = macd_hist > macd_hist.shift(1)

    entries = macd_cross_up & hist_above_zero & hist_rising

    # =========================
    # EXIT CONDITION
    # =========================

    macd_cross_down = (
        (macd_line < macd_signal) &
        (macd_line.shift(1) >= macd_signal.shift(1))
    )

    exits = macd_cross_down

    return entries.fillna(False), exits.fillna(False)


# =========================
# BACKTEST RUNNER
# =========================

def run_backtest_with_report(data, symbol="CRUDE", initial_capital=100000, trailing_sl_percent=2.0):
    """
    Run standalone backtest with trailing stop loss and generate HTML report with charts
    
    Args:
        data: DataFrame with Close prices
        symbol: Trading symbol
        initial_capital: Starting capital
        trailing_sl_percent: Trailing stop loss as percentage (default 2%)
    """
    print("\\n" + "="*80)
    print("MACD STRATEGY BACKTEST WITH TRAILING STOP LOSS")
    print("="*80)
    print(f"Symbol: {symbol}")
    print(f"Data Points: {len(data)}")
    print(f"Period: {data.index[0]} to {data.index[-1]}")
    print(f"Trailing SL: {trailing_sl_percent}%")
    
    # call strategy
    entries, exits = strategy(data)
    
    # simulate trades with trailing stop loss
    trades = []
    entry_price = None
    entry_idx = None
    highest_price = None
    
    for i in range(1, len(data)):
        current_price = data["Close"].iloc[i]
        
        if entries.iloc[i] and entry_price is None:
            # Entry
            entry_price = current_price
            entry_idx = i
            highest_price = current_price
            
        elif entry_price is not None:
            # Update highest price since entry
            if current_price > highest_price:
                highest_price = current_price
            
            # Calculate trailing stop loss level
            trailing_sl_level = highest_price * (1 - trailing_sl_percent / 100)
            
            # Exit conditions: MACD signal OR trailing stop loss
            macd_exit = exits.iloc[i]
            sl_exit = current_price <= trailing_sl_level
            
            if macd_exit or sl_exit:
                exit_price = current_price
                pnl = exit_price - entry_price
                pnl_pct = (pnl / entry_price) * 100
                exit_reason = "MACD Signal" if (macd_exit and not sl_exit) else ("Trailing SL" if sl_exit else "Both")
                
                trades.append({
                    'entry_idx': entry_idx,
                    'exit_idx': i,
                    'entry_date': data.index[entry_idx],
                    'exit_date': data.index[i],
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'highest_price': highest_price,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'exit_reason': exit_reason
                })
                entry_price = None
                entry_idx = None
                highest_price = None
    
    # calculate metrics
    trades_df = pd.DataFrame(trades)
    
    print("\\n==============================")
    print(f"   STRATEGY PERFORMANCE ({symbol})")
    print("==============================\\n")
    
    if not trades_df.empty:
        total_trades = len(trades_df)
        wins = len(trades_df[trades_df['pnl']>0])
        losses = len(trades_df[trades_df['pnl']<0])
        win_rate = (wins/total_trades)*100 if total_trades > 0 else 0
        total_pnl = trades_df['pnl'].sum()
        profit_factor = trades_df[trades_df['pnl']>0]['pnl'].sum() / abs(trades_df[trades_df['pnl']<0]['pnl'].sum()) if len(trades_df[trades_df['pnl']<0]) > 0 else 0
        
        print(f"Total Trades: {total_trades}")
        print(f"Winning Trades: {wins}")
        print(f"Losing Trades: {losses}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Total P&L: ₹{total_pnl:.2f}")
        print(f"Profit Factor: {profit_factor:.2f}")
        
        # professional metrics
        print("\\n===== PROFESSIONAL METRICS =====\\n")
        print(f"Total Return: ₹{total_pnl:.2f}")
        print("Sharpe Ratio: N/A")
        print("Max Drawdown: N/A")
        
        # trade quality
        print("\\n===== TRADE QUALITY =====\\n")
        wins_df = trades_df[trades_df['pnl']>0]
        losses_df = trades_df[trades_df['pnl']<0]
        print(f"Average Win: {wins_df['pnl'].mean() if not wins_df.empty else 0:.2f}")
        print(f"Average Loss: {losses_df['pnl'].mean() if not losses_df.empty else 0:.2f}")
        print(f"Largest Win: {trades_df['pnl'].max():.2f}")
        print(f"Largest Loss: {trades_df['pnl'].min():.2f}")
        
        # trade details
        print("\\n===== TRADE DETAILS =====\\n")
        details = trades_df.rename(columns={'entry_date':'Entry','exit_date':'Exit','entry_price':'Buy','exit_price':'Sell','pnl':'PnL'})[["Entry","Exit","Buy","Sell","PnL"]]
        print(details.head().to_string(index=False))
        
        # generate chart with MACD
        print("\\n📊 Generating chart...")
        chart_b64 = generate_macd_chart(data, trades, symbol)
        
        # generate HTML report
        html_content = generate_html_report(symbol, trades_df, details, chart_b64)
        
        # save HTML
        report_path = os.path.abspath("macd_strategy_report.html")
        with open(report_path, "w") as f:
            f.write(html_content)
        print(f"\\n✅ Report generated: {report_path}")
        
        # open in browser
        webbrowser.open("file://" + report_path)
        
    else:
        print("❌ No trades generated")
    
    print(f"\\n✅ Log saved to {log_path}")
    # close log
    log_file.close()


def generate_macd_chart(data, trades, symbol):
    """Generate MACD chart with trade markers as base64"""
    close = data["Close"].squeeze()
    macd = MACD(close, 26, 12, 9)
    macd_line = macd.macd()
    macd_signal = macd.macd_signal()
    macd_hist = macd.macd_diff()
    
    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(3, 1, height_ratios=[2, 1, 1], hspace=0.3)
    
    # Price chart with trades
    ax_price = fig.add_subplot(gs[0])
    ax_price.plot(data.index, data["Close"], label='Close Price', color='black', linewidth=1.5)
    ax_price.set_title(f'{symbol} - MACD Strategy Backtest with Trade Entries/Exits', fontsize=14, fontweight='bold')
    ax_price.set_ylabel('Price (₹)', fontsize=11)
    ax_price.grid(True, alpha=0.3)
    
    # Plot all trades with annotations
    for idx, t in enumerate(trades):
        # Entry point (green triangle)
        ax_price.scatter(data.index[t['entry_idx']], t['entry_price'], 
                        marker='^', color='green', s=150, zorder=5, label='Entry' if idx == 0 else '')
        # Exit point (red triangle)
        ax_price.scatter(data.index[t['exit_idx']], t['exit_price'], 
                        marker='v', color='red', s=150, zorder=5, label='Exit' if idx == 0 else '')
        
        # Draw line connecting entry to exit
        ax_price.plot([data.index[t['entry_idx']], data.index[t['exit_idx']]], 
                     [t['entry_price'], t['exit_price']], 
                     color='green' if t['pnl'] > 0 else 'red', 
                     alpha=0.5, linewidth=1, linestyle='--')
        
        # Color code: green for profit, red for loss
        if t['pnl'] > 0:
            ax_price.annotate(f"W: +₹{t['pnl']:.0f}", 
                            xy=(data.index[t['exit_idx']], t['exit_price']),
                            xytext=(5, 5), textcoords='offset points',
                            fontsize=8, color='green', fontweight='bold')
        else:
            ax_price.annotate(f"L: ₹{t['pnl']:.0f}", 
                            xy=(data.index[t['exit_idx']], t['exit_price']),
                            xytext=(5, -10), textcoords='offset points',
                            fontsize=8, color='red', fontweight='bold')
    
    ax_price.legend(loc='upper left', fontsize=10)
    
    # MACD Line and Signal
    ax_macd = fig.add_subplot(gs[1])
    ax_macd.plot(data.index, macd_line, label='MACD Line', color='blue', linewidth=1.5)
    ax_macd.plot(data.index, macd_signal, label='Signal Line', color='red', linewidth=1.5)
    ax_macd.axhline(0, color='black', linewidth=0.8, linestyle='-', alpha=0.5)
    ax_macd.fill_between(data.index, macd_line, macd_signal, 
                         where=(macd_line >= macd_signal), color='green', alpha=0.2, label='Bullish')
    ax_macd.fill_between(data.index, macd_line, macd_signal, 
                         where=(macd_line < macd_signal), color='red', alpha=0.2, label='Bearish')
    ax_macd.set_ylabel('MACD Value', fontsize=11)
    ax_macd.set_title('MACD Indicator', fontsize=12, fontweight='bold')
    ax_macd.grid(True, alpha=0.3)
    ax_macd.legend(loc='upper left', fontsize=9)
    
    # MACD Histogram
    ax_hist = fig.add_subplot(gs[2])
    colors = ['green' if h > 0 else 'red' for h in macd_hist]
    ax_hist.bar(data.index, macd_hist, color=colors, alpha=0.6, width=0.01)
    ax_hist.axhline(0, color='black', linewidth=0.8)
    ax_hist.set_ylabel('Histogram', fontsize=11)
    ax_hist.set_xlabel('Time', fontsize=11)
    ax_hist.set_title('MACD Histogram (Momentum)', fontsize=12, fontweight='bold')
    ax_hist.grid(True, alpha=0.3)
    
    # Format x-axis
    ax_price.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate(rotation=45, ha='right')
    
    # Save to base64
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def generate_html_report(symbol, trades_df, details, chart_b64):
    """Generate HTML report with embedded chart"""
    total_trades = len(trades_df)
    wins = len(trades_df[trades_df['pnl'] > 0])
    losses = len(trades_df[trades_df['pnl'] < 0])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    total_pnl = trades_df['pnl'].sum()
    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if wins > 0 else 0
    avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if losses > 0 else 0
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>MACD Strategy Report - {symbol}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 20px;
            }}
            .container {{ 
                max-width: 1400px; 
                margin: 0 auto;
                background: white;
                border-radius: 10px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{ font-size: 28px; margin-bottom: 5px; }}
            .header p {{ font-size: 14px; opacity: 0.9; }}
            .content {{ padding: 30px; }}
            .metrics-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            .metric-card {{
                background: #f8f9fa;
                border-left: 4px solid #667eea;
                padding: 20px;
                border-radius: 5px;
                text-align: center;
            }}
            .metric-card.win {{ border-left-color: #28a745; }}
            .metric-card.loss {{ border-left-color: #dc3545; }}
            .metric-value {{
                font-size: 24px;
                font-weight: bold;
                color: #333;
                margin-bottom: 5px;
            }}
            .metric-label {{
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
            }}
            .chart-container {{
                margin: 30px 0;
                text-align: center;
            }}
            .chart-container img {{
                width: 100%;
                height: auto;
                border-radius: 5px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }}
            h2 {{
                color: #333;
                margin: 30px 0 15px 0;
                border-bottom: 2px solid #667eea;
                padding-bottom: 10px;
                font-size: 18px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
                font-size: 13px;
            }}
            th {{
                background: #667eea;
                color: white;
                padding: 12px;
                text-align: left;
                font-weight: 600;
            }}
            td {{
                padding: 10px 12px;
                border-bottom: 1px solid #eee;
            }}
            tr:hover {{ background: #f8f9fa; }}
            tr.win-trade td:first-child::before {{ content: '✓ '; color: #28a745; font-weight: bold; }}
            tr.loss-trade td:first-child::before {{ content: '✗ '; color: #dc3545; font-weight: bold; }}
            .footer {{
                text-align: center;
                color: #666;
                font-size: 12px;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #eee;
            }}
            .stats-row {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 MACD Strategy Backtest Report</h1>
                <p><strong>{symbol}</strong> | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="content">
                <h2>Performance Summary</h2>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-value">{total_trades}</div>
                        <div class="metric-label">Total Trades</div>
                    </div>
                    <div class="metric-card win">
                        <div class="metric-value">{win_rate:.2f}%</div>
                        <div class="metric-label">Win Rate</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">₹{total_pnl:,.0f}</div>
                        <div class="metric-label">Total P&L</div>
                    </div>
                    <div class="metric-card win">
                        <div class="metric-value">{wins}</div>
                        <div class="metric-label">Winning Trades</div>
                    </div>
                    <div class="metric-card loss">
                        <div class="metric-value">{losses}</div>
                        <div class="metric-label">Losing Trades</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">₹{avg_win:,.0f}</div>
                        <div class="metric-label">Avg Win</div>
                    </div>
                </div>

                <h2>Trade Analysis Chart</h2>
                <div class="chart-container">
                    <img src="data:image/png;base64,{chart_b64}" alt="MACD Chart with Trades">
                </div>

                <h2>Trade Details (Last 30 Trades)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Entry Date</th>
                            <th>Exit Date</th>
                            <th>Entry Price</th>
                            <th>Exit Price</th>
                            <th>P&L (₹)</th>
                            <th>Return %</th>
                        </tr>
                    </thead>
                    <tbody>
    """
    
    # Add trade rows
    for _, trade in details.tail(30).iterrows():
        pnl = trade['PnL']
        row_class = 'win-trade' if pnl > 0 else 'loss-trade'
        return_pct = ((trade['Sell'] - trade['Buy']) / trade['Buy'] * 100)
        html += f"""
                        <tr class="{row_class}">
                            <td>{trade['Entry'].strftime('%Y-%m-%d %H:%M')}</td>
                            <td>{trade['Exit'].strftime('%Y-%m-%d %H:%M')}</td>
                            <td>₹{trade['Buy']:,.2f}</td>
                            <td>₹{trade['Sell']:,.2f}</td>
                            <td style="color: {'green' if pnl > 0 else 'red'}; font-weight: bold;">₹{pnl:,.2f}</td>
                            <td style="color: {'green' if return_pct > 0 else 'red'}; font-weight: bold;">{return_pct:.2f}%</td>
                        </tr>
        """
    
    html += f"""
                    </tbody>
                </table>

                <div class="footer">
                    <p>MACD Parameters: Fast=12, Slow=26, Signal=9</p>
                    <p>Strategy: Bullish Crossover + Histogram Above Zero + Histogram Rising</p>
                    <p>Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html


# =========================
# MAIN: Run if executed directly
# =========================

if __name__ == "__main__":
    # example: load mock data with 1D timeframe (daily)
    # 5 years of daily data = ~1250 trading days
    dates = pd.date_range(start='2020-01-01', periods=1250, freq='D')
    
    # Generate realistic daily OHLC data (using Close for simplicity)
    np.random.seed(42)
    close_prices = 5500 + np.cumsum(np.random.randn(1250) * 50)  # random walk
    
    data = pd.DataFrame({
        'Close': close_prices
    }, index=dates)
    
    run_backtest_with_report(data, symbol="CRUDE")
