# MCX 1H EMA/MACD Asymmetric Confirmation Strategy (GOLDM, SILVERMIC, CRUDEM)

## 1. Overview & Architecture

This strategy adapts the production-grade architecture of `emacrossopen.py` for **MCX (Multi Commodity Exchange of India)** commodity futures, specifically designed for:
- **GOLDM** (Gold Mini — 100g contract, quoted per 10g in ₹)
- **SILVERMIC** (Silver Micro — 1kg contract, quoted per 1kg in ₹)
- **CRUDEM / CRUDEOILM** (Crude Oil Mini — 10 barrels contract, quoted per barrel in ₹)

### Key Files Created
- **Live / Paper Strategy Engine**: [`strategies/liveonopenalgo/emacrossmcx.py`](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/emacrossmcx.py)
- **Backtesting & Research Workspace**: [`backtesting/emacrossmcx/`](file:///Users/mac/Desktop/openalgo/backtesting/emacrossmcx/)
  - [`backtesting/emacrossmcx/emacrossmcx.py`](file:///Users/mac/Desktop/openalgo/backtesting/emacrossmcx/emacrossmcx.py) (Strategy Engine)
  - [`backtesting/emacrossmcx/backtest_emacrossmcx.py`](file:///Users/mac/Desktop/openalgo/backtesting/emacrossmcx/backtest_emacrossmcx.py) (Historical Simulation Engine)
  - [`backtesting/emacrossmcx/MCX_EMACROSS_BACKTEST_REPORT.md`](file:///Users/mac/Desktop/openalgo/backtesting/emacrossmcx/MCX_EMACROSS_BACKTEST_REPORT.md) (Automated Performance Report)

---

## 2. Core Strategy Logic

### A. Timeframe & Indicators
- **Timeframe:** Strictly **1-Hour (1H)** completed candles (zero repainting, forming bars filtered out).
- **Fast EMA:** 9-period EMA on completed close.
- **Slow EMA:** 26-period EMA on completed close.
- **MACD:** Fast 12, Slow 26, Signal 9 on completed close.
- **Confirmation Window:** 2 completed candles (`CONFIRMATION_WINDOW = 2`).

### B. Asymmetric Sequential Confirmation Engine
- **LONG Entries:**
  1. `SAME_CANDLE`: EMA 9 crosses above EMA 26 AND MACD crosses above Signal on the same 1H bar.
  2. `MACD_THEN_EMA`: MACD bullish cross occurs first; EMA bullish cross confirms within $\le 2$ candles.
  3. `EMA_THEN_MACD`: EMA bullish cross occurs first; MACD bullish cross confirms within $\le 2$ candles.
- **SHORT Entries (Asymmetric Trap Protection):**
  1. `SAME_CANDLE`: EMA 9 crosses below EMA 26 AND MACD crosses below Signal on the same 1H bar.
  2. `MACD_THEN_EMA`: MACD bearish cross occurs first; EMA bearish cross confirms within $\le 2$ candles.
  3. `EMA_FIRST`: **Strictly rejected** (`SHORT_EMA_FIRST_DISALLOWED`) to prevent lagging entries during sudden commodity short squeezes.
- **Dynamic Invalidation:** If the leading indicator flips directional bias before the second confirms, the pending setup is cancelled.
- **Expiration:** If not confirmed within 2 candles, the pending setup expires.

### C. Risk Management & Exit Priority Hierarchy
Evaluated strictly from the **actual executed fill price** (`pos_info["average_price"]`), never candle close:
1. **Priority 1: Emergency Catastrophe Stop Loss (-4.00% / -6.00%)**
   - Circuit breaker protecting against extreme overnight gaps.
2. **Priority 2: High-Water-Mark (HWM) Trailing Runner (0.35% trail, 0.50% profit floor)**
   - Once profit target is touched, converts into a trailing runner with a guaranteed profit floor.
3. **Priority 3: Break-Even Stop Loss**
   - Upon hitting the early profit milestone (+1.50% Long / +1.00% Short), stop loss is moved to break-even to eliminate downside risk.
4. **Priority 4: Profit Target (+2.50% Long / +1.50% Short)**
5. **Priority 5: Controlled Opposite Reversal Exit**

---

## 3. MCX Specifications & Timings

| Commodity | Base Symbol | Aliases | Unit / Contract Size | Tick Size | Point Value / Lot | Expiry Cycle |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| **Gold Mini** | `GOLDM` | `GOLD` | 100g (quoted per 10g) | ₹1.00 | ₹10.00 | 5th of contract month |
| **Silver Micro** | `SILVERMIC` | `SILVER`, `SILVERM` | 1 kg | ₹1.00 | ₹1.00 | End of contract month |
| **Crude Oil Mini** | `CRUDEOILM` | `CRUDEM`, `CRUDE` | 10 barrels | ₹1.00 | ₹10.00 | ~19th of month |

### MCX Market Hours
- **Trading Hours:** Monday to Friday, 09:00 to 23:30 IST.
- **Candle Completion Boundaries:** 10:00:02, 11:00:02, 12:00:02, 13:00:02, 14:00:02, 15:00:02, 16:00:02, 17:00:02, 18:00:02, 19:00:02, 20:00:02, 21:00:02, 22:00:02, 23:00:02, 23:30:02 IST.
- The engine automatically sleeps until the next completed 1H candle boundary.

---

## 4. Usage Instructions

### Run Automated Verification Test Suite (20 Test Cases)
```bash
python3 strategies/liveonopenalgo/emacrossmcx.py --test
```

### Run Live/Paper Trading Bot for All 3 Commodities
```bash
python3 strategies/liveonopenalgo/emacrossmcx.py
```

### Run for a Specific Commodity
```bash
# Crude Oil Mini
python3 strategies/liveonopenalgo/emacrossmcx.py --symbol CRUDEM

# Gold Mini
python3 strategies/liveonopenalgo/emacrossmcx.py --symbol GOLDM

# Silver Micro
python3 strategies/liveonopenalgo/emacrossmcx.py --symbol SILVERMIC
```

### Run a Single Evaluation Cycle (e.g. for Cron or Watchdog)
```bash
python3 strategies/liveonopenalgo/emacrossmcx.py --once
```

### Run Historical Backtest
```bash
# Backtest all 3 commodities over the past 365 days
python3 backtesting/emacrossmcx/backtest_emacrossmcx.py --days 365

# Backtest specific commodities
python3 backtesting/emacrossmcx/backtest_emacrossmcx.py --symbols GOLDM,CRUDEM --days 180
```

---

## 5. Configuration & Environment Variables

Create or update `.env` to configure parameters:

```env
OPENALGO_HOST=http://127.0.0.1:5000
OPENALGO_API_KEY=your_openalgo_api_key
EXCHANGE=MCX
PRODUCT=NRML
INTERVAL=1h
FAST_EMA_PERIOD=9
SLOW_EMA_PERIOD=26
MACD_FAST_PERIOD=12
MACD_SLOW_PERIOD=26
MACD_SIGNAL_PERIOD=9
CONFIRMATION_WINDOW=2

# Risk Management
LONG_PROFIT_TARGET_PCT=2.50
SHORT_PROFIT_TARGET_PCT=1.50
CATASTROPHE_SL_PCT=4.00
EARLY_LONG_TP_PCT=1.50
EARLY_SHORT_TP_PCT=1.00
MOVE_SL_TO_BE=true
ENABLE_TRAILING_RUNNER=true
RUNNER_TRAIL_PCT=0.35
RUNNER_PROFIT_FLOOR_PCT=0.50

# Telegram Notifications
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```
