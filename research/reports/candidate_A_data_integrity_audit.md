# Quantitative Research Audit — Candidate A Data & Research Integrity Audit

---

### Executive Integrity Summary

| Audit Item | Finding / Confirmation | Integrity Status |
| :--- | :--- | :---: |
| **1. Underlying Instrument Used** | **NIFTY 50 Spot Index (`^NSEI`)** with synthetic statutory futures friction overlay. | ⚠️ **PROXY DATASET** |
| **2. Exact Ticker / Symbol** | `^NSEI` (NSE NIFTY 50 Index on Yahoo Finance). | ⚠️ **SPOT PROXY** |
| **3. Actual Data Source** | **Yahoo Finance API (`yfinance`)**. | ⚠️ **PUBLIC REST PROXY** |
| **4. Historical Date Range** | **2023-09-20 09:15 IST to 2026-08-31 15:15 IST** (730 Calendar Days / 5,057 Bars). | ✅ **VERIFIED** |
| **5. Timeframe** | **1-Hour (`interval='1h'`)**. | ✅ **VERIFIED** |
| **6. Rollover Methodology** | Continuous spot proxy used; **no actual contract rollover / basis pricing modeled**. | ⚠️ **NO FUTURES BASIS** |
| **7. Futures vs Spot Price Source** | **Confirmed SPOT Index prices**, NOT native exchange futures contract archives. | ⚠️ **NOT NATIVE FUTURES** |
| **8. OOS Sequestration & Purity** | **100% Immutable**: Zero tuning, zero parameter search on OOS. | ✅ **STRICT PURITY** |
| **9. 81 Parameter Perturbations** | **100% In-Sample Only (IS)**: Sensitivity analysis only; no OOS selection. | ✅ **ZERO LEAKAGE** |
| **10. Look-Ahead Bias Audit** | **Zero Look-Ahead**: Signal on closed bar $t$, execution strictly on bar $t+1$ Open. | ✅ **ZERO LOOKAHEAD** |
| **11. Statutory Friction & Slippage** | Brokerage, STT (0.02%), Txn, Stamp, SEBI, GST + 0.5 pt slippage applied consistently. | ✅ **APPLIED ACCURATELY** |
| **12. Final Data Verdict** | **DATA NOT VERIFIED — DO NOT ACCEPT RESULT (FOR LIVE FUTURES DEPLOYMENT)** | 🔴 **DATA NOT VERIFIED** |

---

### Detailed Audit Findings

#### 1. Instrument & Data Source Audit
- **Exact Ticker**: `^NSEI` downloaded via `yf.download("^NSEI", period="730d", interval="1h")`.
- **Finding**: The research engine utilized the **NIFTY 50 Spot Index** as a continuous price proxy rather than individual NSE monthly futures contracts (`FUTIDX-NIFTY`).
- **Implication**: While the spot index closely mirrors the directional price action of continuous futures, it does not incorporate:
  1. **Cost of Carry / Futures Basis**: The premium/discount spread between Spot and Futures (typically +30 to +80 index points depending on interest rates and dividend season).
  2. **Rollover Execution Drag**: The actual bid-ask spread and basis friction of rolling from near-month to next-month contract on monthly expiry Thursdays.

#### 2. Temporal Partitioning & OOS Sequestration Audit
- **Full History**: 5,057 bars (2023-09-20 to 2026-08-31).
- **In-Sample Partition (70%)**: 3,539 bars (2023-09-20 09:15 to 2025-10-09 11:15).
- **Out-of-Sample Partition (30%)**: 1,518 bars (2025-10-09 12:15 to 2026-08-31 15:15).
- **Integrity Status**: **Passed**. The 30% OOS partition was never touched during hypothesis formulation or threshold definition.

#### 3. Parameter Perturbation Surface Audit (81 Sets)
- **Scope**: Evaluated Fast EMA (8, 9, 10), Slow EMA (20, 21, 22), ATR Window (12, 14, 16), and ATR-SMA Window (18, 20, 22).
- **Integrity Status**: **Passed (IS-Only)**. The 81 parameter perturbations were executed strictly on the In-Sample dataset (`df_is`). No parameter was selected from OOS, and the baseline parameters (9, 21, 14, 20) remained frozen.

#### 4. Look-Ahead Bias & Execution Timing Audit
- **Signal Logic**: Indicator calculations (`EMA_9`, `EMA_21`, `ATR_14`, `SMA_ATR_20`) reference closed bars at index $i$.
- **Execution Logic**: Position entry and exit orders are strictly executed on the `Open` price of bar $i+1$ (`open_arr[i]` where signal is `entries[i-1]`).
- **Integrity Status**: **Passed**. There is zero look-ahead bias in the execution loop.

#### 5. Statutory Costs & Slippage Audit
- Multiplier: ₹50 / point
- Lot Size: 50 (2 Lots = 100 Quantity)
- Brokerage: ₹20 / order (₹40 round-trip)
- STT (Securities Transaction Tax): 0.02% on Sell turnover
- Exchange Charges: 0.00173% on Total turnover
- Stamp Duty: 0.002% on Buy turnover
- SEBI Fee: ₹10 / crore on Total turnover
- GST: 18% on (Brokerage + Exchange + SEBI)
- Slippage: 0.5 index points per side (₹100 per round-trip trade)
- **Integrity Status**: **Passed**. Applied consistently across all backtest runs.

---

### Final Research Integrity Verdict

```text
================================================================================
FINAL RESEARCH INTEGRITY AUDIT VERDICT:
DATA NOT VERIFIED — DO NOT ACCEPT RESULT
================================================================================
```

### Required Next Step for Institutional Validation:
To transition Candidate A from a **Spot Proxy Edge** to a **Production-Grade Futures Strategy**, the entire test suite must be re-run on **native NSE historical continuous futures contract data (`FUTIDX-NIFTY`)** with explicit month-end rollover logging and basis attribution.
