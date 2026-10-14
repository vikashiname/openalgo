# Live Deployment Readiness Audit Report
**Execution Mode:** STRICT READ-ONLY AUDIT  
**Audit Date:** 2026-10-13  
**Audited Targets:**
- `strategies/liveonopenalgo/macdfno.py` & `liveopenalgo/macdfno.py`
- `strategies/liveonopenalgo/oifno.py` & `liveopenalgo/oifno.py`
- `backtesting/emacrossopen/emacrossopen.py` & `strategies/liveonopenalgo/emacrossopen.py` & `liveopenalgo/emacrossopen.py`
- `services/close_position_service.py`
- Systemd units: `production/systemd/openalgo-macdfno.service`, `production/systemd/openalgo-oifno.service`, `production/systemd/openalgo-emacross.service`

---

## 1. Executive Summary & Verdict

| Component | Overall Status | Critical Blocker / Primary Concern |
| :--- | :---: | :--- |
| **`oifno.py`** | **FAIL** | Code contains `LIVE_TRADING_ENABLED: bool = True` ([oifno.py#L126](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L126)) and asserts `PHASE7_MODE == "LIVE"` ([oifno.py#L129-L134](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L129-L134)). Running internal unit tests or shadow mode triggers assertion failure. |
| **`macdfno.py`** | **FAIL** | Gating check removed ([macdfno.py#L1660-L1661](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L1660-L1661)). Sends real orders directly via OpenAlgo API without client-side mode verification if server is in LIVE mode. Also shares `heartbeat.json` file path with other strategies in `strategies/liveonopenalgo/`. |
| **`emacrossopen.py`** | **PASS / CONDITIONAL** | Strict pre-flight safety check `verify_paper_mode()` ([emacrossopen.py#L1552-L1605](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L1552-L1605), [L2089-L2094](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L2089-L2094)) halts execution if OpenAlgo is LIVE or unconfirmed. Shares default `heartbeat.json` path when run in same folder. |
| **`close_position_service.py`** | **PASS** | Checks `get_analyze_mode()` ([close_position_service.py#L88-L124](file:///Users/mac/Desktop/openalgo/services/close_position_service.py#L88-L124)) and routes to sandbox when analyze mode is active; blocks semi-auto square-off in live mode. |
| **Systemd Units** | **FAIL** | All services run under hardcoded paths `/home/ubuntu/fyersawsog` ([openalgo-oifno.service#L9-L11](file:///Users/mac/Desktop/openalgo/production/systemd/openalgo-oifno.service#L9-L11)). None configure distinct `LOG_FILE`, `STATE_FILE`, or `HEARTBEAT_FILE` environment variables, leading to shared state files in the script directory. |

---

## 2. File Parity: Dev vs. Production

Exact SHA-256 byte comparisons between source directories:

- `strategies/liveonopenalgo/macdfno.py` <==> `liveopenalgo/macdfno.py`: **IDENTICAL** (PASS)
- `strategies/liveonopenalgo/oifno.py` <==> `liveopenalgo/oifno.py`: **IDENTICAL** (PASS)
- `backtesting/emacrossopen/emacrossopen.py` <==> `strategies/liveonopenalgo/emacrossopen.py` <==> `liveopenalgo/emacrossopen.py`: **IDENTICAL** (PASS)

---

## 3. Detailed Audit Matrix

### Strategy 1: OIFNO (`oifno.py`)

| Check | Status | Line Reference | Audit Evidence & Observation |
| :--- | :---: | :--- | :--- |
| **Execution Mode & Real Order Guard** | **FAIL** | [oifno.py#L126](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L126)<br>[oifno.py#L129-L134](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L129-L134) | `LIVE_TRADING_ENABLED: bool = True` is hardcoded. `PHASE7_MODE = os.getenv("PHASE7_MODE", "LIVE")` raises `RuntimeError` if not `"LIVE"`. Meanwhile, `ShadowExecutionAdapter` raises `PermissionError` if `is_live=True` or `LIVE_TRADING_ENABLED` ([oifno.py#L820-L826](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L820-L826)). This contradiction causes initialization and internal tests to fail. |
| **Shadow Mode Prevention** | **FAIL** | [oifno.py#L126-L134](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L126-L134)<br>[oifno.py#L1460](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L1460) | Strategy self-test asserts `LIVE_TRADING_ENABLED is False` and `PHASE7_MODE == "SHADOW"`, which directly contradicts top-level constants. |
| **Systemd Service Isolation** | **FAIL** | [openalgo-oifno.service#L9-L11](file:///Users/mac/Desktop/openalgo/production/systemd/openalgo-oifno.service#L9-L11) | Service executes `/home/ubuntu/fyersawsog/.venv/bin/python strategies/liveonopenalgo/oifno.py --mode live-paper`. Does not define `STATE_FILE`, `LOG_FILE`, or `HEARTBEAT_FILE` overrides in environment. |
| **Position Limits & Risk Controls** | **PASS** | [oifno.py#L156-L165](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L156-L165)<br>[oifno.py#L828-L843](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L828-L843) | `MAX_PORTFOLIO_POSITIONS = 10`, 30% max sector exposure, 2.0% daily portfolio loss circuit breaker, +1.5% opening gap chase filter, and +30 bps limit collar check are implemented. |
| **Duplicate Order Prevention** | **PASS** | [oifno.py#L355-L363](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L355-L363) | Signals tracked in `executed_signal_ids` via `OIPersistentStateManager`. Prevents duplicate signal execution. |
| **State Persistence & Recovery** | **PASS** | [oifno.py#L297-L354](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L297-L354) | Uses atomic temp-file write and rename in `save_state()` to `production/audit/oifno_state.json`. Restores capital, high watermark, and positions on restart. |
| **Environment & Secret Handling** | **PASS** | [oifno.py#L105-L107](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L105-L107)<br>[oifno.py#L148-L151](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/oifno.py#L148-L151) | Loads environment via `dotenv` without hardcoding API keys. |

---

### Strategy 2: MACDFNO (`macdfno.py`)

| Check | Status | Line Reference | Audit Evidence & Observation |
| :--- | :---: | :--- | :--- |
| **Execution Mode & Real Order Guard** | **FAIL** | [macdfno.py#L1660-L1662](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L1660-L1662)<br>[macdfno.py#L1694-L1703](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L1694-L1703) | Comment explicitly notes: *"Pre-flight network blocking removed so orders are never rejected due to positionbook query latency"*. The strategy directly calls `self.client.placeorder(...)`. If OpenAlgo server is running in LIVE mode, real live broker orders will execute without a local client-side safety guard. |
| **Shadow Mode Prevention** | **FAIL** | [macdfno.py#L33](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L33)<br>[macdfno.py#L1694](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L1694) | Comment claims *"STRICTLY PAPER / ANALYZE TRADING MODE ONLY"*, but code relies entirely on OpenAlgo server setting. If server DB has `analyze_mode = False` (the default in `database/settings_db.py#L102`), orders are placed live. |
| **Systemd Service Isolation** | **FAIL** | [openalgo-macdfno.service#L9-L11](file:///Users/mac/Desktop/openalgo/production/systemd/openalgo-macdfno.service#L9-L11) | ExecStart runs `macdfno.py` without env vars. Default `HEARTBEAT_FILE` is `SCRIPT_DIR / "heartbeat.json"` ([macdfno.py#L109](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L109)), which collides with `emacrossopen.py` ([emacrossopen.py#L128](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L128)). |
| **Position Limits & Risk Controls** | **PASS** | [macdfno.py#L30](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L30)<br>[macdfno.py#L377-L387](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L377-L387) | Max 20 active positions cap, 3.5% catastrophe stop loss, 3.0% long target / 1.5% short target. |
| **Duplicate Order Prevention** | **PASS** | [macdfno.py#L1664-L1667](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L1664-L1667)<br>[macdfno.py#L218-L232](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L218-L232) | Enforces idempotency key `f"{contract_symbol}_{action}_{quantity}_{candle_time}"` in `is_order_inflight_or_filled()`. |
| **State Persistence & Recovery** | **PASS** | [macdfno.py#L134-L179](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L134-L179) | `PersistentStateManager` uses atomic temp-file rename to `macdfno_state.json`. Persists candle processing, positions, and orders. |
| **Environment & Secret Handling** | **PASS** | [macdfno.py#L82-L85](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L82-L85)<br>[macdfno.py#L259-L270](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py#L259-L270) | Reads credentials from environment variables (`OPENALGO_API_KEY`, `OPENALGO_HOST`). |

---

### Strategy 3: EMACROSS (`emacrossopen.py`)

| Check | Status | Line Reference | Audit Evidence & Observation |
| :--- | :---: | :--- | :--- |
| **Execution Mode & Real Order Guard** | **PASS** | [emacrossopen.py#L1552-L1605](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L1552-L1605)<br>[emacrossopen.py#L2089-L2094](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L2089-L2094) | `place_paper_order()` performs mandatory pre-flight check `verify_paper_mode()`. If OpenAlgo returns mode `"live"`, it logs a critical error, sends an alert, and returns `None`, blocking the order. |
| **Shadow Mode Prevention** | **PASS** | [emacrossopen.py#L1586-L1589](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L1586-L1589) | Explicit runtime verification against OpenAlgo server API (`/api/v1/positionbook`). Blocks order execution if not `"analyze"` or `"paper"`. |
| **Systemd Service Isolation** | **FAIL** | [openalgo-emacross.service#L9-L11](file:///Users/mac/Desktop/openalgo/production/systemd/openalgo-emacross.service#L9-L11) | ExecStart runs `strategies/liveonopenalgo/emacrossopen.py` without env overrides. Default `HEARTBEAT_FILE` is `SCRIPT_DIR / "heartbeat.json"` ([emacrossopen.py#L128](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L128)), colliding with `macdfno.py`. |
| **Position Limits & Risk Controls** | **PASS** | [emacrossopen.py#L148-L156](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L148-L156)<br>[emacrossopen.py#L365-L390](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L365-L390) | Asymmetric targets (+3.0% Long, +1.5% Short), 6.0% catastrophe stop loss, 0.35% trailing runner, and dead-zone trading hour filters implemented. |
| **Duplicate Order Prevention** | **PASS** | [emacrossopen.py#L2096-L2100](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L2096-L2100)<br>[emacrossopen.py#L2030-L2070](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L2030-L2070) | Idempotency key check plus orderbook pre-retry query reconciliation to prevent duplicate execution. |
| **State Persistence & Recovery** | **PASS** | [emacrossopen.py#L127](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L127)<br>[emacrossopen.py#L1546-L1550](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L1546-L1550) | State maintained in `emacrossopen_state.json` with startup position reconciliation and audit. |
| **Environment & Secret Handling** | **WARNING** | [emacrossopen.py#L195-L198](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/emacrossopen.py#L195-L198) | Contains a fallback default API key `"a93a6d4254ac..."` in code if `OPENALGO_API_KEY` is not set in environment. |

---

### Service: Close Position Service (`close_position_service.py`)

| Check | Status | Line Reference | Audit Evidence & Observation |
| :--- | :---: | :--- | :--- |
| **Order-Event Handling & Analyze Mode** | **PASS** | [close_position_service.py#L88-L124](file:///Users/mac/Desktop/openalgo/services/close_position_service.py#L88-L124) | Directly calls `get_analyze_mode()`. If True, redirects requests to `sandbox_close_position(...)` and publishes `PositionClosedEvent(mode="analyze")`. Never hits live broker APIs in analyze mode. |
| **Order-ID Correlation & Status Codes** | **PASS** | [close_position_service.py#L180-L206](file:///Users/mac/Desktop/openalgo/services/close_position_service.py#L180-L206) | Correctly parses responses, translates broker status codes (200, 404, 429, 500), and records event payloads to bus. |
| **Semi-Auto Guard** | **PASS** | [close_position_service.py#L246-L267](file:///Users/mac/Desktop/openalgo/services/close_position_service.py#L246-L267) | Blocks position close in semi-auto mode when running live, while permitting execution when in sandbox/analyze mode. |
| **Error Handling & Backpressure** | **PASS** | [close_position_service.py#L143-L163](file:///Users/mac/Desktop/openalgo/services/close_position_service.py#L143-L163) | Explicitly catches `BrokerBusyError` (HTTP 429) and generic exceptions (HTTP 500), publishing event bus records. |

---

## 4. Resource & State Collision Matrix

| Resource | `macdfno.py` Default | `oifno.py` Default | `emacrossopen.py` Default | Collision Risk |
| :--- | :--- | :--- | :--- | :---: |
| **Log File** | `log/strategies/macd_fno.log` | `log/strategies/oifno.log` | `log/strategies/emacrossopen.log` | **NONE** (Isolated) |
| **State File** | `macdfno_state.json` | `production/audit/oifno_state.json` | `emacrossopen_state.json` | **NONE** (Isolated) |
| **Heartbeat File** | `heartbeat.json` | `oifno_heartbeat.json` | `heartbeat.json` | **CRITICAL COLLISION**: `macdfno` and `emacrossopen` both write to `SCRIPT_DIR / "heartbeat.json"` |
| **Watchdog Target** | Checks `heartbeat.json` | Checks `heartbeat.json` | Checks `heartbeat.json` | **CORRUPTION**: Watchdog cannot distinguish which strategy last updated the file |

---

## 5. Event Flow & Safe Sandbox Validation

### Expected OpenAlgo Log Entries for Lifecycle Confirmation
1. **Startup & Mode Verification**:
   - `GET /api/v1/positionbook` -> Returns HTTP 200 with `{"status": "success", "mode": "analyze", "data": [...]}`.
2. **Order Placement (Sandbox)**:
   - `POST /api/v1/placeorder` -> Returns HTTP 200 with `{"status": "success", "mode": "analyze", "orderid": "SB-...", "message": "Order placed successfully"}`.
   - Event bus publishes `OrderPlacedEvent(mode="analyze", api_type="placeorder", orderid="SB-...")`.
3. **Position Close (Sandbox)**:
   - `POST /api/v1/closeposition` -> Dispatched to `sandbox_close_position()`.
   - Event bus publishes `PositionClosedEvent(mode="analyze", api_type="closeposition", symbol="...", message="Position closed")`.
   - Returns HTTP 200 with `{"status": "success", "mode": "analyze", "message": "All Open Positions Squared Off"}`.

### Verification of Safe Event Flow
A zero-risk validation order can be tested by:
1. Ensuring the OpenAlgo host database setting has `analyze_mode = 1` (verified via `GET /api/v1/settings` or `database/settings_db.py`).
2. Sending a synthetic test payload using an active API key to `/api/v1/placeorder` with `symbol="IDEA"`, `exchange="NSE"`, `quantity=1`, `action="BUY"`.
3. Verifying that the returned order ID starts with `SB-` (Sandbox prefix) and no broker API network calls occur.

---

## 6. Exact Next Safe Step

**DO NOT START ANY OF THE THREE STRATEGIES AS SYSTEMD SERVICES YET.**

The exact next safe step required before any live or shadow deployment is:
1. **Resolve Governance Inconsistency in `oifno.py`**:
   - Align `LIVE_TRADING_ENABLED` and `PHASE7_MODE` assertion logic so that `--mode live-paper` / `PHASE7_MODE=SHADOW` does not throw fatal exceptions.
2. **Add Client-Side Safety Gate to `macdfno.py`**:
   - Re-introduce the pre-flight `verify_paper_mode()` check before order dispatch to guarantee it never fires live orders when shadow trading is intended.
3. **Isolate Systemd Unit Configurations**:
   - Update `production/systemd/openalgo-macdfno.service` and `production/systemd/openalgo-emacross.service` to pass explicit, unique `HEARTBEAT_FILE`, `STATE_FILE`, and `LOG_FILE` environment variables.
4. **Confirm OpenAlgo Server Mode**:
   - Verify that the target OpenAlgo server instance (`https://vikashiname.in`) has `analyze_mode` set to `True` before starting paper engines.
