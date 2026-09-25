"""Novel Studio 状态机与底层八表持久化引擎 (engine/state.py)。

管理全书长程一致性核心状态八表：
- state/persons.json
- state/items.json
- state/factions.json
- state/places.json
- state/lines.json
- state/locked.json
- state/ledger.json
- state/current.json
并执行严格物理硬约束（如 充能>=0、死亡不可随意诈尸、单一持有者流转）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.config import load_config
from engine.errors import GuardError
from engine.schema import (
    CharacterRecord,
    FactionRecord,
    ItemRecord,
    LedgerRecord,
    LineRecord,
    LockedFactRecord,
)

# ── v4.3.3 FIND-SYNC：sync 跨表事务哨兵（A4 方案 1）──
# sync 是十几次独立的单文件原子写，不是一个跨表事务。中断在任何两次写盘之间，
# 台账会处于跨表不一致状态；此前唯一兜底是「sync_log 恰好在最后写」这一顺序巧合，
# 而非机制保证。哨兵文件把一个隐式巧合升级为显式契约：
#   · sync 入账开始前创建 state/.sync_pending，全部完成（含异常路径）后删除；
#   · 任何命令启动时若发现哨兵存在，说明上次 sync 未完成（中断/崩溃），
#     可据此硬失败或显著提示，避免在中间态上输出误导性数据。
# 落盘顺序仍是幂等重放的第二道防线，由 tests/regression_test.py 的
# ``test_sync_log_is_last_table_write`` 锁定为显式断言。
_SYNC_SENTINEL_NAME = ".sync_pending"

# 写盘计数（v4.3.3 FIND-SYNC）：sync 入账链路由 ops.sync_chapter 显式 reset，
# 用于区分「预检业务阻断（零写盘，可清哨兵）」与「写盘中途中断（已有表落盘，
# 哨兵必须保留）」。只允许 sync 事务窗口内读取，其它调用不依赖此计数。
_SAVE_COUNTER = {"n": 0}


def _save_count() -> int:
    return _SAVE_COUNTER["n"]


def _save_count_reset() -> None:
    _SAVE_COUNTER["n"] = 0


def write_sync_sentinel(workspace: Path, chapter_id: str) -> None:
    """在 state/ 下创建 sync 进行中哨兵（含章号/pid/时间戳，便于人工诊断）。"""
    _sd = Path(workspace) / "state"
    _ensure_dir(_sd)
    sentinel = _sd / _SYNC_SENTINEL_NAME
    _save_json(sentinel, {
        "chapter_id": str(chapter_id),
        "pid": os.getpid(),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    })


def clear_sync_sentinel(workspace: Path) -> None:
    """删除 sync 哨兵（正常完成或异常兜底时调用；幂等）。"""
    sentinel = Path(workspace) / "state" / _SYNC_SENTINEL_NAME
    try:
        sentinel.unlink(missing_ok=True)
    except OSError:
        pass


def read_sync_sentinel(workspace: Path) -> Optional[Dict[str, Any]]:
    """读取哨兵内容；不存在返回 None。"""
    sentinel = Path(workspace) / "state" / _SYNC_SENTINEL_NAME
    if not sentinel.exists():
        return None
    data = _load_json(sentinel, default=None)
    return data if isinstance(data, dict) else None


# ── v4.4.0 FIND-L：schema 契约字段透传白名单 ──
# 历史缺陷：sync 只把细纲 frontmatter 的子集写入台账（new_entities 硬编码十余字段、
# present_characters 硬编码约 14 字段），schema.py 承诺的其余契约字段
# （aliases/attitude/faction/realm/need/lie/micro_actions/danger_tier/leader/evidence…）
# 被**静默丢弃**——作者在细纲声明 life_status: deceased，落账却恒为 alive；
# 声明 faction: 灯火司，落账 None；声明 leader: 萧烜，落账 None。更危险的是 check
# 全程放行（假阳性），长篇一致性在「录入→存储」第一跳就断裂。
# 修复：按 schema 逐表建立白名单，细纲**显式声明过**的键一律透传落账；
# 未声明的键仍走产品默认，绝不凭空造字段、也绝不用默认值覆盖作者的显式声明。
_PERSON_FM_FIELDS: Tuple[str, ...] = (
    "aliases", "attitude", "faction", "tier_rank", "tier_name", "realm",
    "power_benchmark", "status", "injury_level", "injury_desc", "renown",
    "location", "card", "micro_actions", "dossier", "need", "lie", "summary",
)
_ITEM_FM_FIELDS: Tuple[str, ...] = (
    "card", "summary", "tier_rank", "tier_name", "condition", "max_charges",
    "cost_per_use", "faction", "location", "sensory_anchor",
    # FIND-CT35（S-1 漏网）：durability 是 schema.ItemRecord 契约字段，细纲
    # new_entities 显式声明 "durability: 九成新" 旧版被静默丢弃（state_deltas.items
    # 的 durability 有独立落账路径，new_entities 这条路漏了）。
    "durability",
)
_PLACE_FM_FIELDS: Tuple[str, ...] = (
    "card", "summary", "danger_tier", "sensory_anchor",
    # FIND-CT35 续：danger_level 与 environment_rules 是 schema.PlaceRecord 契约
    # 字段——check 的「地点数据残缺」巡逻的正是它们，细纲声明却落空等于让作者
    # 补无可补（只能手搓 state/places.json）。
    "danger_level", "environment_rules",
)
_FACTION_FM_FIELDS: Tuple[str, ...] = (
    "card", "scale_tier", "leader", "headquarters", "core_assets", "diplomacy",
)


_SLOT_JUNK_RE = re.compile(r"\{\{slot:[^}]*\}\}")


def _strip_slot_junk(obj: Any) -> Tuple[Any, int]:
    """FIND-CT54（L1·槽位串入账污染台账）：递归剔除未填模板槽位值，返回 (净化对象, 命中数)。

    根因实证：**金基座** workspace/test-lab/state/persons.json 里躺着一条
    ``id = name = "{{slot:char_1_id|p_001}}"`` 的幽灵人物（condition 亦为槽位串），
    还随快照进了 state/history/ch_001.json 与 ch_002.json；`id list person` 把它当
    第 5 位人物陈列，而 `check` 全程 0 errors（详见 check_id_integrity 的存量巡检补丁）。
    来源是 character_status 的自动打捞建档——「宽容自愈」公理要求未建档实体自动打捞，
    但模板占位串不是实体，绝不能获得台账身份。

    规则：字符串值命中 ``{{slot:`` 即整值丢弃（连同其所在键/列表项）；
    dict/list 递归净化；其余类型原样保留。台账由此获得一条硬不变量：
    **state/*.json 内永不出现模板占位串**。
    """
    if isinstance(obj, str):
        if _SLOT_JUNK_RE.search(obj):
            return None, len(_SLOT_JUNK_RE.findall(obj))
        return obj, 0
    if isinstance(obj, dict):
        hits = 0
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            # 键本身也可能是槽位串（character_status 以 ID/姓名为键）
            if isinstance(k, str) and _SLOT_JUNK_RE.search(k):
                hits += len(_SLOT_JUNK_RE.findall(k))
                continue
            nv, nh = _strip_slot_junk(v)
            hits += nh
            if nh and nv is None:
                continue  # 该字段整体是占位串：不落账
            out[k] = nv
        return out, hits
    if isinstance(obj, list):
        hits = 0
        out_l: List[Any] = []
        for it in obj:
            nv, nh = _strip_slot_junk(it)
            hits += nh
            if nh and nv is None:
                continue
            out_l.append(nv)
        return out_l, hits
    return obj, 0


def _paste_declared(rec: Dict[str, Any], src: Dict[str, Any], fields: Tuple[str, ...]) -> None:
    """把 src 中**显式声明过且非 None**的契约字段透传到 rec（FIND-L 核心通道）。

    用 ``in`` 判断而非 ``get(默认)``：只有细纲真实写出的键才落地，
    绝不替作者补默认值、也不让 None（YAML ``key:`` 留空）覆盖产品默认。
    """
    for _k in fields:
        if _k in src and src[_k] is not None:
            rec[_k] = src[_k]
    # v4.4.0 FIND-L：列表契约字段抗单值误写——作者写 aliases: 决哥（单值字符串）时，
    # 下游 for/集合推导会迭代出单个字符。统一包成单元素列表，保 list 契约。
    for _k in ("aliases", "micro_actions", "core_assets"):
        _v = rec.get(_k)
        if isinstance(_v, str):
            rec[_k] = [_v] if _v.strip() else []


def _entity_update_guard(rec: Dict[str, Any], ch_id: str) -> bool:
    """FIND-P/Q：实体「字段演化」的章序单调守卫。

    判据：当前章号不得早于该实体上次字段演化章（``updated_ch``，老数据回退
    ``established_ch``）。这样 ``--force`` 重放旧章时，旧章 new_entities 里
    携带的历史字段值不会把后续章节的演化（势力易主/道具易主/境界突破）覆盖回退。
    """
    _mut = str(rec.get("updated_ch", "") or rec.get("established_ch", "") or "")
    if not _mut:
        return True  # 老数据无水位，视为可更新（首次演化直接落地）
    return _chapter_num(ch_id) >= _chapter_num(_mut)


def _mark_updated(rec: Dict[str, Any], ch_id: str) -> None:
    """写入实体字段演化水位（FIND-P/Q）。"""
    rec["updated_ch"] = ch_id


# 标准生命状态枚举映射（Schema 归一化：支持显式英文与官方标准中文枚举值）
_LIFE_STATUS_NORM: Dict[str, str] = {
    "deceased": "deceased",
    "dead": "deceased",
    "死亡": "deceased",
    "阵亡": "deceased",
    "已故": "deceased",
    "alive": "alive",
    "活": "alive",
    "存活": "alive",
    "在世": "alive",
    # v4.3 缺陷#B6：补齐 schema/templates 白名单承诺的 missing（失踪）枚举
    "missing": "missing",
    "失踪": "missing",
    "下落不明": "missing",
    "失联": "missing",
    # FIND-CT69（作者需求）：新增第四态 unknown =「生死不知」。
    # missing 讲的是**下落**（人不见了），unknown 讲的是**存活状态本身未确认**
    # （坠崖/爆炸/沉船后生死未卜，作者与读者都不知道死没死）。二者都**不等于死亡**：
    # 不进已故黑名单、不受复活闸门约束、可以正常登场；但正文严禁擅自把其生死坐实。
    # 长篇里这类「悬念人物」极易被后续章节写成死人或活人，故单独建态并在简报里立账。
    "unknown": "unknown",
    "生死不明": "unknown",
    "生死不知": "unknown",
    "生死未卜": "unknown",
    "生死未明": "unknown",
    "生死不详": "unknown",
    "存亡未知": "unknown",
    "存亡不明": "unknown",
    "未知": "unknown",
    "未确认": "unknown",
    "不确定": "unknown",
}

# life_status 四态的中文展示标签（简报 / trace / ask 共用，避免各处硬编码）
LIFE_STATUS_LABELS: Dict[str, str] = {
    "alive": "在世",
    "deceased": "已故",
    "missing": "失踪（下落不明）",
    "unknown": "生死不明",
}


def life_status_label(value: Any) -> str:
    """life_status 枚举 → 中文标签；未知值原样返回（不猜、不改判）。"""
    v = str(value or "").strip()
    canon = _LIFE_STATUS_NORM.get(v.lower(), v)
    return LIFE_STATUS_LABELS.get(canon, canon or "未标注")


def _resolve_person_id(name_or_id: str, persons_db: Dict[str, Any]) -> Optional[str]:
    """智能解析角色 ID，支持 ID 直通、全名、去除括号基准名以及别名解析。"""
    if not name_or_id:
        return None
    nid = str(name_or_id).strip()
    if nid in persons_db:
        return nid
    base_nid = re.sub(r"[（\(].*?[）\)]", "", nid).strip()
    for pid, prec in persons_db.items():
        if not isinstance(prec, dict):
            continue
        pname = str(prec.get("name", "")).strip()
        pbase = re.sub(r"[（\(].*?[）\)]", "", pname).strip()
        aliases = [str(a).strip() for a in prec.get("aliases", []) if a]
        if nid in (pname, pbase) or (base_nid and base_nid in (pname, pbase)) or nid in aliases or (base_nid and base_nid in aliases):
            return pid
    return None


def _resolve_item_id(name_or_id: str, items_db: Dict[str, Any]) -> Optional[str]:
    """智能解析道具 ID，支持 ID 直通、全名、去除括号基准名以及别名解析。"""
    if not name_or_id:
        return None
    iid = str(name_or_id).strip()
    if iid in items_db:
        return iid
    base_iid = re.sub(r"[（\(].*?[）\)]", "", iid).strip()
    for db_id, irec in items_db.items():
        if not isinstance(irec, dict):
            continue
        iname = str(irec.get("name", "")).strip()
        ibase = re.sub(r"[（\(].*?[）\)]", "", iname).strip()
        aliases = [str(a).strip() for a in irec.get("aliases", []) if a]
        if iid in (iname, ibase) or (base_iid and base_iid in (iname, ibase)) or iid in aliases or (base_iid and base_iid in aliases):
            return db_id
    return None


def is_deceased(char_data: Any) -> bool:
    """判定角色是否已阵亡/死亡（支持全格式与语义推断）。"""
    if not isinstance(char_data, dict):
        return False
    life = str(char_data.get("life_status", "")).strip().lower()
    status = str(char_data.get("status", "")).strip().lower()
    cond = str(char_data.get("condition", "")).strip().lower()
    if _LIFE_STATUS_NORM.get(life) == "deceased":
        return True
    if _LIFE_STATUS_NORM.get(status) == "deceased":
        return True
    if life in ("dead", "deceased") or status in ("dead", "deceased"):
        return True
    # L1 兼容层：历史工作区的 condition 可能承载死亡语义而无 life_status。
    # 新数据由 sync 落账时自动升格（见 _infer_life_status），此处仅兜底旧档。
    # 关键：**已有显式生死契约时绝不让 condition 文本翻案**——否则
    # life_status="alive" + condition="气绝身亡"（如假死、诈尸、复活桥段）
    # 会被词表反判为死亡，作者的显式声明形同虚设。
    if life in _LIFE_STATUS_NORM or status in _LIFE_STATUS_NORM:
        return False
    # v4.3.3 FIND-C：无契约兜底与 L2 升格通道共用单一真值函数，消除「同一段
    # 文字三个入口三种结论」的词表漂移。旧版此处只枚举 5 个关键词，「病故于
    # 旧货店」这类非战斗死亡被 is_deceased 判活、get_death_chapter/_infer_life_status
    # 同判死。复用后可判定与 L2 完全一致（含反事实守卫）。
    return _infer_life_status(str(char_data.get("condition", "")).strip()) == "deceased"


def _infer_life_status(text: str) -> str:
    """从自由文本推断生死枚举（L2 语义线索 → L1 契约的升格通道）。

    返回 "deceased" / "missing" / "unknown" / "" （空串表示无法判定，交由调用方决定）。
    仅在 sync 落账时调用一次，把模糊文本**固化**成结构化契约；此后所有硬裁决
    只读 life_status，不再重复猜测。这样同一段文字的解释在全生命周期内唯一，
    不会出现"这次判死、下次判活"的漂移。
    """
    s = str(text or "").strip()
    if not s:
        return ""
    low = s.lower()
    if low in _LIFE_STATUS_NORM:
        return _LIFE_STATUS_NORM[low]
    # 反事实/假设语境守卫：先排除再匹配，避免「几乎死了」「以为他死了」误判
    for g in _NON_DEATH_GUARD_PATTERNS:
        if re.search(g, s):
            return ""
    # FIND-CT69：先判「生死未确认」再判死亡词——「生死不明」里含「不明」不含死亡词，
    # 但「坠崖后生死不知，疑似身亡」这类混写句必须落到 unknown（作者显式保留悬念），
    # 绝不能被后半句的死亡词抢判成 deceased（那会把悬念人物直接钉死进黑名单）。
    if any(k in s for k in ("生死不明", "生死不知", "生死未卜", "生死未明", "生死不详",
                            "存亡未知", "存亡不明", "不知生死", "生死悬而未决")):
        return "unknown"
    if any(k in s for k in _DEATH_KEYWORDS):
        return "deceased"
    if any(k in s for k in ("失踪", "下落不明", "失联", "杳无音信", "人间蒸发")):
        return "missing"
    return ""


# L2 反事实语境守卫：命中任一即放弃推断（宁可不判，不可错判）
_NON_DEATH_GUARD_PATTERNS = (
    r"几乎[^。；]{0,4}死", r"差点[^。；]{0,4}死", r"险些[^。；]{0,4}死",
    r"以为[^。；]{0,6}死", r"若是[^。；]{0,6}死", r"如果[^。；]{0,6}死",
    r"仿佛[^。；]{0,4}死", r"好像[^。；]{0,4}死", r"装死", r"假死",
    r"死[^。；]{0,4}(?:里逃生|而复生)", r"被救回", r"救了回来", r"没有死", r"未死", r"不曾死",
)


def _chapter_num(chapter_id: str) -> int:
    """提取章节数字编号。"""
    m = re.search(r"(\d+)$", str(chapter_id))
    return int(m.group(1)) if m else 0


# ============================================================================
# v4.3.3 BUG#47 · 生死判定的分层治理
# ----------------------------------------------------------------------------
# 【问题】汉语死亡表述无法穷举。旧实现把「是否死亡」这一**必须准确**的判定
#   建立在关键词枚举上，两类错误必然同时存在：
#     · 漏判：「倒在雪地里再没起来」「那盏灯，灭了」——真死判活 ⇒ 死者复活失控；
#     · 误判：「重伤，几乎死了，被救回」——没死判死 ⇒ 活人被封进黑名单。
#   每补一个词都在扩大误判面，每加一条守卫都在扩大漏判面，本质是拿模糊手段
#   去做确定性裁决。
#
# 【方案】按「判定后果」分层，而不是继续堆词表：
#   L1 结构化契约（唯一权威 · 确定性）：life_status / status 的法定枚举值。
#      只有它能把角色置为 deceased，供死者复活阻断等**硬裁决**使用。
#   L2 语义线索（仅用于提醒 · 不做裁决）：自由文本里的死亡措辞。命中后
#      **不改台账**，只提示作者「疑似死亡描写，请补 life_status 显式声明」。
#      词表在这一层永远是"够用就好"，漏了不造成事故，多了只是一句提醒。
#   L3 兜底：契约缺失且语义存疑时，宁可报"需要澄清"，也不替作者做决定。
#
# 这样汉语的模糊性被隔离在 L2，不再污染 L1 的确定性裁决。
# ============================================================================

# L2 语义线索词表：**仅用于生成提醒**，严禁用于 is_deceased 等硬裁决。
_DEATH_KEYWORDS = (
    "阵亡", "永久湮灭", "身死", "气绝身亡", "被斩杀", "deceased", "dead",
    # v4.3.2 缺陷#15：旧词表过窄，漏掉中文最常见的死亡表述。实测「为掩护沈决死于
    # 档案室火场」整条不命中 ⇒ 回落到 last_seen_ch，把死于 ch_004 的齐鸣判成
    # 「已于 ch_003 阵亡」，于是他真正的牺牲章 ch_004 被反诬为「死者复活」，
    # 全书体检对一本完全正常的书常驻 1 条阻断错误。
    "死于", "牺牲", "殒命", "丧生", "身亡", "毙命", "战死", "烧死", "溺亡", "自尽", "遇害",
    # v4.3.2 补遗：病故/猝死等"非暴力死亡"同样是常见写法，回归测试中由
    # 「病故于旧货店」一例暴露——旧词表偏战斗向，日常题材的死亡会整条漏判。
    "病故", "病逝", "猝死", "离世", "过世", "去世", "咽了气", "断气", "殉职", "殉难",
    "圆寂", "仙逝", "长眠", "命丧", "毙于", "死在", "死了",
)


# FIND-CT64：伏笔 action 合法值只有 plant/reveal/resolve（screenwriter SKILL 第 51 行明写），
# 但旧版对**任何**其它写法一律静默忽略——不告警、不落账、不阻断。SKILL 自己的措辞是
# 「若本章有**推进**或回收」，模型照措辞写 `action: 推进` / `action: push` 是高频行为，
# 后果是整条跨卷伏笔链在台账上永不推进（revealed_chs 恒空），卷末对账与 trace 全部失真，
# 且作者拿不到任何一句提示。归一表按「同义词收敛 + 未知值 loud warning」双轨处理。
_LINE_ACTION_ALIASES = (
    ("plant", ("plant", "planted", "plants", "planting", "setup", "seed", "sow",
               "埋", "埋设", "埋下", "埋伏", "植入", "播种", "设伏", "铺垫", "新埋", "首埋")),
    ("reveal", ("reveal", "revealed", "reveals", "revealing", "push", "advance", "develop",
                "hint", "hinted", "progress", "update",
                "推进", "推", "揭示", "揭露", "发展", "递进", "深化", "加码", "暗示", "推动", "更新", "递进")),
    ("resolve", ("resolve", "resolved", "resolves", "resolving", "payoff", "close", "closed",
                 "回收", "收", "收束", "收尾", "揭晓", "揭破", "兑现", "解开", "闭环", "了结")),
)


def _normalize_line_action(raw: Any) -> str:
    """伏笔 action → 法定三值；无法归一返回空串（调用方必须 loud warning）。"""
    v = str(raw or "").strip()
    if not v:
        return ""
    low = v.lower()
    for canon, aliases in _LINE_ACTION_ALIASES:
        if low == canon:
            return canon
        for a in aliases:
            # 中文别名走「包含」判定（「本章推进」「首次埋设」这类整句写法），
            # 英文别名走精确判定（避免 reveal 命中 reveals 之外的意外词）。
            if (a.isascii() and low == a) or (not a.isascii() and a in v):
                return canon
    return ""


# FIND-CT68（FP-4 裁决落地 · 倒叙/闪回豁免）：死者登场硬闸门旧版一刀切——
# 「回忆杀」「梦境相见」「亡魂托梦」这类中文网文极高频的合法桥段，只要把已故角色
# 写进 present_characters 就被判 exit 1 阻断，作者只能被迫把死者从在场表里删掉，
# 于是这一场的对白/称谓/认知探针全部失去对象，细纲与正文对不上。
# 裁决：**不放开生死台账**（life_status 仍是唯一权威，死者永不因登场而复活），
# 只放开「登场形态」——细纲在该条目上显式声明回忆/闪回形态即豁免闸门，并留一条
# 可追溯的 warning。既保住因果铁律，又不把合法叙事技法逼成脏数据。
_FLASHBACK_KEYS = ("appearance", "mode", "form", "scene_mode", "登场形态", "形态", "出场形态")
_FLASHBACK_MARKERS = (
    "flashback", "memory", "dream", "illusion", "vision", "recollection",
    "回忆", "倒叙", "闪回", "梦境", "梦中", "幻境", "幻象", "幻影", "生前",
    "遗影", "亡魂", "魂魄", "灵魂", "鬼魂", "托梦", "追忆", "回想",
)


def flashback_appearance(entry: Any) -> str:
    """返回 present_characters 条目声明的回忆/闪回形态标记；未声明返回空串。"""
    if not isinstance(entry, dict):
        return ""
    for k in _FLASHBACK_KEYS:
        v = str(entry.get(k, "") or "").strip()
        if not v:
            continue
        low = v.lower()
        for mk in _FLASHBACK_MARKERS:
            if (mk.isascii() and low == mk) or (not mk.isascii() and mk in v):
                return v
    return ""


def _ch_order(cid: str) -> int:
    m = re.search(r"(\d+)", str(cid or ""))
    return int(m.group(1)) if m else -1


def get_death_chapter(char_data: Any) -> str:
    """获取角色的阵亡章节。

    v4.3.2 缺陷#15：取 arc_history 中命中死亡语义的**最晚**一章，而非首个命中项
    —— arc_history 不保证按章序排列（实测实际为倒序），首命中会给出错误章号。
    v4.4.0 FIND-N：死亡语义判定统一走 ``_infer_life_status``（含反事实守卫），
    撤销与 BUG#15 同期遗留的**裸 ``_DEATH_KEYWORDS`` 枚举**——它会命中
    「重伤，几乎死了，被救回」里的「死了」，把合法死里逃生误报成死亡，
    继而让 check 对着一本完全正常的书打「台账生死状态自相矛盾」的 error（假阳性）。
    「deceased 兜底取最晚露面章」补上 is_deceased 前置，避免活人无端返回 last_seen_ch。
    """
    if not isinstance(char_data, dict):
        return ""
    hits = []
    for a in char_data.get("arc_history", []):
        if not isinstance(a, dict):
            continue
        if _infer_life_status(str(a.get("status_out", "")).strip()) == "deceased":
            hits.append(str(a.get("chapter", "")))
    if hits:
        return max(hits, key=_ch_order)

    # 未命中死亡语义但已登记为 deceased（如通过 life_status 显式声明）：
    # 取「最后露面章」与「弧光轨迹最晚一章」中较晚者，避免把死亡当章误判成复活。
    if is_deceased(char_data):
        cands = [str(char_data.get("last_seen_ch", "") or "")]
        for a in char_data.get("arc_history", []):
            if isinstance(a, dict) and a.get("chapter"):
                cands.append(str(a["chapter"]))
        cands = [c for c in cands if c]
        return max(cands, key=_ch_order) if cands else ""
    return ""


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_json(p: Path, default: Any = None) -> Any:
    """读表。v4.1 数据安全契约：
    - 文件不存在 → 返回默认值（合法首跑路径）；
    - JSON 损坏 → 隔离为 *.corrupt-<时间戳> 并**硬报错**，绝不静默以空表继续
      （旧版静默返回 {}，下一次保存会用空表覆盖真实台账，造成无痕数据蒸发）。
    """
    if not p.exists():
        # v4.3.2 缺陷#13（P0 · 静默空表放行）：损坏隔离把坏表 rename 成 *.corrupt-<ts> 后，
        # 原路径就此消失。下一条命令走到这里只看到「文件不存在」，当成合法首跑返回空表 ——
        # 于是第 1 次 exit 4 停机，第 2 次同一命令 exit 0 若无其事，发号器按空表重新发
        # it_001（实测 `id next item` 从 it_003 退回、`id list` 显示台账为空），
        # 真实台账被无声抹掉，正好撞穿本函数 docstring 承诺的「绝不静默以空表继续」。
        # 修正：只要同目录留有该表的隔离残骸且正主缺席，一律持续硬失败直到人工处置。
        try:
            leftovers = sorted(q.name for q in p.parent.glob(p.name + ".corrupt-*"))
        except OSError:
            leftovers = []
        if leftovers:
            raise RuntimeError(
                f"状态文件缺失但存在损坏隔离残骸: {p.name} 已于此前损坏并被隔离为 "
                f"{', '.join(leftovers[-3:])}，而正主文件至今未恢复。"
                f"引擎拒绝以空表继续运行（否则发号器会重发已占 ID、台账将被空表覆盖）。"
                f"请用 `python studio.py snapshot list` + `snapshot rollback <快照名>` 恢复，"
                f"或修复隔离文件后改名还原为 {p.name}；确认该表本就应为空时，"
                f"可手工写入空表（{{}} 或 []）并清理残骸。"
            )
        return default if default is not None else {}
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        corrupt = p.with_name(p.name + f".corrupt-{ts}")
        try:
            p.rename(corrupt)
            dest_hint = f"坏文件已隔离为: {corrupt.name}"
        except Exception:
            dest_hint = "坏文件隔离失败，请手工处理"
        raise RuntimeError(
            f"状态文件 JSON 损坏: {p.name}（{e}）。{dest_hint}。"
            f"引擎拒绝以空表继续运行以防台账蒸发；请用 `python studio.py snapshot list` + `snapshot rollback` "
            f"恢复最近快照，或手工修复该文件后重试。"
        ) from e
    except UnicodeDecodeError as e:
        # FIND-CT2：编码损坏（非 UTF-8 字节）与 JSON 损坏同级——旧版它作为
        # ValueError 子类被 cli 的「参数校验桶」吞掉，报 exit 1 且文案误导
        # （用户参数没问题，是表文件被写坏了）。此处隔离 + exit 4 归位。
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        corrupt = p.with_name(p.name + f".corrupt-{ts}")
        try:
            p.rename(corrupt)
            dest_hint = f"坏文件已隔离为: {corrupt.name}"
        except Exception:
            dest_hint = "坏文件隔离失败，请手工处理"
        raise RuntimeError(
            f"状态文件编码损坏（非 UTF-8 字节）: {p.name}（{e}）。{dest_hint}。"
            f"引擎拒绝以空表继续运行以防台账蒸发；请用 `python studio.py snapshot list` + `snapshot rollback` "
            f"恢复最近快照，或以 UTF-8 编码重写该文件后重试。"
        ) from e
    except OSError as e:
        raise RuntimeError(f"状态文件不可读: {p.name}（{e}）。请检查磁盘与权限后重试。") from e

    # v4.3 缺陷#C17：顶层结构类型契约校验——0B 若把 dict 表（如 lines.json）误写成 list
    # （或反之），旧版会延迟到业务层抛 AttributeError/TypeError，被笼统归入 exit 4 大盒子。
    # 此处按 default 的声明类型即时拦截并给出结构化修复指引；不自动隔离，防台账静默蒸发。
    if default is not None and data is not None and not isinstance(data, type(default)):
        expect = "JSON 对象 {}（字典）" if isinstance(default, dict) else "JSON 数组 []（列表）"
        actual = (
            "JSON 数组 []（列表）" if isinstance(data, list)
            else ("JSON 对象 {}（字典）" if isinstance(data, dict) else f"标量 {type(data).__name__}")
        )
        raise RuntimeError(
            f"状态文件顶层结构类型错误: {p.name} —— 该表应为 {expect}，实际读到的是 {actual}。"
            f"这通常是手工编辑状态表时写错了顶层括号。"
            f"请对照 templates/README.md 的表示例将该文件顶层改回 {expect}，"
            f"或用 `python studio.py snapshot list` + `snapshot rollback` 恢复最近快照后重试。"
        )
    return data


def _save_json(p: Path, data: Any) -> None:
    """原子写盘（v4.1）：临时文件 + os.replace，杜绝中途被杀导致 JSON 半截损坏。"""
    _ensure_dir(p.parent)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, p)
        # v4.3.3 FIND-SYNC：累计「事务写盘」次数——哨兵自己的创建/删除不计入
        # （哨兵是事务边界的标记，不是台账数据；若计入，哨兵清掉时计数会虚增，
        # 掩盖「零业务写盘」的阻断场景）。哨兵文件仅在 sync 事务窗口内由
        # write_sync_sentinel/clear_sync_sentinel 写删。
        if p.name != _SYNC_SENTINEL_NAME:
            _SAVE_COUNTER["n"] += 1
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


# ══════════════════════════════════════════════════════════════════════════════
#  FIND-CT73（公理二 · 自愈层）：脏数据在**写盘前**就地修正，且每一步都留痕
# ──────────────────────────────────────────────────────────────────────────────
#  设计取向（作者裁定：判据别太死板 + 增强自愈）：
#   1. 引擎能确定性推断的一律自己修（ID 规范、取号建档、改名留别名、数值夹取、
#      伏笔补章、流水去重、自怨清除、幽灵记录清扫），不再把「格式不好看」当阻断；
#   2. **绝不偷偷改**：每个自愈动作追加一条人读记录进 sync 报告的「🩹 自愈动作」，
#      写明改了哪张表、哪条记录、原值是什么、改成了什么；
#   3. **绝不猜剧情**：涉及叙事因果的（死者复活、生死矛盾、伏笔回收章到底是哪章）
#      只做「补一个可追溯的推断值 + 标注 inferred」或原样保留并提醒，不替作者定夺；
#   4. 幂等：同章 --force 重放不会产生第二次改动（自愈只在值确实非法时触发）。
# ══════════════════════════════════════════════════════════════════════════════

#: 规范 ID 形态（唯一真值：id_tracker.CANONICAL_PREFIXES 的发号口径）
CANONICAL_ID_RE: Dict[str, str] = {
    "person": r"^p_(\d+)$",
    "item": r"^it_(\d+)$",
    "location": r"^loc_(\d+)$",
    "faction": r"^fac_(\d+)$",
}

#: 细纲 type 写法 → ID 类别
_TYPE_TO_CAT: Dict[str, str] = {
    "person": "person", "character": "person",
    "item": "item", "weapon": "item", "tool": "item",
    "place": "location", "location": "location",
    "faction": "faction", "organization": "faction",
}

#: 数值契约字段的合法区间（**唯一真值**，check.py 3.4b 直接 import 本表，
#: 杜绝「体检口径」与「自愈口径」两处漂移——缺陷#15 的词表漂移就是前车之鉴）。
#: None 表示该侧无界。
NUMERIC_FIELD_BOUNDS: Dict[str, Dict[str, Tuple[Optional[int], Optional[int]]]] = {
    "persons": {"tier_rank": (1, 12), "injury_level": (0, 5), "renown": (None, None)},
    # FIND-CT37：max_charges/charges 下限按 -1 计（schema 默认值即 -1，表示非计数型）
    "items": {"charges": (-1, None), "max_charges": (-1, None), "tier_rank": (1, 12)},
    "factions": {"scale_tier": (1, 10)},
    "places": {"danger_tier": (1, 10)},
}

_CN_NUM: Dict[str, int] = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12,
}


def canonicalize_entity_id(raw: Any, category: str) -> Optional[str]:
    """把常见 ID 笔误规范成法定形态；无法确定时返回 None（**不猜**）。

    可确定性修的形态：大小写（P001）、缺下划线（p001）、位数不足（p_1 → p_001）、
    全角字符（ｐ＿００１）、尾随空格/句点。修不了（如「张三」这种姓名串）返回 None，
    交由调用方走取号建档路径。
    """
    rx = CANONICAL_ID_RE.get(category)
    if not rx:
        return None
    s = str(raw or "").strip()
    if not s:
        return None
    if re.match(rx, s):
        # 已合法（含 p_1 这类未补零写法）：原样返回，**不重编号**——
        # 改号会牵动全表引用（co_occurrence / entity_timeline / history 切片），
        # 得不偿失；补零只是美观，不是正确性。
        return s
    prefix = re.match(r"\^(\w+?)_", rx).group(1)   # p / it / loc / fac
    # NFKC 一把梭：全角字母数字、全角空格、兼容字符统统折回半角
    norm = unicodedata.normalize("NFKC", s)
    norm = re.sub(r"[\s\.\-—_·、]+", "", norm).strip()
    m = re.match(rf"^{prefix}0*(\d+)$", norm, re.IGNORECASE)
    if not m:
        return None
    return f"{prefix}_{int(m.group(1)):03d}"


def _name_base(name: Any) -> str:
    """姓名归一：剥括号补语、去空白与间隔号，用于判断「是否同一个人」。"""
    s = re.sub(r"[（\(].*?[）\)]", "", str(name or ""))
    return re.sub(r"[\s·・\-—_、,，.。]+", "", s).strip()


def _is_known_alias(name: Any, rec: Dict[str, Any]) -> bool:
    base = _name_base(name)
    if not base:
        return False
    if _name_base(rec.get("name")) == base:
        return True
    return any(_name_base(a) == base for a in (rec.get("aliases") or []))


def coerce_int(value: Any) -> Tuple[Optional[int], str]:
    """尽力把值转成整数；返回 (整数或 None, 处置说明)。

    支持：真 int、数字串（"3"/"+3"/"3.0"）、中文数字（"三"/"十二"）、bool（拒绝）。
    转不动就返回 (None, 原因)——调用方据此决定「夹取/丢弃/告警」，绝不硬塞 0。
    """
    if isinstance(value, bool):
        return None, "布尔值不是合法数值"
    if isinstance(value, int):
        return value, ""
    if isinstance(value, float):
        return int(value), f"浮点 {value} 截断为整数"
    s = str(value or "").strip()
    if not s:
        return None, "空值"
    if s in _CN_NUM:
        return _CN_NUM[s], f"中文数字「{s}」"
    m = re.match(r"^[+\-]?\d+(\.0+)?$", s)
    if m:
        return int(float(s)), f"数字串「{s}」"
    # 兜底：从「第三重」「Tier 5」「9 品」这类带单位/汉字的写法里提取数值——
    # 能提取就不丢字段（丢字段等于丢设定），只在真的一个数都找不到时才摘除。
    m2 = re.search(r"(\d+)", s)
    if m2:
        return int(m2.group(1)), f"从「{s}」中提取数字"
    for _cn, _n in sorted(_CN_NUM.items(), key=lambda kv: -len(kv[0])):
        if _cn and _cn in s:
            return _n, f"从「{s}」中识别中文数字「{_cn}」"
    return None, f"无法解析的数值 {_value_repr(value)}"


def _value_repr(v: Any) -> str:
    s = repr(v)
    return s if len(s) <= 40 else s[:37] + "..."


def heal_numeric_fields(rec: Dict[str, Any], table: str, eid: str, healed: List[str]) -> None:
    """数值契约字段自愈：类型纠正 → 区间夹取 → 无法解析则摘除字段（不塞假值）。"""
    bounds = NUMERIC_FIELD_BOUNDS.get(table) or {}
    for field, (lo, hi) in bounds.items():
        if field not in rec:
            continue
        raw = rec[field]
        if raw is None or raw == "":
            # 选填字段留空是合法的：不补默认值、不告警（作者裁定：别太死板）
            continue
        num, note = coerce_int(raw)
        if num is None:
            rec.pop(field, None)
            healed.append(
                f"[{table}/{eid}] 数值字段 `{field}` = {_value_repr(raw)} {note}，"
                f"已摘除该字段（选填，留空比塞假值安全；下游排序/统计不再被脏值绊倒）。"
            )
            continue
        fixed = num
        if lo is not None and fixed < lo:
            fixed = lo
        if hi is not None and fixed > hi:
            fixed = hi
        if fixed != raw:
            rec[field] = fixed
            _why = []
            if note:
                _why.append(note)
            if lo is not None and num < lo:
                _why.append(f"低于下限 {lo} 已夹取")
            if hi is not None and num > hi:
                _why.append(f"超出上限 {hi} 已夹取")
            healed.append(
                f"[{table}/{eid}] 数值字段 `{field}`：{_value_repr(raw)} → {fixed}"
                f"（{'，'.join(_why) or '类型纠正'}）。"
            )


def heal_life_status_field(rec: Dict[str, Any], eid: str, healed: List[str]) -> None:
    """life_status 归一自愈：中文写法/大小写/空格 → 法定四态；归一不了的原样保留。"""
    raw = rec.get("life_status")
    if raw in (None, ""):
        return                      # 选填：缺省即在世语义，不硬写 alive、不告警
    s = str(raw).strip()
    canon = _LIFE_STATUS_NORM.get(s.lower())
    if canon and canon != raw:
        rec["life_status"] = canon
        healed.append(f"[persons/{eid}] life_status 归一：「{s}」→ `{canon}`（{life_status_label(canon)}）。")
    elif not canon and s.lower() not in LIFE_STATUS_LABELS:
        # 自造值：不猜、不改判，只留痕提醒（死亡硬裁决按「非 deceased」处理）
        healed.append(
            f"[persons/{eid}] life_status「{s}」不在法定四态（alive/deceased/missing/unknown）内，"
            f"引擎**未擅自改判**，按「非已故」处理；若要坐实死亡请显式改写为 deceased。"
        )


def apply_name_update(rec: Dict[str, Any], new_name: Any, eid: str, label: str,
                      healed: List[str]) -> None:
    """改名自愈（FIND-CT73 H3）：旧名**降级为别名保留**，绝不无声蒸发。

    旧版三处 `if ename: rec["name"] = ename` 是台账最阴的一类污染——细纲把
    `[p_010] 阿福` 写成 p_010（台账里是「王五」）时，sync 直接把王五改名成阿福：
    既有角色的身份被顶替，而所有旧章的称谓、别名探针、address_matrix 全部失联，
    check 事后只能报一条「ID 与姓名不一致」，损失已不可逆。
    现在的处置：① 括号补语/间隔号差异（王莽（狂刀开荒队队长） vs 王莽）视为同一人，
    直接更新写法；② 真·改名则把旧名塞进 aliases（引用与称谓仍可解析）并留痕。
    """
    new = str(new_name or "").strip()
    if not new:
        return
    old = str(rec.get("name", "") or "").strip()
    if old == new:
        return
    if not old or _name_base(old) == _name_base(new) or _is_known_alias(new, rec):
        rec["name"] = new
        return
    aliases = [str(a).strip() for a in (rec.get("aliases") or []) if str(a).strip()]
    if old not in aliases:
        aliases.append(old)
    rec["aliases"] = aliases
    rec["name"] = new
    healed.append(
        f"[{label}/{eid}] 改名自愈：「{old}」→「{new}」，旧名已降级为 aliases 保留"
        f"（称谓探针与旧章引用不失联）。若这是**另一个角色**被写错了 ID，"
        f"请在 new_entities 用新号声明，引擎会自动改派。"
    )


def remap_chapter_refs(frontmatter: Dict[str, Any], old_id: str, new_id: str,
                       name: str, healed: List[str]) -> None:
    """撞号改派后，把**本章**同时带该 ID 与该姓名的引用改指新号（H2 配套）。

    保守口径：只改「ID + 姓名双匹配」的条目。仅凭 ID 匹配的引用无法区分
    「指新实体」还是「指原有实体」，一律不动，并在留痕里写明需要人工核对。
    """
    base = _name_base(name)
    moved: List[str] = []

    def _fix_entry(entry: Any, where: str) -> None:
        if not isinstance(entry, dict):
            return
        if str(entry.get("id", "") or "").strip() == old_id and _name_base(entry.get("name")) == base:
            entry["id"] = new_id
            moved.append(where)

    pres = frontmatter.get("present_characters")
    if isinstance(pres, list):
        for e in pres:
            _fix_entry(e, "present_characters")
    elif isinstance(pres, dict):
        _fix_entry(pres, "present_characters")
    sd = frontmatter.get("state_deltas")
    if isinstance(sd, dict):
        for key in ("items", "new_items"):
            vals = sd.get(key)
            if isinstance(vals, list):
                for e in vals:
                    _fix_entry(e, f"state_deltas.{key}")
            elif isinstance(vals, dict):
                _fix_entry(vals, f"state_deltas.{key}")
    if moved:
        healed.append(
            f"同章引用已改指新号：{'、'.join(sorted(set(moved)))} 中 [{old_id}] {name} → [{new_id}]。"
        )
    healed.append(
        f"⚠️ 仅凭 ID 匹配的引用（character_status 键、relation_deltas、debts）无法判定指向谁，"
        f"引擎未改动；若本章这些块也在写「{name}」，请核对是否需改用 [{new_id}]。"
    )


def sweep_ghost_records(sm: "StateManager", healed: List[str]) -> None:
    """台账幽灵记录清扫（槽位污染 / 空身份记录）。

    · id 与 name **双双**是未填模板槽位（`{{slot:...}}`）→ 整条删除（确定的模板垃圾）；
    · 只有 name 是槽位（ID 合法，人物真实存在）→ 保留记录，name 改为可追溯占位，
      绝不因为一个字段脏就把角色从台账里抹掉。
    """
    for table, getter, fname, label in (
        ("persons", sm.get_persons, sm.persons_file, "人物"),
        ("items", sm.get_items, sm.items_file, "道具"),
        ("places", sm.get_places, sm.places_file, "地点"),
        ("factions", sm.get_factions, sm.factions_file, "势力"),
    ):
        try:
            db = getter()
        except Exception:
            continue
        if not isinstance(db, dict) or not db:
            continue
        changed = False
        for eid in list(db.keys()):
            rec = db[eid]
            if not isinstance(rec, dict):
                db.pop(eid, None)
                changed = True
                healed.append(f"[{table}] 删除非 dict 的畸形记录 [{eid}]（无法承载任何字段）。")
                continue
            _id_dirty = "{{slot:" in str(eid)
            _nm_dirty = "{{slot:" in str(rec.get("name", ""))
            if _id_dirty and _nm_dirty:
                db.pop(eid, None)
                changed = True
                healed.append(f"[{table}] 清除幽灵记录 [{eid}]（id 与姓名都是未填模板槽位，无任何合法语义）。")
            elif _nm_dirty:
                rec["name"] = f"未命名{label}[{eid}]"
                changed = True
                healed.append(f"[{table}/{eid}] 姓名字段是未填槽位串，已改为可追溯占位「{rec['name']}」（记录保留，未删角色）。")
            elif _id_dirty:
                healed.append(f"[{table}] 记录 ID [{eid}] 含模板槽位但姓名「{rec.get('name')}」有效，"
                              f"引擎不擅自改号（会牵动全表引用），请手工核对后处理。")
        if changed:
            try:
                _save_json(fname, db)
            except Exception as e:      # noqa: BLE001
                healed.append(f"[{table}] 幽灵清扫写盘失败（原表未变）：{type(e).__name__}: {e}")


def heal_tables_pass(sm: "StateManager", ch_id: str, healed: List[str]) -> None:
    """sync 收尾的全表自愈一遍过（幂等）：数值、生死枚举、伏笔补章、经济数值、
    恩怨自指、关系轨迹重复。只改**确定性可推**的部分，全部动作留痕。"""
    # ── 人物 / 道具 / 势力 / 地点：数值 + 枚举 ──
    for table, getter, fname in (
        ("persons", sm.get_persons, sm.persons_file),
        ("items", sm.get_items, sm.items_file),
        ("factions", sm.get_factions, sm.factions_file),
        ("places", sm.get_places, sm.places_file),
    ):
        try:
            db = getter()
        except Exception:
            continue
        if not isinstance(db, dict):
            continue
        dirty = False
        for eid, rec in db.items():
            if not isinstance(rec, dict):
                continue
            _before = repr(rec)
            heal_numeric_fields(rec, table, eid, healed)
            if table == "persons":
                heal_life_status_field(rec, eid, healed)
            if repr(rec) != _before:
                dirty = True
        if dirty:
            try:
                _save_json(fname, db)
            except Exception as e:      # noqa: BLE001
                healed.append(f"[{table}] 自愈写盘失败（原表未变）：{type(e).__name__}: {e}")

    # ── 伏笔：planted_ch / resolved_ch 缺章自愈（推断值必须标注来源）──
    try:
        lines_db = sm.get_lines()
        if isinstance(lines_db, dict) and lines_db:
            dirty = False
            for lid, lr in lines_db.items():
                if not isinstance(lr, dict):
                    continue
                revealed = [str(x) for x in (lr.get("revealed_chs") or []) if str(x).strip()]
                if not str(lr.get("planted_ch", "") or "").strip():
                    infer = revealed[0] if revealed else ch_id
                    lr["planted_ch"] = infer
                    lr["planted_ch_source"] = "inferred"
                    dirty = True
                    healed.append(
                        f"[lines/{lid}] 缺埋设章 planted_ch，已按{'最早的推进章' if revealed else '本次入账章'}"
                        f"补为 {infer} 并标注 `planted_ch_source: inferred`（卷末对账需要它归卷；"
                        f"真实埋设章若在更早，请在该章细纲补 `action: plant` 覆盖）。"
                    )
                if str(lr.get("status", "")).lower() == "resolved" and not str(lr.get("resolved_ch", "") or "").strip():
                    infer = (revealed[-1] if revealed else str(lr.get("planted_ch", "") or ch_id)) or ch_id
                    lr["resolved_ch"] = infer
                    lr["resolved_ch_source"] = "inferred"
                    dirty = True
                    healed.append(
                        f"[lines/{lid}] 状态已 resolved 却缺回收章 resolved_ch，已补为 {infer} "
                        f"并标注 `resolved_ch_source: inferred`（引擎不猜真实回收章，请核对后覆盖）。"
                    )
            if dirty:
                _save_json(sm.lines_file, lines_db)
    except Exception as e:              # noqa: BLE001
        healed.append(f"[lines] 伏笔补章自愈跳过：{type(e).__name__}: {e}")

    # ── 经济：池余额 / 基线 / 流水 delta 的数值消毒（非数值会让下游算术崩栈）──
    try:
        led = sm.get_ledger()
        if isinstance(led, dict):
            dirty = False
            for key in ("pools", "pools_baseline"):
                bag = led.get(key)
                if not isinstance(bag, dict):
                    continue
                for pname, val in list(bag.items()):
                    num, note = coerce_int(val)
                    if num is None:
                        bag[pname] = 0
                        dirty = True
                        healed.append(f"[ledger/{key}] 池「{pname}」余额 {_value_repr(val)} {note}，已置 0（避免下游算术崩栈）；请按剧情核对后改写。")
                    elif num != val:
                        bag[pname] = num
                        dirty = True
                        healed.append(f"[ledger/{key}] 池「{pname}」余额 {_value_repr(val)} → {num}（{note or '类型纠正'}）。")
            txs = led.get("transactions")
            if isinstance(txs, list):
                for tx in txs:
                    if not isinstance(tx, dict):
                        continue
                    num, note = coerce_int(tx.get("delta", 0))
                    if num is None:
                        tx["delta"] = 0
                        dirty = True
                        healed.append(f"[ledger/transactions] 第 {tx.get('chapter', '?')} 章流水 delta {_value_repr(tx.get('delta'))} {note}，已置 0。")
                    elif num != tx.get("delta"):
                        tx["delta"] = num
                        dirty = True
                        healed.append(f"[ledger/transactions] 第 {tx.get('chapter', '?')} 章流水 delta → {num}（{note or '类型纠正'}）。")
            if dirty:
                _save_json(sm.ledger_file, led)
    except Exception as e:              # noqa: BLE001
        healed.append(f"[ledger] 经济数值自愈跳过：{type(e).__name__}: {e}")

    # ── 恩怨：自指条目清除（p_001 欠 p_001 是幽灵关系）──
    try:
        debts = sm.get_debts()
        if isinstance(debts, list) and debts:
            kept = []
            for d in debts:
                if isinstance(d, dict):
                    _s = str(d.get("source_char", "") or "").strip()
                    _t = str(d.get("target_char", "") or "").strip()
                    if _s and _t and _s == _t:
                        healed.append(f"[debts] 清除自指恩怨 [{d.get('id', 'DEBT')}]（发起方与承受方同为 {_s}，属幽灵关系）。")
                        continue
                kept.append(d)
            if len(kept) != len(debts):
                _save_json(sm.debts_file, kept)
    except Exception as e:              # noqa: BLE001
        healed.append(f"[debts] 恩怨自愈跳过：{type(e).__name__}: {e}")

    # ── 关系：同章重复轨迹去重（保留最后一条，与 sync 的按章幂等口径一致）──
    try:
        rel = sm.get_relations()
        if isinstance(rel, dict) and rel:
            dirty = False
            for pair, r in rel.items():
                if not isinstance(r, dict):
                    continue
                hist = r.get("history")
                if not isinstance(hist, list) or len(hist) < 2:
                    continue
                seen: Dict[str, int] = {}
                for h in hist:
                    if isinstance(h, dict):
                        hc = str(h.get("chapter", "") or "").strip()
                        if hc:
                            seen[hc] = seen.get(hc, 0) + 1
                dup = {k for k, v in seen.items() if v > 1}
                if not dup:
                    continue
                last_idx: Dict[str, int] = {}
                for i, h in enumerate(hist):
                    if isinstance(h, dict):
                        hc = str(h.get("chapter", "") or "").strip()
                        if hc in dup:
                            last_idx[hc] = i
                new_hist = [
                    h for i, h in enumerate(hist)
                    if not (isinstance(h, dict) and str(h.get("chapter", "") or "").strip() in dup
                            and last_idx.get(str(h.get("chapter", "") or "").strip()) != i)
                ]
                r["history"] = new_hist
                dirty = True
                healed.append(f"[relations/{pair}] 关系轨迹同章重复，已去重（{len(hist)} → {len(new_hist)} 条，保留每章最后一条）。")
            if dirty:
                _save_json(sm.relations_file, rel)
    except Exception as e:              # noqa: BLE001
        healed.append(f"[relations] 关系轨迹自愈跳过：{type(e).__name__}: {e}")


class StateManager:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.state_dir = self.workspace / "state"
        self.history_dir = self.state_dir / "history"
        self.indices_dir = self.state_dir / "indices"
        self.persons_file = self.state_dir / "persons.json"
        self.items_file = self.state_dir / "items.json"
        self.factions_file = self.state_dir / "factions.json"
        self.places_file = self.state_dir / "places.json"
        self.lines_file = self.state_dir / "lines.json"
        self.locked_file = self.state_dir / "locked.json"
        self.ledger_file = self.state_dir / "ledger.json"
        self.current_file = self.state_dir / "current.json"
        self.timeline_file = self.state_dir / "timeline.json"
        self.synopsis_file = self.state_dir / "synopsis.json"
        self.debts_file = self.state_dir / "debts.json"
        self.relations_file = self.state_dir / "relations.json"
        self.milestones_file = self.state_dir / "milestones.json"
        self.co_occurrence_file = self.indices_dir / "co_occurrence.json"
        self.entity_timeline_file = self.indices_dir / "entity_timeline.json"

    # --- 读取接口 ---
    def get_milestones(self) -> List[Dict[str, Any]]:
        return _load_json(self.milestones_file, default=[])

    def get_co_occurrence(self) -> Dict[str, Any]:
        return _load_json(self.co_occurrence_file, default={})

    def get_entity_timeline(self) -> Dict[str, Any]:
        return _load_json(self.entity_timeline_file, default={})

    def save_chapter_snapshot(self, chapter_id: str) -> Path:
        """保存当章全时空全息快照切片 (state/history/ch_XXX.json · 0-Token 历史漫游基石)。"""
        snap_data = {
            "chapter_id": chapter_id,
            "timestamp": datetime.now().isoformat(),
            "current": self.get_current(),
            "persons": self.get_persons(),
            "items": self.get_items(),
            "lines": self.get_lines(),
            "relations": self.get_relations(),
            "debts": self.get_debts(),
            "locked_facts": self.get_locked_facts(),
            "milestones": self.get_milestones(),
            "synopsis": self.get_synopsis().get(chapter_id, {}),
        }
        dest = self.history_dir / f"{chapter_id}.json"
        _save_json(dest, snap_data)
        return dest

    def get_relations(self) -> Dict[str, Dict[str, Any]]:
        return _load_json(self.relations_file, default={})

    def get_debts(self) -> List[Dict[str, Any]]:
        return _load_json(self.debts_file, default=[])

    def get_synopsis(self) -> Dict[str, Dict[str, Any]]:
        return _load_json(self.synopsis_file, default={})

    def get_persons(self) -> Dict[str, Dict[str, Any]]:
        return _load_json(self.persons_file, default={})

    def get_items(self) -> Dict[str, Dict[str, Any]]:
        return _load_json(self.items_file, default={})

    def get_factions(self) -> Dict[str, Dict[str, Any]]:
        return _load_json(self.factions_file, default={})

    def get_places(self) -> Dict[str, Dict[str, Any]]:
        return _load_json(self.places_file, default={})

    def get_lines(self) -> Dict[str, Dict[str, Any]]:
        return _load_json(self.lines_file, default={})

    def get_active_lines(self) -> List[Dict[str, Any]]:
        lines = self.get_lines()
        return [l for l in lines.values() if l.get("status") == "active"]

    def get_locked_facts(self) -> List[Dict[str, Any]]:
        return _load_json(self.locked_file, default=[])

    def get_ledger(self) -> Dict[str, Any]:
        # v4.2.2 全题材适配：默认不再预置任何题材币种（旧版预置"灵石"会让都市书报告出现仙侠残迹）
        return _load_json(self.ledger_file, default={"pools": {}, "transactions": []})

    def get_current(self) -> Dict[str, Any]:
        return _load_json(
            self.current_file,
            default={
                "current_vol": "vol_01",
                "current_ch": "ch_001",
                "last_timeline": "",
                "last_location": "",
                "present_characters": [],
                "active_foreshadowings": [],
            },
        )

    def get_timeline(self) -> List[Dict[str, Any]]:
        return _load_json(self.timeline_file, default=[])

    # --- 写入与增量更新 ---
    def register_person(self, person: CharacterRecord) -> None:
        db = self.get_persons()
        db[person.id] = person.to_dict()
        _save_json(self.persons_file, db)

    def register_item(self, item: ItemRecord) -> None:
        db = self.get_items()
        db[item.id] = item.to_dict()
        _save_json(self.items_file, db)

    def register_line(self, line: LineRecord) -> None:
        db = self.get_lines()
        db[line.id] = line.to_dict()
        _save_json(self.lines_file, db)

    def lock_fact(self, fact_id: str, fact: str, chapter_id: str, domain: str = "general") -> None:
        facts = self.get_locked_facts()
        if not any(f.get("id") == fact_id for f in facts):
            facts.append(LockedFactRecord(id=fact_id, fact=fact, established_ch=chapter_id, domain=domain).to_dict())
            _save_json(self.locked_file, facts)

    def apply_fine_outline_delta(
        self,
        frontmatter: Dict[str, Any],
        word_count: int = 0,
        beats_body: str = "",
    ) -> Dict[str, Any]:
        # FIND-CT54：单一咽喉消毒——本章全部增量在进任何一条落账通道之前先剔除模板
        # 占位串，八表由此获得「永不接纳 {{slot:}}」的硬不变量（sync 侧另有闸门双保险）。
        frontmatter, _slot_dropped = _strip_slot_junk(frontmatter)
        if not isinstance(frontmatter, dict):
            frontmatter = {}

        ch_id = frontmatter.get("chapter_id", "ch_001")
        vol_id = frontmatter.get("volume_id", "vol_01")
        title = frontmatter.get("title", "")
        timeline_str = str(frontmatter.get("timeline", ""))
        location_str = str(frontmatter.get("location", ""))
        chapter_type = str(frontmatter.get("chapter_type", "")).strip()  # 节奏遥测用（v4.1）

        warnings: List[str] = []
        # FIND-CT73（公理二 · 自愈层）：本次入账过程中引擎自己动手修好的每一处，
        # 都记进 healed，随 sync 报告一并公示（改了什么、原值是什么，全程可追溯）。
        healed: List[str] = []
        # 在途号：同章连续取号时排除尚未落盘的新 ID，避免分配器发出重号（FIND-CT5 同源）
        _inflight_ids: set = set()
        # H10：先扫掉台账里的幽灵记录（槽位污染 / 畸形条目），
        # 否则它们会占住发号水位、混进 id list 与简报。
        sweep_ghost_records(self, healed)
        if _slot_dropped:
            warnings.append(
                f"第 {ch_id} 章细纲含 {_slot_dropped} 处未填模板槽位值，已拒绝写入台账"
                f"（台账永不接纳占位串，相关字段按未声明处理）。\n"
                f"      💡 方案：请派发 Stage 1 (novel-screenwriter) 填实细纲剩余槽位后重跑 "
                f"`python studio.py sync {ch_id} --force`；未使用的可选块整段删除或置 []。"
            )
        cfg = load_config(self.workspace)

        # 0. 同步本章新登场实体 (new_entities)
        raw_new_ents = frontmatter.get("new_entities")
        new_entities = [raw_new_ents] if isinstance(raw_new_ents, dict) else (raw_new_ents if isinstance(raw_new_ents, list) else [])
        new_ent_count = 0
        if new_entities:
            persons_db = self.get_persons()
            items_db = self.get_items()
            places_db = self.get_places()
            factions_db = self.get_factions()
            for ne in new_entities:
                if not isinstance(ne, dict):
                    continue
                eid = str(ne.get("id", "")).strip()
                etype = str(ne.get("type", "person")).strip().lower()
                ename = str(ne.get("name", "")).strip()
                if not eid:
                    # 选填字段缺 ID 不再直接丢弃：能取号就取号建档（H4），
                    # 没名字又没 ID 才真无从下手。
                    if not ename:
                        continue
                    _cat0 = _TYPE_TO_CAT.get(etype)
                    if not _cat0:
                        continue
                    from engine.id_tracker import IdTracker as _IdT
                    eid = _IdT(self.workspace).get_next_id(_cat0, exclude=set(_inflight_ids))
                    if not eid:
                        continue
                    ne["id"] = eid
                    _inflight_ids.add(eid)
                    healed.append(
                        f"第 {ch_id} 章 new_entities 缺 id，已按类型 {_cat0} 自动取号 [{eid}] 建档「{ename}」"
                        f"（选填字段缺漏不再整条丢弃）。"
                    )
                # H1：ID 笔误规范化（P001 / p001 / ｐ＿００１ → p_001）
                _cat = _TYPE_TO_CAT.get(etype)
                if _cat:
                    _canon = canonicalize_entity_id(eid, _cat)
                    if _canon and _canon != eid:
                        healed.append(f"第 {ch_id} 章 new_entities ID 规范自愈：[{eid}] → [{_canon}]（{_cat}）。")
                        eid = _canon
                        ne["id"] = _canon
                # H2：撞号改派——ID 已被**另一个名字**的实体占用时，旧版会把既有角色
                # 改名顶替（台账身份被劫持）。现改为给新实体取新号，原记录分毫不动。
                if _cat and ename:
                    # 用**内存态**四表判定（新实体此时尚未落盘，重读磁盘会漏掉同章前几条）
                    _db_now = {
                        "person": persons_db, "item": items_db,
                        "location": places_db, "faction": factions_db,
                    }[_cat]
                    _label_now = {"person": "人物", "item": "道具",
                                  "location": "地点", "faction": "势力"}[_cat]
                    _old_rec = _db_now.get(eid) if isinstance(_db_now, dict) else None
                    if isinstance(_old_rec, dict):
                        _old_name = str(_old_rec.get("name", "") or "").strip()
                        if (_old_name and _name_base(_old_name) != _name_base(ename)
                                and not _is_known_alias(ename, _old_rec)):
                            from engine.id_tracker import IdTracker as _IdT2
                            _new_id = _IdT2(self.workspace).get_next_id(
                                _cat, exclude=set(_db_now.keys()) | _inflight_ids
                            )
                            if _new_id:
                                _old_id = eid
                                healed.append(
                                    f"第 {ch_id} 章 new_entities 撞号自愈：ID [{eid}] 台账已登记为"
                                    f"{_label_now}「{_old_name}」，细纲却声明新{_label_now}「{ename}」"
                                    f"→ 已改派新号 [{_new_id}] 入账，原记录「{_old_name}」保持不变"
                                    f"（旧版会静默覆盖姓名，等于把既有角色改名换姓）。"
                                )
                                eid = _new_id
                                ne["id"] = _new_id
                                _inflight_ids.add(_new_id)
                                remap_chapter_refs(frontmatter, _old_id, _new_id, ename, healed)
                # v4.3.3 BUG#46：细纲 new_entities 中残留的模板占位条目
                # （name 为「待填写道具名」「待填写新角色名」等）此前被当作真实实体入账，
                # 在 items/persons 表里留下幽灵记录，并占住 ID 让同号真实实体被丢弃
                # （实测 workspace/testbook 的 it_002 占位条挤掉了真正的「旧手表」）。
                # ops._is_placeholder_value 只守 proposal auto 路径，细纲直投无人拦截。
                _en = ename
                if (not _en) or _en in ("无", "示例", "略", "-", "N/A", "n/a") or any(
                        _en.startswith(_k) for _k in ("待填写", "待补充", "示例", "如：", "例如")):
                    continue
                if etype in ("person", "character"):
                    if eid not in persons_db:
                        # v4.4.0 FIND-L：schema 契约字段透传——作者在细纲显式声明的
                        # tier_rank/realm/faction/aliases/need/lie/life_status… 一律落账，
                        # 未声明的才走产品默认。旧版硬编码 role/tier_name 等十余字段并
                        # 把 life_status 恒置 "alive"（开篇死者静默复活，见 log/FINDINGS）。
                        _prec: Dict[str, Any] = {
                            "id": eid,
                            "name": ename or eid,
                            "role": ne.get("role", "supporting"),
                            "tier_name": ne.get("tier_name", ""),
                            "condition": ne.get("condition", "完好"),
                            "sensory_anchor": ne.get("sensory_anchor", ""),
                            "address_matrix": ne.get("address_matrix", {}),
                            "want": ne.get("want", "未锁定"),
                            "fear": ne.get("fear", "未锁定"),
                            "summary": ne.get("summary", ""),
                            "established_ch": ch_id,
                            "last_seen_ch": ch_id,
                            "life_status": "alive",
                            "arc_history": [],
                        }
                        _paste_declared(_prec, ne, _PERSON_FM_FIELDS)
                        # 生死契约走 L1 归一化（deceased/dead/死亡/阵亡…），未命中才落原值
                        _ne_life = str(ne.get("life_status", "") or "").strip()
                        if _ne_life:
                            _prec["life_status"] = _LIFE_STATUS_NORM.get(_ne_life.lower(), _ne_life)
                        persons_db[eid] = _prec
                        new_ent_count += 1
                    else:
                        # v4.4.0 FIND-P：实体已建档时不再静默跳过——中期演化（境界突破、
                        # 势力易主、道具易主、伤势变化）正是长篇一致性最核心的「状态变化」，
                        # 旧版 `if eid not in db` 把作者对既有实体的字段更新整条丢弃。
                        # 原地只更新**显式声明过**的字段，未声明字段保持既有值不回滚。
                        _eprec = persons_db[eid]
                        if not _entity_update_guard(_eprec, ch_id):
                            continue  # 旧章重放，比「上次演化章」更早，不回退字段
                        if ename:
                            apply_name_update(_eprec, ename, eid, "人物", healed)
                        _paste_declared(_eprec, ne, _PERSON_FM_FIELDS)
                        _ne_life = str(ne.get("life_status", "") or "").strip()
                        if _ne_life:
                            _eprec["life_status"] = _LIFE_STATUS_NORM.get(_ne_life.lower(), _ne_life)
                        _mark_updated(_eprec, ch_id)
                        # 同章重入账/补建档不改变「最近现身」（FIND-Q 单调守卫在 present 循环另行处理）
                elif etype in ("item", "weapon", "tool"):
                    if eid not in items_db:
                        _irec: Dict[str, Any] = {
                            "id": eid,
                            "name": ename or eid,
                            "holder": ne.get("holder", cfg.get("protagonist", "主角")),
                            "charges": ne.get("charges", -1),
                            "status": ne.get("status", "active"),
                            "durability": ne.get("durability", "完好"),
                            "sensory_anchor": ne.get("sensory_anchor", ""),
                            "location": ne.get("location", "随身"),
                            "summary": ne.get("summary", ""),
                            "established_ch": ch_id,
                            "last_seen_ch": ch_id,
                            "transfer_history": [],
                        }
                        _paste_declared(_irec, ne, _ITEM_FM_FIELDS)
                        items_db[eid] = _irec
                        new_ent_count += 1
                    else:
                        # v4.4.0 FIND-P：道具已建档时，原地更新**档案字段**（无独立 delta
                        # 通道的字段：tier_name/max_charges/condition/cost_per_use 等）。
                        # holder/charges/status/durability 是「有状态字段」，已有专门的
                        # state_deltas.items 通道（holder_change / charges_delta / status /
                        # durability），若在此一并覆盖会破坏 --force 重放的累计幂等
                        # （BUG#1 回归实证：重放把扣减后的 charges 重置回初值）。
                        _eirec = items_db[eid]
                        if not _entity_update_guard(_eirec, ch_id):
                            continue  # 旧章重放不回退
                        if ename:
                            apply_name_update(_eirec, ename, eid, "道具", healed)
                        _paste_declared(_eirec, ne, _ITEM_FM_FIELDS)
                        _mark_updated(_eirec, ch_id)
                elif etype in ("place", "location"):
                    if eid not in places_db:
                        _plrec: Dict[str, Any] = {
                            "id": eid,
                            "name": ename or eid,
                            "danger_level": ne.get("danger_level", "基础安全区"),
                            "sensory_anchor": ne.get("sensory_anchor", ""),
                            "environment_rules": ne.get("environment_rules", []),
                            "summary": ne.get("summary", ""),
                            "established_ch": ch_id,
                            "visited_chapters": [ch_id],
                        }
                        _paste_declared(_plrec, ne, _PLACE_FM_FIELDS)
                        places_db[eid] = _plrec
                        new_ent_count += 1
                    else:
                        # v4.4.0 FIND-P：地点已建档时，原地更新显式声明的字段。
                        _eplrec = places_db[eid]
                        if not _entity_update_guard(_eplrec, ch_id):
                            continue  # 旧章重放不回退
                        if ename:
                            apply_name_update(_eplrec, ename, eid, "地点", healed)
                        _paste_declared(_eplrec, ne, _PLACE_FM_FIELDS)
                        if "danger_level" in ne and ne["danger_level"] is not None:
                            _eplrec["danger_level"] = ne["danger_level"]
                        if "environment_rules" in ne and ne["environment_rules"] is not None:
                            _eplrec["environment_rules"] = ne["environment_rules"]
                        _mark_updated(_eplrec, ch_id)
                elif etype in ("faction", "organization"):
                    if eid not in factions_db:
                        _frec: Dict[str, Any] = {
                            "id": eid,
                            "name": ename or eid,
                            "summary": ne.get("summary", ""),
                            "established_ch": ch_id,
                        }
                        _paste_declared(_frec, ne, _FACTION_FM_FIELDS)
                        factions_db[eid] = _frec
                        new_ent_count += 1
                    else:
                        # v4.4.0 FIND-P：势力已建档时，原地更新显式声明的字段（领袖更替等）。
                        _efrec = factions_db[eid]
                        if not _entity_update_guard(_efrec, ch_id):
                            continue  # 旧章重放不回退
                        if ename:
                            apply_name_update(_efrec, ename, eid, "势力", healed)
                        _paste_declared(_efrec, ne, _FACTION_FM_FIELDS)
                        _mark_updated(_efrec, ch_id)
            # v4.3.2 缺陷#20（P0 · 阻断章仍污染台账）：旧版在此立即落盘 new_entities，
            # 而事务预检（死者登场 / 充能透支）在下方第 2 节才执行 —— 一旦预检 raise，
            # 本章的新人物/新道具/新地点/新势力已经写进台账且无人回滚。
            # 实测：cruise 在 ch_016 因充能透支刹车，p_017「守关人16」与 loc_016 仍被建档，
            # 于是台账里躺着一个"从未出现在任何已封存章"的幽灵人物，且占用了 ID 水位。
            # 修正：新实体只在内存中暂存，推迟到预检通过后（第 1 节起始处）统一落盘，
            # 与「事务预检先于任何写盘」的设计不变量对齐。
            _pending_entity_writes = [
                (self.persons_file, persons_db),
                (self.items_file, items_db),
                (self.places_file, places_db),
                (self.factions_file, factions_db),
            ]
        else:
            _pending_entity_writes = []
            persons_db = self.get_persons()
            # FIND-D1：预检需要吃「内存 items_db」才能看到同章 new_entities 新道具；
            # 此处保证无论 new_entities 是否为空，items_db 都是内存态。
            items_db = self.get_items()

        # 1. 同步人物与心理状态
        # 注意：此处不可重新 get_persons()——新实体尚未落盘，需沿用上方内存态。
        raw_pres = frontmatter.get("present_characters")
        raw_list = [raw_pres] if isinstance(raw_pres, (str, dict)) else (raw_pres if isinstance(raw_pres, list) else [])
        # v4.3 缺陷#B1：列表级归一化前移——字符串紧凑形态（present_characters: [p_001, p_003]）
        # 在此一次性补全为 dict，下游（死亡预检/弧光/共现矩阵/实体时间线）全部受益。
        # 旧版只在人物循环内做局部变量归一化，co_occurrence 与 entity_timeline 遍历原始
        # 列表时把字符串条目整体跳过，造成共现统计静默丢失。
        present_chars: List[Dict[str, Any]] = []
        # v4.3 R2：紧凑形态按「名→ID」二次解析——字符串写角色名（如 "周楚"）或
        # dict 只给 name 无 id 时，先按 name/aliases 反查已有建档（含别名），
        # 查不到才按原值走自注册（旧版会把中文名直接当成物理 ID 建出幽灵人物）。
        def _resolve_person_ref(raw_id: str, raw_name: str) -> Tuple[str, str]:
            rid = (raw_id or "").strip()
            rname = (raw_name or "").strip()
            if rid in persons_db:
                return rid, (persons_db[rid].get("name") or rname)
            probe = rid or rname
            if probe:
                for _pid, _prec in persons_db.items():
                    if not isinstance(_prec, dict):
                        continue
                    _names = {str(_prec.get("name", "")).strip()} | {str(a).strip() for a in (_prec.get("aliases") or [])}
                    if probe in _names:
                        return _pid, (_prec.get("name") or probe)
                    # 补充：括号别名剥离（如 "王莽（狂刀开荒队队长）" 匹配 "王莽"）
                    _base_name = re.sub(r"[（\(].*?[）\)]", "", _prec.get("name", "")).strip()
                    if _base_name and probe == _base_name:
                        return _pid, (_prec.get("name") or probe)
            return rid, rname

        for _c in raw_list:
            if isinstance(_c, str):
                _cid = _c.strip()
                if not _cid:
                    continue
                _rid, _rname = _resolve_person_ref(_cid, "")
                present_chars.append({"id": _rid, "name": _rname})
            elif isinstance(_c, dict):
                _rid, _rname = _resolve_person_ref(str(_c.get("id", "")), str(_c.get("name", "")))
                _cc = dict(_c)
                _cc["id"] = _rid
                if _rname and not _cc.get("name"):
                    _cc["name"] = _rname
                present_chars.append(_cc)
        # v4.3 R2：归一化后按 ID 去重——紧凑形态允许混写（"p_001" 与别名 "渊哥" 同章
        # 并存时归一化后指向同一人），不去重会产生重复在场名单与 p_001<->p_001 自配对
        _seen_pc: set = set()
        _pc_dedup: List[Dict[str, Any]] = []
        for _pc in present_chars:
            _k = str(_pc.get("id", "")).strip() if isinstance(_pc, dict) else ""
            if not _k or _k in _seen_pc:
                continue
            _seen_pc.add(_k)
            _pc_dedup.append(_pc)
        present_chars = _pc_dedup
        char_names_present: List[str] = []
        raw_sd = frontmatter.get("state_deltas")
        state_deltas = raw_sd if isinstance(raw_sd, dict) else {}
        char_status_deltas = state_deltas.get("character_status") if isinstance(state_deltas.get("character_status"), dict) else {}
        raw_items = (state_deltas.get("items") if isinstance(state_deltas, dict) else None) or []
        # v4.3：items 增量兼容单 dict 形态（未写列表时不再静默丢弃）
        item_deltas = [raw_items] if isinstance(raw_items, dict) else (raw_items if isinstance(raw_items, list) else [])

        # ── v4.2 缺陷#10 事务预检：硬约束违规必须在任何写盘前拦截 ──
        # （旧版先落盘后 raise，被阻断章节仍会污染台账：实测 ch_011 流转记录×3）
        _fatal: List[str] = []
        for cc in present_chars:
            if not isinstance(cc, dict):
                continue
            _cid = str(cc.get("id", "")).strip()
            _cname = str(cc.get("name", "")).strip()

            # 1. 直接按 ID 判定死者
            _is_dead = False
            _d_ch = ""
            _prec = persons_db.get(_cid)
            if _prec and is_deceased(_prec):
                _d_ch = get_death_chapter(_prec)
                if _chapter_num(ch_id) > _chapter_num(_d_ch):
                    _is_dead = True

            # 2. 若 ID 未命中，按名称/别名全库检索死者（防止编剧自编临时 ID 携死者复活）
            if not _is_dead and _cname:
                for _d_id, _d_prec in persons_db.items():
                    if not is_deceased(_d_prec):
                        continue
                    _cand_ch = get_death_chapter(_d_prec)
                    if _chapter_num(ch_id) <= _chapter_num(_cand_ch):
                        continue
                    _d_names = {str(_d_prec.get("name", "")).strip()} | {str(a).strip() for a in (_d_prec.get("aliases") or [])}
                    _d_base = re.sub(r"[（\(].*?[）\)]", "", _d_prec.get("name", "")).strip()
                    if _cname in _d_names or (_d_base and _cname == _d_base):
                        _is_dead = True
                        _cid = _d_id
                        _d_ch = _cand_ch
                        break

            if _is_dead:
                _disp_name = cc.get("name") or (_prec.get("name") if _prec else _cid)
                # FIND-CT68：显式声明回忆/闪回形态 ⇒ 豁免闸门，改记 warning（台账生死不变）
                _fb = flashback_appearance(cc)
                if _fb:
                    warnings.append(
                        f"第 {ch_id} 章已故角色 [{_disp_name}] ({_cid}) 以「{_fb}」形态登场，"
                        f"已豁免复活闸门（其卒章仍为 {_d_ch}，台账 life_status=deceased 不变）。"
                    )
                    continue
                _fatal.append(
                    f"因果冲突阻断：角色 [{_disp_name}] ({_cid}) 已于第 {_d_ch} 章阵亡，不能在后续章节作为在场人登场！\n"
                    f"💡 方案：① 若为回忆/闪回/梦境桥段，请在该 present_characters 条目补 `appearance: \"回忆\"`"
                    f"（合法豁免，台账生死状态不变）；② 否则请从 present_characters 中移除该角色；"
                    f"③ 若确系复活反转剧情，请先委派 Stage 4C (novel-evolution) 重构人物档案。"
                )
        if isinstance(item_deltas, list):
            # FIND-D1（L3·透支预检盲区）：旧版在此从磁盘重读 items 表——同章
            # new_entities 新道具要到 884 行才落盘，磁盘快照里根本没有它，charges 取
            # 默认 -1 使透支检查整段跳过；预检"通过"后应用侧发现扣成负值又静默丢弃，
            # 而 transfer_history 照记 charges_delta ⇒ sync exit 0 且台账自相矛盾
            # （实测 it_007：charges 停在 2、流水却写着 -3）。
            # 修正：预检改吃内存 items_db（含新道具），且道具引用解析与应用侧
            # 统一步走 _resolve_item_id（D2：细纲按名称/非 ID 引用时旧版预检裸 id
            # 查无此人同样漏检）。预检口径==应用口径。
            _items_pre = items_db
            for it in item_deltas:
                if not isinstance(it, dict):
                    continue
                _raw_id = str(it.get("id", "") or "").strip()
                _raw_nm = str(it.get("name", "") or "").strip()
                _iid = _resolve_item_id(_raw_id or _raw_nm, _items_pre) or _raw_id or _raw_nm
                if not _iid:
                    continue
                _rec = _items_pre.get(_iid, {})
                # FIND-CT1：脏值消毒防线（存量）——charges 非 int / < -1 时旧版直接
                # `None >= 0` TypeError 崩栈成 exit 4「未预期异常」，而 check 本就能
                # 检出该脏值。此处对齐 check 口径，在写盘前以业务阻断（exit 1 + 方案）
                # 拦下，杜绝系统级退出码错位。
                _raw_charges = _rec.get("charges", -1)
                if (
                    not isinstance(_raw_charges, int)
                    or isinstance(_raw_charges, bool)
                    or _raw_charges < -1
                ):
                    _fatal.append(
                        f"道具规则阻断：道具 [{it.get('name') or _iid}] ({_iid}) 的 charges 值非法: "
                        f"{_raw_charges!r}（合法范围: >= -1 的整数，-1 为非计数型无限耐久）。\n"
                        f"💡 方案：请先在 state/items.json 中将该字段修正为合法整数，"
                        f"或检查细纲 new_entities 中的 charges 声明后重试。"
                    )
                    continue
                try:
                    _d = int(it.get("charges_delta", 0))
                except (ValueError, TypeError):
                    continue
                # v4.3.2 缺陷#1：预检与应用侧口径必须一致——本章已入账的旧 delta 先冲销，
                # 否则同章 --force 重放会被自己上一次的扣减误判为透支。
                _prev_d = 0
                for _h in _rec.get("transfer_history", []) or []:
                    if isinstance(_h, dict) and _h.get("chapter") == ch_id:
                        try:
                            _prev_d += int(_h.get("charges_delta", 0) or 0)
                        except (ValueError, TypeError):
                            pass
                _d = _d - _prev_d
                # 口径统一：一律用 _raw_charges（已消毒为合法 int 或 -1），杜绝旧版
                # `get(..., 0)` 默认 0 与 `get(..., -1)` 默认 -1 的双口径漂移。
                if _raw_charges >= 0 and _raw_charges + _d < 0:
                    _fatal.append(
                        f"道具规则阻断：道具 [{it.get('name') or _iid}] ({_iid}) 充能已耗尽 "
                        f"(当前 {_raw_charges}，拟扣减 {_d})，不可透支使用！\n"
                        f"💡 方案：请在细纲 state_deltas.items 中调整 charges_delta 扣减值，或在前置剧情安排充能。"
                    )
                # FIND-D1b（静默无效扣减）：道具 delta 引用了一个 items 表中不存在的 id，
                # 且带非零 charges_delta——旧版按默认 -1（无限耐久）把扣减静默吞掉，
                # 台账零变化、零告警。此处显式告警，提示作者先建档或改用正确 id。
                if _iid not in _items_pre and _d != 0:
                    warnings.append(
                        f"道具 [{it.get('name') or _iid}] ({_iid}) 未在 state/items.json 建档，"
                        f"本章 charges_delta={_d} 已按「非计数型（-1）」忽略，台账不会发生充能变更。\n"
                        f"      💡 方案：若该道具应为计数型，请在细纲 new_entities 中声明 "
                        f'{{id: "{_iid}", type: "item", name: "...", charges: <初始次数>, max_charges: <上限>}}；'
                        f"若引用笔误请修正 id。"
                    )
        if _fatal:
            # 预检不通过：此刻尚未发生任何写盘，新实体随内存一并丢弃（零污染）。
            raise GuardError("\n".join(_fatal))

        # 预检通过，方可落盘本章新实体（v4.3.2 缺陷#20）
        for _pf, _pdb in _pending_entity_writes:
            _save_json(_pf, _pdb)

        for c in present_chars:
            # 字符串紧凑形态已在函数首部列表级归一化，此处仅剩 dict 形态
            if not isinstance(c, dict):
                continue
            cid = c.get("id", "").strip()
            cname = c.get("name", "").strip()
            if not cid:
                continue
            char_names_present.append(cname or cid)

            # H1/H4：present_characters 里的 ID 笔误先规范化；规范后仍未建档的，
            # 沿用旧有的「宽容自注册」路径（CharacterRecord 兜底建档），
            # 但 ID 必须是法定形态——旧版会把「张三」这类姓名串直接当物理 ID，
            # 产出 id=张三 的幽灵记录，污染 id list、发号水位与共现矩阵。
            _canon_cid = canonicalize_entity_id(cid, "person")
            if _canon_cid and _canon_cid != cid:
                healed.append(f"第 {ch_id} 章 present_characters ID 规范自愈：[{cid}] → [{_canon_cid}]。")
                cid = _canon_cid
                c["id"] = _canon_cid
            elif not _canon_cid:
                from engine.id_tracker import IdTracker as _IdT3
                _probe = _resolve_person_id(cid, persons_db)
                if not _probe and cid:
                    _alloc = _IdT3(self.workspace).get_next_id("person", exclude=set(persons_db.keys()) | _inflight_ids)
                    if _alloc:
                        _inflight_ids.add(_alloc)
                        healed.append(
                            f"第 {ch_id} 章 present_characters 条目 [{cid}] 不是规范人物 ID，"
                            f"已自动取号建档为 [{_alloc}]（姓名沿用「{cname or cid}」）。"
                        )
                        cid = _alloc
                        c["id"] = _alloc
                        if not cname:
                            cname = str(c.get("name") or "")

            p_data = persons_db.get(cid, CharacterRecord(id=cid, name=cname or cid).to_dict())
            # 死亡状态校验已前置至事务预检（缺陷#10：写盘前拦截）

            if cname:
                apply_name_update(p_data, cname, cid, "人物", healed)
            if c.get("role"):
                p_data["role"] = c["role"]
            if c.get("want"):
                p_data["want"] = c["want"]
            if c.get("fear"):
                p_data["fear"] = c["fear"]
            if c.get("quirk"):
                p_data["quirk"] = c["quirk"]
            if c.get("taboo"):
                p_data["taboo"] = c["taboo"]
            if c.get("latent_mood"):
                p_data["latent_mood"] = c["latent_mood"]
            if c.get("physiological_leak"):
                p_data["physiological_leak"] = c["physiological_leak"]
            if c.get("emotional_temp") is not None:
                p_data["emotional_temp"] = c["emotional_temp"]
            if c.get("vulnerability"):
                p_data["vulnerability"] = c["vulnerability"]
            if c.get("status_in"):
                p_data["condition"] = c["status_in"]
            # v4.4.0 FIND-L：present_characters 同样按 schema 白名单透传显式声明的
            # 契约字段——旧版只认 name/role/want/fear/quirk/taboo/latent_mood/
            # physiological_leak/emotional_temp/vulnerability/status_in 共 11 个，
            # realm/tier_rank/faction/aliases/need/lie/attitude… 写了也白写。
            _paste_declared(p_data, c, _PERSON_FM_FIELDS)
            # 生死契约：present_characters 若显式 life_status，走 L1 归一化落账
            # （与 character_status 通道同一真值函数，避免双入口双结论）。
            _pc_life = str(c.get("life_status", "") or "").strip()
            if _pc_life:
                p_data["life_status"] = _LIFE_STATUS_NORM.get(_pc_life.lower(), _pc_life)
            # v4.4.0 FIND-Q：last_seen_ch 单调不倒退。--force 重放旧章时，若把
            # 「最近现身」直接改成旧章号，会把角色的最后登场时刻回拨，污染
            # 时间线推理（trace 登场履历、死亡章兜底、后续因果校验都依赖它）。
            _prev_lsc = str(p_data.get("last_seen_ch", "") or "")
            if not _prev_lsc or _chapter_num(ch_id) >= _chapter_num(_prev_lsc):
                p_data["last_seen_ch"] = ch_id

            # 维护角色心理与弧光演进轨迹 (arc_history，幂等去重)
            _s_out_raw = char_status_deltas.get(cid, "") if isinstance(char_status_deltas, dict) else ""
            if isinstance(_s_out_raw, dict):
                _s_out = str(_s_out_raw.get("condition") or _s_out_raw.get("life_status") or "")
            else:
                _s_out = str(_s_out_raw)
            arc_hist = [a for a in p_data.get("arc_history", []) if isinstance(a, dict) and a.get("chapter") != ch_id]
            arc_hist.append({
                "chapter": ch_id,
                "want": c.get("want", ""),
                "fear": c.get("fear", ""),
                "latent_mood": c.get("latent_mood", p_data.get("latent_mood", "")),
                "physiological_leak": c.get("physiological_leak", p_data.get("physiological_leak", "")),
                "status_in": c.get("status_in", ""),
                "status_out": _s_out,
            })
            p_data["arc_history"] = arc_hist

            persons_db[cid] = p_data

        # 人物状态增量 (state_deltas.character_status)
        if isinstance(char_status_deltas, dict):
            for cid, s_val in char_status_deltas.items():
                target_pid = _resolve_person_id(cid, persons_db)
                if not target_pid:
                    # 若未建档，自动打捞为临时角色建档，坚决不静默丢失状态！
                    # FIND-CT73 H4：物理 ID 必须规范——键是「P001/p001」这类笔误就规范化，
                    # 是姓名串就取号建档，绝不把原始串直接当 ID 落库（幽灵记录源头）。
                    _canon_key = canonicalize_entity_id(cid, "person")
                    if _canon_key:
                        target_pid = _canon_key
                        if _canon_key != cid:
                            healed.append(f"第 {ch_id} 章 character_status 键规范自愈：[{cid}] → [{_canon_key}]。")
                        _display = _canon_key
                    else:
                        from engine.id_tracker import IdTracker as _IdT4
                        target_pid = _IdT4(self.workspace).get_next_id(
                            "person", exclude=set(persons_db.keys()) | _inflight_ids
                        ) or cid
                        if target_pid != cid:
                            _inflight_ids.add(target_pid)
                            healed.append(
                                f"第 {ch_id} 章 character_status 键「{cid}」不是规范人物 ID，"
                                f"已自动取号建档为 [{target_pid}]（姓名沿用「{cid}」）。"
                            )
                        _display = cid if not re.match(r"^[A-Za-z0-9_\-]+$", cid) else target_pid
                    persons_db[target_pid] = CharacterRecord(id=target_pid, name=_display).to_dict()
                    cid = target_pid

                # 显式契约优先：支持字典形态 {life_status: "deceased", condition: "..."}
                if isinstance(s_val, dict):
                    explicit_life = str(s_val.get("life_status", "")).strip().lower()
                    cond_text = str(s_val.get("condition") or s_val.get("status") or s_val.get("desc") or "").strip()
                    if cond_text:
                        persons_db[target_pid]["condition"] = cond_text
                    if explicit_life in _LIFE_STATUS_NORM:
                        # 显式契约最高优先级，直接采信
                        persons_db[target_pid]["life_status"] = _LIFE_STATUS_NORM[explicit_life]
                    else:
                        _inf2 = _infer_life_status(cond_text)
                        if _inf2:
                            persons_db[target_pid]["life_status"] = _inf2
                        elif any(_k in cond_text for _k in _DEATH_KEYWORDS):
                            # v4.4.0 FIND-L3：显式 life_status 拼写非法 + 文本命中死亡词表
                            # 又被反事实守卫拦下（几乎死了/装死…）——引擎判定未死亡，
                            # 但作者写了显式契约意图，必须提示修复拼写。
                            warnings.append(
                                f"第 {ch_id} 章角色 [{cid}] 的生死契约「{explicit_life}」不是法定枚举值，"
                                f"且描述「{cond_text}」命中死亡字面却陷入反事实/未遂语境，引擎不能据此判定死亡。\n"
                                f"      💡 方案：若确系死亡，请显式声明 "
                                f'{cid}: {{life_status: "deceased", condition: "{cond_text}"}}；'
                                f"或修正 life_status 为 alive/deceased/missing 之一。"
                            )
                else:
                    s_desc = str(s_val).strip()
                    persons_db[target_pid]["condition"] = s_desc
                    # v4.3.3 BUG#47：旧版只认精确枚举，作者写「重伤·气绝身亡」这类
                    # 自由文本时 life_status 永远不被写入，死亡只能靠下游词表反复猜测，
                    # 同一段文字在不同调用点可能得出不同结论。此处一次性升格为契约：
                    # 推断成功即固化进 life_status，此后所有硬裁决只读契约不再猜。
                    _inferred = _infer_life_status(s_desc)
                    if _inferred:
                        persons_db[target_pid]["life_status"] = _inferred
                    elif any(_k in s_desc for _k in _DEATH_KEYWORDS):
                        # v4.4.0 FIND-L3：命中死亡词表但被反事实守卫拦下（几乎死了/装死/
                        # 以为死了…）——这是合法的「死里逃生」，不落 life_status，
                        # 但给作者一句可食用的提示，避免他以为引擎漏判。
                        warnings.append(
                            f"第 {ch_id} 章角色 [{cid}] 的状态「{s_desc}」含死亡字面但命中反事实/未遂语境（几乎/差点/装死/假死…），"
                            f"引擎判定为**未死亡**。\n"
                            f"      💡 方案：若实为死亡反转，请显式声明字典形态 "
                            f'{cid}: {{life_status: "deceased", condition: "{s_desc}"}}；若确为死里逃生可忽略。'
                        )

        _save_json(self.persons_file, persons_db)

        # 2. 同步道具流转与充能约束
        items_db = self.get_items()
        if isinstance(item_deltas, list):
            for it in item_deltas:
                if not isinstance(it, dict):
                    continue
                raw_id = it.get("id", "").strip()
                iname = it.get("name", "").strip()
                iid = _resolve_item_id(raw_id or iname, items_db) or raw_id or iname
                if not iid:
                    continue
                irecord = items_db.get(iid, ItemRecord(id=iid, name=iname or iid).to_dict())
                if iname:
                    irecord["name"] = iname

                # 状态流转 (status): active, consumed, destroyed, lost
                raw_status = str(it.get("status") or it.get("action") or "").lower().strip()
                if raw_status in ("destroyed", "destroy", "损毁", "碎裂"):
                    irecord["status"] = "destroyed"
                elif raw_status in ("consumed", "consume", "消耗", "使用"):
                    irecord["status"] = "consumed"
                elif raw_status in ("lost", "遗失", "丢失"):
                    irecord["status"] = "lost"
                elif raw_status in ("active", "完好", "正常"):
                    irecord["status"] = "active"

                if it.get("durability"):
                    irecord["durability"] = str(it["durability"]).strip()

                # 持有者流转: "p_001 -> p_002"
                h_change = str(it.get("holder_change", ""))
                old_h = irecord.get("holder", "")
                new_h = old_h
                if "->" in h_change:
                    old_part, new_part = h_change.split("->", 1)
                    new_h = new_part.strip()
                    irecord["holder"] = new_h
                elif h_change:
                    new_h = h_change.strip()
                    irecord["holder"] = new_h

                # 充能消耗（透支已在事务预检拦截，此处安全应用）
                c_delta = it.get("charges_delta", 0)
                delta_int = 0
                try:
                    delta_int = int(c_delta)
                except (ValueError, TypeError):
                    delta_int = 0
                # v4.3.2 缺陷#1（充能重放非幂等）：本章若已入账过 charges_delta，
                # 必须先冲销旧值再应用新值——否则 `sync --force` 每重放一次就真扣一次，
                # 连扣数次后引擎反被自己的透支守卫阻断（实测 3→2→1→0→GuardError）。
                # transfer_history 是同章唯一流水凭据（同章记录已按 chapter 去重替换）。
                _prev_delta = 0
                for _h in irecord.get("transfer_history", []) or []:
                    if isinstance(_h, dict) and _h.get("chapter") == ch_id:
                        try:
                            _prev_delta += int(_h.get("charges_delta", 0) or 0)
                        except (ValueError, TypeError):
                            pass
                _net_delta = delta_int - _prev_delta
                # FIND-CT1：脏值消毒防线（同章新建）——new_entities 本章声明的 charges
                # 非 int 时（如显式 null），预检读的是落盘前快照拦不到，应用层必须兜底：
                # 跳过充能变更并告警，其余 delta（持有人/状态）照常入账。
                _cur_charges = irecord.get("charges", -1)
                if (
                    not isinstance(_cur_charges, int)
                    or isinstance(_cur_charges, bool)
                    or _cur_charges < -1
                ):
                    warnings.append(
                        f"道具 [{raw_id or iname or iid}] 的 charges 值非法: {_cur_charges!r}"
                        f"（合法范围: >= -1 的整数，-1 为非计数型无限耐久），本次充能变动已跳过。\n"
                        f"      💡 方案：请在 state/items.json 中将该字段修正为合法整数后重跑 sync"
                        f"（或去掉细纲 new_entities 中的 charges 声明）。"
                    )
                elif _cur_charges >= 0:
                    new_charges = _cur_charges + _net_delta
                    if new_charges >= 0:
                        irecord["charges"] = new_charges

                # v4.4.0 FIND-Q：道具 last_seen_ch 单调不倒退（--force 重放旧章不回拨）。
                _iprev_lsc = str(irecord.get("last_seen_ch", "") or "")
                if not _iprev_lsc or _chapter_num(ch_id) >= _chapter_num(_iprev_lsc):
                    irecord["last_seen_ch"] = ch_id
                if "transfer_history" not in irecord:
                    irecord["transfer_history"] = []
                # v4.2 幂等数据层：同章流转记录替换而非追加（--force 重放不翻倍）
                irecord["transfer_history"] = [
                    h for h in irecord["transfer_history"]
                    if isinstance(h, dict) and h.get("chapter") != ch_id
                ]
                irecord["transfer_history"].append({
                    "chapter": ch_id,
                    "holder_change": h_change or f"{old_h} -> {new_h}",
                    "charges_delta": delta_int,
                    "remaining_charges": irecord.get("charges", -1),
                    "status": irecord.get("status", "active"),
                })
                items_db[iid] = irecord

        _save_json(self.items_file, items_db)

        # 2.5 同步地点足迹与自动打捞建档
        if location_str:
            places_db = self.get_places()
            _scene_env = frontmatter.get("scene_environment") if isinstance(frontmatter.get("scene_environment"), dict) else {}
            _sensory = str(_scene_env.get("sensory_focus") or frontmatter.get("sensory_anchor") or "").strip()
            _raw_rules = _scene_env.get("environment_rules") or frontmatter.get("environment_rules") or []
            _env_rules = [_raw_rules] if isinstance(_raw_rules, str) else (list(_raw_rules) if isinstance(_raw_rules, list) else [])

            loc_match = re.search(r"(loc_\d+)", location_str)
            found_id = loc_match.group(1) if loc_match else None
            if not found_id:
                # 核心层级匹配：优先匹配已有顶级或已知地点（按名称长度倒序），杜绝微观修饰词造成空壳地点暴增
                for pid, prec in sorted(places_db.items(), key=lambda x: len(str(x[1].get("name", ""))), reverse=True):
                    pname = str(prec.get("name", "") or "").strip()
                    if not pname:
                        continue
                    p_core = re.sub(r"^[0-9]+号?", "", pname).strip()
                    if pname == location_str or pname in location_str or location_str in pname or (p_core and len(p_core) >= 3 and p_core in location_str):
                        found_id = pid
                        break
            if found_id:
                if found_id in places_db:
                    places_db[found_id].setdefault("visited_chapters", [])
                    if ch_id not in places_db[found_id]["visited_chapters"]:
                        places_db[found_id]["visited_chapters"].append(ch_id)
                    # 增量自愈：若已有地点缺少物象或规则，且当前细纲提供了声明，自动补充
                    if not places_db[found_id].get("sensory_anchor") and _sensory:
                        places_db[found_id]["sensory_anchor"] = _sensory
                    if not places_db[found_id].get("environment_rules") and _env_rules:
                        places_db[found_id]["environment_rules"] = _env_rules
                else:
                    places_db[found_id] = {
                        "id": found_id,
                        "name": location_str,
                        "danger_level": "普通",
                        "sensory_anchor": _sensory,
                        "environment_rules": _env_rules,
                        "summary": "",
                        "visited_chapters": [ch_id],
                    }
            else:
                from engine.id_tracker import IdTracker
                tracker = IdTracker(self.workspace)
                new_lid = tracker.get_next_id("place")
                places_db[new_lid] = {
                    "id": new_lid,
                    "name": location_str,
                    "danger_level": "普通",
                    "sensory_anchor": _sensory,
                    "environment_rules": _env_rules,
                    "summary": "",
                    "visited_chapters": [ch_id],
                }
            _save_json(self.places_file, places_db)

        # 3. 同步伏笔生命周期 (lines.json)
        lines_db = self.get_lines()
        raw_fd = frontmatter.get("foreshadowing_deltas")
        f_deltas = [raw_fd] if isinstance(raw_fd, dict) else (raw_fd if isinstance(raw_fd, list) else [])
        line_summary = {"planted": [], "revealed": [], "resolved": []}

        if f_deltas:
            for fd in f_deltas:
                if not isinstance(fd, dict):
                    continue
                fid = fd.get("id", "").strip()
                fname = fd.get("name", "").strip()
                _raw_faction = str(fd.get("action", "") or "").strip()
                fdesc = fd.get("desc", "").strip()
                if not fid:
                    continue
                # FIND-CT64：空值沿用旧默认 plant（无声明即视为本章埋设），
                # 非空但无法归一的写法**不再静默吞掉**——先记一条告警，再按 plant 兜底，
                # 保证伏笔至少入台账（宁可多一句提醒，不可整条链失踪）。
                faction = _normalize_line_action(_raw_faction)
                if not faction:
                    warnings.append(
                        f"第 {ch_id} 章伏笔 [{fid}] 的 action『{_raw_faction}』不在法定枚举 "
                        f"(plant/reveal/resolve) 内，无法判定推进语义，已按 plant 兜底入账。"
                        f"\n      💡 方案：请改写为 plant（埋设）/ reveal（推进揭示）/ resolve（回收）之一；"
                        f"中文同义词（埋设/推进/回收）引擎可直接识别。"
                    )
                    faction = "plant"

                lrecord = lines_db.get(fid, LineRecord(id=fid, name=fname or fid).to_dict())
                if fname:
                    lrecord["name"] = fname
                # v4.3.2 缺陷#2（伏笔分类恒为 GUN）：LineRecord.type 默认 "GUN"，且旧版
                # 既不读细纲显式 type、也不按 ID 前缀推断 ⇒ KNO-001/MIS-001 全被记成 GUN，
                # schema 承诺的 GUN/KNO/MIS 三分类形同虚设（trace 报告同步误导）。
                _explicit_type = str(fd.get("type", "") or "").upper().strip()
                if _explicit_type in ("GUN", "KNO", "MIS"):
                    lrecord["type"] = _explicit_type
                else:
                    _m_pref = re.match(r"^(GUN|KNO|MIS)-", fid.upper())
                    if _m_pref:
                        lrecord["type"] = _m_pref.group(1)
                if fdesc:
                    lrecord["desc"] = fdesc

                # FIND-CT64 续：长篇跨卷最常见的两类伏笔时序事故——
                #   ① 未埋先推/先收（planted_ch 空 ⇒ 卷末对账无法归属卷，trace 链路断裂）；
                #   ② 已回收又回收（status 已 resolved ⇒ 二次回收会把 resolved_ch 改写，
                #      回收章静默漂移，读者视角变成「伏笔收了两次」）。
                _was_resolved = str(lrecord.get("status", "")).lower() == "resolved"
                if faction in ("reveal", "resolve") and not str(lrecord.get("planted_ch", "")).strip():
                    warnings.append(
                        f"第 {ch_id} 章伏笔 [{fid}] {lrecord.get('name', '')} 尚未埋设"
                        f"（planted_ch 为空）却声明 {faction}——台账无法确定它属于哪一卷。"
                        f"\n      💡 方案：请确认埋设章是否漏声明（在该章细纲补 `action: plant`），"
                        f"或把本章改为 plant。"
                    )
                if faction == "resolve" and _was_resolved:
                    warnings.append(
                        f"第 {ch_id} 章伏笔 [{fid}] 已于 {lrecord.get('resolved_ch', '?')} 回收，"
                        f"本章重复声明 resolve，回收章将被改写为 {ch_id}。"
                        f"\n      💡 方案：若本章只是余波提及，请改用 reveal；"
                        f"若确为真正回收章，请回改前一章的 resolve 声明。"
                    )
                if faction == "plant":
                    if str(lrecord.get("planted_ch", "")).strip() and lrecord.get("planted_ch") != ch_id:
                        warnings.append(
                            f"第 {ch_id} 章伏笔 [{fid}] 重复埋设：台账已记录埋设于 "
                            f"{lrecord.get('planted_ch')}，本次改写为 {ch_id}。"
                            f"\n      💡 方案：若本章只是再次提及，请改用 reveal。"
                        )
                    lrecord["status"] = "active"
                    lrecord["planted_ch"] = ch_id
                    line_summary["planted"].append(fid)
                elif faction == "reveal":
                    if "revealed_chs" not in lrecord:
                        lrecord["revealed_chs"] = []
                    if ch_id not in lrecord["revealed_chs"]:
                        lrecord["revealed_chs"].append(ch_id)
                    line_summary["revealed"].append(fid)
                elif faction == "resolve":
                    lrecord["status"] = "resolved"
                    lrecord["resolved_ch"] = ch_id
                    line_summary["resolved"].append(fid)

                if fd.get("tier"):
                    lrecord["tier"] = str(fd["tier"]).upper().strip()
                if fd.get("target_ch"):
                    lrecord["target_ch"] = str(fd["target_ch"]).strip()
                # v4.4.0 FIND-L：evidence 是 schema/synopsis/audit 承诺的「原文证据切片」，
                # 旧版声明了却从未落账（trace 报告永远拿不到证据，悬空契约字段）。
                if fd.get("evidence"):
                    lrecord["evidence"] = str(fd["evidence"]).strip()

                lines_db[fid] = lrecord

        _save_json(self.lines_file, lines_db)

        # 4. 同步经济流水账本 (ledger.json)
        # v4.3 缺陷#A3 修复（资金池静默蒸发）：
        # 旧版 `state_deltas.get("ledger") or {}` 空 dict 也会进入账本块，导致每次 sync
        # 都全量重放清零手工声明的初始池余额，并凭空创建默认池。现改为：
        #  ① 仅当细纲真实声明了 ledger 增量（非空 dict）才处理；
        #  ② 首次入账时把既有人工声明池值固化为 pools_baseline，
        #     池余额恒 = baseline + 全部流水重放，初始资金永不蒸发。
        ledger_db = self.get_ledger()
        ledger_delta = state_deltas.get("ledger") or {}
        if isinstance(ledger_delta, dict) and ledger_delta:
            # FIND-CT67 续：池名先 strip 再比对——尾随空格/换行是最常见的 YAML 手误，
            # 旧版原样当键用 ⇒ 「通用资金池 」静默开出第二个池，全书经济被劈成两本账。
            # 按公理二「能自动解决的直接自愈」就地归一；真正的别名（灵石池 vs 通用资金池）
            # 仍由下方的「新资金池」warning 提醒作者核对。
            pool_name = str(
                ledger_delta.get("pool") or load_config(self.workspace).get("default_pool", "通用资金池")
            ).strip()
            delta_val = str(ledger_delta.get("delta", "0")).strip()
            try:
                d_num = int(delta_val.replace("+", ""))
            except ValueError:
                d_num = 0
                warnings.append(
                    f"ledger.delta 无法解析为整数: '{delta_val}'（本章经济增量已忽略，请检查细纲书写）"
                )
            pools = ledger_db.setdefault("pools", {})
            baseline = ledger_db.setdefault("pools_baseline", {})
            # FIND-CT67：触账前的既有池名集合（用于识别「本章静默开出新资金池」）
            _pre_pools = set(pools) | set(baseline)
            # 首次触账：把 Stage 0B 手工声明的既存池余额固化为基线（之后只增不改）
            for _p, _b in list(pools.items()):
                if _p not in baseline and isinstance(_b, (int, float)) and not isinstance(_b, bool):
                    baseline[_p] = int(_b)
            baseline.setdefault(pool_name, 0)
            pools.setdefault(pool_name, baseline[pool_name])
            txs = [
                t for t in ledger_db.get("transactions", [])
                if not (t.get("chapter") == ch_id and t.get("pool") == pool_name)
            ]
            if d_num != 0:
                # v4.3 R2：流水可选记录事由（细纲 ledger.reason/desc），供 cockpit 经济遥测与对账溯源
                tx_reason = str(ledger_delta.get("reason", "") or ledger_delta.get("desc", "")).strip()
                txs.append({"chapter": ch_id, "pool": pool_name, "delta": d_num, "reason": tx_reason})
            ledger_db["transactions"] = txs
            all_pools = set(baseline.keys()) | {t.get("pool") for t in txs}
            for p_name in all_pools:
                pools[p_name] = baseline.get(p_name, 0) + sum(t.get("delta", 0) for t in txs if t.get("pool") == p_name)

            # FIND-CT67（L2·经济面静默失衡）：道具充能透支有硬守卫（「道具规则阻断：
            # 充能已耗尽，不可透支使用」⇒ exit 1），资金面却对笔误完全静默——实测把
            # delta 写成 -999999，池余额直接转负近百万，sync 仍 exit 0 且零提示，
            # 直到几十章后卷末对账才暴露，回溯成本极高。欠账/负债线是合法剧情
            # （故**不阻断**，与充能的物理不可透支区分开），但必须 loud warning。
            # 同理：ledger 声明一个台账从未出现过的池名（多打一个空格、写别名）会
            # 静默开出第二个资金池，把全书经济劈成两半，也必须提醒作者核对。
            if d_num != 0:
                _bal = pools.get(pool_name, 0)
                if isinstance(_bal, (int, float)) and not isinstance(_bal, bool) and _bal < 0:
                    warnings.append(
                        f"资金池「{pool_name}」余额已转负（{_bal}）：第 {ch_id} 章 delta={d_num:+d}。"
                        f"\n      💡 方案：若为剧情欠账/负债线，可忽略本提醒；"
                        f"若为笔误（多写一个零、正负号写反），请修正细纲 state_deltas.ledger.delta 后重跑 sync。"
                    )
                if pool_name not in _pre_pools:
                    warnings.append(
                        f"第 {ch_id} 章 ledger 开出新资金池「{pool_name}」（此前台账无此池，既有池: "
                        f"{', '.join(sorted(_pre_pools)) or '无'}）。"
                        f"\n      💡 方案：若为笔误（池名多空格/写别名），请改回既有池名后重跑 sync，"
                        f"否则全书经济将被劈成两本账；若确为剧情新开户，可忽略本提醒。"
                    )
        _save_json(self.ledger_file, ledger_db)

        # 4.5 同步恩怨情仇账本 (debts.json)
        debts_deltas = state_deltas.get("debts") or []
        if isinstance(debts_deltas, list):
            debts_db = self.get_debts()
            for dd in debts_deltas:
                if not isinstance(dd, dict):
                    continue
                d_source = str(dd.get("source") or "p_001").strip()
                d_target = str(dd.get("target", "")).strip()
                d_type = str(dd.get("type", "grudge")).strip()
                d_desc = str(dd.get("desc", "")).strip()
                d_action = str(dd.get("action", "record")).strip().lower()
                # v4.3.2 缺陷#6（恩怨重放膨胀）：缺省 id 旧版按 len(debts_db)+1 发号，
                # 随表长漂移 ⇒ 同章 --force 重放每次都算「新恩怨」，实测三次重放出
                # DEBT-001/002/003 三条相同记录。templates/beats.md 默认就不带 id，
                # 这条路径是常态而非边角。改为按（章节+双方+类型）派生稳定幂等键。
                d_id = str(dd.get("id", "") or "").strip()
                if not d_id:
                    # FIND-CT11（ID-4·恩怨静默抹除）：旧种子 `章节|双方|类型` 不含
                    # 事由——同章同双方同类型不同 desc 的两条恩怨（如既结"杀父之仇"
                    # 又欠"夺财之恨"，type 均 grudge）算出同一 hash，sync 的「同 id
                    # 先删后加」把前一条无声抹掉。种子追加 desc，语义才够区分。
                    _seed = f"{ch_id}|{d_source}|{d_target}|{d_type}|{d_desc}"
                    d_id = "DEBT-AUTO-" + hashlib.sha1(_seed.encode("utf-8")).hexdigest()[:8]

                if d_action == "record":
                    # v4.2 幂等数据层：同 id 恩怨替换而非追加（--force 重放不翻倍）
                    debts_db = [d for d in debts_db if d.get("id") != d_id]
                    # v4.4.0 FIND-L：status 显式声明透传。旧版恒为 "unpaid"，作者
                    # 首章就声明 status: settled 的「前史已清账」被静默改判为未了结。
                    _d_status = str(dd.get("status", "unpaid") or "unpaid").strip().lower()
                    _d_status_norm = {"settled": "settled", "paid": "settled", "resolved": "settled",
                                      "unpaid": "unpaid", "open": "unpaid"}.get(_d_status, "unpaid")
                    _d_item: Dict[str, Any] = {
                        "id": d_id,
                        "source_char": d_source,
                        "target_char": d_target,
                        "type": d_type,
                        "desc": d_desc,
                        "status": _d_status_norm,
                        "created_ch": ch_id,
                    }
                    if _d_status_norm == "settled":
                        _d_item["settled_ch"] = ch_id
                    debts_db.append(_d_item)
                elif d_action in ("settle", "resolve"):
                    for d_item in debts_db:
                        if (d_item.get("target_char") == d_target or d_item.get("id") == d_id) and d_item.get("status") == "unpaid":
                            d_item["status"] = "settled"
                            d_item["settled_ch"] = ch_id
            _save_json(self.debts_file, debts_db)

        # 4.6 同步双向动态情感与心理拉扯 (relations.json)
        raw_rels = frontmatter.get("relation_deltas") or (state_deltas.get("relation_deltas") if isinstance(state_deltas, dict) else None)
        rel_deltas = [raw_rels] if isinstance(raw_rels, dict) else (raw_rels if isinstance(raw_rels, list) else [])
        if rel_deltas:
            rel_db = self.get_relations()
            for rd in rel_deltas:
                if not isinstance(rd, dict):
                    continue
                pair_val = rd.get("pair")
                s_id = str(rd.get("source", "")).strip()
                t_id = str(rd.get("target", "")).strip()
                if isinstance(pair_val, list) and len(pair_val) >= 2:
                    s_id = str(pair_val[0]).strip()
                    t_id = str(pair_val[1]).strip()
                    pair_key = f"{s_id}->{t_id}"
                elif s_id and t_id:
                    pair_key = f"{s_id}->{t_id}"
                elif isinstance(pair_val, str) and pair_val.strip():
                    pair_key = pair_val.strip()
                    if "->" in pair_key:
                        parts = pair_key.split("->", 1)
                        s_id, t_id = parts[0].strip(), parts[1].strip()
                else:
                    continue

                if not pair_key:
                    continue

                curr_rel = rel_db.get(pair_key, {
                    "pair": pair_key,
                    "source_id": s_id,
                    "target_id": t_id,
                    "affinity": 0,
                    "trust": 50,
                    "tension": 20,
                    "dynamic_label": "初识",
                    "unspoken_subtext": "",
                    "history": [],
                })

                if rd.get("affinity_delta") is not None:
                    try:
                        curr_rel["affinity"] = max(-100, min(100, curr_rel.get("affinity", 0) + int(rd["affinity_delta"])))
                    except (ValueError, TypeError):
                        pass
                elif rd.get("affinity") is not None:
                    # v4.4.0 FIND-L：显式 affinity 是绝对覆盖语义（与 tension 对等），
                    # 旧版只在 affinity_delta 分支处理，写 affinity 被静默丢弃。
                    try:
                        curr_rel["affinity"] = max(-100, min(100, int(rd["affinity"])))
                    except (ValueError, TypeError):
                        pass
                if rd.get("trust") is not None:
                    # v4.4.0 FIND-L：信任度显式声明落账（schema/synopsis 承诺字段）
                    try:
                        curr_rel["trust"] = max(0, min(100, int(rd["trust"])))
                    except (ValueError, TypeError):
                        pass
                if rd.get("tension") is not None:
                    try:
                        curr_rel["tension"] = max(0, min(100, int(rd["tension"])))
                    except (ValueError, TypeError):
                        pass
                elif rd.get("tension_delta") is not None:
                    try:
                        curr_rel["tension"] = max(0, min(100, curr_rel.get("tension", 20) + int(rd["tension_delta"])))
                    except (ValueError, TypeError):
                        pass
                dynamic_text = rd.get("dynamic_label") or rd.get("dynamic")
                if dynamic_text:
                    curr_rel["dynamic_label"] = str(dynamic_text).strip()
                subtext_str = rd.get("unspoken_subtext") or rd.get("subtext")
                if subtext_str:
                    curr_rel["unspoken_subtext"] = str(subtext_str).strip()

                curr_rel["last_updated_ch"] = ch_id
                rel_hist = [h for h in curr_rel.get("history", []) if isinstance(h, dict) and h.get("chapter") != ch_id]
                rel_hist.append({
                    "chapter": ch_id,
                    "dynamic": curr_rel.get("dynamic_label"),
                    "subtext": curr_rel.get("unspoken_subtext"),
                    "affinity": curr_rel.get("affinity"),
                    "tension": curr_rel.get("tension"),
                })
                curr_rel["history"] = rel_hist
                rel_db[pair_key] = curr_rel
            _save_json(self.relations_file, rel_db)

        raw_ms = (
            frontmatter.get("milestone_deltas")
            or (state_deltas.get("milestone_deltas") if isinstance(state_deltas, dict) else None)
            or (state_deltas.get("milestones") if isinstance(state_deltas, dict) else None)
        )
        ms_deltas = [raw_ms] if isinstance(raw_ms, dict) else (raw_ms if isinstance(raw_ms, list) else [])
        if ms_deltas:
            ms_list = self.get_milestones()
            ms_map = {m.get("id"): m for m in ms_list if isinstance(m, dict) and m.get("id")}
            for md in ms_deltas:
                if not isinstance(md, dict):
                    continue
                ms_id = str(md.get("id", "") or "").strip()
                action = str(md.get("action", "advance") or "advance").strip().lower()
                summary = str(md.get("summary", "") or "").strip()
                if not ms_id:
                    continue
                if ms_id in ms_map:
                    if action in ("achieve", "achieved", "达成", "完成"):
                        ms_map[ms_id]["status"] = "achieved"
                        ms_map[ms_id]["achieved_ch"] = ch_id
                    elif action in ("advance", "progress", "推进"):
                        ms_map[ms_id]["last_advanced_ch"] = ch_id
                        if summary:
                            ms_map[ms_id]["latest_progress"] = summary
                else:
                    new_ms = {
                        "id": ms_id,
                        "title": summary[:20] if summary else ms_id,
                        "desc": summary,
                        "status": "achieved" if action in ("achieve", "achieved", "达成", "完成") else "pending",
                        "established_ch": ch_id,
                    }
                    if action in ("achieve", "achieved", "达成", "完成"):
                        new_ms["achieved_ch"] = ch_id
                    else:
                        new_ms["last_advanced_ch"] = ch_id
                    ms_list.append(new_ms)
                    ms_map[ms_id] = new_ms
            _save_json(self.milestones_file, ms_list)

        # 5. 登记法定锁定事实 (locked.json)
        raw_lfs = frontmatter.get("locked_facts")
        locked_facts = [raw_lfs] if isinstance(raw_lfs, dict) else (raw_lfs if isinstance(raw_lfs, list) else [])
        locked_facts_count = 0
        if locked_facts:
            locked_db = self.get_locked_facts()
            for lf in locked_facts:
                if not isinstance(lf, dict):
                    continue
                lid = str(lf.get("id", "")).strip()
                fact_str = str(lf.get("fact", "")).strip()
                if not lid or not fact_str:
                    continue
                existing = next((f for f in locked_db if f.get("id") == lid), None)
                if existing:
                    existing["fact"] = fact_str
                else:
                    locked_db.append({
                        "id": lid,
                        "fact": fact_str,
                        "domain": lf.get("domain", "plot"),
                        "established_ch": ch_id,
                    })
                    locked_facts_count += 1
            _save_json(self.locked_file, locked_db)

        # 6. 解析并保存单章剧梗 (synopsis.json)
        dramatic_goal = ""
        cliffhanger_desc = ""
        if beats_body:
            m_goal = re.search(r"-\s*\*\*本章核心戏剧目标\*\*：\s*(.+)", beats_body)
            if m_goal:
                dramatic_goal = m_goal.group(1).strip()
            m_cliff = re.search(r"-\s*\*\*物理定格画面\*\*：\s*(.+)", beats_body)
            if m_cliff:
                cliffhanger_desc = m_cliff.group(1).strip()

        synopsis_db = self.get_synopsis()
        synopsis_db[ch_id] = {
            "chapter_id": ch_id,
            "volume_id": vol_id,
            "title": title,
            "timeline": timeline_str,
            "location": location_str,
            "chapter_type": chapter_type,
            "dramatic_goal": dramatic_goal,
            "cliffhanger": cliffhanger_desc,
            "word_count": word_count,
            "present_characters": char_names_present,
        }
        _save_json(self.synopsis_file, synopsis_db)

        # 7. 追加全书时间线 (timeline.json)
        timeline_list = self.get_timeline()
        timeline_list = [t for t in timeline_list if t.get("chapter_id") != ch_id]
        timeline_list.append({
            "chapter_id": ch_id,
            "volume_id": vol_id,
            "title": title,
            "timeline": timeline_str,
            "location": location_str,
            "chapter_type": chapter_type,
            "word_count": word_count,
            "present_characters": char_names_present,
            "dramatic_goal": dramatic_goal,
            "cliffhanger": cliffhanger_desc,
        })
        # FIND-CT23（FN-2 根治 · 同步修复自伤假阳性）：旧版 append 到尾部，
        # `--force` 重放旧章会把该章条目移到尾部，timeline 陷入乱序——cockpit
        # 节奏遥测、卷末统计与新加的倒置巡检全部失真。按 chapter_id 数字序
        # 稳定排序：任何重放顺序下终态一致（幂等的自然延伸）。
        def _tl_ch_key(_t: Dict[str, Any]) -> int:
            _mm = re.search(r"(\d+)$", str(_t.get("chapter_id", "")))
            return int(_mm.group(1)) if _mm else 0
        timeline_list.sort(key=_tl_ch_key)
        _save_json(self.timeline_file, timeline_list)

        # 8. 即时现场快照 (current.json)
        active_lines = [lid for lid, l in lines_db.items() if l.get("status") == "active"]
        curr_snapshot = {
            "current_vol": vol_id,
            "current_ch": ch_id,
            "last_timeline": timeline_str,
            "last_location": location_str,
            "last_chapter_type": chapter_type,
            "present_characters": char_names_present,
            "active_foreshadowings": active_lines,
            "latest_word_count": word_count,
            "last_dramatic_goal": dramatic_goal,
            "last_cliffhanger": cliffhanger_desc,
        }
        _save_json(self.current_file, curr_snapshot)

        # 9. 更新角色与实体共现矩阵 (co_occurrence.json · 0-Token 历史交集计算)
        co_db = self.get_co_occurrence()
        rel_db = self.get_relations()
        for i, c1 in enumerate(present_chars):
            if not isinstance(c1, dict):
                continue
            cid1 = str(c1.get("id", "")).strip()
            cname1 = str(c1.get("name", "")).strip()
            if not cid1:
                continue
            for j, c2 in enumerate(present_chars):
                if i >= j or not isinstance(c2, dict):
                    continue
                cid2 = str(c2.get("id", "")).strip()
                cname2 = str(c2.get("name", "")).strip()
                if not cid2:
                    continue
                p_sorted = sorted([(cid1, cname1), (cid2, cname2)], key=lambda x: x[0])
                co_key = f"{p_sorted[0][0]}<->{p_sorted[1][0]}"
                co_item = co_db.get(co_key, {
                    "pair": [p_sorted[0][0], p_sorted[1][0]],
                    "names": [p_sorted[0][1], p_sorted[1][1]],
                    "first_seen_ch": ch_id,
                    "last_seen_ch": ch_id,
                    "total_co_occurrences": 0,
                    "chapters": [],
                    "history": [],
                })
                # v4.4.0 FIND-Q：共现矩阵 last_seen_ch 单调不倒退（--force 重放旧章不回拨）。
                if _chapter_num(ch_id) >= _chapter_num(str(co_item.get("last_seen_ch", "") or "")):
                    co_item["last_seen_ch"] = ch_id
                # v4.1 幂等修复：本章已在册则不重复计数/追加历史（旧版重复 sync 会翻倍虚增）
                already_synced = ch_id in co_item.setdefault("chapters", [])
                if not already_synced:
                    co_item["total_co_occurrences"] = co_item.get("total_co_occurrences", 0) + 1
                    co_item["chapters"].append(ch_id)

                rel_item = rel_db.get(f"{cid1}->{cid2}") or rel_db.get(f"{cid2}->{cid1}") or {}
                co_item["last_interaction_summary"] = {
                    "chapter": ch_id,
                    "dynamic": rel_item.get("dynamic_label", "同场"),
                    "unspoken_subtext": rel_item.get("unspoken_subtext", ""),
                    "tension": rel_item.get("tension", 20),
                    "affinity": rel_item.get("affinity", 0),
                }
                if not already_synced:
                    co_item.setdefault("history", []).append({
                        "chapter": ch_id,
                        "dynamic": rel_item.get("dynamic_label", "同场"),
                        "subtext": rel_item.get("unspoken_subtext", ""),
                    })
                co_db[co_key] = co_item
        _save_json(self.co_occurrence_file, co_db)

        # 10. 更新实体全生命周期时间线索引 (entity_timeline.json)
        timeline_db = self.get_entity_timeline()
        for c in present_chars:
            if isinstance(c, dict) and c.get("id"):
                cid = c.get("id")
                c_entry = timeline_db.setdefault(cid, {
                    "id": cid, "name": c.get("name", ""), "type": "person", "events": []
                })
                c_events = c_entry.setdefault("events", [])
                # v4.1 幂等修复：同章同事件不重复追加
                if not any(e.get("chapter") == ch_id and e.get("event") == "出场" for e in c_events):
                    c_events.append({
                        "chapter": ch_id,
                        "event": "出场",
                        "status_in": c.get("status_in", ""),
                        "want": c.get("want", ""),
                        "fear": c.get("fear", ""),
                    })

        # item_deltas 已在函数首部完成单 dict/列表归一化，此处直接复用
        if isinstance(item_deltas, list):
            for it in item_deltas:
                if isinstance(it, dict) and it.get("id"):
                    iid = it.get("id")
                    i_rec = items_db.get(iid, {})
                    i_entry = timeline_db.setdefault(iid, {
                        "id": iid, "name": it.get("name", i_rec.get("name", "")), "type": "item", "events": []
                    })
                    i_events = i_entry.setdefault("events", [])
                    if not any(e.get("chapter") == ch_id and e.get("event") == "流转/使用" for e in i_events):
                        i_events.append({
                            "chapter": ch_id,
                            "event": "流转/使用",
                            "holder": it.get("holder_change", i_rec.get("holder", "主角")),
                            "charges_delta": it.get("charges_delta", 0),
                            "remaining_charges": i_rec.get("charges", -1),
                        })
        _save_json(self.entity_timeline_file, timeline_db)

        # 10.5 细纲正文 ⇄ state_deltas 声明漂移探针（v4.3.2 缺陷#21）
        #
        # 背景：Stage 1 编剧手册此前只点名 chapter_type/present_characters/
        # epistemology/foreshadowing_deltas/state_deltas 五项，对 items/ledger/
        # relation_deltas 全程零提及；而脚手架里 items 与 ledger 两块默认是
        # **注释状态**。于是编剧在剧情脉络里写了「耗尽一次充能」「花掉五百灵石」，
        # Frontmatter 却没有对应声明——引擎只认 Frontmatter，台账静默停留在旧值，
        # 且 sync 成功、check 0 errors，全链路零告警（实测复现）。
        # 这类漏账往往几十章后才在充能对不上时爆发，且极难回溯到具体哪一章。
        # 此处做一次廉价的关键词比对，命中即 warning 提示补声明（只提醒，不猜数改账）。
        try:
            if beats_body:
                _body = re.sub(r"<!--.*?-->", "", beats_body, flags=re.DOTALL)
                _probes = (
                    ("items", bool(item_deltas),
                     ("充能", "耗尽", "用掉", "点燃", "折断", "碎裂", "损毁", "夺走",
                      "易主", "赠予", "交给", "丢失", "遗失", "报废", "熔毁"),
                     "state_deltas.items（charges_delta / holder_change / status）"),
                    ("ledger", bool(state_deltas.get("ledger")),
                     ("灵石", "银两", "赏金", "花掉", "花光", "买下", "赔款", "报酬",
                      "酬金", "付了", "收入", "进账", "债务"),
                     "state_deltas.ledger（pool / delta / reason）"),
                    ("relations", bool(raw_rels),
                     ("反目", "决裂", "翻脸", "结盟", "和解", "背叛", "生分", "交心"),
                     "relation_deltas（tension / dynamic / subtext）"),
                )
                for _name, _declared, _kws, _field in _probes:
                    if _declared:
                        continue
                    _hits = sorted({k for k in _kws if k in _body})
                    if _hits:
                        warnings.append(
                            f"细纲正文提到「{'、'.join(_hits[:4])}」等{_name}相关变动，"
                            f"但 Frontmatter 未作任何声明，本章台账不会发生对应变更。"
                            f"\n      💡 方案：若确有变动，请在细纲补写 {_field}"
                            f"（脚手架中该块默认为注释状态，需取消注释）；若属误报可忽略。"
                        )
        except Exception:
            pass

        # 10.9 FIND-CT73（公理二 · 自愈层）：全表收尾自愈一遍过（幂等）——
        # 数值类型/区间、life_status 归一、伏笔缺章补填、经济数值消毒、
        # 恩怨自指清除、关系轨迹同章去重。全部动作留痕进 healed。
        heal_tables_pass(self, ch_id, healed)

        # 11. 自动持久化当章全时空全息历史快照切片 (history/ch_XXX.json)
        self.save_chapter_snapshot(ch_id)

        return {
            "chapter_id": ch_id,
            "volume_id": vol_id,
            "title": title,
            "word_count": word_count,
            "characters_updated": len(present_chars),
            "new_entities_added": new_ent_count,
            "locked_facts_added": locked_facts_count,
            "lines_summary": line_summary,
            "active_lines_count": len(active_lines),
            "warnings": warnings,
            # FIND-CT73：🩹 自愈动作清单（引擎自己修好的脏数据，逐条可追溯）
            "healed": healed,
        }

    # 兼容别名
    apply_chapter_delta = apply_fine_outline_delta
    get_active_foreshadowings = get_active_lines
    get_characters = get_persons
    get_foreshadowings = get_lines
