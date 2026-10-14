# NIFTY F&O Quantitative Research Report — Experiment 002E: EMA + Daily HTF Trend Alignment

---

### Executive Summary

| Parameter | Control (Baseline) | Treatment (Daily EMA 50 Gate) | Delta / Change |
| :--- | :---: | :---: | :---: |
| **Strategy Configuration** | **EMA (9/21)** | **EMA (9/21) + Daily EMA 50 HTF Alignment** | Higher-timeframe trend filter |
| **Asset / Universe** | NIFTY Index Futures (`FUTIDX-NIFTY`) | NIFTY Index Futures (`FUTIDX-NIFTY`) | Identical 1-Hour dataset (5,057 bars) |
| **HTF Indicator** | None | Daily EMA(50) on confirmed ($D-1$) Close | Strict zero-lookahead alignment |
| **In-Sample Period (70%)** | 2023-09-20 to 2025-10-09 | 2023-09-20 to 2025-10-09 | 3,539 bars |
| **Out-of-Sample Period (30%)** | 2025-10-09 to 2026-08-31 | 2025-10-09 to 2026-08-31 | 1,518 bars |
| **Execution Protocol** | Next-Bar Open, Zero Look-ahead | Next-Bar Open, Zero Look-ahead | Identical statutory costs + slippage |
| **In-Sample Profit Factor** | **1.33** | **1.18** | **-0.15 (Lag Penalty)** |
| **In-Sample Net P&L (₹)** | **+₹469,797.94** | **+₹98,283.59** | **-₹371,514.35** |
| **Out-of-Sample Profit Factor** | **0.96** | **0.69** | **-0.27 (Severe OOS Failure)** |
| **OOS Net P&L (₹)** | **-₹36,228.98** | **-₹98,256.06** | **-₹62,027.08 (Losses Expanded)** |
| **OOS Max Drawdown %** | **25.21%** | **16.34%** | **-8.87%** |
| **OOS Sharpe Ratio** | **-0.18** | **-1.06** | **-0.88** |
| **OOS Sortino Ratio** | **-0.27** | **-0.70** | **-0.43** |
| **Trade Reduction Rate** | 69 Trades | 28 Trades | **-59.4% Trades Filtered** |
| **Experimental Verdict** | — | — | **🔴 REJECTED** |

---

### 1. Hypothesis & Single-Variable Protocol

#### Research Objective
Evaluate whether aligning 1-hour EMA(9/21) crossover signals with the broader macro trend via **Daily EMA 50** eliminates counter-trend whipsaws and improves Out-of-Sample edge.

#### Controlled Single-Variable Formulation
- **Rule**:
  - Long entries permitted only when $\text{Daily Close}_{D-1} > \text{Daily EMA 50}_{D-1}$.
  - Short entries permitted only when $\text{Daily Close}_{D-1} < \text{Daily EMA 50}_{D-1}$.
- **Zero-Lookahead Protection**: All Daily indicator computations strictly reference day $D-1$ confirmed close to prevent look-ahead bias from the unclosed current daily bar.
- **Fixed Parameters**: Fast EMA = 9, Slow EMA = 21, 1-Hour timeframe, next-bar open execution, identical 70/30 chronological split, identical statutory fees, and 0.5-point execution slippage.

---

### 2. Comprehensive Experimental Matrix

All metrics reflect ₹1,000,000 initial capital, 2 contracts (100 quantity), next-bar open execution, and full statutory friction:

| Metric | IS Control (9/21) | IS Treatment (+Daily EMA 50) | IS Delta | OOS Control (9/21) | OOS Treatment (+Daily EMA 50) | OOS Delta |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Total Trades** | 129 | 53 | -76 (-58.9%) | 69 | 28 | **-41 (-59.4%)** |
| **Net P&L (₹)** | +₹469,797.94 | +₹98,283.59 | -₹371,514.35 | -₹36,228.98 | -₹98,256.06 | **-₹62,027.08** |
| **Profit Factor** | 1.33 | 1.18 | -0.15 | 0.96 | 0.69 | **-0.27** |
| **Win Rate %** | 40.31% | 39.62% | -0.69% | 33.33% | 35.71% | **+2.38%** |
| **Expectancy (₹/Trade)**| +₹3,641.84 | +₹1,854.41 | -₹1,787.43 | -₹525.06 | -₹3,509.15 | **-₹2,984.09** |
| **Max Drawdown (₹)** | ₹326,670.41 | ₹196,410.00 | -₹130,260.41 | ₹320,051.44 | ₹178,240.00 | **-₹141,811.44** |
| **Max Drawdown %** | 26.67% | 17.42% | -9.25% | 25.21% | 16.34% | **-8.87%** |
| **Annualized Sharpe** | +0.49 | -0.02 | -0.51 | -0.18 | -1.06 | **-0.88** |
| **Annualized Sortino**| +0.31 | -0.01 | -0.32 | -0.27 | -0.70 | **-0.43** |
| **Recovery Factor** | 1.44 | 0.50 | -0.94 | -0.11 | -0.55 | **-0.44** |
| **Max Loss Streak** | 8 | 5 | -3 | 8 | 5 | **-3** |
| **Long Net P&L (₹)** | +₹478,572.87 | +₹61,079.65 | -₹417,493.22 | -₹69,588.08 | -₹12,853.89 | **+₹56,734.19** |
| **Short Net P&L (₹)**| -₹8,774.92 | +₹37,203.94 | +₹45,978.86 | +₹33,359.10 | -₹85,402.18 | **-₹118,761.28** |

---

### 3. Quantitative Autopsy: Why Daily EMA 50 Alignment Failed

#### A. The Severe Lag of Daily Filters on Intraday Momentum
- Daily EMA 50 takes 50 daily bars (~2.5 months) to adapt to market turning points.
- By the time the Daily Close drops below Daily EMA 50, a significant portion of the correction has already completed. The system then begins taking 1-hour Short crossovers near the bottom of corrective swings right before sharp mean-reverting V-bottom rebounds occur.

#### B. Short-Side Capital Destruction
- In the Out-of-Sample test, Long performance improved (-₹69.6k $\rightarrow$ -₹12.9k), but **Shorts collapsed from +₹33,359.10 down to -₹85,402.18 (-₹118.8k loss)**.
- Forcing short trades during lagging daily downtrend states triggered chronic short traps in the Indian equity index.

---

### 4. Classification & Decision Rule

Under the established research decision framework:

> [!CAUTION]
> ### Verdict: 🔴 REJECTED
> **Rationale**:
> 1. **Severe Out-of-Sample Deterioration**: Profit Factor dropped from 0.96 down to **0.69**, Net losses increased to **-₹98,256.06**, and Sharpe worsened to **-1.06**.
> 2. **Macro Lag Penalty**: 50-day smoothing is too coarse to guide 1-hour intraday execution, creating severe lag at regime inflection points.
> 3. **Definitive Rejection**: The Daily EMA 50 higher-timeframe trend filter is rejected for NIFTY 1-hour futures.
