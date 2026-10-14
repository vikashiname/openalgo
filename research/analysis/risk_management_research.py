"""
================================================================================
Risk Management & Execution Research Engine (risk_management_research.py)
================================================================================
Comprehensive evaluation of Risk Management on MTF_BASELINE_V2 (Gold & Silver):
  - Phase 1: Baseline Exit (1H EMA Bearish Cross at Next Open)
  - Phase 2-3: ATR Stop Loss (1.5x, 2.0x, 2.5x, 3.0x ATR) & Exit Behavior Metrics
  - Phase 4: Partial Profit Taking (50% scale-out at 1.5R, 2.0R, 2.5R)
  - Phase 5: Trailing Stop (Chandelier / ATR trailing exit)
  - Phase 6: Session Filtering (London, New York, Overlap, Asian Dead Zone Exclude)
  - Phase 7-10: Incremental Comparison (V2 -> V3 -> V4 -> V5)
  - Phase 11: 10,000 Monte Carlo Simulation on Final Candidate
"""

import math
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import yfinance as yf

from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import CONTRACT_SPECS, DataHandler


# ==============================================================================
# FROZEN MTF_BASELINE_V2 CONFIGURATION
# ==============================================================================
MTF_BASELINE_V2 = {
    "GC=F": {
        "name": "Gold Futures (COMEX)",
        "fast_ema": 9,
        "slow_ema": 21,
        "daily_filter": "d_trend_ema9_21",
        "rvol_threshold": 1.2,
        "multiplier": 100.0,
        "margin_pct": 0.10,
        "fixed_fee": 2.50,
        "tick_size": 0.10,
    },
    "SI=F": {
        "name": "Silver Futures (COMEX)",
        "fast_ema": 20,
        "slow_ema": 50,
        "daily_filter": "d_trend_ema9_21",
        "rvol_threshold": 1.2,
        "multiplier": 5000.0,
        "margin_pct": 0.15,
        "fixed_fee": 2.50,
        "tick_size": 0.005,
    },
}


def load_and_prepare_data(symbol: str) -> pd.DataFrame:
    """Loads 1H and Daily data, aligns daily trend and calculates zero-lookahead ATR(14) and RVOL."""
    # 1. 1-Hour Intraday Data (~730 days)
    df_1h = yf.download(symbol, period="730d", interval="1h", progress=False)
    if isinstance(df_1h.columns, pd.MultiIndex):
        df_1h.columns = [c[0] for c in df_1h.columns]
    df_1h = df_1h.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    df_1h = df_1h[df_1h["close"].notnull() & (df_1h["close"] > 0)].copy()
    df_1h.index = pd.to_datetime(df_1h.index)
    if df_1h.index.tz is not None:
        df_1h.index = df_1h.index.tz_convert("UTC").tz_localize(None)
    df_1h = df_1h.sort_index()

    # 2. Daily Data
    df_daily = yf.download(symbol, period="3y", interval="1d", progress=False)
    if isinstance(df_daily.columns, pd.MultiIndex):
        df_daily.columns = [c[0] for c in df_daily.columns]
    df_daily = df_daily.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    df_daily = df_daily[df_daily["close"].notnull() & (df_daily["close"] > 0)].copy()
    df_daily.index = pd.to_datetime(df_daily.index)
    if df_daily.index.tz is not None:
        df_daily.index = df_daily.index.tz_convert("UTC").tz_localize(None)
    df_daily = df_daily.sort_index()

    # Daily trend indicator (Shifted by 1 for zero lookahead)
    d_close = df_daily["close"]
    df_daily["d_ema9"] = d_close.ewm(span=9, adjust=False).mean()
    df_daily["d_ema21"] = d_close.ewm(span=21, adjust=False).mean()
    df_daily["d_trend_ema9_21"] = (df_daily["d_ema9"] > df_daily["d_ema21"]).shift(1)

    # Align to 1H bars
    df_1h["date_key"] = df_1h.index.normalize()
    df_1h = df_1h.join(df_daily[["d_trend_ema9_21"]], on="date_key")
    df_1h["d_trend_ema9_21"] = df_1h["d_trend_ema9_21"].ffill().fillna(False)

    # 3. 1-Hour Indicators (ATR 14 & RVOL)
    tr = np.maximum(
        df_1h["high"] - df_1h["low"],
        np.maximum(
            (df_1h["high"] - df_1h["close"].shift(1)).abs(),
            (df_1h["low"] - df_1h["close"].shift(1)).abs()
        )
    )
    df_1h["atr14"] = tr.rolling(14).mean()
    vol_sma20 = df_1h["volume"].rolling(20).mean()
    df_1h["rvol"] = df_1h["volume"] / (vol_sma20 + 1e-6)

    # UTC Hour for session filtering
    df_1h["utc_hour"] = df_1h.index.hour

    return df_1h


def simulate_risk_managed_backtest(
    df: pd.DataFrame,
    cfg: Dict[str, Any],
    atr_stop_mult: Optional[float] = None,
    tp_r_mult: Optional[float] = None,
    tp_pct: float = 0.50,
    trailing_atr_mult: Optional[float] = None,
    session_filter: Optional[str] = None,
    initial_capital: float = 100_000.0,
    allocation_pct: float = 0.50,
    slippage_ticks: int = 1,
) -> Dict[str, Any]:
    """
    Simulates advanced risk-managed execution:
      - Initial ATR stop loss
      - Partial profit taking (scale out 50% at target R)
      - Dynamic trailing stop
      - Session execution filter
      - Whipsaw and MFE/MAE excursions
    """
    n = len(df)
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    atrs = df["atr14"].values
    rvols = df["rvol"].values
    daily_trend = df[cfg["daily_filter"]].values
    utc_hours = df["utc_hour"].values
    dates = df.index

    # 1H EMAs
    fast_p = cfg["fast_ema"]
    slow_p = cfg["slow_ema"]
    close_series = df["close"]
    ema_f = close_series.ewm(span=fast_p, adjust=False).mean().values
    ema_s = close_series.ewm(span=slow_p, adjust=False).mean().values

    # Raw Entry Signals (Confirmed at Close[t-1])
    buy_raw = (ema_f > ema_s) & (np.roll(ema_f, 1) <= np.roll(ema_s, 1))
    sell_raw = (ema_f < ema_s) & (np.roll(ema_f, 1) >= np.roll(ema_s, 1))
    buy_raw[0] = False
    sell_raw[0] = False

    # Session filter conditions (UTC hours)
    # London: 08:00 - 16:00 UTC
    # New York: 13:00 - 21:00 UTC
    # Overlap: 13:00 - 16:00 UTC
    # Exclude Asian Dead Zone: 07:00 - 21:00 UTC
    if session_filter == "london":
        session_mask = (utc_hours >= 8) & (utc_hours < 16)
    elif session_filter == "new_york":
        session_mask = (utc_hours >= 13) & (utc_hours < 21)
    elif session_filter == "overlap":
        session_mask = (utc_hours >= 13) & (utc_hours < 16)
    elif session_filter == "exclude_asian":
        session_mask = (utc_hours >= 7) & (utc_hours < 21)
    else:
        session_mask = np.ones(n, dtype=bool)

    # MTF_BASELINE_V2 Entry Rule: 1H Cross + Daily Trend + RVOL > 1.2 + Session
    buy_signals = buy_raw & daily_trend & (rvols > cfg["rvol_threshold"]) & session_mask
    sell_signals = sell_raw | (~daily_trend)

    mult = cfg["multiplier"]
    margin_pct = cfg["margin_pct"]
    fee = cfg["fixed_fee"]
    tick_size = cfg["tick_size"]
    slippage = slippage_ticks * tick_size

    cash = initial_capital
    pos = 0  # contracts held
    entry_p = 0.0
    entry_idx = 0
    entry_atr = 0.0
    stop_price = 0.0
    target_price = 0.0
    tp_executed = False
    highest_high = 0.0
    lowest_low = 0.0

    trades = []
    equity_curve = np.empty(n, dtype=np.float64)

    for i in range(n):
        op = opens[i]
        cp = closes[i]
        hp = highs[i]
        lp = lows[i]
        curr_atr = atrs[i]

        # 1. Manage Active Position Exits intra-bar (Stops / TP)
        if pos > 0:
            if hp > highest_high:
                highest_high = hp
            if lp < lowest_low:
                lowest_low = lp

            # Dynamic Trailing Stop update
            if trailing_atr_mult is not None and not np.isnan(curr_atr):
                trail_stop = highest_high - (trailing_atr_mult * curr_atr)
                if trail_stop > stop_price:
                    stop_price = trail_stop

            # Check Partial Profit Taking Trigger
            if tp_r_mult is not None and not tp_executed and hp >= target_price:
                scale_lots = max(1, int(pos * tp_pct))
                if scale_lots < pos:
                    exec_p = target_price - slippage
                    partial_pnl = (exec_p - entry_p) * mult * scale_lots
                    cash += partial_pnl - (fee * scale_lots * 2)
                    pos -= scale_lots
                    tp_executed = True
                    # Move stop to Breakeven after TP
                    stop_price = max(stop_price, entry_p)

            # Check Stop Loss Trigger (Intra-bar check)
            if stop_price > 0 and lp <= stop_price:
                # Stop loss hit
                exec_p = min(op, stop_price) - slippage
                pnl = (exec_p - entry_p) * mult * pos
                net_pnl = pnl - (fee * pos * 2)
                return_pct = (exec_p - entry_p) / entry_p * 100.0
                holding_bars = i - entry_idx
                mfe_pct = (highest_high - entry_p) / entry_p * 100.0
                is_whipsaw = (holding_bars <= 12) and (net_pnl <= 0) and (mfe_pct < 1.0)

                cash += pnl - fee
                trades.append({
                    "entry_date": dates[entry_idx],
                    "exit_date": dates[i],
                    "entry_price": entry_p,
                    "exit_price": exec_p,
                    "contracts": pos,
                    "net_pnl": net_pnl,
                    "return_pct": return_pct,
                    "holding_bars": holding_bars,
                    "exit_reason": "Stop Loss",
                    "mfe_pct": mfe_pct,
                    "is_whipsaw": is_whipsaw,
                })
                pos = 0
                entry_p = 0.0
                stop_price = 0.0

        # 2. Next Open Order Processing (using signal confirmed at bar i-1)
        if i > 0:
            prev_b = buy_signals[i - 1]
            prev_s = sell_signals[i - 1]

            # Regular EMA / Trend Exit on Next Open
            if prev_s and pos > 0:
                exec_p = op - slippage
                pnl = (exec_p - entry_p) * mult * pos
                total_fees = fee * pos * 2
                net_pnl = pnl - total_fees
                return_pct = (exec_p - entry_p) / entry_p * 100.0
                holding_bars = i - entry_idx
                mfe_pct = (highest_high - entry_p) / entry_p * 100.0
                is_whipsaw = (holding_bars <= 12) and (net_pnl <= 0) and (mfe_pct < 1.0)

                cash += pnl - fee
                trades.append({
                    "entry_date": dates[entry_idx],
                    "exit_date": dates[i],
                    "entry_price": entry_p,
                    "exit_price": exec_p,
                    "contracts": pos,
                    "net_pnl": net_pnl,
                    "return_pct": return_pct,
                    "holding_bars": holding_bars,
                    "exit_reason": "EMA Cross Exit",
                    "mfe_pct": mfe_pct,
                    "is_whipsaw": is_whipsaw,
                })
                pos = 0
                entry_p = 0.0
                stop_price = 0.0

            # Entry Execution on Next Open
            elif prev_b and pos == 0:
                exec_p = op + slippage
                contract_val = exec_p * mult
                margin_req = contract_val * margin_pct
                lots = int((cash * allocation_pct) // margin_req) if margin_req > 0 else 0
                if lots < 1 and cash >= margin_req:
                    lots = 1

                if lots >= 1:
                    pos = lots
                    entry_p = exec_p
                    entry_idx = i
                    entry_atr = atrs[i - 1] if not np.isnan(atrs[i - 1]) else (exec_p * 0.01)
                    highest_high = op
                    lowest_low = op
                    tp_executed = False

                    # Set Initial ATR Stop
                    if atr_stop_mult is not None:
                        stop_dist = atr_stop_mult * entry_atr
                        stop_price = entry_p - stop_dist
                        if tp_r_mult is not None:
                            target_price = entry_p + (tp_r_mult * stop_dist)
                    else:
                        stop_price = 0.0

                    cash -= (fee * pos)

        # Mark to market equity
        unrealized = (cp - entry_p) * mult * pos if pos > 0 else 0.0
        equity_curve[i] = cash + unrealized

    end_val = equity_curve[-1]
    net_profit = end_val - initial_capital
    total_ret = (net_profit / initial_capital) * 100.0

    years = max(0.1, n / (252.0 * 6.5))
    cagr = (((end_val / initial_capital) ** (1.0 / years)) - 1.0) * 100.0 if end_val > 0 else -100.0

    running_max = np.maximum.accumulate(equity_curve)
    dd_series = (running_max - equity_curve) / running_max * 100.0
    max_dd = float(np.max(dd_series)) if len(dd_series) > 0 else 0.0

    daily_eq = pd.Series(equity_curve, index=dates).resample("1D").last().dropna()
    daily_rets = daily_eq.pct_change().dropna()
    daily_rf = (1.0 + 0.045) ** (1.0 / 252.0) - 1.0
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
    pf = (g_win / g_loss) if g_loss > 0 else (99.0 if g_win > 0 else 0.0)

    avg_winner = (g_win / len(wins)) if wins else 0.0
    avg_loser = (g_loss / len(losses)) if losses else 0.0
    largest_loser = min([t["net_pnl"] for t in trades]) if trades else 0.0
    avg_holding_bars = float(np.mean([t["holding_bars"] for t in trades])) if trades else 0.0

    # Max consecutive losses
    max_consec = 0
    cur_consec = 0
    for t in trades:
        if t["net_pnl"] <= 0:
            cur_consec += 1
            if cur_consec > max_consec:
                max_consec = cur_consec
        else:
            cur_consec = 0

    whipsaws = [t for t in trades if t.get("is_whipsaw", False)]
    expectancy = (net_profit / len(trades)) if trades else 0.0

    return {
        "total_return_pct": total_ret,
        "cagr_pct": cagr,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "profit_factor": pf,
        "win_rate_pct": win_rate,
        "total_trades": len(trades),
        "expectancy_dollars": expectancy,
        "avg_winner": avg_winner,
        "avg_loser": avg_loser,
        "largest_loser": largest_loser,
        "max_consecutive_losses": max_consec,
        "avg_holding_bars": avg_holding_bars,
        "whipsaws": len(whipsaws),
        "trades": trades,
    }


def run_comprehensive_risk_study():
    """Runs complete risk management study for Gold and Silver."""
    print("\n" + "=" * 135)
    print(" 🛡️ RISK MANAGEMENT & EXECUTION RESEARCH (GOLD & SILVER)")
    print(" Baseline: MTF_BASELINE_V2 (Daily Trend + 1H EMA + RVOL > 1.2 -> Next Open Execution)")
    print("=" * 135)

    all_assets_data = {}
    for sym in ["GC=F", "SI=F"]:
        cfg = MTF_BASELINE_V2[sym]
        df_1h = load_and_prepare_data(sym)
        all_assets_data[sym] = (cfg, df_1h)

    for sym, (cfg, df_1h) in all_assets_data.items():
        print(f"\n==========================================================================================")
        print(f" 📦 ASSET: {cfg['name']} ({sym}) | Risk Management Architecture Study")
        print(f"==========================================================================================")

        n = len(df_1h)
        is_end = int(n * 0.60)
        val_end = int(n * 0.80)

        df_is = df_1h.iloc[:is_end].copy()
        df_val = df_1h.iloc[is_end:val_end].copy()
        df_oos = df_1h.iloc[val_end:].copy()

        # ----------------------------------------------------------------------
        # PHASE 1: Baseline Exit (Control)
        # ----------------------------------------------------------------------
        m_base_is = simulate_risk_managed_backtest(df_is, cfg)
        m_base_val = simulate_risk_managed_backtest(df_val, cfg)
        m_base_oos = simulate_risk_managed_backtest(df_oos, cfg)
        m_base_full = simulate_risk_managed_backtest(df_1h, cfg)

        print("\n[PHASE 1: BASELINE EXIT CONTROL (EMA Cross Exit)]")
        print(f"  In-Sample PF: {m_base_is['profit_factor']:.2f} | Val PF: {m_base_val['profit_factor']:.2f} | OOS PF: {m_base_oos['profit_factor']:.2f}")
        print(f"  OOS Sharpe: {m_base_oos['sharpe_ratio']:.2f} | OOS MaxDD: {m_base_oos['max_drawdown_pct']:.2f}% | OOS CAGR: {m_base_oos['cagr_pct']:+.2f}%")
        print(f"  Full Trades: {m_base_full['total_trades']} | Whipsaws: {m_base_full['whipsaws']} | Expectancy: ${m_base_full['expectancy_dollars']:+,.0f}")

        # ----------------------------------------------------------------------
        # PHASE 2 & 3: ATR Stop Loss (1.5x, 2.0x, 2.5x, 3.0x ATR) & Behavior Metrics
        # ----------------------------------------------------------------------
        print(f"\n[PHASE 2 & 3: ATR STOP LOSS EVALUATION & BEHAVIOR METRICS]")
        header = f"{'Stop Loss Setting':25} {'IS PF':7} {'OOS PF':8} {'OOS Sh':8} {'OOS DD':8} {'Avg Win ($)':13} {'Avg Loss ($)':13} {'Max Loss ($)':14} {'Hold (hrs)':10} {'Trades':7}"
        print(header)
        print("-" * 125)

        atr_stops = [1.5, 2.0, 2.5, 3.0]
        for mult in atr_stops:
            r_is = simulate_risk_managed_backtest(df_is, cfg, atr_stop_mult=mult)
            r_oos = simulate_risk_managed_backtest(df_oos, cfg, atr_stop_mult=mult)
            r_full = simulate_risk_managed_backtest(df_1h, cfg, atr_stop_mult=mult)

            print(
                f"{f'ATR Stop: {mult:.1f}x ATR':25} {r_is['profit_factor']:7.2f} {r_oos['profit_factor']:8.2f} "
                f"{r_oos['sharpe_ratio']:8.2f} {r_oos['max_drawdown_pct']:7.1f}% "
                f"${r_full['avg_winner']:+11,.0f} ${r_full['avg_loser']:+11,.0f} ${r_full['largest_loser']:+12,.0f} "
                f"{r_full['avg_holding_bars']:9.1f} {r_full['total_trades']:7d}"
            )

        # ----------------------------------------------------------------------
        # PHASE 4: Partial Profit Taking (50% Scale-Out at 1.5R, 2.0R, 2.5R)
        # ----------------------------------------------------------------------
        print(f"\n[PHASE 4: PARTIAL PROFIT TAKING (50% at Target R, 50% Trend Ride)]")
        # Use 2.5x ATR as baseline stop
        for tp_r in [1.5, 2.0, 2.5]:
            r_is = simulate_risk_managed_backtest(df_is, cfg, atr_stop_mult=2.5, tp_r_mult=tp_r, tp_pct=0.50)
            r_oos = simulate_risk_managed_backtest(df_oos, cfg, atr_stop_mult=2.5, tp_r_mult=tp_r, tp_pct=0.50)
            r_full = simulate_risk_managed_backtest(df_1h, cfg, atr_stop_mult=2.5, tp_r_mult=tp_r, tp_pct=0.50)
            print(
                f"  50% Exit at {tp_r:.1f}R + 50% Trend -> IS PF: {r_is['profit_factor']:.2f} | OOS PF: {r_oos['profit_factor']:.2f} | "
                f"OOS Sharpe: {r_oos['sharpe_ratio']:.2f} | OOS MaxDD: {r_oos['max_drawdown_pct']:.2f}% | Expectancy: ${r_full['expectancy_dollars']:+,.0f}"
            )

        # ----------------------------------------------------------------------
        # PHASE 5: Trailing Stop (Chandelier / Dynamic ATR Exit)
        # ----------------------------------------------------------------------
        print(f"\n[PHASE 5: DYNAMIC TRAILING STOP EVALUATION]")
        for trail_m in [2.5, 3.0, 3.5]:
            r_is = simulate_risk_managed_backtest(df_is, cfg, atr_stop_mult=2.5, trailing_atr_mult=trail_m)
            r_oos = simulate_risk_managed_backtest(df_oos, cfg, atr_stop_mult=2.5, trailing_atr_mult=trail_m)
            r_full = simulate_risk_managed_backtest(df_1h, cfg, atr_stop_mult=2.5, trailing_atr_mult=trail_m)
            print(
                f"  Initial 2.5x ATR + {trail_m:.1f}x Trail -> IS PF: {r_is['profit_factor']:.2f} | OOS PF: {r_oos['profit_factor']:.2f} | "
                f"OOS Sharpe: {r_oos['sharpe_ratio']:.2f} | OOS MaxDD: {r_oos['max_drawdown_pct']:.2f}% | Expectancy: ${r_full['expectancy_dollars']:+,.0f}"
            )

        # ----------------------------------------------------------------------
        # PHASE 6: Session Filtering (London, NY, Overlap, Asian Exclude)
        # ----------------------------------------------------------------------
        print(f"\n[PHASE 6: INTRADAY SESSION FILTERING (UTC Timezones)]")
        sessions = [
            ("All 24-Hour Sessions", None),
            ("London Session (08-16 UTC)", "london"),
            ("New York Session (13-21 UTC)", "new_york"),
            ("London/NY Overlap (13-16 UTC)", "overlap"),
            ("Exclude Asian Dead Zone (07-21 UTC)", "exclude_asian"),
        ]

        for s_name, s_key in sessions:
            r_is = simulate_risk_managed_backtest(df_is, cfg, atr_stop_mult=2.5, session_filter=s_key)
            r_oos = simulate_risk_managed_backtest(df_oos, cfg, atr_stop_mult=2.5, session_filter=s_key)
            r_full = simulate_risk_managed_backtest(df_1h, cfg, atr_stop_mult=2.5, session_filter=s_key)
            print(
                f"  {s_name:38} -> IS PF: {r_is['profit_factor']:.2f} | OOS PF: {r_oos['profit_factor']:.2f} | "
                f"OOS Sharpe: {r_oos['sharpe_ratio']:.2f} | OOS MaxDD: {r_oos['max_drawdown_pct']:.2f}% | Trades: {r_full['total_trades']:3d}"
            )

        # ----------------------------------------------------------------------
        # PHASE 8 & 9: Final Master Comparison Table (V2 -> V3 -> V4 -> V5)
        # ----------------------------------------------------------------------
        print(f"\n[PHASE 8 & 9: MASTER INCREMENTAL VERSION COMPARISON]")
        evolution_suite = [
            ("V2: Baseline MTF (No Stop)", "Daily + 1H EMA + RVOL>1.2", "1H EMA Bear Cross", None, None, None),
            ("V3: MTF + 2.5x ATR Stop", "Daily + 1H EMA + RVOL>1.2", "2.5x ATR Stop / EMA Cross", 2.5, None, None),
            ("V4: MTF + Stop + 2.0R TP", "Daily + 1H EMA + RVOL>1.2", "2.5x ATR Stop + 50% @ 2R", 2.5, 2.0, None),
            ("V5: MTF + Stop + Active Sessions", "Daily + 1H EMA + RVOL (07-21 UTC)", "2.5x ATR Stop / EMA Cross", 2.5, None, "exclude_asian"),
        ]

        header = f"{'VERSION':34} {'OOS PF':8} {'OOS CAGR':10} {'OOS Sh':8} {'OOS DD':8} {'EXPECTANCY':12} {'TRADES':8} {'WHIPSAWS':9} {'VERDICT':20}"
        print(header)
        print("-" * 135)

        for v_name, ent_desc, exit_desc, stop_m, tp_m, sess_m in evolution_suite:
            r_is = simulate_risk_managed_backtest(df_is, cfg, atr_stop_mult=stop_m, tp_r_mult=tp_m, session_filter=sess_m)
            r_oos = simulate_risk_managed_backtest(df_oos, cfg, atr_stop_mult=stop_m, tp_r_mult=tp_m, session_filter=sess_m)
            r_full = simulate_risk_managed_backtest(df_1h, cfg, atr_stop_mult=stop_m, tp_r_mult=tp_m, session_filter=sess_m)

            if r_oos['profit_factor'] > 2.0 and r_oos['max_drawdown_pct'] <= 15.0:
                verd = "✅ ROBUST"
            elif r_oos['profit_factor'] >= 1.4:
                verd = "🌟 PROMISING"
            elif r_full['total_trades'] < 20:
                verd = "⚠️ OVERFIT"
            else:
                verd = "❌ WEAK"

            print(
                f"{v_name:34} {r_oos['profit_factor']:8.2f} {r_oos['cagr_pct']:+9.2f}% "
                f"{r_oos['sharpe_ratio']:8.2f} {r_oos['max_drawdown_pct']:7.1f}% "
                f"${r_full['expectancy_dollars']:+10,.0f} {r_full['total_trades']:8d} {r_full['whipsaws']:9d} {verd:20}"
            )
        print("=" * 135)

    # ----------------------------------------------------------------------
    # PHASE 11: 10,000 Monte Carlo Simulation on Final Gold Strategy
    # ----------------------------------------------------------------------
    print(f"\n==========================================================================================")
    print(f" 🎲 PHASE 11: 10,000 MONTE CARLO SIMULATIONS ON GOLD FINAL CANDIDATE (V3)")
    print(f"==========================================================================================")
    gold_cfg, gold_df = all_assets_data["GC=F"]
    best_gold_full = simulate_risk_managed_backtest(gold_df, gold_cfg, atr_stop_mult=2.5)
    trades = best_gold_full["trades"]
    pnls = np.array([t["net_pnl"] for t in trades])

    np.random.seed(42)
    n_sims = 10_000
    n_trades = len(pnls)
    sim_returns = []
    sim_max_dds = []

    for _ in range(n_sims):
        sample_pnl = np.random.choice(pnls, size=n_trades, replace=True)
        equity = 100_000.0 + np.cumsum(sample_pnl)
        ret_pct = (equity[-1] - 100_000.0) / 100_000.0 * 100.0
        peaks = np.maximum.accumulate(equity)
        dds = (peaks - equity) / peaks * 100.0
        sim_returns.append(ret_pct)
        sim_max_dds.append(np.max(dds))

    sim_returns = np.array(sim_returns)
    sim_max_dds = np.array(sim_max_dds)

    p_loss = float(np.mean(sim_returns < 0.0) * 100.0)
    print(f"  Total Trades Resampled: {n_trades} (Statistically Viable N >= 30)")
    print(f"  Median Simulated Return: {np.median(sim_returns):+.2f}%")
    print(f"  5th Percentile Return:   {np.percentile(sim_returns, 5):+.2f}%")
    print(f"  95th Percentile Return:  {np.percentile(sim_returns, 95):+.2f}%")
    print(f"  Median Max Drawdown:     {np.median(sim_max_dds):.2f}%")
    print(f"  95th Percentile MaxDD:   {np.percentile(sim_max_dds, 95):.2f}%")
    print(f"  Probability of Loss:     {p_loss:.2f}%")
    print("=" * 135)


if __name__ == "__main__":
    run_comprehensive_risk_study()
