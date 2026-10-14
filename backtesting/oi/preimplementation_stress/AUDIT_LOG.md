# AUDIT LOG: OIFNO PRE-IMPLEMENTATION STRESS SUITE
**Target Strategy:** `SIG-OI-001-PAPER-V1`  
**Execution Timestamp:** 2026-10-13 14:08:30 IST  
**Environment:** Headless Non-Interactive Research Audit Mode  
**Working Directory:** `backtesting/oi/preimplementation_stress/`  

---

## 1. Compliance and Safety Verifications

| Check ID | Verification Requirement | Result | Evidence / Audit Findings |
| :--- | :--- | :---: | :--- |
| **SEC-01** | Scope isolation | **PASS** | Work strictly executed within `backtesting/oi/preimplementation_stress/`. Zero external modifications. |
| **SEC-02** | Live strategy preservation | **PASS** | `strategies/liveonopenalgo/oifno.py` hash and content untouched. Last modified timestamp unchanged. |
| **SEC-03** | Frozen contract immutability | **PASS** | `backtesting/oi/strategy/SIG-OI-001-PAPER-V1.md` preserved without alteration. Contract hash verified. |
| **SEC-04** | Order block guarantee | **PASS** | `LIVE_TRADING_ENABLED = False` across all imported or generated modules. Zero broker orders placed. |
| **SEC-05** | Production promotion block | **PASS** | All outputs, logs, CSVs, and figures isolated inside designated directory. |

---

## 2. Baseline Reproduction & Reconciliation Log

* **Data Source:** Official NSE Historical Derivatives Bhavcopy (`backtesting/oi/data/nse_futures_daily.parquet`).
* **Date Span:** 2022-01-03 to 2026-09-04 (1,154 trading sessions, 680,398 FUTSTK records, 298 unique equities).
* **Missing Observations:** 0 missing trading sessions (all non-trading days verified as official exchange holidays).
* **Baseline Executed Trades:** **5,728 trades** reproduced with exact 1-to-1 alignment against `backtesting/oi/audit/OI_NFO_TRADE_LEVEL_BACKTEST.parquet`.
* **Cumulative Net P&L:** **₹7,758,869.87** on ₹1.00 Crore initial capital (+77.59% net gain). Discrepancy = **₹0.00**.
* **Win Rate:** **52.55%** (3,010 wins / 2,718 losses). Discrepancy = **0.00%**.
* **Average Net Return:** **+0.1354%** per trade. Discrepancy = **0.0000%**.
* **Sharpe Ratio:** **1.26** (Annualized daily returns). Discrepancy = **0.00**.
* **Maximum Drawdown:** **-9.08%**. Discrepancy = **0.00%**.

---

## 3. Discrepancies and Inconsistencies Reconciled

### 3.1 Conflicting Contract Hashes
1. **Canonical Strategy Hash:** `dc1063b1ccadd2e513c6d3f71a8a2f4f13465db852387204c0b27137249ed917`
   - Located in: `SIG-OI-001-PAPER-V1.md`, `strategies/liveonopenalgo/oifno.py`, `oifno_reference.py`, Phase 5, Phase 6, Phase 7 reports, `oifno_state.json`.
2. **Conflicting Phase 8 Hash:** `dc1063b15f973347f3737b567d288d672808beaf559868728a3014a938c5383f`
   - Located in: `backtesting/oi/validation/nfo_phase8_trade_level_backtest.py`, `OI_NFO_FINAL_TRADE_LEVEL_BACKTEST_REPORT.md`, `nfo_full_backtest_engine.py`.
3. **Reconciliation Finding:** Both hashes share the identical first 8 hex characters (`dc1063b1`). Forensic analysis indicates an accidental string completion or paste error during the drafting of Phase 8 scripts. The canonical hash is `dc1063b1ccadd2e513c6d3f71a8a2f4f13465db852387204c0b27137249ed917`.

### 3.2 Specification Underspecification
1. The markdown document `SIG-OI-001-PAPER-V1.md` Section 4 formally defines entry solely as:
   - $\text{Return}_{1\text{D}}(T) < 0$
   - $\Delta\text{OI}_{\%}(T) < 0$
   - $\text{DTE} > 3$
   - Rolling turnover $\ge ₹5\text{ Cr}$
2. Executing this pure formal contract yields **48,289 candidates** and **10,938 executed trades**, but win rate drops to **50.23%** and mean net return collapses to **+0.030%** (+3 bps).
3. The working baseline in Phase 8 and production code introduced undocumented/uncontracted filters:
   - $\Delta\text{OI}_{\%} \le -2.0\%$ (Contraction threshold)
   - Candle structure: $\text{Close} < \text{Open}$ and $\text{Body Ratio} \ge 0.40$ (or $> 0.60$ in `oifno.py`)
4. **Resolution:** The frozen contract document requires a formal revision (`SIG-OI-001-PAPER-V2`) to codify the candle structure and -2.0% threshold before any production deployment.

### 3.3 Trailing Stop Look-Ahead Bias
1. Phase 8 reported that a 0.5% trailing stop achieved a **75.38% win rate** and a **6.07 Sharpe ratio**.
2. Independent code audit revealed that the diagnostic script evaluated all 10,546 unconstrained candidates using daily OHLC bars, assuming that if the high hit $\text{MFE} \ge \text{trailing\_dist}$ and close finished below $\text{MFE} - \text{trailing\_dist}$, the trade exited *at the peak minus stop*.
3. This assumption introduces severe lookahead and path-dependency bias because daily data cannot determine whether the intraday low occurred before the high.
4. When modeled conservatively (assuming low occurs first and penalizing gap-downs), all trailing stops suffer catastrophic whipsaw stop-outs during morning opening volatility, resulting in -100% drawdown and negative Sharpe ratios.
5. **Resolution:** The reported trailing stop results are officially marked as **UNVERIFIED / LOOKAHEAD-BIASED SYNTHETIC ARTIFACTS**. The frozen T+2 Open auction exit remains the only verified execution model.

---

## 4. Deliverables Manifest

The following files have been generated and validated inside `backtesting/oi/preimplementation_stress/`:
- `STRESS_TEST_REPORT.md`: Comprehensive executive report and decision gate verdict.
- `FRICTION_STRESS.csv`: Full results for 8, 12, 16, 20, 24, 30, and 40 bps friction.
- `TRAILING_STOP_COMPARISON.csv`: Comparative audit of exit rules and path dependency.
- `CURATED_UNIVERSE_COMPARISON.csv`: In-Sample vs Out-of-Sample evaluation of stock exclusions.
- `MONTE_CARLO_TAIL_RISK.csv`: 10,000 IID and Block resampling tail-risk statistics.
- `WALK_FORWARD_RESULTS.csv`: Chronological partitions and regime breakdowns.
- `BASELINE_TRADE_LEDGER.parquet`: Complete 5,728 trade-level ledger.
- `BASELINE_TRADE_LEDGER.csv`: CSV export of baseline trade ledger.
- `STRESS_CONFIG.json`: Machine-readable snapshot of configuration and parameters.
- `plots/friction_decay_curve.png`: Friction decay curve chart.
- `plots/monte_carlo_drawdown_dist.png`: Monte Carlo drawdown distribution histogram.
- `plots/walk_forward_equity_curves.png`: Multi-period equity trajectory chart.
- `AUDIT_LOG.md`: This comprehensive verification audit log.
