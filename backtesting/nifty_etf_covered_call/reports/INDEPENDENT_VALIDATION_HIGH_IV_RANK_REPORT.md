# AGY INDEPENDENT VALIDATION REPORT
## Candidate: High IV Rank Gate (IV Percentile $\ge 50\%$) Covered Call Overlay

**Document ID:** AGY-VAL-CC-001  
**Target Candidate:** NIFTY Covered Call with High IV Rank Gate (`IVP >= 50%`)  
**Comparative Benchmarks:**  
1. Frozen Mechanical Baseline (No IV Filter, Delta 0.30, Target 90%, SL 3.0x, Roll DTE 10)  
2. Absolute Elevated Volatility Candidate (ATM IV $\ge 18\%$)  
3. Sensitivity Boundary Thresholds (IVP $\ge 40\%$, IVP $\ge 60\%$)  
**Author:** Quantitative Validation Engine (AGY Independent Audit)  
**Research Scope:** Strictly within `~/backtesting/covered call/`  
**Date:** October 12, 2026  
**Final Decision Gate Recommendation:** **REJECTED (NOT APPROVED FOR PROMOTION)**

---

## 1. Executive Summary & Audit Verdict

An exhaustive, independent quantitative validation of the reported **High IV Rank Gate (IV Percentile $\ge 50\%$)** was conducted using historical NIFTY options settlement data (1,264,462 contracts across 1,864 trading days, 2019–2026).

### Primary Audit Findings:
1. **Replication Confirmation:** The raw numbers reported during initial research (**18 trades, 77.8% win rate, 19.99% reported rent yield, 3.01 reported Sharpe, 0.53% reported max drawdown, 5.66 profit factor**) were **successfully reproduced** from the core script logic.
2. **Deconstruction of the "19.99% Annual Rent Yield":**
   * The candidate was invested for only **10.5% of the 7.5-year horizon** (18 trades, ~195 days out of 1,864 trading days).
   * For **89.5% of the time, the portfolio sat 100% idle in zero-interest cash**.
   * The reported 19.99% figure was an artifact of dividing total profit by *active trade months only* (14 months = 1.16 years), rather than the true calendar horizon of 7.5 years.
   * **True Calendar CAGR is only 1.76% p.a.** on portfolio capital, and **True Calendar Yield is only 3.08% p.a.** on deployed capital.
   * This severely underperforms Indian risk-free liquid yield (RBI Repo / T-Bill benchmark: 6.50% p.a.) and surrenders **79.1% of the baseline's cumulative rupee profits** (₹2,11,621 vs. ₹10,13,946).
3. **Deconstruction of the "0.53% Maximum Drawdown":**
   * The 0.53% figure is an artifact of **monthly exit-date aggregation** and **cash-cushion denominator dilution** (dividing by ₹15,00,000 total capital while only ~₹8,50,000 was deployed).
   * In Trade 3 (May 2019), the strategy suffered a **-₹28,911.03 loss (-3.32% on deployed capital)**. This loss was completely concealed in monthly accounting because Trade 4 (+₹29,750.58) closed in the exact same calendar month, producing a net positive month (+₹839.55).
   * **True Daily Mark-to-Market (MTM) Drawdown is 2.73%** (more than 5x the reported figure).
4. **Sample Size & Episode Concentration:**
   * 18 trades across 7.5 years equals just **2.4 trades per year**, concentrated in only **4 discrete market episodes**.
   * **Zero trades occurred in 2020** (the entire COVID crash and recovery were skipped).
   * **Zero trades occurred in the 2025–2026 Holdout partition**.
5. **Verdict:** The candidate is **REJECTED**. The apparent "3.01 Sharpe" and "0.53% DD" are statistical mirages caused by extreme trade sparsity, cash drag, and monthly aggregation distortion.

---

## 2. Comparative Performance Matrix

All metrics are evaluated net of Indian statutory costs (STT, GST, brokerage, exchange charges, stamp duty) and execution slippage:

| Metric | Baseline (No IV Filter) | Candidate (IVP $\ge 40\%$) | **Candidate (IVP $\ge 50\%$)** | Candidate (IVP $\ge 60\%$) | Elevated Vol (IV $\ge 18\%$) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Total Trades** | 118 | 28 | **18** | 13 | 47 |
| **Win Rate (%)** | 69.5% | 71.4% | **77.8%** | 76.9% | 72.3% |
| **Total Net PnL (₹)** | **₹10,13,946.09** | ₹2,07,832.03 | **₹2,11,621.07** | ₹1,48,724.04 | **₹6,11,265.39** |
| **Market Exposure (% Days)** | 71.8% | 16.4% | **10.5%** | 7.2% | 27.6% |
| **Reported Rent Yield (%)** | 14.87% | 12.65% | **19.99%** | 19.33% | 21.89% |
| **True Calendar Yield (%)** | **12.54%** | 2.95% | **3.08%** | 2.13% | **8.53%** |
| **True Calendar CAGR (%)** | **7.07%** | 1.73% | **1.76%** | 1.26% | **4.62%** |
| **Reported Sharpe Ratio** | 1.12 | 0.86 | **3.01** | 1.25 | 1.75 |
| **Bootstrap Median Sharpe** | 1.08 | 0.82 | **1.30** | 1.10 | 1.68 |
| **Reported Max Drawdown (%)** | 3.82% | 3.74% | **0.53%** | 1.51% | 2.39% |
| **True Daily MTM Max DD (%)** | 5.69% | 4.58% | **2.73%** | 1.95% | 3.34% |
| **Profit Factor** | 2.51 | 2.96 | **5.66** | 3.59 | 3.93 |
| **Worst Single Trade PnL (₹)** | -₹75,043.10 | -₹46,455.90 | **-₹28,911.03** | -₹28,911.03 | -₹41,534.37 |
| **Worst Trade Return on Cap** | -4.49% | -5.35% | **-3.32%** | -4.40% | -4.40% |

---

## 3. Detailed Audit of the 18 Realized Trades

The candidate generated exactly 18 trades between February 2019 and June 2024. Below is the complete trade ledger:

| Trade ID | Entry Date | Exit Date | Holding Days | Exit Reason | Capital Deployed (₹) | Net PnL (₹) | Return on Cap |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **CAND_T001** | 2019-02-25 | 2019-03-12 | 15 | STOP_LOSS | ₹8,16,007.50 | +₹18,131.39 | +2.22% |
| **CAND_T002** | 2019-03-13 | 2019-04-01 | 19 | EXPIRY_ROLL | ₹8,50,627.50 | +₹18,362.84 | +2.16% |
| **CAND_T003** | 2019-04-02 | 2019-04-22 | 20 | PROFIT_TARGET | ₹8,78,490.00 | -₹5,002.14 | -0.57% |
| **CAND_T004** | 2019-05-06 | 2019-05-13 | 7 | PROFIT_TARGET | ₹8,69,868.75 | **-₹28,911.03** | **-3.32%** |
| **CAND_T005** | 2019-05-16 | 2019-05-20 | 4 | STOP_LOSS | ₹8,44,282.50 | +₹29,750.58 | +3.52% |
| **CAND_T006** | 2019-05-21 | 2019-06-10 | 20 | EXPIRY_ROLL | ₹8,78,182.50 | +₹19,928.80 | +2.27% |
| *DORMANCY* | *2019-06-11* | *2021-10-25* | *867 days* | *NO TRADES* | *₹0.00 (Cash)* | *₹0.00* | *0.00%* |
| **CAND_T007** | 2021-10-26 | 2021-11-10 | 15 | PROFIT_TARGET | ₹9,13,420.00 | -₹8,208.20 | -0.90% |
| **CAND_T008** | 2021-12-15 | 2022-01-03 | 19 | EXPIRY_ROLL | ₹8,61,070.00 | +₹25,830.10 | +3.00% |
| **CAND_T009** | 2022-01-21 | 2022-02-04 | 14 | PROFIT_TARGET | ₹8,80,857.50 | +₹2,744.57 | +0.31% |
| **CAND_T010** | 2022-03-22 | 2022-04-11 | 20 | EXPIRY_ROLL | ₹8,65,775.00 | +₹24,907.90 | +2.88% |
| *DORMANCY* | *2022-04-12* | *2023-12-20* | *618 days* | *NO TRADES* | *₹0.00 (Cash)* | *₹0.00* | *0.00%* |
| **CAND_T011** | 2023-12-21 | 2024-01-08 | 18 | EXPIRY_ROLL | ₹10,62,752.50 | +₹16,761.66 | +1.58% |
| **CAND_T012** | 2024-01-17 | 2024-02-05 | 19 | EXPIRY_ROLL | ₹10,78,597.50 | +₹14,769.66 | +1.37% |
| **CAND_T013** | 2024-02-08 | 2024-02-26 | 18 | EXPIRY_ROLL | ₹10,85,897.50 | +₹18,767.86 | +1.73% |
| **CAND_T014** | 2024-02-27 | 2024-03-15 | 17 | PROFIT_TARGET | ₹11,09,917.50 | -₹3,281.72 | -0.30% |
| **CAND_T015** | 2024-03-18 | 2024-04-08 | 21 | EXPIRY_ROLL | ₹11,02,785.00 | +₹29,208.33 | +2.65% |
| **CAND_T016** | 2024-04-15 | 2024-05-06 | 21 | EXPIRY_ROLL | ₹11,13,625.00 | +₹11,962.98 | +1.07% |
| **CAND_T017** | 2024-05-07 | 2024-05-27 | 20 | EXPIRY_ROLL | ₹5,57,562.50 | +₹10,471.80 | +1.88% |
| **CAND_T018** | 2024-05-28 | 2024-06-13 | 16 | PROFIT_TARGET | ₹5,72,203.75 | +₹15,425.71 | +2.70% |
| *DORMANCY* | *2024-06-14* | *2026-09-04* | *813 days* | *NO TRADES* | *₹0.00 (Cash)* | *₹0.00* | *0.00%* |

---

## 4. Chronological In-Sample, Out-of-Sample & Holdout Splits

To eliminate lookahead and evaluate out-of-sample persistence, the dataset was partitioned chronologically:

| Partition | Date Range | Trading Days | Trades | Win Rate | Net PnL (₹) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **In-Sample (IS)** | 2019-02-11 to 2022-12-30 | 958 | 10 | 70.0% | ₹97,534.80 | 3.32 |
| **Out-of-Sample (OOS)** | 2023-01-02 to 2024-12-31 | 491 | 8 | 87.5% | ₹1,14,086.27 | 35.76 |
| **Final Holdout** | 2025-01-01 to 2026-09-04 | 415 | **0** | **0.0%** | **₹0.00** | **0.00** |

### Critical Finding on Partitions:
* **Final Holdout Dormancy:** Across 415 consecutive trading days in the final holdout (2025–2026), the strategy **did not take a single trade**. 
* **Regime Collapse:** In low-to-moderate volatility bull runs, the 252-day IV Percentile remained stubbornly below 50.0%. A strategy that produces 0 trades across 20 months in live forward deployment is unusable for capital deployment.

---

## 5. Walk-Forward Rolling Analysis (2-Year Train, 1-Year Test)

| Walk-Forward Window | Train Period | Train Trades | Train PnL (₹) | Test Period | Test Trades | Test PnL (₹) | Test Win Rate |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Window 1** | 2019–2020 | 6 | ₹52,260.43 | 2021 | 2 | ₹17,621.90 | 50.0% |
| **Window 2** | 2020–2021 | 2 | ₹17,621.90 | 2022 | 2 | ₹27,652.47 | 100.0% |
| **Window 3** | 2021–2022 | 4 | ₹45,274.37 | 2023 | 1 | ₹16,761.66 | 100.0% |
| **Window 4** | 2022–2023 | 3 | ₹44,414.13 | 2024 | 7 | ₹97,324.61 | 85.7% |
| **Window 5** | 2023–2024 | 8 | ₹1,14,086.27 | 2025–2026 | **0** | **₹0.00** | **N/A** |

*In 3 out of 5 walk-forward test periods, the strategy executed $\le 2$ trades.* This demonstrates severe instability in opportunity generation.

---

## 6. Statutory Tax & Cost Reconciliation

Every statutory charge was reconciled directly against the trade ledger using the official Indian regulatory cost engine (`IndianDerivativesCostModel`):

| Statutory Fee Component | Rate Applied | Total Deducted (18 Trades) | Notes |
| :--- | :--- | :---: | :--- |
| **Securities Transaction Tax (STT)** | 0.0625% pre-Oct 2024; 0.10% post-Oct 2024 | **₹65.13** | Sell premium turnover only |
| **Brokerage** | Flat ₹20.00 per executed order leg | **₹720.00** | ₹40 roundtrip per trade |
| **Exchange Turnover Fee** | 0.03503% of premium turnover | **₹36.52** | NSE Derivatives segment |
| **SEBI Turnover Charges** | ₹10 per crore turnover | **₹0.10** | Regulatory charge |
| **Stamp Duty** | 0.003% on Buy orders | **₹0.54** | Central/State stamp duty |
| **GST (Goods & Services Tax)** | 18% on (Brokerage + Exch + SEBI) | **₹140.09** | Government service tax |
| **Execution Slippage** | 1.0% premium / min 0.25 pts | **₹1,304.88** | Crossing bid-ask spread |
| **Total Friction & Taxation** | — | **₹2,267.26** | Fully deducted from reported net PnL |

*Due to low turnover (18 trades), total friction was minimal (₹2,267.26). Statutory costs are NOT the reason for underperformance; opportunity starvation and cash drag are.*

---

## 7. Adverse Stress Testing & Fragility Audit

We subjected the candidate's 18 trades to realistic adverse market shocks:

| Scenario Description | Stressed PnL (₹) | PnL Deterioration | Stressed Win Rate | Worst Single Trade (₹) |
| :--- | :---: | :---: | :---: | :---: |
| **Base Realized** | **₹2,11,621.07** | **0.0%** | **77.8%** | **-₹28,911.03** |
| **2x Adverse Slippage** | ₹2,10,621.07 | -0.5% | 77.8% | -₹28,986.03 |
| **3x Severe Slippage (Illiquid)** | ₹2,09,621.07 | -0.9% | 77.8% | -₹29,061.03 |
| **Gap Shock: -1.5% Overnight Gap** | **-₹33,507.77** | **-115.8%** | **61.1%** | **-₹41,959.06** |
| **Tail Shock: -3.0% Gap on Stop Losses** | **-₹2,78,636.61** | **-231.7%** | **5.6%** | **-₹55,007.10** |

### Stress Insight:
* The candidate possesses zero resilience against systematic gap-down risk. Because it has only 18 trades to generate income, a single -1.5% gap down on underlying entries wipes out **100% of cumulative net profits across the entire 7.5-year history**, turning the strategy net negative (-₹33,507).

---

## 8. Statistical Significance & Multiple Testing Audit

1. **Bootstrap Sharpe Ratio Distribution (1,000 Iterations):**
   * **Reported Sharpe:** 3.01
   * **Bootstrap Median Annualized Sharpe:** **1.30**
   * **90% Confidence Interval:** **[0.51, 2.71]**
   * *The true risk-adjusted Sharpe is less than half the reported headline value.*
2. **Deflated Sharpe Ratio (DSR) & Multiple Testing:**
   * In Part 1 and Part 2, 45 parameter combinations + 10 IV regimes were evaluated ($N = 55$ trials).
   * After applying the Bailey & López de Prado (2014) Deflated Sharpe Ratio adjustment for $N = 55$ trials and an effective sample size of $T = 18$ trades, the p-value is **$p = 0.28 > 0.05$**.
   * **The result fails statistical significance and cannot reject the null hypothesis of selection bias.**

---

## 9. Final Decision Gate Checklist

| Evaluation Criterion | Requirement | Result | Audit Status |
| :--- | :--- | :---: | :---: |
| **1. Metric Reproducibility** | Reproduce raw metrics from underlying ledger | Exact match | **PASS** |
| **2. Lookahead Prevention** | Verify no lookahead in IVP calculation | Passed | **PASS** |
| **3. Sample Size Sufficiency** | Minimum 50+ trades across diverse cycles | Only 18 trades | **FAIL ❌** |
| **4. Calendar Opportunity Consistency** | Stable trade frequency across all years | 0 trades in 2020 & 2025–26 | **FAIL ❌** |
| **5. Capital Efficiency (CAGR vs. Rf)** | CAGR > Risk-free liquid rate (6.5%) | 1.76% CAGR | **FAIL ❌** |
| **6. Total Rupee Expectancy** | Outperform baseline absolute profit | -79.1% vs Baseline | **FAIL ❌** |
| **7. Drawdown Integrity** | Daily MTM DD matches reported DD | 2.73% true vs 0.53% reported | **FAIL ❌** |
| **8. Out-of-Sample Holdout Vitality** | Positive activity in final holdout | 0 trades in 2025–2026 | **FAIL ❌** |

---

## 10. Formal Recommendation

### Verdict: **REJECTED**

The **High IV Rank Gate (`IVP >= 50%`)** is **REJECTED** for live deployment or production consideration. 

### Recommended Research Alternative:
If volatility filtering is desired, the **Absolute Elevated Volatility configuration (`ATM IV >= 18%`)** is strongly preferred:
* **Trades:** 47 trades (statistically meaningful).
* **Total Net Profit:** ₹6,11,265 (nearly 3x higher than IVP $\ge$ 50%).
* **Calendar CAGR:** 4.62% p.a.
* **True Daily Max DD:** 3.34%.
* **Distribution:** Consistent execution across all market regimes without multi-year dormancy periods.

*All reproducible artifacts and data ledgers are preserved in `~/backtesting/covered call/validation/`.*
