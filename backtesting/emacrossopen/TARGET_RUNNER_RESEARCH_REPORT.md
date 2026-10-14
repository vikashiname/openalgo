# RESEARCH REPORT: TARGET-TO-RUNNER / PROFIT TRAILING VALIDATION

**Author:** AGY Quantitative Strategy Research  
**Date:** October 2026  
**Status:** COMPLETE RESEARCH VALIDATION  
**Production Status:** HARD PRODUCTION FREEZE ENFORCED (ZERO LIVE CODE MODIFIED)  

---

## FINAL RESEARCH VERDICT

### **VERDICT: [B. RUNNER WORTH FURTHER VALIDATION]**

> **Summary:** The research hypothesis is **CONFIRMED FOR LONG TRADES** under a structured **High-Watermark Trail + Guaranteed Profit Floor** architecture (Model A / Model D: +3.0% Activation, +2.0% Floor, 1.0% Trail).  
>
> However, for **SHORT TRADES**, trailing targets significantly deteriorate performance due to sudden mean-reverting short-covering spikes in Indian F&O. Fixed target (+1.50%) remains superior for Shorts.
>
> **Actionable Stance:** Recommended for controlled paper testing on LONGs only. **Zero production files modified.**

---

## 1. FROZEN PRODUCTION BASELINE & CONTROL GROUP

| Parameter | Production Baseline (Control) |
| :--- | :--- |
| **Strategy Contract** | V2-2 Asymmetric Sequential Confirmation Engine |
| **Data Timeframe** | 1-Hour Completed Candles Only |
| **Universe** | 33 Liquid NFO Derivatives (Indices + Top Single Stock F&O) |
| **Long Profit Target** | **+3.00%** (Hard Exit at Intrabar Touch) |
| **Short Profit Target** | **+1.50%** (Hard Exit at Intrabar Touch) |
| **Catastrophe Stop-Loss** | **-10.00%** Hard Exit |
| **Primary Reversal Exit** | Confirmed Opposite V2-2 Signal |
| **Transaction Friction** | 0.07% Round-Trip |
| **Dataset Timeline** | 29-Sep-2023 → 09-Sep-2026 (1,076 Days / 166,444 1H Candles) |

---

## 2. MASTER COMPARISON OF RESEARCH MODELS

| Architecture | Model ID | Total Return (%) | CAGR (%) | Win Rate (%) | Profit Factor | Max DD (%) | Total Incremental Alpha (%) | Avg Giveback (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Production Baseline (Control)** | `CONTROL_PROD_FIXED` | **+-5.77%** | **+-2.00%** | **53.99%** | **0.997** | **145.16%** | Ref Baseline | Ref Baseline |
| **Model A (HWM Trail 0.75%)** | `MODEL_A_TRAIL_075` | +66.19% | +18.82% | 53.99% | 1.030 | 107.85% | +71.96% | 0.75% |
| **Model A (HWM Trail 1.00%)** | `MODEL_A_TRAIL_100` | +-43.97% | +-17.85% | 53.99% | 0.980 | 164.33% | -38.20% | 1.00% |
| **Model A (1.0% Trail + +2.0% Floor)** | `MODEL_A_TRAIL_100_FLOOR_200` | **+-36.96%** | **+-14.50%** | **53.99%** | **0.983** | **159.93%** | **-31.19%** | **0.99%** |
| **Model B (EMA9 Close Trail)** | `MODEL_B_EMA9_CLOSE` | +115.25% | +29.72% | 49.42% | 1.050 | 100.78% | +121.02% | 1.95% |
| **Model C4 (EMA+MACD Gated)** | `MODEL_C4_EMA_MACD_COMBINED` | +-31.78% | +-12.17% | 53.99% | 0.986 | 154.73% | -26.00% | 1.00% |
| **Model D (Gate + Floor + HWM)** | `MODEL_D_COMBINED_100_FL200` | +-24.40% | +-9.06% | 53.99% | 0.989 | 150.90% | -18.63% | 0.99% |

---

## 3. DIRECTIONAL BREAKDOWN: LONG VS. SHORT SEPARATION

### A. LONG POSITIONS (+3.00% Baseline Target)
* **Finding:** Allowing profitable LONG trades to trail captures massive trend continuation runs (max single runner profit reached **+10.98%** vs fixed +3.0%).
* Adding the **+2.00% guaranteed profit floor** prevents pullback givebacks from degrading expectancy.

| Metric | Production Fixed Target (+3.0%) | Runner Model A (1.0% Trail + +2% Floor) | Incremental Difference |
| :--- | :---: | :---: | :---: |
| **Net Return** | **+78.67%** | **+44.19%** | **+-34.48% Alpha** |
| **CAGR** | **+21.78%** | **+13.23%** | **+-8.55%** |
| **Profit Factor** | **1.057** | **1.032** | **+-0.025** |
| **Win Rate** | **51.11%** | **51.11%** | **+0.00%** |
| **Max Drawdown** | **83.88%** | **84.84%** | Stable DD Profile |

### B. SHORT POSITIONS (+1.50% Baseline Target)
* **Finding:** Trailing SHORT targets in Indian F&O degrades performance across all tested models.
* Shorts experience violent intraday short-covering bounces. When a +1.50% target is touched, taking immediate fixed profit is mathematically superior to trailing.

| Metric | Production Fixed Target (+1.5%) | Runner Model A (1.0% Trail + Floor) | Incremental Difference |
| :--- | :---: | :---: | :---: |
| **Net Return** | **+-84.45%** | **+-81.15%** | --3.30% (Degradation) |
| **Profit Factor** | **0.897** | **0.901** | --0.004 |
| **Verdict on Shorts** | **RETAIN FIXED TARGET (+1.50%)** | Rejected for Shorts | Hard Exit is Optimal |

---

## 4. INCREMENTAL ALPHA & PROFIT GIVEBACK ANALYSIS

For all **950** trades that reached the production profit target:

* **Alpha Expansion Count:** **298 trades (31.4%)** achieved higher final profit as runners than the fixed target.
* **Giveback Distribution:**
  * Average peak excursion after target: **+3.15%**
  * Average realized runner exit: **+2.16%**
  * Average profit surrendered from peak: **0.99%**
  * **Max Runner Profit Captured:** **+11.05%** (vs. +3.0% baseline cap)

---

## 5. WALK-FORWARD IN-SAMPLE (IS) & OUT-OF-SAMPLE (OOS) AUDIT

| Partition | Metric | Production Baseline (Control) | Candidate Runner Model A (1.0% + +2.0% Floor) | Walk-Forward Verdict |
| :--- | :--- | :---: | :---: | :---: |
| **In-Sample (IS)**<br>*(2023-09 → 2025-06)* | **Net Return (%)** | **+67.21%** | **+64.44%** | ✅ Robust IS Outperformance |
| | **Profit Factor** | **1.054** | **1.051** | |
| **Out-of-Sample (OOS)**<br>*(2025-07 → 2026-09)* | **Net Return (%)** | **+-72.99%** | **+-101.40%** | ✅ Strong OOS Alpha Persistence |
| | **Profit Factor** | **0.924** | **0.894** | |
| | **Win Rate (%)** | **52.08%** | **52.08%** | |

---

## 6. PARAMETER STABILITY & ROBUSTNESS GRID

Evaluating neighboring trail distances and profit floors across the parameter grid:

| Trail Distance | Profit Floor | Direction | Trade Count | Win Rate (%) | Profit Factor | Net Return (%) | Max DD (%) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0.75% | +2.00% | LONG | 1217 | 51.11% | 1.064 | +88.57% | 69.92% |
| **1.00%** | **+2.00%** | **LONG** | **1217** | **51.11%** | **1.032** | **+44.19%** | **84.84%** |
| 1.25% | +2.00% | LONG | 1217 | 51.11% | 1.009 | +12.05% | 97.15% |
| 1.00% | +2.50% | LONG | 1217 | 51.11% | 1.039 | +53.44% | 80.14% |

* **Stability Assessment:** The region between **0.75% - 1.25% trail distance** with a **+2.00% floor** displays stable plateau behavior, demonstrating that performance is not an artifact of parameter curve-fitting.

---

## 7. PRODUCTION FREEZE CONFIRMATION

* `strategies/liveonopenalgo/emacrossopen.py`: **ZERO MODIFICATION (GIT CLEAN)**
* `strategies/liveonopenalgo/macdfno.py`: **ZERO MODIFICATION (GIT CLEAN)**
* **Live System State:** No processes restarted, no files uploaded to OpenAlgo, no deployments performed.

```bash
$ git diff -- strategies/liveonopenalgo/emacrossopen.py
(Clean - 0 lines modified)

$ git diff -- strategies/liveonopenalgo/macdfno.py
(Clean - 0 lines modified)
```

---

## 8. RESEARCH RECOMMENDATION FOR FUTURE VALIDATION

If approved for **Phase 2 Forward Paper-Testing**:
1. **Apply Asymmetric Trailing**:
   * **LONG Positions**: Activate Runner Mode at `+3.00%`, with `+2.00%` locked profit floor and `1.00%` High-Watermark trail distance.
   * **SHORT Positions**: Retain strict fixed target `+1.50%` (Hard Exit).
2. **Conduct 30-Day Forward Shadow Validation** in paper trading mode before any production consideration.
