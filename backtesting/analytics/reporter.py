"""
Detailed Terminal & HTML Summary Reporter with Institutional Gate Checklist
-----------------------------------------------------------------------------
Formats and outputs research-grade ASCII summaries and deployment gate evaluation checklists.
"""

from typing import Any, Dict, Optional

import numpy as np

from ..portfolio.equity import EquityCurveTracker
from .portfolio_analytics import AdvancedPortfolioMetrics
from .trade_analytics import PerformanceMetrics


class DeploymentGateEvaluator:
    """
    Evaluates backtest metrics against institutional minimum benchmarks
    to determine if a strategy is ready for live/paper deployment.
    """

    DEFAULT_BENCHMARKS = {
        "sharpe_ratio": 1.0,  # Minimum Sharpe Ratio >= 1.0
        "profit_factor": 1.30,  # Minimum Profit Factor >= 1.30
        "win_rate_pct": 40.0,  # Minimum Win Rate >= 40%
        "max_drawdown_pct": 20.0,  # Maximum Drawdown <= 20%
        "min_trades": 100,  # Minimum Trade Count >= 100
        "cagr_pct": 7.0,  # Minimum CAGR >= 7.0%
        "expectancy_pct": 0.0,  # Trade Expectancy > 0.0%
    }

    @classmethod
    def evaluate(
        cls,
        metrics: PerformanceMetrics,
        adv_metrics: AdvancedPortfolioMetrics,
        equity_tracker: EquityCurveTracker,
        custom_benchmarks: dict[str, float] | None = None,
        oos_results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        benchmarks = cls.DEFAULT_BENCHMARKS.copy()
        if custom_benchmarks:
            benchmarks.update(custom_benchmarks)

        max_dd = equity_tracker.get_max_drawdown_pct()

        gates = [
            {
                "name": "1. Risk-Adjusted Return (Sharpe)",
                "target": f"Sharpe ≥ {benchmarks['sharpe_ratio']:.2f}",
                "actual": f"{adv_metrics.sharpe_ratio:.2f}",
                "passed": adv_metrics.sharpe_ratio >= benchmarks["sharpe_ratio"],
            },
            {
                "name": "2. Compound Annual Return (CAGR)",
                "target": f"CAGR ≥ {benchmarks['cagr_pct']:.1f}%",
                "actual": f"{adv_metrics.cagr:+.2f}%",
                "passed": adv_metrics.cagr >= benchmarks["cagr_pct"],
            },
            {
                "name": "3. Profit Factor",
                "target": f"Profit Factor ≥ {benchmarks['profit_factor']:.2f}",
                "actual": f"{metrics.profit_factor:.2f}"
                if not np.isnan(metrics.profit_factor)
                else "N/A",
                "passed": (not np.isnan(metrics.profit_factor))
                and (metrics.profit_factor >= benchmarks["profit_factor"]),
            },
            {
                "name": "4. Maximum Drawdown (MDD)",
                "target": f"Max Drawdown ≤ {benchmarks['max_drawdown_pct']:.1f}%",
                "actual": f"{max_dd:.2f}%",
                "passed": max_dd <= benchmarks["max_drawdown_pct"],
            },
            {
                "name": "5. Win Rate",
                "target": f"Win Rate ≥ {benchmarks['win_rate_pct']:.1f}%",
                "actual": f"{metrics.win_rate:.2f}%",
                "passed": metrics.win_rate >= benchmarks["win_rate_pct"],
            },
            {
                "name": "6. Sample Size (Trade Count)",
                "target": f"Total Trades ≥ {benchmarks['min_trades']}",
                "actual": f"{metrics.total_trades}",
                "passed": metrics.total_trades >= benchmarks["min_trades"],
            },
            {
                "name": "7. Trade Expectancy",
                "target": f"Expectancy > {benchmarks['expectancy_pct']:.1f}%",
                "actual": f"{metrics.expectancy_pct:+.2f}%",
                "passed": metrics.expectancy_pct > benchmarks["expectancy_pct"],
            },
        ]

        if oos_results:
            is_sharpe = oos_results.get("is_adv_metrics", adv_metrics).sharpe_ratio
            oos_sharpe = oos_results.get("oos_adv_metrics", adv_metrics).sharpe_ratio
            retention = (oos_sharpe / is_sharpe * 100.0) if is_sharpe > 0 else 0.0
            gates.append(
                {
                    "name": "8. Out-of-Sample Robustness",
                    "target": "OOS Sharpe Retention ≥ 60%",
                    "actual": f"{retention:.1f}% (IS: {is_sharpe:.2f} | OOS: {oos_sharpe:.2f})",
                    "passed": retention >= 60.0 and oos_sharpe > 0,
                }
            )

        passed_count = sum(1 for g in gates if g["passed"])
        total_count = len(gates)
        overall_passed = passed_count == total_count

        return {
            "gates": gates,
            "passed_count": passed_count,
            "total_count": total_count,
            "overall_passed": overall_passed,
            "verdict": "🟢 PASS - READY FOR PAPER/LIVE TRADING"
            if overall_passed
            else "🔴 FAIL - REJECTED FOR LIVE TRADING",
        }


class DetailedConsoleReporter:
    """
    Phase 1-7: Comprehensive Terminal Reporter.
    Formats research-grade execution, risk, portfolio analytics, and optimization metrics.
    """

    @staticmethod
    def print_summary(
        symbol: str,
        metrics: PerformanceMetrics,
        adv_metrics: AdvancedPortfolioMetrics,
        equity_tracker: EquityCurveTracker,
        csv_path: str,
        oos_results: dict[str, Any] | None = None,
    ):
        eq_df = equity_tracker.get_equity_dataframe()
        max_dd = equity_tracker.get_max_drawdown_pct()
        end_equity = (
            eq_df["portfolio_value"].iloc[-1] if not eq_df.empty else equity_tracker.initial_capital
        )
        total_return_pct = (
            (end_equity - equity_tracker.initial_capital) / equity_tracker.initial_capital
        ) * 100.0

        pf_str = f"{metrics.profit_factor:.2f}" if not np.isnan(metrics.profit_factor) else "N/A"

        print("\n================================================================================")
        print(f"          RESEARCH-GRADE FULL FRAMEWORK SUMMARY ({symbol})                      ")
        print("================================================================================")
        print(" 📊 PORTFOLIO & EQUITY CURVE METRICS (PHASE 1)")
        print(" ------------------------------------------------------------------------------")
        print(f"  • Initial Capital      : ₹{equity_tracker.initial_capital:,.2f}")
        print(f"  • Final Portfolio Value: ₹{end_equity:,.2f}")
        print(f"  • Total Strategy Return: {total_return_pct:+.2f}%")
        print(
            f"  • Peak Portfolio Value : ₹{eq_df['cum_max'].max():,.2f}"
            if not eq_df.empty
            else "  • Peak Portfolio Value : N/A"
        )
        print(f"  • Maximum Drawdown (%) : {max_dd:.2f}%")
        print(" ------------------------------------------------------------------------------")
        print(" 📈 DETAILED TRADE & RISK ANALYTICS (PHASE 2)")
        print(" ------------------------------------------------------------------------------")
        print(f"  • Total Executed Trades: {metrics.total_trades}")
        print(f"  • Winning Trades       : {metrics.winning_trades} ({metrics.win_rate:.2f}%)")
        print(f"  • Losing Trades        : {metrics.losing_trades} ({metrics.loss_rate:.2f}%)")
        print(f"  • Profit Factor        : {pf_str}")
        print(f"  • Risk-Reward Ratio    : {metrics.risk_reward_ratio:.2f}")
        print(
            f"  • Trade Expectancy     : ₹{metrics.expectancy:+.2f} per trade ({metrics.expectancy_pct:+.2f}%)"
        )
        print(f"  • Average Win          : ₹{metrics.avg_win:,.2f} ({metrics.avg_win_pct:+.2f}%)")
        print(f"  • Average Loss         : ₹{metrics.avg_loss:,.2f} (-{metrics.avg_loss_pct:.2f}%)")
        print(
            f"  • Largest Winner       : ₹{metrics.largest_winner:,.2f} ({metrics.largest_winner_pct:+.2f}%)"
        )
        print(
            f"  • Largest Loser        : ₹{metrics.largest_loser:,.2f} ({metrics.largest_loser_pct:.2f}%)"
        )
        print(f"  • Max Consecutive Wins : {metrics.max_consecutive_wins} trades")
        print(f"  • Max Consecutive Loss : {metrics.max_consecutive_losses} trades")
        print(" ------------------------------------------------------------------------------")
        print(" 🏛️ ADVANCED RISK-ADJUSTED PORTFOLIO ANALYTICS (PHASE 3)")
        print(" ------------------------------------------------------------------------------")
        print(f"  • Compound Annual Rate (CAGR) : {adv_metrics.cagr:+.2f}%")
        print(f"  • Sharpe Ratio (Annualized)   : {adv_metrics.sharpe_ratio:.2f}")
        print(f"  • Sortino Ratio (Downside)   : {adv_metrics.sortino_ratio:.2f}")
        print(f"  • Calmar Ratio (CAGR / MDD)   : {adv_metrics.calmar_ratio:.2f}")
        print(f"  • Annualized Volatility       : {adv_metrics.annual_volatility:.2f}%")
        print(f"  • Recovery Factor             : {adv_metrics.recovery_factor:.2f}")
        print(
            f"  • Market Exposure             : {adv_metrics.exposure_pct:.2f}% of total timeframe"
        )
        print(
            f"  • Average Holding Period      : {adv_metrics.avg_holding_period:.1f} bars/candles"
        )
        print(" ------------------------------------------------------------------------------")

        # Evaluate Institutional Deployment Gate Checklist
        gate_res = DeploymentGateEvaluator.evaluate(
            metrics, adv_metrics, equity_tracker, oos_results=oos_results
        )

        print(" 🚦 INSTITUTIONAL DEPLOYMENT & RESEARCH READINESS CHECKLIST")
        print(" ------------------------------------------------------------------------------")
        for g in gate_res["gates"]:
            status_icon = "✅ PASS" if g["passed"] else "❌ FAIL"
            print(
                f"  {status_icon} | {g['name']:<35} | Target: {g['target']:<22} | Actual: {g['actual']}"
            )
        print(" ------------------------------------------------------------------------------")
        print(
            f"  • Overall Gate Score: {gate_res['passed_count']}/{gate_res['total_count']} Gates Passed"
        )
        print(f"  • FINAL VERDICT     : {gate_res['verdict']}")
        print(" ------------------------------------------------------------------------------")
        print(" 📁 DATA EXPORT & ARTIFACTS")
        print(" ------------------------------------------------------------------------------")
        print(f"  • Exported CSV Path    : {csv_path}")
        print("================================================================\n")
        return gate_res
