#!/usr/bin/env python3
"""
Test Suite: Futures-Level Risk Controls for Nifty Covered Call
Location: backtesting/nifty_covered_call/test_futures_risk_control.py

Tests the proposed dual-leg risk architecture:
  1. Normal Bullish Target Hit (Call Decay)
  2. Call Premium Stop-Loss (Rapid rally beyond 3.0x premium)
  3. Futures-Level Catastrophe Stop-Loss (-2.0% breach on spot)
  4. Max Strategy Drawdown Cap (-₹20,000 net loss cap)
  5. Roll Threshold at DTE <= 10
  6. Prevention of "Profit Target" false label on market crashes
"""

import unittest
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class Position:
    fut_symbol: str
    fut_entry_price: float
    fut_qty: int
    call_symbol: str
    call_entry_price: float
    call_qty: int
    target_price: float
    stoploss_price: float
    roll_dte: int


class MockCoveredCallRiskManager:
    def __init__(
        self,
        fut_stoploss_pct: float = 0.02,
        max_drawdown_inr: float = 20000.0,
        target_pct: float = 0.90,
        stoploss_mult: float = 3.0,
        roll_dte: int = 10,
    ):
        self.fut_stoploss_pct = fut_stoploss_pct
        self.max_drawdown_inr = max_drawdown_inr
        self.target_pct = target_pct
        self.stoploss_mult = stoploss_mult
        self.roll_dte = roll_dte
        self.last_exit_reason: Optional[str] = None
        self.is_closed = False

    def evaluate_risk(self, pos: Position, spot: float, curr_call_price: float, dte_left: int) -> bool:
        """
        Evaluates risk on both legs.
        Returns True if an exit is triggered, False otherwise.
        """
        fut_m2m = (spot - pos.fut_entry_price) * pos.fut_qty
        call_m2m = (pos.call_entry_price - curr_call_price) * pos.call_qty
        net_m2m = fut_m2m + call_m2m
        fut_return_pct = (spot - pos.fut_entry_price) / pos.fut_entry_price

        # Guard 1: Futures Catastrophe Stop-Loss (-2.0%)
        if fut_return_pct <= -self.fut_stoploss_pct:
            self.last_exit_reason = f"FUTURES_STOP_LOSS_HIT ({fut_return_pct*100:.2f}%)"
            self.is_closed = True
            return True

        # Guard 2: Absolute Strategy Net Drawdown Cap (-₹20,000)
        if net_m2m <= -self.max_drawdown_inr:
            self.last_exit_reason = f"MAX_NET_DRAWDOWN_BREACHED (₹{net_m2m:,.2f})"
            self.is_closed = True
            return True

        # Guard 3: Call Profit Target (90% decay)
        if curr_call_price <= pos.target_price:
            if net_m2m > 0:
                self.last_exit_reason = "PROFIT_TARGET_HIT (90% Decay)"
            else:
                self.last_exit_reason = "BEARISH_DECAY_CLOSE (Net Negative)"
            self.is_closed = True
            return True

        # Guard 4: Call Stop Loss (3.0x premium)
        if curr_call_price >= pos.stoploss_price:
            self.last_exit_reason = "CALL_STOP_LOSS_HIT (3.0x Premium)"
            self.is_closed = True
            return True

        # Guard 5: Roll Threshold
        if dte_left <= self.roll_dte:
            self.last_exit_reason = f"ROLL_THRESHOLD_REACHED (DTE <= {self.roll_dte})"
            self.is_closed = True
            return True

        return False


class TestCoveredCallRiskControl(unittest.TestCase):
    def setUp(self):
        self.rm = MockCoveredCallRiskManager(
            fut_stoploss_pct=0.02,       # 2% stoploss
            max_drawdown_inr=20000.0,   # ₹20,000 max drawdown cap
            target_pct=0.90,
            stoploss_mult=3.0,
            roll_dte=10
        )
        self.pos = Position(
            fut_symbol="NIFTY27OCT26FUT",
            fut_entry_price=22738.80,
            fut_qty=65,
            call_symbol="NIFTY27OCT2623100CE",
            call_entry_price=86.95,
            call_qty=65,
            target_price=8.69,
            stoploss_price=260.85,
            roll_dte=10
        )

    def test_01_normal_bullish_profit_target(self):
        """Spot remains steady/rises slightly, Call premium decays to target (<= 8.69)."""
        spot = 22800.00  # Up +61 pts
        call_price = 8.50  # Decayed
        dte = 18
        triggered = self.rm.evaluate_risk(self.pos, spot, call_price, dte)
        self.assertTrue(triggered)
        self.assertEqual(self.rm.last_exit_reason, "PROFIT_TARGET_HIT (90% Decay)")

    def test_02_rapid_rally_call_stoploss(self):
        """Spot surges up sharply, call price explodes >= 260.85."""
        spot = 23600.00
        call_price = 265.00
        dte = 20
        triggered = self.rm.evaluate_risk(self.pos, spot, call_price, dte)
        self.assertTrue(triggered)
        self.assertEqual(self.rm.last_exit_reason, "CALL_STOP_LOSS_HIT (3.0x Premium)")

    def test_03_futures_catastrophe_stoploss(self):
        """Spot drops -2.5% (-568 pts). Futures stoploss triggers before massive bleed."""
        spot = 22738.80 * (1.0 - 0.025)  # 22170.33
        call_price = 25.00  # Call decayed somewhat, but not 90%
        dte = 22
        triggered = self.rm.evaluate_risk(self.pos, spot, call_price, dte)
        self.assertTrue(triggered)
        self.assertIn("FUTURES_STOP_LOSS_HIT", self.rm.last_exit_reason)

    def test_04_max_net_drawdown_cap(self):
        """Spot drops so that net M2M breaches -₹20,000 before reaching -2% fut return."""
        # Suppose fut drops 350 pts (-₹22,750), call price is 70 (-₹1,101 net call gain = +₹1,101)
        # Net M2M = -22,750 + 1,101 = -21,649 <= -20,000
        spot = 22738.80 - 350.0
        call_price = 70.0
        dte = 24
        triggered = self.rm.evaluate_risk(self.pos, spot, call_price, dte)
        self.assertTrue(triggered)
        self.assertIn("MAX_NET_DRAWDOWN_BREACHED", self.rm.last_exit_reason)

    def test_05_roll_threshold_triggered(self):
        """DTE falls to 10 days while market is quiet."""
        spot = 22750.00
        call_price = 35.00
        dte = 10
        triggered = self.rm.evaluate_risk(self.pos, spot, call_price, dte)
        self.assertTrue(triggered)
        self.assertEqual(self.rm.last_exit_reason, "ROLL_THRESHOLD_REACHED (DTE <= 10)")

    def test_06_crash_decay_mislabel_prevention(self):
        """If spot dropped 400 pts and call decays to 8.0, do not label as profitable target hit."""
        # Spot drops 400 pts: fut_m2m = -26,000, call_m2m = +5,131 -> net_m2m = -20,868
        # Net drawdown cap triggers first
        spot = 22738.80 - 400.0
        call_price = 8.00
        dte = 15
        triggered = self.rm.evaluate_risk(self.pos, spot, call_price, dte)
        self.assertTrue(triggered)
        self.assertIn("MAX_NET_DRAWDOWN_BREACHED", self.rm.last_exit_reason)


if __name__ == "__main__":
    unittest.main()
