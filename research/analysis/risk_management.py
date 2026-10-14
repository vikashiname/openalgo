"""
================================================================================
Phase 10: Modular Risk Management Research
================================================================================
Tests Fixed Stop Loss, ATR Volatility Stops, Trailing Stops, and Take Profit
targets independently against the baseline crossover logic.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import ContractSpec
from ..engine.metrics import MetricsEngine
from ..engine.trade_logger import TradeLogger, TradeRecord
from ..strategies.ema_crossover import EMACrossoverStrategy


class RiskManagementAnalyzer:
    def __init__(self, spec: ContractSpec, initial_capital: float = 100_000.0):
        self.spec = spec
        self.initial_capital = initial_capital

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        high, low, close = df["high"], df["low"], df["close"]
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def test_risk_variations(
        self,
        df: pd.DataFrame,
        fast_period: int = 9,
        slow_period: int = 21
    ) -> pd.DataFrame:
        """
        Evaluate multiple risk management overlays:
          1. Baseline (Pure EMA Opposite Cross Exit)
          2. Fixed Stop Loss (2.0%)
          3. Fixed Stop Loss (3.0%)
          4. ATR Stop Loss (1.5x ATR)
          5. ATR Stop Loss (2.5x ATR)
          6. Trailing Stop (2.0x ATR)
          7. Profit Target (1:2.5 Risk/Reward)
        """
        df = df.copy()
        df["atr"] = self.calculate_atr(df, period=14)
        strat = EMACrossoverStrategy(fast_period=fast_period, slow_period=slow_period)
        buy_signals, sell_signals = strat.generate_signals(df)

        risk_configs = [
            {"name": "1. Baseline (Opposite Cross)", "sl_type": "none", "sl_val": 0.0, "trail": False, "tp_mult": 0.0},
            {"name": "2. Fixed SL (2.0%)", "sl_type": "fixed", "sl_val": 0.02, "trail": False, "tp_mult": 0.0},
            {"name": "3. Fixed SL (3.5%)", "sl_type": "fixed", "sl_val": 0.035, "trail": False, "tp_mult": 0.0},
            {"name": "4. ATR Stop (1.5x ATR)", "sl_type": "atr", "sl_val": 1.5, "trail": False, "tp_mult": 0.0},
            {"name": "5. ATR Stop (2.5x ATR)", "sl_type": "atr", "sl_val": 2.5, "trail": False, "tp_mult": 0.0},
            {"name": "6. Trailing Stop (2.0x ATR)", "sl_type": "atr", "sl_val": 2.0, "trail": True, "tp_mult": 0.0},
            {"name": "7. ATR SL + 1:2.5 TP Target", "sl_type": "atr", "sl_val": 2.0, "trail": False, "tp_mult": 2.5},
        ]

        summary = []
        n = len(df)

        for cfg in risk_configs:
            trade_logger = TradeLogger()
            cash = self.initial_capital
            pos = 0
            entry_p = 0.0
            entry_t = None
            entry_idx = 0
            sl_price = 0.0
            tp_price = 0.0
            highest_since_entry = 0.0

            eq_curve = pd.Series(index=df.index, dtype=float)
            trade_id = 0

            for i in range(n):
                c_bar = df.iloc[i]
                b_date = df.index[i]
                op, hp, lp, cp = float(c_bar["open"]), float(c_bar["high"]), float(c_bar["low"]), float(c_bar["close"])
                atr_val = float(c_bar["atr"]) if not np.isnan(c_bar["atr"]) else (cp * 0.02)

                # Order Execution (next open after signal)
                if i > 0:
                    prev_buy = bool(buy_signals.iloc[i - 1])
                    prev_sell = bool(sell_signals.iloc[i - 1])

                    # Check SL / TP trigger during bar
                    sl_hit = False
                    tp_hit = False
                    exit_price = op

                    if pos > 0:
                        # Trailing stop update
                        if cfg["trail"]:
                            if hp > highest_since_entry:
                                highest_since_entry = hp
                                sl_price = highest_since_entry - (cfg["sl_val"] * atr_val)

                        if cfg["sl_type"] != "none" and lp <= sl_price:
                            sl_hit = True
                            exit_price = min(op, sl_price)  # Gap protection
                        elif cfg["tp_mult"] > 0 and hp >= tp_price:
                            tp_hit = True
                            exit_price = max(op, tp_price)
                        elif prev_sell:
                            exit_price = op

                    # Process Exit
                    if pos > 0 and (prev_sell or sl_hit or tp_hit):
                        pnl = (exit_price - entry_p) * self.spec.multiplier * pos
                        fee = self.spec.fixed_fee_per_contract * pos * 2
                        net = pnl - fee
                        cash += pnl - (fee / 2)

                        reason = "Stop Loss" if sl_hit else ("Take Profit" if tp_hit else "EMA Cross")
                        trade_id += 1
                        trade_logger.record_trade(TradeRecord(
                            trade_id=trade_id,
                            symbol=self.spec.symbol,
                            direction="LONG",
                            entry_time=entry_t,
                            entry_price=entry_p,
                            exit_time=b_date,
                            exit_price=exit_price,
                            contracts=pos,
                            contract_multiplier=self.spec.multiplier,
                            gross_pnl=pnl,
                            brokerage_fees=fee,
                            slippage_cost=0.0,
                            net_pnl=net,
                            return_pct=(exit_price - entry_p) / entry_p * 100.0,
                            holding_bars=i - entry_idx,
                            holding_days=(b_date - entry_t).days,
                            mfe_price=hp,
                            mfe_dollars=max(0.0, pnl),
                            mfe_pct=max(0.0, (exit_price - entry_p) / entry_p * 100.0),
                            mae_price=lp,
                            mae_dollars=max(0.0, -pnl),
                            mae_pct=max(0.0, (entry_p - exit_price) / entry_p * 100.0),
                            entry_reason="EMA Bullish Cross",
                            exit_reason=reason,
                            is_open=False,
                        ))
                        pos = 0

                    # Process Entry
                    elif pos == 0 and prev_buy:
                        contract_val = op * self.spec.multiplier
                        margin = contract_val * self.spec.margin_pct
                        lots = max(1, int((cash * 0.50) // margin)) if margin > 0 else 1

                        pos = lots
                        entry_p = op
                        entry_t = b_date
                        entry_idx = i
                        highest_since_entry = op
                        cash -= (self.spec.fixed_fee_per_contract * pos)

                        # Set SL / TP
                        if cfg["sl_type"] == "fixed":
                            sl_price = entry_p * (1.0 - cfg["sl_val"])
                        elif cfg["sl_type"] == "atr":
                            sl_price = entry_p - (cfg["sl_val"] * atr_val)
                        
                        if cfg["tp_mult"] > 0:
                            risk_dist = entry_p - sl_price
                            tp_price = entry_p + (risk_dist * cfg["tp_mult"])

                # Mark to market
                unrealized = (cp - entry_p) * self.spec.multiplier * pos if pos > 0 else 0.0
                eq_curve.iloc[i] = cash + unrealized

            m = MetricsEngine.calculate_metrics(
                equity_series=eq_curve,
                trades=trade_logger.trades,
                initial_capital=self.initial_capital,
                benchmark_series=df["close"]
            )
            summary.append({
                "overlay": cfg["name"],
                "total_return_pct": m["total_return_pct"],
                "cagr_pct": m["cagr_pct"],
                "max_drawdown_pct": m["max_drawdown_pct"],
                "sharpe_ratio": m["sharpe_ratio"],
                "profit_factor": m["profit_factor"],
                "win_rate_pct": m["win_rate_pct"],
                "trades_count": m["total_trades"],
                "expectancy_dollars": m["expectancy_dollars"],
            })

        return pd.DataFrame(summary)
