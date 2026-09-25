"""Novel Studio 主控态势感知大盘 (engine/cockpit.py) · v4.2.2。

为 Director (主控总导演) 提供全景上帝视角态势仪表盘：
- 小说基础水位与当前连载进度
- 即时时空现场与主角随身状态
- 活跃未决伏笔雷达 (GUN/KNO/MIS)：收网临界 + 冷冻预警 + 逾期警报
- 📈 近 10 章节奏遥测：字数曲线、章型序列、同章型连转疲劳黄牌（v4.1 新增）
- 双向情感温标与修罗场雷达（None 安全渲染）
- 未来 1~2 章主线排产航标
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from engine import __version__
from engine.parser import parse_volume_outline
from engine.state import StateManager


def _ch_num(cid: str) -> int:
    m = re.search(r"(\d+)$", str(cid))
    return int(m.group(1)) if m else 0


def _s(v: Any, default: str = "") -> str:
    """None 安全字符串化。"""
    return str(v) if v is not None else default


_SLOT_TOKEN = re.compile(r"\{\{slot:[^}|\n]*(?:\|([^}]*))?\}\}")


def _outline_clean(v: Any, default: str = "待大纲细化") -> str:
    """v4.3 R2：航标展示的卷纲取值先过槽位清洗——未填卷纲不再把
    {{slot:ch_0XX_title|自行设定}} 原始槽位串糊进大盘（v4.2 实测槽位汤）。"""
    txt = str(v or "")
    if "{{slot:" not in txt:
        return txt or default
    txt = _SLOT_TOKEN.sub(lambda m: (m.group(1) or "").split("|")[-1].strip() if m.group(1) else "", txt)
    txt = re.sub(r"\s{2,}", " ", txt).strip(" 　，,。;；")
    return txt or default


def _rhythm_panel(timeline: List[Dict[str, Any]], current_num: int, window: int = 10) -> List[str]:
    """近 N 章节奏遥测面板（数据源：synopsis/timeline 的 chapter_type 与 word_count）。"""
    recent = [t for t in timeline if _ch_num(t.get("chapter_id", "")) <= current_num][-window:]
    if not recent:
        return ["📈 【近章节奏遥测】 (暂无已封存章节)"]

    words = [t.get("word_count", 0) or 0 for t in recent]
    types = [str(t.get("chapter_type") or "未标注") for t in recent]
    ids = [t.get("chapter_id", "?") for t in recent]

    lines = [
        f"📈 【近 {len(recent)} 章节奏遥测 (Rhythm Telemetry)】",
        f"   - 字数曲线: {' ➔ '.join(str(w) for w in words)}",
        f"   - 章型序列: {' ➔ '.join(types)}   (章型来自细纲 chapter_type: 破局/铺垫/过渡/爆发/回收/余韵)",
    ]
    # FIND-CT70（作者裁定 · 引擎退出文学性判断）：原「🟡 节奏黄牌 + 建议下一章安排
    # 对比章型换气」是引擎在替作者做**节奏审美裁决**——章型连排是否"疲劳"取决于题材、
    # 卷内位置与作者意图（连环爆发章正是爽文常态），引擎无从判断，也不该建议。
    # 现只报**事实**：连续同章型的章数与序列，怎么换气完全交给 Stage 1/2 的创作者。
    streak = 1
    streak_type = types[-1] if types else ""
    for t in reversed(types[:-1]):
        if t == streak_type:
            streak += 1
        else:
            break
    if streak_type not in ("未标注", "") and streak >= 2:
        lines.append(f"   - 章型连排事实：末尾连续 {streak} 章「{streak_type}」（纯计量，引擎不评价节奏好坏）")
    avg = sum(words) // len(words) if words else 0
    lines.append(f"   - 均章字数: {avg} 字 ｜ 覆盖: {ids[0]} ~ {ids[-1]}（纯计量，不设达标线）")
    return lines


def render_cockpit(workspace: Path) -> str:
    state_mgr = StateManager(workspace)
    curr = state_mgr.get_current()
    timeline = state_mgr.get_timeline()
    active_lines = state_mgr.get_active_lines()
    persons = state_mgr.get_persons()

    project_file = workspace / "project.json"
    pdata = {}
    if project_file.exists():
        try:
            with open(project_file, "r", encoding="utf-8-sig") as f:
                pdata = json.load(f)
        except Exception:
            pass

    title = pdata.get("title", "未命名小说")
    genre = pdata.get("genre", "通用题材")
    protagonist = pdata.get("protagonist", "主角")

    vol_id = curr.get("current_vol", "vol_01")
    ch_id = curr.get("current_ch", "ch_001")
    total_words = sum(t.get("word_count", 0) or 0 for t in timeline)
    total_chs = len(timeline)

    # 查主角即时状态
    protag_data = persons.get("p_001", {})
    protag_condition = protag_data.get("condition", "完好")
    protag_tier = protag_data.get("tier_name") or protag_data.get("role") or "初始阶段"
    locked_facts = state_mgr.get_locked_facts()
    last_goal = curr.get("last_dramatic_goal", "")

    # 查接下来 2 章的规划
    vol_outline = workspace / "outlines" / vol_id / "outline.md"
    upcoming_lines = []
    if vol_outline.exists():
        v_text = vol_outline.read_text(encoding="utf-8-sig", errors="replace")
        c_num = _ch_num(ch_id) or 1
        for off in [1, 2]:
            t_id = f"ch_{c_num + off:03d}"
            info = parse_volume_outline(v_text, t_id)
            if info:
                _t = _outline_clean(info.get("title"), default="（标题待定）")
                event = _outline_clean(info.get("event"))[:40]
                upcoming_lines.append(f"     - {t_id}: 《{_t}》 ➔ {event}{'…' if len(_outline_clean(info.get('event'))) > 40 else ''}")

    output = f"""================================================================================
🎮 【Novel Studio {__version__} · Showrunner Cockpit 态势感知大盘】
================================================================================
📖 作品元数据： 《{title}》 ｜ 题材：{genre} ｜ 主角：{protagonist}
📊 连载总水位： {vol_id} / {ch_id} ｜ 正文总字数：{total_words} 字 ｜ 已封存：{total_chs} 章
⏱️ 当前现场：   时空：{_s(curr.get('last_timeline'), '开局第一现场')} ｜ 地点：{_s(curr.get('last_location'), '初始场景')}
🩺 主角状态：   位阶：{protag_tier} ｜ 肉身/心境：{protag_condition}
🔒 铁律底座：   不可逆既定事实：{len(locked_facts)} 项 ｜ 上章主线戏眼：{_s(last_goal, '初始章节')}

💣 【活跃伏笔雷达 (Active Lines: {len(active_lines)} 条)】"""

    c_curr_num = _ch_num(ch_id) or 1

    if active_lines:
        for l in sorted(active_lines, key=lambda x: _ch_num(x.get("planted_ch", "")))[:8]:
            p_num = _ch_num(l.get("planted_ch", "")) or c_curr_num
            dormant_chs = max(0, c_curr_num - p_num)
            tier = l.get("tier", "A")
            tgt_ch = l.get("target_ch", "")

            # 临界倒计时 + 逾期警报（v4.1）
            deadline_alert = ""
            if tgt_ch:
                t_num = _ch_num(tgt_ch)
                if t_num:
                    remain = t_num - c_curr_num
                    if remain < 0:
                        deadline_alert = f" ⛔ [已逾期: 预定 {tgt_ch} 兑现，现已推进至 ch_{c_curr_num:03d}，本卷必清！]"
                    elif remain <= 5:
                        deadline_alert = f" 🔥 [收网临界: 距预定兑现 {tgt_ch} 仅剩 {remain} 章！]"

            tease_alert = ""
            if dormant_chs >= 25 and not deadline_alert:
                tease_alert = f" ⚠️ [冷冻预警: 已静默 {dormant_chs} 章！建议近期安排一次物象闪烁唤醒预期]"

            tgt_info = f" ➔ 预定收于 {tgt_ch}" if tgt_ch else ""
            desc = _s(l.get("desc"))
            output += (f"\n   - [{tier}阶] [{l.get('id')}] {l.get('name')}{tgt_info} "
                       f"(已存续 {dormant_chs} 章) ｜ 描述: {desc[:35]}{'…' if len(desc) > 35 else ''}{deadline_alert}{tease_alert}")
    else:
        output += "\n   (暂无活跃未决伏笔，剧情线收束平稳)"

    output += "\n\n" + "\n".join(_rhythm_panel(timeline, c_curr_num))

    # 查恩怨情仇未清算账本
    debts = state_mgr.get_debts()
    unpaid_debts = [d for d in debts if d.get("status") == "unpaid"]
    output += f"\n\n⚖️ 【全书未清算恩怨情仇账 (Unsettled Debts: {len(unpaid_debts)} 笔)】"
    if unpaid_debts:
        for d in unpaid_debts[:4]:
            # v4.3.2 缺陷#8：旧版只打印 target_char，丢失结怨发起方，
            # 「p_002 → p_001 的血债」在大盘上显示成「涉及 p_001」，方向不明。
            # 与 pack.py / ops.py 的 dossier 对齐为双向展示。
            _d_src = d.get("source_char") or "未知"
            _d_tgt = d.get("target_char") or "未知"
            output += f"\n   - [{d.get('type', '恩怨')}] `{_d_src}` ➔ `{_d_tgt}` ｜ 事由: {d.get('desc')} ｜ 立于第 {d.get('created_ch')} 章"
    else:
        output += "\n   (恩怨两清，暂无未结血仇或悬赏人情)"

    # 查双向情感与修罗场张力雷达（None 安全）
    relations = state_mgr.get_relations()

    # FIND-CT15（cli L2·大盘崩栈）：relations 表经手工编辑/跨版本导入可能带
    # 字符串型数值（tension: "75"），裸 `>= 30` / `> 0` 直接 TypeError → exit 4。
    # 大盘是只读展示位，绝不因脏展示数据崩栈：统一走数值归一化。
    def _num(v, default: float = 0.0) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    high_tension = [r for r in relations.values() if isinstance(r, dict) and _num(r.get("tension")) >= 30]
    output += f"\n\n💔 【人物情感温标与修罗场雷达 (Emotional Dynamics: {len(relations)} 组 ｜ 高张力 {len(high_tension)} 组)】"
    if relations:
        for r in list(relations.values())[:4]:
            if not isinstance(r, dict):
                continue
            aff = _num(r.get("affinity"))
            aff_str = f"+{int(aff)}" if aff > 0 else str(int(aff))
            subtext = _s(r.get("unspoken_subtext"), "（未记录）")[:30]
            output += (f"\n   - 💘 [{r.get('dynamic_label', '情感对撞')}] `{r.get('pair')}` ｜ "
                       f"温标: {aff_str} ｜ 张力: 🔥 {int(_num(r.get('tension'), 20))}/100 ｜机锋 : “{subtext}…”")
    else:
        output += "\n   (在场各方情感基调平稳，暂无白热化)"

    output += "\n\n🔭 【后续剧情航标前瞻】"
    if upcoming_lines:
        output += "\n" + "\n".join(upcoming_lines)
    else:
        output += "\n   (下一章待分卷大纲细化)"

    # v4.3 R2：经济面遥测——资金池余额与近笔流水（旧版大盘对经济系统完全失明）
    ledger_db = state_mgr.get_ledger()
    pools = ledger_db.get("pools", {}) if isinstance(ledger_db, dict) else {}
    txs = ledger_db.get("transactions", []) if isinstance(ledger_db, dict) else []
    output += f"\n\n💰 【资金池与近笔流水 (Pools: {len(pools)} 池 ｜ 流水 {len(txs)} 笔)】"
    if pools:
        pool_str = " ｜ ".join(f"`{k}`: {v}" for k, v in list(pools.items())[:6])
        output += f"\n   - 池余额：{pool_str}"
        if txs:
            last_txs = txs[-3:]
            for tx in last_txs:
                output += (f"\n   - [第 {tx.get('chapter', '?')} 章] {tx.get('pool', '?')} "
                           f"{tx.get('delta', 0):+} （事由: {str(tx.get('reason', ''))[:24]}）")
    else:
        output += "\n   (尚未声明任何货币池，经济系统未启用)"

    # 查主线里程碑规划
    ms_file = workspace / "state" / "milestones.json"
    ms_list = []
    if ms_file.exists():
        try:
            with open(ms_file, "r", encoding="utf-8-sig") as f:
                ms_list = json.load(f)
        except Exception:
            pass
    output += f"\n\n🎯 【主线里程碑排产 (Milestones: {len(ms_list)} 项)】"
    if ms_list:
        for m in ms_list[:5]:
            status_tag = "✅ [已达成]" if m.get("status") == "achieved" else f"⏳ [待达成 目标: 第{m.get('target_ch')}章]"
            desc = _s(m.get("desc"))[:35]
            output += f"\n   - [{m.get('id')}] 《{m.get('title')}》 {status_tag} ｜ {desc}{'…' if len(_s(m.get('desc'))) > 35 else ''}"
    else:
        output += "\n   (暂无阶段里程碑)"

    output += """
================================================================================"""
    return output
