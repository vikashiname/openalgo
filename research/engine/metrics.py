"""
================================================================================
Quantitative Performance & Risk Metrics Engine
================================================================================
Implements institutional-grade risk and performance statistics:
CAGR, Sharpe, Sortino, Calmar, Expectancy, Max Drawdown & Recovery.
"""

import math
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from .trade_logger import TradeRecord


class MetricsEngine:
    @staticmethod
    def calculate_metrics(
        equity_series: pd.Series,
        trades: List[TradeRecord],
        initial_capital: float,
        risk_free_rate: float = 0.045,  # 4.5% annual risk-free rate
        benchmark_series: Optional[pd.Series] = None
    ) -> Dict[str, Any]:
        """
        Compute full quantitative performance metrics from equity curve and trade logs.
        """
        if equity_series.empty or len(equity_series) < 2:
            return {}

        start_val = initial_capital
        end_val = float(equity_series.iloc[-1])
        total_ret = ((end_val - start_val) / start_val) * 100.0
        net_profit = end_val - start_val

        # Duration & CAGR
        start_date = equity_series.index[0]
        end_date = equity_series.index[-1]
        days = max(1, (end_date - start_date).days)
        years = days / 365.25

        if years > 0 and end_val > 0:
            cagr = ((end_val / start_val) ** (1.0 / years) - 1.0) * 100.0
        else:
            cagr = 0.0

        # Drawdown Series & Duration
        running_max = equity_series.cummax()
        drawdown_series = (running_max - equity_series) / running_max * 100.0
        max_dd = float(drawdown_series.max())

        # Drawdown Duration (peak to new peak)
        dd_duration_days = 0
        current_dd_days = 0
        last_peak_date = start_date

        for dt, val in equity_series.items():
            if val >= running_max.loc[dt]:
                last_peak_date = dt
                current_dd_days = 0
            else:
                current_dd_days = (dt - last_peak_date).days
                if current_dd_days > dd_duration_days:
                    dd_duration_days = current_dd_days

        # Daily Returns & Volatility
        daily_rets = equity_series.pct_change().dropna()
        trading_days_per_year = 252

        daily_rf = (1.0 + risk_free_rate) ** (1.0 / trading_days_per_year) - 1.0
        excess_daily_rets = daily_rets - daily_rf

        mean_excess = excess_daily_rets.mean()
        std_ret = daily_rets.std()

        # Sharpe Ratio
        if std_ret > 0:
            sharpe = (mean_excess / std_ret) * math.sqrt(trading_days_per_year)
        else:
            sharpe = 0.0

        # Sortino Ratio (True Downside Semi-Deviation below Risk-Free Rate)
        downside_diff = np.minimum(0.0, excess_daily_rets.values)
        downside_semi_variance = np.mean(downside_diff ** 2)
        downside_deviation = math.sqrt(downside_semi_variance) if downside_semi_variance > 0 else 0.0001

        if downside_deviation > 0:
            sortino = (mean_excess / downside_deviation) * math.sqrt(trading_days_per_year)
        else:
            sortino = 0.0

        # Calmar Ratio (CAGR / MaxDD)
        calmar = (cagr / max_dd) if max_dd > 0 else 0.0

        # Recovery Factor (Net Profit / Max Dollar Drawdown)
        dollar_dd = running_max - equity_series
        max_dollar_dd = float(dollar_dd.max())
        recovery_factor = (net_profit / max_dollar_dd) if max_dollar_dd > 0 else 0.0

        # Trade-Level Statistics
        closed_trades = [t for t in trades if not t.is_open]
        total_trades = len(closed_trades)

        winning_trades = [t for t in closed_trades if t.net_pnl > 0]
        losing_trades = [t for t in closed_trades if t.net_pnl <= 0]

        win_count = len(winning_trades)
        loss_count = len(losing_trades)

        win_rate = (win_count / total_trades * 100.0) if total_trades > 0 else 0.0
        loss_rate = (loss_count / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profit = sum(t.net_pnl for t in winning_trades)
        gross_loss = abs(sum(t.net_pnl for t in losing_trades))

        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        avg_win = (gross_profit / win_count) if win_count > 0 else 0.0
        avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0.0
        win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0

        avg_trade = (net_profit / total_trades) if total_trades > 0 else 0.0
        expectancy_dollars = (
            (win_rate / 100.0 * avg_win) - (loss_rate / 100.0 * avg_loss)
        ) if total_trades > 0 else 0.0

        largest_win = max([t.net_pnl for t in closed_trades], default=0.0)
        largest_loss = min([t.net_pnl for t in closed_trades], default=0.0)

        avg_holding_days = (
            sum(t.holding_days for t in closed_trades) / total_trades
        ) if total_trades > 0 else 0.0

        # Benchmark Comparison
        if benchmark_series is not None and not benchmark_series.empty:
            bench_start = float(benchmark_series.iloc[0])
            bench_end = float(benchmark_series.iloc[-1])
            bench_return = ((bench_end - bench_start) / bench_start) * 100.0
            alpha = total_ret - bench_return
        else:
            bench_return = 0.0
            alpha = total_ret

        return {
            "initial_capital": initial_capital,
            "final_equity": end_val,
            "net_profit": net_profit,
            "total_return_pct": total_ret,
            "cagr_pct": cagr,
            "benchmark_return_pct": bench_return,
            "alpha_pct": alpha,
            "max_drawdown_pct": max_dd,
            "max_drawdown_duration_days": dd_duration_days,
            "recovery_factor": recovery_factor,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate_pct": win_rate,
            "loss_rate_pct": loss_rate,
            "profit_factor": profit_factor,
            "avg_win_dollars": avg_win,
            "avg_loss_dollars": avg_loss,
            "win_loss_ratio": win_loss_ratio,
            "avg_trade_dollars": avg_trade,
            "expectancy_dollars": expectancy_dollars,
            "largest_win_dollars": largest_win,
            "largest_loss_dollars": largest_loss,
            "avg_holding_days": avg_holding_days,
            "start_date": str(start_date)[:10],
            "end_date": str(end_date)[:10],
            "total_days": days,
        }
