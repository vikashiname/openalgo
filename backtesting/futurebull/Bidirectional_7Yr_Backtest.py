#!/usr/bin/env python3
"""
================================================================================
7-YEAR NFO BIDIRECTIONAL BACKTEST ENGINE: BULL & BEAR FUTURES BREAKOUT
================================================================================
Directory   : backtesting/futurebull/
Role        : Full 7-Year (2019-2026) backtesting on 46 liquid Indian stock
              futures evaluating:
                - Long-Only Bullish Breakout
                - Short-Only Bearish Breakdown
                - Long + Short Bidirectional All-Weather Strategy
              Includes complete Indian futures statutory charges and slippage.
Outputs:
  - reports/BIDIRECTIONAL_7YR_SUMMARY.csv
  - reports/BIDIRECTIONAL_7YR_YEARLY_BREAKDOWN.csv
  - reports/BIDIRECTIONAL_7YR_ALL_TRADES.csv
  - reports/LONG_VS_SHORT_COMPARISON.csv
================================================================================
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from scanner_engine import compute_all_filters

DATA_DIR = CURRENT_DIR / "data"
REPORTS_DIR = CURRENT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Realistic Indian Stock Futures Friction Model
BROKERAGE_PER_ORDER = 20.0
STT_FUTURES_SELL = 0.000125       # 0.0125% on sell side
EXCHANGE_TURNOVER = 0.000019     # NSE turnover charge
GST_RATE = 0.18                  # 18% on (brokerage + turnover)
STAMP_DUTY_BUY = 0.00002        # 0.002% on buy
SLIPPAGE_RATE = 0.0005           # 0.05% slippage on entry & exit


def calculate_friction(entry_val: float, exit_val: float) -> float:
    total_val = entry_val + exit_val
    brokerage = BROKERAGE_PER_ORDER * 2.0
    stt = exit_val * STT_FUTURES_SELL  # Applied on sell leg
    exch = total_val * EXCHANGE_TURNOVER
    gst = (brokerage + exch) * GST_RATE
    stamp = entry_val * STAMP_DUTY_BUY
    slippage = total_val * SLIPPAGE_RATE
    return brokerage + stt + exch + gst + stamp + slippage


def simulate_bidirectional_trades(
    symbol_dfs: Dict[str, pd.DataFrame],
    mode: str = "BIDIRECTIONAL",  # "LONG_ONLY", "SHORT_ONLY", "BIDIRECTIONAL"
    long_sl_pct: float = 3.0,
    long_tp_pct: float = 6.0,
    long_max_hold: int = 15,
    short_sl_pct: float = 1.5,
    short_tp_pct: float = 4.0,
    short_max_hold: int = 5,
    position_capital: float = 200000.0,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    all_trades = []

    for symbol, df in symbol_dfs.items():
        if symbol == "NIFTY_INDEX":
            continue
        in_trade = False
        direction = None  # "LONG" or "SHORT"
        entry_price = 0.0
        entry_idx = 0
        entry_date = None
        stop_loss = 0.0
        target = 0.0
        active_max_hold = 15

        length = len(df)
        dates = df.index
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        volumes = df["volume"].values
        sma_vol = df["volume"].rolling(20).mean().values

        bull_sigs = df["SIG_BULL_OPTIMISED"].values
        # High-conviction institutional breakdown requires volume surge
        bear_sigs = (df["SIG_BEAR_OPTIMISED"] & (df["volume"] >= 1.25 * df["volume"].rolling(20).mean())).values

        for i in range(length - 1):
            if not in_trade:
                trigger_long = bull_sigs[i] and mode in ["LONG_ONLY", "BIDIRECTIONAL"]
                trigger_short = bear_sigs[i] and mode in ["SHORT_ONLY", "BIDIRECTIONAL"]

                if trigger_long and trigger_short:
                    trigger_short = False

                if trigger_long:
                    entry_idx = i + 1
                    entry_date = dates[entry_idx]
                    entry_price = opens[entry_idx]
                    if entry_price <= 0 or np.isnan(entry_price):
                        continue
                    in_trade = True
                    direction = "LONG"
                    stop_loss = entry_price * (1.0 - long_sl_pct / 100.0)
                    target = entry_price * (1.0 + long_tp_pct / 100.0)
                    active_max_hold = long_max_hold

                elif trigger_short:
                    entry_idx = i + 1
                    entry_date = dates[entry_idx]
                    entry_price = opens[entry_idx]
                    if entry_price <= 0 or np.isnan(entry_price):
                        continue
                    in_trade = True
                    direction = "SHORT"
                    stop_loss = entry_price * (1.0 + short_sl_pct / 100.0)
                    target = entry_price * (1.0 - short_tp_pct / 100.0)
                    active_max_hold = short_max_hold
            else:
                curr = i
                h = highs[curr]
                l = lows[curr]
                c = closes[curr]
                dt = dates[curr]
                holding = curr - entry_idx + 1

                exit_price = None
                exit_reason = None

                if direction == "LONG":
                    if l <= stop_loss:
                        exit_price = stop_loss
                        exit_reason = "STOP_LOSS"
                    elif h >= target:
                        exit_price = target
                        exit_reason = "PROFIT_TARGET"
                    elif holding >= active_max_hold:
                        exit_price = c
                        exit_reason = f"TIME_EXIT_{active_max_hold}D"

                    if exit_price:
                        shares = max(1, int(position_capital / entry_price))
                        buy_v = shares * entry_price
                        sell_v = shares * exit_price
                        gross = sell_v - buy_v
                        friction = calculate_friction(buy_v, sell_v)
                        net = gross - friction
                        ret_pct = (net / buy_v) * 100.0

                        all_trades.append({
                            "symbol": symbol,
                            "direction": "LONG",
                            "entry_date": entry_date,
                            "exit_date": dt,
                            "year": entry_date.year,
                            "holding_days": holding,
                            "entry_price": round(entry_price, 2),
                            "exit_price": round(exit_price, 2),
                            "shares": shares,
                            "gross_pnl": round(gross, 2),
                            "friction": round(friction, 2),
                            "net_pnl": round(net, 2),
                            "return_pct": round(ret_pct, 2),
                            "exit_reason": exit_reason
                        })
                        in_trade = False

                elif direction == "SHORT":
                    if h >= stop_loss:
                        exit_price = stop_loss
                        exit_reason = "STOP_LOSS"
                    elif l <= target:
                        exit_price = target
                        exit_reason = "PROFIT_TARGET"
                    elif holding >= active_max_hold:
                        exit_price = c
                        exit_reason = f"TIME_EXIT_{active_max_hold}D"

                    if exit_price:
                        shares = max(1, int(position_capital / entry_price))
                        sell_v = shares * entry_price
                        buy_v = shares * exit_price
                        gross = sell_v - buy_v
                        friction = calculate_friction(sell_v, buy_v)
                        net = gross - friction
                        ret_pct = (net / sell_v) * 100.0

                        all_trades.append({
                            "symbol": symbol,
                            "direction": "SHORT",
                            "entry_date": entry_date,
                            "exit_date": dt,
                            "year": entry_date.year,
                            "holding_days": holding,
                            "entry_price": round(entry_price, 2),
                            "exit_price": round(exit_price, 2),
                            "shares": shares,
                            "gross_pnl": round(gross, 2),
                            "friction": round(friction, 2),
                            "net_pnl": round(net, 2),
                            "return_pct": round(ret_pct, 2),
                            "exit_reason": exit_reason
                        })
                        in_trade = False

    t_df = pd.DataFrame(all_trades)
    if t_df.empty:
        return t_df, {}

    t_df = t_df.sort_values(by="entry_date").reset_index(drop=True)

    total_trades = len(t_df)
    wins = t_df[t_df["net_pnl"] > 0]
    losses = t_df[t_df["net_pnl"] <= 0]
    win_rate = (len(wins) / total_trades) * 100.0
    tot_pnl = t_df["net_pnl"].sum()
    avg_win = wins["net_pnl"].mean() if len(wins) > 0 else 0.0
    avg_loss = abs(losses["net_pnl"].mean()) if len(losses) > 0 else 0.0
    win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0
    tot_profit = wins["net_pnl"].sum() if len(wins) > 0 else 0.0
    tot_loss = abs(losses["net_pnl"].sum()) if len(losses) > 0 else 0.0
    profit_factor = (tot_profit / tot_loss) if tot_loss > 0 else 0.0
    expectancy = t_df["return_pct"].mean()

    # Drawdown on initial capital of ₹25 Lakhs
    initial_cap = 2500000.0
    cum_equity = initial_cap + t_df["net_pnl"].cumsum()
    peaks = cum_equity.cummax()
    dd = (cum_equity - peaks) / peaks * 100.0
    max_dd = abs(dd.min())

    sharpe = (t_df["return_pct"].mean() / t_df["return_pct"].std() * np.sqrt(252)) if t_df["return_pct"].std() > 0 else 0.0

    stats = {
        "mode": mode,
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "total_net_pnl_inr": round(tot_pnl, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy_pct": round(expectancy, 2),
        "avg_win_inr": round(avg_win, 2),
        "avg_loss_inr": round(avg_loss, 2),
        "win_loss_ratio": round(win_loss_ratio, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "avg_holding_days": round(t_df["holding_days"].mean(), 1)
    }

    return t_df, stats


def run_7year_bidirectional_analysis():
    print("================================================================================")
    print("🔬 RUNNING 7-YEAR (2019-2026) NFO BIDIRECTIONAL BACKTEST")
    print("================================================================================")

    data_files = sorted(list(DATA_DIR.glob("*.parquet")))
    symbol_dfs = {}
    print(f"Loading and processing {len(data_files)} symbols across 7+ years...")
    for f in data_files:
        df = pd.read_parquet(f)
        symbol_dfs[f.stem] = compute_all_filters(df)

    modes = ["LONG_ONLY", "SHORT_ONLY", "BIDIRECTIONAL"]
    summaries = []
    mode_ledgers = {}

    for m in modes:
        t_df, stats = simulate_bidirectional_trades(
            symbol_dfs,
            mode=m,
            long_sl_pct=3.0,
            long_tp_pct=6.0,
            long_max_hold=15,
            short_sl_pct=1.5,
            short_tp_pct=4.0,
            short_max_hold=5
        )
        mode_ledgers[m] = t_df
        summaries.append(stats)

    sum_df = pd.DataFrame(summaries)
    sum_out = REPORTS_DIR / "BIDIRECTIONAL_7YR_SUMMARY.csv"
    sum_df.to_csv(sum_out, index=False)
    print(f"✓ Exported 7-Year summary to: {sum_out}")

    bidi_trades = mode_ledgers["BIDIRECTIONAL"]
    trades_out = REPORTS_DIR / "BIDIRECTIONAL_7YR_ALL_TRADES.csv"
    bidi_trades.to_csv(trades_out, index=False)
    print(f"✓ Exported all 7-Year trades ({len(bidi_trades)} trades) to: {trades_out}")

    # Long vs Short breakdown table
    long_trades = bidi_trades[bidi_trades["direction"] == "LONG"]
    short_trades = bidi_trades[bidi_trades["direction"] == "SHORT"]

    comp_records = []
    for d_name, d_grp in [("LONG_BULLISH", long_trades), ("SHORT_BEARISH", short_trades), ("TOTAL_BIDIRECTIONAL", bidi_trades)]:
        wins = d_grp[d_grp["net_pnl"] > 0]
        losses = d_grp[d_grp["net_pnl"] <= 0]
        pf = (wins["net_pnl"].sum() / abs(losses["net_pnl"].sum())) if len(losses) > 0 else 0.0
        comp_records.append({
            "segment": d_name,
            "trades": len(d_grp),
            "win_rate_pct": round((len(wins) / len(d_grp)) * 100.0, 1) if len(d_grp) > 0 else 0.0,
            "total_net_pnl_inr": round(d_grp["net_pnl"].sum(), 2),
            "profit_factor": round(pf, 2),
            "expectancy_pct": round(d_grp["return_pct"].mean(), 2),
            "avg_win_inr": round(wins["net_pnl"].mean(), 2) if len(wins) > 0 else 0.0,
            "avg_loss_inr": round(abs(losses["net_pnl"].mean()), 2) if len(losses) > 0 else 0.0
        })
    comp_df = pd.DataFrame(comp_records)
    comp_out = REPORTS_DIR / "LONG_VS_SHORT_COMPARISON.csv"
    comp_df.to_csv(comp_out, index=False)
    print(f"✓ Exported Long vs Short comparison to: {comp_out}")

    # Yearly breakdown for Bidirectional
    yearly_records = []
    for yr, grp in bidi_trades.groupby("year"):
        l_sub = grp[grp["direction"] == "LONG"]
        s_sub = grp[grp["direction"] == "SHORT"]

        wins = grp[grp["net_pnl"] > 0]
        losses = grp[grp["net_pnl"] <= 0]
        pf = (wins["net_pnl"].sum() / abs(losses["net_pnl"].sum())) if len(losses) > 0 else 0.0

        yearly_records.append({
            "year": yr,
            "total_trades": len(grp),
            "long_trades": len(l_sub),
            "short_trades": len(s_sub),
            "win_rate_pct": round((len(wins) / len(grp)) * 100.0, 1),
            "profit_factor": round(pf, 2),
            "long_pnl_inr": round(l_sub["net_pnl"].sum(), 2),
            "short_pnl_inr": round(s_sub["net_pnl"].sum(), 2),
            "total_net_pnl_inr": round(grp["net_pnl"].sum(), 2),
            "expectancy_pct": round(grp["return_pct"].mean(), 2)
        })

    yr_df = pd.DataFrame(yearly_records)
    yr_out = REPORTS_DIR / "BIDIRECTIONAL_7YR_YEARLY_BREAKDOWN.csv"
    yr_df.to_csv(yr_out, index=False)
    print(f"✓ Exported 7-Year yearly breakdown to: {yr_out}")

    print("\n--------------------------------------------------------------------------------")
    print("🏆 7-YEAR (2019-2026) NFO PERFORMANCE COMPARISON:")
    print("--------------------------------------------------------------------------------")
    for _, r in sum_df.iterrows():
        print(f"  {r['mode']:<16} | Trades: {r['total_trades']:<5} | WinRate: {r['win_rate_pct']:>5.1f}% | PF: {r['profit_factor']:>4.2f} | Net PnL: ₹{r['total_net_pnl_inr']:>11,.0f} | Sharpe: {r['sharpe_ratio']:>+5.2f} | MaxDD: {r['max_drawdown_pct']:>5.1f}%")

    print("\n--------------------------------------------------------------------------------")
    print("📅 YEAR-BY-YEAR BIDIRECTIONAL P&L (2019 - 2026):")
    print("--------------------------------------------------------------------------------")
    for _, r in yr_df.iterrows():
        print(f"  {r['year']} | Trades: {r['total_trades']:<4} (L:{r['long_trades']:<3} S:{r['short_trades']:<3}) | Win: {r['win_rate_pct']:>4.1f}% | PF: {r['profit_factor']:>4.2f} | Long PnL: ₹{r['long_pnl_inr']:>9,.0f} | Short PnL: ₹{r['short_pnl_inr']:>9,.0f} | Net: ₹{r['total_net_pnl_inr']:>10,.0f}")
    print("================================================================================\n")


if __name__ == "__main__":
    run_7year_bidirectional_analysis()
