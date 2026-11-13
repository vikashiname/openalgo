# FINAL INDEPENDENT AUDIT FINDINGS: EXP-064-INT5 VALIDATION
**Strategy:** NIFTY Covered Call Strategy  
**Candidate ID:** `EXP-064-INT5`  
**Parameters:** Short Call Delta `0.25`, Profit Target `80%`, Stop Loss `3.0x`, Roll Threshold `7 Trading Sessions` (Holiday-Aware)  
**Benchmark:** Frozen Mechanical Baseline (Delta `0.30`, Target `90%`, Stop Loss `3.0x`, Roll `10 Calendar DTE`)  
**Audit Path:** `~/backtesting/covered call/`  
**Audit Date:** October 13, 2026  
**Auditor:** AGY Quantitative Validation Engine  

---

## 1. Executive Audit Summary

A forensic, read-only audit of the completed backtesting and validation artifacts for candidate **EXP-064-INT5** was conducted across the 2019–2026 historical horizon (1,264,462 option contracts, 1,864 trading days, 7.56 calendar years). 

This audit examined:
1. Holdout independence and selection contamination
2. Crash and overnight gap stress modeling mechanics
3. Risk metric reconciliation and denominator integrity
4. Statistical comparison and Sharpe confidence intervals
5. Walk-forward rolling accounting and window independence
6. Accounting, PnL, lot-size transitions, and statutory cost integrity

### Decision Gate Classification:
```text
========================================================================================================
                                     FINAL DECISION GATE VERDICT
========================================================================================================
 Candidate ID:     EXP-064-INT5
 Parameters:       Short Call Delta 0.25 | Profit Target 80% | Stop Loss 3.0x | Roll 7 Trading Sessions
 Classification:   VALIDATED FOR FURTHER PAPER EVALUATION (WITH DOCUMENTED CAVEATS)

 Verdict Summary:
 - Mathematical PnL & Daily NAV reconciliation: PASS (exact 0.000000 rupee discrepancy).
 - Frictional Cost & Regulatory Taxes: PASS (itemized brokerage, STT, exchange, SEBI, GST verified).
 - Net Cumulative Alpha: PASS (+₹75,562 net profit lead over baseline).
 - Tail Risk Containment: PASS (32.9% reduction in worst-trade rupee loss).
 - Walk-Forward Accounting: PASS (zero double-counting; positive cumulative OOS test PnL).
 - Parameter Stability Grid: PASS (81 permutations; 59.3% beat baseline; mean PnL ₹10.47L).
 - Holdout Independence: INCONCLUSIVE / CONDITIONAL PASS (holdout was inspected during full sweep,
   not held in a blind vault; however, parameters sit on an in-sample structural plateau).
 - Crash & Gap Stress Modeling: INCONCLUSIVE (stress model applies a linear net-delta approximation
   on stop-loss trades; full nonlinear gamma/vega/skew crash validation is NOT claimed).
 - Statistical Significance: INCONCLUSIVE (Sharpe difference is a higher point estimate, but not
   statistically significant: paired t-test p = 0.65).
========================================================================================================
```

---

## 2. Itemized Audit Checks & Empirical Findings

```text
========================================================================================================
                                    ITEMIZED AUDIT CHECK RESULTS
========================================================================================================
 Check #   Audit Domain                      Result          Primary Evaluation Summary
--------------------------------------------------------------------------------------------------------
 Check 1   Holdout Independence              INCONCLUSIVE    Full dataset loaded during sweep; holdout was
                                                             inspected rather than locked in a blind vault.
 Check 2   Crash & Gap Stress Mechanics      INCONCLUSIVE    Static linear net-delta approximation used;
                                                             missing nonlinear gamma, vega & skew repricing.
 Check 3   Risk Metric Reconciliation        PASS (CORRECTED) Conflation of Trade 127 (rupee) and Trade 98 (%)
                                                             identified and reconciled. Loss is lower on NAV.
 Check 4   Statistical Comparison            INCONCLUSIVE    Point Sharpe is higher (0.22 vs 0.13), but
                                                             confidence intervals overlap; paired t-test p = 0.65.
 Check 5   Walk-Forward Accounting           PASS            Zero double-counting; 5 non-overlapping test slices
                                                             reconciled; 2022 loss (-₹10k) fully explained.
 Check 6   Accounting & Cost Integrity       PASS            Exact ₹0.000000 PnL discrepancy; lot size schedule
                                                             and statutory taxes fully verified.
========================================================================================================
```

---

### Check 1: Holdout Independence & Selection Contamination
**Audit Status:** **INCONCLUSIVE (CONDITIONAL PASS)**  
**Supporting Artifacts:** [`run_experiments.py`](file:///Users/mac/backtesting/covered%20call/research/run_experiments.py), [`optimization_results_matrix.csv`](file:///Users/mac/backtesting/covered%20call/research/optimization_results_matrix.csv), [`validation_int5_holdout_audit.csv`](file:///Users/mac/backtesting/covered%20call/validation/validation_int5_holdout_audit.csv)

#### Forensic Findings:
1. **Full-Horizon Sweep:** In `run_experiments.py`, `evaluate_experiment()` executed all 40 candidates across the complete date range (`2019-02-11` to `2026-09-04`). Candidate metrics in `optimization_results_matrix.csv` were calculated over the full 7.56-year horizon.
2. **Holdout Visibility:** The 2025–2026 final holdout was not quarantined in an encrypted or separate unaccessed partition prior to candidate ranking. The candidate's reported cumulative PnL (₹10,89,508.91) embeds the ₹1,57,195.21 generated during the 2025–2026 holdout.
3. **Parameter Derivation:** The core parameters of INT5 were formulated based on in-sample structural hypotheses:
   - Delta `0.25`: Derived from in-sample risk-return trade-offs (yielding ₹7.25L in In-Sample 2019–2022 vs Baseline's ₹6.45L).
   - Target `80%`: Derived from in-sample gamma-risk avoidance (avoiding the late-tenor gamma spikes observed at 95%–99%).
   - Roll `7 Trading Sessions`: Derived from exchange calendar rules to eliminate weekend theta decay traps.
4. **Conclusion:** While parameter formulation was conceptually sound and supported by in-sample evidence, the final evaluation cannot be classified as a *strictly untouched blind holdout*. It must be classified as a *retrospective holdout partition inspected concurrently with candidate ranking*.

---

### Check 2: Crash and Overnight Gap Stress Mechanics
**Audit Status:** **INCONCLUSIVE (LIMITATION IDENTIFIED — DO NOT CLAIM FULL CRASH VALIDATION)**  
**Supporting Artifacts:** [`optimization_engine.py`](file:///Users/mac/backtesting/covered%20call/research/optimization_engine.py#L281-L295), [`validation_int5_stress_test_matrix.csv`](file:///Users/mac/backtesting/covered%20call/validation/validation_int5_stress_test_matrix.csv)

#### Forensic Findings:
1. **Stress Test Implementation Analysis:**
   In `optimization_engine.py` (lines 281–295), adverse gap shocks are modeled as:
   ```python
   # -1.5% Overnight Gap
   t_shock.loc[sl_mask, 'net_pnl'] = t_shock.loc[sl_mask, 'net_pnl'] - (
       t_shock.loc[sl_mask, 'capital_deployed'] * 0.015 * net_delta
   )
   ```
2. **Methodological Deficiencies:**
   - **Static Net-Delta Approximation:** The stress calculation assumes a fixed net position delta ($\Delta_{net} = 1.0 - \Delta_{call} \approx 0.75$). In an actual market crash, option delta is non-linear ($\Delta$ shifts with spot movement according to $\Gamma$).
   - **Absence of Volatility Expansion (Vega Shock):** During overnight crashes, implied volatility spikes violently ($\Delta \sigma > 0$). While spot depreciation helps the short call, IV expansion inflates the option buyback price ($\text{Vega} \times \Delta \sigma$), diminishing the hedge. This effect is completely omitted.
   - **Absence of Volatility Skew:** OTM call IV decays differently than ATM/ITM IV during panic selloffs. Skew dynamics are unmodeled.
   - **Selective Trade Application:** The shock is applied only to trades that exited via `'STOP_LOSS'`. Positions that were active during overnight gaps but did not trigger a stop loss are unshocked.
3. **Conclusion:** The stress test provides a useful linear delta-cushion approximation, but **DOES NOT constitute full crash validation**. Full crash resilience under non-linear gamma, vega expansion, and skew shocks remains unproven.

---

### Check 3: Risk Metric Reconciliation & Denominator Verification
**Audit Status:** **PASS (CONFLATION DISCREPANCY IDENTIFIED AND RECONCILED)**  
**Supporting Artifacts:** [`validation_int5_trade_ledger.csv`](file:///Users/mac/backtesting/covered%20call/validation/validation_int5_trade_ledger.csv), [`validation_base_trade_ledger.csv`](file:///Users/mac/backtesting/covered%20call/validation/validation_base_trade_ledger.csv)

#### Forensic Reconciliation:
In previous scorecards, candidate EXP-064-INT5 reported a worst trade of `-₹50,374.65 (-5.73%)` vs Baseline's `-₹75,043.10 (-4.49%)`. A forensic trace reveals that these numbers came from **two completely different trades**:

```text
========================================================================================================
                               WORST TRADE FORENSIC RECONCILIATION
========================================================================================================
 Metric / Trade Dimension       Baseline (BASE_T114)     INT5 Rupee (INT5_T127)   INT5 Return% (INT5_T098)
--------------------------------------------------------------------------------------------------------
 Trade ID                       BASE_T114                INT5_T127                INT5_T098
 Entry Date                     2026-02-23               2026-02-23               2024-06-03 (Election Day)
 Exit Date                      2026-03-06               2026-03-02               2024-06-04
 NSE Lot Size                   65                       65                       25
 Entry Spot                     25,713.00                25,713.00                23,263.90
 Capital Deployed (Spot * Lot)  ₹16,71,345.00            ₹16,71,345.00            ₹5,81,597.50
 Net Trade PnL (₹)              -₹75,043.10              -₹50,374.65              -₹33,343.58
 Return on Capital Deployed     -4.4900% (-4.49%)        -3.0140% (-3.01%)        -5.7331% (-5.73%)
 Return on Reference Cap (₹15L) -5.0029% (-5.00%)        -3.3583% (-3.36%)        -2.2229% (-2.22%)
 Return on Current NAV (~₹24L)  -3.06%                   -2.01%                   -1.48%
========================================================================================================
```

#### Key Reconciliation Findings:
1. **Reporting Conflation:** The prior summary report concatenated the **lowest rupee PnL** from Trade 127 (-₹50,374.65) with the **lowest percentage return** from Trade 98 (-5.73%).
2. **Lot Size Distortion in Trade 98:** On June 3, 2024 (Lok Sabha election results), NSE lot size had been cut to **25**, reducing deployed capital to only ₹5.81 Lakhs. The rupee loss of -₹33,343 represented -5.73% of deployed capital, but only **-2.22% of portfolio capital**.
3. **True Apple-to-Apple Comparison:** On the identical market drawdown episode (Feb–March 2026, Lot 65):
   - Baseline suffered **-₹75,043.10 (-4.49% on deployed capital; -5.00% on portfolio capital)**.
   - Candidate INT5 suffered **-₹50,374.65 (-3.01% on deployed capital; -3.36% on portfolio capital)**.
4. **Audit Verdict:** When measured on an identical capital denominator, candidate INT5 reduced tail risk by **32.9% in rupees** and **148 basis points on capital**.

---

### Check 4: Statistical Comparison & Sharpe Confidence Intervals
**Audit Status:** **INCONCLUSIVE (HIGHER POINT ESTIMATE CONFIRMED; NO STATISTICAL SUPERIORITY)**  
**Supporting Artifacts:** [`validation_int5_baseline_comparison.csv`](file:///Users/mac/backtesting/covered%20call/validation/validation_int5_baseline_comparison.csv), [`validation_int5_daily_nav.csv`](file:///Users/mac/backtesting/covered%20call/validation/validation_int5_daily_nav.csv)

#### Forensic Statistical Calculations:
Using daily percentage returns ($N = 1,864$ trading days) and Indian benchmark risk-free rate ($R_f = 6.5\%$ p.a.):

| Statistical Dimension | Baseline (EXP-000-BASE) | Candidate (EXP-064-INT5) | Statistical Comparison / Test |
| :--- | :---: | :---: | :--- |
| **Point Daily Sharpe (0% Cash)** | 0.129 | 0.219 | +0.090 higher point estimate |
| **Bootstrap 90% Confidence Interval** | `[-0.47, 0.72]` | `[-0.39, 0.79]` | **Massive overlap across entire range** |
| **Point Daily Sharpe (+4.8% Cash)**| 0.455 | 0.558 | +0.103 higher point estimate |
| **Paired Daily Return Difference** | $\mu_{\Delta} = +0.0022\%$ / day | $\sigma_{\Delta} = 0.2104\%$ / day | **Paired $t$-statistic = 0.449** |
| **Paired $t$-Test $p$-Value** | — | — | **$p = 0.6537 \gg 0.05$ (Not significant)** |

#### Statistical Audit Verdict:
- The candidate achieves a higher point Sharpe ratio (0.22 vs 0.13 without cash sweep; 0.56 vs 0.46 with cash sweep).
- However, zero is comfortably contained within both 90% confidence intervals.
- A paired $t$-test on daily return series yields $p = 0.6537$, confirming that **the daily return series differences are not statistically distinguishable from zero**.
- **Audit Verdict:** The claim of "Sharpe superiority" must be retracted to **"higher point estimate with overlapping confidence bounds"**.

---

### Check 5: Walk-Forward Accounting & Rolling Window Independence
**Audit Status:** **PASS**  
**Supporting Artifacts:** [`validation_int5_walk_forward_matrix.csv`](file:///Users/mac/backtesting/covered%20call/validation/validation_int5_walk_forward_matrix.csv)

#### Forensic Walk-Forward Verification:
```text
========================================================================================================
                              WALK-FORWARD ROLLING WINDOW RECONCILIATION
========================================================================================================
 Window   Train Window  Test Slice    Baseline Test PnL        INT5 Test PnL            Test Trade Count
--------------------------------------------------------------------------------------------------------
 Window 1 2019–2020     2021          ₹2,53,755.66 (73.7% WR)  ₹3,41,834.55 (82.6% WR)  Base: 19 | INT5: 23
 Window 2 2020–2021     2022          +₹34,354.10 (50.0% WR)   -₹10,004.19 (43.8% WR)   Base: 14 | INT5: 16
 Window 3 2021–2022     2023          ₹1,68,477.49 (77.8% WR)  ₹1,57,817.90 (73.7% WR)  Base: 18 | INT5: 19
 Window 4 2022–2023     2024          ₹63,334.95 (64.7% WR)    ₹49,581.32 (60.0% WR)    Base: 17 | INT5: 20
 Window 5 2023–2024     2025–2026     ₹1,36,667.05 (63.6% WR)  ₹1,57,195.21 (62.5% WR)  Base: 22 | INT5: 24
--------------------------------------------------------------------------------------------------------
 Cumulative Out-of-Sample Test PnL:   ₹6,56,589.25             ₹6,96,424.79             Base: 90 | INT5: 102
========================================================================================================
```

#### Forensic Observations:
1. **Window Independence:** The test slices (2021, 2022, 2023, 2024, 2025–2026) are strictly contiguous, non-overlapping calendar periods. Each trade entry falls into exactly one test window.
2. **Zero Double-Counting:** Cumulative test trades equal 90 for Baseline and 102 for INT5. The remaining trades (28 for Baseline, 30 for INT5) occurred in 2019–2020, serving exclusively as initial training data. Zero trades are double-counted.
3. **Reconciliation of 2022 Loss:** In Window 2 (2022), INT5 posted -₹10,004.19 vs Baseline's +₹34,354.10. Detailed ledger inspection confirms that Delta 0.25 collected ~45 points lower initial premium cushion than Delta 0.30 during the Russia-Ukraine selloff. This was offset by +₹88k alpha in 2021 and +₹20.5k alpha in 2025–2026. Cumulative test PnL favored INT5 by **+₹39,835.54**.

---

### Check 6: Accounting, Sizing, and Regulatory Cost Integrity
**Audit Status:** **PASS**  
**Supporting Artifacts:** [`validation_int5_cost_reconciliation.csv`](file:///Users/mac/backtesting/covered%20call/validation/validation_int5_cost_reconciliation.csv), [`validation_int5_daily_nav.csv`](file:///Users/mac/backtesting/covered%20call/validation/validation_int5_daily_nav.csv)

#### Forensic Integrity Verification:
1. **PnL Reconciliation Formula:**
   $$\Delta \text{NAV}_{\text{Terminal}} = \text{NAV}_{\text{End}} - \text{NAV}_{\text{Initial}} = \sum_{i=1}^{N} \text{Net PnL}_i$$
   - **Baseline:** $\sum \text{Net PnL} = ₹10,13,946.087599$ | $\Delta \text{NAV} = ₹10,13,946.087599$ | **Diff = ₹0.000000**
   - **Candidate INT5:** $\sum \text{Net PnL} = ₹10,89,508.909081$ | $\Delta \text{NAV} = ₹10,89,508.909081$ | **Diff = ₹0.000000**
2. **Statutory Fee Verification:**
   - Brokerage: Exactly ₹20 per order leg (₹40 roundtrip). 132 trades = ₹5,280.00.
   - STT: Verified at 0.0625% on sell premium turnover before Oct 1, 2024; 0.10% after Oct 1, 2024.
   - Exchange charges (0.03503%), SEBI turnover fees (₹10/Cr), stamp duty (0.003% buy), and GST (18%) reconcile down to 2 decimal places.
3. **Lot Size History:** Successfully handled all regulatory lot size transitions:
   - 2019–2020: 75
   - 2021: Transition from 75 to 50
   - 2022–2023: 50
   - 2024: 50 to 25 (May) to 75 (Nov)
   - 2025: 75
   - 2026: 65

---

## 3. Final Decision Gate Recommendation

In accordance with institutional quantitative governance, candidate **EXP-064-INT5** is classified as:

### **`VALIDATED FOR FURTHER PAPER EVALUATION`**

#### Conditions & Forward Guardrails:
1. **Paper Observation Only:** The candidate is qualified to enter forward paper observation in `~/backtesting/covered call/forward/`.
2. **Retract Overstated Claims:**
   - Do NOT claim "statistically superior Sharpe" (it is a higher point estimate, but $p = 0.65$).
   - Do NOT claim "full crash/gap validation" (existing stress testing uses a linear net-delta approximation without non-linear gamma, vega, and skew modeling).
   - Reconcile worst-trade percentage to `-3.01% on deployed capital` (-3.36% on portfolio capital) on Trade 127, clearly separating it from Trade 98's -5.73% on a reduced 25-lot denominator.
3. **Dynamic Position Sizing Advisory:** Live paper execution must size underlying exposure using fractional cash ETF (`NIFTYBEES`) units to prevent notional equity from exceeding available portfolio capital as index levels rise.
4. **Hard Stop Governance:** No live orders, no broker connections, and no modification to production directories (`~/strategy/`, `strategies/liveonopenalgo/`, `macdfno.py`, `emacrossopen.py`) are permitted without separate explicit approval.
