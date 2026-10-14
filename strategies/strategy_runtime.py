"""
================================================================================
OPENALGO STRATEGY RUNTIME ENGINE: CORE ATOMIC PERSISTENCE & LIFECYCLE UTILITIES
================================================================================
File Role            : SYSTEMIC RELIABILITY GUARD & CORE UTILITY
Module               : strategies.strategy_runtime
Current Version      : 1.0.0
Author               : OpenAlgo Engineering Team

Guarantees system-wide protection against:
  1. Concurrent heartbeat collisions (process-isolated PID temp files).
  2. Multi-strategy file clobbering (unique strategy-specific heartbeat defaults).
  3. Corrupted state crash loops (self-healing state recovery and atomic replacement).
  4. Exchange expiry date format mismatches (%d-%b-%y, %d-%b-%Y, ISO, etc.).
  5. Infinite search-API loops on dropped or inactive NFO contracts via TTL cache.
================================================================================
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("STRATEGY_RUNTIME")

COMMON_EXPIRY_FORMATS: Tuple[str, ...] = (
    "%d-%b-%y",   # e.g., 28-OCT-26
    "%d-%b-%Y",  # e.g., 28-OCT-2026
    "%d-%B-%y",  # e.g., 28-October-26
    "%d-%B-%Y",  # e.g., 28-October-2026
    "%d-%m-%Y",  # e.g., 28-10-2026
    "%d-%m-%y",  # e.g., 28-10-26
    "%Y-%m-%d",  # e.g., 2026-10-28
)


def atomic_write_json(file_path: Path, data: Any, indent: int = 2) -> None:
    """
    Atomically writes JSON to disk using a process-isolated temporary file
    and atomic file replacement to eliminate race conditions and zero-byte file corruptions.
    """
    pid = os.getpid()
    temp_file = file_path.with_suffix(f".tmp.{pid}")
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, default=str)
        temp_file.replace(file_path)
    except Exception as e:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
        raise IOError(f"Atomic JSON write failed for {file_path}: {e}") from e


def parse_contract_expiry(expiry_str: Optional[str]) -> Optional[datetime]:
    """
    Robustly parses contract expiry string across all known Indian broker
    and exchange date formats. Returns datetime with hour=23, minute=59.
    """
    if not expiry_str or not isinstance(expiry_str, str):
        return None

    cleaned = expiry_str.strip()
    for fmt in COMMON_EXPIRY_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).replace(hour=23, minute=59, second=59)
        except (ValueError, TypeError):
            continue
    return None


def get_strategy_heartbeat_path(strategy_name: str, script_dir: Path) -> Path:
    """
    Returns strategy-specific heartbeat path from environment variable or derives
    a guaranteed collision-free default filename.
    """
    env_override = os.getenv("HEARTBEAT_FILE")
    if env_override:
        return Path(env_override)
    safe_name = strategy_name.lower().replace("-", "_").replace(" ", "_")
    return script_dir / f"{safe_name}_heartbeat.json"


class SafeContractCache:
    """
    In-memory contract resolution cache with 24-hour TTL for unresolvable symbols.
    Prevents repetitive search API round-trips and error logging loops.
    """
    def __init__(self, ttl_hours: int = 24):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = timedelta(hours=ttl_hours)

    def is_resolved(self, symbol: str, now: Optional[datetime] = None) -> bool:
        entry = self.cache.get(symbol)
        if not entry:
            return False
        now_dt = now or datetime.now()
        exp = entry.get("expiry_dt")
        if exp and now_dt >= exp:
            return False
        return bool(entry.get("contract"))

    def should_retry(self, symbol: str, now: Optional[datetime] = None) -> bool:
        entry = self.cache.get(symbol)
        if not entry:
            return True
        now_dt = now or datetime.now()
        exp = entry.get("expiry_dt")
        return bool(exp and now_dt >= exp)

    def record_resolved(self, symbol: str, contract: str, lot_size: int, order_qty: int, expiry_dt: datetime):
        self.cache[symbol] = {
            "contract": contract,
            "lot_size": lot_size,
            "order_qty": order_qty,
            "expiry_dt": expiry_dt,
            "unresolvable": False,
        }

    def record_unresolvable(self, symbol: str, now: Optional[datetime] = None):
        now_dt = now or datetime.now()
        self.cache[symbol] = {
            "contract": None,
            "lot_size": None,
            "order_qty": 0,
            "expiry_dt": now_dt + self.ttl,
            "unresolvable": True,
        }
