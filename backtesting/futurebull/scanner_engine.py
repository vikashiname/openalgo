"""
================================================================================
FUTURES BULLISH BREAKOUT SCANNER — CORE VECTORIZED INDICATOR & FILTER ENGINE
================================================================================
Directory   : backtesting/futurebull/
Role        : Precise, vectorized computation of all 29 scanner conditions,
              forward excursion analytics, and group combination logic.
================================================================================
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional


def compute_psar(high: pd.Series, low: pd.Series, close: pd.Series, af_start: float = 0.02, af_step: float = 0.02, af_max: float = 0.2) -> pd.Series:
    """Computes Parabolic SAR vectorized / iterative state."""
    length = len(close)
    psar = pd.Series(index=close.index, dtype=float)
    if length < 2:
        return psar

    bull = True
    af = af_start
    ep = high.iloc[0]
    psar.iloc[0] = low.iloc[0]

    for i in range(1, length):
        prev_psar = psar.iloc[i - 1]
        if bull:
            current_psar = prev_psar + af * (ep - prev_psar)
            current_psar = min(current_psar, low.iloc[i - 1], low.iloc[max(0, i - 2)])
            if low.iloc[i] < current_psar:
                bull = False
                current_psar = ep
                ep = low.iloc[i]
                af = af_start
            else:
                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af = min(af + af_step, af_max)
        else:
            current_psar = prev_psar + af * (ep - prev_psar)
            current_psar = max(current_psar, high.iloc[i - 1], high.iloc[max(0, i - 2)])
            if high.iloc[i] > current_psar:
                bull = True
                current_psar = ep
                ep = high.iloc[i]
                af = af_start
            else:
                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af = min(af + af_step, af_max)
        psar.iloc[i] = current_psar

    return psar


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def compute_stoch_rsi(rsi: pd.Series, period: int = 14) -> pd.Series:
    rsi_min = rsi.rolling(period).min()
    rsi_max = rsi.rolling(period).max()
    denom = (rsi_max - rsi_min).replace(0, np.nan)
    stoch = (rsi - rsi_min) / denom * 100.0
    return stoch.fillna(50.0)


def compute_cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10) -> pd.Series:
    tp = (high + low + close) / 3.0
    sma_tp = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
    return cci.fillna(0.0)


def compute_mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 10) -> pd.Series:
    tp = (high + low + close) / 3.0
    raw_mf = tp * volume
    pos_mf = pd.Series(0.0, index=close.index)
    neg_mf = pd.Series(0.0, index=close.index)

    diff = tp.diff()
    pos_mf[diff > 0] = raw_mf[diff > 0]
    neg_mf[diff < 0] = raw_mf[diff < 0]

    pos_mf_sum = pos_mf.rolling(period).sum()
    neg_mf_sum = neg_mf.rolling(period).sum()
    mfr = pos_mf_sum / neg_mf_sum.replace(0, np.nan)
    mfi = 100.0 - (100.0 / (1.0 + mfr))
    return mfi.fillna(50.0)


def compute_williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10) -> pd.Series:
    highest_h = high.rolling(period).max()
    lowest_l = low.rolling(period).min()
    denom = (highest_h - lowest_l).replace(0, np.nan)
    r = (highest_h - close) / denom * -100.0
    return r.fillna(-50.0)


def compute_ichimoku(high: pd.Series, low: pd.Series, conv_period: int = 3, base_period: int = 7, span_b_period: int = 14):
    tenkan = (high.rolling(conv_period).max() + low.rolling(conv_period).min()) / 2.0
    kijun = (high.rolling(base_period).max() + low.rolling(base_period).min()) / 2.0
    span_a = (tenkan + kijun) / 2.0
    span_b = (high.rolling(span_b_period).max() + low.rolling(span_b_period).min()) / 2.0
    cloud_bottom = np.minimum(span_a, span_b)
    return tenkan, kijun, span_a, span_b, cloud_bottom


def compute_adx_dm(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10):
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = np.maximum(tr1, np.maximum(tr2, tr3))

    tr_smooth = pd.Series(tr, index=close.index).ewm(alpha=1.0 / period, adjust=False).mean()
    plus_di = pd.Series(plus_dm, index=close.index).ewm(alpha=1.0 / period, adjust=False).mean() / tr_smooth.replace(0, np.nan) * 100.0
    minus_di = pd.Series(minus_dm, index=close.index).ewm(alpha=1.0 / period, adjust=False).mean() / tr_smooth.replace(0, np.nan) * 100.0
    return plus_di.fillna(0.0), minus_di.fillna(0.0)


def compute_aroon(high: pd.Series, low: pd.Series, period: int = 10):
    aroon_up = high.rolling(period + 1).apply(lambda x: float(np.argmax(x)) / period * 100.0, raw=True)
    aroon_down = low.rolling(period + 1).apply(lambda x: float(np.argmin(x)) / period * 100.0, raw=True)
    return aroon_up.fillna(0.0), aroon_down.fillna(0.0)


def compute_stochastics(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 5, d_period: int = 3):
    lowest_l = low.rolling(k_period).min()
    highest_h = high.rolling(k_period).max()
    fast_k = (close - lowest_l) / (highest_h - lowest_l).replace(0, np.nan) * 100.0
    fast_d = fast_k.rolling(d_period).mean()
    slow_k = fast_d
    slow_d = slow_k.rolling(d_period).mean()
    return fast_k.fillna(50.0), fast_d.fillna(50.0), slow_k.fillna(50.0), slow_d.fillna(50.0)


def compute_bollinger_bands(close: pd.Series, period: int = 20, num_std: float = 2.0):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower


def compute_macd_14_5_3(close: pd.Series):
    """
    Computes MACD(14, 5, 3).
    In Chartink / Indian platform syntax, Fast is 5, Slow is 14, Signal is 3.
    """
    ema_fast = close.ewm(span=5, adjust=False).mean()
    ema_slow = close.ewm(span=14, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=3, adjust=False).mean()
    macd_hist = macd_line - macd_signal
    return macd_line, macd_signal, macd_hist


FILTER_NAMES = {
    "A1_SMA_VOL_20": "Daily SMA(Volume, 20) >= 100,000",
    "A2_ICHI_CLOUD_BOT_3_7_14": "Close >= Ichimoku Cloud Bottom(3, 7, 14)",
    "B1_PSAR": "Close >= Parabolic SAR(0.02, 0.02, 0.2)",
    "B2_RSI10_GTE_20": "RSI(10) >= 20",
    "B3_EMA20_GT_20": "EMA(Close, 20) > 20 (Absolute Price Filter)",
    "B4_STOCHRSI10_GTE_20": "Stoch RSI(10) >= 20",
    "B5_CCI10_GTE_0": "CCI(10) >= 0",
    "B6_MFI10_GTE_20": "MFI(10) >= 20",
    "B7_WILLR10_GTE_M80": "Williams %R(10) >= -80",
    "B8_ICHI_CONV_GTE_BASE": "Ichimoku Conversion >= Base (3, 7, 14)",
    "B9_ICHI_SPANA_GTE_SPANB": "Ichimoku Span A >= Span B (3, 7, 14)",
    "B10_CLOSE_GTE_EMA14": "Close >= EMA(Close, 14)",
    "B11_ADX_DIP_GTE_DIM": "ADX +DI(10) >= -DI(10)",
    "B12_AROON_UP_GTE_DOWN": "Aroon Up(10) >= Aroon Down(10)",
    "B13_SLOW_STOCH_K_GTE_D": "Slow Stoch %K(5,3) >= %D(5,3)",
    "B14_FAST_STOCH_K_GTE_D": "Fast Stoch %K(5,3) >= %D(5,3)",
    "B15_CLOSE_GTE_SMA10": "Close >= SMA(Close, 10)",
    "C1_MACD_LINE_GTE_SIG": "MACD Line(14,5,3) >= MACD Signal",
    "C2_MACD_HIST_GTE_0": "MACD Histogram(14,5,3) >= 0",
    "D1_RSI14_GT_50": "RSI(14) > 50",
    "D2_STOCHRSI14_GT_50": "Stoch RSI(14) > 50",
    "D3_RSI10_LT_80": "RSI(10) < 80",
    "D4_CLOSE_GTE_UPPER_BB": "Close >= Upper Bollinger Band(20, 2)",
    "D5_ICHI_CLOUD_BOT_9_26_52": "Close >= Ichimoku Cloud Bottom(9, 26, 52)",
    "D6_CLOSE_GT_OPEN": "Close > Open (Green Candle)",
    "D7_VOL_GT_100K": "Volume > 100,000",
    "D8_EMA5_GT_EMA20": "EMA(Close, 5) > EMA(Close, 20)",
    "D9_EMA20_GT_EMA50": "EMA(Close, 20) > EMA(Close, 50)",
    "D10_CLOSE_GT_EMA50": "Close > EMA(Close, 50)",
}


def compute_all_filters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes all 29 individual boolean filter columns and group combinations.
    Input df must have: open, high, low, close, volume.
    """
    res = df.copy()
    c = res["close"]
    h = res["high"]
    l = res["low"]
    o = res["open"]
    v = res["volume"]

    # --- Precalculate Indicator Series ---
    sma_vol_20 = v.rolling(20).mean()
    t_3, k_7, sa_14, sb_14, cloud_bot_3_7_14 = compute_ichimoku(h, l, 3, 7, 14)
    psar = compute_psar(h, l, c)
    rsi_10 = compute_rsi(c, 10)
    ema_20 = c.ewm(span=20, adjust=False).mean()
    stoch_rsi_10 = compute_stoch_rsi(rsi_10, 10)
    cci_10 = compute_cci(h, l, c, 10)
    mfi_10 = compute_mfi(h, l, c, v, 10)
    will_r_10 = compute_williams_r(h, l, c, 10)
    ema_14 = c.ewm(span=14, adjust=False).mean()
    plus_di_10, minus_di_10 = compute_adx_dm(h, l, c, 10)
    aroon_up_10, aroon_dn_10 = compute_aroon(h, l, 10)
    fast_k, fast_d, slow_k, slow_d = compute_stochastics(h, l, c, 5, 3)
    sma_10 = c.rolling(10).mean()
    macd_line, macd_sig, macd_hist = compute_macd_14_5_3(c)
    rsi_14 = compute_rsi(c, 14)
    stoch_rsi_14 = compute_stoch_rsi(rsi_14, 14)
    bb_mid, bb_upper, bb_lower = compute_bollinger_bands(c, 20, 2.0)
    t_9, k_26, sa_52, sb_52, cloud_bot_9_26_52 = compute_ichimoku(h, l, 9, 26, 52)
    ema_5 = c.ewm(span=5, adjust=False).mean()
    ema_50 = c.ewm(span=50, adjust=False).mean()

    # --- Group A: Liquidity & Initial Trend ---
    res["A1_SMA_VOL_20"] = (sma_vol_20 >= 100000).fillna(False)
    res["A2_ICHI_CLOUD_BOT_3_7_14"] = (c >= cloud_bot_3_7_14).fillna(False)

    # --- Group B: Bullish Trend Confirmation ---
    res["B1_PSAR"] = (c >= psar).fillna(False)
    res["B2_RSI10_GTE_20"] = (rsi_10 >= 20.0).fillna(False)
    res["B3_EMA20_GT_20"] = (ema_20 > 20.0).fillna(False)
    res["B4_STOCHRSI10_GTE_20"] = (stoch_rsi_10 >= 20.0).fillna(False)
    res["B5_CCI10_GTE_0"] = (cci_10 >= 0.0).fillna(False)
    res["B6_MFI10_GTE_20"] = (mfi_10 >= 20.0).fillna(False)
    res["B7_WILLR10_GTE_M80"] = (will_r_10 >= -80.0).fillna(False)
    res["B8_ICHI_CONV_GTE_BASE"] = (t_3 >= k_7).fillna(False)
    res["B9_ICHI_SPANA_GTE_SPANB"] = (sa_14 >= sb_14).fillna(False)
    res["B10_CLOSE_GTE_EMA14"] = (c >= ema_14).fillna(False)
    res["B11_ADX_DIP_GTE_DIM"] = (plus_di_10 >= minus_di_10).fillna(False)
    res["B12_AROON_UP_GTE_DOWN"] = (aroon_up_10 >= aroon_dn_10).fillna(False)
    res["B13_SLOW_STOCH_K_GTE_D"] = (slow_k >= slow_d).fillna(False)
    res["B14_FAST_STOCH_K_GTE_D"] = (fast_k >= fast_d).fillna(False)
    res["B15_CLOSE_GTE_SMA10"] = (c >= sma_10).fillna(False)

    # --- Group C: MACD Confirmation ---
    res["C1_MACD_LINE_GTE_SIG"] = (macd_line >= macd_sig).fillna(False)
    res["C2_MACD_HIST_GTE_0"] = (macd_hist >= 0.0).fillna(False)

    # --- Group D: Momentum & Breakout Confirmation ---
    res["D1_RSI14_GT_50"] = (rsi_14 > 50.0).fillna(False)
    res["D2_STOCHRSI14_GT_50"] = (stoch_rsi_14 > 50.0).fillna(False)
    res["D3_RSI10_LT_80"] = (rsi_10 < 80.0).fillna(False)
    res["D4_CLOSE_GTE_UPPER_BB"] = (c >= bb_upper).fillna(False)
    res["D5_ICHI_CLOUD_BOT_9_26_52"] = (c >= cloud_bot_9_26_52).fillna(False)
    res["D6_CLOSE_GT_OPEN"] = (c > o).fillna(False)
    res["D7_VOL_GT_100K"] = (v > 100000).fillna(False)
    res["D8_EMA5_GT_EMA20"] = (ema_5 > ema_20).fillna(False)
    res["D9_EMA20_GT_EMA50"] = (ema_20 > ema_50).fillna(False)
    res["D10_CLOSE_GT_EMA50"] = (c > ema_50).fillna(False)

    # --- Group Aggregates ---
    group_a_cols = ["A1_SMA_VOL_20", "A2_ICHI_CLOUD_BOT_3_7_14"]
    group_b_cols = [
        "B1_PSAR", "B2_RSI10_GTE_20", "B3_EMA20_GT_20", "B4_STOCHRSI10_GTE_20", "B5_CCI10_GTE_0",
        "B6_MFI10_GTE_20", "B7_WILLR10_GTE_M80", "B8_ICHI_CONV_GTE_BASE", "B9_ICHI_SPANA_GTE_SPANB",
        "B10_CLOSE_GTE_EMA14", "B11_ADX_DIP_GTE_DIM", "B12_AROON_UP_GTE_DOWN", "B13_SLOW_STOCH_K_GTE_D",
        "B14_FAST_STOCH_K_GTE_D", "B15_CLOSE_GTE_SMA10"
    ]
    group_c_cols = ["C1_MACD_LINE_GTE_SIG", "C2_MACD_HIST_GTE_0"]
    group_d_cols = [
        "D1_RSI14_GT_50", "D2_STOCHRSI14_GT_50", "D3_RSI10_LT_80", "D4_CLOSE_GTE_UPPER_BB",
        "D5_ICHI_CLOUD_BOT_9_26_52", "D6_CLOSE_GT_OPEN", "D7_VOL_GT_100K", "D8_EMA5_GT_EMA20",
        "D9_EMA20_GT_EMA50", "D10_CLOSE_GT_EMA50"
    ]

    res["COMBO_A"] = res[group_a_cols].all(axis=1)
    res["COMBO_AB"] = res["COMBO_A"] & res[group_b_cols].all(axis=1)
    res["COMBO_ABC"] = res["COMBO_AB"] & res[group_c_cols].all(axis=1)
    res["COMBO_ABD"] = res["COMBO_AB"] & res[group_d_cols].all(axis=1)
    res["COMBO_ALL_ORIGINAL"] = res["COMBO_ABC"] & res[group_d_cols].all(axis=1)

    # --- OPTIMIZED BULLISH BREAKOUT SIGNAL ---
    res["SIG_BULL_OPTIMISED"] = (
        (sma_vol_20 >= 100000) &
        (v > 100000) &
        (c > o) &
        (c > ema_20) & (ema_20 > ema_50) & (c > ema_50) &
        (rsi_14 > 52.0) & (rsi_14 < 75.0) &
        (macd_hist >= 0.0) &
        (c < bb_upper)
    ).fillna(False)

    # --- OPTIMIZED BEARISH BREAKDOWN SIGNAL ---
    cloud_top_3_7_14 = np.maximum(sa_14, sb_14)
    res["SIG_BEAR_OPTIMISED"] = (
        (sma_vol_20 >= 100000) &
        (v > 100000) &
        (c < o) &                         # Red confirmation candle
        (c < ema_20) & (ema_20 < ema_50) & (c < ema_50) & # Bearish trend alignment
        (rsi_14 < 48.0) & (rsi_14 > 25.0) & # Downward momentum without deep oversold bounce risk
        (macd_hist <= 0.0) &              # Bearish MACD momentum
        (c > bb_lower) &                  # Not exhausted below lower BB
        (c <= cloud_top_3_7_14)           # Below Ichimoku resistance
    ).fillna(False)

    # Forward Returns (Next session open to forward close, avoiding lookahead)
    next_open = res["open"].shift(-1)
    # Long forward returns
    res["fwd_ret_1d"] = (res["close"].shift(-1) - next_open) / next_open * 100.0
    res["fwd_ret_3d"] = (res["close"].shift(-3) - next_open) / next_open * 100.0
    res["fwd_ret_5d"] = (res["close"].shift(-5) - next_open) / next_open * 100.0
    res["fwd_ret_10d"] = (res["close"].shift(-10) - next_open) / next_open * 100.0
    res["fwd_ret_20d"] = (res["close"].shift(-20) - next_open) / next_open * 100.0

    # Short forward returns (Profit when forward close is lower than next open)
    res["short_fwd_ret_1d"] = (next_open - res["close"].shift(-1)) / next_open * 100.0
    res["short_fwd_ret_3d"] = (next_open - res["close"].shift(-3)) / next_open * 100.0
    res["short_fwd_ret_5d"] = (next_open - res["close"].shift(-5)) / next_open * 100.0
    res["short_fwd_ret_10d"] = (next_open - res["close"].shift(-10)) / next_open * 100.0
    res["short_fwd_ret_20d"] = (next_open - res["close"].shift(-20)) / next_open * 100.0

    # Max Favorable / Adverse Excursion over 10 days
    fwd_high_10 = res["high"].iloc[::-1].rolling(10).max().iloc[::-1].shift(-1)
    fwd_low_10 = res["low"].iloc[::-1].rolling(10).min().iloc[::-1].shift(-1)
    res["mfe_10d_pct"] = (fwd_high_10 - next_open) / next_open * 100.0
    res["mae_10d_pct"] = (fwd_low_10 - next_open) / next_open * 100.0

    res["short_mfe_10d_pct"] = (next_open - fwd_low_10) / next_open * 100.0
    res["short_mae_10d_pct"] = (next_open - fwd_high_10) / next_open * 100.0

    return res
