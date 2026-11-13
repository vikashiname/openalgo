# Futures Bullish Breakout Scanner — Filter Optimisation

> **AGY MASTER SOP COMPLIANCE:**
> - Master Research Directory: `backtesting/futurebull/` (Symlink: `backtesting/FUTURES_BULLISH_SCANNER`)
> - 100% Isolated from Live Production (`strategies/liveopenalgo`).
> - Zero Live Broker Connections. No live strategy modification.

---

## 📁 Project Directory Map

```text
backtesting/futurebull/
├── download_fno_data.py                 # Downloads & validates 46 liquid F&O stocks (2021-2026)
├── scanner_engine.py                    # Vectorized computation of all 29 scanner conditions
├── Individual_Filter_Analysis.py        # Phase 1: Predictive power & MFE/MAE per condition
├── Filter_Correlation_Analysis.py       # Phase 2 & 3: Group combos & paired redundancy engine
├── Scanner_Optimisation.py              # Phase 4: Parameter sweeps & candidate variant synthesis
├── Scanner_Original_Backtest.py         # Phase 5: Baseline 29-condition executable strategy backtest
├── Futures_Strategy_Backtest.py         # Phase 5 & 6: 5-variant portfolio backtest & regime breakdown
├── Robustness_Validation.py             # Phase 7: Walk-forward IS/OOS & friction stress tests
├── generate_performance_charts.py       # Generates interactive Plotly dark-theme HTML tearsheet
├── RESEARCH_REPORT.md                   # Full quantitative research report & governance verdict
├── README.md                            # Project overview & reproduction guide
├── data/                                # 46 Parquet/CSV files (66,470 daily candles)
└── reports/                             # Generated research artifacts (14 CSVs + HTML dashboard)
    ├── PERFORMANCE_DASHBOARD.html
    ├── PHASE1_INDIVIDUAL_FILTER_METRICS.csv
    ├── PHASE2_COMBINED_GROUP_METRICS.csv
    ├── PHASE3_CORRELATION_MATRIX.csv
    ├── PHASE3_REDUNDANCY_REPORT.csv
    ├── PHASE4_PARAM_SENSITIVITY_EXPERIMENTS.csv
    ├── PHASE4_SCANNER_VARIANTS_COMPARISON.csv
    ├── ORIGINAL_SCANNER_EXIT_MODELS_SUMMARY.csv
    ├── ORIGINAL_SCANNER_TRADE_LEDGER.csv
    ├── OPTIMISED_SCANNER_TRADE_LEDGER.csv
    ├── FUTURES_STRATEGY_PORTFOLIO_BENCHMARK.csv
    ├── YEARLY_PERFORMANCE_BREAKDOWN.csv
    ├── REGIME_PERFORMANCE_BREAKDOWN.csv
    ├── PHASE7_WALK_FORWARD_VALIDATION.csv
    ├── PHASE7_FRICTION_SENSITIVITY.csv
    └── PHASE7_OOS_HOLDING_COMPARISON.csv
```

---

## 🔬 How to Reproduce All Research Results

Run each step sequentially from the project directory:

```bash
cd backtesting/futurebull

# 1. Download & Validate Liquid F&O Historical Candles (46 stocks, 2021-2026)
python3 download_fno_data.py

# 2. Phase 1: Individual Filter Predictive Power Analysis
python3 Individual_Filter_Analysis.py

# 3. Phase 2 & 3: Combined Group Experiments & Redundancy Matrix
python3 Filter_Correlation_Analysis.py

# 4. Phase 4: Parameter Optimization & Candidate Synthesis
python3 Scanner_Optimisation.py

# 5. Phase 5: Original Scanner Baseline Strategy Backtest
python3 Scanner_Original_Backtest.py

# 6. Phase 5 & 6: Portfolio Multi-Variant Backtest & Regime Analysis
python3 Futures_Strategy_Backtest.py

# 7. Phase 7: Walk-Forward & Friction Robustness Validation
python3 Robustness_Validation.py

# 8. Generate Interactive Performance Dashboard
python3 generate_performance_charts.py
```

Open [PERFORMANCE_DASHBOARD.html](file:///Users/mac/Desktop/openalgo/backtesting/futurebull/reports/PERFORMANCE_DASHBOARD.html) in your browser to view the interactive equity curves and tearsheets.

---

## 🏆 Key Research Conclusions

1. **Original Scanner Fails in Short-Term Trading:**
   - 29 conditions cause severe curve-fitting.
   - `Close >= Upper Bollinger Band` buys overbought exhaustion, yielding a negative expectancy (**-0.18% per trade**, Profit Factor 0.87).
   - `MACD Line >= Signal` and `MACD Histogram >= 0` are 100% redundant tautologies.
2. **The Optimised Scanner Solves the Edge:**
   - Drops redundant filters and exhaustion traps.
   - Requires sustainable momentum (`RSI 52-75`, `EMA 20 > 50`, `Volume > 100K`, `Green Candle`, `c < Upper BB`).
   - When held for 15–20 sessions, generates **+₹755,473 Net PnL, Profit Factor 1.08, and Sharpe +0.59** after full Indian statutory frictions and slippage.
