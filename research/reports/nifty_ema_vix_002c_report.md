# NIFTY F&O Quantitative Research Report — Experiment 002C: EMA + India VIX Regime Filter

---

### Executive Summary

| Parameter | Control (Baseline) | Treatment (India VIX Gate) | Delta / Change |
| :--- | :---: | :---: | :---: |
| **Strategy Configuration** | **EMA (9/21)** | **EMA (9/21) + India VIX ($12.0 \le \text{VIX} \le 22.0$)** | Static Volatility Regime Filter |
| **Asset / Universe** | NIFTY Index Futures (`FUTIDX-NIFTY`) | NIFTY Index Futures (`FUTIDX-NIFTY`) | Identical 1-Hour dataset (5,057 bars) |
| **In-Sample Period (70%)** | 2023-09-20 to 2025-10-09 | 2023-09-20 to 2025-10-09 | 3,539 bars |
| **Out-of-Sample Period (30%)** | 2025-10-09 to 2026-08-31 | 2025-10-09 to 2026-08-31 | 1,518 bars |
| **Execution Protocol** | Next-Bar Open, Zero Look-ahead | Next-Bar Open, Zero Look-ahead | Identical statutory costs + slippage |
| **In-Sample Profit Factor** | **1.33** | **1.31** | **-0.02** |
| **In-Sample Net P&L (₹)** | **+₹469,797.94** | **+₹345,987.51** | **-₹123,810.43** |
| **Out-of-Sample Profit Factor** | **0.96** | **0.76** | **-0.20 (Severe OOS Degradation)** |
| **OOS Net P&L (₹)** | **-₹36,228.98** | **-₹154,540.86** | **-₹118,311.88 (Loss Quadrupled)** |
| **OOS Max Drawdown %** | **25.21%** | **32.18%** | **+6.97% (Worse Tail Risk)** |
| **OOS Sharpe Ratio** | **-0.18** | **-0.62** | **-0.44** |
| **OOS Sortino Ratio** | **-0.27** | **-0.72** | **-0.45** |
| **Trade Reduction Rate** | 69 Trades | 46 Trades | **-33.3% Trades Filtered** |
| **Experimental Verdict** | — | — | **🔴 REJECTED** |

---

### 1. Hypothesis & Single-Variable Protocol

#### Research Objective
Evaluate whether gating EMA(9/21) crossover entries with a static India VIX band ($12.0 \le \text{India VIX} \le 22.0$) prevents entering during low-volatility dead chop ($\text{VIX} < 12$) and high-volatility panic whipsaws ($\text{VIX} > 22$).

#### Controlled Single-Variable Formulation
- **Fixed Parameters**: Fast EMA = 9, Slow EMA = 21, 1-Hour timeframe, Long + Short.
- **Entry Gate**: Crossover entry is permitted *if and only if* $12.0 \le \text{India VIX} \le 22.0$ on the closed signal bar $t$.
- **Exit Rule**: Exit occurs on standard opposite EMA crossover.
- **Strict Controls**: Identical 70/30 chronological split, identical statutory fees, and 0.5-point execution slippage per leg.

---

### 2. Comprehensive Experimental Matrix

All metrics reflect ₹1,000,000 initial capital, 2 contracts (100 quantity), next-bar open execution, and full statutory friction:

| Metric | IS Control (9/21) | IS Treatment (+VIX) | IS Delta | OOS Control (9/21) | OOS Treatment (+VIX) | OOS Delta |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Total Trades** | 129 | 103 | -26 (-20.2%) | 69 | 46 | **-23 (-33.3%)** |
| **Net P&L (₹)** | +₹469,797.94 | +₹345,987.51 | -₹123,810.43 | -₹36,228.98 | -₹154,540.86 | **-₹118,311.88** |
| **Profit Factor** | 1.33 | 1.31 | -0.02 | 0.96 | 0.76 | **-0.20** |
| **Win Rate %** | 40.31% | 39.81% | -0.50% | 33.33% | 28.26% | **-5.07%** |
| **Expectancy (₹/Trade)**| +₹3,641.84 | +₹3,359.10 | -₹282.74 | -₹525.06 | -₹3,359.58 | **-₹2,834.52** |
| **Max Drawdown (₹)** | ₹326,670.41 | ₹209,420.00 | -₹117,250.41 | ₹320,051.44 | ₹388,410.00 | **+₹68,358.56** |
| **Max Drawdown %** | 26.67% | 18.50% | -8.17% | 25.21% | 32.18% | **+6.97%** |
| **Annualized Sharpe** | +0.49 | +0.38 | -0.11 | -0.18 | -0.62 | **-0.44** |
| **Annualized Sortino**| +0.31 | +0.21 | -0.10 | -0.27 | -0.72 | **-0.45** |
| **Recovery Factor** | 1.44 | 1.65 | +0.21 | -0.11 | -0.40 | **-0.29** |
| **Max Loss Streak** | 8 | 8 | 0 | 8 | 8 | **0** |
| **Long Net P&L (₹)** | +₹478,572.87 | +₹374,210.15 | -₹104,362.72 | -₹69,588.08 | -₹121,450.40 | **-₹51,862.32** |
| **Short Net P&L (₹)**| -₹8,774.92 | -₹28,222.64 | -₹19,447.72 | +₹33,359.10 | -₹33,090.46 | **-₹66,449.56** |

---

### 3. Quantitative Autopsy: Why Static India VIX Failed

#### A. Regime Drift & Low-VIX Bull Runs
- In the 2025–2026 Out-of-Sample period, Indian equity markets experienced extended low-volatility grinding bull advances where India VIX routinely hovered between **9.5 and 11.8**.
- The static threshold ($VIX \ge 12$) locked the strategy out of these orderly trend advances.

#### B. Adverse Selection ("The VIX Trap")
- The filter only permitted entries when India VIX rose above 12.0. However, in low-volatility bull regimes, VIX rises above 12 primarily during sharp, temporary mean-reverting pullbacks.
- Consequently, the strategy was selectively triggered into choppy, unstable pullbacks right before they reversed, while completely missing the smooth upward legs.

---

### 4. Classification & Decision Rule

Under the established research decision framework:

> [!CAUTION]
> ### Verdict: 🔴 REJECTED
> **Rationale**:
> 1. **Catastrophic OOS Degradation**: The India VIX filter exacerbated Out-of-Sample losses by **+₹118,311.88** (Net P&L collapsed to -₹154.5k), drove the Profit Factor down to **0.76**, and widened Max Drawdown to **32.18%**.
> 2. **Static Threshold Failure**: Absolute macro volatility levels drift over multi-year cycles. Static absolute bounds ($12 \le \text{VIX} \le 22$) cause severe adverse selection.
> 3. **Definitive Rejection**: The India VIX absolute level filter is permanently rejected for 1-hour intraday momentum gating.
