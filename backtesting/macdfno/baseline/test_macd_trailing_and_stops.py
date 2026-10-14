import sys, os
from pathlib import Path
import pandas as pd
import numpy as np

DATA_DIR = Path("/Users/mac/Desktop/openalgo/backtesting/emacrossopen/data")
parquet_files = sorted(list(DATA_DIR.glob("*_1h.parquet")))

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return macd, sig, hist

data_map = {}
for p in parquet_files:
    sym = p.name.replace("_1h.parquet", "")
    df = pd.read_parquet(p)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)
    df.sort_index(inplace=True)
    df["Close"] = df["Close"].astype(float)
    df["High"] = df["High"].astype(float)
    df["Low"] = df["Low"].astype(float)
    
    macd, sig, hist = calculate_macd(df["Close"])
    df["macd"] = macd
    df["sig"] = sig
    df["hist"] = hist
    df["ema26"] = df["Close"].ewm(span=26, adjust=False).mean()
    df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
    data_map[sym] = df

def test_engine(
    long_tp=0.0,      # 0.0 = pure indicator cross exit (no fixed TP)
    short_tp=0.0,
    sl_pct=6.0,       # 6.0% catastrophe SL
    trail_runner=False,
    trail_pct=0.35,
    min_expansion_pts=0.0, # Delta Hist
    zero_line_filter=False, # MACD line > 0 for Longs, < 0 for Shorts
    friction_pct=0.07,
):
    all_trades = []
    
    for sym, df in data_map.items():
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        macd = df["macd"]
        sig = df["sig"]
        hist = df["hist"]
        
        current_pos = 0
        entry_price = 0.0
        entry_bar_idx = 0
        entry_time = None
        
        runner_active = False
        peak_px = 0.0
        trough_px = 999999.0
        
        n = len(df)
        for i in range(2, n):
            ts = df.index[i]
            c_close = close.iloc[i]
            c_high = high.iloc[i]
            c_low = low.iloc[i]
            
            # Active trade management
            if current_pos != 0:
                exit_reason = None
                exit_price = 0.0
                
                # Check Catastrophe SL
                if current_pos == 1:
                    cat_sl = entry_price * (1.0 - sl_pct / 100.0)
                    if c_low <= cat_sl:
                        exit_reason = "CATASTROPHE_SL"
                        exit_price = cat_sl
                    elif long_tp > 0:
                        target_px = entry_price * (1.0 + long_tp / 100.0)
                        if not runner_active:
                            if c_high >= target_px:
                                if trail_runner:
                                    runner_active = True
                                    peak_px = max(c_high, target_px)
                                else:
                                    exit_reason = "TARGET_HIT"
                                    exit_price = target_px
                        else:
                            peak_px = max(peak_px, c_high)
                            trail_sl = peak_px * (1.0 - trail_pct / 100.0)
                            if c_low <= trail_sl:
                                exit_reason = "RUNNER_TRAIL"
                                exit_price = trail_sl
                elif current_pos == -1:
                    cat_sl = entry_price * (1.0 + sl_pct / 100.0)
                    if c_high >= cat_sl:
                        exit_reason = "CATASTROPHE_SL"
                        exit_price = cat_sl
                    elif short_tp > 0:
                        target_px = entry_price * (1.0 - short_tp / 100.0)
                        if not runner_active:
                            if c_low <= target_px:
                                if trail_runner:
                                    runner_active = True
                                    trough_px = min(c_low, target_px)
                                else:
                                    exit_reason = "TARGET_HIT"
                                    exit_price = target_px
                        else:
                            trough_px = min(trough_px, c_low)
                            trail_sl = trough_px * (1.0 + trail_pct / 100.0)
                            if c_high >= trail_sl:
                                exit_reason = "RUNNER_TRAIL"
                                exit_price = trail_sl
                                
                if exit_reason:
                    dir_mult = 1.0 if current_pos == 1 else -1.0
                    gross_pnl = ((exit_price - entry_price) / entry_price) * 100.0 * dir_mult
                    all_trades.append({
                        "symbol": sym,
                        "direction": current_pos,
                        "exit_time": ts,
                        "net_pnl_pct": gross_pnl - friction_pct,
                    })
                    current_pos = 0
                    entry_price = 0.0
                    runner_active = False
                    continue
                    
            # Fresh signal
            prev_macd, prev_sig = macd.iloc[i-1], sig.iloc[i-1]
            c_macd, c_sig = macd.iloc[i], sig.iloc[i]
            p2_h, p_h, c_h = hist.iloc[i-2], hist.iloc[i-1], hist.iloc[i]
            
            bull_exp = (c_h > p_h) and (p_h > p2_h)
            bear_exp = (c_h < p_h) and (p_h < p2_h)
            
            if min_expansion_pts > 0:
                if (c_h - p_h) < min_expansion_pts:
                    bull_exp = False
                if (p_h - c_h) < min_expansion_pts:
                    bear_exp = False
                    
            is_bullish = (prev_macd <= prev_sig) and (c_macd > c_sig) and bull_exp
            is_bearish = (prev_macd >= prev_sig) and (c_macd < c_sig) and bear_exp
            
            if zero_line_filter:
                if is_bullish and c_macd < 0:
                    is_bullish = False
                if is_bearish and c_macd > 0:
                    is_bearish = False
                    
            if is_bullish:
                if current_pos == -1:
                    gross_pnl = ((c_close - entry_price) / entry_price) * 100.0 * (-1.0)
                    all_trades.append({
                        "symbol": sym,
                        "direction": -1,
                        "exit_time": ts,
                        "net_pnl_pct": gross_pnl - friction_pct,
                    })
                current_pos = 1
                entry_price = c_close
                runner_active = False
            elif is_bearish:
                if current_pos == 1:
                    gross_pnl = ((c_close - entry_price) / entry_price) * 100.0 * (1.0)
                    all_trades.append({
                        "symbol": sym,
                        "direction": 1,
                        "exit_time": ts,
                        "net_pnl_pct": gross_pnl - friction_pct,
                    })
                current_pos = -1
                entry_price = c_close
                runner_active = False
                
    df_t = pd.DataFrame(all_trades)
    if df_t.empty:
        return 0, 0.0, 0.0, 0.0
    pnls = df_t["net_pnl_pct"].values
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    pf = np.sum(wins) / abs(np.sum(losses)) if len(losses) else 999.0
    net = np.sum(pnls)
    
    # 2026 Holdout
    t_2026 = df_t[df_t['exit_time'] >= '2026-01-01']
    if not t_2026.empty:
        p_26 = t_2026['net_pnl_pct'].values
        w_26 = p_26[p_26 > 0]
        l_26 = p_26[p_26 < 0]
        pf_26 = np.sum(w_26) / abs(np.sum(l_26)) if len(l_26) else 999.0
    else:
        pf_26 = 0.0
    return len(df_t), net, pf, pf_26

print(f"{'Variant':<45} | {'Trades':<6} | {'Net%':<8} | {'PF':<6} | {'2026_PF':<7}")
print("-" * 80)

# Test 1: Pure Indicator Cross (No target, No SL)
n, net, pf, pf26 = test_engine(long_tp=0.0, short_tp=0.0, sl_pct=99.0)
print(f"{'1. Pure MACD Cross (No Fixed TP / No SL)':<45} | {n:<6} | {net:>7.2f}% | {pf:>6.3f} | {pf26:>6.3f}")

# Test 2: Catastrophe SL Only (-6.0%)
n, net, pf, pf26 = test_engine(long_tp=0.0, short_tp=0.0, sl_pct=6.0)
print(f"{'2. MACD Cross + 6.0% Catastrophe SL':<45} | {n:<6} | {net:>7.2f}% | {pf:>6.3f} | {pf26:>6.3f}")

# Test 3: Fixed Targets (+3.0% / +1.5%) + 6.0% SL
n, net, pf, pf26 = test_engine(long_tp=3.0, short_tp=1.5, sl_pct=6.0)
print(f"{'3. Fixed Targets (3%/1.5%) + 6.0% SL':<45} | {n:<6} | {net:>7.2f}% | {pf:>6.3f} | {pf26:>6.3f}")

# Test 4: Fixed Targets + 0.35% Runner + 6.0% SL
n, net, pf, pf26 = test_engine(long_tp=3.0, short_tp=1.5, sl_pct=6.0, trail_runner=True, trail_pct=0.35)
print(f"{'4. Target + 0.35% Runner + 6.0% SL':<45} | {n:<6} | {net:>7.2f}% | {pf:>6.3f} | {pf26:>6.3f}")

# Test 5: Zero-Line Filter (Trade only with macro momentum)
n, net, pf, pf26 = test_engine(long_tp=3.0, short_tp=1.5, sl_pct=6.0, zero_line_filter=True)
print(f"{'5. Zero-Line Regime + Fixed Targets + 6% SL':<45} | {n:<6} | {net:>7.2f}% | {pf:>6.3f} | {pf26:>6.3f}")
