# -*- coding: utf-8 -*-
"""
Universal Novel Studio - Shared Utilities & Core Literary Engine (novel_utils.py)
Centralizes common infrastructure and pattern libraries for diagnostic tools:
- Workspace path resolution & fallback
- Natural alphanumeric chapter sorting
- Clean manuscript file discovery
- Registered character extraction from index and profiles
- Generic Syntactic Skeletons, Semantic Redundancy Clusters & AI Cliché Rules
  (v2: 通用兜底 + 题材特定词表动态叠加，不再硬编码玄幻偏见)
- Ground Truth loader for State Machine (Character Arcs & Chekhov Guns)
- Unsupervised N-gram burstiness & semantic redundancy analyzers
- UTF-8 console reconfiguration
"""

import sys
import re
from pathlib import Path
from collections import defaultdict


def reconfigure_utf8():
    """Ensure UTF-8 encoding on Windows consoles."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def project_root() -> Path:
    """Returns the repository root (parent of the tools/ directory)."""
    return Path(__file__).resolve().parent.parent


def resolve_workspace(workspace_arg=None) -> Path:
    """Resolves target workspace directory.

    Resolution order:
      1. Explicit --workspace argument (relative paths are anchored at repo root).
      2. ``workspace_dir`` declared in novel_config.yaml (anchored at repo root).
      3. Default ``<repo_root>/novel_workspace``.
    """
    base_dir = project_root()
    if workspace_arg:
        w_path = Path(workspace_arg)
        if not w_path.is_absolute():
            w_path = (base_dir / w_path).resolve()
        return w_path
    cfg = load_studio_config()
    declared = cfg.get("project", {}).get("workspace_dir")
    if declared:
        return (base_dir / declared).resolve()
    return (base_dir / "novel_workspace").resolve()


# ---------------------------------------------------------------------------
# Lightweight novel_config.yaml loader (zero third-party dependencies)
# ---------------------------------------------------------------------------
_CONFIG_CACHE = None


def load_studio_config() -> dict:
    """Parses the small subset of novel_config.yaml the toolchain actually needs.

    Supports nested mappings via indentation and simple ``key: value`` scalars
    (quoted strings, ints, floats, bools).  Returns defaults when the file is
    absent or unparsable, so every tool keeps working out-of-the-box.
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    cfg = {
        "project": {"workspace_dir": "novel_workspace"},
        "generation": {
            "target_word_count": {"min": 2500, "max": 5000, "recommended": 3200}
        },
        "linter_thresholds": {
            "hard_gate_min_word_count": 2500,
            "max_consecutive_breathless_chars": 75,
        },
    }
    cfg_path = project_root() / "novel_config.yaml"
    try:
        if cfg_path.exists():
            stack = [(-1, cfg)]
            for raw in cfg_path.read_text(encoding="utf-8").splitlines():
                line = raw.split("#", 1)[0].rstrip() if "#" in raw else raw.rstrip()
                if not line.strip() or ":" not in line:
                    continue
                indent = len(line) - len(line.lstrip(" "))
                key, _, val = line.strip().partition(":")
                key = key.strip()
                val = val.strip()
                while stack and indent <= stack[-1][0]:
                    stack.pop()
                parent = stack[-1][1]
                if val == "":
                    node = {}
                    parent[key] = node
                    stack.append((indent, node))
                else:
                    parent[key] = _parse_yaml_scalar(val)
    except Exception:
        pass

    _CONFIG_CACHE = cfg
    return cfg


def _parse_yaml_scalar(val: str):
    """Coerces a YAML scalar string into bool/int/float/str."""
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        return val[1:-1]
    low = val.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", ""):
        return None
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


# ---------------------------------------------------------------------------
# Chapter identity helpers (boundary-safe, works past chapter 100)
# ---------------------------------------------------------------------------
def chapter_token_to_num(token) -> int:
    """Extracts the chapter number from a token like 'ch_004', 'ch-12', '4' or 4."""
    if token is None:
        return None
    if isinstance(token, int):
        return token
    m = re.search(r"(\d+)", str(token))
    return int(m.group(1)) if m else None


def chapter_number_from_name(name: str):
    """Extracts the chapter number embedded in a file/directory name (None if absent)."""
    m = re.search(r"ch[_-]?0*(\d+)(?![0-9])", str(name), re.IGNORECASE)
    if not m:
        m = re.search(r"chapter[_-]?0*(\d+)(?![0-9])", str(name), re.IGNORECASE)
    return int(m.group(1)) if m else None


def file_matches_chapter(path: Path, target_chapter) -> bool:
    """Boundary-safe chapter match.

    ``ch_001`` / ``1`` only matches files whose chapter token is exactly 1,
    so 'ch_001' no longer accidentally matches 'ch_010' or 'ch_0010'.
    """
    target_num = chapter_token_to_num(target_chapter)
    if target_num is None:
        return str(target_chapter) in str(path).replace("\\", "/")
    return chapter_number_from_name(path.name) == target_num


def latest_chapter_number(manuscript_dir: Path, require_finalized: bool = True):
    """Highest chapter number present in the manuscript tree (0 if none)."""
    if not manuscript_dir or not manuscript_dir.exists():
        return 0
    if require_finalized:
        files = manuscript_dir.glob("**/finalized/ch_*.md")
    else:
        files = manuscript_dir.glob("**/ch_*.md")
    nums = [chapter_number_from_name(f.name) for f in files
            if not f.name.startswith(".") and chapter_number_from_name(f.name) is not None]
    return max(nums) if nums else 0


# ---------------------------------------------------------------------------
# Template placeholder detection
# ---------------------------------------------------------------------------
PLACEHOLDER_RE = re.compile(r"\[[^\[\]]*[\u4e00-\u9fa5][^\[\]]*\]")


def has_placeholder(text) -> bool:
    """True if the text still contains an unfilled [中文] template placeholder."""
    if text is None:
        return False
    return bool(PLACEHOLDER_RE.search(str(text)))


_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")


def is_table_separator(line: str) -> bool:
    """True for markdown table separator rows like '|---|:---:|---|' (any spacing)."""
    if not line or not line.strip().startswith("|"):
        return False
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return all(_SEPARATOR_CELL_RE.match(c) for c in cells if c != "") and any(cells)


def is_table_header(line: str, keywords=()) -> bool:
    """True for table header rows (contains a header keyword) or separator rows."""
    if is_table_separator(line):
        return True
    return any(k in line for k in keywords)


# ---------------------------------------------------------------------------
# Atomic file writes (never leave a half-written state file on crash)
# ---------------------------------------------------------------------------
def atomic_write_text(path, text: str, encoding: str = "utf-8") -> None:
    """Writes text to `path` atomically (temp file + os.replace).

    Guarantees readers never see a truncated/half-written ledger or state file.
    """
    import os
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding=encoding, newline="") as f:
        f.write(text)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Markdown table helpers (deterministic parse / upsert / render)
# ---------------------------------------------------------------------------
def split_table_row(line: str) -> list:
    """Splits a markdown table line into trimmed cell strings."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def render_table_row(cells: list) -> str:
    """Renders a markdown table row from cell strings."""
    return "| " + " | ".join(str(c) for c in cells) + " |"


def find_table_block(lines: list, header_keyword: str):
    """Locates a markdown table whose header contains `header_keyword`.

    Returns dict with keys: header_idx, sep_idx, data_start, data_end,
    headers (list), rows (list of cell-lists), or None if not found.
    """
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and header_keyword in line and i + 1 < len(lines):
            if is_table_separator(lines[i + 1]):
                headers = split_table_row(line)
                rows = []
                j = i + 2
                while j < len(lines) and lines[j].strip().startswith("|"):
                    if is_table_separator(lines[j]):
                        j += 1
                        continue
                    rows.append(split_table_row(lines[j]))
                    j += 1
                return {
                    "header_idx": i,
                    "sep_idx": i + 1,
                    "data_start": i + 2,
                    "data_end": j,
                    "headers": headers,
                    "rows": rows,
                }
    return None


def strip_placeholders(text: str) -> str:
    """Removes all [中文] placeholder spans from a string."""
    return PLACEHOLDER_RE.sub("", str(text or ""))


def natural_chapter_sort_key(file_path: Path) -> tuple:
    """Generates natural sort key (volume_num, chapter_num, filename) for chapters."""
    path_str = str(file_path).replace("\\", "/")
    vol_match = re.search(r"vol[_-]?(\d+)", path_str, re.IGNORECASE)
    vol_num = int(vol_match.group(1)) if vol_match else 1

    ch_num = chapter_number_from_name(file_path.name)
    if ch_num is None:
        m = re.search(r"(\d+)", file_path.name)
        ch_num = int(m.group(1)) if m else 9999
    return (vol_num, ch_num, file_path.name)


def find_manuscript_files(manuscript_dir: Path, target_chapter: str = None, single_latest: bool = False) -> list:
    """Finds valid novel chapter manuscript files (finalized or raw_drafts)."""
    if not manuscript_dir.exists():
        return []

    def _excluded(f: Path) -> bool:
        norm = str(f).replace("\\", "/")
        return ("prescriptions" in norm or "snapshots" in norm
                or f.name.startswith("."))

    if target_chapter:
        matches = [
            f for f in manuscript_dir.glob("**/ch_*.md")
            if not _excluded(f) and file_matches_chapter(f, target_chapter)
        ]
        finalized = [f for f in matches if "finalized" in str(f).replace("\\", "/")]
        res = finalized if finalized else matches
        return sorted(res, key=natural_chapter_sort_key)

    finalized = sorted(
        [
            f for f in manuscript_dir.glob("**/finalized/ch_*.md")
            if not f.name.startswith(".")
        ],
        key=natural_chapter_sort_key
    )
    if finalized:
        return [finalized[-1]] if single_latest else finalized

    raw_drafts = sorted(
        [
            f for f in manuscript_dir.glob("**/raw_drafts/ch_*.md")
            if not f.name.startswith(".")
        ],
        key=natural_chapter_sort_key
    )
    if raw_drafts:
        return [raw_drafts[-1]] if single_latest else raw_drafts

    all_md = sorted(
        [
            f for f in manuscript_dir.glob("**/*.md")
            if "prescriptions" not in str(f).replace("\\", "/")
            and "snapshots" not in str(f).replace("\\", "/")
            and not f.name.startswith(".")
        ],
        key=natural_chapter_sort_key
    )
    if all_md:
        return [all_md[-1]] if single_latest else all_md
    return []


def load_registered_characters(workspace_dir: Path) -> list:
    """Extracts all registered character names (Chinese names)."""
    chars = set()
    index_file = workspace_dir / "02_characters" / "character_index.md"
    if index_file.exists():
        content = index_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("|"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts and not parts[0].startswith("[") and not parts[0].startswith(":") and not parts[0].startswith("-") and "角色" not in parts[0] and "姓名" not in parts[0]:
                    clean_name = re.sub(r"[*_`#]", "", parts[0]).strip()
                    clean_name = re.sub(r"\s*[（(].*?[）)]", "", clean_name).strip()
                    if clean_name and len(clean_name) <= 10 and not has_placeholder(clean_name):
                        chars.add(clean_name)

    profiles_dir = workspace_dir / "02_characters" / "profiles"
    if profiles_dir.exists():
        for pfile in profiles_dir.glob("*.md"):
            if not pfile.name.startswith("."):
                content = pfile.read_text(encoding="utf-8")
                m = re.search(r"#+\s*(?:角色(?:姓名)?[：:]\s*)?([^\n(（\s#*]+)", content)
                if m:
                    cname = m.group(1).strip()
                    cname = re.sub(r"[*_`#]", "", cname).strip()
                    if cname and len(cname) <= 10 and not cname.startswith("[") and not has_placeholder(cname):
                        chars.add(cname)

    return sorted(list(chars))


# ===========================================================================
# v2: 题材自适应词表加载层（Genre-Adaptive Lexicon Layer）
# ---------------------------------------------------------------------------
# 所有题材特定词表（断章关键词/语义聚类/数量词白名单/陈词模式）
# 均从 genre_profile.json 动态加载，通用代码不再硬编码玄幻偏见。
# 延迟导入 genre_profile 以避免循环引用。
# ===========================================================================

def get_genre_profile(workspace=None) -> dict:
    """延迟加载题材档案（避免循环引用）。失败时返回空 dict。"""
    try:
        from genre_profile import resolve_genre_profile
        return resolve_genre_profile(workspace)
    except Exception:
        return {}


def is_combat_genre(workspace=None) -> bool:
    """判断当前题材是否为战斗密集型（影响战斗套路检测是否启用）。"""
    prof = get_genre_profile(workspace)
    return bool(prof.get("combat_heavy", False))


def get_cliffhanger_keywords(workspace=None) -> list:
    """返回断章关键词：通用兜底 + 题材特定叠加。"""
    keywords = list(CLIFFHANGER_KEYWORDS_GENERIC)
    prof = get_genre_profile(workspace)
    extra = prof.get("cliffhanger_keywords", [])
    if extra:
        keywords.extend(extra)
    return list(dict.fromkeys(keywords))  # 去重保序


def get_semantic_clusters(workspace=None) -> list:
    """返回语义冗余聚类：通用兜底 + 题材特定叠加。"""
    clusters = list(SEMANTIC_CLUSTERS_GENERIC)
    prof = get_genre_profile(workspace)
    extra = prof.get("semantic_clusters", [])
    if extra:
        clusters.extend(extra)
    return clusters


def get_quantity_whitelist(workspace=None) -> set:
    """返回数量词白名单：通用兜底 + 题材特定叠加。"""
    whitelist = set(QUANTITY_WHITELIST_GENERIC)
    prof = get_genre_profile(workspace)
    extra = prof.get("quantity_whitelist", [])
    if extra:
        whitelist.update(extra)
    return whitelist


def get_cliche_patterns(workspace=None) -> list:
    """返回陈词滥调模式：通用兜底 + 题材特定叠加。
    战斗套路仅在 combat_heavy 题材中启用。"""
    patterns = []
    for p in GENERIC_SKELETONS:
        if p.get("combat_genre_only") and not is_combat_genre(workspace):
            continue
        patterns.append(p)
    prof = get_genre_profile(workspace)
    extra = prof.get("cliche_patterns", [])
    if extra:
        patterns.extend(extra)
    return patterns


# ---------------------------------------------------------------------------
# 通用兜底词表（Generic Fallback Lexicons）
# v2: 仅保留真正跨题材通用的内容，题材特定内容移至 genre_profile
# ---------------------------------------------------------------------------

# 通用数量词白名单（跨题材通用，题材特定在 genre_profile.quantity_whitelist 叠加）
QUANTITY_WHITELIST_GENERIC = {
    "一个", "两个", "三个", "四个", "五个", "六个", "七个", "八个", "九个", "十个",
    "十二", "十三", "十四", "十五", "二十", "三十", "五十", "一百", "数百", "数千",
    "数万", "三年", "三日", "一日", "两日", "半步", "一寸", "三寸", "一息", "数息",
    "十息", "一汪", "一尊", "一枚", "一抹", "一丝", "一柄", "一具", "一道", "一轮",
    "一团", "一口", "半截", "半天", "一夜", "半晌", "片刻", "须臾", "转瞬", "顷刻",
}

# 通用断章关键词（跨题材通用，题材特定在 genre_profile.cliffhanger_keywords 叠加）
# v2: 移除了灵鹤/玉简/飞舟/剑鸣/神芒/神轮/大世/出山等玄幻专属词
CLIFFHANGER_KEYWORDS_GENERIC = [
    "脚步声", "突如其来", "敲门声", "传讯", "杀气", "暗流", "异动", "死寂",
    "冷笑", "破空声", "警钟", "急促", "变故", "暴涨", "入局", "急报",
    "波澜", "落子", "风暴", "警报", "震动", "轰鸣", "碎裂", "崩塌",
    "沉默", "对峙", "逼近", "降临", "觉醒", "逆转", "真相", "秘密",
]

# 通用压抑氛围词（跨题材通用，题材特定在 genre_profile 叠加）
OPPRESSIVE_KEYWORDS = [
    "死寂", "阴冷", "森然", "逼仄", "沉郁", "如坠冰窟", "暗黑", "森冷", "死气沉沉",
    "压抑", "窒息", "彻骨", "冰冷死寂", "绝望", "阴沉", "灰败",
]

STOP_CHARS = set("的一是在了不有和人这中大上个国为以我时要他就出于也得着到说后自会那多可家去下地生心而便与向之但如所微此")


def build_smart_whitelist(workspace_dir: Path) -> set:
    """Dynamically builds comprehensive whitelist of character names, locations, factions, items, and numerals from workspace.

    v2: 数量词白名单从题材档案动态加载，不再硬编码古风量词。
    """
    registered_chars = load_registered_characters(workspace_dir)
    whitelist = set()
    for name in registered_chars:
        whitelist.add(name)
        for i in range(len(name) - 1):
            whitelist.add(name[i:i+2])
        if len(name) >= 3:
            for i in range(len(name) - 2):
                whitelist.add(name[i:i+3])

    # v2: 数量词白名单从题材档案动态加载（通用兜底 + 题材特定）
    whitelist.update(get_quantity_whitelist(workspace_dir))

    # 动态扫描世界观、势力、地理与状态机中的专有词汇 (100% 全题材动态自适应)
    world_dir = workspace_dir / "01_world"
    if world_dir.exists():
        for wfile in world_dir.glob("*.md"):
            if not wfile.name.startswith("."):
                content = wfile.read_text(encoding="utf-8")
                matches = re.findall(r"(?:#+\s*|【|\*\*|`)([\u4e00-\u9fa5]{2,8})(?:】|\*\*|`|\s)", content)
                for term in matches:
                    if len(term) <= 6:
                        whitelist.add(term)

    # 动态扫描当前状态机与伏笔道具别名
    state_file = workspace_dir / "04_timeline_and_state" / "current_state.md"
    if state_file.exists():
        content = state_file.read_text(encoding="utf-8")
        matches = re.findall(r"【([\u4e00-\u9fa5]{2,10})】", content)
        for term in matches:
            whitelist.add(term)

    return whitelist


# 🏛️ 高阶抽象句式骨架与 AI 味诊断正则 (Single Source of Truth)
# v2: 战斗套路标记 combat_genre_only=True，非战斗题材自动跳过
GENERIC_SKELETONS = [
    {
        "name": "虚词化修饰与状态垫片 (State Particle Abstraction)",
        "pattern": r"[\u4e00-\u9fa5]{1,4}之[色意态状感势威波气韵]",
        "suggestion": "避免过度虚词化修饰（如XX之色/之意/之态/之势），建议直接呈现具体动作、真实神态或省略垫片；但不要一刀切完全删除，若在特定语境下贴切自然，仍可酌情保留。"
    },
    {
        "name": "脸谱化神态与微表情模板 (Sensory & Facial Template)",
        "pattern": r"(?:眼底|眸中|双眸|眸底|眉宇间|眉心|心底|心头|唇角|嘴角|指尖)(?:深处)?(?:悄然|隐隐|微不可察地|极快地)?(?:掠过|闪过|浮现|泛起|升腾起|透着|多出)(?:了)?(?:一抹|一丝|几分|些许|一道)[\u4e00-\u9fa5]{1,4}",
        "suggestion": "避免'眼底掠过一丝/唇角泛起一抹'等机械化脸谱模板。可灵活选用切合当前具体情境的人物专属动作、生理本能反应、现场环境借景或纯对白；但若此处描写确属点睛之笔，可灵活保留。角色表情需多样化且符合逻辑，该是什么反应就得是什么反应。"
    },
    {
        "name": "机械比喻与套路修辞 (Mechanical Metaphor Skeleton)",
        "pattern": r"(?:宛若|仿佛|好似|恰似|犹如)[\u4e00-\u9fa5]{2,10}(?:一般|似的|模样|般的存在)",
        "suggestion": "精简'宛若XX一般/仿佛XX似的'等套路比喻，保持行文简练利落与张力；但若比喻新颖贴切，不必教条全删，依情节需要灵活取舍。"
    },
    {
        "name": "高频偷懒副词与极值修饰 (Intensifier & Adverb Overuse)",
        "pattern": r"(?:极其|极度|极为|极快|极冷|极强|极盛|极深|极细|极淡|极好|极美|极高|极低|极难|极具|极点|极准|极匀|悍然|沛莫能御|摧枯拉朽|无所遁形|悄然|隐隐|微不可察)",
        "suggestion": "此类副词常为 AI 偷懒垫片，建议动态降频，改用具象物理动作、现场声效、环境阻力或直接省略；但也不必完全剔除，合适之处仍需保留。"
    },
    {
        "name": "旁白说教与过度解释 (Over-Explanation & Preachy Clichés)",
        "pattern": r"原来.*?才是.*?的真谛|他终于明白|这一刻，?他懂了|这，?就是|人生.*?不过是一场|修仙.*?不过是一场|不得不说|未尝不[能可是]|并非不[能可是知会]|不可谓不|在某种程度上|值得一提的是|众所周知|毋庸置疑|何谓.*?？|这分明是.*?|这哪里是.*?分明是|换句话说|简而言之|总而言之|正因如此|由此可见|不言而喻|可想而知",
        "suggestion": "坚决拔除旁白跳出来当人生导师或说明书式自问自答。用具体行动、事实推进与留白代替旁白碎碎念，把感悟与反差留给读者。"
    },
    {
        "name": "辩证反差骨架泛型 (Dialectical Antithesis Skeleton)",
        "pattern": r"(?:看似|表面[上来看]*|看似寻常的?|看似漫不经心的?)[\u4e00-\u9fa5]{1,8}[，,]?(?:实则|暗地里|暗中却|骨子里却|实际上)[\u4e00-\u9fa5]{1,8}",
        "suggestion": "避免说教式'看似XX实则XX'生硬对比，直接呈现角色行动与实际影响，让戏剧反差自然浮现。"
    },
    {
        "name": "系统工程标记外泄 (Internal Engineering Tag Leak)",
        "pattern": r"(?:GUN-\d+|MIS-\d+|Stage\s*\d+|伏笔道具|当前心智阶段|因果律震荡)",
        "suggestion": "严禁在小说正文中出现内部工程台账标记（如 GUN-003、MIS-001、Stage 1、伏笔道具等）。"
    },
    {
        "name": "战斗套路与脸谱反派口癖 (Battle & Antagonist Cliché Skeleton)",
        "combat_genre_only": True,
        "pattern": r"(?:目光如刀|神色未变|不知死活的[小杂畜东西]|死到临头.*?还敢|留你不得|眼中闪过一抹杀[气意]|嘴角勾起一抹[冷残狞]笑|冷笑连连|去势不减|连眼皮都未曾眨一下)",
        "suggestion": "避免'目光如刀/神色未变/不知死活/嘴角勾起一抹冷笑'等模式化爽文词汇堆砌。建议置换为真实的生理反应（如喉头耸动、汗毛倒竖、呼吸暂止）、微动作（如指节扣紧、重心微沉）或现场物理阻力描写。非战斗题材此规则自动禁用。"
    },
]

# 🌊 通用语义冗余聚类（Generic Fallback）
# v2: 仅保留跨题材通用的聚类，题材特定在 genre_profile.semantic_clusters 叠加
SEMANTIC_CLUSTERS_GENERIC = [
    {
        "cluster_name": "恐惧与瘫软同义堆砌",
        "keywords": ["吓瘫", "抖若筛糠", "面无人色", "牙关打战", "魂飞魄散", "涕泗横流", "冷汗涔涔", "惊恐万状"],
        "min_hits": 3,
        "suggestion": "当前段落密集出现多次'恐惧/惊骇'同义表达，存在情节与情绪冗余。建议合并或删减 1处，用一记利落动作直接推进，避免反复自嗨。"
    },
    {
        "cluster_name": "愤怒与暴怒同义堆砌",
        "keywords": ["勃然大怒", "怒不可遏", "怒火中烧", "火冒三丈", "暴跳如雷", "咬牙切齿", "目眦欲裂", "青筋暴起"],
        "min_hits": 3,
        "suggestion": "当前段落密集出现多次'愤怒'同义表达，存在情绪冗余。建议合并或删减，用具体动作或后果呈现愤怒，避免反复描写情绪本身。"
    },
    {
        "cluster_name": "震惊与不可思议同义堆砌",
        "keywords": ["难以置信", "不可思议", "瞠目结舌", "目瞪口呆", "大惊失色", "震惊", "骇然", "惊愕"],
        "min_hits": 3,
        "suggestion": "当前段落密集出现多次'震惊'同义表达，存在情绪冗余。建议删减重复，用配角视角或具体后果呈现震撼，避免反复自嗨。"
    },
]

# 向后兼容别名（旧代码引用 SEMANTIC_CLUSTERS 时仍可用）
SEMANTIC_CLUSTERS = SEMANTIC_CLUSTERS_GENERIC
CLIFFHANGER_KEYWORDS = CLIFFHANGER_KEYWORDS_GENERIC


def load_ground_truth(workspace_dir: Path):
    """Loads Character growth mindset arcs and Chekhov guns from state machine."""
    mindset_arcs = {}
    growth_file = workspace_dir / "04_timeline_and_state" / "character_growth_arcs.md"
    if growth_file.exists():
        content = growth_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("|") and "角色" not in line and not is_table_separator(line):
                if has_placeholder(line):
                    continue
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 3:
                    raw_name = parts[0]
                    raw_stage = parts[2]
                    clean_name = re.sub(r"[*_`#]", "", raw_name).strip()
                    clean_name = re.sub(r"\s*[（(].*?[）)]", "", clean_name).strip()
                    clean_stage = re.sub(r"[*_`]", "", raw_stage).strip()
                    if clean_name and "Stage" in clean_stage and not has_placeholder(clean_name):
                        mindset_arcs[clean_name] = clean_stage

        if not mindset_arcs:
            matches = re.findall(r"###\s*(?:📌\s*|【)?(.*?)(?:】|[（(]|$).*?当前(?:心智)?阶段[：:]\s*(.*?)(?:\n|$)", content, re.DOTALL)
            for cname, stage in matches:
                clean_name = re.sub(r"[*_`#]", "", cname).strip()
                clean_stage = re.sub(r"[*_`]", "", stage).strip()
                if clean_name and len(clean_name) <= 10:
                    mindset_arcs[clean_name] = clean_stage

    guns = []
    guns_file = workspace_dir / "04_timeline_and_state" / "chekhov_guns.md"
    if guns_file.exists():
        content = guns_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("|") and ("Planted" in line or "Reminded" in line or "Triggered" in line or "Active" in line):
                if has_placeholder(line):
                    continue
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    guns.append(f"{parts[0]} - {parts[1]}")
    return mindset_arcs, guns


def detect_semantic_redundancy(lines, window_lines=4, workspace=None):
    """Detects paragraph-level semantic redundancy and emotional clutter.

    v2: 聚类从题材档案动态加载（通用兜底 + 题材特定）。
    """
    redundancy_slices = []
    clusters = get_semantic_clusters(workspace)
    for idx in range(len(lines)):
        window = lines[idx:min(len(lines), idx + window_lines)]
        window_text = " ".join(window)
        for cluster in clusters:
            matched_words = [kw for kw in cluster["keywords"] if kw in window_text]
            if len(matched_words) >= cluster["min_hits"]:
                redundancy_slices.append({
                    "line_idx": idx,
                    "cluster_name": cluster["cluster_name"],
                    "matched_words": matched_words,
                    "suggestion": cluster["suggestion"]
                })
                break
    return redundancy_slices


def unsupervised_burstiness_slices(lines, window_size=400, min_repeat=3):
    """Unsupervised N-gram burstiness slice extractor."""
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

    burst_slices = []
    starts = list(range(0, len(full_text), 120)) if len(full_text) <= window_size else list(range(0, len(full_text) - window_size + 1, 120))
    if not starts:
        starts = [0]
    for n in [2, 3, 4]:
        for i in starts:
            chunk = full_text[i:i + window_size]
            counts = defaultdict(list)
            for j in range(len(chunk) - n + 1):
                gram = chunk[j:j + n]
                if re.match(r"^[\u4e00-\u9fa5]+$", gram):
                    if all(c in STOP_CHARS for c in gram):
                        continue
                    counts[gram].append(i + j)
            for gram, positions in counts.items():
                if len(positions) >= min_repeat:
                    l_idx = get_line_idx(positions[0])
                    burst_slices.append({
                        "line_idx": l_idx,
                        "gram": gram,
                        "count": len(positions)
                    })
    return burst_slices
