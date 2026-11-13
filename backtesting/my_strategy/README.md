# My Custom Strategy (Independent Research & Execution)

> **Zero Contamination Guarantee:** This directory is **100% isolated** from production trading in `strategies/liveopenalgo/`. It has its own independent state files, logs, parameters, and paper-trading engine.

---

## 📁 Directory Structure

```text
backtesting/my_strategy/
├── config.py                 # Central strategy parameters & risk settings
├── backtest.py               # Historical backtesting engine with Indian market friction
├── strategy_runner.py        # Standalone paper/live execution runner
├── README.md                 # Strategy documentation and guide
├── data/                     # Historical OHLCV datasets and cached CSVs
└── reports/                  # Generated trade logs, metrics, and equity curves
```

---

## 🚀 Quick Start Guide

### 1. Run a Historical Backtest

To run a backtest on historical data with realistic Indian brokerage and statutory charges (STT, GST, Stamp Duty, Slippage):

```bash
# Default backtest (RELIANCE, 15m, 180 days)
python3 backtest.py

# Custom symbol and timeframe
python3 backtest.py --symbol INFY --interval 15m --days 90

# Long-term daily backtest
python3 backtest.py --symbol SBIN --interval D --days 365
```

**Outputs generated:**
- `reports/trade_history.csv`: Row-by-row breakdown of every entry, exit, PnL, and statutory friction.
- `reports/backtest_summary.json`: Win rate, profit factor, max drawdown %, Sharpe ratio, and CAGR.

---

### 2. Run Paper Trading / Dry-Run Simulation

The runner evaluates the market and simulates trades in real-time **without placing real orders** on your broker account:

```bash
# Run a single pre-flight diagnostic cycle
python3 strategy_runner.py --test

# Run continuous paper trading loop (scans every 60s)
python3 strategy_runner.py --paper --interval-sec 60
```

---

## ⚙️ How to Customize Your Strategy

### Editing Parameters
Open `config.py` to change:
- **Instrument**: `SYMBOL`, `EXCHANGE`, `INTERVAL`
- **Indicators**: `EMA_FAST`, `EMA_SLOW`, `RSI_PERIOD`, `RSI_BULLISH_THRESHOLD`
- **Risk Management**: `STOP_LOSS_PCT`, `PROFIT_TARGET_PCT`, `TRAILING_SL_PCT`, `INITIAL_CAPITAL`

### Customizing Entry / Exit Logic
- Open `backtest.py` -> Edit `run_backtest()` function.
- Open `strategy_runner.py` -> Edit `run_iteration()` function.

---

## 🛡️ Isolation Verification Checklist

- [x] State file is stored locally at `backtesting/my_strategy/strategy_state.json`.
- [x] Heartbeat file is stored locally at `backtesting/my_strategy/strategy_heartbeat.json`.
- [x] Log file is stored locally at `backtesting/my_strategy/strategy.log`.
- [x] `scripts/deploy_live_strategies.sh` does **not** touch or deploy this directory.
- [x] The live watchdog does **not** monitor or terminate this strategy.
