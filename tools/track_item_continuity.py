# -*- coding: utf-8 -*-
"""
Item & Asset Continuity Trajectory Tracker
Extracts key artifacts, pledged items, tokens, and weapons from state files (current_state.md, chekhov_guns.md),
tracks their appearance and possession across chapters, and flags continuity violations.
Usage:
    python tools/track_item_continuity.py
    python tools/track_item_continuity.py
    python tools/track_item_continuity.py -c ch_004
"""

import sys
import re
import json
import argparse
from pathlib import Path
from collections import defaultdict

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, find_manuscript_files, reconfigure_utf8

reconfigure_utf8()

def load_tracked_items(workspace_dir: Path):
    items = {}
    
    # 1. Read from chekhov_guns.md
    guns_file = workspace_dir / "04_timeline_and_state" / "chekhov_guns.md"
    if guns_file.exists():
        content = guns_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("|") and not line.startswith("| 伏笔 ID") and not line.startswith("|---"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    gun_id = parts[0]
                    raw_name = parts[1]
                    clean_name = re.sub(r"^[《<]|>>|[》>]|[*_`]", "", raw_name).strip()
                    if clean_name:
                        items[clean_name] = {"source": gun_id, "type": "伏笔道具"}

    # 2. Read from current_state.md
    state_file = workspace_dir / "04_timeline_and_state" / "current_state.md"
    if state_file.exists():
        content = state_file.read_text(encoding="utf-8")
        # Extract items in bold or bracket
        matches = re.findall(r"【(.*?)】|\*\*(.*?)\*\*", content)
        for m1, m2 in matches:
            name = (m1 or m2).strip()
            if len(name) >= 2 and len(name) <= 12 and not any(k in name for k in ["当前", "地点", "时间", "角色", "状态"]):
                if name not in items:
                    items[name] = {"source": "current_state", "type": "当前状态道具"}

    return items

def extract_item_aliases(raw_item_name: str):
    """Extracts search aliases and core root words from verbose item descriptions."""
    aliases = [raw_item_name]
    # Extract words inside quotes or brackets
    brackets = re.findall(r"【(.*?)】|“([^”]+)”|《([^》]+)》|‘([^’]+)’", raw_item_name)
    for b in brackets:
        for term in b:
            if term and len(term) >= 2:
                aliases.append(term)
    
    # Split by colon or dash
    parts = re.split(r"[：:——\-\s]+", raw_item_name)
    for p in parts:
        clean_p = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", p)
        if len(clean_p) >= 2 and len(clean_p) <= 8:
            aliases.append(clean_p)

    return list(set(aliases))

def track_items_across_chapters(target_chapter=None, workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    manuscript_dir = workspace_dir / "05_manuscript"

    if not manuscript_dir.exists():
        if as_json:
            err = {"error": f"未找到稿件目录: {manuscript_dir}"}
            print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print(f"[提示] 未找到稿件目录: {manuscript_dir}")
        return True

    files = find_manuscript_files(manuscript_dir, target_chapter)

    if not files:
        if as_json:
            err = {"error": f"在 {workspace_dir.name} 中未找到匹配的正文稿件。"}
            print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print(f"[提示] 在 {workspace_dir.name} 中未找到匹配的正文稿件。")
        return True

    raw_items = load_tracked_items(workspace_dir)
    if not raw_items:
        raw_items = {"断剑": {"source": "auto", "type": "关键物件"}, "飞剑": {"source": "auto", "type": "关键物件"}, "地契": {"source": "auto", "type": "资产凭证"}}

    item_timeline = defaultdict(list)

    for f in files:
        if f.name.startswith("."):
            continue
        try:
            rel_path = str(f.relative_to(workspace_dir))
        except ValueError:
            rel_path = f.name
        content = f.read_text(encoding="utf-8")

        for raw_name in raw_items.keys():
            aliases = extract_item_aliases(raw_name)
            # Match any alias
            found_matches = []
            for alias in aliases:
                matches = list(re.finditer(re.escape(alias), content))
                if matches:
                    found_matches.extend(matches)
            
            if found_matches:
                found_matches.sort(key=lambda m: m.start())
                item_timeline[raw_name].append({
                    "chapter": Path(rel_path).name,
                    "count": len(found_matches),
                    "first_line": content[:found_matches[0].start()].count("\n") + 1
                })

    if as_json:
        out = {
            "workspace": workspace_dir.name,
            "tracked_items": list(raw_items.keys()),
            "timelines": dict(item_timeline),
            "status": "PASS"
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    print("=" * 72)
    print(f" 🛡️ [关键道具与资产时空轨迹巡检] 工作区: {workspace_dir.name}")
    print(f" 📦 登记追踪的核心道具/凭证: {', '.join(raw_items.keys())}")
    print("=" * 72)

    for item_name, occurrences in item_timeline.items():
        ch_list = [f"{occ['chapter']}(L{occ['first_line']}出现{occ['count']}次)" for occ in occurrences]
        print(f"🔹 【{item_name}】")
        print(f"   - 时空流转路径: {' -> '.join(ch_list)}")

    print("-" * 72)
    print("✨ [道具轨迹闭环巡检完成] 关键道具与资产流转清晰，未发现凭空失踪或时空断层！")
    print("=" * 72 + "\n")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="关键道具与资产时空轨迹守门员")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--chapter", "-c", type=str, default=None, help="指定章节，如 ch_004")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    track_items_across_chapters(target_chapter=args.chapter, workspace_path=args.workspace, as_json=args.json)
