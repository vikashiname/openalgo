import sys, os, glob
import pandas as pd
import numpy as np

DATA_DIR = "/Users/mac/Desktop/openalgo/backtesting/data"
parquet_files = sorted(glob.glob(os.path.join(DATA_DIR, "*_1H.parquet")))

print(f"Total parquet files located: {len(parquet_files)}")

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return macd, sig, hist

def backtest_macdfno_baseline(
    df,
    symbol,
    long_tp=3.0,
    short_tp=1.5,
    sl_pct=3.5,
    delta_hist_threshold=0.0,
    use_regime=False,
    use_time_filter=False,
    friction_pct=0.07,
):
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)
    df.sort_index(inplace=True)
    
    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    
    macd, sig, hist = calculate_macd(close)
    
    # Optional 50 EMA regime
    ema50 = close.ewm(span=50, adjust=False).mean()
    
    trades = []
    current_pos = 0 # 1=LONG, -1=SHORT, 0=FLAT
    entry_price = 0.0
    entry_bar_idx = 0
    entry_time = None
    
    for i in range(2, len(df)):
        ts = df.index[i]
        curr_close = close.iloc[i]
        curr_high = high.iloc[i]
        curr_low = low.iloc[i]
        
        # 1. Manage active position exits (TARGET / SL)
        if current_pos != 0:
            exit_reason = None
            exit_price = 0.0
            
            if current_pos == 1: # LONG
                target_px = entry_price * (1.0 + long_tp / 100.0)
                sl_px = entry_price * (1.0 - sl_pct / 100.0)
                
                # Check catastrophic SL first, then target
                if curr_low <= sl_px:
                    exit_reason = "CATASTROPHE_SL"
                    exit_price = sl_px
                elif curr_high >= target_px:
                    exit_reason = "TARGET_HIT"
                    exit_price = target_px
            elif current_pos == -1: # SHORT
                target_px = entry_price * (1.0 - short_tp / 100.0)
                sl_px = entry_price * (1.0 + sl_pct / 100.0)
                
                if curr_high >= sl_px:
                    exit_reason = "CATASTROPHE_SL"
                    exit_price = sl_px
                elif curr_low <= target_px:
                    exit_reason = "TARGET_HIT"
                    exit_price = target_px
                    
            if exit_reason:
                dir_mult = 1.0 if current_pos == 1 else -1.0
                gross_pnl = ((exit_price - entry_price) / entry_price) * 100.0 * dir_mult
                net_pnl = gross_pnl - friction_pct
                
                trades.append({
                    "symbol": symbol,
                    "direction": current_pos,
                    "entry_time": entry_time,
                    "exit_time": ts,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "bars_held": i - entry_bar_idx,
                    "gross_pnl_pct": gross_pnl,
                    "net_pnl_pct": net_pnl,
                })
                current_pos = 0
                entry_price = 0.0
                continue
                
        # 2. Evaluate fresh signal strictly on completed bars (prev vs curr)
        # In live macdfno: evaluates on completed bar i-1, executes next bar
        prev_macd, prev_sig = macd.iloc[i-1], sig.iloc[i-1]
        c_macd, c_sig = macd.iloc[i], sig.iloc[i]
        p2_h, p_h, c_h = hist.iloc[i-2], hist.iloc[i-1], hist.iloc[i]
        
        # 2-bar histogram expansion
        bull_exp = (c_h > p_h) and (p_h > p2_h)
        bear_exp = (c_h < p_h) and (p_h < p2_h)
        
        # Momentum threshold check
        if delta_hist_threshold > 0:
            if not ((c_h - p_h) >= delta_hist_threshold):
                bull_exp = False
            if not ((p_h - c_h) >= delta_hist_threshold):
                bear_exp = False
                
        is_bullish = (prev_macd <= prev_sig) and (c_macd > c_sig) and bull_exp
        is_bearish = (prev_macd >= prev_sig) and (c_macd < c_sig) and bear_exp
        
        # Time filter
        if use_time_filter:
            m = ts.hour * 60 + ts.minute
            allowed = False
            if (9*60+45) <= m <= (10*60+55) or (12*60) <= m <= (13*60+15) or (15*60) <= m <= (15*60+20):
                allowed = True
            if not allowed:
                is_bullish = False
                is_bearish = False
                
        # Regime filter
        if use_regime:
            if is_bullish and curr_close < ema50.iloc[i]:
                is_bullish = False
                
        # Position Reversal / Entry
        if is_bullish:
            if current_pos == -1: # Close short first
                dir_mult = -1.0
                gross_pnl = ((curr_close - entry_price) / entry_price) * 100.0 * dir_mult
                net_pnl = gross_pnl - friction_pct
                trades.append({
                    "symbol": symbol,
                    "direction": -1,
                    "entry_time": entry_time,
                    "exit_time": ts,
                    "entry_price": entry_price,
                    "exit_price": curr_close,
                    "exit_reason": "REVERSAL",
                    "bars_held": i - entry_bar_idx,
                    "gross_pnl_pct": gross_pnl,
                    "net_pnl_pct": net_pnl,
                })
            current_pos = 1
            entry_price = curr_close
            entry_bar_idx = i
            entry_time = ts
        elif is_bearish:
            if current_pos == 1: # Close long first
                dir_mult = 1.0
                gross_pnl = ((curr_close - entry_price) / entry_price) * 100.0 * dir_mult
                net_pnl = gross_pnl - friction_pct
                trades.append({
                    "symbol": symbol,
                    "direction": 1,
                    "entry_time": entry_time,
                    "exit_time": ts,
                    "entry_price": entry_price,
                    "exit_price": curr_close,
                    "exit_reason": "REVERSAL",
                    "bars_held": i - entry_bar_idx,
                    "gross_pnl_pct": gross_pnl,
                    "net_pnl_pct": net_pnl,
                })
            current_pos = -1
            entry_price = curr_close
            entry_bar_idx = i
            entry_time = ts
            
    return trades

print("Macdfno baseline auditor compiled cleanly.")
