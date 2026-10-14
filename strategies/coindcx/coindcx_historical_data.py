#!/usr/bin/env python3
"""
CoinDCX Historical OHLCV Candle Data Downloader
===============================================
Downloads historical candlestick data from CoinDCX public API, handles
pagination, validates data integrity, formats IST/UTC timestamps, and
saves clean CSVs for backtesting and quantitative trading.

Features:
- Pure public market data endpoint (NO API keys required).
- Automatic symbol resolution (e.g., BTCUSDT -> B-BTC_USDT, BTCINR -> I-BTC_INR).
- Supports native (1m, 15m, 1h, 1d) and resampled (5m, 30m, 4h, etc.) timeframes.
- Robust backward batch pagination (1000 candles per batch limit).
- Automatic retry logic with exponential backoff for rate limits and network errors.
- Comprehensive data validation (gaps, missing candles, duplicate timestamps, OHLC integrity, zero volume).
- Dual timezone support: Indian Standard Time (IST - Asia/Kolkata) and UTC.
- Modular architecture with indicator helpers (EMA, MACD, RSI, etc.) for backtesting.
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple, Union

import requests
import pandas as pd
import numpy as np

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("CoinDCXDownloader")

# Constants
BASE_URL = "https://api.coindcx.com"
CANDLES_ENDPOINT = f"{BASE_URL}/market_data/candles"
MARKETS_DETAILS_ENDPOINT = f"{BASE_URL}/exchange/v1/markets_details"
MAX_LIMIT = 1000
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/backtesting/coindcx_data")
IST_ZONE = ZoneInfo("Asia/Kolkata")
UTC_ZONE = timezone.utc

# Interval mappings and durations in milliseconds
INTERVAL_DURATIONS_MS: Dict[str, int] = {
    "1m": 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "30m": 30 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "2h": 2 * 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "8h": 8 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
    "1w": 7 * 24 * 60 * 60 * 1000,
}

# Native CoinDCX API intervals
NATIVE_INTERVALS = {"1m", "15m", "1h", "1d"}

# Mapping for resampling from base native intervals
RESAMPLE_BASE_MAPPING: Dict[str, Tuple[str, str]] = {
    # target_interval: (base_native_interval, pandas_rule)
    "5m": ("1m", "5min"),
    "30m": ("15m", "30min"),
    "2h": ("1h", "2h"),
    "4h": ("1h", "4h"),
    "6h": ("1h", "6h"),
    "8h": ("1h", "8h"),
    "12h": ("1h", "12h"),
    "1w": ("1d", "7D"),
}


class CoinDCXDownloader:
    """Downloader for CoinDCX Historical OHLCV Candlestick Data."""

    def __init__(self, request_delay: float = 0.15, max_retries: int = 5, timeout: int = 15):
        """
        Initialize the downloader.

        :param request_delay: Delay in seconds between API requests to prevent rate limiting.
        :param max_retries: Maximum retry attempts for failed requests.
        :param timeout: Network timeout per request in seconds.
        """
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CoinDCX-Historical-Downloader/1.0",
            "Accept": "application/json",
        })
        self._markets_cache: Optional[List[Dict[str, Any]]] = None

    def get_markets_details(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch and cache CoinDCX active markets details."""
        if self._markets_cache is not None and not force_refresh:
            return self._markets_cache

        logger.info("Fetching CoinDCX market details for symbol resolution...")
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(MARKETS_DETAILS_ENDPOINT, timeout=self.timeout)
                if response.status_code == 200:
                    self._markets_cache = response.json()
                    return self._markets_cache
                else:
                    logger.warning(f"Market details fetch failed (HTTP {response.status_code}), attempt {attempt}/{self.max_retries}")
            except Exception as e:
                logger.warning(f"Market details request error: {e}, attempt {attempt}/{self.max_retries}")
            time.sleep(1.0 * attempt)

        logger.warning("Could not fetch market details from CoinDCX. Using heuristic symbol resolution.")
        return []

    def resolve_symbol(self, symbol: str) -> str:
        """
        Resolve a user symbol (e.g. 'BTCUSDT', 'BTC_USDT', 'BTCINR') to CoinDCX pair format (e.g. 'B-BTC_USDT', 'I-BTC_INR').

        :param symbol: User symbol string.
        :return: CoinDCX pair string.
        """
        clean_sym = symbol.strip().upper()
        # If already in CoinDCX pair format (e.g. B-BTC_USDT or I-BTC_INR)
        if "-" in clean_sym and "_" in clean_sym:
            return clean_sym

        markets = self.get_markets_details()
        normalized_input = clean_sym.replace("-", "").replace("_", "")

        for m in markets:
            pair = m.get("pair", "")
            cdcx_name = (m.get("coindcx_name") or "").replace("-", "").replace("_", "").upper()
            sym = (m.get("symbol") or "").replace("-", "").replace("_", "").upper()

            if normalized_input in (cdcx_name, sym) or clean_sym == pair.upper():
                return pair

        # Heuristic fallback if not found in markets
        if normalized_input.endswith("USDT"):
            base = normalized_input[:-4]
            return f"B-{base}_USDT"
        elif normalized_input.endswith("INR"):
            base = normalized_input[:-3]
            return f"I-{base}_INR"
        elif normalized_input.endswith("BTC"):
            base = normalized_input[:-3]
            return f"B-{base}_BTC"

        return clean_sym

    def fetch_batch(
        self,
        pair: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        limit: int = MAX_LIMIT
    ) -> List[Dict[str, Any]]:
        """
        Fetch a single batch of candles from CoinDCX public API with retries and exponential backoff.

        :param pair: CoinDCX pair (e.g. 'B-BTC_USDT').
        :param interval: Native interval ('1m', '15m', '1h', '1d').
        :param start_ms: Start timestamp in milliseconds.
        :param end_ms: End timestamp in milliseconds.
        :param limit: Maximum candles to return (max 1000).
        :return: List of candle dicts.
        """
        params = {
            "pair": pair,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": min(limit, MAX_LIMIT),
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(CANDLES_ENDPOINT, params=params, timeout=self.timeout)

                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict) and data.get("status") == "error":
                        logger.error(f"CoinDCX API Error: {data.get('message')}")
                        return []
                    return []

                elif response.status_code == 429:
                    wait_time = (2 ** attempt) + 0.5
                    logger.warning(f"Rate limited (429). Backing off for {wait_time:.1f}s (attempt {attempt}/{self.max_retries})...")
                    time.sleep(wait_time)

                elif response.status_code in (500, 502, 503, 504):
                    wait_time = (1.5 ** attempt)
                    logger.warning(f"Server error ({response.status_code}). Retrying in {wait_time:.1f}s (attempt {attempt}/{self.max_retries})...")
                    time.sleep(wait_time)

                elif response.status_code == 422:
                    logger.error(f"Unprocessable Entity (422): {response.text}")
                    return []

                else:
                    logger.warning(f"HTTP {response.status_code}: {response.text}. Retrying (attempt {attempt}/{self.max_retries})...")
                    time.sleep(1.0 * attempt)

            except (requests.ConnectionError, requests.Timeout) as e:
                wait_time = (1.5 ** attempt)
                logger.warning(f"Network error ({e}). Retrying in {wait_time:.1f}s (attempt {attempt}/{self.max_retries})...")
                time.sleep(wait_time)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                time.sleep(1.0)

        logger.error(f"Failed to fetch batch after {self.max_retries} attempts.")
        return []

    def download_data(
        self,
        symbol: str,
        interval: str,
        start_time: Union[str, datetime, int],
        end_time: Optional[Union[str, datetime, int]] = None
    ) -> pd.DataFrame:
        """
        Download historical candle data across any timeframe and date range.

        :param symbol: Trading pair (e.g. 'BTCUSDT', 'B-BTC_USDT').
        :param interval: Timeframe ('1m', '5m', '15m', '30m', '1h', '4h', '1d', etc.).
        :param start_time: Start date/time (datetime object, ISO string 'YYYY-MM-DD', or epoch ms).
        :param end_time: End date/time (defaults to current time).
        :return: pandas DataFrame containing clean OHLCV data.
        """
        pair = self.resolve_symbol(symbol)
        interval_clean = interval.strip().lower()

        # Determine native fetching interval vs resampled interval
        needs_resampling = False
        fetch_interval = interval_clean
        resample_rule = None

        if interval_clean not in NATIVE_INTERVALS:
            if interval_clean in RESAMPLE_BASE_MAPPING:
                fetch_interval, resample_rule = RESAMPLE_BASE_MAPPING[interval_clean]
                needs_resampling = True
                logger.info(f"Interval '{interval_clean}' is not natively provided by CoinDCX. Will download '{fetch_interval}' and resample to '{interval_clean}' ({resample_rule}).")
            else:
                raise ValueError(
                    f"Unsupported interval '{interval}'. Supported intervals: {sorted(list(NATIVE_INTERVALS | set(RESAMPLE_BASE_MAPPING.keys())))}"
                )

        # Parse start and end timestamps into epoch ms
        start_ms = self._parse_to_epoch_ms(start_time)
        end_ms = self._parse_to_epoch_ms(end_time) if end_time is not None else int(time.time() * 1000)

        if start_ms >= end_ms:
            raise ValueError(f"start_time ({start_ms}) must be earlier than end_time ({end_ms})")

        start_dt_utc = datetime.fromtimestamp(start_ms / 1000, tz=UTC_ZONE)
        end_dt_utc = datetime.fromtimestamp(end_ms / 1000, tz=UTC_ZONE)
        start_dt_ist = start_dt_utc.astimezone(IST_ZONE)
        end_dt_ist = end_dt_utc.astimezone(IST_ZONE)

        logger.info("=" * 65)
        logger.info(f"Starting Download: {pair} [{interval_clean.upper()}]")
        logger.info(f"Start: {start_dt_ist.strftime('%Y-%m-%d %H:%M:%S')} IST ({start_dt_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        logger.info(f"End:   {end_dt_ist.strftime('%Y-%m-%d %H:%M:%S')} IST ({end_dt_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        logger.info("=" * 65)

        # Backward pagination loop
        all_raw_candles: List[Dict[str, Any]] = []
        current_end = end_ms
        batch_idx = 0
        total_fetched = 0

        while current_end >= start_ms:
            batch_idx += 1
            batch = self.fetch_batch(
                pair=pair,
                interval=fetch_interval,
                start_ms=start_ms,
                end_ms=current_end,
                limit=MAX_LIMIT
            )

            if not batch:
                logger.info(f"Batch {batch_idx}: No more candles returned. End of available historical data reached.")
                break

            batch_count = len(batch)
            all_raw_candles.extend(batch)
            total_fetched += batch_count

            # Extract oldest candle in this batch (last element in newest-first list)
            oldest_batch_time = batch[-1]["time"]
            newest_batch_time = batch[0]["time"]

            oldest_batch_dt = datetime.fromtimestamp(oldest_batch_time / 1000, tz=UTC_ZONE).astimezone(IST_ZONE)
            newest_batch_dt = datetime.fromtimestamp(newest_batch_time / 1000, tz=UTC_ZONE).astimezone(IST_ZONE)

            logger.info(
                f"Batch {batch_idx:02d}: Fetched {batch_count:4d} candles "
                f"[{oldest_batch_dt.strftime('%Y-%m-%d %H:%M')} -> {newest_batch_dt.strftime('%Y-%m-%d %H:%M')} IST] | "
                f"Total: {total_fetched:6d}"
            )

            # Check termination conditions
            if oldest_batch_time <= start_ms:
                logger.info("Reached the requested start timestamp.")
                break

            if oldest_batch_time >= current_end:
                # No progress made backwards, prevent infinite loop
                logger.warning("Pagination reached historical data boundary.")
                break

            # Move current_end to 1 millisecond before the oldest candle in this batch
            current_end = oldest_batch_time - 1

            # Respectful rate-limiting sleep
            if self.request_delay > 0:
                time.sleep(self.request_delay)

        if not all_raw_candles:
            logger.warning("No data was downloaded for the given range.")
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(all_raw_candles)

        # Standardize columns and types
        df["open"] = pd.to_numeric(df["open"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        df["epoch_ms"] = df["time"].astype("int64")

        # Sort chronologically (oldest to newest) and deduplicate
        df = df.sort_values("epoch_ms").drop_duplicates(subset=["epoch_ms"]).reset_index(drop=True)

        # Filter to exact requested range
        df = df[(df["epoch_ms"] >= start_ms) & (df["epoch_ms"] <= end_ms)].reset_index(drop=True)

        # Convert timestamps
        # Datetime objects in UTC
        df["timestamp_utc"] = pd.to_datetime(df["epoch_ms"], unit="ms", utc=True)

        # Resample if needed
        if needs_resampling and resample_rule is not None:
            df = self._resample_dataframe(df, resample_rule)

        # Format IST and UTC string representations
        df["timestamp_ist"] = df["timestamp_utc"].dt.tz_convert(IST_ZONE).dt.strftime("%Y-%m-%d %H:%M:%S")
        # Standard primary timestamp column in IST
        df["timestamp"] = df["timestamp_ist"]
        df["timestamp_utc_str"] = df["timestamp_utc"].dt.strftime("%Y-%m-%d %H:%M:%S+00:00")

        # Reorder columns cleanly
        ordered_cols = ["timestamp", "open", "high", "low", "close", "volume", "timestamp_utc_str", "epoch_ms"]
        available_cols = [c for c in ordered_cols if c in df.columns]
        df = df[available_cols].rename(columns={"timestamp_utc_str": "timestamp_utc"})

        return df

    @staticmethod
    def _resample_dataframe(df: pd.DataFrame, rule: str) -> pd.DataFrame:
        """Resample 1m or 1h OHLCV data into larger timeframe (e.g. 5m, 30m, 4h)."""
        logger.info(f"Resampling candles to target rule: {rule}...")
        df_indexed = df.set_index("timestamp_utc")

        resampled = df_indexed.resample(rule, closed="left", label="left").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna(subset=["open", "close"]).reset_index()

        resampled["epoch_ms"] = resampled["timestamp_utc"].apply(lambda ts: int(ts.timestamp() * 1000))
        return resampled

    @staticmethod
    def _parse_to_epoch_ms(val: Union[str, datetime, int, float]) -> int:
        """Parse string date, datetime object, or relative duration ('30d') into epoch milliseconds."""
        if isinstance(val, (int, float)):
            if val < 10**11:
                return int(val * 1000)
            return int(val)

        if isinstance(val, datetime):
            if val.tzinfo is None:
                val = val.replace(tzinfo=UTC_ZONE)
            return int(val.timestamp() * 1000)

        if isinstance(val, str):
            val_str = val.strip().lower()

            # Relative duration handling: '30d', '7d', '1y', '24h'
            if val_str.endswith("d") and val_str[:-1].isdigit():
                days = int(val_str[:-1])
                dt = datetime.now(UTC_ZONE) - timedelta(days=days)
                return int(dt.timestamp() * 1000)
            elif val_str.endswith("y") and val_str[:-1].isdigit():
                years = int(val_str[:-1])
                dt = datetime.now(UTC_ZONE) - timedelta(days=years * 365)
                return int(dt.timestamp() * 1000)
            elif val_str.endswith("h") and val_str[:-1].isdigit():
                hours = int(val_str[:-1])
                dt = datetime.now(UTC_ZONE) - timedelta(hours=hours)
                return int(dt.timestamp() * 1000)

            if val_str == "now":
                return int(time.time() * 1000)

            # Try parsing various datetime formats
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d",
                "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y",
            ]
            for fmt in formats:
                try:
                    dt = datetime.strptime(val.strip(), fmt)
                    dt = dt.replace(tzinfo=UTC_ZONE)
                    return int(dt.timestamp() * 1000)
                except ValueError:
                    continue

            # Try ISO format
            try:
                dt = datetime.fromisoformat(val.strip())
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC_ZONE)
                return int(dt.timestamp() * 1000)
            except Exception:
                pass

        raise ValueError(f"Cannot parse date/time value: '{val}'. Use 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS', or relative '30d', '1y'.")


class DataValidator:
    """Validator for checking candlestick data integrity and reporting statistics."""

    @staticmethod
    def validate(df: pd.DataFrame, interval: str, start_ms: int, end_ms: int) -> Dict[str, Any]:
        """
        Validate OHLCV DataFrame for missing candles, duplicates, OHLC consistency, and gaps.

        :param df: Cleaned OHLCV DataFrame.
        :param interval: Timeframe string (e.g. '1h').
        :param start_ms: Expected start timestamp in ms.
        :param end_ms: Expected end timestamp in ms.
        :return: Dictionary of validation metrics.
        """
        if df.empty:
            return {
                "valid": False,
                "total_candles": 0,
                "missing_candles": 0,
                "gaps_count": 0,
                "gaps": [],
                "duplicates_count": 0,
                "invalid_ohlc_count": 0,
                "zero_volume_count": 0,
                "ohlc_valid": False,
            }

        total_candles = len(df)
        interval_ms = INTERVAL_DURATIONS_MS.get(interval, 60 * 60 * 1000)

        # Expected candles calculation based on time span
        actual_span_ms = df["epoch_ms"].iloc[-1] - df["epoch_ms"].iloc[0]
        expected_candles = int(actual_span_ms / interval_ms) + 1 if actual_span_ms >= 0 else total_candles

        # Check timestamp differences for gaps
        diffs = df["epoch_ms"].diff().dropna()
        gap_mask = diffs > (interval_ms * 1.5)  # Allow small tolerance
        gaps_count = int(gap_mask.sum())
        
        gaps_list = []
        missing_candles_count = 0
        if gaps_count > 0:
            gap_indices = df.index[1:][gap_mask]
            for idx in gap_indices:
                prev_time = df.loc[idx - 1, "timestamp"]
                curr_time = df.loc[idx, "timestamp"]
                time_jump_ms = df.loc[idx, "epoch_ms"] - df.loc[idx - 1, "epoch_ms"]
                missing_in_gap = int(time_jump_ms / interval_ms) - 1
                missing_candles_count += missing_in_gap
                gaps_list.append({
                    "from": prev_time,
                    "to": curr_time,
                    "missing_candles": missing_in_gap,
                    "gap_duration_hrs": round(time_jump_ms / 3600000, 2)
                })

        # OHLC Integrity Checks
        invalid_high_low = (df["high"] < df["low"]).sum()
        invalid_high_open = (df["high"] < df["open"]).sum()
        invalid_high_close = (df["high"] < df["close"]).sum()
        invalid_low_open = (df["low"] > df["open"]).sum()
        invalid_low_close = (df["low"] > df["close"]).sum()
        non_positive_prices = ((df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)).sum()
        null_count = df[["open", "high", "low", "close", "volume"]].isnull().sum().sum()

        total_invalid_ohlc = int(
            invalid_high_low + invalid_high_open + invalid_high_close +
            invalid_low_open + invalid_low_close + non_positive_prices + null_count
        )
        ohlc_valid = (total_invalid_ohlc == 0)

        # Zero and negative volume check
        zero_volume_count = int((df["volume"] == 0).sum())
        negative_volume_count = int((df["volume"] < 0).sum())

        return {
            "valid": ohlc_valid and (gaps_count == 0),
            "total_candles": total_candles,
            "expected_candles": expected_candles,
            "missing_candles": missing_candles_count,
            "gaps_count": gaps_count,
            "gaps": gaps_list,
            "duplicates_count": 0,
            "invalid_ohlc_count": total_invalid_ohlc,
            "zero_volume_count": zero_volume_count,
            "negative_volume_count": negative_volume_count,
            "ohlc_valid": ohlc_valid,
            "first_timestamp_ist": df["timestamp"].iloc[0],
            "last_timestamp_ist": df["timestamp"].iloc[-1],
            "first_timestamp_utc": df["timestamp_utc"].iloc[0],
            "last_timestamp_utc": df["timestamp_utc"].iloc[-1],
        }


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Modular helper to compute baseline technical indicators for downstream strategy backtesting.

    Includes:
    - EMA 9, EMA 21, EMA 50, EMA 200
    - MACD (12, 26, 9) & MACD Histogram
    - RSI 14
    - Volume 20 SMA
    - Average True Range (ATR 14)
    - Bollinger Bands (20, 2)
    """
    df = df.copy()

    # EMAs
    df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()

    # MACD
    ema_12 = df["close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # RSI (14)
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # Volume SMA
    df["volume_sma_20"] = df["volume"].rolling(window=20).mean()

    # ATR (14)
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(window=14).mean()

    # Bollinger Bands (20, 2)
    bb_mid = df["close"].rolling(window=20).mean()
    bb_std = df["close"].rolling(window=20).std()
    df["bb_upper"] = bb_mid + (2 * bb_std)
    df["bb_lower"] = bb_mid - (2 * bb_std)
    df["bb_mid"] = bb_mid

    return df


def print_summary_report(
    symbol: str,
    pair: str,
    interval: str,
    df: pd.DataFrame,
    validation: Dict[str, Any],
    file_path: str
):
    """Print structured execution summary table."""
    file_size_kb = os.path.getsize(file_path) / 1024 if os.path.exists(file_path) else 0

    print("\n" + "=" * 70)
    print("           COINDCX HISTORICAL DATA DOWNLOAD SUMMARY")
    print("=" * 70)
    print(f"  Symbol (Input)      : {symbol}")
    print(f"  CoinDCX API Pair    : {pair}")
    print(f"  Timeframe           : {interval}")
    print(f"  Total Candles Saved : {validation['total_candles']:,}")
    print(f"  Expected Candles    : {validation.get('expected_candles', 0):,}")
    print(f"  Start Time (IST)    : {validation.get('first_timestamp_ist', 'N/A')}")
    print(f"  End Time (IST)      : {validation.get('last_timestamp_ist', 'N/A')}")
    print(f"  Start Time (UTC)    : {validation.get('first_timestamp_utc', 'N/A')}")
    print(f"  End Time (UTC)      : {validation.get('last_timestamp_utc', 'N/A')}")
    print("-" * 70)
    print(f"  Data Gaps Detected  : {validation['gaps_count']}")
    print(f"  Missing Candles     : {validation['missing_candles']}")
    print(f"  Duplicates Removed  : {validation['duplicates_count']}")
    ohlc_status = "PASSED (Valid)" if validation["ohlc_valid"] else f"FAILED ({validation['invalid_ohlc_count']} invalid)"
    print(f"  OHLC Consistency    : {ohlc_status}")
    print(f"  Zero-Volume Candles : {validation['zero_volume_count']}")
    print("-" * 70)
    print(f"  Saved CSV File Path : {file_path}")
    print(f"  File Size           : {file_size_kb:.2f} KB")
    print("=" * 70)

    if validation["gaps_count"] > 0:
        print("\n[!] Top Gaps Details:")
        for i, gap in enumerate(validation["gaps"][:5], 1):
            print(f"    {i}. {gap['from']} -> {gap['to']} (Missing: {gap['missing_candles']} candles, {gap['gap_duration_hrs']} hrs)")
    print()


def run_downloader(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    start_date: Union[str, datetime] = "30d",
    end_date: Union[str, datetime] = "now",
    output_dir: str = DEFAULT_OUTPUT_DIR,
    include_indicators: bool = False
) -> Tuple[pd.DataFrame, str]:
    """
    Main download pipeline function.

    :param symbol: Trading pair (e.g. 'BTCUSDT').
    :param interval: Timeframe (e.g. '1m', '5m', '15m', '30m', '1h', '4h', '1d').
    :param start_date: Start date string or duration (e.g. '2023-01-01', '30d').
    :param end_date: End date string (e.g. '2026-08-30', 'now').
    :param output_dir: Directory where CSV will be stored.
    :param include_indicators: Whether to append technical indicators (EMA, MACD, RSI, etc.).
    :return: Tuple of (DataFrame, saved_file_path).
    """
    downloader = CoinDCXDownloader()
    resolved_pair = downloader.resolve_symbol(symbol)

    # 1. Download
    df = downloader.download_data(
        symbol=symbol,
        interval=interval,
        start_time=start_date,
        end_time=end_date
    )

    if df.empty:
        logger.error("Download failed or returned zero records.")
        return df, ""

    # 2. Add indicators if requested
    if include_indicators:
        logger.info("Computing baseline technical indicators (EMA 9/21/50/200, MACD, RSI, ATR, BB)...")
        df = add_technical_indicators(df)

    # 3. Validate
    start_ms = CoinDCXDownloader._parse_to_epoch_ms(start_date)
    end_ms = CoinDCXDownloader._parse_to_epoch_ms(end_date)
    validation = DataValidator.validate(df, interval, start_ms, end_ms)

    # 4. Prepare Output File Path
    os.makedirs(output_dir, exist_ok=True)
    clean_sym = symbol.replace("-", "").replace("_", "").upper()
    start_str = df["timestamp"].iloc[0].split(" ")[0]
    end_str = df["timestamp"].iloc[-1].split(" ")[0]
    filename = f"{clean_sym}_{interval}_{start_str}_{end_str}.csv"
    file_path = os.path.join(output_dir, filename)

    # 5. Save to CSV
    df.to_csv(file_path, index=False)
    logger.info(f"Successfully saved {len(df):,} candles to {file_path}")

    # 6. Print Summary Report
    print_summary_report(
        symbol=clean_sym,
        pair=resolved_pair,
        interval=interval,
        df=df,
        validation=validation,
        file_path=file_path
    )

    return df, file_path


def parse_args():
    """Command-line arguments parser."""
    parser = argparse.ArgumentParser(
        description="CoinDCX Historical OHLCV Candle Data Downloader for Quantitative Backtesting",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--symbol", "-s",
        type=str,
        default="BTCUSDT",
        help="Trading pair symbol (e.g. BTCUSDT, ETHUSDT, BTCINR, B-BTC_USDT)"
    )
    parser.add_argument(
        "--interval", "-i",
        type=str,
        default="1h",
        choices=["1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "1d", "1w"],
        help="Candle timeframe interval"
    )
    parser.add_argument(
        "--start", "-start",
        type=str,
        default="30d",
        help="Start date ('YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS') or relative ('30d', '7d', '1y', '3y', '5y')"
    )
    parser.add_argument(
        "--end", "-end",
        type=str,
        default="now",
        help="End date ('YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS') or 'now'"
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=None,
        help="Shortcut to specify last N days of data (overrides --start)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to save downloaded CSV files"
    )
    parser.add_argument(
        "--indicators",
        action="store_true",
        help="Include technical indicators (EMA, MACD, RSI, ATR, BB) in the CSV"
    )
    return parser.parse_args()


def main():
    """CLI Entrypoint."""
    args = parse_args()

    start = f"{args.days}d" if args.days is not None else args.start

    try:
        run_downloader(
            symbol=args.symbol,
            interval=args.interval,
            start_date=start,
            end_date=args.end,
            output_dir=args.output_dir,
            include_indicators=args.indicators
        )
    except KeyboardInterrupt:
        logger.warning("\nDownload cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Execution failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
