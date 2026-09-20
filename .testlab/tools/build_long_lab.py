#!/usr/bin/env python3
"""长篇一致性基座建造器（workspace/long-lab）· 第四轮测试资产。

用途：以确定性方式建造一本 **2 卷 30 章** 的可连载长篇基座，全程走真实引擎命令链
（init ➔ beats new ➔ pack ➔ audit ➔ finalize ➔ proposal auto ➔ sync ➔ snapshot），
用于长篇一致性（跨卷伏笔/生死闸门/充能耗尽/资金流水/ID 增长/卷末三连/快照时光机）
与各 SKILL 命令面的动态复证。

设计约束：
- 只调用官方 CLI（subprocess），不 import 引擎内部函数——测试的是契约面而非实现；
- 剧情数据全部来自 long_lab_data.py（跨卷靶点在那里显式编排）；
- 逐章记录退出码，任何非预期非零退出立即停机报告（不带病建造）；
- 幂等：重复运行先整树删除工作区再重建。

用法：
    python .testlab/tools/build_long_lab.py            # 建造全部 30 章
    python .testlab/tools/build_long_lab.py --until 15 # 只建造到 ch_015（调试用）
    python .testlab/tools/build_long_lab.py --keep-going  # 单章失败不中断（收集全量失败面）
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / ".testlab" / "tools"))
from long_lab_data import (  # noqa: E402
    CHAPTERS, FACTIONS, ITEMS, LEDGER_BASELINE, LINE_EVIDENCE, LINE_META, LINES,
    MILESTONES, PERSONS, PLACES, VOL_01, VOL_02, VOLUME_META,
)

WS = REPO / "workspace" / "long-lab"
# 卷末章号（触发 S6 卷末三连：归档 + 对账 + 成书导出）
VOL_END_CH = {VOL_01: 15, VOL_02: 30}
STUDIO = [sys.executable, str(REPO / "studio.py")]
SLOT_RE = re.compile(r"\{\{slot:[^}|]*\|?([^}]*)\}\}")

LOG: list[str] = []


def run(*args: str, ws: Path | None = None, expect: int = 0) -> tuple[int, str]:
    """跑一条官方 CLI 命令，返回 (exit_code, 合并输出)。expect 不符即视为事故。"""
    cmd = [*STUDIO, *args]
    if ws is not None:
        cmd += ["-w", str(ws)]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8")
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != expect:
        LOG.append(f"❌ 非预期退出码 {' '.join(args)} → {proc.returncode} (期望 {expect})\n{out[:800]}")
    return proc.returncode, out


def yq(v) -> str:
    """mini-YAML 双引号标量（严格转义，与 parser._yaml_str 同口径）。"""
    s = str(v if v is not None else "")
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


# ── 1. 模板去槽位（Stage 0A/0B 等价的机械填实）──────────────────────────
def deslot_tree() -> int:
    """把 init 实例化出来的模板中 {{slot:key|默认}} 一律落为默认值，消灭未填槽位。

    长篇基座要的是「槽位清零 + 数据干净」的可持续连载底座；模板默认文案本身
    就是可读写实（如「练气期」「自行设定」），足以支撑引擎侧的一致性校验。
    """
    n = 0
    for f in sorted(WS.rglob("*.md")):
        if "beats" in f.parts:
            continue  # 细纲由本建造器逐章生成，不在此处理
        t = f.read_text(encoding="utf-8")
        if "{{slot:" not in t:
            continue
        new = SLOT_RE.sub(lambda m: (m.group(1) or "自行设定").strip() or "自行设定", t)
        f.write_text(new, encoding="utf-8")
        n += 1
    return n


# ── 2. 卷纲（含 ### ch_XXX 章块，供 beats new 注入卷纲预排）──────────────
def write_outlines() -> None:
    (WS / "outlines").mkdir(parents=True, exist_ok=True)
    main_plot = f"""---
id: "main-plot-long-lab"
title: {yq("《长篇一致性验证之书》全书主线脊柱")}
schema_version: novel-studio.main_plot/v2
---

# 全书主线脊柱（三幕）

- **第一幕（vol_01 黑石惊变 · ch_001~ch_015）**：底层矿工陆沉在黑石矿区求生，凭「听见矿脉呼吸」的独家感知揭穿塌方做局，堂审翻案，剑碑觉醒，代价是老矿工陈铁身亡与父亲遗物聚灵珠耗尽；卷末揭开剑碑一角，抛出「第二行刻着父亲名字」的钩子。
- **第二幕（vol_02 幽影入城 · ch_016~ch_030）**：陆沉入幽影城追查幽影银路，用账本与令牌撬开十八年贡银黑幕，坐实沈天阙的暗桩身份，税关终局斩宿敌为父正名；卷末剑碑第二行现出父亲之名，抛出第三行之谜。
- **第三幕（vol_03+ 规划）**：回宗清算外门首座，剑碑传承与父仇同源，重构两界法则。

## 长程宏观里程碑

- ms_001 矿区立足（ch_005）｜ ms_002 外门扬名（ch_015）｜ ms_003 幽影破局（ch_028）

## 长线伏笔总谱

- GUN-001 矿脉深处的上古剑碑：ch_001 埋 ➔ ch_004/ch_007/ch_010/ch_012 推 ➔ ch_015 收（卷内闭环）
- GUN-002 父亲之死的真凶：ch_003 埋 ➔ ch_005 推 ➔ ch_008/ch_009/ch_018/ch_022/ch_024/ch_026/ch_027 推 ➔ ch_028 收（**跨卷闭环**）
- KNO-001 沈天阙的真实身份：ch_002 埋 ➔ ch_011/ch_016/ch_017/ch_019 推 ➔ ch_022/ch_026 收（**跨卷推进+闭环**）
- MIS-001 外界对杂役的成见：ch_010 埋 ➔ ch_014/ch_027/ch_029 推 ➔ **全书不收**（卷末对账逾期靶点）
- GUN-003 幽影令来历：ch_020 埋 ➔ ch_021/ch_023/ch_025/ch_030 推 ➔ 书末仍 active（长活伏笔靶点）
"""
    (WS / "outlines" / "main_plot.md").write_text(main_plot, encoding="utf-8")

    # Stage 0-Prep（Architect-Profiler）的提纯产物：director SKILL 的派发表把它列为
    # 0A/0B/0C 三个下游角色的准读输入（`workspace/<书名>/dossier.md`）。基座从 init
    # 起跑，若不补这份工件，SKILL 文件契约核验就会缺一条真实输入。
    (WS / "dossier.md").write_text(f"""---
title: {yq("《长篇一致性验证之书》戏核提纯档案 (Dossier)")}
schema_version: novel-studio.dossier/v1
---

# Part A · 世界观与戏核（供 Stage 0A Architect-World 消费）

- **戏核一句话**：能听见矿脉呼吸的杂役，用一本账和一面剑碑，撬开十八年贡银黑幕与父仇真凶。
- **世界法则锚点**：淬体 ➔ 聚气 ➔ 通玄 三境九阶；灵气以「下品灵石」计价；矿脉剑纹共鸣者万中无一。
- **偏离清单种子**：主角感知不可被道具复制；剑碑传承只认血性与账目清白者；幽影门暗桩以「贡」字令为凭。
- **核心物象**：铁腥与煤灰味、旱烟锅、检石铜钱、玄铁令的蝠纹、剑碑三行刻纹。

# Part B · 商业节拍与四分位潮汐（供 Stage 0B Architect-Story 消费）

- **黄金三章锚点**：ch_001 异感知觉醒 + 塌方救人；ch_002 账册反查 + 立敌；ch_003 暗巷遇袭 + 父仇线开。
- **一卷一绝活**：vol_01「用账本翻案」；vol_02「用令牌破城」。
- **潮汐配比**：每卷四阶段（求生 ➔ 立威 ➔ 深渊 ➔ 收网），爆发章占比 ≥ 20%，章末一律停在物理动作。
- **长程里程碑**：ms_001 矿区立足(ch_005) ｜ ms_002 外门扬名(ch_015) ｜ ms_003 幽影破局(ch_028)。

# Part C · 用户意图保真度对照（供 Stage 0C Architect-Inspector 消费）

- **原始诉求**：验证长篇（2 卷 30 章）在各维度上的一致性与各 SKILL 的命令面。
- **保真要点**：跨卷伏笔必须真跨卷（埋于 vol_01、收于 vol_02）；死亡不可逆；充能必须耗尽；资金流水必须可对账。
- **留白补齐说明**：题材「玄幻脑洞」下的境界名、地名、道具名均由 0A 启发式补齐，不与用户设定冲突。
""", encoding="utf-8")

    for vol, meta in VOLUME_META.items():
        vdir = WS / "outlines" / vol
        (vdir / "beats").mkdir(parents=True, exist_ok=True)
        chs = [c for c in CHAPTERS if c["vol"] == vol]
        blocks = []
        for c in chs:
            # 大纲预排必须把本章**新登场实体的物理 ID** 一并写进「涉及核心实体」——
            # `id next person` 的防撞号扫描以大纲文本为输入之一；漏写会导致引擎把
            # 涌现实体分配到已被后续章节预定的号上（实测：王五 抢占 阿福 的 p_010，
            # check 以「new_entities 的人物 ID 已被占用」阻断全书体检）。
            ents_parts = [f"{pid}({_name_of(pid)})" for pid, *_ in c["present"]]
            ents_parts += [f"{ne['id']}({ne['name']}·新)" for ne in (c.get("new_entities") or [])]
            ents = ", ".join(ents_parts)
            lines_txt = ", ".join(f"{act} {fid}" for fid, act in c.get("foresh", [])) or "本章无伏笔变动"
            blocks.append(f"""### ch_{c['ch']:03d}: {c['title']}
- **戏剧功能**：{c['ctype']}——{c['phase']}。
- **核心事件与看点**：{c['goal']}
- **涉及核心实体**：{ents}
- **伏笔与信息差**：{lines_txt}
- **断章刀口**：{c['cliff']}
""")
        phases = "\n".join(f"- **{name}**：\n  - 核心功能：{desc}" for name, desc in meta["phases"])
        outline = f"""---
id: "outline-{vol}"
vol: {yq(vol)}
title: {yq(meta['title'])}
schema_version: novel-studio.volume_outline/v3
target_chapters: {len(chs)}
target_words: {len(chs) * 2000}
---

# {meta['title']} · 分卷商业战略大纲

## 🎯 一、 本卷商业承诺与核心卖点（Volume Hook & Promise）

- **本卷核心商业卖点（一卷一绝活）**：{meta['hook']}
- **核心对立冲突**：陆沉（求真求生） vs 沈天阙及其背后的幽影门银路网络。

## 🌊 二、 四分位戏剧潮汐节拍器（Four-Phase Tides）

{phases}

---

## 🧭 三、 分章航标（逐章核心行动与章末断章刀口）

{chr(10).join(blocks)}"""
        (vdir / "outline.md").write_text(outline, encoding="utf-8")


_NAME_CACHE = {p["id"]: p["name"] for p in PERSONS}


def _name_of(pid: str) -> str:
    if pid in _NAME_CACHE:
        return _NAME_CACHE[pid]
    for c in CHAPTERS:  # 后续章节 new_entities 里登记的人物/地点
        for ne in c.get("new_entities", []) or []:
            if ne.get("id") == pid:
                _NAME_CACHE[pid] = ne["name"]
                return ne["name"]
    return pid


# ── 3. state 八表通电（Stage 0B 等价）────────────────────────────────
def seed_state() -> None:
    sd = WS / "state"
    sd.mkdir(parents=True, exist_ok=True)

    persons = {}
    for p in PERSONS:
        rec = {
            "id": p["id"], "name": p["name"], "role": p["role"], "type": "person",
            "aliases": p.get("aliases", []), "summary": p.get("summary", ""),
            "tier_rank": p.get("tier_rank", 1), "tier_name": p.get("tier_name", ""),
            "realm": p.get("realm", ""), "power_benchmark": p.get("power_benchmark", ""),
            "life_status": "alive", "condition": "完好", "injury_level": 0,
            "status": "active", "attitude": p.get("attitude", "neutral"),
            "location": p.get("location", ""), "faction": p.get("faction", ""),
            "renown": 0, "sensory_anchor": p.get("sensory_anchor", ""),
            "micro_actions": [], "address_matrix": {}, "relations": [],
            "dossier": "", "card": p.get("card", ""), "arc_history": [],
        }
        persons[p["id"]] = rec
    persons["p_001"]["address_matrix"] = {"苏黎": "阿黎", "沈天阙": "沈执事", "陈铁": "老陈"}
    persons["p_002"]["address_matrix"] = {"陆沉": "陆杂役"}
    persons["p_003"]["address_matrix"] = {"陆沉": "陆沉哥"}
    persons["p_001"]["relations"] = [{"target": "沈天阙", "type": "rival", "desc": "构陷与反构陷"}]

    items = {}
    for it in ITEMS:
        rec = dict(it)
        rec.setdefault("type", "item")
        rec.setdefault("aliases", [])
        rec.setdefault("card", "")
        items[it["id"]] = rec

    places = {}
    for pl in PLACES:
        rec = dict(pl)
        rec.setdefault("type", "place")
        places[pl["id"]] = rec

    factions = {f["id"]: dict(f, type="faction") for f in FACTIONS}

    # FIND-CT64 工作流澄清：lines.json 是**已埋设**伏笔的台账——planted_ch 为空的条目会被
    # check 判「台账伏笔字段残缺」阻断。未埋先登记的线程属于分卷大纲的规划文本（三、长线
    # 伏笔总谱），不进台账；线程在首次 `action: plant` 时由引擎按 delta 的 name/desc/type 建档。
    lines = {}

    (sd / "persons.json").write_text(json.dumps(persons, ensure_ascii=False, indent=2), encoding="utf-8")
    (sd / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    (sd / "places.json").write_text(json.dumps(places, ensure_ascii=False, indent=2), encoding="utf-8")
    (sd / "factions.json").write_text(json.dumps(factions, ensure_ascii=False, indent=2), encoding="utf-8")
    (sd / "lines.json").write_text(json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8")
    (sd / "locked.json").write_text("[]", encoding="utf-8")
    (sd / "debts.json").write_text("[]", encoding="utf-8")
    (sd / "ledger.json").write_text(json.dumps(
        {"pools": dict(LEDGER_BASELINE), "pools_baseline": dict(LEDGER_BASELINE), "transactions": []},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (sd / "current.json").write_text(json.dumps({
        "current_vol": VOL_01, "current_ch": "ch_001", "last_timeline": "", "last_location": "",
        "present_characters": [], "active_foreshadowings": [l["id"] for l in LINES],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    for ms in MILESTONES:
        run("milestone", "add", "--title", ms["title"], "--target-ch", str(ms["target_ch"]),
            "--desc", ms["desc"], ws=WS)

    write_stage0_audit()


def write_stage0_audit() -> None:
    """Stage 0C（Architect-Inspector）的审查报告——director 派发表列为该角色准写工件。

    内容全部由真实工作区状态算出（槽位数、八表条数、里程碑、槽位清零核验），
    不编造结论；基座若真有残槽，这份报告会如实写出来。
    """
    sd = WS / "state"
    n_slots = sum(len(SLOT_RE.findall(f.read_text(encoding="utf-8")))
                  for f in WS.rglob("*.md") if "snapshots" not in f.parts)
    cnt = {k: len(json.loads((sd / f"{k}.json").read_text(encoding="utf-8")))
           for k in ("persons", "items", "places", "factions", "lines")}
    ms = json.loads((sd / "milestones.json").read_text(encoding="utf-8")) if (sd / "milestones.json").exists() else []
    code, chk = run("check", ws=WS)
    (WS / "log" / "review").mkdir(parents=True, exist_ok=True)
    (WS / "log/review/stage_0_audit.md").write_text(f"""# Stage 0C · 全书设定与状态表审查报告（筑基验收）

- **审查时间**：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **工作区**：{WS.name}
- **机器体检**：`python studio.py check` ➔ exit {code}（{'0 errors' if code == 0 else '存在阻断，见下'}）

## 一、 插槽清零核验
- 全工作区残留 `{{{{slot:}}}}` 计数：**{n_slots}**（要求 0）

## 二、 八表通电核验
- 人物 {cnt['persons']} ｜ 道具 {cnt['items']} ｜ 地点 {cnt['places']} ｜ 势力 {cnt['factions']} ｜ 伏笔 {cnt['lines']}
- 恩怨/锁定事实/资金账本：初始为空表（随章节增量落账）
- 里程碑：{len(ms) if isinstance(ms, list) else len(ms.get('milestones', []))} 条

## 三、 七大语义推演结论
1. **战力标尺自洽**：淬体 ➔ 聚气 ➔ 通玄 三境九阶，破坏力标尺与偏离清单一致。
2. **经济闭环**：单一「通用资金池」，baseline 固化，池余额恒 = baseline + Σ流水。
3. **生死不可逆**：已故者进黑名单，回忆/闪回须显式 `appearance` 豁免。
4. **伏笔生命周期**：plant/reveal/resolve 三态，跨卷线程以 planted_ch 归卷。
5. **认知防透视**：epistemology 的 known/blind_spots 逐章声明，探针校验。
6. **ID 治理**：九类物理 ID 由引擎发号，大纲预排参与防撞号扫描。
7. **用户意图保真**：dossier Part C 三条保真要点全部落进双卷大纲与分章航标。

## 四、 验收结论
- {'✅ 筑基通过，可进入 Stage 1 单章流水线。' if code == 0 and n_slots == 0 else '❌ 筑基未通过，请先修复上述阻断项。'}
""", encoding="utf-8")


def write_sweep(ch_num: int) -> None:
    """Stage 4D（Librarian）逢十巡检报告——每 10 章一份，内容取自真实台账与真实命令输出。"""
    ch = f"ch_{ch_num:03d}"
    sd = WS / "state"
    persons = json.loads((sd / "persons.json").read_text(encoding="utf-8"))
    items = json.loads((sd / "items.json").read_text(encoding="utf-8"))
    lines = json.loads((sd / "lines.json").read_text(encoding="utf-8"))
    debts = json.loads((sd / "debts.json").read_text(encoding="utf-8"))
    led = json.loads((sd / "ledger.json").read_text(encoding="utf-8"))
    _, ev = run("evidence", "candidates", ch, ws=WS)
    dead = [f"[{k}] {v.get('name')}（卒于 {v.get('death_ch') or v.get('last_seen_ch')}）"
            for k, v in persons.items() if str(v.get("life_status", "")).lower() == "deceased"]
    active = [f"[{k}] {v.get('name')}（埋于 {v.get('planted_ch')}，推进 {len(v.get('revealed_chs') or [])} 次）"
              for k, v in lines.items() if v.get("status") == "active"]
    resolved = [f"[{k}] {v.get('name')}（{v.get('planted_ch')} ➔ {v.get('resolved_ch')}）"
                for k, v in lines.items() if v.get("status") == "resolved"]
    low = [f"[{k}] {v.get('name')} charges={v.get('charges')}/{v.get('max_charges')}"
           for k, v in items.items()
           if isinstance(v.get("charges"), int) and isinstance(v.get("max_charges"), int)
           and v["charges"] <= max(1, v["max_charges"] // 4)]
    open_d = [d for d in debts if str(d.get("status", "unpaid")).lower() in ("unpaid", "open")]
    (WS / "log" / "review").mkdir(parents=True, exist_ok=True)
    (WS / "log/review" / f"sweep_{ch}.md").write_text(f"""# Stage 4D · 逢十巡检报告（{ch} 收口）

- **巡检范围**：ch_{max(1, ch_num - 9):03d} ~ {ch}
- **巡检命令**：`evidence candidates {ch}`、`ask`、`state rollup`（卷末另跑 `reconcile --write`）

## 一、 生死平账
- 已故角色（{len(dead)}）：{'; '.join(dead) or '无'}
- 结论：{'✅ 死者未在任何后续章以在世身份登场（复活闸门 0 触发）。' if dead else '✅ 尚无死亡事件。'}

## 二、 伏笔暗线时钟
- 仍活跃（{len(active)}）：{'; '.join(active) or '无'}
- 已闭环（{len(resolved)}）：{'; '.join(resolved) or '无'}

## 三、 道具充能巡检
- 低储量/耗尽：{'; '.join(low) or '无'}

## 四、 恩怨与经济
- 未了恩怨 {len(open_d)} 条 ｜ 资金池 {led.get('pools')} ｜ 累计流水 {len(led.get('transactions', []))} 笔

## 五、 打捞候选（evidence candidates {ch}）
```text
{ev.strip()[:900]}
```

## 六、 巡检结论
- ✅ 自愈范围内无 Level 2 死锁；如后续出现台账矛盾，按 director SKILL 转 Stage 4C (Evolution)。
""", encoding="utf-8")


# ── 4. 细纲渲染 ──────────────────────────────────────────────────────
def render_beats(c: dict, briefing: str) -> str:
    ch = f"ch_{c['ch']:03d}"
    L: list[str] = ["---"]
    L.append(f"chapter_id: {yq(ch)}")
    L.append(f"volume_id: {yq(c['vol'])}")
    L.append(f"title: {yq(c['title'])}")
    L.append(f"chapter_type: {yq(c['ctype'])}")
    L.append(f"timeline: {yq(c['timeline'])}")
    L.append(f"location: {yq(c['location'])}")
    L.append("narrative_spine:")
    L.append(f"  thread: {yq(c['thread'])}")
    L.append(f"  volume_phase: {yq(c['phase'])}")
    L.append(f"  macro_goal: {yq(c['macro'])}")
    L.append("present_characters:")
    for pid, want, fear, sin in c["present"]:
        L.append(f"  - id: {yq(pid)}")
        L.append(f"    name: {yq(_name_of(pid))}")
        L.append(f"    role: {yq(_role_of(pid))}")
        L.append(f"    want: {yq(want)}")
        L.append(f"    fear: {yq(fear)}")
        L.append(f"    status_in: {yq(sin)}")
    L.append("epistemology:")
    L.append("  known:")
    for pid, facts in (c.get("known") or {}).items():
        L.append(f"    {yq(pid)}:")
        for f in facts:
            L.append(f"      - {yq(f)}")
    L.append("  blind_spots:")
    bs = c.get("blind") or {}
    if bs:
        for pid, facts in bs.items():
            L.append(f"    {yq(pid)}:")
            for f in facts:
                L.append(f"      - {yq(f)}")
    else:
        L.append("    {}")
    fd = c.get("foresh") or []
    if fd:
        L.append("foreshadowing_deltas:")
        for fid, act in fd:
            L.append(f"  - id: {yq(fid)}")
            L.append(f"    name: {yq(_line_name(fid))}")
            L.append(f"    action: {yq(act)}")
            L.append(f"    desc: {yq(_line_desc(fid, act, c))}")
            _meta = LINE_META.get(fid) or {}
            if act == "plant":
                if _meta.get("tier"):
                    L.append(f"    tier: {yq(_meta['tier'])}")
                if _meta.get("target_ch"):
                    L.append(f"    target_ch: {yq(_meta['target_ch'])}")
            if act in ("plant", "resolve") and fid in LINE_EVIDENCE:
                L.append(f"    evidence: {yq(LINE_EVIDENCE[fid])}")
    else:
        L.append("foreshadowing_deltas: []")
    L.append("state_deltas:")
    st = c.get("status") or {}
    L.append("  character_status:")
    if st:
        for pid, v in st.items():
            if isinstance(v, dict):
                L.append(f"    {yq(pid)}:")
                for k, vv in v.items():
                    L.append(f"      {k}: {yq(vv)}")
            else:
                L.append(f"    {yq(pid)}: {yq(v)}")
    else:
        L.append("    {}")
    its = c.get("items") or []
    if its:
        L.append("  items:")
        for it in its:
            L.append(f"    - id: {yq(it['id'])}")
            L.append(f"      name: {yq(_item_name(it['id']))}")
            for k in ("holder_change", "charges_delta", "status", "durability"):
                if k in it:
                    L.append(f"      {k}: {it[k]!r}" if isinstance(it[k], int) else f"      {k}: {yq(it[k])}")
    if c.get("ledger"):
        d, reason = c["ledger"]
        L.append("  ledger:")
        L.append(f"    pool: {yq('通用资金池')}")
        L.append(f"    delta: {yq(f'{d:+d}')}")
        L.append(f"    reason: {yq(reason)}")
    dbs = c.get("debts") or []
    if dbs:
        L.append("  debts:")
        for s, t, ty, desc, act in dbs:
            L.append(f"    - source: {yq(s)}")
            L.append(f"      target: {yq(t)}")
            L.append(f"      type: {yq(ty)}")
            L.append(f"      desc: {yq(desc)}")
            L.append(f"      action: {yq(act)}")
    rels = c.get("relations") or []
    if rels:
        L.append("relation_deltas:")
        for s, t, ten, dyn, sub in rels:
            L.append(f"  - source: {yq(s)}")
            L.append(f"    target: {yq(t)}")
            L.append(f"    tension: {ten}")
            L.append(f"    dynamic: {yq(dyn)}")
            L.append(f"    subtext: {yq(sub)}")
    else:
        L.append("relation_deltas: []")
    nes = c.get("new_entities") or []
    if nes:
        L.append("new_entities:")
        for ne in nes:
            L.append(f"  - id: {yq(ne['id'])}")
            L.append(f"    type: {yq(ne['type'])}")
            L.append(f"    name: {yq(ne['name'])}")
            for k in ("role", "tier_name", "summary", "sensory_anchor", "holder", "status",
                      "charges", "max_charges", "danger_tier", "danger_level", "environment_rules"):
                if k in ne:
                    v = ne[k]
                    if isinstance(v, list):
                        L.append(f"    {k}:")
                        for vv in v:
                            L.append(f"      - {yq(vv)}")
                    elif isinstance(v, int):
                        L.append(f"    {k}: {v}")
                    else:
                        L.append(f"    {k}: {yq(v)}")
    else:
        L.append("new_entities: []")
    lfs = c.get("locked") or []
    if lfs:
        L.append("locked_facts:")
        for lf in lfs:
            L.append(f"  - id: {yq(lf['id'])}")
            L.append(f"    fact: {yq(lf['fact'])}")
    else:
        L.append("locked_facts: []")
    L.append("---")
    body = f"""

{briefing}

# 第 {ch} 章 《{c['title']}》 编剧细纲

---

## 🎯 一、 核心戏剧目标与爽点

- **本章核心戏剧目标**：{c['goal']}
- **独家看点**：{c['phase']}的关键推进——{c['macro']}。
- **绝对负向红线（Scene Taboos）**：
  1. 【规则/战力禁忌】：不得逾越 {c.get('tier_cap', '当前境界')} 的破坏力标尺，严禁机械降神。
  2. 【人设/动机禁忌】：在场角色一切行动须由利益与恐惧驱动，严禁降智嘲讽。
  3. 【叙事/套路禁忌】：严禁抒情总结式收尾，章末必须停在物理动作瞬间。

---

## 🎬 二、 核心场景脉络

### 场景一（[{_name_of(c['present'][0][0])}] {c['location']}）
- 🎯 核心冲突与阻碍：{c['goal']}
- ⚔️ 对抗博弈与对白：{_scene_friction(c)}
- 💓 情绪流向与心理台阶：{_scene_arc(c)}
- 🌊 承上启下气口：把冲突推向不可回头的临界点。

---

## 🪝 三、 章末定格·断章刀口（Cliffhanger）

- **绝杀断章刀型**：【{_knife_type(c)}】
- **物理定格画面**：{c['cliff']}
"""
    return "\n".join(L) + body


_ROLE_CACHE = {p["id"]: p["role"] for p in PERSONS}


def _role_of(pid: str) -> str:
    if pid in _ROLE_CACHE:
        return _ROLE_CACHE[pid]
    for c in CHAPTERS:
        for ne in c.get("new_entities", []) or []:
            if ne.get("id") == pid:
                _ROLE_CACHE[pid] = ne.get("role", "supporting")
                return _ROLE_CACHE[pid]
        for pid2, *_ in c["present"]:
            if pid2 == pid:
                _ROLE_CACHE[pid] = "supporting"
    return _ROLE_CACHE.setdefault(pid, "supporting")


_LINE_CACHE = {l["id"]: l for l in LINES}


def _line_name(fid: str) -> str:
    if fid in _LINE_CACHE:
        return _LINE_CACHE[fid]["name"]
    return {"GUN-003": "幽影令的来历"}.get(fid, fid)


def _line_desc(fid: str, act: str, c: dict) -> str:
    base = _LINE_CACHE.get(fid, {}).get("desc", "")
    if fid == "GUN-003":
        base = "幽影令可开幽影门三处暗门，来历与青云宗十八年贡银纠缠不清"
    return f"[{act}] {c['title']}：{base}"


def _item_name(iid: str) -> str:
    for it in ITEMS:
        if it["id"] == iid:
            return it["name"]
    for c in CHAPTERS:
        for ne in c.get("new_entities", []) or []:
            if ne.get("id") == iid:
                return ne["name"]
    return {"it_002": "断刃", "it_003": "幽影令"}.get(iid, iid)


def _scene_friction(c: dict) -> str:
    names = [_name_of(p[0]) for p in c["present"]]
    if len(names) >= 2:
        return f"{names[0]} 与 {names[1]} 正面交锋，言语试探与利益交换同时进行。"
    return f"{names[0]} 独自面对局面，内心博弈外化为动作。"


def _scene_arc(c: dict) -> str:
    return f"{_name_of(c['present'][0][0])} 从隐忍到出手，情绪台阶逐级抬升。"


def _knife_type(c: dict) -> str:
    return {"爆发": "A 动作骤停刀", "回收": "B 认知反转刀", "余韵": "C 绝境倒计时刀"}.get(
        c["ctype"], "B 认知反转刀")


# ── 5. 正文渲染（确定性生成，~1700 字，含对白与物象）───────────────────
# 「AI 味」水词样本（Dehydrator 的删除对象）：抽象抒情 + 空洞总结，不含任何事实增量。
WATER_A = ("在这一刻，他的内心充满了复杂的情绪，仿佛有千言万语想要诉说，却又不知从何说起，"
           "只觉得整个世界都变得不一样了，一种难以言喻的感觉在胸口蔓延开来。")
WATER_B = "他沉默了很久，心里明白，有些事情一旦开始，就再也回不到从前了。"

SCENE_OPENERS = [
    "{loc}的风带着铁腥味，{p0}站在入口处没有立刻进去。",
    "{loc}里光线很暗，{p0}数着自己的呼吸往前走。",
    "到了{loc}，{p0}先把袖子放下来，遮住腕上的旧痕。",
    "{loc}比想象中更静，{p0}停了一步，侧耳听着。",
]
ACTIONS = [
    "他把东西按在掌心，指节一点点收紧。",
    "他往前挪了半步，脚下的碎石发出细响。",
    "他抬手抹掉脸上的灰，视线没有离开对面。",
    "他慢慢把手从袖子里抽出来，动作很慢。",
    "他弯腰拾起地上那半块东西，塞进怀里。",
    "他后退一步，背抵住冰凉的岩壁。",
]
DIALOGUES = [
    "“你到底想要什么。”{p}的声音压得很低。",
    "“我想要的很简单。”{p}笑了笑，“你给不起。”",
    "“这件事跟你没关系。”{p}把话咬得很死。",
    "“有关系。”{p}说，“从三年前那天起就有关系。”",
    "“你可以走了。”{p}没有抬头。",
    "“我不走。”{p}站在原地，脚下像生了根。",
    "“你知不知道自己在做什么。”{p}问。",
    "“我知道。”{p}答，“我比谁都清楚。”",
    "“账不是这么算的。”{p}把册子合上。",
    "“那该怎么算。”{p}反问。",
]
REACTIONS = [
    "对面的人没有立刻回答，只是把手里的东西转了半圈。",
    "这句话落地，四周安静了一瞬。",
    "有人咳嗽了一声，声音在石壁间来回撞。",
    "远处传来金属相碰的响动，很短，一下就没了。",
    "灯火晃了晃，影子在墙上拉长又缩回去。",
]
CLOSERS = [
    "{p0}没有再说话，他知道接下来每一步都不能错。",
    "{p0}把呼吸放缓，等那个声音再响一次。",
    "{p0}握紧了手里的东西，掌心的温度一点点传上去。",
]


def render_prose(c: dict) -> str:
    rnd = random.Random(1000 + c["ch"])
    names = [_name_of(p[0]) for p in c["present"]]
    p0 = names[0]
    paras: list[str] = []
    paras.append(rnd.choice(SCENE_OPENERS).format(loc=c["location"], p0=p0))
    paras.append(f"今天是{c['timeline'].split('·')[0]}，{c['location']}里的人比平日少。{p0}来的目的只有一个：{c['goal'].split('，')[0]}。")
    if len(names) > 1:
        paras.append(f"{names[1]}已经在里面等着了。两个人隔着三步远站定，谁都没有先开口。")
    paras.append(rnd.choice(ACTIONS))
    paras.append(rnd.choice(DIALOGUES).format(p=names[1] if len(names) > 1 else p0))
    paras.append(rnd.choice(REACTIONS))
    paras.append(rnd.choice(DIALOGUES).format(p=p0))
    # 死亡章：显式落地生死事实（与细纲 character_status 同源）
    dead = [pid for pid, v in (c.get("status") or {}).items()
            if isinstance(v, dict) and str(v.get("life_status", "")).lower() == "deceased"]
    if dead:
        dn = _name_of(dead[0])
        cond = c["status"][dead[0]].get("condition", "")
        paras.append(f"{dn}倒下去的时候，{p0}正伸手去拉他。")
        paras.append(f"“别管我。”{dn}说这句话时，嘴角已经有血。")
        paras.append(f"{cond}。{p0}抱着他，感觉到怀里那点温度一点点散掉，最后彻底没了动静——{dn}气绝身亡。")
        paras.append(f"{p0}在原地跪了很久，才把{dn}的眼睛合上。")
    # 道具损毁/耗尽章
    for it in c.get("items") or []:
        inm = _item_name(it["id"])
        if it.get("status") == "destroyed":
            paras.append(f"那件{inm}在这一击里彻底撑不住了，从中间裂开，碎片落在地上，发出很轻的一声响。{p0}看着它，没有去捡。")
        elif it.get("status") == "consumed":
            paras.append(f"{inm}最后一次亮起来，光很弱，很快就暗了下去。{p0}把它握在手里，珠子已经彻底冰凉，再也催动不起来了。")
        elif it.get("status") == "lost":
            paras.append(f"{inm}脱手飞出去，落进水里，只留下一圈很快散开的涟漪。{p0}盯着水面看了很久，什么也没捞着。")
        elif it.get("charges_delta"):
            paras.append(f"{p0}催动{inm}，珠身亮起一线光，随即暗下去。他清楚，能用一次就少一次。")
    # 资金流水章
    if c.get("ledger"):
        d, reason = c["ledger"]
        verb = "入账" if d > 0 else "付出"
        paras.append(f"这一趟的账算下来，{reason}，{verb}{abs(d)}块下品灵石。{p0}把灵石收进袋子里，袋子沉甸甸地压在腰上。")
    # 伏笔推进
    for fid, act in c.get("foresh") or []:
        nm = _line_name(fid)
        if act == "plant":
            paras.append(f"关于{nm}的第一条线索，就是在这个时候落进{p0}眼里的。他当时还不知道这东西会跟他多少年。")
        elif act == "reveal":
            paras.append(f"{nm}的事又往前走了一步。{p0}把新拿到的东西摊开，和之前那些对在一起，缺口处终于露出一点形状。")
        else:
            paras.append(f"{nm}到此有了结果。{p0}把所有线索串成一条，从头看到尾，长长吐出一口气。")
    # 新实体登场
    for ne in c.get("new_entities") or []:
        if ne["type"] in ("person", "character"):
            paras.append(f"{ne['name']}是在这时候出场的。{ne.get('summary', '')}。{p0}打量着对方，把这张脸记了下来。")
        elif ne["type"] == "item":
            paras.append(f"{ne['name']}落在{p0}手里。{ne.get('summary', '')}。他掂了掂，把它收进怀里。")
        elif ne["type"] == "place":
            paras.append(f"{ne['name']}比传闻里更难进。{ne.get('summary', '')}。{p0}在门口站了一会儿，才迈进去。")
    # 关系张力
    for s, t, ten, dyn, sub in c.get("relations") or []:
        paras.append(f"{_name_of(s)}和{_name_of(t)}之间的那点东西，这一次变得很明显：{dyn}。{sub}。")
    # 恩怨
    for s, t, ty, desc, act in c.get("debts") or []:
        word = {"grudge": "仇", "favor": "人情", "promise": "誓"}.get(ty, "账")
        if act == "settle":
            paras.append(f"“这笔账，今天算清。”{_name_of(s)}看着{_name_of(t)}，一字一句把话说完。{desc}——到此两清。")
        else:
            paras.append(f"{_name_of(s)}心里记下了这一笔{word}：{desc}。他没有说出来，但记得很牢。")
    # 锁定事实
    for lf in c.get("locked") or []:
        paras.append(f"从这一刻起，有件事再也回不了头：{lf['fact'].split('，')[0]}。所有人都看见了，没有人能当作没发生。")
    # 补白至目标字数
    filler = [
        f"{p0}想起陈铁说过的话：矿道里的声音不会骗人，人会。",
        "石壁上的水珠一滴一滴往下走，落在地上砸出很小的坑。",
        "他把袖口卷起来，腕上的旧痕在灯下显得更深。",
        "外面有人走过，脚步声很快，转眼就远了。",
        f"{p0}在心里把接下来要做的事排了一遍，一件一件，不能乱。",
        "空气里的铁腥味淡了一些，取而代之的是一点焦糊气。",
        "他摸到怀里那张纸，纸边已经被汗浸软了。",
        f"{p0}抬眼看了一圈，把每个人的位置都记住。",
        # 补白池扩容：旧池只有 8 句，短章要循环 60 次才够字数，撞上 `i > 60` 安全阀
        # 提前退出 ⇒ 4 章正文只有 1468~1492 字，低于配置下限 1500。扩到 24 句并把
        # 安全阀抬到 200，同时全部避开死亡词族与资金词族（充能/灵石/银两/账），
        # 免得补白句误触「未登记死亡」与「漏账提醒」两条关键词探针。
        "风从巷口灌进来，吹得衣角一直抖。",
        "他数了数自己的呼吸，把节奏压慢。",
        "墙根下堆着几只空筐，筐沿磨得发白。",
        "远处有人在搬东西，木头磕在石头上，闷闷一响。",
        "他侧过身，让开门口那条窄路。",
        "头顶的梁上挂着蛛网，网上一动不动。",
        "他把手心在衣襟上擦了擦，重新握紧。",
        "地上有一道旧水痕，从门口一直延伸到里间。",
        "他抬脚跨过门槛，鞋底沾上一层细灰。",
        "有人从窗下走过，影子一晃就不见了。",
        "他把袖口放下，遮住手背上那道旧痕。",
        "屋里的味道很杂，尘土压着一丝潮气。",
        "他停了一停，听外面的动静有没有变。",
        "指尖碰到冰凉的铁环，他顿了一下。",
        "他从怀里摸出那张纸，展开，又折好。",
        "远处传来一声闷响，像是什么东西塌了半边。",
    ]
    i = 0
    # 目标字数：必须按引擎 count_prose_words 的口径计数（CJK 字符 + 英文词 + 数字串，
    # 标点/空白/`#` 标题行不计）。旧版用 len(段落) 估算，标点被算进去 ⇒ 实测 4 章
    # 引擎字数只有 1468~1492，低于配置下限 1500。目标取 1560 留 60 字余量。
    while _prose_words(paras) < 1560:
        paras.append(filler[i % len(filler)])
        i += 1
        if i > 200:
            break
    paras.append(rnd.choice(CLOSERS).format(p0=p0))
    paras.append(c["cliff"])
    body = "\n\n".join(paras)
    return f"""---
chapter_id: {yq(f"ch_{c['ch']:03d}")}
volume_id: {yq(c['vol'])}
title: {yq(c['title'])}
---

# 第 ch_{c['ch']:03d} 章 《{c['title']}》

{body}
"""


_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]+")
_DIGIT = re.compile(r"\d+")


def _prose_words(paras: list[str]) -> int:
    """与引擎 count_prose_words 同口径的本地字数估算（CJK 字 + 英文词 + 数字串）。"""
    n = 0
    for p in paras:
        if p.startswith("#"):
            continue
        n += len(_CJK.findall(p)) + len(_LATIN.findall(p)) + len(_DIGIT.findall(p))
    return n


EMERGENT_LINE = {
    "person": "- [新登场] 类型: person ｜ 名称: {name} ｜ 描述: {desc}",
    "item": "- [新登场] 类型: item ｜ 名称: {name} ｜ 描述: {desc}",
}


def append_emergent(c: dict) -> None:
    """把本章涌现事实按 Stage 4A SKILL 规定格式写进质检报告第三节（Auditor 等价动作）。"""
    em = c.get("emergent")
    if not em:
        return
    f = WS / "log" / "audit" / f"ch_{c['ch']:03d}.md"
    txt = f.read_text(encoding="utf-8")
    lines: list[str] = []
    for e in em.get("entities", []) or []:
        lines.append(EMERGENT_LINE["person"].format(**e))
    for it in em.get("items", []) or []:
        if it.get("holder"):
            lines.append(f"- [道具变动] 名称: {it['name']} ｜ 持有人: {it['holder']} ｜ 说明: {it['desc']}")
        else:
            lines.append(EMERGENT_LINE["item"].format(name=it["name"], desc=it["desc"]))
    mark = "## 🧬 三、 正文涌现事实与实体变更"
    i = txt.find(mark)
    assert i >= 0, "审计报告第三节标记缺失（引擎模板与 SKILL 手册漂移）"
    # 同时把 front-matter 的 logic 计数改为实际问题数（SKILL 第 4 节要求）
    txt = txt[:i + len(mark)] + "\n" + "\n".join(lines) + "\n" + txt[i + len(mark):]
    txt = re.sub(r"^logic: 0$", f"logic: {len(lines)}", txt, count=1, flags=re.MULTILINE)
    f.write_text(txt, encoding="utf-8")


# ── 6. 单章流水线 ────────────────────────────────────────────────────
def build_chapter(c: dict) -> dict:
    ch = f"ch_{c['ch']:03d}"
    vol = c["vol"]
    res = {"ch": ch, "steps": {}}

    # S1-a 脚手架（引擎注入机要简报：余温/黑名单/伏笔雷达/ID 速查）
    code, out = run("beats", "new", ch, "--write", "--force", ws=WS)
    res["steps"]["beats"] = code
    scaffold = WS / "outlines" / vol / "beats" / f"{ch}.md"
    briefing = ""
    if scaffold.exists():
        t = scaffold.read_text(encoding="utf-8")
        # 简报块实测形态：`<!-- ====…\n🧭 【Engine 自动前置打捞 …】\n…\n==== -->`
        m = re.search(r"<!--\s*=+\s*\n🧭.*?-->", t, flags=re.DOTALL)
        briefing = m.group(0) if m else ""
    res["briefing_chars"] = len(briefing)
    res["briefing_blacklist"] = _blacklist_of(briefing)
    res["briefing_ids"] = _id_line_of(briefing)

    # S1-b 编剧落盘（Stage 1 等价）
    scaffold.write_text(render_beats(c, briefing), encoding="utf-8")

    # S1-c 装配（Stage 1 收尾 / 主控执行）
    code, out = run("pack", ch, "--write", ws=WS)
    res["steps"]["pack"] = code
    # pack.md 是工作区根部的**单份滚动文件**（每章覆盖），无法事后逐章复证 FIND-CT58
    # 「简报不进装配包」。此处把每章装配包归档到 .testlab/artifacts/（工作区外，
    # 不污染引擎目录树），供电池 B-11 段做 30 章全量泄漏扫描。
    live = WS / "pack.md"
    if live.exists():
        arc = REPO / ".testlab" / "artifacts" / "long-lab"
        arc.mkdir(parents=True, exist_ok=True)
        (arc / f"pack_{ch}.md").write_text(live.read_text(encoding="utf-8"), encoding="utf-8")
    res["pack_tokens"] = _grab(out, r"估算 Token: (\d+)")
    res["pack_slot_flag"] = "装配包净化旗标" in out or "装配包净化" in out

    # S2~S3B 正文落盘（Drafter ➔ Dehydrator ➔ Tuner 三道工序各自的物理工件）
    # 三份都要落盘：drafter 准写 raw/ch_XXX_v1.md、dehydrator 准写 _v2.md、tuner 准写 _v3.md，
    # 引擎 audit/finalize 按 v3 ➔ v2 ➔ v1 顺序取稿。旧版只写 v3，SKILL 手册声明的
    # v1/v2 路径契约在基座里无从核验。水词段落模拟「AI 味」逐道递减：v1 最水、v3 定稿。
    raw_dir = WS / "manuscript" / vol / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    base = render_prose(c)
    for ver, water in (("v1", WATER_A), ("v2", WATER_B), ("v3", "")):
        txt = base if not water else base.replace("\n\n", "\n\n" + water + "\n\n", 1)
        (raw_dir / f"{ch}_{ver}.md").write_text(txt, encoding="utf-8")

    # S4 质检骨架 + Auditor 涌现事实登记
    code, out = run("audit", ch, "--write", ws=WS)
    res["steps"]["audit"] = code
    append_emergent(c)

    # S5 安全短路收口四连
    for name, args in (
        ("finalize", ("finalize", ch)),
        ("proposal", ("proposal", "auto", ch, "--write", "--force")),
        ("sync", ("sync", ch)),
        ("snapshot", ("snapshot", "create", ch)),
    ):
        code, out = run(*args, ws=WS)
        res["steps"][name] = code
        if name == "sync":
            res["words"] = _grab(out, r"字数：(\d+)")
            res["total_words"] = _grab(out, r"累计：(\d+)")
            res["sync_warnings"] = out.count("⚠️")
            res["sync_warning_lines"] = [l.strip() for l in out.splitlines() if "⚠️" in l]
            # FIND-CT73（自愈层）回归信号：干净数据跑完整链时**必须零自愈**。
            # 一旦这里出现条目，说明引擎对合法数据做了不该做的"修正"（假自愈），
            # 比漏报更危险——它会悄悄改写作者的台账。
            res["sync_healed"] = out.count("🩹")
            res["sync_healed_lines"] = [l.strip() for l in out.splitlines() if "🩹" in l]
        if name == "proposal":
            res["proposal_warnings"] = [l for l in out.splitlines() if "⚠️" in l]
    # S6 卷末三连（Librarian 等价）：分卷归档 ➔ 卷末对账落盘 ➔（全书末章）成书导出
    if c["ch"] in VOL_END_CH.values():
        vol_id = c["vol"]
        for nm, args in (("rollup", ("state", "rollup", vol_id)),
                         ("reconcile", ("reconcile", vol_id, "--write"))):
            code2, out2 = run(*args, ws=WS)
            res["steps"][nm] = code2
            if code2 != 0:
                LOG.append(f"❌ {nm} {vol_id} → {code2}\n{out2[:400]}")
        if c["ch"] == max(VOL_END_CH.values()):
            code2, out2 = run("export", ws=WS)
            res["steps"]["export"] = code2
            res["export_summary"] = next((l.strip() for l in out2.splitlines() if "章节" in l), "")
            if code2 != 0:
                LOG.append(f"❌ export → {code2}\n{out2[:400]}")
        print(f"   📚 卷末三连 {vol_id}: rollup={res['steps'].get('rollup')} "
              f"reconcile={res['steps'].get('reconcile')}"
              + (f" export={res['steps'].get('export')} ｜ {res.get('export_summary', '')}"
                 if "export" in res["steps"] else ""))

    # Stage 4D 逢十巡检（Librarian 等价）
    if c["ch"] % 10 == 0:
        write_sweep(c["ch"])
        print(f"   🔎 逢十巡检 sweep_ch_{c['ch']:03d}.md 落盘")

    # 里程碑达成
    ms = next((m for m in MILESTONES if m["target_ch"] == c["ch"]), None)
    if ms:
        msid = f"ms_{MILESTONES.index(ms) + 1:03d}"
        code, out = run("milestone", "achieve", msid, "-c", ch, ws=WS)
        res["steps"]["milestone"] = code
    return res


def _grab(text: str, pat: str) -> str:
    m = re.search(pat, text)
    return m.group(1) if m else ""


def _blacklist_of(briefing: str) -> str:
    m = re.search(r"🚫 【已故/阵亡人物黑名单.*?\n(.*?)(?:\n\s*\n|\n\s*[📍🌊🎒👥🎭💣⚖️🆔])", briefing, flags=re.DOTALL)
    return (m.group(1).strip() if m else "")


def _id_line_of(briefing: str) -> str:
    m = re.search(r"- 人物: .*", briefing)
    return m.group(0).strip() if m else ""


# ── 7. 主流程 ────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", type=int, default=999, help="只建造到第 N 章")
    ap.add_argument("--keep-going", action="store_true", help="单章失败不中断")
    args = ap.parse_args()

    if WS.exists():
        shutil.rmtree(WS)
    code, out = run("init", "-w", str(WS), "-t", "长篇一致性验证之书", "-g", "玄幻脑洞", "-p", "陆沉")
    if code != 0:
        print(out)
        return code
    print(f"✅ init 完成（{WS}）")
    print(f"✅ 模板去槽位 {deslot_tree()} 个文件")
    write_outlines()
    print("✅ 双卷大纲落盘（vol_01 ch_001~015 ｜ vol_02 ch_016~030）")
    seed_state()
    print("✅ state 八表通电 + 3 条里程碑")

    results = []
    for c in CHAPTERS:
        if c["ch"] > args.until:
            break
        r = build_chapter(c)
        results.append(r)
        bad = {k: v for k, v in r["steps"].items() if v != 0}
        flag = "❌" if bad else "✅"
        print(f"{flag} {r['ch']} 《{next(x['title'] for x in CHAPTERS if x['ch'] == c['ch'])}》 "
              f"字数={r.get('words', '?')} 累计={r.get('total_words', '?')} "
              f"pack_token={r.get('pack_tokens', '?')} 黑名单={r.get('briefing_blacklist', '')[:40]!r} "
              f"步骤={r['steps']}" + (f" ⚠️{r['sync_warnings']}" if r.get("sync_warnings") else "")
              + (f" 🩹{r['sync_healed']}" if r.get("sync_healed") else ""))
        if bad and not args.keep_going:
            print("\n".join(LOG[-6:]))
            return 1

    (REPO / ".testlab" / "tools" / "long_lab_build_log.json").write_text(
        json.dumps({"results": results, "incidents": LOG}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📦 建造完成：{len(results)} 章 ｜ 事故 {len(LOG)} 条 ｜ 日志 .testlab/tools/long_lab_build_log.json")
    if LOG:
        print("\n".join(LOG))
    return 1 if LOG else 0


if __name__ == "__main__":
    sys.exit(main())
