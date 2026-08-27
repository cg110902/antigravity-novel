# -*- coding: utf-8 -*-
"""
Prescription-Driven Micro-Surgery Engine for Novel Chapters.
Refactored to deeply align with the 3-Tier Literary Pyramid:
1. 🌊 Readability & Cadence Slices (读感优先: 移动端大黑块段落、长难断气句、说教长对白)
2. 🎭 Reading Experience & Tone Slices (体验第二: 压抑沉郁词群降频、说教旁白拔除)
3. ✍️ Diction & AI De-Cliché Slices (造句第三: 智能角色白名单去噪、脸谱神态/副词微创置换)

Usage:
    python tools/suggest_micro_surgery.py
    python tools/suggest_micro_surgery.py -c ch_006
    python tools/suggest_micro_surgery.py -c ch_006 -w novel_workspace
"""

import sys
import re
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
    reconfigure_utf8,
    GENERIC_SKELETONS,
    OPPRESSIVE_KEYWORDS,
    STOP_CHARS,
    load_ground_truth,
    detect_semantic_redundancy
)

reconfigure_utf8()

def extract_surgical_slices(draft_path: Path, workspace_dir: Path):
    """
    依照三大优先级，分层提取定点微创手术切片
    """
    lines = draft_path.read_text(encoding="utf-8").splitlines()
    mindset_arcs, guns = load_ground_truth(workspace_dir)
    whitelist_substrings = build_smart_whitelist(workspace_dir)

    cadence_slices = []
    tone_slices = []
    diction_slices = []
    seen_lines = set()

    # ========================================================
    # 🌊 第一优先级：自然读感切片 (Readability & Flow)
    # ========================================================
    for idx, line in enumerate(lines):
        clean_l = line.strip()
        if not clean_l or clean_l.startswith("#"):
            continue
        
        # 1. 极端超长无标点断气长难句 (> 75 字无标点)
        clauses = re.split(r"[，,；;、———]+", clean_l)
        for clause in clauses:
            clause_chars = len(re.findall(r"[\u4e00-\u9fa5]", clause.strip()))
            if clause_chars > 75 and idx not in seen_lines:
                seen_lines.add(idx)
                cadence_slices.append({
                    "line_num": idx + 1,
                    "tier": "🌊 读感呼吸层",
                    "type": "超长无标点断气长难句",
                    "matched": f"连续 {clause_chars} 字无停顿: \"{clause[:20]}...\"",
                    "context_before": lines[max(0, idx - 2):idx],
                    "target_line": line,
                    "context_after": lines[idx + 1:min(len(lines), idx + 3)],
                    "strategy": "在长句中间增设逗号进行气口停顿，或拆为短促连贯的微动作分句。"
                })
                break

        # 2. 说明书式超长单句对白 (> 220 字)
        quotes = re.findall(r"“([^”]*)”", clean_l)
        for q in quotes:
            q_chars = len(re.findall(r"[\u4e00-\u9fa5]", q.strip()))
            if q_chars > 220 and idx not in seen_lines:
                seen_lines.add(idx)
                cadence_slices.append({
                    "line_num": idx + 1,
                    "tier": "🌊 读感呼吸层",
                    "type": "单向说教式长对白",
                    "matched": f"单句对白 {q_chars} 字",
                    "context_before": lines[max(0, idx - 2):idx],
                    "target_line": line,
                    "context_after": lines[idx + 1:min(len(lines), idx + 3)],
                    "strategy": "在长对白中穿插角色的专属肢体动作、眼神交锋或对方微反应，避免单向说教。"
                })
                break

    # ========================================================
    # 🎭 第二优先级：阅读体验与情绪文风切片 (Experience & Tone)
    # ========================================================
    for idx in range(len(lines)):
        window = lines[idx:min(len(lines), idx + 4)]
        window_text = " ".join(window)
        matched_oppressive = [kw for kw in OPPRESSIVE_KEYWORDS if kw in window_text]
        if len(matched_oppressive) >= 3 and idx not in seen_lines:
            target_idx = idx
            for j in range(idx, min(len(lines), idx + 4)):
                if any(kw in lines[j] for kw in matched_oppressive):
                    target_idx = j
                    break
            if target_idx not in seen_lines:
                seen_lines.add(target_idx)
                tone_slices.append({
                    "line_num": target_idx + 1,
                    "tier": "🎭 体验情绪层",
                    "type": "冷峻压抑词汇密集扎堆",
                    "matched": "、".join(matched_oppressive),
                    "context_before": lines[max(0, target_idx - 2):target_idx],
                    "target_line": lines[target_idx],
                    "context_after": lines[target_idx + 1:min(len(lines), target_idx + 3)],
                    "strategy": "若此处非极度凶险之魔窟绝境，建议将压抑死寂词汇置换为从容、明快或带烟火气的物理动作描写，提升读者积极心流。"
                })

    # 同义反复与情绪堆砌
    redundant_items = detect_semantic_redundancy(lines, window_lines=3)
    for r in redundant_items:
        l_idx = r["line_idx"]
        if l_idx not in seen_lines and l_idx < len(lines):
            line_text = lines[l_idx].strip()
            if line_text and not line_text.startswith("#"):
                seen_lines.add(l_idx)
                tone_slices.append({
                    "line_num": l_idx + 1,
                    "tier": "🎭 体验情绪层",
                    "type": f"情绪堆砌 ({r['cluster_name']})",
                    "matched": "、".join(r["matched_words"]),
                    "context_before": lines[max(0, l_idx - 2):l_idx],
                    "target_line": lines[l_idx],
                    "context_after": lines[l_idx + 1:min(len(lines), l_idx + 3)],
                    "strategy": r["suggestion"]
                })

    # ========================================================
    # ✍️ 第三优先级：遣词造句与去AI味微创切片 (Diction & AI)
    # ========================================================
    # 1. 扫描泛型句式骨架与 AI 套路
    for idx, line in enumerate(lines):
        if not line.strip() or line.startswith("#") or idx in seen_lines:
            continue
        for skeleton in GENERIC_SKELETONS:
            m = re.search(skeleton["pattern"], line)
            if m:
                seen_lines.add(idx)
                is_hard = "系统工程标记" in skeleton["name"]
                diction_slices.append({
                    "line_num": idx + 1,
                    "tier": "✍️ 造句去AI层",
                    "type": ("🚨 [硬伤拦截] " if is_hard else "💡 ") + skeleton["name"],
                    "matched": m.group(0),
                    "context_before": lines[max(0, idx - 2):idx],
                    "target_line": line,
                    "context_after": lines[idx + 1:min(len(lines), idx + 3)],
                    "strategy": skeleton["suggestion"]
                })
                break

    # 2. 智能过滤角色名后的无监督局部词汇扎堆
    full_text = "\n".join(lines)
    line_offsets = []
    curr = 0
    for l in lines:
        line_offsets.append(curr)
        curr += len(l) + 1

    def get_line_idx(pos):
        for idx, offset in enumerate(line_offsets):
            if offset > pos:
                return max(0, idx - 1)
        return len(lines) - 1

    starts = list(range(0, len(full_text), 150)) if len(full_text) <= 500 else list(range(0, len(full_text) - 500 + 1, 150))
    if not starts:
        starts = [0]
    for n in [2, 3, 4]:
        for i in starts:
            chunk = full_text[i:i + 500]
            counts = defaultdict(list)
            for j in range(len(chunk) - n + 1):
                gram = chunk[j:j + n]
                if re.match(r"^[\u4e00-\u9fa5]+$", gram):
                    if all(c in STOP_CHARS for c in gram):
                        continue
                    if any(gram in wl or wl in gram for wl in whitelist_substrings):
                        continue
                    counts[gram].append(i + j)
            for gram, positions in counts.items():
                if len(positions) >= 3:
                    l_idx = get_line_idx(positions[0])
                    if l_idx not in seen_lines and l_idx < len(lines):
                        line_text = lines[l_idx].strip()
                        if line_text and not line_text.startswith("#"):
                            seen_lines.add(l_idx)
                            diction_slices.append({
                                "line_num": l_idx + 1,
                                "tier": "✍️ 造句去AI层",
                                "type": "局部非专名短距离密集",
                                "matched": f"【{gram}】500字内出现 {len(positions)} 次",
                                "context_before": lines[max(0, l_idx - 2):l_idx],
                                "target_line": lines[l_idx],
                                "context_after": lines[l_idx + 1:min(len(lines), l_idx + 3)],
                                "strategy": f"词组【{gram}】在短距离内密集重复，若非刻意强调，建议用具体动作、物理环境物象或代词置换。"
                            })

    all_slices = cadence_slices + tone_slices + diction_slices
    all_slices.sort(key=lambda x: x["line_num"])
    return all_slices[:15], mindset_arcs, guns, len(cadence_slices), len(tone_slices), len(diction_slices)

def generate_prescription_markdown(chapter_id: str, slices: list, mindset_arcs: dict, guns: list, c_count: int, t_count: int, d_count: int):
    md = []
    md.append(f"# 🩺 【全维分层微创手术处方单】(Chapter: {chapter_id})\n")
    md.append("> 🎯 **执行准则**：本处方单依循 **【读感第一 · 体验第二 · 造句第三】** 金字塔体系。审校官需严格恪守【核心逻辑绝对不动】底线（主线胜负因果、未爆伏笔绝对不动），对读感卡点与AI病灶实施定点微创手术，保留优秀内容！\n")

    md.append("## 一、 核心事实真值与心智防线 (Ground Truth)\n")
    if mindset_arcs:
        md.append("### 🧠 角色当前心智阶段：")
        for name, stage in mindset_arcs.items():
            md.append(f"- **{name}**：`{stage}`")
    else:
        md.append("- （保持角色基线心智）")

    if guns:
        md.append("\n### 🔫 活跃伏笔池：")
        for g in guns:
            md.append(f"- 📌 `{g}`")

    md.append("\n---\n")
    md.append(f"## 二、 靶向微创切片清单（共提取 {len(slices)} 处诊断切片: 🌊读感 {c_count} 处 / 🎭体验 {t_count} 处 / ✍️造句 {d_count} 处）\n")

    for i, s in enumerate(slices, 1):
        md.append(f"### 📍 切片 {i}：L{s['line_num']} · {s['tier']} · 【{s['type']}】")
        matched_str = f" 触发特征: `【{s['matched']}】`" if s['matched'] else ""
        md.append(f"- 🎯 **微创策略建议**: {s['strategy']}{matched_str}")
        md.append("- ✂️ **局部上下文切片**:")
        md.append("```text")
        for b_line in s['context_before']:
            md.append(f"   {b_line}")
        md.append(f"👉 [病灶行 L{s['line_num']}] {s['target_line']}")
        for a_line in s['context_after']:
            md.append(f"   {a_line}")
        md.append("```")
        md.append("- 💡 **多维微创实操指引 (自由选用或复合拼接)**:")
        md.append("  - `[策略 A · 顺读感与气口拆分]`：若属长难句，按气口增设逗号或拆为节奏明快、长短错落的动作短句；")
        md.append("  - `[策略 B · 具象物理动作置换]`：将套路神态/副词置换为角色专属动作（捻针/摸刀镡/拨算盘/拍袍上尘土）；")
        md.append("  - `[策略 C · 脱水纯对白击剑]`：在谈判交锋时直接以纯台词推进，删去冗余引述动词与神态垫片；")
        md.append("  - `[策略 D · 环境借景与意境留白]`：以风声、檐雨、茶水涟漪、烛火爆星等现场物象代替空洞的情绪惊叹；")
        md.append("  - `[策略 E · 真实生理应激反应]`：将‘心神巨震’转化为喉头微耸、后背发紧、指尖用力发白等真实生理本能；")
        md.append("  - `[策略 F · 市井反差与人情幽默]`：在严肃缝隙中插入世俗小人物的利益算盘与冷幽默，打破单一单调气氛；")
        md.append("  - `[策略 G · 物理声效与力学触感]`：描写刀刃入肉的阻力、靴底碾碎瓦砾的声响、罡气扑面的灼热沉坠感；")
        md.append("  - `[策略 H · 酌情保留高光原貌]`：若结合上下文此处自然妥帖、极具神韵，100% 坚决保留原句，严禁盲目修改；")
        md.append("  - `[策略 I · 自主创新修润]`：根据当前场景特色，自主设计上述选项之外的更优修润手法。\n")

    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(description="Generate layered surgical prescriptions prioritizing Readability, Experience, and Diction.")
    parser.add_argument("-w", "--workspace", type=str, default=None, help="Novel workspace path")
    parser.add_argument("-c", "--chapter", type=str, default=None, help="Target chapter (e.g., ch_006)")
    args = parser.parse_args()

    w_dir = resolve_workspace(args.workspace)
    manuscript_dir = w_dir / "05_manuscript"
    all_drafts = find_manuscript_files(manuscript_dir, args.chapter)
    if not all_drafts:
        print(f"ℹ️ 在 {w_dir} 中未找到待手术的稿件文件。")
        # 指定章节却找不到 → 用法错误，返回 1；全书空扫描 → 正常空态返回 0。
        return 1 if args.chapter else 0

    target_draft = all_drafts[-1]
    ch_id = args.chapter or target_draft.stem.replace("_v1", "")

    slices, mindset_arcs, guns, c_cnt, t_cnt, d_cnt = extract_surgical_slices(target_draft, w_dir)
    prescription_content = generate_prescription_markdown(ch_id, slices, mindset_arcs, guns, c_cnt, t_cnt, d_cnt)
    print(prescription_content)
    print(f"\n✨ [分层处方生成完成] 靶向切片数: {len(slices)} 处 (🌊读感:{c_cnt} / 🎭体验:{t_cnt} / ✍️造句:{d_cnt})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
