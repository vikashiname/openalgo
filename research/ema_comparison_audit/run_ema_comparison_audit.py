"""
================================================================================
Isolated Research Harness: EMA 9/26 vs EMA 10/28 Controlled Comparison Audit
File: research/ema_comparison_audit/run_ema_comparison_audit.py
================================================================================
Performs an isolated, deterministic backtest comparing:
  - Baseline: Fast EMA 9 / Slow EMA 26
  - Candidate: Fast EMA 10 / Slow EMA 28

Under identical:
  - 1H completed candles
  - MACD 12/26/9
  - Asymmetric V2-2 2-candle confirmation window
  - Long: SAME_CANDLE, MACD_THEN_EMA, EMA_THEN_MACD
  - Short: SAME_CANDLE, MACD_THEN_EMA (EMA-first rejected)
  - Exits: Target (+3.00% Long / +1.50% Short), Catastrophe SL (-6.00%), V2-2 Reversal
  - Transaction friction: 0.07% round-trip (with stress testing at 0.05%, 0.10%, 0.15%)
  - In-Sample (< 2025-07-01) vs Out-of-Sample (>= 2025-07-01)
  - 33 liquid NFO instruments (2023-09-29 to 2026-09-09)
================================================================================
"""

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Add backtesting path for data access
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKTEST_DIR = PROJECT_ROOT / "backtesting" / "emacrossopen"
if str(BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(BACKTEST_DIR))

from data_manager import load_or_download_all_data, SYMBOL_TICKER_MAP

OUTPUT_DIR = Path(__file__).resolve().parent

FRICTION_PCT = 0.07
LONG_TP_PCT = 3.00
SHORT_TP_PCT = 1.50
CATASTROPHE_SL_PCT = 6.00
IS_SPLIT_DATE = pd.to_datetime("2025-07-01", utc=True)


def calculate_indicators_for_params(
    df: pd.DataFrame, fast_ema: int, slow_ema: int, macd_fast: int = 12, macd_slow: int = 26, macd_sig: int = 9
) -> pd.DataFrame:
    """Calculates EMA, MACD, and ATR with configurable spans."""
    res = df.copy()
    close = res["Close"]
    high = res["High"]
    low = res["Low"]

    res["fast_ema"] = close.ewm(span=fast_ema, adjust=False).mean()
    res["slow_ema"] = close.ewm(span=slow_ema, adjust=False).mean()

    res["macd_fast_ema"] = close.ewm(span=macd_fast, adjust=False).mean()
    res["macd_slow_ema"] = close.ewm(span=macd_slow, adjust=False).mean()
    res["macd"] = res["macd_fast_ema"] - res["macd_slow_ema"]
    res["macd_signal"] = res["macd"].ewm(span=macd_sig, adjust=False).mean()
    res["macd_histogram"] = res["macd"] - res["macd_signal"]

    # ATR 14
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    res["atr14"] = tr.rolling(window=14).mean()

    return res


def run_state_machine_for_config(
    data_map: Dict[str, pd.DataFrame],
    fast_ema: int,
    slow_ema: int,
    long_tp: float = LONG_TP_PCT,
    short_tp: float = SHORT_TP_PCT,
    sl_pct: float = CATASTROPHE_SL_PCT,
    friction: float = FRICTION_PCT,
) -> pd.DataFrame:
    """Executes chronological bar-by-bar simulation matching production V2-2 state machine."""
    all_trades = []

    for sym, raw_df in data_map.items():
        meta = SYMBOL_TICKER_MAP.get(sym, {"lot_size": 1, "sector": "UNKNOWN"})
        lot_size = meta["lot_size"]
        sector = meta["sector"]

        df = calculate_indicators_for_params(raw_df, fast_ema, slow_ema).dropna().copy()
        n = len(df)
        if n < 50:
            continue

        close = df["Close"].values
        open_px = df["Open"].values
        high_px = df["High"].values
        low_px = df["Low"].values
        f_ema = df["fast_ema"].values
        s_ema = df["slow_ema"].values
        macd = df["macd"].values
        sig_line = df["macd_signal"].values
        atr = df["atr14"].values
        times = df.index

        pos = 0  # 1 = LONG, -1 = SHORT, 0 = FLAT
        entry_px = 0.0
        entry_time = None
        entry_idx = 0
        active_pending = None

        for i in range(1, n - 1):
            curr_open = open_px[i]
            curr_high = high_px[i]
            curr_low = low_px[i]
            curr_f = f_ema[i]
            prev_f = f_ema[i - 1]
            curr_s = s_ema[i]
            prev_s = s_ema[i - 1]
            curr_m = macd[i]
            prev_m = macd[i - 1]
            curr_sig = sig_line[i]
            prev_sig = sig_line[i - 1]

            # 1. RISK CHECK ON COMPLETED 1H CANDLE
            exited_this_bar = False
            if pos != 0 and i >= entry_idx:
                if pos == 1:  # LONG
                    target_px = entry_px * (1.0 + long_tp / 100.0) if long_tp else None
                    stop_px = entry_px * (1.0 - sl_pct / 100.0) if sl_pct else None

                    tp_hit = (target_px is not None) and (curr_high >= target_px)
                    sl_hit = (stop_px is not None) and (curr_low <= stop_px)

                    if tp_hit and sl_hit:
                        if curr_open >= target_px:
                            x_px = curr_open
                            x_reason = "TARGET_HIT"
                        elif curr_open <= stop_px:
                            x_px = curr_open
                            x_reason = "CATASTROPHE_SL"
                        else:
                            x_px = stop_px
                            x_reason = "CATASTROPHE_SL"
                        exited_this_bar = True
                    elif sl_hit:
                        x_px = curr_open if curr_open <= stop_px else max(stop_px, curr_low)
                        x_reason = "CATASTROPHE_SL"
                        exited_this_bar = True
                    elif tp_hit:
                        x_px = curr_open if curr_open >= target_px else min(target_px, curr_high)
                        x_reason = "TARGET_HIT"
                        exited_this_bar = True

                else:  # SHORT
                    target_px = entry_px * (1.0 - short_tp / 100.0) if short_tp else None
                    stop_px = entry_px * (1.0 + sl_pct / 100.0) if sl_pct else None

                    tp_hit = (target_px is not None) and (curr_low <= target_px)
                    sl_hit = (stop_px is not None) and (curr_high >= stop_px)

                    if tp_hit and sl_hit:
                        if curr_open <= target_px:
                            x_px = curr_open
                            x_reason = "TARGET_HIT"
                        elif curr_open >= stop_px:
                            x_px = curr_open
                            x_reason = "CATASTROPHE_SL"
                        else:
                            x_px = stop_px
                            x_reason = "CATASTROPHE_SL"
                        exited_this_bar = True
                    elif sl_hit:
                        x_px = curr_open if curr_open >= stop_px else min(stop_px, curr_high)
                        x_reason = "CATASTROPHE_SL"
                        exited_this_bar = True
                    elif tp_hit:
                        x_px = curr_open if curr_open <= target_px else max(target_px, curr_low)
                        x_reason = "TARGET_HIT"
                        exited_this_bar = True

                if exited_this_bar:
                    dir_mult = 1.0 if pos == 1 else -1.0
                    raw_pnl = ((x_px - entry_px) / entry_px) * 100.0 * dir_mult
                    net_pnl = raw_pnl - friction

                    slice_highs = high_px[entry_idx : i + 1]
                    slice_lows = low_px[entry_idx : i + 1]
                    if pos == 1:
                        mfe = ((slice_highs.max() - entry_px) / entry_px) * 100.0
                        mae = ((entry_px - slice_lows.min()) / entry_px) * 100.0
                    else:
                        mfe = ((entry_px - slice_lows.min()) / entry_px) * 100.0
                        mae = ((slice_highs.max() - entry_px) / entry_px) * 100.0

                    entry_ts = pd.to_datetime(entry_time)
                    if entry_ts.tzinfo is not None:
                        is_split = IS_SPLIT_DATE.tz_convert(entry_ts.tz)
                    else:
                        entry_ts = entry_ts.tz_localize("UTC")
                        is_split = IS_SPLIT_DATE
                    sample = "IS" if entry_ts < is_split else "OOS"

                    all_trades.append({
                        "symbol": sym,
                        "sector": sector,
                        "direction": "LONG" if pos == 1 else "SHORT",
                        "entry_time": entry_time,
                        "exit_time": times[i],
                        "entry_price": entry_px,
                        "exit_price": x_px,
                        "exit_reason": x_reason,
                        "bars_held": i - entry_idx + 1,
                        "raw_pnl_pct": raw_pnl,
                        "net_pnl_pct": net_pnl,
                        "is_win": net_pnl > 0,
                        "mfe_pct": mfe,
                        "mae_pct": mae,
                        "sample": sample,
                        "config": f"EMA_{fast_ema}_{slow_ema}",
                    })
                    pos = 0

            # 2. V2-2 SIGNAL EVALUATION ON COMPLETED CANDLE i
            ema_bull = (prev_f <= prev_s) and (curr_f > curr_s)
            ema_bear = (prev_f >= prev_s) and (curr_f < curr_s)
            macd_bull = (prev_m <= prev_sig) and (curr_m > curr_sig)
            macd_bear = (prev_m >= prev_sig) and (curr_m < curr_sig)

            sig = None
            if ema_bull and macd_bull:
                sig = "BUY"
                active_pending = None
            elif ema_bear and macd_bear:
                sig = "SELL"
                active_pending = None
            else:
                if active_pending is not None:
                    active_pending["elapsed"] += 1
                    direction = active_pending["direction"]
                    leading = active_pending["leading"]
                    elapsed = active_pending["elapsed"]
                    is_invalid = False
                    if direction == "LONG":
                        if leading == "MACD" and curr_m < curr_sig:
                            is_invalid = True
                        elif leading == "EMA" and curr_f < curr_s:
                            is_invalid = True
                    elif direction == "SHORT":
                        if leading == "MACD" and curr_m > curr_sig:
                            is_invalid = True

                    if is_invalid or elapsed > 2:
                        active_pending = None
                    else:
                        if direction == "LONG":
                            if leading == "MACD" and ema_bull:
                                sig = "BUY"
                                active_pending = None
                            elif leading == "EMA" and macd_bull:
                                sig = "BUY"
                                active_pending = None
                        elif direction == "SHORT":
                            if leading == "MACD" and ema_bear:
                                sig = "SELL"
                                active_pending = None

                if active_pending is None and sig is None:
                    if macd_bull and not ema_bull:
                        active_pending = {"direction": "LONG", "leading": "MACD", "elapsed": 0}
                    elif ema_bull and not macd_bull:
                        active_pending = {"direction": "LONG", "leading": "EMA", "elapsed": 0}
                    elif macd_bear and not ema_bear:
                        active_pending = {"direction": "SHORT", "leading": "MACD", "elapsed": 0}

            # 3. SIGNAL EXECUTION AT NEXT BAR OPEN
            if sig is not None and not exited_this_bar:
                next_entry_idx = i + 1
                next_entry_px = open_px[next_entry_idx]
                next_entry_time = times[next_entry_idx]

                if pos == 0:
                    pos = 1 if sig == "BUY" else -1
                    entry_px = next_entry_px
                    entry_time = next_entry_time
                    entry_idx = next_entry_idx
                elif (pos == 1 and sig == "SELL") or (pos == -1 and sig == "BUY"):
                    # Controlled Reversal
                    dir_mult = 1.0 if pos == 1 else -1.0
                    raw_pnl = ((next_entry_px - entry_px) / entry_px) * 100.0 * dir_mult
                    net_pnl = raw_pnl - friction

                    slice_highs = high_px[entry_idx:next_entry_idx]
                    slice_lows = low_px[entry_idx:next_entry_idx]
                    if pos == 1:
                        mfe = ((slice_highs.max() - entry_px) / entry_px) * 100.0
                        mae = ((entry_px - slice_lows.min()) / entry_px) * 100.0
                    else:
                        mfe = ((entry_px - slice_lows.min()) / entry_px) * 100.0
                        mae = ((slice_highs.max() - entry_px) / entry_px) * 100.0

                    entry_ts = pd.to_datetime(entry_time)
                    if entry_ts.tzinfo is not None:
                        is_split = IS_SPLIT_DATE.tz_convert(entry_ts.tz)
                    else:
                        entry_ts = entry_ts.tz_localize("UTC")
                        is_split = IS_SPLIT_DATE
                    sample = "IS" if entry_ts < is_split else "OOS"

                    all_trades.append({
                        "symbol": sym,
                        "sector": sector,
                        "direction": "LONG" if pos == 1 else "SHORT",
                        "entry_time": entry_time,
                        "exit_time": next_entry_time,
                        "entry_price": entry_px,
                        "exit_price": next_entry_px,
                        "exit_reason": "V2-2_REVERSAL",
                        "bars_held": next_entry_idx - entry_idx,
                        "raw_pnl_pct": raw_pnl,
                        "net_pnl_pct": net_pnl,
                        "is_win": net_pnl > 0,
                        "mfe_pct": mfe,
                        "mae_pct": mae,
                        "sample": sample,
                        "config": f"EMA_{fast_ema}_{slow_ema}",
                    })
                    # Flip to opposite
                    pos = 1 if sig == "BUY" else -1
                    entry_px = next_entry_px
                    entry_time = next_entry_time
                    entry_idx = next_entry_idx

    df_res = pd.DataFrame(all_trades)
    if not df_res.empty:
        df_res["entry_time"] = pd.to_datetime(df_res["entry_time"])
        df_res["exit_time"] = pd.to_datetime(df_res["exit_time"])
        df_res = df_res.sort_values("entry_time").reset_index(drop=True)
    return df_res


def calculate_comprehensive_metrics(trades_df: pd.DataFrame, label: str = "") -> Dict[str, Any]:
    """Computes all portfolio risk-gate metrics, CAGR, Sharpe, drawdown, and stats."""
    if trades_df.empty:
        return {"label": label, "trade_count": 0}

    n = len(trades_df)
    net_pnls = trades_df["net_pnl_pct"].values
    wins = net_pnls[net_pnls > 0]
    losses = net_pnls[net_pnls < 0]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / n) * 100.0 if n > 0 else 0.0

    sum_wins = float(np.sum(wins)) if win_count > 0 else 0.0
    sum_losses = float(np.abs(np.sum(losses))) if loss_count > 0 else 0.0
    profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)

    total_return_pct = float(np.sum(net_pnls))
    expectancy_pct = float(np.mean(net_pnls)) if n > 0 else 0.0
    avg_win = float(np.mean(wins)) if win_count > 0 else 0.0
    avg_loss = float(np.abs(np.mean(losses))) if loss_count > 0 else 0.0

    # Drawdown calculation on cumulative equity curve
    cum_returns = np.cumsum(net_pnls)
    peak = np.maximum.accumulate(cum_returns)
    drawdowns = peak - cum_returns
    max_dd_pct = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Sharpe ratio (annualized assuming 252 trading days, ~7 bars/day = ~1764 bars/yr)
    std_pnl = float(np.std(net_pnls)) if len(net_pnls) > 1 else 1.0
    # Average trade frequency per year
    t_start = trades_df["entry_time"].min()
    t_end = trades_df["exit_time"].max()
    days = max(1.0, (t_end - t_start).total_seconds() / 86400.0)
    years = days / 365.25
    trades_per_year = n / years if years > 0 else n
    sharpe = (expectancy_pct / std_pnl * np.sqrt(trades_per_year)) if std_pnl > 0 else 0.0

    # CAGR: Compounded Annual Growth Rate based on portfolio allocation model
    # Standard OpenAlgo portfolio attribution: (1 + total_return/100)^(1/years) - 1
    # If total_return is cumulative percentage points, CAGR = total_return / years
    cagr_pct = total_return_pct / years if years > 0 else 0.0

    # Holding times
    bars = trades_df["bars_held"].values
    avg_bars = float(np.mean(bars)) if len(bars) > 0 else 0.0
    median_bars = float(np.median(bars)) if len(bars) > 0 else 0.0

    # Risk Gates
    gates = [
        {"name": "1. Risk-Adjusted Return (Sharpe)", "target": "Sharpe >= 1.00", "actual": f"{sharpe:.2f}", "passed": bool(sharpe >= 1.00)},
        {"name": "2. Compound Annual Return (CAGR)", "target": "CAGR >= 7.0%", "actual": f"{cagr_pct:.1f}%", "passed": bool(cagr_pct >= 7.0)},
        {"name": "3. Profit Factor", "target": "Profit Factor >= 1.30", "actual": f"{profit_factor:.2f}", "passed": bool(profit_factor >= 1.30)},
        {"name": "4. Maximum Drawdown (MDD)", "target": "Max DD <= 20.0%", "actual": f"{max_dd_pct:.1f}%", "passed": bool(max_dd_pct <= 20.0)},
        {"name": "5. Win Rate", "target": "Win Rate >= 40.0%", "actual": f"{win_rate:.1f}%", "passed": bool(win_rate >= 40.0)},
        {"name": "6. Sample Size", "target": "Trade Count >= 100", "actual": f"{n}", "passed": bool(n >= 100)},
        {"name": "7. Trade Expectancy", "target": "Expectancy > 0.0%", "actual": f"{expectancy_pct:.3f}%", "passed": bool(expectancy_pct > 0.0)},
    ]
    passed_count = sum(1 for g in gates if g["passed"])

    return {
        "label": label,
        "trade_count": n,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 3),
        "expectancy_pct": round(expectancy_pct, 4),
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "win_loss_ratio": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0,
        "avg_bars_held": round(avg_bars, 1),
        "median_bars_held": round(median_bars, 1),
        "years": round(years, 2),
        "gates": gates,
        "passed_gates_count": passed_count,
        "total_gates_count": len(gates),
        "overall_passed": passed_count == len(gates),
    }


def main():
    print("=" * 80)
    print("🚀 STARTING ISOLATED EMA 9/26 VS EMA 10/28 CONTROLLED BACKTEST AUDIT")
    print("=" * 80)

    data_map = load_or_download_all_data()
    print(f"Loaded {len(data_map)} validated instruments from data directory.")

    # 1. Run Baseline (EMA 9/26)
    print("\n[1/4] Running Baseline Engine: Fast EMA 9 / Slow EMA 26...")
    df_base = run_state_machine_for_config(data_map, fast_ema=9, slow_ema=26)
    df_base.to_csv(OUTPUT_DIR / "trades_baseline_ema9_26.csv", index=False)
    print(f"  -> Generated {len(df_base)} trades for Baseline (9/26).")

    # 2. Run Candidate (EMA 10/28)
    print("\n[2/4] Running Candidate Engine: Fast EMA 10 / Slow EMA 28...")
    df_cand = run_state_machine_for_config(data_map, fast_ema=10, slow_ema=28)
    df_cand.to_csv(OUTPUT_DIR / "trades_candidate_ema10_28.csv", index=False)
    print(f"  -> Generated {len(df_cand)} trades for Candidate (10/28).")

    # 3. Compute Metrics Breakdown
    print("\n[3/4] Computing Sub-Segment & In-Sample / Out-of-Sample Metrics...")
    
    comparisons = []
    configs = [("Baseline (EMA 9/26)", df_base), ("Candidate (EMA 10/28)", df_cand)]
    
    for cfg_name, df_cfg in configs:
        # Full
        m_full = calculate_comprehensive_metrics(df_cfg, label=f"{cfg_name} - Overall")
        # In-Sample
        m_is = calculate_comprehensive_metrics(df_cfg[df_cfg["sample"] == "IS"], label=f"{cfg_name} - In-Sample (<2025-07-01)")
        # Out-of-Sample
        m_oos = calculate_comprehensive_metrics(df_cfg[df_cfg["sample"] == "OOS"], label=f"{cfg_name} - Out-of-Sample (>=2025-07-01)")
        # Long Only
        m_long = calculate_comprehensive_metrics(df_cfg[df_cfg["direction"] == "LONG"], label=f"{cfg_name} - Long Only")
        # Short Only
        m_short = calculate_comprehensive_metrics(df_cfg[df_cfg["direction"] == "SHORT"], label=f"{cfg_name} - Short Only")

        comparisons.extend([m_full, m_is, m_oos, m_long, m_short])

    df_comp = pd.DataFrame(comparisons)
    df_comp.to_csv(OUTPUT_DIR / "performance_comparison.csv", index=False)

    # 4. Friction Stress Testing
    print("\n[4/4] Running Friction Sensitivity Stress Tests (0.05%, 0.07%, 0.10%, 0.15%)...")
    friction_results = []
    for f_level in [0.05, 0.07, 0.10, 0.15]:
        t_base_f = run_state_machine_for_config(data_map, 9, 26, friction=f_level)
        t_cand_f = run_state_machine_for_config(data_map, 10, 28, friction=f_level)
        
        m_b = calculate_comprehensive_metrics(t_base_f, label=f"EMA 9/26 (Friction {f_level}%)")
        m_c = calculate_comprehensive_metrics(t_cand_f, label=f"EMA 10/28 (Friction {f_level}%)")
        friction_results.extend([m_b, m_c])

    df_fric = pd.DataFrame(friction_results)
    df_fric.to_csv(OUTPUT_DIR / "stress_friction_comparison.csv", index=False)

    # 5. Sector Breakdown
    sectors = sorted(list(set(df_base["sector"].dropna().unique())))
    sector_rows = []
    for sec in sectors:
        sb = df_base[df_base["sector"] == sec]
        sc = df_cand[df_cand["sector"] == sec]
        mb = calculate_comprehensive_metrics(sb, label=f"EMA 9/26 - Sector: {sec}")
        mc = calculate_comprehensive_metrics(sc, label=f"EMA 10/28 - Sector: {sec}")
        sector_rows.extend([mb, mc])
    df_sec = pd.DataFrame(sector_rows)
    df_sec.to_csv(OUTPUT_DIR / "sector_breakdown.csv", index=False)

    # 6. Save JSON Summary
    summary_data = {
        "metadata": {
            "dataset_instruments_count": len(data_map),
            "date_range_start": "2023-09-29",
            "date_range_end": "2026-09-09",
            "in_sample_cutoff": "2025-07-01",
            "friction_base": FRICTION_PCT,
            "long_tp": LONG_TP_PCT,
            "short_tp": SHORT_TP_PCT,
            "catastrophe_sl": CATASTROPHE_SL_PCT,
        },
        "baseline_summary": calculate_comprehensive_metrics(df_base, label="Baseline (9/26)"),
        "candidate_summary": calculate_comprehensive_metrics(df_cand, label="Candidate (10/28)"),
    }
    with open(OUTPUT_DIR / "ema_comparison_summary.json", "w") as f:
        json.dump(summary_data, f, indent=2)

    print("\n" + "=" * 80)
    print("✅ AUDIT BACKTEST COMPLETED SUCCESSFULLY!")
    print(f"Results saved to: {OUTPUT_DIR}")
    print("=" * 80)


if __name__ == "__main__":
    main()
