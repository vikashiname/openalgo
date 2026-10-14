"""
================================================================================
Zero-Lookahead Institutional Backtest Engine
================================================================================
Simulates strategy execution with strict chronological sequencing, configurable
slippage, discrete integer contract lots, realistic margin accounting, and
intra-bar MAE/MFE excursion tracking.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from .data_handler import ContractSpec
from .metrics import MetricsEngine
from .trade_logger import TradeLogger, TradeRecord


class BacktestEngine:
    def __init__(
        self,
        spec: ContractSpec,
        initial_capital: float = 100_000.0,
        execution_timing: str = "next_open",  # "next_open" (Realistic) or "same_close" (Flawed baseline)
        slippage_ticks: int = 1,
        allocation_pct: float = 0.50,         # Deploy up to 50% capital into required margin
        max_contracts: Optional[int] = None,
        risk_free_rate: float = 0.045
    ):
        self.spec = spec
        self.initial_capital = initial_capital
        self.execution_timing = execution_timing
        self.slippage_ticks = slippage_ticks
        self.allocation_pct = allocation_pct
        self.max_contracts = max_contracts
        self.risk_free_rate = risk_free_rate

    def run(
        self,
        df: pd.DataFrame,
        signal_generator: Callable[[pd.DataFrame], Tuple[pd.Series, pd.Series]]
    ) -> Dict[str, Any]:
        """
        Execute backtest simulation on cleaned OHLCV DataFrame.
        signal_generator: Function returning (buy_signals: pd.Series, sell_signals: pd.Series)
        """
        if len(df) < 5:
            raise ValueError("Insufficient historical bars for backtesting.")

        # Compute raw boolean signals
        buy_signals, sell_signals = signal_generator(df)

        trade_logger = TradeLogger()
        n = len(df)

        cash = self.initial_capital
        position_contracts = 0
        entry_price = 0.0
        entry_time: Optional[pd.Timestamp] = None
        entry_idx = 0

        # Excursion tracking during position holding
        mfe_price = 0.0
        mae_price = 0.0

        equity_curve = pd.Series(index=df.index, dtype=float)
        cash_curve = pd.Series(index=df.index, dtype=float)

        trade_counter = 0
        slippage_per_unit = self.slippage_ticks * self.spec.tick_size

        for i in range(n):
            current_bar = df.iloc[i]
            bar_date = df.index[i]
            open_p = float(current_bar["open"])
            high_p = float(current_bar["high"])
            low_p = float(current_bar["low"])
            close_p = float(current_bar["close"])

            # ------------------------------------------------------------------
            # 1. EXECUTION PHASE (Orders triggered by previous bar's confirmed signal)
            # ------------------------------------------------------------------
            if self.execution_timing == "next_open":
                if i > 0:
                    prev_buy = bool(buy_signals.iloc[i - 1])
                    prev_sell = bool(sell_signals.iloc[i - 1])

                    # Exit Signal Execution
                    if prev_sell and position_contracts > 0:
                        exec_price = open_p - slippage_per_unit
                        point_diff = exec_price - entry_price
                        gross_pnl = point_diff * self.spec.multiplier * position_contracts
                        
                        fee = (self.spec.fixed_fee_per_contract * position_contracts)
                        slippage_dollars = (slippage_per_unit * self.spec.multiplier * position_contracts)
                        net_pnl = gross_pnl - fee
                        return_pct = (point_diff / entry_price) * 100.0 if entry_price > 0 else 0.0

                        cash += gross_pnl - fee
                        holding_bars = i - entry_idx
                        holding_days = (bar_date - entry_time).days

                        # MAE / MFE Dollar calculations
                        mfe_dollars = (mfe_price - entry_price) * self.spec.multiplier * position_contracts
                        mae_dollars = (entry_price - mae_price) * self.spec.multiplier * position_contracts

                        trade_counter += 1
                        trade_logger.record_trade(TradeRecord(
                            trade_id=trade_counter,
                            symbol=self.spec.symbol,
                            direction="LONG",
                            entry_time=entry_time,
                            entry_price=entry_price,
                            exit_time=bar_date,
                            exit_price=exec_price,
                            contracts=position_contracts,
                            contract_multiplier=self.spec.multiplier,
                            gross_pnl=gross_pnl,
                            brokerage_fees=fee * 2,  # Round trip
                            slippage_cost=slippage_dollars * 2,
                            net_pnl=net_pnl - fee,  # Deduct entry fee as well
                            return_pct=return_pct,
                            holding_bars=holding_bars,
                            holding_days=holding_days,
                            mfe_price=mfe_price,
                            mfe_dollars=max(0.0, mfe_dollars),
                            mfe_pct=(mfe_price - entry_price) / entry_price * 100.0,
                            mae_price=mae_price,
                            mae_dollars=max(0.0, mae_dollars),
                            mae_pct=(entry_price - mae_price) / entry_price * 100.0,
                            entry_reason="EMA Crossover Bullish",
                            exit_reason="EMA Crossover Bearish",
                            is_open=False,
                        ))

                        position_contracts = 0
                        entry_price = 0.0
                        entry_time = None

                    # Entry Signal Execution
                    elif prev_buy and position_contracts == 0:
                        exec_price = open_p + slippage_per_unit
                        
                        # Futures discrete lot calculation based on margin requirement
                        contract_val = exec_price * self.spec.multiplier
                        margin_per_contract = contract_val * self.spec.margin_pct
                        
                        deployable_capital = cash * self.allocation_pct
                        max_lots = int(deployable_capital // margin_per_contract) if margin_per_contract > 0 else 0
                        
                        if self.max_contracts:
                            max_lots = min(max_lots, self.max_contracts)
                        
                        # Minimum 1 contract if affordable
                        if max_lots < 1 and cash >= margin_per_contract:
                            max_lots = 1

                        if max_lots >= 1:
                            position_contracts = max_lots
                            entry_price = exec_price
                            entry_time = bar_date
                            entry_idx = i

                            fee = self.spec.fixed_fee_per_contract * position_contracts
                            cash -= fee
                            mfe_price = high_p
                            mae_price = low_p

            elif self.execution_timing == "same_close":
                # Legacy / Flawed same-bar close execution for audit comparison
                curr_buy = bool(buy_signals.iloc[i])
                curr_sell = bool(sell_signals.iloc[i])

                if curr_sell and position_contracts > 0:
                    exec_price = close_p
                    gross_pnl = (exec_price - entry_price) * self.spec.multiplier * position_contracts
                    fee = self.spec.fixed_fee_per_contract * position_contracts
                    net_pnl = gross_pnl - fee
                    cash += gross_pnl - fee

                    trade_counter += 1
                    trade_logger.record_trade(TradeRecord(
                        trade_id=trade_counter,
                        symbol=self.spec.symbol,
                        direction="LONG",
                        entry_time=entry_time,
                        entry_price=entry_price,
                        exit_time=bar_date,
                        exit_price=exec_price,
                        contracts=position_contracts,
                        contract_multiplier=self.spec.multiplier,
                        gross_pnl=gross_pnl,
                        brokerage_fees=fee * 2,
                        slippage_cost=0.0,
                        net_pnl=net_pnl - fee,
                        return_pct=(exec_price - entry_price) / entry_price * 100.0,
                        holding_bars=i - entry_idx,
                        holding_days=(bar_date - entry_time).days,
                        mfe_price=close_p,
                        mfe_dollars=max(0.0, gross_pnl),
                        mfe_pct=max(0.0, (exec_price - entry_price) / entry_price * 100.0),
                        mae_price=close_p,
                        mae_dollars=max(0.0, -gross_pnl),
                        mae_pct=max(0.0, (entry_price - exec_price) / entry_price * 100.0),
                        entry_reason="EMA Crossover Bullish (Same Close)",
                        exit_reason="EMA Crossover Bearish (Same Close)",
                        is_open=False,
                    ))
                    position_contracts = 0

                elif curr_buy and position_contracts == 0:
                    exec_price = close_p
                    contract_val = exec_price * self.spec.multiplier
                    margin_per_contract = contract_val * self.spec.margin_pct
                    max_lots = max(1, int((cash * self.allocation_pct) // margin_per_contract)) if margin_per_contract > 0 else 1
                    
                    position_contracts = max_lots
                    entry_price = exec_price
                    entry_time = bar_date
                    entry_idx = i
                    cash -= (self.spec.fixed_fee_per_contract * position_contracts)

            # ------------------------------------------------------------------
            # 2. INTRA-BAR MFE / MAE EXCURSION UPDATES
            # ------------------------------------------------------------------
            if position_contracts > 0:
                if high_p > mfe_price:
                    mfe_price = high_p
                if low_p < mae_price:
                    mae_price = low_p

            # ------------------------------------------------------------------
            # 3. MARK-TO-MARKET TOTAL EQUITY EVALUATION
            # ------------------------------------------------------------------
            if position_contracts > 0:
                unrealized_pnl = (close_p - entry_price) * self.spec.multiplier * position_contracts
                total_equity = cash + unrealized_pnl
            else:
                total_equity = cash

            equity_curve.iloc[i] = total_equity
            cash_curve.iloc[i] = cash

        # ----------------------------------------------------------------------
        # 4. TERMINAL OPEN POSITION SETTLEMENT
        # ----------------------------------------------------------------------
        if position_contracts > 0:
            final_price = float(df["close"].iloc[-1])
            final_date = df.index[-1]
            unrealized_pnl = (final_price - entry_price) * self.spec.multiplier * position_contracts
            fee = self.spec.fixed_fee_per_contract * position_contracts

            trade_counter += 1
            trade_logger.record_trade(TradeRecord(
                trade_id=trade_counter,
                symbol=self.spec.symbol,
                direction="LONG",
                entry_time=entry_time,
                entry_price=entry_price,
                exit_time=final_date,
                exit_price=final_price,
                contracts=position_contracts,
                contract_multiplier=self.spec.multiplier,
                gross_pnl=unrealized_pnl,
                brokerage_fees=fee,
                slippage_cost=0.0,
                net_pnl=unrealized_pnl - fee,
                return_pct=(final_price - entry_price) / entry_price * 100.0,
                holding_bars=n - 1 - entry_idx,
                holding_days=(final_date - entry_time).days,
                mfe_price=mfe_price,
                mfe_dollars=max(0.0, (mfe_price - entry_price) * self.spec.multiplier * position_contracts),
                mfe_pct=max(0.0, (mfe_price - entry_price) / entry_price * 100.0),
                mae_price=mae_price,
                mae_dollars=max(0.0, (entry_price - mae_price) * self.spec.multiplier * position_contracts),
                mae_pct=max(0.0, (entry_price - mae_price) / entry_price * 100.0),
                entry_reason="EMA Crossover Bullish",
                exit_reason="Backtest End (Open Position MTM)",
                is_open=True,
            ))

        # Compute full performance & risk analytics
        metrics = MetricsEngine.calculate_metrics(
            equity_series=equity_curve,
            trades=trade_logger.trades,
            initial_capital=self.initial_capital,
            risk_free_rate=self.risk_free_rate,
            benchmark_series=df["close"]
        )

        return {
            "metrics": metrics,
            "equity_curve": equity_curve,
            "cash_curve": cash_curve,
            "trade_logger": trade_logger,
            "trades_df": trade_logger.to_dataframe(),
        }
