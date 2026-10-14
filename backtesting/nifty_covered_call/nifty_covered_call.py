#!/usr/bin/env python3
"""
================================================================================
NIFTY Covered Call Live & Paper Trading Engine for OpenAlgo
Location: strategies/liveonopenalgo/nifty_covered_call.py
================================================================================
Strategy Specification:
  1. Underlying: NIFTY 50 Futures (NFO) / NIFTY ETF Proxy
  2. Short Call Option: Target ~0.30 Delta Call (CE) expiring in ~28 DTE
  3. Profit Target: 90% premium decay (target_pct = 0.90)
  4. Stop Loss: 3.0x initial premium multiplier (stoploss_mult = 3.0)
  5. Roll Threshold: When DTE <= 10 days, roll to next monthly contract
  6. Trend Filter: 100-EMA on underlying (Spot > 100 EMA for bullish qualification)
  7. Execution Modes:
     - ANALYZE (Paper Trading): Fills simulated at live broker bid/ask, tracks real M2M
     - LIVE: Places real orders through OpenAlgo REST API
  8. Persistence: Atomic crash-safe state recovery across process restarts
================================================================================
"""

import os
import sys
import time
import json
import signal
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import pytz
import numpy as np
import pandas as pd
from scipy.stats import norm

import requests

# Load environment configuration
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(), override=False)
except ImportError:
    pass

try:
    from openalgo import api
    OPENALGO_AVAILABLE = True
except ImportError:
    OPENALGO_AVAILABLE = False
    api = None

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S IST"
)
logger = logging.getLogger("NiftyCoveredCall")

# Paths & Directory Architecture
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_STATE_FILE = Path(os.getenv("STATE_FILE", SCRIPT_DIR / "nifty_covered_call_state.json"))
DEFAULT_LOG_FILE = Path(os.getenv("LOG_FILE", PROJECT_ROOT / "log/strategies/nifty_covered_call.log" if (PROJECT_ROOT / "log").exists() else SCRIPT_DIR / "nifty_covered_call.log"))

# Timezone
IST = pytz.timezone("Asia/Kolkata")

# Canonical Environment Config
OPENALGO_HOST = os.getenv("OPENALGO_HOST", os.getenv("HOST_SERVER", "http://127.0.0.1:5000")).rstrip("/")
OPENALGO_API_KEY = os.getenv("OPENALGO_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Fallback 1: Query OpenAlgo Host REST API if unconfigured
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
    except Exception as e:
        logger.debug(f"Could not load Telegram credentials from OpenAlgo API: {e}")

# Fallback 2: Check local database if available
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    try:
        from database.telegram_db import get_bot_config, get_all_telegram_users
        bot_cfg = get_bot_config()
        if bot_cfg and bot_cfg.get("is_active"):
            token = bot_cfg.get("bot_token") or bot_cfg.get("token")
            if token and token != "test_token_123456789" and not TELEGRAM_BOT_TOKEN:
                TELEGRAM_BOT_TOKEN = token
        users = get_all_telegram_users()
        if users and not TELEGRAM_CHAT_ID:
            TELEGRAM_CHAT_ID = str(users[0].get("telegram_id", ""))
    except Exception as e:
        logger.debug(f"Could not load Telegram credentials from database: {e}")


def get_current_ist() -> datetime:
    """Return current datetime in Indian Standard Time (IST)."""
    return datetime.now(IST)


def is_market_hours() -> bool:
    """Return True if current IST time is within NSE/NFO trading session (09:15 - 15:30 IST Mon-Fri)."""
    now = get_current_ist()
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


def calculate_bs_delta(spot: float, strike: float, dte: int, r: float = 0.07, sigma: float = 0.14) -> float:
    """Calculate Black-Scholes Call Delta."""
    if spot <= 0 or strike <= 0 or dte <= 0:
        return 0.50
    t = max(1, dte) / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    return float(norm.cdf(d1))


class NiftyCoveredCallEngine:
    def __init__(
        self,
        host: str = OPENALGO_HOST,
        api_key: str = OPENALGO_API_KEY,
        mode: str = "ANALYZE",
        delta: float = 0.30,
        target_pct: float = 0.90,
        stoploss_mult: float = 3.0,
        target_dte: int = 28,
        roll_dte: int = 10,
        lots: int = 1,
        trend_filter: bool = True,
        state_file: str = None,
    ):
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.mode = mode.upper()
        self.target_delta = delta
        self.target_pct = target_pct
        self.stoploss_mult = stoploss_mult
        self.target_dte = target_dte
        self.roll_dte = roll_dte
        self.lots = lots
        self.trend_filter = trend_filter
        self.state_file = Path(state_file) if state_file else DEFAULT_STATE_FILE
        self.running = True

        # OpenAlgo API Client
        self.client = None
        if OPENALGO_AVAILABLE and self.api_key:
            try:
                self.client = api(api_key=self.api_key, host=self.host)
                logger.info(f"[✓] OpenAlgo API client connected to {self.host}")
            except Exception as e:
                logger.warning(f"[!] Could not initialize OpenAlgo client: {e}")

        # Active Position State
        self.state = {
            "active_position": None,
            "total_realized_pnl": 0.0,
            "trade_history": [],
            "last_scan_ist": None,
        }
        self.load_state()

    def load_state(self):
        """Recover active position and trade ledger from state file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.state.update(data)
                active = self.state.get("active_position")
                if active:
                    logger.info(f"[✓] Restored ACTIVE COVERED CALL position: Long {active.get('fut_symbol')} | Short {active.get('call_symbol')}")
                else:
                    logger.info("[✓] State loaded: No active open position (FLAT).")
            except Exception as e:
                logger.error(f"[!] Failed to read state file {self.state_file}: {e}")

    def save_state(self):
        """Persist position state atomically."""
        try:
            tmp = self.state_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, default=str)
            os.replace(tmp, self.state_file)
        except Exception as e:
            logger.error(f"[!] Failed to persist state: {e}")

    def send_telegram(self, message: str, buttons: list = None):
        """Send notifications with optional inline action buttons."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return
        try:
            import requests
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if buttons:
                payload["reply_markup"] = {"inline_keyboard": buttons}
            else:
                # Default quick trade links for Covered Call
                payload["reply_markup"] = {
                    "inline_keyboard": [
                        [
                            {"text": "⚡ Strategy Manager", "url": "https://vikashiname.in/python"},
                            {"text": "📊 Positionbook", "url": "https://vikashiname.in/positionbook"},
                        ],
                        [
                            {"text": "📖 Orderbook", "url": "https://vikashiname.in/orderbook"},
                            {"text": "📈 Trading Terminal", "url": "https://vikashiname.in/trading"},
                        ],
                    ]
                }
            requests.post(url, json=payload, timeout=6)
        except Exception as e:
            logger.warning(f"[!] Telegram alert error: {e}")

    def get_near_futures_contract(self) -> dict:
        """Discover active near-month NIFTY Futures contract on NFO."""
        if not self.client:
            return {"symbol": "NIFTY27OCT26FUT", "lotsize": 65, "ltp": 22500.0}
        try:
            res = self.client.search(query="NIFTY", exchange="NFO")
            if isinstance(res, dict) and res.get("status") == "success":
                futs = [
                    x for x in res.get("data", [])
                    if x.get("instrumenttype") in ["FUTIDX", "futures", "FUT"]
                    and x.get("symbol", "").startswith("NIFTY")
                    and not any(x.get("symbol", "").startswith(p) for p in ["BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"])
                    and "FPI" not in x.get("symbol", "")
                ]
                if futs:
                    # Pick closest expiry future using proper datetime sorting
                    def _parse_fut_exp(x):
                        try:
                            return datetime.strptime(x.get("expiry", ""), "%d-%b-%y").date()
                        except Exception:
                            return datetime.max.date()

                    futs_sorted = sorted(futs, key=_parse_fut_exp)
                    target_fut = futs_sorted[0]
                    sym = target_fut.get("symbol")
                    q = self.client.quotes(exchange="NFO", symbol=sym)
                    ltp = q.get("data", {}).get("ltp", 0.0) if isinstance(q, dict) else 0.0
                    return {
                        "symbol": sym,
                        "lotsize": int(target_fut.get("lotsize", 65)),
                        "ltp": float(ltp),
                        "expiry": target_fut.get("expiry", "27-OCT-26"),
                    }
        except Exception as e:
            logger.warning(f"[!] Error fetching futures contract: {e}")

        return {"symbol": "NIFTY27OCT26FUT", "lotsize": 65, "ltp": 22500.0, "expiry": "27-OCT-26"}

    def check_trend_filter(self, spot: float) -> bool:
        """Check if Spot > 100-EMA on NIFTY."""
        if not self.trend_filter or not self.client:
            return True
        try:
            today_str = get_current_ist().strftime("%Y-%m-%d")
            start_str = (get_current_ist() - timedelta(days=200)).strftime("%Y-%m-%d")
            hist = self.client.history(symbol="NIFTY 50", exchange="NSE", interval="D", start_date=start_str, end_date=today_str)
            if hist and isinstance(hist, list) and len(hist) >= 50:
                closes = [float(c.get("close", 0)) for c in hist if "close" in c]
                ema_100 = pd.Series(closes).ewm(span=100, adjust=False).mean().iloc[-1]
                bullish = spot >= ema_100
                logger.info(f"[*] Trend Filter Check: Spot={spot:.2f} | 100-EMA={ema_100:.2f} | Bullish={bullish}")
                return bullish
        except Exception as e:
            logger.warning(f"[!] Trend filter evaluation fallback to True: {e}")
        return True

    def find_target_call_option(self, spot: float, target_expiry: str = None) -> dict:
        """Find the target ~0.30 Delta Call option on the monthly expiry."""
        if not self.client:
            return None
        try:
            now_date = get_current_ist().date()

            # Priority 1: Match the Monthly Futures Expiry (guarantees maximum liquidity)
            best_expiry_str = target_expiry
            best_dte = 15

            if not best_expiry_str:
                exp_resp = self.client.expiry(symbol="NIFTY", exchange="NFO", instrumenttype="options")
                if not isinstance(exp_resp, dict) or exp_resp.get("status") != "success":
                    return None

                valid_expiries = []
                for exp_str in exp_resp.get("data", []):
                    try:
                        exp_dt = datetime.strptime(exp_str, "%d-%b-%y").date()
                        dte = (exp_dt - now_date).days
                        if dte >= 7:
                            valid_expiries.append((abs(dte - self.target_dte), dte, exp_str))
                    except Exception:
                        continue

                if not valid_expiries:
                    return None

                valid_expiries.sort()
                best_diff, best_dte, best_expiry_str = valid_expiries[0]
            else:
                try:
                    exp_dt = datetime.strptime(best_expiry_str, "%d-%b-%y").date()
                    best_dte = (exp_dt - now_date).days
                except Exception:
                    best_dte = 15

            logger.info(f"[*] Selected Target Monthly Expiry: {best_expiry_str} (DTE: {best_dte} days)")

            # 2. Search CE options for this expiry using both possible prefixes:
            exp_date_obj = datetime.strptime(best_expiry_str, "%d-%b-%y")
            prefix_a = f"NIFTY{exp_date_obj.strftime('%d%b%y').upper()}"
            prefix_b = f"NIFTY{exp_date_obj.strftime('%y%b').upper()}"

            res = self.client.search(query=prefix_a, exchange="NFO")
            items = res.get("data", []) if isinstance(res, dict) and res.get("status") == "success" else []
            if not items:
                res = self.client.search(query=prefix_b, exchange="NFO")
                items = res.get("data", []) if isinstance(res, dict) and res.get("status") == "success" else []

            if not items:
                return None

            candidates = []
            for item in items:
                sym = item.get("symbol", "")
                if "CE" in sym and item.get("expiry") == best_expiry_str:
                    strike = float(item.get("strike", 0))
                    # Only strikes within +/- 8% of spot
                    if 0.95 * spot <= strike <= 1.10 * spot:
                        candidates.append((strike, sym, item))

            if not candidates:
                return None

            # 3. Calculate Black-Scholes Delta for candidates and find closest to target_delta
            best_delta_diff = float("inf")
            selected_option = None

            for strike, sym, item in candidates:
                d = calculate_bs_delta(spot, strike, best_dte)
                diff = abs(d - self.target_delta)
                if diff < best_delta_diff:
                    best_delta_diff = diff
                    q = self.client.quotes(exchange="NFO", symbol=sym)
                    ltp = float(q.get("data", {}).get("ltp", 0.0)) if isinstance(q, dict) else 0.0
                    selected_option = {
                        "symbol": sym,
                        "strike": strike,
                        "expiry": best_expiry_str,
                        "dte": best_dte,
                        "delta": d,
                        "ltp": ltp,
                        "lot_size": int(item.get("lotsize", 65)),
                    }

            return selected_option

        except Exception as e:
            logger.error(f"[!] Error discovering target call option: {e}", exc_info=True)
            return None

    def execute_entry(self, fut_info: dict, opt_info: dict):
        """Execute Covered Call Entry (Long Futures + Short Call)."""
        now_str = get_current_ist().strftime("%Y-%m-%d %H:%M:%S IST")
        fut_symbol = fut_info["symbol"]
        fut_price = fut_info["ltp"]
        fut_qty = fut_info["lotsize"] * self.lots

        opt_symbol = opt_info["symbol"]
        opt_price = opt_info["ltp"]
        opt_qty = opt_info["lot_size"] * self.lots

        logger.info(f"\n{'='*60}")
        logger.info(f"🟢 EXECUTING COVERED CALL ENTRY [{self.mode} MODE]")
        logger.info(f"  • Long Leg : BUY {fut_qty}x {fut_symbol} @ ₹{fut_price:,.2f}")
        logger.info(f"  • Short Leg: SELL {opt_qty}x {opt_symbol} @ ₹{opt_price:,.2f} (Delta: {opt_info['delta']:.2f})")
        logger.info(f"  • Target   : 90% decay -> Buy to Cover @ ₹{opt_price * (1.0 - self.target_pct):,.2f}")
        logger.info(f"  • StopLoss : {self.stoploss_mult:.1f}x premium -> Buy to Cover @ ₹{opt_price * self.stoploss_mult:,.2f}")
        logger.info(f"{'='*60}\n")

        if self.client:
            try:
                # Place Long Futures order (OpenAlgo routes to Sandbox DB in Analyze mode, or broker in Live mode)
                fut_order = self.client.placeorder(
                    strategy="NIFTY_COVERED_CALL",
                    symbol=fut_symbol,
                    exchange="NFO",
                    action="BUY",
                    quantity=fut_qty,
                    price_type="MARKET",
                    product="NRML",
                )
                logger.info(f"  [✓] Futures Order Response: {fut_order}")

                # Place Short Call order
                call_order = self.client.placeorder(
                    strategy="NIFTY_COVERED_CALL",
                    symbol=opt_symbol,
                    exchange="NFO",
                    action="SELL",
                    quantity=opt_qty,
                    price_type="MARKET",
                    product="NRML",
                )
                logger.info(f"  [✓] Short Call Order Response: {call_order}")
            except Exception as e:
                logger.error(f"[!] Order Placement Failed: {e}")
                if self.mode == "LIVE":
                    return

        # Record Active Position
        self.state["active_position"] = {
            "entry_time": now_str,
            "fut_symbol": fut_symbol,
            "fut_entry_price": fut_price,
            "fut_qty": fut_qty,
            "call_symbol": opt_symbol,
            "call_strike": opt_info["strike"],
            "call_expiry": opt_info["expiry"],
            "call_entry_price": opt_price,
            "call_qty": opt_qty,
            "call_delta": opt_info["delta"],
            "target_price": round(opt_price * (1.0 - self.target_pct), 2),
            "stoploss_price": round(opt_price * self.stoploss_mult, 2),
            "roll_dte": self.roll_dte,
            "mode": self.mode,
        }
        self.save_state()

        msg = (
            f"🟢 <b>NIFTY COVERED CALL — ENTRY</b>\n"
            f"Mode: <code>{self.mode}</code>\n"
            f"Futures: <b>BUY {fut_qty}x {fut_symbol}</b> @ ₹{fut_price:,.2f}\n"
            f"Short Call: <b>SELL {opt_qty}x {opt_symbol}</b> @ ₹{opt_price:,.2f}\n"
            f"Delta: {opt_info['delta']:.2f} | DTE: {opt_info['dte']} days\n"
            f"🎯 Profit Target: ₹{opt_price * (1.0 - self.target_pct):,.2f}\n"
            f"🛑 Stop Loss: ₹{opt_price * self.stoploss_mult:,.2f}\n"
            f"⏰ Time: {now_str}"
        )
        self.send_telegram(msg)

    def execute_exit(self, reason: str, curr_fut_price: float, curr_opt_price: float):
        """Execute Covered Call Exit / Roll."""
        pos = self.state.get("active_position")
        if not pos:
            return

        now_str = get_current_ist().strftime("%Y-%m-%d %H:%M:%S IST")
        fut_pnl = (curr_fut_price - pos["fut_entry_price"]) * pos["fut_qty"]
        opt_pnl = (pos["call_entry_price"] - curr_opt_price) * pos["call_qty"]
        total_pnl = fut_pnl + opt_pnl

        logger.info(f"\n{'='*60}")
        logger.info(f"🔴 CLOSING COVERED CALL POSITION [{reason}]")
        logger.info(f"  • Futures Exit Price : ₹{curr_fut_price:,.2f} | PnL: ₹{fut_pnl:+,.2f}")
        logger.info(f"  • Option Exit Price  : ₹{curr_opt_price:,.2f} | PnL: ₹{opt_pnl:+,.2f}")
        logger.info(f"  • Total Trade PnL    : ₹{total_pnl:+,.2f}")
        logger.info(f"{'='*60}\n")

        if self.client:
            try:
                # Close Long Futures
                self.client.placeorder(
                    strategy="NIFTY_COVERED_CALL",
                    symbol=pos["fut_symbol"],
                    exchange="NFO",
                    action="SELL",
                    quantity=pos["fut_qty"],
                    price_type="MARKET",
                    product="NRML",
                )
                # Buy to cover Short Call
                self.client.placeorder(
                    strategy="NIFTY_COVERED_CALL",
                    symbol=pos["call_symbol"],
                    exchange="NFO",
                    action="BUY",
                    quantity=pos["call_qty"],
                    price_type="MARKET",
                    product="NRML",
                )
            except Exception as e:
                logger.error(f"[!] Error sending closing orders: {e}")

        # Ledger Recording
        trade_record = {
            **pos,
            "exit_time": now_str,
            "exit_reason": reason,
            "fut_exit_price": curr_fut_price,
            "call_exit_price": curr_opt_price,
            "fut_pnl": fut_pnl,
            "opt_pnl": opt_pnl,
            "total_pnl": total_pnl,
        }
        self.state["trade_history"].append(trade_record)
        self.state["total_realized_pnl"] += total_pnl
        self.state["active_position"] = None
        self.save_state()

        msg = (
            f"🔴 <b>NIFTY COVERED CALL — CLOSED</b>\n"
            f"Reason: <b>{reason}</b> | Mode: <code>{self.mode}</code>\n"
            f"Futures PnL: ₹{fut_pnl:+,.2f}\n"
            f"Option PnL: ₹{opt_pnl:+,.2f}\n"
            f"<b>Total PnL: ₹{total_pnl:+,.2f}</b>\n"
            f"Cumulative Strategy PnL: ₹{self.state['total_realized_pnl']:+,.2f}\n"
            f"⏰ Time: {now_str}"
        )
        self.send_telegram(msg)

    def evaluate_cycle(self):
        """Single assessment cycle."""
        now = get_current_ist()
        self.state["last_scan_ist"] = now.strftime("%Y-%m-%d %H:%M:%S IST")

        # 1. Fetch live futures quote
        fut_info = self.get_near_futures_contract()
        spot = fut_info["ltp"]
        if spot <= 0:
            logger.warning("[!] Invalid spot/futures price received. Skipping cycle.")
            return

        pos = self.state.get("active_position")

        # 2. Morning Briefing Alert (dispatched once per day between 09:15 and 09:30 IST)
        today_date_str = now.strftime("%Y-%m-%d")
        if now.weekday() < 5 and (now.hour == 9 and 15 <= now.minute <= 30):
            if self.state.get("last_morning_alert_date") != today_date_str:
                self.state["last_morning_alert_date"] = today_date_str
                self.save_state()
                trend_ok = self.check_trend_filter(spot)
                status_txt = "Active Position Tracking" if pos else "Flat / Scanning for Entry"
                briefing_msg = (
                    f"🌅 <b>NIFTY COVERED CALL — MORNING BRIEFING</b>\n"
                    f"📅 Date: <code>{now.strftime('%d-%b-%Y')}</code> | Time: <code>{now.strftime('%H:%M:%S IST')}</code>\n"
                    f"⚡ Mode: <code>{self.mode}</code>\n"
                    f"📈 Nifty Futures: <b>₹{spot:,.2f}</b>\n"
                    f"🎯 Trend Filter: {'🟢 BULLISH (Spot > 100-EMA)' if trend_ok else '🔴 BEARISH (Spot < 100-EMA)'}\n"
                    f"📊 Strategy State: <b>{status_txt}</b>\n"
                )
                if pos:
                    briefing_msg += (
                        f"• Long: {pos['fut_qty']}x {pos['fut_symbol']} (Entry: ₹{pos['fut_entry_price']:,.2f})\n"
                        f"• Short: {pos['call_qty']}x {pos['call_symbol']} (Entry: ₹{pos['call_entry_price']:,.2f})\n"
                        f"• Profit Target: ₹{pos['target_price']:,.2f} | Stop Loss: ₹{pos['stoploss_price']:,.2f}\n"
                    )
                briefing_msg += "✅ AWS OpenAlgo Engine is RUNNING and monitoring market."
                self.send_telegram(briefing_msg)
        # Case A: An active position is open -> Monitor Exits / Rolls
        if pos:
            # Query current call price
            curr_call_price = pos["call_entry_price"]
            if self.client:
                q = self.client.quotes(exchange="NFO", symbol=pos["call_symbol"])
                if isinstance(q, dict) and q.get("status") == "success":
                    curr_call_price = float(q.get("data", {}).get("ltp", curr_call_price) or curr_call_price)

            # Check DTE remaining
            try:
                exp_dt = datetime.strptime(pos["call_expiry"], "%d-%b-%y").date()
                dte_left = (exp_dt - now.date()).days
            except Exception:
                dte_left = 15

            # Calculate Unrealized M2M
            fut_m2m = (spot - pos["fut_entry_price"]) * pos["fut_qty"]
            call_m2m = (pos["call_entry_price"] - curr_call_price) * pos["call_qty"]
            net_m2m = fut_m2m + call_m2m

            logger.info(
                f"[{now.strftime('%H:%M:%S IST')}] POSITION MONITORED | Long: {pos['fut_symbol']} @ ₹{spot:,.1f} | "
                f"Short: {pos['call_symbol']} @ ₹{curr_call_price:,.2f} (Entry: ₹{pos['call_entry_price']:.2f}) | "
                f"M2M: ₹{net_m2m:+,.2f} | DTE: {dte_left}d"
            )

            # Exit Condition 1: Profit Target (90% decay)
            if curr_call_price <= pos["target_price"]:
                self.execute_exit("PROFIT_TARGET_HIT (90% Decay)", spot, curr_call_price)
                return

            # Exit Condition 2: Stop Loss (3.0x initial premium)
            if curr_call_price >= pos["stoploss_price"]:
                self.execute_exit("STOP_LOSS_HIT (3.0x Premium)", spot, curr_call_price)
                return

            # Exit Condition 3: Roll Threshold (DTE <= roll_dte)
            if dte_left <= self.roll_dte:
                self.execute_exit(f"ROLL_THRESHOLD_REACHED (DTE <= {self.roll_dte})", spot, curr_call_price)
                return

        # Case B: No active position (FLAT) -> Check Entry Conditions
        else:
            if not is_market_hours():
                logger.info(f"[{now.strftime('%H:%M:%S IST')}] Market Closed. Engine idle waiting for next session.")
                return

            # Check trend filter
            if not self.check_trend_filter(spot):
                logger.info(f"[{now.strftime('%H:%M:%S IST')}] Trend filter bearish (Spot < 100-EMA). No entry initiated.")
                return

            # Discover ~0.30 Delta Call option on the monthly contract matching the futures
            opt_info = self.find_target_call_option(spot, target_expiry=fut_info.get("expiry"))
            if not opt_info or opt_info["ltp"] <= 1.0:
                logger.warning(f"[{now.strftime('%H:%M:%S IST')}] No suitable 0.30 Delta option found. Retrying next cycle.")
                return

            # Enter Position
            self.execute_entry(fut_info, opt_info)

    def run_loop(self, poll_interval: int = 30):
        """Continuous execution loop."""
        def _sig_handler(sig, frame):
            logger.info(f"\n[!] Signal {sig} received. Terminating Nifty Covered Call Engine cleanly...")
            self.running = False

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        logger.info("\n" + "=" * 70)
        logger.info("  🚀 NIFTY COVERED CALL — CONTINUOUS TRADING ENGINE STARTED")
        logger.info(f"  Mode             : {self.mode} (Paper / Real Execution)")
        logger.info(f"  Target Delta     : {self.target_delta:.2f} CE")
        logger.info(f"  Target DTE       : {self.target_dte} Days")
        logger.info(f"  Roll DTE         : {self.roll_dte} Days")
        logger.info(f"  Profit Target    : {self.target_pct*100:.0f}% decay")
        logger.info(f"  Stop Loss        : {self.stoploss_mult:.1f}x premium")
        logger.info(f"  Trend Filter     : {'Enabled (Spot > 100-EMA)' if self.trend_filter else 'Disabled'}")
        logger.info(f"  Poll Interval    : {poll_interval} Seconds")
        logger.info("=" * 70 + "\n")

        cycle_count = 0
        while self.running:
            cycle_count += 1
            try:
                self.evaluate_cycle()
            except Exception as e:
                logger.error(f"[!] Exception during cycle #{cycle_count}: {e}", exc_info=True)

            # Sleep with interrupt check
            for _ in range(poll_interval):
                if not self.running:
                    break
                time.sleep(1)

        logger.info(f"[{get_current_ist().strftime('%Y-%m-%d %H:%M:%S IST')}] Engine stopped.")


def parse_cli():
    parser = argparse.ArgumentParser(description="Nifty Covered Call Production Engine")
    parser.add_argument("--mode", type=str, default=os.getenv("TRADING_MODE", "ANALYZE"), choices=["ANALYZE", "LIVE"], help="Execution mode (ANALYZE / LIVE)")
    parser.add_argument("--delta", type=float, default=0.30, help="Target short call delta (default: 0.30)")
    parser.add_argument("--target", type=float, default=0.90, help="Profit target pct (default: 0.90 = 90%% decay)")
    parser.add_argument("--stoploss", type=float, default=3.0, help="Stop loss multiplier (default: 3.0 = 3x)")
    parser.add_argument("--roll-dte", type=int, default=10, help="Roll DTE threshold (default: 10)")
    parser.add_argument("--target-dte", type=int, default=28, help="Target initial DTE (default: 28)")
    parser.add_argument("--lots", type=int, default=1, help="Number of lots (default: 1)")
    parser.add_argument("--no-trend-filter", action="store_true", help="Disable 100-EMA trend filter")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between evaluation passes (default: 30)")
    parser.add_argument("--run-once", action="store_true", help="Run single evaluation cycle and exit immediately")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_cli()
    engine = NiftyCoveredCallEngine(
        mode=args.mode,
        delta=args.delta,
        target_pct=args.target,
        stoploss_mult=args.stoploss,
        target_dte=args.target_dte,
        roll_dte=args.roll_dte,
        lots=args.lots,
        trend_filter=not args.no_trend_filter,
    )
    if args.run_once:
        logger.info("[*] Running single evaluation cycle (--run-once)...")
        engine.evaluate_cycle()
    else:
        engine.run_loop(poll_interval=args.poll_interval)
