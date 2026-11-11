#!/usr/bin/env python3
"""
================================================================================
NIFTY Covered Call: Isolated Research Audit & Risk Control Verification
Location: backtesting/nifty_covered_call/research_audit_runner.py
================================================================================
Implements rigorous, isolated testing:
  1. Baseline Exact Audit & Replication
  2. Transaction Costs & Friction Integration (STT, Exchange, GST, Stamp, Slippage)
  3. Benchmark Comparison (Buy & Hold NIFTY)
  4. Minimum DTE Entry Filter Evaluation (15-day minimum vs alternatives)
  5. Isolated Risk Control Evaluation:
     - Control 1: Futures Catastrophe Stop (-2.0%)
     - Control 2: Combined Position M2M Loss Cap (-₹20,000)
     - Control 3: Trend Breakdown Exit (Close < 100-EMA)
     - Control 4: High-Water-Mark Trailing Exit (Peak >= ₹15k, 40% buffer)
     - Control 5: Combined Multi-Barrier Model
================================================================================
"""

import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from scipy.stats import norm

# Standard NIFTY parameters
LOT_SIZE = 50
RISK_FREE_RATE = 0.07
DEFAULT_SIGMA = 0.14

# Indian F&O Transaction Cost Model (Standard Institutional Rates)
# Futures: Brokerage ₹20, STT 0.02% on Sell, Exch 0.0019%, Stamp 0.002% on Buy, GST 18%, Slippage 1.0 pt
# Options: Brokerage ₹20, STT 0.10% on Sell Premium, Exch 0.05% Premium, Stamp 0.003% on Buy, GST 18%, Slippage 0.5 pt

def calculate_transaction_costs(
    fut_entry: float,
    fut_exit: float,
    opt_entry: float,
    opt_exit: float,
    lot_size: int = LOT_SIZE,
    fut_slippage_pts: float = 1.0,
    opt_slippage_pts: float = 0.5,
) -> Dict[str, float]:
    """Calculate granular regulatory taxes, brokerage, and execution slippage."""
    # 1. Futures Turnovers
    fut_buy_val = (fut_entry + fut_slippage_pts) * lot_size
    fut_sell_val = (fut_exit - fut_slippage_pts) * lot_size
    
    # 2. Options Turnovers (Premium Turnover)
    opt_sell_val = (opt_entry - opt_slippage_pts) * lot_size
    opt_buy_val = (opt_exit + opt_slippage_pts) * lot_size
    
    # 3. Slippage Cost
    fut_slippage_cost = (2 * fut_slippage_pts) * lot_size
    opt_slippage_cost = (2 * opt_slippage_pts) * lot_size
    total_slippage = fut_slippage_cost + opt_slippage_cost
    
    # 4. Brokerage (₹20 per order * 4 orders)
    brokerage = 20.0 * 4.0
    
    # 5. STT (Securities Transaction Tax)
    # 0.02% on futures sell turnover
    stt_fut = fut_sell_val * 0.0002
    # 0.10% on options sell premium turnover (entry is sell)
    stt_opt = opt_sell_val * 0.0010
    total_stt = stt_fut + stt_opt
    
    # 6. Exchange Turnover Charges
    exch_fut = (fut_buy_val + fut_sell_val) * 0.000019
    exch_opt = (opt_sell_val + opt_buy_val) * 0.00050
    total_exch = exch_fut + exch_opt
    
    # 7. Stamp Duty (Buy side only: 0.002% on Fut, 0.003% on Opt)
    stamp_fut = fut_buy_val * 0.00002
    stamp_opt = opt_buy_val * 0.00003
    total_stamp = stamp_fut + stamp_opt
    
    # 8. SEBI Turnover Charges (0.0001% of total turnover)
    sebi = (fut_buy_val + fut_sell_val + opt_sell_val + opt_buy_val) * 0.000001
    
    # 9. GST (18% on Brokerage + Exchange + SEBI)
    gst = (brokerage + total_exch + sebi) * 0.18
    
    total_fees_taxes = brokerage + total_stt + total_exch + total_stamp + sebi + gst
    total_cost = total_fees_taxes + total_slippage
    
    return {
        "brokerage": brokerage,
        "stt": total_stt,
        "exchange_fees": total_exch,
        "stamp_duty": total_stamp,
        "gst": gst,
        "slippage": total_slippage,
        "total_cost": total_cost,
    }


def calculate_bs_call_price(spot: float, strike: float, dte: int, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    """Calculate Black-Scholes Call Option Price."""
    if dte <= 0:
        return max(0.0, spot - strike)
    t = dte / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    price = spot * norm.cdf(d1) - strike * np.exp(-r * t) * norm.cdf(d2)
    return max(0.05, float(price))


def calculate_bs_call_delta(spot: float, strike: float, dte: int, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    """Calculate Black-Scholes Call Delta."""
    if dte <= 0:
        return 1.0 if spot > strike else 0.0
    t = dte / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    return float(norm.cdf(d1))


def find_target_strike(spot: float, dte: int, target_delta: float = 0.30, r: float = RISK_FREE_RATE, sigma: float = DEFAULT_SIGMA) -> float:
    """Find the strike closest to the target delta (rounded to nearest 50)."""
    t = max(1, dte) / 365.0
    target_d1 = norm.ppf(target_delta)
    approx_strike = spot / np.exp(target_d1 * sigma * np.sqrt(t) - (r + 0.5 * sigma ** 2) * t)
    return round(approx_strike / 50.0) * 50.0


@dataclass
class TradeRecord:
    variant: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    expiry_date: pd.Timestamp
    entry_spot: float
    exit_spot: float
    strike: float
    call_entry_price: float
    call_exit_price: float
    dte_entry: int
    dte_exit: int
    fut_gross_pnl: float
    call_gross_pnl: float
    net_gross_pnl: float
    transaction_costs: float
    net_pnl: float
    exit_reason: str
    holding_days: int
    peak_net_m2m: float
    trough_net_m2m: float
    is_downside_false_target: bool


def simulate_strategy(
    df: pd.DataFrame,
    variant_name: str,
    min_dte_entry: int = 22,
    max_dte_entry: int = 35,
    fut_stop_pct: Optional[float] = None,
    m2m_cap_inr: Optional[float] = None,
    trend_exit: bool = False,
    trail_active_threshold: Optional[float] = None,
    trail_pullback_pct: Optional[float] = None,
    apply_costs: bool = True,
) -> List[TradeRecord]:
    """
    Simulate covered call trading cycle-by-cycle across the dataset with configurable risk controls.
    """
    df = df.copy().reset_index(drop=True)
    df["ema_100"] = df["close"].ewm(span=100, adjust=False).mean()

    trades: List[TradeRecord] = []
    in_position = False
    pos: Dict[str, Any] = {}

    for i in range(100, len(df)):
        row = df.iloc[i]
        date = row["trade_date"]
        spot = row["close"]
        ema100 = row["ema_100"]
        dte = int(row["active_dte"])
        expiry = row["active_expiry"]

        if not in_position:
            # Entry condition:
            # 1. Spot > 100-EMA (Trend Filter)
            # 2. DTE within configured entry window
            if spot > ema100 and (min_dte_entry <= dte <= max_dte_entry):
                strike = find_target_strike(spot, dte, target_delta=0.30)
                call_price = calculate_bs_call_price(spot, strike, dte)
                
                pos = {
                    "entry_date": date,
                    "expiry_date": expiry,
                    "entry_spot": spot,
                    "strike": strike,
                    "call_entry_price": call_price,
                    "target_price": call_price * 0.10,   # 90% decay
                    "stoploss_price": call_price * 3.0,  # 3.0x premium
                    "dte_entry": dte,
                    "entry_index": i,
                    "peak_net_m2m": 0.0,
                    "trough_net_m2m": 0.0,
                }
                in_position = True
            continue

        # Position monitoring
        curr_dte = max(0, dte)
        curr_call_price = calculate_bs_call_price(spot, pos["strike"], curr_dte)
        
        # M2M calculation
        fut_pnl = (spot - pos["entry_spot"]) * LOT_SIZE
        call_pnl = (pos["call_entry_price"] - curr_call_price) * LOT_SIZE
        net_m2m = fut_pnl + call_pnl
        fut_return_pct = (spot - pos["entry_spot"]) / pos["entry_spot"]
        
        pos["peak_net_m2m"] = max(pos["peak_net_m2m"], net_m2m)
        pos["trough_net_m2m"] = min(pos["trough_net_m2m"], net_m2m)

        exit_triggered = False
        exit_reason = ""

        # Risk Control 1: Futures Catastrophe Stop-Loss
        if fut_stop_pct is not None and fut_return_pct <= -fut_stop_pct:
            exit_triggered = True
            exit_reason = f"FUTURES_STOP_LOSS_HIT ({fut_return_pct*100:.2f}%)"

        # Risk Control 2: Combined Strategy M2M Loss Cap
        elif m2m_cap_inr is not None and net_m2m <= -m2m_cap_inr:
            exit_triggered = True
            exit_reason = f"MAX_M2M_LOSS_CAP_BREACHED (-₹{m2m_cap_inr:,.0f})"

        # Risk Control 3: Dynamic Trend Breakdown Exit (Close < 100-EMA)
        elif trend_exit and spot < ema100:
            exit_triggered = True
            exit_reason = f"TREND_BREAKDOWN_EXIT (Spot < 100-EMA)"

        # Risk Control 4: High-Water-Mark Trailing Exit
        elif (
            trail_active_threshold is not None
            and trail_pullback_pct is not None
            and pos["peak_net_m2m"] >= trail_active_threshold
            and net_m2m <= (pos["peak_net_m2m"] * (1.0 - trail_pullback_pct))
        ):
            exit_triggered = True
            exit_reason = f"TRAILING_PROFIT_TRIGGERED (Peak: ₹{pos['peak_net_m2m']:,.0f})"

        # Standard Covered Call Core Rules:
        # Call Profit Target (90% decay)
        elif curr_call_price <= pos["target_price"]:
            exit_triggered = True
            exit_reason = "PROFIT_TARGET_HIT (90% Decay)"

        # Call Stop Loss (3.0x premium multiplier)
        elif curr_call_price >= pos["stoploss_price"]:
            exit_triggered = True
            exit_reason = "STOP_LOSS_HIT (3.0x Premium)"

        # Roll Threshold (DTE <= 10 or reached expiry)
        elif curr_dte <= 10 or date >= pos["expiry_date"]:
            exit_triggered = True
            exit_reason = "ROLL_THRESHOLD_REACHED (DTE <= 10)"

        if exit_triggered:
            holding_days = (date - pos["entry_date"]).days
            
            # Detect Downside False Target Trap
            is_downside_trap = (
                "PROFIT_TARGET_HIT" in exit_reason
                and net_m2m < 0
            )
            
            # Transaction costs
            if apply_costs:
                costs_dict = calculate_transaction_costs(
                    fut_entry=pos["entry_spot"],
                    fut_exit=spot,
                    opt_entry=pos["call_entry_price"],
                    opt_exit=curr_call_price,
                    lot_size=LOT_SIZE,
                )
                tx_cost = costs_dict["total_cost"]
            else:
                tx_cost = 0.0

            net_pnl_after_cost = net_m2m - tx_cost

            trades.append(TradeRecord(
                variant=variant_name,
                entry_date=pos["entry_date"],
                exit_date=date,
                expiry_date=pos["expiry_date"],
                entry_spot=pos["entry_spot"],
                exit_spot=spot,
                strike=pos["strike"],
                call_entry_price=pos["call_entry_price"],
                call_exit_price=curr_call_price,
                dte_entry=pos["dte_entry"],
                dte_exit=curr_dte,
                fut_gross_pnl=fut_pnl,
                call_gross_pnl=call_pnl,
                net_gross_pnl=net_m2m,
                transaction_costs=tx_cost,
                net_pnl=net_pnl_after_cost,
                exit_reason=exit_reason,
                holding_days=holding_days,
                peak_net_m2m=pos["peak_net_m2m"],
                trough_net_m2m=pos["trough_net_m2m"],
                is_downside_false_target=is_downside_trap,
            ))
            in_position = False

    return trades


def compute_comprehensive_metrics(trades: List[TradeRecord], df_daily: pd.DataFrame) -> Dict[str, Any]:
    """Calculate thorough portfolio and trade metrics."""
    if not trades:
        return {}

    pnls = [t.net_pnl for t in trades]
    gross_pnls = [t.net_gross_pnl for t in trades]
    fut_pnls = [t.fut_gross_pnl for t in trades]
    call_pnls = [t.call_gross_pnl for t in trades]
    costs = [t.transaction_costs for t in trades]

    total_net_pnl = sum(pnls)
    total_gross_pnl = sum(gross_pnls)
    total_costs = sum(costs)
    total_fut_pnl = sum(fut_pnls)
    total_call_pnl = sum(call_pnls)

    n_trades = len(trades)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / n_trades) * 100.0 if n_trades > 0 else 0.0

    total_wins = sum(wins)
    total_losses = abs(sum(losses))
    profit_factor = (total_wins / total_losses) if total_losses > 0 else (999.0 if total_wins > 0 else 0.0)

    # Max Drawdown based on closed trades equity curve
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    drawdowns = peak - equity
    max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Max Intra-Trade Unrealized Trough Drawdown
    worst_intra_trade_trough = min([t.trough_net_m2m for t in trades]) if trades else 0.0

    # Annualization (avg 12 trades / year)
    pnl_series = pd.Series(pnls)
    mean_pnl = pnl_series.mean()
    std_pnl = pnl_series.std() if len(pnls) > 1 else 1.0
    downside_std = pnl_series[pnl_series < 0].std() if len(losses) > 1 else 1.0

    trades_per_year = 12.0
    sharpe = (mean_pnl / std_pnl) * np.sqrt(trades_per_year) if std_pnl > 0 else 0.0
    sortino = (mean_pnl / downside_std) * np.sqrt(trades_per_year) if downside_std > 0 else 0.0
    calmar = (total_net_pnl / max_drawdown) if max_drawdown > 0 else 0.0

    # Count of Downside False Profit Targets
    false_targets = sum([1 for t in trades if t.is_downside_false_target])

    return {
        "Total Trades": n_trades,
        "Win Rate (%)": round(win_rate, 2),
        "Profit Factor": round(profit_factor, 2),
        "Total Gross P&L (₹)": round(total_gross_pnl, 2),
        "Total Costs (₹)": round(total_costs, 2),
        "Total Net P&L (₹)": round(total_net_pnl, 2),
        "Futures Leg P&L (₹)": round(total_fut_pnl, 2),
        "Option Leg P&L (₹)": round(total_call_pnl, 2),
        "Max Closed DD (₹)": round(max_drawdown, 2),
        "Worst Intra Trough (₹)": round(worst_intra_trade_trough, 2),
        "Sharpe Ratio": round(sharpe, 2),
        "Sortino Ratio": round(sortino, 2),
        "Calmar Ratio": round(calmar, 2),
        "Avg Trade (₹)": round(mean_pnl, 2),
        "Largest Win (₹)": round(max(pnls) if pnls else 0.0, 2),
        "Largest Loss (₹)": round(min(pnls) if pnls else 0.0, 2),
        "Avg Holding (Days)": round(float(np.mean([t.holding_days for t in trades])), 1),
        "False Profit Targets": false_targets,
    }


def compute_benchmark(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute Buy & Hold NIFTY Spot Benchmark over the exact trading window."""
    df_window = df.iloc[100:].reset_index(drop=True)
    start_spot = df_window.iloc[0]["close"]
    end_spot = df_window.iloc[-1]["close"]
    pnl = (end_spot - start_spot) * LOT_SIZE
    ret_pct = ((end_spot - start_spot) / start_spot) * 100.0
    
    # Peak & Drawdown
    spots = df_window["close"].values
    spot_pnls = (spots - start_spot) * LOT_SIZE
    peak = np.maximum.accumulate(spot_pnls)
    dd = peak - spot_pnls
    max_dd = float(np.max(dd))
    
    return {
        "Start Date": str(df_window.iloc[0]["trade_date"].date()),
        "End Date": str(df_window.iloc[-1]["trade_date"].date()),
        "Start Spot": start_spot,
        "End Spot": end_spot,
        "B&H Net P&L (₹)": round(pnl, 2),
        "B&H Return (%)": round(ret_pct, 2),
        "B&H Max DD (₹)": round(max_dd, 2),
    }


def run_all_experiments() -> None:
    data_path = Path("backtesting/oi/data/normalized/NIFTY_continuous.parquet")
    if not data_path.exists():
        print(f"Error: {data_path} not found.")
        sys.exit(1)

    df = pd.read_parquet(data_path)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["active_expiry"] = pd.to_datetime(df["active_expiry"])
    df = df.sort_values("trade_date").reset_index(drop=True)

    out_dir = Path("backtesting/nifty_covered_call")

    print("\n" + "=" * 90)
    print("      NIFTY COVERED CALL — COMPREHENSIVE RESEARCH & AUDIT SUITE")
    print(f"      Data Span: {df['trade_date'].min().date()} to {df['trade_date'].max().date()} | Bars: {len(df)}")
    print("=" * 90)

    # Benchmark calculation
    bench = compute_benchmark(df)
    print(f"\n[BENCHMARK] Buy & Hold NIFTY ({bench['Start Date']} to {bench['End Date']}):")
    print(f"  • Start Spot: ₹{bench['Start Spot']:,.2f} -> End Spot: ₹{bench['End Spot']:,.2f} ({bench['B&H Return (%)']}%)")
    print(f"  • Gross P&L : ₹{bench['B&H Net P&L (₹)']:,.2f} (50 qty)")
    print(f"  • Max Drawdown: ₹{bench['B&H Max DD (₹)']:,.2f}")

    # Experiments
    experiments = {}
    all_trade_records: List[TradeRecord] = []

    # 1. Baseline Exact Replication (Zero Costs - as in existing backtest)
    t_base_raw = simulate_strategy(df, "1_Baseline_Raw_NoCosts", apply_costs=False)
    experiments["1. Baseline (Raw No Costs)"] = compute_comprehensive_metrics(t_base_raw, df)
    all_trade_records.extend(t_base_raw)

    # 2. Baseline Net of Costs
    t_base_net = simulate_strategy(df, "2_Baseline_Net_Costs", apply_costs=True)
    experiments["2. Baseline (Net Costs)"] = compute_comprehensive_metrics(t_base_net, df)
    all_trade_records.extend(t_base_net)

    # 3. Minimum DTE Entry Filter Evaluation
    # 3A: Permissive DTE (10 <= DTE <= 35) - allows entering late into cycle
    t_dte_10 = simulate_strategy(df, "3A_DTE_Min_10", min_dte_entry=10, max_dte_entry=35, apply_costs=True)
    experiments["3A. DTE Entry >= 10d"] = compute_comprehensive_metrics(t_dte_10, df)
    all_trade_records.extend(t_dte_10)

    # 3B: 15-Day Minimum DTE Entry Filter (15 <= DTE <= 35)
    t_dte_15 = simulate_strategy(df, "3B_DTE_Min_15", min_dte_entry=15, max_dte_entry=35, apply_costs=True)
    experiments["3B. DTE Entry >= 15d (Candidate)"] = compute_comprehensive_metrics(t_dte_15, df)
    all_trade_records.extend(t_dte_15)

    # 3C: 20-Day Minimum DTE Entry Filter (20 <= DTE <= 35)
    t_dte_20 = simulate_strategy(df, "3C_DTE_Min_20", min_dte_entry=20, max_dte_entry=35, apply_costs=True)
    experiments["3C. DTE Entry >= 20d (Strict)"] = compute_comprehensive_metrics(t_dte_20, df)
    all_trade_records.extend(t_dte_20)

    # 4. Isolated Risk Controls (Evaluated independently on top of Baseline Net Costs)
    # Control 1: Futures Catastrophe Stop (-2.0%)
    t_ctrl1 = simulate_strategy(df, "4_Ctrl1_Futures_Stop_2pct", fut_stop_pct=0.02, apply_costs=True)
    experiments["4. Control 1: Fut Stop (-2.0%)"] = compute_comprehensive_metrics(t_ctrl1, df)
    all_trade_records.extend(t_ctrl1)

    # Control 2: Combined Position M2M Loss Cap (-₹20,000)
    t_ctrl2 = simulate_strategy(df, "5_Ctrl2_M2M_Cap_20k", m2m_cap_inr=20000.0, apply_costs=True)
    experiments["5. Control 2: M2M Cap (-₹20k)"] = compute_comprehensive_metrics(t_ctrl2, df)
    all_trade_records.extend(t_ctrl2)

    # Control 3: Trend Breakdown Exit (Close < 100-EMA)
    t_ctrl3 = simulate_strategy(df, "6_Ctrl3_Trend_Breakdown", trend_exit=True, apply_costs=True)
    experiments["6. Control 3: Trend Exit (<100EMA)"] = compute_comprehensive_metrics(t_ctrl3, df)
    all_trade_records.extend(t_ctrl3)

    # Control 4: High-Water-Mark Trailing Exit (Peak >= ₹15,000, 40% buffer)
    t_ctrl4 = simulate_strategy(df, "7_Ctrl4_Trailing_Exit", trail_active_threshold=15000.0, trail_pullback_pct=0.40, apply_costs=True)
    experiments["7. Control 4: Trailing Exit (15k/40%)"] = compute_comprehensive_metrics(t_ctrl4, df)
    all_trade_records.extend(t_ctrl4)

    # Control 5: Combined Selective Risk Architecture (Only justified controls combined)
    # (Futures Catastrophe Stop 2.0% + 15-DTE Filter + Trailing Exit 15k/40%)
    t_combined = simulate_strategy(
        df,
        "8_Combined_Risk_Architecture",
        min_dte_entry=15,
        max_dte_entry=35,
        fut_stop_pct=0.02,
        trail_active_threshold=15000.0,
        trail_pullback_pct=0.40,
        apply_costs=True,
    )
    experiments["8. Combined Architecture (Justified)"] = compute_comprehensive_metrics(t_combined, df)
    all_trade_records.extend(t_combined)

    # Build Comparison Matrix
    comparison_df = pd.DataFrame(experiments).T
    print("\n" + "=" * 90)
    print("                     EXPERIMENT PERFORMANCE MATRIX")
    print("=" * 90)
    print(comparison_df.to_string())

    # Export Artifacts (preserving all existing files!)
    comparison_df.to_csv(out_dir / "research_comparison_metrics.csv")
    
    trades_df = pd.DataFrame([asdict(t) for t in all_trade_records])
    trades_df.to_csv(out_dir / "research_all_trades.csv", index=False)

    print(f"\n[✓] Research outputs saved to:")
    print(f"    - {out_dir / 'research_comparison_metrics.csv'}")
    print(f"    - {out_dir / 'research_all_trades.csv'}")


if __name__ == "__main__":
    run_all_experiments()
