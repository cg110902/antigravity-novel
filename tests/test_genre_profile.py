# -*- coding: utf-8 -*-
"""
Unit tests for P3-4 genre profiles (tools/genre_profile.py + integration).
- fuzzy genre matching
- builtin profiles complete + baseline sane
- workspace profile overrides builtin (manual tuning respected)
- init installs matching profile
- quality_radar / scheduler read profile windows

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
import genre_profile as gp  # noqa: E402


def _mk_ws(genre="通用题材"):
    tmp = Path(tempfile.mkdtemp(prefix="novel_genre_"))
    ws = tmp / "ws"
    init_novel(workspace_path=str(ws), genre=genre, title="题材测试", protagonist="主角")
    return tmp, ws


class TestGenreMatching(unittest.TestCase):
    def test_known_genres_match(self):
        cases = {
            "科幻机甲 / 星际": "scifi",
            "玄幻脑洞/系统/模拟器/仙武穿越": "xuanhuan",
            "硬核悬疑推理": "mystery",
            "都市异能商战": "urban",
            "规则怪谈无限流": "rulebound",
            "历史架空种田权谋": "history",
        }
        for text, expect in cases.items():
            self.assertEqual(gp.match_genre(text), expect, msg=f"{text} -> {expect}")

    def test_unknown_falls_back_to_generic(self):
        self.assertEqual(gp.match_genre("随便什么奇怪题材"), "generic")
        self.assertEqual(gp.match_genre(""), "generic")

    def test_all_builtin_profiles_load_complete(self):
        ids = [it["id"] for it in gp.list_builtin_profiles()]
        for expect in ("generic", "xuanhuan", "urban", "scifi", "mystery", "history", "rulebound"):
            self.assertIn(expect, ids)
        for it in gp.list_builtin_profiles():
            prof = gp.load_builtin(it["id"])
            # 通用字段必须齐全（深合后）
            self.assertIn("ratio_baseline", prof)
            self.assertIn("stall_window", prof)
            self.assertIn("word_count", prof)
            self.assertIn("director_notes", prof)
            self.assertIsInstance(prof["extra_ticks"], list)


class TestWorkspaceProfile(unittest.TestCase):
    def tearDown(self):
        # tmp dirs cleaned per-test
        for attr in ("tmp",):
            d = getattr(self, attr, None)
            if d:
                shutil.rmtree(d, ignore_errors=True)

    def test_init_installs_matching_profile(self):
        self.tmp, ws = _mk_ws("科幻机甲 / 末世")
        wp = ws / gp.WORKSPACE_PROFILE
        self.assertTrue(wp.exists())
        data = json.loads(wp.read_text(encoding="utf-8"))
        self.assertEqual(data["id"], "scifi")

    def test_manual_tuning_respected(self):
        self.tmp, ws = _mk_ws("玄幻仙侠")
        wp = ws / gp.WORKSPACE_PROFILE
        data = json.loads(wp.read_text(encoding="utf-8"))
        data["stall_window"] = 9
        data["ratio_baseline"]["dialogue"] = [5, 10]
        wp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        resolved = gp.resolve_genre_profile(ws)
        self.assertEqual(resolved["stall_window"], 9)
        self.assertEqual(resolved["ratio_baseline"]["dialogue"], [5, 10])
        # 其它字段仍来自该题材档案
        self.assertEqual(resolved["id"], "xuanhuan")

    def test_resolve_falls_back_to_config_genre(self):
        self.tmp, ws = _mk_ws("悬疑推理惊悚")
        # 删除工作区 profile，模拟只有 config 题材
        (ws / gp.WORKSPACE_PROFILE).unlink()
        resolved = gp.resolve_genre_profile(ws)
        self.assertEqual(resolved["id"], "mystery")
        self.assertEqual(resolved["stall_window"], 2)  # 悬疑更紧


class TestProfileIntegration(unittest.TestCase):
    def tearDown(self):
        d = getattr(self, "tmp", None)
        if d:
            shutil.rmtree(d, ignore_errors=True)

    def test_quality_radar_uses_profile_stall_window(self):
        import quality_radar as qr
        self.tmp, ws = _mk_ws("规则怪谈 / 无限流")  # stall_window=2
        fin = ws / "05_manuscript/vol_01/finalized"
        fin.mkdir(parents=True, exist_ok=True)
        desc = "天色阴沉，街道空旷，风吹动落叶，屋里光线昏暗，桌椅陈旧，空气有霉味。"
        for n in (1, 2):
            (fin / f"ch_{n:03d}.md").write_text(f"# 第{n}章\n\n{desc*6}\n", encoding="utf-8")
        rep = qr.detect_stall(ws)
        self.assertEqual(rep["window"], 2)
        self.assertTrue(rep["stalled"], msg="规则怪谈 2 章无变更应判塌中段")

    def test_scheduler_uses_profile_windows(self):
        import foreshadow_scheduler as fs
        self.tmp, ws = _mk_ws("悬疑推理")  # remind_lead=4
        guns = ("# 契诃夫之枪\n\n"
                "| 伏笔 ID | 名称 | 埋设 | 状态 | 预定引爆 | 规划 |\n"
                "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                "| **GUN-001** | 《关键物证》 | 第 1 章 | **Planted** | 第 6 章 | 指认凶手 |\n")
        (ws / "04_timeline_and_state/chekhov_guns.md").write_text(guns, encoding="utf-8")
        # 当前第 2 章，距引爆 4 章 -> 悬疑 lead=4 应触发回唤（通用 lead=3 不会）
        sched = fs.schedule(ws, 2)
        remind_ids = [g["id"] for g in sched["remind_soon"]]
        self.assertIn("GUN-001", remind_ids)


if __name__ == "__main__":
    unittest.main()
