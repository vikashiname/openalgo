#!/usr/bin/env python3
"""
================================================================================
PHASE 5 & 6: FULL PORTFOLIO FUTURES STRATEGY BACKTEST & MULTI-VARIANT BENCHMARK
================================================================================
Directory   : backtesting/futurebull/
Role        : Backtests all 5 scanner variants as institutional-grade trading
              strategies on 46 Indian Stock Futures (2021-2026).
              Calculates comprehensive performance metrics, monthly/yearly breakdowns,
              consecutive loss streaks, and market regime analysis.
Outputs:
  - reports/FUTURES_STRATEGY_PORTFOLIO_BENCHMARK.csv
  - reports/YEARLY_PERFORMANCE_BREAKDOWN.csv
  - reports/REGIME_PERFORMANCE_BREAKDOWN.csv
  - reports/OPTIMISED_SCANNER_TRADE_LEDGER.csv
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

from scanner_engine import compute_all_filters, compute_rsi, compute_bollinger_bands, compute_macd_14_5_3

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


def calculate_friction(buy_val: float, sell_val: float) -> float:
    total_val = buy_val + sell_val
    brokerage = BROKERAGE_PER_ORDER * 2.0
    stt = sell_val * STT_FUTURES_SELL
    exch = total_val * EXCHANGE_TURNOVER
    gst = (brokerage + exch) * GST_RATE
    stamp = buy_val * STAMP_DUTY_BUY
    slippage = total_val * SLIPPAGE_RATE
    return brokerage + stt + exch + gst + stamp + slippage


def compute_signals_for_variants(df: pd.DataFrame) -> pd.DataFrame:
    """Appends boolean signal masks for all 5 scanner variants."""
    res = compute_all_filters(df)
    c = res["close"]
    h = res["high"]
    o = res["open"]
    v = res["volume"]

    sma_vol_20 = v.rolling(20).mean()
    ema_5 = c.ewm(span=5, adjust=False).mean()
    ema_20 = c.ewm(span=20, adjust=False).mean()
    ema_50 = c.ewm(span=50, adjust=False).mean()
    rsi_14 = compute_rsi(c, 14)
    rsi_10 = compute_rsi(c, 10)
    _, bb_upper, _ = compute_bollinger_bands(c, 20, 2.0)
    _, _, macd_hist = compute_macd_14_5_3(c)
    high_20 = h.rolling(20).max().shift(1)

    # 1. Original 29-condition scanner
    res["SIG_ORIGINAL"] = res["COMBO_ALL_ORIGINAL"]

    # 2. Optimized Scanner (Eliminates exhaustion trap + clean momentum zone)
    res["SIG_OPTIMISED"] = (
        (sma_vol_20 >= 100000) & (v > 100000) & (c > o) &
        (c > ema_20) & (ema_20 > ema_50) &
        (rsi_14 > 52.0) & (rsi_14 < 75.0) &
        (macd_hist >= 0.0) & (c < bb_upper)
    )

    # 3. Simplified Scanner (5 core factors)
    res["SIG_SIMPLIFIED"] = (
        (sma_vol_20 >= 100000) & (c > ema_20) & (ema_20 > ema_50) &
        (rsi_14 > 50.0) & (macd_hist >= 0.0) & (c > o)
    )

    # 4. High-Frequency Scanner
    res["SIG_HIGH_FREQ"] = (
        (sma_vol_20 >= 100000) & (ema_5 > ema_20) &
        (rsi_10 > 50.0) & (c > o)
    )

    # 5. High-Quality Breakout Scanner
    res["SIG_HQ_BREAKOUT"] = (
        (sma_vol_20 >= 100000) & (v >= 1.5 * sma_vol_20) &
        (c >= high_20) & (c > ema_50) &
        (rsi_14 > 55.0) & (rsi_14 < 80.0)
    )

    return res


def run_single_simulation(
    symbol_dfs: Dict[str, pd.DataFrame],
    signal_col: str,
    stop_loss_pct: float = 2.0,
    profit_target_pct: float = 4.0,
    max_holding_days: int = 10,
    position_capital: float = 200000.0,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Runs chronologically aligned portfolio backtest."""
    all_trades = []

    for symbol, df in symbol_dfs.items():
        in_trade = False
        entry_price = 0.0
        entry_idx = 0
        entry_date = None
        stop_loss = 0.0
        target = 0.0

        length = len(df)
        dates = df.index
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        signals = df[signal_col].values

        for i in range(length - 1):
            if not in_trade:
                if signals[i]:
                    entry_idx = i + 1
                    entry_date = dates[entry_idx]
                    entry_price = opens[entry_idx]
                    if entry_price <= 0 or np.isnan(entry_price):
                        continue
                    in_trade = True
                    stop_loss = entry_price * (1.0 - stop_loss_pct / 100.0)
                    target = entry_price * (1.0 + profit_target_pct / 100.0)
            else:
                curr = i
                h = highs[curr]
                l = lows[curr]
                c = closes[curr]
                dt = dates[curr]
                holding = curr - entry_idx + 1

                exit_price = None
                exit_reason = None

                if l <= stop_loss:
                    exit_price = stop_loss
                    exit_reason = "STOP_LOSS"
                elif h >= target:
                    exit_price = target
                    exit_reason = "PROFIT_TARGET"
                elif holding >= max_holding_days:
                    exit_price = c
                    exit_reason = f"TIME_EXIT_{max_holding_days}D"

                if exit_reason:
                    shares = max(1, int(position_capital / entry_price))
                    buy_v = shares * entry_price
                    sell_v = shares * exit_price
                    gross = sell_v - buy_v
                    friction = calculate_friction(buy_v, sell_v)
                    net = gross - friction
                    ret_pct = (net / buy_v) * 100.0

                    all_trades.append({
                        "symbol": symbol,
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

    # Performance Analytics
    total_trades = len(t_df)
    wins = t_df[t_df["net_pnl"] > 0]
    losses = t_df[t_df["net_pnl"] <= 0]
    win_rate = (len(wins) / total_trades) * 100.0
    tot_pnl = t_df["net_pnl"].sum()
    avg_win = wins["net_pnl"].mean() if len(wins) > 0 else 0.0
    avg_loss = abs(losses["net_pnl"].mean()) if len(losses) > 0 else 0.0
    profit_factor = (wins["net_pnl"].sum() / abs(losses["net_pnl"].sum())) if len(losses) > 0 else 0.0
    expectancy = t_df["return_pct"].mean()

    # Drawdown on cumulative portfolio PnL
    initial_cap = 2000000.0
    cum_equity = initial_cap + t_df["net_pnl"].cumsum()
    peaks = cum_equity.cummax()
    dd = (cum_equity - peaks) / peaks * 100.0
    max_dd = abs(dd.min())

    # Max Consecutive Losses
    is_loss = (t_df["net_pnl"] <= 0).astype(int)
    max_consec_loss = 0
    curr_streak = 0
    for v in is_loss:
        if v == 1:
            curr_streak += 1
            max_consec_loss = max(max_consec_loss, curr_streak)
        else:
            curr_streak = 0

    sharpe = (t_df["return_pct"].mean() / t_df["return_pct"].std() * np.sqrt(252)) if t_df["return_pct"].std() > 0 else 0.0

    stats = {
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "total_net_pnl_inr": round(tot_pnl, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy_pct": round(expectancy, 2),
        "avg_win_inr": round(avg_win, 2),
        "avg_loss_inr": round(avg_loss, 2),
        "win_loss_ratio": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0,
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_consecutive_losses": max_consec_loss,
        "avg_holding_days": round(t_df["holding_days"].mean(), 1)
    }

    return t_df, stats


def run_phase5_and_6():
    print("================================================================================")
    print("🔬 RUNNING PHASE 5 & 6: PORTFOLIO BACKTEST & 5-VARIANT BENCHMARK")
    print("================================================================================")

    data_files = sorted(list(DATA_DIR.glob("*.parquet")))
    symbol_dfs = {}
    print(f"Loading and processing {len(data_files)} stock datasets...")
    for f in data_files:
        df = pd.read_parquet(f)
        symbol_dfs[f.stem] = compute_signals_for_variants(df)

    variants_to_test = [
        ("1_Original_Scanner", "SIG_ORIGINAL"),
        ("2_Optimised_Scanner", "SIG_OPTIMISED"),
        ("3_Simplified_Scanner", "SIG_SIMPLIFIED"),
        ("4_High_Frequency_Scanner", "SIG_HIGH_FREQ"),
        ("5_High_Quality_Breakout", "SIG_HQ_BREAKOUT"),
    ]

    benchmark_rows = []
    trade_ledgers = {}

    for var_name, sig_col in variants_to_test:
        t_df, stats = run_single_simulation(symbol_dfs, sig_col, stop_loss_pct=2.0, profit_target_pct=4.0, max_holding_days=10)
        trade_ledgers[var_name] = t_df
        row = {"strategy_variant": var_name, **stats}
        benchmark_rows.append(row)

    bench_df = pd.DataFrame(benchmark_rows)
    bench_out = REPORTS_DIR / "FUTURES_STRATEGY_PORTFOLIO_BENCHMARK.csv"
    bench_df.to_csv(bench_out, index=False)
    print(f"✓ Exported portfolio benchmark to: {bench_out}")

    # Export Optimized Trade Ledger
    opt_ledger = trade_ledgers["2_Optimised_Scanner"]
    opt_out = REPORTS_DIR / "OPTIMISED_SCANNER_TRADE_LEDGER.csv"
    opt_ledger.to_csv(opt_out, index=False)
    print(f"✓ Exported optimized trade ledger ({len(opt_ledger)} trades) to: {opt_out}")

    # --------------------------------------------------------------------------
    # YEARLY BREAKDOWN COMPARISON
    # --------------------------------------------------------------------------
    yearly_records = []
    for var_name in ["1_Original_Scanner", "2_Optimised_Scanner", "3_Simplified_Scanner"]:
        t_df = trade_ledgers[var_name]
        for yr, grp in t_df.groupby("year"):
            wins = grp[grp["net_pnl"] > 0]
            losses = grp[grp["net_pnl"] <= 0]
            pf = (wins["net_pnl"].sum() / abs(losses["net_pnl"].sum())) if len(losses) > 0 else 0.0
            yearly_records.append({
                "strategy": var_name,
                "year": yr,
                "trades": len(grp),
                "win_rate_pct": round((len(wins) / len(grp)) * 100.0, 1),
                "net_pnl_inr": round(grp["net_pnl"].sum(), 2),
                "profit_factor": round(pf, 2),
                "avg_return_pct": round(grp["return_pct"].mean(), 2)
            })

    yearly_df = pd.DataFrame(yearly_records)
    yearly_out = REPORTS_DIR / "YEARLY_PERFORMANCE_BREAKDOWN.csv"
    yearly_df.to_csv(yearly_out, index=False)
    print(f"✓ Exported yearly performance breakdown to: {yearly_out}")

    # --------------------------------------------------------------------------
    # MARKET REGIME BREAKDOWN
    # 2021: Post-COVID Bull | 2022: Chop/Correction | 2023: Bull | 2024: Momentum Bull | 2025-26: Modern
    # --------------------------------------------------------------------------
    def get_regime(year: int) -> str:
        if year in [2021, 2023, 2024]:
            return "BULL_MARKET"
        elif year in [2022]:
            return "BEAR_OR_CHOP"
        else:
            return "SIDEWAYS_ROTATIONAL"

    regime_records = []
    for var_name in ["1_Original_Scanner", "2_Optimised_Scanner", "3_Simplified_Scanner"]:
        t_df = trade_ledgers[var_name].copy()
        t_df["regime"] = t_df["year"].apply(get_regime)
        for reg, grp in t_df.groupby("regime"):
            wins = grp[grp["net_pnl"] > 0]
            losses = grp[grp["net_pnl"] <= 0]
            pf = (wins["net_pnl"].sum() / abs(losses["net_pnl"].sum())) if len(losses) > 0 else 0.0
            regime_records.append({
                "strategy": var_name,
                "market_regime": reg,
                "trades": len(grp),
                "win_rate_pct": round((len(wins) / len(grp)) * 100.0, 1),
                "net_pnl_inr": round(grp["net_pnl"].sum(), 2),
                "profit_factor": round(pf, 2),
                "avg_return_pct": round(grp["return_pct"].mean(), 2)
            })

    regime_df = pd.DataFrame(regime_records)
    regime_out = REPORTS_DIR / "REGIME_PERFORMANCE_BREAKDOWN.csv"
    regime_df.to_csv(regime_out, index=False)
    print(f"✓ Exported market regime breakdown to: {regime_out}")

    print("\n--------------------------------------------------------------------------------")
    print("🏆 FINAL PORTFOLIO STRATEGY BENCHMARK RESULTS (2021-2026):")
    print("--------------------------------------------------------------------------------")
    for _, r in bench_df.iterrows():
        print(f"  {r['strategy_variant']:<26} | Trades: {r['total_trades']:<5} | WinRate: {r['win_rate_pct']:>5.1f}% | PF: {r['profit_factor']:>4.2f} | PnL: ₹{r['total_net_pnl_inr']:>10,.0f} | MaxDD: {r['max_drawdown_pct']:>5.1f}% | Sharpe: {r['sharpe_ratio']:>+5.2f}")
    print("================================================================================\n")


if __name__ == "__main__":
    run_phase5_and_6()
