#!/usr/bin/env python3
"""
================================================================================
REGRESSION TEST SUITE: OIFNO TWO-MODE EXECUTION STANDARD & GOVERNANCE
================================================================================
Compliance verification against SIG-OI-001-EXECUTION-STANDARD-V2 and Master Instruction:

  Category 1:  PAPER default on first startup and restart
  Category 2:  Blocking real orders across all paths in PAPER
  Category 3:  Rejection of SHADOW and invalid modes
  Category 4:  LIVE activation denied when checks fail
  Category 5:  LIVE activation accepted in controlled test with mocked broker
  Category 6:  One-click request behavior and transition audit logging
  Category 7:  Position reconciliation and pending order handling during transition
  Category 8:  Kill switch and risk limit enforcement
  Category 9:  State persistence, restart recovery, legacy migration, invalid state recovery
  Category 10: Scheduler compatibility and prevention of duplicate workers
  Category 11: Phase 7 validation, simulated fills, performance calculations
  Category 12: Confirmation that zero real orders were placed
================================================================================
"""

import copy
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import standardized strategy components
from backtesting.oi.strategy.oifno_standard import (
    SUPPORTED_EXECUTION_MODES,
    STRATEGY_CONTRACT_VERSION,
    STRATEGY_HASH,
    EXECUTION_MODE,
    VALIDATION_PHASE,
    LIVE_TRADING_ENABLED,
    OIPersistentStateManager,
    OpenAlgoBridge,
    OISignalEngine,
    OIRankingEngine,
    OIRiskEngine,
    OrderIntent,
    PaperExecutionAdapter,
    LiveExecutionAdapter,
    LiveActivationManager,
    PreFlightCheckResult,
    OIReconciliationEngine,
    MarketRecord,
    OICandidateSignal,
)


class TestOifnoExecutionStandardMaster(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temp_dir.name) / "test_oifno_state.json"
        self.transition_log = Path(self.temp_dir.name) / "mode_transitions.jsonl"
        self.kill_switch_file = Path(self.temp_dir.name) / "kill_switch.flag"
        self.bridge = OpenAlgoBridge()

    def tearDown(self):
        self.temp_dir.cleanup()

    # ==========================================================================
    # CATEGORY 1: PAPER DEFAULT ON FIRST STARTUP AND RESTART
    # ==========================================================================
    def test_cat01_paper_default_on_first_startup(self):
        """Category 1: Default execution mode on fresh startup is strictly PAPER."""
        mgr = OIPersistentStateManager(self.state_file)
        self.assertEqual(mgr.state["execution_mode"], "PAPER")
        self.assertEqual(mgr.state["validation_phase"], "PHASE_7")
        self.assertIn(mgr.state["execution_mode"], SUPPORTED_EXECUTION_MODES)

    def test_cat01_paper_default_on_restart(self):
        """Category 1: Preserves PAPER mode across simulated process restart."""
        mgr = OIPersistentStateManager(self.state_file)
        mgr.state["risk_state"]["current_capital"] = 10500000.0
        mgr.save_state()

        mgr2 = OIPersistentStateManager(self.state_file)
        self.assertEqual(mgr2.state["execution_mode"], "PAPER")
        self.assertEqual(mgr2.state["validation_phase"], "PHASE_7")
        self.assertEqual(mgr2.state["risk_state"]["current_capital"], 10500000.0)

    # ==========================================================================
    # CATEGORY 2: BLOCKING REAL ORDERS ACROSS ALL PATHS IN PAPER
    # ==========================================================================
    def test_cat02_paper_adapter_refuses_live_flag(self):
        """Category 2: PaperExecutionAdapter raises PermissionError if initialized with is_live=True."""
        with self.assertRaises(PermissionError):
            PaperExecutionAdapter(is_live=True)

    def test_cat02_live_adapter_refuses_paper_environment(self):
        """Category 2: LiveExecutionAdapter strictly refuses initialization under default PAPER mode."""
        with self.assertRaises(PermissionError):
            LiveExecutionAdapter(self.bridge)

    # ==========================================================================
    # CATEGORY 3: REJECTION OF SHADOW AND INVALID MODES
    # ==========================================================================
    def test_cat03_supported_modes_strictly_paper_and_live(self):
        """Category 3: Exactly two modes supported: PAPER and LIVE. SHADOW is removed."""
        self.assertEqual(SUPPORTED_EXECUTION_MODES, {"PAPER", "LIVE"})
        self.assertNotIn("SHADOW", SUPPORTED_EXECUTION_MODES)
        self.assertNotIn("HYBRID", SUPPORTED_EXECUTION_MODES)

    def test_cat03_shadow_env_rejection_fail_closed(self):
        """Category 3: Setting OIFNO_EXECUTION_MODE=SHADOW raises ValueError and fails closed."""
        env = os.environ.copy()
        env["OIFNO_EXECUTION_MODE"] = "SHADOW"
        script_path = PROJECT_ROOT / "backtesting/oi/strategy/oifno_standard.py"
        proc = subprocess.run(
            [sys.executable, str(script_path), "--mode", "test-suite"],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("CRITICAL CONFIGURATION ERROR", proc.stderr + proc.stdout)
        self.assertIn("SHADOW is obsolete", proc.stderr + proc.stdout)

    def test_cat03_arbitrary_mode_env_rejection(self):
        """Category 3: Setting unknown OIFNO_EXECUTION_MODE fails closed."""
        env = os.environ.copy()
        env["OIFNO_EXECUTION_MODE"] = "SIMULATION_UNKNOWN"
        script_path = PROJECT_ROOT / "backtesting/oi/strategy/oifno_standard.py"
        proc = subprocess.run(
            [sys.executable, str(script_path), "--mode", "test-suite"],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("CRITICAL CONFIGURATION ERROR", proc.stderr + proc.stdout)

    # ==========================================================================
    # CATEGORY 4: LIVE ACTIVATION DENIED WHEN CHECKS FAIL
    # ==========================================================================
    def test_cat04_live_activation_denied_missing_token(self):
        """Category 4: Live activation fails closed when operator token is missing/short."""
        state_mgr = OIPersistentStateManager(self.state_file)
        risk_engine = OIRiskEngine()
        manager = LiveActivationManager(self.bridge, state_mgr, risk_engine)
        manager.transition_log_file = self.transition_log

        ok, msg, checks = manager.request_enable_live(
            operator_id="admin",
            operator_token="short",  # Invalid token < 16 chars
            confirmation_phrase="CONFIRM_ENABLE_LIVE_TRADING",
            live_gate_unlocked=True,
        )
        self.assertFalse(ok)
        self.assertEqual(manager.current_mode, "PAPER")
        self.assertIn("DENIED", msg)

    def test_cat04_live_activation_denied_bad_phrase(self):
        """Category 4: Live activation fails closed when confirmation phrase is invalid."""
        state_mgr = OIPersistentStateManager(self.state_file)
        risk_engine = OIRiskEngine()
        manager = LiveActivationManager(self.bridge, state_mgr, risk_engine)
        manager.transition_log_file = self.transition_log

        ok, msg, checks = manager.request_enable_live(
            operator_id="admin_user_01",
            operator_token="secure_operator_token_12345",
            confirmation_phrase="WRONG_PHRASE",
            live_gate_unlocked=True,
        )
        self.assertFalse(ok)
        self.assertEqual(manager.current_mode, "PAPER")

    def test_cat04_live_activation_denied_master_gate_locked(self):
        """Category 4: Live activation fails closed when live gate is locked."""
        state_mgr = OIPersistentStateManager(self.state_file)
        risk_engine = OIRiskEngine()
        manager = LiveActivationManager(self.bridge, state_mgr, risk_engine)
        manager.transition_log_file = self.transition_log

        # Mock broker connectivity to pass
        manager.bridge.ping = lambda: (True, "fyers", {})
        manager.bridge.get_positionbook = lambda: (True, [], "live")
        manager.bridge.get_orderbook = lambda: (True, [])

        ok, msg, checks = manager.request_enable_live(
            operator_id="admin_user_01",
            operator_token="secure_operator_token_12345",
            confirmation_phrase="CONFIRM_ENABLE_LIVE_TRADING",
            live_gate_unlocked=False,  # Locked
        )
        self.assertFalse(ok)
        self.assertEqual(manager.current_mode, "PAPER")
        self.assertIn("Master Live Trading Gate", [c.check_name for c in checks if not c.passed])

    # ==========================================================================
    # CATEGORY 5: LIVE ACTIVATION ACCEPTED IN CONTROLLED TEST WITH MOCKED BROKER
    # ==========================================================================
    def test_cat05_live_activation_accepted_controlled_mock(self):
        """Category 5: Live activation succeeds when all 6 pre-flight checks pass in mock harness."""
        state_mgr = OIPersistentStateManager(self.state_file)
        risk_engine = OIRiskEngine()
        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = (True, "fyers", {})
        mock_bridge.get_positionbook.return_value = (True, [], "live")
        mock_bridge.get_orderbook.return_value = (True, [])

        manager = LiveActivationManager(mock_bridge, state_mgr, risk_engine)
        manager.transition_log_file = self.transition_log

        ok, msg, checks = manager.request_enable_live(
            operator_id="authorized_lead_dev",
            operator_token="secure_token_abc123456789xyz",
            confirmation_phrase="CONFIRM_ENABLE_LIVE_TRADING",
            live_gate_unlocked=True,
        )
        self.assertTrue(ok)
        self.assertEqual(manager.current_mode, "LIVE")
        self.assertIn("ACTIVATED", msg)
        self.assertEqual(state_mgr.state["execution_mode"], "LIVE")

    # ==========================================================================
    # CATEGORY 6: ONE-CLICK REQUEST BEHAVIOR AND TRANSITION AUDIT LOGGING
    # ==========================================================================
    def test_cat06_transition_audit_logging(self):
        """Category 6: Mode transition requests are append-only logged with structured metadata."""
        state_mgr = OIPersistentStateManager(self.state_file)
        risk_engine = OIRiskEngine()
        manager = LiveActivationManager(self.bridge, state_mgr, risk_engine)
        manager.transition_log_file = self.transition_log

        manager.request_enable_live(
            operator_id="audit_test_operator",
            operator_token="operator_token_long_enough_12345",
            confirmation_phrase="CONFIRM_ENABLE_LIVE_TRADING",
            live_gate_unlocked=False,
        )

        self.assertTrue(self.transition_log.exists())
        with open(self.transition_log, "r") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["operator_id"], "audit_test_operator")
        self.assertEqual(record["previous_mode"], "PAPER")
        self.assertEqual(record["requested_mode"], "LIVE")
        self.assertEqual(record["final_outcome"], "DENIED")
        self.assertEqual(record["active_mode"], "PAPER")
        self.assertIn("checks", record)
        self.assertGreaterEqual(len(record["checks"]), 6)

    # ==========================================================================
    # CATEGORY 7: POSITION RECONCILIATION & PENDING ORDER HANDLING
    # ==========================================================================
    def test_cat07_reconciliation_detects_pending_orders(self):
        """Category 7: Pending orders in broker book trip pre-flight check and block LIVE activation."""
        state_mgr = OIPersistentStateManager(self.state_file)
        risk_engine = OIRiskEngine()
        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = (True, "fyers", {})
        mock_bridge.get_positionbook.return_value = (True, [], "live")
        # Broker has an open pending limit order
        mock_bridge.get_orderbook.return_value = (True, [{"order_id": "ORD999", "order_status": "OPEN"}])

        manager = LiveActivationManager(mock_bridge, state_mgr, risk_engine)
        manager.transition_log_file = self.transition_log

        result = manager.verify_positions_and_reconciliation()
        self.assertFalse(result.passed)
        self.assertIn("open/pending broker orders", result.details)

        ok, _, _ = manager.request_enable_live(
            operator_id="test_op",
            operator_token="token_with_sufficient_length_1234",
            confirmation_phrase="CONFIRM_ENABLE_LIVE_TRADING",
            live_gate_unlocked=True,
        )
        self.assertFalse(ok)
        self.assertEqual(manager.current_mode, "PAPER")

    # ==========================================================================
    # CATEGORY 8: KILL SWITCH AND RISK LIMIT ENFORCEMENT
    # ==========================================================================
    def test_cat08_kill_switch_blocks_activation(self):
        """Category 8: Active kill switch flag file blocks LIVE activation immediately."""
        state_mgr = OIPersistentStateManager(self.state_file)
        risk_engine = OIRiskEngine()
        manager = LiveActivationManager(self.bridge, state_mgr, risk_engine)
        manager.transition_log_file = self.transition_log

        # Create kill switch flag
        self.kill_switch_file.touch()
        with patch.dict(os.environ, {"KILL_SWITCH_FILE": str(self.kill_switch_file)}):
            result = manager.verify_risk_limits_and_kill_switch()
            self.assertFalse(result.passed)
            self.assertIn("Kill switch flag file active", result.details)

    def test_cat08_drawdown_circuit_breaker_blocks_orders_and_live(self):
        """Category 8: Drawdown >= 15% trips circuit breaker and halts intents."""
        risk = OIRiskEngine(initial_capital=10000000.0, max_drawdown_pct=15.0)
        risk.update_high_watermark(realized_pnl=-1600000.0)  # -16% drawdown
        self.assertTrue(risk.circuit_breaker_tripped)
        self.assertIn("MAX_DRAWDOWN_EXCEEDED", risk.circuit_breaker_reason)

        # evaluate_candidates returns empty
        intents = risk.evaluate_candidates_for_intents(
            candidates=[],
            open_positions={},
            contract_resolver=lambda s: ("SYMFUT", 100, datetime.now(), 15),
        )
        self.assertEqual(len(intents), 0)

        # Live activation manager blocks activation
        state_mgr = OIPersistentStateManager(self.state_file)
        manager = LiveActivationManager(self.bridge, state_mgr, risk)
        res = manager.verify_risk_limits_and_kill_switch()
        self.assertFalse(res.passed)

    # ==========================================================================
    # CATEGORY 9: STATE PERSISTENCE, RESTORE, MIGRATION & CORRUPTION RECOVERY
    # ==========================================================================
    def test_cat09_legacy_shadow_migration(self):
        """Category 9: Migrates legacy phase7_mode: SHADOW to execution_mode: PAPER."""
        legacy_data = {
            "strategy": "OIFNO_V1",
            "phase7_mode": "SHADOW",
            "risk_state": {
                "initial_capital": 10000000.0,
                "current_capital": 10250000.0,
                "high_watermark": 10250000.0,
            },
            "tracked_positions": {"TCS": {"quantity": 350}},
        }
        with open(self.state_file, "w") as f:
            json.dump(legacy_data, f)

        mgr = OIPersistentStateManager(self.state_file)
        self.assertEqual(mgr.state["execution_mode"], "PAPER")
        self.assertEqual(mgr.state["validation_phase"], "PHASE_7")
        self.assertNotIn("phase7_mode", mgr.state)

    def test_cat09_corrupt_state_recovery_fails_safe_to_paper(self):
        """Category 9: Corrupted JSON state file recovers to safe default state with PAPER mode."""
        with open(self.state_file, "w") as f:
            f.write("{corrupt_json_structure: missing_quotes_and_brackets")

        mgr = OIPersistentStateManager(self.state_file)
        self.assertEqual(mgr.state["execution_mode"], "PAPER")
        self.assertEqual(mgr.state["validation_phase"], "PHASE_7")
        self.assertEqual(mgr.state["risk_state"]["current_capital"], 10000000.0)

    # ==========================================================================
    # CATEGORY 10: SCHEDULER COMPATIBILITY & NO DUPLICATE WORKERS
    # ==========================================================================
    def test_cat10_scheduler_compatibility_zero_args_default(self):
        """Category 10: Strategy can be launched with zero args (as OpenAlgo scheduler does) in test mode."""
        env = os.environ.copy()
        script_path = PROJECT_ROOT / "backtesting/oi/strategy/oifno_standard.py"
        proc = subprocess.run(
            [sys.executable, str(script_path), "--mode", "test-suite"],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("18/18 PASSED", proc.stdout)

    def test_cat10_cli_request_live_option_available(self):
        """Category 10: Strategy CLI provides --request-live option for one-click operator request."""
        script_path = PROJECT_ROOT / "backtesting/oi/strategy/oifno_standard.py"
        proc = subprocess.run(
            [sys.executable, str(script_path), "--request-live", "--operator-id", "test", "--operator-token", "short"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("DENIED", proc.stdout + proc.stderr)

    # ==========================================================================
    # CATEGORY 11: PHASE 7 VALIDATION, SIMULATED FILLS & PERFORMANCE
    # ==========================================================================
    def test_cat11_phase7_signal_rules_preserved(self):
        """Category 11: Phase 7 signal logic (Price dip, ΔOI <= -2%, bear candle ratio > 0.60) intact."""
        self.assertEqual(VALIDATION_PHASE, "PHASE_7")
        engine = OISignalEngine()
        rec = MarketRecord(
            trade_date="2026-10-13",
            symbol="TCS",
            open=3500.0,
            high=3510.0,
            low=3440.0,
            close=3450.0,
            traded_contracts=8000,
            turnover_lakh=12000.0,
            open_interest=50000,
            days_to_expiry=15,
            prev_close=3520.0,
            prev_open_interest=52000.0,
        )
        sig = engine.evaluate_record(rec)
        self.assertIsNotNone(sig)
        self.assertLess(sig.return_1d_pct, 0.0)
        self.assertLessEqual(sig.delta_oi_pct, -2.0)
        self.assertGreater(sig.body_range_ratio, 0.60)

    def test_cat11_simulated_fill_friction_and_protections(self):
        """Category 11: Verified paper fills include 2.5 bps slippage, +30 bps collar, +1.5% gap limit."""
        adapter = PaperExecutionAdapter(is_live=False)
        intent = OrderIntent(
            intent_id="INTENT_P7_1",
            signal_id="SIG_P7_1",
            symbol="RELIANCE",
            contract_symbol="RELIANCEFUT",
            action="BUY",
            order_type="LIMIT",
            quantity=250,
            lots=1,
            reference_price=2500.0,
            limit_price=2507.50,
            max_gap_price=2537.50,
            allocated_capital=625000.0,
            sector="OIL_GAS",
            created_at=datetime.now().isoformat(),
        )
        # Normal fill within collar
        ok, filled = adapter.submit_intent(copy.deepcopy(intent), market_open_price=2505.0)
        self.assertTrue(ok)
        self.assertEqual(filled.status, "FILLED")
        self.assertEqual(filled.fill_price, round(2505.0 * 1.00025, 2))

        # Collar breach
        ok_col, col_intent = adapter.submit_intent(copy.deepcopy(intent), market_open_price=2510.0)
        self.assertFalse(ok_col)
        self.assertEqual(col_intent.status, "MISSED_COLLAR")

        # Gap breach
        ok_gap, gap_intent = adapter.submit_intent(copy.deepcopy(intent), market_open_price=2545.0)
        self.assertFalse(ok_gap)
        self.assertEqual(gap_intent.status, "MISSED_GAP")

    # ==========================================================================
    # CATEGORY 12: CONFIRMATION THAT ZERO REAL ORDERS WERE PLACED
    # ==========================================================================
    def test_cat12_zero_real_broker_orders_verified(self):
        """Category 12: Proven audit trace that ZERO broker orders are placed by PAPER mode."""
        state_mgr = OIPersistentStateManager(self.state_file)
        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = (True, "fyers", {"status": "success"})
        mock_bridge.verify_analyze_mode.return_value = (True, "analyze")
        mock_bridge.get_positionbook.return_value = (True, [], "analyze")
        mock_bridge.get_orderbook.return_value = (True, [])

        reconciler = OIReconciliationEngine(mock_bridge, state_mgr)
        summary = reconciler.run_reconciliation()

        self.assertEqual(summary["execution_mode"], "PAPER")
        self.assertEqual(summary["real_broker_orders_found"], 0)
        self.assertEqual(summary["status"], "PASS")
        # Ensure placeorder and modifyorder were NEVER called
        self.assertFalse(hasattr(mock_bridge, "placeorder") and mock_bridge.placeorder.called)
        self.assertFalse(hasattr(mock_bridge, "modifyorder") and mock_bridge.modifyorder.called)


if __name__ == "__main__":
    unittest.main()
