# NIFTY F&O Quantitative Research Report — Experiment 003: EMA 9/26 Baseline

---

### Executive Summary

| Parameter | Control (EMA 9/21) | Treatment (EMA 9/26) | Delta / Change |
| :--- | :---: | :---: | :---: |
| **Strategy Configuration** | **EMA Fast (9) / Slow (21)** | **EMA Fast (9) / Slow (26)** | Slow period shifted $21 \rightarrow 26$ |
| **Asset / Universe** | NIFTY Index Futures (`FUTIDX-NIFTY`) | NIFTY Index Futures (`FUTIDX-NIFTY`) | Identical 1-Hour dataset (5,057 bars) |
| **In-Sample Period (70%)** | 2023-09-20 to 2025-10-09 | 2023-09-20 to 2025-10-09 | 3,539 bars |
| **Out-of-Sample Period (30%)** | 2025-10-09 to 2026-08-31 | 2025-10-09 to 2026-08-31 | 1,518 bars |
| **Execution Protocol** | Next-Bar Open, Zero Look-ahead | Next-Bar Open, Zero Look-ahead | Identical statutory costs + slippage |
| **In-Sample Profit Factor** | **1.33** | **1.44** | **+0.11 (Higher Trend Holding)** |
| **In-Sample Net P&L (₹)** | **+₹469,797.94** | **+₹547,652.63** | **+₹77,854.69** |
| **Out-of-Sample Profit Factor** | **0.96** | **0.98** | **+0.02 (Remains Sub-1.0)** |
| **OOS Net P&L (₹)** | **-₹36,228.98** | **-₹14,442.42** | **+₹21,786.56 (Loss Reduced)** |
| **OOS Max Drawdown %** | **25.21%** | **22.65%** | **-2.56% (Slight Drawdown Reduction)** |
| **OOS Sharpe Ratio** | **-0.18** | **-0.11** | **+0.07 (Remains Negative)** |
| **OOS Sortino Ratio** | **-0.27** | **-0.16** | **+0.11** |
| **Trade Count Reduction** | 69 Trades | 59 Trades | **-14.5% Trades Filtered** |
| **Experimental Verdict** | — | — | **🔴 REJECTED (As Standalone Edge)** |

---

### 1. Hypothesis & Single-Variable Formulation

#### Research Objective
Evaluate whether widening the slow EMA period from 21 to 26 (the standard Ichimoku Kijun / MACD slow baseline) provides sufficient trend smoothing to eliminate false breakouts on NIFTY 1-hour futures without any secondary indicator filters.

#### Controlled Parameters
- **Changed Variable**: Slow EMA period shifted from **21 to 26**.
- **Fixed Parameters**: Fast EMA = 9, 1-Hour timeframe, Long + Short, closed candle evaluation with next-bar open execution.
- **Controls**: Zero additional indicator filters (No ADX, No ATR, No VIX, No session rules), identical 70/30 chronological split, identical statutory fees, and 0.5-point execution slippage.

---

### 2. Comprehensive Experimental Matrix

All metrics reflect ₹1,000,000 initial capital, 2 contracts (100 quantity), next-bar open execution, and full statutory friction:

| Metric | IS Control (9/21) | IS Treatment (9/26) | IS Delta | OOS Control (9/21) | OOS Treatment (9/26) | OOS Delta |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Total Trades** | 129 | 115 | -14 (-10.9%) | 69 | 59 | **-10 (-14.5%)** |
| **Net P&L (₹)** | +₹469,797.94 | +₹547,652.63 | +₹77,854.69 | -₹36,228.98 | -₹14,442.42 | **+₹21,786.56** |
| **Profit Factor** | 1.33 | 1.44 | +0.11 | 0.96 | 0.98 | **+0.02** |
| **Win Rate %** | 40.31% | 42.61% | +2.30% | 33.33% | 27.12% | **-6.21%** |
| **Expectancy (₹/Trade)**| +₹3,641.84 | +₹4,762.20 | +₹1,120.36 | -₹525.06 | -₹244.79 | **+₹280.27** |
| **Max Drawdown (₹)** | ₹326,670.41 | ₹337,420.10 | +₹10,749.69 | ₹320,051.44 | ₹274,380.00 | **-₹45,671.44** |
| **Max Drawdown %** | 26.67% | 27.27% | +0.60% | 25.21% | 22.65% | **-2.56%** |
| **Annualized Sharpe** | +0.49 | +0.58 | +0.09 | -0.18 | -0.11 | **+0.07** |
| **Annualized Sortino**| +0.31 | +0.33 | +0.02 | -0.27 | -0.16 | **+0.11** |
| **Long Net P&L (₹)** | +₹478,572.87 | +₹515,450.13 | +₹36,877.26 | -₹69,588.08 | -₹58,694.80 | **+₹10,893.28** |
| **Short Net P&L (₹)**| -₹8,774.92 | +₹32,202.51 | +₹40,977.43 | +₹33,359.10 | +₹44,252.38 | **+₹10,893.28** |

---

### 3. Monthly Out-of-Sample Performance Breakdown (Oct 2025 to Aug 2026)

| Month | Control (9/21) Net P&L | Treatment (9/26) Net P&L | Delta | Market Regime Dynamics |
| :--- | :---: | :---: | :---: | :--- |
| **2025-10** | +₹33,526.35 | +₹32,211.60 | -₹1,314.75 | Mild trending drift |
| **2025-11** | +₹19,052.30 | +₹20,827.27 | +₹1,774.98 | Low volatility continuation |
| **2025-12** | -₹75,363.94 | -₹71,184.12 | +₹4,179.82 | Range-bound consolidation |
| **2026-01** | +₹62,722.43 | +₹81,673.54 | +₹18,951.11 | Strong trend expansion |
| **2026-02** | -₹4,585.19 | -₹36,723.29 | -₹32,138.10 | Sharp counter-trend pullback |
| **2026-03** | +₹97,564.34 | +₹64,102.13 | -₹33,462.21 | Moderate recovery trend |
| **2026-04** | +₹78,885.67 | +₹78,023.24 | -₹862.42 | Bull continuation |
| **2026-05** | -₹241,667.63 | -₹206,864.64 | +₹34,803.00 | Severe whipsaw chop channel |
| **2026-06** | -₹12,146.60 | -₹1,148.84 | +₹10,997.76 | Sideways consolidation |
| **2026-07** | +₹5,831.41 | +₹3,771.82 | -₹2,059.59 | Narrow channel grind |
| **2026-08** | -₹48.11 | +₹20,868.85 | +₹20,916.96 | Modest breakout capture |

---

### 4. Quantitative Evaluation & Comparative Analysis

#### A. In-Sample vs Out-of-Sample Divergence
- **In-Sample Success**: EMA 9/26 improved In-Sample P&L (+₹77.8k, PF 1.33 $\rightarrow$ 1.44) by allowing winning trades to ride longer trends without prematurely flipping on minor 1-hour noise.
- **Out-of-Sample Failure**: In the choppy Out-of-Sample regime, simply changing the slow period from 21 to 26 was **insufficient to prevent negative expectancy** (Net P&L: -₹14,442.42, PF: 0.98, Sharpe: -0.11).

#### B. The Core Quantitative Takeaway
Adjusting moving average periods alone (parameter tuning within the same unconditioned indicator class) cannot solve regime vulnerability. Without an external volatility or regime filter (such as the ATR Volatility Expansion mechanism validated in 002B), raw crossover systems inevitably bleed capital during consolidating market phases.

---

### 5. Classification & Decision Rule

Under the established research decision framework:

> [!CAUTION]
> ### Verdict: 🔴 REJECTED (As a Standalone Baseline)
> **Rationale**:
> 1. **Persistent Negative OOS Expectancy**: Out-of-Sample Net P&L remains negative (-₹14,442.42) and Profit Factor remains below 1.0 (0.98), failing the requirement for positive standalone robustness.
> 2. **In-Sample Bias**: The improvement occurred primarily on In-Sample trending data (+₹77.8k) but failed to hold up out-of-sample without a volatility gate.
> 3. **Next Step**: While rejected as a standalone unconditioned strategy, EMA 9/26 provides slightly superior trend smoothing over 9/21 and is a prime candidate to test in combination with the validated **ATR Volatility Expansion filter (003B: EMA 9/26 + ATR)**.
