# -*- coding: utf-8 -*-
"""
Unit tests for the 0-LLM proposal skeleton generator (tools/proposal_draft.py)
and the state_apply guard that must never merge a draft.
Throwaway temp workspaces only; never touches novel_workspace/.
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
import proposal_draft as pd  # noqa: E402
from state_apply import apply_proposal  # noqa: E402


def _mk_ws(genre="玄幻仙侠", protagonist="陈昂"):
    tmp = Path(tempfile.mkdtemp(prefix="novel_draft_"))
    ws = tmp / "ws"
    init_novel(workspace_path=str(ws), genre=genre, title="草稿测试", protagonist=protagonist)
    return tmp, ws


def _write_ch(ws, num, body):
    d = ws / "05_manuscript/vol_01/finalized"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"ch_{num:03d}.md").write_text(f"# 第{num}章 交易\n\n{body}\n", encoding="utf-8")


def _register(ws, *names):
    cdir = ws / "02_characters"
    cdir.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"| {n} | 角色 |" for n in names)
    (cdir / "character_index.md").write_text(
        "# 角色索引表\n| 角色名 | 身份 |\n|---|---|\n" + rows + "\n", encoding="utf-8")


class TestNumberParsing(unittest.TestCase):
    def test_arabic_and_cn(self):
        self.assertEqual(pd.parse_cn_number("500"), 500)
        self.assertEqual(pd.parse_cn_number("五百"), 500)
        self.assertEqual(pd.parse_cn_number("二两"), 2)
        self.assertEqual(pd.parse_cn_number("三千"), 3000)
        self.assertIsNone(pd.parse_cn_number(""))
        self.assertIsNone(pd.parse_cn_number("没有数字"))


class TestTransactionExtraction(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = _mk_ws()
        _register(self.ws, "陈昂", "老周")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_income_expense_direction_and_pool(self):
        _write_ch(self.ws, 4,
                  "陈昂完成任务，获得 30 点功勋。他又花了 5 信用点修好义体。")
        d = pd.build_draft(self.ws, "ch_004")
        tx = d["transactions_draft"]
        self.assertEqual(len(tx), 2)
        by_unit = {t["_unit"]: t for t in tx}
        # 功勋 -> vital_points，收入
        gong = [t for t in tx if t["resource"] == "vital_points"]
        self.assertTrue(gong and gong[0]["delta"] == 30 and gong[0]["delta"] > 0)
        # 信用点 -> standard_currency，支出
        cred = [t for t in tx if t["resource"] == "standard_currency"]
        self.assertTrue(cred and cred[0]["delta"] == -5)

    def test_cn_amount_and_multi_tx_in_one_line(self):
        _write_ch(self.ws, 3,
                  "他向老周花了二两灵石买下情报，又把旧剑卖了赚回五百文钱。")
        d = pd.build_draft(self.ws, "ch_003")
        tx = d["transactions_draft"]
        self.assertEqual(len(tx), 2)
        deltas = sorted(t["delta"] for t in tx)
        self.assertEqual(deltas, [-2, 500])

    def test_all_tx_marked_needs_review_with_evidence(self):
        _write_ch(self.ws, 1, "陈昂花了十两灵石买剑。")
        d = pd.build_draft(self.ws, "ch_001")
        for t in d["transactions_draft"]:
            self.assertTrue(t["_needs_review"])
            self.assertIn("sentence", t["evidence"])


class TestPresentCharacters(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = _mk_ws()
        _register(self.ws, "陈昂", "老周", "路人甲")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_prefills_only_characters_present(self):
        _write_ch(self.ws, 2, "陈昂独自走进黑市，没有遇到老周，也没见其他人。")
        d = pd.build_draft(self.ws, "ch_002")
        present = d["current_state"]["present_characters"]
        self.assertIn("陈昂", present)
        self.assertNotIn("路人甲", present)  # 未出场不入列


class TestDraftSafety(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = _mk_ws()
        _register(self.ws, "陈昂")
        _write_ch(self.ws, 1, "陈昂花了五两灵石。")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_draft_flag_rejected_by_apply(self):
        d = pd.build_draft(self.ws, "ch_001")
        self.assertTrue(d["_draft"])
        rep = apply_proposal(self.ws, d)
        self.assertTrue(any("草稿" in e for e in rep["errors"]))

    def test_gather_skips_draft_files(self):
        from state_apply import _gather_proposals
        inbox = self.ws / "04_timeline_and_state/state_inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "ch_001.draft.json").write_text("{}", encoding="utf-8")
        (inbox / "ch_001.json").write_text("{}", encoding="utf-8")
        names = [p.name for p in _gather_proposals(inbox)]
        self.assertIn("ch_001.json", names)
        self.assertNotIn("ch_001.draft.json", names)

    def test_draft_has_review_checklist_and_clues(self):
        d = pd.build_draft(self.ws, "ch_001")
        self.assertTrue(d["_review_checklist"])
        self.assertIn("_evidence_summary", d)
        # 语义字段留空给 LLM
        self.assertEqual(d["guns"], [])
        self.assertEqual(d["timeline"], [])


if __name__ == "__main__":
    unittest.main()
