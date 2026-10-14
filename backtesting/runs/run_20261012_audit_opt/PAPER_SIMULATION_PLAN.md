# PAPER SIMULATION IMPLEMENTATION PLAN
**Target Strategy:** `emacrossopen.py` Candidate Architecture (`EXP_I`)  
**Scope:** Controlled Forward-Testing Paper Simulation (Zero Live Capital At Risk)  
**Safety Status:** Research protocol ONLY. No deployment or live broker modifications are permitted without explicit owner confirmation.

---

## 1. Architectural Blueprint: Candidate `EXP_I`

The empirical audit and robustness testing revealed that **Candidate `EXP_I`** provides the strongest risk-adjusted profile:
- **Asymmetric Universe Selection:**
  - **Approved Longs (`TOP_LONGS`):** `SUNPHARMA`, `BAJAJ-AUTO`, `BPCL`, `WIPRO`, `TATASTEEL`, `BAJFINANCE`, `NTPC`
  - **Approved Shorts (`TOP_SHORTS`):** `SUNPHARMA`, `BAJAJ-AUTO`, `M&M`, `BPCL`, `NTPC`, `NIFTY`
  - *All other symbols rejected on entry.*
- **1H Macro Trend Regime Guard:**
  - Longs only initiated if 1-Hour bar `Close > EMA26`.
  - Shorts only initiated if 1-Hour bar `Close < EMA26`.
- **Target & Trailing Runner Engine:**
  - Long Initial Target: **+3.00%**
  - Short Initial Target: **+1.50%**
  - Runner Activation: Once Initial Target is breached intrabar.
  - Conservative Lookahead-Free Trailing Distance: **0.35%** from High Water Mark (HWM), evaluated on subsequent bar closes/extremes.
  - Catastrophe Emergency Stop-Loss: **-6.00%** from initial fill price.
- **Opposite Signal Handling:**
  - If holding an active position and an opposite signal appears for an unapproved opposite direction, exit cleanly to **FLAT** without taking the unapproved direction.

---

## 2. Pre-Requisites & Entry Gates for Paper Trading

Before activating a paper run, the following conditions must be satisfied:
1. **Isolated State Directory:**  
   The paper instance must use a dedicated state file (e.g., `emacrossopen_paper_state.json`), completely separated from any live strategy state (`strategies/liveonopenalgo/emacrossopen_state.json`).
2. **Strict Mock/Analyze Mode Guard:**  
   Verify that `--mode analyze` or `--mode paper` is hardcoded in the execution wrapper. Real broker credentials must be disconnected or passed through a mock adapter.
3. **Dedicated Port & Webhook Binding:**  
   Ensure OpenAlgo webhook ports do not collide with running production instances.
4. **Log Retention:**  
   Set up separate forward-test logging to `backtesting/runs/paper_eval/` with millisecond-resolution bar timestamps.

---

## 3. Two-Week Forward Verification Protocol

| Week | Focus Area | Success Metrics | Abort Conditions |
| :---: | :--- | :--- | :--- |
| **Week 1** | **Order Execution & Runner State Tracking** | - 100% of signals correctly filtered by `TOP_LONGS`/`TOP_SHORTS`.<br>- Zero ghost trades.<br>- Runner transitions correctly from TARGET_HIT to HWM tracking.<br>- Zero lookahead artifacts. | - Any order sent to a live account.<br>- State desynchronization across process restarts. |
| **Week 2** | **Friction & Real-World Slippage Comparison** | - Measured slippage on 1H candle opens vs model assumptions (must be $\le 0.05\%$).<br>- Trailing stop fill slippage $\le 0.03\%$.<br>- Telegram alerts match state transitions. | - Average slippage $> 0.12\%$.<br>- Runner trail triggering prematurely due to wide bid-ask spread. |

---

## 4. Promotion Criteria into Production

Candidate `EXP_I` may only be considered for production deployment when the owner:
1. Has reviewed `BASELINE_AUDIT.md`, `ACCOUNTING_AUDIT.md`, `ROBUSTNESS_REPORT.md`, and `TEST_RESULTS.md`.
2. Has observed $\ge 15$ live paper trades across at least 2 distinct calendar weeks.
3. Has verified that forward paper Profit Factor $\ge 1.40$ and paper slippage remains within modeled parameters.
4. Provides explicit written sign-off to update `strategies/liveonopenalgo/emacrossopen.py`.
