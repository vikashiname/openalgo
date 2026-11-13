"""
================================================================================
MY STRATEGY CONFIGURATION (ISOLATED RESEARCH & EXECUTION RUNNER)
================================================================================
Directory   : backtesting/my_strategy/
Role        : Independent strategy configuration decoupled from liveopenalgo
================================================================================
"""

import os
from pathlib import Path

# --- Directory & Path Isolation (Zero Contamination) ---
STRATEGY_DIR = Path(__file__).resolve().parent
DATA_DIR = STRATEGY_DIR / "data"
REPORTS_DIR = STRATEGY_DIR / "reports"

# Isolated state, heartbeat, and log files - NEVER touches strategies/liveopenalgo
STATE_FILE = STRATEGY_DIR / "strategy_state.json"
HEARTBEAT_FILE = STRATEGY_DIR / "strategy_heartbeat.json"
LOG_FILE = STRATEGY_DIR / "strategy.log"

# --- Strategy Identity ---
STRATEGY_NAME = "MyCustomStrategy"
VERSION = "1.0.0"

# --- Instrument & Market ---
SYMBOL = os.getenv("STRATEGY_SYMBOL", "RELIANCE")
EXCHANGE = os.getenv("STRATEGY_EXCHANGE", "NSE")  # NSE, NFO, MCX, BSE, etc.
INTERVAL = os.getenv("STRATEGY_INTERVAL", "15m")  # 1m, 3m, 5m, 15m, 1h, D

# --- Technical Parameters (Example: Trend Following EMA + RSI Filter) ---
EMA_FAST = int(os.getenv("EMA_FAST", "9"))
EMA_SLOW = int(os.getenv("EMA_SLOW", "21"))
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
RSI_BULLISH_THRESHOLD = float(os.getenv("RSI_BULLISH_THRESHOLD", "50.0"))
RSI_BEARISH_THRESHOLD = float(os.getenv("RSI_BEARISH_THRESHOLD", "50.0"))

# --- Risk Management ---
INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "100000.0"))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))  # 1% per trade
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "1.5"))          # 1.5% SL
PROFIT_TARGET_PCT = float(os.getenv("PROFIT_TARGET_PCT", "3.0"))  # 3.0% TP (1:2 R:R)
TRAILING_SL_PCT = float(os.getenv("TRAILING_SL_PCT", "1.0"))      # 1.0% Trailing SL

# --- Brokerage & Indian Market Statutory Friction ---
BROKERAGE_PER_ORDER = 20.0     # Flat ₹20 per executed order
STT_PCT = 0.001                # 0.1% on delivery / 0.025% on intraday sell
EXCHANGE_TURNOVER_PCT = 0.0000345
GST_PCT = 0.18                 # 18% on brokerage + turnover
SEBI_TURNOVER_PCT = 0.000001
STAMP_DUTY_PCT = 0.00015       # 0.015% on buy
SLIPPAGE_PCT = 0.0005          # 0.05% slippage allowance
