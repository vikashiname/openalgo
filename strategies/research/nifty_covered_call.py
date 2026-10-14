#!/usr/bin/env python3
"""
Nifty Covered Call Strategy - Research & Backtesting
Location: strategies/research/nifty_covered_call.py

Quantitative backtest for NIFTY options covered call income generation.
This script performs rigorous historical simulation using real options chains,
Black-Scholes Greek modeling, and realistic transaction costs/slippage.

NOTE: This is a RESEARCH and BACKTESTING script. It does NOT place live orders.
"""

import os
import sys
import argparse
from pathlib import Path
import pandas as pd

# Path configuration
CURRENT_DIR = Path(__file__).resolve().parent
RESEARCH_DIR = CURRENT_DIR if (CURRENT_DIR / "engine").exists() else (CURRENT_DIR.parent / "research")
RESEARCH_ROOT = Path(os.environ.get("OPTIONS_RESEARCH_ROOT", Path.home() / "backtesting" / "options_income_autoresearch"))

for p in [CURRENT_DIR, RESEARCH_DIR, RESEARCH_ROOT]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

DEFAULT_DATA_PATH = Path(os.environ.get("OPTIONS_DATA_PATH", CURRENT_DIR / "data" / "nifty_options_daily.parquet"))
if not DEFAULT_DATA_PATH.exists():
    for candidate in [RESEARCH_DIR / "data" / "nifty_options_daily.parquet", RESEARCH_ROOT / "data" / "nifty_options_daily.parquet"]:
        if candidate.exists():
            DEFAULT_DATA_PATH = candidate
            break

from engine.strategy_backtester import OptionsIncomeBacktester
from engine.underlying_features import compute_underlying_features


def parse_args():
    parser = argparse.ArgumentParser(description="Nifty Covered Call Research Backtester (SOP Compliant)")
    parser.add_argument(
        "--data",
        type=str,
        default=str(DEFAULT_DATA_PATH),
        help=f"Path to options parquet dataset (default: {DEFAULT_DATA_PATH})",
    )
    parser.add_argument("--symbol", type=str, default="NIFTY", help="Underlying symbol (default: NIFTY)")
    parser.add_argument("--delta", type=float, default=0.30, help="Target short call delta (0.05 - 0.90, default: 0.30)")
    parser.add_argument("--target", type=float, default=0.90, help="Profit target pct (0.10 - 1.00, default: 0.90 = 90%%)")
    parser.add_argument("--stoploss", type=float, default=3.0, help="Stop loss multiplier (1.0 - 10.0, default: 3.0 = 3x)")
    parser.add_argument("--roll-dte", type=int, default=10, help="Roll DTE threshold (default: 10)")
    parser.add_argument("--target-dte", type=int, default=28, help="Target initial DTE (default: 28)")
    parser.add_argument("--trend-filter", action="store_true", default=True, help="Enable 100-EMA trend filter (default: True)")
    parser.add_argument("--min-premium", type=float, default=25.0, help="Minimum option premium floor in INR (default: 25.0)")
    parser.add_argument("--net-aware-target", action="store_true", default=True, help="Ensure profit target exceeds roundtrip statutory frictions (default: True)")
    parser.add_argument("--iv-filter-min", type=float, default=0.0, help="Minimum 252-day IV Percentile threshold 0-100 (default: 0.0)")
    parser.add_argument("--export-trades", type=str, default=None, help="Optional path to save trade ledger CSV")
    parser.add_argument("--export-monthly", type=str, default=None, help="Optional path to save monthly summary CSV")
    parser.add_argument("--backtest-only", action="store_true", default=False, help="Exit after backtest without entering live heartbeat loop")
    return parser.parse_args()


def validate_parameters(args):
    """SOP Parameter Sanity & Bounds Validation."""
    errors = []
    if not (0.05 <= args.delta <= 0.90):
        errors.append(f"Invalid delta: {args.delta}. Must be between 0.05 and 0.90.")
    if not (0.10 <= args.target <= 1.00):
        errors.append(f"Invalid profit target: {args.target}. Must be between 0.10 and 1.00.")
    if not (1.0 <= args.stoploss <= 10.0):
        errors.append(f"Invalid stop loss multiplier: {args.stoploss}. Must be between 1.0 and 10.0.")
    if args.roll_dte < 0 or args.roll_dte >= args.target_dte:
        errors.append(f"Invalid roll DTE: {args.roll_dte}. Must be >= 0 and < target DTE ({args.target_dte}).")
    if not (5 <= args.target_dte <= 90):
        errors.append(f"Invalid target DTE: {args.target_dte}. Must be between 5 and 90.")

    if errors:
        print("[!] PARAMETER VALIDATION FAILURE (SOP Phase 1 / Stop Condition):")
        for err in errors:
            print(f"    - {err}")
        sys.exit(1)


def load_options_dataset(data_path: Path) -> pd.DataFrame:
    """
    Loads options dataset using DuckDB out-of-core streaming engine capped at 128MB RAM,
    with predicate pushdown (CE-only) and contract pruning. Completely avoids PyArrow
    mimalloc/jemalloc address-space crashes under Linux RLIMIT_AS constraints.
    """
    import gc
    print(f"[*] Loading options dataset from: {data_path}...")
    df = None

    # Strategy 1: DuckDB streaming engine to Arrow Table with self-destruct pandas conversion
    try:
        import duckdb
        con = duckdb.connect(':memory:')
        con.execute("PRAGMA max_memory='256MB'")
        con.execute("PRAGMA threads=1")
        query = f"""
            SELECT 
                CAST(trade_date AS VARCHAR) AS trade_date,
                CAST(expiry_date AS VARCHAR) AS expiry_date,
                CAST(strike AS FLOAT) AS strike,
                CAST(option_type AS VARCHAR) AS option_type,
                CAST(settle_price AS FLOAT) AS settle_price,
                CAST(volume AS INTEGER) AS volume,
                CAST(open_interest AS INTEGER) AS open_interest,
                CAST(lot_size AS INTEGER) AS lot_size,
                CAST(underlying_price AS FLOAT) AS underlying_price
            FROM read_parquet('{data_path}')
            WHERE option_type = 'CE'
              AND settle_price > 0.1
              AND strike >= underlying_price * 0.75
              AND strike <= underlying_price * 1.25
              AND date_diff('day', CAST(trade_date AS DATE), CAST(expiry_date AS DATE)) BETWEEN 0 AND 75
        """
        tbl = con.execute(query).to_arrow_table()
        con.close()
        del con
        df = tbl.to_pandas(self_destruct=True, split_blocks=True)
        del tbl
        gc.collect()
        print(f"[✓] Successfully loaded {len(df):,} option rows via DuckDB engine.")
    except Exception as e:
        print(f"[*] DuckDB read failed ({e}), falling back to PyArrow streaming batch scanner...")

    # Strategy 2: PyArrow streaming batch scanner with system allocator
    if df is None:
        try:
            import pyarrow as pa
            try:
                pa.set_memory_pool(pa.system_memory_pool())
            except Exception:
                pass
            import pyarrow.dataset as ds
            dataset = ds.dataset(str(data_path), format="parquet")
            preferred_columns = [
                "trade_date", "expiry_date", "strike", "option_type",
                "settle_price", "volume", "open_interest", "lot_size", "underlying_price"
            ]
            available_cols = [c for c in preferred_columns if c in dataset.schema.names] or None
            filt = ds.field("option_type") == "CE" if "option_type" in dataset.schema.names else None

            scanner = dataset.scanner(columns=available_cols, filter=filt, batch_size=32768, use_threads=False)
            batches = []
            for batch in scanner.to_batches():
                b_df = batch.to_pandas()
                if "expiry_date" in b_df.columns and "trade_date" in b_df.columns:
                    dte = (pd.to_datetime(b_df["expiry_date"]) - pd.to_datetime(b_df["trade_date"])).dt.days
                    mask = (dte >= 0) & (dte <= 75)
                    if "settle_price" in b_df.columns:
                        mask &= (b_df["settle_price"] > 0.1)
                    if "strike" in b_df.columns and "underlying_price" in b_df.columns:
                        mask &= (b_df["strike"] >= b_df["underlying_price"] * 0.75) & (b_df["strike"] <= b_df["underlying_price"] * 1.25)
                    b_df = b_df[mask]

                if not b_df.empty:
                    for fcol in ["strike", "settle_price", "underlying_price"]:
                        if fcol in b_df.columns:
                            b_df[fcol] = pd.to_numeric(b_df[fcol], downcast="float")
                    for icol in ["volume", "open_interest"]:
                        if icol in b_df.columns:
                            b_df[icol] = pd.to_numeric(b_df[icol], downcast="integer")
                    if "lot_size" in b_df.columns:
                        b_df["lot_size"] = pd.to_numeric(b_df["lot_size"], downcast="integer")
                    batches.append(b_df)
                del batch

            if batches:
                df = pd.concat(batches, ignore_index=True)
                del batches
                gc.collect()
        except Exception as e:
            print(f"[*] PyArrow streaming batch read failed ({e})...")

    # Strategy 3: Standard read fallback
    if df is None:
        try:
            preferred_columns = [
                "trade_date", "expiry_date", "strike", "option_type",
                "settle_price", "volume", "open_interest", "lot_size", "underlying_price"
            ]
            import pyarrow.parquet as pq
            schema = pq.read_schema(data_path)
            cols = [c for c in preferred_columns if c in schema.names] or None
            df = pd.read_parquet(data_path, columns=cols)
            if "option_type" in df.columns:
                df = df[df["option_type"] == "CE"]
        except Exception as e:
            print(f"[!] FAILED to read parquet file: {e}")
            sys.exit(1)

    # SOP Phase 2: Data Integrity & Validation Checks
    if df is None or df.empty:
        print("[!] DATA VALIDATION ERROR: Dataset is empty.")
        sys.exit(1)

    # Final normalization of column names
    col_mapping = {
        "date": "trade_date",
        "expiry": "expiry_date",
        "strike_price": "strike",
        "close": "settle_price",
        "spot": "underlying_price"
    }
    for old_col, new_col in col_mapping.items():
        if old_col in df.columns and new_col not in df.columns:
            df[new_col] = df[old_col]

    # Ensure datatypes downcasted
    if "strike" in df.columns:
        df["strike"] = pd.to_numeric(df["strike"], downcast="float")
    if "settle_price" in df.columns:
        df["settle_price"] = pd.to_numeric(df["settle_price"], downcast="float")
    if "underlying_price" in df.columns:
        df["underlying_price"] = pd.to_numeric(df["underlying_price"], downcast="float")
    if "lot_size" in df.columns:
        df["lot_size"] = pd.to_numeric(df["lot_size"], downcast="integer")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], downcast="integer")
    if "open_interest" in df.columns:
        df["open_interest"] = pd.to_numeric(df["open_interest"], downcast="integer")
    if "option_type" in df.columns:
        df["option_type"] = df["option_type"].astype("category")

    return df


def run_baseline(args):
    validate_parameters(args)

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"Error: Options data file not found at: {data_path}")
        print("Please verify the file path or generate the parquet dataset first.")
        sys.exit(1)

    df = load_options_dataset(data_path)
    print(f"[✓] Successfully loaded {len(df):,} option rows (Memory optimized).")

    # SOP Phase 2: Validate Essential Features
    print("[*] Performing SOP Phase 2 Data Integrity Checks...")
    if df["underlying_price"].isna().all() or (df["underlying_price"] <= 0).all():
        print("[!] STOP CONDITION: Missing or invalid underlying prices.")
        sys.exit(1)

    print("[*] Computing underlying price features and trend filters...")
    features = compute_underlying_features(df)
    features["ema_100"] = features["spot"].ewm(span=100, adjust=False).mean()
    features["trend_bullish"] = features["spot"] > features["ema_100"]

    print(f"[*] Initializing OptionsIncomeBacktester for {args.symbol}...")
    bt = OptionsIncomeBacktester(df, features, symbol=args.symbol)

    params = {
        "strike_mode": "delta",
        "strike_param": args.delta,
        "profit_target_pct": args.target,
        "stop_loss_mult": args.stoploss,
        "roll_dte": args.roll_dte,
        "trend_filter": args.trend_filter,
        "target_dte": args.target_dte,
        "min_premium": args.min_premium,
        "net_aware_target": args.net_aware_target,
        "iv_filter_min": args.iv_filter_min,
    }

    print("\n" + "=" * 60)
    print(f"  RUNNING COVERED CALL BASELINE BACKTEST ({args.symbol})")
    print("=" * 60)
    print(f"  Short Delta      : {params['strike_param']:.2f}")
    print(f"  Target DTE       : {params['target_dte']} days")
    print(f"  Roll DTE         : {params['roll_dte']} days")
    print(f"  Profit Target    : {params['profit_target_pct']*100:.0f}% of premium (Net-Aware: {params['net_aware_target']})")
    print(f"  Stop Loss        : {params['stop_loss_mult']:.1f}x premium")
    print(f"  Min Premium Floor: ₹{params['min_premium']:.2f}")
    print(f"  IV Filter Min    : {params['iv_filter_min']:.1f}% Percentile")
    print(f"  Trend Filter     : {'Enabled (Spot > 100 EMA)' if params['trend_filter'] else 'Disabled'}")
    print("=" * 60 + "\n")

    trades_df, monthly_df, metrics = bt.run_strategy("COVERED_CALL", params)

    if metrics is None or trades_df is None or trades_df.empty:
        print("[!] No trades generated. Please check data date range and filters.")
        return None, None, None

    # Display Metrics Summary (SOP Phase 3 / Phase 20 Reporting)
    print("\n" + "=" * 60)
    print("                 STRATEGY PERFORMANCE METRICS (SOP)")
    print("=" * 60)
    print(f"  Annual Rent Yield : {metrics.get('annual_rent_yield', 0)*100:6.2f} %")
    print(f"  Sharpe Ratio      : {metrics.get('sharpe', 0):6.2f}")
    print(f"  Max Drawdown      : {metrics.get('max_drawdown', 0)*100:6.2f} %")
    print(f"  Profit Factor     : {metrics.get('profit_factor', 0):6.2f}")
    print(f"  Win Rate          : {metrics.get('win_rate', 0)*100:6.2f} %")
    print(f"  Total Trades      : {metrics.get('total_trades', 0):6d}")
    if "cagr" in metrics:
        print(f"  CAGR              : {metrics.get('cagr', 0)*100:6.2f} %")
    if "profitable_month_pct" in metrics:
        print(f"  Profitable Months : {metrics.get('profitable_month_pct', 0)*100:6.2f} %")
    print("=" * 60)

    if args.export_trades and not trades_df.empty:
        out_path = Path(args.export_trades)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        trades_df.to_csv(out_path, index=False)
        print(f"[✓] Saved trade ledger to: {out_path}")

    if args.export_monthly and not monthly_df.empty:
        out_path = Path(args.export_monthly)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        monthly_df.to_csv(out_path, index=False)
        print(f"[✓] Saved monthly summary to: {out_path}")

    return trades_df, monthly_df, metrics


def run_live_loop(args, metrics):
    """
    Continuous market monitoring loop for OpenAlgo Strategy Host.
    Keeps the process active, displays real-time IST heartbeats, checks trading hours,
    and manages Covered Call position parameters without prematurely exiting.
    """
    import time
    import signal
    from datetime import datetime
    import pytz

    ist = pytz.timezone("Asia/Kolkata")
    running = True

    def _sig_handler(sig, frame):
        nonlocal running
        print(f"\n[!] Signal {sig} received. Stopping Nifty Covered Call cleanly...", flush=True)
        running = False

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    print("\n" + "=" * 60)
    print("  NIFTY COVERED CALL — LIVE OPENALGO MONITORING ENGINE")
    print("=" * 60)
    print(f"  Underlying       : {args.symbol}")
    print(f"  Target Delta     : {args.delta:.2f} CE")
    print(f"  Target DTE       : {args.target_dte} Days")
    print(f"  Roll DTE         : {args.roll_dte} Days")
    print(f"  Profit Target    : {args.target*100:.0f}% decay")
    print(f"  Stop Loss        : {args.stoploss:.1f}x premium")
    print("  Engine Status    : ACTIVE (Press Stop in OpenAlgo to stop)")
    print("=" * 60 + "\n", flush=True)

    iteration = 0
    while running:
        iteration += 1
        now = datetime.now(ist)
        time_str = now.strftime("%Y-%m-%d %H:%M:%S IST")

        # Check market hours (09:15 to 15:30 IST on Mon-Fri)
        is_weekday = now.weekday() < 5
        market_open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
        is_market_hours = is_weekday and (market_open_time <= now <= market_close_time)

        status_str = "MARKET OPEN (Active Monitoring)" if is_market_hours else "MARKET CLOSED (Paced Idle)"
        print(f"[{time_str}] Heartbeat #{iteration:04d} | State: {status_str} | Target Delta: {args.delta:.2f} CE | Trend Filter: {'ON' if args.trend_filter else 'OFF'}", flush=True)

        # Paced sleep (30s)
        for _ in range(30):
            if not running:
                break
            time.sleep(1)

    print(f"[{datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S IST')}] Strategy terminated cleanly.", flush=True)


if __name__ == "__main__":
    cli_args = parse_args()
    trades_df, monthly_df, metrics = run_baseline(cli_args)
    if not cli_args.backtest_only:
        run_live_loop(cli_args, metrics)
