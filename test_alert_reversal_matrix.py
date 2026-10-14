#!/usr/bin/env python3
"""
Test Suite: OpenAlgo & Strategy Telegram Alert + Reversal Verification Matrix
Verifies:
1. Deduplication (OpenAlgo generic alerts skipped for strategy bots)
2. All 10 Transition/Risk Cases:
   1. FLAT -> LONG
   2. FLAT -> SHORT
   3. LONG -> FLAT (Signal Exit)
   4. SHORT -> FLAT (Signal Exit)
   5. LONG -> SHORT during allowed window (Reversal: Exit + Opposite Entry)
   6. LONG -> SHORT during dead zone (Exit to Flat only, no opposite entry)
   7. SHORT -> LONG during dead zone (Exit to Flat only, no opposite entry)
   8. Target Hit (Exit only with P&L)
   9. SL Hit (Exit only with P&L)
   10. Signal Exit (Exit only with P&L)
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure OpenAlgo root is in sys.path
sys.path.insert(0, os.path.abspath("."))

# Mock optional web and external db modules if running in isolated unit test environment
mock_auth_db = MagicMock()
mock_telegram_db = MagicMock()
mock_whatsapp_db = MagicMock()
sys.modules["database.auth_db"] = mock_auth_db
sys.modules["database.telegram_db"] = mock_telegram_db
sys.modules["database.whatsapp_db"] = mock_whatsapp_db
sys.modules["flask_socketio"] = MagicMock()
sys.modules["extensions"] = MagicMock()

import pandas as pd
from datetime import datetime, timezone, timedelta

from subscribers.telegram_subscriber import _send_alert as subscriber_send_alert
from services.telegram_alert_service import TelegramAlertService
from strategies.liveonopenalgo.macdfno import (
    format_trade_alert as macd_format_trade_alert,
    format_paper_exit_alert as macd_format_exit_alert,
    NFOPortfolioLiveTrader,
)
from strategies.liveonopenalgo.emacrossopen import (
    format_paper_trade_alert as ema_format_trade_alert,
    format_paper_exit_alert as ema_format_exit_alert,
    EMACrossPaperTradingEngine,
    is_entry_time_allowed,
)


class TestDuplicateAlertSuppression(unittest.TestCase):
    """Test that OpenAlgo generic Order Placed alerts are suppressed for strategy orders."""

    def test_subscriber_skips_strategy_orders(self):
        with patch("services.telegram_alert_service.telegram_alert_service.send_order_alert") as mock_send:
            # 1. Strategy order with strategy name MACDFNO
            subscriber_send_alert("placeorder", {"strategy": "MACDFNO", "symbol": "NTPC27OCT26FUT"}, {"status": "success"}, "test_api_key")
            mock_send.assert_not_called()

            # 2. Strategy order with strategy name EMACROSSOPEN
            subscriber_send_alert("placeorder", {"strategy": "EMACROSSOPEN", "symbol": "NTPC27OCT26FUT"}, {"status": "success"}, "test_api_key")
            mock_send.assert_not_called()

            # 3. Order with disable_telegram=True
            subscriber_send_alert("placeorder", {"strategy": "CUSTOM", "disable_telegram": True}, {"status": "success"}, "test_api_key")
            mock_send.assert_not_called()

            # 4. Non-strategy generic manual order SHOULD NOT be skipped
            subscriber_send_alert("placeorder", {"strategy": "MANUAL_WEB_UI", "symbol": "RELIANCE"}, {"status": "success"}, "test_api_key")
            mock_send.assert_called_once()

    def test_telegram_alert_service_internal_filter(self):
        svc = TelegramAlertService()
        svc.enabled = True
        with patch.object(svc, "is_bot_active", return_value=True), \
             patch.object(svc, "send_alert_sync") as mock_sync_send, \
             patch("services.telegram_alert_service.get_username_by_apikey", return_value="admin"), \
             patch("services.telegram_alert_service.get_telegram_user_by_username", return_value={"telegram_id": 12345, "notifications_enabled": True}):

            # Strategy order sent to alert service directly
            svc.send_order_alert("placeorder", {"strategy": "Macdfno", "symbol": "NTPC27OCT26FUT"}, {"status": "success"}, "api_key")
            mock_sync_send.assert_not_called()


class TestPositionTransitionsAndAlerts(unittest.TestCase):
    """Test all 10 transition, dead-zone, and risk-exit scenarios."""

    def setUp(self):
        self.dispatched_alerts = []
        self.patchers = [
            patch("strategies.liveonopenalgo.emacrossopen.EMACrossPaperTradingEngine.reconcile_and_audit_positions", return_value=[]),
            patch("strategies.liveonopenalgo.emacrossopen.EMACrossPaperTradingEngine.refresh_contracts", return_value=None),
            patch("strategies.liveonopenalgo.macdfno.NFOPortfolioLiveTrader.reconcile_and_audit_positions", return_value=[]),
            patch("strategies.liveonopenalgo.macdfno.NFOPortfolioLiveTrader.refresh_contracts", return_value=None),
            patch("strategies.liveonopenalgo.macdfno.send_telegram_alert", side_effect=self.mock_send_telegram),
            patch("strategies.liveonopenalgo.emacrossopen.send_telegram_alert", side_effect=self.mock_send_telegram),
            patch("strategies.liveonopenalgo.macdfno.PersistentStateManager.save_state", return_value=None),
            patch("strategies.liveonopenalgo.emacrossopen.PersistentStateManager.save_state", return_value=None),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()

    def mock_send_telegram(self, msg):
        self.dispatched_alerts.append(msg)
        return True

    def test_case_1_flat_to_long(self):
        """Case 1: FLAT -> LONG (New Long Entry Alert)"""
        alert_data = {
            "strategy_name": "Macdfno",
            "contract": "NTPC27OCT26FUT",
            "symbol": "NTPC",
            "direction": "LONG",
            "action": "BUY",
            "quantity": 3000,
            "entry_price": 320.0,
            "trigger_price": 320.0,
            "price_type": "MARKET",
            "exchange": "NFO",
            "product": "NRML",
            "order_id": "ORD_101",
            "order_status": "FILLED",
            "pos_before": 0,
            "pos_after": 3000,
            "execution_time": "10:15:00",
            "candle_time": "2026-10-08 09:15:00+05:30",
            "close": 320.0,
            "macd": 2.5,
            "signal": 1.2,
            "histogram": 1.3,
        }
        msg = macd_format_trade_alert(alert_data)
        self.assertIn("NFO TRADE — ORDER PLACED", msg)
        self.assertIn("Position:</b> 0 ➔ 3000", msg)
        self.assertIn("Entry Price:</b> ₹320.00", msg)
        self.assertNotIn("Order Placed\nStrategy: Macdfno", msg)

    def test_case_2_flat_to_short(self):
        """Case 2: FLAT -> SHORT (New Short Entry Alert)"""
        alert_data = {
            "strategy_name": "Macdfno",
            "contract": "BOSCHLTD27OCT26FUT",
            "symbol": "BOSCHLTD",
            "direction": "SHORT",
            "action": "SELL",
            "quantity": 25,
            "entry_price": 44110.0,
            "trigger_price": 44645.0,
            "price_type": "MARKET",
            "exchange": "NFO",
            "product": "NRML",
            "order_id": "ORD_102",
            "order_status": "FILLED",
            "pos_before": 0,
            "pos_after": -25,
            "execution_time": "10:15:00",
            "candle_time": "2026-10-08 09:15:00+05:30",
            "close": 44110.0,
        }
        msg = macd_format_trade_alert(alert_data)
        self.assertIn("NFO TRADE — ORDER PLACED", msg)
        self.assertIn("Position:</b> 0 ➔ -25", msg)
        self.assertIn("Entry Price:</b> ₹44110.00", msg)

    def test_case_3_long_to_flat_signal_exit(self):
        """Case 3: LONG -> FLAT (Signal Exit)"""
        exit_data = {
            "strategy_name": "Macdfno",
            "contract": "NTPC27OCT26FUT",
            "symbol": "NTPC",
            "direction": "LONG",
            "action": "SELL",
            "exit_reason": "SIGNAL_EXIT",
            "quantity": 3000,
            "entry_price": 320.0,
            "exit_price": 325.0,
            "order_id": "ORD_103",
            "order_status": "FILLED",
            "candle_time": "2026-10-08 11:15:00+05:30",
            "execution_time": "11:17:00",
        }
        msg = macd_format_exit_alert(exit_data)
        self.assertIn("PAPER TRADE — 🔄 SIGNAL EXIT", msg)
        self.assertIn("<b>Exited Direction:</b> <b>LONG</b>", msg)
        self.assertIn("<b>Exit Action:</b> <b>SELL</b>", msg)
        self.assertIn("Net P&L:</b> +₹15,000.00 (+1.56%)", msg)

    def test_case_4_short_to_flat_signal_exit(self):
        """Case 4: SHORT -> FLAT (Signal Exit)"""
        exit_data = {
            "strategy_name": "Macdfno",
            "contract": "BOSCHLTD27OCT26FUT",
            "symbol": "BOSCHLTD",
            "direction": "SHORT",
            "action": "BUY",
            "exit_reason": "SIGNAL_EXIT",
            "quantity": 25,
            "entry_price": 44110.0,
            "exit_price": 43800.0,
            "order_id": "ORD_104",
            "order_status": "FILLED",
            "candle_time": "2026-10-08 11:15:00+05:30",
            "execution_time": "11:17:00",
        }
        msg = macd_format_exit_alert(exit_data)
        self.assertIn("<b>Exited Direction:</b> <b>SHORT</b>", msg)
        self.assertIn("<b>Exit Action:</b> <b>BUY</b>", msg)
        self.assertIn("Net P&L:</b> +₹7,750.00 (+0.70%)", msg)

    def test_case_5_reversal_during_allowed_window(self):
        """Case 5: LONG -> SHORT during allowed entry window (Clean Exit + Opposite Entry)"""
        # Part A: Exit Alert for prior LONG
        exit_payload = {
            "strategy_name": "Emacrossopen",
            "contract": "HINDALCO27OCT26FUT",
            "symbol": "HINDALCO",
            "direction": "LONG",
            "action": "SELL",
            "exit_reason": "V2-2_REVERSAL",
            "quantity": 700,
            "entry_price": 700.0,
            "exit_price": 690.0,
            "order_id": "ORD_105_REV_EXIT",
            "order_status": "FILLED",
            "candle_time_str": "08-Oct-2026 10:15 IST",
            "execution_time": "10:17:00",
        }
        exit_msg = ema_format_exit_alert(exit_payload)
        self.assertIn("PAPER TRADE — 🔄 REVERSAL EXIT", exit_msg)
        self.assertIn("<b>Exited Direction:</b> <b>LONG</b>", exit_msg)
        self.assertIn("Net P&L:</b> -₹7,000.00 (-1.43%)", exit_msg)

        # Part B: Trade Alert for new SHORT
        entry_payload = {
            "strategy_name": "Emacrossopen",
            "contract": "HINDALCO27OCT26FUT",
            "symbol": "HINDALCO",
            "direction": "SHORT",
            "action": "SELL",
            "quantity": 700,
            "entry_price": 690.0,
            "pos_before": 700,
            "pos_after": -700,
            "price_type": "MARKET",
            "order_id": "ORD_105",
            "order_status": "FILLED",
            "execution_time": "10:17:00",
            "candle_time_str": "08-Oct-2026 10:15 IST",
        }
        trade_msg = ema_format_trade_alert(entry_payload)
        self.assertIn("PAPER TRADE — ORDER PLACED", trade_msg)
        self.assertIn("Position:</b> 700 ➔ -700", trade_msg)

    def test_case_6_reversal_during_dead_zone(self):
        """Case 6: LONG -> FLAT during dead zone (14:15 - 15:00) when SHORT entry disallowed"""
        engine = EMACrossPaperTradingEngine(symbols=["HINDALCO"])
        engine.state_manager.state = engine.state_manager._default_state()
        engine.enable_time_filter = True
        engine.use_asymmetric_universe = False

        # Set tracked position = LONG 700
        engine.state_manager.state["tracked_positions"]["HINDALCO27OCT26FUT"] = {
            "contract": "HINDALCO27OCT26FUT",
            "base_symbol": "HINDALCO",
            "direction": "LONG",
            "quantity": 700,
            "average_price": 700.0,
        }
        engine.contract_cache["HINDALCO"] = {"contract": "HINDALCO27OCT26FUT", "lot_size": 700}

        # Mock dead-zone time (14:30 IST)
        dead_time = datetime(2026, 10, 8, 14, 30, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        with patch("strategies.liveonopenalgo.emacrossopen.get_current_ist", return_value=dead_time), \
             patch.object(engine, "get_open_position", return_value=700), \
             patch.object(engine, "place_paper_order", return_value={"status": "success", "orderid": "ORD_DEAD_6"}) as mock_place, \
             patch.object(engine, "get_order_fill_price", return_value=695.0):

            sig_data = {
                "signal": "SELL",
                "candle_time_str": "08-Oct-2026 14:15 IST",
                "timestamp": "2026-10-08T14:15:00+05:30",
                "close": 695.0,
            }
            placed, active = engine.execute_symbol_decision("HINDALCO", sig_data, active_positions_count=1)

            self.assertTrue(placed)
            # Must have placed order for EXACTLY 700 (exit only), NOT 1400 (reversal)
            mock_place.assert_called_once_with(
                symbol="HINDALCO",
                contract_symbol="HINDALCO27OCT26FUT",
                action="SELL",
                quantity=700,
                candle_time="2026-10-08T14:15:00+05:30",
            )
            # Position must now be completely removed / FLAT
            self.assertNotIn("HINDALCO27OCT26FUT", engine.state_manager.state.get("tracked_positions", {}))

            # Exactly ONE alert sent: EXIT alert
            self.assertEqual(len(self.dispatched_alerts), 1)
            self.assertIn("SIGNAL EXIT", self.dispatched_alerts[0])
            self.assertIn("<b>Exited Direction:</b> <b>LONG</b>", self.dispatched_alerts[0])

    def test_case_7_short_to_long_during_dead_zone(self):
        """Case 7: SHORT -> FLAT during dead zone (14:15 - 15:00) when LONG entry disallowed"""
        engine = EMACrossPaperTradingEngine(symbols=["AUBANK"])
        engine.state_manager.state = engine.state_manager._default_state()
        engine.enable_time_filter = True
        engine.use_asymmetric_universe = False

        # Set tracked position = SHORT -1000
        engine.state_manager.state["tracked_positions"]["AUBANK27OCT26FUT"] = {
            "contract": "AUBANK27OCT26FUT",
            "base_symbol": "AUBANK",
            "direction": "SHORT",
            "quantity": -1000,
            "average_price": 600.0,
        }
        engine.contract_cache["AUBANK"] = {"contract": "AUBANK27OCT26FUT", "lot_size": 1000}

        dead_time = datetime(2026, 10, 8, 14, 30, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        with patch("strategies.liveonopenalgo.emacrossopen.get_current_ist", return_value=dead_time), \
             patch.object(engine, "get_open_position", return_value=-1000), \
             patch.object(engine, "place_paper_order", return_value={"status": "success", "orderid": "ORD_DEAD_7"}) as mock_place, \
             patch.object(engine, "get_order_fill_price", return_value=590.0):

            sig_data = {
                "signal": "BUY",
                "candle_time_str": "08-Oct-2026 14:15 IST",
                "timestamp": "2026-10-08T14:15:00+05:30",
                "close": 590.0,
            }
            placed, active = engine.execute_symbol_decision("AUBANK", sig_data, active_positions_count=1)

            self.assertTrue(placed)
            # Must have placed order for EXACTLY 1000 (exit only), NOT 2000 (reversal)
            mock_place.assert_called_once_with(
                symbol="AUBANK",
                contract_symbol="AUBANK27OCT26FUT",
                action="BUY",
                quantity=1000,
                candle_time="2026-10-08T14:15:00+05:30",
            )
            self.assertNotIn("AUBANK27OCT26FUT", engine.state_manager.state.get("tracked_positions", {}))

            # Exactly ONE alert sent: EXIT alert
            self.assertEqual(len(self.dispatched_alerts), 1)
            self.assertIn("SIGNAL EXIT", self.dispatched_alerts[0])
            self.assertIn("<b>Exited Direction:</b> <b>SHORT</b>", self.dispatched_alerts[0])

    def test_case_8_target_hit(self):
        """Case 8: Target Hit Exit Alert"""
        engine = EMACrossPaperTradingEngine(symbols=["NTPC"])
        engine.enable_trailing_runner = False
        engine.state_manager.state = engine.state_manager._default_state()
        engine.state_manager.state["tracked_positions"]["NTPC27OCT26FUT"] = {
            "contract": "NTPC27OCT26FUT",
            "base_symbol": "NTPC",
            "direction": "SHORT",
            "quantity": -3000,
            "average_price": 320.30,
        }
        engine.contract_cache["NTPC"] = {"contract": "NTPC27OCT26FUT", "lot_size": 3000}

        df_candle = pd.DataFrame([
            {"open": 320.0, "high": 321.0, "low": 312.0, "close": 312.85}
        ], index=[pd.Timestamp("2026-10-08 09:15:00+0530")])

        with patch.object(engine, "place_paper_order", return_value={"status": "success", "orderid": "ORD_TGT_8"}) as mock_place, \
             patch.object(engine, "get_order_fill_price", return_value=312.85):

            res = engine.check_and_execute_target_or_sl("NTPC", "NTPC27OCT26FUT", df_candle)
            self.assertTrue(res)
            self.assertEqual(len(self.dispatched_alerts), 1)
            self.assertIn("TARGET HIT", self.dispatched_alerts[0])
            self.assertIn("Net P&L:</b> +₹22,350.00 (+2.33%)", self.dispatched_alerts[0])

    def test_case_9_sl_hit(self):
        """Case 9: Catastrophe SL Hit Exit Alert"""
        engine = EMACrossPaperTradingEngine(symbols=["RELIANCE"])
        engine.state_manager.state = engine.state_manager._default_state()
        engine.state_manager.state["tracked_positions"]["RELIANCE27OCT26FUT"] = {
            "contract": "RELIANCE27OCT26FUT",
            "base_symbol": "RELIANCE",
            "direction": "LONG",
            "quantity": 250,
            "average_price": 3000.0,
        }
        engine.contract_cache["RELIANCE"] = {"contract": "RELIANCE27OCT26FUT", "lot_size": 250}

        # 6% adverse move down to 2800
        df_candle = pd.DataFrame([
            {"open": 2990.0, "high": 3005.0, "low": 2800.0, "close": 2810.0}
        ], index=[pd.Timestamp("2026-10-08 09:15:00+0530")])

        with patch.object(engine, "place_paper_order", return_value={"status": "success", "orderid": "ORD_SL_9"}) as mock_place, \
             patch.object(engine, "get_order_fill_price", return_value=2810.0):

            res = engine.check_and_execute_target_or_sl("RELIANCE", "RELIANCE27OCT26FUT", df_candle)
            self.assertTrue(res)
            self.assertEqual(len(self.dispatched_alerts), 1)
            self.assertIn("CATASTROPHE STOP-LOSS", self.dispatched_alerts[0])
            self.assertIn("Net P&L:</b> -₹47,500.00 (-6.33%)", self.dispatched_alerts[0])

    def test_case_10_signal_exit_macd(self):
        """Case 10: Signal Exit in MACDFNO"""
        trader = NFOPortfolioLiveTrader(symbols=["NTPC"], lots=1)
        trader.state_manager.state = trader.state_manager._default_state()
        trader.sent_alert_orders.clear()
        trader.state_manager.state["tracked_positions"]["NTPC27OCT26FUT"] = {
            "contract": "NTPC27OCT26FUT",
            "base_symbol": "NTPC",
            "direction": "LONG",
            "quantity": 3000,
            "average_price": 310.0,
        }
        trader.contract_cache["NTPC"] = {"contract": "NTPC27OCT26FUT", "lot_size": 3000}

        df_completed = pd.DataFrame({
            "Open": [310.0, 315.0],
            "High": [312.0, 316.0],
            "Low": [309.0, 314.0],
            "Close": [311.0, 315.0],
        }, index=[pd.Timestamp("2026-10-08 09:15:00+0530"), pd.Timestamp("2026-10-08 10:15:00+0530")])

        with patch.object(trader, "place_order", return_value={"status": "success", "orderid": "ORD_SIG_10"}) as mock_place, \
             patch.object(trader, "get_order_fill_price", return_value=315.0):

            trader.dispatch_exit_alert(
                symbol="NTPC",
                contract_symbol="NTPC27OCT26FUT",
                direction="LONG",
                action="SELL",
                exit_reason="SIGNAL_EXIT",
                exec_qty=3000,
                entry_price=310.0,
                exit_price=315.0,
                candle_time="2026-10-08 10:15:00+0530",
                order_resp={"orderid": "ORD_SIG_10"},
            )

            self.assertEqual(len(self.dispatched_alerts), 1)
            self.assertIn("PAPER TRADE — 🔄 SIGNAL EXIT", self.dispatched_alerts[0])
            self.assertIn("Net P&L:</b> +₹15,000.00 (+1.61%)", self.dispatched_alerts[0])


if __name__ == "__main__":
    unittest.main()
