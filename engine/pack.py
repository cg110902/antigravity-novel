"""Novel Studio 创作装配包构建引擎 (engine/pack.py)。

将细纲 (SSOT)、时空背景、在场人物全息档案、称谓矩阵、道具充能与世界公理
深度装配为自完备的 pack.md，彻底解决大模型跨文件翻找与截断丢失问题。
支持 15,000 Token 动态预算（配置项 token_cap）与优先级自适应修剪算法（四级修剪 + 🔴 超预算显式旗标）。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.config import load_config
from engine.errors import BusinessError
from engine.ops import _find_volume_outline
from engine.parser import parse_frontmatter
from engine.state import StateManager


def estimate_tokens(text: str) -> int:
    """估算文本的 Token 消耗（网文通用 Heuristic 算法：中文约 0.75 token/字，英文单词约 1.3 token/词）。"""
    if not text:
        return 0
    zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    en_words = len(re.findall(r"\b[a-zA-Z]+\b", text))
    numbers = len(re.findall(r"\b\d+\b", text))
    other_chars = len(text) - (zh_chars + sum(len(w) for w in re.findall(r"\b[a-zA-Z]+\b", text)) + sum(len(n) for n in re.findall(r"\b\d+\b", text)))
    return int(zh_chars * 0.75 + en_words * 1.3 + numbers * 0.6 + max(0, other_chars) * 0.4)


def _render_pack_content(
    chapter_id: str,
    budget_badge: str,
    beats_text: str,
    prev_tail: str,
    char_dossiers: List[str],
    address_rules: List[str],
    debt_blocks: List[str],
    relation_blocks: List[str],
    shared_history_blocks: List[str],
    location_block: str,
    item_blocks: List[str],
    epistemology_warnings: List[str],
    dev_text: str,
    power_text: str,
    locked_fact_blocks: List[str],
    rolling_synopses: List[str],
) -> str:
    """内部装配组装器。"""
    return f"""# Novel Studio 自完备创作装配包 ({chapter_id})

> ⚡ **【起草先锋 Drafter 唯一事实源 · 杜绝全书漫游】**
> 本装配包已集成当章细纲、时空因果、在场人档案、称谓约束与世界红线。
> 起手单次全读本文件即可直接提笔撰写 1500~2600 字初稿，严禁查阅外部散乱文件！
{budget_badge}

---

## 📖 一、 本章法定细纲任务书（Single Source of Truth · 绝对事实依据 · P0）

{beats_text}

---

## 🌊 二、 上一章末尾余温（接戏动量 · P1）

{prev_tail if prev_tail else "（全书第一章，开门见山直接切入冲突）"}

---

## 👤 三、 在场人物全息档案与称谓法则 (P1)

{"".join(char_dossiers) if char_dossiers else "（在场均为即时人物）"}

### 🗣️ 法定称谓矩阵（严禁叫错称呼）
{chr(10).join(address_rules) if address_rules else "- 保持人物自然称谓，严禁乱加昵称。"}

### ⚡ 在场人物未了恩怨账（暗流张力与利益对冲）
{chr(10).join(debt_blocks) if debt_blocks else "- 在场各方暂无未清算因果血仇或重大誓言债务。"}

### 💔 双向动态情感温标与心理（拒绝干瘪流水账）
{chr(10).join(relation_blocks) if relation_blocks else "- 在场角色关系为基础接触，按当章戏剧目标展开摩擦。"}

### ⏳ 跨章历史交集与旧物渊源 (Shared History & Continuity Anchors)
{chr(10).join(shared_history_blocks) if shared_history_blocks else "- 在场各方首次同框交集或无显著历史跨章包袱，按当期心境正常推进。"}

{location_block}

> 🎭 **【行文法则】**：
> 1. **严禁抽象情绪形容词**：禁止直接写“感到心痛/难过/愤怒/五味杂陈/十分感动”，必须全量转化为**神经微反射与生理动作**（咽唾沫、指关节发白、背脊绷紧、避开对视、说话刻意用敬语拉远距离）；
> 2. **嘴硬体诚与情绪反冲（Emotional Dissonance）**：越在乎越要冷淡挑刺，越痛苦越要平静整理袖口，越恐惧话越密，嘴上说“随便你”，脚下一步不移；
> 3. **对白三分字面七分机锋（Subtext）**：每一句对话必须带双层潜台词，表面是公事/挑衅，底下是试探、怨怼或试探爱意，绝不直抒胸臆！

---

## ⚔️ 四、 道具支配权与充能账本 (P1)

{chr(10).join(item_blocks) if item_blocks else "- 当章无特殊道具调用。"}

---

## 🛡️ 五、 角色认知界限与防透视红线 (P0 硬约束)

{chr(10).join(epistemology_warnings) if epistemology_warnings else "- 本章无特殊信息差阻隔。"}

---

## 🚫 六、 世界红线与战力标尺 (P2)

### 1. 本书偏离清单
{dev_text}

### 2. 战力破坏力实物标尺
{power_text}

---

## 🔒 七、 全书不可推翻法定事实 (Locked Facts · P0 铁律)

{chr(10).join(locked_fact_blocks) if locked_fact_blocks else "- 暂无全局锁定事实。"}

---

## 📜 八、 近期剧情滚动概要 (Rolling Synopses · 最近 3 章 · P2)

{chr(10).join(rolling_synopses) if rolling_synopses else "- 本卷开篇前序无历史梗概。"}
"""


def build_pack(workspace: Path, chapter_id: str, write_file: bool = True) -> Dict[str, Any]:
    state_mgr = StateManager(workspace)
    curr_state = state_mgr.get_current()
    cfg = load_config(workspace)
    protagonist = cfg.get("protagonist", "主角")

    # 1. 寻找并读取 beats 细纲 (P0)
    # v4.1 跨卷修复：改用全卷扫描定位（旧版只看 current_vol，换卷期会装配错卷或找不到细纲）
    vol_outline_file, vol_id = _find_volume_outline(workspace, chapter_id)
    beats_cand = [
        workspace / "outlines" / vol_id / "beats" / f"{chapter_id}.md",
        workspace / "outlines" / f"{chapter_id}.md",
    ]
    beats_file: Optional[Path] = None
    for bc in beats_cand:
        if bc.exists():
            beats_file = bc
            break
    if not beats_file and vol_outline_file is not None:
        for cand in sorted((workspace / "outlines").glob(f"**/beats/{chapter_id}.md")) if (workspace / "outlines").exists() else []:
            beats_file = cand
            break

    if not beats_file:
        raise BusinessError(
            f"未找到第 {chapter_id} 章细纲文件（候选路径: {beats_cand[0]}）",
            solution=f"请先运行脚手架命令生成细纲: python studio.py beats new {chapter_id} --write",
        )

    beats_text = beats_file.read_text(encoding="utf-8-sig", errors="replace")
    frontmatter, _ = parse_frontmatter(beats_text)
    if not frontmatter:
        raise BusinessError(
            f"第 {chapter_id} 章细纲未包含有效 YAML Front-matter 元数据: {beats_file.name}",
            solution="请检查细纲顶部是否包含由 '---' 包裹的 YAML 区块（含 chapter_id, present_characters 等必要字段）。",
        )

    # 2. 提取上一章尾声 (P1)
    prev_tail = ""
    m = re.search(r"(\d+)$", chapter_id)
    if m:
        num = int(m.group(1)) - 1
        if num > 0:
            prev_id = f"ch_{num:03d}"
            cands = [
                workspace / "manuscript" / vol_id / "final" / f"{prev_id}.md",
                workspace / "manuscript" / vol_id / "raw" / f"{prev_id}_v3.md",
                workspace / "manuscript" / vol_id / "raw" / f"{prev_id}.md",
            ]
            for c in cands:
                if c.exists():
                    ptxt = c.read_text(encoding="utf-8-sig", errors="replace").strip()
                    prev_tail = ptxt[-1000:] if len(ptxt) > 1000 else ptxt
                    break

    # 3. 提取在场角色全息档案与法定互称矩阵 (P1)
    persons_db = state_mgr.get_persons()
    # v4.2.2 缺陷#20：紧凑列表形态（present_characters: [p_001, p_002]）此前被
    # isinstance(dict) 检查整段跳过——人物档案、恩怨、关系、历史交集全部丢失。
    # 此处统一归一化：字符串条目回查 persons_db 补全记录，下游全部受益。
    # FIND-CT7（cli L1· Drafter 唯一事实源污染）：整值标量包裹。作者按自然 YAML
    # 写 `present_characters: p_001`（不带方括号，独戏章极常见）时，旧版
    # `for _c in <str>` 按单字符迭代，产出 5 条幻影档案 [p]/[_]/[0]/[0]/[1]，
    # 主角 Want/Fear/卡/称谓矩阵全丢且 exit 0 无任何旗标。与 ops.py evidence
    # candidates 的归一化口径对齐：str/dict 整值先包成列表再迭代。
    pack_warnings: List[str] = []
    _raw_pc = frontmatter.get("present_characters")
    _pc_iter: List[Any] = (
        [_raw_pc] if isinstance(_raw_pc, (str, dict))
        else (_raw_pc if isinstance(_raw_pc, list) else [])
    )
    present_chars: List[Dict[str, Any]] = []
    for _c in _pc_iter:
        if isinstance(_c, str):
            _cid = _c.strip()
            _rec = persons_db.get(_cid, {})
            present_chars.append({
                "id": _cid,
                "name": _rec.get("name", "") or _cid,
                "role": _rec.get("role", "supporting"),
            })
        elif isinstance(_c, dict):
            present_chars.append(_c)
        elif _c is not None:
            # FIND-CT7b：数字/嵌套/non-str-non-dict 条目静默丢弃会让作者误以为
            # 角色在场；显式告警（flow-list 里未加引号的数字会走到这里）。
            pack_warnings.append(
                f"present_characters 存在无法解析的条目（类型 {type(_c).__name__}: {_c!r} 已跳过）——"
                f"每个条目应为角色 ID 字符串（\"p_001\"）或含 id/name 的字典；未加引号的数字 ID 请补引号。"
            )
    char_dossiers: List[str] = []
    address_rules: List[str] = []

    for c in present_chars:
        if not isinstance(c, dict):
            continue
        cid = c.get("id", "")
        cname = c.get("name", "")
        c_record = persons_db.get(cid, {})

        # 查实体卡文件
        card_text = ""
        card_fm: Dict[str, Any] = {}
        card_candidates = []
        if c_record.get("card"):
            card_candidates.append(workspace / c_record["card"])
        card_candidates.extend([
            workspace / "characters" / f"{cname}.md",
            workspace / "characters" / "protagonist.md" if cid == "p_001" else None,
            workspace / "characters" / "antagonist.md" if (cid == "p_002" or c.get("role") == "antagonist") else None,
        ])
        for card_path in card_candidates:
            if card_path and card_path.exists():
                raw_c_txt = card_path.read_text(encoding="utf-8-sig", errors="replace")
                card_fm, _ = parse_frontmatter(raw_c_txt)
                card_text = raw_c_txt[:800]
                break

        want = c.get("want") or c_record.get("want") or card_fm.get("want", "未锁定")
        fear = c.get("fear") or c_record.get("fear") or card_fm.get("fear", "未锁定")
        arc_phase = c.get("arc_phase") or c_record.get("arc_phase", "")
        quirk = c.get("quirk") or c_record.get("quirk") or card_fm.get("quirk", "")
        taboo = c.get("taboo") or c_record.get("taboo") or card_fm.get("taboo", "")
        latent_mood = c.get("latent_mood") or c_record.get("latent_mood") or card_fm.get("latent_mood", "")
        physio_leak = c.get("physiological_leak") or c_record.get("physiological_leak") or card_fm.get("physiological_leak", "")
        vuln = c.get("vulnerability") or c_record.get("vulnerability") or card_fm.get("vulnerability", "")
        sensory = c_record.get("sensory_anchor") or card_fm.get("sensory_anchor", "")
        micro_list = c_record.get("micro_actions") or card_fm.get("micro_actions", [])
        micro = ", ".join(micro_list) if isinstance(micro_list, list) else str(micro_list)
        arc_hist = c_record.get("arc_history") or []
        last_seen = c_record.get("last_seen_ch", "")

        dossier_block = f"""#### 👤 [{cid}] {cname} ({c.get('role', '配角')})
- **核心渴望 (Want)**：{want}
- **核心恐惧 (Fear)**：{fear}
"""
        if arc_phase:
            dossier_block += f"- **人物弧光阶段 (Arc Phase)**：{arc_phase}\n"
        dossier_block += f"""- **入场隐性情绪荷载 (Latent Mood)**：{latent_mood if latent_mood else '带着前文事件的隐秘后劲入场'}
- **生理应激微动作 (Physio Leak)**：{physio_leak if physio_leak else '不自觉小动作/视线回避/小动作泄露'}
- **心理软肋 (Vulnerability)**：{vuln if vuln else '触碰必破防之软肋'}
- **反常怪癖 (Quirk)**：{quirk if quirk else '活人生态反常点/神经质执念'}
- **神经雷区 (Taboo)**：{taboo if taboo else '触碰必死之底线'}
- **外观感知物象**：{sensory if sensory else '见细纲描写'}
- **习惯微动作**：{micro if micro else '切身利益下生活化神态'}
"""
        if arc_hist:
            last_arc = arc_hist[-1]
            dossier_block += f"- **前序出场轨迹**：第 {last_arc.get('chapter')} 章 (离场心境: {last_arc.get('status_out') or '未注明'})\n"
        elif last_seen:
            dossier_block += f"- **前序最后登场**：第 {last_seen} 章\n"

        if card_text:
            dossier_block += f"- **人物全息卡切片**：\n```text\n{card_text[:400]}...\n```\n"
        char_dossiers.append(dossier_block)

        # 称谓矩阵（融合实体卡与台账中的称谓映射）
        matrix = dict(card_fm.get("address_matrix") or {})
        matrix.update(c_record.get("address_matrix") or {})
        for tgt, addr in matrix.items():
            if tgt and addr:
                address_rules.append(f"- **{cname}** 称呼 **{tgt}** 必须为：`{addr}`")

    # 4.0 提取在场角色的未了恩怨人情账 (Debts & Grudges · P1 · 双向检索)
    debts_db = state_mgr.get_debts()
    in_scene_names = {c.get("name") for c in present_chars if isinstance(c, dict)}
    in_scene_ids = {c.get("id") for c in present_chars if isinstance(c, dict)}
    debt_blocks: List[str] = []
    for d in debts_db:
        if d.get("status", "unpaid") == "unpaid":
            t = d.get("target_char", "")
            s = d.get("source_char", "")
            if t in in_scene_names or t in in_scene_ids or s in in_scene_names or s in in_scene_ids:
                debt_blocks.append(f"- ⚔️ **[{d.get('type', '恩怨')}]** `{s}` ➔ `{t}`: {d.get('desc')} (立于第 {d.get('created_ch')} 章 ｜ 状态: 待清算)")

    # 3.6 提取在场角色双向动态情感与心理 (Relations & Push-Pull Tension · P1)
    rel_db = state_mgr.get_relations()
    relation_blocks: List[str] = []
    for i, c1 in enumerate(present_chars):
        if not isinstance(c1, dict):
            continue
        c1_id = c1.get("id", "")
        c1_name = c1.get("name", "")
        for j, c2 in enumerate(present_chars):
            if i == j or not isinstance(c2, dict):
                continue
            c2_id = c2.get("id", "")
            c2_name = c2.get("name", "")
            pair_keys = [f"{c1_id}->{c2_id}", f"{c1_name}->{c2_name}"]
            for pk in pair_keys:
                if pk in rel_db:
                    r = rel_db[pk]
                    # FIND-CT15：与 cockpit 同口径的数值归一化——字符串型 affinity
                    # （"20"）会让 `aff > 0` TypeError 崩掉装配（Drafter 唯一输入）。
                    try:
                        aff = float(r.get("affinity", 0) or 0)
                    except (TypeError, ValueError):
                        aff = 0.0
                    aff_str = f"+{int(aff)}" if aff > 0 else str(int(aff))
                    try:
                        _trust = int(float(r.get("trust", 50) or 50))
                    except (TypeError, ValueError):
                        _trust = 50
                    try:
                        _tension = int(float(r.get("tension", 20) or 20))
                    except (TypeError, ValueError):
                        _tension = 20
                    relation_blocks.append(
                        f"- 💘 **[{r.get('dynamic_label', '情感暗流')}]** `{c1_name}` ➔ `{c2_name}`：\n"
                        f"  - 好恶温标: `{aff_str}` ｜ 信任度: `{_trust}/100` ｜ 心理拉扯指数: `🔥 {_tension}/100`\n"
                        f"  - 🤫 潜台词与未挑明心结: “{r.get('unspoken_subtext') or '表面客套，暗中较劲'}”"
                    )

    # 3.7 提取跨章历史交集与旧物渊源 (Shared History & Continuity Anchors · P1)
    co_occur_db = state_mgr.get_co_occurrence()
    timeline_db = state_mgr.get_entity_timeline()
    shared_history_blocks: List[str] = []

    # 查在场人物之间的历史交集
    for i, c1 in enumerate(present_chars):
        if not isinstance(c1, dict):
            continue
        c1_id = c1.get("id", "")
        c1_name = c1.get("name", "")
        for j, c2 in enumerate(present_chars):
            if i >= j or not isinstance(c2, dict):
                continue
            c2_id = c2.get("id", "")
            c2_name = c2.get("name", "")
            p_sorted = sorted([c1_id, c2_id])
            co_key = f"{p_sorted[0]}<->{p_sorted[1]}"
            co_info = co_occur_db.get(co_key)
            if co_info:
                last_ch = co_info.get("last_seen_ch", "")
                if last_ch and last_ch != chapter_id:
                    m_curr = re.search(r"(\d+)$", chapter_id)
                    m_past = re.search(r"(\d+)$", last_ch)
                    gap_str = ""
                    if m_curr and m_past:
                        gap = int(m_curr.group(1)) - int(m_past.group(1))
                        if gap > 1:
                            gap_str = f"（时隔 {gap} 章再会）"
                    last_dyn = co_info.get("last_interaction_summary", {})
                    dyn_desc = last_dyn.get("dynamic", "同场")
                    sub_desc = last_dyn.get("unspoken_subtext", "")
                    shared_history_blocks.append(
                        f"- 👥 **【故人交集记忆】** `{c1_name}` 与 `{c2_name}` 上一次交集发生于第 `{last_ch}` 章 {gap_str}：\n"
                        f"  - 离场关系动态: `{dyn_desc}`\n"
                        f"  - 前序遗留潜台词: “{sub_desc or '各怀心腹事，存在利益防备'}”"
                    )

    # 查在场道具的历史登场流转
    # v4.3：单 dict 形态统一包裹为列表（与 state.py 归一化口径一致，防 dict 键名被当条目遍历）
    # FIND-CT14（cli L2）：state_deltas 为 null/标量时旧版 `.get("items")` 直接
    # AttributeError 逃逸 exit 4（用户数据问题被升级为系统故障）。先判 dict 形态。
    _sd_raw = frontmatter.get("state_deltas")
    _sd_dict = _sd_raw if isinstance(_sd_raw, dict) else {}
    _raw_it = _sd_dict.get("items") or []
    _it_list = [_raw_it] if isinstance(_raw_it, dict) else (_raw_it if isinstance(_raw_it, list) else [])
    for it in _it_list:
        if isinstance(it, dict):
            iid = it.get("id", "")
            iname = it.get("name", "")
            t_info = timeline_db.get(iid)
            if t_info and t_info.get("events"):
                past_events = [e for e in t_info["events"] if e.get("chapter") != chapter_id]
                if past_events:
                    last_ev = past_events[-1]
                    shared_history_blocks.append(
                        f"- 🗡️ **【旧物历史履历】** 道具 `[{iid}] {iname}` 上一次现身于第 `{last_ev.get('chapter')}` 章：\n"
                        f"  - 历史事件: {last_ev.get('event', '流转使用')} (记录持有人: {last_ev.get('holder', '未知')}, 剩余充能: {last_ev.get('remaining_charges', '未知')})"
                    )

    # 3.8 提取当前空间场景氛围锚点 (P1)
    location_str = str(frontmatter.get("location", ""))
    location_block = ""
    if location_str:
        places_db = state_mgr.get_places()
        matched_place = None
        for pid, prec in places_db.items():
            if pid in location_str or prec.get("name") in location_str or location_str in prec.get("name", ""):
                matched_place = prec
                break
        sensory = matched_place.get("sensory_anchor", "") if matched_place else ""
        # v4.3.1：places 台账法定字段统一为 environment_rules（schema.PlaceRecord /
        # templates/README §4 白名单 / entities/location_card 卡三方一致口径）；
        # 兼容早期工作区手写的 rules_taboos 旧键。
        taboos = ""
        if matched_place:
            _tab = matched_place.get("environment_rules") or matched_place.get("rules_taboos") or ""
            taboos = "；".join(_tab) if isinstance(_tab, list) else str(_tab)
        summary = matched_place.get("summary", "") if matched_place else ""
        loc_desc = []
        if sensory:
            loc_desc.append(f"  - **感官物象**：{sensory}")
        if taboos:
            loc_desc.append(f"  - **禁忌规则**：{taboos}")
        if summary:
            loc_desc.append(f"  - **场景概要**：{summary}")
        if loc_desc:
            location_block = f"### 📍 当前空间场景氛围锚点 (`{location_str}`)\n" + "\n".join(loc_desc) + "\n"
        else:
            location_block = f"### 📍 当前空间场景发生地\n- 发生地：`{location_str}`（请紧扣当下空间环境渲染呼吸感）\n"

    # 4. 提取当章道具与持有者 (P1)
    items_db = state_mgr.get_items()
    item_blocks: List[str] = []

    # 4.1 在场核心角色常驻随身装备与物品 (Active Carried Inventory)
    carried_blocks: List[str] = []
    in_scene_names = {c.get("name") for c in present_chars if isinstance(c, dict)}
    in_scene_ids = {c.get("id") for c in present_chars if isinstance(c, dict)}
    for iid, irec in sorted(items_db.items()):
        if not isinstance(irec, dict):
            continue
        if irec.get("status", "active") == "active":
            h = str(irec.get("holder", ""))
            if h in in_scene_names or h in in_scene_ids or any(k in h for k in (protagonist, "主角", "p_001")):
                # FIND-CT40（CT15 漏网）：charges 经手工编辑可能带字符串（"abc"/"3"），
                # `c_val >= 0` 直接 TypeError 崩掉装配。与 relations 同口径数值归一。
                c_val = irec.get("charges", -1)
                try:
                    c_num = float(c_val)
                except (TypeError, ValueError):
                    c_num = -1.0
                c_str = f"充能/储量: `{c_val}`" if c_num >= 0 else "无上限/装备"
                dur = irec.get("durability", "完好")
                sens = irec.get("sensory_anchor", "")
                sens_str = f" ｜ 物象: {sens[:40]}…" if sens else ""
                carried_blocks.append(f"- 🎒 **[{iid}] {irec.get('name')}** ｜ 支配人: `{h}` ｜ {c_str} ｜ 耐久: `{dur}`{sens_str}")

    if carried_blocks:
        item_blocks.append("### 🎒 在场角色随身常驻装备与物品 (Carried Inventory)")
        item_blocks.extend(carried_blocks)

    # 4.2 当章明确增量与充能变动 (Deltas)
    delta_blocks: List[str] = []
    # FIND-CT14：state_deltas 非 dict 时按空块处理（同上，防 AttributeError）
    _raw_deltas = (_sd_raw if isinstance(_sd_raw, dict) else {}).get("items") or []
    item_deltas = [_raw_deltas] if isinstance(_raw_deltas, dict) else (_raw_deltas if isinstance(_raw_deltas, list) else [])
    for it in item_deltas:
        if isinstance(it, dict):
            iid = it.get("id", "")
            iname = it.get("name", "")
            irec = items_db.get(iid, {})
            holder = it.get("holder_change") or irec.get("holder", "主角")
            charges = irec.get("charges", "非计数")
            st = it.get("status") or irec.get("status", "active")
            delta_blocks.append(f"- ⚡ **[{iid}] {iname}** ｜ 当前支配人: `{holder}` ｜ 变动后充能: `{charges}` ｜ 状态: `{st}`")

    if delta_blocks:
        item_blocks.append("\n### ⚡ 当章道具状态变动与充能消耗 (Deltas)")
        item_blocks.extend(delta_blocks)


    # 5. 提取认知盲区警示 (Epistemology Guardrail · P0 铁律)
    # FIND-CT39（同 CT38 漏网）：epistemology 非 dict（list/标量）时旧版
    # `frontmatter.get("epistemology") or {}` 后 .get 直接 AttributeError 崩掉
    # 装配——pack 是 Drafter 唯一输入，不能因前端形态问题崩栈。形态防御。
    epistemology = frontmatter.get("epistemology")
    if not isinstance(epistemology, dict):
        epistemology = {}
    blind_spots = epistemology.get("blind_spots") or {}
    if not isinstance(blind_spots, dict):
        blind_spots = {}
    epistemology_warnings: List[str] = []
    for cid, secrets in blind_spots.items():
        if isinstance(secrets, list):
            for s in secrets:
                epistemology_warnings.append(f"🚨 **绝密禁令**：角色 `[{cid}]` 绝对不知晓: 【{s}】（正文中绝对严禁该角色提及或反应知晓！）")

    # 6. 提取世界偏离与战力标尺 (P2)
    dev_file = workspace / "bible" / "06_deviations.md"
    dev_text = dev_file.read_text(encoding="utf-8-sig", errors="replace")[:1200] if dev_file.exists() else "无"

    power_file = workspace / "bible" / "02_power_system.md"
    power_text = power_file.read_text(encoding="utf-8-sig", errors="replace")[:1000] if power_file.exists() else "无"

    # 7. 提取全书不可违逆既定事实 (Locked Facts · P0 铁律)
    locked_facts = state_mgr.get_locked_facts()
    locked_fact_blocks: List[str] = []
    for lf in locked_facts:
        if isinstance(lf, dict) and lf.get("fact"):
            locked_fact_blocks.append(f"- **[{lf.get('id', 'FACT')}]** {lf.get('fact')} (第{lf.get('established_ch', '初始')}章确立)")

    # 8. 提取近期剧情滚动概要 (Rolling Synopses · 最近 3 章 · P2)
    synopses_db = state_mgr.get_synopsis()
    rolling_synopses: List[str] = []
    m_ch = re.search(r"(\d+)$", chapter_id)
    if m_ch:
        curr_ch_num = int(m_ch.group(1))
        for prev_c in range(max(1, curr_ch_num - 3), curr_ch_num):
            pid = f"ch_{prev_c:03d}"
            if pid in synopses_db:
                s_item = synopses_db[pid]
                goal = s_item.get("dramatic_goal") or "情节推进"
                cliff = s_item.get("cliffhanger") or "悬念定格"
                rolling_synopses.append(f"- **第 {pid} 章 《{s_item.get('title', '')}》**：\n  - 戏眼事件：{goal}\n  - 断章余温：{cliff}")

    # =========================================================================
    # 动态 Token 预算管理与自适应优先级修剪算法 (Dynamic Budget Manager)
    # 预算上限：配置中心 token_cap（默认 15,000 Tokens）
    # P0 (细纲、禁令、事实) 绝对刚性保护；P2 率先重塑/压缩；P1 次级优化
    # =========================================================================
    TOKEN_CAP = int(load_config(workspace).get("token_cap", 15000))
    is_pruned = False
    prune_stages: List[str] = []

    # 初始组装检查
    initial_badge = "> 📊 【装配包动态预算监控】 估算中..."
    raw_md = _render_pack_content(
        chapter_id, initial_badge, beats_text, prev_tail, char_dossiers,
        address_rules, debt_blocks, relation_blocks, shared_history_blocks,
        location_block, item_blocks, epistemology_warnings, dev_text, power_text,
        locked_fact_blocks, rolling_synopses,
    )
    tokens = estimate_tokens(raw_md)

    # 裁剪 Pass 1: 压缩 P2 世界观与战力设定 (保留前 300 字符)
    if tokens > TOKEN_CAP:
        if len(dev_text) > 400 or len(power_text) > 400:
            is_pruned = True
            dev_text = dev_text[:400] + "\n...（已自适应重塑保留核心）"
            power_text = power_text[:400] + "\n...（已自适应重塑保留核心破坏力标尺）"
            prune_stages.append("P2 世界观重塑")
            raw_md = _render_pack_content(
                chapter_id, initial_badge, beats_text, prev_tail, char_dossiers,
                address_rules, debt_blocks, relation_blocks, shared_history_blocks,
                location_block, item_blocks, epistemology_warnings, dev_text, power_text,
                locked_fact_blocks, rolling_synopses,
            )
            tokens = estimate_tokens(raw_md)

    # 裁剪 Pass 2: 压缩 P2 滚动大纲 (仅保留最近 1 章，或完全折叠)
    if tokens > TOKEN_CAP:
        is_pruned = True
        if len(rolling_synopses) > 1:
            rolling_synopses = rolling_synopses[-1:]
            prune_stages.append("P2 历史梗概向前折叠")
        else:
            rolling_synopses = ["- （为保障当期核心戏剧冲突最高算力注意力，历史梗概已动态折叠）"]
            prune_stages.append("P2 历史梗概完全折叠")
        raw_md = _render_pack_content(
            chapter_id, initial_badge, beats_text, prev_tail, char_dossiers,
            address_rules, debt_blocks, relation_blocks, shared_history_blocks,
            location_block, item_blocks, epistemology_warnings, dev_text, power_text,
            locked_fact_blocks, rolling_synopses,
        )
        tokens = estimate_tokens(raw_md)

    # 裁剪 Pass 3: 剥离 P1 人物卡切片中非核心长文，限制历史交集条目
    if tokens > TOKEN_CAP:
        is_pruned = True
        pruned_dossiers = []
        for d in char_dossiers:
            d_clean = re.sub(r"- \*\*人物全息卡切片\*\*：\n```text[\s\S]*?```\n?", "", d)
            pruned_dossiers.append(d_clean)
        char_dossiers = pruned_dossiers
        if len(shared_history_blocks) > 2:
            shared_history_blocks = shared_history_blocks[:2]
        prune_stages.append("P1 人物卡长篇切片精简")
        raw_md = _render_pack_content(
            chapter_id, initial_badge, beats_text, prev_tail, char_dossiers,
            address_rules, debt_blocks, relation_blocks, shared_history_blocks,
            location_block, item_blocks, epistemology_warnings, dev_text, power_text,
            locked_fact_blocks, rolling_synopses,
        )
        tokens = estimate_tokens(raw_md)

    # 裁剪 Pass 4: 压缩 P1 接戏动量至最后 200 字
    if tokens > TOKEN_CAP:
        if len(prev_tail) > 200:
            is_pruned = True
            prev_tail = "..." + prev_tail[-200:]
            prune_stages.append("P1 接戏尾声压缩")
            raw_md = _render_pack_content(
                chapter_id, initial_badge, beats_text, prev_tail, char_dossiers,
                address_rules, debt_blocks, relation_blocks, shared_history_blocks,
                location_block, item_blocks, epistemology_warnings, dev_text, power_text,
                locked_fact_blocks, rolling_synopses,
            )
            tokens = estimate_tokens(raw_md)

    # 最终状态徽章
    # v4.2.2 缺陷#21：修剪到底仍超预算时必须显式暴露（旧版静默超发，Drafter 上下文被截断无人知）
    over_budget = tokens > TOKEN_CAP
    if over_budget:
        status_label = f"🔴 超预算 {tokens - TOKEN_CAP} Tokens (已触发全部修剪级: {' ➔ '.join(prune_stages) or '无'} ｜ 建议拆分细纲或提高 token_cap)"
        badge = f"> 📊 【装配包动态预算监控】 估算消耗: **{tokens}** / {TOKEN_CAP} Tokens (状态: {status_label})"
    elif is_pruned:
        status_label = f"🟡 自适应动态修剪 (已触发: {' ➔ '.join(prune_stages)} ｜ 核心 P0 绝对保护)"
        badge = f"> 📊 【装配包动态预算监控】 估算消耗: **{tokens}** / {TOKEN_CAP} Tokens (状态: {status_label})"
    else:
        status_label = "🟢 预算健康 (无损全量装配)"
        badge = f"> 📊 【装配包动态预算监控】 估算消耗: **{tokens}** / {TOKEN_CAP} Tokens (状态: {status_label})"

    pack_md = _render_pack_content(
        chapter_id, badge, beats_text, prev_tail, char_dossiers,
        address_rules, debt_blocks, relation_blocks, shared_history_blocks,
        location_block, item_blocks, epistemology_warnings, dev_text, power_text,
        locked_fact_blocks, rolling_synopses,
    )

    target_pack = workspace / "pack.md"
    if write_file:
        target_pack.write_text(pack_md, encoding="utf-8")

    return {
        "chapter_id": chapter_id,
        "volume_id": vol_id,
        "target_pack": str(target_pack),
        "size_bytes": len(pack_md.encode("utf-8")),
        "estimated_tokens": tokens,
        "is_pruned": is_pruned,
        "over_budget": over_budget,
        "status": status_label,
        "warnings": pack_warnings,
    }
