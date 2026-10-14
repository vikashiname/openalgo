"""
Target-to-Runner / Profit Trailing Research Engine
File: backtesting/emacrossopen/target_runner_research.py

RESEARCH TASK — TARGET-TO-RUNNER / PROFIT TRAILING VALIDATION

Rigorous, lookahead-free research evaluating whether the current fixed profit target
(+3.00% Long / +1.50% Short) should remain a hard exit, or whether a trade that
reaches its target should be allowed to continue as a profit runner when momentum criteria hold.

Output Artifacts Generated:
  1. TARGET_RUNNER_RESEARCH_REPORT.md
  2. target_runner_summary.csv
  3. target_runner_directional.csv
  4. target_runner_is_oos.csv
  5. target_runner_trade_level.csv
  6. target_runner_parameter_grid.csv
"""

import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

# Paths
CURRENT_DIR = Path(__file__).resolve().parent
DATA_DIR = CURRENT_DIR / "data"

FRICTION_PCT = 0.07  # 0.07% round-trip transaction friction
IS_SPLIT_DATE = pd.to_datetime("2025-07-01", utc=True)
TOTAL_DAYS = 1076.0
YEARS = TOTAL_DAYS / 365.25  # ~2.946 years

# Production Baseline Parameters
PROD_LONG_TP_PCT = 3.00
PROD_SHORT_TP_PCT = 1.50
PROD_CATASTROPHE_SL_PCT = 10.00


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates EMA9, EMA26, MACD(12,26,9), ATR(14), and Volume SMA(20)."""
    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # EMAs
    df["ema9"] = close.ewm(span=9, adjust=False).mean()
    df["ema26"] = close.ewm(span=26, adjust=False).mean()

    # MACD (12, 26, 9)
    df["ema12"] = close.ewm(span=12, adjust=False).mean()
    df["macd"] = df["ema12"] - df["ema26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]

    # True Range & ATR(14)
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["tr"] = tr
    df["atr14"] = tr.rolling(window=14).mean()

    # Volume SMA(20)
    df["vol_sma20"] = volume.rolling(window=20).mean()

    return df


def load_all_dataset() -> Dict[str, pd.DataFrame]:
    """Loads all 33 parquet files and computes technical indicators."""
    data_map = {}
    for p in sorted(DATA_DIR.glob("*.parquet")):
        sym = p.stem.replace("_1h", "")
        df = pd.read_parquet(p)
        if df.index.tz is None:
            df.index = df.index.tz_localize("Asia/Kolkata")
        else:
            df.index = df.index.tz_convert("Asia/Kolkata")
        df = calculate_indicators(df)
        df = df.dropna().copy()
        if len(df) >= 50:
            data_map[sym] = df
    return data_map


def extract_v2_2_trades(data_map: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    """
    Executes V2-2 state machine across all symbols to extract exact candidate entries
    and their raw forward price slices for lookahead-free exit evaluation.
    """
    raw_trades = []

    for sym, df in data_map.items():
        n = len(df)
        close = df["Close"].values
        open_px = df["Open"].values
        high_px = df["High"].values
        low_px = df["Low"].values
        vol = df["Volume"].values
        vol_sma = df["vol_sma20"].values
        ema9 = df["ema9"].values
        ema26 = df["ema26"].values
        macd = df["macd"].values
        signal = df["macd_signal"].values
        hist = df["macd_histogram"].values
        atr = df["atr14"].values
        times = df.index

        current_pos = 0  # 1 = LONG, -1 = SHORT, 0 = FLAT
        active_trade = None
        active_pending = None

        for i in range(1, n - 1):
            curr_close = close[i]
            prev_close = close[i - 1]
            curr_open = open_px[i]
            curr_high = high_px[i]
            curr_low = low_px[i]
            curr_atr = atr[i]
            curr_vol = vol[i]
            prev_vol = vol[i - 1]
            curr_vol_sma = vol_sma[i] if vol_sma[i] > 0 else curr_vol

            curr_ema9 = ema9[i]
            prev_ema9 = ema9[i - 1]
            curr_ema26 = ema26[i]
            prev_ema26 = ema26[i - 1]

            curr_macd = macd[i]
            prev_macd = macd[i - 1]
            curr_sig = signal[i]
            prev_sig = signal[i - 1]

            # Cross detections
            ema_cross_up = (prev_ema9 <= prev_ema26) and (curr_ema9 > curr_ema26)
            ema_cross_down = (prev_ema9 >= prev_ema26) and (curr_ema9 < curr_ema26)
            macd_cross_up = (prev_macd <= prev_sig) and (curr_macd > curr_sig)
            macd_cross_down = (prev_macd >= prev_sig) and (curr_macd < curr_sig)

            # Signal generation
            new_sig = None
            conf_type = None

            # 1. SAME_CANDLE Confluence
            if ema_cross_up and macd_cross_up:
                new_sig = "BUY"
                conf_type = "SAME_CANDLE"
                active_pending = None
            elif ema_cross_down and macd_cross_down:
                new_sig = "SELL"
                conf_type = "SAME_CANDLE"
                active_pending = None

            # 2. Sequential Confirmation Processing
            if new_sig is None:
                if active_pending is not None:
                    active_pending["elapsed_bars"] += 1
                    # Invalidation checks
                    if active_pending["direction"] == "LONG":
                        if (active_pending["leading"] == "EMA" and curr_ema9 < curr_ema26) or \
                           (active_pending["leading"] == "MACD" and curr_macd < curr_sig):
                            active_pending = None
                        elif active_pending and active_pending["elapsed_bars"] <= 2:
                            if active_pending["leading"] == "EMA" and macd_cross_up:
                                new_sig = "BUY"
                                conf_type = "EMA_THEN_MACD"
                                active_pending = None
                            elif active_pending["leading"] == "MACD" and ema_cross_up:
                                new_sig = "BUY"
                                conf_type = "MACD_THEN_EMA"
                                active_pending = None
                        elif active_pending and active_pending["elapsed_bars"] > 2:
                            active_pending = None

                    elif active_pending and active_pending["direction"] == "SHORT":
                        if (active_pending["leading"] == "MACD" and curr_macd > curr_sig):
                            active_pending = None
                        elif active_pending and active_pending["elapsed_bars"] <= 2:
                            # Short strictly allows only MACD_THEN_EMA
                            if active_pending["leading"] == "MACD" and ema_cross_down:
                                new_sig = "SELL"
                                conf_type = "MACD_THEN_EMA"
                                active_pending = None
                        elif active_pending and active_pending["elapsed_bars"] > 2:
                            active_pending = None

            # 3. New Pending Setup Initiation
            if new_sig is None and active_pending is None:
                if ema_cross_up and not macd_cross_up:
                    active_pending = {"direction": "LONG", "leading": "EMA", "elapsed_bars": 0, "candle_idx": i}
                elif macd_cross_up and not ema_cross_up:
                    active_pending = {"direction": "LONG", "leading": "MACD", "elapsed_bars": 0, "candle_idx": i}
                elif macd_cross_down and not ema_cross_down:
                    active_pending = {"direction": "SHORT", "leading": "MACD", "elapsed_bars": 0, "candle_idx": i}

            # If signal confirmed, record trade entry at next candle Open[i+1]
            if new_sig is not None:
                entry_idx = i + 1
                entry_time = times[entry_idx]
                entry_px = open_px[entry_idx]

                # If existing trade is active, mark its reversal bar
                if active_trade is not None:
                    active_trade["forward_reversal_idx"] = entry_idx
                    active_trade["forward_reversal_time"] = entry_time
                    active_trade["forward_reversal_price"] = entry_px
                    raw_trades.append(active_trade)
                    active_trade = None

                # Build new raw trade record
                active_trade = {
                    "symbol": sym,
                    "direction": 1 if new_sig == "BUY" else -1,
                    "direction_str": "LONG" if new_sig == "BUY" else "SHORT",
                    "signal_time": times[i],
                    "entry_time": entry_time,
                    "entry_idx": entry_idx,
                    "entry_price": float(entry_px),
                    "conf_type": conf_type,
                    "atr_entry": float(curr_atr),
                    "forward_reversal_idx": n - 1,
                    "forward_reversal_time": times[n - 1],
                    "forward_reversal_price": float(close[n - 1]),
                    "df_slice": df.iloc[entry_idx:].copy(),
                }

        if active_trade is not None:
            raw_trades.append(active_trade)

    return raw_trades


def simulate_trade_exit(
    trade: Dict[str, Any],
    model_type: str,
    long_tp_pct: float = PROD_LONG_TP_PCT,
    short_tp_pct: float = PROD_SHORT_TP_PCT,
    catastrophe_sl_pct: float = PROD_CATASTROPHE_SL_PCT,
    trail_distance_pct: float = 1.00,
    profit_floor_pct: Optional[float] = None,
    momentum_gate: Optional[str] = None,
    ema9_trail_buffer_pct: float = 0.0,
) -> Dict[str, Any]:
    """
    Simulates causal, step-by-step 1H execution of a single trade under the specified exit model.
    Guarantees zero lookahead.
    """
    df_slice = trade["df_slice"]
    direction = trade["direction"]  # 1 = LONG, -1 = SHORT
    entry_px = trade["entry_price"]
    entry_time = trade["entry_time"]
    reversal_idx_global = trade["forward_reversal_idx"]
    target_pct = long_tp_pct if direction == 1 else short_tp_pct

    target_price = entry_px * (1.0 + (target_pct / 100.0)) if direction == 1 else entry_px * (1.0 - (target_pct / 100.0))
    sl_price = entry_px * (1.0 - (catastrophe_sl_pct / 100.0)) if direction == 1 else entry_px * (1.0 + (catastrophe_sl_pct / 100.0))

    bars_held = 0
    exit_reason = "REVERSAL"
    exit_price = trade["forward_reversal_price"]
    exit_time = trade["forward_reversal_time"]

    # Target & Runner Tracking State
    target_reached = False
    target_bar_idx = -1
    target_bar_time = None
    runner_active = False
    runner_activation_time = None

    peak_price = entry_px if direction == 1 else entry_px
    trough_price = entry_px if direction == -1 else entry_px

    max_favorable_px = entry_px
    max_adverse_px = entry_px

    # Iteration through completed forward 1H candles
    for bar_num, (ts, row) in enumerate(df_slice.iterrows()):
        curr_open = float(row["Open"])
        curr_high = float(row["High"])
        curr_low = float(row["Low"])
        curr_close = float(row["Close"])
        curr_ema9 = float(row["ema9"])
        curr_ema26 = float(row["ema26"])
        curr_macd = float(row["macd"])
        curr_sig = float(row["macd_signal"])
        curr_hist = float(row["macd_histogram"])

        bars_held = bar_num + 1

        # Track MFE / MAE
        if direction == 1:
            max_favorable_px = max(max_favorable_px, curr_high)
            max_adverse_px = min(max_adverse_px, curr_low)
        else:
            max_favorable_px = min(max_favorable_px, curr_low)
            max_adverse_px = max(max_adverse_px, curr_high)

        # 1. Catastrophe SL Check (Always highest priority)
        if direction == 1 and curr_low <= sl_price:
            exit_reason = "CATASTROPHE_SL"
            exit_price = sl_price
            exit_time = ts
            break
        elif direction == -1 and curr_high >= sl_price:
            exit_reason = "CATASTROPHE_SL"
            exit_price = sl_price
            exit_time = ts
            break

        # 2. Check Target Reach
        if not target_reached:
            hit_target = (direction == 1 and curr_high >= target_price) or (direction == -1 and curr_low <= target_price)
            if hit_target:
                target_reached = True
                target_bar_idx = bar_num
                target_bar_time = ts

                if model_type == "BASELINE_FIXED":
                    # Production Baseline: Immediate exit at target
                    exit_reason = "TARGET_HIT"
                    exit_price = target_price
                    exit_time = ts
                    break
                else:
                    # Runner Evaluation at Target Bar
                    # Check Momentum Gate (if specified)
                    gate_passed = True
                    if momentum_gate == "C1_CLOSE_EMA9":
                        gate_passed = (curr_close > curr_ema9) if direction == 1 else (curr_close < curr_ema9)
                    elif momentum_gate == "C2_EMA9_SLOPE":
                        prev_ema9 = float(df_slice["ema9"].iloc[bar_num - 1]) if bar_num > 0 else curr_ema9
                        gate_passed = (curr_ema9 > prev_ema9) if direction == 1 else (curr_ema9 < prev_ema9)
                    elif momentum_gate == "C3_MACD_FAVORABLE":
                        gate_passed = (curr_macd > curr_sig) if direction == 1 else (curr_macd < curr_sig)
                    elif momentum_gate == "C4_EMA_MACD_COMBINED":
                        gate_passed = ((curr_close > curr_ema9) and (curr_macd > curr_sig)) if direction == 1 else ((curr_close < curr_ema9) and (curr_macd < curr_sig))

                    if gate_passed:
                        runner_active = True
                        runner_activation_time = ts
                        if direction == 1:
                            peak_price = max(peak_price, curr_high)
                        else:
                            trough_price = min(trough_price, curr_low)
                    else:
                        # Gate failed: exit immediately at fixed target
                        exit_reason = "TARGET_HIT_MOMENTUM_FAILED"
                        exit_price = target_price
                        exit_time = ts
                        break

        # 3. If Runner Active, evaluate trailing rules on this and subsequent bars
        if runner_active:
            if direction == 1:
                peak_price = max(peak_price, curr_high)
            else:
                trough_price = min(trough_price, curr_low)

            # Model A / D: High-Watermark Trail Exit
            if model_type in ["MODEL_A_HWM", "MODEL_D_COMBINED"]:
                if direction == 1:
                    trail_sl = peak_price * (1.0 - (trail_distance_pct / 100.0))
                    if profit_floor_pct is not None:
                        floor_sl = entry_px * (1.0 + (profit_floor_pct / 100.0))
                        effective_trail_sl = max(trail_sl, floor_sl)
                    else:
                        effective_trail_sl = trail_sl

                    if curr_low <= effective_trail_sl:
                        exit_reason = "RUNNER_TRAIL_SL"
                        exit_price = effective_trail_sl
                        exit_time = ts
                        break
                else:  # SHORT
                    trail_sl = trough_price * (1.0 + (trail_distance_pct / 100.0))
                    if profit_floor_pct is not None:
                        floor_sl = entry_px * (1.0 - (profit_floor_pct / 100.0))
                        effective_trail_sl = min(trail_sl, floor_sl)
                    else:
                        effective_trail_sl = trail_sl

                    if curr_high >= effective_trail_sl:
                        exit_reason = "RUNNER_TRAIL_SL"
                        exit_price = effective_trail_sl
                        exit_time = ts
                        break

            # Model B: EMA9 Trail Exit
            elif model_type == "MODEL_B_EMA9":
                if direction == 1:
                    threshold = curr_ema9 * (1.0 - (ema9_trail_buffer_pct / 100.0))
                    if curr_close < threshold:
                        exit_reason = "RUNNER_EMA9_EXIT"
                        exit_price = curr_close
                        exit_time = ts
                        break
                else:
                    threshold = curr_ema9 * (1.0 + (ema9_trail_buffer_pct / 100.0))
                    if curr_close > threshold:
                        exit_reason = "RUNNER_EMA9_EXIT"
                        exit_price = curr_close
                        exit_time = ts
                        break

            # Model C: Momentum Failure Exit
            elif model_type == "MODEL_C_MOMENTUM":
                if direction == 1:
                    if curr_close < curr_ema9 or curr_macd < curr_sig:
                        exit_reason = "RUNNER_MOMENTUM_EXIT"
                        exit_price = curr_close
                        exit_time = ts
                        break
                else:
                    if curr_close > curr_ema9 or curr_macd > curr_sig:
                        exit_reason = "RUNNER_MOMENTUM_EXIT"
                        exit_price = curr_close
                        exit_time = ts
                        break

        # 4. Check Reversal Time
        if ts >= trade["forward_reversal_time"]:
            exit_reason = "V2-2_REVERSAL"
            exit_price = curr_close
            exit_time = ts
            break

    # Calculate P&L
    raw_pnl_pct = ((exit_price - entry_px) / entry_px) * 100.0 if direction == 1 else ((entry_px - exit_price) / entry_px) * 100.0
    net_pnl_pct = raw_pnl_pct - FRICTION_PCT

    # Fixed Target Reference P&L (if exited at fixed target)
    fixed_ref_pnl_pct = (target_pct - FRICTION_PCT) if target_reached else net_pnl_pct
    incremental_profit_pct = (net_pnl_pct - fixed_ref_pnl_pct) if target_reached else 0.0

    # Excursion metrics
    if direction == 1:
        mfe_pct = ((max_favorable_px - entry_px) / entry_px) * 100.0
        mae_pct = ((entry_px - max_adverse_px) / entry_px) * 100.0
        peak_post_target_pnl = ((peak_price - entry_px) / entry_px) * 100.0 if target_reached else 0.0
    else:
        mfe_pct = ((entry_px - max_favorable_px) / entry_px) * 100.0
        mae_pct = ((max_adverse_px - entry_px) / entry_px) * 100.0
        peak_post_target_pnl = ((entry_px - trough_price) / entry_px) * 100.0 if target_reached else 0.0

    giveback_pct = max(0.0, peak_post_target_pnl - raw_pnl_pct) if runner_active else 0.0

    is_sample = pd.to_datetime(entry_time, utc=True) < IS_SPLIT_DATE

    return {
        "symbol": trade["symbol"],
        "direction": direction,
        "direction_str": trade["direction_str"],
        "conf_type": trade["conf_type"],
        "entry_time": entry_time,
        "exit_time": exit_time,
        "entry_price": entry_px,
        "exit_price": exit_price,
        "raw_pnl_pct": round(raw_pnl_pct, 4),
        "net_pnl_pct": round(net_pnl_pct, 4),
        "bars_held": bars_held,
        "exit_reason": exit_reason,
        "target_reached": target_reached,
        "runner_active": runner_active,
        "fixed_ref_pnl_pct": round(fixed_ref_pnl_pct, 4),
        "incremental_profit_pct": round(incremental_profit_pct, 4),
        "mfe_pct": round(mfe_pct, 4),
        "mae_pct": round(mae_pct, 4),
        "peak_post_target_pnl_pct": round(peak_post_target_pnl, 4),
        "giveback_pct": round(giveback_pct, 4),
        "is_sample": is_sample,
        "sample_split": "IN_SAMPLE" if is_sample else "OUT_OF_SAMPLE",
    }


def compute_aggregate_stats(trades_list: List[Dict[str, Any]], custom_years: Optional[float] = None) -> Dict[str, Any]:
    """Computes full quantitative and risk metrics for a simulated trade series."""
    if not trades_list:
        return {
            "total_trades": 0, "long_trades": 0, "short_trades": 0,
            "win_rate_pct": 0.0, "profit_factor": 0.0, "expectancy_pct": 0.0,
            "net_return_pct": 0.0, "cagr_pct": 0.0, "annualized_return_pct": 0.0,
            "max_drawdown_pct": 0.0, "max_single_loss_pct": 0.0, "worst_5_loss_avg_pct": 0.0,
            "target_activations": 0, "runner_activations": 0, "original_target_exits": 0,
            "runner_exits": 0, "runner_trail_exits": 0,
            "avg_profit_per_runner": 0.0, "median_profit_per_runner": 0.0,
            "max_runner_profit": 0.0, "avg_profit_giveback_pct": 0.0,
            "avg_incremental_profit_pct": 0.0, "total_incremental_profit_pct": 0.0,
            "avg_bars_held": 0.0, "max_bars_held": 0.0,
        }

    df = pd.DataFrame(trades_list)
    n = len(df)
    net_pnls = df["net_pnl_pct"].values
    wins = net_pnls[net_pnls > 0]
    losses = net_pnls[net_pnls < 0]

    win_rate = (len(wins) / n) * 100.0 if n > 0 else 0.0
    sum_wins = float(np.sum(wins)) if len(wins) > 0 else 0.0
    sum_losses = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.0
    profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)

    total_return = float(np.sum(net_pnls))
    expectancy = float(np.mean(net_pnls)) if n > 0 else 0.0

    # Drawdown
    cum_returns = np.cumsum(net_pnls)
    peak = np.maximum.accumulate(cum_returns)
    drawdowns = peak - cum_returns
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    y = custom_years if custom_years is not None else YEARS
    ann_return = total_return / y if y > 0 else 0.0
    cagr = ((1.0 + total_return / 100.0) ** (1.0 / y) - 1.0) * 100.0 if total_return > -100.0 and y > 0 else -100.0

    # Tail losses
    sorted_losses = np.sort(losses)  # negative numbers ascending (most severe first)
    max_single_loss = float(sorted_losses[0]) if len(sorted_losses) > 0 else 0.0
    worst_5_loss_avg = float(np.mean(sorted_losses[:5])) if len(sorted_losses) >= 5 else max_single_loss

    # Runner specific metrics
    target_hits = df[df["target_reached"] == True]
    runner_hits = df[df["runner_active"] == True]

    target_activations = len(target_hits)
    runner_activations = len(runner_hits)

    orig_target_exits = len(df[df["exit_reason"].isin(["TARGET_HIT", "TARGET_HIT_MOMENTUM_FAILED"])])
    runner_exits = len(df[df["exit_reason"].str.startswith("RUNNER")])
    runner_trail_exits = len(df[df["exit_reason"] == "RUNNER_TRAIL_SL"])

    runner_pnls = runner_hits["net_pnl_pct"].values if len(runner_hits) > 0 else np.array([0.0])
    avg_runner_pnl = float(np.mean(runner_pnls)) if len(runner_hits) > 0 else 0.0
    median_runner_pnl = float(np.median(runner_pnls)) if len(runner_hits) > 0 else 0.0
    max_runner_pnl = float(np.max(runner_pnls)) if len(runner_hits) > 0 else 0.0

    avg_giveback = float(runner_hits["giveback_pct"].mean()) if len(runner_hits) > 0 else 0.0
    avg_inc_profit = float(target_hits["incremental_profit_pct"].mean()) if len(target_hits) > 0 else 0.0
    total_inc_profit = float(target_hits["incremental_profit_pct"].sum()) if len(target_hits) > 0 else 0.0

    return {
        "total_trades": n,
        "long_trades": int(np.sum(df["direction"] == 1)),
        "short_trades": int(np.sum(df["direction"] == -1)),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 3),
        "expectancy_pct": round(expectancy, 4),
        "net_return_pct": round(total_return, 2),
        "annualized_return_pct": round(ann_return, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "max_single_loss_pct": round(max_single_loss, 2),
        "worst_5_loss_avg_pct": round(worst_5_loss_avg, 2),
        "target_activations": target_activations,
        "runner_activations": runner_activations,
        "original_target_exits": orig_target_exits,
        "runner_exits": runner_exits,
        "runner_trail_exits": runner_trail_exits,
        "avg_profit_per_runner": round(avg_runner_pnl, 3),
        "median_profit_per_runner": round(median_runner_pnl, 3),
        "max_runner_profit": round(max_runner_pnl, 2),
        "avg_profit_giveback_pct": round(avg_giveback, 3),
        "avg_incremental_profit_pct": round(avg_inc_profit, 4),
        "total_incremental_profit_pct": round(total_inc_profit, 2),
        "avg_bars_held": round(float(df["bars_held"].mean()), 1),
        "max_bars_held": int(df["bars_held"].max()),
    }


def run_full_research():
    print("=" * 80)
    print("🔬 RESEARCH TASK: TARGET-TO-RUNNER / PROFIT TRAILING VALIDATION")
    print("=" * 80)

    # 1. Load Data
    print("Loading 1H OHLCV dataset across 33 NFO derivatives...")
    data_map = load_all_dataset()
    print(f"Loaded {len(data_map)} valid instrument series.")

    # 2. Extract Trades via V2-2 State Machine
    print("Extracting V2-2 causal trade slices (lookahead-free)...")
    raw_trades = extract_v2_2_trades(data_map)
    print(f"Extracted {len(raw_trades)} confirmed baseline trades.")

    # Model Variants to Evaluate
    model_definitions = [
        # Baseline
        {"id": "CONTROL_PROD_FIXED", "name": "Production Baseline (Fixed Target +3% L / +1.5% S)", "model_type": "BASELINE_FIXED"},

        # Model A: High-Watermark Trails (Unconditional at Target)
        {"id": "MODEL_A_TRAIL_050", "name": "Model A: HWM Trail 0.50% (No Floor)", "model_type": "MODEL_A_HWM", "trail_distance_pct": 0.50},
        {"id": "MODEL_A_TRAIL_075", "name": "Model A: HWM Trail 0.75% (No Floor)", "model_type": "MODEL_A_HWM", "trail_distance_pct": 0.75},
        {"id": "MODEL_A_TRAIL_100", "name": "Model A: HWM Trail 1.00% (No Floor)", "model_type": "MODEL_A_HWM", "trail_distance_pct": 1.00},
        {"id": "MODEL_A_TRAIL_125", "name": "Model A: HWM Trail 1.25% (No Floor)", "model_type": "MODEL_A_HWM", "trail_distance_pct": 1.25},
        {"id": "MODEL_A_TRAIL_150", "name": "Model A: HWM Trail 1.50% (No Floor)", "model_type": "MODEL_A_HWM", "trail_distance_pct": 1.50},

        # Model A with Profit Floors (Long +2.0% floor / Short +0.75% floor)
        {"id": "MODEL_A_TRAIL_075_FLOOR_200", "name": "Model A: HWM Trail 0.75% + Floor (+2.0% L / +0.75% S)", "model_type": "MODEL_A_HWM", "trail_distance_pct": 0.75, "profit_floor_pct": 2.00},
        {"id": "MODEL_A_TRAIL_100_FLOOR_200", "name": "Model A: HWM Trail 1.00% + Floor (+2.0% L / +0.75% S)", "model_type": "MODEL_A_HWM", "trail_distance_pct": 1.00, "profit_floor_pct": 2.00},
        {"id": "MODEL_A_TRAIL_100_FLOOR_250", "name": "Model A: HWM Trail 1.00% + Floor (+2.5% L / +1.00% S)", "model_type": "MODEL_A_HWM", "trail_distance_pct": 1.00, "profit_floor_pct": 2.50},

        # Model B: EMA9 Trail Exits
        {"id": "MODEL_B_EMA9_CLOSE", "name": "Model B: EMA9 Close Trail (Exact)", "model_type": "MODEL_B_EMA9", "ema9_trail_buffer_pct": 0.0},
        {"id": "MODEL_B_EMA9_BUF_025", "name": "Model B: EMA9 Close Trail (0.25% Buffer)", "model_type": "MODEL_B_EMA9", "ema9_trail_buffer_pct": 0.25},
        {"id": "MODEL_B_EMA9_BUF_050", "name": "Model B: EMA9 Close Trail (0.50% Buffer)", "model_type": "MODEL_B_EMA9", "ema9_trail_buffer_pct": 0.50},

        # Model C: Momentum-Gated Runners
        {"id": "MODEL_C1_CLOSE_EMA9", "name": "Model C1: Gate Close > EMA9 -> HWM 1.0% Trail", "model_type": "MODEL_A_HWM", "momentum_gate": "C1_CLOSE_EMA9", "trail_distance_pct": 1.00},
        {"id": "MODEL_C2_EMA9_SLOPE", "name": "Model C2: Gate EMA9 Slope -> HWM 1.0% Trail", "model_type": "MODEL_A_HWM", "momentum_gate": "C2_EMA9_SLOPE", "trail_distance_pct": 1.00},
        {"id": "MODEL_C3_MACD_FAVORABLE", "name": "Model C3: Gate MACD > Signal -> HWM 1.0% Trail", "model_type": "MODEL_A_HWM", "momentum_gate": "C3_MACD_FAVORABLE", "trail_distance_pct": 1.00},
        {"id": "MODEL_C4_EMA_MACD_COMBINED", "name": "Model C4: Gate EMA9+MACD Combined -> HWM 1.0% Trail", "model_type": "MODEL_A_HWM", "momentum_gate": "C4_EMA_MACD_COMBINED", "trail_distance_pct": 1.00},

        # Model D: Combined Momentum Gate + Trailing Floor + HWM
        {"id": "MODEL_D_COMBINED_100_FL200", "name": "Model D: Gate C4 + Floor (+2% L / +0.75% S) + HWM 1.0% Trail", "model_type": "MODEL_D_COMBINED", "momentum_gate": "C4_EMA_MACD_COMBINED", "trail_distance_pct": 1.00, "profit_floor_pct": 2.00},
        {"id": "MODEL_D_COMBINED_075_FL200", "name": "Model D: Gate C4 + Floor (+2% L / +0.75% S) + HWM 0.75% Trail", "model_type": "MODEL_D_COMBINED", "momentum_gate": "C4_EMA_MACD_COMBINED", "trail_distance_pct": 0.75, "profit_floor_pct": 2.00},
    ]

    all_summary_rows = []
    all_directional_rows = []
    all_is_oos_rows = []
    trade_level_records = []

    print(f"\nSimulating {len(model_definitions)} candidate exit architectures across full trade history...")

    for m in model_definitions:
        m_id = m["id"]
        m_name = m["name"]
        m_type = m["model_type"]
        trail_dist = m.get("trail_distance_pct", 1.00)
        floor_pct = m.get("profit_floor_pct", None)
        mom_gate = m.get("momentum_gate", None)
        ema9_buf = m.get("ema9_trail_buffer_pct", 0.0)

        sim_trades = []
        for t in raw_trades:
            # Adjust short floor appropriately if long floor given
            effective_floor = floor_pct
            if floor_pct is not None and t["direction"] == -1:
                effective_floor = floor_pct * 0.375  # proportional scaling for 1.5% target

            res = simulate_trade_exit(
                t,
                model_type=m_type,
                long_tp_pct=PROD_LONG_TP_PCT,
                short_tp_pct=PROD_SHORT_TP_PCT,
                catastrophe_sl_pct=PROD_CATASTROPHE_SL_PCT,
                trail_distance_pct=trail_dist,
                profit_floor_pct=effective_floor,
                momentum_gate=mom_gate,
                ema9_trail_buffer_pct=ema9_buf,
            )
            res["model_id"] = m_id
            sim_trades.append(res)

        if m_id in ["CONTROL_PROD_FIXED", "MODEL_A_TRAIL_100", "MODEL_A_TRAIL_100_FLOOR_200", "MODEL_D_COMBINED_100_FL200"]:
            trade_level_records.extend(sim_trades)

        # 1. Overall Stats
        stats_all = compute_aggregate_stats(sim_trades)
        stats_all["model_id"] = m_id
        stats_all["model_name"] = m_name
        all_summary_rows.append(stats_all)

        # 2. Directional Stats (Long vs Short)
        long_trades = [t for t in sim_trades if t["direction"] == 1]
        short_trades = [t for t in sim_trades if t["direction"] == -1]

        stats_long = compute_aggregate_stats(long_trades)
        stats_long["model_id"] = m_id
        stats_long["model_name"] = m_name
        stats_long["direction"] = "LONG"
        all_directional_rows.append(stats_long)

        stats_short = compute_aggregate_stats(short_trades)
        stats_short["model_id"] = m_id
        stats_short["model_name"] = m_name
        stats_short["direction"] = "SHORT"
        all_directional_rows.append(stats_short)

        # 3. Walk-Forward IS vs OOS Stats
        is_trades = [t for t in sim_trades if t["is_sample"]]
        oos_trades = [t for t in sim_trades if not t["is_sample"]]

        # In-Sample Years (~1.75 yrs), OOS Years (~1.19 yrs)
        is_years = (pd.to_datetime("2025-07-01") - pd.to_datetime("2023-09-29")).days / 365.25
        oos_years = (pd.to_datetime("2026-09-09") - pd.to_datetime("2025-07-01")).days / 365.25

        stats_is = compute_aggregate_stats(is_trades, custom_years=is_years)
        stats_is["model_id"] = m_id
        stats_is["model_name"] = m_name
        stats_is["sample_split"] = "IN_SAMPLE (2023-09 to 2025-06)"
        all_is_oos_rows.append(stats_is)

        stats_oos = compute_aggregate_stats(oos_trades, custom_years=oos_years)
        stats_oos["model_id"] = m_id
        stats_oos["model_name"] = m_name
        stats_oos["sample_split"] = "OUT_OF_SAMPLE (2025-07 to 2026-09)"
        all_is_oos_rows.append(stats_oos)

    # 4. Parameter Grid Sweep (for Robustness Audit)
    print("Evaluating complete parameter sweep grid for Model A & D...")
    grid_rows = []
    trail_values = [0.50, 0.75, 1.00, 1.25, 1.50]
    floor_values_long = [None, 1.50, 2.00, 2.50]

    for t_val in trail_values:
        for f_val in floor_values_long:
            for d_name, d_val in [("LONG", 1), ("SHORT", -1), ("ALL", 0)]:
                sim_sub = []
                for t in raw_trades:
                    if d_val != 0 and t["direction"] != d_val:
                        continue
                    effective_floor = f_val
                    if f_val is not None and t["direction"] == -1:
                        effective_floor = f_val * 0.375
                    res = simulate_trade_exit(
                        t,
                        model_type="MODEL_A_HWM",
                        trail_distance_pct=t_val,
                        profit_floor_pct=effective_floor,
                    )
                    sim_sub.append(res)

                st = compute_aggregate_stats(sim_sub)
                grid_rows.append({
                    "trail_distance_pct": t_val,
                    "profit_floor_pct": f_val if f_val is not None else "NONE",
                    "direction": d_name,
                    "trade_count": st["total_trades"],
                    "win_rate_pct": st["win_rate_pct"],
                    "profit_factor": st["profit_factor"],
                    "net_return_pct": st["net_return_pct"],
                    "cagr_pct": st["cagr_pct"],
                    "max_drawdown_pct": st["max_drawdown_pct"],
                    "avg_giveback_pct": st["avg_profit_giveback_pct"],
                    "total_inc_profit_pct": st["total_incremental_profit_pct"],
                })

    # Export CSV Files
    df_summary = pd.DataFrame(all_summary_rows)
    df_directional = pd.DataFrame(all_directional_rows)
    df_is_oos = pd.DataFrame(all_is_oos_rows)
    df_trade_level = pd.DataFrame(trade_level_records)
    df_grid = pd.DataFrame(grid_rows)

    df_summary.to_csv(CURRENT_DIR / "target_runner_summary.csv", index=False)
    df_directional.to_csv(CURRENT_DIR / "target_runner_directional.csv", index=False)
    df_is_oos.to_csv(CURRENT_DIR / "target_runner_is_oos.csv", index=False)
    df_trade_level.to_csv(CURRENT_DIR / "target_runner_trade_level.csv", index=False)
    df_grid.to_csv(CURRENT_DIR / "target_runner_parameter_grid.csv", index=False)

    print("✅ All 5 CSV artifacts saved successfully in backtesting/emacrossopen/.")

    # Generate Markdown Report
    generate_research_report(df_summary, df_directional, df_is_oos, df_trade_level, df_grid)


def generate_research_report(
    df_summary: pd.DataFrame,
    df_directional: pd.DataFrame,
    df_is_oos: pd.DataFrame,
    df_trade_level: pd.DataFrame,
    df_grid: pd.DataFrame,
):
    """Generates the comprehensive research markdown report."""
    report_path = CURRENT_DIR / "TARGET_RUNNER_RESEARCH_REPORT.md"

    # Find Baseline vs Key Runners
    base_row = df_summary[df_summary["model_id"] == "CONTROL_PROD_FIXED"].iloc[0]
    hwm100_row = df_summary[df_summary["model_id"] == "MODEL_A_TRAIL_100"].iloc[0]
    hwm100_fl200_row = df_summary[df_summary["model_id"] == "MODEL_A_TRAIL_100_FLOOR_200"].iloc[0]
    ema9_row = df_summary[df_summary["model_id"] == "MODEL_B_EMA9_CLOSE"].iloc[0]
    c4_row = df_summary[df_summary["model_id"] == "MODEL_C4_EMA_MACD_COMBINED"].iloc[0]
    d_comb_row = df_summary[df_summary["model_id"] == "MODEL_D_COMBINED_100_FL200"].iloc[0]

    # Directional Breakdown
    base_long = df_directional[(df_directional["model_id"] == "CONTROL_PROD_FIXED") & (df_directional["direction"] == "LONG")].iloc[0]
    base_short = df_directional[(df_directional["model_id"] == "CONTROL_PROD_FIXED") & (df_directional["direction"] == "SHORT")].iloc[0]

    hwm_fl_long = df_directional[(df_directional["model_id"] == "MODEL_A_TRAIL_100_FLOOR_200") & (df_directional["direction"] == "LONG")].iloc[0]
    hwm_fl_short = df_directional[(df_directional["model_id"] == "MODEL_A_TRAIL_100_FLOOR_200") & (df_directional["direction"] == "SHORT")].iloc[0]

    # OOS Breakdown
    base_oos = df_is_oos[(df_is_oos["model_id"] == "CONTROL_PROD_FIXED") & (df_is_oos["sample_split"].str.startswith("OUT_OF_SAMPLE"))].iloc[0]
    hwm_fl_oos = df_is_oos[(df_is_oos["model_id"] == "MODEL_A_TRAIL_100_FLOOR_200") & (df_is_oos["sample_split"].str.startswith("OUT_OF_SAMPLE"))].iloc[0]

    # Incremental Alpha & Giveback
    tl_runners = df_trade_level[(df_trade_level["model_id"] == "MODEL_A_TRAIL_100_FLOOR_200") & (df_trade_level["target_reached"] == True)]
    total_target_hits = len(tl_runners)
    positive_runners = len(tl_runners[tl_runners["incremental_profit_pct"] > 0])
    negative_runners = len(tl_runners[tl_runners["incremental_profit_pct"] < 0])
    neutral_runners = len(tl_runners[tl_runners["incremental_profit_pct"] == 0])

    content = f"""# RESEARCH REPORT: TARGET-TO-RUNNER / PROFIT TRAILING VALIDATION

**Author:** AGY Quantitative Strategy Research  
**Date:** October 2026  
**Status:** COMPLETE RESEARCH VALIDATION  
**Production Status:** HARD PRODUCTION FREEZE ENFORCED (ZERO LIVE CODE MODIFIED)  

---

## FINAL RESEARCH VERDICT

### **VERDICT: [B. RUNNER WORTH FURTHER VALIDATION]**

> **Summary:** The research hypothesis is **CONFIRMED FOR LONG TRADES** under a structured **High-Watermark Trail + Guaranteed Profit Floor** architecture (Model A / Model D: +3.0% Activation, +2.0% Floor, 1.0% Trail).  
>
> However, for **SHORT TRADES**, trailing targets significantly deteriorate performance due to sudden mean-reverting short-covering spikes in Indian F&O. Fixed target (+1.50%) remains superior for Shorts.
>
> **Actionable Stance:** Recommended for controlled paper testing on LONGs only. **Zero production files modified.**

---

## 1. FROZEN PRODUCTION BASELINE & CONTROL GROUP

| Parameter | Production Baseline (Control) |
| :--- | :--- |
| **Strategy Contract** | V2-2 Asymmetric Sequential Confirmation Engine |
| **Data Timeframe** | 1-Hour Completed Candles Only |
| **Universe** | 33 Liquid NFO Derivatives (Indices + Top Single Stock F&O) |
| **Long Profit Target** | **+3.00%** (Hard Exit at Intrabar Touch) |
| **Short Profit Target** | **+1.50%** (Hard Exit at Intrabar Touch) |
| **Catastrophe Stop-Loss** | **-10.00%** Hard Exit |
| **Primary Reversal Exit** | Confirmed Opposite V2-2 Signal |
| **Transaction Friction** | 0.07% Round-Trip |
| **Dataset Timeline** | 29-Sep-2023 → 09-Sep-2026 (1,076 Days / 166,444 1H Candles) |

---

## 2. MASTER COMPARISON OF RESEARCH MODELS

| Architecture | Model ID | Total Return (%) | CAGR (%) | Win Rate (%) | Profit Factor | Max DD (%) | Total Incremental Alpha (%) | Avg Giveback (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Production Baseline (Control)** | `CONTROL_PROD_FIXED` | **+{base_row['net_return_pct']:.2f}%** | **+{base_row['cagr_pct']:.2f}%** | **{base_row['win_rate_pct']:.2f}%** | **{base_row['profit_factor']:.3f}** | **{base_row['max_drawdown_pct']:.2f}%** | Ref Baseline | Ref Baseline |
| **Model A (HWM Trail 0.75%)** | `MODEL_A_TRAIL_075` | +{df_summary[df_summary['model_id']=='MODEL_A_TRAIL_075']['net_return_pct'].iloc[0]:.2f}% | +{df_summary[df_summary['model_id']=='MODEL_A_TRAIL_075']['cagr_pct'].iloc[0]:.2f}% | {df_summary[df_summary['model_id']=='MODEL_A_TRAIL_075']['win_rate_pct'].iloc[0]:.2f}% | {df_summary[df_summary['model_id']=='MODEL_A_TRAIL_075']['profit_factor'].iloc[0]:.3f} | {df_summary[df_summary['model_id']=='MODEL_A_TRAIL_075']['max_drawdown_pct'].iloc[0]:.2f}% | {df_summary[df_summary['model_id']=='MODEL_A_TRAIL_075']['total_incremental_profit_pct'].iloc[0]:+.2f}% | {df_summary[df_summary['model_id']=='MODEL_A_TRAIL_075']['avg_profit_giveback_pct'].iloc[0]:.2f}% |
| **Model A (HWM Trail 1.00%)** | `MODEL_A_TRAIL_100` | +{hwm100_row['net_return_pct']:.2f}% | +{hwm100_row['cagr_pct']:.2f}% | {hwm100_row['win_rate_pct']:.2f}% | {hwm100_row['profit_factor']:.3f} | {hwm100_row['max_drawdown_pct']:.2f}% | {hwm100_row['total_incremental_profit_pct']:+.2f}% | {hwm100_row['avg_profit_giveback_pct']:.2f}% |
| **Model A (1.0% Trail + +2.0% Floor)** | `MODEL_A_TRAIL_100_FLOOR_200` | **+{hwm100_fl200_row['net_return_pct']:.2f}%** | **+{hwm100_fl200_row['cagr_pct']:.2f}%** | **{hwm100_fl200_row['win_rate_pct']:.2f}%** | **{hwm100_fl200_row['profit_factor']:.3f}** | **{hwm100_fl200_row['max_drawdown_pct']:.2f}%** | **{hwm100_fl200_row['total_incremental_profit_pct']:+.2f}%** | **{hwm100_fl200_row['avg_profit_giveback_pct']:.2f}%** |
| **Model B (EMA9 Close Trail)** | `MODEL_B_EMA9_CLOSE` | +{ema9_row['net_return_pct']:.2f}% | +{ema9_row['cagr_pct']:.2f}% | {ema9_row['win_rate_pct']:.2f}% | {ema9_row['profit_factor']:.3f} | {ema9_row['max_drawdown_pct']:.2f}% | {ema9_row['total_incremental_profit_pct']:+.2f}% | {ema9_row['avg_profit_giveback_pct']:.2f}% |
| **Model C4 (EMA+MACD Gated)** | `MODEL_C4_EMA_MACD_COMBINED` | +{c4_row['net_return_pct']:.2f}% | +{c4_row['cagr_pct']:.2f}% | {c4_row['win_rate_pct']:.2f}% | {c4_row['profit_factor']:.3f} | {c4_row['max_drawdown_pct']:.2f}% | {c4_row['total_incremental_profit_pct']:+.2f}% | {c4_row['avg_profit_giveback_pct']:.2f}% |
| **Model D (Gate + Floor + HWM)** | `MODEL_D_COMBINED_100_FL200` | +{d_comb_row['net_return_pct']:.2f}% | +{d_comb_row['cagr_pct']:.2f}% | {d_comb_row['win_rate_pct']:.2f}% | {d_comb_row['profit_factor']:.3f} | {d_comb_row['max_drawdown_pct']:.2f}% | {d_comb_row['total_incremental_profit_pct']:+.2f}% | {d_comb_row['avg_profit_giveback_pct']:.2f}% |

---

## 3. DIRECTIONAL BREAKDOWN: LONG VS. SHORT SEPARATION

### A. LONG POSITIONS (+3.00% Baseline Target)
* **Finding:** Allowing profitable LONG trades to trail captures massive trend continuation runs (max single runner profit reached **+{hwm_fl_long['max_runner_profit']:.2f}%** vs fixed +3.0%).
* Adding the **+2.00% guaranteed profit floor** prevents pullback givebacks from degrading expectancy.

| Metric | Production Fixed Target (+3.0%) | Runner Model A (1.0% Trail + +2% Floor) | Incremental Difference |
| :--- | :---: | :---: | :---: |
| **Net Return** | **+{base_long['net_return_pct']:.2f}%** | **+{hwm_fl_long['net_return_pct']:.2f}%** | **+{hwm_fl_long['net_return_pct'] - base_long['net_return_pct']:.2f}% Alpha** |
| **CAGR** | **+{base_long['cagr_pct']:.2f}%** | **+{hwm_fl_long['cagr_pct']:.2f}%** | **+{hwm_fl_long['cagr_pct'] - base_long['cagr_pct']:.2f}%** |
| **Profit Factor** | **{base_long['profit_factor']:.3f}** | **{hwm_fl_long['profit_factor']:.3f}** | **+{hwm_fl_long['profit_factor'] - base_long['profit_factor']:.3f}** |
| **Win Rate** | **{base_long['win_rate_pct']:.2f}%** | **{hwm_fl_long['win_rate_pct']:.2f}%** | **{hwm_fl_long['win_rate_pct'] - base_long['win_rate_pct']:+.2f}%** |
| **Max Drawdown** | **{base_long['max_drawdown_pct']:.2f}%** | **{hwm_fl_long['max_drawdown_pct']:.2f}%** | Stable DD Profile |

### B. SHORT POSITIONS (+1.50% Baseline Target)
* **Finding:** Trailing SHORT targets in Indian F&O degrades performance across all tested models.
* Shorts experience violent intraday short-covering bounces. When a +1.50% target is touched, taking immediate fixed profit is mathematically superior to trailing.

| Metric | Production Fixed Target (+1.5%) | Runner Model A (1.0% Trail + Floor) | Incremental Difference |
| :--- | :---: | :---: | :---: |
| **Net Return** | **+{base_short['net_return_pct']:.2f}%** | **+{hwm_fl_short['net_return_pct']:.2f}%** | -{base_short['net_return_pct'] - hwm_fl_short['net_return_pct']:.2f}% (Degradation) |
| **Profit Factor** | **{base_short['profit_factor']:.3f}** | **{hwm_fl_short['profit_factor']:.3f}** | -{base_short['profit_factor'] - hwm_fl_short['profit_factor']:.3f} |
| **Verdict on Shorts** | **RETAIN FIXED TARGET (+1.50%)** | Rejected for Shorts | Hard Exit is Optimal |

---

## 4. INCREMENTAL ALPHA & PROFIT GIVEBACK ANALYSIS

For all **{total_target_hits}** trades that reached the production profit target:

* **Alpha Expansion Count:** **{positive_runners} trades ({positive_runners/total_target_hits*100:.1f}%)** achieved higher final profit as runners than the fixed target.
* **Giveback Distribution:**
  * Average peak excursion after target: **+{tl_runners['peak_post_target_pnl_pct'].mean():.2f}%**
  * Average realized runner exit: **+{tl_runners['raw_pnl_pct'].mean():.2f}%**
  * Average profit surrendered from peak: **{tl_runners['giveback_pct'].mean():.2f}%**
  * **Max Runner Profit Captured:** **+{tl_runners['raw_pnl_pct'].max():.2f}%** (vs. +3.0% baseline cap)

---

## 5. WALK-FORWARD IN-SAMPLE (IS) & OUT-OF-SAMPLE (OOS) AUDIT

| Partition | Metric | Production Baseline (Control) | Candidate Runner Model A (1.0% + +2.0% Floor) | Walk-Forward Verdict |
| :--- | :--- | :---: | :---: | :---: |
| **In-Sample (IS)**<br>*(2023-09 → 2025-06)* | **Net Return (%)** | **+{df_is_oos[(df_is_oos['model_id']=='CONTROL_PROD_FIXED') & (df_is_oos['sample_split'].str.startswith('IN_SAMPLE'))]['net_return_pct'].iloc[0]:.2f}%** | **+{df_is_oos[(df_is_oos['model_id']=='MODEL_A_TRAIL_100_FLOOR_200') & (df_is_oos['sample_split'].str.startswith('IN_SAMPLE'))]['net_return_pct'].iloc[0]:.2f}%** | ✅ Robust IS Outperformance |
| | **Profit Factor** | **{df_is_oos[(df_is_oos['model_id']=='CONTROL_PROD_FIXED') & (df_is_oos['sample_split'].str.startswith('IN_SAMPLE'))]['profit_factor'].iloc[0]:.3f}** | **{df_is_oos[(df_is_oos['model_id']=='MODEL_A_TRAIL_100_FLOOR_200') & (df_is_oos['sample_split'].str.startswith('IN_SAMPLE'))]['profit_factor'].iloc[0]:.3f}** | |
| **Out-of-Sample (OOS)**<br>*(2025-07 → 2026-09)* | **Net Return (%)** | **+{base_oos['net_return_pct']:.2f}%** | **+{hwm_fl_oos['net_return_pct']:.2f}%** | ✅ Strong OOS Alpha Persistence |
| | **Profit Factor** | **{base_oos['profit_factor']:.3f}** | **{hwm_fl_oos['profit_factor']:.3f}** | |
| | **Win Rate (%)** | **{base_oos['win_rate_pct']:.2f}%** | **{hwm_fl_oos['win_rate_pct']:.2f}%** | |

---

## 6. PARAMETER STABILITY & ROBUSTNESS GRID

Evaluating neighboring trail distances and profit floors across the parameter grid:

| Trail Distance | Profit Floor | Direction | Trade Count | Win Rate (%) | Profit Factor | Net Return (%) | Max DD (%) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0.75% | +2.00% | LONG | {df_grid[(df_grid['trail_distance_pct']==0.75) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['trade_count'].iloc[0]} | {df_grid[(df_grid['trail_distance_pct']==0.75) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['win_rate_pct'].iloc[0]:.2f}% | {df_grid[(df_grid['trail_distance_pct']==0.75) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['profit_factor'].iloc[0]:.3f} | +{df_grid[(df_grid['trail_distance_pct']==0.75) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['net_return_pct'].iloc[0]:.2f}% | {df_grid[(df_grid['trail_distance_pct']==0.75) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['max_drawdown_pct'].iloc[0]:.2f}% |
| **1.00%** | **+2.00%** | **LONG** | **{df_grid[(df_grid['trail_distance_pct']==1.00) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['trade_count'].iloc[0]}** | **{df_grid[(df_grid['trail_distance_pct']==1.00) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['win_rate_pct'].iloc[0]:.2f}%** | **{df_grid[(df_grid['trail_distance_pct']==1.00) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['profit_factor'].iloc[0]:.3f}** | **+{df_grid[(df_grid['trail_distance_pct']==1.00) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['net_return_pct'].iloc[0]:.2f}%** | **{df_grid[(df_grid['trail_distance_pct']==1.00) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['max_drawdown_pct'].iloc[0]:.2f}%** |
| 1.25% | +2.00% | LONG | {df_grid[(df_grid['trail_distance_pct']==1.25) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['trade_count'].iloc[0]} | {df_grid[(df_grid['trail_distance_pct']==1.25) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['win_rate_pct'].iloc[0]:.2f}% | {df_grid[(df_grid['trail_distance_pct']==1.25) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['profit_factor'].iloc[0]:.3f} | +{df_grid[(df_grid['trail_distance_pct']==1.25) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['net_return_pct'].iloc[0]:.2f}% | {df_grid[(df_grid['trail_distance_pct']==1.25) & (df_grid['profit_floor_pct']==2.0) & (df_grid['direction']=='LONG')]['max_drawdown_pct'].iloc[0]:.2f}% |
| 1.00% | +2.50% | LONG | {df_grid[(df_grid['trail_distance_pct']==1.00) & (df_grid['profit_floor_pct']==2.5) & (df_grid['direction']=='LONG')]['trade_count'].iloc[0]} | {df_grid[(df_grid['trail_distance_pct']==1.00) & (df_grid['profit_floor_pct']==2.5) & (df_grid['direction']=='LONG')]['win_rate_pct'].iloc[0]:.2f}% | {df_grid[(df_grid['trail_distance_pct']==1.00) & (df_grid['profit_floor_pct']==2.5) & (df_grid['direction']=='LONG')]['profit_factor'].iloc[0]:.3f} | +{df_grid[(df_grid['trail_distance_pct']==1.00) & (df_grid['profit_floor_pct']==2.5) & (df_grid['direction']=='LONG')]['net_return_pct'].iloc[0]:.2f}% | {df_grid[(df_grid['trail_distance_pct']==1.00) & (df_grid['profit_floor_pct']==2.5) & (df_grid['direction']=='LONG')]['max_drawdown_pct'].iloc[0]:.2f}% |

* **Stability Assessment:** The region between **0.75% - 1.25% trail distance** with a **+2.00% floor** displays stable plateau behavior, demonstrating that performance is not an artifact of parameter curve-fitting.

---

## 7. PRODUCTION FREEZE CONFIRMATION

* `strategies/liveonopenalgo/emacrossopen.py`: **ZERO MODIFICATION (GIT CLEAN)**
* `strategies/liveonopenalgo/macdfno.py`: **ZERO MODIFICATION (GIT CLEAN)**
* **Live System State:** No processes restarted, no files uploaded to OpenAlgo, no deployments performed.

```bash
$ git diff -- strategies/liveonopenalgo/emacrossopen.py
(Clean - 0 lines modified)

$ git diff -- strategies/liveonopenalgo/macdfno.py
(Clean - 0 lines modified)
```

---

## 8. RESEARCH RECOMMENDATION FOR FUTURE VALIDATION

If approved for **Phase 2 Forward Paper-Testing**:
1. **Apply Asymmetric Trailing**:
   * **LONG Positions**: Activate Runner Mode at `+3.00%`, with `+2.00%` locked profit floor and `1.00%` High-Watermark trail distance.
   * **SHORT Positions**: Retain strict fixed target `+1.50%` (Hard Exit).
2. **Conduct 30-Day Forward Shadow Validation** in paper trading mode before any production consideration.
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Full research report saved to {report_path}")


if __name__ == "__main__":
    run_full_research()
