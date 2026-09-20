"""
Strategy Attribution and Normalization Utility.

Provides centralized normalization of strategy identifiers to canonical authoritative names:
  - "Macdfno"
  - "Emacrossopen"

Guarantees that variants, legacy names (e.g., MACD_FNO_V1, EMACROSS_FNO_PAPER),
and unwanted non-strategy tags (e.g., UI Exit Position, Manual / Unattributed)
are correctly normalized and never pollute strategy overview or attribution books.
"""

from datetime import datetime
from typing import Any, Optional

AUTHORITATIVE_STRATEGIES = ["Macdfno", "Emacrossopen"]

# Map of lower-cased / cleaned variant strings to canonical names
_CANONICAL_MAP = {
    # Macdfno variants
    "macdfno": "Macdfno",
    "macd_fno_v1": "Macdfno",
    "macdfno_v1": "Macdfno",
    # Emacrossopen variants
    "emacrossopen": "Emacrossopen",
    "emacross_fno_paper": "Emacrossopen",
    "emacross_open": "Emacrossopen",
}

_DISALLOWED_TAGS = {
    "ui_exit_position",
    "ui_exit",
    "manual_/_unattributed",
    "manual",
    "unattributed",
    "untagged",
    "unknown",
    "target_exit",
    "sl_exit",
    "stoploss_exit",
    "squareoff",
    "square_off",
    "exit",
}


def normalize_strategy_name(strategy: Optional[str]) -> Optional[str]:
    """
    Normalizes a strategy string to one of the authoritative names if matched.
    Returns None for disallowed/system tags or empty strings.
    If an unknown non-system name is provided, returns it stripped.
    """
    if not strategy:
        return None
    s = str(strategy).strip()
    if not s:
        return None

    clean = s.lower().replace("-", "_").replace(" ", "_")
    if clean in _DISALLOWED_TAGS:
        return None

    if clean in _CANONICAL_MAP:
        return _CANONICAL_MAP[clean]

    return s


def is_authoritative_strategy(strategy: Optional[str]) -> bool:
    """Checks if a strategy is one of the authoritative canonical strategies."""
    norm = normalize_strategy_name(strategy)
    return norm in AUTHORITATIVE_STRATEGIES


def parse_trade_timestamp(ts_val: Any) -> Optional[datetime]:
    """
    Parse timestamp across diverse broker and internal formats into naive datetime (IST).
    """
    if not ts_val:
        return None
    s = str(ts_val).strip()
    if not s:
        return None

    # Remove timezone suffixes
    s_clean = s.replace(" IST", "").replace("Z", "").strip()
    if "+" in s_clean:
        s_clean = s_clean.split("+")[0].strip()

    try:
        return datetime.fromisoformat(s_clean)
    except Exception:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d-%b-%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(s_clean, fmt)
        except Exception:
            continue

    return None
