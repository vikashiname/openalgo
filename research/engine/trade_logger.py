"""
================================================================================
Trade Logger & Excursion Analytics (MAE / MFE)
================================================================================
Defines robust trade record schema and tracks Maximum Favorable Excursion (MFE)
and Maximum Adverse Excursion (MAE) across intra-bar price paths.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
import pandas as pd


@dataclass
class TradeRecord:
    trade_id: int
    symbol: str
    direction: str            # "LONG" or "SHORT"
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: Optional[pd.Timestamp]
    exit_price: Optional[float]
    contracts: int            # Discrete integer lots
    contract_multiplier: float
    gross_pnl: float
    brokerage_fees: float
    slippage_cost: float
    net_pnl: float
    return_pct: float
    holding_bars: int
    holding_days: int
    mfe_price: float          # Best price reached during holding
    mfe_dollars: float        # Max unrealized profit
    mfe_pct: float
    mae_price: float          # Worst price reached during holding
    mae_dollars: float        # Max unrealized drawdown
    mae_pct: float
    entry_reason: str
    exit_reason: str
    is_open: bool             # True if trade was still active at the final bar


class TradeLogger:
    def __init__(self):
        self.trades: List[TradeRecord] = []
        self._current_trade_id = 0

    def record_trade(self, trade: TradeRecord):
        self.trades.append(trade)

    def to_dataframe(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        records = [asdict(t) for t in self.trades]
        df = pd.DataFrame(records)
        return df

    def get_closed_trades(self) -> List[TradeRecord]:
        return [t for t in self.trades if not t.is_open]

    def get_open_trades(self) -> List[TradeRecord]:
        return [t for t in self.trades if t.is_open]
