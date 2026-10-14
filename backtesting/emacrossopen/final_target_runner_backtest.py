"""
Final Target-to-Runner Quantitative Backtest & Research Engine
File: backtesting/emacrossopen/final_target_runner_backtest.py

Independent, causal, lookahead-free quantitative backtest of the proposed
Target-to-Runner architecture against the frozen production strategy.
"""

import math
import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
DATA_DIR = CURRENT_DIR / "data"

BASE_FRICTION_PCT = 0.07  # 0.07% round-trip baseline
IS_SPLIT_DATE = pd.to_datetime("2025-07-01", utc=True)
TOTAL_DAYS = 1076.0
YEARS = TOTAL_DAYS / 365.25  # ~2.946 years

PROD_LONG_TP_PCT = 3.00
PROD_SHORT_TP_PCT = 1.50
PROD_CATASTROPHE_SL_PCT = 10.00


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    df["ema9"] = close.ewm(span=9, adjust=False).mean()
    df["ema26"] = close.ewm(span=26, adjust=False).mean()

    df["ema12"] = close.ewm(span=12, adjust=False).mean()
    df["macd"] = df["ema12"] - df["ema26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["tr"] = tr
    df["atr14"] = tr.rolling(window=14).mean()
    df["vol_sma20"] = volume.rolling(window=20).mean()

    return df


def load_all_dataset() -> Dict[str, pd.DataFrame]:
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
        atr = df["atr14"].values
        times = df.index

        active_trade = None
        active_pending = None

        for i in range(1, n - 1):
            curr_ema9 = ema9[i]
            prev_ema9 = ema9[i - 1]
            curr_ema26 = ema26[i]
            prev_ema26 = ema26[i - 1]

            curr_macd = macd[i]
            prev_macd = macd[i - 1]
            curr_sig = signal[i]
            prev_sig = signal[i - 1]

            ema_cross_up = (prev_ema9 <= prev_ema26) and (curr_ema9 > curr_ema26)
            ema_cross_down = (prev_ema9 >= prev_ema26) and (curr_ema9 < curr_ema26)
            macd_cross_up = (prev_macd <= prev_sig) and (curr_macd > curr_sig)
            macd_cross_down = (prev_macd >= prev_sig) and (curr_macd < curr_sig)

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

            # 2. Sequential Confirmation
            if new_sig is None:
                if active_pending is not None:
                    active_pending["elapsed_bars"] += 1
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

                if active_trade is not None:
                    active_trade["forward_reversal_idx"] = entry_idx
                    active_trade["forward_reversal_time"] = entry_time
                    active_trade["forward_reversal_price"] = entry_px
                    raw_trades.append(active_trade)
                    active_trade = None

                active_trade = {
                    "symbol": sym,
                    "direction": 1 if new_sig == "BUY" else -1,
                    "direction_str": "LONG" if new_sig == "BUY" else "SHORT",
                    "signal_time": times[i],
                    "entry_time": entry_time,
                    "entry_idx": entry_idx,
                    "entry_price": float(entry_px),
                    "conf_type": conf_type,
                    "atr_entry": float(atr[i]),
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
    model_family: str,  # "FIXED", "HWM", "EMA9", "EMA9_MACD"
    trail_pct: float = 0.50,
    friction_pct: float = BASE_FRICTION_PCT,
    long_tp_pct: float = PROD_LONG_TP_PCT,
    short_tp_pct: float = PROD_SHORT_TP_PCT,
    sl_pct: float = PROD_CATASTROPHE_SL_PCT,
) -> Dict[str, Any]:
    df_slice = trade["df_slice"]
    direction = trade["direction"]
    entry_px = trade["entry_price"]
    entry_time = trade["entry_time"]
    target_pct = long_tp_pct if direction == 1 else short_tp_pct

    target_price = entry_px * (1.0 + (target_pct / 100.0)) if direction == 1 else entry_px * (1.0 - (target_pct / 100.0))
    sl_price = entry_px * (1.0 - (sl_pct / 100.0)) if direction == 1 else entry_px * (1.0 + (sl_pct / 100.0))

    exit_reason = "V2-2_REVERSAL"
    exit_price = trade["forward_reversal_price"]
    exit_time = trade["forward_reversal_time"]
    bars_held = 0

    target_reached = False
    target_bar_idx = -1
    target_bar_time = None
    runner_active = False

    peak_price = entry_px
    trough_price = entry_px
    max_favorable_px = entry_px
    max_adverse_px = entry_px

    for bar_num, (ts, row) in enumerate(df_slice.iterrows()):
        curr_open = float(row["Open"])
        curr_high = float(row["High"])
        curr_low = float(row["Low"])
        curr_close = float(row["Close"])
        curr_ema9 = float(row["ema9"])
        curr_ema26 = float(row["ema26"])
        curr_macd = float(row["macd"])
        curr_sig = float(row["macd_signal"])

        bars_held = bar_num + 1

        if direction == 1:
            max_favorable_px = max(max_favorable_px, curr_high)
            max_adverse_px = min(max_adverse_px, curr_low)
        else:
            max_favorable_px = min(max_favorable_px, curr_low)
            max_adverse_px = max(max_adverse_px, curr_high)

        # 1. Catastrophe SL
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

        # 2. Check Target Touch
        if not target_reached:
            hit_target = (direction == 1 and curr_high >= target_price) or (direction == -1 and curr_low <= target_price)
            if hit_target:
                target_reached = True
                target_bar_idx = bar_num
                target_bar_time = ts

                if model_family == "FIXED":
                    exit_reason = "TARGET_HIT"
                    exit_price = target_price
                    exit_time = ts
                    break
                else:
                    runner_active = True
                    if direction == 1:
                        peak_price = max(peak_price, curr_high)
                    else:
                        trough_price = min(trough_price, curr_low)

        # 3. Trailing logic if runner active
        if runner_active:
            if direction == 1:
                peak_price = max(peak_price, curr_high)
            else:
                trough_price = min(trough_price, curr_low)

            if model_family == "HWM":
                if direction == 1:
                    effective_trail_sl = peak_price * (1.0 - (trail_pct / 100.0))
                    if curr_low <= effective_trail_sl:
                        exit_reason = "RUNNER_HWM_TRAIL"
                        exit_price = effective_trail_sl
                        exit_time = ts
                        break
                else:  # SHORT
                    effective_trail_sl = trough_price * (1.0 + (trail_pct / 100.0))
                    if curr_high >= effective_trail_sl:
                        exit_reason = "RUNNER_HWM_TRAIL"
                        exit_price = effective_trail_sl
                        exit_time = ts
                        break

            elif model_family == "EMA9":
                if direction == 1:
                    if curr_close < curr_ema9:
                        exit_reason = "RUNNER_EMA9_EXIT"
                        exit_price = curr_close
                        exit_time = ts
                        break
                else:
                    if curr_close > curr_ema9:
                        exit_reason = "RUNNER_EMA9_EXIT"
                        exit_price = curr_close
                        exit_time = ts
                        break

            elif model_family == "EMA9_MACD":
                if direction == 1:
                    if curr_close < curr_ema9 and curr_macd < curr_sig:
                        exit_reason = "RUNNER_EMA9_MACD_EXIT"
                        exit_price = curr_close
                        exit_time = ts
                        break
                else:
                    if curr_close > curr_ema9 and curr_macd > curr_sig:
                        exit_reason = "RUNNER_EMA9_MACD_EXIT"
                        exit_price = curr_close
                        exit_time = ts
                        break

        # 4. Check Reversal Time
        if ts >= trade["forward_reversal_time"]:
            exit_reason = "V2-2_REVERSAL"
            exit_price = curr_close
            exit_time = ts
            break

    raw_pnl_pct = ((exit_price - entry_px) / entry_px) * 100.0 if direction == 1 else ((entry_px - exit_price) / entry_px) * 100.0
    net_pnl_pct = raw_pnl_pct - friction_pct

    fixed_ref_pnl_pct = (target_pct - friction_pct) if target_reached else net_pnl_pct
    incremental_profit_pct = (net_pnl_pct - fixed_ref_pnl_pct) if target_reached else 0.0

    if direction == 1:
        mfe_pct = ((max_favorable_px - entry_px) / entry_px) * 100.0
        mae_pct = ((entry_px - max_adverse_px) / entry_px) * 100.0
        peak_post_target_pnl = ((peak_price - entry_px) / entry_px) * 100.0 if target_reached else 0.0
        giveback_pct = (peak_post_target_pnl - raw_pnl_pct) if (target_reached and peak_post_target_pnl > raw_pnl_pct) else 0.0
    else:
        mfe_pct = ((entry_px - max_favorable_px) / entry_px) * 100.0
        mae_pct = ((max_adverse_px - entry_px) / entry_px) * 100.0
        peak_post_target_pnl = ((entry_px - trough_price) / entry_px) * 100.0 if target_reached else 0.0
        giveback_pct = (peak_post_target_pnl - raw_pnl_pct) if (target_reached and peak_post_target_pnl > raw_pnl_pct) else 0.0

    # Check threshold reaches post entry
    reached_4 = (mfe_pct >= 4.0)
    reached_5 = (mfe_pct >= 5.0)
    reached_6 = (mfe_pct >= 6.0)
    reached_8 = (mfe_pct >= 8.0)
    reached_10 = (mfe_pct >= 10.0)

    return {
        "symbol": trade["symbol"],
        "direction": direction,
        "direction_str": trade["direction_str"],
        "entry_time": entry_time,
        "entry_price": entry_px,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "bars_held": bars_held,
        "target_reached": target_reached,
        "runner_active": runner_active,
        "raw_pnl_pct": raw_pnl_pct,
        "net_pnl_pct": net_pnl_pct,
        "incremental_profit_pct": incremental_profit_pct,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "peak_post_target_pnl": peak_post_target_pnl,
        "giveback_pct": giveback_pct,
        "reached_4": reached_4,
        "reached_5": reached_5,
        "reached_6": reached_6,
        "reached_8": reached_8,
        "reached_10": reached_10,
        "is_is": (pd.to_datetime(entry_time) < IS_SPLIT_DATE),
    }


def compute_metrics(sim_trades: List[Dict[str, Any]], years: float = YEARS) -> Dict[str, Any]:
    if not sim_trades:
        return {}

    df = pd.DataFrame(sim_trades)
    n = len(df)
    net_pnl = df["net_pnl_pct"].values
    raw_pnl = df["raw_pnl_pct"].values

    wins = df[df["net_pnl_pct"] > 0]
    losses = df[df["net_pnl_pct"] <= 0]
    win_rate = (len(wins) / n) * 100.0

    total_net = float(np.sum(net_pnl))
    gross_gain = float(wins["net_pnl_pct"].sum()) if len(wins) > 0 else 0.0
    gross_loss = float(abs(losses["net_pnl_pct"].sum())) if len(losses) > 0 else 0.0
    profit_factor = (gross_gain / gross_loss) if gross_loss > 0 else (999.0 if gross_gain > 0 else 1.0)
    expectancy = float(np.mean(net_pnl))

    # CAGR (additive percentage compounding approx vs raw sum)
    # Using annualized arithmetic return as standard across openalgo backtests
    cagr = total_net / years

    # Drawdown calculation
    equity_curve = np.cumsum(net_pnl)
    peaks = np.maximum.accumulate(equity_curve)
    drawdowns = peaks - equity_curve
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
    avg_dd = float(np.mean(drawdowns)) if len(drawdowns) > 0 else 0.0

    max_loss = float(np.min(net_pnl))
    avg_win = float(wins["net_pnl_pct"].mean()) if len(wins) > 0 else 0.0
    avg_loss = float(losses["net_pnl_pct"].mean()) if len(losses) > 0 else 0.0

    mfe_mean = float(df["mfe_pct"].mean())
    mae_mean = float(df["mae_pct"].mean())

    # Target-to-runner specific
    target_hits = df[df["target_reached"] == True]
    n_target_hits = len(target_hits)
    n_runners = len(df[df["runner_active"] == True])
    conversion_rate = (n_runners / n_target_hits * 100.0) if n_target_hits > 0 else 0.0

    avg_giveback = float(target_hits["giveback_pct"].mean()) if n_target_hits > 0 else 0.0
    max_giveback = float(target_hits["giveback_pct"].max()) if n_target_hits > 0 else 0.0
    incremental_alpha = float(df["incremental_profit_pct"].sum())

    trail_stopped = df[df["exit_reason"].str.startswith("RUNNER")]
    pct_stopped_by_trail = (len(trail_stopped) / n_runners * 100.0) if n_runners > 0 else 0.0

    pct_r4 = (df["reached_4"].sum() / n_target_hits * 100.0) if n_target_hits > 0 else 0.0
    pct_r5 = (df["reached_5"].sum() / n_target_hits * 100.0) if n_target_hits > 0 else 0.0
    pct_r6 = (df["reached_6"].sum() / n_target_hits * 100.0) if n_target_hits > 0 else 0.0
    pct_r8 = (df["reached_8"].sum() / n_target_hits * 100.0) if n_target_hits > 0 else 0.0
    pct_r10 = (df["reached_10"].sum() / n_target_hits * 100.0) if n_target_hits > 0 else 0.0

    avg_duration_bars = float(df["bars_held"].mean())

    return {
        "n_trades": n,
        "n_target_hits": n_target_hits,
        "win_rate": win_rate,
        "net_return": total_net,
        "cagr": cagr,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "max_drawdown": max_dd,
        "avg_drawdown": avg_dd,
        "max_loss": max_loss,
        "avg_winner": avg_win,
        "avg_loser": avg_loss,
        "mfe": mfe_mean,
        "mae": mae_mean,
        "avg_giveback": avg_giveback,
        "max_giveback": max_giveback,
        "incremental_alpha": incremental_alpha,
        "conversion_rate": conversion_rate,
        "pct_stopped_by_trail": pct_stopped_by_trail,
        "pct_r4": pct_r4,
        "pct_r5": pct_r5,
        "pct_r6": pct_r6,
        "pct_r8": pct_r8,
        "pct_r10": pct_r10,
        "avg_duration_bars": avg_duration_bars,
    }


def run_comprehensive_validation():
    print("=" * 80)
    print("STARTING COMPREHENSIVE TARGET-TO-RUNNER BACKTEST VALIDATION")
    print("=" * 80)

    data_map = load_all_dataset()
    print(f"Loaded {len(data_map)} symbol parquet files successfully.")

    raw_trades = extract_v2_2_trades(data_map)
    print(f"Extracted {len(raw_trades)} raw V2-2 trade slices across dataset.")

    long_trades = [t for t in raw_trades if t["direction"] == 1]
    short_trades = [t for t in raw_trades if t["direction"] == -1]
    print(f"LONG Trades: {len(long_trades)} | SHORT Trades: {len(short_trades)}")

    # Define Candidate Models
    # Long Models: A to H
    long_models = [
        {"id": "LONG_A_FIXED", "family": "FIXED", "trail": 0.0, "name": "Fixed +3.00% Control"},
        {"id": "LONG_B_HWM_035", "family": "HWM", "trail": 0.35, "name": "HWM Trail 0.35%"},
        {"id": "LONG_C_HWM_050", "family": "HWM", "trail": 0.50, "name": "HWM Trail 0.50%"},
        {"id": "LONG_D_HWM_060", "family": "HWM", "trail": 0.60, "name": "HWM Trail 0.60%"},
        {"id": "LONG_E_HWM_075", "family": "HWM", "trail": 0.75, "name": "HWM Trail 0.75%"},
        {"id": "LONG_F_HWM_100", "family": "HWM", "trail": 1.00, "name": "HWM Trail 1.00%"},
        {"id": "LONG_G_EMA9", "family": "EMA9", "trail": 0.0, "name": "EMA9 Close Trail"},
        {"id": "LONG_H_EMA9_MACD", "family": "EMA9_MACD", "trail": 0.0, "name": "EMA9 + MACD Trail"},
    ]

    # Short Models: A to H
    short_models = [
        {"id": "SHORT_A_FIXED", "family": "FIXED", "trail": 0.0, "name": "Fixed +1.50% Control"},
        {"id": "SHORT_B_HWM_035", "family": "HWM", "trail": 0.35, "name": "HWM Trail 0.35%"},
        {"id": "SHORT_C_HWM_050", "family": "HWM", "trail": 0.50, "name": "HWM Trail 0.50%"},
        {"id": "SHORT_D_HWM_060", "family": "HWM", "trail": 0.60, "name": "HWM Trail 0.60%"},
        {"id": "SHORT_E_HWM_075", "family": "HWM", "trail": 0.75, "name": "HWM Trail 0.75%"},
        {"id": "SHORT_F_HWM_100", "family": "HWM", "trail": 1.00, "name": "HWM Trail 1.00%"},
        {"id": "SHORT_G_EMA9", "family": "EMA9", "trail": 0.0, "name": "EMA9 Close Trail"},
        {"id": "SHORT_H_EMA9_MACD", "family": "EMA9_MACD", "trail": 0.0, "name": "EMA9 + MACD Trail"},
    ]

    # 1. Full Historical Backtest for all models
    results_master = []
    sim_data_store = {}

    for m in long_models:
        sims = [simulate_trade_exit(t, m["family"], trail_pct=m["trail"]) for t in long_trades]
        sim_data_store[m["id"]] = sims
        met = compute_metrics(sims)
        met["direction"] = "LONG"
        met["model_id"] = m["id"]
        met["model_name"] = m["name"]
        results_master.append(met)

    for m in short_models:
        sims = [simulate_trade_exit(t, m["family"], trail_pct=m["trail"]) for t in short_trades]
        sim_data_store[m["id"]] = sims
        met = compute_metrics(sims)
        met["direction"] = "SHORT"
        met["model_id"] = m["id"]
        met["model_name"] = m["name"]
        results_master.append(met)

    df_master = pd.DataFrame(results_master)
    df_master.to_csv(CURRENT_DIR / "final_models_master.csv", index=False)
    print("\n--- MASTER MODEL RESULTS (FULL HISTORICAL) ---")
    print(df_master[["direction", "model_name", "net_return", "profit_factor", "cagr", "max_drawdown", "expectancy", "incremental_alpha", "avg_giveback"]].to_string(index=False))

    # 2. In-Sample vs Out-of-Sample Split
    is_oos_results = []
    for model_id, sims in sim_data_store.items():
        is_sims = [s for s in sims if s["is_is"]]
        oos_sims = [s for s in sims if not s["is_is"]]
        m_is = compute_metrics(is_sims, years=IS_SPLIT_DATE.year - 2023 + 0.5)
        m_oos = compute_metrics(oos_sims, years=YEARS - (IS_SPLIT_DATE.year - 2023 + 0.5))
        is_oos_results.append({
            "model_id": model_id,
            "is_net": m_is.get("net_return", 0.0),
            "is_pf": m_is.get("profit_factor", 0.0),
            "is_dd": m_is.get("max_drawdown", 0.0),
            "oos_net": m_oos.get("net_return", 0.0),
            "oos_pf": m_oos.get("profit_factor", 0.0),
            "oos_dd": m_oos.get("max_drawdown", 0.0),
            "oos_alpha": m_oos.get("incremental_alpha", 0.0),
        })
    df_is_oos = pd.DataFrame(is_oos_results)
    df_is_oos.to_csv(CURRENT_DIR / "final_models_is_oos.csv", index=False)

    # 3. Rolling Walk-Forward Analysis (4 Slices)
    # Divide time chronologically into 4 quarters
    timestamps = [pd.to_datetime(t["entry_time"]) for t in raw_trades]
    min_t, max_t = min(timestamps), max(timestamps)
    dt_step = (max_t - min_t) / 4

    rolling_results = []
    for fold in range(4):
        f_start = min_t + fold * dt_step
        f_end = min_t + (fold + 1) * dt_step
        f_years = (f_end - f_start).total_seconds() / (365.25 * 86400)
        
        # Test key models: Control vs Long HWM 0.50 vs Short HWM 0.50
        for m_id in ["LONG_A_FIXED", "LONG_C_HWM_050", "SHORT_A_FIXED", "SHORT_C_HWM_050"]:
            sims = sim_data_store[m_id]
            f_sims = [s for s in sims if f_start <= pd.to_datetime(s["entry_time"]) < f_end]
            met = compute_metrics(f_sims, years=f_years)
            rolling_results.append({
                "fold": fold + 1,
                "fold_range": f"{f_start.strftime('%Y-%m')} to {f_end.strftime('%Y-%m')}",
                "model_id": m_id,
                "net_return": met.get("net_return", 0.0),
                "pf": met.get("profit_factor", 0.0),
                "trades": met.get("n_trades", 0),
                "alpha": met.get("incremental_alpha", 0.0),
            })
    df_rolling = pd.DataFrame(rolling_results)
    df_rolling.to_csv(CURRENT_DIR / "final_models_rolling.csv", index=False)

    # 4. Parameter Sensitivity Plateau Analysis (Fine grid: 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.75, 1.00)
    fine_grid = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.75, 1.00]
    plateau_long = []
    plateau_short = []

    for trail in fine_grid:
        l_sims = [simulate_trade_exit(t, "HWM", trail_pct=trail) for t in long_trades]
        s_sims = [simulate_trade_exit(t, "HWM", trail_pct=trail) for t in short_trades]
        l_met = compute_metrics(l_sims)
        s_met = compute_metrics(s_sims)
        plateau_long.append({
            "trail_pct": trail,
            "net_return": l_met["net_return"],
            "pf": l_met["profit_factor"],
            "max_dd": l_met["max_drawdown"],
            "expectancy": l_met["expectancy"],
            "incremental_alpha": l_met["incremental_alpha"],
            "avg_giveback": l_met["avg_giveback"],
        })
        plateau_short.append({
            "trail_pct": trail,
            "net_return": s_met["net_return"],
            "pf": s_met["profit_factor"],
            "max_dd": s_met["max_drawdown"],
            "expectancy": s_met["expectancy"],
            "incremental_alpha": s_met["incremental_alpha"],
            "avg_giveback": s_met["avg_giveback"],
        })
    df_plat_long = pd.DataFrame(plateau_long)
    df_plat_short = pd.DataFrame(plateau_short)
    df_plat_long.to_csv(CURRENT_DIR / "final_plateau_long.csv", index=False)
    df_plat_short.to_csv(CURRENT_DIR / "final_plateau_short.csv", index=False)

    # 5. Transaction-Cost / Slippage Stress Test (0.00%, 0.05%, 0.07%, 0.10%, 0.15%, 0.20%)
    frictions = [0.00, 0.05, 0.07, 0.10, 0.15, 0.20]
    friction_results = []
    for f in frictions:
        l_ctrl = compute_metrics([simulate_trade_exit(t, "FIXED", friction_pct=f) for t in long_trades])
        l_cand = compute_metrics([simulate_trade_exit(t, "HWM", trail_pct=0.50, friction_pct=f) for t in long_trades])
        s_ctrl = compute_metrics([simulate_trade_exit(t, "FIXED", friction_pct=f) for t in short_trades])
        s_cand = compute_metrics([simulate_trade_exit(t, "HWM", trail_pct=0.50, friction_pct=f) for t in short_trades])
        friction_results.append({
            "friction_pct": f,
            "long_ctrl_net": l_ctrl["net_return"],
            "long_cand_net": l_cand["net_return"],
            "long_alpha": l_cand["net_return"] - l_ctrl["net_return"],
            "short_ctrl_net": s_ctrl["net_return"],
            "short_cand_net": s_cand["net_return"],
            "short_alpha": s_cand["net_return"] - s_ctrl["net_return"],
        })
    df_fric = pd.DataFrame(friction_results)
    df_fric.to_csv(CURRENT_DIR / "final_friction_stress.csv", index=False)

    # 6. Monte Carlo Validation (5,000 resamples)
    np.random.seed(42)
    mc_long_ctrl = [s["net_pnl_pct"] for s in sim_data_store["LONG_A_FIXED"]]
    mc_long_cand = [s["net_pnl_pct"] for s in sim_data_store["LONG_C_HWM_050"]]
    mc_short_ctrl = [s["net_pnl_pct"] for s in sim_data_store["SHORT_A_FIXED"]]
    mc_short_cand = [s["net_pnl_pct"] for s in sim_data_store["SHORT_C_HWM_050"]]

    n_mc = 5000
    mc_long_alphas = []
    mc_short_alphas = []

    for _ in range(n_mc):
        idx_l = np.random.randint(0, len(mc_long_ctrl), size=len(mc_long_ctrl))
        idx_s = np.random.randint(0, len(mc_short_ctrl), size=len(mc_short_ctrl))
        mc_long_alphas.append(float(np.sum(np.array(mc_long_cand)[idx_l]) - np.sum(np.array(mc_long_ctrl)[idx_l])))
        mc_short_alphas.append(float(np.sum(np.array(mc_short_cand)[idx_s]) - np.sum(np.array(mc_short_ctrl)[idx_s])))

    mc_summary = {
        "n_simulations": n_mc,
        "long_mean_alpha": float(np.mean(mc_long_alphas)),
        "long_median_alpha": float(np.median(mc_long_alphas)),
        "long_p5_alpha": float(np.percentile(mc_long_alphas, 5)),
        "long_p95_alpha": float(np.percentile(mc_long_alphas, 95)),
        "long_prob_positive": float(np.mean(np.array(mc_long_alphas) > 0) * 100.0),
        "short_mean_alpha": float(np.mean(mc_short_alphas)),
        "short_median_alpha": float(np.median(mc_short_alphas)),
        "short_p5_alpha": float(np.percentile(mc_short_alphas, 5)),
        "short_p95_alpha": float(np.percentile(mc_short_alphas, 95)),
        "short_prob_positive": float(np.mean(np.array(mc_short_alphas) > 0) * 100.0),
    }
    with open(CURRENT_DIR / "final_monte_carlo.json", "w") as f:
        json.dump(mc_summary, f, indent=2)

    # 7. Market Regime Analysis
    # Regime by ATR / Volatility and Trend
    regime_results = []
    # Identify symbol average ATR
    atr_median = np.median([t["atr_entry"] / t["entry_price"] for t in raw_trades])
    high_vol_long = [t for t in long_trades if (t["atr_entry"] / t["entry_price"]) >= atr_median]
    low_vol_long = [t for t in long_trades if (t["atr_entry"] / t["entry_price"]) < atr_median]
    high_vol_short = [t for t in short_trades if (t["atr_entry"] / t["entry_price"]) >= atr_median]
    low_vol_short = [t for t in short_trades if (t["atr_entry"] / t["entry_price"]) < atr_median]

    regime_results.append({
        "regime": "High Volatility (ATR >= Median)",
        "direction": "LONG",
        "ctrl_net": compute_metrics([simulate_trade_exit(t, "FIXED") for t in high_vol_long])["net_return"],
        "cand_net": compute_metrics([simulate_trade_exit(t, "HWM", trail_pct=0.50) for t in high_vol_long])["net_return"],
        "alpha": compute_metrics([simulate_trade_exit(t, "HWM", trail_pct=0.50) for t in high_vol_long])["incremental_alpha"],
    })
    regime_results.append({
        "regime": "Low Volatility (ATR < Median)",
        "direction": "LONG",
        "ctrl_net": compute_metrics([simulate_trade_exit(t, "FIXED") for t in low_vol_long])["net_return"],
        "cand_net": compute_metrics([simulate_trade_exit(t, "HWM", trail_pct=0.50) for t in low_vol_long])["net_return"],
        "alpha": compute_metrics([simulate_trade_exit(t, "HWM", trail_pct=0.50) for t in low_vol_long])["incremental_alpha"],
    })
    regime_results.append({
        "regime": "High Volatility (ATR >= Median)",
        "direction": "SHORT",
        "ctrl_net": compute_metrics([simulate_trade_exit(t, "FIXED") for t in high_vol_short])["net_return"],
        "cand_net": compute_metrics([simulate_trade_exit(t, "HWM", trail_pct=0.50) for t in high_vol_short])["net_return"],
        "alpha": compute_metrics([simulate_trade_exit(t, "HWM", trail_pct=0.50) for t in high_vol_short])["incremental_alpha"],
    })
    regime_results.append({
        "regime": "Low Volatility (ATR < Median)",
        "direction": "SHORT",
        "ctrl_net": compute_metrics([simulate_trade_exit(t, "FIXED") for t in low_vol_short])["net_return"],
        "cand_net": compute_metrics([simulate_trade_exit(t, "HWM", trail_pct=0.50) for t in low_vol_short])["net_return"],
        "alpha": compute_metrics([simulate_trade_exit(t, "HWM", trail_pct=0.50) for t in low_vol_short])["incremental_alpha"],
    })
    df_regime = pd.DataFrame(regime_results)
    df_regime.to_csv(CURRENT_DIR / "final_market_regime.csv", index=False)

    print("\nValidation complete. All data tables saved.")
    return df_master, df_is_oos, df_rolling, df_plat_long, df_plat_short, df_fric, mc_summary, df_regime


if __name__ == "__main__":
    run_comprehensive_validation()
