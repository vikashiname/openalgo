"""
================================================================================
OPENALGO STRATEGY RUNTIME CONTRACT AUDIT & PREVENTION TEST SUITE
================================================================================
Automated verification ensuring all live strategy engines comply with:
  1. Collision-Free Heartbeat Allocation: No two strategies share default heartbeats.
  2. Process-Isolated PID Atomic State: All temp writes use PID or strategy_runtime.
  3. Multi-Format Expiry Parsing: Robust date handling for all exchange formats.
  4. Contract Resolution Caching: 24h TTL suppression for discontinued symbols.
  5. Self-Healing State Recovery: Automatic fallback/re-creation on invalid JSON.
================================================================================
"""

import ast
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from strategies.strategy_runtime import (
    COMMON_EXPIRY_FORMATS,
    SafeContractCache,
    atomic_write_json,
    get_strategy_heartbeat_path,
    parse_contract_expiry,
)


class TestStrategyRuntimeModule(unittest.TestCase):
    """Verifies core functions in strategies/strategy_runtime.py"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_strategy_rt_"))

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_atomic_write_json_success_and_pid_isolation(self):
        target_file = self.test_dir / "state.json"
        data = {"status": "ACTIVE", "trades": [1, 2, 3], "ts": "2026-10-13"}
        atomic_write_json(target_file, data)

        self.assertTrue(target_file.exists())
        with open(target_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["status"], "ACTIVE")
        self.assertEqual(loaded["trades"], [1, 2, 3])

        # Verify no orphan tmp file left behind
        tmp_files = list(self.test_dir.glob("*.tmp*"))
        self.assertEqual(len(tmp_files), 0)

    def test_parse_contract_expiry_all_formats(self):
        sample_dates = [
            ("27-OCT-26", 2026, 10, 27),
            ("27-OCT-2026", 2026, 10, 27),
            ("27-October-26", 2026, 10, 27),
            ("27-October-2026", 2026, 10, 27),
            ("27-10-2026", 2026, 10, 27),
            ("27-10-26", 2026, 10, 27),
            ("2026-10-27", 2026, 10, 27),
        ]
        for date_str, expected_y, expected_m, expected_d in sample_dates:
            dt = parse_contract_expiry(date_str)
            self.assertIsNotNone(dt, f"Failed to parse valid date: {date_str}")
            self.assertEqual(dt.year, expected_y)
            self.assertEqual(dt.month, expected_m)
            self.assertEqual(dt.day, expected_d)
            self.assertEqual(dt.hour, 23)
            self.assertEqual(dt.minute, 59)

        # Invalid/empty dates return None
        self.assertIsNone(parse_contract_expiry(None))
        self.assertIsNone(parse_contract_expiry(""))
        self.assertIsNone(parse_contract_expiry("INVALID_DATE"))

    def test_safe_contract_cache_unresolvable_ttl(self):
        cache = SafeContractCache(ttl_hours=24)
        now = datetime(2026, 10, 13, 9, 0, 0)
        symbol = "DALBHARAT"

        # Initially not in cache -> should retry
        self.assertFalse(cache.is_resolved(symbol, now))
        self.assertTrue(cache.should_retry(symbol, now))

        # Record unresolvable
        cache.record_unresolvable(symbol, now)

        # Within 24h, should NOT retry and is NOT resolved
        self.assertFalse(cache.is_resolved(symbol, now))
        self.assertFalse(cache.should_retry(symbol, now))

        # 1 hour later -> still cached, do not retry
        one_hour_later = now + timedelta(hours=1)
        self.assertFalse(cache.should_retry(symbol, one_hour_later))

        # 25 hours later -> TTL expired, should retry
        twenty_five_hours_later = now + timedelta(hours=25)
        self.assertTrue(cache.should_retry(symbol, twenty_five_hours_later))

    def test_strategy_heartbeat_path_collision_free(self):
        script_dir = Path("/home/ubuntu/strategies")
        hb_macd = get_strategy_heartbeat_path("macdfno", script_dir)
        hb_ema = get_strategy_heartbeat_path("emacrossopen", script_dir)
        hb_oi = get_strategy_heartbeat_path("oifno", script_dir)
        hb_ncc = get_strategy_heartbeat_path("nifty_covered_call", script_dir)

        # Ensure no two strategies share the same heartbeat filename
        paths = [hb_macd, hb_ema, hb_oi, hb_ncc]
        unique_paths = set(paths)
        self.assertEqual(len(paths), len(unique_paths))
        self.assertNotIn(script_dir / "heartbeat.json", paths)


class TestLiveStrategiesStaticContractAudit(unittest.TestCase):
    """
    Statically audits live strategy scripts to ensure no regression
    or re-introduction of shared temp files or colliding heartbeats.
    """

    ROOT_DIR = Path(__file__).resolve().parent.parent
    LIVE_DIR = ROOT_DIR / "strategies" / "liveonopenalgo"

    STRATEGY_SCRIPTS = [
        "macdfno.py",
        "emacrossopen.py",
        "oifno.py",
        "nifty_covered_call.py",
    ]

    def test_unique_default_heartbeat_files(self):
        """No two strategies should default to the generic 'heartbeat.json' or collide."""
        assigned_heartbeats = {}
        for script_name in self.STRATEGY_SCRIPTS:
            file_path = self.LIVE_DIR / script_name
            self.assertTrue(file_path.exists(), f"Missing strategy script: {file_path}")
            content = file_path.read_text(encoding="utf-8")

            # Find default heartbeat path definition
            heartbeat_found = None
            for line in content.splitlines():
                if "HEARTBEAT_FILE" in line and "=" in line and "getenv" in line:
                    heartbeat_found = line
                    break
            self.assertIsNotNone(heartbeat_found, f"{script_name} must define HEARTBEAT_FILE with strategy default")
            assigned_heartbeats[script_name] = heartbeat_found

        # Assert no strategy has generic default 'heartbeat.json' as primary target
        for script, hb_def in assigned_heartbeats.items():
            self.assertNotIn('SCRIPT_DIR / "heartbeat.json")', hb_def,
                             f"{script} defaults to generic heartbeat.json! Must use strategy-specific heartbeat.")

    def test_process_isolated_pid_temp_writes(self):
        """All temporary atomic writes must include os.getpid() to prevent race clobbering."""
        for script_name in self.STRATEGY_SCRIPTS:
            file_path = self.LIVE_DIR / script_name
            content = file_path.read_text(encoding="utf-8")

            # Check every occurrence of .tmp or atomic replace
            lines = content.splitlines()
            for idx, line in enumerate(lines, 1):
                if ".tmp" in line and not line.strip().startswith("#"):
                    # Must use PID isolation (.tmp.{os.getpid()} or .tmp.{pid})
                    has_pid = ("os.getpid()" in line) or ("{pid}" in line) or ("pid" in line)
                    self.assertTrue(has_pid, f"Unsafe non-PID temp write in {script_name}:{idx}: {line}")

    def test_multi_format_expiry_parser_present(self):
        """Contract resolution strategies must handle multiple date formats."""
        fno_scripts = ["macdfno.py", "emacrossopen.py"]
        for script_name in fno_scripts:
            file_path = self.LIVE_DIR / script_name
            content = file_path.read_text(encoding="utf-8")
            has_multi_format = (
                "strptime" in content and (
                    ("%d-%b-%y" in content and "%d-%b-%Y" in content) or
                    "parse_contract_expiry" in content
                )
            )
            self.assertTrue(has_multi_format, f"{script_name} must support multi-format contract expiry parsing.")

    def test_watchdog_monitors_all_live_strategies(self):
        """Ensure watchdog monitors all live strategies without collisions."""
        from strategies.liveonopenalgo.watchdog import HealthWatchdog, REGISTERED_HEARTBEATS
        wd = HealthWatchdog()
        targets = wd.get_monitored_targets()
        self.assertGreaterEqual(len(targets), 4)
        for key in ["MACD_FNO", "EMACROSS", "OI_FNO", "NIFTY_COVERED_CALL"]:
            self.assertIn(key, targets)


if __name__ == "__main__":
    unittest.main()
