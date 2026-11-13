#!/usr/bin/env python3
"""
Independent Accounting Assertion Test Suite
Location: backtesting/nifty_etf_covered_call/tests/test_baseline_accounting_reconciliation.py

Verifies and asserts the exact mathematical reconciliation of the baseline engine:
1. Option leg: Gross Premium - Settlement Debits - Option Costs == Option Net P&L
2. Total Statutory Costs == Option Costs + ETF Transaction Costs
3. Total Portfolio Gain == Intra-Cycle ETF P&L + Inter-Cycle ETF Holding Gap + Option Net P&L
4. Final Portfolio Equity == Initial Capital + Total Portfolio Gain
"""

import unittest
from pathlib import Path
import pandas as pd

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
LEDGER_PATH = WORKSPACE_DIR / "baseline" / "cycle_ledger.csv"


class TestBaselineAccountingReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not LEDGER_PATH.exists():
            raise FileNotFoundError(f"Cycle ledger not found at {LEDGER_PATH}")
        cls.df = pd.read_csv(LEDGER_PATH)

    def test_option_leg_reconciliation(self):
        gross_prem = float(self.df["gross_premium"].sum())
        debits = float(self.df["cash_debit"].sum())
        opt_costs = float(self.df["opt_costs"].sum())
        reported_opt_net = float(self.df["opt_net_pnl"].sum())

        expected_opt_net = gross_prem - debits - opt_costs
        self.assertAlmostEqual(gross_prem, 237445.0, places=2)
        self.assertAlmostEqual(debits, 238449.90, places=2)
        self.assertAlmostEqual(opt_costs, 978.43, places=2)
        self.assertAlmostEqual(reported_opt_net, -1983.33, places=2)
        self.assertAlmostEqual(expected_opt_net, reported_opt_net, places=5)

    def test_statutory_costs_reconciliation(self):
        opt_costs = float(self.df["opt_costs"].sum())
        etf_costs = float(self.df["etf_costs"].sum())
        total_costs = opt_costs + etf_costs

        self.assertAlmostEqual(opt_costs, 978.43, places=2)
        self.assertAlmostEqual(etf_costs, 1757.14, places=2)
        self.assertAlmostEqual(total_costs, 2735.57, places=2)

    def test_full_portfolio_equity_reconciliation(self):
        initial_capital = 1500000.0
        final_equity = float(self.df["portfolio_equity"].iloc[-1])
        intra_etf_pnl = float(self.df["etf_net_pnl"].sum())
        opt_net_pnl = float(self.df["opt_net_pnl"].sum())

        # Calculate inter-cycle ETF holding gap (overnight/weekend price changes between cycles)
        intercycle_etf_gap = 0.0
        for idx in range(1, len(self.df)):
            prev_row = self.df.iloc[idx - 1]
            curr_row = self.df.iloc[idx]
            units = prev_row["etf_units"]
            price_gap = curr_row["p_entry"] - prev_row["p_exit"]
            intercycle_etf_gap += units * price_gap

        total_etf_pnl = intra_etf_pnl + intercycle_etf_gap
        total_portfolio_gain = total_etf_pnl + opt_net_pnl
        expected_final_equity = initial_capital + total_portfolio_gain

        self.assertAlmostEqual(final_equity, 1810698.41, places=2)
        self.assertAlmostEqual(intra_etf_pnl, 180838.41, places=2)
        self.assertAlmostEqual(intercycle_etf_gap, 131843.33, places=2)
        self.assertAlmostEqual(total_portfolio_gain, 310698.41, places=2)
        self.assertAlmostEqual(final_equity, expected_final_equity, places=5)


if __name__ == "__main__":
    unittest.main()
