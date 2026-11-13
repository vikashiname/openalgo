# STRATEGY INTEGRITY AND FEASIBILITY REVIEW
## Candidate: EXP-064-INT5 Covered Call Overlay

**Document ID:** AGY-REV-CC-001  
**Candidate Name:** Systematic NIFTY Covered Call Overlay (Candidate `EXP-064-INT5`)  
**Scope:** `~/backtesting/covered call/forward/` and existing research artifacts under `~/backtesting/covered call/`  
**Review Type:** Read-Only Strategy Integrity, Hedging Equivalence & Feasibility Audit  
**Date:** October 13, 2026  
**Auditor:** AGY Quantitative Validation Engine  

---

## 1. Executive Summary & Review Verdict

A forensic, read-only strategy-integrity review of candidate **EXP-064-INT5** was conducted to verify the mathematical, structural, and regulatory equivalence between:
1. The historical backtest engine that generated the reported metrics (₹10,89,508.91 net PnL, 7.49% CAGR, 5.21% max DD).
2. The operational forward paper-observation protocol proposed for real-time tracking.

### Core Review Finding:
> [!CAUTION]
> **CRITICAL ARCHITECTURAL DISCREPANCY IDENTIFIED:**  
> The historical backtest modeled a **100% linear delta-1.0 synthetic underlying index basket** with an exact 1-to-1 lot size multiplier ($L_t = 65, 75, 50, 25$), zero cash equity frictions, and perfect mathematical payoff netting.  
> 
> Proposing **fractional cash ETF (`NIFTYBEES`) sizing** (e.g. capping ETF at 75% of ₹15L capital = ~45 index shares) against an **indivisible 1-lot exchange call option** (65 shares) creates an **under-covered ratio call write**. Above the short call strike, the portfolio becomes **NET SHORT 20 NIFTY INDEX SHARES with UNLIMITED UPSIDE LIABILITY**. Fractional ETF sizing is **NOT equivalent** to the historical backtest and violates basic covered-call risk boundaries.

---

## 2. Forensic Trace of the Historical Backtest Structure

A code-level inspection of [`optimization_engine.py`](file:///Users/mac/backtesting/covered%20call/research/optimization_engine.py) and [`strategy_backtester.py`](file:///Users/mac/Desktop/openalgo/strategies/research/engine/strategy_backtester.py#L177-L197) reveals the exact instruments, contract multipliers, and hedging mechanics used to generate the baseline and candidate results:

```text
========================================================================================================
                          HISTORICAL BACKTEST INSTRUMENT & PAYOFF TRACE
========================================================================================================
 Leg                    Instrument Modeled             Multiplier ($L_t$)        Payoff & Cost Modeling
--------------------------------------------------------------------------------------------------------
 Long Underlying Leg    NIFTY 50 Spot Index Notional   $1.0 \times \text{lot}$   $\text{Spot PnL} = (S_t - S_0) \times L_t$
                        (Synthetic Linear Basket)      (65, 75, 50, 25)          Zero brokerage, Zero STT,
                                                                                 Zero delivery drag, Zero TER.
 Short Option Leg       NSE European Call Option       $1.0 \times \text{lot}$   $\text{Opt PnL} = (P_0 - P_t) \times L_t$
                        (`OPTIDX NIFTY CE`)            (65, 75, 50, 25)          Full statutory taxes, fees,
                                                                                 and execution slippage deducted.
 Combined Position      Synthetic Covered Call         $L_t \equiv L_t$          Net terminal payoff:
                                                       (Exact 1:1 parity)        $\min(S_T - S_0, K - S_0)L_t + P_0 L_t$
========================================================================================================
```

### Forensic Backtest Observations:
1. **Instrument Identity:** The historical underlying leg was **NOT** `NIFTYBEES`. It was a frictionless, continuous spot index notional basket.
2. **Hedge Parity ($1:1$):** On every trade, underlying quantity was strictly identical to option contract lot size ($Q_{\text{underlying}} = L_{\text{option}}$).
3. **Friction Imbalance:** All transaction costs, slippage, STT, and exchange fees were applied exclusively to the option leg. Cash market equity delivery friction was zero.
4. **Payoff Netting:** At expiry, if spot closed above strike $K$, the option intrinsic loss $-(S_T - K) \times L$ was perfectly absorbed by spot equity gains $(S_T - S_0) \times L$, capping upside at $(K - S_0)L + \text{Premium}$. The position had **zero net delta above strike $K$**.

---

## 3. Structural Comparison: Backtest vs. Forward Protocol vs. Futures Buy-Write

| Dimension | Historical Backtest (EXP-064-INT5) | Proposed Forward Protocol (`NIFTYBEES` Fractional) | Actual Futures Buy-Write (`FUTIDX` + Short Call) |
| :--- | :--- | :--- | :--- |
| **Underlying Leg** | Synthetic Spot Index Basket | Cash ETF (`NIFTYBEES`) in CM Segment | Current-Month NIFTY Futures in F&O |
| **Market Segment** | Single-Segment (F&O Proxy) | Cross-Segment: Cash Market + F&O | Single-Segment: F&O only |
| **Underlying Multiplier**| Exactly 1 market lot ($L = 65$) | Fractional ETF units ($Q \approx 45$ index eq.) | Exactly 1 market lot ($L = 65$) |
| **Option Multiplier** | Exactly 1 market lot ($L = 65$) | Minimum exchange lot ($L = 65$) | Minimum exchange lot ($L = 65$) |
| **Underlying Delta** | **+65.0** (100% index coverage) | **+45.0** (only 69.2% index coverage) | **+65.0** (100% index coverage) |
| **Short Call Delta** | **-16.25** ($\Delta = -0.25 \times 65$) | **-16.25** ($\Delta = -0.25 \times 65$) | **-16.25** ($\Delta = -0.25 \times 65$) |
| **Net Entry Delta** | **+48.75** (Net Long) | **+28.75** (Net Long) | **+48.75** (Net Long) |
| **Delta Above Strike $K$**| **0.00 (Flat / Capped Profit)** | **-20.00 (NET SHORT NIFTY!)** | **0.00 (Flat / Capped Profit)** |
| **Terminal Bull Risk** | Zero upside risk (Capped gain) | **UNLIMITED UPSIDE LIABILITY!** | Zero upside risk (Capped gain) |
| **Capital Deployed** | ₹16,25,000 (notional tracked) | ₹11,25,000 (ETF) + ₹3,75,000 (Cash Buffer) | SPAN Margin: **~₹95,000 to ₹1,20,000** |
| **Margin Relief** | N/A (Theoretical) | Zero automatic offset (Demat pledge required) | Direct SPAN portfolio relief (~70% reduction) |
| **Settlement Mechanics** | Mathematical netting | **CRITICAL: ETF cannot settle option cash debit!** | **NCL nets futures & option cash in F&O** |

---

## 4. Quantitative Breakdown: Capital, Hedge Ratio & Residual Risk

### 4.1 The Under-Covered Ratio Call Trap
Assume current market conditions: NIFTY Spot $S = 25,000$, Lot Size $L = 65$, Option Strike $K = 25,600$, Reference Portfolio Capital = ₹15,00,000.

1. **Full 1-Lot Notional Requirement:**
   $$\text{Notional Value} = 25,000 \times 65 = ₹16,25,000$$
   To fully cover 1 lot with `NIFTYBEES` requires ₹16.25 Lakhs, exceeding portfolio capital by ₹1.25 Lakhs (108.3% allocation with zero cash buffer).

2. **Fractional Sizing Calculation (75% Cap):**
   If capital is capped at 75% (₹11,25,000 in ETF, ₹3,75,000 in cash):
   $$\text{Index Equivalent Held} = \frac{₹11,25,000}{25,000} = 45.0 \text{ shares}$$
   $$\text{Hedge Ratio} = \frac{45.0}{65.0} = 0.6923 \ (69.2\% \text{ covered})$$

3. **Residual Directional Risk in a Bull Surge:**
   If NIFTY surges to 27,000 (+2,000 points, call expires 1,400 points ITM):
   - **Long ETF Leg Gain:** $45 \times (27,000 - 25,000) = +₹90,000$
   - **Short Call Leg Intrinsic Loss:** $-65 \times (27,000 - 25,600) = -₹91,000$
   - **Option Premium Collected:** $+₹150 \times 65 = +₹9,750$
   - **Net PnL:** $+₹90,000 - ₹91,000 + ₹9,750 - \text{Costs} = +₹8,750$
   - If NIFTY surges to 28,000 (+3,000 points, call expires 2,400 points ITM):
     - **Long ETF Gain:** $45 \times 3,000 = +₹1,35,000$
     - **Short Call Loss:** $-65 \times 2,400 = -₹1,56,000$
     - **Net PnL:** $+₹1,35,000 - ₹1,56,000 + ₹9,750 = -₹11,250 \ \mathbf{(NET\ LOSS\ IN\ A\ BULL\ MARKET!)}$
   - For every 100 points NIFTY rises above 27,500, the portfolio loses an additional **-₹2,000** net.

### 4.2 Cross-Segment Margin & Cash Settlement Mismatch
Under SEBI circular SEBI/HO/MRD/DP/CIR/P/2018/102:
* Index derivatives are **strictly cash-settled**. ETF delivery does not exist.
* If the short call expires 1,000 points ITM, NCL debits **₹65,000 in hard cash** on settlement day ($T+1$).
* The 4,105 units of `NIFTYBEES` held in Demat **cannot clear this debit**.
* The unencumbered cash buffer of ₹3,75,000 can absorb up to ~575 points of ITM debit. A move beyond that triggers a broker cash margin shortfall and penalty.

### 4.3 Strategic Synthesis: Three Execution Paths
1. **Path A (Pure Cash ETF Buy-Write):** Allocate ₹17.5L to ₹18.0L reference capital to fully fund 1 full lot of `NIFTYBEES` ($65 \times S \approx ₹16.25L$) plus a ₹1.5L unencumbered cash buffer.
2. **Path B (Futures Buy-Write — Single Segment F&O):** Buy 1 NIFTY Future + Sell 1 NIFTY Call. Total SPAN margin = ₹1.10L. Remaining ₹13.9L sits in Liquid ETF / TREPS yielding 6.5%. Zero settlement mismatch; exact 1:1 delta netting. However, requires modeling futures calendar roll drag (~0.35% to 0.50% p.a.).
3. **Path C (Fractional Rejection):** Strictly reject fractional ETF sizing against 1-lot options.

---

## 5. Market-Data Feed Evaluation for 15:15 IST Observation

To observe contemporaneous top-of-book bid/ask quotes without broker order routing:

| Feed Source | Contemporaneous 15:15 IST Bid/Ask Quotes | Reliability & Integrity Rating | Technical Assessment |
| :--- | :--- | :--- | :--- |
| **OpenAlgo REST API `/api/v1/quote`** | **YES (Full Top-of-Book)** | ⭐⭐⭐⭐⭐ (Institutional Standard) | Provides normalized JSON: `bid`, `ask`, `ltp`, `oi`, `volume`, `timestamp`. Requires active read-only broker session. |
| **Broker WebSocket Feed (Kite / Upstox / Shoonya)** | **YES (Streaming Ticks)** | ⭐⭐⭐⭐⭐ (Sub-millisecond) | High-speed tick stream. Best for continuous monitoring of 3x stop loss and 80% target triggers. |
| **Bhavcopy / Parquet EOD (`DuckDB`)** | **NO (EOD Settle Price Only)** | ⭐⭐ (Unsuitable for Live Paper) | Only records closing/settle prices. Lacks bid/ask spreads at 15:15 IST; induces fill lookahead. |
| **Public NSE Website Scraping** | **POOR / UNRELIABLE** | ⭐ (Prohibited) | Prone to Cloudflare IP blocks, 5-minute delayed quotes, and format breaking. |

*Feed Recommendation:* The paper-observation engine should utilize a read-only snapshot adapter pulling from **OpenAlgo's normalized `/api/v1/quote` endpoint** or a broker's read-only market quote API at 15:15 IST. Zero trading permissions are required.

---

## 6. Minimum Technical Test Suite Specification

Before forward paper observation can be certified, the following four automated unit/integration tests must pass:

```text
========================================================================================================
                               MINIMUM TECHNICAL TEST SPECIFICATION
========================================================================================================
 Test Suite ID     Target Component       Test Assertion & Acceptance Criteria
--------------------------------------------------------------------------------------------------------
 `TEST_FEED_001`   Market Data Feed       Assert quote freshness $\le 3.0$ seconds at 15:15 IST.
                                          Assert non-empty `bid`, `ask`, `ltp`, and `oi \ge 10,000`.
 `TEST_SIZE_002`   Position & Hedge Parity Assert underlying delta strictly equals option lot size
                                          ($\Delta_{\text{underlying}} \equiv L_t = 65$).
                                          Reject any configuration where hedge ratio $< 1.0$.
 `TEST_FILL_003`   Execution Slippage     Assert Sell fill = $\text{Bid} - \max(P \times 0.01, 0.50)$.
                                          Assert Buy fill = $\text{Ask} + \max(P \times 0.01, 0.50)$.
                                          Assert statutory taxes match official NSE rate schedule.
 `TEST_NAV_004`    Append-Only Logging    Assert daily ledger is idempotent (no duplicate rows on replay).
                                          Assert mathematical identity:
                                          $\text{NAV}_t - \text{NAV}_0 = \sum \text{Realized} + \text{Unrealized} + \text{Interest}$.
========================================================================================================
```

---

## 7. Updated Readiness Checklist & Audit Scores

```text
========================================================================================================
                         UPDATED PAPER-OBSERVATION READINESS SCORECARD
========================================================================================================
 Dimension                         Audit Finding   Evaluation Summary
--------------------------------------------------------------------------------------------------------
 1. Strategy Parameter Spec        PASS            Short delta 0.25, Target 80%, SL 3.0x, Roll 7 TS verified.
 2. Baseline Benchmark Anchor      PASS            Frozen baseline anchored at ₹10,13,946 net PnL.
 3. Statutory Cost & Tax Model     PASS            NSE rates (STT 0.10%, Brokerage ₹20, GST 18%) verified.
 4. Holiday Roll Logic             PASS            Holiday-aware trading session counter verified.
 5. PnL & Daily NAV Engine         PASS            Zero discrepancy (₹0.000000) verified between ledger and NAV.
--------------------------------------------------------------------------------------------------------
 6. Hedge Parity & Sizing Integrity FAIL           Fractional ETF sizing creates under-covered ratio write
                                                   with unlimited upside risk. Must be redesigned.
 7. Contemporaneous Data Feed      INCONCLUSIVE    OpenAlgo `/api/v1/quote` identified, but adapter not wired.
 8. Automated Logging Daemon       INCONCLUSIVE    Post-market daemon architecture defined, awaiting approval.
 9. Non-Linear Crash Stress Model  INCONCLUSIVE    Linear delta approximation used; gamma/vega unmodeled.
 10. Explicit User Approval        INCONCLUSIVE    Governance hard stop respected; awaiting formal sign-off.
========================================================================================================
```

---

## 8. Governance Certification & Recommendations

1. **Retract Fractional ETF Sizing:** Do not proceed with fractional ETF sizing. Choose either:
   - **Alternative 1:** Increase reference capital to ₹18,00,000 to fully cover 1 lot of `NIFTYBEES` ($65 \times S$) + cash buffer.
   - **Alternative 2:** Execute a unified Futures Buy-Write (`Long 1 NIFTY Future + Short 1 NIFTY Call`) within ₹15,00,000 capital, deploying ~₹1.1L in SPAN margin and sweeping ~₹13.9L into liquid yield.
2. **Hard Stop Enforced:** Zero background processes, broker connections, orders, or production file modifications have been made.
3. **Awaiting User Review:** Await explicit user decision on the underlying instrument architecture before initiating forward observation.
