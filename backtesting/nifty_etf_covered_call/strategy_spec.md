# COVERED CALL STRATEGY — SPECIFICATION & RESEARCH FRAMEWORK

**Document Phase:** Phase 1 — Research & Specification  
**Strategy Project:** Covered Call Strategy (Buy-Write Overlay)  
**Mandatory Project Path:** `~/backtesting/covered call/`  
**Specification File:** `~/backtesting/covered call/strategy_spec.md`  
**Date:** September 2026  
**Status:** DRAFT / UNDER REVIEW — NO EXECUTION AUTHORIZED  

---

## 1. RESEARCH VS. EXECUTION GOVERNANCE POLICY

### 1.1 Mandatory Directory Governance
All quantitative research, algorithmic modeling, exploratory scripting, historical backtesting, and validation artifacts for this strategy MUST remain strictly confined to:

```text
~/backtesting/covered call/
```

Under no circumstances may Covered Call research files, specifications, data caches, or scripts be created in or moved to:
* `~/Desktop/`
* `~/strategy/`
* `~/openalgo/`
* `~/openalgo research/`
* Any unrelated project directory

Existing production or ongoing research projects (including `macdfno.py`, MACD research, and Ichimoku research) are completely independent and must not be touched, modified, or referenced.

### 1.2 The Strategy Lifecycle SOP
The boundary between research and execution is absolute:
* **`~/backtesting/`** is the **RESEARCH** environment.
* **`~/strategy/`** is the **APPROVED EXECUTION** environment.

No strategy may ever be placed in `~/strategy/` or deployed to OpenAlgo / paper trading / live trading without passing through every single gate in the quantitative lifecycle:

```text
========================================================================================
                          QUANTITATIVE STRATEGY RESEARCH LIFECYCLE
========================================================================================
  [ 1. IDEA / CONCEPT ]
          │
          ▼
  [ 2. STRATEGY SPECIFICATION (Phase 1) ]  <======== CURRENT ACTIVE STAGE
          │
          ▼
  [ 3. DATA ACQUISITION & INTEGRITY AUDIT (Phase 2) ]
          │
          ▼
  [ 4. MECHANICAL BASELINE BACKTEST (Phase 3) ]
          │
          ▼
  [ 5. CONTROLLED IN-SAMPLE RESEARCH (Phase 4) ]
          │
          ▼
  [ 6. OUT-OF-SAMPLE & WALK-FORWARD VALIDATION (Phase 5) ]
          │
          ▼
  [ 7. STRESS TESTING, SENSITIVITY & ROBUSTNESS (Phase 6) ]
          │
          ▼
  [ 8. FORMAL STRATEGY FREEZE (Immutable Spec & Code) ]
          │
          ▼
  [ 9. FORWARD PAPER OBSERVATION (Phase 7) ]
          │
          ▼
  [ 10. FORMAL APPROVAL GATEWAY ]
          │
          ▼
  [ 11. PRODUCTION EXECUTION (~/strategy/<strategy>/ -> OpenAlgo) ]
========================================================================================
```

---

## 2. STUDY OF THE COVERED CALL STRATEGY

### 2.1 Foundational Architecture: Long Underlying + Short Call
A Covered Call (often termed a *Buy-Write* when initiated simultaneously) is a dual-leg derivative overlay strategy consisting of:
1. **Long Underlying Asset Leg:** Holding the actual underlying cash shares, an equity exchange-traded fund (ETF), or long near-month futures contracts.
2. **Short Call Option Leg:** Selling (writing) call option contracts against the underlying position in a strictly covered ratio ($1:1$ contract multiplier coverage).

```text
                                COVERED CALL PAYOFF DIAGRAM
       Profit ^
              │                                      Maximum Profit: (K - S0) + C0
              │                               ┌────────────────────────────────────────
              │                              /
              │                             /
              │                            /
              │                           /
        C0 ───┼──────────────────────────/
              │                         /│
       0 ─────┼────────────────────────/─┼─────────────────────────────> Terminal Spot (ST)
              │                       /  │
              │                      /   │
              │                     /    │
              │                    /     │
              │                   /      │
              │                  /       │
              │                 /        │
      -S0+C0 ─┼────────────────/         │
              │               /          │
              │              /           │
              │             /            │
              │            /             │
              │           /              │
              └──────────┴───────────────┴─────────────────────────────
              0     Break-Even       Strike Price
                    (S0 - C0)            (K)
```

### 2.2 Mathematical Payoff Equations
Let:
* $S_0$ = Purchase / entry price of the underlying asset per share.
* $S_T$ = Spot settlement price of the underlying asset at option expiration date $T$.
* $K$ = Strike price of the written Call option contract.
* $C_0$ = Option premium collected per share upon writing the Call option ($C_0 > 0$).
* $Q$ = Total quantity of underlying shares held.
* $M$ = Option contract multiplier / lot size.

The net economic payoff per share at expiration $T$ is:
$$\Pi(S_T) = (S_T - S_0) - \max(0, S_T - K) + C_0$$

Expressed across terminal price domains:
$$\Pi(S_T) = 
\begin{cases} 
(S_T - S_0) + C_0, & \text{for } S_T \le K \quad (\text{Call expires OTM or ATM}) \\
(K - S_0) + C_0, & \text{for } S_T > K \quad (\text{Call expires ITM})
\end{cases}$$

### 2.3 Core Economic Characteristics
* **Premium Received ($C_0$):** Immediate cash credit received upon entering the short call. This premium provides an incremental cash yield and lowers the effective cost basis of the underlying asset.
* **Maximum Profit ($\Pi_{\max}$):**
  $$\Pi_{\max} = (K - S_0) + C_0 \quad \text{per share}$$
  Achieved whenever $S_T \ge K$. Any price appreciation of the underlying beyond strike $K$ is completely forfeited because each rupee of underlying gain above $K$ is exactly cancelled by a rupee of intrinsic loss on the short call.
* **Maximum Loss ($\Pi_{\min}$):**
  $$\Pi_{\min} = -S_0 + C_0 \quad \text{per share}$$
  Achieved if the underlying asset price drops to zero ($S_T = 0$). The trader bears the total loss of the capital invested in the underlying, mitigated only by the small retained premium $C_0$.
* **Break-Even Point ($S_{\text{BE}}$):**
  $$S_{\text{BE}} = S_0 - C_0$$
  The underlying can fall by at most the premium received before the aggregate position enters net negative P&L.
* **Asymmetric Risk Profile:** The strategy combines **capped upside** with **unhedged, substantial downside risk**.

### 2.4 The Greeks & Dynamic Sensitivity

| Greek Parameter | Long Underlying | Short Call Option Leg | Combined Covered Call Position | Institutional Trading Implication |
| :--- | :--- | :--- | :--- | :--- |
| **Delta ($\Delta$)** | $+1.00$ | $-\Delta_{\text{call}} \in [-1.0, 0.0]$ | $1.00 - \Delta_{\text{call}} \in [0.0, 1.0]$ | The position is always net long delta. Deep OTM calls provide near full market exposure ($\Delta_{\text{net}} \approx 0.85\text{--}0.95$). ATM calls cut delta in half ($\Delta_{\text{net}} \approx 0.50$). Deep ITM calls approach market neutrality ($\Delta_{\text{net}} \approx 0.05\text{--}0.15$). |
| **Gamma ($\Gamma$)** | $0.00$ | $-\Gamma_{\text{call}} \le 0.0$ | $-\Gamma_{\text{call}} \le 0.0$ | **Negative Gamma**. The position exhibits negative convexity: as the underlying surges, net delta drops (selling winners early); as the underlying crashes, net delta rises toward $+1.00$ (accumulating maximum risk on losers). Gamma risk peaks near the strike $K$ close to expiration (pin risk). |
| **Theta ($\Theta$)** | $0.00$ | $+\Theta_{\text{call}} > 0.0$ | $+\Theta_{\text{call}} > 0.0$ | **Positive Theta**. Time decay accrues directly to the strategy. Premium decay accelerates non-linearly as Days-to-Expiration (DTE) drops below 30 days, following the classic square-root-of-time decay curve. |
| **Vega ($\nu$)** | $0.00$ | $-\nu_{\text{call}} < 0.0$ | $-\nu_{\text{call}} < 0.0$ | **Negative Vega**. A sudden surge in market Implied Volatility (IV) inflates option value, creating an immediate mark-to-market loss on the short call. Volatility contraction (IV crush) benefits the position. |
| **Rho ($\rho$)** | $0.00$ | $-\rho_{\text{call}} < 0.0$ | $-\rho_{\text{call}}$ | Marginal interest rate sensitivity. In futures-based implementations, cost-of-carry is directly influenced by prevailing RBI repo / interbank rates. |

### 2.5 Implied Volatility, Skew, and Tail Dynamics
1. **Volatility Skew Impact:**
   * Equity markets typically exhibit structural put skew (downside puts trade at higher IV than upside calls). Consequently, out-of-the-money calls often trade at lower IVs relative to the ATM straddle, depressing the premium yield harvested unless overall market IV is elevated.
2. **Volatility Risk & IV Crush:**
   * Writing calls ahead of binary macro events (e.g., Union Budget, RBI MPC policy, corporate earnings) captures high IV, but subjects the underlying to massive gap risk. If IV collapses post-event without a large directional move, the short call captures rapid extrinsic profit; however, a directional gap exceeding the strike or break-even causes severe net loss.
3. **Overnight Gap Risk:**
   * **Adverse Gap Down:** A sudden overnight market gap down (e.g., geopolitical shock) exposes the underlying to full drawdown. The 2%–3% premium cushion is overwhelmed immediately.
   * **Favorable Gap Up:** A massive overnight gap up pushes the short call deep into the money. While the maximum profit is secured, the trader misses all surplus gains, and the position suffers severe liquidity drag if rolled or closed.
4. **Opportunity Cost:**
   * During sharp secular bull phases, the Covered Call forfeits the entire right tail of the return distribution. Compounding over long timeframes can cause a Covered Call portfolio to severely underperform simple buy-and-hold during persistent bull markets.
5. **Capped Upside vs. Limited Downside Cushioning:**
   * **CRITICAL PRINCIPLE:** **A Covered Call is NOT a complete downside hedge.**
   * The short call provides only a tiny, finite buffer (typically $1.0\%$ to $3.5\%$ per monthly cycle). If the underlying falls by $15\%$, $30\%$, or $50\%$, the trader absorbs virtually the entire crash. Calling a covered call a "hedge" is financially inaccurate; it is an income enhancement overlay with asymmetric downside exposure.

---

## 3. CORE RESEARCH HYPOTHESIS

### 3.1 Primary Research Hypothesis
> **"Can a systematic, rules-based Covered Call overlay strategy generate superior risk-adjusted returns (measured by Sharpe Ratio, Sortino Ratio, and Maximum Drawdown mitigation) compared to passively holding the same underlying asset, after incorporating full, realistic transaction costs, statutory taxes, exchange fees, and execution slippage in the Indian financial market?"**

### 3.2 Secondary Research Hypotheses
The research framework must systematically explore the following secondary hypotheses in future phases:

1. **Strike Selection Hypothesis ($H_1$):**
   * *Statement:* Dynamic delta-targeted strike selection (e.g., $20\Delta$ vs $30\Delta$) outperforms static percentage out-of-the-money strikes (e.g., $2.5\%$ OTM) by automatically adapting to widening and contracting volatility regimes.
2. **Expiry Cycle Hypothesis ($H_2$):**
   * *Statement:* Systematic weekly call writing captures higher gross annualized theta decay than monthly call writing, but net returns are inferior once weekly bid-ask slippage, turnover, and statutory STT friction are deducted.
3. **Early Profit-Taking / Premium Capture Hypothesis ($H_3$):**
   * *Statement:* Systematically closing or rolling the short call upon capturing $50\%$ to $75\%$ of the maximum credit eliminates late-tenor gamma risk and improves the Sortino ratio compared to holding every contract into expiry settlement.
4. **Defensive Rolling Hypothesis ($H_4$):**
   * *Statement:* Active rolling rules (rolling "up and out" when the call is tested, and rolling "down and out" when the underlying declines) mitigate drawdown and opportunity cost compared to passive unmanaged expirations.
5. **Volatility Regime Conditioning Hypothesis ($H_5$):**
   * *Statement:* Writing calls only when Implied Volatility Percentile (IVP) or India VIX exceeds a defined threshold (e.g., $\text{IVP} \ge 50\%$) produces significantly higher Sharpe ratios than unconditional, continuous mechanical cycle writing.
6. **Market Trend Regime Conditioning Hypothesis ($H_6$):**
   * *Statement:* Overlaying a trend-following filter (e.g., 200-day EMA or supertrend on the underlying) to suppress call writing during high-velocity bull breakouts reduces upside opportunity loss and enhances total return.

> [!IMPORTANT]
> **Phase 1 Restriction:** Under no circumstances are any of these hypotheses to be tested, simulated, or optimized in Phase 1. They represent theoretical research questions to be systematically evaluated in Phase 2+.

---

## 4. STRATEGY DESIGN DIMENSIONS & PARAMETER TAXONOMY

Before backtest code is designed, all strategy variables must be categorized. In Phase 1, all dimensions remain open for research and evaluation:

```text
                                STRATEGY DESIGN TAXONOMY
  ┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
  │ 1. UNDERLYING    │ 2. STRIKE SELECTION 3. EXPIRY TENOR │ 4. ENTRY TIMING  │
  │ • Index (Cash)   │ • Fixed % OTM    │ • Weekly (4-7 DTE│ • Fixed Day/Time │
  │ • Long Futures   │ • Fixed Pts OTM  │ • Monthly (25-35)│ • Expiry Roll    │
  │ • Cash Equity    │ • Delta Target   │ • Target DTE     │ • Trend Signal   │
  │ • Index ETF      │ • IV / Exp Move  │ • Bi-Monthly     │ • IV Rank Filter │
  └─────────┬────────┴─────────┬────────┴─────────┬────────┴─────────┬────────┘
            │                  │                  │                  │
            └──────────────────┼──────────────────┼──────────────────┘
                               │
  ┌────────────────────────────┴────────────────────────────┐
  │                   5. MANAGEMENT & LIFECYCLE             │
  │  ┌────────────────────────────┬───────────────────────┐ │
  │  │      EXIT CRITERIA         │     ROLLING RULES     │ │
  │  │ • Hold to Expiry           │ • No Early Roll       │ │
  │  │ • % Premium Capture (50/75)│ • Tested Roll (Up/Out)│ │
  │  │ • Stop-Loss on Short Call  │ • Untested Roll (Down)│ │
  │  │ • Underlying Trailing Stop │ • DTE Threshold Roll  │ │
  │  │ • Delta Inversion Exit     │ • Delta Band Rebalance│ │
  │  └────────────────────────────┴───────────────────────┘ │
  └─────────────────────────────────────────────────────────┘
```

### 4.1 Dimension 1: Underlying Implementation
* **Option A: Index Derivatives (NIFTY 50 / BANKNIFTY)**
  * *Cash Settlement:* Cash-settled on NSE; zero physical delivery obligations.
  * *Liquidity:* Deepest liquidity, tightest bid-ask spreads, continuous option chains.
  * *Implementation Modality:* Cannot buy cash index directly; must choose between:
    * *Long Futures + Short Call* (Covered Futures / Buy-Write overlay)
    * *Index ETF (NIFTYBEES) + Short Index Call* (Subject to lot size mismatch and tracking error)
* **Option B: Single-Stock Large-Cap Equities (e.g., RELIANCE, TCS, INFY)**
  * *Direct Demat Ownership:* Direct equity shares can be pledged or held in demat.
  * *Idiosyncratic Risk:* Vulnerable to single-stock earnings surprises, regulatory actions.
  * *Physical Delivery:* Subject to SEBI's physical delivery settlement mandate since Oct 2019.
  * *Capital Requirement:* High minimum capital per lot (₹8 Lakhs to ₹20 Lakhs per contract).
* **Option C: Long Near-Month Futures + Short Call**
  * *Lot Parity:* Exact 1:1 lot size matching with option contracts.
  * *Capital Efficiency:* Requires margin rather than 100% cash equity value.
  * *Basis Risk:* Exposes strategy to futures rollover cost (contango drag / negative roll yield).
* **Status:** `UNKNOWN — USER DECISION REQUIRED`

### 4.2 Dimension 2: Call Strike Selection
* **Method 1: Fixed Percentage OTM** (e.g., $+1.5\%$, $+2.5\%$, $+5.0\%$ above spot). Simple, but unresponsive to shifting volatility regimes.
* **Method 2: Fixed Absolute Points OTM** (e.g., $+300$ pts on NIFTY). Unsound across long multi-year horizons as underlying drifts.
* **Method 3: Delta-Targeted Strike** (e.g., $15\Delta$, $20\Delta$, $30\Delta$, $50\Delta$ ATM). Dynamically adjusts strike distance based on implied volatility.
* **Method 4: Implied Volatility / Expected Move Formula** ($K = S_t \times (1 + k \cdot \sigma_{\text{IV}} \sqrt{\text{DTE}/365})$).
* **Status:** `UNKNOWN — USER DECISION REQUIRED`

### 4.3 Dimension 3: Expiry Tenor
* **Weekly Contracts (4–7 DTE):** Accelerates theta decay capture, but multiplies transaction friction, STT, and gamma exposure.
* **Monthly Contracts (25–35 DTE):** Traditional institutional standard; captures larger absolute premiums; lower turnover and friction drag.
* **Status:** `UNKNOWN — USER DECISION REQUIRED`

### 4.4 Dimension 4: Entry Timing & Triggers
* **Calendar Scheduled:** Fixed weekday and time (e.g., every monthly expiry Thursday at 15:15 IST, or Friday at 09:30 IST).
* **Technical Indicator Trigger:** Sell call only when underlying is overbought (e.g., RSI(14) > 65 or Bollinger upper band test).
* **Volatility Regime Trigger:** Sell call only when India VIX > 15 or IV Rank > 50%.
* **Status:** `UNKNOWN — USER DECISION REQUIRED`

### 4.5 Dimension 5: Exit & Profit-Taking Rules
* **Hold to Expiration:** Contract is held until final expiry settlement.
* **Percentage Premium Capture:** Close call early if $50\%$, $70\%$, or $80\%$ of credit is harvested.
* **Call Stop-Loss:** Close call if premium doubles ($2\times C_0$) or triples.
* **Underlying Stop-Loss:** Liquidate entire structure if underlying falls by $X\%$.
* **Status:** `UNKNOWN — USER DECISION REQUIRED`

### 4.6 Dimension 6: Rolling Rules
* **Passive (No Early Roll):** Do not touch position between entry and settlement.
* **Roll Up & Out:** If spot breaches strike $K$, close existing call and open higher strike in next monthly cycle.
* **Roll Down & Out:** If spot drops significantly, roll call down to harvest additional premium.
* **Time-Based Roll:** Roll at $3\text{--}5$ DTE to avoid expiration-week gamma spikes.
* **Status:** `UNKNOWN — USER DECISION REQUIRED`

---

## 5. OWNERSHIP, LOT SIZING & ASSIGNMENT HANDLING

### 5.1 The Invariant Coverage Principle
The strategy backtest engine and execution framework must enforce the **Invariant Coverage Rule**:
$$\text{Covered Ratio} = \frac{\text{Quantity of Underlying Held}}{\text{Number of Short Call Contracts} \times \text{Contract Multiplier}} \ge 1.000$$

* The system must rigorously track:
  * `Underlying_Quantity_Held`
  * `Short_Call_Contracts`
  * `Contract_Lot_Size` (Multiplier)
  * `Covered_Quantity = Short_Call_Contracts * Contract_Lot_Size`
  * `Uncovered_Quantity = max(0, Short_Call_Contracts * Contract_Lot_Size - Underlying_Quantity_Held)`
* **STRICT ENGINE INVARIANT:** If `Uncovered_Quantity > 0`, the position is invalid. The system must never enter or leave a naked call position under any operational circumstance.

### 5.2 Expiration & Settlement Mechanics in Indian Markets
Derivative settlements in India operate under distinct exchange rules governed by SEBI and NSE Clearing Limited (NCL):

#### 1. European Style Exercise (All NSE / BSE Options)
* All equity and index options in India are **European Style** (`CE` / `PE`).
* **Rule:** Options cannot be exercised prior to the expiration date. Early assignment risk during the contract life is **strictly zero**. All assignment and settlement occurs strictly on expiry day at the official closing settlement price.

#### 2. Index Derivatives Settlement (NIFTY / BANKNIFTY)
* **Settlement Mechanism:** **Strictly Cash-Settled**.
* If Short Call expires Out-of-the-Money ($S_T \le K$): The option expires worthless. The seller retains $100\%$ of the initial premium $C_0$. No underlying transfer occurs.
* If Short Call expires In-the-Money ($S_T > K$): The clearing corporation (NCL) debits cash equal to:
  $$\text{Cash Debit} = (S_{\text{settle}} - K) \times \text{Lot Size}$$
  No equity shares or futures contracts change hands. The underlying holding remains untouched in the portfolio.

#### 3. Single-Stock Derivatives Settlement (Physical Settlement Mandate)
* **Regulatory Mandate:** In October 2019, SEBI mandated physical settlement for all stock derivatives.
* If Short Call expires Out-of-the-Money ($S_T \le K$): Option expires worthless; seller retains premium.
* If Short Call expires In-the-Money ($S_T > K$):
  * **Assignment Obligation:** The short call seller is **assigned** and MUST deliver physical shares equal to $\text{Lot Size}$ at the strike price $K$.
  * **Cash Equity Covered Position:** The trader's demat shares are automatically debited by the clearing corporation/depository (NSDL/CDSL). The trader receives cash equal to $K \times \text{Lot Size}$.
  * **Futures Covered Position:** Stock futures also settle physically on the same day. Long future shares to be received offset short call shares to be delivered, resulting in net cash settlement via clearing, but subject to stringent delivery margin rules.
  * **Staggered Delivery Margins:** Exchanges levy delivery margins on physical stock options starting from $T-4$ trading days before expiry (typically 10%, 25%, 50%, and 100% of contract value). The engine must model this capital lockup if stock options are chosen.
* **Status:** `UNKNOWN — DATA / MARKET RULE VALIDATION REQUIRED`

### 5.3 Formal Atomic Rolling Protocol
A roll must never be modeled as a single synthetic transaction. In reality, a roll consists of two independent transactions executed in a specific order with distinct transaction costs and slippage:

```text
========================================================================================
                          ATOMIC ROLLING TRANSACTION PROTOCOL
========================================================================================
 Step 1: Query current position & verify underlying ownership invariant.
   │
 Step 2: Place Buy-to-Close (BTC) order for existing Short Call contract.
   │
 Step 3: Await confirmation & fill of BTC order. Apply slippage & transaction costs.
   │
 Step 4: Calculate & book Realized P&L on the terminated Call leg.
   │
 Step 5: Verify underlying inventory is still fully intact and unencumbered.
   │
 Step 6: Place Sell-to-Open (STO) order for target Replacement Call contract.
   │
 Step 7: Await confirmation & fill of STO order. Apply slippage & transaction costs.
   │
 Step 8: Log new leg parameters (Strike, Expiry, Entry Premium, Execution Timestamp).
========================================================================================
```

---

## 6. DUAL-LEG POSITION ACCOUNTING & RECONCILIATION

The accounting engine must maintain two completely isolated ledgers that roll up into an auditable combined strategy ledger.

### 6.1 Underlying Leg Ledger
* `Underlying_Symbol`: Asset identifier (e.g., `NIFTY` or `RELIANCE`).
* `Underlying_Entry_Timestamp`: IST datetime of asset acquisition.
* `Underlying_Entry_Price`: Cost basis per share ($S_0$).
* `Underlying_Quantity`: Absolute quantity held ($Q$).
* `Underlying_Current_Price`: Mark-to-market spot/close price ($S_t$).
* `Underlying_Exit_Price`: Price at disposal or settlement ($S_{\text{exit}}$).
* `Underlying_Unrealized_PnL`: $(S_t - S_0) \times Q$.
* `Underlying_Realized_PnL`: $(S_{\text{exit}} - S_0) \times Q$.
* `Underlying_Dividends_Received`: Cash dividends paid during holding period.

### 6.2 Call Option Leg Ledger
* `Call_Contract_Symbol`: Specific exchange contract code.
* `Call_Strike`: Strike price ($K$).
* `Call_Expiry_Date`: Expiration timestamp ($T$).
* `Call_Entry_Timestamp`: Time of writing option.
* `Call_Entry_Premium`: Price received per share ($C_0$).
* `Call_Quantity`: Number of contracts $\times$ Lot Size ($Q_{\text{opt}}$).
* `Call_Current_Premium`: Current market mark-to-market premium ($C_t$).
* `Call_Exit_Price`: Buy-to-close or terminal settlement price ($C_{\text{exit}}$).
* `Call_Unrealized_PnL`: $(C_0 - C_t) \times Q_{\text{opt}}$.
* `Call_Realized_PnL`: $(C_0 - C_{\text{exit}}) \times Q_{\text{opt}}$.

### 6.3 Friction Ledger (Separately Audited)
* `Brokerage_Paid`: Explicit broker fee per trade or lot.
* `Exchange_Turnover_Charges`: NSE/BSE transaction fee.
* `Securities_Transaction_Tax (STT)`: Statutory STT calculated per regulatory slab.
* `SEBI_Turnover_Fee`: Regulatory charge.
* `Stamp_Duty`: State-mandated stamp duty on buy transactions.
* `GST`: Goods & Services Tax (18% on Brokerage + Exchange + SEBI fees).
* `Execution_Slippage`: Difference between modeled theoretical price and actual execution price.

### 6.4 Master Reconciliation Formula
At any time $t$, cumulative net portfolio equity $E_t$ and realized strategy P&L must satisfy:
$$\text{Net Strategy P\&L} = \sum \text{Underlying P\&L} + \sum \text{Call P\&L} + \sum \text{Dividends} - \sum \text{Taxes \& Statutory Charges} - \sum \text{Brokerage} - \sum \text{Slippage}$$

Every monthly settlement or roll must produce an auditable reconciliation ticket.

---

## 7. INDIAN MARKET CONSIDERATIONS & INSTITUTIONAL REALITIES

### 7.1 Exchange & Contract Specification Landscape
* **Exchanges:** National Stock Exchange of India (NSE) is the primary F&O venue with $>95\%$ derivative market share; Bombay Stock Exchange (BSE) has active liquidity primarily in SENSEX / BANKEX.
* **Contract Multiplier / Lot Size History:**
  * In the Indian market, lot sizes are not fixed at 100 shares (unlike US markets). Lot sizes are periodically adjusted by NSE circulars to keep the contract value between ₹5 Lakhs and ₹10 Lakhs (revised upward to ₹15 Lakhs to ₹20 Lakhs per SEBI guidelines).
  * *Example (NIFTY Lot Size Evolution):* 50 → 75 → 50 → 25 (as of November 2024 / recent circulars).
  * *Requirement:* The backtest engine cannot use a single static lot size. It must load a dynamic historical lot size master table mapped to expiry dates.
* **Expiry Day Rationalization & Historical Shifts:**
  * Historically, all NSE equity derivatives expired on the **last Thursday** of the month.
  * In recent years, multiple weekly expiries proliferated (BANKNIFTY on Wednesdays, FINNIFTY on Tuesdays, MIDCPNIFTY on Mondays, SENSEX on Fridays, NIFTY on Thursdays).
  * SEBI's 2024 regulatory framework restricted each exchange to only **one benchmark index with weekly expiry** (e.g., NIFTY on NSE, SENSEX on BSE).
  * *Requirement:* Backtest engine must ingest historical contract masters that correctly reflect the actual historical expiration weekday for each specific contract.

### 7.2 Statutory & Transaction Cost Architecture (India)
The simulation must support a parametric cost model reflecting the actual Indian tax regime:

| Component | Equity Cash Delivery (Underlying Buy) | Equity Cash Delivery (Underlying Sell) | Futures (Buy / Sell) | Options Selling (Entry) | Options Buying (Exit / BTC) | Options Exercise / Assignment (Settlement) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **STT** | 0.1% on Turnover | 0.1% on Turnover | 0.02% on Sell Turnover | 0.1% on Premium Turnover (revised from 0.0625%) | Nil | 0.125% of Settlement Value (Intrinsic) on Buyer |
| **Exchange Charges** | ~0.00325% | ~0.00325% | ~0.0019% | ~0.05% on Premium | ~0.05% on Premium | Standard cash settlement fee |
| **GST** | 18% on (Brokerage + Exch + SEBI) | 18% on (Brokerage + Exch + SEBI) | 18% on (Brokerage + Exch + SEBI) | 18% on (Brokerage + Exch + SEBI) | 18% on (Brokerage + Exch + SEBI) | 18% on fees |
| **Stamp Duty** | 0.015% on Buy | Nil | 0.002% on Buy | 0.003% on Buy Premium | 0.003% on Buy Premium | Applicable on physical transfer |
| **SEBI Turnover Fee** | ₹10 / Crore | ₹10 / Crore | ₹10 / Crore | ₹10 / Crore | ₹10 / Crore | ₹10 / Crore |
| **Brokerage** | ₹20/order or 0.05% | ₹20/order or 0.05% | ₹20/order or 0.05% | ₹20/order flat | ₹20/order flat | Varies by broker |

* **Rule:** Do not hard-code current rates into logic. All rates must be read from a versioned configuration file (`cost_model_india.json`).

### 7.3 Liquidity & Bid-Ask Spread Dynamics
* **Strike Liquidity Profile:** In the Indian options market, liquidity is heavily concentrated in:
  1. At-the-Money (ATM) strikes and near OTM strikes ($\pm 1\%$ to $\pm 3\%$).
  2. Round-number strikes (e.g., multiples of 500 or 1000 on NIFTY; multiples of 100 on stocks).
  3. The immediate nearest weekly or monthly expiry.
* **Illiquidity Trap:** Far OTM options (e.g., > 5% OTM) often exhibit bid-ask spreads exceeding 20% to 50% of the option premium, with zero bid depth. An algorithm attempting to sell 10Δ calls on illiquid strikes will suffer catastrophic execution slippage.
* **Open Interest (OI) Filter Requirement:** Simulated orders must verify minimum contract Open Interest (e.g., $\text{OI} \ge 100,000$ contracts) and 5-minute bar volume before assuming fill validity.

---

## 8. HISTORICAL DATA REQUIREMENTS & INTEGRITY

To ensure institutional validity, data requirements are partitioned into three tiers:

```text
                               DATA ARCHITECTURE SCHEMA
   ┌────────────────────────────────────────────────────────────────────────┐
   │ 1. MANDATORY DATA (Engine cannot run without this)                     │
   │    • Underlying 1-minute or Daily OHLCV with accurate corporate action │
   │      splits and dividend adjustment factors.                           │
   │    • Historical Options EOD/Minute OHLCV with exact Strike, Expiry,    │
   │      Option Type (CE), and Volume.                                     │
   │    • Exchange Contract Master (Mapping symbol -> expiry -> lot size).  │
   │    • Official Expiry Settlement Prices from Clearing Corporation.      │
   └────────────────────────────────────┬───────────────────────────────────┘
                                        │
   ┌────────────────────────────────────┴───────────────────────────────────┐
   │ 2. PREFERRED DATA (Required for high-fidelity research)                │
   │    • Historical 1-minute / 5-minute Option Bar Data.                   │
   │    • Historical Open Interest (OI) per strike.                         │
   │    • Top-of-Book Bid/Ask Quotes or Spread Estimates.                   │
   │    • Pre-calculated Historical Implied Volatility (IV) & Delta.        │
   └────────────────────────────────────┬───────────────────────────────────┘
                                        │
   ┌────────────────────────────────────┴───────────────────────────────────┐
   │ 3. OPTIONAL / DERIVED DATA                                             │
   │    • Full Historical Order Book / Level-2 Depth.                       │
   │    • India VIX Index tick/minute series.                               │
   │    • Real-time depository borrowing rates (SLB rates).                 │
   └────────────────────────────────────────────────────────────────────────┘
```

### 8.1 Data Quality Risks & Mitigations

1. **Survivorship Bias:**
   * *Risk:* Selecting only current NIFTY 50 constituents or current F&O stocks. Stocks that fell out of the index, entered bankruptcy, or were removed from F&O (e.g., DHFL, YES BANK, RCOM) are excluded, drastically inflating historical returns.
   * *Mitigation:* For stock-level covered calls, use point-in-time constituent lists. For index-level, use the continuous NIFTY 50 cash/futures series.
2. **Look-Ahead Bias:**
   * *Risk:* Calculating strikes or signals at 15:30 using the day's close price, but assuming execution at the day's open or mean price.
   * *Mitigation:* Signals generated at bar close $t$ may only be filled at bar open $t+1$ or bar close $t$ with an explicit latency and next-tick execution buffer.
3. **Missing Strike & Expired Contract Data:**
   * *Risk:* Commercial data vendors frequently purge expired derivative contracts or fail to record strikes that were added mid-series due to extreme market moves.
   * *Mitigation:* Maintain a contract verification audit step before backtest ingestion. If a chosen strike is missing from the dataset, the engine must flag an unresolvable market data exception rather than silently filling at an imaginary price.
4. **Corporate Action Distortions:**
   * *Risk:* A 2:1 stock split cuts the share price in half. An unadjusted underlying series shows an artificial 50% crash, triggering false stops, while option strikes are adjusted by the exchange (strike halved, lot size doubled).
   * *Mitigation:* Corporate action adjustments must synchronize both the underlying share ledger and the option contract multiplier identically.

---

## 9. PROPOSED BACKTEST ARCHITECTURE

*(Design Specification Only — No Code Implemented in Phase 1)*

The backtesting system must operate as an **event-driven, strictly chronological simulation pipeline**:

```text
========================================================================================
                        EVENT-DRIVEN SIMULATION ARCHITECTURE
========================================================================================
                                 [ HISTORICAL DATA FEED ]
                               (Bar t: Underlying & Chains)
                                            │
                                            ▼
                           [ CONTRACT RESOLVER & FILTER ]
                           (Find liquid strikes, DTE, OI)
                                            │
                                            ▼
                             [ SIGNAL GENERATION ENGINE ]
                             (Entry, Exit, or Roll Triggers)
                                            │
                                            ▼
                           [ INVARIANT COVERAGE VALIDATOR ]
                          (Verify 1:1 underlying coverage)
                                            │
                                            ▼
                           [ ORDER EXECUTION SIMULATOR ]
                      (Apply slippage, bid-ask, fill delays)
                                            │
                                            ▼
                         [ POSITION & LEDGER BOOKKEEPING ]
                     (Underlying Leg + Call Leg + Cash Ledger)
                                            │
                                            ▼
                      [ LIFECYCLE & SETTLEMENT RECONCILER ]
                      (Handle expiry, cash/physical settle)
                                            │
                                            ▼
                         [ TRANSACTION COST & TAX ENGINE ]
                       (STT, GST, Exch, Stamp Duty, Broker)
                                            │
                                            ▼
                           [ PERFORMANCE & METRIC ENGINE ]
                     (Drawdown, Sharpe, Sortino, Benchmarking)
========================================================================================
```

### Architectural Guarantees
1. **Zero Look-Ahead Invariant:** Every calculation at timestamp $t$ has access only to data with timestamps $< t$.
2. **Deterministic Reproducibility:** Given the identical dataset and configuration JSON, the simulation must produce bit-for-bit identical P&L, ledger records, and performance metrics.
3. **Isolated Modular Engines:** The execution simulator, cost engine, and ledger are completely decoupled from strategy logic.

---

## 10. MECHANICAL BASELINE STRATEGY SPECIFICATION

To prevent premature optimization, we specify a clean, strictly mechanical, non-optimized **Baseline Covered Call Strategy**. All subsequent research variants will be measured against this baseline.

### 10.1 Baseline Strategy Definition
* **Asset:** Underlying Asset = Selected benchmark index or stock (to be finalized upon user decision).
* **Underlying Leg:** Buy and hold exactly 1 contract lot of the underlying at inception ($t_0$).
* **Call Writing Rule:**
  * Write exactly 1 monthly Call option contract on the nearest monthly expiry cycle.
  * **Timing:** Initiate on the first trading day of the monthly expiry cycle (or immediately upon previous monthly expiry settlement at 15:15 IST).
  * **Strike Selection:** Choose the nearest available strike that is approximately **2.0% Out-of-the-Money (OTM)** relative to spot price ($K \approx 1.02 \times S_t$), or nearest available standard strike above $+2\%$.
* **Management & Exit Rule:**
  * **Pure Hold to Expiry:** The short call is held until the final expiration settlement.
  * No intra-cycle profit taking (no 50% capture exit).
  * No stop-loss on the call option.
  * No dynamic rolling during the month.
* **Rollover Rule:**
  * On monthly expiry day at 15:15 IST:
    1. Settle existing call (cash settlement or expiry worthless).
    2. Write the next month's ~2% OTM call contract.
* **Optimization Constraint:** This baseline specification is **NOT OPTIMIZED**. It represents a naive, rules-based, industry-standard mechanical covered call benchmark.

### 10.2 Parameter Separation Taxonomy

```text
┌───────────────────────────────────────┬───────────────────────────────────────┐
│     BASELINE PARAMETERS (FROZEN)      │    RESEARCH PARAMETERS (EXPLORATORY)  │
├───────────────────────────────────────┼───────────────────────────────────────┤
│ • Fixed 2% OTM Strike                 │ • Delta targeting (10Δ, 20Δ, 30Δ, 40Δ)│
│ • Monthly Expiration Cycle            │ • Weekly vs Bi-weekly vs Monthly DTE  │
│ • Fixed 15:15 Expiry Roll             │ • IV Rank / VIX Regime Filtering      │
│ • No Intra-Month Management           │ • Dynamic Profit Targets (50%, 75%)   │
│ • 100% Notional Coverage Ratio        │ • Dynamic Rolling (Up & Out / Down)   │
│ • Fixed Realistic Slippage Model      │ • Trend / Moving Average Overlays     │
└───────────────────────────────────────┴───────────────────────────────────────┘
```

---

## 11. PERFORMANCE & RISK EVALUATION METRICS

The research platform must compute and report the following comprehensive metric suite:

### 11.1 Portfolio & Return Metrics
* **Initial Capital ($C_{\text{start}}$)** and **Final Capital ($C_{\text{end}}$)**.
* **Total Return (%):** $\frac{C_{\text{end}} - C_{\text{start}}}{C_{\text{start}}} \times 100$.
* **Compounded Annual Growth Rate (CAGR %):** $\left(\frac{C_{\text{end}}}{C_{\text{start}}}\right)^{\frac{1}{\text{Years}}} - 1$.
* **Annual & Monthly Returns Distribution Table** (Matrix of monthly percentage returns).
* **Gross Premium Collected vs. Net Realized Premium.**

### 11.2 Risk & Drawdown Metrics
* **Maximum Drawdown (MDD %):** Peak-to-trough maximum portfolio decline.
* **Max Drawdown Duration:** Peak-to-recovery time in trading days.
* **Annualized Volatility ($\sigma_{\text{ann}}$):** Standard deviation of daily returns annualized ($\times \sqrt{252}$).
* **Value-at-Risk (VaR 95%, 99%) & Conditional VaR (CVaR / Expected Shortfall).**

### 11.3 Risk-Adjusted Performance Ratios
* **Sharpe Ratio:** $\frac{R_p - R_f}{\sigma_p}$ (Assuming Indian 91-day T-Bill rate as $R_f$, e.g., 6.5%).
* **Sortino Ratio:** $\frac{R_p - R_f}{\sigma_{\text{downside}}}$ (Penalizing only downside volatility).
* **Calmar Ratio:** $\frac{\text{CAGR}}{|\text{Max Drawdown}|}$.
* **Omega Ratio:** Ratio of probability-weighted gains versus losses relative to benchmark return threshold.

### 11.4 Trade & Execution Metrics
* **Win Rate (%):** Percentage of option cycles ending with net positive P&L.
* **Profit Factor:** Gross Profits / Gross Losses.
* **Average Trade P&L, Median Trade P&L, Best Trade, Worst Trade.**
* **Assignment Frequency (%):** Percentage of cycles ending with call ITM ($S_T > K$).
* **Cumulative Transaction Costs & Statutory Friction (% of Gross Profit).**
* **Capital Utilization & Peak Margin Requirement.**

### 11.5 Relative Benchmark Metrics (vs. Buy & Hold)
* **Alpha ($\alpha$) & Beta ($\beta$)** relative to underlying buy-and-hold.
* **Upside Capture Ratio:** Performance of strategy during positive benchmark months / Benchmark return.
* **Downside Capture Ratio:** Performance of strategy during negative benchmark months / Benchmark return.
* **Excess Return over Buy & Hold:** $\text{CAGR}_{\text{Strategy}} - \text{CAGR}_{\text{Underlying}}$.
* **Information Ratio:** Active return divided by tracking error.

---

## 12. BENCHMARK & COMPARATIVE EVALUATION METHODOLOGY

Every backtest evaluation in Phase 2+ must present a three-way comparative triangulation:

```text
========================================================================================
                          TRIANGULATION BENCHMARK MATRIX
========================================================================================
       METRIC               1. BUY & HOLD           2. COVERED CALL       3. RESEARCH
                             UNDERLYING                 BASELINE            VARIANTS
────────────────────────────────────────────────────────────────────────────────────────
 CAGR (%)                       ...                       ...                 ...
 Max Drawdown (%)               ...                       ...                 ...
 Annualized Volatility (%)      ...                       ...                 ...
 Sharpe Ratio (Rf=6.5%)         ...                       ...                 ...
 Sortino Ratio                  ...                       ...                 ...
 Calmar Ratio                   ...                       ...                 ...
 Total Friction Paid            ...                       ...                 ...
 Net Terminal Wealth            ...                       ...                 ...
 Upside Capture Ratio          100.0%                     ...                 ...
 Downside Capture Ratio        100.0%                     ...                 ...
========================================================================================
```

### Fundamental Benchmark Evaluation Principle
The research objective is **NOT** simply: *"Did the strategy make money?"*  
The core research test is:
> **"Did the strategy harvest sufficient option premium to justify forfeiting the fat right-tail upside, achieving a demonstrably superior Sharpe/Sortino ratio and reduced drawdown compared to simply holding the underlying asset net of all friction?"**

---

## 13. ANTI-OVERFITTING & SCIENTIFIC INTEGRITY FRAMEWORK

To prevent data mining, p-hacking, and curve-fitting, the research workflow must strictly enforce the following protocols:

```text
========================================================================================
                           DATA SPLITTING & VALIDATION FUNNEL
========================================================================================
 [ FULL HISTORICAL DATASET ]
             │
             ├───> [ IN-SAMPLE (IS) DISCOVERY SET: 60% ]
             │     (Exploratory research, hypothesis formulation, baseline test)
             │
             ├───> [ OUT-OF-SAMPLE (OOS) HOLDOUT SET: 20% ]
             │     (Locked holdout; tested ONCE after parameter freeze)
             │
             └───> [ WALK-FORWARD & REGIME STRESS SET: 20% ]
                   (Anchored / rolling walk-forward optimization, crash regimes)
========================================================================================
```

### 13.1 Validation Rules
1. **Immutable In-Sample / Out-of-Sample Boundary:**
   * Under no circumstances may OOS data be accessed during preliminary exploration.
   * Testing an idea on OOS data burns the OOS dataset. If an idea fails OOS, it cannot be tweaked and re-tested on the same OOS data.
2. **Deflated Sharpe Ratio (DSR):**
   * Whenever multiple parameter variations (e.g., $N$ strike tests) are evaluated, the reported Sharpe ratio must be penalized using Marcos López de Prado's Deflated Sharpe Ratio to account for selection bias and multiple testing:
   $$\text{DSR} = f\left(\widehat{\text{SR}}, N, \text{Skewness}, \text{Kurtosis}, \text{Variance of Trials}\right)$$
3. **Parameter Stability & Flatness Check:**
   * A strategy variant is deemed robust only if its performance parameter surface is flat. If a 20Δ call shows a Sharpe of 1.4 but 18Δ and 22Δ show Sharpes of 0.6, the 20Δ result is rejected as spurious curve-fitted noise.
4. **Experiment Registry & Traceability:**
   * Every research experiment must be assigned a unique immutable identifier (e.g., `EXP_CC_001`).
   * The registry must record: Git commit hash, dataset hash, exact configuration JSON, seed value, execution logs, and full performance summary.

---

## 14. STRATEGY RISKS, BOUNDARY CONDITIONS & LIMITATIONS

A rigorous specification must document all structural failure modes:

1. **Unhedged Tail Risk / Left-Tail Exposure:**
   * In a 2008 or March 2020 style liquidity crash, the underlying asset can drop 30%–50% in weeks. The 2%–3% call premium collected is trivial. The covered call trader suffers almost the entire underlying catastrophic loss.
2. **Upside Opportunity Cost in Runaway Bull Markets:**
   * During explosive post-crisis recoveries or secular bull rallies (e.g., 2020–2021), underlying assets may rally 50%–100%. The covered call strategy earns only its modest strike increment + premium, underperforming the underlying by enormous margins.
3. **Slippage & Friction Erosion:**
   * Options trading in India incurs substantial statutory friction (STT on turnover, GST on charges, exchange fees). In weekly expiry writing, cumulative transaction costs can consume 20% to 40% of the gross premium collected.
4. **Physical Delivery Surcharge & Liquidity Squeeze (Stock Derivatives):**
   * If single-stock options are selected, physical settlement rules impose severe capital locks during expiry week. Any failed delivery incurs exchange auction penalties (up to 20% of value).
5. **Basis & Rollover Drag (Futures Implementation):**
   * If implemented via Long Futures + Short Call, the trader must roll futures contracts every month. If futures trade at a persistent premium (contango) that collapses into expiry, or if roll execution suffers slippage, the strategy suffers persistent negative carry.

---

# DECISIONS REQUIRED FROM USER

Before Phase 2 (Data Validation & Ingestion) can commence, the user must provide explicit directional decisions on the following questions. **No assumptions will be made.**

### Decision 1: Target Underlying Asset & Market Segment
* Which asset category and specific instrument shall be the target for this research?
  * [ ] **Option 1A (Recommended):** NIFTY 50 Index (Implemented as Long Futures + Short Call / Synthetic Covered Call). *Benefits: Cash settled, deepest liquidity, tightest spreads, no physical delivery risk.*
  * [ ] **Option 1B:** NIFTY 50 Index via ETF (e.g., NIFTYBEES in Cash Equity + Short NIFTY Call Option). *Note: Must address lot size divergence.*
  * [ ] **Option 1C:** Specific Large-Cap Liquid Stock (e.g., RELIANCE, TCS, or INFY). *Note: Incurs physical settlement delivery rules.*
  * [ ] **Option 1D:** Other (User specified).

### Decision 2: Expiration Tenor for Primary Investigation
* What contract expiration frequency should form the primary focus?
  * [ ] **Option 2A (Recommended):** Monthly Expiries (Entering ~25–35 DTE, rolling on monthly expiry day). *Lower friction, cleaner historical data.*
  * [ ] **Option 2B:** Weekly Expiries (Entering ~5–7 DTE). *Higher theta capture rate, but substantially higher friction and gamma risk.*
  * [ ] **Option 2C:** Dual comparative study (Run both independently).

### Decision 3: Initial Capital & Portfolio Sizing Assumptions
* What hypothetical base portfolio capital should be modeled?
  * *Context:* 1 lot of NIFTY 50 futures / options notional value is approximately ₹12 Lakhs to ₹15 Lakhs. For single-stocks, 1 lot ranges from ₹8 Lakhs to ₹20 Lakhs.
  * [ ] **Option 3A:** ₹15,00,000 (1 Lot fully covered).
  * [ ] **Option 3B:** ₹50,00,000 (Multi-lot scalable).
  * [ ] **Option 3C:** Other specific capital base specified by user.

### Decision 4: Historical Data Source & Date Range
* What historical data horizon should be targeted for the research?
  * [ ] **Option 4A (Recommended):** 5 Years (e.g., 2019 – 2024 / 2025). Captures pre-COVID, COVID crash, 2020–2021 bull run, 2022 consolidation, and 2023–2024 momentum.
  * [ ] **Option 4B:** 3 Years (e.g., 2021 – 2024). Higher availability of clean 1-minute options data.
  * [ ] **Option 4C:** User-provided historical dataset (Specify format and location).

---

# RECOMMENDED PHASE 2

Upon formal user sign-off and receipt of decisions on the open items above, **Phase 2: Data Acquisition, Validation & Environment Ingestion** will encompass:

1. **Historical Data Sourcing & Verification:**
   * Acquire official daily and intraday historical series for the selected underlying asset.
   * Acquire clean historical options chain datasets with complete strike series, Greeks, volume, and open interest.
   * Validate data against official NSE Bhavcopy settlement files.
2. **Contract Master & Corporate Action Pipeline:**
   * Build the historical contract master resolver (mapping dynamic lot sizes, strike intervals, and expiry calendar shifts).
   * Ingest and verify corporate actions table (splits, bonuses, dividends).
3. **Data Integrity Audit:**
   * Run automated diagnostics for missing strikes, unrecorded expired contracts, zero-volume anomalies, and timestamp misalignments.
   * Generate `data_audit_report.md` inside `~/backtesting/covered call/data/`.
4. **Freeze Clean Research Dataset:**
   * Formally lock and checksum the In-Sample and Out-of-Sample datasets before building backtest logic.

> [!CAUTION]
> **STOP CONDITION:** Phase 1 is strictly limited to specification and research scoping. Do not write backtest code, download datasets, execute simulations, or modify files outside `~/backtesting/covered call/` until the user provides answers to the decisions above and gives explicit authorization to proceed to Phase 2.
