"""
Position Sizing Models
----------------------
Contains abstract PositionSizer base class and concrete sizing strategies.
"""

import abc


class PositionSizer(abc.ABC):
    """Abstract Base Class for Position Sizing Models."""

    @abc.abstractmethod
    def calculate_quantity(self, price: float, portfolio_equity: float, atr: float = 0.0) -> float:
        pass


class FixedQuantitySizer(PositionSizer):
    """Fixed Quantity Position Sizer (e.g. 1 share/contract)."""

    def __init__(self, qty: float = 1.0):
        self.qty = qty

    def calculate_quantity(self, price: float, portfolio_equity: float, atr: float = 0.0) -> float:
        return self.qty


class FixedCapitalSizer(PositionSizer):
    """Fixed Capital Allocation Sizer (e.g. ₹50,000 per trade)."""

    def __init__(self, capital_per_trade: float = 50000.0):
        self.capital_per_trade = capital_per_trade

    def calculate_quantity(self, price: float, portfolio_equity: float, atr: float = 0.0) -> float:
        return max(self.capital_per_trade / price, 1.0) if price > 0 else 1.0


class PercentEquitySizer(PositionSizer):
    """Percent Equity Position Sizer (e.g. Allocate 20% of Portfolio Equity)."""

    def __init__(self, equity_pct: float = 20.0):
        self.equity_pct = equity_pct

    def calculate_quantity(self, price: float, portfolio_equity: float, atr: float = 0.0) -> float:
        target_cap = portfolio_equity * (self.equity_pct / 100.0)
        return max(target_cap / price, 1.0) if price > 0 else 1.0


class ATRSizer(PositionSizer):
    """ATR Volatility Position Sizer (Risking fixed % of capital divided by ATR risk)."""

    def __init__(self, risk_pct: float = 1.0, atr_multiplier: float = 1.5):
        self.risk_pct = risk_pct
        self.atr_multiplier = atr_multiplier

    def calculate_quantity(self, price: float, portfolio_equity: float, atr: float = 0.0) -> float:
        if atr <= 0 or price <= 0:
            return 1.0
        risk_amount = portfolio_equity * (self.risk_pct / 100.0)
        risk_per_share = atr * self.atr_multiplier
        return max(risk_amount / risk_per_share, 1.0)
