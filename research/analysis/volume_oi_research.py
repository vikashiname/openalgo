"""
================================================================================
Phase 9: Volume & Open Interest (OI) Filter Research
================================================================================
Investigates Volume and OI dynamics independently to evaluate whether volume
confirmation filters improve strategy Expectancy, Sharpe, and Drawdown.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import ContractSpec
from ..strategies.ema_crossover import EMACrossoverStrategy


class VolumeAnalyzer:
    def __init__(self, spec: ContractSpec, initial_capital: float = 100_000.0):
        self.spec = spec
        self.initial_capital = initial_capital

    @staticmethod
    def compute_volume_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute volume moving average, Relative Volume (RVOL), and price-volume quadrants.
        """
        df = df.copy()
        vol = df["volume"]
        close = df["close"]
        vol_sma20 = vol.rolling(20).mean()
        rvol = vol / (vol_sma20 + 1.0)

        price_change = close - close.shift(1)
        vol_change = vol - vol.shift(1)

        # 4 Price-Volume Interaction Quadrants
        quadrant = []
        for i in range(len(df)):
            p_chg = price_change.iloc[i]
            v_chg = vol_change.iloc[i]

            if p_chg > 0 and v_chg > 0:
                quadrant.append("Price_Up_Vol_Up")      # Strong Bullish
            elif p_chg > 0 and v_chg <= 0:
                quadrant.append("Price_Up_Vol_Down")    # Weak Bullish (Divergence)
            elif p_chg <= 0 and v_chg > 0:
                quadrant.append("Price_Down_Vol_Up")    # Strong Bearish
            else:
                quadrant.append("Price_Down_Vol_Down")  # Weak Bearish

        df["vol_sma20"] = vol_sma20
        df["rvol"] = rvol
        df["pv_quadrant"] = quadrant
        return df

    def test_volume_filters(
        self,
        df: pd.DataFrame,
        fast_period: int = 9,
        slow_period: int = 21
    ) -> pd.DataFrame:
        """
        Test multiple volume filter variations alongside base EMA crossover:
          1. Baseline (No Filter)
          2. Volume > 20-day SMA Volume
          3. RVOL > 1.2 (Relative Volume Surge)
          4. RVOL > 1.5 (High Volume Breakout)
          5. Price Up + Volume Up Confirmation Only
        """
        df_vol = self.compute_volume_indicators(df)
        base_strat = EMACrossoverStrategy(fast_period=fast_period, slow_period=slow_period)
        buy_base, sell_base = base_strat.generate_signals(df_vol)

        engine = BacktestEngine(self.spec, self.initial_capital, execution_timing="next_open")

        filter_configs = [
            ("1. Baseline (No Filter)", buy_base, sell_base),
            ("2. Vol > 20-SMA Volume", buy_base & (df_vol["volume"] > df_vol["vol_sma20"]), sell_base),
            ("3. RVOL > 1.2 Surge", buy_base & (df_vol["rvol"] > 1.2), sell_base),
            ("4. RVOL > 1.5 Breakout", buy_base & (df_vol["rvol"] > 1.5), sell_base),
            ("5. Price_Up + Vol_Up Confirmed", buy_base & (df_vol["pv_quadrant"] == "Price_Up_Vol_Up"), sell_base),
        ]

        results = []
        for name, buy_sig, sell_sig in filter_configs:
            def sig_gen(d, b=buy_sig, s=sell_sig):
                return b, s

            res = engine.run(df_vol, sig_gen)
            m = res["metrics"]
            results.append({
                "filter_name": name,
                "total_return_pct": m["total_return_pct"],
                "cagr_pct": m["cagr_pct"],
                "max_drawdown_pct": m["max_drawdown_pct"],
                "sharpe_ratio": m["sharpe_ratio"],
                "profit_factor": m["profit_factor"],
                "win_rate_pct": m["win_rate_pct"],
                "trades_count": m["total_trades"],
                "expectancy_dollars": m["expectancy_dollars"],
            })

        return pd.DataFrame(results)
