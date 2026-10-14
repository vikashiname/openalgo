# Controlled Forward-Testing Preparation Report

**Audit Date:** 2026-10-14  
**Audit Time:** 11:30:00 IST  
**Reference Benchmark:** `AWS_STRATEGY_CONSOLIDATION_AUDIT_20261014.md`  
**Execution Mode:** STRICT READ-ONLY VERIFICATION (Zero AWS Process Modifications, Zero Live Orders, Zero Production File Changes)  
**Author:** Antigravity Quantitative Research Team

---

## 1. Read-Only Verification of Proposed Strategy Configurations

### 1.1 Nifty Covered Call (`nifty_covered_call_20261012110856.py`)
- **Verified Status**: Active in `ANALYZE` (Paper Sandbox) mode.
- **Open Positions**:
  - Long 65 units `NIFTY27OCT26FUT` @ ₹22,740.20
  - Short -65 units `NIFTY27OCT2623100CE` @ ₹86.80
  - M2M: Tracking dynamically every 30 seconds (~+₹390 to +₹2,346 unrealized).
  - Realized Strategy P&L: **+₹6,773.00** from earlier closed cycle.
- **Order Execution Safety**: Orders are currently submitted through `self.client.placeorder(strategy="NIFTY_COVERED_CALL", disable_telegram=True, notify=False)`. OpenAlgo server is confirmed in `analyze` mode, routing orders to SQLite sandbox DB (`openalgo.db`), not to broker.

### 1.2 Emacrossopen (`emacrossopen_20260903110443.py`) — Position Limit Verification
- **Verified Status**: Active in `ANALYZE` mode, scanning 210 NFO stock futures on 1H candle intervals.
- **Maximum 3 Active Positions Limit Verification**:
  - **Code Inspection Line 159**: `MAX_ACTIVE_POSITIONS = int(os.getenv("MAX_ACTIVE_POSITIONS", "0"))`
  - **Code Inspection Line 4731**: CLI parameter `--max-active` overrides default.
  - **Risk Gate Enforcement (Lines 2775–2782 & 2823–2830)**:
    ```python
    if self.max_active <= 0 or active_positions_count < self.max_active:
        action = "BUY" # or "SELL"
        exec_qty = base_order_qty
    else:
        logger.info(f"⏸️ [RISK GATE] Max active positions ({self.max_active}) reached. Skipping NEW LONG/SHORT for {symbol}.")
        return False, active_positions_count
    ```
  - **Verdict**: **SUPPORTED & STRICTLY ENFORCED**. Setting `MAX_ACTIVE_POSITIONS=3` (or passing `--max-active 3`) guarantees the engine queries open positions from OpenAlgo/broker and hard-blocks any 4th concurrent position with an audit log.
  - **Safety Gate**: The strategy also features `verify_paper_mode()` (lines 1552–1605), which hard-blocks execution if OpenAlgo is ever set to LIVE mode.

### 1.3 Macdfno (`macdfno_20260902130041.py`) — Safe Pause Plan (NOT Paused Yet)
- **Verified Status**: Currently active in `ANALYZE` mode (PIDs 96815 and 92358). Tracked positions: `{}` (Flat).
- **Pause Preparedness**: Retained in active running state. Safe pause procedure fully documented in Section 4.

### 1.4 Oifno (`oifno_20261013171056.py`) — Phase 7 Shadow Mode Governance
- **Verified Status**: Running in `SHADOW` mode under strict governance assertions (`LIVE_TRADING_ENABLED = False`, `PHASE7_MODE = "SHADOW"`).
- **Audit Result**: Zero live broker orders found (`real_broker_orders_found: 0`). Actively recording daily OI shifts and shadow opening executions with limit collars.

---

## 2. Nifty Covered Call Futures-Level Risk-Control Investigation

### 2.1 The Critical Vulnerability in Production
In `/home/ubuntu/fyersawsog/strategies/scripts/nifty_covered_call_20261012110856.py` (lines 618–632), the exit logic monitors:
1. `curr_call_price <= pos["target_price"]` (90% decay on Call premium)
2. `curr_call_price >= pos["stoploss_price"]` (3.0x Call premium stop-loss)
3. `dte_left <= 10` (Roll threshold)

**Finding**: There is **no stop-loss on the Futures leg** and **no cap on net mark-to-market drawdown**.  
If NIFTY crashes 1,000 points, the Call premium rapidly decays to zero. Once it reaches 90% decay (e.g. ₹8.69), the engine triggers **Exit Condition 1 ("Profit Target Hit")**, liquidating the futures at a **-₹65,000 loss** while capturing only +₹5,086 on the option.

### 2.2 Research Implementation Proposal & Test Suite
To address this deficiency without touching production files, two research deliverables were developed and stored in `~/backtesting/nifty_covered_call/`:

1. **Implementation Proposal**: [`PROPOSAL_FUTURES_RISK_CONTROL.md`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/PROPOSAL_FUTURES_RISK_CONTROL.md)  
   *(Mirrored on AWS at `/home/ubuntu/backtesting/nifty_covered_call/PROPOSAL_FUTURES_RISK_CONTROL.md`)*
   - Introduces `fut_stoploss_pct = 0.02` (2.0% catastrophe futures stop-loss, ~455 NIFTY points).
   - Introduces `max_drawdown_inr = 20000.0` (Absolute ₹20,000 net strategy loss cap per lot).
   - Disentangles the "Profit Target" label: If the net position is in drawdown when the Call decays, the exit is flagged as `BEARISH_DECAY_CLOSE` rather than a profitable trade.
2. **Unit Test Suite**: [`test_futures_risk_control.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/test_futures_risk_control.py)  
   *(Mirrored on AWS at `/home/ubuntu/backtesting/nifty_covered_call/test_futures_risk_control.py`)*
   - Validates all 6 core test scenarios:
     - Test 1: Normal bullish decay target hit (`PROFIT_TARGET_HIT`)
     - Test 2: Rapid rally Call stop-loss (`CALL_STOP_LOSS_HIT`)
     - Test 3: Futures catastrophe stop-loss (`FUTURES_STOP_LOSS_HIT`)
     - Test 4: Max net strategy drawdown cap (`MAX_NET_DRAWDOWN_BREACHED`)
     - Test 5: Monthly roll threshold (`ROLL_THRESHOLD_REACHED`)
     - Test 6: Crash decay false profit-target label prevention
   - **Verification Result**: Ran locally and on AWS — **6/6 tests passed (100% pass rate)**.

---

## 3. Verification of September 2026 Overlap Findings

An exact query across original production files (`tradebook_september_2026.csv`, `daily_pnl_september_2026.csv`, and `positions_summary.csv`) established the boundary between verified facts and estimates:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      SEPTEMBER 2026 EMPIRICAL AUDIT RESULTS                           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ [VERIFIED] Total Executed Trades:                 491 trades                           │
│ [VERIFIED] Trades by Macdfno:                     245 trades                           │
│ [VERIFIED] Trades by AUTO_SQUARE_OFF:             119 trades                           │
│ [VERIFIED] Trades by Emacrossopen:                 98 trades                           │
│ [VERIFIED] Trades by Legacy/Diagnostic/UI:         29 trades                           │
│ [VERIFIED] Macdfno Distinct Underlyings Traded:   101 instruments                      │
│ [VERIFIED] Emacrossopen Distinct Underlyings:     62 instruments                       │
│ [VERIFIED] Intersecting Underlyings Over Month:   47 instruments (75.8% of Emacross)   │
│ [VERIFIED] Same-Second / Same-Day Overlap:        0 trades                             │
│ [VERIFIED] Day-Over-Day Contradictory Whiplash:   Frequent (e.g. TATASTEEL, NHPC, etc) │
│ [VERIFIED] Total Net Realized P&L:                +₹2,91,019.51                        │
│ [VERIFIED] Max Single-Day Realized Profit:        +₹5,90,650.00 (2026-09-28)           │
│ [VERIFIED] Max Single-Day Realized Loss:          -₹2,35,491.50 (2026-09-23)           │
│ [VERIFIED] Peak Margin Used:                      ₹63,60,179.03 (2026-09-23)           │
│ [VERIFIED] Average Daily Margin Used:             ₹21,26,911.73                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Critical Finding on Signal Overlap:
- **Prior Assumption / Estimate**: It was previously hypothesized that `Macdfno` and `Emacrossopen` entered competing positions simultaneously within the same second or minute.
- **Empirical Reality Verified**: They did **not** execute trades on the exact same second on the same underlying. Instead, they **whiplashed across successive days**:
  - Example (`TATASTEEL`): On `2026-09-22`, `Macdfno` bought **22,000 shares**. The very next day (`2026-09-23`), `Emacrossopen` sold **13,750 shares**!
  - Example (`NHPC`): On `2026-09-09`, `Emacrossopen` bought **6,950 shares**. The next day (`2026-09-10`), `Macdfno` sold **6,950 shares**!
- **Margin Consequence**: On `2026-09-23`, concurrent stock futures positions across both strategies required **₹63.60 Lakhs in margin**, proving that running both concurrently creates unacceptable margin spikes and contradictory exposure.

---

## 4. Strategy Configuration Schema & Scheduler Behavior

### 4.1 How OpenAlgo's Scheduler Operates
Code inspection of `blueprints/python_strategy.py` reveals OpenAlgo's process architecture:
1. OpenAlgo runs an in-memory manager (`RUNNING_STRATEGIES`, `STOPPING_STRATEGIES`, `STRATEGY_CONFIGS`).
2. An APScheduler instance runs background jobs:
   - `_run_daily_trading_day_check`
   - `_run_market_hours_enforcer`
   - `_run_dead_process_reaper` (calls `cleanup_dead_processes()`)
   - `_run_scheduled_start(strategy_id)`
   - `_run_scheduled_stop(strategy_id)`
3. Configuration state is stored in `strategies/strategy_configs.json`.

### 4.2 Why `pkill` is Dangerous & Strictly Prohibited
- If a strategy process is killed externally via `pkill` or raw `kill -9`:
  1. `app.py`'s in-memory `RUNNING_STRATEGIES` dictionary is **not updated**.
  2. The configuration file still marks `is_running: true` and `manually_stopped: false`.
  3. During the next periodic check, `cleanup_dead_processes()` or `_run_market_hours_enforcer` notices that a scheduled strategy is dead without a manual stop record, and **automatically relaunches it** (as observed at 10:31 IST).
  4. If an external process survived, this creates orphaned dual-running instances.

### 4.3 Verified Scheduler-Aware Safe Pause Procedure
When authorized in the future, the correct procedure to pause `Macdfno` without using `pkill` is:
```python
# Scheduler-Aware Configuration Update
with open("/home/ubuntu/fyersawsog/strategies/strategy_configs.json", "r") as f:
    cfg = json.load(f)

cfg["macdfno_20260902130041"]["is_running"] = False
cfg["macdfno_20260902130041"]["is_scheduled"] = False
cfg["macdfno_20260902130041"]["manually_stopped"] = True
cfg["macdfno_20260902130041"]["pid"] = None

with open("/home/ubuntu/fyersawsog/strategies/strategy_configs.json", "w") as f:
    json.dump(cfg, f, indent=2)
```
Setting `manually_stopped: True` informs `app.py`'s market-hours enforcer and APScheduler to permanently suppress automated restarts until manually re-enabled.

---

## 5. Outstanding Validation Gates & Unresolved Risks

| Strategy | Outstanding Validation Gates | Unresolved Operational Risks |
| :--- | :--- | :--- |
| **Nifty Covered Call** | 1. Implement and verify futures-level stop-loss (`PROPOSAL_FUTURES_RISK_CONTROL.md`).<br>2. Accumulate 180 days forward paper returns.<br>3. Verify behavior under extreme gap downs. | Current code has **no stop loss on futures**. Severe crash causes 90% call decay to exit both legs at market bottom. |
| **Emacrossopen** | 1. Forward-test with enforced `--max-active 3`.<br>2. Validate 180 days out-of-sample positive expectancy.<br>3. Confirm bid-ask slippage on 210 NFO stocks. | Full 210 universe has liquidity variance on lower-tier stocks; must verify top-liquid names. |
| **Macdfno** | 1. High turnover optimization.<br>2. Resolve whiplash overlap with Emacrossopen.<br>3. Add client-side analyze mode lock. | Relies entirely on server mode setting; creates ₹63.6L margin shock when dual-run with Emacrossopen. |
| **Oifno** | 1. Complete 30 trading sessions in Phase 7 Shadow mode.<br>2. Verify opening gap fill collar efficiency. | Phase 7 Shadow governance must not be bypassed. |

---

## 6. Next Steps & Action Plan

1. **Maintain Current Read-Only State**: All 4 processes remain running on AWS in `ANALYZE` / `SHADOW` mode.
2. **Review Deliverables**:
   - Audit & Preparation Report: `backtesting/reports/CONTROLLED_FORWARD_TESTING_PREPARATION_20261014.md`
   - Nifty Risk Proposal: `backtesting/nifty_covered_call/PROPOSAL_FUTURES_RISK_CONTROL.md`
   - Test Suite: `backtesting/nifty_covered_call/test_futures_risk_control.py` (6/6 tests passing)
   - Research Checkpoint: `backtesting/reports/strategy_consolidation_preparation_checkpoint_20261014.json`
3. **Awaiting User Authorization**: Once explicitly approved, execute the scheduler-aware cutover to the consolidated configuration (`Nifty Covered Call` + `Emacrossopen max 3` + `Oifno Shadow`, with `Macdfno` paused).
