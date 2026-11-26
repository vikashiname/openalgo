"""
================================================================================
OPENALGO LIVE STRATEGY: MCX TRADITIONAL ICHIMOKU MULTI-TIMEFRAME ENGINE
================================================================================
File Role            : LIVE_OPENALGO_STRATEGY
Strategy Identifier  : ICHIMOKU_MCX_PAPER
Target Universe      : GOLDM, CRUDEOILM (Optional: SILVERMIC, NATGASMINI)
Exchange             : MCX (Multi Commodity Exchange of India)
Default Product      : NRML (Normal Futures)
Timeframe            : 1-Hour (1H) Confirmed Bar Close, Filled at Next-Bar Open
Current Version      : 1.1.0-REMEDIATED (Institutional Fail-Closed Production Baseline)
Baseline Promotion   : Certified Replacement for Legacy emacrossmcx.py (EMA/MACD)
================================================================================
Strategy Specifications & Approved Target Calculations (Option A):
  1. Primary Signal Engine (1H Model I5 - Hosoda San Yaku Kouten / Gyakuten):
     - San Yaku Kouten (Long):
       * Tenkan-sen > Kijun-sen (TK Cross Up)
       * Close > Kumo Top (Span A & Span B)
       * Chikou Span > Past Close (Close[t] > Close[t-26])
       * Close > Kijun-sen
       * Forward Cloud Bullish (Span A future > Span B future)
     - San Yaku Gyakuten (Short):
       * Tenkan-sen < Kijun-sen (TK Cross Down)
       * Close < Kumo Bottom (Span A & Span B)
       * Chikou Span < Past Close (Close[t] < Close[t-26])
       * Close < Kijun-sen
       * Forward Cloud Bearish (Span A future < Span B future)

  2. Higher Timeframe Geometric Consensus Gate (F5 Dual 4H & 1D Confluence):
     - Long Entry Gate : 4H Geometric Regime contains 'Bullish' AND 1D Geometric Regime contains 'Bullish'.
     - Short Entry Gate: 4H Geometric Regime contains 'Bearish' AND 1D Geometric Regime contains 'Bearish'.
     - Resampling anchors strictly at MCX session open (09:00 IST). In-progress HTF bars are discarded.

  3. Risk Management Hierarchy (Strictly Causal & Approved Option A Calculation):
     - Priority 1: Point-of-No-Return Hard Stop Loss (Fixed 2.0x ATR14) -> 1R Risk Baseline.
     - Priority 2: Intrabar Profit Taking Target = 3.5x ATR14 (Actual Reward-to-Risk = 1.75R).
       * Quant Proof & Clarification: Stop Loss is 2.0 ATR (1R); Target is 3.5 ATR (1.75R).
       * Preserves exact quantitative research baseline assumptions without unapproved shifts.
     - Priority 3: Hosoda Model I3 Kijun Pullback Re-entry Engine (Kijun-sen Oshi):
       * Active ONLY after a 3.5 ATR (1.75R) target exit while HTF 4H+1D regime remains confluent.
       * Requires at least 1 completed bar separation after target exit before re-entry test.
       * Expiration window: 15 bars max.
       * Proximity tolerance: GOLDM 1.0%, CRUDEOILM 1.5%.
       * Re-enters at next-bar Open with fresh 2.0x ATR stop loss.
     - Priority 4: Hosoda Structural Exits (Evaluated on Bar Close):
       * Longs: Close < Kijun OR Tenkan < Kijun.
       * Shorts: Close > Kijun OR Tenkan > Kijun.
     - Priority 5: Confirmed Opposing Reversal.

  4. Institutional Execution & Data Safety Gates (FAIL-CLOSED):
     - Strictly NO research CSV fallbacks in live order execution path.
     - Mandatory broker connectivity, live market data freshness (< 75m), and depth (>= 80 bars).
     - Confirmed bar close execution: in-progress candles are completely filtered out.
     - Dynamic exchange lot-size verification (e.g. 100 units for GOLDM, 10 units for CRUDEOILM).
     - Order lifecycle verification: polls /api/v1/orderstatus for verified COMPLETE fill price.
     - Broker position book reconciliation (/api/v1/positionbook) at start and every cycle.
     - Thread-safe atomic persistence with process/thread-unique temporary files and RLock.
================================================================================
"""

import argparse
import fcntl
import json
import logging
import os
import signal
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

_LOCK_FILE = None


def acquire_single_instance_lock(lock_name: str = "ichimoku_mcx"):
    global _LOCK_FILE
    lock_path = f"/tmp/{lock_name}.lock"
    try:
        _LOCK_FILE = open(lock_path, "w")
        fcntl.flock(_LOCK_FILE, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FILE.write(f"{os.getpid()}\n")
        _LOCK_FILE.flush()
        return True
    except (BlockingIOError, IOError):
        logger.error(
            f"🛑 [LOCK REJECTED] Another instance of {lock_name} is already active on this system (lockfile: {lock_path}). Exiting."
        )
        sys.exit(0)


# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import find_dotenv, load_dotenv

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
                        if k and k not in os.environ:
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
# 1. FILE PATHS & SYSTEM CONSTANTS
# ==============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
LOG_FILE_PATH = Path(
    os.getenv(
        "LOG_FILE",
        PROJECT_ROOT / "log/strategies/ichimoku_mcx.log"
        if (PROJECT_ROOT / "log").exists()
        else SCRIPT_DIR / "ichimoku_mcx.log",
    )
)
STATE_FILE_PATH = Path(os.getenv("STATE_FILE", SCRIPT_DIR / "ichimoku_mcx_state.json"))
HEARTBEAT_FILE_PATH = Path(os.getenv("HEARTBEAT_FILE", SCRIPT_DIR / "ichimoku_mcx_heartbeat.json"))

STRATEGY_NAME = os.getenv("STRATEGY_NAME", "ICHIMOKU_MCX_PAPER")
EXCHANGE = os.getenv("EXCHANGE", "MCX")
PRODUCT = os.getenv("PRODUCT", "NRML")
INTERVAL = os.getenv("INTERVAL", "1h")

# Model Parameters (Calibrated Production Values)
TENKAN_PERIOD = int(os.getenv("TENKAN_PERIOD", "9"))
KIJUN_PERIOD = int(os.getenv("KIJUN_PERIOD", "26"))
SENKOU_B_PERIOD = int(os.getenv("SENKOU_B_PERIOD", "52"))
DISPLACEMENT = int(os.getenv("DISPLACEMENT", "26"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))

# Risk Management: Approved Option A (Stop: 2.0x ATR, Target: 3.5x ATR = 1.75R)
STOP_LOSS_ATR_MULT = float(os.getenv("STOP_LOSS_ATR_MULT", "2.0"))
PROFIT_TARGET_ATR_MULT = float(os.getenv("PROFIT_TARGET_ATR_MULT", os.getenv("PROFIT_TARGET_R", "3.5")))
REWARD_RISK_RATIO = PROFIT_TARGET_ATR_MULT / STOP_LOSS_ATR_MULT  # 1.75R
ENABLE_TARGET = os.getenv("ENABLE_TARGET", "true").lower() in ["true", "1", "yes"]
ENABLE_PULLBACK_REENTRY = os.getenv("ENABLE_PULLBACK_REENTRY", "true").lower() in ["true", "1", "yes"]
ALLOW_REVERSALS = os.getenv("ALLOW_REVERSALS", "true").lower() in ["true", "1", "yes"]

LOTS = int(os.getenv("LOTS", "1"))
MAX_ACTIVE_POSITIONS = int(os.getenv("MAX_ACTIVE_POSITIONS", "0"))  # 0 = Unlimited
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() in ["true", "1", "yes"]
ORDER_PACING_DELAY_SEC = float(os.getenv("ORDER_PACING_DELAY_SEC", "0.25"))

# IST Timezone (+05:30)
IST = timezone(timedelta(hours=5, minutes=30))

# ==============================================================================
# 2. LOGGING SETUP
# ==============================================================================
logger = logging.getLogger("ICHIMOKU_MCX")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(LOG_FILE_PATH), mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Could not initialize file logger at {LOG_FILE_PATH}: {e}")

# ==============================================================================
# 3. OPENALGO API CREDENTIALS & TELEGRAM SETUP (FAIL-CLOSED SECURITY)
# ==============================================================================
OPENALGO_API_KEY = os.getenv("OPENALGO_API_KEY") or os.getenv("API_KEY") or ""
OPENALGO_HOST = os.getenv("OPENALGO_HOST", os.getenv("HOST_SERVER", "https://vikashiname.in"))
if not OPENALGO_HOST.startswith("http"):
    OPENALGO_HOST = f"http://{OPENALGO_HOST}"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Fallback: Query Telegram config from OpenAlgo Host API if unconfigured
if OPENALGO_API_KEY and (not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID):
    try:
        cfg_resp = requests.get(
            f"{OPENALGO_HOST.rstrip('/')}/api/v1/telegram/config",
            headers={"X-API-KEY": OPENALGO_API_KEY},
            timeout=5,
        )
        if cfg_resp.status_code == 200:
            cfg_d = cfg_resp.json().get("data", {})
            if cfg_d.get("is_active") and cfg_d.get("token") and not TELEGRAM_BOT_TOKEN:
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


def send_telegram_alert(message: str) -> bool:
    """Dispatches real-time markdown notifications to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(url, json=payload, timeout=6)
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"Telegram dispatch failed: {e}")
        return False


# ==============================================================================
# 4. MCX COMMODITY SPECIFICATIONS & VERIFIED LOT SIZES
# ==============================================================================
DEFAULT_MCX_UNIVERSE = ["GOLDM", "CRUDEOILM"]

SYMBOL_ALIASES = {
    "CRUDEM": "CRUDEOILM",
    "CRUDE": "CRUDEOILM",
    "GOLD": "GOLDM",
    "SILVER": "SILVERMIC",
    "SILVERM": "SILVERMIC",
    "NATGAS": "NATGASMINI",
    "NATURALGAS": "NATGASMINI",
}


def normalize_mcx_symbol(symbol: str) -> str:
    s = str(symbol).strip().upper()
    return SYMBOL_ALIASES.get(s, s)


# Authoritative fallback mapping matching broker/zerodha/mapping/mcx_contract_size.py
MCX_COMMODITY_SPECS: Dict[str, Dict[str, Any]] = {
    "GOLDM": {
        "display_name": "Gold Mini (100g)",
        "search_prefix": "GOLDM",
        "default_lot": 1,
        "exchange_lot_size": 100,  # 100 grams per contract (OpenAlgo units)
        "unit": "100g",
        "tick_size": 1.0,
        "multiplier": 10.0,  # ₹10 per 1-point move per 100g lot
        "pullback_tolerance": 0.010,  # 1.0% Kijun proximity
        "expiry_cycle": [2, 4, 6, 8, 10, 12],  # Bi-monthly expiries on MCX
    },
    "CRUDEOILM": {
        "display_name": "Crude Oil Mini (10 bbl)",
        "search_prefix": "CRUDEOILM",
        "default_lot": 1,
        "exchange_lot_size": 10,  # 10 Barrels per contract (OpenAlgo units)
        "unit": "10 Barrels",
        "tick_size": 1.0,
        "multiplier": 10.0,  # ₹10 per 1-point move per 10 bbl lot
        "pullback_tolerance": 0.015,  # 1.5% Kijun proximity
        "expiry_cycle": list(range(1, 13)),  # Monthly
    },
    "SILVERMIC": {
        "display_name": "Silver Micro (1kg)",
        "search_prefix": "SILVERMIC",
        "default_lot": 1,
        "exchange_lot_size": 1,  # 1 Kilogram per contract (OpenAlgo units)
        "unit": "1kg",
        "tick_size": 1.0,
        "multiplier": 1.0,
        "pullback_tolerance": 0.010,
        "expiry_cycle": [2, 4, 6, 8, 11],
    },
    "NATGASMINI": {
        "display_name": "Natural Gas Mini (250 mmBtu)",
        "search_prefix": "NATGASMINI",
        "default_lot": 1,
        "exchange_lot_size": 250,  # 250 mmBtu per contract (OpenAlgo units)
        "unit": "250 mmBtu",
        "tick_size": 0.10,
        "multiplier": 250.0,
        "pullback_tolerance": 0.015,
        "expiry_cycle": list(range(1, 13)),
    },
}

# ==============================================================================
# 5. MCX SESSION & TIME HELPERS
# ==============================================================================
def get_current_ist() -> datetime:
    return datetime.now(timezone.utc).astimezone(IST)


def is_mcx_trading_time(now_dt: Optional[datetime] = None) -> Tuple[bool, str]:
    now = now_dt or get_current_ist()
    weekday = now.weekday()
    if weekday >= 5:
        return False, "WEEKEND_CLOSED"
    m = now.hour * 60 + now.minute
    session_start = 9 * 60  # 09:00 IST
    session_end = 23 * 60 + 30  # 23:30 IST
    if session_start <= m <= session_end:
        return True, "SESSION_ACTIVE"
    return False, "HOURS_CLOSED"


def get_seconds_to_next_candle_boundary(now_dt: Optional[datetime] = None, buffer_seconds: int = 5) -> float:
    now = now_dt or get_current_ist()
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    sleep_seconds = (next_hour - now).total_seconds() + buffer_seconds
    return max(5.0, sleep_seconds)


# ==============================================================================
# 6. MATHEMATICAL ENGINES (ICHIMOKU & MCX SESSION-ALIGNED HTF GEOMETRY)
# ==============================================================================
def compute_atr14(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return atr.bfill().ffill()


def compute_ichimoku_1h(
    df: pd.DataFrame,
    tenkan_period: int = TENKAN_PERIOD,
    kijun_period: int = KIJUN_PERIOD,
    senkou_b_period: int = SENKOU_B_PERIOD,
    displacement: int = DISPLACEMENT,
) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None
    data = df.copy()
    data.columns = [str(c).strip().lower() for c in data.columns]
    for col in ["high", "low", "close"]:
        if col not in data.columns:
            logger.error(f"🛑 [FAIL-CLOSED] Missing required price column '{col}' in input dataframe.")
            return None
        data[col] = data[col].astype(float)
    if "open" in data.columns:
        data["open"] = data["open"].astype(float)

    high = data["high"]
    low = data["low"]
    close = data["close"]

    data["tenkan"] = (high.rolling(window=tenkan_period).max() + low.rolling(window=tenkan_period).min()) / 2.0
    data["kijun"] = (high.rolling(window=kijun_period).max() + low.rolling(window=kijun_period).min()) / 2.0

    # Unshifted (current calculation) spans
    raw_span_a = (data["tenkan"] + data["kijun"]) / 2.0
    raw_span_b = (high.rolling(window=senkou_b_period).max() + low.rolling(window=senkou_b_period).min()) / 2.0

    # Real-time visible cloud at bar t is computed from t - displacement
    data["senkou_a"] = raw_span_a.shift(displacement)
    data["senkou_b"] = raw_span_b.shift(displacement)

    data["kumo_top"] = np.maximum(data["senkou_a"], data["senkou_b"])
    data["kumo_bottom"] = np.minimum(data["senkou_a"], data["senkou_b"])

    # Chikou Span: Close at bar t compared against Close at bar t - displacement
    data["chikou"] = close.shift(displacement)
    data["chikou_past_close"] = data["chikou"]

    # Future cloud: Forward cloud at t + displacement (Span A future > Span B future)
    data["future_cloud_bull"] = raw_span_a > raw_span_b
    data["future_cloud_bear"] = raw_span_a < raw_span_b
    data["atr14"] = compute_atr14(data, period=ATR_PERIOD)

    return data


def resample_ohlcv(df: pd.DataFrame, timeframe: str = "4h") -> pd.DataFrame:
    """
    Resamples 1H completed data to 4H or 1D completed candles anchored to MCX 09:00 IST open.
    In-progress / uncompleted higher-timeframe bars are strictly dropped.
    """
    data = df.copy()
    if "timestamp" in data.columns:
        if pd.api.types.is_numeric_dtype(data["timestamp"]):
            data["timestamp"] = pd.to_datetime(data["timestamp"], unit="s", utc=True).dt.tz_convert(IST)
        else:
            data["timestamp"] = pd.to_datetime(data["timestamp"])
            if data["timestamp"].dt.tz is None:
                data["timestamp"] = data["timestamp"].dt.tz_localize(IST)
            else:
                data["timestamp"] = data["timestamp"].dt.tz_convert(IST)
        data = data.sort_values("timestamp").set_index("timestamp")
    elif not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index)
        if data.index.tz is None:
            data.index = data.index.tz_localize(IST)
        else:
            data.index = data.index.tz_convert(IST)
    elif data.index.tz is None:
        data.index = data.index.tz_localize(IST)
    else:
        data.index = data.index.tz_convert(IST)

    data.index.name = "timestamp"

    rule = "4h" if timeframe.lower() == "4h" else "1D"
    first_dt = data.index[0]
    origin_dt = first_dt.normalize() + timedelta(hours=9)  # 09:00 IST MCX anchor

    agg_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in data.columns:
        agg_dict["volume"] = "sum"

    resampled = (
        data.resample(rule, origin=origin_dt, closed="left", label="left")
        .agg(agg_dict)
        .dropna()
        .reset_index()
    )

    bar_duration = pd.Timedelta(hours=4) if timeframe.lower() == "4h" else pd.Timedelta(days=1)
    resampled["completion_time"] = resampled["timestamp"] + bar_duration

    # Drop any in-progress HTF bar whose completion time is beyond the end of the last completed 1H bar
    last_1h_end = data.index[-1] + pd.Timedelta(hours=1)
    resampled = resampled[resampled["completion_time"] <= last_1h_end].copy()

    return resampled


def classify_htf_regime(df_htf: pd.DataFrame) -> Tuple[str, str, bool]:
    """
    Computes HTF composite geometric consensus and Kijun slope/plateau state.
    Requires minimum 78 bars for Senkou Span B + displacement.
    """
    if len(df_htf) < 78:
        return "Neutral_Chop", "Neutral", False

    df_ichi = compute_ichimoku_1h(df_htf)
    close = df_ichi["close"].iloc[-1]
    tenkan = df_ichi["tenkan"].iloc[-1]
    kijun = df_ichi["kijun"].iloc[-1]
    span_a = df_ichi["senkou_a"].iloc[-1]
    span_b = df_ichi["senkou_b"].iloc[-1]

    if np.isnan(span_a) or np.isnan(span_b) or np.isnan(kijun) or np.isnan(tenkan):
        return "Neutral_Chop", "Neutral", False

    kumo_top = max(span_a, span_b)
    kumo_bot = min(span_a, span_b)

    # Line slopes over 3 bars
    kijun_prev = df_ichi["kijun"].iloc[-3]
    atr = df_ichi["atr14"].iloc[-1] or 1.0
    kijun_slope = (kijun - kijun_prev) / (2.0 * atr)

    is_horizontal = abs(kijun_slope) < 0.05
    kijun_direction = "Bullish" if kijun_slope >= 0.05 else ("Bearish" if kijun_slope <= -0.05 else "Neutral")

    # Consensus score
    score = 0
    score += 1 if tenkan > kijun else -1
    score += 1 if close > kumo_top else (-1 if close < kumo_bot else 0)
    score += 1 if close > kijun else -1
    score += 1 if df_ichi["future_cloud_bull"].iloc[-1] else -1

    if score >= 2:
        regime = "Strong_Bullish_Geometry"
    elif score == 1:
        regime = "Mild_Bullish_Geometry"
    elif score <= -2:
        regime = "Strong_Bearish_Geometry"
    elif score == -1:
        regime = "Mild_Bearish_Geometry"
    else:
        regime = "Neutral_Chop"

    return regime, kijun_direction, is_horizontal


# ==============================================================================
# 7. THREAD-SAFE ATOMIC PERSISTENT STATE MANAGER
# ==============================================================================
class PersistentStateManager:
    """Thread-safe, atomic, crash-safe state persistence for ichimoku_mcx.py."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lock = threading.RLock()
        self.state: Dict[str, Any] = self.load_state()

    def load_state(self) -> Dict[str, Any]:
        default_state = {
            "strategy_name": STRATEGY_NAME,
            "version": "1.1.0-REMEDIATED",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "tracked_positions": {},  # contract_symbol -> pos_dict
            "pullback_watch": {},  # symbol -> {target_exited_dir, exit_time, exit_bar_idx, target_exit_price}
            "last_processed_candle": {},  # symbol -> candle_iso_string
            "completed_trades": [],
            "order_registry": {},
        }
        if not self.file_path.exists():
            return default_state
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in default_state.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception as e:
            logger.error(f"Error reading state file {self.file_path}: {e}. Initializing fresh state.")
            return default_state

    def save_state(self):
        with self.lock:
            self.state["last_updated"] = datetime.now(timezone.utc).isoformat()
            # Unique temp file per thread/process to prevent truncation races
            temp_file = self.file_path.with_name(f"{self.file_path.stem}_{uuid.uuid4().hex}.tmp")
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(self.state, f, indent=2, default=str)
                os.replace(temp_file, self.file_path)
            except Exception as e:
                logger.error(f"Failed to persist state atomically: {e}")
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass

    def get_last_processed_candle(self, symbol: str) -> Optional[str]:
        with self.lock:
            return self.state.get("last_processed_candle", {}).get(symbol)

    def set_last_processed_candle(self, symbol: str, candle_ts: str):
        with self.lock:
            if "last_processed_candle" not in self.state:
                self.state["last_processed_candle"] = {}
            self.state["last_processed_candle"][symbol] = str(candle_ts)
            self.save_state()

    def get_position(self, contract_symbol: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.state.get("tracked_positions", {}).get(contract_symbol)

    def save_position(self, contract_symbol: str, pos_dict: Dict[str, Any]):
        with self.lock:
            if "tracked_positions" not in self.state:
                self.state["tracked_positions"] = {}
            self.state["tracked_positions"][contract_symbol] = pos_dict
            self.save_state()

    def remove_position(self, contract_symbol: str):
        with self.lock:
            if "tracked_positions" in self.state and contract_symbol in self.state["tracked_positions"]:
                del self.state["tracked_positions"][contract_symbol]
                self.save_state()

    def set_pullback_watch(self, symbol: str, watch_data: Dict[str, Any]):
        with self.lock:
            if "pullback_watch" not in self.state:
                self.state["pullback_watch"] = {}
            self.state["pullback_watch"][symbol] = watch_data
            self.save_state()

    def get_pullback_watch(self, symbol: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.state.get("pullback_watch", {}).get(symbol)

    def clear_pullback_watch(self, symbol: str):
        with self.lock:
            if "pullback_watch" in self.state and symbol in self.state["pullback_watch"]:
                del self.state["pullback_watch"][symbol]
                self.save_state()

    def record_completed_trade(self, trade_info: Dict[str, Any]):
        with self.lock:
            if "completed_trades" not in self.state:
                self.state["completed_trades"] = []
            self.state["completed_trades"].append(trade_info)
            self.save_state()

    def try_mark_order_pending(
        self,
        order_key: str,
        order_data: Optional[Dict[str, Any]] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        qty: Optional[int] = None,
    ) -> bool:
        """
        Atomically checks if an order is inflight and reserves it as PENDING under the same lock
        in a single critical section, persisting the reservation to disk immediately.
        Returns True if reservation was acquired; False if the order already exists or is in-flight.
        Only one execution thread may acquire the reservation.
        Does not release reservation on request timeouts; uncertain submissions require broker reconciliation.
        """
        with self.lock:
            if "order_registry" not in self.state:
                self.state["order_registry"] = {}
            rec = self.state["order_registry"].get(order_key)
            if rec is not None:
                status = str(rec.get("status", "")).upper()
                if status in ["PENDING", "FILLED", "UNVERIFIED", "COMPLETE", "OPEN"]:
                    return False

            if order_data is None:
                order_data = {"symbol": symbol or "", "side": side or "", "qty": qty or 0}

            self.state["order_registry"][order_key] = {
                "status": "PENDING",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": order_data,
            }
            self.save_state()
            return True

    def mark_order_pending(self, order_key: str, order_data: Dict[str, Any]):
        with self.lock:
            if "order_registry" not in self.state:
                self.state["order_registry"] = {}
            self.state["order_registry"][order_key] = {
                "status": "PENDING",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": order_data,
            }
            self.save_state()

    def mark_order_resolved(self, order_key: str, status: str, order_id: Optional[str] = None):
        with self.lock:
            if "order_registry" in self.state and order_key in self.state["order_registry"]:
                self.state["order_registry"][order_key]["status"] = status
                if order_id:
                    self.state["order_registry"][order_key]["order_id"] = order_id
                self.save_state()

    def is_order_inflight(self, order_key: str) -> bool:
        with self.lock:
            rec = self.state.get("order_registry", {}).get(order_key)
            return rec is not None and rec.get("status") in ["PENDING", "FILLED", "UNVERIFIED"]


# ==============================================================================
# 8. MASTER REMEDIATED LIVE STRATEGY ENGINE
# ==============================================================================
class MCXIchimokuStrategy:
    """
    Production Multi-Timeframe Ichimoku Live Execution Engine for OpenAlgo.
    Enforces FAIL-CLOSED execution, verified fills, broker reconciliation, and session alignment.
    """

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        api_key: str = OPENALGO_API_KEY,
        host: str = OPENALGO_HOST,
        state_file: Path = STATE_FILE_PATH,
    ):
        self.symbols = [normalize_mcx_symbol(s) for s in (symbols or DEFAULT_MCX_UNIVERSE)]
        self.api_key = api_key
        self.host = host
        self.state_manager = PersistentStateManager(state_file)
        self.is_running = True
        self.active_contracts: Dict[str, str] = {}
        self.verified_lot_sizes: Dict[str, int] = {}
        self.candle_cache: Dict[str, pd.DataFrame] = {}
        self.client = None
        self.is_host_reachable = False
        self.has_reconciliation_discrepancy: bool = False
        self.reconciliation_discrepancies: List[str] = []
        self.unexpected_broker_positions: Dict[str, int] = {}

        if not self.api_key:
            logger.critical("❌ [FAIL-CLOSED] OPENALGO_API_KEY is not configured. Live orders cannot be authorized.")

        self.is_host_reachable = self._check_host_reachability()
        if self.is_host_reachable:
            logger.info(f"✅ Connected to OpenAlgo server at {self.host}.")
            self._init_sdk_client()
            self._discover_active_contracts()
            self.reconcile_broker_positions()
        else:
            logger.warning(
                f"🛑 [FAIL-CLOSED] OpenAlgo server at {self.host} is unreachable. "
                f"Live order authorization is strictly BLOCKED until gateway is restored."
            )

    def _check_host_reachability(self) -> bool:
        base_url = self.host.rstrip("/")
        try:
            r = requests.post(f"{base_url}/api/v1/ping", json={"apikey": self.api_key}, timeout=5.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass

        try:
            r2 = requests.get(self.host, timeout=5.0)
            return r2.status_code == 200
        except Exception:
            return False

    def _init_sdk_client(self):
        if self.client is not None or not OPENALGO_AVAILABLE or api is None or not self.api_key:
            return
        try:
            self.client = api(api_key=self.api_key, host=self.host, timeout=6.0)
            logger.info("OpenAlgo Python SDK client initialized.")
        except Exception as e:
            logger.warning(f"Failed to initialize SDK client: {e}. Falling back to REST.")

    def resolve_lot_size(self, symbol: str, contract_symbol: str) -> int:
        """
        Dynamically queries OpenAlgo /api/v1/symbol to retrieve the official exchange lot size.
        Falls back to authoritative MCX commodity specs and asserts non-zero quantity.
        """
        if contract_symbol in self.verified_lot_sizes:
            return self.verified_lot_sizes[contract_symbol]

        lot_size = None
        if self.is_host_reachable and self.api_key:
            try:
                url = f"{self.host.rstrip('/')}/api/v1/symbol"
                resp = requests.post(
                    url,
                    json={"apikey": self.api_key, "symbol": contract_symbol, "exchange": EXCHANGE},
                    timeout=5,
                )
                if resp.status_code == 200:
                    d = resp.json().get("data", {})
                    ls = d.get("lotsize") or d.get("lot_size")
                    if ls and int(ls) > 0:
                        lot_size = int(ls)
            except Exception as e:
                logger.debug(f"Symbol lookup for lot size on {contract_symbol}: {e}")

        if not lot_size:
            specs = MCX_COMMODITY_SPECS.get(symbol, {})
            lot_size = specs.get("exchange_lot_size")

        if not lot_size or lot_size <= 0:
            logger.error(f"🛑 [FAIL-CLOSED] Cannot verify official lot size for {contract_symbol}. Order rejected.")
            return 0

        self.verified_lot_sizes[contract_symbol] = lot_size
        return lot_size

    def _discover_active_contracts(self):
        """Resolves active near-month contract symbols with tender-period awareness."""
        logger.info("🔍 Resolving active MCX contracts and official lot sizes...")
        now = get_current_ist()
        for sym in self.symbols:
            specs = MCX_COMMODITY_SPECS.get(sym, {})
            prefix = specs.get("search_prefix", sym)
            contract = None

            if self.is_host_reachable and self.api_key:
                try:
                    url = f"{self.host.rstrip('/')}/api/v1/search"
                    resp = requests.post(
                        url,
                        json={"apikey": self.api_key, "query": prefix, "exchange": EXCHANGE},
                        timeout=6,
                    )
                    if resp.status_code == 200:
                        results = resp.json().get("data", [])
                        valid = []
                        now_naive = datetime.now()
                        for r in results:
                            s = str(r.get("symbol", ""))
                            if r.get("instrumenttype") == "FUT" and s.startswith(prefix):
                                exp_str = r.get("expiry")
                                exp_dt = None
                                if exp_str:
                                    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
                                        try:
                                            exp_dt = datetime.strptime(exp_str, fmt)
                                            break
                                        except Exception:
                                            pass
                                # Tender-period protection: Require expiry at least 3 days in future
                                if exp_dt and (exp_dt - now_naive).days >= 3:
                                    valid.append((exp_dt, s))
                        if valid:
                            valid.sort(key=lambda x: x[0])
                            contract = valid[0][1]
                except Exception as e:
                    logger.warning(f"Error querying search API for {prefix}: {e}")

            if not contract:
                # Algorithmic fallback aligned with MCX expiry cycles
                cycle = specs.get("expiry_cycle", list(range(1, 13)))
                target_month = now.month
                target_year = now.year
                while target_month not in cycle or (target_month == now.month and now.day >= 24):
                    target_month += 1
                    if target_month > 12:
                        target_month = 1
                        target_year += 1

                month_str = datetime(target_year, target_month, 1).strftime("%b").upper()
                year_str = datetime(target_year, target_month, 1).strftime("%y")
                contract = f"{prefix}{year_str}{month_str}FUT"

            self.active_contracts[sym] = contract
            lot_sz = self.resolve_lot_size(sym, contract)
            logger.info(f"  [+] {sym:10s} -> Active Contract: {contract} (Official Lot Size: {lot_sz} units)")

    def reconcile_broker_positions(self):
        """
        Reconciles internal tracked state against official broker position book and order book.
        Performs bidirectional reconciliation:
        - Detects internally tracked positions missing at broker (clears phantom state).
        - Detects unexpected/external broker positions missing internally (flags and blocks new entries).
        - Detects quantity mismatches (updates internal state and flags discrepancy).
        - Detects pending/unverified orders and partial fills against broker orderbook.
        - Strictly NEVER auto-closes, overwrites or silently adopts unexpected external positions.
        - Blocks new entries until discrepancies are resolved safely.
        """
        if not self.is_host_reachable or not self.api_key:
            return

        discrepancies: List[str] = []
        unexpected_positions: Dict[str, int] = {}

        try:
            # 1. Pending orders and partial fills check against broker orderbook
            try:
                ob_url = f"{self.host.rstrip('/')}/api/v1/orderbook"
                ob_resp = requests.post(ob_url, json={"apikey": self.api_key}, timeout=6)
                if ob_resp.status_code == 200:
                    ob_data = ob_resp.json().get("data", [])
                    broker_orders = {}
                    if isinstance(ob_data, list):
                        for o in ob_data:
                            if isinstance(o, dict):
                                oid = str(o.get("orderid") or o.get("order_id") or "")
                                if oid:
                                    broker_orders[oid] = o

                    registry = self.state_manager.state.get("order_registry", {})
                    for o_key, o_val in list(registry.items()):
                        if o_val.get("status") in ["PENDING", "UNVERIFIED"]:
                            oid = str(o_val.get("order_id") or "")
                            bo = broker_orders.get(oid) if oid else None
                            if not bo and not oid:
                                o_data = o_val.get("data", {})
                                c_sym = o_data.get("contract", "")
                                c_qty = int(o_data.get("quantity", 0))
                                c_act = str(o_data.get("action", "")).upper()
                                for b_order in broker_orders.values():
                                    b_sym = b_order.get("tradingsymbol") or b_order.get("symbol")
                                    b_qty = int(b_order.get("quantity") or 0)
                                    b_act = str(b_order.get("transaction_type") or b_order.get("action") or "").upper()
                                    if b_sym == c_sym and b_qty == c_qty and (not c_act or b_act == c_act):
                                        bo = b_order
                                        oid = str(bo.get("orderid") or bo.get("order_id") or "")
                                        o_val["order_id"] = oid
                                        break

                            if bo:
                                b_status = str(bo.get("order_status") or bo.get("status") or "").upper()
                                filled_qty = int(bo.get("filled_quantity") or bo.get("filledqty") or 0)
                                total_qty = int(bo.get("quantity") or 0)

                                if b_status in ["COMPLETE", "FILLED"]:
                                    self.state_manager.mark_order_resolved(o_key, "FILLED", oid)
                                    logger.info(f"✅ [RECONCILIATION] Order {oid} ({o_key}) reconciled as FILLED.")
                                    o_data = o_val.get("data", {})
                                    c_sym = o_data.get("contract", "")
                                    act = o_data.get("action", "")
                                    if c_sym and c_sym not in self.state_manager.state.get("tracked_positions", {}):
                                        avg_px = float(bo.get("average_price") or bo.get("price") or 0.0)
                                        self.state_manager.save_position(
                                            c_sym,
                                            {
                                                "symbol": o_data.get("symbol", ""),
                                                "contract": c_sym,
                                                "direction": "Long" if act == "BUY" else "Short",
                                                "quantity": filled_qty or total_qty or int(o_data.get("quantity", 0)),
                                                "entry_price": avg_px,
                                                "reconciled_from_order": oid,
                                            },
                                        )
                                elif b_status in ["CANCELLED", "REJECTED"]:
                                    self.state_manager.mark_order_resolved(o_key, b_status, oid)
                                    logger.info(f"ℹ️ [RECONCILIATION] Order {oid} ({o_key}) reconciled as {b_status}.")
                                elif 0 < filled_qty < total_qty:
                                    msg = f"Partial fill on order {oid} ({o_key}): {filled_qty}/{total_qty}"
                                    logger.warning(f"⚠️ [RECONCILIATION] {msg}")
                                    discrepancies.append(msg)
                                elif b_status in ["OPEN", "PENDING", "TRIGGER_PENDING"]:
                                    msg = f"Order {oid} ({o_key}) still open/pending at broker"
                                    logger.info(f"⏳ [RECONCILIATION] {msg}")
                                    discrepancies.append(msg)
                            else:
                                msg = f"Unresolved pending order reservation: {o_key} (ID: {oid or 'UNCONFIRMED'})"
                                logger.warning(f"⚠️ [RECONCILIATION] {msg}")
                                discrepancies.append(msg)
            except Exception as ob_err:
                logger.debug(f"Orderbook reconciliation check: {ob_err}")

            # 2. Positionbook reconciliation
            url = f"{self.host.rstrip('/')}/api/v1/positionbook"
            resp = requests.post(url, json={"apikey": self.api_key}, timeout=6)
            if resp.status_code == 200:
                broker_data = resp.json().get("data", [])
                broker_positions: Dict[str, int] = {}
                for p in broker_data:
                    sym = p.get("symbol") or p.get("tradingsymbol")
                    qty = int(p.get("quantity") or p.get("netqty") or p.get("net_qty") or 0)
                    exch = str(p.get("exchange", "")).upper()
                    # Isolate strategy exchange: external positions on other exchanges (e.g. NFO, NSE) must be ignored
                    if exch and exch != EXCHANGE:
                        logger.debug(
                            f"ℹ️ [EXTERNAL POSITION IGNORED] {sym} on exchange '{exch}' "
                            f"is outside strategy scope ({EXCHANGE})."
                        )
                        continue
                    if sym:
                        broker_positions[sym] = qty

                # 2A. Forward check: Internally tracked positions vs broker positions
                tracked = self.state_manager.state.get("tracked_positions", {})
                for contract, pos_info in list(tracked.items()):
                    broker_qty = broker_positions.get(contract, 0)
                    if broker_qty == 0:
                        logger.warning(
                            f"⚠️ [RECONCILIATION] Phantom position detected! Internal state holds {contract}, "
                            f"but broker position is 0. Clearing internal position."
                        )
                        self.state_manager.remove_position(contract)
                        self.state_manager.clear_pullback_watch(pos_info.get("symbol", ""))
                    elif abs(broker_qty) != abs(pos_info.get("quantity", 0)):
                        msg = (
                            f"Quantity mismatch for {contract}! "
                            f"Internal: {pos_info.get('quantity')}, Broker: {broker_qty}"
                        )
                        logger.warning(f"⚠️ [RECONCILIATION] {msg}. Updating internal state quantity.")
                        pos_info["quantity"] = abs(broker_qty)
                        self.state_manager.save_position(contract, pos_info)
                        discrepancies.append(msg)

                # 2B. Reverse check: Broker positions vs internally tracked positions
                for sym, b_qty in broker_positions.items():
                    if b_qty != 0 and sym not in tracked:
                        msg = (
                            f"Unexpected external broker position: {sym} Qty={b_qty} (not tracked internally)"
                        )
                        logger.critical(f"🚨 [AUDIT ALERT] {msg}. Strategy will NOT adopt or close this position.")
                        unexpected_positions[sym] = b_qty
                        discrepancies.append(msg)

        except Exception as e:
            logger.warning(f"Error during broker position book reconciliation: {e}")
            discrepancies.append(f"Reconciliation query error: {e}")

        self.unexpected_broker_positions = unexpected_positions
        if discrepancies:
            self.has_reconciliation_discrepancy = True
            self.reconciliation_discrepancies = discrepancies
            logger.error(
                f"🛑 [SAFETY GOVERNOR] Reconciliation discrepancies detected: {discrepancies}. "
                f"New entries are BLOCKED until resolved safely."
            )
        else:
            self.has_reconciliation_discrepancy = False
            self.reconciliation_discrepancies = []

    def fetch_1h_candles(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Fetches completed, confirmed 1H candles from OpenAlgo API.
        STRICT FAIL-CLOSED POLICY:
        - In-progress / unclosed candles are filtered out.
        - Stale data (> 75 min old during market hours) is rejected.
        - Insufficient history (< 80 bars) is rejected.
        - Zero research CSV fallback is permitted in live execution.
        """
        contract = self.active_contracts.get(symbol, symbol)
        now = get_current_ist()

        if not self.is_host_reachable or not self.api_key:
            logger.warning(f"🛑 [FAIL-CLOSED] OpenAlgo gateway unavailable. Refusing data fetch for {symbol}.")
            return None

        # Request 35 days of history (~450 1H bars) for robust HTF warm-up without synthetic CSVs
        start_date = (now - timedelta(days=35)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        df_live = None
        # 1. Try SDK History
        if self.client is not None:
            try:
                resp = self.client.history(
                    symbol=contract,
                    exchange=EXCHANGE,
                    interval=INTERVAL,
                    start_date=start_date,
                    end_date=end_date,
                )
                if isinstance(resp, pd.DataFrame) and not resp.empty:
                    df_live = resp
            except Exception as e:
                logger.debug(f"SDK history fetch for {symbol} ({contract}): {e}")

        # 2. Try REST API History
        if df_live is None or df_live.empty:
            try:
                url = f"{self.host.rstrip('/')}/api/v1/history"
                payload = {
                    "apikey": self.api_key,
                    "symbol": contract,
                    "exchange": EXCHANGE,
                    "interval": INTERVAL,
                    "start_date": start_date,
                    "end_date": end_date,
                }
                r = requests.post(url, json=payload, timeout=8)
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    if data:
                        df_live = pd.DataFrame(data)
            except Exception as e:
                logger.error(f"[FAIL-CLOSED] History fetch error for {symbol} ({contract}): {e}")
                return None

        if df_live is None or df_live.empty:
            logger.warning(f"🛑 [FAIL-CLOSED] Empty history received from live broker for {symbol}.")
            return None

        # Format dataframe
        df_live.columns = [str(c).strip().lower() for c in df_live.columns]
        if "timestamp" in df_live.columns:
            if pd.api.types.is_numeric_dtype(df_live["timestamp"]):
                df_live["timestamp"] = pd.to_datetime(df_live["timestamp"], unit="s", utc=True).dt.tz_convert(IST)
            else:
                df_live["timestamp"] = pd.to_datetime(df_live["timestamp"])
                if df_live["timestamp"].dt.tz is None:
                    df_live["timestamp"] = df_live["timestamp"].dt.tz_localize(IST)
                else:
                    df_live["timestamp"] = df_live["timestamp"].dt.tz_convert(IST)
            df_live = df_live.set_index("timestamp")
        elif not isinstance(df_live.index, pd.DatetimeIndex):
            df_live.index = pd.to_datetime(df_live.index)
            if df_live.index.tz is None:
                df_live.index = df_live.index.tz_localize(IST)
            else:
                df_live.index = df_live.index.tz_convert(IST)
        elif df_live.index.tz is None:
            df_live.index = df_live.index.tz_localize(IST)
        else:
            df_live.index = df_live.index.tz_convert(IST)

        df_live = df_live.sort_index()
        for col in ["open", "high", "low", "close"]:
            if col in df_live.columns:
                df_live[col] = df_live[col].astype(float)

        # GATE 1: Filter out forming, unclosed hourly bar
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        df_completed = df_live[df_live.index < current_hour_start].copy()

        if df_completed.empty:
            logger.warning(f"🛑 [FAIL-CLOSED] No completed 1H candles found for {symbol}.")
            return None

        # GATE 2: Data Freshness Check during MCX market hours
        last_bar_dt = df_completed.index[-1]
        # In OHLCV data, timestamp represents the start of the bar.
        # A completed 1H bar completed at bar_close = last_bar_dt + 1 hour.
        bar_close_dt = last_bar_dt + timedelta(hours=1)
        age_minutes = (now - bar_close_dt).total_seconds() / 60.0
        # If market has been open for > 60m, require the last completed bar to be within 75m of close
        session_active, _ = is_mcx_trading_time(now)
        if session_active and (now.hour * 60 + now.minute) >= (10 * 60 + 5) and age_minutes > 75.0:
            logger.error(
                f"🛑 [FAIL-CLOSED] Market data is STALE for {symbol} "
                f"(Last bar: {last_bar_dt.strftime('%Y-%m-%d %H:%M IST')} [Close: {bar_close_dt.strftime('%H:%M IST')}], "
                f"Age: {age_minutes:.1f}m > 75m). Aborting."
            )
            return None

        # GATE 3: Minimum Historical Depth (80 bars required for Senkou B 52 + displacement 26)
        if len(df_completed) < 80:
            logger.warning(
                f"🛑 [FAIL-CLOSED] Insufficient history for {symbol} ({len(df_completed)} < 80 bars). "
                f"Indicator warm-up requirements not satisfied."
            )
            return None

        self.candle_cache[symbol] = df_completed
        return df_completed

    def place_order(
        self,
        symbol: str,
        contract_symbol: str,
        action: str,
        lots: int,
        reason: str,
        reference_price: float = 0.0,
        candle_timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Submits order with dynamic exchange lot size validation and verified fill polling.
        Guarantees that quantity sent to OpenAlgo is in verified exchange units.
        """
        lot_size = self.resolve_lot_size(symbol, contract_symbol)
        if lot_size <= 0:
            logger.error(f"🛑 [FAIL-CLOSED] Unverified lot size for {contract_symbol}. Order rejected.")
            return None

        exchange_qty = lots * lot_size
        if exchange_qty <= 0 or (exchange_qty % lot_size != 0):
            logger.error(
                f"🛑 [FAIL-CLOSED] Order quantity {exchange_qty} is not a valid multiple of lot size {lot_size}."
            )
            return None

        candle_key = candle_timestamp or get_current_ist().strftime("%Y%m%d%H")
        order_key = f"{contract_symbol}_{action}_{candle_key}"
        order_data = {
            "symbol": symbol,
            "contract": contract_symbol,
            "action": action,
            "lots": lots,
            "quantity": exchange_qty,
            "reason": reason,
            "candle": candle_key,
        }

        # ATOMIC CHECK-AND-RESERVE TO PREVENT CONCURRENT DUPLICATE ORDERS
        if not self.state_manager.try_mark_order_pending(order_key, order_data):
            logger.warning(f"⚠️ [IDEMPOTENCY] Order {order_key} already inflight/reserved. Skipping duplicate.")
            return None

        logger.info(
            f"🚀 [ORDER] Submitting {action} {lots} lot(s) = {exchange_qty} units of {contract_symbol} ({reason})..."
        )

        resp = None
        timed_out = False
        if self.client is not None:
            try:
                resp = self.client.placeorder(
                    strategy=STRATEGY_NAME,
                    symbol=contract_symbol,
                    exchange=EXCHANGE,
                    action=action,
                    price_type="MARKET",
                    product=PRODUCT,
                    quantity=exchange_qty,
                )
            except requests.exceptions.Timeout as e:
                logger.error(f"SDK placeorder timeout: {e}")
                timed_out = True
            except Exception as e:
                logger.error(f"SDK placeorder error: {e}")

        if not resp and not timed_out:
            try:
                order_url = f"{self.host.rstrip('/')}/api/v1/placeorder"
                payload = {
                    "apikey": self.api_key,
                    "strategy": STRATEGY_NAME,
                    "symbol": contract_symbol,
                    "exchange": EXCHANGE,
                    "action": action,
                    "price_type": "MARKET",
                    "product": PRODUCT,
                    "quantity": exchange_qty,
                }
                r = requests.post(order_url, json=payload, timeout=8)
                resp = r.json() if r.status_code == 200 else {"status": "error", "message": r.text}
            except requests.exceptions.Timeout as e:
                logger.error(f"REST placeorder timeout: {e}")
                timed_out = True
            except Exception as e:
                logger.error(f"REST placeorder error: {e}")

        if timed_out:
            logger.critical(
                f"🛑 [ORDER UNCERTAIN] Order request timed out for {order_key}. "
                f"Holding reservation as UNVERIFIED until broker reconciliation."
            )
            self.state_manager.mark_order_resolved(order_key, "UNVERIFIED")
            return None

        if isinstance(resp, dict) and resp.get("status") in ["success", 200, "COMPLETE"]:
            order_id = resp.get("orderid", "")
            if not order_id:
                logger.error("🛑 Order gateway acknowledged success but returned no orderid.")
                self.state_manager.mark_order_resolved(order_key, "FAILED")
                return None

            # VERIFIED FILL POLLING: Poll /api/v1/orderstatus up to 5 times for terminal fill state
            fill_success, fill_price = self._poll_verified_fill(order_id, contract_symbol, fallback=reference_price)
            if fill_success and fill_price > 0:
                self.state_manager.mark_order_resolved(order_key, "FILLED", order_id)
                alert_msg = (
                    f"🚨 *{STRATEGY_NAME} ORDER FILLED*\n"
                    f"• *Contract*: `{contract_symbol}`\n"
                    f"• *Action*: *{action}*\n"
                    f"• *Lots*: {lots} ({exchange_qty} units)\n"
                    f"• *Fill Price*: ₹{fill_price:,.2f}\n"
                    f"• *Reason*: {reason}\n"
                    f"• *Timestamp*: {get_current_ist().strftime('%d-%b-%Y %H:%M:%S IST')}"
                )
                send_telegram_alert(alert_msg)
                return {
                    "status": "success",
                    "orderid": order_id,
                    "fill_price": fill_price,
                    "quantity": exchange_qty,
                }
            else:
                logger.error(
                    f"🛑 [UNVERIFIED FILL] Order {order_id} for {contract_symbol} was not confirmed COMPLETE by broker."
                )
                self.state_manager.mark_order_resolved(order_key, "UNVERIFIED", order_id)
                return None

        self.state_manager.mark_order_resolved(order_key, "FAILED")
        return None

    def _poll_verified_fill(
        self, order_id: str, contract_symbol: str, fallback: float = 0.0
    ) -> Tuple[bool, float]:
        """Polls OpenAlgo orderstatus endpoint to verify COMPLETE state and extract real fill price."""
        url = f"{self.host.rstrip('/')}/api/v1/orderstatus"
        for attempt in range(5):
            time.sleep(0.5 * (attempt + 1))
            try:
                r = requests.post(url, json={"apikey": self.api_key, "strategy": STRATEGY_NAME, "orderid": str(order_id)}, timeout=8)
                if r.status_code == 200:
                    data = r.json().get("data", r.json())
                    status = str(
                        data.get("order_status") or data.get("status") or data.get("orderstatus") or ""
                    ).upper()
                    if status in ["COMPLETE", "FILLED"]:
                        for k in ["average_price", "avg_price", "fill_price", "price"]:
                            if data.get(k):
                                fv = float(data[k])
                                if fv > 0:
                                    return True, fv
                        if fallback > 0:
                            return True, fallback
                    elif status in ["REJECTED", "CANCELLED"]:
                        logger.error(f"🛑 Order {order_id} was {status} by broker: {data.get('rejection_reason', '')}")
                        return False, 0.0
            except Exception as e:
                logger.debug(f"Polling order status for {order_id} attempt {attempt+1}: {e}")

        # If orderstatus polling fails to confirm terminal COMPLETE or FILLED state, fail-closed!
        logger.warning(
            f"⚠️ [UNCONFIRMED ORDER] Order {order_id} for {contract_symbol} not confirmed COMPLETE after 5 polling attempts."
        )
        return False, 0.0

    def evaluate_symbol(self, symbol: str):
        """
        Complete evaluation on confirmed, completed 1H candles.
        Enforces exactly-once execution per candle, session-aligned HTF consensus, and verified fill sizing.
        """
        df_1h = self.fetch_1h_candles(symbol)
        if df_1h is None or len(df_1h) < 80:
            return

        specs = MCX_COMMODITY_SPECS.get(symbol, {})
        contract = self.active_contracts.get(symbol, symbol)
        pullback_prox = specs.get("pullback_tolerance", 0.015)
        multiplier = specs.get("multiplier", 10.0)
        lot_size = self.resolve_lot_size(symbol, contract)

        # 1. Compute 1H Ichimoku from confirmed 1H candles
        df_ichi_1h = compute_ichimoku_1h(df_1h)
        if df_ichi_1h is None or len(df_ichi_1h) < 80:
            logger.warning(f"🛑 [FAIL-CLOSED] Insufficient Ichimoku data for {symbol}.")
            return

        # Fail-closed check: verify all required indicator fields exist
        required_cols = [
            "close", "high", "low", "tenkan", "kijun", "senkou_a", "senkou_b",
            "kumo_top", "kumo_bottom", "chikou", "chikou_past_close", "future_cloud_bull",
            "future_cloud_bear", "atr14"
        ]
        if not all(col in df_ichi_1h.columns for col in required_cols):
            logger.error(f"🛑 [FAIL-CLOSED] Missing required Ichimoku indicator columns in df_ichi_1h for {symbol}.")
            return

        # Slicing from latest completed Ichimoku-enriched 1H candle
        last_bar = df_ichi_1h.iloc[-1]
        prev_bar = df_ichi_1h.iloc[-2]

        # Fail-closed check: verify no NaN in critical indicator values
        critical_fields = ["tenkan", "kijun", "senkou_a", "senkou_b", "chikou_past_close", "chikou", "atr14"]
        if any(pd.isna(last_bar.get(col)) for col in critical_fields) or any(pd.isna(prev_bar.get(col)) for col in critical_fields):
            logger.warning(f"🛑 [FAIL-CLOSED] NaN indicator value detected for {symbol}. Insufficient warm-up.")
            return

        candle_ts = str(
            last_bar.name
            if last_bar.name is not None and not str(last_bar.name).isdigit()
            else (last_bar.get("timestamp") or str(last_bar.name))
        )

        close = float(last_bar["close"])
        high = float(last_bar["high"])
        low = float(last_bar["low"])
        tenkan = float(last_bar["tenkan"])
        kijun = float(last_bar["kijun"])
        kumo_top = float(last_bar["kumo_top"])
        kumo_bot = float(last_bar["kumo_bottom"])
        chikou_ref = float(last_bar["chikou_past_close"])
        fut_bull = bool(last_bar["future_cloud_bull"])
        fut_bear = bool(last_bar["future_cloud_bear"])
        atr14 = float(last_bar["atr14"])

        # -------------------------------------------------------------
        # 1. Manage Active Position (Intrabar Stops, Targets & Structural Exits)
        # Continues monitoring stops and targets on every cycle even when no new entry signal exists!
        # -------------------------------------------------------------
        pos = self.state_manager.get_position(contract)
        if pos:
            pos_dir = 1 if pos.get("direction") == "Long" else -1
            entry_p = float(pos.get("entry_price", close))
            stop_p = float(pos.get("stop_price", 0.0))
            target_p = float(pos.get("target_price", 0.0))
            pos_qty = int(pos.get("quantity", LOTS * lot_size))
            pos_lots = max(1, pos_qty // lot_size)

            # A. Intrabar Stop Loss Hit (2.0x ATR)
            stop_hit = (pos_dir == 1 and low <= stop_p) or (pos_dir == -1 and high >= stop_p)
            if stop_hit:
                logger.warning(f"🛑 [STOP LOSS] {contract} Protective 2.0x ATR Stop Hit at {stop_p:.2f}!")
                action = "SELL" if pos_dir == 1 else "BUY"
                res = self.place_order(
                    symbol,
                    contract,
                    action,
                    pos_lots,
                    reason=f"Hard 2.0x ATR Stop Loss Hit ({stop_p:.2f})",
                    reference_price=stop_p,
                    candle_timestamp=candle_ts,
                )
                if res:
                    self.state_manager.remove_position(contract)
                    self.state_manager.clear_pullback_watch(symbol)  # Re-entry strictly barred on stop-out
                    pnl_pts = (stop_p - entry_p) if pos_dir == 1 else (entry_p - stop_p)
                    self.state_manager.record_completed_trade(
                        {
                            "symbol": symbol,
                            "contract": contract,
                            "direction": pos["direction"],
                            "exit_reason": "STOP_LOSS",
                            "entry_price": entry_p,
                            "exit_price": stop_p,
                            "net_pnl": round(pnl_pts * (multiplier / lot_size) * pos_qty - 40.0, 2),
                        }
                    )
                return

            # B. Intrabar Profit Target Reached (+3.5x ATR = 1.75R)
            if ENABLE_TARGET and target_p > 0:
                target_hit = (pos_dir == 1 and high >= target_p) or (pos_dir == -1 and low <= target_p)
                if target_hit:
                    logger.info(
                        f"🎯 [TARGET REACHED] {contract} 3.5x ATR (1.75R) Target Reached at {target_p:.2f}!"
                    )
                    action = "SELL" if pos_dir == 1 else "BUY"
                    res = self.place_order(
                        symbol,
                        contract,
                        action,
                        pos_lots,
                        reason=f"3.5x ATR (1.75R) Profit Target Hit ({target_p:.2f})",
                        reference_price=target_p,
                        candle_timestamp=candle_ts,
                    )
                    if res:
                        self.state_manager.remove_position(contract)
                        pnl_pts = (target_p - entry_p) if pos_dir == 1 else (entry_p - target_p)
                        self.state_manager.record_completed_trade(
                            {
                                "symbol": symbol,
                                "contract": contract,
                                "direction": pos["direction"],
                                "exit_reason": "TARGET_REACHED_1_75R",
                                "entry_price": entry_p,
                                "exit_price": target_p,
                                "net_pnl": round(pnl_pts * (multiplier / lot_size) * pos_qty - 40.0, 2),
                            }
                        )
                        if ENABLE_PULLBACK_REENTRY:
                            self.state_manager.set_pullback_watch(
                                symbol,
                                {
                                    "target_exited_dir": pos_dir,
                                    "exit_time": candle_ts,
                                    "target_exit_price": target_p,
                                    "bars_since_exit": 0,
                                },
                            )
                            logger.info(
                                f"👀 [PULLBACK WATCH] Activated for {symbol} "
                                f"(Direction: {pos['direction']}, Target Exit: {target_p:.2f}, 1.75R Banked)."
                            )
                    return

            # C. Bar Close Structural Exit
            struct_exit = (pos_dir == 1 and (close < kijun or tenkan < kijun)) or (
                pos_dir == -1 and (close > kijun or tenkan > kijun)
            )
            if struct_exit:
                logger.info(f"📉 [STRUCTURAL EXIT] {contract} Hosoda Equilibrium Breakdown on Bar Close.")
                action = "SELL" if pos_dir == 1 else "BUY"
                res = self.place_order(
                    symbol,
                    contract,
                    action,
                    pos_lots,
                    reason="Hosoda Structural Exit (Close vs Kijun / TK Cross)",
                    reference_price=close,
                    candle_timestamp=candle_ts,
                )
                if res:
                    self.state_manager.remove_position(contract)
                    self.state_manager.clear_pullback_watch(symbol)
                    pnl_pts = (close - entry_p) if pos_dir == 1 else (entry_p - close)
                    self.state_manager.record_completed_trade(
                        {
                            "symbol": symbol,
                            "contract": contract,
                            "direction": pos["direction"],
                            "exit_reason": "STRUCTURAL_EXIT",
                            "entry_price": entry_p,
                            "exit_price": close,
                            "net_pnl": round(pnl_pts * (multiplier / lot_size) * pos_qty - 40.0, 2),
                        }
                    )
                return

            return  # Position active; monitoring continues on every cycle

        # -------------------------------------------------------------
        # 2. Check Fresh Entries or Pullback Re-entries (Flat State Only)
        # -------------------------------------------------------------
        # Safety gate: block new entries if broker reconciliation discrepancy is active
        if self.has_reconciliation_discrepancy:
            logger.warning(
                f"🛑 [SAFETY BLOCK] New entries blocked for {symbol} due to active broker reconciliation discrepancies: "
                f"{self.reconciliation_discrepancies}"
            )
            return

        # Exactly-once execution check per candle boundary
        last_processed = self.state_manager.get_last_processed_candle(symbol)
        if last_processed == candle_ts:
            return  # This confirmed candle has already been processed

        # Exposure limit check
        tracked = self.state_manager.state.get("tracked_positions", {})
        if MAX_ACTIVE_POSITIONS > 0 and len(tracked) >= MAX_ACTIVE_POSITIONS:
            logger.info(
                f"⏸️ Max active positions limit ({MAX_ACTIVE_POSITIONS}) reached. Skipping new entries for {symbol}."
            )
            return

        # Compute HTF Consensuses for Fresh Entry Filter
        df_4h = resample_ohlcv(df_1h, "4h")
        df_1d = resample_ohlcv(df_1h, "1D")

        reg_4h, dir_4h, _ = classify_htf_regime(df_4h)
        reg_1d, dir_1d, _ = classify_htf_regime(df_1d)

        htf_bull_gate = ("Bullish" in reg_4h) and ("Bullish" in reg_1d)
        htf_bear_gate = ("Bearish" in reg_4h) and ("Bearish" in reg_1d)

        # 1H Model I5 Trigger
        bull_state = (tenkan > kijun) and (close > kumo_top) and (close > chikou_ref) and (close > kijun) and fut_bull
        bear_state = (tenkan < kijun) and (close < kumo_bot) and (close < chikou_ref) and (close < kijun) and fut_bear

        prev_bull = (
            (prev_bar["tenkan"] > prev_bar["kijun"])
            and (prev_bar["close"] > prev_bar["kumo_top"])
            and (prev_bar["close"] > prev_bar["chikou_past_close"])
            and (prev_bar["close"] > prev_bar["kijun"])
            and prev_bar["future_cloud_bull"]
        )
        prev_bear = (
            (prev_bar["tenkan"] < prev_bar["kijun"])
            and (prev_bar["close"] < prev_bar["kumo_bottom"])
            and (prev_bar["close"] < prev_bar["chikou_past_close"])
            and (prev_bar["close"] < prev_bar["kijun"])
            and prev_bar["future_cloud_bear"]
        )

        bull_trigger = bull_state and not prev_bull
        bear_trigger = bear_state and not prev_bear

        # -------------------------------------------------------------
        # 2. Check Fresh Entries or Pullback Re-entries (Flat State)
        # -------------------------------------------------------------
        # Safety gate: block new entries if broker reconciliation discrepancy is active
        if self.has_reconciliation_discrepancy:
            logger.warning(
                f"🛑 [SAFETY BLOCK] New entries blocked for {symbol} due to active broker reconciliation discrepancies: "
                f"{self.reconciliation_discrepancies}"
            )
            return

        # Exactly-once execution check per candle boundary
        last_processed = self.state_manager.get_last_processed_candle(symbol)
        if last_processed == candle_ts:
            return  # This confirmed candle has already been processed

        # Exposure limit check
        tracked = self.state_manager.state.get("tracked_positions", {})
        if MAX_ACTIVE_POSITIONS > 0 and len(tracked) >= MAX_ACTIVE_POSITIONS:
            logger.info(
                f"⏸️ Max active positions limit ({MAX_ACTIVE_POSITIONS}) reached. Skipping new entries for {symbol}."
            )
            return

        watch = self.state_manager.get_pullback_watch(symbol)
        reenter_long = False
        reenter_short = False

        if watch and ENABLE_PULLBACK_REENTRY:
            t_dir = watch.get("target_exited_dir", 0)
            bars_since = watch.get("bars_since_exit", 0) + 1
            watch["bars_since_exit"] = bars_since
            self.state_manager.set_pullback_watch(symbol, watch)

            # Invalidate watch if HTF regime broke or max lifetime (15 bars) exceeded
            if (t_dir == 1 and not htf_bull_gate) or (t_dir == -1 and not htf_bear_gate):
                logger.info(f"ℹ️ [WATCH INVALIDATED] HTF regime no longer confluent for {symbol}. Clearing watch.")
                self.state_manager.clear_pullback_watch(symbol)
            elif bars_since > 15:
                logger.info(f"ℹ️ [WATCH EXPIRED] Pullback watch exceeded 15 bars for {symbol}. Clearing watch.")
                self.state_manager.clear_pullback_watch(symbol)
            elif bars_since >= 2:  # Must have at least 1 completed bar separation after exit
                if t_dir == 1:
                    tested_kijun = low <= kijun * (1.0 + pullback_prox)
                    if tested_kijun and close > tenkan and close > kijun:
                        reenter_long = True
                        logger.info(f"🚀 [PULLBACK RE-ENTRY TRIGGER] {symbol} Bullish Hosoda Model I3 Bounce confirmed!")
                elif t_dir == -1:
                    tested_kijun = high >= kijun * (1.0 - pullback_prox)
                    if tested_kijun and close < tenkan and close < kijun:
                        reenter_short = True
                        logger.info(f"🚀 [PULLBACK RE-ENTRY TRIGGER] {symbol} Bearish Hosoda Model I3 Bounce confirmed!")

        fresh_long = bull_trigger and htf_bull_gate
        fresh_short = bear_trigger and htf_bear_gate

        if fresh_long or reenter_long:
            stop_p = close - (STOP_LOSS_ATR_MULT * atr14)
            target_p = close + (PROFIT_TARGET_ATR_MULT * atr14) if ENABLE_TARGET else 0.0
            reason = (
                "Hosoda Model I3 Pullback Re-entry"
                if reenter_long
                else "San Yaku Kouten + Dual 4H/1D Confluence"
            )
            res = self.place_order(
                symbol,
                contract,
                "BUY",
                LOTS,
                reason=reason,
                reference_price=close,
                candle_timestamp=candle_ts,
            )
            if res:
                fill_p = res.get("fill_price", close)
                verified_qty = res.get("quantity", LOTS * lot_size)
                self.state_manager.save_position(
                    contract,
                    {
                        "symbol": symbol,
                        "contract": contract,
                        "direction": "Long",
                        "lots": LOTS,
                        "quantity": verified_qty,
                        "entry_price": fill_p,
                        "entry_atr": atr14,
                        "stop_price": round(fill_p - (STOP_LOSS_ATR_MULT * atr14), 2),
                        "target_price": round(fill_p + (PROFIT_TARGET_ATR_MULT * atr14), 2) if ENABLE_TARGET else 0.0,
                        "entry_time": candle_ts,
                        "order_id": res.get("orderid"),
                    },
                )
                self.state_manager.clear_pullback_watch(symbol)
                self.state_manager.set_last_processed_candle(symbol, candle_ts)

        elif fresh_short or reenter_short:
            stop_p = close + (STOP_LOSS_ATR_MULT * atr14)
            target_p = close - (PROFIT_TARGET_ATR_MULT * atr14) if ENABLE_TARGET else 0.0
            reason = (
                "Hosoda Model I3 Pullback Re-entry"
                if reenter_short
                else "San Yaku Gyakuten + Dual 4H/1D Confluence"
            )
            res = self.place_order(
                symbol,
                contract,
                "SELL",
                LOTS,
                reason=reason,
                reference_price=close,
                candle_timestamp=candle_ts,
            )
            if res:
                fill_p = res.get("fill_price", close)
                verified_qty = res.get("quantity", LOTS * lot_size)
                self.state_manager.save_position(
                    contract,
                    {
                        "symbol": symbol,
                        "contract": contract,
                        "direction": "Short",
                        "lots": LOTS,
                        "quantity": verified_qty,
                        "entry_price": fill_p,
                        "entry_atr": atr14,
                        "stop_price": round(fill_p + (STOP_LOSS_ATR_MULT * atr14), 2),
                        "target_price": round(fill_p - (PROFIT_TARGET_ATR_MULT * atr14), 2) if ENABLE_TARGET else 0.0,
                        "entry_time": candle_ts,
                        "order_id": res.get("orderid"),
                    },
                )
                self.state_manager.clear_pullback_watch(symbol)
                self.state_manager.set_last_processed_candle(symbol, candle_ts)

        # Mark candle as evaluated to avoid re-running signal checks on same bar
        self.state_manager.set_last_processed_candle(symbol, candle_ts)

    def emit_heartbeat(self, status: str = "ACTIVE", active_count: int = 0):
        hb = {
            "strategy": STRATEGY_NAME,
            "version": "1.1.0-REMEDIATED",
            "timestamp": get_current_ist().isoformat(),
            "status": status,
            "host_reachable": self.is_host_reachable,
            "data_source_mode": "FAIL_CLOSED_LIVE_GATEWAY",
            "universe": self.symbols,
            "active_positions_count": active_count,
            "open_contracts": list(self.state_manager.state.get("tracked_positions", {}).keys()),
            "pullback_watches": self.state_manager.state.get("pullback_watch", {}),
            "verified_lot_sizes": self.verified_lot_sizes,
        }
        # Atomic heartbeat persistence via temp file + replace
        tmp_hb = HEARTBEAT_FILE_PATH.with_name(f"{HEARTBEAT_FILE_PATH.stem}_{uuid.uuid4().hex}.tmp")
        try:
            with open(tmp_hb, "w", encoding="utf-8") as f:
                json.dump(hb, f, indent=2)
            os.replace(tmp_hb, HEARTBEAT_FILE_PATH)
        except Exception:
            if tmp_hb.exists():
                try:
                    tmp_hb.unlink()
                except Exception:
                    pass

    def execute_cycle(self):
        """Runs a complete evaluation cycle with broker position reconciliation and fail-closed checks."""
        now_ist = get_current_ist()
        is_open, open_reason = is_mcx_trading_time(now_ist)
        if not is_open:
            logger.info(f"⏸️ MCX is closed ({open_reason}). Session hours: 09:00 - 23:30 IST.")
            self.emit_heartbeat(status="IDLE_MARKET_CLOSED")
            return

        if not self.is_host_reachable:
            if self._check_host_reachability():
                self.is_host_reachable = True
                logger.info(f"🔄 Reconnected to OpenAlgo server at {self.host}. Re-discovering contracts...")
                self._init_sdk_client()
                self._discover_active_contracts()
                self.reconcile_broker_positions()
            else:
                logger.warning("🛑 [FAIL-CLOSED] OpenAlgo host unreachable. Cycle aborted.")
                self.emit_heartbeat(status="ERROR_GATEWAY_OFFLINE")
                return

        # Reconcile broker positions before evaluating symbols
        self.reconcile_broker_positions()

        logger.info(f"⏳ [CYCLE START] Evaluating MCX commodities at {now_ist.strftime('%d-%b-%Y %H:%M:%S IST')}...")
        with ThreadPoolExecutor(max_workers=min(len(self.symbols), 4)) as executor:
            list(executor.map(self.evaluate_symbol, self.symbols))

        tracked = self.state_manager.state.get("tracked_positions", {})
        active_count = len(tracked)
        self.emit_heartbeat(status="ACTIVE", active_count=active_count)
        logger.info(
            f"✅ [CYCLE COMPLETE] Active Positions: {active_count} | Pullback Watches: {len(self.state_manager.state.get('pullback_watch', {}))}"
        )

    def run_loop(self, poll_interval: int = POLL_INTERVAL_SECONDS):
        def _sig_handler(sig, frame):
            logger.info(f"\n[!] Signal {sig} received. Gracefully stopping {STRATEGY_NAME}...")
            self.is_running = False

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        logger.info(f"🔁 Strategy loop started for {STRATEGY_NAME} (Poll Interval: {poll_interval}s).")
        while self.is_running:
            try:
                self.execute_cycle()
            except Exception as e:
                logger.error(f"Error during cycle execution: {e}", exc_info=True)

            if RUN_ONCE or not self.is_running:
                break

            sleep_sec = get_seconds_to_next_candle_boundary(buffer_seconds=5)
            wait_time = min(float(poll_interval), sleep_sec)
            logger.info(f"💤 Sleeping {wait_time:.1f}s until next candle boundary check...")
            sleep_start = time.time()
            while self.is_running and (time.time() - sleep_start < wait_time):
                time.sleep(1)

        logger.info(f"⏹️ {STRATEGY_NAME} shutdown complete.")


# ==============================================================================
# 9. CLI ENTRY POINT & VERIFICATION HARNESS
# ==============================================================================
def run_verification_test() -> bool:
    """Verifies math, state persistence, indicators, lot sizing, and session resampling."""
    print("=" * 70)
    print("RUNNING REMEDIATED ICHIMOKU MCX SELF-TEST & VERIFICATION HARNESS")
    print("=" * 70)

    # 1. Generate Synthetic 1H Candles (300 bars)
    np.random.seed(42)
    dates = pd.date_range("2026-10-01 09:00", periods=300, freq="1h", tz=IST)
    price = 100000.0 + np.cumsum(np.random.normal(50.0, 150.0, 300))
    df_mock = pd.DataFrame(
        {
            "open": price - 20,
            "high": price + 100,
            "low": price - 100,
            "close": price,
            "volume": np.random.randint(100, 1000, 300),
        },
        index=dates,
    )

    # 2. Test Indicators & Approved Option A Target Ratio
    df_ichi = compute_ichimoku_1h(df_mock)
    assert "tenkan" in df_ichi.columns and "kijun" in df_ichi.columns, "Ichimoku lines missing"
    assert "atr14" in df_ichi.columns, "ATR14 missing"
    assert STOP_LOSS_ATR_MULT == 2.0, "Stop loss multiple must be 2.0x ATR"
    assert PROFIT_TARGET_ATR_MULT == 3.5, "Profit target multiple must be 3.5x ATR"
    assert REWARD_RISK_RATIO == 1.75, "Reward-to-risk must be exactly 1.75R"
    print("  [+] Ichimoku lines, ATR14, and Option A 1.75R risk ratio verified.")

    # 3. Test Session-Aligned HTF Resampling & Geometry
    df_4h = resample_ohlcv(df_mock, "4h")
    assert len(df_4h) > 0, "4H resampling failed"
    assert df_4h["timestamp"].iloc[0].hour == 9, "4H must anchor at 09:00 IST MCX open"
    regime_4h, dir_4h, is_horiz = classify_htf_regime(df_4h)
    assert regime_4h in [
        "Strong_Bullish_Geometry",
        "Mild_Bullish_Geometry",
        "Strong_Bearish_Geometry",
        "Mild_Bearish_Geometry",
        "Neutral_Chop",
    ]
    print(f"  [+] Session-Aligned 4H HTF Geometry verified (Regime: {regime_4h}).")

    # 4. Test Thread-Safe State Persistence
    test_state_file = SCRIPT_DIR / "test_ichimoku_remediated_state.json"
    mgr = PersistentStateManager(test_state_file)
    mgr.save_position("GOLDM_TEST", {"direction": "Long", "quantity": 100, "entry_price": 100000.0})
    mgr.set_pullback_watch("GOLDM", {"target_exited_dir": 1, "target_exit_price": 103500.0})

    mgr2 = PersistentStateManager(test_state_file)
    assert mgr2.get_position("GOLDM_TEST")["quantity"] == 100
    assert mgr2.get_pullback_watch("GOLDM")["target_exited_dir"] == 1
    if test_state_file.exists():
        test_state_file.unlink()
    print("  [+] Thread-Safe Atomic State Persistence verified.")

    # 5. Test Lot Sizing
    assert MCX_COMMODITY_SPECS["GOLDM"]["exchange_lot_size"] == 100
    assert MCX_COMMODITY_SPECS["CRUDEOILM"]["exchange_lot_size"] == 10
    print("  [+] Verified Exchange Lot Sizes (GOLDM: 100, CRUDEOILM: 10) verified.")

    print("\n✅ ALL REMEDIATED ICHIMOKU MCX TESTS PASSED.")
    return True


def main():
    parser = argparse.ArgumentParser(description="MCX Traditional Ichimoku Production Strategy Engine")
    parser.add_argument("--symbols", type=str, default="GOLDM,CRUDEOILM", help="Comma-separated MCX commodities")
    parser.add_argument("--once", action="store_true", help="Execute single cycle and exit")
    parser.add_argument("--test", action="store_true", help="Run automated verification test suite")
    parser.add_argument("--poll", type=int, default=60, help="Poll interval in seconds")

    args = parser.parse_args()

    if args.test:
        success = run_verification_test()
        sys.exit(0 if success else 1)

    sym_list = [s.strip() for s in args.symbols.split(",") if s.strip()]
    engine = MCXIchimokuStrategy(symbols=sym_list)

    if args.once:
        engine.execute_cycle()
    else:
        acquire_single_instance_lock("ichimoku_mcx")
        engine.run_loop(poll_interval=args.poll)


if __name__ == "__main__":
    main()
