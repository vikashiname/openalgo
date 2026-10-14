"""
Target & Stop-Loss Simulation Engine
File: backtesting/emacrossopen/target_sl_engine.py

Performs exhaustive path-dependent simulation of Target and Stop-Loss models
across all 2,143 historical V2-2 trades.
Evaluates Fixed %, ATR-based, Risk/Reward, Volatility-adjusted, and Strength-dependent models.
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from feature_extractor import extract_trades_and_features
from data_manager import load_or_download_all_data

# Transaction Friction in Indian NFO Futures (Brokerage + STT + Turnover + GST + Slippage)
FRICTION_PCT = 0.07  # 0.07% round trip

def simulate_trade_path(
    t: Dict[str, Any],
    tp_pct: Optional[float] = None,
    sl_pct: Optional[float] = None,
    tp_atr_mult: Optional[float] = None,
    sl_atr_mult: Optional[float] = None,
    friction: float = FRICTION_PCT,
) -> Dict[str, Any]:
    """
    Path-dependent candle-by-candle evaluation of a trade slice under TP/SL parameters.
    """
    direction = t["direction"]
    entry_px = t["entry_price"]
    entry_atr = t["entry_atr"]
    slice_df = t["slice_df"]
    n_bars = len(slice_df)

    # Determine absolute Target and SL prices
    target_px = None
    stop_px = None
    initial_risk_pct = 1.0

    if tp_pct is not None:
        target_px = entry_px * (1.0 + tp_pct / 100.0) if direction == "LONG" else entry_px * (1.0 - tp_pct / 100.0)
    elif tp_atr_mult is not None:
        target_px = entry_px + (tp_atr_mult * entry_atr) if direction == "LONG" else entry_px - (tp_atr_mult * entry_atr)

    if sl_pct is not None:
        stop_px = entry_px * (1.0 - sl_pct / 100.0) if direction == "LONG" else entry_px * (1.0 + sl_pct / 100.0)
        initial_risk_pct = sl_pct
    elif sl_atr_mult is not None:
        stop_px = entry_px - (sl_atr_mult * entry_atr) if direction == "LONG" else entry_px + (sl_atr_mult * entry_atr)
        initial_risk_pct = (sl_atr_mult * entry_atr / entry_px) * 100.0

    exit_px = None
    exit_reason = "REVERSAL"
    exit_bar = n_bars

    highs = slice_df["High"].values
    lows = slice_df["Low"].values
    opens = slice_df["Open"].values
    closes = slice_df["Close"].values

    for k in range(n_bars):
        h = highs[k]
        l = lows[k]
        o = opens[k]
        c = closes[k]

        if direction == "LONG":
            tp_hit = (target_px is not None) and (h >= target_px)
            sl_hit = (stop_px is not None) and (l <= stop_px)

            if tp_hit and sl_hit:
                # Same-candle conflict resolution
                if o >= target_px:
                    exit_px = o
                    exit_reason = "TARGET"
                elif o <= stop_px:
                    exit_px = o
                    exit_reason = "STOP_LOSS"
                else:
                    # Conservative: assume SL hit first
                    exit_px = stop_px
                    exit_reason = "STOP_LOSS"
                exit_bar = k + 1
                break
            elif tp_hit:
                exit_px = target_px
                exit_reason = "TARGET"
                exit_bar = k + 1
                break
            elif sl_hit:
                exit_px = stop_px
                exit_reason = "STOP_LOSS"
                exit_bar = k + 1
                break
        else: # SHORT
            tp_hit = (target_px is not None) and (l <= target_px)
            sl_hit = (stop_px is not None) and (h >= stop_px)

            if tp_hit and sl_hit:
                if o <= target_px:
                    exit_px = o
                    exit_reason = "TARGET"
                elif o >= stop_px:
                    exit_px = o
                    exit_reason = "STOP_LOSS"
                else:
                    exit_px = stop_px
                    exit_reason = "STOP_LOSS"
                exit_bar = k + 1
                break
            elif tp_hit:
                exit_px = target_px
                exit_reason = "TARGET"
                exit_bar = k + 1
                break
            elif sl_hit:
                exit_px = stop_px
                exit_reason = "STOP_LOSS"
                exit_bar = k + 1
                break

    # If neither TP nor SL triggered, exit on reversal at the last candle
    if exit_px is None:
        exit_px = closes[-1]
        exit_reason = "REVERSAL"
        exit_bar = n_bars

    dir_mult = 1.0 if direction == "LONG" else -1.0
    raw_pnl_pct = ((exit_px - entry_px) / entry_px) * 100.0 * dir_mult
    net_pnl_pct = raw_pnl_pct - friction
    r_multiple = net_pnl_pct / max(initial_risk_pct, 0.1)

    return {
        "exit_price": exit_px,
        "exit_reason": exit_reason,
        "exit_bar": exit_bar,
        "raw_pnl_pct": raw_pnl_pct,
        "net_pnl_pct": net_pnl_pct,
        "r_multiple": r_multiple,
        "is_win": net_pnl_pct > 0,
        "is_target": exit_reason == "TARGET",
        "is_sl": exit_reason == "STOP_LOSS",
        "is_reversal": exit_reason == "REVERSAL",
    }

def calculate_portfolio_metrics(trade_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes full quantitative performance metrics for a backtest run."""
    if not trade_results:
        return {}

    n = len(trade_results)
    pnls = np.array([r["net_pnl_pct"] for r in trade_results])
    r_mults = np.array([r["r_multiple"] for r in trade_results])
    
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / n) * 100.0 if n > 0 else 0.0

    gross_win = float(np.sum(wins)) if len(wins) > 0 else 0.0
    gross_loss = float(abs(np.sum(losses))) if len(losses) > 0 else 0.0

    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    else:
        profit_factor = 99.0 if gross_win > 0 else 1.0

    avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_loss = float(abs(np.mean(losses))) if len(losses) > 0 else 0.0
    expectancy = float(np.mean(pnls))
    total_return = float(np.sum(pnls))
    avg_r = float(np.mean(r_mults))

    # Target & SL hit rates
    target_hits = sum(1 for r in trade_results if r["is_target"])
    sl_hits = sum(1 for r in trade_results if r["is_sl"])
    reversal_exits = sum(1 for r in trade_results if r["is_reversal"])

    target_hit_pct = (target_hits / n) * 100.0 if n > 0 else 0.0
    sl_hit_pct = (sl_hits / n) * 100.0 if n > 0 else 0.0
    reversal_pct = (reversal_exits / n) * 100.0 if n > 0 else 0.0

    # Target-before-SL probability (among trades that resolved via Target or SL)
    resolved_count = target_hits + sl_hits
    target_before_sl_pct = (target_hits / resolved_count * 100.0) if resolved_count > 0 else 0.0

    # Max Drawdown calculation on cumulative equity curve
    equity_curve = np.cumsum(pnls)
    running_max = np.maximum.accumulate(equity_curve)
    drawdowns = running_max - equity_curve
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Average bars held
    avg_bars = float(np.mean([r["exit_bar"] for r in trade_results]))

    return {
        "trade_count": n,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 3),
        "expectancy_pct": round(expectancy, 4),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "avg_r": round(avg_r, 3),
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "target_hit_pct": round(target_hit_pct, 2),
        "sl_hit_pct": round(sl_hit_pct, 2),
        "reversal_exit_pct": round(reversal_pct, 2),
        "target_before_sl_pct": round(target_before_sl_pct, 2),
        "avg_bars_held": round(avg_bars, 1),
    }

def run_grid_simulations(trades: List[Dict[str, Any]]):
    """
    Executes simulations across:
      1. Baseline (reversal-only)
      2. Fixed % Target/SL Grid
      3. ATR-based Target/SL Grid
      4. Risk/Reward Grid
      5. Volatility-Adjusted Model
      6. Strength-Dependent Dynamic Model
    Evaluates In-Sample, Out-of-Sample, and Full Dataset.
    """
    print("=" * 80)
    print("RUNNING TARGET & STOP-LOSS SIMULATION ENGINE")
    print(f"Total Evaluated Trades: {len(trades)}")
    print("=" * 80)

    # 1. BASELINE EVALUATION (Reversal-Only)
    base_results = [simulate_trade_path(t, tp_pct=None, sl_pct=None) for t in trades]
    base_metrics_full = calculate_portfolio_metrics(base_results)

    is_mask = [t["sample"] == "IS" for t in trades]
    oos_mask = [t["sample"] == "OOS" for t in trades]

    base_is = calculate_portfolio_metrics([r for r, is_t in zip(base_results, is_mask) if is_t])
    base_oos = calculate_portfolio_metrics([r for r, oos_t in zip(base_results, oos_mask) if oos_t])

    print("\n--- BASELINE V2-2 (REVERSAL-ONLY) PERFORMANCE ---")
    print(f"Full Dataset : Trades={base_metrics_full['trade_count']}, WR={base_metrics_full['win_rate_pct']}%, PF={base_metrics_full['profit_factor']}, Exp={base_metrics_full['expectancy_pct']}%, TotRet={base_metrics_full['total_return_pct']}%, MaxDD={base_metrics_full['max_drawdown_pct']}%, AvgBars={base_metrics_full['avg_bars_held']}")
    print(f"In-Sample    : Trades={base_is['trade_count']}, WR={base_is['win_rate_pct']}%, PF={base_is['profit_factor']}, Exp={base_is['expectancy_pct']}%, TotRet={base_is['total_return_pct']}%, MaxDD={base_is['max_drawdown_pct']}%")
    print(f"Out-of-Sample: Trades={base_oos['trade_count']}, WR={base_oos['win_rate_pct']}%, PF={base_oos['profit_factor']}, Exp={base_oos['expectancy_pct']}%, TotRet={base_oos['total_return_pct']}%, MaxDD={base_oos['max_drawdown_pct']}%")

    # 2. FIXED PERCENTAGE GRID MATRIX
    target_pct_grid = [0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.50, 3.00, 3.50, 4.00]
    sl_pct_grid = [0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.50, 3.00, 3.50, 4.00]

    fixed_rows = []
    for tp in target_pct_grid:
        for sl in sl_pct_grid:
            sim_res = [simulate_trade_path(t, tp_pct=tp, sl_pct=sl) for t in trades]
            m_full = calculate_portfolio_metrics(sim_res)
            m_is = calculate_portfolio_metrics([r for r, is_t in zip(sim_res, is_mask) if is_t])
            m_oos = calculate_portfolio_metrics([r for r, oos_t in zip(sim_res, oos_mask) if oos_t])

            fixed_rows.append({
                "Model": "Fixed_Pct",
                "Target": f"+{tp:.2f}%",
                "Stop_Loss": f"-{sl:.2f}%",
                "Target_Val": tp,
                "SL_Val": sl,
                "PF_Full": m_full["profit_factor"],
                "Exp_Full": m_full["expectancy_pct"],
                "WR_Full": m_full["win_rate_pct"],
                "TotRet_Full": m_full["total_return_pct"],
                "MaxDD_Full": m_full["max_drawdown_pct"],
                "AvgR_Full": m_full["avg_r"],
                "Target_Hit_Pct": m_full["target_hit_pct"],
                "SL_Hit_Pct": m_full["sl_hit_pct"],
                "Reversal_Pct": m_full["reversal_exit_pct"],
                "Target_Before_SL_Pct": m_full["target_before_sl_pct"],
                "Avg_Bars": m_full["avg_bars_held"],
                "PF_IS": m_is["profit_factor"],
                "Exp_IS": m_is["expectancy_pct"],
                "WR_IS": m_is["win_rate_pct"],
                "TotRet_IS": m_is["total_return_pct"],
                "PF_OOS": m_oos["profit_factor"],
                "Exp_OOS": m_oos["expectancy_pct"],
                "WR_OOS": m_oos["win_rate_pct"],
                "TotRet_OOS": m_oos["total_return_pct"],
            })

    fixed_df = pd.DataFrame(fixed_rows)
    fixed_path = Path(__file__).resolve().parent / "research_fixed_grid.csv"
    fixed_df.to_csv(fixed_path, index=False)
    print(f"\nFixed % Grid complete ({len(fixed_df)} combinations). Saved to {fixed_path}")

    # 3. ATR-BASED DYNAMIC GRID MATRIX
    target_atr_grid = [0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.50, 3.00, 3.50, 4.00]
    sl_atr_grid = [0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.50, 3.00, 3.50]

    atr_rows = []
    for tp_mult in target_atr_grid:
        for sl_mult in sl_atr_grid:
            sim_res = [simulate_trade_path(t, tp_atr_mult=tp_mult, sl_atr_mult=sl_mult) for t in trades]
            m_full = calculate_portfolio_metrics(sim_res)
            m_is = calculate_portfolio_metrics([r for r, is_t in zip(sim_res, is_mask) if is_t])
            m_oos = calculate_portfolio_metrics([r for r, oos_t in zip(sim_res, oos_mask) if oos_t])

            atr_rows.append({
                "Model": "ATR_Dynamic",
                "Target": f"{tp_mult:.2f}x ATR",
                "Stop_Loss": f"{sl_mult:.2f}x ATR",
                "Target_Mult": tp_mult,
                "SL_Mult": sl_mult,
                "PF_Full": m_full["profit_factor"],
                "Exp_Full": m_full["expectancy_pct"],
                "WR_Full": m_full["win_rate_pct"],
                "TotRet_Full": m_full["total_return_pct"],
                "MaxDD_Full": m_full["max_drawdown_pct"],
                "AvgR_Full": m_full["avg_r"],
                "Target_Hit_Pct": m_full["target_hit_pct"],
                "SL_Hit_Pct": m_full["sl_hit_pct"],
                "Reversal_Pct": m_full["reversal_exit_pct"],
                "Target_Before_SL_Pct": m_full["target_before_sl_pct"],
                "Avg_Bars": m_full["avg_bars_held"],
                "PF_IS": m_is["profit_factor"],
                "Exp_IS": m_is["expectancy_pct"],
                "WR_IS": m_is["win_rate_pct"],
                "TotRet_IS": m_is["total_return_pct"],
                "PF_OOS": m_oos["profit_factor"],
                "Exp_OOS": m_oos["expectancy_pct"],
                "WR_OOS": m_oos["win_rate_pct"],
                "TotRet_OOS": m_oos["total_return_pct"],
            })

    atr_df = pd.DataFrame(atr_rows)
    atr_path = Path(__file__).resolve().parent / "research_atr_grid.csv"
    atr_df.to_csv(atr_path, index=False)
    print(f"ATR Dynamic Grid complete ({len(atr_df)} combinations). Saved to {atr_path}")

    # 4. RISK / REWARD MODEL EVALUATION
    # Base SL options: 1.0x ATR, 1.5x ATR, 2.0x ATR, and Fixed 1.5%
    rr_rows = []
    rr_ratios = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
    base_sl_configs = [
        ("1.00x ATR", None, 1.00),
        ("1.50x ATR", None, 1.50),
        ("2.00x ATR", None, 2.00),
        ("Fixed -1.50%", 1.50, None),
        ("Fixed -2.00%", 2.00, None),
    ]

    for label, sl_pct_val, sl_atr_val in base_sl_configs:
        for rr in rr_ratios:
            if sl_pct_val is not None:
                tp_pct_val = sl_pct_val * rr
                sim_res = [simulate_trade_path(t, tp_pct=tp_pct_val, sl_pct=sl_pct_val) for t in trades]
                tp_label = f"+{tp_pct_val:.2f}% (1:{rr:.2f} R:R)"
            else:
                tp_atr_val = sl_atr_val * rr
                sim_res = [simulate_trade_path(t, tp_atr_mult=tp_atr_val, sl_atr_mult=sl_atr_val) for t in trades]
                tp_label = f"{tp_atr_val:.2f}x ATR (1:{rr:.2f} R:R)"

            m_full = calculate_portfolio_metrics(sim_res)
            m_is = calculate_portfolio_metrics([r for r, is_t in zip(sim_res, is_mask) if is_t])
            m_oos = calculate_portfolio_metrics([r for r, oos_t in zip(sim_res, oos_mask) if oos_t])

            rr_rows.append({
                "Base_SL": label,
                "RR_Ratio": f"1:{rr:.2f}",
                "Target": tp_label,
                "PF_Full": m_full["profit_factor"],
                "Exp_Full": m_full["expectancy_pct"],
                "WR_Full": m_full["win_rate_pct"],
                "TotRet_Full": m_full["total_return_pct"],
                "MaxDD_Full": m_full["max_drawdown_pct"],
                "AvgR_Full": m_full["avg_r"],
                "Target_Before_SL_Pct": m_full["target_before_sl_pct"],
                "PF_IS": m_is["profit_factor"],
                "Exp_IS": m_is["expectancy_pct"],
                "PF_OOS": m_oos["profit_factor"],
                "Exp_OOS": m_oos["expectancy_pct"],
            })

    rr_df = pd.DataFrame(rr_rows)
    rr_path = Path(__file__).resolve().parent / "research_risk_reward.csv"
    rr_df.to_csv(rr_path, index=False)
    print(f"Risk/Reward models complete ({len(rr_df)} combinations). Saved to {rr_path}")

    # 5. VOLATILITY-ADJUSTED MODEL
    # Low Volatility (ATR% < 1.0%): tighter TP (1.5x ATR) / SL (1.5x ATR)
    # High Volatility (ATR% >= 1.8%): wider TP (2.5x ATR) / SL (2.0x ATR)
    # Normal Volatility: TP 2.0x ATR / SL 1.5x ATR
    vol_adjusted_results = []
    for t in trades:
        atr_p = t["entry_atr_pct"]
        if atr_p < 1.0:
            res = simulate_trade_path(t, tp_atr_mult=1.50, sl_atr_mult=1.25)
        elif atr_p >= 1.8:
            res = simulate_trade_path(t, tp_atr_mult=2.50, sl_atr_mult=2.00)
        else:
            res = simulate_trade_path(t, tp_atr_mult=2.00, sl_atr_mult=1.50)
        vol_adjusted_results.append(res)

    vol_m_full = calculate_portfolio_metrics(vol_adjusted_results)
    vol_m_is = calculate_portfolio_metrics([r for r, is_t in zip(vol_adjusted_results, is_mask) if is_t])
    vol_m_oos = calculate_portfolio_metrics([r for r, oos_t in zip(vol_adjusted_results, oos_mask) if oos_t])

    # 6. STRENGTH-DEPENDENT DYNAMIC MODEL
    # High Strength (Score >= 3): Wider Target (2.50x ATR), SL (1.75x ATR)
    # Moderate Strength (Score == 2): Standard Target (2.00x ATR), SL (1.50x ATR)
    # Low Strength (Score <= 1): Conservative Target (1.50x ATR), SL (1.50x ATR)
    strength_results = []
    for t in trades:
        score = t["f_strength_score"]
        if score >= 3:
            res = simulate_trade_path(t, tp_atr_mult=2.50, sl_atr_mult=1.75)
        elif score == 2:
            res = simulate_trade_path(t, tp_atr_mult=2.00, sl_atr_mult=1.50)
        else:
            res = simulate_trade_path(t, tp_atr_mult=1.50, sl_atr_mult=1.50)
        strength_results.append(res)

    str_m_full = calculate_portfolio_metrics(strength_results)
    str_m_is = calculate_portfolio_metrics([r for r, is_t in zip(strength_results, is_mask) if is_t])
    str_m_oos = calculate_portfolio_metrics([r for r, oos_t in zip(strength_results, oos_mask) if oos_t])

    # 7. COMPARATIVE SUMMARY TABLE
    # Select Top Models from each family
    top_fixed = fixed_df.sort_values(by="Exp_OOS", ascending=False).iloc[0]
    top_fixed_pf = fixed_df.sort_values(by="PF_OOS", ascending=False).iloc[0]

    top_atr = atr_df.sort_values(by="Exp_OOS", ascending=False).iloc[0]
    top_atr_pf = atr_df.sort_values(by="PF_OOS", ascending=False).iloc[0]

    top_rr = rr_df.sort_values(by="Exp_OOS", ascending=False).iloc[0]

    summary_rows = [
        {
            "Model_Architecture": "0. Baseline V2-2 (Reversal-Only)",
            "Target": "None",
            "Stop_Loss": "None",
            "Full_WR_Pct": base_metrics_full["win_rate_pct"],
            "Full_PF": base_metrics_full["profit_factor"],
            "Full_Exp_Pct": base_metrics_full["expectancy_pct"],
            "Full_TotRet_Pct": base_metrics_full["total_return_pct"],
            "Full_MaxDD_Pct": base_metrics_full["max_drawdown_pct"],
            "Full_Avg_R": base_metrics_full["avg_r"],
            "IS_Exp_Pct": base_is["expectancy_pct"],
            "IS_PF": base_is["profit_factor"],
            "OOS_Exp_Pct": base_oos["expectancy_pct"],
            "OOS_PF": base_oos["profit_factor"],
            "Avg_Bars_Held": base_metrics_full["avg_bars_held"],
        },
        {
            "Model_Architecture": f"1. Top Fixed % (Best OOS Exp)",
            "Target": top_fixed["Target"],
            "Stop_Loss": top_fixed["Stop_Loss"],
            "Full_WR_Pct": top_fixed["WR_Full"],
            "Full_PF": top_fixed["PF_Full"],
            "Full_Exp_Pct": top_fixed["Exp_Full"],
            "Full_TotRet_Pct": top_fixed["TotRet_Full"],
            "Full_MaxDD_Pct": top_fixed["MaxDD_Full"],
            "Full_Avg_R": top_fixed["AvgR_Full"],
            "IS_Exp_Pct": top_fixed["Exp_IS"],
            "IS_PF": top_fixed["PF_IS"],
            "OOS_Exp_Pct": top_fixed["Exp_OOS"],
            "OOS_PF": top_fixed["PF_OOS"],
            "Avg_Bars_Held": top_fixed["Avg_Bars"],
        },
        {
            "Model_Architecture": f"2. Top ATR Dynamic (Best OOS Exp)",
            "Target": top_atr["Target"],
            "Stop_Loss": top_atr["Stop_Loss"],
            "Full_WR_Pct": top_atr["WR_Full"],
            "Full_PF": top_atr["PF_Full"],
            "Full_Exp_Pct": top_atr["Exp_Full"],
            "Full_TotRet_Pct": top_atr["TotRet_Full"],
            "Full_MaxDD_Pct": top_atr["MaxDD_Full"],
            "Full_Avg_R": top_atr["AvgR_Full"],
            "IS_Exp_Pct": top_atr["Exp_IS"],
            "IS_PF": top_atr["PF_IS"],
            "OOS_Exp_Pct": top_atr["Exp_OOS"],
            "OOS_PF": top_atr["PF_OOS"],
            "Avg_Bars_Held": top_atr["Avg_Bars"],
        },
        {
            "Model_Architecture": f"3. Top ATR Dynamic (Best OOS PF)",
            "Target": top_atr_pf["Target"],
            "Stop_Loss": top_atr_pf["Stop_Loss"],
            "Full_WR_Pct": top_atr_pf["WR_Full"],
            "Full_PF": top_atr_pf["PF_Full"],
            "Full_Exp_Pct": top_atr_pf["Exp_Full"],
            "Full_TotRet_Pct": top_atr_pf["TotRet_Full"],
            "Full_MaxDD_Pct": top_atr_pf["MaxDD_Full"],
            "Full_Avg_R": top_atr_pf["AvgR_Full"],
            "IS_Exp_Pct": top_atr_pf["Exp_IS"],
            "IS_PF": top_atr_pf["PF_IS"],
            "OOS_Exp_Pct": top_atr_pf["Exp_OOS"],
            "OOS_PF": top_atr_pf["PF_OOS"],
            "Avg_Bars_Held": top_atr_pf["Avg_Bars"],
        },
        {
            "Model_Architecture": f"4. Top Risk/Reward (Best OOS Exp)",
            "Target": top_rr["Target"],
            "Stop_Loss": top_rr["Base_SL"],
            "Full_WR_Pct": top_rr["WR_Full"],
            "Full_PF": top_rr["PF_Full"],
            "Full_Exp_Pct": top_rr["Exp_Full"],
            "Full_TotRet_Pct": top_rr["TotRet_Full"],
            "Full_MaxDD_Pct": top_rr["MaxDD_Full"],
            "Full_Avg_R": top_rr["AvgR_Full"],
            "IS_Exp_Pct": top_rr["Exp_IS"],
            "IS_PF": top_rr["PF_IS"],
            "OOS_Exp_Pct": top_rr["Exp_OOS"],
            "OOS_PF": top_rr["PF_OOS"],
            "Avg_Bars_Held": "-",
        },
        {
            "Model_Architecture": "5. Volatility-Regime Adjusted",
            "Target": "Dynamic (1.5x-2.5x ATR)",
            "Stop_Loss": "Dynamic (1.25x-2.0x ATR)",
            "Full_WR_Pct": vol_m_full["win_rate_pct"],
            "Full_PF": vol_m_full["profit_factor"],
            "Full_Exp_Pct": vol_m_full["expectancy_pct"],
            "Full_TotRet_Pct": vol_m_full["total_return_pct"],
            "Full_MaxDD_Pct": vol_m_full["max_drawdown_pct"],
            "Full_Avg_R": vol_m_full["avg_r"],
            "IS_Exp_Pct": vol_m_is["expectancy_pct"],
            "IS_PF": vol_m_is["profit_factor"],
            "OOS_Exp_Pct": vol_m_oos["expectancy_pct"],
            "OOS_PF": vol_m_oos["profit_factor"],
            "Avg_Bars_Held": vol_m_full["avg_bars_held"],
        },
        {
            "Model_Architecture": "6. Strength-Dependent Dynamic",
            "Target": "Adaptive (1.5x-2.5x ATR)",
            "Stop_Loss": "Adaptive (1.5x-1.75x ATR)",
            "Full_WR_Pct": str_m_full["win_rate_pct"],
            "Full_PF": str_m_full["profit_factor"],
            "Full_Exp_Pct": str_m_full["expectancy_pct"],
            "Full_TotRet_Pct": str_m_full["total_return_pct"],
            "Full_MaxDD_Pct": str_m_full["max_drawdown_pct"],
            "Full_Avg_R": str_m_full["avg_r"],
            "IS_Exp_Pct": str_m_is["expectancy_pct"],
            "IS_PF": str_m_is["profit_factor"],
            "OOS_Exp_Pct": str_m_oos["expectancy_pct"],
            "OOS_PF": str_m_oos["profit_factor"],
            "Avg_Bars_Held": str_m_full["avg_bars_held"],
        },
    ]

    summary_df = pd.DataFrame(summary_rows)
    summary_path = Path(__file__).resolve().parent / "research_candidate_models_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print("\n" + "=" * 80)
    print("MASTER CANDIDATE MODELS COMPARISON TABLE")
    print("=" * 80)
    print(summary_df.to_string(index=False))

    return summary_df

if __name__ == "__main__":
    data = load_or_download_all_data()
    trades, _ = extract_trades_and_features(data)
    run_grid_simulations(trades)
