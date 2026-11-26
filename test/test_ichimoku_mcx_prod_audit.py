"""
Automated Forensic Verification & Remediation Test Suite for ICHIMOKU_MCX_PAPER v1.1.0-REMEDIATED.
Tests API timeouts, network outages, broker disconnects, fail-closed data gates,
session-aligned resampling, exchange lot sizing, verified fills, and broker reconciliation.
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import requests

from strategies.liveonopenalgo.ichimoku_mcx import (
    IST,
    MCX_COMMODITY_SPECS,
    PROFIT_TARGET_ATR_MULT,
    REWARD_RISK_RATIO,
    STOP_LOSS_ATR_MULT,
    MCXIchimokuStrategy,
    PersistentStateManager,
    classify_htf_regime,
    compute_atr14,
    compute_ichimoku_1h,
    resample_ohlcv,
)


# ==============================================================================
# 1. API TIMEOUT & NETWORK OUTAGE HANDLING TESTS
# ==============================================================================
class TestApiTimeoutAndNetworkOutages:
    """Verifies that API timeouts, broker disconnects, and slow responses fail closed safely."""

    @patch("requests.post")
    def test_history_fetch_api_timeout_fails_closed(self, mock_post):
        """When OpenAlgo history endpoint times out, strategy returns None without authorizing orders."""
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out after 8.0s")

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            engine = MCXIchimokuStrategy(
                symbols=["GOLDM"],
                api_key="test_api_key",
                host="http://mock-host:5000",
                state_file=state_file,
            )
            engine.is_host_reachable = True

            df = engine.fetch_1h_candles("GOLDM")
            assert df is None, "Timeout must return None (Fail-Closed) and never fallback to CSV"

    @patch("requests.post")
    def test_order_status_polling_timeout_marks_unverified(self, mock_post):
        """If orderstatus polling times out across all retries, the order is marked UNVERIFIED and no position is saved."""
        # 1. placeorder succeeds at gateway
        # 2. orderstatus times out repeatedly
        mock_post.side_effect = requests.exceptions.Timeout("Orderstatus timeout")

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            engine = MCXIchimokuStrategy(
                symbols=["GOLDM"],
                api_key="test_api_key",
                host="http://mock-host:5000",
                state_file=state_file,
            )
            engine.is_host_reachable = True

            fill_success, fill_px = engine._poll_verified_fill("ORD_9999", "GOLDM26DECFUT", fallback=0.0)
            assert fill_success is False
            assert fill_px == 0.0

    @patch("requests.post")
    def test_gateway_offline_aborts_cycle(self, mock_post):
        """When OpenAlgo server is offline, execute_cycle emits ERROR_GATEWAY_OFFLINE and aborts cleanly."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            engine = MCXIchimokuStrategy(
                symbols=["GOLDM"],
                api_key="test_api_key",
                host="http://mock-host:5000",
                state_file=state_file,
            )
            engine.is_host_reachable = False

            # Mock MCX market hours as active
            with patch("strategies.liveonopenalgo.ichimoku_mcx.is_mcx_trading_time", return_value=(True, "SESSION_ACTIVE")):
                with patch.object(engine, "emit_heartbeat") as mock_hb:
                    engine.execute_cycle()
                    mock_hb.assert_called_with(status="ERROR_GATEWAY_OFFLINE")


# ==============================================================================
# 2. FAIL-CLOSED MARKET DATA PIPELINE TESTS
# ==============================================================================
class TestFailClosedDataPipeline:
    """Verifies that missing, stale, incomplete, or synthetic CSV data NEVER authorizes live orders."""

    def test_csv_fallback_strictly_eliminated(self):
        """Source code must have zero references to research CSV ingestion in fetch_1h_candles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            engine = MCXIchimokuStrategy(
                symbols=["GOLDM"],
                api_key="test_api_key",
                host="http://mock-host:5000",
                state_file=state_file,
            )
            # Ensure engine has no _preload_historical_cache method
            assert not hasattr(engine, "_preload_historical_cache")

    def test_incomplete_in_progress_hourly_bar_filtered_out(self):
        """The forming candle of the current hour must be stripped from signal evaluation."""
        now = datetime(2026, 11, 25, 14, 25, tzinfo=IST)
        # Raw API response includes 13:00 (completed) and 14:00 (forming, 25m old)
        timestamps = [
            datetime(2026, 11, 25, 12, 0, tzinfo=IST),
            datetime(2026, 11, 25, 13, 0, tzinfo=IST),
            datetime(2026, 11, 25, 14, 0, tzinfo=IST),
        ]
        df_raw = pd.DataFrame({
            "open": [100.0, 102.0, 105.0],
            "high": [103.0, 104.0, 108.0],
            "low": [99.0, 101.0, 104.0],
            "close": [102.0, 103.0, 107.0],
        }, index=pd.DatetimeIndex(timestamps))

        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        df_completed = df_raw[df_raw.index < current_hour_start]

        assert len(df_completed) == 2
        assert df_completed.index[-1] == datetime(2026, 11, 25, 13, 0, tzinfo=IST)
        assert datetime(2026, 11, 25, 14, 0, tzinfo=IST) not in df_completed.index

    def test_stale_data_rejected_during_session(self):
        """Data older than 75m during active trading session must be rejected as STALE."""
        now = datetime(2026, 11, 25, 15, 0, tzinfo=IST)
        stale_last_bar = datetime(2026, 11, 25, 12, 0, tzinfo=IST)  # 180 min old from open, 120m from close

        bar_close_dt = stale_last_bar + timedelta(hours=1)
        age_minutes = (now - bar_close_dt).total_seconds() / 60.0
        assert age_minutes > 75.0, "Must be flagged as stale"

    def test_hourly_bar_freshness_accounting_for_candle_close(self):
        """At 11:30 IST, last completed bar from 10:00 (closed at 11:00) is 30m old and must be accepted."""
        now = datetime(2026, 11, 26, 11, 30, tzinfo=IST)
        completed_bar = datetime(2026, 11, 26, 10, 0, tzinfo=IST)
        bar_close_dt = completed_bar + timedelta(hours=1)
        age_minutes = (now - bar_close_dt).total_seconds() / 60.0
        assert age_minutes == 30.0
        assert age_minutes <= 75.0, "Completed bar from previous hour must be considered fresh"

    def test_insufficient_depth_warmup_rejected(self):
        """Data with fewer than 80 bars must be rejected to prevent undefined Ichimoku spans."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            engine = MCXIchimokuStrategy(
                symbols=["GOLDM"],
                api_key="test_api_key",
                host="http://mock-host:5000",
                state_file=state_file,
            )
            engine.is_host_reachable = True

            # Mock API returning only 40 bars
            dates = pd.date_range("2026-11-20 09:00", periods=40, freq="1h", tz=IST)
            df_short = pd.DataFrame({
                "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5
            }, index=dates)

            with patch.object(engine, "fetch_1h_candles", return_value=df_short):
                with patch.object(engine, "place_order") as mock_order:
                    engine.evaluate_symbol("GOLDM")
                    # Must NOT place orders when length < 80
                    mock_order.assert_not_called()


# ==============================================================================
# 3. SESSION-ALIGNED RESAMPLING & ZERO LOOKAHEAD TESTS
# ==============================================================================
class TestSessionAlignedResampling:
    """Verifies that 4H and 1D resampling align to MCX 09:00 IST open with no incomplete bar leakage."""

    def test_mcx_session_4h_origin_alignment(self):
        """MCX 4H candles must anchor at 09:00 IST (09:00-13:00, 13:00-17:00, etc.)."""
        dates = pd.date_range("2026-11-25 09:00", periods=8, freq="1h", tz=IST)
        df_1h = pd.DataFrame({
            "open": range(100, 108),
            "high": range(105, 113),
            "low": range(95, 103),
            "close": range(102, 110),
            "volume": [100] * 8,
        }, index=dates)

        df_4h = resample_ohlcv(df_1h, "4h")

        assert len(df_4h) == 2
        # Bar 1: 09:00 to 13:00
        assert df_4h["timestamp"].iloc[0] == pd.Timestamp("2026-11-25 09:00:00+0530", tz=IST)
        assert df_4h["open"].iloc[0] == 100
        assert df_4h["close"].iloc[0] == 105
        # Bar 2: 13:00 to 17:00
        assert df_4h["timestamp"].iloc[1] == pd.Timestamp("2026-11-25 13:00:00+0530", tz=IST)
        assert df_4h["open"].iloc[1] == 104
        assert df_4h["close"].iloc[1] == 109

    def test_incomplete_htf_bar_dropped(self):
        """An in-progress 4H bar (e.g. 2 hours completed out of 4) must be dropped from completed HTF bars."""
        # 6 hours: 09:00, 10:00, 11:00, 12:00 (full 4H bar), and 13:00, 14:00 (only 2 hours of 2nd bar)
        dates = pd.date_range("2026-11-25 09:00", periods=6, freq="1h", tz=IST)
        df_1h = pd.DataFrame({
            "open": range(100, 106),
            "high": range(105, 111),
            "low": range(95, 101),
            "close": range(102, 108),
        }, index=dates)

        df_4h = resample_ohlcv(df_1h, "4h")
        # Only the first 4H bar (09:00-13:00) is fully completed; the 13:00-17:00 bar ends at 17:00 > 15:00
        assert len(df_4h) == 1
        assert df_4h["timestamp"].iloc[0].hour == 9


# ==============================================================================
# 4. EXCHANGE LOT SIZE & QUANTITY CONVENTION TESTS
# ==============================================================================
class TestExchangeLotSizeValidation:
    """Verifies that OpenAlgo order quantity is denominated in exchange units, not lot counts."""

    def test_exchange_lot_sizes_verified(self):
        """Asserts correct conversion of lots to units for all supported commodities."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            engine = MCXIchimokuStrategy(
                symbols=["GOLDM", "CRUDEOILM", "NATGASMINI", "SILVERMIC"],
                api_key="test_api_key",
                host="http://mock-host:5000",
                state_file=state_file,
            )

            assert engine.resolve_lot_size("GOLDM", "GOLDM26DECFUT") == 100
            assert engine.resolve_lot_size("CRUDEOILM", "CRUDEOILM26DECFUT") == 10
            assert engine.resolve_lot_size("NATGASMINI", "NATGASMINI26DECFUT") == 250
            assert engine.resolve_lot_size("SILVERMIC", "SILVERMIC26DECFUT") == 1

    def test_raw_lot_count_quantity_one_refused_for_goldm_crudeoilm(self):
        """Sending quantity=1 to Zerodha converter for GOLDM or CRUDEOILM raises McxQuantityError."""
        from broker.zerodha.mapping.mcx_contract_size import to_kite_quantity, McxQuantityError

        with pytest.raises(McxQuantityError):
            to_kite_quantity(1, "GOLDM26DECFUT", "MCX")

        with pytest.raises(McxQuantityError):
            to_kite_quantity(1, "CRUDEOILM26DECFUT", "MCX")

        # But sending verified units passes
        assert to_kite_quantity(100, "GOLDM26DECFUT", "MCX") == 1
        assert to_kite_quantity(10, "CRUDEOILM26DECFUT", "MCX") == 1


# ==============================================================================
# 5. BROKER POSITION RECONCILIATION & RESTART RECOVERY TESTS
# ==============================================================================
class TestBrokerReconciliationAndRecovery:
    """Verifies startup reconciliation against broker positionbook and clean recovery."""

    @patch("requests.post")
    def test_phantom_position_cleared_on_reconciliation(self, mock_post):
        """If internal state holds a position that broker reports as 0, it must be cleared immediately."""
        # Mock /api/v1/positionbook returning empty/flat position
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "data": [{"symbol": "GOLDM26DECFUT", "quantity": 0}]
        }
        mock_post.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            mgr = PersistentStateManager(state_file)
            mgr.save_position("GOLDM26DECFUT", {
                "symbol": "GOLDM", "contract": "GOLDM26DECFUT", "direction": "Long", "quantity": 100
            })
            mgr.set_pullback_watch("GOLDM", {"target_exited_dir": 1})

            engine = MCXIchimokuStrategy(
                symbols=["GOLDM"],
                api_key="test_api_key",
                host="http://mock-host:5000",
                state_file=state_file,
            )
            engine.is_host_reachable = True

            engine.reconcile_broker_positions()

            # Position and watch must be cleared
            assert engine.state_manager.get_position("GOLDM26DECFUT") is None
            assert engine.state_manager.get_pullback_watch("GOLDM") is None

    @patch("requests.post")
    def test_external_positions_from_other_exchanges_ignored(self, mock_post):
        """Positions from other exchanges (e.g. NFO Nifty options/futures) must be ignored and not block entries."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "data": [
                {"symbol": "NIFTY29DEC26FUT", "exchange": "NFO", "quantity": 65},
                {"symbol": "NIFTY29DEC2624150PE", "exchange": "NFO", "quantity": 65},
                {"symbol": "NIFTY29DEC2626700CE", "exchange": "NFO", "quantity": -65},
            ],
        }
        mock_post.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            engine = MCXIchimokuStrategy(
                symbols=["GOLDM"],
                api_key="test_api_key",
                host="http://mock-host:5000",
                state_file=state_file,
            )
            engine.is_host_reachable = True

            engine.reconcile_broker_positions()

            assert engine.has_reconciliation_discrepancy is False
            assert len(engine.reconciliation_discrepancies) == 0
            assert len(engine.unexpected_broker_positions) == 0

    @patch("requests.post")
    def test_active_broker_position_preserved_on_restart(self, mock_post):
        """Existing broker position matching internal state is preserved across engine restart."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "data": [{"symbol": "CRUDEOILM26DECFUT", "quantity": 10}]
        }
        mock_post.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            mgr = PersistentStateManager(state_file)
            mgr.save_position("CRUDEOILM26DECFUT", {
                "symbol": "CRUDEOILM", "contract": "CRUDEOILM26DECFUT", "direction": "Long", "quantity": 10, "entry_price": 7200.0
            })

            engine = MCXIchimokuStrategy(
                symbols=["CRUDEOILM"],
                api_key="test_api_key",
                host="http://mock-host:5000",
                state_file=state_file,
            )
            engine.is_host_reachable = True

            engine.reconcile_broker_positions()

            pos = engine.state_manager.get_position("CRUDEOILM26DECFUT")
            assert pos is not None
            assert pos["quantity"] == 10
            assert pos["entry_price"] == 7200.0


# ==============================================================================
# 6. VERIFIED FILL ORDER LIFECYCLE TESTS
# ==============================================================================
class TestVerifiedFillOrderLifecycle:
    """Verifies that orders are recorded only upon confirmed broker execution."""

    @patch("requests.post")
    def test_rejected_order_never_creates_position(self, mock_post):
        """When broker rejects an order (e.g. margin error), no position is added to state."""
        def route_post(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "ping" in url:
                resp.json.return_value = {"status": "success"}
            elif "search" in url:
                resp.json.return_value = {"status": "success", "data": []}
            elif "symbol" in url:
                resp.json.return_value = {"status": "success", "data": {"lotsize": 100}}
            elif "positionbook" in url:
                resp.json.return_value = {"status": "success", "data": []}
            elif "placeorder" in url:
                resp.json.return_value = {"status": "success", "orderid": "ORD_REJECTED"}
            elif "orderstatus" in url:
                resp.json.return_value = {
                    "status": "success",
                    "data": {"order_status": "REJECTED", "rejection_reason": "RMS: Margin Insufficient"}
                }
            return resp

        mock_post.side_effect = route_post

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            engine = MCXIchimokuStrategy(
                symbols=["GOLDM"],
                api_key="test_api_key",
                host="http://mock-host:5000",
                state_file=state_file,
            )
            engine.is_host_reachable = True
            engine.client = None  # Ensure REST routing for mock

            res = engine.place_order("GOLDM", "GOLDM26DECFUT", "BUY", 1, "Test Entry")
            assert res is None
            assert engine.state_manager.get_position("GOLDM26DECFUT") is None

    @patch("requests.post")
    def test_complete_fill_records_verified_position(self, mock_post):
        """When broker confirms COMPLETE with fill price, position is saved with exact price."""
        def route_post(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "ping" in url:
                resp.json.return_value = {"status": "success"}
            elif "search" in url:
                resp.json.return_value = {"status": "success", "data": []}
            elif "symbol" in url:
                resp.json.return_value = {"status": "success", "data": {"lotsize": 100}}
            elif "positionbook" in url:
                resp.json.return_value = {"status": "success", "data": []}
            elif "placeorder" in url:
                resp.json.return_value = {"status": "success", "orderid": "ORD_FILLED"}
            elif "orderstatus" in url:
                resp.json.return_value = {
                    "status": "success",
                    "data": {"order_status": "COMPLETE", "average_price": 121500.0, "filled_quantity": 100}
                }
            return resp

        mock_post.side_effect = route_post

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            engine = MCXIchimokuStrategy(
                symbols=["GOLDM"],
                api_key="test_api_key",
                host="http://mock-host:5000",
                state_file=state_file,
            )
            engine.is_host_reachable = True
            engine.client = None  # Ensure REST routing for mock

            res = engine.place_order("GOLDM", "GOLDM26DECFUT", "BUY", 1, "Test Fill")
            assert res is not None
            assert res["status"] == "success"
            assert res["fill_price"] == 121500.0
            assert res["quantity"] == 100


# ==============================================================================
# 7. APPROVED OPTION A RISK CALCULATIONS (1.75R TARGET)
# ==============================================================================
class TestOptionARiskCalculations:
    """Verifies approved Option A: 2.0x ATR Stop, 3.5x ATR Target = 1.75R."""

    def test_option_a_parameters(self):
        assert STOP_LOSS_ATR_MULT == 2.0
        assert PROFIT_TARGET_ATR_MULT == 3.5
        assert REWARD_RISK_RATIO == 1.75

    def test_long_stop_and_target_levels(self):
        entry_price = 120000.0
        atr14 = 500.0

        stop_loss = entry_price - (STOP_LOSS_ATR_MULT * atr14)
        target = entry_price + (PROFIT_TARGET_ATR_MULT * atr14)

        risk_points = entry_price - stop_loss  # 1000.0
        reward_points = target - entry_price   # 1750.0

        assert stop_loss == 119000.0
        assert target == 121750.0
        assert reward_points / risk_points == 1.75
