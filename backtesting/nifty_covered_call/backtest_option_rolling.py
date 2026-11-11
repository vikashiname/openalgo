#!/usr/bin/env python3
"""
================================================================================
NIFTY Dynamic Option Management & Rolling Engine Backtest
Location: backtesting/nifty_covered_call/backtest_option_rolling.py
================================================================================
Compares 5 models across 32 monthly NIFTY expiry cycles (2022-2024):
  1. NON_ROLLING_BASELINE:
     - Full exit when DTE <= 10 or Call hits 3.0x SL or 90% decay
  2. CALENDAR_ROLL_ONLY:
     - At DTE <= 10: Roll short call to next month if Spot > 100-EMA; Keep Future running!
  3. ROLL_UP_AND_OUT (Rally Defense):
     - When Call reaches 3.0x SL in bull run, roll up & out instead of killing the winning future!
  4. FULL_ROLLING_COVERED_CALL:
     - Calendar roll + Roll Up & Out + Early Decay Harvest (at 85% decay)
  5. INSTITUTIONAL_ROLLING_COLLAR:
     - Full rolling engine on a Collar (Long Future + Short 0.25 Call + Long 0.07 Put)
================================================================================
"""

import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from scipy.stats import norm

LOT_SIZE = 50
RISK_FREE_RATE = 0.07
DEFAULT_SIGMA = 0.14


def calculate_bs_call_price(spot: float, strike: float, dte: int, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    if dte <= 0:
        return max(0.0, spot - strike)
    t = dte / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    price = spot * norm.cdf(d1) - strike * np.exp(-r * t) * norm.cdf(d2)
    return max(0.05, float(price))


def calculate_bs_call_delta(spot: float, strike: float, dte: int, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    if dte <= 0:
        return 1.0 if spot > strike else 0.0
    t = dte / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    return float(norm.cdf(d1))


def find_call_strike(spot: float, dte: int, target_delta: float = 0.25, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    t = max(1, dte) / 365.0
    target_d1 = norm.ppf(target_delta)
    approx_strike = spot / np.exp(target_d1 * sigma * np.sqrt(t) - (r + 0.5 * sigma ** 2) * t)
    return round(approx_strike / 50.0) * 50.0


def calculate_bs_put_price(spot: float, strike: float, dte: int, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    if dte <= 0:
        return max(0.0, strike - spot)
    t = dte / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    price = strike * np.exp(-r * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)
    return max(0.05, float(price))


def find_put_strike(spot: float, dte: int, target_delta_abs: float = 0.07, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    t = max(1, dte) / 365.0
    d1 = -norm.ppf(target_delta_abs)
    approx_strike = spot * np.exp(-(d1 * sigma * np.sqrt(t) - (r + 0.5 * sigma ** 2) * t))
    return round(approx_strike / 50.0) * 50.0


@dataclass
class CampaignTrade:
    model_name: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_spot: float
    exit_spot: float
    holding_days: int
    fut_pnl: float
    realized_opt_pnl: float
    final_unrealized_opt_pnl: float
    total_opt_pnl: float
    net_pnl: float
    roll_count: int
    exit_reason: str
    roll_history: List[str] = field(default_factory=list)


def run_rolling_backtest(df: pd.DataFrame, model_type: str = "non_rolling") -> List[CampaignTrade]:
    df = df.copy().reset_index(drop=True)
    df["ema_100"] = df["close"].ewm(span=100, adjust=False).mean()

    expiries = sorted(df["active_expiry"].unique())
    next_exp_map = {exp: (expiries[i + 1] if i + 1 < len(expiries) else exp) for i, exp in enumerate(expiries)}

    trades: List[CampaignTrade] = []
    in_position = False
    campaign: Dict[str, Any] = {}

    for i in range(100, len(df)):
        row = df.iloc[i]
        date = row["trade_date"]
        spot = row["close"]
        ema100 = row["ema_100"]
        active_exp = row["active_expiry"]
        active_dte = int(row["active_dte"])
        sub_exp = next_exp_map[active_exp]
        sub_dte = (sub_exp - date).days

        if not in_position:
            # Entry condition: Spot > 100-EMA and DTE in 22..35
            if spot > ema100 and 22 <= active_dte <= 35:
                c_strike = find_call_strike(spot, active_dte, target_delta=0.25)
                c_price = calculate_bs_call_price(spot, c_strike, active_dte)

                p_strike = None
                p_price = 0.0
                if "collar" in model_type:
                    p_strike = find_put_strike(spot, active_dte, target_delta_abs=0.07)
                    p_price = calculate_bs_put_price(spot, p_strike, active_dte)

                campaign = {
                    "entry_date": date,
                    "entry_spot": spot,
                    "active_call_strike": c_strike,
                    "active_call_price": c_price,
                    "active_call_expiry": active_exp,
                    "active_call_target": c_price * 0.15,  # 85% decay
                    "active_call_sl": c_price * 3.0,      # 3.0x premium
                    "active_put_strike": p_strike,
                    "active_put_price": p_price,
                    "active_put_expiry": active_exp if p_strike else None,
                    "realized_opt_pnl": 0.0,
                    "roll_count": 0,
                    "roll_history": [],
                    "peak_net_m2m": 0.0,
                }
                in_position = True
            continue

        # Position monitoring
        call_dte = max(0, (campaign["active_call_expiry"] - date).days)
        curr_call_px = calculate_bs_call_price(spot, campaign["active_call_strike"], call_dte)

        curr_put_px = 0.0
        if campaign["active_put_strike"] is not None:
            put_dte = max(0, (campaign["active_put_expiry"] - date).days)
            curr_put_px = calculate_bs_put_price(spot, campaign["active_put_strike"], put_dte)

        # M2M components
        fut_pnl = (spot - campaign["entry_spot"]) * LOT_SIZE
        call_unrealized = (campaign["active_call_price"] - curr_call_px) * LOT_SIZE
        put_unrealized = (curr_put_px - campaign["active_put_price"]) * LOT_SIZE if campaign["active_put_strike"] else 0.0
        
        net_m2m = fut_pnl + campaign["realized_opt_pnl"] + call_unrealized + put_unrealized
        campaign["peak_net_m2m"] = max(campaign["peak_net_m2m"], net_m2m)

        # ----------------------------------------------------------------------
        # MODEL 1: NON_ROLLING (Current Architecture Baseline)
        # ----------------------------------------------------------------------
        if model_type == "non_rolling":
            exit_triggered = False
            exit_reason = ""

            if curr_call_px >= campaign["active_call_sl"]:
                exit_triggered = True
                exit_reason = "CALL_STOP_LOSS_HIT (3.0x Premium)"
            elif curr_call_px <= campaign["active_call_target"]:
                exit_triggered = True
                exit_reason = "PROFIT_TARGET_HIT (85% Decay)" if net_m2m > 0 else "BEARISH_DECAY_CLOSE"
            elif call_dte <= 10 or date >= campaign["active_call_expiry"]:
                exit_triggered = True
                exit_reason = "ROLL_THRESHOLD_REACHED (DTE <= 10)"
            elif spot < ema100:
                exit_triggered = True
                exit_reason = "TREND_FILTER_EXIT (Spot < 100-EMA)"

            if exit_triggered:
                holding_days = (date - campaign["entry_date"]).days
                trades.append(CampaignTrade(
                    model_name=model_type,
                    entry_date=campaign["entry_date"],
                    exit_date=date,
                    entry_spot=campaign["entry_spot"],
                    exit_spot=spot,
                    holding_days=holding_days,
                    fut_pnl=fut_pnl,
                    realized_opt_pnl=0.0,
                    final_unrealized_opt_pnl=call_unrealized + put_unrealized,
                    total_opt_pnl=call_unrealized + put_unrealized,
                    net_pnl=net_m2m,
                    roll_count=0,
                    exit_reason=exit_reason,
                    roll_history=[],
                ))
                in_position = False
            continue

        # ----------------------------------------------------------------------
        # ACTIVE ROLLING ENGINES (Models 2, 3, 4, 5)
        # ----------------------------------------------------------------------
        campaign_exit = False
        campaign_exit_reason = ""

        # Priority 1: Trend Breakdown -> Full Campaign Exit
        if spot < ema100:
            campaign_exit = True
            campaign_exit_reason = "TREND_BREAKDOWN (Spot < 100-EMA)"

        # Priority 2: Catastrophe Net Drawdown Cap (-₹20k)
        elif net_m2m <= -20000.0:
            campaign_exit = True
            campaign_exit_reason = "MAX_NET_DD_BREACHED (-₹20k Cap)"

        # Priority 3: Trailing Profit Lock (+₹25k peak, trail 40%)
        elif campaign["peak_net_m2m"] >= 25000.0 and net_m2m <= (campaign["peak_net_m2m"] * 0.60):
            campaign_exit = True
            campaign_exit_reason = f"TRAILING_PROFIT_TRIGGERED (Peak: ₹{campaign['peak_net_m2m']:,.0f})"

        # If no campaign exit, check rolling triggers
        else:
            can_roll_rally = ("up_and_out" in model_type or "full" in model_type or "collar" in model_type)
            can_harvest_decay = ("harvest" in model_type or "full" in model_type or "collar" in model_type)

            # Trigger A: Call SL Hit during strong rally (Roll Up & Out)
            if can_roll_rally and curr_call_px >= campaign["active_call_sl"]:
                # Book loss on call, roll up and out to next month
                realized_call = (campaign["active_call_price"] - curr_call_px) * LOT_SIZE
                campaign["realized_opt_pnl"] += realized_call
                campaign["roll_count"] += 1
                
                # Pick next expiry contract
                roll_exp = sub_exp if sub_dte > 15 else expiries[min(len(expiries) - 1, expiries.index(sub_exp) + 1)]
                roll_dte = max(15, (roll_exp - date).days)
                
                new_c_strike = find_call_strike(spot, roll_dte, target_delta=0.25)
                new_c_price = calculate_bs_call_price(spot, new_c_strike, roll_dte)
                
                campaign["roll_history"].append(
                    f"RALLY_ROLL @ {date.date()}: Closed CE {campaign['active_call_strike']} (PnL: ₹{realized_call:,.0f}), "
                    f"Opened CE {new_c_strike} (Exp: {roll_exp.date()}, DTE: {roll_dte}, Prem: ₹{new_c_price:.1f})"
                )
                campaign["active_call_strike"] = new_c_strike
                campaign["active_call_price"] = new_c_price
                campaign["active_call_expiry"] = roll_exp
                campaign["active_call_target"] = new_c_price * 0.15
                campaign["active_call_sl"] = new_c_price * 3.0

            # Trigger B: Early Decay Harvest (85% decay captured with > 10 DTE remaining)
            elif can_harvest_decay and curr_call_px <= campaign["active_call_target"] and call_dte > 10:
                realized_call = (campaign["active_call_price"] - curr_call_px) * LOT_SIZE
                campaign["realized_opt_pnl"] += realized_call
                campaign["roll_count"] += 1
                
                # Re-load short call for remaining DTE
                new_c_strike = find_call_strike(spot, call_dte, target_delta=0.25)
                new_c_price = calculate_bs_call_price(spot, new_c_strike, call_dte)
                
                campaign["roll_history"].append(
                    f"DECAY_HARVEST @ {date.date()}: Booked CE {campaign['active_call_strike']} (+₹{realized_call:,.0f}), "
                    f"Re-loaded CE {new_c_strike} (DTE: {call_dte}, Prem: ₹{new_c_price:.1f})"
                )
                campaign["active_call_strike"] = new_c_strike
                campaign["active_call_price"] = new_c_price
                campaign["active_call_target"] = new_c_price * 0.15
                campaign["active_call_sl"] = new_c_price * 3.0

            # Trigger C: Calendar Expiry Roll (DTE <= 10 or date >= active_call_expiry)
            elif call_dte <= 10 or date >= campaign["active_call_expiry"]:
                realized_call = (campaign["active_call_price"] - curr_call_px) * LOT_SIZE
                campaign["realized_opt_pnl"] += realized_call
                
                realized_put = 0.0
                new_p_strike = None
                new_p_price = 0.0
                if campaign["active_put_strike"] is not None:
                    realized_put = (curr_put_px - campaign["active_put_price"]) * LOT_SIZE
                    campaign["realized_opt_pnl"] += realized_put

                campaign["roll_count"] += 1
                roll_exp = sub_exp if sub_dte > 15 else expiries[min(len(expiries) - 1, expiries.index(sub_exp) + 1)]
                roll_dte = max(15, (roll_exp - date).days)

                new_c_strike = find_call_strike(spot, roll_dte, target_delta=0.25)
                new_c_price = calculate_bs_call_price(spot, new_c_strike, roll_dte)

                if campaign["active_put_strike"] is not None:
                    new_p_strike = find_put_strike(spot, roll_dte, target_delta_abs=0.07)
                    new_p_price = calculate_bs_put_price(spot, new_p_strike, roll_dte)

                campaign["roll_history"].append(
                    f"CALENDAR_ROLL @ {date.date()}: Rolled CE to {new_c_strike} & PE to {new_p_strike} (Exp: {roll_exp.date()}, DTE: {roll_dte})"
                )
                campaign["active_call_strike"] = new_c_strike
                campaign["active_call_price"] = new_c_price
                campaign["active_call_expiry"] = roll_exp
                campaign["active_call_target"] = new_c_price * 0.15
                campaign["active_call_sl"] = new_c_price * 3.0

                if new_p_strike is not None:
                    campaign["active_put_strike"] = new_p_strike
                    campaign["active_put_price"] = new_p_price
                    campaign["active_put_expiry"] = roll_exp

        # Check if campaign terminated
        if campaign_exit:
            holding_days = (date - campaign["entry_date"]).days
            trades.append(CampaignTrade(
                model_name=model_type,
                entry_date=campaign["entry_date"],
                exit_date=date,
                entry_spot=campaign["entry_spot"],
                exit_spot=spot,
                holding_days=holding_days,
                fut_pnl=fut_pnl,
                realized_opt_pnl=campaign["realized_opt_pnl"],
                final_unrealized_opt_pnl=call_unrealized + put_unrealized,
                total_opt_pnl=campaign["realized_opt_pnl"] + call_unrealized + put_unrealized,
                net_pnl=net_m2m,
                roll_count=campaign["roll_count"],
                exit_reason=campaign_exit_reason,
                roll_history=campaign["roll_history"],
            ))
            in_position = False

    return trades


def compute_metrics(trades: List[CampaignTrade]) -> Dict[str, Any]:
    if not trades:
        return {}

    pnls = [t.net_pnl for t in trades]
    total_pnl = sum(pnls)
    n_trades = len(trades)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / n_trades) * 100.0 if n_trades > 0 else 0.0

    total_wins = sum(wins)
    total_losses = abs(sum(losses))
    profit_factor = (total_wins / total_losses) if total_losses > 0 else (999.0 if total_wins > 0 else 0.0)

    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    drawdowns = peak - equity
    max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    pnl_series = pd.Series(pnls)
    mean_pnl = pnl_series.mean()
    std_pnl = pnl_series.std() if len(pnls) > 1 else 1.0
    downside_std = pnl_series[pnl_series < 0].std() if len(losses) > 1 else 1.0

    trades_per_year = max(1.0, (n_trades / 2.5))
    sharpe = (mean_pnl / std_pnl) * np.sqrt(trades_per_year) if std_pnl > 0 else 0.0
    sortino = (mean_pnl / downside_std) * np.sqrt(trades_per_year) if downside_std > 0 else 0.0
    calmar = (total_pnl / max_drawdown) if max_drawdown > 0 else 0.0

    total_rolls = sum(t.roll_count for t in trades)
    fut_total = sum(t.fut_pnl for t in trades)
    opt_total = sum(t.total_opt_pnl for t in trades)

    return {
        "Total Net P&L (₹)": round(total_pnl, 2),
        "Futures P&L (₹)": round(fut_total, 2),
        "Options P&L (₹)": round(opt_total, 2),
        "Campaigns": n_trades,
        "Total Rolls": total_rolls,
        "Win Rate (%)": round(win_rate, 2),
        "Profit Factor": round(profit_factor, 2),
        "Max Drawdown (₹)": round(max_drawdown, 2),
        "Sharpe Ratio": round(sharpe, 2),
        "Sortino Ratio": round(sortino, 2),
        "Calmar Ratio": round(calmar, 2),
        "Average Campaign (₹)": round(mean_pnl, 2),
        "Largest Win (₹)": round(max(pnls), 2) if pnls else 0.0,
        "Largest Loss (₹)": round(min(pnls), 2) if pnls else 0.0,
        "Avg Holding (Days)": round(float(np.mean([t.holding_days for t in trades])), 1),
    }


def main():
    data_path = Path("backtesting/oi/data/normalized/NIFTY_continuous.parquet")
    if not data_path.exists():
        print(f"Error: {data_path} not found.")
        sys.exit(1)

    df = pd.read_parquet(data_path)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["active_expiry"] = pd.to_datetime(df["active_expiry"])
    df = df.sort_values("trade_date").reset_index(drop=True)

    print("=" * 85)
    print("      QUANTITATIVE EVALUATION: DYNAMIC OPTION MANAGEMENT & ROLLING")
    print("=" * 85)

    models = {
        "1. Non-Rolling (Baseline)": "non_rolling",
        "2. Calendar Roll Only": "calendar_roll",
        "3. Roll Up & Out (Rally Def)": "calendar_roll_up_and_out",
        "4. Full Rolling Covered Call": "full_rolling",
        "5. Institutional Rolling Collar": "collar_full_rolling",
    }

    results = {}
    all_campaigns = []

    for label, m_type in models.items():
        campaigns = run_rolling_backtest(df, model_type=m_type)
        results[label] = compute_metrics(campaigns)
        for c in campaigns:
            all_campaigns.append({
                "model_label": label,
                "model_type": c.model_name,
                "entry_date": c.entry_date,
                "exit_date": c.exit_date,
                "holding_days": c.holding_days,
                "fut_pnl": c.fut_pnl,
                "total_opt_pnl": c.total_opt_pnl,
                "net_pnl": c.net_pnl,
                "roll_count": c.roll_count,
                "exit_reason": c.exit_reason,
                "num_rolls_executed": len(c.roll_history),
            })

    summary_df = pd.DataFrame(results).T
    print("\n--- PERFORMANCE SUMMARY MATRIX ---\n")
    print(summary_df[["Total Net P&L (₹)", "Futures P&L (₹)", "Options P&L (₹)", "Total Rolls", "Win Rate (%)", "Profit Factor", "Max Drawdown (₹)", "Sharpe Ratio"]].to_string())

    out_dir = Path("backtesting/nifty_covered_call")
    summary_df.to_csv(out_dir / "option_rolling_comparison_metrics.csv")
    pd.DataFrame(all_campaigns).to_csv(out_dir / "trades_option_rolling_comparison.csv", index=False)

    print(f"\n[✓] Results successfully exported to {out_dir}/:")
    print("    - option_rolling_comparison_metrics.csv")
    print("    - trades_option_rolling_comparison.csv")


if __name__ == "__main__":
    main()
