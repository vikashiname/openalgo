# NIFTY Covered Call: Pre-Restart Full System Health & Strategy Audit

**Audit Date:** 2026-10-16 10:48 IST  
**Audit Mode:** Strictly Read-Only  
**Strategy Workspace:** `backtesting/nifty_covered_call/`  
**Target AWS Script:** `/home/ubuntu/fyersawsog/strategies/scripts/nifty_covered_call_20261012110856.py`  
**Production Host:** AWS EC2 (`13.203.187.139`) / OpenAlgo (`https://vikashiname.in`)  
**Executive Readiness Verdict:** 🛑 **NOT READY FOR RESTART**

---

## 1. Executive Summary & Readiness Verdict

### Overall System Status: 🛑 **NOT READY FOR RESTART**

While broker positions and AWS host state are **100% synchronized and cleanly flat** (Zero open risk), restarting the production strategy script in its current code state presents **high immediate risk of financial loss and unintended trade entry**:

1. **Immediate Unintended October Entry (11 DTE)**:
   Because `active_position: null` and market hours are active (Spot > 100-EMA), restarting the script will immediately trigger a fresh entry within 30 seconds into the **October monthly contract (`27-OCT-26`)** which has only **11 DTE** remaining.
2. **Forced Roll Trap in 24–48 Hours**:
   The script has a hardcoded roll threshold of `roll_dte = 10`. Entering October at 11 DTE guarantees an immediate forced liquidation and roll within 1 to 2 trading sessions, incurring double slippage and transaction costs.
3. **Downside False Profit Target Trap Active in Production**:
   The script does not verify `net_m2m > 0` before triggering `PROFIT_TARGET_HIT (90% Decay)`. Any sharp market drawdown causes the call option premium to collapse, triggering an exit that locks in massive futures losses at the market bottom.
4. **No Fill Verification (Naked Call Risk)**:
   Order placement does not check API order status or fills. If a futures order fails (e.g. margin or symbol format) while the option order succeeds, the strategy runs an unhedged naked short call.
5. **Scheduler Auto-Start Hazard**:
   The strategy is registered in `strategies/strategy_configs.json` with `is_scheduled: true`. Tomorrow at 09:00 IST, OpenAlgo Strategy Manager will automatically attempt to launch it unless disarmed.

---

## 2. Broker and AWS Synchronization Audit

| Checkpoint | Target | Expected State | Actual Verified State | Status | Evidence Source |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **OpenAlgo Positionbook** | `NIFTY27OCT26FUT` | Qty: 0 | **Qty: 0** (Flat) | **PASS** | `/api/v1/positionbook` (HTTP 200) |
| **OpenAlgo Positionbook** | `NIFTY27OCT2623100CE` | Qty: 0 | **Qty: 0** (Flat) | **PASS** | `/api/v1/positionbook` (HTTP 200) |
| **OpenAlgo OpenPosition** | Both Legs | Qty: 0 | **Qty: 0** | **PASS** | `/api/v1/openposition` (HTTP 200) |
| **OpenAlgo Orderbook** | Pending / Open Orders | 0 Orders | **0 Open / 0 Pending** | **PASS** | `/api/v1/orderbook` (HTTP 200) |
| **Platform Realized P&L** | Session Total | Cleanly booked | **-₹4,930.25** | **PASS** | Complete execution in tradebook |
| **AWS Strategy State** | `active_position` | `null` | **`null`** | **PASS** | `nifty_covered_call_state.json` |
| **AWS Process Health** | Python Process | Stopped | **Stopped** (`pid: null`) | **PASS** | `ps -ef \| grep nifty_covered_call` |
| **State Reconciliation** | Broker vs Strategy State | Flat | **100% In Sync (Zero Mismatch)**| **PASS** | Direct API & File Cross-check |

*Audit Finding: The account is completely flat with zero market exposure.*

---

## 3. Theta-Decay Strategy Logic Audit

| Component | Code Implementation | Verified Behavior & Risk | Status |
| :--- | :--- | :--- | :---: |
| **Call Strike Selection** | Black-Scholes Delta ~0.30 (`calculate_bs_delta`) | Fixed $r=0.07$, $\sigma=0.14$. In high-vol regimes, actual 0.30 delta is further OTM than calculated; in low-vol regimes, closer. | **PASS** *(Acceptable approximation)* |
| **Entry Timing & DTE Selection** | `get_near_futures_contract()` (Line 270) | `target_fut = futs_sorted[0]`. Blindly takes nearest expiry (`27-OCT-26`, 11 DTE). **Lacks minimum DTE filter**. | ❌ **FAIL** *(Critical Defect)* |
| **Roll Threshold** | `dte_left <= self.roll_dte` (Line 629) | Set to 10 days. Rolling triggers immediately when DTE $\le 10$. Incompatible with entering at 11 DTE. | ❌ **FAIL** *(Critical Churn Risk)* |
| **Option Profit Target** | `curr_call_price <= target_price` (Line 619) | Triggers at 90% decay **without checking `net_m2m > 0`**. In market crashes, option collapses and locks in futures losses. | ❌ **FAIL** *(Known Downside Trap)* |
| **Option Stop Loss** | `curr_call_price >= stoploss_price` (Line 624)| Triggers at 3.0x premium multiplier. Closes both legs simultaneously. | **PASS** |
| **Hedge Quantity Matching**| `fut_qty = fut_info['lotsize'] * lots` | Futures (65) and Options (65) match 1:1. | **PASS** |
| **Order Fill Verification** | `execute_entry` (Lines 419-445) | Sends orders via `placeorder` but **does not verify `fut_order['status'] == 'success'`**. Assumes immediate 100% fill. | ❌ **FAIL** *(Naked Leg Risk)* |
| **Exit Leg Atomicity** | `execute_exit` (Lines 503-524) | Sends SELL futures, then BUY call. If one order fails, script logs error and wipes state anyway, leaving an orphaned leg. | ❌ **FAIL** *(Execution Hazard)* |

---

## 4. Risk Controls Audit

| Risk Control | Target Specification | Actual Implementation in Production Code | Status |
| :--- | :--- | :--- | :---: |
| **Futures Catastrophe Stop** | Stop loss on futures adverse drop (-2.0%) | **NON-EXISTENT**. No futures-level stop loss exists in `nifty_covered_call_20261012110856.py`. | ❌ **FAIL** |
| **Combined M2M Loss Cap** | Strategy net drawdown cap (-₹20,000) | **NON-EXISTENT**. No net M2M drawdown stop exists in the production script. | ❌ **FAIL** |
| **Trailing Profit Protection**| Lock in gains after reaching peak profit | **NON-EXISTENT**. Script holds all winners until 90% decay or roll threshold. | ❌ **FAIL** |
| **Order Sizing & Freeze Qty** | Prevent oversized order submission | Hardcoded `lots = 1` ($\times 65$ qty). Below NFO freeze quantity of 1,800. | **PASS** |
| **Duplicate Order Protection**| Check broker positions before order send | **NON-EXISTENT**. Script only checks its internal JSON state; does not query broker positionbook before entry. | ❌ **FAIL** |
| **Network Timeout & Retry** | Resend on connection drop | Single HTTP request with 5s timeout. No exponential backoff or fill reconciliation loop. | ⚠️ **UNVERIFIED / POOR** |

---

## 5. AWS and Execution Infrastructure Audit

| Component | Target Parameter | Actual Verified State | Status | Evidence |
| :--- | :--- | :--- | :---: | :--- |
| **Process Concurrency** | Zero ghost or duplicate processes | Exactly 0 instances running | **PASS** | `ps -ef \| grep nifty_covered_call` |
| **Python Environment** | Compatible virtualenv with packages | `/home/ubuntu/fyersawsog/venv` (Python 3.12+, pandas, scipy, requests) | **PASS** | Verified via SSH python test |
| **OpenAlgo Host Connectivity**| REST API responsiveness | Responsive on `127.0.0.1:5000` & `vikashiname.in` | **PASS** | HTTP 200 on all endpoints |
| **Broker Session (Fyers)** | Valid OAuth authentication | Auth active in `openalgo.db` (`is_revoked: 0`); live quotes streaming | **PASS** | Live streaming quotes verified |
| **Market Data Feed Health** | Fresh quotes for NIFTY F&O | Quotes returning live bids, asks, LTP, OI, Volume | **PASS** | `LTP: 22,985.9` returned from Fyers |
| **Timezone Alignment** | Indian Standard Time (IST) | Explicit `pytz.timezone("Asia/Kolkata")` in all modules | **PASS** | Timestamp verified |
| **Scheduler Status** | Strategy Manager scheduled run | `is_scheduled: true` in `strategy_configs.json` | ⚠️ **FAIL / WARNING** | Auto-start will trigger tomorrow at 09:00 IST |

---

## 6. Theta-Decay & Expiry Operational Readiness

| Readiness Item | Finding / Evaluation | Status |
| :--- | :--- | :---: |
| **Calendar & Expiry Calculation** | `(exp_dt - now.date()).days` properly handles weekends and market holidays. | **PASS** |
| **Immediate Startup Entry Hazard**| Starting the script during market hours with `active_position: null` **fires a trade immediately** without operator confirmation. | ❌ **FAIL** |
| **Executable Price vs. LTP** | Script evaluates exits on `ltp`. In illiquid OTM options with wide bid-ask spreads, LTP can trigger false targets or fail to fill. | ⚠️ **UNVERIFIED** |
| **Slippage & Cost Awareness** | Script does not account for slippage or transaction costs when determining net M2M. | ⚠️ **UNVERIFIED** |

---

## 7. Exact Files Inspected

1. [`strategies/scripts/nifty_covered_call_20261012110856.py`](file:///Users/mac/Desktop/openalgo/strategies/scripts/nifty_covered_call_20261012110856.py) *(Production script on AWS)*
2. [`/home/ubuntu/fyersawsog/strategies/scripts/nifty_covered_call_state.json`](file:///home/ubuntu/fyersawsog/strategies/scripts/nifty_covered_call_state.json) *(AWS live state file)*
3. [`/home/ubuntu/fyersawsog/strategies/strategy_configs.json`](file:///home/ubuntu/fyersawsog/strategies/strategy_configs.json) *(AWS strategy manager config)*
4. [`/home/ubuntu/fyersawsog/db/openalgo.db`](file:///home/ubuntu/fyersawsog/db/openalgo.db) *(AWS OpenAlgo database)*
5. [`backtesting/nifty_covered_call/CURRENT_WORK.md`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/CURRENT_WORK.md) *(Sync checkpoint)*
6. [`backtesting/nifty_covered_call/RESEARCH_AUDIT_REPORT.md`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/RESEARCH_AUDIT_REPORT.md) *(Research findings)*

---

## 8. Minimum Remediation Actions (Priority Order)

Before this strategy can safely run in live or paper production, the following code updates must be applied:

1. **[CRITICAL] Enforce Minimum DTE Entry Filter ($\ge 15$ Days)**:
   In `get_near_futures_contract()`, filter candidate expiries to require `dte >= 15` days. This ensures that any fresh entry targets the **November monthly cycle (`23-NOV-26`, 38 DTE)** rather than the expiring October contract (11 DTE).
2. **[CRITICAL] Guard Profit Target against Downside Crashes**:
   In `evaluate_cycle()`, update the profit target condition to require positive strategy M2M:
   ```python
   if curr_call_price <= pos["target_price"] and net_m2m > 0:
       self.execute_exit("PROFIT_TARGET_HIT (90% Decay)", spot, curr_call_price)
   ```
3. **[CRITICAL] Add Fill Verification & Orphan Prevention**:
   In `execute_entry()`, check `if fut_order.get("status") != "success" or call_order.get("status") != "success":` and abort rather than recording an incomplete position in state.
4. **[HIGH] Implement Futures Catastrophe Stop-Loss (-2.0%)**:
   Add a direct stop trigger if futures drop $\ge 2.0\%$ from entry price to prevent unhedged runaway futures drawdowns.
5. **[MEDIUM] Disarm Scheduler Auto-Start**:
   Set `is_scheduled: false` in `strategies/strategy_configs.json` until code updates are validated and user gives explicit restart approval.

---

## 9. Actions Requiring Explicit User Approval

The following actions **require your explicit sign-off** before proceeding:
1. Updating production strategy code on AWS (`nifty_covered_call_20261012110856.py`) with the remediation fixes.
2. Disabling the auto-start scheduler in `strategy_configs.json` on AWS.
3. Launching or restarting the strategy process on AWS.
4. Placing any live or paper trades for the November cycle (`NIFTY23NOV26FUT` + `NIFTY23NOV2623400CE`).
