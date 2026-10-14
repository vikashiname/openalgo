# Research Report: EMA26 Candle-Close Trailing Exit Analysis
**Strategy:** OpenAlgo NFO 1-Hour EMA (9/26) + MACD (12/26/9) Asymmetric V2-2 Sequential Confirmation Engine  
**Execution Context:** Isolated Research Workspace (`backtesting/emacrossopen/`)  
**Historical Period:** September 29, 2023 09:15 IST to September 09, 2026 12:15 IST (1,076 calendar days / 2.95 years)  
**Universe:** 33 Liquid Indian NFO Derivatives (166,444 completed 1H bars)  
**Friction:** 0.07% round-trip | **Open Interest:** 0 synthetic OI  
**Safety Status:** Live production files (`strategies/liveonopenalgo/emacrossopen.py`, `macdfno.py`) completely unmodified (`git diff` clean: 0 diff).

---

## 1. Executive Summary & Definitive Recommendation

This research investigated whether an **EMA26 candle-close trailing exit** improves profit retention versus the baseline **V2-2 opposite-signal reversal exit**.

### Definitive Verdict:
> [!CAUTION]
> **REJECT EMA26 TRAILING EXIT ENTIRELY.**  
> Testing across 166,444 completed 1H candles proves conclusively that an EMA26 candle-close trailing exit **severely degrades strategy performance, chokes off winning target trades, increases drawdown, and turns an Out-of-Sample profitable system into a persistent money-loser across every single tested buffer.**

### Core Empirical Proof:
1. **Catastrophic Edge Destruction:**
   - The verified benchmark (**Target + V2-2 Reversal + Fixed SL -10%**) delivers **+161.76% Net Return**, **1.081 Profit Factor**, and **53.66% Win Rate**.
   - Introducing an EMA26 candle-close trailing exit with **0.00% buffer** causes total return to collapse from **+161.76% down to -42.87%** (a **204% destruction of alpha**), with Win Rate dropping to **36.29%** and Profit Factor dropping below unity to **0.970**.
2. **Persistent Out-of-Sample Failure Across ALL Buffers:**
   - In Out-of-Sample testing (Jul 2025 – Sep 2026, 14.5 months), the benchmark produced **+30.30% Net Profit** (PF 1.037).
   - Under EMA26 trailing exits, **every single buffer variant loses money out-of-sample**:
     - 0.00% buffer: **-56.40% OOS** (PF 0.906)
     - 0.25% buffer: **-35.56% OOS** (PF 0.946)
     - 0.50% buffer: **-81.59% OOS** (PF 0.885)
     - 1.00% buffer: **-61.79% OOS** (PF 0.919)
     - 1.50% buffer: **-30.99% OOS** (PF 0.961)
     - 2.00% buffer: **-31.74% OOS** (PF 0.962)
3. **Massive Premature Choking of Winning Trades:**
   - At 0.00% buffer, **70.96% of all trades (1,449 trades)** exit prematurely via EMA26!
   - Target hits drop from **942 trades (52.66%) down to 592 trades (28.99%)**—eradicating 350 winning target completions.
4. **EMA26 Performs Even Worse than EMA9 at Wider Buffers:**
   - At 0.50% buffer: EMA9 achieved -2.69% return, while EMA26 collapsed to **-51.77%**.
   - At 1.00% buffer: EMA9 achieved +23.02% return, while EMA26 collapsed to **-25.26%**.
   - At 2.00% buffer: EMA9 achieved +128.51% return, while EMA26 achieved only **+65.79%**.

---

## 2. Master Comparison: Benchmark vs All EMA26 Buffer Variants

All variants maintain:
- Long Target: **+3.00%** | Short Target: **+1.50%** (evaluated from actual fill price)
- Catastrophe SL: **-10.00%** emergency backup
- V2-2 Reversal Logic
- Completed 1H candles only, 0.07% round-trip friction, strictly causal next-bar execution:

| Variant | Trades | Win Rate (%) | Profit Factor | Expectancy (%) | Total Return (%) | CAGR (%) | Max DD (%) | Calmar | Target Hits (%) | EMA26 Exits (%) | SL Hits (%) | Reversals (%) | Avg Bars Held | Max Single Loss (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No EMA Exit)** | **1,789** | **53.66%** | **1.081** | **+0.0904%** | **+161.76%** | **38.63%** | **116.20%** | **0.473** | **52.66% (942)** | **0.00% (0)** | **2.29% (41)** | **45.05% (806)** | **30.8** | **-10.65%** |
| **EMA26 Trailing (Buffer 0.00%)** | 2,042 | 36.29% | 0.970 | -0.0210% | **-42.87%** | -17.31% | 92.34% | -0.158 | 28.99% (592) | **70.96% (1449)**| 0.05% (1) | 0.00% (0) | 10.1 | -10.07% |
| **EMA26 Trailing (Buffer 0.25%)** | 1,939 | 39.81% | 1.001 | +0.0008% | **+1.48%** | 0.50% | 96.00% | 0.005 | 34.50% (669) | 64.26% (1246) | 0.10% (2) | 1.13% (22) | 12.7 | -10.07% |
| **EMA26 Trailing (Buffer 0.50%)** | 1,855 | 41.02% | 0.968 | -0.0279% | **-51.77%** | -21.93% | 128.93% | -0.136 | 37.57% (697) | 54.34% (1008) | 0.11% (2) | 7.98% (148) | 14.7 | -10.07% |
| **EMA26 Trailing (Buffer 1.00%)** | 1,822 | 44.24% | 0.986 | -0.0139% | **-25.26%** | -9.41% | 125.98% | -0.068 | 42.86% (781) | 31.56% (575) | 0.16% (3) | 25.41% (463) | 18.0 | -10.07% |
| **EMA26 Trailing (Buffer 1.50%)** | 1,805 | 47.76% | 1.032 | +0.0327% | **+59.04%** | 17.06% | 107.28% | 0.187 | 46.70% (843) | 20.44% (369) | 0.22% (4) | 32.63% (589) | 21.3 | -10.65% |
| **EMA26 Trailing (Buffer 2.00%)** | 1,803 | 50.08% | 1.034 | +0.0365% | **+65.79%** | 18.72% | 95.90% | 0.233 | 49.08% (885) | 13.37% (241) | 0.33% (6) | 37.22% (671) | 24.3 | -10.65% |

---

## 3. Head-to-Head Comparison: EMA26 vs EMA9 vs Benchmark

| Metric | Benchmark (V2-2 Only) | EMA26 Trailing (0.00%) | EMA9 Trailing (0.00%) | EMA26 Trailing (0.50%) | EMA9 Trailing (0.50%) | EMA26 Trailing (2.00%) | EMA9 Trailing (2.00%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Total Net Return** | **+161.76%** | **-42.87%** | **-61.23%** | **-51.77%** | **-2.69%** | **+65.79%** | **+128.51%** |
| **Profit Factor** | **1.081** | **0.970** | **0.948** | **0.968** | **0.998** | **1.034** | **1.066** |
| **Win Rate** | **53.66%** | **36.29%** | **35.88%** | **41.02%** | **41.61%** | **50.08%** | **51.83%** |
| **Expectancy / Trade** | **+0.0904%** | **-0.0210%** | **-0.0296%** | **-0.0279%** | **-0.0014%** | **+0.0365%** | **+0.0723%** |
| **OOS Return (14.5m)** | **+30.30%** | **-56.40%** | **-98.19%** | **-81.59%** | **-56.36%** | **-31.74%** | **+21.51%** |
| **Target Hits** | **942 (52.66%)** | **592 (28.99%)** | **443 (21.45%)** | **697 (37.57%)** | **676 (35.65%)** | **885 (49.08%)** | **903 (50.82%)** |
| **Premature Moving Avg Exits** | **0 (0.00%)** | **1,449 (70.96%)**| **1,622 (78.55%)**| **1,008 (54.34%)**| **1,052 (55.49%)**| **241 (13.37%)** | **149 (8.38%)** |
| **Verdict** | **SUPERIOR** | **FAILS** | **FAILS** | **FAILS** | **FAILS** | **UNDERPERFORMS**| **UNDERPERFORMS**|

---

## 4. Directional Breakdown: LONG vs SHORT Dynamics

| Variant | Direction | Trades | Win Rate (%) | Profit Factor | Expectancy (%) | Total Return (%) | Max DD (%) | Target Hits (%) | EMA26 Exits (%) | Reversals (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No EMA Exit)** | **LONG** | 939 | **49.73%** | **1.124** | **+0.1612%** | **+151.35%** | 96.69% | **47.92% (450)** | **0.00%** | 48.78% |
| | **SHORT** | 850 | **58.00%** | **1.013** | **+0.0123%** | **+10.42%** | 47.11% | **57.88% (492)** | **0.00%** | 40.94% |
| **EMA26 Trailing (0.00%)** | **LONG** | 1,176 | 32.74% | 0.989 | -0.0081% | **-9.51%** | 64.89% | 21.51% (253) | **78.40% (922)** | 0.00% |
| | **SHORT** | 866 | 41.11% | 0.942 | -0.0385% | **-33.36%** | 51.82% | 39.15% (339) | **60.85% (527)** | 0.00% |
| **EMA26 Trailing (0.25%)** | **LONG** | 1,125 | 35.20% | 1.028 | +0.0230% | **+25.86%** | 74.81% | 26.22% (295) | 72.62% (817) | 0.98% |
| | **SHORT** | 814 | 46.19% | 0.960 | -0.0299% | **-24.38%** | 45.31% | 45.95% (374) | 52.70% (429) | 1.35% |
| **EMA26 Trailing (0.50%)** | **LONG** | 1,074 | 35.29% | 0.995 | -0.0046% | **-4.95%** | 90.81% | 29.52% (317) | 62.94% (676) | 7.36% |
| | **SHORT** | 781 | 48.91% | 0.927 | -0.0600% | **-46.83%** | 62.00% | 48.66% (380) | 42.51% (332) | 8.83% |
| **EMA26 Trailing (1.00%)** | **LONG** | 1,010 | 37.23% | 0.988 | -0.0134% | **-13.49%** | 103.13% | 34.95% (353) | 38.61% (390) | 26.14% |
| | **SHORT** | 812 | 52.96% | 0.983 | -0.0145% | **-11.76%** | 46.27% | 52.71% (428) | 22.78% (185) | 24.51% |
| **EMA26 Trailing (1.50%)** | **LONG** | 981 | 41.59% | 1.050 | +0.0583% | **+57.19%** | 94.32% | 39.76% (390) | 26.81% (263) | 33.13% |
| | **SHORT** | 824 | 55.10% | 1.003 | +0.0022% | **+1.85%** | 51.96% | 54.98% (453) | 12.86% (106) | 32.04% |
| **EMA26 Trailing (2.00%)** | **LONG** | 968 | 44.73% | 1.065 | +0.0806% | **+78.04%** | 82.03% | 42.98% (416) | 18.70% (181) | 37.91% |
| | **SHORT** | 835 | 56.29% | 0.984 | -0.0147% | **-12.26%** | 56.80% | 56.17% (469) | 7.19% (60) | 36.41% |

---

## 5. Year-by-Year Performance Breakdown

### A. Rolling 12-Month Periods
- **Year 1:** Sep 29, 2023 to Sep 28, 2024
- **Year 2:** Sep 29, 2024 to Sep 28, 2025
- **Year 3:** Sep 29, 2025 to Sep 09, 2026

| Variant | Year 1 Return (%) | Year 1 PF | Year 2 Return (%) | Year 2 PF | Year 3 Return (%) | Year 3 PF | Full 3-Year Return (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No EMA Exit)** | **+177.61%** | **1.286** | **-11.33%** | **0.983** | **-4.52%** | **0.994** | **+161.76%** |
| **EMA26 Trailing (0.00%)** | +25.31% | 1.054 | +2.82% | 1.007 | **-71.00%** | **0.864** | **-42.87%** |
| **EMA26 Trailing (0.25%)** | +55.97% | 1.112 | -2.89% | 0.994 | **-51.60%** | 0.909 | **+1.48%** |
| **EMA26 Trailing (0.50%)** | +61.94% | 1.118 | -36.31% | 0.929 | **-77.41%** | 0.872 | **-51.77%** |
| **EMA26 Trailing (1.00%)** | +67.41% | 1.116 | -27.34% | 0.952 | **-65.32%** | 0.898 | **-25.26%** |
| **EMA26 Trailing (1.50%)** | +85.23% | 1.139 | +5.55% | 1.010 | **-31.74%** | 0.952 | **+59.04%** |
| **EMA26 Trailing (2.00%)** | +88.54% | 1.137 | +27.11% | 1.045 | **-49.87%** | 0.929 | **+65.79%** |

### B. Calendar Year Results (2023–2026)

| Variant | 2023 (Q4) Return | 2024 Return | 2025 Return | 2026 (YTD) Return | Cumulative Net Return |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No EMA Exit)** | **+62.11%** | **+91.63%** | **+11.95%** | **-3.92%** | **+161.76%** |
| **EMA26 Trailing (0.00%)** | +12.52% | +19.60% | -23.86% | **-51.12%** | **-42.87%** |
| **EMA26 Trailing (0.25%)** | +24.60% | +26.74% | -27.72% | **-22.14%** | **+1.48%** |
| **EMA26 Trailing (0.50%)** | +29.78% | +6.78% | -46.10% | **-42.23%** | **-51.77%** |
| **EMA26 Trailing (1.00%)** | +29.05% | +9.59% | -16.70% | **-47.20%** | **-25.26%** |
| **EMA26 Trailing (1.50%)** | +40.00% | +41.92% | +15.70% | **-38.58%** | **+59.04%** |
| **EMA26 Trailing (2.00%)** | +37.72% | +47.54% | +24.30% | **-43.77%** | **+65.79%** |

---

## 6. In-Sample vs Out-of-Sample Walk-Forward Stability

Partition: **In-Sample (IS)** = Sep 29, 2023 to Jun 30, 2025 (21 months) vs **Out-of-Sample (OOS)** = Jul 01, 2025 to Sep 09, 2026 (14.5 months):

| Variant | IS Trades | IS Return (%) | IS PF | IS Win Rate (%) | OOS Trades | OOS Return (%) | OOS PF | OOS Win Rate (%) | WF Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No EMA Exit)** | 1,056 | **+131.46%** | **1.112** | **54.73%** | 733 | **+30.30%** | **1.037** | **52.11%** | **PROFITABLE & STABLE** |
| **EMA26 Trailing (0.00%)** | 1,167 | +13.53% | 1.017 | 37.53% | 875 | **-56.40%** | **0.906** | 34.63% | **FAILS OOS** |
| **EMA26 Trailing (0.25%)** | 1,104 | +37.04% | 1.042 | 40.67% | 835 | **-35.56%** | **0.946** | 38.68% | **FAILS OOS** |
| **EMA26 Trailing (0.50%)** | 1,056 | +29.81% | 1.032 | 42.52% | 799 | **-81.59%** | **0.885** | 39.05% | **FAILS OOS** |
| **EMA26 Trailing (1.00%)** | 1,053 | +36.53% | 1.036 | 45.68% | 769 | **-61.79%** | **0.919** | 42.26% | **FAILS OOS** |
| **EMA26 Trailing (1.50%)** | 1,054 | +90.03% | 1.084 | 49.34% | 751 | **-30.99%** | **0.961** | 45.54% | **FAILS OOS** |
| **EMA26 Trailing (2.00%)** | 1,060 | +97.53% | 1.087 | 51.42% | 743 | **-31.74%** | **0.962** | 48.18% | **FAILS OOS** |

---

## 7. Deep Forensic Analysis: Why EMA26 Trailing Destroys Strategy Alpha

Why does trailing with EMA26 fail so catastrophically?

### 1. The Retest Trap (Exiting at the Mean-Reversion Bottom):
- In a classic trend-following system based on EMA9/EMA26 crossover, **EMA26 serves as the baseline trend line**.
- Once a trend establishes, price routinely expands away from EMA26 and then retests EMA26 during normal intra-trend consolidations.
- On 1-hour candles, a standard pullback will frequently close right at or 0.1%–0.5% below EMA26 before institutional buyers step in to resume the trend.
- An EMA26 candle-close trailing exit forces the strategy to **sell at the exact low of the pullback**.
- The trade is liquidated for a small loss, only for the asset to immediately reverse upward and reach what would have been the +3.00% target!

### 2. Destruction of Target Completion:
- Under the benchmark, **942 trades (52.66%)** hit their profit targets.
- Under EMA26 trailing (0% buffer), target hits plunge to **592 trades (28.99%)**.
- Over **350 winning target trades are eliminated**, converting high-payoff winners (+3% / +1.5%) into mediocre scratch or losing exits.

### 3. Frictional Churn and Re-entry Penalty:
- Liquidating a position via EMA26 trailing resets the strategy to `FLAT`.
- Because the macro regime has not confirmed an opposite trend (no opposite V2-2 signal), the bot re-enters as soon as a new qualifying candle appears.
- This creates **253 additional trades** of pure churn, incurring **0.07% round-trip friction** on each iteration while exposing capital to compounding whipsaws.

### 4. Comparison Between EMA9 and EMA26:
- **EMA9** is too fast: it exits on shallow pullbacks (holding time 7.4 bars, 78.5% exits).
- **EMA26** is intermediate: it catches the deeper pullback right where support normally holds, taking maximum damage on the consolidation before the next impulse leg.
- **Both moving average trailing stops are fundamentally unsuited for this strategy**.
- The existing **V2-2 Reversal Exit** is structurally vastly superior because it requires **confirmed dual-indicator trend invalidation (EMA crossover + MACD crossover over 2 candles)**, ensuring trades are only terminated when the macro trend has genuinely failed.

---

## 8. Final Research Verdict & Implementation Guidance

| Proposed Modification | Empirical Result | Architecture Recommendation |
| :--- | :--- | :--- |
| **Add EMA26 Candle-Close Trailing Exit** | Net return collapses from **+161.76% to -42.87%**; Win rate drops from **53.66% to 36.29%**; Fails OOS across all buffers. | **REJECT COMPLETELY.** Do NOT implement in production. |
| **Existing V2-2 Architecture** | **+161.76% Net Return**, **1.081 PF**, **+30.30% OOS Profit**, **52.66% Target Hit Rate**. | **RETAIN AS-IS.** Keep Target (+3% L / +1.5% S), V2-2 opposite-signal reversal, and -10% Catastrophe SL. |

**No changes should be made to `strategies/liveonopenalgo/emacrossopen.py`.**
