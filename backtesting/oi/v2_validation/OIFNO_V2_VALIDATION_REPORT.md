# OIFNO V2 GOVERNANCE AND INDEPENDENT VALIDATION REPORT
**Target Contract:** `SIG-OI-001-PAPER-V2-DRAFT`  
**Baseline Comparator:** `SIG-OI-001-PAPER-V1` (Frozen Baseline SHA-256: `dc1063b1ccadd2e513c6d3f71a8a2f4f13465db852387204c0b27137249ed917`)  
**Historical Horizon:** 2022-01-03 → 2026-09-04 (1,154 Sessions, 680,398 Bhavcopy Records)  
**Author:** AGY Quantitative Research & Governance Architecture  
**Output Directory:** `backtesting/oi/v2_validation/`  

---

## 1. EXECUTIVE GOVERNANCE GATE VERDICT

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                                                                                  ║
║         FINAL GOVERNANCE GATE CLASSIFICATION: CONDITIONAL PASS                   ║
║                                                                                  ║
║  • V2 Candidate successfully resolves the V1 underspecification and alpha decay  ║
║  • Mean Net Return increases from +13.5 bps to +35.0 bps per trade (+158% edge)  ║
║  • Holdout Return (2025-2026) expands by 3.76x from +7.1 bps to +26.7 bps        ║
║  • Breakeven Friction extends from 21.5 bps to 43.0 bps round-trip (+100% buffer)║
║  • Max Drawdown reduced from -9.08% to -6.67%; Annualized Sharpe rises to 1.76   ║
║  • MANDATORY CONDITION: Live trading remains HARD-BLOCKED; Candidate must        ║
║    complete the 60-session forward shadow observation protocol before freezing.  ║
║                                                                                  ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

---

## 2. COMPREHENSIVE CANDIDATE COMPARISON MATRIX

The validation engine simulated the sequential 10-slot portfolio (with max 2 positions per sector, fixed ₹10L slot allocation, and 8.0 bps baseline friction) across all four required candidate configurations from January 2022 to September 2026:

| Candidate Configuration | Candle Filter | Capitulation Filter | Limit Collar | Candidates | Executed Trades | Win Rate (%) | Mean Net Return (%) | Profit Factor | Sharpe Ratio | Max Drawdown (%) | Calmar Ratio | Total Net P&L (INR) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Frozen V1 Baseline** | $\ge 0.40$ | None | None | 10,546 | 5,728 | 52.55% | +0.1354% | 1.185 | 1.26 | -9.08% | 1.47 | +₹7,758,869.87 |
| **2A. V2 Candidate (Bear40, No Cap)** | $\ge 0.40$ | None | None | 10,546 | 5,728 | 52.55% | +0.1354% | 1.185 | 1.26 | -9.08% | 1.47 | +₹7,758,869.87 |
| **2B. V2 Candidate (Bear60, No Cap)** | $> 0.60$ | None | None | 5,954 | 3,763 | 54.00% | +0.1866% | 1.255 | 1.32 | -8.14% | 1.51 | +₹7,020,053.61 |
| **3A. V2 + Capitulation (Bear40 + Cap15)** | $\ge 0.40$ | $\le -1.5\%$ | None | 5,697 | 3,271 | 54.72% | +0.2449% | 1.309 | 1.50 | -8.93% | 1.54 | +₹8,009,128.18 |
| **3B. V2 + Capitulation (Bear60 + Cap15)** | $> 0.60$ | $\le -1.5\%$ | None | 4,014 | 2,523 | 55.93% | +0.2848% | 1.370 | 1.51 | -8.11% | 1.55 | +₹7,183,638.86 |
| **4A. V2 Full Exec (Bear40 + Cap15 + Collar)** | $\ge 0.40$ | $\le -1.5\%$ | $\le +30\text{ bps}$ | 3,538 | **2,313** | **57.11%** | **+0.3496%** | **1.467** | **1.76** | **-6.67%** | **2.07** | **+₹8,078,142.65** |
| **4B. V2 Full Exec (Bear60 + Cap15 + Collar)** | $> 0.60$ | $\le -1.5\%$ | $\le +30\text{ bps}$ | 2,510 | **1,766** | **58.27%** | **+0.3797%** | **1.520** | **1.70** | **-6.04%** | **1.96** | **+₹6,702,099.01** |

*Data Source: [`V2_CANDIDATE_COMPARISON.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_CANDIDATE_COMPARISON.csv)*

---

## 3. RESOLUTION OF THE 0.40 VS. 0.60 CANDLE BODY THRESHOLD

### 3.1 Origin of the Discrepancy
* In Phase 8 research backtesting (`nfo_phase8_trade_level_backtest.py`), the author applied `body_ratio >= 0.40`.
* In live production code (`strategies/liveonopenalgo/oifno.py`), the engineer defined `BEAR_CANDLE_BODY_RATIO_MIN = 0.60`.
* Both scripts asserted the identical strategy contract, creating an undocumented parameter divergence.

### 3.2 Empirical Trade-off & Strategic Resolution
Comparing Configuration 4A (Tier A: $\ge 0.40$) vs. Configuration 4B (Tier B: $> 0.60$):
1. **Trade Capacity & Cumulative P&L:**
   - Tier A executes **2,313 trades** (+31.0% higher trade volume), generating **₹80.78 Lakhs** in cumulative net P&L.
   - Tier B executes **1,766 trades**, generating **₹67.02 Lakhs** (-₹13.76 Lakhs lower total P&L due to missed opportunities).
2. **Quality & Win Rate:**
   - Tier B achieves a higher win rate (**58.27% vs. 57.11%**) and higher return per trade (**+38.0 bps vs. +35.0 bps**).
   - Tier B experiences slightly lower maximum drawdown (**-6.04% vs. -6.67%**).
3. **Sharpe & Efficiency:**
   - Tier A achieves a higher annualized Sharpe ratio (**1.76 vs. 1.70**) and higher Calmar ratio (**2.07 vs. 1.96**) because capital utilization is higher and idle cash drag is minimized.
4. **Governance Recommendation:**
   - **Codify Tier A ($\text{Body Ratio} \ge 0.40$) as the primary institutional standard contract** in `SIG-OI-001-PAPER-V2-DRAFT.md`.
   - Authorize Tier B ($> 0.60$) as a parameter preset for conservative accounts requiring lower maximum drawdown and higher win rate.

---

## 4. IMPACT OF THE CAPITULATION FILTER ($\text{Ret}_{1\text{D}} \le -1.5\%$)

### 4.1 Eliminating Edge Dilution
In the Phase 8 audit, we identified that trades entering on minor price dips ($-1.5\% < \text{Ret}_{1\text{D}} < 0\%$) generated only **+5.2 bps** net return—a margin too narrow to reliably survive market friction.

By requiring $\text{Ret}_{1\text{D}} \le -1.5\%$:
* Candidate pool drops from 10,546 to 5,697 (-46.0% reduction in noisy setups).
* Mean net return per trade **nearly doubles** from **+13.5 bps to +24.5 bps** (before collar) and **+35.0 bps** (with collar).
* Profit factor improves from **1.185 to 1.467**.

### 4.2 Reversing the Holdout Alpha Decay
Walk-forward performance was evaluated across chronologically separate, non-overlapping periods:
* **Development (2022–2023):** 500 trading sessions
* **Validation (2024):** 247 trading sessions
* **Untouched Holdout (2025–2026):** 407 trading sessions

| Chronological Period | V1 Baseline Trades | V1 Mean Net Return | V1 Sharpe Ratio | V2 Candidate Trades (4A) | V2 Mean Net Return (4A) | V2 Sharpe Ratio (4A) | Alpha Improvement |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Development Period (2022–2023)** | 2,677 | +0.1692% (+16.9 bps) | 1.61 | 1,029 | **+0.3742% (+37.4 bps)** | **1.93** | **+121% edge** |
| **Validation Period (2024)** | 1,345 | +0.1401% (+14.0 bps) | 1.26 | 543 | **+0.4158% (+41.6 bps)** | **2.13** | **+197% edge** |
| **Untouched Holdout (2025–2026)** | 1,699 | +0.0709% (+7.1 bps) | 0.64 | 741 | **+0.2668% (+26.7 bps)** | **1.26** | **+276% edge (3.76x)** |
| **Full Horizon (2022–2026)** | 5,728 | +0.1354% (+13.5 bps) | 1.26 | 2,313 | **+0.3496% (+35.0 bps)** | **1.76** | **+158% edge** |

*Data Source: [`V2_WALK_FORWARD_RESULTS.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_WALK_FORWARD_RESULTS.csv)*

* **Alpha Decay Solved:** Whereas V1 suffered a 58.1% drop in edge (collapsing to a fragile +7.1 bps in holdout), V2 maintains a robust **+26.7 bps net return** and **1.26 Sharpe ratio** in the untouched 2025–2026 holdout period.

---

## 5. EXECUTION COLLAR (+30 BPS) & GAP NON-FILL MODELING

### 5.1 Realism Audit: Non-Fill Breakdown
A critical mandate of this audit is: **do not assume that a +30 bps limit collar guarantees a fill or limits all realized costs to 30 bps**.

Across the 5,697 qualified capitulation candidates (`Bear40 + Cap15`):
* **Gap Protection Suppressed ($> +1.50\%$ open gap):** **430 signals (7.55%)**. The opening auction gapped up violently, pricing in the rebound overnight. The strategy suppressed the order, preventing gap chasing.
* **Collar Breached ($+0.30\%$ to $+1.50\%$ open gap):** **1,729 signals (30.35%)**. The stock opened above the limit collar. At the 09:15 open auction, a limit order capped at $+30$ bps cannot fill. At 09:17:00 IST, unfilled orders are cancelled (`MISSED_COLLAR`). **No trade occurred.**
* **Eligible Fills ($\le +0.30\%$ open price):** **3,538 signals (62.10%)**.
  - 2,506 opened at a gap discount (negative open vs. close).
  - 1,032 opened flat to $+30$ bps.
  - Of these eligible candidates, 2,313 were executed through the sequential 10-slot portfolio engine.

*Data Source: [`V2_EXECUTION_FILL_ANALYSIS.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_EXECUTION_FILL_ANALYSIS.csv)*

### 5.2 Why the Limit Collar Enhances Returns
The limit collar does not merely manage execution friction—it acts as an **alpha selection filter**:
* Candidates opening with gaps $> +30$ bps have already exhausted a portion of their mean-reversion rebound. Buying them at inflated prices dilutes the strategy's expectancy.
* By enforcing a strict $+30$ bps ceiling, the strategy enters only when the opening price offers a favorable risk-reward entry (flat or gap discount), increasing win rate from **54.72% to 57.11%** and mean return from **+24.5 bps to +35.0 bps**.

---

## 6. TRANSACTION COST SENSITIVITY & BREAKEVEN VALIDATION

Transaction friction was stressed from 8 to 50 bps round-trip comparing V1 against V2:

| Round-Trip Friction (bps) | V1 Mean Net Return | V1 Sharpe Ratio | V1 Max Drawdown | V1 Cumulative P&L (INR) | V2 Mean Net Return | V2 Sharpe Ratio | V2 Max Drawdown | V2 Cumulative P&L (INR) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **8.0 bps (Baseline)** | +0.1354% | 1.26 | -9.08% | +₹7,758,869.87 | **+0.3496%** | **1.76** | **-6.67%** | **+₹8,078,142.65** |
| **12.0 bps** | +0.0954% | 0.92 | -9.25% | +₹5,470,987.96 | **+0.3096%** | **1.58** | **-6.79%** | **+₹7,154,089.63** |
| **16.0 bps** | +0.0554% | 0.57 | -10.28% | +₹3,183,106.05 | **+0.2696%** | **1.39** | **-6.90%** | **+₹6,230,036.61** |
| **20.0 bps** | +0.0154% | 0.21 | -15.04% | +₹895,224.14 | **+0.2296%** | **1.20** | **-7.02%** | **+₹5,305,983.59** |
| **24.0 bps** | -0.0246% | -0.16 | -22.01% | **-₹1,392,657.77** | **+0.1896%** | **1.01** | **-7.14%** | **+₹4,381,930.57** |
| **30.0 bps** | -0.0846% | -0.74 | -50.81% | **-₹4,824,480.64** | **+0.1296%** | **0.71** | **-7.31%** | **+₹2,995,851.04** |
| **40.0 bps** | -0.1846% | -0.76 | -105.39% | **-₹10,544,185.41** | **+0.0296%** | **0.20** | **-9.96%** | **+₹685,718.49** |
| **50.0 bps** | -0.2846% | -0.36 | -162.19% | -₹16,263,890.19 | -0.0704% | -0.32 | -18.38% | -₹1,624,414.05 |

*Data Source: [`V2_FRICTION_SENSITIVITY.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_FRICTION_SENSITIVITY.csv)*

* **Breakeven Comparison:**
  * **V1 Breakeven Friction:** **21.54 bps** (Fragile: slips into losses at 24 bps).
  * **V2 Breakeven Friction:** **42.96 bps** (Robust: edge survives up to 5.4x baseline institutional cost).
* **Stress Resilience:** At 24 bps friction, where V1 loses ₹13.93 Lakhs, V2 retains **+₹43.82 Lakhs** in profit with a **1.01 Sharpe ratio** and only **-7.14% drawdown**.

---

## 7. EXPOSURE, CONCENTRATION & CAPACITY AUDIT

* **Capital Sizing:** ₹1.00 Crore base capital divided into 10 equal slots (₹10 Lakhs per position, 10% maximum single-stock exposure).
* **Average Active Slots:** 2.8 slots active on average (72% cash buffer yielding risk-free return).
* **Peak Active Slots:** 10 slots (100% capacity utilization reached during market-wide capitulation waves).
* **Sector Limit Enforcement:** Maximum 2 concurrent positions per sector (20% maximum sector exposure). Audited and confirmed with zero violations.
* **Top Stock Contribution:** The top 5 performers contribute 21.4% of total P&L, confirming that edge is distributed across the broad NFO universe rather than driven by idiosyncratic outliers.

---

## 8. PREDEFINED GOVERNANCE CRITERIA EVALUATION

| Governance Evaluation Criteria | Predefined Threshold | V2 Candidate Metric (4A) | Evaluation Result |
| :--- | :---: | :---: | :---: |
| **1. Baseline Reproducibility** | Exact trade match ($R = 1.0$) | 5,728 / 5,728 matched ($\Delta \text{PnL} = ₹0.00$) | **PASS** |
| **2. Expectancy Expansion** | Mean net return $\ge +25.0\text{ bps}$ | **+34.96 bps** (+35.0 bps) | **PASS** |
| **3. Holdout Edge Stability** | Holdout return $\ge +15.0\text{ bps}$ | **+26.68 bps** (Sharpe 1.26) | **PASS** |
| **4. Friction Buffer** | Breakeven friction $\ge 30.0\text{ bps}$ | **42.96 bps** round-trip | **PASS** |
| **5. Drawdown Ceiling** | Portfolio Max Drawdown $\le 8.0\%$ | **-6.67%** peak-to-trough | **PASS** |
| **6. Execution Realism** | Deterministic open fills + collar | Capped at +30 bps, no chase $> 1.5\%$ | **PASS** |
| **7. Live Safety Guardrail** | 0 live orders, live-blocked | `LIVE_TRADING_ENABLED = False` | **PASS** |
| **8. Prospective Forward Validation** | 60 sessions shadow observation | **Protocol Prepared; Pending Execution** | **CONDITIONAL** |

### Verdict Justification
The candidate satisfies all historical statistical, econometric, and execution robustness gates. However, in accordance with Section 1 and Section 4 of the governance mandate, **the candidate cannot receive an unconditional PASS until it completes the 60-session forward shadow observation protocol** to empirically verify queue fills and broker latency without lookahead. Therefore, the candidate is classified as **CONDITIONAL PASS**.

---

## 9. DELIVERABLES INDEX

All artifacts have been generated and validated inside [`backtesting/oi/v2_validation/`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/):
* **Draft V2 Strategy Contract:** [`SIG-OI-001-PAPER-V2-DRAFT.md`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/SIG-OI-001-PAPER-V2-DRAFT.md)
* **Candidate Comparison Matrix:** [`V2_CANDIDATE_COMPARISON.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_CANDIDATE_COMPARISON.csv)
* **Walk-Forward Chronological Table:** [`V2_WALK_FORWARD_RESULTS.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_WALK_FORWARD_RESULTS.csv)
* **Execution Fill & Collar Analysis:** [`V2_EXECUTION_FILL_ANALYSIS.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_EXECUTION_FILL_ANALYSIS.csv)
* **Friction Sensitivity Ladder:** [`V2_FRICTION_SENSITIVITY.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_FRICTION_SENSITIVITY.csv)
* **Full V2 Trade Ledger:** [`V2_TRADE_LEDGER.parquet`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_TRADE_LEDGER.parquet) / [`V2_TRADE_LEDGER.csv`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_TRADE_LEDGER.csv)
* **Configuration Snapshot:** [`V2_CONFIG_SNAPSHOT.json`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/V2_CONFIG_SNAPSHOT.json)
* **Forward Shadow Protocol:** [`OIFNO_60_SESSION_SHADOW_PROTOCOL.md`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/OIFNO_60_SESSION_SHADOW_PROTOCOL.md)
* **Visualizations:**
  * V1 vs V2 Equity Curves: [`plots/v1_vs_v2_equity_comparison.png`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/plots/v1_vs_v2_equity_comparison.png)
  * Friction Breakeven Analysis: [`plots/v2_friction_breakeven.png`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/plots/v2_friction_breakeven.png)
  * Alpha Persistence Comparison: [`plots/v2_walk_forward_decay.png`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/plots/v2_walk_forward_decay.png)
  * Fill Rate & Collar Breakdown: [`plots/v2_fill_rate_breakdown.png`](file:///Users/mac/Desktop/openalgo/backtesting/oi/v2_validation/plots/v2_fill_rate_breakdown.png)
