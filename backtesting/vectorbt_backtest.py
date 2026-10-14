"""
================================================================================
VectorBT Professional Backtesting Script (backtesting/vectorbt_backtest.py)
================================================================================
Features:
  - VectorBT Fast Vectorized Simulation
  - Technical Indicators via TA-Lib / OpenAlgo TA
  - Signal Deduplication via openalgo.ta.exrem
  - Realistic Indian Market Fee Modeling (Statutory Charges + ₹20 Brokerage)
  - Benchmark Comparison (NIFTY 50 Buy-and-Hold)
  - Plain Language Risk and Performance Metrics
  - Export Trades to backtesting/reports/
================================================================================
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from dotenv import find_dotenv, load_dotenv

# Ensure project root is accessible
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Load .env without overriding shell environment
load_dotenv(find_dotenv(), override=False)

# Required Imports
try:
    import vectorbt as vbt
except ImportError:
    vbt = None

try:
    from openalgo import api, ta
except ImportError:
    api = None
    ta = None

try:
    import talib as tl
except ImportError:
    tl = None

try:
    import yfinance as yf
except ImportError:
    yf = None

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
OPENALGO_API_KEY = os.getenv("OPENALGO_API_KEY", "")
OPENALGO_HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

DEFAULT_SYMBOL = "SBIN"
DEFAULT_EXCHANGE = "NSE"
DEFAULT_INTERVAL = "15m"
DEFAULT_CAPITAL = 1_000_000.0  # ₹10 Lakh
DEFAULT_ALLOCATION = 0.75      # 75% per trade

# Indian Market Cost Constants (per side)
FEES_INTRADAY = 0.000225   # 0.0225% statutory (STT + Exchange + GST + Stamp)
FEES_DELIVERY = 0.00111    # 0.111% statutory for delivery
FIXED_FEES = 20.0          # ₹20 flat brokerage per order

BENCHMARK_SYMBOL = "^NSEI" # NIFTY 50 index proxy


# ==============================================================================
# DATA LOADER
# ==============================================================================
def load_historical_data(
    symbol: str, exchange: str, interval: str, days: int = 180
) -> pd.DataFrame:
    """
    Fetches OHLCV data using OpenAlgo API if available, with yfinance as fallback.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # 1. Try OpenAlgo API
    if api is not None and OPENALGO_API_KEY:
        try:
            client = api(api_key=OPENALGO_API_KEY, host=OPENALGO_HOST)
            print(f"[DATA] Querying OpenAlgo API for {symbol} ({exchange}) {interval}...", flush=True)
            df = client.history(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
            if isinstance(df, pd.DataFrame) and not df.empty:
                if "timestamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df = df.set_index("timestamp")
                elif not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                if df.index.tz is not None:
                    df.index = df.index.tz_convert(None)
                df.columns = [c.lower() for c in df.columns]
                return df
        except Exception as e:
            print(f"[WARN] OpenAlgo data fetch returned: {e}. Trying fallback...", flush=True)

    # 2. Fallback to Yahoo Finance
    if yf is not None:
        yf_ticker = f"{symbol}.NS" if exchange in ["NSE", "NFO"] else symbol
        print(f"[DATA] Fetching Yahoo Finance fallback for {yf_ticker}...", flush=True)
        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "60m": "1h", "D": "1d"}
        yf_interval = interval_map.get(interval, "1d")

        # Yahoo Finance limits intraday requests (1m-15m) to 59 days
        if yf_interval in ["1m", "5m", "15m"] and days > 59:
            print(f"[INFO] Yahoo Finance limits {interval} intraday data to 59 days. Clamping lookback to 59d.", flush=True)
            period_str = "59d"
        else:
            period_str = f"{days}d"

        df = yf.download(yf_ticker, period=period_str, interval=yf_interval, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                if "Ticker" in df.columns.names:
                    df = df.xs(yf_ticker, level="Ticker", axis=1).copy()
                else:
                    df = df.copy()
                    df.columns = [c[0] for c in df.columns]
            df.columns = [c.lower() for c in df.columns]
            df.index = pd.to_datetime(df.index)
            if df.index.tz is not None:
                df.index = df.index.tz_convert(None)
            return df.dropna()

    raise ValueError(f"Could not load data for {symbol} from either OpenAlgo or Yahoo Finance.")


# ==============================================================================
# INDICATORS & SIGNAL GENERATION
# ==============================================================================
def generate_ema_signals(close: pd.Series, fast: int, slow: int) -> tuple[pd.Series, pd.Series]:
    """Calculates EMA crossover signals with TA-Lib and cleans with openalgo.ta.exrem."""
    # Always prefer TA-Lib for technical indicators
    if tl is not None:
        ema_fast = pd.Series(tl.EMA(close.values.astype(np.float64), timeperiod=fast), index=close.index)
        ema_slow = pd.Series(tl.EMA(close.values.astype(np.float64), timeperiod=slow), index=close.index)
    elif ta is not None and hasattr(ta, "ema"):
        ema_fast = pd.Series(ta.ema(close, fast), index=close.index)
        ema_slow = pd.Series(ta.ema(close, slow), index=close.index)
    else:
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()

    # Raw Crossover Signals
    buy_raw = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
    sell_raw = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))

    # Clean consecutive signals with exrem
    if ta is not None and hasattr(ta, "exrem"):
        entries = pd.Series(ta.exrem(buy_raw.fillna(False), sell_raw.fillna(False)), index=close.index, dtype=bool)
        exits = pd.Series(ta.exrem(sell_raw.fillna(False), buy_raw.fillna(False)), index=close.index, dtype=bool)
    else:
        entries = buy_raw.fillna(False)
        exits = sell_raw.fillna(False)

    return entries, exits


# ==============================================================================
# VECTORBT SIMULATION
# ==============================================================================
def run_vectorbt_backtest(
    df: pd.DataFrame,
    symbol: str,
    fast_ema: int = 10,
    slow_ema: int = 20,
    initial_capital: float = DEFAULT_CAPITAL,
    allocation: float = DEFAULT_ALLOCATION,
    freq: str = "15m",
    show_plot: bool = False,
):
    """Executes VectorBT backtesting, prints institutional metrics, and exports trades."""
    if vbt is None:
        raise ImportError("VectorBT is not installed. Run using 'python3.11 backtesting/vectorbt_backtest.py'.")

    close = df["close"]
    entries, exits = generate_ema_signals(close, fast_ema, slow_ema)

    print("\n" + "=" * 80)
    print(f"VECTORBT BACKTEST ENGINE: {symbol} EMA({fast_ema}) / EMA({slow_ema})")
    print("=" * 80)
    print(f"  Bars Analyzed   : {len(close):,} bars")
    print(f"  Period          : {close.index[0].strftime('%Y-%m-%d')} to {close.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Initial Capital : Rs {initial_capital:,.0f}")
    print(f"  Allocation      : {allocation * 100:.0f}% per trade")
    print(f"  Entry Signals   : {entries.sum()} trades triggered")
    print("=" * 80 + "\n", flush=True)

    # 1. CORE VECTORBT COMMAND
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        init_cash=initial_capital,
        size=allocation,
        size_type="percent",
        fees=FEES_INTRADAY,
        fixed_fees=FIXED_FEES,
        direction="longonly",
        min_size=1,
        size_granularity=1,
        freq=freq,
    )

    # 2. Benchmark Portfolio (NIFTY 50 Buy-and-Hold)
    try:
        df_bench = yf.download(BENCHMARK_SYMBOL, start=close.index[0], end=close.index[-1], progress=False)
        if isinstance(df_bench.columns, pd.MultiIndex):
            bench_close = df_bench["Close"][BENCHMARK_SYMBOL]
        else:
            bench_close = df_bench["Close"]
        bench_close = bench_close.reindex(close.index).ffill().bfill()
        pf_bench = vbt.Portfolio.from_holding(bench_close, init_cash=initial_capital, fees=FEES_DELIVERY, freq=freq)
        has_benchmark = True
    except Exception:
        has_benchmark = False
        pf_bench = None

    # 3. Print VectorBT Stats
    print("=" * 80)
    print("DETAILED VECTORBT PERFORMANCE STATS")
    print("=" * 80)
    print(pf.stats().to_string())
    print("=" * 80 + "\n")

    # 4. Strategy vs Benchmark Comparison Table
    bench_ret_str = f"{pf_bench.total_return() * 100:+.2f}%" if has_benchmark else "N/A"
    bench_sh_str = f"{pf_bench.sharpe_ratio():.2f}" if has_benchmark else "N/A"
    bench_dd_str = f"{pf_bench.max_drawdown() * 100:.2f}%" if has_benchmark else "N/A"

    comparison = pd.DataFrame(
        {
            "Strategy": [
                f"{pf.total_return() * 100:+.2f}%",
                f"{pf.sharpe_ratio():.2f}",
                f"{pf.sortino_ratio():.2f}",
                f"{pf.max_drawdown() * 100:.2f}%",
                f"{pf.trades.win_rate() * 100:.1f}%",
                f"{pf.trades.count()}",
                f"{pf.trades.profit_factor():.2f}",
            ],
            f"Benchmark ({BENCHMARK_SYMBOL})": [
                bench_ret_str,
                bench_sh_str,
                "-",
                bench_dd_str,
                "-",
                "-",
                "-",
            ],
        },
        index=[
            "Total Return",
            "Sharpe Ratio",
            "Sortino Ratio",
            "Max Drawdown",
            "Win Rate",
            "Total Trades",
            "Profit Factor",
        ],
    )

    print("=" * 80)
    print("STRATEGY VS BENCHMARK COMPARISON")
    print("=" * 80)
    print(comparison.to_string())
    print("=" * 80 + "\n")

    # 5. Plain Language Explanation
    print("PLAIN LANGUAGE EXECUTIVE SUMMARY:")
    print(f"  * Total Return: The strategy gained {pf.total_return() * 100:+.2f}% after deducting all statutory fees & brokerage.")
    print(f"  * Worst Drawdown: {pf.max_drawdown() * 100:.2f}%. On Rs {initial_capital:,.0f}, the deepest dip was Rs {abs(pf.max_drawdown()) * initial_capital:,.0f}.")
    print(f"  * Win Rate: {pf.trades.win_rate() * 100:.1f}% across {pf.trades.count()} closed trades.")
    print(f"  * Profit Factor: {pf.trades.profit_factor():.2f} (values > 1.3 indicate institutional viability).")

    # 6. Export Trades
    reports_dir = ROOT_DIR / "backtesting" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    trades_path = reports_dir / f"{symbol.lower()}_vbt_trades.csv"
    try:
        trades_df = pf.trades.records_readable
        trades_df.to_csv(trades_path, index=False)
        print(f"\n[INFO] Trade records exported to: {trades_path}\n")
    except Exception as e:
        print(f"[WARN] Trade export skipped: {e}")

    # 7. Interactive Chart (Optional)
    if show_plot:
        print("[PLOT] Opening interactive VectorBT performance charts...")
        fig = pf.plot(subplots=["value", "underwater", "cum_returns"], template="plotly_dark")
        fig.show()


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="VectorBT Backtesting Engine for OpenAlgo")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help=f"Ticker symbol (default: {DEFAULT_SYMBOL}).")
    parser.add_argument("--exchange", default=DEFAULT_EXCHANGE, help=f"Exchange (default: {DEFAULT_EXCHANGE}).")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL, help=f"Candle interval (default: {DEFAULT_INTERVAL}).")
    parser.add_argument("--days", type=int, default=180, help="Lookback days (default: 180).")
    parser.add_argument("--fast-ema", type=int, default=10, help="Fast EMA period (default: 10).")
    parser.add_argument("--slow-ema", type=int, default=20, help="Slow EMA period (default: 20).")
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL, help=f"Initial capital (default: Rs {DEFAULT_CAPITAL:,.0f}).")
    parser.add_argument("--allocation", type=float, default=DEFAULT_ALLOCATION, help="Capital allocation per trade (default: 0.75).")
    parser.add_argument("--plot", action="store_true", help="Launch interactive Plotly dark charts.")

    args = parser.parse_args()

    df = load_historical_data(symbol=args.symbol, exchange=args.exchange, interval=args.interval, days=args.days)
    run_vectorbt_backtest(
        df=df,
        symbol=args.symbol,
        fast_ema=args.fast_ema,
        slow_ema=args.slow_ema,
        initial_capital=args.capital,
        allocation=args.allocation,
        freq=args.interval,
        show_plot=args.plot,
    )


if __name__ == "__main__":
    main()
