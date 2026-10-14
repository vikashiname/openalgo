# SIGNAL CONTRACT: SIG-OI-001-PAPER-V1

**Contract Version:** `SIG-OI-001-PAPER-V1`  
**Strategy Hash (SHA-256):** `dc1063b1ccadd2e513c6d3f71a8a2f4f13465db852387204c0b27137249ed917`  
**Status:** FROZEN & IMMUTABLE  
**Deployment Tier:** PAPER TRADING SPECIFICATION  
**Author:** AGY Quantitative Research System  
**Effective Date:** September 2026  

---

## 1. STRATEGY IDENTITY & RATIONALE

* **Core Premise:** Institutional Long Unwinding Exhaustion.
* **Mechanism:** When a liquid futures contract experiences a price drop accompanied by open interest contraction, existing long market participants are liquidating/flushing positions without new aggressive short initiation. Once the order book is swept of weak-hand stops, supply exhausts, creating an institutional liquidity vacuum that triggers a sharp mean-reversion rebound on the subsequent trading session.
* **Research Provenance:**
  - Discovered in Phase 1 (`HYP-OI-0002`).
  - Audited & Falsification-tested in Phase 2 ($p < 10^{-6}$, Placebo $p = 0.000$).
  - Multi-Year Validated across 2022–2024 in Phase 3 (12 Walk-Forward folds, PBO 25.0%).
  - Causal Mechanism Confirmed in Phase 4 (Matched Controls $\Delta = +0.132\%$, $p = 10^{-5}$; Nested Regression $t_{\text{OI}} = -10.25$).

---

## 2. ELIGIBLE UNIVERSE

1. **Asset Class:** Indian National Stock Exchange (NSE) Equity Index and Stock Futures.
2. **Contract Type:** Standard Monthly Futures (`FUTIDX`, `FUTSTK`).
3. **Liquidity Threshold:** Minimum rolling 20-day median turnover $\ge ₹500\text{ Lakhs}$ (₹5 Crores).
4. **Active Expiry Filter:** Nearest near-month active contract.
5. **Rollover Purge Window:** Contracts with $\text{Days to Expiry (DTE)} \le 3$ calendar days are strictly **ineligible** to prevent roll volatility contamination.

---

## 3. REQUIRED DATA FIELDS

At signal time $T$ (15:30 IST), the engine requires:
* `trade_date`: YYYY-MM-DD (Official exchange session)
* `symbol`: Underlying NSE symbol
* `open`: Opening traded price
* `high`: Highest traded price
* `low`: Lowest traded price
* `close`: Official exchange closing price (30m VWAP)
* `traded_contracts`: Traded volume in contracts
* `turnover_lakh`: Traded turnover in Lakhs INR
* `open_interest`: End-of-day outstanding open contracts
* `days_to_expiry`: Calendar days to contract settlement

---

## 4. SIGNAL SPECIFICATION

A valid buy signal is triggered at Day $T$ market close if and only if:
1. **Price Dip:**
   $$\text{Return}_{1\text{D}}(T) = \frac{\text{Close}(T) - \text{Close}(T-1)}{\text{Close}(T-1)} < 0$$
2. **Open Interest Contraction:**
   $$\Delta\text{OI}_{\%}(T) = \frac{\text{OI}(T) - \text{OI}(T-1)}{\text{OI}(T-1)} < 0$$
3. **Data Validity:** All required fields non-null, non-zero, and positive.
4. **Rollover Check:** $\text{DTE}(T) > 3$.

---

## 5. EXECUTION CONTRACT & TIMESTAMPS

* **Signal Generation Time:** Day $T$ at 15:30 IST (after official Bhavcopy publication).
* **Order Placement Time:** Day $T+1$ at 09:00 IST (pre-market order book).
* **Entry Execution:** Day $T+1$ at 09:15 IST (Market Open Auction Fill).
* **Exit Execution:** Day $T+2$ at 09:15 IST (Market Open Auction Fill) (1-day holding horizon).
* **Execution Price:** Simulated at opening traded price with realistic slippage deduction.

---

## 6. TRANSACTION COST MODEL

All-in institutional cost deducted automatically from each trade:
* **Baseline Friction:** **8.0 basis points (0.080%)** roundtrip:
  - STT: 1.00 bps (0.02% on sell turnover)
  - Stamp Duty: 0.20 bps (0.002% on buy turnover)
  - Exchange Charges: 0.38 bps (0.0019% both legs)
  - SEBI Fee: 0.02 bps
  - GST: 0.30 bps (18% on fees)
  - Institutional Brokerage: 1.00 bps (flat ₹20/order)
  - Slippage & Market Impact: 5.00 bps (0.025% per leg)
* **Stress Scenario 1:** **18.0 basis points (0.180%)** (+10 bps slippage).
* **Stress Scenario 2:** **28.0 basis points (0.280%)** (+20 bps extreme friction).

---

## 7. PORTFOLIO ALLOCATION & CONSTRAINTS

* **Maximum Simultaneous Positions:** 10 (Top-10 portfolio).
* **Position Sizing:** Equal-weight fixed allocation:
  $$\text{Target Weight} = \frac{1}{\text{Max Positions}} = 10\% \text{ of Total Equity per Slot}$$
* **Maximum Gross Exposure:** $100\%$ (No margin leverage; fully cash-backed equity basis).
* **Maximum Single-Stock Exposure:** $10\%$ at time of entry.
* **Maximum Sector Exposure:** $30\%$ of total equity.
* **Cash Buffer:** Idle allocation remains in cash yielding standard risk-free rate ($6.5\%$ p.a.).
* **Ranking Heuristic for Signal Collisions:** When $>10$ signals trigger on Day $T$, rank candidate symbols by **most negative OI contraction intensity** ($\Delta\text{OI}_{\%}$ ascending), selecting the Top 10.

---

## 8. FAIL-CLOSED SAFETY PROTOCOL

A signal MUST BE REJECTED and order suppressed if:
1. `open_interest` is 0, missing, or unchanged for $>2$ consecutive sessions.
2. `traded_contracts` is 0 or turnover $< ₹500\text{ Lakhs}$.
3. Timestamp discontinuity or stale date detected.
4. Contract has expired or $\text{DTE} \le 3$.
5. Price is outside valid exchange price bands.
6. Portfolio hard risk limits are active (e.g. daily loss or drawdown circuit breaker).

---

## 9. IMMUTABILITY COMMITMENT

This signal contract is **FROZEN**.  
The automated production paper engine is strictly prohibited from altering these rules. Any future change requires a new formal hypothesis registration and a new versioned contract (`SIG-OI-001-PAPER-V2`).
