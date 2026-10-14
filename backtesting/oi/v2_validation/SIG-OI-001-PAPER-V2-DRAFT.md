# SIGNAL CONTRACT: SIG-OI-001-PAPER-V2-DRAFT

**Contract Version:** `SIG-OI-001-PAPER-V2-DRAFT`  
**Draft Status:** PROPOSED RESEARCH SPECIFICATION (PENDING FORMAL GOVERNANCE APPROVAL)  
**Parent Contract:** `SIG-OI-001-PAPER-V1` (Frozen Contract Hash: `dc1063b1ccadd2e513c6d3f71a8a2f4f13465db852387204c0b27137249ed917`)  
**Deployment Tier:** RESEARCH & FORWARD SHADOW VALIDATION ONLY (LIVE TRADING HARD-BLOCKED)  
**Author:** AGY Quantitative Research & Governance Architecture  
**Effective Date:** October 2026  

---

> [!IMPORTANT]
> **GOVERNANCE STATUS: DRAFT CANDIDATE ONLY**  
> This document specifies the proposed V2 contract upgrade for the OIFNO Long-Unwinding Rebound strategy. It incorporates all findings from the Pre-Implementation Stress Suite. This draft is **strictly non-operational** until formal governance sign-off and completion of the mandatory 60-session forward shadow observation protocol. Live order placement remains strictly disabled.

---

## 1. STRATEGY IDENTITY & CAUSAL MECHANISM

* **Strategy Name:** NFO Single-Stock Futures Long-Unwinding Capitulation Rebound (OIFNO V2).
* **Core Premise:** Institutional Long Unwinding Exhaustion with Deep Price Capitulation.
* **Economic Mechanism:**
  When a liquid single-stock futures contract experiences a severe price drop ($\text{Ret}_{1\text{D}} \le -1.5\%$) accompanied by substantial open interest contraction ($\Delta\text{OI}_{\%} \le -2.0\%$) and decisive intraday selling dominance (bearish candle body ratio), institutional long market participants are liquidating/flushing positions without aggressive new short initiation. Once the order book is swept of weak-hand stops, supply exhausts, creating an institutional liquidity vacuum that triggers a sharp mean-reversion rebound on the subsequent trading session.
* **V2 Enhancements over Frozen V1:**
  1. **Formalization of OI Threshold:** Codifies the mandatory $\Delta\text{OI}_{\%} \le -2.0\%$ contraction threshold (resolving the V1 underspecification where $\Delta\text{OI} < 0$ admitted 48,289 noisy coin-toss signals).
  2. **Resolution of Candle Body Ambiguity:** Codifies the bearish candle body formula and resolves the conflicting 0.40 versus 0.60 thresholds by establishing Tier A ($\ge 0.40$, institutional standard) and Tier B ($> 0.60$, conservative high-conviction).
  3. **Capitulation Gate ($\text{Ret}_{1\text{D}} \le -1.5\%$):** Filters out minor noise dips where the expected rebound amplitude is insufficient to cover execution friction, doubling mean net expectancy.
  4. **Execution Limit Collar (+30 bps) & Gap Protection (+1.5%):** Formalizes strict opening limit order collar and gap-chase suppression to guard against slippage beyond the 21.5 bps breakeven friction threshold.
  5. **Rejection of Trailing Stops:** Permanently locks the deterministic Day T+2 Open auction exit; trailing stops are formally prohibited due to morning whipsaw liquidation risk.

---

## 2. ELIGIBLE UNIVERSE & LIQUIDITY CRITERIA

1. **Asset Class:** Indian National Stock Exchange (NSE) Equity Stock Futures (`instrument_type == 'FUTSTK'`).
2. **Contract Type:** Standard Monthly Futures (`FUTSTK`).
3. **Liquidity Threshold:** Minimum rolling 20-day median turnover $\ge ₹500\text{ Lakhs}$ (₹5 Crores).
4. **Active Expiry Filter:** Nearest near-month active contract.
5. **Rollover Purge Window:** Contracts with Days to Expiry $\text{DTE} \le 3$ calendar days are strictly **ineligible** to prevent rollover volatility contamination.
6. **No Subjective Stock Blacklisting:** The universe is strictly systematic and rules-based. Manual exclusion of individual historical losers (such as IGL, GODREJCP, CANBK) is prohibited to prevent selection and look-ahead bias.

---

## 3. REQUIRED DATA FIELDS

At signal time $T$ (15:30 IST), the engine requires official Bhavcopy fields:
* `trade_date`: YYYY-MM-DD (Official exchange session)
* `symbol`: Underlying NSE equity symbol
* `open`: Opening traded price
* `high`: Highest traded price
* `low`: Lowest traded price
* `close`: Official exchange closing price (30m VWAP)
* `traded_contracts`: Traded volume in contracts
* `turnover_lakh`: Traded turnover in Lakhs INR
* `open_interest`: End-of-day outstanding open contracts (aggregated across expiries)
* `days_to_expiry`: Calendar days to contract settlement

---

## 4. FORMAL SIGNAL SPECIFICATION

A valid buy signal is triggered at Day $T$ market close (15:30 IST) if and only if **all** of the following conditions are simultaneously met:

### 4.1 Price Capitulation Gate
The underlying futures contract must experience a significant daily decline:
$$\text{Return}_{1\text{D}}(T) = \frac{\text{Close}(T) - \text{Close}(T-1)}{\text{Close}(T-1)} \le -1.50\%$$

### 4.2 Open Interest Contraction Gate
Total market-wide open interest must contract significantly, indicating aggressive long liquidation:
$$\Delta\text{OI}_{\%}(T) = \frac{\text{OI}_{\text{total}}(T) - \text{OI}_{\text{total}}(T-1)}{\text{OI}_{\text{total}}(T-1)} \le -2.00\%$$

### 4.3 Bearish Candle Structure & Body Ratio Gate
The daily price bar must represent a decisive bearish session where sellers dominated from open to close:
$$\text{Close}(T) < \text{Open}(T)$$

The candle body ratio is defined as:
$$\text{Range}(T) = \max\left(\text{High}(T) - \text{Low}(T), 10^{-6}\right)$$
$$\text{Body}(T) = |\text{Close}(T) - \text{Open}(T)|$$
$$\text{Body Ratio}(T) = \frac{\text{Body}(T)}{\text{Range}(T)}$$

**Threshold Resolution:**
* **Standard Operational Specification (Tier A):** $\text{Body Ratio}(T) \ge 0.40$ (Body comprises at least 40% of the entire high-low range).
* **High-Conviction Overlay (Tier B):** $\text{Body Ratio}(T) > 0.60$ (Body comprises over 60% of range).
* *Governance Decision:* Tier A ($\ge 0.40$) is the primary standard contract threshold because it captures optimal diversification (2,313 executed trades, ₹80.8L PnL, Sharpe 1.76). Tier B is reserved as an optional risk-off setting.

### 4.4 Expiry & Sanity Filters
* $\text{DTE}(T) > 3$ calendar days.
* $\text{Turnover}_{\text{total}}(T) \ge ₹500\text{ Lakhs}$ (₹5 Crores).
* $\left|\frac{\text{Open}(T+1) - \text{Close}(T)}{\text{Close}(T)}\right| < 30\%$ (Scrub synthetic contract rollover jumps).

---

## 5. EXECUTION CONTRACT, TIMESTAMPS & LIMIT COLLAR

### 5.1 Timestamp Lifecycle
* **Signal Identification:** Day $T$ at 15:30 IST (after official NSE Bhavcopy publication).
* **Pre-Market Verification:** Day $T+1$ at 09:00–09:08 IST (order intent staged in memory).
* **Order Placement:** Day $T+1$ at 09:15:00 IST (market open).
* **Order Timeout:** Day $T+1$ at 09:17:00 IST (hard cancellation of unfilled limit orders).
* **Exit Execution:** Day $T+2$ at 09:15:00 IST (market open auction fill, exactly 1-day overnight holding horizon).

### 5.2 Reference Price Definition
The reference price for order pricing is the **official Day $T$ exchange closing price**:
$$P_{\text{ref}} = \text{Close}(T)$$

### 5.3 Limit Order Collar (+30 bps)
To prevent adverse execution slippage beyond the strategy's 21.5 bps baseline breakeven point, all entry orders must be placed as **LIMIT** orders capped at +30 basis points above the reference price:
$$P_{\text{limit}} = \text{round}\left(P_{\text{ref}} \times 1.0030, 2\right)$$

* If Day $T+1$ opening auction price $P_{\text{open}}(T+1) \le P_{\text{limit}}$: Order fills at the opening price plus normal bid-ask spread slippage.
* If Day $T+1$ opening auction price $P_{\text{open}}(T+1) > P_{\text{limit}}$: Order does not fill at open. It remains on the book until 09:17:00 IST. If the price does not trade at or below $P_{\text{limit}}$ within 2 minutes, the order is **hard-cancelled** (`MISSED_COLLAR`). **No fill means no trade.**

### 5.4 Opening Gap Protection (+1.50%)
If the opening indicative price or traded price gaps up by more than +1.50% above the reference price:
$$\text{Gap}_{\%} = \frac{P_{\text{open}}(T+1) - P_{\text{ref}}}{P_{\text{ref}}} \times 100.0 > +1.50\%$$
The order intent is **suppressed entirely** (`MISSED_GAP`). The strategy strictly prohibits chasing opening gaps.

### 5.5 Exit Execution Rule
* Positions exit exclusively at **Day $T+2$ 09:15:00 IST Market Open Auction**.
* **Strict Ban on Trailing Stops:** Trailing stops calculated from intraday high-water marks are strictly prohibited. Empirical validation proved they trigger premature whipsaw liquidations during morning opening noise, destroying strategy performance.

---

## 6. TRANSACTION COST & FRICTION MODEL

* **Baseline Institutional Friction:** **8.0 basis points (0.080%)** round-trip deducted from allocated capital:
  - STT: 1.00 bps (0.02% on sell leg)
  - Stamp Duty: 0.20 bps (0.002% on buy leg)
  - Exchange Charges: 0.38 bps (0.0019% per leg)
  - SEBI Fee: 0.02 bps
  - GST: 0.30 bps (18% on fees)
  - Institutional Brokerage: 1.00 bps (flat ₹20/order)
  - Execution Half-Spread Slippage: 5.10 bps (2.55 bps per leg)
* **Breakeven Friction Ceiling:** **42.96 basis points** round-trip. The strategy maintains a robust +34.96 bps safety buffer under V2 execution rules.

---

## 7. PORTFOLIO ALLOCATION & RISK CONSTRAINTS

* **Maximum Simultaneous Positions:** 10 slots (Equal-weight portfolio).
* **Position Sizing:** Fixed slot allocation:
  $$\text{Slot Capital} = \frac{\text{Initial Capital}}{\text{Max Positions}} = \frac{₹1,00,00,000}{10} = ₹10,00,000 \text{ per slot (10\%)}$$
  $$\text{Quantity} = \max\left(1, \left\lfloor \frac{\text{Slot Capital}}{P_{\text{open}}} \right\rfloor \right)$$
* **Maximum Single-Stock Exposure:** $10\%$ at entry.
* **Maximum Sector Exposure:** $20\%$ of portfolio (maximum 2 simultaneous positions per sector).
* **Cash Yield:** Idle cash yields standard risk-free rate (6.5% p.a.).
* **Collision Ranking Heuristic:** When $> 10$ candidates qualify on Day $T$, rank candidate symbols by **most negative open interest contraction intensity** ($\Delta\text{OI}_{\%}$ ascending), selecting the Top 10 subject to sector limits.

---

## 8. FAIL-CLOSED SAFETY PROTOCOL

An order intent MUST BE REJECTED and order suppressed if:
1. `open_interest` is 0, missing, or unchanged for $> 2$ consecutive sessions.
2. `turnover_lakh` is $< 500.0$ (₹5 Crores).
3. Timestamp discontinuity, holiday mismatch, or stale date detected.
4. Contract $\text{DTE} \le 3$.
5. Opening price violates the +30 bps Limit Collar or +1.50% Gap Ceiling.
6. Portfolio circuit breaker is active (daily drawdown $\ge 3.0\%$ or peak-to-trough drawdown $\ge 8.0\%$).

---

## 9. KNOWN LIMITATIONS & RESEARCH RISKS

1. **Intraday Tick Resolution:** Bhavcopy archives lack intraday tick depth. The +30 bps collar non-fill rate is modeled conservatively at the open bar; actual queue priority in live order books may vary.
2. **Opening Liquidity Imbalances:** On days with extreme index gap openings, single-stock futures spreads can widen to 10–20 bps during the first 60 seconds (09:15:00–09:16:00 IST). Limit orders protect against adverse fills, but increase the non-fill rate.
3. **Clustered Drawdown Tail Risk:** During market-wide crash sessions, multiple stock positions will experience correlated adverse moves. The strategy must be sized conservatively.

---

## 10. DRAFT CRYPTOGRAPHIC SPECIFICATION HASH

```
CONTRACT_VERSION : SIG-OI-001-PAPER-V2-DRAFT
DRAFT_HASH_SHA256: 7f3b89c445698b6710b100914c6ca9ce51307b22a0ce124cbf8a6b6f7c768912
GOVERNANCE_STATE : DRAFT — PENDING 60-SESSION SHADOW PAPER VALIDATION
```
*(This hash uniquely identifies this draft specification. Final freezing will occur only upon completion of the shadow observation period and explicit governance sign-off.)*
