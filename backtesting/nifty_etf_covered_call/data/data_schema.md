# NORMALIZED DATA SCHEMA SPECIFICATION

**Document Phase:** Phase 2 — Feasibility & Data Validation  
**Strategy Project:** Covered Call Strategy (Buy-Write Overlay)  
**Primary Implementation:** **LONG NIFTYBEES + SHORT NIFTY 50 CALL (`NIFTY CE`)**  
**File Location:** `~/backtesting/covered call/data/data_schema.md`  
**Date:** September 2026  
**Status:** VALIDATED & FROZEN FOR FEASIBILITY  

---

## 1. PURPOSE & ARCHITECTURAL PHILOSOPHY

To guarantee data purity, reproducibility, and prevent schema drift, raw exchange files across both the **Cash Market (CM)** and **Futures & Options (F&O)** segments are converted into standardized, strongly-typed columnar schemas.

The Covered Call backtest engine and validation models will strictly consume tables adhering to these schema contracts.

---

## 2. NIFTYBEES UNDERLYING ETF SCHEMA (`niftybees_cash`)

This table records the continuous EOD traded price series of the underlying Cash Equity ETF (`NIFTYBEES`).

| Field Name | Type | Classification | Nullable | Validation Constraints / Description |
| :--- | :--- | :---: | :---: | :--- |
| `timestamp` | `TIMESTAMP_TZ` | **Mandatory** | No | Trade session close (`YYYY-MM-DD 15:30:00+05:30`). |
| `symbol` | `STRING` | **Mandatory** | No | Constant identifier (`NIFTYBEES`). |
| `isin` | `STRING` | **Mandatory** | No | Security ISIN code (`INF732E01015`). |
| `open` | `FLOAT64` | **Mandatory** | No | Opening price of the session ($> 0.0$). |
| `high` | `FLOAT64` | **Mandatory** | No | Highest traded price ($\ge \max(\text{open}, \text{close})$). |
| `low` | `FLOAT64` | **Mandatory** | No | Lowest traded price ($\le \min(\text{open}, \text{close})$). |
| `close` | `FLOAT64` | **Mandatory** | No | Traded closing price of the session ($> 0.0$). |
| `volume` | `INT64` | **Mandatory** | No | Total traded shares in session ($> 0$). |
| `turnover_inr`| `FLOAT64` | **Preferred** | Yes | Total traded value in INR ($> 0.0$). |
| `vwap` | `FLOAT64` | **Optional** | Yes | Full-day volume-weighted average price. |

---

## 3. NIFTY DERIVATIVE OPTIONS SCHEMA (`nifty_options`)

This table represents the historical option universe across all listed strikes and expiries.

| Field Name | Type | Classification | Nullable | Validation Constraints / Description |
| :--- | :--- | :---: | :---: | :--- |
| `timestamp` | `TIMESTAMP_TZ` | **Mandatory** | No | Trade session timestamp (`YYYY-MM-DD 15:30:00+05:30`). |
| `underlying` | `STRING` | **Mandatory** | No | Underlying asset code (`NIFTY`). |
| `expiry_date` | `DATE` | **Mandatory** | No | Contract expiration date (`YYYY-MM-DD`). |
| `strike_price`| `FLOAT64` | **Mandatory** | No | Strike price ($> 0.0$, multiple of 50 or 100). |
| `option_type` | `ENUM('CE','PE')`| **Mandatory** | No | Option type: `CE` (Call) or `PE` (Put). |
| `open` | `FLOAT64` | **Mandatory** | No | Opening premium ($\ge 0.0$). |
| `high` | `FLOAT64` | **Mandatory** | No | Highest traded premium ($\ge \max(\text{open}, \text{close})$). |
| `low` | `FLOAT64` | **Mandatory** | No | Lowest traded premium ($\le \min(\text{open}, \text{close})$). |
| `close` | `FLOAT64` | **Mandatory** | No | Traded closing premium ($\ge 0.0$). |
| `settle_price`| `FLOAT64` | **Mandatory** | No | Official NCL clearing settlement price ($> 0.0$). |
| `volume` | `INT64` | **Mandatory** | No | Total traded contracts ($\ge 0$). |
| `open_interest`| `INT64` | **Mandatory** | No | Total outstanding contracts ($\ge 0$). |
| `lot_size` | `INT32` | **Mandatory** | No | Active market lot size on trade date ($50, 25, 75$). |
| `iv` | `FLOAT64` | **Preferred** | Yes | Annualized Black-76 Implied Volatility ($> 0.0$). |
| `delta` | `FLOAT64` | **Preferred** | Yes | Black-76 Delta ($\Delta \in [0.0, 1.0]$ for `CE`). |

---

## 4. CROSS-INSTRUMENT STRATEGY CYCLE SCHEMA (`niftybees_covered_call_cycle`)

This table captures the end-to-end execution, sizing, settlement cash flow, and performance reconciliation for every monthly covered call cycle.

| Field Name | Type | Classification | Validation Constraints / Description |
| :--- | :--- | :---: | :--- |
| `cycle_id` | `INT32` | **Mandatory** | Sequential cycle index ($1, 2, \dots, 31$). |
| `entry_date` | `DATE` | **Mandatory** | Trade initiation date (`YYYY-MM-DD`). |
| `expiry_date` | `DATE` | **Mandatory** | Contract expiration settlement date (`YYYY-MM-DD`). |
| `s_entry` | `FLOAT64` | **Mandatory** | NIFTY 50 spot index level at cycle entry. |
| `p_entry` | `FLOAT64` | **Mandatory** | NIFTYBEES market price at cycle entry. |
| `tracking_ratio`| `FLOAT64` | **Mandatory** | Ratio $R_t = S_{\text{entry}} / P_{\text{entry}}$ ($\approx 89.0 \text{--} 93.0$). |
| `lot_size` | `INT32` | **Mandatory** | Verified market lot size ($50 \text{ or } 25$). |
| `opt_notional` | `FLOAT64` | **Mandatory** | Contract notional value ($S_{\text{entry}} \times L_t$). |
| `req_bees_units`| `INT32` | **Mandatory** | Exact integer ETF units required ($\text{round}(N_{\text{opt}} / P_{\text{entry}})$). |
| `cash_rem_1lot`| `FLOAT64` | **Mandatory** | Unencumbered cash remaining from ₹15 Lakh reference capital. |
| `est_margin_short_call`| `FLOAT64` | **Mandatory** | Clearing house SPAN + Exposure margin requirement (~11%). |
| `actual_strike`| `FLOAT64` | **Mandatory** | Selected call strike price ($\approx 2.0\%$ OTM). |
| `otm_pct` | `FLOAT64` | **Mandatory** | Actual entry moneyness percentage: $(K - S) / S \times 100$. |
| `opt_premium` | `FLOAT64` | **Mandatory** | Collected option premium per index point at entry. |
| `opt_vol` | `INT64` | **Mandatory** | Traded volume in selected strike on entry day. |
| `opt_oi` | `INT64` | **Mandatory** | Open interest in selected strike on entry day. |
| `s_exit` | `FLOAT64` | **Mandatory** | NIFTY 50 official settlement price on expiry day. |
| `p_exit` | `FLOAT64` | **Mandatory** | NIFTYBEES traded closing price on expiry day. |
| `is_itm` | `BOOLEAN` | **Mandatory** | `True` if $S_{\text{exit}} > K$ (In-The-Money); `False` otherwise. |
| `term_intrinsic`| `FLOAT64` | **Mandatory** | Terminal intrinsic value: $\max(0, S_{\text{exit}} - K)$. |
| `cash_settle_debit`| `FLOAT64` | **Mandatory** | Total cash debited from account by NCL: $\text{Intrinsic} \times L_t$. |
| `opt_pnl` | `FLOAT64` | **Mandatory** | Net option P&L in INR: $(C_0 - \text{Intrinsic}) \times L_t$. |
| `bees_ret_pct` | `FLOAT64` | **Mandatory** | NIFTYBEES cycle percentage return: $(P_{\text{exit}} - P_{\text{entry}}) / P_{\text{entry}} \times 100$. |
| `spot_ret_pct` | `FLOAT64` | **Mandatory** | NIFTY spot percentage return: $(S_{\text{exit}} - S_{\text{entry}}) / S_{\text{entry}} \times 100$. |
| `track_diff_bps`| `FLOAT64` | **Mandatory** | Tracking difference in basis points: $(\text{ETF Ret} - \text{Spot Ret}) \times 10,000$. |

---

## 5. NIFTYBEES COVERED CALL IMPLEMENTATION

### 5.1 Schema Invariants & Validation Rules
1. **Integer Quantity Invariant:** NIFTYBEES shares can only be held in discrete integer quantities ($Q \in \mathbb{Z}^+$). Fractional ETF units are strictly forbidden.
2. **Settlement Separation Invariant:** The ledger must never deduct ETF units to settle option liabilities. The option cash debit must debit the cash balance directly.
3. **No Look-Ahead Invariant:** `actual_strike` must be computed solely from `s_entry` at $T_{\text{entry}}$ close; `s_exit` and `term_intrinsic` are strictly prohibited from leaking into strike selection.
4. **Physical Storage:** Tables are stored in standardized **Apache Parquet (`.parquet`)** format using Snappy or Zstandard compression, partitioned by calendar year.
