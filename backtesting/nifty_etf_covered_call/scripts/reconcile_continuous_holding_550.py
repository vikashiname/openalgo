#!/usr/bin/env python3
"""
================================================================================
Continuous Holding Reconciliation & Personal Exposure Analysis (550 Units)
Location: backtesting/nifty_etf_covered_call/scripts/reconcile_continuous_holding_550.py
================================================================================
Performs 100% continuous holding accounting for 550 NIFTYBEES units:
  - Starting Capital (at market 2022-01-03): ₹1,04,896.00
  - Purchase Cost Basis (₹250/unit): ₹1,37,500.00
  - Full-period continuous holding ETF appreciation: ₹44,660.01
    (Intra-cycle: ₹28,385.50 + Inter-cycle holding gap: ₹16,274.51)
  - Options overlays evaluated with exact continuous holding dates & quantities:
    1. Benchmark: Pure Buy & Hold (0 options)
    2. Overlay 1: 1 Lot Short Call (Bhavcopy fills, historical lots 50, 25)
    3. Overlay 2: 1 Lot Call Credit Spread (+300 pts wing, Bhavcopy fills)
================================================================================
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = WORKSPACE_DIR / "data"
BASELINE_DIR = WORKSPACE_DIR / "baseline"

UNITS = 550.0
COST_BASIS_PER_UNIT = 250.0
TOTAL_COST_BASIS = UNITS * COST_BASIS_PER_UNIT  # ₹1,37,500.00


def run_continuous_reconciliation():
    cycles_path = BASELINE_DIR / "cycle_ledger.csv"
    spread_path = DATA_DIR / "personal_ledger_550_spread.csv"
    daily_path = BASELINE_DIR / "daily_equity.csv"

    df_cycles = pd.read_csv(cycles_path)
    df_spread = pd.read_csv(spread_path)
    df_daily = pd.read_csv(daily_path)

    p0_mkt = df_cycles["p_entry"].iloc[0]
    p_end_mkt = df_cycles["p_exit"].iloc[-1]
    init_mkt_val = UNITS * p0_mkt      # ₹1,04,896.00
    end_mkt_val = UNITS * p_end_mkt    # ₹1,49,556.01

    # Exact duration
    d0 = pd.to_datetime(df_daily["date"].iloc[0])
    d_end = pd.to_datetime(df_daily["date"].iloc[-1])
    years = (d_end - d0).days / 365.25  # 2.56 years

    # 1. Full-Period ETF Appreciation Decomposition
    intra_cycle_etf_pnl = 0.0
    for idx, r in df_cycles.iterrows():
        intra_cycle_etf_pnl += UNITS * (r["p_exit"] - r["p_entry"])

    inter_cycle_etf_gap = 0.0
    for idx in range(1, len(df_cycles)):
        prev_p = df_cycles.iloc[idx - 1]["p_exit"]
        curr_p = df_cycles.iloc[idx]["p_entry"]
        inter_cycle_etf_gap += UNITS * (curr_p - prev_p)

    full_period_etf_pnl = end_mkt_val - init_mkt_val

    # Assert exact continuous holding identity
    assert abs(full_period_etf_pnl - (intra_cycle_etf_pnl + inter_cycle_etf_gap)) < 1e-6

    # 2. Benchmark (Pure Buy & Hold)
    bh_final_equity = end_mkt_val
    bh_net_pnl = full_period_etf_pnl
    bh_ret_mkt = (bh_net_pnl / init_mkt_val) * 100.0
    bh_cagr_mkt = ((bh_final_equity / init_mkt_val) ** (1.0 / years) - 1.0) * 100.0
    bh_ret_cost = ((bh_final_equity - TOTAL_COST_BASIS) / TOTAL_COST_BASIS) * 100.0
    bh_cagr_cost = ((bh_final_equity / TOTAL_COST_BASIS) ** (1.0 / years) - 1.0) * 100.0

    # Benchmark daily drawdown
    df_daily["bh_equity"] = UNITS * df_daily["niftybees_close"]
    bh_mdd = ((df_daily["bh_equity"].cummax() - df_daily["bh_equity"]) / df_daily["bh_equity"].cummax()).max() * 100.0

    # 3. Overlay 1: 1 Lot Short Call (Naked)
    naked_opt_pnl = df_cycles["opt_net_pnl"].sum()  # -₹1,983.33
    naked_final_equity = bh_final_equity + naked_opt_pnl
    naked_net_pnl = naked_final_equity - init_mkt_val
    naked_ret_mkt = (naked_net_pnl / init_mkt_val) * 100.0
    naked_cagr_mkt = ((naked_final_equity / init_mkt_val) ** (1.0 / years) - 1.0) * 100.0
    naked_ret_cost = ((naked_final_equity - TOTAL_COST_BASIS) / TOTAL_COST_BASIS) * 100.0
    naked_cagr_cost = ((naked_final_equity / TOTAL_COST_BASIS) ** (1.0 / years) - 1.0) * 100.0

    # 4. Overlay 2: 1 Lot Call Credit Spread
    spread_opt_pnl = df_spread["opt_pnl"].sum()  # -₹24,998.63
    spread_final_equity = bh_final_equity + spread_opt_pnl
    spread_net_pnl = spread_final_equity - init_mkt_val
    spread_ret_mkt = (spread_net_pnl / init_mkt_val) * 100.0
    spread_cagr_mkt = ((spread_final_equity / init_mkt_val) ** (1.0 / years) - 1.0) * 100.0
    spread_ret_cost = ((spread_final_equity - TOTAL_COST_BASIS) / TOTAL_COST_BASIS) * 100.0
    spread_cagr_cost = ((spread_final_equity / TOTAL_COST_BASIS) ** (1.0 / years) - 1.0) * 100.0

    # Cycle NAV trajectories for Drawdown & Worst Month
    cum_opt_naked = 0.0
    cum_opt_spread = 0.0
    nav_series_naked = [init_mkt_val]
    nav_series_spread = [init_mkt_val]

    monthly_rets_bh = []
    monthly_rets_naked = []
    monthly_rets_spread = []

    for idx, r in df_cycles.iterrows():
        p_in = r["p_entry"]
        p_out = r["p_exit"]
        etf_in = UNITS * p_in
        etf_out = UNITS * p_out

        cum_opt_naked += r["opt_net_pnl"]
        cum_opt_spread += df_spread.iloc[idx]["opt_pnl"]

        nav_series_naked.append(etf_out + cum_opt_naked)
        nav_series_spread.append(etf_out + cum_opt_spread)

        m_bh = (p_out - p_in) / p_in * 100.0
        m_naked = ((etf_out - etf_in) + r["opt_net_pnl"]) / etf_in * 100.0
        m_spread = ((etf_out - etf_in) + df_spread.iloc[idx]["opt_pnl"]) / etf_in * 100.0

        monthly_rets_bh.append(m_bh)
        monthly_rets_naked.append(m_naked)
        monthly_rets_spread.append(m_spread)

    s_naked = pd.Series(nav_series_naked)
    naked_mdd = ((s_naked.cummax() - s_naked) / s_naked.cummax()).max() * 100.0

    s_spread = pd.Series(nav_series_spread)
    spread_mdd = ((s_spread.cummax() - s_spread) / s_spread.cummax()).max() * 100.0

    summary = {
        "Metric": [
            "Initial Market Capital (2022-01-03)",
            "Confirmed Cost Basis (₹250/unit)",
            "Full-Period Continuous ETF Gain",
            "  - Intra-Cycle ETF Gain",
            "  - Inter-Cycle Holding Gap",
            "Options Leg Net P&L",
            "Final Reconciled Equity",
            "Net Portfolio Profit (vs Market Init)",
            "Net Portfolio Profit (vs Cost Basis)",
            "Market Total Return (%)",
            "Market Annualized CAGR (%)",
            "Cost-Basis Annualized CAGR (%)",
            "Alpha / Underperformance vs B&H (₹)",
            "Maximum Drawdown (%)",
            "Worst Monthly Return (%)",
            "Best Monthly Return (%)",
        ],
        "Benchmark: Buy & Hold 550 Units": [
            f"₹{init_mkt_val:,.2f}",
            f"₹{TOTAL_COST_BASIS:,.2f}",
            f"₹{full_period_etf_pnl:,.2f}",
            f"₹{intra_cycle_etf_pnl:,.2f}",
            f"₹{inter_cycle_etf_gap:,.2f}",
            "₹0.00",
            f"₹{bh_final_equity:,.2f}",
            f"+₹{bh_net_pnl:,.2f}",
            f"+₹{bh_final_equity - TOTAL_COST_BASIS:,.2f}",
            f"+{bh_ret_mkt:.2f}%",
            f"{bh_cagr_mkt:.2f}%",
            f"{bh_cagr_cost:.2f}%",
            "₹0.00 (Benchmark)",
            f"-{bh_mdd:.2f}%",
            f"{min(monthly_rets_bh):.2f}%",
            f"+{max(monthly_rets_bh):.2f}%",
        ],
        "Overlay 1: Continuous 550 + 1 Lot Call": [
            f"₹{init_mkt_val:,.2f}",
            f"₹{TOTAL_COST_BASIS:,.2f}",
            f"₹{full_period_etf_pnl:,.2f}",
            f"₹{intra_cycle_etf_pnl:,.2f}",
            f"₹{inter_cycle_etf_gap:,.2f}",
            f"₹{naked_opt_pnl:,.2f}",
            f"₹{naked_final_equity:,.2f}",
            f"+₹{naked_net_pnl:,.2f}",
            f"+₹{naked_final_equity - TOTAL_COST_BASIS:,.2f}",
            f"+{naked_ret_mkt:.2f}%",
            f"{naked_cagr_mkt:.2f}%",
            f"{naked_cagr_cost:.2f}%",
            f"-₹{abs(naked_opt_pnl):,.2f}",
            f"-{naked_mdd:.2f}%",
            f"{min(monthly_rets_naked):.2f}%",
            f"+{max(monthly_rets_naked):.2f}%",
        ],
        "Overlay 2: Continuous 550 + Credit Spread": [
            f"₹{init_mkt_val:,.2f}",
            f"₹{TOTAL_COST_BASIS:,.2f}",
            f"₹{full_period_etf_pnl:,.2f}",
            f"₹{intra_cycle_etf_pnl:,.2f}",
            f"₹{inter_cycle_etf_gap:,.2f}",
            f"₹{spread_opt_pnl:,.2f}",
            f"₹{spread_final_equity:,.2f}",
            f"+₹{spread_net_pnl:,.2f}",
            f"-₹{abs(spread_final_equity - TOTAL_COST_BASIS):,.2f}",
            f"+{spread_ret_mkt:.2f}%",
            f"{spread_cagr_mkt:.2f}%",
            f"{spread_cagr_cost:.2f}%",
            f"-₹{abs(spread_opt_pnl):,.2f}",
            f"-{spread_mdd:.2f}%",
            f"{min(monthly_rets_spread):.2f}%",
            f"+{max(monthly_rets_spread):.2f}%",
        ],
    }

    res_df = pd.DataFrame(summary)
    out_csv = DATA_DIR / "continuous_holding_reconciliation_550.csv"
    res_df.to_csv(out_csv, index=False)
    print(f"[✓] Saved continuous holding reconciliation table to {out_csv}")
    print("\n" + res_df.to_string(index=False))


if __name__ == "__main__":
    run_continuous_reconciliation()
