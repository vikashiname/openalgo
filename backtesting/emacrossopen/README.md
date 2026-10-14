# Isolated EMA + MACD Backtesting & Research Workspace
**Directory:** `backtesting/emacrossopen/`

This workspace is strictly dedicated to historical backtesting, parameter optimization, and logic verification for the **NFO 1H EMA (9/26) + MACD (12/26/9) Asymmetric V2-2 Strategy**.

---

## 🔒 Isolation Guarantee
- **Live Strategy Path:** `strategies/liveonopenalgo/emacrossopen.py` (remains untouched)
- **Live State Path:** `strategies/liveonopenalgo/emacrossopen_state.json` (remains untouched)
- All executions, state files, research logs, and test runs initiated inside this directory resolve relative to `backtesting/emacrossopen/` and will never interfere with live paper-trading engines.

---

## 📁 Workspace Contents
| File | Description |
| :--- | :--- |
| **`emacrossopen.py`** | Independent strategy and verification script containing the 20-case test suite and sequential confirmation engine. |
| **`emacrossopen_state.json`** | Initial snapshot of tracked positions, active setups, and confirmation state. |
| **`emacrossopen_research.csv`** | Historical signal confirmation records and candle log. |
| **`heartbeat.json`** | Health telemetry state template. |
| **`nfo_scanner_local_validation.md`** | Baseline validation report and mathematical specification of the 1H EMA/MACD confluence rules. |

---

## 🧪 Verification & Execution Commands
Run the automated 20-case verification test suite:
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
