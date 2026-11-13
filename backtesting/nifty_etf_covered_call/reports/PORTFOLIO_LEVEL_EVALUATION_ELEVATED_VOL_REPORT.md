# AGY PORTFOLIO-LEVEL EVALUATION REPORT
## Candidate: Elevated Volatility Gate (ATM IV $\ge 18\%$) Covered Call Overlay vs. Frozen Mechanical Baseline

**Document ID:** AGY-VAL-CC-003  
**Target Candidate:** NIFTY Covered Call with Elevated Volatility Gate (`ATM IV >= 18%`)  
**Primary Benchmark:** Frozen Mechanical Baseline (No IV Filter, Delta 0.30, Target 90%, SL 3.0x, Roll DTE 10)  
**Historical Horizon:** Feb 2019 – Sep 2026 (1,264,462 contracts, 1,864 trading days, 7.56 calendar years)  
**Research Scope:** Strictly confined within `~/backtesting/covered call/`  
**Date:** October 12, 2026  
**Final Decision Gate Recommendation:** **INCONCLUSIVE (SPECIALTY TACTICAL OVERLAY — NOT VALIDATED AS REPLACEMENT BASELINE)**

---

## 1. Executive Summary & Audit Verdict

A rigorous, portfolio-level evaluation of the **Elevated Volatility Gate (`ATM IV >= 18%`)** covered call overlay was conducted against the **Frozen Mechanical Baseline**. The analysis evaluates the strategy under identical starting capital (₹15,00,000), identical calendar horizons (2019–2026), true daily mark-to-market (MTM) NAV curves, and dual idle cash assumptions (0.0% zero cash return vs. 4.8% net liquid fund yield).

### Key Portfolio Findings:
1. **Underlying Reproduction:**
   * **Mechanical Baseline:** 118 trades | ₹10,13,946.09 net PnL | 7.07% calendar CAGR (zero cash) / 8.51% (with liquid yield) | 5.69% daily MTM max DD | 71.8% exposure.
   * **ATM IV $\ge 18\%$ Candidate:** 47 trades | ₹6,11,265.39 net PnL | 4.62% calendar CAGR (zero cash) / 7.22% (with liquid yield) | 3.34% daily MTM max DD | 27.6% exposure.
2. **Audit of the Two-Trade Final Holdout (2025–2026):**
   * Across the 415 trading days of the final holdout, the candidate triggered exactly **two trades** (May 8 – May 26, 2025, +₹47,489; May 27 – June 16, 2025, +₹19,331).
   * **Critical Statistical Caveat:** $N = 2$ trades is **statistically uninformative** ($t$-statistic undefined, standard error infinite). It proves that the filter did not trigger false entries during 2025's lower-volatility conditions, but **it does not establish forward out-of-sample edge**. Furthermore, 5/5 positive rolling walk-forward test windows reflect positive market drift across train/test splits rather than structural proof of generalization across unseen regimes.
3. **Rigorous Stress Mechanics (Option Delta/Gamma Correction):**
   * In earlier naive stress models, gap shocks were subtracted directly from deployed capital without accounting for the short option's delta hedge.
   * Under first-principles position repricing: with short call delta $\Delta \approx 0.30$, the net position delta is $\Delta_{net} = 1.0 - 0.30 = 0.70$. A -1.5% overnight gap drops spot by 1.5%, but the short call decays/collapses by ~0.45%, offsetting 30% of the loss.
   * Under rigorous position repricing, the candidate survives a -1.5% overnight shock with **+₹1,43,438 net profit (57.4% win rate)**, rather than turning negative.
4. **Capital Allocation & Portfolio Combination Constraint:**
   * Because the candidate is a strict conditional subset of the baseline, running both concurrently on the same underlying NIFTY without dedicated capital partitions would create overlapping positions (17 overlapping trades), requiring ~₹17L margin and introducing uncontrolled leverage.
5. **Verdict:** **INCONCLUSIVE**. The candidate is a robust risk-reduction tool for tactical volatility harvesting, but its significant surrender of rupee alpha (-39.7% vs. baseline) precludes it from replacing the baseline.

---

## 2. Comparative Portfolio Matrix (Identical Capital & Daily MTM)

Both strategies start with **₹15,00,000 initial capital** on 2019-02-11 and run continuously through 2026-09-04 (7.56 calendar years):

| Portfolio Dimension | Frozen Mechanical Baseline | Candidate (ATM IV $\ge 18\%$) | Comparison / Delta |
| :--- | :---: | :---: | :---: |
| **Trade Count** | 118 | **47** | -71 trades (-60.2%) |
| **Win Rate** | 69.5% | **72.3%** | +2.8% |
| **Net Realized Trade PnL** | **₹10,13,946.09** | **₹6,11,265.39** | **-₹4,02,680.70 (-39.7%)** |
| **Market Exposure (% Days)** | 71.8% | **27.6%** | -44.2% (Low market presence) |
| **Average Margin Deployed** | ₹10,69,450.00 | ₹9,48,310.00 | -₹1,21,140.00 |
| **Worst Single Trade PnL** | -₹75,043.10 (-4.49%) | **-₹41,534.37 (-4.40%)** | +₹33,508.73 (+44.7% better) |
| **Daily MTM Max Drawdown** | 5.69% | **3.34%** | **-2.35% (Superior preservation)** |
| **Bootstrap Median Sharpe** | 1.08 [0.55, 1.62] | **1.35 [0.68, 2.15]** | +0.27 (Higher per-trade Sharpe) |
| **Profit Factor** | 2.51 | **3.93** | +1.42 |
| **Return on Deployed Capital (Ann.)**| 12.54% | **8.53%** | -4.01% |
| **Return on Total Capital (Ann.)** | 8.94% | **5.39%** | -3.55% |
| --- | --- | --- | --- |
| **A. ZERO CASH RETURN (0.0% on Idle Margin)** | | | |
| **Final Portfolio NAV** | **₹25,13,946.09** | **₹21,11,265.39** | -₹4,02,680.70 |
| **Calendar CAGR** | **7.07% p.a.** | **4.62% p.a.** | **-2.45% p.a.** |
| --- | --- | --- | --- |
| **B. REALISTIC LIQUID YIELD (4.8% Net on Idle Margin)** | | | |
| **Cumulative Interest Income** | ₹2,67,678.09 | **₹4,30,000.42** | +₹1,62,322.33 |
| **Final Portfolio NAV** | **₹27,81,624.18** | **₹25,41,265.81** | -₹2,40,358.37 |
| **Calendar CAGR** | **8.51% p.a.** | **7.22% p.a.** | **-1.29% p.a.** |
| **Daily MTM Max Drawdown** | 4.47% | **2.62%** | **-1.85%** |

---

## 3. Idle Cash Modeling & Benchmark Realism

### Benchmark Specification & Taxation:
1. **Instrument:** Indian Institutional Liquid Mutual Funds / Liquid ETFs (e.g. Nippon India Liquid BeES, ABSL Liquid Fund).
2. **Gross Return:** 6.25%–6.40% p.a. (tracking prevailing overnight TREPS / RBI Repo corridor).
3. **Frictional Drag:** Total Expense Ratio (TER) ~0.15%–0.25%, tracking error ~0.05%.
4. **Tax Treatment (Finance Act 2023):** Under Section 50AA, specified mutual funds (debt/liquid funds with $\le 35\%$ equity) no longer receive indexation benefits and are taxed at the investor's marginal slab rate. Assuming a corporate / high-slab entity (25%–30% effective tax rate), the net post-tax, post-expense yield is **4.80% p.a.**
5. **Impact on Portfolio:**
   * Because the **ATM IV $\ge 18\%$** candidate is uninvested 72.4% of the time, sweeping idle cash into liquid instruments adds **₹4,30,000.42** in cumulative interest, lifting its CAGR from **4.62% to 7.22%** and suppressing daily drawdown to **2.62%**.
   * However, sweeping idle cash for the **Mechanical Baseline** also lifts its CAGR from **7.07% to 8.51%** (generating ₹2,67,678 in interest). The baseline retains a **+1.29% p.a. CAGR lead** under identical cash management.

---

## 4. Rigorous Adverse Stress Testing & Option Repricing Mechanics

### Correcting the Stress Testing Methodology:
In earlier audits, adverse gap moves were applied as a flat percentage loss against total capital, ignoring option sensitivity. Below, we document and execute the **first-principles position repricing**:

$$\Delta_{net} = \Delta_{spot} - \Delta_{call} \approx 1.0 - 0.30 = 0.70$$

When a sudden overnight gap occurs:
1. **Spot Leg:** Drops by $\Delta S = \text{Gap \%} \times S_0 \times \text{Lot}$.
2. **Short Option Leg:** Revalues by $\Delta C \approx \Delta \times \Delta S + \frac{1}{2}\Gamma (\Delta S)^2$. As spot drops, the call option price falls, providing a cash gain to the short seller that cushions the loss by ~30%.
3. **Execution Slippage:** Stop-loss exits cross the bid-ask spread with a full slippage penalty.

| Stress Scenario | Applied Repricing Model | Stressed Net PnL (₹) | PnL Deterioration | Stressed Win Rate | Worst Single Trade (₹) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Base Realized** | Historical fills | **₹6,11,265.39** | **0.0%** | **72.3%** | **-₹41,534.37** |
| **2x Adverse Slippage** | Doubled spread penalty | ₹6,08,315.39 | -0.5% | 72.3% | -₹41,609.37 |
| **3x Severe Slippage** | Illiquid OTM spread (3x) | ₹6,05,365.39 | -1.0% | 72.3% | -₹41,684.37 |
| **Sharp Rally (+2.0% Gap)** | Gap into short call delta | ₹5,55,237.59 | -9.2% | 72.3% | -₹41,534.37 |
| **-1.5% Overnight Gap (Repriced)**| Net delta 0.70 shock | **₹1,43,438.14** | **-76.5%** | **57.4%** | **-₹53,003.09** |
| *-1.5% Gap (Naive Spot Model)* | Unhedged underlying drop | *-₹57,059.23* | *-109.3%* | *51.1%* | *-₹57,918.25* |
| **-3.0% Tail Shock (Repriced)** | Net delta 0.70 on stop losses | **₹4,93,607.00** | **-19.2%** | **70.2%** | **-₹41,534.37** |
| *-3.0% Tail Shock (Naive Model)*| Unhedged 3% loss on stops | *-₹7,25,383.85* | *-218.7%* | *29.8%* | *-₹74,302.13* |

**Finding:** Accounting for the short call delta cushion confirms that the strategy remains solidly net profitable (+₹1,43,438) even if every single entry suffers an immediate -1.5% gap down.

---

## 5. Audit of the Holdout (2025–2026) & Walk-Forward Generalization

```
+-----------------------------------------------------------------------------------------+
|                  CHRONOLOGICAL PARTITIONS & HOLDOUT AUDIT                               |
+--------------------------+-----------------------+--------+----------+------------------+
| Partition                | Date Range            | Trades | Win Rate | Net PnL (₹)      |
+--------------------------+-----------------------+--------+----------+------------------+
| In-Sample (IS)           | 2019-02-11 to 2022-12 |   37   |  73.0%   |   ₹4,75,600.65   |
| Out-of-Sample (OOS)      | 2023-01-02 to 2024-12 |    8   |  62.5%   |     ₹68,845.49   |
| Final Holdout (Untouched)| 2025-01-01 to 2026-09 |    2   | 100.0%   |     ₹66,819.25   |
+--------------------------+-----------------------+--------+----------+------------------+
```

### Statistical Disclosures:
1. **Two-Trade Holdout Limitation:** The final holdout produced exactly 2 trades across 20 months. While both trades were profitable (+₹47,489 and +₹19,331), **a sample of $N = 2$ carries zero statistical significance**. It is impossible to compute a meaningful Sharpe ratio, confidence interval, or profit factor on 2 observations.
2. **Walk-Forward Generalization Caution:** Although all 5 rolling walk-forward test periods generated positive PnL, this must not be misconstrued as conclusive mathematical proof of generalization. During 2019–2026, the Indian equity market was in a structural multi-year uptrend. High-IV episodes during this macro regime predominantly resolved via mean reversion and volatility collapse, which naturally flatters short-call structures.

---

## 6. Combined Portfolio Analysis & Capital Constraints

We examined whether the Baseline and ATM IV $\ge$ 18% candidate could be combined into a multi-sleeve portfolio:
1. **Position Overlap:** The candidate is a conditional filter on the baseline. Of the candidate's 47 trades, 17 coincide on the exact same entry dates as baseline trades.
2. **Capital Doubling Hazard:** Operating both concurrently with standard lot sizing would demand **₹17,00,000 to ₹18,00,000 in peak margin**, violating the fixed ₹15,00,000 capital constraint or requiring 1.2x financial leverage.
3. **Partitioned Capital (50/50 Allocation):** If ₹7,50,000 is allocated to Baseline and ₹7,50,000 to Candidate, neither sleeve has enough capital to meet standard exchange margin requirements (~₹8.5L–₹11L per NIFTY lot) without using fractional contracts or index mini-lots, which do not exist in the Indian market.
4. **Conclusion:** They cannot be run simultaneously on the same underlying account. They are mutually exclusive operating modes.

---

## 7. Decision Gate Checklist & Final Recommendation

| Portfolio Evaluation Criterion | Audit Requirement | Observed Result | Status |
| :--- | :--- | :---: | :---: |
| **1. Numerical Reproduction** | Exact reproduction of ledgers and MTM curves | Verified | **PASS** |
| **2. Holdout Disclosure** | Explicit disclosure of $N=2$ holdout limit | Documented | **PASS** |
| **3. Rigorous Stress Modeling** | First-principles option delta/gamma repricing | Implemented | **PASS** |
| **4. Dual Cash Benchmark Modeling**| Model 0.0% and realistic net liquid yield | Modeled | **PASS** |
| **5. Drawdown Protection** | Lower maximum drawdown vs. baseline | 3.34% vs 5.69% | **PASS** |
| **6. Capital Growth & Rupee Total**| Deliver superior absolute returns vs baseline | -39.7% Rupee PnL | **FAIL ❌** |
| **7. Multi-Sleeve Compatibility** | Combine without leverage or margin breach | Overlaps / Mutually exclusive | **FAIL ❌** |

---

### Final Classification: **INCONCLUSIVE (TACTICAL VOLATILITY OVERLAY)**

### Formal Recommendation:
1. **Do NOT Promote as Primary Replacement:** The **Frozen Mechanical Baseline (No IV Filter)** remains the primary, production-grade strategy. It produces **₹10,13,946 net profit** and an **8.51% CAGR (with liquid yield)** versus the candidate's **₹6,11,265 net profit** and **7.22% CAGR**.
2. **Retain for Specialty Mandates:** The **ATM IV $\ge$ 18%** candidate is validated solely as a **tactical overlay** for capital that demands strict drawdown ceilings ($\le 3.5\%$) and maintains an institutional cash-management desk to harvest liquid returns during inactive periods.
3. **Hard Stop Adherence:** No live orders, broker connections, parameter modifications, or paper trading processes have been initiated.

*All reproducibility artifacts, daily curves, and matrices are preserved in `~/backtesting/covered call/validation/` and reports in `~/backtesting/covered call/reports/`.*
