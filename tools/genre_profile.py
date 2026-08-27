# -*- coding: utf-8 -*-
"""
Genre Profile — P3-4 题材 Profile 配置化（全题材自适应的最后一公里）。

不同题材的"好书阈值"本就不同：玄幻靠境界推进与战斗、悬疑靠信息差与线索公平、
都市靠世情对白、科幻靠设定自洽…… 此前这些阈值/词表/节奏全写死在通用代码里，
本模块把它们抽成随书走的「题材档案」：

- 内置档案：tools/genre_profiles/<id>.json（generic/xuanhuan/urban/scifi/mystery/history/rulebound）
- 随书覆盖：<workspace>/00_meta/genre_profile.json（init 时按题材拷贝，可人工微调，优先于内置）
- 全链路读取：quality_radar（配比基线/口癖/塌中段窗口）、foreshadow_scheduler（提醒窗口）、
  pack（注入 director_notes 题材指导）统一从 resolve_genre_profile() 取值。

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

PROFILE_SCHEMA = "novel-studio.genre-profile/v1"
WORKSPACE_PROFILE = "00_meta/genre_profile.json"

# 题材模糊匹配关键词（命中即选该内置档案）
_GENRE_KEYWORDS = {
    "xuanhuan": ["玄幻", "仙侠", "修仙", "修真", "仙武", "系统", "模拟器", "异界", "大陆", "宗门", "境界"],
    "urban":    ["都市", "异能", "职场", "商战", "娱乐", "都市异能", "现代", "重生都市", "神豪"],
    "scifi":    ["科幻", "机甲", "星际", "赛博", "末世", "废土", "未来", "科技", "太空", "进化"],
    "mystery":  ["悬疑", "推理", "侦探", "惊悚", "犯罪", "破案", "本格"],
    "history":  ["历史", "架空", "穿越古代", "王朝", "种田", "权谋", "历史架空"],
    "rulebound": ["规则怪谈", "无限流", "怪谈", "规则", "副本", "求生", "恐怖"],
}

# 通用兜底默认（与既有代码常量一致，保证不引入 profile 时行为不变）
GENERIC_PROFILE = {
    "schema": PROFILE_SCHEMA,
    "id": "generic",
    "label": "全题材通用",
    "word_count": {"min": 2500, "recommended": 3200, "max": 5000},
    "ratio_baseline": {"dialogue": [30, 45], "action": [35, 55], "describe": [10, 30]},
    "stall_window": 3,
    "scheduler": {"remind_lead": 3, "dormant_gap": 5, "longline_interval": [8, 12]},
    "dialogue_floor": 20,       # 对白低于此（%）可能通篇旁白
    "describe_ceiling": 40,     # 描写高于此（%）疑似注水
    "extra_ticks": [],          # 题材专属口癖/高频雷词（叠加在通用口癖上）
    "director_notes": "遵循 4 大心流母则与黄金配比；对白讲人话、推进利落、断章有钩。",
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
    # 1) 工作区 bible（随书走，-w 指向外部目录也正确）。只认「主类型」标签行，
    #    避免命中"书名/题材"等含"题"字的其他行。
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
    # 2) 仓库 config 兜底
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
    ap = argparse.ArgumentParser(description="P3-4 题材 Profile 配置化")
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
            print("内置题材档案：")
            for it in items:
                print(f"  - {it['id']:<10} {it['label']}")
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
        print("=" * 70)
        wc = prof.get("word_count", {})
        print(f" 字数：下限 {wc.get('min')} / 建议 {wc.get('recommended')} / 上限 {wc.get('max')}")
        rb = prof.get("ratio_baseline", {})
        print(f" 配比基线：对白 {rb.get('dialogue')} | 推进 {rb.get('action')} | 描写 {rb.get('describe')}")
        print(f" 塌中段窗口：{prof.get('stall_window')} 章 | 对白地板 {prof.get('dialogue_floor')}% | 描写天花板 {prof.get('describe_ceiling')}%")
        sc = prof.get("scheduler", {})
        print(f" 伏笔调度：回唤提前 {sc.get('remind_lead')} 章 / 沉睡 {sc.get('dormant_gap')} 章 / 长线周期 {sc.get('longline_interval')}")
        if prof.get("extra_ticks"):
            print(f" 题材专属雷词：{', '.join(prof['extra_ticks'][:12])}")
        print(f"\n 📝 导演指导 (director_notes)：\n   {prof.get('director_notes','')}")


if __name__ == "__main__":
    _main()
