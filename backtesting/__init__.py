"""
OpenAlgo Research-Grade Backtesting Engine Framework
---------------------------------------------------
Modular framework providing trade logging, equity tracking, performance analytics,
position sizing, advanced risk management, and parameter optimization.
"""

from .analytics import (
    AdvancedPortfolioMetrics,
    DetailedConsoleReporter,
    PerformanceMetrics,
    PortfolioAnalytics,
    TradeAnalytics,
)
from .models import Trade, TradeLogManager
from .optimization import OptimizationResult, ParameterOptimizer, WalkForwardAnalyzer
from .portfolio import (
    ATRSizer,
    EquityCurveTracker,
    FixedCapitalSizer,
    FixedQuantitySizer,
    PercentEquitySizer,
    PositionSizer,
)
from .risk import RiskManagementConfig

__all__ = [
    "Trade",
    "TradeLogManager",
    "EquityCurveTracker",
    "PositionSizer",
    "FixedQuantitySizer",
    "FixedCapitalSizer",
    "PercentEquitySizer",
    "ATRSizer",
    "TradeAnalytics",
    "PerformanceMetrics",
    "PortfolioAnalytics",
    "AdvancedPortfolioMetrics",
    "DetailedConsoleReporter",
    "RiskManagementConfig",
    "OptimizationResult",
    "ParameterOptimizer",
    "WalkForwardAnalyzer",
]
