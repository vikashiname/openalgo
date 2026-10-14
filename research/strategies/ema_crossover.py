"""
================================================================================
EMA Crossover Strategy Generator
================================================================================
Generates clean, deterministic entry/exit crossover signals.
"""

from typing import Tuple
import pandas as pd


class EMACrossoverStrategy:
    def __init__(self, fast_period: int = 9, slow_period: int = 21):
        if fast_period >= slow_period:
            raise ValueError(f"Fast EMA ({fast_period}) must be strictly less than Slow EMA ({slow_period}).")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def generate_signals(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        Calculates EMA 9 and EMA 21 on closed prices.
        Returns: (buy_signals, sell_signals) as Boolean pd.Series
        """
        close = df["close"]
        ema_fast = close.ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow_period, adjust=False).mean()

        # Bullish Crossover: Fast crosses strictly ABOVE Slow
        buy_raw = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
        # Bearish Crossover: Fast crosses strictly BELOW Slow
        sell_raw = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))

        # Fill NaNs with False
        buy_signals = buy_raw.fillna(False)
        sell_signals = sell_raw.fillna(False)

        return buy_signals, sell_signals
