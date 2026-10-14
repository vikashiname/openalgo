# AUTOMATED ENGINEERING TEST RESULTS
**Test Suite:** `backtesting/emacrossopen/emacrossopen.py --test`  
**Execution Timestamp:** 2026-10-12 19:24:51 IST  
**Environment:** Offline Test Harness, Isolated Memory State, Mock Broker Order Engine  
**Result:** **39 / 39 TESTS PASSED (100% Pass Rate)**

---

## 1. Test Verification Matrix

| Test ID | Verification Category | Test Description | Assertions Verified | Status |
| :---: | :--- | :--- | :--- | :---: |
| **01** | Entry Logic | Long SAME_CANDLE confirmation | Signal triggered at Delay 0 | ✅ PASS |
| **02** | Entry Logic | Long MACD_FIRST -> EMA confirmation within 2 candles | Delay 1 confirmation validated | ✅ PASS |
| **03** | Entry Logic | Long EMA_FIRST -> MACD confirmation within 2 candles | Delay 1 confirmation validated | ✅ PASS |
| **04** | Entry Invalidation | Long confirmation after >2 candles | Signal expired gracefully (>2 bars) | ✅ PASS |
| **05** | Entry Invalidation | Long leading indicator reversal | Setup canceled via INVALIDATED | ✅ PASS |
| **06** | Entry Logic | Short SAME_CANDLE confirmation | Signal triggered at Delay 0 | ✅ PASS |
| **07** | Entry Logic | Short MACD_FIRST -> EMA confirmation within 2 candles | Delay 1 confirmation validated | ✅ PASS |
| **08** | Entry Asymmetry | Short EMA_FIRST -> MACD later | EMA-first short rejected; no signal produced | ✅ PASS |
| **09** | Entry Invalidation | Short confirmation after >2 candles | Signal expired gracefully (>2 bars) | ✅ PASS |
| **10** | Entry Invalidation | Short leading MACD reversal | Setup canceled via INVALIDATED | ✅ PASS |
| **11** | Historical Scenario | SRF 04-Sep scenario validation | Verified exact historical short signal | ✅ PASS |
| **12** | Indicator Safety | Histogram value changes | Signal invariant to histogram expansion/contraction | ✅ PASS |
| **13** | Bar Timing Guard | Incomplete 1H forming candle | Incomplete candle strictly ignored | ✅ PASS |
| **14** | Session Boundary | 15:15 candle evaluation | Candle eligible strictly at/after 15:30 close | ✅ PASS |
| **15** | Idempotency | Duplicate processing lock | Duplicate signal key deduplicated | ✅ PASS |
| **16** | Restart Recovery | Process restart idempotency | Executed signal retained in persistent JSON | ✅ PASS |
| **17** | Position Management| Controlled position reversal | Verified sizing flip (e.g. +100 to -100 = 200 units) | ✅ PASS |
| **18** | Safety Boundaries | Live execution block | Hard-block verified; live orders prevented | ✅ PASS |
| **19** | Universe Contract | 218-symbol master list | Exactly 218 symbols present | ✅ PASS |
| **20** | Master Contract | Dynamic near-month futures discovery | Contract discovery & lot size matching verified | ✅ PASS |
| **21** | Alert Formatting | Single Telegram order dispatch | Formatted message without phantom fields | ✅ PASS |
| **22** | Execution Simulation| Mocked order fill & single alert | 1 message generated; fill price captured | ✅ PASS |
| **23** | Target Engine | Long target hit (+3.00%) | Position exited via SELL at +3.00%; alert sent | ✅ PASS |
| **24** | Target Engine | Short target hit (+1.50%) | Position exited via BUY at +1.50%; alert sent | ✅ PASS |
| **25** | Risk Engine | Long catastrophe stop-loss (-6.00%) | Position exited via SELL on -6.00% emergency SL | ✅ PASS |
| **26** | Risk Engine | Short catastrophe stop-loss (-6.00%) | Position exited via BUY on -6.00% emergency SL | ✅ PASS |
| **27** | Exit Precedence | Target not hit -> reversal executed | Controlled reversal executed when target untouched | ✅ PASS |
| **28** | Exit Precedence | Target hit before reversal | Position closed to FLAT before reversal logic | ✅ PASS |
| **29** | Exit Precedence | Catastrophe SL before reversal | Emergency SL triggered before reversal logic | ✅ PASS |
| **30** | Fill Accounting | Fill price vs candle close | Target evaluated strictly from actual fill price | ✅ PASS |
| **31** | Idempotency | Duplicate exit order guard | Duplicate exit orders blocked by state lock | ✅ PASS |
| **32** | State Recovery | Target/SL state across restarts | Recovered entry price and triggered target | ✅ PASS |
| **33** | Safety Guard | ANALYZE mode exit block | Live exit orders blocked during ANALYZE mode | ✅ PASS |
| **34** | Alert Verification | Paper exit alert schema | All 17 required audit fields present | ✅ PASS |
| **35** | Universe Filter | Blacklisted symbol filter | Blacklisted symbol blocked from execution | ✅ PASS |
| **36** | Universe Filter | Asymmetric universe entry filter | MARUTI skipped; SUNPHARMA accepted | ✅ PASS |
| **37** | Universe Filter | Unapproved opposite signal exit | WIPRO long exited to FLAT without shorting | ✅ PASS |
| **38** | Trailing Runner | HWM Runner Activation on Target | Runner activated, peak tracked, HWM SL set | ✅ PASS |
| **39** | Trailing Runner | HWM Runner Exit on Pullback Breach | Runner closed at trail SL; alert emitted | ✅ PASS |

---

## 2. Regression & State Invariant Summary
- **Zero Regressions:** Existing sequential confirmation, catastrophe stop-loss, and contract selection behaviors are 100% intact when trailing runners are inactive.
- **Strict Isolation:** Mocked broker sessions prevented any network egress or order generation to live endpoints.
- **Accounting Invariants:** All state transitions between FLAT -> ENTERED -> TARGET_HIT -> RUNNER_ACTIVE -> CLOSED satisfy strict deterministic finite-state machine (FSM) properties.
