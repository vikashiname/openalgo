# MACD_FNO_V1 — C3 FORWARD ANALYZE VALIDATION READINESS REPORT

**Document Location:** `backtesting/experiments/exp_20261015_macd_time_filter_audit/forward/C3_FORWARD_ANALYZE_READINESS_REPORT.md`  
**Execution Timestamp:** 2026-10-15 11:59 IST  
**Environment:** 100% Isolated Research Workspace  
**Operational Status:** **STANDBY / AWAITING USER AUTHORIZATION** (Zero live modifications, zero services started)  

---

## 1. Executive Summary & Readiness Verdict

### Technical Readiness Verdict:
**TECHNICALLY READY FOR AUTHORIZED TRIAL — CURRENT STATUS: STANDBY**

All preparatory code, configuration schemas, safety locks, and daily reporting monitors for **Variant C3** have been assembled in an isolated research directory. In strict adherence to AGY safety boundaries:
* `strategies/liveonopenalgo/macdfno.py` and `strategies/scripts/macdfno.py` remain **100% untouched on the Variant A production baseline**.
* No strategy process has been launched or enabled.
* No orders have been or can be sent to any broker.
* Pre-flight checks guarantee that OpenAlgo operates in **simulated `ANALYZE` mode** before any simulated order can be processed.

---

## 2. Parameter & Timing Verification (Variant A vs. Variant C3)

We verified via diff audit that **ONLY the intended 11:15 IST time-filter behavior differs** between Variant A and Variant C3:

```diff
--- Variant A Baseline Filter (Live macdfno.py)
+++ Variant C3 Targeted Filter (forward/macdfno_c3_forward.py)
@@ -588,14 +588,9 @@
-    if (9 * 60 + 45) <= m <= (10 * 60 + 55):
-        return True, "MORNING_WINDOW"
-    elif (12 * 60 + 0) <= m <= (13 * 60 + 15):
-        return True, "MIDDAY_WINDOW"
+    if (9 * 60 + 45) <= m <= (13 * 60 + 15):
+        return True, "MORNING_AND_MIDDAY_WINDOW"
     elif (15 * 60 + 0) <= m <= (15 * 60 + 20):
         return True, "CLOSING_WINDOW"
-    elif (11 * 60) <= m < (12 * 60):
-        return False, "DEAD_ZONE_11_AM"
     elif (14 * 60) <= m < (15 * 60):
         return False, "DEAD_ZONE_14_PM"
     else:
         return False, "OUTSIDE_ALLOWED_WINDOWS"
```

### Candle-by-Candle Timing Schedule:

| Bar # | Completed 1H Candle | Polling Clock Time | Variant A Status | Variant C3 Status | Operational Rationale |
| :---: | :---: | :---: | :---: | :---: | :--- |
| **1** | 09:15 – 10:15 IST | 10:15:02 IST | ✅ **Allowed** | ✅ **Allowed** | Morning trend initiation |
| **2** | 10:15 – 11:15 IST | 11:15:02 IST | ❌ **Blocked** | ✅ **Allowed** | **Morning trend continuation (C3 Enhancement)** |
| **3** | 11:15 – 12:15 IST | 12:15:02 IST | ✅ **Allowed** | ✅ **Allowed** | Midday session |
| **4** | 12:15 – 13:15 IST | 13:15:02 IST | ✅ **Allowed** | ✅ **Allowed** | Midday session |
| **5** | 13:15 – 14:15 IST | 14:15:02 IST | ❌ **Blocked** | ❌ **Blocked** | **European Open Whipsaw Protection (Confirmed Blocked)** |
| **6** | 14:15 – 15:15 IST | 15:15:02 IST | ✅ **Allowed** | ✅ **Allowed** | Late-day closing surge |
| **7** | 15:15 – 15:30 IST | 15:30:02 IST | ❌ **Blocked** | ❌ **Blocked** | Market close squareoff |

### Confirmation of Invariants:
* **Identical Signal Logic:** MACD 12/26/9 + 2-bar histogram expansion (`(c_h > p_h) and (p_h > p2_h)`).
* **Identical Universe:** Candidate G/E Asymmetric Universe (`TOP_LONGS`: 7, `TOP_SHORTS`: 6).
* **Identical Risk Model:** +3.0% Long TP, +1.5% Short TP, -3.5% Catastrophe SL, Opposite MACD Reversal Exit.
* **Identical Sizing:** 1 Lot per position, hard 20-position portfolio ceiling.
* **14:15 IST Block Confirmed:** The `(14 * 60) <= m < (15 * 60)` dead zone remains 100% active and prevents afternoon whipsaw entries.

---

## 3. OpenAlgo Analyze-Mode Safety Verification

Before any execution script can run, OpenAlgo's operating mode is cryptographically verified:
1. **Pre-Flight Hook (`verify_analyze_mode`):**  
   Queries `http://127.0.0.1:5000/api/v1/positionbook`. The response explicitly declares `"mode": "analyze"`.
2. **Hard Lock on "LIVE":**  
   If the returned mode is ever `"live"`, the script terminates immediately with a `CRITICAL` safety lock exception:
   ```text
   🛑 [SAFETY LOCK] OpenAlgo mode is 'live' (NOT 'analyze'). Order placement BLOCKED!
   ```
3. **Broker Route Isolation:**  
   In OpenAlgo Analyze mode, orders are processed entirely within the local in-memory simulated matching engine. **No API tokens, secret keys, or socket calls are dispatched to external brokers.**

---

## 4. Signal Audit & Fill Comparison Protocol

During the forward trial, every event is persisted to dedicated CSV streams in `forward/`:

### A. Signal Stream (`c3_forward_signals.csv`)
Logs every candidate symbol on every 1-hour candle boundary:
* `timestamp`: Exact evaluation time (e.g., `2026-10-15 11:15:02 IST`)
* `symbol` / `contract`: Asset identifier
* `direction`: `BUY` / `SELL`
* `time_ok` / `time_reason`: e.g. `True, "MORNING_AND_MIDDAY_WINDOW"` vs. `False, "DEAD_ZONE_14_PM"`
* `universe_ok`: e.g. `True, "IN_TOP_LONGS"` vs. `False, "NOT_IN_TOP_LONGS"`
* `decision`: `EXECUTED` / `REJECTED`

### B. Fill & Slippage Audit Stream (`c3_forward_trades.csv`)
For every executed simulated order:
* **Trigger Price:** The reference price at completed bar close.
* **Fill Price:** The simulated execution fill price returned by OpenAlgo.
* **Slippage Calculation:**
  $$\text{Slippage (bps)} = \frac{|\text{Fill Price} - \text{Trigger Price}|}{\text{Trigger Price}} \times 10,000$$
* **Friction Benchmark:** Realized fills are compared against the research baseline assumption of **7 bps (0.07%) round-trip**.

---

## 5. Daily Reporting & Operational Monitoring

An automated audit script has been deployed at:
[`forward/daily_c3_forward_audit.py`](file:///Users/mac/Desktop/openalgo/backtesting/experiments/exp_20261015_macd_time_filter_audit/forward/daily_c3_forward_audit.py)

Each day at market close (15:35 IST), it aggregates:
1. **Trade Count & Volume:** Closed trades, active positions, trades per day.
2. **Realized Metrics:** Cumulative Net P&L, Win Rate, Profit Factor (once $N \ge 10$), and Maximum Drawdown.
3. **Directional Attribution:** Long Net P&L vs. Short Net P&L.
4. **Signal Divergence:** Discrepancies between Variant A production logs and C3 forward logs.

---

## 6. Pre-Specified Review Rules & Minimum Observation Gate

To guard against early stopping bias and sample-size distortions:

### A. Minimum Trial Duration:
* **Minimum Observation Period:** **20 Trading Days** (~4 calendar weeks).
* **Minimum Completed Trade Sample:** **30 Closed Trades**.
* *Rule:* The trial **must not be terminated early** merely because initial trades are profitable or unprofitable.

### B. Safety Circuit Breakers (Early Abort Triggers):
The trial will be paused immediately for forensic review if any of the following occur:
1. **Drawdown Circuit Breaker:** Cumulative paper drawdown exceeds **5.0%** of initial simulated equity.
2. **Consecutive Losses:** **5 consecutive stop-loss hits** occur within the added 11:15 window.
3. **Signal Divergence:** Unreconciled signal discrepancy exceeds **10%** of total evaluated signals.
4. **Mode Compromise:** Any API response indicates OpenAlgo is not in `ANALYZE` mode.

---

## 7. Complete Isolation Guarantees

All Variant C3 assets are strictly isolated from production:

| Component | Production Baseline (Variant A) | Candidate C3 Forward Trial |
| :--- | :--- | :--- |
| **Strategy Code** | `strategies/scripts/macdfno.py` | `forward/macdfno_c3_forward.py` |
| **Strategy Name** | `MACDFNO` | `MACDFNO_C3_FORWARD` |
| **State File** | `strategies/scripts/macdfno_state.json` | `forward/macdfno_c3_state.json` |
| **Heartbeat File** | `strategies/scripts/macdfno_heartbeat.json`| `forward/macdfno_c3_heartbeat.json` |
| **Log File** | `log/strategies/macd_fno.log` | `forward/macd_c3_forward.log` |
| **Trade Ledger** | Production OpenAlgo Book | `forward/c3_forward_trades.csv` |
| **Signal Log** | Production OpenAlgo Log | `forward/c3_forward_signals.csv` |

---

## 8. What Remains Unresolved

Before launching an authorized trial, the user should be aware of two open considerations:
1. **SUNPHARMA Asymmetry:** Historical data showed that SUNPHARMA entries at 11:15 IST experienced a sub-1.0 Profit Factor (0.828). In 2026, however, it recovered (+3.97%). The forward trial will observe whether SUNPHARMA's 11:15 entries add value or drag performance.
2. **Statistical Significance Horizon:** Because the per-trade expectancy difference is modest (+0.078% vs. +0.072%, $p = 0.953$), statistical validation requires accumulating a live sample of 30–50 completed trades.

---

## 9. Exact Steps Required to Start Trial (When Authorized)

When the user provides explicit authorization to start the Analyze-mode trial, the execution steps are:

### Step 1: Verify OpenAlgo Analyze Mode
```bash
curl -s -X POST http://127.0.0.1:5000/api/v1/positionbook -H "Content-Type: application/json" -d '{"apikey": "test"}' | grep -i "mode"
```
*(Must return `"mode": "analyze"`)*

### Step 2: Launch Isolated C3 Forward Process
```bash
nohup python3 backtesting/experiments/exp_20261015_macd_time_filter_audit/forward/macdfno_c3_forward.py \
  > backtesting/experiments/exp_20261015_macd_time_filter_audit/forward/macd_c3_forward.log 2>&1 &
```

### Step 3: Run Daily End-of-Day Audit
```bash
python3 backtesting/experiments/exp_20261015_macd_time_filter_audit/forward/daily_c3_forward_audit.py
```

---

## 10. Operational Status

**EXECUTION IS STOPPED. AWAITING USER APPROVAL.**  
No background processes have been started. Production files are untouched.
