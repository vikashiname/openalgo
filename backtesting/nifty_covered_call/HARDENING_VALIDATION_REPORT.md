# NIFTY Covered Call — Hardening Validation Report

**Date:** 2026-10-16  
**Workspace:** `backtesting/nifty_covered_call/`  
**Primary Engine File:** [`backtesting/nifty_covered_call/nifty_covered_call_validated.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py)  
**Failure-Injection Suite:** [`backtesting/nifty_covered_call/test_hardening_failure_injection.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/test_hardening_failure_injection.py)  
**Pre-Deployment Suite:** [`backtesting/nifty_covered_call/test_pre_deployment_validation.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/test_pre_deployment_validation.py)  
**Risk Control Suite:** [`backtesting/nifty_covered_call/test_futures_risk_control.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/test_futures_risk_control.py)  
**Safety Status:** AWS Production remains **FLAT, STOPPED, AND DISARMED**. Zero production files modified; zero broker orders executed.

---

## 1. Executive Verdict & Summary

All four hardening patches identified during the independent validation gate were successfully implemented, verified against 9 failure-injection tests, and passed through full regression testing across all 36 automated test cases without a single failure or regression.

| Requirement / Milestone | Target Mechanism | Outcome | Status |
| :--- | :--- | :---: | :---: |
| **Patch 1: Active-Position Guard** | Guard head of [`execute_entry()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L395); reject duplicate entry attempts if state $\ne$ null. | Verified | **PASS** |
| **Patch 2: Partial Short-Call Fill Shield** | Cancel remainder, query positionbook, buyback exact partial call, verify buyback before touching futures. | Verified | **PASS** |
| **Patch 3: Verified Emergency Futures Unwind** | Check order acceptance, filled quantity, and final positionbook reconciliation in [`_emergency_close_futures()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L480). | Verified | **PASS** |
| **Patch 4: Configurable Cost Buffer** | Add `profit_target_cost_buffer = 1000.0` in [`evaluate_risk_and_exits()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L522) to prevent false exits. | Verified | **PASS** |
| **Failure-Injection Test Suite** | 9 adversarial failure scenarios in [`test_hardening_failure_injection.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/test_hardening_failure_injection.py). | 9 / 9 Passed | **PASS** |
| **Regression & Integrity Check** | Re-run all 3 backtest and mock test suites (36 tests total across codebase). | 36 / 36 Passed | **PASS** |
| **Trade Ledger & Cost Reconciliation** | Verify all 270 trades across 10 variants in [`research_all_trades.csv`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/research_all_trades.csv). | 100% Match | **PASS** |
| **Sandbox Readiness Assessment** | Comprehensive prerequisites, configuration boundaries, and rollback plan documented. | Staged / Awaiting User Approval | **PASS** |

---

## 2. Phase 1 — Detailed Implementation of the Four Hardening Patches

### Patch 1: Active-Position Guard in `execute_entry`
* **Vulnerability Resolved:** Previously, if `execute_entry()` was called when an active position was already open and matched 1:1 in the broker, reconciliation returned `True`, allowing duplicate orders to be placed.
* **Implementation:** Added an explicit guard at the top of [`execute_entry()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L402-L405):
  ```python
  if self.state.get("active_position") is not None:
      logger.warning("🛑 [DUPLICATE ENTRY REJECTED] Active position already exists in strategy state. Entry aborted.")
      return False
  ```

### Patch 2: Partial Short-Call Fill Handling & Orphan Prevention
* **Vulnerability Resolved:** If Leg 2 Call only filled partially (e.g. 30 out of 65 qty), previous logic treated it as an unfulfilled order and called `_emergency_close_futures(65)`. Selling 65 Long Futures left 30 Short Calls open in the broker as an **unhedged naked short call**.
* **Implementation:** Implemented [`_handle_call_fill_failure()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L500-L585):
  1. Cancels any open remainder order via `self.client.cancelorder(call_orderid)`.
  2. Queries broker `positionbook()` to detect actual short call exposure (`filled_call_qty`).
  3. If partial short calls are open (`filled_call_qty > 0`), submits a market `BUY` order for the exact partial quantity and verifies the fill.
  4. Only if the short call exposure is confirmed flat does it proceed to unwind the corresponding Long Futures leg.
  5. If buyback fails or position remains ambiguous, it preserves state with `emergency_unresolved = True` and raises a critical alert, preventing the futures from being dumped while short options remain.

### Patch 3: Verified Emergency Futures Liquidation
* **Vulnerability Resolved:** [`_emergency_close_futures()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L587-L635) previously returned `True` immediately upon sending the order without verifying fill, partial execution, or broker acceptance.
* **Implementation:**
  1. Checks broker order acceptance: `if r.get("status") != "success": return False`.
  2. Verifies complete execution via [`verify_order_fill(r, qty)`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L340); handles partial fills (`filled_qty < qty`) and open states.
  3. Re-queries broker `positionbook()` to confirm zero residual exposure for `fut_symbol`.
  4. If any check fails, returns `False` and invokes [`_record_emergency_exposure()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L480-L498) to save state for manual operator intervention.

### Patch 4: Configurable Combined-M2M Profit-Target Cost Buffer
* **Vulnerability Resolved:** Naive `net_m2m > 0` allowed trades with marginal gains (+₹100 to +₹300) to trigger 90% decay exit, resulting in a net realized loss after statutory fees.
* **Implementation:**
  1. Added `DEFAULT_PROFIT_TARGET_COST_BUFFER = 1000.0` in engine config.
  2. In [`evaluate_risk_and_exits()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L650-L660):
     ```python
     if curr_call_price <= pos["target_price"]:
         if net_m2m >= self.profit_target_cost_buffer:
             return True, "PROFIT_TARGET_HIT (90% Decay)"
         else:
             logger.warning(
                 f"⚠️ [DOWNSIDE/COST TRAP DEFLECTED] Call hit 90% decay (₹{curr_call_price:.2f}) but Combined M2M (₹{net_m2m:+,.2f}) "
                 f"is below profit-target cost buffer (₹{self.profit_target_cost_buffer:,.2f}). Rejecting premature exit."
             )
     ```

### Cost Buffer Evaluation & Limitations:
* **Statutory Cost Breakdown (1 Lot NIFTY F&O @ ~₹23,000 spot, 65 lot size):**
  * Brokerage: ₹40.00 (₹20 entry + ₹20 exit)
  * STT (Securities Transaction Tax): ~₹330.00 (0.02% on futures sell, 0.10% on option sell premium)
  * Exchange Turnover & SEBI Charges: ~₹85.00
  * Stamp Duty: ~₹30.00 (0.002% on futures buy, 0.003% on option buy)
  * GST (18% on Brokerage & Exchange fees): ~₹25.00
  * Realistic Execution Slippage: ~₹195.00 (1.0 pt futures + 0.5 pt option round-trip)
  * **Total Estimated Round-Trip Friction:** **`₹705.00 to ₹845.00`**
* **Evaluation of ₹1,000 Threshold:** Setting `profit_target_cost_buffer = ₹1,000.00` guarantees that any trade exited via profit target generates a true net cash gain of at least **+₹155 to +₹295**, preventing fee drag from converting nominal winners into losers.
* **Limitations of the ₹1,000 Estimate:**
  1. *Turnover Scaling:* If NIFTY trades at 26,000+, turnover-based taxes (STT & Stamp) increase proportionally.
  2. *Lot Size Adjustments:* Lot size transitions (e.g. 50 $\to$ 25 $\to$ 65 $\to$ 75) scale absolute friction costs.
  3. *High-IV Regimes:* Option entry premiums of ₹300+ incur higher premium turnover fees.
  4. *Auction/Gap Slippage:* Gap openings can incur 2-3 points of slippage.
  *Conclusion:* A configurable parameter `profit_target_cost_buffer` is essential so operators can adjust for prevailing contract specifications.

---

## 3. Phase 2 — Failure-Injection Test Telemetry

The new automated test suite [`test_hardening_failure_injection.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/test_hardening_failure_injection.py) was executed:

```bash
./.venv/bin/python -m unittest backtesting/nifty_covered_call/test_hardening_failure_injection.py -v
```

### Telemetry Output:
```text
test_01_repeated_entry_while_position_active ... 
  🛑 [DUPLICATE ENTRY REJECTED] Active position already exists in strategy state. Entry aborted.
  ok
test_02_short_call_partial_fill_cancellation_failure ... 
  [!] Order ORD_CALL_1 not complete (Status: open, Filled: 30/65)
  [!] Leg 2 Call order ORD_CALL_1 NOT filled or partial. Initiating safe failure handling!
  [!] Exception cancelling call order ORD_CALL_1: Network timeout during cancel
  ⚠️ [PARTIAL CALL DETECTED] Short Call partially filled for 30x NIFTY27NOV2623500CE. Buying back to neutralize naked short exposure...
  ⚠️ [CANCELLATION FAILED] Call order cancellation could not be confirmed. Checking broker...
  ⚠️ [EMERGENCY CLEANUP] Selling 65x NIFTY27NOV26FUT to prevent orphaned position...
  ok
test_03_short_call_buyback_rejection_preserves_state_and_alerts ... 
  [!] Order ORD_CALL_1 not complete (Status: rejected, Filled: 25/65)
  [!] Leg 2 Call order ORD_CALL_1 NOT filled or partial. Initiating safe failure handling!
  ⚠️ [PARTIAL CALL DETECTED] Short Call partially filled for 25x NIFTY27NOV2623500CE. Buying back to neutralize naked short exposure...
  🛑 [CRITICAL EXPOSURE] Buyback of 25x NIFTY27NOV2623500CE failed/partial! (OrderID: )
  🛑 [UNRESOLVED PARTIAL EXPOSURE] Short call buyback was NOT confirmed flat! Preserving state for manual operator intervention.
  ok
test_04a_emergency_futures_close_rejected ... 
  ⚠️ [EMERGENCY CLEANUP] Selling 65x NIFTY27NOV26FUT to prevent orphaned position...
  🛑 [EMERGENCY FAILED] Futures order rejected: {'status': 'error', 'message': 'Exchange down'}
  ok
test_04b_emergency_futures_close_partial_fill ... 
  ⚠️ [EMERGENCY CLEANUP] Selling 65x NIFTY27NOV26FUT to prevent orphaned position...
  [!] Order EMERGENCY_FUT not complete (Status: open, Filled: 30/65)
  🛑 [EMERGENCY FAILED] Futures liquidation order EMERGENCY_FUT NOT filled or partial!
  ok
test_04c_emergency_futures_close_positionbook_reports_residual ... 
  ⚠️ [EMERGENCY CLEANUP] Selling 65x NIFTY27NOV26FUT to prevent orphaned position...
  🛑 [EMERGENCY FAILED] Broker still reports remaining futures exposure: 15x NIFTY27NOV26FUT
  ok
test_05_broker_local_state_mismatch_after_exit ... ok
test_06_profit_target_cost_buffer_dynamics ... 
  ⚠️ [DOWNSIDE/COST TRAP DEFLECTED] Call hit 90% decay (₹8.00) but Combined M2M (₹+780.00) is below profit-target cost buffer (₹1,000.00). Rejecting premature exit to preserve true net profitability after transaction costs.
  ok
test_07_restart_during_ambiguous_order_state ... 
  🛑 [DUPLICATE ENTRY REJECTED] Active position already exists in strategy state. Entry aborted.
  ok

Ran 9 tests in 0.005s — OK (0 failures, 0 errors)
```

---

## 4. Phase 3 — Full Regression Test Audit

All 3 automated test suites across the repository were executed together:

```bash
./.venv/bin/python -m unittest discover -s backtesting/nifty_covered_call -p "test_*.py" -v
```

### Cumulative Results:
* **`test_hardening_failure_injection.py`**: 9 / 9 Passed
* **`test_pre_deployment_validation.py`**: 21 / 21 Passed
* **`test_futures_risk_control.py`**: 6 / 6 Passed
* **Total Automated Tests:** **`36 / 36 PASSED (100% Success, 0 Failures, 0 Errors, 0.012s)`**

---

## 5. Phase 4 — Controlled Sandbox Readiness Assessment

### Current Production State
* AWS Host: `13.203.187.139`
* Strategy State: **STOPPED (`pid: null`, `is_running: false`)**
* Scheduler State: **AUTO-START DISARMED (`is_scheduled: false`, `manually_stopped: true`)**
* Broker Account (`https://vikashiname.in`): **100% FLAT (0 futures, 0 options, 0 open orders)**

### Recommended Staging Architecture:
1. **Target Expiry Contract:**
   * October monthly contract has only 11 days remaining (strictly barred by the 15 DTE minimum filter).
   * Sandbox staging must target the **November Monthly Expiry** (`NIFTY26NOV26FUT` / November ~0.30 Delta Call option).
2. **Execution Mode Boundary:**
   * Configure strictly in **`ANALYZE`** mode (`mode = "ANALYZE"`).
   * OpenAlgo will ingest live Fyers WebSocket quotes, evaluate tick-level M2M, record simulated executions against real bid/ask depth, and persist state atomically without transmitting real orders to the exchange.
3. **Dedicated Sandbox State & Logs:**
   * `state_file`: `/home/ubuntu/fyersawsog/strategies/nifty_covered_call_sandbox_state.json`
   * `log_file`: `/home/ubuntu/fyersawsog/log/strategies/nifty_covered_call_sandbox.log`
4. **Mandatory Staging Prerequisites (Prior to Launch):**
   * Pre-deployment smoke test via `test_pre_deployment_validation.py` on AWS Python environment.
   * Verify OpenAlgo REST API responds with HTTP 200 on `/api/v1/positionbook` and `/api/v1/orderbook`.
   * Confirm auto-start cron remains disabled (`is_scheduled: false`). Launch strictly via manual process invocation.
5. **Rollback Plan:**
   * If any anomaly, unhandled exception, or unexpected order submission occurs:
     1. Issue SIGTERM: `kill -15 <pid>`.
     2. Restore baseline config: `cp /home/ubuntu/fyersawsog/strategies/strategy_configs.json.bak_20261016_1052 /home/ubuntu/fyersawsog/strategies/strategy_configs.json`.
     3. Verify zero broker exposure on `https://vikashiname.in`.
     4. Remove sandbox state file to return to clean baseline.

---

## 6. Classification & Final Recommendation

* **Hardening Implementation:** **PASS**
* **Failure-Injection Validation:** **PASS**
* **Regression Safety:** **PASS**
* **Controlled Sandbox Readiness:** **READY FOR STAGING (AWAITING USER AUTHORIZATION)**

**Next Step:** In strict accordance with user restrictions, all execution has stopped. No deployment, AWS file changes, or process launches will occur without explicit user approval.
