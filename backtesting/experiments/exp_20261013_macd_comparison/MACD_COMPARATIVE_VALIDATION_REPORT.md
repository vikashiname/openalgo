# INDEPENDENT RESEARCH AUDIT: MACD STRATEGY COMPARATIVE VALIDATION
**Run Directory:** `backtesting/experiments/exp_20261013_macd_comparison/`  
**Execution Timestamp:** 2026-10-13 21:46 IST  
**Environment:** 100% Isolated Offline Research Harness (Read-Only Operational Integrity Maintained)  
**Safety Status:** ZERO Live Changes, ZERO Broker Orders, Baseline Files Untouched on Git HEAD  

---

## 1. Executive Summary & Verification Verdict

We conducted a controlled, reproducible quantitative evaluation comparing the four independent strategy candidates across 33 liquid NSE F&O instruments (5,039 completed 1-Hour candles per instrument, spanning September 2023 to September 2026):

1. **Candidate 1: MACD_FNO_V1 Baseline** (`strategies/liveonopenalgo/macdfno.py`): MACD 12/26/9 + 2-bar histogram expansion, 3% Long TP / 1.5% Short TP / 3.5% Catastrophe SL, reversal exit.
2. **Candidate 2: EMA/MACD V2-2** (`backtesting/emacrossopen/`): Researched EMA 9/26 + MACD 12/26/9 sequential confirmation (≤ 2 candles), 3% Long TP / 1.5% Short TP / 6% Catastrophe SL, next-candle open execution.
3. **Candidate 3: Model B / Preset A** (`backtesting/reports/macdfno_sl_target_optimization_report.md`): Reported +1.50% Target / -1.50% Stop-Loss on MACD 12/26/9.
4. **Candidate 4: Candidate E / Preset B** (`backtesting/macdfno/baseline/test_macd_universe_and_runners.py`): Reported +3.0% Long / +1.5% Short Target, -3.5% Catastrophe SL, 0.35% HWM trailing runner, restricted to asymmetric universe (`TOP_LONGS` / `TOP_SHORTS`).

---

### Key Verification Verdicts by Candidate

| Candidate | Previously Claimed Metric | Independently Verified Metric (Native Universe) | Verified Metric (Common 33 Universe) | Reproducibility Classification | Primary Failure Mode / Finding |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **Candidate 1: MACD Baseline** | Baseline Reference | **PF 0.968** \| Net: -222.41% \| DD: 343.48% (9,288 trades) | **PF 0.968** \| Net: -222.41% | ✅ **Reproduced** | High churn, whipsaws on choppy large caps, severe exit lag on 1H reversals. |
| **Candidate 2: EMA/MACD V2-2** | Research Candidate (PF ~1.39 - 1.82 reported in EXP_J/EXP_I) | **PF 0.936** \| Net: -135.66% \| DD: 187.50% (1,867 trades) | **PF 0.936** \| Net: -135.66% | ⚠️ **Partially Reproduced** | Raw V2-2 sequential entry without macro regime filter or trailing runners bleeds money; requires full multi-filter stack. |
| **Candidate 3: Model B (Preset A)** | Claimed: **PF 1.34–1.35**, Holdout: **1.33**, Net: **+684.0%** (4,007 trades) | **PF 0.927** \| Net: -162.91% \| DD: 173.40% (3,332 trades on Core 15) | **PF 0.889** \| Net: -673.83% (9,341 trades) | ❌ **Not Reproduced (Critical Accounting Defect)** | Historical report used optimistic bar-level MFE/MAE overlay assuming target hits occurred before stop hits on ambiguous candles. Sequential path evaluation triggers stop shakes. |
| **Candidate 4: Candidate E (Preset B)** | Claimed: **PF 1.581**, Holdout: **1.462**, Net: **+672.66%** | **PF 1.211** \| Net: **+315.73%** \| DD: **50.05%** (1,588 trades) | **PF 1.200** \| Net: **+1411.35%** (9,276 trades) | ⚠️ **Partially Reproduced** | Produces robust positive edge above 1.20 PF across both In-Sample and Holdout; however, claimed 1.58 PF was overfitted to intrabar runner assumptions. Lookahead-free runner yields PF 1.211. |

---

## 2. Controlled Candidate-by-Candidate Comparison Table

All four strategies evaluated under identical 0.07% round-trip friction, completed-candle rule, and chronological ordering.

### A. Native Universe Performance
| Candidate | Universe Scope | Trades | Win Rate (%) | Net Return (%) | Profit Factor | Expectancy (%) | Max DD (%) | 2026 Holdout PF |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. MACD_FNO_V1 Baseline** | Native Universe | 9,288 | 44.90% | -222.41% | **0.968** | -0.024% | 343.48% | **0.866** |
| **2. EMA_MACD_V2_2** | Native Universe | 1,867 | 50.51% | -135.66% | **0.936** | -0.073% | 187.50% | **0.909** |
| **3. Model B (Preset A)** | Native Universe | 3,332 | 45.50% | -162.91% | **0.927** | -0.049% | 173.40% | **0.915** |
| **4. Candidate E (Preset B)** | Native Universe | 1,588 | 48.61% | +315.73% | **1.211** | +0.199% | 50.05% | **1.218** |

### B. Common Comparison Universe (All 33 Liquid Symbols)
| Candidate | Universe Scope | Trades | Win Rate (%) | Net Return (%) | Profit Factor | Expectancy (%) | Max DD (%) | 2026 Holdout PF |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. MACD_FNO_V1 Baseline** | Common 33 | 9,288 | 44.90% | -222.41% | **0.968** | -0.024% | 343.48% | **0.866** |
| **2. EMA_MACD_V2_2** | Common 33 | 1,867 | 50.51% | -135.66% | **0.936** | -0.073% | 187.50% | **0.909** |
| **3. Model B (Preset A)** | Common 33 | 9,341 | 43.23% | -673.83% | **0.889** | -0.072% | 686.90% | **0.858** |
| **4. Candidate E (Preset B)** | Common 33 | 9,276 | 44.77% | +1411.35% | **1.200** | +0.152% | 124.89% | **1.113** |

### C. Common Comparison Universe (15 Core Liquid Leaders)
| Candidate | Universe Scope | Trades | Win Rate (%) | Net Return (%) | Profit Factor | Expectancy (%) | Max DD (%) | 2026 Holdout PF |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. MACD_FNO_V1 Baseline** | Core 15 | 3,324 | 47.50% | +34.79% | **1.013** | +0.010% | 86.84% | **0.961** |
| **2. EMA_MACD_V2_2** | Core 15 | 655 | 50.84% | -116.75% | **0.859** | -0.178% | 162.75% | **1.036** |
| **3. Model B (Preset A)** | Core 15 | 3,332 | 45.50% | -162.91% | **0.927** | -0.049% | 173.40% | **0.915** |
| **4. Candidate E (Preset B)** | Core 15 | 3,319 | 47.36% | +776.97% | **1.293** | +0.234% | 55.41% | **1.249** |

---

## 3. Discrepancy Forensic Analysis: Why Model B Failed to Reproduce

### Finding 1: The Model B / Preset A MFE/MAE Accounting Flaw
In the original research report (`macdfno_sl_target_optimization_report.md`), Model B claimed:
- **Win Rate:** 56.4%
- **Profit Factor:** 1.34 (IS: 1.35, OOS: 1.33)
- **Net Cumulative:** +684.0%

When executed sequentially bar-by-bar using actual candle highs, lows, and closes:
- **Total Trades:** 3,332
- **Win Rate:** 45.5%
- **Profit Factor:** **0.927** (Losing)
- **Net Cumulative:** **-162.91%**

**Root Cause Forensic:**
The original MFE/MAE script analyzed closed baseline trades from an unmanaged crossover strategy and asked: *"Did this trade ever touch +1.50% MFE?"* and *"Did this trade ever touch -1.50% MAE?"*
1. In reality, **74.5% of trades reach -1.00% to -1.50% adverse excursion early in their trade life** (during initial entry noise).
2. When a fixed -1.50% stop loss is evaluated in chronological order, positions hit their stop loss and exit **before** price has an opportunity to rally to the +1.50% profit target!
3. The previous report assumed independent probabilities, effectively giving the strategy credit for hitting +1.50% even if price had already breached -1.50% earlier in the trade.
4. **Conclusion:** Model B (+1.50% TP / -1.50% SL) is **not viable** in real sequential trading without a wider catastrophe stop or trailing threshold.

---

## 4. Friction Cost Sensitivity Analysis

Evaluating resilience across transaction costs (0.05% to 0.15% round-trip):

| Round-Trip Friction (%) | C1 Baseline PF | C2 EMA/MACD PF | C3 Model B PF | C4 Candidate E PF | C4 Net P&L (%) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **0.05%** | 0.995 | 0.953 | 0.956 | **1.234** | **+347.49%** |
| **0.07%** | 0.968 | 0.936 | 0.927 | **1.211** | **+315.73%** |
| **0.10%** | 0.930 | 0.910 | 0.885 | **1.176** | **+268.09%** |
| **0.12%** | 0.906 | 0.894 | 0.858 | **1.154** | **+236.33%** |
| **0.15%** | 0.871 | 0.870 | 0.819 | **1.121** | **+188.69%** |

**Resilience Finding:**
- Only **Candidate E (Preset B)** maintains a Profit Factor > 1.0 under all friction regimes, remaining profitable at **PF 1.121** even under extreme 0.15% friction stress.
- All other candidates bleed heavily into negative expectancy as friction increases.

---

## 5. Directional Long vs Short Performance Breakdown

| Candidate | Long Trades | Long Net (%) | Long PF | Long WR (%) | Short Trades | Short Net (%) | Short PF | Short WR (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Candidate 1 (Baseline)** | 4,600 | +175.17% | 1.049 | 41.0% | 4,688 | -397.58% | 0.886 | 48.8% |
| **Candidate 2 (EMA/MACD V2-2)** | 979 | -65.27% | 0.951 | 44.8% | 888 | -70.39% | 0.911 | 56.8% |
| **Candidate 3 (Model B)** | 1,625 | -47.15% | 0.955 | 45.6% | 1,707 | -115.76% | 0.902 | 45.4% |
| **Candidate 4 (Candidate E)** | 826 | +237.92% | 1.278 | 45.3% | 762 | +77.81% | 1.121 | 52.2% |

**Directional Finding:**
- Long trades perform consistently better than Short trades across all architectures due to the secular bull market drift in Indian equities between 2023 and 2026.
- In Candidate 1, Short trades lost -397.58% (PF 0.886), dragging down Long profits (+175.17%, PF 1.049).
- Candidate E resolves this via **asymmetric parameters**: tighter short targets (+1.5% Short vs +3.0% Long) and restricting shorts to structurally weak symbols (`TOP_SHORTS`), generating positive edge on both sides (Long PF 1.278, Short PF 1.121).

---

## 6. Portfolio Concurrency Gate Simulation (Max 20 Active Positions)

Testing live operational risk constraints (`MAX_ACTIVE_POSITIONS = 20`):

| Candidate | Unconstrained Trades | Unconstrained Net (%) | Constrained Trades (Max 20) | Constrained Net (%) | Constrained PF | Concurrency Impact |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Candidate 1 (Baseline)** | 9,288 | -222.41% | 7,899 | -308.92% | 0.949 | Degrades further; skips reversals when saturated |
| **Candidate 2 (EMA/MACD)** | 1,867 | -135.66% | 1,848 | -127.34% | 0.939 | Minimal skipping (lower frequency entry) |
| **Candidate 3 (Model B)** | 3,332 | -162.91% | 3,332 | -162.91% | 0.927 | No concurrency blockage on 15 core |
| **Candidate 4 (Candidate E)** | 1,588 | +315.73% | 1,588 | +315.73% | **1.211** | Zero trade loss; maximum concurrent open was 11 |

---

## 7. Artifact Manifest & Preserved Trade Ledgers

The following machine-readable audit artifacts have been created in `backtesting/experiments/exp_20261013_macd_comparison/`:

1. `ledgers/candidate1_macdfno_baseline_ledger.csv` — Complete 9,288-trade chronological ledger.
2. `ledgers/candidate2_ema_macd_v2_2_ledger.csv` — Complete 1,867-trade chronological ledger.
3. `ledgers/candidate3_model_b_ledger.csv` — Complete 3,332-trade chronological ledger.
4. `ledgers/candidate4_candidate_e_ledger.csv` — Complete 1,588-trade chronological ledger.
5. `master_comparison_summary.csv` — Comprehensive metric matrix across all universes and subsets.
6. `friction_sensitivity_matrix.csv` — Step-by-step stress tests from 0.05% to 0.15% friction.
7. `directional_breakdown.csv` — Long vs Short segmented performance.
8. `per_symbol_breakdown.csv` — Symbol-by-symbol breakdown across all 33 instruments.

---

## 8. Final Recommendation & Operational Next Steps

### Summary Ranking:
1. 🥇 **Candidate 4 (Candidate E / Preset B)**: **The only candidate with statistically validated positive alpha.**
   - Verified Profit Factor: **1.211** (2026 Holdout PF: **1.218**).
   - Maximum Drawdown: **50.05%** (lowest among all candidates).
   - Friction Resilient: Remains profitable up to **0.15%** round-trip friction.
   - Mechanism: Curated universe + Asymmetric targets (+3% Long / +1.5% Short) + 0.35% HWM trailing runner.
2. ❌ **Candidate 3 (Model B / Preset A)**: **REJECTED.**
   - Disproven due to path-dependent SL hit order; realized PF is **0.927**, not 1.34.
3. ❌ **Candidate 2 (EMA/MACD V2-2)**: **REJECTED IN ISOLATION.**
   - Sequential confirmation alone fails (PF **0.936**); requires Candidate EXP_I's macro regime and trailing runner stack.
4. ❌ **Candidate 1 (Baseline)**: **REJECTED.**
   - Raw MACD crossovers on 1H generate negative return (-222.41%) and severe 343% drawdown.

### Operational Next Steps:
- **Live Strategy Files:** Kept 100% clean and untouched.
- **Decision Point for User:** Awaiting explicit authorization whether to proceed with paper simulation of **Candidate E** or maintain current baseline.
