"""Novel Studio 实体与因果全生命周期 ID 追踪与发号引擎 (engine/id_tracker.py)。

提供全书 30~50 万字超长篇连载的核心 ID 治理能力：
1. trace_id: 全时空物理 ID 深度回溯与穿透追踪
   (Person / Item / Line / Location / Faction / Debt / Lock / Milestone / Chapter)
2. id_next: 全局唯一物理 ID 确定性自动分配器 (防冲突、防断号)
3. id_list: 全书活跃物理资产与设定 ID 总账清册
4. check_id_integrity: 细纲与台账 ID 格式与因果强校验 (防悬空、防偷跑、防拼写笔误)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _load_json(file_path: Path, default: Any = None) -> Any:
    """v4.2.1 缺陷#15：旧版静默吞损坏 JSON（返回默认值）——坏表会让发号器复用
    已占 ID、让完整性校验假绿。现对齐 state.py 数据安全契约：损坏即隔离并硬失败。"""
    from engine.state import _load_json as _hard_load

    return _hard_load(file_path, default=default if default is not None else {})


def _strip_html_comments(txt: str) -> str:
    """v4.3：发号扫描前的文本消毒。

    双重自保：
    1. 剥离 HTML 注释块——beats 任务卡的机要简报以 <!-- … --> 包裹注入，其中含
       「🆔 下一可用物理 ID 速查」（如 fac_005）；若计入，速查块会把发号水位逐章顶高。
    2. 抹除 {{slot:KEY|DEFAULT}} 的 KEY 段——模板槽位键名含伪 ID（如 fac_4_name 中的
       fac_4），会被编号正则误计为已占号（实测新书势力直接跳到 fac_005）。
       DEFAULT 段保留：它是作者可能采纳的建议 ID（如 GUN-001），保守计入防撞号。

    FIND-CT44（ID-7 两处漏网）：
    (a) 无管道形态 `{{slot:p_004}}` 旧版不被清洗（正则要求带 `|`），其中伪 ID
        被编号正则计入——正是本注释想防的场景的漏网形态；
    (b) 未闭合的 `<!--` 旧版用非贪婪 DOTALL 一路吃到文件尾，其后所有真实 ID
        被静默忽略 → 发号撞号。修正为手工扫描：找不到闭合 `-->` 时保守保留
        其后内容（吞内容与漏数同样导致撞号，保留至少让真实 ID 进入扫描）。
    """
    if "<!--" in txt:
        _out: List[str] = []
        _i = 0
        while _i < len(txt):
            _j = txt.find("<!--", _i)
            if _j == -1:
                _out.append(txt[_i:])
                break
            _out.append(txt[_i:_j])
            _k = txt.find("-->", _j)
            if _k == -1:
                _out.append(txt[_j:])
                break
            _i = _k + 3
        txt = "".join(_out)
    txt = re.sub(r"\{\{slot:[^|}]*\|", "{{slot:|", txt)
    txt = re.sub(r"\{\{slot:[^{}|]*\}\}", "", txt)
    return txt


CANONICAL_PREFIXES = {
    "person": ("p_", r"p_(\d+)"),
    "char": ("p_", r"p_(\d+)"),
    "item": ("it_", r"it_(\d+)"),
    "gun": ("GUN-", r"GUN-(\d+)"),
    "kno": ("KNO-", r"KNO-(\d+)"),
    "mis": ("MIS-", r"MIS-(\d+)"),
    "line": ("GUN-", r"(?:GUN|KNO|MIS)-(\d+)"),
    "loc": ("loc_", r"loc_(\d+)"),
    "location": ("loc_", r"loc_(\d+)"),
    "place": ("loc_", r"loc_(\d+)"),
    "fac": ("fac_", r"fac_(\d+)"),
    "faction": ("fac_", r"fac_(\d+)"),
    "debt": ("DEBT-", r"DEBT-(\d+)"),
    "lock": ("LOCK-", r"LOCK-(\d+)"),
    "ms": ("ms_", r"ms_(\d+)"),
    "milestone": ("ms_", r"ms_(\d+)"),
}


def detect_id_category(entity_id: str) -> str:
    """根据 ID 前缀判断其所属法定实体类型。"""
    eid = entity_id.strip()
    if eid.startswith("p_"):
        return "person"
    elif eid.startswith("it_"):
        return "item"
    elif eid.startswith("GUN-"):
        return "gun"
    elif eid.startswith("KNO-"):
        return "kno"
    elif eid.startswith("MIS-"):
        return "mis"
    elif eid.startswith("loc_"):
        return "location"
    elif eid.startswith("fac_"):
        return "faction"
    elif eid.startswith("LOCK-"):
        return "lock"
    elif eid.startswith("DEBT-"):
        return "debt"
    elif eid.startswith("ms_"):
        return "milestone"
    elif eid.startswith("ch_"):
        return "chapter"
    return "unknown"


def id_next(workspace: Path, category: str, sub_type: str = "", exclude: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """计算并发放下一个安全、不冲突的物理 ID。

    FIND-CT5（ID-1）：``exclude`` 接受本批次已分配、但因事务未提交而尚未落盘/回写的
    「在途号」。纯 max+1 的分配器在 proposal auto 涌现循环里对同章多个新实体连续调用时
    会读到完全相同的工作区状态，发出同一个 ID（实测两个新人物都得 p_005）——sync 时
    `if eid not in xxx_db` 把第二条静默丢弃，实体永久不入账且 check 假绿。
    传入在途集合后，分配结果逐次自增，与落盘后的视角一致。
    """
    cat = category.strip().lower()
    if cat == "line" and sub_type:
        cat = sub_type.strip().lower()

    if cat not in CANONICAL_PREFIXES:
        raise ValueError(
            f"未知的 ID 实体类型: '{category}'。\n"
            f"💡 方案：支持的实体类型包括: person, item, gun, kno, mis, location, faction, debt, lock, milestone。"
        )

    prefix, pattern = CANONICAL_PREFIXES[cat]
    max_num = 0

    state_dir = workspace / "state"

    # 1. 扫描对应的 state 表
    if cat in ("person", "char"):
        p_db = _load_json(state_dir / "persons.json", {})
        for k in p_db.keys():
            m = re.match(pattern, k)
            if m:
                max_num = max(max_num, int(m.group(1)))
    elif cat == "item":
        i_db = _load_json(state_dir / "items.json", {})
        for k in i_db.keys():
            m = re.match(pattern, k)
            if m:
                max_num = max(max_num, int(m.group(1)))
    elif cat in ("gun", "kno", "mis", "line"):
        l_db = _load_json(state_dir / "lines.json", {})
        for k in l_db.keys():
            m = re.match(pattern, k)
            if m:
                max_num = max(max_num, int(m.group(1)))
    elif cat in ("loc", "location", "place"):
        pl_db = _load_json(state_dir / "places.json", {})
        for k in pl_db.keys():
            m = re.match(pattern, k)
            if m:
                max_num = max(max_num, int(m.group(1)))
    elif cat in ("fac", "faction"):
        fc_db = _load_json(state_dir / "factions.json", {})
        for k in fc_db.keys():
            m = re.match(pattern, k)
            if m:
                max_num = max(max_num, int(m.group(1)))
    elif cat == "debt":
        d_db = _load_json(state_dir / "debts.json", [])
        for d in d_db:
            m = re.match(pattern, d.get("id", ""))
            if m:
                max_num = max(max_num, int(m.group(1)))
    elif cat == "lock":
        lk_db = _load_json(state_dir / "locked.json", [])
        for lk in lk_db:
            m = re.match(pattern, lk.get("id", ""))
            if m:
                max_num = max(max_num, int(m.group(1)))
    elif cat in ("ms", "milestone"):
        ms_db = _load_json(state_dir / "milestones.json", [])
        for ms in ms_db:
            m = re.match(pattern, ms.get("id", ""))
            if m:
                max_num = max(max_num, int(m.group(1)))

    # 2. 扫描所有待同步或已编细纲中的 ID，防止跨章未同步期间撞号
    # FIND-CT31（ID-2·扫描盲区）：旧版只扫 outlines/**/beats/*.md——编剧按卷纲
    # 预排的 ID（卷纲先行、beats 未落）与 final/raw 正文中引用的 ID 都不在扫描
    # 范围，`id next` 会重发已占用号造成跨文档撞号（agents 报告实测场景）。
    # 扩为全 outlines + 全 manuscript；单文件 >2MB 跳过防历史巨稿拖慢发号。
    for _scan_dir, _glob_pat in (("outlines", "**/*.md"), ("manuscript", "**/*.md")):
        _sd = workspace / _scan_dir
        if not _sd.exists():
            continue
        for _f in _sd.glob(_glob_pat):
            try:
                if _f.stat().st_size > 2 * 1024 * 1024:
                    continue
                txt = _strip_html_comments(_f.read_text(encoding="utf-8-sig", errors="replace"))
            except OSError:
                continue
            matches = re.findall(pattern, txt)
            for m in matches:
                try:
                    max_num = max(max_num, int(m))
                except ValueError:
                    pass

    # 3. 扫描设定卡片与实体文档（characters/, entities/, bible/, worldview/ 等），防止撞号
    for doc_dir_name in ("characters", "entities", "bible", "worldview", "docs"):
        doc_dir = workspace / doc_dir_name
        if doc_dir.exists():
            for mf in doc_dir.glob("**/*.md"):
                txt = _strip_html_comments(mf.read_text(encoding="utf-8-sig", errors="replace"))
                matches = re.findall(pattern, txt)
                for m in matches:
                    try:
                        max_num = max(max_num, int(m))
                    except ValueError:
                        pass

    next_num = max_num + 1
    # FIND-CT5：跳过本批次在途号（已分配未落盘），逐次自增直到真正空闲
    _ex = {str(x) for x in (exclude or [])}
    while _ex and f"{prefix}{next_num:03d}" in _ex:
        next_num += 1
    generated_id = f"{prefix}{next_num:03d}"

    return {
        "category": cat,
        "prefix": prefix,
        "current_max": max_num,
        "next_id": generated_id,
        "format": f"{prefix}XXX",
    }


def id_list(workspace: Path, filter_type: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """汇总并列出工作区中所有已注册的物理 ID 清单。"""
    state_dir = workspace / "state"
    target_filter = filter_type.strip().lower() if filter_type else None

    result: Dict[str, List[Dict[str, Any]]] = {
        "persons": [],
        "items": [],
        "lines": [],
        "places": [],
        "factions": [],
        "debts": [],
        "locked_facts": [],
        # FIND-CT27（ID-3）：ms_ 是法定 ID 类目（id next milestone / trace 均正常），
        # 旧版总账清册没有它 ⇒ `id list milestone` 静默空输出，作者误判无里程碑
        # 而重发 ms_001。补齐类目。
        "milestones": [],
    }

    # 1. 人物
    if not target_filter or target_filter in ("person", "char", "p"):
        p_db = _load_json(state_dir / "persons.json", {})
        for pid, p in sorted(p_db.items()):
            result["persons"].append({
                "id": pid,
                "name": p.get("name", ""),
                "role": p.get("role", "supporting"),
                "status": p.get("status", "active"),
                "life_status": p.get("life_status", "alive"),
                "condition": p.get("condition", "正常"),
                "last_seen_ch": p.get("last_seen_ch", ""),
            })

    # 2. 道具
    if not target_filter or target_filter in ("item", "it"):
        i_db = _load_json(state_dir / "items.json", {})
        for iid, it in sorted(i_db.items()):
            result["items"].append({
                "id": iid,
                "name": it.get("name", ""),
                "holder": it.get("holder", "未知"),
                "charges": it.get("charges", -1),
                "condition": it.get("condition", "完好"),
                "last_seen_ch": it.get("last_seen_ch", ""),
            })

    # 3. 伏笔
    if not target_filter or target_filter in ("line", "gun", "kno", "mis"):
        l_db = _load_json(state_dir / "lines.json", {})
        for lid, l in sorted(l_db.items()):
            result["lines"].append({
                "id": lid,
                "name": l.get("name", ""),
                "type": l.get("type", "GUN"),
                "tier": l.get("tier", "A"),
                "status": l.get("status", "active"),
                "target_ch": l.get("target_ch", ""),
                "planted_ch": l.get("planted_ch", ""),
                "desc": l.get("desc", ""),
            })

    # 4. 地点
    if not target_filter or target_filter in ("loc", "location", "place"):
        pl_db = _load_json(state_dir / "places.json", {})
        for plid, pl in sorted(pl_db.items()):
            result["places"].append({
                "id": plid,
                "name": pl.get("name", ""),
                "summary": pl.get("summary", ""),
                "visited_chapters": pl.get("visited_chapters", []),
            })

    # 5. 势力
    if not target_filter or target_filter in ("fac", "faction"):
        fc_db = _load_json(state_dir / "factions.json", {})
        for fcid, fc in sorted(fc_db.items()):
            result["factions"].append({
                "id": fcid,
                "name": fc.get("name", ""),
                "leader": fc.get("leader", ""),
                "summary": fc.get("summary", ""),
            })

    # 6. 恩怨
    if not target_filter or target_filter in ("debt",):
        d_db = _load_json(state_dir / "debts.json", [])
        for d in d_db:
            result["debts"].append({
                "id": d.get("id", ""),
                "type": d.get("type", "grudge"),
                "target_char": d.get("target_char", ""),
                "status": d.get("status", "unpaid"),
                "created_ch": d.get("created_ch", ""),
                "desc": d.get("desc", ""),
            })

    # 7. 锁定事实
    if not target_filter or target_filter in ("lock", "locked"):
        lk_db = _load_json(state_dir / "locked.json", [])
        for lk in lk_db:
            result["locked_facts"].append({
                "id": lk.get("id", ""),
                "fact": lk.get("fact", ""),
                "domain": lk.get("domain", "plot"),
                "established_ch": lk.get("established_ch", ""),
            })

    # 8. 里程碑（FIND-CT27 / ID-3）
    if not target_filter or target_filter in ("ms", "milestone", "milestones"):
        ms_db = _load_json(state_dir / "milestones.json", [])
        for ms in ms_db:
            result["milestones"].append({
                "id": ms.get("id", ""),
                "title": ms.get("title", ""),
                "status": ms.get("status", "pending"),
                "target_ch": ms.get("target_ch", ""),
                "achieved_ch": ms.get("achieved_ch", ""),
                "desc": ms.get("desc", ""),
            })

    return result


def trace_id(workspace: Path, target_id: str) -> Dict[str, Any]:
    """深度追踪指定物理 ID 的全生命周期流转轨迹与因果全息信息。"""
    tid = target_id.strip()
    category = detect_id_category(tid)
    state_dir = workspace / "state"

    report: Dict[str, Any] = {
        "id": tid,
        "category": category,
        "found": False,
        "profile": {},
        "trajectory": [],
        "related_entities": {},
        "human_readable": "",
    }

    # 1. 角色追踪 (Person Trace)
    if category == "person":
        p_db = _load_json(state_dir / "persons.json", {})
        p_data = p_db.get(tid)
        if not p_data:
            # 尝试通过名字逆查
            p_data = next((v for v in p_db.values() if v.get("name") == tid), None)
            if p_data:
                tid = p_data.get("id", tid)

        if p_data:
            report["found"] = True
            report["id"] = tid
            # v4.4.0 FIND-M：trace profile 与 human_readable 补齐「细纲声明、sync 落账」
            # 的全部 schema 契约字段——旧版 realm 竟被 `tier_name or realm` 抢占（FIND-L
            # 已让 realm 真正落账却查不到），aliases/attitude/faction/tier_rank/need/lie/
            # micro_actions/injury/renown/power_benchmark/dossier 落账后零展示。现按
            # 「有值才显」，不造噪音也不漏实质。
            report["profile"] = {
                "name": p_data.get("name", ""),
                "role": p_data.get("role", "supporting"),
                "realm": p_data.get("realm") or p_data.get("tier_name") or "凡阶",
                "tier_name": p_data.get("tier_name", ""),
                "tier_rank": p_data.get("tier_rank", 1),
                "power_benchmark": p_data.get("power_benchmark", ""),
                "life_status": p_data.get("life_status", "alive"),
                "condition": p_data.get("condition", "正常"),
                "injury_level": p_data.get("injury_level", 0),
                "injury_desc": p_data.get("injury_desc", "无伤"),
                "renown": p_data.get("renown", 0),
                "faction": p_data.get("faction", ""),
                "attitude": p_data.get("attitude", "neutral"),
                "aliases": p_data.get("aliases", []),
                "micro_actions": p_data.get("micro_actions", []),
                "dossier": p_data.get("dossier", ""),
                "want": p_data.get("want", "无"),
                "fear": p_data.get("fear", "无"),
                "need": p_data.get("need", ""),
                "lie": p_data.get("lie", ""),
                "latent_mood": p_data.get("latent_mood", "无"),
                "physiological_leak": p_data.get("physiological_leak", "无"),
                "vulnerability": p_data.get("vulnerability", "无"),
                "quirk": p_data.get("quirk", "无特殊怪癖"),
                "taboo": p_data.get("taboo", "无触碰雷区"),
                "last_seen_ch": p_data.get("last_seen_ch", "初始"),
            }

            # 登场轨迹 (来自 arc_history)
            arc = p_data.get("arc_history", [])
            traj = []
            for a in arc:
                ch = a.get("chapter", "")
                details = f"诉求: {a.get('want', '')} ｜ 忌惮: {a.get('fear', '')}"
                if a.get("latent_mood"):
                    details += f" ｜ 隐性底色: {a.get('latent_mood')}"
                if a.get("physiological_leak"):
                    details += f" ｜ 应激物象: {a.get('physiological_leak')}"
                traj.append({
                    "chapter": ch,
                    "event": f"入场状态: {a.get('status_in', '正常')} ➔ 出场状态: {a.get('status_out', '正常')}",
                    "details": details,
                })
            report["trajectory"] = traj

            # 关联道具 (持有人是此角色)
            i_db = _load_json(state_dir / "items.json", {})
            held_items = [f"[{iid}] {it.get('name')} (充能: {it.get('charges')})" for iid, it in i_db.items() if it.get("holder") in (tid, p_data.get("name"))]
            report["related_entities"]["held_items"] = held_items

            # 关联恩怨
            d_db = _load_json(state_dir / "debts.json", [])
            debts = [f"[{d.get('id')}] {d.get('type')}: {d.get('desc')} (对象: {d.get('target_char')}, 状态: {d.get('status')})" for d in d_db if d.get("target_char") in (tid, p_data.get("name")) or d.get("source_char") == tid]
            report["related_entities"]["debts"] = debts

            # 关联动态情感网络 (relations.json)
            rel_db = _load_json(state_dir / "relations.json", {})
            relations_list = []
            for r_key, r_item in rel_db.items():
                if tid in r_key or p_data.get("name") in r_key:
                    aff = r_item.get("affinity", 0)
                    aff_str = f"+{aff}" if aff > 0 else str(aff)
                    relations_list.append(
                        f"[{r_item.get('dynamic_label', '动态')}] 关联 `{r_key}` (温标: {aff_str}, 张力: 🔥{r_item.get('tension', 0)}/100, 心结: “{r_item.get('unspoken_subtext')}”)"
                    )
            report["related_entities"]["relations"] = relations_list

            # 组织终端文本
            _pf = report["profile"]
            _extras = []
            if _pf.get("need"):
                _extras.append(f"深层需求 [{_pf['need']}]")
            if _pf.get("lie"):
                _extras.append(f"自我谎言 [{_pf['lie']}]")
            lines = [
                f"👤 【ID 深度追踪报告：{tid} · {p_data.get('name')}】",
                f"   - 角色定位：{_pf['role']} ｜ 境界：{_pf['realm']}"
                + (f" ｜ 品阶：{_pf['tier_name']} (T{_pf['tier_rank']})" if _pf.get("tier_name") else ""),
                f"   - 生死与状态：{_pf['life_status']} (肉身: {_pf['condition']})"
                + (f" ｜ 伤势：{_pf['injury_level']} 级 ({_pf['injury_desc']})" if _pf.get("injury_level") or _pf.get("injury_desc") != "无伤" else ""),
            ]
            if _pf.get("faction"):
                lines.append(f"   - 阵营与态度：{_pf['faction']} ｜ {_pf.get('attitude') or 'neutral'}")
            if _pf.get("aliases"):
                lines.append(f"   - 别名：{'、'.join(_pf['aliases'])}")
            if _pf.get("renown"):
                lines.append(f"   - 声望：{_pf['renown']}")
            if _pf.get("power_benchmark"):
                lines.append(f"   - 战力标尺：{_pf['power_benchmark']}")
            if _pf.get("micro_actions"):
                lines.append(f"   - 动作库：{'、'.join(_pf['micro_actions'])}")
            if _pf.get("dossier"):
                lines.append(f"   - 档案：{_pf['dossier']}")
            lines += [
                f"   - 核心心理：渴望 [{_pf['want']}] ｜ 恐惧 [{_pf['fear']}]"
                + (" ｜ " + " ｜ ".join(_extras) if _extras else ""),
                f"   - 隐性底色：当前情绪荷载 [{_pf['latent_mood']}] ｜ 应激动作 [{_pf['physiological_leak']}]",
                f"   - 心理软肋：破防触点 [{_pf['vulnerability']}]",
                f"   - 反常刺点：怪癖 [{_pf['quirk']}] ｜ 雷区 [{_pf['taboo']}]",
                f"   - 登场履历：共登场 {len(traj)} 次，最近现身于第 {_pf['last_seen_ch']} 章",
            ]
            if traj:
                lines.append("   - 章节心境与隐性情绪演化轨迹：")
                for t in traj:
                    lines.append(f"     * [{t['chapter']}] {t['event']}")
                    if t['details'].strip():
                        lines.append(f"       └─ {t['details']}")
            if relations_list:
                lines.append("   - 动态情感与网络 (Relations)：")
                for rl in relations_list:
                    lines.append(f"     * 💘 {rl}")
            if held_items:
                lines.append(f"   - 支配持有资产：{', '.join(held_items)}")
            if debts:
                lines.append(f"   - 牵涉恩怨情仇：{'; '.join(debts)}")

            report["human_readable"] = "\n".join(lines)
            return report

    # 2. 道具追踪 (Item Trace)
    elif category == "item":
        i_db = _load_json(state_dir / "items.json", {})
        it_data = i_db.get(tid)
        if not it_data:
            it_data = next((v for v in i_db.values() if v.get("name") == tid), None)
            if it_data:
                tid = it_data.get("id", tid)

        if it_data:
            report["found"] = True
            report["id"] = tid
            # v4.4.0 FIND-M：补 max_charges/cost_per_use/tier_rank/tier_name——sync 已落账、
            # 但旧版 trace 零展示的 schema 承诺字段。
            report["profile"] = {
                "name": it_data.get("name", ""),
                "holder": it_data.get("holder", "未知"),
                "charges": it_data.get("charges", -1),
                "max_charges": it_data.get("max_charges", -1),
                "cost_per_use": it_data.get("cost_per_use", ""),
                "tier_rank": it_data.get("tier_rank", 1),
                "tier_name": it_data.get("tier_name", ""),
                "condition": it_data.get("condition", "完好"),
                "summary": it_data.get("summary", ""),
                "last_seen_ch": it_data.get("last_seen_ch", "初始"),
            }
            # 流转轨迹 (transfer_history)
            trans = it_data.get("transfer_history", [])
            traj = []
            for tr in trans:
                traj.append({
                    "chapter": tr.get("chapter", ""),
                    "event": f"持有流转: {tr.get('holder_change', '')} ｜ 充能变动: {tr.get('charges_delta', 0)} (剩余: {tr.get('remaining_charges', -1)})",
                })
            report["trajectory"] = traj

            lines = [
                f"⚔️ 【ID 深度追踪报告：{tid} · {it_data.get('name')}】",
                f"   - 道具定位：{it_data.get('summary') or '核心道具/法宝'}",
            ]
            if report["profile"].get("tier_name") or (report["profile"].get("tier_rank") or 1) != 1:
                _tname = report["profile"].get("tier_name")
                _trank = report["profile"].get("tier_rank") or 1
                lines.append(f"   - 品阶：{_tname or ('Tier ' + str(_trank))}")
            lines += [
                f"   - 当前支配者：{report['profile']['holder']}",
            ]
            _c = report["profile"]["charges"]
            _mc = report["profile"]["max_charges"]
            _chg_line = f"   - 充能与耐久：剩余可用 {_c} 次" + (f" / 上限 {_mc}" if _mc and _mc >= 0 else "")
            if report["profile"].get("cost_per_use"):
                _chg_line += f" ｜ 单次代价: {report['profile']['cost_per_use']}"
            _chg_line += f" (物理状态: {report['profile']['condition']})"
            lines.append(_chg_line)
            lines.append(f"   - 活跃记录：最近现身于第 {report['profile']['last_seen_ch']} 章 ｜ 历史流转变动 {len(traj)} 次")
            if traj:
                lines.append("   - 全生命周期流转与消耗轨迹：")
                for t in traj:
                    lines.append(f"     * [{t['chapter']}] {t['event']}")

            report["human_readable"] = "\n".join(lines)
            return report

    # 3. 伏笔暗线追踪 (Line Trace: GUN / KNO / MIS)
    elif category in ("gun", "kno", "mis", "line"):
        l_db = _load_json(state_dir / "lines.json", {})
        l_data = l_db.get(tid)
        if not l_data:
            l_data = next((v for v in l_db.values() if v.get("name") == tid), None)
            if l_data:
                tid = l_data.get("id", tid)

        if l_data:
            report["found"] = True
            report["id"] = tid
            report["profile"] = {
                "name": l_data.get("name", ""),
                "type": l_data.get("type", "GUN"),
                "tier": l_data.get("tier", "A"),
                "status": l_data.get("status", "active"),
                "target_ch": l_data.get("target_ch", ""),
                "planted_ch": l_data.get("planted_ch", ""),
                "revealed_chs": l_data.get("revealed_chs", []),
                "resolved_ch": l_data.get("resolved_ch", ""),
                "desc": l_data.get("desc", ""),
            }

            traj = []
            if l_data.get("planted_ch"):
                traj.append({
                    "chapter": l_data.get("planted_ch"),
                    "action": "plant (埋设)",
                    "desc": l_data.get("desc", ""),
                })
            for rch in l_data.get("revealed_chs", []):
                traj.append({
                    "chapter": rch,
                    "action": "reveal (推进/揭示一角)",
                    "desc": "剧情推进暴露线索与因果张力",
                })
            if l_data.get("resolved_ch"):
                traj.append({
                    "chapter": l_data.get("resolved_ch"),
                    "action": "resolve (闭环回收)",
                    "desc": "暗线全面引爆收束，兑现爽点承诺",
                })

            report["trajectory"] = traj

            lines = [
                f"💣 【ID 深度追踪报告：{tid} · {l_data.get('name')}】",
                f"   - 伏笔分类：[{l_data.get('type')}] ｜ 战略量级：{l_data.get('tier', 'A')}阶 ｜ 当前状态：{l_data.get('status', 'active')}",
                f"   - 预期收网：第 {l_data.get('target_ch') or '待定'} 章 ｜ 首次埋于：第 {l_data.get('planted_ch')} 章",
                f"   - 物理物象/事实描述：{l_data.get('desc')}",
            ]
            if traj:
                lines.append("   - 因果演进生命周期轨迹：")
                for t in traj:
                    lines.append(f"     * [{t['chapter']}] {t['action']} ➔ {t['desc']}")

            report["human_readable"] = "\n".join(lines)
            return report

    # 4. 地点追踪 (Location Trace)
    elif category == "location":
        pl_db = _load_json(state_dir / "places.json", {})
        pl_data = pl_db.get(tid)
        if pl_data:
            report["found"] = True
            report["profile"] = pl_data
            v_chs = pl_data.get("visited_chapters", [])
            report["trajectory"] = [{"chapter": ch, "event": "发生核心剧情"} for ch in v_chs]
            lines = [
                f"🗺️ 【ID 深度追踪报告：{tid} · {pl_data.get('name')}】",
                f"   - 地点简介：{pl_data.get('summary') or '无特殊说明'}",
            ]
            # v4.4.0 FIND-M：补危险层级与感官物象（sync 可落账，旧版无展示）。
            if pl_data.get("danger_level") or (pl_data.get("danger_tier") or 1) > 1:
                lines.append(f"   - 危险度：{pl_data.get('danger_level') or 'Tier ' + str(pl_data.get('danger_tier'))}"
                             + (f" (T{pl_data.get('danger_tier')})" if pl_data.get("danger_tier") else ""))
            if pl_data.get("sensory_anchor"):
                lines.append(f"   - 感官物象：{pl_data['sensory_anchor']}")
            lines.append(f"   - 发生章节：共在此展开 {len(v_chs)} 次剧情 ({', '.join(v_chs) if v_chs else '暂无历史记录'})")
            report["human_readable"] = "\n".join(lines)
            return report

    # 5. 恩怨账本追踪 (Debt Trace)
    elif category == "debt":
        d_db = _load_json(state_dir / "debts.json", [])
        d_data = next((d for d in d_db if d.get("id") == tid), None)
        if d_data:
            report["found"] = True
            report["profile"] = d_data
            lines = [
                f"⚖️ 【ID 深度追踪报告：{tid}】",
                f"   - 恩怨性质：[{d_data.get('type')}] ｜ 结怨发起：{d_data.get('source_char')} ➔ 针对目标：{d_data.get('target_char')}",
                f"   - 履约状态：{d_data.get('status', 'unpaid')} (立于第 {d_data.get('created_ch')} 章)",
                f"   - 核心因由：{d_data.get('desc')}",
            ]
            if d_data.get("settled_ch"):
                lines.append(f"   - 平账终结：已于第 {d_data.get('settled_ch')} 章彻底平账闭环")
            report["human_readable"] = "\n".join(lines)
            return report

    # 6. 法定锁定事实追踪 (Lock Trace)
    elif category == "lock":
        lk_db = _load_json(state_dir / "locked.json", [])
        lk_data = next((lk for lk in lk_db if lk.get("id") == tid), None)
        if lk_data:
            report["found"] = True
            report["profile"] = lk_data
            lines = [
                f"🔒 【ID 深度追踪报告：{tid} · 不可逆法定既定事实】",
                f"   - 确立章节：第 {lk_data.get('established_ch')} 章 ｜ 适用领域：{lk_data.get('domain', 'plot')}",
                f"   - 铁律事实：{lk_data.get('fact')}",
                f"   - 约束效力：全书长程不可违背，后续所有章节自动继承该既定事实",
            ]
            report["human_readable"] = "\n".join(lines)
            return report

    # 7. 势力追踪 (Faction Trace) —— v4.3 缺陷#B11：补齐缺失的专属分支
    # （旧版按名逆查到 fac_XXX 后递归坠落兜底、永远报“未检索到”）
    elif category == "faction":
        fc_db = _load_json(state_dir / "factions.json", {})
        fc_data = fc_db.get(tid)
        if not fc_data:
            fc_data = next((v for v in fc_db.values() if v.get("name") == tid), None)
            if fc_data:
                tid = fc_data.get("id", tid)

        if fc_data:
            report["found"] = True
            report["id"] = tid
            report["profile"] = fc_data
            # 关联成员：人物台账中 faction/affiliation 指向本势力（ID 或名称）
            p_db = _load_json(state_dir / "persons.json", {})
            members = []
            for pid, p in p_db.items():
                aff = str(p.get("faction", "") or p.get("affiliation", "") or "").strip()
                if aff and aff in (tid, fc_data.get("name", "")):
                    members.append(f"[{pid}] {p.get('name', '')} ({p.get('role', 'supporting')})")
            report["related_entities"]["members"] = members
            lines = [
                f"🏴 【ID 深度追踪报告：{tid} · {fc_data.get('name')}】",
                f"   - 势力领袖：{fc_data.get('leader', '未知')} ｜ 本部坐标：{fc_data.get('headquarters', '未知')}",
            ]
            # v4.4.0 FIND-M：scale_tier/core_assets/diplomacy 已有值才显（sync 可落账）。
            if (fc_data.get("scale_tier") or 0) > 1:
                lines.append(f"   - 规模层级：{fc_data.get('scale_tier')}")
            if fc_data.get("core_assets"):
                lines.append(f"   - 核心资产：{'、'.join(fc_data['core_assets'])}")
            if fc_data.get("diplomacy"):
                _dip = "；".join(f"{k}→{v}" for k, v in fc_data["diplomacy"].items())
                lines.append(f"   - 外交网络：{_dip}")
            lines += [
                f"   - 设定卡片：{fc_data.get('card') or '未建档'}",
                f"   - 在编成员：共 {len(members)} 人" + (f"（{', '.join(members[:8])}）" if members else ""),
            ]
            report["human_readable"] = "\n".join(lines)
            return report

    # 8. 里程碑追踪 (Milestone Trace) —— v4.3 缺陷#B11：补齐缺失的专属分支
    elif category == "milestone":
        ms_db = _load_json(state_dir / "milestones.json", [])
        ms_data = next((m for m in ms_db if m.get("id") == tid), None)
        if not ms_data:
            ms_data = next((m for m in ms_db if m.get("title") == tid or m.get("name") == tid), None)
            if ms_data:
                tid = ms_data.get("id", tid)

        if ms_data:
            report["found"] = True
            report["id"] = tid
            report["profile"] = ms_data
            lines = [
                f"🚩 【ID 深度追踪报告：{tid} · {ms_data.get('title') or ms_data.get('name', '')}】",
                f"   - 战略定位：第 {ms_data.get('target_ch', '待定')} 章关键节点 ｜ 当前状态：{ms_data.get('status', 'pending')}",
                f"   - 事件描述：{ms_data.get('desc', '无')}",
            ]
            if ms_data.get("achieved_ch"):
                lines.append(f"   - 达成记录：已于第 {ms_data.get('achieved_ch')} 章兑现")
            report["human_readable"] = "\n".join(lines)
            return report

    # 9. 章节追踪 (Chapter Trace) —— v4.3 缺陷#B11：补齐缺失的专属分支
    elif category == "chapter":
        sync_log = _load_json(state_dir / "sync_log.json", {})
        entry = sync_log.get(tid)
        manuscript = list(workspace.glob(f"manuscript/*/final/{tid}.md"))
        prose_exists = bool(manuscript)
        beats = list(workspace.glob(f"outlines/**/beats/{tid}.md"))
        report["found"] = bool(entry or prose_exists or beats)
        if report["found"]:
            # v4.3 R2：优先读 sync_log 元数据（v4.3 起封存条目已带 title/word_count），
            # 兼容旧格式封存日志——回源 synopsis.json 补全
            title = (entry or {}).get("title", "")
            word_count = (entry or {}).get("word_count", 0) or 0
            if not title and not word_count:
                syn = _load_json(state_dir / "synopsis.json", {}).get(tid, {})
                title = syn.get("title", "")
                word_count = syn.get("word_count", 0) or 0
            lines = [
                f"📖 【ID 深度追踪报告：{tid} · {title or '章节归档'}】",
                f"   - 封存状态：{'✅ 已入账（sync_log 登记）' if entry else '⚠️ 未入账（final/beats 存在但 sync_log 无记录）'}",
                f"   - 正文定稿：{'存在: ' + str(manuscript[0].relative_to(workspace)) if prose_exists else '未找到 final 定稿'}",
                f"   - 章节细纲：{'存在: ' + str(beats[0].relative_to(workspace)) if beats else '未装配'}",
            ]
            if word_count:
                wc_line = f"   - 入账字数：{word_count} 字"
                wc_line += f" ｜ 入账时间：{entry.get('synced_at', '未知')}" if entry else "（来自剧梗记录，尚未入账）"
                lines.append(wc_line)
            report["human_readable"] = "\n".join(lines)
            return report

    # 10. 全库逆查兜底 (精确匹配优先)
    # 10.1 第一遍：全库精确匹配实体名称 (name == tid)
    # FIND-CT46（ID-6a·无限递归）：台账条目 id==name 的畸形数据（手工编辑产生）
    # 会让下列递归以同一参数无限进行 → RecursionError → exit 4。加自指守卫。
    for p_id, p in _load_json(state_dir / "persons.json", {}).items():
        if p.get("name") == tid and p_id != tid:
            return trace_id(workspace, p_id)
    for i_id, it in _load_json(state_dir / "items.json", {}).items():
        if it.get("name") == tid and i_id != tid:
            return trace_id(workspace, i_id)
    for l_id, l in _load_json(state_dir / "lines.json", {}).items():
        if l.get("name") == tid and l_id != tid:
            return trace_id(workspace, l_id)
    for pl_id, pl in _load_json(state_dir / "places.json", {}).items():
        if pl.get("name") == tid and pl_id != tid:
            return trace_id(workspace, pl_id)
    for fc_id, fc in _load_json(state_dir / "factions.json", {}).items():
        if fc.get("name") == tid and fc_id != tid:
            return trace_id(workspace, fc_id)
    # v4.3 缺陷#B11：里程碑按标题逆查纳入兜底（旧版会让 trace "首杀立威" 找不到）
    for ms in _load_json(state_dir / "milestones.json", []):
        if tid in (ms.get("title"), ms.get("name")) and ms.get("id", tid) != tid:
            return trace_id(workspace, ms.get("id", tid))

    # 10.2 第二遍：模糊包含匹配 (要求搜索词长度 >= 2，防单字泛化误伤)
    # FIND-CT47（ID-6b·模糊命中误导致命）：旧版命中即返回子报告且不标注，
    # `trace p_0` 会返回某人物完整档案，误导使用者以为精确命中。显式标注。
    if len(tid) >= 2:
        for _tbl_file, _is_person in (("persons.json", True), ("items.json", False), ("lines.json", False)):
            for _rid, _r in _load_json(state_dir / _tbl_file, {}).items():
                if _rid == tid:
                    continue  # 自指守卫（防递归）
                if tid in _rid or tid in str(_r.get("name", "")):
                    _sub = trace_id(workspace, _rid)
                    if _sub.get("found"):
                        _sub["fuzzy_match"] = True
                        _sub["human_readable"] = (
                            f"⚠️ 模糊匹配结果（'{target_id}' 非精确 ID，以下为最相似实体，请核对）：\n"
                            + str(_sub.get("human_readable", ""))
                        )
                        return _sub

    report["human_readable"] = f"⚠️ 未检索到物理 ID: '{target_id}'。请检查 ID 前缀（如 p_001, it_001, GUN-001, loc_001, DEBT-001, LOCK-001）。"
    return report


def check_id_integrity(workspace: Path, chapter_id: Optional[str] = None) -> Dict[str, List[str]]:
    """深度校验工作区中实体 ID 的唯一性、规范性与细纲引用的因果完备性（防悬空、防笔误、防偷跑）。

    FIND-CT72（作者裁定 · 判据不要太死板 + 增强自愈）：ID 类问题的**定级重排**。
    旧版把「引用了没建档的人物/道具」「ID 写成 p_1 而不是 p_001」「new_entities 撞号」
    全部按 error 阻断——可这些都是引擎自己兜得住的账面问题（自动建档 / 自动规范 /
    自动改号），阻断只会让无人值守巡航动辄停摆、让作者为一条格式提醒停工改表。
    新契约：
      · **仍阻断（error）**：① 指定章节的细纲文件根本不存在（无从校验，不是"缺字段"）；
        ② 已故角色在后续章节登场（复活闸门，CT68 豁免标记除外）——这是叙事因果硬矛盾，
        必须由作者/Stage 4C 显式定夺，引擎不得自行揣测。
      · **降级提醒（warning + 🩹 自愈标注）**：格式非法、引用悬空、撞号、ID 与姓名不一致、
        伏笔未登记、槽位污染等——一律不阻断，并统一追加自愈提示：重跑
        `sync <章号> --force` 时 state.py 会自动规范/补建/改号，动作全部留痕在
        sync 报告的「🩹 自愈动作」清单里（公理二：系统自愈，但绝不偷偷改）。
    """
    errors: List[str] = []
    warnings: List[str] = []
    state_dir = workspace / "state"

    persons_db = _load_json(state_dir / "persons.json", {})
    items_db = _load_json(state_dir / "items.json", {})
    lines_db = _load_json(state_dir / "lines.json", {})
    places_db = _load_json(state_dir / "places.json", {})
    factions_db = _load_json(state_dir / "factions.json", {})
    debts_db = _load_json(state_dir / "debts.json", [])
    locked_db = _load_json(state_dir / "locked.json", [])

    # FIND-CT54b（L1 存量污染 + 体检假绿）：旧版 ID 校验只查**细纲引用侧**
    # （present_characters / new_entities 的格式与悬空），对**四表存量记录自身**的
    # ID 形态零校验。实证：金基座 workspace/test-lab/state/persons.json 里躺着一条
    # id = name = "{{slot:char_1_id|p_001}}" 的幽灵人物（由 character_status 自动打捞
    # 建档产生），`id list person` 把它当第 5 位人物陈列、随快照进入 history/ch_001.json
    # 与 ch_002.json，而 check 全程 0 errors / passed=true。存量污染必须能被体检看见。
    # 分级：槽位串身份 = warning + 🩹（确定的模板垃圾，无任何合法语义，sync 会自动清除；
    #       FIND-CT72 前为 error——但既然引擎自己能扫掉，就没必要拦住整条流水线）；
    #       非规范前缀 = warning（按姓名自动打捞建档属「宽容自愈」合法路径，仅需提示规范化）。
    _CANON_TABLES = (
        ("persons", persons_db, r"^p_\d+$", "人物", "p_001", "person"),
        ("items", items_db, r"^it_\d+$", "道具", "it_001", "item"),
        ("factions", factions_db, r"^fac_\d+$", "势力", "fac_001", "faction"),
        ("places", places_db, r"^loc_\d+$", "地点", "loc_001", "location"),
    )
    for _tname, _tdb, _trx, _tlabel, _teg, _tcat in _CANON_TABLES:
        if not isinstance(_tdb, dict):
            continue
        for _rid, _rec in _tdb.items():
            _rn = str(_rec.get("name", "") or "") if isinstance(_rec, dict) else ""
            if "{{slot:" in str(_rid) or "{{slot:" in _rn:
                warnings.append(
                    f"台账存量槽位污染: state/{_tname}.json 存在以未填模板槽位串为身份的{_tlabel}记录 "
                    f"[{_rid}]（姓名: {_rn or '同 ID'}）。该幽灵记录会混入 id list / ask / trace / "
                    f"cockpit 大盘与后续发号扫描，旧版体检对此全程 0 errors。\n"
                    f"      💡 方案：请从 state/{_tname}.json 删除该条记录（并同步清理 "
                    f"state/history/*.json 快照切片中的同名条目），随后运行 `python studio.py check` 复验；"
                    f"源头已由 pack/audit/finalize/proposal/sync 五处槽位闸门与 state 层消毒双重阻断。"
                )
            elif not re.match(_trx, str(_rid)):
                warnings.append(
                    f"台账 {_tlabel} ID 形态不规范: [{_rid}]（标准形态: {_teg}）。"
                    f"多为按姓名自动打捞建档所致，会使 `id next {_tcat}` 的防撞号扫描与 "
                    f"trace / ask 的检索口径失真。\n"
                    f"      💡 方案：建议改用标准编号 ID（可运行 `python studio.py id next {_tcat}` 取号），"
                    f"并在细纲中以该 ID 引用；若确为一次性路人可保留，但请勿在后续章节按 ID 追踪。"
                )

    # 扫描 characters/ 与 entities/ 实体卡，打捞已显式建档的合法 ID
    declared_card_ids = set()
    for doc_dir_name in ("characters", "entities", "bible"):
        dd = workspace / doc_dir_name
        if dd.exists():
            for mf in dd.glob("**/*.md"):
                txt = mf.read_text(encoding="utf-8-sig", errors="replace")
                m_ids = re.findall(r"\b(p_\d+|it_\d+|GUN-\d+|KNO-\d+|MIS-\d+|loc_\d+|fac_\d+)\b", txt)
                declared_card_ids.update(m_ids)
                declared_card_ids.add(mf.stem)

    # 校验细纲中的引用完整性
    from engine.parser import parse_frontmatter

    beats_files: List[Path] = []
    if chapter_id:
        # 单章检查
        b_file = workspace / "outlines" / "vol_01" / "beats" / f"{chapter_id}.md"
        if not b_file.exists():
            for f in workspace.glob(f"**/beats/{chapter_id}.md"):
                b_file = f
                break
        if b_file.exists():
            beats_files.append(b_file)
        else:
            # FIND-CT45（ID-9·单章校验假绿）：旧版找不到 beats 文件时静默返回
            # 0 errors——调用方若只用本函数（如第三方工具链）会把"文件不存在"
            # 读成"校验通过"。显式报错（check.py 侧另有独立兜底，双保险）。
            errors.append(
                f"未找到第 {chapter_id} 章细纲文件（outlines/**/beats/{chapter_id}.md），无法校验。"
                f"\n      💡 方案：请先运行 `python studio.py beats new {chapter_id} --write` 生成细纲；"
                f"若章节号笔误请核对后重试。"
            )
    else:
        # 全书扫描
        beats_files = list(workspace.glob("**/beats/*.md"))

    for bf in beats_files:
        txt = bf.read_text(encoding="utf-8-sig", errors="replace")
        fm, _ = parse_frontmatter(txt)
        if not fm:
            continue
        ch = fm.get("chapter_id", bf.stem)

        # FIND-CT32（ID-5 + FN-13）：章节号零校验——`chapter_id: CH_001`/`ch_1`
        # 可入账；Windows 大小写不敏感 FS 下 CH_001 命中真实 ch_001.md，但
        # audit/proposal 产物按 log/audit/CH_001.md 错位落盘，与 finalize/sync
        # 期望路径脱节，修补配方静默丢失（大小写变体与跨文档撞号同源）。
        if not re.match(r"^ch_\d{3,}$", str(ch)):
            warnings.append(
                f"第 {ch} 章章节号格式不规范: [{ch}]（标准形态: ch_001，三位以上数字）。\n"
                f"      💡 方案：请统一为 ch_XXX 形态；大小写/位数变体在 Windows 文件系统下"
                f"会造成审计产物错位与跨文档撞号。"
            )

        # 收集当章 new_entities 声明的 ID
        declared_new_ids = set()
        raw_new = fm.get("new_entities") or []
        new_ents = [raw_new] if isinstance(raw_new, dict) else (raw_new if isinstance(raw_new, list) else [])
        for ne in new_ents:
            if isinstance(ne, dict) and ne.get("id"):
                declared_new_ids.add(str(ne["id"]).strip())

        # FIND-CT32(2)：new_entities 的 loc_/fac_ 前缀格式校验（此前仅 p_/it_ 有正则把关）
        _PREFIX_FMT = {
            "p_": r"^p_\d+$", "it_": r"^it_\d+$",
            "loc_": r"^loc_\d+$", "fac_": r"^fac_\d+$",
        }
        for _ne in new_ents:
            if not isinstance(_ne, dict):
                continue
            _nid2 = str(_ne.get("id", "")).strip()
            if not _nid2 or "{{" in _nid2:
                continue
            for _pref, _rx in _PREFIX_FMT.items():
                if _nid2.startswith(_pref) and not re.match(_rx, _nid2):
                    warnings.append(
                        f"第 {ch} 章 new_entities 实体 ID 格式非法: [{_nid2}]（标准格式: {_pref}001）。\n"
                        f"      💡 方案：请将 ID 修正为标准编号格式（可运行 `python studio.py id next` 取号）。"
                    )

        # v4.3.3 BUG#40：new_entities 声明的 ID 若已被占用，state.py 的
        # `if eid not in xxx_db` 会静默跳过——实体既不入账也无任何提示，
        # 作者却以为已登记，后续章节引用时才发现不存在（且台账原记录不受影响，
        # 属"无声吞掉"而非覆盖）。此处在 check 阶段前置拦截。
        _EXIST_DB = {
            "person": (persons_db, "人物"), "character": (persons_db, "人物"),
            "item": (items_db, "道具"), "weapon": (items_db, "道具"), "tool": (items_db, "道具"),
            "place": (places_db, "地点"), "location": (places_db, "地点"),
            "faction": (factions_db, "势力"), "organization": (factions_db, "势力"),
        }
        for ne in new_ents:
            if not isinstance(ne, dict):
                continue
            _nid = str(ne.get("id", "")).strip()
            _nty = str(ne.get("type", "person")).strip().lower()
            _nnm = str(ne.get("name", "")).strip()
            if not _nid or "{{" in _nid or _nty not in _EXIST_DB:
                continue
            _db, _label = _EXIST_DB[_nty]
            if _nid in _db:
                _old = str(_db[_nid].get("name", "")).strip()
                if _nnm and _nnm != _old:
                    warnings.append(
                        f"第 {ch} 章 new_entities 的 {_label} ID 已被占用: [{_nid}] 台账中已登记为「{_old}」，"
                        f"细纲却声明为新实体「{_nnm}」。该声明会被静默丢弃，实体不会入账。\n"
                        f"      💡 方案：新实体请改用未占用的 ID（可运行 `python studio.py id next "
                        f"{'person' if _label == '人物' else 'item' if _label == '道具' else 'location' if _label == '地点' else 'faction'}` 取号）；"
                        f"若本就想引用既有实体，请从 new_entities 移除该条。"
                    )

        # 1. 人物在场校验 (present_characters)
        from engine.state import is_deceased
        raw_pres = fm.get("present_characters") or []
        pres_list = [raw_pres] if isinstance(raw_pres, (str, dict)) else (raw_pres if isinstance(raw_pres, list) else [])
        for p_item in pres_list:
            pid = ""
            pname = ""
            if isinstance(p_item, str):
                pid = p_item.strip()
            elif isinstance(p_item, dict):
                pid = str(p_item.get("id", "")).strip()
                pname = str(p_item.get("name", "")).strip()
            if not pid or "{{" in pid:
                continue
            # 若符合人物物理 ID 规范 (p_XXX)
            if pid.startswith("p_"):
                if not re.match(r"^p_\d+$", pid):
                    warnings.append(f"第 {ch} 章细纲人物 ID 格式非法: [{pid}]（标准格式: p_001）。\n      💡 方案：请将细纲 present_characters 中的人物 ID 改为标准编号格式。")
                elif pid not in persons_db and pid not in declared_new_ids and pid not in declared_card_ids:
                    warnings.append(f"第 {ch} 章细纲引用未定义的人物 ID: [{pid}]（未在 state/persons.json 登记，且未在当章 new_entities 或实体卡声明）。\n      💡 方案：可运行 `python studio.py id list person` 查看已有人物；若属新登场角色，请在细纲 new_entities 声明登记，或在 characters/ 建立人物卡。")

            # v4.3.3 BUG#37：id 与 name 必须指向同一人。
            # 旧版对 pid、pname 各自单独校验，从不比对二者是否自洽。
            # 一旦错配（如 id: p_003 配 name: 崔敬亭），sync 会以 name 为准回写
            # persons 表：被冒名者姓名遭覆盖、死亡/状态增量记到无关角色头上，
            # 且 check 全程 0 error 无感。此处做交叉核对。
            if pid in persons_db and pname:
                _reg = str(persons_db[pid].get("name", "")).strip()
                _reg_base = re.sub(r"[（\(].*?[）\)]", "", _reg).strip()
                _pn_base = re.sub(r"[（\(].*?[）\)]", "", pname).strip()
                if _reg and _pn_base != _reg_base:
                    _owner = next(
                        (f"（{pname} 实为 {_oid}）" for _oid, _op in persons_db.items()
                         if re.sub(r"[（\(].*?[）\)]", "", str(_op.get("name", ""))).strip() == _pn_base),
                        "",
                    )
                    warnings.append(
                        f"第 {ch} 章细纲人物 ID 与姓名不一致: [{pid}] 在台账中登记为「{_reg}」，"
                        f"细纲却写作「{pname}」{_owner}。\n"
                        f"      💡 方案：请修正 present_characters 中该条目的 id 或 name，使二者指向同一人"
                        f"（可运行 `python studio.py id list person` 核对）。"
                    )

            # 死者登场硬阻断 (Anti-Resurrection Guard · 时序因果校验)
            # 仅当当章章节号晚于角色阵亡章节时阻断（在阵亡当章登场属于合法事实）
            from engine.state import get_death_chapter

            def _ch_num(cid_str: str) -> int:
                m = re.search(r"(\d+)$", str(cid_str))
                return int(m.group(1)) if m else 0

            # 1) 按 ID 检查
            # v4.3.2 缺陷#10：ID 命中后必须短路，否则紧随其后的「按名检索」会对同一个
            # 死者再报一遍，体检输出出现两条一模一样的阻断错误（实测 ch_007 韩姨 ×2）。
            # FIND-CT68：与 state.apply_fine_outline_delta 的 sync 闸门同口径——
            # 显式声明回忆/闪回形态的已故角色降级为 warning，不再阻断全书体检。
            from engine.state import flashback_appearance as _fb_app
            _fb_mark = _fb_app(p_item if isinstance(p_item, dict) else {})
            _dead_reported = False
            if pid in persons_db and is_deceased(persons_db[pid]):
                d_ch = get_death_chapter(persons_db[pid])
                if _ch_num(ch) > _ch_num(d_ch):
                    dead_name = persons_db[pid].get("name") or pid
                    _dead_reported = True
                    if _fb_mark:
                        warnings.append(f"第 {ch} 章已故角色 [{dead_name}] ({pid}) 以「{_fb_mark}」形态登场，已豁免复活闸门（卒章 {d_ch}，台账生死不变）。")
                    else:
                        errors.append(f"第 {ch} 章细纲因果严重冲突：角色 [{dead_name}] ({pid}) 已于第 {d_ch} 章阵亡，禁止在后续章节登场！\n      💡 方案：① 回忆/闪回/梦境桥段请在该条目补 `appearance: \"回忆\"` 合法豁免；② 否则请从 present_characters 中移除该角色；③ 剧情反转请委派 Stage 4C (novel-evolution) 处理。")
            # 2) 按 Name 检查（防止用临时 ID 或中文名登场死者）
            probe_name = "" if _dead_reported else (pname or (pid if not pid.startswith("p_") else ""))
            if probe_name:
                for _d_id, _d_p in persons_db.items():
                    if is_deceased(_d_p):
                        d_ch = get_death_chapter(_d_p)
                        if _ch_num(ch) > _ch_num(d_ch):
                            _d_base = re.sub(r"[（\(].*?[）\)]", "", _d_p.get("name", "")).strip()
                            if probe_name == _d_p.get("name") or (probe_name == _d_base and len(probe_name) >= 2):
                                if _fb_mark:
                                    warnings.append(f"第 {ch} 章已故角色 [{probe_name}] ({_d_id}) 以「{_fb_mark}」形态登场，已豁免复活闸门（卒章 {d_ch}，台账生死不变）。")
                                else:
                                    errors.append(f"第 {ch} 章细纲因果严重冲突：角色 [{probe_name}] ({_d_id}) 已于第 {d_ch} 章阵亡，禁止在后续章节登场！\n      💡 方案：① 回忆/闪回/梦境桥段请在该条目补 `appearance: \"回忆\"` 合法豁免；② 否则请从 present_characters 中移除该角色；③ 剧情反转请委派 Stage 4C (novel-evolution) 处理。")
                                break

        # v4.3.3 BUG#47 · L3 兜底：细纲 character_status 的自由文本若疑似描述死亡，
        # 但既未写成法定枚举、推断也不确定，则主动索要显式契约——
        # 宁可让作者补一个字段，也不让引擎替作者猜生死。
        try:
            from engine.state import _infer_life_status, _LIFE_STATUS_NORM, _DEATH_KEYWORDS
            _sd_cs = (fm.get("state_deltas") or {}).get("character_status") or {}
            if isinstance(_sd_cs, dict):
                for _cid, _cv in _sd_cs.items():
                    _txt = ""
                    _explicit = ""
                    if isinstance(_cv, dict):
                        _explicit = str(_cv.get("life_status", "")).strip().lower()
                        _txt = str(_cv.get("condition") or _cv.get("status") or _cv.get("desc") or "")
                    else:
                        _txt = str(_cv or "")
                    if _explicit in _LIFE_STATUS_NORM:
                        continue  # 已有显式契约，无需干预
                    if _infer_life_status(_txt):
                        continue  # 推断明确，sync 会自动升格为契约
                    # 推断为空但文本含死亡字样 ⇒ 处于「疑似死亡 + 语境不明」的灰区
                    if any(_k in _txt for _k in _DEATH_KEYWORDS):
                        warnings.append(
                            f"第 {ch} 章角色 [{_cid}] 的状态「{_txt}」含死亡语义，但语境不明确"
                            f"（可能是假设、反事实或未遂），引擎不擅自判定生死。\n"
                            f"      💡 方案：若该角色确已死亡，请改写为字典形态显式声明："
                            f'{_cid}: {{life_status: "deceased", condition: "{_txt}"}}；'
                            f"若未死亡则可忽略本提醒。"
                        )
        except Exception:
            pass

        # 2. 人物状态增量校验 (state_deltas.character_status)
        raw_sd = fm.get("state_deltas") or {}
        if isinstance(raw_sd, dict):
            c_status = raw_sd.get("character_status") or {}
            if isinstance(c_status, dict):
                for cid in c_status.keys():
                    cid_str = str(cid).strip()
                    if cid_str.startswith("p_") and "{{" not in cid_str:
                        if not re.match(r"^p_\d+$", cid_str):
                            warnings.append(f"第 {ch} 章细纲状态变更人物 ID 格式非法: [{cid_str}]。\n      💡 方案：请修正 state_deltas.character_status 中的键名为标准格式（如 p_001）。")
                        elif cid_str not in persons_db and cid_str not in declared_new_ids and cid_str not in declared_card_ids:
                            warnings.append(f"第 {ch} 章细纲状态变更引用未定义的人物 ID: [{cid_str}]。\n      💡 方案：请确认人物已建档，或在当章 new_entities 声明。")

            # 3. 道具增量校验 (state_deltas.items)
            it_deltas = raw_sd.get("items") or []
            if isinstance(it_deltas, list):
                for it in it_deltas:
                    if not isinstance(it, dict):
                        continue
                    iid = str(it.get("id", "")).strip()
                    if not iid or "{{" in iid:
                        continue
                    if iid.startswith("it_"):
                        if not re.match(r"^it_\d+$", iid):
                            warnings.append(f"第 {ch} 章细纲道具 ID 格式非法: [{iid}]（标准格式: it_001）。\n      💡 方案：请将道具 ID 修正为标准格式。")
                        elif iid not in items_db and iid not in declared_new_ids and iid not in declared_card_ids:
                            warnings.append(f"第 {ch} 章细纲引用未定义的道具 ID: [{iid}]（未在 state/items.json 登记，且未在当章 new_entities 或实体卡声明）。\n      💡 方案：运行 `python studio.py id list item` 查看已有道具；若属新道具，请在细纲 new_entities 声明登记。")

        # 4. 伏笔闭环/推进引用校验 (foreshadowing_deltas)
        f_deltas = fm.get("foreshadowing_deltas") or []
        planted_in_chapter = set()
        if isinstance(f_deltas, list):
            for fd in f_deltas:
                if not isinstance(fd, dict):
                    continue
                fid = str(fd.get("id", "")).strip()
                faction = str(fd.get("action", "plant")).lower().strip()
                if not fid or "{{" in fid:
                    continue

                if faction == "plant":
                    planted_in_chapter.add(fid)
                elif faction in ("resolve", "progress", "reveal", "update"):
                    if fid not in lines_db and fid not in planted_in_chapter:
                        warnings.append(f"第 {ch} 章细纲试图推进/闭环未登记的伏笔 ID: [{fid}]（未在 state/lines.json 登记）。\n      💡 方案：运行 `python studio.py id list line` 查看已有伏笔；若是本章新埋设线索，请将 action 改为 'plant'。")
                    elif faction == "resolve" and fid in lines_db:
                        curr_line = lines_db[fid]
                        if curr_line.get("status") == "resolved" and curr_line.get("resolved_ch") != ch:
                            warnings.append(f"第 {ch} 章伏笔提示：伏笔 [{fid}] 此前已于第 {curr_line.get('resolved_ch')} 章闭环。")


    # FIND-CT72：凡是引擎自己能修的提醒项，统一挂一条 🩹 自愈指引，
    # 让作者/Librarian 一眼看出「这条不用手工改表，重跑 sync 就好」。
    _HEAL_SUBSTR = (
        "存量槽位污染",
        "new_entities 实体 ID 格式非法",
        "ID 已被占用",
        "细纲人物 ID 格式非法",
        "细纲引用未定义的人物 ID",
        "细纲人物 ID 与姓名不一致",
        "状态变更人物 ID 格式非法",
        "状态变更引用未定义的人物 ID",
        "细纲道具 ID 格式非法",
        "细纲引用未定义的道具 ID",
        "推进/闭环未登记的伏笔 ID",
    )
    warnings = [
        (w + "\n      🩹 自愈：本项无需手工改表——重跑 `python studio.py sync <章号> --force` "
             "时引擎会自动规范 ID / 补建档案 / 改派新号，并把每一步动作记入 sync 报告的"
             "「🩹 自愈动作」清单（改了什么、原值是什么都可追溯）。")
        if any(s in w for s in _HEAL_SUBSTR) else w
        for w in warnings
    ]

    return {
        "errors": errors,
        "warnings": warnings,
    }


class IdTracker:
    """ID 跟踪与分配器兼容类，供 state.py 与自动化建档打捞调用。"""

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace)

    def get_next_id(self, category: str, sub_type: str = "", exclude: Optional[Iterable[str]] = None) -> str:
        res = id_next(self.workspace, category, sub_type, exclude=exclude)
        return res.get("next_id", "")
