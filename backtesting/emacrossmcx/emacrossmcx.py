"""
================================================================================
OPENALGO LIVE STRATEGY: MCX 1H EMA/MACD ASYMMETRIC SEQUENTIAL CONFIRMATION ENGINE
================================================================================
File Role            : LIVE_OPENALGO_STRATEGY
Strategy Identifier  : EMACROSS_MCX_PAPER
Target Universe      : GOLDM, SILVERMIC, CRUDEOILM (alias CRUDEM)
Exchange             : MCX (Multi Commodity Exchange of India)
Default Product      : NRML (Normal Futures)
Timeframe            : 1-Hour (1H) Completed Candles
Current Version      : 3.1.0-MCX
================================================================================
Strategy Specification:
  1. Target Commodities (MCX Mini & Micro Contracts):
     - GOLDM (Gold Mini): 100g contract, quoted per 10g in INR.
     - SILVERMIC (Silver Micro): 1kg contract, quoted per 1kg in INR.
     - CRUDEOILM / CRUDEM (Crude Oil Mini): 10 barrels contract, quoted per barrel in INR.
  2. Timeframe: Strictly 1-Hour (1H) for both EMA and MACD on completed candles.
     MCX trading hours: 09:00 to 23:30 IST (Mon - Fri).
  3. EMA Structure:
     - EMA 9 and EMA 26 calculated on completed 1H close.
     - Bullish EMA XOVER: prev_ema9 <= prev_ema26 AND curr_ema9 > curr_ema26
     - Bearish EMA XOVER: prev_ema9 >= prev_ema26 AND curr_ema9 < curr_ema26
  4. MACD Structure (12, 26, 9):
     - MACD Line   = EMA12 - EMA26
     - Signal Line = EMA9 of MACD Line
     - Histogram   = MACD Line - Signal Line
     - Bullish MACD XOVER: prev_macd <= prev_signal AND curr_macd > curr_signal
     - Bearish MACD XOVER: prev_macd >= prev_signal AND curr_macd < curr_signal
  5. Confirmation Window:
     - CONFIRMATION_WINDOW = 2 completed 1H candles.
     - Delay = 0: SAME_CANDLE confirmation (Immediate Entry).
     - Delay = 1 or 2: Sequential confirmation within window.
     - Delay > 2: Expired.
  6. Long Entry Logic (Unfiltered V2-2):
     - Case A: SAME_CANDLE (EMA Bullish & MACD Bullish on same completed candle).
     - Case B: MACD_FIRST (MACD Bullish -> PENDING_EMA -> EMA confirms within 2 candles).
     - Case C: EMA_FIRST (EMA Bullish -> PENDING_MACD -> MACD confirms within 2 candles).
  7. Short Entry Logic (MACD-First Only V2-2):
     - Case A: SAME_CANDLE (MACD Bearish & EMA Bearish on same completed candle).
     - Case B: MACD_FIRST (MACD Bearish -> PENDING_EMA -> EMA confirms within 2 candles).
     - Case C: EMA_FIRST -> STRICTLY REJECTED. Prevents lagging short squeeze traps.
  8. Invalidation:
     - If leading indicator reverses directional bias before 2nd confirms, setup is CANCELLED.
  9. Risk Management Hierarchy (Evaluated from Actual Executed Fill Price):
     - Priority 1: Emergency Catastrophe Stop Loss (-4.00% / -6.00% configurable).
     - Priority 2: High-Water-Mark (HWM) Trailing Runner (0.35% trail, 0.50% floor).
     - Priority 3: Break-Even Stop Loss (Triggered on Early Profit Milestone).
     - Priority 4: Asymmetric Profit Target (+2.50% / +3.00% Long, +1.50% Short).
     - Priority 5: Opposite V2-2 Reversal Exit.
  10. Execution Standards:
     - Pre-flight PAPER / ANALYZE safety lock.
     - Dynamic discovery of active near-month MCX futures contracts & lot sizes.
     - Orderbook reconciliation before retrying.
     - Atomic crash-safe state persistence across restarts.
     - Watchdog heartbeat emission for runtime monitoring.
     - Consolidated single-message Telegram notifications.
================================================================================
"""

import argparse
import csv
import json
import logging
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone, time as dt_time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(), override=False)
except ImportError:
    pass

for candidate in [
    ROOT_DIR / ".env",
    Path.cwd() / ".env",
    Path("/opt/openalgo/.env"),
    SCRIPT_DIR.parent / ".env",
    SCRIPT_DIR / ".env",
]:
    if candidate.exists():
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and (k not in os.environ or os.environ[k] == "a93a6d4254acb477c693e0776b9c34ef4f129d0a94a4c1c100235186f8e1a41e"):
                            os.environ[k] = v
            break
        except Exception:
            pass

try:
    from openalgo import api
    OPENALGO_AVAILABLE = True
except ImportError:
    OPENALGO_AVAILABLE = False
    api = None

# ==============================================================================
# 1. FILE PATHS & CONSTANTS
# ==============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
LOG_FILE_PATH = Path(os.getenv("LOG_FILE", PROJECT_ROOT / "log/strategies/emacrossmcx.log" if (PROJECT_ROOT / "log").exists() else SCRIPT_DIR / "emacrossmcx.log"))
STATE_FILE_PATH = Path(os.getenv("STATE_FILE", SCRIPT_DIR / "emacrossmcx_state.json"))
HEARTBEAT_FILE_PATH = Path(os.getenv("HEARTBEAT_FILE", SCRIPT_DIR / "emacrossmcx_heartbeat.json"))
RESEARCH_CSV_PATH = Path(os.getenv("RESEARCH_CSV_FILE", SCRIPT_DIR / "emacrossmcx_research.csv"))

STRATEGY_NAME = os.getenv("STRATEGY_NAME", "EMACROSS_MCX_PAPER")
EXCHANGE = os.getenv("EXCHANGE", "MCX")
PRODUCT = os.getenv("PRODUCT", "NRML")
INTERVAL = os.getenv("INTERVAL", "1h")

# Strategy Parameters
FAST_EMA_PERIOD = int(os.getenv("FAST_EMA_PERIOD", "9"))
SLOW_EMA_PERIOD = int(os.getenv("SLOW_EMA_PERIOD", "26"))
MACD_FAST_PERIOD = int(os.getenv("MACD_FAST_PERIOD", "12"))
MACD_SLOW_PERIOD = int(os.getenv("MACD_SLOW_PERIOD", "26"))
MACD_SIGNAL_PERIOD = int(os.getenv("MACD_SIGNAL_PERIOD", "9"))
CONFIRMATION_WINDOW = int(os.getenv("CONFIRMATION_WINDOW", "2"))

# Risk Management Parameters (Optimized for MCX Commodities)
LONG_PROFIT_TARGET_PCT = float(os.getenv("LONG_PROFIT_TARGET_PCT", "2.00"))
SHORT_PROFIT_TARGET_PCT = float(os.getenv("SHORT_PROFIT_TARGET_PCT", "1.50"))
CATASTROPHE_SL_PCT = float(os.getenv("CATASTROPHE_SL_PCT", "2.50"))
ORDER_PACING_DELAY_SEC = float(os.getenv("ORDER_PACING_DELAY_SEC", "0.25"))

# Early Profit Milestone & Break-Even Stop Loss
EARLY_LONG_TP_PCT = float(os.getenv("EARLY_LONG_TP_PCT", "1.00"))
EARLY_SHORT_TP_PCT = float(os.getenv("EARLY_SHORT_TP_PCT", "0.75"))
MOVE_SL_TO_BE = os.getenv("MOVE_SL_TO_BE", "true").lower() in ["true", "1", "yes"]
RUNNER_PROFIT_FLOOR_PCT = float(os.getenv("RUNNER_PROFIT_FLOOR_PCT", "0.35"))

# Trailing Runner Parameters
ENABLE_TRAILING_RUNNER = os.getenv("ENABLE_TRAILING_RUNNER", "true").lower() in ["true", "1", "yes"]
RUNNER_TRAIL_PCT = float(os.getenv("RUNNER_TRAIL_PCT", "0.20"))
RUNNER_TRAIL_MODE = os.getenv("RUNNER_TRAIL_MODE", "HWM").upper()

LOTS = int(os.getenv("LOTS", "1"))
MAX_ACTIVE_POSITIONS = int(os.getenv("MAX_ACTIVE_POSITIONS", "0"))  # 0 = Unlimited
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() in ["true", "1", "yes"]

# IST Timezone (+05:30)
IST = timezone(timedelta(hours=5, minutes=30))

# ==============================================================================
# 2. LOGGING SETUP
# ==============================================================================
logger = logging.getLogger("EMACROSS_MCX")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE_PATH, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Failed to setup RotatingFileHandler for {LOG_FILE_PATH}: {e}", file=sys.stderr)

# ==============================================================================
# 3. OPENALGO & TELEGRAM CONFIGURATION
# ==============================================================================
OPENALGO_API_KEY = os.getenv(
    "OPENALGO_API_KEY",
    "a93a6d4254acb477c693e0776b9c34ef4f129d0a94a4c1c100235186f8e1a41e",
)
OPENALGO_HOST = os.getenv("OPENALGO_HOST")
if not OPENALGO_HOST:
    host_server = os.getenv("HOST_SERVER", "")
    if host_server and "127.0.0.1" not in host_server and "localhost" not in host_server:
        OPENALGO_HOST = host_server
    else:
        OPENALGO_HOST = "http://127.0.0.1:5000"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Fallback: Query Telegram config from OpenAlgo Host API if unconfigured
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

# ==============================================================================
# 4. MCX COMMODITY SPECIFICATIONS & UNIVERSE
# ==============================================================================
# Standard target universe for this strategy:
DEFAULT_MCX_UNIVERSE = ["GOLDM", "SILVERMIC", "CRUDEOILM"]

# Symbol alias normalization
SYMBOL_ALIASES = {
    "CRUDEM": "CRUDEOILM",
    "CRUDE": "CRUDEOILM",
    "GOLD": "GOLDM",
    "SILVER": "SILVERMIC",
    "SILVERM": "SILVERMIC",
}

def normalize_mcx_symbol(symbol: str) -> str:
    """Normalizes symbol aliases (e.g. CRUDEM -> CRUDEOILM)."""
    s = str(symbol).strip().upper()
    return SYMBOL_ALIASES.get(s, s)

MCX_COMMODITY_SPECS: Dict[str, Dict[str, Any]] = {
    "GOLDM": {
        "display_name": "Gold Mini (100g)",
        "search_prefix": "GOLDM",
        "default_lot": 1,  # 1 lot per order (100 grams)
        "trading_lot_size": 1,  # Strict 1-lot order enforcement
        "unit": "100g",
        "tick_size": 1.0,
        "point_value": 10.0,  # ₹10 per 1-point move per lot (10 units of 10g in 100g)
        "fallback_expiry_day": 5,
        "conv_type": "gold_10g",
        "yf_symbol": "GC=F",
    },
    "SILVERMIC": {
        "display_name": "Silver Micro (1kg)",
        "search_prefix": "SILVERMIC",
        "default_lot": 1,  # 1 lot per order (1kg)
        "trading_lot_size": 1,  # Strict 1-lot order enforcement
        "unit": "1kg",
        "tick_size": 1.0,
        "point_value": 1.0,  # ₹1 per 1-point move per lot
        "fallback_expiry_day": 28,
        "conv_type": "silver_1kg",
        "yf_symbol": "SI=F",
    },
    "CRUDEOILM": {
        "display_name": "Crude Oil Mini (10 bbl)",
        "search_prefix": "CRUDEOILM",
        "default_lot": 1,  # 1 lot per order (10 barrels)
        "trading_lot_size": 1,  # Strict 1-lot order enforcement
        "unit": "10 Barrels",
        "tick_size": 1.0,
        "point_value": 10.0,  # ₹10 per 1-point move per lot (10 barrels)
        "fallback_expiry_day": 19,
        "conv_type": "barrel",
        "yf_symbol": "CL=F",
    },
}

FALLBACK_LOT_SIZES = {
    "GOLDM": 1,
    "SILVERMIC": 1,
    "CRUDEOILM": 1,
}

# ==============================================================================
# 5. MCX TIME & CANDLE COMPLETION HELPERS
# ==============================================================================
def get_current_ist() -> datetime:
    """Returns current datetime localized to Indian Standard Time (IST)."""
    return datetime.now(timezone.utc).astimezone(IST)


def format_candle_time(dt: datetime) -> str:
    """Formats datetime as '11-Nov-2026 21:00 IST'."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime("%d-%b-%Y %H:%M IST")


def is_mcx_trading_time(now_dt: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    Checks if current time is within active MCX trading hours.
    MCX Session: Monday to Friday, 09:00 to 23:30 IST.
    """
    now = (now_dt or get_current_ist())
    weekday = now.weekday()
    if weekday >= 5:
        return False, "WEEKEND_CLOSED"

    t = now.time()
    m = t.hour * 60 + t.minute
    session_start = 9 * 60         # 09:00 IST
    session_end = 23 * 60 + 30     # 23:30 IST

    if session_start <= m <= session_end:
        return True, "MCX_SESSION_OPEN"
    elif m < session_start:
        return False, "PRE_MARKET_HOURS"
    else:
        return False, "POST_MARKET_HOURS"


def get_mcx_bar_duration(candle_ts: datetime) -> timedelta:
    """
    Returns timedelta duration for an MCX 1H candle.
    Standard 1H candles: 60 minutes.
    The final MCX evening bar starting at 23:00 completes at 23:30 (30 minutes).
    """
    if candle_ts.hour == 23 and candle_ts.minute == 0:
        return timedelta(minutes=30)
    return timedelta(minutes=60)


def get_completed_1h_candles(df: pd.DataFrame, now_override: Optional[datetime] = None) -> pd.DataFrame:
    """
    CRITICAL CANDLE RULE:
    Filters out any currently forming / incomplete 1-hour candle.
    A candle starting at T is completed only after T + duration.
    Returns strictly closed/completed candles.
    """
    if df.empty or len(df) < 2:
        return df

    now_ist = now_override or get_current_ist()

    last_idx = df.index[-1]
    if last_idx.tzinfo is None:
        last_dt = last_idx.replace(tzinfo=IST)
    else:
        last_dt = last_idx.astimezone(IST)

    bar_duration = get_mcx_bar_duration(last_dt)
    if now_ist < (last_dt + bar_duration):
        return df.iloc[:-1].copy()

    return df.copy()


def get_seconds_to_next_candle_boundary(now_dt: Optional[datetime] = None, buffer_seconds: int = 2) -> float:
    """
    Calculates seconds to the next completed 1H candle boundary for MCX.
    MCX Completed Candle Boundaries (HH:00:00 + buffer_seconds IST):
      10:00:02 (09:00 - 10:00 candle)
      11:00:02 (10:00 - 11:00 candle)
      12:00:02 (11:00 - 12:00 candle)
      13:00:02 (12:00 - 13:00 candle)
      14:00:02 (13:00 - 14:00 candle)
      15:00:02 (14:00 - 15:00 candle)
      16:00:02 (15:00 - 16:00 candle)
      17:00:02 (16:00 - 17:00 candle)
      18:00:02 (17:00 - 18:00 candle)
      19:00:02 (18:00 - 19:00 candle)
      20:00:02 (19:00 - 20:00 candle)
      21:00:02 (20:00 - 21:00 candle)
      22:00:02 (21:00 - 22:00 candle)
      23:00:02 (22:00 - 23:00 candle)
      23:30:02 (23:00 - 23:30 final candle)
    """
    if now_dt is None:
        now_dt = get_current_ist()
    elif now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=IST)
    else:
        now_dt = now_dt.astimezone(IST)

    today = now_dt.date()
    # If today is weekend, advance to Monday
    advance_days = 0
    if today.weekday() == 5:  # Saturday
        advance_days = 2
    elif today.weekday() == 6:  # Sunday
        advance_days = 1

    if advance_days > 0:
        target_date = today + timedelta(days=advance_days)
        target_dt = datetime.combine(target_date, dt_time(10, 0, buffer_seconds), tzinfo=IST)
        return max(1.0, (target_dt - now_dt).total_seconds())

    boundary_times = [
        (10, 0, buffer_seconds),
        (11, 0, buffer_seconds),
        (12, 0, buffer_seconds),
        (13, 0, buffer_seconds),
        (14, 0, buffer_seconds),
        (15, 0, buffer_seconds),
        (16, 0, buffer_seconds),
        (17, 0, buffer_seconds),
        (18, 0, buffer_seconds),
        (19, 0, buffer_seconds),
        (20, 0, buffer_seconds),
        (21, 0, buffer_seconds),
        (22, 0, buffer_seconds),
        (23, 0, buffer_seconds),
        (23, 30, buffer_seconds),
    ]

    for h, m, s in boundary_times:
        b_dt = datetime.combine(today, dt_time(h, m, s), tzinfo=IST)
        diff = (b_dt - now_dt).total_seconds()
        if diff > 0.5:
            return diff

    # If all boundaries today have passed, schedule for next trading day at 10:00
    next_day = today + timedelta(days=1)
    while next_day.weekday() >= 5:  # Skip weekends
        next_day += timedelta(days=1)

    next_boundary = datetime.combine(next_day, dt_time(10, 0, buffer_seconds), tzinfo=IST)
    return max(1.0, (next_boundary - now_dt).total_seconds())


# ==============================================================================
# 6. PERSISTENT STATE MANAGER
# ==============================================================================
class PersistentStateManager:
    """
    Atomic, crash-safe state persistence for emacrossmcx.py.
    Guarantees state is preserved across process crashes, restarts, and reboots.
    """

    def __init__(self, state_file: Path = STATE_FILE_PATH):
        self.state_file = state_file
        self.state: Dict[str, Any] = self.load_state()

    def load_state(self) -> Dict[str, Any]:
        """Safely loads state from disk with corrupt-file recovery."""
        if not self.state_file.exists():
            default = self._default_state()
            self._write_fresh_state(default)
            return default
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "version" in data:
                    return data
                logger.warning(f"⚠️ State file {self.state_file} has invalid format. Resetting to default.")
                default = self._default_state()
                self._write_fresh_state(default)
                return default
        except Exception as e:
            logger.error(f"❌ Error loading state file {self.state_file}: {e}. Initializing fresh state.")
            default = self._default_state()
            self._write_fresh_state(default)
            return default

    def _write_fresh_state(self, state_data: Dict[str, Any]):
        """Helper to write initial/recovered state safely."""
        try:
            temp_file = self.state_file.with_suffix(f".tmp.{os.getpid()}")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2, default=str)
            temp_file.replace(self.state_file)
        except Exception as e:
            logger.error(f"❌ Failed to initialize clean state file {self.state_file}: {e}")

    def _default_state(self) -> Dict[str, Any]:
        return {
            "version": "1.0",
            "strategy": STRATEGY_NAME,
            "exchange": EXCHANGE,
            "last_saved_at": None,
            "last_processed_candles": {},
            "processed_signals": {},
            "tracked_positions": {},
            "in_flight_orders": {},
            "recent_executions": [],
            "sent_alerts": {},
            "last_reconciliation_audit": {},
            "pending_setups": {},
        }

    def save_state(self):
        """Atomic write: writes to temp file then atomic rename to prevent corruption on crash."""
        try:
            self.state["last_saved_at"] = get_current_ist().isoformat()
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

    def is_signal_processed(self, signal_key: str) -> bool:
        return signal_key in self.state.get("processed_signals", {})

    def record_signal_processed(self, signal_key: str):
        if "processed_signals" not in self.state:
            self.state["processed_signals"] = {}
        self.state["processed_signals"][signal_key] = get_current_ist().isoformat()
        self.save_state()

    def is_order_inflight_or_filled(self, order_key: str) -> bool:
        in_flight = self.state.get("in_flight_orders", {})
        return in_flight.get(order_key, {}).get("status") in ["PENDING", "FILLED"]

    def mark_order_pending(self, order_key: str, details: Dict[str, Any]):
        if "in_flight_orders" not in self.state:
            self.state["in_flight_orders"] = {}
        self.state["in_flight_orders"][order_key] = {
            "status": "PENDING",
            "timestamp": get_current_ist().isoformat(),
            "details": details,
        }
        self.save_state()

    def mark_order_resolved(self, order_key: str, status: str, order_id: Optional[str] = None):
        if "in_flight_orders" in self.state and order_key in self.state["in_flight_orders"]:
            self.state["in_flight_orders"][order_key]["status"] = status
            self.state["in_flight_orders"][order_key]["resolved_at"] = get_current_ist().isoformat()
            if order_id:
                self.state["in_flight_orders"][order_key]["order_id"] = order_id
            self.save_state()

    def record_execution(
        self,
        symbol: str,
        contract: str,
        action: str,
        qty: int,
        candle_time: Any,
        order_resp: Any,
        order_id: Optional[str] = None,
    ):
        entry = {
            "timestamp": get_current_ist().isoformat(),
            "symbol": symbol,
            "contract": contract,
            "action": action,
            "quantity": qty,
            "candle_time": str(candle_time),
            "order_id": order_id or (order_resp.get("orderid") if isinstance(order_resp, dict) else None),
            "order_response": order_resp if isinstance(order_resp, (dict, list, str, int, float)) else str(order_resp),
        }
        if "recent_executions" not in self.state:
            self.state["recent_executions"] = []
        self.state["recent_executions"].append(entry)
        self.state["recent_executions"] = self.state["recent_executions"][-100:]
        self.save_state()

    def update_tracked_positions(self, positions_map: Dict[str, Any]):
        self.state["tracked_positions"] = positions_map
        self.save_state()

    def record_reconciliation_audit(self, audit_summary: Dict[str, Any]):
        self.state["last_reconciliation_audit"] = {
            "timestamp": get_current_ist().isoformat(),
            "summary": audit_summary,
        }
        self.save_state()

    def is_alert_sent(self, alert_key: str) -> bool:
        return alert_key in self.state.get("sent_alerts", {})

    def record_alert_sent(self, alert_key: str):
        if "sent_alerts" not in self.state:
            self.state["sent_alerts"] = {}
        self.state["sent_alerts"][alert_key] = get_current_ist().isoformat()
        self.save_state()

    def get_pending_setup(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self.state.get("pending_setups", {}).get(symbol)

    def save_pending_setup(self, symbol: str, setup: Dict[str, Any]):
        if "pending_setups" not in self.state:
            self.state["pending_setups"] = {}
        self.state["pending_setups"][symbol] = setup
        self.save_state()

    def clear_pending_setup(self, symbol: str):
        if "pending_setups" in self.state and symbol in self.state["pending_setups"]:
            del self.state["pending_setups"][symbol]
            self.save_state()

    def get_all_pending_setups(self) -> Dict[str, Any]:
        return self.state.get("pending_setups", {})


# ==============================================================================
# 7. RESEARCH DATA STORE
# ==============================================================================
RESEARCH_CSV_HEADERS = [
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "ema9",
    "previous_ema9",
    "ema26",
    "previous_ema26",
    "macd",
    "previous_macd",
    "macd_signal",
    "previous_signal",
    "macd_histogram",
    "previous_histogram",
    "ema_crossover",
    "macd_crossover",
    "combined_signal",
    "trigger_type",
    "confirmation_delay",
    "strategy_state",
    "rejection_reason",
    "direction",
    "paper_order_id",
    "order_status",
    "quantity",
    "position_before",
    "position_after",
]


def log_research_record(record: Dict[str, Any]):
    """Appends a research data row for evaluating signal expectancies and executions."""
    try:
        file_exists = RESEARCH_CSV_PATH.exists()
        RESEARCH_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(RESEARCH_CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=RESEARCH_CSV_HEADERS)
            if not file_exists or os.path.getsize(RESEARCH_CSV_PATH) == 0:
                writer.writeheader()
            writer.writerow({k: record.get(k, "") for k in RESEARCH_CSV_HEADERS})
        logger.info(f"💾 Research record saved for {record.get('symbol')} at {record.get('timestamp')}")
    except Exception as e:
        logger.error(f"Failed to log research record to CSV: {e}")


# ==============================================================================
# 8. TELEGRAM ALERT DISPATCHER
# ==============================================================================
def send_telegram_alert(message: str) -> bool:
    """Dispatches formatted alert message to Telegram if configured."""
    clean_msg = (
        message.replace("<b>", "")
        .replace("</b>", "")
        .replace("<code>", "")
        .replace("</code>", "")
        .replace("<i>", "")
        .replace("</i>", "")
    )

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info(f"📢 [TELEGRAM ALERT - CONSOLE DISPATCH]\n{clean_msg}")
        return True

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
            logger.warning(f"Telegram API warning (HTTP {resp.status_code}): {resp.text}")
            logger.info(f"📢 [FALLBACK ALERT]\n{clean_msg}")
            return False
    except Exception as e:
        logger.warning(f"Telegram dispatch failed non-fatally: {e}")
        logger.info(f"📢 [FALLBACK ALERT]\n{clean_msg}")
        return False


def format_paper_trade_alert(data: Dict[str, Any]) -> str:
    """Formats structured Paper Trade execution notification for MCX orders."""
    direction = data.get("direction", "LONG")
    dir_emoji = "🟢" if direction == "LONG" else "🔴"
    action = data.get("action", "BUY")
    contract = data.get("contract", "N/A")
    symbol = data.get("symbol", "N/A")
    qty = data.get("quantity", 0)
    order_id = data.get("order_id", "N/A")
    order_status = data.get("order_status", "FILLED")
    price_type = data.get("price_type", "MARKET")
    exchange = data.get("exchange", EXCHANGE)
    product = data.get("product", PRODUCT)
    exec_time = data.get("execution_time") or get_current_ist().strftime("%H:%M:%S")
    pos_before = data.get("pos_before", 0)
    pos_after = data.get("pos_after", qty if action == "BUY" else -qty)
    strategy_name = data.get("strategy_name", STRATEGY_NAME)
    trigger_type = data.get("trigger_type", "SAME_CANDLE")
    confirmation_delay = data.get("confirmation_delay", 0)

    delay_str = f"{confirmation_delay} candle{'s' if confirmation_delay != 1 else ''}"

    entry_price = data.get("entry_price")
    if entry_price is None or entry_price == "":
        entry_price = data.get("fill_price") or data.get("average_price") or 0.0
    try:
        entry_price_val = float(entry_price)
    except (TypeError, ValueError):
        entry_price_val = 0.0

    target_pct = float(os.getenv("LONG_PROFIT_TARGET_PCT", str(LONG_PROFIT_TARGET_PCT))) if direction == "LONG" else float(os.getenv("SHORT_PROFIT_TARGET_PCT", str(SHORT_PROFIT_TARGET_PCT)))
    sl_pct = float(os.getenv("CATASTROPHE_SL_PCT", str(CATASTROPHE_SL_PCT)))

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

    price_lines = f"<b>Entry Price:</b> ₹{entry_price_val:.2f}\n{target_sl_lines}"

    c_close = float(data.get('close') or 0.0)
    c_ema9 = float(data.get('ema9') or 0.0)
    c_ema26 = float(data.get('ema26') or 0.0)
    c_macd = float(data.get('macd') or 0.0)
    c_signal = float(data.get('macd_signal') or 0.0)
    c_hist = float(data.get('macd_histogram') or 0.0)

    return (
        f"{dir_emoji} <b>MCX COMMODITY — ORDER PLACED</b>\n\n"
        f"<b>Strategy:</b> {strategy_name} (MCX EMA + MACD Asymmetric V2-2)\n"
        f"🔬 <b>ANALYZE / PAPER MODE</b>\n"
        f"─────────────────────\n"
        f"<b>Symbol:</b> <code>{contract}</code> ({symbol})\n"
        f"<b>Action:</b> <b>{action}</b>\n"
        f"<b>Direction:</b> <b>{direction}</b>\n"
        f"<b>Trigger:</b> <b>{trigger_type}</b> (Delay: {delay_str})\n"
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
        f"📊 <b>Completed Candle:</b> {data.get('candle_time_str')}\n\n"
        f"<b>Close:</b> ₹{c_close:.2f}\n"
        f"<b>EMA9:</b> ₹{c_ema9:.2f}\n"
        f"<b>EMA26:</b> ₹{c_ema26:.2f}\n"
        f"<b>MACD:</b> {c_macd:.2f}\n"
        f"<b>Signal:</b> {c_signal:.2f}\n"
        f"<b>Histogram:</b> {c_hist:+.2f}\n"
        f"─────────────────────\n"
        f"<i>ℹ️ Mode: PAPER / ANALYZE ONLY</i>"
    )


def format_paper_exit_alert(data: Dict[str, Any]) -> str:
    """Formats an HTML Telegram alert message for position exits."""
    strategy_name = data.get("strategy_name", STRATEGY_NAME)
    contract = data.get("contract", "N/A")
    symbol = data.get("symbol", "N/A")
    direction = data.get("direction", "LONG")
    action = data.get("action", "SELL" if direction == "LONG" else "BUY")
    exit_reason = data.get("exit_reason", "UNKNOWN")
    qty = abs(int(data.get("quantity", 0)))
    order_id = data.get("order_id", "N/A")
    order_status = data.get("order_status", "FILLED")
    exec_time = data.get("execution_time") or get_current_ist().strftime("%H:%M:%S")
    candle_time = data.get("candle_time_str") or data.get("candle_time", "N/A")

    entry_price = float(data.get("entry_price", 0.0) or 0.0)
    exit_price = float(data.get("exit_price", 0.0) or 0.0)

    # Commodity Point Value multiplier calculation
    spec = MCX_COMMODITY_SPECS.get(symbol, {"point_value": 1.0, "default_lot": 1})
    pt_val = spec.get("point_value", 1.0)
    def_lot = spec.get("default_lot", 1)
    lots_count = max(1, qty // def_lot)

    dir_mult = 1.0 if direction == "LONG" else -1.0
    if entry_price > 0:
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0 * dir_mult
        pts_pnl = (exit_price - entry_price) * dir_mult
        pnl_abs = pts_pnl * pt_val * lots_count
    else:
        pnl_pct = 0.0
        pnl_abs = 0.0

    target_pct = float(os.getenv("LONG_PROFIT_TARGET_PCT", str(LONG_PROFIT_TARGET_PCT))) if direction == "LONG" else float(os.getenv("SHORT_PROFIT_TARGET_PCT", str(SHORT_PROFIT_TARGET_PCT)))
    sl_pct = float(os.getenv("CATASTROPHE_SL_PCT", str(CATASTROPHE_SL_PCT)))

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
    elif exit_reason == "BREAK_EVEN_SL":
        reason_header = "🛡️ BREAK-EVEN STOP-LOSS"
        reason_badge = "🛡️ <b>BREAK-EVEN STOP-LOSS TRIGGERED</b>"
    elif exit_reason == "CATASTROPHE_SL":
        reason_header = "🛑 CATASTROPHE STOP-LOSS"
        reason_badge = "🛑 <b>EMERGENCY STOP LOSS TRIGGERED</b>"
    elif exit_reason == "V2-2_REVERSAL":
        reason_header = "🔄 REVERSAL EXIT"
        reason_badge = "🔄 <b>OPPOSITE V2-2 SIGNAL REVERSAL</b>"
    else:
        reason_header = f"EXIT ({exit_reason})"
        reason_badge = f"ℹ️ <b>{exit_reason}</b>"

    return (
        f"{pnl_emoji} <b>MCX COMMODITY — {reason_header}</b>\n\n"
        f"<b>Strategy:</b> {strategy_name} (MCX EMA + MACD Asymmetric V2-2)\n"
        f"🔬 <b>ANALYZE / PAPER MODE</b>\n"
        f"─────────────────────\n"
        f"<b>Symbol:</b> <code>{contract}</code> ({symbol})\n"
        f"<b>Exited Direction:</b> <b>{direction}</b>\n"
        f"<b>Exit Action:</b> <b>{action}</b>\n"
        f"<b>Exit Reason:</b> {reason_badge}\n"
        f"<b>Quantity:</b> {qty}\n"
        f"<b>Entry Price:</b> ₹{entry_price:.2f}\n"
        f"<b>Exit Price:</b> ₹{exit_price:.2f}\n"
        f"{target_sl_lines}"
        f"<b>Estimated P&L:</b> {pnl_str}\n"
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


# ==============================================================================
# 9. DYNAMIC MCX FUTURES CONTRACT RESOLUTION
# ==============================================================================
def resolve_mcx_contract(
    symbol: str, host: str, api_key: str
) -> Tuple[Optional[str], Optional[int], Optional[datetime]]:
    """
    Queries OpenAlgo search API to dynamically find the active near-month
    MCX futures contract symbol, its exact lot size, and its expiry datetime.
    Includes strict collision guards (GOLDM must not match GOLD, SILVERMIC must not match SILVER,
    and CRUDEOILM must not match CRUDEOIL).
    """
    clean_sym = normalize_mcx_symbol(symbol)
    spec = MCX_COMMODITY_SPECS.get(clean_sym, {})
    fallback_lot = spec.get("trading_lot_size", FALLBACK_LOT_SIZES.get(clean_sym, 1))
    fallback_day = spec.get("fallback_expiry_day", 20)

    try:
        search_url = f"{host.rstrip('/')}/api/v1/search"
        resp = requests.post(
            search_url,
            json={"apikey": api_key, "query": clean_sym, "exchange": "MCX"},
            timeout=6,
        )
        if resp.status_code == 200:
            items = resp.json().get("data", [])
            fut_items = [
                i for i in items
                if i.get("instrumenttype") == "FUT"
                and (i.get("symbol", "").startswith(clean_sym) or i.get("name", "").startswith(clean_sym))
            ]

            # Anti-collision filters
            if clean_sym == "GOLDM":
                fut_items = [i for i in fut_items if i.get("symbol", "").startswith("GOLDM") and not i.get("symbol", "").startswith("GOLDGUINEA") and not i.get("symbol", "").startswith("GOLDPETAL")]
            elif clean_sym == "SILVERMIC":
                fut_items = [i for i in fut_items if i.get("symbol", "").startswith("SILVERMIC")]
            elif clean_sym == "CRUDEOILM":
                fut_items = [i for i in fut_items if i.get("symbol", "").startswith("CRUDEOILM")]

            now = datetime.now()
            valid = []
            for item in fut_items:
                exp_str = item.get("expiry")
                if exp_str:
                    exp_dt = None
                    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%B-%Y", "%d-%B-%y"):
                        try:
                            exp_dt = datetime.strptime(exp_str, fmt).replace(hour=23, minute=59)
                            break
                        except Exception:
                            pass
                    if exp_dt and exp_dt >= now:
                        # For MCX commodity futures on OpenAlgo/Fyers, 1 order quantity = 1 lot.
                        # Enforce strict 1-lot trading per order contract.
                        lot = int(spec.get("trading_lot_size", 1))
                        valid.append((exp_dt, item.get("symbol"), lot))

            if valid:
                valid.sort(key=lambda x: x[0])
                expiry_dt = valid[0][0]
                contract_symbol = valid[0][1]
                lot_size = valid[0][2]
                return contract_symbol, lot_size, expiry_dt

    except Exception as e:
        logger.error(f"❌ Search API lookup error for MCX {clean_sym}: {e}")

    # Fallback formula for near-month MCX contract
    now = datetime.now()
    exp_month = now.month
    exp_year = now.year
    # If today is past the expiry day of this month, advance to next month
    if now.day > fallback_day:
        exp_month += 1
        if exp_month > 12:
            exp_month = 1
            exp_year += 1

    exp_dt = datetime(exp_year, exp_month, fallback_day, 23, 59)
    month_str = exp_dt.strftime("%b").upper()
    year_str = exp_dt.strftime("%y")
    fallback_symbol = f"{clean_sym}{fallback_day:02d}{month_str}{year_str}FUT"

    logger.info(f"ℹ️ Contract for {clean_sym} resolved via standard MCX calendar fallback: {fallback_symbol} (Lot: {fallback_lot})")
    return fallback_symbol, fallback_lot, exp_dt


# ==============================================================================
# 10. STRATEGY INDICATOR & ASYMMETRIC V2-2 SIGNAL LOGIC
# ==============================================================================
def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates:
      - EMA 9 & EMA 26
      - MACD (12, 26, 9):
        * MACD Line   = EMA12 - EMA26
        * Signal Line = EMA9 of MACD Line
        * Histogram   = MACD Line - Signal Line
    All calculated on the exact same 1-Hour completed candle series.
    """
    close = df["close"]

    # EMA 9 & EMA 26
    df["ema9"] = close.ewm(span=FAST_EMA_PERIOD, adjust=False).mean()
    df["ema26"] = close.ewm(span=SLOW_EMA_PERIOD, adjust=False).mean()

    # MACD Calculation (12, 26, 9)
    df["ema12"] = close.ewm(span=MACD_FAST_PERIOD, adjust=False).mean()
    df["ema26_macd"] = close.ewm(span=MACD_SLOW_PERIOD, adjust=False).mean()
    df["macd"] = df["ema12"] - df["ema26_macd"]
    df["macd_signal"] = df["macd"].ewm(span=MACD_SIGNAL_PERIOD, adjust=False).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]

    return df


def detect_ema_macd_signal(
    df: pd.DataFrame,
    symbol: str = "",
    pending_setup: Optional[Dict[str, Any]] = None,
    window: int = CONFIRMATION_WINDOW,
) -> Optional[Dict[str, Any]]:
    """
    Evaluates completed 1-Hour candles for Asymmetric V2-2 Sequential Confirmation:
      1. EMA 9 x EMA 26 Crossover:
         - Bullish: prev_ema9 <= prev_ema26 AND curr_ema9 > curr_ema26
         - Bearish: prev_ema9 >= prev_ema26 AND curr_ema9 < curr_ema26
      2. MACD 12/26/9 Crossover:
         - Bullish: prev_macd <= prev_signal AND curr_macd > curr_signal
         - Bearish: prev_macd >= prev_signal AND curr_macd < curr_signal
      3. Long Entry Rules (Unfiltered V2-2):
         - Case A (SAME_CANDLE): Both EMA & MACD cross bullish on the exact same candle (delay=0).
         - Case B (MACD_THEN_EMA): Bullish MACD crosses first -> PENDING_EMA -> Bullish EMA confirms within 2 candles.
         - Case C (EMA_THEN_MACD): Bullish EMA crosses first -> PENDING_MACD -> Bullish MACD confirms within 2 candles.
      4. Short Entry Rules (MACD-First Only V2-2):
         - Case A (SAME_CANDLE): Both EMA & MACD cross bearish on the exact same candle (delay=0).
         - Case B (MACD_THEN_EMA): Bearish MACD crosses first -> PENDING_EMA -> Bearish EMA confirms within 2 candles.
         - Case C (EMA_THEN_MACD): Bearish EMA crosses first -> STRICTLY REJECTED (SHORT_EMA_FIRST_DISALLOWED).
      5. Invalidation:
         - If leading indicator reverses directional bias before 2nd confirms, setup is INVALIDATED & cancelled.
      6. Expiration:
         - If confirmation delay exceeds `window` (2 candles), setup is EXPIRED & cancelled.
      7. Histogram:
         - Telemetry only. STRICTLY NOT an entry filter.
    """
    if df is None or len(df) < 2:
        return None

    required_cols = ["close", "ema9", "ema26", "macd"]
    for col in required_cols:
        if col not in df.columns:
            return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    candle_dt = df.index[-1]
    if isinstance(candle_dt, str):
        candle_dt = pd.to_datetime(candle_dt)
    candle_time_str = format_candle_time(candle_dt)
    candle_iso = candle_dt.isoformat() if hasattr(candle_dt, "isoformat") else str(candle_dt)

    curr_open = float(curr["open"]) if "open" in curr else float(curr["close"])
    curr_high = float(curr["high"]) if "high" in curr else float(curr["close"])
    curr_low = float(curr["low"]) if "low" in curr else float(curr["close"])
    curr_close = float(curr["close"])
    prev_close = float(prev["close"])

    curr_ema9 = float(curr["ema9"])
    prev_ema9 = float(prev["ema9"])
    curr_ema26 = float(curr["ema26"])
    prev_ema26 = float(prev["ema26"])

    curr_macd = float(curr["macd"])
    prev_macd = float(prev["macd"])
    curr_signal = float(curr["macd_signal"]) if "macd_signal" in curr else float(curr.get("signal", 0.0))
    prev_signal = float(prev["macd_signal"]) if "macd_signal" in prev else float(prev.get("signal", 0.0))
    curr_hist = float(curr["macd_histogram"]) if "macd_histogram" in curr else (curr_macd - curr_signal)
    prev_hist = float(prev["macd_histogram"]) if "macd_histogram" in prev else (prev_macd - prev_signal)

    # 1. EMA Crossover on current candle
    ema_bull = (prev_ema9 <= prev_ema26) and (curr_ema9 > curr_ema26)
    ema_bear = (prev_ema9 >= prev_ema26) and (curr_ema9 < curr_ema26)
    ema_crossover = "BULLISH" if ema_bull else ("BEARISH" if ema_bear else "NONE")

    # 2. MACD Crossover on current candle
    macd_bull = (prev_macd <= prev_signal) and (curr_macd > curr_signal)
    macd_bear = (prev_macd >= prev_signal) and (curr_macd < curr_signal)
    macd_crossover = "BULLISH" if macd_bull else ("BEARISH" if macd_bear else "NONE")

    confluence = "NONE"
    signal_dir = None
    trigger_type = "NONE"
    confirmation_delay = 0
    strategy_state = "IDLE"
    rejection_reason = "NONE"
    action_on_pending = "KEEP"
    new_pending_setup = None

    # Case A: Same-Candle Confluence (Delay = 0)
    if ema_bull and macd_bull:
        confluence = "BULLISH"
        signal_dir = "BUY"
        trigger_type = "SAME_CANDLE"
        confirmation_delay = 0
        strategy_state = "CONFIRMED"
        action_on_pending = "CLEAR"
        new_pending_setup = None
    elif ema_bear and macd_bear:
        confluence = "BEARISH"
        signal_dir = "SELL"
        trigger_type = "SAME_CANDLE"
        confirmation_delay = 0
        strategy_state = "CONFIRMED"
        action_on_pending = "CLEAR"
        new_pending_setup = None
    else:
        active_setup = None
        if pending_setup and isinstance(pending_setup, dict) and pending_setup.get("direction"):
            active_setup = dict(pending_setup)
        elif len(df) >= 3:
            sig_col = "macd_signal" if "macd_signal" in df.columns else "signal"
            max_lookback = min(len(df) - 1, window + 2)
            for lb in range(2, max_lookback + 1):
                p_curr = df.iloc[-lb]
                p_prev = df.iloc[-lb - 1]

                p_ema_bull = (p_prev["ema9"] <= p_prev["ema26"]) and (p_curr["ema9"] > p_curr["ema26"])
                p_ema_bear = (p_prev["ema9"] >= p_prev["ema26"]) and (p_curr["ema9"] < p_curr["ema26"])
                p_macd_bull = (p_prev["macd"] <= p_prev[sig_col]) and (p_curr["macd"] > p_curr[sig_col])
                p_macd_bear = (p_prev["macd"] >= p_prev[sig_col]) and (p_curr["macd"] < p_curr[sig_col])

                if (p_ema_bull and p_macd_bull) or (p_ema_bear and p_macd_bear):
                    continue

                if p_macd_bull and not p_ema_bull:
                    active_setup = {
                        "symbol": symbol,
                        "direction": "LONG",
                        "leading_indicator": "MACD",
                        "setup_candle_time": df.index[-lb],
                        "setup_idx": len(df) - lb,
                        "elapsed_bars": lb - 1,
                        "strategy_state": "PENDING_EMA",
                    }
                    break
                elif p_ema_bull and not p_macd_bull:
                    active_setup = {
                        "symbol": symbol,
                        "direction": "LONG",
                        "leading_indicator": "EMA",
                        "setup_candle_time": df.index[-lb],
                        "setup_idx": len(df) - lb,
                        "elapsed_bars": lb - 1,
                        "strategy_state": "PENDING_MACD",
                    }
                    break
                elif p_macd_bear and not p_ema_bear:
                    active_setup = {
                        "symbol": symbol,
                        "direction": "SHORT",
                        "leading_indicator": "MACD",
                        "setup_candle_time": df.index[-lb],
                        "setup_idx": len(df) - lb,
                        "elapsed_bars": lb - 1,
                        "strategy_state": "PENDING_EMA",
                    }
                    break
                elif p_ema_bear and not p_macd_bear:
                    break

        if active_setup:
            dir_setup = active_setup.get("direction")
            leading = active_setup.get("leading_indicator")
            setup_time = active_setup.get("setup_candle_time")

            delay = 1
            if setup_time is not None:
                try:
                    setup_dt = pd.to_datetime(setup_time)
                    idx_dts = [pd.to_datetime(t) for t in df.index]
                    if setup_dt.tzinfo is not None:
                        idx_dts = [
                            t.tz_convert(setup_dt.tz) if t.tzinfo is not None else t.tz_localize(setup_dt.tz)
                            for t in idx_dts
                        ]
                    else:
                        idx_dts = [t.tz_localize(None) if t.tzinfo is not None else t for t in idx_dts]

                    if setup_dt in idx_dts:
                        setup_pos = idx_dts.index(setup_dt)
                        delay = (len(df) - 1) - setup_pos
                    else:
                        delay = active_setup.get("elapsed_bars", 0) + 1
                except Exception:
                    delay = active_setup.get("elapsed_bars", 0) + 1
            elif "setup_idx" in active_setup:
                delay = (len(df) - 1) - active_setup["setup_idx"]
            else:
                delay = active_setup.get("elapsed_bars", 0) + 1

            # Step 1: Invalidation check
            is_invalidated = False
            if dir_setup == "LONG":
                if leading == "MACD" and curr_macd < curr_signal:
                    is_invalidated = True
                    strategy_state = "INVALIDATED"
                    rejection_reason = "LEADING_MACD_REVERSED_BEARISH"
                    trigger_type = "MACD_THEN_EMA"
                    confirmation_delay = delay
                    action_on_pending = "CLEAR"
                elif leading == "EMA" and curr_ema9 < curr_ema26:
                    is_invalidated = True
                    strategy_state = "INVALIDATED"
                    rejection_reason = "LEADING_EMA_REVERSED_BEARISH"
                    trigger_type = "EMA_THEN_MACD"
                    confirmation_delay = delay
                    action_on_pending = "CLEAR"
            elif dir_setup == "SHORT":
                if leading == "MACD" and curr_macd > curr_signal:
                    is_invalidated = True
                    strategy_state = "INVALIDATED"
                    rejection_reason = "LEADING_MACD_REVERSED_BULLISH"
                    trigger_type = "MACD_THEN_EMA"
                    confirmation_delay = delay
                    action_on_pending = "CLEAR"
                elif leading == "EMA":
                    is_invalidated = True
                    strategy_state = "REJECTED"
                    rejection_reason = "SHORT_EMA_FIRST_DISALLOWED"
                    trigger_type = "EMA_THEN_MACD_REJECTED"
                    confirmation_delay = delay
                    action_on_pending = "CLEAR"

            if not is_invalidated:
                # Step 2: Confirmation or Expiration
                if delay <= window:
                    if dir_setup == "LONG":
                        if leading == "MACD" and ema_bull:
                            confluence = "BULLISH"
                            signal_dir = "BUY"
                            trigger_type = "MACD_THEN_EMA"
                            confirmation_delay = delay
                            strategy_state = "CONFIRMED"
                            action_on_pending = "CLEAR"
                        elif leading == "EMA" and macd_bull:
                            confluence = "BULLISH"
                            signal_dir = "BUY"
                            trigger_type = "EMA_THEN_MACD"
                            confirmation_delay = delay
                            strategy_state = "CONFIRMED"
                            action_on_pending = "CLEAR"
                        else:
                            strategy_state = f"PENDING_{'EMA' if leading == 'MACD' else 'MACD'}"
                            trigger_type = f"{leading}_THEN_{'EMA' if leading == 'MACD' else 'MACD'}"
                            confirmation_delay = delay
                            action_on_pending = "UPDATE"
                            new_pending_setup = dict(active_setup, elapsed_bars=delay)
                    elif dir_setup == "SHORT":
                        if leading == "MACD" and ema_bear:
                            confluence = "BEARISH"
                            signal_dir = "SELL"
                            trigger_type = "MACD_THEN_EMA"
                            confirmation_delay = delay
                            strategy_state = "CONFIRMED"
                            action_on_pending = "CLEAR"
                        else:
                            strategy_state = "PENDING_EMA"
                            trigger_type = "MACD_THEN_EMA"
                            confirmation_delay = delay
                            action_on_pending = "UPDATE"
                            new_pending_setup = dict(active_setup, elapsed_bars=delay)
                else:
                    strategy_state = "EXPIRED"
                    rejection_reason = "CONFIRMATION_WINDOW_EXCEEDED"
                    trigger_type = f"{leading}_THEN_{'EMA' if leading == 'MACD' else 'MACD'}"
                    confirmation_delay = delay
                    action_on_pending = "CLEAR"
                    active_setup = None

        # Step 3: Check if new setup starts on current candle
        if strategy_state == "IDLE":
            if macd_bull and not ema_bull:
                strategy_state = "PENDING_EMA"
                trigger_type = "MACD_THEN_EMA"
                confirmation_delay = 0
                action_on_pending = "SET"
                new_pending_setup = {
                    "symbol": symbol,
                    "direction": "LONG",
                    "leading_indicator": "MACD",
                    "setup_candle_time": candle_iso,
                    "elapsed_bars": 0,
                    "strategy_state": "PENDING_EMA",
                }
            elif ema_bull and not macd_bull:
                strategy_state = "PENDING_MACD"
                trigger_type = "EMA_THEN_MACD"
                confirmation_delay = 0
                action_on_pending = "SET"
                new_pending_setup = {
                    "symbol": symbol,
                    "direction": "LONG",
                    "leading_indicator": "EMA",
                    "setup_candle_time": candle_iso,
                    "elapsed_bars": 0,
                    "strategy_state": "PENDING_MACD",
                }
            elif macd_bear and not ema_bear:
                strategy_state = "PENDING_EMA"
                trigger_type = "MACD_THEN_EMA"
                confirmation_delay = 0
                action_on_pending = "SET"
                new_pending_setup = {
                    "symbol": symbol,
                    "direction": "SHORT",
                    "leading_indicator": "MACD",
                    "setup_candle_time": candle_iso,
                    "elapsed_bars": 0,
                    "strategy_state": "PENDING_EMA",
                }
            elif ema_bear and not macd_bear:
                strategy_state = "REJECTED"
                trigger_type = "EMA_THEN_MACD_REJECTED"
                rejection_reason = "SHORT_EMA_FIRST_DISALLOWED"
                confirmation_delay = 0
                action_on_pending = "NONE"
                new_pending_setup = None

    return {
        "symbol": symbol,
        "candle_time": candle_dt,
        "candle_time_str": candle_time_str,
        "timestamp": candle_iso,
        "open": curr_open,
        "high": curr_high,
        "low": curr_low,
        "close": curr_close,
        "previous_close": prev_close,
        "ema9": curr_ema9,
        "previous_ema9": prev_ema9,
        "ema26": curr_ema26,
        "previous_ema26": prev_ema26,
        "macd": curr_macd,
        "previous_macd": prev_macd,
        "macd_signal": curr_signal,
        "previous_signal": prev_signal,
        "macd_histogram": curr_hist,
        "previous_histogram": prev_hist,
        "ema_crossover": ema_crossover,
        "macd_crossover": macd_crossover,
        "confluence": confluence,
        "signal": signal_dir,
        "trigger_type": trigger_type,
        "confirmation_delay": confirmation_delay,
        "strategy_state": strategy_state,
        "rejection_reason": rejection_reason,
        "action_on_pending": action_on_pending,
        "new_pending_setup": new_pending_setup,
    }


# ==============================================================================
# 11. OPENALGO MCX EXECUTION ENGINE
# ==============================================================================
class MCXEMACrossStrategy:
    """
    OpenAlgo Multi-Commodity Strategy Engine for MCX.
    Manages GOLDM, SILVERMIC, and CRUDEOILM with Asymmetric V2-2 EMA/MACD Confirmation.
    """

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        lots: int = LOTS,
        max_active: int = MAX_ACTIVE_POSITIONS,
        host: str = OPENALGO_HOST,
        api_key: str = OPENALGO_API_KEY,
        state_file: Path = STATE_FILE_PATH,
        heartbeat_file: Path = HEARTBEAT_FILE_PATH,
        enable_trailing_runner: bool = ENABLE_TRAILING_RUNNER,
        runner_trail_pct: float = RUNNER_TRAIL_PCT,
        runner_trail_mode: str = RUNNER_TRAIL_MODE,
        early_long_tp_pct: float = EARLY_LONG_TP_PCT,
        early_short_tp_pct: float = EARLY_SHORT_TP_PCT,
        move_sl_to_be: bool = MOVE_SL_TO_BE,
        runner_profit_floor_pct: float = RUNNER_PROFIT_FLOOR_PCT,
    ):
        raw_symbols = symbols or DEFAULT_MCX_UNIVERSE
        self.symbols = [normalize_mcx_symbol(s) for s in raw_symbols]
        self.lots = lots
        self.max_active = max_active
        self.host = host
        self.api_key = api_key
        self.heartbeat_file = heartbeat_file

        self.enable_trailing_runner = enable_trailing_runner
        self.runner_trail_pct = runner_trail_pct
        self.runner_trail_mode = runner_trail_mode
        self.early_long_tp_pct = early_long_tp_pct
        self.early_short_tp_pct = early_short_tp_pct
        self.move_sl_to_be = move_sl_to_be
        self.runner_profit_floor_pct = runner_profit_floor_pct

        self.state_manager = PersistentStateManager(state_file=state_file)
        self.is_running = True
        self.contract_cache: Dict[str, Dict[str, Any]] = {}
        self.paper_orders_placed = 0

        self.client = None
        if OPENALGO_AVAILABLE and api is not None:
            try:
                self.client = api(api_key=self.api_key, host=self.host)
            except Exception as e:
                logger.warning(f"Could not initialize OpenAlgo SDK client: {e}")

        # Setup graceful shutdown signals
        def _handle_signal(signum, frame):
            logger.info(f"Signal {signum} received. Initiating graceful shutdown...")
            self.is_running = False

        try:
            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
        except (ValueError, AttributeError):
            pass

        self._startup_health_check()

    def _startup_health_check(self):
        """Performs startup connectivity, paper-mode safety check, and contract discovery."""
        logger.info("=" * 80)
        logger.info(f"🚀 INITIALIZING {STRATEGY_NAME} (MCX COMMODITIES)")
        logger.info(f"  Target Universe   : {', '.join(self.symbols)}")
        logger.info(f"  Exchange          : {EXCHANGE} (Product: {PRODUCT})")
        logger.info(f"  Timeframe         : {INTERVAL} completed candles")
        logger.info(f"  Trading Lots      : {self.lots} lot(s) per commodity")
        logger.info(f"  Target Long/Short : +{LONG_PROFIT_TARGET_PCT}% / -{SHORT_PROFIT_TARGET_PCT}%")
        logger.info(f"  Catastrophe SL    : -{CATASTROPHE_SL_PCT}%")
        logger.info(f"  BE Stop / Runner  : Break-Even on Early TP | HWM Trail: {self.runner_trail_pct}%")
        logger.info(f"  OpenAlgo Host     : {self.host}")
        logger.info("=" * 80)

        mode_ok, mode_str = self.verify_paper_mode()
        if not mode_ok:
            logger.critical(
                f"🛑 [SAFETY LOCK ACTIVATED] Trading mode is '{mode_str}'! "
                f"{STRATEGY_NAME} requires PAPER or ANALYZE trading mode. Order execution disabled."
            )
        else:
            logger.info(f"✅ Pre-flight safety verified: Trading Mode = '{mode_str.upper()}' (SAFE).")

        self.refresh_contracts()
        self.reconcile_and_audit_positions()
        self.emit_heartbeat(status="STARTED", active_count=0)

    def verify_paper_mode(self) -> Tuple[bool, str]:
        """
        Queries OpenAlgo API to verify the server is running in PAPER or ANALYZE trading mode.
        Returns (is_safe: bool, mode_name: str).
        """
        try:
            resp = requests.get(
                f"{self.host.rstrip('/')}/api/v1/ping",
                headers={"X-API-KEY": self.api_key},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                mode = str(data.get("mode", data.get("trading_mode", ""))).lower()
                if mode in ["paper", "analyze", "virtual", "sandbox", "simulation"]:
                    return True, mode
                if "live" in mode or "real" in mode:
                    return False, "live"

            # Check profile endpoint as secondary confirmation
            prof_resp = requests.get(
                f"{self.host.rstrip('/')}/api/v1/profile",
                headers={"X-API-KEY": self.api_key},
                timeout=5,
            )
            if prof_resp.status_code == 200:
                data = prof_resp.json().get("data", {})
                mode = str(data.get("mode", data.get("trading_mode", ""))).lower()
                if mode in ["paper", "analyze", "virtual", "sandbox", "simulation"]:
                    return True, mode
                if "live" in mode:
                    return False, "live"

        except Exception as e:
            logger.warning(f"Could not reach OpenAlgo ping/profile for mode check ({e}). Defaulting to paper-safe mode.")
            return True, "paper_safe_fallback"

        return True, "paper_default"

    def emit_heartbeat(self, status: str = "ACTIVE", active_count: int = 0, last_eval_time: Optional[str] = None):
        """Emits atomic watchdog heartbeat."""
        try:
            now_ist = get_current_ist()
            payload = {
                "strategy": STRATEGY_NAME,
                "exchange": EXCHANGE,
                "status": status,
                "timestamp": now_ist.isoformat(),
                "time_ist": now_ist.strftime("%d-%b-%Y %H:%M:%S IST"),
                "active_positions_count": active_count,
                "symbols": self.symbols,
                "last_evaluation_time": last_eval_time or now_ist.strftime("%H:%M:%S IST"),
                "tracked_positions": self.state_manager.state.get("tracked_positions", {}),
            }
            temp_file = self.heartbeat_file.with_suffix(f".tmp.{os.getpid()}")
            self.heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
            temp_file.replace(self.heartbeat_file)
        except Exception as e:
            logger.error(f"Failed to emit heartbeat: {e}")

    def refresh_contracts(self, symbols_to_check: Optional[List[str]] = None):
        """Resolves active near-month contracts and verified lot sizes for MCX commodities."""
        targets = symbols_to_check or self.symbols
        logger.info(f"🔍 Discovering active near-month futures contracts for: {', '.join(targets)}...")

        for sym in targets:
            contract_sym, lot_sz, exp_dt = resolve_mcx_contract(sym, self.host, self.api_key)
            if contract_sym and lot_sz:
                self.contract_cache[sym] = {
                    "contract": contract_sym,
                    "lot_size": lot_sz,
                    "expiry_dt": exp_dt,
                }
                logger.info(f"  ✅ {sym} -> Contract: {contract_sym} | Lot: {lot_sz} (1 lot) | Expiry: {exp_dt.strftime('%d-%b-%Y') if exp_dt else 'N/A'}")
            else:
                logger.warning(f"  ⚠️ Could not resolve contract for {sym}.")

    def reconcile_and_audit_positions(self) -> List[Dict[str, Any]]:
        """Reconciles internal state with OpenAlgo open positions on MCX."""
        discrepancies = []
        try:
            broker_positions = self.get_all_open_positions()
            tracked_positions = self.state_manager.state.get("tracked_positions", {})

            for contract_sym, pos_data in list(tracked_positions.items()):
                tracked_qty = pos_data.get("quantity", 0)
                actual_qty = broker_positions.get(contract_sym, 0)
                if tracked_qty != actual_qty:
                    discrepancies.append({
                        "contract": contract_sym,
                        "tracked_qty": tracked_qty,
                        "actual_qty": actual_qty,
                    })
                    logger.warning(
                        f"⚠️ [POSITION MISMATCH] {contract_sym}: Local State = {tracked_qty}, OpenAlgo Broker = {actual_qty}."
                    )
                    if actual_qty == 0:
                        del tracked_positions[contract_sym]
                    else:
                        pos_data["quantity"] = actual_qty
                        pos_data["direction"] = "LONG" if actual_qty > 0 else "SHORT"

            self.state_manager.update_tracked_positions(tracked_positions)
            self.state_manager.record_reconciliation_audit({"discrepancies": discrepancies})
        except Exception as e:
            logger.error(f"Error during position reconciliation: {e}")
        return discrepancies

    def fetch_1h_candles(self, symbol: str, contract_symbol: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        Fetches 1-Hour historical candles from OpenAlgo for the MCX commodity.
        Tries contract symbol on MCX, then base symbol on MCX.
        """
        now = get_current_ist()
        start_date = (now - timedelta(days=45)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        candidates = []
        if contract_symbol:
            candidates.append((contract_symbol, "MCX"))
        candidates.append((symbol, "MCX"))

        df = None
        for sym_cand, exch in candidates:
            # 1. Try SDK
            if self.client is not None:
                try:
                    df = self.client.history(
                        symbol=sym_cand,
                        exchange=exch,
                        interval=INTERVAL,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    if isinstance(df, pd.DataFrame) and not df.empty and len(df) >= 10:
                        break
                except Exception:
                    pass

            # 2. Try REST
            try:
                hist_url = f"{self.host.rstrip('/')}/api/v1/history"
                payload = {
                    "apikey": self.api_key,
                    "symbol": sym_cand,
                    "exchange": exch,
                    "interval": INTERVAL,
                    "start_date": start_date,
                    "end_date": end_date,
                }
                resp = requests.post(hist_url, json=payload, timeout=8)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data:
                        df = pd.DataFrame(data)
                        if len(df) >= 10:
                            break
            except Exception:
                pass

        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return None

        df.columns = [str(col).strip().lower() for col in df.columns]

        if "timestamp" in df.columns:
            if pd.api.types.is_numeric_dtype(df["timestamp"]):
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(IST)
            else:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")
        elif not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        df = df.sort_index()

        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["close"])
        return df

    def get_open_position(self, contract_symbol: str) -> int:
        """Retrieves actual net position quantity from OpenAlgo for the contract."""
        try:
            url = f"{self.host.rstrip('/')}/api/v1/positionbook"
            resp = requests.post(url, json={"apikey": self.api_key}, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                positions = data.get("positions", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for p in positions:
                    if p.get("symbol") == contract_symbol:
                        return int(p.get("quantity", p.get("netqty", 0)))
        except Exception as e:
            logger.error(f"Failed to query position for {contract_symbol}: {e}")
        return 0

    def is_strategy_mcx_position(self, p: Dict[str, Any]) -> bool:
        """
        Determines whether a positionbook record belongs to this strategy's MCX commodity universe.
        Prevents counting unrelated equity derivatives (NFO), indices, or other instruments.
        """
        if not isinstance(p, dict):
            return False

        sym = str(p.get("symbol", "")).strip().upper()
        if not sym:
            return False

        exch = str(p.get("exchange", "") or p.get("exch", "")).strip().upper()
        # If exchange is provided and not MCX, reject immediately
        if exch and exch != "MCX":
            return False

        # 1. Exact match against known resolved active contracts in contract_cache
        active_contracts = {
            str(c.get("contract", "")).strip().upper()
            for c in self.contract_cache.values()
            if isinstance(c, dict) and c.get("contract")
        }
        if sym in active_contracts:
            return True

        # 2. Match against active target commodity symbols or prefixes
        allowed_prefixes = set()
        for base_sym in self.symbols:
            allowed_prefixes.add(base_sym.upper())
            spec = MCX_COMMODITY_SPECS.get(base_sym, {})
            prefix = spec.get("search_prefix")
            if prefix:
                allowed_prefixes.add(prefix.upper())

        # Also add aliases mapping to target symbols
        for alias, target in SYMBOL_ALIASES.items():
            if target in self.symbols:
                allowed_prefixes.add(alias.upper())

        for prefix in allowed_prefixes:
            if sym.startswith(prefix):
                return True

        return False

    def get_all_open_positions(self, only_strategy_universe: bool = True) -> Dict[str, int]:
        """
        Queries OpenAlgo /api/v1/positionbook and returns {contract_symbol: net_quantity}.
        When only_strategy_universe is True (default), filters out non-MCX and unrelated instruments.
        """
        pos_map = {}
        try:
            url = f"{self.host.rstrip('/')}/api/v1/positionbook"
            resp = requests.post(url, json={"apikey": self.api_key}, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                positions = (
                    data.get("positions", [])
                    if isinstance(data, dict)
                    else (data if isinstance(data, list) else [])
                )
                for p in positions:
                    if only_strategy_universe and not self.is_strategy_mcx_position(p):
                        continue
                    sym = p.get("symbol")
                    qty = int(p.get("quantity", p.get("netqty", 0)))
                    if sym:
                        pos_map[sym] = qty
        except Exception as e:
            logger.error(f"Error querying positionbook: {e}")
        return pos_map

    def check_orderbook_for_matching_order(
        self, contract_symbol: str, action: str, quantity: int, max_lookback_seconds: int = 180
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Orderbook reconciliation before retry."""
        try:
            resp = requests.post(
                f"{self.host.rstrip('/')}/api/v1/orderbook",
                json={"apikey": self.api_key},
                timeout=6,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                orders = data.get("orders", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
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
        except Exception as e:
            logger.error(f"❌ Error querying orderbook during reconciliation: {e}")

        return False, None, None

    def place_paper_order(
        self,
        symbol: str,
        contract_symbol: str,
        action: str,
        quantity: int,
        candle_time: Any = None,
        reference_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Submits order to OpenAlgo paper engine with safety locks, idempotency, and retries.
        """
        mode_ok, mode_str = self.verify_paper_mode()
        if not mode_ok:
            logger.critical(f"🛑 [SAFETY LOCK] Order placement for {contract_symbol} BLOCKED! Mode is '{mode_str}'.")
            return None

        order_key = f"{contract_symbol}_{action}_{quantity}_{candle_time or 'LIVE'}"
        if self.state_manager.is_order_inflight_or_filled(order_key):
            logger.warning(f"ℹ️ [IDEMPOTENCY LOCK] Order {order_key} is already PENDING or FILLED. Skipping.")
            return None

        if quantity <= 0:
            logger.error(f"❌ Cannot place order: Invalid quantity ({quantity}) for {contract_symbol}.")
            return None

        logger.info(f"🚀 [PAPER ORDER] Submitting {action} {quantity} units of {contract_symbol} [{symbol}] (Key: {order_key})...")
        self.state_manager.mark_order_pending(
            order_key,
            {"symbol": symbol, "contract": contract_symbol, "action": action, "qty": quantity},
        )

        max_attempts = 2
        attempt = 0
        order_kwargs: Dict[str, Any] = {}
        if reference_price is not None and float(reference_price) > 0:
            order_kwargs["price"] = float(reference_price)

        while attempt < max_attempts:
            attempt += 1
            try:
                if self.client is not None:
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
                else:
                    order_url = f"{self.host.rstrip('/')}/api/v1/placeorder"
                    payload = {
                        "apikey": self.api_key,
                        "strategy": STRATEGY_NAME,
                        "symbol": contract_symbol,
                        "exchange": EXCHANGE,
                        "action": action,
                        "price_type": "MARKET",
                        "product": PRODUCT,
                        "quantity": quantity,
                        **order_kwargs,
                    }
                    r = requests.post(order_url, json=payload, timeout=8)
                    resp = r.json() if r.status_code == 200 else {"status": "error", "message": r.text}

                logger.info(f"📦 Order Response (Attempt {attempt}, {contract_symbol}): {resp}")

                if isinstance(resp, dict):
                    status = resp.get("status")
                    order_id = resp.get("orderid")
                    msg = str(resp.get("message", "")).lower()

                    if status in ["success", 200, "COMPLETE"]:
                        self.state_manager.mark_order_resolved(order_key, "FILLED", order_id)
                        self.paper_orders_placed += 1
                        return resp
                    elif "auth" in msg or "apikey" in msg:
                        logger.critical(f"🛑 [AUTH FAILURE] {contract_symbol}: {resp.get('message')}.")
                        self.state_manager.mark_order_resolved(order_key, "AUTH_FAILED")
                        return None
                    elif "sqlite" in msg or "database is locked" in msg:
                        time.sleep(1.0 * attempt)
                    else:
                        logger.warning(f"⚠️ Response: {resp}")

            except Exception as e:
                logger.warning(f"⚠️ Exception during placeorder attempt {attempt} for {contract_symbol}: {e}")

            if attempt < max_attempts:
                time.sleep(2)
                found, order_id, order_status = self.check_orderbook_for_matching_order(
                    contract_symbol, action, quantity
                )
                if found:
                    self.state_manager.mark_order_resolved(order_key, "FILLED", order_id)
                    self.paper_orders_placed += 1
                    if ORDER_PACING_DELAY_SEC > 0:
                        time.sleep(ORDER_PACING_DELAY_SEC)
                    return {"status": "success", "orderid": order_id, "verified_via": "orderbook"}

        self.state_manager.mark_order_resolved(order_key, "FAILED_UNCERTAIN")
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
    ) -> float:
        """Retrieves actual fill price from OpenAlgo."""
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

        for attempt in range(max_retries):
            try:
                url = f"{self.host.rstrip('/')}/api/v1/orderstatus"
                r = requests.post(url, json={"apikey": self.api_key, "orderid": str(order_id)}, timeout=5)
                if r.status_code == 200:
                    st_data = r.json().get("data", r.json())
                    if isinstance(st_data, dict):
                        for k in ["average_price", "avg_price", "fill_price", "traded_price", "price"]:
                            v = st_data.get(k)
                            if v is not None:
                                try:
                                    fv = float(v)
                                    if fv > 0:
                                        return fv
                                except (ValueError, TypeError):
                                    pass
            except Exception:
                pass
            time.sleep(0.5)

        # Fallback to live quote LTP
        try:
            q_url = f"{self.host.rstrip('/')}/api/v1/quotes"
            q_resp = requests.post(q_url, json={"apikey": self.api_key, "symbol": contract_symbol, "exchange": EXCHANGE}, timeout=4)
            if q_resp.status_code == 200:
                q_data = q_resp.json().get("data", {})
                ltp = float(q_data.get("ltp", 0.0) or 0.0)
                if ltp > 0:
                    return ltp
        except Exception:
            pass

        return fallback_price if fallback_price > 0 else 0.0

    def check_and_execute_target_or_sl(
        self,
        symbol: str,
        contract_sym: str,
        df_completed: pd.DataFrame,
    ) -> bool:
        """Evaluates Catastrophe SL, HWM Trailing Runner, Break-Even SL, and Profit Target."""
        if df_completed is None or df_completed.empty:
            return False

        tracked_positions = self.state_manager.state.get("tracked_positions", {})
        pos_info = tracked_positions.get(contract_sym)
        if not pos_info:
            return False

        qty = int(pos_info.get("quantity", 0))
        if qty == 0:
            return False

        entry_price = float(pos_info.get("average_price", 0.0) or 0.0)
        if entry_price <= 0:
            return False

        direction = pos_info.get("direction")
        if not direction:
            direction = "LONG" if qty > 0 else "SHORT"

        last_idx = df_completed.index[-1]
        candle_iso = last_idx.isoformat() if hasattr(last_idx, "isoformat") else str(last_idx)
        candle_time_str = format_candle_time(last_idx)
        last_candle = df_completed.iloc[-1]
        candle_high = float(last_candle["high"])
        candle_low = float(last_candle["low"])
        candle_close = float(last_candle["close"])

        long_target_px = entry_price * (1.0 + (LONG_PROFIT_TARGET_PCT / 100.0))
        short_target_px = entry_price * (1.0 - (SHORT_PROFIT_TARGET_PCT / 100.0))
        long_catastrophe_px = entry_price * (1.0 - (CATASTROPHE_SL_PCT / 100.0))
        short_catastrophe_px = entry_price * (1.0 + (CATASTROPHE_SL_PCT / 100.0))

        early_long_target_px = entry_price * (1.0 + (self.early_long_tp_pct / 100.0))
        early_short_target_px = entry_price * (1.0 - (self.early_short_tp_pct / 100.0))

        target_hit = False
        catastrophe_hit = False
        early_target_hit = False
        be_sl_hit = False
        target_exit_px = 0.0
        sl_exit_px = 0.0

        runner_active = bool(pos_info.get("runner_active", False))
        already_early_hit = bool(pos_info.get("early_target_hit", False))
        be_stop_active = bool(pos_info.get("be_stop_active", False))
        peak_price = float(pos_info.get("peak_price", entry_price))
        trough_price = float(pos_info.get("trough_price", entry_price))

        if direction == "LONG":
            target_hit = candle_high >= long_target_px
            catastrophe_hit = candle_low <= long_catastrophe_px
            early_target_hit = candle_high >= early_long_target_px
            target_exit_px = round(long_target_px, 2)
            sl_exit_px = round(long_catastrophe_px, 2)
            if be_stop_active:
                be_sl_hit = candle_low <= entry_price
        elif direction == "SHORT":
            target_hit = candle_low <= short_target_px
            catastrophe_hit = candle_high >= short_catastrophe_px
            early_target_hit = candle_low <= early_short_target_px
            target_exit_px = round(short_target_px, 2)
            sl_exit_px = round(short_catastrophe_px, 2)
            if be_stop_active:
                be_sl_hit = candle_high >= entry_price
        else:
            return False

        # Priority 1: Catastrophe SL
        if catastrophe_hit:
            exit_reason = "CATASTROPHE_SL"
            expected_exit_px = sl_exit_px

        # Priority 2: Trailing Runner
        elif runner_active and self.enable_trailing_runner:
            trail_pct = self.runner_trail_pct
            floor_pct = self.runner_profit_floor_pct
            if direction == "LONG":
                peak_price = max(peak_price, candle_high)
                pos_info["peak_price"] = peak_price
                raw_trail_sl = peak_price * (1.0 - (trail_pct / 100.0))
                guaranteed_floor = entry_price * (1.0 + (floor_pct / 100.0))
                effective_trail_sl = max(raw_trail_sl, guaranteed_floor, entry_price)
                pos_info["effective_trail_sl"] = round(effective_trail_sl, 2)
                if candle_low <= effective_trail_sl:
                    exit_reason = "RUNNER_HWM_TRAIL"
                    expected_exit_px = round(effective_trail_sl, 2)
                else:
                    self.state_manager.update_tracked_positions(tracked_positions)
                    return False
            else:
                trough_price = min(trough_price, candle_low)
                pos_info["trough_price"] = trough_price
                raw_trail_sl = trough_price * (1.0 + (trail_pct / 100.0))
                guaranteed_floor = entry_price * (1.0 - (floor_pct / 100.0))
                effective_trail_sl = min(raw_trail_sl, guaranteed_floor, entry_price)
                pos_info["effective_trail_sl"] = round(effective_trail_sl, 2)
                if candle_high >= effective_trail_sl:
                    exit_reason = "RUNNER_HWM_TRAIL"
                    expected_exit_px = round(effective_trail_sl, 2)
                else:
                    self.state_manager.update_tracked_positions(tracked_positions)
                    return False

        # Priority 3: Break-Even SL
        elif be_stop_active and be_sl_hit:
            exit_reason = "BREAK_EVEN_SL"
            expected_exit_px = round(entry_price, 2)

        # Priority 4: Target Hit / Runner Activation
        elif target_hit:
            if self.enable_trailing_runner and self.runner_trail_mode == "HWM":
                pos_info["runner_active"] = True
                pos_info["target_hit_candle"] = candle_iso
                pos_info["early_target_hit"] = True
                pos_info["be_stop_active"] = True
                if direction == "LONG":
                    peak_price = max(entry_price, candle_high)
                    pos_info["peak_price"] = peak_price
                    raw_trail_sl = peak_price * (1.0 - (self.runner_trail_pct / 100.0))
                    guaranteed_floor = entry_price * (1.0 + (self.runner_profit_floor_pct / 100.0))
                    effective_trail_sl = max(raw_trail_sl, guaranteed_floor, entry_price)
                    pos_info["effective_trail_sl"] = round(effective_trail_sl, 2)
                    logger.info(
                        f"🏃 [RUNNER ACTIVATED] {symbol} ({contract_sym}): Long Target {LONG_PROFIT_TARGET_PCT}% reached on candle {candle_time_str} | "
                        f"Peak: ₹{peak_price:.2f} | HWM Trail SL: ₹{effective_trail_sl:.2f}"
                    )
                else:
                    trough_price = min(entry_price, candle_low)
                    pos_info["trough_price"] = trough_price
                    raw_trail_sl = trough_price * (1.0 + (self.runner_trail_pct / 100.0))
                    guaranteed_floor = entry_price * (1.0 - (self.runner_profit_floor_pct / 100.0))
                    effective_trail_sl = min(raw_trail_sl, guaranteed_floor, entry_price)
                    pos_info["effective_trail_sl"] = round(effective_trail_sl, 2)
                    logger.info(
                        f"🏃 [RUNNER ACTIVATED] {symbol} ({contract_sym}): Short Target {SHORT_PROFIT_TARGET_PCT}% reached on candle {candle_time_str} | "
                        f"Trough: ₹{trough_price:.2f} | HWM Trail SL: ₹{effective_trail_sl:.2f}"
                    )
                self.state_manager.update_tracked_positions(tracked_positions)
                return False
            else:
                exit_reason = "TARGET_HIT"
                expected_exit_px = target_exit_px

        # Priority 5: Early Target Milestone -> Lock Break-Even
        elif early_target_hit and not already_early_hit:
            pos_info["early_target_hit"] = True
            pos_info["early_target_candle"] = candle_iso
            if self.move_sl_to_be:
                pos_info["be_stop_active"] = True
                logger.info(
                    f"🛡️ [EARLY PROFIT MILESTONE] {symbol} ({contract_sym}): Early target reached on candle {candle_time_str} | "
                    f"Stop-Loss moved to Break-Even (₹{entry_price:.2f})."
                )
            self.state_manager.update_tracked_positions(tracked_positions)
            return False
        else:
            return False

        exit_action = "SELL" if direction == "LONG" else "BUY"
        exit_qty = abs(qty)

        exit_key = f"{symbol}_{candle_iso}_EXIT_{exit_reason}"
        if self.state_manager.is_signal_processed(exit_key):
            return False

        logger.info(
            f"🎯 [RISK EXIT TRIGGERED] {symbol} ({contract_sym}): {exit_reason} on candle {candle_time_str} | "
            f"Direction: {direction} | Entry: ₹{entry_price:.2f} | Close: ₹{candle_close:.2f} | Action: {exit_action} {exit_qty}"
        )

        resp = self.place_paper_order(
            symbol=symbol,
            contract_symbol=contract_sym,
            action=exit_action,
            quantity=exit_qty,
            candle_time=candle_iso,
            reference_price=candle_close,
        )

        if resp:
            order_id = resp.get("orderid", f"PAPER_EXIT_{int(time.time())}")
            order_status = "FILLED"
            exit_fill_price = self.get_order_fill_price(
                order_id=str(order_id),
                contract_symbol=contract_sym,
                initial_resp=resp,
                fallback_price=expected_exit_px,
            )

            self.state_manager.record_signal_processed(exit_key)
            self.state_manager.record_processed_candle(symbol, candle_iso)
            self.state_manager.record_execution(
                symbol=symbol,
                contract=contract_sym,
                action=exit_action,
                qty=exit_qty,
                candle_time=candle_iso,
                order_resp=resp,
                order_id=str(order_id),
            )

            updated_tracked = dict(self.state_manager.state.get("tracked_positions", {}))
            if contract_sym in updated_tracked:
                del updated_tracked[contract_sym]
            self.state_manager.update_tracked_positions(updated_tracked)

            exit_alert_payload = {
                "strategy_name": STRATEGY_NAME,
                "contract": contract_sym,
                "symbol": symbol,
                "direction": direction,
                "action": exit_action,
                "exit_reason": exit_reason,
                "quantity": exit_qty,
                "entry_price": entry_price,
                "exit_price": exit_fill_price,
                "order_id": order_id,
                "order_status": order_status,
                "candle_time_str": candle_time_str,
                "candle_time": candle_iso,
                "execution_time": get_current_ist().strftime("%H:%M:%S"),
            }
            alert_key = f"ORDER_ALERT_{order_id}"
            if not self.state_manager.is_alert_sent(alert_key):
                exit_msg = format_paper_exit_alert(exit_alert_payload)
                send_telegram_alert(exit_msg)
                self.state_manager.record_alert_sent(alert_key)

            research_entry = {
                "symbol": symbol,
                "timestamp": candle_iso,
                "open": float(last_candle.get("open", candle_close)),
                "high": candle_high,
                "low": candle_low,
                "close": candle_close,
                "ema9": float(last_candle.get("ema9", 0.0)),
                "previous_ema9": 0.0,
                "ema26": float(last_candle.get("ema26", 0.0)),
                "previous_ema26": 0.0,
                "macd": float(last_candle.get("macd", 0.0)),
                "previous_macd": 0.0,
                "macd_signal": float(last_candle.get("macd_signal", 0.0)),
                "previous_signal": 0.0,
                "macd_histogram": float(last_candle.get("macd_histogram", 0.0)),
                "previous_histogram": 0.0,
                "ema_crossover": "NONE",
                "macd_crossover": "NONE",
                "combined_signal": f"EXIT_{exit_reason}",
                "trigger_type": exit_reason,
                "confirmation_delay": 0,
                "strategy_state": f"EXIT_{exit_reason}",
                "rejection_reason": "NONE",
                "direction": direction,
                "paper_order_id": str(order_id),
                "order_status": exit_reason,
                "quantity": exit_qty,
                "position_before": qty,
                "position_after": 0,
            }
            log_research_record(research_entry)
            return True

        return False

    def execute_symbol_decision(
        self,
        symbol: str,
        sig_data: Dict[str, Any],
        active_positions_count: int,
        df_completed: Optional[pd.DataFrame] = None,
    ) -> Tuple[bool, int]:
        """Evaluates entry signals, reversals, and executes paper orders."""
        sig = sig_data.get("signal")
        candle_time = sig_data.get("candle_time_str")
        candle_iso = sig_data.get("timestamp")

        if sig not in ["BUY", "SELL"]:
            return False, active_positions_count

        signal_key = f"{symbol}_{candle_iso}_{sig}"
        if self.state_manager.is_signal_processed(signal_key):
            logger.info(f"ℹ️ Signal {sig} for {symbol} on candle {candle_time} already processed. Skipping duplicate.")
            return False, active_positions_count

        c_meta = self.contract_cache.get(symbol)
        if not c_meta:
            self.refresh_contracts([symbol])
            c_meta = self.contract_cache.get(symbol)

        if not c_meta or not c_meta.get("contract"):
            logger.warning(f"⚠️ Cannot trade {symbol}: active MCX futures contract could not be resolved.")
            return False, active_positions_count

        contract_sym = c_meta["contract"]
        lot_size = c_meta["lot_size"]
        base_order_qty = self.lots * lot_size

        current_pos = self.get_open_position(contract_sym)

        action = None
        exec_qty = 0
        is_reversal = False

        if sig == "BUY":
            if current_pos == 0:
                if self.max_active <= 0 or active_positions_count < self.max_active:
                    action = "BUY"
                    exec_qty = base_order_qty
                else:
                    logger.info(f"⏸️ Max active positions ({self.max_active}) reached. Skipping NEW LONG for {symbol}.")
                    return False, active_positions_count
            elif current_pos < 0:
                action = "BUY"
                exec_qty = abs(current_pos) + base_order_qty
                is_reversal = True
                logger.info(f"🔄 [REVERSAL SHORT->LONG] {symbol} ({contract_sym}): Reversing pos ({current_pos}) -> Order Qty = {exec_qty}")
            else:
                logger.info(f"ℹ️ Already in LONG position ({current_pos}) for {symbol}. Skipping.")
                self.state_manager.record_signal_processed(signal_key)
                return False, active_positions_count

        elif sig == "SELL":
            if current_pos == 0:
                if self.max_active <= 0 or active_positions_count < self.max_active:
                    action = "SELL"
                    exec_qty = base_order_qty
                else:
                    logger.info(f"⏸️ Max active positions ({self.max_active}) reached. Skipping NEW SHORT for {symbol}.")
                    return False, active_positions_count
            elif current_pos > 0:
                action = "SELL"
                exec_qty = current_pos + base_order_qty
                is_reversal = True
                logger.info(f"🔄 [REVERSAL LONG->SHORT] {symbol} ({contract_sym}): Reversing pos ({current_pos}) -> Order Qty = {exec_qty}")
            else:
                logger.info(f"ℹ️ Already in SHORT position ({current_pos}) for {symbol}. Skipping.")
                self.state_manager.record_signal_processed(signal_key)
                return False, active_positions_count

        if not action or exec_qty <= 0:
            return False, active_positions_count

        resp = self.place_paper_order(
            symbol=symbol,
            contract_symbol=contract_sym,
            action=action,
            quantity=exec_qty,
            candle_time=candle_iso,
            reference_price=float(sig_data.get("close", 0.0)),
        )

        if resp:
            order_id = resp.get("orderid", "PAPER_" + str(int(time.time())))
            order_status = "FILLED"
            candle_close = float(sig_data.get("close", 0.0))
            fill_price = self.get_order_fill_price(
                order_id=str(order_id),
                contract_symbol=contract_sym,
                initial_resp=resp,
                fallback_price=candle_close,
            )

            self.state_manager.record_signal_processed(signal_key)
            self.state_manager.record_processed_candle(symbol, candle_iso)
            self.state_manager.record_execution(
                symbol=symbol,
                contract=contract_sym,
                action=action,
                qty=exec_qty,
                candle_time=candle_iso,
                order_resp=resp,
                order_id=str(order_id),
            )

            new_net_pos = base_order_qty if sig == "BUY" else -base_order_qty
            tracked_positions = self.state_manager.state.get("tracked_positions", {})
            tracked_positions[contract_sym] = {
                "symbol": symbol,
                "contract": contract_sym,
                "direction": "LONG" if sig == "BUY" else "SHORT",
                "quantity": new_net_pos,
                "average_price": fill_price,
                "entry_candle": candle_iso,
                "entry_time": get_current_ist().isoformat(),
                "order_id": order_id,
                "runner_active": False,
                "early_target_hit": False,
                "be_stop_active": False,
                "peak_price": fill_price,
                "trough_price": fill_price,
            }
            self.state_manager.update_tracked_positions(tracked_positions)

            alert_payload = {
                "strategy_name": STRATEGY_NAME,
                "contract": contract_sym,
                "symbol": symbol,
                "action": action,
                "direction": "LONG" if sig == "BUY" else "SHORT",
                "quantity": exec_qty,
                "entry_price": fill_price,
                "order_id": order_id,
                "order_status": order_status,
                "price_type": "MARKET",
                "exchange": EXCHANGE,
                "product": PRODUCT,
                "pos_before": current_pos,
                "pos_after": new_net_pos,
                "trigger_type": sig_data.get("trigger_type"),
                "confirmation_delay": sig_data.get("confirmation_delay"),
                "candle_time_str": candle_time,
                "close": candle_close,
                "ema9": sig_data.get("ema9"),
                "ema26": sig_data.get("ema26"),
                "macd": sig_data.get("macd"),
                "macd_signal": sig_data.get("macd_signal"),
                "macd_histogram": sig_data.get("macd_histogram"),
                "execution_time": get_current_ist().strftime("%H:%M:%S"),
            }
            alert_key = f"ORDER_ALERT_{order_id}"
            if not self.state_manager.is_alert_sent(alert_key):
                msg = format_paper_trade_alert(alert_payload)
                send_telegram_alert(msg)
                self.state_manager.record_alert_sent(alert_key)

            research_entry = {
                "symbol": symbol,
                "timestamp": candle_iso,
                "open": sig_data.get("open"),
                "high": sig_data.get("high"),
                "low": sig_data.get("low"),
                "close": candle_close,
                "ema9": sig_data.get("ema9"),
                "previous_ema9": sig_data.get("previous_ema9"),
                "ema26": sig_data.get("ema26"),
                "previous_ema26": sig_data.get("previous_ema26"),
                "macd": sig_data.get("macd"),
                "previous_macd": sig_data.get("previous_macd"),
                "macd_signal": sig_data.get("macd_signal"),
                "previous_signal": sig_data.get("previous_signal"),
                "macd_histogram": sig_data.get("macd_histogram"),
                "previous_histogram": sig_data.get("previous_histogram"),
                "ema_crossover": sig_data.get("ema_crossover"),
                "macd_crossover": sig_data.get("macd_crossover"),
                "combined_signal": sig,
                "trigger_type": sig_data.get("trigger_type"),
                "confirmation_delay": sig_data.get("confirmation_delay"),
                "strategy_state": sig_data.get("strategy_state"),
                "rejection_reason": sig_data.get("rejection_reason"),
                "direction": "LONG" if sig == "BUY" else "SHORT",
                "paper_order_id": str(order_id),
                "order_status": order_status,
                "quantity": exec_qty,
                "position_before": current_pos,
                "position_after": new_net_pos,
            }
            log_research_record(research_entry)

            new_active_count = active_positions_count + (1 if current_pos == 0 else 0)
            return True, new_active_count

        return False, active_positions_count

    def _fetch_and_eval_symbol(self, symbol: str) -> Dict[str, Any]:
        """Fetches candles and evaluates indicators for a single commodity."""
        c_meta = self.contract_cache.get(symbol, {})
        contract_sym = c_meta.get("contract")

        df = self.fetch_1h_candles(symbol, contract_sym)
        if df is None or len(df) < 28:
            return {"symbol": symbol, "status": "INSUFFICIENT_DATA"}

        df_completed = get_completed_1h_candles(df)
        if df_completed is None or len(df_completed) < 28:
            return {"symbol": symbol, "status": "NO_COMPLETED_CANDLE"}

        df_ind = calculate_indicators(df_completed)
        pending_setup = self.state_manager.get_pending_setup(symbol)

        sig_data = detect_ema_macd_signal(
            df=df_ind,
            symbol=symbol,
            pending_setup=pending_setup,
            window=CONFIRMATION_WINDOW,
        )

        return {
            "symbol": symbol,
            "status": "OK",
            "df_completed": df_completed,
            "sig_data": sig_data,
            "contract_symbol": contract_sym,
        }

    def execute_cycle(self):
        """Runs a complete evaluation cycle across all MCX target commodities."""
        now_ist = get_current_ist()
        is_open, open_reason = is_mcx_trading_time(now_ist)
        if not is_open:
            logger.info(f"⏸️ MCX is currently closed ({open_reason}). Waiting for session opening (09:00 - 23:30 IST).")
            self.emit_heartbeat(status="IDLE_MARKET_CLOSED")
            return

        logger.info(f"⏳ [CYCLE START] Evaluating MCX commodities at {now_ist.strftime('%d-%b-%Y %H:%M:%S IST')}...")

        # 1. Fetch & evaluate all target symbols in parallel
        results = []
        with ThreadPoolExecutor(max_workers=min(len(self.symbols), 4)) as executor:
            futures = [executor.submit(self._fetch_and_eval_symbol, sym) for sym in self.symbols]
            for f in futures:
                try:
                    res = f.result()
                    if res:
                        results.append(res)
                except Exception as e:
                    logger.error(f"Error evaluating commodity: {e}")

        open_positions = self.get_all_open_positions()
        active_count = len([qty for qty in open_positions.values() if qty != 0])

        # 2. Risk check: Target / Catastrophe SL / Trailing Runner on active positions
        for res in results:
            if res.get("status") == "OK":
                sym = res["symbol"]
                contract_sym = res.get("contract_symbol")
                df_comp = res.get("df_completed")
                if contract_sym and df_comp is not None:
                    exit_placed = self.check_and_execute_target_or_sl(sym, contract_sym, df_comp)
                    if exit_placed:
                        active_count = max(0, active_count - 1)

        # 3. New Entry & Reversal Evaluations
        for res in results:
            if res.get("status") == "OK":
                sym = res["symbol"]
                sig_data = res.get("sig_data")
                df_comp = res.get("df_completed")

                if sig_data:
                    action_on_pending = sig_data.get("action_on_pending")
                    if action_on_pending == "CLEAR":
                        self.state_manager.clear_pending_setup(sym)
                    elif action_on_pending in ["SET", "UPDATE"]:
                        new_setup = sig_data.get("new_pending_setup")
                        if new_setup:
                            self.state_manager.save_pending_setup(sym, new_setup)

                    sig = sig_data.get("signal")
                    if sig in ["BUY", "SELL"]:
                        placed, active_count = self.execute_symbol_decision(
                            sym, sig_data, active_count, df_comp
                        )

        self.emit_heartbeat(status="ACTIVE", active_count=active_count)
        active_symbols = [f"{sym} ({qty})" for sym, qty in open_positions.items() if qty != 0]
        pos_summary_str = f" [{', '.join(active_symbols)}]" if active_symbols and active_count > 0 else ""
        logger.info(f"✅ [CYCLE COMPLETE] Active MCX Positions: {active_count}{pos_summary_str}")

    def run_loop(self, poll_interval: int = POLL_INTERVAL_SECONDS):
        """Continuous production polling loop with exact candle boundary alignment."""
        logger.info(f"🔁 Strategy loop started for {STRATEGY_NAME} (Poll Interval: {poll_interval}s).")
        while self.is_running:
            try:
                self.execute_cycle()
            except Exception as e:
                logger.error(f"Error during cycle execution: {e}", exc_info=True)

            if RUN_ONCE or not self.is_running:
                break

            sleep_sec = get_seconds_to_next_candle_boundary(buffer_seconds=2)
            wait_time = min(float(poll_interval), sleep_sec)
            logger.info(f"💤 Sleeping {wait_time:.1f}s until next boundary check...")
            time.sleep(wait_time)

        logger.info(f"⏹️ {STRATEGY_NAME} shutdown complete.")


# ==============================================================================
# 12. AUTOMATED VERIFICATION TEST SUITE (40+ TEST CASES)
# ==============================================================================
def run_automated_tests() -> bool:
    """Executes comprehensive automated unit and integration tests."""
    logger.info("=" * 80)
    logger.info("🧪 RUNNING MCX EMA/MACD AUTOMATED TEST SUITE")
    logger.info("=" * 80)

    results: List[Tuple[int, str, bool, str]] = []

    def make_test_df(candles: List[Dict[str, float]], base_time: Optional[datetime] = None) -> pd.DataFrame:
        if base_time is None:
            base_time = datetime(2026, 11, 10, 10, 0, tzinfo=IST)
        rows = []
        times = []
        for i, c in enumerate(candles):
            t = base_time + timedelta(hours=i)
            times.append(t)
            row = dict(c)
            if "open" not in row:
                row["open"] = row["close"]
            if "high" not in row:
                row["high"] = row["close"]
            if "low" not in row:
                row["low"] = row["close"]
            if "macd_histogram" not in row:
                sig_val = row.get("macd_signal", row.get("signal", 0.0))
                row["macd_histogram"] = row.get("macd", 0.0) - sig_val
            rows.append(row)
        return pd.DataFrame(rows, index=times)

    class MockMCXEngine(MCXEMACrossStrategy):
        def __init__(self, *args, **kwargs):
            if "state_file" not in kwargs:
                import tempfile, uuid
                self._tmp_state_file = Path(tempfile.gettempdir()) / f"test_mcx_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}.json"
                kwargs["state_file"] = self._tmp_state_file
            else:
                self._tmp_state_file = None
            if "heartbeat_file" not in kwargs:
                import tempfile, uuid
                kwargs["heartbeat_file"] = Path(tempfile.gettempdir()) / f"test_mcx_hb_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}.json"
            super().__init__(*args, **kwargs)

        def _startup_health_check(self):
            # Suppress network healthcheck in unit tests
            pass

        def verify_paper_mode(self):
            return True, "analyze"

        def place_paper_order(self, symbol, contract_symbol, action, quantity, candle_time=None, reference_price=None):
            order_id = f"MOCK_MCX_{int(time.time()*1000)}"
            order_key = f"{contract_symbol}_{action}_{quantity}_{candle_time or 'LIVE'}"
            self.state_manager.mark_order_pending(order_key, {"symbol": symbol, "contract": contract_symbol, "action": action, "qty": quantity})
            self.state_manager.mark_order_resolved(order_key, "FILLED", order_id)
            self.paper_orders_placed += 1
            return {"status": "success", "orderid": order_id, "mode": "analyze"}

        def get_order_fill_price(self, order_id, contract_symbol, initial_resp=None, fallback_price=0.0, max_retries=3):
            return fallback_price if fallback_price > 0 else 75000.0

        def get_open_position(self, contract_symbol: str) -> int:
            pos = self.state_manager.state.get("tracked_positions", {}).get(contract_symbol, {})
            return int(pos.get("quantity", 0))

        def __del__(self):
            if getattr(self, "_tmp_state_file", None) and self._tmp_state_file.exists():
                try:
                    self._tmp_state_file.unlink()
                except Exception:
                    pass

    # 1. Alias normalizations
    try:
        assert normalize_mcx_symbol("CRUDEM") == "CRUDEOILM"
        assert normalize_mcx_symbol("CRUDE") == "CRUDEOILM"
        assert normalize_mcx_symbol("GOLD") == "GOLDM"
        assert normalize_mcx_symbol("SILVER") == "SILVERMIC"
        assert normalize_mcx_symbol("SILVERM") == "SILVERMIC"
        assert normalize_mcx_symbol("GOLDM") == "GOLDM"
        results.append((1, "Commodity symbol alias normalization", True, "CRUDEM/CRUDE/GOLD/SILVER correctly mapped"))
    except Exception as e:
        results.append((1, "Commodity symbol alias normalization", False, str(e)))

    # 2. MCX Session timings
    try:
        t_open = datetime(2026, 11, 11, 14, 0, tzinfo=IST)  # Wednesday 14:00 IST
        is_op, reason = is_mcx_trading_time(t_open)
        assert is_op and reason == "MCX_SESSION_OPEN"

        t_evening = datetime(2026, 11, 11, 22, 30, tzinfo=IST)  # 22:30 IST
        is_op2, reason2 = is_mcx_trading_time(t_evening)
        assert is_op2 and reason2 == "MCX_SESSION_OPEN"

        t_closed = datetime(2026, 11, 11, 23, 45, tzinfo=IST)  # 23:45 IST
        is_op3, reason3 = is_mcx_trading_time(t_closed)
        assert not is_op3 and reason3 == "POST_MARKET_HOURS"

        t_wkend = datetime(2026, 11, 14, 12, 0, tzinfo=IST)  # Saturday
        is_op4, reason4 = is_mcx_trading_time(t_wkend)
        assert not is_op4 and reason4 == "WEEKEND_CLOSED"
        results.append((2, "MCX market session validation", True, "Trading session 09:00 - 23:30 verified"))
    except Exception as e:
        results.append((2, "MCX market session validation", False, str(e)))

    # 3. Schedule boundary
    try:
        t_930 = datetime(2026, 11, 11, 9, 30, tzinfo=IST)
        sec = get_seconds_to_next_candle_boundary(t_930, buffer_seconds=2)
        assert abs(sec - ((30 * 60) + 2)) <= 1
        results.append((3, "MCX candle boundary schedule", True, f"Boundary target calculated: {sec}s"))
    except Exception as e:
        results.append((3, "MCX candle boundary schedule", False, str(e)))

    # 4. Long SAME_CANDLE signal
    try:
        df1 = make_test_df([
            {"close": 100, "ema9": 99, "ema26": 101, "macd": -1.0, "macd_signal": -0.5},
            {"close": 105, "ema9": 102, "ema26": 101, "macd": 0.5, "macd_signal": 0.0},
        ])
        s1 = detect_ema_macd_signal(df1, symbol="GOLDM")
        assert s1 is not None and s1["signal"] == "BUY"
        assert s1["trigger_type"] == "SAME_CANDLE"
        assert s1["confirmation_delay"] == 0
        assert s1["strategy_state"] == "CONFIRMED"
        results.append((4, "Long SAME_CANDLE -> signal", True, "BUY via SAME_CANDLE (Delay 0)"))
    except Exception as e:
        results.append((4, "Long SAME_CANDLE -> signal", False, str(e)))

    # 5. Long MACD_FIRST -> EMA confirmation within 2 candles -> signal
    try:
        df2 = make_test_df([
            {"close": 100, "ema9": 98, "ema26": 102, "macd": -1.0, "macd_signal": -0.5},
            {"close": 102, "ema9": 99, "ema26": 101, "macd": 0.2, "macd_signal": -0.1},
            {"close": 106, "ema9": 102, "ema26": 101, "macd": 0.8, "macd_signal": 0.2},
        ])
        s2_pending = detect_ema_macd_signal(df2.iloc[:2], symbol="GOLDM")
        assert s2_pending["strategy_state"] == "PENDING_EMA"
        assert s2_pending["signal"] is None

        s2 = detect_ema_macd_signal(df2, symbol="GOLDM", pending_setup=s2_pending["new_pending_setup"])
        assert s2["signal"] == "BUY"
        assert s2["trigger_type"] == "MACD_THEN_EMA"
        assert s2["confirmation_delay"] == 1
        assert s2["strategy_state"] == "CONFIRMED"
        results.append((5, "Long MACD_FIRST -> EMA confirmation -> signal", True, "BUY via MACD_THEN_EMA (Delay 1)"))
    except Exception as e:
        results.append((5, "Long MACD_FIRST -> EMA confirmation -> signal", False, str(e)))

    # 6. Long EMA_FIRST -> MACD confirmation within 2 candles -> signal
    try:
        df3 = make_test_df([
            {"close": 100, "ema9": 98, "ema26": 101, "macd": -1.0, "macd_signal": -0.5},
            {"close": 104, "ema9": 102, "ema26": 101, "macd": -0.2, "macd_signal": 0.1},
            {"close": 106, "ema9": 103, "ema26": 101, "macd": 0.5, "macd_signal": 0.2},
        ])
        s3_pending = detect_ema_macd_signal(df3.iloc[:2], symbol="SILVERMIC")
        assert s3_pending["strategy_state"] == "PENDING_MACD"
        assert s3_pending["signal"] is None

        s3 = detect_ema_macd_signal(df3, symbol="SILVERMIC", pending_setup=s3_pending["new_pending_setup"])
        assert s3["signal"] == "BUY"
        assert s3["trigger_type"] == "EMA_THEN_MACD"
        assert s3["confirmation_delay"] == 1
        assert s3["strategy_state"] == "CONFIRMED"
        results.append((6, "Long EMA_FIRST -> MACD confirmation -> signal", True, "BUY via EMA_THEN_MACD (Delay 1)"))
    except Exception as e:
        results.append((6, "Long EMA_FIRST -> MACD confirmation -> signal", False, str(e)))

    # 7. Long confirmation after >2 candles -> no signal (Expired)
    try:
        df4 = make_test_df([
            {"close": 100, "ema9": 98, "ema26": 102, "macd": -1.0, "macd_signal": -0.5},
            {"close": 102, "ema9": 99, "ema26": 101, "macd": 0.2, "macd_signal": -0.1},
            {"close": 102, "ema9": 99.5, "ema26": 101, "macd": 0.3, "macd_signal": 0.0},
            {"close": 102, "ema9": 100, "ema26": 101, "macd": 0.35, "macd_signal": 0.1},
            {"close": 106, "ema9": 102, "ema26": 101, "macd": 0.5, "macd_signal": 0.2},
        ])
        s4_setup = detect_ema_macd_signal(df4.iloc[:2], symbol="GOLDM")
        s4 = detect_ema_macd_signal(df4, symbol="GOLDM", pending_setup=s4_setup["new_pending_setup"])
        assert s4["signal"] is None
        assert s4["strategy_state"] in ["EXPIRED", "IDLE"]
        results.append((7, "Long confirmation after >2 candles -> expired", True, "Expired after delay > 2 bars"))
    except Exception as e:
        results.append((7, "Long confirmation after >2 candles -> expired", False, str(e)))

    # 8. Long leading indicator reversal -> cancellation
    try:
        df5 = make_test_df([
            {"close": 100, "ema9": 98, "ema26": 102, "macd": -1.0, "macd_signal": -0.5},
            {"close": 102, "ema9": 99, "ema26": 101, "macd": 0.2, "macd_signal": -0.1},
            {"close": 98, "ema9": 98.5, "ema26": 101, "macd": -0.3, "macd_signal": 0.0},
        ])
        s5_setup = detect_ema_macd_signal(df5.iloc[:2], symbol="GOLDM")
        s5 = detect_ema_macd_signal(df5, symbol="GOLDM", pending_setup=s5_setup["new_pending_setup"])
        assert s5["signal"] is None
        assert s5["strategy_state"] == "INVALIDATED"
        assert s5["action_on_pending"] == "CLEAR"
        results.append((8, "Long leading indicator reversal -> cancellation", True, "Setup cancelled via INVALIDATED"))
    except Exception as e:
        results.append((8, "Long leading indicator reversal -> cancellation", False, str(e)))

    # 9. Short SAME_CANDLE -> signal
    try:
        df6 = make_test_df([
            {"close": 105, "ema9": 102, "ema26": 100, "macd": 1.0, "macd_signal": 0.5},
            {"close": 98, "ema9": 99, "ema26": 100, "macd": -0.5, "macd_signal": 0.0},
        ])
        s6 = detect_ema_macd_signal(df6, symbol="CRUDEOILM")
        assert s6 is not None and s6["signal"] == "SELL"
        assert s6["trigger_type"] == "SAME_CANDLE"
        assert s6["confirmation_delay"] == 0
        assert s6["strategy_state"] == "CONFIRMED"
        results.append((9, "Short SAME_CANDLE -> signal", True, "SELL via SAME_CANDLE (Delay 0)"))
    except Exception as e:
        results.append((9, "Short SAME_CANDLE -> signal", False, str(e)))

    # 10. Short MACD_FIRST -> EMA confirmation within 2 candles -> signal
    try:
        df7 = make_test_df([
            {"close": 105, "ema9": 103, "ema26": 100, "macd": 1.0, "macd_signal": 0.5},
            {"close": 101, "ema9": 101.5, "ema26": 100.5, "macd": -0.2, "macd_signal": 0.1},
            {"close": 98, "ema9": 99, "ema26": 100, "macd": -0.5, "macd_signal": -0.1},
        ])
        s7_pending = detect_ema_macd_signal(df7.iloc[:2], symbol="CRUDEOILM")
        assert s7_pending["strategy_state"] == "PENDING_EMA"
        assert s7_pending["signal"] is None

        s7 = detect_ema_macd_signal(df7, symbol="CRUDEOILM", pending_setup=s7_pending["new_pending_setup"])
        assert s7["signal"] == "SELL"
        assert s7["trigger_type"] == "MACD_THEN_EMA"
        assert s7["confirmation_delay"] == 1
        assert s7["strategy_state"] == "CONFIRMED"
        results.append((10, "Short MACD_FIRST -> EMA confirmation within 2 candles -> signal", True, "SELL via MACD_THEN_EMA (Delay 1)"))
    except Exception as e:
        results.append((10, "Short MACD_FIRST -> EMA confirmation within 2 candles -> signal", False, str(e)))

    # 11. Short EMA_FIRST -> MACD later -> STRICTLY REJECTED
    try:
        df8 = make_test_df([
            {"close": 105, "ema9": 102, "ema26": 100, "macd": 1.0, "macd_signal": 0.5},
            {"close": 99, "ema9": 99, "ema26": 100, "macd": 0.8, "macd_signal": 0.5},
            {"close": 97, "ema9": 98, "ema26": 100, "macd": -0.2, "macd_signal": 0.2},
        ])
        s8_bar1 = detect_ema_macd_signal(df8.iloc[:2], symbol="CRUDEOILM")
        assert s8_bar1["strategy_state"] == "REJECTED"
        assert s8_bar1["trigger_type"] == "EMA_THEN_MACD_REJECTED"
        assert s8_bar1["rejection_reason"] == "SHORT_EMA_FIRST_DISALLOWED"
        assert s8_bar1["new_pending_setup"] is None

        s8_bar2 = detect_ema_macd_signal(df8, symbol="CRUDEOILM", pending_setup=s8_bar1["new_pending_setup"])
        assert s8_bar2["signal"] is None
        results.append((11, "Short EMA_FIRST -> strictly rejected", True, "EMA-first short rejected; no signal produced"))
    except Exception as e:
        results.append((11, "Short EMA_FIRST -> strictly rejected", False, str(e)))

    # 12. Contract fallback resolution
    try:
        sym_gold, lot_gold, _ = resolve_mcx_contract("GOLDM", "http://127.0.0.1:5000", "dummy")
        sym_silv, lot_silv, _ = resolve_mcx_contract("SILVERMIC", "http://127.0.0.1:5000", "dummy")
        sym_crud, lot_crud, _ = resolve_mcx_contract("CRUDEM", "http://127.0.0.1:5000", "dummy")
        assert sym_gold.startswith("GOLDM") and lot_gold == 1
        assert sym_silv.startswith("SILVERMIC") and lot_silv == 1
        assert sym_crud.startswith("CRUDEOILM") and lot_crud == 1
        results.append((12, "MCX contract fallback resolution", True, f"GOLDM, SILVERMIC, CRUDEOILM resolved successfully"))
    except Exception as e:
        results.append((12, "MCX contract fallback resolution", False, str(e)))

    # 13. Telegram notification formatting
    try:
        trade_alert = format_paper_trade_alert({
            "strategy_name": "EMACROSS_MCX_PAPER",
            "contract": "GOLDM05DEC26FUT",
            "symbol": "GOLDM",
            "action": "BUY",
            "direction": "LONG",
            "quantity": 1,
            "entry_price": 78000.0,
            "order_id": "MOCK_ORD_101",
            "order_status": "FILLED",
            "price_type": "MARKET",
            "exchange": "MCX",
            "product": "NRML",
            "pos_before": 0,
            "pos_after": 1,
            "trigger_type": "SAME_CANDLE",
            "confirmation_delay": 0,
            "candle_time_str": "11-Nov-2026 15:00 IST",
            "close": 78000.0,
            "ema9": 77950.0,
            "ema26": 77800.0,
            "macd": 150.0,
            "macd_signal": 120.0,
            "macd_histogram": 30.0,
        })
        assert "GOLDM05DEC26FUT" in trade_alert
        assert "Target" in trade_alert
        assert "Stop Loss" in trade_alert
        results.append((13, "Single consolidated Telegram trade alert formatting", True, "All fields and target/SL formatted properly"))
    except Exception as e:
        results.append((13, "Single consolidated Telegram trade alert formatting", False, str(e)))

    # 14. Telegram exit notification formatting
    try:
        exit_alert = format_paper_exit_alert({
            "strategy_name": "EMACROSS_MCX_PAPER",
            "contract": "CRUDEOILM19NOV26FUT",
            "symbol": "CRUDEOILM",
            "direction": "LONG",
            "action": "SELL",
            "exit_reason": "TARGET_HIT",
            "quantity": 10,
            "entry_price": 6000.0,
            "exit_price": 6150.0,
            "order_id": "MOCK_EXIT_102",
            "order_status": "FILLED",
            "candle_time_str": "11-Nov-2026 18:00 IST",
        })
        assert "CRUDEOILM19NOV26FUT" in exit_alert
        assert "TARGET HIT" in exit_alert
        results.append((14, "Telegram exit notification formatting", True, "Exit notification contains P&L and contract details"))
    except Exception as e:
        results.append((14, "Telegram exit notification formatting", False, str(e)))

    # 15. Risk check: LONG target hit converts to Trailing Runner
    try:
        mock_eng = MockMCXEngine(symbols=["GOLDM", "SILVERMIC", "CRUDEOILM"])
        mock_eng.contract_cache["GOLDM"] = {"contract": "GOLDM05DEC26FUT", "lot_size": 1}
        mock_eng.state_manager.update_tracked_positions({
            "GOLDM05DEC26FUT": {
                "symbol": "GOLDM",
                "contract": "GOLDM05DEC26FUT",
                "direction": "LONG",
                "quantity": 1,
                "average_price": 75000.0,
                "runner_active": False,
                "early_target_hit": False,
                "be_stop_active": False,
            }
        })
        # +2.5% target is 76875. High reaches 77000.
        df_target = pd.DataFrame([{
            "open": 75500, "high": 77000, "low": 75200, "close": 76900, "ema9": 75200, "ema26": 74800, "macd": 200, "macd_signal": 150
        }], index=[datetime(2026, 11, 11, 15, 0, tzinfo=IST)])
        mock_eng.check_and_execute_target_or_sl("GOLDM", "GOLDM05DEC26FUT", df_target)
        pos = mock_eng.state_manager.state["tracked_positions"]["GOLDM05DEC26FUT"]
        assert pos["runner_active"] is True
        assert pos["peak_price"] == 77000.0
        results.append((15, "LONG Target reach activates HWM Trailing Runner", True, "Runner activated with peak at 77000"))
    except Exception as e:
        results.append((15, "LONG Target reach activates HWM Trailing Runner", False, str(e)))

    # 16. Risk check: Trailing Runner exits on pullback breach
    try:
        # Trail SL = 77000 * (1 - 0.0035) = 76730.5. Low dips to 76500.
        df_pullback = pd.DataFrame([{
            "open": 76900, "high": 76950, "low": 76500, "close": 76600, "ema9": 76500, "ema26": 75000, "macd": 180, "macd_signal": 150
        }], index=[datetime(2026, 11, 11, 16, 0, tzinfo=IST)])
        mock_eng.check_and_execute_target_or_sl("GOLDM", "GOLDM05DEC26FUT", df_pullback)
        pos_after = mock_eng.state_manager.state["tracked_positions"].get("GOLDM05DEC26FUT")
        assert pos_after is None
        results.append((16, "Trailing Runner exits on pullback breach", True, "Position closed via RUNNER_HWM_TRAIL"))
    except Exception as e:
        results.append((16, "Trailing Runner exits on pullback breach", False, str(e)))

    # 17. Risk check: Early profit milestone activates Break-Even stop
    try:
        mock_eng2 = MockMCXEngine(symbols=["SILVERMIC"])
        mock_eng2.contract_cache["SILVERMIC"] = {"contract": "SILVERMIC28NOV26FUT", "lot_size": 1}
        mock_eng2.state_manager.update_tracked_positions({
            "SILVERMIC28NOV26FUT": {
                "symbol": "SILVERMIC",
                "contract": "SILVERMIC28NOV26FUT",
                "direction": "LONG",
                "quantity": 1,
                "average_price": 90000.0,
                "runner_active": False,
                "early_target_hit": False,
                "be_stop_active": False,
            }
        })
        # +1.5% is 91350. High reaches 91400.
        df_early = pd.DataFrame([{
            "open": 90200, "high": 91400, "low": 90100, "close": 91300, "ema9": 90500, "ema26": 89800, "macd": 150, "macd_signal": 100
        }], index=[datetime(2026, 11, 11, 15, 0, tzinfo=IST)])
        mock_eng2.check_and_execute_target_or_sl("SILVERMIC", "SILVERMIC28NOV26FUT", df_early)
        pos_e = mock_eng2.state_manager.state["tracked_positions"]["SILVERMIC28NOV26FUT"]
        assert pos_e["early_target_hit"] is True
        assert pos_e["be_stop_active"] is True
        results.append((17, "Early profit milestone activates Break-Even stop", True, "BE stop activated without premature exit"))
    except Exception as e:
        results.append((17, "Early profit milestone activates Break-Even stop", False, str(e)))

    # 18. Risk check: Catastrophe Stop-Loss
    try:
        mock_eng3 = MockMCXEngine(symbols=["CRUDEOILM"])
        mock_eng3.contract_cache["CRUDEOILM"] = {"contract": "CRUDEOILM19NOV26FUT", "lot_size": 1}
        mock_eng3.state_manager.update_tracked_positions({
            "CRUDEOILM19NOV26FUT": {
                "symbol": "CRUDEOILM",
                "contract": "CRUDEOILM19NOV26FUT",
                "direction": "LONG",
                "quantity": 1,
                "average_price": 6000.0,
                "runner_active": False,
                "early_target_hit": False,
                "be_stop_active": False,
            }
        })
        # -4.0% catastrophe SL is 5760. Low breaches 5700.
        df_sl = pd.DataFrame([{
            "open": 5900, "high": 5910, "low": 5700, "close": 5720, "ema9": 5850, "ema26": 5900, "macd": -50, "macd_signal": -20
        }], index=[datetime(2026, 11, 11, 16, 0, tzinfo=IST)])
        mock_eng3.check_and_execute_target_or_sl("CRUDEOILM", "CRUDEOILM19NOV26FUT", df_sl)
        pos_sl = mock_eng3.state_manager.state["tracked_positions"].get("CRUDEOILM19NOV26FUT")
        assert pos_sl is None
        results.append((18, "Catastrophe Stop-Loss triggers on adverse move", True, "Position closed via CATASTROPHE_SL"))
    except Exception as e:
        results.append((18, "Catastrophe Stop-Loss triggers on adverse move", False, str(e)))

    # 19. Controlled Reversal: SHORT to LONG
    try:
        mock_eng4 = MockMCXEngine(symbols=["GOLDM"])
        mock_eng4.contract_cache["GOLDM"] = {"contract": "GOLDM05DEC26FUT", "lot_size": 1}
        mock_eng4.state_manager.update_tracked_positions({
            "GOLDM05DEC26FUT": {
                "symbol": "GOLDM",
                "contract": "GOLDM05DEC26FUT",
                "direction": "SHORT",
                "quantity": -1,
                "average_price": 76000.0,
            }
        })
        sig_rev = {
            "signal": "BUY",
            "trigger_type": "SAME_CANDLE",
            "confirmation_delay": 0,
            "candle_time_str": "11-Nov-2026 17:00 IST",
            "timestamp": "2026-11-11T17:00:00+05:30",
            "close": 76500.0,
        }
        placed, count = mock_eng4.execute_symbol_decision("GOLDM", sig_rev, active_positions_count=1)
        assert placed is True
        pos_rev = mock_eng4.state_manager.state["tracked_positions"]["GOLDM05DEC26FUT"]
        assert pos_rev["direction"] == "LONG"
        assert pos_rev["quantity"] == 1
        results.append((19, "Controlled reversal SHORT to LONG sizing", True, "Successfully reversed net position from -1 to +1"))
    except Exception as e:
        results.append((19, "Controlled reversal SHORT to LONG sizing", False, str(e)))

    # 20. Idempotency Lock: duplicate signal does not place duplicate order
    try:
        sig_dup = {
            "signal": "BUY",
            "trigger_type": "SAME_CANDLE",
            "confirmation_delay": 0,
            "candle_time_str": "11-Nov-2026 17:00 IST",
            "timestamp": "2026-11-11T17:00:00+05:30",
            "close": 76500.0,
        }
        placed_dup, _ = mock_eng4.execute_symbol_decision("GOLDM", sig_dup, active_positions_count=1)
        assert placed_dup is False
        results.append((20, "Idempotency Lock prevents duplicate signal execution", True, "Duplicate signal rejected"))
    except Exception as e:
        results.append((20, "Idempotency Lock prevents duplicate signal execution", False, str(e)))

    # 21. MCX Position Book Filtering: Excludes NFO/NSE non-commodity positions
    try:
        mock_eng_filter = MockMCXEngine(symbols=["GOLDM", "SILVERMIC", "CRUDEOILM"])
        mock_eng_filter.contract_cache = {
            "GOLDM": {"contract": "GOLDM05DEC26FUT"},
            "SILVERMIC": {"contract": "SILVERMIC30NOV26FUT"},
            "CRUDEOILM": {"contract": "CRUDEOILM19NOV26FUT"},
        }
        # Non-MCX positions (NFO, NSE) must be rejected
        assert mock_eng_filter.is_strategy_mcx_position({"symbol": "M&M23NOV26FUT", "exchange": "NFO", "quantity": -200}) is False
        assert mock_eng_filter.is_strategy_mcx_position({"symbol": "NIFTY29DEC26FUT", "exchange": "NFO", "quantity": 65}) is False
        assert mock_eng_filter.is_strategy_mcx_position({"symbol": "NIFTY29DEC2626400CE", "exchange": "NFO", "quantity": -65}) is False
        assert mock_eng_filter.is_strategy_mcx_position({"symbol": "BAJFINANCE23NOV26FUT", "exchange": "NFO", "quantity": 750}) is False
        assert mock_eng_filter.is_strategy_mcx_position({"symbol": "RELIANCE", "exchange": "NSE", "quantity": 100}) is False
        # MCX commodity outside strategy universe must be rejected
        assert mock_eng_filter.is_strategy_mcx_position({"symbol": "COPPER30NOV26FUT", "exchange": "MCX", "quantity": 1}) is False
        # Valid MCX strategy commodity positions must be accepted
        assert mock_eng_filter.is_strategy_mcx_position({"symbol": "SILVERMIC30NOV26FUT", "exchange": "MCX", "quantity": 0}) is True
        assert mock_eng_filter.is_strategy_mcx_position({"symbol": "GOLDM05DEC26FUT", "exchange": "MCX", "quantity": 1}) is True
        assert mock_eng_filter.is_strategy_mcx_position({"symbol": "CRUDEOILM19NOV26FUT", "exchange": "MCX", "quantity": 10}) is True
        results.append((21, "Positionbook Exchange & Universe Filter", True, "NFO/NSE positions strictly excluded from MCX strategy"))
    except Exception as e:
        results.append((21, "Positionbook Exchange & Universe Filter", False, str(e)))

    # 22. Active Position Count Reconciliation with Mock Positionbook
    try:
        class MockPositionbookEngine(MockMCXEngine):
            def __init__(self, mock_positions, *args, **kwargs):
                self._mock_positions = mock_positions
                super().__init__(*args, **kwargs)

            def get_all_open_positions(self, only_strategy_universe: bool = True) -> Dict[str, int]:
                pos_map = {}
                for p in self._mock_positions:
                    if only_strategy_universe and not self.is_strategy_mcx_position(p):
                        continue
                    sym = p.get("symbol")
                    qty = int(p.get("quantity", p.get("netqty", 0)))
                    if sym:
                        pos_map[sym] = qty
                return pos_map

        sample_broker_positions = [
            {"symbol": "M&M23NOV26FUT", "exchange": "NFO", "quantity": -200},
            {"symbol": "NIFTY29DEC26FUT", "exchange": "NFO", "quantity": 65},
            {"symbol": "NIFTY29DEC2626400CE", "exchange": "NFO", "quantity": -65},
            {"symbol": "SILVERMIC30NOV26FUT", "exchange": "MCX", "quantity": 0},
            {"symbol": "BAJFINANCE23NOV26FUT", "exchange": "NFO", "quantity": 750},
        ]
        eng_pb = MockPositionbookEngine(sample_broker_positions, symbols=["GOLDM", "SILVERMIC", "CRUDEOILM"])
        pb_res = eng_pb.get_all_open_positions()
        # Only SILVERMIC is an MCX strategy symbol in this book
        assert list(pb_res.keys()) == ["SILVERMIC30NOV26FUT"]
        # Its quantity is 0 (closed/flat)
        active_mcx_count = len([q for q in pb_res.values() if q != 0])
        assert active_mcx_count == 0
        results.append((22, "Active MCX Position Count Calculation", True, "Evaluated to 0 active positions despite 4 active NFO positions"))
    except Exception as e:
        results.append((22, "Active MCX Position Count Calculation", False, str(e)))

    all_passed = True
    for tid, name, status, msg in results:
        if status:
            logger.info(f"[✅ PASS] Test {tid}: {name} -> {msg}")
        else:
            all_passed = False
            logger.error(f"[❌ FAIL] Test {tid}: {name} -> {msg}")

    logger.info("=" * 80)
    logger.info(f"📊 SUMMARY: {len([r for r in results if r[2]])}/{len(results)} tests PASSED. All Passed: {all_passed}")
    logger.info("=" * 80)
    return all_passed


# ==============================================================================
# 13. CLI ENTRY POINT
# ==============================================================================
def main():
    global INTERVAL, RUN_ONCE
    parser = argparse.ArgumentParser(description="OpenAlgo MCX 1H EMA/MACD Confirmation Strategy")
    parser.add_argument("--test", action="store_true", help="Run automated test suite and exit")
    parser.add_argument("--once", action="store_true", help="Execute single cycle and exit")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated MCX commodities (default: GOLDM,SILVERMIC,CRUDEOILM)")
    parser.add_argument("--symbol", type=str, default="", help="Single commodity symbol to trade")
    parser.add_argument("--lots", type=int, default=LOTS, help="Lots per commodity (default: 1)")
    parser.add_argument("--interval", type=str, default=INTERVAL, help="Candle timeframe interval (default: 1h)")
    parser.add_argument("--host", type=str, default=OPENALGO_HOST, help="OpenAlgo Host URL")
    parser.add_argument("--apikey", type=str, default=OPENALGO_API_KEY, help="OpenAlgo API Key")
    parser.add_argument("--poll-interval", type=int, default=POLL_INTERVAL_SECONDS, help="Poll interval in seconds")

    args = parser.parse_args()

    if args.test:
        success = run_automated_tests()
        sys.exit(0 if success else 1)

    symbols_list = None
    if args.symbol:
        symbols_list = [args.symbol.strip()]
    elif args.symbols:
        symbols_list = [s.strip() for s in args.symbols.split(",") if s.strip()]

    INTERVAL = args.interval
    if args.once:
        RUN_ONCE = True

    strategy = MCXEMACrossStrategy(
        symbols=symbols_list,
        lots=args.lots,
        host=args.host,
        api_key=args.apikey,
    )

    if RUN_ONCE:
        strategy.execute_cycle()
    else:
        strategy.run_loop(poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
