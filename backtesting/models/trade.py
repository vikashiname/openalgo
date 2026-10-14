"""
Trade Model & Trade Log Manager
-------------------------------
Contains standardized Trade dataclass and TradeLogManager.
"""

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

import pandas as pd


@dataclass
class Trade:
    """Standardized Trade Data Structure (Trade History Object)."""

    trade_id: int
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    entry_index: int
    exit_index: int
    entry_date: Any
    exit_date: Any
    entry_price: float
    exit_price: float
    quantity: float
    profit_loss: float
    profit_loss_pct: float
    holding_period: int  # Duration in bars/candles
    exit_reason: str
    type: str
    slippage: float = 0.0
    brokerage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if hasattr(self.entry_date, "strftime"):
            d["entry_date"] = self.entry_date.strftime("%Y-%m-%d")
        if hasattr(self.exit_date, "strftime"):
            d["exit_date"] = self.exit_date.strftime("%Y-%m-%d")
        return d


class TradeLogManager:
    """
    Phase 1: Trade Log Manager.
    Handles storing trade history, filtering, dataframe generation, and CSV export.
    """

    def __init__(self):
        self._trades: list[Trade] = []

    def add_trade(self, trade: Trade) -> None:
        self._trades.append(trade)

    @property
    def trades(self) -> list[Trade]:
        return self._trades

    def __len__(self) -> int:
        return len(self._trades)

    def to_dataframe(self) -> pd.DataFrame:
        if not self._trades:
            return pd.DataFrame()
        return pd.DataFrame([t.to_dict() for t in self._trades])

    def export_csv(self, filepath: str) -> str:
        df = self.to_dataframe()
        abs_path = os.path.abspath(filepath)
        df.to_csv(abs_path, index=False)
        return abs_path
