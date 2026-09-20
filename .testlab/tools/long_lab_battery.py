#!/usr/bin/env python3
"""长篇一致性电池（第四轮 · workspace/long-lab 30 章基座）。

三段式：
  A 段【命令面冒烟】26 个子命令逐一通电，记录退出码是否符合 0/1/2/3/4 契约；
  B 段【跨卷不变量】离线读台账/细纲/正文，校验长篇一致性硬指标（生死闸门、
     充能链、资金流水算术、跨卷伏笔闭环、ID 形态、卷末三连、导出完整性）；
  C 段【负向与假阳性】在 /tmp 副本上注入脏数据，验证引擎「拦得住 + 不误伤」。

用法：
    python .testlab/tools/long_lab_battery.py            # 全量
    python .testlab/tools/long_lab_battery.py --only A,B # 只跑指定段
    python .testlab/tools/long_lab_battery.py --keep     # 保留 /tmp 副本供人工复查
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WS = REPO / "workspace" / "long-lab"
STUDIO = [sys.executable, str(REPO / "studio.py")]
TMP = Path("/tmp")

ROWS: list[dict] = []


def rec(sec: str, tid: str, name: str, ok: bool, detail: str = "") -> bool:
    ROWS.append({"sec": sec, "id": tid, "name": name, "ok": ok, "detail": detail[:600]})
    print(f"{'✅' if ok else '❌'} [{sec}/{tid}] {name}" + (f" ｜ {detail[:220]}" if detail else ""))
    return ok


def run(args: list[str], ws: Path, expect: int | None = 0) -> tuple[int, str]:
    cmd = [*STUDIO, *args, "-w", str(ws)]
    p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8")
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def jload(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def copy_ws(tag: str, with_snapshots: bool = False) -> Path:
    dst = TMP / f"ll-{tag}"
    if dst.exists():
        shutil.rmtree(dst)
    ign = None if with_snapshots else shutil.ignore_patterns("snapshots")
    shutil.copytree(WS, dst, ignore=ign)
    return dst


def fm_of(path: Path) -> dict:
    """极简 front-matter 读取（只取本电池需要的键，避免依赖引擎内部解析器）。"""
    t = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", t, flags=re.DOTALL)
    return {"_raw": m.group(1) if m else "", "_full": t}


# ══════════════════ A 段：命令面冒烟 ══════════════════
def section_a() -> None:
    A = "A"
    # A-01 版本与帮助
    p = subprocess.run([*STUDIO, "--version"], cwd=str(REPO), capture_output=True, text=True)
    rec(A, "A-01", "studio --version", p.returncode == 0, p.stdout.strip()[:80])
    p = subprocess.run([*STUDIO, "help"], cwd=str(REPO), capture_output=True, text=True)
    rec(A, "A-02", "studio help（官方接口契约）", p.returncode == 0, f"{len(p.stdout)} 字符")

    # A-03~ 只读态势面
    for tid, args, want in (
        ("A-03", ["status"], 0),
        ("A-04", ["cockpit"], 0),
        ("A-05", ["calendar", "14"], 0),
        ("A-06", ["style"], 0),
        ("A-07", ["config", "guide"], 0),
        ("A-08", ["check"], 0),
        ("A-09", ["check", "--json"], 0),
        ("A-10", ["id", "list"], 0),
        ("A-11", ["id", "list", "person"], 0),
    ):
        code, out = run(args, WS, want)
        rec(A, tid, f"{' '.join(args)}", code == want, f"exit={code} ｜ {out.strip().splitlines()[-1][:120] if out.strip() else ''}")

    # A-12 写操作类命令一律跑在副本上（避免污染 golden 基座）
    wsmoke = copy_ws("smoke")
    code, out = run(["milestone", "add", "--title", "冒烟", "--target-ch", "31"], wsmoke)
    rec(A, "A-12", "milestone add（副本）", code == 0, f"exit={code}")
    code, out = run(["milestone", "achieve", "ms_004", "-c", "ch_030"], wsmoke)
    rec(A, "A-12b", "milestone achieve ms_004（副本）", code in (0, 1), f"exit={code}")

    # A-13 取号器：五类实体
    ids = {}
    for cat in ("person", "item", "location", "gun", "lock"):
        code, out = run(["id", "next", cat], WS)
        m = re.search(r"下一个可用物理 ID: (\S+)", out)
        ids[cat] = m.group(1) if m else "?"
        rec(A, f"A-13.{cat}", f"id next {cat}", code == 0 and m is not None, f"→ {ids[cat]}")
    # 取号必须严格大于台账现存最大号（防撞号扫描含大纲预排）
    persons = jload(WS / "state/persons.json")
    mx = max(int(re.sub(r"\D", "", k)) for k in persons if re.match(r"^p_\d+$", k))
    rec(A, "A-14", "id next person 严格大于台账最大号",
        int(re.sub(r"\D", "", ids["person"])) > mx, f"台账最大 p_{mx:03d} → 建议 {ids['person']}")

    # A-15~ 检索/追踪/打捞/测算（只读）
    for tid, args in (
        ("A-15", ["ask", "沈天阙"]),
        ("A-16", ["ask", "幽影令"]),
        ("A-17", ["ask", "陈铁"]),
        ("A-18", ["trace", "GUN-002"]),
        ("A-19", ["trace", "p_004"]),
        ("A-20", ["trace", "it_001"]),
        ("A-21", ["id", "trace", "p_001"]),
        ("A-22", ["evidence", "candidates", "ch_030"]),
        ("A-23", ["simulate", "impact", "--entity", "p_002", "--action", "retcon"]),
    ):
        code, out = run(args, WS)
        rec(A, tid, f"{' '.join(args)}", code == 0, f"exit={code} ｜ {len(out)} 字符")

    # A-24 参数契约：缺参 → exit 2
    p = subprocess.run([*STUDIO, "beats", "new", "-w", str(WS)], cwd=str(REPO),
                       capture_output=True, text=True)
    rec(A, "A-24", "beats new 缺 chapter_id → exit 2（参数错误契约）", p.returncode == 2, f"exit={p.returncode}")
    # A-25 未知子命令 → exit 2
    p = subprocess.run([*STUDIO, "nosuchcmd", "-w", str(WS)], cwd=str(REPO),
                       capture_output=True, text=True)
    rec(A, "A-25", "未知子命令 → exit 2", p.returncode == 2, f"exit={p.returncode}")
    # A-26 不存在章节 → exit 1（业务阻断，不是 4 系统故障）
    code, out = run(["pack", "ch_999"], WS)
    rec(A, "A-26", "pack ch_999 → exit 1 业务阻断", code == 1, f"exit={code}")
    # A-27 路径穿越（FIND-CT10 回归）
    code, out = run(["pack", "../../etc/passwd"], WS)
    head = out.strip().splitlines()[0][:110] if out.strip() else ""
    rec(A, "A-27", "pack 路径穿越被拦（FIND-CT10 回归）",
        code in (1, 2) and code != 4, f"exit={code} ｜ {head}")
    code, out = run(["sync", "../long-lab"], WS)
    rec(A, "A-27b", "sync 路径穿越被拦", code in (1, 2) and code != 4, f"exit={code}")
    # A-28 工作区不存在 → exit 1（业务阻断 + 可执行方案），不是 3
    #   裁决记录（第四轮）：AGENTS.md 的 exit 3 语义是「运行环境依赖缺失」（Python 版本/
    #   引擎无法 import，studio.py 已在 import 期兜住）；工作区没建档属于**用户可自愈的
    #   业务前置条件**，引擎给出「请先 init」的 💡 方案，正落在 director SKILL 的 Level 1
    #   （exit 1/2 主控自理）。若误报 3，反而会让主控把它当环境问题停机上报。判为设计正确。
    code, out = run(["status"], TMP / "ll-does-not-exist")
    rec(A, "A-28", "工作区未建档 → exit 1 + 可执行方案（Level 1 自愈）",
        code == 1 and "工作区未建档" in out and "init" in out, f"exit={code}")
    # A-28b exit 3 契约仍可达：脱离引擎包的孤儿入口必须报环境错误
    orphan = TMP / "ll-orphan-studio.py"
    orphan.write_text((REPO / "studio.py").read_text(encoding="utf-8"), encoding="utf-8")
    p = subprocess.run([sys.executable, str(orphan), "status"], cwd=str(TMP),
                       capture_output=True, text=True)
    rec(A, "A-28b", "引擎无法 import → exit 3（环境依赖契约可达）",
        p.returncode == 3 and "运行环境异常" in (p.stderr or ""), f"exit={p.returncode}")


# ══════════════════ B 段：跨卷一致性不变量 ══════════════════
def section_b() -> None:
    B = "B"
    st = WS / "state"
    persons = jload(st / "persons.json")
    items = jload(st / "items.json")
    places = jload(st / "places.json")
    lines = jload(st / "lines.json")
    ledger = jload(st / "ledger.json")
    current = jload(st / "current.json")
    # history 台账实测形态是 state/history/ch_XXX.json 逐章文件（不是单一大 JSON）
    history = {f.stem: 1 for f in sorted((st / "history").glob("ch_*.json"))} if (st / "history").exists() else {}
    synopsis = jload(st / "synopsis.json") if (st / "synopsis.json").exists() else {}
    timeline = jload(st / "timeline.json") if (st / "timeline.json").exists() else {}

    beats = sorted(WS.glob("outlines/*/beats/ch_*.md"))
    finals = sorted(WS.glob("manuscript/*/final/ch_*.md"))
    # pack.md 是工作区根部单份滚动文件；逐章归档由 builder 落在 .testlab/artifacts/long-lab/
    packs = sorted((REPO / ".testlab/artifacts/long-lab").glob("pack_ch_*.md"))
    if WS.glob("pack.md"):
        packs = packs + list(WS.glob("pack.md"))

    rec(B, "B-01", "30 章细纲齐备", len(beats) == 30, f"{len(beats)} 份")
    rec(B, "B-02", "30 章定稿齐备", len(finals) == 30, f"{len(finals)} 份")
    rec(B, "B-03", "章号连续 ch_001~ch_030",
        [p.stem for p in finals] == [f"ch_{i:03d}" for i in range(1, 31)],
        f"首尾 {finals[0].stem}…{finals[-1].stem}")

    # B-04 双卷归档：history/synopsis/timeline 三表各 30 条
    for tid, tbl, name in (("B-04a", history, "history"), ("B-04b", synopsis, "synopsis"),
                           ("B-04c", timeline, "timeline")):
        n = len(tbl) if isinstance(tbl, (dict, list)) else 0
        rec(B, tid, f"{name} 台账 30 条", n == 30, f"{n} 条")

    # B-05 生死闸门：已故者不得在卒章之后任何细纲的 present_characters 中出现
    dead = {pid: p for pid, p in persons.items() if str(p.get("life_status", "")).lower() == "deceased"}
    rec(B, "B-05a", "台账登记 2 名已故者（陈铁 ch_008 / 沈天阙 ch_028）", len(dead) == 2,
        ", ".join(f"{k}={v.get('name')}@{v.get('death_ch') or v.get('last_seen_ch')}" for k, v in dead.items()))
    violations = []
    for pid, p in dead.items():
        dch = str(p.get("death_ch") or p.get("last_seen_ch") or "")
        dn = int(re.sub(r"\D", "", dch) or 0)
        for bf in beats:
            cn = int(re.sub(r"\D", "", bf.stem) or 0)
            if cn <= dn:
                continue
            raw = fm_of(bf)["_raw"]
            # present_characters 区块内出现该 ID 或姓名即算违规
            m = re.search(r"present_characters:(.*?)(?=\n[a-z_]+:|\Z)", raw, flags=re.DOTALL)
            blk = m.group(1) if m else ""
            if pid in blk or str(p.get("name", "")) in blk:
                violations.append(f"{bf.stem}:{pid}")
    rec(B, "B-05b", "卒章之后无死者复活（30 章细纲全扫）", not violations, "; ".join(violations) or "0 处违规")

    # B-06 充能链：it_001 九转聚灵珠 5 → 0，且过程不为负
    it1 = items.get("it_001", {})
    charges_seq = []
    cur = int(it1.get("max_charges", it1.get("charges", 0)) or 0)
    for bf in beats:
        raw = fm_of(bf)["_raw"]
        for m in re.finditer(r"charges_delta:\s*(-?\d+)", raw):
            # 仅统计 it_001 条目下的 delta（细纲 items 块内就近匹配）
            seg = raw[max(0, m.start() - 200):m.start()]
            if "it_001" in seg.split("- id:")[-1]:
                cur += int(m.group(1))
                charges_seq.append((bf.stem, cur))
    rec(B, "B-06a", "it_001 终值归零（耗尽链闭合）", int(it1.get("charges", -1)) == 0,
        f"台账 charges={it1.get('charges')} ｜ 状态={it1.get('status')}")
    rec(B, "B-06b", "充能重放全程不为负", all(c >= 0 for _, c in charges_seq),
        " → ".join(f"{s}:{c}" for s, c in charges_seq))

    # B-07 资金流水算术：池余额 == baseline + Σ流水
    pools = ledger.get("pools", {})
    base = ledger.get("pools_baseline", {})
    txs = ledger.get("transactions", [])
    replay = dict(base)
    for t in txs:
        k = t.get("pool") or t.get("pool_name") or "通用资金池"
        replay[k] = replay.get(k, 0) + int(t.get("delta", 0) or 0)
    diff = {k: (pools.get(k), replay.get(k)) for k in set(pools) | set(replay) if pools.get(k) != replay.get(k)}
    rec(B, "B-07a", "池余额 == baseline + Σ流水（独立重放）", not diff, f"流水 {len(txs)} 笔 ｜ 差异 {diff}")
    rec(B, "B-07b", "流水笔数 ≥ 12（剧情编排 12 笔）", len(txs) >= 12, f"{len(txs)} 笔")
    neg = [t for t in txs if int(t.get("delta", 0) or 0) < 0]
    rec(B, "B-07c", "存在支出流水（非只进不出）", len(neg) >= 3, f"支出 {len(neg)} 笔")

    # B-08 跨卷伏笔闭环
    def L(i):
        return lines.get(i, {})
    g2 = L("GUN-002")
    rec(B, "B-08a", "GUN-002 跨卷闭环（vol_01 埋 ➔ vol_02 收）",
        g2.get("planted_ch") == "ch_003" and g2.get("resolved_ch") == "ch_028" and g2.get("status") == "resolved",
        f"planted={g2.get('planted_ch')} resolved={g2.get('resolved_ch')} status={g2.get('status')}")
    rv = g2.get("revealed_chs", [])
    vols = {("vol_01" if int(re.sub(r"\D", "", c)) <= 15 else "vol_02") for c in rv}
    rec(B, "B-08b", "GUN-002 推进章横跨两卷", vols == {"vol_01", "vol_02"},
        f"{len(rv)} 次推进 ｜ 覆盖 {sorted(vols)} ｜ {rv}")
    rec(B, "B-08c", "GUN-002 tier=S 且 evidence 落账", g2.get("tier") == "S" and bool(g2.get("evidence")),
        f"tier={g2.get('tier')} evidence={str(g2.get('evidence'))[:40]}")
    k1 = L("KNO-001")
    rec(B, "B-08d", "KNO-001 跨卷闭环 + 类型未被误记为 GUN",
        k1.get("planted_ch") == "ch_002" and k1.get("resolved_ch") == "ch_026" and k1.get("type") == "KNO",
        f"type={k1.get('type')} planted={k1.get('planted_ch')} resolved={k1.get('resolved_ch')}")
    m1 = L("MIS-001")
    rec(B, "B-08e", "MIS-001 全书未回收（逾期靶点）+ type=MIS",
        m1.get("status") == "active" and not m1.get("resolved_ch") and m1.get("type") == "MIS",
        f"status={m1.get('status')} revealed={m1.get('revealed_chs')}")
    g3 = L("GUN-003")
    rec(B, "B-08f", "GUN-003 书末仍 active 且带 target_ch 排期",
        g3.get("status") == "active" and g3.get("target_ch") == "ch_035",
        f"status={g3.get('status')} target_ch={g3.get('target_ch')} planted={g3.get('planted_ch')}")
    g1 = L("GUN-001")
    rec(B, "B-08g", "GUN-001 卷内闭环（ch_001 埋 ➔ ch_015 收）",
        g1.get("planted_ch") == "ch_001" and g1.get("resolved_ch") == "ch_015",
        f"planted={g1.get('planted_ch')} resolved={g1.get('resolved_ch')}")
    rec(B, "B-08h", "台账伏笔共 5 条（无幽灵线程）", len(lines) == 5, ", ".join(sorted(lines)))

    # B-09 ID 形态与唯一性
    bad_id = [k for k in persons if not re.match(r"^p_\d{3}$", k)]
    rec(B, "B-09a", "人物 ID 全为标准形态 p_XXX（CT63 幽灵已绝迹）", not bad_id, str(bad_id))
    names = [p.get("name") for p in persons.values()]
    dup = {n for n in names if names.count(n) > 1}
    rec(B, "B-09b", "人物姓名无重复占用", not dup, str(dup))
    bad_it = [k for k in items if not re.match(r"^it_\d{3}$", k)]
    rec(B, "B-09c", "道具 ID 全为标准形态 it_XXX", not bad_it, str(bad_it))
    bad_ln = [k for k in lines if not re.match(r"^(GUN|KNO|MIS)-\d{3}$", k)]
    rec(B, "B-09d", "伏笔 ID 全为标准形态 XXX-NNN", not bad_ln, str(bad_ln))
    emergent = {"王五", "阿福", "柳如烟", "幽影使者", "韩拓"}
    got = {p.get("name") for p in persons.values()} & emergent
    rec(B, "B-09e", "5 名涌现/新登场人物全部入册", got == emergent, f"缺 {emergent - got}")

    # B-10 道具生命周期：it_002 断刃 ch_012 损毁；it_003 幽影令 ch_020 涌现 ➔ ch_025 易主 ➔ ch_028 失落
    it2, it3 = items.get("it_002", {}), items.get("it_003", {})
    rec(B, "B-10a", "it_002 断刃 状态 destroyed", it2.get("status") == "destroyed",
        f"status={it2.get('status')} ｜ {it2.get('name')}")
    rec(B, "B-10b", "it_003 幽影令 涌现入册 + 终态 lost",
        it3.get("name") == "幽影令" and it3.get("status") == "lost",
        f"name={it3.get('name')} status={it3.get('status')} holder={it3.get('holder')}")

    # B-11 CT58：装配包不得含编剧简报，细纲必须保留简报
    leak = [p.name for p in packs if "Engine 自动前置打捞" in p.read_text(encoding="utf-8")]
    keep = [p.name for p in beats if "Engine 自动前置打捞" in p.read_text(encoding="utf-8")]
    rec(B, "B-11a", f"装配包零简报泄漏（{len(packs)} 份 pack 全扫）",
        len(packs) >= 30 and not leak, f"{len(packs)} 份 ｜ 泄漏 {leak[:5]}")
    # 装配包必须自完备（Drafter 唯一准读输入）：在场人物/伏笔/道具/上一章尾声四要素齐备
    if packs:
        sample = packs[-1].read_text(encoding="utf-8")
        # Drafter SKILL 契约：装配包只承载「本章法定细纲任务书 + 实时事实」，
        # 伏笔通过细纲 front-matter 的 foreshadowing_deltas 落地（全局伏笔雷达属于
        # 编剧简报，FIND-CT58 已刻意不进包）——故此处校验 SSOT 字段而非「伏笔」字样。
        need = ("present_characters", "epistemology", "foreshadowing_deltas", "断章",
                "道具支配权与充能账本", "角色认知界限", "全书不可推翻法定事实")
        rec(B, "B-11c", "装配包自完备（细纲 SSOT + 道具/认知/锁定事实四要素）",
            all(k in sample for k in need), f"{len(sample)} 字符 ｜ 缺 {[k for k in need if k not in sample]}")
        rec(B, "B-11d", "装配包零槽位残留", "{{slot:" not in sample, "")
    rec(B, "B-11b", "细纲保留简报（供编剧追溯）", len(keep) == 30, f"{len(keep)}/30")

    # B-12 字数与节奏
    wc = {}
    for f in finals:
        t = f.read_text(encoding="utf-8")
        body = re.sub(r"^---\s*\n.*?\n---\s*", "", t, flags=re.DOTALL)
        body = "\n".join(l for l in body.splitlines() if not l.startswith("#"))
        cjk = len(re.findall(r"[\u4e00-\u9fff]", body))
        wc[f.stem] = cjk
    lo, hi = min(wc.values()), max(wc.values())
    # FIND-CT70 定性：这两条校验的是**基座数据形态**（建造器按规划体量生成），
    # 不是引擎的判据——引擎已完全退出字数/占比等文学性判断，短章长章都不告警。
    rec(B, "B-12a", "基座每章正文 ≥1500 字（规划体量事实，非引擎判据）", lo >= 1500, f"区间 {lo}~{hi}")
    rec(B, "B-12b", "基座每章正文 ≤2600 字（规划体量事实，非引擎判据）", hi <= 2600, f"区间 {lo}~{hi}")
    rec(B, "B-12c", "全书累计 ≥45000 字", sum(wc.values()) >= 45000, f"{sum(wc.values())} 字")

    # B-13 时间线单调（同卷内不得倒流）
    def tkey(s: str):
        m = re.search(r"(\d+)年.*?(\d+)月.*?(\d+)日", s)
        if not m:
            return (0, 0, 0)
        return tuple(int(x) for x in m.groups())
    seq, back = [], []
    for bf in beats:
        raw = fm_of(bf)["_raw"]
        m = re.search(r'^timeline:\s*"?(.*?)"?\s*$', raw, flags=re.MULTILINE)
        seq.append((bf.stem, tkey(m.group(1) if m else "")))
    for (c1, t1), (c2, t2) in zip(seq, seq[1:]):
        v1, v2 = "vol_01" if int(c1[3:]) <= 15 else "vol_02", "vol_01" if int(c2[3:]) <= 15 else "vol_02"
        if v1 == v2 and t2 < t1:
            back.append(f"{c1}{t1}→{c2}{t2}")
    rec(B, "B-13", "卷内时间线单调不倒流", not back, "; ".join(back) or "30 章顺序推进")

    # B-14 卷末三连：rollup / reconcile / export
    code, out = run(["state", "rollup", "vol_01"], WS)
    rec(B, "B-14a", "state rollup vol_01", code == 0, f"exit={code}")
    code, out = run(["state", "rollup", "vol_02"], WS)
    rec(B, "B-14b", "state rollup vol_02", code == 0, f"exit={code}")
    # 卷末对账在副本上 --write 落盘后读报告全文校验（报告才是对账的交付物）
    wrec = copy_ws("rec-battery")
    code, out = run(["reconcile", "vol_01", "--write"], wrec)
    r1 = (wrec / "log/review/reconcile_vol_01.md").read_text(encoding="utf-8") if code == 0 else ""
    rec(B, "B-14c", "reconcile vol_01 落盘报告（GUN-001 卷内闭环 + MIS-001 本卷活跃）",
        code == 0 and "GUN-001" in r1 and "MIS-001" in r1 and "本卷埋设、仍活跃" in r1,
        f"exit={code} ｜ {len(r1)} 字符")
    # FIND-CT66 回归：vol_01 报告严禁把后卷才埋的 GUN-003 诬为「前卷遗留」
    rec(B, "B-14c2", "CT66 回归：vol_01 不背后卷伏笔的债",
        "前卷遗留" not in r1 and "范围说明" in r1 and "GUN-003" in r1,
        f"遗留段={'有' if '前卷遗留' in r1 else '无'} 范围说明={'有' if '范围说明' in r1 else '无'}")
    code, out2 = run(["reconcile", "vol_02", "--write"], wrec)
    r2 = (wrec / "log/review/reconcile_vol_02.md").read_text(encoding="utf-8") if code == 0 else ""
    rec(B, "B-14d", "reconcile vol_02：跨卷回收 GUN-002/KNO-001 + 前卷遗留 MIS-001",
        code == 0 and "GUN-002" in r2 and "KNO-001" in r2
        and ("前卷遗留" in r2 and "MIS-001" in r2.split("前卷遗留", 1)[1][:300]),
        f"exit={code} ｜ 已回收段={'GUN-002' in r2}")
    rec(B, "B-14d2", "对账报告含充能耗尽/资金结余/锁定事实三节",
        all(k in r2 for k in ("耗尽道具", "资金池结余", "法定不可逆既定事实")),
        f"it_001 耗尽={'九转聚灵珠' in r2}")
    shutil.rmtree(wrec, ignore_errors=True)

    code, out = run(["export"], WS)
    exp = sorted(WS.glob("export/**/*.md")) + sorted(WS.glob("exports/**/*.md")) + sorted(WS.glob("*成书*.md"))
    rec(B, "B-14e", "export 全书导出成功", code == 0, f"exit={code} ｜ {out.strip().splitlines()[-1][:120] if out.strip() else ''}")
    # 导出物完整性：30 章标题齐备、无简报/无槽位泄漏
    blob = ""
    for f in exp:
        blob += f.read_text(encoding="utf-8")
    if not blob:
        m = re.search(r"(/[^\s]+\.md)", out)
        if m and Path(m.group(1)).exists():
            blob = Path(m.group(1)).read_text(encoding="utf-8")
            exp = [Path(m.group(1))]
    titles = sum(1 for i in range(1, 31) if f"ch_{i:03d}" in blob or f"第 {i} 章" in blob or f"第{i}章" in blob)
    rec(B, "B-14f", "导出物覆盖 30 章", titles >= 30, f"{titles}/30 ｜ 文件 {len(exp)} 个 ｜ {len(blob)} 字符")
    rec(B, "B-14g", "导出物零简报/零槽位泄漏",
        "Engine 自动前置打捞" not in blob and "{{slot:" not in blob,
        f"简报={'有' if 'Engine 自动前置打捞' in blob else '无'} 槽位={'有' if '{{slot:' in blob else '无'}")

    # B-15 里程碑三连达成
    code, out = run(["status"], WS)
    ms_hits = re.findall(r"ms_00\d", out)
    rec(B, "B-15", "里程碑面板可见 3 条 ms_00X", len(set(ms_hits)) >= 3, f"{sorted(set(ms_hits))}")

    # B-16 快照：30 份章节快照 + 可列表
    snaps = sorted((WS / "snapshots").glob("ch_*.zip")) if (WS / "snapshots").exists() else []
    rec(B, "B-16", "30 份章节快照落盘", len(snaps) == 30, f"{len(snaps)} 份")

    # B-17 current.json 收口态
    rec(B, "B-17", "current 收口在 ch_030 / vol_02",
        current.get("current_ch") == "ch_030" and current.get("current_vol") == "vol_02",
        f"{current.get('current_vol')}/{current.get('current_ch')} 累计={current.get('latest_word_count')}")


# ══════════════════ C 段：负向与假阳性（副本）══════════════════
def section_c(keep: bool) -> None:
    C = "C"
    # ── C-01 死者复活：把 ch_008 已卒的陈铁塞进 ch_010 在场人物 ──
    w = copy_ws("revive")
    bf = w / "outlines/vol_01/beats/ch_010.md"
    t = bf.read_text(encoding="utf-8")
    t2 = t.replace('present_characters:\n', 'present_characters:\n  - id: "p_004"\n    name: "陈铁"\n    role: "supporting"\n    want: "复活测试"\n    fear: "无"\n    status_in: "完好"\n', 1)
    assert t2 != t
    bf.write_text(t2, encoding="utf-8")
    code, out = run(["sync", "ch_010", "--force"], w)
    blocked = code == 1 and ("复活" in out or "已故" in out or "阵亡" in out or "死亡" in out)
    rec(C, "C-01", "死者复活被 sync 阻断（exit 1）", blocked, f"exit={code} ｜ {out.strip()[:200]}")
    code2, out2 = run(["check"], w)
    rec(C, "C-01b", "check 同步点名死者复活", code2 == 1 and ("复活" in out2 or "已故" in out2 or "阵亡" in out2),
        f"exit={code2}")

    # ── C-02 充能透支：it_001 已归零后再扣 1 ──
    w = copy_ws("overdraft")
    bf = w / "outlines/vol_01/beats/ch_014.md"
    t = bf.read_text(encoding="utf-8")
    if "items:" in t:
        t2 = t.replace("  items:\n", '  items:\n    - id: "it_001"\n      name: "九转聚灵珠"\n      charges_delta: -3\n', 1)
    else:
        t2 = t.replace("state_deltas:\n", 'state_deltas:\n  items:\n    - id: "it_001"\n      name: "九转聚灵珠"\n      charges_delta: -3\n', 1)
    assert t2 != t
    bf.write_text(t2, encoding="utf-8")
    code, out = run(["sync", "ch_014", "--force"], w)
    it1 = jload(w / "state/items.json").get("it_001", {})
    rec(C, "C-02", "充能透支被拦或告警（不得静默变负）",
        code == 1 or int(it1.get("charges", 0)) >= 0,
        f"exit={code} charges={it1.get('charges')} ｜ 告警={'⚠️' in out}")

    # ── C-03 资金面：巨额透支 / 池名漂移 / 尾随空格自愈（FIND-CT67）──
    w = copy_ws("ledger-od")
    bf = w / "outlines/vol_02/beats/ch_023.md"
    t0 = bf.read_text(encoding="utf-8")
    t2 = t0.replace('delta: "-450"', 'delta: "-999999"', 1)   # 替换而非追加：避免 YAML 重复键
    assert t2 != t0, "ch_023 未找到 ledger delta 注入点"
    bf.write_text(t2, encoding="utf-8")
    code, out = run(["sync", "ch_023", "--force"], w)
    led = jload(w / "state/ledger.json")
    bal = led.get("pools", {}).get("通用资金池")
    rec(C, "C-03a", "巨额透支：不阻断（欠账合法）但 loud warning",
        code == 0 and "转负" in out, f"exit={code} 余额={bal}")
    rec(C, "C-03b", "透支后账目仍可独立重放（baseline + Σ流水）",
        bal == led.get("pools_baseline", {}).get("通用资金池", 0) + sum(
            x.get("delta", 0) for x in led.get("transactions", []) if x.get("pool") == "通用资金池"),
        f"余额={bal}")

    bf = w / "outlines/vol_02/beats/ch_026.md"
    t0 = bf.read_text(encoding="utf-8")
    t2 = t0.replace('pool: "通用资金池"', 'pool: "通用资金池 "', 1)   # 尾随空格
    assert t2 != t0
    bf.write_text(t2, encoding="utf-8")
    code, out = run(["sync", "ch_026", "--force"], w)
    pools = jload(w / "state/ledger.json").get("pools", {})
    rec(C, "C-03c", "池名尾随空格自愈（不劈成两本账、不告警）",
        code == 0 and "通用资金池 " not in pools and "新资金池" not in out, f"pools={list(pools)}")

    bf = w / "outlines/vol_02/beats/ch_029.md"
    t0 = bf.read_text(encoding="utf-8")
    t2 = t0.replace('pool: "通用资金池"', 'pool: "灵石池"', 1)        # 真别名
    assert t2 != t0
    bf.write_text(t2, encoding="utf-8")
    code, out = run(["sync", "ch_029", "--force"], w)
    rec(C, "C-03d", "池名真别名 → 提醒作者核对（经济不被静默劈开）",
        code == 0 and "新资金池" in out, f"exit={code}")

    # 流水溯源：每笔必须带 chapter/pool/delta/reason 四要素
    txs = jload(WS / "state/ledger.json").get("transactions", [])
    bad = [x for x in txs if not all(k in x and x[k] not in ("", None) for k in ("chapter", "pool", "delta"))]
    rec(C, "C-03e", "12 笔流水四要素齐备（chapter/pool/delta/reason 可溯源）",
        not bad and all(x.get("reason") for x in txs), f"{len(txs)} 笔 ｜ 残缺 {len(bad)}")

    # ── C-04 CT63 假阳性回归：真涌现行 + 保留模板注释 ⇒ 只收真的（注释态机不误伤）──
    w = copy_ws("ct63")
    code, out = run(["audit", "ch_011", "--write", "--force"], w)
    af = w / "log/audit/ch_011.md"
    t0 = af.read_text(encoding="utf-8")
    mark = "## 🧬 三、 正文涌现事实与实体变更"
    i = t0.find(mark)
    real = ("\n- [新登场] 类型: person ｜ 名称: 铁面判官 ｜ 描述: 幽影城税关主审，冷面无私\n"
            "- [阵亡/死亡] 角色: 赵三 ｜ 说明: 被税关判官当场格杀\n"
            "- [道具变动] 名称: 断刃 ｜ 状态: destroyed ｜ 说明: 税关前折断\n")
    af.write_text(t0[:i + len(mark)] + real + t0[i + len(mark):], encoding="utf-8")
    code, out = run(["proposal", "auto", "ch_011", "--write", "--force"], w)
    harvested = "涌现事实: 死亡 1 / 新实体 1 / 道具变动 1" in out
    rec(C, "C-04a", "真涌现事实被收割（死亡1/新实体1/道具1）", code == 0 and harvested,
        f"exit={code} ｜ {[l.strip() for l in out.splitlines() if '涌现事实' in l]}")
    beats_t = (w / "outlines/vol_01/beats/ch_011.md").read_text(encoding="utf-8")
    m = re.search(r'- id: "(p_\d+)"\s*\n\s*type: "person"\s*\n\s*name: "铁面判官"', beats_t)
    rec(C, "C-04b", "涌现人物回填细纲并由引擎发号（标准 p_XXX）", m is not None,
        f"分配到 {m.group(1) if m else '未回填'}")
    dead_in_beats = re.search(r'p_005:\s*\n\s*life_status: "deceased"', beats_t)
    rec(C, "C-04c", "涌现死亡并入既有 character_status（CT62 合并路径）", dead_in_beats is not None, "")
    persons_before = {k: v.get("name") for k, v in jload(w / "state/persons.json").items()}
    ghosts = [k for k in persons_before if not re.match(r"^p_\d{3}$", k)]
    rec(C, "C-04d", "模板示例零幽灵（CT63 修复生效）", not ghosts, str(ghosts))
    code, out = run(["sync", "ch_011", "--force"], w)
    persons = jload(w / "state/persons.json")
    rec(C, "C-04e", "sync 后涌现人物入册 + 赵三转 deceased",
        code == 0 and any(p.get("name") == "铁面判官" for p in persons.values())
        and persons.get("p_005", {}).get("life_status") == "deceased",
        f"exit={code} 人物数 {len(persons_before)}→{len(persons)}")
    items = jload(w / "state/items.json")
    rec(C, "C-04f", "涌现道具变动落账（断刃 destroyed）",
        items.get("it_002", {}).get("status") == "destroyed", f"status={items.get('it_002', {}).get('status')}")

    # ── C-05 CT63 假阳性回归 2：Auditor 照抄范例到注释外 ⇒ 零入账 + 一条提醒 ──
    w = copy_ws("ct63b")
    code, out = run(["audit", "ch_012", "--write", "--force"], w)
    af = w / "log/audit/ch_012.md"
    t = af.read_text(encoding="utf-8")
    # 删掉模板注释，把范例五行原样贴到注释外（模型照抄手册范例的高频形态）
    t2 = re.sub(r"<!--.*?-->", """- [阵亡/死亡] 角色: 阵亡角色名 ｜ 说明: 死亡原因/场景
- [新登场] 类型: person ｜ 名称: 新角色名 ｜ 描述: 角色定位与特征
- [新登场] 类型: item ｜ 名称: 新道具名 ｜ 描述: 道具来源与属性
- [道具变动] 名称: 道具名 ｜ 状态: destroyed/consumed/lost/active ｜ 说明: 变动原因
- [道具变动] 名称: 道具名 ｜ 持有人: 获得者角色名 ｜ 说明: 归属确认""", t, flags=re.DOTALL)
    af.write_text(t2, encoding="utf-8")
    before = set(jload(w / "state/persons.json")) | set(jload(w / "state/items.json"))
    code, out = run(["proposal", "auto", "ch_012", "--write", "--force"], w)
    after = set(jload(w / "state/persons.json")) | set(jload(w / "state/items.json"))
    prop = jload(w / "state/inbox/proposal_ch_012.json")
    warned = any("CT63" in str(x) or "模板示例" in str(x) for x in (prop.get("warnings") or [])) or "模板示例" in out
    rec(C, "C-05a", "照抄范例零入账（无幽灵实体）", not (after - before), f"新增 {sorted(after - before)}")
    rec(C, "C-05b", "照抄范例给出可忽略提醒", warned, f"warnings={prop.get('warnings')}")

    # ── C-06 CT64：非契约 action 值 ──
    w = copy_ws("ct64")
    bf = w / "outlines/vol_01/beats/ch_013.md"
    t = bf.read_text(encoding="utf-8")
    t2 = t.replace('action: "reveal"', 'action: "推进"', 1)
    if t2 == t:
        t2 = t.replace("foreshadowing_deltas: []", 'foreshadowing_deltas:\n  - id: "GUN-001"\n    name: "矿脉深处的上古剑碑"\n    action: "推进"\n    desc: "中文 action 归一测试"', 1)
    assert t2 != t
    bf.write_text(t2, encoding="utf-8")
    code, out = run(["sync", "ch_013", "--force"], w)
    l = jload(w / "state/lines.json").get("GUN-001", {})
    rec(C, "C-06a", "中文 action「推进」归一为 reveal 并落账",
        code == 0 and "ch_013" in (l.get("revealed_chs") or []),
        f"exit={code} revealed_chs={l.get('revealed_chs')}")

    bf = w / "outlines/vol_01/beats/ch_014.md"
    t = bf.read_text(encoding="utf-8")
    t2 = t.replace("foreshadowing_deltas: []", 'foreshadowing_deltas:\n  - id: "GUN-001"\n    name: "矿脉深处的上古剑碑"\n    action: "乱写一个"\n    desc: "非法枚举测试"', 1)
    if t2 == t:
        t2 = t.replace('action: "reveal"', 'action: "乱写一个"', 1)
    assert t2 != t
    bf.write_text(t2, encoding="utf-8")
    code, out = run(["sync", "ch_014", "--force"], w)
    rec(C, "C-06b", "非法 action 值 loud warning（不再静默吞掉）",
        "乱写一个" in out or "法定枚举" in out, f"exit={code} ｜ 命中告警={'法定枚举' in out}")

    # 未埋先推
    bf = w / "outlines/vol_02/beats/ch_017.md"
    t = bf.read_text(encoding="utf-8")
    t2 = t.replace("foreshadowing_deltas: []", 'foreshadowing_deltas:\n  - id: "GUN-009"\n    name: "未埋先推测试线"\n    action: "reveal"\n    desc: "时序事故靶点"', 1)
    if t2 == t:
        t2 = t.replace('action: "reveal"', 'action: "reveal"', 1)  # no-op 保底
        t2 = re.sub(r'(foreshadowing_deltas:\n(?:.*\n)*?)',
                    r'\1  - id: "GUN-009"\n    name: "未埋先推测试线"\n    action: "reveal"\n    desc: "时序事故靶点"\n', t, count=1)
    assert t2 != t
    bf.write_text(t2, encoding="utf-8")
    code, out = run(["sync", "ch_017", "--force"], w)
    rec(C, "C-06c", "未埋先推 → 告警（planted_ch 为空）", "尚未埋设" in out, f"exit={code} ｜ {'尚未埋设' in out}")

    # 重复回收
    bf = w / "outlines/vol_02/beats/ch_027.md"
    t = bf.read_text(encoding="utf-8")
    t2 = re.sub(r'(foreshadowing_deltas:\n(?:.*\n)*?)',
                r'\1  - id: "KNO-001"\n    name: "沈天阙的真实身份"\n    action: "resolve"\n    desc: "重复回收测试"\n', t, count=1)
    assert t2 != t
    bf.write_text(t2, encoding="utf-8")
    code, out = run(["sync", "ch_027", "--force"], w)
    k1 = jload(w / "state/lines.json").get("KNO-001", {})
    rec(C, "C-06d", "重复回收 → 告警并提示改用 reveal", "重复声明 resolve" in out or "已于" in out,
        f"exit={code} resolved_ch={k1.get('resolved_ch')}")

    # ── C-07 CT65 假阳性回归：上一章正文含槽位 ⇒ 溯源到「上一章正文」而非崩溃 ──
    w = copy_ws("ct65")
    prev = w / "manuscript/vol_01/raw/ch_001_v3.md"
    prev.write_text(prev.read_text(encoding="utf-8") + "\n\n{{slot:foo|bar}} 残留槽位测试\n", encoding="utf-8")
    code, out = run(["pack", "ch_002", "--write"], w)
    rec(C, "C-07", "pack ch_002 不再 UnboundLocalError（CT65 修复）",
        code in (0, 1) and "UnboundLocalError" not in out and "_note_slot" not in out,
        f"exit={code} ｜ 溯源命中={'上一章正文' in out}")

    # ── C-08 sync 幂等/重复入账 ──
    w = copy_ws("sync2")
    code, out = run(["sync", "ch_030"], w)
    rec(C, "C-08a", "已封存章重复 sync → 明确处置（非 4 崩溃）", code in (0, 1), f"exit={code}")
    code, out = run(["sync", "ch_030", "--refresh"], w)
    rec(C, "C-08b", "sync --refresh 纯文笔修订通道", code == 0, f"exit={code}")

    # ── C-09 巡航：越过卷末（大纲无 ch_031）⇒ 卷末刹车而非崩溃 ──
    w = copy_ws("cruise")
    code, out = run(["cruise", "ch_031", "--once"], w)
    rec(C, "C-09", "cruise 越界 → 优雅刹车（exit≤1，非 4）", code in (0, 1),
        f"exit={code} ｜ {out.strip().splitlines()[-1][:120] if out.strip() else ''}")

    # ── C-10 快照时光机：回滚 ch_015 ⇒ 未来文件清除 + 台账回到卷末态 ──
    w = copy_ws("snap", with_snapshots=True)
    snaps = sorted(p.stem for p in (w / "snapshots").glob("ch_015_*.zip"))
    if snaps:
        code, out = run(["snapshot", "rollback", snaps[0]], w)
        cur = jload(w / "state/current.json")
        f_left = sorted(p.stem for p in w.glob("manuscript/*/final/ch_*.md"))
        ok = (code == 0 and cur.get("current_ch") == "ch_015" and len(f_left) == 15
              and (w / "snapshots").glob("pre_rollback_*.zip") is not None)
        rec(C, "C-10", "回滚 ch_015：current/定稿/自动备份三对齐", bool(ok),
            f"exit={code} current={cur.get('current_ch')} 定稿={len(f_left)} 份")
    else:
        rec(C, "C-10", "回滚 ch_015", False, "未找到 ch_015 快照")

    # ── C-11 分卷导出隔离 ──
    w = copy_ws("expvol")
    code, out = run(["export", "--vol", "vol_01"], w)
    rec(C, "C-11", "export --vol vol_01 单卷导出", code == 0, f"exit={code}")

    # ── C-12 卷末对账写入 ──
    w = copy_ws("recw")
    code, out = run(["reconcile", "vol_02", "--write"], w)
    rec(C, "C-12", "reconcile --write 落盘对账报告", code == 0, f"exit={code}")

    # ── C-13/C-14 FIND-CT68（FP-4 裁决落地）：回忆/闪回豁免 ──
    w = copy_ws("flashback")
    inj_ok = ('present_characters:\n  - id: "p_004"\n    name: "陈铁"\n    role: "supporting"\n'
              '    want: "在回忆里把旱烟锅交托出去"\n    fear: "陆沉走岔了路"\n'
              '    status_in: "生前·咳血"\n    appearance: "回忆"\n')
    inj_bad = ('present_characters:\n  - id: "p_004"\n    name: "陈铁"\n    role: "supporting"\n'
               '    want: "无标记复活测试"\n    fear: "无"\n    status_in: "完好"\n')
    bf = w / "outlines/vol_01/beats/ch_012.md"
    t0 = bf.read_text(encoding="utf-8")
    bf.write_text(t0.replace("present_characters:\n", inj_ok, 1), encoding="utf-8")
    bf2 = w / "outlines/vol_01/beats/ch_013.md"
    t1 = bf2.read_text(encoding="utf-8")
    bf2.write_text(t1.replace("present_characters:\n", inj_bad, 1), encoding="utf-8")

    code, out = run(["sync", "ch_012", "--force"], w)
    st_ = jload(w / "state/persons.json")["p_004"]
    rec(C, "C-13", "回忆形态豁免：exit 0 + 可追溯提醒 + 台账生死不变",
        code == 0 and "豁免复活闸门" in out and st_.get("life_status") == "deceased",
        f"exit={code} life_status={st_.get('life_status')}")
    code, out = run(["sync", "ch_013", "--force"], w)
    rec(C, "C-14a", "无豁免标记仍硬阻断（exit 1）", code == 1 and "因果冲突阻断" in out, f"exit={code}")
    rec(C, "C-14b", "阻断方案自带豁免出口（Level 1 可自愈）", "appearance" in out and "回忆" in out, "")
    code, out = run(["check"], w)
    rec(C, "C-14c", "check 同口径：豁免章降级 warning、无标记章仍 error",
        code == 1 and "ch_013" in out and "豁免复活闸门" in out, f"exit={code}")

    # ── C-15/C-16 FN-8 裁决证据：正文层死亡检测保持 warning-only ──
    w = copy_ws("fn8")
    code, out = run(["audit", "ch_008", "--write", "--force"], w)   # 已登记死亡章
    rep = (w / "log/audit/ch_008.md").read_text(encoding="utf-8")
    rec(C, "C-15a", "已登记死亡章：探针不误报（零 🚨）",
        code == 0 and "疑似阵亡" not in rep, f"exit={code}")
    f = w / "manuscript/vol_01/raw/ch_011_v3.md"
    t0 = f.read_text(encoding="utf-8")
    f.write_text(t0.replace("\n\n", "\n\n柳如烟被那一刀穿透胸膛，当场气绝身亡，尸身跌在柜台边上。\n\n", 1), encoding="utf-8")
    code, out = run(["audit", "ch_011", "--write", "--force"], w)
    rep = (w / "log/audit/ch_011.md").read_text(encoding="utf-8")
    rec(C, "C-15b", "未登记死亡：探针点名 + 保持 warning-only（exit 0，不阻断）",
        code == 0 and "柳如烟" in rep and "疑似阵亡" in rep, f"exit={code}")
    # 假阳性回归：非死亡修辞（死寂/该死/生死）不得触发
    f2 = w / "manuscript/vol_01/raw/ch_012_v3.md"
    t2 = f2.read_text(encoding="utf-8")
    f2.write_text(t2.replace("\n\n", "\n\n矿道里一片死寂，苏黎该死地慢了一步，生死只在一瞬。\n\n", 1), encoding="utf-8")
    code, out = run(["audit", "ch_012", "--write", "--force"], w)
    rep2 = (w / "log/audit/ch_012.md").read_text(encoding="utf-8")
    rec(C, "C-16", "非死亡修辞（死寂/该死/生死）不误报为阵亡",
        code == 0 and "疑似阵亡" not in rep2, f"exit={code} ｜ {'疑似阵亡' in rep2}")


    # ══════════════ 第五轮靶点：生死不明第四态 / 引擎退出文学判断 / 判据松绑 / 自愈层 ══════════════

    # ── C-17 无人值守：稿件未就绪时优雅停（不刷 error、不崩溃、报告可解析）──
    w = copy_ws("cruise-wait", with_snapshots=True)
    snaps = sorted(p.stem for p in (w / "snapshots").glob("ch_014_*.zip"))
    if snaps:
        code, out = run(["snapshot", "rollback", snaps[0]], w)
        code2, out2 = run(["cruise", "--once"], w, expect=None)
        tail = [l for l in out2.splitlines() if "巡航报告:" in l]
        rep, rep_ok = None, False
        if tail:
            try:
                rep = json.loads(tail[-1].split("巡航报告:", 1)[1].strip())
                # 无稿件 ⇒ 有计划章但零结果（没带伤入账），且不进 brake/timeout
                rep_ok = (isinstance(rep, dict) and rep.get("planned") == ["ch_015"]
                          and rep.get("results") == [] and rep.get("sealed_total") == 14)
            except Exception as _e:      # noqa: BLE001
                rep_ok = False
        # 无人值守三不原则：不崩溃、不刷 error、不静默（必须给出"等待作者产出"的明话）
        rec(C, "C-17", "无人值守：稿件未就绪时优雅停（exit 0 · 报告可解析 · 明说等待 · 零 error）",
            code2 == 0 and rep_ok and "等待作者产出" in out2
            and "Traceback" not in out2 and "❌" not in out2
            and (w / "log/cruise_report.json").exists(),
            f"rollback={code} cruise={code2} 报告合法={rep_ok} 落盘={(w / 'log/cruise_report.json').exists()}")
    else:
        rec(C, "C-17", "无人值守优雅停", False, "未找到 ch_014 快照")

    # ── C-18 卷末自动刹车：整卷已封存 ⇒ rollup + reconcile + export 三连 ──
    w = copy_ws("vol-brake")
    code, out = run(["cruise", "--vol", "vol_01", "--once"], w, expect=None)
    tail = [l for l in out.splitlines() if "巡航报告" in l]
    brake_ok = False
    if tail:
        try:
            rep = json.loads(tail[-1].split("巡航报告:", 1)[1].strip())
            brake_ok = (rep.get("planned") == [] and isinstance(rep.get("rollup"), dict)
                        and rep.get("rollup", {}).get("volume_id") == "vol_01")
        except Exception:
            brake_ok = False
    rec(C, "C-18", "卷末自动刹车：planned=[] + rollup/reconcile 三连（exit 0）",
        code == 0 and brake_ok and "卷末自动刹车" in out, f"exit={code} brake_ok={brake_ok}")

    # ── C-19 生死不明第四态 unknown：不进黑名单、立悬念账、可正常登场 ──
    w = copy_ws("unknown-life")
    pf = w / "state/persons.json"
    pdb = jload(pf)
    pdb["p_008"]["life_status"] = "unknown"
    pf.write_text(json.dumps(pdb, ensure_ascii=False, indent=2), encoding="utf-8")
    code, out = run(["check"], w, expect=None)
    rec(C, "C-19a", "unknown 是法定枚举：全书体检 exit 0（不再报枚举越界）",
        code == 0 and "unknown" not in out, f"exit={code}")
    bf = w / "outlines/vol_02/beats/ch_025.md"
    if bf.exists():
        bf.unlink()
    code, out = run(["beats", "new", "ch_025", "--write"], w, expect=None)
    beats_t = bf.read_text(encoding="utf-8") if bf.exists() else ""
    # 黑名单段落 = 「已故/阵亡人物黑名单」到下一个板块（❓ 悬念账 / 💣 伏笔雷达）为止
    _blk_black = re.split(r"❓|💣", beats_t.split("已故/阵亡人物黑名单", 1)[-1])[0] if "已故/阵亡人物黑名单" in beats_t else ""
    rec(C, "C-19b", "unknown 角色不进已故黑名单（生死不明 ≠ 死亡）",
        code == 0 and "幽影使者" not in _blk_black, f"exit={code} 黑名单段={_blk_black.strip()[:60]!r}")
    rec(C, "C-19c", "简报立「❓ 生死不明人物悬念账」并禁止擅自坐实生死",
        "生死不明人物悬念账" in beats_t and "严禁在正文里擅自坐实" in beats_t, "")
    rec(C, "C-19d", "unknown 角色仍在在场候选中（可正常登场）",
        "幽影使者" in beats_t.split("在场人物速查候选", 1)[-1].split("🎭", 1)[0], "")
    # 中文同义写法归一 + 悬置态收束为 alive
    pdb["p_008"]["life_status"] = "生死不知"
    pf.write_text(json.dumps(pdb, ensure_ascii=False, indent=2), encoding="utf-8")
    code, out = run(["sync", "ch_024", "--force"], w, expect=None)
    st8 = jload(w / "state/persons.json")["p_008"]
    rec(C, "C-19e", "中文「生死不知」自动归一为 unknown（🩹 留痕）",
        code == 0 and st8.get("life_status") == "unknown" and "🩹" in out,
        f"exit={code} life_status={st8.get('life_status')}")

    # ── C-20 引擎退出文学性判断：无对白占比、无体量分档、短章不告警 ──
    w = copy_ws("no-literary")
    code, out = run(["check", "ch_011"], w, expect=None)
    rec(C, "C-20a", "对白占比探针已退役（体检零提及）",
        code == 0 and "对白占比" not in out and "dialogue" not in out, f"exit={code}")
    code, out = run(["audit", "ch_011", "--write", "--force"], w, expect=None)
    rep = (w / "log/audit/ch_011.md").read_text(encoding="utf-8")
    rec(C, "C-20b", "审计报告只做字数计量（无「参考区间/达标线」等评价语）",
        code == 0 and "参考区间" not in rep and "words_range" not in rep, f"exit={code}")
    # 极短章（200 字）：数据完整（非空）即合法，引擎不评判长短
    for v in ("v1", "v2", "v3"):
        f = w / f"manuscript/vol_01/raw/ch_011_{v}.md"
        if f.exists():
            head = f.read_text(encoding="utf-8").split("\n\n")
            f.write_text(head[0] + "\n\n" + "矿道深处，风停了。陆沉把断刃插回鞘里，一句话也没说。" * 8, encoding="utf-8")
    code, out = run(["finalize", "ch_011"], w, expect=None)
    code2, out2 = run(["sync", "ch_011", "--force"], w, expect=None)
    code3, out3 = run(["check", "ch_011"], w, expect=None)
    rec(C, "C-20c", "200 字短章全链通行（finalize/sync/check 均 exit 0，零体量告警）",
        code == 0 and code2 == 0 and code3 == 0
        and "体量" not in (out + out2 + out3) and "不足标准下限" not in (out + out2 + out3),
        f"finalize={code} sync={code2} check={code3}")

    # ── C-21 判据松绑：台账瑕疵只提醒不阻断，且 sync 自愈补章 ──
    w = copy_ws("loose-check")
    lf = w / "state/lines.json"
    ldb = jload(lf)
    ldb["GUN-001"].pop("planted_ch", None)
    ldb["GUN-002"]["resolved_ch"] = ""          # resolved 却缺回收章
    ldb["GUN-002"]["status"] = "resolved"
    lf.write_text(json.dumps(ldb, ensure_ascii=False, indent=2), encoding="utf-8")
    code, out = run(["check"], w, expect=None)
    rec(C, "C-21a", "选填字段缺漏 ⇒ exit 0 + warning + 🩹 自愈指引（不再阻断）",
        code == 0 and "台账伏笔字段残缺" in out and "🩹" in out, f"exit={code}")
    code, out = run(["sync", "ch_024", "--force"], w, expect=None)
    ldb2 = jload(w / "state/lines.json")
    rec(C, "C-21b", "sync 自愈补齐 planted_ch / resolved_ch 并标注 inferred",
        code == 0 and ldb2["GUN-001"].get("planted_ch") and ldb2["GUN-002"].get("resolved_ch")
        and ldb2["GUN-001"].get("planted_ch_source") == "inferred" and "🩹" in out,
        f"planted={ldb2['GUN-001'].get('planted_ch')} resolved={ldb2['GUN-002'].get('resolved_ch')}")
    code, out = run(["check"], w, expect=None)
    rec(C, "C-21c", "自愈后复检：同类提醒消失（幂等，不重复报警）",
        code == 0 and "台账伏笔字段残缺" not in out, f"exit={code}")

    # ── C-22 撞号自愈：new_entities 占用他人 ID ⇒ 改派新号，原角色分毫不动 ──
    w = copy_ws("id-collision")
    bf = w / "outlines/vol_02/beats/ch_024.md"
    t0 = bf.read_text(encoding="utf-8")
    inj = ('new_entities:\n  - id: "p_010"\n    type: "person"\n    name: "测试新人甲"\n'
           '    role: "supporting"\n    summary: "撞号自愈靶点"\n')
    # 脚手架默认写的是 `new_entities: []`（空列表形态），据此替换；否则整体前插
    if "new_entities: []" in t0:
        t1 = t0.replace("new_entities: []", inj.rstrip("\n"), 1)
    elif "\nnew_entities:\n" in t0:
        t1 = t0.replace("new_entities:\n", inj, 1)
    else:
        t1 = t0.replace("present_characters:\n", inj + "present_characters:\n", 1)
    assert t1 != t0, "ch_024 未找到 new_entities 注入点"
    bf.write_text(t1, encoding="utf-8")
    before = jload(w / "state/persons.json")
    code, out = run(["sync", "ch_024", "--force"], w, expect=None)
    after = jload(w / "state/persons.json")
    new_ids = [k for k, v in after.items() if v.get("name") == "测试新人甲"]
    rec(C, "C-22", "撞号自愈：原「阿福」姓名不变 + 新实体改派新号 + 🩹 留痕",
        code == 0 and after.get("p_010", {}).get("name") == "阿福" and len(new_ids) == 1
        and new_ids[0] != "p_010" and "撞号自愈" in out,
        f"exit={code} p_010={after.get('p_010', {}).get('name')} 新号={new_ids} 人物 {len(before)}→{len(after)}")

    # ── C-23 数值脏值自愈：中文数字解析 / 越界夹取 / 不可解析摘除 ──
    w = copy_ws("num-heal")
    pf = w / "state/persons.json"
    pdb = jload(pf)
    pdb["p_001"]["tier_rank"] = "第三重"
    pdb["p_001"]["injury_level"] = 9
    pdb["p_003"]["renown"] = "abc"
    pf.write_text(json.dumps(pdb, ensure_ascii=False, indent=2), encoding="utf-8")
    itf = w / "state/items.json"
    idb = jload(itf)
    idb["it_001"]["charges"] = "两"
    itf.write_text(json.dumps(idb, ensure_ascii=False, indent=2), encoding="utf-8")
    code, out = run(["sync", "ch_024", "--force"], w, expect=None)
    pdb2 = jload(pf)
    idb2 = jload(itf)
    rec(C, "C-23", "数值自愈：中文数字→int、越界夹取、不可解析摘除（全部 🩹 留痕）",
        code == 0 and pdb2["p_001"].get("tier_rank") == 3 and pdb2["p_001"].get("injury_level") == 5
        and "renown" not in pdb2["p_003"] and idb2["it_001"].get("charges") == 2 and "🩹" in out,
        f"tier_rank={pdb2['p_001'].get('tier_rank')} injury={pdb2['p_001'].get('injury_level')} "
        f"renown={'renown' in pdb2['p_003']} charges={idb2['it_001'].get('charges')}")

    # ── C-24 ID 笔误规范化：P005 ⇒ p_005，不产生幽灵记录 ──
    w = copy_ws("id-typo")
    bf = w / "outlines/vol_02/beats/ch_024.md"
    t0 = bf.read_text(encoding="utf-8")
    t1 = t0.replace("present_characters:\n", 'present_characters:\n  - id: "P005"\n    name: "赵三"\n', 1)
    assert t1 != t0
    bf.write_text(t1, encoding="utf-8")
    code, out = run(["sync", "ch_024", "--force"], w, expect=None)
    pdb2 = jload(w / "state/persons.json")
    ghosts = [k for k in pdb2 if not re.match(r"^p_\d+$", k)]
    rec(C, "C-24", "ID 笔误自愈：P005 归一到 p_005，台账零幽灵键",
        code == 0 and not ghosts and "P005" not in pdb2 and pdb2.get("p_005", {}).get("name") == "赵三",
        f"exit={code} 幽灵键={ghosts}")

    # ── C-25 选填字段最小集：只有 chapter_id/title/present_characters 也能入账 ──
    w = copy_ws("minimal")
    vol_dir = w / "outlines/vol_02/beats"
    (vol_dir / "ch_031.md").write_text(
        "---\nchapter_id: ch_031\nvolume_id: vol_02\ntitle: \"最小集验证章\"\n"
        "present_characters:\n  - id: \"p_001\"\n    name: \"陆沉\"\n---\n\n"
        "# 最小集验证章\n\n（本章细纲只填必填项，其余选填块整段不写。）\n", encoding="utf-8")
    (w / "manuscript/vol_02/raw").mkdir(parents=True, exist_ok=True)
    (w / "manuscript/vol_02/raw/ch_031_v1.md").write_text(
        "---\nchapter_id: ch_031\nvolume_id: vol_02\ntitle: \"最小集验证章\"\n---\n\n"
        + "陆沉把账册合上，灯芯爆了一下。" * 60 + "\n", encoding="utf-8")
    code, out = run(["finalize", "ch_031"], w, expect=None)
    code2, out2 = run(["sync", "ch_031"], w, expect=None)
    code3, out3 = run(["check", "ch_031"], w, expect=None)
    rec(C, "C-25", "选填块全缺 ⇒ finalize/sync/check 全 exit 0（缺字段不报错）",
        code == 0 and code2 == 0 and code3 == 0 and "未声明" not in out3,
        f"finalize={code} sync={code2} check={code3}")

    # ── C-26 幽灵记录清扫：槽位污染条目在 sync 时被自动清除 ──
    w = copy_ws("ghost")
    pf = w / "state/persons.json"
    pdb = jload(pf)
    pdb["{{slot:char_1_id|p_099}}"] = {"id": "{{slot:char_1_id|p_099}}",
                                       "name": "{{slot:char_1_name}}", "role": "supporting"}
    pdb["p_012"] = {"id": "p_012", "name": "{{slot:char_2_name}}", "role": "supporting"}
    pf.write_text(json.dumps(pdb, ensure_ascii=False, indent=2), encoding="utf-8")
    code, out = run(["sync", "ch_024", "--force"], w, expect=None)
    pdb2 = jload(pf)
    rec(C, "C-26", "幽灵清扫：双槽位记录删除、半槽位记录保号改名（不删角色）",
        code == 0 and "{{slot:" not in json.dumps(pdb2, ensure_ascii=False)
        and "p_012" in pdb2 and pdb2["p_012"].get("name") == "未命名人物[p_012]" and "🩹" in out,
        f"exit={code} 残留槽位={'{{slot:' in json.dumps(pdb2, ensure_ascii=False)} p_012={pdb2.get('p_012', {}).get('name')}")

    # ── C-27 假自愈回归：干净数据零自愈动作（引擎不得乱改合法台账）──
    w = copy_ws("clean-heal")
    code, out = run(["sync", "ch_010", "--force"], w, expect=None)
    rec(C, "C-27", "假自愈回归：干净数据重放 ⇒ 零 🩹 动作、台账不变",
        code == 0 and "🩹" not in out, f"exit={code} 🩹={'🩹' in out}")

    if not keep:
        for d in TMP.glob("ll-*"):
            shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="A,B,C")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    secs = {s.strip().upper() for s in a.only.split(",")}
    if "A" in secs:
        print("\n══ A 段：命令面冒烟 ══")
        section_a()
    if "B" in secs:
        print("\n══ B 段：跨卷一致性不变量 ══")
        section_b()
    if "C" in secs:
        print("\n══ C 段：负向与假阳性 ══")
        section_c(a.keep)

    fails = [r for r in ROWS if not r["ok"]]
    print(f"\n{'=' * 70}\n📊 电池汇总：{len(ROWS)} 项 ｜ ✅ {len(ROWS) - len(fails)} ｜ ❌ {len(fails)}")
    for r in fails:
        print(f"   ❌ [{r['sec']}/{r['id']}] {r['name']} ｜ {r['detail'][:200]}")
    (REPO / ".testlab" / "tools" / "long_lab_battery_result.json").write_text(
        json.dumps(ROWS, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
