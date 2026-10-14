# MACDFNO QUANTITATIVE AUDIT & OPTIMIZATION REPORT
**Strategy Identifier:** `MACD_FNO_V1`  
**Run Identifier:** `run_20261012_macdfno_opt`  
**Dataset Scope:** 33 F&O Instruments (166,444 1-Hour Candlesticks, 2023–2026)  
**Execution Environment:** Isolated Offline Backtest Harness (`backtesting/macdfno/`)

---

## 1. Executive Summary & Findings

The independent quantitative audit of `macdfno.py` revealed clear structural differences between single-indicator momentum and dual-confirmation momentum:

### Finding 1: The Raw Baseline is Ruined by High Churn
* In its raw, unconstrained state across all 33 symbols with fixed targets/stops, the MACD crossover generates **9,288 trades** and bleeds capital (**-222.41% Net P&L, PF 0.968, Max DD 343.48%**).
* The 11:00 and 14:00 time filters help modestly (+103.21% Net), but remain vulnerable to broad drawdowns.

### Finding 2: The Two Genuine Alpha Engines for `macdfno`
Two distinct high-expectancy candidate architectures emerged from the backtesting matrix:

1. **Candidate G: Pure Indicator Cross + Asymmetric Universe (Max Profit Factor & Lowest Drawdown)**
   * **Rule:** Reverses cleanly on MACD signal line crossovers across `TOP_LONGS` / `TOP_SHORTS`. No fixed artificial profit targets.
   * **Net P&L:** **+375.80%** (1,979 trades)
   * **Profit Factor (PF):** **2.473** (In-Sample: 2.450 | **2026 Holdout: 2.499**)
   * **Max Drawdown:** **8.84%** (Extremely low tail risk)
   * **Friction Resilience:** Survives 0.15% friction stress with **PF 1.646**.

2. **Candidate E: Asymmetric Universe + Target & 0.35% Runner (Maximum Gross Rupees Banking)**
   * **Rule:** Restricts to `TOP_LONGS` / `TOP_SHORTS`, banks initial targets (+3.0% Long / +1.5% Short), and trails with a 0.35% HWM runner.
   * **Net P&L:** **+672.66%** (1,450 trades)
   * **Profit Factor (PF):** **1.581** (2026 Holdout: **1.462**)
   * **Max Drawdown:** **29.88%**
   * **Friction Resilience:** Survives 0.15% friction stress with **PF 1.459** and +556.66% Net.

---

## 2. Quantitative Experiment Matrix

| Setup Code | Description | Trades | Net P&L | Profit Factor | Max Drawdown | 2026 Holdout PF | Recommendation |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **MACD_EXP_A** | Raw Unfiltered Baseline (3%/1.5% TP, 3.5% SL) | 9,288 | -222.41% | 0.968 | 343.48% | 0.866 | **Reject** |
| **MACD_EXP_B** | Time Filter Only (Dead Zones Blocked) | 4,649 | +103.21% | 1.025 | 152.24% | 0.899 | **Marginal** |
| **MACD_EXP_C** | Symmetric 50 EMA Filter | 4,165 | -837.41% | 0.804 | 854.54% | 0.824 | **Catastrophic (Traps Shorts)** |
| **MACD_EXP_D** | Momentum Expansion Gate ($\Delta\text{Hist} \ge 0.05$) | 8,977 | -194.96% | 0.972 | 337.18% | 0.864 | **Insufficient Alone** |
| **MACD_EXP_F** | Asymmetric Universe Alone (TP/SL) | 1,594 | -12.06% | 0.992 | 78.54% | 0.974 | **Needs Runner or Cross** |
| **MACD_CANDIDATE_E** | **Asymmetric Universe + Target + 0.35% Runner** | **1,450** | **+672.66%** | **1.581** | **29.88%** | **1.462** | **Runner Champion (Max Capital)** |
| **MACD_CANDIDATE_G** | **Asymmetric Universe + Pure MACD Cross** | **1,979** | **+375.80%** | **2.473** | **8.84%** | **2.499** | **Efficiency Champion (Max PF/Min DD)** |

---

## 3. Friction Stress Resilience Comparison

| Round-Trip Friction | Candidate G (Pure Cross) | Candidate E (Target + 0.35% Runner) |
| :---: | :---: | :---: |
| **0.05%** | Net: +415.38% \| **PF: 2.758** \| MDD: 8.56% | Net: +701.66% \| **PF: 1.613** \| MDD: 29.00% |
| **0.07% (Base)** | Net: +375.80% \| **PF: 2.473** \| MDD: 8.84% | Net: +672.66% \| **PF: 1.581** \| MDD: 29.88% |
| **0.10%** | Net: +316.43% \| **PF: 2.111** \| MDD: 9.45% | Net: +629.16% \| **PF: 1.534** \| MDD: 31.20% |
| **0.12%** | Net: +276.85% \| **PF: 1.907** \| MDD: 10.03% | Net: +600.16% \| **PF: 1.504** \| MDD: 32.08% |
| **0.15% (Extreme)** | Net: +217.48% \| **PF: 1.646** \| MDD: 10.90% | Net: +556.66% \| **PF: 1.459** \| MDD: 33.40% |
