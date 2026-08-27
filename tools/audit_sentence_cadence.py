# -*- coding: utf-8 -*-
"""
Sentence Cadence & Rhythm Variance Analyzer
1. Audits chapter text for monotonous sentence-ending repetitive particles ("了", "的", "着", "道", "去").
2. Computes sentence length variance to detect robotic monotone sentences (identical sentence lengths in a row).
3. Evaluates overall readability cadence and rhythmic flow.
Usage:
    python tools/audit_sentence_cadence.py
    python tools/audit_sentence_cadence.py -c ch_004
    python tools/audit_sentence_cadence.py --json
"""

import sys
import re
import json
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, find_manuscript_files, reconfigure_utf8

reconfigure_utf8()

def split_into_sentences(text: str):
    # Split by Chinese punctuation marks: 。！？；…\n
    raw_sentences = re.split(r'[。！？；…\n]+', text)
    sentences = []
    for s in raw_sentences:
        clean = s.strip()
        if clean and len(clean) >= 3 and not clean.startswith("#"):
            sentences.append(clean)
    return sentences

def analyze_cadence(target_chapter=None, workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    manuscript_dir = workspace_dir / "05_manuscript"

    if not manuscript_dir.exists():
        msg = f"未找到稿件目录: {manuscript_dir}"
        if as_json:
            out = {"error": msg, "workspace": workspace_dir.name, "reports": []}
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return out
        print(f"[错误] {msg}")
        return False

    files = find_manuscript_files(manuscript_dir, target_chapter)

    if not files:
        msg = f"在 {workspace_dir.name} 中未找到匹配的正文稿件。"
        if as_json:
            out = {"error": msg, "workspace": workspace_dir.name,
                   "target_chapter": target_chapter, "reports": []}
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return out
        print(f"[提示] {msg}")
        # 指定章节却找不到稿件属于调用错误，应返回非 0；全书空扫描属正常空态。
        return not bool(target_chapter)

    reports = []

    for f in files:
        if f.name.startswith("."):
            continue
        try:
            rel_path = f.relative_to(workspace_dir)
        except ValueError:
            rel_path = f.name

        content = f.read_text(encoding="utf-8")
        sentences = split_into_sentences(content)
        
        if not sentences:
            continue

        lengths = [len(s) for s in sentences]
        avg_len = sum(lengths) / max(1, len(lengths))
        
        # Calculate variance
        variance = sum((l - avg_len) ** 2 for l in lengths) / max(1, len(lengths))
        std_dev = variance ** 0.5

        # 1. Check for repetitive sentence-ending particles (3+ in a row)
        repeats = []
        for i in range(len(sentences) - 2):
            end1 = sentences[i][-1]
            end2 = sentences[i+1][-1]
            end3 = sentences[i+2][-1]
            if end1 == end2 == end3 and end1 in ["了", "的", "着", "道", "去", "来", "起"]:
                repeats.append({
                    "particle": end1,
                    "sample": f"1) {sentences[i][-15:]} | 2) {sentences[i+1][-15:]} | 3) {sentences[i+2][-15:]}"
                })

        # 2. Check for robotic equal-length sentences (4 in a row within ±1 char)
        robotic_blocks = []
        for i in range(len(sentences) - 3):
            l0, l1, l2, l3 = lengths[i], lengths[i+1], lengths[i+2], lengths[i+3]
            if abs(l0 - l1) <= 1 and abs(l1 - l2) <= 1 and abs(l2 - l3) <= 1 and l0 >= 8:
                robotic_blocks.append(f"{sentences[i][:15]}... ({l0}字) -> {sentences[i+1][:15]}... ({l1}字)")

        r_data = {
            "chapter": str(rel_path),
            "total_sentences": len(sentences),
            "mean_length": round(avg_len, 1),
            "length_std_dev": round(std_dev, 1),
            "repetitive_endings": repeats[:3],
            "robotic_monotones": robotic_blocks[:3]
        }
        reports.append(r_data)

        if not as_json:
            print("═" * 74)
            print(f" 🎵 [句末声韵音律与节奏特征参考] 章节: {rel_path}")
            print("═" * 74)
            print(f"📊 【音律指纹】总有效分句: {len(sentences)} 句 | 均长: {avg_len:.1f} 字 | 句长离散度: {std_dev:.1f}")
            print("✨ [自然文风流] 句子长短随剧情心绪自由舒展，无需刻意追求机械等长或交错。")
            print("═" * 74 + "\n")

    if as_json:
        out = {"workspace": workspace_dir.name, "reports": reports}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="句末声韵音律与节奏方差诊断器")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--chapter", "-c", type=str, default=None, help="指定章节，例如: ch_004")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    result = analyze_cadence(target_chapter=args.chapter, workspace_path=args.workspace, as_json=args.json)
    if isinstance(result, dict):
        sys.exit(1 if result.get("error") else 0)
    sys.exit(0 if result else 1)
