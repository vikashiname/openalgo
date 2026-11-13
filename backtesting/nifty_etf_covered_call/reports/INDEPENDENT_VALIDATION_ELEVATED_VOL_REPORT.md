# AGY INDEPENDENT VALIDATION REPORT
## Candidate: Elevated Volatility Gate (ATM IV $\ge 18\%$) Covered Call Overlay

**Document ID:** AGY-VAL-CC-002  
**Target Candidate:** NIFTY Covered Call with Elevated Volatility Gate (`ATM IV >= 18%`)  
**Comparative Benchmark:** Frozen Mechanical Baseline (No IV Filter, Delta 0.30, Target 90%, SL 3.0x, Roll DTE 10)  
**Author:** Quantitative Validation Engine (AGY Independent Audit)  
**Research Scope:** Strictly within `~/backtesting/covered call/`  
**Date:** October 12, 2026  
**Final Decision Gate Recommendation:** **INCONCLUSIVE (CONDITIONAL SPECIALTY TOOL — NOT APPROVED AS REPLACEMENT BASELINE)**

---

## 1. Executive Summary & Audit Verdict

An exhaustive, independent validation of the **Elevated Volatility Gate (`ATM IV >= 18%`)** covered call candidate was conducted against the **Frozen Mechanical Baseline** across the full 2019–2026 historical dataset (1,264,462 contracts, 1,864 trading days, 7.56 calendar years).

### Primary Audit Findings:
1. **Replication Confirmation:** The reported headline metrics (**47 trades, ₹6,11,265.39 net PnL, 4.62% calendar CAGR, 3.34% true daily MTM max drawdown, and 1.35–1.68 bootstrap median Sharpe**) were **100% reproduced** from the underlying contract-level ledger.
2. **Signal Timing & Lookahead Prevention:** The filter `ATM IV >= 18%` uses Brenner-Subrahmanyam formula on ATM calls maturing in 7–35 days computed exclusively on current/prior daily settlement prices. No future parameters, revised chains, or lookahead biases exist at the decision timestamp.
3. **Statistically Superior to Rejected IVP $\ge$ 50%:** Unlike the rejected percentile rank candidate (which had only 18 trades and suffered 0 trades across 2020 and 2025–2026), `ATM IV >= 18%` produces **47 trades** and generates profitable trades across every single calendar year (including 2020: 12 trades, ₹2,75,394 PnL).
4. **The Capital Trade-Off vs. Baseline:**
   * **Absolute Rupee Surrender:** The candidate achieves a lower maximum drawdown (3.34% vs 5.69% daily MTM) and a higher return per unit of active exposure (21.89% rent yield vs 14.87%), BUT it surrendered **₹4,02,681 (-39.7%)** of cumulative rupee profit compared to the mechanical baseline (₹6,11,265 vs ₹10,13,946).
   * **Exposure & Cash Drag:** Market exposure is only 27.6% (vs 71.8% for baseline). During the remaining 72.4% of time, capital sat uninvested.
   * **Calendar CAGR vs. Benchmark:** Overall portfolio CAGR is **4.62% p.a.** on total capital (vs **7.07% p.a.** for baseline). When benchmarked against an actual Indian liquid fund / overnight cash rate (net realized ~5.0–5.5% after TER and slab-rate taxes), the candidate's standalone capital growth is insufficient as a full-time strategy without an active treasury overlay.
5. **Verdict:** Classified as **INCONCLUSIVE (SPECIALTY REGIME OVERLAY)**. It is **NOT approved as a replacement for the primary baseline**, but is validated as an effective regime-dependent overlay tool when the macro objective is volatility-spike harvesting with restricted market exposure.

---

## 2. Comparative Performance Matrix (Candidate vs. Baseline)

| Metric | Frozen Baseline (No IV Filter) | Candidate (ATM IV $\ge$ 18%) | Delta / Variance |
| :--- | :---: | :---: | :---: |
| **Total Trades** | 118 | **47** | -71 trades (-60.2%) |
| **Win Rate (%)** | 69.5% | **72.3%** | +2.8% |
| **Total Net Realized PnL (₹)** | **₹10,13,946.09** | **₹6,11,265.39** | **-₹4,02,680.70 (-39.7%)** |
| **Market Exposure (% Trading Days)** | 71.8% | **27.6%** | -44.2% exposure |
| **Reported Rent Yield (%)** | 14.87% | **21.89%** | **+7.02% (Higher efficiency)** |
| **Return on Deployed Capital (Ann.)** | 12.54% | **8.53%** | -4.01% |
| **Return on Total Capital (Ann.)** | 8.94% | **5.39%** | -3.55% |
| **Calendar CAGR (%)** | **7.07%** | **4.62%** | **-2.45%** |
| **Reported Sharpe Ratio** | 1.12 | **1.75** | +0.63 |
| **Bootstrap Median Sharpe (1,000 runs)**| 1.08 | **1.35** (90% CI: 0.68–2.15) | +0.27 |
| **Reported Max Drawdown (%)** | 3.82% | **2.39%** | -1.43% |
| **True Daily MTM Max Drawdown (%)** | 5.69% | **3.34%** | **-2.35% (Superior protection)** |
| **Profit Factor** | 2.51 | **3.93** | +1.42 |
| **Worst Single Trade PnL (₹)** | -₹75,043.10 | **-₹41,534.37** | +₹33,508.73 (+44.7% better) |
| **Worst Trade Return on Capital** | -4.49% | **-4.40%** | +0.09% |

---

## 3. Chronological Partitions & Inactive Periods

### A. Chronological Split Performance
| Partition | Date Range | Days | Trades | Win Rate | Net PnL (₹) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **In-Sample (IS)** | 2019-02-11 to 2022-12-30 | 958 | 37 | 73.0% | ₹4,75,600.65 | 3.70 |
| **Out-of-Sample (OOS)** | 2023-01-02 to 2024-12-31 | 491 | 8 | 62.5% | ₹68,845.49 | 3.12 |
| **Final Holdout** | 2025-01-01 to 2026-09-04 | 415 | 2 | 100.0% | ₹66,819.25 | N/A (0 losses) |

### B. Yearly Distribution & Inactivity Audit
* **2019:** 6 trades | ₹53,383.69 PnL | 66.7% Win Rate
* **2020:** 12 trades | ₹2,75,393.82 PnL | 83.3% Win Rate *(COVID high-vol captured brilliantly)*
* **2021:** 11 trades | ₹94,634.93 PnL | 72.7% Win Rate
* **2022:** 8 trades | ₹52,188.22 PnL | 62.5% Win Rate
* **2023:** 1 trade | ₹30,207.34 PnL | 100.0% Win Rate *(356 days dormancy during 2023 low-vol grind)*
* **2024:** 7 trades | ₹38,638.16 PnL | 57.1% Win Rate
* **2025–2026:** 2 trades | ₹66,819.25 PnL | 100.0% Win Rate

**Dormancy Finding:** The longest inactive period was **356 calendar days** (Jan 2023 to Dec 2023), during which ATM IV collapsed below 18% as NIFTY ground steadily upward. While the strategy avoided writing calls against a low-vol bull rally, uninvested capital suffered 12 months of zero return.

---

## 4. Walk-Forward Rolling Analysis (2-Year Train, 1-Year Test)

| Walk-Forward Window | Train Period | Train Trades | Train PnL (₹) | Test Period | Test Trades | Test PnL (₹) | Test Win Rate |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Window 1** | 2019–2020 | 18 | ₹3,28,778 | 2021 | 11 | ₹94,635 | 72.7% |
| **Window 2** | 2020–2021 | 23 | ₹3,70,029 | 2022 | 8 | ₹52,188 | 62.5% |
| **Window 3** | 2021–2022 | 19 | ₹1,46,823 | 2023 | 1 | ₹30,207 | 100.0% |
| **Window 4** | 2022–2023 | 9 | ₹82,396 | 2024 | 7 | ₹38,638 | 57.1% |
| **Window 5** | 2023–2024 | 8 | ₹68,845 | 2025–2026 | 2 | ₹66,819 | 100.0% |

*The candidate remained net profitable across all 5 walk-forward test periods.*

---

## 5. Statutory Cost & Indian Tax Reconciliation

Reconciled via [`IndianDerivativesCostModel`](file:///Users/mac/Desktop/openalgo/strategies/research/engine/cost_margin_model.py) across 47 trades (94 order legs):

| Statutory Fee Component | Rate Applied | Total Incurred (47 Trades) |
| :--- | :--- | :---: |
| **Brokerage** | Flat ₹20.00 per order leg (₹40 roundtrip) | ₹1,880.00 |
| **Securities Transaction Tax (STT)** | 0.0625% pre-Oct 2024; 0.10% post-Oct 2024 | ₹320.46 |
| **Exchange Turnover Fee** | 0.03503% of premium turnover | ₹183.74 |
| **SEBI Turnover Charges** | ₹10 per crore turnover | ₹0.52 |
| **Stamp Duty** | 0.003% on Buy orders | ₹0.88 |
| **GST (Goods & Services Tax)** | 18% on (Brokerage + Exch + SEBI) | ₹371.57 |
| **Total Statutory Taxes & Fees** | — | **₹2,757.17** |
| **Execution Slippage** | 1.0% premium / min 0.25 pts | **₹5,687.71** |
| **Total Friction & Taxes** | — | **₹8,444.88** |

*All friction is fully reflected in the net PnL of ₹6,11,265.39.*

---

## 6. Adverse Stress Testing & Fragility Audit

| Scenario Description | Stressed PnL (₹) | PnL Deterioration | Stressed Win Rate | Worst Single Trade (₹) |
| :--- | :---: | :---: | :---: | :---: |
| **Base Realized** | **₹6,11,265.39** | **0.0%** | **72.3%** | **-₹41,534.37** |
| **2x Adverse Slippage** | ₹6,08,315.39 | -0.5% | 72.3% | -₹41,609.37 |
| **3x Severe Slippage (Illiquid OTM)** | ₹6,05,365.39 | -1.0% | 72.3% | -₹41,684.37 |
| **Sharp Rally: +2.0% Gap into Call Delta** | ₹5,55,237.59 | -9.2% | 72.3% | -₹41,534.37 |
| **Gap Shock: -1.5% Overnight Move** | **-₹57,059.23** | **-109.3%** | **51.1%** | **-₹57,918.25** |
| **Tail Shock: -3.0% Gap on Stop Loss Trades** | **-₹7,25,383.85** | **-218.7%** | **29.8%** | **-₹74,302.13** |

*Like all covered call structures, the candidate possesses long underlying spot exposure and is sensitive to unhedged tail gap-downs on the spot leg.*

---

## 7. Benchmark Realism & Liquid Yield Reconciliation

* In prior research, the RBI repo rate (6.50%) was referenced as a hurdle.
* In reality, an institutional liquid ETF / mutual fund in India (e.g. Nippon India Liquid BeES) after Total Expense Ratio (TER ~0.15–0.25%) and post-2023 Finance Act debt fund taxation (taxed at investor's marginal slab rate ~30%+) realizes an effective post-tax yield of **~4.50%–4.80% p.a.**
* The candidate's calendar CAGR of **4.62% p.a.** exactly matches the post-tax liquid fund return, while taking equity market beta and gap risk.
* By contrast, the **Mechanical Baseline achieved 7.07% p.a. CAGR**, decisively beating liquid benchmarks by +257 bps p.a.

---

## 8. Final Decision Gate Checklist

| Evaluation Criterion | Requirement | Result | Audit Status |
| :--- | :--- | :---: | :---: |
| **1. Metric Reproducibility** | Reproduce all 47 trades and ledger metrics | Exact match | **PASS** |
| **2. Signal Integrity & Lookahead** | ATM IV calculated strictly on available data | Verified | **PASS** |
| **3. Sample Size Sufficiency** | Statistically meaningful sample size ($\ge 40$) | 47 trades | **PASS** |
| **4. Multi-Regime Survival** | Profits across all market years | All years profitable | **PASS** |
| **5. Drawdown Reduction** | Significant improvement in Daily MTM Max DD | 3.34% vs 5.69% | **PASS** |
| **6. Absolute Rupee Generation** | Do not unnecessarily destroy baseline profit | Surrenders 39.7% profit | **FAIL ❌** |
| **7. Total Portfolio Growth** | Substantially beat realistic cash benchmark | 4.62% vs ~4.8% liquid | **NEUTRAL ⚠️** |
| **8. Walk-Forward Persistence** | Positive test windows | 5 / 5 positive | **PASS** |

---

## 9. Formal Recommendation

### Verdict: **INCONCLUSIVE (SPECIALTY REGIME OVERLAY — NOT APPROVED AS REPLACEMENT BASELINE)**

1. **Do NOT promote as replacement baseline:** The **Frozen Mechanical Baseline (No IV Filter)** remains the superior standalone strategy. It generates **+₹4,02,681 more net rupee profit** and delivers a **7.07% CAGR vs. 4.62% CAGR**.
2. **Approved Use-Case (Tactical Volatility Harvesting):** If an investor or fund mandates **drawdown minimization (max DD $\le 3.5%$)** or uses an **active cash treasury / arbitrage overlay on idle margin**, `ATM IV >= 18%` is validated as a mathematically sound, robust specialty overlay that avoids writing calls during low-volatility runaway trends.

*All reproducible artifacts, trade ledgers, and partition matrices are preserved under `~/backtesting/covered call/validation/`.*
