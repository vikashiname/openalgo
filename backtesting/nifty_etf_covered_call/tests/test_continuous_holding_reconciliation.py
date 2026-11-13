#!/usr/bin/env python3
"""
Unit Test Suite: Continuous Holding Accounting Reconciliation (550 Units)
Location: backtesting/nifty_etf_covered_call/tests/test_continuous_holding_reconciliation.py
"""

import unittest
from pathlib import Path
import pandas as pd

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
CYCLES_PATH = WORKSPACE_DIR / "baseline" / "cycle_ledger.csv"
SPREAD_PATH = WORKSPACE_DIR / "data" / "personal_ledger_550_spread.csv"
RECON_CSV = WORKSPACE_DIR / "data" / "continuous_holding_reconciliation_550.csv"


class TestContinuousHoldingReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df_cycles = pd.read_csv(CYCLES_PATH)
        cls.df_spread = pd.read_csv(SPREAD_PATH)
        cls.df_recon = pd.read_csv(RECON_CSV)
        cls.units = 550.0

    def test_etf_continuous_holding_identity(self):
        p0 = self.df_cycles["p_entry"].iloc[0]
        p_end = self.df_cycles["p_exit"].iloc[-1]
        direct_gain = self.units * (p_end - p0)

        intra_gain = 0.0
        for idx, r in self.df_cycles.iterrows():
            intra_gain += self.units * (r["p_exit"] - r["p_entry"])

        inter_gap = 0.0
        for idx in range(1, len(self.df_cycles)):
            prev_p = self.df_cycles.iloc[idx - 1]["p_exit"]
            curr_p = self.df_cycles.iloc[idx]["p_entry"]
            inter_gap += self.units * (curr_p - prev_p)

        self.assertAlmostEqual(direct_gain, 44660.01, places=2)
        self.assertAlmostEqual(intra_gain, 28385.50, places=2)
        self.assertAlmostEqual(inter_gap, 16274.51, places=2)
        self.assertAlmostEqual(direct_gain, intra_gain + inter_gap, places=6)

    def test_reconciled_overlay_final_equities(self):
        p0 = self.df_cycles["p_entry"].iloc[0]
        p_end = self.df_cycles["p_exit"].iloc[-1]
        bh_final = self.units * p_end  # ₹149,556.01

        naked_opt_pnl = self.df_cycles["opt_net_pnl"].sum()  # -₹1,983.33
        spread_opt_pnl = self.df_spread["opt_pnl"].sum()      # -₹24,998.63

        expected_naked_final = bh_final + naked_opt_pnl
        expected_spread_final = bh_final + spread_opt_pnl

        self.assertAlmostEqual(bh_final, 149556.01, places=2)
        self.assertAlmostEqual(expected_naked_final, 147572.67, places=2)
        self.assertAlmostEqual(expected_spread_final, 124557.37, places=2)

    def test_underperformance_identities(self):
        naked_opt_pnl = self.df_cycles["opt_net_pnl"].sum()
        spread_opt_pnl = self.df_spread["opt_pnl"].sum()

        # Under continuous holding, underperformance is exactly equal to the net option loss
        self.assertAlmostEqual(naked_opt_pnl, -1983.33, places=2)
        self.assertAlmostEqual(spread_opt_pnl, -24998.63, places=2)


if __name__ == "__main__":
    unittest.main()
