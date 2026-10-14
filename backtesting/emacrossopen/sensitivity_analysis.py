"""
EMACROSSOPEN Target and Catastrophe-SL Sensitivity & Robustness Engine
File: backtesting/emacrossopen/sensitivity_analysis.py

Independently tests Target and Catastrophe-SL sensitivity across the full available
historical dataset (166,444 completed 1H bars, 33 NFO symbols, Sep 2023 - Sep 2026).

Preserves exact production emacrossopen.py logic:
  - 1H completed candles
  - EMA9/EMA26, MACD 12/26/9
  - Asymmetric V2-2 2-candle confirmation window
  - Long: SAME_CANDLE, MACD_THEN_EMA, EMA_THEN_MACD
  - Short: SAME_CANDLE, MACD_THEN_EMA (EMA_FIRST strictly rejected)
  - Chronological bar-by-bar state machine with FLAT states on Target/SL exit
  - Priority: 1. Catastrophe SL, 2. Target, 3. Opposite Reversal
  - Round-trip transaction friction: 0.07%

Evaluates:
  - Catastrophe SL variants: No-SL, -6%, -7%, -8%, -9%, -10%
  - ATR-based SL variants: 2.0x, 2.5x, 3.0x, 3.5x, 4.0x, 5.0x, 6.0x, 8.0x, 10.0x, 12.0x ATR
  - Target sensitivity: No-Target, 2.0%/1.0%, 2.5%/1.25%, 3.0%/1.5%, 4.0%/2.0%, 3.0%/3.0%
  - Separate LONG/SHORT analysis for all variants
  - Full metrics: MFE, MAE, Holding Time, Win Rate, Profit Factor, Expectancy, Total Return, CAGR, Max DD
  - In-Sample (IS) vs Out-of-Sample (OOS) walk-forward stability
  - Conditional MAE recovery probability analysis
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

FRICTION_PCT = 0.07  # 0.07% round-trip friction
IS_SPLIT_DATE = pd.to_datetime("2025-07-01", utc=True)
TOTAL_DAYS = 1076.0  # Sep 29, 2023 to Sep 09, 2026
YEARS = TOTAL_DAYS / 365.25  # ~2.946 years


def compute_metrics(trades_df: pd.DataFrame) -> Dict[str, Any]:
    """Computes comprehensive quantitative metrics for a given subset of trades."""
    if trades_df.empty:
        return {
            "trade_count": 0, "win_rate_pct": 0.0, "profit_factor": 0.0,
            "expectancy_pct": 0.0, "total_return_pct": 0.0, "annualized_return_pct": 0.0,
            "cagr_pct": 0.0, "max_drawdown_pct": 0.0, "calmar_ratio": 0.0,
            "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
            "avg_bars_held": 0.0, "median_bars_held": 0.0, "max_bars_held": 0.0,
            "avg_mfe_pct": 0.0, "avg_mae_pct": 0.0,
            "target_hit_count": 0, "target_hit_pct": 0.0,
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
    ann_return = total_return / YEARS
    if total_return > -100.0:
        cagr = ((1.0 + total_return / 100.0) ** (1.0 / YEARS) - 1.0) * 100.0
    else:
        cagr = -100.0
    calmar = (ann_return / max_dd) if max_dd > 0 else 0.0

    # Holding periods
    bars = trades_df["bars_held"].values
    avg_bars = float(np.mean(bars)) if len(bars) > 0 else 0.0
    median_bars = float(np.median(bars)) if len(bars) > 0 else 0.0
    max_bars = float(np.max(bars)) if len(bars) > 0 else 0.0

    # MFE / MAE
    avg_mfe = float(trades_df["mfe_pct"].mean()) if "mfe_pct" in trades_df.columns else 0.0
    avg_mae = float(trades_df["mae_pct"].mean()) if "mae_pct" in trades_df.columns else 0.0

    # Exit reason counts
    reasons = trades_df["exit_reason"].value_counts().to_dict()
    tp_count = reasons.get("TARGET_HIT", 0)
    sl_count = reasons.get("CATASTROPHE_SL", 0)
    rev_count = reasons.get("V2-2_REVERSAL", 0)

    tp_pct = (tp_count / n) * 100.0 if n > 0 else 0.0
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
        "max_bars_held": int(max_bars),
        "avg_mfe_pct": round(avg_mfe, 2),
        "avg_mae_pct": round(avg_mae, 2),
        "target_hit_count": tp_count,
        "target_hit_pct": round(tp_pct, 2),
        "sl_hit_count": sl_count,
        "sl_hit_pct": round(sl_pct, 2),
        "reversal_count": rev_count,
        "reversal_pct": round(rev_pct, 2),
        "max_single_loss_pct": round(max_single_loss, 2),
        "worst_5_loss_avg_pct": round(worst_5_loss, 2),
    }


def run_state_machine_simulation(
    data_map: Dict[str, pd.DataFrame],
    long_tp: Optional[float] = 3.00,
    short_tp: Optional[float] = 1.50,
    sl_mode: Optional[str] = "fixed",  # "fixed", "atr", or None
    sl_val: Optional[float] = 6.00,    # fixed % if "fixed", atr_mult if "atr"
    friction: float = FRICTION_PCT,
) -> pd.DataFrame:
    """
    Executes an exact chronological, bar-by-bar state machine simulation matching
    emacrossopen.py with support for fixed percentage SL or ATR-based SL.
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
        hist = df["macd_histogram"].values
        atr = df["atr14"].values
        times = df.index

        pos = 0  # 1 = LONG, -1 = SHORT, 0 = FLAT
        entry_px = 0.0
        entry_time = None
        entry_idx = 0
        entry_atr = 0.0
        active_pending = None

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

            # 1. RISK MANAGEMENT CHECK ON COMPLETED 1H CANDLE (BEFORE REVERSAL)
            exited_this_bar = False
            if pos != 0 and i >= entry_idx:
                # Compute Target Price
                if pos == 1:
                    target_px = entry_px * (1.0 + long_tp / 100.0) if long_tp is not None else None
                else:
                    target_px = entry_px * (1.0 - short_tp / 100.0) if short_tp is not None else None

                # Compute Stop Loss Price
                stop_px = None
                if sl_mode == "fixed" and sl_val is not None:
                    if pos == 1:
                        stop_px = entry_px * (1.0 - sl_val / 100.0)
                    else:
                        stop_px = entry_px * (1.0 + sl_val / 100.0)
                elif sl_mode == "atr" and sl_val is not None:
                    if pos == 1:
                        stop_px = entry_px - (sl_val * entry_atr)
                    else:
                        stop_px = entry_px + (sl_val * entry_atr)

                # Check triggers
                if pos == 1:
                    tp_hit = (target_px is not None) and (curr_high >= target_px)
                    sl_hit = (stop_px is not None) and (curr_low <= stop_px)

                    if tp_hit and sl_hit:
                        # Conservative priority: SL first unless open breached target
                        if curr_open >= target_px:
                            x_px = curr_open
                            x_reason = "TARGET_HIT"
                        elif curr_open <= stop_px:
                            x_px = curr_open
                            x_reason = "CATASTROPHE_SL"
                        else:
                            x_px = stop_px
                            x_reason = "CATASTROPHE_SL"
                        exited_this_bar = True
                    elif sl_hit:
                        x_px = curr_open if curr_open <= stop_px else max(stop_px, curr_low)
                        x_reason = "CATASTROPHE_SL"
                        exited_this_bar = True
                    elif tp_hit:
                        x_px = curr_open if curr_open >= target_px else min(target_px, curr_high)
                        x_reason = "TARGET_HIT"
                        exited_this_bar = True

                else:  # pos == -1 (SHORT)
                    tp_hit = (target_px is not None) and (curr_low <= target_px)
                    sl_hit = (stop_px is not None) and (curr_high >= stop_px)

                    if tp_hit and sl_hit:
                        if curr_open <= target_px:
                            x_px = curr_open
                            x_reason = "TARGET_HIT"
                        elif curr_open >= stop_px:
                            x_px = curr_open
                            x_reason = "CATASTROPHE_SL"
                        else:
                            x_px = stop_px
                            x_reason = "CATASTROPHE_SL"
                        exited_this_bar = True
                    elif sl_hit:
                        x_px = curr_open if curr_open >= stop_px else min(stop_px, curr_high)
                        x_reason = "CATASTROPHE_SL"
                        exited_this_bar = True
                    elif tp_hit:
                        x_px = curr_open if curr_open <= target_px else max(target_px, curr_low)
                        x_reason = "TARGET_HIT"
                        exited_this_bar = True

                if exited_this_bar:
                    dir_mult = 1.0 if pos == 1 else -1.0
                    raw_pnl = ((x_px - entry_px) / entry_px) * 100.0 * dir_mult
                    net_pnl = raw_pnl - friction

                    slice_highs = high_px[entry_idx : i + 1]
                    slice_lows = low_px[entry_idx : i + 1]
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

                    all_trades.append({
                        "symbol": sym,
                        "sector": sector,
                        "direction": "LONG" if pos == 1 else "SHORT",
                        "entry_time": entry_time,
                        "exit_time": times[i],
                        "entry_price": entry_px,
                        "exit_price": x_px,
                        "exit_reason": x_reason,
                        "bars_held": i - entry_idx + 1,
                        "raw_pnl_pct": raw_pnl,
                        "net_pnl_pct": net_pnl,
                        "is_win": net_pnl > 0,
                        "mfe_pct": mfe,
                        "mae_pct": mae,
                        "sample": sample,
                        "entry_atr": entry_atr,
                        "entry_atr_pct": (entry_atr / entry_px) * 100.0 if entry_px > 0 else 0.0,
                    })
                    pos = 0  # FLAT

            # 2. V2-2 SIGNAL EVALUATION ON COMPLETED CANDLE i
            ema_bull = (prev_ema9 <= prev_ema26) and (curr_ema9 > curr_ema26)
            ema_bear = (prev_ema9 >= prev_ema26) and (curr_ema9 < curr_ema26)
            macd_bull = (prev_macd <= prev_sig) and (curr_macd > curr_sig)
            macd_bear = (prev_macd >= prev_sig) and (curr_macd < curr_sig)

            sig = None
            trig = None
            conf_delay = 0

            if ema_bull and macd_bull:
                sig = "BUY"
                trig = "SAME_CANDLE"
                conf_delay = 0
                active_pending = None
            elif ema_bear and macd_bear:
                sig = "SELL"
                trig = "SAME_CANDLE"
                conf_delay = 0
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
                                trig = "MACD_THEN_EMA"
                                conf_delay = elapsed
                                active_pending = None
                            elif leading == "EMA" and macd_bull:
                                sig = "BUY"
                                trig = "EMA_THEN_MACD"
                                conf_delay = elapsed
                                active_pending = None
                        elif direction == "SHORT":
                            if leading == "MACD" and ema_bear:
                                sig = "SELL"
                                trig = "MACD_THEN_EMA"
                                conf_delay = elapsed
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
                    entry_atr = atr[i]
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

                    all_trades.append({
                        "symbol": sym,
                        "sector": sector,
                        "direction": "LONG" if pos == 1 else "SHORT",
                        "entry_time": entry_time,
                        "exit_time": next_entry_time,
                        "entry_price": entry_px,
                        "exit_price": next_entry_px,
                        "exit_reason": "V2-2_REVERSAL",
                        "bars_held": next_entry_idx - entry_idx,
                        "raw_pnl_pct": raw_pnl,
                        "net_pnl_pct": net_pnl,
                        "is_win": net_pnl > 0,
                        "mfe_pct": mfe,
                        "mae_pct": mae,
                        "sample": sample,
                        "entry_atr": entry_atr,
                        "entry_atr_pct": (entry_atr / entry_px) * 100.0 if entry_px > 0 else 0.0,
                    })

                    pos = 1 if sig == "BUY" else -1
                    entry_px = next_entry_px
                    entry_time = next_entry_time
                    entry_idx = next_entry_idx
                    entry_atr = atr[i]
                else:
                    # Same direction: duplicate skipped
                    pass

    return pd.DataFrame(all_trades)


def run_comprehensive_sensitivity_study():
    print("=" * 80)
    print("🚀 STARTING EMACROSSOPEN TARGET & CATASTROPHE-SL SENSITIVITY STUDY")
    print("=" * 80)

    data_map = load_or_download_all_data()
    print(f"Loaded {len(data_map)} symbols with {sum(len(v) for v in data_map.values())} total completed 1H candles.\n")

    # -------------------------------------------------------------------------
    # PART 1: STOP-LOSS SENSITIVITY VARIANTS (BASELINE TARGET: +3.0% L / +1.5% S)
    # -------------------------------------------------------------------------
    sl_configs = [
        {"name": "No-SL (Reversal Only)", "mode": None, "val": None},
        {"name": "Fixed SL -6.0% (Current Live)", "mode": "fixed", "val": 6.0},
        {"name": "Fixed SL -7.0%", "mode": "fixed", "val": 7.0},
        {"name": "Fixed SL -8.0%", "mode": "fixed", "val": 8.0},
        {"name": "Fixed SL -9.0%", "mode": "fixed", "val": 9.0},
        {"name": "Fixed SL -10.0%", "mode": "fixed", "val": 10.0},
        {"name": "ATR SL 2.0x (~1.4% avg)", "mode": "atr", "val": 2.0},
        {"name": "ATR SL 2.5x (~1.8% avg)", "mode": "atr", "val": 2.5},
        {"name": "ATR SL 3.0x (~2.1% avg)", "mode": "atr", "val": 3.0},
        {"name": "ATR SL 3.5x (~2.5% avg)", "mode": "atr", "val": 3.5},
        {"name": "ATR SL 4.0x (~2.8% avg)", "mode": "atr", "val": 4.0},
        {"name": "ATR SL 5.0x (~3.5% avg)", "mode": "atr", "val": 5.0},
        {"name": "ATR SL 6.0x (~4.3% avg)", "mode": "atr", "val": 6.0},
        {"name": "ATR SL 8.0x (~5.7% avg)", "mode": "atr", "val": 8.0},
        {"name": "ATR SL 10.0x (~7.1% avg)", "mode": "atr", "val": 10.0},
        {"name": "ATR SL 12.0x (~8.5% avg)", "mode": "atr", "val": 12.0},
    ]

    sl_master_rows = []
    directional_rows = []
    walk_forward_rows = []
    variant_trades_map = {}

    print("Evaluating 16 Stop-Loss variants on baseline target (+3.0% Long / +1.5% Short)...")
    for cfg in sl_configs:
        name = cfg["name"]
        mode = cfg["mode"]
        val = cfg["val"]

        trades_df = run_state_machine_simulation(
            data_map, long_tp=3.00, short_tp=1.50, sl_mode=mode, sl_val=val, friction=FRICTION_PCT
        )
        variant_trades_map[name] = trades_df

        # Overall metrics
        m_all = compute_metrics(trades_df)
        m_long = compute_metrics(trades_df[trades_df["direction"] == "LONG"]) if not trades_df.empty else {}
        m_short = compute_metrics(trades_df[trades_df["direction"] == "SHORT"]) if not trades_df.empty else {}
        m_is = compute_metrics(trades_df[trades_df["sample"] == "IS"]) if not trades_df.empty else {}
        m_oos = compute_metrics(trades_df[trades_df["sample"] == "OOS"]) if not trades_df.empty else {}

        sl_master_rows.append({
            "variant": name,
            "sl_mode": str(mode),
            "sl_param": val if val is not None else "None",
            "trades": m_all["trade_count"],
            "win_rate_pct": m_all["win_rate_pct"],
            "profit_factor": m_all["profit_factor"],
            "expectancy_pct": m_all["expectancy_pct"],
            "total_return_pct": m_all["total_return_pct"],
            "annualized_return_pct": m_all["annualized_return_pct"],
            "cagr_pct": m_all["cagr_pct"],
            "max_drawdown_pct": m_all["max_drawdown_pct"],
            "calmar_ratio": m_all["calmar_ratio"],
            "target_hit_pct": m_all["target_hit_pct"],
            "target_hit_count": m_all["target_hit_count"],
            "sl_hit_pct": m_all["sl_hit_pct"],
            "sl_hit_count": m_all["sl_hit_count"],
            "reversal_pct": m_all["reversal_pct"],
            "reversal_count": m_all["reversal_count"],
            "avg_bars_held": m_all["avg_bars_held"],
            "median_bars_held": m_all["median_bars_held"],
            "avg_mfe_pct": m_all["avg_mfe_pct"],
            "avg_mae_pct": m_all["avg_mae_pct"],
            "max_single_loss_pct": m_all["max_single_loss_pct"],
            "worst_5_loss_avg_pct": m_all["worst_5_loss_avg_pct"],
        })

        # Directional breakdown
        for d_name, d_m in [("LONG", m_long), ("SHORT", m_short)]:
            directional_rows.append({
                "variant": name,
                "direction": d_name,
                "trades": d_m["trade_count"],
                "win_rate_pct": d_m["win_rate_pct"],
                "profit_factor": d_m["profit_factor"],
                "expectancy_pct": d_m["expectancy_pct"],
                "total_return_pct": d_m["total_return_pct"],
                "max_drawdown_pct": d_m["max_drawdown_pct"],
                "target_hit_pct": d_m["target_hit_pct"],
                "sl_hit_pct": d_m["sl_hit_pct"],
                "reversal_pct": d_m["reversal_pct"],
                "avg_bars_held": d_m["avg_bars_held"],
                "avg_mfe_pct": d_m["avg_mfe_pct"],
                "avg_mae_pct": d_m["avg_mae_pct"],
                "max_single_loss_pct": d_m["max_single_loss_pct"],
            })

        # Walk-Forward breakdown
        wf_pf_ratio = round(m_oos["profit_factor"] / m_is["profit_factor"], 3) if m_is["profit_factor"] > 0 else 0.0
        walk_forward_rows.append({
            "variant": name,
            "is_trades": m_is["trade_count"],
            "is_return_pct": m_is["total_return_pct"],
            "is_pf": m_is["profit_factor"],
            "is_win_rate_pct": m_is["win_rate_pct"],
            "is_expectancy_pct": m_is["expectancy_pct"],
            "oos_trades": m_oos["trade_count"],
            "oos_return_pct": m_oos["total_return_pct"],
            "oos_pf": m_oos["profit_factor"],
            "oos_win_rate_pct": m_oos["win_rate_pct"],
            "oos_expectancy_pct": m_oos["expectancy_pct"],
            "wf_pf_ratio": wf_pf_ratio,
            "wf_win_rate_diff": round(m_oos["win_rate_pct"] - m_is["win_rate_pct"], 2),
        })

    sl_master_df = pd.DataFrame(sl_master_rows)
    directional_df = pd.DataFrame(directional_rows)
    walk_forward_df = pd.DataFrame(walk_forward_rows)

    sl_master_df.to_csv(CURRENT_DIR / "sensitivity_sl_variants.csv", index=False)
    directional_df.to_csv(CURRENT_DIR / "sensitivity_directional_breakdown.csv", index=False)
    walk_forward_df.to_csv(CURRENT_DIR / "sensitivity_walk_forward_breakdown.csv", index=False)
    print("  ✓ Saved sensitivity_sl_variants.csv")
    print("  ✓ Saved sensitivity_directional_breakdown.csv")
    print("  ✓ Saved sensitivity_walk_forward_breakdown.csv")

    # -------------------------------------------------------------------------
    # PART 2: TARGET SENSITIVITY MATRIX (TARGET x SL)
    # -------------------------------------------------------------------------
    print("\nEvaluating Target Sensitivity Matrix across key SL candidates...")
    target_configs = [
        {"target_name": "No-Target", "long_tp": None, "short_tp": None},
        {"target_name": "Tight (+2.0% L / +1.0% S)", "long_tp": 2.00, "short_tp": 1.00},
        {"target_name": "Moderate (+2.5% L / +1.25% S)", "long_tp": 2.50, "short_tp": 1.25},
        {"target_name": "Baseline (+3.0% L / +1.5% S)", "long_tp": 3.00, "short_tp": 1.50},
        {"target_name": "Wide (+4.0% L / +2.0% S)", "long_tp": 4.00, "short_tp": 2.00},
        {"target_name": "Symmetric (+3.0% L / +3.0% S)", "long_tp": 3.00, "short_tp": 3.00},
    ]

    selected_sls = [
        {"sl_name": "No-SL", "mode": None, "val": None},
        {"sl_name": "Fixed SL -6.0%", "mode": "fixed", "val": 6.0},
        {"sl_name": "Fixed SL -8.0%", "mode": "fixed", "val": 8.0},
        {"sl_name": "Fixed SL -10.0%", "mode": "fixed", "val": 10.0},
        {"sl_name": "ATR SL 8.0x", "mode": "atr", "val": 8.0},
        {"sl_name": "ATR SL 10.0x", "mode": "atr", "val": 10.0},
    ]

    target_sl_rows = []
    for t_cfg in target_configs:
        t_name = t_cfg["target_name"]
        l_tp = t_cfg["long_tp"]
        s_tp = t_cfg["short_tp"]

        for s_cfg in selected_sls:
            s_name = s_cfg["sl_name"]
            s_mode = s_cfg["mode"]
            s_val = s_cfg["val"]

            t_df = run_state_machine_simulation(
                data_map, long_tp=l_tp, short_tp=s_tp, sl_mode=s_mode, sl_val=s_val, friction=FRICTION_PCT
            )
            m = compute_metrics(t_df)

            target_sl_rows.append({
                "target_variant": t_name,
                "sl_variant": s_name,
                "trades": m["trade_count"],
                "win_rate_pct": m["win_rate_pct"],
                "profit_factor": m["profit_factor"],
                "expectancy_pct": m["expectancy_pct"],
                "total_return_pct": m["total_return_pct"],
                "cagr_pct": m["cagr_pct"],
                "max_drawdown_pct": m["max_drawdown_pct"],
                "calmar_ratio": m["calmar_ratio"],
                "target_hit_pct": m["target_hit_pct"],
                "sl_hit_pct": m["sl_hit_pct"],
                "reversal_pct": m["reversal_pct"],
                "avg_bars_held": m["avg_bars_held"],
                "max_single_loss_pct": m["max_single_loss_pct"],
            })

    target_sl_df = pd.DataFrame(target_sl_rows)
    target_sl_df.to_csv(CURRENT_DIR / "sensitivity_target_sl_grid.csv", index=False)
    print("  ✓ Saved sensitivity_target_sl_grid.csv")

    # -------------------------------------------------------------------------
    # PART 3: CONDITIONAL MAE RECOVERY PROBABILITY ANALYSIS (MATHEMATICAL PROOF)
    # -------------------------------------------------------------------------
    print("\nComputing Conditional MAE Recovery Probability Analysis...")
    no_sl_trades = variant_trades_map["No-SL (Reversal Only)"]
    mae_thresholds = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0]
    mae_recovery_rows = []

    total_no_sl = len(no_sl_trades)

    for th in mae_thresholds:
        # Trades that breached this adverse threshold during their lifecycle
        subset = no_sl_trades[no_sl_trades["mae_pct"] >= th]
        sub_n = len(subset)
        if sub_n == 0:
            continue

        share_of_all = (sub_n / total_no_sl) * 100.0
        # What happened to them without stop-loss?
        recovered_wins = len(subset[subset["net_pnl_pct"] > 0])
        recovery_win_rate = (recovered_wins / sub_n) * 100.0

        target_hits = len(subset[subset["exit_reason"] == "TARGET_HIT"])
        target_recovery_rate = (target_hits / sub_n) * 100.0

        reversals = len(subset[subset["exit_reason"] == "V2-2_REVERSAL"])
        reversal_rate = (reversals / sub_n) * 100.0

        # Mean eventual return if left unstopped
        actual_mean_pnl = float(subset["net_pnl_pct"].mean())
        actual_total_pnl = float(subset["net_pnl_pct"].sum())

        # If hard stopped at threshold:
        # PnL would be approximately (-th - friction)
        stop_pnl_per_trade = - (th + FRICTION_PCT)
        stopped_total_pnl = sub_n * stop_pnl_per_trade

        # Net Alpha Delta: actual total pnl - stopped total pnl
        # If delta > 0: allowing trades to run produced MORE money than stopping them!
        # If delta < 0: hard stopping them SAVED capital!
        alpha_delta = actual_total_pnl - stopped_total_pnl
        delta_per_trade = actual_mean_pnl - stop_pnl_per_trade

        # Catastrophic runaway count: trades that ended worse than (-th * 1.5)
        runaway_trades = len(subset[subset["net_pnl_pct"] < -th * 1.5])
        runaway_pct = (runaway_trades / sub_n) * 100.0

        mae_recovery_rows.append({
            "mae_threshold_pct": th,
            "trades_breached": sub_n,
            "share_of_all_trades_pct": round(share_of_all, 2),
            "recovery_win_rate_pct": round(recovery_win_rate, 2),
            "target_recovery_rate_pct": round(target_recovery_rate, 2),
            "unstopped_mean_pnl_pct": round(actual_mean_pnl, 2),
            "unstopped_total_pnl_pct": round(actual_total_pnl, 2),
            "hard_stopped_pnl_pct": round(stop_pnl_per_trade, 2),
            "hard_stopped_total_pnl_pct": round(stopped_total_pnl, 2),
            "alpha_delta_total_pct": round(alpha_delta, 2),
            "alpha_delta_per_trade_pct": round(delta_per_trade, 2),
            "runaway_breaches_count": runaway_trades,
            "runaway_breaches_pct": round(runaway_pct, 2),
            "efficacy_verdict": "SL HARMS PORTFOLIO" if alpha_delta > 0 else "SL PROTECTS PORTFOLIO",
        })

    mae_recovery_df = pd.DataFrame(mae_recovery_rows)
    mae_recovery_df.to_csv(CURRENT_DIR / "sensitivity_mae_recovery_analysis.csv", index=False)
    print("  ✓ Saved sensitivity_mae_recovery_analysis.csv")

    # -------------------------------------------------------------------------
    # PART 4: CROSS-SYMBOL CONSISTENCY FOR KEY VARIANTS
    # -------------------------------------------------------------------------
    print("\nComputing Symbol-by-Symbol consistency for key variants...")
    key_variant_names = [
        "No-SL (Reversal Only)",
        "Fixed SL -6.0% (Current Live)",
        "Fixed SL -8.0%",
        "Fixed SL -10.0%",
        "ATR SL 8.0x (~5.7% avg)",
        "ATR SL 10.0x (~7.1% avg)",
    ]

    sym_rows = []
    for sym in data_map.keys():
        sec = SYMBOL_TICKER_MAP.get(sym, {}).get("sector", "UNKNOWN")
        row = {"symbol": sym, "sector": sec}
        for v_name in key_variant_names:
            v_trades = variant_trades_map[v_name]
            sym_sub = v_trades[v_trades["symbol"] == sym]
            if sym_sub.empty:
                row[f"{v_name}_return"] = 0.0
                row[f"{v_name}_wr"] = 0.0
                row[f"{v_name}_trades"] = 0
            else:
                row[f"{v_name}_return"] = round(float(sym_sub["net_pnl_pct"].sum()), 2)
                row[f"{v_name}_wr"] = round((len(sym_sub[sym_sub["net_pnl_pct"] > 0]) / len(sym_sub)) * 100.0, 1)
                row[f"{v_name}_trades"] = len(sym_sub)
        sym_rows.append(row)

    sym_df = pd.DataFrame(sym_rows)
    sym_df.to_csv(CURRENT_DIR / "sensitivity_symbol_consistency.csv", index=False)
    print("  ✓ Saved sensitivity_symbol_consistency.csv")

    print("\n" + "=" * 80)
    print("✅ COMPREHENSIVE SENSITIVITY STUDY COMPLETE!")
    print("=" * 80)


if __name__ == "__main__":
    run_comprehensive_sensitivity_study()
