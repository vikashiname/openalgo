"""
Trend-Based Exit Research Engine — EMACROSSOPEN
File: backtesting/emacrossopen/trend_exit_research.py

Researches whether a better trend-based exit can replace or complement
the -10% catastrophe SL on completed 1H candles across 33 NFO symbols (166,444 bars).

Concepts Evaluated:
  A. EMA9/EMA26 trend-state exits (pure EMA cross)
  B. Close-based EMA9/EMA26 exits only after confirmation (low breakout / buffer)
  C. 2-candle confirmation below EMA9 / EMA26 for LONG and above for SHORT
  D. EMA9 + EMA26 combined exit conditions (double MA, baseline + EMA cross, spread contracting)
  E. EMA9/EMA26 exit accompanied by MACD deterioration/reversal (histogram, MACD cross)
  F. Testing both WITH -10% catastrophe SL backup and WITHOUT fixed SL (pure replacement)
  G. Comparison against the verified production benchmark:
     +3.00% Long / +1.50% Short, -10% Catastrophe SL, V2-2 Reversal (+161.76% return).
"""

import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from data_manager import load_or_download_all_data, SYMBOL_TICKER_MAP
from feature_extractor import calculate_indicators

FRICTION_PCT = 0.07
TOTAL_DAYS = 1076.0
YEARS = TOTAL_DAYS / 365.25  # ~2.946 years
IS_SPLIT_DATE = pd.to_datetime("2025-07-01", utc=True)


def compute_metrics(trades_df: pd.DataFrame, custom_years: Optional[float] = None) -> Dict[str, Any]:
    """Computes comprehensive quantitative metrics for a given subset of trades."""
    if trades_df.empty:
        return {
            "trade_count": 0, "win_rate_pct": 0.0, "profit_factor": 0.0,
            "expectancy_pct": 0.0, "total_return_pct": 0.0, "annualized_return_pct": 0.0,
            "cagr_pct": 0.0, "max_drawdown_pct": 0.0, "calmar_ratio": 0.0,
            "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
            "avg_bars_held": 0.0, "median_bars_held": 0.0,
            "avg_mfe_pct": 0.0, "avg_mae_pct": 0.0,
            "target_hit_count": 0, "target_hit_pct": 0.0,
            "trend_exit_count": 0, "trend_exit_pct": 0.0,
            "sl_hit_count": 0, "sl_hit_pct": 0.0,
            "reversal_count": 0, "reversal_pct": 0.0,
            "max_single_loss_pct": 0.0, "worst_5_loss_avg_pct": 0.0,
        }

    n = len(trades_df)
    net_pnls = trades_df["net_pnl_pct"].values
    wins = net_pnls[net_pnls > 0]
    losses = net_pnls[net_pnls < 0]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / n) * 100.0 if n > 0 else 0.0

    sum_wins = float(np.sum(wins)) if win_count > 0 else 0.0
    sum_losses = float(np.abs(np.sum(losses))) if loss_count > 0 else 0.0
    profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)

    total_return = float(np.sum(net_pnls))
    expectancy = float(np.mean(net_pnls)) if n > 0 else 0.0
    avg_win = float(np.mean(wins)) if win_count > 0 else 0.0
    avg_loss = float(np.abs(np.mean(losses))) if loss_count > 0 else 0.0

    # Drawdown on cumulative net PnL percentage curve
    cum_returns = np.cumsum(net_pnls)
    peak = np.maximum.accumulate(cum_returns)
    drawdowns = peak - cum_returns
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Annualized return & CAGR
    y = custom_years if custom_years is not None else YEARS
    ann_return = total_return / y if y > 0 else 0.0
    if total_return > -100.0 and y > 0:
        cagr = ((1.0 + total_return / 100.0) ** (1.0 / y) - 1.0) * 100.0
    else:
        cagr = -100.0
    calmar = (ann_return / max_dd) if max_dd > 0 else 0.0

    # Holding periods
    bars = trades_df["bars_held"].values
    avg_bars = float(np.mean(bars)) if len(bars) > 0 else 0.0
    median_bars = float(np.median(bars)) if len(bars) > 0 else 0.0

    # MFE / MAE
    avg_mfe = float(trades_df["mfe_pct"].mean()) if "mfe_pct" in trades_df.columns else 0.0
    avg_mae = float(trades_df["mae_pct"].mean()) if "mae_pct" in trades_df.columns else 0.0

    # Exit reason counts
    reasons = trades_df["exit_reason"].value_counts().to_dict()
    tp_count = reasons.get("TARGET_HIT", 0)
    trend_count = sum(v for k, v in reasons.items() if "TREND_EXIT" in k)
    sl_count = reasons.get("CATASTROPHE_SL", 0)
    rev_count = reasons.get("V2-2_REVERSAL", 0)

    tp_pct = (tp_count / n) * 100.0 if n > 0 else 0.0
    trend_pct = (trend_count / n) * 100.0 if n > 0 else 0.0
    sl_pct = (sl_count / n) * 100.0 if n > 0 else 0.0
    rev_pct = (rev_count / n) * 100.0 if n > 0 else 0.0

    # Tail Risk metrics
    sorted_losses = np.sort(net_pnls)
    max_single_loss = float(sorted_losses[0]) if len(sorted_losses) > 0 and sorted_losses[0] < 0 else 0.0
    worst_5_loss = float(np.mean(sorted_losses[:min(5, len(sorted_losses))])) if len(sorted_losses) > 0 else 0.0

    return {
        "trade_count": n,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 3),
        "expectancy_pct": round(expectancy, 4),
        "total_return_pct": round(total_return, 2),
        "annualized_return_pct": round(ann_return, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "calmar_ratio": round(calmar, 3),
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "avg_bars_held": round(avg_bars, 1),
        "median_bars_held": round(median_bars, 1),
        "avg_mfe_pct": round(avg_mfe, 2),
        "avg_mae_pct": round(avg_mae, 2),
        "target_hit_count": tp_count,
        "target_hit_pct": round(tp_pct, 2),
        "trend_exit_count": trend_count,
        "trend_exit_pct": round(trend_pct, 2),
        "sl_hit_count": sl_count,
        "sl_hit_pct": round(sl_pct, 2),
        "reversal_count": rev_count,
        "reversal_pct": round(rev_pct, 2),
        "max_single_loss_pct": round(max_single_loss, 2),
        "worst_5_loss_avg_pct": round(worst_5_loss, 2),
    }


def run_trend_exit_simulation(
    data_map: Dict[str, pd.DataFrame],
    variant_name: str,
    trend_mode: str,
    catastrophe_sl_pct: Optional[float] = 10.0,  # None means NO catastrophe SL
    buffer_pct: float = 0.0,
    long_tp: float = 3.00,
    short_tp: float = 1.50,
    friction: float = FRICTION_PCT,
) -> pd.DataFrame:
    """
    Simulates the exact chronological state machine with the specified trend-based exit.
    
    Order of evaluation on completed 1H candle i:
      1. Catastrophe SL check (if enabled, against candle Low/High)
      2. Target Hit check (+3% Long / +1.5% Short against candle High/Low)
      3. Trend-Based Exit condition on completed candle i:
         - If triggered: fills at open_px[i+1] (Next-Bar Open, strictly causal)
         - Position becomes FLAT
      4. V2-2 Reversal check on completed candle i:
         - If opposite signal confirmed, controlled reversal at open_px[i+1]
      5. Signal execution from FLAT:
         - If FLAT and signal confirmed on candle i, opens at open_px[i+1]
    """
    all_trades = []

    for sym, raw_df in data_map.items():
        meta = SYMBOL_TICKER_MAP.get(sym, {"lot_size": 1, "sector": "UNKNOWN"})
        lot_size = meta["lot_size"]
        sector = meta["sector"]

        df = calculate_indicators(raw_df).dropna().copy()
        n = len(df)
        if n < 50:
            continue

        close = df["Close"].values
        open_px = df["Open"].values
        high_px = df["High"].values
        low_px = df["Low"].values
        ema9 = df["ema9"].values
        ema26 = df["ema26"].values
        macd = df["macd"].values
        signal = df["macd_signal"].values
        macd_hist = df["macd_histogram"].values
        times = df.index

        pos = 0  # 1 = LONG, -1 = SHORT, 0 = FLAT
        entry_px = 0.0
        entry_time = None
        entry_idx = 0
        active_pending = None
        
        # State tracking for confirmation variants
        breakout_ref_price = None

        for i in range(2, n - 1):
            curr_close = close[i]
            prev_close = close[i - 1]
            prev2_close = close[i - 2]
            curr_open = open_px[i]
            curr_high = high_px[i]
            curr_low = low_px[i]
            prev_low = low_px[i - 1]
            prev_high = high_px[i - 1]
            
            curr_ema9 = ema9[i]
            prev_ema9 = ema9[i - 1]
            prev2_ema9 = ema9[i - 2]
            
            curr_ema26 = ema26[i]
            prev_ema26 = ema26[i - 1]
            prev2_ema26 = ema26[i - 2]
            
            curr_macd = macd[i]
            prev_macd = macd[i - 1]
            curr_sig = signal[i]
            prev_sig = signal[i - 1]
            
            curr_hist = macd_hist[i]
            prev_hist = macd_hist[i - 1]

            # 1. RISK MANAGEMENT CHECKS ON COMPLETED 1H CANDLE i
            exited_this_bar = False
            if pos != 0 and i >= entry_idx:
                target_px = entry_px * (1.0 + long_tp / 100.0) if pos == 1 else entry_px * (1.0 - short_tp / 100.0)
                
                tp_hit = (curr_high >= target_px) if pos == 1 else (curr_low <= target_px)
                
                # Catastrophe SL check (only if enabled)
                sl_hit = False
                if catastrophe_sl_pct is not None and catastrophe_sl_pct > 0:
                    stop_px = entry_px * (1.0 - catastrophe_sl_pct / 100.0) if pos == 1 else entry_px * (1.0 + catastrophe_sl_pct / 100.0)
                    sl_hit = (curr_low <= stop_px) if pos == 1 else (curr_high >= stop_px)

                # Priority 1: Catastrophe SL
                if sl_hit:
                    if pos == 1:
                        x_px = curr_open if curr_open <= stop_px else max(stop_px, curr_low)
                    else:
                        x_px = curr_open if curr_open >= stop_px else min(stop_px, curr_high)
                    x_reason = "CATASTROPHE_SL"
                    exited_this_bar = True
                    x_bar_idx = i

                # Priority 2: Target Hit
                elif tp_hit:
                    if pos == 1:
                        x_px = curr_open if curr_open >= target_px else min(target_px, curr_high)
                    else:
                        x_px = curr_open if curr_open <= target_px else max(target_px, curr_low)
                    x_reason = "TARGET_HIT"
                    exited_this_bar = True
                    x_bar_idx = i

                # Priority 3: Trend-Based Exit
                elif trend_mode != "NONE":
                    trend_triggered = False

                    # A. PURE EMA CROSS (EMA9 < EMA26 for Long / EMA9 > EMA26 for Short)
                    if trend_mode == "EMA_CROSS":
                        if pos == 1:
                            trend_triggered = (prev_ema9 >= prev_ema26) and (curr_ema9 < curr_ema26)
                        else:
                            trend_triggered = (prev_ema9 <= prev_ema26) and (curr_ema9 > curr_ema26)

                    # B1. CLOSE < EMA9 CONFIRMED BY NEXT-BAR LOW BREAK
                    elif trend_mode == "CLOSE_EMA9_LOW_BREAK":
                        if pos == 1:
                            # If previous bar closed below EMA9, did current bar break its low?
                            if prev_close < prev_ema9:
                                trend_triggered = curr_close < prev_low
                        else:
                            if prev_close > prev_ema9:
                                trend_triggered = curr_close > prev_high

                    # B2. CLOSE < EMA26 CONFIRMED BY NEXT-BAR LOW BREAK
                    elif trend_mode == "CLOSE_EMA26_LOW_BREAK":
                        if pos == 1:
                            if prev_close < prev_ema26:
                                trend_triggered = curr_close < prev_low
                        else:
                            if prev_close > prev_ema26:
                                trend_triggered = curr_close > prev_high

                    # B3. CLOSE < EMA26 WITH BUFFER CONFIRMATION
                    elif trend_mode == "CLOSE_EMA26_BUFFER":
                        if pos == 1:
                            thresh = curr_ema26 * (1.0 - buffer_pct / 100.0)
                            trend_triggered = curr_close < thresh
                        else:
                            thresh = curr_ema26 * (1.0 + buffer_pct / 100.0)
                            trend_triggered = curr_close > thresh

                    # C1. 2 CONSECUTIVE CLOSES BELOW EMA9
                    elif trend_mode == "2_CLOSE_EMA9":
                        if pos == 1:
                            trend_triggered = (curr_close < curr_ema9) and (prev_close < prev_ema9)
                        else:
                            trend_triggered = (curr_close > curr_ema9) and (prev_close > prev_ema9)

                    # C2. 2 CONSECUTIVE CLOSES BELOW EMA26
                    elif trend_mode == "2_CLOSE_EMA26":
                        if pos == 1:
                            trend_triggered = (curr_close < curr_ema26) and (prev_close < prev_ema26)
                        else:
                            trend_triggered = (curr_close > curr_ema26) and (prev_close > prev_ema26)

                    # D1. DOUBLE MA BREAKDOWN (Close < EMA9 AND Close < EMA26)
                    elif trend_mode == "DOUBLE_MA_BREAKDOWN":
                        if pos == 1:
                            trend_triggered = (curr_close < curr_ema9) and (curr_close < curr_ema26)
                        else:
                            trend_triggered = (curr_close > curr_ema9) and (curr_close > curr_ema26)

                    # D2. CLOSE < EMA26 AND EMA9 < EMA26 (Baseline break + Bearish EMA cross)
                    elif trend_mode == "CLOSE_EMA26_AND_EMA_CROSS":
                        if pos == 1:
                            trend_triggered = (curr_close < curr_ema26) and (curr_ema9 < curr_ema26)
                        else:
                            trend_triggered = (curr_close > curr_ema26) and (curr_ema9 > curr_ema26)

                    # D3. CLOSE < EMA9 AND SPREAD CONTRACTING
                    elif trend_mode == "CLOSE_EMA9_SPREAD_CONTRACTING":
                        if pos == 1:
                            curr_spread = curr_ema9 - curr_ema26
                            prev_spread = prev_ema9 - prev_ema26
                            trend_triggered = (curr_close < curr_ema9) and (curr_spread < prev_spread)
                        else:
                            curr_spread = curr_ema26 - curr_ema9
                            prev_spread = prev_ema26 - prev_ema9
                            trend_triggered = (curr_close > curr_ema9) and (curr_spread < prev_spread)

                    # E1. CLOSE < EMA9 AND MACD HISTOGRAM DETERIORATING
                    elif trend_mode == "CLOSE_EMA9_MACD_HIST_DOWN":
                        if pos == 1:
                            trend_triggered = (curr_close < curr_ema9) and (curr_hist < prev_hist)
                        else:
                            trend_triggered = (curr_close > curr_ema9) and (curr_hist > prev_hist)

                    # E2. CLOSE < EMA9 AND MACD BEARISH CROSS (MACD < Signal)
                    elif trend_mode == "CLOSE_EMA9_MACD_BEAR_CROSS":
                        if pos == 1:
                            trend_triggered = (curr_close < curr_ema9) and (curr_macd < curr_sig)
                        else:
                            trend_triggered = (curr_close > curr_ema9) and (curr_macd > curr_sig)

                    # E3. CLOSE < EMA26 AND MACD HISTOGRAM DETERIORATING
                    elif trend_mode == "CLOSE_EMA26_MACD_HIST_DOWN":
                        if pos == 1:
                            trend_triggered = (curr_close < curr_ema26) and (curr_hist < prev_hist)
                        else:
                            trend_triggered = (curr_close > curr_ema26) and (curr_hist > prev_hist)

                    # E4. CLOSE < EMA26 AND MACD BEARISH CROSS (MACD < Signal)
                    elif trend_mode == "CLOSE_EMA26_MACD_BEAR_CROSS":
                        if pos == 1:
                            trend_triggered = (curr_close < curr_ema26) and (curr_macd < curr_sig)
                        else:
                            trend_triggered = (curr_close > curr_ema26) and (curr_macd > curr_sig)

                    # E5. PURE MACD LINE CROSS (MACD < Signal)
                    elif trend_mode == "PURE_MACD_CROSS":
                        if pos == 1:
                            trend_triggered = (prev_macd >= prev_sig) and (curr_macd < curr_sig)
                        else:
                            trend_triggered = (prev_macd <= prev_sig) and (curr_macd > curr_sig)

                    if trend_triggered:
                        next_idx = i + 1
                        x_px = open_px[next_idx]
                        x_reason = f"TREND_EXIT_{trend_mode}"
                        exited_this_bar = True
                        x_bar_idx = next_idx

                if exited_this_bar:
                    dir_mult = 1.0 if pos == 1 else -1.0
                    raw_pnl = ((x_px - entry_px) / entry_px) * 100.0 * dir_mult
                    net_pnl = raw_pnl - friction

                    slice_highs = high_px[entry_idx : x_bar_idx + 1]
                    slice_lows = low_px[entry_idx : x_bar_idx + 1]
                    if pos == 1:
                        mfe = ((slice_highs.max() - entry_px) / entry_px) * 100.0
                        mae = ((entry_px - slice_lows.min()) / entry_px) * 100.0
                    else:
                        mfe = ((entry_px - slice_lows.min()) / entry_px) * 100.0
                        mae = ((slice_highs.max() - entry_px) / entry_px) * 100.0

                    entry_ts = pd.to_datetime(entry_time)
                    if entry_ts.tzinfo is not None:
                        is_split = IS_SPLIT_DATE.tz_convert(entry_ts.tz)
                    else:
                        entry_ts = entry_ts.tz_localize("UTC")
                        is_split = IS_SPLIT_DATE
                    sample = "IS" if entry_ts < is_split else "OOS"

                    cal_year = str(entry_ts.year)
                    if entry_ts < pd.to_datetime("2024-09-29", utc=True):
                        roll_year = "Year 1 (Sep 23 - Sep 24)"
                    elif entry_ts < pd.to_datetime("2025-09-29", utc=True):
                        roll_year = "Year 2 (Sep 24 - Sep 25)"
                    else:
                        roll_year = "Year 3 (Sep 25 - Sep 26)"

                    all_trades.append({
                        "symbol": sym,
                        "sector": sector,
                        "direction": "LONG" if pos == 1 else "SHORT",
                        "entry_time": entry_time,
                        "exit_time": times[x_bar_idx],
                        "entry_price": entry_px,
                        "exit_price": x_px,
                        "exit_reason": x_reason,
                        "bars_held": x_bar_idx - entry_idx + 1,
                        "raw_pnl_pct": raw_pnl,
                        "net_pnl_pct": net_pnl,
                        "is_win": net_pnl > 0,
                        "mfe_pct": mfe,
                        "mae_pct": mae,
                        "sample": sample,
                        "cal_year": cal_year,
                        "roll_year": roll_year,
                    })
                    pos = 0  # FLAT

            # 2. V2-2 SIGNAL EVALUATION ON COMPLETED CANDLE i
            ema_bull = (prev_ema9 <= prev_ema26) and (curr_ema9 > curr_ema26)
            ema_bear = (prev_ema9 >= prev_ema26) and (curr_ema9 < curr_ema26)
            macd_bull = (prev_macd <= prev_sig) and (curr_macd > curr_sig)
            macd_bear = (prev_macd >= prev_sig) and (curr_macd < curr_sig)

            sig = None
            if ema_bull and macd_bull:
                sig = "BUY"
                active_pending = None
            elif ema_bear and macd_bear:
                sig = "SELL"
                active_pending = None
            else:
                if active_pending is not None:
                    active_pending["elapsed"] += 1
                    direction = active_pending["direction"]
                    leading = active_pending["leading"]
                    elapsed = active_pending["elapsed"]
                    is_invalid = False
                    if direction == "LONG":
                        if leading == "MACD" and curr_macd < curr_sig:
                            is_invalid = True
                        elif leading == "EMA" and curr_ema9 < curr_ema26:
                            is_invalid = True
                    elif direction == "SHORT":
                        if leading == "MACD" and curr_macd > curr_sig:
                            is_invalid = True

                    if is_invalid or elapsed > 2:
                        active_pending = None
                    else:
                        if direction == "LONG":
                            if leading == "MACD" and ema_bull:
                                sig = "BUY"
                                active_pending = None
                            elif leading == "EMA" and macd_bull:
                                sig = "BUY"
                                active_pending = None
                        elif direction == "SHORT":
                            if leading == "MACD" and ema_bear:
                                sig = "SELL"
                                active_pending = None

                if active_pending is None and sig is None:
                    if macd_bull and not ema_bull:
                        active_pending = {"direction": "LONG", "leading": "MACD", "elapsed": 0}
                    elif ema_bull and not macd_bull:
                        active_pending = {"direction": "LONG", "leading": "EMA", "elapsed": 0}
                    elif macd_bear and not ema_bear:
                        active_pending = {"direction": "SHORT", "leading": "MACD", "elapsed": 0}

            # 3. SIGNAL EXECUTION (ONLY IF NOT EXITED THIS CANDLE)
            if sig is not None and not exited_this_bar:
                next_entry_idx = i + 1
                next_entry_px = open_px[next_entry_idx]
                next_entry_time = times[next_entry_idx]

                if pos == 0:
                    pos = 1 if sig == "BUY" else -1
                    entry_px = next_entry_px
                    entry_time = next_entry_time
                    entry_idx = next_entry_idx
                elif (pos == 1 and sig == "SELL") or (pos == -1 and sig == "BUY"):
                    # Controlled reversal exit
                    dir_mult = 1.0 if pos == 1 else -1.0
                    raw_pnl = ((next_entry_px - entry_px) / entry_px) * 100.0 * dir_mult
                    net_pnl = raw_pnl - friction

                    slice_highs = high_px[entry_idx:next_entry_idx]
                    slice_lows = low_px[entry_idx:next_entry_idx]
                    if pos == 1:
                        mfe = ((slice_highs.max() - entry_px) / entry_px) * 100.0
                        mae = ((entry_px - slice_lows.min()) / entry_px) * 100.0
                    else:
                        mfe = ((entry_px - slice_lows.min()) / entry_px) * 100.0
                        mae = ((slice_highs.max() - entry_px) / entry_px) * 100.0

                    entry_ts = pd.to_datetime(entry_time)
                    if entry_ts.tzinfo is not None:
                        is_split = IS_SPLIT_DATE.tz_convert(entry_ts.tz)
                    else:
                        entry_ts = entry_ts.tz_localize("UTC")
                        is_split = IS_SPLIT_DATE
                    sample = "IS" if entry_ts < is_split else "OOS"

                    cal_year = str(entry_ts.year)
                    if entry_ts < pd.to_datetime("2024-09-29", utc=True):
                        roll_year = "Year 1 (Sep 23 - Sep 24)"
                    elif entry_ts < pd.to_datetime("2025-09-29", utc=True):
                        roll_year = "Year 2 (Sep 24 - Sep 25)"
                    else:
                        roll_year = "Year 3 (Sep 25 - Sep 26)"

                    all_trades.append({
                        "symbol": sym,
                        "sector": sector,
                        "direction": "LONG" if pos == 1 else "SHORT",
                        "entry_time": entry_time,
                        "exit_time": next_entry_time,
                        "entry_price": entry_px,
                        "exit_price": next_entry_px,
                        "exit_reason": "V2-2_REVERSAL",
                        "bars_held": next_entry_idx - entry_idx + 1,
                        "raw_pnl_pct": raw_pnl,
                        "net_pnl_pct": net_pnl,
                        "is_win": net_pnl > 0,
                        "mfe_pct": mfe,
                        "mae_pct": mae,
                        "sample": sample,
                        "cal_year": cal_year,
                        "roll_year": roll_year,
                    })

                    # Open reversed position
                    pos = 1 if sig == "BUY" else -1
                    entry_px = next_entry_px
                    entry_time = next_entry_time
                    entry_idx = next_entry_idx

    return pd.DataFrame(all_trades)


def classify_trend_variant(m: Dict[str, Any], oos_m: Dict[str, Any], bm_ret: float = 161.76, bm_oos: float = 30.30) -> str:
    """
    Classifies a trend-based exit variant:
      - REPLACE: Strictly outperforms benchmark on total return, OOS return, and Calmar ratio.
      - KEEP CURRENT: Underperforms benchmark return or OOS stability.
      - NEED MORE RESEARCH: Closely matches benchmark (+-3%) with interesting drawdown profile.
    """
    tot_ret = m["total_return_pct"]
    oos_ret = oos_m["total_return_pct"]
    pf = m["profit_factor"]
    max_loss = m["max_single_loss_pct"]

    if tot_ret >= bm_ret and oos_ret >= bm_oos and pf >= 1.081:
        return "REPLACE"
    elif tot_ret < bm_ret * 0.90 or oos_ret < 10.0 or pf < 1.05 or max_loss < -15.0:
        return "KEEP CURRENT"
    else:
        return "NEED MORE RESEARCH"


def main():
    print("=" * 80)
    print("TREND-BASED EXIT RESEARCH ENGINE — EMACROSSOPEN")
    print("Testing 23 Configurations across 33 NFO symbols (166,444 completed 1H bars)")
    print("=" * 80)

    # 1. Load Data
    data_map = load_or_download_all_data()
    total_bars = sum(len(df) for df in data_map.values())
    print(f"Loaded {len(data_map)} instruments, total bars: {total_bars:,}")

    # 2. Define Variants Matrix
    variants_config = [
        # --- BENCHMARKS ---
        {
            "name": "Benchmark (Current: Target + V2-2 Reversal + Fixed SL -10%)",
            "group": "F. Benchmark",
            "trend_mode": "NONE",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "Benchmark (No Catastrophe SL: Target + V2-2 Reversal Only)",
            "group": "F. Benchmark (No SL)",
            "trend_mode": "NONE",
            "catastrophe_sl_pct": None,
            "buffer_pct": 0.0,
        },

        # --- A. EMA9/EMA26 TREND-STATE EXITS ---
        {
            "name": "A1: Pure EMA Cross (EMA9 < EMA26) [with -10% SL]",
            "group": "A. Trend State",
            "trend_mode": "EMA_CROSS",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "A2: Pure EMA Cross (EMA9 < EMA26) [No Fixed SL]",
            "group": "A. Trend State",
            "trend_mode": "EMA_CROSS",
            "catastrophe_sl_pct": None,
            "buffer_pct": 0.0,
        },

        # --- B. CLOSE-BASED EMA9/EMA26 EXITS AFTER CONFIRMATION ---
        {
            "name": "B1: Close < EMA9 + Next-Bar Low Break Confirmation [with -10% SL]",
            "group": "B. Breakout Confirmation",
            "trend_mode": "CLOSE_EMA9_LOW_BREAK",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "B2: Close < EMA26 + Next-Bar Low Break Confirmation [with -10% SL]",
            "group": "B. Breakout Confirmation",
            "trend_mode": "CLOSE_EMA26_LOW_BREAK",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "B3: Close < EMA26 (Buffer 0.50%) Confirmation [with -10% SL]",
            "group": "B. Breakout Confirmation",
            "trend_mode": "CLOSE_EMA26_BUFFER",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.50,
        },

        # --- C. 2-CANDLE CONFIRMATION (BELOW EMA9 / EMA26) ---
        {
            "name": "C1: 2-Candle Closes < EMA9 [with -10% SL]",
            "group": "C. 2-Candle Confirmation",
            "trend_mode": "2_CLOSE_EMA9",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "C2: 2-Candle Closes < EMA9 [No Fixed SL]",
            "group": "C. 2-Candle Confirmation",
            "trend_mode": "2_CLOSE_EMA9",
            "catastrophe_sl_pct": None,
            "buffer_pct": 0.0,
        },
        {
            "name": "C3: 2-Candle Closes < EMA26 [with -10% SL]",
            "group": "C. 2-Candle Confirmation",
            "trend_mode": "2_CLOSE_EMA26",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "C4: 2-Candle Closes < EMA26 [No Fixed SL]",
            "group": "C. 2-Candle Confirmation",
            "trend_mode": "2_CLOSE_EMA26",
            "catastrophe_sl_pct": None,
            "buffer_pct": 0.0,
        },

        # --- D. EMA9 + EMA26 COMBINED EXIT CONDITIONS ---
        {
            "name": "D1: Double MA Breakdown (Close < EMA9 & Close < EMA26) [with -10% SL]",
            "group": "D. Combined EMA Conditions",
            "trend_mode": "DOUBLE_MA_BREAKDOWN",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "D2: Double MA Breakdown (Close < EMA9 & Close < EMA26) [No Fixed SL]",
            "group": "D. Combined EMA Conditions",
            "trend_mode": "DOUBLE_MA_BREAKDOWN",
            "catastrophe_sl_pct": None,
            "buffer_pct": 0.0,
        },
        {
            "name": "D3: Close < EMA26 AND EMA9 < EMA26 (Trend Breakdown) [with -10% SL]",
            "group": "D. Combined EMA Conditions",
            "trend_mode": "CLOSE_EMA26_AND_EMA_CROSS",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "D4: Close < EMA26 AND EMA9 < EMA26 (Trend Breakdown) [No Fixed SL]",
            "group": "D. Combined EMA Conditions",
            "trend_mode": "CLOSE_EMA26_AND_EMA_CROSS",
            "catastrophe_sl_pct": None,
            "buffer_pct": 0.0,
        },
        {
            "name": "D5: Close < EMA9 AND Spread Contracting [with -10% SL]",
            "group": "D. Combined EMA Conditions",
            "trend_mode": "CLOSE_EMA9_SPREAD_CONTRACTING",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },

        # --- E. EMA EXITS WITH MACD DETERIORATION / REVERSAL ---
        {
            "name": "E1: Close < EMA9 AND MACD Histogram Contracting [with -10% SL]",
            "group": "E. EMA + MACD Confirmation",
            "trend_mode": "CLOSE_EMA9_MACD_HIST_DOWN",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "E2: Close < EMA9 AND MACD Bearish Cross (MACD < Signal) [with -10% SL]",
            "group": "E. EMA + MACD Confirmation",
            "trend_mode": "CLOSE_EMA9_MACD_BEAR_CROSS",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "E3: Close < EMA26 AND MACD Histogram Contracting [with -10% SL]",
            "group": "E. EMA + MACD Confirmation",
            "trend_mode": "CLOSE_EMA26_MACD_HIST_DOWN",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "E4: Close < EMA26 AND MACD Bearish Cross (MACD < Signal) [with -10% SL]",
            "group": "E. EMA + MACD Confirmation",
            "trend_mode": "CLOSE_EMA26_MACD_BEAR_CROSS",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "E5: Close < EMA26 AND MACD Bearish Cross (MACD < Signal) [No Fixed SL]",
            "group": "E. EMA + MACD Confirmation",
            "trend_mode": "CLOSE_EMA26_MACD_BEAR_CROSS",
            "catastrophe_sl_pct": None,
            "buffer_pct": 0.0,
        },
        {
            "name": "E6: Pure MACD Line Cross (MACD < Signal) [with -10% SL]",
            "group": "E. EMA + MACD Confirmation",
            "trend_mode": "PURE_MACD_CROSS",
            "catastrophe_sl_pct": 10.0,
            "buffer_pct": 0.0,
        },
        {
            "name": "E7: Pure MACD Line Cross (MACD < Signal) [No Fixed SL]",
            "group": "E. EMA + MACD Confirmation",
            "trend_mode": "PURE_MACD_CROSS",
            "catastrophe_sl_pct": None,
            "buffer_pct": 0.0,
        },
    ]

    summary_rows = []
    directional_rows = []
    is_oos_rows = []
    calendar_rows = []
    rolling_rows = []

    print(f"\nSimulating {len(variants_config)} configurations...")
    for idx, cfg in enumerate(variants_config, 1):
        v_name = cfg["name"]
        print(f"[{idx:02d}/{len(variants_config):02d}] Simulating: {v_name}...")

        trades_df = run_trend_exit_simulation(
            data_map=data_map,
            variant_name=v_name,
            trend_mode=cfg["trend_mode"],
            catastrophe_sl_pct=cfg["catastrophe_sl_pct"],
            buffer_pct=cfg["buffer_pct"],
        )

        m = compute_metrics(trades_df)

        # IS / OOS breakdown
        is_df = trades_df[trades_df["sample"] == "IS"]
        oos_df = trades_df[trades_df["sample"] == "OOS"]
        is_m = compute_metrics(is_df, custom_years=21.0 / 12.0)
        oos_m = compute_metrics(oos_df, custom_years=14.5 / 12.0)

        verdict = classify_trend_variant(m, oos_m, bm_ret=161.76, bm_oos=30.30)

        summary_rows.append({
            "variant": v_name,
            "group": cfg["group"],
            "trade_count": m["trade_count"],
            "win_rate_pct": m["win_rate_pct"],
            "profit_factor": m["profit_factor"],
            "expectancy_pct": m["expectancy_pct"],
            "total_return_pct": m["total_return_pct"],
            "annualized_return_pct": m["annualized_return_pct"],
            "cagr_pct": m["cagr_pct"],
            "max_drawdown_pct": m["max_drawdown_pct"],
            "calmar_ratio": m["calmar_ratio"],
            "avg_win_pct": m["avg_win_pct"],
            "avg_loss_pct": m["avg_loss_pct"],
            "avg_bars_held": m["avg_bars_held"],
            "median_bars_held": m["median_bars_held"],
            "avg_mfe_pct": m["avg_mfe_pct"],
            "avg_mae_pct": m["avg_mae_pct"],
            "target_hit_count": m["target_hit_count"],
            "target_hit_pct": m["target_hit_pct"],
            "trend_exit_count": m["trend_exit_count"],
            "trend_exit_pct": m["trend_exit_pct"],
            "sl_hit_count": m["sl_hit_count"],
            "sl_hit_pct": m["sl_hit_pct"],
            "reversal_count": m["reversal_count"],
            "reversal_pct": m["reversal_pct"],
            "max_single_loss_pct": m["max_single_loss_pct"],
            "worst_5_loss_avg_pct": m["worst_5_loss_avg_pct"],
            "is_return_pct": is_m["total_return_pct"],
            "is_profit_factor": is_m["profit_factor"],
            "oos_return_pct": oos_m["total_return_pct"],
            "oos_profit_factor": oos_m["profit_factor"],
            "verdict": verdict,
        })

        # Directional breakdown
        for d in ["LONG", "SHORT"]:
            sub_d = trades_df[trades_df["direction"] == d]
            dm = compute_metrics(sub_d)
            dm["variant"] = v_name
            dm["direction"] = d
            directional_rows.append(dm)

        # IS / OOS breakdown
        is_m["variant"] = v_name
        is_m["sample"] = "IS"
        is_oos_rows.append(is_m)

        oos_m["variant"] = v_name
        oos_m["sample"] = "OOS"
        is_oos_rows.append(oos_m)

        # Calendar year breakdown
        for cy in ["2023", "2024", "2025", "2026"]:
            sub_cy = trades_df[trades_df["cal_year"] == cy]
            cy_years = 0.25 if cy == "2023" else (1.0 if cy in ["2024", "2025"] else 0.69)
            cym = compute_metrics(sub_cy, custom_years=cy_years)
            cym["variant"] = v_name
            cym["calendar_year"] = cy
            calendar_rows.append(cym)

        # Rolling year breakdown
        for ry in ["Year 1 (Sep 23 - Sep 24)", "Year 2 (Sep 24 - Sep 25)", "Year 3 (Sep 25 - Sep 26)"]:
            sub_ry = trades_df[trades_df["roll_year"] == ry]
            rym = compute_metrics(sub_ry, custom_years=1.0)
            rym["variant"] = v_name
            rym["rolling_year"] = ry
            rolling_rows.append(rym)

    # Save to DataFrames and CSV
    df_summary = pd.DataFrame(summary_rows)
    df_directional = pd.DataFrame(directional_rows)
    df_is_oos = pd.DataFrame(is_oos_rows)
    df_calendar = pd.DataFrame(calendar_rows)
    df_rolling = pd.DataFrame(rolling_rows)

    output_dir = CURRENT_DIR
    df_summary.to_csv(output_dir / "trend_exit_research_summary.csv", index=False)
    df_directional.to_csv(output_dir / "trend_exit_research_directional.csv", index=False)
    df_is_oos.to_csv(output_dir / "trend_exit_research_is_oos.csv", index=False)
    df_calendar.to_csv(output_dir / "trend_exit_research_calendar_years.csv", index=False)
    df_rolling.to_csv(output_dir / "trend_exit_research_rolling_years.csv", index=False)

    print("\n" + "=" * 80)
    print("SIMULATION COMPLETE — ALL DATASETS EXPORTED")
    print("=" * 80)
    print("\nSummary Table:")
    cols_to_print = ["variant", "trade_count", "win_rate_pct", "profit_factor", "total_return_pct", "max_drawdown_pct", "oos_return_pct", "max_single_loss_pct", "verdict"]
    print(df_summary[cols_to_print].to_string(index=False))


if __name__ == "__main__":
    main()
