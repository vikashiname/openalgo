"""
================================================================================
Phase 8: Market Regime Analysis
================================================================================
Analyzes EMA crossover performance across discrete market regimes:
Bull, Bear, Sideways (Chop/Consolidation), High Volatility, and Low Volatility.
"""

from typing import Any, Dict
import numpy as np
import pandas as pd
from ..engine.backtest_engine import BacktestEngine
from ..engine.data_handler import ContractSpec
from ..strategies.ema_crossover import EMACrossoverStrategy


class MarketRegimeAnalyzer:
    def __init__(self, spec: ContractSpec, initial_capital: float = 100_000.0):
        self.spec = spec
        self.initial_capital = initial_capital

    @staticmethod
    def classify_regimes(df: pd.DataFrame) -> pd.DataFrame:
        """
        Classify each bar into Trend (Bull/Bear/Sideways) and Volatility (High/Low) regimes.
        """
        df = df.copy()
        close = df["close"]
        high = df["high"]
        low = df["low"]

        # Trend Indicators (50 & 100 SMAs + ADX approximation)
        sma50 = close.rolling(50).mean()
        sma100 = close.rolling(100).mean()

        # True Range & ATR(14)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()
        atr_pct = atr14 / close

        # Historical Volatility (20-day annualized std dev of returns)
        log_ret = np.log(close / close.shift(1))
        hist_vol = log_ret.rolling(20).std() * np.sqrt(252)

        # Directional Movement for ADX proxy
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).mean() / atr14)
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).mean() / atr14)
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 0.0001))
        adx14 = dx.rolling(14).mean()

        # Volatility thresholds
        vol_70th = hist_vol.quantile(0.70)
        vol_30th = hist_vol.quantile(0.30)

        trend_regime = []
        vol_regime = []

        for i in range(len(df)):
            c = close.iloc[i]
            s50 = sma50.iloc[i]
            s100 = sma100.iloc[i]
            adx = adx14.iloc[i]
            hv = hist_vol.iloc[i]

            # Trend Classification
            if np.isnan(s100) or np.isnan(adx):
                trend_regime.append("Warmup")
            elif adx < 20 or abs(s50 - s100) / s100 < 0.015:
                trend_regime.append("Sideways / Chop")
            elif c > s100 and s50 > s100:
                trend_regime.append("Bull Trend")
            elif c < s100 and s50 < s100:
                trend_regime.append("Bear Trend")
            else:
                trend_regime.append("Transitional")

            # Volatility Classification
            if np.isnan(hv):
                vol_regime.append("Warmup")
            elif hv >= vol_70th:
                vol_regime.append("High Volatility")
            elif hv <= vol_30th:
                vol_regime.append("Low Volatility")
            else:
                vol_regime.append("Medium Volatility")

        df["trend_regime"] = trend_regime
        df["vol_regime"] = vol_regime
        return df

    def analyze_strategy_by_regime(
        self,
        df: pd.DataFrame,
        fast_period: int = 9,
        slow_period: int = 21
    ) -> Dict[str, Any]:
        """
        Runs strategy backtest and evaluates trade outcomes across each market regime.
        """
        df_regimes = self.classify_regimes(df)
        strat = EMACrossoverStrategy(fast_period=fast_period, slow_period=slow_period)
        engine = BacktestEngine(self.spec, self.initial_capital, execution_timing="next_open")
        res = engine.run(df_regimes, strat.generate_signals)

        trades = res["trade_logger"].get_closed_trades()
        if not trades:
            return {"overall_metrics": res["metrics"], "regime_breakdown": pd.DataFrame()}

        # Tag each trade with the regime at entry time
        trades_enriched = []
        for t in trades:
            entry_dt = t.entry_time
            if entry_dt in df_regimes.index:
                t_regime = df_regimes.loc[entry_dt, "trend_regime"]
                v_regime = df_regimes.loc[entry_dt, "vol_regime"]
            else:
                t_regime = "Unknown"
                v_regime = "Unknown"

            trades_enriched.append({
                "trade_id": t.trade_id,
                "net_pnl": t.net_pnl,
                "return_pct": t.return_pct,
                "trend_regime": t_regime,
                "vol_regime": v_regime,
                "holding_days": t.holding_days,
            })

        tdf = pd.DataFrame(trades_enriched)
        
        # Group by Trend Regime
        trend_summary = []
        for reg, grp in tdf.groupby("trend_regime"):
            wins = grp[grp["net_pnl"] > 0]
            losses = grp[grp["net_pnl"] <= 0]
            gross_w = wins["net_pnl"].sum()
            gross_l = abs(losses["net_pnl"].sum())
            pf = (gross_w / gross_l) if gross_l > 0 else (99.0 if gross_w > 0 else 0.0)
            trend_summary.append({
                "regime_type": "Trend Regime",
                "regime": reg,
                "trades": len(grp),
                "win_rate_pct": (len(wins) / len(grp) * 100.0) if len(grp) > 0 else 0.0,
                "total_pnl": grp["net_pnl"].sum(),
                "avg_return_pct": grp["return_pct"].mean(),
                "profit_factor": pf,
            })

        # Group by Volatility Regime
        vol_summary = []
        for reg, grp in tdf.groupby("vol_regime"):
            wins = grp[grp["net_pnl"] > 0]
            losses = grp[grp["net_pnl"] <= 0]
            gross_w = wins["net_pnl"].sum()
            gross_l = abs(losses["net_pnl"].sum())
            pf = (gross_w / gross_l) if gross_l > 0 else (99.0 if gross_w > 0 else 0.0)
            vol_summary.append({
                "regime_type": "Volatility Regime",
                "regime": reg,
                "trades": len(grp),
                "win_rate_pct": (len(wins) / len(grp) * 100.0) if len(grp) > 0 else 0.0,
                "total_pnl": grp["net_pnl"].sum(),
                "avg_return_pct": grp["return_pct"].mean(),
                "profit_factor": pf,
            })

        regime_df = pd.DataFrame(trend_summary + vol_summary)
        return {
            "overall_metrics": res["metrics"],
            "regime_breakdown": regime_df,
            "df_regimes": df_regimes,
        }
