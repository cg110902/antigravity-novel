# -*- coding: utf-8 -*-
"""
Unit tests for novel_utils core functions.
"""

import unittest
import sys
import re
from pathlib import Path

# Add project root and tools to sys.path
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "tools"))

from novel_utils import (
    GENERIC_SKELETONS,
    CLIFFHANGER_KEYWORDS,
    natural_chapter_sort_key,
    detect_semantic_redundancy,
    unsupervised_burstiness_slices
)

class TestNovelUtils(unittest.TestCase):

    def test_natural_chapter_sort_key(self):
        p1 = Path("vol_01/finalized/ch_001.md")
        p2 = Path("vol_01/finalized/ch_002.md")
        p10 = Path("vol_01/finalized/ch_010.md")
        self.assertLess(natural_chapter_sort_key(p1), natural_chapter_sort_key(p2))
        self.assertLess(natural_chapter_sort_key(p2), natural_chapter_sort_key(p10))

    def test_generic_skeletons_patterns(self):
        # 1. State Particle Abstraction
        pattern_item = next(p for p in GENERIC_SKELETONS if "State Particle" in p["name"])
        self.assertTrue(re.search(pattern_item["pattern"], "面上露出一抹思索之色"))
        
        # 2. Tag Leak
        tag_leak_item = next(p for p in GENERIC_SKELETONS if "Internal Engineering Tag Leak" in p["name"])
        self.assertTrue(re.search(tag_leak_item["pattern"], "伏笔道具【GUN-003：太上剑宗绝密残篇】"))
        self.assertTrue(re.search(tag_leak_item["pattern"], "触发MIS-001误会"))
        self.assertTrue(re.search(tag_leak_item["pattern"], "进入Stage 1心智阶段"))
        self.assertFalse(re.search(tag_leak_item["pattern"], "陆知白收起手中的竹丝扫帚"))

    def test_semantic_redundancy_detection(self):
        lines = [
            "黑衣人吓瘫在地上，双腿抖若筛糠。",
            "他面无人色，牙关剧烈打战，魂飞魄散。"
        ]
        slices = detect_semantic_redundancy(lines, window_lines=2)
        self.assertGreaterEqual(len(slices), 1)
        self.assertEqual(slices[0]["cluster_name"], "恐惧与瘫软同义堆砌")

    def test_unsupervised_burstiness(self):
        lines = [
            "陆知白端起茶碗，陆知白微微一笑，陆知白缓缓站起身来。"
        ]
        bursts = unsupervised_burstiness_slices(lines, window_size=200, min_repeat=3)
        grams = [b["gram"] for b in bursts]
        self.assertIn("陆知白", grams)

if __name__ == "__main__":
    unittest.main()
