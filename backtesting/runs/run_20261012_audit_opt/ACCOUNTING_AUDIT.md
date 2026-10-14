# PHASE B — BACKTEST ACCOUNTING AUDIT REPORT
**Run Directory:** `backtesting/runs/run_20261012_audit_opt/`  
**Audit Date:** 2026-10-12 19:22 IST  

---

## 1. Executive Summary & Verification Methodology

A forensic quantitative audit was conducted across the 33-symbol NFO dataset (166,444 completed 1H bars, 2023-09-29 to 2026-09-09) to verify chronological sequencing, return calculations, and intrabar execution order.

---

## 2. Forensic Discoveries & Critical Vulnerabilities

### A. Intrabar Ordering Ambiguity in the "Standard" Trailing Runner
* **Vulnerability:** In the standard trailing backtest implementation, when price touches the profit target (+3.0% Long / +1.5% Short), the trailing runner was activated and evaluated on the **exact same 1-Hour candle**.
* **Empirical Evidence:** In **1,916 out of 1,961 target touches (97.7%)**, the candle's low breached the trailing stop (`Low <= High * (1 - 0.35%)`).
* **Distortion Effect:** Assuming the trailing stop locked in peak profit on the same bar produced **+939.4% in artificial lookahead alpha**. In reality, on 527 Longs and 406 Shorts, the trailing stop price was actually *worse* than the target price itself at the moment of touch.
* **Accounting Resolution:** The **Conservative Model** enforces that trailing stop evaluation strictly begins on **candle $N+1$**. This removes lookahead bias.

### B. Understanding "Max Drawdown > 100%"
* In the raw research CSVs, net return was computed as a simple arithmetic sum of percentage returns ($\sum \Delta\%$), which led to cumulative drawdown metrics exceeding 100% (-175.3% on unhedged baseline).
* When evaluated on a per-trade capital-allocated account basis, drawdown represents cumulative adverse excursion across consecutive sequences of losses.

### C. Realized vs. Unrealized P&L
* When a position reaches its target in the runner model, **0% of the position was partially closed**; 100% converted to a trailing runner.
* Accounting confirms: Unrealized target gains are **never credited as realized P&L** until the position is officially closed by `RUNNER_HWM_TRAIL`, `CATASTROPHE_SL`, or `V2-2_REVERSAL`.

---

## 3. Backtest Accounting Audit Verdict

| Audit Checklist | Status | Detail |
| :--- | :--- | :--- |
| **Chronological Ordering** | **PASS** | Strict timestamp sequencing verified across all 2,143 trades |
| **Future-Candle Leakage** | **PASS** | Fixed via Conservative Next-Bar Trailing model |
| **Transaction Friction** | **PASS** | 0.07% round-trip baseline friction applied consistently |
| **Catastrophe SL Precedence** | **PASS** | Emergency SL (-6.0%) executes ahead of targets if breached |
| **Holdout Integrity** | **PASS** | 2026 holdout (514 trades) kept untouched during parameter derivation |

**Accounting Audit Verdict:** **PASS (Conditioned on Conservative Lookahead-Free Execution)**
