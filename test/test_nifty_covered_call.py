#!/usr/bin/env python3
"""
Unit Test Suite for NIFTY Covered Call Strategy
Location: test/test_nifty_covered_call.py
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from datetime import datetime, date
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from strategies.liveonopenalgo.nifty_covered_call import (
    calculate_bs_delta,
    NiftyCoveredCallEngine,
)


class TestNiftyCoveredCall(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.state_file = Path(self.test_dir) / "test_ncc_state.json"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_bs_delta_calculation(self):
        """Test Black-Scholes Call Delta calculations."""
        # 1. At-the-money (ATM) Call with standard DTE ~ 28
        delta_atm = calculate_bs_delta(spot=25000.0, strike=25000.0, dte=28)
        self.assertGreater(delta_atm, 0.45)
        self.assertLess(delta_atm, 0.60)

        # 2. Out-of-the-money (OTM) Call
        delta_otm = calculate_bs_delta(spot=25000.0, strike=25600.0, dte=28)
        self.assertGreater(delta_otm, 0.15)
        self.assertLess(delta_otm, 0.35)

        # 3. Deep In-the-money (ITM) Call
        delta_itm = calculate_bs_delta(spot=25000.0, strike=24000.0, dte=28)
        self.assertGreater(delta_itm, 0.85)
        self.assertLessEqual(delta_itm, 1.0)

        # 4. Invalid inputs fallback
        self.assertEqual(calculate_bs_delta(spot=0, strike=25000, dte=28), 0.50)

    def test_futures_contract_discovery_rejects_other_indices(self):
        """Verify that get_near_futures_contract strictly rejects BANKNIFTY, FINNIFTY, MIDCPNIFTY."""
        engine = NiftyCoveredCallEngine(
            host="http://mock-host",
            api_key="test_key",
            mode="ANALYZE",
            state_file=str(self.state_file),
        )
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "status": "success",
            "data": [
                # BANKNIFTY should be ignored even if it contains 'NIFTY'
                {"symbol": "BANKNIFTY29OCT26FUT", "instrumenttype": "FUT", "lotsize": 30, "expiry": "29-OCT-26"},
                # FINNIFTY should be ignored
                {"symbol": "FINNIFTY27OCT26FUT", "instrumenttype": "FUT", "lotsize": 60, "expiry": "27-OCT-26"},
                # NIFTYNXT50 should be ignored
                {"symbol": "NIFTYNXT5029OCT26FUT", "instrumenttype": "FUT", "lotsize": 25, "expiry": "29-OCT-26"},
                # Valid NIFTY Future
                {"symbol": "NIFTY29OCT26FUT", "instrumenttype": "FUT", "lotsize": 65, "expiry": "29-OCT-26"},
            ]
        }
        mock_client.quotes.return_value = {"status": "success", "data": {"ltp": 25100.0}}
        engine.client = mock_client

        fut_info = engine.get_near_futures_contract()
        self.assertEqual(fut_info["symbol"], "NIFTY29OCT26FUT")
        self.assertEqual(fut_info["lotsize"], 65)
        self.assertEqual(fut_info["ltp"], 25100.0)

    def test_target_call_option_discovery(self):
        """Verify discovery of ~0.30 Delta Call option on matching expiry."""
        engine = NiftyCoveredCallEngine(
            host="http://mock-host",
            api_key="test_key",
            mode="ANALYZE",
            delta=0.30,
            state_file=str(self.state_file),
        )
        mock_client = MagicMock()
        mock_client.expiry.return_value = {
            "status": "success",
            "data": ["29-OCT-26"]
        }
        mock_client.search.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY26OCT24500CE", "strike": 24500, "expiry": "29-OCT-26", "lotsize": 65},
                {"symbol": "NIFTY26OCT25000CE", "strike": 25000, "expiry": "29-OCT-26", "lotsize": 65},
                {"symbol": "NIFTY26OCT25400CE", "strike": 25400, "expiry": "29-OCT-26", "lotsize": 65},
                {"symbol": "NIFTY26OCT26000CE", "strike": 26000, "expiry": "29-OCT-26", "lotsize": 65},
            ]
        }
        mock_client.quotes.return_value = {"status": "success", "data": {"ltp": 160.0}}
        engine.client = mock_client

        opt_info = engine.find_target_call_option(spot=25000.0, target_expiry="29-OCT-26")
        self.assertIsNotNone(opt_info)
        self.assertIn("CE", opt_info["symbol"])
        self.assertAlmostEqual(opt_info["delta"], 0.30, delta=0.20)
        self.assertEqual(opt_info["lot_size"], 65)

    def test_entry_execution_and_state_persistence(self):
        """Verify Covered Call entry order dispatch and atomic state recording."""
        engine = NiftyCoveredCallEngine(
            host="http://mock-host",
            api_key="test_key",
            mode="ANALYZE",
            state_file=str(self.state_file),
        )
        mock_client = MagicMock()
        engine.client = mock_client

        fut_info = {"symbol": "NIFTY29OCT26FUT", "lotsize": 65, "ltp": 25000.0, "expiry": "29-OCT-26"}
        opt_info = {
            "symbol": "NIFTY26OCT25400CE",
            "strike": 25400.0,
            "expiry": "29-OCT-26",
            "dte": 28,
            "delta": 0.30,
            "ltp": 150.0,
            "lot_size": 65,
        }

        with patch.object(engine, "send_telegram"):
            engine.execute_entry(fut_info, opt_info)

        # Check client calls
        self.assertEqual(mock_client.placeorder.call_count, 2)
        fut_call = mock_client.placeorder.call_args_list[0][1]
        self.assertEqual(fut_call["symbol"], "NIFTY29OCT26FUT")
        self.assertEqual(fut_call["action"], "BUY")
        self.assertEqual(fut_call["quantity"], 65)

        opt_call = mock_client.placeorder.call_args_list[1][1]
        self.assertEqual(opt_call["symbol"], "NIFTY26OCT25400CE")
        self.assertEqual(opt_call["action"], "SELL")
        self.assertEqual(opt_call["quantity"], 65)

        # Check state
        active = engine.state.get("active_position")
        self.assertIsNotNone(active)
        self.assertEqual(active["fut_symbol"], "NIFTY29OCT26FUT")
        self.assertEqual(active["call_symbol"], "NIFTY26OCT25400CE")
        self.assertEqual(active["target_price"], 15.0)     # 90% decay of 150 = 15.0
        self.assertEqual(active["stoploss_price"], 450.0)  # 3.0x of 150 = 450.0

        # Reload engine from disk to verify persistence
        new_engine = NiftyCoveredCallEngine(state_file=str(self.state_file))
        self.assertIsNotNone(new_engine.state.get("active_position"))
        self.assertEqual(new_engine.state["active_position"]["fut_symbol"], "NIFTY29OCT26FUT")

    def test_exit_profit_target_trigger(self):
        """Verify position exit when call decays to 90% profit target."""
        engine = NiftyCoveredCallEngine(
            host="http://mock-host",
            api_key="test_key",
            mode="ANALYZE",
            state_file=str(self.state_file),
        )
        mock_client = MagicMock()
        engine.client = mock_client

        engine.state["active_position"] = {
            "entry_time": "2026-10-13 10:00:00 IST",
            "fut_symbol": "NIFTY29OCT26FUT",
            "fut_entry_price": 25000.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY26OCT25400CE",
            "call_strike": 25400.0,
            "call_expiry": "29-OCT-26",
            "call_entry_price": 150.0,
            "call_qty": 65,
            "call_delta": 0.30,
            "target_price": 15.0,
            "stoploss_price": 450.0,
            "roll_dte": 10,
            "mode": "ANALYZE",
        }

        with patch.object(engine, "send_telegram"):
            engine.execute_exit("PROFIT_TARGET_HIT (90% Decay)", curr_fut_price=25200.0, curr_opt_price=12.0)

        # Active position should now be None
        self.assertIsNone(engine.state.get("active_position"))
        self.assertEqual(len(engine.state["trade_history"]), 1)
        record = engine.state["trade_history"][0]
        self.assertEqual(record["exit_reason"], "PROFIT_TARGET_HIT (90% Decay)")

        # PnL calculations:
        # Futures: (25200 - 25000) * 65 = +13000
        # Call: (150 - 12) * 65 = +8970
        # Total = 21970
        self.assertEqual(record["fut_pnl"], 13000.0)
        self.assertEqual(record["opt_pnl"], 8970.0)
        self.assertEqual(record["total_pnl"], 21970.0)
        self.assertEqual(engine.state["total_realized_pnl"], 21970.0)

    def test_exit_stoploss_trigger(self):
        """Verify position exit when call rises above 3.0x stoploss multiplier."""
        engine = NiftyCoveredCallEngine(
            host="http://mock-host",
            api_key="test_key",
            mode="ANALYZE",
            state_file=str(self.state_file),
        )
        mock_client = MagicMock()
        engine.client = mock_client

        engine.state["active_position"] = {
            "entry_time": "2026-10-13 10:00:00 IST",
            "fut_symbol": "NIFTY29OCT26FUT",
            "fut_entry_price": 25000.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY26OCT25400CE",
            "call_strike": 25400.0,
            "call_expiry": "29-OCT-26",
            "call_entry_price": 150.0,
            "call_qty": 65,
            "call_delta": 0.30,
            "target_price": 15.0,
            "stoploss_price": 450.0,
            "roll_dte": 10,
            "mode": "ANALYZE",
        }

        with patch.object(engine, "send_telegram"):
            engine.execute_exit("STOP_LOSS_HIT (3.0x Premium)", curr_fut_price=24600.0, curr_opt_price=460.0)

        self.assertIsNone(engine.state.get("active_position"))
        record = engine.state["trade_history"][0]
        self.assertEqual(record["exit_reason"], "STOP_LOSS_HIT (3.0x Premium)")
        # Futures: (24600 - 25000) * 65 = -26000
        # Call: (150 - 460) * 65 = -20150
        # Total = -46150
        self.assertEqual(record["fut_pnl"], -26000.0)
        self.assertEqual(record["opt_pnl"], -20150.0)
        self.assertEqual(record["total_pnl"], -46150.0)


if __name__ == "__main__":
    unittest.main()
