#!/usr/bin/env python3
"""
================================================================================
Test Suite: Failure-Injection & Hardening Scenarios for NIFTY Covered Call
Location: backtesting/nifty_covered_call/test_hardening_failure_injection.py
================================================================================
Tests the 4 hardening patches across extreme broker and network failure scenarios:
  1. Repeated entry calls while a position is active (Duplicate Order Prevention)
  2. Short-call partial fill followed by cancellation failure
  3. Short-call buyback rejection or partial fill (Orphaned Naked Short Prevention)
  4. Emergency futures close rejection, partial fill, and timeout
  5. Broker/local-state mismatch after an exit
  6. Profit target reached before and after the cost buffer (₹1,000 threshold)
  7. Restart during an ambiguous order state
================================================================================
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure module path is accessible
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

from nifty_covered_call_validated import (
    NiftyCoveredCallValidatedEngine,
    DEFAULT_PROFIT_TARGET_COST_BUFFER,
)


class TestHardeningFailureInjection(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.test_dir.name) / "test_hardening_state.json"
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
    # TEST 1: Repeated entry calls while a position is active
    # ==========================================================================
    def test_01_repeated_entry_while_position_active(self):
        """Patch 1: execute_entry must immediately reject if position already active in state."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23000.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2623500CE",
            "call_entry_price": 100.0,
            "call_qty": 65,
        }

        fut_info = {"symbol": "NIFTY27NOV26FUT", "lotsize": 65, "ltp": 23000.0}
        opt_info = {"symbol": "NIFTY27NOV2623500CE", "lot_size": 65, "strike": 23500, "expiry": "27-Nov-26", "delta": 0.30, "ltp": 100.0}

        success = self.engine.execute_entry(fut_info, opt_info)
        self.assertFalse(success)
        # placeorder must NEVER be called
        self.assertEqual(self.mock_client.placeorder.call_count, 0)

    # ==========================================================================
    # TEST 2: Short-call partial fill followed by cancellation failure
    # ==========================================================================
    def test_02_short_call_partial_fill_cancellation_failure(self):
        """Patch 2: Short-call partial fill (30/65), cancel fails, but buyback and unwind succeed."""
        self.engine.reconcile_broker_positions = MagicMock(return_value=(True, "Safe", {}))

        # 1. Leg 1 Fut Buy succeeds and fills
        fut_resp = {"status": "success", "orderid": "ORD_FUT_1"}
        # 2. Leg 2 Call Sell order placed for 65 qty
        call_resp = {"status": "success", "orderid": "ORD_CALL_1"}
        # 3. Buyback of 30 short calls succeeds
        buyback_resp = {"status": "success", "orderid": "ORD_CALL_BUYBACK"}
        # 4. Emergency unwind of 65 futures succeeds
        unwind_resp = {"status": "success", "orderid": "ORD_FUT_UNWIND"}

        self.mock_client.placeorder.side_effect = [fut_resp, call_resp, buyback_resp, unwind_resp]

        # Cancel order throws an exception (e.g. network timeout)
        self.mock_client.cancelorder.side_effect = Exception("Network timeout during cancel")

        # Mock orderstatus:
        # - ORD_FUT_1: complete (65)
        # - ORD_CALL_1: open with partial 30 filled
        # - ORD_CALL_BUYBACK: complete (30)
        # - ORD_FUT_UNWIND: complete (65)
        def mock_orderstatus(orderid):
            if orderid == "ORD_FUT_1":
                return {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 23000.0}}
            elif orderid == "ORD_CALL_1":
                return {"status": "success", "data": {"order_status": "open", "filled_quantity": 30, "average_price": 100.0}}
            elif orderid == "ORD_CALL_BUYBACK":
                return {"status": "success", "data": {"order_status": "complete", "filled_quantity": 30, "average_price": 101.0}}
            elif orderid == "ORD_FUT_UNWIND":
                return {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 22995.0}}
            return {"status": "error"}

        self.mock_client.orderstatus.side_effect = mock_orderstatus

        # Mock positionbook during recovery:
        # Step 2: detects -30 short call
        # Step 4: after unwind, everything flat
        def mock_positionbook():
            call_count = self.mock_client.positionbook.call_count
            if call_count <= 2:
                # Still holding -30 short call
                return {"status": "success", "data": [{"symbol": "NIFTY27NOV2623500CE", "quantity": -30}]}
            else:
                # Neutralized flat
                return {"status": "success", "data": []}

        self.mock_client.positionbook.side_effect = mock_positionbook

        fut_info = {"symbol": "NIFTY27NOV26FUT", "lotsize": 65, "ltp": 23000.0}
        opt_info = {"symbol": "NIFTY27NOV2623500CE", "lot_size": 65, "strike": 23500, "expiry": "27-Nov-26", "delta": 0.30, "ltp": 100.0}

        success = self.engine.execute_entry(fut_info, opt_info)
        self.assertFalse(success)

        # Confirm cancellation was attempted despite failing
        self.mock_client.cancelorder.assert_called_once_with(orderid="ORD_CALL_1")
        # Confirm buyback order was placed for exactly 30 calls
        buyback_call = self.mock_client.placeorder.call_args_list[2]
        self.assertEqual(buyback_call.kwargs["symbol"], "NIFTY27NOV2623500CE")
        self.assertEqual(buyback_call.kwargs["action"], "BUY")
        self.assertEqual(buyback_call.kwargs["quantity"], 30)

        # State must remain clean / flat because both legs were neutralized
        self.assertIsNone(self.engine.state.get("active_position"))

    # ==========================================================================
    # TEST 3: Short-call buyback rejection or partial fill
    # ==========================================================================
    def test_03_short_call_buyback_rejection_preserves_state_and_alerts(self):
        """Patch 2: If call buyback fails, DO NOT sell futures (avoid naked call); preserve state!"""
        self.engine.reconcile_broker_positions = MagicMock(return_value=(True, "Safe", {}))

        fut_resp = {"status": "success", "orderid": "ORD_FUT_1"}
        call_resp = {"status": "success", "orderid": "ORD_CALL_1"}
        # Buyback order rejected by broker RMS (e.g. margin or circuit)
        buyback_resp = {"status": "error", "message": "RMS: Margin insufficient for buyback"}

        self.mock_client.placeorder.side_effect = [fut_resp, call_resp, buyback_resp]

        def mock_orderstatus(orderid):
            if orderid == "ORD_FUT_1":
                return {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 23000.0}}
            elif orderid == "ORD_CALL_1":
                return {"status": "success", "data": {"order_status": "rejected", "filled_quantity": 25, "average_price": 100.0}}
            return {"status": "error"}

        self.mock_client.orderstatus.side_effect = mock_orderstatus
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY27NOV26FUT", "quantity": 65},
                {"symbol": "NIFTY27NOV2623500CE", "quantity": -25},
            ],
        }

        fut_info = {"symbol": "NIFTY27NOV26FUT", "lotsize": 65, "ltp": 23000.0}
        opt_info = {"symbol": "NIFTY27NOV2623500CE", "lot_size": 65, "strike": 23500, "expiry": "27-Nov-26", "delta": 0.30, "ltp": 100.0}

        success = self.engine.execute_entry(fut_info, opt_info)
        self.assertFalse(success)

        # Critical: Exactly 3 placeorder calls (Fut Buy, Call Sell, Call Buyback).
        # Futures emergency sale was NOT attempted because Call leg was not flat!
        self.assertEqual(self.mock_client.placeorder.call_count, 3)

        # State MUST NOT be wiped! It must retain the emergency exposure
        pos = self.engine.state.get("active_position")
        self.assertIsNotNone(pos)
        self.assertTrue(pos.get("emergency_unresolved"))
        self.assertEqual(pos.get("emergency_reason"), "PARTIAL_CALL_BUYBACK_FAILED")
        self.assertEqual(pos.get("call_qty"), 25)

    # ==========================================================================
    # TEST 4: Emergency futures close rejection, partial fill, and timeout
    # ==========================================================================
    def test_04a_emergency_futures_close_rejected(self):
        """Patch 3a: Futures unwind order rejected by broker -> returns False and records exposure."""
        self.mock_client.placeorder.return_value = {"status": "error", "message": "Exchange down"}
        success = self.engine._emergency_close_futures("NIFTY27NOV26FUT", 65)
        self.assertFalse(success)

    def test_04b_emergency_futures_close_partial_fill(self):
        """Patch 3b: Futures unwind order only fills 30/65 -> returns False."""
        self.mock_client.placeorder.return_value = {"status": "success", "orderid": "EMERGENCY_FUT"}
        self.mock_client.orderstatus.return_value = {
            "status": "success",
            "data": {"order_status": "open", "filled_quantity": 30, "average_price": 22900.0},
        }
        success = self.engine._emergency_close_futures("NIFTY27NOV26FUT", 65)
        self.assertFalse(success)

    def test_04c_emergency_futures_close_positionbook_reports_residual(self):
        """Patch 3c: Order completed, but broker positionbook still reports remaining position -> returns False."""
        self.mock_client.placeorder.return_value = {"status": "success", "orderid": "EMERGENCY_FUT"}
        self.mock_client.orderstatus.return_value = {
            "status": "success",
            "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 22900.0},
        }
        # Broker positionbook shows 15 contracts remaining
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [{"symbol": "NIFTY27NOV26FUT", "quantity": 15}],
        }
        success = self.engine._emergency_close_futures("NIFTY27NOV26FUT", 65)
        self.assertFalse(success)

    # ==========================================================================
    # TEST 5: Broker/local-state mismatch after an exit
    # ==========================================================================
    def test_05_broker_local_state_mismatch_after_exit(self):
        """Fails closed when strategy state says FLAT, but broker positionbook has residual position."""
        self.engine.state["active_position"] = None
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [{"symbol": "NIFTY27NOV26FUT", "exchange": "NFO", "quantity": 65}],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }
        safe, msg, _ = self.engine.reconcile_broker_positions()
        self.assertFalse(safe)
        self.assertIn("state mismatch", msg.lower())

    # ==========================================================================
    # TEST 6: Profit target reached before and after cost buffer
    # ==========================================================================
    def test_06_profit_target_cost_buffer_dynamics(self):
        """Patch 4: Call hits 90% decay, but requires Combined M2M >= profit_target_cost_buffer (₹1,000)."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23000.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2623500CE",
            "call_entry_price": 100.0,
            "call_qty": 65,
            "target_price": 10.0,
            "stoploss_price": 300.0,
            "roll_dte": 10,
        }

        # Case A: Call decays to ₹8.0 (decay target met), but Spot fell 80 pts (22,920).
        # Fut loss = -80 * 65 = -₹5,200
        # Call gain = +92 * 65 = +₹5,980
        # Gross M2M = +₹780.
        # Although +₹780 is positive, it is below the ₹1,000 cost buffer (statutory costs ~₹600 + slippage).
        # Must be DEFLECTED!
        t_a, r_a = self.engine.evaluate_risk_and_exits(spot=22920.0, curr_call_price=8.0, dte_left=20)
        self.assertFalse(t_a)

        # Case B: Spot rises 20 pts (23,020).
        # Fut gain = +20 * 65 = +₹1,300
        # Call gain = +92 * 65 = +₹5,980
        # Gross M2M = +₹7,280 (>= ₹1,000 cost buffer).
        # Must TRIGGER PROFIT_TARGET_HIT!
        t_b, r_b = self.engine.evaluate_risk_and_exits(spot=23020.0, curr_call_price=8.0, dte_left=20)
        self.assertTrue(t_b)
        self.assertEqual(r_b, "PROFIT_TARGET_HIT (90% Decay)")

        # Case C: Configure cost buffer to 0.0 -> +₹780 triggers immediately
        self.engine.profit_target_cost_buffer = 0.0
        t_c, r_c = self.engine.evaluate_risk_and_exits(spot=22920.0, curr_call_price=8.0, dte_left=20)
        self.assertTrue(t_c)
        self.assertEqual(r_c, "PROFIT_TARGET_HIT (90% Decay)")

    # ==========================================================================
    # TEST 7: Restart during an ambiguous order state
    # ==========================================================================
    def test_07_restart_during_ambiguous_order_state(self):
        """Engine crash leaves emergency unresolved in state file; restart fails closed on reconciliation."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23000.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2623500CE",
            "call_qty": 25,
            "emergency_unresolved": True,
            "emergency_reason": "PARTIAL_CALL_BUYBACK_FAILED",
        }
        self.engine.save_state()

        # Restart new engine from persisted state file
        new_engine = NiftyCoveredCallValidatedEngine(
            state_file=self.state_file,
            client=self.mock_client,
        )
        self.assertIsNotNone(new_engine.state.get("active_position"))
        self.assertTrue(new_engine.state["active_position"].get("emergency_unresolved"))

        # Reconcile against broker that holds mismatched quantities
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY27NOV26FUT", "quantity": 65},
                {"symbol": "NIFTY27NOV2623500CE", "quantity": -25},
            ],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }

        # Any attempt to enter must be blocked by active state guard
        fut_info = {"symbol": "NIFTY27NOV26FUT", "lotsize": 65, "ltp": 23000.0}
        opt_info = {"symbol": "NIFTY27NOV2623500CE", "lot_size": 65, "strike": 23500, "expiry": "27-Nov-26", "delta": 0.30, "ltp": 100.0}
        entry_blocked = new_engine.execute_entry(fut_info, opt_info)
        self.assertFalse(entry_blocked)


if __name__ == "__main__":
    unittest.main()
