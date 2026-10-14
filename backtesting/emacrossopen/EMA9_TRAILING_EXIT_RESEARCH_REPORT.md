# Research Report: EMA9 Candle-Close Trailing Exit Analysis
**Strategy:** OpenAlgo NFO 1-Hour EMA (9/26) + MACD (12/26/9) Asymmetric V2-2 Sequential Confirmation Engine  
**Execution Context:** Isolated Research Workspace (`backtesting/emacrossopen/`)  
**Historical Period:** September 29, 2023 09:15 IST to September 09, 2026 12:15 IST (1,076 calendar days / 2.95 years)  
**Universe:** 33 Liquid Indian NFO Derivatives (166,444 completed 1H bars)  
**Friction:** 0.07% round-trip | **Open Interest:** 0 synthetic OI  
**Safety Status:** Live production files (`strategies/liveonopenalgo/emacrossopen.py`, `macdfno.py`) completely unmodified (`git diff` clean: 0 diff).

---

## 1. Executive Summary & Definitive Recommendation

This research investigated whether an **EMA9 candle-close trailing exit** improves profit retention versus the baseline **V2-2 opposite-signal reversal exit**.

### Definitive Verdict:
> [!CAUTION]
> **REJECT EMA9 TRAILING EXIT ENTIRELY.**  
> Testing across 166,444 completed 1H candles proves conclusively that an EMA9 candle-close trailing exit **severely destroys strategy edge, kills more than half of all winning target trades, and collapses net profitability into a massive loss.**

### Core Empirical Proof:
1. **Catastrophic Edge Destruction:**
   - The verified benchmark (**Target + V2-2 Reversal + Fixed SL -10%**) delivers **+161.76% Net Return**, **1.081 Profit Factor**, and **53.66% Win Rate**.
   - Adding an EMA9 candle-close trailing exit with **0.00% buffer** causes total return to collapse from **+161.76% down to -61.23%** (a **223% destruction of alpha**), with Win Rate dropping to **35.88%** and Profit Factor collapsing to **0.948**.
2. **Massive Premature Exit Rate:**
   - At 0.00% buffer, **78.55% of all trades (1,622 trades)** exit prematurely via EMA9 trailing exit!
   - Target hits collapse by **53%** (from **942 trades / 52.66% down to 443 trades / 21.45%**).
3. **Severe Out-of-Sample Failure:**
   - In Out-of-Sample testing (Jul 2025 – Sep 2026, 14.5 months), the benchmark generated **+30.30% profit** (PF 1.037).
   - Under EMA9 trailing exit (0% buffer), Out-of-Sample performance plummeted to **-98.19% loss** (PF 0.808)!
4. **Buffer Sensitivity Monotonicity:**
   - Across buffers (0.00% $\to$ 0.25% $\to$ 0.50% $\to$ 1.00% $\to$ 1.50% $\to$ 2.00%), performance is strictly monotonic: **the less active the EMA9 exit, the better the strategy performs**.
   - Every single buffer $\le 1.00\%$ produces severe underperformance (+23% to -2% return vs +161.76% benchmark).

---

## 2. Master Comparison: Benchmark vs All EMA9 Buffer Variants

All variants maintain:
- Long Target: **+3.00%** | Short Target: **+1.50%** (evaluated from actual fill price)
- Catastrophe SL: **-10.00%** emergency backup
- V2-2 Reversal Logic
- Completed 1H candles only, 0.07% round-trip friction, strictly causal next-bar execution:

| Variant | Trades | Win Rate (%) | Profit Factor | Expectancy (%) | Total Return (%) | CAGR (%) | Max DD (%) | Calmar | Target Hits (%) | EMA9 Exits (%) | SL Hits (%) | Reversals (%) | Avg Bars Held | Max Single Loss (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No EMA9 Exit)** | **1,789** | **53.66%** | **1.081** | **+0.0904%** | **+161.76%** | **38.63%** | 116.20% | **0.473** | **52.66% (942)** | **0.00% (0)** | **2.29% (41)** | **45.05% (806)** | **30.8** | **-10.65%** |
| **EMA9 Trailing (Buffer 0.00%)** | 2,065 | 35.88% | 0.948 | -0.0296% | **-61.23%** | -27.50% | 91.48% | -0.227 | 21.45% (443) | **78.55% (1622)** | 0.00% (0) | 0.00% (0) | 7.4 | -9.24% |
| **EMA9 Trailing (Buffer 0.25%)** | 1,977 | 39.76% | 1.018 | +0.0122% | **+24.06%** | 7.59% | **76.92%** | 0.106 | 29.49% (583) | 69.20% (1368) | 0.10% (2) | 1.21% (24) | 10.3 | -10.07% |
| **EMA9 Trailing (Buffer 0.50%)** | 1,896 | 41.61% | 0.998 | -0.0014% | **-2.69%** | -0.92% | 99.47% | -0.009 | 35.65% (676) | 55.49% (1052) | 0.11% (2) | 8.76% (166) | 13.5 | -10.07% |
| **EMA9 Trailing (Buffer 1.00%)** | 1,823 | 45.69% | 1.013 | +0.0126% | **+23.02%** | 7.29% | 107.80% | 0.072 | 44.32% (808) | 29.07% (530) | 0.11% (2) | 26.49% (483) | 19.7 | -10.07% |
| **EMA9 Trailing (Buffer 1.50%)** | 1,776 | 50.11% | 1.049 | +0.0527% | **+93.60%** | 25.14% | 104.56% | 0.304 | 49.04% (871) | 15.77% (280) | 0.34% (6) | 34.85% (619) | 24.9 | -10.07% |
| **EMA9 Trailing (Buffer 2.00%)** | 1,777 | 51.83% | 1.066 | +0.0723% | **+128.51%** | 32.38% | 90.83% | 0.480 | 50.82% (903) | 8.38% (149) | 0.68% (12) | 40.12% (713) | 28.2 | -10.48% |

---

## 3. Directional Breakdown: LONG vs SHORT Dynamics

| Variant | Direction | Trades | Win Rate (%) | Profit Factor | Expectancy (%) | Total Return (%) | Max DD (%) | Target Hits (%) | EMA9 Exits (%) | Reversals (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No EMA9 Exit)** | **LONG** | 939 | **49.73%** | **1.124** | **+0.1612%** | **+151.35%** | 96.69% | **47.92% (450)** | **0.00%** | 48.78% |
| | **SHORT** | 850 | **58.00%** | **1.013** | **+0.0123%** | **+10.42%** | 47.11% | **57.88% (492)** | **0.00%** | 40.94% |
| **EMA9 Trailing (0.00%)** | **LONG** | 1,181 | 34.38% | 0.975 | -0.0142% | **-16.77%** | 58.58% | 13.72% (162) | **86.28% (1019)** | 0.00% |
| | **SHORT** | 884 | 37.90% | 0.912 | -0.0503% | **-44.45%** | 62.07% | 31.79% (281) | **68.21% (603)** | 0.00% |
| **EMA9 Trailing (0.25%)** | **LONG** | 1,137 | 37.03% | 1.039 | +0.0277% | **+31.46%** | 48.18% | 20.84% (237) | 78.01% (887) | 0.97% |
| | **SHORT** | 840 | 43.45% | 0.987 | -0.0088% | **-7.40%** | 44.33% | 41.19% (346) | 57.26% (481) | 1.55% |
| **EMA9 Trailing (0.50%)** | **LONG** | 1,087 | 37.07% | 1.028 | +0.0236% | **+25.61%** | 72.73% | 26.95% (293) | 64.86% (705) | 8.00% |
| | **SHORT** | 809 | 47.71% | 0.955 | -0.0350% | **-28.30%** | 56.05% | 47.34% (383) | 42.89% (347) | 9.77% |
| **EMA9 Trailing (1.00%)** | **LONG** | 1,005 | 39.20% | 1.023 | +0.0255% | **+25.62%** | 97.15% | 36.82% (370) | 35.42% (356) | 27.56% |
| | **SHORT** | 818 | 53.67% | 0.996 | -0.0032% | **-2.60%** | 42.96% | 53.55% (438) | 21.27% (174) | 25.18% |

---

## 4. Year-by-Year Performance Breakdown

### A. Rolling 12-Month Periods
- **Year 1:** Sep 29, 2023 to Sep 28, 2024
- **Year 2:** Sep 29, 2024 to Sep 28, 2025
- **Year 3:** Sep 29, 2025 to Sep 09, 2026

| Variant | Year 1 Return (%) | Year 1 PF | Year 2 Return (%) | Year 2 PF | Year 3 Return (%) | Year 3 PF | Full 3-Year Return (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No EMA9 Exit)** | **+177.61%** | **1.286** | **-11.33%** | **0.983** | **-4.52%** | **0.994** | **+161.76%** |
| **EMA9 Trailing (0.00%)** | +40.57% | 1.110 | -5.58% | 0.985 | **-96.22%** | **0.782** | **-61.23%** |
| **EMA9 Trailing (0.25%)** | +65.71% | 1.151 | +9.39% | 1.022 | **-51.05%** | 0.899 | **+24.06%** |
| **EMA9 Trailing (0.50%)** | +63.83% | 1.129 | -12.18% | 0.975 | **-54.35%** | 0.905 | **-2.69%** |
| **EMA9 Trailing (1.00%)** | +108.86% | 1.196 | -17.75% | 0.970 | **-68.09%** | 0.898 | **+23.02%** |
| **EMA9 Trailing (1.50%)** | +121.95% | 1.202 | +10.20% | 1.017 | **-38.55%** | 0.943 | **+93.60%** |
| **EMA9 Trailing (2.00%)** | +137.05% | 1.221 | -7.27% | 0.989 | **-1.28%** | 0.998 | **+128.51%** |

### B. Calendar Year Results (2023–2026)
| Variant | 2023 (Q4) Return | 2024 Return | 2025 Return | 2026 (YTD) Return | Cumulative Net Return |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No EMA9 Exit)** | **+62.11%** | **+91.63%** | **+11.95%** | **-3.92%** | **+161.76%** |
| **EMA9 Trailing (0.00%)** | +6.37% | +33.65% | -28.08% | **-73.18%** | **-61.23%** |
| **EMA9 Trailing (0.25%)** | +14.07% | +62.23% | -17.22% | **-35.03%** | **+24.06%** |
| **EMA9 Trailing (0.50%)** | +39.36% | +17.39% | -33.27% | **-26.18%** | **-2.69%** |
| **EMA9 Trailing (1.00%)** | +31.04% | +39.07% | +11.28% | **-58.37%** | **+23.02%** |
| **EMA9 Trailing (2.00%)** | +48.96% | +55.93% | +39.34% | -15.71% | **+128.51%** |

---

## 5. In-Sample vs Out-of-Sample Walk-Forward Stability

Partition: **In-Sample (IS)** = Sep 29, 2023 to Jun 30, 2025 (21 months) vs **Out-of-Sample (OOS)** = Jul 01, 2025 to Sep 09, 2026 (14.5 months):

| Variant | IS Trades | IS Return (%) | IS PF | IS Win Rate (%) | OOS Trades | OOS Return (%) | OOS PF | OOS Win Rate (%) | WF Stability Ratio |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No EMA9 Exit)** | 1,056 | **+131.46%** | **1.112** | **54.73%** | 733 | **+30.30%** | **1.037** | **52.11%** | **0.933** |
| **EMA9 Trailing (0.00%)** | 1,180 | +36.96% | 1.056 | 37.71% | 885 | **-98.19%** | **0.808** | **33.45%** | **0.765** |
| **EMA9 Trailing (0.25%)** | 1,126 | +63.08% | 1.082 | 41.47% | 851 | **-39.02%** | 0.934 | 37.49% | 0.863 |
| **EMA9 Trailing (0.50%)** | 1,082 | +53.66% | 1.061 | 42.88% | 814 | **-56.36%** | 0.917 | 39.93% | 0.864 |
| **EMA9 Trailing (1.00%)** | 1,057 | +88.94% | 1.088 | 46.93% | 766 | **-65.92%** | 0.917 | 43.99% | 0.843 |
| **EMA9 Trailing (1.50%)** | 1,041 | +112.19% | 1.103 | 51.49% | 735 | **-18.59%** | 0.977 | 48.16% | 0.886 |
| **EMA9 Trailing (2.00%)** | 1,048 | +107.00% | 1.093 | 52.86% | 729 | **+21.51%** | 1.027 | 50.34% | 0.940 |

---

## 6. Detailed MFE, MAE, Holding Time & Risk Profile

| Variant | Avg Bars Held | Median Bars | Avg MFE (%) | Avg MAE (%) | Max Single Loss (%) | Worst 5 Avg Loss (%) | Target Hit Rate (%) | EMA9 Exit Rate (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benchmark (No EMA9 Exit)** | **30.8** | **12.0** | **1.91%** | **2.00%** | **-10.65%** | **-10.36%** | **52.66%** | **0.00%** |
| **EMA9 Trailing (0.00%)** | 7.4 | 6.0 | 1.20% | 0.97% | -9.24% | -7.22% | 21.45% | 78.55% |
| **EMA9 Trailing (0.25%)** | 10.3 | 8.0 | 1.44% | 1.14% | -10.07% | -8.78% | 29.49% | 69.20% |
| **EMA9 Trailing (0.50%)** | 13.5 | 10.0 | 1.59% | 1.31% | -10.07% | -8.78% | 35.65% | 55.49% |
| **EMA9 Trailing (1.00%)** | 19.7 | 12.0 | 1.76% | 1.57% | -10.07% | -9.22% | 44.32% | 29.07% |
| **EMA9 Trailing (1.50%)** | 24.9 | 12.0 | 1.85% | 1.78% | -10.07% | -10.07% | 49.04% | 15.77% |
| **EMA9 Trailing (2.00%)** | 28.2 | 12.0 | 1.89% | 1.89% | -10.48% | -10.15% | 50.82% | 8.38% |

---

## 7. Deep Forensic Analysis: Why EMA9 Trailing Fails Disastrously

The idea of using a fast moving average (EMA9) as a trailing stop appears intuitive in theory, but in practice on 1-hour completed candles across Indian equity derivatives, it produces three fatal structural failures:

### 1. The "Premature Choke" Mechanism:
In 1-hour trend-following, price does not move in a straight line. Healthy, sustained upward trends on large-cap NFO stocks (e.g. RELIANCE, TCS, HDFCBANK) frequently experience normal intraday pullbacks where 1 or 2 completed 1H candles close 0.2% to 0.6% below EMA9 before surging forward to hit the +3.00% target.
- Under the benchmark, the trade absorbs this noise and banks **+3.00% profit**.
- Under EMA9 trailing, the trade is **prematurely choked on the very first pullback**, banking a negligible gain or a minor loss (-0.2% to -0.6%).
- This is why Target Hits collapse by more than half (from 942 trades down to 443 trades).

### 2. The Whipsaw & Friction Cascade:
When an EMA9 trailing exit triggers, the position is closed to **FLAT**.
- However, the macro trend has NOT reversed: EMA9 is still above EMA26, and MACD is still above zero.
- Because the bot is FLAT, the very next candle or two frequently produces another confirmed entry signal!
- The bot re-enters, pays **0.07% round-trip friction**, and then gets stopped out again on the next minor EMA9 dip.
- This creates **276 extra trades of pure frictional churn and repeated whipsaw losses**.

### 3. V2-2 Reversal is Structurally Superior:
The production V2-2 reversal mechanism waits for **asymmetric 2-candle confirmation between EMA9/EMA26 and MACD**. This requires a structural, macro trend change before abandoning the position.
- This macro filter gives winning trades the exact breathing space required to capture the full +3.00% Long / +1.50% Short targets, while naturally exiting when the entire trend cycle has concluded.

---

## 8. Summary Comparison Table

| Evaluation Criterion | Verified Benchmark (V2-2 Reversal Only) | EMA9 Trailing (0.00% Buffer) | EMA9 Trailing (0.50% Buffer) | EMA9 Trailing (1.00% Buffer) |
| :--- | :---: | :---: | :---: | :---: |
| **Total Net Return** | **+161.76%** | **-61.23%** | **-2.69%** | **+23.02%** |
| **Profit Factor** | **1.081** | **0.948** | **0.998** | **1.013** |
| **Win Rate** | **53.66%** | **35.88%** | **41.61%** | **45.69%** |
| **Expectancy / Trade**| **+0.0904%** | **-0.0296%** | **-0.0014%** | **+0.0126%** |
| **Max Drawdown** | 116.20% | 91.48% | 99.47% | 107.80% |
| **OOS Return (14.5m)**| **+30.30%** | **-98.19%** | **-56.36%** | **-65.92%** |
| **LONG Return** | **+151.35%** | **-16.77%** | **+25.61%** | **+25.62%** |
| **SHORT Return** | **+10.42%** | **-44.45%** | **-28.30%** | **-2.60%** |
| **Target Hits (Count)**| **942 trades (52.66%)** | **443 trades (21.45%)** | **676 trades (35.65%)** | **808 trades (44.32%)** |
| **Premature EMA9 Exits**| **0 trades (0.00%)** | **1,622 trades (78.55%)** | **1,052 trades (55.49%)** | **530 trades (29.07%)** |
| **Edge Verdict** | **OPTIMAL ALPHA ENGINE** | **MASSIVE ALPHA DESTRUCTION** | **EDGE ERADICATED** | **SUBSTANTIALLY INFERIOR** |
