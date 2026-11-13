"""
MACD_FNO_V1 Dead-Zone Filter Impact Audit Engine
Location: backtesting/experiments/exp_20261015_macd_time_filter_audit/run_time_filter_audit.py

Objectives:
  1. Audit exact implementation of is_entry_time_allowed() in live vs backtest.
  2. Simulate Variants:
     - Variant A (Live Baseline Filter): Exact wall-clock evaluation at 1H candle boundary sync (:15:02 IST)
     - Variant B (Time Filter Disabled): ENABLE_TIME_FILTER=False (All 1H completed bars eligible)
     - Variant C1 (Candle-Aligned Filter): Evaluates completed 1H bar timestamp without premature clock cutoffs
     - Variant C2 (Midday-Only Lull Exclusion): Allows morning (10:15 & 11:15) and afternoon (14:15 & 15:15); blocks only 12:30-13:30 lunch chop
     - Variant Legacy_Backtest: The historical backtest implementation (which evaluated bar open timestamp ts = df.index[i])
  3. Track all eligible signals, rejections, rejection reasons, and counterfactual trade outcomes.
  4. Perform IS, OOS, and 2026 Holdout validations, friction sensitivity, directional breakdown, and portfolio concurrency.
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
import json
from typing import Dict, List, Any, Tuple, Optional
from datetime import time, datetime

# Setup directories
EXP_DIR = Path("/Users/mac/Desktop/openalgo/backtesting/experiments/exp_20261015_macd_time_filter_audit")
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

# ------------------------------------------------------------------------------
# Time Filter Logic Implementations
# ------------------------------------------------------------------------------

def filter_variant_a_live_baseline(eval_time: time) -> Tuple[bool, str]:
    """
    Exact reproduction of live macdfno.py is_entry_time_allowed()
    evaluated at candle polling time (:15:02 IST).
    """
    m = eval_time.hour * 60 + eval_time.minute
    if (9 * 60 + 45) <= m <= (10 * 60 + 55):
        return True, "MORNING_WINDOW"
    elif (12 * 60 + 0) <= m <= (13 * 60 + 15):
        return True, "MIDDAY_WINDOW"
    elif (15 * 60 + 0) <= m <= (15 * 60 + 20):
        return True, "CLOSING_WINDOW"
    elif (11 * 60) <= m < (12 * 60):
        return False, "DEAD_ZONE_11_AM"
    elif (14 * 60) <= m < (15 * 60):
        return False, "DEAD_ZONE_14_PM"
    else:
        return False, "OUTSIDE_ALLOWED_WINDOWS"

def filter_variant_b_disabled(eval_time: time) -> Tuple[bool, str]:
    """Variant B: Time filter disabled entirely."""
    return True, "FILTER_DISABLED"

def filter_variant_c1_realigned(eval_time: time) -> Tuple[bool, str]:
    """
    Variant C1: Realigned 1-Hour Candle Filter.
    Permits the 11:15 IST execution (10:15-11:15 candle) and 14:15 IST execution (13:15-14:15 candle).
    Blocks only early opening noise (< 09:45) and late market close (> 15:20).
    """
    m = eval_time.hour * 60 + eval_time.minute
    if m < (9 * 60 + 45):
        return False, "OPENING_NOISE"
    elif m > (15 * 60 + 20):
        return False, "POST_CLOSE"
    else:
        return True, "REALIGNED_ACTIVE_SESSION"

def filter_variant_c2_midday_lull_only(eval_time: time) -> Tuple[bool, str]:
    """
    Variant C2: Explicit Midday-Only Lull Exclusion.
    Blocks entries strictly during the true institutional lunch vacuum: 12:30 - 13:30 IST.
    Permits morning trending moves (10:15, 11:15, 12:15) and afternoon trends (14:15, 15:15).
    """
    m = eval_time.hour * 60 + eval_time.minute
    if m < (9 * 60 + 45):
        return False, "OPENING_NOISE"
    elif (12 * 60 + 30) <= m < (13 * 60 + 30):
        return False, "MIDDAY_LUNCH_LULL"
    elif m > (15 * 60 + 20):
        return False, "POST_CLOSE"
    else:
        return True, "ALLOWED_WINDOW"

def filter_variant_legacy_backtest(bar_open_time: time) -> Tuple[bool, str]:
    """
    How the historical backtest script (run_macdfno_experiments.py) checked it:
    Checked bar_open_time (df.index[i]) against IST windows.
    """
    m = bar_open_time.hour * 60 + bar_open_time.minute
    if (9 * 60 + 45) <= m <= (10 * 60 + 55):
        return True, "LEGACY_MORNING"
    elif (12 * 60 + 0) <= m <= (13 * 60 + 15):
        return True, "LEGACY_MIDDAY"
    elif (15 * 60 + 0) <= m <= (15 * 60 + 20):
        return True, "LEGACY_CLOSING"
    else:
        return False, "LEGACY_BLOCKED"

# ------------------------------------------------------------------------------
# Data Loading & Indicator Computation
# ------------------------------------------------------------------------------

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
        
        # 50 EMA Regime
        df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["ema26"] = ema26
        
        # IST Datetime column for time filtering & audit
        df["ist_dt"] = df.index.tz_convert("Asia/Kolkata")
        
        data_map[sym] = df
    return data_map

# ------------------------------------------------------------------------------
# Comprehensive Simulation & Audit Engine
# ------------------------------------------------------------------------------

def simulate_variant(
    data_map: Dict[str, pd.DataFrame],
    time_filter_fn: Any,
    filter_mode: str, # "eval_clock" vs "bar_open"
    universe_mode: str = "native", # "native" (asym), "all33", "core15"
    use_regime: bool = False,
    long_tp: float = 3.0,
    short_tp: float = 1.5,
    sl_pct: float = 3.5,
    friction_pct: float = 0.07,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Simulates MACD_FNO_V1 strictly on completed 1H candles with full signal audit.
    Returns: (executed_trades, signal_audit_log)
    """
    executed_trades = []
    signal_audit = []
    
    for sym, df in data_map.items():
        if universe_mode == "core15" and sym not in CORE_15_SYMBOLS:
            continue
            
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        macd = df["macd"]
        sig = df["sig"]
        hist = df["hist"]
        ema50 = df["ema50"]
        ema26 = df["ema26"]
        ist_dt = df["ist_dt"]
        
        current_pos = 0 # 1=LONG, -1=SHORT, 0=FLAT
        entry_price = 0.0
        entry_time = None
        entry_ist = None
        entry_bar = 0
        
        n = len(df)
        for i in range(2, n):
            ts = df.index[i]
            ts_ist = ist_dt.iloc[i]
            c_close = close.iloc[i]
            c_high = high.iloc[i]
            c_low = low.iloc[i]
            
            # Bar i represents the candle that just COMPLETED.
            # In live openalgo, this bar finishes 60 mins after its index.
            # The polling clock time is roughly: ts_ist + 1 hour (+2 seconds).
            # e.g., 09:15 bar completes at 10:15 IST.
            eval_clock_time = (ts_ist + pd.Timedelta(hours=1, seconds=2)).time()
            bar_open_time = ts_ist.time()
            
            # 1. Manage Active Position Exits (Target, SL, Catastrophe)
            if current_pos != 0:
                exit_reason = None
                exit_price = 0.0
                
                if current_pos == 1: # LONG
                    target_px = entry_price * (1.0 + long_tp / 100.0)
                    sl_px = entry_price * (1.0 - sl_pct / 100.0)
                    if c_low <= sl_px:
                        exit_reason = "CATASTROPHE_SL"
                        exit_price = sl_px
                    elif c_high >= target_px:
                        exit_reason = "TARGET_HIT"
                        exit_price = target_px
                elif current_pos == -1: # SHORT
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
                    net_pnl = gross_pnl - friction_pct
                    executed_trades.append({
                        "symbol": sym,
                        "direction": current_pos,
                        "entry_time": entry_time,
                        "entry_ist": str(entry_ist),
                        "exit_time": ts,
                        "exit_ist": str(ts_ist),
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "exit_reason": exit_reason,
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                        "net_pnl_pct": net_pnl,
                        "eval_hour": entry_ist.hour if entry_ist is not None else 0,
                    })
                    current_pos = 0
                    entry_price = 0.0
                    continue

            # 2. Evaluate MACD Cross + 2-Bar Hist Expansion
            prev_macd, prev_sig = macd.iloc[i-1], sig.iloc[i-1]
            c_macd, c_sig = macd.iloc[i], sig.iloc[i]
            p2_h, p_h, c_h = hist.iloc[i-2], hist.iloc[i-1], hist.iloc[i]
            
            bull_exp = (c_h > p_h) and (p_h > p2_h)
            bear_exp = (c_h < p_h) and (p_h < p2_h)
            
            raw_bull = (prev_macd <= prev_sig) and (c_macd > c_sig) and bull_exp
            raw_bear = (prev_macd >= prev_sig) and (c_macd < c_sig) and bear_exp
            
            if not raw_bull and not raw_bear:
                continue
                
            sig_dir = 1 if raw_bull else -1
            sig_name = "BUY" if raw_bull else "SELL"
            
            # Filter checks
            # A. Time Filter Check
            t_check_time = eval_clock_time if filter_mode == "eval_clock" else bar_open_time
            time_ok, time_reason = time_filter_fn(t_check_time)
            
            # B. Universe Filter Check
            universe_ok = True
            univ_reason = "IN_UNIVERSE"
            if universe_mode == "native":
                if sig_dir == 1 and sym not in TOP_LONGS:
                    universe_ok = False
                    univ_reason = "NOT_IN_TOP_LONGS"
                elif sig_dir == -1 and sym not in TOP_SHORTS:
                    universe_ok = False
                    univ_reason = "NOT_IN_TOP_SHORTS"
            elif universe_mode == "core15":
                if sym not in CORE_15_SYMBOLS:
                    universe_ok = False
                    univ_reason = "NOT_IN_CORE_15"
                    
            # C. Regime Filter Check
            regime_ok = True
            regime_reason = "REGIME_OK"
            if use_regime:
                if sig_dir == 1 and c_close < ema50.iloc[i]:
                    regime_ok = False
                    regime_reason = "BELOW_EMA50"
                elif sig_dir == -1 and c_close > ema26.iloc[i]:
                    regime_ok = False
                    regime_reason = "ABOVE_EMA26"
                    
            decision = "EXECUTED" if (time_ok and universe_ok and regime_ok) else "REJECTED"
            primary_rejection = None
            if not time_ok:
                primary_rejection = f"TIME_{time_reason}"
            elif not universe_ok:
                primary_rejection = f"UNIV_{univ_reason}"
            elif not regime_ok:
                primary_rejection = f"REGIME_{regime_reason}"
                
            signal_audit.append({
                "symbol": sym,
                "candle_open_ist": str(ts_ist),
                "candle_complete_ist": str(ts_ist + pd.Timedelta(hours=1)),
                "eval_clock_time": str(eval_clock_time),
                "direction": sig_name,
                "close_price": c_close,
                "time_ok": time_ok,
                "time_reason": time_reason,
                "universe_ok": universe_ok,
                "univ_reason": univ_reason,
                "regime_ok": regime_ok,
                "regime_reason": regime_reason,
                "decision": decision,
                "primary_rejection": primary_rejection,
            })
            
            # If rejected, do not enter
            if decision == "REJECTED":
                continue
                
            # Execute Entry / Reversal
            if sig_dir == 1:
                if current_pos == -1: # Close short first
                    dir_mult = -1.0
                    gross_pnl = ((c_close - entry_price) / entry_price) * 100.0 * dir_mult
                    net_pnl = gross_pnl - friction_pct
                    executed_trades.append({
                        "symbol": sym,
                        "direction": -1,
                        "entry_time": entry_time,
                        "entry_ist": str(entry_ist),
                        "exit_time": ts,
                        "exit_ist": str(ts_ist),
                        "entry_price": entry_price,
                        "exit_price": c_close,
                        "exit_reason": "REVERSAL",
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                        "net_pnl_pct": net_pnl,
                        "eval_hour": entry_ist.hour if entry_ist is not None else 0,
                    })
                current_pos = 1
                entry_price = c_close
                entry_bar = i
                entry_time = ts
                entry_ist = ts_ist + pd.Timedelta(hours=1)
            elif sig_dir == -1:
                if current_pos == 1: # Close long first
                    dir_mult = 1.0
                    gross_pnl = ((c_close - entry_price) / entry_price) * 100.0 * dir_mult
                    net_pnl = gross_pnl - friction_pct
                    executed_trades.append({
                        "symbol": sym,
                        "direction": 1,
                        "entry_time": entry_time,
                        "entry_ist": str(entry_ist),
                        "exit_time": ts,
                        "exit_ist": str(ts_ist),
                        "entry_price": entry_price,
                        "exit_price": c_close,
                        "exit_reason": "REVERSAL",
                        "bars_held": i - entry_bar,
                        "gross_pnl_pct": gross_pnl,
                        "net_pnl_pct": net_pnl,
                        "eval_hour": entry_ist.hour if entry_ist is not None else 0,
                    })
                current_pos = -1
                entry_price = c_close
                entry_bar = i
                entry_time = ts
                entry_ist = ts_ist + pd.Timedelta(hours=1)
                
    return executed_trades, signal_audit

# ------------------------------------------------------------------------------
# Performance Metrics Computation
# ------------------------------------------------------------------------------

def compute_metrics(trades: List[Dict[str, Any]], friction_pct: float = 0.07) -> Dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0, "trades_per_day": 0.0, "long_trades": 0, "short_trades": 0,
            "net_pnl_pct": 0.0, "profit_factor": 0.0, "win_rate_pct": 0.0,
            "avg_win_pct": 0.0, "avg_loss_pct": 0.0, "payoff_ratio": 0.0,
            "expectancy_pct": 0.0, "max_drawdown_pct": 0.0,
            "is_trades": 0, "is_pf": 0.0, "is_net_pnl": 0.0,
            "oos_trades": 0, "oos_pf": 0.0, "oos_net_pnl": 0.0,
            "holdout_trades": 0, "holdout_pf": 0.0, "holdout_net_pnl": 0.0,
            "long_pf": 0.0, "long_net_pnl": 0.0, "short_pf": 0.0, "short_net_pnl": 0.0,
        }
        
    df_t = pd.DataFrame(trades)
    df_t["exit_time"] = pd.to_datetime(df_t["exit_time"], utc=True)
    df_t.sort_values("exit_time", inplace=True)
    
    # Recalculate net pnl with specified friction
    df_t["net_pnl_pct"] = df_t["gross_pnl_pct"] - friction_pct
    
    pnls = df_t["net_pnl_pct"].values
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    
    total_trades = len(df_t)
    long_trades = int((df_t["direction"] == 1).sum())
    short_trades = int((df_t["direction"] == -1).sum())
    
    win_rate = (len(wins) / total_trades * 100.0) if total_trades else 0.0
    avg_win = float(np.mean(wins)) if len(wins) else 0.0
    avg_loss = float(abs(np.mean(losses))) if len(losses) else 0.0
    payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0
    
    gross_win = float(np.sum(wins)) if len(wins) else 0.0
    gross_loss = float(abs(np.sum(losses))) if len(losses) else 0.00001
    pf = gross_win / gross_loss
    net_pnl = float(np.sum(pnls))
    expectancy = (net_pnl / total_trades) if total_trades else 0.0
    
    # Drawdown
    cum_pnl = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum_pnl)
    drawdowns = peak - cum_pnl
    mdd = float(np.max(drawdowns)) if len(drawdowns) else 0.0
    
    # Date range for trades per day
    min_date = df_t["exit_time"].min()
    max_date = df_t["exit_time"].max()
    days = max(1, (max_date - min_date).days)
    trading_days = days * (250.0 / 365.0)
    tpd = total_trades / trading_days
    
    # Segmentations: IS, OOS, Holdout
    df_is = df_t[df_t["exit_time"] < IS_CUTOFF]
    df_oos = df_t[df_t["exit_time"] >= IS_CUTOFF]
    df_holdout = df_t[df_t["exit_time"] >= HOLDOUT_CUTOFF]
    
    def calc_sub_pf(df_sub):
        if df_sub.empty:
            return 0.0, 0.0
        p = df_sub["net_pnl_pct"].values
        w = p[p > 0]
        l = p[p < 0]
        gw = float(np.sum(w)) if len(w) else 0.0
        gl = float(abs(np.sum(l))) if len(l) else 0.00001
        return (gw / gl), float(np.sum(p))
        
    is_pf, is_net = calc_sub_pf(df_is)
    oos_pf, oos_net = calc_sub_pf(df_oos)
    holdout_pf, holdout_net = calc_sub_pf(df_holdout)
    
    # Long vs Short
    df_long = df_t[df_t["direction"] == 1]
    df_short = df_t[df_t["direction"] == -1]
    long_pf, long_net = calc_sub_pf(df_long)
    short_pf, short_net = calc_sub_pf(df_short)
    
    return {
        "total_trades": total_trades,
        "trades_per_day": round(tpd, 2),
        "long_trades": long_trades,
        "short_trades": short_trades,
        "net_pnl_pct": round(net_pnl, 2),
        "profit_factor": round(pf, 3),
        "win_rate_pct": round(win_rate, 2),
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "payoff_ratio": round(payoff_ratio, 2),
        "expectancy_pct": round(expectancy, 3),
        "max_drawdown_pct": round(mdd, 2),
        "is_trades": len(df_is),
        "is_pf": round(is_pf, 3),
        "is_net_pnl": round(is_net, 2),
        "oos_trades": len(df_oos),
        "oos_pf": round(oos_pf, 3),
        "oos_net_pnl": round(oos_net, 2),
        "holdout_trades": len(df_holdout),
        "holdout_pf": round(holdout_pf, 3),
        "holdout_net_pnl": round(holdout_net, 2),
        "long_pf": round(long_pf, 3),
        "long_net_pnl": round(long_net, 2),
        "short_pf": round(short_pf, 3),
        "short_net_pnl": round(short_net, 2),
    }

# ------------------------------------------------------------------------------
# Main Execution Runner
# ------------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("🚀 MACD_FNO_V1 DEAD-ZONE FILTER IMPACT AUDIT")
    print("=" * 80)
    
    data_map = load_data()
    print(f"Loaded {len(data_map)} instrument datasets (33 NSE F&O Underlyings, 1H Candles).")
    
    variants_to_run = [
        # (Variant Code, Name, Filter Fn, Filter Mode, Universe Mode)
        ("A_LIVE_ASYM", "Variant A: Live Baseline (Asym Universe)", filter_variant_a_live_baseline, "eval_clock", "native"),
        ("B_DISABLED_ASYM", "Variant B: Filter Disabled (Asym Universe)", filter_variant_b_disabled, "eval_clock", "native"),
        ("C1_REALIGNED_ASYM", "Variant C1: Realigned 1H Filter (Asym Universe)", filter_variant_c1_realigned, "eval_clock", "native"),
        ("C2_MIDDAY_ASYM", "Variant C2: Midday-Only Lull (Asym Universe)", filter_variant_c2_midday_lull_only, "eval_clock", "native"),
        ("LEGACY_ASYM", "Variant Legacy: Bar-Open Check (Asym Universe)", filter_variant_legacy_backtest, "bar_open", "native"),
        
        # Unrestricted 33 Universe Comparisons
        ("A_LIVE_ALL33", "Variant A: Live Baseline (Common 33)", filter_variant_a_live_baseline, "eval_clock", "all33"),
        ("B_DISABLED_ALL33", "Variant B: Filter Disabled (Common 33)", filter_variant_b_disabled, "eval_clock", "all33"),
        ("C1_REALIGNED_ALL33", "Variant C1: Realigned 1H Filter (Common 33)", filter_variant_c1_realigned, "eval_clock", "all33"),
        ("C2_MIDDAY_ALL33", "Variant C2: Midday-Only Lull (Common 33)", filter_variant_c2_midday_lull_only, "eval_clock", "all33"),
        ("LEGACY_ALL33", "Variant Legacy: Bar-Open Check (Common 33)", filter_variant_legacy_backtest, "bar_open", "all33"),
    ]
    
    master_summary = []
    audit_reports = {}
    
    for code, desc, fn, f_mode, u_mode in variants_to_run:
        print(f"\nRunning {code}: {desc}...")
        trades, audit_log = simulate_variant(
            data_map,
            time_filter_fn=fn,
            filter_mode=f_mode,
            universe_mode=u_mode,
            friction_pct=0.07,
        )
        
        # Save Trade Ledger
        df_trades = pd.DataFrame(trades)
        ledger_path = LEDGER_DIR / f"{code}_ledger.csv"
        df_trades.to_csv(ledger_path, index=False)
        
        # Save Signal Rejection Log
        df_audit = pd.DataFrame(audit_log)
        audit_path = EXP_DIR / f"{code}_signals.csv"
        df_audit.to_csv(audit_path, index=False)
        
        metrics = compute_metrics(trades, friction_pct=0.07)
        master_summary.append({
            "variant_code": code,
            "description": desc,
            "universe": u_mode,
            **metrics
        })
        audit_reports[code] = {
            "total_signals": len(df_audit),
            "executed_signals": int((df_audit["decision"] == "EXECUTED").sum()),
            "rejected_signals": int((df_audit["decision"] == "REJECTED").sum()),
            "time_rejections": int(df_audit["primary_rejection"].str.startswith("TIME_", na=False).sum()),
            "univ_rejections": int(df_audit["primary_rejection"].str.startswith("UNIV_", na=False).sum()),
            "regime_rejections": int(df_audit["primary_rejection"].str.startswith("REGIME_", na=False).sum()),
        }
        
    df_summary = pd.DataFrame(master_summary)
    summary_path = EXP_DIR / "master_variant_summary.csv"
    df_summary.to_csv(summary_path, index=False)
    print(f"\n✅ Master summary saved to {summary_path}")
    
    # Signal audit summary
    df_audit_summary = pd.DataFrame.from_dict(audit_reports, orient="index")
    df_audit_summary.to_csv(EXP_DIR / "signal_rejection_audit_summary.csv")
    print(f"✅ Signal rejection audit saved to {EXP_DIR / 'signal_rejection_audit_summary.csv'}")

    # Friction sensitivity for core variants
    friction_levels = [0.05, 0.07, 0.10, 0.12, 0.15]
    friction_rows = []
    core_codes = ["A_LIVE_ASYM", "B_DISABLED_ASYM", "C1_REALIGNED_ASYM", "C2_MIDDAY_ASYM"]
    for c_code in core_codes:
        t_path = LEDGER_DIR / f"{c_code}_ledger.csv"
        t_df = pd.read_csv(t_path)
        t_list = t_df.to_dict(orient="records")
        for f in friction_levels:
            m = compute_metrics(t_list, friction_pct=f)
            friction_rows.append({
                "variant_code": c_code,
                "friction_pct": f,
                "profit_factor": m["profit_factor"],
                "net_pnl_pct": m["net_pnl_pct"],
                "expectancy_pct": m["expectancy_pct"],
                "win_rate_pct": m["win_rate_pct"],
            })
    df_friction = pd.DataFrame(friction_rows)
    df_friction.to_csv(EXP_DIR / "friction_sensitivity_matrix.csv", index=False)
    print(f"✅ Friction sensitivity matrix saved to {EXP_DIR / 'friction_sensitivity_matrix.csv'}")

if __name__ == "__main__":
    main()
