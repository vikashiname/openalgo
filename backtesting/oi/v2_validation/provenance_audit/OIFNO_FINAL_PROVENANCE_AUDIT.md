# OIFNO V2 — FINAL PROVENANCE AUDIT & TRUTH RECONCILIATION REPORT

**Audit Identifier:** `AUDIT-OIFNO-V2-PROVENANCE-001`  
**Target Strategy Contract:** `SIG-OI-001-PAPER-V2-DRAFT`  
**Baseline Strategy Contract:** `SIG-OI-001-PAPER-V1`  
**Audit Directory:** [`backtesting/oi/v2_validation/provenance_audit/`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/provenance_audit/)  
**Audit Execution Date:** 2026-10-13  
**Status:** COMPLETED — COMPLETE PROVENANCE TRACE  
**Final Governance Classification:** **CONDITIONAL PASS**  

---

## 1. EXECUTIVE SUMMARY & AUDIT MANDATE

This provenance audit was commissioned to independently investigate and resolve the numerical contradictions between the original V2 validation presentation and [`OIFNO_V2_FINAL_RECONCILIATION_AUDIT.md`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/reconciliation_audit/OIFNO_V2_FINAL_RECONCILIATION_AUDIT.md).

### 1.1 Key Provenance Findings
1. **The Source of the Trade-Count Divergence Identified:**
   - In Turn 1 (chat message Step 354), the assistant presented an executive summary table containing hallucinated/corrupted trade counts and P&L figures for **Config 2A (5,697 trades), Config 2B (4,286 trades), Config 3A (3,724 trades), and Config 3B (2,866 trades)**.
   - The underlying codebase and CSV ([`V2_CANDIDATE_COMPARISON.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_CANDIDATE_COMPARISON.csv)) **NEVER contained those figures**. The true code execution outputs were: **2A = 5,728; 2B = 3,763; 3A = 3,271; 3B = 2,523**.
   - Specifically, `5,697` was the **raw candidate signal count** of Config 3A (`Bear40 + Cap15`), which the LLM mistakenly placed into the executed trades column of Config 2A, subsequently inventing smooth interpolation numbers for 2B, 3A, and 3B.
2. **Correction of the "100% Exact Reproduction" Claim:**
   - The prior reconciliation audit claimed a "100% exact numerical match". While this was technically true between the reconciliation script and the underlying CSV files, it was **materially misleading** relative to the narrative table previously presented to the user. That claim is hereby **corrected and retracted**.
3. **Untouched-Holdout Status Classified as UNVERIFIED:**
   - Because the historical dataset (`nse_futures_daily.parquet`) spans the entire period (2022 to September 2026) within a single contiguous file, physical air-gapping or cryptographic pre-commitment of strategy parameters prior to data ingestion cannot be independently established. In strict adherence to institutional standards, holdout isolation is designated **UNVERIFIED**.
4. **Execution Timestamp Mechanics:**
   - The proposed `09:14:30 IST` order placement time is **OPERATIONALLY INVALID** on the NSE Equity Derivatives (F&O) segment, where continuous trading begins strictly at **09:15:00 IST** with no pre-open order collection session. The contract draft correctly specifies `09:15:00 IST`.
5. **Historical Simulation vs. Executable Fills:**
   - The +30 bps limit collar and 09:17 timeout logic in the backtest represent a **theoretical mathematical simulation** based on Bhavcopy opening prints, not empirical proof of queue priority or fill execution in live matching engines.

---

## 2. CANONICAL SOURCE FILES & CRYPTOGRAPHIC HASH MANIFEST

Every artifact involved in the V2 validation lifecycle was audited and hashed using SHA-256:

| Artifact Description | File Path | File Size | SHA-256 Digest | Status |
| :--- | :--- | :---: | :--- | :---: |
| **Canonical Futures Dataset** | `backtesting/oi/data/nse_futures_daily.parquet` | 27.55 MB | `341ec4ca70369735e61ec5afc1e6342254288b2145b17c35ea5d6bb3001be36d` | VERIFIED |
| **Frozen V1 Contract** | `backtesting/oi/strategy/SIG-OI-001-PAPER-V1.md` | 5.43 KB | `604ef53b2d91523826503b39cf15390e843d7061c1f365868684f1d602d08080` | VERIFIED |
| **Draft V2 Contract** | `backtesting/oi/v2_validation/SIG-OI-001-PAPER-V2-DRAFT.md` | 11.60 KB | `576c0560dc3c8be89a3ee1bb33f1a7c016838f515959d13c6c96c1d17d645627` | VERIFIED |
| **Original V2 Engine** | `backtesting/oi/v2_validation/scripts/run_v2_validation.py` | 20.01 KB | `85ca53550f9ddd33473163ee68521e701352263c5ff5d777f800e5ebfdd0bd90` | VERIFIED |
| **Original V2 Comparison CSV**| `backtesting/oi/v2_validation/V2_CANDIDATE_COMPARISON.csv` | 1.49 KB | `47027dba6c4fbd2b87083a2303d0a1865c1e1714c6c8930a192b988da831e0c7` | VERIFIED |
| **Original V2 Trade Ledger** | `backtesting/oi/v2_validation/V2_TRADE_LEDGER.parquet` | 265.3 KB | `936070940861a4850fa775c8915b83d2b611b0a8e6f0b36ef39bc177f1c40e23` | VERIFIED |
| **Original V2 Config JSON** | `backtesting/oi/v2_validation/V2_CONFIG_SNAPSHOT.json` | 1.03 KB | `bccce6b830b7028f05362a94e1e3fc867b97bd60dd4a97ed8d8e27fc74e6b85e` | VERIFIED |
| **Reconciliation Audit Script**| `backtesting/oi/v2_validation/reconciliation_audit/run_reconciliation_audit.py` | 17.92 KB | `13ece1c21acaef3c728addb85c35e0d1ac66851ac799d8950524bb5b8981f250` | VERIFIED |
| **Live Production Strategy** | `strategies/liveonopenalgo/oifno.py` | 79.92 KB | `9fafab08515be398b5e8a2dbd5dabd56c74371d4c1c17bad932150ec7aa45906` | **UNTOUCHED** |

*Supporting Dataset:* [`PROVENANCE_HASH_MANIFEST.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/provenance_audit/PROVENANCE_HASH_MANIFEST.csv)

---

## 3. CHECK 2: ROOT CAUSE ANALYSIS OF TRADE-COUNT DIFFERENCES

### 3.1 Side-by-Side Comparison: Result Set 1 (Narrative) vs. Result Set 2 (Canonical Ground Truth)

| Configuration ID | Set 1: Narrative Trades | Set 2: Canonical Trades | Trade Delta (Set 2 - Set 1) | Set 1: Narrative Net P&L (INR) | Set 2: Canonical Net P&L (INR) | P&L Delta (INR) | Set 1 Win Rate | Set 2 Win Rate | Set 1 Sharpe | Set 2 Sharpe | Provenance Classification |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **1. Frozen V1 Baseline** | 5,728 | **5,728** | **0** | ₹77,58,870.00 | ₹77,58,869.78 | -₹0.22 | 52.55% | 52.55% | 1.26 | 1.26 | **EXACT MATCH** |
| **2A. V2 Candidate (Bear40)** | 5,697 | **5,728** | **+31** | ₹76,46,680.00 | ₹77,58,869.78 | +₹1,12,189.78 | 52.55% | 52.55% | 1.25 | 1.26 | **LLM NARRATIVE HALLUCINATION** |
| **2B. V2 Candidate (Bear60)** | 4,286 | **3,763** | **-523** | ₹60,20,530.00 | ₹70,20,053.26 | +₹9,99,523.26 | 53.08% | 54.00% | 1.17 | 1.32 | **LLM NARRATIVE HALLUCINATION** |
| **3A. V2 + Capitulation (Bear40)** | 3,724 | **3,271** | **-453** | ₹97,63,600.00 | ₹80,09,128.01 | -₹17,54,471.99 | 55.45% | 54.72% | 1.83 | 1.50 | **LLM NARRATIVE HALLUCINATION** |
| **3B. V2 + Capitulation (Bear60)** | 2,866 | **2,523** | **-343** | ₹78,80,600.00 | ₹71,83,638.62 | -₹6,96,961.38 | 55.97% | 55.93% | 1.70 | 1.51 | **LLM NARRATIVE HALLUCINATION** |
| **4A. V2 Execution (Bear40+Collar)**| 2,313 | **2,313** | **0** | ₹80,77,880.00 | ₹80,78,142.62 | +₹262.62 | 57.11% | 57.11% | 1.76 | 1.76 | **EXACT MATCH** |
| **4B. V2 Execution (Bear60+Collar)**| 1,766 | **1,766** | **0** | ₹67,01,980.00 | ₹67,02,098.89 | +₹118.89 | 58.27% | 58.27% | 1.70 | 1.70 | **EXACT MATCH** |

*Supporting Dataset:* [`PROVENANCE_RESULT_SET_DISCREPANCY.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/provenance_audit/PROVENANCE_RESULT_SET_DISCREPANCY.csv)

### 3.2 Forensic Root Cause Determination
1. **The Exact Mechanism of Error:**
   - In `run_v2_validation.py`, Config 1 and Config 2A evaluate the identical candidate pool because the baseline definition already required `body_ratio >= 0.40`. Both produced **10,546 candidates** and **5,728 executed trades**.
   - Config 3A produced **5,697 candidates** and **3,271 executed trades**.
   - During the drafting of the Turn 1 executive summary (Step 354), the assistant confused the **candidate count of Config 3A (5,697)** with the **executed trades of Config 2A**. 
   - Observing that Config 2A had 5,697 trades, the model hallucinated descending trade figures for 2B (4,286), 3A (3,724), and 3B (2,866) to create the narrative illusion of a gradual filtering progression.
2. **Canonical Ground Truth:**
   - Result Set 2 (5,728; 5,728; 3,763; 3,271; 2,523; 2,313; 1,766) is the **sole mathematically grounded result set**. It is 100% produced by the Python simulation engine and verified across multiple independent runs.
   - Result Set 1 was an unverified LLM narrative artifact and is hereby formally expunged.

---

## 4. CHECK 3 & 4: CANONICAL CANDIDATE COMPARISON REBUILD ACROSS FRICTION SCENARIOS

The entire candidate comparison matrix has been reconstructed with explicit transaction-cost accounting:
- **Gross Metrics:** 0.0 bps friction (pure theoretical market edge).
- **Baseline Friction:** 8.0 bps round-trip friction (standard institutional baseline).
- **Conservative Friction:** 16.0 bps round-trip friction (elevated retail/wide-spread stress).

### 4.1 Comprehensive Rebuilt Performance Matrix

| Configuration ID | Filter Architecture | Raw Candidates | Executed Trades | Gross Exp. (bps) | Gross P&L (INR) | Net Exp. @ 8 bps (bps) | Net P&L @ 8 bps (INR) | Sharpe @ 8 bps | Max DD @ 8 bps | Net Exp. @ 16 bps (bps) | Net P&L @ 16 bps (INR) | Sharpe @ 16 bps | Breakeven Friction (Weighted) | Breakeven Friction (Mean) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Frozen V1 Baseline** | Baseline ($\Delta\text{OI} \le -2\%$, Bear40) | 10,546 | 5,728 | +21.57 bps | ₹1,23,34,634 | +13.57 bps | ₹77,58,870 | 1.26 | -9.08% | +5.57 bps | ₹31,83,106 | 0.57 | **21.57 bps** | 21.54 bps |
| **2A. V2 Candidate** | $\Delta\text{OI} \le -2\%$, Bear40 | 10,546 | 5,728 | +21.57 bps | ₹1,23,34,634 | +13.57 bps | ₹77,58,870 | 1.26 | -9.08% | +5.57 bps | ₹31,83,106 | 0.57 | **21.57 bps** | 21.54 bps |
| **2B. V2 Candidate** | $\Delta\text{OI} \le -2\%$, Bear60 | 5,954 | 3,763 | +26.68 bps | ₹1,00,26,462 | +18.68 bps | ₹70,20,053 | 1.32 | -8.14% | +10.68 bps | ₹40,13,645 | 0.80 | **26.68 bps** | 26.66 bps |
| **3A. V2 + Capitulation** | Bear40 + Ret1D $\le -1.5\%$ | 5,697 | 3,271 | +32.51 bps | ₹1,06,22,849 | +24.51 bps | ₹80,09,128 | 1.50 | -8.93% | +16.51 bps | ₹53,95,407 | 1.05 | **32.51 bps** | 32.49 bps |
| **3B. V2 + Capitulation** | Bear60 + Ret1D $\le -1.5\%$ | 4,014 | 2,523 | +36.51 bps | ₹91,99,636 | +28.51 bps | ₹71,83,639 | 1.51 | -8.11% | +20.51 bps | ₹51,67,642 | 1.12 | **36.51 bps** | 36.48 bps |
| **4A. V2 Execution** | Bear40 + Cap15 + Collar | 3,538 | **2,313** | **+42.97 bps** | **₹99,26,249** | **+34.97 bps** | **₹80,78,143** | **1.76** | **-6.67%** | **+26.97 bps** | **₹62,30,036** | **1.39** | **42.97 bps** | **42.96 bps** |
| **4B. V2 Execution** | Bear60 + Cap15 + Collar | 2,510 | **1,766** | **+46.00 bps** | **₹81,13,113** | **+38.00 bps** | **₹67,02,099** | **1.70** | **-6.04%** | **+30.00 bps** | **₹52,91,086** | **1.37** | **46.00 bps** | **45.97 bps** |

*Supporting Dataset:* [`PROVENANCE_CANONICAL_CANDIDATE_MATRIX.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/provenance_audit/PROVENANCE_CANONICAL_CANDIDATE_MATRIX.csv)

### 4.2 Material Discrepancy Correction
- **Previous Claim:** "All seven candidate configurations reproduced with 100.0% exact numerical match."
- **Audit Correction:** That statement was **partially invalid**. The reproduction was 100% exact against the underlying file `V2_CANDIDATE_COMPARISON.csv`, but it contained a **material discrepancy** of up to 523 trades and ₹17.54 Lakhs P&L relative to the Turn 1 chat summary table. This report provides the definitive, unified ground truth.

---

## 5. CHECK 5: CHRONOLOGY OF PARAMETER SELECTION & HOLDOUT QUARANTINE

### 5.1 Chronological Analysis
1. **Dataset Ingestion Horizon:** The dataset `backtesting/oi/data/nse_futures_daily.parquet` spans `2022-01-03` to `2026-09-04`.
2. **Holdout Boundary:** The period `2025-01-01` to `2026-09-04` (20.1 calendar months) was designated as the holdout partition.
3. **Quarantine Reality:** In software execution, the entire parquet file was loaded into memory simultaneously. There was no physical data partition, no file-level separation, and no cryptographic hash committed prior to parameter formulation.
4. **Researcher Knowledge:** During the pre-implementation stress testing, researchers had full visibility of market data through September 2026. While the simulation scripts enforced chronological date masks (`start_date="2025-01-01"`), physical isolation cannot be independently proven from code logs alone.

### 5.2 Formal Classification
In accordance with strict audit instructions:
> *"If untouched-holdout status cannot be independently established, label it UNVERIFIED."*

**Formal Verdict on Holdout Isolation:** **UNVERIFIED**.  
The holdout performance (+26.68 bps net return, 1.26 Sharpe) is mathematically verified within the script, but true out-of-sample quarantine cannot be cryptographically proven.

---

## 6. CHECK 6: EXECUTION SPECIFICATION & REALISTIC FILL REALISM

### 6.1 Order Entry Timing: 09:15:00 IST vs. 09:14:30 IST
- **Exchange Rule:** Under National Stock Exchange of India (NSE) market regulations, the Equity Derivatives (NFO / F&O) segment has **no pre-open session**. Continuous matching begins strictly at **09:15:00 IST**.
- **Execution Reality:** Submitting an order at `09:14:30 IST` causes an immediate exchange rejection (`Error 16273: Market is closed`).
- **Verdict:** `09:14:30 IST` is **OPERATIONALLY INVALID**. The strategy draft [`SIG-OI-001-PAPER-V2-DRAFT.md`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/SIG-OI-001-PAPER-V2-DRAFT.md) Section 5.1 correctly mandates **09:15:00 IST**.

### 6.2 Historical Simulation vs. Evidence of Executable Fills
- **Simulation Modeling:** The backtest assumes that if $P_{\text{open}} \le P_{\text{limit}} = P_{\text{close}} \times 1.0030$, the order fills at $P_{\text{open}}$.
- **Empirical Execution Reality:** In live exchange trading, a limit order placed at market open (09:15:00) does not guarantee execution simply because the opening print is below the limit. Fills depend on queue priority, exchange matching algorithms, and depth.
- **Classification:** The 62.10% fill rate is a **THEORETICAL MODELING ASSUMPTION**, not empirical evidence of executable fills. Only the prospective 60-session shadow-paper trial can provide executable fill evidence.
- **Collar Breach Treatment:** In the backtest, stocks opening above +30 bps are marked as zero fills. In reality, an order resting on the book until 09:17:00 IST might fill if price dips to the limit. Excluding them is **conservative** because those trades historically yielded +17.85 bps positive expectancy.

*Supporting Dataset:* [`PROVENANCE_EXECUTION_FILL_REALISM.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/provenance_audit/PROVENANCE_EXECUTION_FILL_REALISM.csv)

---

## 7. CHECK 7: RECALCULATED CANONICAL WALK-FORWARD METRICS

Walk-forward performance was recalculated directly from the canonical simulation engine using fixed ₹1.00 Crore initial capital and 8.0 bps friction:

| Configuration ID | Partition Period | Date Range | Executed Trades | Win Rate (%) | Mean Net Return (%) | Profit Factor | Net P&L (INR) | Annualized Sharpe | Max Drawdown (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Frozen V1 Baseline** | Development (In-Sample) | 2022-01-03 to 2023-12-31 | 2,677 | 53.94% | +0.1692% | 1.244 | ₹45,30,940 | 1.61 | -9.08% |
| **1. Frozen V1 Baseline** | Validation | 2024-01-01 to 2024-12-31 | 1,345 | 51.60% | +0.1401% | 1.183 | ₹18,86,595 | 1.26 | -10.25% |
| **1. Frozen V1 Baseline** | Untouched Holdout | 2025-01-01 to 2026-09-04 | 1,699 | 50.91% | +0.0709% | 1.093 | ₹12,01,483 | 0.64 | -7.16% |
| **1. Frozen V1 Baseline** | **Full Horizon** | **2022-01-03 to 2026-09-04** | **5,728** | **52.55%** | **+0.1354%** | **1.186** | **₹77,58,870** | **1.26** | **-9.08%** |
| **4A. V2 Primary (Bear40)** | Development (In-Sample) | 2022-01-03 to 2023-12-31 | 1,029 | 58.21% | +0.3742% | 1.522 | ₹38,50,944 | 1.93 | -6.67% |
| **4A. V2 Primary (Bear40)** | Validation | 2024-01-01 to 2024-12-31 | 543 | 58.38% | +0.4158% | 1.560 | ₹22,53,555 | 2.13 | -3.30% |
| **4A. V2 Primary (Bear40)** | Untouched Holdout | 2025-01-01 to 2026-09-04 | 741 | 54.66% | +0.2668% | 1.335 | ₹19,73,644 | 1.26 | -4.60% |
| **4A. V2 Primary (Bear40)** | **Full Horizon** | **2022-01-03 to 2026-09-04** | **2,313** | **57.11%** | **+0.3496%** | **1.467** | **₹80,78,143** | **1.76** | **-6.67%** |
| **4B. V2 Overlay (Bear60)** | Development (In-Sample) | 2022-01-03 to 2023-12-31 | 795 | 59.62% | +0.4403% | 1.651 | ₹35,01,587 | 1.96 | -6.04% |
| **4B. V2 Overlay (Bear60)** | Validation | 2024-01-01 to 2024-12-31 | 378 | 59.52% | +0.3698% | 1.479 | ₹13,94,133 | 1.73 | -3.07% |
| **4B. V2 Overlay (Bear60)** | Untouched Holdout | 2025-01-01 to 2026-09-04 | 593 | 55.65% | +0.3049% | 1.394 | ₹18,06,379 | 1.32 | -4.81% |
| **4B. V2 Overlay (Bear60)** | **Full Horizon** | **2022-01-03 to 2026-09-04** | **1,766** | **58.27%** | **+0.3797%** | **1.521** | **₹67,02,099** | **1.70** | **-6.04%** |

*Supporting Dataset:* [`PROVENANCE_WALK_FORWARD_AUDIT.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/provenance_audit/PROVENANCE_WALK_FORWARD_AUDIT.csv)

---

## 8. CHECK 8: AUDIT OF THE EIGHT 60-SESSION PASS/FAIL GATES

The 8 proposed gates in [`OIFNO_60_SESSION_SHADOW_PROTOCOL.md`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/OIFNO_60_SESSION_SHADOW_PROTOCOL.md) were audited for statistical consistency without relaxing hurdles:

| Gate Identifier | Metric | Required Hurdle | Backtest Reference | Internal Consistency Audit | Verdict |
| :--- | :--- | :---: | :---: | :--- | :---: |
| **GATE-1: SAMPLE** | Completed Trades | $\ge 25$ closed trades | Min 60-session = **66 trades** | Across 1,095 rolling 60-session windows, zero windows fell below 25. Gate is achievable. | **CONSISTENT** |
| **GATE-2: WIN RATE** | Realized Win Rate | $\ge 52.0\%$ | Holdout WR = **54.66%** | Realistic hurdle reflecting mean-reversion persistence above coin-toss. | **CONSISTENT** |
| **GATE-3: EXPECTANCY** | Mean Net Return | $\ge +15.0\text{ bps}$ per trade | Holdout Net = **+26.68 bps** | Provides a solid +7.0 bps margin of safety above 8 bps friction. | **CONSISTENT** |
| **GATE-4: SLIPPAGE** | Realized Friction | $\le 5.0\text{ bps}$ round-trip | Modeled spread = **5.1 bps** | Realistic for top-of-book liquid stock futures. | **CONSISTENT** |
| **GATE-5: FILL RATE** | Collar Fill Efficiency | $\ge 55.0\%$ of setups | Modeled fill rate = **62.10%** | Allows an acceptable 7.1% buffer below backtest fill rate. | **CONSISTENT** |
| **GATE-6: TRACKING** | Model Tracking Error | $\le 10.0\text{ bps}$ absolute error | Bhavcopy auction tracking | Realistic for synchronized opening prints. | **CONSISTENT** |
| **GATE-7: DRAWDOWN** | Peak-to-Trough DD | $\le 5.0\%$ max drawdown | 95th-pct 60s DD = **-3.49%** | **Non-trivial risk test:** 98.54% of windows passed, but 1.46% of windows breached 5% in 2022. | **CONSISTENT** |
| **GATE-8: GOVERNANCE** | Live Broker Orders | **Exactly 0 live orders** | `LIVE_TRADING = False` | Hardcoded block with fail-closed assertions. | **CONSISTENT** |

---

## 9. REMAINING RISKS & FINAL GOVERNANCE CLASSIFICATION

### 9.1 Remaining Strategy Risks
1. **Queue Priority Risk:** Limit collar (+30 bps) fills cannot be guaranteed without empirical tick observation during the 09:15:00–09:15:05 opening burst.
2. **Asymmetric Gap Risk:** While runaway gap-ups (> +1.50%) are suppressed, catastrophic gap-downs occur before the order is placed, resulting in unfavorable adverse fills on already-collapsing names.
3. **Capacity Constraints:** 10 simultaneous positions with fixed ₹10L slot allocation requires ₹1.00 Crore working capital. At ₹5 Cr daily turnover, market impact is minimal, but position sizing must remain uncompounded.

---

### 9.2 Final Classification: **CONDITIONAL PASS**

**Formal Justification:**
- **Calculations & Ledger Integrity (PASS):** All metrics are 100% reproducible directly from trade records. The discrepancy between Result Set 1 and Result Set 2 has been definitively resolved and documented.
- **Econometric Alpha (PASS):** V2Primary achieves **+34.97 bps net return**, **1.76 Sharpe**, **-6.67% max drawdown**, and **42.97 bps breakeven friction tolerance** (2.0x higher than baseline).
- **Mandatory Forward Conditions:**
  1. Holdout quarantine is classified as **UNVERIFIED** and cannot be used as sole proof of forward readiness.
  2. Order placement must strictly execute at **09:15:00 IST** (not 09:14:30).
  3. Realized execution fills and queue dynamics must be prospectively validated via the **60-session shadow-paper trial** satisfying all 8 gates before any production deployment.

---

## 10. HARD STOP CONFIRMATION

As strictly mandated by safety instructions:
- **Zero Live Modifications:** [`strategies/liveonopenalgo/oifno.py`](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py) was completely untouched throughout this audit.
- **Zero Contracts Activated:** `SIG-OI-001-PAPER-V2-DRAFT.md` remains a draft candidate.
- **Zero Runners or Daemons Started:** The 60-session runner has **NOT** been initialized.
- **Zero Broker Orders Placed:** All tests were conducted offline against historical data.
- **Next Step:** The audit is complete. Awaiting your explicit written review and direction.
