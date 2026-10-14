"""
Overfitting Gate & Quality Control for AutoResearch
File: backtesting/emacrossopen/autoresearch/overfitting_gate.py

Strict institutional-grade checks to reject curve-fitted flukes and data-mined artifacts.
"""

from typing import Any, Dict, Tuple


def evaluate_candidate(
    overall: Dict[str, Any],
    in_sample: Dict[str, Any],
    out_of_sample: Dict[str, Any],
    min_total_trades: int = 70,
    min_oos_trades: int = 25,
    min_oos_pf: float = 1.25,
    max_dd_limit: float = 35.0,
) -> Tuple[bool, str]:
    """
    Evaluates backtest metrics against strict quality gates.
    Returns: (is_accepted: bool, reason: str)
    """
    total_trades = overall.get("trade_count", 0)
    oos_trades = out_of_sample.get("trade_count", 0)
    oos_pf = out_of_sample.get("profit_factor", 0.0)
    is_pf = in_sample.get("profit_factor", 0.0)
    max_dd = overall.get("max_drawdown", 999.0)
    oos_ret = out_of_sample.get("total_return", -999.0)

    # Gate 1: Statistical Sample Size
    if total_trades < min_total_trades:
        return False, f"REJECT: Sample size too small (Total={total_trades} < {min_total_trades})"

    if oos_trades < min_oos_trades:
        return False, f"REJECT: OOS sample too small (OOS={oos_trades} < {min_oos_trades})"

    # Gate 2: Out-of-Sample Profitability
    if oos_ret <= 0 or oos_pf < min_oos_pf:
        return False, f"REJECT: OOS Profit Factor ({oos_pf:.3f}) below threshold ({min_oos_pf}) or OOS Return ({oos_ret:.1f}%) negative"

    # Gate 3: Overfitting Decay Ratio (OOS PF should not collapse relative to IS PF)
    if is_pf > 0:
        decay_ratio = oos_pf / is_pf
        if decay_ratio < 0.60:
            return False, f"REJECT: Severe OOS degradation (OOS/IS ratio = {decay_ratio:.2f} < 0.60)"

    # Gate 4: Maximum Drawdown Limit
    if max_dd > max_dd_limit:
        return False, f"REJECT: Drawdown excessive (MaxDD={max_dd:.1f}% > {max_dd_limit}%)"

    return True, f"ACCEPT: Robust OOS PF ({oos_pf:.3f}) & Controlled DD ({max_dd:.1f}%)"
