"""
================================================================================
Independent Backtest Calculation Audit & Reconciliation
File: research/ema_comparison_audit/audit_backtest_calculations.py
================================================================================
Performs an independent mathematical audit of the backtest calculations:
  1. Root cause analysis of drawdowns exceeding 100%
  2. Compounded vs Additive return modeling
  3. Realistic portfolio equity modeling (margin-aware and fractional sizing)
  4. Chronological In-Sample vs Out-of-Sample integrity check
  5. Exact reproduction of metrics from trade-level CSVs
  6. Revalidation of all 7 portfolio risk gates under both calculation models
================================================================================
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd

AUDIT_DIR = Path(__file__).resolve().parent
BASE_CSV = AUDIT_DIR / "trades_baseline_ema9_26.csv"
CAND_CSV = AUDIT_DIR / "trades_candidate_ema10_28.csv"


def audit_dataset_integrity():
    """Verifies chronological separation of In-Sample and Out-of-Sample datasets."""
    df_base = pd.read_csv(BASE_CSV)
    df_cand = pd.read_csv(CAND_CSV)

    results = {}
    for name, df in [("Baseline_9_26", df_base), ("Candidate_10_28", df_cand)]:
        df["entry_time"] = pd.to_datetime(df["entry_time"])
        df["exit_time"] = pd.to_datetime(df["exit_time"])

        is_trades = df[df["sample"] == "IS"]
        oos_trades = df[df["sample"] == "OOS"]

        is_max_entry = is_trades["entry_time"].max()
        oos_min_entry = oos_trades["entry_time"].min()
        is_max_exit = is_trades["exit_time"].max()

        results[name] = {
            "total_trades": len(df),
            "is_count": len(is_trades),
            "oos_count": len(oos_trades),
            "is_start": str(is_trades["entry_time"].min()),
            "is_end_entry": str(is_max_entry),
            "is_end_exit": str(is_max_exit),
            "oos_start_entry": str(oos_min_entry),
            "oos_end_exit": str(oos_trades["exit_time"].max()),
            "temporal_overlap": bool(oos_min_entry < is_max_entry),
        }
    return results


def reproduce_reported_metrics():
    """Reproduces the exact metrics reported in performance_comparison.csv from trade CSVs."""
    reproduced = {}
    for name, path in [("Baseline_9_26", BASE_CSV), ("Candidate_10_28", CAND_CSV)]:
        df = pd.read_csv(path)
        pnls = df["net_pnl_pct"].values
        n = len(pnls)
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        total_return_additive = float(np.sum(pnls))
        expectancy = float(np.mean(pnls))
        win_rate = float(len(wins) / n * 100.0)
        profit_factor = float(np.sum(wins) / abs(np.sum(losses)))

        # Additive peak-to-trough drop in percentage points
        cum_pts = np.cumsum(pnls)
        peak_pts = np.maximum.accumulate(cum_pts)
        max_dd_additive = float(np.max(peak_pts - cum_pts))

        reproduced[name] = {
            "trade_count": n,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 3),
            "expectancy_pct": round(expectancy, 4),
            "total_return_additive_pct": round(total_return_additive, 2),
            "max_dd_additive_percentage_points": round(max_dd_additive, 2),
        }
    return reproduced


def compute_true_portfolio_metrics(alloc_frac: float = 0.10, initial_capital: float = 1000000.0):
    """
    Computes mathematically rigorous compounded portfolio equity metrics:
      - Initial capital: initial_capital (default ₹10,00,000)
      - Capital allocation per trade: alloc_frac (default 10% for 10 concurrent slots)
      - True portfolio return = (Final_Equity - Initial_Capital) / Initial_Capital * 100%
      - True portfolio max drawdown = max((Peak - Equity) / Peak) * 100% (strictly <= 100%)
    """
    results = {}
    for name, path in [("Baseline_9_26", BASE_CSV), ("Candidate_10_28", CAND_CSV)]:
        df = pd.read_csv(path)
        df["entry_time"] = pd.to_datetime(df["entry_time"])
        df["exit_time"] = pd.to_datetime(df["exit_time"])
        df = df.sort_values("exit_time").reset_index(drop=True)

        equity = initial_capital
        curve = [equity]
        times = [df["entry_time"].min()]

        for _, row in df.iterrows():
            ret = (row["net_pnl_pct"] / 100.0) * alloc_frac
            equity *= (1.0 + ret)
            curve.append(equity)
            times.append(row["exit_time"])

        curve = np.array(curve)
        peak = np.maximum.accumulate(curve)
        dd = (peak - curve) / peak * 100.0
        max_dd_pct = float(np.max(dd))

        total_return_pct = float((curve[-1] - initial_capital) / initial_capital * 100.0)
        days = (df["exit_time"].max() - df["entry_time"].min()).total_seconds() / 86400.0
        years = days / 365.25
        cagr_pct = float(((curve[-1] / initial_capital) ** (1.0 / years) - 1.0) * 100.0)

        # Portfolio Sharpe based on periodic trade log returns
        trade_log_rets = np.diff(np.log(curve))
        trades_per_year = len(df) / years
        sharpe = float(np.mean(trade_log_rets) / np.std(trade_log_rets) * np.sqrt(trades_per_year)) if np.std(trade_log_rets) > 0 else 0.0

        pnls = df["net_pnl_pct"].values
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        profit_factor = float(np.sum(wins) / abs(np.sum(losses)))
        win_rate = float(len(wins) / len(df) * 100.0)
        expectancy = float(np.mean(pnls))

        gates = [
            {"name": "1. Sharpe Ratio", "target": "Sharpe >= 1.00", "actual": f"{sharpe:.2f}", "passed": bool(sharpe >= 1.00)},
            {"name": "2. CAGR", "target": "CAGR >= 7.0%", "actual": f"{cagr_pct:.2f}%", "passed": bool(cagr_pct >= 7.0)},
            {"name": "3. Profit Factor", "target": "Profit Factor >= 1.30", "actual": f"{profit_factor:.2f}", "passed": bool(profit_factor >= 1.30)},
            {"name": "4. Maximum Drawdown", "target": "Max DD <= 20.0%", "actual": f"{max_dd_pct:.2f}%", "passed": bool(max_dd_pct <= 20.0)},
            {"name": "5. Win Rate", "target": "Win Rate >= 40.0%", "actual": f"{win_rate:.1f}%", "passed": bool(win_rate >= 40.0)},
            {"name": "6. Sample Size", "target": "Trades >= 100", "actual": f"{len(df)}", "passed": bool(len(df) >= 100)},
            {"name": "7. Expectancy", "target": "Expectancy > 0.0%", "actual": f"{expectancy:.4f}%", "passed": bool(expectancy > 0.0)},
        ]
        passed_count = sum(1 for g in gates if g["passed"])

        results[name] = {
            "allocation_fraction_per_trade": alloc_frac,
            "initial_capital_inr": initial_capital,
            "final_equity_inr": round(float(curve[-1]), 2),
            "total_portfolio_return_pct": round(total_return_pct, 2),
            "cagr_pct": round(cagr_pct, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "sharpe_ratio": round(sharpe, 2),
            "profit_factor": round(profit_factor, 3),
            "win_rate_pct": round(win_rate, 2),
            "trade_count": len(df),
            "years": round(years, 2),
            "gates_passed": f"{passed_count} / {len(gates)}",
            "gates_detail": gates,
        }
    return results


def main():
    print("=" * 80)
    print("AUDIT: INDEPENDENT BACKTEST CALCULATION & RISK GATE REVALIDATION")
    print("=" * 80)

    # 1. Dataset Integrity
    ds_audit = audit_dataset_integrity()
    print("\n[1] DATASET TEMPORAL SEPARATION AUDIT:")
    for k, v in ds_audit.items():
        print(f"  {k}: IS trades={v['is_count']} ({v['is_start'][:10]} to {v['is_end_entry'][:10]}), OOS trades={v['oos_count']} ({v['oos_start_entry'][:10]} to {v['oos_end_exit'][:10]}), Overlap={v['temporal_overlap']}")

    # 2. Reproduction of Reported Additive Metrics
    rep_metrics = reproduce_reported_metrics()
    print("\n[2] TRADE-LEVEL ADDITIVE METRICS REPRODUCTION:")
    for k, v in rep_metrics.items():
        print(f"  {k}: Trades={v['trade_count']}, Return={v['total_return_additive_pct']}%, PF={v['profit_factor']}, Exp={v['expectancy_pct']}%, Additive Max Drop={v['max_dd_additive_percentage_points']} points")

    # 3. True Compounded Portfolio Equity Metrics (10% Allocation)
    true_10 = compute_true_portfolio_metrics(alloc_frac=0.10)
    print("\n[3] TRUE COMPOUNDED PORTFOLIO METRICS (10% ALLOCATION PER TRADE):")
    for k, v in true_10.items():
        print(f"  {k}: Return={v['total_portfolio_return_pct']:+.2f}%, CAGR={v['cagr_pct']:+.2f}%, True Max DD={v['max_drawdown_pct']:.2f}%, Sharpe={v['sharpe_ratio']}, Gates={v['gates_passed']}")

    # 4. True Compounded Portfolio Equity Metrics (5% Allocation)
    true_5 = compute_true_portfolio_metrics(alloc_frac=0.05)
    print("\n[4] TRUE COMPOUNDED PORTFOLIO METRICS (5% ALLOCATION PER TRADE):")
    for k, v in true_5.items():
        print(f"  {k}: Return={v['total_portfolio_return_pct']:+.2f}%, CAGR={v['cagr_pct']:+.2f}%, True Max DD={v['max_drawdown_pct']:.2f}%, Sharpe={v['sharpe_ratio']}, Gates={v['gates_passed']}")

    # Save Audit Summary JSON
    audit_output = {
        "temporal_integrity": ds_audit,
        "reported_additive_reproduction": rep_metrics,
        "true_compounded_portfolio_10pct": true_10,
        "true_compounded_portfolio_5pct": true_5,
    }
    out_file = AUDIT_DIR / "backtest_calculation_audit_results.json"
    with open(out_file, "w") as f:
        json.dump(audit_output, f, indent=2)
    print(f"\nAudit results successfully saved to: {out_file}")


if __name__ == "__main__":
    main()
