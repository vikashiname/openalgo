"""
================================================================================
OPENALGO BACKTEST EXPERIMENT LAB: MACD F&O CANDIDATE EVALUATION
================================================================================
Conducts rigorous backtesting across three candidate configurations:
  1. BASELINE: Original 7 Longs & 6 Shorts on 1-Hour candles.
  2. CANDIDATE A: Top 30 High-Liquidity F&O Leaders on 1-Hour candles.
  3. CANDIDATE C: Top 30 Leaders on 15-Minute Multi-Timeframe candles.

Evaluates against SOP-STRAT-003 quantitative checklist gates:
  - Total Trades
  - Win Rate (Target >= 40%)
  - Profit Factor (Target >= 1.30)
  - Max Drawdown (Target <= 20%)
  - Trade Expectancy (Target > 0%)
  - Average Trade Return
================================================================================
"""

import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
import yfinance as yf

# Symbols Definition
ORIGINAL_7 = ["SUNPHARMA", "BAJAJ-AUTO", "BPCL", "WIPRO", "TATASTEEL", "BAJFINANCE", "NTPC"]

TOP_30_LEADERS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "BHARTIARTL",
    "INFY", "SBIN", "ITC", "HINDUNILVR", "LT",
    "BAJFINANCE", "HCLTECH", "SUNPHARMA", "ADANIENT", "KOTAKBANK",
    "TITAN", "ONGC", "NTPC", "AXISBANK", "ADANIPORTS",
    "COALINDIA", "POWERGRID", "BAJAJ-AUTO", "M&M", "TATASTEEL",
    "BPCL", "WIPRO", "ASIANPAINT", "JSWSTEEL", "HINDALCO"
]

FALLBACK_LOTS = {
    "RELIANCE": 250, "TCS": 175, "HDFCBANK": 550, "ICICIBANK": 700, "BHARTIARTL": 475,
    "INFY": 400, "SBIN": 750, "ITC": 1600, "HINDUNILVR": 300, "LT": 175,
    "BAJFINANCE": 750, "HCLTECH": 350, "SUNPHARMA": 350, "ADANIENT": 309, "KOTAKBANK": 400,
    "TITAN": 175, "ONGC": 3850, "NTPC": 3000, "AXISBANK": 625, "ADANIPORTS": 475,
    "COALINDIA": 1350, "POWERGRID": 1950, "BAJAJ-AUTO": 75, "M&M": 350, "TATASTEEL": 2750,
    "BPCL": 1800, "WIPRO": 1500, "ASIANPAINT": 250, "JSWSTEEL": 675, "HINDALCO": 700
}


def download_candles(symbol: str, interval: str, days: int = 60) -> pd.DataFrame:
    """Downloads historical candles with error resilience."""
    ticker = f"{symbol}.NS"
    try:
        df = yf.download(ticker, period=f"{days}d", interval=interval, progress=False)
        if df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).capitalize() for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()


def run_strategy_simulation(
    symbols: List[str],
    interval: str,
    days: int = 60,
    use_trend_filter: bool = False,
    target_pct: float = 3.0,
    sl_pct: float = 3.5,
) -> Dict[str, any]:
    """Simulates MACD execution on portfolio."""
    all_trades = []
    
    for sym in symbols:
        df = download_candles(sym, interval=interval, days=days)
        if df.empty or len(df) < 35:
            continue
            
        close = df["Close"].astype(float)
        high = df["High"].astype(float) if "High" in df.columns else close
        low = df["Low"].astype(float) if "Low" in df.columns else close
        lot = FALLBACK_LOTS.get(sym, 250)
        
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        sig = macd.ewm(span=9, adjust=False).mean()
        
        # Trend EMA if multi-timeframe enabled
        ema50 = close.ewm(span=50, adjust=False).mean()
        
        in_pos = False
        pos_side = 0  # +1 Long, -1 Short
        entry_price = 0.0
        entry_time = None
        
        for i in range(1, len(close)):
            c_px = float(close.iloc[i])
            h_px = float(high.iloc[i])
            l_px = float(low.iloc[i])
            ts = close.index[i]
            
            m_prev, s_prev = macd.iloc[i-1], sig.iloc[i-1]
            m_cur, s_cur = macd.iloc[i], sig.iloc[i]
            
            # 1. Check Exit for existing position (Opposite Signal, Target, SL)
            if in_pos:
                exit_price = None
                exit_reason = None
                
                if pos_side == 1:
                    # Long Target Hit
                    if target_pct > 0 and h_px >= entry_price * (1.0 + target_pct / 100.0):
                        exit_price = entry_price * (1.0 + target_pct / 100.0)
                        exit_reason = "TARGET_HIT"
                    # Long Catastrophe SL
                    elif sl_pct > 0 and l_px <= entry_price * (1.0 - sl_pct / 100.0):
                        exit_price = entry_price * (1.0 - sl_pct / 100.0)
                        exit_reason = "SL_HIT"
                    # Opposite Cross
                    elif m_prev >= s_prev and m_cur < s_cur:
                        exit_price = c_px
                        exit_reason = "MACD_REVERSAL"
                        
                elif pos_side == -1:
                    # Short Target Hit
                    if target_pct > 0 and l_px <= entry_price * (1.0 - (target_pct / 2.0) / 100.0):
                        exit_price = entry_price * (1.0 - (target_pct / 2.0) / 100.0)
                        exit_reason = "TARGET_HIT"
                    # Short Catastrophe SL
                    elif sl_pct > 0 and h_px >= entry_price * (1.0 + sl_pct / 100.0):
                        exit_price = entry_price * (1.0 + sl_pct / 100.0)
                        exit_reason = "SL_HIT"
                    # Opposite Cross
                    elif m_prev <= s_prev and m_cur > s_cur:
                        exit_price = c_px
                        exit_reason = "MACD_REVERSAL"
                        
                if exit_price is not None:
                    ret_pct = ((exit_price - entry_price) / entry_price * 100.0) if pos_side == 1 else ((entry_price - exit_price) / entry_price * 100.0)
                    pnl_rupees = ((exit_price - entry_price) * lot) if pos_side == 1 else ((entry_price - exit_price) * lot)
                    all_trades.append({
                        "symbol": sym,
                        "side": "LONG" if pos_side == 1 else "SHORT",
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "ret_pct": ret_pct,
                        "pnl_rupees": pnl_rupees,
                        "reason": exit_reason,
                        "entry_time": entry_time,
                        "exit_time": ts,
                    })
                    in_pos = False
                    pos_side = 0
                    
            # 2. Check Fresh Entry
            if not in_pos:
                # Buy Entry
                if m_prev <= s_prev and m_cur > s_cur:
                    if (not use_trend_filter) or (c_px > ema50.iloc[i]):
                        in_pos = True
                        pos_side = 1
                        entry_price = c_px
                        entry_time = ts
                # Sell Entry
                elif m_prev >= s_prev and m_cur < s_cur:
                    if (not use_trend_filter) or (c_px < ema50.iloc[i]):
                        in_pos = True
                        pos_side = -1
                        entry_price = c_px
                        entry_time = ts

    # Aggregate Statistics
    total_trades = len(all_trades)
    if total_trades == 0:
        return {"total_trades": 0, "win_rate": 0, "profit_factor": 0, "expectancy": 0, "net_pnl": 0}
        
    wins = [t for t in all_trades if t["pnl_rupees"] > 0]
    losses = [t for t in all_trades if t["pnl_rupees"] <= 0]
    win_rate = len(wins) / total_trades * 100.0
    
    total_profit = sum(t["pnl_rupees"] for t in wins)
    total_loss = abs(sum(t["pnl_rupees"] for t in losses))
    profit_factor = (total_profit / total_loss) if total_loss > 0 else (99.0 if total_profit > 0 else 0.0)
    net_pnl = total_profit - total_loss
    expectancy = np.mean([t["ret_pct"] for t in all_trades])
    
    # Cumulative Drawdown
    equity_curve = np.cumsum([t["pnl_rupees"] for t in all_trades])
    peak = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - peak)
    max_dd_rupees = abs(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0
    
    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy_pct": round(expectancy, 2),
        "net_pnl_rupees": round(net_pnl, 2),
        "max_dd_rupees": round(max_dd_rupees, 2),
        "avg_win": round(np.mean([t["pnl_rupees"] for t in wins]), 2) if wins else 0.0,
        "avg_loss": round(np.mean([t["pnl_rupees"] for t in losses]), 2) if losses else 0.0,
    }


def main():
    print("=" * 80)
    print("🧪 RUNNING RIGOROUS 60-DAY MULTI-CANDIDATE BACKTEST EXPERIMENT")
    print("=" * 80)
    
    # Run Experiment 1: Baseline
    print("\n[*] Evaluating BASELINE: Original 7 Champions (1-Hour candles)...")
    res_baseline = run_strategy_simulation(ORIGINAL_7, interval="1h", days=60, use_trend_filter=False)
    
    # Run Experiment 2: Candidate A
    print("[*] Evaluating CANDIDATE A: Top 30 Liquid F&O Leaders (1-Hour candles)...")
    res_cand_a = run_strategy_simulation(TOP_30_LEADERS, interval="1h", days=60, use_trend_filter=False)
    
    # Run Experiment 3: Candidate C
    print("[*] Evaluating CANDIDATE C: Top 30 Liquid Leaders (15-Minute candles + EMA-50 Trend)...")
    res_cand_c = run_strategy_simulation(TOP_30_LEADERS, interval="15m", days=60, use_trend_filter=True)
    
    # Print Comparative Matrix
    print("\n" + "=" * 80)
    print(f"{'METRIC':<25} | {'BASELINE (7 Syms, 1H)':<22} | {'CANDIDATE A (30, 1H)':<20} | {'CANDIDATE C (30, 15m)'}")
    print("-" * 80)
    print(f"{'Total Trades':<25} | {res_baseline['total_trades']:<22} | {res_cand_a['total_trades']:<20} | {res_cand_c['total_trades']}")
    print(f"{'Win Rate (%)':<25} | {res_baseline['win_rate']:<22}% | {res_cand_a['win_rate']:<20}% | {res_cand_c['win_rate']}%")
    print(f"{'Profit Factor':<25} | {res_baseline['profit_factor']:<22} | {res_cand_a['profit_factor']:<20} | {res_cand_c['profit_factor']}")
    print(f"{'Expectancy (%/trade)':<25} | {res_baseline['expectancy_pct']:<22}% | {res_cand_a['expectancy_pct']:<20}% | {res_cand_c['expectancy_pct']}%")
    print(f"{'Net P&L (₹)':<25} | ₹{res_baseline['net_pnl_rupees']:<21,.2f} | ₹{res_cand_a['net_pnl_rupees']:<19,.2f} | ₹{res_cand_c['net_pnl_rupees']:,.2f}")
    print(f"{'Max Drawdown (₹)':<25} | ₹{res_baseline['max_dd_rupees']:<21,.2f} | ₹{res_cand_a['max_dd_rupees']:<19,.2f} | ₹{res_cand_c['max_dd_rupees']:,.2f}")
    print("=" * 80)


if __name__ == "__main__":
    main()
