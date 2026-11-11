# NIFTY Covered Call Backtest & Baseline Comparison Report

**Workspace:** `backtesting/nifty_covered_call/`  
**Dataset:** NSE Continuous Daily Futures & Options Synthetics (2022-01-03 to 2024-07-31, 635 trading sessions, 32 monthly expiries)  
**Lot Size:** 50 (Standard NIFTY Contract)  
**Execution Files:**
- Engine & Runner: [`backtesting/nifty_covered_call/backtest_covered_call.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/backtest_covered_call.py)
- Baseline Trade Log: [`backtesting/nifty_covered_call/trades_baseline.csv`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/trades_baseline.csv)
- Trend/Trail Trade Log: [`backtesting/nifty_covered_call/trades_trend_following_trailing.csv`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/trades_trend_following_trailing.csv)
- Metrics CSV: [`backtesting/nifty_covered_call/comparison_metrics.csv`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/comparison_metrics.csv)

---

## 1. Executive Performance Comparison

| Metric | Baseline (Unhedged Futures) | Trend-Following & Trailing | Analysis & Key Difference |
| :--- | :---: | :---: | :--- |
| **Total Net P&L** | **₹2,64,980.62** | **₹2,61,564.29** | Near-identical return (~₹3.4k difference over 2.5 years) |
| **Total Cycles / Trades** | 23 | 23 | Identical entry cycles (Spot > 100-EMA) |
| **Win Rate** | **78.26%** | **78.26%** | 18 Wins / 5 Losses |
| **Profit Factor** | **6.66** | **5.92** | Robust profitability on both models |
| **Max Drawdown (₹)** | **₹23,639.11** | **₹23,639.11** | Drawdown controlled within ₹24,000 |
| **Sharpe Ratio** | **2.89** | **2.74** | High risk-adjusted return |
| **Sortino Ratio** | **9.40** | **6.07** | Exceptional downside protection |
| **Calmar Ratio** | **11.21** | **11.06** | Return-to-drawdown ratio > 11x |
| **Average Trade** | ₹11,520.90 | ₹11,372.36 | Average monthly yield per 1 lot |
| **Largest Single Win** | +₹30,924.93 | +₹30,924.93 | Strong trending rally capture |
| **Avg Holding Period** | 16.5 Days | 15.9 Days | Shorter exposure duration with trailing lock |

---

## 2. Key Insights & Critical Discoveries

### A. The "Downside Profit Target" Trap in Baseline
In the Baseline model, **all 5 losing trades** (100% of losses) were closed with the label:
```
PROFIT_TARGET_HIT (90% Decay) -> Net Losses: -₹7,843, -₹12,399, -₹3,396, -₹8,822, -₹14,334
```
When NIFTY suffered mid-cycle pullbacks, the Call Option decayed to 90% of its initial value due to Delta collapse. The Baseline engine mistakenly flagged this as a "Profit Target Hit" and liquidated the position at the bottom of the drawdown, booking heavy futures losses.

The **Trend-Following & Trailing** model fixes this by classifying these as `BEARISH_DECAY_CLOSE (Net Negative M2M)` or cutting at the futures stop limit.

### B. Trailing Profit Lock Prevents Evaporation
Look at **Trade #18 (March–April 2024)**:
- **Peak Unrealized Profit:** Reached $+₹16,029$
- **Baseline Result:** Held through the expiry roll, giving almost all gains back $\to$ **Net P&L: +₹333.30**
- **Trailing Result:** Triggered at peak pullback $\to$ **Net P&L: +₹9,587.46** (Saved $+₹9,254$ in profit)

### C. Trailing Stop Calibration
- If the trailing stop pullback buffer is set too tight (e.g., ₹3,500 / 70 NIFTY points), normal intraday market noise stops out winning trades prematurely before the theta decay curve accelerates.
- Setting the trailing activation at $+₹15,000$ with a 40% pullback buffer preserves 98.7% of total baseline profits while protecting against late-cycle sharp reversals.
