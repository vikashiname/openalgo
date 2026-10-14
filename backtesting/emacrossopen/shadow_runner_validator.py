"""
Research Shadow Runner Validator (30-Day Forward Protocol)
File: backtesting/emacrossopen/shadow_runner_validator.py

RESEARCH / PAPER-SHADOW ONLY.
DO NOT MODIFY, DEPLOY, UPLOAD, OR RESTART ANY LIVE PRODUCTION SYSTEM.

Tracks parallel forward execution of:
  1. FROZEN PRODUCTION CONTROL:
     - LONG: Fixed +3.00% Target
     - SHORT: Fixed +1.50% Target
     - Catastrophe SL: -10.00%
     - Reversal: V2-2 Opposite Signal
  2. CANDIDATE SHADOW RUNNER:
     - LONG: +3.00% Target Reach -> 0.50% High-Watermark (HWM) Trail
     - SHORT: Fixed +1.50% Target (Retained)
     - Catastrophe SL: -10.00%
     - Reversal: V2-2 Opposite Signal
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

# Research workspace directories
RESEARCH_DIR = Path(__file__).resolve().parent
LOG_FILE_PATH = RESEARCH_DIR / "shadow_validation_log.csv"
SUMMARY_FILE_PATH = RESEARCH_DIR / "shadow_validation_summary.json"

PROD_LONG_TP = 3.00
PROD_SHORT_TP = 1.50
SHADOW_LONG_TRAIL_DIST = 0.50
CATASTROPHE_SL = 10.00
FRICTION_PCT = 0.07

IST = timezone(timedelta(hours=5, minutes=30))


class ShadowRunnerTracker:
    """
    Research-only state tracker recording causal performance metrics
    between the Production Baseline and the Candidate Shadow Runner.
    """

    def __init__(self):
        self.trades: List[Dict[str, Any]] = self._load_existing_log()

    def _load_existing_log(self) -> List[Dict[str, Any]]:
        if LOG_FILE_PATH.exists():
            try:
                df = pd.read_csv(LOG_FILE_PATH)
                return df.to_dict(orient="records")
            except Exception:
                return []
        return []

    def record_trade_completion(
        self,
        symbol: str,
        direction: str,  # 'LONG' or 'SHORT'
        entry_time: str,
        entry_price: float,
        exit_time: str,
        fixed_exit_price: float,
        fixed_exit_reason: str,
        shadow_exit_price: float,
        shadow_exit_reason: str,
        target_touched: bool,
        runner_activated: bool,
        peak_price_post_target: float,
        mfe_pct: float,
        mae_pct: float,
    ):
        """Records a finalized completed trade into the 30-day shadow validation log."""
        dir_mult = 1 if direction.upper() == "LONG" else -1

        # Fixed Control P&L
        fixed_raw_pnl = ((fixed_exit_price - entry_price) / entry_price) * 100.0 * dir_mult
        fixed_net_pnl = fixed_raw_pnl - FRICTION_PCT

        # Shadow Candidate P&L
        shadow_raw_pnl = ((shadow_exit_price - entry_price) / entry_price) * 100.0 * dir_mult
        shadow_net_pnl = shadow_raw_pnl - FRICTION_PCT

        # Incremental Alpha & Giveback
        incremental_pnl = (shadow_net_pnl - fixed_net_pnl) if target_touched else 0.0
        peak_profit_pct = ((peak_price_post_target - entry_price) / entry_price) * 100.0 * dir_mult if target_touched else 0.0
        giveback_pct = max(0.0, peak_profit_pct - shadow_raw_pnl) if runner_activated else 0.0

        trade_record = {
            "timestamp": datetime.now(IST).isoformat(),
            "symbol": symbol,
            "direction": direction.upper(),
            "entry_time": entry_time,
            "entry_price": round(entry_price, 2),
            "exit_time": exit_time,
            "fixed_exit_price": round(fixed_exit_price, 2),
            "fixed_exit_reason": fixed_exit_reason,
            "fixed_net_pnl_pct": round(fixed_net_pnl, 4),
            "shadow_exit_price": round(shadow_exit_price, 2),
            "shadow_exit_reason": shadow_exit_reason,
            "shadow_net_pnl_pct": round(shadow_net_pnl, 4),
            "target_touched": target_touched,
            "runner_activated": runner_activated,
            "peak_profit_pct": round(peak_profit_pct, 4),
            "giveback_pct": round(giveback_pct, 4),
            "incremental_pnl_pct": round(incremental_pnl, 4),
            "mfe_pct": round(mfe_pct, 4),
            "mae_pct": round(mae_pct, 4),
        }

        self.trades.append(trade_record)
        self._save_log()
        self._update_summary()

    def _save_log(self):
        df = pd.DataFrame(self.trades)
        df.to_csv(LOG_FILE_PATH, index=False)

    def _update_summary(self):
        if not self.trades:
            return

        df = pd.DataFrame(self.trades)

        def get_group_stats(sub_df: pd.DataFrame) -> Dict[str, Any]:
            if sub_df.empty:
                return {}
            n = len(sub_df)
            fixed_pnls = sub_df["fixed_net_pnl_pct"].values
            shadow_pnls = sub_df["shadow_net_pnl_pct"].values

            def stats(arr):
                wins = arr[arr > 0]
                losses = arr[arr < 0]
                wr = (len(wins) / len(arr)) * 100.0 if len(arr) else 0.0
                pf = float(np.sum(wins) / np.abs(np.sum(losses))) if len(losses) and np.sum(losses) != 0 else (99.0 if len(wins) else 0.0)
                tot = float(np.sum(arr))
                cum = np.cumsum(arr)
                peak = np.maximum.accumulate(cum)
                mdd = float(np.max(peak - cum)) if len(cum) else 0.0
                return {"win_rate_pct": round(wr, 2), "profit_factor": round(pf, 3), "net_return_pct": round(tot, 2), "max_drawdown_pct": round(mdd, 2)}

            targets = sub_df[sub_df["target_touched"] == True]
            runners = sub_df[sub_df["runner_activated"] == True]

            return {
                "total_trades": n,
                "target_touches": len(targets),
                "runner_activations": len(runners),
                "control_fixed": stats(fixed_pnls),
                "candidate_shadow": stats(shadow_pnls),
                "total_incremental_alpha_pct": round(float(sub_df["incremental_pnl_pct"].sum()), 2),
                "avg_giveback_pct": round(float(runners["giveback_pct"].mean()), 3) if len(runners) else 0.0,
                "avg_mfe_pct": round(float(sub_df["mfe_pct"].mean()), 3),
                "avg_mae_pct": round(float(sub_df["mae_pct"].mean()), 3),
            }

        summary = {
            "last_updated": datetime.now(IST).isoformat(),
            "protocol_days_active": 0,
            "overall": get_group_stats(df),
            "long_positions": get_group_stats(df[df["direction"] == "LONG"]),
            "short_positions": get_group_stats(df[df["direction"] == "SHORT"]),
        }

        with open(SUMMARY_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)


if __name__ == "__main__":
    tracker = ShadowRunnerTracker()
    print(f"✅ Research Shadow Runner Validator Initialized.")
    print(f"  • Log File: {LOG_FILE_PATH}")
    print(f"  • Summary File: {SUMMARY_FILE_PATH}")
    print(f"  • Tracked Trades: {len(tracker.trades)}")
