#!/usr/bin/env python3
"""
================================================================================
HISTORICAL BACKTEST ENGINE — MY STRATEGY
================================================================================
Directory   : backtesting/my_strategy/
Role        : Realistic historical backtesting with Indian statutory frictions.
              Completely decoupled from live production and liveopenalgo.
Usage:
  python3 backtest.py
  python3 backtest.py --symbol INFY --interval 15m --days 180
================================================================================
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Load local configuration
from config import (
    BROKERAGE_PER_ORDER,
    DATA_DIR,
    EMA_FAST,
    EMA_SLOW,
    EXCHANGE,
    EXCHANGE_TURNOVER_PCT,
    GST_PCT,
    INITIAL_CAPITAL,
    INTERVAL,
    PROFIT_TARGET_PCT,
    REPORTS_DIR,
    RISK_PER_TRADE_PCT,
    RSI_BEARISH_THRESHOLD,
    RSI_BULLISH_THRESHOLD,
    RSI_PERIOD,
    SEBI_TURNOVER_PCT,
    SLIPPAGE_PCT,
    STAMP_DUTY_PCT,
    STOP_LOSS_PCT,
    STT_PCT,
    SYMBOL,
    TRAILING_SL_PCT,
)

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(), override=False)
except ImportError:
    pass

try:
    from openalgo import api, ta
    OPENALGO_AVAILABLE = True
except ImportError:
    OPENALGO_AVAILABLE = False
    api = None
    ta = None

try:
    import yfinance as yf
except ImportError:
    yf = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("BACKTEST_ENGINE")


def calculate_friction(buy_val: float, sell_val: float) -> float:
    """Calculates realistic Indian equity statutory charges and brokerage."""
    turnover = buy_val + sell_val
    brokerage = BROKERAGE_PER_ORDER * 2  # Entry + Exit
    stt = sell_val * STT_PCT
    exchange_charges = turnover * EXCHANGE_TURNOVER_PCT
    sebi_charges = turnover * SEBI_TURNOVER_PCT
    gst = (brokerage + exchange_charges) * GST_PCT
    stamp_duty = buy_val * STAMP_DUTY_PCT
    slippage = turnover * SLIPPAGE_PCT
    return brokerage + stt + exchange_charges + sebi_charges + gst + stamp_duty + slippage


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculates standard Relative Strength Index (RSI)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def load_historical_data(symbol: str, exchange: str, interval: str, days: int = 365) -> pd.DataFrame:
    """Fetches historical data from local CSV, OpenAlgo API, or yfinance fallback."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_file = DATA_DIR / f"{symbol}_{interval}.csv"

    def _normalize_df(d: pd.DataFrame) -> pd.DataFrame:
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = [col[0].lower() for col in d.columns]
        else:
            d.columns = [str(c).lower() for c in d.columns]

        if "timestamp" in d.columns:
            d["timestamp"] = pd.to_datetime(d["timestamp"])
            d = d.set_index("timestamp")
        elif "date" in d.columns:
            d["date"] = pd.to_datetime(d["date"])
            d = d.set_index("date")
        elif not isinstance(d.index, pd.DatetimeIndex):
            d.index = pd.to_datetime(d.index)

        d = d.sort_index()
        for col in ["open", "high", "low", "close", "volume"]:
            if col in d.columns:
                d[col] = pd.to_numeric(d[col], errors="coerce")
        return d.dropna(subset=["close"])

    # 1. Check local cached CSV
    if csv_file.exists():
        logger.info(f"Loading cached data from {csv_file}")
        try:
            df = pd.read_csv(csv_file)
            return _normalize_df(df)
        except Exception as e:
            logger.warning(f"Error reading {csv_file}: {e}. Refetching...")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # 2. Try OpenAlgo API
    api_key = os.getenv("OPENALGO_API_KEY")
    host = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")
    if OPENALGO_AVAILABLE and api_key:
        try:
            logger.info(f"Fetching {symbol} ({exchange}) from OpenAlgo server at {host}...")
            client = api(api_key=api_key, host=host)
            res = client.history(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
            if isinstance(res, pd.DataFrame) and not res.empty:
                df = _normalize_df(res)
                df.to_csv(csv_file, index=True, index_label="timestamp")
                logger.info(f"Saved {len(df)} candles to cache: {csv_file}")
                return df
        except Exception as e:
            logger.warning(f"OpenAlgo API fetch unsuccessful: {e}. Falling back...")

    # 3. Fallback to yfinance
    if yf:
        yf_symbol = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
        yf_interval = "1d" if interval.upper() in ["D", "1D"] else interval
        logger.info(f"Fetching fallback data via yfinance for {yf_symbol} ({yf_interval})...")
        df = yf.download(yf_symbol, start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"), interval=yf_interval, progress=False)
        if not df.empty:
            df = _normalize_df(df)
            df.to_csv(csv_file, index=True, index_label="timestamp")
            logger.info(f"Downloaded and cached {len(df)} candles via yfinance to {csv_file}")
            return df

    # 4. Generate realistic mock synthetic data if offline/unreachable
    logger.warning("No live data source available. Generating representative synthetic OHLCV for validation...")
    dates = pd.date_range(end=datetime.now(), periods=500, freq="15min" if interval == "15m" else "D")
    base_price = 2800.0
    returns = np.random.normal(0.0002, 0.01, size=len(dates))
    price = base_price * np.exp(np.cumsum(returns))
    df = pd.DataFrame({
        "open": price * (1 + np.random.normal(0, 0.001, len(dates))),
        "high": price * (1 + abs(np.random.normal(0, 0.003, len(dates)))),
        "low": price * (1 - abs(np.random.normal(0, 0.003, len(dates)))),
        "close": price,
        "volume": np.random.randint(50000, 500000, size=len(dates)),
    }, index=dates)
    return df


def run_backtest(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Runs the strategy backtest with SL/TP, trailing exits, and friction."""
    # Compute Indicators
    if ta and OPENALGO_AVAILABLE:
        df["ema_fast"] = ta.ema(df["close"], EMA_FAST)
        df["ema_slow"] = ta.ema(df["close"], EMA_SLOW)
        df["rsi"] = ta.rsi(df["close"], RSI_PERIOD)
    else:
        df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
        df["rsi"] = compute_rsi(df["close"], RSI_PERIOD)

    # Signal Generation: EMA Crossover + RSI Confirmation Filter
    df["ema_bullish_cross"] = (df["ema_fast"] > df["ema_slow"]) & (df["ema_fast"].shift(1) <= df["ema_slow"].shift(1))
    df["ema_bearish_cross"] = (df["ema_fast"] < df["ema_slow"]) & (df["ema_fast"].shift(1) >= df["ema_slow"].shift(1))

    df["long_signal"] = df["ema_bullish_cross"] & (df["rsi"] >= RSI_BULLISH_THRESHOLD)
    df["exit_signal"] = df["ema_bearish_cross"] | (df["rsi"] <= RSI_BEARISH_THRESHOLD)

    # Simulation Variables
    capital = INITIAL_CAPITAL
    position = 0
    entry_price = 0.0
    entry_time = None
    stop_loss = 0.0
    profit_target = 0.0
    trailing_high = 0.0
    trades: List[Dict[str, Any]] = []

    for timestamp, row in df.iterrows():
        close = float(row["close"])
        high = float(row.get("high", close))
        low = float(row.get("low", close))

        # Check Active Position Exits
        if position > 0:
            trailing_high = max(trailing_high, high)
            trailing_stop = trailing_high * (1.0 - (TRAILING_SL_PCT / 100.0))

            exit_reason = None
            exit_price = close

            # Check Hard Stop Loss
            if low <= stop_loss:
                exit_price = stop_loss
                exit_reason = "STOP_LOSS"
            # Check Profit Target
            elif high >= profit_target:
                exit_price = profit_target
                exit_reason = "PROFIT_TARGET"
            # Check Trailing Stop
            elif low <= trailing_stop and trailing_high > entry_price * 1.01:
                exit_price = trailing_stop
                exit_reason = "TRAILING_STOP"
            # Check Indicator Technical Exit
            elif bool(row["exit_signal"]):
                exit_price = close
                exit_reason = "SIGNAL_EXIT"

            if exit_reason:
                gross_pnl = (exit_price - entry_price) * position
                buy_turnover = entry_price * position
                sell_turnover = exit_price * position
                friction = calculate_friction(buy_turnover, sell_turnover)
                net_pnl = gross_pnl - friction
                capital += net_pnl

                trades.append({
                    "entry_time": entry_time,
                    "exit_time": timestamp,
                    "action": "LONG",
                    "quantity": position,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "gross_pnl": round(gross_pnl, 2),
                    "friction": round(friction, 2),
                    "net_pnl": round(net_pnl, 2),
                    "return_pct": round((net_pnl / buy_turnover) * 100, 2),
                    "exit_reason": exit_reason,
                    "capital_after": round(capital, 2),
                })
                position = 0
                entry_price = 0.0

        # Check New Entry
        elif position == 0 and bool(row["long_signal"]):
            # Position sizing based on capital and fixed risk %
            risk_amount = capital * (RISK_PER_TRADE_PCT / 100.0)
            sl_distance = close * (STOP_LOSS_PCT / 100.0)
            qty = max(1, int(risk_amount / sl_distance))
            trade_cost = qty * close

            if trade_cost <= capital * 0.95:  # Margin limit check
                position = qty
                entry_price = close
                entry_time = timestamp
                stop_loss = entry_price * (1.0 - (STOP_LOSS_PCT / 100.0))
                profit_target = entry_price * (1.0 + (PROFIT_TARGET_PCT / 100.0))
                trailing_high = entry_price

    trades_df = pd.DataFrame(trades)

    # Compute Summary Statistics
    total_trades = len(trades_df)
    if total_trades > 0:
        winning_trades = trades_df[trades_df["net_pnl"] > 0]
        losing_trades = trades_df[trades_df["net_pnl"] <= 0]
        win_rate = (len(winning_trades) / total_trades) * 100.0
        total_profit = winning_trades["net_pnl"].sum()
        total_loss = abs(losing_trades["net_pnl"].sum())
        profit_factor = round(total_profit / total_loss, 2) if total_loss > 0 else float("inf")

        # Peak & Drawdown
        equity_curve = [INITIAL_CAPITAL] + trades_df["capital_after"].tolist()
        peaks = pd.Series(equity_curve).cummax()
        drawdowns = (pd.Series(equity_curve) - peaks) / peaks * 100.0
        max_drawdown_pct = abs(drawdowns.min())

        total_net_pnl = capital - INITIAL_CAPITAL
        total_return_pct = (total_net_pnl / INITIAL_CAPITAL) * 100.0

        returns = trades_df["net_pnl"] / INITIAL_CAPITAL
        sharpe = round(float(returns.mean() / returns.std() * np.sqrt(252)), 2) if returns.std() > 0 else 0.0
    else:
        win_rate = 0.0
        profit_factor = 0.0
        max_drawdown_pct = 0.0
        total_net_pnl = 0.0
        total_return_pct = 0.0
        sharpe = 0.0

    summary = {
        "strategy_name": "MyCustomStrategy",
        "symbol": SYMBOL,
        "exchange": EXCHANGE,
        "interval": INTERVAL,
        "initial_capital": INITIAL_CAPITAL,
        "ending_capital": round(capital, 2),
        "total_net_pnl": round(total_net_pnl, 2),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe,
    }

    return trades_df, summary


def main():
    parser = argparse.ArgumentParser(description="My Strategy Historical Backtest Engine")
    parser.add_argument("--symbol", type=str, default=SYMBOL, help="Trading symbol (e.g. RELIANCE)")
    parser.add_argument("--exchange", type=str, default=EXCHANGE, help="Exchange (NSE/NFO/MCX)")
    parser.add_argument("--interval", type=str, default=INTERVAL, help="Candle timeframe (e.g. 15m, D)")
    parser.add_argument("--days", type=int, default=180, help="Historical lookback period in days")
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("================================================================================")
    print(f"📊 STARTING INDEPENDENT BACKTEST: {args.symbol} ({args.exchange}) [{args.interval}]")
    print("================================================================================")

    data = load_historical_data(args.symbol, args.exchange, args.interval, days=args.days)
    trades_df, summary = run_backtest(data)

    # Save Artifacts
    trades_path = REPORTS_DIR / "trade_history.csv"
    summary_path = REPORTS_DIR / "backtest_summary.json"

    trades_df.to_csv(trades_path, index=False)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Display Pretty Summary
    print("\n--------------------------------------------------------------------------------")
    print("📈 PERFORMANCE SUMMARY & AUDIT METRICS")
    print("--------------------------------------------------------------------------------")
    for k, v in summary.items():
        print(f"  {k.replace('_', ' ').title():<25} : {v}")
    print("--------------------------------------------------------------------------------")
    print(f"✓ Trade log exported to  : {trades_path}")
    print(f"✓ Summary exported to    : {summary_path}")
    print("================================================================================\n")


if __name__ == "__main__":
    main()
