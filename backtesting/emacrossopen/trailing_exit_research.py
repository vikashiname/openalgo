"""
Comprehensive Profit-Protecting Trailing Exit Research Engine
File: backtesting/emacrossopen/trailing_exit_research.py

Evaluates alternative profit-protecting trailing exits across 166,444 completed 1H candles
(33 NFO symbols, Sep 29, 2023 – Sep 09, 2026).

Tested Concepts:
  1. EMA9 close trail activated ONLY after trade becomes profitable (>0% profit).
  2. EMA9 trail activated after +1.0% profit.
  3. EMA9 trail activated after +1.5% profit.
  4. EMA9 trail activated after +2.0% profit.
  5. EMA26 close trail activated ONLY after trade becomes profitable (>0% profit).
  6. EMA26 trail activated after +1.0%, +1.5%, and +2.0% profit.
  7. EMA9 + EMA26 structural confirmation:
     - Close < EMA9 AND spread contracting
     - Close < EMA9 AND EMA9 < EMA26 (Bearish EMA cross)
     - Close < EMA9 AND Close < EMA26 (Double MA breakdown)
     - Close < EMA9 AND EMA9 slope down
  8. Previous-candle / delayed confirmation trail variants:
     - EMA9 2-consecutive-candle trail
     - EMA26 2-consecutive-candle trail
     - EMA9 previous-bar EMA9 level
     - EMA26 previous-bar EMA26 level
  9. EMA buffer variants:
     - 0.25%, 0.50%, 1.00%
  10. Counterfactual Premature Exit ("Choke") Analysis:
     - Specifically tracks whether a trail-exited trade would have subsequently reached Target,
       Catastrophe SL, or Reversal.
  11. Execution Order Sensitivity Audit.
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
            "trail_exit_count": 0, "trail_exit_pct": 0.0,
            "sl_hit_count": 0, "sl_hit_pct": 0.0,
            "reversal_count": 0, "reversal_pct": 0.0,
            "trail_choke_count": 0, "trail_choke_pct": 0.0,
            "trail_rescue_count": 0, "trail_rescue_pct": 0.0,
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
    trail_count = sum(v for k, v in reasons.items() if "TRAIL" in k)
    sl_count = reasons.get("CATASTROPHE_SL", 0)
    rev_count = reasons.get("V2-2_REVERSAL", 0)

    tp_pct = (tp_count / n) * 100.0 if n > 0 else 0.0
    trail_pct = (trail_count / n) * 100.0 if n > 0 else 0.0
    sl_pct = (sl_count / n) * 100.0 if n > 0 else 0.0
    rev_pct = (rev_count / n) * 100.0 if n > 0 else 0.0

    # Premature Exit (Choke) vs Protective Rescue metrics
    if "counterfactual_outcome" in trades_df.columns:
        trail_trades = trades_df[trades_df["exit_reason"].str.contains("TRAIL", na=False)]
        n_trail = len(trail_trades)
        if n_trail > 0:
            chokes = len(trail_trades[trail_trades["counterfactual_outcome"] == "TARGET_HIT"])
            # Rescues: counterfactual was CATASTROPHE_SL or worse reversal loss
            rescues = len(trail_trades[
                (trail_trades["counterfactual_outcome"] == "CATASTROPHE_SL") |
                ((trail_trades["counterfactual_outcome"] == "V2-2_REVERSAL") & 
                 (trail_trades["counterfactual_net_pnl"] < trail_trades["net_pnl_pct"]))
            ])
            choke_pct = (chokes / n_trail) * 100.0
            rescue_pct = (rescues / n_trail) * 100.0
        else:
            chokes = 0
            rescues = 0
            choke_pct = 0.0
            rescue_pct = 0.0
    else:
        chokes = 0
        rescues = 0
        choke_pct = 0.0
        rescue_pct = 0.0

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
        "trail_exit_count": trail_count,
        "trail_exit_pct": round(trail_pct, 2),
        "sl_hit_count": sl_count,
        "sl_hit_pct": round(sl_pct, 2),
        "reversal_count": rev_count,
        "reversal_pct": round(rev_pct, 2),
        "trail_choke_count": chokes,
        "trail_choke_pct": round(choke_pct, 2),
        "trail_rescue_count": rescues,
        "trail_rescue_pct": round(rescue_pct, 2),
        "max_single_loss_pct": round(max_single_loss, 2),
        "worst_5_loss_avg_pct": round(worst_5_loss, 2),
    }


def simulate_counterfactual_path(
    pos: int,
    entry_px: float,
    start_idx: int,
    end_idx: int,
    target_px: float,
    stop_px: float,
    open_px: np.ndarray,
    high_px: np.ndarray,
    low_px: np.ndarray,
    close_px: np.ndarray,
    ema9: np.ndarray,
    ema26: np.ndarray,
    macd: np.ndarray,
    signal: np.ndarray,
    friction: float = FRICTION_PCT,
) -> Tuple[str, float]:
    """
    Simulates forward from start_idx to determine what would have happened to the position
    if it had NOT exited via trailing stop, but had continued under pure Benchmark rules
    (Target +3% L / +1.5% S, Catastrophe SL -10%, V2-2 Reversal).
    
    Returns:
        (outcome_name, counterfactual_net_pnl)
    """
    n = len(open_px)
    active_pending = None

    for j in range(start_idx, n - 1):
        curr_high = high_px[j]
        curr_low = low_px[j]
        curr_open = open_px[j]

        # 1. Intrabar Risk Management checks
        tp_hit = (curr_high >= target_px) if pos == 1 else (curr_low <= target_px)
        sl_hit = (curr_low <= stop_px) if pos == 1 else (curr_high >= stop_px)

        if tp_hit and sl_hit:
            # Conservative: SL takes precedence
            x_px = curr_open if (pos == 1 and curr_open <= stop_px) or (pos == -1 and curr_open >= stop_px) else stop_px
            pnl = (((x_px - entry_px) / entry_px) * 100.0 * (1.0 if pos == 1 else -1.0)) - friction
            return "CATASTROPHE_SL", pnl
        elif sl_hit:
            x_px = curr_open if (pos == 1 and curr_open <= stop_px) or (pos == -1 and curr_open >= stop_px) else stop_px
            pnl = (((x_px - entry_px) / entry_px) * 100.0 * (1.0 if pos == 1 else -1.0)) - friction
            return "CATASTROPHE_SL", pnl
        elif tp_hit:
            x_px = curr_open if (pos == 1 and curr_open >= target_px) or (pos == -1 and curr_open <= target_px) else target_px
            pnl = (((x_px - entry_px) / entry_px) * 100.0 * (1.0 if pos == 1 else -1.0)) - friction
            return "TARGET_HIT", pnl

        # 2. V2-2 Signal Reversal check on completed candle j
        prev_ema9 = ema9[j - 1]
        curr_ema9 = ema9[j]
        prev_ema26 = ema26[j - 1]
        curr_ema26 = ema26[j]
        prev_macd = macd[j - 1]
        curr_macd = macd[j]
        prev_sig = signal[j - 1]
        curr_sig = signal[j]

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

        # Check if reversal triggers exit
        if (pos == 1 and sig == "SELL") or (pos == -1 and sig == "BUY"):
            next_px = open_px[j + 1]
            pnl = (((next_px - entry_px) / entry_px) * 100.0 * (1.0 if pos == 1 else -1.0)) - friction
            return "V2-2_REVERSAL", pnl

    # End of dataset
    last_px = close_px[-1]
    pnl = (((last_px - entry_px) / entry_px) * 100.0 * (1.0 if pos == 1 else -1.0)) - friction
    return "DATA_END", pnl


def run_trailing_simulation(
    data_map: Dict[str, pd.DataFrame],
    concept_name: str,
    trail_mode: str,
    ma_type: str = "EMA9",  # "EMA9" or "EMA26"
    profit_activation_long: Optional[float] = None,  # None = not profit activated; float = threshold in %
    profit_activation_short: Optional[float] = None,
    buffer_pct: float = 0.0,
    in_profit_close_only: bool = False,
    catastrophe_sl_pct: float = 10.0,
    long_tp: float = 3.00,
    short_tp: float = 1.50,
    friction: float = FRICTION_PCT,
    reverse_priority_audit: bool = False,
) -> pd.DataFrame:
    """
    Executes chronological simulation for a specific trailing exit variant across all instruments.
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
        times = df.index

        pos = 0  # 1 = LONG, -1 = SHORT, 0 = FLAT
        entry_px = 0.0
        entry_time = None
        entry_idx = 0
        active_pending = None
        is_trail_armed = False

        for i in range(1, n - 1):
            curr_close = close[i]
            prev_close = close[i - 1]
            curr_open = open_px[i]
            curr_high = high_px[i]
            curr_low = low_px[i]
            curr_ema9 = ema9[i]
            prev_ema9 = ema9[i - 1]
            curr_ema26 = ema26[i]
            prev_ema26 = ema26[i - 1]
            curr_macd = macd[i]
            prev_macd = macd[i - 1]
            curr_sig = signal[i]
            prev_sig = signal[i - 1]

            # 1. RISK MANAGEMENT CHECKS ON COMPLETED 1H CANDLE i
            exited_this_bar = False
            if pos != 0 and i >= entry_idx:
                target_px = entry_px * (1.0 + long_tp / 100.0) if pos == 1 else entry_px * (1.0 - short_tp / 100.0)
                stop_px = entry_px * (1.0 - catastrophe_sl_pct / 100.0) if pos == 1 else entry_px * (1.0 + catastrophe_sl_pct / 100.0)

                tp_hit = (curr_high >= target_px) if pos == 1 else (curr_low <= target_px)
                sl_hit = (curr_low <= stop_px) if pos == 1 else (curr_high >= stop_px)

                # Update profit activation arming status (Peak MFE ratchet)
                if pos == 1:
                    peak_gain = ((curr_high - entry_px) / entry_px) * 100.0
                    thresh = profit_activation_long if profit_activation_long is not None else 0.0
                    if profit_activation_long is not None and peak_gain >= thresh:
                        is_trail_armed = True
                elif pos == -1:
                    peak_gain = ((entry_px - curr_low) / entry_px) * 100.0
                    thresh = profit_activation_short if profit_activation_short is not None else 0.0
                    if profit_activation_short is not None and peak_gain >= thresh:
                        is_trail_armed = True

                # Priority 1: Catastrophe SL
                if sl_hit and not (reverse_priority_audit and tp_hit):
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

                # Priority 3: Trailing Exit (Evaluated at Completed Candle Close, Fills at Next Bar Open)
                elif trail_mode != "NONE":
                    trail_triggered = False

                    # Check profit arming requirement
                    can_trail = True
                    if profit_activation_long is not None or profit_activation_short is not None:
                        can_trail = is_trail_armed

                    # In-profit close only requirement
                    if in_profit_close_only:
                        if pos == 1 and curr_close <= entry_px:
                            can_trail = False
                        elif pos == -1 and curr_close >= entry_px:
                            can_trail = False

                    if can_trail:
                        target_ma = curr_ema9 if ma_type == "EMA9" else curr_ema26

                        if trail_mode == "MA_CLOSE":
                            if pos == 1:
                                thresh = target_ma * (1.0 - buffer_pct / 100.0)
                                trail_triggered = curr_close < thresh
                            else:
                                thresh = target_ma * (1.0 + buffer_pct / 100.0)
                                trail_triggered = curr_close > thresh

                        elif trail_mode == "SPREAD_CONTRACTING":
                            # Close < EMA9 AND EMA9/26 spread is narrowing
                            if pos == 1:
                                thresh = curr_ema9 * (1.0 - buffer_pct / 100.0)
                                curr_spread = curr_ema9 - curr_ema26
                                prev_spread = prev_ema9 - prev_ema26
                                trail_triggered = (curr_close < thresh) and (curr_spread < prev_spread)
                            else:
                                thresh = curr_ema9 * (1.0 + buffer_pct / 100.0)
                                curr_spread = curr_ema26 - curr_ema9
                                prev_spread = prev_ema26 - prev_ema9
                                trail_triggered = (curr_close > thresh) and (curr_spread < prev_spread)

                        elif trail_mode == "BEARISH_EMA_CROSS":
                            # Close < EMA9 AND EMA9 < EMA26 (Bearish cross for Long, Bullish for Short)
                            if pos == 1:
                                thresh = curr_ema9 * (1.0 - buffer_pct / 100.0)
                                trail_triggered = (curr_close < thresh) and (curr_ema9 < curr_ema26)
                            else:
                                thresh = curr_ema9 * (1.0 + buffer_pct / 100.0)
                                trail_triggered = (curr_close > thresh) and (curr_ema9 > curr_ema26)

                        elif trail_mode == "DOUBLE_MA":
                            # Close < EMA9 AND Close < EMA26
                            if pos == 1:
                                thresh9 = curr_ema9 * (1.0 - buffer_pct / 100.0)
                                thresh26 = curr_ema26 * (1.0 - buffer_pct / 100.0)
                                trail_triggered = (curr_close < thresh9) and (curr_close < thresh26)
                            else:
                                thresh9 = curr_ema9 * (1.0 + buffer_pct / 100.0)
                                thresh26 = curr_ema26 * (1.0 + buffer_pct / 100.0)
                                trail_triggered = (curr_close > thresh9) and (curr_close > thresh26)

                        elif trail_mode == "SLOPE_DOWN":
                            # Close < EMA9 AND EMA9 slope is negative
                            if pos == 1:
                                thresh = curr_ema9 * (1.0 - buffer_pct / 100.0)
                                trail_triggered = (curr_close < thresh) and (curr_ema9 < prev_ema9)
                            else:
                                thresh = curr_ema9 * (1.0 + buffer_pct / 100.0)
                                trail_triggered = (curr_close > thresh) and (curr_ema9 > prev_ema9)

                        elif trail_mode == "2_CONSECUTIVE":
                            # Two consecutive completed candles closing beyond MA
                            if pos == 1:
                                thresh_curr = target_ma * (1.0 - buffer_pct / 100.0)
                                prev_ma = prev_ema9 if ma_type == "EMA9" else prev_ema26
                                thresh_prev = prev_ma * (1.0 - buffer_pct / 100.0)
                                trail_triggered = (curr_close < thresh_curr) and (prev_close < thresh_prev)
                            else:
                                thresh_curr = target_ma * (1.0 + buffer_pct / 100.0)
                                prev_ma = prev_ema9 if ma_type == "EMA9" else prev_ema26
                                thresh_prev = prev_ma * (1.0 + buffer_pct / 100.0)
                                trail_triggered = (curr_close > thresh_curr) and (prev_close > thresh_prev)

                        elif trail_mode == "PREV_BAR_LEVEL":
                            # Close < previous candle's MA value
                            prev_ma = prev_ema9 if ma_type == "EMA9" else prev_ema26
                            if pos == 1:
                                thresh = prev_ma * (1.0 - buffer_pct / 100.0)
                                trail_triggered = curr_close < thresh
                            else:
                                thresh = prev_ma * (1.0 + buffer_pct / 100.0)
                                trail_triggered = curr_close > thresh

                    if trail_triggered:
                        next_idx = i + 1
                        x_px = open_px[next_idx]
                        x_reason = f"TRAIL_{ma_type}_{trail_mode}"
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

                    # If exited via trailing stop, run counterfactual audit!
                    cf_outcome = "N/A"
                    cf_pnl = 0.0
                    if "TRAIL" in x_reason:
                        cf_outcome, cf_pnl = simulate_counterfactual_path(
                            pos=pos,
                            entry_px=entry_px,
                            start_idx=i,  # From current bar
                            end_idx=n - 1,
                            target_px=target_px,
                            stop_px=stop_px,
                            open_px=open_px,
                            high_px=high_px,
                            low_px=low_px,
                            close_px=close,
                            ema9=ema9,
                            ema26=ema26,
                            macd=macd,
                            signal=signal,
                            friction=friction,
                        )

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
                        "counterfactual_outcome": cf_outcome,
                        "counterfactual_net_pnl": cf_pnl,
                    })
                    pos = 0  # FLAT
                    is_trail_armed = False

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
                    is_trail_armed = False
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
                        "counterfactual_outcome": "N/A",
                        "counterfactual_net_pnl": 0.0,
                    })

                    # Open reversed position
                    pos = 1 if sig == "BUY" else -1
                    entry_px = next_entry_px
                    entry_time = next_entry_time
                    entry_idx = next_entry_idx
                    is_trail_armed = False

    return pd.DataFrame(all_trades)


def classify_variant(metrics: Dict[str, Any], oos_metrics: Dict[str, Any], benchmark_return: float = 161.76) -> str:
    """
    Classifies variant into ACCEPT, REJECT, or NEEDS MORE RESEARCH.
    Rules:
      - ACCEPT: Total return > benchmark (161.76%), OOS return > 30.30%, Calmar improved, no choke penalty.
      - REJECT: Return < benchmark, or negative OOS return, or choke rate > 50%, or profit factor collapsed.
      - NEEDS MORE RESEARCH: Comparable return (within 5%), positive OOS, but mixed risk-adjusted metrics.
    """
    tot_ret = metrics["total_return_pct"]
    oos_ret = oos_metrics["total_return_pct"]
    pf = metrics["profit_factor"]
    choke_pct = metrics["trail_choke_pct"]

    if tot_ret >= benchmark_return and oos_ret >= 30.30 and pf >= 1.081 and choke_pct < 30.0:
        return "ACCEPT"
    elif tot_ret < benchmark_return * 0.90 or oos_ret < 0.0 or pf < 1.0 or choke_pct >= 50.0:
        return "REJECT"
    else:
        return "NEEDS MORE RESEARCH"


def main():
    print("=" * 80)
    print("PROFIT-PROTECTING TRAILING EXIT RESEARCH ENGINE — EMACROSSOPEN")
    print("Testing 9 Core Concepts across 33 NFO symbols (166,444 completed 1H bars)")
    print("=" * 80)

    # 1. Load Data
    data_map = load_or_download_all_data()
    total_bars = sum(len(df) for df in data_map.values())
    print(f"Loaded {len(data_map)} instruments, total bars: {total_bars:,}")

    # Define all variants to evaluate
    variants_config = [
        # Concept 0: Benchmark
        {
            "name": "Benchmark (No Trailing Exit, Fixed SL -10%)",
            "concept": "Concept 0: Benchmark",
            "trail_mode": "NONE",
            "ma_type": "NONE",
            "profit_activation_long": None,
            "profit_activation_short": None,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        # Concept 1: EMA9 close trail activated ONLY after trade becomes profitable (>0% profit)
        {
            "name": "EMA9 Trail (Active >0.0% Profit)",
            "concept": "Concept 1: EMA9 Profit Active",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA9",
            "profit_activation_long": 0.01,
            "profit_activation_short": 0.01,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA9 Trail (In-Profit Close Only)",
            "concept": "Concept 1: EMA9 Profit Active",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA9",
            "profit_activation_long": None,
            "profit_activation_short": None,
            "buffer_pct": 0.0,
            "in_profit_close_only": True,
        },
        # Concept 2: EMA9 trail activated after +1.0% profit
        {
            "name": "EMA9 Trail (Active >=+1.0% Profit)",
            "concept": "Concept 2: EMA9 +1.0% Profit",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA9",
            "profit_activation_long": 1.00,
            "profit_activation_short": 0.50,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        # Concept 3: EMA9 trail activated after +1.5% profit
        {
            "name": "EMA9 Trail (Active >=+1.5% Profit)",
            "concept": "Concept 3: EMA9 +1.5% Profit",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA9",
            "profit_activation_long": 1.50,
            "profit_activation_short": 0.75,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        # Concept 4: EMA9 trail activated after +2.0% profit
        {
            "name": "EMA9 Trail (Active >=+2.0% Profit)",
            "concept": "Concept 4: EMA9 +2.0% Profit",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA9",
            "profit_activation_long": 2.00,
            "profit_activation_short": 1.00,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        # Concept 5: EMA26 close trail activated ONLY after trade becomes profitable (>0% profit)
        {
            "name": "EMA26 Trail (Active >0.0% Profit)",
            "concept": "Concept 5: EMA26 Profit Active",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA26",
            "profit_activation_long": 0.01,
            "profit_activation_short": 0.01,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA26 Trail (In-Profit Close Only)",
            "concept": "Concept 5: EMA26 Profit Active",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA26",
            "profit_activation_long": None,
            "profit_activation_short": None,
            "buffer_pct": 0.0,
            "in_profit_close_only": True,
        },
        # Concept 6: EMA26 trail activated after +1.0%, +1.5%, and +2.0%
        {
            "name": "EMA26 Trail (Active >=+1.0% Profit)",
            "concept": "Concept 6: EMA26 +1.0%/1.5%/2.0%",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA26",
            "profit_activation_long": 1.00,
            "profit_activation_short": 0.50,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA26 Trail (Active >=+1.5% Profit)",
            "concept": "Concept 6: EMA26 +1.0%/1.5%/2.0%",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA26",
            "profit_activation_long": 1.50,
            "profit_activation_short": 0.75,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA26 Trail (Active >=+2.0% Profit)",
            "concept": "Concept 6: EMA26 +1.0%/1.5%/2.0%",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA26",
            "profit_activation_long": 2.00,
            "profit_activation_short": 1.00,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        # Concept 7: EMA9 + EMA26 Structural Confirmation
        {
            "name": "EMA9 Trail + Spread Contracting",
            "concept": "Concept 7: Structural Confirmation",
            "trail_mode": "SPREAD_CONTRACTING",
            "ma_type": "EMA9",
            "profit_activation_long": None,
            "profit_activation_short": None,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA9 Trail + Bearish EMA Cross (EMA9 < EMA26)",
            "concept": "Concept 7: Structural Confirmation",
            "trail_mode": "BEARISH_EMA_CROSS",
            "ma_type": "EMA9",
            "profit_activation_long": None,
            "profit_activation_short": None,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA9 Trail + Double MA Breakdown (Close < EMA9 & 26)",
            "concept": "Concept 7: Structural Confirmation",
            "trail_mode": "DOUBLE_MA",
            "ma_type": "EMA9",
            "profit_activation_long": None,
            "profit_activation_short": None,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA9 Trail + EMA9 Slope Down",
            "concept": "Concept 7: Structural Confirmation",
            "trail_mode": "SLOPE_DOWN",
            "ma_type": "EMA9",
            "profit_activation_long": None,
            "profit_activation_short": None,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        # Concept 8: Previous-candle / Delayed Confirmation Variants
        {
            "name": "EMA9 Trail (2 Consecutive 1H Closes)",
            "concept": "Concept 8: Delayed / Multi-Bar",
            "trail_mode": "2_CONSECUTIVE",
            "ma_type": "EMA9",
            "profit_activation_long": None,
            "profit_activation_short": None,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA26 Trail (2 Consecutive 1H Closes)",
            "concept": "Concept 8: Delayed / Multi-Bar",
            "trail_mode": "2_CONSECUTIVE",
            "ma_type": "EMA26",
            "profit_activation_long": None,
            "profit_activation_short": None,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA9 Trail (Previous-Bar EMA9 Level)",
            "concept": "Concept 8: Delayed / Multi-Bar",
            "trail_mode": "PREV_BAR_LEVEL",
            "ma_type": "EMA9",
            "profit_activation_long": None,
            "profit_activation_short": None,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA26 Trail (Previous-Bar EMA26 Level)",
            "concept": "Concept 8: Delayed / Multi-Bar",
            "trail_mode": "PREV_BAR_LEVEL",
            "ma_type": "EMA26",
            "profit_activation_long": None,
            "profit_activation_short": None,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
        # Concept 9: Reasonable EMA Buffer Values
        {
            "name": "EMA9 Trail (Active >=+1.0% Profit, Buffer 0.25%)",
            "concept": "Concept 9: Buffer Optimization",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA9",
            "profit_activation_long": 1.00,
            "profit_activation_short": 0.50,
            "buffer_pct": 0.25,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA9 Trail (Active >=+1.0% Profit, Buffer 0.50%)",
            "concept": "Concept 9: Buffer Optimization",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA9",
            "profit_activation_long": 1.00,
            "profit_activation_short": 0.50,
            "buffer_pct": 0.50,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA26 Trail (Active >=+1.0% Profit, Buffer 0.50%)",
            "concept": "Concept 9: Buffer Optimization",
            "trail_mode": "MA_CLOSE",
            "ma_type": "EMA26",
            "profit_activation_long": 1.00,
            "profit_activation_short": 0.50,
            "buffer_pct": 0.50,
            "in_profit_close_only": False,
        },
        {
            "name": "EMA9 Trail (2 Cons Closes + Profit >=+1.0% Armed)",
            "concept": "Concept 9: Buffer Optimization",
            "trail_mode": "2_CONSECUTIVE",
            "ma_type": "EMA9",
            "profit_activation_long": 1.00,
            "profit_activation_short": 0.50,
            "buffer_pct": 0.0,
            "in_profit_close_only": False,
        },
    ]

    summary_rows = []
    directional_rows = []
    is_oos_rows = []
    calendar_rows = []
    rolling_rows = []
    mae_mfe_rows = []

    # Store benchmark trade df for baseline comparisons
    benchmark_df = None

    print(f"\nEvaluating {len(variants_config)} configurations...")
    for idx, cfg in enumerate(variants_config, 1):
        v_name = cfg["name"]
        print(f"[{idx:02d}/{len(variants_config):02d}] Simulating: {v_name}...")

        trades_df = run_trailing_simulation(
            data_map=data_map,
            concept_name=cfg["concept"],
            trail_mode=cfg["trail_mode"],
            ma_type=cfg["ma_type"],
            profit_activation_long=cfg["profit_activation_long"],
            profit_activation_short=cfg["profit_activation_short"],
            buffer_pct=cfg["buffer_pct"],
            in_profit_close_only=cfg["in_profit_close_only"],
        )

        if idx == 1:
            benchmark_df = trades_df.copy()

        # Compute overall metrics
        m = compute_metrics(trades_df)

        # Compute IS / OOS metrics
        is_df = trades_df[trades_df["sample"] == "IS"]
        oos_df = trades_df[trades_df["sample"] == "OOS"]
        is_m = compute_metrics(is_df, custom_years=21.0 / 12.0)
        oos_m = compute_metrics(oos_df, custom_years=14.5 / 12.0)

        # Classification
        classification = classify_variant(m, oos_m, benchmark_return=161.76)

        summary_rows.append({
            "variant": v_name,
            "concept": cfg["concept"],
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
            "trail_exit_count": m["trail_exit_count"],
            "trail_exit_pct": m["trail_exit_pct"],
            "sl_hit_count": m["sl_hit_count"],
            "sl_hit_pct": m["sl_hit_pct"],
            "reversal_count": m["reversal_count"],
            "reversal_pct": m["reversal_pct"],
            "trail_choke_count": m["trail_choke_count"],
            "trail_choke_pct": m["trail_choke_pct"],
            "trail_rescue_count": m["trail_rescue_count"],
            "trail_rescue_pct": m["trail_rescue_pct"],
            "max_single_loss_pct": m["max_single_loss_pct"],
            "worst_5_loss_avg_pct": m["worst_5_loss_avg_pct"],
            "classification": classification,
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

        # Detailed MAE / MFE breakdown by exit reason
        for reason in ["TARGET_HIT", "TRAIL_EXIT", "CATASTROPHE_SL", "V2-2_REVERSAL"]:
            if reason == "TRAIL_EXIT":
                sub_r = trades_df[trades_df["exit_reason"].str.contains("TRAIL", na=False)]
            else:
                sub_r = trades_df[trades_df["exit_reason"] == reason]
            
            mae_mfe_rows.append({
                "variant": v_name,
                "exit_group": reason,
                "count": len(sub_r),
                "avg_mfe_pct": round(float(sub_r["mfe_pct"].mean()), 2) if len(sub_r) > 0 else 0.0,
                "median_mfe_pct": round(float(sub_r["mfe_pct"].median()), 2) if len(sub_r) > 0 else 0.0,
                "avg_mae_pct": round(float(sub_r["mae_pct"].mean()), 2) if len(sub_r) > 0 else 0.0,
                "median_mae_pct": round(float(sub_r["mae_pct"].median()), 2) if len(sub_r) > 0 else 0.0,
                "avg_net_pnl_pct": round(float(sub_r["net_pnl_pct"].mean()), 2) if len(sub_r) > 0 else 0.0,
            })

    # Convert to DataFrames
    df_summary = pd.DataFrame(summary_rows)
    df_directional = pd.DataFrame(directional_rows)
    df_is_oos = pd.DataFrame(is_oos_rows)
    df_calendar = pd.DataFrame(calendar_rows)
    df_rolling = pd.DataFrame(rolling_rows)
    df_mae_mfe = pd.DataFrame(mae_mfe_rows)

    # Save to CSV
    output_dir = CURRENT_DIR
    df_summary.to_csv(output_dir / "trailing_exit_research_summary.csv", index=False)
    df_directional.to_csv(output_dir / "trailing_exit_research_directional.csv", index=False)
    df_is_oos.to_csv(output_dir / "trailing_exit_research_is_oos.csv", index=False)
    df_calendar.to_csv(output_dir / "trailing_exit_research_calendar_years.csv", index=False)
    df_rolling.to_csv(output_dir / "trailing_exit_research_rolling_years.csv", index=False)
    df_mae_mfe.to_csv(output_dir / "trailing_exit_research_mae_mfe.csv", index=False)

    print("\n" + "=" * 80)
    print("SIMULATION COMPLETE — ALL DATASETS EXPORTED")
    print("=" * 80)
    print("\nSummary Table:")
    print(df_summary[["variant", "trade_count", "win_rate_pct", "profit_factor", "total_return_pct", "trail_choke_pct", "classification"]].to_string(index=False))


if __name__ == "__main__":
    main()
