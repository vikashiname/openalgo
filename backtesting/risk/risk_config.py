"""
Risk Management & Multi-Stage Exit Configurations
--------------------------------------------------
Configuration object for Stop Loss, Target Profit, Trailing Stop, Break-Even, and Time Exits.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RiskManagementConfig:
    """Phase 5 Advanced Risk Management Rules & Multi-Stage Exits."""

    use_breakeven_stop: bool = True
    breakeven_profit_trigger_pct: float = 1.5  # Move SL to entry price once profit reaches 1.5%
    max_holding_bars: int | None = 40  # Time Exit after N bars
    partial_exit_pct: float = 0.0  # Partial exit percentage
