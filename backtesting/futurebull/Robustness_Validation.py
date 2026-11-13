#!/usr/bin/env python3
"""
================================================================================
PHASE 7: ROBUSTNESS & WALK-FORWARD OUT-OF-SAMPLE VALIDATION
================================================================================
Directory   : backtesting/futurebull/
Role        : Rigorous statistical robustness testing:
                - Chronological In-Sample (2021-2023) vs Out-of-Sample (2024-2026)
                - Friction Stress-Testing (0.5x, 1.0x, 1.5x, 2.0x)
                - Holding Horizon Robustness (5d, 10d, 20d) across regimes
Outputs:
  - reports/PHASE7_WALK_FORWARD_VALIDATION.csv
  - reports/PHASE7_FRICTION_SENSITIVITY.csv
  - reports/PHASE7_OOS_HOLDING_COMPARISON.csv
================================================================================
"""

import sys
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from scanner_engine import compute_all_filters
from Futures_Strategy_Backtest import compute_signals_for_variants, calculate_friction

DATA_DIR = CURRENT_DIR / "data"
REPORTS_DIR = CURRENT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def simulate_trades_custom(
    symbol_dfs: Dict[str, pd.DataFrame],
    signal_col: str,
    max_holding_days: int = 20,
    stop_loss_pct: float = 3.0,
    profit_target_pct: float = 8.0,
    friction_multiplier: float = 1.0,
    start_year: int = 2021,
    end_year: int = 2026,
    position_capital: float = 200000.0,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    trades = []

    for symbol, df in symbol_dfs.items():
        in_trade = False
        entry_price = 0.0
        entry_idx = 0
        entry_date = None
        stop_loss = 0.0
        target = 0.0

        length = len(df)
        dates = df.index
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        signals = df[signal_col].values

        for i in range(length - 1):
            curr_date = dates[i]
            if curr_date.year < start_year or curr_date.year > end_year:
                continue

            if not in_trade:
                if signals[i]:
                    entry_idx = i + 1
                    entry_date = dates[entry_idx]
                    entry_price = opens[entry_idx]
                    if entry_price <= 0 or np.isnan(entry_price):
                        continue
                    in_trade = True
                    stop_loss = entry_price * (1.0 - stop_loss_pct / 100.0) if stop_loss_pct else 0.0
                    target = entry_price * (1.0 + profit_target_pct / 100.0) if profit_target_pct else float("inf")
            else:
                curr = i
                h = highs[curr]
                l = lows[curr]
                c = closes[curr]
                dt = dates[curr]
                holding = curr - entry_idx + 1

                exit_price = None
                exit_reason = None

                if stop_loss_pct and l <= stop_loss:
                    exit_price = stop_loss
                    exit_reason = "STOP_LOSS"
                elif profit_target_pct and h >= target:
                    exit_price = target
                    exit_reason = "PROFIT_TARGET"
                elif holding >= max_holding_days:
                    exit_price = c
                    exit_reason = f"TIME_EXIT_{max_holding_days}D"

                if exit_reason:
                    shares = max(1, int(position_capital / entry_price))
                    buy_v = shares * entry_price
                    sell_v = shares * exit_price
                    gross = sell_v - buy_v
                    friction = calculate_friction(buy_v, sell_v) * friction_multiplier
                    net = gross - friction
                    ret_pct = (net / buy_v) * 100.0

                    trades.append({
                        "symbol": symbol,
                        "entry_date": entry_date,
                        "exit_date": dt,
                        "year": entry_date.year,
                        "holding_days": holding,
                        "net_pnl": round(net, 2),
                        "return_pct": round(ret_pct, 2),
                        "exit_reason": exit_reason
                    })
                    in_trade = False

    t_df = pd.DataFrame(trades)
    if t_df.empty:
        return t_df, {"total_trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0, "expectancy_pct": 0.0, "sharpe_ratio": 0.0}

    wins = t_df[t_df["net_pnl"] > 0]
    losses = t_df[t_df["net_pnl"] <= 0]
    win_rate = (len(wins) / len(t_df)) * 100.0
    pf = (wins["net_pnl"].sum() / abs(losses["net_pnl"].sum())) if len(losses) > 0 else 0.0
    exp = t_df["return_pct"].mean()
    sharpe = (t_df["return_pct"].mean() / t_df["return_pct"].std() * np.sqrt(252)) if t_df["return_pct"].std() > 0 else 0.0

    stats = {
        "total_trades": len(t_df),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(pf, 2),
        "expectancy_pct": round(exp, 2),
        "total_net_pnl_inr": round(t_df["net_pnl"].sum(), 2),
        "sharpe_ratio": round(sharpe, 2)
    }
    return t_df, stats


def run_phase7_robustness():
    print("================================================================================")
    print("🔬 RUNNING PHASE 7: WALK-FORWARD & ROBUSTNESS VALIDATION")
    print("================================================================================")

    data_files = sorted(list(DATA_DIR.glob("*.parquet")))
    symbol_dfs = {}
    for f in data_files:
        df = pd.read_parquet(f)
        symbol_dfs[f.stem] = compute_signals_for_variants(df)

    # 1. Walk-Forward In-Sample (2021-2023) vs Out-of-Sample (2024-2026)
    wf_results = []
    variants = [
        ("1_Original_Scanner", "SIG_ORIGINAL"),
        ("2_Optimised_Scanner", "SIG_OPTIMISED"),
        ("3_Simplified_Scanner", "SIG_SIMPLIFIED"),
    ]

    for v_name, sig_col in variants:
        _, is_stats = simulate_trades_custom(symbol_dfs, sig_col, max_holding_days=15, stop_loss_pct=3.0, profit_target_pct=6.0, start_year=2021, end_year=2023)
        _, oos_stats = simulate_trades_custom(symbol_dfs, sig_col, max_holding_days=15, stop_loss_pct=3.0, profit_target_pct=6.0, start_year=2024, end_year=2026)

        wf_results.append({
            "variant": v_name,
            "is_trades": is_stats["total_trades"],
            "is_win_rate_pct": is_stats["win_rate_pct"],
            "is_profit_factor": is_stats["profit_factor"],
            "is_expectancy_pct": is_stats["expectancy_pct"],
            "is_sharpe": is_stats["sharpe_ratio"],
            "oos_trades": oos_stats["total_trades"],
            "oos_win_rate_pct": oos_stats["win_rate_pct"],
            "oos_profit_factor": oos_stats["profit_factor"],
            "oos_expectancy_pct": oos_stats["expectancy_pct"],
            "oos_sharpe": oos_stats["sharpe_ratio"],
            "robustness_score": round(oos_stats["profit_factor"] / is_stats["profit_factor"], 2) if is_stats["profit_factor"] > 0 else 0.0
        })

    wf_df = pd.DataFrame(wf_results)
    wf_out = REPORTS_DIR / "PHASE7_WALK_FORWARD_VALIDATION.csv"
    wf_df.to_csv(wf_out, index=False)
    print(f"✓ Exported walk-forward validation to: {wf_out}")

    # 2. Friction Sensitivity Test (0.5x, 1.0x, 1.5x, 2.0x) on Optimised Scanner
    fric_results = []
    for mult in [0.5, 1.0, 1.5, 2.0]:
        _, f_stats = simulate_trades_custom(symbol_dfs, "SIG_OPTIMISED", max_holding_days=15, stop_loss_pct=3.0, profit_target_pct=6.0, friction_multiplier=mult)
        fric_results.append({
            "friction_scenario": f"{mult}x Statutory Friction",
            "friction_multiplier": mult,
            "total_trades": f_stats["total_trades"],
            "win_rate_pct": f_stats["win_rate_pct"],
            "profit_factor": f_stats["profit_factor"],
            "expectancy_pct": f_stats["expectancy_pct"],
            "total_net_pnl_inr": f_stats["total_net_pnl_inr"],
            "sharpe_ratio": f_stats["sharpe_ratio"]
        })

    fric_df = pd.DataFrame(fric_results)
    fric_out = REPORTS_DIR / "PHASE7_FRICTION_SENSITIVITY.csv"
    fric_df.to_csv(fric_out, index=False)
    print(f"✓ Exported friction sensitivity to: {fric_out}")

    # 3. Holding Period Horizon Comparison (5d, 10d, 15d, 20d)
    hold_results = []
    for hold in [5, 10, 15, 20]:
        _, h_stats = simulate_trades_custom(symbol_dfs, "SIG_OPTIMISED", max_holding_days=hold, stop_loss_pct=3.0, profit_target_pct=6.0)
        hold_results.append({
            "holding_period_days": hold,
            "total_trades": h_stats["total_trades"],
            "win_rate_pct": h_stats["win_rate_pct"],
            "profit_factor": h_stats["profit_factor"],
            "expectancy_pct": h_stats["expectancy_pct"],
            "total_net_pnl_inr": h_stats["total_net_pnl_inr"],
            "sharpe_ratio": h_stats["sharpe_ratio"]
        })

    hold_df = pd.DataFrame(hold_results)
    hold_out = REPORTS_DIR / "PHASE7_OOS_HOLDING_COMPARISON.csv"
    hold_df.to_csv(hold_out, index=False)
    print(f"✓ Exported holding horizon comparison to: {hold_out}")

    print("\n--------------------------------------------------------------------------------")
    print("🏆 WALK-FORWARD VALIDATION (IN-SAMPLE 2021-2023 vs OUT-OF-SAMPLE 2024-2026):")
    print("--------------------------------------------------------------------------------")
    for _, r in wf_df.iterrows():
        print(f"  {r['variant']:<26} | IS PF: {r['is_profit_factor']:>4.2f} (Exp: {r['is_expectancy_pct']:>+5.2f}%) | OOS PF: {r['oos_profit_factor']:>4.2f} (Exp: {r['oos_expectancy_pct']:>+5.2f}%) | Robustness: {r['robustness_score']:.2f}")

    print("\n--------------------------------------------------------------------------------")
    print("🛡️ FRICTION SENSITIVITY (OPTIMISED SCANNER):")
    print("--------------------------------------------------------------------------------")
    for _, r in fric_df.iterrows():
        print(f"  {r['friction_scenario']:<26} | PF: {r['profit_factor']:>4.2f} | Expectancy: {r['expectancy_pct']:>+5.2f}% | Net PnL: ₹{r['total_net_pnl_inr']:>10,.0f} | Sharpe: {r['sharpe_ratio']:>+5.2f}")
    print("================================================================================\n")


if __name__ == "__main__":
    run_phase7_robustness()
