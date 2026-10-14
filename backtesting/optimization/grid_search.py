"""
Grid Search Parameter Optimization Engine
------------------------------------------
Systematically evaluates strategy performance over parameter grids.
"""

import itertools
from collections.abc import Callable
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from ..analytics.portfolio_analytics import AdvancedPortfolioMetrics, PortfolioAnalytics
from ..analytics.trade_analytics import PerformanceMetrics, TradeAnalytics


class OptimizationResult:
    """Container for Grid Search Parameter Optimization Runs."""

    def __init__(
        self,
        params: dict[str, Any],
        metrics: PerformanceMetrics,
        adv_metrics: AdvancedPortfolioMetrics,
    ):
        self.params = params
        self.metrics = metrics
        self.adv_metrics = adv_metrics


class ParameterOptimizer:
    """
    Phase 7: Grid Search & Parameter Optimization Engine.
    Executes systematic search over strategy parameter combinations and ranks results.
    """

    @staticmethod
    def grid_search(
        symbol: str,
        yf_ticker: str,
        candle_data: pd.DataFrame,
        param_grid: dict[str, list[Any]],
        backtest_runner_fn: Callable,
        rank_by: str = "sharpe_ratio",
    ) -> list[OptimizationResult]:
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(itertools.product(*values))

        results = []
        for combo in combinations:
            params = dict(zip(keys, combo, strict=False))
            # Validate parameter logic (e.g. fast < slow)
            if "fast" in params and "slow" in params and params["fast"] >= params["slow"]:
                continue

            tester = backtest_runner_fn(symbol, yf_ticker, params, candle_data)
            if tester is None or len(tester.trade_manager) == 0:
                continue

            metrics = TradeAnalytics.calculate_metrics(tester.trade_manager)
            adv_metrics = PortfolioAnalytics.calculate_advanced_metrics(
                tester.equity_tracker, tester.trade_manager
            )

            results.append(OptimizationResult(params, metrics, adv_metrics))

        def get_score(res: OptimizationResult):
            val = None
            if hasattr(res.adv_metrics, rank_by):
                val = getattr(res.adv_metrics, rank_by)
            elif hasattr(res.metrics, rank_by):
                val = getattr(res.metrics, rank_by)
            else:
                val = res.metrics.win_rate

            if val is None or np.isnan(val):
                return -999999.0
            return float(val)

        results.sort(key=get_score, reverse=True)
        return results
