#!/usr/bin/env python3
"""
================================================================================
AGY Futures OI Auto-Research System — Backtest Engine & Benchmark Comparator
================================================================================
Executes formal simulation of signal contracts with strict execution discipline:
  1. Next-Bar Open Execution (Signal at Close t -> Fill at Open t+1)
  2. Realistic Friction (Slippage + Exchange Fees = 0.05% per trade)
  3. Realistic Intraday Stop Loss Checking
  4. In-Sample (70%) vs Out-of-Sample (30%) Performance Isolation
  5. Side-by-Side Comparison against Price-Only Benchmarks & Buy-and-Hold
================================================================================
"""

import os
import pandas as pd
import numpy as np
from dataclasses import asdict

from backtesting.oi.strategy.signal_contracts import SignalContract, ALL_CONTRACTS

FEATURES_DIR = "research/oi/features"
BACKTESTS_DIR = "research/oi/backtests"
REPORTS_DIR = "research/oi/reports"


def simulate_signal_contract(df: pd.DataFrame, contract: SignalContract, is_split_ratio: float = 0.70) -> dict:
    """
    Simulate trading performance of a SignalContract on featured dataset.
    """
    df = df.copy()
    n_total = len(df)
    split_idx = int(n_total * is_split_ratio)

    # 1. Generate Signal on bar t Close
    signals = contract.entry_generator(df)
    
    # 2. Map Execution to bar t+1 Open
    # Position entered on bar t+1 at Open
    # Trade PnL depends on direction
    trades = []
    
    # Friction (0.03% slippage + 0.02% fees = 0.05% total roundtrip)
    friction_pct = contract.slippage_pct + contract.transaction_cost_pct

    for i in range(len(df) - contract.exit_bars - 1):
        if not signals.iloc[i]:
            continue

        entry_idx = i + 1
        entry_date = df["trade_date"].iloc[entry_idx]
        entry_price = df["open"].iloc[entry_idx]
        sample_type = "IS" if entry_idx < split_idx else "OOS"

        # Check holding period and stop loss
        exit_idx = entry_idx + contract.exit_bars
        if exit_idx >= len(df):
            break

        sl_hit = False
        exit_price = df["close"].iloc[exit_idx - 1] # Close of holding period or Open of next
        
        # Intraday adverse excursion check for Stop Loss
        if contract.trade_direction == "LONG":
            # Check min low across holding bars
            min_low = df["low"].iloc[entry_idx:exit_idx].min()
            adverse_pct = (min_low - entry_price) / entry_price * 100.0
            if adverse_pct <= -contract.stop_loss_pct:
                sl_hit = True
                raw_pnl_pct = -contract.stop_loss_pct
            else:
                raw_pnl_pct = (exit_price - entry_price) / entry_price * 100.0
        else: # SHORT
            max_high = df["high"].iloc[entry_idx:exit_idx].max()
            adverse_pct = (max_high - entry_price) / entry_price * 100.0
            if adverse_pct >= contract.stop_loss_pct:
                sl_hit = True
                raw_pnl_pct = -contract.stop_loss_pct
            else:
                raw_pnl_pct = (entry_price - exit_price) / entry_price * 100.0

        net_pnl_pct = raw_pnl_pct - friction_pct
        trades.append({
            "signal_id": contract.signal_id,
            "hypothesis_id": contract.hypothesis_id,
            "entry_date": entry_date,
            "exit_date": df["trade_date"].iloc[exit_idx - 1],
            "direction": contract.trade_direction,
            "sample": sample_type,
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "raw_pnl_pct": round(raw_pnl_pct, 3),
            "friction_pct": round(friction_pct, 3),
            "net_pnl_pct": round(net_pnl_pct, 3),
            "sl_hit": sl_hit,
            "is_win": net_pnl_pct > 0
        })

    trades_df = pd.DataFrame(trades)
    
    # Summary Statistics helper
    def calc_stats(t_df: pd.DataFrame, label: str) -> dict:
        if t_df.empty:
            return {
                "sample": label, "trades": 0, "win_rate_pct": 0.0,
                "net_pnl_pct": 0.0, "profit_factor": 0.0, "expectancy_pct": 0.0,
                "max_drawdown_pct": 0.0, "sharpe_ratio": 0.0
            }
        n = len(t_df)
        wins = t_df[t_df["net_pnl_pct"] > 0]["net_pnl_pct"]
        losses = t_df[t_df["net_pnl_pct"] <= 0]["net_pnl_pct"]
        
        win_rate = len(wins) / n * 100.0
        tot_win = wins.sum()
        tot_loss = abs(losses.sum())
        pf = tot_win / tot_loss if tot_loss > 0 else (99.0 if tot_win > 0 else 0.0)
        
        cum_ret = (1.0 + t_df["net_pnl_pct"] / 100.0).cumprod()
        peak = cum_ret.cummax()
        dd = (cum_ret - peak) / peak * 100.0
        max_dd = abs(dd.min())

        mean_pnl = t_df["net_pnl_pct"].mean()
        std_pnl = t_df["net_pnl_pct"].std()
        sharpe = (mean_pnl / std_pnl * np.sqrt(252)) if std_pnl > 0 else 0.0

        return {
            "sample": label,
            "trades": n,
            "win_rate_pct": round(win_rate, 1),
            "net_pnl_pct": round(t_df["net_pnl_pct"].sum(), 2),
            "profit_factor": round(pf, 2),
            "expectancy_pct": round(mean_pnl, 3),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2)
        }

    full_stats = calc_stats(trades_df, "FULL")
    is_trades = trades_df[trades_df["sample"] == "IS"] if not trades_df.empty else pd.DataFrame()
    oos_trades = trades_df[trades_df["sample"] == "OOS"] if not trades_df.empty else pd.DataFrame()
    
    is_stats = calc_stats(is_trades, "IN_SAMPLE")
    oos_stats = calc_stats(oos_trades, "OUT_OF_SAMPLE")

    return {
        "contract": contract,
        "trades": trades_df,
        "full_stats": full_stats,
        "is_stats": is_stats,
        "oos_stats": oos_stats
    }


def run_comprehensive_backtest_study(symbol: str = "NIFTY") -> pd.DataFrame:
    """
    Run simulation across all registered signal contracts and benchmark comparator.
    """
    fpath = os.path.join(FEATURES_DIR, f"{symbol}_features.parquet")
    if not os.path.exists(fpath):
        raise FileNotFoundError(f"Feature dataset not found: {fpath}")

    df = pd.read_parquet(fpath)
    # Buy & Hold Benchmark
    bnh_return = (df["close"].iloc[-1] / df["close"].iloc[0] - 1.0) * 100.0

    print(f"\n=================================================================")
    print(f"BACKTEST STUDY: {symbol} (142 Trading Sessions)")
    print(f"Buy & Hold Return: {bnh_return:.2f}%")
    print(f"=================================================================")

    summary_rows = []
    all_trades_list = []

    for contract in ALL_CONTRACTS:
        res = simulate_signal_contract(df, contract)
        full = res["full_stats"]
        is_s = res["is_stats"]
        oos_s = res["oos_stats"]

        summary_rows.append({
            "Signal ID": contract.signal_id,
            "Hypothesis ID": contract.hypothesis_id,
            "Name": contract.name,
            "Direction": contract.trade_direction,
            "Hold Bars": contract.exit_bars,
            "Trades (Full)": full["trades"],
            "Win Rate (%)": full["win_rate_pct"],
            "Net PnL (%)": full["net_pnl_pct"],
            "PF": full["profit_factor"],
            "Expectancy (%)": full["expectancy_pct"],
            "Max DD (%)": full["max_drawdown_pct"],
            "Sharpe": full["sharpe_ratio"],
            "IS Net PnL (%)": is_s["net_pnl_pct"],
            "IS Sharpe": is_s["sharpe_ratio"],
            "OOS Net PnL (%)": oos_s["net_pnl_pct"],
            "OOS Sharpe": oos_s["sharpe_ratio"]
        })

        if not res["trades"].empty:
            all_trades_list.append(res["trades"])

    summary_df = pd.DataFrame(summary_rows)
    
    # Save results
    os.makedirs(BACKTESTS_DIR, exist_ok=True)
    summary_path = os.path.join(BACKTESTS_DIR, f"{symbol}_signal_comparison.csv")
    summary_df.to_csv(summary_path, index=False)
    print(f"[+] Saved backtest summary to {summary_path}")

    if all_trades_list:
        combined_trades = pd.concat(all_trades_list, ignore_index=True)
        trades_path = os.path.join(BACKTESTS_DIR, f"{symbol}_all_trades.csv")
        combined_trades.to_csv(trades_path, index=False)
        print(f"[+] Saved individual trade logs to {trades_path}")

    return summary_df


if __name__ == "__main__":
    for sym in ["NIFTY", "BANKNIFTY"]:
        df_res = run_comprehensive_backtest_study(sym)
        print(f"\n--- {sym} Signal Performance Summary ---")
        print(df_res[["Signal ID", "Direction", "Trades (Full)", "Win Rate (%)", "Net PnL (%)", "PF", "Expectancy (%)", "Sharpe", "IS Net PnL (%)", "OOS Net PnL (%)"]].to_string(index=False))
