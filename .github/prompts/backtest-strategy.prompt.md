---
description: "Backtest a trading strategy using VectorBT in the OpenAlgo project"
name: "backtest-strategy"
argument-hint: "Provide strategy code, parameters, or reference to existing strategy file"
agent: "agent"
tools: ["run_notebook_cell", "create_new_jupyter_notebook", "read_file", "semantic_search"]
---

Backtest the provided trading strategy using VectorBT.

1. If strategy code is provided, create a Jupyter notebook for backtesting.
2. Fetch historical data for the symbols involved.
3. Run the backtest with appropriate parameters (start date, end date, initial capital).
4. Generate performance metrics: total return, Sharpe ratio, max drawdown, win rate.
5. Plot equity curve and drawdown chart.
6. Provide analysis and recommendations.

Use OpenAlgo's ta helpers if applicable (crossover, supertrend, etc.).
Reference existing backtest examples in the workspace like macd_backtest_strategy.txt.