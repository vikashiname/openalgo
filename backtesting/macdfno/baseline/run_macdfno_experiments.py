import sys, os, glob
from pathlib import Path
import pandas as pd
import numpy as np

DATA_DIR = Path("/Users/mac/Desktop/openalgo/backtesting/emacrossopen/data")
parquet_files = sorted(list(DATA_DIR.glob("*_1h.parquet")))
print(f"Total 1H parquet datasets: {len(parquet_files)}")

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return macd, sig, hist

# Load datasets into memory
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
    df["Open"] = df["Open"].astype(float)
    
    # Calculate indicators once
    macd, sig, hist = calculate_macd(df["Close"])
    df["macd"] = macd
    df["sig"] = sig
    df["hist"] = hist
    df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["ema26"] = df["Close"].ewm(span=26, adjust=False).mean()
    data_map[sym] = df

print(f"Successfully loaded {len(data_map)} symbol datasets into memory.")

def simulate_macdfno(
    data_map,
    long_tp=3.0,
    short_tp=1.5,
    sl_pct=3.5,
    delta_hist_threshold=0.0,
    use_regime=False,
    use_time_filter=False,
    use_asym_universe=False,
    friction_pct=0.07,
):
    TOP_LONGS = {'SUNPHARMA', 'BAJAJ-AUTO', 'BPCL', 'WIPRO', 'TATASTEEL', 'BAJFINANCE', 'NTPC'}
    TOP_SHORTS = {'SUNPHARMA', 'BAJAJ-AUTO', 'M&M', 'BPCL', 'NTPC', 'NIFTY'}
    
    all_trades = []
    
    for sym, df in data_map.items():
        if use_asym_universe:
            # We will filter on entry direction below
            pass
            
        current_pos = 0 # 1=LONG, -1=SHORT, 0=FLAT
        entry_price = 0.0
        entry_bar_idx = 0
        entry_time = None
        
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        macd = df["macd"]
        sig = df["sig"]
        hist = df["hist"]
        ema50 = df["ema50"]
        ema26 = df["ema26"]
        
        n_bars = len(df)
        
        for i in range(2, n_bars):
            ts = df.index[i]
            curr_close = close.iloc[i]
            curr_high = high.iloc[i]
            curr_low = low.iloc[i]
            
            # 1. Manage active position exits
            if current_pos != 0:
                exit_reason = None
                exit_price = 0.0
                
                if current_pos == 1:
                    target_px = entry_price * (1.0 + long_tp / 100.0)
                    sl_px = entry_price * (1.0 - sl_pct / 100.0)
                    if curr_low <= sl_px:
                        exit_reason = "CATASTROPHE_SL"
                        exit_price = sl_px
                    elif curr_high >= target_px:
                        exit_reason = "TARGET_HIT"
                        exit_price = target_px
                elif current_pos == -1:
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
                    all_trades.append({
                        "symbol": sym,
                        "direction": current_pos,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "exit_reason": exit_reason,
                        "bars_held": i - entry_bar_idx,
                        "net_pnl_pct": net_pnl,
                    })
                    current_pos = 0
                    entry_price = 0.0
                    continue
                    
            # 2. Evaluate fresh signal
            prev_macd, prev_sig = macd.iloc[i-1], sig.iloc[i-1]
            c_macd, c_sig = macd.iloc[i], sig.iloc[i]
            p2_h, p_h, c_h = hist.iloc[i-2], hist.iloc[i-1], hist.iloc[i]
            
            bull_exp = (c_h > p_h) and (p_h > p2_h)
            bear_exp = (c_h < p_h) and (p_h < p2_h)
            
            if delta_hist_threshold > 0:
                if (c_h - p_h) < delta_hist_threshold:
                    bull_exp = False
                if (p_h - c_h) < delta_hist_threshold:
                    bear_exp = False
                    
            is_bullish = (prev_macd <= prev_sig) and (c_macd > c_sig) and bull_exp
            is_bearish = (prev_macd >= prev_sig) and (c_macd < c_sig) and bear_exp
            
            if use_time_filter:
                m = ts.hour * 60 + ts.minute
                allowed = (9*60+45) <= m <= (10*60+55) or (12*60) <= m <= (13*60+15) or (15*60) <= m <= (15*60+20)
                if not allowed:
                    is_bullish = False
                    is_bearish = False
                    
            if use_regime:
                if is_bullish and curr_close < ema50.iloc[i]:
                    is_bullish = False
                if is_bearish and curr_close > ema26.iloc[i]:
                    is_bearish = False
                    
            if use_asym_universe:
                if is_bullish and sym not in TOP_LONGS:
                    is_bullish = False
                if is_bearish and sym not in TOP_SHORTS:
                    is_bearish = False
                    
            if is_bullish:
                if current_pos == -1:
                    gross_pnl = ((curr_close - entry_price) / entry_price) * 100.0 * (-1.0)
                    all_trades.append({
                        "symbol": sym,
                        "direction": -1,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": curr_close,
                        "exit_reason": "REVERSAL",
                        "bars_held": i - entry_bar_idx,
                        "net_pnl_pct": gross_pnl - friction_pct,
                    })
                current_pos = 1
                entry_price = curr_close
                entry_bar_idx = i
                entry_time = ts
            elif is_bearish:
                if current_pos == 1:
                    gross_pnl = ((curr_close - entry_price) / entry_price) * 100.0 * (1.0)
                    all_trades.append({
                        "symbol": sym,
                        "direction": 1,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": curr_close,
                        "exit_reason": "REVERSAL",
                        "bars_held": i - entry_bar_idx,
                        "net_pnl_pct": gross_pnl - friction_pct,
                    })
                current_pos = -1
                entry_price = curr_close
                entry_bar_idx = i
                entry_time = ts
                
    return pd.DataFrame(all_trades)

def summarize(df_trades):
    if df_trades.empty:
        return {'trades': 0, 'win_rate': 0.0, 'net_pnl': 0.0, 'pf': 0.0, 'max_dd': 0.0, 'holdout_pf': 0.0}
    df_trades = df_trades.copy()
    df_trades['exit_time'] = pd.to_datetime(df_trades['exit_time'], utc=True)
    df_trades.sort_values('exit_time', inplace=True)
    
    pnls = df_trades['net_pnl_pct'].values
    n = len(pnls)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    wr = len(wins) / n * 100.0
    net = float(np.sum(pnls))
    gross_win = float(np.sum(wins)) if len(wins) else 0.0
    gross_loss = float(abs(np.sum(losses))) if len(losses) else 0.0001
    pf = gross_win / gross_loss
    
    # Max DD
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    mdd = float(np.max(dd)) if len(dd) else 0.0
    
    # 2026 Holdout
    t_2026 = df_trades[df_trades['exit_time'] >= '2026-01-01']
    if not t_2026.empty:
        p_2026 = t_2026['net_pnl_pct'].values
        w_2026 = p_2026[p_2026 > 0]
        l_2026 = p_2026[p_2026 < 0]
        pf_2026 = float(np.sum(w_2026)) / float(abs(np.sum(l_2026))) if len(l_2026) and np.sum(l_2026) != 0 else (999.0 if len(w_2026) else 0.0)
    else:
        pf_2026 = 0.0
        
    return {
        'trades': n,
        'win_rate': wr,
        'net_pnl': net,
        'pf': pf,
        'max_dd': mdd,
        'holdout_pf': pf_2026
    }

# Run Experiment Grid
experiments = [
    ("MACD_EXP_A_Frozen_Baseline", 3.0, 1.5, 3.5, 0.0, False, False, False),
    ("MACD_EXP_B_Time_Filter_Only", 3.0, 1.5, 3.5, 0.0, False, True, False),
    ("MACD_EXP_C_Regime_EMA50_Only", 3.0, 1.5, 3.5, 0.0, True, False, False),
    ("MACD_EXP_D_Momentum_Gate_005", 3.0, 1.5, 3.5, 0.05, False, False, False),
    ("MACD_EXP_E_Momentum_Gate_010", 3.0, 1.5, 3.5, 0.10, False, False, False),
    ("MACD_EXP_F_Asym_Universe_Only", 3.0, 1.5, 3.5, 0.0, False, False, True),
    ("MACD_EXP_G_Asym_Universe_Plus_Time", 3.0, 1.5, 3.5, 0.0, False, True, True),
    ("MACD_EXP_H_Asym_Universe_Plus_Regime", 3.0, 1.5, 3.5, 0.0, True, False, True),
    ("MACD_EXP_I_Full_Synergy", 3.0, 1.5, 3.5, 0.05, True, True, True),
]

results = []
print("\n" + "="*80)
print(f"{'Experiment':<35} | {'N':<5} | {'Net%':<8} | {'PF':<6} | {'MaxDD%':<7} | {'2026_PF':<7}")
print("="*80)

for name, l_tp, s_tp, sl, d_h, reg, t_f, asym in experiments:
    df_t = simulate_macdfno(
        data_map,
        long_tp=l_tp,
        short_tp=s_tp,
        sl_pct=sl,
        delta_hist_threshold=d_h,
        use_regime=reg,
        use_time_filter=t_f,
        use_asym_universe=asym,
    )
    res = summarize(df_t)
    results.append({
        'experiment': name,
        **res
    })
    print(f"{name:<35} | {res['trades']:<5} | {res['net_pnl']:>7.2f}% | {res['pf']:>6.3f} | {res['max_dd']:>6.2f}% | {res['holdout_pf']:>6.3f}")

df_matrix = pd.DataFrame(results)
out_csv = "/Users/mac/Desktop/openalgo/backtesting/runs/run_20261012_macdfno_opt/MACDFNO_EXPERIMENT_MATRIX.csv"
df_matrix.to_csv(out_csv, index=False)
print(f"\nSaved macdfno experiment matrix to {out_csv}")
