"""
EMA9 Candle-Close Trailing Exit Research Engine
File: backtesting/emacrossopen/ema9_trailing_research.py

Researches EMA9 candle-close trailing exit logic on completed 1H candles:
  - Reference: Exact production emacrossopen.py logic
  - Targets: +3.00% Long / +1.50% Short from actual fill price
  - Catastrophe SL: -10.00% emergency backup from actual fill price
  - V2-2 Reversal: Opposite confirmed signal reversal
  - Friction: 0.07% round-trip
  - Zero synthetic OI, completed 1H candles only, no lookahead

Variants evaluated:
  - Benchmark: Target + V2-2 Reversal + Fixed -10% Catastrophe SL (No EMA9 exit)
  - EMA9 Buffer 0.00% (Pure Close < EMA9 for Long / Close > EMA9 for Short)
  - EMA9 Buffer 0.25%
  - EMA9 Buffer 0.50%
  - EMA9 Buffer 1.00%
  - Sensitivity buffers: 1.50%, 2.00%

Provides:
  - Overall, LONG, SHORT breakdowns
  - Rolling Year and Calendar Year breakdowns
  - In-Sample (IS) vs Out-of-Sample (OOS) walk-forward metrics
  - MFE, MAE, holding periods, exit reason distributions
  - Profit retention vs premature exit trade-off analysis
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
            "ema9_exit_count": 0, "ema9_exit_pct": 0.0,
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
    ema_count = reasons.get("EMA9_TRAIL_EXIT", 0)
    sl_count = reasons.get("CATASTROPHE_SL", 0)
    rev_count = reasons.get("V2-2_REVERSAL", 0)

    tp_pct = (tp_count / n) * 100.0 if n > 0 else 0.0
    ema_pct = (ema_count / n) * 100.0 if n > 0 else 0.0
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
        "ema9_exit_count": ema_count,
        "ema9_exit_pct": round(ema_pct, 2),
        "sl_hit_count": sl_count,
        "sl_hit_pct": round(sl_pct, 2),
        "reversal_count": rev_count,
        "reversal_pct": round(rev_pct, 2),
        "max_single_loss_pct": round(max_single_loss, 2),
        "worst_5_loss_avg_pct": round(worst_5_loss, 2),
    }


def run_ema9_trailing_simulation(
    data_map: Dict[str, pd.DataFrame],
    enable_ema9_exit: bool = True,
    ema9_buffer_pct: float = 0.0,
    catastrophe_sl_pct: float = 10.0,
    long_tp: float = 3.00,
    short_tp: float = 1.50,
    friction: float = FRICTION_PCT,
) -> pd.DataFrame:
    """
    Simulates the exact chronological state machine with optional EMA9 candle-close trailing exit.

    Order of evaluation on completed 1H candle i:
      1. Catastrophe SL check (-10.00% against candle Low/High)
      2. Profit Target check (+3.00% Long / +1.50% Short against candle High/Low)
      3. EMA9 Candle-Close Trailing Exit:
         - Evaluated on completed 1H candle Close vs EMA9(i)
         - Long: close[i] < ema9[i] * (1 - buffer/100)
         - Short: close[i] > ema9[i] * (1 + buffer/100)
         - If triggered: fills at open_px[i+1] (the opening price of the next bar, strictly causal)
         - Position becomes FLAT
      4. V2-2 Reversal check:
         - If neither SL, Target, nor EMA9 exit triggered, check for confirmed opposite V2-2 signal.
         - If opposite signal: controlled reversal at open_px[i+1].
      5. Signal execution from FLAT:
         - If FLAT and signal confirmed on completed candle i: opens position at open_px[i+1].
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

                # Priority 1: Catastrophe SL
                # Priority 2: Target Hit
                if tp_hit and sl_hit:
                    # Conservative assumption: SL touched first unless open breached target
                    if pos == 1:
                        x_px = curr_open if curr_open <= stop_px else stop_px
                    else:
                        x_px = curr_open if curr_open >= stop_px else stop_px
                    x_reason = "CATASTROPHE_SL"
                    exited_this_bar = True
                    x_bar_idx = i
                elif sl_hit:
                    if pos == 1:
                        x_px = curr_open if curr_open <= stop_px else max(stop_px, curr_low)
                    else:
                        x_px = curr_open if curr_open >= stop_px else min(stop_px, curr_high)
                    x_reason = "CATASTROPHE_SL"
                    exited_this_bar = True
                    x_bar_idx = i
                elif tp_hit:
                    if pos == 1:
                        x_px = curr_open if curr_open >= target_px else min(target_px, curr_high)
                    else:
                        x_px = curr_open if curr_open <= target_px else max(target_px, curr_low)
                    x_reason = "TARGET_HIT"
                    exited_this_bar = True
                    x_bar_idx = i

                # Priority 3: EMA9 Candle-Close Trailing Exit (if neither SL nor Target hit)
                elif enable_ema9_exit:
                    if pos == 1:
                        ema_thresh = curr_ema9 * (1.0 - ema9_buffer_pct / 100.0)
                        ema_trail_triggered = curr_close < ema_thresh
                    else:
                        ema_thresh = curr_ema9 * (1.0 + ema9_buffer_pct / 100.0)
                        ema_trail_triggered = curr_close > ema_thresh

                    if ema_trail_triggered:
                        # Executed at the open of the next candle (strictly causal, no lookahead)
                        next_idx = i + 1
                        x_px = open_px[next_idx]
                        x_reason = "EMA9_TRAIL_EXIT"
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
                    pos = 0  # Position is now FLAT

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
                        "bars_held": next_entry_idx - entry_idx,
                        "raw_pnl_pct": raw_pnl,
                        "net_pnl_pct": net_pnl,
                        "is_win": net_pnl > 0,
                        "mfe_pct": mfe,
                        "mae_pct": mae,
                        "sample": sample,
                        "cal_year": cal_year,
                        "roll_year": roll_year,
                    })

                    pos = 1 if sig == "BUY" else -1
                    entry_px = next_entry_px
                    entry_time = next_entry_time
                    entry_idx = next_entry_idx
                else:
                    # Same direction: duplicate skipped
                    pass

    return pd.DataFrame(all_trades)


def run_comprehensive_ema9_research():
    print("=" * 80)
    print("🚀 STARTING EMA9 CANDLE-CLOSE TRAILING EXIT RESEARCH STUDY")
    print("=" * 80)

    data_map = load_or_download_all_data()

    configs = [
        {"name": "Benchmark (No EMA9, Fixed SL -10%)", "enable": False, "buffer": 0.0},
        {"name": "EMA9 Trailing (Buffer 0.00%)", "enable": True, "buffer": 0.0},
        {"name": "EMA9 Trailing (Buffer 0.25%)", "enable": True, "buffer": 0.25},
        {"name": "EMA9 Trailing (Buffer 0.50%)", "enable": True, "buffer": 0.50},
        {"name": "EMA9 Trailing (Buffer 1.00%)", "enable": True, "buffer": 1.00},
        {"name": "EMA9 Trailing (Buffer 1.50%)", "enable": True, "buffer": 1.50},
        {"name": "EMA9 Trailing (Buffer 2.00%)", "enable": True, "buffer": 2.00},
    ]

    master_summary = []
    directional_summary = []
    rolling_years_summary = []
    calendar_years_summary = []
    is_oos_summary = []
    trades_map = {}

    for cfg in configs:
        name = cfg["name"]
        en = cfg["enable"]
        buf = cfg["buffer"]
        print(f"Simulating: {name}...")

        trades_df = run_ema9_trailing_simulation(
            data_map, enable_ema9_exit=en, ema9_buffer_pct=buf, catastrophe_sl_pct=10.0
        )
        trades_map[name] = trades_df

        # 1. Overall Metrics
        m = compute_metrics(trades_df)
        master_summary.append({"variant": name, "enable_ema9": en, "buffer_pct": buf, **m})

        # 2. Directional Breakdown
        for d in ["LONG", "SHORT"]:
            sub = trades_df[trades_df["direction"] == d]
            dm = compute_metrics(sub)
            directional_summary.append({"variant": name, "direction": d, **dm})

        # 3. Rolling Years
        for ry in ["Year 1 (Sep 23 - Sep 24)", "Year 2 (Sep 24 - Sep 25)", "Year 3 (Sep 25 - Sep 26)"]:
            sub = trades_df[trades_df["roll_year"] == ry]
            rm = compute_metrics(sub, custom_years=1.0)
            rolling_years_summary.append({"variant": name, "rolling_year": ry, **rm})

        # 4. Calendar Years
        for cy in ["2023", "2024", "2025", "2026"]:
            sub = trades_df[trades_df["cal_year"] == cy]
            cy_y = 0.25 if cy in ["2023", "2026"] else 1.0
            cm = compute_metrics(sub, custom_years=cy_y)
            calendar_years_summary.append({"variant": name, "calendar_year": cy, **cm})

        # 5. IS vs OOS
        for s in ["IS", "OOS"]:
            sub = trades_df[trades_df["sample"] == s]
            s_y = 1.75 if s == "IS" else 1.20
            sm = compute_metrics(sub, custom_years=s_y)
            is_oos_summary.append({"variant": name, "sample": s, **sm})

    # Save to CSV files
    pd.DataFrame(master_summary).to_csv(CURRENT_DIR / "ema9_research_summary.csv", index=False)
    pd.DataFrame(directional_summary).to_csv(CURRENT_DIR / "ema9_research_directional.csv", index=False)
    pd.DataFrame(rolling_years_summary).to_csv(CURRENT_DIR / "ema9_research_rolling_years.csv", index=False)
    pd.DataFrame(calendar_years_summary).to_csv(CURRENT_DIR / "ema9_research_calendar_years.csv", index=False)
    pd.DataFrame(is_oos_summary).to_csv(CURRENT_DIR / "ema9_research_is_oos.csv", index=False)

    print("\n  ✓ Saved ema9_research_summary.csv")
    print("  ✓ Saved ema9_research_directional.csv")
    print("  ✓ Saved ema9_research_rolling_years.csv")
    print("  ✓ Saved ema9_research_calendar_years.csv")
    print("  ✓ Saved ema9_research_is_oos.csv")

    # -------------------------------------------------------------------------
    # FORENSIC AUDIT: PREMATURE EXITS VS PROFIT RETENTION
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("🔬 PREMATURE EXITS VS PROFIT RETENTION FORENSIC AUDIT")
    print("=" * 80)

    bench_trades = trades_map["Benchmark (No EMA9, Fixed SL -10%)"]
    ema0_trades = trades_map["EMA9 Trailing (Buffer 0.00%)"]

    print(f"Benchmark Trades: {len(bench_trades)} | Net Return: {bench_trades['net_pnl_pct'].sum():+.2f}% | Win Rate: {(bench_trades['net_pnl_pct'] > 0).mean()*100:.2f}%")
    print(f"EMA9 0.00% Trades: {len(ema0_trades)} | Net Return: {ema0_trades['net_pnl_pct'].sum():+.2f}% | Win Rate: {(ema0_trades['net_pnl_pct'] > 0).mean()*100:.2f}%")

    # Check how many trades exited via EMA9 in buffer 0.00%
    ema0_reasons = ema0_trades["exit_reason"].value_counts().to_dict()
    print("\nExit Breakdown for EMA9 Buffer 0.00%:")
    for r, c in ema0_reasons.items():
        print(f"  • {r:18s}: {c:4d} ({c/len(ema0_trades)*100:.2f}%)")

    print("\n" + "=" * 80)
    print("✅ EMA9 TRAILING RESEARCH STUDY COMPLETE!")
    print("=" * 80)


if __name__ == "__main__":
    run_comprehensive_ema9_research()
