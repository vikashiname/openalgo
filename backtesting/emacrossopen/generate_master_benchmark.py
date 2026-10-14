"""
Master Benchmark Generator
File: backtesting/emacrossopen/generate_master_benchmark.py

Produces the comprehensive master comparison table for all candidate models
against the V2-2 baseline across all requested metrics.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

from data_manager import load_or_download_all_data
from feature_extractor import extract_trades_and_features
from target_sl_engine import simulate_trade_path, calculate_portfolio_metrics

def generate_master_benchmark():
    data = load_or_download_all_data()
    trades, feat_df = extract_trades_and_features(data)

    is_mask = [t["sample"] == "IS" for t in trades]
    oos_mask = [t["sample"] == "OOS" for t in trades]

    # Model specifications to benchmark
    models = [
        {
            "id": "M0_BASELINE",
            "name": "Baseline V2-2 (Reversal Only)",
            "type": "Baseline",
            "long_tp_pct": None, "short_tp_pct": None,
            "long_tp_atr": None, "short_tp_atr": None,
            "sl_pct": None, "sl_atr": None,
        },
        {
            "id": "M1_FIXED_SYM_3PCT",
            "name": "Symmetric Fixed Target +3.00%",
            "type": "Fixed %",
            "long_tp_pct": 3.00, "short_tp_pct": 3.00,
            "long_tp_atr": None, "short_tp_atr": None,
            "sl_pct": None, "sl_atr": None,
        },
        {
            "id": "M2_ATR_SYM_3ATR",
            "name": "Symmetric ATR Target 3.00x ATR",
            "type": "ATR Dynamic",
            "long_tp_pct": None, "short_tp_pct": None,
            "long_tp_atr": 3.00, "short_tp_atr": 3.00,
            "sl_pct": None, "sl_atr": None,
        },
        {
            "id": "M3_ASYM_FIXED_3_2",
            "name": "Asymmetric Fixed: Long +3.0%, Short +2.0%",
            "type": "Asymmetric Fixed",
            "long_tp_pct": 3.00, "short_tp_pct": 2.00,
            "long_tp_atr": None, "short_tp_atr": None,
            "sl_pct": None, "sl_atr": None,
        },
        {
            "id": "M4_ASYM_FIXED_3_15",
            "name": "Asymmetric Fixed: Long +3.0%, Short +1.5%",
            "type": "Asymmetric Fixed",
            "long_tp_pct": 3.00, "short_tp_pct": 1.50,
            "long_tp_atr": None, "short_tp_atr": None,
            "sl_pct": None, "sl_atr": None,
        },
        {
            "id": "M5_ASYM_ATR_35_20",
            "name": "Asymmetric ATR: Long 3.5x ATR, Short 2.0x ATR",
            "type": "Asymmetric ATR",
            "long_tp_pct": None, "short_tp_pct": None,
            "long_tp_atr": 3.50, "short_tp_atr": 2.00,
            "sl_pct": None, "sl_atr": None,
        },
    ]

    master_rows = []

    symbols = sorted(list(set(t["symbol"] for t in trades)))

    for m in models:
        # Run simulation
        sim_trades = []
        for t in trades:
            d = t["direction"]
            tp_p = m["long_tp_pct"] if d == "LONG" else m["short_tp_pct"]
            tp_a = m["long_tp_atr"] if d == "LONG" else m["short_tp_atr"]
            res = simulate_trade_path(t, tp_pct=tp_p, tp_atr_mult=tp_a, sl_pct=m["sl_pct"], sl_atr_mult=m["sl_atr"])
            sim_trades.append(res)

        full_m = calculate_portfolio_metrics(sim_trades)
        is_m = calculate_portfolio_metrics([r for r, is_t in zip(sim_trades, is_mask) if is_t])
        oos_m = calculate_portfolio_metrics([r for r, oos_t in zip(sim_trades, oos_mask) if oos_t])

        # Directional breakdown
        long_res = [r for r, t in zip(sim_trades, trades) if t["direction"] == "LONG"]
        short_res = [r for r, t in zip(sim_trades, trades) if t["direction"] == "SHORT"]
        long_m = calculate_portfolio_metrics(long_res)
        short_m = calculate_portfolio_metrics(short_res)

        # Symbol level robustness (% profitable symbols)
        sym_exps = []
        for sym in symbols:
            sym_res = [r for r, t in zip(sim_trades, trades) if t["symbol"] == sym]
            if sym_res:
                sym_exps.append(calculate_portfolio_metrics(sym_res)["expectancy_pct"])
        pct_profitable_syms = (np.array(sym_exps) > 0).mean() * 100.0
        sym_exp_std = float(np.std(sym_exps))

        master_rows.append({
            "Model_ID": m["id"],
            "Model_Name": m["name"],
            "Architecture_Type": m["type"],
            "Trade_Count": full_m["trade_count"],
            "Total_Return_Pct": full_m["total_return_pct"],
            "Profit_Factor": full_m["profit_factor"],
            "Win_Rate_Pct": full_m["win_rate_pct"],
            "Expectancy_Pct": full_m["expectancy_pct"],
            "Max_Drawdown_Pct": full_m["max_drawdown_pct"],
            "Avg_R": full_m["avg_r"],
            "Avg_MFE_Pct": round(feat_df["mfe_pct"].mean(), 2),
            "Avg_MAE_Pct": round(feat_df["mae_pct"].mean(), 2),
            "Target_Hit_Pct": full_m["target_hit_pct"],
            "SL_Hit_Pct": full_m["sl_hit_pct"],
            "Reversal_Exit_Pct": full_m["reversal_exit_pct"],
            "Target_Before_SL_Pct": full_m["target_before_sl_pct"],
            "Profitable_Symbols_Pct": round(pct_profitable_syms, 1),
            "Symbol_Exp_Std": round(sym_exp_std, 3),
            "IS_Trades": is_m["trade_count"],
            "IS_Return_Pct": is_m["total_return_pct"],
            "IS_Expectancy_Pct": is_m["expectancy_pct"],
            "IS_Profit_Factor": is_m["profit_factor"],
            "IS_Win_Rate_Pct": is_m["win_rate_pct"],
            "OOS_Trades": oos_m["trade_count"],
            "OOS_Return_Pct": oos_m["total_return_pct"],
            "OOS_Expectancy_Pct": oos_m["expectancy_pct"],
            "OOS_Profit_Factor": oos_m["profit_factor"],
            "OOS_Win_Rate_Pct": oos_m["win_rate_pct"],
            "Long_Return_Pct": long_m["total_return_pct"],
            "Long_PF": long_m["profit_factor"],
            "Short_Return_Pct": short_m["total_return_pct"],
            "Short_PF": short_m["profit_factor"],
        })

    master_df = pd.DataFrame(master_rows)
    out_path = Path(__file__).resolve().parent / "research_master_benchmark.csv"
    master_df.to_csv(out_path, index=False)
    print(f"\nSaved master benchmark to {out_path}\n")
    print(master_df.to_string(index=False))

if __name__ == "__main__":
    generate_master_benchmark()
