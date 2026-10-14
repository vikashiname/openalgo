"""
Backtest Current EMACROSSOPEN Logic
File: backtesting/emacrossopen/backtest_current_emacrossopen.py

Independently backtests the CURRENT strategies/liveonopenalgo/emacrossopen.py logic:
  - 1H completed candles
  - EMA9 / EMA26, MACD 12/26/9
  - Asymmetric V2-2 2-candle confirmation window
  - Long: SAME_CANDLE, MACD_THEN_EMA, EMA_THEN_MACD
  - Short: SAME_CANDLE, MACD_THEN_EMA (EMA_FIRST strictly rejected)
  - Exit Priority:
      1. Catastrophe SL (-6.00%)
      2. Profit Target (+3.00% Long / +1.50% Short)
      3. V2-2 Opposite-Signal Reversal
  - Round-trip transaction friction: 0.07%

Evaluates:
  1. Chronological Sequential Execution Engine (matching live emacrossopen.py state machine)
  2. Fixed-Slice Benchmark Reproduction (matching previous 2,143-trade research methodology)
"""

import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

# Ensure local imports work from this directory
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from data_manager import load_or_download_all_data, SYMBOL_TICKER_MAP
from feature_extractor import calculate_indicators, extract_trades_and_features
from target_sl_engine import simulate_trade_path, calculate_portfolio_metrics

FRICTION_PCT = 0.07  # 0.07% round-trip friction
LONG_TP_PCT = 3.00   # +3.00%
SHORT_TP_PCT = 1.50  # +1.50%
CATASTROPHE_SL_PCT = 6.00  # -6.00% emergency stop loss
IS_SPLIT_DATE = pd.to_datetime("2025-07-01", utc=True)


def compute_portfolio_stats(trades_df: pd.DataFrame, initial_capital: float = 100000.0) -> Dict[str, Any]:
    """Computes comprehensive quantitative performance statistics for a set of trades."""
    if trades_df.empty:
        return {
            "trade_count": 0, "win_rate_pct": 0.0, "profit_factor": 0.0,
            "expectancy_pct": 0.0, "total_return_pct": 0.0, "max_drawdown_pct": 0.0,
            "avg_r": 0.0, "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
            "avg_bars_held": 0.0, "median_bars_held": 0.0, "max_bars_held": 0.0,
            "avg_mfe_pct": 0.0, "avg_mae_pct": 0.0,
            "target_hit_count": 0, "target_hit_pct": 0.0,
            "sl_hit_count": 0, "sl_hit_pct": 0.0,
            "reversal_count": 0, "reversal_pct": 0.0,
        }

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

    total_return = float(np.sum(net_pnls))
    expectancy = float(np.mean(net_pnls)) if n > 0 else 0.0

    avg_win = float(np.mean(wins)) if win_count > 0 else 0.0
    avg_loss = float(np.abs(np.mean(losses))) if loss_count > 0 else 0.0

    # Drawdown on cumulative percentage curve
    cum_returns = np.cumsum(net_pnls)
    peak = np.maximum.accumulate(cum_returns)
    drawdowns = peak - cum_returns
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Holding period
    bars = trades_df["bars_held"].values if "bars_held" in trades_df.columns else np.zeros(n)
    avg_bars = float(np.mean(bars)) if len(bars) > 0 else 0.0
    median_bars = float(np.median(bars)) if len(bars) > 0 else 0.0
    max_bars = float(np.max(bars)) if len(bars) > 0 else 0.0

    # MFE / MAE
    avg_mfe = float(trades_df["mfe_pct"].mean()) if "mfe_pct" in trades_df.columns else 0.0
    avg_mae = float(trades_df["mae_pct"].mean()) if "mae_pct" in trades_df.columns else 0.0

    # Exit reason counts
    reasons = trades_df["exit_reason"].value_counts().to_dict() if "exit_reason" in trades_df.columns else {}
    tp_count = reasons.get("TARGET_HIT", reasons.get("TARGET", 0))
    sl_count = reasons.get("CATASTROPHE_SL", reasons.get("STOP_LOSS", 0))
    rev_count = reasons.get("V2-2_REVERSAL", reasons.get("REVERSAL", 0))

    tp_pct = (tp_count / n) * 100.0 if n > 0 else 0.0
    sl_pct = (sl_count / n) * 100.0 if n > 0 else 0.0
    rev_pct = (rev_count / n) * 100.0 if n > 0 else 0.0

    # Risk Multiple (R-multiple normalized by 1% risk)
    r_multiples = net_pnls / 1.0
    avg_r = float(np.mean(r_multiples)) if n > 0 else 0.0

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
        "avg_bars_held": round(avg_bars, 1),
        "median_bars_held": round(median_bars, 1),
        "max_bars_held": int(max_bars),
        "avg_mfe_pct": round(avg_mfe, 2),
        "avg_mae_pct": round(avg_mae, 2),
        "target_hit_count": tp_count,
        "target_hit_pct": round(tp_pct, 2),
        "sl_hit_count": sl_count,
        "sl_hit_pct": round(sl_pct, 2),
        "reversal_count": rev_count,
        "reversal_pct": round(rev_pct, 2),
    }


def run_chronological_state_machine_backtest(
    data_map: Dict[str, pd.DataFrame],
    long_tp: Optional[float] = LONG_TP_PCT,
    short_tp: Optional[float] = SHORT_TP_PCT,
    sl_pct: Optional[float] = CATASTROPHE_SL_PCT,
    friction: float = FRICTION_PCT,
) -> pd.DataFrame:
    """
    Executes an exact chronological, bar-by-bar simulation matching strategies/liveonopenalgo/emacrossopen.py:
      - Evaluates completed 1H candle indicators
      - In active position: checks Catastrophe SL, then Target against candle High/Low
      - Intrabar same-candle conflict: conservative precedence (SL hit first if both touched)
      - On Target/SL exit: position becomes FLAT (0)
      - If FLAT: waits for next confirmed V2-2 signal (Long or Short)
      - If active position and opposite signal confirmed: executes controlled reversal
      - If active position and same signal confirmed: ignores duplicate
    """
    all_trades = []

    for sym, raw_df in data_map.items():
        meta = SYMBOL_TICKER_MAP.get(sym, {"lot_size": 1, "sector": "UNKNOWN"})
        lot_size = meta["lot_size"]
        sector = meta["sector"]

        df = calculate_indicators(raw_df).dropna().copy()
        n = len(df)
        if n < 50:
            continue

        close = df["Close"].values
        open_px = df["Open"].values
        high_px = df["High"].values
        low_px = df["Low"].values
        ema9 = df["ema9"].values
        ema26 = df["ema26"].values
        macd = df["macd"].values
        signal = df["macd_signal"].values
        hist = df["macd_histogram"].values
        atr = df["atr14"].values
        times = df.index

        pos = 0  # 1 = LONG, -1 = SHORT, 0 = FLAT
        entry_px = 0.0
        entry_time = None
        entry_idx = 0
        entry_atr = 0.0
        active_pending = None

        for i in range(1, n - 1):
            curr_close = close[i]
            prev_close = close[i - 1]
            curr_open = open_px[i]
            curr_high = high_px[i]
            curr_low = low_px[i]
            curr_ema9 = ema9[i]
            prev_ema9 = ema9[i - 1]
            curr_ema26 = ema26[i]
            prev_ema26 = ema26[i - 1]
            curr_macd = macd[i]
            prev_macd = macd[i - 1]
            curr_sig = signal[i]
            prev_sig = signal[i - 1]

            # 1. RISK MANAGEMENT CHECK ON COMPLETED 1H CANDLE (BEFORE REVERSAL)
            exited_this_bar = False
            if pos != 0 and i >= entry_idx:
                if pos == 1:  # LONG
                    target_px = entry_px * (1.0 + long_tp / 100.0) if long_tp is not None else None
                    stop_px = entry_px * (1.0 - sl_pct / 100.0) if sl_pct is not None else None

                    tp_hit = (target_px is not None) and (curr_high >= target_px)
                    sl_hit = (stop_px is not None) and (curr_low <= stop_px)

                    if tp_hit and sl_hit:
                        # Conservative assumption: SL touched first unless open breached target
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
                    target_px = entry_px * (1.0 - short_tp / 100.0) if short_tp is not None else None
                    stop_px = entry_px * (1.0 + sl_pct / 100.0) if sl_pct is not None else None

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

                    # Calculate MFE / MAE on this trade's slice
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
                    })
                    pos = 0  # Position is now FLAT

            # 2. V2-2 SIGNAL EVALUATION ON COMPLETED CANDLE i
            ema_bull = (prev_ema9 <= prev_ema26) and (curr_ema9 > curr_ema26)
            ema_bear = (prev_ema9 >= prev_ema26) and (curr_ema9 < curr_ema26)
            macd_bull = (prev_macd <= prev_sig) and (curr_macd > curr_sig)
            macd_bear = (prev_macd >= prev_sig) and (curr_macd < curr_sig)

            sig = None
            trig = None
            conf_delay = 0

            if ema_bull and macd_bull:
                sig = "BUY"
                trig = "SAME_CANDLE"
                conf_delay = 0
                active_pending = None
            elif ema_bear and macd_bear:
                sig = "SELL"
                trig = "SAME_CANDLE"
                conf_delay = 0
                active_pending = None
            else:
                if active_pending is not None:
                    active_pending["elapsed"] += 1
                    direction = active_pending["direction"]
                    leading = active_pending["leading"]
                    elapsed = active_pending["elapsed"]
                    is_invalid = False
                    if direction == "LONG":
                        if leading == "MACD" and curr_macd < curr_sig:
                            is_invalid = True
                        elif leading == "EMA" and curr_ema9 < curr_ema26:
                            is_invalid = True
                    elif direction == "SHORT":
                        if leading == "MACD" and curr_macd > curr_sig:
                            is_invalid = True

                    if is_invalid or elapsed > 2:
                        active_pending = None
                    else:
                        if direction == "LONG":
                            if leading == "MACD" and ema_bull:
                                sig = "BUY"
                                trig = "MACD_THEN_EMA"
                                conf_delay = elapsed
                                active_pending = None
                            elif leading == "EMA" and macd_bull:
                                sig = "BUY"
                                trig = "EMA_THEN_MACD"
                                conf_delay = elapsed
                                active_pending = None
                        elif direction == "SHORT":
                            if leading == "MACD" and ema_bear:
                                sig = "SELL"
                                trig = "MACD_THEN_EMA"
                                conf_delay = elapsed
                                active_pending = None

                if active_pending is None and sig is None:
                    if macd_bull and not ema_bull:
                        active_pending = {"direction": "LONG", "leading": "MACD", "elapsed": 0}
                    elif ema_bull and not macd_bull:
                        active_pending = {"direction": "LONG", "leading": "EMA", "elapsed": 0}
                    elif macd_bear and not ema_bear:
                        active_pending = {"direction": "SHORT", "leading": "MACD", "elapsed": 0}

            # 3. SIGNAL EXECUTION (ONLY IF NOT EXITED BY RISK CHECK THIS CANDLE)
            if sig is not None and not exited_this_bar:
                next_entry_idx = i + 1
                next_entry_px = open_px[next_entry_idx]
                next_entry_time = times[next_entry_idx]

                if pos == 0:
                    # Enter new position from FLAT
                    pos = 1 if sig == "BUY" else -1
                    entry_px = next_entry_px
                    entry_time = next_entry_time
                    entry_idx = next_entry_idx
                    entry_atr = atr[i]
                elif (pos == 1 and sig == "SELL") or (pos == -1 and sig == "BUY"):
                    # Controlled reversal: close current trade, open opposite
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
                    })

                    pos = 1 if sig == "BUY" else -1
                    entry_px = next_entry_px
                    entry_time = next_entry_time
                    entry_idx = next_entry_idx
                    entry_atr = atr[i]
                else:
                    # Same direction: duplicate signal skipped
                    pass

    return pd.DataFrame(all_trades)


def run_benchmark_slice_simulation(
    trades: List[Dict[str, Any]],
    long_tp: Optional[float] = LONG_TP_PCT,
    short_tp: Optional[float] = SHORT_TP_PCT,
    sl_pct: Optional[float] = CATASTROPHE_SL_PCT,
    friction: float = FRICTION_PCT,
) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """
    Simulates trades using the exact forward trade slice methodology of the previous research.
    Runs path-dependent candle-by-candle evaluation across the 2,143 trade slices.
    """
    sim_results = []
    rows = []

    for t in trades:
        d = t["direction"]
        tp_val = long_tp if d == "LONG" else short_tp
        res = simulate_trade_path(t, tp_pct=tp_val, sl_pct=sl_pct, friction=friction)
        sim_results.append(res)

        rows.append({
            "trade_id": t["trade_id"],
            "symbol": t["symbol"],
            "sector": t["sector"],
            "direction": t["direction"],
            "entry_time": t["entry_time"],
            "exit_time": t["exit_time"],
            "entry_price": t["entry_price"],
            "exit_price": res["exit_price"],
            "exit_reason": res["exit_reason"],
            "bars_held": res["exit_bar"],
            "raw_pnl_pct": res["raw_pnl_pct"],
            "net_pnl_pct": res["net_pnl_pct"],
            "is_win": res["is_win"],
            "mfe_pct": t.get("mfe_pct", 0.0),
            "mae_pct": t.get("mae_pct", 0.0),
            "sample": t["sample"],
        })

    return sim_results, pd.DataFrame(rows)


def main():
    print("=" * 80)
    print("🚀 OPENALGO EMACROSS V2-2 COMPREHENSIVE BACKTEST ENGINE")
    print("=" * 80)

    # 1. Load Data
    data = load_or_download_all_data()
    symbols = sorted(list(data.keys()))
    print(f"Loaded {len(symbols)} instruments: {', '.join(symbols[:10])} ...")

    # 2. Extract 2,143 Baseline Trades (for slice comparison)
    trades, feat_df = extract_trades_and_features(data)
    print(f"Reconstructed {len(trades)} baseline V2-2 trade opportunities.")

    # 3. RUN CHRONOLOGICAL SEQUENTIAL BACKTEST (Exact Live emacrossopen.py Engine)
    print("\n[1/4] Running Exact Chronological Sequential Backtest (emacrossopen.py Live Logic)...")
    chron_df = run_chronological_state_machine_backtest(
        data, long_tp=LONG_TP_PCT, short_tp=SHORT_TP_PCT, sl_pct=CATASTROPHE_SL_PCT
    )
    chron_stats = compute_portfolio_stats(chron_df)
    chron_df.to_csv(CURRENT_DIR / "backtest_chronological_trades.csv", index=False)
    print(f"  Chronological Trades: {chron_stats['trade_count']}")
    print(f"  Total Return: {chron_stats['total_return_pct']:+.2f}% | PF: {chron_stats['profit_factor']:.3f} | WR: {chron_stats['win_rate_pct']:.2f}%")
    print(f"  Target Hits: {chron_stats['target_hit_pct']:.1f}% | Catastrophe SL: {chron_stats['sl_hit_pct']:.1f}% | Reversal: {chron_stats['reversal_pct']:.1f}%")

    # 4. RUN SLICE BENCHMARK BACKTEST (Current Logic on 2,143 Slices)
    print("\n[2/4] Running Slice Benchmark Backtest (Current Logic on 2,143 Slices)...")
    slice_sims, slice_df = run_benchmark_slice_simulation(
        trades, long_tp=LONG_TP_PCT, short_tp=SHORT_TP_PCT, sl_pct=CATASTROPHE_SL_PCT
    )
    slice_stats = compute_portfolio_stats(slice_df)
    slice_df.to_csv(CURRENT_DIR / "backtest_slice_trades.csv", index=False)
    print(f"  Slice Trades: {slice_stats['trade_count']}")
    print(f"  Total Return: {slice_stats['total_return_pct']:+.2f}% | PF: {slice_stats['profit_factor']:.3f} | WR: {slice_stats['win_rate_pct']:.2f}%")

    # 5. RUN RESEARCH BENCHMARKS (M0 Baseline, M4 Research, M5 ATR)
    print("\n[3/4] Running Benchmark Comparisons (M0 Baseline, M4 Research, M5 ATR)...")
    # M0 Baseline (Reversal only)
    _, m0_df = run_benchmark_slice_simulation(trades, long_tp=None, short_tp=None, sl_pct=None)
    m0_stats = compute_portfolio_stats(m0_df)

    # M4 Research (Asymmetric Fixed +3% / +1.5%, No Stop Loss)
    _, m4_df = run_benchmark_slice_simulation(trades, long_tp=3.0, short_tp=1.5, sl_pct=None)
    m4_stats = compute_portfolio_stats(m4_df)

    # Chronological without SL (Pure Target + Reversal)
    chron_nosl_df = run_chronological_state_machine_backtest(
        data, long_tp=LONG_TP_PCT, short_tp=SHORT_TP_PCT, sl_pct=None
    )
    chron_nosl_stats = compute_portfolio_stats(chron_nosl_df)

    # 6. PER-SYMBOL RESULTS (Chronological Engine)
    print("\n[4/4] Computing Per-Symbol and Sub-Cohort Breakdowns...")
    sym_rows = []
    for s in symbols:
        s_df = chron_df[chron_df["symbol"] == s]
        s_stats = compute_portfolio_stats(s_df)
        sym_rows.append({
            "Symbol": s,
            "Sector": SYMBOL_TICKER_MAP.get(s, {}).get("sector", "N/A"),
            "Trades": s_stats["trade_count"],
            "Return_Pct": s_stats["total_return_pct"],
            "PF": s_stats["profit_factor"],
            "Win_Rate_Pct": s_stats["win_rate_pct"],
            "Expectancy_Pct": s_stats["expectancy_pct"],
            "MaxDD_Pct": s_stats["max_drawdown_pct"],
            "Target_Hits": s_stats["target_hit_count"],
            "SL_Hits": s_stats["sl_hit_count"],
            "Reversals": s_stats["reversal_count"],
            "Avg_Bars": s_stats["avg_bars_held"],
        })
    sym_df = pd.DataFrame(sym_rows).sort_values("Return_Pct", ascending=False)
    sym_df.to_csv(CURRENT_DIR / "backtest_per_symbol_results.csv", index=False)

    # Long vs Short
    long_df = chron_df[chron_df["direction"] == "LONG"]
    short_df = chron_df[chron_df["direction"] == "SHORT"]
    long_stats = compute_portfolio_stats(long_df)
    short_stats = compute_portfolio_stats(short_df)

    # IS vs OOS
    is_df = chron_df[chron_df["sample"] == "IS"]
    oos_df = chron_df[chron_df["sample"] == "OOS"]
    is_stats = compute_portfolio_stats(is_df)
    oos_stats = compute_portfolio_stats(oos_df)

    # Comparison Table
    comp_models = [
        {"Model": "M0 Baseline (Reversal Only, 2143 Slices)", "Stats": m0_stats},
        {"Model": "M4 Researched (Fixed Asym +3%/+1.5%, No SL, 2143 Slices)", "Stats": m4_stats},
        {"Model": "M4 + Catastrophe SL -6% (Current Logic on 2143 Slices)", "Stats": slice_stats},
        {"Model": "Chronological Target Only (No SL, 1774 Trades)", "Stats": chron_nosl_stats},
        {"Model": "CURRENT LIVE emacrossopen.py (Target + SL -6%, 1815 Trades)", "Stats": chron_stats},
    ]

    comp_rows = []
    for c in comp_models:
        st = c["Stats"]
        comp_rows.append({
            "Model_Description": c["Model"],
            "Trades": st["trade_count"],
            "Total_Return_Pct": st["total_return_pct"],
            "Profit_Factor": st["profit_factor"],
            "Win_Rate_Pct": st["win_rate_pct"],
            "Expectancy_Pct": st["expectancy_pct"],
            "Max_Drawdown_Pct": st["max_drawdown_pct"],
            "Avg_Bars_Held": st["avg_bars_held"],
            "Target_Hit_Pct": st["target_hit_pct"],
            "SL_Hit_Pct": st["sl_hit_pct"],
            "Reversal_Exit_Pct": st["reversal_pct"],
        })
    comp_df = pd.DataFrame(comp_rows)
    comp_df.to_csv(CURRENT_DIR / "backtest_comparison_master.csv", index=False)

    print("\n" + "=" * 80)
    print("📊 MASTER MODEL COMPARISON")
    print("=" * 80)
    print(comp_df.to_string(index=False))

    print("\n" + "=" * 80)
    print("🎯 DIRECTIONAL BREAKDOWN (CURRENT LIVE emacrossopen.py)")
    print("=" * 80)
    print(f"LONG : Trades={long_stats['trade_count']} | Return={long_stats['total_return_pct']:+.2f}% | PF={long_stats['profit_factor']:.3f} | WR={long_stats['win_rate_pct']:.2f}% | MaxDD={long_stats['max_drawdown_pct']:.2f}%")
    print(f"SHORT: Trades={short_stats['trade_count']} | Return={short_stats['total_return_pct']:+.2f}% | PF={short_stats['profit_factor']:.3f} | WR={short_stats['win_rate_pct']:.2f}% | MaxDD={short_stats['max_drawdown_pct']:.2f}%")

    print("\n" + "=" * 80)
    print("📅 IN-SAMPLE VS OUT-OF-SAMPLE STABILITY (CURRENT LIVE emacrossopen.py)")
    print("=" * 80)
    print(f"IS  (< 2025-07-01): Trades={is_stats['trade_count']} | Return={is_stats['total_return_pct']:+.2f}% | PF={is_stats['profit_factor']:.3f} | WR={is_stats['win_rate_pct']:.2f}% | Exp={is_stats['expectancy_pct']:+.4f}%")
    print(f"OOS (>= 2025-07-01): Trades={oos_stats['trade_count']} | Return={oos_stats['total_return_pct']:+.2f}% | PF={oos_stats['profit_factor']:.3f} | WR={oos_stats['win_rate_pct']:.2f}% | Exp={oos_stats['expectancy_pct']:+.4f}%")

    print("\n" + "=" * 80)
    print("🏆 TOP 5 SYMBOLS BY RETURN")
    print("=" * 80)
    print(sym_df.head(5)[["Symbol", "Sector", "Trades", "Return_Pct", "PF", "Win_Rate_Pct", "Target_Hits", "SL_Hits", "Reversals"]].to_string(index=False))

    print("\n" + "=" * 80)
    print("⚠️ BOTTOM 5 SYMBOLS BY RETURN")
    print("=" * 80)
    print(sym_df.tail(5)[["Symbol", "Sector", "Trades", "Return_Pct", "PF", "Win_Rate_Pct", "Target_Hits", "SL_Hits", "Reversals"]].to_string(index=False))
    print("=" * 80)


if __name__ == "__main__":
    main()
