# Isolated EMA + MACD Backtesting & Research Workspace
**Directory:** `backtesting/emacrossopen/`

This workspace is strictly dedicated to historical backtesting, parameter optimization, and logic verification for the **NFO 1H EMA (11/29) + MACD (12/26/9) Volume-Filtered Strategy (V5.0 Certified Baseline - Candidate EXP_V)**.

---

## 🔒 Isolation & Parity Guarantee
- **Live Strategy Path:** `strategies/liveonopenalgo/emacrossopen.py` (V5.0 Certified Baseline)
- **Digital-Twin Path:** `backtesting/emacrossopen/emacrossopen.py` (100% Logic & Parameter Parity)
- **Live State Path:** `strategies/liveonopenalgo/emacrossopen_state.json` (State isolated; never touched by backtests)
- All executions, state files, research logs, and test runs initiated inside this directory resolve relative to `backtesting/emacrossopen/` and will never interfere with live trading engines.

---

## 📁 Workspace Contents
| File | Description |
| :--- | :--- |
| **`emacrossopen.py`** | Independent digital-twin strategy containing the 47-case test suite and volume-filtered confirmation engine. |
| **`emacrossopen_state.json`** | Isolated snapshot of tracked positions, active setups, and confirmation state. |
| **`emacrossopen_research.csv`** | Historical signal confirmation records and candle log. |
| **`heartbeat.json`** | Health telemetry state template. |
| **`research_leaderboard.csv`** | Historical ledger of all 79 autonomous quant optimization runs. |
| **`sop_baseline_comparison_final.csv`** | Empirical head-to-head comparison table against SOP Section 8A baselines. |

---

## 🧪 Verification & Execution Commands
Run the automated 47-case verification test suite:
```bash
./.venv/bin/python backtesting/emacrossopen/emacrossopen.py --test
```

Run a single evaluation pass on a symbol in paper mode:
```bash
./.venv/bin/python backtesting/emacrossopen/emacrossopen.py --symbols SBIN --run-once
```

Run startup position reconciliation audit without placing orders:
```bash
./.venv/bin/python backtesting/emacrossopen/emacrossopen.py --reconcile-only
```
