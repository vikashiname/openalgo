"""
Trade Performance Analytics Engine
----------------------------------
Calculates trade distribution, win rate, expectancy, risk-reward, and streaks.
"""

from dataclasses import dataclass

import numpy as np

from ..models.trade import TradeLogManager


@dataclass
class PerformanceMetrics:
    """Phase 2 Performance Metrics Container."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate: float = 0.0
    loss_rate: float = 0.0

    total_profit: float = 0.0
    total_profit_pct: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0

    avg_trade_pnl: float = 0.0
    avg_trade_pnl_pct: float = 0.0
    avg_win: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss: float = 0.0
    avg_loss_pct: float = 0.0

    largest_winner: float = 0.0
    largest_winner_pct: float = 0.0
    largest_loser: float = 0.0
    largest_loser_pct: float = 0.0

    risk_reward_ratio: float = 0.0
    expectancy: float = 0.0
    expectancy_pct: float = 0.0

    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0


class TradeAnalytics:
    """
    Phase 2: Modular Research-Grade Trade Analytics Engine.
    Decoupled analytics logic calculating Win Rate, Avg Win/Loss, Profit Factor,
    Expectancy, Risk-Reward, and Consecutive Win/Loss Streaks.
    """

    @staticmethod
    def calculate_metrics(trade_manager: TradeLogManager) -> PerformanceMetrics:
        trades = trade_manager.trades
        if not trades:
            return PerformanceMetrics()

        df = trade_manager.to_dataframe()
        total_trades = len(df)

        winners = df[df["profit_loss"] > 0]
        losers = df[df["profit_loss"] < 0]
        breakevens = df[df["profit_loss"] == 0]

        winning_trades = len(winners)
        losing_trades = len(losers)
        breakeven_trades = len(breakevens)

        win_rate = (winning_trades / total_trades) * 100.0 if total_trades > 0 else 0.0
        loss_rate = (losing_trades / total_trades) * 100.0 if total_trades > 0 else 0.0

        total_profit = float(df["profit_loss"].sum())
        # Institutional: Average trade return percentage instead of linear sum of percentages
        total_profit_pct = float(df["profit_loss_pct"].mean()) if total_trades > 0 else 0.0

        gross_profit = float(winners["profit_loss"].sum()) if not winners.empty else 0.0
        gross_loss = abs(float(losers["profit_loss"].sum())) if not losers.empty else 0.0
        profit_factor = (
            (gross_profit / gross_loss)
            if gross_loss > 0
            else (np.nan if gross_profit == 0 else np.inf)
        )

        avg_trade_pnl = total_profit / total_trades if total_trades > 0 else 0.0
        avg_trade_pnl_pct = total_profit_pct

        avg_win = float(winners["profit_loss"].mean()) if not winners.empty else 0.0
        avg_win_pct = float(winners["profit_loss_pct"].mean()) if not winners.empty else 0.0

        avg_loss = abs(float(losers["profit_loss"].mean())) if not losers.empty else 0.0
        avg_loss_pct = abs(float(losers["profit_loss_pct"].mean())) if not losers.empty else 0.0

        largest_winner = float(winners["profit_loss"].max()) if not winners.empty else 0.0
        largest_winner_pct = float(winners["profit_loss_pct"].max()) if not winners.empty else 0.0

        largest_loser = float(losers["profit_loss"].min()) if not losers.empty else 0.0
        largest_loser_pct = float(losers["profit_loss_pct"].min()) if not losers.empty else 0.0

        risk_reward_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0

        win_prob = winning_trades / total_trades if total_trades > 0 else 0.0
        loss_prob = losing_trades / total_trades if total_trades > 0 else 0.0
        expectancy = (win_prob * avg_win) - (loss_prob * avg_loss)
        expectancy_pct = (win_prob * avg_win_pct) - (loss_prob * avg_loss_pct)

        max_wins = 0
        max_losses = 0
        curr_wins = 0
        curr_losses = 0

        for pnl in df["profit_loss"]:
            if pnl > 0:
                curr_wins += 1
                curr_losses = 0
                if curr_wins > max_wins:
                    max_wins = curr_wins
            elif pnl < 0:
                curr_losses += 1
                curr_wins = 0
                if curr_losses > max_losses:
                    max_losses = curr_losses
            else:
                curr_wins = 0
                curr_losses = 0

        return PerformanceMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            breakeven_trades=breakeven_trades,
            win_rate=win_rate,
            loss_rate=loss_rate,
            total_profit=total_profit,
            total_profit_pct=total_profit_pct,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            avg_trade_pnl=avg_trade_pnl,
            avg_trade_pnl_pct=avg_trade_pnl_pct,
            avg_win=avg_win,
            avg_win_pct=avg_win_pct,
            avg_loss=avg_loss,
            avg_loss_pct=avg_loss_pct,
            largest_winner=largest_winner,
            largest_winner_pct=largest_winner_pct,
            largest_loser=largest_loser,
            largest_loser_pct=largest_loser_pct,
            risk_reward_ratio=risk_reward_ratio,
            expectancy=expectancy,
            expectancy_pct=expectancy_pct,
            max_consecutive_wins=max_wins,
            max_consecutive_losses=max_losses,
        )
