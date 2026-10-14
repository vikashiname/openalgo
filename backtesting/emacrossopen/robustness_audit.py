"""
Symbol Robustness & Temporal Walk-Forward Analysis
File: backtesting/emacrossopen/robustness_audit.py

Tests candidate models across:
  1. All 33 individual symbols (distribution of win rate, expectancy, PF)
  2. Yearly & Quarterly sub-periods
  3. Directional breakdown (LONG vs SHORT)
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

from data_manager import load_or_download_all_data
from feature_extractor import extract_trades_and_features
from target_sl_engine import simulate_trade_path, calculate_portfolio_metrics

def run_robustness_audit():
    data = load_or_download_all_data()
    trades, _ = extract_trades_and_features(data)

    models_to_test = [
        ("Baseline (Reversal Only)", None, None, None),
        ("Target +3.00% (Reversal Exit)", 3.00, None, None),
        ("Target +2.00% (Reversal Exit)", 2.00, None, None),
        ("Target 3.0x ATR (Reversal Exit)", None, None, 3.00),
        ("Target 2.5x ATR (Reversal Exit)", None, None, 2.50),
    ]

    print("=" * 80)
    print("1. ROBUSTNESS ACROSS SYMBOLS (33 NFO INSTRUMENTS)")
    print("=" * 80)

    symbols = sorted(list(set(t["symbol"] for t in trades)))
    symbol_rows = []

    for sym in symbols:
        sym_trades = [t for t in trades if t["symbol"] == sym]
        if not sym_trades:
            continue

        row = {"Symbol": sym, "Sector": sym_trades[0]["sector"], "Trades": len(sym_trades)}

        for name, tp_pct, sl_pct, tp_atr in models_to_test:
            if tp_pct is not None:
                sim = [simulate_trade_path(t, tp_pct=tp_pct, sl_pct=sl_pct) for t in sym_trades]
            elif tp_atr is not None:
                sim = [simulate_trade_path(t, tp_atr_mult=tp_atr, sl_atr_mult=None) for t in sym_trades]
            else:
                sim = [simulate_trade_path(t, tp_pct=None, sl_pct=None) for t in sym_trades]

            m = calculate_portfolio_metrics(sim)
            short_name = name.split("(")[0].strip()
            row[f"{short_name}_Exp"] = m["expectancy_pct"]
            row[f"{short_name}_PF"] = m["profit_factor"]
            row[f"{short_name}_WR"] = m["win_rate_pct"]

        symbol_rows.append(row)

    sym_df = pd.DataFrame(symbol_rows)
    sym_path = Path(__file__).resolve().parent / "research_symbol_robustness.csv"
    sym_df.to_csv(sym_path, index=False)
    print(f"Saved symbol robustness table to {sym_path}")

    # Summary stats across symbols
    print("\nSymbol Level Summary Stats:")
    for name, _, _, _ in models_to_test:
        short_name = name.split("(")[0].strip()
        exp_col = f"{short_name}_Exp"
        pf_col = f"{short_name}_PF"
        pos_symbols = (sym_df[exp_col] > 0).mean() * 100.0
        avg_sym_exp = sym_df[exp_col].mean()
        std_sym_exp = sym_df[exp_col].std()
        print(f"  {short_name:<30}: Profitable Symbols: {pos_symbols:.1f}% | Avg Exp: {avg_sym_exp:+.3f}% (Std: {std_sym_exp:.3f})")

    # 2. TEMPORAL ROBUSTNESS ACROSS PERIODS
    print("\n" + "=" * 80)
    print("2. TEMPORAL ROBUSTNESS ACROSS TIME PERIODS (YEARLY & HALF-YEARLY)")
    print("=" * 80)

    # Add period tags to trades
    for t in trades:
        ts = pd.to_datetime(t["entry_time"])
        t["period_year"] = str(ts.year)
        t["period_hy"] = f"{ts.year}-H1" if ts.month <= 6 else f"{ts.year}-H2"

    periods = sorted(list(set(t["period_hy"] for t in trades)))
    period_rows = []

    for per in periods:
        per_trades = [t for t in trades if t["period_hy"] == per]
        row = {"Period": per, "Trades": len(per_trades)}

        for name, tp_pct, sl_pct, tp_atr in models_to_test:
            if tp_pct is not None:
                sim = [simulate_trade_path(t, tp_pct=tp_pct, sl_pct=sl_pct) for t in per_trades]
            elif tp_atr is not None:
                sim = [simulate_trade_path(t, tp_atr_mult=tp_atr, sl_atr_mult=None) for t in per_trades]
            else:
                sim = [simulate_trade_path(t, tp_pct=None, sl_pct=None) for t in per_trades]

            m = calculate_portfolio_metrics(sim)
            short_name = name.split("(")[0].strip()
            row[f"{short_name}_Exp"] = m["expectancy_pct"]
            row[f"{short_name}_PF"] = m["profit_factor"]
            row[f"{short_name}_WR"] = m["win_rate_pct"]
            row[f"{short_name}_TotRet"] = m["total_return_pct"]

        period_rows.append(row)

    per_df = pd.DataFrame(period_rows)
    per_path = Path(__file__).resolve().parent / "research_period_robustness.csv"
    per_df.to_csv(per_path, index=False)
    print(per_df.to_string(index=False))

    # 3. DIRECTIONAL ROBUSTNESS (LONG vs SHORT)
    print("\n" + "=" * 80)
    print("3. DIRECTIONAL BREAKDOWN (LONG vs SHORT)")
    print("=" * 80)

    dir_rows = []
    for d in ["LONG", "SHORT"]:
        d_trades = [t for t in trades if t["direction"] == d]
        row = {"Direction": d, "Trades": len(d_trades)}
        for name, tp_pct, sl_pct, tp_atr in models_to_test:
            if tp_pct is not None:
                sim = [simulate_trade_path(t, tp_pct=tp_pct, sl_pct=sl_pct) for t in d_trades]
            elif tp_atr is not None:
                sim = [simulate_trade_path(t, tp_atr_mult=tp_atr, sl_atr_mult=None) for t in d_trades]
            else:
                sim = [simulate_trade_path(t, tp_pct=None, sl_pct=None) for t in d_trades]

            m = calculate_portfolio_metrics(sim)
            short_name = name.split("(")[0].strip()
            row[f"{short_name}_Exp"] = m["expectancy_pct"]
            row[f"{short_name}_PF"] = m["profit_factor"]
            row[f"{short_name}_WR"] = m["win_rate_pct"]
            row[f"{short_name}_TotRet"] = m["total_return_pct"]
        dir_rows.append(row)

    dir_df = pd.DataFrame(dir_rows)
    dir_path = Path(__file__).resolve().parent / "research_direction_robustness.csv"
    dir_df.to_csv(dir_path, index=False)
    print(dir_df.to_string(index=False))

if __name__ == "__main__":
    run_robustness_audit()
