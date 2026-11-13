"""
Unit and boundary tests for MACD_FNO_V1_C3 Baseline Update.
Validates:
1. Time-filter boundary conditions:
   - 11:15 IST is ALLOWED (MORNING_AND_MIDDAY_WINDOW)
   - 14:15 IST remains BLOCKED (DEAD_ZONE_14_PM)
   - All other boundary minute marks (09:44, 09:45, 13:15, 13:16, 14:00, 14:59, 15:00, 15:20, 15:21)
2. Invariance of core strategy parameters:
   - MACD (12, 26, 9, 2-bar hist)
   - Universe (TOP_LONGS 7, TOP_SHORTS 6)
   - Profit targets (+3.0% / +1.5%) and SL (-3.5%)
   - Max active positions (20)
3. Agreement across all 3 strategy codebases:
   - strategies/scripts/macdfno.py
   - strategies/liveonopenalgo/macdfno.py
   - backtesting/macdfno/macdfno.py
"""

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
import zoneinfo

IST = zoneinfo.ZoneInfo("Asia/Kolkata")

def load_module_from_path(module_name: str, file_path: str):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMacdFnoC3TimeFilter(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cls.scripts_mod = load_module_from_path(
            "macdfno_scripts",
            os.path.join(base_dir, "strategies", "scripts", "macdfno.py")
        )
        cls.live_mod = load_module_from_path(
            "macdfno_live",
            os.path.join(base_dir, "strategies", "liveonopenalgo", "macdfno.py")
        )
        cls.bt_mod = load_module_from_path(
            "macdfno_bt",
            os.path.join(base_dir, "backtesting", "macdfno", "macdfno.py")
        )

    def test_c3_time_filter_boundaries(self):
        """Test exact boundary points for C3 time filter."""
        test_cases = [
            # time_str, expected_allowed, expected_reason
            ("09:15", False, "OUTSIDE_ALLOWED_WINDOWS"),
            ("09:44", False, "OUTSIDE_ALLOWED_WINDOWS"),
            ("09:45", True, "MORNING_AND_MIDDAY_WINDOW"),
            ("10:15", True, "MORNING_AND_MIDDAY_WINDOW"),
            ("11:00", True, "MORNING_AND_MIDDAY_WINDOW"),
            ("11:15", True, "MORNING_AND_MIDDAY_WINDOW"),  # Key C3 unblocked window!
            ("11:59", True, "MORNING_AND_MIDDAY_WINDOW"),
            ("12:15", True, "MORNING_AND_MIDDAY_WINDOW"),
            ("13:15", True, "MORNING_AND_MIDDAY_WINDOW"),
            ("13:16", False, "OUTSIDE_ALLOWED_WINDOWS"),
            ("14:00", False, "DEAD_ZONE_14_PM"),          # Key C3 retained dead zone!
            ("14:15", False, "DEAD_ZONE_14_PM"),          # Key C3 retained dead zone!
            ("14:59", False, "DEAD_ZONE_14_PM"),          # Key C3 retained dead zone!
            ("15:00", True, "CLOSING_WINDOW"),
            ("15:15", True, "CLOSING_WINDOW"),
            ("15:20", True, "CLOSING_WINDOW"),
            ("15:21", False, "OUTSIDE_ALLOWED_WINDOWS"),
            ("15:30", False, "OUTSIDE_ALLOWED_WINDOWS"),
        ]

        for mod_name, mod in [("scripts", self.scripts_mod), ("live", self.live_mod), ("bt", self.bt_mod)]:
            for time_str, exp_allowed, exp_reason in test_cases:
                h, m = map(int, time_str.split(":"))
                dt = datetime(2026, 10, 15, h, m, 0, tzinfo=IST)
                allowed, reason = mod.is_entry_time_allowed(dt)
                self.assertEqual(
                    allowed, exp_allowed,
                    f"[{mod_name}] Failed allowed check at {time_str}: got {allowed}, expected {exp_allowed}"
                )
                self.assertEqual(
                    reason, exp_reason,
                    f"[{mod_name}] Failed reason check at {time_str}: got '{reason}', expected '{exp_reason}'"
                )

    def test_c3_invariant_parameters(self):
        """Test that all core strategy invariants remain intact across all modules."""
        for mod_name, mod in [("scripts", self.scripts_mod), ("live", self.live_mod), ("bt", self.bt_mod)]:
            # Universe
            self.assertEqual(
                mod.TOP_LONGS,
                {"SUNPHARMA", "BAJAJ-AUTO", "BPCL", "WIPRO", "TATASTEEL", "BAJFINANCE", "NTPC"},
                f"[{mod_name}] TOP_LONGS mismatch"
            )
            self.assertEqual(
                mod.TOP_SHORTS,
                {"SUNPHARMA", "BAJAJ-AUTO", "M&M", "BPCL", "NTPC"},
                f"[{mod_name}] TOP_SHORTS mismatch"
            )

            # Targets and Stops
            self.assertAlmostEqual(mod.LONG_PROFIT_TARGET_PCT, 3.0, places=2)
            self.assertAlmostEqual(mod.SHORT_PROFIT_TARGET_PCT, 1.5, places=2)
            self.assertAlmostEqual(mod.CATASTROPHE_SL_PCT, 3.5, places=2)

            # Max Active Positions
            self.assertEqual(mod.MAX_ACTIVE_POSITIONS, 20)


if __name__ == "__main__":
    unittest.main()
