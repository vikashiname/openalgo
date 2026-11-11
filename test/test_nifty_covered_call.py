#!/usr/bin/env python3
"""
Unit Test Suite for NIFTY Covered Call Strategy
Location: test/test_nifty_covered_call.py
Imports and runs the comprehensive pre-deployment validation suite.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BACKTEST_DIR = PROJECT_ROOT / "backtesting" / "nifty_covered_call"
if str(BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(BACKTEST_DIR))

from test_pre_deployment_validation import TestPreDeploymentValidation
from test_hardening_failure_injection import TestHardeningFailureInjection
from test_always_in_sync_reconciliation import TestAlwaysInSyncReconciliation
from test_rolling_defensive_collar import TestRollingDefensiveCollar

if __name__ == "__main__":
    import unittest
    unittest.main()
