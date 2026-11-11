#!/usr/bin/env python3
"""
================================================================================
Automated Test Suite: NIFTY Covered Call Pre-Deployment Validation
Location: backtesting/nifty_covered_call/test_pre_deployment_validation.py
================================================================================
Verifies all 7 production safety fixes implemented in nifty_covered_call_validated.py:
  1. Fail-closed Startup & Pre-Entry Broker Reconciliation
  2. 15-Calendar-Day Minimum DTE Entry Filter
  3. Two-Phase Order Fill Verification & Orphan Prevention (Emergency Unwind)
  4. Guarded Combined-Position Profit Target (Downside Trap Deflection)
  5. Configurable Futures Catastrophe Stop (-2.0%) & Net M2M Cap (-₹20,000)
  6. Crash-Safe State Recovery & Persistence
  7. Exit Leg Sequencing & Partial Exit Hazard Prevention
================================================================================
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Ensure module path is accessible
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

from nifty_covered_call_validated import (
    NiftyCoveredCallValidatedEngine,
    calculate_bs_delta,
    get_current_ist,
)


class TestPreDeploymentValidation(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory and state file for clean test isolation
        self.test_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.test_dir.name) / "test_state.json"
        self.mock_client = MagicMock()
        self.engine = NiftyCoveredCallValidatedEngine(
            host="http://mock-openalgo:5000",
            api_key="mock_api_key",
            mode="ANALYZE",
            state_file=self.state_file,
            client=self.mock_client,
            min_entry_dte=15,
            roll_dte=10,
            fut_stoploss_pct=0.02,
            max_m2m_loss_cap=20000.0,
        )

    def tearDown(self):
        self.test_dir.cleanup()

    # ==========================================================================
    # FIX 1: Startup & Pre-Entry Broker Reconciliation (Fail-Closed)
    # ==========================================================================
    def test_reconcile_fail_closed_when_client_none(self):
        """Fix 1a: Engine must fail closed if client is None."""
        self.engine.client = None
        safe, msg, _ = self.engine.reconcile_broker_positions()
        self.assertFalse(safe)
        self.assertIn("unavailable", msg.lower())

    def test_reconcile_fail_closed_when_positionbook_fails(self):
        """Fix 1b: Engine must fail closed if positionbook API fails."""
        self.mock_client.positionbook.return_value = {"status": "error", "message": "Broker timeout"}
        safe, msg, _ = self.engine.reconcile_broker_positions()
        self.assertFalse(safe)
        self.assertIn("failed to retrieve positionbook", msg.lower())

    def test_reconcile_fail_closed_when_orderbook_fails(self):
        """Fix 1c: Engine must fail closed if orderbook API fails."""
        self.mock_client.positionbook.return_value = {"status": "success", "data": []}
        self.mock_client.orderbook.return_value = {"status": "error", "message": "Auth expired"}
        safe, msg, _ = self.engine.reconcile_broker_positions()
        self.assertFalse(safe)
        self.assertIn("failed to retrieve orderbook", msg.lower())

    def test_reconcile_fail_closed_when_open_orders_exist(self):
        """Fix 1d: Any pending or open orders in the broker must block entry/operation."""
        self.mock_client.positionbook.return_value = {"status": "success", "data": []}
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {
                "statistics": {"total_open_orders": 1, "total_trigger_pending_orders": 0},
                "orders": [{"orderid": "123", "order_status": "open"}],
            },
        }
        safe, msg, _ = self.engine.reconcile_broker_positions()
        self.assertFalse(safe)
        self.assertIn("active/pending orders exist", msg.lower())

    def test_reconcile_fail_closed_when_ghost_position_exists(self):
        """Fix 1e: Strategy says FLAT, but broker has open F&O position -> Mismatch!"""
        self.engine.state["active_position"] = None
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY27OCT26FUT", "exchange": "NFO", "quantity": 65, "side": "BUY"}
            ],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }
        safe, msg, data = self.engine.reconcile_broker_positions()
        self.assertFalse(safe)
        self.assertIn("state mismatch", msg.lower())
        self.assertIn("broker holds", msg.lower())

    def test_reconcile_fail_closed_when_active_position_mismatched(self):
        """Fix 1f: Strategy has active position, but broker leg quantity differs."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27OCT26FUT",
            "fut_qty": 65,
            "call_symbol": "NIFTY27OCT2623500CE",
            "call_qty": 65,
        }
        # Broker only holds 0 futures or partial quantity
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY27OCT26FUT", "exchange": "NFO", "quantity": 0},
                {"symbol": "NIFTY27OCT2623500CE", "exchange": "NFO", "quantity": -65},
            ],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }
        safe, msg, _ = self.engine.reconcile_broker_positions()
        self.assertFalse(safe)
        self.assertIn("futures leg", msg.lower())

    def test_reconcile_success_when_both_flat(self):
        """Fix 1g: Strategy FLAT and Broker FLAT -> Reconciled Safe."""
        self.engine.state["active_position"] = None
        self.mock_client.positionbook.return_value = {"status": "success", "data": []}
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }
        safe, msg, _ = self.engine.reconcile_broker_positions()
        self.assertTrue(safe)
        self.assertIn("both strategy and broker are flat", msg.lower())

    def test_reconcile_success_when_active_positions_match_1_to_1(self):
        """Fix 1h: Strategy and Broker both hold exactly 65 Long Fut and -65 Short Call."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27OCT26FUT",
            "fut_qty": 65,
            "call_symbol": "NIFTY27OCT2623500CE",
            "call_qty": 65,
        }
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY27OCT26FUT", "exchange": "NFO", "quantity": 65},
                {"symbol": "NIFTY27OCT2623500CE", "exchange": "NFO", "quantity": -65},
            ],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }
        safe, msg, _ = self.engine.reconcile_broker_positions()
        self.assertTrue(safe)
        self.assertIn("matched 1:1", msg.lower())

    # ==========================================================================
    # FIX 2: 15-Calendar-Day Minimum DTE Entry Filter
    # ==========================================================================
    def test_minimum_dte_rejects_expiring_futures(self):
        """Fix 2a: Futures contracts with DTE < 15 days must be rejected."""
        today = get_current_ist().date()
        exp_near = (today + timedelta(days=11)).strftime("%d-%b-%y")  # 11 days DTE
        exp_far = (today + timedelta(days=39)).strftime("%d-%b-%y")   # 39 days DTE

        self.mock_client.search.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY_OCT_FUT", "instrumenttype": "FUTIDX", "expiry": exp_near, "lotsize": 65},
                {"symbol": "NIFTY_NOV_FUT", "instrumenttype": "FUTIDX", "expiry": exp_far, "lotsize": 65},
            ],
        }
        self.mock_client.quotes.return_value = {"status": "success", "data": {"ltp": 23000.0}}

        contract = self.engine.get_eligible_futures_contract()
        self.assertIsNotNone(contract)
        # Must skip 11-day contract and select 39-day contract
        self.assertEqual(contract["symbol"], "NIFTY_NOV_FUT")
        self.assertGreaterEqual(contract["dte"], 15)

    def test_minimum_dte_returns_none_if_all_contracts_under_15_dte(self):
        """Fix 2b: If all available futures have DTE < 15 days, return None."""
        today = get_current_ist().date()
        exp_7d = (today + timedelta(days=7)).strftime("%d-%b-%y")
        exp_12d = (today + timedelta(days=12)).strftime("%d-%b-%y")

        self.mock_client.search.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY_7D_FUT", "instrumenttype": "FUTIDX", "expiry": exp_7d, "lotsize": 65},
                {"symbol": "NIFTY_12D_FUT", "instrumenttype": "FUTIDX", "expiry": exp_12d, "lotsize": 65},
            ],
        }
        contract = self.engine.get_eligible_futures_contract()
        self.assertIsNone(contract)

    def test_find_target_call_rejects_sub_15_dte_expiry(self):
        """Fix 2c: Option selector rejects target expiry if DTE < 15 days."""
        today = get_current_ist().date()
        sub_15_exp = (today + timedelta(days=10)).strftime("%d-%b-%y")
        opt = self.engine.find_target_call_option(spot=23000.0, target_expiry=sub_15_exp)
        self.assertIsNone(opt)

    # ==========================================================================
    # FIX 3: Two-Phase Fill Verification & Orphan Prevention
    # ==========================================================================
    def test_entry_fails_when_futures_order_fails(self):
        """Fix 3a: Leg 1 (Futures) failure aborts immediately before placing Leg 2."""
        self.engine.reconcile_broker_positions = MagicMock(return_value=(True, "Safe", {}))
        # Futures order rejected
        self.mock_client.placeorder.return_value = {
            "status": "error",
            "message": "Insufficient margin",
        }

        fut_info = {"symbol": "NIFTY27NOV26FUT", "lotsize": 65, "ltp": 23000.0}
        opt_info = {"symbol": "NIFTY27NOV2623500CE", "lot_size": 65, "strike": 23500, "expiry": "27-Nov-26", "delta": 0.30, "ltp": 120.0}

        success = self.engine.execute_entry(fut_info, opt_info)
        self.assertFalse(success)
        # placeorder called only once (for futures), NEVER for call
        self.assertEqual(self.mock_client.placeorder.call_count, 1)
        self.assertIsNone(self.engine.state["active_position"])

    def test_entry_fails_and_unwinds_futures_when_call_order_fails(self):
        """Fix 3b: Leg 1 fills, but Leg 2 fails -> Emergency liquidation of Leg 1 (No naked futures)."""
        self.engine.reconcile_broker_positions = MagicMock(return_value=(True, "Safe", {}))

        # Order 1 (Futures) succeeds and fills
        fut_resp = {"status": "success", "orderid": "ORD_FUT_100"}
        # Order 2 (Call) fails
        call_resp = {"status": "error", "message": "RMS strike blocked"}
        # Order 3 (Emergency Fut Sale) succeeds
        unwind_resp = {"status": "success", "orderid": "ORD_EMERGENCY_UNWIND"}

        self.mock_client.placeorder.side_effect = [fut_resp, call_resp, unwind_resp]
        # Orderstatus for futures reports complete
        self.mock_client.orderstatus.return_value = {
            "status": "success",
            "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 23050.0},
        }

        fut_info = {"symbol": "NIFTY27NOV26FUT", "lotsize": 65, "ltp": 23050.0}
        opt_info = {"symbol": "NIFTY27NOV2623500CE", "lot_size": 65, "strike": 23500, "expiry": "27-Nov-26", "delta": 0.30, "ltp": 120.0}

        success = self.engine.execute_entry(fut_info, opt_info)
        self.assertFalse(success)

        # Confirm 3 orders placed: Fut Buy, Call Sell (failed), Fut Sell (emergency unwind)
        self.assertEqual(self.mock_client.placeorder.call_count, 3)
        calls = self.mock_client.placeorder.call_args_list
        # Leg 1: BUY Futures
        self.assertEqual(calls[0].kwargs["action"], "BUY")
        self.assertEqual(calls[0].kwargs["symbol"], "NIFTY27NOV26FUT")
        # Leg 2: SELL Call
        self.assertEqual(calls[1].kwargs["action"], "SELL")
        self.assertEqual(calls[1].kwargs["symbol"], "NIFTY27NOV2623500CE")
        # Emergency unwind: SELL Futures
        self.assertEqual(calls[2].kwargs["action"], "SELL")
        self.assertEqual(calls[2].kwargs["symbol"], "NIFTY27NOV26FUT")

        # State must remain FLAT
        self.assertIsNone(self.engine.state["active_position"])

    # ==========================================================================
    # FIX 4: Guarded Combined-Position Profit Target (Downside Trap Deflection)
    # ==========================================================================
    def test_guarded_profit_target_rejects_decay_when_net_m2m_negative(self):
        """Fix 4a: Market crashes -> Option decays 90%, but Futures loss causes Net M2M <= 0.
        Must NOT declare PROFIT_TARGET_HIT!"""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23000.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2623500CE",
            "call_entry_price": 100.0,
            "call_qty": 65,
            "target_price": 10.0,      # 90% decay target
            "stoploss_price": 300.0,
            "roll_dte": 10,
        }

        # Suppose spot fell from 23000 to 22700 (-300 pts = -1.3%, before 2.0% catastrophe stop)
        # Fut loss = -300 * 65 = -₹19,500
        # Call decayed to ₹8 (gain = 92 * 65 = +₹5,980)
        # Combined M2M = -19,500 + 5,980 = -₹13,520 (Negative!)
        triggered, reason = self.engine.evaluate_risk_and_exits(spot=22700.0, curr_call_price=8.0, dte_left=20)
        # Must NOT trigger PROFIT_TARGET_HIT because net_m2m < 0!
        self.assertFalse(triggered)
        self.assertNotEqual(reason, "PROFIT_TARGET_HIT (90% Decay)")

    def test_guarded_profit_target_triggers_when_net_m2m_positive(self):
        """Fix 4b: Spot rallies or stays flat -> Call decays 90%, Net M2M > 0 -> PROFIT_TARGET_HIT."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23000.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2623500CE",
            "call_entry_price": 100.0,
            "call_qty": 65,
            "target_price": 10.0,      # 90% decay target
            "stoploss_price": 300.0,
            "roll_dte": 10,
        }

        # Spot is flat at 23050 (+50 pts)
        # Fut gain = +50 * 65 = +₹3,250
        # Call gain = +92 * 65 = +₹5,980
        # Net M2M = +₹9,230 (> 0)
        triggered, reason = self.engine.evaluate_risk_and_exits(spot=23050.0, curr_call_price=8.0, dte_left=20)
        self.assertTrue(triggered)
        self.assertEqual(reason, "PROFIT_TARGET_HIT (90% Decay)")

    # ==========================================================================
    # FIX 5: Futures Catastrophe Stop (-2.0%) & Net M2M Cap (-₹20,000)
    # ==========================================================================
    def test_futures_catastrophe_stop_triggers_at_minus_2_pct(self):
        """Fix 5a: Spot drops >= 2.0% -> Triggers FUTURES_STOP_LOSS_HIT."""
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
        # 2.1% drop: 23000 * (1 - 0.021) = 22517.0
        triggered, reason = self.engine.evaluate_risk_and_exits(spot=22517.0, curr_call_price=50.0, dte_left=20)
        self.assertTrue(triggered)
        self.assertIn("FUTURES_STOP_LOSS_HIT", reason)

    def test_max_m2m_loss_cap_triggers_at_minus_20k(self):
        """Fix 5b: Combined M2M breaches -₹20,000 cap -> Triggers MAX_M2M_LOSS_CAP_BREACHED."""
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
        # Spot drops 350 pts (1.52% drop, so under 2.0% fut stop): Fut loss = -350 * 65 = -₹22,750
        # Call price stays at 80 (call gain = +20 * 65 = +₹1,300)
        # Net M2M = -22,750 + 1,300 = -₹21,450 (Breaches -₹20,000 cap)
        triggered, reason = self.engine.evaluate_risk_and_exits(spot=22650.0, curr_call_price=80.0, dte_left=20)
        self.assertTrue(triggered)
        self.assertIn("MAX_M2M_LOSS_CAP_BREACHED", reason)

    def test_call_stoploss_and_roll_threshold(self):
        """Fix 5c & 5d: Call premium spikes 3x or DTE drops <= 10."""
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
        # Call spikes to 310
        t1, r1 = self.engine.evaluate_risk_and_exits(spot=23200.0, curr_call_price=310.0, dte_left=18)
        self.assertTrue(t1)
        self.assertIn("CALL_STOP_LOSS_HIT", r1)

        # DTE drops to 9
        t2, r2 = self.engine.evaluate_risk_and_exits(spot=23000.0, curr_call_price=80.0, dte_left=9)
        self.assertTrue(t2)
        self.assertIn("ROLL_THRESHOLD_REACHED", r2)

    # ==========================================================================
    # FIX 6: Crash-Safe Atomic State Persistence & Recovery
    # ==========================================================================
    def test_atomic_state_persistence_and_recovery(self):
        """Fix 6: State must persist atomically without partial file corruption."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23100.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2623600CE",
            "call_entry_price": 95.0,
            "call_qty": 65,
        }
        saved = self.engine.save_state()
        self.assertTrue(saved)
        self.assertTrue(self.state_file.exists())

        # Create a new engine instance with the same file and verify recovery
        new_engine = NiftyCoveredCallValidatedEngine(state_file=self.state_file)
        self.assertIsNotNone(new_engine.state.get("active_position"))
        self.assertEqual(new_engine.state["active_position"]["fut_symbol"], "NIFTY27NOV26FUT")

    # ==========================================================================
    # FIX 7: Exit Leg Sequencing & Partial Exit Hazard Prevention
    # ==========================================================================
    def test_partial_exit_hazard_retains_state(self):
        """Fix 7a: If Leg 1 exit succeeds but Leg 2 exit fails, DO NOT clear state!"""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23000.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2623500CE",
            "call_entry_price": 100.0,
            "call_qty": 65,
        }

        # Leg 1 (Futures Sell) succeeds
        fut_exit_resp = {"status": "success", "orderid": "EXIT_FUT"}
        # Leg 2 (Call Buy) fails
        call_exit_resp = {"status": "error", "message": "API network timeout"}

        self.mock_client.placeorder.side_effect = [fut_exit_resp, call_exit_resp]
        self.mock_client.orderstatus.return_value = {
            "status": "success",
            "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 23200.0},
        }

        success = self.engine.execute_exit("TEST_PARTIAL_EXIT", curr_fut_price=23200.0, curr_opt_price=50.0)
        self.assertFalse(success)
        # CRUCIAL: Active position must NOT be wiped when partial exit occurs
        self.assertIsNotNone(self.engine.state.get("active_position"))

    def test_full_exit_success_clears_state_and_records_history(self):
        """Fix 7b: Both legs fill -> State is reconciled to FLAT and recorded in trade_history."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23000.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2623500CE",
            "call_entry_price": 100.0,
            "call_qty": 65,
        }

        fut_exit_resp = {"status": "success", "orderid": "EXIT_FUT"}
        call_exit_resp = {"status": "success", "orderid": "EXIT_CALL"}

        self.mock_client.placeorder.side_effect = [fut_exit_resp, call_exit_resp]
        self.mock_client.orderstatus.side_effect = [
            {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 23200.0}},
            {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 20.0}},
        ]

        success = self.engine.execute_exit("PROFIT_TARGET_HIT", curr_fut_price=23200.0, curr_opt_price=20.0)
        self.assertTrue(success)
        # State must now be FLAT
        self.assertIsNone(self.engine.state.get("active_position"))
        # Trade must be archived
        self.assertEqual(len(self.engine.state.get("trade_history", [])), 1)
        # Total realized PnL = (23200 - 23000)*65 + (100 - 20)*65 = 13000 + 5200 = 18200
        self.assertEqual(self.engine.state.get("total_realized_pnl"), 18200.0)


if __name__ == "__main__":
    unittest.main()
