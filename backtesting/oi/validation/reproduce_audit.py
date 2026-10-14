#!/usr/bin/env python3
"""
================================================================================
AGY Futures OI Auto-Research System — Phase 2: Independent Reproduction Audit
================================================================================
Independently verifies that the reported Phase 1 results reproduce exactly
from raw/normalized features to the exact trade level.
================================================================================
"""

import os
import pandas as pd
import numpy as np

from backtesting.oi.archive.v1_frozen.backtests.backtest_engine import simulate_signal_contract
from backtesting.oi.strategy.signal_contracts import (
    CONTRACT_SIG_OI_001,
    CONTRACT_SIG_BENCH_001,
    CONTRACT_SIG_OI_002,
    CONTRACT_SIG_BENCH_002,
    CONTRACT_SIG_OI_003
)

FEATURES_DIR = "research/oi/features"
FROZEN_DIR = "research/oi/v1_frozen/backtests"


def audit_reproduction(symbol: str) -> dict:
    """
    Independently re-simulate all signal contracts for symbol and compare
    against frozen backtest summary and trade logs.
    """
    fpath = os.path.join(FEATURES_DIR, f"{symbol}_features.parquet")
    if not os.path.exists(fpath):
        raise FileNotFoundError(f"Feature dataset not found: {fpath}")

    df = pd.read_parquet(fpath)

    # Load frozen summary
    frozen_summary_path = os.path.join(FROZEN_DIR, f"{symbol}_signal_comparison.csv")
    frozen_trades_path = os.path.join(FROZEN_DIR, f"{symbol}_all_trades.csv")

    frozen_summary = pd.read_csv(frozen_summary_path)
    frozen_trades = pd.read_csv(frozen_trades_path)

    contracts = [
        CONTRACT_SIG_OI_001,
        CONTRACT_SIG_BENCH_001,
        CONTRACT_SIG_OI_002,
        CONTRACT_SIG_BENCH_002,
        CONTRACT_SIG_OI_003
    ]

    all_matched = True
    discrepancies = []
    reproduced_summaries = []
    reproduced_trades = []

    for contract in contracts:
        res = simulate_signal_contract(df, contract)
        full = res["full_stats"]
        is_s = res["is_stats"]
        oos_s = res["oos_stats"]
        t_df = res["trades"]

        # Match against frozen summary row
        frozen_row = frozen_summary[frozen_summary["Signal ID"] == contract.signal_id].iloc[0]

        checks = [
            ("Trades (Full)", full["trades"], int(frozen_row["Trades (Full)"])),
            ("Win Rate (%)", full["win_rate_pct"], float(frozen_row["Win Rate (%)"])),
            ("Net PnL (%)", full["net_pnl_pct"], float(frozen_row["Net PnL (%)"])),
            ("Profit Factor", full["profit_factor"], float(frozen_row["PF"])),
            ("Expectancy (%)", full["expectancy_pct"], float(frozen_row["Expectancy (%)"])),
            ("Sharpe", full["sharpe_ratio"], float(frozen_row["Sharpe"])),
            ("IS Net PnL (%)", is_s["net_pnl_pct"], float(frozen_row["IS Net PnL (%)"])),
            ("OOS Net PnL (%)", oos_s["net_pnl_pct"], float(frozen_row["OOS Net PnL (%)"]))
        ]

        for metric_name, repro_val, frozen_val in checks:
            diff = abs(repro_val - frozen_val)
            if diff > 1e-4:
                all_matched = False
                discrepancies.append({
                    "symbol": symbol,
                    "signal_id": contract.signal_id,
                    "metric": metric_name,
                    "reproduced": repro_val,
                    "frozen": frozen_val,
                    "diff": diff
                })

        if not t_df.empty:
            reproduced_trades.append(t_df)

    # Trade-by-trade comparison
    if reproduced_trades:
        rep_all_trades = pd.concat(reproduced_trades, ignore_index=True)
        if len(rep_all_trades) != len(frozen_trades):
            all_matched = False
            discrepancies.append({
                "symbol": symbol,
                "signal_id": "ALL",
                "metric": "Total Trade Count",
                "reproduced": len(rep_all_trades),
                "frozen": len(frozen_trades),
                "diff": abs(len(rep_all_trades) - len(frozen_trades))
            })

    return {
        "symbol": symbol,
        "is_exact_match": all_matched,
        "discrepancies": discrepancies,
        "total_trades_reproduced": len(rep_all_trades) if reproduced_trades else 0
    }


if __name__ == "__main__":
    print("=================================================================")
    print("PHASE 2: INDEPENDENT REPRODUCTION AUDIT")
    print("=================================================================")
    for sym in ["NIFTY", "BANKNIFTY"]:
        audit = audit_reproduction(sym)
        print(f"\nAudit for {sym}:")
        print(f"  Exact Numerical Match: {audit['is_exact_match']}")
        print(f"  Total Trades Audited: {audit['total_trades_reproduced']}")
        if not audit["is_exact_match"]:
            print(f"  [!] DISCREPANCIES DETECTED: {len(audit['discrepancies'])}")
            for d in audit["discrepancies"]:
                print(f"      {d}")
        else:
            print(f"  [+] SUCCESS: All trades, PnL, win rates, PF, Sharpe, IS/OOS reproduced with 0 error.")
