"""
================================================================================
Phase 7: Rolling Walk-Forward Optimization (WFO)
================================================================================
Implements rolling window optimization and stitches out-of-sample forward
test windows into an un-overfitted Walk-Forward Equity Curve.
"""

from typing import Any, Dict, List
import numpy as np
import pandas as pd
from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import ContractSpec
from ..engine.metrics import MetricsEngine
from ..strategies.ema_crossover import EMACrossoverStrategy
from .sensitivity import SensitivityAnalyzer


class WalkForwardAnalyzer:
    def __init__(
        self,
        spec: ContractSpec,
        initial_capital: float = 100_000.0,
        train_bars: int = 350,   # ~1.4 years training window
        test_bars: int = 100     # ~5 months out-of-sample test window
    ):
        self.spec = spec
        self.initial_capital = initial_capital
        self.train_bars = train_bars
        self.test_bars = test_bars

    def run_walk_forward(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Execute rolling walk-forward analysis across historical bars.
        """
        n = len(df)
        if n < (self.train_bars + self.test_bars):
            raise ValueError(f"Insufficient bars ({n}) for train ({self.train_bars}) + test ({self.test_bars}).")

        current_idx = 0
        window_results = []
        all_oos_trades = []
        
        running_capital = self.initial_capital
        stitched_equity_pieces = []

        window_id = 0
        while (current_idx + self.train_bars + self.test_bars) <= n:
            window_id += 1
            train_df = df.iloc[current_idx : current_idx + self.train_bars].copy()
            test_df = df.iloc[current_idx + self.train_bars : current_idx + self.train_bars + self.test_bars].copy()

            # 1. Optimize on In-Sample Training Window
            analyzer = SensitivityAnalyzer(self.spec, running_capital)
            grid_train = analyzer.run_grid(train_df)
            robust_train = analyzer.identify_robust_regions(grid_train, metric="sharpe_ratio", min_trades=3)

            if not robust_train.empty:
                opt_fast = int(robust_train.iloc[0]["fast_ema"])
                opt_slow = int(robust_train.iloc[0]["slow_ema"])
                is_sharpe = robust_train.iloc[0]["sharpe_ratio"]
                is_cagr = robust_train.iloc[0]["cagr_pct"]
            else:
                opt_fast, opt_slow = 9, 21
                is_sharpe = 0.0
                is_cagr = 0.0

            # 2. Test strictly on Out-of-Sample Window with chosen parameter
            strat = EMACrossoverStrategy(fast_period=opt_fast, slow_period=opt_slow)
            engine = BacktestEngine(
                self.spec,
                initial_capital=running_capital,
                execution_timing="next_open",
                slippage_ticks=1,
                allocation_pct=0.50
            )
            res_oos = engine.run(test_df, strat.generate_signals)
            m_oos = res_oos["metrics"]

            # Update running capital for next window
            eq_piece = res_oos["equity_curve"]
            running_capital = float(eq_piece.iloc[-1])
            stitched_equity_pieces.append(eq_piece)

            for t in res_oos["trade_logger"].trades:
                all_oos_trades.append(t)

            window_results.append({
                "window": window_id,
                "train_start": str(train_df.index[0])[:10],
                "train_end": str(train_df.index[-1])[:10],
                "test_start": str(test_df.index[0])[:10],
                "test_end": str(test_df.index[-1])[:10],
                "chosen_fast": opt_fast,
                "chosen_slow": opt_slow,
                "is_cagr_pct": is_cagr,
                "is_sharpe": is_sharpe,
                "oos_return_pct": m_oos["total_return_pct"],
                "oos_sharpe": m_oos["sharpe_ratio"],
                "oos_trades": m_oos["total_trades"],
            })

            # Advance rolling window forward by test_bars
            current_idx += self.test_bars

        # Combine stitched equity curve
        if stitched_equity_pieces:
            full_wfo_equity = pd.concat(stitched_equity_pieces)
            full_wfo_equity = full_wfo_equity[~full_wfo_equity.index.duplicated(keep="last")]
        else:
            full_wfo_equity = pd.Series([self.initial_capital])

        wfo_metrics = MetricsEngine.calculate_metrics(
            equity_series=full_wfo_equity,
            trades=all_oos_trades,
            initial_capital=self.initial_capital,
            benchmark_series=df.loc[full_wfo_equity.index, "close"] if full_wfo_equity.index[0] in df.index else None
        )

        avg_is_cagr = np.mean([w["is_cagr_pct"] for w in window_results]) if window_results else 0.0
        wfe_ratio = (wfo_metrics["cagr_pct"] / avg_is_cagr) if avg_is_cagr > 0 else 0.0

        return {
            "symbol": self.spec.symbol,
            "windows_df": pd.DataFrame(window_results),
            "wfo_metrics": wfo_metrics,
            "wfe_ratio": wfe_ratio,
            "equity_curve": full_wfo_equity,
            "trades": all_oos_trades,
        }
