"""
================================================================================
MCX EMA Crossover Strategy & Backtesting Engine (emabacktestmcx.py)
================================================================================
Features:
  - Live & Paper Trading via OpenAlgo API (Standardized RMS Reversals)
  - Auto-detection of Active MCX Near-Month Contracts & Lot Sizes
  - Multi-Asset MCX Futures Backtesting with Realistic Indian Statutory Friction
    (Brokerage, CTT, Exchange Txn, GST, Stamp Duty, and Slippage)
  - Lookahead-Free Backtest Execution (Signal on Bar Close -> Fill on Next Bar)
  - Accurate Currency & Unit Pricing (COMEX to MCX INR Conversion with Duty)
  - Native Integration with OpenAlgo Modular Backtesting Framework
    (TradeLogManager, EquityCurveTracker, PortfolioAnalytics, DetailedConsoleReporter)
================================================================================
"""

import argparse
import math
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from dotenv import find_dotenv, load_dotenv

# Load environment variables from root .env without overriding existing shell env
load_dotenv(find_dotenv(), override=False)

# Optional Imports
try:
    from openalgo import api, ta
except ImportError:
    api = None
    ta = None

try:
    import talib as tl
except ImportError:
    tl = None

try:
    import yfinance as yf
except ImportError:
    yf = None

# Native OpenAlgo Backtesting Framework Imports
try:
    from backtesting.analytics.portfolio_analytics import PortfolioAnalytics
    from backtesting.analytics.reporter import DetailedConsoleReporter
    from backtesting.analytics.trade_analytics import TradeAnalytics
    from backtesting.models.trade import Trade, TradeLogManager
    from backtesting.portfolio.equity import EquityCurveTracker
except ImportError:
    # If run standalone, try relative path import
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from backtesting.analytics.portfolio_analytics import PortfolioAnalytics
        from backtesting.analytics.reporter import DetailedConsoleReporter
        from backtesting.analytics.trade_analytics import TradeAnalytics
        from backtesting.models.trade import Trade, TradeLogManager
        from backtesting.portfolio.equity import EquityCurveTracker
    except ImportError:
        Trade = None
        TradeLogManager = None
        EquityCurveTracker = None
        TradeAnalytics = None
        PortfolioAnalytics = None
        DetailedConsoleReporter = None

# ==============================================================================
# DEFAULT CONFIGURATION
# ==============================================================================
OPENALGO_API_KEY = os.getenv("OPENALGO_API_KEY", "")
OPENALGO_HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

BASE_SYMBOL = os.getenv("BASE_SYMBOL", "CRUDEOIL").upper()
EXCHANGE = os.getenv("EXCHANGE", "MCX").upper()
INTERVAL = os.getenv("INTERVAL", "5m")
PRODUCT = os.getenv("PRODUCT", "NRML").upper()  # NRML or MIS
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "MCX_EMA_CROSS")

FAST_EMA = int(os.getenv("FAST_EMA", "9"))
SLOW_EMA = int(os.getenv("SLOW_EMA", "21"))
LOTS = int(os.getenv("LOTS", os.getenv("QTY", "1")))
TRADE_DIRECTION = os.getenv("TRADE_DIRECTION", "BOTH").upper()  # BOTH, BUY_ONLY, SELL_ONLY
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() in ["true", "1", "yes"]
PAPER_MODE = os.getenv("PAPER_MODE", "false").lower() in ["true", "1", "yes"]

# ==============================================================================
# MCX COMMODITY SPECIFICATIONS & CONVERSION MAPPINGS
# ==============================================================================
# Point Value = INR P&L for a 1.0 point price change per lot.
# Tick Size = Minimum price variation on MCX.
# Expiry Day = Typical expiry day of the month for contract resolution fallback.
MCX_COMMODITY_SPECS = {
    "CRUDEOIL": {
        "yf_symbol": "CL=F",
        "default_lot": 100,
        "unit": "Barrels",
        "tick": 1.0,
        "point_value": 100.0,
        "expiry_day": 19,
        "conv_type": "barrel",
    },
    "CRUDEOILM": {
        "yf_symbol": "CL=F",
        "default_lot": 10,
        "unit": "Barrels",
        "tick": 1.0,
        "point_value": 10.0,
        "expiry_day": 19,
        "conv_type": "barrel",
    },
    "GOLD": {
        "yf_symbol": "GC=F",
        "default_lot": 1,
        "unit": "1kg (quoted per 10g)",
        "tick": 1.0,
        "point_value": 100.0,  # 100 units of 10g in 1kg lot
        "expiry_day": 5,
        "conv_type": "gold_10g",
    },
    "GOLDM": {
        "yf_symbol": "GC=F",
        "default_lot": 1,
        "unit": "100g (quoted per 10g)",
        "tick": 1.0,
        "point_value": 10.0,  # 10 units of 10g in 100g lot
        "expiry_day": 5,
        "conv_type": "gold_10g",
    },
    "GOLDTEN": {
        "yf_symbol": "GC=F",
        "default_lot": 1,
        "unit": "10g",
        "tick": 1.0,
        "point_value": 1.0,
        "expiry_day": 5,
        "conv_type": "gold_10g",
    },
    "SILVER": {
        "yf_symbol": "SI=F",
        "default_lot": 30,
        "unit": "Kg",
        "tick": 1.0,
        "point_value": 30.0,  # 30 kg lot, quoted per 1kg
        "expiry_day": 5,
        "conv_type": "silver_1kg",
    },
    "SILVERM": {
        "yf_symbol": "SI=F",
        "default_lot": 5,
        "unit": "Kg",
        "tick": 1.0,
        "point_value": 5.0,  # 5 kg lot, quoted per 1kg
        "expiry_day": 5,
        "conv_type": "silver_1kg",
    },
    "NATURALGAS": {
        "yf_symbol": "NG=F",
        "default_lot": 1250,
        "unit": "mmBtu",
        "tick": 0.10,
        "point_value": 1250.0,  # 1250 mmBtu, quoted per mmBtu
        "expiry_day": 25,
        "conv_type": "mmbtu",
    },
    "COPPER": {
        "yf_symbol": "HG=F",
        "default_lot": 2500,
        "unit": "Kg",
        "tick": 0.05,
        "point_value": 2500.0,  # 2500 kg, quoted per 1kg
        "expiry_day": 30,
        "conv_type": "copper_1kg",
    },
    "ZINC": {
        "yf_symbol": "ZN=F",
        "default_lot": 5000,
        "unit": "Kg",
        "tick": 0.05,
        "point_value": 5000.0,
        "expiry_day": 30,
        "conv_type": "zinc_1kg",
    },
}


# ==============================================================================
# TECHNICAL INDICATORS & SIGNAL HELPERS
# ==============================================================================
def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average using openalgo.ta, TA-Lib, or pandas."""
    if ta is not None and hasattr(ta, "ema"):
        try:
            res = ta.ema(series, period)
            if isinstance(res, pd.Series):
                return res
            return pd.Series(res, index=series.index)
        except Exception:
            pass

    if tl is not None and hasattr(tl, "EMA"):
        try:
            res = tl.EMA(series.values.astype(np.float64), timeperiod=period)
            return pd.Series(res, index=series.index)
        except Exception:
            pass

    return series.ewm(span=period, adjust=False).mean()


def apply_exrem(entries: pd.Series, exits: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """Removes redundant consecutive signals using openalgo.ta.exrem or fallback."""
    if ta is not None and hasattr(ta, "exrem"):
        try:
            clean_entries = pd.Series(
                ta.exrem(entries.fillna(False), exits.fillna(False)),
                index=entries.index,
                dtype=bool,
            )
            clean_exits = pd.Series(
                ta.exrem(exits.fillna(False), entries.fillna(False)),
                index=exits.index,
                dtype=bool,
            )
            return clean_entries, clean_exits
        except Exception:
            pass

    # High-performance inline state-machine fallback
    clean_ent = pd.Series(False, index=entries.index)
    clean_ex = pd.Series(False, index=exits.index)
    state = 0  # 1: long active, -1: short active, 0: neutral

    for i in range(len(entries)):
        is_ent = bool(entries.iloc[i])
        is_ex = bool(exits.iloc[i])
        if is_ent and state <= 0:
            clean_ent.iloc[i] = True
            state = 1
        elif is_ex and state >= 0:
            clean_ex.iloc[i] = True
            state = -1

    return clean_ent, clean_ex


# ==============================================================================
# COMEX TO MCX CONVERSION (Real-world Pricing Alignment)
# ==============================================================================
def convert_comex_to_mcx(
    df: pd.DataFrame, conv_type: str, usdinr: float = 84.0
) -> pd.DataFrame:
    """
    Converts COMEX/NYMEX USD futures price data into realistic MCX INR price levels.
    Includes unit conversions (Troy Oz -> 10g/1kg, Lbs -> Kg) and statutory import duties.
    """
    out = df.copy()
    cols = [c for c in ["Open", "High", "Low", "Close", "open", "high", "low", "close"] if c in out.columns]

    # Gold: COMEX is USD per Troy Ounce (31.1034768g). MCX is INR per 10g (+ ~10% import duty/cess)
    if conv_type == "gold_10g":
        factor = (10.0 / 31.1034768) * usdinr * 1.10
    # Silver: COMEX is USD per Troy Ounce. MCX is INR per 1kg (1000g) (+ ~10% import duty/cess)
    elif conv_type == "silver_1kg":
        factor = (1000.0 / 31.1034768) * usdinr * 1.10
    # Copper: COMEX is USD per Pound (lb). 1 Kg = 2.20462 lbs. MCX is INR per 1kg.
    elif conv_type == "copper_1kg":
        factor = 2.20462 * usdinr
    # Zinc: COMEX is USD per Pound.
    elif conv_type == "zinc_1kg":
        factor = 2.20462 * usdinr
    # Crude Oil & Natural Gas: Units are 1:1 (Barrel & mmBtu). MCX is INR per barrel/mmBtu.
    elif conv_type in ["barrel", "mmbtu"]:
        factor = usdinr
    else:
        factor = usdinr

    for col in cols:
        out[col] = out[col] * factor

    return out


# ==============================================================================
# CONTRACT & LOT SIZE RESOLUTION
# ==============================================================================
def resolve_mcx_contract(
    base_symbol: str, host: str, api_key: str, exchange: str = "MCX"
) -> Tuple[str, int]:
    """
    Queries OpenAlgo master search API to discover the active near-month
    futures contract symbol and its verified lot size.
    """
    spec = MCX_COMMODITY_SPECS.get(base_symbol, {"default_lot": 1, "expiry_day": 20})
    fallback_lot = spec.get("default_lot", 1)
    fallback_day = spec.get("expiry_day", 20)

    try:
        search_url = f"{host.rstrip('/')}/api/v1/search"
        resp = requests.post(
            search_url,
            json={"apikey": api_key, "query": base_symbol, "exchange": exchange},
            timeout=8,
        )
        if resp.status_code == 200:
            items = resp.json().get("data", [])
            fut_items = [
                i for i in items
                if i.get("instrumenttype") == "FUT"
                and i.get("symbol", "").startswith(base_symbol)
            ]

            # Avoid matching MINI contracts when trading regular contract
            if not base_symbol.endswith("M"):
                fut_items = [
                    i for i in fut_items
                    if not i.get("symbol", "").startswith(f"{base_symbol}M")
                ]

            now = datetime.now()
            valid = []
            for item in fut_items:
                exp_str = item.get("expiry")
                if exp_str:
                    try:
                        exp_dt = pd.to_datetime(exp_str, errors="coerce")
                        if pd.notna(exp_dt):
                            exp_dt = exp_dt.to_pydatetime().replace(hour=23, minute=59)
                            if exp_dt >= now:
                                lot = int(item.get("lotsize", fallback_lot))
                                valid.append((exp_dt, item.get("symbol"), lot))
                    except Exception:
                        pass

            if valid:
                valid.sort(key=lambda x: x[0])
                contract_symbol = valid[0][1]
                lot_size = valid[0][2]
                return contract_symbol, lot_size

    except Exception as e:
        print(f"[WARN] Search API lookup failed ({e}), using contract fallback formula.", flush=True)

    today = datetime.now()
    month = today.strftime("%b").upper()
    year = today.strftime("%y")
    fallback_symbol = f"{base_symbol}{fallback_day:02d}{month}{year}FUT"
    return fallback_symbol, fallback_lot


# ==============================================================================
# OPENALGO LIVE & PAPER TRADING BOT
# ==============================================================================
class MCXEMATrader:
    """
    OpenAlgo Execution Bot for MCX Futures.
    Features:
      - Closed-candle signal validation (eliminates repainting)
      - Internal paper state tracking (fixes infinite paper order loops)
      - RMS-compliant sequential reversals (close existing position before opening reverse)
    """

    def __init__(
        self,
        base_symbol: str = BASE_SYMBOL,
        exchange: str = EXCHANGE,
        interval: str = INTERVAL,
        fast_ema: int = FAST_EMA,
        slow_ema: int = SLOW_EMA,
        lots: int = LOTS,
        product: str = PRODUCT,
        host: str = OPENALGO_HOST,
        api_key: str = OPENALGO_API_KEY,
        paper_mode: bool = PAPER_MODE,
    ):
        self.base_symbol = base_symbol
        self.exchange = exchange
        self.interval = interval
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.num_lots = lots
        self.product = product
        self.host = host
        self.api_key = api_key
        self.paper_mode = paper_mode

        # Paper trading internal state
        self.paper_position: int = 0
        self.paper_avg_price: float = 0.0
        self.paper_trades: List[Dict[str, Any]] = []
        self.last_signaled_bar: Optional[Any] = None

        if api is None:
            raise ImportError("OpenAlgo SDK not found. Install it using 'pip install openalgo'.")

        self.client = api(api_key=self.api_key, host=self.host)

        # Resolve active contract symbol & lot size
        self.symbol, self.lot_size = resolve_mcx_contract(
            self.base_symbol, self.host, self.api_key, self.exchange
        )
        self.order_quantity = self.num_lots * self.lot_size

        print("=" * 80)
        print("OPENALGO MCX EMA CROSSOVER TRADING BOT")
        print("=" * 80)
        print(f"  Host Server     : {self.host}")
        print(f"  Base Symbol     : {self.base_symbol}")
        print(f"  Active Contract : {self.symbol}")
        print(f"  Lot Size        : {self.lot_size} units/lot")
        print(f"  Trading Lots    : {self.num_lots} lot(s) (Total Qty: {self.order_quantity})")
        print(f"  Timeframe       : {self.interval}")
        print(f"  Strategy        : EMA({self.fast_ema}) / EMA({self.slow_ema}) Crossover")
        print(f"  Direction       : {TRADE_DIRECTION}")
        print(f"  Paper Mode      : {self.paper_mode}")
        print("=" * 80, flush=True)

    def _get_required_lookback_days(self) -> int:
        """Dynamically computes required lookback days to ensure sufficient warmup bars."""
        interval_lower = self.interval.lower()
        if "m" in interval_lower:
            minutes = int(interval_lower.replace("m", "")) if interval_lower.replace("m", "").isdigit() else 5
            if minutes <= 5:
                return 15
            elif minutes <= 30:
                return 30
            return 60
        elif "h" in interval_lower:
            return 90
        elif "d" in interval_lower:
            return 365
        return 20

    def fetch_data(self) -> Optional[pd.DataFrame]:
        """Fetches historical OHLCV data with sufficient warmup for EMA convergence."""
        lookback_days = self._get_required_lookback_days()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)

        try:
            df = self.client.history(
                symbol=self.symbol,
                exchange=self.exchange,
                interval=self.interval,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
            if not isinstance(df, pd.DataFrame) or df.empty:
                print(f"[WARN] No historical data returned for {self.symbol}.", flush=True)
                return None

            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df.set_index("timestamp")
            elif not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)

            df = df.sort_index()
            if df.index.tz is not None:
                df.index = df.index.tz_convert(None)

            df.columns = [str(c).lower() for c in df.columns]

            min_required = self.slow_ema * 3
            if len(df) < min_required:
                print(f"[WARN] Insufficient bars ({len(df)}) for EMA({self.slow_ema}). Need >= {min_required}.", flush=True)
                return None

            return df
        except Exception as e:
            print(f"[ERROR] Historical data fetch failed: {e}", flush=True)
            return None

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates fast and slow EMAs."""
        df["ema_fast"] = calculate_ema(df["close"], self.fast_ema)
        df["ema_slow"] = calculate_ema(df["close"], self.slow_ema)
        return df

    def get_signal(self, df: pd.DataFrame) -> Tuple[Optional[str], Optional[Any]]:
        """
        Evaluates signals strictly on the last COMPLETED candle to prevent repainting.
        df.iloc[-1] is the incomplete/forming bar.
        df.iloc[-2] is the last completed bar.
        df.iloc[-3] is the completed bar prior to that.
        """
        if len(df) < 3:
            return None, None

        completed_bar = df.iloc[-2]
        prev_bar = df.iloc[-3]
        bar_timestamp = df.index[-2]

        # Prevent re-evaluating the exact same completed candle
        if self.last_signaled_bar == bar_timestamp:
            return None, bar_timestamp

        print(
            f"[{bar_timestamp}] Closed Bar -> Close: {completed_bar.close:.2f} | "
            f"EMA({self.fast_ema}): {completed_bar.ema_fast:.2f} | "
            f"EMA({self.slow_ema}): {completed_bar.ema_slow:.2f}",
            flush=True,
        )

        # Bullish Crossover on completed candle
        if prev_bar.ema_fast <= prev_bar.ema_slow and completed_bar.ema_fast > completed_bar.ema_slow:
            if TRADE_DIRECTION in ["BOTH", "BUY_ONLY"]:
                return "BUY", bar_timestamp

        # Bearish Crossover on completed candle
        if prev_bar.ema_fast >= prev_bar.ema_slow and completed_bar.ema_fast < completed_bar.ema_slow:
            if TRADE_DIRECTION in ["BOTH", "SELL_ONLY"]:
                return "SELL", bar_timestamp

        return None, bar_timestamp

    def get_current_position(self) -> int:
        """Retrieves net position quantity (internal state in paper mode, broker API in live)."""
        if self.paper_mode:
            return self.paper_position

        try:
            pos = self.client.openposition(
                strategy=STRATEGY_NAME,
                symbol=self.symbol,
                exchange=self.exchange,
                product=self.product,
            )
            if isinstance(pos, dict) and pos.get("quantity") is not None:
                return int(pos["quantity"])
        except Exception as e:
            print(f"[WARN] Broker position check failed: {e}", flush=True)

        return 0

    def place_order(self, action: str, quantity: int, execution_price: float = 0.0) -> Optional[Dict]:
        """Routes order to OpenAlgo broker API or logs paper trade."""
        lots_count = quantity // self.lot_size
        print(f"[ORDER] Submitting {action} {quantity} units ({lots_count} lots) of {self.symbol}...", flush=True)

        if self.paper_mode:
            if action == "BUY":
                self.paper_position += quantity
            elif action == "SELL":
                self.paper_position -= quantity

            paper_fill = {
                "status": "success",
                "mode": "paper",
                "action": action,
                "quantity": quantity,
                "net_position": self.paper_position,
                "price": execution_price,
                "timestamp": datetime.now().isoformat(),
            }
            self.paper_trades.append(paper_fill)
            print(
                f"[PAPER] Filled {action} {quantity} units @ {execution_price:.2f}. "
                f"New Net Position: {self.paper_position} units ({self.paper_position // self.lot_size} lots)",
                flush=True,
            )
            return paper_fill

        try:
            response = self.client.placeorder(
                strategy=STRATEGY_NAME,
                symbol=self.symbol,
                exchange=self.exchange,
                action=action,
                price_type="MARKET",
                product=self.product,
                quantity=quantity,
            )
            print(f"[RESPONSE] {response}", flush=True)
            return response
        except Exception as e:
            print(f"[ERROR] Order placement error: {e}", flush=True)
            return None

    def execute_cycle(self):
        """Executes a single cycle: data fetch -> signal check -> sequential order execution."""
        df = self.fetch_data()
        if df is None or df.empty:
            return

        df = self.calculate_indicators(df)
        signal, bar_timestamp = self.get_signal(df)
        current_pos = self.get_current_position()
        current_price = float(df["close"].iloc[-1])

        print(
            f"[CYCLE] Signal: {signal or 'NONE'} | "
            f"Current Position: {current_pos} units ({current_pos // self.lot_size} lots)",
            flush=True,
        )

        if not signal:
            return

        # Case 1: BUY Signal (Bullish Crossover)
        if signal == "BUY":
            if current_pos == 0:
                self.place_order(action="BUY", quantity=self.order_quantity, execution_price=current_price)
            elif current_pos < 0:
                # RMS Safe Reversal: 1. Close Short -> 2. Open Fresh Long
                close_qty = abs(current_pos)
                print(f"[REVERSAL] Squaring off SHORT position ({close_qty} units) before going LONG...", flush=True)
                self.place_order(action="BUY", quantity=close_qty, execution_price=current_price)
                self.place_order(action="BUY", quantity=self.order_quantity, execution_price=current_price)
            else:
                print("[INFO] Already in LONG position. No trade required.", flush=True)

        # Case 2: SELL Signal (Bearish Crossover)
        elif signal == "SELL":
            if current_pos == 0:
                self.place_order(action="SELL", quantity=self.order_quantity, execution_price=current_price)
            elif current_pos > 0:
                # RMS Safe Reversal: 1. Close Long -> 2. Open Fresh Short
                close_qty = current_pos
                print(f"[REVERSAL] Squaring off LONG position ({close_qty} units) before going SHORT...", flush=True)
                self.place_order(action="SELL", quantity=close_qty, execution_price=current_price)
                self.place_order(action="SELL", quantity=self.order_quantity, execution_price=current_price)
            else:
                print("[INFO] Already in SHORT position. No trade required.", flush=True)

        # Record bar timestamp to prevent double triggers on same bar
        self.last_signaled_bar = bar_timestamp

    def run_loop(self, poll_interval: int = 60):
        """Runs continuous polling loop."""
        print(f"[LOOP] Starting strategy poll loop (interval: {poll_interval}s). Press Ctrl+C to stop.\n", flush=True)
        while True:
            try:
                self.execute_cycle()
            except KeyboardInterrupt:
                print("\n[STOP] Strategy stopped by user.")
                break
            except Exception as e:
                print(f"[ERROR] Cycle execution failed: {e}", flush=True)

            time.sleep(poll_interval)


# ==============================================================================
# MCX MULTI-ASSET FUTURES BACKTEST ENGINE
# ==============================================================================
def calculate_mcx_transaction_charges(turnover_buy: float, turnover_sell: float) -> float:
    """
    Calculates exact regulatory and statutory charges for MCX Commodity Futures in India.
    Includes:
      - Brokerage: Rs 20 buy + Rs 20 sell = Rs 40
      - CTT (Commodities Transaction Tax): 0.01% on sell turnover (Futures)
      - Exchange Transaction Charges: 0.0026% on total turnover
      - GST: 18% on (Brokerage + Exchange Charges)
      - SEBI Turnover Charges: 0.0001% on total turnover
      - Stamp Duty: 0.002% on buy turnover
    """
    turnover_total = turnover_buy + turnover_sell
    brokerage = 40.0  # Rs 20 per order
    ctt = 0.0001 * turnover_sell
    exchange_charges = 0.000026 * turnover_total
    gst = 0.18 * (brokerage + exchange_charges)
    sebi_charges = 0.000001 * turnover_total
    stamp_duty = 0.00002 * turnover_buy
    return brokerage + ctt + exchange_charges + gst + sebi_charges + stamp_duty


def run_mcx_futures_backtest(
    name: str,
    base_symbol: str,
    fast_ema: int = 9,
    slow_ema: int = 21,
    lookback_years: int = 3,
    initial_capital: float = 500_000.0,
    slippage_ticks: int = 1,
) -> Optional[Dict]:
    """
    Performs institutional-grade, lookahead-free bi-directional MCX Futures backtesting.
    Accounts for INR point value, lot sizes, slippage, and statutory Indian market costs.
    """
    if yf is None:
        print("[ERROR] yfinance is required for historical simulation. Install via 'pip install yfinance'.")
        return None

    spec = MCX_COMMODITY_SPECS.get(base_symbol, {
        "yf_symbol": "CL=F",
        "default_lot": 100,
        "tick": 1.0,
        "point_value": 100.0,
        "conv_type": "barrel",
    })

    yf_symbol = spec["yf_symbol"]
    lot_size = spec["default_lot"]
    tick_size = spec.get("tick", 1.0)
    point_value = spec.get("point_value", float(lot_size))
    conv_type = spec.get("conv_type", "barrel")

    start_date = (datetime.now() - timedelta(days=lookback_years * 365)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    # Download historical daily data
    raw_df = yf.download(yf_symbol, start=start_date, end=end_date, progress=False)
    if raw_df.empty:
        print(f"[WARN] No data available for {yf_symbol}.", flush=True)
        return None

    # Handle MultiIndex columns from newer yfinance versions
    if isinstance(raw_df.columns, pd.MultiIndex):
        if "Ticker" in raw_df.columns.names:
            df = raw_df.xs(yf_symbol, level="Ticker", axis=1).copy()
        else:
            df = raw_df.copy()
            df.columns = [c[0] for c in df.columns]
    else:
        df = raw_df.copy()

    df = df.dropna()
    if len(df) < slow_ema + 20:
        return None

    # Convert COMEX USD prices into realistic MCX INR prices
    df = convert_comex_to_mcx(df, conv_type=conv_type)

    close = df["Close"]
    open_prices = df["Open"] if "Open" in df.columns else close

    # Calculate Indicators
    ema_fast = calculate_ema(close, fast_ema)
    ema_slow = calculate_ema(close, slow_ema)

    # Raw Crossover Signals
    raw_buy = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
    raw_sell = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))

    # Clean signals with exrem
    buy_signals, sell_signals = apply_exrem(raw_buy, raw_sell)

    # Initialise native framework models if available
    use_native_framework = (
        TradeLogManager is not None
        and Trade is not None
        and EquityCurveTracker is not None
        and TradeAnalytics is not None
        and PortfolioAnalytics is not None
    )

    trade_manager = TradeLogManager() if use_native_framework else None
    equity_tracker = EquityCurveTracker(initial_capital) if use_native_framework else None

    capital = initial_capital
    position = 0  # +1 Long, -1 Short, 0 Flat
    entry_price = 0.0
    entry_idx = 0
    trade_counter = 1
    trades_list = []
    equity_curve = [initial_capital] * len(close)

    slippage_cost = slippage_ticks * tick_size

    # Simulation Loop: Signal at bar i close -> Order fills at bar i+1 open (NO LOOKAHEAD)
    for i in range(len(close) - 1):
        date = close.index[i]
        curr_close = float(close.iloc[i])

        # Next bar execution price (open of i+1)
        next_open = float(open_prices.iloc[i + 1])
        next_date = close.index[i + 1]

        # Process Signals triggered on bar i
        if buy_signals.iloc[i]:
            # If already Short, close Short at next bar open + slippage
            if position == -1:
                exit_price = next_open + slippage_cost
                pts = entry_price - exit_price
                gross_pnl = pts * point_value
                charges = calculate_mcx_transaction_charges(
                    turnover_buy=exit_price * lot_size,
                    turnover_sell=entry_price * lot_size,
                )
                net_pnl = gross_pnl - charges
                capital += net_pnl

                trade_data = {
                    "trade_id": trade_counter,
                    "symbol": base_symbol,
                    "type": "SHORT",
                    "entry_date": close.index[entry_idx],
                    "entry_price": entry_price,
                    "exit_date": next_date,
                    "exit_price": exit_price,
                    "points": pts,
                    "pnl": net_pnl,
                    "holding_days": i + 1 - entry_idx,
                }
                trades_list.append(trade_data)

                if use_native_framework:
                    trade_manager.add_trade(
                        Trade(
                            trade_id=trade_counter,
                            symbol=base_symbol,
                            side="SHORT",
                            entry_index=entry_idx,
                            exit_index=i + 1,
                            entry_date=close.index[entry_idx],
                            exit_date=next_date,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            quantity=float(lot_size),
                            profit_loss=net_pnl,
                            profit_loss_pct=(pts / entry_price) * 100.0,
                            holding_period=i + 1 - entry_idx,
                            exit_reason="BULLISH_REVERSAL",
                            type="FUTURES",
                            slippage=slippage_cost * point_value,
                            brokerage=charges,
                        )
                    )
                trade_counter += 1

            # Enter Long at next bar open + slippage
            position = 1
            entry_price = next_open + slippage_cost
            entry_idx = i + 1

        elif sell_signals.iloc[i]:
            # If already Long, close Long at next bar open - slippage
            if position == 1:
                exit_price = next_open - slippage_cost
                pts = exit_price - entry_price
                gross_pnl = pts * point_value
                charges = calculate_mcx_transaction_charges(
                    turnover_buy=entry_price * lot_size,
                    turnover_sell=exit_price * lot_size,
                )
                net_pnl = gross_pnl - charges
                capital += net_pnl

                trade_data = {
                    "trade_id": trade_counter,
                    "symbol": base_symbol,
                    "type": "LONG",
                    "entry_date": close.index[entry_idx],
                    "entry_price": entry_price,
                    "exit_date": next_date,
                    "exit_price": exit_price,
                    "points": pts,
                    "pnl": net_pnl,
                    "holding_days": i + 1 - entry_idx,
                }
                trades_list.append(trade_data)

                if use_native_framework:
                    trade_manager.add_trade(
                        Trade(
                            trade_id=trade_counter,
                            symbol=base_symbol,
                            side="LONG",
                            entry_index=entry_idx,
                            exit_index=i + 1,
                            entry_date=close.index[entry_idx],
                            exit_date=next_date,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            quantity=float(lot_size),
                            profit_loss=net_pnl,
                            profit_loss_pct=(pts / entry_price) * 100.0,
                            holding_period=i + 1 - entry_idx,
                            exit_reason="BEARISH_REVERSAL",
                            type="FUTURES",
                            slippage=slippage_cost * point_value,
                            brokerage=charges,
                        )
                    )
                trade_counter += 1

            # Enter Short at next bar open - slippage
            position = -1
            entry_price = next_open - slippage_cost
            entry_idx = i + 1

        # Mark-to-Market Equity Accounting
        if position == 1:
            floating_pnl = (curr_close - entry_price) * point_value
            eq = capital + floating_pnl
        elif position == -1:
            floating_pnl = (entry_price - curr_close) * point_value
            eq = capital + floating_pnl
        else:
            eq = capital

        equity_curve[i] = eq
        if use_native_framework:
            pos_val = (curr_close * lot_size) if position != 0 else 0.0
            equity_tracker.record_bar(
                date=date,
                portfolio_value=eq,
                cash=capital,
                position_value=pos_val,
            )

    equity_curve[-1] = capital

    # Compute Performance Analytics
    net_profit = capital - initial_capital
    total_ret = (net_profit / initial_capital) * 100.0
    bench_ret = ((close.iloc[-1] - close.iloc[0]) / close.iloc[0]) * 100.0

    # Max Drawdown
    peak = initial_capital
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    wins = [t for t in trades_list if t["pnl"] > 0]
    losses = [t for t in trades_list if t["pnl"] <= 0]
    win_rate = (len(wins) / len(trades_list) * 100.0) if trades_list else 0.0
    gross_p = sum(t["pnl"] for t in wins)
    gross_l = abs(sum(t["pnl"] for t in losses))
    pf = (gross_p / gross_l) if gross_l > 0 else (99.0 if gross_p > 0 else 0.0)

    daily_returns = pd.Series(equity_curve).pct_change().dropna()
    mean_ret = daily_returns.mean()
    std_ret = daily_returns.std()
    downside_std = daily_returns[daily_returns < 0].std()

    sharpe = (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0.0
    sortino = (mean_ret / downside_std * math.sqrt(252)) if (downside_std and downside_std > 0) else 0.0

    # Export trades CSV
    report_dir = Path(__file__).resolve().parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    trades_csv_path = report_dir / f"{base_symbol.lower()}_trades.csv"

    if use_native_framework and trade_manager and len(trade_manager) > 0:
        trade_manager.export_csv(str(trades_csv_path))
    elif trades_list:
        pd.DataFrame(trades_list).to_csv(trades_csv_path, index=False)

    return {
        "name": name,
        "base_symbol": base_symbol,
        "lot_size": lot_size,
        "start": close.index[0].strftime("%Y-%m-%d"),
        "end": close.index[-1].strftime("%Y-%m-%d"),
        "bars": len(close),
        "initial_capital": initial_capital,
        "final_capital": capital,
        "net_pnl": net_profit,
        "total_return": total_ret,
        "benchmark_return": bench_ret,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "win_rate": win_rate,
        "profit_factor": pf,
        "trades_count": len(trades_list),
        "recent_trades": trades_list[-3:] if trades_list else [],
        "trades_csv": str(trades_csv_path),
    }


def run_all_backtests(fast_ema: int = FAST_EMA, slow_ema: int = SLOW_EMA, lookback_years: int = 3):
    """Runs lookahead-free backtesting across key MCX Commodities."""
    commodities = {
        "Crude Oil": "CRUDEOIL",
        "Natural Gas": "NATURALGAS",
        "Gold": "GOLD",
        "Silver": "SILVER",
        "Copper": "COPPER",
    }

    print("\n" + "=" * 105)
    print(f"MCX FUTURES BI-DIRECTIONAL BACKTEST: EMA({fast_ema}) & EMA({slow_ema}) CROSSOVER")
    print("Strategy: Long + Short Futures | Realistic MCX CTT & Friction | Lookahead-Free Fills")
    print("=" * 105)

    results = []
    for name, sym in commodities.items():
        print(f"Analyzing {name:15} [{sym}]...")
        res = run_mcx_futures_backtest(
            name=name,
            base_symbol=sym,
            fast_ema=fast_ema,
            slow_ema=slow_ema,
            lookback_years=lookback_years,
        )
        if res:
            results.append(res)

    print("\n" + "=" * 105)
    print("PERFORMANCE SUMMARY TABLE (1 LOT MCX FUTURES)")
    print("=" * 105)
    header = (
        f"{'Commodity':15} {'Symbol':12} {'Lot Size':10} {'Net P&L (INR)':15} "
        f"{'Return %':10} {'MaxDD %':9} {'Win %':8} {'Trades':8} {'Sharpe':7} {'PF':6}"
    )
    print(header)
    print("-" * 105)

    for r in results:
        print(
            f"{r['name']:15} {r['base_symbol']:12} {r['lot_size']:<10} "
            f"Rs {r['net_pnl']:+12,.0f} {r['total_return']:+9.2f}% "
            f"{r['max_drawdown']:8.2f}% {r['win_rate']:7.1f}% {r['trades_count']:8} "
            f"{r['sharpe']:7.2f} {r['profit_factor']:6.2f}"
        )
    print("=" * 105)
    print(f"[INFO] Detailed trade logs exported to 'backtesting/reports/' folder.\n")


# ==============================================================================
# MAIN CLI ENTRY POINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="MCX EMA Crossover Live Trading & Backtesting Engine")
    parser.add_argument(
        "--mode",
        choices=["trade", "backtest", "both"],
        default=os.getenv("MODE", "backtest"),
        help="Execution mode: 'trade' for OpenAlgo live/paper trading, 'backtest' for multi-asset simulation.",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        default=RUN_ONCE,
        help="Run single execution cycle and exit (useful for testing & cron jobs).",
    )
    parser.add_argument(
        "--symbol",
        default=BASE_SYMBOL,
        help=f"MCX Base Symbol (default: {BASE_SYMBOL}).",
    )
    parser.add_argument(
        "--lots",
        type=int,
        default=LOTS,
        help=f"Number of lots to trade (default: {LOTS}).",
    )
    parser.add_argument(
        "--fast-ema",
        type=int,
        default=FAST_EMA,
        help=f"Fast EMA period (default: {FAST_EMA}).",
    )
    parser.add_argument(
        "--slow-ema",
        type=int,
        default=SLOW_EMA,
        help=f"Slow EMA period (default: {SLOW_EMA}).",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=3,
        help="Historical lookback years for backtest (default: 3).",
    )
    parser.add_argument(
        "--paper",
        action="store_true",
        default=PAPER_MODE,
        help="Enable paper trading mode (tracks positions locally without broker execution).",
    )
    args = parser.parse_args()

    if args.mode in ["backtest", "both"]:
        if args.symbol and args.symbol.upper() != "ALL":
            spec_name = args.symbol.capitalize()
            print(f"\n[INFO] Running backtest for {args.symbol.upper()}...")
            res = run_mcx_futures_backtest(
                name=spec_name,
                base_symbol=args.symbol.upper(),
                fast_ema=args.fast_ema,
                slow_ema=args.slow_ema,
                lookback_years=args.years,
            )
            if res:
                print(f"Results for {res['name']} [{res['base_symbol']}]:")
                print(f"  Period         : {res['start']} to {res['end']} ({res['bars']} bars)")
                print(f"  Net P&L        : Rs {res['net_pnl']:+,.2f}")
                print(f"  Total Return   : {res['total_return']:+.2f}%")
                print(f"  Benchmark Ret  : {res['benchmark_return']:+.2f}%")
                print(f"  Max Drawdown   : {res['max_drawdown']:.2f}%")
                print(f"  Win Rate       : {res['win_rate']:.1f}% ({res['trades_count']} trades)")
                print(f"  Profit Factor  : {res['profit_factor']:.2f}")
                print(f"  Sharpe Ratio   : {res['sharpe']:.2f}")
                print(f"  Sortino Ratio  : {res['sortino']:.2f}")
                print(f"  Trades Log     : {res['trades_csv']}")
        else:
            run_all_backtests(fast_ema=args.fast_ema, slow_ema=args.slow_ema, lookback_years=args.years)

    if args.mode in ["trade", "both"]:
        trader = MCXEMATrader(
            base_symbol=args.symbol,
            fast_ema=args.fast_ema,
            slow_ema=args.slow_ema,
            lots=args.lots,
            paper_mode=args.paper,
        )
        if args.run_once:
            print("[INFO] Executing single strategy cycle...", flush=True)
            trader.execute_cycle()
        else:
            trader.run_loop(poll_interval=60)


if __name__ == "__main__":
    main()
