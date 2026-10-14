#!/usr/bin/env python3
"""
================================================================================
AGY Futures OI Auto-Research System — Feature Engineering Engine
================================================================================
Constructs production-grade, vectorized quantitative features combining:
  PRICE ACTION + VOLUME + OPEN INTEREST + SEQUENCES + CANDLE STRUCTURE
================================================================================
"""

import os
import pandas as pd
import numpy as np

FEATURES_DIR = "research/oi/features"
NORMALIZED_DIR = "research/oi/normalized"


def compute_all_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate comprehensive feature matrix from normalized continuous futures data.
    Input must contain: trade_date, open, high, low, close, total_futures_vol, total_futures_oi.
    """
    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values("trade_date").reset_index(drop=True)

    # -------------------------------------------------------------------------
    # 1. Price Action & Return Features
    # -------------------------------------------------------------------------
    df["ret_1d"] = df["close"].pct_change(1) * 100.0
    df["ret_2d"] = df["close"].pct_change(2) * 100.0
    df["ret_3d"] = df["close"].pct_change(3) * 100.0
    df["ret_5d"] = df["close"].pct_change(5) * 100.0

    # Forward returns (target variables for evaluation)
    # Next day Open to Open return (strictly executable)
    df["fwd_ret_open_to_open_1d"] = (df["open"].shift(-2) / df["open"].shift(-1) - 1.0) * 100.0
    # Next day Open to Close return
    df["fwd_ret_open_to_close_1d"] = (df["close"].shift(-1) / df["open"].shift(-1) - 1.0) * 100.0
    # 5-day forward return from next open
    df["fwd_ret_open_5d"] = (df["close"].shift(-5) / df["open"].shift(-1) - 1.0) * 100.0

    # Moving Averages
    df["sma10"] = df["close"].rolling(10).mean()
    df["sma20"] = df["close"].rolling(20).mean()
    df["sma50"] = df["close"].rolling(50).mean()
    df["dist_sma20_pct"] = ((df["close"] / df["sma20"]) - 1.0) * 100.0
    df["trend_regime"] = np.where(df["close"] > df["sma20"], 1, -1)  # 1 = Bull, -1 = Bear

    # 10-day Price Extremes
    df["high10"] = df["high"].rolling(10).max().shift(1)
    df["low10"] = df["low"].rolling(10).min().shift(1)
    df["dist_high10_pct"] = ((df["close"] / df["high10"]) - 1.0) * 100.0
    df["dist_low10_pct"] = ((df["close"] / df["low10"]) - 1.0) * 100.0

    # -------------------------------------------------------------------------
    # 2. Candle Structure & Volatility Features
    # -------------------------------------------------------------------------
    # True Range & ATR(14)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift(1)).abs()
    tr3 = (df["low"] - df["close"].shift(1)).abs()
    df["tr"] = np.maximum(tr1, np.maximum(tr2, tr3))
    df["atr14"] = df["tr"].rolling(14).mean()
    df["atr_pct"] = (df["atr14"] / df["close"]) * 100.0
    df["volatility_ratio"] = df["tr"] / df["atr14"]

    # Candle Body, Upper Wick, Lower Wick ratios
    candle_range = np.maximum(df["high"] - df["low"], 1e-6)
    body = (df["close"] - df["open"]).abs()
    df["body_range_ratio"] = body / candle_range
    df["is_green_candle"] = df["close"] >= df["open"]

    upper_wick = df["high"] - np.maximum(df["close"], df["open"])
    lower_wick = np.minimum(df["close"], df["open"]) - df["low"]
    df["upper_wick_ratio"] = upper_wick / candle_range
    df["lower_wick_ratio"] = lower_wick / candle_range

    # -------------------------------------------------------------------------
    # 3. Volume Dynamics
    # -------------------------------------------------------------------------
    df["vol_sma5"] = df["total_futures_vol"].rolling(5).mean()
    df["vol_sma20"] = df["total_futures_vol"].rolling(20).mean()
    df["vol_rel_ratio"] = df["total_futures_vol"] / df["vol_sma20"]
    df["vol_chg_pct"] = df["total_futures_vol"].pct_change(1) * 100.0

    # -------------------------------------------------------------------------
    # 4. Open Interest Dynamics (Total Futures OI)
    # -------------------------------------------------------------------------
    df["oi_chg"] = df["total_futures_oi"].diff(1)
    df["oi_chg_pct"] = df["total_futures_oi"].pct_change(1) * 100.0
    df["oi_chg_5d_pct"] = df["total_futures_oi"].pct_change(5) * 100.0
    df["oi_sma10"] = df["total_futures_oi"].rolling(10).mean()
    df["oi_momentum_ratio"] = df["total_futures_oi"] / df["oi_sma10"]
    # OI Acceleration: change of OI change
    df["oi_accel"] = df["oi_chg_pct"].diff(1)

    # -------------------------------------------------------------------------
    # 5. Descriptive Price + OI States (Rule 11)
    # -------------------------------------------------------------------------
    conds = [
        (df["ret_1d"] > 0) & (df["oi_chg_pct"] > 0),
        (df["ret_1d"] < 0) & (df["oi_chg_pct"] > 0),
        (df["ret_1d"] > 0) & (df["oi_chg_pct"] < 0),
        (df["ret_1d"] < 0) & (df["oi_chg_pct"] < 0),
    ]
    states = ["LONG_BUILDUP", "SHORT_BUILDUP", "SHORT_COVERING", "LONG_UNWINDING"]
    df["oi_state"] = np.select(conds, states, default="NEUTRAL")

    # Sequence Persistence
    state_s = df["oi_state"]
    persist = []
    c = 1
    for i in range(len(state_s)):
        if i == 0:
            persist.append(1)
        elif state_s.iloc[i] == state_s.iloc[i-1]:
            c += 1
            persist.append(c)
        else:
            c = 1
            persist.append(1)
    df["state_persistence"] = persist

    return df


def generate_feature_store(symbols: list = ["NIFTY", "BANKNIFTY"]):
    """Build and persist feature matrices for given symbols."""
    os.makedirs(FEATURES_DIR, exist_ok=True)
    for sym in symbols:
        raw_p = os.path.join(NORMALIZED_DIR, f"{sym}_continuous.parquet")
        if not os.path.exists(raw_p):
            print(f"[!] Normalized data for {sym} not found. Skipping.")
            continue
        raw_df = pd.read_parquet(raw_p)
        featured_df = compute_all_features(raw_df)
        out_p = os.path.join(FEATURES_DIR, f"{sym}_features.parquet")
        featured_df.to_parquet(out_p, index=False)
        print(f"[+] Feature matrix created for {sym}: {len(featured_df)} rows, {len(featured_df.columns)} features -> {out_p}")


if __name__ == "__main__":
    generate_feature_store()
