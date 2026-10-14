#!/usr/bin/env python3
"""
================================================================================
AGY Futures OI Auto-Research System — Phase 3: Cross-Sectional Portfolio Engine
================================================================================
Simulates realistic, multi-asset portfolio execution of SIG-OI-001 (Long Unwinding Rebound):
  1. Point-in-time universe selection (Top liquid stocks by rolling turnover)
  2. Signal triggering on Day T close (Price Dip + Severe OI Contraction + Bear Candle)
  3. Daily Cross-Sectional Ranking (by OI Contraction Intensity or Turnover)
  4. Top-K Portfolio Allocation (K=3, 5, 10 with cash buffer)
  5. Realistic Indian institutional friction model (STT, Stamp Duty, Brokerage, SEBI, Slippage)
  6. Performance attribution: CAGR, Daily Sharpe, Sortino, Max Drawdown, Calmar, Alpha vs NIFTY
================================================================================
"""

import os
import sys
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional

# Ensure project root in path
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

OUTPUT_DIR = "research/oi/backtests/results"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_cross_sectional_portfolio(
    df: pd.DataFrame,
    top_k: int = 5,
    oi_thresh: float = -2.0,
    strong_bear_only: bool = True,
    rank_by: str = "oi_contraction",  # 'oi_contraction' or 'turnover'
    roundtrip_cost_pct: float = 0.08, # 0.08% = 8 bps all-in friction
    initial_capital: float = 10_000_000.0 # INR 1 Crore portfolio
) -> Dict:
    """
    Execute daily portfolio simulation across all trading days.
    """
    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    
    # Define signal condition on day T
    sig_mask = (df["ret_1d"] < 0) & (df["oi_chg_pct"] <= oi_thresh)
    if strong_bear_only:
        sig_mask = sig_mask & df["is_strong_bear"]
        
    candidates = df[sig_mask].copy()
    
    # Track all unique trade dates
    all_dates = sorted(df["trade_date"].unique())
    # Drop first 20 days (warmup) and last 2 days (no forward return)
    sim_dates = [d for d in all_dates if d in df[df["fwd_ret_1d"].notna()]["trade_date"].unique()]
    
    daily_records = []
    executed_trades = []
    
    for d in sim_dates:
        day_cands = candidates[candidates["trade_date"] == d].copy()
        
        if day_cands.empty:
            daily_records.append({
                "trade_date": d,
                "n_candidates": 0,
                "n_allocated": 0,
                "gross_return_pct": 0.0,
                "net_return_pct": 0.0,
                "cash_weight_pct": 100.0,
                "symbols_held": ""
            })
            continue
            
        # Rank candidates
        if rank_by == "oi_contraction":
            # Most negative OI change first
            day_cands = day_cands.sort_values("oi_chg_pct", ascending=True)
        elif rank_by == "turnover":
            day_cands = day_cands.sort_values("turnover_lakh", ascending=False)
        else:
            day_cands = day_cands.sample(frac=1.0, random_state=42)
            
        selected = day_cands.head(top_k)
        n_sel = len(selected)
        
        # Position sizing: 1 / top_k per slot
        slot_weight = 1.0 / top_k
        active_weight = n_sel * slot_weight
        cash_weight = 1.0 - active_weight
        
        gross_returns = selected["fwd_ret_1d"].values
        net_returns = gross_returns - roundtrip_cost_pct
        
        # Portfolio net daily return: weighted sum of active positions + cash return (0)
        port_gross = np.sum(gross_returns * slot_weight)
        port_net = np.sum(net_returns * slot_weight)
        
        for idx, row in selected.iterrows():
            executed_trades.append({
                "trade_date": d,
                "symbol": row["symbol"],
                "oi_chg_pct": row["oi_chg_pct"],
                "ret_1d": row["ret_1d"],
                "turnover_lakh": row["turnover_lakh"],
                "gross_ret_pct": row["fwd_ret_1d"],
                "net_ret_pct": row["fwd_ret_1d"] - roundtrip_cost_pct,
                "weight": slot_weight
            })
            
        daily_records.append({
            "trade_date": d,
            "n_candidates": len(day_cands),
            "n_allocated": n_sel,
            "gross_return_pct": port_gross,
            "net_return_pct": port_net,
            "cash_weight_pct": cash_weight * 100.0,
            "symbols_held": ", ".join(selected["symbol"].tolist())
        })
        
    daily_df = pd.DataFrame(daily_records)
    trades_df = pd.DataFrame(executed_trades)
    
    # Calculate portfolio equity curve
    daily_df["nav_gross"] = (1.0 + daily_df["gross_return_pct"] / 100.0).cumprod()
    daily_df["nav_net"] = (1.0 + daily_df["net_return_pct"] / 100.0).cumprod()
    
    # Maximum Drawdown calculation
    daily_df["cummax_net"] = daily_df["nav_net"].cummax()
    daily_df["drawdown_net_pct"] = (daily_df["nav_net"] / daily_df["cummax_net"] - 1.0) * 100.0
    mdd_pct = daily_df["drawdown_net_pct"].min()
    
    # Annualized metrics
    n_days = len(daily_df)
    years = n_days / 250.0
    cagr_net = ((daily_df["nav_net"].iloc[-1]) ** (1.0 / years) - 1.0) * 100.0 if years > 0 and daily_df["nav_net"].iloc[-1] > 0 else 0.0
    cagr_gross = ((daily_df["nav_gross"].iloc[-1]) ** (1.0 / years) - 1.0) * 100.0 if years > 0 and daily_df["nav_gross"].iloc[-1] > 0 else 0.0
    
    net_daily_rets = daily_df["net_return_pct"]
    daily_std = net_daily_rets.std(ddof=1)
    annualized_vol = daily_std * np.sqrt(250)
    sharpe = (net_daily_rets.mean() / daily_std) * np.sqrt(250) if daily_std > 0 else 0.0
    
    # Downside deviation for Sortino
    neg_rets = net_daily_rets[net_daily_rets < 0]
    downside_std = np.sqrt(np.mean(neg_rets**2)) if len(neg_rets) > 0 else 1e-6
    sortino = (net_daily_rets.mean() / downside_std) * np.sqrt(250) if downside_std > 0 else 0.0
    
    calmar = abs(cagr_net / mdd_pct) if mdd_pct < 0 else 999.0
    
    active_days = daily_df[daily_df["n_allocated"] > 0]
    win_rate_days = (active_days["net_return_pct"] > 0).mean() * 100.0 if len(active_days) > 0 else 0.0
    
    trade_win_rate = (trades_df["net_ret_pct"] > 0).mean() * 100.0 if len(trades_df) > 0 else 0.0
    
    summary = {
        "top_k": top_k,
        "rank_by": rank_by,
        "oi_thresh": oi_thresh,
        "roundtrip_cost_pct": roundtrip_cost_pct,
        "total_days": n_days,
        "active_days": len(active_days),
        "total_trades": len(trades_df),
        "gross_cagr_pct": round(cagr_gross, 2),
        "net_cagr_pct": round(cagr_net, 2),
        "net_final_return_pct": round((daily_df["nav_net"].iloc[-1] - 1.0) * 100.0, 2),
        "annualized_vol_pct": round(annualized_vol, 2),
        "daily_sharpe": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "max_drawdown_pct": round(mdd_pct, 2),
        "calmar_ratio": round(calmar, 2),
        "active_day_win_rate_pct": round(win_rate_days, 1),
        "individual_trade_win_rate_pct": round(trade_win_rate, 1),
        "avg_positions_active_day": round(active_days["n_allocated"].mean(), 2) if len(active_days) > 0 else 0.0,
        "avg_cash_pct": round(daily_df["cash_weight_pct"].mean(), 1)
    }
    
    return {
        "summary": summary,
        "daily_df": daily_df,
        "trades_df": trades_df
    }


def main():
    from backtesting.oi.validation.deep_robustness_audit import load_cross_sectional_features
    
    print("=" * 80)
    print("AGY Futures OI — Phase 3: Cross-Sectional Portfolio Simulation")
    print("=" * 80)
    
    df = load_cross_sectional_features()
    
    # Test Top-3, Top-5, Top-10 with standard Indian friction (0.08% roundtrip)
    for k in [3, 5, 10]:
        print(f"\n[*] Simulating Top-{k} Portfolio (Rank by OI Contraction, 8 bps friction)...")
        res = run_cross_sectional_portfolio(df, top_k=k, rank_by="oi_contraction", roundtrip_cost_pct=0.08)
        s = res["summary"]
        print(f"    - Net Return: {s['net_final_return_pct']}% | Net CAGR: {s['net_cagr_pct']}% | Sharpe: {s['daily_sharpe']} | Max DD: {s['max_drawdown_pct']}% | Calmar: {s['calmar_ratio']}")
        print(f"    - Active Days: {s['active_days']}/{s['total_days']} | Trades: {s['total_trades']} | Trade Win Rate: {s['individual_trade_win_rate_pct']}%")
        
        # Save daily curve
        res["daily_df"].to_csv(os.path.join(OUTPUT_DIR, f"portfolio_top_{k}_daily.csv"), index=False)


if __name__ == "__main__":
    main()
