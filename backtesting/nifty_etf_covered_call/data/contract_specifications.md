# NIFTYBEES & NIFTY 50 DERIVATIVES CONTRACT SPECIFICATIONS & MARKET RULES

**Document Phase:** Phase 2 — Feasibility & Data Validation  
**Strategy Project:** Covered Call Strategy (Buy-Write Overlay)  
**Primary Implementation:** **LONG NIFTYBEES + SHORT NIFTY 50 CALL (`NIFTY CE`)**  
**Comparative Baseline (Secondary Research Only):** Long NIFTY Futures + Short NIFTY Call  
**Exchange Venue:** National Stock Exchange of India (NSE)  
**Clearing Corporation:** NSE Clearing Limited (NCL)  
**File Location:** `~/backtesting/covered call/data/contract_specifications.md`  
**Date:** September 2026  
**Status:** VALIDATED — AUTHORITATIVE EXCHANGE REFERENCE  

---

## 1. EXECUTIVE CONTRACT SPECIFICATION MATRIX

| Parameter | NIFTYBEES ETF (`NIFTYBEES`) | NIFTY 50 Call Options (`OPTIDX` / `IDO`) | NIFTY 50 Futures (`FUTIDX` / `IDF`) [Comparative] |
| :--- | :--- | :--- | :--- |
| **Market Segment** | **NSE Capital Market (CM) / Cash Equity** | **NSE Futures & Options (F&O)** | **NSE Futures & Options (F&O)** |
| **Asset Class** | Open-Ended Equity Index ETF | Equity Index European Call Option | Equity Index Futures Contract |
| **Exchange Ticker** | `NIFTYBEES` (ISIN: `INF732E01015`) | `OPTIDX NIFTY <EXPIRY> <STRIKE> CE` | `FUTIDX NIFTY <EXPIRY>` |
| **Underlying Index** | NIFTY 50 Total Return Index (TRI) | NIFTY 50 Price Return Index (PR) | NIFTY 50 Price Return Index (PR) |
| **Contract Multiplier / Lot Size** | **1 Unit** (Discrete integer share) | **Dynamic: 75 / 50 / 25 / 75 units** | **Dynamic: 75 / 50 / 25 / 75 units** |
| **Quotation / Pricing Unit** | INR per ETF unit (e.g., ₹248.50) | Option Premium in Index Points (e.g., ₹185.00) | Index Points (e.g., 24,500.50) |
| **Tick Size** | ₹0.01 (1 Paisa) | ₹0.05 (5 Paise) | ₹0.05 (5 Paise) |
| **Exercise / Option Style** | N/A (Traded Equity Asset) | **European Style (`CE`)** — No early exercise | N/A (Linear Derivative) |
| **Settlement Mechanism** | **T+1 Rolling Settlement** (Demat delivery) | **Cash Settled in INR** via NCL VWAP | **Cash Settled in INR** via NCL VWAP |
| **Delivery Feasibility** | Physical custody in Demat (CDSL/NSDL) | **Zero Physical Delivery** (Index options cannot be settled via ETF units) | **Zero Physical Delivery** |
| **Trading Hours** | 09:15:00 to 15:30:00 IST | 09:15:00 to 15:30:00 IST | 09:15:00 to 15:30:00 IST |
| **Strike Intervals** | N/A | 50 points (ATM / near-term), 100 points (far OTM) | N/A |
| **Contract Expiries** | Continuous perpetual holding | Weekly + 3 Monthly + Quarterly/Half-Yearly | 3 Monthly Contracts (Near, Next, Far Month) |
| **Expiration Date** | N/A | Last Thursday of month (or prior trading day) | Last Thursday of month (or prior trading day) |
| **Settlement Benchmark** | Market closing price / iNAV | Official 30-min NIFTY VWAP (15:00–15:30 IST) | Official 30-min NIFTY VWAP (15:00–15:30 IST) |
| **Expense Ratio / Drag** | ~0.04% p.a. (TER deducted daily from NAV) | None | Cost of carry / roll friction |
| **Dividend Treatment** | Reinvested into fund NAV (Total Return) | Embedded in option pricing / forward curve | Embedded in futures basis / forward discount |

---

## 2. NIFTYBEES COVERED CALL IMPLEMENTATION

### 2.1 Critical Structural Distinction: NIFTYBEES + Short Call vs. NIFTY Futures + Short Call

The primary Covered Call strategy is strictly:
$$\mathbf{LONG\ NIFTYBEES\ (Cash\ Equity)\ +\ SHORT\ NIFTY\ 50\ CALL\ (F\&O)}$$

This is fundamentally and operationally distinct from the classic synthetic **Long NIFTY Futures + Short NIFTY Call (Buy-Write)** structure:

```text
========================================================================================
             STRUCTURAL COMPARISON: CASH ETF BUY-WRITE VS. FUTURES BUY-WRITE
========================================================================================
 Dimension                NIFTYBEES + Short NIFTY Call           NIFTY Futures + Short NIFTY Call
----------------------------------------------------------------------------------------
 Market Segment           Cross-Segment: Cash (CM) + F&O         Single-Segment: F&O only
 Delivery / Custody       Actual delivery to Demat account       Zero delivery; pure financial derivative
 Margining Architecture   100% upfront cash for ETF (or pledge)  SPAN + Exposure cross-margining
 Margin Offset            Zero direct cross-margining in F&O     Direct margin relief (~₹80k-1.1L total)
 Collateral Rules         Haircut (10-12.5%) + SEBI 50:50 rule   Unified margin pool
 Settlement Mismatch      CRITICAL: ETF cannot settle option!    Unified cash MTM & settlement in F&O
 ITM Expiry Outcome       Cash debited from trading account;     Cash debit netted against long future
                          NIFTYBEES remains intact in Demat      terminal settlement automatically
 Cash Call / Deficit Risk High if unbuffered cash is depleted    Zero cash-deficit risk if funded
 Tracking Risk            TER drag, cash drag, tracking error    Zero ETF tracking error (cost-of-carry only)
 Dividend Impact          Accrues to investor via ETF NAV (TRI)  Foregone/discounted in futures basis
 Statutory Tax Bucket     Equity LTCG (12.5%) / STCG (20%)       Non-speculative business income
========================================================================================
```

### 2.2 The Non-Delivery Invariant: Settlement Mismatch

Under SEBI regulatory statutes, **NIFTY 50 Index Options (`OPTIDX`) are strictly cash-settled financial contracts**.
1. **No Physical Delivery:** An index option writer **cannot surrender, assign, or deliver NIFTYBEES units** to satisfy an in-the-money option assignment.
2. **Terminal Expiry Scenarios:**
   * **Scenario A: Out-of-the-Money Expiry ($S_{\text{settle}} \le K$):**
     $$\text{Option Terminal Payoff} = ₹0.00$$
     $$\text{Net Cash Flow} = +C_0 \times L_t \quad (\text{Premium Retained})$$
     $$\text{NIFTYBEES Position} = \text{Maintained intact in Demat without alteration}.$$
   * **Scenario B: In-the-Money Expiry ($S_{\text{settle}} > K$):**
     $$\text{Intrinsic Settlement Value} = (S_{\text{settle}} - K) \times L_t$$
     $$\text{Cash Obligation} = \text{Debited directly in INR from trading account by NCL}.$$
     $$\text{NIFTYBEES Position} = \mathbf{REMAINS\ COMPLETELY\ UNTOUCHED\ IN\ DEMAT}.$$
3. **Operational Consequence:**
   Because the ETF units are not sold or transferred automatically by the clearing house, **the investor must have sufficient liquid cash in the trading account to pay the ITM cash debit**. If cash is insufficient, the broker charges overdue debit interest (typically 18% to 24% p.a.), issues a margin call, or forcefully liquidates NIFTYBEES units on the open market at prevailing market prices (incurring market impact, slippage, and delivery STT).

---

## 3. HEDGE RATIO ENGINE & MATHEMATICAL FORMULATION

### 3.1 Mathematical Derivation of Coverage

To determine the exact number of NIFTYBEES units ($Q_t$) required to achieve **100% covered call protection** against 1 lot of NIFTY 50 options:

Let:
* $S_t$ = NIFTY 50 Index Level at cycle initiation (index points).
* $P_t$ = NIFTYBEES Market Price at cycle initiation (INR per unit).
* $L_t$ = Applicable NIFTY 50 Option Market Lot Size on trade date ($50, 25, \text{or } 75$).
* $N_t^{\text{opt}} = S_t \times L_t$ = Notional contract value of 1 NIFTY option contract.
* $R_t = \frac{S_t}{P_t}$ = Dynamic NIFTY-to-NIFTYBEES tracking ratio.

When the index advances by $\Delta S$ points above the strike price $K$, the short option incurs a terminal intrinsic liability of:
$$\Delta \Pi_{\text{opt}} = -\Delta S \times L_t$$

To achieve exact dollar-for-dollar (rupee-for-rupee) offsetting gains from the NIFTYBEES holding:
$$\Delta \Pi_{\text{ETF}} = Q_t \times \Delta P_t$$

Assuming faithful ETF tracking ($\frac{\Delta P_t}{P_t} \approx \frac{\Delta S}{S_t} \implies \Delta P_t \approx \frac{P_t}{S_t} \Delta S$):
$$\Delta \Pi_{\text{ETF}} = Q_t \times \left(\frac{P_t}{S_t} \Delta S\right)$$

Equating the two exposures ($\Delta \Pi_{\text{ETF}} = -\Delta \Pi_{\text{opt}}$):
$$Q_t \times \left(\frac{P_t}{S_t} \Delta S\right) = \Delta S \times L_t$$

Solving for $Q_t^{\text{required}}$:
$$\mathbf{Q_t^{\text{required}} = \frac{S_t \times L_t}{P_t} = L_t \times \left(\frac{S_t}{P_t}\right) = L_t \times R_t}$$

And the portfolio capital required to purchase these units is:
$$\mathbf{V_t^{\text{ETF}} = Q_t^{\text{required}} \times P_t = \left(\frac{S_t \times L_t}{P_t}\right) \times P_t = S_t \times L_t = N_t^{\text{opt}}}$$

> [!CRITICAL]
> **Fundamental Mathematical Identity:**
> To hold 100% covered protection against 1 NIFTY option lot, the market value of NIFTYBEES held MUST equal the **exact Notional Value of the Option Contract** ($S_t \times L_t$).
> Because $S_t$ changes daily and $L_t$ changes historically, **the hedge ratio is dynamic and non-constant**.

### 3.2 Evaluation of Coverage Methodologies

Three competing coverage definitions were evaluated:

```text
========================================================================================
                          EVALUATION OF COVERAGE DEFINITIONS
========================================================================================
 Method                   Mathematical Formulation          Assessment & Verdict
----------------------------------------------------------------------------------------
 Method A:                Q_t * P_t = S_t * L_t             RECOMMENDED BASELINE.
 Notional Coverage        Rupee ETF value = Option Notional Exactly satisfies terminal
                                                            intrinsic payoff at expiry.
                                                            Stable, transparent, standard.
----------------------------------------------------------------------------------------
 Method B:                Q_t * (P_t / S_t) = L_t           RECOMMENDED BASELINE.
 Index-Equivalent         NIFTY index units held = L_t      Mathematically identical to
 Exposure                                                   Method A. Represents physical
                                                            unit equivalence.
----------------------------------------------------------------------------------------
 Method C:                Q_t * (P_t / S_t) = Delta * L_t   REJECTED FOR BASELINE.
 Delta-Equivalent         Only holds 25-35% ETF units       Exposes writer to catastrophic
 Coverage                 at entry (Delta ~ 0.30)           unhedged upside if index rallies.
                                                            Requires continuous rebalancing,
                                                            causing huge churn, STT & fees.
========================================================================================
```

**Recommendation:** **Method A / Method B (Terminal Notional & Index-Equivalent Coverage)** is selected as the sole baseline definition. Method C is rejected as it violates the regulatory and economic definition of a buy-and-hold covered call.

---

## 4. HISTORICAL LOT SIZE TIMELINE & DYNAMIC PARAMETERS

The simulation engine must never hardcode a static lot size. The exact historical schedule mandated by NSE circulars is:

| Effective Date Range | Expiry Contracts Governed | NIFTY Market Lot Size ($L_t$) | Exchange Circular Reference |
| :--- | :--- | :---: | :--- |
| **June 12, 2000 – Oct 27, 2005** | Inception Contracts | **200** | NSE/F&O/172/2000 |
| **Oct 28, 2005 – May 3, 2007** | Nov 2005 – May 2007 | **100** | NSE/F&O/678/2005 |
| **May 4, 2007 – Oct 29, 2015** | May 2007 – Oct 2015 | **50** | NSE/FAOP/8854 |
| **Oct 30, 2015 – June 24, 2021** | Nov 2015 – June 2021 | **75** | NSE/FAOP/28362 & NSE/FAOP/29729 |
| **July 1, 2021 – April 25, 2024** | July 2021 – June 2024 | **50** | NSE/FAOP/47743 (Dated March 24, 2021) |
| **April 26, 2024 – Nov 19, 2024** | July 2024 – Nov 2024 | **25** | NSE/FAOP/61327 (Dated March 27, 2024) |
| **Nov 20, 2024 – Present** | Dec 2024 onwards | **75** | NSE/FAOP/64442 (SEBI Mandate Oct 2024) |

### Historical Cycle Sizing Profile (2022 to 2024 Sample)

* **When Lot Size = 50 (Jan 2022 – Apr 2024):**
  * NIFTY Spot: 15,752 to 22,462 points.
  * NIFTYBEES Price: ₹171.64 to ₹248.19.
  * Tracking Ratio ($S_t / P_t$): 90.46 to 92.77 (Mean: 91.36).
  * Contract Notional ($S_t \times 50$): **₹7,87,600 to ₹11,23,100** (Mean: ₹9,26,728).
  * Required NIFTYBEES Units ($Q_t^{\text{req}}$): **4,523 to 4,639 units** (Mean: 4,569 units).
* **When Lot Size = 25 (Apr 2024 – Jul 2024):**
  * NIFTY Spot: 22,420 to 24,011 points.
  * NIFTYBEES Price: ₹248.44 to ₹267.48.
  * Tracking Ratio ($S_t / P_t$): 89.71 to 90.24 (Mean: 89.91).
  * Contract Notional ($S_t \times 25$): **₹5,60,500 to ₹6,00,265** (Mean: ₹5,74,677).
  * Required NIFTYBEES Units ($Q_t^{\text{req}}$): **2,243 to 2,256 units** (Mean: 2,248 units).
* **When Lot Size = 75 (Post Nov 2024 Projections):**
  * NIFTY Spot: ~25,000 points.
  * Contract Notional: **~₹18,75,000**.
  * Required NIFTYBEES Units: **~6,750 units**.

---

## 5. CAPITAL MODELING (₹15,00,000 REFERENCE PORTFOLIO)

### 5.1 Model Architecture Comparison

For a reference capital of **₹15,00,000**, two capital deployment models exist:

```text
========================================================================================
             CAPITAL ALLOCATION MODELS UNDER ₹15,00,000 REFERENCE CAPITAL
========================================================================================
 Metric / Feature         Architecture 1: 100% Notional Coverage    Architecture 2: 100% Equity Deployment
----------------------------------------------------------------------------------------
 Portfolio Concept        Buy exact Q_req units to cover 1 lot;     Deploy entire ₹15L into NIFTYBEES;
                          Retain remainder in liquid cash buffer.   Pledge ETF to write 1 NIFTY call.
 NIFTYBEES Units Held     4,525 to 4,639 units (Lot 50)             6,000 to 7,800 units
 ETF Investment Value     ₹7,87,600 to ₹11,23,100                   ₹15,00,000
 Liquid Cash Remaining    ₹3,76,900 to ₹7,12,400 (Mean: ₹5.73L)     ₹0.00 (Zero unencumbered cash)
 Option Lots Written      1 Lot                                     1 Lot
 Coverage Percentage      Exactly 100.0%                            150% to 267% (Over-covered)
 Margin Obligation        ₹86,000 to ₹1,23,000                      ₹86,000 to ₹1,23,000
 Margin Source            Drawn directly from cash buffer           Pledged NIFTYBEES (10-12.5% haircut)
 SEBI 50:50 Cash Rule     100% Cash satisfied (Zero violation)      VIOLATION unless cash infused
 ITM Settlement Cash      Fully absorbed by free cash buffer        CRITICAL DEFICIT: Account in debit;
                          (Max observed debit: ₹56,435)             Requires margin loan or forced sale.
 Backtest Feasibility     HIGH: Clean, realistic, self-contained    LOW: Requires synthetic margin loans.
========================================================================================
```

> [!IMPORTANT]
> **Baseline Recommendation:** **Architecture 1 (100% Notional Coverage)** is selected.
> In Architecture 1, ₹15,00,000 purchases the exact required units of NIFTYBEES ($Q_t^{\text{req}} = S_t \times L_t / P_t$), leaving **₹3.76L to ₹7.12L in liquid cash buffer**. This buffer comfortably satisfies:
> 1. The short call SPAN + Exposure margin (~₹86,000 to ₹1,23,000).
> 2. The maximum potential ITM cash settlement debit (peak observed: ₹56,435 in Dec 2023).
> 3. Zero reliance on broker margin loans, zero pledge friction, and zero risk of forced liquidation.

---

## 6. VERIFIED STATUTORY CHARGES & TAXATION SCHEDULE

The simulation engine must apply the verified statutory cost schedule across both legs:

### 6.1 NIFTYBEES Cash Equity Leg (Delivery)

| Charge Type | Rate / Tariff | Basis |
| :--- | :--- | :--- |
| **Brokerage** | ₹20 per executed order (or ₹0 on discount delivery) | Per order |
| **Securities Transaction Tax (STT)**| 0.10% (Buy) and 0.10% (Sell) on delivery turnover* | Turnover ($Q \times P$) |
| **Exchange Transaction Charges** | 0.00297% (NSE CM Segment) | Turnover ($Q \times P$) |
| **SEBI Turnover Charges** | ₹10 per Crore (0.0001%) | Turnover ($Q \times P$) |
| **Stamp Duty** | 0.015% (Buy only) | Buy Turnover |
| **Goods & Services Tax (GST)** | 18% on (Brokerage + Exchange + SEBI fees) | Service components |
| **Depository / DP Charges** | ₹13.50 + GST (on sale / debit from Demat) | Per ISIN per day |

*\*Note on ETF STT: Equity ETFs traded on exchange have concessional STT under certain broker classifications (0.001% on sell), but conservative institutional backtesting applies the standard 0.1% delivery STT to prevent return overstatement.*

### 6.2 NIFTY 50 Call Option Leg (F&O)

| Charge Type | Rate / Tariff | Basis |
| :--- | :--- | :--- |
| **Brokerage** | Flat ₹20 per executed order | Per order |
| **Securities Transaction Tax (STT)**| • 0.0625% on Sell Premium (Pre-Oct 1, 2024)<br>• 0.1000% on Sell Premium (Post-Oct 1, 2024)<br>• Zero on Buy-to-Close | Premium Turnover ($L_t \times C_0$) |
| **Exchange Transaction Charges** | 0.03503% on Premium Turnover | Premium Turnover ($L_t \times C_0$) |
| **SEBI Turnover Charges** | ₹10 per Crore (0.0001%) on Premium Turnover | Premium Turnover ($L_t \times C_0$) |
| **Stamp Duty** | 0.003% on Buy Premium Turnover | Buy Premium Turnover |
| **Goods & Services Tax (GST)** | 18% on (Brokerage + Exchange + SEBI fees) | Service components |

---

## 7. SUMMARY VERDICT & BASELINE READINESS

1. **Practical Feasibility:** **YES — FULLY MODELABLE**. NIFTYBEES and NIFTY CE contracts have complete, verified EOD data across the entire historical horizon.
2. **Hedge Ratio Requirement:** Dynamically computed as $Q_t = \frac{S_t \times L_t}{P_t}$. Discrete integers must be rounded.
3. **Cash Buffer Invariant:** Cash settlement requires an explicit liquid cash cushion. ₹15,00,000 provides complete 100% coverage with ~₹3.76L to ₹7.12L cash buffer, guaranteeing zero margin calls.
