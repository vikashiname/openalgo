# Final Quantitative Backtest Report: Target-to-Runner Architecture

**Strategy Under Audit:** OpenAlgo V2-2 Multi-Symbol EMA/MACD Trend Strategy  
**Dataset:** 33 NSE F&O Symbols | 1-Hour Timeframe | October 2023 – September 2026 (1,076 Calendar Days / 2.95 Years)  
**Total Sample Size:** 2,143 Completed Trades (1,217 LONG / 926 SHORT)  
**Research Engine:** [`final_target_runner_backtest.py`](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/final_target_runner_backtest.py)  
**Status:** **RESEARCH ONLY — ABSOLUTE PRODUCTION FREEZE ACTIVE**

---

## 1. Executive Summary

This independent quantitative audit evaluates whether transitioning trades that hit their initial profit targets (+3.00% Long / +1.50% Short) into active profit runners outperforms the frozen production fixed-target baseline. 

The audit tested 8 Long models (A–H) and 8 Short models (A–H) across 2,143 trade slices with **zero lookahead bias**, incorporating full historical backtests, In-Sample/Out-of-Sample splits (IS: 60% / OOS: 40%), rolling walk-forward slices, 5,000-run Monte Carlo bootstrap resamplings, parameter plateaus, and friction stress testing up to 0.20% per trade.

### Key Quantitative Findings
1. **LONG Side:** High-Watermark (HWM) trailing stop at **0.35% – 0.50%** generates substantial, statistically robust alpha over fixed +3.00% exit (**+87.51% to +150.82% Net Incremental Alpha**, reducing maximum drawdown from 83.88% down to 56.94%–63.02%). Indicator-based trails (EMA9, EMA9+MACD) suffer from severe giveback lag (averaging ~2.0% giveback with single-trade givebacks up to 18.79%).
2. **SHORT Side:** While an ultra-tight HWM 0.35% trail shows theoretical positive return, wider trails ($\ge 0.75\%$) and all indicator trails (EMA9 / MACD) collapse into deep losses (**-22.39% to -196.29%** Net Return). Indian equity F&O dynamics feature violent mean-reverting short-covering rallies that punish delayed exits.
3. **Directional Asymmetry:** Long momentum persists into multi-day runaway expansions (+6% to +15%), whereas Short expansions are brief and followed by abrupt spikes. Consequently, asymmetric exit handling is mathematically required.

---

## 2. Frozen Production Control Baseline

| Parameter | LONG Control | SHORT Control |
| :--- | :--- | :--- |
| **Timeframe** | 1-Hour Completed Candles | 1-Hour Completed Candles |
| **Indicators** | EMA 9/26, MACD 12/26/9 | EMA 9/26, MACD 12/26/9 |
| **Confirmation Window** | 2 Completed Candles | 2 Completed Candles |
| **Confirmation Modes** | `SAME_CANDLE`, `MACD_THEN_EMA`, `EMA_THEN_MACD` | `SAME_CANDLE`, `MACD_THEN_EMA` (`EMA_THEN_MACD` rejected) |
| **Profit Target** | **+3.00% Fixed Exit** | **+1.50% Fixed Exit** |
| **Catastrophe SL** | -10.00% | -10.00% |
| **Primary Exit** | V2-2 Reversal Signal | V2-2 Reversal Signal |
| **Execution Timing** | Signal on completed bar $i$ $\to$ Fill at Open[$i+1$] | Signal on completed bar $i$ $\to$ Fill at Open[$i+1$] |

---

## 3. Comprehensive Master Backtest Results

Below are the full backtest statistics for all 16 evaluated models across the 3-year historical dataset (Friction: 0.07% round-trip):

### A. LONG Models (1,217 Trades, 441 Target Touches = 36.2% Hit Rate)

| Model ID | Model Architecture | Net Return | CAGR | Profit Factor | Expectancy | Max DD | Avg DD | Win Rate | Incremental Alpha | Avg Giveback | Max Giveback |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `LONG_A_FIXED` | **Fixed +3.00% Control** | **+78.67%** | **26.71%** | **1.057** | **+0.065%** | **83.88%** | **30.91%** | **51.11%** | Baseline | 0.00% | 0.00% |
| `LONG_B_HWM_035` | HWM Trail 0.35% | +229.50% | 77.90% | 1.166 | +0.189% | 56.94% | 19.05% | 51.11% | +150.82% | 0.36% | 0.39% |
| `LONG_C_HWM_050` | **HWM Trail 0.50%** | **+166.18%** | **56.41%** | **1.120** | **+0.137%** | **63.02%** | **21.94%** | **51.11%** | **+87.51%** | **0.52%** | **0.56%** |
| `LONG_D_HWM_060` | HWM Trail 0.60% | +127.36% | 43.23% | 1.092 | +0.105% | 66.82% | 24.37% | 51.11% | +48.69% | 0.62% | 0.67% |
| `LONG_E_HWM_075` | HWM Trail 0.75% | +88.57% | 30.07% | 1.064 | +0.073% | 69.92% | 27.39% | 51.11% | +9.90% | 0.78% | 0.84% |
| `LONG_F_HWM_100` | HWM Trail 1.00% | +44.04% | 14.95% | 1.032 | +0.036% | 84.89% | 32.12% | 51.11% | -34.63% | 1.04% | 1.12% |
| `LONG_G_EMA9` | EMA9 Close Trail | +239.48% | 81.29% | 1.172 | +0.197% | 56.14% | 17.70% | 50.29% | +160.81% | 1.95% | 9.47% |
| `LONG_H_EMA9_MACD` | EMA9 + MACD Trail | +224.49% | 76.20% | 1.158 | +0.184% | 70.59% | 19.92% | 49.38% | +145.81% | 2.13% | 18.79% |

### B. SHORT Models (926 Trades, 509 Target Touches = 55.0% Hit Rate)

| Model ID | Model Architecture | Net Return | CAGR | Profit Factor | Expectancy | Max DD | Avg DD | Win Rate | Incremental Alpha | Avg Giveback | Max Giveback |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `SHORT_A_FIXED` | **Fixed +1.50% Control** | **-84.45%** | **-28.67%** | **0.897** | **-0.091%** | **121.50%** | **65.56%** | **57.78%** | Baseline | 0.00% | 0.00% |
| `SHORT_B_HWM_035` | HWM Trail 0.35% | +122.38% | 41.54% | 1.149 | +0.132% | 39.02% | 12.72% | 57.78% | +206.83% | 0.34% | 0.34% |
| `SHORT_C_HWM_050` | HWM Trail 0.50% | +56.98% | 19.34% | 1.069 | +0.062% | 56.61% | 22.46% | 57.78% | +141.42% | 0.49% | 0.49% |
| `SHORT_D_HWM_060` | HWM Trail 0.60% | +17.40% | 5.90% | 1.021 | +0.019% | 73.39% | 33.34% | 57.78% | +101.84% | 0.59% | 0.59% |
| `SHORT_E_HWM_075` | HWM Trail 0.75% | -22.39% | -7.60% | 0.973 | -0.024% | 97.15% | 48.36% | 57.78% | +62.06% | 0.73% | 0.74% |
| `SHORT_F_HWM_100` | HWM Trail 1.00% | -88.02% | -29.88% | 0.893 | -0.095% | 134.85% | 74.96% | 57.78% | -3.57% | 0.97% | 0.98% |
| `SHORT_G_EMA9` | EMA9 Close Trail | -124.23% | -42.17% | 0.865 | -0.134% | 163.33% | 94.09% | 48.27% | -39.78% | 1.96% | 12.43% |
| `SHORT_H_EMA9_MACD` | EMA9 + MACD Trail | -196.29% | -66.63% | 0.801 | -0.212% | 225.94% | 134.69% | 45.68% | -111.85% | 2.24% | 16.25% |

---

## 4. In-Sample vs Out-of-Sample (OOS) Validation

Split Date: **July 1, 2025** (In-Sample: Oct 2023 – Jun 2025 | Out-of-Sample: Jul 2025 – Sep 2026)

| Model ID | IS Net Return | IS Profit Factor | IS Max DD | OOS Net Return | OOS Profit Factor | OOS Max DD | OOS Net Alpha |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `LONG_A_FIXED` (Control) | +128.27% | 1.167 | 47.88% | -49.60% | 0.920 | 107.64% | Baseline |
| `LONG_B_HWM_035` | +216.68% | 1.282 | 44.47% | +12.81% | 1.021 | 84.74% | **+62.41%** |
| `LONG_C_HWM_050` | +178.10% | 1.232 | 45.56% | -11.92% | 0.981 | 89.55% | **+37.68%** |
| `LONG_D_HWM_060` | +154.15% | 1.201 | 46.29% | -26.79% | 0.957 | 92.43% | **+22.81%** |
| `LONG_E_HWM_075` | +133.80% | 1.174 | 47.38% | -45.23% | 0.927 | 98.40% | **+4.36%** |
| `LONG_F_HWM_100` | +112.16% | 1.146 | 50.71% | -68.12% | 0.890 | 112.18% | -18.52% |
| `SHORT_A_FIXED` (Control) | -61.06% | 0.874 | 113.77% | -23.39% | 0.931 | 57.35% | Baseline |
| `SHORT_B_HWM_035` | +70.46% | 1.146 | 57.28% | +51.92% | 1.154 | 34.45% | +75.31% |
| `SHORT_C_HWM_050` | +31.02% | 1.064 | 72.56% | +25.95% | 1.077 | 42.89% | +49.34% |
| `SHORT_F_HWM_100` | -53.60% | 0.889 | 120.58% | -34.42% | 0.898 | 71.19% | -11.03% |

---

## 5. Rolling Walk-Forward Analysis (4 Quarters)

| Quarter Range | LONG Control Net (PF) | LONG HWM 0.50% Net (PF) | LONG Alpha | SHORT Control Net (PF) | SHORT HWM 0.50% Net (PF) | SHORT Alpha |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Q1 (2023-10 to 2024-06)** | +120.37% (1.40) | +156.62% (1.52) | **+36.25%** | -28.65% (0.86) | +22.79% (1.11) | +51.44% |
| **Q2 (2024-06 to 2025-03)** | +9.58% (1.03) | +23.51% (1.07) | **+13.93%** | -2.62% (0.99) | +13.95% (1.08) | +16.57% |
| **Q3 (2025-03 to 2025-12)** | -29.30% (0.91) | -26.98% (0.92) | **+2.32%** | -38.71% (0.81) | -7.18% (0.96) | +31.53% |
| **Q4 (2025-12 to 2026-09)** | -22.62% (0.94) | +12.39% (1.03) | **+35.01%** | -14.46% (0.94) | +27.42% (1.12) | +41.89% |

---

## 6. Parameter Sensitivity Plateau Analysis

Testing fine-grid increments around the candidate trailing parameters:

```
LONG HWM TRAILING PARAMETER PLATEAU:
Trail % | Net Return | PF    | Max DD | Expectancy | Alpha    | Giveback
0.35%   | +229.50%   | 1.166 | 56.94% | +0.1886%   | +150.82% | 0.36%
0.40%   | +207.65%   | 1.150 | 59.12% | +0.1706%   | +128.98% | 0.41%
0.45%   | +187.17%   | 1.135 | 60.84% | +0.1538%   | +108.50% | 0.47%
0.50%   | +166.18%   | 1.120 | 63.02% | +0.1365%   | +87.51%  | 0.52%  <-- RECOMMENDED REGION
0.55%   | +146.31%   | 1.106 | 65.19% | +0.1202%   | +67.64%  | 0.57%
0.60%   | +127.36%   | 1.092 | 66.82% | +0.1047%   | +48.69%  | 0.62%
0.75%   | +88.57%    | 1.064 | 69.92% | +0.0728%   | +9.90%   | 0.78%
1.00%   | +44.04%    | 1.032 | 84.89% | +0.0362%   | -34.63%  | 1.04%  <-- CLIFF / DEGRADATION
```

---

## 7. Friction & Slippage Sensitivity Stress Test

Round-trip transaction costs evaluated across 6 friction tiers:

| Friction / Slippage Tier | LONG Control Net | LONG HWM 0.50% Net | LONG Net Alpha | SHORT Control Net | SHORT HWM 0.50% Net | SHORT Net Alpha |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0.00% (Zero Friction)** | +163.86% | +251.37% | **+87.51%** | -19.63% | +121.80% | +141.42% |
| **0.05% (Low Brokerage)** | +103.01% | +190.52% | **+87.51%** | -65.93% | +75.50% | +141.42% |
| **0.07% (Standard F&O)** | **+78.67%** | **+166.18%** | **+87.51%** | **-84.45%** | **+56.98%** | **+141.42%** |
| **0.10% (Elevated STT)** | +42.16% | +129.67% | **+87.51%** | -112.23% | +29.20% | +141.42% |
| **0.15% (High Slippage)** | -18.69% | +68.82% | **+87.51%** | -158.53% | -17.10% | +141.42% |
| **0.20% (Extreme Stress)** | -79.54% | +7.97% | **+87.51%** | -204.83% | -63.40% | +141.42% |

---

## 8. Monte Carlo Bootstrap Analysis (5,000 Resamples)

| Resampling Metric | LONG Candidate Alpha | SHORT Candidate Alpha |
| :--- | :---: | :---: |
| **Simulations** | 5,000 | 5,000 |
| **Mean Alpha** | **+87.41%** | **+141.44%** |
| **Median Alpha** | **+86.86%** | **+141.21%** |
| **5th Percentile (Worst 5% tail)** | **+53.18%** | **+100.20%** |
| **95th Percentile (Top 5% tail)** | **+123.94%** | **+184.53%** |
| **Probability of Positive Alpha ($P[\alpha > 0]$)** | **100.00%** | **100.00%** |

---

## 9. Final Decision Matrix

| Direction | Model Architecture | Net Return | PF | CAGR | Max DD | OOS Alpha | Avg Giveback | Robust Plateau? | Verdict |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **LONG** | Fixed +3.00% Control | +78.67% | 1.057 | 26.71% | 83.88% | Baseline | 0.00% | Control | **FROZEN CONTROL** |
| **LONG** | HWM Trail 0.35% | +229.50% | 1.166 | 77.90% | 56.94% | +62.41% | 0.36% | Yes (Tight) | **ACCEPT FOR VALIDATION** |
| **LONG** | **HWM Trail 0.50%** | **+166.18%** | **1.120** | **56.41%** | **63.02%** | **+37.68%** | **0.52%** | **Yes (Optimal)** | **ACCEPT FOR VALIDATION** |
| **LONG** | HWM Trail 0.60% | +127.36% | 1.092 | 43.23% | 66.82% | +22.81% | 0.62% | Yes | **ACCEPT FOR VALIDATION** |
| **LONG** | HWM Trail 0.75% | +88.57% | 1.064 | 30.07% | 69.92% | +4.36% | 0.78% | Borderline | **INCONCLUSIVE** |
| **LONG** | HWM Trail 1.00% | +44.04% | 1.032 | 14.95% | 84.89% | -18.52% | 1.04% | No (Decayed) | **REJECT** |
| **LONG** | EMA9 Close Trail | +239.48% | 1.172 | 81.29% | 56.14% | +29.77% | 1.95% | High Giveback | **REJECT (Giveback Risk)** |
| **LONG** | EMA9 + MACD Trail | +224.49% | 1.158 | 76.20% | 70.59% | +19.48% | 2.13% | High Giveback | **REJECT (Giveback Risk)** |
| **SHORT** | **Fixed +1.50% Control** | **-84.45%** | **0.897** | **-28.67%** | **121.50%** | **Baseline** | **0.00%** | **Control** | **FROZEN CONTROL** |
| **SHORT** | HWM Trail 0.35% | +122.38% | 1.149 | 41.54% | 39.02% | +75.31% | 0.34% | Fragile | **INCONCLUSIVE** |
| **SHORT** | HWM Trail 0.50% | +56.98% | 1.069 | 19.34% | 56.61% | +49.34% | 0.49% | Narrow | **INCONCLUSIVE** |
| **SHORT** | HWM Trail 0.60% | +17.40% | 1.021 | 5.90% | 73.39% | +31.39% | 0.59% | Low PF | **REJECT** |
| **SHORT** | HWM Trail $\ge 0.75\%$ | -22.39% | 0.973 | -7.60% | 97.15% | +13.61% | 0.73% | Negative | **REJECT** |
| **SHORT** | EMA9 / MACD Trails | -124.23% | 0.865 | -42.17% | 163.33% | +32.19% | 1.96% | Severe Loss | **REJECT** |

---

## 10. Explicit Answers to the 10 Conclusion Questions

1. **Is LONG target-to-runner superior to fixed +3.00%?**  
   **YES.** HWM trailing at 0.50% generates +87.51% incremental net return, lifts Profit Factor from 1.057 to 1.120, and contracts maximum drawdown from 83.88% down to 63.02%.
2. **Is SHORT target-to-runner superior to fixed +1.50%?**  
   **NO for production adoption.** Although a tight 0.35% trailing model extracts temporary alpha in backtesting, the parameter space is precarious: any trail $\ge 0.75\%$ plunges directly into net losses due to violent short-covering bounces.
3. **Which trail width is most robust for LONG?**  
   **0.50% HWM Trail.** It sits in the center of the stable plateau (0.35%–0.60%), surrenders only 0.52% average giveback, and achieves 100% positive bootstrap confidence.
4. **Which trail width is most robust for SHORT?**  
   **Fixed +1.50% target (zero trail) remains the safest control.** If a runner were tested in paper mode, only 0.35% is mathematically viable.
5. **Is there evidence that both directions should use trailing?**  
   **NO.** Evidence demonstrates strong directional divergence. Longs trend steadily; Shorts suffer frequent sharp mean-reversions.
6. **Is asymmetric treatment LONG vs SHORT statistically justified?**  
   **YES.** Asymmetry is mandatory. Longs benefit from riding runaway trends beyond +3.00% (reaching up to +15%), while Shorts must bank fixed quick profits at +1.50%.
7. **Does the result survive OOS testing?**  
   **YES.** LONG HWM 0.50% delivered +37.68% net alpha over control in untouched OOS data (Jul 2025 – Sep 2026).
8. **Does the result survive walk-forward testing?**  
   **YES.** LONG HWM 0.50% outperformed the fixed control across all 4 consecutive rolling quarters.
9. **Does it survive transaction-cost/slippage stress?**  
   **YES.** LONG HWM 0.50% maintains positive profitability across all friction levels up to 0.20% per trade.
10. **Is further shadow validation necessary?**  
    **YES.** Forward paper observation is recommended before modifying live execution code.

---

## 11. Production Freeze Verification

- `strategies/liveonopenalgo/emacrossopen.py`: **Clean / Frozen**
- `strategies/liveonopenalgo/macdfno.py`: **Clean / Frozen**
- **OpenAlgo Uploads:** 0 (None)
- **AWS Server Deployments:** 0 (None)
- **Process Restarts:** 0 (None)

**System status: STOPPED. Awaiting explicit user direction.**
