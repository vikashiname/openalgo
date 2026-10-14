"""
Ultra-Fast Quantitative Backtest Harness for AutoResearch
File: backtesting/emacrossopen/autoresearch/backtest_harness.py

High-performance chronological state-machine simulation engine across multi-symbol universes.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

IS_SPLIT_DATE = pd.to_datetime("2025-07-01")

# Default Asymmetric Universe classifications from baseline empirical research
TOP_LONGS = {"SUNPHARMA", "BAJAJ-AUTO", "BPCL", "WIPRO", "TATASTEEL", "BAJFINANCE", "NTPC", "POWERGRID", "M&M"}
TOP_SHORTS = {"SUNPHARMA", "BAJAJ-AUTO", "M&M", "BPCL", "NTPC", "NIFTY", "BANKNIFTY"}
BLACKLIST_AVOID = {"ITC", "ONGC", "ADANIENT", "DRREDDY", "INFY"}


def compute_metrics(trades_df: pd.DataFrame) -> Dict[str, Any]:
    """Computes standard institutional quant metrics for a trades DataFrame."""
    if trades_df.empty:
        return {
            "trade_count": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "expectancy": 0.0, "total_return": 0.0, "max_drawdown": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "avg_bars": 0.0,
        }

    pnls = trades_df["net_pnl_pct"].values
    n = len(pnls)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    win_count = len(wins)
    win_rate = (win_count / n) * 100.0 if n > 0 else 0.0

    sum_wins = float(np.sum(wins)) if win_count > 0 else 0.0
    sum_losses = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.0
    pf = (sum_wins / sum_losses) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)

    total_return = float(np.sum(pnls))
    expectancy = float(np.mean(pnls)) if n > 0 else 0.0

    avg_win = float(np.mean(wins)) if win_count > 0 else 0.0
    avg_loss = float(np.abs(np.mean(losses))) if len(losses) > 0 else 0.0

    cum_returns = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum_returns)
    dd = peak - cum_returns
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0

    bars = trades_df["bars_held"].values if "bars_held" in trades_df.columns else np.zeros(n)
    avg_bars = float(np.mean(bars)) if len(bars) > 0 else 0.0

    return {
        "trade_count": n,
        "win_rate": round(win_rate, 2),
        "profit_factor": round(pf, 3),
        "expectancy": round(expectancy, 4),
        "total_return": round(total_return, 2),
        "max_drawdown": round(max_dd, 2),
        "avg_win": round(avg_win, 3),
        "avg_loss": round(avg_loss, 3),
        "avg_bars": round(avg_bars, 1),
    }


def run_single_symbol_backtest(
    df: pd.DataFrame,
    symbol: str,
    fast_ema: int = 9,
    slow_ema: int = 26,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_sig: int = 9,
    direction_mode: str = "SYMMETRICAL",  # 'SYMMETRICAL', 'LONG_ONLY', 'SHORT_ONLY', 'ASYMMETRIC'
    exit_type: str = "REVERSAL",          # 'REVERSAL', 'TARGET_SL', 'EMA26_EXIT', 'ATR_TRAILING'
    long_tp_pct: float = 3.0,
    short_tp_pct: float = 1.5,
    sl_pct: float = 6.0,
    atr_mult: float = 2.0,
    friction: float = 0.07,              # 0.07% round-trip
    htf_bias_series: Optional[pd.Series] = None,
) -> List[Dict[str, Any]]:
    """Runs high-speed chronological simulation on one instrument."""
    n = len(df)
    if n < 40:
        return []

    # Filter by Asymmetric Universe
    allow_long_entry = True
    allow_short_entry = True
    if direction_mode == "LONG_ONLY":
        allow_short_entry = False
    elif direction_mode == "SHORT_ONLY":
        allow_long_entry = False
    elif direction_mode == "ASYMMETRIC":
        if symbol in BLACKLIST_AVOID:
            return []
        allow_long_entry = symbol in TOP_LONGS
        allow_short_entry = symbol in TOP_SHORTS
        if not allow_long_entry and not allow_short_entry:
            return []

    close = df["Close"].values
    open_px = df["Open"].values
    high_px = df["High"].values
    low_px = df["Low"].values
    times = df.index

    # Technical Indicators
    s_close = pd.Series(close)
    ema_fast_s = s_close.ewm(span=fast_ema, adjust=False).mean().values
    ema_slow_s = s_close.ewm(span=slow_ema, adjust=False).mean().values
    macd_s = (s_close.ewm(span=macd_fast, adjust=False).mean() - s_close.ewm(span=macd_slow, adjust=False).mean()).values
    sig_s = pd.Series(macd_s).ewm(span=macd_sig, adjust=False).mean().values

    # ATR if needed
    if exit_type == "ATR_TRAILING":
        s_high = pd.Series(high_px)
        s_low = pd.Series(low_px)
        tr = np.maximum(
            s_high - s_low,
            np.maximum(np.abs(s_high - s_close.shift(1)), np.abs(s_low - s_close.shift(1)))
        )
        atr_vals = tr.rolling(14).mean().bfill().values
    else:
        atr_vals = np.zeros(n)

    # Reindex HTF bias to LTF timestamps safely
    if htf_bias_series is not None:
        htf_s = htf_bias_series.copy()
        if hasattr(htf_s.index, "tz") and htf_s.index.tz is not None:
            htf_s.index = htf_s.index.tz_localize(None)
        df_idx = df.index
        if hasattr(df_idx, "tz") and df_idx.tz is not None:
            df_idx = df_idx.tz_localize(None)
        htf_aligned = htf_s.reindex(df_idx, method="ffill").fillna(0).values
    else:
        htf_aligned = None

    pos = 0  # 1 = LONG, -1 = SHORT, 0 = FLAT
    entry_px = 0.0
    entry_time = None
    entry_idx = 0
    highest_px = 0.0
    lowest_px = 0.0
    trades = []
    active_pending = None

    for i in range(1, n - 1):
        curr_c = close[i]
        curr_h = high_px[i]
        curr_l = low_px[i]
        curr_o = open_px[i]

        curr_ef = ema_fast_s[i]
        prev_ef = ema_fast_s[i - 1]
        curr_es = ema_slow_s[i]
        prev_es = ema_slow_s[i - 1]

        curr_m = macd_s[i]
        prev_m = macd_s[i - 1]
        curr_sig = sig_s[i]
        prev_sig = sig_s[i - 1]

        # 1. RISK EXIT CHECK (if in active position)
        exited_this_bar = False
        if pos != 0:
            highest_px = max(highest_px, curr_h)
            lowest_px = min(lowest_px, curr_l)

            if exit_type == "TARGET_SL":
                if pos == 1:
                    tp = entry_px * (1.0 + long_tp_pct / 100.0)
                    sl = entry_px * (1.0 - sl_pct / 100.0)
                    if curr_l <= sl:
                        x_px = curr_o if curr_o <= sl else sl
                        raw_pnl = ((x_px - entry_px) / entry_px) * 100.0
                        trades.append({
                            "symbol": symbol, "direction": "LONG", "entry_time": entry_time,
                            "exit_time": times[i], "net_pnl_pct": raw_pnl - friction,
                            "bars_held": i - entry_idx + 1, "exit_reason": "SL"
                        })
                        pos = 0
                        exited_this_bar = True
                    elif curr_h >= tp:
                        x_px = curr_o if curr_o >= tp else tp
                        raw_pnl = ((x_px - entry_px) / entry_px) * 100.0
                        trades.append({
                            "symbol": symbol, "direction": "LONG", "entry_time": entry_time,
                            "exit_time": times[i], "net_pnl_pct": raw_pnl - friction,
                            "bars_held": i - entry_idx + 1, "exit_reason": "TP"
                        })
                        pos = 0
                        exited_this_bar = True
                else:  # SHORT
                    tp = entry_px * (1.0 - short_tp_pct / 100.0)
                    sl = entry_px * (1.0 + sl_pct / 100.0)
                    if curr_h >= sl:
                        x_px = curr_o if curr_o >= sl else sl
                        raw_pnl = ((entry_px - x_px) / entry_px) * 100.0
                        trades.append({
                            "symbol": symbol, "direction": "SHORT", "entry_time": entry_time,
                            "exit_time": times[i], "net_pnl_pct": raw_pnl - friction,
                            "bars_held": i - entry_idx + 1, "exit_reason": "SL"
                        })
                        pos = 0
                        exited_this_bar = True
                    elif curr_l <= tp:
                        x_px = curr_o if curr_o <= tp else tp
                        raw_pnl = ((entry_px - x_px) / entry_px) * 100.0
                        trades.append({
                            "symbol": symbol, "direction": "SHORT", "entry_time": entry_time,
                            "exit_time": times[i], "net_pnl_pct": raw_pnl - friction,
                            "bars_held": i - entry_idx + 1, "exit_reason": "TP"
                        })
                        pos = 0
                        exited_this_bar = True

            elif exit_type == "EMA26_EXIT":
                if pos == 1 and curr_c < curr_es:
                    nxt_o = open_px[i + 1]
                    raw_pnl = ((nxt_o - entry_px) / entry_px) * 100.0
                    trades.append({
                        "symbol": symbol, "direction": "LONG", "entry_time": entry_time,
                        "exit_time": times[i + 1], "net_pnl_pct": raw_pnl - friction,
                        "bars_held": i - entry_idx + 1, "exit_reason": "EMA26_EXIT"
                    })
                    pos = 0
                    exited_this_bar = True
                elif pos == -1 and curr_c > curr_es:
                    nxt_o = open_px[i + 1]
                    raw_pnl = ((entry_px - nxt_o) / entry_px) * 100.0
                    trades.append({
                        "symbol": symbol, "direction": "SHORT", "entry_time": entry_time,
                        "exit_time": times[i + 1], "net_pnl_pct": raw_pnl - friction,
                        "bars_held": i - entry_idx + 1, "exit_reason": "EMA26_EXIT"
                    })
                    pos = 0
                    exited_this_bar = True

            elif exit_type == "ATR_TRAILING":
                trail_stop = highest_px - (atr_vals[i] * atr_mult) if pos == 1 else lowest_px + (atr_vals[i] * atr_mult)
                if pos == 1 and curr_l <= trail_stop:
                    x_px = curr_o if curr_o <= trail_stop else trail_stop
                    raw_pnl = ((x_px - entry_px) / entry_px) * 100.0
                    trades.append({
                        "symbol": symbol, "direction": "LONG", "entry_time": entry_time,
                        "exit_time": times[i], "net_pnl_pct": raw_pnl - friction,
                        "bars_held": i - entry_idx + 1, "exit_reason": "ATR_TRAIL"
                    })
                    pos = 0
                    exited_this_bar = True
                elif pos == -1 and curr_h >= trail_stop:
                    x_px = curr_o if curr_o >= trail_stop else trail_stop
                    raw_pnl = ((entry_px - x_px) / entry_px) * 100.0
                    trades.append({
                        "symbol": symbol, "direction": "SHORT", "entry_time": entry_time,
                        "exit_time": times[i], "net_pnl_pct": raw_pnl - friction,
                        "bars_held": i - entry_idx + 1, "exit_reason": "ATR_TRAIL"
                    })
                    pos = 0
                    exited_this_bar = True

        # 2. SIGNAL DETECTION (V2-2 Confluence)
        ema_bull = (prev_ef <= prev_es) and (curr_ef > curr_es)
        ema_bear = (prev_ef >= prev_es) and (curr_ef < curr_es)
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
                    elif leading == "EMA" and curr_ef < curr_es:
                        is_invalid = True
                elif direction == "SHORT":
                    if leading == "MACD" and curr_m > curr_sig:
                        is_invalid = True

                if is_invalid or elapsed > 2:
                    active_pending = None
                else:
                    if direction == "LONG":
                        if (leading == "MACD" and ema_bull) or (leading == "EMA" and macd_bull):
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

        # Apply HTF Trend Filter if active (only affects entries)
        if sig is not None and htf_aligned is not None:
            htf_val = htf_aligned[i]
            if sig == "BUY" and htf_val < 0:
                sig = None
            elif sig == "SELL" and htf_val > 0:
                sig = None

        # 3. EXECUTION LOGIC (WITH LONG-ONLY / SHORT-ONLY PROPER EXIT HANDLING)
        if sig is not None and not exited_this_bar:
            nxt_open = open_px[i + 1]
            nxt_time = times[i + 1]

            # Case A: Currently FLAT
            if pos == 0:
                if sig == "BUY" and allow_long_entry:
                    pos = 1
                    entry_px = nxt_open
                    entry_time = nxt_time
                    entry_idx = i + 1
                    highest_px = nxt_open
                    lowest_px = nxt_open
                elif sig == "SELL" and allow_short_entry:
                    pos = -1
                    entry_px = nxt_open
                    entry_time = nxt_time
                    entry_idx = i + 1
                    highest_px = nxt_open
                    lowest_px = nxt_open

            # Case B: Currently in LONG position
            elif pos == 1 and sig == "SELL":
                # Close LONG trade
                raw_pnl = ((nxt_open - entry_px) / entry_px) * 100.0
                trades.append({
                    "symbol": symbol,
                    "direction": "LONG",
                    "entry_time": entry_time,
                    "exit_time": nxt_time,
                    "net_pnl_pct": raw_pnl - friction,
                    "bars_held": (i + 1) - entry_idx,
                    "exit_reason": "REVERSAL",
                })
                # If short entries are allowed, reverse into SHORT; otherwise transition to FLAT
                if allow_short_entry:
                    pos = -1
                    entry_px = nxt_open
                    entry_time = nxt_time
                    entry_idx = i + 1
                    highest_px = nxt_open
                    lowest_px = nxt_open
                else:
                    pos = 0

            # Case C: Currently in SHORT position
            elif pos == -1 and sig == "BUY":
                # Close SHORT trade
                raw_pnl = ((entry_px - nxt_open) / entry_px) * 100.0
                trades.append({
                    "symbol": symbol,
                    "direction": "SHORT",
                    "entry_time": entry_time,
                    "exit_time": nxt_time,
                    "net_pnl_pct": raw_pnl - friction,
                    "bars_held": (i + 1) - entry_idx,
                    "exit_reason": "REVERSAL",
                })
                # If long entries are allowed, reverse into LONG; otherwise transition to FLAT
                if allow_long_entry:
                    pos = 1
                    entry_px = nxt_open
                    entry_time = nxt_time
                    entry_idx = i + 1
                    highest_px = nxt_open
                    lowest_px = nxt_open
                else:
                    pos = 0

    return trades


def run_portfolio_backtest(
    dataset: Dict[str, pd.DataFrame],
    fast_ema: int = 9,
    slow_ema: int = 26,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_sig: int = 9,
    direction_mode: str = "SYMMETRICAL",
    exit_type: str = "REVERSAL",
    long_tp_pct: float = 3.0,
    short_tp_pct: float = 1.5,
    sl_pct: float = 6.0,
    atr_mult: float = 2.0,
    friction: float = 0.07,
    htf_bias_map: Optional[Dict[str, pd.Series]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Executes backtest across the entire portfolio dataset."""
    all_trades = []
    for sym, df in dataset.items():
        htf_bias = htf_bias_map.get(sym) if htf_bias_map else None
        sym_trades = run_single_symbol_backtest(
            df=df, symbol=sym,
            fast_ema=fast_ema, slow_ema=slow_ema,
            macd_fast=macd_fast, macd_slow=macd_slow, macd_sig=macd_sig,
            direction_mode=direction_mode, exit_type=exit_type,
            long_tp_pct=long_tp_pct, short_tp_pct=short_tp_pct, sl_pct=sl_pct,
            atr_mult=atr_mult, friction=friction,
            htf_bias_series=htf_bias,
        )
        all_trades.extend(sym_trades)

    if not all_trades:
        empty = compute_metrics(pd.DataFrame())
        return empty, empty, empty

    tdf = pd.DataFrame(all_trades)
    tdf["entry_dt"] = pd.to_datetime(tdf["entry_time"])

    # Ensure timezone naive
    if tdf["entry_dt"].dt.tz is not None:
        tdf["entry_dt"] = tdf["entry_dt"].dt.tz_localize(None)

    is_df = tdf[tdf["entry_dt"] < IS_SPLIT_DATE]
    oos_df = tdf[tdf["entry_dt"] >= IS_SPLIT_DATE]

    overall_m = compute_metrics(tdf)
    is_m = compute_metrics(is_df)
    oos_m = compute_metrics(oos_df)

    return overall_m, is_m, oos_m
