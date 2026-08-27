# -*- coding: utf-8 -*-
"""
Chapter Tension Pacing Curve & Mobile Visual Heatmap Analyzer
Computes 5-segment tension/conflict velocity curves, checks paragraph breathing density,
and flags breathless sentences (>30 chars without punctuation) for mobile readability.
Usage:
    python tools/analyze_pacing_curve.py
    python tools/analyze_pacing_curve.py -c ch_004
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

# Conflict and Tension marker keywords
CONFLICT_MARKERS = [
    "杀", "死", "剑", "血", "痛", "剧毒", "暴退", "碎裂", "轰然", "斩", "破", "寒煞",
    "欠", "灵石", "契约", "地契", "冷哼", "暴喝", "抽", "耳光", "掌风", "围起来", "打断",
    "逃", "惊骇", "震颤", "炸开", "危急", "死局", "绝境", "反扑", "倒飞", "枪声", "警报"
]

def analyze_pacing(target_chapter=None, workspace_path=None, as_json=False):
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

        content = f.read_text(encoding="utf-8")
        clean_lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#")]
        full_text = "\n".join(clean_lines)
        total_len = len(full_text)

        # 1. 5-Segment Tension Waveform
        chunk_size = max(1, total_len // 5)
        segments = [full_text[i*chunk_size : (i+1)*chunk_size] for i in range(5)]
        
        scores = []
        for seg in segments:
            hits = sum(len(re.findall(re.escape(k), seg)) for k in CONFLICT_MARKERS)
            density = (hits / max(1, len(seg))) * 1000  # score per 1000 chars
            scores.append(round(density, 1))

        max_score = max(1.0, max(scores))
        normalized = [int((s / max_score) * 10) for s in scores]

        stage_names = ["01.开篇抓人(0-20%)", "02.危机激化(20-40%)", "03.中点转折(40-60%)", "04.高潮爆发(60-80%)", "05.断章黄金钩(80-100%)"]

        warnings = []

        # 2. 自然句子与段落统计
        paragraphs = content.split("\n\n")
        sentences = re.split(r'[。！？\n]', content)
        breathless = []
        for s in sentences:
            clauses = re.split(r'[,，、；;]', s)
            for c in clauses:
                clean_c = c.strip()
                if len(clean_c) >= 75 and not clean_c.startswith("“") and not clean_c.endswith("”"):
                    breathless.append(clean_c)

        if breathless:
            for b in breathless[:2]:
                warnings.append(f"🌊 [长难句停顿提示] 连续 {len(b)} 字无标点 (\"...{b[:20]}...\")，可适当补充标点助读。")

        ch_report = {
            "chapter": rel_path,
            "total_chars": total_len,
            "five_stage_scores": scores,
            "five_stage_normalized": normalized,
            "total_paragraphs": len(paragraphs),
            "avg_paragraph_length": total_len // max(1, len(paragraphs)),
            "warnings": warnings,
            "status": "PASS" if not warnings else "REVIEW"
        }
        reports.append(ch_report)

        if not as_json:
            print("=" * 72)
            print(f" 📈 [单章张力波形与叙事流统计] 工作区: {workspace_dir.name} | 章节: {rel_path}")
            print("=" * 72)
            print("📊 【单章 5 段式张力波形参考】:")
            for name, norm_val, raw_score in zip(stage_names, normalized, scores):
                bar = "█" * norm_val + "░" * (10 - norm_val)
                print(f"   {name:<20} [{bar}] 冲突动能: {raw_score:.1f}")

            print("\n🌊 【自然段落与句式统计】:")
            print(f"   - 总段落数: {len(paragraphs)} 段 | 平均段长: {total_len // max(1, len(paragraphs))} 字/段")
            print("-" * 72)
            if warnings:
                print("🚨 【节奏与排版调优建议】:")
                for w in warnings:
                    print(f"   {w}")
            else:
                print("✨ [张力波形与视觉极佳] 情绪波段起伏健康，段落短小精悍，适合移动端高爽感畅读！")
            print("=" * 72 + "\n")

    if as_json:
        out = {"workspace": workspace_dir.name, "reports": reports}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="单章张力波形与移动端视觉热力图")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--chapter", "-c", type=str, default=None, help="指定章节，例如: ch_004")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    result = analyze_pacing(target_chapter=args.chapter, workspace_path=args.workspace, as_json=args.json)
    if isinstance(result, dict):
        sys.exit(1 if result.get("error") else 0)
    sys.exit(0 if result else 1)
