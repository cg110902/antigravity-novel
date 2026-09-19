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
    if any(k in cond for k in ("阵亡", "永久湮灭", "身死", "气绝身亡", "被斩杀")):
        return True
    return False


def _chapter_num(chapter_id: str) -> int:
    """提取章节数字编号。"""
    m = re.search(r"(\d+)$", str(chapter_id))
    return int(m.group(1)) if m else 0


_DEATH_KEYWORDS = (
    "阵亡", "永久湮灭", "身死", "气绝身亡", "被斩杀", "deceased", "dead",
    # v4.3.2 缺陷#15：旧词表过窄，漏掉中文最常见的死亡表述。实测「为掩护沈决死于
    # 档案室火场」整条不命中 ⇒ 回落到 last_seen_ch，把死于 ch_004 的齐鸣判成
    # 「已于 ch_003 阵亡」，于是他真正的牺牲章 ch_004 被反诬为「死者复活」，
    # 全书体检对一本完全正常的书常驻 1 条阻断错误。
    "死于", "牺牲", "殒命", "丧生", "身亡", "毙命", "战死", "烧死", "溺亡", "自尽", "遇害",
)


def _ch_order(cid: str) -> int:
    m = re.search(r"(\d+)", str(cid or ""))
    return int(m.group(1)) if m else -1


def get_death_chapter(char_data: Any) -> str:
    """获取角色的阵亡章节。

    v4.3.2 缺陷#15：取 arc_history 中命中死亡语义的**最晚**一章，而非首个命中项
    —— arc_history 不保证按章序排列（实测实际为倒序），首命中会给出错误章号。
    """
    if not isinstance(char_data, dict):
        return ""
    hits = []
    for a in char_data.get("arc_history", []):
        if not isinstance(a, dict):
            continue
        s_out = str(a.get("status_out", "")).lower()
        if any(k in s_out for k in _DEATH_KEYWORDS):
            hits.append(str(a.get("chapter", "")))
    if hits:
        return max(hits, key=_ch_order)

    # 未命中语义关键词但已登记为 deceased（如通过 life_status 显式声明）：
    # 取「最后露面章」与「弧光轨迹最晚一章」中较晚者，避免把死亡当章误判成复活。
    cands = [str(char_data.get("last_seen_ch", "") or "")]
    for a in char_data.get("arc_history", []):
        if isinstance(a, dict) and a.get("chapter"):
            cands.append(str(a["chapter"]))
    cands = [c for c in cands if c]
    return max(cands, key=_ch_order) if cands else ""


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
                if etype in ("person", "character"):
                    if eid not in persons_db:
                        persons_db[eid] = {
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
                        new_ent_count += 1
                elif etype in ("item", "weapon", "tool"):
                    if eid not in items_db:
                        items_db[eid] = {
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
                        new_ent_count += 1
                elif etype in ("place", "location"):
                    if eid not in places_db:
                        places_db[eid] = {
                            "id": eid,
                            "name": ename or eid,
                            "danger_level": ne.get("danger_level", "基础安全区"),
                            "sensory_anchor": ne.get("sensory_anchor", ""),
                            "environment_rules": ne.get("environment_rules", []),
                            "summary": ne.get("summary", ""),
                            "established_ch": ch_id,
                            "visited_chapters": [ch_id],
                        }
                        new_ent_count += 1
                elif etype in ("faction", "organization"):
                    if eid not in factions_db:
                        factions_db[eid] = {
                            "id": eid,
                            "name": ename or eid,
                            "summary": ne.get("summary", ""),
                            "established_ch": ch_id,
                        }
                        new_ent_count += 1
            _save_json(self.persons_file, persons_db)
            _save_json(self.items_file, items_db)
            _save_json(self.places_file, places_db)
            _save_json(self.factions_file, factions_db)

        # 1. 同步人物与心理状态
        persons_db = self.get_persons()
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
            _items_pre = self.get_items()
            for it in item_deltas:
                if not isinstance(it, dict):
                    continue
                _iid = str(it.get("id", "")).strip()
                if not _iid:
                    continue
                _rec = _items_pre.get(_iid, {})
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
                if _rec.get("charges", -1) >= 0 and _rec.get("charges", 0) + _d < 0:
                    _fatal.append(
                        f"道具规则阻断：道具 [{it.get('name') or _iid}] ({_iid}) 充能已耗尽 "
                        f"(当前 {_rec.get('charges')}，拟扣减 {_d})，不可透支使用！\n"
                        f"💡 方案：请在细纲 state_deltas.items 中调整 charges_delta 扣减值，或在前置剧情安排充能。"
                    )
        if _fatal:
            raise GuardError("\n".join(_fatal))


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
                        persons_db[target_pid]["life_status"] = _LIFE_STATUS_NORM[explicit_life]
                    elif cond_text.lower() in _LIFE_STATUS_NORM:
                        persons_db[target_pid]["life_status"] = _LIFE_STATUS_NORM[cond_text.lower()]
                else:
                    s_desc = str(s_val).strip()
                    persons_db[target_pid]["condition"] = s_desc
                    if s_desc.lower() in _LIFE_STATUS_NORM:
                        persons_db[target_pid]["life_status"] = _LIFE_STATUS_NORM[s_desc.lower()]

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
                if irecord.get("charges", -1) >= 0:
                    new_charges = irecord["charges"] + _net_delta
                    if new_charges >= 0:
                        irecord["charges"] = new_charges

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
                    _seed = f"{ch_id}|{d_source}|{d_target}|{d_type}"
                    d_id = "DEBT-AUTO-" + hashlib.sha1(_seed.encode("utf-8")).hexdigest()[:8]

                if d_action == "record":
                    # v4.2 幂等数据层：同 id 恩怨替换而非追加（--force 重放不翻倍）
                    debts_db = [d for d in debts_db if d.get("id") != d_id]
                    debts_db.append({
                        "id": d_id,
                        "source_char": d_source,
                        "target_char": d_target,
                        "type": d_type,
                        "desc": d_desc,
                        "status": "unpaid",
                        "created_ch": ch_id,
                    })
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
