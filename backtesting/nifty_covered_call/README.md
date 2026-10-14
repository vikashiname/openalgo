# NIFTY Covered Call: Research & Backtesting Workspace

## 1. Role & Digital-Twin Protocol
This folder serves as the dedicated research, backtesting, and parameter optimization workspace for the NIFTY Covered Call strategy, functioning as the digital twin to [`strategies/liveonopenalgo/nifty_covered_call.py`](file:///Users/mac/Desktop/openalgo/strategies/liveonopenalgo/nifty_covered_call.py).

## 2. Directory Governance (Directive 5A)
1. **Zero Contamination**: All backtest runs, parameter grid searches, and paper replays must operate here using local or ephemeral state files.
2. **Strategy Code Parity**: Code changes must be validated here with 100% test passes before promotion to the live production directory.
3. **Outputs & Logs**: All research artifacts (CSV logs, equity curves, Greeks drift reports) are stored inside this directory and never committed into the live folder.

## 3. Key Strategy Parameters
- **Underlying**: NIFTY 50 Futures / Spot
- **Delta Selection**: ~0.30 Delta Call (CE) expiring in ~28 DTE
- **Profit Target**: 90% premium decay (`target_pct = 0.90`)
- **Stop Loss**: 3.0x initial premium (`stoploss_mult = 3.0`)
- **Roll Rule**: When DTE <= 10 days, roll to next monthly cycle
- **Trend Filter**: Spot > 100 EMA
