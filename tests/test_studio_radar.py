# -*- coding: utf-8 -*-
"""
Integration test for the master radar aggregation and snapshot/rollback flows.
Uses a throwaway temp workspace; never touches the committed repo workspace.
"""

import sys
import shutil
import tempfile
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "tools"))

from init_new_novel import init_novel  # noqa: E402
from studio_radar import run_master_radar, run_subtool_json, _is_blocking  # noqa: E402
import sys as _sys  # noqa: E402

PY = _sys.executable
TOOLS = _root / "tools"


class TestStudioRadar(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="novel_studio_radar_"))
        self.workspace = self.tmp / "ws"
        init_novel(title="雷达测试", genre="悬疑", protagonist="林默",
                   workspace_path=str(self.workspace))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_workspace_radar_is_green(self):
        """A brand-new workspace with no chapters must report ALL_GREEN (not errors)."""
        report = run_master_radar(workspace_path=str(self.workspace), as_json=True)
        self.assertEqual(report["overall_status"], "ALL_GREEN")
        self.assertFalse(report["blocking"],
                         msg=f"空工作区不应有阻断项: {report.get('anomalies')}")
        # No subtool should have died with a parse error.
        for name, sub in report["scorecard"].items():
            self.assertNotIn("无法解析", str(sub.get("error", "")),
                             msg=f"{name} 输出了无法解析的 JSON")

    def test_blocking_flag_detects_failures(self):
        self.assertTrue(_is_blocking({"error": "boom"}))
        self.assertTrue(_is_blocking({"status": "FAIL"}))
        self.assertTrue(_is_blocking({"is_balanced": False}))
        self.assertTrue(_is_blocking({"total_critical": 2}))
        self.assertTrue(_is_blocking({"anomalies": ["x"]}))
        self.assertFalse(_is_blocking({"status": "PASS"}))
        self.assertFalse(_is_blocking({"status": "SKIP"}))

    def test_bad_subtool_command_is_reported_not_crashed(self):
        """A non-existent tool must surface as an error dict, never None/silent."""
        res = run_subtool_json([PY, str(TOOLS / "does_not_exist.py"), "--json"])
        self.assertIsInstance(res, dict)
        self.assertIn("error", res)

    def test_fresh_workspace_plot_dag_has_no_phantom_guns(self):
        """Template example guns ([...] placeholders) must NOT be parsed as real guns."""
        from audit_plot_dag import audit_plot_dag
        report = audit_plot_dag(workspace_path=str(self.workspace), as_json=True, print_output=False)
        self.assertEqual(report.get("total_guns"), 0,
                         msg=f"新书不应解析出示例伏笔: {[g['id'] for g in report.get('guns_details', [])]}")
        self.assertEqual(report.get("anomalies"), [])

    def test_fresh_workspace_guns_state_machine_clean(self):
        """State inspector must report zero active guns for a fresh templated workspace."""
        from state_inspector import inspect_state
        report = inspect_state(workspace_path=str(self.workspace), as_json=True)
        self.assertEqual(report["guns"]["active_list"], [])
        self.assertEqual(report["guns"]["planted"], 0)
        self.assertEqual(report["misunderstandings"], [])


if __name__ == "__main__":
    unittest.main()
