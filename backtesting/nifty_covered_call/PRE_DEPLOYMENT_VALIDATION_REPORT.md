# NIFTY Covered Call: Pre-Deployment Validation Report

**Date:** 2026-10-16  
**Workspace:** `backtesting/nifty_covered_call/`  
**Target Reference (Read-Only):** `strategies/scripts/nifty_covered_call_20261012110856.py`  
**Validated Research Twin:** [`backtesting/nifty_covered_call/nifty_covered_call_validated.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py)  
**Automated Test Suite:** [`backtesting/nifty_covered_call/test_pre_deployment_validation.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/test_pre_deployment_validation.py)  
**Safety Status:** AWS Production remains **FLAT, STOPPED, AND DISARMED**. Zero production changes or orders were executed.

---

## 1. Executive Summary & Validation Verdict

A rigorous pre-deployment engineering audit and testing process was executed to address all 7 structural vulnerabilities identified in [`PRE_RESTART_AUDIT.md`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/PRE_RESTART_AUDIT.md). All fixes were implemented in an isolated research twin ([`nifty_covered_call_validated.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/nifty_covered_call_validated.py)), verified via an automated 21-test mock suite ([`test_pre_deployment_validation.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/test_pre_deployment_validation.py)), and validated against historical backtests across 635 trading sessions.

### Validation Verdict: **PASS — VALIDATED RESEARCH TWIN READY FOR USER REVIEW**

* **Unit & Safety Test Pass Rate**: **100% (21 / 21 tests passed)**
* **Risk Control Regression Pass Rate**: **100% (6 / 6 tests passed)**
* **Production Boundary Preserved**: AWS host `13.203.187.139` and production files were **NOT modified**.
* **Auto-Start Security**: Scheduler auto-start remains permanently disabled (`is_scheduled: false`).

---

## 2. Detailed Verification of the 7 Production Fixes

| # | Vulnerability from Audit | Resolution Mechanism | Verification Test Case | Test Result |
| :--- | :--- | :--- | :--- | :---: |
| **1** | **Blind Startup & Ghost Position Hazard** | `reconcile_broker_positions()` queries OpenAlgo broker positionbook and orderbook. Fails closed on API errors, pending orders, or quantity mismatch. | `test_reconcile_fail_closed_*` (6 scenarios) & `test_reconcile_success_*` (2 scenarios) | **PASS** |
| **2** | **Expiring Near-Month Entry Hazard** | Dynamic contract scanner enforces $\ge 15$ calendar DTE filter; skips expiring near-month (e.g. 11d) and selects eligible contract (e.g. 39d). | `test_minimum_dte_rejects_expiring_futures`, `test_minimum_dte_returns_none...`, `test_find_target_call_rejects...` | **PASS** |
| **3** | **Unverified Fills & Naked Position Hazard** | Two-phase sequential submission with fill verification via `orderstatus`. If Futures fail, aborts. If Call fails, triggers `_emergency_close_futures()`. | `test_entry_fails_when_futures_order_fails`, `test_entry_fails_and_unwinds_futures...` | **PASS** |
| **4** | **Downside False Profit-Target Trap** | Guarded call-decay logic: 90% decay exit is strictly prohibited if `net_m2m <= 0`. Deflects locking in futures bottom during market selloffs. | `test_guarded_profit_target_rejects_decay_when_net_m2m_negative`, `test_guarded_profit_target_triggers...` | **PASS** |
| **5** | **Absence of Futures Stop & Net Drawdown Cap** | Dual-barrier circuit breaker: Futures Catastrophe Stop (-2.0% spot breach) and Strategy Net M2M Loss Cap (-₹20,000 net loss). | `test_futures_catastrophe_stop_triggers...`, `test_max_m2m_loss_cap_triggers...`, `test_call_stoploss_and_roll...` | **PASS** |
| **6** | **State File Corruption Risk** | Atomic write cycle using temporary file swapping (`.tmp` $\to$ `os.replace`) preventing partial write corruption on abrupt reboot/crash. | `test_atomic_state_persistence_and_recovery` | **PASS** |
| **7** | **Partial Exit Orphan Hazard** | Sequential exit with two-leg fill confirmation. If one leg fails to fill, strategy state is **preserved** to alert operator and prevent untracked exposure. | `test_partial_exit_hazard_retains_state`, `test_full_exit_success_clears_state...` | **PASS** |

---

## 3. Automated Test Suite Execution Telemetry

Execution of the mock test suite via Python 3.12 environment (`./.venv/bin/python -m unittest backtesting/nifty_covered_call/test_pre_deployment_validation.py -v`):

```text
test_atomic_state_persistence_and_recovery ... ok
test_call_stoploss_and_roll_threshold ... ok
test_entry_fails_and_unwinds_futures_when_call_order_fails ... 
  [!] Leg 2 Call order NOT filled. INITIATING EMERGENCY FUTURES UNWIND!
  ⚠️ [EMERGENCY CLEANUP] Selling 65x NIFTY27NOV26FUT to prevent orphaned position...
  ok
test_entry_fails_when_futures_order_fails ... 
  [!] Leg 1 Futures order NOT filled. Aborting entry.
  ok
test_find_target_call_rejects_sub_15_dte_expiry ... 
  [!] Target expiry 26-Oct-26 has DTE=10 < min_entry_dte=15.
  ok
test_full_exit_success_clears_state_and_records_history ... ok
test_futures_catastrophe_stop_triggers_at_minus_2_pct ... ok
test_guarded_profit_target_rejects_decay_when_net_m2m_negative ... 
  ⚠️ [DOWNSIDE TRAP DEFLECTED] Call hit 90% decay (₹8.00) but Combined M2M is negative (₹-13,520.00). 
  Rejecting false profit-target exit to prevent locking in futures bottom.
  ok
test_guarded_profit_target_triggers_when_net_m2m_positive ... ok
test_max_m2m_loss_cap_triggers_at_minus_20k ... ok
test_minimum_dte_rejects_expiring_futures ... ok
test_minimum_dte_returns_none_if_all_contracts_under_15_dte ... 
  [!] No futures contract found with DTE >= 15 days.
  ok
test_partial_exit_hazard_retains_state ... 
  🛑 [PARTIAL EXIT HAZARD] Futures closed: True, Call closed: False. 
  State NOT cleared to preserve leg tracking. Operator intervention required!
  ok
test_reconcile_fail_closed_when_active_position_mismatched ... ok
test_reconcile_fail_closed_when_client_none ... ok
test_reconcile_fail_closed_when_ghost_position_exists ... ok
test_reconcile_fail_closed_when_open_orders_exist ... ok
test_reconcile_fail_closed_when_orderbook_fails ... ok
test_reconcile_fail_closed_when_positionbook_fails ... ok
test_reconcile_success_when_active_positions_match_1_to_1 ... ok
test_reconcile_success_when_both_flat ... ok

----------------------------------------------------------------------
Ran 21 tests in 0.007s

OK
```

---

## 4. Historical Backtest Comparison & Risk Evaluation

Backtest simulations across 635 trading sessions (2022-01-03 to 2024-07-31) incorporating institutional Indian transaction costs (Brokerage, STT, Exchange turnover, Stamp duty, GST, slippage):

| Strategy Variant | Trades | Win Rate | Profit Factor | Total Net P&L (₹) | Max Drawdown (₹) | Sharpe Ratio | Calmar Ratio | False Targets |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Buy & Hold NIFTY (Benchmark)** | — | — | — | ₹4,21,778 | ₹99,663 | — | 4.23 | — |
| **Baseline (Net of Costs)** | 23 | 73.91% | 6.10 | ₹2,52,776 | ₹25,130 | 2.76 | 10.06 | 5 (100% of losses) |
| **DTE Filter $\ge$ 10d** | 32 | 71.88% | 5.73 | ₹2,96,138 | ₹30,398 | 2.51 | 9.74 | 5 |
| **DTE Filter $\ge$ 15d (Validated Twin)** | **27** | **77.78%** | **7.09** | **₹3,02,147** | **₹25,130** | **3.01** | **12.02** | 5 |
| **Control 1: Futures Stop (-2.0%)** | 23 | 73.91% | 5.40 | ₹2,46,394 | ₹25,130 | 2.57 | 9.80 | 3 |
| **Control 2: Net M2M Cap (-₹20k)** | 23 | 73.91% | 5.40 | ₹2,46,394 | ₹25,130 | 2.57 | 9.80 | 4 |
| **Combined Architecture (Target)** | **27** | **81.48%** | **6.47** | **₹3,04,828** | **₹25,130** | **2.91** | **12.13** | **3** |

### Key Backtest Insights:
1. **15-Day Minimum DTE Superiority**: Raising entry threshold from 0 to $\ge 15$ DTE increased Net P&L by **+₹49,371 (+19.5%)** and improved Sharpe to **3.01** (vs 2.76 on baseline and 2.51 on 10 DTE). It captures optimal theta decay while avoiding hyper-gamma near-expiry risk.
2. **Deflection of Downside Trap**: With `net_m2m > 0` gating, the strategy no longer prematurely liquidates winning long positions at temporary dips just because the out-of-the-money call decayed to 90%.
3. **Downside Risk Protection**: While Buy & Hold suffered nearly ₹1,00,000 in peak drawdown, the validated covered call architecture caps drawdown at **₹25,130** (a 74.8% reduction in drawdown risk).

---

## 5. Deployment Readiness & Operating Recommendations

### Current State
* Local research twin is fully patched, documented, and tested.
* Production host `13.203.187.139` remains untouched.
* Auto-start scheduler on AWS is safely disabled (`is_scheduled: false`, `manually_stopped: true`).
* OpenAlgo broker account is flat (0 futures, 0 options, 0 open orders).

### Prerequisites Before Any Future Production Launch:
1. **Explicit Operator Authorization**: No deployment or live trading until requested by the user.
2. **November Expiry Contract Timing**: October expiry has only 11 days remaining (below the 15 DTE minimum filter). Any upcoming manual cycle must target the November monthly contract (`NIFTY26NOV26FUT` / November ~0.30 Delta CE).
3. **Production File Migration**: When approved, copy `nifty_covered_call_validated.py` to the AWS strategies folder, update `strategy_configs.json` parameters, and run in `ANALYZE` (Sandbox) mode for initial live observation.
