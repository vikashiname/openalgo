# Options Research & Backtesting Strategies

This directory houses quantitative research strategies, historical backtests, and sensitivity models ported from the options income autoresearch engine.

> **Safety Notice**:  
> Scripts in this folder are for **research, simulation, and backtesting only**.  
> They do **not** connect to OpenAlgo live broker endpoints or place live orders.

---

## 1. Nifty Covered Call Strategy

**File:** [`nifty_covered_call.py`](file:///Users/mac/Desktop/openalgo/strategies/research/nifty_covered_call.py)

### Description
Executes a historical simulation of an institutional Covered Call (Cash-Secured / Equity-Covered Call) strategy on NIFTY options using real option chains, Black-Scholes Greeks, and friction models.

### Key Baseline Parameters
- **Delta Target:** 0.30 OTM Call
- **Target DTE:** 28 days
- **Roll DTE:** 10 days
- **Profit Target:** 90% of collected premium (Net-aware: ensures gain > roundtrip friction)
- **Stop Loss Multiplier:** 3.0x premium
- **Min Premium Floor:** ₹25.00 (eliminates sub-₹20 penny drag)
- **Trend Filter:** Bullish gate (`Spot > 100 EMA`)
- **Cost Engine:** Full Indian statutory schedule (date-aware 0.10% STT, 18% GST, ₹20 brokerage, slippage)

### How to Run

```bash
# Run baseline backtest and exit cleanly
.venv/bin/python strategies/research/nifty_covered_call.py --backtest-only

# Run optimized fast-decay configuration (50% target, 0.30 delta)
.venv/bin/python strategies/research/nifty_covered_call.py \
    --delta 0.30 \
    --target 0.50 \
    --stoploss 3.0 \
    --min-premium 25.0 \
    --backtest-only

# Export trade ledger and monthly summary
.venv/bin/python strategies/research/nifty_covered_call.py \
    --backtest-only \
    --export-trades strategies/research/trade_ledger.csv \
    --export-monthly strategies/research/monthly_summary.csv
```

### Baseline Performance Benchmark (NIFTY 2019–2024, Net of All Statutory Costs & Slippage)
- **Annual Rent Yield:** 14.38% (14.70% under 50% target)
- **Sharpe Ratio:** 1.04 (1.21 under 50% target)
- **Max Drawdown:** 3.88% (2.98% under 50% target)
- **Profit Factor:** 2.46
- **Win Rate:** 69.23%
- **Total Trades:** 117
- **Profitable Months:** 71.05%
