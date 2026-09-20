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
}


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

    返回 "deceased" / "missing" / "" （空串表示无法判定，交由调用方决定）。
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
    if any(k in s for k in _DEATH_KEYWORDS):
        return "deceased"
    if any(k in s for k in ("失踪", "下落不明", "失联", "生死不明")):
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
        self.co_occurrence_file = self.indices_dir / "co_occurrence.json"
        self.entity_timeline_file = self.indices_dir / "entity_timeline.json"

    # --- 读取接口 ---
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
        ch_id = frontmatter.get("chapter_id", "ch_001")
        vol_id = frontmatter.get("volume_id", "vol_01")
        title = frontmatter.get("title", "")
        timeline_str = str(frontmatter.get("timeline", ""))
        location_str = str(frontmatter.get("location", ""))
        chapter_type = str(frontmatter.get("chapter_type", "")).strip()  # 节奏遥测用（v4.1）

        warnings: List[str] = []
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
                    continue
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
                            _eprec["name"] = ename
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
                            _eirec["name"] = ename
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
                            _eplrec["name"] = ename
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
                            _efrec["name"] = ename
                        _paste_declared(_efrec, ne, _FACTION_FM_FIELDS)
                        _mark_updated(_efrec, ch_id)
            # v4.3.2 缺陷#18（P0 · 阻断章仍污染台账）：旧版在此立即落盘 new_entities，
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
                _fatal.append(
                    f"因果冲突阻断：角色 [{_disp_name}] ({_cid}) 已于第 {_d_ch} 章阵亡，不能在后续章节作为在场人登场！\n"
                    f"💡 方案：请在细纲 beats/ch_XXX.md 的 present_characters 中移除该角色；若确系复活反转剧情，请先委派 Stage 4C (novel-evolution) 重构人物档案。"
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

        # 预检通过，方可落盘本章新实体（v4.3.2 缺陷#18）
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

            p_data = persons_db.get(cid, CharacterRecord(id=cid, name=cname).to_dict())
            # 死亡状态校验已前置至事务预检（缺陷#10：写盘前拦截）

            if cname:
                p_data["name"] = cname
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
                    target_pid = cid
                    persons_db[target_pid] = CharacterRecord(id=cid, name=cid).to_dict()

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
                else:
                    places_db[found_id] = {
                        "id": found_id,
                        "name": location_str,
                        "danger_level": "普通",
                        "sensory_anchor": "",
                        "environment_rules": [],
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
                    "sensory_anchor": "",
                    "environment_rules": [],
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
                faction = str(fd.get("action", "plant")).lower().strip()
                fdesc = fd.get("desc", "").strip()
                if not fid:
                    continue

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

                if faction == "plant":
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
            pool_name = ledger_delta.get("pool") or load_config(self.workspace).get("default_pool", "通用资金池")
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
        }

    # 兼容别名
    apply_chapter_delta = apply_fine_outline_delta
    get_active_foreshadowings = get_active_lines
    get_characters = get_persons
    get_foreshadowings = get_lines
