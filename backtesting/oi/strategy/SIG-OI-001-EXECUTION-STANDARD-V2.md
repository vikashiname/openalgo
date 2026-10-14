# SIGNAL & EXECUTION CONTRACT: SIG-OI-001-EXECUTION-STANDARD-V2

**Contract Identifier:** `SIG-OI-001-EXECUTION-STANDARD-V2`  
**Supercedes:** `SIG-OI-001-PAPER-V1` (Frozen Contract Hash: `dc1063b1ccadd2e513c6d3f71a8a2f4f13465db852387204c0b27137249ed917`)  
**Deployment Tiers Supported:** Exactly Two: `PAPER` and `LIVE`  
**Obsoleted / Deprecated Terms:** `SHADOW` (eliminated as an execution mode, config setting, or user-facing status)  
**Research Status:** `PHASE_7` (Forward Validation Trial Active)  
**Live Execution Status:** `HARD-BLOCKED` (Strict Gated Specification Only; Multi-Key Authorization Required)  
**Author:** AGY Quantitative Architecture & Systems Governance  
**Date:** October 2026  

---

## 1. PURPOSE & ARCHITECTURAL SEPARATION

This document establishes the unified execution-mode standard for the Open Interest NFO Single-Stock Futures Strategy (`OIFNO`). 

Historically, research artifacts and deployment configurations conflated **Research / Validation Phases** (e.g., "Phase 7") with **Execution Modes**, using terms like "SHADOW mode", "live-paper", and "shadow scheduler". 

Under this standard, a strict architectural separation is enforced:
1. **Execution Mode (`EXECUTION_MODE`)**: Dictates order routing mechanics. Exactly two modes are supported:
   - **`PAPER`**: Automated forward simulation using in-memory / simulated execution. Real broker order placement is strictly disabled.
   - **`LIVE`**: Real capital deployment routing orders to the broker. Gated behind multi-key fail-closed authorization.
2. **Research & Validation Phase (`VALIDATION_PHASE`)**: Dictates research and statistical validation governance (e.g., `PHASE_7` forward observation trial). A strategy in `PHASE_7` runs in `PAPER` execution mode.

---

## 2. EXECUTION MODE SPECIFICATION

### 2.1 Mode Enumeration
The strategy engine enforces the following strict enum:
```python
SUPPORTED_EXECUTION_MODES = {"PAPER", "LIVE"}
```
Any setting, environment variable, or CLI option specifying `SHADOW` or any other string must fail closed immediately:
```python
if mode not in SUPPORTED_EXECUTION_MODES:
    raise ValueError(f"Invalid execution mode '{mode}'. OIFNO strictly supports: {sorted(SUPPORTED_EXECUTION_MODES)}")
```

### 2.2 PAPER Mode (Default Operational Tier)
* **Default Status**: When `OIFNO_EXECUTION_MODE` is unset, the engine defaults to `PAPER`.
* **Order Routing**: Strictly in-memory and simulated (`PaperExecutionAdapter`).
* **Broker Safeguard**: Zero calls to OpenAlgo's `/api/v1/placeorder` API or broker order endpoints.
* **Friction & Simulation Model**:
  - Entry Fill: Simulated at Day $T+1$ Market Open auction.
  - Entry Slippage: +2.5 basis points half-spread.
  - Exit Slippage: -2.5 basis points half-spread.
  - Statutory Charges: -3.0 basis points round-trip (STT, Stamp, Exchange, GST, SEBI).
  - Limit Collar (+30 bps above Day $T$ Close): Orders exceeding collar are missed (`MISSED_COLLAR`).
  - Gap Protection (+1.50% above Day $T$ Close): Opening gaps exceeding +1.50% are missed (`MISSED_GAP`).
  - Partial Fills: Contracts with turnover $< ₹10\text{ Crores}$ simulated at 50% allocation (`PARTIAL`).

### 2.3 LIVE Mode (Hard-Blocked Research Specification)
* **Default State**: Gated fail-closed (`LIVE_TRADING_ENABLED: bool = False`).
* **Multi-Key Authorization Requirements**:
  To initialize in `LIVE` mode, all four conditions must be met simultaneously:
  1. `OIFNO_EXECUTION_MODE == "LIVE"`
  2. `LIVE_TRADING_ENABLED == True` (explicit code constant modification)
  3. `OIFNO_LIVE_CONFIRMED == "YES_ENABLE_LIVE_ORDERS"` (environment token)
  4. `OIFNO_OPERATOR_SIGN_OFF == "AUTHORIZED_BY_OPERATOR"` (cryptographic/operator token)
* If any condition is absent, the engine raises `PermissionError` and immediately halts.
* Under this task, **LIVE mode is retained as a gated specification only; no live orders may be placed**.

---

## 3. RESEARCH PHASE PRESERVATION (PHASE 7)

* **Phase Definition**: `PHASE_7` designates the 30-to-60 session forward validation protocol under realistic friction to accumulate statistical evidence of mean-reversion edge on NSE single-stock futures.
* **Separation from Mode**:
  - `validation_phase: "PHASE_7"` is stored in persistent state and telemetry.
  - Execution runs under `execution_mode: "PAPER"`.
* **Telemetry & Alerts**:
  - Log prefix: `[OIFNO-PAPER]`
  - Telegram alert banner:
    ```html
    🔬 <b>[OIFNO PAPER TRADING]</b>
    <b>Strategy:</b> Oifno (OI Analysis)
    <b>Phase:</b> Phase 7 Validation
    ```

---

## 4. PERSISTENT STATE SCHEMA & LEGACY MIGRATION

### 4.1 V2 State Schema (`oifno_state.json`)
```json
{
  "strategy": "OIFNO_STANDARD_V2",
  "contract_version": "SIG-OI-001-EXECUTION-STANDARD-V2",
  "execution_mode": "PAPER",
  "validation_phase": "PHASE_7",
  "last_saved_at": "2026-10-14T12:00:00.000000",
  "risk_state": {
    "initial_capital": 10000000.0,
    "current_capital": 10000000.0,
    "high_watermark": 10000000.0,
    "current_drawdown_pct": 0.0,
    "circuit_breaker_tripped": false
  },
  "tracked_positions": {},
  "executed_signal_ids": [],
  "execution_history": []
}
```

### 4.2 Transparent Legacy Migration
When reading existing state files containing `"phase7_mode": "SHADOW"`:
1. `execution_mode` is automatically set to `"PAPER"`.
2. `validation_phase` is set to `"PHASE_7"`.
3. The obsolete `phase7_mode` key is permanently pruned upon state write.
4. Historical positions and risk high-watermarks are preserved with zero data loss.

---

## 5. GOVERNANCE & PROMOTION GATES

Before OIFNO can be promoted from `PAPER` to `LIVE`:
1. **Accumulate $\ge 180$ Days of Positive Net Returns** in `PAPER` mode with Profit Factor $\ge 1.50$.
2. Complete multi-session broker order reconciliation with zero discrepancies.
3. Formal human operator sign-off and multi-key live deployment authorization.
4. Production release bump and verification of broker margin adequacy.
