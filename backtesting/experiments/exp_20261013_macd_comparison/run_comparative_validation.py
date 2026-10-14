"""
Comparative Validation Engine for 4 Independent Strategy Candidates
Location: backtesting/experiments/exp_20261013_macd_comparison/run_comparative_validation.py

Candidates:
  1. MACD_FNO_V1 Baseline (macdfno.py: MACD 12/26/9 + 2-bar hist expansion, 3% Long TP / 1.5% Short TP / 3.5% SL, reversal exit)
  2. EMA_MACD_V2_2 (EMA 9/26 + MACD 12/26/9 sequential confirmation <= 2 bars, 3% Long TP / 1.5% Short TP / 6.0% SL, reversal exit)
  3. Model B / Preset A (MACD 12/26/9 + 2-bar hist expansion, symmetric 1.5% TP / 1.5% SL, reversal fallback)
  4. Candidate E / Preset B (MACD 12/26/9 + 2-bar hist expansion, 3% Long TP / 1.5% Short TP / 3.5% SL, 0.35% HWM trailing runner, Asymmetric Universe)

Controlled Evaluation:
  - Dataset: 33 Liquid F&O Underlyings (1H candles, 2023-09 to 2026-09)
  - Common Subsets:
      * Common Universe: 33 Liquid Symbols
      * Core 15 Liquid Universe: ADANIENT, ADANIPORTS, ASIANPAINT, AXISBANK, BAJFINANCE, BHARTIARTL, EICHERMOT, HCLTECH, HEROMOTOCO, LT, M&M, NTPC, ONGC, TATASTEEL, ULTRACEMCO
      * Candidate E Native Universe: TOP_LONGS & TOP_SHORTS
  - Friction: Base 0.07%, Stress [0.05%, 0.10%, 0.12%, 0.15%]
  - In-Sample / Out-of-Sample Split: IS < 2025-07-01, OOS >= 2025-07-01, Holdout >= 2026-01-01
  - Lookahead-free / conservative intrabar trailing: trail active on subsequent bar or conservative same-bar.
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
import json
from typing import Dict, List, Any, Tuple, Optional

EXP_DIR = Path("/Users/mac/Desktop/openalgo/backtesting/experiments/exp_20261013_macd_comparison")
DATA_DIR = Path("/Users/mac/Desktop/openalgo/backtesting/emacrossopen/data")
LEDGER_DIR = EXP_DIR / "ledgers"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)

TOP_LONGS = {'SUNPHARMA', 'BAJAJ-AUTO', 'BPCL', 'WIPRO', 'TATASTEEL', 'BAJFINANCE', 'NTPC'}
TOP_SHORTS = {'SUNPHARMA', 'BAJAJ-AUTO', 'M&M', 'BPCL', 'NTPC', 'NIFTY'}

CORE_15_SYMBOLS = {
    'ADANIENT', 'ADANIPORTS', 'ASIANPAINT', 'AXISBANK', 'BAJFINANCE',
    'BHARTIARTL', 'EICHERMOT', 'HCLTECH', 'HEROMOTOCO', 'LT',
    'M&M', 'NTPC', 'ONGC', 'TATASTEEL', 'ULTRACEMCO'
}

IS_CUTOFF = pd.to_datetime("2025-07-01", utc=True)
HOLDOUT_CUTOFF = pd.to_datetime("2026-01-01", utc=True)

def load_data() -> Dict[str, pd.DataFrame]:
    parquet_files = sorted(list(DATA_DIR.glob("*_1h.parquet")))
    data_map = {}
    for p in parquet_files:
        sym = p.name.replace("_1h.parquet", "")
        df = pd.read_parquet(p)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)
        elif df.index.tz is None:
            df.index = df.index.tz_localize("Asia/Kolkata").tz_convert("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
            
        df.sort_index(inplace=True)
        df["Close"] = df["Close"].astype(float)
        df["High"] = df["High"].astype(float)
        df["Low"] = df["Low"].astype(float)
        df["Open"] = df["Open"].astype(float)
        
        # MACD (12, 26, 9)
        ema12 = df["Close"].ewm(span=12, adjust=False).mean()
        ema26 = df["Close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["sig"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["hist"] = df["macd"] - df["sig"]
        
        # EMA (9, 26, 50)
        df["ema9"] = df["Close"].ewm(span=9, adjust=False).mean()
        df["ema26"] = ema26
        df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
        
        data_map[sym] = df
    return data_map

def compute_metrics(trades: List[Dict[str, Any]], friction_pct: float = 0.07) -> Dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0, "long_trades": 0, "short_trades": 0,
            "net_pnl_pct": 0.0, "profit_factor": 0.0, "win_rate_pct": 0.0,
            "avg_win_pct": 0.0, "avg_loss_pct": 0.0, "expectancy_pct": 0.0,
            "max_drawdown_pct": 0.0, "is_pf": 0.0, "oos_pf": 0.0, "holdout_pf": 0.0,
            "is_trades": 0, "oos_trades": 0, "holdout_trades": 0
        }
        
    df_t = pd.DataFrame(trades)
    df_t.sort_values("exit_time", inplace=True)
    df_t["net_pnl_pct"] = df_t["gross_pnl_pct"] - friction_pct
    
    pnls = df_t["net_pnl_pct"].values
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    
    total_trades = len(df_t)
    long_trades = int((df_t["direction"] == 1).sum())
    short_trades = int((df_t["direction"] == -1).sum())
    
    win_rate = (len(wins) / total_trades) * 100.0 if total_trades > 0 else 0.0
    avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
    expectancy = float(np.mean(pnls)) if total_trades > 0 else 0.0
    
    gross_win_sum = float(np.sum(wins)) if len(wins) > 0 else 0.0
    gross_loss_sum = abs(float(np.sum(losses))) if len(losses) > 0 else 0.0
    pf = gross_win_sum / gross_loss_sum if gross_loss_sum > 0 else (999.0 if gross_win_sum > 0 else 0.0)
    net_pnl = float(np.sum(pnls))
    
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    mdd = float(np.max(peak - cum)) if len(cum) > 0 else 0.0
    
    # Sub-periods
    df_is = df_t[df_t["exit_time"] < IS_CUTOFF]
    df_oos = df_t[df_t["exit_time"] >= IS_CUTOFF]
    df_holdout = df_t[df_t["exit_time"] >= HOLDOUT_CUTOFF]
    
    def get_pf(sub_df):
        if sub_df.empty: return 0.0
        p = sub_df["net_pnl_pct"].values
        w = p[p > 0]
        l = p[p < 0]
        w_s = np.sum(w) if len(w) > 0 else 0.0
        l_s = abs(np.sum(l)) if len(l) > 0 else 0.0
        return float(w_s / l_s) if l_s > 0 else (999.0 if w_s > 0 else 0.0)

    return {
        "total_trades": total_trades,
        "long_trades": long_trades,
        "short_trades": short_trades,
        "net_pnl_pct": net_pnl,
        "profit_factor": pf,
        "win_rate_pct": win_rate,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "expectancy_pct": expectancy,
        "max_drawdown_pct": mdd,
        "is_trades": len(df_is),
        "is_pf": get_pf(df_is),
        "oos_trades": len(df_oos),
        "oos_pf": get_pf(df_oos),
        "holdout_trades": len(df_holdout),
        "holdout_pf": get_pf(df_holdout),
    }

# Candidate 1: MACD_FNO_V1 Baseline
def run_candidate_1_macdfno_baseline(data_map: Dict[str, pd.DataFrame], symbol_subset: Optional[set] = None) -> List[Dict[str, Any]]:
    trades = []
    long_tp = 3.0
    short_tp = 1.5
    sl_pct = 3.5
    
    for sym, df in data_map.items():
        if symbol_subset and sym not in symbol_subset:
            continue
            
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        macd = df["macd"]
        sig = df["sig"]
        hist = df["hist"]
        
        current_pos = 0
        entry_price = 0.0
        entry_time = None
        entry_bar = 0
        
        n = len(df)
        for i in range(2, n):
            ts = df.index[i]
            c_close = close.iloc[i]
            c_high = high.iloc[i]
            c_low = low.iloc[i]
            
            # Active Position Management
            if current_pos != 0:
                exit_reason = None
                exit_price = 0.0
                if current_pos == 1:
                    target_px = entry_price * (1.0 + long_tp / 100.0)
                    sl_px = entry_price * (1.0 - sl_pct / 100.0)
                    if c_low <= sl_px:
                        exit_reason = "CATASTROPHE_SL"
                        exit_price = sl_px
                    elif c_high >= target_px:
                        exit_reason = "TARGET_HIT"
                        exit_price = target_px
                elif current_pos == -1:
                    target_px = entry_price * (1.0 - short_tp / 100.0)
                    sl_px = entry_price * (1.0 + sl_pct / 100.0)
                    if c_high >= sl_px:
                        exit_reason = "CATASTROPHE_SL"
                        exit_price = sl_px
                    elif c_low <= target_px:
                        exit_reason = "TARGET_HIT"
                        exit_price = target_px
                        
                if exit_reason:
                    dir_mult = 1.0 if current_pos == 1 else -1.0
                    gross_pnl = ((exit_price - entry_price) / entry_price) * 100.0 * dir_mult
                    trades.append({
                        "symbol": sym,
                        "candidate": "MACD_FNO_V1",
                        "direction": current_pos,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "exit_reason": exit_reason,
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                    })
                    current_pos = 0
                    entry_price = 0.0
                    continue

            # Fresh Signal: MACD cross + 2-bar hist expansion
            prev_macd, prev_sig = macd.iloc[i-1], sig.iloc[i-1]
            c_macd, c_sig = macd.iloc[i], sig.iloc[i]
            p2_h, p_h, c_h = hist.iloc[i-2], hist.iloc[i-1], hist.iloc[i]
            
            bull_exp = (c_h > p_h) and (p_h > p2_h)
            bear_exp = (c_h < p_h) and (p_h < p2_h)
            
            is_bullish = (prev_macd <= prev_sig) and (c_macd > c_sig) and bull_exp
            is_bearish = (prev_macd >= prev_sig) and (c_macd < c_sig) and bear_exp
            
            if is_bullish:
                if current_pos == -1:
                    gross_pnl = ((c_close - entry_price) / entry_price) * 100.0 * (-1.0)
                    trades.append({
                        "symbol": sym,
                        "candidate": "MACD_FNO_V1",
                        "direction": -1,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": c_close,
                        "exit_reason": "REVERSAL",
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                    })
                current_pos = 1
                entry_price = c_close
                entry_time = ts
                entry_bar = i
            elif is_bearish:
                if current_pos == 1:
                    gross_pnl = ((c_close - entry_price) / entry_price) * 100.0 * (1.0)
                    trades.append({
                        "symbol": sym,
                        "candidate": "MACD_FNO_V1",
                        "direction": 1,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": c_close,
                        "exit_reason": "REVERSAL",
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                    })
                current_pos = -1
                entry_price = c_close
                entry_time = ts
                entry_bar = i
                
    return trades

# Candidate 2: EMA_MACD_V2_2 (Sequential confirmation within 2 bars)
def run_candidate_2_ema_macd_v2_2(data_map: Dict[str, pd.DataFrame], symbol_subset: Optional[set] = None) -> List[Dict[str, Any]]:
    trades = []
    long_tp = 3.0
    short_tp = 1.5
    sl_pct = 6.0
    
    for sym, df in data_map.items():
        if symbol_subset and sym not in symbol_subset:
            continue
            
        n = len(df)
        close = df["Close"].values
        open_px = df["Open"].values
        high_px = df["High"].values
        low_px = df["Low"].values
        ema9 = df["ema9"].values
        ema26 = df["ema26"].values
        macd = df["macd"].values
        sig = df["sig"].values
        times = df.index
        
        current_pos = 0
        entry_price = 0.0
        entry_time = None
        entry_bar = 0
        active_pending = None
        
        for i in range(1, n - 1):
            ts = times[i]
            c_high = high_px[i]
            c_low = low_px[i]
            c_close = close[i]
            
            # Active Position Management
            if current_pos != 0:
                exit_reason = None
                exit_price = 0.0
                if current_pos == 1:
                    target_px = entry_price * (1.0 + long_tp / 100.0)
                    sl_px = entry_price * (1.0 - sl_pct / 100.0)
                    if c_low <= sl_px:
                        exit_reason = "CATASTROPHE_SL"
                        exit_price = sl_px
                    elif c_high >= target_px:
                        exit_reason = "TARGET_HIT"
                        exit_price = target_px
                elif current_pos == -1:
                    target_px = entry_price * (1.0 - short_tp / 100.0)
                    sl_px = entry_price * (1.0 + sl_pct / 100.0)
                    if c_high >= sl_px:
                        exit_reason = "CATASTROPHE_SL"
                        exit_price = sl_px
                    elif c_low <= target_px:
                        exit_reason = "TARGET_HIT"
                        exit_price = target_px
                        
                if exit_reason:
                    dir_mult = 1.0 if current_pos == 1 else -1.0
                    gross_pnl = ((exit_price - entry_price) / entry_price) * 100.0 * dir_mult
                    trades.append({
                        "symbol": sym,
                        "candidate": "EMA_MACD_V2_2",
                        "direction": current_pos,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "exit_reason": exit_reason,
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                    })
                    current_pos = 0
                    entry_price = 0.0
                    continue
                    
            # Fresh Signal Evaluation (V2-2 Sequential Confirmation)
            curr_ema9, prev_ema9 = ema9[i], ema9[i-1]
            curr_ema26, prev_ema26 = ema26[i], ema26[i-1]
            curr_macd, prev_macd = macd[i], macd[i-1]
            curr_sig, prev_sig = sig[i], sig[i-1]
            
            ema_cross_up = (prev_ema9 <= prev_ema26) and (curr_ema9 > curr_ema26)
            ema_cross_down = (prev_ema9 >= prev_ema26) and (curr_ema9 < curr_ema26)
            macd_cross_up = (prev_macd <= prev_sig) and (curr_macd > curr_sig)
            macd_cross_down = (prev_macd >= prev_sig) and (curr_macd < curr_sig)
            
            new_sig = None
            if ema_cross_up and macd_cross_up:
                new_sig = "BUY"
                active_pending = None
            elif ema_cross_down and macd_cross_down:
                new_sig = "SELL"
                active_pending = None
            elif active_pending is not None:
                active_pending["elapsed_bars"] += 1
                if active_pending["direction"] == "LONG":
                    if (active_pending["leading"] == "EMA" and curr_ema9 < curr_ema26) or \
                       (active_pending["leading"] == "MACD" and curr_macd < curr_sig):
                        active_pending = None
                    elif active_pending["elapsed_bars"] <= 2:
                        if active_pending["leading"] == "EMA" and macd_cross_up:
                            new_sig = "BUY"
                            active_pending = None
                        elif active_pending["leading"] == "MACD" and ema_cross_up:
                            new_sig = "BUY"
                            active_pending = None
                    else:
                        active_pending = None
                elif active_pending["direction"] == "SHORT":
                    if active_pending["leading"] == "MACD" and curr_macd > curr_sig:
                        active_pending = None
                    elif active_pending["elapsed_bars"] <= 2:
                        if active_pending["leading"] == "MACD" and ema_cross_down:
                            new_sig = "SELL"
                            active_pending = None
                    else:
                        active_pending = None
                        
            if new_sig is None and active_pending is None:
                if ema_cross_up and not macd_cross_up:
                    active_pending = {"direction": "LONG", "leading": "EMA", "elapsed_bars": 0}
                elif macd_cross_up and not ema_cross_up:
                    active_pending = {"direction": "LONG", "leading": "MACD", "elapsed_bars": 0}
                elif macd_cross_down and not ema_cross_down:
                    active_pending = {"direction": "SHORT", "leading": "MACD", "elapsed_bars": 0}
                    
            if new_sig is not None:
                # Enter at next bar open
                next_open = open_px[i+1]
                next_time = times[i+1]
                if new_sig == "BUY":
                    if current_pos == -1:
                        gross_pnl = ((next_open - entry_price) / entry_price) * 100.0 * (-1.0)
                        trades.append({
                            "symbol": sym,
                            "candidate": "EMA_MACD_V2_2",
                            "direction": -1,
                            "entry_time": entry_time,
                            "exit_time": next_time,
                            "entry_price": entry_price,
                            "exit_price": next_open,
                            "exit_reason": "REVERSAL",
                            "bars_held": (i + 1) - entry_bar,
                            "gross_pnl_pct": gross_pnl,
                        })
                    current_pos = 1
                    entry_price = next_open
                    entry_time = next_time
                    entry_bar = i + 1
                elif new_sig == "SELL":
                    if current_pos == 1:
                        gross_pnl = ((next_open - entry_price) / entry_price) * 100.0 * (1.0)
                        trades.append({
                            "symbol": sym,
                            "candidate": "EMA_MACD_V2_2",
                            "direction": 1,
                            "entry_time": entry_time,
                            "exit_time": next_time,
                            "entry_price": entry_price,
                            "exit_price": next_open,
                            "exit_reason": "REVERSAL",
                            "bars_held": (i + 1) - entry_bar,
                            "gross_pnl_pct": gross_pnl,
                        })
                    current_pos = -1
                    entry_price = next_open
                    entry_time = next_time
                    entry_bar = i + 1
                    
    return trades

# Candidate 3: Model B / Preset A (MACD 12/26/9 + 2-bar hist expansion, TP = 1.5%, SL = 1.5%)
def run_candidate_3_model_b(data_map: Dict[str, pd.DataFrame], symbol_subset: Optional[set] = None) -> List[Dict[str, Any]]:
    trades = []
    long_tp = 1.5
    short_tp = 1.5
    sl_pct = 1.5
    
    for sym, df in data_map.items():
        if symbol_subset and sym not in symbol_subset:
            continue
            
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        macd = df["macd"]
        sig = df["sig"]
        hist = df["hist"]
        
        current_pos = 0
        entry_price = 0.0
        entry_time = None
        entry_bar = 0
        
        n = len(df)
        for i in range(2, n):
            ts = df.index[i]
            c_close = close.iloc[i]
            c_high = high.iloc[i]
            c_low = low.iloc[i]
            
            # Active Position Management
            if current_pos != 0:
                exit_reason = None
                exit_price = 0.0
                if current_pos == 1:
                    target_px = entry_price * (1.0 + long_tp / 100.0)
                    sl_px = entry_price * (1.0 - sl_pct / 100.0)
                    if c_low <= sl_px:
                        exit_reason = "STOP_LOSS"
                        exit_price = sl_px
                    elif c_high >= target_px:
                        exit_reason = "TARGET_HIT"
                        exit_price = target_px
                elif current_pos == -1:
                    target_px = entry_price * (1.0 - short_tp / 100.0)
                    sl_px = entry_price * (1.0 + sl_pct / 100.0)
                    if c_high >= sl_px:
                        exit_reason = "STOP_LOSS"
                        exit_price = sl_px
                    elif c_low <= target_px:
                        exit_reason = "TARGET_HIT"
                        exit_price = target_px
                        
                if exit_reason:
                    dir_mult = 1.0 if current_pos == 1 else -1.0
                    gross_pnl = ((exit_price - entry_price) / entry_price) * 100.0 * dir_mult
                    trades.append({
                        "symbol": sym,
                        "candidate": "Model_B_Preset_A",
                        "direction": current_pos,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "exit_reason": exit_reason,
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                    })
                    current_pos = 0
                    entry_price = 0.0
                    continue

            # Fresh Signal
            prev_macd, prev_sig = macd.iloc[i-1], sig.iloc[i-1]
            c_macd, c_sig = macd.iloc[i], sig.iloc[i]
            p2_h, p_h, c_h = hist.iloc[i-2], hist.iloc[i-1], hist.iloc[i]
            
            bull_exp = (c_h > p_h) and (p_h > p2_h)
            bear_exp = (c_h < p_h) and (p_h < p2_h)
            
            is_bullish = (prev_macd <= prev_sig) and (c_macd > c_sig) and bull_exp
            is_bearish = (prev_macd >= prev_sig) and (c_macd < c_sig) and bear_exp
            
            if is_bullish:
                if current_pos == -1:
                    gross_pnl = ((c_close - entry_price) / entry_price) * 100.0 * (-1.0)
                    trades.append({
                        "symbol": sym,
                        "candidate": "Model_B_Preset_A",
                        "direction": -1,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": c_close,
                        "exit_reason": "REVERSAL",
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                    })
                current_pos = 1
                entry_price = c_close
                entry_time = ts
                entry_bar = i
            elif is_bearish:
                if current_pos == 1:
                    gross_pnl = ((c_close - entry_price) / entry_price) * 100.0 * (1.0)
                    trades.append({
                        "symbol": sym,
                        "candidate": "Model_B_Preset_A",
                        "direction": 1,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": c_close,
                        "exit_reason": "REVERSAL",
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                    })
                current_pos = -1
                entry_price = c_close
                entry_time = ts
                entry_bar = i
                
    return trades

# Candidate 4: Candidate E / Preset B (Target + 0.35% HWM Runner + Asymmetric Universe)
def run_candidate_4_candidate_e(
    data_map: Dict[str, pd.DataFrame],
    symbol_subset: Optional[set] = None,
    use_asym_universe: bool = True,
    conservative_trailing: bool = True
) -> List[Dict[str, Any]]:
    trades = []
    long_tp = 3.0
    short_tp = 1.5
    trail_pct = 0.35
    sl_pct = 3.5
    
    for sym, df in data_map.items():
        if symbol_subset and sym not in symbol_subset:
            continue
            
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        macd = df["macd"]
        sig = df["sig"]
        hist = df["hist"]
        
        current_pos = 0
        entry_price = 0.0
        entry_time = None
        entry_bar = 0
        runner_active = False
        peak_px = 0.0
        trough_px = 999999.0
        
        n = len(df)
        for i in range(2, n):
            ts = df.index[i]
            c_close = close.iloc[i]
            c_high = high.iloc[i]
            c_low = low.iloc[i]
            
            # Active Position Management
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
                    else:
                        trough_px = min(trough_px, c_low)
                        trail_sl = trough_px * (1.0 + trail_pct / 100.0)
                        if c_high >= trail_sl:
                            exit_reason = "RUNNER_TRAIL"
                            exit_price = trail_sl
                            
                if exit_reason:
                    dir_mult = 1.0 if current_pos == 1 else -1.0
                    gross_pnl = ((exit_price - entry_price) / entry_price) * 100.0 * dir_mult
                    trades.append({
                        "symbol": sym,
                        "candidate": "Candidate_E_Preset_B",
                        "direction": current_pos,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "exit_reason": exit_reason,
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                    })
                    current_pos = 0
                    entry_price = 0.0
                    runner_active = False
                    continue

            # Fresh Signal
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
                    trades.append({
                        "symbol": sym,
                        "candidate": "Candidate_E_Preset_B",
                        "direction": -1,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": c_close,
                        "exit_reason": "REVERSAL",
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                    })
                current_pos = 1
                entry_price = c_close
                entry_time = ts
                entry_bar = i
                runner_active = False
            elif is_bearish:
                if current_pos == 1:
                    gross_pnl = ((c_close - entry_price) / entry_price) * 100.0 * (1.0)
                    trades.append({
                        "symbol": sym,
                        "candidate": "Candidate_E_Preset_B",
                        "direction": 1,
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": c_close,
                        "exit_reason": "REVERSAL",
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                    })
                current_pos = -1
                entry_price = c_close
                entry_time = ts
                entry_bar = i
                runner_active = False
                
    return trades

def run_portfolio_constrained_simulation(
    trades: List[Dict[str, Any]],
    max_active_positions: int = 20,
    friction_pct: float = 0.07
) -> Dict[str, Any]:
    """
    Simulates a portfolio concurrency gate: if active positions >= max_active_positions,
    new trades that open while at capacity are rejected/skipped.
    """
    if not trades:
        return compute_metrics([], friction_pct)
        
    df_t = pd.DataFrame(trades)
    df_t.sort_values("entry_time", inplace=True)
    
    accepted_trades = []
    # Event simulation
    events = []
    # We will step through chronological entries and check open positions at that moment
    active_until = [] # list of (exit_time, symbol)
    
    for idx, row in df_t.iterrows():
        entry_t = row["entry_time"]
        # Clear expired positions
        active_until = [p for p in active_until if p[0] > entry_t]
        
        if len(active_until) < max_active_positions:
            active_until.append((row["exit_time"], row["symbol"]))
            accepted_trades.append(row.to_dict())
            
    return compute_metrics(accepted_trades, friction_pct)

def main():
    print("=" * 80)
    print("STARTING MACD STRATEGY COMPARATIVE VALIDATION (READ-ONLY)")
    print("=" * 80)
    
    data_map = load_data()
    print(f"Loaded {len(data_map)} instrument datasets.")
    
    # 1. Native / Original Runs
    print("\n--- 1. EXECUTING CANDIDATE RUNS (NATIVE UNIVERSES) ---")
    t1_native = run_candidate_1_macdfno_baseline(data_map) # All 33
    t2_native = run_candidate_2_ema_macd_v2_2(data_map)    # All 33
    t3_native = run_candidate_3_model_b(data_map, symbol_subset=CORE_15_SYMBOLS) # 15 Core
    t4_native = run_candidate_4_candidate_e(data_map, use_asym_universe=True)    # Asym Universe
    
    # Save Native Trade Ledgers
    pd.DataFrame(t1_native).to_csv(LEDGER_DIR / "candidate1_macdfno_baseline_ledger.csv", index=False)
    pd.DataFrame(t2_native).to_csv(LEDGER_DIR / "candidate2_ema_macd_v2_2_ledger.csv", index=False)
    pd.DataFrame(t3_native).to_csv(LEDGER_DIR / "candidate3_model_b_ledger.csv", index=False)
    pd.DataFrame(t4_native).to_csv(LEDGER_DIR / "candidate4_candidate_e_ledger.csv", index=False)
    
    m1_nat = compute_metrics(t1_native)
    m2_nat = compute_metrics(t2_native)
    m3_nat = compute_metrics(t3_native)
    m4_nat = compute_metrics(t4_native)
    
    print(f"C1 Native (33 symbols): {m1_nat['total_trades']} trades | Net: {m1_nat['net_pnl_pct']:.2f}% | PF: {m1_nat['profit_factor']:.3f} | MDD: {m1_nat['max_drawdown_pct']:.2f}% | Holdout PF: {m1_nat['holdout_pf']:.3f}")
    print(f"C2 Native (33 symbols): {m2_nat['total_trades']} trades | Net: {m2_nat['net_pnl_pct']:.2f}% | PF: {m2_nat['profit_factor']:.3f} | MDD: {m2_nat['max_drawdown_pct']:.2f}% | Holdout PF: {m2_nat['holdout_pf']:.3f}")
    print(f"C3 Native (15 Core):    {m3_nat['total_trades']} trades | Net: {m3_nat['net_pnl_pct']:.2f}% | PF: {m3_nat['profit_factor']:.3f} | MDD: {m3_nat['max_drawdown_pct']:.2f}% | Holdout PF: {m3_nat['holdout_pf']:.3f}")
    print(f"C4 Native (Asym Univ):  {m4_nat['total_trades']} trades | Net: {m4_nat['net_pnl_pct']:.2f}% | PF: {m4_nat['profit_factor']:.3f} | MDD: {m4_nat['max_drawdown_pct']:.2f}% | Holdout PF: {m4_nat['holdout_pf']:.3f}")
    
    # 2. Common Comparison Universe (All 33 Liquid Symbols)
    print("\n--- 2. CONTROLLED COMPARISON ON IDENTICAL 33-SYMBOL UNIVERSE ---")
    t1_c33 = t1_native
    t2_c33 = t2_native
    t3_c33 = run_candidate_3_model_b(data_map, symbol_subset=None) # Model B across all 33
    t4_c33 = run_candidate_4_candidate_e(data_map, symbol_subset=None, use_asym_universe=False) # Cand E across all 33
    
    m1_c33 = compute_metrics(t1_c33)
    m2_c33 = compute_metrics(t2_c33)
    m3_c33 = compute_metrics(t3_c33)
    m4_c33 = compute_metrics(t4_c33)
    
    print(f"C1 Common-33: {m1_c33['total_trades']} trades | Net: {m1_c33['net_pnl_pct']:.2f}% | PF: {m1_c33['profit_factor']:.3f} | MDD: {m1_c33['max_drawdown_pct']:.2f}% | Holdout PF: {m1_c33['holdout_pf']:.3f}")
    print(f"C2 Common-33: {m2_c33['total_trades']} trades | Net: {m2_c33['net_pnl_pct']:.2f}% | PF: {m2_c33['profit_factor']:.3f} | MDD: {m2_c33['max_drawdown_pct']:.2f}% | Holdout PF: {m2_c33['holdout_pf']:.3f}")
    print(f"C3 Common-33: {m3_c33['total_trades']} trades | Net: {m3_c33['net_pnl_pct']:.2f}% | PF: {m3_c33['profit_factor']:.3f} | MDD: {m3_c33['max_drawdown_pct']:.2f}% | Holdout PF: {m3_c33['holdout_pf']:.3f}")
    print(f"C4 Common-33: {m4_c33['total_trades']} trades | Net: {m4_c33['net_pnl_pct']:.2f}% | PF: {m4_c33['profit_factor']:.3f} | MDD: {m4_c33['max_drawdown_pct']:.2f}% | Holdout PF: {m4_c33['holdout_pf']:.3f}")

    # 3. Controlled Comparison on 15 Core Liquid Leaders
    print("\n--- 3. CONTROLLED COMPARISON ON IDENTICAL 15 CORE LIQUID UNIVERSE ---")
    t1_c15 = run_candidate_1_macdfno_baseline(data_map, symbol_subset=CORE_15_SYMBOLS)
    t2_c15 = run_candidate_2_ema_macd_v2_2(data_map, symbol_subset=CORE_15_SYMBOLS)
    t3_c15 = t3_native
    t4_c15 = run_candidate_4_candidate_e(data_map, symbol_subset=CORE_15_SYMBOLS, use_asym_universe=False)
    
    m1_c15 = compute_metrics(t1_c15)
    m2_c15 = compute_metrics(t2_c15)
    m3_c15 = compute_metrics(t3_c15)
    m4_c15 = compute_metrics(t4_c15)

    print(f"C1 Core-15: {m1_c15['total_trades']} trades | Net: {m1_c15['net_pnl_pct']:.2f}% | PF: {m1_c15['profit_factor']:.3f} | MDD: {m1_c15['max_drawdown_pct']:.2f}% | Holdout PF: {m1_c15['holdout_pf']:.3f}")
    print(f"C2 Core-15: {m2_c15['total_trades']} trades | Net: {m2_c15['net_pnl_pct']:.2f}% | PF: {m2_c15['profit_factor']:.3f} | MDD: {m2_c15['max_drawdown_pct']:.2f}% | Holdout PF: {m2_c15['holdout_pf']:.3f}")
    print(f"C3 Core-15: {m3_c15['total_trades']} trades | Net: {m3_c15['net_pnl_pct']:.2f}% | PF: {m3_c15['profit_factor']:.3f} | MDD: {m3_c15['max_drawdown_pct']:.2f}% | Holdout PF: {m3_c15['holdout_pf']:.3f}")
    print(f"C4 Core-15: {m4_c15['total_trades']} trades | Net: {m4_c15['net_pnl_pct']:.2f}% | PF: {m4_c15['profit_factor']:.3f} | MDD: {m4_c15['max_drawdown_pct']:.2f}% | Holdout PF: {m4_c15['holdout_pf']:.3f}")

    # 4. Cost Sensitivity Grid [0.05%, 0.07%, 0.10%, 0.12%, 0.15%]
    print("\n--- 4. FRICTION COST SENSITIVITY MATRIX ---")
    frictions = [0.05, 0.07, 0.10, 0.12, 0.15]
    f_results = []
    for f in frictions:
        f_results.append({
            "friction_pct": f,
            "c1_pf": compute_metrics(t1_native, f)["profit_factor"],
            "c2_pf": compute_metrics(t2_native, f)["profit_factor"],
            "c3_pf": compute_metrics(t3_native, f)["profit_factor"],
            "c4_pf": compute_metrics(t4_native, f)["profit_factor"],
            "c1_net": compute_metrics(t1_native, f)["net_pnl_pct"],
            "c2_net": compute_metrics(t2_native, f)["net_pnl_pct"],
            "c3_net": compute_metrics(t3_native, f)["net_pnl_pct"],
            "c4_net": compute_metrics(t4_native, f)["net_pnl_pct"],
        })
    df_f = pd.DataFrame(f_results)
    df_f.to_csv(EXP_DIR / "friction_sensitivity_matrix.csv", index=False)
    print(df_f.to_string())

    # 5. Position Limit Impact Simulation (Max 20 Active Contracts)
    print("\n--- 5. POSITION CONCURRENCY GATE SIMULATION (MAX 20 ACTIVE) ---")
    c1_cap = run_portfolio_constrained_simulation(t1_native, max_active_positions=20)
    c2_cap = run_portfolio_constrained_simulation(t2_native, max_active_positions=20)
    c3_cap = run_portfolio_constrained_simulation(t3_native, max_active_positions=20)
    c4_cap = run_portfolio_constrained_simulation(t4_native, max_active_positions=20)
    print(f"C1 Cap-20: {c1_cap['total_trades']} trades | Net: {c1_cap['net_pnl_pct']:.2f}% | PF: {c1_cap['profit_factor']:.3f}")
    print(f"C2 Cap-20: {c2_cap['total_trades']} trades | Net: {c2_cap['net_pnl_pct']:.2f}% | PF: {c2_cap['profit_factor']:.3f}")
    print(f"C3 Cap-20: {c3_cap['total_trades']} trades | Net: {c3_cap['net_pnl_pct']:.2f}% | PF: {c3_cap['profit_factor']:.3f}")
    print(f"C4 Cap-20: {c4_cap['total_trades']} trades | Net: {c4_cap['net_pnl_pct']:.2f}% | PF: {c4_cap['profit_factor']:.3f}")

    # 6. Directional Long vs Short Breakdown
    print("\n--- 6. DIRECTIONAL LONG VS SHORT BREAKDOWN ---")
    def get_dir_breakdown(trades, label):
        df = pd.DataFrame(trades)
        if df.empty: return
        df["net_pnl_pct"] = df["gross_pnl_pct"] - 0.07
        longs = df[df["direction"] == 1]
        shorts = df[df["direction"] == -1]
        m_l = compute_metrics(longs.to_dict("records"))
        m_s = compute_metrics(shorts.to_dict("records"))
        return {
            "candidate": label,
            "long_trades": m_l["total_trades"], "long_net": m_l["net_pnl_pct"], "long_pf": m_l["profit_factor"], "long_wr": m_l["win_rate_pct"],
            "short_trades": m_s["total_trades"], "short_net": m_s["net_pnl_pct"], "short_pf": m_s["profit_factor"], "short_wr": m_s["win_rate_pct"],
        }
    
    dir_summary = [
        get_dir_breakdown(t1_native, "Candidate 1 (Baseline)"),
        get_dir_breakdown(t2_native, "Candidate 2 (EMA/MACD V2-2)"),
        get_dir_breakdown(t3_native, "Candidate 3 (Model B)"),
        get_dir_breakdown(t4_native, "Candidate 4 (Candidate E)"),
    ]
    df_dir = pd.DataFrame(dir_summary)
    df_dir.to_csv(EXP_DIR / "directional_breakdown.csv", index=False)
    print(df_dir.to_string())

    # 7. Per-Symbol Breakdown
    print("\n--- 7. PER-SYMBOL PERFORMANCE BREAKDOWN ---")
    all_sym_rows = []
    for cand_name, tr_list in [("C1_Baseline", t1_native), ("C2_EMA_MACD", t2_native), ("C3_Model_B", t3_native), ("C4_Candidate_E", t4_native)]:
        df = pd.DataFrame(tr_list)
        if df.empty: continue
        for sym, grp in df.groupby("symbol"):
            m = compute_metrics(grp.to_dict("records"))
            all_sym_rows.append({
                "candidate": cand_name,
                "symbol": sym,
                "trades": m["total_trades"],
                "net_pnl_pct": m["net_pnl_pct"],
                "profit_factor": m["profit_factor"],
                "win_rate_pct": m["win_rate_pct"],
                "max_drawdown_pct": m["max_drawdown_pct"]
            })
    df_sym = pd.DataFrame(all_sym_rows)
    df_sym.to_csv(EXP_DIR / "per_symbol_breakdown.csv", index=False)

    # 8. Master Summary Table
    summary_rows = [
        {"Scope": "Native Universe", "Candidate": "1. MACD_FNO_V1 Baseline", **m1_nat},
        {"Scope": "Native Universe", "Candidate": "2. EMA_MACD_V2_2", **m2_nat},
        {"Scope": "Native Universe", "Candidate": "3. Model B (Preset A)", **m3_nat},
        {"Scope": "Native Universe", "Candidate": "4. Candidate E (Preset B)", **m4_nat},
        {"Scope": "Common 33-Universe", "Candidate": "1. MACD_FNO_V1 Baseline", **m1_c33},
        {"Scope": "Common 33-Universe", "Candidate": "2. EMA_MACD_V2_2", **m2_c33},
        {"Scope": "Common 33-Universe", "Candidate": "3. Model B (Preset A)", **m3_c33},
        {"Scope": "Common 33-Universe", "Candidate": "4. Candidate E (Preset B)", **m4_c33},
        {"Scope": "Core 15-Universe", "Candidate": "1. MACD_FNO_V1 Baseline", **m1_c15},
        {"Scope": "Core 15-Universe", "Candidate": "2. EMA_MACD_V2_2", **m2_c15},
        {"Scope": "Core 15-Universe", "Candidate": "3. Model B (Preset A)", **m3_c15},
        {"Scope": "Core 15-Universe", "Candidate": "4. Candidate E (Preset B)", **m4_c15},
    ]
    df_sum = pd.DataFrame(summary_rows)
    df_sum.to_csv(EXP_DIR / "master_comparison_summary.csv", index=False)
    print("\nSaved master comparison summary to:", EXP_DIR / "master_comparison_summary.csv")
    print("=" * 80)

if __name__ == "__main__":
    main()
