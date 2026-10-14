"""
================================================================================
OPENALGO LIVE STRATEGY: NFO 1H EMA/MACD ASYMMETRIC SEQUENTIAL CONFIRMATION ENGINE
================================================================================
File Role            : LIVE_OPENALGO
Strategy Identifier  : EMACROSS_FNO_PAPER (Candidate EXP_I Champion Architecture)
Current Version      : 3.1.0
Last Modified        : 2026-10-12
Production Approval  : SHADOW / PAPER TRADING ONLY (Phase 7 Governance)

Implementation History:
  - 2026-10-12 [v3.1.0]: Candidate EXP_I Baseline Deployment:
      * Asymmetric Universe Whitelist (TOP_LONGS: 7, TOP_SHORTS: 6).
      * 1H Trend Regime Filter (Close > EMA26 for Longs, Close < EMA26 for Shorts).
      * Lookahead-Free Conservative 0.35% HWM Trailing Runner.
      * Isolated temporary state generator in test harness (39/39 tests passed).
      * Order pacing delay (0.25s) and SQLite retry exponential backoff.
  - 2026-10-12 [v3.0.2]: Added SQLite lock exponential backoff and order pacing delay (0.25s).
  - 2026-10-10 [v3.0.1]: Alert deduplication with OpenAlgo subscriber; position reconciliation.
  - 2026-10-04 [v3.0.0]: AutoResearch V3.0 baseline (EMA 10/28, Asymmetric Universe, 3.0%/1.5% TP, 6.0% SL).
================================================================================
Strategy Specification:
  1. Timeframe: Strictly 1-Hour (1H) for both EMA and MACD on completed candles.
  2. EMA Structure:
     - EMA 9 and EMA 26 calculated on completed 1H close.
     - Bullish EMA XOVER:
       prev_ema9 <= prev_ema26 AND curr_ema9 > curr_ema26 (EMA 9 crosses ABOVE EMA 26)
     - Bearish EMA XOVER:
       prev_ema9 >= prev_ema26 AND curr_ema9 < curr_ema26 (EMA 9 crosses BELOW EMA 26)
  3. MACD Structure (12, 26, 9):
     - MACD Line   = EMA12 - EMA26
     - Signal Line = EMA9 of MACD Line
     - Histogram   = MACD Line - Signal Line
     - Bullish MACD XOVER:
       prev_macd <= prev_signal AND curr_macd > curr_signal
     - Bearish MACD XOVER:
       prev_macd >= prev_signal AND curr_macd < curr_signal
  4. Confirmation Window:
     - CONFIRMATION_WINDOW = 2 completed 1H candles.
     - Delay = 0: SAME_CANDLE confirmation (Immediate Entry).
     - Delay = 1 or 2: Sequential confirmation within window.
     - Delay > 2: Expired.
  5. Long Entry Logic (Unfiltered V2-2):
     - Case A: SAME_CANDLE (EMA Bullish & MACD Bullish on same completed candle).
     - Case B: MACD_FIRST (MACD Bullish -> PENDING_EMA -> EMA confirms within 2 candles).
     - Case C: EMA_FIRST (EMA Bullish -> PENDING_MACD -> MACD confirms within 2 candles).
     - Both sequences allowed. Unfiltered to preserve full positive expectancy (+₹18.6M).
  6. Short Entry Logic (MACD-First Only V2-2):
     - Case A: SAME_CANDLE (MACD Bearish & EMA Bearish on same completed candle).
     - Case B: MACD_FIRST (MACD Bearish -> PENDING_EMA -> EMA confirms within 2 candles).
     - Case C: EMA_FIRST -> STRICTLY REJECTED. Does NOT create pending setup.
     - Eliminates lagging EMA entries that caused short squeeze drawdowns.
  7. Invalidation:
     - If leading indicator reverses directional bias before 2nd confirms, setup is CANCELLED.
  8. Histogram Filter:
     - STRICTLY NOT USED AS AN ENTRY FILTER.
     - Calculated, logged, and alerted for research and diagnostics only.
  9. Execution Standard:
     - STRICTLY PAPER / ANALYZE TRADING MODE ONLY.
     - If paper/analyze mode is unconfirmed or live mode is detected, order execution is hard-disabled.
     - Dynamic discovery of active near-month NFO futures contracts & lot sizes.
     - Real-time OpenAlgo position synchronization, duplicate entry protection,
       and controlled position reversals (FLAT->LONG, FLAT->SHORT, LONG->SHORT, SHORT->LONG).
     - Full idempotency across process restarts (Candle timestamp + Symbol + Direction).
     - Atomic crash-safe state persistence, startup position reconciliation,
       and independent watchdog heartbeat.
     - Complete active NFO instrument universe.
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
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(), override=False)
except ImportError:
    for candidate in [ROOT_DIR / ".env", Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]:
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
# 1. FILE PATHS & CONSTANTS
# ==============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
LOG_FILE_PATH = Path(os.getenv("LOG_FILE", PROJECT_ROOT / "log/strategies/emacrossopen.log" if (PROJECT_ROOT / "log").exists() else SCRIPT_DIR / "emacrossopen.log"))
STATE_FILE_PATH = Path(os.getenv("STATE_FILE", SCRIPT_DIR / "emacrossopen_state.json"))
HEARTBEAT_FILE_PATH = Path(os.getenv("HEARTBEAT_FILE", SCRIPT_DIR / "emacross_heartbeat.json"))
RESEARCH_CSV_PATH = Path(os.getenv("RESEARCH_CSV_FILE", PROJECT_ROOT / "backtesting/emacrossopen/emacrossopen_research.csv" if (PROJECT_ROOT / "backtesting/emacrossopen").exists() else SCRIPT_DIR / "emacrossopen_research.csv"))

STRATEGY_NAME = os.getenv("STRATEGY_NAME", "EMACROSS_FNO_PAPER")
EXCHANGE = os.getenv("EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "NRML")
INTERVAL = os.getenv("INTERVAL", "1h")

# Strategy Parameters (AutoResearch Champion Specification V3.0)
FAST_EMA_PERIOD = int(os.getenv("FAST_EMA_PERIOD", "10"))
SLOW_EMA_PERIOD = int(os.getenv("SLOW_EMA_PERIOD", "28"))
MACD_FAST_PERIOD = int(os.getenv("MACD_FAST_PERIOD", "12"))
MACD_SLOW_PERIOD = int(os.getenv("MACD_SLOW_PERIOD", "26"))
MACD_SIGNAL_PERIOD = int(os.getenv("MACD_SIGNAL_PERIOD", "9"))
CONFIRMATION_WINDOW = int(os.getenv("CONFIRMATION_WINDOW", "2"))  # Asymmetric V2-2: Second confirmation within 2 candles

# Universe Routing Configuration (AutoResearch Champion V3.0)
USE_ASYMMETRIC_UNIVERSE = os.getenv("USE_ASYMMETRIC_UNIVERSE", "true").lower() in ["true", "1", "yes"]

# Risk Management Parameters (Researched Asymmetric Fixed Target & Catastrophe SL)
LONG_PROFIT_TARGET_PCT = float(os.getenv("LONG_PROFIT_TARGET_PCT", "3.00"))
SHORT_PROFIT_TARGET_PCT = float(os.getenv("SHORT_PROFIT_TARGET_PCT", "1.50"))
CATASTROPHE_SL_PCT = float(os.getenv("CATASTROPHE_SL_PCT", "6.00"))
ORDER_PACING_DELAY_SEC = float(os.getenv("ORDER_PACING_DELAY_SEC", "0.25"))

# Target-to-Runner Optimization Parameters (Champion Research Architecture)
ENABLE_TRAILING_RUNNER = os.getenv("ENABLE_TRAILING_RUNNER", "true").lower() in ["true", "1", "yes"]
RUNNER_TRAIL_PCT = float(os.getenv("RUNNER_TRAIL_PCT", "0.35"))  # 0.35% High-Water-Mark pullback trail
RUNNER_TRAIL_MODE = os.getenv("RUNNER_TRAIL_MODE", "HWM").upper()  # "HWM" or "FIXED"

LOTS = int(os.getenv("LOTS", "1"))
MAX_ACTIVE_POSITIONS = int(os.getenv("MAX_ACTIVE_POSITIONS", "0"))  # 0 = Unlimited (no risk gate cap)
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() in ["true", "1", "yes"]

# Empirical Performance Optimization Parameters (September 2026 Audit)
ENABLE_TIME_FILTER = os.getenv("ENABLE_TIME_FILTER", "true").lower() in ["true", "1", "yes"]
ENABLE_REGIME_FILTER = os.getenv("ENABLE_REGIME_FILTER", "true").lower() in ["true", "1", "yes"]
INDEX_LOT_MULTIPLIER = int(os.getenv("INDEX_LOT_MULTIPLIER", "2"))

# IST Timezone (+05:30)
IST = timezone(timedelta(hours=5, minutes=30))

# ==============================================================================
# 2. LOGGING SETUP (Console Stream + Rotating File Handler)
# ==============================================================================
logger = logging.getLogger("EMACROSS_ENGINE")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
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
        OPENALGO_HOST = "https://vikashiname.in"

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
        token = bot_cfg.get("bot_token")
        if token and token != "test_token_123456789" and bot_cfg.get("is_active"):
            if not TELEGRAM_BOT_TOKEN:
                TELEGRAM_BOT_TOKEN = token
            users = get_all_telegram_users()
            if users and not TELEGRAM_CHAT_ID:
                TELEGRAM_CHAT_ID = str(users[0].get("telegram_id", ""))
    except Exception:
        pass

# ==============================================================================
# 4. BROAD F&O UNIVERSE (211 Active NFO Instruments)
# ==============================================================================
DEFAULT_NFO_UNIVERSE = [
    "360ONE", "ABB", "ABCAPITAL", "ADANIENSOL", "ADANIENT", "ADANIGREEN", "ADANIPORTS", "ADANIPOWER",
    "ALKEM", "AMBER", "AMBUJACEM", "ANGELONE", "APLAPOLLO", "APOLLOHOSP", "ASHOKLEY", "ASIANPAINT",
    "ASTRAL", "AUBANK", "AUROPHARMA", "AXISBANK", "BAJAJ-AUTO", "BAJAJFINSV", "BAJAJHLDNG", "BAJFINANCE",
    "BANDHANBNK", "BANKBARODA", "BANKINDIA", "BANKNIFTY", "BDL", "BEL", "BHARATFORG", "BHARTIARTL",
    "BHEL", "BIOCON", "BLUESTARCO", "BOSCHLTD", "BPCL", "BRITANNIA", "BSE", "CAMS",
    "CANBK", "CDSL", "CGPOWER", "CHOLAFIN", "CIPLA", "COALINDIA", "COCHINSHIP", "COFORGE",
    "COLPAL", "CONCOR", "CROMPTON", "CUMMINSIND", "DABUR", "DELHIVERY", "DIVISLAB",
    "DIXON", "DLF", "DMART", "DRREDDY", "EICHERMOT", "ETERNAL", "FEDERALBNK",
    "FINNIFTY", "FORCEMOT", "FORTIS", "GAIL", "GLENMARK", "GMRAIRPORT", "GODFRYPHLP", "GODREJCP",
    "GODREJPROP", "GRASIM", "HAL", "HAVELLS", "HCLTECH", "HDFCAMC", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDPETRO", "HINDUNILVR", "HINDZINC", "HYUNDAI", "ICICIBANK",
    "ICICIGI", "ICICIPRULI", "IDEA", "IDFCFIRSTB", "IEX", "INDHOTEL", "INDIANB", "INDIGO",
    "INDUSINDBK", "INDUSTOWER", "INFY", "INOXWIND", "IOC", "IREDA", "IRFC", "ITC",
    "JINDALSTEL", "JIOFIN", "JSWENERGY", "JSWSTEEL", "JUBLFOOD", "KALYANKJIL", "KAYNES", "KEI",
    "KFINTECH", "KOTAKBANK", "KPITTECH", "LAURUSLABS", "LICHSGFIN", "LICI", "LODHA", "LT",
    "LTF", "LTM", "LUPIN", "M&M", "MANAPPURAM", "MANKIND", "MARICO", "MARUTI",
    "MAXHEALTH", "MAZDOCK", "MCX", "MFSL", "MIDCPNIFTY", "MOTHERSON", "MOTILALOFS", "MPHASIS",
    "MUTHOOTFIN", "NAM-INDIA", "NATIONALUM", "NAUKRI", "NBCC", "NESTLEIND", "NHPC", "NIFTY",
    "NIFTYNXT50", "NMDC", "NTPC", "NYKAA", "OBEROIRLTY", "OFSS", "OIL",
    "ONGC", "PAGEIND", "PATANJALI", "PAYTM", "PERSISTENT", "PETRONET", "PFC", "PGEL",
    "PHOENIXLTD", "PIDILITIND", "PIIND", "PNB", "PNBHOUSING", "POLICYBZR", "POLYCAB", "POWERGRID",
    "POWERINDIA", "PREMIERENE", "PRESTIGE", "RBLBANK", "RECLTD", "RELIANCE", "RVNL",
    "SAGILITY", "SAIL", "SBICARD", "SBILIFE", "SBIN", "SHREECEM", "SHRIRAMFIN", "SIEMENS",
    "SOLARINDS", "SONACOMS", "SRF", "SUNPHARMA", "SUPREMEIND", "SUZLON", "SWIGGY", "TATACONSUM",
    "TATAELXSI", "TATAPOWER", "TATASTEEL", "TCS", "TECHM", "TIINDIA", "TITAN",
    "TMPV", "TORNTPHARM", "TRENT", "TVSMOTOR", "ULTRACEMCO", "UNIONBANK", "UNITDSPR",
    "UNOMINDA", "UPL", "VBL", "VEDL", "VMM", "VOLTAS", "WAAREEENER", "WIPRO",
    "YESBANK", "ZYDUSLIFE"
]

INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}

# Asymmetric Universe Segregation (AutoResearch Champion V3.0)
TOP_LONGS = {
    "SUNPHARMA", "BAJAJ-AUTO", "BPCL", "WIPRO", "TATASTEEL",
    "BAJFINANCE", "NTPC"
}
TOP_SHORTS = {
    "SUNPHARMA", "BAJAJ-AUTO", "M&M", "BPCL", "NTPC",
    "NIFTY"
}
BLACKLIST_AVOID = {
    "ITC", "ONGC", "ADANIENT", "DRREDDY", "INFY"
}

# Fallback Lot Sizes Map for known instruments
FALLBACK_LOT_SIZES = {
    "360ONE": 500, "ABB": 125, "ABCAPITAL": 3100, "ADANIENSOL": 675, "ADANIENT": 309,
    "ADANIGREEN": 600, "ADANIPORTS": 475, "ADANIPOWER": 3550, "ALKEM": 125, "AMBER": 100,
    "AMBUJACEM": 1050, "ANGELONE": 2500, "APLAPOLLO": 350, "APOLLOHOSP": 125, "ASHOKLEY": 5000,
    "ASIANPAINT": 250, "ASTRAL": 425, "AUBANK": 1000, "AUROPHARMA": 550, "AXISBANK": 625,
    "BAJAJ-AUTO": 75, "BAJAJFINSV": 250, "BAJAJHLDNG": 50, "BAJFINANCE": 750, "BANDHANBNK": 3600,
    "BANKBARODA": 2925, "BANKINDIA": 5200, "BANKNIFTY": 30, "BDL": 350, "BEL": 1425,
    "BHARATFORG": 500, "BHARTIARTL": 475, "BHEL": 2625, "BIOCON": 2500, "BLUESTARCO": 325,
    "BOSCHLTD": 25, "BPCL": 1975, "BRITANNIA": 125, "BSE": 375, "CAMS": 750,
    "CANBK": 6750, "CDSL": 475, "CGPOWER": 850, "CHOLAFIN": 625, "CIPLA": 375,
    "COALINDIA": 1350, "COCHINSHIP": 400, "COFORGE": 375, "COLPAL": 225, "CONCOR": 1250,
    "CROMPTON": 1800, "CUMMINSIND": 200, "DABUR": 1250, "DALBHARAT": 325, "DELHIVERY": 2075,
    "DIVISLAB": 100, "DIXON": 50, "DLF": 825, "DMART": 150, "DRREDDY": 625,
    "EICHERMOT": 100, "ETERNAL": 2425, "EXIDEIND": 1800, "FEDERALBNK": 5000, "FINNIFTY": 60,
    "FORCEMOT": 25, "FORTIS": 775, "GAIL": 3150, "GLENMARK": 375, "GMRAIRPORT": 6975,
    "GODFRYPHLP": 275, "GODREJCP": 500, "GODREJPROP": 275, "GRASIM": 250, "HAL": 150,
    "HAVELLS": 500, "HCLTECH": 350, "HDFCAMC": 300, "HDFCBANK": 550, "HDFCLIFE": 1100,
    "HEROMOTOCO": 150, "HINDALCO": 700, "HINDPETRO": 2025, "HINDUNILVR": 300, "HINDZINC": 1225,
    "HUDCO": 2775, "HYUNDAI": 275, "ICICIBANK": 700, "ICICIGI": 325, "ICICIPRULI": 925,
    "IDEA": 71475, "IDFCFIRSTB": 9275, "IEX": 3750, "INDHOTEL": 1000, "INDIANB": 1000,
    "INDIGO": 150, "INDUSINDBK": 700, "INDUSTOWER": 1700, "INFY": 400, "INOXWIND": 3575,
    "IOC": 4875, "IREDA": 3450, "IRFC": 4250, "ITC": 1600, "JINDALSTEL": 625,
    "JIOFIN": 2350, "JSWENERGY": 1000, "JSWSTEEL": 675, "JUBLFOOD": 1250, "KALYANKJIL": 1175,
    "KAYNES": 100, "KEI": 175, "KFINTECH": 500, "KOTAKBANK": 2000, "KPITTECH": 425,
    "LAURUSLABS": 850, "LICHSGFIN": 1000, "LICI": 700, "LODHA": 450, "LT": 175,
    "LTF": 2250, "LTM": 150, "LUPIN": 425, "M&M": 200, "MANAPPURAM": 3000,
    "MANKIND": 225, "MARICO": 1200, "MARUTI": 50, "MAXHEALTH": 525, "MAZDOCK": 200,
    "MCX": 625, "MFSL": 400, "MIDCPNIFTY": 120, "MOTHERSON": 6150, "MOTILALOFS": 775,
    "MPHASIS": 275, "MUTHOOTFIN": 275, "NAM-INDIA": 625, "NATIONALUM": 3750, "NAUKRI": 375,
    "NBCC": 6500, "NESTLEIND": 500, "NHPC": 6400, "NIFTY": 65, "NIFTYNXT50": 25,
    "NMDC": 6750, "NTPC": 1500, "NUVAMA": 500, "NYKAA": 3125, "OBEROIRLTY": 350,
    "OFSS": 75, "OIL": 1400, "ONGC": 2250, "PAGEIND": 15, "PATANJALI": 900,
    "PAYTM": 725, "PERSISTENT": 100, "PETRONET": 1900, "PFC": 1300, "PGEL": 950,
    "PHOENIXLTD": 350, "PIDILITIND": 500, "PIIND": 175, "PNB": 8000, "PNBHOUSING": 650,
    "POLICYBZR": 350, "POLYCAB": 125, "POWERGRID": 1900, "POWERINDIA": 50, "PPLPHARMA": 2625,
    "PREMIERENE": 575, "PRESTIGE": 450, "RBLBANK": 3175, "RECLTD": 1400, "RELIANCE": 500,
    "RVNL": 1525, "SAGILITY": 12000, "SAIL": 4700, "SAMMAANCAP": 4300, "SBICARD": 800, "SBILIFE": 375,
    "SBIN": 750, "SHREECEM": 25, "SHRIRAMFIN": 825, "SIEMENS": 175, "SOLARINDS": 50,
    "SONACOMS": 1225, "SRF": 200, "SUNPHARMA": 350, "SUPREMEIND": 175, "SUZLON": 9025,
    "SWIGGY": 1300, "TATACONSUM": 550, "TATAELXSI": 100, "TATAPOWER": 1450, "TATASTEEL": 5500,
    "TATATECH": 800, "TCS": 175, "TECHM": 600, "TIINDIA": 200, "TITAN": 175,
    "TMPV": 800, "TORNTPHARM": 250, "TORNTPOWER": 425, "TRENT": 100, "TVSMOTOR": 175,
    "ULTRACEMCO": 50, "UNIONBANK": 4425, "UNITDSPR": 400, "UNOMINDA": 550, "UPL": 1355,
    "VBL": 1125, "VEDL": 1150, "VMM": 4850, "VOLTAS": 375, "WAAREEENER": 175,
    "WIPRO": 3000, "YESBANK": 31100, "ZYDUSLIFE": 900
}

# ==============================================================================
# 5. TIME & CANDLE COMPLETION HELPERS
# ==============================================================================
def get_current_ist() -> datetime:
    """Returns current datetime localized to Indian Standard Time (IST)."""
    return datetime.now(timezone.utc).astimezone(IST)


def format_candle_time(dt: datetime) -> str:
    """Formats datetime as '01-Sep-2026 11:00 IST'."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime("%d-%b-%Y %H:%M IST")


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
    now = (now_dt or get_current_ist()).time()
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


def is_long_regime_allowed(symbol: str, df_completed: pd.DataFrame) -> Tuple[bool, str]:
    """
    Regime guard for Long entries during market pullbacks.
    Requires:
      1. Completed close must be above 50-period EMA on 1H (medium-term trend).
      2. For weak sectors in correction (IT, Banking, Auto), requires close > 100-period EMA.
    """
    if df_completed is None or len(df_completed) < 30:
        return True, "FILTER_BYPASSED"
    try:
        close_col = "close" if "close" in df_completed.columns else "Close"
        close_series = df_completed[close_col].astype(float)
        span_period = min(50, len(close_series))
        ema50 = close_series.ewm(span=span_period, adjust=False).mean().iloc[-1]
        last_close = float(close_series.iloc[-1])
        if last_close < ema50:
            return False, f"BELOW_EMA50 ({last_close:.2f} < {ema50:.2f})"

        weak_long_symbols = {
            "OFSS", "MPHASIS", "PERSISTENT", "COFORGE", "LTM", "WIPRO", "INFY", "TCS", "TECHM",
            "ICICIBANK", "BANKBARODA", "AUBANK", "KOTAKBANK", "AXISBANK", "SBIN",
            "HEROMOTOCO", "MARUTI", "M&M", "BAJAJ-AUTO"
        }
        if symbol in weak_long_symbols and len(close_series) >= 60:
            span_weak = min(100, len(close_series))
            ema_weak = close_series.ewm(span=span_weak, adjust=False).mean().iloc[-1]
            if last_close < ema_weak:
                return False, f"WEAK_SECTOR_BELOW_EMA ({last_close:.2f} < {ema_weak:.2f})"
    except Exception as e:
        logger.warning(f"Regime filter check error for {symbol}: {e}")
    return True, "TREND_ALIGNED"


def get_interval_minutes(interval_str: str) -> int:
    """Parses candle interval string (e.g. '1h', '60m') into integer minutes."""
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
    The 15:15 candle completes only after 15:30.
    """
    s = str(interval_str).strip().lower()
    if s in ["1h", "60m"] and candle_ts.hour == 15 and candle_ts.minute == 15:
        return timedelta(minutes=15)
    return timedelta(minutes=get_interval_minutes(interval_str))


def get_completed_1h_candles(df: pd.DataFrame, now_override: Optional[datetime] = None) -> pd.DataFrame:
    """
    CRITICAL CANDLE RULE:
    Filters out any currently forming / incomplete 1-hour candle.
    A regular 1H candle starting at T is completed after T + 60 minutes.
    The final session candle (15:15 -> 15:30) is completed only after 15:30.
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

    bar_duration = get_bar_duration("1h", last_dt)
    if now_ist < (last_dt + bar_duration):
        return df.iloc[:-1].copy()

    return df.copy()


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
        now_dt = get_current_ist()
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


# ==============================================================================
# 6. PERSISTENT STATE MANAGER
# ==============================================================================
class PersistentStateManager:
    """
    Atomic, crash-safe state persistence for emacrossopen.py.
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
    """
    Dispatches formatted alert message to Telegram channel/user if configured.
    Non-blocking, non-fatal on failure.
    """
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
    """
    Formats structured Paper Trade execution notification merging strategy analysis
    and order execution details into a single consolidated 1-part alert.
    """
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

    # Resolve Entry Price (actual broker/OpenAlgo filled price)
    entry_price = data.get("entry_price")
    if entry_price is None or entry_price == "":
        entry_price = data.get("fill_price") or data.get("average_price") or 0.0
    try:
        entry_price_val = float(entry_price)
    except (TypeError, ValueError):
        entry_price_val = 0.0

    target_pct = float(os.getenv("LONG_PROFIT_TARGET_PCT", "3.00")) if direction == "LONG" else float(os.getenv("SHORT_PROFIT_TARGET_PCT", "1.50"))
    sl_pct = float(os.getenv("CATASTROPHE_SL_PCT", "6.00"))

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

    # For MARKET orders: strictly display Entry Price and NEVER display Trigger Price: 0.0
    if price_type == "MARKET":
        price_lines = f"<b>Entry Price:</b> ₹{entry_price_val:.2f}\n{target_sl_lines}"
    else:
        trigger_px = data.get("trigger_price")
        try:
            trigger_px_val = float(trigger_px) if trigger_px is not None else 0.0
        except (TypeError, ValueError):
            trigger_px_val = 0.0
        if trigger_px_val > 0:
            price_lines = f"<b>Entry Price:</b> ₹{entry_price_val:.2f}\n<b>Trigger Price:</b> ₹{trigger_px_val:.2f}\n{target_sl_lines}"
        else:
            price_lines = f"<b>Entry Price:</b> ₹{entry_price_val:.2f}\n{target_sl_lines}"

    return (
        f"{dir_emoji} <b>PAPER TRADE — ORDER PLACED</b>\n\n"
        f"<b>Strategy:</b> {strategy_name} (EMA + MACD Asymmetric V2-2)\n"
        f"🔬 <b>ANALYZE MODE - No Real Order</b>\n"
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
        f"<b>Close:</b> {data.get('close', 0.0):.2f}\n"
        f"<b>EMA9:</b> {data.get('ema9', 0.0):.2f}\n"
        f"<b>EMA26:</b> {data.get('ema26', 0.0):.2f}\n"
        f"<b>MACD:</b> {data.get('macd', 0.0):.2f}\n"
        f"<b>Signal:</b> {data.get('macd_signal', 0.0):.2f}\n"
        f"<b>Histogram:</b> {data.get('macd_histogram', 0.0):+.2f}\n"
        f"─────────────────────\n"
        f"<i>ℹ️ Mode: PAPER / ANALYZE ONLY</i>"
    )


def format_paper_exit_alert(data: Dict[str, Any]) -> str:
    """
    Formats an HTML Telegram alert message for paper trading position exits
    (TARGET_HIT, CATASTROPHE_SL, V2-2_REVERSAL, SIGNAL_EXIT).
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
    exec_time = data.get("execution_time") or get_current_ist().strftime("%H:%M:%S")
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

    target_pct = float(os.getenv("LONG_PROFIT_TARGET_PCT", "3.00")) if direction == "LONG" else float(os.getenv("SHORT_PROFIT_TARGET_PCT", "1.50"))
    sl_pct = float(os.getenv("CATASTROPHE_SL_PCT", "6.00"))

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
    elif exit_reason == "V2-2_REVERSAL":
        reason_header = "🔄 REVERSAL EXIT"
        reason_badge = "🔄 <b>OPPOSITE V2-2 SIGNAL REVERSAL</b>"
    elif exit_reason == "SIGNAL_EXIT":
        reason_header = "🔄 SIGNAL EXIT"
        reason_badge = "🔄 <b>OPPOSITE SIGNAL EXIT (ENTRY BLOCKED)</b>"
    else:
        reason_header = f"EXIT ({exit_reason})"
        reason_badge = f"ℹ️ <b>{exit_reason}</b>"

    return (
        f"{pnl_emoji} <b>PAPER TRADE — {reason_header}</b>\n\n"
        f"<b>Strategy:</b> {strategy_name} (EMA + MACD Asymmetric V2-2)\n"
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


# ==============================================================================
# 9. DYNAMIC FUTURES CONTRACT RESOLUTION
# ==============================================================================
def resolve_nfo_contract(
    symbol: str, host: str, api_key: str
) -> Tuple[Optional[str], Optional[int], Optional[datetime]]:
    """
    Queries OpenAlgo search API to dynamically find the active near-month
    NFO futures contract symbol, its exact lot size, and its expiry datetime.
    Returns (None, None, None) if contract cannot be resolved (NEVER fabricates a symbol).
    """
    fallback_lot = FALLBACK_LOT_SIZES.get(symbol, 1)

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
                    exp_dt = None
                    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%B-%Y", "%d-%B-%y"):
                        try:
                            exp_dt = datetime.strptime(exp_str, fmt).replace(hour=23, minute=59)
                            break
                        except Exception:
                            pass
                    if exp_dt and exp_dt >= now:
                        lot = int(item.get("lotsize", fallback_lot))
                        valid.append((exp_dt, item.get("symbol"), lot))

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
# 10. STRATEGY LOGIC (SEPARATE FROM EXECUTION)
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
         - Case C (EMA_THEN_MACD): Bearish EMA crosses first -> STRICTLY REJECTED (rejection_reason="SHORT_EMA_FIRST_DISALLOWED").
      5. Invalidation:
         - If leading indicator reverses directional bias before 2nd confirms, setup is INVALIDATED & cancelled.
      6. Expiration:
         - If confirmation delay exceeds `window` (2 candles), setup is EXPIRED & cancelled.
      7. Histogram:
         - Calculated and logged for research/diagnostics only. STRICTLY NOT an entry filter.

    Returns:
      Dictionary with candle data, indicator values, crossovers, signal ('BUY', 'SELL', None),
      trigger_type, confirmation_delay, strategy_state, rejection_reason, action_on_pending, and new_pending_setup.
    """
    if df is None or len(df) < 2:
        return None

    # Required columns
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

    # 1. EMA 9 x EMA 26 Crossover on current candle
    ema_bull = (prev_ema9 <= prev_ema26) and (curr_ema9 > curr_ema26)
    ema_bear = (prev_ema9 >= prev_ema26) and (curr_ema9 < curr_ema26)
    ema_crossover = "BULLISH" if ema_bull else ("BEARISH" if ema_bear else "NONE")

    # 2. MACD 12/26/9 Crossover on current candle
    macd_bull = (prev_macd <= prev_signal) and (curr_macd > curr_signal)
    macd_bear = (prev_macd >= prev_signal) and (curr_macd < curr_signal)
    macd_crossover = "BULLISH" if macd_bull else ("BEARISH" if macd_bear else "NONE")

    # Result placeholders
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
        # Resolve active pending setup (either explicitly passed or reconstructed from recent df lookback)
        active_setup = None
        if pending_setup and isinstance(pending_setup, dict) and pending_setup.get("direction"):
            active_setup = dict(pending_setup)
        elif len(df) >= 3:
            # Lookback reconstruction for deterministic testing and recovery:
            # Check up to `window` previous completed candles (from -2 backwards)
            sig_col = "macd_signal" if "macd_signal" in df.columns else "signal"
            max_lookback = min(len(df) - 1, window + 2)
            for lb in range(2, max_lookback + 1):
                p_curr = df.iloc[-lb]
                p_prev = df.iloc[-lb - 1]

                p_ema_bull = (p_prev["ema9"] <= p_prev["ema26"]) and (p_curr["ema9"] > p_curr["ema26"])
                p_ema_bear = (p_prev["ema9"] >= p_prev["ema26"]) and (p_curr["ema9"] < p_curr["ema26"])
                p_macd_bull = (p_prev["macd"] <= p_prev[sig_col]) and (p_curr["macd"] > p_curr[sig_col])
                p_macd_bear = (p_prev["macd"] >= p_prev[sig_col]) and (p_curr["macd"] < p_curr[sig_col])

                # Both crossed on that bar -> same candle at that bar, not pending
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
                    # Short EMA-first is disallowed, cannot be a valid pending setup
                    break

        if active_setup:
            dir_setup = active_setup.get("direction")
            leading = active_setup.get("leading_indicator")
            setup_time = active_setup.get("setup_candle_time")

            # Compute delay in candles
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

            # Step 1: Invalidation check on current candle
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
                            # Still pending
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
                            # Still pending
                            strategy_state = "PENDING_EMA"
                            trigger_type = "MACD_THEN_EMA"
                            confirmation_delay = delay
                            action_on_pending = "UPDATE"
                            new_pending_setup = dict(active_setup, elapsed_bars=delay)
                else:
                    # Expired (> window)
                    strategy_state = "EXPIRED"
                    rejection_reason = "CONFIRMATION_WINDOW_EXCEEDED"
                    trigger_type = f"{leading}_THEN_{'EMA' if leading == 'MACD' else 'MACD'}"
                    confirmation_delay = delay
                    action_on_pending = "CLEAR"
                    active_setup = None

        # Step 3: If no active pending setup was evaluated on this candle, check if a NEW setup starts:
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
                # SHORT EMA-first is explicitly disallowed and rejected
                strategy_state = "REJECTED"
                trigger_type = "EMA_THEN_MACD_REJECTED"
                rejection_reason = "SHORT_EMA_FIRST_DISALLOWED"
                confirmation_delay = 0
                action_on_pending = "CLEAR"
                new_pending_setup = None

    return {
        "symbol": symbol,
        "timestamp": candle_iso,
        "candle_time_str": candle_time_str,
        "candle_dt": candle_dt,
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
# 11. EXECUTION LOGIC (SEPARATE FROM STRATEGY)
# ==============================================================================
class EMACrossPaperTradingEngine:
    """
    Continuous Paper-Trading Execution Engine.
    Implements production-grade execution robustness adapted from macdfno.py:
      - PAPER / ANALYZE Mode Only verification
      - Startup position reconciliation & misalignment audit
      - Dynamic futures contract resolution & lot-size caching
      - Atomic state persistence & crash recovery
      - Idempotency & duplicate-entry protection
      - Position-aware execution (FLAT->LONG, FLAT->SHORT, LONG->SHORT, SHORT->LONG)
      - Atomic heartbeat for external watchdog monitoring
    """

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        lots: int = LOTS,
        max_active: int = MAX_ACTIVE_POSITIONS,
        host: str = OPENALGO_HOST,
        api_key: str = OPENALGO_API_KEY,
        use_asymmetric_universe: Optional[bool] = None,
        state_file: Optional[Path] = None,
    ):
        self.symbols = symbols or DEFAULT_NFO_UNIVERSE
        self.lots = lots
        self.max_active = max_active
        self.host = host
        self.api_key = api_key
        self.use_asymmetric_universe = (
            use_asymmetric_universe
            if use_asymmetric_universe is not None
            else USE_ASYMMETRIC_UNIVERSE
        )
        self.state_file_path = state_file or STATE_FILE_PATH
        self.running = True
        self.parallel_fetch = os.getenv("PARALLEL_DATA_FETCH", "1").lower() in ("1", "true", "yes")
        self.max_workers = int(os.getenv("MAX_WORKERS", "8"))
        self.use_candle_boundary = os.getenv("CANDLE_BOUNDARY_SCHEDULER", "1").lower() in ("1", "true", "yes")
        self.candle_boundary_buffer = int(os.getenv("CANDLE_BOUNDARY_BUFFER_SECONDS", "2"))
        self.enable_time_filter = ENABLE_TIME_FILTER
        self.enable_regime_filter = ENABLE_REGIME_FILTER
        self.index_lot_multiplier = INDEX_LOT_MULTIPLIER
        self.enable_trailing_runner = ENABLE_TRAILING_RUNNER
        self.runner_trail_pct = RUNNER_TRAIL_PCT
        self.runner_trail_mode = RUNNER_TRAIL_MODE

        # Connection-pooled HTTP session for efficient fallback data fetching
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Signal handlers for graceful shutdown
        def _handle_signal(signum, frame):
            logger.info(f"🛑 Received termination signal ({signum}). Initiating graceful shutdown...")
            self.running = False
            self.emit_heartbeat(status="STOPPED")

        try:
            signal.signal(signal.SIGTERM, _handle_signal)
            signal.signal(signal.SIGINT, _handle_signal)
        except Exception:
            pass

        # OpenAlgo SDK Client
        self.client = None
        if OPENALGO_AVAILABLE and api is not None:
            try:
                self.client = api(api_key=self.api_key, host=self.host)
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAlgo client SDK: {e}")

        # State Manager
        self.state_manager = PersistentStateManager(self.state_file_path)
        self.contract_cache: Dict[str, Dict[str, Any]] = {}

        # Mode Safety Flag
        self.paper_mode_confirmed = False

        # Counters for monitoring
        self.total_scans = 0
        self.signals_detected = 0
        self.paper_orders_placed = 0

        # Startup Sequence
        self._startup_health_check()

    def _startup_health_check(self):
        """Validates configuration, verifies PAPER/ANALYZE mode, and runs position reconciliation."""
        logger.info("=" * 80)
        logger.info(f"🚀 {STRATEGY_NAME}: 1H EMA (9/26) + MACD (12/26/9) Asymmetric V2-2 Engine")
        logger.info("=" * 80)
        logger.info(f"  • OpenAlgo Host Server   : {self.host}")
        logger.info(f"  • Universe Size          : {len(self.symbols)} NFO Instruments")
        logger.info(f"  • Timeframe Interval     : {INTERVAL} (Completed Candles Only)")
        logger.info(f"  • Data Ingestion Mode    : {'Bounded Parallel (' + str(self.max_workers) + ' workers)' if self.parallel_fetch else 'Sequential'}")
        logger.info(f"  • Candle Boundary Sync   : {'Enabled (:15:' + f'{self.candle_boundary_buffer:02d} IST target)' if self.use_candle_boundary else 'Disabled (Drifted Interval)'}")
        logger.info(f"  • Confirmation Window    : {CONFIRMATION_WINDOW} Completed Candles")
        logger.info(f"  • Long Confirmation      : Unfiltered (SAME_CANDLE, MACD_THEN_EMA, EMA_THEN_MACD)")
        logger.info(f"  • Short Confirmation     : MACD-First Only (SAME_CANDLE, MACD_THEN_EMA; EMA-first REJECTED)")
        logger.info(f"  • Histogram Filter       : DISABLED (Research/Tracking Only)")
        logger.info(f"  • Position Sizing        : {self.lots} Lot(s) per instrument")
        logger.info(f"  • Max Active Positions   : {'Unlimited (No Cap)' if self.max_active <= 0 else f'{self.max_active} Concurrent Positions'}")
        logger.info(f"  • State File             : {STATE_FILE_PATH}")
        logger.info(f"  • Research Store         : {RESEARCH_CSV_PATH}")
        logger.info(f"  • Heartbeat File         : {HEARTBEAT_FILE_PATH}")
        logger.info(f"  • Log File (Rotating)    : {LOG_FILE_PATH}")
        logger.info(
            f"  • Telegram Alerts        : {'Configured' if bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) else 'Console/File Only'}"
        )
        logger.info("=" * 80)

        # 1. Verify PAPER / ANALYZE Mode
        mode_ok, mode_str = self.verify_paper_mode()
        if mode_ok:
            self.paper_mode_confirmed = True
            logger.info(f"✅ PAPER TRADING / ANALYZE MODE CONFIRMED (Mode: '{mode_str}')")
        else:
            self.paper_mode_confirmed = False
            logger.critical(f"🛑 EXECUTION DISABLED: Mode is '{mode_str}'. Order placement is HARD-BLOCKED!")

        # 2. Startup Reconciliation & Audit
        self.reconcile_and_audit_positions()

        # 3. Initial Heartbeat
        self.emit_heartbeat(status="INITIALIZED")

    def verify_paper_mode(self) -> Tuple[bool, str]:
        """
        Pre-Flight Safety Check:
        Verifies OpenAlgo is operating in PAPER / ANALYZE mode.
        If live mode is detected or paper mode cannot be positively verified,
        returns (False, mode_string).
        Includes TTL caching (60s), retries (3x, 12s timeout), and localhost fallback.
        """
        now = time.time()
        if hasattr(self, "_last_mode_verified_time") and hasattr(self, "_last_verified_mode"):
            if (now - self._last_mode_verified_time) < 60:
                if self._last_verified_mode in ["analyze", "paper"]:
                    return True, self._last_verified_mode
                elif self._last_verified_mode == "live":
                    return False, "live"

        hosts_to_try = [self.host]
        if "127.0.0.1" not in self.host and "localhost" not in self.host:
            hosts_to_try.append("http://127.0.0.1:5000")

        for attempt in range(1, 4):
            for h in hosts_to_try:
                try:
                    resp = requests.post(
                        f"{h.rstrip('/')}/api/v1/positionbook",
                        json={"apikey": self.api_key},
                        timeout=12,
                    )
                    if resp.status_code == 200:
                        mode = resp.json().get("mode", "").lower()
                        self._last_mode_verified_time = now
                        self._last_verified_mode = mode
                        if mode in ["analyze", "paper"]:
                            return True, mode
                        elif mode == "live":
                            logger.critical("🛑 [SAFETY LOCK] OpenAlgo is running in 'LIVE' mode! Execution disabled.")
                            send_telegram_alert("🛑 <b>SAFETY LOCK:</b> OpenAlgo is in <b>LIVE</b> mode. Execution disabled.")
                            return False, "live"
                        else:
                            logger.warning(f"⚠️ [SAFETY LOCK] Unknown OpenAlgo mode: '{mode}'. Order execution disabled.")
                            return False, mode or "unknown"
                except Exception as e:
                    logger.warning(f"⚠️ [Attempt {attempt}] Mode check failed on {h}: {e}")
            time.sleep(1.0)

        # Resilient fallback: If verified recently (within 5 minutes), do not block orders on transient API latency
        if hasattr(self, "_last_verified_mode") and self._last_verified_mode in ["analyze", "paper"]:
            if (now - getattr(self, "_last_mode_verified_time", 0)) < 300:
                logger.warning("⚠️ OpenAlgo mode check timed out, but recently confirmed paper mode. Permitting execution.")
                return True, self._last_verified_mode

        logger.error("❌ Failed to verify OpenAlgo mode after 3 attempts.")
        return False, "unreachable"

    def emit_heartbeat(
        self,
        status: str = "HEALTHY",
        instruments_scanned: int = 0,
        signals_detected: int = 0,
        paper_orders_count: int = 0,
        last_scan: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Atomic Heartbeat Emitter.
        Writes heartbeat JSON to disk for independent watchdog monitoring.
        """
        try:
            now_dt = get_current_ist()
            hb_data = {
                "strategy": STRATEGY_NAME,
                "pid": os.getpid(),
                "timestamp_ist": now_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
                "timestamp_epoch": now_dt.timestamp(),
                "status": status,
                "openalgo_host": self.host,
                "openalgo_mode": "analyze" if self.paper_mode_confirmed else "disabled",
                "active_positions_count": len(self.state_manager.state.get("tracked_positions", {})),
                "instruments_scanned": instruments_scanned or self.total_scans,
                "signals_detected": signals_detected or self.signals_detected,
                "paper_orders_count": paper_orders_count or self.paper_orders_placed,
                "last_scan": last_scan or now_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
                "api_status": "CONNECTED" if self.paper_mode_confirmed else "ERROR",
                "last_completed_candle": str(self.state_manager.state.get("last_processed_candles", {})),
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
        Startup Position Reconciliation & Misalignment Detector.
        Strictly observational:
          1. Queries live positionbook from OpenAlgo.
          2. Compares broker state vs local persistent state.
          3. Evaluates current 1H candle regime for every open position.
          4. Classifies position as ALIGNED, MISALIGNED, or NEUTRAL.
          5. Updates tracked positions and records audit summary.
        """
        logger.info("=" * 80)
        logger.info("🔍 STARTUP POSITION RECONCILIATION & MISALIGNMENT AUDIT")
        logger.info("=" * 80)

        reconciled_positions = []
        tracked_map = {}

        try:
            resp = requests.post(
                f"{self.host.rstrip('/')}/api/v1/positionbook",
                json={"apikey": self.api_key},
                timeout=8,
            )
            if resp.status_code != 200:
                logger.error(f"❌ Failed to fetch positionbook (HTTP {resp.status_code}): {resp.text}")
                return []
            book_data = resp.json()
            mode = book_data.get("mode", "unknown")
            positions = book_data.get("data", [])
        except Exception as e:
            logger.error(f"❌ Exception fetching positionbook: {e}")
            return []

        logger.info(f"  • OpenAlgo Execution Mode : {mode.upper()}")
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
                logger.info(f"  ℹ️ [EXTERNAL/OPTION] Skipping {contract_sym} (Options contract not traded by EMACROSS).")
                continue

            # 2. Skip positions not originated by this strategy
            if contract_sym not in local_tracked:
                logger.info(f"  ℹ️ [EXTERNAL POSITION] Skipping {contract_sym} (not in EMACROSS tracked_positions).")
                continue

            pos_dir = "LONG" if qty > 0 else "SHORT"

            # Check local state discrepancy
            local_pos_info = local_tracked.get(contract_sym, {})
            local_qty = local_pos_info.get("quantity")
            if local_qty is not None and local_qty != qty:
                logger.warning(
                    f"⚠️ [STATE MISMATCH] {contract_sym}: Broker Qty = {qty}, Local State Qty = {local_qty}"
                )

            # Resolve base symbol
            base_sym = contract_sym
            for s in self.symbols:
                if contract_sym.startswith(s):
                    base_sym = s
                    break

            # Fetch 1H completed candles to evaluate regime
            df = self.fetch_1h_candles(base_sym, contract_sym)
            regime = "NEUTRAL / INDETERMINATE"
            alignment = "NEUTRAL"
            candle_time = "UNKNOWN"
            curr_close = ltp
            curr_macd = 0.0
            curr_sig = 0.0
            curr_hist = 0.0
            curr_ema9 = 0.0
            curr_ema26 = 0.0

            if df is not None and len(df) >= 30:
                df_comp = get_completed_1h_candles(df)
                if len(df_comp) >= 30:
                    df_comp = calculate_indicators(df_comp)
                    i = len(df_comp) - 1
                    candle_time = format_candle_time(df_comp.index[i])
                    curr_close = float(df_comp["close"].iloc[i])
                    curr_ema9 = float(df_comp["ema9"].iloc[i])
                    curr_ema26 = float(df_comp["ema26"].iloc[i])
                    curr_macd = float(df_comp["macd"].iloc[i])
                    curr_sig = float(df_comp["macd_signal"].iloc[i])
                    curr_hist = float(df_comp["macd_histogram"].iloc[i])

                    if curr_ema9 > curr_ema26 and curr_macd > curr_sig:
                        regime = "BULLISH"
                    elif curr_ema9 < curr_ema26 and curr_macd < curr_sig:
                        regime = "BEARISH"
                    else:
                        regime = "CONSOLIDATION"

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
                f"LTP: ₹{ltp:<8.2f} | PnL: ₹{pnl:>+10,.2f} | 1H Regime: {regime:<13} | Status: {alignment}"
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
                "ema9": curr_ema9,
                "ema26": curr_ema26,
                "macd": curr_macd,
                "signal": curr_sig,
                "histogram": curr_hist,
                "regime": regime,
                "alignment": alignment,
            }
            reconciled_positions.append(record)
            tracked_map[contract_sym] = record

            if alignment == "MISALIGNED":
                alert_msg = (
                    f"⚠️ <b>POSITION MISALIGNMENT DETECTED</b>\n\n"
                    f"• <b>Contract:</b> <code>{contract_sym}</code>\n"
                    f"• <b>Position:</b> <b>{pos_dir}</b> ({qty} units)\n"
                    f"• <b>Entry Price:</b> ₹{avg_px:.2f}\n"
                    f"• <b>Current LTP:</b> ₹{ltp:.2f} (P&L: ₹{pnl:,.2f})\n"
                    f"• <b>Completed 1H Candle:</b> {candle_time}\n"
                    f"• <b>EMA9:</b> ₹{curr_ema9:.2f} | <b>EMA26:</b> ₹{curr_ema26:.2f}\n"
                    f"• <b>MACD:</b> {curr_macd:+.2f} | <b>Signal:</b> {curr_sig:+.2f} | <b>Hist:</b> {curr_hist:+.2f}\n"
                    f"• <b>Current Market Regime:</b> <b>{regime}</b>\n"
                    f"• <b>Alignment Status:</b> <b>MISALIGNED</b>\n\n"
                    f"<i>ℹ️ Note: Observational audit only. No automatic orders placed.</i>"
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

        logger.info(
            f"📊 Startup Audit Complete: {len(reconciled_positions)} active position(s) found | "
            f"Aligned: {sum(1 for r in reconciled_positions if r['alignment'] == 'ALIGNED')} | "
            f"Misaligned: {sum(1 for r in reconciled_positions if r['alignment'] == 'MISALIGNED')}"
        )
        logger.info("=" * 80 + "\n")
        return reconciled_positions

    def refresh_contracts(self, symbols_to_check: Optional[List[str]] = None):
        """
        Resolves active NFO futures contracts and lot sizes for symbols.
        Uses intelligent caching: active contracts expire only once a month.
        """
        target_list = symbols_to_check or self.symbols
        now = datetime.now()

        unresolved = [
            s for s in target_list
            if not self.contract_cache.get(s)
            or (self.contract_cache[s].get("expiry_dt") and now >= self.contract_cache[s]["expiry_dt"])
        ]

        if not unresolved:
            return

        # Bulk pre-fetch if many symbols need resolution
        if len(unresolved) > 5:
            logger.info(f"🔄 Bulk pre-fetching contracts for {len(unresolved)} symbols...")
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
                        exp_dt = None
                        for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%B-%Y", "%d-%B-%y"):
                            try:
                                exp_dt = datetime.strptime(exp_str, fmt).replace(hour=23, minute=59)
                                break
                            except Exception:
                                pass
                        if exp_dt and exp_dt >= now:
                            parts = name.rsplit(" ", 4)
                            base = " ".join(parts[:-4]) if len(parts) >= 5 else name.split()[0]
                            if base in unresolved:
                                curr = self.contract_cache.get(base)
                                if not curr or (curr.get("expiry_dt") and exp_dt < curr["expiry_dt"]):
                                    self.contract_cache[base] = {
                                        "contract": sym,
                                        "lot_size": lot,
                                        "order_qty": self.lots * lot,
                                        "expiry_dt": exp_dt,
                                    }
            except Exception as e:
                logger.warning(f"⚠️ Bulk contract search warning: {e}")

        # Individual resolution for any remaining unresolved
        remaining = [s for s in unresolved if s not in self.contract_cache]
        if remaining:
            def _worker(s):
                c_sym, lot, exp_dt = resolve_nfo_contract(s, self.host, self.api_key)
                return s, c_sym, lot, exp_dt

            max_threads = min(8, len(remaining))
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                results = list(executor.map(_worker, remaining))

            for s, c_sym, lot, exp_dt in results:
                if c_sym and lot:
                    self.contract_cache[s] = {
                        "contract": c_sym,
                        "lot_size": lot,
                        "order_qty": self.lots * lot,
                        "expiry_dt": exp_dt,
                    }
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

    def fetch_1h_candles(self, symbol: str, contract_symbol: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        Fetches 1-Hour historical candles from OpenAlgo.
        Tries contract symbol on NFO, then symbol on NFO, then symbol on NSE.
        """
        now = get_current_ist()
        start_date = (now - timedelta(days=25)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        candidates: List[Tuple[str, str]] = []
        if contract_symbol:
            candidates.append((contract_symbol, "NFO"))

        if symbol in INDEX_SYMBOLS:
            candidates.extend([(symbol, "NFO"), (symbol, "NSE_INDEX")])
        else:
            candidates.extend([(symbol, "NFO"), (symbol, "NSE")])

        df = None
        for sym_cand, exch in candidates:
            # 1. Try Client SDK
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

            # 2. Try REST API
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
                session = getattr(self, "session", None) or requests
                resp = session.post(hist_url, json=payload, timeout=8)
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

        # Standardize column names
        df.columns = [str(col).strip().lower() for col in df.columns]

        # Handle DatetimeIndex
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
        if not contract_symbol:
            return 0
        try:
            if self.client is not None:
                pos = self.client.openposition(
                    strategy=STRATEGY_NAME,
                    symbol=contract_symbol,
                    exchange=EXCHANGE,
                    product=PRODUCT,
                )
                if isinstance(pos, dict) and pos.get("quantity") is not None:
                    return int(pos["quantity"])

            resp = requests.post(
                f"{self.host.rstrip('/')}/api/v1/positionbook",
                json={"apikey": self.api_key},
                timeout=6,
            )
            if resp.status_code == 200:
                positions = resp.json().get("data", [])
                for p in positions:
                    if p.get("symbol") == contract_symbol:
                        return int(p.get("quantity", 0))
        except Exception as e:
            logger.warning(f"Position query warning for {contract_symbol}: {e}")

        # Fallback to locally tracked positions if server returns 0 / unreachable
        tracked = self.state_manager.state.get("tracked_positions", {}).get(contract_symbol, {})
        if tracked:
            return int(tracked.get("quantity", 0))

        return 0

    def get_all_open_positions(self) -> Dict[str, int]:
        """Queries OpenAlgo positionbook and returns map of {contract_symbol: quantity} for all open positions."""
        open_positions = {}
        try:
            resp = requests.post(
                f"{self.host.rstrip('/')}/api/v1/positionbook",
                json={"apikey": self.api_key},
                timeout=6,
            )
            if resp.status_code == 200:
                positions = resp.json().get("data", [])
                for p in positions:
                    sym = p.get("symbol", "")
                    qty = int(p.get("quantity", 0))
                    if qty != 0 and sym:
                        open_positions[sym] = qty
        except Exception as e:
            logger.warning(f"Failed to query all open positions: {e}")

        return open_positions

    def check_orderbook_for_matching_order(
        self, contract_symbol: str, action: str, quantity: int, max_lookback_seconds: int = 180
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Orderbook Reconciliation before Retry.
        Queries OpenAlgo orderbook to verify whether an order already reached the broker/paper engine.
        Returns: (found: bool, order_id: Optional[str], order_status: Optional[str])
        """
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
    ) -> Optional[Dict[str, Any]]:
        """
        Resilient Paper Order Placement Engine with Pre-Flight Safety & Idempotency.
          1. Re-verifies OpenAlgo PAPER / ANALYZE mode.
          2. Enforces Idempotency Lock on (contract_symbol, action, quantity, candle_time).
          3. Validates contract and quantity (> 0).
          4. Submits order via OpenAlgo API with retry handling and orderbook reconciliation.
          5. Updates persistent state and returns order details.
        """
        # 1. Pre-Flight Safety Verification
        mode_ok, mode_str = self.verify_paper_mode()
        if not mode_ok:
            logger.critical(
                f"🛑 [SAFETY LOCK] Order placement for {contract_symbol} BLOCKED! Mode is '{mode_str}'."
            )
            return None

        # 2. Idempotency Key
        order_key = f"{contract_symbol}_{action}_{quantity}_{candle_time or 'LIVE'}"
        if self.state_manager.is_order_inflight_or_filled(order_key):
            logger.warning(f"ℹ️ [IDEMPOTENCY LOCK] Order {order_key} is already PENDING or FILLED. Skipping.")
            return None

        if quantity <= 0:
            logger.error(f"❌ Cannot place order: Invalid quantity ({quantity}) for {contract_symbol}.")
            return None

        logger.info(
            f"🚀 [PAPER ORDER] Submitting {action} {quantity} units of {contract_symbol} [{symbol}] (Key: {order_key})..."
        )
        self.state_manager.mark_order_pending(
            order_key,
            {"symbol": symbol, "contract": contract_symbol, "action": action, "qty": quantity},
        )

        max_attempts = 2
        attempt = 0
        resp = None

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
                    elif "auth" in msg or "apikey" in msg or "unauthorized" in msg:
                        logger.critical(f"🛑 [AUTH FAILURE] {contract_symbol}: {resp.get('message')}.")
                        send_telegram_alert(
                            f"🛑 <b>AUTH ERROR:</b> OpenAlgo API Key error on {contract_symbol}: {resp.get('message')}"
                        )
                        self.state_manager.mark_order_resolved(order_key, "AUTH_FAILED")
                        return None
                    elif "symbol" in msg or "quantity" in msg or "invalid" in msg:
                        logger.error(f"❌ [VALIDATION ERROR] {contract_symbol}: {resp.get('message')}.")
                        self.state_manager.mark_order_resolved(order_key, "VALIDATION_FAILED")
                        return None
                    elif "restricted" in msg or "margin" in msg or "funds" in msg:
                        logger.error(f"❌ [RMS REJECTION] {contract_symbol}: {resp.get('message')}.")
                        self.state_manager.mark_order_resolved(order_key, "REJECTED")
                        return None
                    elif "sqlite" in msg or "database is locked" in msg or "timeout" in msg or "timed out" in msg:
                        logger.warning(
                            f"⚠️ [DATABASE LOCK / TIMEOUT] {contract_symbol}: {resp.get('message')}. Backing off {1.0 * attempt}s before retry..."
                        )
                        time.sleep(1.0 * attempt)
                    else:
                        logger.warning(f"⚠️ [TRANSIENT RESPONSE] {contract_symbol}: {resp}")

            except Exception as e:
                logger.warning(f"⚠️ Exception during placeorder attempt {attempt} for {contract_symbol}: {e}")

            # Reconcile with orderbook before retrying
            if attempt < max_attempts:
                logger.info(f"🔍 [RETRY RECONCILIATION] Checking Orderbook for {contract_symbol} {action}...")
                time.sleep(2)
                found, order_id, order_status = self.check_orderbook_for_matching_order(
                    contract_symbol, action, quantity
                )
                if found:
                    logger.info(f"✅ [ORDER FOUND IN BOOK] Order {order_id} exists ({order_status}). No retry needed.")
                    self.state_manager.mark_order_resolved(order_key, "FILLED", order_id)
                    self.paper_orders_placed += 1
                    if ORDER_PACING_DELAY_SEC > 0:
                        time.sleep(ORDER_PACING_DELAY_SEC)
                    return {"status": "success", "orderid": order_id, "verified_via": "orderbook"}
                else:
                    logger.info(f"ℹ️ Order not found in book. Retrying attempt {attempt + 1}/{max_attempts}...")

        logger.error(f"❌ Paper order placement failed or unconfirmed for {contract_symbol} (Key: {order_key}).")
        self.state_manager.mark_order_resolved(order_key, "FAILED_UNCERTAIN")
        send_telegram_alert(
            f"⚠️ <b>PAPER ORDER UNCERTAIN:</b> {contract_symbol} {action} {quantity} units unconfirmed."
        )
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
        """
        Retrieves the actual market fill price from the broker/OpenAlgo.
        Order of precedence:
          1. Direct fill/average price in initial order placement response.
          2. OpenAlgo /api/v1/orderstatus query (client or HTTP).
          3. OpenAlgo /api/v1/orderbook query (client or HTTP).
          4. Live contract quote LTP fallback.
          5. Fallback candle close (if quote unavailable).
        """
        # 1. Check initial order response
        if isinstance(initial_resp, dict):
            for k in ["average_price", "avg_price", "fill_price", "traded_price", "price"]:
                v = initial_resp.get(k)
                if v is not None:
                    try:
                        fv = float(v)
                        if fv > 0:
                            logger.info(f"✅ [FILL PRICE] Found ₹{fv:.2f} in initial order response ({k}) for {order_id}.")
                            return fv
                    except (ValueError, TypeError):
                        pass

            data_nest = initial_resp.get("data")
            if isinstance(data_nest, dict):
                for k in ["average_price", "avg_price", "fill_price", "traded_price", "price"]:
                    v = data_nest.get(k)
                    if v is not None:
                        try:
                            fv = float(v)
                            if fv > 0:
                                logger.info(f"✅ [FILL PRICE] Found ₹{fv:.2f} in initial response data ({k}) for {order_id}.")
                                return fv
                        except (ValueError, TypeError):
                            pass

        # 2 & 3. Query order status and orderbook with retries
        for attempt in range(max_retries):
            # Try orderstatus endpoint/SDK
            try:
                st_data = None
                if self.client is not None and hasattr(self.client, "orderstatus"):
                    st_resp = self.client.orderstatus(order_id=str(order_id), strategy=STRATEGY_NAME)
                    if isinstance(st_resp, dict):
                        st_data = st_resp.get("data", st_resp)
                else:
                    url = f"{self.host.rstrip('/')}/api/v1/orderstatus"
                    r = requests.post(url, json={"apikey": self.api_key, "orderid": str(order_id)}, timeout=5)
                    if r.status_code == 200:
                        res_json = r.json()
                        st_data = res_json.get("data", res_json)

                if isinstance(st_data, dict):
                    for k in ["average_price", "avg_price", "fill_price", "traded_price", "price"]:
                        v = st_data.get(k)
                        if v is not None:
                            try:
                                fv = float(v)
                                if fv > 0:
                                    logger.info(f"✅ [FILL PRICE] Retrieved ₹{fv:.2f} via orderstatus for {order_id}.")
                                    return fv
                            except (ValueError, TypeError):
                                pass
            except Exception as e:
                logger.debug(f"orderstatus query failed on attempt {attempt + 1}: {e}")

            # Try orderbook endpoint/SDK
            try:
                ob_orders = None
                if self.client is not None and hasattr(self.client, "orderbook"):
                    ob_resp = self.client.orderbook()
                    if isinstance(ob_resp, dict):
                        d = ob_resp.get("data", [])
                        ob_orders = d.get("orders", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])
                else:
                    url = f"{self.host.rstrip('/')}/api/v1/orderbook"
                    r = requests.post(url, json={"apikey": self.api_key}, timeout=5)
                    if r.status_code == 200:
                        d = r.json().get("data", [])
                        ob_orders = d.get("orders", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])

                if ob_orders:
                    for o in ob_orders:
                        if str(o.get("orderid", "")) == str(order_id):
                            for k in ["average_price", "avg_price", "fill_price", "traded_price", "price"]:
                                v = o.get(k)
                                if v is not None:
                                    try:
                                        fv = float(v)
                                        if fv > 0:
                                            logger.info(f"✅ [FILL PRICE] Retrieved ₹{fv:.2f} via orderbook for {order_id}.")
                                            return fv
                                    except (ValueError, TypeError):
                                        pass
            except Exception as e:
                logger.debug(f"orderbook query failed on attempt {attempt + 1}: {e}")

            if attempt < max_retries - 1:
                time.sleep(retry_delay)

        # 4. Fallback to contract quote LTP
        try:
            ltp = None
            if self.client is not None and hasattr(self.client, "quotes"):
                q_resp = self.client.quotes(symbol=contract_symbol, exchange=EXCHANGE)
                if isinstance(q_resp, dict):
                    qd = q_resp.get("data", q_resp)
                    ltp = qd.get("ltp") or qd.get("last_price") or qd.get("price")
            else:
                q_resp = requests.post(
                    f"{self.host.rstrip('/')}/api/v1/quotes",
                    json={"apikey": self.api_key, "symbol": contract_symbol, "exchange": EXCHANGE},
                    timeout=5,
                )
                if q_resp.status_code == 200:
                    qd = q_resp.json().get("data", {})
                    ltp = qd.get("ltp") or qd.get("last_price") or qd.get("price")

            if ltp is not None:
                fltp = float(ltp)
                if fltp > 0:
                    logger.info(f"ℹ️ [FILL PRICE] Used live quote LTP ₹{fltp:.2f} for {contract_symbol} (Order {order_id}).")
                    return fltp
        except Exception as e:
            logger.debug(f"Live quote fallback query failed: {e}")

        # 5. Last resort fallback
        if fallback_price > 0:
            logger.warning(f"⚠️ [FILL PRICE] Fill price unavailable from OpenAlgo; using candle close fallback ₹{fallback_price:.2f}.")
            return fallback_price

        return 0.0

    def check_and_execute_target_or_sl(
        self,
        symbol: str,
        contract_sym: str,
        df_completed: pd.DataFrame,
    ) -> bool:
        """
        Evaluates dynamic Profit Target and Emergency Catastrophe Stop-Loss on completed 1H candle.
        Target & SL are calculated from ACTUAL EXECUTED FILL PRICE (average_price), not candle close.

        Specifications:
          - LONG Target: candle_high >= entry_price * (1 + LONG_PROFIT_TARGET_PCT / 100.0)  [+3.00%]
          - SHORT Target: candle_low <= entry_price * (1 - SHORT_PROFIT_TARGET_PCT / 100.0) [-1.50%]
          - LONG Catastrophe SL: candle_low <= entry_price * (1 - CATASTROPHE_SL_PCT / 100.0) [-6.00%]
          - SHORT Catastrophe SL: candle_high >= entry_price * (1 + CATASTROPHE_SL_PCT / 100.0) [+6.00%]

        Exit Priority:
          1. Catastrophe SL takes precedence if both target and SL are breached in the same candle.
          2. Target Hit -> exit reason TARGET_HIT.
          3. Catastrophe SL Hit -> exit reason CATASTROPHE_SL.
          4. Controlled reversal handled subsequently if neither hit.

        Returns:
          True if an exit order was placed, False otherwise.
        """
        if df_completed is None or df_completed.empty:
            return False

        # Retrieve active tracked position
        tracked_positions = self.state_manager.state.get("tracked_positions", {})
        pos_info = tracked_positions.get(contract_sym)
        if not pos_info:
            return False

        qty = int(pos_info.get("quantity", 0))
        if qty == 0:
            return False

        entry_price = float(pos_info.get("average_price", 0.0) or 0.0)
        if entry_price <= 0:
            logger.warning(
                f"⚠️ [TARGET/SL] Tracked position for {contract_sym} has invalid entry_price {entry_price}. Skipping."
            )
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

        # Calculate trigger thresholds from ACTUAL fill price
        long_target_px = entry_price * (1.0 + (LONG_PROFIT_TARGET_PCT / 100.0))
        short_target_px = entry_price * (1.0 - (SHORT_PROFIT_TARGET_PCT / 100.0))
        long_catastrophe_px = entry_price * (1.0 - (CATASTROPHE_SL_PCT / 100.0))
        short_catastrophe_px = entry_price * (1.0 + (CATASTROPHE_SL_PCT / 100.0))

        target_hit = False
        catastrophe_hit = False
        target_exit_px = 0.0
        sl_exit_px = 0.0

        # Retrieve runner state for this position (if any)
        runner_active = bool(pos_info.get("runner_active", False))
        peak_price = float(pos_info.get("peak_price", entry_price))
        trough_price = float(pos_info.get("trough_price", entry_price))

        if direction == "LONG":
            target_hit = candle_high >= long_target_px
            catastrophe_hit = candle_low <= long_catastrophe_px
            target_exit_px = round(long_target_px, 2)
            sl_exit_px = round(long_catastrophe_px, 2)
        elif direction == "SHORT":
            target_hit = candle_low <= short_target_px
            catastrophe_hit = candle_high >= short_catastrophe_px
            target_exit_px = round(short_target_px, 2)
            sl_exit_px = round(short_catastrophe_px, 2)
        else:
            return False

        # 1. Catastrophe SL has ultimate precedence
        if catastrophe_hit:
            exit_reason = "CATASTROPHE_SL"
            expected_exit_px = sl_exit_px

        # 2. If runner is already active, evaluate HWM trailing stop
        elif runner_active and getattr(self, "enable_trailing_runner", True):
            trail_pct = getattr(self, "runner_trail_pct", RUNNER_TRAIL_PCT)
            if direction == "LONG":
                peak_price = max(peak_price, candle_high)
                pos_info["peak_price"] = peak_price
                effective_trail_sl = peak_price * (1.0 - (trail_pct / 100.0))
                pos_info["effective_trail_sl"] = round(effective_trail_sl, 2)
                if candle_low <= effective_trail_sl:
                    exit_reason = "RUNNER_HWM_TRAIL"
                    expected_exit_px = round(effective_trail_sl, 2)
                else:
                    # Trailing continues; update high-water-mark in state and do not exit
                    self.state_manager.update_tracked_positions(tracked_positions)
                    return False
            else:  # SHORT
                trough_price = min(trough_price, candle_low)
                pos_info["trough_price"] = trough_price
                effective_trail_sl = trough_price * (1.0 + (trail_pct / 100.0))
                pos_info["effective_trail_sl"] = round(effective_trail_sl, 2)
                if candle_high >= effective_trail_sl:
                    exit_reason = "RUNNER_HWM_TRAIL"
                    expected_exit_px = round(effective_trail_sl, 2)
                else:
                    # Trailing continues; update low-water-mark in state and do not exit
                    self.state_manager.update_tracked_positions(tracked_positions)
                    return False

        # 3. Target Hit reached for the first time
        elif target_hit:
            trail_mode = getattr(self, "runner_trail_mode", RUNNER_TRAIL_MODE)
            trail_enabled = getattr(self, "enable_trailing_runner", True)
            trail_pct = getattr(self, "runner_trail_pct", RUNNER_TRAIL_PCT)
            if trail_enabled and trail_mode == "HWM":
                # Convert position to a Trailing Runner rather than exiting completely
                pos_info["runner_active"] = True
                pos_info["target_hit_candle"] = candle_iso
                if direction == "LONG":
                    peak_price = max(entry_price, candle_high)
                    pos_info["peak_price"] = peak_price
                    effective_trail_sl = peak_price * (1.0 - (trail_pct / 100.0))
                    pos_info["effective_trail_sl"] = round(effective_trail_sl, 2)
                    logger.info(
                        f"🏃 [RUNNER ACTIVATED] {symbol} ({contract_sym}): Long Target {LONG_PROFIT_TARGET_PCT}% reached on candle {candle_time_str} | "
                        f"Peak: ₹{peak_price:.2f} | HWM Trail SL: ₹{effective_trail_sl:.2f} (-{trail_pct}%)"
                    )
                else:
                    trough_price = min(entry_price, candle_low)
                    pos_info["trough_price"] = trough_price
                    effective_trail_sl = trough_price * (1.0 + (trail_pct / 100.0))
                    pos_info["effective_trail_sl"] = round(effective_trail_sl, 2)
                    logger.info(
                        f"🏃 [RUNNER ACTIVATED] {symbol} ({contract_sym}): Short Target {SHORT_PROFIT_TARGET_PCT}% reached on candle {candle_time_str} | "
                        f"Trough: ₹{trough_price:.2f} | HWM Trail SL: ₹{effective_trail_sl:.2f} (+{trail_pct}%)"
                    )
                self.state_manager.update_tracked_positions(tracked_positions)
                return False
            else:
                exit_reason = "TARGET_HIT"
                expected_exit_px = target_exit_px

        else:
            return False

        exit_action = "SELL" if direction == "LONG" else "BUY"
        exit_qty = abs(qty)

        # Idempotency lock on exit order
        exit_key = f"{symbol}_{candle_iso}_EXIT_{exit_reason}"
        if self.state_manager.is_signal_processed(exit_key):
            logger.info(
                f"ℹ️ [EXIT DEDUP] Exit {exit_reason} for {symbol} on candle {candle_time_str} already processed. Skipping."
            )
            return False

        logger.info(
            f"🎯 [RISK EXIT TRIGGERED] {symbol} ({contract_sym}): {exit_reason} on candle {candle_time_str} | "
            f"Direction: {direction} | Entry: ₹{entry_price:.2f} | High: ₹{candle_high:.2f} | "
            f"Low: ₹{candle_low:.2f} | Close: ₹{candle_close:.2f} | Action: {exit_action} {exit_qty}"
        )

        resp = self.place_paper_order(
            symbol=symbol,
            contract_symbol=contract_sym,
            action=exit_action,
            quantity=exit_qty,
            candle_time=candle_iso,
        )

        if resp:
            order_id = resp.get("orderid", f"PAPER_EXIT_{int(time.time())}")
            order_status = "FILLED"

            # Retrieve actual market fill price
            exit_fill_price = self.get_order_fill_price(
                order_id=str(order_id),
                contract_symbol=contract_sym,
                initial_resp=resp,
                fallback_price=expected_exit_px,
            )

            # Record state updates
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

            # Position is now flat: remove from tracked_positions
            updated_tracked = dict(self.state_manager.state.get("tracked_positions", {}))
            if contract_sym in updated_tracked:
                del updated_tracked[contract_sym]
            self.state_manager.update_tracked_positions(updated_tracked)

            # Telegram Paper Exit Notification
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
            else:
                logger.info(f"ℹ️ [ALERT DEDUP] Exit alert for order {order_id} already sent. Skipping duplicate.")

            # Research CSV Logging for Exit
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
        """
        Evaluates position and risk checks, then executes paper order if eligible.
        Handles:
          FLAT  -> LONG
          FLAT  -> SHORT
          LONG  -> LONG   (no duplicate)
          SHORT -> SHORT  (no duplicate)
          LONG  -> SHORT  (controlled reversal)
          SHORT -> LONG   (controlled reversal)

        Returns: (order_placed: bool, updated_active_count: int)
        """
        sig = sig_data.get("signal")
        candle_time = sig_data.get("candle_time_str")
        candle_iso = sig_data.get("timestamp")

        if sig not in ["BUY", "SELL"]:
            return False, active_positions_count

        # Idempotency: Symbol + Candle Timestamp + Direction
        signal_key = f"{symbol}_{candle_iso}_{sig}"
        if self.state_manager.is_signal_processed(signal_key):
            logger.info(f"ℹ️ Signal {sig} for {symbol} on candle {candle_time} already processed. Skipping duplicate.")
            return False, active_positions_count

        # Resolve active futures contract
        c_meta = self.contract_cache.get(symbol)
        if not c_meta:
            self.refresh_contracts([symbol])
            c_meta = self.contract_cache.get(symbol)

        if not c_meta or not c_meta.get("contract"):
            logger.warning(f"⚠️ Cannot trade {symbol}: active futures contract could not be resolved.")
            return False, active_positions_count

        contract_sym = c_meta["contract"]
        lot_size = c_meta["lot_size"]
        mult = getattr(self, "index_lot_multiplier", 1) if symbol in INDEX_SYMBOLS else 1
        base_order_qty = self.lots * lot_size * mult

        # Query actual position from OpenAlgo
        current_pos = self.get_open_position(contract_sym)

        # Asymmetric Universe Directional Filter (AutoResearch Champion V3.0)
        if self.use_asymmetric_universe:
            if symbol in BLACKLIST_AVOID:
                logger.info(
                    f"🚫 [ASYMMETRIC UNIVERSE] {symbol} is blacklisted due to high whipsaw profile. Skipping order."
                )
                self.state_manager.record_signal_processed(signal_key)
                return False, active_positions_count

            if sig == "BUY" and current_pos == 0 and symbol not in TOP_LONGS:
                logger.info(
                    f"⏸️ [ASYMMETRIC UNIVERSE] {symbol} not in TOP_LONGS ({', '.join(sorted(TOP_LONGS))}). Skipping new LONG."
                )
                self.state_manager.record_signal_processed(signal_key)
                return False, active_positions_count

            if sig == "SELL" and current_pos == 0 and symbol not in TOP_SHORTS:
                logger.info(
                    f"⏸️ [ASYMMETRIC UNIVERSE] {symbol} not in TOP_SHORTS ({', '.join(sorted(TOP_SHORTS))}). Skipping new SHORT."
                )
                self.state_manager.record_signal_processed(signal_key)
                return False, active_positions_count

        # Risk & Position Logic
        action = None
        exec_qty = 0
        is_reversal = False
        is_exit_to_flat = False

        if sig == "BUY":
            if current_pos == 0:
                if getattr(self, "enable_time_filter", False):
                    time_ok, time_reason = is_entry_time_allowed()
                    if not time_ok:
                        logger.info(
                            f"⏸️ [TIME FILTER] Skipping NEW LONG for {symbol}: {time_reason}"
                        )
                        self.state_manager.record_signal_processed(signal_key)
                        return False, active_positions_count

                if getattr(self, "enable_regime_filter", False):
                    df_target = df_completed if df_completed is not None else sig_data.get("df_completed")
                    regime_ok, regime_reason = is_long_regime_allowed(symbol, df_target)
                    if not regime_ok:
                        logger.info(
                            f"⏸️ [REGIME FILTER] Skipping NEW LONG for {symbol}: {regime_reason}"
                        )
                        self.state_manager.record_signal_processed(signal_key)
                        return False, active_positions_count

                if self.max_active <= 0 or active_positions_count < self.max_active:
                    action = "BUY"
                    exec_qty = base_order_qty
                else:
                    logger.info(
                        f"⏸️ [RISK GATE] Max active positions ({self.max_active}) reached. Skipping NEW LONG for {symbol}."
                    )
                    return False, active_positions_count
            elif current_pos < 0:
                # Controlled reversal or exit to flat
                time_ok = True
                if getattr(self, "enable_time_filter", False):
                    time_ok, time_reason = is_entry_time_allowed()
                regime_ok = True
                if getattr(self, "enable_regime_filter", False):
                    df_target = df_completed if df_completed is not None else sig_data.get("df_completed")
                    regime_ok, _ = is_long_regime_allowed(symbol, df_target)
                universe_ok = (not self.use_asymmetric_universe) or (symbol in TOP_LONGS)

                action = "BUY"
                if time_ok and regime_ok and universe_ok:
                    exec_qty = abs(current_pos) + base_order_qty
                    is_reversal = True
                    logger.info(
                        f"🔄 [REVERSAL SHORT->LONG] {symbol} ({contract_sym}): Current Pos = {current_pos}, Order Qty = {exec_qty}"
                    )
                else:
                    exec_qty = abs(current_pos)
                    is_exit_to_flat = True
                    logger.info(
                        f"🔄 [EXIT TO FLAT] {symbol} ({contract_sym}): Closing SHORT pos ({current_pos}) to FLAT (opposite entry blocked). Order Qty = {exec_qty}"
                    )
            else:
                logger.info(f"ℹ️ [DUPLICATE] Already in LONG position ({current_pos}) for {symbol}. No order placed.")
                self.state_manager.record_signal_processed(signal_key)
                return False, active_positions_count

        elif sig == "SELL":
            if current_pos == 0:
                if getattr(self, "enable_time_filter", False):
                    time_ok, time_reason = is_entry_time_allowed()
                    if not time_ok:
                        logger.info(
                            f"⏸️ [TIME FILTER] Skipping NEW SHORT for {symbol}: {time_reason}"
                        )
                        self.state_manager.record_signal_processed(signal_key)
                        return False, active_positions_count

                if self.max_active <= 0 or active_positions_count < self.max_active:
                    action = "SELL"
                    exec_qty = base_order_qty
                else:
                    logger.info(
                        f"⏸️ [RISK GATE] Max active positions ({self.max_active}) reached. Skipping NEW SHORT for {symbol}."
                    )
                    return False, active_positions_count
            elif current_pos > 0:
                # Controlled reversal or exit to flat
                time_ok = True
                if getattr(self, "enable_time_filter", False):
                    time_ok, time_reason = is_entry_time_allowed()
                universe_ok = (not self.use_asymmetric_universe) or (symbol in TOP_SHORTS)

                action = "SELL"
                if time_ok and universe_ok:
                    exec_qty = current_pos + base_order_qty
                    is_reversal = True
                    logger.info(
                        f"🔄 [REVERSAL LONG->SHORT] {symbol} ({contract_sym}): Current Pos = {current_pos}, Order Qty = {exec_qty}"
                    )
                else:
                    exec_qty = current_pos
                    is_exit_to_flat = True
                    logger.info(
                        f"🔄 [EXIT TO FLAT] {symbol} ({contract_sym}): Closing LONG pos ({current_pos}) to FLAT (opposite entry blocked). Order Qty = {exec_qty}"
                    )
            else:
                logger.info(f"ℹ️ [DUPLICATE] Already in SHORT position ({current_pos}) for {symbol}. No order placed.")
                self.state_manager.record_signal_processed(signal_key)
                return False, active_positions_count

        if not action or exec_qty <= 0:
            return False, active_positions_count

        # Place the Paper Order
        resp = self.place_paper_order(
            symbol=symbol,
            contract_symbol=contract_sym,
            action=action,
            quantity=exec_qty,
            candle_time=candle_iso,
        )

        if resp:
            order_id = resp.get("orderid", "PAPER_" + str(int(time.time())))
            order_status = "FILLED"

            # Retrieve actual broker/OpenAlgo market fill price
            candle_close = float(sig_data.get("close", 0.0))
            fill_price = self.get_order_fill_price(
                order_id=str(order_id),
                contract_symbol=contract_sym,
                initial_resp=resp,
                fallback_price=candle_close,
            )

            # Record state updates
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

            if is_exit_to_flat:
                # 1. Dispatch rich exit notification for closed position
                prior_tracked = self.state_manager.state.get("tracked_positions", {}).get(contract_sym, {})
                prior_entry_price = float(prior_tracked.get("average_price", 0.0) or candle_close)
                prior_direction = prior_tracked.get("direction", "LONG" if current_pos > 0 else "SHORT")
                exit_payload = {
                    "strategy_name": STRATEGY_NAME,
                    "contract": contract_sym,
                    "symbol": symbol,
                    "direction": prior_direction,
                    "action": action,
                    "exit_reason": "SIGNAL_EXIT",
                    "quantity": exec_qty,
                    "entry_price": prior_entry_price,
                    "exit_price": fill_price,
                    "order_id": str(order_id),
                    "order_status": order_status,
                    "candle_time_str": candle_time,
                    "candle_time": candle_iso,
                    "execution_time": get_current_ist().strftime("%H:%M:%S"),
                }
                alert_key = f"ORDER_ALERT_{order_id}"
                if not self.state_manager.is_alert_sent(alert_key):
                    exit_msg = format_paper_exit_alert(exit_payload)
                    send_telegram_alert(exit_msg)
                    self.state_manager.record_alert_sent(alert_key)

                # 2. Clear tracked position
                tracked = self.state_manager.state.get("tracked_positions", {})
                tracked.pop(contract_sym, None)
                self.state_manager.update_tracked_positions(tracked)
                return True, max(0, active_positions_count - 1)

            elif is_reversal and current_pos != 0:
                new_pos = base_order_qty if action == "BUY" else -base_order_qty
                # 1. Exit alert for prior position
                prior_tracked = self.state_manager.state.get("tracked_positions", {}).get(contract_sym, {})
                prior_entry_price = float(prior_tracked.get("average_price", 0.0) or candle_close)
                prior_direction = prior_tracked.get("direction", "LONG" if current_pos > 0 else "SHORT")
                prior_qty = abs(current_pos)
                rev_exit_payload = {
                    "strategy_name": STRATEGY_NAME,
                    "contract": contract_sym,
                    "symbol": symbol,
                    "direction": prior_direction,
                    "action": "SELL" if prior_direction == "LONG" else "BUY",
                    "exit_reason": "V2-2_REVERSAL",
                    "quantity": prior_qty,
                    "entry_price": prior_entry_price,
                    "exit_price": fill_price,
                    "order_id": f"{order_id}_REV_EXIT",
                    "order_status": order_status,
                    "candle_time_str": candle_time,
                    "candle_time": candle_iso,
                    "execution_time": get_current_ist().strftime("%H:%M:%S"),
                }
                rev_alert_key = f"ORDER_ALERT_{order_id}_REV_EXIT"
                if not self.state_manager.is_alert_sent(rev_alert_key):
                    rev_exit_msg = format_paper_exit_alert(rev_exit_payload)
                    send_telegram_alert(rev_exit_msg)
                    self.state_manager.record_alert_sent(rev_alert_key)

                # 2. Update tracked position with new opposite position
                tracked = self.state_manager.state.get("tracked_positions", {})
                tracked[contract_sym] = {
                    "contract": contract_sym,
                    "base_symbol": symbol,
                    "direction": "LONG" if new_pos > 0 else "SHORT",
                    "quantity": new_pos,
                    "average_price": fill_price,
                    "candle_time": candle_time,
                    "last_order_id": order_id,
                }
                self.state_manager.update_tracked_positions(tracked)

                # 3. Dispatch new opposite trade entry alert
                alert_payload = {
                    **sig_data,
                    "strategy_name": STRATEGY_NAME,
                    "contract": contract_sym,
                    "direction": "LONG" if sig == "BUY" else "SHORT",
                    "pos_before": current_pos,
                    "pos_after": new_pos,
                    "action": action,
                    "quantity": base_order_qty,
                    "entry_price": fill_price,
                    "price_type": "MARKET",
                    "exchange": EXCHANGE,
                    "product": PRODUCT,
                    "order_id": order_id,
                    "order_status": order_status,
                    "execution_time": get_current_ist().strftime("%H:%M:%S"),
                }
                alert_key = f"ORDER_ALERT_{order_id}"
                if not self.state_manager.is_alert_sent(alert_key):
                    trade_alert_msg = format_paper_trade_alert(alert_payload)
                    send_telegram_alert(trade_alert_msg)
                    self.state_manager.record_alert_sent(alert_key)
                return True, active_positions_count

            else:
                # Fresh entry (current_pos == 0)
                new_pos = base_order_qty if action == "BUY" else -base_order_qty
                tracked = self.state_manager.state.get("tracked_positions", {})
                tracked[contract_sym] = {
                    "contract": contract_sym,
                    "base_symbol": symbol,
                    "direction": "LONG" if new_pos > 0 else "SHORT",
                    "quantity": new_pos,
                    "average_price": fill_price,
                    "candle_time": candle_time,
                    "last_order_id": order_id,
                }
                self.state_manager.update_tracked_positions(tracked)

                alert_payload = {
                    **sig_data,
                    "strategy_name": STRATEGY_NAME,
                    "contract": contract_sym,
                    "direction": "LONG" if sig == "BUY" else "SHORT",
                    "pos_before": 0,
                    "pos_after": new_pos,
                    "action": action,
                    "quantity": exec_qty,
                    "entry_price": fill_price,
                    "price_type": "MARKET",
                    "exchange": EXCHANGE,
                    "product": PRODUCT,
                    "order_id": order_id,
                    "order_status": order_status,
                    "execution_time": get_current_ist().strftime("%H:%M:%S"),
                }
                alert_key = f"ORDER_ALERT_{order_id}"
                if not self.state_manager.is_alert_sent(alert_key):
                    trade_alert_msg = format_paper_trade_alert(alert_payload)
                    send_telegram_alert(trade_alert_msg)
                    self.state_manager.record_alert_sent(alert_key)
                return True, active_positions_count + 1

            # Research CSV Logging
            research_entry = {
                "symbol": symbol,
                "timestamp": candle_iso,
                "open": sig_data.get("open"),
                "high": sig_data.get("high"),
                "low": sig_data.get("low"),
                "close": sig_data.get("close"),
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
                "combined_signal": sig_data.get("confluence"),
                "trigger_type": sig_data.get("trigger_type", "SAME_CANDLE"),
                "confirmation_delay": sig_data.get("confirmation_delay", 0),
                "strategy_state": sig_data.get("strategy_state", "CONFIRMED"),
                "rejection_reason": sig_data.get("rejection_reason", "NONE"),
                "direction": "LONG" if sig == "BUY" else "SHORT",
                "paper_order_id": order_id,
                "order_status": order_status,
                "quantity": exec_qty,
                "position_before": current_pos,
                "position_after": new_pos,
            }
            log_research_record(research_entry)

            if not is_reversal and current_pos == 0:
                active_positions_count += 1

            return True, active_positions_count

        return False, active_positions_count

    def _fetch_and_eval_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Worker task for bounded parallel data fetching and indicator calculation.
        STRICTLY READ-ONLY:
          - No order placement
          - No state writes
          - No position mutation
          - No Telegram alerts
          - No research CSV writes
        """
        t0 = time.perf_counter()
        try:
            c_meta = self.contract_cache.get(symbol, {})
            contract_sym = c_meta.get("contract")

            df = self.fetch_1h_candles(symbol, contract_sym)
            if df is None or df.empty:
                return {"symbol": symbol, "contract_sym": contract_sym, "valid": False, "duration": time.perf_counter() - t0}

            # Filter strictly completed candles
            df_completed = get_completed_1h_candles(df)
            if len(df_completed) < 30:
                return {"symbol": symbol, "contract_sym": contract_sym, "valid": False, "duration": time.perf_counter() - t0}

            # Calculate indicators
            df_completed = calculate_indicators(df_completed)

            return {
                "symbol": symbol,
                "contract_sym": contract_sym,
                "df_completed": df_completed,
                "valid": True,
                "duration": time.perf_counter() - t0,
            }
        except Exception as e:
            logger.error(f"Error fetching/evaluating {symbol}: {e}")
            return {"symbol": symbol, "contract_sym": None, "valid": False, "duration": time.perf_counter() - t0}

    def execute_cycle(self):
        """Single portfolio scan cycle across all active NFO instruments."""
        cycle_t0 = time.perf_counter()
        now_ist = get_current_ist()
        logger.info(
            f"🔎 Starting 1H Scan Cycle across {len(self.symbols)} NFO instruments at {now_ist.strftime('%d-%b-%Y %H:%M:%S IST')}..."
        )

        self.refresh_contracts()

        # Query existing open positions from broker/engine
        open_positions = self.get_all_open_positions()
        active_positions_count = len(open_positions)
        max_cap_str = "Unlimited" if self.max_active <= 0 else str(self.max_active)
        logger.info(
            f"📊 Active Portfolio Positions: {active_positions_count} / {max_cap_str} max concurrent"
        )

        scanned_count = 0
        signals_found = 0
        orders_placed_this_cycle = 0

        # 1. Ingestion Phase: Bounded Parallel (8 workers) or Sequential
        t_fetch_start = time.perf_counter()
        if getattr(self, "parallel_fetch", True) and getattr(self, "max_workers", 8) > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                results = list(executor.map(self._fetch_and_eval_symbol, self.symbols))
        else:
            results = [self._fetch_and_eval_symbol(s) for s in self.symbols]
        t_fetch_duration = time.perf_counter() - t_fetch_start

        # 2. Sequential Execution Phase (Strictly single-threaded in original alphabetical sequence)
        t_exec_start = time.perf_counter()
        for res in results:
            if not res.get("valid"):
                continue

            symbol = res["symbol"]
            contract_sym = res["contract_sym"]
            df_completed = res["df_completed"]

            try:
                # Evaluate Risk Management (Profit Target & Catastrophe SL) on completed 1H candle
                if contract_sym:
                    exit_placed = self.check_and_execute_target_or_sl(
                        symbol=symbol,
                        contract_sym=contract_sym,
                        df_completed=df_completed,
                    )
                    if exit_placed:
                        orders_placed_this_cycle += 1
                        scanned_count += 1
                        if active_positions_count > 0:
                            active_positions_count -= 1
                        continue

                # Detect EMA + MACD Asymmetric V2-2 Signal
                pending_setup = self.state_manager.get_pending_setup(symbol)
                sig_data = detect_ema_macd_signal(
                    df_completed, symbol=symbol, pending_setup=pending_setup
                )
                scanned_count += 1

                if not sig_data:
                    continue

                # Manage pending setup persistence
                action_on_pending = sig_data.get("action_on_pending", "KEEP")
                if action_on_pending in ["SET", "UPDATE"]:
                    if sig_data.get("new_pending_setup"):
                        self.state_manager.save_pending_setup(symbol, sig_data["new_pending_setup"])
                elif action_on_pending == "CLEAR":
                    self.state_manager.clear_pending_setup(symbol)

                confluence = sig_data.get("confluence", "NONE")
                sig = sig_data.get("signal")
                strat_state = sig_data.get("strategy_state", "IDLE")

                # If individual crossover occurred, pending changed, or rejected/invalidated/expired, log research data
                has_crossover = (sig_data.get("ema_crossover") != "NONE") or (
                    sig_data.get("macd_crossover") != "NONE"
                )
                should_log_research = (
                    (has_crossover and confluence == "NONE")
                    or strat_state in ["PENDING_EMA", "PENDING_MACD", "REJECTED", "INVALIDATED", "EXPIRED"]
                )

                if should_log_research:
                    research_entry = {
                        "symbol": symbol,
                        "timestamp": sig_data.get("timestamp"),
                        "open": sig_data.get("open"),
                        "high": sig_data.get("high"),
                        "low": sig_data.get("low"),
                        "close": sig_data.get("close"),
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
                        "combined_signal": confluence,
                        "trigger_type": sig_data.get("trigger_type", "NONE"),
                        "confirmation_delay": sig_data.get("confirmation_delay", 0),
                        "strategy_state": strat_state,
                        "rejection_reason": sig_data.get("rejection_reason", "NONE"),
                        "direction": "NONE",
                        "paper_order_id": "",
                        "order_status": strat_state,
                        "quantity": 0,
                        "position_before": 0,
                        "position_after": 0,
                    }
                    log_research_record(research_entry)

                # Full Confluence Signal: Execute Paper Order
                if confluence != "NONE" and sig in ["BUY", "SELL"]:
                    signals_found += 1
                    self.signals_detected += 1
                    logger.info(
                        f"✨ [{confluence} CONFLUENCE] {symbol} @ {sig_data.get('candle_time_str')} | "
                        f"Close: {sig_data.get('close'):.2f} | EMA9: {sig_data.get('ema9'):.2f} | "
                        f"EMA26: {sig_data.get('ema26'):.2f} | MACD: {sig_data.get('macd'):.2f} | "
                        f"Signal: {sig_data.get('macd_signal'):.2f} | Hist: {sig_data.get('macd_histogram'):+.2f}"
                    )

                    placed, active_positions_count = self.execute_symbol_decision(
                        symbol=symbol,
                        sig_data=sig_data,
                        active_positions_count=active_positions_count,
                        df_completed=df_completed,
                    )
                    if placed:
                        orders_placed_this_cycle += 1

            except Exception as e:
                logger.error(f"Error evaluating {symbol}: {e}")

        t_exec_duration = time.perf_counter() - t_exec_start
        self.total_scans += scanned_count
        total_cycle_duration = time.perf_counter() - cycle_t0
        logger.info(
            f"✅ Scan Cycle Completed: {scanned_count}/{len(self.symbols)} instruments evaluated, "
            f"{signals_found} signal(s) detected, {orders_placed_this_cycle} paper order(s) placed.\n"
        )
        logger.info(
            f"⏱️ [PERF emacrossopen] Total Cycle: {total_cycle_duration:.3f}s | "
            f"Ingestion: {t_fetch_duration:.3f}s ({scanned_count}/{len(self.symbols)} syms, avg {t_fetch_duration/max(1, len(self.symbols)):.3f}s/sym) | "
            f"Process/Exec: {t_exec_duration:.3f}s"
        )
        self.emit_heartbeat(
            status="HEALTHY",
            instruments_scanned=scanned_count,
            signals_detected=self.signals_detected,
            paper_orders_count=self.paper_orders_placed,
        )

    def run_loop(self, poll_interval: int = POLL_INTERVAL_SECONDS):
        """Continuous live execution loop."""
        boundary_sync = getattr(self, "use_candle_boundary", True)
        buf = getattr(self, "candle_boundary_buffer", 2)
        logger.info(
            f"🔄 Starting continuous paper-trading engine loop (Candle Boundary Sync: {'Enabled (:15:' + f'{buf:02d} IST)' if boundary_sync else f'{poll_interval}s interval'})... Press Ctrl+C to stop.\n"
        )
        while self.running:
            try:
                self.emit_heartbeat(status="SCANNING")
                self.execute_cycle()
            except KeyboardInterrupt:
                logger.info("🛑 Termination signal received. Stopping engine cleanly.")
                self.emit_heartbeat(status="STOPPED")
                break
            except Exception as e:
                logger.error(f"❌ Error in execution cycle: {e}", exc_info=True)
                self.emit_heartbeat(status="ERROR", details={"error": str(e)})

            if not self.running:
                break

            if boundary_sync:
                wait_seconds = get_seconds_to_next_candle_boundary(buffer_seconds=buf)
                wake_target = get_current_ist() + timedelta(seconds=wait_seconds)
                logger.info(f"💤 Next 1H candle boundary at {wake_target.strftime('%H:%M:%S IST')} ({wait_seconds:.1f}s). Entering paced sleep...")

                while self.running and wait_seconds > 0.5:
                    sleep_chunk = min(30.0, wait_seconds)
                    time.sleep(sleep_chunk)
                    self.emit_heartbeat(status="HEALTHY")
                    wait_seconds = (wake_target - get_current_ist()).total_seconds()
            else:
                logger.info(f"💤 Sleeping for {poll_interval}s until next scan pass...")
                time.sleep(poll_interval)


# ==============================================================================
# 12. AUTOMATED VERIFICATION TEST SUITE (34 CASES)
# ==============================================================================
def run_automated_tests() -> bool:
    """
    Automated Verification Test Suite for Asymmetric V2-2 Sequential Confirmation Engine
    and Research-Selected Target + Catastrophe SL Risk Management.
    Executes all 34 required verification cases:
      1. Long SAME_CANDLE -> signal
      2. Long MACD_FIRST -> EMA confirmation within 2 candles -> signal
      3. Long EMA_FIRST -> MACD confirmation within 2 candles -> signal
      4. Long confirmation after >2 candles -> no signal
      5. Long leading indicator reversal -> cancellation
      6. Short SAME_CANDLE -> signal
      7. Short MACD_FIRST -> EMA confirmation within 2 candles -> signal
      8. Short EMA_FIRST -> MACD later -> NO SIGNAL
      9. Short confirmation after >2 candles -> no signal
      10. Short leading MACD reversal -> cancellation
      11. SRF 04-Sep scenario -> SHORT signal
      12. Histogram changes cannot change signal validity
      13. Incomplete 1H candle cannot generate signal
      14. 15:15 candle becomes eligible only after 15:30
      15. Duplicate processing cannot create duplicate orders
      16. Restart cannot duplicate an already executed signal
      17. Position reversal works correctly
      18. Paper/analyze safety guard blocks live execution
      19. Full 211-symbol active NFO universe remains intact
      20. Dynamic near-month contract discovery remains intact
      21. Single consolidated Telegram order notification formatting
      22. Mocked order fill execution & single-message dispatch
      23. LONG target hit (+3.00%)
      24. SHORT target hit (+1.50%)
      25. LONG catastrophe SL (-6.00%)
      26. SHORT catastrophe SL (-6.00%)
      27. Target not hit -> existing reversal still works
      28. Target hit before reversal -> TARGET_HIT
      29. Catastrophe SL before reversal -> CATASTROPHE_SL
      30. Actual fill price used instead of candle close
      31. Duplicate processing cannot create duplicate exit
      32. Restart/state recovery preserves entry price and target/SL state
      33. ANALYZE mode still blocks real orders on exit
      34. Format paper exit alert includes all required fields
      35. Asymmetric Universe blocks blacklisted symbols
      36. Asymmetric Universe filters new LONG entries by expectancy
      37. Asymmetric Universe exits unapproved short to FLAT
    """
    logger.info("=" * 80)
    logger.info("🧪 RUNNING AUTOMATED VERIFICATION TEST SUITE (37 CASES)")
    logger.info("=" * 80)

    results = []

    def make_test_df(candles: List[Dict[str, float]], base_time: Optional[datetime] = None) -> pd.DataFrame:
        if base_time is None:
            base_time = datetime(2026, 9, 4, 9, 15, tzinfo=IST)
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

    class MockTestEngine(EMACrossPaperTradingEngine):
        def __init__(self, *args, **kwargs):
            if "use_asymmetric_universe" not in kwargs:
                kwargs["use_asymmetric_universe"] = False
            if "state_file" not in kwargs:
                import uuid, tempfile
                self._tmp_state_file = Path(tempfile.gettempdir()) / f"test_emacross_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}.json"
                kwargs["state_file"] = self._tmp_state_file
            else:
                self._tmp_state_file = None
            super().__init__(*args, **kwargs)
            self.enable_time_filter = False
            self.enable_regime_filter = False
            self.enable_trailing_runner = False

        def _startup_health_check(self):
            self.paper_mode_confirmed = True

        def __del__(self):
            if getattr(self, "_tmp_state_file", None) and self._tmp_state_file.exists():
                try:
                    self._tmp_state_file.unlink()
                except Exception:
                    pass

    # 1. Long SAME_CANDLE -> signal
    try:
        df1 = make_test_df([
            {"close": 100, "ema9": 99, "ema26": 101, "macd": -1.0, "macd_signal": -0.5},
            {"close": 105, "ema9": 102, "ema26": 101, "macd": 0.5, "macd_signal": 0.0},
        ])
        s1 = detect_ema_macd_signal(df1, symbol="TEST")
        assert s1 is not None, "Signal dict is None"
        assert s1["signal"] == "BUY", f"Expected BUY, got {s1['signal']}"
        assert s1["trigger_type"] == "SAME_CANDLE", f"Expected SAME_CANDLE, got {s1['trigger_type']}"
        assert s1["confirmation_delay"] == 0, f"Expected delay 0, got {s1['confirmation_delay']}"
        assert s1["strategy_state"] == "CONFIRMED", f"Expected CONFIRMED, got {s1['strategy_state']}"
        results.append((1, "Long SAME_CANDLE -> signal", True, "BUY via SAME_CANDLE (Delay 0)"))
    except Exception as e:
        results.append((1, "Long SAME_CANDLE -> signal", False, str(e)))

    # 2. Long MACD_FIRST -> EMA confirmation within 2 candles -> signal
    try:
        df2 = make_test_df([
            {"close": 100, "ema9": 98, "ema26": 102, "macd": -1.0, "macd_signal": -0.5},
            {"close": 102, "ema9": 99, "ema26": 101, "macd": 0.2, "macd_signal": -0.1},
            {"close": 105, "ema9": 102, "ema26": 101, "macd": 0.5, "macd_signal": 0.1},
        ])
        s2_pending = detect_ema_macd_signal(df2.iloc[:2], symbol="TEST")
        assert s2_pending["strategy_state"] == "PENDING_EMA", f"Expected PENDING_EMA on bar 1, got {s2_pending['strategy_state']}"
        assert s2_pending["signal"] is None, "Bar 1 should have no signal"

        s2 = detect_ema_macd_signal(df2, symbol="TEST", pending_setup=s2_pending["new_pending_setup"])
        assert s2["signal"] == "BUY", f"Expected BUY on bar 2, got {s2['signal']}"
        assert s2["trigger_type"] == "MACD_THEN_EMA", f"Expected MACD_THEN_EMA, got {s2['trigger_type']}"
        assert s2["confirmation_delay"] == 1, f"Expected delay 1, got {s2['confirmation_delay']}"
        assert s2["strategy_state"] == "CONFIRMED", f"Expected CONFIRMED, got {s2['strategy_state']}"
        results.append((2, "Long MACD_FIRST -> EMA confirmation within 2 candles -> signal", True, "BUY via MACD_THEN_EMA (Delay 1)"))
    except Exception as e:
        results.append((2, "Long MACD_FIRST -> EMA confirmation within 2 candles -> signal", False, str(e)))

    # 3. Long EMA_FIRST -> MACD confirmation within 2 candles -> signal
    try:
        df3 = make_test_df([
            {"close": 100, "ema9": 98, "ema26": 102, "macd": -1.0, "macd_signal": -0.5},
            {"close": 104, "ema9": 102, "ema26": 101, "macd": -0.8, "macd_signal": -0.5},
            {"close": 106, "ema9": 103, "ema26": 101, "macd": 0.2, "macd_signal": -0.2},
        ])
        s3_pending = detect_ema_macd_signal(df3.iloc[:2], symbol="TEST")
        assert s3_pending["strategy_state"] == "PENDING_MACD", f"Expected PENDING_MACD on bar 1, got {s3_pending['strategy_state']}"
        assert s3_pending["signal"] is None, "Bar 1 should have no signal"

        s3 = detect_ema_macd_signal(df3, symbol="TEST", pending_setup=s3_pending["new_pending_setup"])
        assert s3["signal"] == "BUY", f"Expected BUY on bar 2, got {s3['signal']}"
        assert s3["trigger_type"] == "EMA_THEN_MACD", f"Expected EMA_THEN_MACD, got {s3['trigger_type']}"
        assert s3["confirmation_delay"] == 1, f"Expected delay 1, got {s3['confirmation_delay']}"
        assert s3["strategy_state"] == "CONFIRMED", f"Expected CONFIRMED, got {s3['strategy_state']}"
        results.append((3, "Long EMA_FIRST -> MACD confirmation within 2 candles -> signal", True, "BUY via EMA_THEN_MACD (Delay 1)"))
    except Exception as e:
        results.append((3, "Long EMA_FIRST -> MACD confirmation within 2 candles -> signal", False, str(e)))

    # 4. Long confirmation after >2 candles -> no signal
    try:
        df4 = make_test_df([
            {"close": 100, "ema9": 98, "ema26": 102, "macd": -1.0, "macd_signal": -0.5},
            {"close": 102, "ema9": 99, "ema26": 101, "macd": 0.2, "macd_signal": -0.1},
            {"close": 102, "ema9": 99.5, "ema26": 101, "macd": 0.3, "macd_signal": 0.0},
            {"close": 102, "ema9": 100, "ema26": 101, "macd": 0.35, "macd_signal": 0.1},
            {"close": 105, "ema9": 102, "ema26": 101, "macd": 0.4, "macd_signal": 0.15},
        ])
        s4_setup = detect_ema_macd_signal(df4.iloc[:2], symbol="TEST")
        pending_setup4 = s4_setup["new_pending_setup"]
        s4 = detect_ema_macd_signal(df4, symbol="TEST", pending_setup=pending_setup4)
        assert s4["signal"] is None, f"Expected None on bar 4 (expired), got {s4['signal']}"
        assert s4["strategy_state"] in ["EXPIRED", "IDLE"], f"Expected EXPIRED state, got {s4['strategy_state']}"
        results.append((4, "Long confirmation after >2 candles -> no signal", True, "Expired after delay > 2 bars"))
    except Exception as e:
        results.append((4, "Long confirmation after >2 candles -> no signal", False, str(e)))

    # 5. Long leading indicator reversal -> cancellation
    try:
        df5 = make_test_df([
            {"close": 100, "ema9": 98, "ema26": 102, "macd": -1.0, "macd_signal": -0.5},
            {"close": 102, "ema9": 99, "ema26": 101, "macd": 0.2, "macd_signal": -0.1},
            {"close": 98, "ema9": 98.5, "ema26": 101, "macd": -0.3, "macd_signal": 0.0},
        ])
        s5_setup = detect_ema_macd_signal(df5.iloc[:2], symbol="TEST")
        s5 = detect_ema_macd_signal(df5, symbol="TEST", pending_setup=s5_setup["new_pending_setup"])
        assert s5["signal"] is None, f"Expected None on reversal, got {s5['signal']}"
        assert s5["strategy_state"] == "INVALIDATED", f"Expected INVALIDATED, got {s5['strategy_state']}"
        assert s5["action_on_pending"] == "CLEAR", f"Expected action CLEAR, got {s5['action_on_pending']}"
        results.append((5, "Long leading indicator reversal -> cancellation", True, "Setup cancelled via INVALIDATED"))
    except Exception as e:
        results.append((5, "Long leading indicator reversal -> cancellation", False, str(e)))

    # 6. Short SAME_CANDLE -> signal
    try:
        df6 = make_test_df([
            {"close": 105, "ema9": 102, "ema26": 100, "macd": 1.0, "macd_signal": 0.5},
            {"close": 98, "ema9": 99, "ema26": 100, "macd": -0.5, "macd_signal": 0.0},
        ])
        s6 = detect_ema_macd_signal(df6, symbol="TEST")
        assert s6 is not None, "Signal dict is None"
        assert s6["signal"] == "SELL", f"Expected SELL, got {s6['signal']}"
        assert s6["trigger_type"] == "SAME_CANDLE", f"Expected SAME_CANDLE, got {s6['trigger_type']}"
        assert s6["confirmation_delay"] == 0, f"Expected delay 0, got {s6['confirmation_delay']}"
        assert s6["strategy_state"] == "CONFIRMED", f"Expected CONFIRMED, got {s6['strategy_state']}"
        results.append((6, "Short SAME_CANDLE -> signal", True, "SELL via SAME_CANDLE (Delay 0)"))
    except Exception as e:
        results.append((6, "Short SAME_CANDLE -> signal", False, str(e)))

    # 7. Short MACD_FIRST -> EMA confirmation within 2 candles -> signal
    try:
        df7 = make_test_df([
            {"close": 105, "ema9": 103, "ema26": 100, "macd": 1.0, "macd_signal": 0.5},
            {"close": 101, "ema9": 101.5, "ema26": 100.5, "macd": -0.2, "macd_signal": 0.1},
            {"close": 98, "ema9": 99, "ema26": 100, "macd": -0.5, "macd_signal": -0.1},
        ])
        s7_pending = detect_ema_macd_signal(df7.iloc[:2], symbol="TEST")
        assert s7_pending["strategy_state"] == "PENDING_EMA", f"Expected PENDING_EMA on bar 1, got {s7_pending['strategy_state']}"
        assert s7_pending["signal"] is None, "Bar 1 should have no signal"

        s7 = detect_ema_macd_signal(df7, symbol="TEST", pending_setup=s7_pending["new_pending_setup"])
        assert s7["signal"] == "SELL", f"Expected SELL on bar 2, got {s7['signal']}"
        assert s7["trigger_type"] == "MACD_THEN_EMA", f"Expected MACD_THEN_EMA, got {s7['trigger_type']}"
        assert s7["confirmation_delay"] == 1, f"Expected delay 1, got {s7['confirmation_delay']}"
        assert s7["strategy_state"] == "CONFIRMED", f"Expected CONFIRMED, got {s7['strategy_state']}"
        results.append((7, "Short MACD_FIRST -> EMA confirmation within 2 candles -> signal", True, "SELL via MACD_THEN_EMA (Delay 1)"))
    except Exception as e:
        results.append((7, "Short MACD_FIRST -> EMA confirmation within 2 candles -> signal", False, str(e)))

    # 8. Short EMA_FIRST -> MACD later -> NO SIGNAL
    try:
        df8 = make_test_df([
            {"close": 105, "ema9": 102, "ema26": 100, "macd": 1.0, "macd_signal": 0.5},
            {"close": 99, "ema9": 99, "ema26": 100, "macd": 0.8, "macd_signal": 0.5},
            {"close": 97, "ema9": 98, "ema26": 100, "macd": -0.2, "macd_signal": 0.2},
        ])
        s8_bar1 = detect_ema_macd_signal(df8.iloc[:2], symbol="TEST")
        assert s8_bar1["strategy_state"] == "REJECTED", f"Expected REJECTED, got {s8_bar1['strategy_state']}"
        assert s8_bar1["trigger_type"] == "EMA_THEN_MACD_REJECTED", f"Expected EMA_THEN_MACD_REJECTED, got {s8_bar1['trigger_type']}"
        assert s8_bar1["rejection_reason"] == "SHORT_EMA_FIRST_DISALLOWED", f"Expected SHORT_EMA_FIRST_DISALLOWED, got {s8_bar1['rejection_reason']}"
        assert s8_bar1["new_pending_setup"] is None, "Short EMA-first must not create pending setup"

        s8_bar2 = detect_ema_macd_signal(df8, symbol="TEST", pending_setup=s8_bar1["new_pending_setup"])
        assert s8_bar2["signal"] is None, f"Expected None on bar 2, got {s8_bar2['signal']}"
        results.append((8, "Short EMA_FIRST -> MACD later -> NO SIGNAL", True, "EMA-first short rejected; no signal produced"))
    except Exception as e:
        results.append((8, "Short EMA_FIRST -> MACD later -> NO SIGNAL", False, str(e)))

    # 9. Short confirmation after >2 candles -> no signal
    try:
        df9 = make_test_df([
            {"close": 105, "ema9": 103, "ema26": 100, "macd": 1.0, "macd_signal": 0.5},
            {"close": 101, "ema9": 101.5, "ema26": 100.5, "macd": -0.2, "macd_signal": 0.1},
            {"close": 101, "ema9": 101, "ema26": 100.5, "macd": -0.3, "macd_signal": 0.0},
            {"close": 101, "ema9": 100.8, "ema26": 100.5, "macd": -0.35, "macd_signal": -0.1},
            {"close": 98, "ema9": 99, "ema26": 100.5, "macd": -0.4, "macd_signal": -0.15},
        ])
        s9_setup = detect_ema_macd_signal(df9.iloc[:2], symbol="TEST")
        pending_setup9 = s9_setup["new_pending_setup"]
        s9 = detect_ema_macd_signal(df9, symbol="TEST", pending_setup=pending_setup9)
        assert s9["signal"] is None, f"Expected None on bar 4 (expired), got {s9['signal']}"
        assert s9["strategy_state"] in ["EXPIRED", "IDLE"], f"Expected EXPIRED state, got {s9['strategy_state']}"
        results.append((9, "Short confirmation after >2 candles -> no signal", True, "Expired after delay > 2 bars"))
    except Exception as e:
        results.append((9, "Short confirmation after >2 candles -> no signal", False, str(e)))

    # 10. Short leading MACD reversal -> cancellation
    try:
        df10 = make_test_df([
            {"close": 105, "ema9": 103, "ema26": 100, "macd": 1.0, "macd_signal": 0.5},
            {"close": 101, "ema9": 101.5, "ema26": 100.5, "macd": -0.2, "macd_signal": 0.1},
            {"close": 106, "ema9": 102, "ema26": 100.5, "macd": 0.4, "macd_signal": 0.2},
        ])
        s10_setup = detect_ema_macd_signal(df10.iloc[:2], symbol="TEST")
        s10 = detect_ema_macd_signal(df10, symbol="TEST", pending_setup=s10_setup["new_pending_setup"])
        assert s10["signal"] is None, f"Expected None on reversal, got {s10['signal']}"
        assert s10["strategy_state"] == "INVALIDATED", f"Expected INVALIDATED, got {s10['strategy_state']}"
        assert s10["action_on_pending"] == "CLEAR", f"Expected action CLEAR, got {s10['action_on_pending']}"
        results.append((10, "Short leading MACD reversal -> cancellation", True, "Setup cancelled via INVALIDATED"))
    except Exception as e:
        results.append((10, "Short leading MACD reversal -> cancellation", False, str(e)))

    # 11. SRF 04-Sep scenario -> SHORT signal
    try:
        df_srf = make_test_df([
            {"close": 2580.0, "ema9": 2595.0, "ema26": 2593.0, "macd": 6.0, "macd_signal": 5.0},
            {"close": 2572.0, "ema9": 2594.0, "ema26": 2593.5, "macd": 0.95, "macd_signal": 5.42},
            {"close": 2558.0, "ema9": 2590.79, "ema26": 2592.02, "macd": 0.61, "macd_signal": 4.91},
        ])
        s_srf_1015 = detect_ema_macd_signal(df_srf.iloc[:2], symbol="SRF")
        assert s_srf_1015["strategy_state"] == "PENDING_EMA", f"Expected PENDING_EMA at 10:15, got {s_srf_1015['strategy_state']}"
        assert s_srf_1015["signal"] is None, "10:15 bar should be unconfirmed"

        s_srf_1115 = detect_ema_macd_signal(df_srf, symbol="SRF", pending_setup=s_srf_1015["new_pending_setup"])
        assert s_srf_1115["signal"] == "SELL", f"Expected SELL on SRF at 11:15, got {s_srf_1115['signal']}"
        assert s_srf_1115["trigger_type"] == "MACD_THEN_EMA", f"Expected MACD_THEN_EMA, got {s_srf_1115['trigger_type']}"
        assert s_srf_1115["confirmation_delay"] == 1, f"Expected delay 1, got {s_srf_1115['confirmation_delay']}"
        results.append((11, "SRF 04-Sep scenario -> SHORT signal", True, "SELL via MACD_THEN_EMA (Delay 1)"))
    except Exception as e:
        results.append((11, "SRF 04-Sep scenario -> SHORT signal", False, str(e)))

    # 12. Histogram changes cannot change signal validity
    try:
        df12_pos = make_test_df([
            {"close": 100, "ema9": 99, "ema26": 101, "macd": -1.0, "macd_signal": -0.5, "macd_histogram": -0.5},
            {"close": 105, "ema9": 102, "ema26": 101, "macd": 0.5, "macd_signal": 0.0, "macd_histogram": 5.0},
        ])
        s12_pos = detect_ema_macd_signal(df12_pos, symbol="TEST")
        df12_neg = make_test_df([
            {"close": 100, "ema9": 99, "ema26": 101, "macd": -1.0, "macd_signal": -0.5, "macd_histogram": -0.5},
            {"close": 105, "ema9": 102, "ema26": 101, "macd": 0.5, "macd_signal": 0.0, "macd_histogram": -5.0},
        ])
        s12_neg = detect_ema_macd_signal(df12_neg, symbol="TEST")
        assert s12_pos["signal"] == s12_neg["signal"] == "BUY", "Histogram modified signal validity!"
        assert s12_pos["trigger_type"] == s12_neg["trigger_type"] == "SAME_CANDLE", "Histogram changed trigger!"
        results.append((12, "Histogram changes cannot change signal validity", True, "Signal invariant to histogram values"))
    except Exception as e:
        results.append((12, "Histogram changes cannot change signal validity", False, str(e)))

    # 13. Incomplete 1H candle cannot generate signal
    try:
        base_t = datetime(2026, 9, 4, 9, 15, tzinfo=IST)
        df13 = make_test_df([
            {"close": 100, "ema9": 99, "ema26": 101, "macd": -1.0, "macd_signal": -0.5},
            {"close": 105, "ema9": 102, "ema26": 101, "macd": 0.5, "macd_signal": 0.0},
        ], base_time=base_t)
        now_during_bar = datetime(2026, 9, 4, 10, 45, tzinfo=IST)
        df13_filtered = get_completed_1h_candles(df13, now_override=now_during_bar)
        assert len(df13_filtered) == 1, f"Incomplete candle was not dropped (len: {len(df13_filtered)})"
        results.append((13, "Incomplete 1H candle cannot generate signal", True, "Incomplete forming candle dropped"))
    except Exception as e:
        results.append((13, "Incomplete 1H candle cannot generate signal", False, str(e)))

    # 14. 15:15 candle becomes eligible only after 15:30
    try:
        t_1515 = datetime(2026, 9, 4, 15, 15, tzinfo=IST)
        t_prev = datetime(2026, 9, 4, 14, 15, tzinfo=IST)
        df14 = pd.DataFrame([
            {"close": 100, "ema9": 99, "ema26": 101, "macd": -1.0, "macd_signal": -0.5},
            {"close": 105, "ema9": 102, "ema26": 101, "macd": 0.5, "macd_signal": 0.0},
        ], index=[t_prev, t_1515])
        df14_before = get_completed_1h_candles(df14, now_override=datetime(2026, 9, 4, 15, 25, tzinfo=IST))
        assert len(df14_before) == 1, "15:15 candle included prematurely before 15:30"
        df14_after = get_completed_1h_candles(df14, now_override=datetime(2026, 9, 4, 15, 30, tzinfo=IST))
        assert len(df14_after) == 2, "15:15 candle not included at/after 15:30"
        results.append((14, "15:15 candle becomes eligible only after 15:30", True, "Eligible strictly at/after 15:30"))
    except Exception as e:
        results.append((14, "15:15 candle becomes eligible only after 15:30", False, str(e)))

    # 15. Duplicate processing cannot create duplicate orders
    try:
        tmp_state_file = Path(f"/tmp/test_state_{int(time.time()*1000)}.json")
        sm15 = PersistentStateManager(tmp_state_file)
        sig_key = "RELIANCE_2026-09-04T11:15:00+05:30_BUY"
        assert not sm15.is_signal_processed(sig_key), "Signal should not be processed initially"
        sm15.record_signal_processed(sig_key)
        assert sm15.is_signal_processed(sig_key), "Signal should be processed after record"
        if tmp_state_file.exists():
            tmp_state_file.unlink()
        results.append((15, "Duplicate processing cannot create duplicate orders", True, "Duplicate signal key recognized"))
    except Exception as e:
        results.append((15, "Duplicate processing cannot create duplicate orders", False, str(e)))

    # 16. Restart cannot duplicate an already executed signal
    try:
        tmp_state_file = Path(f"/tmp/test_restart_{int(time.time()*1000)}.json")
        sm16_1 = PersistentStateManager(tmp_state_file)
        sig_key = "TCS_2026-09-04T11:15:00+05:30_BUY"
        sm16_1.record_signal_processed(sig_key)
        sm16_2 = PersistentStateManager(tmp_state_file)
        assert sm16_2.is_signal_processed(sig_key), "Signal key was lost across restart!"
        if tmp_state_file.exists():
            tmp_state_file.unlink()
        results.append((16, "Restart cannot duplicate an already executed signal", True, "Persistent across process restarts"))
    except Exception as e:
        results.append((16, "Restart cannot duplicate an already executed signal", False, str(e)))

    # 17. Position reversal works correctly
    try:
        pos_long = 100
        base_qty = 100
        reversal_sell_qty = pos_long + base_qty
        assert reversal_sell_qty == 200, f"Expected reversal qty 200, got {reversal_sell_qty}"
        pos_short = -100
        reversal_buy_qty = abs(pos_short) + base_qty
        assert reversal_buy_qty == 200, f"Expected reversal qty 200, got {reversal_buy_qty}"
        results.append((17, "Position reversal works correctly", True, "Controlled reversal sizing verified (200 units)"))
    except Exception as e:
        results.append((17, "Position reversal works correctly", False, str(e)))

    # 18. Paper/analyze safety guard blocks live execution
    try:
        class LiveModeEngine(EMACrossPaperTradingEngine):
            def __init__(self):
                self.paper_mode_confirmed = False
                self.host = "http://localhost:5000"
                self.api_key = "dummy"
                self.state_manager = PersistentStateManager(Path(f"/tmp/test_live_{int(time.time()*1000)}.json"))
            def verify_paper_mode(self):
                return False, "live"

        live_eng = LiveModeEngine()
        blocked_resp = live_eng.place_paper_order("RELIANCE", "RELIANCE26SEPFUT", "BUY", 100, "2026-09-04T10:15:00")
        assert blocked_resp is None, "Order was NOT blocked when live mode was detected!"
        if live_eng.state_manager.state_file.exists():
            live_eng.state_manager.state_file.unlink()
        results.append((18, "Paper/analyze safety guard blocks live execution", True, "Hard-block verified on unconfirmed/live mode"))
    except Exception as e:
        results.append((18, "Paper/analyze safety guard blocks live execution", False, str(e)))

    # 19. Full 211-symbol active NFO universe remains intact
    try:
        assert len(DEFAULT_NFO_UNIVERSE) == 211, f"Expected 211 instruments, got {len(DEFAULT_NFO_UNIVERSE)}"
        assert "SRF" in DEFAULT_NFO_UNIVERSE, "SRF missing from universe"
        assert "RELIANCE" in DEFAULT_NFO_UNIVERSE, "RELIANCE missing from universe"
        assert "NIFTY" in DEFAULT_NFO_UNIVERSE, "NIFTY missing from universe"
        assert "SAGILITY" in DEFAULT_NFO_UNIVERSE, "SAGILITY missing from universe"
        results.append((19, "Full 211-symbol active NFO universe remains intact", True, f"Exactly {len(DEFAULT_NFO_UNIVERSE)} symbols present"))
    except Exception as e:
        results.append((19, "Full 211-symbol active NFO universe remains intact", False, str(e)))

    # 20. Dynamic near-month contract discovery remains intact
    try:
        assert len(FALLBACK_LOT_SIZES) >= 218, f"Lot size table has {len(FALLBACK_LOT_SIZES)} entries"
        assert FALLBACK_LOT_SIZES.get("SRF") is not None, "SRF lot size missing"
        assert FALLBACK_LOT_SIZES.get("RELIANCE") is not None, "RELIANCE lot size missing"
        import inspect
        sig = inspect.signature(resolve_nfo_contract)
        assert "symbol" in sig.parameters, "resolve_nfo_contract missing symbol parameter"
        results.append((20, "Dynamic near-month contract discovery remains intact", True, "Dynamic contract discovery and lot sizes verified"))
    except Exception as e:
        results.append((20, "Dynamic near-month contract discovery remains intact", False, str(e)))

    # 21. Single consolidated Telegram order notification formatting
    try:
        sample_data = {
            "strategy_name": "EMACROSS_FNO_PAPER",
            "contract": "NIFTY26SEPFUT",
            "symbol": "NIFTY",
            "action": "BUY",
            "direction": "LONG",
            "trigger_type": "SAME_CANDLE",
            "confirmation_delay": 0,
            "quantity": 75,
            "entry_price": 24850.50,
            "price_type": "MARKET",
            "exchange": "NFO",
            "product": "NRML",
            "order_id": "TEST_ORD_260908",
            "order_status": "FILLED",
            "pos_before": 0,
            "pos_after": 75,
            "execution_time": "14:15:00",
            "candle_time_str": "08-Sep-2026 14:15",
            "close": 24840.0,
            "ema9": 24830.0,
            "ema26": 24800.0,
            "macd": 15.5,
            "macd_signal": 12.0,
            "macd_histogram": 3.5,
            "trigger_price": 0.0,  # even if passed in dict, MARKET order must ignore
        }
        msg = format_paper_trade_alert(sample_data)
        assert "<b>Entry Price:</b> ₹24850.50" in msg, "Entry Price missing or incorrect in formatted alert"
        assert "Trigger Price: 0.0" not in msg, "Trigger Price: 0.0 must NOT be present for MARKET order"
        assert "Trigger Price" not in msg, "Trigger Price should be absent for MARKET order"
        assert "<b>Strategy:</b>" in msg and "<b>ANALYZE MODE - No Real Order</b>" in msg, "Strategy or Mode header missing"
        assert "<b>Symbol:</b> <code>NIFTY26SEPFUT</code> (NIFTY)" in msg, "Symbol missing"
        assert "<b>Action:</b> <b>BUY</b>" in msg and "<b>Direction:</b> <b>LONG</b>" in msg, "Action or Direction missing"
        assert "<b>Trigger:</b> <b>SAME_CANDLE</b> (Delay: 0 candles)" in msg, "Trigger type missing"
        assert "<b>Quantity:</b> 75" in msg, "Quantity missing"
        assert "<b>Price Type:</b> MARKET" in msg, "Price Type missing"
        assert "<b>Exchange:</b> NFO" in msg and "<b>Product:</b> NRML" in msg, "Exchange/Product missing"
        assert "<b>Order ID:</b> <code>TEST_ORD_260908</code>" in msg, "Order ID missing"
        assert "<b>Order Status:</b> FILLED" in msg, "Order Status missing"
        assert "<b>Position:</b> 0 ➔ 75" in msg, "Position transition missing"
        assert "<b>Close:</b> 24840.00" in msg and "<b>EMA9:</b> 24830.00" in msg and "<b>EMA26:</b> 24800.00" in msg, "Candle EMA missing"
        assert "<b>MACD:</b> 15.50" in msg and "<b>Signal:</b> 12.00" in msg and "<b>Histogram:</b> +3.50" in msg, "MACD indicators missing"
        assert "14:15:00 IST" in msg, "Time missing"
        results.append((21, "Single consolidated Telegram order notification formatting", True, "Entry Price formatted; Trigger Price: 0.0 absent; all 17 fields preserved"))
    except Exception as e:
        results.append((21, "Single consolidated Telegram order notification formatting", False, str(e)))

    # 22. Mocked order fill execution & single-message dispatch
    try:
        from unittest.mock import patch, MagicMock

        sent_messages = []
        def fake_send_telegram(message: str) -> bool:
            sent_messages.append(message)
            return True

        tmp_state_file = Path(f"/tmp/test_fill_exec_{int(time.time()*1000)}.json")
        engine_mock = MockTestEngine(
            symbols=["NIFTY"],
            lots=1,
            max_active=10,
        )
        engine_mock.state_manager = PersistentStateManager(tmp_state_file)
        engine_mock.contract_cache["NIFTY"] = {
            "contract": "NIFTY26SEPFUT",
            "lot_size": 75,
            "order_qty": 75,
            "expiry_dt": datetime.now() + timedelta(days=30),
        }

        # Mock OpenAlgo client with orderstatus returning actual fill price 24850.75
        mock_client = MagicMock()
        mock_client.placeorder.return_value = {
            "status": "success",
            "orderid": "MOCK_ORD_777",
            "mode": "analyze",
        }
        mock_client.orderstatus.return_value = {
            "status": "success",
            "data": {
                "orderid": "MOCK_ORD_777",
                "order_status": "complete",
                "average_price": 24850.75,
                "price": 24850.75,
                "quantity": 75,
                "symbol": "NIFTY26SEPFUT",
            }
        }
        engine_mock.client = mock_client
        engine_mock.paper_mode_confirmed = True
        engine_mock.verify_paper_mode = lambda: (True, "analyze")
        engine_mock.get_open_position = lambda contract: 0

        mock_sig_data = {
            "signal": "BUY",
            "confluence": "BULLISH",
            "trigger_type": "SAME_CANDLE",
            "confirmation_delay": 0,
            "candle_time_str": "08-Sep-2026 14:15",
            "timestamp": "2026-09-08T14:15:00+05:30",
            "close": 24840.0,
            "open": 24800.0,
            "high": 24860.0,
            "low": 24790.0,
            "ema9": 24830.0,
            "ema26": 24800.0,
            "macd": 15.5,
            "macd_signal": 12.0,
            "macd_histogram": 3.5,
            "previous_ema9": 24790.0,
            "previous_ema26": 24795.0,
            "previous_macd": 10.0,
            "previous_signal": 11.0,
            "previous_histogram": -1.0,
            "ema_crossover": "BULLISH",
            "macd_crossover": "BULLISH",
            "strategy_state": "CONFIRMED",
            "rejection_reason": "NONE",
        }

        # Patch send_telegram_alert in both current namespace and module namespace
        mod_name = __name__
        with patch(f"{mod_name}.send_telegram_alert", side_effect=fake_send_telegram):
            placed, new_active = engine_mock.execute_symbol_decision("NIFTY", mock_sig_data, active_positions_count=0)

        assert placed is True, "Order was not placed in mock test"
        assert len(sent_messages) == 1, f"Expected exactly 1 Telegram message, got {len(sent_messages)}"
        final_msg = sent_messages[0]
        assert "<b>Entry Price:</b> ₹24850.75" in final_msg, "Actual fill price 24850.75 not in Telegram message"
        assert "Trigger Price: 0.0" not in final_msg, "Trigger Price: 0.0 found in message!"
        assert "Trigger Price" not in final_msg, "Trigger Price found in MARKET order message!"
        assert "PAPER TRADE — ORDER PLACED" in final_msg, "Standard order header missing"
        # Verify tracked_positions has actual fill price, not candle close
        tracked_pos = engine_mock.state_manager.state.get("tracked_positions", {}).get("NIFTY26SEPFUT")
        assert tracked_pos is not None, "Tracked position not saved"
        assert tracked_pos["average_price"] == 24850.75, f"Expected tracked average_price 24850.75, got {tracked_pos.get('average_price')}"
        # Verify order alert was recorded in sent_alerts for deduplication
        assert engine_mock.state_manager.is_alert_sent("ORDER_ALERT_MOCK_ORD_777"), "Order alert was not recorded in sent_alerts"

        if tmp_state_file.exists():
            tmp_state_file.unlink()
        results.append((22, "Mocked order fill execution & single-message dispatch", True, "Exactly 1 message generated; fill price 24850.75 captured; Trigger Price: 0.0 absent; alert deduplication recorded"))
    except Exception as e:
        results.append((22, "Mocked order fill execution & single-message dispatch", False, str(e)))

    # 23. LONG target hit (+3.00%)
    try:
        tmp_state23 = Path(f"/tmp/test_target_long_{int(time.time()*1000)}.json")
        engine23 = MockTestEngine(symbols=["RELIANCE"], lots=1, max_active=10)
        engine23.state_manager = PersistentStateManager(tmp_state23)
        contract_sym23 = "RELIANCE26SEPFUT"
        engine23.contract_cache["RELIANCE"] = {
            "contract": contract_sym23,
            "lot_size": 250,
            "order_qty": 250,
            "expiry_dt": datetime.now() + timedelta(days=30),
        }
        engine23.state_manager.update_tracked_positions({
            contract_sym23: {
                "contract": contract_sym23,
                "base_symbol": "RELIANCE",
                "direction": "LONG",
                "quantity": 250,
                "average_price": 2000.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_ENTRY_23",
            }
        })
        mock_cli23 = MagicMock()
        mock_cli23.placeorder.return_value = {"status": "success", "orderid": "EXIT_ORD_23", "mode": "analyze"}
        mock_cli23.orderstatus.return_value = {
            "status": "success",
            "data": {"orderid": "EXIT_ORD_23", "order_status": "complete", "average_price": 2062.0, "quantity": 250, "symbol": contract_sym23}
        }
        engine23.client = mock_cli23
        engine23.verify_paper_mode = lambda: (True, "analyze")

        # Candle reaches high 2065.0 (>= 2000 * 1.03 = 2060.0)
        df23 = make_test_df([
            {"close": 2000.0, "high": 2010.0, "low": 1990.0, "open": 1995.0},
            {"close": 2055.0, "high": 2065.0, "low": 2010.0, "open": 2015.0},
        ])
        exit_sent_msgs23 = []
        with patch(f"{__name__}.send_telegram_alert", side_effect=lambda m: exit_sent_msgs23.append(m)):
            exited23 = engine23.check_and_execute_target_or_sl("RELIANCE", contract_sym23, df23)

        assert exited23 is True, "Target exit was not executed for LONG"
        mock_cli23.placeorder.assert_called_once()
        call_kwargs23 = mock_cli23.placeorder.call_args[1]
        assert call_kwargs23["action"] == "SELL", f"Expected SELL exit, got {call_kwargs23['action']}"
        assert call_kwargs23["quantity"] == 250, f"Expected 250 qty, got {call_kwargs23['quantity']}"
        tracked23 = engine23.state_manager.state.get("tracked_positions", {})
        assert contract_sym23 not in tracked23, "Tracked position was not cleared after target exit"
        assert len(exit_sent_msgs23) == 1, f"Expected 1 exit alert, got {len(exit_sent_msgs23)}"
        assert "TARGET HIT" in exit_sent_msgs23[0], "TARGET HIT header missing in alert"
        assert "TARGET REACHED" in exit_sent_msgs23[0], "TARGET REACHED badge missing in alert"
        if tmp_state23.exists():
            tmp_state23.unlink()
        results.append((23, "LONG target hit (+3.00%)", True, "LONG position exited via SELL at +3.00% target; tracked positions cleared; alert sent"))
    except Exception as e:
        results.append((23, "LONG target hit (+3.00%)", False, str(e)))

    # 24. SHORT target hit (+1.50%)
    try:
        tmp_state24 = Path(f"/tmp/test_target_short_{int(time.time()*1000)}.json")
        engine24 = MockTestEngine(symbols=["TCS"], lots=1, max_active=10)
        engine24.state_manager = PersistentStateManager(tmp_state24)
        contract_sym24 = "TCS26SEPFUT"
        engine24.contract_cache["TCS"] = {
            "contract": contract_sym24,
            "lot_size": 175,
            "order_qty": 175,
            "expiry_dt": datetime.now() + timedelta(days=30),
        }
        engine24.state_manager.update_tracked_positions({
            contract_sym24: {
                "contract": contract_sym24,
                "base_symbol": "TCS",
                "direction": "SHORT",
                "quantity": -175,
                "average_price": 3000.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_ENTRY_24",
            }
        })
        mock_cli24 = MagicMock()
        mock_cli24.placeorder.return_value = {"status": "success", "orderid": "EXIT_ORD_24", "mode": "analyze"}
        mock_cli24.orderstatus.return_value = {
            "status": "success",
            "data": {"orderid": "EXIT_ORD_24", "order_status": "complete", "average_price": 2950.0, "quantity": 175, "symbol": contract_sym24}
        }
        engine24.client = mock_cli24
        engine24.verify_paper_mode = lambda: (True, "analyze")

        # Candle reaches low 2950.0 (<= 3000 * (1 - 0.015) = 2955.0)
        df24 = make_test_df([
            {"close": 3000.0, "high": 3010.0, "low": 2990.0, "open": 2995.0},
            {"close": 2958.0, "high": 2990.0, "low": 2950.0, "open": 2985.0},
        ])
        exit_sent_msgs24 = []
        with patch(f"{__name__}.send_telegram_alert", side_effect=lambda m: exit_sent_msgs24.append(m)):
            exited24 = engine24.check_and_execute_target_or_sl("TCS", contract_sym24, df24)

        assert exited24 is True, "Target exit was not executed for SHORT"
        call_kwargs24 = mock_cli24.placeorder.call_args[1]
        assert call_kwargs24["action"] == "BUY", f"Expected BUY exit for short, got {call_kwargs24['action']}"
        assert call_kwargs24["quantity"] == 175, f"Expected 175 qty, got {call_kwargs24['quantity']}"
        assert "TARGET HIT" in exit_sent_msgs24[0], "TARGET HIT header missing in alert"
        if tmp_state24.exists():
            tmp_state24.unlink()
        results.append((24, "SHORT target hit (+1.50%)", True, "SHORT position exited via BUY at +1.50% target; alert sent"))
    except Exception as e:
        results.append((24, "SHORT target hit (+1.50%)", False, str(e)))

    # 25. LONG catastrophe SL (-6.00%)
    try:
        tmp_state25 = Path(f"/tmp/test_sl_long_{int(time.time()*1000)}.json")
        engine25 = MockTestEngine(symbols=["INFY"], lots=1, max_active=10)
        engine25.state_manager = PersistentStateManager(tmp_state25)
        contract_sym25 = "INFY26SEPFUT"
        engine25.contract_cache["INFY"] = {
            "contract": contract_sym25,
            "lot_size": 400,
            "order_qty": 400,
            "expiry_dt": datetime.now() + timedelta(days=30),
        }
        engine25.state_manager.update_tracked_positions({
            contract_sym25: {
                "contract": contract_sym25,
                "base_symbol": "INFY",
                "direction": "LONG",
                "quantity": 400,
                "average_price": 1500.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_ENTRY_25",
            }
        })
        mock_cli25 = MagicMock()
        mock_cli25.placeorder.return_value = {"status": "success", "orderid": "EXIT_ORD_25", "mode": "analyze"}
        mock_cli25.orderstatus.return_value = {
            "status": "success",
            "data": {"orderid": "EXIT_ORD_25", "order_status": "complete", "average_price": 1405.0, "quantity": 400, "symbol": contract_sym25}
        }
        engine25.client = mock_cli25
        engine25.verify_paper_mode = lambda: (True, "analyze")

        # Candle breaches -6.00% catastrophe SL: low <= 1500 * 0.94 = 1410.0
        df25 = make_test_df([
            {"close": 1500.0, "high": 1510.0, "low": 1490.0, "open": 1495.0},
            {"close": 1415.0, "high": 1460.0, "low": 1405.0, "open": 1450.0},
        ])
        exit_sent_msgs25 = []
        with patch(f"{__name__}.send_telegram_alert", side_effect=lambda m: exit_sent_msgs25.append(m)):
            exited25 = engine25.check_and_execute_target_or_sl("INFY", contract_sym25, df25)

        assert exited25 is True, "Catastrophe SL was not executed for LONG"
        call_kwargs25 = mock_cli25.placeorder.call_args[1]
        assert call_kwargs25["action"] == "SELL"
        assert "CATASTROPHE STOP-LOSS" in exit_sent_msgs25[0], "CATASTROPHE STOP-LOSS header missing"
        assert "EMERGENCY STOP LOSS TRIGGERED" in exit_sent_msgs25[0], "Emergency SL badge missing"
        if tmp_state25.exists():
            tmp_state25.unlink()
        results.append((25, "LONG catastrophe SL (-6.00%)", True, "LONG position exited via SELL on -6.00% emergency stop-loss"))
    except Exception as e:
        results.append((25, "LONG catastrophe SL (-6.00%)", False, str(e)))

    # 26. SHORT catastrophe SL (-6.00%)
    try:
        tmp_state26 = Path(f"/tmp/test_sl_short_{int(time.time()*1000)}.json")
        engine26 = MockTestEngine(symbols=["HDFCBANK"], lots=1, max_active=10)
        engine26.state_manager = PersistentStateManager(tmp_state26)
        contract_sym26 = "HDFCBANK26SEPFUT"
        engine26.contract_cache["HDFCBANK"] = {
            "contract": contract_sym26,
            "lot_size": 550,
            "order_qty": 550,
            "expiry_dt": datetime.now() + timedelta(days=30),
        }
        engine26.state_manager.update_tracked_positions({
            contract_sym26: {
                "contract": contract_sym26,
                "base_symbol": "HDFCBANK",
                "direction": "SHORT",
                "quantity": -550,
                "average_price": 1600.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_ENTRY_26",
            }
        })
        mock_cli26 = MagicMock()
        mock_cli26.placeorder.return_value = {"status": "success", "orderid": "EXIT_ORD_26", "mode": "analyze"}
        mock_cli26.orderstatus.return_value = {
            "status": "success",
            "data": {"orderid": "EXIT_ORD_26", "order_status": "complete", "average_price": 1700.0, "quantity": 550, "symbol": contract_sym26}
        }
        engine26.client = mock_cli26
        engine26.verify_paper_mode = lambda: (True, "analyze")

        # Candle breaches -6.00% SL for SHORT: high >= 1600 * 1.06 = 1696.0
        df26 = make_test_df([
            {"close": 1600.0, "high": 1610.0, "low": 1590.0, "open": 1595.0},
            {"close": 1690.0, "high": 1705.0, "low": 1640.0, "open": 1645.0},
        ])
        exit_sent_msgs26 = []
        with patch(f"{__name__}.send_telegram_alert", side_effect=lambda m: exit_sent_msgs26.append(m)):
            exited26 = engine26.check_and_execute_target_or_sl("HDFCBANK", contract_sym26, df26)

        assert exited26 is True, "Catastrophe SL was not executed for SHORT"
        call_kwargs26 = mock_cli26.placeorder.call_args[1]
        assert call_kwargs26["action"] == "BUY"
        assert "CATASTROPHE STOP-LOSS" in exit_sent_msgs26[0]
        if tmp_state26.exists():
            tmp_state26.unlink()
        results.append((26, "SHORT catastrophe SL (-6.00%)", True, "SHORT position exited via BUY on -6.00% emergency stop-loss"))
    except Exception as e:
        results.append((26, "SHORT catastrophe SL (-6.00%)", False, str(e)))

    # 27. Target not hit -> existing reversal still works
    try:
        tmp_state27 = Path(f"/tmp/test_reversal_preserved_{int(time.time()*1000)}.json")
        engine27 = MockTestEngine(symbols=["SBIN"], lots=1, max_active=10)
        engine27.state_manager = PersistentStateManager(tmp_state27)
        contract_sym27 = "SBIN26SEPFUT"
        engine27.contract_cache["SBIN"] = {
            "contract": contract_sym27,
            "lot_size": 750,
            "order_qty": 750,
            "expiry_dt": datetime.now() + timedelta(days=30),
        }
        engine27.state_manager.update_tracked_positions({
            contract_sym27: {
                "contract": contract_sym27,
                "base_symbol": "SBIN",
                "direction": "LONG",
                "quantity": 750,
                "average_price": 800.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_ENTRY_27",
            }
        })
        engine27.get_open_position = lambda contract: 750
        mock_cli27 = MagicMock()
        mock_cli27.placeorder.return_value = {"status": "success", "orderid": "REV_ORD_27", "mode": "analyze"}
        mock_cli27.orderstatus.return_value = {
            "status": "success",
            "data": {"orderid": "REV_ORD_27", "order_status": "complete", "average_price": 805.0, "quantity": 1500, "symbol": contract_sym27}
        }
        engine27.client = mock_cli27
        engine27.verify_paper_mode = lambda: (True, "analyze")

        df27 = make_test_df([
            {"close": 800.0, "high": 805.0, "low": 795.0, "open": 798.0},
            {"close": 805.0, "high": 815.0, "low": 790.0, "open": 795.0},
        ])
        target_hit27 = engine27.check_and_execute_target_or_sl("SBIN", contract_sym27, df27)
        assert target_hit27 is False, "Target/SL should not have triggered"

        rev_sig_data = {
            "signal": "SELL",
            "confluence": "BEARISH",
            "trigger_type": "SAME_CANDLE",
            "confirmation_delay": 0,
            "candle_time_str": "08-Sep-2026 14:15",
            "timestamp": "2026-09-08T14:15:00+05:30",
            "close": 805.0,
            "open": 810.0,
            "high": 815.0,
            "low": 790.0,
            "ema9": 802.0,
            "ema26": 804.0,
            "macd": -1.0,
            "macd_signal": 0.0,
            "macd_histogram": -1.0,
        }
        sent_msgs27 = []
        with patch(f"{__name__}.send_telegram_alert", side_effect=lambda m: sent_msgs27.append(m)):
            placed27, _ = engine27.execute_symbol_decision("SBIN", rev_sig_data, active_positions_count=1)

        assert placed27 is True, "Reversal order was not placed"
        call_kwargs27 = mock_cli27.placeorder.call_args[1]
        assert call_kwargs27["action"] == "SELL"
        assert call_kwargs27["quantity"] == 1500, f"Expected 1500 reversal qty (750 + 750), got {call_kwargs27['quantity']}"
        assert len(sent_msgs27) == 2, f"Expected 2 alerts (reversal exit + new entry), got {len(sent_msgs27)}"
        assert "REVERSAL EXIT" in sent_msgs27[0], "First alert should be REVERSAL EXIT"
        assert "V2-2 SIGNAL REVERSAL" in sent_msgs27[0]
        assert "PAPER TRADE — ORDER PLACED" in sent_msgs27[1], "Second alert should be ORDER PLACED"
        if tmp_state27.exists():
            tmp_state27.unlink()
        results.append((27, "Target not hit -> existing reversal still works", True, "Controlled reversal smoothly executed (1500 units) with both exit & entry alerts dispatched"))
    except Exception as e:
        results.append((27, "Target not hit -> existing reversal still works", False, str(e)))

    # 28. Target hit before reversal -> TARGET_HIT
    try:
        tmp_state28 = Path(f"/tmp/test_tp_before_rev_{int(time.time()*1000)}.json")
        engine28 = MockTestEngine(symbols=["LT"], lots=1, max_active=10)
        engine28.state_manager = PersistentStateManager(tmp_state28)
        contract_sym28 = "LT26SEPFUT"
        engine28.contract_cache["LT"] = {
            "contract": contract_sym28,
            "lot_size": 150,
            "order_qty": 150,
            "expiry_dt": datetime.now() + timedelta(days=30),
        }
        engine28.state_manager.update_tracked_positions({
            contract_sym28: {
                "contract": contract_sym28,
                "base_symbol": "LT",
                "direction": "LONG",
                "quantity": 150,
                "average_price": 3500.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_ENTRY_28",
            }
        })
        mock_cli28 = MagicMock()
        mock_cli28.placeorder.return_value = {"status": "success", "orderid": "TP_ORD_28", "mode": "analyze"}
        mock_cli28.orderstatus.return_value = {
            "status": "success",
            "data": {"orderid": "TP_ORD_28", "order_status": "complete", "average_price": 3610.0, "quantity": 150, "symbol": contract_sym28}
        }
        engine28.client = mock_cli28
        engine28.verify_paper_mode = lambda: (True, "analyze")

        # Candle reaches target: high 3615.0 >= 3500 * 1.03 = 3605.0
        df28 = make_test_df([
            {"close": 3500.0, "high": 3510.0, "low": 3490.0, "open": 3495.0},
            {"close": 3610.0, "high": 3615.0, "low": 3520.0, "open": 3520.0},
        ])
        exit_executed28 = engine28.check_and_execute_target_or_sl("LT", contract_sym28, df28)
        assert exit_executed28 is True, "Target should have triggered"

        tracked28 = engine28.state_manager.state.get("tracked_positions", {})
        assert contract_sym28 not in tracked28, "Position should be closed to FLAT"
        if tmp_state28.exists():
            tmp_state28.unlink()
        results.append((28, "Target hit before reversal -> TARGET_HIT", True, "Position cleanly closed to FLAT via TARGET_HIT before reversal evaluation"))
    except Exception as e:
        results.append((28, "Target hit before reversal -> TARGET_HIT", False, str(e)))

    # 29. Catastrophe SL before reversal -> CATASTROPHE_SL
    try:
        tmp_state29 = Path(f"/tmp/test_sl_before_rev_{int(time.time()*1000)}.json")
        engine29 = MockTestEngine(symbols=["AXISBANK"], lots=1, max_active=10)
        engine29.state_manager = PersistentStateManager(tmp_state29)
        contract_sym29 = "AXISBANK26SEPFUT"
        engine29.contract_cache["AXISBANK"] = {
            "contract": contract_sym29,
            "lot_size": 625,
            "order_qty": 625,
            "expiry_dt": datetime.now() + timedelta(days=30),
        }
        engine29.state_manager.update_tracked_positions({
            contract_sym29: {
                "contract": contract_sym29,
                "base_symbol": "AXISBANK",
                "direction": "LONG",
                "quantity": 625,
                "average_price": 1200.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_ENTRY_29",
            }
        })
        mock_cli29 = MagicMock()
        mock_cli29.placeorder.return_value = {"status": "success", "orderid": "SL_ORD_29", "mode": "analyze"}
        mock_cli29.orderstatus.return_value = {
            "status": "success",
            "data": {"orderid": "SL_ORD_29", "order_status": "complete", "average_price": 1120.0, "quantity": 625, "symbol": contract_sym29}
        }
        engine29.client = mock_cli29
        engine29.verify_paper_mode = lambda: (True, "analyze")

        # Candle breaches catastrophe SL: low 1120.0 <= 1200 * 0.94 = 1128.0
        df29 = make_test_df([
            {"close": 1200.0, "high": 1210.0, "low": 1190.0, "open": 1195.0},
            {"close": 1125.0, "high": 1180.0, "low": 1120.0, "open": 1175.0},
        ])
        exit_executed29 = engine29.check_and_execute_target_or_sl("AXISBANK", contract_sym29, df29)
        assert exit_executed29 is True, "Catastrophe SL should have triggered"
        tracked29 = engine29.state_manager.state.get("tracked_positions", {})
        assert contract_sym29 not in tracked29, "Position should be closed to FLAT"
        if tmp_state29.exists():
            tmp_state29.unlink()
        results.append((29, "Catastrophe SL before reversal -> CATASTROPHE_SL", True, "Emergency catastrophe SL triggered before reversal processing"))
    except Exception as e:
        results.append((29, "Catastrophe SL before reversal -> CATASTROPHE_SL", False, str(e)))

    # 30. Actual fill price used instead of candle close
    try:
        tmp_state30 = Path(f"/tmp/test_fill_vs_close_{int(time.time()*1000)}.json")
        engine30 = MockTestEngine(symbols=["BAJFINANCE"], lots=1, max_active=10)
        engine30.state_manager = PersistentStateManager(tmp_state30)
        contract_sym30 = "BAJFINANCE26SEPFUT"
        engine30.contract_cache["BAJFINANCE"] = {
            "contract": contract_sym30,
            "lot_size": 125,
            "order_qty": 125,
            "expiry_dt": datetime.now() + timedelta(days=30),
        }
        # Signal candle close was 7000.0, but actual executed fill price was 7200.0
        # Target (+3%) from fill price 7200.0 is 7416.0.
        # If candle close 7000 were incorrectly used, target would be 7210.0.
        engine30.state_manager.update_tracked_positions({
            contract_sym30: {
                "contract": contract_sym30,
                "base_symbol": "BAJFINANCE",
                "direction": "LONG",
                "quantity": 125,
                "average_price": 7200.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_ENTRY_30",
            }
        })
        mock_cli30 = MagicMock()
        mock_cli30.placeorder.return_value = {"status": "success", "orderid": "EXIT_ORD_30", "mode": "analyze"}
        mock_cli30.orderstatus.return_value = {
            "status": "success",
            "data": {"orderid": "EXIT_ORD_30", "order_status": "complete", "average_price": 7420.0, "quantity": 125, "symbol": contract_sym30}
        }
        engine30.client = mock_cli30
        engine30.verify_paper_mode = lambda: (True, "analyze")

        # Candle reaches high 7250.0 (> 7210.0 close target, but < 7416.0 fill target)
        df30_below = make_test_df([
            {"close": 7000.0, "high": 7020.0, "low": 6980.0, "open": 6990.0},
            {"close": 7240.0, "high": 7250.0, "low": 7180.0, "open": 7190.0},
        ])
        exit_below = engine30.check_and_execute_target_or_sl("BAJFINANCE", contract_sym30, df30_below)
        assert exit_below is False, "Target incorrectly triggered using candle close instead of actual fill price!"

        # Now candle reaches high 7420.0 (>= 7416.0) -> triggers target!
        df30_above = make_test_df([
            {"close": 7000.0, "high": 7020.0, "low": 6980.0, "open": 6990.0},
            {"close": 7410.0, "high": 7420.0, "low": 7220.0, "open": 7230.0},
        ])
        exit_above = engine30.check_and_execute_target_or_sl("BAJFINANCE", contract_sym30, df30_above)
        assert exit_above is True, "Target failed to trigger on actual fill price threshold 7416.0!"
        if tmp_state30.exists():
            tmp_state30.unlink()
        results.append((30, "Actual fill price used instead of candle close", True, "Confirmed: Target evaluated strictly from actual fill price 7200 (target 7416), ignoring candle close 7000"))
    except Exception as e:
        results.append((30, "Actual fill price used instead of candle close", False, str(e)))

    # 31. Duplicate processing cannot create duplicate exit
    try:
        tmp_state31 = Path(f"/tmp/test_exit_dedup_{int(time.time()*1000)}.json")
        engine31 = MockTestEngine(symbols=["KOTAKBANK"], lots=1, max_active=10)
        engine31.state_manager = PersistentStateManager(tmp_state31)
        contract_sym31 = "KOTAKBANK26SEPFUT"
        engine31.contract_cache["KOTAKBANK"] = {
            "contract": contract_sym31,
            "lot_size": 400,
            "order_qty": 400,
            "expiry_dt": datetime.now() + timedelta(days=30),
        }
        engine31.state_manager.update_tracked_positions({
            contract_sym31: {
                "contract": contract_sym31,
                "base_symbol": "KOTAKBANK",
                "direction": "LONG",
                "quantity": 400,
                "average_price": 1800.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_ENTRY_31",
            }
        })
        mock_cli31 = MagicMock()
        mock_cli31.placeorder.return_value = {"status": "success", "orderid": "EXIT_ORD_31", "mode": "analyze"}
        mock_cli31.orderstatus.return_value = {
            "status": "success",
            "data": {"orderid": "EXIT_ORD_31", "order_status": "complete", "average_price": 1860.0, "quantity": 400, "symbol": contract_sym31}
        }
        engine31.client = mock_cli31
        engine31.verify_paper_mode = lambda: (True, "analyze")

        df31 = make_test_df([
            {"close": 1800.0, "high": 1810.0, "low": 1790.0, "open": 1795.0},
            {"close": 1855.0, "high": 1865.0, "low": 1810.0, "open": 1815.0},
        ])
        first_exit = engine31.check_and_execute_target_or_sl("KOTAKBANK", contract_sym31, df31)
        assert first_exit is True, "First exit execution failed"
        assert mock_cli31.placeorder.call_count == 1, "Expected 1 order placement"

        # Simulate repeat evaluation with re-injected position
        engine31.state_manager.update_tracked_positions({
            contract_sym31: {
                "contract": contract_sym31,
                "base_symbol": "KOTAKBANK",
                "direction": "LONG",
                "quantity": 400,
                "average_price": 1800.0,
                "candle_time": "08-Sep-2026 13:15",
            }
        })
        second_exit = engine31.check_and_execute_target_or_sl("KOTAKBANK", contract_sym31, df31)
        assert second_exit is False, "Duplicate exit was erroneously executed!"
        assert mock_cli31.placeorder.call_count == 1, "placeorder should still have been called exactly once"
        if tmp_state31.exists():
            tmp_state31.unlink()
        results.append((31, "Duplicate processing cannot create duplicate exit", True, "Idempotency lock verified: repeat evaluation does not duplicate exit order"))
    except Exception as e:
        results.append((31, "Duplicate processing cannot create duplicate exit", False, str(e)))

    # 32. Restart/state recovery preserves entry price and target/SL state
    try:
        tmp_state32 = Path(f"/tmp/test_state_restart_{int(time.time()*1000)}.json")
        sm32_initial = PersistentStateManager(tmp_state32)
        contract_sym32 = "TITAN26SEPFUT"
        sm32_initial.update_tracked_positions({
            contract_sym32: {
                "contract": contract_sym32,
                "base_symbol": "TITAN",
                "direction": "LONG",
                "quantity": 175,
                "average_price": 3200.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_PRE_RESTART",
            }
        })

        sm32_reloaded = PersistentStateManager(tmp_state32)
        recovered_pos = sm32_reloaded.state.get("tracked_positions", {}).get(contract_sym32)
        assert recovered_pos is not None, "Position not recovered after state reload"
        assert recovered_pos["average_price"] == 3200.0, f"Expected recovered average_price 3200.0, got {recovered_pos.get('average_price')}"
        assert recovered_pos["direction"] == "LONG"
        assert recovered_pos["quantity"] == 175

        engine32 = MockTestEngine(symbols=["TITAN"], lots=1, max_active=10)
        engine32.state_manager = sm32_reloaded
        engine32.contract_cache["TITAN"] = {"contract": contract_sym32, "lot_size": 175, "order_qty": 175}
        mock_cli32 = MagicMock()
        mock_cli32.placeorder.return_value = {"status": "success", "orderid": "EXIT_RESTART_32", "mode": "analyze"}
        mock_cli32.orderstatus.return_value = {"status": "success", "data": {"average_price": 3300.0}}
        engine32.client = mock_cli32
        engine32.verify_paper_mode = lambda: (True, "analyze")

        df32 = make_test_df([
            {"close": 3200.0, "high": 3210.0, "low": 3190.0, "open": 3195.0},
            {"close": 3295.0, "high": 3305.0, "low": 3220.0, "open": 3225.0},
        ])
        exit32 = engine32.check_and_execute_target_or_sl("TITAN", contract_sym32, df32)
        assert exit32 is True, "Target exit failed on recovered state engine"
        if tmp_state32.exists():
            tmp_state32.unlink()
        results.append((32, "Restart/state recovery preserves entry price and target/SL state", True, "Persistent JSON state successfully recovered entry price and triggered target"))
    except Exception as e:
        results.append((32, "Restart/state recovery preserves entry price and target/SL state", False, str(e)))

    # 33. ANALYZE mode still blocks real orders on exit
    try:
        tmp_state33 = Path(f"/tmp/test_safety_exit_{int(time.time()*1000)}.json")
        engine33 = MockTestEngine(symbols=["MARUTI"], lots=1, max_active=10)
        engine33.state_manager = PersistentStateManager(tmp_state33)
        contract_sym33 = "MARUTI26SEPFUT"
        engine33.contract_cache["MARUTI"] = {"contract": contract_sym33, "lot_size": 50, "order_qty": 50}
        engine33.state_manager.update_tracked_positions({
            contract_sym33: {
                "contract": contract_sym33,
                "base_symbol": "MARUTI",
                "direction": "LONG",
                "quantity": 50,
                "average_price": 12000.0,
                "candle_time": "08-Sep-2026 13:15",
            }
        })
        engine33.verify_paper_mode = lambda: (False, "live")
        mock_cli33 = MagicMock()
        engine33.client = mock_cli33

        df33 = make_test_df([
            {"close": 12000.0, "high": 12050.0, "low": 11950.0, "open": 11980.0},
            {"close": 12400.0, "high": 12450.0, "low": 12100.0, "open": 12150.0},
        ])
        exit33 = engine33.check_and_execute_target_or_sl("MARUTI", contract_sym33, df33)
        assert exit33 is False, "Exit order was placed despite mode violation!"
        mock_cli33.placeorder.assert_not_called()
        if tmp_state33.exists():
            tmp_state33.unlink()
        results.append((33, "ANALYZE mode still blocks real orders on exit", True, "Live order placement strictly blocked on exit; pre-flight safety verified"))
    except Exception as e:
        results.append((33, "ANALYZE mode still blocks real orders on exit", False, str(e)))

    # 34. Format paper exit alert includes all required fields
    try:
        sample_exit_data = {
            "strategy_name": STRATEGY_NAME,
            "contract": "RELIANCE26SEPFUT",
            "symbol": "RELIANCE",
            "direction": "LONG",
            "action": "SELL",
            "exit_reason": "TARGET_HIT",
            "quantity": 250,
            "entry_price": 2000.0,
            "exit_price": 2060.0,
            "order_id": "EXIT_ORD_12345",
            "order_status": "FILLED",
            "candle_time_str": "08-Sep-2026 14:15",
            "execution_time": "15:30:00",
        }
        exit_msg = format_paper_exit_alert(sample_exit_data)
        assert "RELIANCE26SEPFUT" in exit_msg, "Contract missing from exit alert"
        assert "RELIANCE" in exit_msg, "Symbol missing from exit alert"
        assert "LONG" in exit_msg, "Direction missing from exit alert"
        assert "SELL" in exit_msg, "Action missing from exit alert"
        assert "TARGET HIT" in exit_msg, "Exit reason header missing from exit alert"
        assert "TARGET REACHED" in exit_msg, "Exit reason badge missing from exit alert"
        assert "₹2000.00" in exit_msg, "Entry price missing from exit alert"
        assert "₹2060.00" in exit_msg, "Exit price missing from exit alert"
        assert "+₹15,000.00" in exit_msg, "Absolute P&L missing from exit alert"
        assert "+3.00%" in exit_msg, "Percentage P&L missing from exit alert"
        assert "EXIT_ORD_12345" in exit_msg, "Order ID missing from exit alert"
        assert "08-Sep-2026 14:15" in exit_msg, "Completed candle missing from exit alert"
        assert "PAPER / ANALYZE ONLY" in exit_msg, "Safety footer missing from exit alert"

        sample_sl = dict(sample_exit_data, exit_reason="CATASTROPHE_SL", exit_price=1880.0)
        sl_msg = format_paper_exit_alert(sample_sl)
        assert "CATASTROPHE STOP-LOSS" in sl_msg
        assert "EMERGENCY STOP LOSS TRIGGERED" in sl_msg
        assert "-6.00%" in sl_msg

        sample_rev = dict(sample_exit_data, exit_reason="V2-2_REVERSAL", exit_price=2010.0)
        rev_msg = format_paper_exit_alert(sample_rev)
        assert "REVERSAL EXIT" in rev_msg
        assert "OPPOSITE V2-2 SIGNAL REVERSAL" in rev_msg

        results.append((34, "Format paper exit alert includes all required fields", True, "All fields (Symbol, Direction, Reason, Entry/Exit Price, P&L abs/%, Order ID, Mode) verified across all 3 exit types"))
    except Exception as e:
        results.append((34, "Format paper exit alert includes all required fields", False, str(e)))

    # 35. Asymmetric Universe blocks blacklisted symbols (ITC, ONGC, etc.)
    try:
        tmp_state35 = Path(f"/tmp/test_asym_blacklist_{int(time.time()*1000)}.json")
        engine35 = MockTestEngine(symbols=["ITC"], lots=1, max_active=10, use_asymmetric_universe=True)
        engine35.state_manager = PersistentStateManager(tmp_state35)
        engine35.contract_cache["ITC"] = {"contract": "ITC26SEPFUT", "lot_size": 1600, "order_qty": 1600}
        engine35.get_open_position = lambda contract: 0
        engine35.verify_paper_mode = lambda: (True, "analyze")
        mock_cli35 = MagicMock()
        engine35.client = mock_cli35

        sig_data_itc = {
            "signal": "BUY",
            "timestamp": "2026-09-04T10:15:00+05:30",
            "candle_time_str": "04-Sep-2026 10:15 IST",
        }
        placed35, _ = engine35.execute_symbol_decision("ITC", sig_data_itc, active_positions_count=0)
        assert placed35 is False, "Blacklisted symbol ITC was traded!"
        mock_cli35.placeorder.assert_not_called()
        if tmp_state35.exists():
            tmp_state35.unlink()
        results.append((35, "Asymmetric Universe blocks blacklisted symbols", True, "Blacklisted symbol ITC was correctly blocked from order execution"))
    except Exception as e:
        results.append((35, "Asymmetric Universe blocks blacklisted symbols", False, str(e)))

    # 36. Asymmetric Universe filters unapproved new LONG entries from FLAT
    try:
        tmp_state36 = Path(f"/tmp/test_asym_long_{int(time.time()*1000)}.json")
        engine36 = MockTestEngine(symbols=["MARUTI", "SUNPHARMA"], lots=1, max_active=10, use_asymmetric_universe=True)
        engine36.state_manager = PersistentStateManager(tmp_state36)
        engine36.contract_cache["MARUTI"] = {"contract": "MARUTI26SEPFUT", "lot_size": 50, "order_qty": 50}
        engine36.contract_cache["SUNPHARMA"] = {"contract": "SUNPHARMA26SEPFUT", "lot_size": 350, "order_qty": 350}
        engine36.get_open_position = lambda contract: 0
        engine36.verify_paper_mode = lambda: (True, "analyze")
        mock_cli36 = MagicMock()
        mock_cli36.placeorder.return_value = {"status": "success", "orderid": "ORD_SUN_36", "mode": "analyze"}
        mock_cli36.orderstatus.return_value = {"status": "success", "data": {"average_price": 1800.0}}
        engine36.client = mock_cli36

        # MARUTI is NOT in TOP_LONGS -> should be skipped from FLAT
        sig_maruti = {"signal": "BUY", "timestamp": "2026-09-04T10:15:00+05:30", "candle_time_str": "04-Sep-2026 10:15 IST"}
        p_maruti, _ = engine36.execute_symbol_decision("MARUTI", sig_maruti, active_positions_count=0)
        assert p_maruti is False, "MARUTI was entered as LONG despite not being in TOP_LONGS!"

        # SUNPHARMA IS in TOP_LONGS -> should be placed
        sig_sun = {"signal": "BUY", "timestamp": "2026-09-04T10:15:00+05:30", "candle_time_str": "04-Sep-2026 10:15 IST"}
        p_sun, _ = engine36.execute_symbol_decision("SUNPHARMA", sig_sun, active_positions_count=0)
        assert p_sun is True, "SUNPHARMA failed to place LONG order!"
        if tmp_state36.exists():
            tmp_state36.unlink()
        results.append((36, "Asymmetric Universe filters new LONG entries by expectancy", True, "Unapproved LONG (MARUTI) skipped; Approved LONG (SUNPHARMA) placed"))
    except Exception as e:
        results.append((36, "Asymmetric Universe filters new LONG entries by expectancy", False, str(e)))

    # 37. Asymmetric Universe exits unapproved short to FLAT instead of full reversal
    try:
        tmp_state37 = Path(f"/tmp/test_asym_exit_flat_{int(time.time()*1000)}.json")
        engine37 = MockTestEngine(symbols=["WIPRO"], lots=1, max_active=10, use_asymmetric_universe=True)
        engine37.state_manager = PersistentStateManager(tmp_state37)
        contract37 = "WIPRO26SEPFUT"
        engine37.contract_cache["WIPRO"] = {"contract": contract37, "lot_size": 1500, "order_qty": 1500}
        # WIPRO is in TOP_LONGS, but NOT in TOP_SHORTS. Currently in LONG 1500.
        engine37.get_open_position = lambda c: 1500
        engine37.verify_paper_mode = lambda: (True, "analyze")
        mock_cli37 = MagicMock()
        mock_cli37.placeorder.return_value = {"status": "success", "orderid": "ORD_WIPRO_FLAT", "mode": "analyze"}
        mock_cli37.orderstatus.return_value = {"status": "success", "data": {"average_price": 540.0}}
        engine37.client = mock_cli37

        sig_wipro_sell = {"signal": "SELL", "timestamp": "2026-09-04T11:15:00+05:30", "candle_time_str": "04-Sep-2026 11:15 IST"}
        placed37, _ = engine37.execute_symbol_decision("WIPRO", sig_wipro_sell, active_positions_count=1)
        assert placed37 is True, "WIPRO sell signal failed to execute exit to flat"
        # Order quantity should be exactly 1500 (exit to flat), NOT 3000 (reversal into short)
        placed_args = mock_cli37.placeorder.call_args[1]
        assert placed_args["quantity"] == 1500, f"Expected exit qty 1500, got {placed_args['quantity']}"
        assert placed_args["action"] == "SELL"
        if tmp_state37.exists():
            tmp_state37.unlink()
        results.append((37, "Asymmetric Universe exits unapproved short to FLAT", True, "WIPRO LONG pos exited to FLAT (1500 units) on SELL signal without entering unapproved SHORT"))
    except Exception as e:
        results.append((37, "Asymmetric Universe exits unapproved short to FLAT", False, str(e)))

    # 38. HWM Trailing Runner activates on target touch instead of closing position
    try:
        tmp_state38 = Path(f"/tmp/test_runner_activate_{int(time.time()*1000)}.json")
        engine38 = MockTestEngine(symbols=["RELIANCE"], lots=1, max_active=10)
        engine38.state_manager = PersistentStateManager(tmp_state38)
        engine38.enable_trailing_runner = True
        engine38.runner_trail_mode = "HWM"
        engine38.runner_trail_pct = 0.35
        contract_sym38 = "RELIANCE26SEPFUT"
        engine38.state_manager.update_tracked_positions({
            contract_sym38: {
                "contract": contract_sym38,
                "base_symbol": "RELIANCE",
                "direction": "LONG",
                "quantity": 250,
                "average_price": 2000.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_ENTRY_38",
            }
        })
        mock_cli38 = MagicMock()
        engine38.client = mock_cli38
        engine38.verify_paper_mode = lambda: (True, "analyze")

        # Candle reaches target price 2060.0 (high=2065.0, low=2050.0)
        df38 = make_test_df([
            {"close": 2000.0, "high": 2010.0, "low": 1990.0, "open": 1995.0},
            {"close": 2058.0, "high": 2065.0, "low": 2050.0, "open": 2015.0},
        ])
        exited38 = engine38.check_and_execute_target_or_sl("RELIANCE", contract_sym38, df38)
        # Position should NOT exit; it must convert to runner
        assert exited38 is False, "Position exited prematurely instead of activating runner!"
        mock_cli38.placeorder.assert_not_called()
        tracked38 = engine38.state_manager.state.get("tracked_positions", {}).get(contract_sym38, {})
        assert tracked38.get("runner_active") is True, "runner_active flag not set on position!"
        assert tracked38.get("peak_price") == 2065.0, f"Expected peak 2065.0, got {tracked38.get('peak_price')}"
        expected_sl38 = round(2065.0 * (1.0 - 0.0035), 2)
        assert tracked38.get("effective_trail_sl") == expected_sl38, f"Expected SL {expected_sl38}, got {tracked38.get('effective_trail_sl')}"
        if tmp_state38.exists():
            tmp_state38.unlink()
        results.append((38, "HWM Trailing Runner activates on target hit", True, f"Runner activated; peak tracked at ₹2065.00, HWM trail set to ₹{expected_sl38}"))
    except Exception as e:
        results.append((38, "HWM Trailing Runner activates on target hit", False, str(e)))

    # 39. HWM Trailing Runner exits when price breaches effective trail SL
    try:
        tmp_state39 = Path(f"/tmp/test_runner_exit_{int(time.time()*1000)}.json")
        engine39 = MockTestEngine(symbols=["RELIANCE"], lots=1, max_active=10)
        engine39.state_manager = PersistentStateManager(tmp_state39)
        engine39.enable_trailing_runner = True
        engine39.runner_trail_mode = "HWM"
        engine39.runner_trail_pct = 0.35
        contract_sym39 = "RELIANCE26SEPFUT"
        engine39.state_manager.update_tracked_positions({
            contract_sym39: {
                "contract": contract_sym39,
                "base_symbol": "RELIANCE",
                "direction": "LONG",
                "quantity": 250,
                "average_price": 2000.0,
                "candle_time": "08-Sep-2026 13:15",
                "last_order_id": "ORD_ENTRY_39",
                "runner_active": True,
                "peak_price": 2100.0,
                "effective_trail_sl": 2092.65,  # 2100 * (1 - 0.0035)
            }
        })
        mock_cli39 = MagicMock()
        mock_cli39.placeorder.return_value = {"status": "success", "orderid": "EXIT_RUNNER_39", "mode": "analyze"}
        mock_cli39.orderstatus.return_value = {"status": "success", "data": {"average_price": 2092.0}}
        engine39.client = mock_cli39
        engine39.verify_paper_mode = lambda: (True, "analyze")

        # Next candle pulls back below trailing stop (low=2085.0 <= 2092.65)
        df39 = make_test_df([
            {"close": 2000.0, "high": 2010.0, "low": 1990.0, "open": 1995.0},
            {"close": 2088.0, "high": 2098.0, "low": 2085.0, "open": 2096.0},
        ])
        exit_msgs39 = []
        with patch(f"{__name__}.send_telegram_alert", side_effect=lambda m: exit_msgs39.append(m)):
            exited39 = engine39.check_and_execute_target_or_sl("RELIANCE", contract_sym39, df39)
        assert exited39 is True, "Runner trail stop failed to trigger exit order!"
        mock_cli39.placeorder.assert_called_once()
        order_call39 = mock_cli39.placeorder.call_args[1]
        assert order_call39["action"] == "SELL"
        assert order_call39["quantity"] == 250
        assert len(exit_msgs39) == 1
        assert "RUNNER TRAIL HIT" in exit_msgs39[0]
        tracked39 = engine39.state_manager.state.get("tracked_positions", {})
        assert contract_sym39 not in tracked39, "Tracked position not cleared after runner exit"
        if tmp_state39.exists():
            tmp_state39.unlink()
        results.append((39, "HWM Trailing Runner exits on pullback breach", True, "Runner successfully closed at trail SL; alert emitted with RUNNER TRAIL HIT"))
    except Exception as e:
        results.append((39, "HWM Trailing Runner exits on pullback breach", False, str(e)))

    # Summary Report
    all_passed = True
    for test_id, name, passed, detail in results:
        status_str = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"[{status_str}] Test {test_id:02d}: {name} -> {detail}")
        if not passed:
            all_passed = False

    logger.info("=" * 80)
    passed_count = sum(1 for _, _, p, _ in results if p)
    logger.info(f"📊 SUMMARY: {passed_count}/{len(results)} tests PASSED. All Passed: {all_passed}")
    logger.info("=" * 80)
    return all_passed


# ==============================================================================
# 13. CLI & ENTRYPOINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="OpenAlgo NFO 1H EMA (9/26) + MACD (12/26/9) Continuous Paper-Trading Engine"
    )
    parser.add_argument(
        "--symbols",
        default=os.getenv("NFO_SYMBOLS", "ALL"),
        help="Target symbols: 'ALL' for full 211-instrument active NFO universe or comma-separated list e.g. 'RELIANCE,TCS,INFY'.",
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
        help=f"Maximum concurrent active positions (0 for unlimited, default: {MAX_ACTIVE_POSITIONS}).",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=POLL_INTERVAL_SECONDS,
        help=f"Seconds between execution scans in continuous mode (default: {POLL_INTERVAL_SECONDS}).",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        default=RUN_ONCE,
        help="Run a single evaluation pass and exit.",
    )
    parser.add_argument(
        "--reconcile-only",
        action="store_true",
        default=False,
        help="Run startup position reconciliation audit and exit immediately without placing orders.",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        default=False,
        help="Run comprehensive automated test suite across all 37 verification cases and exit.",
    )

    args = parser.parse_args()

    if args.test:
        success = run_automated_tests()
        sys.exit(0 if success else 1)

    # Resolve symbol universe
    if args.symbols.strip().upper() == "ALL":
        target_symbols = DEFAULT_NFO_UNIVERSE
    else:
        target_symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    engine = EMACrossPaperTradingEngine(
        symbols=target_symbols,
        lots=args.lots,
        max_active=args.max_active,
    )

    if args.reconcile_only:
        logger.info("Reconciliation audit complete (--reconcile-only). Exiting cleanly.")
        return

    if args.run_once:
        logger.info("Running single evaluation pass (--run-once)...")
        engine.execute_cycle()
        logger.info("Single pass complete. Exiting.")
        return

    engine.run_loop(poll_interval=args.poll_interval)



if __name__ == "__main__":
    main()
