# -*- coding: utf-8 -*-
"""
Universal Novel Studio - Reader Confusion & Comprehension Blocker Detector
(audit_reader_confusion.py)

Detects points in novel text where a first-time reader would likely feel confused,
lost, or unable to follow the narrative. Uses 8 deterministic algorithmic checks
drawing data from the full novel_workspace state machine.

Severity Levels:
  CRITICAL  → Must fix before delivery (Exit Code 1 blocker)
  WARNING   → Strongly recommended to address
  INFO      → Informational, may be intentional

Usage:
    python tools/audit_reader_confusion.py -c ch_014
    python tools/audit_reader_confusion.py -c ch_014 --json
    python tools/audit_reader_confusion.py -c ch_014 -w novel_workspace
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
    natural_chapter_sort_key,
    reconfigure_utf8,
    has_placeholder,
)

reconfigure_utf8()

# ─────────────────────────────────────────────────────────────────────
# Helpers: Data Extraction from novel_workspace
# ─────────────────────────────────────────────────────────────────────

def _extract_chapter_number(filepath: Path) -> int:
    """Extract numeric chapter ID from filename like ch_013.md -> 13."""
    m = re.search(r"ch[_-]?(\d+)", filepath.name, re.IGNORECASE)
    return int(m.group(1)) if m else 9999


# 结构标签/字段名等“看起来像专名、其实是母版说明文字”的噪声词，不应作为实体。
_ENTITY_NOISE = {
    "地位", "核心掌权人物", "利益算盘与底层动机", "核心人物", "利益算盘", "长线阴谋",
    "核心基本盘", "协同纽带", "地理特征", "空间尺度", "与外界距离", "烟火气息",
    "步行/马车", "特殊载具/飞舟", "第一阶", "第二阶", "第三阶", "第四阶", "第五阶",
    "第六阶", "第七阶", "第八阶", "第九阶", "终极极境", "基础阶梯", "中阶进阶",
    "高阶绝顶", "运作逻辑", "升级与进化路径", "负荷与消耗", "防滥用边界",
    "货币级别", "兑换基准", "对应消费场景",
}

def _is_proper_entity_name(name: str) -> bool:
    """Rejects template labels/field names and unclosed placeholders."""
    if not name:
        return False
    name = name.strip()
    if "[" in name or "]" in name or "：" in name or ":" in name:
        return False
    if name in _ENTITY_NOISE:
        return False
    # 纯字段说明（含斜杠分隔的模板提示语）不视为实体
    if "/" in name and len(name) <= 8:
        return False
    return True


def _load_entity_registry(workspace_dir: Path) -> dict:
    """Build comprehensive entity registry from workspace.
    Returns dict: { entity_name: entity_type }
    entity_type in: 'character', 'faction', 'location', 'item', 'concept'
    """
    registry = {}

    # 1. Characters from character_index.md
    index_file = workspace_dir / "02_characters" / "character_index.md"
    if index_file.exists():
        content = index_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("|") and not any(
                h in line for h in ["角色姓名", ":---", "---"]
            ):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts:
                    name = re.sub(r"[*_`#]", "", parts[0]).strip()
                    name = re.sub(r"\s*[（(].*?[）)]", "", name).strip()
                    if name and 2 <= len(name) <= 10 and not has_placeholder(name):
                        registry[name] = "character"

    # 2. Characters from profiles/
    profiles_dir = workspace_dir / "02_characters" / "profiles"
    if profiles_dir.exists():
        for pfile in profiles_dir.glob("*.md"):
            if pfile.name.startswith(".") or "template" in pfile.name:
                continue
            content = pfile.read_text(encoding="utf-8")
            m = re.search(r"#+\s*(?:角色(?:姓名)?[：:]\s*)?([^\n(（\s#*]+)", content)
            if m:
                cname = re.sub(r"[*_`#]", "", m.group(1)).strip()
                if cname and 2 <= len(cname) <= 10 and not has_placeholder(cname):
                    registry[cname] = "character"

    # 3. Factions from factions.md
    factions_file = workspace_dir / "01_world" / "factions.md"
    if factions_file.exists():
        content = factions_file.read_text(encoding="utf-8")
        # Extract bold names and heading names
        for m in re.finditer(r"\*\*([^\*]{2,12})\*\*", content):
            name = m.group(1).strip()
            if len(name) >= 2 and _is_proper_entity_name(name):
                registry.setdefault(name, "faction")
        for m in re.finditer(r"###\s*阵营\s*\w+[：:．·]\s*(.+?)[\s(（]", content):
            name = m.group(1).strip()
            if len(name) >= 2 and _is_proper_entity_name(name):
                registry.setdefault(name, "faction")

    # 4. Locations from geography.md
    geo_file = workspace_dir / "01_world" / "geography.md"
    if geo_file.exists():
        content = geo_file.read_text(encoding="utf-8")
        for m in re.finditer(r"[*#【]+\s*([^\n*#】]{2,10})\s*[】*#]", content):
            name = m.group(1).strip()
            if len(name) >= 2 and _is_proper_entity_name(name):
                registry.setdefault(name, "location")

    # 5. Items and concepts from world_rules.md + current_state.md
    for src_file in [
        workspace_dir / "01_world" / "world_rules.md",
        workspace_dir / "04_timeline_and_state" / "current_state.md",
    ]:
        if src_file.exists():
            content = src_file.read_text(encoding="utf-8")
            for m in re.finditer(r"【([^\u3011]{2,12})】", content):
                name = m.group(1).strip()
                if _is_proper_entity_name(name) and not has_placeholder(name):
                    registry.setdefault(name, "concept")

    # 6. Items from chekhov_guns.md
    guns_file = workspace_dir / "04_timeline_and_state" / "chekhov_guns.md"
    if guns_file.exists():
        content = guns_file.read_text(encoding="utf-8")
        for m in re.finditer(r"《([^》]{2,20})》", content):
            name = m.group(1).strip()
            if _is_proper_entity_name(name) and not has_placeholder(name):
                registry.setdefault(name, "item")

    return registry


def _load_chekhov_guns(workspace_dir: Path) -> list:
    """Load Chekhov guns with their plant chapters and keywords."""
    guns = []
    guns_file = workspace_dir / "04_timeline_and_state" / "chekhov_guns.md"
    if not guns_file.exists():
        return guns

    content = guns_file.read_text(encoding="utf-8")
    for line in content.splitlines():
        if not line.startswith("|") or "伏笔 ID" in line or ":---" in line:
            continue
        if has_placeholder(line):
            continue  # 母版示例占位行，不是真实伏笔
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 4:
            gun_id = re.sub(r"[*_`]", "", parts[0]).strip()
            gun_name = re.sub(r"[*_`《》]", "", parts[1]).strip()
            plant_ch_match = re.search(r"(\d+)", parts[2])
            plant_ch = int(plant_ch_match.group(1)) if plant_ch_match else 1
            status = parts[3] if len(parts) > 3 else ""
            # Extract meaningful keywords from the gun name
            keywords = [kw for kw in re.findall(r"[\u4e00-\u9fa5]{2,6}", gun_name) if len(kw) >= 2]
            guns.append({
                "id": gun_id,
                "name": gun_name,
                "plant_chapter": plant_ch,
                "status": status,
                "keywords": keywords,
            })
    return guns


def _load_prior_chapters(workspace_dir: Path, current_ch_num: int) -> dict:
    """Load text of all finalized chapters before the current one.
    Returns: { chapter_num: text_content }
    """
    prior = {}
    manuscript_dir = workspace_dir / "05_manuscript"
    if not manuscript_dir.exists():
        return prior

    all_finalized = sorted(
        manuscript_dir.glob("**/finalized/ch_*.md"),
        key=natural_chapter_sort_key,
    )
    for f in all_finalized:
        ch_num = _extract_chapter_number(f)
        if ch_num < current_ch_num:
            prior[ch_num] = f.read_text(encoding="utf-8")
    return prior


def _extract_proper_nouns_from_text(text: str) -> set:
    """Extract likely proper nouns (Chinese 2-6 char) enclosed in special markers."""
    nouns = set()
    # 【XX】 bracketed terms
    for m in re.finditer(r"【([^\u3011]{2,10})】", text):
        nouns.add(m.group(1).strip())
    # 《XX》 book-title marks
    for m in re.finditer(r"《([^》]{2,14})》", text):
        nouns.add(m.group(1).strip())
    return nouns


def _build_reader_knowledge(prior_texts: dict, entity_registry: dict) -> set:
    """Build the set of entity names a reader would know from prior chapters."""
    known = set()
    for ch_num in sorted(prior_texts.keys()):
        text = prior_texts[ch_num]
        for name in entity_registry:
            if name in text:
                known.add(name)
    return known


# ─────────────────────────────────────────────────────────────────────
# 8 Detection Algorithms
# ─────────────────────────────────────────────────────────────────────

def detect_phantom_entities(
    text: str, lines: list, entity_registry: dict,
    reader_knowledge: set, current_ch_num: int
) -> list:
    """Algorithm 1: Phantom Entity Detector
    Finds entities that appear in the text but have never been introduced
    to the reader in prior chapters or earlier in this chapter.
    """
    alerts = []
    # Track entities appearing in this chapter, paragraph by paragraph
    introduced_this_chapter = set()

    # Characters are the most critical - readers get confused by unknown names
    char_entities = {n for n, t in entity_registry.items() if t == "character"}

    # Build intro patterns (indicating first mention with explanation)
    intro_patterns = [
        r"名叫|名为|叫做|名号|是.*?的|自称|人称|唤作|绰号|乃是|正是|本是|原是|时任|现任",
        r"(?:此人|那人|对方|这人)[正是乃是为系]",
        r"(?:巡检|副使|主官|执事|管事|堂主|掌柜|朝奉|刺客|死士|孤儿|老汉|老者|少年|女子|男子|少主|长老|宗主|统领|差役|打手|帮众|捕头|知县|将军|武师|首领)[，,、\s——\-]+",
        r"[，,]\s*(?:乃是|正是|是|本是|原是|时任|现任|作为|属于|时任)",
    ]

    for line_idx, line in enumerate(lines):
        clean_line = line.strip()
        if not clean_line or clean_line.startswith("#"):
            continue

        for name in char_entities:
            if name not in clean_line:
                continue
            if name in reader_knowledge or name in introduced_this_chapter:
                introduced_this_chapter.add(name)
                continue

            # Check if this line or surrounding context has introduction
            context_start = max(0, line_idx - 2)
            context_end = min(len(lines), line_idx + 3)
            context = "\n".join(lines[context_start:context_end])

            has_intro = any(
                re.search(pat, context) for pat in intro_patterns
            )

            if not has_intro:
                # First chapter is exempt - everything is new
                if current_ch_num <= 1:
                    introduced_this_chapter.add(name)
                    continue

                preview = (clean_line[:40] + "...") if len(clean_line) > 40 else clean_line
                alerts.append({
                    "severity": "CRITICAL",
                    "detector": "幽灵实体",
                    "line": line_idx + 1,
                    "entity": name,
                    "entity_type": "character",
                    "message": f"角色「{name}」在前文中从未出场或介绍，读者可能不知道这是谁",
                    "preview": preview,
                })

            introduced_this_chapter.add(name)

    return alerts


def detect_info_density_overload(
    text: str, lines: list, entity_registry: dict
) -> list:
    """Algorithm 2: Information Density Heatmap
    Detects passages with too many unique proper nouns crammed together.
    """
    alerts = []
    WINDOW_SIZE = 200  # characters
    STEP = 80
    THRESHOLD = 6  # unique proper nouns per window

    # Build line offset map for locating line numbers
    full_text = "\n".join(lines)
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

    entity_names = set(entity_registry.keys())

    for i in range(0, max(1, len(full_text) - WINDOW_SIZE + 1), STEP):
        window = full_text[i:i + WINDOW_SIZE]
        # Skip windows that are mostly headings or blank
        if window.count("#") > 3:
            continue

        found_entities = set()
        for name in entity_names:
            if name in window:
                found_entities.add(name)

        if len(found_entities) >= THRESHOLD:
            line_num = get_line_num(i)
            preview = window.replace("\n", " ").strip()
            preview = (preview[:50] + "...") if len(preview) > 50 else preview
            alerts.append({
                "severity": "WARNING",
                "detector": "信息密度过载",
                "line": line_num,
                "entity_count": len(found_entities),
                "entities": sorted(found_entities)[:8],
                "message": f"200 字内出现 {len(found_entities)} 个不同专有名词，读者信息消化压力大",
                "preview": preview,
            })

    # Deduplicate overlapping windows - keep only the worst per ~5 line range
    if alerts:
        deduped = []
        alerts.sort(key=lambda a: a["line"])
        last_line = -10
        for a in alerts:
            if a["line"] - last_line >= 5:
                deduped.append(a)
                last_line = a["line"]
            elif a["entity_count"] > deduped[-1]["entity_count"]:
                deduped[-1] = a
                last_line = a["line"]
        alerts = deduped

    return alerts


def detect_pronoun_fog(text: str, lines: list, entity_registry: dict) -> list:
    """Algorithm 3: Pronoun Fog Zone Detector
    Detects passages where multiple same-gender characters are present
    and pronouns are used without name anchors.
    """
    alerts = []
    char_names = [n for n, t in entity_registry.items() if t == "character"]

    # Scan in paragraph chunks (groups of consecutive non-empty lines)
    paragraphs = []
    current_para = []
    current_start = 0
    for idx, line in enumerate(lines):
        if line.strip():
            if not current_para:
                current_start = idx
            current_para.append(line)
        else:
            if current_para:
                paragraphs.append((current_start, current_para))
                current_para = []
    if current_para:
        paragraphs.append((current_start, current_para))

    # For each paragraph, check if multiple characters are present
    for para_start, para_lines in paragraphs:
        para_text = "\n".join(para_lines)
        if len(para_text) < 100:
            continue

        # Find characters present in this paragraph
        present_chars = [n for n in char_names if n in para_text]
        if len(present_chars) < 2:
            continue

        # Count pronoun usage vs name anchors in consecutive sentences
        sentences = re.split(r"[。！？\n]+", para_text)
        pronoun_streak = 0
        max_streak = 0
        streak_start_line = para_start

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            has_name = any(n in sent for n in present_chars)
            # Count "他/她/其" pronouns (excluding inside quotes for dialogue)
            # Remove quoted text for pronoun counting
            unquoted = re.sub(r"\u201c[^\u201d]*\u201d", "", sent)
            pronoun_count = len(re.findall(r"[他她其](?:[的们]|自己)?", unquoted))

            if pronoun_count > 0 and not has_name:
                pronoun_streak += 1
            else:
                if pronoun_streak > max_streak:
                    max_streak = pronoun_streak
                pronoun_streak = 0

        if pronoun_streak > max_streak:
            max_streak = pronoun_streak

        if max_streak >= 4:
            preview_text = para_text[:60].replace("\n", " ")
            preview = (preview_text + "...") if len(preview_text) >= 60 else preview_text
            alerts.append({
                "severity": "WARNING",
                "detector": "代词迷雾区",
                "line": para_start + 1,
                "pronoun_streak": max_streak,
                "present_characters": present_chars[:5],
                "message": f"连续 {max_streak} 句使用代词无人名锚定，在场角色 {len(present_chars)} 人，读者可能分不清谁是谁",
                "preview": preview,
            })

    return alerts


def detect_dormant_thread_no_recall(
    text: str, lines: list, guns: list, current_ch_num: int,
    prior_texts: dict
) -> list:
    """Algorithm 4: Dormant Thread No-Recall Detector
    When text references a Chekhov gun planted >= 8 chapters ago,
    checks if there's a recall/reminder phrase nearby.
    """
    alerts = []
    DORMANT_THRESHOLD = 8  # chapters since last mention

    recall_patterns = [
        r"当初|此前|先前|之前|早在|那时|当日|彼时|曾经|上次|记得",
        r"那枚|那柄|那张|那本|那份|那座",
        r"原来|想起|忆起|念及|想到了",
    ]

    for gun in guns:
        if "Resolved" in gun.get("status", ""):
            continue

        chapters_since = current_ch_num - gun["plant_chapter"]
        if chapters_since < DORMANT_THRESHOLD:
            continue

        # Check if gun keywords appear in current chapter
        for kw in gun["keywords"]:
            if len(kw) < 2 or kw not in text:
                continue

            # Find the line where the keyword appears
            for line_idx, line in enumerate(lines):
                if kw not in line:
                    continue

                # Check surrounding context (300 chars / ~6 lines) for recall phrases
                context_start = max(0, line_idx - 3)
                context_end = min(len(lines), line_idx + 4)
                context = "\n".join(lines[context_start:context_end])

                has_recall = any(
                    re.search(pat, context) for pat in recall_patterns
                )

                if not has_recall:
                    preview = (line.strip()[:50] + "...") if len(line.strip()) > 50 else line.strip()
                    alerts.append({
                        "severity": "WARNING",
                        "detector": "休眠伏笔无召回",
                        "line": line_idx + 1,
                        "gun_id": gun["id"],
                        "gun_name": gun["name"],
                        "chapters_since": chapters_since,
                        "keyword": kw,
                        "message": f"引用了 {chapters_since} 章前埋下的伏笔「{gun['name']}」(关键词:「{kw}」)，但附近缺少回忆提示，读者可能已遗忘",
                        "preview": preview,
                    })
                break  # Only alert once per keyword per gun

    return alerts


def detect_hard_scene_cuts(text: str, lines: list) -> list:
    """Algorithm 5: Hard Scene Cut Detector
    Detects abrupt time/location jumps between paragraphs
    without transition phrases.
    """
    alerts = []

    time_markers = [
        r"翌日|次日|第二[天日]|三[天日]后|隔日|黄昏|清晨|午后|傍晚|入夜|深夜|凌晨|破晓|日落",
        r"一[个炷]时辰[后前]|半[个柱]时辰|片刻[后前]|须臾|稍后|不多时|半日|数日",
    ]
    location_markers = [
        r"回到|来到|抵达|踏入|走进|步入|离开|转身|赶往|奔赴|赶赴",
    ]
    transition_phrases = [
        r"翌日|次日|第二天|三天后|当天.*?时|到了.*?时|待到|等到|不多时|片刻后",
        r"回到|来到|抵达|踏入|另一边|与此同时|就在.*?时|此时此刻",
        r"话分两头|场景一转|画面一切",
        r"───|——|◆|▲|※",  # Explicit scene break markers
    ]

    # Identify paragraph boundaries (blank lines)
    para_boundaries = []
    for idx, line in enumerate(lines):
        if not line.strip() and idx > 0 and idx < len(lines) - 1:
            para_boundaries.append(idx)

    for boundary_idx in para_boundaries:
        # Get last 2 lines before break and first 2 lines after
        before_start = max(0, boundary_idx - 3)
        before_text = "\n".join(lines[before_start:boundary_idx])

        after_end = min(len(lines), boundary_idx + 4)
        after_lines = [l for l in lines[boundary_idx + 1:after_end] if l.strip()]
        if not after_lines:
            continue
        after_text = "\n".join(after_lines)

        # Skip dialogue lines as scene cuts (characters discussing time/place in dialogue is normal conversation)
        first_line = after_lines[0].strip()
        if first_line.startswith(("“", "\"", "‘", "'")):
            continue

        # Strip quoted dialogue to avoid dialogue time markers triggering narrative cut alerts
        narrative_after = re.sub(r'[“"][^”"]*[”"]', '', after_text)

        # Check if there's a time/location shift in narrative
        has_time_shift = any(re.search(p, narrative_after) for p in time_markers)
        has_loc_shift = any(re.search(p, narrative_after) for p in location_markers)

        if not (has_time_shift or has_loc_shift):
            continue

        # Check if there's a transition phrase
        has_transition = any(re.search(p, after_text) for p in transition_phrases)

        if not has_transition:
            preview = after_lines[0].strip() if after_lines else ""
            preview = (preview[:50] + "...") if len(preview) > 50 else preview
            shift_type = "时空" if (has_time_shift and has_loc_shift) else ("时间" if has_time_shift else "地点")
            alerts.append({
                "severity": "INFO",
                "detector": "硬切场景",
                "line": boundary_idx + 2,
                "shift_type": shift_type,
                "message": f"{shift_type}跳转缺少过渡衔接，读者可能产生短暂迷失",
                "preview": preview,
            })

    return alerts


def detect_causal_gaps(text: str, lines: list) -> list:
    """Algorithm 6: Causal Gap Detector
    Detects 'therefore/so' connectors without preceding cause,
    and excessive 'suddenly' usage without foreshadowing.
    """
    alerts = []

    # 6a. "于是/因此/所以/便" without preceding cause
    causal_connectors = r"于是|因此|所以(?!然)|故而|是以"
    cause_indicators = r"因为|由于|既然|鉴于|考虑到|想到|念及|得知|发现|看到|听到|察觉|意识到"

    for line_idx, line in enumerate(lines):
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue

        for m in re.finditer(causal_connectors, clean):
            # Check preceding 3 lines + current line before connector for cause
            context_start = max(0, line_idx - 3)
            context_lines = lines[context_start:line_idx + 1]
            context = "\n".join(context_lines)

            has_cause = bool(re.search(cause_indicators, context))
            # Also check if there's dialogue that might contain the cause
            has_dialogue_cause = bool(re.search(r"\u201c[^\u201d]*\u201d", context))

            if not has_cause and not has_dialogue_cause:
                preview = (clean[:50] + "...") if len(clean) > 50 else clean
                alerts.append({
                    "severity": "INFO",
                    "detector": "因果虚接",
                    "line": line_idx + 1,
                    "connector": m.group(0),
                    "message": f"使用因果连接词「{m.group(0)}」但前文缺少明确原因铺垫",
                    "preview": preview,
                })

    # 6b. Excessive "突然/骤然/忽然" density
    sudden_words = re.findall(r"突然|骤然|忽然|猛然|陡然", text)
    if len(sudden_words) >= 4:
        alerts.append({
            "severity": "WARNING",
            "detector": "因果虚接",
            "line": 1,
            "count": len(sudden_words),
            "message": f"全章「突然/骤然/忽然」类词汇出现 {len(sudden_words)} 次，过多则削弱惊讶感且暴露铺垫不足",
            "preview": f"出现词汇: {', '.join(sudden_words[:6])}",
        })

    return alerts


def detect_floating_dialogue(text: str, lines: list) -> list:
    """Algorithm 7: Floating Dialogue Detector
    Detects consecutive dialogue lines without action/narration
    attribution, making it unclear who is speaking.
    """
    alerts = []
    STREAK_THRESHOLD = 4  # consecutive dialogue-only lines

    dialogue_streak = 0
    streak_start = 0

    for line_idx, line in enumerate(lines):
        clean = line.strip()
        if not clean:
            if dialogue_streak >= STREAK_THRESHOLD:
                preview = lines[streak_start].strip()[:40] + "..."
                alerts.append({
                    "severity": "WARNING",
                    "detector": "悬空对白",
                    "line": streak_start + 1,
                    "streak_length": dialogue_streak,
                    "message": f"连续 {dialogue_streak} 行对白无动作/神态插叙标注说话人，读者可能分不清谁在说话",
                    "preview": preview,
                })
            dialogue_streak = 0
            continue

        # Check if this line is pure dialogue (starts with or is entirely a quote)
        is_pure_dialogue = bool(re.match(r"^\s*\u201c[^\u201d]*\u201d\s*$", clean))

        if is_pure_dialogue:
            if dialogue_streak == 0:
                streak_start = line_idx
            dialogue_streak += 1
        else:
            if dialogue_streak >= STREAK_THRESHOLD:
                preview = lines[streak_start].strip()[:40] + "..."
                alerts.append({
                    "severity": "WARNING",
                    "detector": "悬空对白",
                    "line": streak_start + 1,
                    "streak_length": dialogue_streak,
                    "message": f"连续 {dialogue_streak} 行对白无动作/神态插叙标注说话人，读者可能分不清谁在说话",
                    "preview": preview,
                })
            dialogue_streak = 0

    # Handle streak at end of file
    if dialogue_streak >= STREAK_THRESHOLD:
        preview = lines[streak_start].strip()[:40] + "..."
        alerts.append({
            "severity": "WARNING",
            "detector": "悬空对白",
            "line": streak_start + 1,
            "streak_length": dialogue_streak,
            "message": f"连续 {dialogue_streak} 行对白缺少说话人标注",
            "preview": preview,
        })

    return alerts


def detect_unexplained_concepts(
    text: str, lines: list, entity_registry: dict,
    reader_knowledge: set, current_ch_num: int
) -> list:
    """Algorithm 8: Unexplained New Concept Detector
    Detects world-building terms (realms, techniques, artifacts) that
    appear for the first time without nearby explanation.
    """
    alerts = []

    concept_entities = {
        n for n, t in entity_registry.items()
        if t in ("concept", "item") and len(n) >= 3
    }

    explanation_patterns = [
        r"所谓|即是|也就是|意为|指的是|乃是|便是|正是|相当于",
        r"一种|一类|一门|一套|一枚|一柄|一卷|一部",
        r"据说|传闻|相传|古籍记载|典籍所载",
    ]

    for concept in concept_entities:
        if concept in reader_knowledge:
            continue
        if concept not in text:
            continue

        # First chapter is more lenient - lots of world-building
        if current_ch_num <= 1:
            continue

        # Find first occurrence
        for line_idx, line in enumerate(lines):
            if concept not in line:
                continue

            # Check surrounding context for explanation
            context_start = max(0, line_idx - 1)
            context_end = min(len(lines), line_idx + 4)
            context = "\n".join(lines[context_start:context_end])

            has_explanation = any(
                re.search(pat, context) for pat in explanation_patterns
            )

            # Also check if it's inside 【】 which typically signals a system notification
            in_brackets = bool(re.search(r"【" + re.escape(concept) + r"】", context))

            if not has_explanation and not in_brackets:
                preview = (line.strip()[:50] + "...") if len(line.strip()) > 50 else line.strip()
                alerts.append({
                    "severity": "INFO",
                    "detector": "新概念无解释",
                    "line": line_idx + 1,
                    "concept": concept,
                    "message": f"世界观术语「{concept}」首次出现但附近缺少解释性说明",
                    "preview": preview,
                })
            break  # Only check first occurrence

    return alerts


# ─────────────────────────────────────────────────────────────────────
# Main Orchestrator
# ─────────────────────────────────────────────────────────────────────

SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
DETECTOR_EMOJI = {
    "幽灵实体": "👻",
    "信息密度过载": "🧠",
    "代词迷雾区": "🌫️",
    "休眠伏笔无召回": "💤",
    "硬切场景": "✂️",
    "因果虚接": "🔗",
    "悬空对白": "💬",
    "新概念无解释": "❓",
}


def audit_reader_confusion(
    workspace_dir: Path, target_chapter: str = None, as_json: bool = False
) -> dict:
    """Main entry point: run all 8 detectors on target chapter(s)."""

    manuscript_dir = workspace_dir / "05_manuscript"
    files = find_manuscript_files(manuscript_dir, target_chapter)

    if not files:
        msg = f"未在 {workspace_dir.name}/05_manuscript 中找到目标章节文件。"
        if as_json:
            result = {"error": msg}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return result
        print(f"ℹ️ {msg}")
        return {"status": "SKIP", "critical_count": 0}

    # Load workspace data
    entity_registry = _load_entity_registry(workspace_dir)
    guns = _load_chekhov_guns(workspace_dir)

    if not as_json:
        print("=" * 76)
        print(" 👁️ [Universal Novel Studio · 读者阅读卡点与懵逼检测引擎]")
        print("=" * 76)
        print(f" 📂 工作区: {workspace_dir.name} | 📊 已注册实体: {len(entity_registry)} 个 | 🎯 活跃伏笔: {len(guns)} 条")

    all_reports = []
    total_critical = 0
    total_warning = 0
    total_info = 0

    for filepath in files:
        content = filepath.read_text(encoding="utf-8")
        lines = content.splitlines()
        ch_num = _extract_chapter_number(filepath)
        rel_path = filepath.relative_to(workspace_dir)

        # Load prior chapters for reader knowledge building
        prior_texts = _load_prior_chapters(workspace_dir, ch_num)
        reader_knowledge = _build_reader_knowledge(prior_texts, entity_registry)

        # Run all 8 detectors
        all_alerts = []
        all_alerts.extend(detect_phantom_entities(content, lines, entity_registry, reader_knowledge, ch_num))
        all_alerts.extend(detect_info_density_overload(content, lines, entity_registry))
        all_alerts.extend(detect_pronoun_fog(content, lines, entity_registry))
        all_alerts.extend(detect_dormant_thread_no_recall(content, lines, guns, ch_num, prior_texts))
        all_alerts.extend(detect_hard_scene_cuts(content, lines))
        all_alerts.extend(detect_causal_gaps(content, lines))
        all_alerts.extend(detect_floating_dialogue(content, lines))
        all_alerts.extend(detect_unexplained_concepts(content, lines, entity_registry, reader_knowledge, ch_num))

        # Sort by severity then line number
        all_alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 9), a.get("line", 0)))

        critical = [a for a in all_alerts if a["severity"] == "CRITICAL"]
        warnings = [a for a in all_alerts if a["severity"] == "WARNING"]
        infos = [a for a in all_alerts if a["severity"] == "INFO"]

        total_critical += len(critical)
        total_warning += len(warnings)
        total_info += len(infos)

        report = {
            "file": str(rel_path),
            "chapter": ch_num,
            "critical_count": len(critical),
            "warning_count": len(warnings),
            "info_count": len(infos),
            "alerts": all_alerts,
        }
        all_reports.append(report)

        if not as_json:
            if critical:
                status = f"❌ CRITICAL ({len(critical)}) + WARNING ({len(warnings)}) + INFO ({len(infos)})"
            elif warnings:
                status = f"⚠️ WARNING ({len(warnings)}) + INFO ({len(infos)})"
            elif infos:
                status = f"💡 INFO ({len(infos)})"
            else:
                status = "✅ 读者视角畅通无阻"

            print(f"\n📄 {rel_path} (第 {ch_num} 章) → {status}")

            if all_alerts:
                # Group by detector
                by_detector = defaultdict(list)
                for a in all_alerts:
                    by_detector[a["detector"]].append(a)

                for det_name, det_alerts in by_detector.items():
                    emoji = DETECTOR_EMOJI.get(det_name, "🔍")
                    print(f"   {emoji} ──【{det_name}】({len(det_alerts)} 处)──")
                    for a in det_alerts[:5]:  # Show at most 5 per detector
                        sev_icon = "🚨" if a["severity"] == "CRITICAL" else ("⚠️" if a["severity"] == "WARNING" else "💡")
                        line_info = f"L{a['line']}" if a.get("line") else ""
                        print(f"      {sev_icon} [{a['severity']}] {line_info}: {a['message']}")
                        if a.get("preview"):
                            print(f"         → \"{a['preview']}\"")
                    if len(det_alerts) > 5:
                        print(f"      ... (其余 {len(det_alerts) - 5} 处略)")

    # Final summary
    overall_status = "FAIL" if total_critical > 0 else ("REVIEW" if total_warning > 0 else "PASS")

    result = {
        "workspace": workspace_dir.name,
        "target": target_chapter or "all",
        "total_files": len(files),
        "total_critical": total_critical,
        "total_warning": total_warning,
        "total_info": total_info,
        "status": overall_status,
        "reports": all_reports,
    }

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n" + "=" * 76)
        if total_critical > 0:
            print(f"❌ [读者懵逼门禁未通过] 发现 {total_critical} 处 CRITICAL 级阅读卡点！必须修正后方可定稿！")
        elif total_warning > 0:
            print(f"⚠️ [检测完成] 发现 {total_warning} 处 WARNING + {total_info} 处 INFO，建议审阅修正。")
        else:
            print(f"✅ [读者视角畅通] 未发现阅读卡点，读者视角一路丝滑！")
        print("=" * 76)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Universal Novel Studio - 读者阅读卡点与懵逼检测引擎"
    )
    parser.add_argument("-c", "--chapter", type=str, default=None, help="目标章节 (如 ch_014)")
    parser.add_argument("-w", "--workspace", type=str, default=None, help="工作区路径")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    workspace_dir = resolve_workspace(args.workspace)
    result = audit_reader_confusion(workspace_dir, args.chapter, as_json=args.json)

    if isinstance(result, dict) and result.get("status") == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
