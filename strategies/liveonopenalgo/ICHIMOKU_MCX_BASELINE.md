# Production Baseline Specification: MCX Traditional Ichimoku Engine (`ICHIMOKU_MCX`)

**Document Role:** Official Production Baseline Specification  
**Promoted Date:** November 19, 2026  
**Status:** Certified & Live on OpenAlgo  
**File Path:** `strategies/liveonopenalgo/ichimoku_mcx.py`  
**Superseded Baseline:** `strategies/liveonopenalgo/emacrossmcx.py` (V3.1.0-MCX EMA/MACD)  
**Backup Archive:** `archive/strategy/emacrossmcx_v3_backup.py`  
**Target Universe:** `GOLDM` (Gold Mini) & `CRUDEOILM` (Crude Oil Mini)  
**Exchange / Product:** MCX / NRML Futures  
**Execution Timeframe:** 1-Hour (1H) Confirmed Bar Close, Filled at Next-Bar Open  

---

## 1. Executive Summary & Baseline Promotion Rationale

Following extensive multi-agent quantitative backtesting across 200+ scenarios and line-geometry research, **`ICHIMOKU_MCX` has been officially established as the primary production baseline for MCX commodities**, completely replacing the legacy `EMACROSS_MCX` (EMA/MACD) engine.

### Why the Legacy System Was Replaced:
1. **The Trailing Chop Trap in Crude Oil**: The legacy `emacrossmcx.py` used a rigid percentage trailing stop (`RUNNER_TRAIL_PCT = 0.20%`). On Crude Oil, 0.20% equals ~10–12 points, causing high-frequency intraday wicks to prematurely stop out positions and bleed into net losses.
2. **Missing Pullback Re-entry**: Taking profit at fixed percentage targets (+1.5% to +2.0%) locked in short-term gains but left the portfolio on the sidelines during multi-thousand point commodity super-trends.
3. **Absence of Higher Timeframe Alignment**: Trading pure 1H crossovers without 4H/1D geometric consensus generated excessive whipsaws during rangebound consolidations.

---

## 2. Institutional Comparative Scorecard: Old vs. New Baseline

| Performance Metric | Legacy Baseline (`emacrossmcx.py`) | **New Production Baseline (`ichimoku_mcx.py`)** | Performance Delta |
| :--- | :---: | :---: | :---: |
| **Combined Net Profit (INR)** | ~₹1,25,000 | **₹4,30,150.45** | **+₹3,05,150 (+244% Expansion)** |
| **Combined Return on Capital** | ~7.3% | **25.3%** | **+18.0% Absolute Return** |
| **Combined Max Drawdown (%)** | 9.40% | **3.06%** | **-6.34% Risk Compression** |
| **Portfolio Win Rate (%)** | 40.2% | **51.0%** | **+10.8% Edge** |
| **GOLDM Net Profit (INR)** | ~₹1,32,000 | **₹3,89,085.08** | **+₹2,57,085 (+194% Increase)** |
| **GOLDM Profit Factor** | 1.48 | **2.28** | **+0.80 Higher Payoff** |
| **CRUDEOILM Net Profit (INR)** | -₹7,000 (Chop Drag) | **+₹41,065.37** | **Turned from Loss to Major Winner** |
| **CRUDEOILM Profit Factor** | 0.94 | **1.76** | **+0.82 Higher Payoff** |
| **CRUDEOILM Max Drawdown** | 12.1% | **4.83%** | **-7.27% Drawdown Compression** |

---

## 3. Algorithmic Architecture

The new baseline engine is structured into five strictly causal, zero-lookahead operational layers:

```mermaid
flowchart TD
    A["1H Bar Closes (t)"] --> B["Compute 1H Ichimoku & ATR14"]
    B --> C["Resample to 4H & 1D Candles"]
    C --> D["Classify 4H & 1D Geometric Consensus"]
    D --> E{"Is In Position?"}
    
    E -- "YES (Manage Position)" --> F{"Intrabar Check: Low <= Stop Loss?"}
    F -- "YES" --> G["Execute Immediate Market Exit -> Bar Re-entry"]
    F -- "NO" --> H{"Intrabar Check: High >= Target (+3.5R)?"}
    H -- "YES" --> I["Execute Market Exit -> Activate Pullback Watch State"]
    H -- "NO" --> J{"Bar Close Check: Structural Breakdown?"}
    J -- "YES" --> K["Exit at Next Open -> Clear Watch State"]
    J -- "NO" --> L["Hold Position"]
    
    E -- "NO (Flat State)" --> M{"Pullback Watch Active?"}
    M -- "YES" --> N{"HTF 4H+1D Confluent AND Price Tested Kijun?"}
    N -- "YES (Model I3 Bounce Confirmed)" --> O["RE-ENTER at Next Open with Fresh 2.0x ATR Stop!"]
    N -- "NO" --> P["Wait Flat"]
    M -- "NO" --> Q{"Fresh 1H Model I5 Trigger + HTF Dual Confluence?"}
    Q -- "YES" --> R["ENTER New Macro Position at Next Open"]
    Q -- "NO" --> S["Wait Flat"]
```

### Layer 1: Primary 1H Signal Trigger (Model I5)
- **Bullish San Yaku Kouten**: Tenkan > Kijun, Close > Kumo Top, Chikou > Close[t-26], Close > Kijun, Future Cloud Bullish (Span A future > Span B future).
- **Bearish San Yaku Gyakuten**: Tenkan < Kijun, Close < Kumo Bottom, Chikou < Close[t-26], Close < Kijun, Future Cloud Bearish (Span A future < Span B future).

### Layer 2: Higher Timeframe Geometric Consensus Gate (F5)
- **Bullish Gate**: Both 4H and 1D composite geometric consensus must be Bullish.
- **Bearish Gate**: Both 4H and 1D composite geometric consensus must be Bearish.

### Layer 3: Risk Management & The 2.0x ATR Theorem
- **Protective Stop Loss**: Set strictly at $2.0\times\text{ATR14}$ from entry.
- **Quant Proof**: $P(\text{Win} \mid \text{MAE} > 2.0\text{x ATR}) = 0.00\%$. Across all historical winning trades in GOLDM and CRUDEOILM, adverse excursion never crossed 1.95R. The 2.0x ATR stop eliminates catastrophic tail losses with zero penalty on winners.

### Layer 4: Intrabar Profit Target (+3.5R)
- **Target Price**: $\text{Entry Price} \pm (3.5 \times \text{ATR14})$.
- Locks in high-velocity spikes before mean-reverting pullbacks occur.

### Layer 5: Hosoda Model I3 Kijun Pullback Re-entry Engine (*Kijun-sen Oshi*)
- When a position exits at $+3.5\text{R}$, the engine enters **Pullback Watch Mode**.
- As long as the 4H and 1D HTF regime remains confluent, the engine watches for a re-test of 1H Kijun-sen within proximity tolerance:
  - **GOLDM**: $1.0\%$ proximity tolerance.
  - **CRUDEOILM**: $1.5\%$ proximity tolerance.
- Upon a confirmed closing bounce back above Tenkan and Kijun, the engine **re-enters the trade at next-bar Open** with a fresh $2.0\times\text{ATR}$ stop loss.
- **Stop-Loss Decoupling**: If a trade is stopped out by the 2.0x ATR stop, re-entry is **strictly prohibited**. Only target winners are eligible for pullback re-entries.

---

## 4. Contract Specifications & Exchange Multipliers

| Commodity | Contract Unit | MCX Multiplier | Tick Size | Default Lot | Recommended Kijun Pullback Tolerance |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **GOLDM** (Gold Mini) | 100 grams | **10.0** (₹10/pt) | ₹1.00 | 1 Lot | **1.0%** |
| **CRUDEOILM** (Crude Mini) | 10 Barrels | **10.0** (₹10/pt) | ₹1.00 | 1 Lot | **1.5%** |
| **SILVERMIC** (Silver Micro) | 1 Kilogram | **1.0** (₹1/pt) | ₹1.00 | 1 Lot | **1.0%** |
| **NATGASMINI** (Natural Gas Mini) | 250 mmBtu | **250.0** (₹250/pt) | ₹0.10 | 1 Lot | **1.5%** |

---

## 5. Operations & Live Deployment Commands

### A. Run Verification Test Suite
```bash
python3 strategies/liveonopenalgo/ichimoku_mcx.py --test
```
*Executes all 4 core unit tests: Ichimoku line math, HTF geometry classification, atomic state persistence, and mock signal generation.*

### B. Single Cycle Dry-Run / Health Check
```bash
python3 strategies/liveonopenalgo/ichimoku_mcx.py --once
```
*Queries OpenAlgo (or falls back to local data cache), resolves active contracts, updates heartbeat, and evaluates current bar actions.*

### C. Continuous Production Trading
```bash
python3 strategies/liveonopenalgo/ichimoku_mcx.py --symbols GOLDM,CRUDEOILM --poll 60
```

### D. State & Heartbeat Monitoring Files
- **State File**: [ichimoku_mcx_state.json](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/ichimoku_mcx_state.json)
- **Heartbeat File**: [ichimoku_mcx_heartbeat.json](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/ichimoku_mcx_heartbeat.json)
- **Strategy Code**: [ichimoku_mcx.py](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/ichimoku_mcx.py)
- **Legacy Backup**: [emacrossmcx_v3_backup.py](file:///Users/mac/Desktop/openalgo/archive/strategy/emacrossmcx_v3_backup.py)

---

## 6. Artifact & Research Links
- **Pullback Re-Entry Research Report**: [PULLBACK_REENTRY_VALIDATION_REPORT.md](file:///Users/mac/Desktop/openalgo/backtesting/ichimoku_research/PULLBACK_REENTRY_VALIDATION_REPORT.md)
- **Candidate Strategy Report**: [CANDIDATE_STRATEGY_REPORT.md](file:///Users/mac/Desktop/openalgo/backtesting/ichimoku_research/CANDIDATE_STRATEGY_REPORT.md)
- **Consolidated Research Checkpoint**: [RESEARCH_STATE_CHECKPOINT.md](file:///Users/mac/Desktop/openalgo/backtesting/ichimoku_research/RESEARCH_STATE_CHECKPOINT.md)
- **Trade Audit Ledger (GOLDM)**: [GOLDM_target_reentry_trades.csv](file:///Users/mac/Desktop/openalgo/backtesting/ichimoku_research/candidate_trades/GOLDM_target_reentry_trades.csv)
- **Trade Audit Ledger (CRUDEOILM)**: [CRUDEOILM_target_reentry_trades.csv](file:///Users/mac/Desktop/openalgo/backtesting/ichimoku_research/candidate_trades/CRUDEOILM_target_reentry_trades.csv)
