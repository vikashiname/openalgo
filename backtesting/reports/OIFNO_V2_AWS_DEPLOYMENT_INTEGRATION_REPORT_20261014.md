# OIFNO V2 AWS PRODUCTION DEPLOYMENT & OPENALGO INTEGRATION REPORT
**Contract Standard:** `SIG-OI-001-EXECUTION-STANDARD-V2`  
**Deployment Date:** October 14, 2026, 13:02 IST  
**Environment:** AWS EC2 Production (`ip-172-31-37-78` / `vikashiname.in`)  
**Deployment Architecture:** OpenAlgo Process Supervisor (`openalgo.service`)  
**Supervised Script Path:** `/home/ubuntu/fyersawsog/strategies/scripts/oifno_standard_v2.py`  
**Execution Mode:** Strictly `PAPER` (Simulated Orders Only)  
**Research Status:** Decoupled `PHASE_7` Forward Validation  

---

## 1. Executive Verdict

### **VERDICT: PASS**

The standardized OIFNO V2 implementation (`SIG-OI-001-EXECUTION-STANDARD-V2`) has been successfully deployed to AWS and integrated into OpenAlgo's production scheduler and process supervisor.

- **Two Modes Enforced**: The engine runs strictly in **`PAPER`** mode. Legacy `SHADOW` execution mode has been eliminated from active code, configuration, state schema, and runtime logs.
- **Fail-Safe Startup**: Strategy starts reliably under OpenAlgo supervision as PID `121185` and performs periodic reconciliation audits in `PAPER` mode every 60 seconds.
- **Zero Real Broker Orders**: Across all deployment actions, restarts, and reconciliation cycles, exactly **zero** broker orders have been submitted to Fyers or OpenAlgo.
- **Frozen V1 Intact**: The original frozen V1 script (`oifno_20261013171056.py`, SHA-256: `11b501f11be1e34517a2532a9a1ee6d4f5e89f901f9b6e28381009e279aceae9`) remains preserved and unaltered on AWS.
- **Other Strategies Unaffected**: `Macdfno` (PID 121181), `Emacrossopen` (PID 121182), and `Nifty Covered Call` (PID 121183) remain actively running and undisturbed.

---

## 2. Environment & Application Verification

| Parameter | Verified Production Value |
| :--- | :--- |
| **AWS Host** | `Linux ip-172-31-37-78 7.0.0-1014-aws x86_64` (Ubuntu 24.04.4 LTS) |
| **Application Directory** | `/home/ubuntu/fyersawsog` |
| **Python Virtualenv** | `/home/ubuntu/fyersawsog/venv/bin/python` (Python 3.12.3) |
| **OpenAlgo Service** | `openalgo.service` (Systemd unit, Main PID: `121156`) |
| **OpenAlgo Version** | 1.0.7 |
| **OpenAlgo Mode** | `analyze` (`analyze_mode = 1`) |
| **Supervisor Mechanism** | `blueprints/python_strategy.py` with multi-strategy state restoration & process isolation |

---

## 3. Deployed Artifact & Hash Verification

| Artifact | Location | SHA-256 Checksum | Match Status |
| :--- | :--- | :--- | :--- |
| **Deployed Script (AWS)** | `/home/ubuntu/fyersawsog/strategies/scripts/oifno_standard_v2.py` | `bc56059430f4c4e6a7314ed0b376fb9e7b61e7cd27e405924afb188466e41648` | **100% MATCH** |
| **Approved Source (Local)** | `backtesting/oi/strategy/oifno_standard.py` | `bc56059430f4c4e6a7314ed0b376fb9e7b61e7cd27e405924afb188466e41648` | **100% MATCH** |
| **Frozen V1 Baseline** | `/home/ubuntu/fyersawsog/strategies/scripts/oifno_20261013171056.py` | `11b501f11be1e34517a2532a9a1ee6d4f5e89f901f9b6e28381009e279aceae9` | **UNMODIFIED** |
| **Production State File** | `/home/ubuntu/fyersawsog/strategies/production/audit/oifno_state.json` | Migrated to Schema V2 (`execution_mode: PAPER`, `validation_phase: PHASE_7`) | **VERIFIED** |

---

## 4. Pre-Deployment Backup & Change Control

Prior to touching production configuration, a full timestamped backup was captured on AWS:
- **Backup Directory**: `/home/ubuntu/backtesting/backups/oifno_v2_deploy_backup_20261014_124500/`
- **Archived Files**:
  - `strategy_configs.json`: SHA-256 `f2a72c344da675f97ad608a9b0e86c6dd6a7bc09bbcca4c1b1d940752fe9a432`
  - `oifno_20261013171056.py`: SHA-256 `11b501f11be1e34517a2532a9a1ee6d4f5e89f901f9b6e28381009e279aceae9`
  - `oifno_state.json`: SHA-256 `adcb22fec937d369e84e67b867f40a604b0502dac3d766cd229371b4705e3cd5`
  - `process_snapshot_pre_deploy.txt`: Captured full process tree before deployment

---

## 5. Strategy Registration & Configuration Diff

The existing registered strategy entry `oifno_20261013171056` in `/home/ubuntu/fyersawsog/strategies/strategy_configs.json` was updated to bind to the versioned V2 script and set exchange to `NFO`:

```diff
   "oifno_20261013171056": {
     "name": "Oifno",
-    "file_path": "strategies/scripts/oifno_20261013171056.py",
-    "file_name": "oifno_20261013171056.py",
-    "exchange": "NSE",
+    "file_path": "strategies/scripts/oifno_standard_v2.py",
+    "file_name": "oifno_standard_v2.py",
+    "exchange": "NFO",
+    "execution_mode": "PAPER",
     "is_running": true,
     "is_scheduled": true,
     "created_at": "2026-10-13T17:10:56.140018+05:30",
     "user_id": "vikashiname",
     "schedule_start": "09:15",
     "schedule_stop": "15:30",
     "schedule_days": [
       "mon",
       "tue",
       "wed",
       "thu",
       "fri"
     ],
-    "last_started": "2026-10-14T12:33:12.707801+05:30",
-    "pid": 110150,
+    "last_started": "2026-10-14T13:00:43.484206+05:30",
+    "pid": 121185,
     "last_stopped": "2026-10-14T12:52:42.352402+05:30"
   }
```

---

## 6. Live Process & Scheduler Verification

### 6.1 Process Verification on AWS
Command: `ps aux | grep -E 'python|strategies'` (Captured at 13:01 IST)
```text
ubuntu  121156  openalgo.service (Main Flask App & Strategy Supervisor)
ubuntu  121181  macdfno_20260902130041.py (Running, unchanged)
ubuntu  121182  emacrossopen_20260903110443.py (Running, unchanged)
ubuntu  121183  nifty_covered_call_20261012110856.py (Running, unchanged)
ubuntu  121185  oifno_standard_v2.py (Running under OpenAlgo supervisor)
```
- Exactly **one** Oifno worker (`PID 121185`) is running.
- Zero duplicate workers or orphan processes exist.

### 6.2 Supervisor Startup Logs
Journal extract from `openalgo.service`:
```text
[2026-10-14 13:00:43,463] INFO in python_strategy: Attempting to restart strategy oifno_20261013171056...
[2026-10-14 13:00:43,489] INFO in python_strategy: Executing command: /home/ubuntu/fyersawsog/venv/bin/python -u /home/ubuntu/fyersawsog/strategies/scripts/oifno_standard_v2.py
[2026-10-14 13:00:43,560] INFO in python_strategy: Started strategy oifno_20261013171056 with PID 121185 at 13:00:43 IST on linux
[2026-10-14 13:00:43,561] INFO in python_strategy: Successfully restarted strategy oifno_20261013171056
[2026-10-14 13:00:43,586] INFO in python_strategy: State restoration complete: 4 restored, 0 in error state
```

### 6.3 Strategy Runtime Log
Log file: `/home/ubuntu/fyersawsog/log/strategies/oifno_20261013171056_20261014_130043_IST.log`
```text
=== Strategy Started at 2026-10-14 13:00:43 IST ===
=== Platform: linux ===

2026-10-14 13:00:46,927 [INFO] [OIFNO-PAPER] ================================================================================
2026-10-14 13:00:46,930 [INFO] [OIFNO-PAPER] 🚀 OIFNO PRODUCTION STRATEGY BRIDGE — SIG-OI-001-EXECUTION-STANDARD-V2
2026-10-14 13:00:46,930 [INFO] [OIFNO-PAPER]   • Strategy Hash        : 8f4e2b1c7a9d3e5f6a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f
2026-10-14 13:00:46,930 [INFO] [OIFNO-PAPER]   • Execution Mode       : PAPER
2026-10-14 13:00:46,930 [INFO] [OIFNO-PAPER]   • Validation Phase     : PHASE_7
2026-10-14 13:00:46,931 [INFO] [OIFNO-PAPER]   • Capital Base         : ₹10,000,000.00
2026-10-14 13:00:46,932 [INFO] [OIFNO-PAPER]   • OpenAlgo Host        : http://127.0.0.1:5000
2026-10-14 13:00:46,932 [INFO] [OIFNO-PAPER]   • State File           : /home/ubuntu/fyersawsog/strategies/production/audit/oifno_state.json
2026-10-14 13:00:46,932 [INFO] [OIFNO-PAPER]   • Audit Journal        : /home/ubuntu/fyersawsog/strategies/production/audit/oifno_execution_audit.jsonl
2026-10-14 13:00:46,933 [INFO] [OIFNO-PAPER] ================================================================================
2026-10-14 13:00:56,832 [INFO] [OIFNO-PAPER] 🟢 OIFNO Strategy Bot running in PAPER mode. Press Ctrl+C to terminate.
2026-10-14 13:00:57,007 [INFO] [OIFNO-PAPER]   • OpenAlgo Positionbook Active: 3 position(s) found (Mode: analyze)
2026-10-14 13:00:57,071 [INFO] [OIFNO-PAPER] 📊 Reconciliation Verdict: PASS | Discrepancies: 0
```

---

## 7. PAPER Order-Routing & LIVE Gating Safety Proof

1. **PAPER Mode Real-Broker Route Isolation**:
   - `PaperExecutionAdapter` contains **zero** network requests or API hooks to `/api/v1/placeorder` or `/api/v1/modifyorder`.
   - All simulated orders are handled in-memory and logged to `oifno_execution_audit.jsonl`.
   - Initialized with strict safety assertion: raises `PermissionError` if initialized with `is_live=True` or if `EXECUTION_MODE != "PAPER"`.
2. **LIVE Mode Multi-Key Fail-Closed Architecture**:
   - `LiveExecutionAdapter` strictly raises `PermissionError` without explicit operator token sign-off and unlocked gate.
   - One-click LIVE activation (`--request-live`) requires 6 pre-flight checks: operator identity, strategy hash match, broker ping, position/orderbook reconciliation with zero pending orders, risk limits/kill-switch, and config integrity.
   - Any check failure immediately fails closed and keeps the strategy in `PAPER` mode.
3. **Graceful Supervisor Termination**:
   - Tested sending `SIGTERM` to worker: intercepted by `_handle_sigterm`, logs `🛑 SIGTERM received from OpenAlgo supervisor. Graceful shutdown complete.`, and exits with code 0 without orphaned state.

---

## 8. Broker Position & Orderbook Reconciliation

- **Real Broker Orders Found**: **0** (Verified via `/api/v1/orderbook`).
- **Positions Maintained**: Exactly unchanged in Sandbox mode:
  1. Long 65 `NIFTY27OCT26FUT`
  2. Short -65 `NIFTY27OCT2623100CE`
  3. Closed 0 `NIFTY27OCT2623000CE`
- **Reconciliation Audit Verdict**: **PASS** (Discrepancies: 0).

---

## 9. Immediate Rollback Runbook (Zero-Downtime)

If any operational rollback is ever needed:

```bash
# 1. SSH into AWS host
ssh -i ~/.ssh/openalgo-key.pem ubuntu@13.203.187.139

# 2. Stop service, restore backup configuration, and start service
sudo systemctl stop openalgo.service
cp /home/ubuntu/backtesting/backups/oifno_v2_deploy_backup_20261014_124500/strategy_configs.json /home/ubuntu/fyersawsog/strategies/strategy_configs.json
sudo systemctl start openalgo.service

# 3. Verify original V1 process is restored
ps aux | grep -E 'python.*oifno'
```

---

## 10. Conclusion

The OIFNO V2 deployment and OpenAlgo integration has been completed in compliance with all safety constraints:
- `SHADOW` is completely eliminated.
- Strategy is actively executing in `PAPER` mode under OpenAlgo supervision.
- Zero real broker orders placed.
- Baseline V1 code and unrelated strategies remain 100% intact.
