"""
Short Target Sensitivity Research Engine — EMACROSSOPEN
File: backtesting/emacrossopen/short_target_research.py

Evaluates Short Profit Target = 3.00% vs the authoritative baseline (Short TP = 1.50%)
across 166,444 completed 1H candles (33 NFO symbols, Sep 29, 2023 to Sep 09, 2026).

Preserves exact production baseline:
  - V2-2 Asymmetric Sequential Confirmation Entry (EMA9/26 + MACD 12/26/9, 2-candle window)
  - Long Target: +3.00%
  - Emergency SL: -10.00% Fixed Catastrophe SL
  - Primary Exit: V2-2 Confirmed Opposite-Signal Reversal
  - Completed 1H candles only
  - Actual executed fill price
  - Next-bar-open execution
  - 0.07% round-trip friction
  - Same 33 NFO symbols
  - Zero synthetic OI, zero lookahead
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


def run_target_simulation(
    data_map: Dict[str, pd.DataFrame],
    long_tp: float = 3.00,
    short_tp: Optional[float] = 1.50,  # None means reversal only for Short
    catastrophe_sl_pct: float = 10.0,
    friction: float = FRICTION_PCT,
) -> pd.DataFrame:
    """
    Simulates the exact V2-2 production state machine with custom Long/Short targets.
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
                # Target price
                if pos == 1:
                    target_px = entry_px * (1.0 + long_tp / 100.0)
                    tp_hit = curr_high >= target_px
                else:
                    if short_tp is not None:
                        target_px = entry_px * (1.0 - short_tp / 100.0)
                        tp_hit = curr_low <= target_px
                    else:
                        tp_hit = False

                # Catastrophe SL price
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


def main():
    print("=" * 80)
    print("SHORT PROFIT TARGET RESEARCH ENGINE — EMACROSSOPEN")
    print("Testing Short Target Grid: 1.0%, 1.5% (Baseline), 2.0%, 2.5%, 3.0% (Candidate), 3.5%, 4.0%, No TP")
    print("33 Liquid NFO instruments across 166,444 completed 1H candles")
    print("=" * 80)

    data_map = load_or_download_all_data()

    # Define variants
    variants = [
        {"name": "Production Baseline (Long +3.0%, Short +1.5%)", "long_tp": 3.0, "short_tp": 1.5, "is_baseline": True},
        {"name": "Candidate Symmetric (Long +3.0%, Short +3.0%)", "long_tp": 3.0, "short_tp": 3.0, "is_candidate": True},
        {"name": "Grid: Short Target = 1.00%", "long_tp": 3.0, "short_tp": 1.0},
        {"name": "Grid: Short Target = 2.00%", "long_tp": 3.0, "short_tp": 2.0},
        {"name": "Grid: Short Target = 2.50%", "long_tp": 3.0, "short_tp": 2.5},
        {"name": "Grid: Short Target = 3.50%", "long_tp": 3.0, "short_tp": 3.5},
        {"name": "Grid: Short Target = 4.00%", "long_tp": 3.0, "short_tp": 4.0},
        {"name": "Grid: Short No Target (Reversal Only)", "long_tp": 3.0, "short_tp": None},
    ]

    summary_rows = []
    directional_rows = []
    is_oos_rows = []
    calendar_rows = []
    rolling_rows = []

    for v in variants:
        v_name = v["name"]
        print(f"Running simulation: {v_name}...")

        trades_df = run_target_simulation(
            data_map=data_map,
            long_tp=v["long_tp"],
            short_tp=v["short_tp"],
            catastrophe_sl_pct=10.0,
            friction=FRICTION_PCT,
        )

        m = compute_metrics(trades_df)

        # IS / OOS breakdown
        is_df = trades_df[trades_df["sample"] == "IS"]
        oos_df = trades_df[trades_df["sample"] == "OOS"]
        is_m = compute_metrics(is_df, custom_years=21.0 / 12.0)
        oos_m = compute_metrics(oos_df, custom_years=14.5 / 12.0)

        # Directional breakdown
        long_df = trades_df[trades_df["direction"] == "LONG"]
        short_df = trades_df[trades_df["direction"] == "SHORT"]
        long_m = compute_metrics(long_df)
        short_m = compute_metrics(short_df)

        summary_rows.append({
            "variant": v_name,
            "short_tp_pct": v["short_tp"] if v["short_tp"] is not None else "None",
            "trade_count": m["trade_count"],
            "win_rate_pct": m["win_rate_pct"],
            "profit_factor": m["profit_factor"],
            "expectancy_pct": m["expectancy_pct"],
            "total_return_pct": m["total_return_pct"],
            "annualized_return_pct": m["annualized_return_pct"],
            "cagr_pct": m["cagr_pct"],
            "max_drawdown_pct": m["max_drawdown_pct"],
            "calmar_ratio": m["calmar_ratio"],
            "target_hit_count": m["target_hit_count"],
            "target_hit_pct": m["target_hit_pct"],
            "sl_hit_count": m["sl_hit_count"],
            "sl_hit_pct": m["sl_hit_pct"],
            "reversal_count": m["reversal_count"],
            "reversal_pct": m["reversal_pct"],
            "max_single_loss_pct": m["max_single_loss_pct"],
            "worst_5_loss_avg_pct": m["worst_5_loss_avg_pct"],
            "long_return_pct": long_m["total_return_pct"],
            "long_pf": long_m["profit_factor"],
            "long_win_rate": long_m["win_rate_pct"],
            "long_target_hits": long_m["target_hit_count"],
            "short_return_pct": short_m["total_return_pct"],
            "short_pf": short_m["profit_factor"],
            "short_win_rate": short_m["win_rate_pct"],
            "short_target_hits": short_m["target_hit_count"],
            "is_return_pct": is_m["total_return_pct"],
            "is_pf": is_m["profit_factor"],
            "is_win_rate": is_m["win_rate_pct"],
            "oos_return_pct": oos_m["total_return_pct"],
            "oos_pf": oos_m["profit_factor"],
            "oos_win_rate": oos_m["win_rate_pct"],
        })

        # Record directional rows
        for d, sub_df in [("LONG", long_df), ("SHORT", short_df)]:
            dm = compute_metrics(sub_df)
            dm["variant"] = v_name
            dm["direction"] = d
            directional_rows.append(dm)

        # Record IS/OOS rows
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

    # Save to CSVs
    output_dir = CURRENT_DIR
    df_summary = pd.DataFrame(summary_rows)
    df_directional = pd.DataFrame(directional_rows)
    df_is_oos = pd.DataFrame(is_oos_rows)
    df_calendar = pd.DataFrame(calendar_rows)
    df_rolling = pd.DataFrame(rolling_rows)

    df_summary.to_csv(output_dir / "short_target_summary.csv", index=False)
    df_directional.to_csv(output_dir / "short_target_directional.csv", index=False)
    df_is_oos.to_csv(output_dir / "short_target_is_oos.csv", index=False)
    df_calendar.to_csv(output_dir / "short_target_calendar_years.csv", index=False)
    df_rolling.to_csv(output_dir / "short_target_rolling_years.csv", index=False)

    print("\n" + "=" * 80)
    print("SIMULATION COMPLETE — ALL DATASETS EXPORTED")
    print("=" * 80)
    cols = ["variant", "short_tp_pct", "trade_count", "win_rate_pct", "profit_factor", "total_return_pct", "short_return_pct", "short_target_hits", "oos_return_pct"]
    print(df_summary[cols].to_string(index=False))


if __name__ == "__main__":
    main()
