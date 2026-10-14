"""
Equity Curve & Drawdown Tracking Engine
----------------------------------------
Tracks bar-by-bar equity snapshots, High Water Marks, and Drawdown series.
"""

from typing import Any, Dict, List

import numpy as np
import pandas as pd


class EquityCurveTracker:
    """
    Phase 1: Equity Curve & Drawdown Curve Tracker.
    Calculates bar-by-bar portfolio value, peak water marks, and drawdown series ($ and %).
    """

    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.snapshots: list[dict[str, Any]] = []

    def record_bar(self, date: Any, portfolio_value: float, cash: float, position_value: float):
        self.snapshots.append(
            {
                "date": date,
                "portfolio_value": portfolio_value,
                "cash": cash,
                "position_value": position_value,
            }
        )

    def get_equity_dataframe(self) -> pd.DataFrame:
        if not self.snapshots:
            return pd.DataFrame()
        df = pd.DataFrame(self.snapshots)
        # Institutional HWM: High Water Mark starts at max(initial_capital, cumulative peak)
        df["cum_max"] = np.maximum(self.initial_capital, df["portfolio_value"].cummax())
        df["drawdown_val"] = df["portfolio_value"] - df["cum_max"]
        df["drawdown_pct"] = np.where(
            df["cum_max"] > 0, (df["drawdown_val"] / df["cum_max"]) * 100.0, 0.0
        )
        df["returns_pct"] = df["portfolio_value"].pct_change().fillna(0.0)
        return df

    def get_max_drawdown_pct(self) -> float:
        df = self.get_equity_dataframe()
        if df.empty:
            return 0.0
        return float(df["drawdown_pct"].min())
