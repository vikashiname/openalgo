"""
Multi-Timeframe Resampler for Indian Market Structure
File: backtesting/emacrossopen/autoresearch/resampler.py

Handles resampling of 1-Hour NSE/NFO data into:
  - 75-Minute (5 equal bars/day)
  - 125-Minute (3 equal bars/day)
  - 4-Hour (2 bars/day)
  - Daily (1 consolidated session bar/day)
All output DatetimeIndexes are standardized to timezone-naive for seamless alignment.
"""

from pathlib import Path
from typing import Dict, Optional
import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _to_naive(df: pd.DataFrame) -> pd.DataFrame:
    """Standardizes index to timezone-naive datetime."""
    df = df.copy()
    if df.index.tz is not None:
        df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
    else:
        df.index = pd.to_datetime(df.index)
    return df


def resample_to_daily(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Consolidates 1-Hour candles into complete Daily session candles."""
    df = _to_naive(df_1h)
    df["session_date"] = df.index.date
    grouped = df.groupby("session_date")

    daily = grouped.agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })

    first_timestamps = grouped.apply(lambda g: g.index[0], include_groups=False)
    daily.index = pd.to_datetime(first_timestamps.values)
    daily = daily.sort_index()
    return daily


def resample_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resamples into 2 session bars (09:15-13:15, 13:15-15:30)."""
    df = _to_naive(df_1h)
    df["session_date"] = df.index.date
    df["bucket_4h"] = np.where(df.index.hour < 13, 0, 1)

    grouped = df.groupby(["session_date", "bucket_4h"])
    df_4h = grouped.agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })

    first_timestamps = grouped.apply(lambda g: g.index[0], include_groups=False)
    df_4h.index = pd.to_datetime(first_timestamps.values)
    df_4h = df_4h.sort_index()
    return df_4h


def resample_to_125m(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resamples 1H data into 3 harmonic session blocks (~125m each)."""
    df = _to_naive(df_1h)
    df["session_date"] = df.index.date
    conditions = [
        df.index.hour < 11,
        (df.index.hour >= 11) & (df.index.hour < 13),
        df.index.hour >= 13,
    ]
    df["bucket_125m"] = np.select(conditions, [0, 1, 2], default=2)

    grouped = df.groupby(["session_date", "bucket_125m"])
    df_125m = grouped.agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })

    first_timestamps = grouped.apply(lambda g: g.index[0], include_groups=False)
    df_125m.index = pd.to_datetime(first_timestamps.values)
    df_125m = df_125m.sort_index()
    return df_125m


def resample_to_75m(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Approximate 75-minute aggregation from 1H candles (5 bars/session)."""
    df = _to_naive(df_1h)
    df["session_date"] = df.index.date
    conditions = [
        df.index.hour <= 9,
        (df.index.hour >= 10) & (df.index.hour <= 11),
        df.index.hour == 12,
        df.index.hour == 13,
        df.index.hour >= 14,
    ]
    df["bucket_75m"] = np.select(conditions, [0, 1, 2, 3, 4], default=4)

    grouped = df.groupby(["session_date", "bucket_75m"])
    df_75m = grouped.agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })

    first_timestamps = grouped.apply(lambda g: g.index[0], include_groups=False)
    df_75m.index = pd.to_datetime(first_timestamps.values)
    df_75m = df_75m.sort_index()
    return df_75m


def load_resampled_dataset(
    timeframe: str = "1h", data_dir: Path = DATA_DIR
) -> Dict[str, pd.DataFrame]:
    """
    Loads all cached parquet files and resamples them into the desired timeframe.
    Ensures all outputs are timezone-naive.
    """
    files = sorted(list(data_dir.glob("*_1h.parquet")))
    resampled_map = {}

    for f in files:
        sym = f.stem.replace("_1h", "")
        raw_df = pd.read_parquet(f)
        if len(raw_df) < 50:
            continue

        tf = timeframe.lower()
        if tf == "1h":
            resampled_map[sym] = _to_naive(raw_df)
        elif tf == "75m":
            resampled_map[sym] = resample_to_75m(raw_df)
        elif tf == "125m":
            resampled_map[sym] = resample_to_125m(raw_df)
        elif tf == "4h":
            resampled_map[sym] = resample_to_4h(raw_df)
        elif tf in ["1d", "daily"]:
            resampled_map[sym] = resample_to_daily(raw_df)
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

    return resampled_map
