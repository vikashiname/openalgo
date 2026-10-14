# OIFNO V2: 60-SESSION FORWARD SHADOW VALIDATION PROTOCOL
**Target Strategy:** `SIG-OI-001-PAPER-V2-DRAFT`  
**Governance Tier:** PROSPECTIVE FORWARD SHADOW TRIAL (LIVE ORDER ROUTING HARD-BLOCKED)  
**Observation Horizon:** 60 Consecutive Official NSE Trading Sessions (~3 Calendar Months)  
**Author:** AGY Quantitative Research & Governance Architecture  
**Working Directory:** `backtesting/oi/v2_validation/`  

---

## 1. PROTOCOL MANDATE & OBJECTIVE

This document establishes the binding operational protocol for the **60-Session Prospective Forward Shadow Validation Trial** of `SIG-OI-001-PAPER-V2-DRAFT`.

### Primary Objective:
To independently observe and verify the execution realism, order book fill rates, opening auction slippage, limit collar non-fills, and prospective alpha persistence of the V2 strategy in **simulated real-time market conditions without deploying real financial capital or modifying live trading strategies**.

### Hard Safety Assertions:
1. `LIVE_TRADING_ENABLED = False` is hardcoded and immutable across all test adapters.
2. Zero orders shall be submitted to any real-money broker trading gateway (Zerodha Kite, OpenAlgo live bridge, Angel One, Upstox, Shoonya).
3. The trial runs in parallel shadow observation mode using OpenAlgo's synthetic/paper execution adapter.
4. Any attempt to enable live order routing will immediately trip a fail-closed exception and abort execution.

---

## 2. SYSTEM ARCHITECTURE & ISOLATION GUARANTEES

```
┌────────────────────────────────────────────────────────────────────────┐
│                        NSE MARKET DATA FEEDS                           │
│  (15:30 IST EOD Bhavcopy + 09:00-09:15 IST Pre-Market Opening Quotes)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     OIFNO V2 SIGNAL ENGINE                             │
│  • Screen: ΔOI <= -2.0% & Ret_1D <= -1.5% & Bear Body >= 40%           │
│  • Rank: Most negative ΔOI% ascending -> Top 10 slots (Max 2/sector)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   SHADOW EXECUTION ADAPTER (HARD-BLOCKED)              │
│  • Rule 1: Gap Protection (Open > Ref + 1.50% -> Suppressed)           │
│  • Rule 2: Limit Collar (Open > Ref + 30 bps -> Cancelled at 09:17)    │
│  • Rule 3: Bid-Ask Slippage (+2.5 bps entry, -2.5 bps exit)            │
│  • Rule 4: Realistic Statutory Costs (STT, Stamp, SEBI, GST, Exch)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    IMMUTABLE SHADOW AUDIT LEDGERS                      │
│  • shadow_v2_signals.parquet  • shadow_v2_intents.parquet              │
│  • shadow_v2_ledger.parquet   • shadow_v2_daily_nav.parquet            │
└────────────────────────────────────────────────────────────────────────┘
```

* **No Production Interference:** The shadow runner operates in a separate process space and logs to isolated audit directories (`backtesting/oi/v2_validation/shadow_audit/`). `strategies/liveonopenalgo/oifno.py` remains completely untouched.

---

## 3. DAILY OPERATIONAL LIFECYCLE

The shadow runner executes five strictly timestamped daily phases:

### Phase 1: Signal Screening & Candidate Ranking (15:30–16:00 IST Day $T$)
1. Ingest official NSE Derivatives Bhavcopy upon exchange publication.
2. Filter for liquid contracts: Near-month `FUTSTK`, $\text{DTE} > 3$, rolling turnover $\ge ₹5\text{ Cr}$.
3. Evaluate V2 criteria:
   - $\text{Return}_{1\text{D}}(T) \le -1.50\%$
   - $\Delta\text{OI}_{\%}(T) \le -2.00\%$
   - $\text{Close}(T) < \text{Open}(T)$ with $\text{Body Ratio}(T) \ge 0.40$
4. Rank qualified candidates by $\Delta\text{OI}_{\%}$ ascending (strongest contraction first).
5. Select Top-10 candidates subject to the maximum 2 positions per sector constraint.
6. Persist candidate list into `shadow_v2_state.json`.

### Phase 2: Pre-Market Verification (09:00–09:14 IST Day $T+1$)
1. Fetch 09:07 IST pre-market indicative equilibrium prices from OpenAlgo market feed.
2. Define Reference Price: $P_{\text{ref}} = \text{Close}(T)$.
3. Compute Order Price Bounds:
   - Limit Collar Price: $P_{\text{limit}} = \text{round}(P_{\text{ref}} \times 1.0030, 2)$
   - Gap Protection Ceiling: $P_{\text{gap}} = \text{round}(P_{\text{ref}} \times 1.0150, 2)$
4. Calculate slot sizing: Quantity $= \lfloor ₹10,00,000 / P_{\text{ref}} \rfloor$ (rounded to contract lot size).
5. Generate `OrderIntent` objects with status `PENDING_SHADOW`.

### Phase 3: Opening Auction Execution Simulation (09:15:00 IST Day $T+1$)
1. Ingest opening traded price $P_{\text{open}}(T+1)$ at 09:15:05 IST.
2. Evaluate Gap Protection:
   - If $P_{\text{open}}(T+1) > P_{\text{gap}}$: Mark intent as `MISSED_GAP`. Log reason: `GAP_PROTECTION_TRIPPED (> +1.50%)`. Order suppressed. No trade.
3. Evaluate Limit Collar:
   - If $P_{\text{open}}(T+1) > P_{\text{limit}}$: Mark intent as `PENDING_COLLAR_TIMEOUT`. Order cannot fill in open auction.
   - If $P_{\text{open}}(T+1) \le P_{\text{limit}}$: Mark intent as `FILLED`.
     $$\text{Fill Price} = \text{round}(P_{\text{open}}(T+1) \times 1.00025, 2) \quad (+2.5\text{ bps spread slippage})$$

### Phase 4: Limit Collar Timeout Enforcement (09:17:00 IST Day $T+1$)
1. At 09:17:00 IST, query 2-minute intraday low $P_{\text{low}}(09:15\text{--}09:17)$.
2. If $P_{\text{low}} \le P_{\text{limit}}$, simulate delayed fill at $P_{\text{limit}}$.
3. If price remained above $P_{\text{limit}}$ for the entire 2-minute window:
   - Mark intent as `MISSED_COLLAR`. Order is hard-cancelled. No position entered.

### Phase 5: Position Exit Execution (09:15:00 IST Day $T+2$)
1. Positions entered on Day $T+1$ exit at Day $T+2$ market open auction.
2. Simulated exit fill price:
   $$P_{\text{exit}} = \text{round}(P_{\text{open}}(T+2) \times 0.99975, 2) \quad (-2.5\text{ bps spread slippage})$$
3. Deduct statutory charges (STT 1.0 bps, Stamp 0.2 bps, Exchange 0.38 bps, SEBI 0.02 bps, GST 0.3 bps, Brokerage flat ₹20).
4. Compute realized Net P&L and update daily portfolio NAV.

---

## 4. AUDIT DATA LOGGING & SCHEMA REQUIREMENTS

The trial must record all observations into four immutable daily Parquet tables:

### 4.1 Candidate Signals Ledger (`shadow_v2_signals.parquet`)
* Fields: `session_date`, `symbol`, `close`, `prev_close`, `ret_1d_pct`, `oi_total`, `prev_oi_total`, `delta_oi_pct`, `open`, `high`, `low`, `body_ratio`, `is_bear_candle`, `turnover_lakh`, `dte`, `sector`, `qualified_status`, `disqualification_reason`.

### 4.2 Order Intent Ledger (`shadow_v2_intents.parquet`)
* Fields: `session_date`, `symbol`, `contract_symbol`, `ref_price`, `limit_price`, `max_gap_price`, `allocated_capital`, `order_quantity`, `open_price_t1`, `gap_pct`, `execution_status` (`FILLED`, `MISSED_COLLAR`, `MISSED_GAP`, `SECTOR_LIMIT_REJECTED`), `fill_price`, `slippage_bps`, `fill_timestamp`.

### 4.3 Closed Trade Ledger (`shadow_v2_trades.parquet`)
* Fields: `trade_id`, `symbol`, `contract_symbol`, `sector`, `entry_date`, `entry_price`, `exit_date`, `exit_price`, `holding_period`, `position_size`, `allocated_capital`, `gross_pnl`, `statutory_costs`, `slippage_cost`, `net_pnl`, `net_return_pct`, `mfe_pct`, `mae_pct`, `why_entered`, `outcome_classification`.

### 4.4 Daily NAV Ledger (`shadow_v2_daily_nav.parquet`)
* Fields: `trade_date`, `portfolio_equity`, `cash_balance`, `invested_capital`, `active_slots_count`, `daily_net_pnl`, `daily_return_pct`, `peak_equity`, `drawdown_pct`.

---

## 5. OBJECTIVE PREDEFINED PASS/FAIL GATES

The 60-session trial shall be evaluated strictly against the following quantitative gates before any consideration of formal contract freezing:

| Gate Identifier | Dimension | Minimum Passing Criteria | Failure Threshold | Rationale |
| :--- | :--- | :---: | :---: | :--- |
| **GATE-1: SAMPLE** | Statistical Sample Size | $\ge 25$ closed trades | $< 20$ closed trades | Ensures sufficient sample size to evaluate edge over 60 sessions. |
| **GATE-2: WIN RATE** | Realized Win Rate | $\ge 52.0\%$ | $< 48.0\%$ | Confirms mean-reversion directional edge persists out-of-sample. |
| **GATE-3: EXPECTANCY** | Mean Net Realized Return | $\ge +15.0\text{ bps}$ per trade | $< +5.0\text{ bps}$ per trade | Verifies net edge remains comfortably above baseline friction (8 bps). |
| **GATE-4: SLIPPAGE** | Realized Execution Friction | Round-trip slippage $\le 5.0\text{ bps}$ | $> 10.0\text{ bps}$ | Guards against opening auction spread widening beyond modeled assumptions. |
| **GATE-5: FILL RATE** | Limit Collar Fill Efficiency | $\ge 55.0\%$ of qualified candidates | $< 40.0\%$ | Confirms the +30 bps collar does not cause excessive non-fill starvation. |
| **GATE-6: TRACKING** | Backtest Tracking Error | $\le 10.0\text{ bps}$ absolute error | $> 20.0\text{ bps}$ | Proves event-driven shadow fills track synthetic Bhavcopy auction fills. |
| **GATE-7: DRAWDOWN** | Peak-to-Trough Drawdown | $\le 5.0\%$ maximum drawdown | $\ge 8.0\%$ | Validates portfolio risk containment across the 60-session window. |
| **GATE-8: GOVERNANCE** | Hard Live-Blocked Integrity | **Zero (0) live broker orders** | $> 0$ orders attempted | Absolute compliance with live safety guardrails. |

### Overall Trial Verdict Classification:
* **PASS:** All 8 gates satisfied. Strategy eligible for formal freezing (`SIG-OI-001-PAPER-V2`) and production staging review.
* **CONDITIONAL PASS:** Gates 1, 2, 3, 7, 8 satisfied; minor non-critical variance on Gate 4 or 5. Requires collar calibration (+35 bps) or liquidity adjustment.
* **INCONCLUSIVE:** Less than 20 trades executed due to prolonged low-volatility regime. Trial extended by 30 sessions.
* **FAIL:** Gate 2, 3, 7, or 8 breached. Candidate rejected; no production promotion.

---

## 6. FAIL-CLOSED INCIDENT PROTOCOLS

1. **Exchange Feed Interruption:** If Bhavcopy or morning opening feed is delayed past 09:10 IST, all Day $T+1$ morning entries are aborted for that session.
2. **Extreme Volatility Market Halt:** If NIFTY index hits exchange circuit breaker (10% lower/upper halt), all active positions remain frozen; zero new entries permitted until normal trading resumes.
3. **Data Anomaly Circuit Breaker:** If $> 25$ candidate signals trigger on a single session (indicating Bhavcopy data corruption or universal market collapse), order generation is paused pending manual research review.

---

## 7. SIGN-OFF & OPERATIONAL STATUS

```
PROTOCOL_ID       : PROTOCOL-OIFNO-V2-SHADOW-60S
TARGET_CONTRACT   : SIG-OI-001-PAPER-V2-DRAFT
OPERATIONAL_STATE : READY FOR SHADOW INITIALIZATION
LIVE_EXECUTION    : STRICTLY FORBIDDEN (LOCKED)
GOVERNANCE_SIGN_OFF: PENDING EXPLICIT USER APPROVAL
```
