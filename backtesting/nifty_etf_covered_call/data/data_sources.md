# HISTORICAL DATA SOURCE STUDY & EVALUATION

**Document Phase:** Phase 2 — Feasibility & Data Validation  
**Strategy Project:** Covered Call Strategy (Buy-Write Overlay)  
**Primary Implementation:** **LONG NIFTYBEES + SHORT NIFTY 50 CALL (`NIFTY CE`)**  
**File Location:** `~/backtesting/covered call/data/data_sources.md`  
**Date:** September 2026  
**Status:** VALIDATED & AUDITED — HISTORIFY DUCKDB INGESTED  

---

## 1. PURPOSE & DATA ACQUISITION CRITERIA

A rigorous, quantitative Covered Call backtest of **NIFTYBEES + NIFTY 50 CE** requires authentic historical data across two distinct exchange market segments:
1. **Cash Equity Segment (Underlying ETF):** Continuous daily End-of-Day (EOD) time series of **Nippon India ETF Nifty BeES (`NIFTYBEES`)** and the **NIFTY 50 Index (`NIFTY`)** stored directly in **OpenAlgo Historify DuckDB (`db/historify.duckdb`)**.
2. **Derivatives Segment (NIFTY Index Options):** Comprehensive strike series across all historical expiration dates (`OPTIDX NIFTY CE`), recording contract-level prices, traded volume, open interest, and official clearing settlement prices from the verified local F&O Bhavcopy archives.

To guarantee institutional reproducibility, prospective data sources are evaluated against strict criteria:
* **Dual-Segment Synchronization:** Every trading session in the Cash Equity dataset must align precisely with the F&O derivatives session (zero calendar mismatch).
* **Local DuckDB Performance:** High-speed columnar retrieval via DuckDB SQL / Apache Parquet without network dependencies.
* **Survivorship Immunity:** Must retain every expired, illiquid, and out-of-the-money contract (zero survivor bias).
* **Exchange Authenticity:** Must match official clearing settlement prices used by NCL for cash debits/credits.
* **Corporate Action Integrity:** NIFTYBEES prices must reflect authentic traded prices without artificial backward split adjustments that distort option contract multiplier matching.

---

## 2. SYSTEMATIC EVALUATION OF HISTORICAL DATA SOURCES

### Source 1: OpenAlgo Historify Local Store (`db/historify.duckdb`)
* **Provider:** OpenAlgo Built-in Historify DuckDB Engine (`services/historify_service.py`, `database/historify_db.py`).
* **Database File:** `/Users/mac/Desktop/openalgo/db/historify.duckdb`.
* **Export Artifacts:**
  * `~/backtesting/covered call/data/niftybees_historify.parquet` (4,360 daily records).
  * `~/backtesting/covered call/data/nifty_historify.parquet` (4,654 daily records).
* **Coverage Period:**
  * `NIFTYBEES:NSE:D`: **January 2, 2009 to September 4, 2026** (4,360 trading days).
  * `NIFTY:NSE:D`: **September 17, 2007 to September 4, 2026** (4,654 trading days).
* **Resolution:** Daily End-of-Day (EOD).
* **Schema Fields:** `timestamp, open, high, low, close, volume, oi`.
* **Access Method:**
  * Python API: `from database.historify_db import get_ohlcv; df = get_ohlcv('NIFTYBEES', 'NSE', 'D')`.
  * OpenAlgo Engine API: `source='db'`.
  * DuckDB SQL: `SELECT * FROM market_data WHERE symbol = 'NIFTYBEES' AND exchange = 'NSE' AND interval = 'D'`.
* **Reliability:** **Local Columnar Truth**. Instant zero-latency in-memory queries.
* **Survivorship Bias:** **ZERO**.
* **Suitability:** **PRIMARY OFFICIAL DATA REPOSITORY FOR STRATEGY EXECUTION & BACKTESTING**.

---

### Source 2: Local Verified NSE F&O Bhavcopy Repository
* **Provider:** Local research cache (`openalgo/backtesting/oi/data/raw/bhavcopy/`).
* **Coverage Period:** **January 3, 2022 to July 31, 2024** (635 consecutive trading days).
* **Resolution:** Daily EOD.
* **Continuity:** Verified **100% complete calendar continuity** (all 635 trading sessions verified against the official NSE holiday calendar).
* **Contract Coverage:** Complete NIFTY option chain across all strikes, weeklies, and monthlies.
* **Suitability:** **IMMEDIATELY VIABLE FOR BASELINE OPTION LEG**.

---

### Source 3: Official NSE Daily Bhavcopy Archives (CM & F&O Segments)
* **Provider:** National Stock Exchange of India Ltd. (NSE).
* **Acquisition Vector:** Direct regulatory archive downloads from `archives.nseindia.com`.
  * Cash Market (CM): `cm<DD><MMM><YYYY>bhav.csv.zip` / `BhavCopy_NSE_CM_...`
  * Derivatives (F&O): `fo<DD><MMM><YYYY>bhav.csv.zip` / `BhavCopy_NSE_FO_...`
* **Coverage Period:** Inception to present day (> 20 years).
* **Resolution:** Daily End-of-Day (EOD).
* **Contract Coverage:** 100% of listed strikes and expiries.
* **Reliability:** **Gold Standard (100% Exchange Truth)**.
* **Survivorship Bias:** **ZERO**.

---

### Source 4: Institutional Data Vendors (TrueData / Global DataFeeds)
* **Provider:** SEBI-registered tick-level data vendors.
* **Coverage Period:** 2010 to Present.
* **Resolution:** 1-minute, 5-minute, and Tick level.
* **Fields Available:** OHLCV, Open Interest, Bid-Ask Depth, IV, Greeks.
* **Cost:** Paid commercial subscription ($₹2,000 \text{--} ₹8,000 / \text{month}$).
* **Suitability:** Recommended for Phase 4+ (Intraday profit taking and dynamic spread slippage modeling).

---

### Source 5: Indian Broker Historical APIs (Zerodha Kite Connect, Angel One, Dhan)
* **Provider:** Broker historical REST APIs.
* **Coverage Period:** Cash equity: 5–10 years; Expired options: Purged after 3–6 months.
* **Suitability:** Unsuitable for multi-year historical option research due to expired strike purging; suitable for live forward paper trading (Phase 7).

---

## 3. COMPARATIVE DATA SOURCE ASSESSMENT MATRIX

| Assessment Vector | 1. Historify DuckDB (`db/historify.duckdb`) | 2. Local Bhavcopy Cache | 3. Official NSE Bhavcopy | 4. TrueData / GDF | 5. Broker Historical APIs |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Asset Governed** | **NIFTYBEES + NIFTY Cash** | NIFTY Options & Futures | F&O + Cash Equity | F&O + Cash Equity | Active Contracts Only |
| **Historical Depth** | **17+ Years (2007–2026)** | 2.58 Years (2022–2024) | > 20 Years | 5–10 Years | < 1 Year for Options |
| **Session Alignment** | **100% Aligned (635/635)** | 100% Exchange Aligned | 100% Exchange Aligned | 100% Aligned | Broken for Expired |
| **Option Chain Breadth** | Cash / Spot Underlying | 100% All Strikes | 100% All Strikes | 100% All Strikes | Severely Fragmented |
| **Storage Engine** | **High-Performance DuckDB** | Compressed CSV zips | Raw exchange archives | Tick Parquet / API | Cloud REST API |
| **Clearing Settle Price** | Traded Close / Settle | **Official Exchange Truth** | **Official Exchange Truth**| Included | Traded Close only |
| **Survivorship Bias** | **Zero** | **Zero** | **Zero** | Low | **Severe** |
| **Cost** | **Free (Native Built-in)** | Free | Free | Paid | Paid |
| **Readiness Status** | **INSTALLED & INGESTED** | **Locally Available** | Validated | Phase 4+ Deferred | Phase 7 Forward Only |

---

## 4. NIFTYBEES COVERED CALL IMPLEMENTATION

### 4.1 Cross-Segment Data Ingestion Architecture

Because the strategy couples **Cash Equity (`NIFTYBEES`)** with **F&O Derivatives (`NIFTY CE`)**, the ingestion engine queries Historify DuckDB directly for the underlying series and reconciles against the local Bhavcopy options repository:

```text
========================================================================================
             DUAL-SEGMENT DATA INGESTION & CROSS-RECONCILIATION PIPELINE
========================================================================================

  [ OpenAlgo Historify DuckDB Store ]           [ F&O Derivatives Stream: NIFTY CE ]
    (db/historify.duckdb: NIFTYBEES:NSE:D)             (Local Verified Bhavcopy Archive)
                  │                                                    │
                  ▼                                                    ▼
     [ Cleanse & Validate Cash Bar ]               [ Parse Daily Option Strikes Universe ]
     • Timestamp: YYYY-MM-DD 15:30 IST             • Filter: SYMBOL == 'NIFTY'
     • Verify P_close > 0                          • Filter: OPTION_TYP == 'CE'
     • Check corporate actions                     • Filter: EXPIRY == Target Monthly Expiry
                  │                                                    │
                  └───────────────────────┬────────────────────────────┘
                                          │
                                          ▼
                      [ Cross-Segment Calendar Reconciliation ]
                      • Enforce Date_Historify == Date_F&O
                      • Verify 635 out of 635 sessions match (100%)
                                          │
                                          ▼
                         [ Dynamic Sizing & Strike Selector ]
                         • Spot S_t, ETF P_t, Lot Size L_t
                         • Compute Tracking Ratio R_t = S_t / P_t
                         • Compute Required Units Q_req = S_t * L_t / P_t
                         • Select Strike K ≈ S_t * 1.02 (Nearest 50 Strike)
                                          │
                                          ▼
                      [ Normalized Strategy Ingestion Table ]
                      • Ready for Phase-3 Mechanical Baseline Engine
========================================================================================
```

### 4.2 Data Integrity Checklist for Historify NIFTYBEES Store
* **Database Location:** `/Users/mac/Desktop/openalgo/db/historify.duckdb`
* **Table:** `market_data`
* **Catalog Status:** Registered in `data_catalog` with 4,360 records for `NIFTYBEES:NSE:D` and 4,654 records for `NIFTY:NSE:D`.
* **Trading Calendar Continuity:** 635 / 635 days verified across 2022–2024 (Zero missing sessions).
* **Parquet Artifacts:** Exported to `~/backtesting/covered call/data/niftybees_historify.parquet` and `~/backtesting/covered call/data/nifty_historify.parquet`.
