"""
Experiment Leaderboard & Registry for AutoResearch
File: backtesting/emacrossopen/autoresearch/leaderboard.py

Persists every autonomous trial into research_leaderboard.csv and tracks champions.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

LEADERBOARD_CSV = Path(__file__).resolve().parent.parent / "research_leaderboard.csv"

FIELDNAMES = [
    "run_id",
    "timestamp",
    "hypothesis_name",
    "timeframe",
    "direction_mode",
    "fast_ema",
    "slow_ema",
    "macd_params",
    "exit_type",
    "target_pct",
    "sl_pct",
    "is_trades",
    "is_pf",
    "is_win_rate",
    "is_return",
    "oos_trades",
    "oos_pf",
    "oos_win_rate",
    "oos_return",
    "overall_trades",
    "overall_pf",
    "overall_win_rate",
    "overall_return",
    "max_drawdown",
    "status",
    "notes",
]


class ExperimentLeaderboard:
    def __init__(self, csv_path: Path = LEADERBOARD_CSV):
        self.csv_path = csv_path
        self._ensure_file()

    def _ensure_file(self):
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(FIELDNAMES)

    def record_experiment(
        self,
        run_id: str,
        hypothesis_name: str,
        config: Dict[str, Any],
        overall: Dict[str, Any],
        in_sample: Dict[str, Any],
        out_of_sample: Dict[str, Any],
        status: str,
        notes: str = "",
    ):
        """Appends a new experiment row."""
        row = {
            "run_id": run_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "hypothesis_name": hypothesis_name,
            "timeframe": config.get("timeframe", "1h"),
            "direction_mode": config.get("direction_mode", "SYMMETRICAL"),
            "fast_ema": config.get("fast_ema", 9),
            "slow_ema": config.get("slow_ema", 26),
            "macd_params": f"{config.get('macd_fast', 12)}/{config.get('macd_slow', 26)}/{config.get('macd_sig', 9)}",
            "exit_type": config.get("exit_type", "REVERSAL"),
            "target_pct": f"{config.get('long_tp_pct', 3.0)}/{config.get('short_tp_pct', 1.5)}",
            "sl_pct": config.get("sl_pct", 6.0),
            "is_trades": in_sample.get("trade_count", 0),
            "is_pf": in_sample.get("profit_factor", 0.0),
            "is_win_rate": in_sample.get("win_rate", 0.0),
            "is_return": in_sample.get("total_return", 0.0),
            "oos_trades": out_of_sample.get("trade_count", 0),
            "oos_pf": out_of_sample.get("profit_factor", 0.0),
            "oos_win_rate": out_of_sample.get("win_rate", 0.0),
            "oos_return": out_of_sample.get("total_return", 0.0),
            "overall_trades": overall.get("trade_count", 0),
            "overall_pf": overall.get("profit_factor", 0.0),
            "overall_win_rate": overall.get("win_rate", 0.0),
            "overall_return": overall.get("total_return", 0.0),
            "max_drawdown": overall.get("max_drawdown", 0.0),
            "status": status,
            "notes": notes,
        }

        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writerow(row)

    def get_dataframe(self) -> pd.DataFrame:
        if not self.csv_path.exists():
            return pd.DataFrame(columns=FIELDNAMES)
        return pd.read_csv(self.csv_path)

    def get_top_champions(self, top_n: int = 5) -> pd.DataFrame:
        df = self.get_dataframe()
        if df.empty:
            return df
        # Filter accepted/champion and sort by OOS Profit Factor descending
        accepted = df[df["status"].isin(["ACCEPTED", "CHAMPION"])]
        if accepted.empty:
            accepted = df
        return accepted.sort_values("oos_pf", ascending=False).head(top_n)
