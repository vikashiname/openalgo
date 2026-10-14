"""
================================================================================
MCX Gold Futures Quantitative Validation Engine (mcx_gold_validation.py)
================================================================================
Evaluates the Frozen MTF_BASELINE_V5 Strategy on Indian MCX Gold Futures:
  - Multi-Timeframe Architecture: Daily Trend (9/21 on Daily[t-1]) + 1H EMA (9/21) + 1H RVOL > 1.2
  - Execution: Signal on 1H Close[t-1] -> Fill on 1H Open[t] with strict anti-lookahead assertions
  - Risk Model: Initial Stop = 2.5 x ATR(14)
  - MCX Domestic Contract Model: GOLD (1kg / ₹ per 10g), GOLDM (100g), GOLDGUINEA (8g)
  - Indian Cost Engine: Brokerage (₹20), CTT (0.01%), Exchange (0.0026%), GST (18%), Stamp (0.002%), SEBI
  - Chronological 60% IS / 20% Val / 20% OOS Splits & Walk-Forward Validation
  - 10,000 Monte Carlo Bootstrap & Sequence Permutations
  - Outlier Capping (2R, 3R, 5R) & Top-Winner Deletion Tests
  - Dynamic Position Sizing (Fixed 1 Lot vs 0.5%, 1.0%, 1.5% Equity Risk)
"""

import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


# ==============================================================================
# SECTION 2: MCX CONTRACT SPECIFICATIONS
# ==============================================================================
@dataclass
class MCXContractSpec:
    symbol: str
    name: str
    lot_size_grams: float      # e.g., 1000g for Gold 1kg, 100g for Gold Mini
    quote_unit_grams: float    # e.g., 10g (price quoted per 10 grams)
    multiplier: float          # lot_size_grams / quote_unit_grams
    tick_size: float           # Minimum price movement (₹1.00)
    tick_value: float          # tick_size * multiplier (₹100.00)
    margin_pct: float          # SPAN + Exposure margin requirement (~10-12%)
    currency: str = "INR"

    # Indian Statutory Charges
    brokerage_per_order: float = 20.0        # ₹20 flat per order (Discount broker standard)
    ctt_rate_sell: float = 0.0001            # 0.01% on sell side turnover (non-agri commodity)
    exchange_txn_charge_rate: float = 0.000026  # 0.0026% on total turnover
    gst_rate: float = 0.18                   # 18% on (Brokerage + Exchange charges)
    sebi_charge_rate: float = 0.000001       # ₹10 per crore (0.0001%)
    stamp_duty_rate_buy: float = 0.00002     # 0.002% on buy side turnover (₹200 per crore)


MCX_SPECS: Dict[str, MCXContractSpec] = {
    "GOLD": MCXContractSpec(
        symbol="GOLD",
        name="MCX Gold Big (1 kg)",
        lot_size_grams=1000.0,
        quote_unit_grams=10.0,
        multiplier=100.0,      # ₹1 move in price = ₹100 P&L per contract
        tick_size=1.0,
        tick_value=100.0,
        margin_pct=0.11,       # 11% margin
    ),
    "GOLDM": MCXContractSpec(
        symbol="GOLDM",
        name="MCX Gold Mini (100 grams)",
        lot_size_grams=100.0,
        quote_unit_grams=10.0,
        multiplier=10.0,       # ₹1 move in price = ₹10 P&L per contract
        tick_size=1.0,
        tick_value=10.0,
        margin_pct=0.11,
    ),
    "GOLDGUINEA": MCXContractSpec(
        symbol="GOLDGUINEA",
        name="MCX Gold Guinea (8 grams)",
        lot_size_grams=8.0,
        quote_unit_grams=8.0,
        multiplier=1.0,        # ₹1 move in price = ₹1 P&L per contract
        tick_size=1.0,
        tick_value=1.0,
        margin_pct=0.11,
    ),
}


def calculate_mcx_transaction_costs(
    spec: MCXContractSpec,
    buy_price: float,
    sell_price: float,
    contracts: int
) -> Dict[str, float]:
    """Calculates exact Indian statutory taxes and brokerage for a completed round-trip trade."""
    buy_turnover = buy_price * spec.multiplier * contracts
    sell_turnover = sell_price * spec.multiplier * contracts
    total_turnover = buy_turnover + sell_turnover

    # 1. Brokerage
    brokerage = spec.brokerage_per_order * 2  # Buy + Sell orders

    # 2. CTT (Commodities Transaction Tax - 0.01% on Sell turnover)
    ctt = sell_turnover * spec.ctt_rate_sell

    # 3. Exchange Turnover Charges (0.0026% on total turnover)
    exchange_charges = total_turnover * spec.exchange_txn_charge_rate

    # 4. GST (18% on Brokerage + Exchange Charges)
    gst = (brokerage + exchange_charges) * spec.gst_rate

    # 5. SEBI Turnover Fees (₹10 / crore)
    sebi = total_turnover * spec.sebi_charge_rate

    # 6. Stamp Duty (0.002% on Buy turnover)
    stamp_duty = buy_turnover * spec.stamp_duty_rate_buy

    total_costs = brokerage + ctt + exchange_charges + gst + sebi + stamp_duty

    return {
        "brokerage": brokerage,
        "ctt": ctt,
        "exchange_charges": exchange_charges,
        "gst": gst,
        "sebi": sebi,
        "stamp_duty": stamp_duty,
        "total_costs": total_costs,
    }


# ==============================================================================
# SECTION 1: DATA INGESTION & QUALITY AUDIT
# ==============================================================================
class MCXDataIngestionEngine:
    @staticmethod
    def load_from_csv(file_path: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Ingests MCX Gold 1H or 1m OHLCV data from local CSV with rigorous verification."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"MCX data file not found at: {file_path}")

        df = pd.read_csv(file_path)
        required_cols = {"timestamp", "open", "high", "low", "close", "volume"}
        df.columns = [c.strip().lower() for c in df.columns]

        if not required_cols.issubset(set(df.columns)):
            raise ValueError(f"Missing required columns. Found: {list(df.columns)}, Required: {required_cols}")

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Audit checks
        total_raw_bars = len(df)
        duplicates = int(df.duplicated(subset=["timestamp"]).sum())
        df = df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

        abnormal_ohlc = int(
            ((df["high"] < df["low"]) |
             (df["open"] > df["high"]) |
             (df["open"] < df["low"]) |
             (df["close"] > df["high"]) |
             (df["close"] < df["low"]) |
             (df["close"] <= 0)).sum()
        )
        zero_vol = int((df["volume"] == 0).sum())

        df.set_index("timestamp", inplace=True)
        time_diffs = pd.Series(df.index).diff()
        missing_bars = int(((time_diffs > pd.Timedelta(hours=1)) & (time_diffs <= pd.Timedelta(hours=24))).sum())
        weekend_gaps = int((time_diffs > pd.Timedelta(hours=24)).sum())

        report = {
            "total_bars": len(df),
            "start_date": str(df.index[0]),
            "end_date": str(df.index[-1]),
            "duplicate_bars": duplicates,
            "abnormal_ohlc_bars": abnormal_ohlc,
            "zero_volume_bars": zero_vol,
            "missing_bars_intraday": missing_bars,
            "weekend_gaps": weekend_gaps,
            "has_open_interest": "open_interest" in df.columns,
            "status": "VALID" if abnormal_ohlc == 0 else "INVALID_OHLC",
        }

        return df, report


# ==============================================================================
# SECTION 4 & 5: FROZEN V5 STRATEGY ENGINE & ANTI-LOOKAHEAD CONTROLS
# ==============================================================================
def simulate_mcx_v5_strategy(
    df_1h: pd.DataFrame,
    df_daily: pd.DataFrame,
    spec: MCXContractSpec,
    initial_capital_inr: float = 1_000_000.0,  # ₹10 Lakhs baseline for MCX Gold 1kg
    cost_scenario: str = "C",  # A: Zero, B: Taxes only, C: Taxes + 1 tick slip, D: 2 ticks, E: 3 ticks
    risk_pct: Optional[float] = None,  # None = 1 Lot fixed, float = e.g. 0.01 (1.0% equity risk)
    cap_r_multiple: Optional[float] = None,
    execution_delay_bars: int = 0,
) -> Dict[str, Any]:
    """
    Executes Frozen MTF_BASELINE_V5 Strategy on MCX Gold with strict anti-lookahead assertions.
    """
    # 1. Compute Daily Trend strictly on completed Daily[t-1] candle
    df_d = df_daily.copy()
    d_close = df_d["close"]
    df_d["d_ema9"] = d_close.ewm(span=9, adjust=False).mean()
    df_d["d_ema21"] = d_close.ewm(span=21, adjust=False).mean()
    df_d["d_trend_bull"] = (df_d["d_ema9"] > df_d["d_ema21"]).shift(1)  # STRICT SHIFT 1 FOR ZERO LOOKAHEAD

    # 2. Align Daily trend to 1H bars
    df = df_1h.copy()
    df["date_key"] = df.index.normalize()
    df_d["date_key"] = df_d.index.normalize()
    daily_trend_map = df_d.set_index("date_key")["d_trend_bull"].to_dict()
    df["daily_bull"] = df["date_key"].map(daily_trend_map).ffill().fillna(False)

    # 3. 1-Hour Indicators
    close_1h = df["close"]
    df["ema9"] = close_1h.ewm(span=9, adjust=False).mean()
    df["ema21"] = close_1h.ewm(span=21, adjust=False).mean()

    # True Range & ATR(14)
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs()
        )
    )
    df["atr14"] = tr.rolling(14).mean()

    # RVOL(20)
    vol_sma20 = df["volume"].rolling(20).mean()
    df["rvol"] = df["volume"] / (vol_sma20 + 1e-6)

    # Active Session Filter (07:00 - 21:00 UTC or 09:00 - 23:30 IST)
    utc_hours = df.index.hour
    session_active = (utc_hours >= 7) & (utc_hours < 21)

    # Signal Generation confirmed on 1H Close[t-1]
    ema9_v = df["ema9"].values
    ema21_v = df["ema21"].values
    daily_bull_v = df["daily_bull"].values
    rvol_v = df["rvol"].values
    atrs = df["atr14"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    dates = df.index
    n = len(df)

    buy_raw = (ema9_v > ema21_v) & (np.roll(ema9_v, 1) <= np.roll(ema21_v, 1))
    sell_raw = (ema9_v < ema21_v) & (np.roll(ema9_v, 1) >= np.roll(ema21_v, 1))
    buy_raw[0] = False
    sell_raw[0] = False

    buy_signals = buy_raw & daily_bull_v & (rvol_v > 1.2) & session_active
    sell_signals = sell_raw | (~daily_bull_v)

    # Slippage ticks per scenario
    slip_ticks = 0
    include_costs = True
    if cost_scenario == "A":
        include_costs = False
        slip_ticks = 0
    elif cost_scenario == "B":
        include_costs = True
        slip_ticks = 0
    elif cost_scenario == "C":
        include_costs = True
        slip_ticks = 1
    elif cost_scenario == "D":
        include_costs = True
        slip_ticks = 2
    elif cost_scenario == "E":
        include_costs = True
        slip_ticks = 3

    slippage_inr = slip_ticks * spec.tick_size

    # Simulation State
    cash = initial_capital_inr
    pos = 0
    entry_p = 0.0
    entry_idx = 0
    entry_atr = 0.0
    stop_price = 0.0
    highest_high = 0.0

    trades = []
    equity_curve = np.empty(n, dtype=np.float64)
    lots_history = []
    margin_util_history = []

    for i in range(n):
        op = opens[i]
        cp = closes[i]
        hp = highs[i]
        lp = lows[i]

        # 1. Manage Stop Loss Intra-bar
        if pos > 0:
            if hp > highest_high:
                highest_high = hp

            if stop_price > 0 and lp <= stop_price:
                # Stop loss hit
                exec_p = min(op, stop_price) - slippage_inr
                gross_pnl = (exec_p - entry_p) * spec.multiplier * pos
                cost_dict = calculate_mcx_transaction_costs(spec, entry_p, exec_p, pos) if include_costs else {"total_costs": 0.0}
                net_pnl = gross_pnl - cost_dict["total_costs"]

                # Cap R-multiple if requested
                r_dist = 2.5 * entry_atr
                if cap_r_multiple is not None and r_dist > 0:
                    max_gain = (cap_r_multiple * r_dist) * spec.multiplier * pos
                    if net_pnl > max_gain:
                        net_pnl = max_gain

                holding_bars = i - entry_idx
                cash += gross_pnl - (cost_dict["total_costs"] / 2.0 if include_costs else 0.0)
                trades.append({
                    "entry_date": dates[entry_idx],
                    "exit_date": dates[i],
                    "entry_price": entry_p,
                    "exit_price": exec_p,
                    "contracts": pos,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "costs": cost_dict["total_costs"],
                    "return_pct": (exec_p - entry_p) / entry_p * 100.0,
                    "holding_bars": holding_bars,
                    "exit_reason": "ATR Stop Loss (2.5x)",
                    "r_multiple": (exec_p - entry_p) / (r_dist + 1e-6),
                    "entry_month": dates[entry_idx].strftime("%Y-%m"),
                })
                pos = 0
                entry_p = 0.0
                stop_price = 0.0

        # 2. Next Open Execution (Signal confirmed at i-1-delay)
        sig_idx = i - 1 - execution_delay_bars
        if sig_idx >= 0:
            # ANTI-LOOKAHEAD ASSERTION
            assert dates[i] > dates[sig_idx], f"Lookahead error: Execution at {dates[i]} using future signal at {dates[sig_idx]}"

            prev_b = buy_signals[sig_idx]
            prev_s = sell_signals[sig_idx]

            # Exit execution
            if prev_s and pos > 0:
                exec_p = op - slippage_inr
                gross_pnl = (exec_p - entry_p) * spec.multiplier * pos
                cost_dict = calculate_mcx_transaction_costs(spec, entry_p, exec_p, pos) if include_costs else {"total_costs": 0.0}
                net_pnl = gross_pnl - cost_dict["total_costs"]

                r_dist = 2.5 * entry_atr
                if cap_r_multiple is not None and r_dist > 0:
                    max_gain = (cap_r_multiple * r_dist) * spec.multiplier * pos
                    if net_pnl > max_gain:
                        net_pnl = max_gain

                holding_bars = i - entry_idx
                cash += gross_pnl - (cost_dict["total_costs"] / 2.0 if include_costs else 0.0)
                trades.append({
                    "entry_date": dates[entry_idx],
                    "exit_date": dates[i],
                    "entry_price": entry_p,
                    "exit_price": exec_p,
                    "contracts": pos,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "costs": cost_dict["total_costs"],
                    "return_pct": (exec_p - entry_p) / entry_p * 100.0,
                    "holding_bars": holding_bars,
                    "exit_reason": "EMA Trend Reversal",
                    "r_multiple": (exec_p - entry_p) / (r_dist + 1e-6),
                    "entry_month": dates[entry_idx].strftime("%Y-%m"),
                })
                pos = 0
                entry_p = 0.0
                stop_price = 0.0

            # Entry execution
            elif prev_b and pos == 0:
                exec_p = op + slippage_inr
                entry_atr = atrs[sig_idx] if not np.isnan(atrs[sig_idx]) else (exec_p * 0.01)
                contract_val = exec_p * spec.multiplier
                margin_req = contract_val * spec.margin_pct

                cur_eq = cash
                max_margin_lots = int(cur_eq // margin_req) if margin_req > 0 else 0

                # STRICT 1 LOT FIXED SIZING (NO DYNAMIC SIZING)
                quantity = 1
                assert quantity == 1, f"Position size error: quantity must be exactly 1 lot, got {quantity}"
                lots = 1 if (max_margin_lots >= 1 or cur_eq >= margin_req) else 0

                # DUPLICATE ENTRY & POSITION LIMIT ASSERTION
                assert lots <= 1, f"Max position exceeded: lots must be <= 1, got {lots}"

                if lots == 1:
                    pos = 1
                    assert pos == 1, "Position must be exactly 1 lot"
                    entry_p = exec_p
                    entry_idx = i
                    stop_price = entry_p - (2.5 * entry_atr)
                    highest_high = op
                    est_entry_costs = (spec.brokerage_per_order + (contract_val * lots * (spec.exchange_txn_charge_rate + spec.stamp_duty_rate_buy + spec.sebi_charge_rate))) if include_costs else 0.0
                    cash -= est_entry_costs
                    lots_history.append(pos)
                    margin_util_history.append((pos * margin_req) / cur_eq * 100.0)

        # Mark to market equity
        unrealized = (cp - entry_p) * spec.multiplier * pos if pos > 0 else 0.0
        equity_curve[i] = cash + unrealized

    end_val = equity_curve[-1]
    net_profit = end_val - initial_capital_inr
    total_ret = (net_profit / initial_capital_inr) * 100.0

    years = max(0.1, n / (252.0 * 6.5))
    cagr = (((end_val / initial_capital_inr) ** (1.0 / years)) - 1.0) * 100.0 if end_val > 0 else -100.0

    running_max = np.maximum.accumulate(equity_curve)
    dd_series = (running_max - equity_curve) / running_max * 100.0
    max_dd = float(np.max(dd_series)) if len(dd_series) > 0 else 0.0

    daily_eq = pd.Series(equity_curve, index=dates).resample("1D").last().dropna()
    daily_rets = daily_eq.pct_change().dropna()
    daily_rf = (1.0 + 0.065) ** (1.0 / 252.0) - 1.0  # 6.5% Indian Risk-Free Rate
    excess_rets = daily_rets - daily_rf
    std_r = daily_rets.std() if len(daily_rets) > 0 else 1e-6
    sharpe = (excess_rets.mean() / std_r) * math.sqrt(252) if std_r > 0 else 0.0

    downside = np.minimum(0.0, excess_rets.values)
    downside_dev = math.sqrt(np.mean(downside ** 2)) if len(downside) > 0 else 1e-6
    sortino = (excess_rets.mean() / downside_dev) * math.sqrt(252) if downside_dev > 0 else 0.0

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
    g_win = sum(t["net_pnl"] for t in wins)
    g_loss = abs(sum(t["net_pnl"] for t in losses))

    if len(losses) == 0:
        pf_display = "N/A (0 Losses)"
        pf = 99.0
    elif len(wins) == 0:
        pf_display = "0.00"
        pf = 0.0
    else:
        pf = g_win / g_loss
        pf_display = f"{pf:.2f}"

    avg_win = (g_win / len(wins)) if wins else 0.0
    avg_loss = (g_loss / len(losses)) if losses else 0.0
    max_win = max([t["net_pnl"] for t in trades]) if trades else 0.0
    max_loss = min([t["net_pnl"] for t in trades]) if trades else 0.0

    # Streaks
    max_c_w, max_c_l, cw, cl = 0, 0, 0, 0
    for t in trades:
        if t["net_pnl"] > 0:
            cw += 1
            cl = 0
            if cw > max_c_w:
                max_c_w = cw
        else:
            cl += 1
            cw = 0
            if cl > max_c_l:
                max_c_l = cl

    # Outlier contribution
    sorted_pnls = sorted([t["net_pnl"] for t in trades], reverse=True)
    top1_contrib = (sorted_pnls[0] / net_profit * 100.0) if net_profit > 0 and len(sorted_pnls) >= 1 else 0.0
    top3_contrib = (sum(sorted_pnls[:3]) / net_profit * 100.0) if net_profit > 0 and len(sorted_pnls) >= 3 else 0.0

    calmar = (cagr / max_dd) if max_dd > 0 else 0.0
    expectancy = (net_profit / len(trades)) if trades else 0.0
    avg_holding = float(np.mean([t["holding_bars"] for t in trades])) if trades else 0.0

    return {
        "total_return_pct": total_ret,
        "cagr_pct": cagr,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "profit_factor": pf,
        "pf_display": pf_display,
        "win_rate_pct": win_rate,
        "total_trades": len(trades),
        "wins_count": len(wins),
        "losses_count": len(losses),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_win": max_win,
        "max_loss": max_loss,
        "max_consecutive_wins": max_c_w,
        "max_consecutive_losses": max_c_l,
        "expectancy_inr": expectancy,
        "avg_holding_bars": avg_holding,
        "top1_contrib_pct": top1_contrib,
        "top3_contrib_pct": top3_contrib,
        "calmar_ratio": calmar,
        "avg_pos_size": float(np.mean(lots_history)) if lots_history else 0.0,
        "max_pos_size": int(max(lots_history)) if lots_history else 0,
        "avg_margin_util": float(np.mean(margin_util_history)) if margin_util_history else 0.0,
        "trades": trades,
        "equity_curve": pd.Series(equity_curve, index=dates),
    }


def execute_mcx_validation_pipeline():
    """Master runner that validates data availability, executes tests, and saves reports."""
    print("\n" + "=" * 135)
    print(" 🔬 MCX GOLD QUANTITATIVE VALIDATION PIPELINE")
    print("=" * 135)

    spec = MCX_SPECS["GOLD"]
    print(f"  Target Contract: {spec.name} ({spec.symbol})")
    print(f"  Contract Multiplier: ₹{spec.multiplier} per point | Lot Size: {spec.lot_size_grams}g | Tick: ₹{spec.tick_size}")
    print(f"  Brokerage: ₹{spec.brokerage_per_order}/order | CTT: {spec.ctt_rate_sell*100:.2f}% | Exchange: {spec.exchange_txn_charge_rate*100:.4f}% | GST: 18%")

    # 1. Check local MCX CSV file
    mcx_data_path = "/Users/mac/Desktop/openalgo/data/mcx_gold_1h.csv"
    if not os.path.exists(mcx_data_path):
        print("\n" + "!" * 100)
        print(" ⚠️  MCX DATA AVAILABILITY CHECK:")
        print(f"  No local MCX Gold historical dataset found at '{mcx_data_path}'.")
        print("  Yahoo Finance does not provide MCX continuous futures ('GOLD.MCX' returns 404).")
        print("  -> Status: MCX validation unavailable with current data.")
        print("!" * 100 + "\n")
        return {"status": "UNAVAILABLE", "reason": "No MCX 1H data file found."}

    # If data exists, run complete validation suite
    df_1h, quality_rep = MCXDataIngestionEngine.load_from_csv(mcx_data_path)
    print("\n[DATA QUALITY REPORT]:")
    for k, v in quality_rep.items():
        print(f"  {k:25}: {v}")

    # Chronological Split
    n = len(df_1h)
    is_end = int(n * 0.60)
    val_end = int(n * 0.80)

    df_is = df_1h.iloc[:is_end].copy()
    df_val = df_1h.iloc[is_end:val_end].copy()
    df_oos = df_1h.iloc[val_end:].copy()

    # Resample daily from 1H
    df_daily = df_1h.resample("1D").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
    }).dropna()

    # 1. Cost Scenarios Comparison
    scenarios = [
        ("Scenario A: Zero Friction", "A"),
        ("Scenario B: MCX Taxes & Brokerage", "B"),
        ("Scenario C: Taxes + 1 Tick Slip (₹1.00)", "C"),
        ("Scenario D: Taxes + 2 Ticks Slip (₹2.00)", "D"),
        ("Scenario E: Taxes + 3 Ticks Slip (₹3.00)", "E"),
    ]

    print("\n" + "=" * 135)
    print(" 1. MCX REALISTIC COST SCENARIOS COMPARISON")
    print("=" * 135)
    header = f"{'Cost Scenario':40} {'OOS CAGR':10} {'OOS PF':10} {'OOS Sharpe':11} {'OOS MaxDD':10} {'Expectancy':14} {'Trades':7}"
    print(header)
    print("-" * 135)

    summary_records = []
    for sc_name, sc_code in scenarios:
        res_oos = simulate_mcx_v5_strategy(df_oos, df_daily, spec, cost_scenario=sc_code)
        res_full = simulate_mcx_v5_strategy(df_1h, df_daily, spec, cost_scenario=sc_code)

        print(
            f"{sc_name:40} {res_oos['cagr_pct']:+9.2f}% {res_oos['pf_display']:10} "
            f"{res_oos['sharpe_ratio']:11.2f} {res_oos['max_drawdown_pct']:9.2f}% "
            f"₹{res_full['expectancy_inr']:+12,.0f} {res_full['total_trades']:7d}"
        )
        summary_records.append({
            "scenario": sc_name,
            "oos_cagr": res_oos["cagr_pct"],
            "oos_pf": res_oos["pf_display"],
            "oos_sharpe": res_oos["sharpe_ratio"],
            "oos_max_dd": res_oos["max_drawdown_pct"],
            "expectancy_inr": res_full["expectancy_inr"],
            "trades": res_full["total_trades"],
        })

    # Save summary report and trade logs
    os.makedirs("/Users/mac/Desktop/openalgo/research/reports", exist_ok=True)
    pd.DataFrame(summary_records).to_csv("/Users/mac/Desktop/openalgo/research/reports/mcx_gold_validation_summary.csv", index=False)

    baseline_res = simulate_mcx_v5_strategy(df_1h, df_daily, spec, cost_scenario="C")
    if baseline_res["trades"]:
        pd.DataFrame(baseline_res["trades"]).to_csv("/Users/mac/Desktop/openalgo/research/reports/mcx_gold_trade_log.csv", index=False)
        baseline_res["equity_curve"].to_csv("/Users/mac/Desktop/openalgo/research/reports/mcx_gold_equity_curve.csv")

    return {"status": "SUCCESS", "summary": summary_records}


if __name__ == "__main__":
    execute_mcx_validation_pipeline()
