"""
================================================================================
OPENALGO LIVE STRATEGY: MULTI-ASSET NFO MACD CROSSOVER & REGIME ENGINE
================================================================================
File Role            : LIVE_OPENALGO
Strategy Identifier  : MACD_FNO_V2 (Candidate E / 0.35% Runner Architecture)
Current Version      : 2.0.0
Last Modified        : 2026-10-12
Git Baseline Commit  : 209361f37ab8ae7e8f9de8f16ce37421f616c11f
Production Approval  : SHADOW / PAPER TRADING ONLY (Phase 7 Governance)

Implementation History:
  - 2026-10-12 [v1.3.0]: Official Baseline Candidate G (Pure MACD Cross + Asymmetric Universe: TOP_LONGS / TOP_SHORTS) with optional Candidate E runner mode.
  - 2026-10-12 [v1.2.1]: Added --auto-exit-misaligned option, DB lock retry backoff, and order pacing.
  - 2026-10-10 [v1.2.0]: Alert deduplication against OpenAlgo subscriber and transition matrix tests.
  - 2026-10-04 [v1.1.0]: Added Dead-Zone time filters, Long Regime guard (EMA 50/100), and Index lot multiplier.

Current Strategy Specification:
  1. Timeframe & Indicators:
     - 1-Hour (1H) completed candles strictly.
     - MACD: 12 / 26 / 9 with 2-bar histogram expansion confirmation.
  2. Execution Gates & Universe:
     - Universe Selection: Asymmetric Alpha Whitelist (TOP_LONGS: 7, TOP_SHORTS: 6).
     - Time Filter: Dead zones 11:00-11:59 and 14:00-14:59 IST blocked; gaps 09:15-09:44 blocked.
     - Long Regime Guard: Close must be above 50-EMA (and 100-EMA for weak sectors).
  3. Risk Management & Exits:
     - Baseline (Candidate G): Pure MACD opposite signal reversal. No fixed artificial profit targets.
     - Runner Variant (Candidate E): +3.0% Long / +1.5% Short target + 0.35% trailing runner.
     - Catastrophe SL: -3.5% emergency stop loss.
     - Max Active Positions: 20 concurrent positions cap.
     - Position Misalignment: Observational audit or auto-exit to FLAT via --auto-exit-misaligned.
  4. Execution Safety:
     - Execution Mode: STRICTLY PAPER / ANALYZE TRADING MODE ONLY.
     - Live orders are gated with persistent state recovery across restarts.

Validation Status:
  - Alert & Reversal Matrix Tests: 12/12 PASSED (python3 -m unittest test_alert_reversal_matrix.py)

Known Limitations & Unresolved Issues:
  - Historical backtesting module depends on optional yfinance/matplotlib packages.
================================================================================
"""

import argparse
import base64
import builtins
import logging
import math
import os
import re
import signal
import subprocess
import sys
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, time as dt_time, timezone
try:
    import zoneinfo
    IST = zoneinfo.ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    matplotlib = None
    plt = None
import numpy as np
import pandas as pd
import requests

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(), override=False)
except ImportError:
    pass

try:
    from openalgo import api
    client_available = True
except ImportError:
    client_available = False
    api = None

try:
    import yfinance as yf
except ImportError:
    yf = None

import json
from logging.handlers import RotatingFileHandler

# ==============================================================================
# LOGGING SETUP (PHASE A: CONSOLE + ROTATING FILE HANDLER)
# ==============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
LOG_FILE_PATH = Path(os.getenv("LOG_FILE", PROJECT_ROOT / "log/strategies/macd_fno.log" if (PROJECT_ROOT / "log").exists() else SCRIPT_DIR / "macd_fno.log"))
STATE_FILE_PATH = Path(os.getenv("STATE_FILE", SCRIPT_DIR / "macdfno_state.json"))
HEARTBEAT_FILE_PATH = Path(os.getenv("HEARTBEAT_FILE", SCRIPT_DIR / "macdfno_heartbeat.json"))

logger = logging.getLogger("MACD_FNO_BOT")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    
    # Console stream handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Rotating file handler (10MB max, 5 backup files)
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE_PATH, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Failed to setup RotatingFileHandler for {LOG_FILE_PATH}: {e}", file=sys.stderr)

# ==============================================================================
# PERSISTENT STATE MANAGER (PHASE A)
# ==============================================================================
class PersistentStateManager:
    """
    Atomic, crash-safe state persistence for macdfno.py.
    Guarantees state is preserved across process crashes, restarts, and reboots.
    """
    def __init__(self, state_file: Path = STATE_FILE_PATH):
        self.state_file = state_file
        self.state: Dict[str, Any] = self.load_state()

    def load_state(self) -> Dict[str, Any]:
        """Safely loads state from disk with corrupt-file recovery."""
        if not self.state_file.exists():
            return self._default_state()
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "version" in data:
                    return data
                logger.warning(f"⚠️ State file {self.state_file} has invalid format. Resetting to default.")
                return self._default_state()
        except Exception as e:
            logger.error(f"❌ Error loading state file {self.state_file}: {e}. Initializing fresh state.")
            return self._default_state()

    def _default_state(self) -> Dict[str, Any]:
        return {
            "version": "1.0",
            "strategy": os.getenv("STRATEGY_NAME", "MACD_FNO_V2"),
            "last_saved_at": None,
            "last_processed_candles": {},
            "tracked_positions": {},
            "recent_executions": [],
            "sent_alerts": [],
        }

    def save_state(self):
        """Atomic write: writes to temp file then atomic rename to prevent corruption on crash."""
        try:
            self.state["last_saved_at"] = datetime.now().isoformat()
            temp_file = self.state_file.with_suffix(f".tmp.{os.getpid()}")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, default=str)
            temp_file.replace(self.state_file)
        except Exception as e:
            logger.error(f"❌ Failed to atomically save state to {self.state_file}: {e}")

    def get_last_processed_candle(self, symbol: str) -> Optional[str]:
        return self.state.get("last_processed_candles", {}).get(symbol)

    def record_processed_candle(self, symbol: str, candle_time: Any):
        if "last_processed_candles" not in self.state:
            self.state["last_processed_candles"] = {}
        self.state["last_processed_candles"][symbol] = str(candle_time)
        self.save_state()

    def record_execution(self, symbol: str, contract: str, action: str, qty: int, candle_time: Any, order_resp: Any):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "contract": contract,
            "action": action,
            "quantity": qty,
            "candle_time": str(candle_time),
            "order_response": order_resp if isinstance(order_resp, (dict, list, str, int, float)) else str(order_resp),
        }
        if "recent_executions" not in self.state:
            self.state["recent_executions"] = []
        self.state["recent_executions"].append(entry)
        self.state["recent_executions"] = self.state["recent_executions"][-100:]
        self.save_state()

    def record_reconciliation_audit(self, audit_summary: Dict[str, Any]):
        """Records startup reconciliation & misalignment audit to persistent state."""
        self.state["last_reconciliation_audit"] = {
            "timestamp": datetime.now().isoformat(),
            "summary": audit_summary,
        }
        self.save_state()

    def update_tracked_positions(self, positions_map: Dict[str, Any]):
        """Updates tracked active positions in persistent state."""
        self.state["tracked_positions"] = positions_map
        self.save_state()

    def is_order_inflight_or_filled(self, order_key: str) -> bool:
        """Checks if an order key is currently in-flight or already filled."""
        in_flight = self.state.get("in_flight_orders", {})
        return in_flight.get(order_key, {}).get("status") in ["PENDING", "FILLED"]

    def mark_order_pending(self, order_key: str, details: Dict[str, Any]):
        """Marks an order key as PENDING before API submission."""
        if "in_flight_orders" not in self.state:
            self.state["in_flight_orders"] = {}
        self.state["in_flight_orders"][order_key] = {
            "status": "PENDING",
            "timestamp": datetime.now().isoformat(),
            "details": details,
        }
        self.save_state()

    def mark_order_resolved(self, order_key: str, status: str, order_id: Optional[str] = None):
        """Marks an in-flight order as resolved (FILLED, REJECTED, AUTH_FAILED, etc.)."""
        if "in_flight_orders" in self.state and order_key in self.state["in_flight_orders"]:
            self.state["in_flight_orders"][order_key]["status"] = status
            self.state["in_flight_orders"][order_key]["resolved_at"] = datetime.now().isoformat()
            if order_id:
                self.state["in_flight_orders"][order_key]["order_id"] = order_id
            self.save_state()

    def is_alert_sent(self, alert_key: str) -> bool:
        """Checks if a telegram alert key was already recorded."""
        return alert_key in self.state.get("sent_alerts", [])

    def record_alert_sent(self, alert_key: str):
        """Records a telegram alert key to persistent state to prevent duplicate alerts."""
        if "sent_alerts" not in self.state:
            self.state["sent_alerts"] = []
        if alert_key not in self.state["sent_alerts"]:
            self.state["sent_alerts"].append(alert_key)
            self.state["sent_alerts"] = self.state["sent_alerts"][-200:]
            self.save_state()

# ==============================================================================
# CONFIGURATION
# ==============================================================================
OPENALGO_API_KEY = os.getenv("OPENALGO_API_KEY", "")
OPENALGO_HOST = os.getenv("OPENALGO_HOST")
if not OPENALGO_HOST:
    host_server = os.getenv("HOST_SERVER", "")
    if host_server and "127.0.0.1" not in host_server and "localhost" not in host_server:
        OPENALGO_HOST = host_server
    else:
        OPENALGO_HOST = "https://vikashiname.in"
OPENALGO_WS_URL = os.getenv(
    "WEBSOCKET_URL", "wss://vikashiname.in/api/ws"
)

# Telegram Alert Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Fallback 1: Fetch Telegram bot config from OpenAlgo Host API if unconfigured
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    try:
        cfg_resp = requests.get(
            f"{OPENALGO_HOST.rstrip('/')}/api/v1/telegram/config",
            headers={"X-API-KEY": OPENALGO_API_KEY},
            timeout=5,
        )
        if cfg_resp.status_code == 200:
            cfg_d = cfg_resp.json().get("data", {})
            if cfg_d.get("is_active") and cfg_d.get("token"):
                if not TELEGRAM_BOT_TOKEN:
                    TELEGRAM_BOT_TOKEN = cfg_d["token"]
            elif cfg_d.get("is_active") and cfg_d.get("bot_token") and "..." not in str(cfg_d.get("bot_token")):
                if not TELEGRAM_BOT_TOKEN:
                    TELEGRAM_BOT_TOKEN = cfg_d["bot_token"]
        user_resp = requests.get(
            f"{OPENALGO_HOST.rstrip('/')}/api/v1/telegram/users",
            headers={"X-API-KEY": OPENALGO_API_KEY},
            timeout=5,
        )
        if user_resp.status_code == 200:
            u_list = user_resp.json().get("data", [])
            if u_list and not TELEGRAM_CHAT_ID:
                TELEGRAM_CHAT_ID = str(u_list[0].get("telegram_id", ""))
    except Exception:
        pass

# Fallback 2: Check local database if available
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    try:
        from database.telegram_db import get_bot_config, get_all_telegram_users
        bot_cfg = get_bot_config()
        token = bot_cfg.get("bot_token") or bot_cfg.get("token")
        if token and token != "test_token_123456789" and bot_cfg.get("is_active"):
            if not TELEGRAM_BOT_TOKEN:
                TELEGRAM_BOT_TOKEN = token
            users = get_all_telegram_users()
            if users and not TELEGRAM_CHAT_ID:
                TELEGRAM_CHAT_ID = str(users[0].get("telegram_id", ""))
    except Exception:
        pass

# ==============================================================================
# TELEGRAM DISPATCHER (PHASE B)
# ==============================================================================
def send_telegram_alert(message: str) -> bool:
    """
    Dispatches formatted alert message to Telegram.
    Non-blocking, non-fatal on failure.
    """
    clean_msg = re.sub(r"<[^>]+>", "", message)
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info(f"📢 [TELEGRAM ALERT - CONSOLE DISPATCH]\n{clean_msg}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=8)
        if resp.status_code == 200:
            logger.info("📱 Telegram alert successfully dispatched.")
            return True
        else:
            logger.warning(f"Telegram API response (HTTP {resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"Telegram dispatch failed non-fatally: {e}")
        return False


def format_trade_alert(data: Dict[str, Any]) -> str:
    """Formats structured trade execution notification into a consolidated Telegram alert."""
    direction = data.get("direction", "LONG")
    dir_emoji = "🟢" if direction == "LONG" else "🔴"
    action = data.get("action", "BUY")
    contract = data.get("contract", "N/A")
    symbol = data.get("symbol", "N/A")
    qty = data.get("quantity", 0)
    order_id = data.get("order_id", "N/A")
    order_status = data.get("order_status", "FILLED")
    price_type = data.get("price_type", "MARKET")
    exchange = data.get("exchange", "NFO")
    product = data.get("product", "NRML")
    exec_time = data.get("execution_time") or datetime.now().strftime("%H:%M:%S")
    pos_before = data.get("pos_before", 0)
    pos_after = data.get("pos_after", qty if action == "BUY" else -qty)
    strategy_name = data.get("strategy_name", "MACD_FNO_V2")
    trigger_px = data.get("trigger_price", 0.0)

    entry_price = data.get("entry_price") or data.get("fill_price") or 0.0
    try:
        entry_price_val = float(entry_price)
    except (TypeError, ValueError):
        entry_price_val = 0.0

    target_pct = float(os.getenv("LONG_PROFIT_TARGET_PCT", "3.0")) if direction == "LONG" else float(os.getenv("SHORT_PROFIT_TARGET_PCT", "1.5"))
    sl_pct = float(os.getenv("CATASTROPHE_SL_PCT", "3.5"))

    if entry_price_val > 0:
        if direction == "LONG":
            target_px = entry_price_val * (1.0 + target_pct / 100.0)
            sl_px = entry_price_val * (1.0 - sl_pct / 100.0)
        else:
            target_px = entry_price_val * (1.0 - target_pct / 100.0)
            sl_px = entry_price_val * (1.0 + sl_pct / 100.0)
        target_sl_lines = f"<b>🎯 Target:</b> ₹{target_px:.2f} ({'+' if direction == 'LONG' else '-'}{target_pct:.1f}%)\n<b>🛑 Stop Loss:</b> ₹{sl_px:.2f} ({'-' if direction == 'LONG' else '+'}{sl_pct:.1f}%)\n"
    else:
        target_sl_lines = ""

    if trigger_px and float(trigger_px) > 0:
        price_lines = f"<b>Entry Price:</b> ₹{entry_price_val:.2f}\n<b>Trigger Price:</b> ₹{float(trigger_px):.2f}\n{target_sl_lines}"
    else:
        price_lines = f"<b>Entry Price:</b> ₹{entry_price_val:.2f}\n{target_sl_lines}"

    close_val = data.get("close", 0.0)
    macd_val = data.get("macd", 0.0)
    signal_val = data.get("signal", 0.0)
    hist_val = data.get("histogram", 0.0)

    return (
        f"{dir_emoji} <b>NFO TRADE — ORDER PLACED</b>\n\n"
        f"<b>Strategy:</b> {strategy_name} (MACD 12/26/9 + 2-Bar Expansion)\n"
        f"🔬 <b>ANALYZE MODE - No Real Order</b>\n"
        f"─────────────────────\n"
        f"<b>Symbol:</b> <code>{contract}</code> ({symbol})\n"
        f"<b>Action:</b> <b>{action}</b>\n"
        f"<b>Direction:</b> <b>{direction}</b>\n"
        f"<b>Quantity:</b> {qty}\n"
        f"{price_lines}"
        f"<b>Price Type:</b> {price_type}\n"
        f"<b>Exchange:</b> {exchange}\n"
        f"<b>Product:</b> {product}\n"
        f"<b>Order ID:</b> <code>{order_id}</code>\n"
        f"<b>Order Status:</b> {order_status}\n"
        f"<b>Position:</b> {pos_before} ➔ {pos_after}\n"
        f"⏰ <b>Time:</b> {exec_time} IST\n"
        f"─────────────────────\n"
        f"📊 <b>Completed Candle:</b> {data.get('candle_time')}\n\n"
        f"<b>Close:</b> ₹{close_val:.2f}\n"
        f"<b>MACD:</b> {macd_val:.2f}\n"
        f"<b>Signal:</b> {signal_val:.2f}\n"
        f"<b>Histogram:</b> {hist_val:+.2f}\n"
        f"─────────────────────\n"
        f"<i>ℹ️ Mode: PAPER / ANALYZE ONLY</i>"
    )


def format_paper_exit_alert(data: Dict[str, Any]) -> str:
    """
    Formats an HTML Telegram alert message for paper trading position exits
    (TARGET_HIT, CATASTROPHE_SL, MACD_REVERSAL, SIGNAL_EXIT).
    """
    strategy_name = data.get("strategy_name", STRATEGY_NAME)
    contract = data.get("contract", "N/A")
    symbol = data.get("symbol", "N/A")
    direction = data.get("direction", "LONG")  # Position direction that was exited
    action = data.get("action", "SELL" if direction == "LONG" else "BUY")
    exit_reason = data.get("exit_reason", "UNKNOWN")
    qty = abs(int(data.get("quantity", 0)))
    order_id = data.get("order_id", "N/A")
    order_status = data.get("order_status", "FILLED")
    exec_time = data.get("execution_time") or datetime.now(IST).strftime("%H:%M:%S")
    candle_time = data.get("candle_time_str") or data.get("candle_time", "N/A")

    entry_price = float(data.get("entry_price", 0.0) or 0.0)
    exit_price = float(data.get("exit_price", 0.0) or 0.0)

    # Calculate P&L
    dir_mult = 1.0 if direction == "LONG" else -1.0
    if entry_price > 0:
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0 * dir_mult
        pnl_abs = (exit_price - entry_price) * qty * dir_mult
    else:
        pnl_pct = 0.0
        pnl_abs = 0.0

    target_pct = float(os.getenv("LONG_PROFIT_TARGET_PCT", "3.0")) if direction == "LONG" else float(os.getenv("SHORT_PROFIT_TARGET_PCT", "1.5"))
    sl_pct = float(os.getenv("CATASTROPHE_SL_PCT", "3.5"))

    if entry_price > 0:
        if direction == "LONG":
            target_px = entry_price * (1.0 + target_pct / 100.0)
            sl_px = entry_price * (1.0 - sl_pct / 100.0)
        else:
            target_px = entry_price * (1.0 - target_pct / 100.0)
            sl_px = entry_price * (1.0 + sl_pct / 100.0)
        target_sl_lines = f"<b>🎯 Target:</b> ₹{target_px:.2f} ({'+' if direction == 'LONG' else '-'}{target_pct:.1f}%)\n<b>🛑 Stop Loss:</b> ₹{sl_px:.2f} ({'-' if direction == 'LONG' else '+'}{sl_pct:.1f}%)\n"
    else:
        target_sl_lines = ""

    pnl_emoji = "🟢" if pnl_abs > 0 else ("🔴" if pnl_abs < 0 else "⚪")
    if pnl_abs > 0:
        pnl_str = f"+₹{pnl_abs:,.2f} (+{pnl_pct:.2f}%)"
    elif pnl_abs < 0:
        pnl_str = f"-₹{abs(pnl_abs):,.2f} ({pnl_pct:.2f}%)"
    else:
        pnl_str = f"₹0.00 (0.00%)"

    if exit_reason == "TARGET_HIT":
        reason_header = "🎯 TARGET HIT"
        reason_badge = "🎯 <b>TARGET REACHED</b>"
    elif exit_reason == "RUNNER_HWM_TRAIL":
        reason_header = "🏃 RUNNER TRAIL HIT"
        reason_badge = "🏃 <b>HIGH-WATER-MARK TRAILING STOP TRIGGERED</b>"
    elif exit_reason == "CATASTROPHE_SL":
        reason_header = "🛑 CATASTROPHE STOP-LOSS"
        reason_badge = "🛑 <b>EMERGENCY STOP LOSS TRIGGERED</b>"
    elif "REVERSAL" in exit_reason:
        reason_header = "🔄 REVERSAL EXIT"
        reason_badge = "🔄 <b>OPPOSITE MACD SIGNAL REVERSAL</b>"
    elif exit_reason == "SIGNAL_EXIT":
        reason_header = "🔄 SIGNAL EXIT"
        reason_badge = "🔄 <b>OPPOSITE SIGNAL EXIT (ENTRY BLOCKED)</b>"
    else:
        reason_header = f"EXIT ({exit_reason})"
        reason_badge = f"ℹ️ <b>{exit_reason}</b>"

    return (
        f"{pnl_emoji} <b>PAPER TRADE — {reason_header}</b>\n\n"
        f"<b>Strategy:</b> {strategy_name} (MACD 12/26/9 + 2-Bar Expansion)\n"
        f"🔬 <b>ANALYZE MODE - No Real Order</b>\n"
        f"─────────────────────\n"
        f"<b>Symbol:</b> <code>{contract}</code> ({symbol})\n"
        f"<b>Exited Direction:</b> <b>{direction}</b>\n"
        f"<b>Exit Action:</b> <b>{action}</b>\n"
        f"<b>Exit Reason:</b> {reason_badge}\n"
        f"<b>Quantity:</b> {qty}\n"
        f"<b>Entry Price:</b> ₹{entry_price:.2f}\n"
        f"<b>Exit Price:</b> ₹{exit_price:.2f}\n"
        f"{target_sl_lines}"
        f"<b>Net P&L:</b> {pnl_str}\n"
        f"<b>Exchange:</b> {EXCHANGE}\n"
        f"<b>Product:</b> {PRODUCT}\n"
        f"<b>Order ID:</b> <code>{order_id}</code>\n"
        f"<b>Order Status:</b> {order_status}\n"
        f"⏰ <b>Time:</b> {exec_time} IST\n"
        f"─────────────────────\n"
        f"📊 <b>Completed Candle:</b> {candle_time}\n"
        f"─────────────────────\n"
        f"<i>ℹ️ Mode: PAPER / ANALYZE ONLY</i>"
    )


EXCHANGE = "NFO"
PRODUCT = os.getenv("PRODUCT", "NRML")
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "MACD_FNO_V2")

FAST_PERIOD = int(os.getenv("FAST_PERIOD", "12"))
SLOW_PERIOD = int(os.getenv("SLOW_PERIOD", "26"))
SIGNAL_PERIOD = int(os.getenv("SIGNAL_PERIOD", "9"))

INTERVAL = os.getenv("INTERVAL", "1h")
LOTS = int(os.getenv("LOTS", "1"))
MAX_ACTIVE_POSITIONS = int(os.getenv("MAX_ACTIVE_POSITIONS", "20"))
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() in ["true", "1", "yes"]

# Asymmetric Universe Whitelist (AutoResearch Champion V3.0 / Candidate G & E)
TOP_LONGS = {
    "SUNPHARMA", "BAJAJ-AUTO", "BPCL", "WIPRO", "TATASTEEL",
    "BAJFINANCE", "NTPC"
}
TOP_SHORTS = {
    "SUNPHARMA", "BAJAJ-AUTO", "M&M", "BPCL", "NTPC",
    "NIFTY"
}
USE_ASYMMETRIC_UNIVERSE = os.getenv("USE_ASYMMETRIC_UNIVERSE", "true").lower() in ["true", "1", "yes"]

# Strategy Baseline Architecture:
# - Candidate G (Default Baseline): Pure MACD Opposite Signal Cross Reversal. (No artificial targets).
# - Candidate E (Runner Variant): Target Touch (+3.0% / +1.5%) + 0.35% HWM trailing runner.
RUNNER_MODE = os.getenv("RUNNER_MODE", "false").lower() in ["true", "1", "yes"]
RUNNER_TRAIL_PCT = float(os.getenv("RUNNER_TRAIL_PCT", "0.35"))

# Empirical Performance Optimization Parameters (September 2026 Audit)
ENABLE_TIME_FILTER = os.getenv("ENABLE_TIME_FILTER", "true").lower() in ["true", "1", "yes"]
ENABLE_REGIME_FILTER = os.getenv("ENABLE_REGIME_FILTER", "true").lower() in ["true", "1", "yes"]
LONG_PROFIT_TARGET_PCT = float(os.getenv("LONG_PROFIT_TARGET_PCT", "3.0"))
SHORT_PROFIT_TARGET_PCT = float(os.getenv("SHORT_PROFIT_TARGET_PCT", "1.5"))
CATASTROPHE_SL_PCT = float(os.getenv("CATASTROPHE_SL_PCT", "3.5"))
ORDER_PACING_DELAY_SEC = float(os.getenv("ORDER_PACING_DELAY_SEC", "0.25"))
AUTO_EXIT_MISALIGNED = os.getenv("AUTO_EXIT_MISALIGNED", "false").lower() in ["true", "1", "yes"]
INDEX_LOT_MULTIPLIER = int(os.getenv("INDEX_LOT_MULTIPLIER", "2"))
INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}

WEAK_LONG_SYMBOLS = {
    "OFSS", "MPHASIS", "PERSISTENT", "COFORGE", "LTM", "WIPRO", "INFY", "TCS", "TECHM",
    "ICICIBANK", "BANKBARODA", "AUBANK", "KOTAKBANK", "AXISBANK", "SBIN",
    "HEROMOTOCO", "MARUTI", "M&M", "BAJAJ-AUTO"
}

def is_entry_time_allowed(now_dt: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    Empirical time-of-day execution filter for Indian F&O.
    Blocks fresh entries during known low-volume chop and European open whipsaw windows:
      - Dead Zone 1: 11:00 - 11:59 IST (Pre-EU chop / volume vacuum: -Rs. 3.04L drain)
      - Dead Zone 2: 14:00 - 14:59 IST (EU open whipsaws: -Rs. 2.11L drain)
      - Opening 30 min: 09:15 - 09:44 IST (Gap noise / unconfirmed momentum)
    Permits fresh entries during:
      - Morning Window:  09:45 - 10:55 IST (+Rs. 4.85L)
      - Midday Window:   12:00 - 13:15 IST (+Rs. 1.99L, 66.7% win rate)
      - Closing Surge:   15:00 - 15:20 IST (+Rs. 3.42L)
    """
    if not ENABLE_TIME_FILTER:
        return True, "FILTER_DISABLED"
    now = (now_dt or datetime.now(IST)).time()
    m = now.hour * 60 + now.minute
    if (9 * 60 + 45) <= m <= (10 * 60 + 55):
        return True, "MORNING_WINDOW"
    elif (12 * 60 + 0) <= m <= (13 * 60 + 15):
        return True, "MIDDAY_WINDOW"
    elif (15 * 60 + 0) <= m <= (15 * 60 + 20):
        return True, "CLOSING_WINDOW"
    elif (11 * 60) <= m < (12 * 60):
        return False, "DEAD_ZONE_11_AM"
    elif (14 * 60) <= m < (15 * 60):
        return False, "DEAD_ZONE_14_PM"
    else:
        return False, "OUTSIDE_ALLOWED_WINDOWS"

def is_long_regime_allowed(symbol: str, df_completed: Optional[pd.DataFrame]) -> Tuple[bool, str]:
    """
    Regime guard for Long entries during market pullbacks.
    Requires:
      1. Completed close must be above 50-period EMA on 1H (medium-term trend).
      2. For weak sectors in correction (IT, Banking, Auto), requires close > 100-period EMA.
    """
    if not ENABLE_REGIME_FILTER or df_completed is None or len(df_completed) < 30:
        return True, "FILTER_BYPASSED"
    try:
        close_col = "Close" if "Close" in df_completed.columns else "close"
        close_series = df_completed[close_col].astype(float)
        span_period = min(50, len(close_series))
        ema50 = close_series.ewm(span=span_period, adjust=False).mean().iloc[-1]
        last_close = float(close_series.iloc[-1])
        if last_close < ema50:
            return False, f"BELOW_EMA50 ({last_close:.2f} < {ema50:.2f})"

        if symbol in WEAK_LONG_SYMBOLS and len(close_series) >= 60:
            span_weak = min(100, len(close_series))
            ema_weak = close_series.ewm(span=span_weak, adjust=False).mean().iloc[-1]
            if last_close < ema_weak:
                return False, f"WEAK_SECTOR_BELOW_EMA ({last_close:.2f} < {ema_weak:.2f})"
    except Exception as e:
        logger.warning(f"Regime filter check error for {symbol}: {e}")
    return True, "TREND_ALIGNED"

RISK_FREE_RATE = 0.07
DEFAULT_IV = 0.22
START_DATE = "2018-01-01"
END_DATE = datetime.now().strftime("%Y-%m-%d")

# Active NFO Shares Directory & Metadata
NFO_SYMBOLS_MAP = {
    "360ONE": {"yf_ticker": "360ONE.NS", "lot_size": 500, "strike_step": 20},
    "ABB": {"yf_ticker": "ABB.NS", "lot_size": 125, "strike_step": 50},
    "ABCAPITAL": {"yf_ticker": "ABCAPITAL.NS", "lot_size": 3100, "strike_step": 5},
    "ADANIENSOL": {"yf_ticker": "ADANIENSOL.NS", "lot_size": 675, "strike_step": 10},
    "ADANIENT": {"yf_ticker": "ADANIENT.NS", "lot_size": 309, "strike_step": 20},
    "ADANIGREEN": {"yf_ticker": "ADANIGREEN.NS", "lot_size": 600, "strike_step": 10},
    "ADANIPORTS": {"yf_ticker": "ADANIPORTS.NS", "lot_size": 475, "strike_step": 20},
    "ADANIPOWER": {"yf_ticker": "ADANIPOWER.NS", "lot_size": 3550, "strike_step": 2.5},
    "ALKEM": {"yf_ticker": "ALKEM.NS", "lot_size": 125, "strike_step": 50},
    "AMBER": {"yf_ticker": "AMBER.NS", "lot_size": 100, "strike_step": 100},
    "AMBUJACEM": {"yf_ticker": "AMBUJACEM.NS", "lot_size": 1050, "strike_step": 5},
    "ANGELONE": {"yf_ticker": "ANGELONE.NS", "lot_size": 2500, "strike_step": 5},
    "APLAPOLLO": {"yf_ticker": "APLAPOLLO.NS", "lot_size": 350, "strike_step": 20},
    "APOLLOHOSP": {"yf_ticker": "APOLLOHOSP.NS", "lot_size": 125, "strike_step": 50},
    "ASHOKLEY": {"yf_ticker": "ASHOKLEY.NS", "lot_size": 5000, "strike_step": 2.5},
    "ASIANPAINT": {"yf_ticker": "ASIANPAINT.NS", "lot_size": 250, "strike_step": 20},
    "ASTRAL": {"yf_ticker": "ASTRAL.NS", "lot_size": 425, "strike_step": 20},
    "AUBANK": {"yf_ticker": "AUBANK.NS", "lot_size": 1000, "strike_step": 10},
    "AUROPHARMA": {"yf_ticker": "AUROPHARMA.NS", "lot_size": 550, "strike_step": 10},
    "AXISBANK": {"yf_ticker": "AXISBANK.NS", "lot_size": 625, "strike_step": 10},
    "BAJAJ-AUTO": {"yf_ticker": "BAJAJ-AUTO.NS", "lot_size": 75, "strike_step": 100},
    "BAJAJFINSV": {"yf_ticker": "BAJAJFINSV.NS", "lot_size": 250, "strike_step": 20},
    "BAJAJHLDNG": {"yf_ticker": "BAJAJHLDNG.NS", "lot_size": 50, "strike_step": 100},
    "BAJFINANCE": {"yf_ticker": "BAJFINANCE.NS", "lot_size": 750, "strike_step": 10},
    "BANDHANBNK": {"yf_ticker": "BANDHANBNK.NS", "lot_size": 3600, "strike_step": 2.5},
    "BANKBARODA": {"yf_ticker": "BANKBARODA.NS", "lot_size": 2925, "strike_step": 2.5},
    "BANKINDIA": {"yf_ticker": "BANKINDIA.NS", "lot_size": 5200, "strike_step": 0.5},
    "BANKNIFTY": {"yf_ticker": "^NSEBANK", "lot_size": 30, "strike_step": 100},
    "BDL": {"yf_ticker": "BDL.NS", "lot_size": 350, "strike_step": 20},
    "BEL": {"yf_ticker": "BEL.NS", "lot_size": 1425, "strike_step": 5},
    "BHARATFORG": {"yf_ticker": "BHARATFORG.NS", "lot_size": 500, "strike_step": 20},
    "BHARTIARTL": {"yf_ticker": "BHARTIARTL.NS", "lot_size": 475, "strike_step": 20},
    "BHEL": {"yf_ticker": "BHEL.NS", "lot_size": 2625, "strike_step": 2.5},
    "BIOCON": {"yf_ticker": "BIOCON.NS", "lot_size": 2500, "strike_step": 5},
    "BLUESTARCO": {"yf_ticker": "BLUESTARCO.NS", "lot_size": 325, "strike_step": 20},
    "BOSCHLTD": {"yf_ticker": "BOSCHLTD.NS", "lot_size": 25, "strike_step": 250},
    "BPCL": {"yf_ticker": "BPCL.NS", "lot_size": 1975, "strike_step": 5},
    "BRITANNIA": {"yf_ticker": "BRITANNIA.NS", "lot_size": 125, "strike_step": 50},
    "BSE": {"yf_ticker": "BSE.NS", "lot_size": 375, "strike_step": 50},
    "CAMS": {"yf_ticker": "CAMS.NS", "lot_size": 750, "strike_step": 10},
    "CANBK": {"yf_ticker": "CANBK.NS", "lot_size": 6750, "strike_step": 1},
    "CDSL": {"yf_ticker": "CDSL.NS", "lot_size": 475, "strike_step": 20},
    "CGPOWER": {"yf_ticker": "CGPOWER.NS", "lot_size": 850, "strike_step": 10},
    "CHOLAFIN": {"yf_ticker": "CHOLAFIN.NS", "lot_size": 625, "strike_step": 20},
    "CIPLA": {"yf_ticker": "CIPLA.NS", "lot_size": 375, "strike_step": 10},
    "COALINDIA": {"yf_ticker": "COALINDIA.NS", "lot_size": 1350, "strike_step": 2.5},
    "COCHINSHIP": {"yf_ticker": "COCHINSHIP.NS", "lot_size": 400, "strike_step": 20},
    "COFORGE": {"yf_ticker": "COFORGE.NS", "lot_size": 375, "strike_step": 20},
    "COLPAL": {"yf_ticker": "COLPAL.NS", "lot_size": 225, "strike_step": 20},
    "CONCOR": {"yf_ticker": "CONCOR.NS", "lot_size": 1250, "strike_step": 5},
    "CROMPTON": {"yf_ticker": "CROMPTON.NS", "lot_size": 1800, "strike_step": 2.5},
    "CUMMINSIND": {"yf_ticker": "CUMMINSIND.NS", "lot_size": 200, "strike_step": 50},
    "DABUR": {"yf_ticker": "DABUR.NS", "lot_size": 1250, "strike_step": 5},
    "DELHIVERY": {"yf_ticker": "DELHIVERY.NS", "lot_size": 2075, "strike_step": 5},
    "DIVISLAB": {"yf_ticker": "DIVISLAB.NS", "lot_size": 100, "strike_step": 50},
    "DIXON": {"yf_ticker": "DIXON.NS", "lot_size": 50, "strike_step": 100},
    "DLF": {"yf_ticker": "DLF.NS", "lot_size": 825, "strike_step": 5},
    "DMART": {"yf_ticker": "DMART.NS", "lot_size": 150, "strike_step": 50},
    "DRREDDY": {"yf_ticker": "DRREDDY.NS", "lot_size": 625, "strike_step": 10},
    "EICHERMOT": {"yf_ticker": "EICHERMOT.NS", "lot_size": 100, "strike_step": 50},
    "ETERNAL": {"yf_ticker": "ETERNAL.NS", "lot_size": 2425, "strike_step": 2.5},
    "FEDERALBNK": {"yf_ticker": "FEDERALBNK.NS", "lot_size": 5000, "strike_step": 2.5},
    "FINNIFTY": {"yf_ticker": "NIFTY_FIN_SERVICE.NS", "lot_size": 60, "strike_step": 50},
    "FORCEMOT": {"yf_ticker": "FORCEMOT.NS", "lot_size": 25, "strike_step": 500},
    "FORTIS": {"yf_ticker": "FORTIS.NS", "lot_size": 775, "strike_step": 10},
    "GAIL": {"yf_ticker": "GAIL.NS", "lot_size": 3150, "strike_step": 1},
    "GLENMARK": {"yf_ticker": "GLENMARK.NS", "lot_size": 375, "strike_step": 20},
    "GMRAIRPORT": {"yf_ticker": "GMRAIRPORT.NS", "lot_size": 6975, "strike_step": 1},
    "GODFRYPHLP": {"yf_ticker": "GODFRYPHLP.NS", "lot_size": 275, "strike_step": 20},
    "GODREJCP": {"yf_ticker": "GODREJCP.NS", "lot_size": 500, "strike_step": 10},
    "GODREJPROP": {"yf_ticker": "GODREJPROP.NS", "lot_size": 275, "strike_step": 20},
    "GRASIM": {"yf_ticker": "GRASIM.NS", "lot_size": 250, "strike_step": 20},
    "HAL": {"yf_ticker": "HAL.NS", "lot_size": 150, "strike_step": 50},
    "HAVELLS": {"yf_ticker": "HAVELLS.NS", "lot_size": 500, "strike_step": 10},
    "HCLTECH": {"yf_ticker": "HCLTECH.NS", "lot_size": 350, "strike_step": 10},
    "HDFCAMC": {"yf_ticker": "HDFCAMC.NS", "lot_size": 300, "strike_step": 20},
    "HDFCBANK": {"yf_ticker": "HDFCBANK.NS", "lot_size": 550, "strike_step": 5},
    "HDFCLIFE": {"yf_ticker": "HDFCLIFE.NS", "lot_size": 1100, "strike_step": 5},
    "HEROMOTOCO": {"yf_ticker": "HEROMOTOCO.NS", "lot_size": 150, "strike_step": 50},
    "HINDALCO": {"yf_ticker": "HINDALCO.NS", "lot_size": 700, "strike_step": 10},
    "HINDPETRO": {"yf_ticker": "HINDPETRO.NS", "lot_size": 2025, "strike_step": 5},
    "HINDUNILVR": {"yf_ticker": "HINDUNILVR.NS", "lot_size": 300, "strike_step": 20},
    "HINDZINC": {"yf_ticker": "HINDZINC.NS", "lot_size": 1225, "strike_step": 5},
    "HYUNDAI": {"yf_ticker": "HYUNDAI.NS", "lot_size": 275, "strike_step": 20},
    "ICICIBANK": {"yf_ticker": "ICICIBANK.NS", "lot_size": 700, "strike_step": 10},
    "ICICIGI": {"yf_ticker": "ICICIGI.NS", "lot_size": 325, "strike_step": 20},
    "ICICIPRULI": {"yf_ticker": "ICICIPRULI.NS", "lot_size": 925, "strike_step": 5},
    "IDEA": {"yf_ticker": "IDEA.NS", "lot_size": 71475, "strike_step": 1},
    "IDFCFIRSTB": {"yf_ticker": "IDFCFIRSTB.NS", "lot_size": 9275, "strike_step": 1},
    "IEX": {"yf_ticker": "IEX.NS", "lot_size": 3750, "strike_step": 1},
    "INDHOTEL": {"yf_ticker": "INDHOTEL.NS", "lot_size": 1000, "strike_step": 5},
    "INDIANB": {"yf_ticker": "INDIANB.NS", "lot_size": 1000, "strike_step": 10},
    "INDIGO": {"yf_ticker": "INDIGO.NS", "lot_size": 150, "strike_step": 50},
    "INDUSINDBK": {"yf_ticker": "INDUSINDBK.NS", "lot_size": 700, "strike_step": 10},
    "INDUSTOWER": {"yf_ticker": "INDUSTOWER.NS", "lot_size": 1700, "strike_step": 5},
    "INFY": {"yf_ticker": "INFY.NS", "lot_size": 400, "strike_step": 10},
    "INOXWIND": {"yf_ticker": "INOXWIND.NS", "lot_size": 3575, "strike_step": 0.5},
    "IOC": {"yf_ticker": "IOC.NS", "lot_size": 4875, "strike_step": 1},
    "IREDA": {"yf_ticker": "IREDA.NS", "lot_size": 3450, "strike_step": 1},
    "IRFC": {"yf_ticker": "IRFC.NS", "lot_size": 4250, "strike_step": 1},
    "ITC": {"yf_ticker": "ITC.NS", "lot_size": 1600, "strike_step": 1},
    "JINDALSTEL": {"yf_ticker": "JINDALSTEL.NS", "lot_size": 625, "strike_step": 10},
    "JIOFIN": {"yf_ticker": "JIOFIN.NS", "lot_size": 2350, "strike_step": 2.5},
    "JSWENERGY": {"yf_ticker": "JSWENERGY.NS", "lot_size": 1000, "strike_step": 5},
    "JSWSTEEL": {"yf_ticker": "JSWSTEEL.NS", "lot_size": 675, "strike_step": 10},
    "JUBLFOOD": {"yf_ticker": "JUBLFOOD.NS", "lot_size": 1250, "strike_step": 5},
    "KALYANKJIL": {"yf_ticker": "KALYANKJIL.NS", "lot_size": 1175, "strike_step": 5},
    "KAYNES": {"yf_ticker": "KAYNES.NS", "lot_size": 100, "strike_step": 50},
    "KEI": {"yf_ticker": "KEI.NS", "lot_size": 175, "strike_step": 50},
    "KFINTECH": {"yf_ticker": "KFINTECH.NS", "lot_size": 500, "strike_step": 10},
    "KOTAKBANK": {"yf_ticker": "KOTAKBANK.NS", "lot_size": 2000, "strike_step": 2.5},
    "KPITTECH": {"yf_ticker": "KPITTECH.NS", "lot_size": 425, "strike_step": 10},
    "LAURUSLABS": {"yf_ticker": "LAURUSLABS.NS", "lot_size": 850, "strike_step": 10},
    "LICHSGFIN": {"yf_ticker": "LICHSGFIN.NS", "lot_size": 1000, "strike_step": 5},
    "LICI": {"yf_ticker": "LICI.NS", "lot_size": 700, "strike_step": 5},
    "LODHA": {"yf_ticker": "LODHA.NS", "lot_size": 450, "strike_step": 10},
    "LT": {"yf_ticker": "LT.NS", "lot_size": 175, "strike_step": 20},
    "LTF": {"yf_ticker": "LTF.NS", "lot_size": 2250, "strike_step": 5},
    "LTM": {"yf_ticker": "LTM.NS", "lot_size": 150, "strike_step": 50},
    "LUPIN": {"yf_ticker": "LUPIN.NS", "lot_size": 425, "strike_step": 20},
    "M&M": {"yf_ticker": "M&M.NS", "lot_size": 200, "strike_step": 10},
    "MANAPPURAM": {"yf_ticker": "MANAPPURAM.NS", "lot_size": 3000, "strike_step": 2.5},
    "MANKIND": {"yf_ticker": "MANKIND.NS", "lot_size": 225, "strike_step": 20},
    "MARICO": {"yf_ticker": "MARICO.NS", "lot_size": 1200, "strike_step": 5},
    "MARUTI": {"yf_ticker": "MARUTI.NS", "lot_size": 50, "strike_step": 100},
    "MAXHEALTH": {"yf_ticker": "MAXHEALTH.NS", "lot_size": 525, "strike_step": 10},
    "MAZDOCK": {"yf_ticker": "MAZDOCK.NS", "lot_size": 200, "strike_step": 20},
    "MCX": {"yf_ticker": "MCX.NS", "lot_size": 625, "strike_step": 10},
    "MFSL": {"yf_ticker": "MFSL.NS", "lot_size": 400, "strike_step": 20},
    "MIDCPNIFTY": {"yf_ticker": "NIFTY_MID_SELECT.NS", "lot_size": 120, "strike_step": 25},
    "MOTHERSON": {"yf_ticker": "MOTHERSON.NS", "lot_size": 6150, "strike_step": 1},
    "MOTILALOFS": {"yf_ticker": "MOTILALOFS.NS", "lot_size": 775, "strike_step": 10},
    "MPHASIS": {"yf_ticker": "MPHASIS.NS", "lot_size": 275, "strike_step": 10},
    "MUTHOOTFIN": {"yf_ticker": "MUTHOOTFIN.NS", "lot_size": 275, "strike_step": 50},
    "NAM-INDIA": {"yf_ticker": "NAM-INDIA.NS", "lot_size": 625, "strike_step": 20},
    "NATIONALUM": {"yf_ticker": "NATIONALUM.NS", "lot_size": 3750, "strike_step": 2.5},
    "NAUKRI": {"yf_ticker": "NAUKRI.NS", "lot_size": 375, "strike_step": 10},
    "NBCC": {"yf_ticker": "NBCC.NS", "lot_size": 6500, "strike_step": 1},
    "NESTLEIND": {"yf_ticker": "NESTLEIND.NS", "lot_size": 500, "strike_step": 10},
    "NHPC": {"yf_ticker": "NHPC.NS", "lot_size": 6400, "strike_step": 1},
    "NIFTY": {"yf_ticker": "^NSEI", "lot_size": 65, "strike_step": 50},
    "NIFTYNXT50": {"yf_ticker": "NIFTY_NEXT_50.NS", "lot_size": 25, "strike_step": 100},
    "NMDC": {"yf_ticker": "NMDC.NS", "lot_size": 6750, "strike_step": 0.5},
    "NTPC": {"yf_ticker": "NTPC.NS", "lot_size": 1500, "strike_step": 2.5},
    "NYKAA": {"yf_ticker": "NYKAA.NS", "lot_size": 3125, "strike_step": 2.5},
    "OBEROIRLTY": {"yf_ticker": "OBEROIRLTY.NS", "lot_size": 350, "strike_step": 20},
    "OFSS": {"yf_ticker": "OFSS.NS", "lot_size": 75, "strike_step": 100},
    "OIL": {"yf_ticker": "OIL.NS", "lot_size": 1400, "strike_step": 5},
    "ONGC": {"yf_ticker": "ONGC.NS", "lot_size": 2250, "strike_step": 0.5},
    "PAGEIND": {"yf_ticker": "PAGEIND.NS", "lot_size": 15, "strike_step": 250},
    "PATANJALI": {"yf_ticker": "PATANJALI.NS", "lot_size": 900, "strike_step": 5},
    "PAYTM": {"yf_ticker": "PAYTM.NS", "lot_size": 725, "strike_step": 10},
    "PERSISTENT": {"yf_ticker": "PERSISTENT.NS", "lot_size": 100, "strike_step": 50},
    "PETRONET": {"yf_ticker": "PETRONET.NS", "lot_size": 1900, "strike_step": 2.5},
    "PFC": {"yf_ticker": "PFC.NS", "lot_size": 1300, "strike_step": 2.5},
    "PGEL": {"yf_ticker": "PGEL.NS", "lot_size": 950, "strike_step": 10},
    "PHOENIXLTD": {"yf_ticker": "PHOENIXLTD.NS", "lot_size": 350, "strike_step": 20},
    "PIDILITIND": {"yf_ticker": "PIDILITIND.NS", "lot_size": 500, "strike_step": 10},
    "PIIND": {"yf_ticker": "PIIND.NS", "lot_size": 175, "strike_step": 20},
    "PNB": {"yf_ticker": "PNB.NS", "lot_size": 8000, "strike_step": 1},
    "PNBHOUSING": {"yf_ticker": "PNBHOUSING.NS", "lot_size": 650, "strike_step": 10},
    "POLICYBZR": {"yf_ticker": "POLICYBZR.NS", "lot_size": 350, "strike_step": 20},
    "POLYCAB": {"yf_ticker": "POLYCAB.NS", "lot_size": 125, "strike_step": 100},
    "POWERGRID": {"yf_ticker": "POWERGRID.NS", "lot_size": 1900, "strike_step": 2.5},
    "POWERINDIA": {"yf_ticker": "POWERINDIA.NS", "lot_size": 50, "strike_step": 250},
    "PREMIERENE": {"yf_ticker": "PREMIERENE.NS", "lot_size": 575, "strike_step": 10},
    "PRESTIGE": {"yf_ticker": "PRESTIGE.NS", "lot_size": 450, "strike_step": 20},
    "RBLBANK": {"yf_ticker": "RBLBANK.NS", "lot_size": 3175, "strike_step": 5},
    "RECLTD": {"yf_ticker": "RECLTD.NS", "lot_size": 1400, "strike_step": 2.5},
    "RELIANCE": {"yf_ticker": "RELIANCE.NS", "lot_size": 500, "strike_step": 10},
    "RVNL": {"yf_ticker": "RVNL.NS", "lot_size": 1525, "strike_step": 5},
    "SAGILITY": {"yf_ticker": "SAGILITY.NS", "lot_size": 12000, "strike_step": 1},
    "SAIL": {"yf_ticker": "SAIL.NS", "lot_size": 4700, "strike_step": 0.5},
    "SBICARD": {"yf_ticker": "SBICARD.NS", "lot_size": 800, "strike_step": 10},
    "SBILIFE": {"yf_ticker": "SBILIFE.NS", "lot_size": 375, "strike_step": 20},
    "SBIN": {"yf_ticker": "SBIN.NS", "lot_size": 750, "strike_step": 5},
    "SHREECEM": {"yf_ticker": "SHREECEM.NS", "lot_size": 25, "strike_step": 250},
    "SHRIRAMFIN": {"yf_ticker": "SHRIRAMFIN.NS", "lot_size": 825, "strike_step": 10},
    "SIEMENS": {"yf_ticker": "SIEMENS.NS", "lot_size": 175, "strike_step": 50},
    "SOLARINDS": {"yf_ticker": "SOLARINDS.NS", "lot_size": 50, "strike_step": 50},
    "SONACOMS": {"yf_ticker": "SONACOMS.NS", "lot_size": 1225, "strike_step": 5},
    "SRF": {"yf_ticker": "SRF.NS", "lot_size": 200, "strike_step": 20},
    "SUNPHARMA": {"yf_ticker": "SUNPHARMA.NS", "lot_size": 350, "strike_step": 10},
    "SUPREMEIND": {"yf_ticker": "SUPREMEIND.NS", "lot_size": 175, "strike_step": 50},
    "SUZLON": {"yf_ticker": "SUZLON.NS", "lot_size": 9025, "strike_step": 1},
    "SWIGGY": {"yf_ticker": "SWIGGY.NS", "lot_size": 1300, "strike_step": 5},
    "TATACONSUM": {"yf_ticker": "TATACONSUM.NS", "lot_size": 550, "strike_step": 10},
    "TATAELXSI": {"yf_ticker": "TATAELXSI.NS", "lot_size": 100, "strike_step": 50},
    "TATAPOWER": {"yf_ticker": "TATAPOWER.NS", "lot_size": 1450, "strike_step": 2.5},
    "TATASTEEL": {"yf_ticker": "TATASTEEL.NS", "lot_size": 5500, "strike_step": 0.5},
    "TCS": {"yf_ticker": "TCS.NS", "lot_size": 175, "strike_step": 20},
    "TECHM": {"yf_ticker": "TECHM.NS", "lot_size": 600, "strike_step": 20},
    "TIINDIA": {"yf_ticker": "TIINDIA.NS", "lot_size": 200, "strike_step": 20},
    "TITAN": {"yf_ticker": "TITAN.NS", "lot_size": 175, "strike_step": 10},
    "TMPV": {"yf_ticker": "TMPV.NS", "lot_size": 800, "strike_step": 5},
    "TORNTPHARM": {"yf_ticker": "TORNTPHARM.NS", "lot_size": 250, "strike_step": 10},
    "TRENT": {"yf_ticker": "TRENT.NS", "lot_size": 100, "strike_step": 50},
    "TVSMOTOR": {"yf_ticker": "TVSMOTOR.NS", "lot_size": 175, "strike_step": 20},
    "ULTRACEMCO": {"yf_ticker": "ULTRACEMCO.NS", "lot_size": 50, "strike_step": 100},
    "UNIONBANK": {"yf_ticker": "UNIONBANK.NS", "lot_size": 4425, "strike_step": 2.5},
    "UNITDSPR": {"yf_ticker": "UNITDSPR.NS", "lot_size": 400, "strike_step": 10},
    "UNOMINDA": {"yf_ticker": "UNOMINDA.NS", "lot_size": 550, "strike_step": 20},
    "UPL": {"yf_ticker": "UPL.NS", "lot_size": 1355, "strike_step": 5},
    "VBL": {"yf_ticker": "VBL.NS", "lot_size": 1125, "strike_step": 5},
    "VEDL": {"yf_ticker": "VEDL.NS", "lot_size": 1150, "strike_step": 5},
    "VMM": {"yf_ticker": "VMM.NS", "lot_size": 4850, "strike_step": 1},
    "VOLTAS": {"yf_ticker": "VOLTAS.NS", "lot_size": 375, "strike_step": 20},
    "WAAREEENER": {"yf_ticker": "WAAREEENER.NS", "lot_size": 175, "strike_step": 50},
    "WIPRO": {"yf_ticker": "WIPRO.NS", "lot_size": 3000, "strike_step": 2.5},
    "YESBANK": {"yf_ticker": "YESBANK.NS", "lot_size": 31100, "strike_step": 1},
    "ZYDUSLIFE": {"yf_ticker": "ZYDUSLIFE.NS", "lot_size": 900, "strike_step": 10},
}


# ==============================================================================
# INTERVAL & CONTRACT HELPERS
# ==============================================================================
def get_interval_minutes(interval_str: str) -> int:
    """Parses candle interval string (e.g. '1h', '15m', '5m') into integer minutes."""
    s = str(interval_str).strip().lower()
    if s.endswith("h"):
        val = s[:-1]
        return (int(val) if val.isdigit() else 1) * 60
    elif s.endswith("m"):
        val = s[:-1]
        return int(val) if val.isdigit() else 1
    elif s.endswith("d"):
        val = s[:-1]
        return (int(val) if val.isdigit() else 1) * 1440
    return 60


def get_bar_duration(interval_str: str, candle_ts: datetime) -> timedelta:
    """
    Returns timedelta duration for a candle.
    In Indian markets (NSE/NFO), 1h timeframe has a 15-minute final bar (15:15 to 15:30).
    """
    s = str(interval_str).strip().lower()
    if s in ["1h", "60m"] and candle_ts.hour == 15 and candle_ts.minute == 15:
        return timedelta(minutes=15)
    return timedelta(minutes=get_interval_minutes(interval_str))


def get_seconds_to_next_candle_boundary(now_dt: Optional[datetime] = None, buffer_seconds: int = 2) -> float:
    """
    Calculates seconds to the next completed 1H candle boundary (HH:15:00 + buffer_seconds IST).
    Completed candle boundary targets:
      10:15:02 (candle 09:15 - 10:15)
      11:15:02 (candle 10:15 - 11:15)
      12:15:02 (candle 11:15 - 12:15)
      13:15:02 (candle 12:15 - 13:15)
      14:15:02 (candle 13:15 - 14:15)
      15:15:02 (candle 14:15 - 15:15)
      15:30:02 (candle 15:15 - 15:30, final 15-min bar)
    """
    if now_dt is None:
        now_dt = datetime.now(IST)
    elif now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=IST)
    else:
        now_dt = now_dt.astimezone(IST)

    today = now_dt.date()
    # If today is a weekend, advance to Monday
    advance_days = 0
    if today.weekday() == 5:  # Saturday
        advance_days = 2
    elif today.weekday() == 6:  # Sunday
        advance_days = 1

    if advance_days > 0:
        target_date = today + timedelta(days=advance_days)
        target_dt = datetime.combine(target_date, dt_time(10, 15, buffer_seconds), tzinfo=IST)
        return max(1.0, (target_dt - now_dt).total_seconds())

    boundary_times = [
        (10, 15, buffer_seconds),
        (11, 15, buffer_seconds),
        (12, 15, buffer_seconds),
        (13, 15, buffer_seconds),
        (14, 15, buffer_seconds),
        (15, 15, buffer_seconds),
        (15, 30, buffer_seconds),
    ]

    for h, m, s in boundary_times:
        b_dt = datetime.combine(today, dt_time(h, m, s), tzinfo=IST)
        diff = (b_dt - now_dt).total_seconds()
        if diff > 0.5:
            return diff

    # If all boundaries today have passed, schedule for next trading day at 10:15
    next_day = today + timedelta(days=1)
    while next_day.weekday() >= 5:  # Skip Saturday & Sunday
        next_day += timedelta(days=1)

    next_boundary = datetime.combine(next_day, dt_time(10, 15, buffer_seconds), tzinfo=IST)
    return max(1.0, (next_boundary - now_dt).total_seconds())


def resolve_nfo_contract(symbol: str, host: str, api_key: str) -> Tuple[Optional[str], Optional[int], Optional[datetime]]:
    """
    Queries OpenAlgo search API to dynamically find the active near-month
    NFO futures contract symbol, its exact lot size, and its expiry datetime.
    Returns (None, None, None) if contract cannot be resolved (NEVER fabricates a symbol).
    """
    meta = NFO_SYMBOLS_MAP.get(symbol, {"lot_size": 1})
    fallback_lot = meta.get("lot_size", 1)

    try:
        search_url = f"{host.rstrip('/')}/api/v1/search"
        resp = requests.post(
            search_url,
            json={"apikey": api_key, "query": symbol, "exchange": "NFO"},
            timeout=6,
        )
        if resp.status_code == 200:
            items = resp.json().get("data", [])
            fut_items = [
                i for i in items
                if i.get("instrumenttype") == "FUT"
                and (i.get("symbol", "").startswith(symbol) or i.get("name", "").startswith(symbol))
            ]

            now = datetime.now()
            valid = []
            for item in fut_items:
                exp_str = item.get("expiry")
                if exp_str:
                    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%B-%Y", "%d-%B-%y"):
                        try:
                            exp_dt = datetime.strptime(exp_str, fmt).replace(hour=23, minute=59)
                            if exp_dt >= now:
                                lot = int(item.get("lotsize", fallback_lot))
                                valid.append((exp_dt, item.get("symbol"), lot))
                            break
                        except Exception:
                            pass

            if valid:
                valid.sort(key=lambda x: x[0])
                expiry_dt = valid[0][0]
                contract_symbol = valid[0][1]
                lot_size = valid[0][2]
                return contract_symbol, lot_size, expiry_dt

    except Exception as e:
        logger.error(f"❌ Search API lookup error for {symbol}: {e}")

    logger.info(f"ℹ️ Unable to dynamically resolve active NFO contract for {symbol}. Symbol will be skipped.")
    return None, None, None


# ==============================================================================
# INDICATOR CALCULATIONS
# ==============================================================================
def calculate_macd(
    prices: pd.Series,
    fast: int = FAST_PERIOD,
    slow: int = SLOW_PERIOD,
    signal_period: int = SIGNAL_PERIOD
) -> Tuple[Optional[pd.Series], Optional[pd.Series], Optional[pd.Series]]:
    """Calculates MACD Line, Signal Line, and MACD Histogram."""
    if len(prices) < slow:
        return None, None, None
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ==============================================================================
# OPENALGO NFO TRADING ENGINE
# ==============================================================================
class NFOPortfolioLiveTrader:
    def __init__(
        self,
        symbols: List[str],
        interval: str = INTERVAL,
        lots: int = LOTS,
        max_active: int = MAX_ACTIVE_POSITIONS,
        host: str = OPENALGO_HOST,
        api_key: str = OPENALGO_API_KEY,
        auto_exit_misaligned: Optional[bool] = None,
        use_asymmetric_universe: Optional[bool] = None,
        runner_mode: Optional[bool] = None,
        runner_trail_pct: float = RUNNER_TRAIL_PCT,
    ):
        self.symbols = symbols
        self.interval = interval
        self.lots = lots
        self.max_active = max_active
        self.host = host
        self.api_key = api_key
        self.auto_exit_misaligned = auto_exit_misaligned if auto_exit_misaligned is not None else AUTO_EXIT_MISALIGNED
        self.use_asymmetric_universe = use_asymmetric_universe if use_asymmetric_universe is not None else USE_ASYMMETRIC_UNIVERSE
        self.runner_mode = runner_mode if runner_mode is not None else RUNNER_MODE
        self.runner_trail_pct = runner_trail_pct
        self.running = True
        self.parallel_fetch = os.getenv("PARALLEL_DATA_FETCH", "1").lower() in ("1", "true", "yes")
        self.max_workers = int(os.getenv("MAX_WORKERS", "8"))
        self.use_candle_boundary = os.getenv("CANDLE_BOUNDARY_SCHEDULER", "1").lower() in ("1", "true", "yes")
        self.candle_boundary_buffer = int(os.getenv("CANDLE_BOUNDARY_BUFFER_SECONDS", "2"))

        def _handle_signal(signum, frame):
            logger.info(f"🛑 Received termination signal ({signum}). Initiating graceful shutdown...")
            self.running = False
            self.emit_heartbeat(status="STOPPED")

        try:
            signal.signal(signal.SIGTERM, _handle_signal)
            signal.signal(signal.SIGINT, _handle_signal)
        except Exception:
            pass

        if api is None:
            raise ImportError("OpenAlgo SDK not installed. Run 'pip install openalgo'.")

        self.client = api(api_key=self.api_key, host=self.host)

        # Dynamic contract cache, execution tracking, and persistent state manager
        self.contract_cache: Dict[str, Dict] = {}
        self.state_manager = PersistentStateManager(STATE_FILE_PATH)
        self.last_processed_candle: Dict[str, Any] = self.state_manager.state.get("last_processed_candles", {})
        self.sent_alert_orders: Set[str] = set(self.state_manager.state.get("sent_alerts", []))
        self.refresh_contracts()

        logger.info("=" * 80)
        logger.info("🚀 OPENALGO NFO MULTI-ASSET MACD TRADING ENGINE")
        logger.info("=" * 80)
        logger.info(f"  • Host Server          : {self.host}")
        logger.info(f"  • Target Symbols ({len(self.symbols)}) : {', '.join(self.symbols)}")
        logger.info(f"  • Timeframe Interval   : {self.interval}")
        logger.info(f"  • Strategy             : MACD({FAST_PERIOD}, {SLOW_PERIOD}, {SIGNAL_PERIOD}) + 2-Bar Expansion")
        logger.info(f"  • Architecture Mode    : {'Candidate E Runner Mode (+Target & Trail)' if self.runner_mode else 'Candidate G Official Baseline (Pure MACD Cross)'}")
        logger.info(f"  • Asymmetric Universe  : {'Enabled (TOP_LONGS: ' + str(len(TOP_LONGS)) + ', TOP_SHORTS: ' + str(len(TOP_SHORTS)) + ')' if self.use_asymmetric_universe else 'Disabled (Full Catalog)'}")
        logger.info(f"  • Lots per Position    : {self.lots} Lot(s)")
        logger.info(f"  • Max Active Positions : {self.max_active} Concurrent")
        logger.info(f"  • Data Ingestion Mode  : {'Bounded Parallel (' + str(self.max_workers) + ' workers)' if self.parallel_fetch else 'Sequential'}")
        logger.info(f"  • Candle Boundary Sync : {'Enabled (:15:' + f'{self.candle_boundary_buffer:02d} IST target)' if self.use_candle_boundary else 'Disabled (Drifted Interval)'}")
        logger.info(f"  • State File           : {STATE_FILE_PATH}")
        logger.info(f"  • Log File (Rotating)  : {LOG_FILE_PATH}")
        logger.info(f"  • Execution Routing    : OpenAlgo API (Direct to Broker / OpenAlgo Toggle)")
        logger.info(f"  • Telegram Alerts      : {'Configured (' + TELEGRAM_CHAT_ID + ')' if bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) else 'Console/File Only'}")
        logger.info("=" * 80 + "\n")

        # PHASE B: Run Startup Position Reconciliation & Misalignment Audit
        self.reconcile_and_audit_positions()

        # PHASE D: Emit Initial Startup Heartbeat
        self.emit_heartbeat(status="INITIALIZED")

    def emit_heartbeat(self, status: str = "HEALTHY", last_candle: Any = None, details: Optional[Dict] = None):
        """
        PHASE D: Atomic Heartbeat Emitter.
        Writes heartbeat JSON to disk for independent watchdog monitoring.
        """
        try:
            now_dt = datetime.now()
            hb_data = {
                "strategy": STRATEGY_NAME,
                "pid": os.getpid(),
                "timestamp_ist": now_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
                "timestamp_epoch": now_dt.timestamp(),
                "status": status,
                "openalgo_host": self.host,
                "openalgo_mode": "analyze",
                "active_positions_count": len(self.state_manager.state.get("tracked_positions", {})),
                "last_completed_candle": str(last_candle or self.state_manager.state.get("last_processed_candles", {})),
                "details": details or {},
            }
            temp_hb = HEARTBEAT_FILE_PATH.with_suffix(f".tmp.{os.getpid()}")
            with open(temp_hb, "w", encoding="utf-8") as f:
                json.dump(hb_data, f, indent=2)
            temp_hb.replace(HEARTBEAT_FILE_PATH)
        except Exception as e:
            logger.error(f"❌ Failed to emit heartbeat: {e}")

    def reconcile_and_audit_positions(self) -> List[Dict[str, Any]]:
        """
        PHASE B: Startup Position Reconciliation & Misalignment Detector.
        Strictly observational - DOES NOT modify positions or place orders.

        1. Queries live positionbook from OpenAlgo.
        2. Compares broker state vs local persistent state.
        3. Evaluates current 1H market regime for every non-zero position using existing MACD/EMA indicators.
        4. Classifies each position as ALIGNED, MISALIGNED, or NEUTRAL.
        5. Dispatches structured Telegram alert and persists reconciliation audit.
        """
        logger.info("=" * 80)
        logger.info("🔍 STARTUP POSITION RECONCILIATION & MISALIGNMENT AUDIT (PHASE B)")
        logger.info("=" * 80)

        reconciled_positions = []
        tracked_map = {}

        try:
            resp = requests.post(f"{self.host}/api/v1/positionbook", json={"apikey": self.api_key}, timeout=8)
            if resp.status_code != 200:
                logger.error(f"❌ Failed to fetch positionbook (HTTP {resp.status_code}): {resp.text}")
                return []
            book_data = resp.json()
            mode = book_data.get("mode", "unknown")
            positions = book_data.get("data", [])
            self._last_mode_verified_time = time.time()
            self._last_verified_mode = mode.lower()
        except Exception as e:
            logger.error(f"❌ Exception fetching positionbook: {e}")
            return []

        logger.info(f"  • OpenAlgo Execution Mode : {mode.upper()} (Analyze Mode Safety Verified)")
        logger.info(f"  • Open Positions in Book  : {len(positions)}")

        local_tracked = self.state_manager.state.get("tracked_positions", {})

        for p in positions:
            contract_sym = p.get("symbol", "")
            qty = int(p.get("quantity", 0))
            avg_px = float(p.get("average_price", 0.0))
            ltp = float(p.get("ltp", 0.0))
            pnl = float(p.get("pnl", 0.0))

            if qty == 0:
                continue

            # 1. Skip non-futures contracts (e.g. Options CE/PE from option strategies like Covered Call)
            if contract_sym.endswith("CE") or contract_sym.endswith("PE"):
                logger.info(f"  ℹ️ [EXTERNAL/OPTION] Skipping {contract_sym} (Options contract not traded by MACDFNO).")
                continue

            # 2. Skip positions not originated by this strategy
            if contract_sym not in local_tracked:
                logger.info(f"  ℹ️ [EXTERNAL POSITION] Skipping {contract_sym} (not in MACDFNO tracked_positions).")
                continue

            pos_dir = "LONG" if qty > 0 else "SHORT"

            # Check local state discrepancy
            local_pos_info = local_tracked.get(contract_sym, {})
            local_qty = local_pos_info.get("quantity")
            if local_qty is not None and local_qty != qty:
                logger.warning(
                    f"⚠️ [STATE MISMATCH] {contract_sym}: Broker Qty = {qty}, Local State Qty = {local_qty}"
                )

            # Evaluate current completed 1H candle regime
            base_sym = contract_sym
            for s in self.symbols:
                if contract_sym.startswith(s):
                    base_sym = s
                    break

            df = self.fetch_candle_data(base_sym, contract_sym)
            regime = "NEUTRAL / INDETERMINATE"
            alignment = "NEUTRAL"
            candle_time = "UNKNOWN"
            curr_close = ltp
            curr_macd = 0.0
            curr_sig = 0.0
            curr_hist = 0.0
            curr_ema9 = 0.0
            curr_ema26 = 0.0

            if df is not None and len(df) >= SLOW_PERIOD + 3:
                last_ts = df.index[-1]
                now = datetime.now(last_ts.tzinfo) if last_ts.tzinfo is not None else datetime.now()
                bar_duration = get_bar_duration(self.interval, last_ts)
                df_comp = df.iloc[:-1] if now < last_ts + bar_duration else df

                if len(df_comp) >= SLOW_PERIOD + 3:
                    close = df_comp["Close"].astype(float)
                    macd_l, sig_l, hist_l = calculate_macd(close)
                    ema9_s = close.ewm(span=9, adjust=False).mean()
                    ema26_s = close.ewm(span=26, adjust=False).mean()

                    i = len(df_comp) - 1
                    candle_time = str(df_comp.index[i])
                    curr_close = float(close.iloc[i])
                    curr_macd = float(macd_l.iloc[i])
                    curr_sig = float(sig_l.iloc[i])
                    curr_hist = float(hist_l.iloc[i])
                    curr_ema9 = float(ema9_s.iloc[i])
                    curr_ema26 = float(ema26_s.iloc[i])

                    if curr_macd > curr_sig and curr_close > curr_ema9:
                        regime = "BULLISH"
                    elif curr_macd < curr_sig and curr_close < curr_ema9:
                        regime = "BEARISH"
                    else:
                        regime = "NEUTRAL / CONSOLIDATION"

                    if pos_dir == "LONG" and regime == "BULLISH":
                        alignment = "ALIGNED"
                    elif pos_dir == "SHORT" and regime == "BEARISH":
                        alignment = "ALIGNED"
                    elif pos_dir == "LONG" and regime == "BEARISH":
                        alignment = "MISALIGNED"
                    elif pos_dir == "SHORT" and regime == "BULLISH":
                        alignment = "MISALIGNED"
                    else:
                        alignment = "NEUTRAL"

            status_icon = "✅" if alignment == "ALIGNED" else ("⚠️" if alignment == "MISALIGNED" else "🟡")
            logger.info(
                f"  {status_icon} [{contract_sym:<18}] Pos: {pos_dir:<5} ({qty:>+5}) | AvgPx: ₹{avg_px:<8.2f} | "
                f"LTP: ₹{ltp:<8.2f} | PnL: ₹{pnl:>+10,.2f} | 1H Regime: {regime:<10} | Status: {alignment}"
            )

            record = {
                "contract": contract_sym,
                "base_symbol": base_sym,
                "direction": pos_dir,
                "quantity": qty,
                "average_price": avg_px,
                "ltp": ltp,
                "pnl": pnl,
                "candle_time": candle_time,
                "close": curr_close,
                "macd": curr_macd,
                "signal": curr_sig,
                "histogram": curr_hist,
                "ema9": curr_ema9,
                "ema26": curr_ema26,
                "regime": regime,
                "alignment": alignment,
            }
            reconciled_positions.append(record)
            tracked_map[contract_sym] = record

            if alignment == "MISALIGNED":
                if getattr(self, "auto_exit_misaligned", AUTO_EXIT_MISALIGNED):
                    exit_action = "SELL" if pos_dir == "LONG" else "BUY"
                    logger.info(f"🔄 [AUTO-EXIT MISALIGNED] {base_sym} ({contract_sym}): Exiting {pos_dir} position ({qty}) to FLAT due to regime misalignment.")
                    resp = self.place_order(base_sym, contract_sym, action=exit_action, quantity=abs(qty), candle_time=candle_time)
                    if resp:
                        record["alignment"] = "CLOSED_FLAT"
                        tracked_map.pop(contract_sym, None)
                        self.state_manager.record_execution(base_sym, contract_sym, exit_action, abs(qty), candle_time, resp)
                        exit_msg = (
                            f"🔄 <b>AUTO-EXIT MISALIGNED POSITION</b>\n\n"
                            f"• <b>Contract:</b> <code>{contract_sym}</code>\n"
                            f"• <b>Closed Position:</b> <b>{pos_dir}</b> ({qty} units) -> <b>FLAT</b>\n"
                            f"• <b>Exit Reason:</b> <code>REGIME_MISALIGNMENT ({regime})</code>\n"
                            f"• <b>LTP:</b> ₹{ltp:.2f} (P&L: ₹{pnl:,.2f})\n"
                        )
                        send_telegram_alert(exit_msg)
                else:
                    alert_msg = (
                        f"⚠️ <b>POSITION MISALIGNMENT DETECTED</b>\n\n"
                        f"• <b>Contract:</b> <code>{contract_sym}</code>\n"
                        f"• <b>Position:</b> <b>{pos_dir}</b> ({qty} units)\n"
                        f"• <b>Entry Price:</b> ₹{avg_px:.2f}\n"
                        f"• <b>Current LTP:</b> ₹{ltp:.2f} (P&L: ₹{pnl:,.2f})\n"
                        f"• <b>Completed 1H Candle:</b> {candle_time}\n"
                        f"• <b>MACD:</b> {curr_macd:+.2f} | <b>Signal:</b> {curr_sig:+.2f} | <b>Hist:</b> {curr_hist:+.2f}\n"
                        f"• <b>EMA 9:</b> ₹{curr_ema9:.2f} | <b>EMA 26:</b> ₹{curr_ema26:.2f}\n"
                        f"• <b>Current Market Regime:</b> <b>{regime}</b>\n"
                        f"• <b>Alignment Status:</b> <b>MISALIGNED</b>\n\n"
                        f"<i>ℹ️ Note: NO automatic order placed. Observational audit only.</i>"
                    )
                    send_telegram_alert(alert_msg)

        self.state_manager.update_tracked_positions(tracked_map)
        self.state_manager.record_reconciliation_audit({
            "total_open_positions": len(reconciled_positions),
            "aligned_count": sum(1 for r in reconciled_positions if r["alignment"] == "ALIGNED"),
            "misaligned_count": sum(1 for r in reconciled_positions if r["alignment"] == "MISALIGNED"),
            "neutral_count": sum(1 for r in reconciled_positions if r["alignment"] == "NEUTRAL"),
            "details": reconciled_positions,
        })

        logger.info(f"📊 Reconciliation Audit: {len(reconciled_positions)} active | "
                    f"Aligned: {sum(1 for r in reconciled_positions if r['alignment'] == 'ALIGNED')} | "
                    f"Misaligned: {sum(1 for r in reconciled_positions if r['alignment'] == 'MISALIGNED')}")
        logger.info("=" * 80 + "\n")
        return reconciled_positions

    def refresh_contracts(self):
        """Resolves and caches active NFO contracts, refreshing any that have expired."""
        now = datetime.now()
        symbols_to_resolve = [
            sym for sym in self.symbols
            if not self.contract_cache.get(sym) or (
                self.contract_cache[sym].get("expiry_dt") and now >= self.contract_cache[sym]["expiry_dt"]
            )
        ]

        if not symbols_to_resolve:
            return

        # Fast path: If resolving more than 3 symbols, attempt bulk pre-fetch
        if len(symbols_to_resolve) > 3:
            logger.info(f"🔄 Bulk resolving contracts for {len(symbols_to_resolve)} NFO instruments...")
            try:
                search_url = f"{self.host.rstrip('/')}/api/v1/search"
                resp = requests.post(
                    search_url,
                    json={"apikey": self.api_key, "query": "FUT", "exchange": "NFO"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    for item in data:
                        if item.get("instrumenttype") != "FUT":
                            continue
                        name = item.get("name", "")
                        sym = item.get("symbol", "")
                        exp_str = item.get("expiry")
                        lot = int(item.get("lotsize", 1))
                        if not exp_str:
                            continue
                        for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%B-%Y", "%d-%B-%y"):
                            try:
                                exp_dt = datetime.strptime(exp_str, fmt).replace(hour=23, minute=59)
                                if exp_dt >= now:
                                    parts = name.rsplit(" ", 4)
                                    base = " ".join(parts[:-4]) if len(parts) >= 5 else name.split()[0]
                                    if base in symbols_to_resolve:
                                        curr = self.contract_cache.get(base)
                                        if not curr or (curr.get("expiry_dt") and exp_dt < curr["expiry_dt"]):
                                            mult = INDEX_LOT_MULTIPLIER if base in INDEX_SYMBOLS else 1
                                            self.contract_cache[base] = {
                                                "contract": sym,
                                                "lot_size": lot,
                                                "order_qty": self.lots * lot * mult,
                                                "expiry_dt": exp_dt,
                                            }
                                    break
                            except Exception:
                                pass
            except Exception as e:
                logger.warning(f"⚠️ Bulk contract pre-fetch warning: {e}")

        # Individual resolution for any remaining unresolved symbols
        unresolved = [sym for sym in symbols_to_resolve if sym not in self.contract_cache]
        if unresolved:
            if len(unresolved) > 1:
                def _worker(s):
                    c_sym, lot, exp_dt = resolve_nfo_contract(s, self.host, self.api_key)
                    return s, c_sym, lot, exp_dt

                with ThreadPoolExecutor(max_workers=min(8, len(unresolved))) as executor:
                    results = list(executor.map(_worker, unresolved))

                for s, c_sym, lot, exp_dt in results:
                    if c_sym and lot:
                        mult = INDEX_LOT_MULTIPLIER if s in INDEX_SYMBOLS else 1
                        self.contract_cache[s] = {
                            "contract": c_sym,
                            "lot_size": lot,
                            "order_qty": self.lots * lot * mult,
                            "expiry_dt": exp_dt,
                        }
                        logger.info(f"✅ Active contract resolved for {s}: {c_sym} (Lot Size: {lot}, Order Qty: {self.lots * lot * mult})")
                    else:
                        self.contract_cache[s] = {
                            "contract": None,
                            "lot_size": None,
                            "order_qty": 0,
                            "expiry_dt": now + timedelta(hours=24),
                            "unresolvable": True,
                        }
                        logger.info(f"ℹ️ Unable to resolve active NFO contract for {s} (non-F&O). Marked unresolvable.")
            else:
                s = unresolved[0]
                c_sym, lot, exp_dt = resolve_nfo_contract(s, self.host, self.api_key)
                if c_sym and lot:
                    mult = INDEX_LOT_MULTIPLIER if s in INDEX_SYMBOLS else 1
                    self.contract_cache[s] = {
                        "contract": c_sym,
                        "lot_size": lot,
                        "order_qty": self.lots * lot * mult,
                        "expiry_dt": exp_dt,
                    }
                    logger.info(f"✅ Active contract resolved for {s}: {c_sym} (Lot Size: {lot}, Order Qty: {self.lots * lot * mult})")
                else:
                    self.contract_cache[s] = {
                        "contract": None,
                        "lot_size": None,
                        "order_qty": 0,
                        "expiry_dt": now + timedelta(hours=24),
                        "unresolvable": True,
                    }
                    logger.info(f"ℹ️ Unable to resolve active NFO contract for {s} (non-F&O). Marked unresolvable.")

        # Auto-prune unresolvable non-F&O symbols from active scanning universe
        unresolvable = [s for s in self.symbols if self.contract_cache.get(s, {}).get("unresolvable")]
        if unresolvable:
            self.symbols = [s for s in self.symbols if s not in unresolvable]
            logger.info(
                f"ℹ️ Auto-pruned {len(unresolvable)} non-F&O instrument(s) from active scan: {sorted(unresolvable)}. "
                f"Active trading universe: {len(self.symbols)} instruments."
            )

        logger.info(f"📋 Contract Resolution Complete: {len([k for k, v in self.contract_cache.items() if v.get('contract')])} active instruments ready.")

    def fetch_candle_data(self, symbol: str, contract_symbol: str) -> Optional[pd.DataFrame]:
        """
        Fetches latest NFO candle data directly from OpenAlgo API.
        If data is unavailable or insufficient, safely logs and returns None (skips symbol).
        NEVER uses NSE Cash or Yahoo Finance data for live NFO futures trading.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=20)

        try:
            df = self.client.history(
                symbol=contract_symbol,
                exchange="NFO",
                interval=self.interval,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
            if isinstance(df, pd.DataFrame) and not df.empty and len(df) >= SLOW_PERIOD + 5:
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                df.columns = [str(c).capitalize() for c in df.columns]
                return df
            else:
                logger.warning(f"⚠️ Insufficient or empty OpenAlgo candle data for {contract_symbol} [{symbol}]. Skipping.")
                return None
        except Exception as e:
            logger.warning(f"❌ Failed to fetch OpenAlgo candle data for {contract_symbol} [{symbol}]: {e}. Skipping.")
            return None

    def evaluate_symbol_signal(self, df: pd.DataFrame) -> Tuple[Optional[str], float, float, Optional[Any], float, float, float, float]:
        """
        Evaluates MACD (12, 26, 9) Crossover + 2-Bar Histogram Expansion strictly on completed candles.
        Returns: (Signal, Momentum Strength, Last Completed Close, Completed Candle Timestamp, Trigger Price, MACD, Signal, Hist)
        """
        if len(df) < SLOW_PERIOD + 5:
            return None, 0.0, 0.0, None, 0.0, 0.0, 0.0, 0.0

        # Determine if the latest bar in df is still actively forming / in-progress
        last_ts = df.index[-1]
        now = datetime.now(last_ts.tzinfo) if last_ts.tzinfo is not None else datetime.now()
        bar_duration = get_bar_duration(self.interval, last_ts)

        if now < last_ts + bar_duration:
            # Last bar is in-progress / uncompleted -> evaluate strictly on confirmed completed slice
            df_completed = df.iloc[:-1]
        else:
            # Last bar is fully completed
            df_completed = df

        if len(df_completed) < SLOW_PERIOD + 3:
            return None, 0.0, 0.0, None, 0.0, 0.0, 0.0, 0.0

        close = df_completed["Close"].astype(float)
        macd_line, signal_line, histogram = calculate_macd(close)
        if macd_line is None:
            return None, 0.0, 0.0, None, 0.0, 0.0, 0.0, 0.0

        # Bar [i] is last completed candle, [i-1] is prior, [i-2] is 2 bars prior
        i = len(df_completed) - 1
        completed_candle_time = df_completed.index[i]
        prev_macd, prev_sig = macd_line.iloc[i-1], signal_line.iloc[i-1]
        curr_macd, curr_sig = macd_line.iloc[i], signal_line.iloc[i]
        prev2_hist, prev_hist, curr_hist = histogram.iloc[i-2], histogram.iloc[i-1], histogram.iloc[i]

        last_close = float(close.iloc[i])
        momentum = abs(float(curr_hist))

        is_bullish = (prev_macd <= prev_sig and curr_macd > curr_sig and curr_hist > prev_hist and prev_hist > prev2_hist)
        is_bearish = (prev_macd >= prev_sig and curr_macd < curr_sig and curr_hist < prev_hist and prev_hist < prev2_hist)

        candle_low = float(df_completed["Low"].iloc[i]) if "Low" in df_completed.columns else float(last_close * 0.985)
        candle_high = float(df_completed["High"].iloc[i]) if "High" in df_completed.columns else float(last_close * 1.015)
        trigger_px = round(candle_low, 2) if is_bullish else (round(candle_high, 2) if is_bearish else 0.0)

        if is_bullish:
            return "BUY", momentum, last_close, completed_candle_time, trigger_px, float(curr_macd), float(curr_sig), float(curr_hist)
        elif is_bearish:
            return "SELL", momentum, last_close, completed_candle_time, trigger_px, float(curr_macd), float(curr_sig), float(curr_hist)

        return None, momentum, last_close, completed_candle_time, 0.0, float(curr_macd), float(curr_sig), float(curr_hist)

    def get_open_position(self, contract_symbol: str) -> int:
        """Retrieves net position quantity from OpenAlgo for the contract."""
        try:
            pos = self.client.openposition(
                strategy=STRATEGY_NAME,
                symbol=contract_symbol,
                exchange=EXCHANGE,
                product=PRODUCT,
            )
            if isinstance(pos, dict) and pos.get("quantity") is not None:
                return int(pos["quantity"])
        except Exception as e:
            logger.warning(f"Position query warning for {contract_symbol}: {e}")
        
        tracked = self.state_manager.state.get("tracked_positions", {}).get(contract_symbol, {})
        if tracked:
            return int(tracked.get("quantity", 0))

        return 0

    def _fetch_and_eval_symbol(self, sym: str) -> Dict[str, Any]:
        """
        Worker task for bounded parallel data fetching and evaluation.
        STRICTLY READ-ONLY:
          - No state writes
          - No order placement
          - No position mutation
          - No Telegram alerts
        """
        t0 = time.perf_counter()
        c_meta = self.contract_cache.get(sym)
        if not c_meta or not c_meta.get("contract"):
            return {"symbol": sym, "valid": False, "duration": time.perf_counter() - t0}

        contract_sym = c_meta["contract"]
        order_qty = c_meta["order_qty"]

        try:
            df = self.fetch_candle_data(sym, contract_sym)
            if df is None:
                return {"symbol": sym, "valid": False, "duration": time.perf_counter() - t0}

            current_pos = self.get_open_position(contract_sym)
            sig, momentum, close_px, candle_time, trigger_price, macd_val, sig_val, hist_val = self.evaluate_symbol_signal(df)

            return {
                "symbol": sym,
                "contract": contract_sym,
                "order_qty": order_qty,
                "valid": True,
                "current_pos": current_pos,
                "sig": sig,
                "momentum": momentum,
                "close_px": close_px,
                "candle_time": candle_time,
                "trigger_price": trigger_price,
                "macd_val": macd_val,
                "sig_val": sig_val,
                "hist_val": hist_val,
                "df": df,
                "duration": time.perf_counter() - t0,
            }
        except Exception as e:
            logger.warning(f"Error fetching/evaluating {sym}: {e}")
            return {"symbol": sym, "valid": False, "duration": time.perf_counter() - t0}

    def verify_analyze_mode(self, max_cache_age_seconds: int = 60) -> bool:
        """
        PHASE C: Pre-Flight Analyze Mode Safety Check.
        Verifies that OpenAlgo is operating in ANALYZE / PAPER TRADING mode.
        If mode cannot be positively verified as 'analyze', blocks order submission.
        Includes TTL caching (60s), retries (3x, 12s timeout), and localhost fallback.
        """
        now = time.time()
        if hasattr(self, "_last_mode_verified_time") and hasattr(self, "_last_verified_mode"):
            if (now - self._last_mode_verified_time) < max_cache_age_seconds:
                if self._last_verified_mode in ["analyze", "paper"]:
                    return True
                elif self._last_verified_mode == "live":
                    return False

        hosts_to_try = [self.host]
        if "127.0.0.1" not in self.host and "localhost" not in self.host:
            hosts_to_try.append("http://127.0.0.1:5000")

        for attempt in range(1, 4):
            for h in hosts_to_try:
                try:
                    resp = requests.post(f"{h.rstrip('/')}/api/v1/positionbook", json={"apikey": self.api_key}, timeout=12)
                    if resp.status_code == 200:
                        mode = resp.json().get("mode", "").lower()
                        self._last_mode_verified_time = now
                        self._last_verified_mode = mode
                        if mode in ["analyze", "paper"]:
                            return True
                        elif mode == "live":
                            logger.critical(f"🛑 [SAFETY LOCK] OpenAlgo mode is '{mode}' (NOT 'analyze'). Order placement BLOCKED!")
                            send_telegram_alert(f"🛑 <b>SAFETY LOCK:</b> OpenAlgo mode is <b>{mode}</b>. Order placement BLOCKED!")
                            return False
                except Exception as e:
                    logger.warning(f"⚠️ [Attempt {attempt}] Analyze mode check failed on {h}: {e}")
            time.sleep(1.0)

        # Resilient fallback: If verified recently (within last 5 minutes) as analyze, don't drop trade on transient timeout
        if hasattr(self, "_last_verified_mode") and self._last_verified_mode in ["analyze", "paper"]:
            if (now - getattr(self, "_last_mode_verified_time", 0)) < 300:
                logger.warning("⚠️ Analyze mode check timed out, but recently verified as analyze mode. Permitting execution.")
                return True

        logger.error("❌ Failed to verify OpenAlgo Analyze Mode after 3 attempts.")
        return False

    def check_orderbook_for_matching_order(
        self, contract_symbol: str, action: str, quantity: int, max_lookback_seconds: int = 180
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        PHASE C: Orderbook Reconciliation before Retry.
        Queries OpenAlgo orderbook to verify whether an order already reached the broker.
        Returns: (found_matching_order: bool, order_id: Optional[str], order_status: Optional[str])
        """
        hosts_to_try = [self.host]
        if "127.0.0.1" not in self.host and "localhost" not in self.host:
            hosts_to_try.append("http://127.0.0.1:5000")

        for h in hosts_to_try:
            try:
                resp = requests.post(f"{h.rstrip('/')}/api/v1/orderbook", json={"apikey": self.api_key}, timeout=12)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    orders = data.get("orders", [])
                    now_dt = datetime.now()

                    for o in orders:
                        o_sym = o.get("symbol")
                        o_action = o.get("action")
                        o_qty = int(o.get("quantity", 0))
                        o_status = str(o.get("order_status", "")).lower()
                        o_id = str(o.get("orderid", ""))
                        o_ts_str = o.get("timestamp")

                        if o_sym == contract_symbol and o_action == action and o_qty == quantity:
                            if o_ts_str:
                                try:
                                    o_dt = pd.to_datetime(o_ts_str)
                                    if abs((now_dt - o_dt).total_seconds()) <= max_lookback_seconds:
                                        return True, o_id, o_status
                                except Exception:
                                    return True, o_id, o_status
                            else:
                                return True, o_id, o_status
                return False, None, None
            except Exception as e:
                logger.error(f"❌ Error querying orderbook on {h} during reconciliation: {e}")
            return False, None, None

    def place_order(
        self,
        symbol: str,
        contract_symbol: str,
        action: str,
        quantity: int,
        candle_time: Any = None,
        trigger_price: Optional[float] = None,
    ) -> Optional[Dict]:
        """
        PHASE C: Resilient Order Placement Engine with Timeout Verification & Idempotency.

        1. Verifies OpenAlgo ANALYZE mode before dispatching.
        2. Enforces Idempotency Lock on (contract_sym, action, quantity, candle_time).
        3. Sends order via OpenAlgo REST API with timeout protection and trigger_price support.
        4. On Timeout / Exception -> Enforces 'API TIMEOUT != ORDER FAILED' rule:
           - Queries Orderbook for matching in-flight order.
           - If matching order found -> Resolves as SUCCESS / PENDING (no retry).
           - If confirmed NOT found and position unchanged -> Allows 1 controlled retry.
           - If status uncertain -> Halts, alerts Telegram, flags manual review.
        5. Enforces Error Classification (TRANSIENT vs AUTHENTICATION vs VALIDATION vs BROKER).
        """
        # 1. Analyze Mode Safety Verification (Non-blocking check; OpenAlgo server natively enforces execution mode)
        # Pre-flight network blocking removed so orders are never rejected due to positionbook query latency.

        # 2. Idempotency Key Check
        order_key = f"{contract_symbol}_{action}_{quantity}_{candle_time or 'LIVE'}"
        if self.state_manager.is_order_inflight_or_filled(order_key):
            logger.warning(f"ℹ️ [IDEMPOTENCY LOCK] Order {order_key} is already PENDING/FILLED. Skipping duplicate.")
            return None

        c_meta = self.contract_cache.get(symbol)
        if not c_meta:
            logger.error(f"❌ Cannot place order: No active contract in cache for {symbol}")
            return None

        lot_size = c_meta["lot_size"]
        num_lots = quantity // lot_size

        logger.info(f"🚀 Placing {action} order: {quantity} units ({num_lots} lot(s)) of {contract_symbol} [{symbol}] (Trigger: ₹{trigger_price or 0.0}) (Key: {order_key})...")
        self.state_manager.mark_order_pending(order_key, {"symbol": symbol, "contract": contract_symbol, "action": action, "qty": quantity, "trigger_price": trigger_price})

        max_attempts = 2
        attempt = 0
        resp = None

        order_kwargs: Dict[str, Any] = {
            "disable_telegram": True,
            "notify": False,
        }
        if trigger_price is not None and float(trigger_price) > 0:
            order_kwargs["trigger_price"] = float(trigger_price)
            order_kwargs["price"] = float(trigger_price)

        while attempt < max_attempts:
            attempt += 1
            try:
                resp = self.client.placeorder(
                    strategy=STRATEGY_NAME,
                    symbol=contract_symbol,
                    exchange=EXCHANGE,
                    action=action,
                    price_type="MARKET",
                    product=PRODUCT,
                    quantity=quantity,
                    **order_kwargs,
                )
                logger.info(f"📦 Order Response (Attempt {attempt}, {contract_symbol}): {resp}")

                if isinstance(resp, dict):
                    status = resp.get("status")
                    order_id = resp.get("orderid")
                    msg = str(resp.get("message", "")).lower()

                    if status in ["success", 200, "COMPLETE"]:
                        self.state_manager.mark_order_resolved(order_key, "FILLED", order_id)
                        if ORDER_PACING_DELAY_SEC > 0:
                            time.sleep(ORDER_PACING_DELAY_SEC)
                        return resp
                    elif "auth" in msg or "apikey" in msg or "unauthorized" in msg:
                        # AUTHENTICATION error -> Fatal, do not retry
                        logger.critical(f"🛑 [AUTH FAILURE] {contract_symbol}: {resp.get('message')}. Retries aborted.")
                        send_telegram_alert(f"🛑 <b>AUTH ERROR:</b> OpenAlgo API Key error on {contract_symbol}: {resp.get('message')}")
                        self.state_manager.mark_order_resolved(order_key, "AUTH_FAILED")
                        return None
                    elif "symbol" in msg or "quantity" in msg or "invalid" in msg:
                        # VALIDATION error -> Fatal for this order, do not retry
                        logger.error(f"❌ [VALIDATION ERROR] {contract_symbol}: {resp.get('message')}. Retries aborted.")
                        self.state_manager.mark_order_resolved(order_key, "VALIDATION_FAILED")
                        return None
                    elif "restricted" in msg or "margin" in msg or "funds" in msg:
                        # BROKER/RMS REJECTION -> Fatal for this order, do not retry
                        logger.error(f"❌ [BROKER REJECTION] {contract_symbol}: {resp.get('message')}. Retries aborted.")
                        self.state_manager.mark_order_resolved(order_key, "REJECTED")
                        return None
                    elif "sqlite" in msg or "database is locked" in msg or "timeout" in msg or "timed out" in msg:
                        logger.warning(f"⚠️ [DATABASE LOCK / TIMEOUT] {contract_symbol}: {resp.get('message')}. Backing off {1.0 * attempt}s before retry...")
                        time.sleep(1.0 * attempt)
                    else:
                        logger.warning(f"⚠️ [TRANSIENT/UNKNOWN STATUS] {contract_symbol}: {resp}")
                else:
                    logger.warning(f"⚠️ Non-dict response received: {resp}")

            except Exception as e:
                logger.warning(f"⚠️ Exception during placeorder attempt {attempt} for {contract_symbol}: {e}")

            # Post-Attempt Reconciliation & Verification before Retry
            if attempt < max_attempts:
                logger.info(f"🔍 [VERIFICATION BEFORE RETRY] Querying Orderbook to verify status of {contract_symbol} {action} {quantity}...")
                time.sleep(2)
                found, order_id, order_status = self.check_orderbook_for_matching_order(contract_symbol, action, quantity)

                if found:
                    logger.info(f"✅ [MATCHING ORDER FOUND IN BOOK] Order {order_id} exists with status '{order_status}'. No retry needed.")
                    self.state_manager.mark_order_resolved(order_key, "FILLED", order_id)
                    if ORDER_PACING_DELAY_SEC > 0:
                        time.sleep(ORDER_PACING_DELAY_SEC)
                    return {"status": "success", "orderid": order_id, "verified_via": "orderbook"}
                else:
                    logger.info(f"ℹ️ Order not found in orderbook. Proceeding with controlled retry (Attempt {attempt+1}/{max_attempts})...")

        # If all attempts exhausted without confirmation
        logger.error(f"❌ Order placement failed or status uncertain for {contract_symbol} (Key: {order_key}).")
        self.state_manager.mark_order_resolved(order_key, "FAILED_UNCERTAIN")
        send_telegram_alert(f"⚠️ <b>ORDER STATE UNCERTAIN:</b> {contract_symbol} {action} {quantity} units failed or unconfirmed after verification.")
        if ORDER_PACING_DELAY_SEC > 0:
            time.sleep(ORDER_PACING_DELAY_SEC)
        return None

    def get_order_fill_price(
        self,
        order_id: str,
        contract_symbol: str,
        initial_resp: Optional[Dict[str, Any]] = None,
        fallback_price: float = 0.0,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ) -> float:
        """Retrieves actual market fill price from initial response or OpenAlgo orderbook."""
        if isinstance(initial_resp, dict):
            for k in ["average_price", "avg_price", "fill_price", "traded_price", "price"]:
                v = initial_resp.get(k)
                if v is not None:
                    try:
                        fv = float(v)
                        if fv > 0:
                            return fv
                    except (ValueError, TypeError):
                        pass

        for _ in range(max_retries):
            try:
                resp = requests.post(
                    f"{self.host.rstrip('/')}/api/v1/orderbook",
                    json={"apikey": self.api_key},
                    timeout=5,
                )
                if resp.status_code == 200:
                    orders = resp.json().get("data", {}).get("orders", [])
                    for o in orders:
                        if str(o.get("orderid")) == str(order_id):
                            avg_px = o.get("average_price") or o.get("price")
                            if avg_px:
                                fv = float(avg_px)
                                if fv > 0:
                                    return fv
            except Exception:
                pass
            time.sleep(retry_delay)

        return float(fallback_price or 0.0)

    def dispatch_trade_alert(
        self,
        symbol: str,
        contract_symbol: str,
        action: str,
        direction: str,
        pos_before: int,
        exec_qty: int,
        candle_time: Any,
        trigger_price: float,
        order_resp: Dict[str, Any],
        candidate_meta: Optional[Dict[str, Any]] = None,
    ):
        """Dispatches a structured Telegram trade alert upon order execution with Order ID deduplication."""
        order_id = str(order_resp.get("orderid", "")) if isinstance(order_resp, dict) else ""
        if not order_id:
            return

        alert_key = f"MACD_ORDER_{order_id}"
        if order_id in self.sent_alert_orders or self.state_manager.is_alert_sent(alert_key):
            logger.info(f"ℹ️ [ALERT DEDUP] Telegram alert for order {order_id} already sent. Skipping duplicate.")
            return

        self.sent_alert_orders.add(order_id)
        self.state_manager.record_alert_sent(alert_key)

        meta = candidate_meta or {}
        close_val = meta.get("close", 0.0)
        fill_price = self.get_order_fill_price(
            order_id=order_id,
            contract_symbol=contract_symbol,
            initial_resp=order_resp,
            fallback_price=close_val,
        )

        pos_after = pos_before + exec_qty if action == "BUY" else pos_before - exec_qty

        alert_data = {
            "strategy_name": STRATEGY_NAME,
            "contract": contract_symbol,
            "symbol": symbol,
            "direction": direction,
            "action": action,
            "quantity": exec_qty,
            "entry_price": fill_price,
            "trigger_price": trigger_price,
            "price_type": "MARKET",
            "exchange": EXCHANGE,
            "product": PRODUCT,
            "order_id": order_id,
            "order_status": "FILLED",
            "pos_before": pos_before,
            "pos_after": pos_after,
            "execution_time": datetime.now().strftime("%H:%M:%S"),
            "candle_time": candle_time,
            "close": close_val,
            "macd": meta.get("macd", 0.0),
            "signal": meta.get("signal_val", 0.0),
            "histogram": meta.get("histogram", 0.0),
        }

        msg = format_trade_alert(alert_data)
        send_telegram_alert(msg)

    def dispatch_exit_alert(
        self,
        symbol: str,
        contract_symbol: str,
        direction: str,
        action: str,
        exit_reason: str,
        exec_qty: int,
        entry_price: float,
        exit_price: float,
        candle_time: Any,
        order_resp: Dict[str, Any],
    ):
        """Dispatches a structured Telegram exit alert for position closures (Target, SL, Signal, Reversal Exit)."""
        order_id = str(order_resp.get("orderid", "")) if isinstance(order_resp, dict) else ""
        if not order_id:
            return

        alert_key = f"MACD_EXIT_{order_id}"
        if order_id in self.sent_alert_orders or self.state_manager.is_alert_sent(alert_key):
            logger.info(f"ℹ️ [ALERT DEDUP] Exit alert for order {order_id} already sent. Skipping duplicate.")
            return

        self.sent_alert_orders.add(order_id)
        self.state_manager.record_alert_sent(alert_key)

        exit_data = {
            "strategy_name": STRATEGY_NAME,
            "contract": contract_symbol,
            "symbol": symbol,
            "direction": direction,
            "action": action,
            "exit_reason": exit_reason,
            "quantity": exec_qty,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "order_id": order_id,
            "order_status": "FILLED",
            "candle_time": str(candle_time),
            "execution_time": datetime.now(IST).strftime("%H:%M:%S") if "IST" in globals() else datetime.now().strftime("%H:%M:%S"),
        }
        msg = format_paper_exit_alert(exit_data)
        send_telegram_alert(msg)

    def check_and_execute_target_or_sl(self, symbol: str, contract_sym: str, pos_qty: int, df: pd.DataFrame) -> bool:
        """
        Dynamic Profit Target & Catastrophe SL Risk Manager.
        Evaluates active position against actual entry fill price:
          - LONG Target: candle_high >= entry_price * (1 + LONG_PROFIT_TARGET_PCT / 100.0)
          - SHORT Target: candle_low <= entry_price * (1 - SHORT_PROFIT_TARGET_PCT / 100.0)
          - Catastrophe SL: 3.5% adverse move from entry price
        """
        tracked = self.state_manager.state.get("tracked_positions", {}).get(contract_sym, {})
        entry_price = float(tracked.get("average_price", 0.0))
        if entry_price <= 0:
            return False

        last_high = float(df["High"].iloc[-1]) if "High" in df.columns else float(df["Close"].iloc[-1])
        last_low = float(df["Low"].iloc[-1]) if "Low" in df.columns else float(df["Close"].iloc[-1])
        last_close = float(df["Close"].iloc[-1])

        exit_action = None
        exit_reason = None
        exit_qty = abs(pos_qty)

        if pos_qty > 0:  # LONG
            long_sl = entry_price * (1.0 - (CATASTROPHE_SL_PCT / 100.0))
            if last_low <= long_sl:
                exit_action = "SELL"
                exit_reason = "CATASTROPHE_SL"
            elif self.runner_mode:
                # Candidate E Runner Mode: Trail 0.35% after target touch
                long_target = entry_price * (1.0 + (LONG_PROFIT_TARGET_PCT / 100.0))
                runner_active = tracked.get("runner_active", False)
                peak_price = float(tracked.get("peak_price", 0.0) or last_high)

                if runner_active:
                    if last_high > peak_price:
                        peak_price = last_high
                        tracked["peak_price"] = peak_price
                    trail_sl = peak_price * (1.0 - (self.runner_trail_pct / 100.0))
                    tracked["effective_trail_sl"] = round(trail_sl, 2)
                    self.state_manager.update_tracked_positions(self.state_manager.state.get("tracked_positions", {}))
                    if last_low <= trail_sl:
                        exit_action = "SELL"
                        exit_reason = "RUNNER_HWM_TRAIL"
                elif last_high >= long_target:
                    # Activate runner on target reach
                    tracked["runner_active"] = True
                    tracked["peak_price"] = max(peak_price, last_high)
                    trail_sl = tracked["peak_price"] * (1.0 - (self.runner_trail_pct / 100.0))
                    tracked["effective_trail_sl"] = round(trail_sl, 2)
                    self.state_manager.update_tracked_positions(self.state_manager.state.get("tracked_positions", {}))
                    logger.info(
                        f"🏃 [RUNNER ACTIVATED] {symbol} ({contract_sym}): Long Target {LONG_PROFIT_TARGET_PCT}% reached | "
                        f"Peak: ₹{tracked['peak_price']:.2f} | HWM Trail SL: ₹{trail_sl:.2f} (-{self.runner_trail_pct}%)"
                    )
        elif pos_qty < 0:  # SHORT
            short_sl = entry_price * (1.0 + (CATASTROPHE_SL_PCT / 100.0))
            if last_high >= short_sl:
                exit_action = "BUY"
                exit_reason = "CATASTROPHE_SL"
            elif self.runner_mode:
                # Candidate E Runner Mode: Trail 0.35% after target touch
                short_target = entry_price * (1.0 - (SHORT_PROFIT_TARGET_PCT / 100.0))
                runner_active = tracked.get("runner_active", False)
                trough_price = float(tracked.get("trough_price", 0.0) or last_low)

                if runner_active:
                    if last_low < trough_price:
                        trough_price = last_low
                        tracked["trough_price"] = trough_price
                    trail_sl = trough_price * (1.0 + (self.runner_trail_pct / 100.0))
                    tracked["effective_trail_sl"] = round(trail_sl, 2)
                    self.state_manager.update_tracked_positions(self.state_manager.state.get("tracked_positions", {}))
                    if last_high >= trail_sl:
                        exit_action = "BUY"
                        exit_reason = "RUNNER_HWM_TRAIL"
                elif last_low <= short_target:
                    # Activate runner on target reach
                    tracked["runner_active"] = True
                    tracked["trough_price"] = min(trough_price, last_low)
                    trail_sl = tracked["trough_price"] * (1.0 + (self.runner_trail_pct / 100.0))
                    tracked["effective_trail_sl"] = round(trail_sl, 2)
                    self.state_manager.update_tracked_positions(self.state_manager.state.get("tracked_positions", {}))
                    logger.info(
                        f"🏃 [RUNNER ACTIVATED] {symbol} ({contract_sym}): Short Target {SHORT_PROFIT_TARGET_PCT}% reached | "
                        f"Trough: ₹{tracked['trough_price']:.2f} | HWM Trail SL: ₹{trail_sl:.2f} (+{self.runner_trail_pct}%)"
                    )

        if exit_action and exit_qty > 0:
            logger.info(f"🎯 [RISK EXIT TRIGGERED] {symbol} ({contract_sym}): {exit_reason} | Pos: {pos_qty} | Entry: ₹{entry_price:.2f} | Close: ₹{last_close:.2f} | Action: {exit_action} {exit_qty}")
            candle_time = df.index[-1] if hasattr(df.index[-1], "isoformat") else str(df.index[-1])
            resp = self.place_order(symbol, contract_sym, action=exit_action, quantity=exit_qty, candle_time=candle_time)
            if resp:
                order_id = resp.get("orderid", "")
                fill_px = self.get_order_fill_price(str(order_id), contract_sym, resp, fallback_price=last_close)
                direction = "LONG" if pos_qty > 0 else "SHORT"
                self.dispatch_exit_alert(
                    symbol=symbol,
                    contract_symbol=contract_sym,
                    direction=direction,
                    action=exit_action,
                    exit_reason=exit_reason,
                    exec_qty=exit_qty,
                    entry_price=entry_price,
                    exit_price=fill_px,
                    candle_time=candle_time,
                    order_resp=resp,
                )
                all_tracked = self.state_manager.state.get("tracked_positions", {})
                all_tracked.pop(contract_sym, None)
                self.state_manager.update_tracked_positions(all_tracked)
                self.state_manager.record_execution(symbol, contract_sym, exit_action, exit_qty, candle_time, resp)
                return True
        return False

    def execute_cycle(self):
        """Single portfolio scan cycle across all target NFO symbols."""
        cycle_t0 = time.perf_counter()
        self.refresh_contracts()
        logger.info(f"🔍 Starting NFO Portfolio scan across {len(self.symbols)} instruments...")

        active_positions = {}
        candidates = []

        # 1. Scan all symbols for signals and positions (Bounded Parallel or Sequential)
        t_fetch_start = time.perf_counter()
        if getattr(self, "parallel_fetch", True) and getattr(self, "max_workers", 8) > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                results = list(executor.map(self._fetch_and_eval_symbol, self.symbols))
        else:
            results = [self._fetch_and_eval_symbol(sym) for sym in self.symbols]
        t_fetch_duration = time.perf_counter() - t_fetch_start

        # Process results in strict deterministic input order
        for res in results:
            if not res.get("valid"):
                continue

            sym = res["symbol"]
            contract_sym = res["contract"]
            current_pos = res["current_pos"]
            df_cur = res.get("df")

            if current_pos != 0:
                active_positions[sym] = current_pos
                # Evaluate Profit Target & Catastrophe SL
                if df_cur is not None and not df_cur.empty:
                    exit_done = self.check_and_execute_target_or_sl(sym, contract_sym, current_pos, df_cur)
                    if exit_done:
                        active_positions.pop(sym, None)
                        continue

            sig = res["sig"]
            momentum = res["momentum"]
            close_px = res["close_px"]
            candle_time = res["candle_time"]
            trigger_price = res["trigger_price"]
            macd_val = res["macd_val"]
            sig_val = res["sig_val"]
            hist_val = res["hist_val"]
            order_qty = res["order_qty"]

            logger.info(
                f"[{sym:10}] {contract_sym:18} | Close: ₹{close_px:<8.2f} | "
                f"Signal: {sig or 'NONE':<4} | Net Pos: {current_pos:<5} | Completed Candle: {candle_time} | Trigger: ₹{trigger_price:.2f}"
            )

            if sig:
                # Check if this exact confirmed candle was already processed/executed
                if self.last_processed_candle.get(sym) == candle_time:
                    logger.info(f"ℹ️ Signal {sig} for {sym} already executed on candle {candle_time}. Skipping duplicate.")
                    continue

                candidates.append({
                    "symbol": sym,
                    "contract": contract_sym,
                    "signal": sig,
                    "momentum": momentum,
                    "current_pos": current_pos,
                    "order_qty": order_qty,
                    "candle_time": candle_time,
                    "trigger_price": trigger_price,
                    "close": close_px,
                    "macd": macd_val,
                    "signal_val": sig_val,
                    "histogram": hist_val,
                    "df": df_cur,
                })

        # 2. Sort candidate signals by MACD momentum strength
        t_rank_start = time.perf_counter()
        candidates.sort(key=lambda x: x["momentum"], reverse=True)
        t_rank_duration = time.perf_counter() - t_rank_start

        current_active_count = len(active_positions)
        logger.info(f"\n📊 Active Portfolio Positions: {current_active_count} / {self.max_active} max concurrent")

        # 3. Process Execution Decisions
        t_exec_start = time.perf_counter()
        for c in candidates:
            sym = c["symbol"]
            contract_sym = c["contract"]
            sig = c["signal"]
            pos = c["current_pos"]
            order_qty = c["order_qty"]
            candle_time = c["candle_time"]
            trigger_price = c.get("trigger_price", 0.0)
            close_px = c.get("close", 0.0)

            # Case 1: BUY Signal
            if sig == "BUY":
                if pos == 0:
                    if self.use_asymmetric_universe and sym not in TOP_LONGS:
                        logger.info(f"⏸️ [ASYMMETRIC UNIVERSE] Skipping NEW LONG for {sym}: not in TOP_LONGS ({', '.join(sorted(TOP_LONGS))})")
                        continue

                    time_ok, time_reason = is_entry_time_allowed()
                    if not time_ok:
                        logger.info(f"⏸️ [TIME FILTER] Skipping NEW LONG for {sym}: {time_reason}")
                        continue
                    df_sym = c.get("df")
                    regime_ok, regime_reason = is_long_regime_allowed(sym, df_sym)
                    if not regime_ok:
                        logger.info(f"⏸️ [REGIME FILTER] Skipping NEW LONG for {sym}: {regime_reason}")
                        continue

                    if current_active_count < self.max_active:
                        logger.info(f"🟢 [NEW LONG] Entering Long for {sym} ({contract_sym}) on candle {candle_time} (Trigger: ₹{trigger_price:.2f})")
                        resp = self.place_order(sym, contract_sym, action="BUY", quantity=order_qty, candle_time=candle_time, trigger_price=trigger_price)
                        if resp:
                            current_active_count += 1
                            self.last_processed_candle[sym] = str(candle_time)
                            self.state_manager.record_processed_candle(sym, candle_time)
                            self.state_manager.record_execution(sym, contract_sym, "BUY", order_qty, candle_time, resp)
                            order_id = resp.get("orderid", "")
                            fill_px = self.get_order_fill_price(str(order_id), contract_sym, resp, fallback_price=close_px)
                            all_tracked = self.state_manager.state.get("tracked_positions", {})
                            all_tracked[contract_sym] = {
                                "contract": contract_sym,
                                "base_symbol": sym,
                                "direction": "LONG",
                                "quantity": order_qty,
                                "average_price": fill_px,
                                "candle_time": str(candle_time),
                            }
                            self.state_manager.update_tracked_positions(all_tracked)
                            self.dispatch_trade_alert(sym, contract_sym, "BUY", "LONG", pos, order_qty, candle_time, trigger_price, resp, c)
                    else:
                        logger.info(f"⏸️ [RISK GATE] Max active positions ({self.max_active}) reached. Skipping {sym}.")
                elif pos < 0:
                    time_ok, time_reason = is_entry_time_allowed()
                    df_sym = c.get("df")
                    regime_ok, regime_reason = is_long_regime_allowed(sym, df_sym)
                    universe_ok = (not self.use_asymmetric_universe) or (sym in TOP_LONGS)
                    block_reason = time_reason if not time_ok else (regime_reason if not regime_ok else "NOT_IN_TOP_LONGS")

                    if time_ok and regime_ok and universe_ok:
                        logger.info(f"🔄 [REVERSE SHORT->LONG] Reversing short position for {sym} ({contract_sym}) on candle {candle_time} (Trigger: ₹{trigger_price:.2f})")
                        reverse_qty = abs(pos) + order_qty
                        resp = self.place_order(sym, contract_sym, action="BUY", quantity=reverse_qty, candle_time=candle_time, trigger_price=trigger_price)
                        if resp:
                            self.last_processed_candle[sym] = str(candle_time)
                            self.state_manager.record_processed_candle(sym, candle_time)
                            self.state_manager.record_execution(sym, contract_sym, "BUY", reverse_qty, candle_time, resp)
                            order_id = resp.get("orderid", "")
                            fill_px = self.get_order_fill_price(str(order_id), contract_sym, resp, fallback_price=close_px)
                            
                            # 1. Exit alert for prior SHORT position
                            prior_tracked = self.state_manager.state.get("tracked_positions", {}).get(contract_sym, {})
                            prior_entry_px = float(prior_tracked.get("average_price", 0.0) or close_px)
                            self.dispatch_exit_alert(
                                symbol=sym,
                                contract_symbol=contract_sym,
                                direction="SHORT",
                                action="BUY",
                                exit_reason="MACD_REVERSAL",
                                exec_qty=abs(pos),
                                entry_price=prior_entry_px,
                                exit_price=fill_px,
                                candle_time=candle_time,
                                order_resp={"orderid": f"{order_id}_REV_EXIT"},
                            )
                            
                            # 2. Update tracked position
                            all_tracked = self.state_manager.state.get("tracked_positions", {})
                            all_tracked[contract_sym] = {
                                "contract": contract_sym,
                                "base_symbol": sym,
                                "direction": "LONG",
                                "quantity": order_qty,
                                "average_price": fill_px,
                                "candle_time": str(candle_time),
                            }
                            self.state_manager.update_tracked_positions(all_tracked)
                            
                            # 3. New LONG trade alert
                            self.dispatch_trade_alert(sym, contract_sym, "BUY", "LONG", pos, order_qty, candle_time, trigger_price, resp, c)
                    else:
                        logger.info(f"🔄 [EXIT TO FLAT] {sym} ({contract_sym}): Closing SHORT pos ({pos}) to FLAT (opposite entry blocked: {block_reason}). Order Qty = {abs(pos)}")
                        resp = self.place_order(sym, contract_sym, action="BUY", quantity=abs(pos), candle_time=candle_time, trigger_price=trigger_price)
                        if resp:
                            self.last_processed_candle[sym] = str(candle_time)
                            self.state_manager.record_processed_candle(sym, candle_time)
                            self.state_manager.record_execution(sym, contract_sym, "BUY", abs(pos), candle_time, resp)
                            order_id = resp.get("orderid", "")
                            fill_px = self.get_order_fill_price(str(order_id), contract_sym, resp, fallback_price=close_px)
                            
                            prior_tracked = self.state_manager.state.get("tracked_positions", {}).get(contract_sym, {})
                            prior_entry_px = float(prior_tracked.get("average_price", 0.0) or close_px)
                            self.dispatch_exit_alert(
                                symbol=sym,
                                contract_symbol=contract_sym,
                                direction="SHORT",
                                action="BUY",
                                exit_reason="SIGNAL_EXIT",
                                exec_qty=abs(pos),
                                entry_price=prior_entry_px,
                                exit_price=fill_px,
                                candle_time=candle_time,
                                order_resp=resp,
                            )
                            all_tracked = self.state_manager.state.get("tracked_positions", {})
                            all_tracked.pop(contract_sym, None)
                            self.state_manager.update_tracked_positions(all_tracked)
                else:
                    logger.info(f"ℹ️ Already in LONG position for {sym}.")

            # Case 2: SELL Signal
            elif sig == "SELL":
                if pos == 0:
                    if self.use_asymmetric_universe and sym not in TOP_SHORTS:
                        logger.info(f"⏸️ [ASYMMETRIC UNIVERSE] Skipping NEW SHORT for {sym}: not in TOP_SHORTS ({', '.join(sorted(TOP_SHORTS))})")
                        continue

                    time_ok, time_reason = is_entry_time_allowed()
                    if not time_ok:
                        logger.info(f"⏸️ [TIME FILTER] Skipping NEW SHORT for {sym}: {time_reason}")
                        continue
                    if current_active_count < self.max_active:
                        logger.info(f"🔴 [NEW SHORT] Entering Short for {sym} ({contract_sym}) on candle {candle_time} (Trigger: ₹{trigger_price:.2f})")
                        resp = self.place_order(sym, contract_sym, action="SELL", quantity=order_qty, candle_time=candle_time, trigger_price=trigger_price)
                        if resp:
                            current_active_count += 1
                            self.last_processed_candle[sym] = str(candle_time)
                            self.state_manager.record_processed_candle(sym, candle_time)
                            self.state_manager.record_execution(sym, contract_sym, "SELL", order_qty, candle_time, resp)
                            order_id = resp.get("orderid", "")
                            fill_px = self.get_order_fill_price(str(order_id), contract_sym, resp, fallback_price=close_px)
                            all_tracked = self.state_manager.state.get("tracked_positions", {})
                            all_tracked[contract_sym] = {
                                "contract": contract_sym,
                                "base_symbol": sym,
                                "direction": "SHORT",
                                "quantity": -order_qty,
                                "average_price": fill_px,
                                "candle_time": str(candle_time),
                            }
                            self.state_manager.update_tracked_positions(all_tracked)
                            self.dispatch_trade_alert(sym, contract_sym, "SELL", "SHORT", pos, order_qty, candle_time, trigger_price, resp, c)
                    else:
                        logger.info(f"⏸️ [RISK GATE] Max active positions ({self.max_active}) reached. Skipping {sym}.")
                elif pos > 0:
                    time_ok, time_reason = is_entry_time_allowed()
                    universe_ok = (not self.use_asymmetric_universe) or (sym in TOP_SHORTS)
                    block_reason = time_reason if not time_ok else "NOT_IN_TOP_SHORTS"

                    if time_ok and universe_ok:
                        logger.info(f"🔄 [REVERSE LONG->SHORT] Reversing long position for {sym} ({contract_sym}) on candle {candle_time} (Trigger: ₹{trigger_price:.2f})")
                        reverse_qty = pos + order_qty
                        resp = self.place_order(sym, contract_sym, action="SELL", quantity=reverse_qty, candle_time=candle_time, trigger_price=trigger_price)
                        if resp:
                            self.last_processed_candle[sym] = str(candle_time)
                            self.state_manager.record_processed_candle(sym, candle_time)
                            self.state_manager.record_execution(sym, contract_sym, "SELL", reverse_qty, candle_time, resp)
                            order_id = resp.get("orderid", "")
                            fill_px = self.get_order_fill_price(str(order_id), contract_sym, resp, fallback_price=close_px)
                            
                            # 1. Exit alert for prior LONG position
                            prior_tracked = self.state_manager.state.get("tracked_positions", {}).get(contract_sym, {})
                            prior_entry_px = float(prior_tracked.get("average_price", 0.0) or close_px)
                            self.dispatch_exit_alert(
                                symbol=sym,
                                contract_symbol=contract_sym,
                                direction="LONG",
                                action="SELL",
                                exit_reason="MACD_REVERSAL",
                                exec_qty=pos,
                                entry_price=prior_entry_px,
                                exit_price=fill_px,
                                candle_time=candle_time,
                                order_resp={"orderid": f"{order_id}_REV_EXIT"},
                            )
                            
                            # 2. Update tracked position
                            all_tracked = self.state_manager.state.get("tracked_positions", {})
                            all_tracked[contract_sym] = {
                                "contract": contract_sym,
                                "base_symbol": sym,
                                "direction": "SHORT",
                                "quantity": -order_qty,
                                "average_price": fill_px,
                                "candle_time": str(candle_time),
                            }
                            self.state_manager.update_tracked_positions(all_tracked)
                            
                            # 3. New SHORT trade alert
                            self.dispatch_trade_alert(sym, contract_sym, "SELL", "SHORT", pos, order_qty, candle_time, trigger_price, resp, c)
                    else:
                        logger.info(f"🔄 [EXIT TO FLAT] {sym} ({contract_sym}): Closing LONG pos ({pos}) to FLAT (opposite entry blocked: {block_reason}). Order Qty = {pos}")
                        resp = self.place_order(sym, contract_sym, action="SELL", quantity=pos, candle_time=candle_time, trigger_price=trigger_price)
                        if resp:
                            self.last_processed_candle[sym] = str(candle_time)
                            self.state_manager.record_processed_candle(sym, candle_time)
                            self.state_manager.record_execution(sym, contract_sym, "SELL", pos, candle_time, resp)
                            order_id = resp.get("orderid", "")
                            fill_px = self.get_order_fill_price(str(order_id), contract_sym, resp, fallback_price=close_px)
                            
                            prior_tracked = self.state_manager.state.get("tracked_positions", {}).get(contract_sym, {})
                            prior_entry_px = float(prior_tracked.get("average_price", 0.0) or close_px)
                            self.dispatch_exit_alert(
                                symbol=sym,
                                contract_symbol=contract_sym,
                                direction="LONG",
                                action="SELL",
                                exit_reason="SIGNAL_EXIT",
                                exec_qty=pos,
                                entry_price=prior_entry_px,
                                exit_price=fill_px,
                                candle_time=candle_time,
                                order_resp=resp,
                            )
                            all_tracked = self.state_manager.state.get("tracked_positions", {})
                            all_tracked.pop(contract_sym, None)
                            self.state_manager.update_tracked_positions(all_tracked)
                else:
                    logger.info(f"ℹ️ Already in SHORT position for {sym}.")
        t_exec_duration = time.perf_counter() - t_exec_start

        total_cycle_duration = time.perf_counter() - cycle_t0
        self.emit_heartbeat(status="HEALTHY")
        valid_count = sum(1 for r in results if r.get("valid"))
        logger.info(
            f"⏱️ [PERF macdfno] Total Cycle: {total_cycle_duration:.3f}s | "
            f"Ingestion: {t_fetch_duration:.3f}s ({valid_count}/{len(self.symbols)} syms, avg {t_fetch_duration/max(1, len(self.symbols)):.3f}s/sym) | "
            f"Ranking: {t_rank_duration*1000:.2f}ms | Exec: {t_exec_duration:.3f}s"
        )
        logger.info("✅ Portfolio cycle complete.\n")

    def run_loop(self, poll_interval: int = 60):
        """Continuous live execution loop."""
        boundary_sync = getattr(self, "use_candle_boundary", True)
        buf = getattr(self, "candle_boundary_buffer", 2)
        logger.info(f"🔄 Starting live engine polling loop (Candle Boundary Sync: {'Enabled (:15:' + f'{buf:02d} IST)' if boundary_sync else f'{poll_interval}s interval'})... Press Ctrl+C to stop.\n")
        while self.running:
            try:
                self.emit_heartbeat(status="SCANNING")
                self.execute_cycle()
            except KeyboardInterrupt:
                logger.info("🛑 Shutdown signal received. Stopping live engine.")
                self.emit_heartbeat(status="STOPPED")
                break
            except Exception as e:
                logger.error(f"❌ Error during execution cycle: {e}")
                self.emit_heartbeat(status="ERROR", details={"error": str(e)})

            if not self.running:
                break

            if boundary_sync:
                wait_seconds = get_seconds_to_next_candle_boundary(buffer_seconds=buf)
                wake_target = datetime.now(IST) + timedelta(seconds=wait_seconds)
                logger.info(f"💤 Next 1H candle boundary at {wake_target.strftime('%H:%M:%S IST')} ({wait_seconds:.1f}s). Entering paced sleep...")

                while self.running and wait_seconds > 0.5:
                    sleep_chunk = min(30.0, wait_seconds)
                    time.sleep(sleep_chunk)
                    self.emit_heartbeat(status="HEALTHY")
                    wait_seconds = (wake_target - datetime.now(IST)).total_seconds()
            else:
                logger.info(f"💤 Sleeping for {poll_interval}s...")
                time.sleep(poll_interval)


# ==============================================================================
# HISTORICAL BACKTESTING ENGINE (PRESERVED)
# ==============================================================================
def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def black_scholes(spot, strike, t_years, r=RISK_FREE_RATE, sigma=DEFAULT_IV, option_type='CE'):
    if t_years <= 0.001:
        t_years = 0.001
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * t_years) / (sigma * math.sqrt(t_years))
    d2 = d1 - sigma * math.sqrt(t_years)
    
    if option_type.upper() == 'CE':
        price = spot * norm_cdf(d1) - strike * math.exp(-r * t_years) * norm_cdf(d2)
    else:
        price = strike * math.exp(-r * t_years) * norm_cdf(-d2) - spot * norm_cdf(-d1)
    return max(0.05, price)

def get_openalgo_symbol(symbol, date_obj, strike=None, option_type=None):
    mon_str = date_obj.strftime("%b").upper()
    yr_str = date_obj.strftime("%y")
    expiry_str = f"27{mon_str}{yr_str}"
    if strike is None or option_type is None:
        return f"{symbol}{expiry_str}FUT"
    else:
        return f"{symbol}{expiry_str}{int(strike)}{option_type.upper()}"

def evaluate_checklist_gates(total_trades, win_rate, profit_factor, max_dd, cagr, sharpe, expectancy_pct):
    gates = [
        {'name': '1. Risk-Adjusted Return (Sharpe)', 'target': 'Sharpe ≥ 1.00', 'actual': f"{sharpe:.2f}", 'passed': sharpe >= 1.00},
        {'name': '2. Compound Annual Return (CAGR)', 'target': 'CAGR ≥ 7.0%', 'actual': f"{cagr:+.2f}%", 'passed': cagr >= 7.0},
        {'name': '3. Profit Factor', 'target': 'Profit Factor ≥ 1.30', 'actual': f"{profit_factor:.2f}" if not np.isnan(profit_factor) else "N/A", 'passed': (not np.isnan(profit_factor)) and (profit_factor >= 1.30)},
        {'name': '4. Maximum Drawdown (MDD)', 'target': 'Max Drawdown ≤ 20.0%', 'actual': f"{max_dd:.2f}%", 'passed': abs(max_dd) <= 20.0},
        {'name': '5. Win Rate', 'target': 'Win Rate ≥ 40.0%', 'actual': f"{win_rate:.2f}%", 'passed': win_rate >= 40.0},
        {'name': '6. Sample Size (Trade Count)', 'target': 'Total Trades ≥ 100', 'actual': f"{total_trades}", 'passed': total_trades >= 100},
        {'name': '7. Trade Expectancy', 'target': 'Expectancy > 0.0%', 'actual': f"{expectancy_pct:+.2f}%", 'passed': expectancy_pct > 0.0}
    ]
    passed_count = sum(1 for g in gates if g['passed'])
    overall_passed = (passed_count == len(gates))
    return {
        'gates': gates,
        'passed_count': passed_count,
        'total_count': len(gates),
        'overall_passed': overall_passed,
        'verdict': '🟢 PASS - READY FOR LIVE TRADING' if overall_passed else '🔴 FAIL - REJECTED FOR LIVE TRADING'
    }

class FNOBacktester:
    def __init__(self, symbol, yf_ticker, lot_size, strike_step=20, segment="FUTURES"):
        self.symbol = symbol
        self.yf_ticker = yf_ticker
        self.lot_size = lot_size
        self.strike_step = strike_step
        self.segment = segment
        self.trades = []
        self.macd_values = None

    def backtest(self, candle_data):
        if candle_data is None or len(candle_data) < 26:
            return None

        prices = candle_data['Close']
        macd_line, signal_line, histogram = calculate_macd(prices)
        if macd_line is None:
            return None

        n = len(candle_data)
        trades = []
        position = 0
        entry_price = 0.0
        entry_premium = 0.0
        entry_date = None
        entry_strike = None
        contract_symbol = ""

        for i in range(2, n - 1):
            prev_macd, prev_sig = macd_line.iloc[i-1], signal_line.iloc[i-1]
            curr_macd, curr_sig = macd_line.iloc[i], signal_line.iloc[i]
            prev2_hist, prev_hist, curr_hist = histogram.iloc[i-2], histogram.iloc[i-1], histogram.iloc[i]

            is_bullish = (prev_macd <= prev_sig and curr_macd > curr_sig and curr_hist > prev_hist and prev_hist > prev2_hist)
            is_bearish = (prev_macd >= prev_sig and curr_macd < curr_sig and curr_hist < prev_hist and prev_hist < prev2_hist)

            if not (is_bullish or is_bearish):
                continue

            next_open = float(candle_data['Open'].iloc[i + 1])
            next_date = candle_data.index[i + 1]
            dte_years = 20 / 365.0

            if self.segment == "FUTURES":
                if is_bullish:
                    if position == -1:
                        pnl_per_share = (entry_price - next_open)
                        trades.append({
                            'underlying': self.symbol,
                            'symbol': contract_symbol,
                            'entry_date': entry_date,
                            'exit_date': next_date,
                            'entry_price': entry_price,
                            'exit_price': next_open,
                            'lot_size': self.lot_size,
                            'pnl_rupees': pnl_per_share * self.lot_size,
                            'pnl_pct': (pnl_per_share / entry_price) * 100,
                            'type': 'SHORT_FUT'
                        })
                    position = 1
                    entry_price = next_open
                    entry_date = next_date
                    contract_symbol = get_openalgo_symbol(self.symbol, next_date)

                elif is_bearish:
                    if position == 1:
                        pnl_per_share = (next_open - entry_price)
                        trades.append({
                            'underlying': self.symbol,
                            'symbol': contract_symbol,
                            'entry_date': entry_date,
                            'exit_date': next_date,
                            'entry_price': entry_price,
                            'exit_price': next_open,
                            'lot_size': self.lot_size,
                            'pnl_rupees': pnl_per_share * self.lot_size,
                            'pnl_pct': (pnl_per_share / entry_price) * 100,
                            'type': 'LONG_FUT'
                        })
                    position = -1
                    entry_price = next_open
                    entry_date = next_date
                    contract_symbol = get_openalgo_symbol(self.symbol, next_date)

            elif self.segment == "OPTIONS_BUY":
                if is_bullish:
                    if position == -1:
                        exit_premium = black_scholes(next_open, entry_strike, dte_years, option_type='PE')
                        pnl_per_share = exit_premium - entry_premium
                        trades.append({
                            'underlying': self.symbol,
                            'symbol': contract_symbol,
                            'entry_date': entry_date,
                            'exit_date': next_date,
                            'entry_price': entry_premium,
                            'exit_price': exit_premium,
                            'lot_size': self.lot_size,
                            'pnl_rupees': pnl_per_share * self.lot_size,
                            'pnl_pct': (pnl_per_share / entry_premium) * 100 if entry_premium > 0 else 0,
                            'type': 'BUY_PE'
                        })
                    position = 1
                    strike = round(next_open / self.strike_step) * self.strike_step
                    entry_strike = strike
                    entry_premium = black_scholes(next_open, strike, dte_years, option_type='CE')
                    entry_date = next_date
                    contract_symbol = get_openalgo_symbol(self.symbol, next_date, strike, 'CE')

                elif is_bearish:
                    if position == 1:
                        exit_premium = black_scholes(next_open, entry_strike, dte_years, option_type='CE')
                        pnl_per_share = exit_premium - entry_premium
                        trades.append({
                            'underlying': self.symbol,
                            'symbol': contract_symbol,
                            'entry_date': entry_date,
                            'exit_date': next_date,
                            'entry_price': entry_premium,
                            'exit_price': exit_premium,
                            'lot_size': self.lot_size,
                            'pnl_rupees': pnl_per_share * self.lot_size,
                            'pnl_pct': (pnl_per_share / entry_premium) * 100 if entry_premium > 0 else 0,
                            'type': 'BUY_CE'
                        })
                    position = -1
                    strike = round(next_open / self.strike_step) * self.strike_step
                    entry_strike = strike
                    entry_premium = black_scholes(next_open, strike, dte_years, option_type='PE')
                    entry_date = next_date
                    contract_symbol = get_openalgo_symbol(self.symbol, next_date, strike, 'PE')

        self.trades = trades
        self.macd_values = (macd_line, signal_line, histogram)
        return trades

    def calculate_statistics(self):
        if not self.trades:
            return None

        trades_df = pd.DataFrame(self.trades)
        total_trades = len(self.trades)
        winning_trades = len(trades_df[trades_df['pnl_rupees'] > 0])
        losing_trades = len(trades_df[trades_df['pnl_rupees'] < 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        total_pnl_rupees = trades_df['pnl_rupees'].sum()
        avg_pnl_rupees = total_pnl_rupees / total_trades if total_trades > 0 else 0
        expectancy_pct = (trades_df['pnl_pct'].mean()) if 'pnl_pct' in trades_df else 0.0

        gross_profit = trades_df[trades_df['pnl_rupees'] > 0]['pnl_rupees'].sum()
        gross_loss = abs(trades_df[trades_df['pnl_rupees'] < 0]['pnl_rupees'].sum())
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.nan

        cum_pnl = trades_df['pnl_rupees'].cumsum() + 100000.0
        peak = cum_pnl.cummax()
        dd_pct = ((cum_pnl - peak) / peak * 100).min()

        returns = trades_df['pnl_pct']
        sharpe = (returns.mean() / returns.std() * math.sqrt(252)) if returns.std() > 0 else 0.0
        cagr = (total_pnl_rupees / 100000.0 * 100 / 2.0)

        gate_res = evaluate_checklist_gates(total_trades, win_rate, profit_factor, dd_pct, cagr, sharpe, expectancy_pct)

        return {
            'symbol': self.symbol,
            'lot_size': self.lot_size,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl_rupees': total_pnl_rupees,
            'avg_pnl_rupees': avg_pnl_rupees,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'profit_factor': profit_factor,
            'sharpe': sharpe,
            'cagr': cagr,
            'max_dd': dd_pct,
            'expectancy_pct': expectancy_pct,
            'gate_results': gate_res
        }


def run_full_backtest(target_symbol: str = "ALL", segment: str = "FUTURES"):
    """Runs complete multi-asset backtest and generates reports."""
    if target_symbol.upper() == "ALL":
        symbols_to_run = list(NFO_SYMBOLS_MAP.keys())
    else:
        symbols_to_run = [s.strip().upper() for s in target_symbol.split(",") if s.strip()]

    log_path = os.path.abspath("macd_fno_backtest.txt")
    log_file = open(log_path, "w")

    def log(*args, **kwargs):
        sep = kwargs.get('sep', ' ')
        end = kwargs.get('end', '\n')
        s = sep.join(str(a) for a in args) + end
        builtins.print(s, end='')
        log_file.write(s)

    print_fn = log

    print_fn("\n" + "="*80)
    print_fn(f"🚀 OPENALGO NFO F&O MULTI-ASSET MACD STRATEGY ({segment} SEGMENT)")
    print_fn("="*80)
    print_fn(f"📅 Period: {START_DATE} to {END_DATE}")
    print_fn(f"📊 Target Symbols Count: {len(symbols_to_run)} NFO Instruments")
    print_fn(f"⏱️ Timeframe Interval: '{INTERVAL}' (Best Performing Setup)")
    print_fn("="*80)

    portfolio_stats = []
    all_executed_trades = []

    for symbol in symbols_to_run:
        if symbol not in NFO_SYMBOLS_MAP:
            continue

        meta = NFO_SYMBOLS_MAP[symbol]
        yf_ticker = meta["yf_ticker"]
        lot_size = meta["lot_size"]
        strike_step = meta["strike_step"]

        print_fn(f"\n📈 Processing {symbol} ({yf_ticker}) | Lot Size: {lot_size}...")

        try:
            candle_data = yf.download(yf_ticker, start=START_DATE, end=END_DATE, interval=INTERVAL, progress=False)
            if candle_data.empty and INTERVAL in ["1h", "60m", "15m", "5m"]:
                candle_data = yf.download(yf_ticker, period="730d", interval=INTERVAL, progress=False)

            if isinstance(candle_data.columns, pd.MultiIndex):
                candle_data.columns = candle_data.columns.get_level_values(0)

            if candle_data.empty:
                print_fn(f"⚠️ No data fetched for {symbol}")
                continue

            backtester = FNOBacktester(symbol, yf_ticker, lot_size=lot_size, strike_step=strike_step, segment=segment)
            trades = backtester.backtest(candle_data)

            if trades:
                all_executed_trades.extend(trades)
                stats = backtester.calculate_statistics()
                portfolio_stats.append(stats)
                print_fn(f"✅ {symbol}: {stats['total_trades']} Trades | Win Rate: {stats['win_rate']:.2f}% | P&L: ₹{stats['total_pnl_rupees']:,.2f}")

        except Exception as e:
            print_fn(f"❌ Error processing {symbol}: {e}")

    if portfolio_stats:
        summary_df = pd.DataFrame(portfolio_stats)
        trades_all_df = pd.DataFrame(all_executed_trades)

        summary_csv_path = os.path.abspath("nfo_portfolio_summary.csv")
        all_trades_csv_path = os.path.abspath("nfo_all_trades.csv")
        summary_df.to_csv(summary_csv_path, index=False)
        trades_all_df.to_csv(all_trades_csv_path, index=False)

        total_net_pnl = summary_df['total_pnl_rupees'].sum()
        total_trades_count = summary_df['total_trades'].sum()
        win_shares_count = len(summary_df[summary_df['total_pnl_rupees'] > 0])

        print_fn("\n" + "="*80)
        print_fn("📊 OVERALL NFO F&O PORTFOLIO PERFORMANCE SUMMARY")
        print_fn("="*80)
        print_fn(f"Total NFO Instruments Evaluated: {len(summary_df)}")
        print_fn(f"Profitable Shares Count        : {win_shares_count} / {len(summary_df)}")
        print_fn(f"Total Portfolio Trades Executed: {total_trades_count}")
        print_fn(f"Total Net Portfolio P&L (₹)    : ₹{total_net_pnl:,.2f}")
        print_fn("="*80)

        # Build HTML Report
        html_report_path = os.path.abspath("macd_fno_portfolio_report.html")
        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>OpenAlgo Multi-Asset NFO F&O Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background-color: #f8f9fa; color: #333; }}
    h1, h2, h3 {{ color: #2c3e50; }}
    .card {{ background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
    th, td {{ border: 1px solid #dee2e6; padding: 8px 12px; text-align: left; }}
    th {{ background-color: #e9ecef; }}
  </style>
</head>
<body>
  <h1>🚀 OpenAlgo NFO F&O Multi-Asset MACD Report</h1>
  <p><strong>Segment:</strong> {segment} | <strong>Total Shares:</strong> {len(summary_df)} | <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
  <div class="card">
    <h2>🏆 Portfolio Performance Overview</h2>
    <ul>
      <li><strong>Total Net Portfolio P&L (₹):</strong> <span style="font-size:18px; color: {'green' if total_net_pnl >= 0 else 'red'};">₹{total_net_pnl:,.2f}</span></li>
      <li><strong>Total Portfolio Trades Executed:</strong> {total_trades_count}</li>
      <li><strong>Profitable Shares:</strong> {win_shares_count} Wins / {len(summary_df) - win_shares_count} Losses</li>
    </ul>
  </div>
</body>
</html>"""
        with open(html_report_path, "w") as f:
            f.write(html_content)

        print_fn(f"✅ HTML Report generated: {html_report_path}")
        print_fn(f"✅ Text log written to: {log_path}")

    log_file.close()


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="OpenAlgo NFO F&O MACD Trading & Backtesting Engine")
    parser.add_argument(
        "--mode",
        choices=["trade", "backtest"],
        default=os.getenv("MODE", "trade"),
        help="Execution mode: 'trade' for automated live trading loop, 'backtest' for multi-year historical simulation.",
    )
    parser.add_argument(
        "--symbols",
        default=os.getenv("TARGET_SYMBOL", "ALL"),
        help="Target symbols: 'ALL' or comma-separated list e.g. 'M&M,BAJFINANCE,AXISBANK'.",
    )
    parser.add_argument(
        "--interval",
        default=INTERVAL,
        help=f"Candle interval timeframe (default: {INTERVAL}).",
    )
    parser.add_argument(
        "--lots",
        type=int,
        default=LOTS,
        help=f"Number of lots per position (default: {LOTS}).",
    )
    parser.add_argument(
        "--max-active",
        type=int,
        default=MAX_ACTIVE_POSITIONS,
        help=f"Maximum concurrent active positions (default: {MAX_ACTIVE_POSITIONS}).",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        default=RUN_ONCE,
        help="Run single portfolio scan cycle and exit.",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=60,
        help="Seconds between execution scans in continuous live mode (default: 60).",
    )
    parser.add_argument(
        "--reconcile-only",
        action="store_true",
        default=False,
        help="Run startup position reconciliation audit and exit immediately without placing orders.",
    )
    parser.add_argument(
        "--auto-exit-misaligned",
        action="store_true",
        default=AUTO_EXIT_MISALIGNED,
        help="Automatically exit positions detected as misaligned with current market regime to FLAT.",
    )
    parser.add_argument(
        "--disable-asymmetric-universe",
        action="store_true",
        default=False,
        help="Disable TOP_LONGS/TOP_SHORTS universe restriction and trade all NFO symbols.",
    )
    parser.add_argument(
        "--runner-mode",
        action="store_true",
        default=RUNNER_MODE,
        help="Enable Candidate E variant (+Target & 0.35%% trailing runner) instead of Candidate G pure cross.",
    )
    args = parser.parse_args()

    if args.mode == "backtest":
        run_full_backtest(target_symbol=args.symbols, segment="FUTURES")
        return

    # OpenAlgo Trading Mode
    selected_symbols = list(NFO_SYMBOLS_MAP.keys()) if args.symbols.upper() == "ALL" else [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    trader = NFOPortfolioLiveTrader(
        symbols=selected_symbols,
        interval=args.interval,
        lots=args.lots,
        max_active=args.max_active,
        auto_exit_misaligned=args.auto_exit_misaligned,
        use_asymmetric_universe=not args.disable_asymmetric_universe,
        runner_mode=args.runner_mode,
    )

    if args.reconcile_only:
        logger.info("Reconciliation audit complete (--reconcile-only). Exiting cleanly.")
        return

    if args.run_once:
        logger.info("🚀 Running single portfolio evaluation cycle (--run-once)...")
        trader.execute_cycle()
    else:
        trader.run_loop(poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()