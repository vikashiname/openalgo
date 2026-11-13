#!/usr/bin/env python3
"""
================================================================================
PHASE 5: ORIGINAL SCANNER BASELINE STRATEGY BACKTEST
================================================================================
Directory   : backtesting/futurebull/
Role        : Backtests the original 29-condition scanner as an executable
              trading strategy on 46 liquid Indian stock futures (2021-2026).
              Enforces Next-Day Open execution, lot-size position sizing,
              and realistic Indian futures transaction frictions.
Outputs:
  - reports/ORIGINAL_SCANNER_TRADE_LEDGER.csv
  - reports/ORIGINAL_SCANNER_EXIT_MODELS_SUMMARY.csv
================================================================================
"""

import sys
from pathlib import Path
from typing import Dict, List, Any
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


def calculate_futures_friction(buy_turnover: float, sell_turnover: float) -> float:
    total_turnover = buy_turnover + sell_turnover
    brokerage = BROKERAGE_PER_ORDER * 2.0
    stt = sell_turnover * STT_FUTURES_SELL
    exch = total_turnover * EXCHANGE_TURNOVER
    gst = (brokerage + exch) * GST_RATE
    stamp = buy_turnover * STAMP_DUTY_BUY
    slippage = total_turnover * SLIPPAGE_RATE
    return brokerage + stt + exch + gst + stamp + slippage


def simulate_strategy_trades(
    symbol: str,
    df: pd.DataFrame,
    signal_col: str = "COMBO_ALL_ORIGINAL",
    max_holding_days: int = 10,
    stop_loss_pct: float = 2.0,
    profit_target_pct: float = 4.0,
    trailing_sl_pct: Optional[float] = None,
    lot_capital: float = 200000.0,
) -> List[Dict[str, Any]]:
    """Simulates realistic futures trades from signal day to next-day open entry."""
    trades = []
    in_trade = False
    entry_price = 0.0
    entry_idx = 0
    entry_date = None
    stop_loss = 0.0
    target_price = 0.0
    trailing_high = 0.0

    length = len(df)
    dates = df.index
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    signals = df[signal_col].values

    for i in range(length - 1):
        if not in_trade:
            # Signal generated at close of day i -> Enter at open of day i+1
            if signals[i]:
                entry_idx = i + 1
                entry_date = dates[entry_idx]
                entry_price = opens[entry_idx]
                if entry_price <= 0 or np.isnan(entry_price):
                    continue
                in_trade = True
                stop_loss = entry_price * (1.0 - stop_loss_pct / 100.0)
                target_price = entry_price * (1.0 + profit_target_pct / 100.0) if profit_target_pct else float("inf")
                trailing_high = entry_price
        else:
            current_bar = i
            h = highs[current_bar]
            l = lows[current_bar]
            c = closes[current_bar]
            dt = dates[current_bar]

            trailing_high = max(trailing_high, h)
            current_trailing_sl = trailing_high * (1.0 - trailing_sl_pct / 100.0) if trailing_sl_pct else 0.0

            holding_bars = current_bar - entry_idx + 1
            exit_price = None
            exit_reason = None

            # 1. Stop loss hit
            if l <= stop_loss:
                exit_price = stop_loss
                exit_reason = "STOP_LOSS"
            # 2. Profit target hit
            elif h >= target_price:
                exit_price = target_price
                exit_reason = "PROFIT_TARGET"
            # 3. Trailing SL hit
            elif trailing_sl_pct and l <= current_trailing_sl and trailing_high > entry_price * 1.01:
                exit_price = current_trailing_sl
                exit_reason = "TRAILING_SL"
            # 4. Max holding period reached
            elif holding_bars >= max_holding_days:
                exit_price = c
                exit_reason = f"TIME_EXIT_{max_holding_days}D"

            if exit_reason:
                shares = max(1, int(lot_capital / entry_price))
                buy_val = shares * entry_price
                sell_val = shares * exit_price
                gross_pnl = sell_val - buy_val
                friction = calculate_futures_friction(buy_val, sell_val)
                net_pnl = gross_pnl - friction
                return_pct = (net_pnl / buy_val) * 100.0

                trades.append({
                    "symbol": symbol,
                    "entry_date": str(entry_date.date()) if hasattr(entry_date, "date") else str(entry_date),
                    "exit_date": str(dt.date()) if hasattr(dt, "date") else str(dt),
                    "holding_days": holding_bars,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "shares": shares,
                    "gross_pnl": round(gross_pnl, 2),
                    "friction": round(friction, 2),
                    "net_pnl": round(net_pnl, 2),
                    "return_pct": round(return_pct, 2),
                    "exit_reason": exit_reason
                })
                in_trade = False

    return trades


def run_original_backtest():
    print("================================================================================")
    print("🔬 RUNNING PHASE 5: ORIGINAL SCANNER BASELINE STRATEGY BACKTEST")
    print("================================================================================")

    data_files = sorted(list(DATA_DIR.glob("*.parquet")))
    symbol_dfs = {}
    print(f"Loading data for {len(data_files)} symbols...")
    for f in data_files:
        df = pd.read_parquet(f)
        symbol = f.stem
        symbol_dfs[symbol] = compute_all_filters(df)

    # Exit Model Experiments (Required in Section 9)
    exit_configs = [
        {"name": "Fixed_Holding_3D", "hold_days": 3, "sl": 99.0, "tp": 99.0, "trail": None},
        {"name": "Fixed_Holding_5D", "hold_days": 5, "sl": 99.0, "tp": 99.0, "trail": None},
        {"name": "Fixed_Holding_10D", "hold_days": 10, "sl": 99.0, "tp": 99.0, "trail": None},
        {"name": "Fixed_Holding_20D", "hold_days": 20, "sl": 99.0, "tp": 99.0, "trail": None},
        {"name": "SL1.5_TP3_Hold10D", "hold_days": 10, "sl": 1.5, "tp": 3.0, "trail": None},
        {"name": "SL2.0_TP4_Hold10D", "hold_days": 10, "sl": 2.0, "tp": 4.0, "trail": None},
        {"name": "SL3.0_TP5_Hold10D", "hold_days": 10, "sl": 3.0, "tp": 5.0, "trail": None},
        {"name": "SL2.0_Trailing1.5_Hold10D", "hold_days": 10, "sl": 2.0, "tp": 99.0, "trail": 1.5},
    ]

    summary_rows = []
    primary_trades = []

    for cfg in exit_configs:
        cfg_trades = []
        for symbol, df in symbol_dfs.items():
            t = simulate_strategy_trades(
                symbol=symbol,
                df=df,
                signal_col="COMBO_ALL_ORIGINAL",
                max_holding_days=cfg["hold_days"],
                stop_loss_pct=cfg["sl"],
                profit_target_pct=cfg["tp"],
                trailing_sl_pct=cfg["trail"],
            )
            cfg_trades.extend(t)

        t_df = pd.DataFrame(cfg_trades)
        total_trades = len(t_df)

        if total_trades > 0:
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
            expectancy_pct = t_df["return_pct"].mean()

            # Max drawdown on sequential capital
            initial_cap = 1000000.0
            equity = initial_cap + t_df["net_pnl"].cumsum()
            peaks = equity.cummax()
            dd = (equity - peaks) / peaks * 100.0
            max_dd = abs(dd.min())
            avg_hold = t_df["holding_days"].mean()
            sharpe = (t_df["return_pct"].mean() / t_df["return_pct"].std() * np.sqrt(252)) if t_df["return_pct"].std() > 0 else 0.0
        else:
            win_rate = tot_pnl = avg_win = avg_loss = win_loss_ratio = profit_factor = expectancy_pct = max_dd = avg_hold = sharpe = 0.0

        summary_rows.append({
            "exit_model": cfg["name"],
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy_pct": round(expectancy_pct, 2),
            "total_net_pnl": round(tot_pnl, 2),
            "avg_win_inr": round(avg_win, 2),
            "avg_loss_inr": round(avg_loss, 2),
            "win_loss_ratio": round(win_loss_ratio, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "avg_holding_days": round(avg_hold, 1)
        })

        if cfg["name"] == "SL2.0_TP4_Hold10D":
            primary_trades = cfg_trades

    summary_df = pd.DataFrame(summary_rows)
    summary_out = REPORTS_DIR / "ORIGINAL_SCANNER_EXIT_MODELS_SUMMARY.csv"
    summary_df.to_csv(summary_out, index=False)
    print(f"✓ Exported exit model summary to: {summary_out}")

    primary_df = pd.DataFrame(primary_trades)
    primary_out = REPORTS_DIR / "ORIGINAL_SCANNER_TRADE_LEDGER.csv"
    primary_df.to_csv(primary_out, index=False)
    print(f"✓ Exported primary trade ledger ({len(primary_df)} trades) to: {primary_out}")

    print("\n--------------------------------------------------------------------------------")
    print("📊 ORIGINAL SCANNER EXIT MODEL PERFORMANCE:")
    print("--------------------------------------------------------------------------------")
    for _, r in summary_df.iterrows():
        print(f"  {r['exit_model']:<28} | Trades: {r['total_trades']:<5} | WinRate: {r['win_rate_pct']:>5.1f}% | PF: {r['profit_factor']:>4.2f} | Exp: {r['expectancy_pct']:>+5.2f}% | MaxDD: {r['max_drawdown_pct']:>5.1f}% | Sharpe: {r['sharpe_ratio']:>+5.2f}")
    print("================================================================================\n")


if __name__ == "__main__":
    run_original_backtest()
