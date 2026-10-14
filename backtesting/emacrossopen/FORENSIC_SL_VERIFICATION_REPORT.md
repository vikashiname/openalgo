# Forensic Audit & Verification Report: Catastrophe Stop-Loss Comparison (-6%, -8%, -9%, -10%)
**Target System:** Exact Production Engine from `strategies/liveonopenalgo/emacrossopen.py`  
**Execution Context:** Isolated Research Workspace (`backtesting/emacrossopen/`)  
**Historical Period:** September 29, 2023 09:15 IST to September 09, 2026 12:15 IST (1,076 calendar days / 2.95 years)  
**Universe:** 33 High-Liquidity Indian NFO Derivatives (166,444 completed 1H bars)  
**Friction:** 0.07% round-trip | **Open Interest:** 0 synthetic OI  
**Safety Status:** Live strategy files (`strategies/liveonopenalgo/emacrossopen.py`, `macdfno.py`) completely unmodified (`git diff` clean: 0 diff).

---

## 1. Executive Summary & Verification of Forensic Integrity

This forensic evaluation was conducted to independently audit and re-run the comparative performance of **-6.00%**, **-8.00%**, **-9.00%**, and **-10.00%** Catastrophe Stop-Loss variants against the **No-SL** baseline, strictly adhering to the production logic of `emacrossopen.py`.

### Definitive Forensic Conclusions:

1. **Zero Execution-Order Artifact:**
   - At **-8.0%**, **-9.0%**, and **-10.0%**, there are **exactly zero instances** in the entire 3-year dataset where both Target (+3% L / +1.5% S) and Stop-Loss were breached within the same 1-hour candle.
   - An explicit invariance stress-test comparing `STRICT_SL_FIRST` against `TP_FIRST` yielded a **trade count difference of 0** and a **net return difference of 0.0000%**. The -10% result is **100% order-invariant**.

2. **Zero Lookahead Bias (Strict Causality):**
   - Indicator values (EMA9, EMA26, MACD, Signal) are strictly evaluated on completed candle $i$.
   - Entry orders are executed strictly at the opening price of candle $i+1$ (`open_px[i+1]`).
   - Risk management exits are evaluated on candle $i+1$ only after candle $i+1$ has fully completed.
   - All 1,789 trades exhibited valid, positive chronological durations ($exit\_time \ge entry\_time$, $bars\_held \ge 1$).

3. **Zero Overlapping Positions:**
   - The state machine maintains a strict integer position state per symbol: `pos \in {1, -1, 0}`.
   - Idempotent suppression prevents duplicate orders when in position.
   - Every single symbol exhibits strictly sequential non-overlapping trade intervals ($exit_k \le entry_{k+1}$). Overlapping trade violations = **0**.

4. **Forensic Cause of the -10.0% Outperformance vs -6.0% (+83.06% Return Delta):**
   - The outperformance is **NOT** an artifact. It is driven by two real market phenomena:
     - **Direct Trade Survival:** Out of 119 matched trades stopped out by -6.0%, **16.0% fully recovered to hit Profit Target** and **50.4% reversed via normal V2-2 reversal** at an average loss of -5.93% (vs -6.26% when stopped out), adding **+40.11%** in direct P&L.
     - **Chop Avoidance (Whipsaw Reduction):** In -6.0%, stopping out forces the bot into **FLAT**. While FLAT during volatile consolidation, the bot enters subsequent false signals, incurring **-42.95%** in cumulative whipsaw losses. In -10.0%, holding through temporary pullbacks completely bypasses those false re-entries.
     - **Short Squeeze Survival:** -6.0% fires directly into temporary short-squeeze spikes, turning Short trading negative (**-17.27%**). -10.0% survives the spikes, generating **+10.42% net profit** on Shorts (a **+27.69% directional swing**).

---

## 2. Master Comparison: -6%, -8%, -9%, -10% vs No-SL

All models operate with the production **Asymmetric Target (+3.00% Long / +1.50% Short)**, actual executed fill prices, completed 1H bars, and 0.07% friction:

| Stop-Loss Model | Trades | Win Rate (%) | Profit Factor | Expectancy (%) | Total Return (%) | CAGR (%) | Max DD (%) | Calmar | Target Hits (%) | SL Hits (%) | Reversals (%) | Avg Bars Held | Max Single Loss (%) | Worst 5 Avg (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **No-SL (Baseline)** | 1,774 | **53.95%** | **1.084** | **+0.0940%** | **+166.79%** | **39.53%** | 117.07% | 0.484 | 52.93% | 0.00% | 47.07% | 33.3 | -29.99% | -19.06% |
| **Fixed SL -6.0% (Current Live)** | 1,815 | 52.29% | 1.038 | +0.0434% | +78.71% | 21.78% | 127.67% | 0.209 | 51.24% | 7.05% | 41.71% | 27.1 | **-9.66%** | **-8.49%** |
| **Fixed SL -8.0%** | 1,798 | 53.17% | 1.046 | +0.0530% | +95.27% | 25.50% | **104.97%** | 0.308 | 52.11% | 4.45% | 43.44% | 29.1 | **-9.66%** | -9.01% |
| **Fixed SL -9.0%** | 1,794 | 53.51% | 1.068 | +0.0771% | +138.26% | 34.27% | 109.57% | 0.428 | 52.45% | 3.07% | 44.48% | 30.3 | -9.68% | -9.48% |
| **Fixed SL -10.0% (Recommended)**| 1,789 | **53.66%** | **1.081** | **+0.0904%** | **+161.76%** | **38.63%** | 116.20% | **0.473** | 52.66% | **2.29%** | 45.05% | 30.8 | **-10.65%** | **-10.36%** |

---

## 3. Directional Breakdown: LONG vs SHORT

| Variant | Direction | Trades | Win Rate (%) | Profit Factor | Expectancy (%) | Total Return (%) | Max DD (%) | Target Hit (%) | SL Hit (%) | Reversal (%) | Max Single Loss (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **No-SL** | **LONG** | 922 | 50.00% | 1.138 | +0.1783% | **+164.42%** | 99.67% | 48.16% | 0.00% | 51.84% | -29.99% |
| | **SHORT** | 852 | 58.22% | 1.003 | +0.0028% | **+2.37%** | 47.74% | 58.10% | 0.00% | 41.90% | -17.13% |
| **Fixed SL -6.0% (Live)**| **LONG** | 960 | 48.12% | 1.076 | +0.1000% | **+95.98%** | 118.95% | 46.25% | 9.58% | 44.17% | -9.66% |
| | **SHORT** | 855 | 56.96% | 0.978 | -0.0202% | **-17.27%** | 49.70% | 56.84% | 4.21% | 38.95% | -8.10% |
| **Fixed SL -8.0%** | **LONG** | 946 | 49.26% | 1.096 | +0.1274% | **+120.50%** | **87.88%** | 47.36% | 5.92% | 46.72% | -9.66% |
| | **SHORT** | 852 | 57.51% | 0.969 | -0.0296% | **-25.23%** | 55.91% | 57.39% | 2.82% | 39.79% | -9.36% |
| **Fixed SL -9.0%** | **LONG** | 940 | 49.68% | 1.127 | +0.1642% | **+154.37%** | 89.63% | 47.77% | 4.04% | 48.19% | -9.68% |
| | **SHORT** | 854 | 57.73% | 0.980 | -0.0189% | **-16.11%** | 61.83% | 57.61% | 1.99% | 40.40% | -9.36% |
| **Fixed SL -10.0%** | **LONG** | 939 | 49.73% | 1.124 | +0.1612% | **+151.35%** | 96.69% | 47.92% | 3.30% | 48.78% | -10.48% |
| | **SHORT** | 850 | **58.00%** | **1.013** | **+0.0123%** | **+10.42%** | **47.11%** | 57.88% | **1.18%** | 40.94% | -10.65% |

---

## 4. Year-by-Year Performance Analysis

### A. Rolling 12-Month Annual Breakdown
- **Year 1:** Sep 29, 2023 to Sep 28, 2024
- **Year 2:** Sep 29, 2024 to Sep 28, 2025
- **Year 3:** Sep 29, 2025 to Sep 09, 2026

| Stop-Loss Variant | Metric | Year 1 (Sep 23 - Sep 24) | Year 2 (Sep 24 - Sep 25) | Year 3 (Sep 25 - Sep 26) | Full 3-Year Total |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **No-SL** | **Trades** | 609 | 574 | 591 | **1,774** |
| | **Net Return (%)** | **+165.41%** | -18.71% | +20.09% | **+166.79%** |
| | **Profit Factor** | 1.260 | 0.972 | 1.030 | **1.084** |
| | **Win Rate (%)** | 56.49% | 52.96% | 52.28% | **53.95%** |
| | **Max DD (%)** | 43.28% | 88.30% | 69.65% | **117.07%** |
| **Fixed SL -6.0% (Live)**| **Trades** | 613 | 592 | 610 | **1,815** |
| | **Net Return (%)** | **+123.18%** | +10.63% | **-55.10%** | **+78.71%** |
| | **Profit Factor** | 1.189 | 1.016 | 0.926 | **1.038** |
| | **Win Rate (%)** | 54.16% | 52.03% | 50.66% | **52.29%** |
| | **SL Hits (Count / %)**| 41 (6.69%) | 41 (6.93%) | **46 (7.54%)** | **128 (7.05%)** |
| | **Max DD (%)** | 32.04% | 79.25% | 101.77% | **127.67%** |
| **Fixed SL -8.0%** | **Trades** | 609 | 589 | 600 | **1,798** |
| | **Net Return (%)** | **+137.82%** | -11.23% | -31.31% | **+95.27%** |
| | **Profit Factor** | 1.212 | 0.983 | 0.957 | **1.046** |
| | **Win Rate (%)** | 55.34% | 52.46% | 51.67% | **53.17%** |
| | **SL Hits (Count / %)**| 25 (4.11%) | 28 (4.75%) | 27 (4.50%) | **80 (4.45%)** |
| | **Max DD (%)** | 28.94% | 104.14% | 86.27% | **104.97%** |
| **Fixed SL -9.0%** | **Trades** | 610 | 585 | 599 | **1,794** |
| | **Net Return (%)** | **+165.94%** | +1.08% | -28.76% | **+138.26%** |
| | **Profit Factor** | 1.264 | 1.002 | 0.960 | **1.068** |
| | **Win Rate (%)** | 55.90% | 52.82% | 51.75% | **53.51%** |
| | **SL Hits (Count / %)**| 13 (2.13%) | 22 (3.76%) | 20 (3.34%) | **55 (3.07%)** |
| | **Max DD (%)** | 31.34% | 94.85% | 86.04% | **109.57%** |
| **Fixed SL -10.0%** | **Trades** | 609 | 583 | 597 | **1,789** |
| | **Net Return (%)** | **+177.61%** | -11.33% | **-4.52%** | **+161.76%** |
| | **Profit Factor** | **1.286** | 0.983 | **0.994** | **1.081** |
| | **Win Rate (%)** | **56.16%** | 52.66% | **52.09%** | **53.66%** |
| | **SL Hits (Count / %)**| 10 (1.64%) | 19 (3.26%) | **12 (2.01%)** | **41 (2.29%)** |
| | **Max DD (%)** | 30.58% | 99.55% | 91.43% | **116.20%** |

### B. Calendar Year Breakdown
| Variant | Calendar Year | Trades | Win Rate (%) | Profit Factor | Total Return (%) | Max DD (%) | SL Hits (Count / %) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Fixed SL -6.0% (Live)**| **2023 (Q4)** | 131 | 54.96% | 1.434 | **+50.60%** | 15.76% | 6 (4.58%) |
| | **2024** | 628 | 54.30% | 1.097 | **+66.99%** | 39.08% | 47 (7.48%) |
| | **2025** | 623 | 49.28% | 1.024 | **+16.63%** | 78.71% | 40 (6.42%) |
| | **2026 (YTD)** | 433 | 52.89% | 0.901 | **-55.51%** | 101.59% | 35 (8.08%) |
| **Fixed SL -10.0%** | **2023 (Q4)** | 130 | 56.15% | 1.575 | **+62.11%** | 18.06% | 1 (0.77%) |
| | **2024** | 624 | 56.25% | 1.133 | **+91.63%** | 39.77% | 16 (2.56%) |
| | **2025** | 608 | 49.67% | 1.018 | **+11.95%** | 89.74% | 15 (2.47%) |
| | **2026 (YTD)** | 427 | 54.80% | 0.992 | **-3.92%** | 58.70% | 9 (2.11%) |

---

## 5. In-Sample vs Out-of-Sample Walk-Forward Results

Partition: **In-Sample (IS)** = Sep 29, 2023 to Jun 30, 2025 (21 months, ~60% of data) vs **Out-of-Sample (OOS)** = Jul 01, 2025 to Sep 09, 2026 (14.5 months, ~40% of data).

| Variant | Sample | Trades | Win Rate (%) | Profit Factor | Expectancy (%) | Total Return (%) | Max DD (%) | SL Hits (Count / %) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **No-SL** | **IS** | 1,048 | 55.15% | 1.100 | +0.1131% | **+118.55%** | 73.43% | 0 (0.00%) |
| | **OOS** | 726 | 52.20% | 1.061 | +0.0664% | **+48.24%** | 79.37% | 0 (0.00%) |
| **Fixed SL -6.0% (Live)**| **IS** | 1,064 | 53.29% | 1.093 | +0.1024% | **+108.92%** | 66.80% | 74 (6.95%) |
| | **OOS** | 751 | 50.87% | 0.966 | -0.0402% | **-30.21%** | 90.38% | 54 (7.19%) |
| **Fixed SL -8.0%** | **IS** | 1,059 | 54.11% | 1.077 | +0.0877% | **+92.93%** | 73.63% | 50 (4.72%) |
| | **OOS** | 739 | 51.83% | 1.003 | +0.0032% | **+2.35%** | 90.58% | 30 (4.06%) |
| **Fixed SL -9.0%** | **IS** | 1,057 | 54.59% | 1.108 | +0.1204% | **+127.24%** | 68.99% | 33 (3.12%) |
| | **OOS** | 737 | 51.97% | 1.013 | +0.0150% | **+11.02%** | 87.96% | 22 (2.99%) |
| **Fixed SL -10.0%** | **IS** | 1,056 | 54.73% | 1.112 | +0.1245% | **+131.46%** | 77.22% | 27 (2.56%) |
| | **OOS** | 733 | 52.11% | **1.037** | **+0.0413%** | **+30.30%** | 94.35% | 14 (1.91%) |

---

## 6. Maximum Adverse Excursion (MAE) Distribution

The table below classifies the maximum intra-trade drawdown experienced by every trade across its entire lifecycle:

| Variant | Total Trades | MAE < 2.0% | MAE 2.0% - 4.0% | MAE 4.0% - 6.0% | MAE 6.0% - 8.0% | MAE 8.0% - 10.0% | MAE $\ge$ 10.0% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **No-SL** | 1,774 | **68.32%** | **19.00%** | **6.03%** | 2.54% | 1.92% | **2.20%** |
| **Fixed SL -6.0%** | 1,815 | 67.88% | 18.84% | 6.23% | 5.95% | 0.94% | 0.17% |
| **Fixed SL -8.0%** | 1,798 | 68.02% | 18.85% | 6.12% | 2.56% | 4.06% | 0.39% |
| **Fixed SL -9.0%** | 1,794 | 68.06% | 18.90% | 6.13% | 2.56% | 3.62% | 0.72% |
| **Fixed SL -10.0%**| 1,789 | 68.03% | 19.01% | 6.09% | 2.63% | 1.96% | **2.29%** |

### Critical Distribution Facts:
- **93.35% of all strategy trades never experience an MAE exceeding 6.0%.**
- Only **6.65% of trades** ever cross -6.0% adverse excursion.
- Only **2.20% of trades (39 trades out of 1,774)** ever cross -10.0% adverse excursion.
- At **-6.0%**, the stop fires on 128 trades, stopping out normal market retracements and volatile short squeezes.
- At **-10.0%**, the stop fires on exactly **41 trades**, cleanly eliminating the dangerous tail without interfering with the 97.7% core distribution.

---

## 7. Forensic Verification Proof: Auditing Artifacts & Lookahead

Four automated forensic tests were executed to rigorously confirm that the -10.0% result is free of any modeling defects:

### Test 1: Intrabar Execution-Order Invariance Test
- **Methodology:** Ran the entire simulation under two opposite priority extremes for same-bar simultaneous breaches:
  1. `STRICT_SL_FIRST`: If high $\ge$ target and low $\le$ stop in the same bar, force `CATASTROPHE_SL`.
  2. `TP_FIRST`: If high $\ge$ target and low $\le$ stop in the same bar, force `TARGET_HIT`.
- **Result:**
  - Trade Count Difference: **0**
  - Total Return Difference: **0.0000%**
- **Root Cause:** A 1-hour candle on these 33 liquid NFO instruments practically never spans a 13.0% range (+3% target to -10% stop). There are **zero same-candle collisions**. The result is 100% immune to execution-order assumptions.

### Test 2: Overlapping Position & Concurrency Audit
- **Methodology:** For all 33 symbols, verified that every subsequent trade entered at or after the previous trade's exit timestamp ($entry\_time_{k+1} \ge exit\_time_k$).
- **Result:** Overlapping violations detected: **0**. Zero multi-position stacking exists.

### Test 3: Lookahead & Causality Audit
- **Methodology:** Audited trade timestamps and bar indices to verify that no trade was entered before its signal candle closed and no exit occurred prior to entry.
- **Result:** Time-travel violations: **0**. Inverted duration violations: **0**. All indicators are calculated on completed bars only.

### Test 4: Direct Trade-by-Trade Forensic Trace
- **Methodology:** Matched identical trade entries between the -6.0% and -10.0% engines. Traced the fate of all 119 matched trades that were stopped out in -6.0%:
  - **19 trades (16.0%)** fully recovered and hit `TARGET_HIT` (+3% L / +1.5% S).
  - **60 trades (50.4%)** reversed via `V2-2_REVERSAL` at an average loss of -5.93% (smaller than the stop-loss).
  - **40 trades (33.6%)** continued dropping and exited via `CATASTROPHE_SL` at -10%.
  - Net direct P&L improvement: **+40.11%**.
  - Remaining +42.95% delta came from **avoiding whipsaws**: in -6.0%, being stopped out forced the bot into FLAT, causing it to take repeated losing re-entries during consolidation chop.

---

## 8. Summary Comparison Table

| Evaluation Criterion | Fixed SL -6.00% (Current Live) | Fixed SL -8.00% | Fixed SL -9.00% | Fixed SL -10.00% (Recommended) |
| :--- | :---: | :---: | :---: | :---: |
| **Total Net Return** | +78.71% | +95.27% | +138.26% | **+161.76%** |
| **Profit Factor** | 1.038 | 1.046 | 1.068 | **1.081** |
| **Win Rate** | 52.29% | 53.17% | 53.51% | **53.66%** |
| **Expectancy / Trade** | +0.0434% | +0.0530% | +0.0771% | **+0.0904%** |
| **Max Drawdown** | 127.67% | **104.97%** | 109.57% | 116.20% |
| **Calmar Ratio** | 0.209 | 0.308 | 0.428 | **0.473** |
| **LONG Return** | +95.98% | +120.50% | +154.37% | **+151.35%** |
| **SHORT Return** | **-17.27%** | **-25.23%** | **-16.11%** | **+10.42%** |
| **Year 1 Return** | +123.18% | +137.82% | +165.94% | **+177.61%** |
| **Year 2 Return** | +10.63% | -11.23% | +1.08% | -11.33% |
| **Year 3 Return** | **-55.10%** | -31.31% | -28.76% | **-4.52%** |
| **OOS Return (14.5m)** | **-30.21%** | **+2.35%** | **+11.02%** | **+30.30%** |
| **SL Hits (%)** | 7.05% (128 trades) | 4.45% (80 trades) | 3.07% (55 trades) | **2.29% (41 trades)** |
| **Max Single Loss** | **-9.66%** | **-9.66%** | -9.68% | **-10.65%** |
| **Disaster Protection** | Eliminates -30% tail | Eliminates -30% tail | Eliminates -30% tail | Eliminates -30% tail |
