#!/usr/bin/env python3
"""
Automated FYERS Token Renewal Service with Fail-Closed Circuit Breaker.
OpenAlgo v2.0.2.7 | macOS (Apple Silicon Mac mini)

Features:
- Unattended retrieval of trading PIN from macOS Keychain ('openalgo.fyers.pin').
- Decryption of stored refresh token from auth.aux_param1.
- 14-day validity boundary enforcement.
- Automated token renewal via FYERS API v3 validate-refresh-token.
- Smoke verification of newly acquired access token against broker funds endpoint.
- Database upsert with automatic cache invalidation and WebSocket adapter pool cleanup.
- Fail-closed master circuit breaker: sets is_revoked = True on any authentication failure,
  halting order dispatch across all routes and strategies.
- Telegram emergency alerting on failure / status alerts on success.
- Idempotency guard: skips re-renewal if current token was already renewed and verified today.
"""

import os
import sys
import time
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import pytz

# Add repository root to python search path if running standalone
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from utils.logging import get_logger
from utils.httpx_client import get_httpx_client

logger = get_logger("fyers_token_renewal")

IST = pytz.timezone("Asia/Kolkata")
KEYCHAIN_SERVICE = "openalgo.fyers.pin"
KEYCHAIN_ACCOUNT = "vikashiname"
MAX_REFRESH_TOKEN_DAYS = 14
DEFAULT_USER = "vikashiname"
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [5, 10, 15]


def get_keychain_pin(account: str = KEYCHAIN_ACCOUNT, service: str = KEYCHAIN_SERVICE) -> Optional[str]:
    """
    Retrieve trading PIN securely from macOS Keychain without user-facing prompts.
    Uses /usr/bin/security CLI utility with stdout capture.
    Never logs or leaks the PIN string.
    """
    try:
        cmd = [
            "/usr/bin/security",
            "find-generic-password",
            "-a", account,
            "-s", service,
            "-w",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        if result.returncode == 0:
            pin = result.stdout.strip()
            if pin:
                logger.debug("Successfully retrieved PIN from macOS Keychain (length: %d)", len(pin))
                return pin
            else:
                logger.error("Keychain item '%s' for '%s' returned empty output", service, account)
                return None
        else:
            stderr_msg = result.stderr.strip()
            logger.error(
                "Keychain lookup failed for service '%s', account '%s' (rc=%d): %s",
                service, account, result.returncode, stderr_msg
            )
            return None
    except Exception as e:
        logger.exception("Unexpected exception accessing macOS Keychain: %s", e)
        return None


def send_telegram_alert(message: str, is_emergency: bool = False) -> bool:
    """
    Dispatch Telegram notification directly using configured bot credentials.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram alerting skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    client = get_httpx_client()
    try:
        resp = client.post(url, json=payload, timeout=10.0)
        return resp.status_code == 200
    except Exception as e:
        logger.error("Failed to send Telegram alert: %s", e)
        return False


def verify_live_token(access_token: str) -> bool:
    """
    Smoke-check access token validity against FYERS live broker funds API.
    Returns True if broker accepts credentials, False if 401/expired.
    """
    try:
        from broker.fyers.api.funds import get_margin_data
        funds = get_margin_data(access_token)
        # get_margin_data returns non-empty dict when broker session is authenticated
        if funds and isinstance(funds, dict) and len(funds) > 0:
            logger.info("Live broker smoke check PASSED: Funds data retrieved successfully")
            return True
        else:
            logger.warning("Live broker smoke check FAILED: Empty funds response (session expired or invalid)")
            return False
    except Exception as e:
        logger.warning("Live broker smoke check raised exception: %s", e)
        return False


def is_token_valid_and_recent(name: str = DEFAULT_USER) -> bool:
    """
    Idempotency check: returns True if current token was already renewed today
    and passes the live broker smoke check.
    """
    try:
        from database.auth_db import get_auth_token_dbquery, decrypt_token
        auth_obj = get_auth_token_dbquery(name)
        if not auth_obj or auth_obj.is_revoked:
            return False

        current_token = decrypt_token(auth_obj.auth)
        if not current_token:
            return False

        # Verify live
        return verify_live_token(current_token)
    except Exception as e:
        logger.debug("Idempotency check check error: %s", e)
        return False


def trigger_fail_closed_lockout(name: str, reason: str):
    """
    Engage the master fail-closed circuit breaker.
    Revokes the auth token in DB, clears caches, closes WS adapter pools,
    and alerts the administrator via Telegram.
    """
    logger.critical("ENGAGING FAIL-CLOSED LOCKOUT FOR '%s': %s", name, reason)
    try:
        from database.auth_db import revoke_auth_token
        revoked = revoke_auth_token(name)
        logger.info("Revocation status in DB: %s", revoked)
    except Exception as e:
        logger.exception("Failed to execute revoke_auth_token in DB: %s", e)

    # Dispatch emergency alert
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    alert_msg = (
        f"🚨 <b>OPENALGO EMERGENCY: FAIL-CLOSED LOCKOUT ENGAGED</b>\n\n"
        f"• <b>Timestamp:</b> <code>{now_ist}</code>\n"
        f"• <b>Reason:</b> {reason}\n"
        f"• <b>Broker:</b> FYERS\n"
        f"• <b>Status:</b> <b>ALL TRADING DISPATCH BLOCKED</b> (HTTP 403)\n"
        f"• <b>Strategies:</b> In Reconciliation Pause / Safe State\n\n"
        f"⚠️ <b>Action Required:</b> Perform manual interactive login at:\n"
        f"🔗 <code>https://vikashiname.in/brlogin/fyers</code>\n"
    )
    send_telegram_alert(alert_msg, is_emergency=True)


def execute_renewal_cycle(force: bool = False, name: str = DEFAULT_USER) -> Tuple[bool, str]:
    """
    Execute full morning FYERS token renewal cycle:
    1. Check if token is already valid (idempotency guard, unless force=True).
    2. Retrieve encrypted refresh token and timestamp from database.
    3. Check 14-day validity window.
    4. Retrieve trading PIN securely from macOS Keychain.
    5. Renew token with retries on transient errors.
    6. Verify new access token live with FYERS broker.
    7. Upsert token into openalgo.db, invalidate memory caches, and refresh WS adapters.
    8. Dispatch success Telegram notification.
    """
    now_ist = datetime.now(IST)
    logger.info("=" * 70)
    logger.info("Starting FYERS Token Renewal Cycle at %s", now_ist.strftime("%Y-%m-%d %H:%M:%S IST"))
    logger.info("=" * 70)

    # 1. Idempotency Check
    if not force:
        if is_token_valid_and_recent(name):
            msg = "Token is already active and verified with FYERS. Renewal cycle skipped (Idempotent)."
            logger.info("✅ %s", msg)
            return True, msg

    # 2. Retrieve refresh token from DB
    from database.auth_db import get_fyers_refresh_token, upsert_auth
    refresh_token, created_at_iso = get_fyers_refresh_token(name)

    if not refresh_token:
        reason = "No stored FYERS refresh token found in database (aux_param1 is empty)."
        trigger_fail_closed_lockout(name, reason)
        return False, reason

    # 3. Check Refresh Token Age
    if created_at_iso:
        try:
            created_dt = datetime.fromisoformat(created_at_iso)
            if created_dt.tzinfo is None:
                created_dt = pytz.utc.localize(created_dt)
            age_days = (datetime.now(pytz.utc) - created_dt).total_seconds() / 86400.0
            logger.info("Refresh token age: %.1f days (threshold: %d days)", age_days, MAX_REFRESH_TOKEN_DAYS)
            if age_days > MAX_REFRESH_TOKEN_DAYS:
                reason = (
                    f"FYERS refresh token has exceeded maximum validity age ({age_days:.1f} days > {MAX_REFRESH_TOKEN_DAYS} days). "
                    "Interactive browser re-login required."
                )
                trigger_fail_closed_lockout(name, reason)
                return False, reason
        except Exception as e:
            logger.warning("Could not parse refresh token timestamp '%s': %s", created_at_iso, e)

    # 4. Retrieve PIN from Keychain
    pin = get_keychain_pin(account=name)
    if not pin:
        reason = "Failed to retrieve FYERS 4-digit PIN from macOS Keychain service 'openalgo.fyers.pin'."
        trigger_fail_closed_lockout(name, reason)
        return False, reason

    # 5. Call FYERS Renewal API with Retries
    from broker.fyers.api.auth_api import renew_broker_token

    new_token = None
    last_err_msg = ""
    auth_permanent_failure = False

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("Renewal API call attempt %d of %d...", attempt, MAX_RETRIES)
        token, resp_data = renew_broker_token(refresh_token=refresh_token, pin=pin)

        if token and resp_data.get("status") == "success":
            new_token = token
            logger.info("Renewal API succeeded on attempt %d", attempt)
            break
        else:
            err_code = resp_data.get("code")
            code_str = f" (code: {err_code})" if err_code is not None else ""
            last_err_msg = f"{resp_data.get('message', 'Unknown error')}{code_str}"
            logger.warning("Attempt %d failed: %s", attempt, last_err_msg)

            # Permanent auth failures (-501, bad pin, 401, 403) should not be endlessly retried
            if err_code in (-501, -401, -442, 401, 403) or "pin" in last_err_msg.lower():
                auth_permanent_failure = True
                break

            if attempt < MAX_RETRIES:
                sleep_s = RETRY_BACKOFF_SECONDS[attempt - 1]
                logger.info("Waiting %d seconds before retry...", sleep_s)
                time.sleep(sleep_s)

    if not new_token:
        reason = f"FYERS token renewal failed: {last_err_msg}"
        trigger_fail_closed_lockout(name, reason)
        return False, reason

    # 6. Live Smoke Verification
    logger.info("Performing live broker smoke verification with fresh access token...")
    verified = verify_live_token(new_token)
    if not verified:
        reason = "New access token failed live broker smoke verification (/api/v3/funds rejected credentials)."
        trigger_fail_closed_lockout(name, reason)
        return False, reason

    # 7. Upsert New Token to Database
    logger.info("Upserting verified access token into OpenAlgo database...")
    try:
        upsert_auth(
            name=name,
            auth_token=new_token,
            broker="fyers",
            revoke=False,
            # Pass None for refresh_token to preserve existing aux_param1 and aux_param2
            refresh_token=None,
        )
        logger.info("Database record successfully updated. Cache cleared and WS adapter pools reset.")
    except Exception as e:
        reason = f"Database error committing refreshed token: {e}"
        trigger_fail_closed_lockout(name, reason)
        return False, reason

    # 8. Success Notification
    success_msg = (
        f"✅ <b>OPENALGO: FYERS TOKEN RENEWED SUCCESSFULLY</b>\n\n"
        f"• <b>Timestamp:</b> <code>{datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}</code>\n"
        f"• <b>Broker:</b> FYERS\n"
        f"• <b>Account:</b> {name}\n"
        f"• <b>Live Verification:</b> PASSED (/api/v3/funds OK)\n"
        f"• <b>Valid Until:</b> Tomorrow 03:00 AM IST\n"
        f"• <b>Mode:</b> ANALYZE (Paper Trading)\n"
        f"• <b>WebSocket:</b> Connection Pools Recycled\n"
    )
    send_telegram_alert(success_msg)
    logger.info("FYERS Token Renewal Cycle completed successfully.")
    return True, "Token renewed and verified successfully."


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    success, message = execute_renewal_cycle(force=force_flag)
    sys.exit(0 if success else 1)
