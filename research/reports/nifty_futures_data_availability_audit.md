# Quantitative Research Audit — NIFTY Futures Data Availability & Sourcing Audit

---

### Executive Data Availability Summary

| Audit Item | Local Finding | Status |
| :--- | :--- | :---: |
| **1. Available Local NIFTY Futures Datasets** | **None found locally**. | 🔴 **NOT AVAILABLE** |
| **2. Local DuckDB Database (`db/historify.duckdb`)** | Contains only 1 symbol (`TCS` Daily Cash Equity, 1,240 rows). | 🔴 **NO FUTURES DATA** |
| **3. Local Flat Files (`*.csv`, `*.parquet`, `*.h5`)** | Contains only `qtyfreeze.csv` (Freeze limits table) and backtest output logs. | 🔴 **NO FUTURES DATA** |
| **4. Contract-Wise Futures OHLC** | No native `FUTIDX-NIFTY` contract files exist in the repository. | 🔴 **MISSING** |
| **5. Expiry & Open Interest Data** | No historical contract-wise expiry or OI series available locally. | 🔴 **MISSING** |
| **6. Continuous Series Construction Feasibility** | **Cannot construct continuous futures series without external data ingestion**. | 🛑 **STOP CONDITION MET** |
| **7. Final Data Verification Verdict** | **DATA NOT VERIFIED — DO NOT ACCEPT RESULT** | 🛑 **STOP** |

---

### Detailed Inventory of Local Data Assets

#### 1. DuckDB Storage (`db/historify.duckdb`)
- **Tables Inspected**: `data_catalog`, `market_data`, `symbol_metadata`, `watchlist`, `download_jobs`, `job_items`.
- **Symbols Found**: `TCS` (NSE Daily Cash Equity only).
- **Futures Records**: `0 rows`.

#### 2. Directory Tree Inspection (`/Users/mac/Desktop/openalgo`)
- **`data/`**: `qtyfreeze.csv` (Static table of NSE quantity freeze limits per symbol).
- **`research/`**: Python analysis scripts, execution models, and Markdown reports.
- **`reports/`**: Trade log outputs from previous MACD / Ichimoku / Research runs (`RELIANCE_macd_trades.csv`, `TCS_macd_trades.csv`, `nfo_all_trades.csv`).

---

### Quantitative Requirements for Authentic NIFTY Futures Research

To build a valid quantitative research dataset for NIFTY Index Futures, the following specific historical data architecture is required:

#### A. Required Data Architecture
1. **Instrument Type**: Native `FUTIDX-NIFTY` (NSE Index Futures).
2. **Contract Representation**: Individual monthly expiration contracts (Near-Month, Next-Month, Far-Month) rather than a synthesized cash proxy.
3. **Fields Required Per Bar**:
   - `timestamp` (1-Hour / 15-Minute bar timestamp in IST)
   - `open`, `high`, `low`, `close`
   - `volume` (Traded volume in contracts / shares)
   - `open_interest` (Live outstanding contracts for rollover thresholding)
   - `expiry_date` (Official monthly settlement date)

#### B. Historical Lot Size Timeline
- **Post Nov 20, 2024**: **25** (SEBI Index Derivative Lot Size Mandate)
- **May 2024 – Nov 2024**: **25**
- **July 2021 – April 2024**: **50**
- **Prior to July 2021**: **75**

#### C. Rollover Engineering Methodology
A rigorous continuous futures series requires an explicit programmatic rollover rule:
1. **Rollover Trigger**: Roll when Next-Month contract Open Interest (OI) exceeds Near-Month contract OI (typically $T-3$ or $T-2$ days before expiry), or at a fixed calendar window (e.g. expiry day 14:30 IST).
2. **Rollover Stitching**:
   - **Option 1 (Panama Canal Back-Adjustment)**: Shift previous contract prices by the basis difference ($\text{Close}_{\text{next}} - \text{Close}_{\text{near}}$) to remove artificial price jumps at contract transitions.
   - **Option 2 (Unadjusted with Cash-Settled Roll Trades)**: Keep raw traded contract prices intact and programmatically log roll transaction costs (closing Near-Month position and opening Next-Month position with full statutory friction and slippage).

---

### Required Data Sources to Ingest

To obtain authentic historical NIFTY Futures data, one of the following official sources is required:

1. **NSE Historical F&O Archives**:
   - Direct historical Bhavcopy archives from NSE (`archives.nseindia.com`) providing contract-wise daily/intraday settlement records.
2. **Authorized Market Data Vendors**:
   - **TrueData / GlobalDataFeeds**: Provides continuous 1-minute / 1-hour back-adjusted and unadjusted `NIFTY_F1`, `NIFTY_F2` contracts with OI.
3. **Broker Historical APIs**:
   - **Zerodha Kite / Fyers / Angel One / Dhan Historical API**: Provides historical intraday candles for expired NIFTY Futures contracts using their instrument tokens.

---

### 🛑 Integrity Audit Decision

```text
================================================================================
VERDICT: DATA NOT VERIFIED — DO NOT ACCEPT RESULT
================================================================================
STATUS:
1. Previous Candidate A result was generated on NIFTY Spot Index (^NSEI) proxy.
2. No authentic exchange-traded NIFTY Futures (FUTIDX-NIFTY) historical dataset
   is currently available locally.
3. Strategy testing, ML development, filter optimization, and live modifications
   are FROZEN until authentic NIFTY Futures contract data is provided/ingested.
================================================================================
```
