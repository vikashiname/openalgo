# PERSONAL EXPOSURE & RISK AUDIT (CORRECTED)
**Target Holding:** 550 Units NIFTYBEES ETF  
**Cost Basis:** ₹1,37,500.00 (₹250.00 average purchase price)  
**Contemporaneous Market Value:** ₹1,51,250.00 (at current market price ~₹275.00)  
**Broker:** Fyers Securities  
**Workspace:** `/Users/mac/Desktop/openalgo/backtesting/nifty_etf_covered_call/`  
**Ledger Artifact:** `data/personal_ledger_550_spread.csv`  
**Execution Script:** `scripts/audit_personal_exposure_550.py`  
**Date:** October 14, 2026  
**Status:** AUDITED WITH OFFICIAL NSE & FYERS CONSTRAINTS  

---

## 1. Contract Lot-Size Mapping & NSE Circular NSE/FAOP/70616

Pursuant to **NSE Circular NSE/FAOP/70616** dated October 3, 2025:
* **Current Active Lot Size (2026):** The market lot size for NIFTY 50 (`NIFTY`) was revised **from 75 to 65**, effective from the **January 2026 expiry cycle onwards** (including the January 27, 2026 monthly expiry).
* **Historical Schedule Applied in Audit:**
  * **Cycles 1 to 28 (Jan 2022 – Apr 2024):** Lot size = **50**.
  * **Cycles 29 to 31 (May 2024 – Jul 2024):** Lot size = **25**.
  * **Current 2026 Trading:** Lot size = **65** (not 75).

---

## 2. Contemporaneous Exposure & Hedge Mismatch (550 Units)

Using current market prices (NIFTY ~25,000, NIFTYBEES ~₹275.00):
* **Your Portfolio Value:** $550 \times ₹275.00 = \mathbf{₹1,51,250.00}$.
* **1 NIFTY Option Contract Notional (Lot Size 65):** $25,000 \times 65 = \mathbf{₹16,25,000.00}$.
* **NIFTYBEES Units Required for 100% Cover:** $\frac{₹16,25,000}{₹275.00} \approx \mathbf{5,909\ \text{units}}$.
* **Your Current Coverage Ratio:** $\frac{550}{5,909} = \mathbf{9.31\%}$.
* **Uncovered Naked Exposure:** $\mathbf{90.69\% \text{ NAKED SHORT CALL}}$.

---

## 3. Current Market Stress Testing (Lot Size 65, NIFTY @ 25,000)

If 1 lot of NIFTY Call (Lot 65) is written against your 550 NIFTYBEES units today:

| Monthly Market Move | Spot Level | 550 ETF Value Change | Short Call Gross P&L (₹) | **Combined Portfolio Net P&L (₹)** | **% of Cost Basis (₹1.37L)** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **-5.0% Crash** | 23,750 | -₹7,562.50 | +₹2,600.00 (100% decay) | **-₹4,962.50** | -3.6% |
| **Flat (0.0%)** | 25,000 | ₹0.00 | +₹2,600.00 (100% decay) | <span style="color:green">**+₹2,600.00**</span> | +1.9% |
| **+2.0% Mild Up** | 25,500 | +₹3,025.00 | +₹2,600.00 (At the money) | <span style="color:green">**+₹5,625.00**</span> | +4.1% |
| **+4.0% Strong Rally** | 26,000 | +₹6,050.00 | -₹29,900.00 (500 pts ITM) | <span style="color:red">**-₹23,850.00**</span> | **-17.3% (Severe Hit)** |
| **+6.0% Bull Surge** | 26,500 | +₹9,075.00 | -₹62,400.00 (1,000 pts ITM) | <span style="color:red">**-₹53,325.00**</span> | **-38.8% (Catastrophic)** |
| **+10.0% Historic Rally**| 27,500 | +₹15,125.00 | -₹1,27,400.00 (2,000 pts ITM)| <span style="color:red">**-₹1,12,275.00**</span> | **-81.7% (Account Wipeout)**|

### Historical December 2023 Adverse Trade Check:
* During December 2023, the historical lot size was **50**.
* NIFTY surged from 20,133 to 21,778 (+1,645 points).
* 550 NIFTYBEES units gained: $+₹9,025.50$.
* The Short Call (20,550 CE) suffered an ITM cash settlement loss of: $-₹51,278.95$.
* **Net Monthly Loss:** **-₹42,253.45** (**-30.7% of total capital lost in 28 days**).

---

## 4. Fyers Margin & Capital Requirements (Official Verification)

1. **Pledge Eligibility:** `NIFTYBEES-EQ` is officially eligible for pledge on Fyers.
2. **Haircut:** **8.00%** (Margin Allowed: **92.00%**).
3. **Category:** **Non-Cash Component**.
4. **Available Non-Cash Collateral:** $550 \times ₹275.00 \times 0.92 = \mathbf{₹1,39,150.00}$ (or ₹1,26,500 based on ₹250 cost basis).
5. **Mandatory SEBI 50:50 Cash-to-Collateral Rule:**
   * At least **50% of the total margin** required for overnight F&O positions must come from **Cash or Cash-Equivalent** instruments (e.g. liquid funds, cash in ledger).
   * **Credit spreads CANNOT be financed 100% by pledged NIFTYBEES without cash.**
   * For 1 lot Call Credit Spread (Margin ~₹22,000 at Lot 65):
     - **Minimum Liquid Cash Required:** $\approx \mathbf{₹11,000.00}$.
     - Non-Cash Collateral used: $\approx ₹11,000.00$.
   * For 1 lot Naked Short Call (Margin ~₹1,15,000 at Lot 65):
     - **Minimum Liquid Cash Required:** $\approx \mathbf{₹57,500.00}$.
     - Non-Cash Collateral used: $\approx ₹57,500.00$.
6. **Cash Shortfall Penalty:** Fyers charges delayed payment interest of **15% per annum** (debited daily on the cash deficit).
7. **Execution Charges:**
   * Fyers Brokerage: ₹0 for Equity Delivery; ₹20 flat per executed F&O order.
   * Pledge / Unpledge Fee: **₹5.00 + GST** per pledge request.

---

## 5. Independent Validation of the Call Credit Spread

### Forensic Reconciliation of the Previous +₹72,513.36 Figure:
* The earlier reported `+₹72,513.36` was an **unvalidated preliminary estimate** based on a theoretical assumption that the protective wing cost 30% of the short call.
* When evaluated using **100% actual traded prices from official NSE F&O Bhavcopies** across all 31 cycles:

| Strategy on 550 Units | Options Leg Net P&L (₹) | Intra-Cycle ETF P&L (₹) | Total Realized Net Gain (₹) | Comparison vs. Benchmark |
| :--- | :---: | :---: | :---: | :--- |
| **Benchmark: Pure Buy & Hold (No Options)** | **₹0.00** | **+₹28,385.50** | **+₹44,660.01** | **BASE BENCHMARK** |
| **Overlay: 1 Lot Call Credit Spread (Bhavcopy)** | **-₹24,998.63** | **+₹28,385.50** | **+₹3,386.87** | <span style="color:red">**-₹41,273.14 (UNDERPERFORMED)**</span> |
| **Overlay: 1 Lot Naked Call (Bhavcopy)** | **-₹1,983.33** | **+₹28,385.50** | **+₹26,402.17** | <span style="color:red">**-₹18,257.84 (UNDERPERFORMED)**</span> |

*(Note: Intra-cycle ETF gain is ₹28,385.50; full holding gain from start to finish is ₹44,660.01 including inter-cycle gaps).*

### Root Cause of Spread Underperformance:
1. **Wing Premium Drag:** In a continuous bull market, buying a protective wing (Strike + 300) costs real cash premium every single month that mostly expires at ₹0. Over 31 months, that debit drag accumulated to **-₹24,998.63** in net option losses.
2. **Fixed Mechanical Flaw:** Selling calls blindly every month without market trend, momentum, or valuation filters forces payouts whenever the index trends upward.

---

## 6. Strategic Verdict & Next Steps

1. **Is Writing Index Options on 550 Units Worth It?**
   * **NO.** At 550 units, the position cannot mathematically support an index options overlay.
   * Selling naked calls exposes you to **-80%+ wipeout risk** in rallies.
   * Buying credit spreads creates **heavy premium drag that underperformed simple buy-and-hold by ₹41,000**.
2. **Recommended Action:**
   * **Preserve your 550 NIFTYBEES units as a pure long-term investment.**
   * Do not write index options against this holding until unit accumulation (via SIP) reaches ~5,900 units (~1 full contract lot).
