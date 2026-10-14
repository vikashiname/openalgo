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
    data_map[sym] = df

# Test trailing distances and universe filtering on macdfno
TOP_LONGS = {'SUNPHARMA', 'BAJAJ-AUTO', 'BPCL', 'WIPRO', 'TATASTEEL', 'BAJFINANCE', 'NTPC'}
TOP_SHORTS = {'SUNPHARMA', 'BAJAJ-AUTO', 'M&M', 'BPCL', 'NTPC', 'NIFTY'}

def test_engine_variant(
    long_tp=3.0,
    short_tp=1.5,
    trail_pct=0.35,
    sl_pct=6.0,
    conservative_trailing=True, # Lookahead-free (subsequent bar)
    use_asym_universe=False,
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
            
            # 1. Manage Active Position
            if current_pos != 0:
                exit_reason = None
                exit_price = 0.0
                
                if current_pos == 1:
                    cat_sl = entry_price * (1.0 - sl_pct / 100.0)
                    if c_low <= cat_sl:
                        exit_reason = "CATASTROPHE_SL"
                        exit_price = cat_sl
                    elif not runner_active:
                        target_px = entry_price * (1.0 + long_tp / 100.0)
                        if c_high >= target_px:
                            runner_active = True
                            peak_px = max(c_high, target_px)
                            if not conservative_trailing:
                                trail_sl = peak_px * (1.0 - trail_pct / 100.0)
                                if c_low <= trail_sl:
                                    exit_reason = "RUNNER_TRAIL"
                                    exit_price = trail_sl
                    else: # Runner already active on previous candle
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
                    elif not runner_active:
                        target_px = entry_price * (1.0 - short_tp / 100.0)
                        if c_low <= target_px:
                            runner_active = True
                            trough_px = min(c_low, target_px)
                            if not conservative_trailing:
                                trail_sl = trough_px * (1.0 + trail_pct / 100.0)
                                if c_high >= trail_sl:
                                    exit_reason = "RUNNER_TRAIL"
                                    exit_price = trail_sl
                    else: # Runner already active on previous candle
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
                    
            # 2. Fresh Signal
            prev_macd, prev_sig = macd.iloc[i-1], sig.iloc[i-1]
            c_macd, c_sig = macd.iloc[i], sig.iloc[i]
            p2_h, p_h, c_h = hist.iloc[i-2], hist.iloc[i-1], hist.iloc[i]
            
            bull_exp = (c_h > p_h) and (p_h > p2_h)
            bear_exp = (c_h < p_h) and (p_h < p2_h)
            
            is_bullish = (prev_macd <= prev_sig) and (c_macd > c_sig) and bull_exp
            is_bearish = (prev_macd >= prev_sig) and (c_macd < c_sig) and bear_exp
            
            if use_asym_universe:
                if is_bullish and sym not in TOP_LONGS:
                    is_bullish = False
                if is_bearish and sym not in TOP_SHORTS:
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
        return 0, 0.0, 0.0, 0.0, 0.0
    df_t.sort_values("exit_time", inplace=True)
    pnls = df_t["net_pnl_pct"].values
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    pf = np.sum(wins) / abs(np.sum(losses)) if len(losses) else 999.0
    net = np.sum(pnls)
    
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    mdd = np.max(peak - cum) if len(cum) else 0.0
    
    t_2026 = df_t[df_t['exit_time'] >= '2026-01-01']
    if not t_2026.empty:
        p_26 = t_2026['net_pnl_pct'].values
        w_26 = p_26[p_26 > 0]
        l_26 = p_26[p_26 < 0]
        pf_26 = np.sum(w_26) / abs(np.sum(l_26)) if len(l_26) else 999.0
    else:
        pf_26 = 0.0
    return len(df_t), net, pf, mdd, pf_26

print(f"{'Variant':<50} | {'Trades':<6} | {'Net%':<9} | {'PF':<6} | {'MaxDD%':<7} | {'2026_PF':<7}")
print("=" * 95)

configs = [
    ("A. Target+Runner 0.35% (All 33 symbols, Intrabar)", 3.0, 1.5, 0.35, False, False),
    ("B. Target+Runner 0.35% (All 33 symbols, Lookahead-Free)", 3.0, 1.5, 0.35, True, False),
    ("C. Target+Runner 0.50% (All 33 symbols, Lookahead-Free)", 3.0, 1.5, 0.50, True, False),
    ("D. Target+Runner 0.75% (All 33 symbols, Lookahead-Free)", 3.0, 1.5, 0.75, True, False),
    ("E. Asymmetric Universe + Target/Runner 0.35%", 3.0, 1.5, 0.35, True, True),
    ("F. Asymmetric Universe + Target/Runner 0.50%", 3.0, 1.5, 0.50, True, True),
    ("G. Asymmetric Universe + Pure MACD Cross (No Fixed TP)", 0.0, 0.0, 0.35, True, True),
]

for label, l_tp, s_tp, tr, cons, asym in configs:
    n, net, pf, mdd, pf26 = test_engine_variant(
        long_tp=l_tp, short_tp=s_tp, trail_pct=tr, conservative_trailing=cons, use_asym_universe=asym
    )
    print(f"{label:<50} | {n:<6} | {net:>8.2f}% | {pf:>6.3f} | {mdd:>6.2f}% | {pf26:>6.3f}")
