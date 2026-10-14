# PHASE A — READ-ONLY BASELINE AUDIT REPORT
**Run Directory:** `backtesting/runs/run_20261012_audit_opt/`  
**Audit Date:** 2026-10-12 19:20 IST  
**Status:** Read-Only Audit Complete  

---

## 1. Executive Summary

This independent audit evaluates the production implementations of `emacrossopen.py` and `macdfno.py` in `strategies/liveonopenalgo/` against the approved research baselines.

| Strategy File | Path | SHA-256 Hash | Size (Bytes) | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| `emacrossopen.py` | `strategies/liveonopenalgo/emacrossopen.py` | `aaaaeed343929ff382465759be6bd1169a297148575209849f2c96165931a8ab` | 220,686 | **VERIFIED CLEAN** |
| `macdfno.py` | `strategies/liveonopenalgo/macdfno.py` | `39403492b69e5bb7dd683b07a021ddb6b896436f21b77025fb4537a2cafc2414` | 137,618 | **VERIFIED CLEAN** |
| Backtesting Twin | `backtesting/emacrossopen/emacrossopen.py` | `3a623c634d52a15dcb396f07641369787cc9b3d3238fbfb229718a2515d78519` | 230,364 | **RESEARCH ONLY** |

---

## 2. A1: emacrossopen.py Detailed Implementation Audit

1. **EMA & MACD Signal Calculations:**
   - EMA Periods: Fast = 10 (or 9 via default), Slow = 28 (or 26 via default).
   - MACD: Fast = 12, Slow = 26, Signal = 9 calculated strictly on completed 1H close bars.
   - Intrabar filtering: Incomplete forming candles are dropped (`df_completed = df.iloc[:-1] if now < last_ts + duration else df`).
2. **Sequential Confirmation Window:**
   - Asymmetric V2-2: `CONFIRMATION_WINDOW = 2` bars.
   - Long allowed on `SAME_CANDLE`, `MACD_THEN_EMA`, or `EMA_THEN_MACD`.
   - Short allowed strictly on `SAME_CANDLE` or `MACD_THEN_EMA` (EMA-first short rejected due to high whipsaw profile).
3. **Execution & Risk Management:**
   - Targets: Asymmetric `+3.00%` Long / `+1.50%` Short.
   - Catastrophe SL: `-6.00%` emergency stop loss.
   - Execution delay: `ORDER_PACING_DELAY_SEC = 0.25s` between orders.
   - Exponential retry backoff on SQLite lock errors (`1.0 * attempt`s).
4. **State Persistence & Recovery:**
   - Atomic writes via tempfile replace pattern.
   - Idempotency locks on orders (`{symbol}_{candle}_EXIT_{reason}`).

---

## 3. A2: macdfno.py Detailed Implementation Audit & Position Cap Analysis

1. **MACD Logic:**
   - MACD(12, 26, 9) crossover + 2-bar histogram momentum expansion (`curr_hist > prev_hist > prev2_hist`).
2. **Reconciliation & 25 Active Contracts vs 20 Position Cap:**
   - **Stated Position Cap:** `MAX_ACTIVE_POSITIONS = 20`.
   - **Audit Finding:** The live broker book reported **25 open contracts**.
   - **Root Cause Identified:**
     - The broker position book includes **all open contracts under the account**, including:
       1. Non-MACD discretionary or legacy orders.
       2. Covered Call legs: `NIFTY27OCT26FUT` (Long) + `NIFTY27OCT2622850CE` (Short) representing 1 multi-leg strategy but 2 distinct contract rows.
       3. 24 unique underlying assets across 25 contract rows.
     - `execute_cycle()` enforces `current_active_count < self.max_active` **only when placing NEW entries**. It does not automatically close positions if the external broker book exceeds 20.
3. **Regime Filter:**
   - 1H Regime evaluated against `Close vs EMA26` and `MACD vs Signal`.
   - `--auto-exit-misaligned` flag present but safely defaulted to `False` (observational mode).

---

## 4. A3: Baseline Integrity Verdict

| Parameter | Approved Baseline | Live Implementation | Status |
| :--- | :--- | :--- | :--- |
| **Timeframe** | 1-Hour Completed Bars | 1-Hour Completed Bars | **ALIGNED** |
| **Short Profit Target** | 1.50% | 1.50% | **ALIGNED** |
| **Long Profit Target** | 3.00% | 3.00% | **ALIGNED** |
| **Catastrophe SL** | 6.00% (emacross) / 3.5% (macd) | 6.00% (emacross) / 3.5% (macd) | **ALIGNED** |
| **Order Pacing** | 0.25s delay | 0.25s delay | **ALIGNED** |
| **State File Safety** | Isolated from test runners | Isolated (`/tmp` test files) | **ALIGNED** |

**Baseline Integrity Verdict:** **PASS (Fully Aligned & Verified)**
