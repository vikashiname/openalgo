"""
================================================================================
Phase 6: In-Sample (60%) / Validation (20%) / Out-of-Sample (20%) Testing
================================================================================
Strictly partitions historical data to detect overfitting and evaluate
parameter degradation on untouched out-of-sample periods.
"""

from typing import Any, Dict, Tuple
import pandas as pd
from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import ContractSpec
from ..strategies.ema_crossover import EMACrossoverStrategy
from .sensitivity import SensitivityAnalyzer


class OutOfSampleAnalyzer:
    def __init__(self, spec: ContractSpec, initial_capital: float = 100_000.0):
        self.spec = spec
        self.initial_capital = initial_capital

    def split_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Split data into 60% In-Sample, 20% Validation, 20% Out-of-Sample."""
        n = len(df)
        is_end = int(n * 0.60)
        val_end = int(n * 0.80)

        df_is = df.iloc[:is_end].copy()
        df_val = df.iloc[is_end:val_end].copy()
        df_oos = df.iloc[val_end:].copy()

        return df_is, df_val, df_oos

    def run_oos_experiment(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        1. Optimize on In-Sample ONLY (60%).
        2. Identify best and robust parameter pairs.
        3. Validate on Validation period (20%).
        4. Test on untouched OOS period (20%).
        5. Compute performance degradation.
        """
        df_is, df_val, df_oos = self.split_data(df)

        # Step 1: Optimize on In-Sample ONLY
        analyzer = SensitivityAnalyzer(self.spec, self.initial_capital)
        grid_is = analyzer.run_grid(df_is)
        robust_is = analyzer.identify_robust_regions(grid_is, metric="sharpe_ratio", min_trades=5)

        if robust_is.empty or grid_is.empty:
            best_fast, best_slow = 9, 21
        else:
            best_fast = int(robust_is.iloc[0]["fast_ema"])
            best_slow = int(robust_is.iloc[0]["slow_ema"])

        # Also track baseline 9/21
        baseline_fast, baseline_slow = 9, 21

        engine = BacktestEngine(self.spec, self.initial_capital, execution_timing="next_open")

        def evaluate_param(f: int, s: int, label: str):
            strat = EMACrossoverStrategy(fast_period=f, slow_period=s)
            res_is = engine.run(df_is, strat.generate_signals)
            res_val = engine.run(df_val, strat.generate_signals)
            res_oos = engine.run(df_oos, strat.generate_signals)

            m_is = res_is["metrics"]
            m_val = res_val["metrics"]
            m_oos = res_oos["metrics"]

            sharpe_is = m_is.get("sharpe_ratio", 0.0)
            sharpe_oos = m_oos.get("sharpe_ratio", 0.0)
            sharpe_deg = (sharpe_oos - sharpe_is) / (abs(sharpe_is) + 0.001) * 100.0

            cagr_is = m_is.get("cagr_pct", 0.0)
            cagr_oos = m_oos.get("cagr_pct", 0.0)
            cagr_deg = (cagr_oos - cagr_is)

            return {
                "label": label,
                "fast_ema": f,
                "slow_ema": s,
                "is_metrics": m_is,
                "val_metrics": m_val,
                "oos_metrics": m_oos,
                "sharpe_degradation_pct": sharpe_deg,
                "cagr_degradation_pct": cagr_deg,
                "is_dates": f"{m_is['start_date']} to {m_is['end_date']}",
                "val_dates": f"{m_val['start_date']} to {m_val['end_date']}",
                "oos_dates": f"{m_oos['start_date']} to {m_oos['end_date']}",
            }

        baseline_eval = evaluate_param(baseline_fast, baseline_slow, "Baseline (9/21)")
        robust_eval = evaluate_param(best_fast, best_slow, f"Robust IS Selected ({best_fast}/{best_slow})")

        return {
            "symbol": self.spec.symbol,
            "baseline": baseline_eval,
            "robust_selected": robust_eval,
            "selected_fast": best_fast,
            "selected_slow": best_slow,
        }
