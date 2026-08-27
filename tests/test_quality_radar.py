# -*- coding: utf-8 -*-
"""
Unit tests for the P2 quality radar (tools/quality_radar.py) and
foreshadow scheduler (tools/foreshadow_scheduler.py).
- stall / water-filling detection
- golden ratio 3-axis gate
- style distillation + single-chapter deviation
- foreshadow scheduler: detonate / remind / dormant / longline

All in throwaway temp workspaces; never touches novel_workspace/.
"""

import sys
import shutil
import tempfile
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "tools"))

from init_new_novel import init_novel  # noqa: E402
import quality_radar as qr  # noqa: E402
import foreshadow_scheduler as fs  # noqa: E402


def _mk_ws():
    tmp = Path(tempfile.mkdtemp(prefix="novel_p2_"))
    ws = tmp / "ws"
    init_novel(workspace_path=str(ws))
    return tmp, ws


def _write_ch(ws, num, body, title=None):
    d = ws / "05_manuscript" / "vol_01" / "finalized"
    d.mkdir(parents=True, exist_ok=True)
    t = title or f"第{num}章"
    (d / f"ch_{num:03d}.md").write_text(f"# 第{num}章 {t}\n\n{body}\n", encoding="utf-8")


GOOD = ("陈昂走进黑市后街，天空灰沉沉的，风卷起废报纸，墙边堆着锈铁桶。\n\n"
        "“你就是那个技工？”老周眯着眼问。\n\n"
        "“我要读取这块芯片。”陈昂把芯片拍在桌上。\n\n"
        "老周犹豫片刻：“风声很紧，铁壁公司在查这个。”\n\n"
        "陈昂猛地起身，一把抓住老周手腕，把水票推过去。老周终于点头。交易达成，陈昂转身就走。\n")
DESC = ("天空的颜色层层叠叠，灰云白云交织。远处群山连绵，河流在阳光下泛着微光。"
        "风吹过树梢，花草摇曳，空气里弥漫泥土气味。街道两旁建筑斑驳，墙壁爬满藤蔓。"
        "阳光洒在地面，光影交错，尘埃在光柱里缓缓浮动。")


class TestStallDetector(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = _mk_ws()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_stall_when_all_chapters_have_proposals(self):
        for n in (1, 2, 3):
            _write_ch(self.ws, n, GOOD)
        # 每章都有 processed 提案
        proc = self.ws / "04_timeline_and_state/state_inbox/processed"
        proc.mkdir(parents=True, exist_ok=True)
        import json
        for n in (1, 2, 3):
            (proc / f"ch_{n:03d}.json").write_text(json.dumps({
                "schema": "novel-studio.state-mutation/v1",
                "chapter": f"ch_{n:03d}",
                "current_state": {"location": f"地点{n}"},
            }), encoding="utf-8")
        rep = qr.detect_stall(self.ws, stall_window=3)
        self.assertFalse(rep["stalled"], msg=str(rep["stall_runs"]))

    def test_stall_flagged_for_consecutive_no_change(self):
        for n in (1, 2, 3, 4):
            _write_ch(self.ws, n, DESC)
        rep = qr.detect_stall(self.ws, stall_window=3)
        self.assertTrue(rep["stalled"])
        self.assertTrue(any(r["count"] >= 3 for r in rep["stall_runs"]))

    def test_short_novel_not_judged(self):
        _write_ch(self.ws, 1, GOOD)
        rep = qr.detect_stall(self.ws, stall_window=3)
        self.assertFalse(rep["stalled"])
        self.assertIn("note", rep)


class TestGoldenRatio(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = _mk_ws()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_balanced_chapter_scores_high(self):
        _write_ch(self.ws, 1, GOOD)
        rep = qr.golden_ratio_gate(self.ws, chapter="ch_001")
        ch = rep["chapters"][0]
        self.assertGreaterEqual(ch["score"], 80, msg=str(ch["warnings"]))
        self.assertGreater(ch["ratio"]["dialogue"], 10)
        self.assertGreater(ch["ratio"]["action"], ch["ratio"]["describe"])

    def test_pure_description_flags_waterfowl(self):
        _write_ch(self.ws, 2, DESC * 2)
        rep = qr.golden_ratio_gate(self.ws, chapter="ch_002")
        ch = rep["chapters"][0]
        self.assertLess(ch["score"], 80)
        joined = " ".join(ch["warnings"])
        self.assertIn("描写", joined)

    def test_ratio_sums_to_roughly_100(self):
        _write_ch(self.ws, 1, GOOD)
        r = qr.classify_ratio(GOOD)
        total = r["dialogue"] + r["action"] + r["describe"]
        self.assertAlmostEqual(total, 100, delta=2)


class TestStyleDistillation(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = _mk_ws()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fingerprint_build_and_reuse(self):
        for n in (1, 2, 3):
            _write_ch(self.ws, n, GOOD)
        fp = qr.distill_style(self.ws)
        self.assertEqual(fp["chapter_count"], 3)
        self.assertIn("sentence_len", fp["features"])
        self.assertTrue((self.ws / qr.STYLE_FINGERPRINT_FILE).exists())

    def test_tick_frequency_detected(self):
        ticky = GOOD + "他笑了笑，又似笑非笑地笑了笑。嘴角微勾，瞳孔骤缩。" * 2
        _write_ch(self.ws, 1, ticky)
        feat = qr._style_features(ticky)
        # 口癖应被统计到
        self.assertTrue(any("笑了笑" in t for t in feat["tick_per_1k"]))

    def test_chapter_comparison_flags_outlier(self):
        # 全书都是正常配比
        for n in (1, 2, 3, 4):
            _write_ch(self.ws, n, GOOD)
        qr.distill_style(self.ws)  # 建指纹
        # 第 5 章是纯描写异类
        _write_ch(self.ws, 5, DESC * 3)
        out = qr.distill_style(self.ws, chapter="ch_005")
        comp = out["comparison"]
        self.assertLess(comp["style_score"], 100)
        self.assertTrue(comp["deviations"])


class TestForeshadowScheduler(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = _mk_ws()
        guns = (
            "# 契诃夫之枪\n\n"
            "| 伏笔 ID | 伏笔名称 / 关键物件 | 埋设章节 | 当前状态 | 预定引爆章节 | 闭环兑现规划 |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            "| **GUN-001** | 《背叛证据》 | 第 2 章 | **Planted** | 第 5 章 | 反制老周 |\n"
            "| **GUN-002** | 《公司账本》 | 第 1 章 | **Planted** | 第 9 章 | 揭黑幕 |\n"
            "| **GUN-003** | 《童年旧照片》 | 第 1 章 | **Planted** | 第 20 章 | 身世之谜 |\n"
            "| **GUN-004** | 《神秘数据芯片》 | 第 1 章 | **Active** | 全局贯穿 | 终极悬念 |\n"
        )
        (self.ws / "04_timeline_and_state/chekhov_guns.md").write_text(guns, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_detonate_overdue_and_remind(self):
        sched = fs.schedule(self.ws, 8)
        det_ids = [g["id"] for g in sched["detonate_now"]]
        self.assertIn("GUN-001", det_ids)  # target 5, 已超期
        remind_ids = [g["id"] for g in sched["remind_soon"]]
        self.assertIn("GUN-002", remind_ids)  # target 9, 剩 1 章

    def test_longline_not_flagged_dormant(self):
        sched = fs.schedule(self.ws, 8)
        dormant_ids = [g["id"] for g in sched["dormant_wakeup"]]
        long_ids = [g["id"] for g in sched["longline_maintain"]]
        self.assertIn("GUN-004", long_ids)
        self.assertNotIn("GUN-004", dormant_ids)  # 长线不重复进沉睡
        # GUN-003 有明确目标(20)且久未提及 -> 沉睡
        self.assertIn("GUN-003", dormant_ids)

    def test_resolved_guns_excluded(self):
        # 把 GUN-001 标为已回收
        f = self.ws / "04_timeline_and_state/chekhov_guns.md"
        f.write_text(f.read_text(encoding="utf-8").replace("**Planted** | 第 5 章",
                                                          "**Resolved** | 第 5 章"),
                     encoding="utf-8")
        sched = fs.schedule(self.ws, 8)
        det_ids = [g["id"] for g in sched["detonate_now"]]
        self.assertNotIn("GUN-001", det_ids)


if __name__ == "__main__":
    unittest.main()
