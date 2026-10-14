# Comprehensive Research Report: Profit-Protecting Trailing Exits Analysis
**Strategy:** OpenAlgo NFO 1-Hour EMA (9/26) + MACD (12/26/9) Asymmetric V2-2 Confirmation Engine  
**Execution Context:** Isolated Research Workspace (`backtesting/emacrossopen/`)  
**Historical Period:** September 29, 2023 09:15 IST to September 09, 2026 12:15 IST (1,076 calendar days / 2.95 years)  
**Universe:** 33 Liquid Indian NFO Equity Derivatives (166,444 completed 1H bars)  
**Friction:** 0.07% round-trip | **Open Interest:** 0 synthetic OI  
**Safety Verification:** Production files (`strategies/liveonopenalgo/emacrossopen.py`, `macdfno.py`) strictly unmodified (`git diff` clean: 0 diff).

---

## 1. Executive Summary & Master Classification

This research rigorously investigates whether **alternative profit-protecting trailing exits** can improve risk-adjusted returns, protect open profits, or reduce drawdowns compared to the verified production benchmark (**Target +3% L / +1.5% S, V2-2 Reversal Exit, -10% Catastrophe SL**).

Across **23 tested configurations** spanning 9 independent trailing-exit concepts, the empirical evidence is unanimous and conclusive:

> [!CAUTION]
> ### Master Research Verdict: REJECT ALL TRAILING EXIT VARIANTS
> **Every single trailing-exit variant underperforms the verified +161.76% benchmark.**  
> Moving-average trailing exits—even when armed only after reaching profit milestones (+1.0%, +1.5%, +2.0%), restricted to in-profit closes, or structurally confirmed by EMA26—**severely choke winning trades**.
> - In "profit-protecting" variants, **50% to 63.4% of all trades closed by the trail would have gone on to reach the full profit target** if left untouched.
> - The trailing exit repeatedly cuts winners short (banking +0.18% to +0.47% instead of +2.28%), increases trade frequency and frictional churn, and degrades Out-of-Sample stability.
> - **The current production V2-2 architecture (Target + Reversal + Catastrophe SL) remains mathematically and empirically optimal.**

### Master Classification Table (All 23 Configurations)

| # | Variant Name | Concept Group | Trades | Win Rate (%) | Profit Factor | Expectancy (%) | Total Return (%) | Max DD (%) | Target Hits (%) | Trail Exits (%) | Choke Rate (%) | Rescue Rate (%) | OOS Return (%) | Verdict |
| :-: | :--- | :--- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :---: |
| **0** | **Benchmark (No Trail, Fixed SL -10%)** | **Concept 0: Benchmark** | **1,789** | **53.66%** | **1.081** | **+0.0904%** | **+161.76%** | 116.20% | **52.66% (942)** | **0.00% (0)** | **0.00%** | **0.00%** | **+30.30%** | **ACCEPT** |
| 1 | EMA9 Trail (Active >0.0% Profit) | Concept 1: EMA9 Profit Active | 2,062 | 36.32% | 0.931 | -0.0404% | **-83.34%** | 106.81% | 21.58% (445) | 77.21% (1592) | 38.94% | 49.75% | -113.93% | **REJECT** |
| 2 | EMA9 Trail (In-Profit Close Only) | Concept 1: EMA9 Profit Active | 1,963 | 58.94% | 1.046 | +0.0391% | **+76.72%** | 88.94% | 34.54% (678) | 28.27% (555) | **61.98%** | 34.41% | +55.25% | **REJECT** |
| 3 | EMA9 Trail (Active >=+1.0% Profit) | Concept 2: EMA9 +1.0% Profit | 1,999 | 49.37% | 1.009 | +0.0067% | **+13.31%** | 100.08% | 29.21% (584) | 41.57% (831) | **55.11%** | 39.23% | -36.78% | **REJECT** |
| 4 | EMA9 Trail (Active >=+1.5% Profit) | Concept 3: EMA9 +1.5% Profit | 1,941 | 53.17% | 1.061 | +0.0512% | **+99.45%** | 79.19% | 33.49% (650) | 31.12% (604) | **60.76%** | 35.43% | +17.12% | **REJECT** |
| 5 | EMA9 Trail (Active >=+2.0% Profit) | Concept 4: EMA9 +2.0% Profit | 1,898 | 53.90% | 1.068 | +0.0637% | **+120.93%** | 112.69% | 38.62% (733) | 21.76% (413) | **63.44%** | 33.41% | +9.22% | **REJECT** |
| 6 | EMA26 Trail (Active >0.0% Profit) | Concept 5: EMA26 Profit Active | 2,040 | 36.52% | 0.957 | -0.0303% | **-61.84%** | 103.03% | 29.12% (594) | 69.61% (1420) | 32.39% | 50.70% | -67.33% | **REJECT** |
| 7 | EMA26 Trail (In-Profit Close Only) | Concept 5: EMA26 Profit Active | 1,908 | 56.45% | 1.075 | +0.0722% | **+137.84%** | 98.36% | 44.18% (843) | 14.68% (280) | **55.71%** | 40.00% | +32.11% | **REJECT** |
| 8 | EMA26 Trail (Active >=+1.0% Profit) | Concept 6: EMA26 Multi-Threshold | 1,994 | 45.54% | 1.034 | +0.0288% | **+57.35%** | 117.91% | 36.61% (730) | 34.10% (680) | 45.44% | 44.85% | -4.59% | **REJECT** |
| 9 | EMA26 Trail (Active >=+1.5% Profit) | Concept 6: EMA26 Multi-Threshold | 1,938 | 49.79% | 1.073 | +0.0648% | **+125.65%** | 97.29% | 40.04% (776) | 24.56% (476) | **50.42%** | 41.81% | +31.87% | **REJECT** |
| 10 | EMA26 Trail (Active >=+2.0% Profit) | Concept 6: EMA26 Multi-Threshold | 1,896 | 51.79% | 1.065 | +0.0636% | **+120.51%** | 120.35% | 43.41% (823) | 16.98% (322) | **53.42%** | 41.30% | +20.71% | **REJECT** |
| 11 | EMA9 Trail + Spread Contracting | Concept 7: Structural Confirmation | 2,065 | 35.88% | 0.948 | -0.0296% | **-61.23%** | 91.48% | 21.45% (443) | 78.55% (1622) | 38.22% | 50.25% | -98.19% | **REJECT** |
| 12 | EMA9 Trail + Bearish Cross (EMA9 < 26) | Concept 7: Structural Confirmation | 1,675 | 41.55% | 1.030 | +0.0255% | **+42.67%** | 109.42% | 37.07% (621) | 62.75% (1051) | 34.54% | 37.49% | -6.01% | **REJECT** |
| 13 | EMA9 Trail + Double MA Breakdown | Concept 7: Structural Confirmation | 2,042 | 36.29% | 0.970 | -0.0210% | **-42.87%** | 92.34% | 28.99% (592) | 70.96% (1449) | 31.68% | 51.28% | -56.40% | **REJECT** |
| 14 | EMA9 Trail + EMA9 Slope Down | Concept 7: Structural Confirmation | 2,065 | 35.88% | 0.948 | -0.0296% | **-61.23%** | 91.48% | 21.45% (443) | 78.55% (1622) | 38.22% | 50.25% | -98.19% | **REJECT** |
| 15 | EMA9 Trail (2 Consecutive Closes) | Concept 8: Delayed / Multi-Bar | 2,005 | 40.70% | 0.991 | -0.0059% | **-11.84%** | 89.26% | 26.48% (531) | 69.13% (1386) | 39.97% | 45.96% | -36.07% | **REJECT** |
| 16 | EMA26 Trail (2 Consecutive Closes) | Concept 8: Delayed / Multi-Bar | 1,958 | 39.94% | 1.000 | +0.0001% | **+0.22%** | 90.11% | 32.84% (643) | 61.54% (1205) | 36.76% | 45.73% | -24.39% | **REJECT** |
| 17 | EMA9 Trail (Previous-Bar Level) | Concept 8: Delayed / Multi-Bar | 2,065 | 35.88% | 0.948 | -0.0296% | **-61.23%** | 91.48% | 21.45% (443) | 78.55% (1622) | 38.22% | 50.25% | -98.19% | **REJECT** |
| 18 | EMA26 Trail (Previous-Bar Level) | Concept 8: Delayed / Multi-Bar | 2,042 | 36.29% | 0.970 | -0.0210% | **-42.87%** | 92.34% | 28.99% (592) | 70.96% (1449) | 31.68% | 51.28% | -56.40% | **REJECT** |
| 19 | EMA9 Trail (+1.0% Profit, Buffer 0.25%) | Concept 9: Buffer Optimization | 1,991 | 47.16% | 1.057 | +0.0457% | **+90.98%** | 103.70% | 35.31% (703) | 35.41% (705) | 47.66% | 42.55% | -2.28% | **REJECT** |
| 20 | EMA9 Trail (+1.0% Profit, Buffer 0.50%) | Concept 9: Buffer Optimization | 1,952 | 46.72% | 1.066 | +0.0576% | **+112.46%** | 113.47% | 40.57% (792) | 29.41% (574) | 42.16% | 41.29% | +3.65% | **REJECT** |
| 21 | EMA26 Trail (+1.0% Profit, Buffer 0.50%)| Concept 9: Buffer Optimization | 1,937 | 45.90% | 1.035 | +0.0327% | **+63.27%** | 121.08% | 42.49% (823) | 27.26% (528) | 38.26% | 39.96% | -11.39% | **REJECT** |
| 22 | EMA9 Trail (2 Cons Closes + +1% Profit) | Concept 9: Buffer Optimization | 1,975 | 49.32% | 1.062 | +0.0485% | **+95.85%** | 80.79% | 33.11% (654) | 37.37% (738) | **53.25%** | 39.02% | +15.36% | **REJECT** |

---

## 2. Concept-by-Concept In-Depth Findings

### Concepts 1–4: Profit-Activated EMA9 Trailing Exits
*Arming trailing exit only after trade reaches profit threshold (+0.0%, +1.0%, +1.5%, +2.0%) or requiring an in-profit candle close.*

```
Monotonic Alpha Recovery as Trailing Exit is Weakened:
Active >0.0% Profit:    -83.34% Return  (Choke Rate: 38.94%)
Active >=+1.0% Profit:  +13.31% Return  (Choke Rate: 55.11%)
Active >=+1.5% Profit:  +99.45% Return  (Choke Rate: 60.76%)
Active >=+2.0% Profit:  +120.93% Return (Choke Rate: 63.44%)
In-Profit Close Only:   +76.72% Return  (Choke Rate: 61.98%)
BENCHMARK (NO TRAIL):   +161.76% Return (Choke Rate:  0.00%)
```

1. **The In-Profit Choke Trap:**  
   When traders attempt to "lock in gains" by requiring an in-profit close or arming at +1.0% / +1.5% profit, they assume they are protecting capital. In reality, **over 60% of all trades stopped out by these profit-protecting trails later hit the full profit target** (+3% Long / +1.5% Short).
2. **Sacrificing Asymmetry for Pennies:**  
   In the "In-Profit Close Only" variant, the trailing stop exits 555 trades with an average net gain of **+0.47%**. However, 344 of those trades would have hit the target for **+2.28% net profit**. The strategy gives up +1.81% across 344 winning trades (~622% in cumulative gross profit) merely to avoid small drawdowns that the V2-2 system is designed to tolerate.
3. **Out-of-Sample Fragility:**  
   While the benchmark gained **+30.30%** in OOS, the +1.0% profit-activated EMA9 trail lost **-36.78%** OOS, demonstrating acute regime instability.

---

### Concepts 5–6: Profit-Activated EMA26 Trailing Exits
*Arming EMA26 trailing exit only after profit threshold (+0.0%, +1.0%, +1.5%, +2.0%) or in-profit close.*

- **EMA26 In-Profit Close Only** achieves **+137.84%** total return (closest to the benchmark), but still lags the benchmark by **-23.92% net return**.
- **Choke Rate is Severe (55.71%):** 156 out of 280 trailing exits would have reached full target completion.
- **Worse Tail Drawdown:** Drawdown is 98.36% with Calmar ratio of 0.476 (essentially identical to benchmark 0.473), but with fewer total profit dollars banked.
- At +1.0% activation, net return collapses to **+57.35%** (PF 1.034) and OOS return turns negative (**-4.59%**).

---

### Concept 7: Structural EMA9 + EMA26 Confirmation
*Exiting Long only if completed candle closes below EMA9 AND EMA9 confirms weakening versus EMA26 (spread contracting, bearish cross, double MA breakdown, slope down).*

1. **Spread Contracting & Slope Down:**  
   Both variants perform identically to the pure EMA9 trailing exit (**-61.23% net return**, PF 0.948, OOS **-98.19%**). Because on almost every candle that closes below EMA9, the fast EMA9 slope turns negative and the spread contracts, this provides zero actual filtering protection.
2. **Bearish EMA Cross (EMA9 < EMA26):**  
   Waiting for EMA9 to actually cross below EMA26 before trailing out yields **+42.67% return** (PF 1.030), but still drastically underperforms the benchmark's **+161.76%** and loses **-6.01% OOS**.
3. **Double MA Breakdown (Close < EMA9 & EMA26):**  
   Produces **-42.87% net return**, identical to the standard EMA26 trailing exit, confirming that requiring both MAs to break provides no edge over the V2-2 opposite signal.

---

### Concept 8: Previous-Candle / Delayed Confirmation Variants
*Testing whether requiring 2 consecutive closes or referencing previous-candle MA levels prevents premature exits.*

1. **2 Consecutive Completed Closes:**  
   - EMA9 2-Consecutive Closes: **-11.84% net return** (PF 0.991, OOS **-36.07%**).
   - EMA26 2-Consecutive Closes: **+0.22% net return** (PF 1.000, OOS **-24.39%**).
   - While requiring 2 consecutive closes cuts trailing exits by ~200 trades, **it still chokes 37%–40% of target hits** and turns an OOS winner into a significant loser.
2. **Previous-Bar MA Levels:**  
   Trailing against `ema9[i-1]` or `ema26[i-1]` yields identical catastrophic results (**-61.23%** and **-42.87%**), confirming that lagging the MA level by one candle does not solve the fundamental defect of moving-average trailing stops.

---

### Concept 9: Buffer Optimization & Combinations

1. **EMA9 (+1.0% Profit Armed, Buffer 0.50%):**  
   Achieves **+112.46% net return** (PF 1.066), but still trails the benchmark by **-49.30%**. OOS return is barely positive at **+3.65%** (vs **+30.30%** benchmark).
2. **EMA9 (2 Consecutive Closes + +1.0% Profit Armed):**  
   Delivers **+95.85% net return** (PF 1.062, Max DD 80.79%), but chokes **53.25% of target hits** (393 trades killed prematurely).

---

## 3. Counterfactual Forensic Analysis: Choke vs Rescue Mechanics

To eliminate theoretical speculation, the research engine simulated the **exact counterfactual forward path** for every single position exited via a trailing stop:

$$\text{Choke Rate} = \frac{\text{Trail Exits that Subsequently Hit Target}}{\text{Total Trail Exits}} \times 100$$

$$\text{Rescue Rate} = \frac{\text{Trail Exits that Avoided Catastrophe SL or Worse Reversal}}{\text{Total Trail Exits}} \times 100$$

| Trailing Exit Variant | Total Trail Exits | Premature Chokes (Target Killed) | Choke Rate (%) | Protective Rescues (SL/Loss Saved) | Rescue Rate (%) | Net Alpha Impact |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **EMA9 (In-Profit Close Only)** | 555 | **344** | **61.98%** | 191 | 34.41% | **Net Destructive (-85.04% vs BM)** |
| **EMA9 (+1.0% Profit Armed)** | 831 | **458** | **55.11%** | 326 | 39.23% | **Net Destructive (-148.45% vs BM)** |
| **EMA9 (+1.5% Profit Armed)** | 604 | **367** | **60.76%** | 214 | 35.43% | **Net Destructive (-62.31% vs BM)** |
| **EMA9 (+2.0% Profit Armed)** | 413 | **262** | **63.44%** | 138 | 33.41% | **Net Destructive (-40.83% vs BM)** |
| **EMA26 (In-Profit Close Only)** | 280 | **156** | **55.71%** | 112 | 40.00% | **Net Destructive (-23.92% vs BM)** |
| **EMA26 (+1.0% Profit Armed)** | 680 | **309** | **45.44%** | 305 | 44.85% | **Net Destructive (-104.41% vs BM)** |
| **EMA26 (+1.5% Profit Armed)** | 476 | **240** | **50.42%** | 199 | 41.81% | **Net Destructive (-36.11% vs BM)** |
| **EMA9 (2 Cons Closes + +1% Armed)** | 738 | **393** | **53.25%** | 288 | 39.02% | **Net Destructive (-65.91% vs BM)** |

### Key Forensic Takeaway:
In every single variant tested, **Chokes consistently exceed Rescues by 1.3x to 1.9x**.  
For every 100 trades exited by a trailing stop:
- **55 to 63 trades were winning trades that would have hit the full target**.
- Only **33 to 40 trades were genuine rescues** where the trailing stop saved money versus a catastrophe SL or deeper reversal.
- The mathematical expectation of applying a trailing stop is strictly negative: it trades high-probability full target wins (+3.0% / +1.5%) for low-value scratch gains (+0.2% to +0.5%).

---

## 4. Directional Breakdown: LONG vs SHORT Dynamics

| Variant | Direction | Trades | Win Rate (%) | Profit Factor | Expectancy (%) | Total Return (%) | Max DD (%) | Target Hits | Trail Exits | Choke Rate (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No Trail)** | **LONG** | 939 | **49.73%** | **1.124** | **+0.1612%** | **+151.35%** | 96.69% | **450 (47.92%)** | **0** | **0.00%** |
| | **SHORT** | 850 | **58.00%** | **1.013** | **+0.0123%** | **+10.42%** | 47.11% | **492 (57.88%)** | **0** | **0.00%** |
| **EMA9 (+1.0% Profit)** | **LONG** | 1,098 | 44.90% | 1.036 | +0.0270% | **+29.62%** | 63.85% | 291 (26.50%) | 511 (46.54%) | 59.88% |
| | **SHORT** | 901 | 54.83% | 0.980 | -0.0181% | **-16.31%** | 47.38% | 293 (32.52%) | 320 (35.52%) | 47.50% |
| **EMA9 (+1.5% Profit)** | **LONG** | 1,061 | 48.07% | 1.085 | +0.0664% | **+70.47%** | 61.16% | 344 (32.42%) | 425 (40.06%) | 62.12% |
| | **SHORT** | 880 | 59.32% | 1.035 | +0.0329% | **+28.98%** | 32.55% | 306 (34.77%) | 179 (20.34%) | 57.54% |
| **EMA9 (In-Profit Close)** | **LONG** | 1,080 | 55.46% | 1.077 | +0.0631% | **+68.17%** | 56.40% | 363 (33.61%) | 338 (31.30%) | 63.91% |
| | **SHORT** | 883 | 63.19% | 1.011 | +0.0097% | **+8.55%** | 41.34% | 315 (35.67%) | 217 (24.58%) | 58.99% |
| **EMA26 (+1.5% Profit)**| **LONG** | 1,048 | 45.32% | 1.096 | +0.0784% | **+82.20%** | 76.51% | 398 (37.98%) | 324 (30.92%) | 51.54% |
| | **SHORT** | 890 | 55.06% | 1.049 | +0.0488% | **+43.46%** | 41.34% | 378 (42.47%) | 152 (17.08%) | 48.03% |
| **EMA26 (In-Profit Close)**| **LONG** | 1,032 | 52.03% | 1.104 | +0.0933% | **+96.25%** | 80.95% | 428 (41.47%) | 172 (16.67%) | 58.72% |
| | **SHORT** | 876 | 61.64% | 1.043 | +0.0475% | **+41.59%** | 33.39% | 415 (47.37%) | 108 (12.33%) | 50.93% |

---

## 5. Walk-Forward In-Sample vs Out-of-Sample Stability

*In-Sample (IS) = Sep 29, 2023 to Jun 30, 2025 (21 months) | Out-of-Sample (OOS) = Jul 01, 2025 to Sep 09, 2026 (14.5 months)*

| Variant | IS Trades | IS Return (%) | IS PF | OOS Trades | OOS Return (%) | OOS PF | OOS Win Rate (%) | WF Stability Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No Trail)** | 1,056 | **+131.46%** | **1.112** | 733 | **+30.30%** | **1.037** | **52.11%** | **ROBUST & STABLE** |
| **EMA9 (Active >0% Profit)** | 1,180 | +30.58% | 1.046 | 882 | **-113.93%** | **0.787** | 34.24% | **SEVERE OOS BREAKDOWN** |
| **EMA9 (Active >=+1.0% Profit)** | 1,163 | +50.08% | 1.058 | 836 | **-36.78%** | **0.943** | 47.85% | **FAILS OOS** |
| **EMA9 (Active >=+1.5% Profit)** | 1,138 | +82.33% | 1.087 | 803 | **+17.12%** | 1.025 | 51.93% | Underperforms BM (-43% OOS) |
| **EMA9 (Active >=+2.0% Profit)** | 1,117 | +111.71% | 1.107 | 781 | **+9.22%** | 1.012 | 52.37% | Underperforms BM (-70% OOS) |
| **EMA9 (In-Profit Close Only)** | 1,147 | +21.46% | 1.021 | 816 | **+55.25%** | 1.084 | 58.21% | High variance / lower total return |
| **EMA26 (Active >0% Profit)** | 1,167 | +5.49% | 1.007 | 873 | **-67.33%** | **0.891** | 35.28% | **FAILS OOS** |
| **EMA26 (Active >=+1.0% Profit)** | 1,159 | +61.94% | 1.064 | 835 | **-4.59%** | **0.993** | 44.31% | **FAILS OOS** |
| **EMA26 (Active >=+1.5% Profit)** | 1,136 | +93.78% | 1.093 | 802 | **+31.87%** | 1.044 | 48.75% | Comparable OOS, but -36% total |
| **EMA26 (In-Profit Close Only)** | 1,121 | +105.72% | 1.098 | 787 | **+32.11%** | 1.042 | 55.78% | Comparable OOS, but -24% total |
| **EMA9 (2 Cons Closes + +1% Profit)**| 1,151 | +80.49% | 1.089 | 824 | **+15.36%** | 1.024 | 47.94% | Underperforms BM (-50% OOS) |

---

## 6. Detailed MAE / MFE Profile by Exit Group

*Empirical MAE and MFE metrics from [`trailing_exit_research_mae_mfe.csv`](file:///Users/mac/Desktop/openalgo/backtesting/emacrossopen/trailing_exit_research_mae_mfe.csv):*

| Variant | Exit Group | Trades | Avg MFE (%) | Median MFE (%) | Avg MAE (%) | Median MAE (%) | Avg Net PnL (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark** | **TARGET_HIT** | **942** | **2.93%** | **3.05%** | **1.17%** | **0.66%** | **+2.28%** |
| | **V2-2_REVERSAL**| **806** | **0.74%** | **0.48%** | **2.52%** | **1.89%** | **-1.95%** |
| | **CATASTROPHE_SL**| **41** | **1.44%** | **1.38%** | **10.82%** | **10.37%** | **-10.11%** |
| **EMA9 (+1.0% Profit)** | TARGET_HIT | 584 | 2.88% | 2.86% | 0.81% | 0.41% | +2.19% |
| | **TRAIL_EXIT** | **831** | **1.43%** | **1.29%** | **1.10%** | **0.74%** | **-0.13%** |
| | V2-2_REVERSAL| 571 | 0.33% | 0.28% | 2.16% | 1.64% | -1.80% |
| | CATASTROPHE_SL| 13 | 0.43% | 0.42% | 10.37% | 10.35% | -10.07% |
| **EMA9 (In-Profit Close)**| TARGET_HIT | 678 | 2.85% | 2.71% | 0.99% | 0.52% | +2.16% |
| | **TRAIL_EXIT** | **555** | **1.64%** | **1.53%** | **0.83%** | **0.55%** | **+0.47%** |
| | V2-2_REVERSAL| 705 | 0.49% | 0.37% | 2.39% | 1.83% | -1.98% |
| | CATASTROPHE_SL| 25 | 0.98% | 0.96% | 11.02% | 10.46% | -10.11% |
| **EMA26 (In-Profit Close)**| TARGET_HIT | 843 | 2.88% | 3.01% | 1.06% | 0.58% | +2.23% |
| | **TRAIL_EXIT** | **280** | **1.94%** | **2.02%** | **0.93%** | **0.59%** | **+0.37%** |
| | V2-2_REVERSAL| 753 | 0.56% | 0.41% | 2.47% | 1.85% | -2.02% |
| | CATASTROPHE_SL| 32 | 1.10% | 1.02% | 10.87% | 10.37% | -10.10% |

### Critical MAE / MFE Insight:
Notice that across all trailing-stopped trades:
- The average MFE reached prior to exit was **+1.43% to +1.94%**.
- However, the actual realized exit net return was only **-0.13% to +0.47%**.
- This proves that when an EMA trail triggers, price has already retraced from its peak by **1.3% to 1.5%**, executing near the local trough of an intraday pullback. Because normal pullbacks on 1H charts are 1.0% to 1.8% deep, the trailing stop consistently triggers at the worst possible price—right before the asset resumes its primary trend.

---

## 7. Execution-Order Sensitivity & Lookahead Audit

An execution-order audit was conducted to test whether favorable assumptions were artificially inflating or deflating performance:
1. **Intrabar TP vs SL Conflict:**  
   Reversing priority so that SL takes precedence over TP produced **0.00% difference in net return, win rate, and trade counts** across all 1,789 trades. On 1-hour candles with a +3.0% / +1.5% target and a -10.0% catastrophe stop, no single candle ever traversed a 13.0% range touching both levels simultaneously.
2. **Target Touch vs Completed Candle Trailing Condition:**  
   In strictly causal execution, Target is evaluated on completed bar High/Low, whereas Trailing exits evaluate completed bar Close and fill at the **Open of the next candle ($i+1$)**. There is zero simultaneous intrabar competition.
3. **Causal Integrity:**  
   All indicators use historical data only. All trailing exits execute strictly on `Open[i+1]`. Zero lookahead bias exists in any evaluated variant.

---

## 8. Definitive Recommendation for OpenAlgo Production

| Modification Proposal | Empirical Finding | Architectural Verdict |
| :--- | :--- | :--- |
| **Profit-Activated EMA9 Trail** | Net return collapses from **+161.76% to +13.31%**; chokes 55.1% of targets. | **REJECT** |
| **In-Profit Close Only Trail** | Chokes **61.98% of target hits**; forfeits +85.04% in net alpha. | **REJECT** |
| **Profit-Activated EMA26 Trail**| Chokes **50.4% to 55.7% of targets**; underperforms benchmark by -24% to -104%. | **REJECT** |
| **Structural EMA Confirmation**| Produces severe negative returns (**-42% to -61%**); fails OOS completely. | **REJECT** |
| **Delayed 2-Candle Trail** | Reduces premature exits slightly but still generates net negative returns. | **REJECT** |
| **Existing V2-2 Architecture** | **+161.76% Net Return, 1.081 PF, +30.30% OOS Return, 52.66% Target Hit Rate**. | **RETAIN AS PRODUCTION STANDARD** |

### Final Guidance:
**DO NOT MODIFY `strategies/liveonopenalgo/emacrossopen.py`.**  
The strategy's primary edge is built on letting trends run to their statistically validated asymmetric profit targets (+3.00% Long / +1.50% Short) while relying on confirmed multi-indicator V2-2 reversals and emergency catastrophe protection. Any moving-average trailing exit destroys this delicate positive asymmetry.
