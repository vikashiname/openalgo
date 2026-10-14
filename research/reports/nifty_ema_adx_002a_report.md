# NIFTY F&O Quantitative Research Report — Experiment 002A: EMA + ADX Filter

---

### Executive Summary

| Parameter | Control (Baseline) | Treatment (ADX Filter) | Delta / Change |
| :--- | :---: | :---: | :---: |
| **Strategy Configuration** | **EMA (9/21)** | **EMA (9/21) + ADX(14) > 22** | Single-variable entry gate |
| **Asset / Universe** | NIFTY Index Futures (`FUTIDX-NIFTY`) | NIFTY Index Futures (`FUTIDX-NIFTY`) | Identical 1-Hour dataset (5,057 bars) |
| **In-Sample Period (70%)** | 2023-09-20 to 2025-10-09 | 2023-09-20 to 2025-10-09 | 3,539 bars |
| **Out-of-Sample Period (30%)** | 2025-10-09 to 2026-08-31 | 2025-10-09 to 2026-08-31 | 1,518 bars |
| **Execution Protocol** | Next-Bar Open, Zero Look-ahead | Next-Bar Open, Zero Look-ahead | Identical statutory costs + slippage |
| **In-Sample Profit Factor** | **1.33** | **1.08** | **-0.25 (Lag Penalty)** |
| **Out-of-Sample Profit Factor** | **0.96** | **1.12** | **+0.16 (Whipsaw Reduction)** |
| **OOS Net P&L (₹)** | **-₹36,228.98** | **+₹48,825.63** | **+₹85,054.61** |
| **OOS Max Drawdown %** | **25.21%** | **20.03%** | **-5.18% (Lower Risk)** |
| **OOS Sharpe Ratio** | **-0.18** | **+0.05** | **+0.23** |
| **Trade Reduction Rate** | 69 Trades | 33 Trades | **-52.2% Trade Count Filtered** |
| **Experimental Verdict** | — | — | **🟡 INCONCLUSIVE** |

---

### 1. Hypothesis & Experimental Integrity

#### Research Objective
Evaluate whether gating EMA(9/21) crossover entries with a strict trend-strength filter (`ADX(14) > 22`) resolves the out-of-sample breakdown identified in Experiment 001 without introducing curve-fitting.

#### Controlled Single-Variable Protocol
- **Fixed Parameters**: Fast EMA = 9, Slow EMA = 21, ADX Window = 14, ADX Threshold = 22.0.
- **Entry Gate**: Crossover entry is permitted *if and only if* $ADX(14) > 22$ on the closed signal bar.
- **Exit Rule**: Position is exited on standard opposite EMA crossover (trend termination).
- **Strict Controls**: Zero parameter tuning on ADX threshold, identical 70/30 chronological split, identical statutory fees, and 0.5-point execution slippage.

---

### 2. Comprehensive Experimental Matrix

All metrics reflect ₹1,000,000 initial capital, 2 contracts (100 quantity), next-bar open execution, and full statutory friction:

| Metric | IS Control (9/21) | IS Treatment (+ADX) | IS Delta | OOS Control (9/21) | OOS Treatment (+ADX) | OOS Delta |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Total Trades** | 129 | 62 | -67 (-51.9%) | 69 | 33 | **-36 (-52.2%)** |
| **Net P&L (₹)** | +₹469,797.94 | +₹70,824.22 | -₹398,973.72 | -₹36,228.98 | +₹48,825.63 | **+₹85,054.61** |
| **Profit Factor** | 1.33 | 1.08 | -0.25 | 0.96 | 1.12 | **+0.16** |
| **Win Rate %** | 40.31% | 43.55% | +3.24% | 33.33% | 33.33% | **+0.00%** |
| **Expectancy (₹/Trade)**| +₹3,641.84 | +₹1,142.33 | -₹2,499.51 | -₹525.06 | +₹1,479.56 | **+₹2,004.62** |
| **Max Drawdown (₹)** | ₹326,670.41 | ₹337,562.90 | +₹10,892.49 | ₹320,051.44 | ₹209,720.00 | **-₹110,331.44** |
| **Max Drawdown %** | 26.67% | 31.06% | +4.39% | 25.21% | 20.03% | **-5.18%** |
| **Annualized Sharpe** | +0.49 | -0.00 | -0.49 | -0.18 | +0.05 | **+0.23** |
| **Annualized Sortino**| +0.31 | -0.00 | -0.31 | -0.27 | +0.05 | **+0.32** |
| **Recovery Factor** | 1.44 | 0.21 | -1.23 | -0.11 | 0.23 | **+0.34** |
| **Max Loss Streak** | 8 | 7 | -1 | 8 | 5 | **-3** |
| **Long Net P&L (₹)** | +₹440,942.09 | +₹102,410.15 | -₹338,531.94 | -₹69,588.08 | +₹24,190.45 | **+₹93,778.53** |
| **Short Net P&L (₹)**| +₹28,855.85 | -₹31,585.93 | -₹60,441.78 | +₹33,359.10 | +₹24,635.18 | **-₹8,723.92** |

---

### 3. In-Depth Quantitative Analysis

#### A. Trade Filtering & Whipsaw Reduction
- The ADX filter filtered out **52.2% of all crossover signals** in the Out-of-Sample test (from 69 down to 33 trades).
- In the consolidating/range-bound OOS market, eliminating 36 low-momentum crossovers successfully prevented consecutive false-breakout losses.

#### B. The Entry Lag Trade-Off (The "ADX Tax")
- In-Sample Net P&L suffered an **84.9% reduction** (from +₹469.8k down to +₹70.8k, PF down from 1.33 to 1.08).
- **Cause**: ADX is a lagging, smoothed trend-strength indicator. By waiting for $ADX > 22$, the system enters trades several bars late, missing the most profitable early momentum phase of legitimate trend expansions.

#### C. Out-of-Sample Economic Significance
- While OOS Net P&L shifted from negative (-₹36.2k) to positive (+₹48.8k), the resulting **OOS Profit Factor (1.12)** and **Sharpe (0.05)** remain modest and fragile.
- Generating ₹48,825 net on ₹1,000,000 capital over 11 months across 33 trades represents an annualized return of ~5.3% (below the risk-free rate).

---

### 4. Classification & Decision Rule

Under the established research protocol:

> [!WARNING]
> ### Verdict: 🟡 INCONCLUSIVE
> **Rationale**:
> 1. **Positive Signs**: Gating by $ADX > 22$ successfully eliminated 52% of noisy whipsaw trades and lifted OOS Net P&L from negative into positive territory (+₹85k delta, PF 0.96 $\rightarrow$ 1.12, Max DD 25.2% $\rightarrow$ 20.0%).
> 2. **Structural Defect**: The severe entry lag dramatically impairs in-sample trend capture (PF falls from 1.33 to 1.08), and the resulting OOS Sharpe (+0.05) is insufficient to establish a robust standalone edge.
> 3. **Action**: The ADX filter will be retained as an exploratory candidate but is **NOT adopted as a primary standalone fix**. Proceed to subsequent single-variable filter evaluations (ATR, Volatility/VIX, Session Gating).
