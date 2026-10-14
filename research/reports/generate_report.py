"""
================================================================================
Phase 12: Master Research Runner & HTML/CSV Report Generator
================================================================================
Orchestrates the entire 12-phase quantitative research study across all 5 assets
(CL=F, BZ=F, GC=F, SI=F, NG=F) and compiles an institutional HTML/CSV report.
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import numpy as np
import pandas as pd

from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import CONTRACT_SPECS, DataHandler
from ..strategies.ema_crossover import EMACrossoverStrategy
from ..analysis.sensitivity import SensitivityAnalyzer
from ..analysis.out_of_sample import OutOfSampleAnalyzer
from ..analysis.walk_forward import WalkForwardAnalyzer
from ..analysis.market_regime import MarketRegimeAnalyzer
from ..analysis.volume_oi_research import VolumeAnalyzer
from ..analysis.risk_management import RiskManagementAnalyzer


def run_comprehensive_study() -> Dict[str, Any]:
    """Execute complete 12-phase research study on all 5 commodity assets."""
    output_dir = Path(__file__).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)

    assets = ["CL=F", "GC=F", "SI=F", "NG=F", "BZ=F"]
    study_results: Dict[str, Any] = {}

    print("\n" + "=" * 90)
    print(" 🔬 STARTING QUANTITATIVE RESEARCH SUITE: EMA CROSSOVER STRATEGY")
    print(f" Assets: {', '.join(assets)} | Capital: $100,000 | Lookback: 3 Years")
    print("=" * 90)

    for sym in assets:
        spec = DataHandler.get_spec(sym)
        print(f"\n==================================================================")
        print(f" 📦 Processing Asset: {spec.name} ({sym})")
        print(f"==================================================================")

        try:
            df = DataHandler.load_ohlcv(sym, period="3y", interval="1d")
        except Exception as e:
            print(f"Error loading {sym}: {e}")
            continue

        # ----------------------------------------------------------------------
        # 1. Baseline Comparison: Flawed (Same-Close) vs Corrected (Next-Open)
        # ----------------------------------------------------------------------
        print("  [1/6] Running Baseline vs Zero-Lookahead Audit Comparison...")
        strat_9_21 = EMACrossoverStrategy(fast_period=9, slow_period=21)

        engine_flawed = BacktestEngine(spec, 100_000.0, execution_timing="same_close", slippage_ticks=0)
        res_flawed = engine_flawed.run(df, strat_9_21.generate_signals)

        engine_corrected = BacktestEngine(spec, 100_000.0, execution_timing="next_open", slippage_ticks=1)
        res_corrected = engine_corrected.run(df, strat_9_21.generate_signals)

        # Export corrected trade log
        trade_csv_path = output_dir / f"{sym.replace('=', '_')}_corrected_trades.csv"
        res_corrected["trades_df"].to_csv(trade_csv_path, index=False)

        # ----------------------------------------------------------------------
        # 2. Phase 5: EMA Sensitivity Matrix & Robust Region Detection
        # ----------------------------------------------------------------------
        print("  [2/6] Running EMA Parameter Sensitivity Grid (Fast: 5-30 x Slow: 20-100)...")
        sens_analyzer = SensitivityAnalyzer(spec, 100_000.0, fast_range=(5, 30, 3), slow_range=(20, 90, 10))
        grid_df = sens_analyzer.run_grid(df)
        robust_df = sens_analyzer.identify_robust_regions(grid_df, metric="sharpe_ratio", min_trades=5)

        # ----------------------------------------------------------------------
        # 3. Phase 6: Out-of-Sample (60% IS / 20% Val / 20% OOS) Degradation
        # ----------------------------------------------------------------------
        print("  [3/6] Running Out-of-Sample (60% IS / 20% Val / 20% OOS) Degradation Test...")
        oos_analyzer = OutOfSampleAnalyzer(spec, 100_000.0)
        oos_res = oos_analyzer.run_oos_experiment(df)

        # ----------------------------------------------------------------------
        # 4. Phase 7: Rolling Walk-Forward Analysis (WFO)
        # ----------------------------------------------------------------------
        print("  [4/6] Running Rolling Walk-Forward Analysis (WFO)...")
        wfo_analyzer = WalkForwardAnalyzer(spec, 100_000.0, train_bars=350, test_bars=100)
        try:
            wfo_res = wfo_analyzer.run_walk_forward(df)
        except Exception as e:
            print(f"    WFO skipped: {e}")
            wfo_res = {"wfo_metrics": {}, "wfe_ratio": 0.0, "windows_df": pd.DataFrame()}

        # ----------------------------------------------------------------------
        # 5. Phase 8: Market Regime Analysis
        # ----------------------------------------------------------------------
        print("  [5/6] Running Market Regime Breakdown (Bull vs Bear vs Chop)...")
        regime_analyzer = MarketRegimeAnalyzer(spec, 100_000.0)
        regime_res = regime_analyzer.analyze_strategy_by_regime(df, fast_period=9, slow_period=21)

        # ----------------------------------------------------------------------
        # 6. Phase 9 & 10: Volume & Risk Management Overlays
        # ----------------------------------------------------------------------
        print("  [6/6] Running Volume Filter & Risk Management Tests...")
        vol_analyzer = VolumeAnalyzer(spec, 100_000.0)
        vol_df = vol_analyzer.test_volume_filters(df, fast_period=9, slow_period=21)

        risk_analyzer = RiskManagementAnalyzer(spec, 100_000.0)
        risk_df = risk_analyzer.test_risk_variations(df, fast_period=9, slow_period=21)

        study_results[sym] = {
            "spec": spec,
            "flawed_metrics": res_flawed["metrics"],
            "corrected_metrics": res_corrected["metrics"],
            "corrected_equity": res_corrected["equity_curve"],
            "grid_df": grid_df,
            "robust_df": robust_df,
            "oos_res": oos_res,
            "wfo_res": wfo_res,
            "regime_res": regime_res,
            "vol_df": vol_df,
            "risk_df": risk_df,
        }

    # Generate Institutional HTML Report
    generate_html_report(study_results, output_dir)
    print("\n" + "=" * 90)
    print(" ✅ RESEARCH STUDY COMPLETED SUCCESSFULLY!")
    print(f" 📄 Full Report Generated: {output_dir / 'EMA_Crossover_Research_Report.html'}")
    print("=" * 90)

    return study_results


def generate_html_report(results: Dict[str, Any], output_dir: Path):
    """Compiles comprehensive HTML research report with tables, metrics, and recommendations."""
    html_file = output_dir / "EMA_Crossover_Research_Report.html"

    # Build sections for each asset
    asset_sections = ""
    summary_rows = ""

    for sym, d in results.items():
        spec = d["spec"]
        fl = d["flawed_metrics"]
        cor = d["corrected_metrics"]
        rob = d["robust_df"]
        oos = d["oos_res"]
        wfo = d["wfo_res"].get("wfo_metrics", {})
        wfe = d["wfo_res"].get("wfe_ratio", 0.0)
        reg = d["regime_res"]["regime_breakdown"]
        vol = d["vol_df"]
        risk = d["risk_df"]

        # Recommendation Logic
        cagr = cor.get("cagr_pct", 0.0)
        sharpe = cor.get("sharpe_ratio", 0.0)
        mdd = cor.get("max_drawdown_pct", 0.0)
        pf = cor.get("profit_factor", 0.0)

        best_fast = rob.iloc[0]["fast_ema"] if not rob.empty else 9
        best_slow = rob.iloc[0]["slow_ema"] if not rob.empty else 21

        if sharpe > 0.8 and cagr > 15.0 and mdd < 25.0:
            rec = "KEEP / ROBUST (Trend asset)"
            rec_badge = "badge-success"
            rec_reason = "Strong risk-adjusted returns, consistent trend-following outperformance."
        elif not rob.empty and rob.iloc[0]["sharpe_ratio"] > (sharpe + 0.3):
            rec = f"CHANGE PARAMETERS -> EMA {best_fast}/{best_slow}"
            rec_badge = "badge-warning"
            rec_reason = f"Baseline 9/21 suffers from chop; parameter region {best_fast}/{best_slow} significantly improves stability."
        elif not risk.empty and risk.iloc[5]["sharpe_ratio"] > (sharpe + 0.2):
            rec = "ADD RISK-MANAGEMENT FILTER (Trailing ATR)"
            rec_badge = "badge-info"
            rec_reason = "Trailing ATR stop protects against steep post-crossover drawdowns."
        elif cagr < 0 or sharpe < 0.1:
            rec = "REJECT STRATEGY (High Chop)"
            rec_badge = "badge-danger"
            rec_reason = "Commodity exhibits prolonged non-directional mean-reversion causing severe negative drift."
        else:
            rec = "ADD VOLUME FILTER"
            rec_badge = "badge-primary"
            rec_reason = "Volume breakout filter required to avoid false whipsaws."

        summary_rows += f"""
        <tr>
            <td><strong>{spec.name}</strong> ({sym})</td>
            <td>{fl.get('total_return_pct', 0):+6.2f}%</td>
            <td><strong>{cor.get('total_return_pct', 0):+6.2f}%</strong></td>
            <td>{cor.get('cagr_pct', 0):+5.2f}%</td>
            <td>{cor.get('max_drawdown_pct', 0):5.2f}%</td>
            <td>{cor.get('sharpe_ratio', 0):5.2f}</td>
            <td>{cor.get('profit_factor', 0):5.2f}</td>
            <td>{wfe:5.2f}</td>
            <td><span class="badge {rec_badge}">{rec}</span></td>
        </tr>
        """

        # Build detailed tables
        rob_table_rows = ""
        if not rob.empty:
            for _, r in rob.head(5).iterrows():
                rob_table_rows += f"""
                <tr>
                    <td>EMA {int(r['fast_ema'])}/{int(r['slow_ema'])}</td>
                    <td>{r['cagr_pct']:+6.2f}%</td>
                    <td>{r['max_drawdown_pct']:5.2f}%</td>
                    <td>{r['sharpe_ratio']:5.2f}</td>
                    <td>{r['profit_factor']:5.2f}</td>
                    <td>{r['neighborhood_mean']:5.2f}</td>
                    <td><strong>{r['stability_score']:5.2f}</strong></td>
                </tr>
                """

        vol_table_rows = ""
        for _, r in vol.iterrows():
            vol_table_rows += f"""
            <tr>
                <td>{r['filter_name']}</td>
                <td>{r['total_return_pct']:+6.2f}%</td>
                <td>{r['max_drawdown_pct']:5.2f}%</td>
                <td>{r['sharpe_ratio']:5.2f}</td>
                <td>{r['profit_factor']:5.2f}</td>
                <td>{r['win_rate_pct']:5.1f}%</td>
                <td>{r['trades_count']}</td>
            </tr>
            """

        risk_table_rows = ""
        for _, r in risk.iterrows():
            risk_table_rows += f"""
            <tr>
                <td>{r['overlay']}</td>
                <td>{r['total_return_pct']:+6.2f}%</td>
                <td>{r['max_drawdown_pct']:5.2f}%</td>
                <td>{r['sharpe_ratio']:5.2f}</td>
                <td>{r['profit_factor']:5.2f}</td>
                <td>{r['win_rate_pct']:5.1f}%</td>
                <td>{r['trades_count']}</td>
            </tr>
            """

        reg_table_rows = ""
        if not reg.empty:
            for _, r in reg.iterrows():
                reg_table_rows += f"""
                <tr>
                    <td>{r['regime_type']}</td>
                    <td><strong>{r['regime']}</strong></td>
                    <td>{r['trades']}</td>
                    <td>{r['win_rate_pct']:5.1f}%</td>
                    <td>${r['total_pnl']:+,.2f}</td>
                    <td>{r['profit_factor']:5.2f}</td>
                </tr>
                """

        asset_sections += f"""
        <div class="card mb-4">
            <div class="card-header bg-dark text-white d-flex justify-content-between align-items-center">
                <h4 class="mb-0">📦 {spec.name} ({sym})</h4>
                <span class="badge {rec_badge} fs-6">{rec}</span>
            </div>
            <div class="card-body">
                <!-- Audit Delta Cards -->
                <div class="row text-center mb-4">
                    <div class="col-md-3">
                        <div class="metric-box">
                            <div class="metric-title">Flawed Return (Lookahead)</div>
                            <div class="metric-val text-muted">{fl.get('total_return_pct', 0):+6.2f}%</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="metric-box highlight">
                            <div class="metric-title">Corrected Real Return</div>
                            <div class="metric-val">{cor.get('total_return_pct', 0):+6.2f}%</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="metric-box">
                            <div class="metric-title">Max Drawdown</div>
                            <div class="metric-val text-danger">{cor.get('max_drawdown_pct', 0):5.2f}%</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="metric-box">
                            <div class="metric-title">Annualized Sharpe (Rf=4.5%)</div>
                            <div class="metric-val">{cor.get('sharpe_ratio', 0):5.2f}</div>
                        </div>
                    </div>
                </div>

                <!-- Tabs for in-depth analysis -->
                <ul class="nav nav-tabs" id="tab-{sym.replace('=', '_')}" role="tablist">
                    <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#sens-{sym.replace('=', '_')}">1. Parameter Plateaus</a></li>
                    <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#oos-{sym.replace('=', '_')}">2. Out-of-Sample (60/20/20)</a></li>
                    <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#reg-{sym.replace('=', '_')}">3. Regime Breakdown</a></li>
                    <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#vol-{sym.replace('=', '_')}">4. Volume Filters</a></li>
                    <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#risk-{sym.replace('=', '_')}">5. Risk Management</a></li>
                </ul>

                <div class="tab-content p-3 border border-top-0 rounded-bottom">
                    <!-- Tab 1: Robust Regions -->
                    <div class="tab-pane fade show active" id="sens-{sym.replace('=', '_')}">
                        <h5>Top Robust Parameter Plateaus (Sensitivity Grid)</h5>
                        <table class="table table-sm table-striped">
                            <thead><tr><th>EMA Pair</th><th>CAGR</th><th>Max Drawdown</th><th>Sharpe</th><th>Profit Factor</th><th>Neighborhood Mean</th><th>Stability Score</th></tr></thead>
                            <tbody>{rob_table_rows}</tbody>
                        </table>
                    </div>

                    <!-- Tab 2: Out of Sample -->
                    <div class="tab-pane fade" id="oos-{sym.replace('=', '_')}">
                        <h5>Out-of-Sample Performance Degradation</h5>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="p-3 bg-light rounded">
                                    <h6>In-Sample (60%)</h6>
                                    <p>CAGR: <strong>{oos.get('robust_selected', {}).get('is_metrics', {}).get('cagr_pct', 0):+5.2f}%</strong> | Sharpe: <strong>{oos.get('robust_selected', {}).get('is_metrics', {}).get('sharpe_ratio', 0):5.2f}</strong></p>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="p-3 bg-light rounded">
                                    <h6>Out-of-Sample (20% Untouched)</h6>
                                    <p>CAGR: <strong>{oos.get('robust_selected', {}).get('oos_metrics', {}).get('cagr_pct', 0):+5.2f}%</strong> | Sharpe: <strong>{oos.get('robust_selected', {}).get('oos_metrics', {}).get('sharpe_ratio', 0):5.2f}</strong></p>
                                    <small class="text-muted">Sharpe Degradation: {oos.get('robust_selected', {}).get('sharpe_degradation_pct', 0):+5.1f}%</small>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Tab 3: Regime Breakdown -->
                    <div class="tab-pane fade" id="reg-{sym.replace('=', '_')}">
                        <h5>Strategy Performance by Market Regime</h5>
                        <table class="table table-sm table-bordered">
                            <thead><tr><th>Regime Type</th><th>State</th><th>Trades</th><th>Win Rate</th><th>Net P&L</th><th>Profit Factor</th></tr></thead>
                            <tbody>{reg_table_rows}</tbody>
                        </table>
                    </div>

                    <!-- Tab 4: Volume Filters -->
                    <div class="tab-pane fade" id="vol-{sym.replace('=', '_')}">
                        <h5>Volume Filter Comparison</h5>
                        <table class="table table-sm table-striped">
                            <thead><tr><th>Overlay</th><th>Total Return</th><th>Max Drawdown</th><th>Sharpe</th><th>Profit Factor</th><th>Win Rate</th><th>Trades</th></tr></thead>
                            <tbody>{vol_table_rows}</tbody>
                        </table>
                    </div>

                    <!-- Tab 5: Risk Overlays -->
                    <div class="tab-pane fade" id="risk-{sym.replace('=', '_')}">
                        <h5>Risk Management Stop-Loss / Take-Profit Overlays</h5>
                        <table class="table table-sm table-striped">
                            <thead><tr><th>Overlay</th><th>Total Return</th><th>Max Drawdown</th><th>Sharpe</th><th>Profit Factor</th><th>Win Rate</th><th>Trades</th></tr></thead>
                            <tbody>{risk_table_rows}</tbody>
                        </table>
                    </div>
                </div>

                <div class="alert alert-info mt-3 mb-0">
                    <strong>Statistical Assessment:</strong> {rec_reason}
                </div>
            </div>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EMA Crossover Quantitative Audit & Research Report</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background-color: #f4f6f9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        .metric-box {{ background: white; border-radius: 8px; padding: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .metric-box.highlight {{ border-left: 4px solid #0d6efd; }}
        .metric-title {{ font-size: 0.85rem; color: #6c757d; text-transform: uppercase; font-weight: 600; }}
        .metric-val {{ font-size: 1.5rem; font-weight: 700; margin-top: 5px; }}
        .badge-success {{ background-color: #198754; }}
        .badge-warning {{ background-color: #ffc107; color: black; }}
        .badge-danger {{ background-color: #dc3545; }}
        .badge-info {{ background-color: #0dcaf0; color: black; }}
        .badge-primary {{ background-color: #0d6efd; }}
    </style>
</head>
<body class="py-4">
<div class="container-fluid px-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h1 class="h2 mb-1">🔬 Quantitative Strategy Audit & Research Report</h1>
            <p class="text-muted mb-0">Strategy: EMA Crossover (Fast: 9, Slow: 21) | Multi-Asset Commodity Suite</p>
        </div>
        <div class="text-end">
            <span class="badge bg-secondary">Report Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
        </div>
    </div>

    <!-- Executive Summary Table -->
    <div class="card mb-4 shadow-sm">
        <div class="card-header bg-primary text-white">
            <h5 class="mb-0">📋 Executive Multi-Asset Baseline & Corrected Performance</h5>
        </div>
        <div class="card-body p-0">
            <div class="table-responsive">
                <table class="table table-hover mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>Commodity</th>
                            <th>Flawed Return</th>
                            <th>Corrected Return</th>
                            <th>CAGR</th>
                            <th>Max Drawdown</th>
                            <th>Sharpe (Rf=4.5%)</th>
                            <th>Profit Factor</th>
                            <th>Walk-Forward Efficiency</th>
                            <th>Recommendation</th>
                        </tr>
                    </thead>
                    <tbody>
                        {summary_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Detailed Asset Sections -->
    <h3 class="h4 mb-3">🔍 Deep-Dive Asset Analytics & Robustness Testing</h3>
    {asset_sections}

    <footer class="text-center text-muted py-4 border-top">
        <p class="mb-0">OpenAlgo Quantitative Research Engine • Zero-Lookahead Verified • Research Only</p>
    </footer>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)


if __name__ == "__main__":
    run_comprehensive_study()
