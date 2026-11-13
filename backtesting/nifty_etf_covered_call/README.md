# Covered Call Strategy — Quantitative Research Project

Welcome to the **Covered Call Strategy** research repository. This is an independent, institutional-grade quantitative research project dedicated to the systematic modeling, backtesting, validation, and evaluation of covered call (buy-write) overlay strategies in the Indian financial markets (NSE/BSE).

---

## 1. STRATEGY IMPLEMENTATION ARCHITECTURE

### Primary Strategy Specification
The primary research strategy is:
$$\mathbf{LONG\ NIFTYBEES\ (Cash\ Equity\ ETF)\ +\ SHORT\ NIFTY\ 50\ CALL\ (F\&O)}$$

* **Underlying Leg:** Physical units of Nippon India ETF Nifty BeES (`NIFTYBEES`) held in Demat account.
* **Option Overlay Leg:** Monthly ~2% OTM European Call Options on NIFTY 50 (`OPTIDX NIFTY CE`).
* **Role of NIFTY Futures:** The futures-based Buy-Write (`Long NIFTY Futures + Short NIFTY Call`) is retained strictly as a **secondary comparative research benchmark** in Phase 4+, but is **NOT** the primary Covered Call baseline.

---

## 2. NIFTYBEES COVERED CALL IMPLEMENTATION

### 2.1 Critical Structural Distinction vs. Futures Buy-Write
The NIFTYBEES Covered Call operates across two distinct market segments:

```text
========================================================================================
             STRUCTURAL COMPARISON: CASH ETF BUY-WRITE VS. FUTURES BUY-WRITE
========================================================================================
 Dimension                NIFTYBEES + Short NIFTY Call           NIFTY Futures + Short NIFTY Call
----------------------------------------------------------------------------------------
 Market Segment           Cross-Segment: Cash (CM) + F&O         Single-Segment: F&O only
 Delivery / Custody       Actual delivery to Demat account       Zero delivery; pure financial derivative
 Margining Architecture   100% upfront cash for ETF (or pledge)  SPAN + Exposure cross-margining
 Margin Offset            Zero direct cross-margining in F&O     Direct margin relief (~₹80k-1.1L total)
 Settlement Mismatch      CRITICAL: ETF cannot settle option!    Unified cash MTM & settlement in F&O
 ITM Expiry Outcome       Cash debited from trading account;     Cash debit netted against long future
                          NIFTYBEES remains intact in Demat      terminal settlement automatically
 Cash Call / Deficit Risk High if unbuffered cash is depleted    Zero cash-deficit risk if funded
 Tracking Risk            TER drag, cash drag, tracking error    Zero ETF tracking error (cost-of-carry only)
 Dividend Impact          Accrues to investor via ETF NAV (TRI)  Foregone/discounted in futures basis
 Statutory Tax Bucket     Equity LTCG (12.5%) / STCG (20%)       Non-speculative business income
========================================================================================
```

### 2.2 The Non-Delivery Invariant: Settlement Mismatch
Under SEBI regulations, NIFTY 50 index options are **strictly cash-settled**.
* **ETF Units Cannot Settle Options:** When a short call expires in-the-money (ITM), NCL debits cash directly from the trading account. **The ETF units remain completely untouched in Demat**.
* **Cash Buffer Requirement:** The portfolio must maintain an unencumbered liquid cash cushion to absorb potential ITM cash debits. In our ₹15,00,000 reference portfolio, purchasing 1 lot equivalent of NIFTYBEES leaves **₹3.76L to ₹7.12L in cash**, easily absorbing the highest historical ITM cash debit (₹56,435 in Dec 2023).

### 2.3 Dynamic Hedge Ratio Engine
The relationship between NIFTYBEES units and 1 NIFTY option lot is governed by:
$$\mathbf{Q_t^{\text{required}} = \frac{S_t \times L_t}{P_t} = L_t \times \left(\frac{S_t}{P_t}\right) = L_t \times R_t}$$

Where:
* $S_t$ = NIFTY 50 Spot Index level.
* $P_t$ = NIFTYBEES market price.
* $L_t$ = Market lot size on trade date (50 pre-April 2024, 25 May–Nov 2024, 75 post-Nov 2024).
* $R_t = S_t / P_t \approx 91.24$ (Mean ratio).
* Required units: **4,523 to 4,639 units** when lot size was 50; **2,243 to 2,256 units** when lot size was 25.

---

## 3. Mandatory Directory & Research Governance

* **Mandatory Project Path:**
  ```text
  ~/backtesting/covered call/
  ```
  All research, specifications, datasets, audit logs, and reports MUST remain strictly confined to this directory.
* **Research vs. Execution Separation:**
  * `~/backtesting/` is the **RESEARCH** environment.
  * `~/strategy/` is the **APPROVED EXECUTION** environment.
* **Execution Boundary Policy:** No strategy may ever be placed into `~/strategy/` or connected to OpenAlgo until it has completed all quantitative validation gates.
* **Non-Interference:** This project does not touch, modify, or depend upon any existing strategy or research project (e.g., `macdfno.py`, MACD research, Ichimoku research).

---

## 4. Quantitative Research Lifecycle & Status

```text
========================================================================================
                          QUANTITATIVE STRATEGY RESEARCH PIPELINE
========================================================================================
   [ 1. IDEA / CONCEPT ]                                         [ COMPLETED ]
            │
            ▼
   [ 2. STRATEGY SPECIFICATION (Phase 1) ]                       [ COMPLETED ]
            │
            ▼
   [ 3. NIFTYBEES FEASIBILITY & DATA AUDIT (Phase 2) ]            [ COMPLETED ✅ ]
            │
            ▼
   [ 4. MECHANICAL BASELINE BACKTEST (Phase 3) ]                 [ COMPLETED ✅ ]
            │
            ▼
   [ 5. CONTROLLED IN-SAMPLE RESEARCH (Phase 4) ]                [ CURRENT ACTIVE STAGE 🟢 ]
            │
            ▼
   [ 6. OUT-OF-SAMPLE & WALK-FORWARD VALIDATION (Phase 5) ]
            │
            ▼
   [ 7. STRESS TESTING, SENSITIVITY & ROBUSTNESS (Phase 6) ]
            │
            ▼
   [ 8. FORMAL STRATEGY FREEZE (Immutable Spec & Code) ]
            │
            ▼
   [ 9. FORWARD PAPER OBSERVATION (Phase 7) ]
            │
            ▼
   [ 10. FORMAL APPROVAL GATEWAY ]
            │
            ▼
   [ 11. PRODUCTION EXECUTION (~/strategy/<strategy>/ -> OpenAlgo) ]
========================================================================================
```

---

## 5. Directory Structure & Artifact Manifest

```text
covered call/
│
├── README.md                                # Project overview, governance SOP, and status
├── strategy_spec.md                         # Formal Phase-1 Strategy Specification Charter
│
├── data/                                    # Phase-2 Feasibility & Data Architecture
│   ├── contract_specifications.md           # NIFTYBEES & NIFTY 50 contract rules, lot sizes & settlement
│   ├── data_sources.md                      # Dual-segment Bhavcopy & YF data source evaluation
│   ├── data_schema.md                       # Normalized ETF, options, and strategy cycle schema
│   └── data_audit_report.md                 # Programmatic audit report (635 days, 31 cycles, empirical tables)
│
├── baseline/                                # Phase-3 Pure mechanical, non-optimized baseline engine
│   ├── engine.py                            # Production backtest execution engine
│   ├── cycle_ledger.parquet / .csv          # Complete 31-cycle trade execution ledger
│   ├── daily_equity.parquet / .csv          # 631-day daily MTM equity curves vs benchmarks
│   └── baseline_backtest_report.md          # Comprehensive baseline metrics report
├── research/                                # Phase-4 In-sample hypothesis testing & comparative futures research
├── validation/                              # Phase-5 Out-of-sample holdout & walk-forward tests
├── forward/                                 # Phase-7 Forward paper-observation logs & audit tickets
└── reports/                                 # Final quantitative fact sheets & teardown reports
```
