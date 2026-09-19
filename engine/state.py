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
}


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
        return default if default is not None else {}
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
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
                            "summary": ne.get("summary", ""),
                            "established_ch": ch_id,
                            "last_seen_ch": ch_id,
                            "life_status": "alive",
                            "arc_history": [],
                        }
                        new_ent_count += 1
                elif etype == "item":
                    if eid not in items_db:
                        items_db[eid] = {
                            "id": eid,
                            "name": ename or eid,
                            "holder": ne.get("holder", "主角"),
                            "charges": ne.get("charges", -1),
                            "summary": ne.get("summary", ""),
                            "established_ch": ch_id,
                            "last_seen_ch": ch_id,
                        }
                        new_ent_count += 1
                elif etype in ("place", "location"):
                    if eid not in places_db:
                        places_db[eid] = {
                            "id": eid,
                            "name": ename or eid,
                            "summary": ne.get("summary", ""),
                            "established_ch": ch_id,
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
        present_chars = [raw_pres] if isinstance(raw_pres, dict) else (raw_pres if isinstance(raw_pres, list) else [])
        char_names_present: List[str] = []
        raw_sd = frontmatter.get("state_deltas")
        state_deltas = raw_sd if isinstance(raw_sd, dict) else {}
        char_status_deltas = state_deltas.get("character_status") if isinstance(state_deltas.get("character_status"), dict) else {}
        item_deltas = state_deltas.get("items") or []  # v4.2: 提前声明，供事务预检与应用阶段共用

        # ── v4.2 缺陷#10 事务预检：硬约束违规必须在任何写盘前拦截 ──
        # （旧版先落盘后 raise，被阻断章节仍会污染台账：实测 ch_011 流转记录×3）
        _fatal: List[str] = []
        for c in present_chars:
            cc = {"id": c.strip(), "name": ""} if isinstance(c, str) else c
            if not isinstance(cc, dict):
                continue
            _cid = str(cc.get("id", "")).strip()
            if _cid and persons_db.get(_cid, {}).get("life_status") == "deceased":
                _fatal.append(
                    f"因果冲突阻断：角色 [{cc.get('name') or _cid}] ({_cid}) 已在既定事实中阵亡，不能作为在场人登场！\n"
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
                if _rec.get("charges", -1) >= 0 and _rec.get("charges", 0) + _d < 0:
                    _fatal.append(
                        f"道具规则阻断：道具 [{it.get('name') or _iid}] ({_iid}) 充能已耗尽 "
                        f"(当前 {_rec.get('charges')}，拟扣减 {_d})，不可透支使用！\n"
                        f"💡 方案：请在细纲 state_deltas.items 中调整 charges_delta 扣减值，或在前置剧情安排充能。"
                    )
        if _fatal:
            raise GuardError("\n".join(_fatal))


        for c in present_chars:
            if isinstance(c, str):
                # v4.2 修复：紧凑列表形态（present_characters: [p_001, p_006]）此前被
                # 整体跳过——死亡阻断、出场事件、共现统计全部旁路（验收实弹复现）。
                cid = c.strip()
                cname = str(persons_db.get(cid, {}).get("name", "") or "")
                c = {"id": cid, "name": cname}
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
                if cid not in persons_db:
                    continue
                # 显式契约优先：支持字典形态 {life_status: "deceased", condition: "..."}
                if isinstance(s_val, dict):
                    explicit_life = str(s_val.get("life_status", "")).strip().lower()
                    cond_text = str(s_val.get("condition") or s_val.get("status") or s_val.get("desc") or "").strip()
                    if cond_text:
                        persons_db[cid]["condition"] = cond_text
                    if explicit_life in _LIFE_STATUS_NORM:
                        persons_db[cid]["life_status"] = _LIFE_STATUS_NORM[explicit_life]
                    elif cond_text.lower() in _LIFE_STATUS_NORM:
                        persons_db[cid]["life_status"] = _LIFE_STATUS_NORM[cond_text.lower()]
                else:
                    s_desc = str(s_val).strip()
                    persons_db[cid]["condition"] = s_desc
                    if s_desc.lower() in _LIFE_STATUS_NORM:
                        persons_db[cid]["life_status"] = _LIFE_STATUS_NORM[s_desc.lower()]

        _save_json(self.persons_file, persons_db)

        # 2. 同步道具流转与充能约束
        items_db = self.get_items()
        if isinstance(item_deltas, list):
            for it in item_deltas:
                if not isinstance(it, dict):
                    continue
                iid = it.get("id", "").strip()
                iname = it.get("name", "").strip()
                if not iid:
                    continue
                irecord = items_db.get(iid, ItemRecord(id=iid, name=iname).to_dict())
                if iname:
                    irecord["name"] = iname

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
                if irecord.get("charges", -1) >= 0:
                    new_charges = irecord["charges"] + delta_int
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
                })
                items_db[iid] = irecord

        _save_json(self.items_file, items_db)

        # 2.5 同步地点足迹与自动打捞建档
        if location_str:
            places_db = self.get_places()
            loc_match = re.search(r"(loc_\d+)", location_str)
            found_id = loc_match.group(1) if loc_match else None
            if not found_id:
                for pid, prec in places_db.items():
                    if prec.get("name") == location_str or location_str in prec.get("name", ""):
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
        # v4.2 幂等数据层：同章同池流水替换而非追加，池余额 = 全部流水重放
        ledger_db = self.get_ledger()
        ledger_delta = state_deltas.get("ledger") or {}
        if isinstance(ledger_delta, dict):
            pool_name = ledger_delta.get("pool") or load_config(self.workspace).get("default_pool", "通用资金池")
            delta_val = str(ledger_delta.get("delta", "0")).strip()
            try:
                d_num = int(delta_val.replace("+", ""))
            except ValueError:
                d_num = 0
                warnings.append(
                    f"ledger.delta 无法解析为整数: '{delta_val}'（本章经济增量已忽略，请检查细纲书写）"
                )
            if pool_name not in ledger_db.get("pools", {}):
                ledger_db.setdefault("pools", {})[pool_name] = 0
            txs = [
                t for t in ledger_db.get("transactions", [])
                if not (t.get("chapter") == ch_id and t.get("pool") == pool_name)
            ]
            if d_num != 0:
                txs.append({"chapter": ch_id, "pool": pool_name, "delta": d_num, "balance": 0})
            ledger_db["transactions"] = txs
            all_pools = set(ledger_db.get("pools", {}).keys()) | {t.get("pool") for t in txs}
            for p_name in all_pools:
                ledger_db["pools"][p_name] = sum(t.get("delta", 0) for t in txs if t.get("pool") == p_name)
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
                d_id = str(dd.get("id", f"DEBT-{len(debts_db)+1:03d}")).strip()

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

        item_deltas = state_deltas.get("items") or []
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
