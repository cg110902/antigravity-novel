# -*- coding: utf-8 -*-
"""
Unit tests for check_consistency.py Linter engine.
"""

import unittest
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "tools"))

from check_consistency import check_all_consistency, resolve_workspace

class TestConsistencyLinter(unittest.TestCase):

    def test_all_finalized_chapters_pass_sanity(self):
        """Validates that all finalized chapters in workspace pass basic linter without crashes."""
        w_dir = resolve_workspace()
        res = check_all_consistency(w_dir, as_json=True)
        self.assertIsInstance(res, dict)
        self.assertIn("reports", res)
        self.assertGreaterEqual(res.get("total_files", 0), 1)

if __name__ == "__main__":
    unittest.main()
