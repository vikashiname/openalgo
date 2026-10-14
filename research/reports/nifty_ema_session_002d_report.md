# NIFTY F&O Quantitative Research Report — Experiment 002D: EMA + Trading Session Filter

---

### Executive Summary

| Parameter | Control (Baseline) | Treatment (Session Gate) | Delta / Change |
| :--- | :---: | :---: | :---: |
| **Strategy Configuration** | **EMA (9/21)** | **EMA (9/21) + Session Filter (09:45–14:45 IST)** | Intraday execution timing window |
| **Asset / Universe** | NIFTY Index Futures (`FUTIDX-NIFTY`) | NIFTY Index Futures (`FUTIDX-NIFTY`) | Identical 1-Hour dataset (5,057 bars) |
| **In-Sample Period (70%)** | 2023-09-20 to 2025-10-09 | 2023-09-20 to 2025-10-09 | 3,539 bars |
| **Out-of-Sample Period (30%)** | 2025-10-09 to 2026-08-31 | 2025-10-09 to 2026-08-31 | 1,518 bars |
| **Execution Protocol** | Next-Bar Open, Zero Look-ahead | Next-Bar Open, Zero Look-ahead | Identical statutory costs + slippage |
| **In-Sample Profit Factor** | **1.33** | **1.47** | **+0.14 (Both IS & OOS Improved)** |
| **In-Sample Net P&L (₹)** | **+₹469,797.94** | **+₹525,316.90** | **+₹55,518.96** |
| **Out-of-Sample Profit Factor** | **0.96** | **1.13** | **+0.17 (Positive Alpha Shift)** |
| **OOS Net P&L (₹)** | **-₹36,228.98** | **+₹90,360.94** | **+₹126,589.92** |
| **OOS Max Drawdown %** | **25.21%** | **22.87%** | **-2.34%** |
| **OOS Sharpe Ratio** | **-0.18** | **+0.20** | **+0.38** |
| **OOS Sortino Ratio** | **-0.27** | **+0.31** | **+0.58** |
| **Trade Reduction Rate** | 69 Trades | 59 Trades | **-14.5% Opening/Closing Noise Filtered** |
| **Experimental Verdict** | — | — | **🟢 IMPROVED** |

---

### 1. Hypothesis & Single-Variable Protocol

#### Research Objective
Evaluate whether restricting trade entry execution to the core institutional liquid trading window (**09:45 to 14:45 IST**) eliminates opening gap auction noise (09:15–09:45) and closing 15-minute squawk reversals (15:15–15:30) on NIFTY 1-hour futures.

#### Controlled Single-Variable Formulation
- **Fixed Parameters**: Fast EMA = 9, Slow EMA = 21, 1-Hour timeframe, Long + Short.
- **Entry Gate**: Fresh trade entry execution is permitted *if and only if* execution time falls between 09:45 and 14:45 IST.
- **Exit Rule**: Exit occurs on standard opposite EMA crossover (unrestricted to ensure complete risk containment).
- **Strict Controls**: Identical 70/30 chronological split, identical statutory fees, and 0.5-point execution slippage per leg.

---

### 2. Comprehensive Experimental Matrix

All metrics reflect ₹1,000,000 initial capital, 2 contracts (100 quantity), next-bar open execution, and full statutory friction:

| Metric | IS Control (9/21) | IS Treatment (+Session) | IS Delta | OOS Control (9/21) | OOS Treatment (+Session) | OOS Delta |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Total Trades** | 129 | 98 | -31 (-24.0%) | 69 | 59 | **-10 (-14.5%)** |
| **Net P&L (₹)** | +₹469,797.94 | +₹525,316.90 | +₹55,518.96 | -₹36,228.98 | +₹90,360.94 | **+₹126,589.92** |
| **Profit Factor** | 1.33 | 1.47 | +0.14 | 0.96 | 1.13 | **+0.17** |
| **Win Rate %** | 40.31% | 42.86% | +2.55% | 33.33% | 35.59% | **+2.26%** |
| **Expectancy (₹/Trade)**| +₹3,641.84 | +₹5,360.38 | +₹1,718.54 | -₹525.06 | +₹1,531.54 | **+₹2,056.60** |
| **Max Drawdown (₹)** | ₹326,670.41 | ₹337,420.10 | +₹10,749.69 | ₹320,051.44 | ₹274,380.00 | **-₹45,671.44** |
| **Max Drawdown %** | 26.67% | 25.80% | -0.87% | 25.21% | 22.87% | **-2.34%** |
| **Annualized Sharpe** | +0.49 | +0.57 | +0.08 | -0.18 | +0.20 | **+0.38** |
| **Annualized Sortino**| +0.31 | +0.31 | 0.00 | -0.27 | +0.31 | **+0.58** |
| **Recovery Factor** | 1.44 | 1.56 | +0.12 | -0.11 | 0.33 | **+0.44** |
| **Max Loss Streak** | 8 | 7 | -1 | 8 | 6 | **-2** |
| **Long Net P&L (₹)** | +₹478,572.87 | +₹508,410.20 | +₹29,837.33 | -₹69,588.08 | +₹28,140.40 | **+₹97,728.48** |
| **Short Net P&L (₹)**| -₹8,774.92 | +₹16,906.70 | +₹25,681.62 | +₹33,359.10 | +₹62,220.54 | **+₹28,861.44** |

---

### 3. Quantitative Analysis & Market Microstructure Mechanics

#### A. Dual In-Sample and Out-of-Sample Confirmation
- Unlike indicator filters (like ADX or VIX) which often trade off In-Sample performance for OOS noise reduction, the Trading Session Filter improved **both In-Sample (+₹55.5k, PF 1.33 $\rightarrow$ 1.47)** and **Out-of-Sample (+₹126.6k, PF 0.96 $\rightarrow$ 1.13)**.

#### B. Market Microstructure Mechanics
1. **Opening Gap Auction (09:15–09:45 IST)**: Overnight global cues often trigger gap openings that produce temporary, artificial EMA crossover spikes at 09:15, only to violently mean-revert during the first 30 minutes of price discovery. Blocking entries before 09:45 successfully avoids these false gap-induced entries.
2. **Closing Squawk (15:00–15:30 IST)**: Crosses occurring at 15:15 force a swing trade entry 15 minutes before the cash market closes, subjecting the position to unhedged overnight gap risk with zero intraday momentum follow-through.

---

### 4. Classification & Decision Rule

Under the established research decision framework:

> [!TIP]
> ### Verdict: 🟢 IMPROVED
> **Rationale**:
> 1. **Robust Dual-Phase Improvement**: Gating trade execution between 09:45 and 14:45 IST improved performance across both In-Sample (PF 1.33 $\rightarrow$ 1.47) and Out-of-Sample (PF 0.96 $\rightarrow$ 1.13, Net P&L -₹36.2k $\rightarrow$ +₹90.4k).
> 2. **Microstructure Soundness**: The filter addresses genuine structural friction in Indian equity markets (opening auction volatility and closing squawk illiquidity) rather than statistical curve-fitting.
> 3. **Candidate Status**: The 09:45–14:45 session timing rule is confirmed as a robust execution hygiene rule to be carried forward into multi-variable testing.
