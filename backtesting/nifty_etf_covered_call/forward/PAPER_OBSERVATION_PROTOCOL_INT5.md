# AGY FORWARD PAPER-OBSERVATION PROTOCOL
## Candidate: EXP-064-INT5 Covered Call Strategy

**Protocol ID:** AGY-FWD-CC-001  
**Candidate Name:** Systematic NIFTY Covered Call Overlay (Candidate `EXP-064-INT5`)  
**Target Architecture:** Underlying Cash Equity (`NIFTYBEES` ETF) + Short Monthly Index Call (`NIFTY CE`)  
**Governance Scope:** `~/backtesting/covered call/forward/`  
**Operational Status:** DRAFT PROTOCOL — PENDING USER APPROVAL BEFORE COMMENCEMENT  
**Date:** October 13, 2026  

---

## 1. Objective & Purpose

This protocol defines the formal operational rules, data collection interfaces, fill simulation mechanics, and risk controls for forward paper observation of candidate **EXP-064-INT5**.

The objective of forward paper observation is to observe, record, and evaluate the strategy's real-time signals, execution frictions, and mark-to-market performance on contemporaneous live market feeds **without risking capital or placing live broker orders**.

---

## 2. Core Candidate Parameters

| Parameter Dimension | Parameter Specification | Operational Implementation |
| :--- | :--- | :--- |
| **Underlying Asset** | Nippon India ETF Nifty BeES (`NIFTYBEES`) / NIFTY 50 Spot | Tracked on NSE Cash Market (`CM`) segment |
| **Option Overlay Leg** | Monthly European Call Option on NIFTY 50 (`OPTIDX NIFTY CE`) | Traded on NSE Futures & Options (`F&O`) segment |
| **Trend Filter** | 100-Day Exponential Moving Average (`100 EMA`) on Spot | Overlay initiated strictly when $\text{Spot} > \text{EMA}_{100}$ |
| **Target Short Delta** | **$\Delta = 0.25$** (~3.0% to 4.0% OTM) | Computed via vectorized Black-Scholes formula |
| **Initial Target Tenor** | ~28 Calendar Days to Expiry (Tolerance: 18 to 38 DTE) | Select nearest monthly contract matching DTE target |
| **Premium Decay Target** | **80% Premium Capture** | Exit when Option Market Price $\le 0.20 \times \text{Entry Fill}$ |
| **Stop Loss Multiple** | **3.0x Entry Premium** | Exit when Option Market Price $\ge 3.00 \times \text{Entry Fill}$ |
| **Roll Timing Threshold** | **$\le 7$ Remaining Exchange Trading Sessions** | Holiday-aware trading day counter to expiry |
| **Reference Capital** | ₹15,00,000.00 Total Allocated Portfolio Equity | Institutional reference denominator |

---

## 3. Signal Timestamps & Daily Operational Cadence

All timestamps operate on Indian Standard Time (IST, UTC+05:30):

```text
========================================================================================
                          DAILY FORWARD OPERATIONAL CADENCE
========================================================================================
 Time (IST)        Stage                  Operational Action
----------------------------------------------------------------------------------------
 09:00 – 09:15     Pre-Market Audit       Verify trading session status against NSE holiday
                                          calendar. Check days to current option expiry.
 09:15 – 15:10     Passive Monitoring     Monitor active short call market price vs stop-loss
                                          threshold (3.0x entry fill) and profit target (80%).
 15:10 – 15:15     Feature Snapshot       Compute underlying 100-day EMA, contemporaneous
                                          ATM IV, and remaining exchange trading sessions.
 15:15 – 15:20     Signal Generation      Evaluate Entry / Exit / Roll rules based on top-of-
                                          book quotes. Log decision ticket if signal triggers.
 15:20 – 15:25     Simulated Fill Logging Log hypothetical fill price including slippage and
                                          statutory taxes based on contemporaneous Bid/Ask.
 15:35 – 16:00     Daily MTM Ledger       Record official NSE settlement prices, daily NAV,
                                          unrealized MTM, and cash buffer interest accrual.
========================================================================================
```

---

## 4. Contract Selection & Execution Mechanics

### 4.1 Delta 0.25 Strike Selection Algorithm
At the signal timestamp (15:15 IST), if no active short call exists and $\text{Spot} > \text{EMA}_{100}$:
1. **Target Expiry Search:** Filter all active monthly `NIFTY CE` contracts expiring in 18 to 38 calendar days. Select the contract whose calendar DTE is closest to 28 days.
2. **Black-Scholes Delta Calculation:**
   $$\Delta_{call} = N(d_1) = N\left( \frac{\ln(S / K) + (r + \frac{1}{2}\sigma^2)T}{\sigma \sqrt{T}} \right)$$
   Where:
   - $S$ = Contemporaneous NIFTY 50 Spot price at 15:15 IST.
   - $K$ = Option strike price.
   - $T = \text{DTE} / 365.25$ (Annualized time to expiry).
   - $r = 0.065$ (6.5% Indian benchmark risk-free rate).
   - $\sigma$ = Contemporaneous ATM implied volatility derived from current settlement/market price.
3. **Selection Rule:** Select strike $K^*$ where $|\Delta(K^*) - 0.25|$ is minimized.
4. **Liquidity Sanity Filters:**
   - Contract Open Interest (OI) must be $\ge 10,000$ contracts.
   - Bid-Ask Spread must be $\le 1.5\%$ of premium or $\le 1.50$ index points.
   - Premium must be $\ge ₹25.00$ per share (reject penny strikes).

### 4.2 Exit & Roll Evaluation Rules
For an active short call position, evaluate rules in the following priority order:
1. **Stop Loss (Priority 1):** If Current Market Price $\ge 3.0 \times \text{Entry Fill Price}$, trigger immediate buyback order (`STOP_LOSS`).
2. **Profit Target (Priority 2):** If Current Market Price $\le 0.20 \times \text{Entry Fill Price}$, trigger buyback order (`PROFIT_TARGET`).
3. **Roll Threshold (Priority 3):** Count remaining exchange trading sessions strictly between current date and expiry date ($\text{ts\_remaining}$). If $\text{ts\_remaining} \le 7$, trigger buyback order (`EXPIRY_ROLL`).
4. **Trend Breakdown (Priority 4):** If NIFTY Spot closes below 100 EMA by $> 1.5\%$, flag position for defensive evaluation.

---

## 5. Contemporaneous Fill Simulation & Slippage Modeling

All paper trades must record contemporaneous market state to eliminate fill hallucination:

### 5.1 Simulated Execution Pricing
* **Sell Orders (Opening Short Call):** Fill Price = $\text{Best Bid} - \text{Slippage Penalty}$
* **Buy Orders (Closing Short Call):** Fill Price = $\text{Best Ask} + \text{Slippage Penalty}$
* **Slippage Schedule:**
  $$\text{Slippage Points} = \max\left( \text{Market Price} \times 0.010,\ 0.50 \text{ index points} \right)$$
  *(Escalate to 2.0% slippage if trade execution occurs during heightened market volatility).*

### 5.2 Regulatory Taxes & Exchange Frictions (NSE Rates)
Every trade ticket must calculate and record exact statutory deductions:
1. **Brokerage:** Flat ₹20.00 per order leg (₹40.00 roundtrip).
2. **Securities Transaction Tax (STT):** 0.10% on sell premium turnover (revised rate effective Oct 1, 2024). STT on buy legs = ₹0.00.
3. **Exchange Transaction Charge:** 0.03503% of premium turnover.
4. **SEBI Turnover Charges:** ₹10.00 per crore turnover (0.0000010).
5. **Stamp Duty:** 0.003% on buy premium turnover.
6. **GST (Goods & Services Tax):** 18% on (Brokerage + Exchange Fees + SEBI Charges).

### 5.3 Exception Logging (Missed Fills & Illiquidity)
* **`REJECTED_ILLIQUID`:** If the selected 0.25 delta strike has bid-ask spread $> 2.0\%$ of premium, step to the nearest liquid strike (50 points wider). If no liquid strike exists within $\pm 100$ points, log ticket as `REJECTED_ILLIQUID` and do not trade.
* **`MISSED_FILL`:** If the market price moves by $> 3.0\%$ between signal timestamp (15:15) and simulated execution timestamp (15:20), log as `MISSED_FILL` and record tracking slippage.

---

## 6. Capital Utilization, Margining & Non-Delivery Controls

### 6.1 Critical Non-Delivery Invariant: Settlement Mismatch
> [!CAUTION]
> **DO NOT ASSUME NIFTYBEES CAN PHYSICALLY SETTLE OR HEDGE THE SHORT CALL.**  
> Under SEBI regulations, NIFTY 50 index options are **strictly cash-settled**. ETF units in Demat **cannot be delivered** to satisfy an in-the-money (ITM) short call assignment. When a short call expires ITM, the clearing corporation (**NCL**) directly debits cash from the trading account. The ETF units remain completely untouched in Demat.

### 6.2 Mandatory Liquid Cash Buffer
* In our ₹15,00,000 reference portfolio, purchasing 1 lot equivalent of underlying equity consumes ~₹10.5L to ₹12.5L.
* The remaining **₹2.5L to ₹4.5L MUST be retained strictly in unencumbered liquid cash or overnight liquid mutual funds** (e.g. Liquid BeES).
* **Cash Deficit Rule:** If unencumbered liquid cash drops below **₹1,50,000**, writing new short calls is **strictly prohibited** until cash is restored.

### 6.3 Dynamic Position Sizing Rules
* **Lot Size Awareness:** Regulatory lot sizes vary (e.g., 50 pre-April 2024, 25 in mid-2024, 75 in 2025, 65 in 2026).
* **Notional Sizing Cap:** Total underlying notional exposure ($S_t \times L_t$) must not exceed **80% of total portfolio NAV**.
* If notional derivative exposure exceeds 80% of NAV, the paper portfolio must simulate **fractional cash ETF units** scaled to 75% of capital rather than an inflexible 1-lot derivative notional.

---

## 7. Mandatory Risk Disclosures & Limitations

In compliance with quantitative research standards, the following unresolved limitations are formally logged:

1. **Retrospective Holdout Inspection (Check 1):** The 2025–2026 holdout was not quarantined in an untouched blind vault; it was inspected during full-horizon candidate ranking. Forward paper observation is mandatory to confirm true out-of-sample edge.
2. **Absence of Non-Linear Crash Modeling (Check 2):** Historical stress tests applied a static linear net-delta approximation ($\Delta_{net} \approx 0.75$) to stop-loss trades. **Full crash resilience under non-linear gamma expansion, vega spikes (IV surge), and volatility skew is UNPROVEN.**
3. **No Claim of Statistical Superiority (Check 4):** The candidate's higher point Sharpe ratio (0.22 vs 0.13) is **not statistically significant** ($p = 0.6537$ on paired daily return differences, with heavily overlapping 90% bootstrap confidence intervals). The candidate is promoted for observation based on net rupee alpha and drawdown reduction, not statistical Sharpe superiority.

---

## 8. Daily Mark-to-Market (MTM) Recording Template

Every forward observation day must record the following schema in `forward_daily_nav.csv`:

```text
========================================================================================================
                               DAILY MTM LOGGING RECORD SCHEMA
========================================================================================================
 Field Name                  Description & Computation
--------------------------------------------------------------------------------------------------------
 `date`                      Trading session date (YYYY-MM-DD)
 `nifty_spot_close`          Official NSE NIFTY 50 Spot closing price
 `ema_100`                   100-day Exponential Moving Average of spot close
 `active_trade_id`           Identifier of active position (e.g. `FWD_T001`), or `NONE`
 `short_contract`            Option symbol (e.g. `NIFTY26NOV26000CE`)
 `days_to_expiry`            Calendar days to option contract expiry
 `trading_sessions_left`     Exchange trading sessions remaining to expiry
 `short_entry_price`         Fill price at opening execution (net of slippage)
 `curr_settle_price`         Official NSE settlement price of the active short call
 `unrealized_spot_pnl`       (Current Spot - Entry Spot) * Lot Size
 `unrealized_opt_pnl`        (Entry Fill Price - Current Settle Price) * Lot Size
 `cumulative_realized_pnl`   Cumulative rupee profit/loss from all closed paper trades
 `idle_cash_balance`         Unencumbered liquid cash in portfolio
 `liquid_interest_earned`    Daily accrued interest on idle cash (4.8% p.a. / 252)
 `total_portfolio_nav`       Starting Capital + Realized PnL + Unrealized PnL + Accrued Interest
 `peak_nav`                  Historical peak of total portfolio NAV
 `current_drawdown_pct`      (Current NAV - Peak NAV) / Peak NAV
========================================================================================================
```
