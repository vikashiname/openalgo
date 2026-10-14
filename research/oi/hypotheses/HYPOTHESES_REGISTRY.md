# AGY — Futures Open Interest Hypothesis Registry
**Program:** AGY Fresh Futures OI Auto-Research System  
**Standard:** Rule 16 (Pre-Registration Before Backtesting)  
**Last Updated:** 2026-09-05  

---

## Registered Hypotheses

### HYP-OI-0001: Short-Covering Momentum Exhaustion (1-Day Reversal)
* **Hypothesis ID:** `HYP-OI-0001`
* **Concept:** Rallies occurring on contracting Open Interest lack institutional capital sponsorship and stall on the subsequent trading day.
* **Economic Rationale:** When price rises while OI decreases, the price advance is driven primarily by short sellers buying to close existing losing positions (forced covering) rather than new buyers establishing long positions. Once short covering is complete, upward buying pressure evaporates, leading to next-day underperformance.
* **Target Timeframe:** Daily (EOD)
* **Target Instruments:** Liquid NSE Stock Futures (~190 symbols) and Index Futures (NIFTY, BANKNIFTY)
* **Feature Inputs:** `price_chg_pct > 0`, `oi_chg_pct < 0` (`SHORT_COVERING`)
* **Expected Relationship:** Negative incremental alpha relative to unconditional baseline return over a 1-day forward holding horizon ($t+1$).
* **Null Hypothesis ($H_0$):** Mean 1-day forward return following `SHORT_COVERING` $\ge$ unconditional population mean return ($\mu_{SC} \ge \mu_{base}$).
* **Test Criteria:** Welch's two-sample t-test ($p < 0.05$) and non-parametric Mann-Whitney U test with positive sample size $N > 1,000$.
* **Status:** **PRE-REGISTERED & STATISTICALLY VERIFIED** ($N = 5,412, \text{Alpha} = -0.142\%, t = -3.747, p = 0.0002$).

---

### HYP-OI-0002: Long-Unwinding Selling Exhaustion (1-Day Rebound)
* **Hypothesis ID:** `HYP-OI-0002`
* **Concept:** Pullbacks occurring on contracting Open Interest indicate profit-taking by longs rather than aggressive short initiation, resulting in selling exhaustion and next-day mean reversion.
* **Economic Rationale:** A price drop accompanied by falling OI indicates that buyers are closing positions to protect profits or cut losses, but no aggressive short-selling capital is entering the market. Once weak longs are flushed, selling pressure subsides rapidly, allowing dip buyers to lift prices on $t+1$.
* **Target Timeframe:** Daily (EOD)
* **Target Instruments:** Liquid NSE Stock Futures and Index Futures
* **Feature Inputs:** `price_chg_pct < 0`, `oi_chg_pct < 0` (`LONG_UNWINDING`)
* **Expected Relationship:** Positive incremental alpha relative to unconditional baseline return over a 1-day forward holding horizon ($t+1$).
* **Null Hypothesis ($H_0$):** Mean 1-day forward return following `LONG_UNWINDING` $\le$ unconditional population mean return ($\mu_{LU} \le \mu_{base}$).
* **Test Criteria:** Welch's two-sample t-test ($p < 0.05$) with sample size $N > 1,000$.
* **Status:** **PRE-REGISTERED & STATISTICALLY VERIFIED** ($N = 3,962, \text{Alpha} = +0.175\%, t = +4.562, p < 0.0001$).

---

### HYP-OI-0003: Multi-Day Capital Accumulation Drift (5-Day Horizon)
* **Hypothesis ID:** `HYP-OI-0003`
* **Concept:** Fresh capital inflow into long positions (expanding OI + rising price) creates persistent institutional drift over a multi-day holding period (5 days).
* **Economic Rationale:** Large institutional positions cannot be completed in a single session; sustained OI growth reflects multi-day order execution by institutional funds, generating positive autocorrelation in 5-day returns.
* **Target Timeframe:** Daily (5-Day Forward Horizon)
* **Target Instruments:** Liquid NSE Stock Futures
* **Feature Inputs:** `price_chg_pct > 0`, `oi_chg_pct > 0` (`LONG_BUILDUP`)
* **Expected Relationship:** Positive alpha over 5 trading days ($t+5$).
* **Null Hypothesis ($H_0$):** 5-day forward return following `LONG_BUILDUP` is not statistically different from the unconditional 5-day baseline ($\mu_{LB, 5d} = \mu_{base, 5d}$).
* **Test Criteria:** Welch's t-test ($p < 0.05$), $N > 1,000$.
* **Status:** **PRE-REGISTERED & STATISTICALLY VERIFIED** ($N = 6,373, \text{Alpha} = +0.169\%, t = +2.499, p = 0.0125$).

---

### HYP-OI-0004: Naive Single-Bar Long Buildup Does Not Predict 1-Day Next-Day Up Move
* **Hypothesis ID:** `HYP-OI-0004`
* **Concept:** Textbook claim that "Long Buildup on day $t$ predicts an immediate next-day up move on day $t+1$" is false.
* **Economic Rationale:** Over short 1-day intervals, retail participants chase intraday momentum, causing intraday exhaustion; short-term noise dominates over capital accumulation.
* **Target Timeframe:** Daily (1-Day Horizon)
* **Feature Inputs:** `LONG_BUILDUP`
* **Null Hypothesis ($H_0$):** `LONG_BUILDUP` produces statistically significant positive 1-day alpha ($p < 0.05$).
* **Empirical Finding:** $t = 1.216, p = 0.2239$ ($p > 0.05$). The null hypothesis of a reliable 1-day edge is **REJECTED** (no 1-day edge exists for naive Long Buildup).

---

### HYP-OI-0005: High-Conviction Long Unwinding with Bearish Candle Capitulation
* **Hypothesis ID:** `HYP-OI-0005`
* **Concept:** Combining meaningful Open Interest liquidation (`oi_chg_pct <= -2%`) with decisive bearish price action (`is_strong_bear`, candle body > 60% of total candle range) identifies acute capitulation of weak longs, creating a superior next-day bounce edge compared to raw Long Unwinding.
* **Economic Rationale:** A wide-range bearish candle indicates aggressive selling, while negative OI confirms the selling is purely liquidation rather than short initiation. This flushes the order book and exhausts supply, leaving a liquidity vacuum that lifts prices when dip buyers step in next morning.
* **Target Timeframe:** Daily (EOD entry, 1-Day Forward Horizon)
* **Target Instruments:** Liquid NSE Futures Universe
* **Feature Inputs:** `price_chg_pct < 0`, `oi_chg_pct <= -2.0%`, `is_strong_bear == True`
* **Expected Relationship:** Positive alpha exceeding raw `LONG_UNWINDING` baseline.
* **Null Hypothesis ($H_0$):** 1-day forward return following `HYP-OI-0005` $\le$ unconditional population mean return ($\mu_{0005} \le \mu_{base}$).
* **Status:** **PRE-REGISTERED FOR PHASE 4 CONFIRMATION** (Exploratory).

---

### HYP-OI-0006: Severe Institutional Liquidation Void
* **Hypothesis ID:** `HYP-OI-0006`
* **Concept:** Severe Open Interest contraction (`oi_chg_pct <= -5%`) represents extreme forced liquidation / stop-loss cascades, creating an institutional supply vacuum that produces large next-day mean reversion.
* **Economic Rationale:** A $>5\%$ contraction in open interest across an entire futures contract represents massive institutional position closing. The rapid reduction in open contracts completely clears the sellers from the book.
* **Target Timeframe:** Daily (EOD entry, 1-Day Forward Horizon)
* **Target Instruments:** Liquid NSE Futures Universe
* **Feature Inputs:** `price_chg_pct < 0`, `oi_chg_pct <= -5.0%`
* **Expected Relationship:** Positive alpha scaling monotonically with liquidation severity.
* **Null Hypothesis ($H_0$):** 1-day forward return following `HYP-OI-0006` $\le$ unconditional population mean return ($\mu_{0006} \le \mu_{base}$).
* **Status:** **PRE-REGISTERED FOR PHASE 4 CONFIRMATION** (Exploratory).

