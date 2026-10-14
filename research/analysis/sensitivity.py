"""
================================================================================
Phase 5: EMA Sensitivity Matrix & Robust Region Analysis
================================================================================
Runs comprehensive grid search across Fast (5-30) x Slow (20-100) EMAs,
constructs performance matrices, and identifies robust parameter plateaus.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import ContractSpec
from ..strategies.ema_crossover import EMACrossoverStrategy


class SensitivityAnalyzer:
    def __init__(
        self,
        spec: ContractSpec,
        initial_capital: float = 100_000.0,
        fast_range: Tuple[int, int, int] = (5, 30, 2),   # start, stop, step
        slow_range: Tuple[int, int, int] = (20, 100, 5)  # start, stop, step
    ):
        self.spec = spec
        self.initial_capital = initial_capital
        self.fast_vals = list(range(fast_range[0], fast_range[1] + 1, fast_range[2]))
        self.slow_vals = list(range(slow_range[0], slow_range[1] + 1, slow_range[2]))

    def run_grid(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Evaluate all valid (Fast < Slow) parameter pairs on historical data.
        """
        records = []
        engine = BacktestEngine(
            spec=self.spec,
            initial_capital=self.initial_capital,
            execution_timing="next_open",
            slippage_ticks=1,
            allocation_pct=0.50
        )

        for fast in self.fast_vals:
            for slow in self.slow_vals:
                if fast >= slow:
                    continue

                strat = EMACrossoverStrategy(fast_period=fast, slow_period=slow)
                res = engine.run(df, strat.generate_signals)
                m = res["metrics"]

                records.append({
                    "symbol": self.spec.symbol,
                    "fast_ema": fast,
                    "slow_ema": slow,
                    "total_return_pct": m["total_return_pct"],
                    "cagr_pct": m["cagr_pct"],
                    "max_drawdown_pct": m["max_drawdown_pct"],
                    "profit_factor": m["profit_factor"],
                    "sharpe_ratio": m["sharpe_ratio"],
                    "sortino_ratio": m["sortino_ratio"],
                    "win_rate_pct": m["win_rate_pct"],
                    "trades_count": m["total_trades"],
                    "expectancy_dollars": m["expectancy_dollars"],
                })

        return pd.DataFrame(records)

    @staticmethod
    def identify_robust_regions(
        grid_df: pd.DataFrame,
        metric: str = "sharpe_ratio",
        min_trades: int = 10,
        neighborhood_size: int = 1
    ) -> pd.DataFrame:
        """
        Identifies parameter plateaus where neighboring parameters also show stable,
        high performance (avoiding isolated overfitted spikes).
        """
        # Filter minimum sample size
        valid = grid_df[grid_df["trades_count"] >= min_trades].copy()
        if valid.empty:
            return pd.DataFrame()

        pivot = valid.pivot(index="fast_ema", columns="slow_ema", values=metric)
        robustness_scores = []

        for idx, row in valid.iterrows():
            f = int(row["fast_ema"])
            s = int(row["slow_ema"])

            # Find neighbors in pivot
            neighbors = []
            for df_val in [-2, 0, 2]:
                for ds_val in [-5, 0, 5]:
                    nf, ns = f + df_val, s + ds_val
                    if nf in pivot.index and ns in pivot.columns:
                        val = pivot.loc[nf, ns]
                        if not np.isnan(val):
                            neighbors.append(val)

            if len(neighbors) >= 4:
                mean_n = np.mean(neighbors)
                std_n = np.std(neighbors)
                stability = mean_n / (std_n + 0.001)  # High mean + low variance
                robustness_scores.append({
                    "fast_ema": f,
                    "slow_ema": s,
                    "sharpe_ratio": row["sharpe_ratio"],
                    "individual_metric": row[metric],
                    "neighborhood_mean": mean_n,
                    "neighborhood_std": std_n,
                    "stability_score": stability,
                    "cagr_pct": row["cagr_pct"],
                    "max_drawdown_pct": row["max_drawdown_pct"],
                    "profit_factor": row["profit_factor"],
                    "trades_count": row["trades_count"],
                })

        rob_df = pd.DataFrame(robustness_scores)
        if not rob_df.empty:
            rob_df = rob_df.sort_values(by="stability_score", ascending=False)
        return rob_df
