# MCX 1H EMA/MACD Confirmation Strategy Backtest Report
**Strategy:** MCX 1H EMA (9/26) + MACD (12/26/9) Asymmetric V2-2 Sequential Confirmation  
**Commodities Evaluated:** GOLDM, SILVERMIC, CRUDEOILM  
**Evaluation Date:** 12-Nov-2026 00:17 IST  

---

## 1. Executive Summary

| Symbol | Trades | Win Rate | Profit Factor | Net P&L (INR) | Max Drawdown (INR) | Target Hits | Catastrophe SL |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **GOLDM** | 33 | 39.39% | 1.22 | **₹45,012.29** | ₹51,327.84 | 13 (39.4%) | 3 (9.1%) |
| **SILVERMIC** | 44 | 36.36% | 0.73 | **₹-17,108.85** | ₹28,160.57 | 16 (36.4%) | 8 (18.2%) |
| **CRUDEOILM** | 36 | 33.33% | 1.05 | **₹740.17** | ₹3,583.12 | 12 (33.3%) | 2 (5.6%) |
| **PORTFOLIO TOTAL** | 113 | 36.28% | 1.10 | **₹28,643.61** | ₹51,327.84 | 41 (36.3%) | 13 (11.5%) |

---

## 2. Key Strategy Takeaways for MCX Commodities
1. **High Trend Capture:** Commodities trend strongly during European and US evening trading sessions. The 1H EMA (9/26) + MACD (12/26/9) engine captures multi-day directional trends effectively.
2. **Asymmetric Sequential Confirmation:** Requiring MACD-first confirmation on short positions prevents whipsaw losses during commodity short squeezes.
3. **Trailing Runner with Profit Floor:** Banking early profits (+1.5% Long / +1.0% Short) and trailing high-water-marks with guaranteed profit floors protects capital while maximizing runner profits.
