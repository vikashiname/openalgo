#!/usr/bin/env python3
"""
================================================================================
Test Suite: NIFTY Rolling Defensive Credit Collar & Dynamic Option Rolling
Location: backtesting/nifty_covered_call/test_rolling_defensive_collar.py
================================================================================
Validates:
  1. 3-Leg Collar Entry Execution (Long Fut + Short Call + Long Put)
  2. Closed-Loop Broker Reconciliation & Auto-Adoption of 3-Leg Collars
  3. Dynamic Intra-Cycle Rolling Trigger Detection (Decay Harvest & Rally Defense)
  4. Execution of roll_short_call (Buyback old call, sell new call, accumulate PnL)
  5. Full Exit Sequencing across all 3 legs and trade ledger persistence
  6. Whipsaw Immunity: Futures stop-loss bypassed when protective put is active
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

from nifty_covered_call_validated import (
    NiftyCoveredCallValidatedEngine,
    calculate_bs_call_price,
    calculate_bs_put_price,
    calculate_bs_put_delta,
)


class TestRollingDefensiveCollar(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.test_dir.name) / "test_collar_state.json"
        self.mock_client = MagicMock()
        self.engine = NiftyCoveredCallValidatedEngine(
            host="http://mock-openalgo:5000",
            api_key="mock_api_key",
            mode="ANALYZE",
            state_file=self.state_file,
            client=self.mock_client,
            enable_collar=True,
            put_delta=0.07,
            enable_rolling=True,
            harvest_decay_pct=0.80,
            roll_min_dte=15,
            fut_stoploss_pct=0.02,
            max_m2m_loss_cap=20000.0,
        )

    def tearDown(self):
        self.test_dir.cleanup()

    # ==========================================================================
    # TEST 1: 3-Leg Collar Entry Execution
    # ==========================================================================
    def test_01_execute_entry_with_protective_put_establishes_3leg_collar(self):
        """When put_info is supplied, entry places Fut Buy, Call Sell, and Put Buy."""
        self.engine.reconcile_broker_positions = MagicMock(return_value=(True, "Safe", {}))

        fut_resp = {"status": "success", "orderid": "ORD_FUT_1"}
        call_resp = {"status": "success", "orderid": "ORD_CALL_1"}
        put_resp = {"status": "success", "orderid": "ORD_PUT_1"}

        self.mock_client.placeorder.side_effect = [fut_resp, call_resp, put_resp]
        self.mock_client.orderstatus.side_effect = [
            {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 23500.0}},
            {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 130.0}},
            {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 24.5}},
        ]

        fut_info = {"symbol": "NIFTY27NOV26FUT", "lotsize": 65, "ltp": 23500.0}
        opt_info = {"symbol": "NIFTY27NOV2624200CE", "lot_size": 65, "strike": 24200, "expiry": "27-Nov-26", "delta": 0.25, "ltp": 130.0}
        put_info = {"symbol": "NIFTY27NOV2622500PE", "lot_size": 65, "strike": 22500, "expiry": "27-Nov-26", "delta": 0.07, "ltp": 24.5}

        success = self.engine.execute_entry(fut_info, opt_info, put_info=put_info)
        self.assertTrue(success)
        self.assertEqual(self.mock_client.placeorder.call_count, 3)

        pos = self.engine.state.get("active_position")
        self.assertIsNotNone(pos)
        self.assertEqual(pos["fut_symbol"], "NIFTY27NOV26FUT")
        self.assertEqual(pos["call_symbol"], "NIFTY27NOV2624200CE")
        self.assertEqual(pos["put_symbol"], "NIFTY27NOV2622500PE")
        self.assertEqual(pos["fut_entry_price"], 23500.0)
        self.assertEqual(pos["call_entry_price"], 130.0)
        self.assertEqual(pos["put_entry_price"], 24.5)
        self.assertEqual(pos["roll_count"], 0)
        self.assertEqual(pos["realized_opt_pnl"], 0.0)
        self.assertEqual(pos["roll_history"], [])

    # ==========================================================================
    # TEST 2: Auto-Adoption of 3-Leg Collar
    # ==========================================================================
    def test_02_broker_reconciliation_adopts_3leg_collar(self):
        """Strategy starts FLAT; broker holds 1 Fut, 1 Short Call, 1 Long Put -> Adopt 3-leg collar."""
        self.engine.state["active_position"] = None
        self.mock_client.positionbook.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY27NOV26FUT", "exchange": "NFO", "instrumenttype": "FUTIDX", "quantity": 65, "average_price": 23500.0},
                {"symbol": "NIFTY27NOV2624200CE", "exchange": "NFO", "quantity": -65, "average_price": 135.0},
                {"symbol": "NIFTY27NOV2622500PE", "exchange": "NFO", "quantity": 65, "average_price": 26.0},
            ],
        }
        self.mock_client.orderbook.return_value = {
            "status": "success",
            "data": {"statistics": {"total_open_orders": 0, "total_trigger_pending_orders": 0}},
        }

        safe, msg, data = self.engine.reconcile_broker_positions()
        self.assertTrue(safe)
        self.assertIn("defensive collar adopted", msg.lower())

        pos = self.engine.state.get("active_position")
        self.assertIsNotNone(pos)
        self.assertEqual(pos["fut_symbol"], "NIFTY27NOV26FUT")
        self.assertEqual(pos["call_symbol"], "NIFTY27NOV2624200CE")
        self.assertEqual(pos["put_symbol"], "NIFTY27NOV2622500PE")

    # ==========================================================================
    # TEST 3: Dynamic Intra-Cycle Rolling Trigger — Decay Harvest
    # ==========================================================================
    def test_03_evaluate_risk_triggers_decay_harvest_roll(self):
        """When Call decays by >= 80% (harvest_decay_pct) with DTE >= 15, trigger ROLL_HARVEST."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23500.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2624200CE",
            "call_entry_price": 140.0,
            "call_qty": 65,
            "target_price": 14.0,  # 90% decay
            "stoploss_price": 420.0,  # 3.0x SL
            "put_symbol": "NIFTY27NOV2622500PE",
            "put_entry_price": 25.0,
            "put_qty": 65,
            "realized_opt_pnl": 0.0,
        }

        # 80% decay on 140.0 = 28.0. At 25.0, decay is > 80%
        # DTE = 20 (>= roll_min_dte=15)
        spot = 23600.0
        curr_call_px = 25.0
        curr_put_px = 12.0
        dte_left = 20

        should_action, reason = self.engine.evaluate_risk_and_exits(
            spot=spot,
            curr_call_price=curr_call_px,
            dte_left=dte_left,
            curr_put_price=curr_put_px,
        )
        self.assertTrue(should_action)
        self.assertEqual(reason, "ROLL_HARVEST")

    # ==========================================================================
    # TEST 4: Dynamic Intra-Cycle Rolling Trigger — Rally Defense
    # ==========================================================================
    def test_04_evaluate_risk_triggers_rally_defense_roll(self):
        """When Call surges to 3.0x stoploss with DTE >= 15, trigger ROLL_RALLY."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23500.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2624200CE",
            "call_entry_price": 140.0,
            "call_qty": 65,
            "target_price": 14.0,
            "stoploss_price": 420.0,
            "put_symbol": "NIFTY27NOV2622500PE",
            "put_entry_price": 25.0,
            "put_qty": 65,
            "realized_opt_pnl": 0.0,
        }

        spot = 24400.0
        curr_call_px = 425.0  # Above 420.0 SL
        curr_put_px = 5.0
        dte_left = 18

        should_action, reason = self.engine.evaluate_risk_and_exits(
            spot=spot,
            curr_call_price=curr_call_px,
            dte_left=dte_left,
            curr_put_price=curr_put_px,
        )
        self.assertTrue(should_action)
        self.assertEqual(reason, "ROLL_RALLY")

    # ==========================================================================
    # TEST 5: roll_short_call Execution (Harvest)
    # ==========================================================================
    def test_05_roll_short_call_harvest_locks_profit_and_updates_strike(self):
        """roll_short_call closes old call, sells new 0.25 delta call, records roll history."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23500.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2624200CE",
            "call_strike": 24200.0,
            "call_expiry": "27-Nov-26",
            "call_entry_price": 140.0,
            "call_qty": 65,
            "call_delta": 0.25,
            "target_price": 14.0,
            "stoploss_price": 420.0,
            "put_symbol": "NIFTY27NOV2622500PE",
            "put_entry_price": 25.0,
            "put_qty": 65,
            "realized_opt_pnl": 0.0,
            "roll_count": 0,
            "roll_history": [],
            "roll_dte": 10,
            "mode": "ANALYZE",
        }

        # Mock discovery of new call
        new_call_info = {
            "symbol": "NIFTY27NOV2624400CE",
            "strike": 24400.0,
            "expiry": "27-Nov-26",
            "dte": 18,
            "delta": 0.25,
            "ltp": 125.0,
            "lot_size": 65,
        }
        self.engine.find_target_call_option = MagicMock(return_value=new_call_info)

        # Mock orders for roll: buyback old call, sell new call
        r_buy = {"status": "success", "orderid": "ORD_BUYBACK"}
        r_sell = {"status": "success", "orderid": "ORD_NEW_CALL"}
        self.mock_client.placeorder.side_effect = [r_buy, r_sell]
        self.mock_client.orderstatus.side_effect = [
            {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 26.0}},
            {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 125.0}},
        ]

        success = self.engine.roll_short_call(spot=23800.0, reason="ROLL_HARVEST")
        self.assertTrue(success)

        pos = self.engine.state["active_position"]
        # Expected call PnL on old call: (140.0 - 26.0) * 65 = 114.0 * 65 = +7,410.0
        self.assertEqual(pos["call_symbol"], "NIFTY27NOV2624400CE")
        self.assertEqual(pos["call_entry_price"], 125.0)
        self.assertEqual(pos["call_strike"], 24400.0)
        self.assertEqual(pos["roll_count"], 1)
        self.assertEqual(pos["realized_opt_pnl"], 7410.0)
        self.assertEqual(len(pos["roll_history"]), 1)
        self.assertEqual(pos["roll_history"][0]["reason"], "ROLL_HARVEST")
        self.assertEqual(pos["roll_history"][0]["call_pnl"], 7410.0)

    # ==========================================================================
    # TEST 6: execute_exit Across All 3 Legs
    # ==========================================================================
    def test_06_execute_exit_closes_all_3_legs_and_archives_history(self):
        """execute_exit closes Long Fut (SELL), Short Call (BUY), and Long Put (SELL)."""
        self.engine.state["active_position"] = {
            "entry_time": "2026-11-01 09:30:00 IST",
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 23500.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2624400CE",
            "call_entry_price": 125.0,
            "call_qty": 65,
            "put_symbol": "NIFTY27NOV2622500PE",
            "put_entry_price": 25.0,
            "put_qty": 65,
            "realized_opt_pnl": 7410.0,
            "roll_count": 1,
            "roll_history": [{"roll_num": 1}],
        }
        self.engine.reconcile_broker_positions = MagicMock(return_value=(True, "Safe", {}))

        r_fut = {"status": "success", "orderid": "EXIT_FUT"}
        r_call = {"status": "success", "orderid": "EXIT_CALL"}
        r_put = {"status": "success", "orderid": "EXIT_PUT"}
        self.mock_client.placeorder.side_effect = [r_fut, r_call, r_put]
        self.mock_client.orderstatus.side_effect = [
            {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 23800.0}},
            {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 8.0}},
            {"status": "success", "data": {"order_status": "complete", "filled_quantity": 65, "average_price": 4.0}},
        ]

        success = self.engine.execute_exit(
            reason="ROLL_THRESHOLD_REACHED",
            curr_fut_price=23800.0,
            curr_opt_price=8.0,
            curr_put_price=4.0,
        )
        self.assertTrue(success)
        self.assertEqual(self.mock_client.placeorder.call_count, 3)

        # State should be reset to FLAT
        self.assertIsNone(self.engine.state.get("active_position"))

        # History should have 1 record with all legs calculated
        history = self.engine.state.get("trade_history", [])
        self.assertEqual(len(history), 1)
        rec = history[0]
        # Fut PnL: (23800 - 23500) * 65 = +19,500
        # Call PnL: (125 - 8) * 65 = +7,605
        # Put PnL: (4 - 25) * 65 = -1,365
        # Roll PnL: +7,410
        # Total PnL: 19500 + 7605 - 1365 + 7410 = +33,150.0
        self.assertEqual(rec["fut_pnl"], 19500.0)
        self.assertEqual(rec["opt_pnl"], 7605.0)
        self.assertEqual(rec["put_pnl"], -1365.0)
        self.assertEqual(rec["accumulated_opt_pnl"], 7410.0)
        self.assertEqual(rec["total_pnl"], 33150.0)
        self.assertEqual(self.engine.state.get("total_realized_pnl"), 33150.0)

    # ==========================================================================
    # TEST 7: Whipsaw Immunity — Protective Put Bypasses Fut Stop Loss
    # ==========================================================================
    def test_07_collar_mode_bypasses_fut_stoploss_whipsaw(self):
        """When protective put is active, intraday futures dip > 2% does NOT trigger whipsaw stop."""
        self.engine.state["active_position"] = {
            "fut_symbol": "NIFTY27NOV26FUT",
            "fut_entry_price": 24000.0,
            "fut_qty": 65,
            "call_symbol": "NIFTY27NOV2624600CE",
            "call_entry_price": 130.0,
            "call_qty": 65,
            "target_price": 13.0,
            "stoploss_price": 390.0,
            "put_symbol": "NIFTY27NOV2623000PE",
            "put_entry_price": 25.0,
            "put_qty": 65,
            "realized_opt_pnl": 0.0,
        }

        # Futures drop 2.3% (24000 -> 23450) <= -2.0% futures stoploss
        spot = 23450.0
        curr_call_px = 35.0
        # Protective put surges to 350, keeping net_m2m (-8,450) safely within max_m2m_cap (20k)
        curr_put_px = 350.0
        dte_left = 22

        should_action, reason = self.engine.evaluate_risk_and_exits(
            spot=spot,
            curr_call_price=curr_call_px,
            dte_left=dte_left,
            curr_put_price=curr_put_px,
        )
        # Because protective put is active and collar is enabled, futures stop is bypassed!
        self.assertFalse(should_action)
        self.assertEqual(reason, "")


if __name__ == "__main__":
    unittest.main()
