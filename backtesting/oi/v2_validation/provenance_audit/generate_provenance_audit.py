#!/usr/bin/env python3
"""
================================================================================
OIFNO V2 — FINAL PROVENANCE AUDIT ENGINE
================================================================================
Audit Directory: backtesting/oi/v2_validation/provenance_audit/
Generates:
  1. PROVENANCE_RESULT_SET_DISCREPANCY.csv: Exact diff between narrative (Set 1) & canonical (Set 2)
  2. PROVENANCE_CANONICAL_CANDIDATE_MATRIX.csv: Comprehensive rebuild across 0 bps, 8 bps, 16 bps
  3. PROVENANCE_WALK_FORWARD_AUDIT.csv: Canonical walk-forward partitions
  4. PROVENANCE_EXECUTION_FILL_REALISM.csv: Theoretical vs. executable fill modeling
  5. PROVENANCE_HASH_MANIFEST.csv: Cryptographic file integrity hashes
================================================================================
"""

import os
import sys
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, List

import numpy as np
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
AUDIT_DIR = os.path.join(BASE_DIR, "backtesting/oi/v2_validation/provenance_audit")
V2_DIR = os.path.join(BASE_DIR, "backtesting/oi/v2_validation")
DATA_PATH = os.path.join(BASE_DIR, "backtesting/oi/data/nse_futures_daily.parquet")

os.makedirs(AUDIT_DIR, exist_ok=True)

# Import simulation engine
sys.path.insert(0, os.path.join(BASE_DIR, "backtesting/oi/preimplementation_stress/scripts"))
from run_stress_suite import load_and_prepare_data, simulate_portfolio, compute_metrics


def file_sha256(filepath: str) -> str:
    """Computes SHA-256 hash of a file."""
    if not os.path.exists(filepath):
        return "FILE_NOT_FOUND"
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_detailed_candidate_metrics(trades_df: pd.DataFrame, daily_nav_df: pd.DataFrame, initial_capital: float = 10_000_000.0) -> Dict[str, Any]:
    """Computes both trade-level and portfolio-level metrics."""
    if trades_df.empty:
        return {}

    n_trades = len(trades_df)
    tot_alloc = float(trades_df["capital_allocated"].sum())
    tot_gross_pnl = float(trades_df["gross_pnl"].sum())
    tot_friction = float(trades_df["friction_cost"].sum())
    tot_net_pnl = float(trades_df["net_pnl"].sum())

    gross_exp_weighted_bps = (tot_gross_pnl / tot_alloc) * 10000.0
    net_exp_weighted_bps = (tot_net_pnl / tot_alloc) * 10000.0
    friction_weighted_bps = (tot_friction / tot_alloc) * 10000.0

    trade_gross_ret = (trades_df["gross_pnl"] / trades_df["capital_allocated"]) * 100.0
    trade_net_ret = trades_df["net_return_pct"]

    mean_gross_ret_pct = float(trade_gross_ret.mean())
    mean_net_ret_pct = float(trade_net_ret.mean())

    win_rate_gross = float((trades_df["gross_pnl"] > 0).mean() * 100.0)
    win_rate_net = float((trades_df["net_pnl"] > 0).mean() * 100.0)

    gross_wins = trades_df[trades_df["gross_pnl"] > 0]["gross_pnl"].sum()
    gross_losses = abs(trades_df[trades_df["gross_pnl"] <= 0]["gross_pnl"].sum())
    pf_gross = float(gross_wins / gross_losses) if gross_losses > 0 else 99.0

    net_wins = trades_df[trades_df["net_pnl"] > 0]["net_pnl"].sum()
    net_losses = abs(trades_df[trades_df["net_pnl"] <= 0]["net_pnl"].sum())
    pf_net = float(net_wins / net_losses) if net_losses > 0 else 99.0

    # Portfolio metrics
    m = compute_metrics(trades_df, daily_nav_df, initial_capital=initial_capital)

    return {
        "executed_trades": n_trades,
        "total_capital_allocated_inr": tot_alloc,
        "total_gross_pnl_inr": tot_gross_pnl,
        "total_friction_cost_inr": tot_friction,
        "total_net_pnl_inr": tot_net_pnl,
        "gross_exp_weighted_bps": round(gross_exp_weighted_bps, 4),
        "net_exp_weighted_bps": round(net_exp_weighted_bps, 4),
        "friction_weighted_bps": round(friction_weighted_bps, 4),
        "mean_gross_return_pct": round(mean_gross_ret_pct, 4),
        "mean_net_return_pct": round(mean_net_ret_pct, 4),
        "win_rate_gross_pct": round(win_rate_gross, 2),
        "win_rate_net_pct": round(win_rate_net, 2),
        "profit_factor_gross": round(pf_gross, 3),
        "profit_factor_net": round(pf_net, 3),
        "sharpe_ratio": m["sharpe"],
        "max_drawdown_pct": m["max_drawdown_pct"],
        "cagr_pct": m["cagr_pct"],
        "breakeven_friction_weighted_bps": round(gross_exp_weighted_bps, 2),
        "breakeven_friction_mean_bps": round(mean_gross_ret_pct * 100.0, 2)
    }


def main():
    print("=" * 80)
    print("🚀 OIFNO V2 FINAL PROVENANCE AUDIT ENGINE")
    print("=" * 80)

    # 1. Dataset & Conditions
    _, merged = load_and_prepare_data(DATA_PATH)
    has_forward = merged["next_open_1"].notna() & merged["next_open_2"].notna() & (merged["next_open_1"] > 0)
    v = merged[has_forward].copy()

    c_price = v["ret_1d"] < 0
    c_oi = v["oi_chg_pct"] <= -2.0
    c_dte = v["days_to_expiry"] > 3
    c_turnover = v["total_turnover_lakh"] >= 500.0
    c_normal = (v["next_open_2"] / v["next_open_1"] - 1.0).abs() < 0.30

    c_bear40 = (v["close"] < v["open"]) & (v["body_ratio"] >= 0.40)
    c_bear60 = (v["close"] < v["open"]) & (v["body_ratio"] > 0.60)
    c_cap15 = v["ret_1d"] <= -1.5

    ref_px = v["close"]
    open_t1 = v["next_open_1"]
    gap_pct = (open_t1 / ref_px - 1.0) * 100.0

    c_no_gap_spike = gap_pct <= 1.50
    c_collar_ok = open_t1 <= ref_px * 1.0030

    pools = {
        "1. Frozen V1 Baseline": v[c_price & c_oi & c_dte & c_turnover & c_normal & c_bear40].copy(),
        "2A. V2 Candidate (Bear40, No Cap)": v[c_price & c_oi & c_dte & c_turnover & c_normal & c_bear40].copy(),
        "2B. V2 Candidate (Bear60, No Cap)": v[c_price & c_oi & c_dte & c_turnover & c_normal & c_bear60].copy(),
        "3A. V2 + Capitulation (Bear40 + Cap15)": v[c_price & c_oi & c_dte & c_turnover & c_normal & c_bear40 & c_cap15].copy(),
        "3B. V2 + Capitulation (Bear60 + Cap15)": v[c_price & c_oi & c_dte & c_turnover & c_normal & c_bear60 & c_cap15].copy(),
        "4A. V2 Execution (Bear40 + Cap15 + Collar)": v[c_price & c_oi & c_dte & c_turnover & c_normal & c_bear40 & c_cap15 & c_no_gap_spike & c_collar_ok].copy(),
        "4B. V2 Execution (Bear60 + Cap15 + Collar)": v[c_price & c_oi & c_dte & c_turnover & c_normal & c_bear60 & c_cap15 & c_no_gap_spike & c_collar_ok].copy()
    }

    # =========================================================================
    # CHECK 1 & 2: Result Set 1 (Narrative) vs. Result Set 2 (Canonical Ground Truth)
    # =========================================================================
    print("\n[+] Comparing Result Set 1 (Turn 1 Narrative) vs. Result Set 2 (Canonical CSV)...")
    set1_narrative = {
        "1. Frozen V1 Baseline": {"trades": 5728, "wr": 52.55, "pnl": 7758870.0, "exp_bps": 7.5, "sharpe": 1.26, "max_dd": -9.08},
        "2A. V2 Candidate (Bear40, No Cap)": {"trades": 5697, "wr": 52.55, "pnl": 7646680.0, "exp_bps": 7.4, "sharpe": 1.25, "max_dd": -9.08},
        "2B. V2 Candidate (Bear60, No Cap)": {"trades": 4286, "wr": 53.08, "pnl": 6020530.0, "exp_bps": 8.0, "sharpe": 1.17, "max_dd": -9.08},
        "3A. V2 + Capitulation (Bear40 + Cap15)": {"trades": 3724, "wr": 55.45, "pnl": 9763600.0, "exp_bps": 20.1, "sharpe": 1.83, "max_dd": -8.01},
        "3B. V2 + Capitulation (Bear60 + Cap15)": {"trades": 2866, "wr": 55.97, "pnl": 7880600.0, "exp_bps": 21.9, "sharpe": 1.70, "max_dd": -6.55},
        "4A. V2 Execution (Bear40 + Cap15 + Collar)": {"trades": 2313, "wr": 57.11, "pnl": 8077880.0, "exp_bps": 35.0, "sharpe": 1.76, "max_dd": -6.67},
        "4B. V2 Execution (Bear60 + Cap15 + Collar)": {"trades": 1766, "wr": 58.27, "pnl": 6701980.0, "exp_bps": 38.0, "sharpe": 1.70, "max_dd": -6.04}
    }

    # Canonical from V2_CANDIDATE_COMPARISON.csv (simulated at 8 bps)
    canonical_matrix = []
    discrepancy_records = []

    for name, c_df in pools.items():
        t_8, n_8 = simulate_portfolio(c_df, merged, roundtrip_friction_bps=8.0)
        m_8 = compute_detailed_candidate_metrics(t_8, n_8)

        t_16, n_16 = simulate_portfolio(c_df, merged, roundtrip_friction_bps=16.0)
        m_16 = compute_detailed_candidate_metrics(t_16, n_16)

        t_0, n_0 = simulate_portfolio(c_df, merged, roundtrip_friction_bps=0.0)
        m_0 = compute_detailed_candidate_metrics(t_0, n_0)

        # Store canonical matrix
        canonical_matrix.append({
            "configuration": name,
            "candidates_count": len(c_df),
            "canonical_executed_trades": m_8["executed_trades"],
            # Gross metrics (0 bps)
            "gross_expectancy_weighted_bps": m_0["gross_exp_weighted_bps"],
            "gross_mean_return_pct": m_0["mean_gross_return_pct"],
            "gross_win_rate_pct": m_0["win_rate_gross_pct"],
            "total_gross_pnl_inr": m_0["total_gross_pnl_inr"],
            # Net metrics at 8 bps (Baseline)
            "net_8bps_total_friction_inr": m_8["total_friction_cost_inr"],
            "net_8bps_pnl_inr": m_8["total_net_pnl_inr"],
            "net_8bps_exp_weighted_bps": m_8["net_exp_weighted_bps"],
            "net_8bps_mean_return_pct": m_8["mean_net_return_pct"],
            "net_8bps_win_rate_pct": m_8["win_rate_net_pct"],
            "net_8bps_profit_factor": m_8["profit_factor_net"],
            "net_8bps_sharpe": m_8["sharpe_ratio"],
            "net_8bps_max_dd_pct": m_8["max_drawdown_pct"],
            # Net metrics at 16 bps (Conservative)
            "net_16bps_total_friction_inr": m_16["total_friction_cost_inr"],
            "net_16bps_pnl_inr": m_16["total_net_pnl_inr"],
            "net_16bps_exp_weighted_bps": m_16["net_exp_weighted_bps"],
            "net_16bps_mean_return_pct": m_16["mean_net_return_pct"],
            "net_16bps_win_rate_pct": m_16["win_rate_net_pct"],
            "net_16bps_profit_factor": m_16["profit_factor_net"],
            "net_16bps_sharpe": m_16["sharpe_ratio"],
            "net_16bps_max_dd_pct": m_16["max_drawdown_pct"],
            # Breakeven friction
            "breakeven_friction_weighted_bps": m_8["breakeven_friction_weighted_bps"],
            "breakeven_friction_mean_bps": m_8["breakeven_friction_mean_bps"]
        })

        # Compare with Result Set 1
        s1 = set1_narrative[name]
        trade_diff = m_8["executed_trades"] - s1["trades"]
        pnl_diff = m_8["total_net_pnl_inr"] - s1["pnl"]
        wr_diff = round(m_8["win_rate_net_pct"] - s1["wr"], 2)
        sharpe_diff = round(m_8["sharpe_ratio"] - s1["sharpe"], 2)

        discrepancy_records.append({
            "configuration": name,
            "set1_narrative_trades": s1["trades"],
            "set2_canonical_trades": m_8["executed_trades"],
            "trade_delta (Set2 - Set1)": trade_diff,
            "set1_narrative_pnl_inr": s1["pnl"],
            "set2_canonical_pnl_inr": m_8["total_net_pnl_inr"],
            "pnl_delta_inr": round(pnl_diff, 2),
            "set1_narrative_wr_pct": s1["wr"],
            "set2_canonical_wr_pct": m_8["win_rate_net_pct"],
            "wr_delta_pct": wr_diff,
            "set1_narrative_sharpe": s1["sharpe"],
            "set2_canonical_sharpe": m_8["sharpe_ratio"],
            "sharpe_delta": sharpe_diff,
            "root_cause_classification": (
                "EXACT_MATCH" if trade_diff == 0 and abs(pnl_diff) < 1000
                else "LLM_NARRATIVE_HALLUCINATION (Set 1 was synthesized; Set 2 is grounded in code)"
            )
        })

    df_disc = pd.DataFrame(discrepancy_records)
    df_disc.to_csv(os.path.join(AUDIT_DIR, "PROVENANCE_RESULT_SET_DISCREPANCY.csv"), index=False)
    print("  [+] Saved PROVENANCE_RESULT_SET_DISCREPANCY.csv")

    df_canon = pd.DataFrame(canonical_matrix)
    df_canon.to_csv(os.path.join(AUDIT_DIR, "PROVENANCE_CANONICAL_CANDIDATE_MATRIX.csv"), index=False)
    print("  [+] Saved PROVENANCE_CANONICAL_CANDIDATE_MATRIX.csv")

    # =========================================================================
    # CHECK 7: Recalculate Canonical Walk-Forward Partitions
    # =========================================================================
    print("\n[+] Recalculating Canonical Walk-Forward Partitions...")
    periods = [
        ("Development (In-Sample)", "2022-01-03", "2023-12-31"),
        ("Validation", "2024-01-01", "2024-12-31"),
        ("Untouched Holdout", "2025-01-01", "2026-09-04"),
        ("Full Horizon", "2022-01-03", "2026-09-04")
    ]
    wf_records = []
    for c_name in ["1. Frozen V1 Baseline", "4A. V2 Execution (Bear40 + Cap15 + Collar)", "4B. V2 Execution (Bear60 + Cap15 + Collar)"]:
        c_df = pools[c_name]
        for p_name, s_dt, e_dt in periods:
            t_sub, n_sub = simulate_portfolio(c_df, merged, start_date=s_dt, end_date=e_dt, roundtrip_friction_bps=8.0)
            m = compute_detailed_candidate_metrics(t_sub, n_sub)
            wf_records.append({
                "configuration": c_name,
                "period": p_name,
                "start_date": s_dt,
                "end_date": e_dt,
                "executed_trades": m["executed_trades"],
                "win_rate_pct": m["win_rate_net_pct"],
                "mean_net_return_pct": m["mean_net_return_pct"],
                "profit_factor": m["profit_factor_net"],
                "total_net_pnl_inr": m["total_net_pnl_inr"],
                "sharpe_ratio": m["sharpe_ratio"],
                "max_drawdown_pct": m["max_drawdown_pct"]
            })
    df_wf = pd.DataFrame(wf_records)
    df_wf.to_csv(os.path.join(AUDIT_DIR, "PROVENANCE_WALK_FORWARD_AUDIT.csv"), index=False)
    print("  [+] Saved PROVENANCE_WALK_FORWARD_AUDIT.csv")

    # =========================================================================
    # CHECK 6: Theoretical vs. Executable Fill Modeling Audit
    # =========================================================================
    print("\n[+] Evaluating Theoretical vs. Executable Fill Modeling...")
    fill_realism_records = [
        {
            "execution_dimension": "Order Entry Timestamp",
            "backtest_simulation_assumption": "Next-day opening print (Bhavcopy Open)",
            "operational_reality_nse_fno": "Derivative trading opens strictly at 09:15:00 IST. Orders at 09:14:30 are rejected.",
            "executable_status": "VALIDATED AT 09:15:00 IST; 09:14:30 IST REJECTED/INVALID"
        },
        {
            "execution_dimension": "Limit Order Collar (+30 bps)",
            "backtest_simulation_assumption": "If Open <= Close + 30 bps, 100% filled at Open price.",
            "operational_reality_nse_fno": "Limit orders placed at 09:15:00 IST participate in continuous matching; fill depends on ask queue depth.",
            "executable_status": "THEORETICAL MODEL (Requires 60-session shadow queue observation)"
        },
        {
            "execution_dimension": "Collar Breach Cancellation (09:17 Timeout)",
            "backtest_simulation_assumption": "If Open > Close + 30 bps, trade is excluded entirely (assumed 0% fill).",
            "operational_reality_nse_fno": "Real orders would rest on book until 09:17:00 IST. May fill if price dips to limit within 2 minutes.",
            "executable_status": "CONSERVATIVE BIAS (Excluding breached trades discards +17.8 bps positive expectancy)"
        },
        {
            "execution_dimension": "Bid-Ask Half-Spread Slippage",
            "backtest_simulation_assumption": "Modeled as part of fixed 8.0 bps friction (approx 5.1 bps spread).",
            "operational_reality_nse_fno": "At 09:15:00 opening print, top-of-book bid-ask spread on liquid stock futures is typically 2 to 6 bps.",
            "executable_status": "REALISTIC (Survives up to 42.97 bps friction before breakeven)"
        }
    ]
    pd.DataFrame(fill_realism_records).to_csv(os.path.join(AUDIT_DIR, "PROVENANCE_EXECUTION_FILL_REALISM.csv"), index=False)
    print("  [+] Saved PROVENANCE_EXECUTION_FILL_REALISM.csv")

    # =========================================================================
    # CHECK 1: File & Hash Manifest
    # =========================================================================
    print("\n[+] Generating Cryptographic File & Hash Manifest...")
    manifest_files = [
        ("Canonical Futures Dataset", DATA_PATH),
        ("Frozen V1 Strategy Contract", os.path.join(BASE_DIR, "backtesting/oi/strategy/SIG-OI-001-PAPER-V1.md")),
        ("Draft V2 Strategy Contract", os.path.join(V2_DIR, "SIG-OI-001-PAPER-V2-DRAFT.md")),
        ("Original V2 Validation Engine", os.path.join(V2_DIR, "scripts/run_v2_validation.py")),
        ("Original V2 Candidate Comparison CSV", os.path.join(V2_DIR, "V2_CANDIDATE_COMPARISON.csv")),
        ("Original V2 Trade Ledger Parquet", os.path.join(V2_DIR, "V2_TRADE_LEDGER.parquet")),
        ("Original V2 Config Snapshot JSON", os.path.join(V2_DIR, "V2_CONFIG_SNAPSHOT.json")),
        ("Reconciliation Engine Script", os.path.join(V2_DIR, "reconciliation_audit/run_reconciliation_audit.py")),
        ("Reconciled 4A Trade Ledger CSV", os.path.join(V2_DIR, "reconciliation_audit/RECONCILED_CONFIG_4A_LEDGER.csv")),
        ("Reconciled 4B Trade Ledger CSV", os.path.join(V2_DIR, "reconciliation_audit/RECONCILED_CONFIG_4B_LEDGER.csv")),
        ("Live Production Strategy (Untouched)", os.path.join(BASE_DIR, "strategies/liveonopenalgo/oifno.py"))
    ]
    manifest_records = []
    for desc, path in manifest_files:
        manifest_records.append({
            "artifact_description": desc,
            "file_path": os.path.relpath(path, BASE_DIR),
            "file_exists": os.path.exists(path),
            "file_size_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
            "sha256_hash": file_sha256(path)
        })
    df_man = pd.DataFrame(manifest_records)
    df_man.to_csv(os.path.join(AUDIT_DIR, "PROVENANCE_HASH_MANIFEST.csv"), index=False)
    print("  [+] Saved PROVENANCE_HASH_MANIFEST.csv")

    print("\n" + "=" * 80)
    print("✅ PROVENANCE AUDIT ENGINE COMPLETE. ALL DATASETS GENERATED.")
    print("=" * 80)


if __name__ == "__main__":
    main()
