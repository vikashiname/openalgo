# OIFNO Execution-Mode Inspection and Safety Report

**Date:** 2026-10-14  
**Audit Target:** OIFNO Strategy Bridge (`oifno_20261013171056.py`) on AWS Production Environment (`ubuntu@13.203.187.139`)  
**Status:** **INSPECTION COMPLETE — STOP RULE 6 TRIGGERED (Zero Code/Process Mutation)**  
**Safety Sign-Off:** Zero Real Broker Orders Placed | Zero Production Files Modified | Pre-Change Baseline Preserved  

---

## 1. Executive Summary & Rule 6 Trigger

Under user directive:
> *"2. Change Oifno's execution mode from the currently configured Shadow designation to PAPER, using the application's supported configuration mechanism. PAPER must mean no real broker orders.*  
> *6. If the actual configuration is ambiguous, or changing it could enable real orders, STOP without making changes and report the exact blocker."*

A rigorous, end-to-end technical inspection of the OpenAlgo application configuration mechanism, scheduler subsystem, and Oifno strategy code on AWS was conducted. 

### Finding & Stop Action:
1. **No Application-Level Execution Mode Field Exists**: OpenAlgo's Python strategy manager ([`blueprints/python_strategy.py`](file:///Users/mac/Desktop/openalgo/blueprints/python_strategy.py)) and configuration file (`strategy_configs.json`) contain **no configuration attribute, CLI parameter, or environment override** for designating a Python strategy as "SHADOW" versus "PAPER".
2. **Hard-Coded Fail-Closed Governance in Strategy Script**: In [`oifno_20261013171056.py`](file:///Users/mac/Desktop/openalgo/strategies/scripts/oifno_20261013171056.py), the execution mode is guarded by an immutable governance assertion:
   ```python
   PHASE7_MODE = os.getenv("PHASE7_MODE", "SHADOW").strip().upper()
   if PHASE7_MODE != "SHADOW":
       raise RuntimeError(
           f"CRITICAL GOVERNANCE FAILURE: PHASE7_MODE must be 'SHADOW' (received: '{PHASE7_MODE}'). "
           "Real-money execution is strictly prohibited under Phase 7 Governance."
       )
   ```
   Attempting to pass `PHASE7_MODE=PAPER` causes Oifno to **crash immediately at process startup** with a fatal `RuntimeError`. Furthermore, Test 2 of its 17-test suite explicitly asserts `assert PHASE7_MODE == "SHADOW"`.
3. **Source Code Mutation Prohibited**: Modifying the script to accept `PHASE7_MODE="PAPER"` would violate the frozen contract hash (`STRATEGY_HASH = "dc1063b1ccadd2e513c6d3f71a8a2f4f13465db852387204c0b27137249ed917"`), break the Phase 7 validation trial, and violate the mandatory directive not to edit production strategy files.
4. **Conclusion**: Per **Rule 6**, execution was **HALTED WITHOUT MUTATING PRODUCTION FILES OR SCHEDULER STATE**. Oifno is empirically proven to be **strictly PAPER-ONLY (simulated fills only, zero live order routing capabilities)**.

---

## 2. Pre-Change Configuration & Baseline Backup

Before conducting verification checks, an exact point-in-time backup of all Oifno configurations and state files was created on AWS.

### Backup Repository Location (AWS):
`/home/ubuntu/backtesting/backups/oifno_pre_correction_20261014/`

### Backed-Up Artifacts & Verification Hashes:

| File Path | Backup Path | SHA-256 Checksum |
| :--- | :--- | :--- |
| `strategies/strategy_configs.json` | `.../strategy_configs.json` | `00c617b357171766639b3ea83b8e8d8fab5894880a9796a3ef6b20ea03a15a1d` |
| `strategies/production/audit/oifno_state.json` | `.../oifno_state.json` | `7138b3ce3c853fcaee3b6a2f3fcf228e932463eef250785dd47690f3b497cb2f` |
| `strategies/scripts/oifno_20261013171056.py` | `.../oifno_20261013171056.py` | `11b501f11be1e34517a2532a9a1ee6d4f5e89f901f9b6e28381009e279aceae9` |

### Pre-Change `strategy_configs.json` Record:
```json
"oifno_20261013171056": {
  "name": "Oifno",
  "file_path": "strategies/scripts/oifno_20261013171056.py",
  "file_name": "oifno_20261013171056.py",
  "exchange": "NSE",
  "is_running": false,
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
  "last_started": "2026-10-14T10:31:47.704466+05:30",
  "pid": null,
  "last_stopped": "2026-10-14T11:04:26.718586+05:30"
}
```

---

## 3. Detailed Inspection of Oifno Architecture & Order Routing

### A. Scheduler Subsystem & Launch Mechanism
OpenAlgo’s `blueprints/python_strategy.py` launches processes via:
```python
cmd = [get_python_executable(), "-u", str(file_path.absolute())]
process = subprocess.Popen(cmd, **subprocess_args)
```
- **CLI Arguments**: The scheduler passes **zero CLI flags** to child strategy scripts. It does not pass `--mode live-paper` or `--mode paper`.
- **Environment Injections**: The scheduler injects:
  - `STRATEGY_ID = "oifno_20261013171056"`
  - `STRATEGY_NAME = "Oifno"`
  - `OPENALGO_STRATEGY_EXCHANGE = "NSE"`
  - `OPENALGO_HOST = "http://127.0.0.1:5000"`
  - `OPENALGO_API_KEY = "<decrypted_api_key>"`
- **Execution Mode Injections**: **None**. There is no parameter mechanism in OpenAlgo's Python strategy manager to configure execution mode.

### B. Strategy-Level CLI Parser
In [`oifno_20261013171056.py`](file:///Users/mac/Desktop/openalgo/strategies/scripts/oifno_20261013171056.py#L1690-L1695):
```python
parser.add_argument(
    "--mode",
    choices=["live", "live-paper", "forward-trial", "reconcile", "test-suite"],
    default="live",
    help="Execution mode: 'live' / 'live-paper' (shadow scheduler), 'forward-trial' (20+ session shadow trial), 'reconcile' (audit against OpenAlgo), 'test-suite' (run all verification tests)"
)
```
- Note that both `--mode live` and `--mode live-paper` execute the **exact same code block**:
  ```python
  elif args.mode in ["live", "live-paper"]:
      bot = OIFNOStrategyBot(initial_capital=args.capital)
      logger.info("🟢 OIFNO Strategy Bot running in SHADOW mode. Press Ctrl+C to terminate.")
  ```
- There is **no CLI choice for `--mode paper`**. Supplying `--mode paper` causes `argparse.ArgumentError` and immediately aborts execution.

### C. Proof of Zero Real Broker Order Routing
Unlike `Macdfno`, `Emacrossopen`, and `Nifty Covered Call` (which actively make HTTP POST calls to OpenAlgo's `/api/v1/placeorder` API endpoint), `oifno_20261013171056.py`:
1. **Contains 0 Calls to `/api/v1/placeorder`**: Grep analysis across the entire script reveals zero calls to order placement endpoints or `client.placeorder(...)`.
2. **Hard-Coded Live Block**:
   ```python
   LIVE_TRADING_ENABLED: bool = False
   ```
3. **Execution Adapter Guard**:
   ```python
   class ShadowExecutionAdapter(ExecutionAdapter):
       def __init__(self, is_live: bool = LIVE_TRADING_ENABLED):
           if is_live:
               raise PermissionError("FATAL: ShadowExecutionAdapter refuses live configuration!")
           self.is_live = False

       def submit_intent(self, intent: OrderIntent, market_open_price: float, ...):
           if self.is_live or LIVE_TRADING_ENABLED:
               raise PermissionError("HARD-BLOCKED: Real-money routing blocked.")
   ```
4. **Reconciliation Security Audit**: Every 60 seconds, Oifno queries OpenAlgo's orderbook via `/api/v1/orderbook`. If any order attributed to `STRATEGY_NAME` is found in the broker book, it triggers a `CRITICAL_SECURITY_BREACH` state and halts.

---

## 4. Empirical Test Results & Fail-Closed Validation

### Test 1: Full Automated Production Test Suite (AWS)
Executed on AWS using production virtualenv:
`/home/ubuntu/fyersawsog/venv/bin/python strategies/scripts/oifno_20261013171056.py --mode test-suite`

**Result: 17/17 TESTS PASSED (100% PASS RATE)**
- ✅ Test 1: Strategy Hash Verification (`dc1063b1...` verified)
- ✅ Test 2: Live Trading Hard-Block Guarantee (`PermissionError` confirmed)
- ✅ Test 3: OpenAlgo Connectivity & Fyers Auth Handling (`analyze` mode confirmed)
- ✅ Test 4: NFO FUTSTK Contract Resolution (RELIANCE resolved, NIFTY index rejected)
- ✅ Test 5: Frozen Signal Contract Logic (`SIG-OI-001-PAPER-V1` verified)
- ✅ Test 6: Cross-Sectional Ranking Heuristic (ΔOI% contraction ranked)
- ✅ Test 7: Limit Collar & Gap Protection (+30 bps collar & +1.5% gap enforced)
- ✅ Test 8: Partial Fill Simulation on Low Turnover (< ₹10 Cr partial fills)
- ✅ Test 9: Risk Engine Limits & Sector Caps (30% sector cap verified)
- ✅ Test 10: Circuit Breakers (10% drawdown trips circuit breaker)
- ✅ Test 11: SHA-256 Duplicate Signal Protection (Idempotent rejection verified)
- ✅ Test 12: Stale Data & Missing Field Rejection (Fail-closed verified)
- ✅ Test 13: Emergency Kill Switch (Halts risk immediately)
- ✅ Test 14: Process Crash & Persistent State Recovery (Disk reload verified)
- ✅ Test 15: Position & Broker Reconciliation Engine (Zero real broker orders verified)
- ✅ Test 16: Audit Trail Logging (Append-only journal verified)
- ✅ Test 17: Fyers Auth Failure Handling (`AUTH_FAILED` fail-closed verified)

### Test 2: Simulated `PHASE7_MODE=PAPER` Override (AWS)
Executed on AWS:
`PHASE7_MODE=PAPER /home/ubuntu/fyersawsog/venv/bin/python strategies/scripts/oifno_20261013171056.py --mode live`

**Output:**
```
Traceback (most recent call last):
  File "/home/ubuntu/fyersawsog/strategies/scripts/oifno_20261013171056.py", line 131, in <module>
    raise RuntimeError(
RuntimeError: CRITICAL GOVERNANCE FAILURE: PHASE7_MODE must be 'SHADOW' (received: 'PAPER'). Real-money execution is strictly prohibited under Phase 7 Governance.
```
*Empirical Confirmation: The script strictly refuses execution and aborts fail-closed if `PHASE7_MODE` is altered.*

---

## 5. Unaltered State Verification (Other Strategies & Positions)

All other production strategies, databases, and positions on AWS remain 100% undisturbed:

### A. Open Positions in Sandbox (`db/sandbox.db`)
Verified query: `SELECT symbol, quantity, average_price, ltp FROM sandbox_positions WHERE quantity != 0;`
- `NIFTY27OCT26FUT`: **+65 units** @ ₹22,740.20 (LTP: ₹22,733.10) — **UNCHANGED**
- `NIFTY27OCT2623100CE`: **-65 units** @ ₹86.80 (LTP: ₹83.10) — **UNCHANGED**
- Total Active Orders: 750 — **UNCHANGED**

### B. Production Strategy Configurations & Source Integrity

| Strategy | AWS Script Path | Hash Verified Identical? | Config Status in `strategy_configs.json` |
| :--- | :--- | :---: | :--- |
| **Nifty Covered Call** | `strategies/scripts/nifty_covered_call_20261012110856.py` | ✅ Yes | `is_running: false`, `is_scheduled: true` |
| **Macdfno** | `strategies/scripts/macdfno_20260902130041.py` | ✅ Yes | `is_running: false`, `is_scheduled: true` |
| **Emacrossopen** | `strategies/scripts/emacrossopen_20260903110443.py` | ✅ Yes | `is_running: false`, `is_scheduled: true` |
| **Oifno** | `strategies/scripts/oifno_20261013171056.py` | ✅ Yes | `is_running: false`, `is_scheduled: true` |

---

## 6. Summary Comparison Table

| Dimension | Before Audit | After Audit | Reason / Explanation |
| :--- | :--- | :--- | :--- |
| **Oifno Operating Mode** | `SHADOW (Phase 7 Simulation)` | `SHADOW (Phase 7 Simulation)` | Preserved per Rule 6; application has no supported configuration mechanism to change this without causing fatal script crashes. |
| **Broker Order Placement** | `HARD-BLOCKED (0 Orders)` | `HARD-BLOCKED (0 Orders)` | Hard constant `LIVE_TRADING_ENABLED: False`, zero `/api/v1/placeorder` code. |
| **OpenAlgo Global Mode** | `ANALYZE` (analyze_mode=1) | `ANALYZE` (analyze_mode=1) | Sandbox database routing strictly enforced. |
| **`strategy_configs.json`** | Intact | Intact | Byte-for-byte identical to pre-change backup. |
| **Active Sandbox Positions** | 2 Legs (Covered Call) | 2 Legs (Covered Call) | Completely undisturbed. |
| **Real Broker Orders** | 0 | 0 | Zero real orders placed. |
| **Phase 7 Research Status** | Active (Forward Shadow Trial) | Active (Forward Shadow Trial) | Preserved intact per instruction 3. |

---

## 7. Next Steps & Recommendation

1. **Retain Current Configuration**: Oifno is already performing pure paper/shadow simulation without touching real capital or OpenAlgo orderbooks.
2. **Do Not Force an Environment Override**: Do not set `PHASE7_MODE=PAPER`, as this violates the fail-closed assertion and halts the strategy.
3. **Formal Mode Unification (Future Work)**: If the term "SHADOW" should formally be rebranded to "PAPER" in Oifno's logs and Telegram headers, this requires an updated contract specification (`SIG-OI-001-PAPER-V2`) with an updated SHA-256 hash.
