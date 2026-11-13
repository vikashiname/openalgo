# FINAL CONTINUOUS-HOLDING RECONCILIATION & EXPOSURE REPORT
**Workspace:** `/Users/mac/Desktop/openalgo/backtesting/nifty_etf_covered_call/`  
**Holding:** 550 Units NIFTYBEES ETF (Continuous Holding — Never Sold)  
**Confirmed Cost Basis:** ₹1,37,500.00 (₹250.00 / unit purchase price)  
**Initial Market Value (2022-01-03):** ₹1,04,896.00 (₹190.72 / unit)  
**Final Market Value (2024-07-25):** ₹1,49,556.01 (₹271.92 / unit)  
**Historical Horizon:** 31 Monthly Cycles (2.56 Years, 631 Trading Days)  
**Independent Test Suite:** `tests/test_continuous_holding_reconciliation.py` (Passes: 2/2 OK)  
**Date:** October 14, 2026  
**Status:** RECONCILED UNDER TRUE CONTINUOUS HOLDING  

---

## 1. Executive Continuous-Holding Performance Reconciliation

Under your verified objective—**holding 550 NIFTYBEES units continuously without inter-cycle selling**—the full capital appreciation of the ETF is retained across all strategies. 

Options overlays either add to or subtract from this exact baseline:

| Metric | Benchmark: Pure Buy & Hold (550 Units) | Overlay 1: Continuous 550 + 1 Lot Call (Naked) | Overlay 2: Continuous 550 + Call Credit Spread | Accounting Status |
| :--- | :---: | :---: | :---: | :--- |
| **Initial Market Value (2022-01-03)** | ₹1,04,896.00 | ₹1,04,896.00 | ₹1,04,896.00 | Exact Day 1 Market Price (₹190.72) |
| **Confirmed Cost Basis (₹250/u)** | ₹1,37,500.00 | ₹1,37,500.00 | ₹1,37,500.00 | Actual Investor Capital Basis |
| **Full-Period Continuous ETF Gain** | **+₹44,660.01** | **+₹44,660.01** | **+₹44,660.01** | Identical continuous ETF asset base |
| *— Intra-Cycle ETF Gain (during trades)*| *₹28,385.50* | *₹28,385.50* | *₹28,385.50* | Sum of trade-period price changes |
| *— Inter-Cycle Holding Gap (weekends/gaps)*| *₹16,274.51* | *₹16,274.51* | *₹16,274.51* | Overnight/weekend appreciation |
| **Options Leg Net P&L (after all costs)** | **₹0.00** | **-₹1,983.33** | **-₹24,998.63** | Real traded Bhavcopy fills & fees |
| **Final Reconciled Portfolio Equity** | **₹1,49,556.01** | **₹1,47,572.67** | **₹1,24,557.37** | $\text{Init Mkt} + \text{ETF Gain} + \text{Opt P&L}$ |
| **Net Portfolio Profit (vs Market Init)** | **+₹44,660.01** | **+₹42,676.67** | **+₹19,661.37** | Net Rupee Growth from Day 1 |
| **Net Portfolio Profit (vs ₹1.375L Cost)** | **+₹12,056.01** | **+₹10,072.67** | <span style="color:red">**-₹12,942.63**</span> | Net Rupee Profit on Investor Basis |
| **Market Total Return (%)** | **+42.58%** | **+40.68%** | **+18.74%** | Total percentage return |
| **Market Annualized CAGR (%)** | **14.88%** | **14.28%** | **6.95%** | Compounded annual return on market |
| **Cost-Basis Annualized CAGR (%)** | **3.34%** | **2.80%** | <span style="color:red">**-3.79%**</span> | Compounded annual return on cost basis |
| **Alpha / Underperformance vs B&H (₹)** | **₹0.00 (Base)** | <span style="color:red">**-₹1,983.33**</span> | <span style="color:red">**-₹24,998.63**</span> | Exact drag caused by options overlays |
| **Maximum Drawdown (Daily / NAV)** | **-15.73%** | <span style="color:red">**-38.71%**</span> | **-19.71%** | Peak-to-trough capital decline |
| **Worst Single Month Return (%)** | **-5.32%** | <span style="color:red">**-34.33%**</span> | **-10.82%** | Worst monthly performance (Dec 2023) |
| **Best Single Month Return (%)** | **+7.33%** | **+10.71%** | **+5.82%** | Best monthly performance |

---

## 2. Market Data Timestamps: Contemporaneous vs. Hypothetical

To guarantee absolute transparency between historical dataset records and forward stress projections:

### A. Contemporaneous Validated Historical Data Point:
* **Source:** `data/nifty_historify.parquet` & `data/niftybees_historify.parquet` (DuckDB validated store).
* **Latest Dataset Timestamp:** **2026-09-04 00:00:00 IST** (September 4, 2026).
* **Contemporaneous Spot Close:** **23,897.70** (`NIFTY:NSE`).
* **Contemporaneous ETF Close:** **₹273.27** (`NIFTYBEES:NSE`).
* **Empirical Tracking Ratio:** $S_t / P_t = \frac{23,897.70}{273.27} = \mathbf{87.45}$.
* **Current Portfolio Valuation on 550 Units:** $550 \times ₹273.27 = \mathbf{₹1,50,298.50}$ (+₹12,798.50 profit over ₹1.375L cost basis).

### B. Hypothetical Round-Number Stress Baseline:
* The values **NIFTY @ 25,000** and **NIFTYBEES @ ₹275.00** are **strictly hypothetical round-number assumptions** designed for scenario stress-testing. They are not historical timestamps.

---

## 3. Notional Exposure vs. Delta-Equivalent Hedge Exposure

> [!IMPORTANT]
> **Key Quantitative Distinction:** 550 NIFTYBEES units do NOT provide a flat 9.31% of option-risk protection across all market states. The actual hedge protection is dynamic, non-linear, and governed by option Greeks ($\Delta$, $\Gamma$, $\nu$).

### A. Static Notional Exposure
* At current lot size **65** and NIFTY @ 23,898:
  * Contract Notional = $23,898 \times 65 = \mathbf{₹15,53,370.00}$.
  * 550 NIFTYBEES Units Value = $550 \times ₹273.27 = \mathbf{₹1,50,298.50}$.
  * **Static Notional Ratio:** $\frac{₹1,50,298.50}{₹15,53,370.00} = \mathbf{9.68\%}$ (or 9.31% at ratio 91.24).
  * This ratio only represents the terminal coverage if the option finishes deep in-the-money ($\Delta = 1.0$).

### B. Dynamic Delta-Equivalent Hedge Exposure ($\Delta$)
* At trade initiation (~28 DTE, ~2.0% OTM):
  * Short Call Delta is approximately $\Delta \approx \mathbf{0.22}$.
  * Total short index delta for 1 lot = $65 \times 0.22 = \mathbf{14.30\ \text{Index Delta Units}}$.
  * 550 NIFTYBEES represents: $\frac{550}{87.45} = \mathbf{+6.29\ \text{Index Delta Units}}$.
  * **Initial Delta Coverage Ratio:** $\frac{+6.29}{14.30} = \mathbf{44.0\%}$!
  * **Empirical Insight:** At entry, 550 units actually hedges **44% of immediate small price fluctuations**.

### C. The Non-Linear Gamma ($\Gamma$) Trap
As NIFTY rallies towards the strike, positive Gamma rapidly increases short call delta:
* **At Strike (ATM, $\Delta \approx 0.50$):** Short delta grows to $65 \times 0.50 = 32.50$ delta $\implies$ **Coverage drops to 19.4%**.
* **Above Strike (ITM, $\Delta \approx 0.85$):** Short delta grows to $65 \times 0.85 = 55.25$ delta $\implies$ **Coverage drops to 11.4%**.
* **Deep ITM ($\Delta \to 1.00$):** Short delta equals $65.00$ delta $\implies$ **Coverage reaches the absolute floor of 9.68%**.

### D. Vega ($\nu$) & Volatility Shock Exposure
* A sudden volatility spike (e.g., India VIX jumping from 13 to 20):
  * Inflates the short call option premium via positive Vega ($\nu \approx 14.5$ points per 1% IV change $\times 65 \approx ₹942$ loss per volatility point).
  * The physical ETF receives **zero offset from IV expansion**, causing immediate mark-to-market drawdown on volatility spikes even before any index breakout.

---

## 4. Date-Aware Historical Contract Lot Sizes

The audit strictly applies exchange lot sizes based on contract initiation date:
* **Cycles 1–28 (Jan 2022 to Apr 2024):** Lot size **50**.
* **Cycles 29–31 (May 2024 to Jul 2024):** Lot size **25**.
* **Current Active Contracts (Post-Jan 2026, Circular NSE/FAOP/70616):** Lot size **65**.

---

## 5. Fyers Margin & SEBI 50:50 Cash Requirements

From official FYERS schedules:
* **Haircut:** 8.00% (Margin benefit: 92.00%).
* **Category:** Non-Cash Collateral.
* **Non-Cash Collateral from 550 Units:** $550 \times ₹273.27 \times 0.92 = \mathbf{₹1,38,274.62}$.
* **The 50:50 Cash Rule:**
  * For 1 lot Call Credit Spread (Margin ~₹22,000 at Lot 65): Requires at least **₹11,000 in liquid cash** + ₹11,000 collateral.
  * For 1 lot Naked Call (Margin ~₹1,15,000 at Lot 65): Requires at least **₹57,500 in liquid cash** + ₹57,500 collateral.
* **Penalty:** Unmaintained cash deficits incur delayed payment interest of **15% per annum** charged daily by FYERS.

---

## 6. Strategic Verdict on 550 Units

1. **Overlay 1 (1 Lot Naked Call):**
   * Delivers near-identical nominal return to Buy & Hold (₹42.6k vs ₹44.6k) but **more than doubles maximum drawdown from -15.7% to -38.7%**, with a catastrophic -34.3% monthly loss in December 2023.
2. **Overlay 2 (1 Lot Call Credit Spread):**
   * Caps maximum loss per cycle, but the continuous debit drag of buying protective wings in a bull market **destroys over ₹25,000 in return** (+₹19.6k total gain vs +₹44.6k for Buy & Hold).
3. **Institutional Recommendation:**
   * **Do not execute options overlays on 550 NIFTYBEES units.**
   * The pure, unleveraged **Buy & Hold** of your 550 NIFTYBEES units delivered the highest CAGR (14.88%), lowest drawdown (-15.73%), and zero cash/margin drag.
   * Options overwriting should only be revisited when unit holdings accumulate to **~5,900 units** (~1 full contract lot).
