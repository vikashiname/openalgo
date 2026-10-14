import numpy as np
import pandas as pd

def calculate_income_metrics(trade_df, monthly_df, initial_capital, risk_free_rate=0.065):
    """
    Computes all quantitative risk, return, consistency and rent-generation metrics.
    """
    if trade_df.empty or monthly_df.empty:
        return {'status': 'EMPTY', 'total_trades': 0}

    total_net_pnl = trade_df['net_pnl'].sum()
    total_trades = len(trade_df)
    win_trades = trade_df[trade_df['net_pnl'] > 0]
    loss_trades = trade_df[trade_df['net_pnl'] <= 0]
    win_rate = len(win_trades) / total_trades if total_trades > 0 else 0.0

    gross_profit = win_trades['net_pnl'].sum() if not win_trades.empty else 0.0
    gross_loss = abs(loss_trades['net_pnl'].sum()) if not loss_trades.empty else 0.001
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 99.0

    # Monthly rent metrics
    monthly_pnl = monthly_df['net_pnl']
    monthly_rent_yield = monthly_pnl / monthly_df['capital_deployed']
    total_months = len(monthly_df)
    profitable_months = (monthly_pnl > 0).sum()
    profitable_month_pct = profitable_months / total_months if total_months > 0 else 0.0

    mean_monthly_rent = monthly_rent_yield.mean()
    median_monthly_rent = monthly_rent_yield.median()
    std_monthly_rent = monthly_rent_yield.std(ddof=1) if total_months > 1 else 0.001
    worst_month = monthly_rent_yield.min()
    best_month = monthly_rent_yield.max()

    # Outlier dependency: P&L after removing top 5% winning trades
    n_drop = max(1, int(np.ceil(0.05 * total_trades)))
    sorted_pnl = trade_df['net_pnl'].sort_values(ascending=False)
    pnl_ex_top5pct = sorted_pnl.iloc[n_drop:].sum() if total_trades > n_drop else total_net_pnl

    # Check if single best month drives > 25% of total profit
    max_month_pnl = monthly_pnl.max()
    month_concentration = (max_month_pnl / total_net_pnl) if total_net_pnl > 0 else 1.0

    # Annual consistency
    monthly_df['year'] = monthly_df['month'].str[:4]
    annual_pnl = monthly_df.groupby('year')['net_pnl'].sum()
    profitable_years = (annual_pnl > 0).sum()
    total_years = len(annual_pnl)
    profitable_year_pct = profitable_years / total_years if total_years > 0 else 0.0

    # Cumulative equity curve & Max Drawdown
    monthly_df['cum_pnl'] = monthly_pnl.cumsum()
    monthly_df['nav'] = initial_capital + monthly_df['cum_pnl']
    cum_max = monthly_df['nav'].cummax()
    drawdown = (monthly_df['nav'] - cum_max) / cum_max
    max_drawdown = abs(drawdown.min())

    # Annualized return (CAGR)
    num_years = max(0.5, total_months / 12.0)
    final_nav = monthly_df['nav'].iloc[-1]
    cagr = ((final_nav / initial_capital) ** (1.0 / num_years)) - 1.0 if final_nav > 0 else -1.0

    # Annual Rent Yield (Annualized strategy P&L / avg capital deployed)
    avg_capital = monthly_df['capital_deployed'].mean()
    annual_rent_yield = (total_net_pnl / num_years) / avg_capital if avg_capital > 0 else 0.0

    # Sharpe & Sortino
    rf_monthly = ((1.0 + risk_free_rate) ** (1.0 / 12.0)) - 1.0
    excess_monthly = monthly_rent_yield - rf_monthly
    sharpe = (excess_monthly.mean() / std_monthly_rent * np.sqrt(12.0)) if std_monthly_rent > 0 else -5.0

    downside_diff = excess_monthly[excess_monthly < 0]
    downside_dev = np.sqrt(np.mean(downside_diff ** 2)) if len(downside_diff) > 0 else 0.0001
    sortino = (excess_monthly.mean() / downside_dev * np.sqrt(12.0)) if downside_dev > 0 else 99.0

    calmar = (cagr / max_drawdown) if max_drawdown > 0 else 0.0

    # AutoResearch Composite Score
    # Emphasizes:
    # 1. Risk-adjusted net return (Sharpe, Sortino)
    # 2. Maximum drawdown (hard penalty >15%, fatal penalty >20%)
    # 3. Monthly consistency (profitable month %, positive median)
    # 4. Outlier robustness
    score = (
        (sharpe * 25.0) +
        (sortino * 15.0) +
        (calmar * 20.0) +
        (profitable_month_pct * 30.0) +
        (profitable_year_pct * 20.0) +
        (annual_rent_yield * 100.0)
    )

    # Penalties
    if max_drawdown > 0.15:
        score -= (max_drawdown - 0.15) * 400.0  # Steep penalty above 15%
    if max_drawdown > 0.20:
        score -= 200.0  # Fatal penalty for exceeding hard gate
    if profitable_month_pct < 0.65:
        score -= (0.65 - profitable_month_pct) * 200.0
    if median_monthly_rent <= 0:
        score -= 100.0
    if pnl_ex_top5pct <= 0:
        score -= 150.0  # Fails outlier test
    if month_concentration > 0.25:
        score -= 50.0

    return {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'total_net_pnl': total_net_pnl,
        'initial_capital': initial_capital,
        'final_nav': final_nav,
        'cagr': cagr,
        'annual_rent_yield': annual_rent_yield,
        'mean_monthly_rent': mean_monthly_rent,
        'median_monthly_rent': median_monthly_rent,
        'std_monthly_rent': std_monthly_rent,
        'profitable_month_pct': profitable_month_pct,
        'profitable_year_pct': profitable_year_pct,
        'total_months': total_months,
        'max_drawdown': max_drawdown,
        'worst_month': worst_month,
        'best_month': best_month,
        'sharpe': sharpe,
        'sortino': sortino,
        'calmar': calmar,
        'pnl_ex_top5pct': pnl_ex_top5pct,
        'month_concentration': month_concentration,
        'autoresearch_score': score
    }
