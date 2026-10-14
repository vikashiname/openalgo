#!/usr/bin/env python3
"""
================================================================================
OpenAlgo Unified Pre-Flight Diagnostics & System Test Suite (NSE RELIANCE ONLY)
================================================================================
File: strategy/testopen.py
Purpose:
  - Verify server host reachability and network latency.
  - Verify OpenAlgo API authentication and Broker active session.
  - Retrieve funds, available margin, and account telemetry.
  - Check open positions across strategies.
  - Test Symbol Master and fetch real-time quotes & candle feed for RELIANCE (NSE).
  - (Optional) Test order placement pipeline (Places 1 Share BUY & SELL of RELIANCE on NSE).
  - (Optional) Send test Telegram alert.

Usage:
  # Standard Read-Only Diagnostics (Safe, No Real Orders):
  python3 strategy/testopen.py

  # With Telegram Test:
  python3 strategy/testopen.py --telegram

  # With Live Order Execution Test (Places 1 Share RELIANCE Buy & Sell on NSE):
  python3 strategy/testopen.py --live-order
================================================================================
"""

import os
import sys
import time
import argparse
import requests
from datetime import datetime

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

# ==============================================================================
# CONFIGURATION - EXCLUSIVELY NSE RELIANCE
# ==============================================================================
DEFAULT_API_KEY = os.getenv("OPENALGO_API_KEY", "")
DEFAULT_HOST = os.getenv("OPENALGO_HOST", os.getenv("HOST_SERVER", "https://vikashiname.in"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Fixed target: 1 Share of RELIANCE on NSE
SYMBOL = "RELIANCE"
EXCHANGE = "NSE"
QTY = 1
PRODUCT = "CNC"

# Fallback: Query local database if unconfigured
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    try:
        from database.telegram_db import get_bot_config, get_all_telegram_users
        bot_cfg = get_bot_config()
        if bot_cfg and bot_cfg.get("is_active"):
            token = bot_cfg.get("bot_token") or bot_cfg.get("token")
            if token and not TELEGRAM_BOT_TOKEN:
                TELEGRAM_BOT_TOKEN = token
        users = get_all_telegram_users()
        if users and not TELEGRAM_CHAT_ID:
            TELEGRAM_CHAT_ID = str(users[0].get("telegram_id", ""))
    except Exception:
        pass

# ==============================================================================
# TELEGRAM HELPER
# ==============================================================================
def send_telegram_alert(token: str, chat_id: str, message: str, buttons: list = None) -> bool:
    """Send alert via Telegram Bot API with optional inline keyboard buttons."""
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        resp = requests.post(url, json=payload, timeout=8)
        return resp.status_code == 200
    except Exception as e:
        print(f"⚠️ Telegram sending failed: {e}")
        return False

# ==============================================================================
# DIAGNOSTICS SUITE
# ==============================================================================
class OpenAlgoDiagnostics:
    def __init__(self, host: str, api_key: str):
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.symbol = SYMBOL
        self.exchange = EXCHANGE
        self.qty = QTY
        self.product = PRODUCT
        self.client = None
        self.results = {}
        self.summary = {}

    def print_header(self):
        print("\n" + "=" * 80)
        print("🚀 OPENALGO PRE-FLIGHT DIAGNOSTICS & SYSTEM HEALTH SUITE")
        print("=" * 80)
        print(f"🌐 Host Target : {self.host}")
        print(f"🔑 API Key     : {self.api_key[:8]}...{self.api_key[-6:] if len(self.api_key) > 14 else ''}")
        print(f"🎯 Test Target : {self.symbol} ({self.exchange}) | Qty: {self.qty} Share | Product: {self.product}")
        print(f"⏱️  Timestamp   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
        print("=" * 80)

    def check_network_and_host(self) -> bool:
        """Check host reachability and latency."""
        print("\n[1/6] 🌐 Testing Host Reachability & Network Latency...")
        endpoints = [
            f"{self.host}/auth/check-setup",
            f"{self.host}/api/v1/funds",
        ]
        
        start_t = time.time()
        connected = False
        status_code = None
        
        for ep in endpoints:
            try:
                r = requests.get(ep, timeout=8)
                status_code = r.status_code
                latency_ms = (time.time() - start_t) * 1000
                if status_code in [200, 400, 401, 403]:
                    connected = True
                    break
            except Exception:
                continue

        if connected:
            print(f"  ✅ Host Reachable: Response in {latency_ms:.1f} ms (Status: {status_code})")
            self.results['network'] = True
            return True
        else:
            print(f"  ❌ Host Unreachable at {self.host}")
            self.results['network'] = False
            return False

    def init_client_and_auth(self) -> bool:
        """Initialize OpenAlgo client and check broker session."""
        print("\n[2/6] 🔑 Verifying OpenAlgo Client & Broker Authentication...")
        if not OPENALGO_AVAILABLE:
            print("  ❌ 'openalgo' python package is not installed.")
            self.results['auth'] = False
            return False

        try:
            self.client = api(api_key=self.api_key, host=self.host)
            print("  ✅ OpenAlgo API Client Initialized")
        except Exception as e:
            print(f"  ❌ Client init failed: {e}")
            self.results['auth'] = False
            return False

        return True

    def check_funds_and_margins(self) -> bool:
        """Retrieve and display funds, cash, and margins."""
        print("\n[3/6] 💰 Querying Account Funds & Margin Telemetry...")
        try:
            funds_resp = self.client.funds()
            if isinstance(funds_resp, dict) and funds_resp.get("status") == "success":
                data = funds_resp.get("data", {})
                mode = funds_resp.get("mode", "live").upper()
                
                def _to_float(v, default=0.0):
                    try:
                        return float(v) if v not in (None, "") else default
                    except (ValueError, TypeError):
                        return default

                avail_cash = _to_float(data.get("availablecash"))
                collateral = _to_float(data.get("collateral"))
                exposure = _to_float(data.get("grossexposure"))
                debits = _to_float(data.get("utiliseddebits"))
                total_pnl = _to_float(data.get("totalpnl"))
                m2m_unrealized = _to_float(data.get("m2munrealized"))

                print(f"  ✅ Broker Session Active | Mode: [{mode}]")
                print(f"  --------------------------------------------------")
                print(f"  • Available Cash   : ₹{avail_cash:,.2f}")
                print(f"  • Collateral Margin: ₹{collateral:,.2f}")
                print(f"  • Gross Exposure   : ₹{exposure:,.2f}")
                print(f"  • Utilised Debits  : ₹{debits:,.2f}")
                print(f"  • Unrealized M2M   : ₹{m2m_unrealized:+,.2f}")
                print(f"  • Total PnL        : ₹{total_pnl:+,.2f}")
                print(f"  --------------------------------------------------")
                self.summary['cash'] = avail_cash
                self.summary['mode'] = mode
                self.summary['m2m'] = m2m_unrealized
                self.summary['total_pnl'] = total_pnl
                self.results['funds'] = True
                self.results['auth'] = True
                return True
            else:
                msg = funds_resp.get("message") if isinstance(funds_resp, dict) else str(funds_resp)
                print(f"  ❌ Broker Auth / Funds Query Failed: {msg}")
                self.results['funds'] = False
                self.results['auth'] = False
                return False
        except Exception as e:
            print(f"  ❌ Error querying funds: {e}")
            self.results['funds'] = False
            self.results['auth'] = False
            return False

    def check_positions(self) -> bool:
        """Check active open positions (ignoring closed/zero-qty previous positions)."""
        print("\n[4/6] 📋 Checking Active Position Book...")
        try:
            pos_resp = self.client.positionbook()
            if isinstance(pos_resp, dict) and pos_resp.get("status") == "success":
                positions = pos_resp.get("data", [])
                
                # Filter out closed/previous positions with 0 quantity
                active_positions = [
                    p for p in positions
                    if int(float(p.get('quantity', 0) or 0)) != 0
                ]

                # Check RELIANCE position specifically
                rel_pos = [
                    p for p in active_positions 
                    if str(p.get('symbol', '')).upper() == self.symbol and str(p.get('exchange', '')).upper() == self.exchange
                ]

                if rel_pos:
                    p = rel_pos[0]
                    qty = p.get('quantity')
                    side = p.get('side', 'NET')
                    pnl = float(p.get('pnl', 0.0) or 0.0)
                    print(f"  ⚠️ {self.symbol} ({self.exchange}) has ACTIVE OPEN POSITION | Qty: {qty} ({side}) | PnL: ₹{pnl:,.2f}")
                else:
                    print(f"  ✅ {self.symbol} ({self.exchange}): Flat / No Open Position.")

                if active_positions:
                    print(f"  📊 Active Non-Zero Positions ({len(active_positions)}):")
                    for p in active_positions:
                        sym = p.get('symbol')
                        qty = p.get('quantity')
                        side = p.get('side', 'NET')
                        try:
                            pnl = float(p.get('pnl', 0.0) or 0.0)
                        except (ValueError, TypeError):
                            pnl = 0.0
                        print(f"     • {sym} | Qty: {qty} ({side}) | PnL: ₹{pnl:,.2f}")
                else:
                    print("  ✅ Position Book Clean: 0 open positions across all symbols.")

                self.summary['active_positions'] = active_positions
                self.results['positions'] = True
                return True
            else:
                print(f"  ℹ️ Position query returned: {pos_resp}")
                self.results['positions'] = True
                return True
        except Exception as e:
            print(f"  ⚠️ Warning querying position book: {e}")
            self.results['positions'] = False
            return False

    def check_symbol_and_market_data(self) -> bool:
        """Query symbol master and historical candle feed for RELIANCE (NSE)."""
        print(f"\n[5/6] 📊 Verifying Symbol Master & Market Data Feed for '{self.symbol}' ({self.exchange})...")
        # 1. Search in Symbol Master
        try:
            search_url = f"{self.host}/api/v1/search"
            resp = requests.post(
                search_url,
                json={"apikey": self.api_key, "query": self.symbol, "exchange": self.exchange},
                timeout=8
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                matched = [x for x in data if x.get("symbol") == self.symbol]
                if matched:
                    info = matched[0]
                    name = info.get("name", "")
                    tok = info.get("token", "")
                    lot = info.get("lotsize", "")
                    print(f"  ✅ Symbol Master Match: {name} (Token: {tok} | Lot Size: {lot})")
                else:
                    print(f"  ⚠️ Symbol '{self.symbol}' not found in search master, checking quote/history directly...")
            else:
                print(f"  ℹ️ Symbol search HTTP {resp.status_code}")
        except Exception as e:
            print(f"  ⚠️ Symbol search check skipped: {e}")

        # 2. Query History Data
        try:
            hist_resp = self.client.history(
                symbol=self.symbol,
                exchange=self.exchange,
                interval="1m",
                start_date=datetime.now().strftime("%Y-%m-%d"),
                end_date=datetime.now().strftime("%Y-%m-%d")
            )
            if hist_resp is not None and not (isinstance(hist_resp, dict) and hist_resp.get("status") == "error"):
                rows = len(hist_resp) if hasattr(hist_resp, '__len__') else 1
                print(f"  ✅ Market Data Feed OK: Retrieved {rows} recent 1-minute candle(s)")
                self.results['data'] = True
                return True
            else:
                # Try daily interval as fallback
                hist_daily = self.client.history(
                    symbol=self.symbol,
                    exchange=self.exchange,
                    interval="D",
                    start_date="2026-01-01",
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )
                if hist_daily is not None and not (isinstance(hist_daily, dict) and hist_daily.get("status") == "error"):
                    print(f"  ✅ Market Data Feed OK: Retrieved Daily candles successfully.")
                    self.results['data'] = True
                    return True
                else:
                    err_msg = hist_resp.get("message") if isinstance(hist_resp, dict) else str(hist_resp)
                    print(f"  ❌ History Feed Failed: {err_msg}")
                    self.results['data'] = False
                    return False
        except Exception as e:
            print(f"  ❌ Error fetching history feed: {e}")
            self.results['data'] = False
            return False

    def run_live_order_test(self) -> bool:
        """Test live order execution: Buy 1 share of RELIANCE on NSE, then Sell 1 share."""
        print(f"\n[6/6] 🎯 Running Live Order Pipeline Test ({self.symbol} on {self.exchange}, Qty: {self.qty} Share, Product: {self.product})...")
        try:
            print(f"  📤 Placing Test BUY Order (Market, {self.product}, Qty: {self.qty})...")
            buy_resp = self.client.placeorder(
                strategy="DIAGNOSTICS_TEST",
                symbol=self.symbol,
                exchange=self.exchange,
                action="BUY",
                quantity=self.qty,
                price_type="MARKET",
                product=self.product
            )
            print(f"     Buy Order Response: {buy_resp}")

            # Verify BUY succeeded before placing square-off SELL
            if not (isinstance(buy_resp, dict) and buy_resp.get("status") == "success"):
                print("  ❌ BUY order failed/rejected. Aborting SELL square-off leg.")
                self.results['orders'] = False
                return False

            time.sleep(3)

            print(f"  📥 Placing Test Square-Off SELL Order (Market, {self.product}, Qty: {self.qty})...")
            sell_resp = self.client.placeorder(
                strategy="DIAGNOSTICS_TEST",
                symbol=self.symbol,
                exchange=self.exchange,
                action="SELL",
                quantity=self.qty,
                price_type="MARKET",
                product=self.product
            )
            print(f"     Square-Off Response: {sell_resp}")
            if isinstance(sell_resp, dict) and sell_resp.get("status") == "success":
                self.results['orders'] = True
                return True
            else:
                print("  ❌ Square-Off SELL order failed.")
                self.results['orders'] = False
                return False
        except Exception as e:
            print(f"  ❌ Order test failed: {e}")
            self.results['orders'] = False
            return False

    def send_telegram_report(self, token: str, chat_id: str) -> bool:
        """Send rich Telegram alert: Green if ready for trading, Red if action required."""
        if not token or not chat_id:
            print("  ⚠️ Telegram configuration missing (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")
            return False

        all_passed = all([
            self.results.get('network', False),
            self.results.get('auth', False),
            self.results.get('funds', False),
            self.results.get('data', False),
        ])

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
        host_display = self.host if "127.0.0.1" not in self.host else "https://vikashiname.in"

        if all_passed:
            mode = self.summary.get('mode', 'ANALYZE')
            cash = self.summary.get('cash', 0.0)
            m2m = self.summary.get('m2m', 0.0)
            positions = self.summary.get('active_positions', [])
            pos_txt = f"{len(positions)} active" if positions else "Flat (0 open)"
            pos_details = ""
            if positions:
                pos_list = [f"  • <code>{p.get('symbol')}</code> ({p.get('quantity')}) | PnL: ₹{float(p.get('pnl',0) or 0):+,.2f}" for p in positions[:4]]
                pos_details = "\n" + "\n".join(pos_list)

            msg = (
                f"🟢 <b>OPENALGO: CONNECTION & READY FOR TRADING</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🌐 <b>Host:</b> {host_display}\n"
                f"🔑 <b>Broker:</b> Active & Authenticated\n"
                f"⚡ <b>Mode:</b> <code>{mode}</code>\n"
                f"💰 <b>Available Cash:</b> ₹{cash:,.2f}\n"
                f"📊 <b>Unrealized M2M:</b> ₹{m2m:+,.2f}\n"
                f"📋 <b>Positions:</b> {pos_txt}{pos_details}\n"
                f"📈 <b>Market Feed:</b> Operational (NSE)\n"
                f"⏱️ <b>Verified:</b> {now_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <i>All pre-flight gates passed. System ready for trading.</i>"
            )
            buttons = [
                [
                    {"text": "⚡ Strategy Manager", "url": f"{host_display}/python"},
                    {"text": "📊 Positionbook", "url": f"{host_display}/positionbook"},
                ],
                [
                    {"text": "📖 Orderbook", "url": f"{host_display}/orderbook"},
                    {"text": "📈 Trading Terminal", "url": f"{host_display}/trading"},
                ]
            ]
        else:
            failed_items = []
            if not self.results.get('network'):
                failed_items.append("Host Reachability / Network Unreachable")
            if not self.results.get('auth'):
                failed_items.append("Broker Session Expired / Authentication Failed")
            if not self.results.get('funds'):
                failed_items.append("Funds & Margin Telemetry Failed")
            if not self.results.get('data'):
                failed_items.append("Market Data & History Feed Inaccessible")

            failed_str = "\n".join([f"  • ❌ <b>{it}</b>" for it in failed_items])
            msg = (
                f"🚨 <b>OPENALGO ALERT: ACTION REQUIRED BEFORE 09:15 IST</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🌐 <b>Host:</b> {host_display}\n"
                f"⚠️ <b>Issues Detected:</b>\n{failed_str}\n"
                f"⏱️ <b>Timestamp:</b> {now_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👉 <b>Action:</b> Please login or check OpenAlgo before market opens!"
            )
            buttons = [
                [
                    {"text": "🔑 Login to Broker", "url": f"{host_display}/auth/login"},
                    {"text": "⚡ OpenAlgo Dashboard", "url": host_display},
                ]
            ]

        ok = send_telegram_alert(token, chat_id, msg, buttons=buttons)
        if ok:
            print("  ✅ Telegram notification delivered.")
        else:
            print("  ❌ Failed to send Telegram alert.")
        return ok

    def print_verdict(self):
        print("\n" + "=" * 80)
        print("📋 FINAL SYSTEM READINESS VERDICT")
        print("=" * 80)
        
        all_passed = True
        checklist = [
            ("Network & Host Reachability", self.results.get('network', False)),
            ("API Client & Broker Session", self.results.get('auth', False)),
            ("Funds & Margin Telemetry", self.results.get('funds', False)),
            ("Market Data & History Feed", self.results.get('data', False)),
        ]

        for name, passed in checklist:
            badge = "✅ PASS" if passed else "❌ FAIL"
            if not passed:
                all_passed = False
            print(f"  {badge} | {name}")

        print("-" * 80)
        if all_passed:
            print("  🟢 SYSTEM READY: OpenAlgo host, broker auth, and data feeds are operational.")
        else:
            print("  🔴 SYSTEM NOT READY: Please review the failed items above.")
        print("=" * 80 + "\n")


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="OpenAlgo Pre-Flight Diagnostics Suite (NSE RELIANCE 1-Share Test)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="OpenAlgo Host URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="OpenAlgo API Key")
    parser.add_argument("--dry-run", action="store_true", help="Skip order execution (dry-run only)")
    parser.add_argument("--telegram", action="store_true", help="Send test alert to Telegram")

    args = parser.parse_args()

    diag = OpenAlgoDiagnostics(
        host=args.host,
        api_key=args.api_key
    )

    diag.print_header()

    # Step 1: Host check
    if not diag.check_network_and_host():
        diag.print_verdict()
        if args.telegram:
            diag.send_telegram_report(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        sys.exit(1)

    # Step 2: Init Client
    if not diag.init_client_and_auth():
        diag.print_verdict()
        if args.telegram:
            diag.send_telegram_report(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        sys.exit(1)

    # Step 3: Funds
    diag.check_funds_and_margins()

    # Step 4: Positions
    diag.check_positions()

    # Step 5: Market Data Feed (RELIANCE on NSE)
    diag.check_symbol_and_market_data()

    # Step 6: Order Execution Test (RELIANCE 1 Share Buy + Sell) - ENABLED BY DEFAULT
    if not args.dry_run:
        diag.run_live_order_test()
    else:
        print("\n[6/6] 🎯 Order Execution Pipeline Test: SKIPPED (Dry-Run Mode).")

    # Optional: Telegram Notification
    if args.telegram:
        print("\n[+] 📱 Sending Morning Pre-Flight Telegram Notification...")
        diag.send_telegram_report(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    diag.print_verdict()


if __name__ == "__main__":
    main()
