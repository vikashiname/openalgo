# 30-DAY FORWARD PAPER-SHADOW VALIDATION PROTOCOL: TARGET-TO-RUNNER

**Document Version:** 1.0 (Research Gating Specification)  
**Creation Date:** 08-Oct-2026  
**Status:** ACTIVE PROTOCOL (30-DAY FORWARD EVALUATION)  
**Production Freeze Level:** **CRITICAL HARD FREEZE — ZERO LIVE CODE MODIFICATION**  

---

## 1. HARD PRODUCTION FREEZE CONFIRMATION

The following production strategy files are **FROZEN** and will **NOT** be modified, deployed, uploaded, or restarted under any circumstances during this evaluation:

- [`strategies/liveonopenalgo/emacrossopen.py`](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/emacrossopen.py)
- [`strategies/liveonopenalgo/macdfno.py`](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py)

### Current Frozen Production Target & Risk Parameters:
* **LONG Trades:** `+3.00%` Fixed Hard Target
* **SHORT Trades:** `+1.50%` Fixed Hard Target
* **Catastrophe Stop-Loss:** `-10.00%` Hard Risk Cap
* **Primary Exit:** V2-2 Confirmed Opposite-Signal Reversal
* **Entry Engine:** Unchanged (Completed 1H candles, 2-bar confirmation window)

---

## 2. SHADOW EXPERIMENTAL CANDIDATE (RESEARCH ONLY)

The shadow candidate runs strictly in an observational, research-only environment:

### Candidate Parameters Under Evaluation:
* **LONG Positions:**
  * Target Touch: `+3.00%` (Does **not** immediately close to flat).
  * Trailing Mechanism: **High-Watermark (HWM) Trail**.
  * Trail Distance: **`0.50%`** below the highest peak price reached after the +3.00% target touch.
* **SHORT Positions:**
  * **Retain Fixed Target (`+1.50%`)** (Trailing is mathematically rejected for shorts due to violent mean-reverting short squeezes).
* **Catastrophe SL & Reversals:**
  * Identical to production baseline (`-10.00%` SL and opposite V2-2 reversal).

---

## 3. REQUIRED 30-DAY SHADOW TRACKING METRICS

The research tracker ([`shadow_runner_validator.py`](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/shadow_runner_validator.py)) records the following metrics separately for **LONG** and **SHORT** positions into [`shadow_validation_log.csv`](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/shadow_validation_log.csv):

1. **Target-Touch Count** (Trades reaching +3.0% Long / +1.5% Short)
2. **Runner Activation Count** (Trades transitioning to active trail)
3. **Maximum Favorable Excursion (MFE)** post-target
4. **Peak Profit (%)** achieved before exit
5. **Trailing Exit Profit (%)** realized
6. **Profit Giveback (%)** (`Peak Profit - Final Realized Profit`)
7. **Fixed-Target Equivalent Profit (%)** (Control group outcome)
8. **Incremental P&L (%)** (`Shadow Realized P&L - Control Realized P&L`)
9. **Profit Factor (PF)** (Control vs. Shadow)
10. **Win Rate (%)** (Control vs. Shadow)
11. **Maximum Drawdown (%)** (Control vs. Shadow)

---

## 4. PROMOTION GATING RULES (TO BE EVALUATED AT DAY 30)

No production implementation will occur unless all 7 criteria are satisfied upon completion of the 30 calendar days:

| # | Gate Requirement | Evaluation Threshold | Status |
| :---: | :--- | :--- | :---: |
| **G1** | **Incremental Alpha** | Total Shadow Net P&L > Production Control Net P&L on LONGs | Pending Day 30 |
| **G2** | **Profit Factor Stability** | Shadow PF ≥ Production Control PF on LONGs | Pending Day 30 |
| **G3** | **Drawdown Containment** | Shadow Max DD does not exceed Production Max DD by > 5.0% | Pending Day 30 |
| **G4** | **Controlled Giveback** | Average profit giveback per runner ≤ `0.75%` | Pending Day 30 |
| **G5** | **Short Integrity** | SHORT trades remain on fixed target (+1.50%) without degradation | Pending Day 30 |
| **G6** | **Sample Size** | At least 25 target-touch events evaluated during the forward window | Pending Day 30 |
| **G7** | **Zero Execution Slippage Drag** | Live fill simulation matches backtest within 0.05% tracking error | Pending Day 30 |

---

## 5. STRICT RULE: NO AUTOMATIC PROMOTION

**Under NO circumstances will automatic production promotion occur.**

* **Even if ALL Day-30 promotion criteria pass with 100% success:**
  1. **DO NOT** modify `strategies/liveonopenalgo/emacrossopen.py` or `strategies/liveonopenalgo/macdfno.py`.
  2. **DO NOT** deploy to AWS or any live/production server.
  3. **DO NOT** upload anything to OpenAlgo.
  4. **DO NOT** restart or reconfigure any live process.
* **At Day 30 Action:** Produce the comprehensive 30-day forward validation research report only and **STOP**.
* **Promotion Requirement:** Any future production deployment strictly requires a separate, explicit, unambiguous user instruction and approval.

---

## 6. AUDIT & SAFETY VERIFICATION

```bash
# Verify production files remain 100% clean
$ git diff -- strategies/liveonopenalgo/emacrossopen.py
(Clean - 0 modifications)

$ git diff -- strategies/liveonopenalgo/macdfno.py
(Clean - 0 modifications)
```

* **Production Environment:** **FROZEN.**
* **OpenAlgo Host Uploads:** **ZERO.**
* **AWS / Live Deployments:** **ZERO.**
* **Live Strategy Restarts:** **ZERO.**
