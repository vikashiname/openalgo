# NIFTY Covered Call: Isolated Research Audit & Risk Control Report

**Date:** 2026-10-16  
**Workspace:** `backtesting/nifty_covered_call/`  
**Dataset:** NSE Continuous Daily Futures & Synthetic Options (`NIFTY_continuous.parquet`, 635 trading sessions, 2022-01-03 to 2024-07-31)  
**Lot Size:** 50 (Historical Standard NIFTY Contract)  
**Execution Files:**
- Research Runner: [`backtesting/nifty_covered_call/research_audit_runner.py`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/research_audit_runner.py)
- Metrics CSV: [`backtesting/nifty_covered_call/research_comparison_metrics.csv`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/research_comparison_metrics.csv)
- Trade Log CSV: [`backtesting/nifty_covered_call/research_all_trades.csv`](file:///Users/mac/Desktop/openalgo/backtesting/nifty_covered_call/research_all_trades.csv)

---

## 1. Executive Performance Comparison Matrix

All figures reflect full transaction costs (brokerage, STT, exchange turnover fees, SEBI charges, stamp duty, GST) and realistic execution slippage (1.0 pt on futures, 0.5 pt on options), unless explicitly labeled "Raw No Costs".

| Variant | Trades | Win Rate | Profit Factor | Total Gross P&L | Total Costs | Total Net P&L | Max Closed DD | Sharpe | Calmar | False Targets |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Buy & Hold NIFTY (Benchmark)** | — | — | — | ₹4,21,778 | — | ₹4,21,778 | ₹99,663 | — | 4.23 | — |
| **1. Baseline (Raw No Costs)** | 23 | 78.26% | 6.66 | ₹2,64,981 | ₹0 | ₹2,64,981 | ₹23,639 | 2.89 | 11.21 | 5 |
| **2. Baseline (Net of Costs)** | 23 | 73.91% | 6.10 | ₹2,64,981 | ₹12,204 | ₹2,52,776 | ₹25,130 | 2.76 | 10.06 | 5 |
| **3A. DTE Entry $\ge$ 10d** | 32 | 71.88% | 5.73 | ₹3,13,034 | ₹16,895 | ₹2,96,138 | ₹30,398 | 2.51 | 9.74 | 5 |
| **3B. DTE Entry $\ge$ 15d (Candidate)** | **27** | **77.78%** | **7.09** | **₹3,16,524** | **₹14,377** | **₹3,02,147** | **₹25,130** | **3.01** | **12.02** | 5 |
| **3C. DTE Entry $\ge$ 20d (Strict)** | 24 | 75.00% | 6.46 | ₹2,83,560 | ₹12,752 | ₹2,70,808 | ₹25,130 | 2.88 | 10.78 | 5 |
| **4. Control 1: Futures Stop (-2.0%)** | 23 | 73.91% | 5.40 | ₹2,58,597 | ₹12,203 | ₹2,46,394 | ₹25,130 | 2.57 | 9.80 | 3 |
| **5. Control 2: Net M2M Cap (-₹20k)** | 23 | 73.91% | 5.40 | ₹2,58,597 | ₹12,203 | ₹2,46,394 | ₹25,130 | 2.57 | 9.80 | 4 |
| **6. Control 3: Trend Exit (<100-EMA)** | 23 | 69.57% | 4.33 | ₹2,41,933 | ₹12,200 | ₹2,29,733 | ₹32,980 | 2.31 | 6.97 | 3 |
| **7. Control 4: Trailing Exit (15k/40%)** | 23 | 78.26% | 6.18 | ₹2,67,948 | ₹12,209 | ₹2,55,739 | ₹25,130 | 2.80 | 10.18 | 5 |
| **8. Combined Architecture (Justified)**| **27** | **81.48%** | **6.47** | **₹3,19,212** | **₹14,384** | **₹3,04,828** | **₹25,130** | **2.91** | **12.13** | **3** |

---

## 2. Research Task A: Existing Backtest Validation Findings

### 1. P&L Accounting & Leg Separation Audit
* **Futures Leg vs. Option Leg Disparity**:
  Across the 23 baseline trades, the **Futures Leg** generated **+₹2,89,275.00** gross profit, while the **Short Call Option Leg** generated **-₹24,294.38** gross loss.
* **Why the Option Leg is Net Negative**:
  In a persistent secular bull market, strong upside runs blow past the short call strike, hitting the 3.0x stop loss multiple (-₹13,000 to -₹16,000 per hit). The short call acts purely as a **variance and drawdown reducer**, sacrificing upside tail return in exchange for compressing drawdowns from ₹99,663 (Buy & Hold) down to ₹25,130.

### 2. Transaction Costs Impact
* In the existing `backtest_covered_call.py`, transaction costs were omitted (₹0).
* Adding statutory Indian F&O costs (Brokerage, STT, Exchange turnover, Stamp Duty, SEBI, GST) and 1.0 pt futures / 0.5 pt option slippage consumes **₹12,204.29** (~₹530.62 per monthly cycle).
* Net P&L drops from **₹2,64,980.62** to **₹2,52,776.33**, reducing baseline profit factor from 6.66 to 6.10 and win rate from 78.26% to 73.91%.

### 3. The "Downside False Profit Target" Trap Confirmed
* In the baseline, **100% of losing trades (5 out of 5)** were recorded with the exit reason:
  `PROFIT_TARGET_HIT (90% Decay)`.
* **Mechanics**: When the underlying market crashed mid-cycle, the out-of-the-money call option lost delta and collapsed toward zero. The naive baseline logic saw the option price $\le 10\%$ of entry, declared "Profit Target Hit", and closed both legs right at the bottom of the selloff, booking large futures losses (-₹7.8k, -₹12.4k, -₹3.4k, -₹8.8k, -₹14.3k).
* **Takeaway**: Option profit-taking must be explicitly conditional on `net_m2m > 0`.

### 4. Benchmark Comparison
* Buy & Hold NIFTY generated ₹4,21,777.50 (+50.89%) but suffered a deep **-₹99,662.50 drawdown** (Calmar 4.23).
* The Covered Call strategy captured **~60% of Buy & Hold returns** while slashing max drawdown by **74.8%** (from ₹99.7k down to ₹25.1k), delivering a superior Calmar ratio of **10.06**.

### 5. Data & Sample Size Limitations
* **Sample Size**: 23 trades over 2.5 years (32 monthly expiries) is a small sample with broad standard error bounds.
* **Regime Bias**: 2022–2024 was an overwhelmingly bullish environment for Indian equities. Stress testing across prolonged bear regimes (such as 2008 or 2011) is required before treating downside drawdown figures as definitive.

---

## 3. Research Task B: Minimum DTE Entry Filter Evaluation

| Entry Filter | Trades | Win Rate | Net P&L | Max Closed DD | Profit Factor | Sharpe |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Permissive: DTE $\ge$ 10d** | 32 | 71.88% | ₹2,96,138 | ₹30,398 | 5.73 | 2.51 |
| **Baseline: 22d $\le$ DTE $\le$ 35d** | 23 | 73.91% | ₹2,52,776 | ₹25,130 | 6.10 | 2.76 |
| **Candidate: DTE $\ge$ 15d** | **27** | **77.78%** | **₹3,02,147** | **₹25,130** | **7.09** | **3.01** |
| **Strict: DTE $\ge$ 20d** | 24 | 75.00% | ₹2,70,808 | ₹25,130 | 6.46 | 2.88 |

### Key Findings on DTE Filter:
1. **DTE $\ge$ 15d is the Optimal Threshold**:
   * It boosts Net P&L by **+₹49,370.74** (+19.5% gain over baseline net) by permitting valid re-entries when early profit targets or stops clear capital mid-cycle.
   * Win rate rises to **77.78%** and Profit Factor reaches **7.09** (highest across all tested configurations).
   * Sharpe ratio improves to **3.01** without increasing max drawdown (remains locked at ₹25,130).
2. **Entering Below 15 DTE Degrades Performance**:
   * Allowing entries down to DTE 10 (Variant 3A) increases trade count to 32 but causes drawdown to expand to ₹30,398, while Sharpe degrades to 2.51 due to severe gamma swings and churn fees.
3. **Historical Expiry Contract Reality**:
   * Entering a monthly cycle with $<15$ DTE when the roll trigger is set at 10 DTE guarantees positions stay open for only 1 to 4 sessions, destroying edge through double transaction friction.

---

## 4. Research Task C: Isolated Risk Controls Evaluation

### Control 1: Futures Catastrophe Stop (-2.0% from Entry)
* **Net P&L**: ₹2,46,394 (down ₹6,382 vs. Baseline Net).
* **Profit Factor**: 5.40 (down from 6.10).
* **Analysis**: While it reduced false downside target exits from 5 to 3 by stopping out runaway bear days, on 1 trade it triggered right before an intraday reversal, leaving money on the table.
* **Execution Reality**: On gap-down sessions, daily bars breached through the 2.0% stop to -2.5% (-₹21,274), proving that fixed stop thresholds cannot guarantee exact execution prices in equity futures.

### Control 2: Combined Position M2M Loss Cap (-₹20,000)
* **Net P&L**: ₹2,46,394 | **Profit Factor**: 5.40.
* **Analysis**: Performs almost identically to Control 1 because a 2% futures move on Nifty (400 pts $\times$ 50 = ₹20,000) minus ~₹3,000 call decay cushion hits the ₹20k net M2M mark at roughly the same price level.

### Control 3: Dynamic Trend-Breakdown Exit (Close < 100-EMA) — **REJECTED**
* **Net P&L**: ₹2,29,733 (Severe ₹23,043 reduction vs. Baseline Net).
* **Win Rate**: Drops to **69.57%** | **Max Drawdown**: Expands to **₹32,980** | **Profit Factor**: **4.33**.
* **Why Rejected**: Daily close crosses below the 100-EMA are notorious for whipsawing in range-bound corrections. It repeatedly liquidated trades at low prices only for the index to bounce back above the EMA two sessions later.

### Control 4: High-Water-Mark Trailing Exit (Peak $\ge$ ₹15k, 40% Pullback)
* **Net P&L**: ₹2,55,739 (+₹2,963 gain over Baseline Net).
* **Win Rate**: 78.26% | **Sortino**: Rises to **9.03**.
* **Analysis**: Preserves late-cycle gains on runaway winners without prematurely clipping developing trades.

### Control 5: Combined Selective Risk Architecture
* **Rules**: 15-Day Minimum DTE Entry + Futures 2.0% Stop + Trailing Profit Lock (₹15k peak, 40% buffer) + False Target Protection (`net_m2m > 0`).
* **Performance**:
  * **Net P&L**: **₹3,04,828** (Highest of all models).
  * **Win Rate**: **81.48%** (22 wins / 5 losses).
  * **Calmar Ratio**: **12.13**.
  * **Max Drawdown**: ₹25,130.

---

## 5. Summary of Created Research Artifacts

All existing files in `backtesting/nifty_covered_call/` remain completely untouched. The following new research artifacts were generated:
1. `backtesting/nifty_covered_call/research_audit_runner.py`: Dedicated standalone experiment runner.
2. `backtesting/nifty_covered_call/research_comparison_metrics.csv`: Machine-readable comparison table of all 10 model variants.
3. `backtesting/nifty_covered_call/research_all_trades.csv`: Granular trade log (entries, exits, spot levels, option strikes, gross P&L, fees, and exit reasons).
4. `backtesting/nifty_covered_call/RESEARCH_AUDIT_REPORT.md`: This comprehensive audit document.
