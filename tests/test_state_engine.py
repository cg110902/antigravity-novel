# -*- coding: utf-8 -*-
"""
Unit tests for the P0 deterministic state engine:
- state_apply.py (structured mutation proposals -> merged state files)
- validate_state.py (workspace health / ledger balance / placeholder check)

All work happens in a throwaway temp workspace; never touches novel_workspace/.
"""

import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "tools"))

from init_new_novel import init_novel  # noqa: E402
from state_apply import apply_proposal, MUTATION_SCHEMA  # noqa: E402
from validate_state import validate_workspace  # noqa: E402


def _ledger_balance(ws: Path):
    d = json.loads((ws / "04_timeline_and_state/economy_ledger.json").read_text(encoding="utf-8"))
    return d["resource_pools"]["standard_currency"]["current"], len(d.get("transactions", []))


class TestStateApply(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="novel_state_"))
        self.ws = self.tmp / "ws"
        self.assertTrue(init_novel(title="状态引擎测试", genre="科幻", protagonist="陈昂",
                                   workspace_path=str(self.ws)))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_transactions_derive_balance(self):
        rep = apply_proposal(self.ws, {
            "schema": MUTATION_SCHEMA, "chapter": "ch_003",
            "transactions": [
                {"resource": "standard_currency", "delta": 100, "subject": "卖货"},
                {"resource": "standard_currency", "delta": -30, "subject": "买情报"},
            ],
        })
        self.assertEqual(rep["errors"], [])
        bal, ntx = _ledger_balance(self.ws)
        self.assertEqual(bal, 70)           # 0 + 100 - 30
        self.assertEqual(ntx, 3)            # 1 opening + 2 new

    def test_undeclared_resource_pool_is_error(self):
        rep = apply_proposal(self.ws, {
            "schema": MUTATION_SCHEMA, "chapter": "ch_004",
            "transactions": [{"resource": "typo_pool", "delta": 50}],
        })
        self.assertTrue(any(("未声明" in e or "不存在" in e) for e in rep["errors"]))

    def test_gun_plant_auto_id_and_resolve(self):
        rep = apply_proposal(self.ws, {
            "schema": MUTATION_SCHEMA, "chapter": "ch_003",
            "guns": [{"action": "plant", "name": "铁壁公司账本", "target_ch": 18}],
        })
        self.assertEqual(rep["errors"], [])
        guns = (self.ws / "04_timeline_and_state/chekhov_guns.md").read_text(encoding="utf-8")
        # 自动编号（模板占位行 GUN-001/2/3 被过滤，真实新枪从 GUN-001 起）
        self.assertIn("铁壁公司账本", guns)
        self.assertIn("Planted", guns)

    def test_proposal_is_idempotent_via_inbox_flow(self):
        """Applying the same proposal file twice (processed archive) must not double-apply."""
        from state_apply import _gather_proposals
        inbox = self.ws / "04_timeline_and_state/state_inbox"
        prop = {"schema": MUTATION_SCHEMA, "chapter": "ch_003",
                "transactions": [{"resource": "standard_currency", "delta": 50, "subject": "x"}]}
        (inbox / "p1.json").write_text(json.dumps(prop, ensure_ascii=False), encoding="utf-8")
        # Simulate main(): gather -> apply -> archive
        import state_apply
        files = _gather_proposals(inbox)
        self.assertEqual(len(files), 1)
        proposal = json.loads(files[0].read_text(encoding="utf-8"))
        rep = apply_proposal(self.ws, proposal)
        self.assertEqual(rep["errors"], [])
        (inbox / "processed").mkdir(exist_ok=True)
        files[0].rename(inbox / "processed" / files[0].name)
        # Second gather sees nothing left
        self.assertEqual(_gather_proposals(inbox), [])
        bal, _ = _ledger_balance(self.ws)
        self.assertEqual(bal, 50)

    def test_current_state_fields_updated(self):
        rep = apply_proposal(self.ws, {
            "schema": MUTATION_SCHEMA, "chapter": "ch_003",
            "current_state": {"location": "黑市后街", "time": "第三日·夜",
                              "present_characters": ["陈昂", "老周"]},
        })
        self.assertEqual(rep["errors"], [])
        cs = (self.ws / "04_timeline_and_state/current_state.md").read_text(encoding="utf-8")
        self.assertIn("黑市后街", cs)
        self.assertIn("陈昂", cs)

    def test_growth_arc_update(self):
        rep = apply_proposal(self.ws, {
            "schema": MUTATION_SCHEMA, "chapter": "ch_003",
            "growth_arcs": [{"name": "陈昂", "stage": "Stage 1【信息做庄】",
                             "inciting_event": "首次主动布局"}],
        })
        self.assertEqual(rep["errors"], [])
        ga = (self.ws / "04_timeline_and_state/character_growth_arcs.md").read_text(encoding="utf-8")
        self.assertIn("Stage 1【信息做庄】", ga)


class TestValidateState(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="novel_validate_"))
        self.ws = self.tmp / "ws"
        init_novel(workspace_path=str(self.ws))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_workspace_has_no_errors(self):
        rep = validate_workspace(self.ws)
        # 新书只有“待填写占位符”警告，不应有结构/账本错误
        self.assertEqual(rep["error_count"], 0, msg=str(rep["errors"]))

    def test_unbalanced_ledger_is_error(self):
        lp = self.ws / "04_timeline_and_state/economy_ledger.json"
        d = json.loads(lp.read_text(encoding="utf-8"))
        d["resource_pools"]["standard_currency"]["current"] = 999  # 流水实际为 0
        lp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        rep = validate_workspace(self.ws)
        self.assertTrue(any("不平衡" in e for e in rep["errors"]))

    def test_missing_file_is_error(self):
        (self.ws / "04_timeline_and_state/timeline.md").unlink()
        rep = validate_workspace(self.ws)
        self.assertTrue(any("timeline.md" in e for e in rep["errors"]))


if __name__ == "__main__":
    unittest.main()
