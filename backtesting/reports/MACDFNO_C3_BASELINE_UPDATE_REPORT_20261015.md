# AGY MASTER SOP — MACD_FNO_V1_C3 BASELINE UPDATE REPORT

- **PHASE:** Strategy Baseline Promotion & Synchronization (Phase 7 Governance)
- **NEW STRATEGY BASELINE:** `MACD_FNO_V1_C3` (Version `1.3.1-C3`)
- **BASELINE REFERENCE:** Variant A (Candidate G / Candidate E Baseline, frozen in `macdfno_baseline_freeze.json`)
- **EXECUTION DATE:** 2026-10-15
- **STATUS:** COMPLETED (Code Updated & Synchronized; Strategy Execution NOT Authorized)

---

## 1. Executive Summary

In accordance with `~/backtesting/AGY_MASTER_SOP.md`, the validated Variant C3 time-filter realignment has been promoted to the official strategy baseline across local and AWS EC2 files.

### Core Strategy Change Applied
- **Alignment Fix:** The 1-hour candle completing at 11:15 IST (covering the 10:15–11:15 IST trading window) is now permitted for fresh signal evaluation (`MORNING_AND_MIDDAY_WINDOW` active from `09:45` to `13:15 IST`).
- **European Open Dead-Zone Preserved:** The afternoon dead zone from `14:00` to `14:59 IST` (`DEAD_ZONE_14_PM`) remains strictly active, blocking signal evaluation for the candle completing at 14:15 IST.
- **Invariants Preserved:** All other core strategy mechanics—MACD 12/26/9, 2-bar histogram expansion, Asymmetric Universe (`TOP_LONGS`: 7, `TOP_SHORTS`: 6), 1-lot sizing, +3.0% Long TP, +1.5% Short TP, −3.5% Catastrophe SL, and 20 max concurrent positions—remain 100% untouched.

---

## 2. Master SOP Phase Report

### FILES CREATED
1. `backtesting/reports/macdfno_c3_baseline_freeze.json` (New versioned baseline record)
2. `backtesting/macdfno/baseline/macdfno_c3_baseline_freeze.json` (Research baseline copy)
3. `test/test_macdfno_c3_validation.py` (Boundary and invariance regression test suite)
4. `strategies/scripts/macdfno.py.bak_20261015122058` (Timestamped local backup)
5. `strategies/liveonopenalgo/macdfno.py.bak_20261015122058` (Timestamped local backup)
6. `backtesting/macdfno/macdfno.py.bak_20261015122058` (Timestamped local backup)
7. AWS EC2: `/home/ubuntu/fyersawsog/strategies/scripts/macdfno.py.bak_20261015122105` (Timestamped AWS backup)
8. AWS EC2: `/home/ubuntu/fyersawsog/strategies/liveonopenalgo/macdfno.py.bak_20261015122105` (Timestamped AWS backup)

### FILES MODIFIED
1. `strategies/scripts/macdfno.py` (Local operational script)
2. `strategies/liveonopenalgo/macdfno.py` (Local live strategy template)
3. `backtesting/macdfno/macdfno.py` (Research baseline copy)
4. AWS EC2: `/home/ubuntu/fyersawsog/strategies/scripts/macdfno.py` (AWS operational copy)
5. AWS EC2: `/home/ubuntu/fyersawsog/strategies/liveonopenalgo/macdfno.py` (AWS live strategy copy)

### DATA USED
- Historical 1-hour completed candle dataset (Yahoo Finance / OpenAlgo Local Parquet Store) across 33 NFO underlying assets (2023-01-01 to 2026-09-09, 732 trading days).
- Untouched 2026 Holdout period (2026-01-01 to 2026-09-09, 74 trading days).

### TESTS PERFORMED
1. **Compilation Validation:** `python3 -m py_compile` executed on all local and AWS files. Result: PASSED.
2. **Time-Filter Boundary Matrix:** Evaluated all 18 minute marks across the trading day (09:15, 09:44, 09:45, 10:15, 11:00, 11:15, 11:59, 12:15, 13:15, 13:16, 14:00, 14:15, 14:59, 15:00, 15:15, 15:20, 15:21, 15:30). Result: PASSED (11:15 IST allowed, 14:15 IST blocked).
3. **Invariance Assertion:** Verified that universe constants (`TOP_LONGS`, `TOP_SHORTS`), targets (+3.0% / +1.5%), catastrophe SL (-3.5%), and `MAX_ACTIVE_POSITIONS` (20) are identical across all modules. Result: PASSED.
4. **Runtime Strategy Contracts:** Executed `pytest test/test_strategy_runtime_contracts.py` (8/8 passed). Result: PASSED.
5. **Controlled C3 Simulation Reproduction:** Executed `run_c3_final_validation.py` to confirm exact reproduction of the 1,243 trades, ₹20L portfolio equity curve (+3.99% return vs +2.84% in A), and statistical significance checks. Result: PASSED.

### RESULTS & COMPARISON MATRIX

| Dimension | Variant A (Baseline) | Variant C3 (New Baseline) | Delta (C3 - A) | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **Total Trades** | 981 | 1,243 | +262 (+26.7%) | Volume expansion from 11:15 window |
| **Summed Net P&L** | +70.84% | +97.04% | +26.20% (+37.0%) | 0.07% round-trip friction applied |
| **Profit Factor** | 1.071 | 1.082 | +0.011 (+1.0%) | Full 2023–2026 sample |
| **Expectancy / Trade** | +0.072% | +0.078% | +0.006% | Statistically indistinguishable ($p=0.953$) |
| **Portfolio Compounded Return (₹20L)** | +2.84% | +3.99% | +1.15% (+40.5%) | Event-driven simulation |
| **Portfolio Max Drawdown (₹20L)** | 2.14% | 1.96% | -0.18% (-8.4%) | Peak concurrent active: 9 / 20 cap |
| **Annualized Sharpe** | 0.51 | 0.66 | +0.15 (+29.4%) | Compounded daily returns |
| **2026 Holdout PF** | **1.072** | **1.013** | -0.059 (-5.5%) | Weaker holdout documented |
| **2026 Holdout Net P&L** | **+17.66%** | **+4.03%** | -13.63% (-77.2%) | Rangebound consolidation friction |
| **Statistical Superiority** | N/A | **NOT ESTABLISHED** | $p=0.953$ | Welch t-test confirms null hypothesis |

### BEFORE/AFTER HASHES

| File Path | Environment | Before SHA-256 | After SHA-256 |
| :--- | :--- | :--- | :--- |
| `strategies/scripts/macdfno.py` | Local | `9de3972953a008f5ca7699517956e32f1f463d51481fd6a1ad7cd76289814f53` | `de3c1add0f02187f905ea7128d578cf48feca5f6d627e594d9e53a41866de416` |
| `strategies/liveonopenalgo/macdfno.py` | Local | `9de3972953a008f5ca7699517956e32f1f463d51481fd6a1ad7cd76289814f53` | `de3c1add0f02187f905ea7128d578cf48feca5f6d627e594d9e53a41866de416` |
| `backtesting/macdfno/macdfno.py` | Local | `f1aa42ce4f8bf45b6b898f3be9b1ca6417e05ccbd286eb28938303fb305c7d3b` | `e046b9f1d50053f2c836b996f79be9240b2005c85d5a17373ceeddce60132fe4` |
| `/home/ubuntu/fyersawsog/strategies/scripts/macdfno.py` | AWS EC2 | `9de3972953a008f5ca7699517956e32f1f463d51481fd6a1ad7cd76289814f53` | `de3c1add0f02187f905ea7128d578cf48feca5f6d627e594d9e53a41866de416` |
| `/home/ubuntu/fyersawsog/strategies/liveonopenalgo/macdfno.py` | AWS EC2 | `9de3972953a008f5ca7699517956e32f1f463d51481fd6a1ad7cd76289814f53` | `de3c1add0f02187f905ea7128d578cf48feca5f6d627e594d9e53a41866de416` |

### LOCAL/AWS SYNCHRONIZATION STATUS
- Local and AWS `strategies/scripts/macdfno.py` and `strategies/liveonopenalgo/macdfno.py` match byte-for-byte (`de3c1add0f02187f905ea7128d578cf48feca5f6d627e594d9e53a41866de416`).
- AWS remote compilation verified successfully.
- Intentional difference in `backtesting/macdfno/macdfno.py`: omits `order_kwargs["price"]` on market order placement (local research file only).

### BACKUP AND ROLLBACK DETAILS
- **Local Rollback:**
  ```bash
  cp strategies/scripts/macdfno.py.bak_20261015122058 strategies/scripts/macdfno.py
  cp strategies/liveonopenalgo/macdfno.py.bak_20261015122058 strategies/liveonopenalgo/macdfno.py
  cp backtesting/macdfno/macdfno.py.bak_20261015122058 backtesting/macdfno/macdfno.py
  ```
- **AWS Rollback:**
  ```bash
  ssh -i ~/.ssh/openalgo-key.pem ubuntu@13.203.187.139 "
    cp /home/ubuntu/fyersawsog/strategies/scripts/macdfno.py.bak_20261015122105 /home/ubuntu/fyersawsog/strategies/scripts/macdfno.py
    cp /home/ubuntu/fyersawsog/strategies/liveonopenalgo/macdfno.py.bak_20261015122105 /home/ubuntu/fyersawsog/strategies/liveonopenalgo/macdfno.py
  "
  ```
- Frozen reference for rollback: `backtesting/reports/macdfno_baseline_freeze.json`.

### SAFETY STATUS
- Zero orders routed to broker.
- Zero services restarted.
- Process status verified on AWS: running process is `/home/ubuntu/fyersawsog/strategies/scripts/macdfno_20260902130041.py` (PID 149764, untouched).
- Neither updated script was executed or activated.

### REMAINING RISKS & LIMITATIONS
1. **Statistical Insignificance:** The per-trade expectancy difference (+0.078% vs +0.072%, $p=0.953$) is not statistically distinguishable from zero; outperformance is driven by volume expansion under positive expectancy.
2. **Weaker 2026 Holdout:** In 2026, C3 achieved PF 1.013 (+4.03% Net) vs Variant A's 1.072 (+17.66% Net), due to mid-morning whipsaws during BPCL/BAJFINANCE rangebound periods.
3. **Execution Pacing:** Adding 11:15 IST entries increases portfolio activity (+26.7% trades), making disciplined order pacing and slippage control critical during live forward observation.

### NEXT STEP
- Await explicit user authorization before launching any forward paper observation.
- When authorized, run Variant C3 in isolated OpenAlgo `ANALYZE` mode (fail-closed simulated fills, zero broker routing) with pre-specified review rules (20 trading days, 30 trades, 5% DD pause).
