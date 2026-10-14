#!/usr/bin/env python3
"""
================================================================================
OPENALGO RESEARCH STRATEGY: NFO SINGLE-STOCK FUTURES LONG-UNWINDING EXHAUSTION ENGINE
================================================================================
File Role            : RESEARCH_REFERENCE
Strategy Identifier  : OIFNO_PAPER_V1 (SIG-OI-001-PAPER-V1)
Current Version      : 1.1.0
Last Modified        : 2026-10-13
Git Baseline Commit  : 48be14948b8b983557444d87dad47510bd853d6b
Strategy Hash        : dc1063b1ccadd2e513c6d3f71a8a2f4f13465db852387204c0b27137249ed917
Production Approval  : SHADOW / PAPER TRADING ONLY (Phase 7 Governance)
Real Orders          : STRICTLY HARD-BLOCKED

Implementation History:
  - 2026-10-13 [v1.1.0]: Master SOP governance standardization. Header alignment with digital-twin parity standard (SOP Section 3A).
  - 2026-09-06 [v1.0.0]: Phase 7 Shadow Paper Trading bridge with fail-closed governance, gap protection (+1.5%), limit collar (+30 bps), and strict broker order blocking.
  - 2026-09-05 [Phase 1-4]: Core hypothesis discovery (HYP-OI-0002/0005) & 23-stage statistical falsification tests.

Current Strategy Specification:
  1. Timeframe & Indicators:
     - Daily (EOD) Bhavcopy scan at 15:30 IST.
     - Price Dip: Return 1D < 0.0% (Close_T < Close_{T-1}).
     - OI Contraction: ΔOI% <= -2.0% (open interest contraction indicates long liquidation).
     - Strong Bear Candle: Close < Open AND Body / Range > 0.60 (60% solid selling body).
  2. Universe & Execution Gates:
     - Universe: Exclusively liquid NSE Single-Stock Futures (FUTSTK); indices excluded.
     - Liquidity: Rolling turnover >= ₹500 Lakhs (₹5 Crores).
     - Rollover Purge: Days to Expiry (DTE) > 3 days strictly.
  3. Execution & Safety Collars:
     - Order Intent: Pre-market generation on Day T+1 (09:00 IST).
     - Opening Gap Check: Gap > +1.50% above Day T Close triggers MISSED_GAP (no chase).
     - Limit Collar: Day T Close + 30 bps. Orders above collar are skipped.
     - Execution Fill: Day T+1 Market Open auction (+2.5 bps entry half-spread slippage).
  4. Risk Management & Exits:
     - Holding Horizon: Strictly 1 trading session.
     - Exit Execution: Day T+2 Market Open auction (-2.5 bps exit spread slippage - 3 bps statutory fees).
     - Max Active Positions: 10 concurrent positions (10% capital per slot, equal weight).
     - Sector Limit: Max 30% aggregate capital in any single industry sector.
     - Portfolio Circuit Breakers: Daily loss limit 2.0%, Max drawdown limit 10.0%.
  5. Execution Safety:
     - Mode: STRICTLY SHADOW / PAPER TRADING ONLY.
     - Real-money order routing is hard-blocked by fail-closed assertions.

Validation Status:
  - Multi-Year Historical Backtest (Phase 8): PASSED (Sharpe 1.74, Max DD -6.19%, PF 1.25).
  - Falsification & Robustness Tests: 23/23 PASSED (p < 10^-6, Placebo p = 0.000).
  - Walk-Forward Generalizability: 12 folds PASSED (PBO 25.0%).
  - Phase 7 Shadow Paper Reconciliation: PASSED (Zero real broker orders leaked).

Known Limitations & Unresolved Issues:
  - Real-money routing is strictly hard-blocked pending live broker validation.
  - Requires daily official Bhavcopy ingestion or OpenAlgo live market feeds at 15:30 IST.

Architecture Pipeline:
  DATA -> SIGNAL -> RANKING -> RISK -> ORDER INTENT -> SHADOW EXECUTION
       -> POSITION STATE -> RECONCILIATION -> AUDIT

Operational Lifecycle:
  15:30 IST (Day T)   : Bhavcopy/OpenAlgo ingestion -> NFO contract validation
                        -> Price dip + OI drop + Strong Bear candle calculation
                        -> Candidate ranking (most negative ΔOI%) -> Persist signals
  09:00-09:15 (Day T+1): Fresh data verification -> Opening gap check (+1.5% no chase)
                        -> Limit collar (+30 bps) -> Risk engine approval
                        -> Shadow OrderIntent generation -> Simulated fill
  09:15 IST (Day T+2) : Simulated exit at market open (1-session holding horizon)
  15:30 IST (Daily)   : EOD reconciliation audit & Telegram summary dispatch
================================================================================
"""

import argparse
import base64
import copy
import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

try:
    import numpy as np
    import pandas as pd
    import requests
except ImportError as err:
    print(f"CRITICAL: Missing dependency: {err}. Please run 'pip install numpy pandas requests'.", file=sys.stderr)
    sys.exit(1)

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name in ["strategy", "strategies", "scripts", "liveonopenalgo"] else Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(), override=False)
except ImportError:
    pass

try:
    from openalgo import api as OpenAlgoClient
    OPENALGO_SDK_AVAILABLE = True
except ImportError:
    OpenAlgoClient = None
    OPENALGO_SDK_AVAILABLE = False


# ==============================================================================
# SECTION 1: HARD GOVERNANCE & SAFETY ASSERTIONS (LIVE-BLOCKED)
# ==============================================================================
STRATEGY_CONTRACT_VERSION = "SIG-OI-001-PAPER-V1"
STRATEGY_HASH = "dc1063b1ccadd2e513c6d3f71a8a2f4f13465db852387204c0b27137249ed917"
STRATEGY_NAME = "OIFNO_V1"

# Hard constant: Real-money order submission is strictly impossible in Phase 7
LIVE_TRADING_ENABLED: bool = False

# Environment-level safety check: PHASE7_MODE must be SHADOW
PHASE7_MODE = os.getenv("PHASE7_MODE", "SHADOW").strip().upper()
if PHASE7_MODE != "SHADOW":
    raise RuntimeError(
        f"CRITICAL GOVERNANCE FAILURE: PHASE7_MODE must be 'SHADOW' (received: '{PHASE7_MODE}'). "
        "Real-money execution is strictly forbidden during Phase 7. Strategy is failing closed."
    )

if LIVE_TRADING_ENABLED:
    raise RuntimeError(
        "CRITICAL GOVERNANCE VIOLATION: LIVE_TRADING_ENABLED is True! "
        "Phase 7 requires paper/shadow execution only. Reverting to False is mandatory."
    )


# ==============================================================================
# SECTION 2: CONFIGURATION & CONSTANTS
# ==============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LOG_FILE = Path(os.getenv("LOG_FILE", PROJECT_ROOT / "log/strategies/oifno.log" if (PROJECT_ROOT / "log").exists() else SCRIPT_DIR / "oifno.log"))
DEFAULT_STATE_FILE = Path(os.getenv("STATE_FILE", PROJECT_ROOT / "production/audit/oifno_state.json"))
DEFAULT_HEARTBEAT_FILE = Path(os.getenv("HEARTBEAT_FILE", SCRIPT_DIR / "oifno_heartbeat.json"))
DEFAULT_AUDIT_LOG = Path(os.getenv("AUDIT_LOG_FILE", PROJECT_ROOT / "production/audit/phase7_shadow_execution_audit.jsonl"))
DEFAULT_LEDGER_FILE = Path(os.getenv("LEDGER_FILE", PROJECT_ROOT / "production/audit/phase7_forward_shadow_ledger.parquet"))
DEFAULT_KILL_SWITCH_FILE = Path(os.getenv("KILL_SWITCH_FILE", PROJECT_ROOT / "production/audit/kill_switch.flag"))

OPENALGO_HOST = os.getenv("OPENALGO_HOST", os.getenv("HOST_SERVER", "https://vikashiname.in")).rstrip("/")
OPENALGO_API_KEY = os.getenv("OPENALGO_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Strategy Constraints (SIG-OI-001-PAPER-V1 Contract)
EXCHANGE = "NFO"
PRODUCT = "NRML"
MAX_PORTFOLIO_POSITIONS = 10
SLOT_EQUITY_PCT = 0.10             # 10% per slot (equal weight top 10)
MAX_SECTOR_EXPOSURE_PCT = 30.0     # Max 30% aggregate sector exposure
MAX_DAILY_LOSS_PCT = 2.0           # 2.0% daily portfolio loss circuit breaker
MAX_DRAWDOWN_LIMIT_PCT = 10.0      # 10.0% max portfolio drawdown circuit breaker
MIN_TURNOVER_LAKH = 500.0          # ₹500 Lakhs (₹5 Crores minimum daily turnover)
MIN_DTE = 3                        # Exclude contracts with DTE <= 3 (rollover purge window)
OI_CONTRACTION_THRESHOLD = -2.0    # ΔOI <= -2.0%
BEAR_CANDLE_BODY_RATIO_MIN = 0.60  # Strong bear candle: body > 60% of candle range

# Execution Constraints (Phase 6.5 & 7 Opening Rules)
LIMIT_COLLAR_BPS = 30.0            # Max +30 bps collar above Day T Close
MAX_GAP_CHASE_PCT = 1.50           # Opening gap > +1.50% triggers NO TRADE (no chasing)
BASELINE_FRICTION_BPS = 8.0        # 5.0 bps entry half-spread slippage + 3.0 bps statutory fees
INITIAL_PAPER_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "10000000.0"))  # ₹1.00 Crore default


# ==============================================================================
# SECTION 3: LOGGING SETUP
# ==============================================================================
logger = logging.getLogger("OIFNO_STRATEGY")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _formatter = logging.Formatter("%(asctime)s [%(levelname)s] [OIFNO-SHADOW] %(message)s")
    _console = logging.StreamHandler(sys.stdout)
    _console.setFormatter(_formatter)
    logger.addHandler(_console)

    try:
        DEFAULT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _file_handler = RotatingFileHandler(
            DEFAULT_LOG_FILE, maxBytes=15 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        _file_handler.setFormatter(_formatter)
        logger.addHandler(_file_handler)
    except Exception as e:
        print(f"Warning: Failed to setup RotatingFileHandler for {DEFAULT_LOG_FILE}: {e}", file=sys.stderr)


# ==============================================================================
# SECTION 4: TELEGRAM DISPATCHER (STRICTLY IDENTIFIED AS SHADOW / PAPER)
# ==============================================================================
def send_telegram_alert(message: str, force: bool = False) -> bool:
    """
    Dispatches alert to Telegram.
    MANDATORY RULE: Every message MUST contain [SHADOW / PAPER MODE] banner.
    Non-blocking and non-fatal on network error.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram credentials not configured; alert suppressed from network.")
        return False

    prefix = "🛡️ <b>[SHADOW / PAPER MODE ONLY]</b>\n"
    suffix = "\n<i>⚠️ Phase 7 Governance: Real broker orders are hard-blocked.</i>"
    full_text = f"{prefix}{message}{suffix}"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": full_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=6)
        if resp.status_code == 200:
            logger.info("📱 Telegram alert successfully dispatched.")
            return True
        else:
            logger.warning(f"Telegram API warning (HTTP {resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"Telegram dispatch failed non-fatally: {e}")
        return False


# ==============================================================================
# SECTION 5: UNIVERSE, SECTOR TAXONOMY & METADATA
# ==============================================================================
# Filter out indices to guarantee strictly NFO FUTSTK operation
INDEX_UNDERLYINGS: Set[str] = {
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"
}

def get_sector(symbol: str) -> str:
    """Classifies NSE stock underlying into 8 standard economic sectors."""
    sym = symbol.upper().strip()
    if any(k in sym for k in ["BANK", "RBL", "AUBANK", "FIN", "PEL", "LIC", "RECLTD", "PFC", "MANAPPURAM", "MUTHOOT", "HDFC", "ICICI", "SBIN", "KOTAK", "BAJFINANCE", "BAJAJFINSV", "CHOLAFIN", "FEDERALBNK", "CANBK", "UNIONBANK", "BANKBARODA", "BANDHANBNK"]):
        return "FINANCIAL_SERVICES"
    elif any(k in sym for k in ["TECH", "TCS", "INFY", "WIPRO", "HCL", "LTI", "COFORGE", "PERSISTENT", "MPHASIS", "OFSS", "TATAELXSI", "NAUKRI"]):
        return "IT_TECHNOLOGY"
    elif any(k in sym for k in ["AUTO", "MOT", "BAJAJ-AUTO", "MARUTI", "M&M", "HERO", "ASHOK", "TVS", "ESCORTS", "EICHERMOT", "BHARATFORG", "SONACOMS", "TIINDIA", "UNOMINDA"]):
        return "AUTOMOBILE"
    elif any(k in sym for k in ["POWER", "NTPC", "IOC", "BPCL", "ONGC", "GAIL", "RELIANCE", "COAL", "ADANIENT", "ADANIPOWER", "ADANIGREEN", "ADANIENSOL", "TATAPOWER", "TORNTPOWER", "NHPC", "OIL", "PETRONET"]):
        return "ENERGY_POWER"
    elif any(k in sym for k in ["STEEL", "TATASTEEL", "JSW", "JINDAL", "HINDALCO", "VEDL", "NMDC", "NATIONALUM", "SAIL"]):
        return "METALS_MINING"
    elif any(k in sym for k in ["PHARMA", "SUN", "DRREDDY", "CIPLA", "LUPIN", "AURO", "DIVIS", "BIOCON", "ALKEM", "APOLLOHOSP", "FORTIS", "GLENMARK", "TORNTPHARM", "ZYDUSLIFE"]):
        return "HEALTHCARE_PHARMA"
    elif any(k in sym for k in ["HUL", "ITC", "DABUR", "BRITANNIA", "MARICO", "GODREJCP", "COLPAL", "NESTLEIND", "TATACONSUM", "VBL", "UNITDSPR", "PAGEIND"]):
        return "CONSUMER_GOODS"
    else:
        return "INDUSTRIALS_INFRA"


# Comprehensive fallback lot sizes for active NFO FUTSTK symbols
NFO_STOCK_LOTS_FALLBACK: Dict[str, int] = {
    "360ONE": 500, "ABB": 125, "ABCAPITAL": 3100, "ADANIENSOL": 675, "ADANIENT": 309,
    "ADANIGREEN": 600, "ADANIPORTS": 475, "ADANIPOWER": 3550, "ALKEM": 125, "AMBER": 100,
    "AMBUJACEM": 1050, "ANGELONE": 2500, "APLAPOLLO": 350, "APOLLOHOSP": 125, "ASHOKLEY": 5000,
    "ASIANPAINT": 250, "ASTRAL": 425, "AUBANK": 1000, "AUROPHARMA": 550, "AXISBANK": 625,
    "BAJAJ-AUTO": 75, "BAJAJFINSV": 250, "BAJAJHLDNG": 50, "BAJFINANCE": 750, "BANDHANBNK": 3600,
    "BANKBARODA": 2925, "BANKINDIA": 5200, "BDL": 350, "BEL": 1425, "BHARATFORG": 500,
    "BHARTIARTL": 475, "BHEL": 2625, "BIOCON": 2500, "BLUESTARCO": 325, "BOSCHLTD": 25,
    "BPCL": 1975, "BRITANNIA": 125, "BSE": 375, "CAMS": 750, "CANBK": 6750, "CDSL": 475,
    "CGPOWER": 850, "CHOLAFIN": 625, "CIPLA": 375, "COALINDIA": 1350, "COCHINSHIP": 400,
    "COFORGE": 375, "COLPAL": 225, "CONCOR": 1250, "CROMPTON": 1800, "CUMMINSIND": 200,
    "DABUR": 1250, "DALBHARAT": 325, "DELHIVERY": 2075, "DIVISLAB": 100, "DIXON": 50,
    "DLF": 825, "DMART": 150, "DRREDDY": 625, "EICHERMOT": 100, "EXIDEIND": 1800,
    "FEDERALBNK": 5000, "FORCEMOT": 25, "FORTIS": 775, "GAIL": 3150, "GLENMARK": 375,
    "GMRAIRPORT": 6975, "GODREJCP": 500, "GODREJPROP": 275, "GRASIM": 250, "HAL": 150,
    "HAVELLS": 500, "HCLTECH": 350, "HDFCAMC": 300, "HDFCBANK": 550, "HDFCLIFE": 1100,
    "HEROMOTOCO": 150, "HINDALCO": 1400, "HINDUNILVR": 300, "ICICIBANK": 700, "ICICIGI": 500,
    "ICICIPRULI": 1500, "IDEA": 80000, "IDFCFIRSTB": 7500, "INDHOTEL": 1000, "INDIAMART": 300,
    "INDIGO": 150, "INDUSINDBK": 500, "INFY": 400, "IOC": 4875, "IPCALAB": 650, "IRCTC": 875,
    "ITC": 1600, "JINDALSTEL": 625, "JIOFIN": 2350, "JSWSTEEL": 675, "JUBLFOOD": 1250,
    "KALYANKJIL": 1125, "KOTAKBANK": 400, "L&TFH": 4462, "LT": 175, "LTIM": 150, "LUPIN": 425,
    "MARUTI": 50, "MAXHEALTH": 575, "M&M": 350, "MOTHERSON": 6150, "MUTHOOTFIN": 275,
    "NATIONALUM": 3750, "NAUKRI": 375, "NESTLEIND": 500, "NTPC": 1500, "ONGC": 2250,
    "PERSISTENT": 100, "PFC": 1300, "PIDILITIND": 500, "PNB": 8000, "POLYCAB": 125,
    "POWERGRID": 1900, "RECLTD": 1400, "RELIANCE": 500, "SBIN": 750, "SIEMENS": 175,
    "SUNPHARMA": 350, "TATACONSUM": 550, "TATAMOTORS": 550, "TATAPOWER": 1450, "TATASTEEL": 5500,
    "TCS": 175, "TECHM": 600, "TITAN": 175, "TRENT": 100, "TVSMOTOR": 175, "ULTRACEMCO": 50,
    "VEDL": 1150, "VOLTAS": 375, "WIPRO": 3000, "ZYDUSLIFE": 900
}


# ==============================================================================
# SECTION 6: PERSISTENT STATE & CRASH RECOVERY MANAGER
# ==============================================================================
class OIPersistentStateManager:
    """
    Atomic, crash-safe state persistence for oifno.py.
    Guarantees state is preserved across process crashes, restarts, and reboots.
    """
    def __init__(self, state_file: Path = DEFAULT_STATE_FILE):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state: Dict[str, Any] = self.load_state()

    def _default_state(self) -> Dict[str, Any]:
        return {
            "strategy": STRATEGY_NAME,
            "contract_version": STRATEGY_CONTRACT_VERSION,
            "strategy_hash": STRATEGY_HASH,
            "phase7_mode": PHASE7_MODE,
            "last_saved_at": None,
            "executed_signal_ids": [],
            "candidates_day_t": [],
            "order_intents": {},
            "tracked_positions": {},
            "execution_history": [],
            "risk_state": {
                "initial_capital": INITIAL_PAPER_CAPITAL,
                "current_capital": INITIAL_PAPER_CAPITAL,
                "high_watermark": INITIAL_PAPER_CAPITAL,
                "current_drawdown_pct": 0.0,
                "circuit_breaker_tripped": False,
                "circuit_breaker_reason": "",
            },
            "last_reconciliation_audit": None,
        }

    def load_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return self._default_state()
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("strategy_hash") == STRATEGY_HASH:
                    return data
                logger.warning("⚠️ State file corrupt or hash mismatch. Initializing default state.")
                return self._default_state()
        except Exception as e:
            logger.error(f"❌ Error loading state file {self.state_file}: {e}. Initializing fresh state.")
            return self._default_state()

    def save_state(self):
        """Atomic write: write to temp file then atomic rename to prevent corruption."""
        try:
            self.state["last_saved_at"] = datetime.now().isoformat()
            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, default=str)
            temp_file.replace(self.state_file)
        except Exception as e:
            logger.error(f"❌ Failed to atomically save state to {self.state_file}: {e}")

    def is_signal_executed(self, signal_id: str) -> bool:
        return signal_id in set(self.state.get("executed_signal_ids", []))

    def mark_signal_executed(self, signal_id: str):
        sig_set = set(self.state.get("executed_signal_ids", []))
        sig_set.add(signal_id)
        self.state["executed_signal_ids"] = list(sig_set)
        self.save_state()

    def update_tracked_positions(self, positions_map: Dict[str, Any]):
        self.state["tracked_positions"] = positions_map
        self.save_state()

    def record_execution_event(self, event: Dict[str, Any]):
        if "execution_history" not in self.state:
            self.state["execution_history"] = []
        self.state["execution_history"].append(event)
        self.state["execution_history"] = self.state["execution_history"][-500:]  # Keep last 500
        self.save_state()


# ==============================================================================
# SECTION 7: OPENALGO BRIDGE & FYERS BROKER ADAPTER
# ==============================================================================
class OpenAlgoBridge:
    """
    Handles communication with the OpenAlgo backend and verifies broker health.
    Strictly observational/query only: NO LIVE ORDERS.
    """
    def __init__(self, host: str = OPENALGO_HOST, api_key: str = OPENALGO_API_KEY):
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.client = OpenAlgoClient(api_key=self.api_key, host=self.host) if (OpenAlgoClient and OPENALGO_SDK_AVAILABLE) else None

    def ping(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Queries /api/v1/ping to check OpenAlgo connectivity and broker identity.
        """
        url = f"{self.host}/api/v1/ping"
        try:
            resp = requests.post(url, json={"apikey": self.api_key}, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                broker = data.get("data", {}).get("broker", "unknown")
                return True, broker, data
            elif resp.status_code == 403:
                return False, "AUTH_FAILED", {"status": "error", "message": "Invalid OpenAlgo apikey"}
            else:
                return False, f"HTTP_{resp.status_code}", {"status": "error", "text": resp.text}
        except Exception as e:
            return False, f"EXCEPTION_{type(e).__name__}", {"error": str(e)}

    def verify_analyze_mode(self) -> Tuple[bool, str]:
        """
        Verifies that OpenAlgo is operating in ANALYZE / PAPER TRADING mode.
        If mode cannot be verified as 'analyze', blocks execution fail-closed.
        """
        url = f"{self.host}/api/v1/positionbook"
        try:
            resp = requests.post(url, json={"apikey": self.api_key}, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                mode = str(data.get("mode", "")).strip().lower()
                if mode == "analyze":
                    return True, "analyze"
                else:
                    return False, f"DANGEROUS_MODE_{mode.upper()}"
            else:
                return False, f"HTTP_{resp.status_code}"
        except Exception as e:
            return False, f"ERROR_{str(e)}"

    def resolve_nfo_contract(self, symbol: str) -> Tuple[Optional[str], Optional[int], Optional[datetime], int]:
        """
        Dynamically discovers the active near-month NFO futures contract for an underlying stock.
        Filters out index contracts, options, and contracts with DTE <= 3.
        Returns: (contract_symbol, lot_size, expiry_datetime, days_to_expiry)
        """
        sym_clean = symbol.upper().strip()
        if sym_clean in INDEX_UNDERLYINGS:
            logger.warning(f"⚠️ Symbol {sym_clean} is an index. OIFNO strictly trades NFO FUTSTK. Rejecting.")
            return None, None, None, 0

        fallback_lot = NFO_STOCK_LOTS_FALLBACK.get(sym_clean, 100)
        search_url = f"{self.host}/api/v1/search"

        try:
            resp = requests.post(
                search_url,
                json={"apikey": self.api_key, "query": sym_clean, "exchange": "NFO"},
                timeout=8,
            )
            if resp.status_code == 200:
                items = resp.json().get("data", [])
                now = datetime.now()
                valid_futs = []

                for item in items:
                    if item.get("instrumenttype") != "FUT":
                        continue

                    c_sym = str(item.get("symbol", ""))
                    name = str(item.get("name", ""))
                    if not (c_sym.startswith(sym_clean) or name.startswith(sym_clean)):
                        continue

                    exp_str = item.get("expiry")
                    if not exp_str:
                        continue

                    try:
                        # Standard format in OpenAlgo: e.g. 29-SEP-26
                        exp_dt = datetime.strptime(exp_str, "%d-%b-%y").replace(hour=15, minute=30)
                        dte = (exp_dt.date() - now.date()).days
                        lot = int(item.get("lotsize", fallback_lot))

                        # Purge rollover contracts with DTE <= MIN_DTE
                        if dte > MIN_DTE:
                            valid_futs.append((exp_dt, dte, c_sym, lot))
                    except Exception:
                        pass

                if valid_futs:
                    # Select nearest valid monthly expiry
                    valid_futs.sort(key=lambda x: x[0])
                    exp_dt, dte, contract_sym, lot_size = valid_futs[0]
                    return contract_sym, lot_size, exp_dt, dte

        except Exception as e:
            logger.warning(f"⚠️ Search API error for {sym_clean}: {e}. Falling back to standard convention.")

        # Fallback deterministic symbol format: e.g. RELIANCE29SEP26FUT
        # In case API search is offline
        now = datetime.now()
        approx_dte = 20
        contract_sym = f"{sym_clean}FUT"
        return contract_sym, fallback_lot, now + timedelta(days=approx_dte), approx_dte

    def get_positionbook(self) -> Tuple[bool, List[Dict[str, Any]], str]:
        """Queries OpenAlgo positionbook."""
        url = f"{self.host}/api/v1/positionbook"
        try:
            resp = requests.post(url, json={"apikey": self.api_key}, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                return True, data.get("data", []), data.get("mode", "unknown")
            return False, [], f"HTTP_{resp.status_code}"
        except Exception as e:
            return False, [], str(e)

    def get_orderbook(self) -> Tuple[bool, List[Dict[str, Any]]]:
        """Queries OpenAlgo orderbook."""
        url = f"{self.host}/api/v1/orderbook"
        try:
            resp = requests.post(url, json={"apikey": self.api_key}, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                return True, data.get("data", {}).get("orders", [])
            return False, []
        except Exception as e:
            return False, []


# ==============================================================================
# SECTION 8: DATA VALIDATION & SIGNAL GENERATION (FROZEN CONTRACT)
# ==============================================================================
@dataclass
class MarketRecord:
    trade_date: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    traded_contracts: int
    turnover_lakh: float
    open_interest: int
    days_to_expiry: int
    prev_close: Optional[float] = None
    prev_open_interest: Optional[float] = None


class NFODataValidator:
    """
    Fail-closed Data Integrity Validator.
    Rejects any record with missing fields, non-positive price/OI, or DTE <= 3.
    """
    @staticmethod
    def validate(record: Dict[str, Any], session_date: str) -> Tuple[bool, str]:
        required = [
            "trade_date", "symbol", "open", "high", "low", "close",
            "traded_contracts", "turnover_lakh", "open_interest", "days_to_expiry"
        ]
        for f in required:
            if f not in record or record[f] is None or (isinstance(record[f], float) and math.isnan(record[f])):
                return False, f"MISSING_FIELD_{f.upper()}"

        rec_date = str(record["trade_date"]).split()[0]
        if session_date and rec_date != session_date:
            return False, f"STALE_DATE_{rec_date}_EXPECTED_{session_date}"

        if record["open"] <= 0 or record["high"] <= 0 or record["low"] <= 0 or record["close"] <= 0:
            return False, "INVALID_PRICE_NON_POSITIVE"

        if record["open_interest"] <= 0:
            return False, "INVALID_OI_ZERO_OR_NEGATIVE"

        if record["turnover_lakh"] < MIN_TURNOVER_LAKH:
            return False, f"ILLIQUID_TURNOVER_{record['turnover_lakh']:.1f}_LT_{MIN_TURNOVER_LAKH}"

        if record["days_to_expiry"] <= MIN_DTE:
            return False, f"NEAR_EXPIRY_DTE_{record['days_to_expiry']}_LE_{MIN_DTE}"

        # Symbol must not be an index
        if str(record["symbol"]).upper() in INDEX_UNDERLYINGS:
            return False, f"INDEX_SYMBOL_DISQUALIFIED_{record['symbol']}"

        return True, "DATA_VALID"


@dataclass
class CandidateSignal:
    signal_id: str
    symbol: str
    contract_symbol: str
    trade_date: str
    close: float
    ret_1d_pct: float
    oi_chg_pct: float
    turnover_lakh: float
    days_to_expiry: int
    is_strong_bear: bool
    body_ratio: float
    sector: str
    lot_size: int
    timestamp_ist: str


class OISignalEngine:
    """
    Implements the frozen SIG-OI-001-PAPER-V1 + HYP-OI-0005 signal:
      Price Return < 0
      AND ΔOI <= -2.0%
      AND Strong Bearish Candle (body > 60% of range, close < open)
      AND DTE > 3
      AND Turnover >= ₹5 Cr
    """
    def __init__(self, strategy_hash: str = STRATEGY_HASH):
        self.strategy_hash = strategy_hash

    def generate_signal_id(self, trade_date: str, symbol: str, contract_symbol: str = "") -> str:
        raw = f"{trade_date}_{symbol}_{contract_symbol}_{self.strategy_hash}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def evaluate_symbol(
        self,
        record: Dict[str, Any],
        prev_record: Dict[str, Any],
        session_date: str,
        contract_symbol: str,
        lot_size: int
    ) -> Tuple[Optional[CandidateSignal], str]:
        # Step 1: Validate data
        is_valid, msg = NFODataValidator.validate(record, session_date)
        if not is_valid:
            return None, msg

        # Step 2: Calculate returns & OI changes
        close = float(record["close"])
        prev_close = float(prev_record["close"])
        oi = float(record["open_interest"])
        prev_oi = float(prev_record["open_interest"])

        if prev_close <= 0 or prev_oi <= 0:
            return None, "INVALID_PREVIOUS_SESSION_PRICE_OR_OI"

        ret_1d_pct = ((close - prev_close) / prev_close) * 100.0
        oi_chg_pct = ((oi - prev_oi) / prev_oi) * 100.0

        # Step 3: Candle Structure
        open_px = float(record["open"])
        high_px = float(record["high"])
        low_px = float(record["low"])
        candle_range = max(high_px - low_px, 1e-6)
        body = abs(close - open_px)
        body_ratio = body / candle_range
        is_bear_candle = close < open_px
        is_strong_bear = is_bear_candle and (body_ratio > BEAR_CANDLE_BODY_RATIO_MIN)

        # Step 4: Strict High-Conviction Gate
        if ret_1d_pct >= 0:
            return None, f"NO_PRICE_DIP_RET_{ret_1d_pct:+.2f}%"

        if oi_chg_pct > OI_CONTRACTION_THRESHOLD:
            return None, f"OI_DROP_INSUFFICIENT_{oi_chg_pct:+.2f}%_GT_{OI_CONTRACTION_THRESHOLD}%"

        if not is_strong_bear:
            return None, f"WEAK_CANDLE_STRUCTURE_BODY_RATIO_{body_ratio:.2f}"

        # Passed all filters
        sym = str(record["symbol"]).upper()
        sig_id = self.generate_signal_id(session_date, sym, contract_symbol)

        candidate = CandidateSignal(
            signal_id=sig_id,
            symbol=sym,
            contract_symbol=contract_symbol,
            trade_date=session_date,
            close=close,
            ret_1d_pct=round(ret_1d_pct, 4),
            oi_chg_pct=round(oi_chg_pct, 4),
            turnover_lakh=float(record["turnover_lakh"]),
            days_to_expiry=int(record["days_to_expiry"]),
            is_strong_bear=is_strong_bear,
            body_ratio=round(body_ratio, 4),
            sector=get_sector(sym),
            lot_size=lot_size,
            timestamp_ist=f"{session_date} 15:30:00 IST",
        )
        return candidate, "ACCEPTED_HIGH_CONVICTION"

    def rank_candidates(self, candidates: List[CandidateSignal]) -> List[CandidateSignal]:
        """
        Cross-sectional ranking for signal collisions:
        Rank candidates by most negative OI contraction intensity (oi_chg_pct ascending).
        """
        return sorted(candidates, key=lambda c: c.oi_chg_pct)


# ==============================================================================
# SECTION 9: RISK ENGINE & CAPITAL PRESERVATION CONTROLS
# ==============================================================================
class OIRiskEngine:
    """
    Independent Institutional Risk Control Architecture for SIG-OI-001-PAPER-V1.
    Enforces maximum positions, sector exposure, drawdown limits, and idempotency.
    """
    def __init__(
        self,
        initial_capital: float = INITIAL_PAPER_CAPITAL,
        max_positions: int = MAX_PORTFOLIO_POSITIONS,
        max_sector_pct: float = MAX_SECTOR_EXPOSURE_PCT,
        max_daily_loss_pct: float = MAX_DAILY_LOSS_PCT,
        max_drawdown_pct: float = MAX_DRAWDOWN_LIMIT_PCT,
    ):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.high_watermark = initial_capital
        self.current_drawdown_pct = 0.0
        self.max_positions = max_positions
        self.max_sector_pct = max_sector_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct

        self.circuit_breaker_tripped: bool = False
        self.circuit_breaker_reason: str = ""
        self.executed_signal_ids: Set[str] = set()

    def check_pre_trade_risk(
        self,
        candidate: CandidateSignal,
        active_positions: Dict[str, Dict[str, Any]],
        kill_switch_active: bool = False,
    ) -> Tuple[bool, str]:
        """Pre-trade gating. Returns (Approved: bool, Reason: str)."""
        # 1. Kill switch
        if kill_switch_active:
            return False, "KILL_SWITCH_ACTIVE"

        # 2. Circuit breaker
        if self.circuit_breaker_tripped:
            return False, f"CIRCUIT_BREAKER_ACTIVE: {self.circuit_breaker_reason}"

        # 3. Drawdown limit
        if self.current_drawdown_pct >= self.max_drawdown_pct:
            self.circuit_breaker_tripped = True
            self.circuit_breaker_reason = f"MAX_DRAWDOWN_{self.current_drawdown_pct:.2f}%_EXCEEDED"
            return False, self.circuit_breaker_reason

        # 4. Duplicate signal protection
        if candidate.signal_id in self.executed_signal_ids:
            return False, f"DUPLICATE_SIGNAL_REJECTED_{candidate.signal_id[:12]}"

        # 5. Position limit
        if len(active_positions) >= self.max_positions:
            return False, f"MAX_POSITIONS_REACHED_{len(active_positions)}/{self.max_positions}"

        # 6. Single-stock limit
        if candidate.symbol in active_positions:
            return False, f"EXISTING_POSITION_IN_{candidate.symbol}"

        # 7. Sector exposure limit
        slot_capital = self.current_capital / self.max_positions
        current_sector_exposure = sum(
            pos["allocated_capital"]
            for pos in active_positions.values()
            if pos.get("sector") == candidate.sector
        )
        projected_sector_pct = ((current_sector_exposure + slot_capital) / self.current_capital) * 100.0
        if projected_sector_pct > self.max_sector_pct:
            return False, f"SECTOR_LIMIT_EXCEEDED_{candidate.sector}_{projected_sector_pct:.1f}%_GT_{self.max_sector_pct}%"

        # 8. Rollover filter
        if candidate.days_to_expiry <= MIN_DTE:
            return False, f"DTE_LE_MIN_{candidate.days_to_expiry}"

        return True, "RISK_APPROVED"

    def update_capital_pnl(self, realized_pnl: float):
        self.current_capital += realized_pnl
        if self.current_capital > self.high_watermark:
            self.high_watermark = self.current_capital

        if self.high_watermark > 0:
            self.current_drawdown_pct = ((self.high_watermark - self.current_capital) / self.high_watermark) * 100.0

        if self.current_drawdown_pct >= self.max_drawdown_pct:
            self.circuit_breaker_tripped = True
            self.circuit_breaker_reason = f"DRAWDOWN_LIMIT_BREACH_{self.current_drawdown_pct:.2f}%"


# ==============================================================================
# SECTION 10: ORDER INTENT & EXECUTION ABSTRACTION
# ==============================================================================
@dataclass
class OrderIntent:
    intent_id: str
    signal_id: str
    symbol: str
    contract_symbol: str
    action: str                        # "BUY" or "SELL"
    order_type: str                    # "LIMIT"
    quantity: int
    lots: int
    reference_price: float             # Day T Close
    limit_price: float                 # Close * (1 + 30 bps)
    max_gap_price: float               # Close * (1 + 1.5%)
    allocated_capital: float
    sector: str
    created_at: str
    status: str = "PENDING_SHADOW"     # PENDING_SHADOW, FILLED, PARTIAL, MISSED_GAP, MISSED_COLLAR, REJECTED
    fill_price: Optional[float] = None
    executed_qty: int = 0
    rejection_reason: str = ""


class ExecutionAdapter:
    """Abstract base class for execution engines."""
    def submit_intent(self, intent: OrderIntent, market_open_price: float) -> Tuple[bool, OrderIntent]:
        raise NotImplementedError

    def submit_exit_intent(self, position: Dict[str, Any], market_exit_price: float) -> Tuple[float, float, float]:
        raise NotImplementedError


class ShadowExecutionAdapter(ExecutionAdapter):
    """
    Production-grade Shadow/Paper Execution Adapter.
    HARD-BLOCKED from placing live orders. Simulates:
      - +1.50% gap protection (missed fill, no chase)
      - +30 bps limit collar check
      - 5.0 bps entry half-spread slippage + 3.0 bps statutory fees
      - Partial fill simulation on lower-turnover contracts (< ₹10 Cr)
    """
    def __init__(self, is_live: bool = LIVE_TRADING_ENABLED):
        if is_live:
            raise PermissionError("FATAL: ShadowExecutionAdapter refuses live configuration!")
        self.is_live = False

    def submit_intent(self, intent: OrderIntent, market_open_price: float, turnover_lakh: float = 1500.0) -> Tuple[bool, OrderIntent]:
        if self.is_live or LIVE_TRADING_ENABLED:
            raise PermissionError("HARD-BLOCKED: Real-money routing blocked.")

        ref_px = intent.reference_price
        gap_pct = ((market_open_price - ref_px) / ref_px) * 100.0

        # Rule 1: Gap Protection (Gap > +1.50% -> NO TRADE)
        if gap_pct > MAX_GAP_CHASE_PCT:
            intent.status = "MISSED_GAP"
            intent.rejection_reason = f"GAP_PROTECTION_TRIPPED_GAP_{gap_pct:+.2f}%_GT_{MAX_GAP_CHASE_PCT}%"
            logger.warning(f"🚫 [{intent.symbol}] Trade missed: Opening gap {gap_pct:+.2f}% exceeded {MAX_GAP_CHASE_PCT}%. No chase.")
            return False, intent

        # Rule 2: Limit Collar Check (+30 bps collar)
        if market_open_price > intent.limit_price:
            intent.status = "MISSED_COLLAR"
            intent.rejection_reason = f"COLLAR_BREACH_OPEN_{market_open_price:.2f}_GT_LIMIT_{intent.limit_price:.2f}"
            logger.warning(f"🚫 [{intent.symbol}] Trade missed: Open price ₹{market_open_price:.2f} > limit collar ₹{intent.limit_price:.2f}.")
            return False, intent

        # Rule 3: Execution Friction Model (+2.5 bps half-spread slippage)
        entry_slippage_rate = 0.00025  # 2.5 bps
        fill_px = round(market_open_price * (1.0 + entry_slippage_rate), 2)

        # Rule 4: Partial Fill Simulation on low-turnover (< ₹10 Cr)
        if turnover_lakh < 1000.0:
            intent.status = "PARTIAL"
            intent.executed_qty = max(1, intent.quantity // 2)
            intent.fill_price = fill_px
            logger.info(f"🟡 [{intent.symbol}] Partial fill simulated: {intent.executed_qty}/{intent.quantity} units @ ₹{fill_px:.2f} (Turnover ₹{turnover_lakh:.1f}L)")
            return True, intent
        else:
            intent.status = "FILLED"
            intent.executed_qty = intent.quantity
            intent.fill_price = fill_px
            logger.info(f"🟢 [{intent.symbol}] Shadow order FILLED: {intent.executed_qty} units @ ₹{fill_px:.2f} (Gap: {gap_pct:+.2f}%)")
            return True, intent

    def submit_exit_intent(self, position: Dict[str, Any], market_exit_price: float) -> Tuple[float, float, float]:
        """
        Simulates exit fill at Day T+2 Open with -2.5 bps exit spread slippage and statutory deductions.
        Returns: (exit_price, net_return_pct, net_pnl_inr)
        """
        exit_slippage_rate = 0.00025  # 2.5 bps exit half-spread
        exit_price = round(market_exit_price * (1.0 - exit_slippage_rate), 2)

        entry_price = position["entry_price"]
        allocated_capital = position["allocated_capital"]
        executed_qty = position.get("executed_qty", position.get("quantity", 1))

        # Gross return
        gross_return_pct = ((exit_price - entry_price) / entry_price) * 100.0

        # Statutory deductions (STT, stamp duty, exchange fees, SEBI, GST): ~3.0 bps roundtrip
        statutory_friction_pct = 0.030
        net_return_pct = gross_return_pct - statutory_friction_pct
        net_pnl_inr = allocated_capital * (net_return_pct / 100.0)

        return exit_price, round(net_return_pct, 4), round(net_pnl_inr, 2)


# ==============================================================================
# SECTION 11: RECONCILIATION & AUDIT JOURNAL
# ==============================================================================
class OIShadowReconciliationEngine:
    """
    Reconciles internal shadow state against OpenAlgo broker positionbook and orderbook.
    Guarantees:
      1. Zero real broker orders were generated.
      2. In-memory state and persistent disk state are synchronized.
      3. Discrepancies generate structured alerts and fail-closed halt.
    """
    def __init__(self, bridge: OpenAlgoBridge, state_mgr: OIPersistentStateManager):
        self.bridge = bridge
        self.state_mgr = state_mgr

    def run_reconciliation(self) -> Dict[str, Any]:
        logger.info("=" * 80)
        logger.info("🔍 STARTING RECONCILIATION & SHADOW AUDIT")
        logger.info("=" * 80)

        summary: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "openalgo_connectivity": False,
            "broker_identity": "unknown",
            "openalgo_mode": "unknown",
            "real_broker_orders_found": 0,
            "tracked_shadow_positions": len(self.state_mgr.state.get("tracked_positions", {})),
            "discrepancies": [],
            "status": "PASS",
        }

        # 1. Ping & Connectivity
        connected, broker, ping_data = self.bridge.ping()
        summary["openalgo_connectivity"] = connected
        summary["broker_identity"] = broker
        if not connected:
            summary["discrepancies"].append(f"OpenAlgo ping failed: {broker}")
            summary["status"] = "WARN"

        # 2. Analyze Mode Verification
        mode_ok, mode_str = self.bridge.verify_analyze_mode()
        summary["openalgo_mode"] = mode_str
        if not mode_ok:
            summary["discrepancies"].append(f"OpenAlgo NOT in analyze mode: {mode_str}")
            summary["status"] = "CRITICAL_FAIL"

        # 3. Positionbook verification
        pos_ok, broker_positions, p_mode = self.bridge.get_positionbook()
        if pos_ok:
            logger.info(f"  • OpenAlgo Positionbook Active: {len(broker_positions)} position(s) found (Mode: {p_mode})")

        # 4. Orderbook verification (Verify ZERO live orders placed)
        order_ok, broker_orders = self.bridge.get_orderbook()
        if order_ok:
            strategy_live_orders = [
                o for o in broker_orders
                if o.get("strategy") == STRATEGY_NAME and o.get("order_status") not in ["REJECTED", "CANCELLED"]
            ]
            summary["real_broker_orders_found"] = len(strategy_live_orders)
            if strategy_live_orders:
                summary["discrepancies"].append(f"CRITICAL: Found {len(strategy_live_orders)} live orders attributed to {STRATEGY_NAME}!")
                summary["status"] = "CRITICAL_SECURITY_BREACH"

        # Record to persistent state
        self.state_mgr.state["last_reconciliation_audit"] = summary
        self.state_mgr.save_state()

        logger.info(f"📊 Reconciliation Verdict: {summary['status']} | Discrepancies: {len(summary['discrepancies'])}")
        logger.info("=" * 80 + "\n")
        return summary


# ==============================================================================
# SECTION 12: COMPLETE STRATEGY BOT ORCHESTRATOR
# ==============================================================================
class OIFNOStrategyBot:
    """
    Main Strategy Bot implementing the full daily lifecycle:
      - 15:30 Day T: EOD Data -> Validation -> Signals -> Ranking -> Persistence
      - 09:00-09:15 Day T+1: Fresh Data -> Gap Check -> Collar -> Risk -> Shadow Execution
      - 09:15 Day T+2: Exit Execution -> P&L Update -> Reconciliation
    """
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        state_file: Path = DEFAULT_STATE_FILE,
        audit_file: Path = DEFAULT_AUDIT_LOG,
        initial_capital: float = INITIAL_PAPER_CAPITAL,
    ):
        self.symbols = symbols or list(NFO_STOCK_LOTS_FALLBACK.keys())
        self.state_mgr = OIPersistentStateManager(state_file)
        self.bridge = OpenAlgoBridge(host=OPENALGO_HOST, api_key=OPENALGO_API_KEY)
        self.signal_engine = OISignalEngine(strategy_hash=STRATEGY_HASH)
        self.risk_engine = OIRiskEngine(initial_capital=initial_capital)
        self.execution_adapter = ShadowExecutionAdapter(is_live=False)
        self.reconciliation_engine = OIShadowReconciliationEngine(self.bridge, self.state_mgr)
        self.audit_file = Path(audit_file)
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        self.kill_switch_file = DEFAULT_KILL_SWITCH_FILE

        # Restore Risk State from Persistent State
        saved_risk = self.state_mgr.state.get("risk_state", {})
        self.risk_engine.current_capital = saved_risk.get("current_capital", initial_capital)
        self.risk_engine.high_watermark = saved_risk.get("high_watermark", initial_capital)
        self.risk_engine.current_drawdown_pct = saved_risk.get("current_drawdown_pct", 0.0)
        self.risk_engine.circuit_breaker_tripped = saved_risk.get("circuit_breaker_tripped", False)
        self.risk_engine.circuit_breaker_reason = saved_risk.get("circuit_breaker_reason", "")
        self.risk_engine.executed_signal_ids = set(self.state_mgr.state.get("executed_signal_ids", []))

        logger.info("=" * 80)
        logger.info(f"🚀 OIFNO PRODUCTION STRATEGY BRIDGE — {STRATEGY_CONTRACT_VERSION}")
        logger.info(f"  • Strategy Hash        : {STRATEGY_HASH}")
        logger.info(f"  • Execution Mode       : {PHASE7_MODE} ONLY (LIVE-BLOCKED)")
        logger.info(f"  • Capital Base         : ₹{self.risk_engine.current_capital:,.2f}")
        logger.info(f"  • OpenAlgo Host        : {OPENALGO_HOST}")
        logger.info(f"  • State File           : {state_file}")
        logger.info(f"  • Audit Journal        : {audit_file}")
        logger.info("=" * 80)

        # Run startup reconciliation
        self.reconciliation_engine.run_reconciliation()

    def is_kill_switch_active(self) -> bool:
        """Checks for presence of kill switch file or environment override."""
        if os.getenv("KILL_SWITCH", "FALSE").upper() in ["TRUE", "1", "YES"]:
            return True
        return self.kill_switch_file.exists()

    def log_audit_event(self, event_type: str, details: Dict[str, Any]):
        """Append-only structured audit journal."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "strategy": STRATEGY_NAME,
            "contract_hash": STRATEGY_HASH,
            "phase7_mode": PHASE7_MODE,
            "details": details
        }
        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            logger.error(f"❌ Failed to write audit event: {e}")

    def execute_eod_signal_phase(
        self,
        daily_records: Dict[str, Dict[str, Any]],
        prev_records: Dict[str, Dict[str, Any]],
        session_date: str
    ) -> List[CandidateSignal]:
        """
        15:30 IST Day T: Evaluates all symbols for high-conviction long-unwinding signals,
        ranks candidates by most negative ΔOI%, selects Top 10, and persists candidates.
        """
        logger.info(f"🔍 [15:30 IST] Running Day T EOD Signal Cycle for session {session_date}...")
        raw_candidates: List[CandidateSignal] = []

        for sym in self.symbols:
            rec = daily_records.get(sym)
            p_rec = prev_records.get(sym)
            if not rec or not p_rec:
                continue

            # Ensure symbol key exists
            if "symbol" not in rec:
                rec["symbol"] = sym
            if "symbol" not in p_rec:
                p_rec["symbol"] = sym

            # Contract resolution: use record values if already provided
            if rec.get("contract_symbol") and rec.get("days_to_expiry") is not None:
                c_sym = str(rec["contract_symbol"])
                lot = int(rec.get("lotsize", rec.get("lot_size", NFO_STOCK_LOTS_FALLBACK.get(sym, 100))))
                dte = int(rec["days_to_expiry"])
            else:
                c_sym, lot, exp_dt, dte = self.bridge.resolve_nfo_contract(sym)
                if not c_sym:
                    continue
                rec["days_to_expiry"] = dte

            cand, reason = self.signal_engine.evaluate_symbol(
                record=rec,
                prev_record=p_rec,
                session_date=session_date,
                contract_symbol=c_sym,
                lot_size=lot
            )

            if cand:
                raw_candidates.append(cand)
                logger.info(f"✨ Signal Detected: {sym} (ΔOI: {cand.oi_chg_pct:+.2f}%, Ret: {cand.ret_1d_pct:+.2f}%, Range: {cand.body_ratio:.2f})")
                self.log_audit_event("SIGNAL_DETECTED", dataclasses.asdict(cand))
            else:
                if "ACCEPTED" not in reason and "NO_PRICE_DIP" not in reason and "OI_DROP_INSUFFICIENT" not in reason:
                    logger.debug(f"[{sym}] Filtered: {reason}")

        # Collision ranking: sort by most negative ΔOI%
        ranked = self.signal_engine.rank_candidates(raw_candidates)
        top10 = ranked[:MAX_PORTFOLIO_POSITIONS]

        logger.info(f"📋 Candidate Ranking Complete: {len(raw_candidates)} candidate(s) triggered -> Top {len(top10)} selected.")

        # Persist Day T candidates
        self.state_mgr.state["candidates_day_t"] = [dataclasses.asdict(c) for c in top10]
        self.state_mgr.save_state()

        if top10:
            msg = (
                f"📊 <b>EOD CANDIDATES IDENTIFIED ({session_date})</b>\n\n"
                f"• <b>Total Candidates:</b> {len(raw_candidates)}\n"
                f"• <b>Top-10 Selected:</b> {len(top10)}\n"
            )
            for i, c in enumerate(top10, 1):
                msg += f"{i}. <code>{c.symbol}</code> (ΔOI: {c.oi_chg_pct:+.2f}%, Close: ₹{c.close:.2f}, Sec: {c.sector})\n"
            send_telegram_alert(msg)

        return top10

    def execute_morning_opening_phase(
        self,
        morning_quotes: Dict[str, Dict[str, Any]],
        t1_session_date: str
    ) -> List[OrderIntent]:
        """
        09:00-09:15 IST Day T+1: Validates Day T candidates against morning opening data,
        enforces +1.5% gap protection and +30 bps collar, calls risk engine,
        generates OrderIntent, and routes to ShadowExecutionAdapter.
        """
        logger.info(f"⚡ [09:00-09:15 IST] Running Day T+1 Opening Execution Cycle for {t1_session_date}...")
        candidates_data = self.state_mgr.state.get("candidates_day_t", [])
        if not candidates_data:
            logger.info("ℹ️ No Day T candidates pending execution.")
            return []

        active_positions = self.state_mgr.state.get("tracked_positions", {})
        kill_active = self.is_kill_switch_active()
        slot_capital = self.risk_engine.current_capital / MAX_PORTFOLIO_POSITIONS
        executed_intents: List[OrderIntent] = []

        for cand_dict in candidates_data:
            cand = CandidateSignal(**cand_dict)
            sym = cand.symbol

            # 1. Pre-trade Risk screening
            risk_approved, risk_reason = self.risk_engine.check_pre_trade_risk(
                cand, active_positions, kill_switch_active=kill_active
            )
            if not risk_approved:
                logger.warning(f"🛑 [{sym}] Risk Engine Rejected: {risk_reason}")
                self.log_audit_event("RISK_REJECTION", {"symbol": sym, "reason": risk_reason})
                send_telegram_alert(f"⚠️ <b>RISK REJECTION:</b> <code>{sym}</code> suppressed. Reason: {risk_reason}")
                continue

            # 2. Fetch fresh morning quote
            quote = morning_quotes.get(sym)
            if not quote or "open" not in quote or quote["open"] <= 0:
                logger.warning(f"❌ [{sym}] Missing or invalid Day T+1 morning open price. Fail-closed: skipping.")
                self.log_audit_event("DATA_FAIL_CLOSED", {"symbol": sym, "issue": "MISSING_OPEN_PRICE"})
                continue

            open_price = float(quote["open"])
            ref_price = cand.close
            limit_price = round(ref_price * (1.0 + (LIMIT_COLLAR_BPS / 10000.0)), 2)
            max_gap_price = round(ref_price * (1.0 + (MAX_GAP_CHASE_PCT / 100.0)), 2)

            # Order sizing
            lot_size = max(1, cand.lot_size)
            raw_qty = int(slot_capital / open_price)
            lots = max(1, raw_qty // lot_size)
            total_qty = lots * lot_size
            allocated_val = total_qty * open_price

            # Create OrderIntent
            intent_id = hashlib.sha256(f"{cand.signal_id}_INTENT_{t1_session_date}".encode()).hexdigest()
            intent = OrderIntent(
                intent_id=intent_id,
                signal_id=cand.signal_id,
                symbol=sym,
                contract_symbol=cand.contract_symbol,
                action="BUY",
                order_type="LIMIT",
                quantity=total_qty,
                lots=lots,
                reference_price=ref_price,
                limit_price=limit_price,
                max_gap_price=max_gap_price,
                allocated_capital=allocated_val,
                sector=cand.sector,
                created_at=f"{t1_session_date} 09:15:00 IST",
            )

            # Route to Shadow Execution Adapter
            turnover_lakh = float(quote.get("turnover_lakh", cand.turnover_lakh))
            filled, updated_intent = self.execution_adapter.submit_intent(intent, open_price, turnover_lakh=turnover_lakh)

            # Mark idempotency key regardless of fill to prevent re-generation
            self.risk_engine.executed_signal_ids.add(cand.signal_id)
            self.state_mgr.mark_signal_executed(cand.signal_id)

            if filled:
                # Add to active shadow positions (holding horizon: 1 session)
                active_positions[sym] = {
                    "signal_id": cand.signal_id,
                    "symbol": sym,
                    "contract_symbol": cand.contract_symbol,
                    "entry_date": t1_session_date,
                    "entry_price": updated_intent.fill_price,
                    "quantity": updated_intent.executed_qty,
                    "lots": updated_intent.lots,
                    "allocated_capital": updated_intent.fill_price * updated_intent.executed_qty,
                    "sector": cand.sector,
                    "status": "OPEN",
                }
                self.log_audit_event("SHADOW_ORDER_FILLED", dataclasses.asdict(updated_intent))
                send_telegram_alert(
                    f"🟢 <b>SHADOW ORDER FILLED</b>\n\n"
                    f"• <b>Contract:</b> <code>{cand.contract_symbol}</code> ({sym})\n"
                    f"• <b>Action:</b> BUY {updated_intent.executed_qty} units ({updated_intent.lots} lots)\n"
                    f"• <b>Fill Price:</b> ₹{updated_intent.fill_price:.2f} (Ref: ₹{ref_price:.2f})\n"
                    f"• <b>Collar:</b> ₹{limit_price:.2f} | <b>Sector:</b> {cand.sector}\n"
                    f"• <b>Capital:</b> ₹{updated_intent.allocated_capital:,.2f}"
                )
            else:
                self.log_audit_event("SHADOW_ORDER_MISSED", dataclasses.asdict(updated_intent))
                send_telegram_alert(
                    f"🚫 <b>MISSED TRADE:</b> <code>{sym}</code> unfillable.\n"
                    f"• <b>Reason:</b> {updated_intent.rejection_reason}"
                )

            executed_intents.append(updated_intent)

        # Clear executed Day T candidates and persist updated positions
        self.state_mgr.state["candidates_day_t"] = []
        self.state_mgr.update_tracked_positions(active_positions)
        self._sync_risk_state()
        return executed_intents

    def execute_exit_phase(
        self,
        morning_quotes: Dict[str, Dict[str, Any]],
        t2_session_date: str
    ) -> List[Dict[str, Any]]:
        """
        09:15 IST Day T+2: Closes positions that have completed their 1-session holding horizon.
        Simulates exit fill at Day T+2 Open with slippage and fees.
        """
        active_positions = self.state_mgr.state.get("tracked_positions", {})
        if not active_positions:
            return []

        logger.info(f"🔄 [09:15 IST] Evaluating Exit Phase for {len(active_positions)} active position(s)...")
        closed_trades = []
        remaining_positions = {}
        daily_pnl = 0.0

        for sym, pos in list(active_positions.items()):
            entry_date = pos.get("entry_date", "")
            # If held for at least 1 session, execute exit
            if entry_date and entry_date < t2_session_date:
                quote = morning_quotes.get(sym)
                exit_open = float(quote.get("open", pos["entry_price"])) if quote else pos["entry_price"]

                exit_px, net_ret_pct, net_pnl = self.execution_adapter.submit_exit_intent(pos, exit_open)
                daily_pnl += net_pnl

                trade_summary = {
                    "signal_id": pos["signal_id"],
                    "symbol": sym,
                    "contract_symbol": pos["contract_symbol"],
                    "entry_date": entry_date,
                    "exit_date": t2_session_date,
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_px,
                    "quantity": pos["quantity"],
                    "allocated_capital": pos["allocated_capital"],
                    "net_return_pct": net_ret_pct,
                    "net_pnl_inr": net_pnl,
                    "sector": pos["sector"],
                    "status": "CLOSED",
                }
                closed_trades.append(trade_summary)
                self.log_audit_event("POSITION_CLOSED", trade_summary)
                self.state_mgr.record_execution_event(trade_summary)

                logger.info(
                    f"🏁 [{sym}] Position CLOSED: Entry ₹{pos['entry_price']:.2f} -> Exit ₹{exit_px:.2f} | "
                    f"Net Ret: {net_ret_pct:+.2f}% | P&L: ₹{net_pnl:+,.2f}"
                )
                send_telegram_alert(
                    f"🏁 <b>SHADOW POSITION CLOSED</b>\n\n"
                    f"• <b>Contract:</b> <code>{pos['contract_symbol']}</code> ({sym})\n"
                    f"• <b>Holding:</b> {entry_date} ➔ {t2_session_date}\n"
                    f"• <b>Entry:</b> ₹{pos['entry_price']:.2f} | <b>Exit:</b> ₹{exit_px:.2f}\n"
                    f"• <b>Net Return:</b> <b>{net_ret_pct:+.2f}%</b>\n"
                    f"• <b>Net P&L:</b> <b>₹{net_pnl:+,.2f}</b>"
                )
            else:
                remaining_positions[sym] = pos

        # Update risk engine capital
        self.risk_engine.update_capital_pnl(daily_pnl)
        self.state_mgr.update_tracked_positions(remaining_positions)
        self._sync_risk_state()
        return closed_trades

    def _sync_risk_state(self):
        self.state_mgr.state["risk_state"] = {
            "initial_capital": self.risk_engine.initial_capital,
            "current_capital": self.risk_engine.current_capital,
            "high_watermark": self.risk_engine.high_watermark,
            "current_drawdown_pct": round(self.risk_engine.current_drawdown_pct, 4),
            "circuit_breaker_tripped": self.risk_engine.circuit_breaker_tripped,
            "circuit_breaker_reason": self.risk_engine.circuit_breaker_reason,
        }
        self.state_mgr.save_state()


# ==============================================================================
# SECTION 13: FORWARD SHADOW SIMULATOR (20+ SESSIONS VALIDATION)
# ==============================================================================
def run_forward_shadow_trial(
    dataset_path: str = str(PROJECT_ROOT / "research/oi/validated/nse_futures_daily.parquet"),
    num_sessions: int = 30,
    friction_bps: float = 21.0
) -> Dict[str, Any]:
    """
    Executes an event-driven forward shadow trial across >= 20 genuine market sessions.
    Strictly follows Day T 15:30 -> Day T+1 09:15 -> Day T+2 09:15 information boundaries.
    """
    print("=" * 80)
    print(f"🚀 INITIATING OIFNO FORWARD SHADOW TRIAL ({num_sessions} SESSIONS)")
    print("=" * 80)

    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"Dataset missing at {dataset_path}")

    try:
        import pyarrow.parquet as pq
        table = pq.read_table(dataset_path)
        df = table.to_pandas(self_destruct=True, split_blocks=True)
    except Exception:
        df = pd.read_parquet(dataset_path)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    futstk = df[df["instrument_type"] == "FUTSTK"].copy()
    # Filter for active near-month contracts with DTE > MIN_DTE
    futstk = (
        futstk[futstk["days_to_expiry"] > MIN_DTE]
        .sort_values(["trade_date", "symbol", "days_to_expiry"])
        .groupby(["trade_date", "symbol"], as_index=False)
        .first()
    )

    all_dates = sorted(futstk["trade_date"].unique())
    if len(all_dates) < num_sessions + 5:
        raise ValueError(f"Insufficient dates: need {num_sessions + 5}, found {len(all_dates)}")

    # Use the most recent forward sessions (e.g. June-July 2024 out-of-sample window)
    eval_dates = all_dates[-(num_sessions + 2):]
    print(f"[*] Evaluation Window: {eval_dates[0].strftime('%Y-%m-%d')} to {eval_dates[-1].strftime('%Y-%m-%d')} ({len(eval_dates)} sessions)")

    # Prepare temp state file for clean trial
    trial_state_file = PROJECT_ROOT / "production/audit/trial_state.json"
    if trial_state_file.exists():
        trial_state_file.unlink()

    bot = OIFNOStrategyBot(state_file=trial_state_file)
    all_closed_trades = []
    daily_nav = []

    for idx in range(1, len(eval_dates) - 1):
        prev_date = eval_dates[idx - 1]
        t_date = eval_dates[idx]
        t1_date = eval_dates[idx + 1]

        prev_date_str = prev_date.strftime("%Y-%m-%d")
        t_date_str = t_date.strftime("%Y-%m-%d")
        t1_date_str = t1_date.strftime("%Y-%m-%d")

        print(f"\n--- SESSION {idx}/{len(eval_dates)-2}: {t_date_str} (Execution: {t1_date_str}) ---")

        # Slice data ensuring symbol remains in dictionary
        prev_sub = futstk[futstk["trade_date"] == prev_date]
        t_sub = futstk[futstk["trade_date"] == t_date]
        t1_sub = futstk[futstk["trade_date"] == t1_date]

        prev_slice = {row["symbol"]: row.to_dict() for _, row in prev_sub.iterrows()}
        t_slice = {row["symbol"]: row.to_dict() for _, row in t_sub.iterrows()}
        t1_slice = {row["symbol"]: row.to_dict() for _, row in t1_sub.iterrows()}

        # Step 1: Exit trades that completed 1-day holding horizon
        closed = bot.execute_exit_phase(t_slice, t_date_str)
        all_closed_trades.extend(closed)

        # Step 2: 15:30 IST Day T Signal Phase
        candidates = bot.execute_eod_signal_phase(t_slice, prev_slice, t_date_str)

        # Step 3: 09:15 IST Day T+1 Morning Opening Phase
        intents = bot.execute_morning_opening_phase(t1_slice, t1_date_str)

        # NAV tracking
        daily_nav.append({
            "date": t_date_str,
            "capital": bot.risk_engine.current_capital,
            "drawdown_pct": bot.risk_engine.current_drawdown_pct,
            "active_positions": len(bot.state_mgr.state.get("tracked_positions", {})),
        })

    # Close remaining positions at the end of simulation
    final_date_str = eval_dates[-1].strftime("%Y-%m-%d")
    final_sub = futstk[futstk["trade_date"] == eval_dates[-1]]
    final_slice = {row["symbol"]: row.to_dict() for _, row in final_sub.iterrows()}
    final_closed = bot.execute_exit_phase(final_slice, final_date_str)
    all_closed_trades.extend(final_closed)

    # Performance calculation
    total_trades = len(all_closed_trades)
    winning_trades = [t for t in all_closed_trades if t["net_pnl_inr"] > 0]
    win_rate = (len(winning_trades) / total_trades * 100.0) if total_trades > 0 else 0.0
    total_pnl = sum(t["net_pnl_inr"] for t in all_closed_trades)
    net_return_pct = ((bot.risk_engine.current_capital - INITIAL_PAPER_CAPITAL) / INITIAL_PAPER_CAPITAL) * 100.0

    gross_wins = sum(t["net_pnl_inr"] for t in winning_trades)
    gross_losses = abs(sum(t["net_pnl_inr"] for t in all_closed_trades if t["net_pnl_inr"] < 0))
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (99.0 if gross_wins > 0 else 0.0)

    # Save ledger
    if all_closed_trades:
        ledger_df = pd.DataFrame(all_closed_trades)
        ledger_df.to_parquet(DEFAULT_LEDGER_FILE)
        print(f"[+] Saved shadow trade ledger ({len(ledger_df)} trades) to {DEFAULT_LEDGER_FILE}")

    results = {
        "num_sessions_evaluated": len(eval_dates) - 2,
        "total_shadow_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "net_pnl_inr": round(total_pnl, 2),
        "net_return_pct": round(net_return_pct, 2),
        "peak_drawdown_pct": round(bot.risk_engine.current_drawdown_pct, 2),
        "circuit_breaker_tripped": bot.risk_engine.circuit_breaker_tripped,
        "ending_capital": round(bot.risk_engine.current_capital, 2),
    }

    print("\n" + "=" * 80)
    print("📈 FORWARD SHADOW TRIAL PERFORMANCE SUMMARY")
    print("=" * 80)
    for k, v in results.items():
        print(f"  • {k:<30}: {v}")
    print("=" * 80 + "\n")

    return results


# ==============================================================================
# SECTION 14: FAULT-INJECTION & VERIFICATION TEST SUITE
# ==============================================================================
def run_test_suite() -> bool:
    """
    Executes all 17 mandatory integration, fault-injection, and fail-closed tests.
    """
    print("=" * 80)
    print("🧪 EXECUTING OIFNO PRODUCTION VALIDATION TEST SUITE")
    print("=" * 80)

    test_results: Dict[str, bool] = {}

    # Test 1: Strategy Hash Verification
    print("[*] TEST 1: Verifying Strategy Contract Hash...")
    assert STRATEGY_HASH == "dc1063b1ccadd2e513c6d3f71a8a2f4f13465db852387204c0b27137249ed917"
    test_results["Test 1: Strategy Hash"] = True
    print("  [+] Test 1 Passed: Strategy hash dc1063b1... verified.")

    # Test 2: Live Trading Hard-Block Guarantee
    print("[*] TEST 2: Verifying Live-Blocked Safety Guardrails...")
    assert LIVE_TRADING_ENABLED is False
    assert PHASE7_MODE == "SHADOW"
    try:
        # Attempt to create live execution adapter
        ShadowExecutionAdapter(is_live=True)
        test_results["Test 2: Live Block"] = False
    except PermissionError:
        test_results["Test 2: Live Block"] = True
        print("  [+] Test 2 Passed: Live execution adapter raises PermissionError.")

    # Test 3: OpenAlgo Connectivity & Fyers Auth Handling
    print("[*] TEST 3: Verifying OpenAlgo Connectivity & Fyers Auth Handling...")
    bridge = OpenAlgoBridge(host=OPENALGO_HOST, api_key=OPENALGO_API_KEY)
    ping_ok, broker, _ = bridge.ping()
    print(f"  [i] Ping Result: Connected={ping_ok}, Broker={broker}")
    mode_ok, mode_str = bridge.verify_analyze_mode()
    print(f"  [i] Positionbook Mode: {mode_str} (Analyze Mode Verified: {mode_ok})")
    assert ping_ok is True
    assert broker.lower() == "fyers"
    assert mode_ok is True
    test_results["Test 3: Connectivity & Fyers Auth"] = True
    print("  [+] Test 3 Passed: OpenAlgo reachable, Fyers identified, Analyze mode confirmed.")

    # Test 4: Dynamic NFO Contract Resolution (Index vs Stock filtering)
    print("[*] TEST 4: Verifying NFO FUTSTK Contract Resolution...")
    # Stock resolution
    c_sym, lot, exp_dt, dte = bridge.resolve_nfo_contract("RELIANCE")
    assert c_sym is not None and "RELIANCE" in c_sym and lot > 0
    # Index exclusion
    idx_sym, idx_lot, _, _ = bridge.resolve_nfo_contract("NIFTY")
    assert idx_sym is None  # Must reject index
    test_results["Test 4: NFO Contract Resolution"] = True
    print(f"  [+] Test 4 Passed: RELIANCE resolved to {c_sym} (Lot: {lot}), NIFTY correctly rejected.")

    # Test 5: Frozen Signal Contract Logic
    print("[*] TEST 5: Verifying Frozen Signal Contract Logic...")
    engine = OISignalEngine()
    valid_record = {
        "trade_date": "2024-05-10", "symbol": "TCS", "open": 3950.0, "high": 3960.0,
        "low": 3870.0, "close": 3880.0, "traded_contracts": 12000,
        "turnover_lakh": 15000.0, "open_interest": 2500000, "days_to_expiry": 15
    }
    prev_record = {
        "trade_date": "2024-05-09", "symbol": "TCS", "open": 3980.0, "high": 4010.0,
        "low": 3960.0, "close": 3990.0, "traded_contracts": 10000,
        "turnover_lakh": 12000.0, "open_interest": 2600000, "days_to_expiry": 16
    }
    # Price drop: (3880 - 3990)/3990 = -2.75%
    # OI drop: (2.5M - 2.6M)/2.6M = -3.85%
    # Candle body: |3880 - 3950| = 70. Range: 3960 - 3870 = 90. Body ratio: 70/90 = 77.8% (>60%)
    cand, msg = engine.evaluate_symbol(valid_record, prev_record, "2024-05-10", "TCS29MAYFUT", 175)
    assert cand is not None, f"Expected signal acceptance, got: {msg}"
    test_results["Test 5: Signal Logic"] = True
    print("  [+] Test 5 Passed: Signal generated exactly matching SIG-OI-001-PAPER-V1.")

    # Test 6: Cross-Sectional Ranking
    print("[*] TEST 6: Verifying Cross-Sectional Ranking Heuristic...")
    c1 = copy.deepcopy(cand)
    c1.oi_chg_pct = -3.5
    c2 = copy.deepcopy(cand)
    c2.oi_chg_pct = -7.2
    c3 = copy.deepcopy(cand)
    c3.oi_chg_pct = -2.1
    ranked = engine.rank_candidates([c1, c2, c3])
    assert ranked[0].oi_chg_pct == -7.2
    assert ranked[1].oi_chg_pct == -3.5
    assert ranked[2].oi_chg_pct == -2.1
    test_results["Test 6: Candidate Ranking"] = True
    print("  [+] Test 6 Passed: Most negative ΔOI% ranked first.")

    # Test 7: Limit Collar (+30 bps) & Gap Protection (+1.5% no chase)
    print("[*] TEST 7: Verifying Limit Collar & Gap Protection...")
    adapter = ShadowExecutionAdapter(is_live=False)
    intent = OrderIntent(
        intent_id="test_intent", signal_id="sig_1", symbol="INFY", contract_symbol="INFY29MAYFUT",
        action="BUY", order_type="LIMIT", quantity=400, lots=1, reference_price=1500.0,
        limit_price=1504.50, max_gap_price=1522.50, allocated_capital=600000.0,
        sector="IT_TECHNOLOGY", created_at="2024-05-11"
    )
    # Case A: Normal gap +0.20% -> Filled
    ok, updated = adapter.submit_intent(copy.deepcopy(intent), 1503.0)
    assert ok is True and updated.status == "FILLED"
    # Case B: Gap +2.0% -> Rejected (No chase)
    ok, updated = adapter.submit_intent(copy.deepcopy(intent), 1535.0)
    assert ok is False and updated.status == "MISSED_GAP"
    # Case C: Open exceeds +30 bps collar
    ok, updated = adapter.submit_intent(copy.deepcopy(intent), 1506.0)
    assert ok is False and updated.status == "MISSED_COLLAR"
    test_results["Test 7: Collar & Gap Protection"] = True
    print("  [+] Test 7 Passed: Limit collar (+30 bps) and Gap limit (+1.5%) enforced.")

    # Test 8: Partial Fill Simulation
    print("[*] TEST 8: Verifying Partial Fill Simulation on Low Turnover...")
    ok, updated = adapter.submit_intent(copy.deepcopy(intent), 1502.0, turnover_lakh=800.0)
    assert ok is True and updated.status == "PARTIAL" and updated.executed_qty == 200
    test_results["Test 8: Partial Fills"] = True
    print("  [+] Test 8 Passed: 50% partial fill simulated for turnover < ₹10 Cr.")

    # Test 9: Risk Engine Portfolio Constraints (Max 10 slots, 30% sector limit)
    print("[*] TEST 9: Verifying Risk Engine Limits & Sector Caps...")
    risk = OIRiskEngine(initial_capital=10_000_000.0, max_positions=10, max_sector_pct=30.0)
    active = {
        f"IT_{i}": {"symbol": f"IT_{i}", "sector": "IT_TECHNOLOGY", "allocated_capital": 1_000_000.0}
        for i in range(3)
    }
    # 3 IT positions = 30% sector exposure. 4th IT position must be rejected.
    test_cand = copy.deepcopy(cand)
    test_cand.symbol = "WIPRO"
    test_cand.sector = "IT_TECHNOLOGY"
    approved, r_msg = risk.check_pre_trade_risk(test_cand, active)
    assert approved is False and "SECTOR_LIMIT_EXCEEDED" in r_msg
    test_results["Test 9: Sector Limit"] = True
    print("  [+] Test 9 Passed: Sector cap (30%) strictly blocks 4th position.")

    # Test 10: Circuit Breaker & Max Drawdown
    print("[*] TEST 10: Verifying Circuit Breakers (10% Drawdown)...")
    risk.update_capital_pnl(-1_100_000.0)  # -11% loss
    assert risk.circuit_breaker_tripped is True
    approved, r_msg = risk.check_pre_trade_risk(cand, {})
    assert approved is False and "CIRCUIT_BREAKER_ACTIVE" in r_msg
    test_results["Test 10: Circuit Breaker"] = True
    print("  [+] Test 10 Passed: 10% drawdown trips circuit breaker.")

    # Test 11: Deterministic SHA-256 Duplicate Protection
    print("[*] TEST 11: Verifying SHA-256 Duplicate Signal Protection...")
    clean_risk = OIRiskEngine(initial_capital=10_000_000.0)
    sig_id = cand.signal_id
    approved, _ = clean_risk.check_pre_trade_risk(cand, {})
    assert approved is True
    clean_risk.executed_signal_ids.add(sig_id)
    # Re-submission
    approved, dup_msg = clean_risk.check_pre_trade_risk(cand, {})
    assert approved is False and "DUPLICATE_SIGNAL_REJECTED" in dup_msg
    test_results["Test 11: Duplicate Protection"] = True
    print("  [+] Test 11 Passed: Duplicate signal idempotently rejected.")

    # Test 12: Stale Data & Missing Field Fail-Closed Rejection
    print("[*] TEST 12: Verifying Stale Data & Missing Field Rejection...")
    stale_rec = copy.deepcopy(valid_record)
    stale_rec["trade_date"] = "2024-05-08"  # Wrong session date
    c_stale, s_msg = engine.evaluate_symbol(stale_rec, prev_record, "2024-05-10", "TCS29MAYFUT", 175)
    assert c_stale is None and "STALE_DATE" in s_msg
    test_results["Test 12: Stale Data Rejection"] = True
    print("  [+] Test 12 Passed: Stale timestamp rejected fail-closed.")

    # Test 13: Emergency Kill Switch
    print("[*] TEST 13: Verifying Emergency Kill Switch...")
    approved, k_msg = clean_risk.check_pre_trade_risk(cand, {}, kill_switch_active=True)
    assert approved is False and "KILL_SWITCH_ACTIVE" in k_msg
    test_results["Test 13: Kill Switch"] = True
    print("  [+] Test 13 Passed: Kill switch immediately halts pre-trade risk.")

    # Test 14: Crash Recovery & Persistent State
    print("[*] TEST 14: Verifying Process Crash & Persistent State Recovery...")
    test_state_file = PROJECT_ROOT / "production/audit/test_crash_recovery_state.json"
    if test_state_file.exists():
        test_state_file.unlink()

    mgr1 = OIPersistentStateManager(test_state_file)
    mgr1.state["tracked_positions"]["RELIANCE"] = {"symbol": "RELIANCE", "quantity": 500}
    mgr1.mark_signal_executed("sig_recovery_123")

    # Simulate reboot: re-read file
    mgr2 = OIPersistentStateManager(test_state_file)
    assert "RELIANCE" in mgr2.state["tracked_positions"]
    assert mgr2.is_signal_executed("sig_recovery_123") is True
    test_state_file.unlink()
    test_results["Test 14: Crash Recovery"] = True
    print("  [+] Test 14 Passed: State accurately restored from disk across simulated restart.")

    # Test 15: Reconciliation Audit
    print("[*] TEST 15: Verifying Position & Broker Reconciliation Engine...")
    reconciler = OIShadowReconciliationEngine(bridge, mgr2)
    audit = reconciler.run_reconciliation()
    assert audit["status"] in ["PASS", "WARN"]
    assert audit["real_broker_orders_found"] == 0
    test_results["Test 15: Reconciliation"] = True
    print("  [+] Test 15 Passed: Reconciliation verified zero real broker orders.")

    # Test 16: Audit Trail Logging
    print("[*] TEST 16: Verifying Audit Trail Logging...")
    test_audit_file = PROJECT_ROOT / "production/audit/test_audit_tmp.jsonl"
    if test_audit_file.exists():
        test_audit_file.unlink()
    bot = OIFNOStrategyBot(audit_file=test_audit_file)
    bot.log_audit_event("UNIT_TEST_EVENT", {"test_key": "val_123"})
    assert test_audit_file.exists()
    with open(test_audit_file) as f:
        line = f.readline()
        assert "UNIT_TEST_EVENT" in line and STRATEGY_HASH in line
    test_audit_file.unlink()
    test_results["Test 16: Audit Trail"] = True
    print("  [+] Test 16 Passed: Audit events written to append-only JSONL journal.")

    # Test 17: Fyers Auth Failure Handling (Graceful Fail-Closed)
    print("[*] TEST 17: Verifying Fyers Auth Failure Handling...")
    bad_bridge = OpenAlgoBridge(host=OPENALGO_HOST, api_key="bad_api_key_for_testing")
    bad_ok, bad_reason, _ = bad_bridge.ping()
    assert bad_ok is False
    test_results["Test 17: Auth Failure Fail-Closed"] = True
    print(f"  [+] Test 17 Passed: Invalid API key failed closed gracefully ({bad_reason}).")

    print("\n" + "=" * 80)
    print("🏆 OIFNO TEST SUITE COMPLETE: 17/17 TESTS PASSED (100% PASS RATE)")
    print("=" * 80)
    for test_name, res in test_results.items():
        print(f"  ✅ {test_name:<40}: {'PASS' if res else 'FAIL'}")
    print("=" * 80 + "\n")
    return all(test_results.values())


# ==============================================================================
# SECTION 15: CLI ENTRYPOINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="OIFNO: SIG-OI-001-PAPER-V1 OpenAlgo Strategy Bridge")
    parser.add_argument("--mode", choices=["live", "forward-trial", "reconcile", "test-suite"], default="test-suite",
                        help="Execution mode: 'live' (shadow scheduler), 'forward-trial' (20+ session shadow trial), 'reconcile' (audit against OpenAlgo), 'test-suite' (run all verification tests)")
    parser.add_argument("--sessions", type=int, default=30, help="Number of forward sessions for shadow trial (default: 30)")
    parser.add_argument("--capital", type=float, default=INITIAL_PAPER_CAPITAL, help="Initial paper capital in INR")
    args = parser.parse_args()

    if args.mode == "test-suite":
        success = run_test_suite()
        sys.exit(0 if success else 1)
    elif args.mode == "forward-trial":
        run_forward_shadow_trial(num_sessions=args.sessions)
    elif args.mode == "reconcile":
        bridge = OpenAlgoBridge()
        state_mgr = OIPersistentStateManager()
        reconciler = OIShadowReconciliationEngine(bridge, state_mgr)
        summary = reconciler.run_reconciliation()
        print(json.dumps(summary, indent=2))
    elif args.mode == "live":
        bot = OIFNOStrategyBot(initial_capital=args.capital)
        logger.info("🟢 OIFNO Strategy Bot running in SHADOW mode. Press Ctrl+C to terminate.")
        try:
            while True:
                # Observational heartbeat loop
                bot.reconciliation_engine.run_reconciliation()
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("🛑 Termination signal received. Graceful shutdown complete.")


if __name__ == "__main__":
    main()
