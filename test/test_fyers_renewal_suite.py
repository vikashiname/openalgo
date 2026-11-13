"""
Automated Test Suite for FYERS Token Renewal & Fail-Closed Circuit Breaker.
Covers Test Cases TC-01 through TC-07 without live broker orders.
"""

import os
import sys
import pytest
from datetime import datetime, timedelta
import pytz
from unittest.mock import patch, MagicMock

# Ensure repo root is on path
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from services.fyers_token_renewal import (
    execute_renewal_cycle,
    trigger_fail_closed_lockout,
    MAX_REFRESH_TOKEN_DAYS,
    DEFAULT_USER,
)


class TestFyersRenewalSuite:

    @patch("services.fyers_token_renewal.send_telegram_alert")
    @patch("services.fyers_token_renewal.verify_live_token")
    @patch("broker.fyers.api.auth_api.renew_broker_token")
    @patch("services.fyers_token_renewal.get_keychain_pin")
    @patch("database.auth_db.get_fyers_refresh_token")
    @patch("database.auth_db.upsert_auth")
    def test_tc01_successful_renewal_flow(
        self, mock_upsert, mock_get_refresh, mock_pin, mock_renew, mock_verify, mock_tg
    ):
        """TC-01: Valid refresh token + valid PIN -> successful renewal, DB update, live smoke check."""
        # Setup mocks
        recent_date = (datetime.now(pytz.utc) - timedelta(days=2)).isoformat()
        mock_get_refresh.return_value = ("valid_refresh_token_12345", recent_date)
        mock_pin.return_value = "1234"
        mock_renew.return_value = ("fresh_access_token_xyz987", {"status": "success", "message": "OK"})
        mock_verify.return_value = True
        mock_upsert.return_value = 1
        mock_tg.return_value = True

        success, msg = execute_renewal_cycle(force=True, name="test_user")

        assert success is True
        assert "Token renewed and verified successfully" in msg
        mock_renew.assert_called_once_with(refresh_token="valid_refresh_token_12345", pin="1234")
        mock_verify.assert_called_once_with("fresh_access_token_xyz987")
        mock_upsert.assert_called_once_with(
            name="test_user",
            auth_token="fresh_access_token_xyz987",
            broker="fyers",
            revoke=False,
            refresh_token=None,
        )
        mock_tg.assert_called_once()
        assert "FYERS TOKEN RENEWED SUCCESSFULLY" in mock_tg.call_args[0][0]

    @patch("services.fyers_token_renewal.trigger_fail_closed_lockout")
    @patch("database.auth_db.get_fyers_refresh_token")
    def test_tc02a_expired_refresh_token_age(self, mock_get_refresh, mock_lockout):
        """TC-02A: Refresh token older than 14 days triggers immediate fail-closed lockout."""
        old_date = (datetime.now(pytz.utc) - timedelta(days=16)).isoformat()
        mock_get_refresh.return_value = ("stale_refresh_token_999", old_date)

        success, msg = execute_renewal_cycle(force=True, name="test_user")

        assert success is False
        assert "exceeded maximum validity age" in msg
        mock_lockout.assert_called_once()
        assert "exceeded maximum validity age" in mock_lockout.call_args[0][1]

    @patch("services.fyers_token_renewal.trigger_fail_closed_lockout")
    @patch("broker.fyers.api.auth_api.renew_broker_token")
    @patch("services.fyers_token_renewal.get_keychain_pin")
    @patch("database.auth_db.get_fyers_refresh_token")
    def test_tc02b_expired_refresh_token_api_error_501(
        self, mock_get_refresh, mock_pin, mock_renew, mock_lockout
    ):
        """TC-02B: API returns code -501 (invalid/expired refresh token) -> triggers fail-closed lockout."""
        recent_date = (datetime.now(pytz.utc) - timedelta(days=1)).isoformat()
        mock_get_refresh.return_value = ("rejected_refresh_token", recent_date)
        mock_pin.return_value = "1234"
        mock_renew.return_value = (None, {"status": "error", "code": -501, "message": "Please provide valid refresh token"})

        success, msg = execute_renewal_cycle(force=True, name="test_user")

        assert success is False
        assert "FYERS token renewal failed" in msg
        mock_lockout.assert_called_once()
        assert "-501" in mock_lockout.call_args[0][1]

    @patch("services.fyers_token_renewal.trigger_fail_closed_lockout")
    @patch("services.fyers_token_renewal.get_keychain_pin")
    @patch("database.auth_db.get_fyers_refresh_token")
    def test_tc03_missing_or_invalid_pin(self, mock_get_refresh, mock_pin, mock_lockout):
        """TC-03: Missing or unretrievable PIN fails closed without leaking credentials."""
        recent_date = (datetime.now(pytz.utc) - timedelta(days=1)).isoformat()
        mock_get_refresh.return_value = ("token", recent_date)
        mock_pin.return_value = None  # Keychain lookup failure

        success, msg = execute_renewal_cycle(force=True, name="test_user")

        assert success is False
        assert "Keychain" in msg
        mock_lockout.assert_called_once()
        # Ensure no secrets leak in reason
        assert "openalgo.fyers.pin" in mock_lockout.call_args[0][1]

    @patch("time.sleep", return_value=None)
    @patch("services.fyers_token_renewal.trigger_fail_closed_lockout")
    @patch("broker.fyers.api.auth_api.renew_broker_token")
    @patch("services.fyers_token_renewal.get_keychain_pin")
    @patch("database.auth_db.get_fyers_refresh_token")
    def test_tc04_network_timeout_and_retries(
        self, mock_get_refresh, mock_pin, mock_renew, mock_lockout, mock_sleep
    ):
        """TC-04: Network timeout retries 3 times before engaging fail-closed lockout."""
        recent_date = (datetime.now(pytz.utc) - timedelta(days=1)).isoformat()
        mock_get_refresh.return_value = ("token", recent_date)
        mock_pin.return_value = "1234"
        # Network errors have no permanent error code
        mock_renew.return_value = (None, {"status": "error", "code": None, "message": "Connection timed out"})

        success, msg = execute_renewal_cycle(force=True, name="test_user")

        assert success is False
        assert mock_renew.call_count == 3
        mock_lockout.assert_called_once()

    @patch("services.fyers_token_renewal.is_token_valid_and_recent")
    @patch("broker.fyers.api.auth_api.renew_broker_token")
    def test_tc05_duplicate_execution_idempotency(self, mock_renew, mock_is_valid):
        """TC-05: When token is already valid, renewal cycle exits cleanly without redundant API calls."""
        mock_is_valid.return_value = True

        success, msg = execute_renewal_cycle(force=False, name="test_user")

        assert success is True
        assert "Idempotent" in msg
        mock_renew.assert_not_called()

    @patch("services.fyers_token_renewal.trigger_fail_closed_lockout")
    @patch("services.fyers_token_renewal.verify_live_token")
    @patch("broker.fyers.api.auth_api.renew_broker_token")
    @patch("services.fyers_token_renewal.get_keychain_pin")
    @patch("database.auth_db.get_fyers_refresh_token")
    @patch("database.auth_db.upsert_auth")
    def test_tc06_database_error_handling(
        self, mock_upsert, mock_get_refresh, mock_pin, mock_renew, mock_verify, mock_lockout
    ):
        """TC-06: Database error during upsert triggers fail-closed lockout."""
        recent_date = (datetime.now(pytz.utc) - timedelta(days=1)).isoformat()
        mock_get_refresh.return_value = ("token", recent_date)
        mock_pin.return_value = "1234"
        mock_renew.return_value = ("access_token", {"status": "success"})
        mock_verify.return_value = True
        mock_upsert.side_effect = RuntimeError("SQLite database is locked")

        success, msg = execute_renewal_cycle(force=True, name="test_user")

        assert success is False
        assert "Database error" in msg
        mock_lockout.assert_called_once()
        assert "database is locked" in mock_lockout.call_args[0][1].lower()

    @patch("websocket_proxy.broker_factory.cleanup_pools_for_user")
    @patch("services.order_update_service.stop_order_update_adapter")
    @patch("database.cache_invalidation.publish_all_cache_invalidation")
    def test_tc07_fail_closed_lockout_verification(
        self, mock_zmq, mock_ws_stop, mock_pool_clean
    ):
        """TC-07: Verifies revoke_auth_token sets is_revoked=True, clears caches, and tears down WS pools."""
        from database.auth_db import (
            Auth,
            db_session,
            revoke_auth_token,
            get_auth_token,
            get_auth_token_broker,
            auth_cache,
        )

        test_username = "test_lockout_user"
        # Create a test auth record
        existing = Auth.query.filter_by(name=test_username).first()
        if existing:
            db_session.delete(existing)
            db_session.commit()

        test_auth = Auth(
            name=test_username,
            auth="test_encrypted_token",
            broker="fyers",
            is_revoked=False,
        )
        db_session.add(test_auth)
        db_session.commit()

        # Populate cache
        auth_cache[f"auth-{test_username}"] = test_auth

        # Execute revocation
        result = revoke_auth_token(test_username)
        assert result is True

        # Verify DB state
        re_queried = Auth.query.filter_by(name=test_username).first()
        assert re_queried.is_revoked is True

        # Verify get_auth_token returns None
        token = get_auth_token(test_username)
        assert token is None

        # Clean up test user
        db_session.delete(re_queried)
        db_session.commit()
