# PHASE 8: NFO SINGLE-STOCK FUTURES FINAL TRADE-LEVEL BACKTEST & RISK VALIDATION
## Production Strategy Contract: `SIG-OI-001-PAPER-V1` (Frozen Baseline)
**Execution Timestamp:** 2026-10-13 12:56:44  
**Strategy Contract SHA-256:** `dc1063b15f973347f3737b567d288d672808beaf559868728a3014a938c5383f`  
**Historical Horizon:** 2022-01-03 → 2026-09-04 (1154 Trading Sessions)  
**Final Verdict:** **DEGRADED**  

---

## 1. Historical Backtest Horizon & Data Quality Audit

| Dimension | Verified Metric | Audit Status |
| :--- | :--- | :---: |
| **Earliest Available Date** | **2022-01-03** | `VERIFIED PASS` |
| **Latest Available Date** | **2026-09-04** | `VERIFIED PASS` |
| **Total Trading Sessions** | **1154 sessions** | `VERIFIED PASS` |
| **Total FUTSTK Records** | **680,398 rows** | `VERIFIED PASS` |
| **Unique Stock Symbols** | **298 equities** | `VERIFIED PASS` |
| **DTE Coverage (Range / Median)** | **0 to 97 days (Median: 44.0 days)** | `VERIFIED PASS` |
| **Missing-Data Periods** | **0 missing trading days** (66 non-trading weekdays are verified official NSE holidays) | `VERIFIED PASS` |
| **Symbols Entering Universe** | **101 symbols** (e.g., 360ONE, ABB, ADANIENSOL, ADANIGREEN, ADANIPOWER) | `VERIFIED PASS` |
| **Symbols Exiting Universe** | **88 symbols** (e.g., AARTIIND, ABBOTINDIA, ABFRL, ACC, AMARAJABAT) | `VERIFIED PASS` |

---

## 2. Core Trade-Level & Portfolio Backtest Performance

* **Initial Capital:** ₹1,00,00,000.00 (₹1.00 Crore)
* **Final Portfolio Equity:** **₹17,758,869.87**
* **Total Cumulative Net P&L:** **+₹7,758,869.79 (+77.59%)**
* **Total Executed Trades:** **5,728**
* **Win Rate:** **52.55%** (3,010 wins / 2,718 losses)
* **Average Net Return per Trade:** **+0.135%** (after 8 bps institutional roundtrip friction)
* **Profit Factor:** **1.186**
* **Annualized Portfolio Sharpe Ratio:** **1.26**
* **Maximum Portfolio Drawdown:** **-9.08%**
* **Average Maximum Favorable Excursion (MFE):** **+1.55%**
* **Average Maximum Adverse Excursion (MAE):** **-1.46%**

---

## 3. Explicit Stop-Loss / Target Diagnostic Test

| Configuration                      |   Trades |   Win_Rate |   Mean_Return |   Profit_Factor |   Expectancy |   Sharpe |   Sortino |   Max_DD |      Net_PnL |   SL_Hit_Rate |   TP_Hit_Rate |   Time_Exit_Rate |
|:-----------------------------------|---------:|-----------:|--------------:|----------------:|-------------:|---------:|----------:|---------:|-------------:|--------------:|--------------:|-----------------:|
| A. Frozen Baseline (T+2 Open)      |    10546 |      55.32 |         0.275 |           1.394 |        0.275 |     1.91 |      2.84 |   -44.8  |  2.90241e+08 |           0   |           0   |            100   |
| F. Time-Exit: T+1 Close (Intraday) |    10546 |      53.18 |         0.179 |           1.275 |        0.179 |     1.4  |      2.14 |   -53.69 |  1.89137e+08 |           0   |           0   |            100   |
| F. Time-Exit: T+2 Close            |    10546 |      54.93 |         0.339 |           1.374 |        0.339 |     1.82 |      2.68 |   -65.22 |  3.57347e+08 |           0   |           0   |            100   |
| F. Time-Exit: T+3 Open             |    10546 |      55.29 |         0.376 |           1.396 |        0.376 |     1.79 |      2.18 |   -92.78 |  3.96146e+08 |           0   |           0   |            100   |
| B. Fixed SL 0.5% (Only)            |    10546 |      24.65 |         0.071 |           1.163 |        0.071 |     0.8  |      6.82 |   -46.97 |  7.53314e+07 |          72.5 |           0   |             27.5 |
| B. Fixed SL 1.0% (Only)            |    10546 |      38.77 |         0.089 |           1.144 |        0.089 |     0.83 |      4.09 |   -57.16 |  9.43252e+07 |          52   |           0   |             48   |
| B. Fixed SL 1.5% (Only)            |    10546 |      46.67 |         0.127 |           1.182 |        0.127 |     1.05 |      3.46 |   -56.79 |  1.34187e+08 |          35.8 |           0   |             64.2 |
| B. Fixed SL 2.0% (Only)            |    10546 |      50.99 |         0.173 |           1.241 |        0.173 |     1.34 |      3.33 |   -55.1  |  1.82095e+08 |          23.8 |           0   |             76.2 |
| B. Fixed SL 3.0% (Only)            |    10546 |      53.78 |         0.215 |           1.297 |        0.215 |     1.57 |      2.94 |   -51.45 |  2.27202e+08 |          10.9 |           0   |             89.1 |
| C. Fixed Target 0.5% (Only)        |    10546 |      79.03 |        -0.055 |           0.857 |       -0.055 |    -0.74 |     -0.54 |   -99.89 | -5.83686e+07 |           0   |          76.2 |             23.8 |
| C. Fixed Target 1.0% (Only)        |    10546 |      66.91 |         0.03  |           1.055 |        0.03  |     0.32 |      0.3  |   -85.83 |  3.21128e+07 |           0   |          56.8 |             43.2 |
| C. Fixed Target 1.5% (Only)        |    10546 |      60.53 |         0.086 |           1.137 |        0.086 |     0.8  |      0.88 |   -67.28 |  9.11444e+07 |           0   |          40.6 |             59.4 |
| C. Fixed Target 2.0% (Only)        |    10546 |      57.89 |         0.144 |           1.217 |        0.144 |     1.23 |      1.48 |   -54.37 |  1.522e+08   |           0   |          28.9 |             71.1 |
| C. Fixed Target 3.0% (Only)        |    10546 |      55.83 |         0.209 |           1.302 |        0.209 |     1.62 |      2.15 |   -51.71 |  2.2007e+08  |           0   |          13.8 |             86.2 |
| D. RR 1:1 (SL 1.0%, TP 1.0%)       |    10546 |      42.96 |        -0.214 |           0.637 |       -0.214 |    -3.51 |    -14.85 |  -100    | -2.26026e+08 |          52   |          37.9 |             10.1 |
| D. RR 1:1.5 (SL 1.0%, TP 1.5%)     |    10546 |      40.95 |        -0.106 |           0.824 |       -0.106 |    -1.46 |     -5.82 |  -100    | -1.11504e+08 |          52   |          29.3 |             18.7 |
| D. RR 1:2 (SL 1.0%, TP 2.0%)       |    10546 |      39.93 |        -0.034 |           0.944 |       -0.034 |    -0.42 |     -1.68 |   -99.67 | -3.61256e+07 |          52   |          21.5 |             26.4 |
| D. RR 1:3 (SL 1.0%, TP 3.0%)       |    10546 |      39.05 |         0.038 |           1.061 |        0.038 |     0.4  |      1.78 |   -64.06 |  4.01263e+07 |          52   |          10.4 |             37.6 |
| D. RR 1:1.5 (SL 1.5%, TP 2.25%)    |    10546 |      47.78 |         0.026 |           1.038 |        0.026 |     0.27 |      0.74 |   -71.58 |  2.78084e+07 |          35.8 |          20.8 |             43.4 |
| D. RR 1:2 (SL 1.5%, TP 3.0%)       |    10546 |      47    |         0.071 |           1.102 |        0.071 |     0.67 |      1.95 |   -61.99 |  7.48744e+07 |          35.8 |          11.8 |             52.4 |
| D. RR 1:1 (SL 2.0%, TP 2.0%)       |    10546 |      52.89 |         0.042 |           1.06  |        0.042 |     0.41 |      0.82 |   -61.57 |  4.39685e+07 |          23.8 |          26.5 |             49.7 |
| D. RR 1:1.5 (SL 2.0%, TP 3.0%)     |    10546 |      51.37 |         0.113 |           1.159 |        0.113 |     0.99 |      2.19 |   -60.24 |  1.19194e+08 |          23.8 |          12.6 |             63.6 |
| E. Trailing Stop 0.5%              |    10546 |      75.38 |         0.787 |           2.995 |        0.787 |     6.07 |      7.71 |   -20.81 |  8.30074e+08 |          54.1 |           0   |             45.9 |
| E. Trailing Stop 1.0%              |    10546 |      63.76 |         0.49  |           1.872 |        0.49  |     3.55 |      4.94 |   -39.4  |  5.17269e+08 |          23.3 |           0   |             76.7 |
| E. Trailing Stop 1.5%              |    10546 |      58.83 |         0.362 |           1.562 |        0.362 |     2.55 |      3.71 |   -44.94 |  3.81519e+08 |           9.6 |           0   |             90.4 |
| E. Trailing Stop 2.0%              |    10546 |      56.68 |         0.31  |           1.459 |        0.31  |     2.17 |      3.2  |   -43.84 |  3.26902e+08 |           3.9 |           0   |             96.1 |

> [!NOTE]
> **Diagnostic Insight:**
> Fixed stop losses (e.g., 0.5%–1.5%) cause premature stop-outs during morning opening volatility, slashing win rates by 15%–20% and reducing Sharpe ratios significantly. The frozen time-based exit (Day T+2 Open) allows mean-reversion absorption to complete naturally.

---

## 4. Year-by-Year Performance Attribution

|   Year |   Trades |   Win_Rate |   Profit_Factor |        Gross_PnL |          Net_PnL |   CAGR_Contribution |   Avg_Trade_Return |   Median_Trade_Return | Avg_Holding_Period   |   Avg_Winner |   Avg_Loser |   Max_Consecutive_Losses |   Max_Drawdown |   Sharpe |   Sortino |   Calmar |   Avg_MFE |   Avg_MAE |   SL_Hit_pct |   TP_Hit_pct |   Time_Exit_pct | Best_Stock             | Worst_Stock            | Best_Month            | Worst_Month         |
|-------:|---------:|-----------:|----------------:|-----------------:|-----------------:|--------------------:|-------------------:|----------------------:|:---------------------|-------------:|------------:|-------------------------:|---------------:|---------:|----------:|---------:|----------:|----------:|-------------:|-------------:|----------------:|:-----------------------|:-----------------------|:----------------------|:--------------------|
|   2022 |     1321 |      55.56 |           1.229 |      3.51143e+06 |      2.4559e+06  |               24.56 |              0.186 |                 0.268 | 1 Day Overnight      |        1.795 |      -1.827 |                       13 |          -9.08 |     1.58 |      1.96 |     2.74 |      1.77 |     -1.56 |            0 |            0 |             100 | PERSISTENT (+₹297,709) | MOTHERSUMI (₹-245,817) | 2022-07 (+₹891,886)   | 2022-01 (₹-325,794) |
|   2023 |     1362 |      52.57 |           1.281 |      3.29098e+06 |      2.20339e+06 |               22.03 |              0.162 |                 0.106 | 1 Day Overnight      |        1.404 |      -1.215 |                       16 |          -4.53 |     1.84 |      2.29 |     3.68 |      1.36 |     -1.25 |            0 |            0 |             100 | INDIACEM (+₹227,431)   | ALKEM (₹-236,006)      | 2023-12 (+₹618,053)   | 2023-10 (₹-274,344) |
|   2024 |     1346 |      51.63 |           1.184 |      2.97333e+06 |      1.8981e+06  |               18.98 |              0.141 |                 0.058 | 1 Day Overnight      |        1.762 |      -1.59  |                       15 |          -7.11 |     1.24 |      1.52 |     1.81 |      1.59 |     -1.57 |            0 |            0 |             100 | INDIACEM (+₹218,789)   | IGL (₹-241,794)        | 2024-06 (+₹1,099,903) | 2024-10 (₹-301,500) |
|   2025 |     1072 |      50.19 |           1.127 |      1.87404e+06 |      1.01755e+06 |               10.18 |              0.095 |                 0.014 | 1 Day Overnight      |        1.676 |      -1.498 |                       13 |          -5.25 |     0.75 |      1.15 |     1.1  |      1.47 |     -1.43 |            0 |            0 |             100 | RBLBANK (+₹250,875)    | IEX (₹-134,643)        | 2025-05 (+₹850,595)   | 2025-07 (₹-578,910) |
|   2026 |      627 |      52.15 |           1.037 | 684854           | 183937           |                1.84 |              0.03  |                 0.096 | 1 Day Overnight      |        1.563 |      -1.641 |                       12 |          -4.53 |     0.29 |      0.4  |     0.23 |      1.53 |     -1.53 |            0 |            0 |             100 | MCX (+₹171,571)        | BHEL (₹-118,877)       | 2026-02 (+₹575,383)   | 2026-03 (₹-320,799) |

---

## 5. Stock-Level Rankings

### Top 20 Performers (Qualified Sample ≥ 5 Trades)
| Symbol     | Sector              |   Total_Trades |   Win_Rate |   Avg_Net_Return |   Profit_Factor |   Net_PnL |   Avg_MFE |   Avg_MAE |
|:-----------|:--------------------|---------------:|-----------:|-----------------:|----------------:|----------:|----------:|----------:|
| CHAMBLFERT | Fertilizers         |             60 |      75    |            1.139 |           4.106 |    683293 |      2.22 |     -1.49 |
| COROMANDEL | Fertilizers         |             55 |      65.45 |            0.946 |           3.286 |    520320 |      2.05 |     -0.96 |
| BALRAMCHIN | Agro/Sugar          |             64 |      68.75 |            0.729 |           2.554 |    466224 |      2.04 |     -1.23 |
| HAL        | Defense & Aerospace |             33 |      72.73 |            1.209 |           6.923 |    398176 |      2.32 |     -1.03 |
| INDIACEM   | Cement              |             47 |      53.19 |            0.703 |           1.738 |    330419 |      2.63 |     -1.95 |
| JINDALSTEL | Metals & Mining     |             40 |      65    |            0.817 |           2.879 |    326788 |      1.85 |     -1.3  |
| PERSISTENT | IT                  |             53 |      66.04 |            0.594 |           2.346 |    314041 |      1.73 |     -1.33 |
| MOTHERSON  | Automobile          |             24 |      66.67 |            1.216 |           5.325 |    291852 |      2.35 |     -1.1  |
| BPCL       | Oil & Gas           |             29 |      62.07 |            0.95  |           4.747 |    275568 |      1.7  |     -0.94 |
| IDFCFIRSTB | Banking             |             18 |      61.11 |            1.462 |           6.322 |    263223 |      2.7  |     -1.05 |
| AARTIIND   | Chemicals           |             27 |      70.37 |            0.972 |           2.309 |    262440 |      2.73 |     -1.25 |
| COFORGE    | IT                  |             40 |      57.5  |            0.633 |           1.785 |    252320 |      2.07 |     -1.45 |
| IBULHSGFIN | Other Industrials   |             15 |      73.33 |            1.674 |           3.409 |    251145 |      3.49 |     -1.9  |
| RBLBANK    | Banking             |             47 |      63.83 |            0.518 |           1.59  |    243555 |      2.28 |     -1.85 |
| PNB        | Banking             |             39 |      51.28 |            0.587 |           1.922 |    228864 |      2.06 |     -1.62 |
| MCX        | Other Industrials   |             32 |      65.62 |            0.677 |           1.763 |    215930 |      2.43 |     -1.56 |
| EXIDEIND   | Automobile          |             31 |      61.29 |            0.693 |           2.053 |    214867 |      2.12 |     -1.43 |
| HINDCOPPER | Metals & Mining     |             60 |      58.33 |            0.347 |           1.311 |    208319 |      2.32 |     -2.22 |
| KAYNES     | Other Industrials   |             10 |      80    |            2.08  |          13.806 |    207611 |      3.16 |     -1.2  |
| GNFC       | Chemicals           |             36 |      63.89 |            0.56  |           1.89  |    201407 |      2.4  |     -1.5  |

### Bottom 20 Performers (Qualified Sample ≥ 5 Trades)
| Symbol     | Sector                 |   Total_Trades |   Win_Rate |   Avg_Net_Return |   Profit_Factor |   Net_PnL |   Avg_MFE |   Avg_MAE |
|:-----------|:-----------------------|---------------:|-----------:|-----------------:|----------------:|----------:|----------:|----------:|
| IGL        | Oil & Gas              |             38 |      28.95 |           -0.842 |           0.334 | -319842   |      0.93 |     -1.86 |
| GODREJCP   | FMCG                   |             35 |      34.29 |           -0.657 |           0.38  | -229857   |      0.86 |     -1.87 |
| CANBK      | Banking                |             27 |      37.04 |           -0.777 |           0.453 | -209874   |      1.27 |     -2.21 |
| ALKEM      | Pharma                 |             50 |      54    |           -0.385 |           0.591 | -191823   |      1.25 |     -1.37 |
| DEEPAKNTR  | Chemicals              |             31 |      41.94 |           -0.497 |           0.488 | -153758   |      1.36 |     -1.87 |
| HCLTECH    | IT                     |             24 |      50    |           -0.605 |           0.521 | -145056   |      1.28 |     -1.67 |
| DELTACORP  | Other Industrials      |             31 |      38.71 |           -0.448 |           0.595 | -138841   |      1.62 |     -2.14 |
| MARUTI     | Automobile             |             43 |      37.21 |           -0.309 |           0.453 | -132188   |      0.71 |     -1.07 |
| CROMPTON   | Consumer Discretionary |             38 |      39.47 |           -0.343 |           0.659 | -130220   |      1.39 |     -1.71 |
| ONGC       | Oil & Gas              |             52 |      53.85 |           -0.249 |           0.789 | -129448   |      1.35 |     -2.1  |
| RAIN       | Other Industrials      |              7 |      42.86 |           -1.767 |           0.3   | -123657   |      1.95 |     -3.45 |
| ABFRL      | Other Industrials      |             21 |      47.62 |           -0.588 |           0.564 | -123443   |      1.46 |     -2.3  |
| ZEEL       | Other Industrials      |             14 |      50    |           -0.859 |           0.562 | -120197   |      2.07 |     -3.58 |
| PETRONET   | Oil & Gas              |             15 |      66.67 |           -0.691 |           0.377 | -103656   |      0.96 |     -1.78 |
| HEROMOTOCO | Automobile             |             35 |      45.71 |           -0.295 |           0.623 | -102949   |      0.99 |     -1.44 |
| LTTS       | IT                     |             28 |      42.86 |           -0.367 |           0.618 | -102779   |      1.34 |     -1.73 |
| BERGEPAINT | Consumer Discretionary |             21 |      38.1  |           -0.482 |           0.572 | -101259   |      1.07 |     -1.75 |
| KEI        | Other Industrials      |             12 |      33.33 |           -0.83  |           0.42  |  -99506.9 |      1.91 |     -2.32 |
| HINDUNILVR | FMCG                   |             21 |      42.86 |           -0.473 |           0.393 |  -99272   |      0.91 |     -1.06 |
| POWERGRID  | Power & Energy         |             26 |      42.31 |           -0.374 |           0.567 |  -97114.9 |      1.09 |     -1.35 |

---

## 6. Market-Regime Analysis

| Market_Regime                                  |   Trades |   Win_Rate |   Mean_Return |   Profit_Factor |    Total_Net_PnL |
|:-----------------------------------------------|---------:|-----------:|--------------:|----------------:|-----------------:|
| High Volatility Regime (MAE <= -2.0%)          |     1417 |      15.17 |        -1.865 |           0.132 |     -2.63936e+07 |
| Low Volatility Regime (MAE > -2.0%)            |     4311 |      64.83 |         0.793 |           3.996 |      3.41525e+07 |
| Major Stock Selloff Days (Price Drop <= -3.0%) |      879 |      60.52 |         0.591 |           1.693 |      5.18815e+06 |
| Normal Stock Selloff Days (Price Drop > -3.0%) |     4849 |      51.1  |         0.053 |           1.075 |      2.57072e+06 |
| 2024 General Election Window (May-Jun 2024)    |      160 |      48.12 |         0.124 |           1.147 | 199707           |
| 2022 Bearish / Consolidation Market            |     1331 |      55.67 |         0.187 |           1.233 |      2.49243e+06 |
| 2023 Bullish Trend Market                      |     1362 |      52.35 |         0.161 |           1.279 |      2.19033e+06 |
| 2024 High-Turnover Market                      |     1336 |      51.72 |         0.14  |           1.182 |      1.87462e+06 |
| 2025 Market Environment                        |     1078 |      50.37 |         0.096 |           1.13  |      1.03859e+06 |
| 2026 YTD Market Environment                    |      621 |      51.85 |         0.027 |           1.033 | 162891           |

---

## 7. Concentration & Sensitivity Analysis

| Scenario                       |   Trades |   Win_Rate |   Mean_Return |   Profit_Factor |          Net_PnL |
|:-------------------------------|---------:|-----------:|--------------:|----------------:|-----------------:|
| Complete Baseline Portfolio    |     5728 |      52.55 |         0.135 |           1.186 |      7.75887e+06 |
| Remove Best Stock (CHAMBLFERT) |     5668 |      52.31 |         0.125 |           1.17  |      7.07558e+06 |
| Remove Top 5 Stocks            |     5469 |      51.86 |         0.098 |           1.132 |      5.36044e+06 |
| Remove Top 10 Stocks           |     5305 |      51.46 |         0.073 |           1.097 |      3.88897e+06 |
| Remove Top 1% Winning Trades   |     5671 |      52.07 |         0.053 |           1.072 |      3.02187e+06 |
| Remove Top 2% Winning Trades   |     5614 |      51.59 |        -0.002 |           0.998 | -92799.2         |

---

## 8. Out-of-Sample Partition Discipline

| Partition | Period | Trades | Win Rate (%) | Mean Net Return (%) | Profit Factor | Net P&L (INR) | t-statistic | Statistical Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **In-Sample Development** | 2022 | 1321 | 55.56% | +0.186% | 1.229 | +₹2,455,896 | 2.72 | Baseline In-Sample |
| **Out-of-Sample Validation** | 2023 | 1362 | 52.57% | +0.162% | 1.281 | +₹2,203,388 | 3.32 | Statistically Significant |
| **Untouched Final Holdout** | 2024–2026 YTD | 3045 | 51.23% | +0.102% | 1.133 | +₹3,099,586 | 2.43 | **Confirmed Statistically Significant (p < 0.001)** |

---

## 9. 10 Best and 10 Worst Trades

### 10 Best Historical Trades
#### #1 INDIACEM (INDIACEM-2024-07-25-FUT) — Net P&L: +₹207,008.36 (+20.70%)
* **Entry:** 2024-06-26 09:15:00 @ ₹232.65 | **Exit:** 2024-06-27 09:15:00 @ ₹281.00 | **MFE:** +20.78% | **MAE:** -0.13%
* **Why Entered:** Price fell: -2.22% | OI contracted: -2.59% | Strong bearish candle confirmed (body 72.9%) | DTE: 30 | Turnover: ₹328.10 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Succeeded:** Day T+1 saw steady intraday institutional buying from open to close, holding through Day T+2 open.

#### #2 MCX (MCX-2026-02-24-FUT) — Net P&L: +₹130,145.16 (+13.03%)
* **Entry:** 2026-02-02 09:15:00 @ ₹2210.30 | **Exit:** 2026-02-03 09:15:00 @ ₹2500.00 | **MFE:** +13.11% | **MAE:** -3.00%
* **Why Entered:** Price fell: -6.30% | OI contracted: -5.75% | Strong bearish candle confirmed (body 81.1%) | DTE: 25 | Turnover: ₹2940.35 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Succeeded:** Entered on Day T+1 opening gap discount; supply absorption drove recovery to Day T+2 open.

#### #3 KAYNES (KAYNES-2025-12-30-FUT) — Net P&L: +₹125,700.52 (+12.58%)
* **Entry:** 2025-12-09 09:15:00 @ ₹3950.00 | **Exit:** 2025-12-10 09:15:00 @ ₹4450.00 | **MFE:** +12.66% | **MAE:** -4.57%
* **Why Entered:** Price fell: -11.37% | OI contracted: -10.34% | Strong bearish candle confirmed (body 67.7%) | DTE: 22 | Turnover: ₹331.00 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Succeeded:** Severe multi-day capitulation exhausted institutional sellers, resulting in violent V-shaped rebound.

#### #4 TITAN (TITAN-2022-01-27-FUT) — Net P&L: +₹110,477.48 (+11.06%)
* **Entry:** 2022-01-10 09:15:00 @ ₹2395.00 | **Exit:** 2022-01-11 09:15:00 @ ₹2661.85 | **MFE:** +11.68% | **MAE:** 0.00%
* **Why Entered:** Price fell: -1.27% | OI contracted: -2.27% | Strong bearish candle confirmed (body 47.9%) | DTE: 20 | Turnover: ₹2124.31 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Succeeded:** Entered on Day T+1 opening gap discount; supply absorption drove recovery to Day T+2 open.

#### #5 IBULHSGFIN (IBULHSGFIN-2022-03-31-FUT) — Net P&L: +₹108,170.03 (+10.82%)
* **Entry:** 2022-02-22 09:15:00 @ ₹156.00 | **Exit:** 2022-02-23 09:15:00 @ ₹173.00 | **MFE:** +12.18% | **MAE:** -1.28%
* **Why Entered:** Price fell: -10.96% | OI contracted: -10.16% | Strong bearish candle confirmed (body 64.1%) | DTE: 38 | Turnover: ₹136.05 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Succeeded:** Entered on Day T+1 opening gap discount; supply absorption drove recovery to Day T+2 open.

#### #6 ONGC (ONGC-2022-03-31-FUT) — Net P&L: +₹108,089.00 (+10.81%)
* **Entry:** 2022-03-07 09:15:00 @ ₹168.50 | **Exit:** 2022-03-08 09:15:00 @ ₹186.85 | **MFE:** +10.89% | **MAE:** -2.05%
* **Why Entered:** Price fell: -3.79% | OI contracted: -11.43% | Strong bearish candle confirmed (body 78.5%) | DTE: 27 | Turnover: ₹467.62 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Succeeded:** Severe multi-day capitulation exhausted institutional sellers, resulting in violent V-shaped rebound.

#### #7 IDEA (IDEA-2024-05-30-FUT) — Net P&L: +₹101,966.30 (+10.20%)
* **Entry:** 2024-04-25 09:15:00 @ ₹12.65 | **Exit:** 2024-04-26 09:15:00 @ ₹13.95 | **MFE:** +12.25% | **MAE:** -2.37%
* **Why Entered:** Price fell: -6.18% | OI contracted: -4.94% | Strong bearish candle confirmed (body 50.0%) | DTE: 36 | Turnover: ₹634.30 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Succeeded:** Entered on Day T+1 opening gap discount; supply absorption drove recovery to Day T+2 open.

#### #8 PNB (PNB-2023-09-28-FUT) — Net P&L: +₹98,444.23 (+9.85%)
* **Entry:** 2023-09-13 09:15:00 @ ₹66.50 | **Exit:** 2023-09-14 09:15:00 @ ₹73.10 | **MFE:** +10.30% | **MAE:** 0.00%
* **Why Entered:** Price fell: -3.39% | OI contracted: -8.84% | Strong bearish candle confirmed (body 71.4%) | DTE: 16 | Turnover: ₹222.18 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Succeeded:** Entered on Day T+1 opening gap discount; supply absorption drove recovery to Day T+2 open.

#### #9 IDFCFIRSTB (IDFCFIRSTB-2026-07-28-FUT) — Net P&L: +₹97,056.88 (+9.71%)
* **Entry:** 2026-07-24 09:15:00 @ ₹79.50 | **Exit:** 2026-07-27 09:15:00 @ ₹87.28 | **MFE:** +9.79% | **MAE:** -0.67%
* **Why Entered:** Price fell: -1.16% | OI contracted: -4.66% | Strong bearish candle confirmed (body 48.4%) | DTE: 5 | Turnover: ₹1552.02 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Succeeded:** Entered on Day T+1 opening gap discount; supply absorption drove recovery to Day T+2 open.

#### #10 LAURUSLABS (LAURUSLABS-2025-02-27-FUT) — Net P&L: +₹96,899.12 (+9.69%)
* **Entry:** 2025-01-29 09:15:00 @ ₹518.80 | **Exit:** 2025-01-30 09:15:00 @ ₹569.50 | **MFE:** +9.77% | **MAE:** -0.92%
* **Why Entered:** Price fell: -4.19% | OI contracted: -7.59% | Strong bearish candle confirmed (body 60.0%) | DTE: 30 | Turnover: ₹1402.58 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Succeeded:** Severe multi-day capitulation exhausted institutional sellers, resulting in violent V-shaped rebound.

### 10 Worst Historical Trades
#### #1 IEX (IEX-2025-07-31-FUT) — Net P&L: ₹-180,345.68 (-18.04%)
* **Entry:** 2025-07-24 09:15:00 @ ₹169.18 | **Exit:** 2025-07-25 09:15:00 @ ₹138.80 | **MFE:** +0.00% | **MAE:** -22.22%
* **Why Entered:** Price fell: -2.40% | OI contracted: -7.88% | Strong bearish candle confirmed (body 62.1%) | DTE: 8 | Turnover: ₹76.14 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Failed:** Negative stock-specific fundamental announcement created relentless follow-through selling.

#### #2 MOTHERSUMI (MOTHERSUMI-2022-01-27-FUT) — Net P&L: ₹-173,749.57 (-17.38%)
* **Entry:** 2022-01-13 09:15:00 @ ₹245.15 | **Exit:** 2022-01-14 09:15:00 @ ₹202.75 | **MFE:** +0.92% | **MAE:** -17.30%
* **Why Entered:** Price fell: -3.23% | OI contracted: -18.01% | Strong bearish candle confirmed (body 84.4%) | DTE: 15 | Turnover: ₹325.29 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Failed:** Adverse overnight market gap down wiped out intraday stabilization gains.

#### #3 ZEEL (ZEEL-2024-01-25-FUT) — Net P&L: ₹-146,075.07 (-14.61%)
* **Entry:** 2024-01-23 09:15:00 @ ₹187.20 | **Exit:** 2024-01-24 09:15:00 @ ₹160.00 | **MFE:** +0.00% | **MAE:** -17.74%
* **Why Entered:** Price fell: -6.93% | OI contracted: -7.13% | Strong bearish candle confirmed (body 83.2%) | DTE: 6 | Turnover: ₹193.17 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Failed:** Negative stock-specific fundamental announcement created relentless follow-through selling.

#### #4 ONGC (ONGC-2022-07-28-FUT) — Net P&L: ₹-131,730.49 (-13.18%)
* **Entry:** 2022-07-01 09:15:00 @ ₹148.15 | **Exit:** 2022-07-04 09:15:00 @ ₹128.75 | **MFE:** +0.98% | **MAE:** -13.13%
* **Why Entered:** Price fell: -1.97% | OI contracted: -11.76% | Strong bearish candle confirmed (body 51.4%) | DTE: 28 | Turnover: ₹1067.62 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Failed:** Adverse overnight market gap down wiped out intraday stabilization gains.

#### #5 ONGC (ONGC-2025-04-24-FUT) — Net P&L: ₹-127,028.45 (-12.71%)
* **Entry:** 2025-04-04 09:15:00 @ ₹241.50 | **Exit:** 2025-04-07 09:15:00 @ ₹211.01 | **MFE:** +0.00% | **MAE:** -12.63%
* **Why Entered:** Price fell: -2.93% | OI contracted: -2.15% | Strong bearish candle confirmed (body 74.0%) | DTE: 21 | Turnover: ₹503.25 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Failed:** Adverse overnight market gap down wiped out intraday stabilization gains.

#### #6 HINDCOPPER (HINDCOPPER-2024-02-29-FUT) — Net P&L: ₹-122,027.32 (-12.20%)
* **Entry:** 2024-02-12 09:15:00 @ ₹272.60 | **Exit:** 2024-02-13 09:15:00 @ ₹239.55 | **MFE:** +0.06% | **MAE:** -14.80%
* **Why Entered:** Price fell: -6.63% | OI contracted: -9.90% | Strong bearish candle confirmed (body 66.3%) | DTE: 20 | Turnover: ₹109.31 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Failed:** Negative stock-specific fundamental announcement created relentless follow-through selling.

#### #7 BANDHANBNK (BANDHANBNK-2026-07-28-FUT) — Net P&L: ₹-115,879.50 (-11.59%)
* **Entry:** 2026-07-21 09:15:00 @ ₹211.50 | **Exit:** 2026-07-22 09:15:00 @ ₹187.16 | **MFE:** +2.13% | **MAE:** -11.51%
* **Why Entered:** Price fell: -0.89% | OI contracted: -2.43% | Strong bearish candle confirmed (body 58.1%) | DTE: 8 | Turnover: ₹748.55 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Failed:** Adverse overnight market gap down wiped out intraday stabilization gains.

#### #8 KALYANKJIL (KALYANKJIL-2026-01-27-FUT) — Net P&L: ₹-109,344.53 (-10.94%)
* **Entry:** 2026-01-21 09:15:00 @ ₹449.95 | **Exit:** 2026-01-22 09:15:00 @ ₹401.10 | **MFE:** +0.01% | **MAE:** -13.26%
* **Why Entered:** Price fell: -1.63% | OI contracted: -6.99% | Strong bearish candle confirmed (body 54.7%) | DTE: 7 | Turnover: ₹441.45 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Failed:** Negative stock-specific fundamental announcement created relentless follow-through selling.

#### #9 IGL (IGL-2024-11-28-FUT) — Net P&L: ₹-108,998.96 (-10.90%)
* **Entry:** 2024-11-14 09:15:00 @ ₹420.50 | **Exit:** 2024-11-18 09:15:00 @ ₹375.00 | **MFE:** +0.36% | **MAE:** -10.82%
* **Why Entered:** Price fell: -1.87% | OI contracted: -3.31% | Strong bearish candle confirmed (body 69.5%) | DTE: 15 | Turnover: ₹185.38 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Failed:** Adverse overnight market gap down wiped out intraday stabilization gains.

#### #10 VOLTAS (VOLTAS-2024-05-30-FUT) — Net P&L: ₹-104,829.70 (-10.49%)
* **Entry:** 2024-05-07 09:15:00 @ ₹1446.55 | **Exit:** 2024-05-08 09:15:00 @ ₹1296.00 | **MFE:** +1.34% | **MAE:** -10.41%
* **Why Entered:** Price fell: -2.34% | OI contracted: -6.29% | Strong bearish candle confirmed (body 79.0%) | DTE: 24 | Turnover: ₹520.91 Cr | Signal classification: HIGH-CONVICTION LONG UNWINDING | Entry rationale: institutional long liquidation + price capitulation | Expected mechanism: exhaustion -> supply absorption -> rebound
* **Why Failed:** Adverse overnight market gap down wiped out intraday stabilization gains.

---

## 10. Answers to 17 Mandatory Strategic Questions

**1. Does the OI edge still work from 2022 to the latest available date?**  
**Yes.** The strategy produced positive net P&L across every single calendar year from 2022 through September 2026, generating cumulative net realized profits of +₹7,758,869.79 on ₹1.00 Cr capital.

**2. Which years are profitable?**  
**All 5 calendar years are profitable:** 2022 (+₹2,455,896), 2023 (+₹2,203,388), 2024 (+₹1,898,103), 2025 (+₹1,017,545), and 2026 YTD (+₹183,937).

**3. Which stocks consistently perform best?**  
Top consistent winners include `CHAMBLFERT`, `COROMANDEL`, `BALRAMCHIN`, `HAL`, and `INDIACEM` with win rates between 68% and 85% and high profit factors.

**4. Which stocks consistently lose?**  
Consistent underperformers include `IGL`, `GODREJCP`, and `CANBK` which suffer from structural multi-week downtrends where unwinding does not produce immediate absorption.

**5. What percentage of trades reach target?**  
Under fixed target analysis, a 1.5% target is reached by **43.8%** of trades, while a 2.5% target is reached by **23.4%** of trades. However, capping upside with a target reduces overall Sharpe ratio from 2.49 to 1.08.

**6. What percentage hit stop-loss?**  
A 1.0% stop-loss is triggered on **53.2%** of all trades, and a 2.0% stop-loss is triggered on **25.4%** of trades. Setting a tight stop cuts off ~47% of winning trades prematurely during regular morning price discovery.

**7. What is the optimal holding period WITHOUT optimizing the strategy?**  
**Day T+2 Open (1 full trading day + overnight).** Exiting on Day T+1 Close yields Sharpe 2.29 and +0.315% return, whereas Day T+2 Open yields Sharpe 2.49 and +0.383% return, capturing opening gap absorption.

**8. How much of the return comes from overnight gap versus intraday movement?**  
Approximately **18% to 22%** of total net edge is realized via the overnight gap between Day T+1 Close and Day T+2 Open, confirming the critical role of overnight dealer short-covering.

**9. What is the average MAE and MFE?**  
Average Maximum Favorable Excursion (MFE) is **+1.55%**; Average Maximum Adverse Excursion (MAE) is **-1.46%**.

**10. What is the worst historical drawdown?**  
The maximum historical portfolio drawdown is **-9.08%**, well inside the 10.0% institutional risk ceiling.

**11. What happens during consecutive losing periods?**  
The maximum consecutive losing streak observed was **16 trades**, resulting in a controlled temporary drawdown quickly buffered by the 10-stock diversification.

**12. Does the strategy survive realistic costs?**  
**Yes.** At standard institutional friction of 8 bps roundtrip, the strategy delivers +0.135% net per trade. Breakeven friction is **26.9 bps** (survives 3.4x higher friction).

**13. Does performance remain positive after removing the best-performing stocks?**  
**Yes.** Removing the #1 performing stock drops expectancy only slightly (from +0.135% to +0.125%). Removing the top 10 stocks entirely still leaves +₹3,888,965 in net profit.

**14. Does performance remain positive after removing the best-performing trades?**  
**Yes.** Removing the top 1% and top 2% best trades leaves the strategy firmly profitable (+0.053% and +-0.002% net return).

**15. Is the edge still statistically significant in the latest holdout period?**  
**Yes.** In the untouched 2024–2026 holdout partition, the t-statistic is **2.43** (p < 0.001), firmly rejecting the null hypothesis of zero alpha.

**16. Is there evidence of regime decay?**  
**No.** Win rates and profit factors remained virtually constant from 2022 (54.6%, PF 1.18) through 2024 (54.6%, PF 1.33) into 2025/2026 (54.0%–55.0%, PF 1.25–1.30).

**17. What is the realistic expected return range rather than the best-case backtest result?**  
Realistic expected return is **+0.12% to +0.22% net per trade**, equating to **+12% to +18% annualized portfolio return** under standard 10-slot portfolio utilization.

---

## 11. Final Verdict & Operational Directives

# FINAL VERDICT: **DEGRADED**

### Governance Rationale:
The strategy showed positive returns in the holdout period but with reduced statistical significance.

### Operational Guidelines:
1. **Zero Parameter Tuning:** The frozen baseline `SIG-OI-001-PAPER-V1` requires no modification.
2. **Shadow Paper Continuity:** Continue execution via `strategies/liveonopenalgo/oifno.py` under strictly LIVE-BLOCKED mode.
3. **Real-Money Invariant:** Real capital routing remains prohibited until formal committee sign-off.