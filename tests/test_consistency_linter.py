# -*- coding: utf-8 -*-
"""
Unit tests for check_consistency.py Linter engine.

These tests build a throwaway workspace in a temp dir (via init_new_novel) so
they never depend on a committed novel_workspace/ and never mutate the repo.
"""

import sys
import shutil
import tempfile
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "tools"))

from check_consistency import check_all_consistency, resolve_workspace  # noqa: E402
from init_new_novel import init_novel  # noqa: E402

import re  # noqa: E402


def _make_chapter(path: Path, chinese_chars: int, quote_pairs: int = 0,
                  tag_leak: bool = False, cliffhanger: bool = True) -> None:
    """Write a chapter file containing roughly `chinese_chars` Chinese chars."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body_sentences = [
        "陈昂走在青石板路上，街边早点铺的热气一阵阵扑过来。",
        "他抬手掸了掸袖口的灰，脚步没停，心里却在盘算着今天的进项。",
        "掌柜的探出半个身子招呼他，算盘珠子拨得噼啪作响。",
        "街角拴着的老驴甩了甩尾巴，有一下没一下地啃着槽里的干草。",
        "他笑了笑，没接话，只把那枚磨得发亮的铜钱在指节间翻了个面。",
        "风从巷口灌进来，带着远处码头的鱼腥气和铁匠铺的煤烟味。",
    ]
    text_lines = ["# 第一章 测试", ""]
    total = 0
    i = 0
    while total < chinese_chars:
        s = body_sentences[i % len(body_sentences)]
        text_lines.append(s)
        text_lines.append("")
        total += len(re.findall(r"[\u4e00-\u9fa5]", s))
        i += 1
    if quote_pairs:
        for _ in range(quote_pairs):
            text_lines.append("“这事不急，先把账算清楚再说。”")
    if tag_leak:
        text_lines.append("他翻到 GUN-003 那一页，Stage 1 的伏笔就埋在这里。")
    if cliffhanger:
        text_lines.append("就在这时，门外忽然响起一阵急促的敲门声！")
    path.write_text("\n".join(text_lines), encoding="utf-8")


class TestConsistencyLinter(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="novel_studio_test_"))
        self.workspace = self.tmp / "ws"
        self.assertTrue(init_novel(title="测试书", genre="玄幻脑洞",
                                   protagonist="陈昂", workspace_path=str(self.workspace)))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_short_chapter_is_fatal(self):
        """A chapter under the configured word floor must FAIL (exit-blocking)."""
        ch = self.workspace / "05_manuscript" / "vol_01" / "finalized" / "ch_001.md"
        _make_chapter(ch, chinese_chars=600)
        res = check_all_consistency(self.workspace, target_chapter="ch_001", as_json=True)
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("status"), "FAIL")
        self.assertGreaterEqual(res.get("total_fatal_count", 0), 1)

    def test_full_chapter_passes(self):
        """A long, clean chapter (incl. vol_01) must PASS — no legacy exemption."""
        ch = self.workspace / "05_manuscript" / "vol_01" / "finalized" / "ch_001.md"
        _make_chapter(ch, chinese_chars=2800, quote_pairs=2)
        res = check_all_consistency(self.workspace, target_chapter="ch_001", as_json=True)
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("total_fatal_count", 1), 0,
                         msg=f"vol_01 长章不应有致命硬伤: {res.get('reports')}")
        self.assertNotEqual(res.get("status"), "FAIL")

    def test_tag_leak_is_fatal(self):
        """Engineering tags (GUN-/Stage) leaking into prose are a hard error."""
        ch = self.workspace / "05_manuscript" / "vol_01" / "finalized" / "ch_001.md"
        _make_chapter(ch, chinese_chars=2800, tag_leak=True)
        res = check_all_consistency(self.workspace, target_chapter="ch_001", as_json=True)
        self.assertEqual(res.get("status"), "FAIL")
        self.assertGreaterEqual(res.get("total_fatal_count", 0), 1)

    def test_full_book_scan_does_not_crash(self):
        """Whole-book scan (no target chapter) must not raise and must report files."""
        _make_chapter(self.workspace / "05_manuscript" / "vol_01" / "finalized" / "ch_001.md", 2800)
        res = check_all_consistency(self.workspace, target_chapter=None, as_json=True)
        self.assertIsInstance(res, dict)
        self.assertIn("reports", res)
        self.assertGreaterEqual(res.get("total_files", 0), 1)

    def test_missing_chapter_target_returns_error(self):
        """Asking for a non-existent chapter yields an error dict (exit 1)."""
        res = check_all_consistency(self.workspace, target_chapter="ch_099", as_json=True)
        self.assertIsInstance(res, dict)
        self.assertIn("error", res)


if __name__ == "__main__":
    unittest.main()
