# MACD_FNO_V1 DEAD-ZONE FILTER IMPACT AUDIT

**Experiment Directory:** `backtesting/experiments/exp_20261015_macd_time_filter_audit/`  
**Execution Timestamp:** 2026-10-15 11:41 IST  
**Environment:** 100% Isolated Offline Research Workspace (Read-Only Safety Preserved)  
**Safety Status:** ZERO Live Changes, ZERO Broker Orders, Production Files Untouched  

---

## 1. Executive Summary & Verification Verdict

We conducted an independent quantitative audit to investigate whether the empirical time-of-day "Dead-Zone Filter" (`is_entry_time_allowed()`) in `macdfno.py` improves risk-adjusted performance or unnecessarily suppresses profitable signals on the 1-hour timeframe.

### Core Audit Verdict:
1. **The Dead-Zone Filter is NOT an Arbitrary Churn Limiter; It Protects Against Catastrophic Decay:**  
   Completely disabling the filter (**Variant B**) causes net performance to collapse from **+70.84% down to -12.06%** in the asymmetric universe (and from **-7.72% to -222.41%** in the full 33-asset universe), while exploding Maximum Drawdown from **48.30% to 78.54%**.
2. **The 1-Hour Timeframe Phase-Shift Discrepancy (Discovery):**  
   There is a critical discrepancy between live execution and historical backtesting:
   - **Live Strategy:** Evaluates wall-clock time (`datetime.now(IST)`) at candle completion boundaries (`:15:02 IST`).
   - **Historical Backtester:** Evaluated candle start time (`ts = df.index[i]`).
   - Because a 1-hour candle completes 60 minutes after its start index, the 10:15–11:15 candle (completed at 11:15 IST) is **allowed in historical backtests** (which saw `ts = 10:15`), but **permanently blocked in live trading** (which sees clock `11:15` inside `DEAD_ZONE_11_AM`).
3. **The SUNPHARMA 11:15 IST Case Study:**  
   Across the 3-year historical dataset (300 total SUNPHARMA trades), SUNPHARMA entries at 11:15 IST had a **39.2% win rate, -8.05% net loss, and a Profit Factor of 0.828**. Blocking SUNPHARMA at 11:15 IST in live trading on 2026-10-15 prevented entry into an historically unprofitable sub-window for that specific asset.
4. **Final Recommendation:** **ADOPT A REVISED FILTER FOR FURTHER VALIDATION (Variant C1/C2)**.  
   While raw removal is destructive, realigning the morning/afternoon windows to allow 11:15 IST entries while preserving the 14:00+ European whipsaw block yields **+83.96% Net P&L** (highest absolute return), but requires strict paper-trading validation before any production deployment.

---

## 2. Implementation Inspection & Verification

Direct code verification of `strategies/scripts/macdfno.py` (lines 556, 572–600, 2163, 2281):

| Inspection Parameter | Verified Implementation Fact | Source Evidence |
| :--- | :--- | :--- |
| **1. `ENABLE_TIME_FILTER` Exists?** | **YES.** Controlled by `os.getenv("ENABLE_TIME_FILTER", "true")`. If set to `false`, `is_entry_time_allowed()` returns `(True, "FILTER_DISABLED")`. | Line 556, Line 584 |
| **2. Timezone & Comparisons** | `IST = pytz.timezone("Asia/Kolkata")`. Evaluates `m = now.hour * 60 + now.minute`. | Lines 586–587 |
| **3. Timestamp Semantics** | In live bot: evaluates **wall-clock execution time (`datetime.now(IST)`)**, NOT candle open or candle completion timestamp. In backtest scripts: evaluated `df.index[i]` (bar open). | Lines 586, 2163, 2281 |
| **4. Dead-Zone Boundaries** | Morning Window: `[09:45, 10:55]` inclusive.<br>Midday Window: `[12:00, 13:15]` inclusive.<br>Closing Window: `[15:00, 15:20]` inclusive.<br>`DEAD_ZONE_11_AM`: `[11:00, 12:00)` half-open.<br>`DEAD_ZONE_14_PM`: `[14:00, 15:00)` half-open.<br>All other times: `OUTSIDE_ALLOWED_WINDOWS`. | Lines 588–599 |
| **5. Independent Filters** | Universe Filter (`TOP_LONGS` / `TOP_SHORTS`), 50 EMA Regime Filter, and 2-Bar Histogram Expansion run alongside the time filter. | Lines 2159–2168, Lines 2277–2284 |
| **6. Constraints & Sizing** | 1 Lot per position, max 20 active concurrent positions across portfolio, +3.0% Long TP / +1.5% Short TP / -3.5% Catastrophe SL, opposite MACD cross reversal exit. | Lines 558–560, Line 2195 |

---

## 3. Controlled Variant Comparison

Evaluated across all 33 liquid NSE F&O instruments (5,039 completed 1-hour candles per asset from September 2023 to September 2026), under identical 0.07% round-trip friction and completed-candle execution:

### Table 1: Asymmetric Universe (TOP_LONGS: 7, TOP_SHORTS: 6) — Candidate G/E Baseline

| Metric | Variant A (Live Baseline) | Variant B (Filter Disabled) | Variant C1 (Realigned 1H) | Variant C2 (Midday Lull Only) | Variant Legacy (Bar-Open) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Total Trades** | **981** | **1,594** | **1,427** | **1,190** | **865** |
| **Trades / Day** | 1.34 | 2.17 | 1.95 | 1.62 | 1.18 |
| **Win Rate (%)** | **55.86%** | **49.06%** | **51.51%** | **52.61%** | **54.57%** |
| **Net P&L (%)** | **+70.84%** | **-12.06%** | **+83.96%** | **+32.07%** | **+17.67%** |
| **Profit Factor** | **1.071** | **0.992** | **1.064** | **1.027** | **1.019** |
| **Avg Win / Avg Loss** | 1.94% / 2.30% | 1.89% / 1.83% | 1.89% / 1.89% | 1.95% / 2.11% | 2.01% / 2.37% |
| **Payoff Ratio** | 0.85 | 1.03 | 1.00 | 0.93 | 0.85 |
| **Expectancy (%)** | **+0.072%** | **-0.008%** | **+0.059%** | **+0.027%** | **+0.020%** |
| **Max Drawdown (%)**| **48.30%** | **78.54%** | **58.01%** | **52.44%** | **77.84%** |
| **In-Sample PF (< Jul 2025)** | **1.076** | **0.946** | **1.022** | **1.009** | **0.954** |
| **In-Sample Net (%)** | +45.41% | -50.79% | +18.52% | +6.44% | -27.76% |
| **Out-of-Sample PF (>= Jul 2025)**| **1.064** | **1.072** | **1.136** | **1.057** | **1.136** |
| **Out-of-Sample Net (%)** | +25.43% | +38.73% | +65.44% | +25.63% | +45.43% |
| **2026 Holdout PF (>= Jan 2026)** | **1.072** | **0.974** | **1.055** | **1.027** | **0.917** |
| **2026 Holdout Net (%)** | **+17.66%** | **-9.53%** | **+17.34%** | **+7.93%** | **-20.43%** |
| **Long PF / Net (%)** | **1.181** (+103.19%) | **1.091** (+77.21%) | **1.158** (+119.50%) | **1.100** (+70.51%) | **1.210** (+107.12%) |
| **Short PF / Net (%)**| **0.924** (-32.35%) | **0.861** (-89.27%) | **0.935** (-35.55%) | **0.920** (-38.44%) | **0.789** (-89.45%) |
| **Max Concurrent Open**| 9 | 10 | 9 | 9 | 8 |

---

### Table 2: Unrestricted Common Universe (All 33 Instruments)

| Metric | Variant A (Live Baseline) | Variant B (Filter Disabled) | Variant C1 (Realigned 1H) | Variant C2 (Midday Lull Only) | Variant Legacy (Bar-Open) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Total Trades** | 5,102 | 9,288 | 8,175 | 6,801 | 4,649 |
| **Win Rate (%)** | 50.78% | 44.90% | 46.08% | 47.18% | 52.08% |
| **Net P&L (%)** | **-7.72%** | **-222.41%** | **-116.92%** | **-220.99%** | **+103.21%** |
| **Profit Factor** | **0.998** | **0.968** | **0.982** | **0.961** | **1.025** |
| **Max Drawdown (%)**| **164.75%** | **343.48%** | **280.80%** | **341.18%** | **152.24%** |
| **2026 Holdout PF** | 0.925 | 0.866 | 0.882 | 0.855 | 0.899 |

---

## 4. Signal-Rejection Audit & Time Slot Forensic

### Signal Decision Log Summary across 33 Instruments

| Variant Code | Total Signals Detected | Signals Executed | Signals Rejected | Rejected by Time Filter | Rejected by Universe Filter |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **A_LIVE_ASYM** | 10,265 | 1,184 | 9,081 | **4,265** (41.5%) | **4,816** (46.9%) |
| **B_DISABLED_ASYM**| 10,255 | 2,004 | 8,251 | **0** (0.0%) | **8,251** (80.5%) |
| **C1_REALIGNED_ASYM**| 10,257 | 1,776 | 8,481 | **1,140** (11.1%) | **7,341** (71.6%) |
| **C2_MIDDAY_ASYM** | 10,253 | 1,504 | 8,749 | **2,430** (23.7%) | **6,319** (61.6%) |

### Performance by Entry Time Slot (Unfiltered 1,594 Trades)

We analyzed the exact realized performance of trades entered at each hourly candle completion:

| Entry Time (IST) | Completed 1H Candle | Trades (N) | Win Rate (%) | Net Return (%) | Profit Factor | Long PF | Short PF | Window Quality Verdict |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **10:15** | 09:15 – 10:15 | 307 | **54.1%** | **+53.87%** | **1.209** | **1.246** | **1.149** | 🌟 **Highest Edge Window** |
| **11:15** | 10:15 – 11:15 | 287 | **50.9%** | **+22.41%** | **1.086** | **1.143** | **0.981** | ✅ **Profitable for Longs** |
| **12:15** | 11:15 – 12:15 | 219 | 46.1% | -1.84% | 0.990 | 1.164 | 0.802 | ⚠️ Neutral / Short Decay |
| **13:15** | 12:15 – 13:15 | 216 | **52.3%** | **+20.87%** | **1.115** | **1.347** | 0.888 | 🌟 **Strong Long Continuation** |
| **14:15** | 13:15 – 14:15 | 184 | 46.2% | **-21.24%** | **0.879** | 0.980 | 0.781 | ❌ **Severe Decay Window (EU Open)** |
| **15:15** | 14:15 – 15:15 | 213 | 45.1% | **-30.35%** | **0.856** | 0.854 | 0.860 | ❌ **Severe Decay Window (Squareoff)** |
| **16:15** | 15:15 – 15:30 | 168 | 44.6% | **-55.78%** | **0.733** | 0.886 | 0.554 | ❌ **Catastrophic Post-Close Noise** |

### Crucial Finding on Window Quality:
* The **Afternoon Sessions (14:15 to 16:15)** are a consistent, heavy drain across all instruments: **cumulative net loss of -107.37%**. The dead zone at 14:00–14:59 IST is **100% justified** and must NOT be removed.
* The **11:15 Entry (10:15–11:15 Candle)** is net positive overall (**PF 1.086, +22.41%**), specifically driven by Long entries (**PF 1.143**). Suppressing it entirely was an unintended artifact of applying clock-hour blocks to completed 1-hour candles.

---

## 5. SUNPHARMA Case Study Forensic

During the live run on 2026-10-15:
* At **11:15:02 IST**, a `BUY` signal fired for `SUNPHARMA27OCT26FUT` at ₹1765.20 (Trigger ₹1759.70).
* The log recorded: `⏸️ [TIME FILTER] Skipping NEW LONG for SUNPHARMA: DEAD_ZONE_11_AM`.

### Historical Evidence for SUNPHARMA:
We queried all 300 historical SUNPHARMA trades in `B_DISABLED_ASYM_ledger.csv`:

| SUNPHARMA Time Slot | Total Trades | Win Rate (%) | Net P&L (%) | Profit Factor | Status Under Variant A |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **10:15 IST** | 59 | **49.2%** | **+14.33%** | **1.467** | Allowed |
| **11:15 IST** | 51 | **39.2%** | **-8.05%** | **0.828** | **Blocked by Dead Zone** |
| **12:15 IST** | 48 | 35.4% | -9.93% | 0.722 | Allowed |
| **13:15 IST** | 38 | 44.7% | +5.86% | 1.268 | Allowed |
| **14:15 IST** | 27 | 29.6% | -12.23% | 0.518 | Blocked by Dead Zone |
| **15:15 IST** | 42 | 31.0% | -19.38% | 0.473 | Allowed |
| **16:15 IST** | 35 | 34.3% | -14.53% | 0.599 | Blocked |

**Forensic Finding:**  
While intuitively it felt like the bot "missed a trade" on SUNPHARMA, historical data demonstrates that **SUNPHARMA entries at 11:15 IST have a sub-1.0 Profit Factor (0.828) and lose -8.05% net**. The filter successfully protected capital on this specific asset.

---

## 6. Friction Sensitivity Analysis

Evaluating resilience across transaction costs (0.05% to 0.15% round-trip):

| Round-Trip Friction (%) | Variant A (Live Baseline) PF | Variant B (Disabled) PF | Variant C1 (Realigned) PF | Variant C2 (Midday Lull) PF |
| :---: | :---: | :---: | :---: | :---: |
| **0.05%** | **1.092** (+90.46%) | 1.013 (+19.82%) | **1.087** (+112.50%) | 1.047 (+55.87%) |
| **0.07%** | **1.071** (+70.84%) | 0.992 (-12.06%) | **1.064** (+83.96%) | 1.027 (+32.07%) |
| **0.10%** | **1.041** (+41.41%) | 0.960 (-59.88%) | **1.031** (+41.15%) | 0.997 (-3.63%) |
| **0.12%** | **1.021** (+21.79%) | 0.940 (-91.76%) | **1.009** (+12.61%) | 0.977 (-27.43%) |
| **0.15%** | **0.993** (-7.64%) | 0.910 (-139.58%) | **0.978** (-30.20%) | 0.949 (-63.13%) |

**Finding:**
* **Variant A** and **Variant C1** maintain edge up to **0.12% round-trip friction**.
* **Variant B** fails immediately above 0.05% friction, bleeding into deep negative returns.

---

## 7. Artifact Manifest & Reproducible Commands

All audit ledgers, signal logs, and matrices have been generated and preserved in:
`backtesting/experiments/exp_20261015_macd_time_filter_audit/`

### Preserved Files:
1. `ledgers/A_LIVE_ASYM_ledger.csv` — Full 981-trade ledger for Variant A.
2. `ledgers/B_DISABLED_ASYM_ledger.csv` — Full 1,594-trade ledger for Variant B.
3. `ledgers/C1_REALIGNED_ASYM_ledger.csv` — Full 1,427-trade ledger for Variant C1.
4. `ledgers/C2_MIDDAY_ASYM_ledger.csv` — Full 1,190-trade ledger for Variant C2.
5. `A_LIVE_ASYM_signals.csv` — 10,265 signal decision records with filter rejection reasons.
6. `master_variant_summary.csv` — Consolidated comparative matrix.
7. `signal_rejection_audit_summary.csv` — Rejection taxonomy summary.
8. `friction_sensitivity_matrix.csv` — Stress test from 0.05% to 0.15%.

### Reproducible Run Command:
```bash
python3 backtesting/experiments/exp_20261015_macd_time_filter_audit/run_time_filter_audit.py
```

---

## 8. Final Decision & Recommendation

### Classification:
**ADOPT A REVISED FILTER FOR FURTHER VALIDATION (Variant C1/C2)**

### Detailed Rationale:
1. **Do NOT disable the filter (Reject Variant B):**  
   Disabling the dead zone increases trade frequency (+62.5%), but destroys the system's edge: Net P&L drops from **+70.84% to -12.06%**, Profit Factor falls below 1.0 (**0.992**), and Drawdown spikes to **78.54%**. The afternoon hours (14:00–16:15) are mathematically toxic for 1H MACD entries.
2. **The Case for Realignment (Variant C1):**  
   Allowing 11:15 IST entries increases net profit from **+70.84% to +83.96%** (+18.5% dollar gain) while preserving a robust **1.064 Profit Factor** and healthy Holdout performance (**1.055 PF in 2026**).
3. **Operational Guardrail:**  
   In compliance with AGY safety boundaries, **zero modifications were made to live strategy files**. Before any change to production `macdfno.py` is made, Variant C1 should be forward paper-traded in OpenAlgo Analyze mode to confirm live execution mechanics.
