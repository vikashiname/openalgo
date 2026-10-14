"""
Feature Extraction and Trade Reconstruction Engine for V2-2
File: backtesting/emacrossopen/feature_extractor.py

Implements exact V2-2 sequential confirmation entry logic and extracts
all Candle, Volume, EMA, MACD, and Volatility factors for every valid entry.
"""

import math
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd

from data_manager import load_or_download_all_data, SYMBOL_TICKER_MAP

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

def extract_trades_and_features(data_map: Dict[str, pd.DataFrame]) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """
    Executes V2-2 state machine and reconstructs full forward trade slices
    along with the complete feature vector for every trade.
    """
    all_trades = []
    
    for sym, raw_df in data_map.items():
        meta = SYMBOL_TICKER_MAP.get(sym, {"lot_size": 1, "sector": "UNKNOWN"})
        lot_size = meta["lot_size"]
        sector = meta["sector"]

        df = calculate_indicators(raw_df)
        df = df.dropna().copy()
        if len(df) < 50:
            continue

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

        current_pos = 0 # 1 = LONG, -1 = SHORT, 0 = FLAT
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
            curr_hist = hist[i]
            prev_hist = hist[i - 1]

            # Crossover conditions
            ema_bull = (prev_ema9 <= prev_ema26) and (curr_ema9 > curr_ema26)
            ema_bear = (prev_ema9 >= prev_ema26) and (curr_ema9 < curr_ema26)
            macd_bull = (prev_macd <= prev_sig) and (curr_macd > curr_sig)
            macd_bear = (prev_macd >= prev_sig) and (curr_macd < curr_sig)

            sig = None
            trig = None
            conf_delay = 0

            # 1. SAME_CANDLE confluence (delay = 0)
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
                # 2. Check existing pending setup
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
                        # Check second confirmation
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

                # 3. If still no active pending setup, start new setup
                if active_pending is None and sig is None:
                    if macd_bull and not ema_bull:
                        active_pending = {"direction": "LONG", "leading": "MACD", "elapsed": 0}
                    elif ema_bull and not macd_bull:
                        active_pending = {"direction": "LONG", "leading": "EMA", "elapsed": 0}
                    elif macd_bear and not ema_bear:
                        active_pending = {"direction": "SHORT", "leading": "MACD", "elapsed": 0}
                    # Short EMA-first is disallowed by V2-2 specification

            # Handle execution of signals
            if sig is not None:
                entry_idx = i + 1
                entry_time = times[entry_idx]
                entry_price = open_px[entry_idx] # Executed on the Open of the immediate next completed 1H bar

                # Controlled reversal / close previous position
                if active_trade is not None:
                    # Close previous trade on this new entry
                    active_trade["exit_idx"] = entry_idx
                    active_trade["exit_time"] = entry_time
                    active_trade["exit_price"] = entry_price
                    all_trades.append(active_trade)
                    active_trade = None

                # Calculate feature vector on confirming candle i
                candle_range = max(curr_high - curr_low, 1e-6)
                candle_body = abs(curr_close - curr_open)
                body_to_range = candle_body / candle_range
                close_location = (curr_close - curr_low) / candle_range
                candle_direction = 1 if curr_close > curr_open else (-1 if curr_close < curr_open else 0)
                candle_atr_norm = candle_range / max(curr_atr, 1e-6)
                body_atr_norm = candle_body / max(curr_atr, 1e-6)

                # Volume
                rel_volume = curr_vol / max(curr_vol_sma, 1e-6)
                vol_expansion = 1 if curr_vol > prev_vol else 0
                vol_ratio_prev = curr_vol / max(prev_vol, 1e-6)

                # EMA
                ema_diff = curr_ema9 - curr_ema26
                ema_separation = abs(curr_ema9 - curr_ema26)
                ema_sep_atr = ema_separation / max(curr_atr, 1e-6)
                prev_ema_sep = abs(prev_ema9 - prev_ema26)
                ema_expanding = 1 if ema_separation > prev_ema_sep else 0

                # MACD
                macd_diff = curr_macd - curr_sig
                macd_crossover_strength = abs(curr_macd - prev_macd) / max(curr_atr, 1e-6)
                hist_value = curr_hist
                hist_expanding = 1 if abs(curr_hist) > abs(prev_hist) else 0

                # Volatility
                atr_pct = (curr_atr / curr_close) * 100.0

                # Composite Setup Strength Score (0 to 4)
                score = 0
                # Component 1: Strong candle in direction of trade
                if sig == "BUY" and close_location >= 0.65 and body_to_range >= 0.50:
                    score += 1
                elif sig == "SELL" and close_location <= 0.35 and body_to_range >= 0.50:
                    score += 1
                # Component 2: Volume expansion & above average
                if rel_volume >= 1.10 and vol_expansion == 1:
                    score += 1
                # Component 3: EMA separation expanding
                if ema_expanding == 1:
                    score += 1
                # Component 4: MACD histogram expanding
                if hist_expanding == 1:
                    score += 1

                trade_dir = "LONG" if sig == "BUY" else "SHORT"
                current_pos = 1 if trade_dir == "LONG" else -1

                active_trade = {
                    "symbol": sym,
                    "sector": sector,
                    "direction": trade_dir,
                    "lot_size": lot_size,
                    "trigger_type": trig,
                    "confirmation_delay": conf_delay,
                    "signal_time": times[i],
                    "signal_price": curr_close,
                    "entry_idx": entry_idx,
                    "entry_time": entry_time,
                    "entry_price": entry_price,
                    "entry_atr": curr_atr,
                    "entry_atr_pct": atr_pct,
                    # Features
                    "f_body_to_range": body_to_range,
                    "f_close_location": close_location,
                    "f_candle_direction": candle_direction,
                    "f_candle_atr_norm": candle_atr_norm,
                    "f_body_atr_norm": body_atr_norm,
                    "f_rel_volume": rel_volume,
                    "f_vol_expansion": vol_expansion,
                    "f_vol_ratio_prev": vol_ratio_prev,
                    "f_ema_diff": ema_diff,
                    "f_ema_sep": ema_separation,
                    "f_ema_sep_atr": ema_sep_atr,
                    "f_ema_expanding": ema_expanding,
                    "f_macd_diff": macd_diff,
                    "f_macd_xover_str": macd_crossover_strength,
                    "f_hist_value": hist_value,
                    "f_hist_expanding": hist_expanding,
                    "f_atr_pct": atr_pct,
                    "f_strength_score": score,
                    "oi_status": "UNAVAILABLE",
                    "exit_idx": None,
                    "exit_time": None,
                    "exit_price": None,
                }

        # If trade still open at end of data, close at last available close
        if active_trade is not None:
            active_trade["exit_idx"] = n - 1
            active_trade["exit_time"] = times[-1]
            active_trade["exit_price"] = close[-1]
            all_trades.append(active_trade)

    # Attach forward candle slices and compute baseline path metrics
    reconstructed_trades = []
    feature_rows = []

    for trade_id, t in enumerate(all_trades, 1):
        sym = t["symbol"]
        df = data_map[sym]
        e_idx = t["entry_idx"]
        x_idx = t["exit_idx"]

        # Ensure valid range
        if x_idx <= e_idx:
            continue

        slice_df = df.iloc[e_idx : x_idx + 1].copy()
        t["slice_df"] = slice_df
        t["trade_id"] = trade_id

        entry_px = t["entry_price"]
        exit_px = t["exit_price"]
        dir_mult = 1.0 if t["direction"] == "LONG" else -1.0

        # Baseline PnL
        raw_pnl_pct = ((exit_px - entry_px) / entry_px) * 100.0 * dir_mult
        bars_held = len(slice_df)

        # Highs and Lows across holding period
        highs = slice_df["High"].values
        lows = slice_df["Low"].values

        if t["direction"] == "LONG":
            peak_px = float(np.max(highs))
            trough_px = float(np.min(lows))
            mfe_pct = ((peak_px - entry_px) / entry_px) * 100.0
            mae_pct = ((entry_px - trough_px) / entry_px) * 100.0
        else: # SHORT
            peak_px = float(np.min(lows))
            trough_px = float(np.max(highs))
            mfe_pct = ((entry_px - peak_px) / entry_px) * 100.0
            mae_pct = ((trough_px - entry_px) / entry_px) * 100.0

        mfe_pct = max(0.0, mfe_pct)
        mae_pct = max(0.0, mae_pct)

        mfe_atr = mfe_pct / max(t["entry_atr_pct"], 1e-4)
        mae_atr = mae_pct / max(t["entry_atr_pct"], 1e-4)

        # In-sample vs Out-of-sample partition
        # IS: 2023-09-29 to 2025-06-30 (21 months)
        # OOS: 2025-07-01 to 2026-09-09 (14.5 months)
        entry_ts = pd.to_datetime(t["entry_time"])
        is_split_date = pd.to_datetime("2025-07-01", utc=True)
        # localize / convert tz
        if entry_ts.tzinfo is not None:
            is_split_date = is_split_date.tz_convert(entry_ts.tz)
        else:
            entry_ts = entry_ts.tz_localize("UTC")
            
        sample = "IS" if entry_ts < is_split_date else "OOS"
        t["sample"] = sample
        t["baseline_pnl_pct"] = raw_pnl_pct
        t["bars_held"] = bars_held
        t["mfe_pct"] = mfe_pct
        t["mae_pct"] = mae_pct
        t["mfe_atr"] = mfe_atr
        t["mae_atr"] = mae_atr

        reconstructed_trades.append(t)

        # Create row for tabular analysis (exclude slice_df)
        row = {k: v for k, v in t.items() if k != "slice_df"}
        feature_rows.append(row)

    feat_df = pd.DataFrame(feature_rows)
    print(f"Total V2-2 Trades Reconstructed: {len(reconstructed_trades)}")
    print(f"  - In-Sample (IS): {sum(1 for t in reconstructed_trades if t['sample'] == 'IS')}")
    print(f"  - Out-of-Sample (OOS): {sum(1 for t in reconstructed_trades if t['sample'] == 'OOS')}")
    print(f"  - Long Trades: {sum(1 for t in reconstructed_trades if t['direction'] == 'LONG')}")
    print(f"  - Short Trades: {sum(1 for t in reconstructed_trades if t['direction'] == 'SHORT')}")
    
    return reconstructed_trades, feat_df

if __name__ == "__main__":
    data = load_or_download_all_data()
    trades, df = extract_trades_and_features(data)
    out_csv = Path(__file__).resolve().parent / "v2_trades_with_features.csv"
    df.to_csv(out_csv, index=False)
    print(f"Saved trades with features to {out_csv}")
