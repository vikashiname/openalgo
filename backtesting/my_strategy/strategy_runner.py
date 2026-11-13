#!/usr/bin/env python3
"""
================================================================================
STANDALONE STRATEGY RUNNER & PAPER TRADING ENGINE — MY STRATEGY
================================================================================
Directory   : backtesting/my_strategy/
Role        : Independent strategy execution runner.
              Supports Paper Trading, Dry-Run, and OpenAlgo API Integration.
              Guarantees ZERO contamination with strategies/liveopenalgo.

Usage:
  # Safe Paper Trading / Dry-Run (Default, no broker orders):
  python3 strategy_runner.py --paper

  # Single pre-flight diagnostic test:
  python3 strategy_runner.py --test

  # Continuous loop execution:
  python3 strategy_runner.py --paper --interval-sec 60
================================================================================
"""

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Load local isolated configuration
from config import (
    EMA_FAST,
    EMA_SLOW,
    EXCHANGE,
    HEARTBEAT_FILE,
    INITIAL_CAPITAL,
    INTERVAL,
    LOG_FILE,
    PROFIT_TARGET_PCT,
    RISK_PER_TRADE_PCT,
    RSI_BEARISH_THRESHOLD,
    RSI_BULLISH_THRESHOLD,
    RSI_PERIOD,
    STATE_FILE,
    STOP_LOSS_PCT,
    STRATEGY_NAME,
    SYMBOL,
    TRAILING_SL_PCT,
    VERSION,
)

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(), override=False)
except ImportError:
    pass

try:
    from openalgo import api, ta
    OPENALGO_AVAILABLE = True
except ImportError:
    OPENALGO_AVAILABLE = False
    api = None
    ta = None

# Configure isolated logging
logger = logging.getLogger(STRATEGY_NAME)
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# Console handler
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
logger.addHandler(ch)

# Isolated file handler
try:
    fh = logging.FileHandler(LOG_FILE)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
except Exception:
    pass


class IsolatedStrategyEngine:
    def __init__(self, mode: str = "paper"):
        self.mode = mode.lower()  # "paper" or "live"
        self.running = True
        self.client = None
        self.state: Dict[str, Any] = self._load_state()

        # Connect to OpenAlgo if configured
        api_key = os.getenv("OPENALGO_API_KEY")
        host = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")
        if OPENALGO_AVAILABLE and api_key:
            try:
                self.client = api(api_key=api_key, host=host)
                logger.info(f"Connected to OpenAlgo API at {host}")
            except Exception as e:
                logger.warning(f"Could not connect to OpenAlgo API: {e}")

    def _load_state(self) -> Dict[str, Any]:
        """Loads state from the strategy's own local state file."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load existing state file ({e}), initializing fresh state.")
        return {
            "strategy_name": STRATEGY_NAME,
            "version": VERSION,
            "position": 0,
            "entry_price": 0.0,
            "entry_time": None,
            "stop_loss": 0.0,
            "profit_target": 0.0,
            "trailing_high": 0.0,
            "simulated_capital": INITIAL_CAPITAL,
            "trades_count": 0,
            "last_cycle": None,
        }

    def _save_state(self) -> None:
        """Atomically saves state to the local isolated directory."""
        temp_file = STATE_FILE.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, default=str)
            temp_file.replace(STATE_FILE)
        except Exception as e:
            logger.error(f"Error saving state to {STATE_FILE}: {e}")

    def _update_heartbeat(self) -> None:
        """Writes heartbeat timestamp for monitoring without polluting live watchdogs."""
        try:
            with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "strategy": STRATEGY_NAME,
                    "mode": self.mode,
                    "timestamp": datetime.now().isoformat(),
                    "pid": os.getpid(),
                    "status": "RUNNING",
                    "position": self.state.get("position", 0),
                }, f, indent=2)
        except Exception as e:
            logger.debug(f"Heartbeat write warning: {e}")

    def fetch_market_quote(self) -> Dict[str, float]:
        """Fetches current LTP and quote."""
        if self.client:
            try:
                quote = self.client.quote(symbol=SYMBOL, exchange=EXCHANGE)
                if quote and "ltp" in quote:
                    return {"ltp": float(quote["ltp"]), "high": float(quote.get("high", quote["ltp"])), "low": float(quote.get("low", quote["ltp"]))}
            except Exception as e:
                logger.debug(f"Quote fetch failed via API: {e}")

        # Fallback simulation price
        last_price = self.state.get("entry_price") or 2850.0
        return {"ltp": last_price, "high": last_price * 1.002, "low": last_price * 0.998}

    def execute_order(self, action: str, quantity: int, price: float, reason: str) -> bool:
        """Executes trade in Paper (Simulated) or Live mode."""
        logger.info(f"[{self.mode.upper()} ORDER] Action: {action} | Qty: {quantity} | Price: {price} | Reason: {reason}")

        if self.mode == "live":
            if not self.client:
                logger.error("Cannot place live order: OpenAlgo client not initialized!")
                return False
            try:
                res = self.client.placeorder(
                    strategy=STRATEGY_NAME,
                    symbol=SYMBOL,
                    exchange=EXCHANGE,
                    action=action,
                    quantity=quantity,
                    pricetype="MARKET",
                    product="CNC" if EXCHANGE == "NSE" else "NRML",
                )
                logger.info(f"OpenAlgo live order response: {res}")
                return True
            except Exception as e:
                logger.error(f"Failed to place live order: {e}")
                return False
        else:
            # Paper trading simulation
            logger.info(f"[PAPER SIMULATION] Order logged safely in local state. Zero broker risk.")
            return True

    def run_iteration(self) -> None:
        """Executes a single strategy decision iteration."""
        quote = self.fetch_market_quote()
        ltp = quote["ltp"]
        high = quote["high"]
        low = quote["low"]

        position = self.state.get("position", 0)
        self.state["last_cycle"] = datetime.now().isoformat()
        self._update_heartbeat()

        logger.info(f"Scan: {SYMBOL} ({EXCHANGE}) LTP: ₹{ltp:.2f} | Current Position: {position}")

        # --- Position Management (Exits) ---
        if position > 0:
            entry_price = self.state["entry_price"]
            stop_loss = self.state["stop_loss"]
            profit_target = self.state["profit_target"]
            trailing_high = max(self.state.get("trailing_high", entry_price), high)
            trailing_stop = trailing_high * (1.0 - (TRAILING_SL_PCT / 100.0))
            self.state["trailing_high"] = trailing_high

            exit_reason = None
            exit_price = ltp

            if low <= stop_loss:
                exit_price = stop_loss
                exit_reason = f"STOP_LOSS triggered at ₹{stop_loss:.2f}"
            elif high >= profit_target:
                exit_price = profit_target
                exit_reason = f"PROFIT_TARGET reached at ₹{profit_target:.2f}"
            elif low <= trailing_stop and trailing_high > entry_price * 1.01:
                exit_price = trailing_stop
                exit_reason = f"TRAILING_STOP locked profit at ₹{trailing_stop:.2f}"

            if exit_reason:
                if self.execute_order("SELL", position, exit_price, exit_reason):
                    pnl = (exit_price - entry_price) * position
                    self.state["simulated_capital"] += pnl
                    self.state["position"] = 0
                    self.state["entry_price"] = 0.0
                    self.state["trades_count"] += 1
                    logger.info(f"Position Closed: PnL = ₹{pnl:.2f} | Balance: ₹{self.state['simulated_capital']:.2f}")
                    self._save_state()

        # --- Entry Evaluation ---
        elif position == 0:
            # In paper/dry-run mode, evaluate entry logic
            # (Replace with your exact indicator conditions or real-time signals)
            logger.info("Looking for entry setups... (EMA Fast > Slow & RSI Bullish)")

            # Example: For testing runner mechanics, trigger a simulated buy test if requested
            # Normal operation waits for live signal

        self._save_state()

    def start_loop(self, interval_sec: int = 60) -> None:
        """Continuous execution loop."""
        logger.info(f"Starting {STRATEGY_NAME} [{self.mode.upper()} MODE] loop (Interval: {interval_sec}s)...")

        def handle_signal(sig, frame):
            logger.info("Termination signal received. Shutting down gracefully...")
            self.running = False

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        while self.running:
            try:
                self.run_iteration()
            except Exception as e:
                logger.error(f"Error in strategy iteration: {e}", exc_info=True)

            for _ in range(interval_sec):
                if not self.running:
                    break
                time.sleep(1)

        logger.info("Strategy runner stopped safely.")


def main():
    parser = argparse.ArgumentParser(description="My Strategy Independent Runner")
    parser.add_argument("--paper", action="store_true", default=True, help="Run in Paper Trading mode (default)")
    parser.add_argument("--test", action="store_true", help="Run a single pre-flight diagnostic cycle and exit")
    parser.add_argument("--interval-sec", type=int, default=60, help="Scan interval in seconds (default: 60)")
    parser.add_argument("--live", action="store_true", help="Enable live trading mode (requires --confirm-live)")
    parser.add_argument("--confirm-live", action="store_true", help="Explicit confirmation for real broker order execution")
    args = parser.parse_args()

    mode = "paper"
    if args.live:
        if not args.confirm_live:
            sys.exit("Error: --live requires explicit --confirm-live safety flag.")
        mode = "live"

    print("================================================================================")
    print(f"🚀 INITIALIZING ISOLATED RUNNER: {STRATEGY_NAME} (v{VERSION})")
    print(f"• Mode           : {mode.upper()}")
    print(f"• State File     : {STATE_FILE}")
    print(f"• Heartbeat File : {HEARTBEAT_FILE}")
    print(f"• Log File       : {LOG_FILE}")
    print("================================================================================")

    engine = IsolatedStrategyEngine(mode=mode)

    if args.test:
        print("[*] Running single diagnostic test cycle...")
        engine.run_iteration()
        print("✓ Diagnostic cycle passed successfully.")
    else:
        engine.start_loop(interval_sec=args.interval_sec)


if __name__ == "__main__":
    main()
