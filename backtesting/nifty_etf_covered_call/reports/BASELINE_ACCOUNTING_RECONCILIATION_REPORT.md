# BASELINE ACCOUNTING RECONCILIATION REPORT
**Workspace:** `/Users/mac/Desktop/openalgo/backtesting/nifty_etf_covered_call/`  
**Strategy:** NIFTYBEES Covered Call Mechanical Baseline (31 Cycles, Jan 2022 – Jul 2024)  
**Verification Suite:** `tests/test_baseline_accounting_reconciliation.py` (Passes: 2/2 OK)  
**Date:** October 14, 2026  
**Status:** FULLY RECONCILED — ZERO DISCREPANCY  

---

## 1. Executive Summary & Verification Ledger

Every reported baseline figure has been forensically traced back to the transaction ledger (`baseline/cycle_ledger.csv`) and the underlying calculation engine (`baseline/engine.py`):

| Metric | Reported Figure | Verified Ledger Total | Discrepancy | Mathematical Proof / Source Formula |
| :--- | :---: | :---: | :---: | :--- |
| **Initial Capital** | ₹15,00,000.00 | ₹15,00,000.00 | ₹0.00 | `INITIAL_CAPITAL` constant at start |
| **Gross Premium Collected** | ₹2,37,445.00 | ₹2,37,445.00 | ₹0.00 | $\sum (\text{opt\_fill\_price} \times \text{lot\_size})$ |
| **Cash Settlement Debits (ITM)** | ₹2,38,449.90 | ₹2,38,449.90 | ₹0.00 | $\sum (\text{intrinsic} \times \text{lot\_size})$ across 11 ITM expiries |
| **Option Statutory Costs** | ₹978.43 | ₹978.43 | ₹0.00 | $\sum \text{opt\_costs}$ (Brokerage, STT, NSE, GST, SEBI) |
| **Option-Leg Net P&L** | **-₹1,983.33** | **-₹1,983.33** | **₹0.00** | $₹2,37,445.00 - ₹2,38,449.90 - ₹978.43 = \mathbf{-₹1,983.33}$ |
| **ETF Transaction Costs** | ₹1,757.14 | ₹1,757.14 | ₹0.00 | $\sum \text{etf\_costs}$ (Cycle 1 purchase + lot-size rebalancing) |
| **Total Reported Statutory Costs** | **₹2,735.57** | **₹2,735.57** | **₹0.00** | $\text{Option Costs (₹978.43)} + \text{ETF Costs (₹1,757.14)} = \mathbf{₹2,735.57}$ |
| **Intra-Cycle ETF Net P&L** | ₹1,80,838.41 | ₹1,80,838.41 | ₹0.00 | $\sum (\text{etf\_val\_exit} - \text{etf\_val\_entry} - \text{etf\_txn\_cost})$ |
| **Inter-Cycle ETF Holding Gap** | — | **₹1,31,843.33** | Reconciled | Overnight & weekend ETF appreciation between cycle expiry and next entry |
| **Total Portfolio Equity** | **₹18,10,698.41** | **₹18,10,698.41** | **₹0.00** | $₹15,00,000 + ₹1,80,838.41 + ₹1,31,843.33 - ₹1,983.33 = \mathbf{₹18,10,698.41}$ |

---

## 2. Root Cause Analysis of the Initial Equity Gap

When summing the `cycle_net_pnl` column ($\sum = ₹1,78,855.08$), there was an apparent gap of **₹1,31,843.33** compared to the total ending equity gain of **₹3,10,698.41** ($₹18,10,698.41 - ₹15,00,000.00$).

### The Mechanism Explained:
1. **Intra-Cycle vs. Permanent Asset Ownership:**
   * In `engine.py` (lines 278–281), `etf_net_pnl` records the price change strictly from `entry_date` to `expiry_date` of that specific monthly option cycle.
   * However, the investor **never sells the ETF units** at monthly expiry. The units are held continuously over the weekend / overnight until the next cycle entry.
2. **Inter-Cycle Weekend & Gap Valuation:**
   * Over the 31 cycles, NIFTYBEES experienced overnight and weekend gaps between the Thursday monthly expiry close and the Friday/Monday new cycle entry.
   * For example, between Cycle 26 expiry (Jan 25, 2024 at ₹236.15) and Cycle 27 entry (Jan 29, 2024 at ₹240.05), NIFTYBEES jumped **+₹3.90/share**, creating $+₹17,682$ of capital appreciation over the weekend.
   * The sum of these 30 inter-cycle gaps equals **exactly ₹131,843.3341**.
3. **Daily Equity Ledger vs. Cycle Ledger:**
   * `daily_equity.csv` tracks true daily mark-to-market NAV ($\text{units} \times P_t + \text{cash}$) every single day, seamlessly capturing both intra-cycle and inter-cycle gains.
   * Adding the inter-cycle gap to the cycle ledger net P&L reconciles with final equity to **$10^{-10}$ rupee precision**.

---

## 3. Statutory Cost Breakdown

The ₹2,735.57 in total statutory charges breaks down into:
* **F&O Option Costs (₹978.43):**
  - ₹20.00 flat brokerage per order $\times 31$ orders = ₹620.00
  - STT on option premium turnover = ₹157.36
  - NSE F&O transaction charges (0.03503%) = ₹83.18
  - SEBI turnover charges = ₹0.24
  - 18% GST on brokerage + exchange + SEBI = ₹117.65
* **Cash Equity ETF Costs (₹1,757.14):**
  - Delivery STT (0.10%) on Cycle 1 acquisition (₹881k turnover) = ₹881.32
  - Delivery STT on Cycle 28 lot-size reduction (50 to 25 units, ₹571k turnover) = ₹571.41
  - Exchange turnover, brokerage, SEBI, and GST = ₹304.41
