# -*- coding: utf-8 -*-
"""
Unit tests for economy ledger double-entry bookkeeping verification.
"""

import unittest
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "tools"))

from audit_economy_ledger import audit_economy_ledger

class TestEconomyLedger(unittest.TestCase):

    def test_current_workspace_economy_ledger_balance(self):
        """Validates that the real economy_ledger.json in novel_workspace is 100% mathematically balanced."""
        report = audit_economy_ledger(as_json=True)
        self.assertIsInstance(report, dict)
        self.assertTrue(report.get("is_balanced", False))
        self.assertEqual(len(report.get("anomalies", [])), 0)

if __name__ == "__main__":
    unittest.main()
