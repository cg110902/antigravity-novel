# -*- coding: utf-8 -*-
"""
Genre Profile — P3-4 题材 Profile 配置化（全题材自适应的最后一公里）。

不同题材的"好书阈值"本就不同：玄幻靠境界推进与战斗、悬疑靠信息差与线索公平、
都市靠世情对白、科幻靠设定自洽…… 此前这些阈值/词表/节奏全写死在通用代码里，
本模块把它们抽成随书走的「题材档案」：

- 内置档案：tools/genre_profiles/<id>.json（17 种题材 + generic 兜底）
- 随书覆盖：<workspace>/00_meta/genre_profile.json（init 时按题材拷贝，可人工微调，优先于内置）
- 全链路读取：quality_radar（配比基线/口癖/塌中段窗口）、foreshadow_scheduler（提醒窗口）、
  pack（注入 director_notes 题材指导）、novel_utils（词表/聚类/白名单动态加载）统一从 resolve_genre_profile() 取值。

全部纯 Python 标准库（json），零第三方依赖、零 Token。

用法：
    python tools/genre_profile.py                 # 查看当前工作区解析到的题材档案
    python tools/genre_profile.py --list          # 列出所有内置题材
    python tools/genre_profile.py --genre "科幻机甲" --json
"""

import sys
import re
import json
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, reconfigure_utf8, load_studio_config

reconfigure_utf8()

PROFILE_SCHEMA = "novel-studio.genre-profile/v2"
WORKSPACE_PROFILE = "00_meta/genre_profile.json"

# 题材模糊匹配关键词（命中即选该内置档案）
# 注意：跨题材通用词（如"系统""模拟器"）在多个题材中都出现，靠命中总数区分
_GENRE_KEYWORDS = {
    "xuanhuan":   ["玄幻", "仙侠", "修仙", "修真", "仙武", "异界", "大陆", "宗门", "境界", "灵气", "渡劫", "金丹", "元婴"],
    "wuxia":      ["武侠", "江湖", "武林", "门派", "内功", "轻功", "剑客", "镖局", "丐帮", "少林", "武当", "真气", "点穴"],
    "urban":      ["都市", "异能", "职场", "商战", "娱乐", "现代", "重生都市", "神豪", "系统", "模拟器", "都市异能"],
    "scifi":      ["科幻", "机甲", "星际", "赛博", "末世", "废土", "未来", "科技", "太空", "进化", "义体", "星舰"],
    "mystery":    ["悬疑", "推理", "侦探", "惊悚", "犯罪", "破案", "本格", "法医", "刑警"],
    "horror":     ["恐怖", "克苏鲁", "鬼故事", "灵异", "怨灵", "凶宅", "心理恐怖", "怪谈"],
    "history":    ["历史", "架空", "穿越古代", "王朝", "种田", "权谋", "历史架空", "古代", "贞观", "大明", "大清"],
    "rulebound":  ["规则怪谈", "规则", "副本", "求生", "SCP", "异常"],
    "infinite":   ["无限流", "无限恐怖", "主神", "轮回", "任务世界", "轮回空间"],
    "romance":    ["言情", "纯爱", "恋爱", "甜宠", "虐恋", "霸总", "总裁", "古言", "现言", "耽美", "百合", "婚恋"],
    "gaming":     ["游戏", "电竞", "网游", "虚拟网游", "全息游戏", "电竞选手", "战队", "直播", "攻略", "副本开荒"],
    "sports":     ["体育", "竞技", "篮球", "足球", "网球", "赛车", "运动", "奥运", "冠军", "田径", "游泳"],
    "military":   ["军事", "战争", "军旅", "特种兵", "战场", "战役", "军装", "部队", "亮剑", "谍战"],
    "lightnovel": ["轻小说", "轻文", "异世界", "转生", "穿越异世界", "冒险者", "公会", "魔王", "勇者", "魔法学院"],
    "realism":    ["现实主义", "年代", "年代文", "知青", "改革开放", "市井", "民生", "纪实", "乡土", "工厂"],
    "iyashikei":  ["治愈", "日常", "治愈系", "慢生活", "田园", "美食", "萌宠", "温馨", "日常系", "百合日常"],
}

# 通用兜底默认（v2 扩展：基调/状态组件/词表全部可由题材覆盖）
GENERIC_PROFILE = {
    "schema": PROFILE_SCHEMA,
    "id": "generic",
    "label": "全题材通用自适应",
    "creation_goal": "commercial",  # commercial / literary / experimental
    "word_count": {"min": 1800, "recommended": 3000, "max": 5000},
    "ratio_baseline": {"dialogue": [20, 55], "action": [20, 55], "describe": [10, 40]},
    "tone_policy": {
        "mode": "adaptive",  # adaptive / bright_preferred / dark_preferred / mixed
        "bright_allowed": True,
        "dark_allowed": True,
        "note": "通用基线无基调禁令。明快/阴暗/压抑/冷峻完全由题材与具体场景决定，AI 应根据故事心流自由选择最贴切的基调。"
    },
    "state_components": ["current_state", "chekhov_guns", "timeline", "character_growth_arcs"],
    "stall_window": 3,
    "scheduler": {"remind_lead": 3, "dormant_gap": 5, "longline_interval": [8, 12]},
    "dialogue_floor": 10,
    "describe_ceiling": 50,
    "extra_ticks": [],
    "cliche_patterns": [],
    "cliffhanger_keywords": [],
    "semantic_clusters": [],
    "quantity_whitelist": [],
    "ending_style": "adaptive",  # adaptive / strong_hook / emotional_resonance / open_ending / quiet_close
    "pov_default": "third_limited",  # third_limited / first / omniscient / multiple_pov
    "combat_heavy": False,  # 是否为战斗密集型题材（影响战斗套路检测是否启用）
    "economy_required": False,  # 是否必须有经济体系
    "director_notes": "通用自适应基线：无题材特定禁令。基调、配比、断章风格、描写密度均由题材档案与具体场景决定，AI 应根据故事心流自由选择最贴切的表达方式。核心铁律仅保留五条：①限制视角不越界 ②信息差自洽 ③角色动机真实 ④前后因果一致 ⑤无工程标记外泄。",
}


def _builtin_dir() -> Path:
    return _tools_dir / "genre_profiles"


def list_builtin_profiles() -> list:
    d = _builtin_dir()
    out = []
    if d.exists():
        for p in sorted(d.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                out.append({"id": data.get("id", p.stem),
                            "label": data.get("label", p.stem),
                            "path": str(p)})
            except Exception:
                continue
    return out


def match_genre(genre_text: str) -> str:
    """把自由文本题材（如 '科幻机甲 / 末世'）模糊匹配到内置档案 id。"""
    if not genre_text:
        return "generic"
    best, best_hits = "generic", 0
    for gid, kws in _GENRE_KEYWORDS.items():
        hits = sum(1 for k in kws if k in genre_text)
        if hits > best_hits:
            best, best_hits = gid, hits
    return best


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并：override 覆盖 base（dict 深合，其余整体覆盖）。"""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_builtin(profile_id: str) -> dict:
    p = _builtin_dir() / f"{profile_id}.json"
    if p.exists():
        try:
            return _deep_merge(GENERIC_PROFILE, json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return dict(GENERIC_PROFILE)


def _read_workspace_genre(ws) -> str:
    """推断工作区题材：优先读随书的 project_bible.md「主类型」，
    其次回退仓库根 novel_config.yaml 的 default_genre。"""
    try:
        bible = Path(ws) / "00_meta" / "project_bible.md"
        if bible.exists():
            for line in bible.read_text(encoding="utf-8").splitlines():
                s = line.strip().lstrip("-*").strip()
                if not re.match(r"\*?\*?主类型\*?\*?\s*[：:]", s):
                    continue
                m = re.search(r"[：:]\s*(.+)$", s)
                if m:
                    val = m.group(1).strip().strip("*《》 ")
                    if val and "[" not in val and "如：" not in val:
                        return val
    except Exception:
        pass
    try:
        return (load_studio_config().get("project", {}) or {}).get("default_genre", "") or ""
    except Exception:
        return ""


def resolve_genre_profile(workspace=None) -> dict:
    """解析当前应使用的题材档案：
    1) 工作区 00_meta/genre_profile.json（随书、可人工微调，最高优先）；
    2) 按 novel_config.yaml 的 default_genre 匹配内置档案；
    3) generic 兜底。
    返回的 dict 始终包含全部通用字段（深合 GENERIC_PROFILE）。
    """
    profile = None
    try:
        ws = resolve_workspace(workspace)
        wp = ws / WORKSPACE_PROFILE
        if wp.exists():
            profile = json.loads(wp.read_text(encoding="utf-8"))
    except Exception:
        profile = None

    if not profile:
        genre = _read_workspace_genre(ws)
        gid = match_genre(genre)
        profile = load_builtin(gid)
        profile["matched_from"] = genre
        return profile

    # 工作区 profile：以其声明的 id 内置档案为底，再叠加工作区覆盖
    base = load_builtin(profile.get("id", "generic"))
    return _deep_merge(base, profile)


def install_profile_for_genre(workspace: Path, genre_text: str) -> Path:
    """init 时调用：按题材把内置档案拷贝到工作区 00_meta/genre_profile.json。
    已存在则不覆盖（保留人工微调）。返回写入路径。"""
    gid = match_genre(genre_text)
    data = load_builtin(gid)
    data["matched_genre"] = genre_text
    ws = Path(workspace)
    target = ws / WORKSPACE_PROFILE
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return target


def _main():
    ap = argparse.ArgumentParser(description="P3-4 题材 Profile 配置化（v2 全题材自适应）")
    ap.add_argument("--workspace", "-w", help="工作区路径")
    ap.add_argument("--list", action="store_true", help="列出所有内置题材档案")
    ap.add_argument("--genre", help="按题材文本解析（不读工作区）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if args.list:
        items = list_builtin_profiles()
        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
        else:
            print(f"内置题材档案（共 {len(items)} 种）：")
            for it in items:
                print(f"  - {it['id']:<14} {it['label']}")
        return

    if args.genre:
        gid = match_genre(args.genre)
        prof = load_builtin(gid)
        prof["matched_genre"] = args.genre
    else:
        ws = resolve_workspace(args.workspace)
        prof = resolve_genre_profile(ws)
        if args.json is False:
            print(f"📂 工作区: {ws.name}")

    if args.json:
        print(json.dumps(prof, ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print(f" 🎭 题材档案: {prof.get('label')} (id={prof.get('id')})")
        if prof.get("matched_genre") or prof.get("matched_from"):
            print(f"   匹配自: {prof.get('matched_genre') or prof.get('matched_from')}")
        print(f"   创作目标: {prof.get('creation_goal')} | 视角默认: {prof.get('pov_default')}")
        print(f"   基调策略: {prof.get('tone_policy', {}).get('mode')} (明快={prof.get('tone_policy', {}).get('bright_allowed')} 阴暗={prof.get('tone_policy', {}).get('dark_allowed')})")
        print("=" * 70)
        wc = prof.get("word_count", {})
        print(f" 字数：下限 {wc.get('min')} / 建议 {wc.get('recommended')} / 上限 {wc.get('max')}")
        rb = prof.get("ratio_baseline", {})
        print(f" 配比基线：对白 {rb.get('dialogue')} | 推进 {rb.get('action')} | 描写 {rb.get('describe')}")
        print(f" 塌中段窗口：{prof.get('stall_window')} 章 | 对白地板 {prof.get('dialogue_floor')}% | 描写天花板 {prof.get('describe_ceiling')}%")
        sc = prof.get("scheduler", {})
        print(f" 伏笔调度：回唤提前 {sc.get('remind_lead')} 章 / 沉睡 {sc.get('dormant_gap')} 章 / 长线周期 {sc.get('longline_interval')}")
        comps = prof.get("state_components", [])
        print(f" 状态组件：{', '.join(comps)}")
        if prof.get("extra_ticks"):
            print(f" 题材专属雷词：{', '.join(prof['extra_ticks'][:12])}")
        if prof.get("cliche_patterns"):
            print(f" 题材陈词模式：{len(prof['cliche_patterns'])} 组")
        if prof.get("cliffhanger_keywords"):
            print(f" 断章关键词：{len(prof['cliffhanger_keywords'])} 个")
        print(f"\n 📝 导演指导 (director_notes)：\n   {prof.get('director_notes','')}")


if __name__ == "__main__":
    _main()
