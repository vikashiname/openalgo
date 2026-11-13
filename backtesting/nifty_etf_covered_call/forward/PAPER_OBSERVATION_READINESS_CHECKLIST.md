# AGY FORWARD PAPER-OBSERVATION READINESS CHECKLIST
## Candidate: EXP-064-INT5 Covered Call Strategy

**Checklist ID:** AGY-CHK-CC-001  
**Candidate Name:** Systematic NIFTY Covered Call Overlay (Candidate `EXP-064-INT5`)  
**Scope:** `~/backtesting/covered call/forward/`  
**Evaluation Status:** PRE-FLIGHT AUDIT COMPLETE — EXPLICIT READINESS SCORES ASSIGNED  
**Date:** October 13, 2026  

---

## 1. Readiness Dimension Checklist & Audit Scores

```text
========================================================================================================
                          PAPER-OBSERVATION READINESS SCORECARD
========================================================================================================
 Dimension / Component             Audit Score     Readiness Assessment & Audit Notes
--------------------------------------------------------------------------------------------------------
 1. Strategy Parameter Spec        PASS            Short delta 0.25, profit target 80%, stop loss 3.0x,
                                                   roll 7 trading sessions, 100 EMA trend filter defined.
 2. Baseline Benchmark Anchor      PASS            Mechanical baseline (Delta 0.30, T90%, SL3x, R10D)
                                                   frozen and anchored at ₹10,13,946 net PnL.
 3. Statutory Tax & Cost Model     PASS            Official NSE rate schedule (STT 0.10%, Brokerage ₹20,
                                                   Exch 0.03503%, SEBI ₹10/Cr, Stamp 0.003%, GST 18%).
 4. Holiday Roll Logic             PASS            Holiday-aware trading session counter implemented
                                                   and empirically verified against NSE holiday calendar.
 5. PnL & Daily NAV Engine         PASS            Mathematical reconciliation passed with 0.000000 rupee
                                                   discrepancy between ledger and daily MTM NAV.
--------------------------------------------------------------------------------------------------------
 6. Hedge Parity & Sizing Integrity FAIL           CRITICAL STRUCTURAL DEFECT: Fractional ETF sizing
                                                   against an indivisible 1-lot option creates an under-
                                                   covered ratio call write with UNLIMITED UPSIDE RISK.
 7. Contemporaneous Data Feed      INCONCLUSIVE    OpenAlgo `/api/v1/quote` identified as reliable source,
                                                   but contemporaneous feed adapter is not yet wired.
 8. Execution Logging Daemon       INCONCLUSIVE    Post-market append-only daemon architecture defined,
                                                   but deployment is blocked awaiting explicit approval.
 9. Non-Linear Crash Stress Model  INCONCLUSIVE    Crash testing remains a static linear approximation;
                                                   gamma convexity, vega expansion & skew are unmodeled.
 10. Explicit User Approval        INCONCLUSIVE    Governance hard stop in effect. No paper process may
                                                   launch without user's explicit separate approval.
========================================================================================================
```

---

## 2. Detailed Technical Findings by Dimension

### A. Passed Dimensions (Ready for Execution)
1. **Strategy Parameter Specification [PASS]:** The candidate configuration (`Delta 0.25`, `Target 80%`, `SL 3.0x`, `Roll 7 TS`, `100 EMA`) is unambiguously codified and validated against 7.56 years of historical options settlements.
2. **Baseline Benchmark Anchor [PASS]:** The mechanical baseline is permanently anchored at ₹10,13,946.09 net PnL, providing a fixed reference for all comparative tracking.
3. **Statutory Tax & Cost Engine [PASS]:** The Indian derivatives fee model accurately computes STT (0.10% on sell premium), exchange turnover charges (0.03503%), SEBI fees (₹10/Cr), stamp duty (0.003%), and 18% GST.
4. **Holiday-Aware Roll Logic [PASS]:** The trading session counter correctly evaluates market days to contract expiry, eliminating weekend decay traps and holiday distortions.
5. **PnL & NAV Integrity Engine [PASS]:** Verified with exact 0.000000 rupee reconciliation between transaction ledgers and daily mark-to-market NAV curves.

---

### B. Failed Dimensions (Critical Blocker)
1. **Hedge Parity & Sizing Integrity [FAIL]:**
   * **The Defect:** Proposing fractional ETF (`NIFTYBEES`) sizing (e.g. allocating 75% of ₹15L capital = ₹11.25L in ETF = ~45 index shares) against an exchange-mandated **indivisible 1-lot option contract (65 index shares)** destroys covered-call parity.
   * **The Hazard:** If NIFTY rallies strongly past the strike, the short call requires delivering/settling 65 shares of intrinsic loss, while the ETF only appreciates on 45 shares. The position turns **NET SHORT 20 NIFTY SHARES**, exposing the portfolio to **UNLIMITED UPSIDE LOSSES**.
   * **Mandatory Resolution:** Fractional ETF sizing must be **REJECTED**. The strategy must either:
     - **Path 1:** Fund 1 full lot of `NIFTYBEES` (65 shares = ~₹16.5L notional) by increasing portfolio capital to ₹18.0L.
     - **Path 2:** Execute a unified single-segment **Futures Buy-Write (`Long 1 NIFTY Future + Short 1 NIFTY Call`)** within ₹15.0L capital (requiring only ~₹1.1L SPAN margin and sweeping ~₹13.9L into liquid yield).

---

### C. Inconclusive Dimensions (Pending Implementation & Approval)
1. **Contemporaneous Market Data Feed [INCONCLUSIVE]:**
   * OpenAlgo's normalized `/api/v1/quote` endpoint has been identified as the optimal non-broker-order quote source for 15:15 IST top-of-book bid/ask quotes.
   * However, the live feed adapter script has not yet been built or connected.
2. **Execution Logging Daemon [INCONCLUSIVE]:**
   * The append-only logging daemon (`forward_daily_nav.csv`) has been specified, but remains undeployed in strict compliance with governance rules.
3. **Non-Linear Crash Stress Model [INCONCLUSIVE]:**
   * Stress models rely on a static linear net-delta approximation ($\Delta_{net} \approx 0.75$) on stop-loss exits.
   * Real-time gamma acceleration, vega spikes (IV expansion), and skew steepening are unmodeled and must be tracked empirically during forward paper observation.
4. **Explicit User Approval [INCONCLUSIVE]:**
   * Formal project governance prohibits launching forward observation without explicit user sign-off.

---

## 3. Governance Hard Stop Certification

In strict adherence to project governance:
- **Zero code, parameters, or configurations** inside `~/strategy/`, `strategies/liveonopenalgo/`, `macdfno.py`, `emacrossopen.py`, OpenAlgo, or AWS services were touched or modified.
- **Zero background daemons, cron jobs, paper trading loops, or broker connections** were launched.
- All historical artifacts, baselines, and validation reports remain preserved intact.

**Awaiting user decision on the underlying instrument architecture (Path 1 vs Path 2) before proceeding.**
