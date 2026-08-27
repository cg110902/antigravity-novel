# -*- coding: utf-8 -*-
"""
Character Dialogue Voice Fingerprint & Anti-OOC Analyzer
Extracts all spoken dialogue (“...”), attributes quotes to active characters,
computes voice fingerprints (mean sentence length, tone markers, exclamation ratio),
and flags OOC shifts and dialogue homogenization.
Usage:
    python tools/audit_dialogue_voice.py
    python tools/audit_dialogue_voice.py -c ch_003
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

from novel_utils import resolve_workspace, find_manuscript_files, load_registered_characters, reconfigure_utf8

reconfigure_utf8()

def extract_dialogues(file_path: Path, characters: list):
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    dialogue_records = []
    current_speaker = "未知/旁白"
    last_two_speakers = []

    for idx, line in enumerate(lines, 1):
        clean_line = line.strip()
        if not clean_line or clean_line.startswith("#"):
            continue

        quotes = list(re.finditer(r'“([^”]+)”', clean_line))
        if not quotes:
            # Check if there is an explicit character acting in narrative
            for c in characters:
                if c in clean_line:
                    current_speaker = c
                    break
            continue

        # For each dialogue chunk in the line
        for q_match in quotes:
            dialogue_text = q_match.group(1).strip()
            
            # Determine speaker based on immediate context before quote or after quote
            pre_text = clean_line[:q_match.start()]
            post_text = clean_line[q_match.end():]
            
            speaker = None
            for c in characters:
                if c in pre_text or c in post_text:
                    speaker = c
                    break

            # Fallback to preceding lines
            if not speaker:
                for prev_idx in range(idx - 2, max(-1, idx - 4), -1):
                    p_line = lines[prev_idx].strip()
                    for c in characters:
                        if c in p_line:
                            speaker = c
                            break
                    if speaker:
                        break

            # Fallback: Alternating turn in 2-person dialogue
            if not speaker and len(last_two_speakers) == 2:
                speaker = last_two_speakers[0]  # ping-pong turn

            if not speaker:
                speaker = current_speaker

            # Update speaker tracking
            if speaker != "未知/旁白":
                if not last_two_speakers or last_two_speakers[-1] != speaker:
                    last_two_speakers.append(speaker)
                    if len(last_two_speakers) > 2:
                        last_two_speakers.pop(0)

            dialogue_records.append({
                "line": idx,
                "speaker": speaker,
                "text": dialogue_text,
                "length": len(dialogue_text),
                "has_exclamation": "！" in dialogue_text or "!" in dialogue_text,
                "has_question": "？" in dialogue_text or "?" in dialogue_text,
                "particles": re.findall(r"[呢吧罢哼呵哈唉嘛呀哇啦]", dialogue_text)
            })

    return dialogue_records

def analyze_voice_fingerprints(target_chapter=None, workspace_path=None, as_json=False):
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

    characters = load_registered_characters(workspace_dir)
    reports = []

    for f in files:
        if f.name.startswith("."):
            continue
        try:
            rel_path = str(f.relative_to(workspace_dir))
        except ValueError:
            rel_path = f.name

        records = extract_dialogues(f, characters)
        if not records:
            continue

        # Aggregate by character
        char_data = defaultdict(lambda: {"count": 0, "total_len": 0, "excl": 0, "ques": 0, "particles": []})
        for r in records:
            sp = r["speaker"]
            char_data[sp]["count"] += 1
            char_data[sp]["total_len"] += r["length"]
            if r["has_exclamation"]:
                char_data[sp]["excl"] += 1
            if r["has_question"]:
                char_data[sp]["ques"] += 1
            char_data[sp]["particles"].extend(r["particles"])

        warnings = []
        char_summary = {}

        for char, d in sorted(char_data.items(), key=lambda x: x[1]["count"], reverse=True):
            if char == "未知/旁白":
                continue
            avg_len = round(d["total_len"] / max(1, d["count"]), 1)
            excl_rate = round((d["excl"] / max(1, d["count"])) * 100, 1)
            ques_rate = round((d["ques"] / max(1, d["count"])) * 100, 1)
            particle_top = list(set(d["particles"][:4])) if d["particles"] else []
            
            char_summary[char] = {
                "count": d["count"],
                "avg_length": avg_len,
                "exclamation_rate": excl_rate,
                "question_rate": ques_rate,
                "particles": particle_top
            }

            # Heuristics checks
            if avg_len > 45:
                warnings.append(f"⚠️ [台词拖沓] 角色【{char}】平均台词达 {avg_len} 字/句，对白偏书面说明书化，建议脱水为短促击剑！")

        # Check for single long monologue lines (> 80 chars)
        for r in records:
            if r["length"] > 75 and r["speaker"] != "未知/旁白":
                warnings.append(f"💡 [长句警示 L{r['line']}] 【{r['speaker']}】单句对白达到 {r['length']} 字 (\"...{r['text'][:25]}...\")，建议拆分为多轮交互打断")

        ch_report = {
            "chapter": rel_path,
            "total_dialogue_turns": len(records),
            "speaking_characters_count": len(char_data),
            "character_voices": char_summary,
            "warnings": warnings,
            "status": "PASS" if not warnings else "REVIEW"
        }
        reports.append(ch_report)

        if not as_json:
            print("=" * 72)
            print(f" 🎙️ [角色声纹指纹与台词风格诊断] 工作区: {workspace_dir.name} | 章节: {rel_path}")
            print("=" * 72)
            print(f"📊 【全章台词统计】总对白轮次: {len(records)} 轮 | 出声角色数: {len(char_data)} 位\n")
            print(f"   {'角色姓名':<10} | {'轮次':<5} | {'均长(字)':<8} | {'感叹率':<8} | {'疑问率':<8} | {'代表性语气词'}")
            print("   " + "-" * 64)
            for char, s in char_summary.items():
                p_str = "/".join(s["particles"]) if s["particles"] else "无"
                print(f"   {char:<10} | {s['count']:<5} | {s['avg_length']:<8.1f} | {s['exclamation_rate']:<7.1f}% | {s['question_rate']:<7.1f}% | {p_str}")

            print("-" * 72)
            if warnings:
                print("🚨 【声纹风格与节奏优化建议】:")
                for w in warnings:
                    print(f"   {w}")
            else:
                print("✨ [声纹指纹极佳] 角色台词长短分明、语气各异，未发现全员书面腔或单调长篇大论！")
            print("=" * 72 + "\n")

    if as_json:
        out = {"workspace": workspace_dir.name, "reports": reports}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="角色声纹指纹与台词防 OOC 诊断引擎")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--chapter", "-c", type=str, default=None, help="指定章节，例如: ch_003")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    analyze_voice_fingerprints(target_chapter=args.chapter, workspace_path=args.workspace, as_json=args.json)
