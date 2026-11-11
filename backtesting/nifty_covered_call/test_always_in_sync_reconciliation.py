#!/usr/bin/env python3
"""
================================================================================
Test Suite: Always-In-Sync Continuous Closed-Loop Reconciliation
Location: backtesting/nifty_covered_call/test_always_in_sync_reconciliation.py
================================================================================
Validates that the NIFTY Covered Call Strategy remains strictly synchronized with
the broker/exchange position book at all times:
  1. Manual UI closure detection when both legs are flat on broker.
  2. Automatic transition from ACTIVE to FLAT with trade archiving (MANUAL_UI_EXIT).
  3. Continuous in-loop detection during evaluate_cycle() preventing phantom monitoring.
  4. Asymmetric exposure protection: Naked Long Futures detected & automated exits blocked.
  5. Asymmetric exposure protection: Naked Short Call detected & automated exits blocked.
  6. Partial quantity mismatch detected and handled safely (Fail-Closed).
  7. API failure (positionbook / orderbook) triggers strict Fail-Closed behavior.
  8. Pending/Open orders in orderbook block all automated actions.
  9. Exit order dispatch rejects duplicate or reverse orders if position already flat.
  10. Entry order dispatch rejects duplicate entries if active in state or broker.
================================================================================
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

from nifty_covered_call_validated import NiftyCoveredCallValidatedEngine


class TestAlwaysInSyncReconciliation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.test_dir.name) / "test_always_in_sync_state.json"
        self.mock_client = MagicMock()
        self.engine = NiftyCoveredCallValidatedEngine(
            host="http://mock-openalgo:5000",
            api_key="mock_api_key",
            mode="ANALYZE",
            state_file=self.state_file,
            client=self.mock_client,
            profit_target_cost_buffer=1000.0,
            fut_stoploss_pct=0.02,
            max_m2m_loss_cap=20000.0,
        )

    def tearDown(self):
        self.test_dir.cleanup()

    # ==========================================================================
    # TEST 1: Manual UI Closure — Both legs flat on broker reconciles state
    # ==========================================================================
    def test_01_manual_ui_closure_both_legs_flat_syncs_to_flat(self):
        """When user manually exits both legs via UI, strategy detects flat broker and syncs state."""
        self.engine.state["active_position"] = {
            "entry_time": "2026-10-16 11:58:02 IST",
            "fut_symbol": "NIFTY23NOV26FUT",
            "fut_entry_price": 23229.2,
            "fut_qty": 65,
            "call_symbol": "NIFTY23NOV2624000CE",
            "call_strike": 24000.0,
            "call_expiry": "23-NOV-26",
            "call_entry_price": 97.35,
            "call_qty": 65,
            "mode": "ANALYZE",
        }
        self.engine.save_state()

        # Broker positionbook shows both legs closed (quantity == 0)
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY23NOV26FUT", "exchange": "NFO", "quantity": 0, "average_price": 23226.7, "ltp": 23226.7},
                {"symbol": "NIFTY23NOV2624000CE", "exchange": "NFO", "quantity": 0, "average_price": 98.95, "ltp": 98.95},
            ],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }

        safe, msg, data = self.engine.reconcile_broker_positions(auto_sync_manual_exit=True)
        self.assertTrue(safe)
        self.assertIn("manual exit detected and synchronized", msg.lower())

        # Strategy state MUST be FLAT
        self.assertIsNone(self.engine.state.get("active_position"))

        # Trade must be archived with reason MANUAL_UI_EXIT
        history = self.engine.state.get("trade_history", [])
        self.assertEqual(len(history), 1)
        record = history[0]
        self.assertEqual(record["exit_reason"], "MANUAL_UI_EXIT")
        self.assertEqual(record["fut_exit_price"], 23226.7)
        self.assertEqual(record["call_exit_price"], 98.95)

        # Expected PnL: 65*(23226.7 - 23229.2) + 65*(97.35 - 98.95) = -162.5 - 104.0 = -266.5
        self.assertEqual(record["total_pnl"], -266.5)
        self.assertEqual(self.engine.state.get("total_realized_pnl"), -266.5)

        # State on disk must also be updated
        with open(self.state_file, "r") as f:
            disk_state = json.load(f)
        self.assertIsNone(disk_state.get("active_position"))

    # ==========================================================================
    # TEST 2: evaluate_cycle() automatically catches UI exit and avoids phantom monitoring
    # ==========================================================================
    def test_02_evaluate_cycle_detects_manual_closure_and_avoids_phantom_monitoring(self):
        """During evaluate_cycle, an external exit resets state to flat before quote/exit logic runs."""
        self.engine.state["active_position"] = {
            "entry_time": "2026-10-16 11:58:02 IST",
            "fut_symbol": "NIFTY23NOV26FUT",
            "fut_entry_price": 23229.2,
            "fut_qty": 65,
            "call_symbol": "NIFTY23NOV2624000CE",
            "call_expiry": "23-NOV-26",
            "call_entry_price": 97.35,
            "call_qty": 65,
            "target_price": 9.73,
            "stoploss_price": 292.05,
        }
        self.engine.save_state()

        # Broker returns 0 quantity for both legs
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY23NOV26FUT", "exchange": "NFO", "quantity": 0, "average_price": 23226.7},
                {"symbol": "NIFTY23NOV2624000CE", "exchange": "NFO", "quantity": 0, "average_price": 98.95},
            ],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }

        # Mock quotes so if it did try to evaluate it wouldn't fail
        self.mock_client.quotes.return_value = {"status": "success", "data": {"ltp": 23200.0}}

        # Run one evaluation cycle (bypass market hours for deterministic test)
        with patch.object(self.engine, "execute_exit") as mock_exit:
            self.engine.evaluate_cycle(ignore_market_hours=True)
            # execute_exit MUST NOT be called because the position was already closed!
            mock_exit.assert_not_called()

        # State is now FLAT
        self.assertIsNone(self.engine.state.get("active_position"))

    # ==========================================================================
    # TEST 3: Asymmetric Exposure — Naked Long Futures
    # ==========================================================================
    def test_03_asymmetric_exposure_naked_futures_blocks_automated_exits(self):
        """If Call leg was manually closed but Futures is still open, flag hazard and block normal exit."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY23NOV26FUT",
            "fut_qty": 65,
            "call_symbol": "NIFTY23NOV2624000CE",
            "call_qty": 65,
        }

        # Broker shows Futures still holding 65x, but Call is 0!
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY23NOV26FUT", "exchange": "NFO", "quantity": 65},
                {"symbol": "NIFTY23NOV2624000CE", "exchange": "NFO", "quantity": 0},
            ],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }

        safe, msg, data = self.engine.reconcile_broker_positions(auto_sync_manual_exit=True)
        self.assertFalse(safe)
        self.assertIn("naked futures risk", msg.lower())
        self.assertEqual(data.get("hazard"), "naked_futures")

        # Crucial: State active_position must NOT be cleared, operator intervention needed
        self.assertIsNotNone(self.engine.state.get("active_position"))

    # ==========================================================================
    # TEST 4: Asymmetric Exposure — Naked Short Call
    # ==========================================================================
    def test_04_asymmetric_exposure_naked_short_call_blocks_automated_exits(self):
        """If Futures leg was closed but Short Call is still open, flag hazard and block normal exit."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY23NOV26FUT",
            "fut_qty": 65,
            "call_symbol": "NIFTY23NOV2624000CE",
            "call_qty": 65,
        }

        # Broker shows Futures = 0, but Call = -65!
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY23NOV26FUT", "exchange": "NFO", "quantity": 0},
                {"symbol": "NIFTY23NOV2624000CE", "exchange": "NFO", "quantity": -65},
            ],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }

        safe, msg, data = self.engine.reconcile_broker_positions(auto_sync_manual_exit=True)
        self.assertFalse(safe)
        self.assertIn("naked short call risk", msg.lower())
        self.assertEqual(data.get("hazard"), "naked_call")
        self.assertIsNotNone(self.engine.state.get("active_position"))

    # ==========================================================================
    # TEST 5: Partial Quantity Mismatch
    # ==========================================================================
    def test_05_partial_quantity_mismatch_detected(self):
        """If broker holds partial quantity (+65 Fut, -30 Call), reconciliation detects mismatch."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY23NOV26FUT",
            "fut_qty": 65,
            "call_symbol": "NIFTY23NOV2624000CE",
            "call_qty": 65,
        }

        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY23NOV26FUT", "exchange": "NFO", "quantity": 65},
                {"symbol": "NIFTY23NOV2624000CE", "exchange": "NFO", "quantity": -30},
            ],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }

        safe, msg, _ = self.engine.reconcile_broker_positions(auto_sync_manual_exit=True)
        self.assertFalse(safe)
        self.assertIn("call leg", msg.lower())
        self.assertIn("not matched in broker", msg.lower())

    # ==========================================================================
    # TEST 6: Fail-Closed on Broker API Failure
    # ==========================================================================
    def test_06_api_failure_fails_closed(self):
        """When positionbook API returns error or raises exception, fail-closed is triggered."""
        self.mock_client.positionbook.side_effect = Exception("Connection timed out to broker")

        safe, msg, _ = self.engine.reconcile_broker_positions(auto_sync_manual_exit=True)
        self.assertFalse(safe)
        self.assertIn("fail closed", msg.lower())

    # ==========================================================================
    # TEST 7: Fail-Closed on Open / Pending Orders
    # ==========================================================================
    def test_07_pending_orders_block_actions(self):
        """Any pending order in the broker orderbook must pause automated strategy actions."""
        self.mock_client.positionbook.return_value = {"status": "success", "data": []}
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 1, "total_trigger_pending_orders": 0}},
        }

        safe, msg, _ = self.engine.reconcile_broker_positions(auto_sync_manual_exit=True)
        self.assertFalse(safe)
        self.assertIn("active/pending orders exist", msg.lower())

    # ==========================================================================
    # TEST 8: Prevention of Duplicate or Reverse Exit Orders
    # ==========================================================================
    def test_08_execute_exit_prevents_reverse_orders_when_already_flat(self):
        """If execute_exit() is invoked when the position is already closed in broker, zero orders are placed."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY23NOV26FUT",
            "fut_entry_price": 23229.2,
            "fut_qty": 65,
            "call_symbol": "NIFTY23NOV2624000CE",
            "call_entry_price": 97.35,
            "call_qty": 65,
        }

        # Broker is already flat
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY23NOV26FUT", "exchange": "NFO", "quantity": 0, "average_price": 23226.7},
                {"symbol": "NIFTY23NOV2624000CE", "exchange": "NFO", "quantity": 0, "average_price": 98.95},
            ],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }

        # Attempt to execute an exit
        result = self.engine.execute_exit("PROFIT_TARGET_HIT", curr_fut_price=23230.0, curr_opt_price=10.0)

        # Must return True (exit not needed) without sending ANY orders to broker
        self.assertTrue(result)
        self.mock_client.placeorder.assert_not_called()

        # State must now be FLAT
        self.assertIsNone(self.engine.state.get("active_position"))

    # ==========================================================================
    # TEST 9: Duplicate Entry Prevention
    # ==========================================================================
    def test_09_duplicate_entry_prevented_when_state_active(self):
        """execute_entry must reject immediately if state already has an active position."""
        self.engine.state["active_position"] = {"fut_symbol": "NIFTY23NOV26FUT"}

        fut_info = {"symbol": "NIFTY23NOV26FUT", "lotsize": 65}
        opt_info = {"symbol": "NIFTY23NOV2624000CE", "lot_size": 65}

        res = self.engine.execute_entry(fut_info, opt_info)
        self.assertFalse(res)
        self.mock_client.placeorder.assert_not_called()

    # ==========================================================================
    # TEST 10: Entry Blocked if Broker Holds Unmanaged Positions
    # ==========================================================================
    def test_10_entry_blocked_when_broker_holds_unmanaged_fno_positions(self):
        """Strategy is FLAT in state, but broker holds an unmanaged NIFTY F&O position -> Entry blocked."""
        self.engine.state["active_position"] = None

        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [{"symbol": "NIFTY23NOV26FUT", "exchange": "NFO", "quantity": 65}],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }

        fut_info = {"symbol": "NIFTY23NOV26FUT", "lotsize": 65}
        opt_info = {"symbol": "NIFTY23NOV2624000CE", "lot_size": 65}

        res = self.engine.execute_entry(fut_info, opt_info)
        self.assertFalse(res)
        self.mock_client.placeorder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
