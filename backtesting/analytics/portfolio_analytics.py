"""
Advanced Portfolio Risk-Adjusted Analytics Engine
-------------------------------------------------
Calculates CAGR, Sharpe, Sortino, Calmar, Volatility, Recovery Factor, Exposure, and Holding Period.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..models.trade import TradeLogManager
from ..portfolio.equity import EquityCurveTracker


@dataclass
class AdvancedPortfolioMetrics:
    """Phase 3 Advanced Risk-Adjusted Metrics Container."""

    cagr: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    annual_volatility: float = 0.0
    recovery_factor: float = 0.0
    exposure_pct: float = 0.0
    avg_holding_period: float = 0.0


class PortfolioAnalytics:
    """
    Phase 3: Portfolio & Risk-Adjusted Return Analytics.
    Calculates CAGR, Sharpe, Sortino, Calmar, Volatility, Recovery Factor, Exposure, and Holding Periods.
    """

    @staticmethod
    def calculate_advanced_metrics(
        equity_tracker: EquityCurveTracker,
        trade_manager: TradeLogManager,
        risk_free_rate: float = 0.05,
    ) -> AdvancedPortfolioMetrics:
        eq_df = equity_tracker.get_equity_dataframe()
        trades_df = trade_manager.to_dataframe()

        if eq_df.empty or len(eq_df) < 2:
            return AdvancedPortfolioMetrics()

        initial_val = equity_tracker.initial_capital
        ending_val = eq_df["portfolio_value"].iloc[-1]

        total_bars = len(eq_df)
        start_date = pd.to_datetime(eq_df["date"].iloc[0])
        end_date = pd.to_datetime(eq_df["date"].iloc[-1])
        days = max((end_date - start_date).days, 1)
        years = days / 365.25

        # Compound Annual Growth Rate (CAGR)
        if ending_val > 0 and initial_val > 0 and years > 0:
            cagr = ((ending_val / initial_val) ** (1.0 / years) - 1.0) * 100.0
        elif ending_val <= 0:
            cagr = -100.0
        else:
            cagr = 0.0

        # Daily Returns & Volatility
        daily_returns = eq_df["returns_pct"].fillna(0.0)
        std_ret = float(daily_returns.std())

        annual_volatility = (
            std_ret * np.sqrt(252) * 100.0 if (not np.isnan(std_ret) and std_ret > 0) else 0.0
        )

        # Sharpe Ratio (annualized excess return over daily risk-free rate)
        daily_rfr = (1.0 + risk_free_rate) ** (1.0 / 252.0) - 1.0
        excess_ret = daily_returns - daily_rfr
        mean_excess = float(excess_ret.mean())

        if not np.isnan(std_ret) and std_ret > 0:
            sharpe_ratio = (mean_excess / std_ret) * np.sqrt(252)
        else:
            sharpe_ratio = 0.0

        # Institutional Sortino Ratio (Downside Deviation over ALL observations N)
        # Downside Deviation = sqrt( sum( min(R_t - R_f, 0)^2 ) / N ) * sqrt(252)
        downside_diff = np.minimum(excess_ret, 0.0)
        downside_dev = float(np.sqrt(np.mean(downside_diff**2))) * np.sqrt(252)

        if not np.isnan(downside_dev) and downside_dev > 0:
            sortino_ratio = (mean_excess * np.sqrt(252)) / downside_dev
        else:
            sortino_ratio = 0.0

        # Calmar Ratio
        max_dd_pct = abs(equity_tracker.get_max_drawdown_pct())
        calmar_ratio = (cagr / max_dd_pct) if max_dd_pct > 0 else 0.0

        # Recovery Factor
        net_profit = ending_val - initial_val
        max_dd_val = abs(eq_df["drawdown_val"].min())
        recovery_factor = (net_profit / max_dd_val) if max_dd_val > 0 else 0.0

        # Market Exposure & Avg Holding Period
        active_bars = (
            len(eq_df[eq_df["position_value"] != 0]) if "position_value" in eq_df.columns else 0
        )
        if active_bars > 0 and total_bars > 0:
            exposure_pct = (active_bars / total_bars) * 100.0
        elif not trades_df.empty and "holding_period" in trades_df.columns:
            market_bars = trades_df["holding_period"].sum()
            exposure_pct = min((market_bars / total_bars) * 100.0, 100.0) if total_bars > 0 else 0.0
        else:
            exposure_pct = 0.0

        avg_holding_period = (
            float(trades_df["holding_period"].mean())
            if (not trades_df.empty and "holding_period" in trades_df.columns)
            else 0.0
        )

        return AdvancedPortfolioMetrics(
            cagr=cagr,
            sharpe_ratio=sharpe_ratio if not np.isnan(sharpe_ratio) else 0.0,
            sortino_ratio=sortino_ratio if not np.isnan(sortino_ratio) else 0.0,
            calmar_ratio=calmar_ratio if not np.isnan(calmar_ratio) else 0.0,
            annual_volatility=annual_volatility,
            recovery_factor=recovery_factor if not np.isnan(recovery_factor) else 0.0,
            exposure_pct=exposure_pct,
            avg_holding_period=avg_holding_period,
        )
