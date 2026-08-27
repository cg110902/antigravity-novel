# -*- coding: utf-8 -*-
"""
Agent-First Dynamic Context Packager
Packages all required context for drafting a chapter in a single call:
- Current State Machine (current_state.md)
- Active Chekhov Guns & Misunderstandings
- Previous Chapter Finalized Ending (Emotional warmth & voice continuity)
- Target Chapter Beats Outline
- Relevant Character Profile Cards
Saves 5-6 separate tool view roundtrips and protects context window hygiene.
Usage:
    python tools/package_context.py -c ch_004
    python tools/package_context.py -c ch_004 --json
"""

import sys
import re
import json
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import (
    resolve_workspace, natural_chapter_sort_key, find_manuscript_files,
    reconfigure_utf8, file_matches_chapter, chapter_token_to_num, has_placeholder
)

reconfigure_utf8()

def package_context_for_chapter(target_chapter_str: str, workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    
    package = {
        "workspace": workspace_dir.name,
        "target_chapter": target_chapter_str or "next_chapter",
        "current_state": "",
        "character_growth_arcs": "",
        "active_chekhov_guns": [],
        "active_misunderstandings": [],
        "previous_chapter_ending": "",
        "target_beats": "",
        "relevant_character_profiles": {}
    }

    # 1. Load Current State
    state_file = workspace_dir / "04_timeline_and_state" / "current_state.md"
    if state_file.exists():
        package["current_state"] = state_file.read_text(encoding="utf-8").strip()

    # 1.5 Load Character Growth Arcs (Mindset Evolution)
    growth_file = workspace_dir / "04_timeline_and_state" / "character_growth_arcs.md"
    if growth_file.exists():
        package["character_growth_arcs"] = growth_file.read_text(encoding="utf-8").strip()

    # 1.6 Load Quantitative Resource Pools & Economy Ledger
    package["resource_pools"] = {}
    econ_file = workspace_dir / "04_timeline_and_state" / "economy_ledger.json"
    if econ_file.exists():
        try:
            econ_data = json.loads(econ_file.read_text(encoding="utf-8"))
            if "resource_pools" in econ_data:
                package["resource_pools"] = econ_data["resource_pools"]
            elif "current_balance" in econ_data:
                package["resource_pools"] = {
                    "currency": {
                        "name": "货币结余",
                        "unit": "单位",
                        "current": econ_data.get("current_balance", 0)
                    }
                }
        except Exception:
            pass

    # 2. Load Active Guns
    guns_file = workspace_dir / "04_timeline_and_state" / "chekhov_guns.md"
    if guns_file.exists():
        content = guns_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if ("Planted" in line or "Reminded" in line or "Active" in line) and not line.startswith("| 伏笔 ID") and not line.startswith("|---"):
                if has_placeholder(line):
                    continue  # 母版示例占位行
                package["active_chekhov_guns"].append(line.strip())

    # 3. Load Active Misunderstandings
    mis_file = workspace_dir / "04_timeline_and_state" / "misunderstandings.md"
    if mis_file.exists():
        content = mis_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "MIS-" in line and not line.startswith("| ID") and not line.startswith("|---"):
                if has_placeholder(line):
                    continue  # 母版示例占位行
                package["active_misunderstandings"].append(line.strip())

    # 4. Find Previous Chapter Ending
    manuscript_dir = workspace_dir / "05_manuscript"
    if manuscript_dir.exists():
        finalized_files = sorted(list(manuscript_dir.glob("**/finalized/ch_*.md")), key=natural_chapter_sort_key)
        if finalized_files:
            # If target_chapter is specified, find the one before it
            prev_file = None
            if target_chapter_str:
                target_num = chapter_token_to_num(target_chapter_str)
                if target_num is not None:
                    for f in finalized_files:
                        if file_matches_chapter(f, target_num - 1):
                            prev_file = f
                            break
            if not prev_file:
                prev_file = finalized_files[-1]

            if prev_file:
                prev_text = prev_file.read_text(encoding="utf-8").strip()
                # Get last 1000 chars for continuity
                package["previous_chapter_ending"] = f"【上一章（{prev_file.name}）末尾余温】:\n" + prev_text[-1000:].strip()

    # 5. Load Target Chapter Beats (boundary-safe: ch_001 won't match ch_010)
    beats_dir = workspace_dir / "03_outlines"
    if beats_dir.exists() and target_chapter_str:
        beat_files = [
            f for f in beats_dir.glob("**/*.md")
            if "beats" in str(f).replace("\\", "/") and file_matches_chapter(f, target_chapter_str)
        ]
        if beat_files:
            package["target_beats"] = sorted(beat_files)[0].read_text(encoding="utf-8").strip()

    # 6. Load Relevant Character Cards
    profiles_dir = workspace_dir / "02_characters" / "profiles"
    if profiles_dir.exists():
        for pfile in profiles_dir.glob("*.md"):
            if not pfile.name.startswith("."):
                p_text = pfile.read_text(encoding="utf-8").strip()
                # Extract real character name and aliases
                name_match = re.search(r"#+\s*(?:角色(?:姓名)?[：:]\s*)?([^\n(（\s#*]+)", p_text)
                char_real_name = name_match.group(1).strip() if name_match else ""
                char_real_name = re.sub(r"[*_`#]", "", char_real_name)
                
                is_protagonist = "protagonist" in pfile.stem.lower() or "主角" in p_text
                
                # Check if character is mentioned in target beats, state, or is protagonist
                search_scope = (package["target_beats"] or "") + "\n" + (package["current_state"] or "")
                
                matched = False
                if char_real_name and len(char_real_name) >= 2 and char_real_name in search_scope:
                    matched = True
                elif pfile.stem in search_scope or pfile.name in search_scope:
                    matched = True
                elif not package["target_beats"] and is_protagonist:
                    matched = True
                elif is_protagonist and len(package["relevant_character_profiles"]) == 0:
                    matched = True
                    
                if matched:
                    display_key = char_real_name if char_real_name else pfile.stem
                    package["relevant_character_profiles"][display_key] = p_text

    # 7. Compute High-Priority Story Alerts (Ebbinghaus Decay + Urgent DAG Guns)
    story_alerts = []
    
    # Check decaying characters
    try:
        from track_character_decay import track_memory_decay
        decay_data = track_memory_decay(workspace_path=str(workspace_dir), as_json=True, print_output=False)
        if decay_data and "warnings" in decay_data:
            for w in decay_data["warnings"]:
                story_alerts.append(f"🧠 [角色掉线唤醒提醒] {w}")
    except Exception:
        pass

    # Check urgent Chekhov guns
    try:
        from audit_plot_dag import audit_plot_dag
        dag_data = audit_plot_dag(workspace_path=str(workspace_dir), as_json=True, print_output=False)
        if dag_data and "urgent_guns" in dag_data:
            for ug in dag_data["urgent_guns"]:
                story_alerts.append(f"🕸️ [伏笔临界到期提醒] {ug}")
    except Exception:
        pass

    package["high_priority_story_alerts"] = story_alerts

    if as_json:
        print(json.dumps(package, ensure_ascii=False, indent=2))
        return package

    # Render Clean Markdown Output for Agent Consumption
    print("═" * 72)
    print(f" 📦 [动态创作上下文极速打包] 工作区: {package['workspace']} | 目标: {package['target_chapter']}")
    print("═" * 72)

    if package["high_priority_story_alerts"]:
        print("\n🚨 【高优先级剧情导航预警 (角色唤醒 & 临界伏笔)】:")
        for al in package["high_priority_story_alerts"]:
            print(f"   👉 {al}")
        print("─" * 72)
    
    if package["target_beats"]:
        print("\n## 🎯 本章细纲与 Beats:\n" + package["target_beats"])
        print("─" * 72)

    if package["current_state"]:
        print("\n## 📍 当前实时状态机:\n" + package["current_state"])
        print("─" * 72)

    if package["character_growth_arcs"]:
        print("\n## 🧠 核心角色心智演进台账 (Growth Arcs):\n" + package["character_growth_arcs"])
        print("─" * 72)

    if package.get("resource_pools"):
        print("\n## 💰 核心资产与量化资源池 (Resource Pools):")
        for p_id, p_info in package["resource_pools"].items():
            name = p_info.get("name", p_id)
            cur = p_info.get("current", 0)
            unit = p_info.get("unit", "")
            print(f"   - {name}: {cur} {unit}".strip())
        print("─" * 72)

    if package["active_chekhov_guns"]:
        print("\n## 🎯 活跃契诃夫之枪 (伏笔池):\n" + "\n".join(package["active_chekhov_guns"]))
        print("─" * 72)

    if package["active_misunderstandings"]:
        print("\n## 🎭 活跃误会与信息差台账:\n" + "\n".join(package["active_misunderstandings"]))
        print("─" * 72)

    if package["previous_chapter_ending"]:
        print("\n## 🔗 上一章情绪余温衔接:\n" + package["previous_chapter_ending"])
        print("─" * 72)

    if package["relevant_character_profiles"]:
        print("\n## 👤 本章涉及核心人物卡:")
        for cname, ptext in package["relevant_character_profiles"].items():
            print(f"\n### 【{cname}】\n" + ptext)

    print("\n═" * 72)
    print(" ✨ [上下文打包就绪] 1 次调用装载全量语境，算力全量留给情节起草！")
    print("═" * 72 + "\n")
    return package

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent-First 动态创作上下文极速打包器")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--chapter", "-c", type=str, default=None, help="目标章节序号，例如: ch_004")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    package_context_for_chapter(target_chapter_str=args.chapter, workspace_path=args.workspace, as_json=args.json)
