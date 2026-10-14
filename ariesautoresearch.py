#!/usr/bin/env python3
"""
================================================================================
AGY Quantitative Research Orchestrator — ariesautoresearch.py
================================================================================
Central research engine for the AGY Futures OI Auto-Research Program.
Coordinates the entire lifecycle:
  DATA -> VALIDATION -> EDA -> HYPOTHESIS -> BACKTEST -> ROBUSTNESS -> REPORT

Usage:
  python ariesautoresearch.py --mode status
  python ariesautoresearch.py --mode audit
  python ariesautoresearch.py --mode pipeline --start 2024-01-01 --end 2024-07-31
  python ariesautoresearch.py --mode eda --symbol NIFTY
  python ariesautoresearch.py --mode test-hypotheses
================================================================================
"""

import sys
import os
import argparse
from datetime import date, datetime

# Ensure project root in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def print_banner():
    print("""
================================================================================
          AGY — FRESH FUTURES OI AUTO-RESEARCH SYSTEM
================================================================================
  Core Question:
  Does PRICE + OI + OI CHANGE + VOLUME + SEQUENCE provide statistically 
  significant predictive information for future price movement?
================================================================================
""")


def run_status():
    print_banner()
    print("[*] Research System Status:")
    
    # 1. Check raw archives
    raw_dir = "research/oi/raw/bhavcopy"
    raw_files = [f for f in os.listdir(raw_dir) if f.endswith(".zip")] if os.path.exists(raw_dir) else []
    print(f"  - Raw Archives: {len(raw_files)} daily Bhavcopy files in {raw_dir}")

    # 2. Check validated dataset
    val_path = "research/oi/validated/nse_futures_daily.parquet"
    if os.path.exists(val_path):
        import pandas as pd
        val_df = pd.read_parquet(val_path, columns=["trade_date", "symbol"])
        n_rows = len(val_df)
        d_min = val_df["trade_date"].min().strftime("%Y-%m-%d")
        d_max = val_df["trade_date"].max().strftime("%Y-%m-%d")
        n_syms = val_df["symbol"].nunique()
        print(f"  - Validated Parquet: {n_rows:,} records across {n_syms} symbols ({d_min} to {d_max})")
    else:
        print("  - Validated Parquet: Not built yet.")

    # 3. Check normalized series
    norm_dir = "research/oi/normalized"
    norm_files = [f for f in os.listdir(norm_dir) if f.endswith(".parquet")] if os.path.exists(norm_dir) else []
    print(f"  - Normalized Series: {len(norm_files)} instruments ({', '.join(norm_files)})")

    # 4. Registered Hypotheses
    hyp_path = "research/oi/hypotheses/HYPOTHESES_REGISTRY.md"
    if os.path.exists(hyp_path):
        print(f"  - Hypotheses Registry: ACTIVE ({hyp_path})")
    else:
        print("  - Hypotheses Registry: Not initialized.")

    # 5. Reports
    rep_dir = "research/oi/reports"
    rep_files = [f for f in os.listdir(rep_dir) if f.endswith(".md")] if os.path.exists(rep_dir) else []
    print(f"  - Research Reports: {len(rep_files)} reports published ({', '.join(rep_files)})")


def run_audit():
    print("[*] Launching Phase 1: Raw Data Audit...")
    from backtesting.oi.data.raw_audit import run_audit
    results = run_audit()
    print(f"[+] Successfully audited {len(results)} sample exchange archives.")


def run_pipeline(start_str: str, end_str: str):
    print(f"[*] Launching Phase 2: Ingestion & Normalization ({start_str} to {end_str})...")
    from backtesting.oi.data.data_pipeline import bulk_download_range, process_and_validate_all_raw, build_continuous_contract
    s_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
    e_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
    
    bulk_download_range(s_dt, e_dt)
    v_df = process_and_validate_all_raw()
    for sym in ["NIFTY", "BANKNIFTY"]:
        build_continuous_contract(v_df, sym)


def run_eda(symbol: str):
    print(f"[*] Launching Phase 3: Exploratory Data Analysis for {symbol}...")
    from backtesting.oi.validation.exploratory_analysis import run_full_eda
    res = run_full_eda(symbol)
    b1 = res["baseline"]["fwd_1d"]
    print(f"\nUnconditional 1D Baseline: Mean = {b1['mean']:.3f}%, Win Rate = {b1['win_rate']:.1f}%")
    print("\n--- 1-Day Forward State Evaluation ---")
    print(res["states_1d"][["state", "count", "frequency_pct", "mean_fwd_ret", "win_rate_pct", "alpha_vs_baseline", "p_value", "statistically_significant"]])


def run_oi_inventory():
    print("=" * 80)
    print("AGY — NFO OI STRATEGY: RESEARCH DIRECTORY REORGANIZATION INVENTORY")
    print("=" * 80)
    
    inventory = {
        "data": [
            ("research/oi/validated/nse_futures_daily.parquet", "backtesting/oi/data/nse_futures_daily.parquet", "13.2 MB validated dataset 2022-01-03 to 2024-07-31"),
            ("research/oi/normalized/BANKNIFTY_continuous.parquet", "backtesting/oi/data/normalized/BANKNIFTY_continuous.parquet", "Continuous futures contract"),
            ("research/oi/normalized/NIFTY_continuous.parquet", "backtesting/oi/data/normalized/NIFTY_continuous.parquet", "Continuous futures contract"),
            ("research/oi/features/BANKNIFTY_features.parquet", "backtesting/oi/data/features/BANKNIFTY_features.parquet", "Computed feature matrix"),
            ("research/oi/features/NIFTY_features.parquet", "backtesting/oi/data/features/NIFTY_features.parquet", "Computed feature matrix"),
            ("research/oi/features/feature_engine.py", "backtesting/oi/data/features/feature_engine.py", "Feature computation engine"),
            ("research/oi/data_pipeline.py", "backtesting/oi/data/data_pipeline.py", "Bhavcopy download & parsing pipeline"),
            ("research/oi/raw_audit.py", "backtesting/oi/data/raw_audit.py", "Raw archive integrity audit"),
            ("research/oi/metadata/data_manifest.json", "backtesting/oi/data/metadata/data_manifest.json", "Dataset checksums & provenance manifest"),
            ("research/oi/raw/bhavcopy/", "backtesting/oi/data/raw/bhavcopy/", "Historical daily Bhavcopy zip archives"),
            ("research/oi/raw/sample_nse/", "backtesting/oi/data/raw/sample_nse/", "Sample exchange archives"),
        ],
        "strategy": [
            ("SIG-OI-001-PAPER-V1.md", "backtesting/oi/strategy/SIG-OI-001-PAPER-V1.md", "Frozen Strategy Contract (SHA-256: dc1063b1...)"),
            ("research/oi/hypotheses/HYPOTHESES_REGISTRY.md", "backtesting/oi/strategy/HYPOTHESES_REGISTRY.md", "Registered hypotheses catalog (HYP-OI-0001 to HYP-OI-0005)"),
            ("research/oi/backtests/signal_contracts.py", "backtesting/oi/strategy/signal_contracts.py", "Python signal contract abstractions"),
            ("strategy/oifno.py", "backtesting/oi/strategy/oifno_reference.py", "OpenAlgo Strategy Bridge reference implementation"),
        ],
        "validation": [
            ("research/oi/exploratory_analysis.py", "backtesting/oi/validation/exploratory_analysis.py", "Phase 1 Exploratory Data Analysis & baseline"),
            ("research/oi/validation/reproduce_audit.py", "backtesting/oi/validation/reproduce_audit.py", "Falsification & audit reproduction"),
            ("research/oi/validation/statistical_audits.py", "backtesting/oi/validation/statistical_audits.py", "Statistical significance tests & p-values"),
            ("research/oi/validation/deep_robustness_audit.py", "backtesting/oi/validation/deep_robustness_audit.py", "Phase 2 40-dimension deep robustness suite"),
            ("research/oi/validation/nfo_deep_falsification_suite.py", "backtesting/oi/validation/nfo_deep_falsification_suite.py", "NFO FUTSTK deep falsification suite"),
            ("research/oi/validation/nfo_shares_dedicated_test.py", "backtesting/oi/validation/nfo_shares_dedicated_test.py", "Dedicated NFO single-stock futures test suite"),
            ("research/oi/validation/phase4_confirmation_suite.py", "backtesting/oi/validation/phase4_confirmation_suite.py", "Phase 4 causal & matched-control validation"),
            ("research/oi/validation/phase4_costs_and_rankings.py", "backtesting/oi/validation/phase4_costs_and_rankings.py", "Phase 4 transaction costs & ranking models"),
            ("research/oi/validation/walk_forward_engine.py", "backtesting/oi/validation/walk_forward_engine.py", "Phase 3 walk-forward out-of-sample engine"),
            ("research/oi/validation/phase7_shadow_validation.py", "backtesting/oi/validation/phase7_shadow_validation.py", "Phase 7 21-dimension broker shadow validation"),
            ("research/oi/validation/results/", "backtesting/oi/validation/results/", "Phase 2-4 validation metrics and fold outputs"),
        ],
        "execution": [
            ("research/oi/validation/nfo_opening_execution_suite.py", "backtesting/oi/execution/nfo_opening_execution_suite.py", "Phase 6.5 opening auction & implementation shortfall"),
            ("production/execution/paper_walkforward_engine.py", "backtesting/oi/execution/paper_walkforward_engine.py", "Event-driven sequential paper execution engine"),
            ("production/execution/phase6_observation_engine.py", "backtesting/oi/execution/phase6_observation_engine.py", "Phase 6 12-week controlled observation engine"),
        ],
        "portfolio": [
            ("research/oi/backtests/cross_sectional_portfolio.py", "backtesting/oi/portfolio/cross_sectional_portfolio.py", "Phase 3 cross-sectional ranking & Top-K portfolio engine"),
            ("production/risk/risk_engine.py", "backtesting/oi/portfolio/risk_engine.py", "Production institutional risk engine (limits, DD, circuit breakers)"),
            ("research/oi/backtests/results/", "backtesting/oi/portfolio/results/", "Daily portfolio NAV and equity curves"),
        ],
        "reports": [
            ("research/oi/reports/OI_RESEARCH_FINDINGS_REPORT.md", "backtesting/oi/reports/OI_RESEARCH_FINDINGS_REPORT.md", "Phase 1 Executive research findings report"),
            ("research/oi/reports/OI_DATA_AUDIT_REPORT.md", "backtesting/oi/reports/OI_DATA_AUDIT_REPORT.md", "Raw Bhavcopy & data pipeline audit report"),
            ("research/oi/reports/OI_PHASE2_ROBUSTNESS_REPORT.md", "backtesting/oi/reports/OI_PHASE2_ROBUSTNESS_REPORT.md", "Phase 2 40-dimension robustness & falsification report"),
            ("research/oi/reports/OI_PHASE3_WALKFORWARD_PORTFOLIO_REPORT.md", "backtesting/oi/reports/OI_PHASE3_WALKFORWARD_PORTFOLIO_REPORT.md", "Phase 3 walk-forward out-of-sample portfolio report"),
            ("research/oi/reports/OI_PHASE4_SIGNAL_CONFIRMATION_REPORT.md", "backtesting/oi/reports/OI_PHASE4_SIGNAL_CONFIRMATION_REPORT.md", "Phase 4 causal mechanism & matched-pairs report"),
            ("research/oi/reports/OI_PHASE5_PAPER_TRADING_REPORT.md", "backtesting/oi/reports/OI_PHASE5_PAPER_TRADING_REPORT.md", "Phase 5 event-driven paper walk-forward report"),
            ("research/oi/reports/PAPER_BACKTEST_RECONCILIATION_REPORT.md", "backtesting/oi/reports/PAPER_BACKTEST_RECONCILIATION_REPORT.md", "Paper vs. backtest reconciliation report"),
            ("research/oi/reports/OI_PHASE6_CONTROLLED_PAPER_OBSERVATION_REPORT.md", "backtesting/oi/reports/OI_PHASE6_CONTROLLED_PAPER_OBSERVATION_REPORT.md", "Phase 6 12-week controlled observation report"),
            ("research/oi/reports/OI_NFO_SHARES_TEST_REPORT.md", "backtesting/oi/reports/OI_NFO_SHARES_TEST_REPORT.md", "NFO FUTSTK dedicated shares test report"),
            ("research/oi/reports/OI_NFO_OPENING_EXECUTION_REPORT.md", "backtesting/oi/reports/OI_NFO_OPENING_EXECUTION_REPORT.md", "Phase 6.5 opening auction & implementation shortfall report"),
            ("research/oi/reports/OI_PHASE7_SHADOW_READINESS_REPORT.md", "backtesting/oi/reports/OI_PHASE7_SHADOW_READINESS_REPORT.md", "Phase 7 shadow readiness report"),
            ("research/oi/reports/OI_PHASE7_OPENALGO_BRIDGE_REPORT.md", "backtesting/oi/reports/OI_PHASE7_OPENALGO_BRIDGE_REPORT.md", "Phase 7 OpenAlgo strategy bridge & comparison report"),
            ("research/oi/reports/OI_NFO_STATISTICAL_AUDIT.md", "backtesting/oi/reports/OI_NFO_STATISTICAL_AUDIT.md", "Independent statistical audit summary"),
            ("PHASE6_INCIDENT_LOG.md", "backtesting/oi/reports/PHASE6_INCIDENT_LOG.md", "Phase 6 operational incident log"),
            ("PHASE7_INCIDENT_LOG.md", "backtesting/oi/reports/PHASE7_INCIDENT_LOG.md", "Phase 7 operational incident log"),
        ],
        "audit": [
            ("production/audit/OI_NFO_EXECUTION_TRADE_AUDIT.parquet", "backtesting/oi/audit/OI_NFO_EXECUTION_TRADE_AUDIT.parquet", "Phase 6.5 trade execution audit ledger"),
            ("production/audit/OI_NFO_FALSIFICATION_RESULTS.parquet", "backtesting/oi/audit/OI_NFO_FALSIFICATION_RESULTS.parquet", "40-dimension falsification results"),
            ("production/audit/OI_NFO_GAP_DECOMPOSITION.parquet", "backtesting/oi/audit/OI_NFO_GAP_DECOMPOSITION.parquet", "Opening gap vs forward return decomposition"),
            ("production/audit/OI_NFO_IMPLEMENTATION_SHORTFALL.parquet", "backtesting/oi/audit/OI_NFO_IMPLEMENTATION_SHORTFALL.parquet", "Implementation shortfall measurements"),
            ("production/audit/OI_NFO_STOCK_LEVEL_AUDIT.parquet", "backtesting/oi/audit/OI_NFO_STOCK_LEVEL_AUDIT.parquet", "Stock-level audit metrics"),
            ("production/audit/OI_NFO_TRADE_LEVEL_AUDIT.parquet", "backtesting/oi/audit/OI_NFO_TRADE_LEVEL_AUDIT.parquet", "Individual trade-level audit records"),
            ("production/audit/PHASE7_API_LATENCY.parquet", "backtesting/oi/audit/PHASE7_API_LATENCY.parquet", "Phase 7 API request latency measurements"),
            ("production/audit/PHASE7_DAILY_SUMMARY.parquet", "backtesting/oi/audit/PHASE7_DAILY_SUMMARY.parquet", "Phase 7 daily session summary metrics"),
            ("production/audit/PHASE7_EXECUTION_AUDIT.parquet", "backtesting/oi/audit/PHASE7_EXECUTION_AUDIT.parquet", "Phase 7 shadow execution audit records"),
            ("production/audit/PHASE7_RECONCILIATION.parquet", "backtesting/oi/audit/PHASE7_RECONCILIATION.parquet", "Phase 7 broker reconciliation records"),
            ("production/audit/PHASE7_SHADOW_LEDGER.parquet", "backtesting/oi/audit/PHASE7_SHADOW_LEDGER.parquet", "Phase 7 shadow trading ledger"),
            ("production/audit/phase6_candidate_decisions.parquet", "backtesting/oi/audit/phase6_candidate_decisions.parquet", "Phase 6 10,958 candidate decision logs"),
            ("production/audit/phase6_paper_ledger.parquet", "backtesting/oi/audit/phase6_paper_ledger.parquet", "Phase 6 41 executed paper trades ledger"),
            ("production/audit/phase6_portfolio_state.json", "backtesting/oi/audit/phase6_portfolio_state.json", "Phase 6 final portfolio state"),
            ("production/audit/phase7_audit.jsonl", "backtesting/oi/audit/phase7_audit.jsonl", "Phase 7 append-only JSONL audit journal"),
            ("production/audit/phase7_candidate_signals.parquet", "backtesting/oi/audit/phase7_candidate_signals.parquet", "Phase 7 candidate signals parquet"),
            ("production/audit/phase7_forward_shadow_ledger.parquet", "backtesting/oi/audit/phase7_forward_shadow_ledger.parquet", "Phase 7 30-session shadow trade ledger"),
            ("production/audit/phase7_shadow_execution_audit.jsonl", "backtesting/oi/audit/phase7_shadow_execution_audit.jsonl", "Phase 7 shadow execution audit journal"),
            ("production/audit/portfolio_state.json", "backtesting/oi/audit/portfolio_state.json", "Persistent risk engine portfolio state"),
            ("production/audit/paper_trading_ledger.parquet", "backtesting/oi/audit/paper_trading_ledger.parquet", "Phase 5 paper trading ledger"),
            ("production/audit/paper_trading_audit.jsonl", "backtesting/oi/audit/paper_trading_audit.jsonl", "Phase 5 paper trading audit journal"),
            ("production/audit/reconcile_paper_backtest.py", "backtesting/oi/audit/reconcile_paper_backtest.py", "Paper vs backtest reconciliation script"),
        ],
        "artifacts": [
            ("research/oi/backtests/BANKNIFTY_all_trades.csv", "backtesting/oi/artifacts/BANKNIFTY_all_trades.csv", "Index backtest trade records"),
            ("research/oi/backtests/NIFTY_all_trades.csv", "backtesting/oi/artifacts/NIFTY_all_trades.csv", "Index backtest trade records"),
            ("production/audit/purged_walk_forward_partitions.csv", "backtesting/oi/artifacts/purged_walk_forward_partitions.csv", "Purged walk-forward partition definitions"),
            ("production/audit/test_set_friction_scenarios.csv", "backtesting/oi/artifacts/test_set_friction_scenarios.csv", "Multi-scenario friction test results"),
        ],
        "tests": [
            ("production/audit/test_crash_recovery_state.json", "backtesting/oi/tests/test_crash_recovery_state.json", "Crash recovery test state artifact"),
            ("production/audit/phase7_risk_engine_test_state.json", "backtesting/oi/tests/phase7_risk_engine_test_state.json", "Risk engine test state artifact"),
        ],
        "archive": [
            ("research/oi/v1_frozen/", "backtesting/oi/archive/v1_frozen/", "Phase 1 frozen initial research snapshot"),
        ]
    }
    
    total_files = sum(len(items) for items in inventory.values())
    print(f"[*] Total OI Program Artifacts Identified: {total_files} items across 10 functional classifications.\n")
    
    for cat, items in inventory.items():
        print(f"### CATEGORY: {cat.upper()} ({len(items)} items)")
        for orig, dest, desc in items:
            exists_str = "EXISTS" if os.path.exists(orig) else "MISSING"
            print(f"  • [{exists_str:<7}] {orig:<58} ➔ {dest} ({desc})")
        print()
        
    print("=" * 80)
    print("CRITICAL ISOLATION GUARANTEE — FILES THAT WILL NOT BE MOVED")
    print("=" * 80)
    not_moved = [
        ("strategies/liveonopenalgo/oifno.py", "Active OpenAlgo strategy bot for live/shadow execution"),
        ("strategies/scripts/oifno.py", "OpenAlgo CLI strategy execution script"),
        ("strategies/strategy_configs.json", "OpenAlgo strategy configuration registry"),
        ("strategy/oifno.py", "OpenAlgo strategy file root pointer"),
        ("backtesting/emabacktestmcx.py", "Unrelated MCX strategy backtest"),
        ("backtesting/macd_strategy.py", "Unrelated MACD strategy"),
        ("backtesting/macdopen.py", "Unrelated MACD OpenAlgo strategy"),
        ("backtesting/vectorbt_backtest.py", "Unrelated VectorBT test engine"),
        ("backtesting/analytics/", "General OpenAlgo backtesting analytics modules"),
        ("backtesting/models/", "General OpenAlgo backtesting data models"),
        ("backtesting/optimization/", "General OpenAlgo grid search & optimization modules"),
        ("backtesting/portfolio/", "General OpenAlgo portfolio equity modules"),
        ("backtesting/reports/", "General OpenAlgo backtesting report files (MACD, MCX, Silver, Crude)"),
        ("backtesting/risk/", "General OpenAlgo risk configuration modules"),
    ]
    for p, r in not_moved:
        print(f"  🔒 [REMAIN IN PLACE] {p:<45}: {r}")
    print()

    print("=" * 80)
    print("DUPLICATE / SHADOW COPIES IDENTIFIED")
    print("=" * 80)
    duplicates = [
        ("SIG-OI-001-PAPER-V1.md", ["Root workspace", "production/signal/SIG-OI-001-PAPER-V1.md"]),
        ("risk_engine.py", ["Root workspace", "production/risk/risk_engine.py"]),
        ("paper_walkforward_engine.py", ["Root workspace", "production/execution/paper_walkforward_engine.py"]),
        ("paper_trading_ledger.parquet", ["Root workspace", "production/audit/paper_trading_ledger.parquet"]),
        ("paper_trading_audit.jsonl", ["Root workspace", "production/audit/paper_trading_audit.jsonl"]),
        ("OI_NFO_OPENING_EXECUTION_REPORT.md", ["Root workspace", "research/oi/reports/OI_NFO_OPENING_EXECUTION_REPORT.md"]),
        ("PAPER_BACKTEST_RECONCILIATION_REPORT.md", ["Root workspace", "research/oi/reports/PAPER_BACKTEST_RECONCILIATION_REPORT.md"]),
        ("OI_PHASE7_OPENALGO_BRIDGE_REPORT.md", ["Root workspace", "research/oi/reports/OI_PHASE7_OPENALGO_BRIDGE_REPORT.md"]),
        ("OI_PHASE7_SHADOW_READINESS_REPORT.md", ["Root workspace", "research/oi/reports/OI_PHASE7_SHADOW_READINESS_REPORT.md"]),
    ]
    for name, locs in duplicates:
        print(f"  ⚠️ Duplicate: {name:<38} in {locs}")
    print("\n[!] INVENTORY COMPLETE. Relocation requires explicit user approval before execution.\n")


def main():
    parser = argparse.ArgumentParser(description="AGY Futures OI Auto-Research Orchestrator")
    parser.add_argument("--mode", choices=[
        "status", "audit", "pipeline", "eda", "test-hypotheses", 
        "walk-forward", "portfolio", "phase3",
        "phase5", "paper", "reconcile", "risk", "phase6", "nfo-robustness", "nfo-execution", "phase7",
        "oi-inventory", "nfo-full-backtest"
    ], default="status", help="Execution mode")
    parser.add_argument("--symbol", default="NIFTY", help="Target symbol for analysis")
    parser.add_argument("--start", default="2022-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2024-07-31", help="End date (YYYY-MM-DD)")

    args = parser.parse_args()

    if args.mode == "oi-inventory":
        run_oi_inventory()
    elif args.mode == "status":
        run_status()
    elif args.mode == "audit":
        run_audit()
    elif args.mode == "pipeline":
        run_pipeline(args.start, args.end)
    elif args.mode == "eda":
        run_eda(args.symbol)
    elif args.mode == "test-hypotheses":
        print("[*] Running statistical tests on registered hypotheses...")
        from backtesting.oi.validation.exploratory_analysis import run_full_eda
        for sym in ["NIFTY", "BANKNIFTY"]:
            run_eda(sym)
    elif args.mode == "walk-forward":
        print("[*] Launching Phase 3: Walk-Forward Out-Of-Sample Validation Engine...")
        from backtesting.oi.validation.walk_forward_engine import main as run_wf
        run_wf()
    elif args.mode == "portfolio":
        print("[*] Launching Phase 3: Cross-Sectional Portfolio Simulation Engine...")
        from backtesting.oi.portfolio.cross_sectional_portfolio import main as run_port
        run_port()
    elif args.mode == "phase3":
        print("[*] Launching Complete Phase 3 Multi-Year Research Pipeline...")
        from backtesting.oi.validation.walk_forward_engine import main as run_wf
        from backtesting.oi.portfolio.cross_sectional_portfolio import main as run_port
        run_wf()
        run_port()
    elif args.mode == "risk":
        print("[*] Launching Production Risk Engine Diagnostics...")
        from backtesting.oi.portfolio.risk_engine import main as run_risk
        run_risk()
    elif args.mode == "paper":
        print("[*] Launching Production Event-Driven Paper Walk-Forward Engine...")
        from backtesting.oi.execution.paper_walkforward_engine import main as run_paper
        run_paper()
    elif args.mode == "reconcile":
        print("[*] Launching Production Paper vs. Backtest Reconciliation...")
        from backtesting.oi.audit.reconcile_paper_backtest import run_reconciliation
        run_reconciliation()
    elif args.mode == "phase5":
        print("[*] Launching Complete Phase 5 Production & Paper Trading Suite...")
        from backtesting.oi.portfolio.risk_engine import main as run_risk
        from backtesting.oi.execution.paper_walkforward_engine import main as run_paper
        from backtesting.oi.audit.reconcile_paper_backtest import run_reconciliation
        run_risk()
        run_paper()
        run_reconciliation()
    elif args.mode == "phase6":
        print("[*] Launching AGY Phase 6: 12-Week Controlled Paper Trading Observation...")
        from backtesting.oi.execution.phase6_observation_engine import run_phase6
        run_phase6()
    elif args.mode == "nfo-robustness":
        print("[*] Launching AGY NFO FUTSTK Deep Falsification & Robustness Suite (40 Tests)...")
        from backtesting.oi.validation.nfo_deep_falsification_suite import main as run_nfo_falsification
        run_nfo_falsification()
    elif args.mode == "nfo-execution":
        print("[*] Launching Phase 6.5: NFO Opening-Auction & Implementation-Shortfall Validation...")
        from backtesting.oi.execution.nfo_opening_execution_suite import run_phase_6_5_execution_validation
        run_phase_6_5_execution_validation()
    elif args.mode == "phase7":
        print("[*] Launching Phase 7: NFO OI Broker & Live-Readiness Shadow Validation...")
        from backtesting.oi.validation.phase7_shadow_validation import run_phase_7
        run_phase_7()
    elif args.mode == "nfo-full-backtest":
        print("[*] Launching NFO Full Historical Backtest Engine (2022–Latest)...")
        from backtesting.oi.validation.nfo_full_backtest.scripts.nfo_full_backtest_engine import execute_full_backtest_pipeline
        execute_full_backtest_pipeline()
    elif args.mode == "phase3":
        print("[*] Launching Complete Phase 3 Multi-Year Research Pipeline...")
        from backtesting.oi.validation.walk_forward_engine import main as run_wf
        from backtesting.oi.portfolio.cross_sectional_portfolio import main as run_port
        run_wf()
        run_port()
    elif args.mode == "risk":
        print("[*] Launching Production Risk Engine Diagnostics...")
        from backtesting.oi.portfolio.risk_engine import main as run_risk
        run_risk()
    elif args.mode == "paper":
        print("[*] Launching Production Event-Driven Paper Walk-Forward Engine...")
        from backtesting.oi.execution.paper_walkforward_engine import main as run_paper
        run_paper()
    elif args.mode == "reconcile":
        print("[*] Launching Production Paper vs. Backtest Reconciliation...")
        from backtesting.oi.audit.reconcile_paper_backtest import run_reconciliation
        run_reconciliation()
    elif args.mode == "phase5":
        print("[*] Launching Complete Phase 5 Production & Paper Trading Suite...")
        from backtesting.oi.portfolio.risk_engine import main as run_risk
        from backtesting.oi.execution.paper_walkforward_engine import main as run_paper
        from backtesting.oi.audit.reconcile_paper_backtest import run_reconciliation
        run_risk()
        run_paper()
        run_reconciliation()
    elif args.mode == "phase6":
        print("[*] Launching AGY Phase 6: 12-Week Controlled Paper Trading Observation...")
        from backtesting.oi.execution.phase6_observation_engine import run_phase6
        run_phase6()
    elif args.mode == "nfo-robustness":
        print("[*] Launching AGY NFO FUTSTK Deep Falsification & Robustness Suite (40 Tests)...")
        from backtesting.oi.validation.nfo_deep_falsification_suite import main as run_nfo_falsification
        run_nfo_falsification()
    elif args.mode == "nfo-execution":
        print("[*] Launching Phase 6.5: NFO Opening-Auction & Implementation-Shortfall Validation...")
        from backtesting.oi.execution.nfo_opening_execution_suite import run_phase_6_5_execution_validation
        run_phase_6_5_execution_validation()
    elif args.mode == "phase7":
        print("[*] Launching Phase 7: NFO OI Broker & Live-Readiness Shadow Validation...")
        from backtesting.oi.validation.phase7_shadow_validation import run_phase_7
        run_phase_7()


if __name__ == "__main__":
    main()
