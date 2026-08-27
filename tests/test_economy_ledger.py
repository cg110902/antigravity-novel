# -*- coding: utf-8 -*-
"""
Unit tests for economy ledger double-entry bookkeeping verification.

All work happens in a temp workspace so the committed repo needs no
novel_workspace/ data.
"""

import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "tools"))

from audit_economy_ledger import audit_economy_ledger  # noqa: E402
from verify_double_ledgers import verify_ledgers  # noqa: E402
from init_new_novel import init_novel  # noqa: E402


class TestEconomyLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="novel_studio_econ_"))
        self.workspace = self.tmp / "ws"
        init_novel(title="账本测试", genre="玄幻", protagonist="陈昂",
                   workspace_path=str(self.workspace))
        self.ledger_path = self.workspace / "04_timeline_and_state" / "economy_ledger.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_ledger(self, data: dict) -> None:
        self.ledger_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_fresh_initialized_ledger_balances(self):
        """The ledger rendered from the shipped template must be balanced."""
        report = audit_economy_ledger(workspace_path=str(self.workspace), as_json=True)
        self.assertTrue(report.get("is_balanced"),
                        msg=f"模板账本应平衡: {report.get('anomalies')}")
        self.assertEqual(len(report.get("anomalies", [])), 0)

        ledgers = verify_ledgers(workspace_path=str(self.workspace), as_json=True)
        self.assertEqual(len(ledgers.get("anomalies", [])), 0,
                         msg=f"双台账不应有异常: {ledgers.get('anomalies')}")

    def test_balanced_transactions_pass(self):
        """Inflow/outflow transactions that sum to the declared current balance pass."""
        data = {
            "resource_pools": {
                "standard_currency": {"name": "银两", "unit": "两", "initial": 10, "current": 35},
            },
            "transactions": [
                {"chapter": "ch_001", "resource": "standard_currency", "type": "income",
                 "inflow": 50, "outflow": 0, "balance_after": 60, "subject": "卖符纸"},
                {"chapter": "ch_002", "resource": "standard_currency", "type": "expense",
                 "inflow": 0, "outflow": 25, "balance_after": 35, "subject": "买药材"},
            ],
        }
        self._write_ledger(data)
        report = audit_economy_ledger(workspace_path=str(self.workspace), as_json=True)
        self.assertTrue(report.get("is_balanced"), msg=str(report.get("anomalies")))

        ledgers = verify_ledgers(workspace_path=str(self.workspace), as_json=True)
        self.assertEqual(ledgers.get("anomalies"), [])

    def test_unbalanced_transactions_fail(self):
        """A declared current balance that disagrees with the flow is flagged."""
        data = {
            "resource_pools": {
                "standard_currency": {"name": "银两", "unit": "两", "initial": 10, "current": 999},
            },
            "transactions": [
                {"chapter": "ch_001", "resource": "standard_currency", "type": "income",
                 "inflow": 50, "outflow": 0, "balance_after": 60, "subject": "卖符纸"},
            ],
        }
        self._write_ledger(data)
        report = audit_economy_ledger(workspace_path=str(self.workspace), as_json=True)
        self.assertFalse(report.get("is_balanced"))
        self.assertGreaterEqual(len(report.get("anomalies", [])), 1)

        ledgers = verify_ledgers(workspace_path=str(self.workspace), as_json=True)
        self.assertGreaterEqual(len(ledgers.get("anomalies", [])), 1)

    def test_unknown_resource_pool_is_flagged(self):
        """Transactions referencing an undeclared resource pool must not be silently skipped."""
        data = {
            "resource_pools": {
                "standard_currency": {"name": "银两", "unit": "两", "initial": 0, "current": 0},
            },
            "transactions": [
                {"chapter": "ch_001", "resource": "some_typo_pool", "type": "income",
                 "inflow": 100, "outflow": 0, "subject": "错误资源名"},
            ],
        }
        self._write_ledger(data)
        ledgers = verify_ledgers(workspace_path=str(self.workspace), as_json=True)
        self.assertTrue(any("未声明" in a for a in ledgers.get("anomalies", [])),
                        msg=f"应报出资源池未声明: {ledgers.get('anomalies')}")


if __name__ == "__main__":
    unittest.main()
