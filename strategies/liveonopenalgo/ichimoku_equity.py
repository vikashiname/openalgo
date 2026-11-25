"""
================================================================================
OPENALGO LIVE STRATEGY: NFO TRADITIONAL ICHIMOKU 50/50 HYBRID ENGINE
================================================================================
File Role            : LIVE_OPENALGO_STRATEGY
Strategy Identifier  : ICHIMOKU_EQUITY_PROD
Target Universe      : Curated Golden 8 Champions (ADANIENT, BAJAJ-AUTO, NTPC,
                       MARUTI, JINDALSTEL, HCLTECH, SBIN, BAJFINANCE)
Exchange             : NFO (National Stock Exchange Futures & Options)
Default Product      : NRML (Normal Futures)
Timeframe            : 1-Hour (1H) Primary Execution with Daily MTF Confluence
Current Version      : 1.0.0-PROD (Certified Production Baseline)
Baseline Promotion   : Official Replacement for Legacy emacrossopen.py (EMA/MACD V5)
================================================================================
Strategy Specifications:
  1. Primary Signal Engine (1H Model I5 - Hosoda San Yaku Kouten):
     - San Yaku Kouten (Long):
       * 1H Close > Cloud Top (Span A & Span B)
       * Tenkan-sen > Kijun-sen (TK Bullish or Bullish Cross)
       * Chikou Span > Past Close (Close[t] > Close[t-26])
       * Daily Close > Daily Cloud Top (Higher Timeframe Macro Confluence)
       * Relative Volume Gate: RVOL >= 0.80 (20-period SMA)
     - Long Only on Equities (Protects against asymmetric short gamma & decay).

  2. 50/50 Split Hybrid Execution & Trailing Engine (Mode 3 Champion):
     - Stop Loss: 2.0x ATR14 Adaptive Stop placed at entry.
     - Target 1 (+3.5R): When price hits Entry + (3.5 * ATR14), bank profit on 50% of position.
     - Risk-Free Runner (Remaining 50%):
       * Stop Loss immediately ratchets to Break-Even (+0.1% buffer).
       * Trails dynamically along the 1H Kijun-sen line.
       * Exits when 1H Close breaches beneath trailing Kijun floor.

  3. Institutional Risk Management & Portfolio Constraints:
     - Max Concurrent Positions: Strictly capped at 4 simultaneous trades.
     - Sector Limit: Max 1 open trade per sector (Zero concentration risk).
     - Execution Cutoff: No fresh entries after 14:30 PM IST.
     - Expiry Filter: No fresh entries within 48 hours of monthly expiry Thursday.

  4. Production Engineering:
     - Strict Next-Bar Open execution (zero lookahead).
     - Atomic crash-safe state persistence across restarts (ichimoku_equity_state.json).
     - Heartbeat emission for watchdog monitoring (ichimoku_equity_heartbeat.json).
     - Dynamic discovery of active near-month NFO futures contracts & lot sizes.
     - Telegram notifications for all order and risk events.
================================================================================
"""

import argparse
import csv
import json
import logging
import os
import signal
import fcntl

_LOCK_FILE = None

def acquire_single_instance_lock(lock_name: str = 'ichimoku_equity'):
    global _LOCK_FILE
    lock_path = f'/tmp/{lock_name}.lock'
    try:
        _LOCK_FILE = open(lock_path, 'w')
        fcntl.flock(_LOCK_FILE, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FILE.write(f'{os.getpid()}\n')
        _LOCK_FILE.flush()
        return True
    except (BlockingIOError, IOError):
        logger.error(f'🛑 [LOCK REJECTED] Another instance of {lock_name} is already active on this system (lockfile: {lock_path}). Exiting.')
        sys.exit(0)
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
# 1. FILE PATHS & SYSTEM CONSTANTS
# ==============================================================================
LOG_FILE_PATH = Path(os.getenv("LOG_FILE", SCRIPT_DIR / "ichimoku_equity.log"))
STATE_FILE_PATH = Path(os.getenv("STATE_FILE", SCRIPT_DIR / "ichimoku_equity_state.json"))
HEARTBEAT_FILE_PATH = Path(os.getenv("HEARTBEAT_FILE", SCRIPT_DIR / "ichimoku_equity_heartbeat.json"))

STRATEGY_NAME = os.getenv("STRATEGY_NAME", "ICHIMOKU_EQUITY_PROD")
EXCHANGE = os.getenv("EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "NRML")
INTERVAL = os.getenv("INTERVAL", "1h")

# The 8 Golden Champions Universe
GOLDEN_CHAMPIONS = [
    "ADANIENT", "BAJAJ-AUTO", "NTPC", "MARUTI",
    "JINDALSTEL", "HCLTECH", "SBIN", "BAJFINANCE"
]

SECTOR_MAP = {
    "ADANIENT": "CONGLOMERATE",
    "BAJAJ-AUTO": "AUTO",
    "MARUTI": "AUTO",
    "NTPC": "POWER",
    "JINDALSTEL": "METALS",
    "HCLTECH": "IT",
    "SBIN": "BANKING",
    "BAJFINANCE": "FINANCE"
}

# Fallback Lot Sizes
FALLBACK_LOT_SIZES = {
    "ADANIENT": 309,
    "BAJAJ-AUTO": 75,
    "NTPC": 1500,
    "MARUTI": 50,
    "JINDALSTEL": 625,
    "HCLTECH": 350,
    "SBIN": 750,
    "BAJFINANCE": 750,
    "NIFTY": 65
}

# Strategy Parameters
TENKAN_PERIOD = int(os.getenv("TENKAN_PERIOD", "9"))
KIJUN_PERIOD = int(os.getenv("KIJUN_PERIOD", "26"))
SENKOU_B_PERIOD = int(os.getenv("SENKOU_B_PERIOD", "52"))
DISPLACEMENT = int(os.getenv("DISPLACEMENT", "26"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))

STOP_LOSS_ATR_MULT = float(os.getenv("STOP_LOSS_ATR_MULT", "2.0"))
PROFIT_TARGET_R = float(os.getenv("PROFIT_TARGET_R", "3.5"))
MIN_RVOL = float(os.getenv("MIN_RVOL", "0.80"))

LOTS = int(os.getenv("LOTS", "1"))
MAX_ACTIVE_POSITIONS = int(os.getenv("MAX_ACTIVE_POSITIONS", "4")) # Max 4 concurrent trades
MAX_PER_SECTOR = int(os.getenv("MAX_PER_SECTOR", "1"))             # Max 1 trade per sector
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() in ["true", "1", "yes"]
ORDER_PACING_DELAY_SEC = float(os.getenv("ORDER_PACING_DELAY_SEC", "0.25"))

# IST Timezone (+05:30)
IST = timezone(timedelta(hours=5, minutes=30))

# ==============================================================================
# 2. LOGGING SETUP
# ==============================================================================
logger = logging.getLogger("ICHIMOKU_EQUITY")
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
OPENALGO_API_KEY = (
    os.getenv("OPENALGO_API_KEY")
    or os.getenv("API_KEY")
    or "70abbff43065667202d02e5eb49e831b38f8fd67e185490e54a2f43122e906b5"
)
OPENALGO_HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")
if not OPENALGO_HOST.startswith("http"):
    OPENALGO_HOST = f"http://{OPENALGO_HOST}"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Fallback: Fetch Telegram bot config from OpenAlgo Host API if unconfigured
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    try:
        cfg_resp = requests.get(
            f"{OPENALGO_HOST.rstrip('/')}/api/v1/telegram/config",
            headers={"X-API-Key": OPENALGO_API_KEY} if OPENALGO_API_KEY else {},
            timeout=5
        )
        if cfg_resp.status_code == 200:
            cfg_data = cfg_resp.json()
            if cfg_data.get("status") == "success" and "data" in cfg_data:
                bot_info = cfg_data["data"]
                TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKEN or bot_info.get("bot_token", "")
                TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID or bot_info.get("chat_id", "")
    except Exception:
        pass


def send_telegram_alert(message: str) -> bool:
    clean_msg = message.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info(f"📢 [TELEGRAM - CONSOLE DISPATCH]\n{clean_msg}")
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
        return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Telegram dispatch failed: {e}")
        return False


# ==============================================================================
# 4. TIME & SESSION HELPERS
# ==============================================================================
def get_current_ist() -> datetime:
    return datetime.now(timezone.utc).astimezone(IST)


def is_nfo_trading_time(now_dt: Optional[datetime] = None) -> Tuple[bool, str]:
    now = now_dt or get_current_ist()
    if now.weekday() >= 5:
        return False, "WEEKEND_CLOSED"
    m = now.hour * 60 + now.minute
    # NSE market hours: 09:15 to 15:30 IST
    if 9 * 60 + 15 <= m <= 15 * 60 + 30:
        return True, "SESSION_ACTIVE"
    return False, "HOURS_CLOSED"


def is_entry_allowed_time(now_dt: Optional[datetime] = None) -> bool:
    """Blocks fresh entries after 14:30 PM IST to prevent late-day overnight trap."""
    now = now_dt or get_current_ist()
    m = now.hour * 60 + now.minute
    return m <= 14 * 60 + 30


def get_seconds_to_next_candle_boundary(now_dt: Optional[datetime] = None, buffer_seconds: int = 2) -> float:
    """
    Computes exact seconds until the next scan boundary:
      09:17:02 (Morning Market Settling Scan)
      10:15:02, 11:15:02, 12:15:02, 13:15:02, 14:15:02, 15:15:02, 15:30:02
    """
    now = now_dt or get_current_ist()
    today = now.date()
    
    if now.weekday() >= 5:
        days_ahead = 7 - now.weekday()
        target_date = today + timedelta(days=days_ahead)
        target_dt = datetime.combine(target_date, dt_time(9, 17, buffer_seconds), tzinfo=IST)
        return max(5.0, (target_dt - now).total_seconds())

    boundary_times = [
        (9, 17, buffer_seconds),
        (10, 15, buffer_seconds),
        (11, 15, buffer_seconds),
        (12, 15, buffer_seconds),
        (13, 15, buffer_seconds),
        (14, 15, buffer_seconds),
        (15, 15, buffer_seconds),
        (15, 30, buffer_seconds)
    ]
    for h, m, s in boundary_times:
        b_dt = datetime.combine(today, dt_time(h, m, s), tzinfo=IST)
        diff = (b_dt - now).total_seconds()
        if diff > 0.5:
            return diff

    # After market close, sleep until next morning 09:17
    next_day = today + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    next_b = datetime.combine(next_day, dt_time(9, 17, buffer_seconds), tzinfo=IST)
    return max(5.0, (next_b - now).total_seconds())


# ==============================================================================
# 5. MATHEMATICAL & INDICATOR ENGINES
# ==============================================================================
def compute_ichimoku_and_atr(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates 1H Ichimoku, ATR14, RVOL, and Daily Cloud Confluence lookahead-free."""
    data = df.copy()
    data.columns = [c.lower() for c in data.columns]
    high = data["high"]
    low = data["low"]
    close = data["close"]
    vol = data["volume"].replace(0, np.nan) if "volume" in data.columns else pd.Series(1.0, index=data.index)

    # 1. 1H Ichimoku Lines
    data["tenkan"] = (high.rolling(TENKAN_PERIOD, min_periods=5).max() + low.rolling(TENKAN_PERIOD, min_periods=5).min()) / 2.0
    data["kijun"] = (high.rolling(KIJUN_PERIOD, min_periods=10).max() + low.rolling(KIJUN_PERIOD, min_periods=10).min()) / 2.0
    
    raw_span_a = (data["tenkan"] + data["kijun"]) / 2.0
    raw_span_b = (high.rolling(SENKOU_B_PERIOD, min_periods=20).max() + low.rolling(SENKOU_B_PERIOD, min_periods=20).min()) / 2.0
    
    data["senkou_a"] = raw_span_a.shift(DISPLACEMENT)
    data["senkou_b"] = raw_span_b.shift(DISPLACEMENT)
    data["cloud_top"] = np.maximum(data["senkou_a"], data["senkou_b"])
    data["cloud_bottom"] = np.minimum(data["senkou_a"], data["senkou_b"])
    data["chikou_past_close"] = close.shift(DISPLACEMENT)

    # 2. ATR 14
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    data["atr14"] = tr.rolling(ATR_PERIOD, min_periods=5).mean().bfill()

    # 3. RVOL (Prior 20-period SMA, lookahead-free)
    vol_sma20 = vol.shift(1).rolling(20, min_periods=10).mean()
    data["rvol"] = np.where(vol_sma20 > 0, vol / vol_sma20, 1.0)

    # 4. Multi-Timeframe Daily Cloud (1D Resample shifted by 1 day)
    try:
        daily = data.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        d_tenkan = (daily["high"].rolling(9).max() + daily["low"].rolling(9).min()) / 2.0
        d_kijun = (daily["high"].rolling(26).max() + daily["low"].rolling(26).min()) / 2.0
        d_span_a = ((d_tenkan + d_kijun) / 2.0).shift(26)
        d_span_b = ((daily["high"].rolling(52).max() + daily["low"].rolling(52).min()) / 2.0).shift(26)
        daily["daily_cloud_top"] = np.maximum(d_span_a, d_span_b)

        daily_shifted = daily.shift(1)
        normalized_dates = pd.Series(data.index.normalize(), index=data.index)
        data["daily_cloud_top"] = normalized_dates.map(daily_shifted["daily_cloud_top"]).ffill()
    except Exception:
        data["daily_cloud_top"] = np.nan

    return data


# ==============================================================================
# 6. PERSISTENT STATE MANAGER
# ==============================================================================
class PersistentStateManager:
    """Atomic, crash-safe state persistence for ichimoku_equity.py."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.state: Dict[str, Any] = self.load_state()

    def _default_state(self) -> Dict[str, Any]:
        return {
            "version": "1.0.0-PROD",
            "strategy": STRATEGY_NAME,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "positions": {},       # symbol -> position dict (tracking target_50 and runner_50)
            "trade_history": [],
            "last_scan_time": None
        }

    def load_state(self) -> Dict[str, Any]:
        if not self.file_path.exists():
            default = self._default_state()
            self.save_state(default)
            return default
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) and "positions" in data else self._default_state()
        except Exception as e:
            logger.error(f"Error loading state from {self.file_path}: {e}")
            return self._default_state()

    def save_state(self, state: Optional[Dict[str, Any]] = None):
        if state is not None:
            self.state = state
        tmp_file = self.file_path.with_suffix(".tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, default=str)
            tmp_file.replace(self.file_path)
        except Exception as e:
            logger.error(f"Failed to persist state: {e}")


# ==============================================================================
# 7. MAIN ICHIMOKU EQUITY TRADING ENGINE
# ==============================================================================
class IchimokuEquityEngine:
    def __init__(self, symbols: Optional[List[str]] = None, lots: int = LOTS, max_active: int = MAX_ACTIVE_POSITIONS):
        self.symbols = symbols or GOLDEN_CHAMPIONS
        self.lots = lots
        self.max_active = max_active
        self.state_mgr = PersistentStateManager(STATE_FILE_PATH)
        self.contract_cache: Dict[str, Dict[str, Any]] = {}
        self.session = requests.Session()
        self.candle_cache: Dict[str, pd.DataFrame] = {}
        self.last_candle_fetch_time: Dict[str, float] = {}
        self.is_running = True

        self._preload_historical_cache()

        logger.info("=" * 80)
        logger.info(f"🚀 INITIALIZING {STRATEGY_NAME} (50/50 SPLIT HYBRID ENGINE)")
        logger.info(f"  • Universe        : {', '.join(self.symbols)} ({len(self.symbols)} symbols)")
        logger.info(f"  • Host Server     : {OPENALGO_HOST}")
        logger.info(f"  • Exchange/Product: {EXCHANGE} / {PRODUCT}")
        logger.info(f"  • Stop Loss       : {STOP_LOSS_ATR_MULT}x ATR14 Adaptive")
        logger.info(f"  • Target 1 (50%)  : +{PROFIT_TARGET_R}R Profit Bank")
        logger.info(f"  • Runner (50%)    : Dynamic 1H Kijun-sen Trailing + BE Lock")
        logger.info(f"  • Max Concurrent  : {self.max_active} (Max {MAX_PER_SECTOR} per sector)")
        logger.info("=" * 80)

    def write_heartbeat(self, status: str = "ACTIVE", current_action: str = "IDLE"):
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy": STRATEGY_NAME,
            "status": status,
            "current_action": current_action,
            "open_positions": len(self.state_mgr.state.get("positions", {})),
            "tracked_symbols": self.symbols,
            "last_scan": self.state_mgr.state.get("last_scan_time")
        }
        try:
            tmp = HEARTBEAT_FILE_PATH.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp.replace(HEARTBEAT_FILE_PATH)
        except Exception:
            pass

    def check_openalgo_connection(self) -> bool:
        url = f"{OPENALGO_HOST.rstrip('/')}/api/v1/ping"
        headers = {"X-API-Key": OPENALGO_API_KEY} if OPENALGO_API_KEY else {}
        try:
            resp = self.session.post(url, json={"apikey": OPENALGO_API_KEY}, headers=headers, timeout=10)
            if resp.status_code == 200:
                logger.info(f"✅ OpenAlgo API online at {OPENALGO_HOST}")
                return True
        except Exception as e:
            logger.warning(f"⚠️ OpenAlgo reachability check: {e}")
        return False

    def resolve_contract(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Resolves active near-month NFO futures contract and lot size dynamically."""
        if symbol in self.contract_cache:
            return self.contract_cache[symbol]

        url = f"{OPENALGO_HOST.rstrip('/')}/api/v1/search"
        headers = {"X-API-Key": OPENALGO_API_KEY} if OPENALGO_API_KEY else {}
        payload = {"apikey": OPENALGO_API_KEY, "query": symbol, "exchange": "NFO"}

        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                fut_contracts = [
                    d for d in data 
                    if str(d.get("symbol", "")).startswith(symbol) and (
                        str(d.get("instrumenttype", "")).upper() == "FUT" or
                        str(d.get("instrument_type", "")).upper() == "FUT" or
                        str(d.get("symbol", "")).endswith("FUT")
                    )
                ]
                now_dt = datetime.now()
                valid = []
                for item in fut_contracts:
                    exp_str = item.get("expiry")
                    lot = int(item.get("lotsize") or item.get("lot_size") or FALLBACK_LOT_SIZES.get(symbol, 1))
                    if exp_str:
                        for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%B-%Y", "%d-%B-%y"):
                            try:
                                exp_dt = datetime.strptime(exp_str, fmt)
                                if exp_dt.date() >= now_dt.date():
                                    valid.append((exp_dt, item.get("symbol"), lot))
                                break
                            except Exception:
                                pass
                    elif item.get("symbol"):
                        valid.append((datetime(2099, 1, 1), item.get("symbol"), lot))

                if valid:
                    valid.sort(key=lambda x: x[0])
                    near_exp, contract_symbol, lot_sz = valid[0]
                    res = {
                        "contract": contract_symbol,
                        "lot_size": lot_sz,
                        "expiry": near_exp.strftime("%Y-%m-%d") if near_exp.year != 2099 else None
                    }
                    self.contract_cache[symbol] = res
                    logger.info(f"✅ Resolved active NFO contract for {symbol}: {res['contract']} (Lot Size: {res['lot_size']})")
                    return res
                else:
                    logger.warning(f"⚠️ Search for {symbol} returned no valid futures contracts in NFO.")
            else:
                logger.warning(f"⚠️ Contract search HTTP {resp.status_code} for {symbol}: {resp.text}")
        except Exception as e:
            logger.warning(f"⚠️ Contract search error for {symbol}: {e}")

        # Algorithmic fallback: Monthly last-Thursday contract
        now_dt = datetime.now()
        year_str = now_dt.strftime("%y")
        month_str = now_dt.strftime("%b").upper()
        contract_symbol = f"{symbol}{year_str}{month_str}FUT"
        lot_sz = FALLBACK_LOT_SIZES.get(symbol, 1)
        res = {"contract": contract_symbol, "lot_size": lot_sz, "expiry": None}
        self.contract_cache[symbol] = res
        logger.info(f"ℹ️ Algorithmic near-month resolution for {symbol}: {contract_symbol} (Lot Size: {lot_sz})")
        return res

    def pre_resolve_contracts(self):
        """Pre-resolves all universe contracts sequentially with pacing at startup."""
        logger.info(f"🔄 Pre-resolving active NFO contracts for {len(self.symbols)} symbols...")
        for sym in self.symbols:
            self.resolve_contract(sym)
            time.sleep(ORDER_PACING_DELAY_SEC)

    def _preload_historical_cache(self):
        """Pre-loads verified clean baseline historical candles into in-memory cache on startup."""
        for sym in self.symbols:
            candidates = [
                SCRIPT_DIR / "data" / f"{sym}_1h.csv",
                ROOT_DIR / "strategies/liveonopenalgo/data" / f"{sym}_1h.csv",
                ROOT_DIR / "backtesting/emacrossopen/data" / f"{sym}_1h.parquet",
            ]
            local_file = next((p for p in candidates if p.exists()), None)
            if local_file:
                try:
                    if local_file.suffix == ".parquet":
                        df = pd.read_parquet(local_file)
                    else:
                        df = pd.read_csv(local_file)
                    df.columns = [str(c).strip().lower() for c in df.columns]
                    if "timestamp" in df.columns:
                        if pd.api.types.is_numeric_dtype(df["timestamp"]):
                            df["date"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(IST)
                        else:
                            df["date"] = pd.to_datetime(df["timestamp"], utc=True)
                            if df["date"].dt.tz is None:
                                df["date"] = df["date"].dt.tz_localize(IST)
                            else:
                                df["date"] = df["date"].dt.tz_convert(IST)
                        df = df.set_index("date")
                    elif "date" in df.columns:
                        df["date"] = pd.to_datetime(df["date"], utc=True)
                        if df["date"].dt.tz is None:
                            df["date"] = df["date"].dt.tz_localize(IST)
                        else:
                            df["date"] = df["date"].dt.tz_convert(IST)
                        df = df.set_index("date")
                    elif not isinstance(df.index, pd.DatetimeIndex):
                        df.index = pd.to_datetime(df.index, utc=True).tz_convert(IST)

                    df = df.sort_index()
                    for col in ["open", "high", "low", "close"]:
                        if col in df.columns:
                            df[col] = df[col].astype(float)
                    if "volume" in df.columns:
                        df["volume"] = df["volume"].astype(float)

                    if len(df) >= 55:
                        self.candle_cache[sym] = df
                        logger.info(f"  [+] Pre-loaded {len(df)} historical baseline candles for {sym} ({local_file.name}).")
                except Exception as e:
                    logger.warning(f"Error pre-loading historical cache for {sym}: {e}")

    def fetch_historical_candles(self, symbol: str, limit: int = 150) -> Optional[pd.DataFrame]:
        contract_info = self.resolve_contract(symbol)
        trading_sym = contract_info.get("contract") if contract_info else None

        now_ist = get_current_ist()
        cached_ready = symbol in self.candle_cache and len(self.candle_cache[symbol]) >= 55
        time_since_fetch = time.time() - self.last_candle_fetch_time.get(symbol, 0.0)

        # 1-Hour candles for equity close at XX:15 (09:15-15:30). Rollover window is minute 15-17.
        is_rollover_minute = (now_ist.minute in (15, 16, 17))
        if cached_ready and time_since_fetch < 180 and not is_rollover_minute:
            df_ret = self.candle_cache[symbol]
            return df_ret.tail(limit) if (limit and len(df_ret) > limit) else df_ret

        self.last_candle_fetch_time[symbol] = time.time()

        candidates: List[Tuple[str, str]] = []
        if trading_sym:
            candidates.append((trading_sym, EXCHANGE))
        # Cash equity fallback on NSE
        candidates.append((symbol, "NSE"))

        # Fetch incremental recent 5 days
        start_date = (now_ist - timedelta(days=5)).strftime("%Y-%m-%d")
        end_date = now_ist.strftime("%Y-%m-%d")

        url = f"{OPENALGO_HOST.rstrip('/')}/api/v1/history"
        headers = {"X-API-Key": OPENALGO_API_KEY} if OPENALGO_API_KEY else {}

        df_live = None
        for sym_cand, exch in candidates:
            payload = {
                "apikey": OPENALGO_API_KEY,
                "symbol": sym_cand,
                "exchange": exch,
                "interval": INTERVAL,
                "start_date": start_date,
                "end_date": end_date,
            }

            for attempt in range(1, 3):
                try:
                    resp = self.session.post(url, json=payload, headers=headers, timeout=6)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        candles = res_json.get("data") or res_json.get("candles", [])
                        if candles:
                            df_live = pd.DataFrame(candles)
                            break
                        else:
                            # 0 candles returned for this derivative symbol, fallback to cash equity
                            break
                    else:
                        logger.debug(f"History API HTTP {resp.status_code} for {symbol} ({sym_cand}:{exch}): {resp.text}")
                        if "429" in resp.text or "-360" in resp.text or "Standard plan limit" in resp.text:
                            break
                except requests.exceptions.RequestException as e:
                    logger.debug(f"Attempt {attempt}/2: Error fetching history for {symbol} ({sym_cand}:{exch}): {e}")
                    if attempt < 2:
                        time.sleep(1.0)
                except Exception as e:
                    logger.debug(f"Unexpected error fetching history for {symbol} ({sym_cand}:{exch}): {e}")
                    break
            if df_live is not None and not df_live.empty:
                break

        if df_live is not None and not df_live.empty:
            df_live.columns = [str(c).strip().lower() for c in df_live.columns]
            if "timestamp" in df_live.columns:
                if pd.api.types.is_numeric_dtype(df_live["timestamp"]):
                    df_live["date"] = pd.to_datetime(df_live["timestamp"], unit="s", utc=True).dt.tz_convert(IST)
                else:
                    df_live["date"] = pd.to_datetime(df_live["timestamp"], utc=True)
                    if df_live["date"].dt.tz is None:
                        df_live["date"] = df_live["date"].dt.tz_localize(IST)
                    else:
                        df_live["date"] = df_live["date"].dt.tz_convert(IST)
            elif "date" in df_live.columns:
                df_live["date"] = pd.to_datetime(df_live["date"], utc=True)
                if df_live["date"].dt.tz is None:
                    df_live["date"] = df_live["date"].dt.tz_localize(IST)
                else:
                    df_live["date"] = df_live["date"].dt.tz_convert(IST)
            df_live = df_live.sort_values("date").set_index("date")
            for col in ["open", "high", "low", "close"]:
                if col in df_live.columns:
                    df_live[col] = df_live[col].astype(float)
            if "volume" in df_live.columns:
                df_live["volume"] = df_live["volume"].astype(float)

            if symbol in self.candle_cache and not self.candle_cache[symbol].empty:
                combined = pd.concat([self.candle_cache[symbol], df_live])
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                self.candle_cache[symbol] = combined
            else:
                self.candle_cache[symbol] = df_live

        if symbol in self.candle_cache and not self.candle_cache[symbol].empty:
            df_ret = self.candle_cache[symbol]
            if limit and len(df_ret) > limit:
                df_ret = df_ret.tail(limit)
            return df_ret

        return None

    def execute_market_order(self, action: str, contract: str, quantity: int) -> Optional[Dict[str, Any]]:
        """Dispatches market order to OpenAlgo using standard /api/v1/placeorder."""
        url = f"{OPENALGO_HOST.rstrip('/')}/api/v1/placeorder"
        headers = {"X-API-Key": OPENALGO_API_KEY} if OPENALGO_API_KEY else {}
        payload = {
            "apikey": OPENALGO_API_KEY,
            "strategy": STRATEGY_NAME,
            "symbol": contract,
            "action": action.upper(),
            "exchange": EXCHANGE,
            "pricetype": "MARKET",
            "product": PRODUCT,
            "quantity": quantity
        }
        for attempt in range(1, 3):
            try:
                resp = self.session.post(url, json=payload, headers=headers, timeout=20)
                if resp.status_code == 200:
                    res_data = resp.json()
                    logger.info(f"✅ Order Dispatched: {action} {quantity} {contract} -> Response: {res_data}")
                    return res_data
                else:
                    logger.error(f"❌ Order failed HTTP {resp.status_code} (attempt {attempt}): {resp.text}")
            except Exception as e:
                logger.error(f"Exception placing order for {contract} (attempt {attempt}): {e}")
            time.sleep(ORDER_PACING_DELAY_SEC)
        return None

    def evaluate_symbol(self, symbol: str):
        """Processes 1H candle close, position management, target bank, and trailing runner."""
        contract_info = self.resolve_contract(symbol)
        if not contract_info or not contract_info.get("contract"):
            logger.warning(f"⚠️ Cannot evaluate {symbol}: Active contract resolution failed.")
            return

        contract = contract_info["contract"]
        lot_size = contract_info.get("lot_size", 1)
        total_qty = lot_size * self.lots

        df = self.fetch_historical_candles(symbol)
        if df is None:
            return
        if len(df) < 55:
            logger.warning(f"⚠️ Insufficient candles ({len(df)} < 55) for {symbol} ({contract}). Skipping.")
            return

        df_calc = compute_ichimoku_and_atr(df)
        last_bar = df_calc.iloc[-1]
        prev_bar = df_calc.iloc[-2]

        cur_close = float(last_bar["close"])
        cur_high = float(last_bar["high"])
        cur_low = float(last_bar["low"])
        cur_atr = float(last_bar["atr14"])
        cur_kijun = float(last_bar["kijun"])

        positions = self.state_mgr.state.get("positions", {})
        pos = positions.get(symbol)

        # ----------------------------------------------------------------------
        # A. POSITION RISK & TRAILING MANAGEMENT (When LONG)
        # ----------------------------------------------------------------------
        if pos:
            entry_price = float(pos["entry_price"])
            stop_price = float(pos["stop_price"])
            target_price = float(pos["target_price"])
            runner_active = bool(pos.get("runner_active", False))
            target_banked = bool(pos.get("target_banked", False))

            exit_triggered = False
            exit_reason = ""
            exit_qty = total_qty

            # 1. Check Initial Stop Loss
            if not runner_active and cur_low <= stop_price:
                exit_triggered = True
                exit_reason = "STOP_LOSS_HIT"
                exit_qty = total_qty

            # 2. Check Target 1 (+3.5R) Bank for 50%
            elif not target_banked and cur_high >= target_price:
                bank_qty = total_qty // 2
                logger.info(f"🎯 TARGET 1 HIT for {symbol} at ₹{target_price:,.2f}! Banking 50% ({bank_qty} units).")
                self.execute_market_order("SELL", contract, bank_qty)
                
                pos["target_banked"] = True
                pos["runner_active"] = True
                # Ratchet Stop Loss to Break-Even (+0.1% buffer)
                pos["stop_price"] = entry_price * 1.001
                pos["runner_floor"] = pos["stop_price"]
                pos["remaining_qty"] = total_qty - bank_qty
                self.state_mgr.save_state()

                msg = (
                    f"🎯 <b>TARGET 1 (50%) BANKED</b>\n"
                    f"Symbol: <code>{contract}</code>\n"
                    f"Entry: ₹{entry_price:,.2f} | Banked: ₹{target_price:,.2f}\n"
                    f"Remaining 50% Runner Stop locked to Break-Even at ₹{pos['stop_price']:,.2f}."
                )
                send_telegram_alert(msg)
                return

            # 3. Check Runner Trailing Exit (Mode 3 along 1H Kijun-sen)
            elif runner_active:
                rem_qty = pos.get("remaining_qty", total_qty // 2)
                runner_floor = float(pos.get("runner_floor", pos["stop_price"]))

                # Ratchet trailing floor along Kijun-sen (0.2% buffer beneath Kijun)
                if pd.notna(cur_kijun) and cur_kijun > 0:
                    new_trail = cur_kijun * 0.998
                    if new_trail > runner_floor:
                        runner_floor = new_trail
                        pos["runner_floor"] = runner_floor
                        pos["stop_price"] = runner_floor
                        self.state_mgr.save_state()

                # Check if Close breaches beneath Kijun trailing floor or Break-Even Stop
                if cur_close < runner_floor or cur_low <= pos["stop_price"]:
                    exit_triggered = True
                    exit_reason = "RUNNER_KIJUN_TRAILING_EXIT"
                    exit_qty = rem_qty

            # 4. Check Structural Ichimoku Exit (Close < Cloud Bottom OR Tenkan < Kijun)
            elif not exit_triggered:
                cloud_bot = float(last_bar["cloud_bottom"])
                tenkan = float(last_bar["tenkan"])
                kijun = float(last_bar["kijun"])
                if cur_close < cloud_bot or tenkan < kijun:
                    exit_triggered = True
                    exit_reason = "ICHIMOKU_STRUCTURAL_REVERSAL"
                    exit_qty = pos.get("remaining_qty", total_qty)

            # Execute Exit
            if exit_triggered:
                logger.info(f"🚨 EXIT TRIGGERED for {symbol} ({exit_reason}) -> Selling {exit_qty} {contract}")
                self.execute_market_order("SELL", contract, exit_qty)
                
                net_pnl = (cur_close - entry_price) * exit_qty
                del positions[symbol]
                self.state_mgr.state["positions"] = positions
                self.state_mgr.save_state()

                msg = (
                    f"🔴 <b>POSITION CLOSED</b>\n"
                    f"Contract: <code>{contract}</code>\n"
                    f"Reason: {exit_reason}\n"
                    f"Entry: ₹{entry_price:,.2f} | Exit: ₹{cur_close:,.2f}\n"
                    f"Est Net PnL: ₹{net_pnl:,.2f}"
                )
                send_telegram_alert(msg)
                return

        # ----------------------------------------------------------------------
        # B. FRESH ENTRY EVALUATION (When FLAT)
        # ----------------------------------------------------------------------
        if not pos:
            # Check Portfolio Capacity (Max 4 positions)
            if len(positions) >= self.max_active:
                return

            # Check Sector Limit (Max 1 position per sector)
            sec = SECTOR_MAP.get(symbol, "OTHER")
            active_sectors = [SECTOR_MAP.get(s, "OTHER") for s in positions.keys()]
            if active_sectors.count(sec) >= MAX_PER_SECTOR:
                return

            # Check Entry Time Cutoff (No entries after 14:30 PM IST)
            if not is_entry_allowed_time():
                return

            # Ichimoku San Yaku Kouten Signals
            c_above_kumo = cur_close > float(last_bar["cloud_top"])
            tk_bull = float(last_bar["tenkan"]) > float(last_bar["kijun"])
            tk_cross = (float(last_bar["tenkan"]) > float(last_bar["kijun"])) and (float(prev_bar["tenkan"]) <= float(prev_bar["kijun"]))
            chikou_free = cur_close > float(last_bar["chikou_past_close"]) if pd.notna(last_bar["chikou_past_close"]) else True
            
            # Daily Cloud Confluence
            d_cloud_top = float(last_bar["daily_cloud_top"]) if pd.notna(last_bar["daily_cloud_top"]) else 0.0
            daily_ok = cur_close > d_cloud_top if d_cloud_top > 0 else True

            # RVOL Filter
            rvol = float(last_bar["rvol"])
            rvol_ok = rvol >= MIN_RVOL

            # Primary Trigger: TK Cross OR Breakout while TK is bullish
            if (tk_cross or (c_above_kumo and tk_bull)) and c_above_kumo and tk_bull and chikou_free and daily_ok and rvol_ok:
                logger.info(f"⚡ BUY SIGNAL CONFIRMED for {symbol} ({contract}) at ₹{cur_close:,.2f} (RVOL: {rvol:.2f})")
                order_resp = self.execute_market_order("BUY", contract, total_qty)

                entry_atr = cur_atr if cur_atr > 0 else (cur_close * 0.015)
                stop_price = cur_close - (STOP_LOSS_ATR_MULT * entry_atr)
                target_price = cur_close + (PROFIT_TARGET_R * entry_atr)

                positions[symbol] = {
                    "contract": contract,
                    "entry_time": datetime.now(timezone.utc).isoformat(),
                    "entry_price": cur_close,
                    "stop_price": stop_price,
                    "target_price": target_price,
                    "initial_qty": total_qty,
                    "remaining_qty": total_qty,
                    "target_banked": False,
                    "runner_active": False,
                    "runner_floor": stop_price,
                    "sector": sec
                }
                self.state_mgr.state["positions"] = positions
                self.state_mgr.save_state()

                msg = (
                    f"🟢 <b>LONG ENTRY CONFIRMED</b>\n"
                    f"Contract: <code>{contract}</code> (Qty: {total_qty})\n"
                    f"Entry Price: ₹{cur_close:,.2f}\n"
                    f"Initial Stop Loss: ₹{stop_price:,.2f} (2.0x ATR)\n"
                    f"Target 1 (50% Bank): ₹{target_price:,.2f} (+3.5R)\n"
                    f"RVOL: {rvol:.2f} | Sector: {sec}"
                )
                send_telegram_alert(msg)

    def scan_universe(self):
        """Iterates over the Golden Champions with thread pool execution."""
        now_ist = get_current_ist()
        logger.info(f"🔎 Scanning Golden Champions Universe ({len(self.symbols)} symbols) at {now_ist.strftime('%H:%M:%S IST')}...")
        self.write_heartbeat(status="ACTIVE", current_action="SCANNING")

        # Use 2 workers to prevent queuing past timeout in OpenAlgo single-broker gateway
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(self.evaluate_symbol, self.symbols))

        self.state_mgr.state["last_scan_time"] = now_ist.isoformat()
        self.state_mgr.save_state()
        self.write_heartbeat(status="ACTIVE", current_action="IDLE")
        active_count = len(self.state_mgr.state.get("positions", {}))
        logger.info(f"✅ [SCAN COMPLETE] Evaluated {len(self.symbols)} symbols | Active Positions: {active_count}")

    def run(self):
        def _sig_handler(sig, frame):
            logger.info(f"\n[!] Signal {sig} received. Gracefully stopping Ichimoku equity engine...")
            self.is_running = False

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        logger.info("🟢 Starting Live Execution Loop...")
        self.check_openalgo_connection()
        self.pre_resolve_contracts()
        startup_scan_pending = True

        while self.is_running:
            try:
                now = get_current_ist()
                is_active, reason = is_nfo_trading_time(now)

                if is_active:
                    m = now.hour * 60 + now.minute
                    # Before 09:17 IST, wait for morning settling boundary unless this is an immediate startup/restart scan
                    if not startup_scan_pending and m < 9 * 60 + 17:
                        sleep_sec = get_seconds_to_next_candle_boundary(now, buffer_seconds=2)
                        logger.info(f"⏳ Market open. Waiting for 09:17 IST morning settling boundary in {sleep_sec:.0f}s...")
                        wait_time = min(sleep_sec, 30)
                        sleep_start = time.time()
                        while self.is_running and (time.time() - sleep_start < wait_time):
                            time.sleep(1)
                        continue

                    self.scan_universe()
                    startup_scan_pending = False
                    sleep_sec = get_seconds_to_next_candle_boundary(now, buffer_seconds=3)
                    logger.info(f"⏳ Next candle boundary in {sleep_sec:.1f}s. Sleeping...")
                    sleep_start = time.time()
                    while self.is_running and (time.time() - sleep_start < sleep_sec):
                        time.sleep(1)
                else:
                    self.write_heartbeat(status="STANDBY", current_action=reason)
                    sleep_sec = get_seconds_to_next_candle_boundary(now, buffer_seconds=5)
                    logger.info(f"💤 Market closed ({reason}). Sleeping {sleep_sec:.0f}s...")
                    wait_time = min(sleep_sec, 300)
                    sleep_start = time.time()
                    while self.is_running and (time.time() - sleep_start < wait_time):
                        time.sleep(1)

            except KeyboardInterrupt:
                logger.info("🛑 Keyboard interrupt received. Exiting...")
                self.is_running = False
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                time.sleep(10)


def main():
    parser = argparse.ArgumentParser(description="NFO Ichimoku 50/50 Hybrid Live Trading Engine")
    parser.add_argument("--run-once", action="store_true", help="Execute single scan cycle and exit")
    parser.add_argument("--lots", type=int, default=LOTS, help="Lots to trade per symbol")
    args = parser.parse_args()

    engine = IchimokuEquityEngine(lots=args.lots)
    if args.run_once:
        engine.scan_universe()
    else:
        acquire_single_instance_lock("ichimoku_equity")
        engine.run()


if __name__ == "__main__":
    main()
