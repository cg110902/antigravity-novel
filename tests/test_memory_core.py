# -*- coding: utf-8 -*-
"""
Unit tests for the P1 memory engine (tools/memory_core.py):
- synopsis spine build / render / manual override
- BM25 librarian recall (relevance ranking)
- cross-chapter repetition detection (repeated intro / n-gram / similar scenes)
- package_context budget mode trimming + memory injection

All in throwaway temp workspaces; never touches novel_workspace/.
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
import memory_core as mc  # noqa: E402


def _mk_ws():
    tmp = Path(tempfile.mkdtemp(prefix="novel_mem_"))
    ws = tmp / "ws"
    init_novel(workspace_path=str(ws))
    return tmp, ws


def _write_ch(ws, num, title, body):
    d = ws / "05_manuscript" / "vol_01" / "finalized"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"ch_{num:03d}.md").write_text(f"# 第{num}章 {title}\n\n{body}\n", encoding="utf-8")


def _register(ws, *names):
    cdir = ws / "02_characters"
    cdir.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"| {n} | 角色 | 备注 |" for n in names)
    (cdir / "character_index.md").write_text(
        "# 角色索引表\n| 角色名 | 身份 | 备注 |\n|---|---|---|\n" + rows + "\n",
        encoding="utf-8")


CH1 = ("陈昂在废土边缘的废墟里醒来，记忆残缺。他曾是铁壁公司的低级技工。"
       "他在废墟中翻找到一块锈迹斑斑的数据芯片，悄悄藏进鞋底。"
       "为了换取饮水配给，陈昂把祖传怀表押给黑市掮客老周。老周说这表只值三天水票。")
CH2 = ("陈昂带着芯片潜入黑市后街，想找门路读取数据。掮客老周认出了他，提出一笔交易。"
       "老周说铁壁公司正在严查流失的数据芯片，风声很紧。两人低声交锋，老周答应引荐解码人。"
       "陈昂交出三分之一水票当定金，约定三日后在废仓库碰面。")
CH3 = ("三日后陈昂如约来到废仓库。解码人没出现，来的是两个铁壁公司打手。陈昂意识到老周出卖了他。"
       "打手上前盘问他的来历，为首的人问他叫什么名字。陈昂沉声道，他叫陈昂，今年二十二岁，只是个拾荒的。"
       "一番恶斗，陈昂翻窗逃脱，但芯片被迫留在了仓库。")


class TestSynopsisSpine(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = _mk_ws()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_spine_build_and_render(self):
        _write_ch(self.ws, 1, "废土求生", CH1)
        _write_ch(self.ws, 2, "黑市交锋", CH2)
        data = mc.build_spine(self.ws)
        self.assertEqual(data["_changed"], 2)
        # 文件落盘
        self.assertTrue((self.ws / mc.SYNOPSIS_FILE).exists())
        brief = mc.render_spine_brief(data)
        self.assertIn("废土求生", brief)
        self.assertIn("第1章", brief)
        # 标题前缀不重复
        self.assertNotIn("第1章《第1章", brief)

    def test_manual_synopsis_not_overwritten_by_auto(self):
        _write_ch(self.ws, 1, "废土求生", CH1)
        mc.build_spine(self.ws)
        data = mc.load_synopsis(self.ws)
        # 标记 manual
        data["chapters"]["ch_001"]["synopsis"] = "人工提炼的高质量梗概。"
        data["chapters"]["ch_001"]["source"] = "manual"
        mc.save_synopsis(self.ws, data)
        # 再次 build 不应覆盖 manual
        mc.build_spine(self.ws)
        again = mc.load_synopsis(self.ws)
        self.assertEqual(again["chapters"]["ch_001"]["synopsis"], "人工提炼的高质量梗概。")
        self.assertEqual(again["chapters"]["ch_001"]["source"], "manual")


class TestBM25Librarian(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = _mk_ws()
        _write_ch(self.ws, 1, "废土求生", CH1)
        _write_ch(self.ws, 2, "黑市交锋", CH2)
        _write_ch(self.ws, 3, "废仓库之夜", CH3)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_recall_ranks_relevant_chapter_first(self):
        hits = mc.librarian_recall(self.ws, "铁壁公司 数据芯片 严查", top_k=3)
        self.assertTrue(hits)
        # ch_002 明确讲"铁壁公司严查芯片"，应排第一
        self.assertEqual(hits[0]["num"], 2)
        self.assertGreater(hits[0]["score"], 0)

    def test_recall_excludes_chapter(self):
        hits = mc.librarian_recall(self.ws, "芯片", top_k=5, exclude_chapter=2)
        self.assertNotIn(2, [h["num"] for h in hits])

    def test_empty_query_returns_empty(self):
        self.assertEqual(mc.librarian_recall(self.ws, "", top_k=3), [])


class TestCrossChapterRepetition(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = _mk_ws()
        _write_ch(self.ws, 1, "废土求生", CH1)
        _write_ch(self.ws, 2, "黑市交锋", CH2)
        _write_ch(self.ws, 3, "废仓库之夜", CH3)
        _register(self.ws, "陈昂", "老周")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_repeated_intro_detected(self):
        rep = mc.detect_cross_chapter_repetition(self.ws)
        # ch3 里陈昂（首见 ch1）又被问名字/报年龄
        self.assertTrue(any("陈昂" in h for h in rep["repeated_intros"]),
                        msg=str(rep["repeated_intros"]))

    def test_ngram_copy_paste_detected(self):
        # ch5 大段复制 ch1
        _write_ch(self.ws, 5, "旧事重演",
                  "陈昂在废土边缘的废墟里醒来，记忆残缺。"
                  "他在废墟中翻找到一块锈迹斑斑的数据芯片，悄悄藏进鞋底。"
                  "为了换取饮水配给，陈昂把祖传怀表押给黑市掮客老周。")
        rep = mc.detect_cross_chapter_repetition(self.ws)
        self.assertTrue(any("ch_001" in h and "ch_005" in h for h in rep["ngram_hits"]),
                        msg=str(rep["ngram_hits"]))

    def test_clean_novel_no_false_positive_for_single_chapter(self):
        tmp2, ws2 = _mk_ws()
        try:
            _write_ch(ws2, 1, "唯一一章", CH1)
            rep = mc.detect_cross_chapter_repetition(ws2)
            self.assertEqual(rep["warnings"], [])
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)


class TestFallbackTokenizer(unittest.TestCase):
    def test_fallback_tokens_contain_bigram(self):
        toks = mc._fallback_tokens("陈昂潜入黑市后街交易")
        # 应含相邻 bi-gram
        self.assertIn("陈昂", toks)
        self.assertIn("黑市", toks)

    def test_english_and_numbers(self):
        toks = mc._fallback_tokens("获得 500 credits 和 GUN-007")
        self.assertIn("500", toks)
        self.assertIn("credits", toks)


class TestPackBudget(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = _mk_ws()
        _write_ch(self.ws, 1, "废土求生", CH1)
        _write_ch(self.ws, 2, "黑市交锋", CH2)
        _write_ch(self.ws, 3, "废仓库之夜", CH3)
        _register(self.ws, "陈昂")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_budget_mode_trims_and_reports(self):
        from package_context import package_context_for_chapter
        pkg = package_context_for_chapter("ch_004", workspace_path=str(self.ws),
                                          as_json=False, budget=900)
        br = pkg.get("budget_report")
        self.assertIsNotNone(br)
        self.assertLessEqual(br["total_kept_tokens"], 900)
        self.assertTrue(br["within_budget"])
        # 记忆区块在全量装配后存在
        self.assertIn("废土求生", pkg.get("synopsis_spine", ""))

    def test_full_mode_has_memory_sections(self):
        from package_context import package_context_for_chapter
        pkg = package_context_for_chapter("ch_004", workspace_path=str(self.ws),
                                          as_json=False, budget=0)
        self.assertNotIn("budget_report", pkg)  # 全量模式无预算报告
        self.assertTrue(pkg.get("synopsis_spine"))


if __name__ == "__main__":
    unittest.main()
