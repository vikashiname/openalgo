#!/usr/bin/env python
"""
Debug script for Nifty strategy
"""

import numpy as np
import pandas as pd
from ta.momentum import StochRSIIndicator
from ta.trend import MACD, IchimokuIndicator

# Create sample data
dates = pd.date_range(start="2022-01-01", periods=200, freq="D")
np.random.seed(42)
price = 18000 + np.cumsum(np.random.randn(200) * 30)
df = pd.DataFrame(
    {
        "Close": price,
        "High": price + np.random.rand(200) * 50,
        "Low": price - np.random.rand(200) * 50,
    },
    index=dates,
)

print("Data shape:", df.shape)
print("Price range:", df["Close"].min(), "to", df["Close"].max())

# Calculate indicators
macd = MACD(df["Close"])
df["macd"] = macd.macd()
df["macd_signal"] = macd.macd_signal()
df["macd_hist"] = macd.macd_diff()

stoch = StochRSIIndicator(df["Close"])
df["stoch_k"] = stoch.stochrsi_k()
df["stoch_d"] = stoch.stochrsi_d()

ichi = IchimokuIndicator(df["High"], df["Low"])
df["tenkan"] = ichi.ichimoku_conversion_line()
df["kijun"] = ichi.ichimoku_base_line()
df["senkou_a"] = ichi.ichimoku_a()

df["recent_high"] = df["High"].rolling(20).max()
df["recent_low"] = df["Low"].rolling(20).min()

print("NaN values after indicators:", df.isna().sum().sum())

# Calculate conditions
macd_cross_up = (df["macd"] > df["macd_signal"]) & (
    df["macd"].shift(1) <= df["macd_signal"].shift(1)
)
macd_cross_down = (df["macd"] < df["macd_signal"]) & (
    df["macd"].shift(1) >= df["macd_signal"].shift(1)
)
hist_expansion = df["macd_hist"] > df["macd_hist"].shift(1)
hist_strength = df["macd_hist"] > df["macd_hist"].rolling(10).mean()
low_momentum = abs(df["macd_hist"]) < df["macd_hist"].rolling(20).std()

print("MACD cross up signals:", macd_cross_up.sum())
print("MACD cross down signals:", macd_cross_down.sum())

long_cond = (
    (df["Close"] > df["senkou_a"])
    & (df["tenkan"] > df["kijun"])
    & macd_cross_up
    & hist_expansion
    & hist_strength
    & (df["stoch_k"] > df["stoch_d"])
    & (df["Close"] > df["recent_high"].shift(1))
    & (~low_momentum)
)

short_cond = (
    (df["Close"] < df["senkou_a"])
    & (df["tenkan"] < df["kijun"])
    & macd_cross_down
    & (df["macd_hist"] < df["macd_hist"].shift(1))
    & (df["macd_hist"] < df["macd_hist"].rolling(10).mean())
    & (df["stoch_k"] < df["stoch_d"])
    & (df["Close"] < df["recent_low"].shift(1))
    & (~low_momentum)
)

print("Long conditions met:", long_cond.sum())
print("Short conditions met:", short_cond.sum())

# Check individual conditions
print("\nChecking individual conditions for long:")
print("Close > senkou_a:", (df["Close"] > df["senkou_a"]).sum())
print("tenkan > kijun:", (df["tenkan"] > df["kijun"]).sum())
print("stoch_k > stoch_d:", (df["stoch_k"] > df["stoch_d"]).sum())
print("Close > recent_high.shift(1):", (df["Close"] > df["recent_high"].shift(1)).sum())
print("~low_momentum:", (~low_momentum).sum())
