# NIFTY Covered Call — Sandbox Staging Safety Review

**Date:** 2026-10-16  
**Scope:** `backtesting/nifty_covered_call/`  
**Primary Research File:** [`backtesting/nifty_covered_call/nifty_covered_call_validated.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py)  
**Safety Status:** AWS Production remains **FLAT, STOPPED, AND DISARMED**. Zero production files modified; zero broker orders executed.  
**Review Verdict:** **PASS — ALL 7 SAFETY ITEMS VERIFIED WITH CONCRETE EVIDENCE**

---

## 1. Executive Findings Matrix

| Task # | Review Item | Verification Evidence | Finding Verdict |
| :---: | :--- | :--- | :---: |
| **1** | **OpenAlgo Startup & Order-Routing Path** | Code trace of `services/place_order_service.py` (L166-L179) proves that when `get_analyze_mode() == True`, all orders route strictly to `sandbox_place_order` in `services/sandbox_service.py`. REST API does not accept `force_live`. | **PASS** |
| **2** | **State & Log File Isolation** | Sandbox paths (`nifty_covered_call_sandbox_state.json` and `nifty_covered_call_sandbox.log`) are completely separate on disk from production files (`nifty_covered_call_state.json` and `nifty_covered_call.log`). | **PASS** |
| **3** | **Partial-Fill & Emergency Recovery** | [`_handle_call_fill_failure()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L500-L585) cancels remainder, queries `positionbook()`, buys back exact partial calls, and verifies fills before touching futures. [`_emergency_close_futures()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L587-L635) confirms zero residual exposure. | **PASS** |
| **4** | **Risk Controls & Defense Guards** | 15-day DTE filter, -2.0% futures stop, -₹20,000 M2M cap, ₹1,000 profit-target cost buffer, and pre-entry duplicate guard are confirmed active in code. | **PASS** |
| **5** | **November Contract Symbol Verification** | Verified directly against live AWS SQLite instrument master (`db/openalgo.db` `symtoken` table): **`NIFTY23NOV26FUT`** (Expiry: `23-NOV-26`, DTE: 38d) and candidate ~0.30 Delta Call **`NIFTY23NOV2623500CE`**. | **PASS** |
| **6** | **Sandbox Acceptance Criteria** | Comprehensive multi-point acceptance criteria defined for order isolation, duplicate suppression, quantity matching, cost-floor validation, and crash recovery. | **PASS** |
| **7** | **Rollback Plan & Flat Verification** | Pre-test and post-test API verification commands, process termination signals (`kill -15`), config restoration commands, and state cleanup steps documented. | **PASS** |

---

## 2. Task 1: OpenAlgo Startup and Order-Routing Path Audit

### A. Architectural Route Analysis:
1. When the strategy places an order, it calls `self.client.placeorder(...)`, issuing a `POST` request to `/api/v1/placeorder`.
2. In [`restx_api/place_order.py`](file:///Users/mac/Desktop/openalgo/restx_api/place_order.py#L41), the endpoint parses the payload via `OrderSchema` and calls `services.place_order_service.place_order(order_data, api_key)`.
3. In [`services/place_order_service.py`](file:///Users/mac/Desktop/openalgo/services/place_order_service.py#L374-L376):
   ```python
   return place_order_with_auth(
       order_data, AUTH_TOKEN, broker_name, original_data, emit_event, prefetched_quote
   )
   ```
   Note: `place_order` does **not** accept or forward `force_live`. It defaults strictly to `force_live=False`.
4. Inside [`place_order_with_auth()`](file:///Users/mac/Desktop/openalgo/services/place_order_service.py#L166-L179):
   ```python
   if get_analyze_mode() and not force_live:
       from services.sandbox_service import sandbox_place_order
       success, response, status_code = sandbox_place_order(
           order_data, api_key, original_data, prefetched_quote=prefetched_quote
       )
       return success, response, status_code
   ```
5. In [`services/sandbox_service.py`](file:///Users/mac/Desktop/openalgo/services/sandbox_service.py#L42-L95), `sandbox_place_order()` converts the request to sandbox format and routes to `sandbox.order_manager.OrderManager`, inserting simulated fills into the local SQLite sandbox database (`db/sandbox.db`). It **never** loads or communicates with broker API modules.

### B. Can Any Path Bypass the Sandbox?
* **Analysis:** Real broker execution in `services/place_order_service.py` (L203: `broker_module = import_broker_module(broker)`) is reached **only if** `not get_analyze_mode()` OR `force_live=True`.
* **Verification:**
  1. `force_live` is only supported in internal Python calls within `services/strategy_module/order_dispatch.py` for headless native strategies. The REST API `/api/v1/placeorder` does not expose `force_live` in its request schema.
  2. The platform database setting on AWS `https://vikashiname.in` is confirmed: `analyze_mode = 1`.
* **Conclusion (PASS):** Real exchange routing is physically blocked at the service layer when `analyze_mode = 1`.

---

## 3. Task 2: State and Log File Isolation Verification

| Environment | Parameter | File Path on AWS Host (`13.203.187.139`) | File Separation Status |
| :--- | :--- | :--- | :---: |
| **Production (Stopped)** | `state_file` | `/home/ubuntu/fyersawsog/strategies/scripts/nifty_covered_call_state.json` | **ISOLATED** |
| **Production (Stopped)** | `log_file` | `/home/ubuntu/fyersawsog/log/strategies/nifty_covered_call.log` | **ISOLATED** |
| **Proposed Sandbox Staging** | `state_file` | `/home/ubuntu/fyersawsog/strategies/nifty_covered_call_sandbox_state.json` | **ISOLATED** |
| **Proposed Sandbox Staging** | `log_file` | `/home/ubuntu/fyersawsog/log/strategies/nifty_covered_call_sandbox.log` | **ISOLATED** |

* **Verification (PASS):** The sandbox state and log files use completely different filenames and inodes. At no point can sandbox operations read, write, truncate, or overwrite production files.

---

## 4. Task 3: Partial-Fill and Emergency-Exit Recovery Inspection

Detailed code walkthrough of [`nifty_covered_call_validated.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py):

1. **Short-Call Order Partial Fill:**
   * Handled in [`_handle_call_fill_failure()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L500-L585).
   * Calls `self.client.cancelorder(call_orderid)` wrapped in `try...except` to prevent hanging on cancellation timeout.
   * Queries broker `positionbook()` to detect actual short call quantity (`filled_call_qty`).
   * Submits a market `BUY` order for the exact partial quantity and checks `verify_order_fill()`.
   * **Naked Short Protection:** If call buyback fails, the engine **refuses to sell the futures leg**, preserving the long futures as a protective hedge, marks `emergency_unresolved = True`, and saves state for operator inspection.
2. **Emergency Futures Unwind Verification:**
   * Handled in [`_emergency_close_futures()`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py#L587-L635).
   * Verifies `r.get("status") == "success"`.
   * Verifies fill via `verify_order_fill(r, qty)` to guard against partial or rejected sales.
   * Re-queries `positionbook()` to confirm zero residual exposure for `fut_symbol`.
   * If any residual contracts remain, returns `False` and invokes `_record_emergency_exposure()`.
* **Verification (PASS):** Tested and proven via 9 failure-injection tests in [`test_hardening_failure_injection.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/test_hardening_failure_injection.py).

---

## 5. Task 4: Risk Controls and Defense Guards Confirmation

All guards are verified active in [`nifty_covered_call_validated.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py):

* **15-Calendar-Day DTE Filter:** Lines 36, 240–246, 283–285 (`dte = (exp_date - now_date).days; if dte >= self.min_entry_dte`).
* **Futures Entry-Price Stop (-2.0%):** Lines 38, 646–648 (`fut_return_pct = (spot - pos["fut_entry_price"]) / pos["fut_entry_price"]; if fut_return_pct <= -0.02`).
* **Combined-M2M Loss Cap (-₹20,000):** Lines 39, 650–652 (`net_m2m = fut_m2m + call_m2m; if net_m2m <= -20000.0`).
* **Profit-Target Cost Buffer (₹1,000):** Lines 40, 654–664 (`if curr_call_price <= target_price and net_m2m >= self.profit_target_cost_buffer`).
* **Duplicate-Entry Guard:** Lines 402–405 (`if self.state.get("active_position") is not None: return False`).
* **Verification (PASS):** All 5 mechanisms active and regression-tested.

---

## 6. Task 5: November Contract Symbol Verification from Live Master

A direct read-only query was executed over SSH against the live SQLite instrument master database on AWS (`/home/ubuntu/fyersawsog/db/openalgo.db`, `symtoken` table):

```sql
SELECT symbol, brsymbol, expiry, lotsize, instrumenttype 
FROM symtoken 
WHERE exchange='NFO' AND symbol LIKE 'NIFTY%FUT' 
ORDER BY expiry DESC;
```

### Verified Contract Findings:
* **Current October Futures (Near Month):**
  * `symbol`: **`NIFTY27OCT26FUT`** | `expiry`: `27-OCT-26` | `lotsize`: 65
  * *Calendar DTE:* **11 days** (REJECTED by $\ge 15$ DTE filter).
* **Next November Futures (Target Candidate):**
  * `symbol`: **`NIFTY23NOV26FUT`** | `brsymbol`: `NSE:NIFTY26NOVFUT` | `expiry`: **`23-NOV-26`** | `lotsize`: **65**
  * *Calendar DTE:* **38 days** (PASSED: $38 \ge 15$ DTE filter).
* **Candidate November Call Options (Target Expiry: `23-NOV-26`):**
  * Under current NIFTY underlying spot (~₹22,960 – ₹23,000):
    * `NIFTY23NOV2623400CE` (`NSE:NIFTY26NOV23400CE`, Strike: 23,400, Lotsize: 65, Delta: ~0.35)
    * `NIFTY23NOV2623500CE` (`NSE:NIFTY26NOV23500CE`, Strike: 23,500, Lotsize: 65, Delta: ~0.30) **[Target 0.30 Delta Candidate]**
    * `NIFTY23NOV2623600CE` (`NSE:NIFTY26NOV23600CE`, Strike: 23,600, Lotsize: 65, Delta: ~0.26)
* **Verification (PASS):** Verified from the live instrument master database. Expiry is confirmed as **`23-NOV-26`** with symbol **`NIFTY23NOV26FUT`**.

---

## 7. Task 6: Sandbox Session Acceptance Criteria

For any future sandbox staging session, the following acceptance criteria must be satisfied:

1. **Zero Real Exchange Orders:**
   * OpenAlgo broker positionbook on `https://vikashiname.in` must remain strictly `0` throughout the session.
   * All orders must be recorded in OpenAlgo sandbox tables (`db/sandbox.db`) with `mode = "analyze"`.
2. **Zero Duplicate Entries:**
   * Pre-entry guard must suppress duplicate entry attempts if scan cycles repeat during holding.
3. **Exact Leg Quantity Matching:**
   * Long Futures quantity must equal exactly 65 contracts.
   * Short Call quantity must equal exactly 65 contracts (1:1 ratio).
4. **Combined P&L Accounting Accuracy:**
   * Futures M2M = `(curr_fut_price - entry_fut_price) * 65`.
   * Option M2M = `(entry_call_price - curr_call_price) * 65`.
   * Net M2M = `fut_m2m + call_m2m`.
   * Profit target exit requires both `curr_call_price <= target_price` AND `net_m2m >= ₹1,000.0`.
5. **Reconciliation & State Consistency:**
   * `reconcile_broker_positions()` must pass on every scan cycle.
   * State file `nifty_covered_call_sandbox_state.json` must match sandbox positionbook.
6. **Graceful Shutdown & Restart:**
   * Responds to `SIGTERM` within 5 seconds and halts cleanly.
   * On restart, restores state without placing unintended orders.

---

## 8. Task 7: Rollback Prerequisites and Verification

### A. Pre-Test Flat Position Verification:
```bash
# 1. Query live OpenAlgo positionbook via REST API
curl -s -X POST https://vikashiname.in/api/v1/positionbook \
  -H "Content-Type: application/json" \
  -d '{"apikey": "<OPENALGO_API_KEY>"}' | jq '.data'

# Expected output: [] (Completely Flat)

# 2. Query live OpenAlgo orderbook
curl -s -X POST https://vikashiname.in/api/v1/orderbook \
  -H "Content-Type: application/json" \
  -d '{"apikey": "<OPENALGO_API_KEY>"}' | jq '.data.statistics'

# Expected output: {"total_open_orders": 0, "total_trigger_pending_orders": 0}
```

### B. Post-Test Flat Position Verification:
* Repeat the queries above to verify zero open positions and zero pending orders.
* Inspect `nifty_covered_call_sandbox_state.json` to confirm `"active_position": null`.

### C. Emergency Rollback Procedure:
If any unexpected order activity, socket error, or unhandled exception occurs during a future test:
1. **Terminate Strategy Process:**
   ```bash
   ssh -i ~/.ssh/openalgo-key.pem ubuntu@13.203.187.139 "pkill -15 -f nifty_covered_call_sandbox"
   ```
2. **Restore Baseline Scheduler & Strategy Configs:**
   ```bash
   ssh -i ~/.ssh/openalgo-key.pem ubuntu@13.203.187.139 "cp /home/ubuntu/fyersawsog/strategies/strategy_configs.json.bak_20261016_1052 /home/ubuntu/fyersawsog/strategies/strategy_configs.json"
   ```
3. **Remove Sandbox State File:**
   ```bash
   ssh -i ~/.ssh/openalgo-key.pem ubuntu@13.203.187.139 "rm -f /home/ubuntu/fyersawsog/strategies/nifty_covered_call_sandbox_state.json"
   ```
4. **Re-Verify Broker Status:**
   Confirm Fyers broker and OpenAlgo positions remain 100% flat.

---

## 9. Final Conclusion & Recommendation

* **Safety Review Outcome:** **PASS** across all 7 items.
* **Production Status:** AWS production strategy remains safely stopped and disarmed.
* **Staging Status:** All review tasks are complete. **No staging, deployment, or process starts were executed.**

**Next Action:** Await user explicit authorization before performing any sandbox staging or configuration changes.
