"""
Walk Forward Analysis & Out-of-Sample Validation Engine
-------------------------------------------------------
Splits market datasets into In-Sample (IS) and Out-of-Sample (OOS) testing windows.
"""

from collections.abc import Callable
from typing import Any, Dict

import pandas as pd

from ..analytics.portfolio_analytics import PortfolioAnalytics
from ..analytics.trade_analytics import TradeAnalytics


class WalkForwardAnalyzer:
    """
    Phase 7: Walk-Forward Analysis & Out-of-Sample (OOS) Testing Engine.
    Evaluates strategy robustness across rolling training (In-Sample) and testing (Out-of-Sample) windows.
    """

    @staticmethod
    def run_out_of_sample_test(
        symbol: str,
        yf_ticker: str,
        candle_data: pd.DataFrame,
        backtest_runner_fn: Callable,
        in_sample_pct: float = 0.7,
        warmup_bars: int = 200,
    ) -> dict[str, Any]:
        n = len(candle_data)
        split_idx = int(n * in_sample_pct)

        is_data = candle_data.iloc[:split_idx]

        # Out-of-Sample window includes warmup_bars from In-Sample for continuous indicator calculation
        oos_start_idx = max(0, split_idx - warmup_bars)
        oos_data = candle_data.iloc[oos_start_idx:]

        is_tester = backtest_runner_fn(symbol, yf_ticker, {}, is_data)
        is_metrics = TradeAnalytics.calculate_metrics(is_tester.trade_manager)
        is_adv = PortfolioAnalytics.calculate_advanced_metrics(
            is_tester.equity_tracker, is_tester.trade_manager
        )

        oos_tester = backtest_runner_fn(symbol, yf_ticker, {}, oos_data)
        oos_metrics = TradeAnalytics.calculate_metrics(oos_tester.trade_manager)
        oos_adv = PortfolioAnalytics.calculate_advanced_metrics(
            oos_tester.equity_tracker, oos_tester.trade_manager
        )

        return {
            "is_metrics": is_metrics,
            "is_adv_metrics": is_adv,
            "oos_metrics": oos_metrics,
            "oos_adv_metrics": oos_adv,
            "is_bars": len(is_data),
            "oos_bars": len(candle_data) - split_idx,
        }
