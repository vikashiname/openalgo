# PHASE E2 — FORWARD PAPER VALIDATION & EXIT MODEL OBSERVATION REPORT

**Date / Timestamp:** 2026-09-02 16:52:45 IST  
**Mode:** **100% READ-ONLY OBSERVATION / FORWARD TRACKING**  
**Environment:** OpenAlgo Analyze Mode / Paper Trading  
**Locked Entry Logic:** MACD (12, 26, 9) Crossover + 2-Bar Histogram Expansion on 1H Completed Candles  
**Frozen Baseline Checksum:** `312c25b8f882bdb2549ebc08a08ed88cd19f3a1989f6a986b6b98171a059c832`  

---

## 1. Frozen Historical Baseline Record

| Parameter | Frozen Value |
| :--- | :--- |
| **Strategy File** | `/Users/mac/Desktop/openalgo/strategies/liveonopenalgo/macdfno.py` |
| **SHA-256 Checksum** | `312c25b8f882bdb2549ebc08a08ed88cd19f3a1989f6a986b6b98171a059c832` |
| **File Size** | `67,267 bytes` |
| **Historical Period** | `2023-09-22 09:15:00 IST` to `2026-09-02 15:15:00 IST` (717 Days) |
| **Universe** | 15 Core Liquid NFO Derivatives Underlyings |
| **Frozen Historical Trade Count** | **4,007 Trades** |
| **Historical Candidate Setup** | **Take Profit: `+1.50%` \| Stop Loss: `-1.50%` \| Break-Even: `DISABLED`** |
| **Historical Win Rate Expectation**| **56.4%** (Profit Factor: **1.34**, Expectancy: **+0.284% / trade**) |

> [!NOTE]
> **Trade Count Reconciliation Note:** The preliminary exploratory run logged 4,006 trades using data up to 14:15 IST. Upon receiving the final 15:15 candle bar on 2026-09-02, 1 additional completed trade on ULTRACEMCO was closed, establishing the definitive frozen historical baseline at **4,007 trades**.

---

## 2. Forward Paper Trading Observation Summary (Live Forward Sample)

| Metric | Forward Observed Value | Historical Benchmark Expectation |
| :--- | :---: | :---: |
| **Total Forward Observed Trades** | **8** | N/A (Live Sample Accumulating) |
| **LONG Signals / SHORT Signals** | **8 LONG / 0 SHORT** | ~50% / 50% |
| **Target (+1.50%) Hit Rate** | **37.5% (3 Trades)** | **47.1% – 51.3%** |
| **Stop Loss (-1.50%) Hit Rate** | **12.5% (1 Trades)** | **24.4% – 27.5%** |
| **MACD Reversal Exits** | **2 Trades** | ~25.4% |
| **Ambiguous Bars (Both touched)**| **0 Trades (0.0%)** | <0.5% |
| **Still Open in Forward Track** | **2 Trades** | Dynamic |
| **Average MFE (%)** | **+9.05%** | **+2.38%** |
| **Median MFE (%)** | **+0.50%** | **+1.57%** |
| **Average MAE (%)** | **-2.89%** | **-1.30%** |
| **Median MAE (%)** | **-0.36%** | **-1.01%** |
| **Model A Cumulative P&L** | **₹+4,126.50** | Baseline (Reversal only) |
| **Model B Cumulative P&L** | **₹+14,541.12** | Proposed Candidate (+1.50% / -1.50%) |
| **Net Difference (Model B - Model A)** | **₹+10,414.62** | Target Monetization Alpha |

---

## 3. Individual Forward Trade Audit (20-Field Path Breakdown)

| Symbol | Contract | Dir | Entry Time | Entry Price | MFE (%) | MAE (%) | First Event | Model A PnL | Model B PnL | PnL Diff | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BAJFINANCE** | `BAJFINANCE29SEP26FUT` | LONG | 2026-09-02 14:16:00+05:30 | ₹1,064.10 | +0.0% | -0.31% | **STILL_OPEN** | ₹-2,250.00 | ₹-2,250.00 | ₹+0.00 | STILL_OPEN |
| **ADANIENT** | `ADANIENT29SEP26FUT` | LONG | 2026-09-02 14:16:00+05:30 | ₹2,911.10 | +0.0% | -0.42% | **STILL_OPEN** | ₹-2,781.00 | ₹-2,781.00 | ₹+0.00 | STILL_OPEN |
| **M&M** | `M&M29SEP26FUT` | LONG | 2026-09-02 09:16:00+05:30 | ₹3,192.15 | +0.82% | -1.15% | **MACD_REVERSAL** | ₹-2,030.00 | ₹-2,030.00 | ₹+0.00 | MACD_REVERSAL |
| **EICHERMOT** | `EICHERMOT29SEP26FUT` | LONG | 2026-09-02 09:16:00+05:30 | ₹4,911.00 | +57.27% | -0.0% | **TP** | ₹+800.00 | ₹+7,366.50 | ₹+6,566.50 | TARGET |
| **BHARTIARTL** | `BHARTIARTL29SEP26FUT` | LONG | 2026-09-02 09:16:00+05:30 | ₹1,878.00 | +0.18% | -0.8% | **MACD_REVERSAL** | ₹+4,750.00 | ₹+4,750.00 | ₹+0.00 | MACD_REVERSAL |
| **ASIANPAINT** | `ASIANPAINT29SEP26FUT` | LONG | 2026-09-02 09:16:00+05:30 | ₹2,478.00 | +2.76% | -0.0% | **TP** | ₹+3,137.50 | ₹+9,292.50 | ₹+6,155.00 | TARGET |
| **NTPC** | `NTPC29SEP26FUT` | LONG | 2026-09-02 09:16:00+05:30 | ₹412.00 | +0.0% | -20.46% | **SL** | ₹+3,375.00 | ₹-9,270.00 | ₹-12,645.00 | SL |
| **LT** | `LT29SEP26FUT` | LONG | 2026-09-02 09:16:00+05:30 | ₹3,605.00 | +11.4% | -0.0% | **TP** | ₹-875.00 | ₹+9,463.12 | ₹+10,338.12 | TARGET |


---

## 4. Methodology & Ambiguity Handling

1. **Path-Dependent Sequential Evaluation:**
   * High and Low excursions are evaluated chronologically on completed 1H bars.
   * If `High >= Entry * 1.015` occurs before `Low <= Entry * 0.985`, trade is marked `TP`.
   * If `Low <= Entry * 0.985` occurs before `High >= Entry * 1.015`, trade is marked `SL`.
2. **Ambiguity Rule:**
   * If both $+1.50\%$ and $-1.50\%$ are touched within the exact same 1H bar, it is flagged `AMBIGUOUS`.
   * P&L is recorded as `0.00%` with zero assumption of TP or SL priority until tick-level data confirms sequence.
3. **Reversal Fallback:**
   * If neither TP nor SL is touched, the position exits when an opposite 1H MACD crossover bar closes.

---

## 5. Artifacts Generated & Preserved

1. `backtesting/reports/macdfno_baseline_freeze.json` — Immutable baseline configuration and checksum.
2. `backtesting/reports/macdfno_forward_state.json` — Persistent forward tracking state.
3. `backtesting/reports/macdfno_forward_validation.csv` — Full 20-column machine-readable validation dataset.
4. `backtesting/reports/macdfno_forward_daily_report.md` — Live daily update markdown report.

* ❌ **ZERO changes made to `macdfno.py`.**
* ❌ **ZERO orders placed.**
* ❌ **ZERO positions modified in OpenAlgo.**
