# -*- coding: utf-8 -*-
"""
Universal Readability & Consistency Linter for novel chapters.
Refactored to prioritize:
1. 🌊 Readability & Cadence First (读感优先 / 呼吸感 / 长难句 / 排版透气度)
2. 🎭 Reading Experience & Tone Second (阅读体验 / 文风明快度 / 对白张力 / 断章钩子)
3. ✍️ Diction & AI De-Cliché Tuning Third (遣词造句 / 去AI味启发 / 智能角色去噪)

Supports any genre (Sci-Fi, Xianxia/Fantasy, Urban, Suspense, Game, etc.).
Usage:
    python tools/check_consistency.py
    python tools/check_consistency.py -w novel_workspace
    python tools/check_consistency.py -c ch_006 -w novel_workspace
    python tools/check_consistency.py -c ch_006 --json
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

from novel_utils import (
    resolve_workspace,
    find_manuscript_files,
    load_registered_characters,
    build_smart_whitelist,
    natural_chapter_sort_key,
    reconfigure_utf8,
    GENERIC_SKELETONS,
    CLIFFHANGER_KEYWORDS,
    OPPRESSIVE_KEYWORDS,
    STOP_CHARS
)

reconfigure_utf8()

def detect_genre(workspace_dir: Path) -> str:
    """Detects primary genre from project bible."""
    bible_file = workspace_dir / "00_meta" / "project_bible.md"
    if bible_file.exists():
        content = bible_file.read_text(encoding="utf-8")
        m = re.search(r"-\s*\*\*主类型\*\*\s*[:：]\s*(.*)", content)
        if m:
            return m.group(1).strip()
    return "通用"

def check_readability_cadence(lines):
    """
    🌊 自然读感检测 (Natural Readability Diagnostics)
    - 段落长短随物赋形，句子长短自然无规律；
    - 仅对极端无标点病句或极端说教长段进行基础兜底。
    """
    cadence_issues = []
    full_text = "\n".join(lines)

    # 1. 极端长难句检测 (超过 70 字完全无任何逗号标点停顿的病句)
    raw_sentences = re.split(r"[\n。！？!?…]+", full_text)
    for sent in raw_sentences:
        sent = sent.strip()
        if not sent or sent.startswith("#"):
            continue
        clauses = re.split(r"[，,；;、———]+", sent)
        for clause in clauses:
            clause = clause.strip()
            clause_chars = len(re.findall(r"[\u4e00-\u9fa5]", clause))
            if clause_chars > 70:
                preview = (clause[:25] + "..." + clause[-15:]) if len(clause) > 42 else clause
                cadence_issues.append(
                    f"   🌊 [长难句停顿提示] 连续 {clause_chars} 字无标点停顿: \"{preview}\"，可适当增设标点以助自然默读。"
                )
                
    # 2. 检查单次超长说教对白 (> 250 字无任何动作与叙事穿插)
    quotes = re.findall(r"“([^”]*)”", full_text)
    for q in quotes:
        q_clean = q.strip()
        q_chars = len(re.findall(r"[\u4e00-\u9fa5]", q_clean))
        if q_chars > 250:
            preview = (q_clean[:25] + "..." + q_clean[-15:]) if len(q_clean) > 42 else q_clean
            cadence_issues.append(
                f"   🌊 [对白说教提示] 单句对白长达 {q_chars} 字: \"{preview}\"，建议适当穿插人物动作或情境互动。"
            )
            
    return cadence_issues

def check_reading_experience_and_tone(content, lines, dialogue_ratio):
    """
    🎭 第二优先级：阅读体验与文风情绪诊断 (Reading Experience & Tone Diagnostics)
    - 文风压抑与暗黑饱和度检测 (响应用户最新反压抑规则)
    - 对白与叙事张力平衡
    - 章末断章期待钩子
    """
    experience_issues = []
    
    # 1. 文风压抑温和观察 (Anti-Oppressive Tone)
    chinese_count = len(re.findall(r"[\u4e00-\u9fa5]", content))
    oppressive_hits = []
    for kw in OPPRESSIVE_KEYWORDS:
        matches = len(re.findall(re.escape(kw), content))
        if matches > 0:
            oppressive_hits.append((kw, matches))
    
    total_oppressive_hits = sum(cnt for _, cnt in oppressive_hits)
    if chinese_count > 1000 and total_oppressive_hits >= 15 and (total_oppressive_hits / (chinese_count / 1000.0)) > 5.0:
        top_kws = ", ".join([f"{kw}({cnt}次)" for kw, cnt in sorted(oppressive_hits, key=lambda x: x[1], reverse=True)[:4]])
        experience_issues.append(
            f"   🎭 [文风基调提示] 本章沉郁词汇出现较多（{top_kws}）。若非极端险境死斗，建议结合情境保持从容明快。"
        )
        
    # 2. 章末断章钩子 (温和提示，不强制拦截)
    last_chunk = "\n".join(lines[-15:])
    has_cliffhanger = any(k in last_chunk for k in CLIFFHANGER_KEYWORDS)
    if not has_cliffhanger and len(lines) > 30:
        experience_issues.append(
            "   🎭 [断章期待钩子] 本章末尾未检测到显著转折或悬念钩子，可根据剧情走向决定是否留扣。"
        )
        
    return experience_issues

def check_smart_burstiness(text, smart_whitelist, window_size=500, min_repeat=5):
    """
    ✍️ 智能去噪的高频副词/口癖提示 (仅对真正无意义副词扎堆进行温和参考)
    """
    bursts = {}
    lines = text.splitlines()
    line_offsets = []
    curr = 0
    for l in lines:
        line_offsets.append(curr)
        curr += len(l) + 1

    def get_line_num(pos):
        for idx, offset in enumerate(line_offsets):
            if offset > pos:
                return max(1, idx)
        return len(lines)

    # 常见叙事词/修仙专名/意象名词免检池
    COMMON_EXEMPT = {"灵草", "丹药", "飞剑", "经脉", "真气", "灵石", "长生", "宗门", "师尊", "弟子", "水牢", "战船", "水师", "码头", "鬼市", "地胆", "玉髓", "洗髓", "暗渠", "钟乳", "石胆"}

    clean_text = text
    for n in [2, 3]:
        for i in range(0, max(0, len(clean_text) - window_size), 150):
            chunk = clean_text[i:i + window_size]
            counts = defaultdict(list)
            for j in range(len(chunk) - n + 1):
                gram = chunk[j:j + n]
                if re.match(r"^[\u4e00-\u9fa5]+$", gram):
                    if all(c in STOP_CHARS for c in gram) or gram in COMMON_EXEMPT:
                        continue
                    if any(gram in wl or wl in gram for wl in smart_whitelist):
                        continue
                    counts[gram].append(i + j)
            for gram, positions in counts.items():
                if len(positions) >= min_repeat:
                    if gram not in bursts:
                        line_num = get_line_num(positions[0])
                        bursts[gram] = (line_num, len(positions))
    return bursts

def check_all_consistency(workspace_dir: Path, target_chapter: str = None, as_json: bool = False):
    genre = detect_genre(workspace_dir)
    registered_chars = load_registered_characters(workspace_dir)
    smart_whitelist = build_smart_whitelist(workspace_dir)

    patterns_to_check = list(GENERIC_SKELETONS)

    all_drafts = []
    manuscript_dir = workspace_dir / "05_manuscript"
    if manuscript_dir.exists():
        all_drafts = find_manuscript_files(manuscript_dir, target_chapter)

    if not all_drafts:
        if as_json:
            err = {"error": f"未在 {workspace_dir.name} 中找到待检查的稿件文件。"}
            print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print(f"ℹ️ 未在 {workspace_dir} 中找到待检查的稿件文件。")
        return True

    if not as_json:
        print("=" * 76)
        print(f" 🔍 [Universal Novel Studio 全维读感与体验质检引擎] 根目录: {workspace_dir.name}")
        print("=" * 76)
        print(f"📖 【题材模式】: [{genre}] | 🎯 【质检准则】: 读感第一 · 体验第二 · 造句第三")
        char_preview = ", ".join(registered_chars[:6]) + ("..." if len(registered_chars) > 6 else "")
        print(f"👥 【白名单角色】已注册 {len(registered_chars)} 位核心角色: {char_preview}")

    total_optimizations = 0
    total_fatal_count = 0
    file_reports = []

    for draft_path in all_drafts:
        content = draft_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        rel_path = draft_path.relative_to(workspace_dir)

        chinese_count = len(re.findall(r"[\u4e00-\u9fa5]", content))
        quotes_matches = re.findall(r"“([^”]*)”", content)
        dialogue_chars = sum(len(q) for q in quotes_matches)
        dialogue_ratio = (dialogue_chars / chinese_count * 100) if chinese_count > 0 else 0
        narrative_ratio = 100 - dialogue_ratio

        # ----------------------------------------------------
        # 🚨 0. 核心硬伤断言门禁 (Hard Assertion Gates)
        # ----------------------------------------------------
        fatal_errors = []

        # 0.1 字数硬性门禁 (当前卷及后续章节 < 2500 字直接判定致命硬伤)
        is_legacy_archived = "vol_01" in str(draft_path)
        if chinese_count < 2500:
            if not is_legacy_archived or target_chapter:
                fatal_errors.append(f"   🚨 [硬伤·篇幅熔断门禁] 单章中文字数仅 {chinese_count} 字 (低于 2500 字及格底线)！剧情展开不充分，严禁偷懒短章交差！")
            else:
                experience_issues.append(f"   💡 [早期已归档历史卷字数提示] 单章字数 {chinese_count} 字 (早期历史存档)")

        # 0.2 引号配对检查
        left_quotes = content.count("“")
        right_quotes = content.count("”")
        if left_quotes != right_quotes:
            fatal_errors.append(f"   🚨 [硬伤·排版门禁] 中文双引号不配对 (左引号: {left_quotes}, 右引号: {right_quotes})")

        # ----------------------------------------------------
        # 🌊 1. 读感心流诊断 (Readability & Cadence Flow)
        # ----------------------------------------------------
        cadence_issues = check_readability_cadence(lines)

        # ----------------------------------------------------
        # 🎭 2. 阅读体验与情绪氛围 (Reading Experience & Tone)
        # ----------------------------------------------------
        experience_issues = check_reading_experience_and_tone(content, lines, dialogue_ratio)

        # ----------------------------------------------------
        # ✍️ 3. 遣词造句与去AI味微调 (Diction & AI Tuning)
        # ----------------------------------------------------
        diction_issues = list(fatal_errors)

        # 正则检查
        pattern_hits = defaultdict(list)
        for line_idx, line in enumerate(lines, 1):
            if not line.strip() or line.startswith("#"):
                continue
            for p_info in patterns_to_check:
                p_name = p_info["name"]
                for match in re.finditer(p_info["pattern"], line):
                    hit_word = match.group(0)
                    pattern_hits[p_name].append((line_idx, hit_word, line.strip()))

        for p_name, hits in pattern_hits.items():
            if hits:
                suggestion = next((p["suggestion"] for p in patterns_to_check if p["name"] == p_name), "")
                is_hard_error = "系统工程标记" in p_name
                prefix = "   🚨 [硬伤·标记外泄]" if is_hard_error else f"   💡 [{p_name}]"
                diction_issues.append(f"{prefix} 发现 {len(hits)} 处 (提示: {suggestion}):")
                for l_num, hit_word, full_line in hits[:3]:
                    preview = (full_line[:35] + "...") if len(full_line) > 35 else full_line
                    diction_issues.append(f"      - L{l_num}: \"{preview}\"")
                if len(hits) > 3:
                    diction_issues.append(f"      ... (其余 {len(hits) - 3} 处略)")

        # 3.2 智能去噪的局部词汇爆发
        burst_hits = check_smart_burstiness(content, smart_whitelist, window_size=400, min_repeat=3)
        if burst_hits:
            diction_issues.append(f"   💡 [局部词汇密集提示] (500字内非专名密集出现>=3次，可按需微调):")
            for gram, (l_num, cnt) in list(burst_hits.items())[:4]:
                diction_issues.append(f"      - L{l_num} 附近: 【{gram}】短距离出现 {cnt} 次")

        all_file_fatal = [i for i in diction_issues if "🚨 [硬伤" in i]
        all_file_issues = cadence_issues + experience_issues + diction_issues
        total_optimizations += len(all_file_issues)
        total_fatal_count += len(all_file_fatal)

        f_report = {
            "file": str(rel_path),
            "word_count": chinese_count,
            "dialogue_ratio": f"{dialogue_ratio:.1f}%",
            "narrative_ratio": f"{narrative_ratio:.1f}%",
            "issues_count": len(all_file_issues),
            "fatal_count": len(all_file_fatal),
            "cadence_issues_count": len(cadence_issues),
            "experience_issues_count": len(experience_issues),
            "diction_issues_count": len(diction_issues),
            "issues": all_file_issues
        }
        file_reports.append(f_report)

        if not as_json:
            if all_file_fatal:
                status_symbol = f"❌ [致命阻断硬伤 ({len(all_file_fatal)})]"
            elif all_file_issues:
                status_symbol = f"💡 [可微调优化项 ({len(all_file_issues)})]"
            else:
                status_symbol = "✅ [读感流畅·体验完美]"
            print(f"\n📄 文件: {rel_path} | 中文字数: {chinese_count} | 对白占比: {dialogue_ratio:.1f}% | 叙事占比: {narrative_ratio:.1f}% -> {status_symbol}")
            
            if cadence_issues:
                print("   🌊 ──【1. 读感与呼吸节奏 (Readability & Flow)】──")
                for issue in cadence_issues:
                    print(issue)
            if experience_issues:
                print("   🎭 ──【2. 阅读体验与情绪基调 (Reading Experience & Tone)】──")
                for issue in experience_issues:
                    print(issue)
            if diction_issues:
                print("   ✍️ ──【3. 遣词造句与微创建议 (Diction & AI De-Cliché)】──")
                for issue in diction_issues:
                    print(issue)

    if as_json:
        out = {
            "workspace": workspace_dir.name,
            "genre": genre,
            "total_files": len(all_drafts),
            "total_optimizations": total_optimizations,
            "total_fatal_count": total_fatal_count,
            "reports": file_reports,
            "status": "FAIL" if total_fatal_count > 0 else ("PASS" if total_optimizations == 0 else "REVIEW")
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    print("\n" + "=" * 76)
    if total_fatal_count > 0:
        print(f"❌ [致命门禁未通过] 发现 {total_fatal_count} 处核心硬伤阻断（字数 < 2500 或排版硬伤）！请必须修正后方可定稿！")
        print("=" * 76)
        return False
    elif total_optimizations == 0:
        print(f"✨ [全维巡检通过] 共扫描 {len(all_drafts)} 份文件，读感丝滑、体验极佳、遣词自然！")
    else:
        print(f"📊 [巡检提示] 扫描完毕，给出 {total_optimizations} 条读感/体验/造句分层优化建议，供修审参考。")
    print("=" * 76)
    return True

def main():
    parser = argparse.ArgumentParser(description="Universal Novel Studio Readability & Consistency Linter.")
    parser.add_argument("-w", "--workspace", type=str, default=None, help="Path to novel workspace")
    parser.add_argument("-c", "--chapter", type=str, default=None, help="Target chapter (e.g. ch_001)")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    w_dir = resolve_workspace(args.workspace)
    res = check_all_consistency(w_dir, args.chapter, as_json=args.json)
    if isinstance(res, dict):
        if res.get("status") == "FAIL":
            sys.exit(1)
    elif not res:
        sys.exit(1)

if __name__ == "__main__":
    main()
