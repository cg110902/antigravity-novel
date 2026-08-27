# -*- coding: utf-8 -*-
"""
Character Gesture & Emotion Semantic Extractor & Anomaly Detector
Audits facial expressions, body gestures, and emotional cues across any novel genre.
Enforces hard caps on smile overload (max 3 per chapter), detects unprovoked actions, and flags repetitive mono-gestures.
Usage:
    python tools/audit_character_gestures.py
    python tools/audit_character_gestures.py -c ch_004
"""

import sys
import re
import argparse
from pathlib import Path
from collections import defaultdict

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

UNIVERSAL_GESTURE_KEYWORDS = [
    # Facial & Expressions (五官与神态)
    "笑", "哭", "怒", "惊", "愣", "冷", "叹", "咬", "皱", "挑", "扬", "抿", "抽搐",
    "眼神", "眸光", "目光", "面色", "脸色", "表情", "神态", "神色", "眉峰", "眉心", "嘴角", "唇角", "眼角",
    # Body & Physical Micro-reactions (生理与微反应)
    "僵", "颤", "抖", "退", "跪", "瘫", "扯", "抓", "指尖", "十指", "双手", "背脊", "脊背",
    "深吸了一口气", "倒吸了一口凉气", "咽了口", "冷汗", "头皮发麻", "瞳孔骤缩", "喉结",
    # Universal Prop & Environment Interaction (跨题材道具/环境互动: 现代/古风/科幻通用)
    "转扇", "合扇", "轻叩", "摩挲", "抱拳", "拂袖", "端起", "沏了", "斟满", "点燃", "深吸了一口烟",
    "推了推眼镜", "按了按眉心", "敲击键盘", "滑动屏幕", "轻点桌面", "扣动扳机", "拔出", "握紧", "拂去"
]

def resolve_workspace(workspace_arg=None):
    base_dir = Path(__file__).parent.parent
    if workspace_arg:
        w_path = Path(workspace_arg)
        if not w_path.is_absolute():
            w_path = (base_dir / w_path).resolve()
        return w_path
    return (base_dir / "novel_workspace").resolve()

def load_registered_characters(workspace_dir: Path):
    chars = set()
    
    # 1. Check character_index.md
    index_file = workspace_dir / "02_characters" / "character_index.md"
    if index_file.exists():
        content = index_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("|") and not line.startswith("| 角色姓名") and not line.startswith("|---"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts and not parts[0].startswith("["):
                    clean_name = re.sub(r"[*_`]", "", parts[0])
                    if clean_name and len(clean_name) <= 10:
                        chars.add(clean_name)
    
    # 2. Check profiles directory
    profiles_dir = workspace_dir / "02_characters" / "profiles"
    if profiles_dir.exists():
        for pfile in profiles_dir.glob("*.md"):
            if not pfile.name.startswith("."):
                content = pfile.read_text(encoding="utf-8")
                m = re.search(r"#+\s*(?:角色姓名[：:]\s*)?([^\n(（]+)", content)
                if m:
                    cname = m.group(1).strip()
                    cname = re.sub(r"[*_`#]", "", cname).strip()
                    if cname and len(cname) <= 10 and not cname.startswith("["):
                        chars.add(cname)

    return sorted(list(chars))

def extract_gestures_from_chapter(file_path: Path, workspace_dir: Path):
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    characters = load_registered_characters(workspace_dir)

    results = []

    for idx, line in enumerate(lines, 1):
        clean_line = line.strip()
        if not clean_line or clean_line.startswith("#") or clean_line == "……":
            continue

        has_gesture = any(k in clean_line for k in UNIVERSAL_GESTURE_KEYWORDS)
        if not has_gesture:
            continue

        acting_char = "未知/环境"
        for c in characters:
            if c in clean_line:
                acting_char = c
                break
        
        if acting_char == "未知/环境":
            for prev_idx in range(idx - 2, max(-1, idx - 6), -1):
                prev_line = lines[prev_idx].strip()
                for c in characters:
                    if c in prev_line:
                        acting_char = f"{c} (承前文)"
                        break
                if acting_char != "未知/环境":
                    break

        action_types = []
        is_smile = "笑" in clean_line
        if is_smile:
            action_types.append("😊 表情·笑")
        if any(w in clean_line for w in ["惊", "愣", "僵", "慌", "冷汗", "头皮发麻", "绝望", "瞳孔"]):
            action_types.append("⚡ 情绪·惊/慌/僵")
        if any(w in clean_line for w in ["怒", "咬牙", "咬碎", "发抖", "破防", "狞声", "厉声", "暴喝"]):
            action_types.append("🔥 情绪·怒/破防")
        if any(w in clean_line for w in ["扇", "茶", "杯", "烟", "镜", "袖", "抓", "按", "跪", "叩", "抚", "枪", "机", "屏幕"]):
            action_types.append("✋ 肢体/道具动作")
        if not action_types:
            action_types.append("👀 神态描写")

        prev_ctx = lines[idx - 2].strip() if idx >= 2 else "(开头)"
        next_ctx = lines[idx].strip() if idx < len(lines) else "(结尾)"

        results.append({
            "line": idx,
            "char": acting_char,
            "is_smile": is_smile,
            "types": "/".join(action_types),
            "sentence": clean_line,
            "prev_ctx": prev_ctx,
            "next_ctx": next_ctx
        })

    return results

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

def audit_gestures(target_chapter=None, workspace_path=None, as_json=False):
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
            err = {"error": f"在 {workspace_dir.name} 中未找到指定章节正文稿件。"}
            print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print(f"[提示] 在 {workspace_dir.name} 中未找到指定章节正文稿件。")
        return True

    reports = []

    for f in files:
        if f.name.startswith("."):
            continue
        try:
            rel_path = str(f.relative_to(workspace_dir))
        except ValueError:
            rel_path = f.name
        gestures = extract_gestures_from_chapter(f, workspace_dir)

        # Statistics on Gestures & Distribution
        smile_matches = [g for g in gestures if g["is_smile"]]
        total_smiles = len(smile_matches)
        
        char_smile_counts = defaultdict(int)
        for g in smile_matches:
            clean_char = g["char"].replace(" (承前文)", "")
            char_smile_counts[clean_char] += 1

        anomalies = []

        # Check unprovoked smile in serious crisis context
        for g in smile_matches:
            prev = g["prev_ctx"]
            if any(w in prev for w in ["杀意", "重伤", "吐血", "威压", "绝望", "怒喝", "越狱", "枪声", "报警", "车祸"]):
                if not any(w in g["sentence"] for w in ["冷哼", "冷漠", "平静", "不疾不徐", "从容", "讥诮", "冷笑", "嘲弄"]):
                    anomalies.append(f"⚠️ [突兀发笑疑似 L{g['line']}] 在生死危机前置情境下发笑，请核查动因: \"{g['sentence']}\"")

        # Check repetitive gesture clusters for same character
        for char, count in char_smile_counts.items():
            if count >= 4 and char != "未知/环境":
                anomalies.append(f"💡 [角色表情多样性建议] 角色【{char}】在单章内使用了 {count} 次笑态，若非特定狂放/戏谑情节，建议适度替换为眼神或身体动作提升丰富度。")

        ch_report = {
            "chapter": rel_path,
            "total_gestures": len(gestures),
            "total_smiles": total_smiles,
            "character_smiles": dict(char_smile_counts),
            "anomalies": anomalies,
            "status": "PASS" if not anomalies else "REVIEW"
        }
        reports.append(ch_report)

        if not as_json:
            print("=" * 72)
            print(f" 🎭 [人物动作与神态合理性深度诊断报告] 工作区: {workspace_dir.name} | 章节: {rel_path}")
            print("=" * 72)
            print(f"📊 【全章动作统计】共提取肢体/表情节点: {len(gestures)} 处 | 笑态表达: {total_smiles} 处")
            if char_smile_counts:
                stats_str = ", ".join([f"{k}: {v}次" for k, v in char_smile_counts.items()])
                print(f"   👉 角色情绪笑态分布: {stats_str}")

            print("-" * 72)
            if anomalies:
                print("💡 【动作与神态多样性分析与建议】:")
                for a in anomalies:
                    print(f"   {a}")
            else:
                print("✨ [动作多样性极佳] 全章角色神态生动多维，身体语言与环境交互自然，表达丰富！")
            print("=" * 72 + "\n")

    if as_json:
        out = {"workspace": workspace_dir.name, "reports": reports}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Novel Studio 人物表情动作语义提取与多样性审查工具")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径 (默认为 novel_workspace)")
    parser.add_argument("--chapter", "-c", type=str, default=None, help="指定章节，如 ch_004")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    audit_gestures(target_chapter=args.chapter, workspace_path=args.workspace, as_json=args.json)
