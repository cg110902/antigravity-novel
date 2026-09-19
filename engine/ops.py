"""Novel Studio 核心业务操作引擎 (Operations)。

提供全流水线底层能力支持：
- init, check, cockpit
- beats new, pack
- audit, finalize, proposal auto, sync
- milestone, calendar, ask, evidence, reconcile, snapshot, simulate
"""
from __future__ import annotations

import json
import re
import hashlib
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.config import load_config
from engine.errors import BusinessError, GuardError
from engine.ledger import StateLedger, _ensure_dir, _load_json, _save_json
from engine.parser import dump_mini_yaml, parse_frontmatter, parse_volume_outline


def _count_words(text: str) -> int:
    """统计汉字数与英文单词数（网文通用字数算法）。"""
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    english_words = len(re.findall(r"\b[a-zA-Z]+\b", text))
    numbers = len(re.findall(r"\b\d+\b", text))
    return chinese_chars + english_words + numbers


def _chapter_num(chapter_id: str) -> int:
    m = re.search(r"(\d+)$", chapter_id)
    return int(m.group(1)) if m else 0


_SLOT_RE = re.compile(r"\{\{slot:[^}]*\}\}")


def _find_unfilled_slots(text: str) -> List[str]:
    """扫描文本中残留的 {{slot:...}} 占位符，返回去重后的槽位名列表（保序）。"""
    return list(dict.fromkeys(m.group(0) for m in _SLOT_RE.finditer(text or "")))


def _clean_slot_value(value: Any, default: str) -> str:
    """卷纲/模板取值清洗：空值或仍含 {{slot:}} 占位符时回落默认值（v4.3 缺陷#C9）。

    杜绝卷纲未填槽位串沿 卷纲 ➔ beats ➔ sync ➔ synopsis ➔ 简报/导出书名 一路漂流污染。
    """
    v = str(value or "").strip()
    if not v or "{{" in v:
        return default
    return v


def _find_volume_outline(workspace: Path, chapter_id: str) -> Tuple[Optional[Path], str]:
    """寻找包含该章节的分卷大纲路径及所属卷号。"""
    cnum = _chapter_num(chapter_id)
    outlines_dir = workspace / "outlines"
    if outlines_dir.exists():
        pattern = rf"^###\s+(?:{re.escape(chapter_id)}|ch_0*{cnum})\b" if cnum > 0 else rf"^###\s+{re.escape(chapter_id)}\b"
        for vol_dir in sorted(outlines_dir.glob("vol_*")):
            if vol_dir.is_dir():
                v_outline = vol_dir / "outline.md"
                if v_outline.exists():
                    text = v_outline.read_text(encoding="utf-8-sig", errors="replace")
                    if re.search(pattern, text, re.MULTILINE):
                        return v_outline, vol_dir.name

        for f in sorted(outlines_dir.glob("*.md")):
            text = f.read_text(encoding="utf-8-sig", errors="replace")
            if re.search(pattern, text, re.MULTILINE):
                return f, "vol_01"

        if cnum > 0:
            for vol_dir in sorted(outlines_dir.glob("vol_*")):
                if vol_dir.is_dir():
                    v_outline = vol_dir / "outline.md"
                    if v_outline.exists():
                        text = v_outline.read_text(encoding="utf-8-sig", errors="replace")
                        nums = [int(m.group(1)) for m in re.finditer(r"^###\s+ch_(\d+)\b", text, re.M)]
                        if nums and min(nums) <= cnum <= max(nums):
                            return v_outline, vol_dir.name

    project_file = workspace / "project.json"
    pdata = _load_json(project_file, default={})
    curr_vol = pdata.get("current_status", {}).get("current_vol", "vol_01")
    expected = outlines_dir / curr_vol / "outline.md"
    if expected.exists():
        return expected, curr_vol

    return None, curr_vol


def init_workspace(workspace: Path, title: str, genre: str, protagonist: str,
                   force: bool = False) -> Dict[str, Any]:
    """初始化新书工作区。

    v4.2.1 缺陷#12：工作区已有工程档案时拒绝覆盖（旧版无条件重写 project.json，
    多打一次 init 会静默清掉既有 title/genre/engine 调参）；确认重置需 --force。
    v4.2.3 数据安全：--force 重置前，将被覆盖的五类档案自动备份为 *.bak
    （project.json 调参 / 分卷大纲 / 主角卡 / current 现场 / milestones 里程碑），
    误触 --force 可从 .bak 一键找回；bible/ 等只增不改的档案不在重置范围。
    """
    project_file = workspace / "project.json"
    if project_file.exists() and not force:
        existing = _load_json(project_file, default={})
        if existing:
            raise GuardError(
                f"工作区已存在工程档案: {project_file}（书名《{existing.get('title', '?')}》）。",
                solution="拒绝覆盖初始化以防调参丢失；若确认重置并备份既有档案，请追加 --force 参数。",
            )
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    if not templates_dir.exists():
        raise BusinessError(
            f"找不到模板目录: {templates_dir}",
            solution="请确认项目根目录下 templates/ 目录完整且未被删除。",
        )


    workspace.mkdir(parents=True, exist_ok=True)
    for sub in [
        "bible", "characters", "entities/items", "entities/factions", "entities/locations",
        "outlines/vol_01/beats", "manuscript/vol_01/raw", "manuscript/vol_01/final",
        "log/audit", "log/review", "state/inbox", "state/history", "state/indices", "snapshots",
    ]:
        (workspace / sub).mkdir(parents=True, exist_ok=True)

    # v4.2.3：--force 重置前备份将被覆盖的既有档案（对齐 beats --force 的 .bak 惯例）
    if force:
        for rel in ["project.json", "outlines/vol_01/outline.md",
                    "characters/protagonist.md", "state/current.json", "state/milestones.json"]:
            f = workspace / rel
            if f.exists():
                shutil.copy(f, f.with_name(f.name + ".bak"))

    today = datetime.now().strftime("%Y-%m-%d")

    # 1. 拷贝并实例化 project.json
    tpl_p = templates_dir / "project.json"
    if tpl_p.exists():
        p_text = tpl_p.read_text(encoding="utf-8-sig")
        p_text = p_text.replace("{{slot:title|书名}}", title)
        p_text = p_text.replace("{{slot:genre|题材}}", genre)
        p_text = p_text.replace("{{slot:protagonist|主角名}}", protagonist)
        p_text = p_text.replace("{{slot:created_at|YYYY-MM-DD}}", today)
        (workspace / "project.json").write_text(p_text, encoding="utf-8")

    # 2. 拷贝并实例化 bible/
    tpl_bible = templates_dir / "bible"
    if tpl_bible.exists():
        for bf in tpl_bible.glob("*.md"):
            dest = workspace / "bible" / bf.name
            if not dest.exists():
                b_text = bf.read_text(encoding="utf-8-sig")
                b_text = b_text.replace("{{slot:title|书名}}", title)
                b_text = b_text.replace("{{slot:protagonist|主角名}}", protagonist)
                dest.write_text(b_text, encoding="utf-8")

    # 3. 拷贝 characters/protagonist.md
    tpl_protag = templates_dir / "characters" / "protagonist.md"
    if tpl_protag.exists():
        pt_text = tpl_protag.read_text(encoding="utf-8-sig")
        pt_text = pt_text.replace("{{slot:protagonist_name|主角姓名}}", protagonist)
        pt_text = pt_text.replace("{{slot:protagonist|主角名}}", protagonist)
        (workspace / "characters" / "protagonist.md").write_text(pt_text, encoding="utf-8")

    # 3.1 拷贝 characters/antagonist.md（核心反派初始脚手架，已存在不覆盖）
    tpl_antag = templates_dir / "characters" / "antagonist.md"
    if tpl_antag.exists():
        dest_antag = workspace / "characters" / "antagonist.md"
        if not dest_antag.exists():
            at_text = tpl_antag.read_text(encoding="utf-8-sig")
            at_text = at_text.replace("{{slot:protagonist|主角名}}", protagonist)
            dest_antag.write_text(at_text, encoding="utf-8")

    # 3.5 拷贝全书主线大纲（只增不改：已存在不覆盖，防误删 Architect 手笔）   
    tpl_main = templates_dir / "outlines" / "main_plot.md"
    if tpl_main.exists():
        dest_main = workspace / "outlines" / "main_plot.md"
        if not dest_main.exists():
            m_text = tpl_main.read_text(encoding="utf-8-sig")
            m_text = m_text.replace("{{slot:title|书名}}", title)
            m_text = m_text.replace("{{slot:genre|题材（如：言情恋爱 / 都市职场 / 悬疑推理 / 科幻末世 / 玄幻仙侠 / 历史种田等）}}", genre)
            m_text = m_text.replace("{{slot:genre|题材}}", genre)
            m_text = m_text.replace("{{slot:protagonist|主角名（或男女主名、主角团）}}", protagonist)
            m_text = m_text.replace("{{slot:protagonist|主角名}}", protagonist)
            dest_main.write_text(m_text, encoding="utf-8")
            
    # 4. 拷贝分卷大纲
    tpl_vol = templates_dir / "outlines" / "volume_outline.md"
    if tpl_vol.exists():
        v_text = tpl_vol.read_text(encoding="utf-8-sig")
        v_text = v_text.replace("{{slot:vol_id|vol_01}}", "vol_01")
        # v4.2.2 全题材适配：卷名占位改为中性待定值（旧版硬编码仙侠卷名"龙渊潜底"）
        v_text = v_text.replace("{{slot:vol_title|第1卷：卷名}}", "第1卷：卷名待定")
        v_text = v_text.replace("{{slot:title|书名}}", title)
        (workspace / "outlines" / "vol_01" / "outline.md").write_text(v_text, encoding="utf-8")

    # 5. 初始化 state/
    ledger = StateLedger(workspace)
    curr_data = {
        "current_vol": "vol_01",
        "current_ch": "ch_001",
        "last_timeline": "",
        "last_location": "",
        "active_foreshadowings": [],
        "present_characters": [protagonist],
    }
    _save_json(ledger.current_file, curr_data)
    _save_json(workspace / "state" / "milestones.json", [])
    _save_json(ledger.items_file, {})
    _save_json(ledger.places_file, {})
    _save_json(ledger.factions_file, {})
    _save_json(ledger.lines_file, {})
    _save_json(ledger.locked_file, [])
    _save_json(ledger.debts_file, [])
    _save_json(ledger.relations_file, {})
    _save_json(ledger.ledger_file, {"pools": {}, "pools_baseline": {}, "transactions": []})
    _save_json(ledger.timeline_file, [])
    _save_json(ledger.synopsis_file, {})
    _save_json(ledger.co_occurrence_file, {})
    _save_json(ledger.entity_timeline_file, {})
    _save_json(workspace / "state" / "sync_log.json", {})

    # 初始化种子人物台账 (p_001 主角, p_002 核心反派)，与 characters/ 模板对齐
    persons_init = {
        "p_001": {
            "id": "p_001",
            "name": protagonist,
            "role": "protagonist",
            "type": "person",
            "tier_rank": 1,
            "tier_name": "初始实力阶层",
            "life_status": "alive",
            "condition": "完好",
            "status": "active",
            "attitude": "friendly",
            "established_ch": "ch_001",
            "last_seen_ch": "ch_001",
            "card": "characters/protagonist.md",
            "arc_history": [],
        },
        "p_002": {
            "id": "p_002",
            "name": "核心反派",
            "role": "antagonist",
            "type": "person",
            "tier_rank": 2,
            "tier_name": "反派阶层",
            "life_status": "alive",
            "condition": "完好",
            "status": "active",
            "attitude": "hostile",
            "established_ch": "ch_001",
            "last_seen_ch": "ch_001",
            "card": "characters/antagonist.md",
            "arc_history": [],
        },
    }
    _save_json(ledger.persons_file, persons_init)

    return {"title": title, "genre": genre, "protagonist": protagonist, "workspace": str(workspace)}


def get_beats_scaffold(workspace: Path, chapter_id: str, write_file: bool = True,
                       force: bool = False) -> Dict[str, Any]:
    """生成单章细纲任务卡脚手架 (beats new)。

    v4.1 SSOT 防覆盖守卫：目标细纲已存在且内容 ≠ 空白脚手架时拒绝写入
    （旧版会静默用空模板覆盖主控填好的细纲，实测造成 SSOT 数据销毁）。
    确认重置需显式 force=True（CLI 加 --force），旧文件自动备份为 *.bak。
    """
    ledger = StateLedger(workspace)
    curr_state = ledger.get_current()
    active_foreshadows = ledger.get_active_foreshadowings()

    vol_file, vol_id = _find_volume_outline(workspace, chapter_id)
    chapter_info: Dict[str, str] = {}

    if vol_file and vol_file.exists():
        vol_text = vol_file.read_text(encoding="utf-8-sig", errors="replace")
        parsed_info = parse_volume_outline(vol_text, chapter_id)
        if parsed_info:
            chapter_info = parsed_info

    tpl_file = workspace / "templates" / "beats.md"
    if not tpl_file.exists():
        tpl_file = Path(__file__).resolve().parent.parent / "templates" / "beats.md"

    if not tpl_file.exists():
        raise BusinessError(
            f"未找到细纲模板 templates/beats.md",
            solution="请检查项目 templates/beats.md 文件是否存在且未被删除。",
        )


    tpl_text = tpl_file.read_text(encoding="utf-8-sig", errors="replace")

    project_file = workspace / "project.json"
    pdata = _load_json(project_file, default={})
    protagonist = pdata.get("protagonist", "主角")

    # v4.3 缺陷#C9：卷纲取值先过槽位清洗，未填卷纲槽位串不得注入 beats 脚手架
    title = _clean_slot_value(chapter_info.get("title"), f"第{chapter_id}章")
    event = _clean_slot_value(chapter_info.get("event"), "核心事件推进与破局")
    cliff = _clean_slot_value(chapter_info.get("cliffhanger"), "章末悬念定格")

    scaffold = tpl_text
    scaffold = re.sub(r"\{\{slot:chapter_id\|[^}]*\}\}", chapter_id, scaffold)
    scaffold = re.sub(r"\{\{slot:volume_id\|[^}]*\}\}", vol_id, scaffold)
    scaffold = re.sub(r"\{\{slot:title\|[^}]*\}\}", title, scaffold)
    scaffold = re.sub(r"\{\{slot:char_1_name\|[^}]*\}\}", protagonist, scaffold)
    if event and event != "核心事件推进与破局":
        scaffold = re.sub(r"\{\{slot:dramatic_goal\|[^}]*\}\}", event, scaffold)
    if cliff and cliff != "章末悬念定格":
        scaffold = re.sub(r"\{\{slot:cliffhanger\|[^}]*\}\}", cliff, scaffold)

    curr_time = curr_state.get("last_timeline") or "待定（如 天元三年立秋晨）"
    curr_loc = curr_state.get("last_location") or "待定（如 宗门大殿/核心现场）"
    if curr_state.get("last_location"):
        scaffold = scaffold.replace("loc_001(核心场景名)", curr_state["last_location"])
        scaffold = scaffold.replace("核心场景名", curr_state["last_location"])
    if curr_state.get("last_timeline"):
        scaffold = scaffold.replace("小说历纪年·季节·几月初几晨/昼/暮/夜", curr_state["last_timeline"])
        scaffold = scaffold.replace("小说历纪年·时空时间", curr_state["last_timeline"])

    # --- 编剧机要参考简报 (Pre-computed Dossier) 自动打捞 ---
    # 1. 提取上一章尾声 / 梗概 (接戏余温)
    prev_tail = ""
    m_ch = re.search(r"(\d+)$", chapter_id)
    if m_ch:
        num = int(m_ch.group(1)) - 1
        if num > 0:
            prev_id = f"ch_{num:03d}"
            synopsis_db = ledger.get_synopsis()
            if prev_id in synopsis_db:
                s_rec = synopsis_db[prev_id]
                # v4.3 缺陷#C11：synopsis 真实键名是 dramatic_goal（state.py 写入），
                # 旧版误读从不存在的 "summary" 键，简报【上一章核心进展】区块永远缺席
                s_sum = s_rec.get("dramatic_goal") or s_rec.get("summary", "")
                s_cliff = s_rec.get("cliffhanger", "")
                parts = []
                if s_sum:
                    parts.append(f"【上一章核心进展】{s_sum}")
                if s_cliff:
                    parts.append(f"【上一章断章定格】{s_cliff}")
                if parts:
                    prev_tail = "\n   ".join(parts)
            if not prev_tail:
                cands = [
                    workspace / "manuscript" / vol_id / "final" / f"{prev_id}.md",
                    workspace / "manuscript" / vol_id / "raw" / f"{prev_id}_v3.md",
                    workspace / "manuscript" / vol_id / "raw" / f"{prev_id}.md",
                ]
                for c in cands:
                    if c.exists():
                        ptxt = c.read_text(encoding="utf-8-sig", errors="replace").strip()
                        prev_tail = "【上一章正文收尾】……" + (ptxt[-400:] if len(ptxt) > 400 else ptxt)
                        break
    if not prev_tail:
        prev_tail = "（全书开篇首章，开门见山直接切入核心冲突或初始情境）"

    # 2. 提取在场候选角色速查、离场心境与死亡黑名单
    from engine.state import is_deceased
    persons_db = ledger.get_persons()
    char_lines = []
    dead_lines = []
    mood_lines = []
    for pid, prec in sorted(persons_db.items()):
        pname = prec.get("name", pid)
        if is_deceased(prec):
            dead_lines.append(f"   - [{pid}] {pname}（⚠️ 已阵亡/死亡，严禁作为在场人登场！）")
            continue
        prole = prec.get("role", "配角")
        ptier = prec.get("tier_name", "") or f"Tier {prec.get('tier_rank', 1)}"
        patt = prec.get("attitude", "")
        pcond = prec.get("condition", "完好")
        line = f"   - [{pid}] {pname}（定位: {prole} ｜ 境界: {ptier} ｜ 状态: {pcond}"
        if patt:
            line += f" ｜ 对主角态度: {patt}"
        line += "）"
        char_lines.append(line)

        # 提取最新离场心境与生理状态 (status_out)
        arc_hist = prec.get("arc_history") or []
        last_s_out = ""
        if arc_hist:
            last_s_out = arc_hist[-1].get("status_out", "")
        if not last_s_out:
            last_s_out = pcond
        if last_s_out and last_s_out != "完好":
            mood_lines.append(f"   - [{pid}] {pname}：{last_s_out}")

    char_block = "\n".join(char_lines[:8]) if char_lines else "   - 暂无建档人物，按大纲规划出场"
    dead_block = "\n".join(dead_lines) if dead_lines else "   - 全书当前暂无阵亡角色"
    mood_block = "\n".join(mood_lines[:6]) if mood_lines else "   - 各候选角色当前状态平稳"

    # 2.5 提取主角随身物资与关键装备一览 (Protagonist Inventory & Assets)
    items_db = ledger.get_items()
    proto_item_lines = []
    for iid, irec in sorted(items_db.items()):
        if irec.get("status", "active") == "active":
            h = str(irec.get("holder", ""))
            if any(k in h for k in (protagonist, "主角", "p_001")):
                c_val = irec.get("charges", -1)
                c_str = f"储量/充能: {c_val}" if c_val >= 0 else "无上限/核心装备"
                dur = irec.get("durability", "完好")
                loc = irec.get("location", "随身")
                proto_item_lines.append(f"   - [{iid}] {irec.get('name')}（{c_str} ｜ 耐久: {dur} ｜ 携带: {loc}）")
    proto_item_block = "\n".join(proto_item_lines) if proto_item_lines else "   - 主角当前无特殊随身道具登记"

    # 2.6 提取当前空间场景规则与感官物象
    places_db = ledger.get_places()
    loc_sensory = ""
    loc_rules = ""
    loc_danger = "普通"
    for pid, prec in places_db.items():
        pname = str(prec.get("name", ""))
        if pname and (pname in curr_loc or curr_loc in pname):
            loc_sensory = prec.get("sensory_anchor", "")
            _tab = prec.get("environment_rules") or prec.get("rules_taboos") or ""
            loc_rules = "；".join(_tab) if isinstance(_tab, list) else str(_tab)
            loc_danger = prec.get("danger_level", "普通")
            break
    loc_detail_block = f"   - 空间发生地：{curr_loc}（危险等级: {loc_danger}）"
    if loc_sensory:
        loc_detail_block += f"\n   - 感官物象渲染：{loc_sensory}"
    if loc_rules:
        loc_detail_block += f"\n   - 环境规则/禁忌：{loc_rules}"

    # 3. 提取活跃伏笔雷达
    f_lines = []
    for f in active_foreshadows:
        fid = f.get("id", "")
        fname = f.get("name", "")
        fdesc = f.get("desc", "")
        ftarget = f.get("target_ch", "")
        due = "【⚠️ 本章到期建议推进/回收】" if ftarget == chapter_id else f"（目标章: {ftarget}）"
        f_lines.append(f"   - [{fid}] {fname} {due}：{fdesc}")
    f_block = "\n".join(f_lines) if f_lines else "   - 暂无活跃未决伏笔，剧情平稳推进"

    # 4. 提取未清算恩怨情仇账（双向展开）
    debts = ledger.get_debts()
    d_lines = []
    for d in debts:
        if d.get("status", "unpaid") == "unpaid":
            source = d.get("source_char") or "未知"
            target = d.get("target_char") or d.get("target", "未知")
            dtype = d.get("type", "grudge")
            desc = d.get("desc", "")
            d_lines.append(f"   - [{dtype}] `{source}` ➔ `{target}`：{desc}")
    debt_block = "\n".join(d_lines) if d_lines else "   - 暂无未清算因果血仇或重大誓言债务"

    # 4.5 下一可用物理 ID 速查（v4.3 缺陷#C14：编剧零命令/零 JSON，取号防 collision 唯一途径）
    id_cheat_block = ""
    try:
        from engine.id_tracker import IdTracker
        _tracker = IdTracker(workspace)
        _id_parts = []
        for _cat, _label in [("person", "人物"), ("item", "道具"), ("gun", "GUN"), ("kno", "KNO"),
                             ("mis", "MIS"), ("location", "地点"), ("faction", "势力"),
                             ("debt", "恩怨"), ("lock", "锁定事实")]:
            _id_parts.append(f"{_label}: {_tracker.get_next_id(_cat)}")
        id_cheat_block = "   - " + " ｜ ".join(_id_parts)
    except Exception:
        id_cheat_block = "   - （ID 速查生成失败，可运行 `python studio.py id next <类型>` 查询）"

    # 5. 编译 Markdown 编剧机要简报
    dossier_text = f"""<!-- ==============================================================================
🧭 【Engine 自动前置打捞 · 编剧机要参考简报 (Pre-computed Dossier)】
* 引擎已深入底层台账全量提取关键事实。编剧 Agent 仅需参考本简报即可通晓前情，严禁翻看底层 JSON！*
--------------------------------------------------------------------------------
📍 【本章任务宏观坐标】
   - 任务标识：分卷 {vol_id} / 章节 {chapter_id} 《{title}》
   - 卷纲预排看点：{event}
   - 卷纲预排断章：{cliff}

📍 【当前空间场景规则与感官物象】
{loc_detail_block}

🌊 【上一章收尾余温（接戏动量 · 严禁情节脱节）】
   {prev_tail}

🎒 【主角随身物资与关键装备一览 (Carried Inventory)】
{proto_item_block}

👥 【在场人物速查候选（无需翻看外部卡片）】
{char_block}

🎭 【候选角色前序离场心境与生理状态（接戏情绪台阶）】
{mood_block}

🚫 【已故/阵亡人物黑名单（严禁作为在场人登场！）】
{dead_block}

💣 【活跃伏笔雷达（暗线时钟）】
{f_block}

⚖️ 【未清算恩怨情仇账（暗流张力 · 双向关联）】
{debt_block}

🆔 【下一可用物理 ID 速查（新埋线索/新登场实体/新恩怨请从此取号，严禁自编撞号 ID）】
{id_cheat_block}
============================================================================== -->"""

    if "{{slot:engine_briefing_dossier}}" in scaffold:
        scaffold = scaffold.replace("{{slot:engine_briefing_dossier}}", dossier_text)
    elif "---" in scaffold:
        parts = scaffold.split("---", 2)
        if len(parts) >= 3:
            scaffold = f"---{parts[1]}---\n\n{dossier_text}\n\n{parts[2].lstrip()}"


    target_path = workspace / "outlines" / vol_id / "beats" / f"{chapter_id}.md"
    if write_file:
        if target_path.exists():
            existing = target_path.read_text(encoding="utf-8-sig", errors="replace")
            if existing.strip() != scaffold.strip():
                if not force:
                    raise GuardError(
                        f"细纲已存在且已含填写内容: {target_path}（SSOT 事实源防护，拒绝覆盖）。",
                        solution="确认重置并自动备份旧文件为 .bak 请追加 --force；仅想查看脚手架请去掉 --write 预览。",
                    )
                backup = target_path.with_name(target_path.name + ".bak")

                backup.write_text(existing, encoding="utf-8")
        _ensure_dir(target_path.parent)
        target_path.write_text(scaffold, encoding="utf-8")

    return {
        "chapter_id": chapter_id,
        "volume_id": vol_id,
        "title": title,
        "target_path": str(target_path),
        "written": bool(write_file),
        "forced": bool(force),
        "from_volume_outline": bool(chapter_info),
        "active_foreshadows_injected": len(active_foreshadows),
        "content": scaffold,
    }


def audit_chapter(workspace: Path, chapter_id: str, write_file: bool = True) -> Dict[str, Any]:
    """运行机械探针生成质检报告骨架 (audit)。"""
    _, vol_id = _find_volume_outline(workspace, chapter_id)
    prose_candidates = [
        workspace / "manuscript" / vol_id / "raw" / f"{chapter_id}_v3.md",
        workspace / "manuscript" / vol_id / "raw" / f"{chapter_id}_v2.md",
        workspace / "manuscript" / vol_id / "raw" / f"{chapter_id}_v1.md",
        workspace / "manuscript" / vol_id / "final" / f"{chapter_id}.md",
    ]
    raw_v3 = next((c for c in prose_candidates if c.exists()), None)
    if not raw_v3:
        raise BusinessError(
            f"未找到第 {chapter_id} 章的正文草稿 (raw_v1~v3) 或定稿，无法执行质检。",
            solution=f"请按流水线先派发 Stage 2 (novel-drafter) 起草正文 manuscript/{vol_id}/raw/{chapter_id}_v1.md。",
        )

    prose = raw_v3.read_text(encoding="utf-8-sig", errors="replace")
    words = _count_words(prose)


    cfg = load_config(workspace)
    wc_min, wc_max = cfg.get("words_per_chapter", [1500, 2600])

    # 提取细纲与设定台账供 7 大确定性物理探针体检
    beats_file = workspace / "outlines" / vol_id / "beats" / f"{chapter_id}.md"
    if not beats_file.exists():
        beats_file = workspace / "outlines" / f"{chapter_id}.md"
    fm: Dict[str, Any] = {}
    if beats_file.exists():
        fm, _ = parse_frontmatter(beats_file.read_text(encoding="utf-8-sig", errors="replace"))

    from engine.state import StateManager
    from engine.probes import run_all_probes
    state_mgr = StateManager(workspace)
    persons_db = state_mgr.get_persons() if (workspace / "state" / "persons.json").exists() else {}

    audit_file = workspace / "log" / "audit" / f"{chapter_id}.md"
    audit_txt = audit_file.read_text(encoding="utf-8-sig", errors="replace") if audit_file.exists() else ""
    probe_results = run_all_probes(prose, fm, persons_db=persons_db, config=cfg, audit_text=audit_txt)
    s = probe_results["summary"]

    recipe_blocks_text = """<!-- Auditor 单次全读 raw_v3.md 与任务卡后，在此将所有硬伤、事实出入及存疑备忘转化为修补配方：
Stage 5 finalize 将自动提取所有非占位配方并在正文中完成精准替换。
- **修补配方**：
  - TargetContent:
  ```text
  待修改原句
  ```
  - ReplacementContent:
  ```text
  通俗修改后原句
  ```
  - 理由: 说明（消除硬伤/事实矛盾/行文去AI味/化解存疑）
-->"""

    audit_md = f"""---
chapter_id: {chapter_id}
word_count: {words}
mechanical_probes:
  epistemology_valid: {str(s["epistemology"]["passed"]).lower()}
  all_passed: {str(probe_results["all_passed"]).lower()}
logic: 0
status: pending_auditor
---

# 第 {chapter_id} 章 内容质检报告

## 🤖 一、 机械探针自动化自检（物理事实与数据探针）
- **正文字数**：当前 {words} 字（参考指标，不做硬性阈值拦截）
- **认知盲区防透视**：{s['epistemology']['detail']}
- **法定称谓落地**：{s['address']['detail']}
- **道具与伏笔落地**：{s['grounding']['detail']}
- **生死与新实体探测**：{s.get('fatalities_and_entities', {}).get('detail', '正常')}

## 🧠 二、 语义逻辑、存疑备忘与修补配方（Auditor 专用）
{recipe_blocks_text}

## 🧬 三、 正文涌现事实与实体变更（Auditor 专用 · 驱动台账与细纲双向闭环）
<!-- Auditor 通读正文后，若正文自然涌现了细纲未登记的关键事实（如人物阵亡、新角色登场、道具获得），在此结构化登记：
Stage 5 proposal auto 将自动提取并反向回填至细纲与台账：
- [阵亡/死亡] 角色: 待填写角色名 ｜ 说明: 死亡原因/场景
- [新登场] 类型: person ｜ 名称: 待填写新角色名 ｜ 描述: 定位与特征
- [道具变动] 道具: 待填写道具名 ｜ 变动: 持有者流转或耐久变动
若全篇无未登记事实，保留本行注释即可。
-->
"""
    target_audit = workspace / "log" / "audit" / f"{chapter_id}.md"
    if write_file:
        _ensure_dir(target_audit.parent)
        target_audit.write_text(audit_md, encoding="utf-8")

    return {"chapter_id": chapter_id, "word_count": words, "target_audit": str(target_audit), "probe_results": probe_results}


def finalize_chapter(workspace: Path, chapter_id: str) -> Dict[str, Any]:
    """吸纳 Auditor 预制修补配方，完成正文替换定稿生成 final/ch_XXX.md。"""
    _, vol_id = _find_volume_outline(workspace, chapter_id)
    manuscript_dir = workspace / "manuscript" / vol_id
    # 严格挑选存在且字数大于 0 的有效稿件（v4.2.4 修复：跳过 0 字节半成品，防止产出空 final）
    candidates = [
        manuscript_dir / "raw" / f"{chapter_id}_v3.md",
        manuscript_dir / "raw" / f"{chapter_id}_v2.md",
        manuscript_dir / "raw" / f"{chapter_id}_v1.md",
        manuscript_dir / "final" / f"{chapter_id}.md",
    ]
    target_raw = None
    prose = ""
    for cand in candidates:
        if cand.exists():
            cand_text = cand.read_text(encoding="utf-8-sig", errors="replace")
            if _count_words(cand_text) > 0:
                target_raw = cand
                prose = cand_text
                break

    if not target_raw:
        if any(c.exists() for c in candidates):
            raise BusinessError(
                f"第 {chapter_id} 章所有正文草稿 (raw_v3/v2/v1) 内容均为空 (0 字)，拒绝定稿空章节！",
                solution=f"请派发 Stage 2 (novel-drafter) 起草正文 manuscript/{vol_id}/raw/{chapter_id}_v1.md。",
            )
        raise BusinessError(
            f"未找到第 {chapter_id} 章待定稿正文草稿 (raw_v3/v2/v1)",
            solution=f"请按流水线先派发 Stage 2 (novel-drafter) 起草正文 manuscript/{vol_id}/raw/{chapter_id}_v1.md。",
        )


    # 读取 audit 报告
    audit_file = workspace / "log" / "audit" / f"{chapter_id}.md"
    replacements_count = 0
    recipes_total = 0
    missed_targets: List[str] = []
    if audit_file.exists():
        audit_text = audit_file.read_text(encoding="utf-8-sig", errors="replace")
        # v4.2 修复：占位模板（Auditor 未填写时的示例值）不得被当作真配方
        _placeholder_targets = {"待修改原句"}
        _placeholder_replacements = {"通俗修改后原句"}
        seen_recipes = set()

        def _apply_recipe(tc: str, rc: str):
            nonlocal prose, replacements_count, recipes_total
            key = (tc, rc)
            if key in seen_recipes:
                return
            seen_recipes.add(key)
            if tc in _placeholder_targets or rc in _placeholder_replacements:
                return
            recipes_total += 1
            if tc and tc in prose:
                prose = prose.replace(tc, rc)
                replacements_count += 1
            elif tc:
                missed_targets.append(tc[:40])

        # 1. 提取多行三反引号格式配方（支持 0~多空格缩进、支持加粗、中文冒号、中英文别名）
        pattern_block = (
            r"(?:\*\*)?(?:TargetContent|原句|原文|待修改原句)(?:\*\*)?[:：]\s*"
            r"```(?:text|markdown|txt)?[ \t]*\r?\n(.*?)[ \t]*\r?\n\s*```[ \t]*\r?\n\s*-?\s*"
            r"(?:\*\*)?(?:ReplacementContent|修改后|通俗修改后原句|修改后原句|替换为)(?:\*\*)?[:：]\s*"
            r"```(?:text|markdown|txt)?[ \t]*\r?\n(.*?)[ \t]*\r?\n\s*```"
        )
        for m in re.finditer(pattern_block, audit_text, re.DOTALL | re.IGNORECASE):
            _apply_recipe(m.group(1).strip(), m.group(2).strip())

        # 2. 提取行内反引号与引号格式配方（支持行内、双行、加粗与中英文别名）
        pattern_inline = (
            r"(?:\*\*)?(?:TargetContent|原句|原文|待修改原句)(?:\*\*)?[:：]\s*[`“\"]([^`”\"\r\n]+)[`”\"]\s*"
            r"[|｜\n\s]+-?\s*"
            r"(?:\*\*)?(?:ReplacementContent|修改后|通俗修改后原句|修改后原句|替换为)(?:\*\*)?[:：]\s*[`“\"]([^`”\"\r\n]+)[`”\"]"
        )
        for m in re.finditer(pattern_inline, audit_text, re.IGNORECASE):
            _apply_recipe(m.group(1).strip(), m.group(2).strip())

    final_file = manuscript_dir / "final" / f"{chapter_id}.md"
    _ensure_dir(final_file.parent)
    final_file.write_text(prose, encoding="utf-8")

    return {
        "chapter_id": chapter_id,
        "final_file": str(final_file),
        "word_count": _count_words(prose),
        "replacements_applied": replacements_count,
        "recipes_total": recipes_total,
        "recipes_missed": len(missed_targets),
        "missed_targets": missed_targets,
        "note": ("审计报告不存在，直接采用 v3 原文定稿" if not audit_file.exists()
                 else (f"配方 {replacements_count}/{recipes_total} 应用" if recipes_total else "审计报告中无配方，按原文定稿")),
    }


def proposal_auto(workspace: Path, chapter_id: str) -> Dict[str, Any]:
    """生成本章状态变更提案 (proposal auto)，并自动吸收 Auditor 提纯的正文涌现事实与实体变更。"""
    _, vol_id = _find_volume_outline(workspace, chapter_id)
    beats_file = workspace / "outlines" / vol_id / "beats" / f"{chapter_id}.md"
    if not beats_file.exists():
        beats_file = workspace / "outlines" / f"{chapter_id}.md"

    proposal_data: Dict[str, Any] = {"chapter_id": chapter_id}
    frontmatter: Dict[str, Any] = {}
    body_text: str = ""
    cfg = load_config(workspace)
    protagonist = cfg.get("protagonist", "主角")
    if beats_file.exists():
        frontmatter, body_text = parse_frontmatter(beats_file.read_text(encoding="utf-8-sig", errors="replace"))
        proposal_data["frontmatter"] = frontmatter

    # 自动吸收 Auditor 质检报告中的正文涌现事实 (Emergent Facts Absorption)
    audit_file = workspace / "log" / "audit" / f"{chapter_id}.md"
    emergent_deaths: List[Dict[str, str]] = []
    emergent_entities: List[Dict[str, str]] = []
    emergent_items: List[Dict[str, str]] = []

    if audit_file.exists():
        audit_text = audit_file.read_text(encoding="utf-8-sig", errors="replace")

        # 弹性行解析器：无论 Auditor 使用何种标签、何种键名顺序、何种标点，均能精准捕获涌现事实
        for raw_line in audit_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("<!--") or line.startswith("-->") or line.startswith("#"):
                continue
            line = re.sub(r"^[-*+]\s*", "", line).strip()

            cat = None
            tag = ""
            tag_match = re.match(r"^\[(.*?)\]|^【(.*?)】", line)
            if tag_match:
                tag = (tag_match.group(1) or tag_match.group(2)).strip()
                rem = line[tag_match.end():].lstrip(" :：|｜")
                if any(k in tag for k in ("阵亡", "死亡", "牺牲")):
                    cat = "death"
                elif any(k in tag for k in ("新登场", "新实体", "新角色", "新人物")):
                    cat = "entity"
                elif any(k in tag for k in ("道具", "物品", "装备")):
                    cat = "item"
            else:
                rem = line
                if any(rem.startswith(k) for k in ("阵亡:", "阵亡：", "死亡:", "死亡：", "角色阵亡:", "角色阵亡：", "人物阵亡:", "人物阵亡：")):
                    cat = "death"
                    rem = re.sub(r"^(?:角色|人物)?(?:阵亡|死亡|牺牲)[:：]\s*", "", rem)
                elif any(rem.startswith(k) for k in ("新登场:", "新登场：", "新实体:", "新实体：", "新角色:", "新角色：", "新人物:", "新人物：")):
                    cat = "entity"
                    rem = re.sub(r"^新(?:登场|实体|角色|人物)[:：]\s*", "", rem)
                elif any(rem.startswith(k) for k in ("道具变动:", "道具变动：", "道具获得:", "道具获得：", "道具损毁:", "道具损毁：", "道具:", "道具：")):
                    cat = "item"
                    rem = re.sub(r"^道具(?:变动|获得|损毁)?[:：]\s*", "", rem)

            if not cat:
                continue

            chunks = [c.strip() for c in re.split(r"[|｜;；]", rem) if c.strip()]
            kv: Dict[str, str] = {}
            pos: List[str] = []
            for c in chunks:
                if ":" in c or "：" in c:
                    k_part, v_part = re.split(r"[:：]", c, maxsplit=1)
                    kv[k_part.strip().lower()] = v_part.strip()
                else:
                    pos.append(c)

            if cat == "death":
                cname = kv.get("角色") or kv.get("人物") or kv.get("姓名") or kv.get("名称") or kv.get("name") or (pos[0] if pos else "")
                desc = kv.get("说明") or kv.get("原因") or kv.get("场景") or kv.get("事实") or kv.get("描述") or (pos[1] if len(pos) > 1 else "正文确认阵亡")
                cname = cname.strip()
                if cname and cname not in ("待填写", "示例", "待填写角色名", "无"):
                    emergent_deaths.append({"name": cname, "desc": desc.strip()})

            elif cat == "entity":
                etype = kv.get("类型") or kv.get("类别") or kv.get("type") or kv.get("cat") or "person"
                ename = kv.get("名称") or kv.get("姓名") or kv.get("角色") or kv.get("实体") or kv.get("name") or (pos[0] if pos else "")
                edesc = kv.get("描述") or kv.get("说明") or kv.get("定位") or kv.get("特征") or (pos[1] if len(pos) > 1 else "")
                ename = ename.strip()
                if ename and ename not in ("待填写", "示例", "待填写新角色名", "无"):
                    emergent_entities.append({"type": etype.strip(), "name": ename, "summary": edesc.strip()})

            elif cat == "item":
                iname = kv.get("名称") or kv.get("道具") or kv.get("物品") or kv.get("装备") or kv.get("name") or (pos[0] if pos else "")
                istatus_or_holder = (
                    kv.get("持有人") or kv.get("持有者") or kv.get("支配人") or kv.get("归属")
                    or kv.get("获得者") or kv.get("状态") or kv.get("holder") or kv.get("status")
                )
                if not istatus_or_holder:
                    if "损毁" in tag:
                        istatus_or_holder = "destroyed"
                    elif "获得" in tag:
                        istatus_or_holder = protagonist
                    else:
                        istatus_or_holder = pos[1] if len(pos) > 1 else "active"
                idesc = kv.get("说明") or kv.get("描述") or (pos[2] if len(pos) > 2 else "")
                iname = iname.strip()
                if iname and iname not in ("待填写", "示例", "无"):
                    emergent_items.append({"name": iname, "holder_or_status": istatus_or_holder.strip(), "desc": idesc.strip()})

    # 将涌现事实合并至提案与细纲
    updated_beats = False
    if "frontmatter" in proposal_data and isinstance(proposal_data["frontmatter"], dict):
        fm = proposal_data["frontmatter"]
        sd = fm.setdefault("state_deltas", {})
        if not isinstance(sd, dict):
            sd = {}
            fm["state_deltas"] = sd
        c_status = sd.setdefault("character_status", {})
        if not isinstance(c_status, dict):
            c_status = {}
            sd["character_status"] = c_status

        from engine.id_tracker import IdTracker
        from engine.state import StateManager, _resolve_person_id, _resolve_item_id
        state_mgr = StateManager(workspace)
        tracker = IdTracker(workspace)
        persons_db = state_mgr.get_persons()

        for d in emergent_deaths:
            dname = d["name"]
            matched_pid = _resolve_person_id(dname, persons_db)
            if not matched_pid:
                for pc in fm.get("present_characters", []):
                    if isinstance(pc, dict) and pc.get("name") == dname:
                        matched_pid = pc.get("id")
                        break
                    elif isinstance(pc, str) and pc == dname:
                        matched_pid = pc
                        break

            target_key = matched_pid or dname
            if target_key not in c_status:
                c_status[target_key] = {
                    "life_status": "deceased",
                    "condition": f"正文阵亡·{d['desc']}",
                }
                updated_beats = True

        for ne in emergent_entities:
            raw_new = fm.setdefault("new_entities", [])
            if isinstance(raw_new, list):
                if not any(x.get("name") == ne["name"] for x in raw_new if isinstance(x, dict)):
                    etype = ne.get("type", "person").lower()
                    if etype in ("person", "character"):
                        cat = "person"
                    elif etype in ("item", "weapon", "tool"):
                        cat = "item"
                    elif etype in ("place", "location"):
                        cat = "location"
                    elif etype in ("faction", "org"):
                        cat = "faction"
                    else:
                        cat = "person"
                    # 分配标准合法 ID（杜绝中文名 ID）
                    assigned_id = ne.get("id")
                    if not assigned_id or not re.match(r"^[a-z]+_\d+$", str(assigned_id)):
                        assigned_id = tracker.get_next_id(cat)
                    raw_new.append({
                        "id": assigned_id,
                        "type": cat,
                        "name": ne["name"],
                        "summary": ne["summary"],
                    })
                    updated_beats = True

        for ei in emergent_items:
            items_db = state_mgr.get_items()
            raw_items_delta = sd.setdefault("items", [])
            if not isinstance(raw_items_delta, list):
                raw_items_delta = [raw_items_delta] if isinstance(raw_items_delta, dict) else []
                sd["items"] = raw_items_delta
            matched_iid = _resolve_item_id(ei["name"], items_db)
            if matched_iid:
                val = ei["holder_or_status"]
                delta_entry: Dict[str, Any] = {"id": matched_iid, "name": ei["name"]}
                if val in ("destroyed", "consumed", "lost", "active"):
                    delta_entry["status"] = val
                else:
                    delta_entry["holder_change"] = val
                if not any(x.get("id") == matched_iid or x.get("name") == ei["name"] for x in raw_items_delta if isinstance(x, dict)):
                    raw_items_delta.append(delta_entry)
                    updated_beats = True
            else:
                raw_new = fm.setdefault("new_entities", [])
                if isinstance(raw_new, list):
                    if not any(x.get("name") == ei["name"] for x in raw_new if isinstance(x, dict)):
                        new_iid = tracker.get_next_id("item")
                        val = ei["holder_or_status"]
                        default_holder = protagonist if val in ("destroyed", "consumed", "lost", "active") else val
                        raw_new.append({
                            "id": new_iid,
                            "type": "item",
                            "name": ei["name"],
                            "holder": default_holder,
                            "status": val if val in ("destroyed", "consumed", "lost", "active") else "active",
                            "summary": ei["desc"],
                        })
                        updated_beats = True

    # 真实物理回填 beats 细纲文件 (Physical Backfill)
    if updated_beats and beats_file.exists():
        new_beats_text = f"---\n{dump_mini_yaml(fm)}\n---\n{body_text}"
        beats_file.write_text(new_beats_text, encoding="utf-8")

    inbox_file = workspace / "state" / "inbox" / f"proposal_{chapter_id}.json"
    _ensure_dir(inbox_file.parent)
    _save_json(inbox_file, proposal_data)
    return {
        "chapter_id": chapter_id,
        "proposal_file": str(inbox_file),
        "emergent_deaths": len(emergent_deaths),
        "emergent_entities": len(emergent_entities),
        "beats_backfilled": updated_beats,
    }



def sync_chapter(workspace: Path, chapter_id: str, force: bool = False, refresh: bool = False) -> Dict[str, Any]:
    """解析细纲量化数据，封存正文并原子同步台账。

    v4.2 幂等守卫：同一章节、同一正文（sha1 指纹一致）重复 sync 直接幂等跳过；
    正文内容已变化的重复 sync 默认 GuardError 拒绝，需 --force 显式重入账。
    """
    _, vol_id = _find_volume_outline(workspace, chapter_id)
    beats_file = workspace / "outlines" / vol_id / "beats" / f"{chapter_id}.md"
    if not beats_file.exists():
        beats_file = workspace / "outlines" / f"{chapter_id}.md"

    if not beats_file.exists():
        raise BusinessError(
            f"未找到细纲文件: {beats_file}",
            solution=f"请先运行 `python studio.py beats new {chapter_id} --write` 装配当章细纲任务卡。",
        )

    content = beats_file.read_text(encoding="utf-8-sig", errors="replace")
    # v4.3 缺陷#A5 修复（SSOT 咽喉槽位闸门）：
    # 旧版 sync 对残留 {{slot:...}} 占位符照单全收——槽位字符串被当成实体 ID 写入
    # persons/lines/relations 核心台账，并沿 synopsis 漂流入简报与导出书名。此处硬闸：
    # 细纲任意位置残留槽位即拒绝入账，守护「细纲=唯一事实源」的数据纯度。
    _slot_hits = _find_unfilled_slots(content)
    if _slot_hits:
        raise GuardError(
            f"第 {chapter_id} 章细纲仍含 {len(_slot_hits)} 处未填占位符（如 {_slot_hits[0]}），已拒绝原子封存。",
            solution=f"请先派发 Stage 1 (novel-screenwriter) 将 {beats_file.name} 的全部 {{{{slot:}}}} 槽位填实（未使用的可选块整段删除或置 []）；确认需推翻重排可运行 `python studio.py beats new {chapter_id} --write --force` 重新装配。",
        )
    frontmatter, body_text = parse_frontmatter(content)
    if not frontmatter:
        raise BusinessError(
            f"第 {chapter_id} 章细纲未包含合法 YAML Front-matter 数据: {beats_file.name}",
            solution="请检查细纲顶部是否包含由 '---' 包裹的 YAML 元数据区块（含 chapter_id, present_characters 等）。",
        )

    # v4.1 一致性守卫：细纲内声明的 chapter_id 必须与命令参数一致，防止错章合账
    fm_ch = str(frontmatter.get("chapter_id", "")).strip()
    if fm_ch and fm_ch != chapter_id:
        raise BusinessError(
            f"细纲 front-matter 声明 chapter_id={fm_ch}，与命令参数 {chapter_id} 不一致，已拒绝合账。",
            solution=f"请修正 {beats_file.name} 顶部的 chapter_id 字段使其与 {chapter_id} 保持一致。",
        )

    final_file = workspace / "manuscript" / vol_id / "final" / f"{chapter_id}.md"
    word_count = 0
    if final_file.exists():
        word_count = _count_words(final_file.read_text(encoding="utf-8-sig", errors="replace"))

    # v4.2.4 修复（P1-1 死锁消除）：若 final 缺失或虽存在但为空稿 (0 字)，自动回退寻找非空 raw 草稿并补齐定稿
    if word_count <= 0:
        raw_candidates = [
            workspace / "manuscript" / vol_id / "raw" / f"{chapter_id}_v3.md",
            workspace / "manuscript" / vol_id / "raw" / f"{chapter_id}_v2.md",
            workspace / "manuscript" / vol_id / "raw" / f"{chapter_id}_v1.md",
        ]
        for rc in raw_candidates:
            if rc.exists():
                text = rc.read_text(encoding="utf-8-sig", errors="replace")
                cnt = _count_words(text)
                if cnt > 0:
                    _ensure_dir(final_file.parent)
                    final_file.write_text(text, encoding="utf-8")
                    word_count = cnt
                    print(f"⚠️ 提示：第 {chapter_id} 章原 final 稿件为空 (0 字)，已自动降级回退至有效草稿 {rc.name} ({cnt} 字) 补齐定稿。")
                    break

    # v4.1 空正文守卫：无有效 final/raw 时强制阻断
    if word_count <= 0:
        raise GuardError(
            f"第 {chapter_id} 章无任何有效正文（final 为空或缺失，且 raw 草稿均无内容），已拒绝原子封存。",
            solution=f"请先完成 Stage 2~4 起草正文并执行 `python studio.py finalize {chapter_id}` 完成定稿。",
        )
    cfg = load_config(workspace)
    wc_min = cfg.get("words_per_chapter", [1500, 2600])[0]
    sync_low_words = word_count < int(wc_min * 0.5)

    # v4.2 幂等守卫：以封存正文 sha1 为指纹，重复 sync 不二次入账
    final_text = final_file.read_text(encoding="utf-8-sig", errors="replace")
    final_sha1 = hashlib.sha1(final_text.encode("utf-8")).hexdigest()
    sync_log_file = workspace / "state" / "sync_log.json"
    sync_log = _load_json(sync_log_file, default={})
    prev = sync_log.get(chapter_id)
    if refresh and prev:
        # v4.2 --refresh：纯文笔修订（beats/deltas 未变），只更新指纹不重复入账
        prev["final_sha1"] = final_sha1
        prev["refreshed_at"] = datetime.now().isoformat(timespec="seconds")
        _save_json(sync_log_file, sync_log)
        return {
            "chapter_id": chapter_id,
            "title": frontmatter.get("title", ""),
            "word_count": word_count,
            "refreshed": True,
            "note": "已按修订版正文刷新同步指纹，台账增量未重复入账。",
        }
    if prev and prev.get("final_sha1") == final_sha1 and not force:
        # v4.2.1: --force 现允许同稿重放（数据层增量已按章幂等，重放不翻倍）
        return {
            "chapter_id": chapter_id,
            "title": frontmatter.get("title", ""),
            "word_count": word_count,
            "idempotent": True,
            "note": "本章已按相同正文同步过，幂等跳过，未重复入账。（如需重放细纲增量请加 --force）",
        }
    if prev and prev.get("final_sha1") != final_sha1 and not force:
        raise GuardError(
            f"第 {chapter_id} 章曾以不同版本正文同步过（旧指纹 {str(prev.get('final_sha1'))[:8]}…）。",
            solution=f"如确需按新版本正文重入账，请先使用 `snapshot create` 备份后运行 `python studio.py sync {chapter_id} --force`；若仅是文笔润色未改动细纲事实，请运行 `python studio.py sync {chapter_id} --refresh`。",
        )
    # 提案待办双源对账：若存在 proposal_{chapter_id}.json，融合未入账的涌现事实
    inbox_file = workspace / "state" / "inbox" / f"proposal_{chapter_id}.json"
    if inbox_file.exists():
        p_inbox = _load_json(inbox_file, default={})
        p_fm = p_inbox.get("frontmatter") or {}
        if isinstance(p_fm, dict):
            # 融合新实体
            p_new = p_fm.get("new_entities") or []
            fm_new = frontmatter.setdefault("new_entities", [])
            for ne in p_new:
                if isinstance(ne, dict) and not any(x.get("id") == ne.get("id") for x in fm_new if isinstance(x, dict)):
                    fm_new.append(ne)
            # 融合角色状态
            p_c_status = p_fm.get("state_deltas", {}).get("character_status") or {}
            fm_sd = frontmatter.setdefault("state_deltas", {})
            fm_c_status = fm_sd.setdefault("character_status", {})
            for cid, sval in p_c_status.items():
                if cid not in fm_c_status:
                    fm_c_status[cid] = sval
            # 融合道具变动
            p_items = p_fm.get("state_deltas", {}).get("items") or []
            fm_items = fm_sd.setdefault("items", [])
            for it in p_items:
                if isinstance(it, dict) and not any(x.get("id") == it.get("id") for x in fm_items if isinstance(x, dict)):
                    fm_items.append(it)

    ledger = StateLedger(workspace)
    sync_report = ledger.apply_chapter_delta(frontmatter, word_count=word_count, beats_body=body_text)
    sync_log[chapter_id] = {
        "final_sha1": final_sha1,
        "synced_at": datetime.now().isoformat(timespec="seconds"),
        "forced": bool(force),
        # v4.3 R2：封存条目补齐展示元数据（旧版只有指纹/时间戳，
        # trace ch_XXX 与各类封存清单拿不到章节名与入账字数）
        "title": str(frontmatter.get("title", "") or ""),
        "word_count": word_count,
    }
    _save_json(sync_log_file, sync_log)

    # 累加 project.json
    project_file = workspace / "project.json"
    pdata = _load_json(project_file, default={})
    if "current_status" not in pdata:
        pdata["current_status"] = {}
    pdata["current_status"]["current_vol"] = vol_id
    pdata["current_status"]["current_ch"] = chapter_id
    total_words = sum(t.get("word_count", 0) for t in ledger.get_timeline())
    pdata["current_status"]["total_published_words"] = total_words
    _save_json(project_file, pdata)

    sync_report["total_published_words"] = total_words
    sync_report["final_prose_path"] = str(final_file) if final_file.exists() else None
    if sync_low_words:
        sync_report.setdefault("warnings", []).append(
            f"本章正文仅 {word_count} 字，低于标准下限（{wc_min} 字）的一半，请确认是否为有意短章。"
        )
    return sync_report


def get_cockpit(workspace: Path) -> Dict[str, Any]:
    """主控态势大盘感知（结构化 dict 版对外 API）。

    注：CLI `cockpit`/`status` 的人读渲染走 engine/cockpit.py render_cockpit（v4.3 R2
    已补充资金池遥测与航标槽位清洗）；本函数保留作为程序化消费的结构化入口。
    """
    ledger = StateLedger(workspace)
    curr = ledger.get_current()
    active_f = ledger.get_active_foreshadowings()
    timeline = ledger.get_timeline()
    project_file = workspace / "project.json"
    pdata = _load_json(project_file, default={})

    return {
        "title": pdata.get("title", "未命名"),
        "genre": pdata.get("genre", "未设定"),
        "protagonist": pdata.get("protagonist", "主角"),
        "current_vol": curr.get("current_vol", "vol_01"),
        "current_ch": curr.get("current_ch", "ch_001"),
        "total_words": sum(t.get("word_count", 0) for t in timeline),
        "total_chapters": len(timeline),
        "last_timeline": curr.get("last_timeline", "未记录"),
        "last_location": curr.get("last_location", "未记录"),
        "active_foreshadowings": [f"{f.get('id')}: {f.get('name')} ({f.get('planted_ch')})" for f in active_f],
    }


def get_calendar(workspace: Path, count: int = 3) -> List[Dict[str, Any]]:
    """未来 N 章排产与伏笔到期日历。"""
    ledger = StateLedger(workspace)
    curr = ledger.get_current()
    ch_id = curr.get("current_ch", "ch_001")
    vol_id = curr.get("current_vol", "vol_01")
    vol_file = workspace / "outlines" / vol_id / "outline.md"

    calendar_list: List[Dict[str, Any]] = []
    if not vol_file.exists():
        return calendar_list

    vol_text = vol_file.read_text(encoding="utf-8-sig", errors="replace")
    m = re.search(r"(\d+)$", ch_id)
    curr_num = int(m.group(1)) if m else 1

    for offset in range(1, count + 1):
        target_ch = f"ch_{curr_num + offset:03d}"
        info = parse_volume_outline(vol_text, target_ch)
        if info:
            calendar_list.append(info)
        else:
            calendar_list.append({"chapter_id": target_ch, "title": f"第{target_ch}章", "event": "待大纲细化"})

    return calendar_list


def ask_fact(workspace: Path, query: str) -> List[str]:
    """事实快速检索 (ask)。"""
    if not str(query).strip():
        return []  # v4.2.1: 空查询会子串命中一切，直接拒答防洪泛
    results: List[str] = []
    ledger = StateLedger(workspace)

    # 查法定锁定事实 (P0)
    for lf in ledger.get_locked_facts():
        if query in lf.get("fact", "") or query in lf.get("id", ""):
            results.append(f"[锁定事实] ({lf.get('id')}) {lf.get('fact')} (第{lf.get('established_ch', '初始')}章确立)")

    # 查角色
    for cid, c in ledger.get_characters().items():
        if query in c.get("name", "") or query in c.get("want", "") or query in cid:
            results.append(f"[角色] {c.get('name')} ({cid}) - 境界: {c.get('tier_name', '凡阶')}, 状态: {c.get('condition', '正常')}, 诉求: {c.get('want', '无')}")

    # 查道具
    for iid, it in ledger.get_items().items():
        if query in it.get("name", "") or query in it.get("holder", "") or query in iid:
            results.append(f"[道具] {it.get('name')} ({iid}) - 持有人: {it.get('holder')}, 可用次数: {it.get('charges')}")

    # v4.3 缺陷#C5：补全势力与地点档案检索（此前 ask 对这两类实体完全失明）
    for fid, f in ledger.get_factions().items():
        if query in f.get("name", "") or query in f.get("leader", "") or query in fid:
            results.append(f"[势力] {f.get('name')} ({fid}) - 领袖: {f.get('leader', '未知')}, 总部: {f.get('headquarters', '未知')}")
    for pid, p in ledger.get_places().items():
        if query in p.get("name", "") or query in p.get("summary", "") or query in pid:
            results.append(f"[地点] {p.get('name')} ({pid}) - 危险等级: {p.get('danger_level', '未知')}")

    # 查伏笔
    for fid, f in ledger.get_foreshadowings().items():
        if query in f.get("name", "") or query in f.get("desc", "") or query in fid:
            results.append(f"[伏笔] {f.get('name')} ({fid}) - 状态: {f.get('status')}, 埋于: {f.get('planted_ch')}")

    # 查章节梗概
    synopsis_db = ledger.get_synopsis()
    for ch, syn in synopsis_db.items():
        title = syn.get("title", "")
        goal = syn.get("dramatic_goal", "")
        cliff = syn.get("cliffhanger", "")
        if query in title or query in goal or query in cliff or query in ch:
            results.append(f"[章节梗概] {ch} 《{title}》: {goal or cliff}")

    # 查设定文件
    for bf in (workspace / "bible").glob("*.md"):
        txt = bf.read_text(encoding="utf-8-sig", errors="replace")
        if query in txt:
            results.append(f"[设定文档] 见 bible/{bf.name}")

    # v4.3 缺陷#C5：检索已封存正文证据切片（Librarian/Evolution 正文溯源依赖）。
    # 只扫 final 定稿（SSOT —— raw 草稿非封存事实）；每条证据截短，控制 stdout 体量。
    ms_root = workspace / "manuscript"
    if ms_root.exists():
        ev_hits = 0
        for final_md in sorted(ms_root.glob("*/final/ch_*.md")):
            try:
                ptxt = final_md.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            idx = ptxt.find(query)
            if idx >= 0:
                snippet = ptxt[max(0, idx - 20): idx + len(query) + 30].replace("\n", " ").strip()
                results.append(f"[正文证据] {final_md.parent.parent.name}/{final_md.stem}: …{snippet}…")
                ev_hits += 1
                if ev_hits >= 3:
                    break

    return results[:12]


def evidence_candidates(workspace: Path, chapter_id: str) -> Dict[str, Any]:
    """打捞当章细纲（SSOT）中已声明但尚未在台账建档的实体候选。

    v4.3 说明：本命令仅扫描细纲 frontmatter 声明（new_entities / present_characters /
    state_deltas.items），不做正文实体识别（确定性引擎不做 NLP 猜测）；正文检索请用
    `python studio.py ask "<名字>"`（可命中 final 定稿证据切片）。
    """
    _, vol_id = _find_volume_outline(workspace, chapter_id)
    cands_files = [
        workspace / "manuscript" / vol_id / "final" / f"{chapter_id}.md",
        workspace / "manuscript" / vol_id / "raw" / f"{chapter_id}_v3.md",
        workspace / "manuscript" / vol_id / "raw" / f"{chapter_id}_v2.md",
        workspace / "manuscript" / vol_id / "raw" / f"{chapter_id}_v1.md",
    ]
    prose = ""
    target_f = None
    for cf in cands_files:
        if cf.exists():
            prose = cf.read_text(encoding="utf-8-sig", errors="replace")
            target_f = cf
            break

    if not target_f:
        return {"chapter_id": chapter_id, "found": False, "candidates": [], "message": f"未找到第 {chapter_id} 章正文草稿"}

    ledger = StateLedger(workspace)
    known_names = set()
    for p in ledger.get_persons().values():
        if p.get("name"):
            known_names.add(p["name"])
    for it in ledger.get_items().values():
        if it.get("name"):
            known_names.add(it["name"])
    for f in ledger.get_factions().values():
        if f.get("name"):
            known_names.add(f["name"])
    for pl in ledger.get_places().values():
        if pl.get("name"):
            known_names.add(pl["name"])

    candidates = []
    seen = set()

    # 1. 从细纲（唯一事实源 SSOT）中打捞未建档实体（新登场人物/在场角色/道具）
    beats_file = workspace / "outlines" / vol_id / "beats" / f"{chapter_id}.md"
    if not beats_file.exists():
        beats_file = workspace / "outlines" / f"{chapter_id}.md"
    if beats_file.exists():
        try:
            b_fm, _ = parse_frontmatter(beats_file.read_text(encoding="utf-8-sig", errors="replace"))
            # v4.3：单 dict 形态统一包裹为列表（与 state.py 归一化口径一致）
            raw_ne = b_fm.get("new_entities") or []
            new_ents = [raw_ne] if isinstance(raw_ne, dict) else (raw_ne if isinstance(raw_ne, list) else [])
            for ne in new_ents:
                if isinstance(ne, dict):
                    ename = str(ne.get("name", "")).strip()
                    etype = str(ne.get("type", "person")).strip()
                    if ename and ename not in known_names and ename not in seen:
                        seen.add(ename)
                        candidates.append({"name": ename, "type": etype, "suggested_role": ne.get("role", "supporting")})
            raw_pc = b_fm.get("present_characters") or []
            pres_list = [raw_pc] if isinstance(raw_pc, (str, dict)) else (raw_pc if isinstance(raw_pc, list) else [])
            persons_db = ledger.get_persons()
            for c in pres_list:
                if isinstance(c, str):
                    # 字符串紧凑形态：按 ID 检查台账是否已建档
                    cid = c.strip()
                    cname = str(persons_db.get(cid, {}).get("name", "") or "")
                    if cid and cid not in persons_db and (not cname or cname not in known_names) and cid not in seen:
                        seen.add(cid)
                        candidates.append({"name": cname or cid, "type": "person", "suggested_role": "supporting"})
                elif isinstance(c, dict):
                    cname = str(c.get("name", "")).strip()
                    if cname and cname not in known_names and cname not in seen:
                        seen.add(cname)
                        candidates.append({"name": cname, "type": "person", "suggested_role": c.get("role", "supporting")})
            raw_it = (b_fm.get("state_deltas") or {}).get("items") or []
            it_list = [raw_it] if isinstance(raw_it, dict) else (raw_it if isinstance(raw_it, list) else [])
            for it in it_list:
                if isinstance(it, dict):
                    iname = str(it.get("name", "")).strip()
                    if iname and iname not in known_names and iname not in seen:
                        seen.add(iname)
                        candidates.append({"name": iname, "type": "item", "suggested_role": "item"})
        except Exception:
            pass

    return {
        "chapter_id": chapter_id,
        "source_file": str(target_f),
        "candidates": candidates,
        "known_entities_count": len(known_names),
        "message": f"打捞完毕：发现 {len(candidates)} 个潜在未登记实体" if candidates else "未发现未登记关键次要实体，台账完备",
    }


def reconcile_volume(workspace: Path, volume_id: str, write_file: bool = False) -> Dict[str, Any]:
    """卷末对账：深度核对全卷字数、伏笔收束率、道具充能状态与经济平账。"""
    ledger = StateLedger(workspace)
    timeline = ledger.get_timeline()
    vol_timeline = [t for t in timeline if t.get("volume_id") == volume_id]
    vol_words = sum(t.get("word_count", 0) for t in vol_timeline)

    # 伏笔对账（v4.2.4 修复：准确限定为当前卷闭环的伏笔，名副其实）
    lines = ledger.get_lines()
    vol_ch_set = {t.get("chapter_id") for t in vol_timeline if t.get("chapter_id")}
    active_in_vol = [l for l in lines.values() if l.get("status") == "active"]
    resolved_in_vol = [l for l in lines.values() if l.get("status") == "resolved" and l.get("resolved_ch") in vol_ch_set]

    def _num(cid: str) -> int:
        m = re.search(r"(\d+)$", str(cid))
        return int(m.group(1)) if m else 0

    latest_ch_num = max((_num(t.get("chapter_id", "")) for t in timeline), default=0)
    overdue_lines = [
        l for l in active_in_vol
        if l.get("target_ch") and _num(l.get("target_ch", "")) < latest_ch_num
    ]

    # 道具对账
    items = ledger.get_items()
    depleted_items = [it for it in items.values() if it.get("charges") == 0]

    # 经济池对账
    ledger_data = ledger.get_ledger()
    pools = ledger_data.get("pools", {})
    tx_count = len(ledger_data.get("transactions", []))

    # 锁定事实
    locked_facts = ledger.get_locked_facts()

    report_lines = [
        f"# {volume_id} 卷末综合对账与长程一致性审计报告",
        f"- **生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **全卷章节数**：{len(vol_timeline)} 章",
        f"- **全卷正文字数**：{vol_words} 字",
        "",
        "## 💣 一、 伏笔收束与暗线生命周期",
        f"- **已闭环回收伏笔 ({len(resolved_in_vol)} 条)**：",
    ]
    for r in resolved_in_vol:
        report_lines.append(f"  - [{r.get('id')}] {r.get('name')} (埋于: {r.get('planted_ch')} ➔ 回收于: {r.get('resolved_ch')})")
    if not resolved_in_vol:
        report_lines.append("  - (本卷暂无已回收伏笔)")

    report_lines.append(f"\n- **仍活跃待跨卷回收伏笔 ({len(active_in_vol)} 条)**：")
    for a in active_in_vol:
        report_lines.append(f"  - [{a.get('id')}] {a.get('name')} (埋于: {a.get('planted_ch')} ｜ 描述: {a.get('desc')})")
    if not active_in_vol:
        report_lines.append("  - (全部伏笔已收束平账)")

    if overdue_lines:
        report_lines.append(f"\n- **⛔ 已逾期未回收 ({len(overdue_lines)} 条 · 本卷必清清单)**：")
        for o in overdue_lines:
            report_lines.append(
                f"  - [{o.get('id')}] {o.get('name')} (预定收于 {o.get('target_ch')}，已逾期至 ch_{latest_ch_num:03d})"
            )

    report_lines.append("\n## ⚔️ 二、 核心道具与充能池监控")
    if depleted_items:
        for di in depleted_items:
            report_lines.append(f"- ⚠️ 耗尽道具: [{di.get('id')}] {di.get('name')} (持有者: {di.get('holder')}, charges: 0)")
    else:
        report_lines.append("- ✅ 所有在案法宝/道具充能运转合规，无透支违规。")

    report_lines.append("\n## 💰 三、 经济流水与资源大盘")
    for p_name, p_bal in pools.items():
        report_lines.append(f"- **{p_name} 资金池结余**：{p_bal} (全书累计发生 {tx_count} 笔收支)")

    report_lines.append(f"\n## 🔒 四、 法定不可逆既定事实 ({len(locked_facts)} 项)")
    for lf in locked_facts:
        report_lines.append(f"- [{lf.get('id')}] {lf.get('fact')} (第{lf.get('established_ch', '初始')}章确立)")

    report_md = "\n".join(report_lines) + "\n"

    target_path = None
    if write_file:
        rev_dir = _ensure_dir(workspace / "log" / "review")
        target_path = rev_dir / f"reconcile_{volume_id}.md"
        target_path.write_text(report_md, encoding="utf-8")

    return {
        "volume_id": volume_id,
        "chapters_count": len(vol_timeline),
        "total_words": vol_words,
        "active_lines": len(active_in_vol),
        "resolved_lines": len(resolved_in_vol),
        "overdue_lines": [l.get("id") for l in overdue_lines],
        "report_file": str(target_path) if target_path else None,
        "content": report_md,
    }


def rollup_volume(workspace: Path, volume_id: str) -> Dict[str, Any]:
    """分卷归档 (state rollup)：把时间线按卷折叠为 rollup JSON，供长篇防膨胀与跨卷总览。"""
    ledger = StateLedger(workspace)
    timeline = ledger.get_timeline()
    vol_entries = sorted(
        (t for t in timeline if t.get("volume_id") == volume_id),
        key=lambda t: int(re.search(r"(\d+)$", t.get("chapter_id", "0")).group(1)) if re.search(r"(\d+)$", t.get("chapter_id", "0")) else 0,
    )
    if not vol_entries:
        raise BusinessError(
            f"时间线中不存在分卷 {volume_id} 的任何章节记录，无可归档数据。",
            solution=f"请确认已通过 `python studio.py sync <ch_XXX>` 封存该卷章节，或检查分卷编号是否正确。",
        )

    def _num(cid: str) -> int:
        m = re.search(r"(\d+)$", str(cid))
        return int(m.group(1)) if m else 0

    lines = ledger.get_lines()
    # v4.2.1 缺陷#13：旧判据 `volume_id in resolved_ch` 永假（resolved_ch 是 ch_XXX），
    # resolved 快照恒为空。改为按本卷章节号区间判定。
    vol_nums = [_num(t.get("chapter_id", "")) for t in vol_entries]
    vol_min, vol_max = (min(vol_nums), max(vol_nums)) if vol_nums else (0, 0)
    archive = {
        "volume_id": volume_id,
        "archived_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "chapters_count": len(vol_entries),
        "total_words": sum(t.get("word_count", 0) for t in vol_entries),
        "chapters": [
            {k: t.get(k) for k in ("chapter_id", "title", "chapter_type", "word_count", "dramatic_goal", "cliffhanger")}
            for t in vol_entries
        ],
        "lines_snapshot": {
            "active": sorted(l.get("id") for l in lines.values() if l.get("status") == "active"),
            "resolved_in_volume": sorted(
                l.get("id") for l in lines.values()
                if l.get("status") == "resolved"
                and vol_min <= _num(l.get("resolved_ch", "")) <= vol_max
                and _num(l.get("resolved_ch", "")) > 0
            ),
        },
    }
    out = workspace / "state" / f"rollup_{volume_id}.json"
    _save_json(out, archive)
    return {
        "volume_id": volume_id,
        "archive_file": str(out),
        "chapters_count": archive["chapters_count"],
        "total_words": archive["total_words"],
        "active_lines": len(archive["lines_snapshot"]["active"]),
    }


def simulate_impact(workspace: Path, entity: str, action: str = "retcon") -> Dict[str, Any]:
    """因果波及与风险测算：评估中途修改设定、人设或道具对全书长程逻辑的影响。"""
    entity = str(entity or "").strip()
    if not entity:
        raise BusinessError(
            "拟测算实体 --entity 参数为空，无法进行测算。",
            solution="请通过 --entity 指定要测算的实体名称或 ID，例如: python studio.py simulate impact --entity p_001",
        )

    ledger = StateLedger(workspace)
    timeline = ledger.get_timeline()
    lines = ledger.get_lines()
    locked = ledger.get_locked_facts()
    synopses = ledger.get_synopsis()

    affected_chapters: List[str] = []
    affected_lines: List[str] = []
    affected_locked: List[str] = []

    # 查时间线与在场记录
    for t in timeline:
        ch = t.get("chapter_id", "")
        chars = t.get("present_characters", [])
        if any(entity in str(c) for c in chars) or entity in str(t.get("dramatic_goal", "")) or entity in str(t.get("cliffhanger", "")):
            if ch not in affected_chapters:
                affected_chapters.append(ch)

    # 查梗概
    for ch, syn in synopses.items():
        if entity in str(syn.get("dramatic_goal", "")) or entity in str(syn.get("cliffhanger", "")) or entity in str(syn.get("present_characters", [])):
            if ch not in affected_chapters:
                affected_chapters.append(ch)

    # 查伏笔
    for lid, l in lines.items():
        if entity in l.get("name", "") or entity in l.get("desc", ""):
            affected_lines.append(f"{lid}: {l.get('name')}")

    # 查锁定事实
    for lf in locked:
        if entity in lf.get("fact", ""):
            affected_locked.append(f"{lf.get('id')}: {lf.get('fact')}")

    # 风险评估
    if affected_locked:
        risk_level = "HIGH (高风险 · 触碰已锁定法定事实)"
    elif len(affected_chapters) >= 5 or len(affected_lines) >= 2:
        risk_level = "MEDIUM (中风险 · 跨多章因果网络，需建立快照精确修补)"
    else:
        risk_level = "LOW (低风险 · 局部微创修改)"

    return {
        "entity": entity,
        "action": action,
        "risk_level": risk_level,
        "affected_chapters": affected_chapters,
        "affected_lines": affected_lines,
        "affected_locked_facts": affected_locked,
        "recommendation": "修改前必须运行 `python studio.py snapshot create` 建立快照备份！",
    }


def snapshot_create(workspace: Path, name: str) -> str:
    """创建工程安全快照 (snapshot create)。v4.1：纳入 log/（审计·对账报告）与根目录 pack.md。"""
    snap_dir = _ensure_dir(workspace / "snapshots")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # v4.2.1 缺陷#11：快照名净化，阻断 "../"等路径注入逃逸 snapshots 目录
    safe_name = re.sub(r'[\\/:*?"<>|\s]+', "_", str(name)).strip("._") or "snapshot"
    snap_file = snap_dir / f"{safe_name}_{timestamp}.zip"

    with zipfile.ZipFile(snap_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in ["bible", "characters", "entities", "outlines", "state", "manuscript", "log"]:
            src_folder = workspace / folder
            if src_folder.exists():
                for f in src_folder.rglob("*"):
                    if f.is_file() and ".corrupt-" not in f.name:
                        zf.write(f, f.relative_to(workspace))
        for root_file in ["project.json", "pack.md"]:
            if (workspace / root_file).exists():
                zf.write(workspace / root_file, root_file)

    return str(snap_file)


def milestone_add(workspace: Path, title: str, target_ch: int, desc: str) -> Dict[str, Any]:
    """新增里程碑。"""
    ms_file = workspace / "state" / "milestones.json"
    milestones = _load_json(ms_file, default=[])
    # v4.2.1 缺陷#14：按现存最大编号 +1 发号（旧版 len+1，删除后补建会撞号）
    max_n = 0
    for m0 in milestones:
        mm = re.search(r"(\d+)$", str(m0.get("id", "")))
        if mm:
            max_n = max(max_n, int(mm.group(1)))
    existing_ids = {m0.get("id") for m0 in milestones}
    n = max_n + 1
    while f"ms_{n:03d}" in existing_ids:
        n += 1
    m_id = f"ms_{n:03d}"
    item = {"id": m_id, "title": title, "target_ch": target_ch, "desc": desc, "status": "pending"}
    milestones.append(item)
    _save_json(ms_file, milestones)
    return item


def milestone_achieve(workspace: Path, milestone_id: str) -> Optional[Dict[str, Any]]:
    """标记里程碑达成。"""
    ms_file = workspace / "state" / "milestones.json"
    milestones = _load_json(ms_file, default=[])
    target = None
    for m in milestones:
        if m.get("id") == milestone_id or m.get("title") == milestone_id:
            m["status"] = "achieved"
            m["achieved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            target = m
            break
    if target:
        _save_json(ms_file, milestones)
    return target


def snapshot_list(workspace: Path) -> List[Dict[str, Any]]:
    """列出当前工作区所有可用的安全快照。"""
    snap_dir = workspace / "snapshots"
    if not snap_dir.exists():
        return []
    snaps = []
    for f in sorted(snap_dir.glob("*.zip"), reverse=True):
        snaps.append({
            "name": f.stem,
            "filename": f.name,
            "path": str(f),
            "size_kb": round(f.stat().st_size / 1024, 1),
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return snaps


def snapshot_rollback(workspace: Path, name_or_file: str) -> Dict[str, Any]:
    """回滚至指定的安全快照。"""
    snap_dir = workspace / "snapshots"
    target_zip: Optional[Path] = None

    if Path(name_or_file).exists() and name_or_file.endswith(".zip"):
        target_zip = Path(name_or_file)
    elif (snap_dir / name_or_file).exists():
        target_zip = snap_dir / name_or_file
    elif (snap_dir / f"{name_or_file}.zip").exists():
        target_zip = snap_dir / f"{name_or_file}.zip"
    else:
        # 模糊匹配最新一个包含该名字的快照
        cand = [f for f in sorted(snap_dir.glob("*.zip"), reverse=True) if name_or_file in f.name]
        if cand:
            target_zip = cand[0]

    if not target_zip or not target_zip.exists():
        raise BusinessError(
            f"未找到指定的快照文件: '{name_or_file}'",
            solution="请运行 `python studio.py snapshot list` 查看可用的快照名称。",
        )

    # v4.1 安全带 1：回滚前自动建立当前状态快照（回滚本身可被撤销）
    pre_snap = snapshot_create(workspace, "pre_rollback")

    # v4.1 安全带 2：zip-slip 防护（拒绝压缩包内越级路径逃逸工作区）
    # v4.2.1 缺陷#11：startswith 前缀校验存在兄弟目录绕过（/ws 与 /ws_evil），
    # 改用 os.sep 锚定的严格前缀校验
    import os as _os
    ws_resolved = workspace.resolve()
    ws_prefix = str(ws_resolved) + _os.sep
    with zipfile.ZipFile(target_zip, "r") as zf:
        for info in zf.infolist():
            dest = (workspace / info.filename).resolve()
            if str(dest) != str(ws_resolved) and not str(dest).startswith(ws_prefix):
                raise GuardError(
                    f"快照包含非法越级路径，已中止回滚: {info.filename}",
                    solution="该快照压缩包可能损坏或包含非法路径，请选用其他快照或联系系统管理员。",
                )
        zip_names = {info.filename.replace("\\", "/") for info in zf.infolist()}
        zf.extractall(workspace)

    # v4.3 缺陷#A4 修复（回滚残留未来章节）：
    # 旧版 rollback 只是覆盖式解压——快照之后才产生的 manuscript/outlines/state 文件
    # 原样残留，被回滚的"未来章节"继续出现在 export 成书里。现做快照域全量对齐：
    # 受管目录中不在快照清单内的文件一律清除（.bak 与 .corrupt-* 安全产物除外），
    # 使工作区真正回到快照时刻。snapshots/、export/、pack.md 等非受管域不受影响。
    removed_files: List[str] = []
    for folder in ["bible", "characters", "entities", "outlines", "state", "manuscript", "log"]:
        d = workspace / folder
        if not d.exists():
            continue
        for f in sorted(d.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            rel = f.relative_to(workspace).as_posix()
            if f.is_file():
                if rel not in zip_names and ".corrupt-" not in f.name and not f.name.endswith(".bak"):
                    try:
                        f.unlink()
                        removed_files.append(rel)
                    except OSError:
                        pass
            elif f.is_dir():
                try:
                    f.rmdir()  # 仅清除已腾空的目录
                except OSError:
                    pass

    return {
        "name": target_zip.stem,
        "restored_from": str(target_zip),
        "target_file": target_zip.name,
        "pre_rollback_snapshot": pre_snap,
        "removed_files": removed_files,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": f"成功回滚工作区至快照: {target_zip.name}（回滚前状态已自动备份: {Path(pre_snap).name}）",
    }


# --- ID 深度追踪与治理导出 ---
from engine.id_tracker import id_list, id_next, trace_id
