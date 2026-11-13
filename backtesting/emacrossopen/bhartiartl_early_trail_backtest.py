"""
BHARTIARTL & Tier-2 Asymmetric Early Profit & Trailing Runner Backtest Engine
File: backtesting/emacrossopen/bhartiartl_early_trail_backtest.py

Evaluates the proposal:
"if asymmetric universe, if signal is strong, book profit early and trail it"
Tests BHARTIARTL (and all non-whitelisted NFO symbols) across:
1. Signal strength filters (ALL vs SAME_CANDLE vs SAME_CANDLE + High Volume)
2. Early Target milestones (1.0%, 1.2%, 1.5%, 2.0%, 3.0%)
3. Trailing runner (0.35% HWM pullback) + Move Stop-Loss to Break-Even (BE) on TP hit
4. Initial Stop-Loss variants (6.0%, 3.0%, 2.0%)
"""

import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
DATA_DIR = CURRENT_DIR / "data"

BASE_FRICTION_PCT = 0.07  # 0.07% round-trip friction (brokerage + STT + slippage)

TOP_LONGS = {
    "SUNPHARMA", "BAJAJ-AUTO", "BPCL", "WIPRO", "TATASTEEL",
    "BAJFINANCE", "NTPC"
}
TOP_SHORTS = {
    "SUNPHARMA", "BAJAJ-AUTO", "M&M", "BPCL", "NTPC",
    "NIFTY"
}


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    df["ema9"] = close.ewm(span=9, adjust=False).mean()
    df["ema26"] = close.ewm(span=26, adjust=False).mean()

    df["ema12"] = close.ewm(span=12, adjust=False).mean()
    df["macd"] = df["ema12"] - df["ema26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["tr"] = tr
    df["atr14"] = tr.rolling(window=14).mean()
    df["vol_sma20"] = volume.rolling(window=20).mean()

    return df


def load_dataset(symbols: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
    data_map = {}
    for p in sorted(DATA_DIR.glob("*.parquet")):
        sym = p.stem.replace("_1h", "")
        if symbols and sym not in symbols:
            continue
        df = pd.read_parquet(p)
        if df.index.tz is None:
            df.index = df.index.tz_localize("Asia/Kolkata")
        else:
            df.index = df.index.tz_convert("Asia/Kolkata")
        df = calculate_indicators(df)
        df = df.dropna().copy()
        if len(df) >= 50:
            data_map[sym] = df
    return data_map


def extract_v2_2_trades(data_map: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    raw_trades = []

    for sym, df in data_map.items():
        n = len(df)
        close = df["Close"].values
        open_px = df["Open"].values
        high_px = df["High"].values
        low_px = df["Low"].values
        vol = df["Volume"].values
        vol_sma = df["vol_sma20"].values
        ema9 = df["ema9"].values
        ema26 = df["ema26"].values
        macd = df["macd"].values
        signal = df["macd_signal"].values
        hist = df["macd_histogram"].values
        atr = df["atr14"].values
        times = df.index

        active_trade = None
        active_pending = None

        for i in range(1, n - 1):
            curr_ema9 = ema9[i]
            prev_ema9 = ema9[i - 1]
            curr_ema26 = ema26[i]
            prev_ema26 = ema26[i - 1]

            curr_macd = macd[i]
            prev_macd = macd[i - 1]
            curr_sig = signal[i]
            prev_sig = signal[i - 1]

            ema_cross_up = (prev_ema9 <= prev_ema26) and (curr_ema9 > curr_ema26)
            ema_cross_down = (prev_ema9 >= prev_ema26) and (curr_ema9 < curr_ema26)
            macd_cross_up = (prev_macd <= prev_sig) and (curr_macd > curr_sig)
            macd_cross_down = (prev_macd >= prev_sig) and (curr_macd < curr_sig)

            new_sig = None
            conf_type = None

            # 1. SAME_CANDLE Confluence
            if ema_cross_up and macd_cross_up:
                new_sig = "BUY"
                conf_type = "SAME_CANDLE"
                active_pending = None
            elif ema_cross_down and macd_cross_down:
                new_sig = "SELL"
                conf_type = "SAME_CANDLE"
                active_pending = None

            # 2. Sequential Confirmation
            if new_sig is None:
                if active_pending is not None:
                    active_pending["elapsed_bars"] += 1
                    if active_pending["direction"] == "LONG":
                        if (active_pending["leading"] == "EMA" and curr_ema9 < curr_ema26) or \
                           (active_pending["leading"] == "MACD" and curr_macd < curr_sig):
                            active_pending = None
                        elif active_pending and active_pending["elapsed_bars"] <= 2:
                            if active_pending["leading"] == "EMA" and macd_cross_up:
                                new_sig = "BUY"
                                conf_type = "EMA_THEN_MACD"
                                active_pending = None
                            elif active_pending["leading"] == "MACD" and ema_cross_up:
                                new_sig = "BUY"
                                conf_type = "MACD_THEN_EMA"
                                active_pending = None
                        elif active_pending and active_pending["elapsed_bars"] > 2:
                            active_pending = None

                    elif active_pending and active_pending["direction"] == "SHORT":
                        if (active_pending["leading"] == "MACD" and curr_macd > curr_sig):
                            active_pending = None
                        elif active_pending and active_pending["elapsed_bars"] <= 2:
                            if active_pending["leading"] == "MACD" and ema_cross_down:
                                new_sig = "SELL"
                                conf_type = "MACD_THEN_EMA"
                                active_pending = None
                        elif active_pending and active_pending["elapsed_bars"] > 2:
                            active_pending = None

            # 3. New Pending Setup Initiation
            if new_sig is None and active_pending is None:
                if ema_cross_up and not macd_cross_up:
                    active_pending = {"direction": "LONG", "leading": "EMA", "elapsed_bars": 0, "candle_idx": i}
                elif macd_cross_up and not ema_cross_up:
                    active_pending = {"direction": "LONG", "leading": "MACD", "elapsed_bars": 0, "candle_idx": i}
                elif macd_cross_down and not ema_cross_down:
                    active_pending = {"direction": "SHORT", "leading": "MACD", "elapsed_bars": 0, "candle_idx": i}

            # If signal confirmed, record trade entry at next candle Open[i+1]
            if new_sig is not None:
                entry_idx = i + 1
                entry_time = times[entry_idx]
                entry_px = open_px[entry_idx]

                if active_trade is not None:
                    active_trade["forward_reversal_idx"] = entry_idx
                    active_trade["forward_reversal_time"] = entry_time
                    active_trade["forward_reversal_price"] = entry_px
                    raw_trades.append(active_trade)
                    active_trade = None

                high_vol = vol[i] > (1.3 * vol_sma[i]) if vol_sma[i] > 0 else False

                active_trade = {
                    "symbol": sym,
                    "direction": 1 if new_sig == "BUY" else -1,
                    "direction_str": "LONG" if new_sig == "BUY" else "SHORT",
                    "signal_time": times[i],
                    "entry_time": entry_time,
                    "entry_idx": entry_idx,
                    "entry_price": float(entry_px),
                    "conf_type": conf_type,
                    "high_volume": high_vol,
                    "atr_entry": float(atr[i]),
                    "forward_reversal_idx": n - 1,
                    "forward_reversal_time": times[n - 1],
                    "forward_reversal_price": float(close[n - 1]),
                    "df_slice": df.iloc[entry_idx:].copy(),
                }

        if active_trade is not None:
            raw_trades.append(active_trade)

    return raw_trades


def simulate_trade_exit(
    trade: Dict[str, Any],
    long_tp_pct: float,
    short_tp_pct: float,
    sl_pct: float,
    trail_pct: float = 0.35,
    enable_runner: bool = True,
    move_sl_to_be: bool = True,
    friction_pct: float = BASE_FRICTION_PCT,
) -> Dict[str, Any]:
    df_slice = trade["df_slice"]
    direction = trade["direction"]
    entry_px = trade["entry_price"]
    target_pct = long_tp_pct if direction == 1 else short_tp_pct

    target_price = entry_px * (1.0 + (target_pct / 100.0)) if direction == 1 else entry_px * (1.0 - (target_pct / 100.0))
    current_sl_price = entry_px * (1.0 - (sl_pct / 100.0)) if direction == 1 else entry_px * (1.0 + (sl_pct / 100.0))

    exit_reason = "V2-2_REVERSAL"
    exit_price = trade["forward_reversal_price"]
    exit_time = trade["forward_reversal_time"]
    bars_held = 0

    target_reached = False
    runner_active = False

    peak_price = entry_px
    trough_price = entry_px

    for bar_num, (ts, row) in enumerate(df_slice.iterrows()):
        curr_high = float(row["High"])
        curr_low = float(row["Low"])
        curr_close = float(row["Close"])

        bars_held = bar_num + 1

        # 1. Check Catastrophe / BE Stop Loss
        if direction == 1 and curr_low <= current_sl_price:
            exit_reason = "STOP_LOSS"
            exit_price = current_sl_price
            exit_time = ts
            break
        elif direction == -1 and curr_high >= current_sl_price:
            exit_reason = "STOP_LOSS"
            exit_price = current_sl_price
            exit_time = ts
            break

        # 2. Check Target Touch
        if not target_reached:
            hit_target = (direction == 1 and curr_high >= target_price) or (direction == -1 and curr_low <= target_price)
            if hit_target:
                target_reached = True
                if move_sl_to_be:
                    # Move Stop Loss to Entry Price (Break-Even)
                    current_sl_price = entry_px

                if not enable_runner:
                    exit_reason = "TARGET_HIT"
                    exit_price = target_price
                    exit_time = ts
                    break
                else:
                    runner_active = True
                    if direction == 1:
                        peak_price = max(peak_price, curr_high)
                    else:
                        trough_price = min(trough_price, curr_low)

        # 3. Trailing logic if runner active
        if runner_active:
            if direction == 1:
                peak_price = max(peak_price, curr_high)
                effective_trail_sl = peak_price * (1.0 - (trail_pct / 100.0))
                # Ensure trail SL cannot be worse than BE SL
                effective_trail_sl = max(effective_trail_sl, entry_px)
                if curr_low <= effective_trail_sl:
                    exit_reason = "RUNNER_HWM_TRAIL"
                    exit_price = effective_trail_sl
                    exit_time = ts
                    break
            else:  # SHORT
                trough_price = min(trough_price, curr_low)
                effective_trail_sl = trough_price * (1.0 + (trail_pct / 100.0))
                # Ensure trail SL cannot be worse than BE SL
                effective_trail_sl = min(effective_trail_sl, entry_px)
                if curr_high >= effective_trail_sl:
                    exit_reason = "RUNNER_HWM_TRAIL"
                    exit_price = effective_trail_sl
                    exit_time = ts
                    break

        # 4. Check Reversal Time
        if ts >= trade["forward_reversal_time"]:
            exit_reason = "V2-2_REVERSAL"
            exit_price = curr_close
            exit_time = ts
            break

    raw_pnl_pct = ((exit_price - entry_px) / entry_px) * 100.0 if direction == 1 else ((entry_px - exit_price) / entry_px) * 100.0
    net_pnl_pct = raw_pnl_pct - friction_pct

    return {
        "symbol": trade["symbol"],
        "direction": trade["direction_str"],
        "entry_time": trade["entry_time"],
        "exit_time": exit_time,
        "entry_price": entry_px,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "target_reached": target_reached,
        "net_pnl_pct": net_pnl_pct,
        "bars_held": bars_held,
        "conf_type": trade["conf_type"],
        "high_volume": trade["high_volume"],
    }


def compute_performance(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {
            "n_trades": 0, "win_rate": 0.0, "net_return": 0.0,
            "profit_factor": 0.0, "expectancy": 0.0, "max_drawdown": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "target_hit_pct": 0.0
        }

    pnls = [r["net_pnl_pct"] for r in results]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    n_trades = len(pnls)
    win_rate = (len(wins) / n_trades) * 100.0
    net_return = sum(pnls)

    total_gain = sum(wins)
    total_loss = abs(sum(losses))
    profit_factor = (total_gain / total_loss) if total_loss > 0 else 999.0
    expectancy = np.mean(pnls)

    # Max Drawdown of cumulative return curve
    cum_returns = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cum_returns)
    drawdowns = running_max - cum_returns
    max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    target_hits = sum(1 for r in results if r["target_reached"])
    target_hit_pct = (target_hits / n_trades) * 100.0

    return {
        "n_trades": n_trades,
        "win_rate": round(win_rate, 2),
        "net_return": round(net_return, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 3),
        "max_drawdown": round(max_drawdown, 2),
        "avg_win": round(np.mean(wins), 2) if wins else 0.0,
        "avg_loss": round(np.mean(losses), 2) if losses else 0.0,
        "target_hit_pct": round(target_hit_pct, 1),
    }


def run_comprehensive_matrix():
    print("=" * 80)
    print("🔬 RUNNING COMPREHENSIVE BACKTEST ON BHARTIARTL & NON-WHITELISTED F&O")
    print("=" * 80)

    all_data = load_dataset()
    bhartiartl_data = {k: v for k, v in all_data.items() if k == "BHARTIARTL"}
    non_whitelist_data = {k: v for k, v in all_data.items() if k not in TOP_LONGS and k not in TOP_SHORTS}

    bharti_trades = extract_v2_2_trades(bhartiartl_data)
    non_wl_trades = extract_v2_2_trades(non_whitelist_data)

    print(f"Extracted {len(bharti_trades)} total V2-2 signals for BHARTIARTL")
    print(f"Extracted {len(non_wl_trades)} total V2-2 signals across {len(non_whitelist_data)} Non-Whitelisted symbols\n")

    # Define models to test
    scenarios = [
        {"name": "1. Baseline V3.0 (Fixed TP 3.0/1.5, SL 6.0%)", "long_tp": 3.0, "short_tp": 1.5, "sl": 6.0, "be": False, "runner": False},
        {"name": "2. V3.0 Champion (TP 3.0/1.5, SL 6.0%, 0.35% HWM Trail)", "long_tp": 3.0, "short_tp": 1.5, "sl": 6.0, "be": False, "runner": True},
        {"name": "3. Early TP 1.0% + BE Stop + 0.35% Trail (SL 6.0%)", "long_tp": 1.0, "short_tp": 1.0, "sl": 6.0, "be": True, "runner": True},
        {"name": "4. Early TP 1.2% + BE Stop + 0.35% Trail (SL 6.0%)", "long_tp": 1.2, "short_tp": 1.0, "sl": 6.0, "be": True, "runner": True},
        {"name": "5. Early TP 1.5% + BE Stop + 0.35% Trail (SL 6.0%)", "long_tp": 1.5, "short_tp": 1.2, "sl": 6.0, "be": True, "runner": True},
        {"name": "6. Early TP 1.2% + BE Stop + 0.35% Trail (Tight SL 3.0%)", "long_tp": 1.2, "short_tp": 1.0, "sl": 3.0, "be": True, "runner": True},
        {"name": "7. Early TP 1.5% + BE Stop + 0.35% Trail (Tight SL 3.0%)", "long_tp": 1.5, "short_tp": 1.2, "sl": 3.0, "be": True, "runner": True},
        {"name": "8. Early TP 1.2% + BE Stop + 0.35% Trail (Tight SL 2.0%)", "long_tp": 1.2, "short_tp": 1.0, "sl": 2.0, "be": True, "runner": True},
    ]

    filter_modes = [
        ("ALL SIGNALS (No Filter)", lambda t: True),
        ("STRONG SIGNAL ONLY (SAME_CANDLE Confluence)", lambda t: t["conf_type"] == "SAME_CANDLE"),
        ("STRONG SIGNAL + VOLUME SURGE (>1.3x SMA)", lambda t: t["conf_type"] == "SAME_CANDLE" and t["high_volume"]),
    ]

    # SECTION 1: BHARTIARTL DETAILED TABLE
    print("=" * 105)
    print("📊 SECTION 1: BHARTIARTL RESULTS")
    print("=" * 105)

    for filter_name, filter_fn in filter_modes:
        filtered_trades = [t for t in bharti_trades if filter_fn(t)]
        print(f"\n▶ Signal Filter: {filter_name} (Sample: {len(filtered_trades)} trades)")
        print(f"{'Configuration':<58} | {'Trades':<6} | {'Win %':<6} | {'Net Return':<10} | {'PF':<5} | {'Exp %':<6} | {'MaxDD %':<7}")
        print("-" * 105)

        for sc in scenarios:
            res = [
                simulate_trade_exit(
                    t,
                    long_tp_pct=sc["long_tp"],
                    short_tp_pct=sc["short_tp"],
                    sl_pct=sc["sl"],
                    trail_pct=0.35,
                    enable_runner=sc["runner"],
                    move_sl_to_be=sc["be"],
                )
                for t in filtered_trades
            ]
            perf = compute_performance(res)
            print(
                f"{sc['name']:<58} | {perf['n_trades']:<6} | {perf['win_rate']:<6.1f} | "
                f"{perf['net_return']:>9.2f}% | {perf['profit_factor']:<5.2f} | {perf['expectancy']:>5.2f}% | {perf['max_drawdown']:>6.2f}%"
            )

    # SECTION 2: ENTIRE NON-WHITELISTED UNIVERSE
    print("\n" + "=" * 105)
    print("📊 SECTION 2: ALL NON-WHITELISTED F&O STOCKS COMBINED (Out-of-Universe Robustness Test)")
    print("=" * 105)

    for filter_name, filter_fn in filter_modes:
        filtered_trades = [t for t in non_wl_trades if filter_fn(t)]
        print(f"\n▶ Signal Filter: {filter_name} (Sample: {len(filtered_trades)} trades across {len(non_whitelist_data)} symbols)")
        print(f"{'Configuration':<58} | {'Trades':<6} | {'Win %':<6} | {'Net Return':<10} | {'PF':<5} | {'Exp %':<6} | {'MaxDD %':<7}")
        print("-" * 105)

        for sc in scenarios:
            res = [
                simulate_trade_exit(
                    t,
                    long_tp_pct=sc["long_tp"],
                    short_tp_pct=sc["short_tp"],
                    sl_pct=sc["sl"],
                    trail_pct=0.35,
                    enable_runner=sc["runner"],
                    move_sl_to_be=sc["be"],
                )
                for t in filtered_trades
            ]
            perf = compute_performance(res)
            print(
                f"{sc['name']:<58} | {perf['n_trades']:<6} | {perf['win_rate']:<6.1f} | "
                f"{perf['net_return']:>9.2f}% | {perf['profit_factor']:<5.2f} | {perf['expectancy']:>5.2f}% | {perf['max_drawdown']:>6.2f}%"
            )


if __name__ == "__main__":
    run_comprehensive_matrix()
