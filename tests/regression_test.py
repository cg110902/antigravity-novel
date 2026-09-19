#!/usr/bin/env python3
"""Novel Studio 引擎回归测试（端到端 · 无第三方依赖）。

用法：python3 tests/regression_test.py
在临时目录里从 init 起重建一本 4 章测试书，跑通
beats → pack → audit → finalize → proposal → sync → reconcile/rollup/export → cruise → snapshot，
并对 BUGS.md 记录的每个缺陷做定点断言，防止回归。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDIO = ROOT / "studio.py"

PASS: list[str] = []
FAIL: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(f"{label}{(' — ' + detail) if detail and not cond else ''}")
    print(("  ✅ " if cond else "  ❌ ") + label + (f" — {detail}" if detail and not cond else ""))


def run(ws: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(STUDIO), *args, "-w", str(ws)],
        capture_output=True, text=True, cwd=str(ROOT),
    )


def load(ws: Path, rel: str):
    p = ws / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# --------------------------------------------------------------------------- 素材
VOL_OUTLINE = """---
id: "outline-vol_01"
vol: "vol_01"
title: "第1卷：灰烬初燃"
---

# 第1卷

## 📋 分章航标大表

### ch_001: 灰烬打火机
- **核心事件与看点**：沈决被裴照堵住，第一次点燃灰烬打火机。
- **断章刀口**：裴照忘了刚才的事，却看见手背上的编号。

### ch_002: 三分钟的窟窿
- **核心事件与看点**：沈决查证编号来源，发现代价是自己的记忆。
- **断章刀口**：沈决想不起母亲的脸。
"""

BEATS_001 = """---
chapter_id: "ch_001"
volume_id: "vol_01"
title: "灰烬打火机"
chapter_type: "破局"
timeline: "灰烬历七年·初秋·黄昏"
location: "城南拆迁楼·七层"
present_characters:
  - id: "p_001"
    name: "沈决"
    role: "protagonist"
    want: "拖过这个黄昏"
    fear: "被看穿他不懂灰烬"
    status_in: "旧伤未愈"
  - id: "p_002"
    name: "裴照"
    role: "antagonist"
    want: "收缴灰烬"
    fear: "上级发现他私自截留"
    status_in: "盛气凌人"
epistemology:
  known:
    "p_001":
      - "打火机能点燃"
  blind_spots:
    "p_002":
      - "沈决其实是登记在册的清算对象家属，而非组织内应"
foreshadowing_deltas:
  - id: "GUN-001"
    name: "打火机内侧的编号"
    action: "plant"
    desc: "打火机内壁刻着七位编号"
    tier: "A"
    target_ch: "ch_004"
  - id: "MIS-001"
    name: "裴照误判沈决身份"
    action: "plant"
    desc: "裴照认定沈决是内应"
    target_ch: "ch_002"
  - id: "KNO-001"
    name: "灰烬来历的知情差"
    action: "plant"
    desc: "只有极少数人知道灰烬从哪来"
    target_ch: "ch_009"
state_deltas:
  character_status:
    "p_001": "左肩旧伤撕裂"
    "p_002": "丢失三分钟记忆"
  items:
    - id: "it_001"
      name: "灰烬打火机"
      holder_change: "p_001"
      charges_delta: -1
      status: "active"
      durability: "外壳发烫"
  ledger:
    pool: "现金"
    delta: "-200"
    reason: "封口费"
  debts:
    - source: "p_002"
      target: "p_001"
      type: "grudge"
      desc: "裴照手背被烙下编号"
      action: "record"
relation_deltas:
  - source: "p_001"
    target: "p_002"
    tension: 75
    dynamic: "猎物与猎手"
    subtext: "他怕的是被看穿"
new_entities:
  - id: "it_001"
    type: "item"
    name: "灰烬打火机"
    holder: "沈决"
    charges: 3
    status: "active"
    summary: "能焚烧他人三分钟记忆"
  - id: "loc_001"
    type: "place"
    name: "城南拆迁楼·七层"
    danger_level: "争端前线"
    sensory_anchor: "水泥灰与风哨声"
    summary: "临时落脚的废弃楼层"
locked_facts:
  - id: "LOCK-001"
    fact: "灰烬打火机每次点燃索取持有者一段记忆"
    domain: "rule"
---

# 第 ch_001 章 编剧细纲

- **本章核心戏剧目标**：
  沈决第一次点燃灰烬打火机。
- **物理定格画面**：
  裴照低头看见手背上的编号。
"""

PROSE_001 = """# 第一章 灰烬打火机

七层没有灯。风从洞口灌进来，水泥灰扑在沈决的睫毛上。

裴照站在唯一的楼梯口。

“交出来。”裴照说，“你知道我说的是哪一件。”

沈决把左手插进口袋，指腹贴住那枚冰凉的金属外壳。

“你毕竟是登记在册的清算对象家属，不是什么内应。”裴照忽然笑了一声。

沈决按下了打火机。灰白的火只有指甲盖那么大。

打火机外壳烫得厉害，内侧那串七位编号硌着他的掌心。

裴照低下头，看见自己手背上多了一道浅褐色的烙痕。

“你是谁？”裴照问。
"""

BEATS_002 = """---
chapter_id: "ch_002"
volume_id: "vol_01"
title: "三分钟的窟窿"
chapter_type: "铺垫"
timeline: "灰烬历七年·初秋·上午"
location: "西巷旧货店"
present_characters:
  - id: "p_001"
    name: "沈决"
    role: "protagonist"
    want: "查出编号来历"
    fear: "代价不可逆"
    status_in: "记忆有缺口"
  - id: "p_003"
    name: "韩姨"
    role: "ally"
    want: "劝沈决离开灰烬"
    fear: "旧事被翻出来"
    status_in: "警惕客套"
foreshadowing_deltas:
  - id: "MIS-001"
    name: "裴照误判沈决身份"
    action: "resolve"
    desc: "误判在此了结"
state_deltas:
  character_status:
    "p_001": "想不起母亲的脸"
  ledger:
    pool: "现金"
    delta: "+500"
    reason: "变卖旧表"
new_entities:
  - id: "p_003"
    type: "character"
    name: "韩姨"
    role: "ally"
    summary: "旧货店老板娘"
    sensory_anchor: "袖口的机油味"
  - id: "loc_002"
    type: "place"
    name: "西巷旧货店"
    danger_level: "安全腹地"
    sensory_anchor: "旧钟表滴答与樟脑味"
    summary: "韩姨的店"
locked_facts: []
---

# 第 ch_002 章 编剧细纲

- **本章核心戏剧目标**：
  沈决求证编号来源。
- **物理定格画面**：
  沈决想不起母亲的脸。
"""

PROSE_002 = """# 第二章 三分钟的窟窿

西巷旧货店的门是往里推的，樟脑味先一步涌出来。

韩姨坐在柜台后面拆一只座钟，袖口上那道机油印子很深。

“东西带来了？”

沈决把一块停了的旧手表放在柜面上，表壳划痕密得像刮过砂纸。

“五百。”韩姨忽然说，“拿着，别再来了。”

沈决走到门口回头，韩姨的手在抖。他忽然发现，自己想不起母亲的脸了。
"""


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="novelstudio_rt_"))
    ws = tmp / "book"
    try:
        print("\n=== 0. 初始化 ===")
        r = run(ws, "init", "-t", "灰烬纪元", "-g", "都市异能", "-p", "沈决")
        check("init 成功", r.returncode == 0, r.stderr[-300:])
        check("init 拒绝重复覆盖", run(ws, "init", "-t", "x", "-g", "y", "-p", "z").returncode == 1)

        (ws / "outlines/vol_01/outline.md").write_text(VOL_OUTLINE, encoding="utf-8")
        (ws / "outlines/vol_01/beats/ch_001.md").write_text(BEATS_001, encoding="utf-8")
        (ws / "manuscript/vol_01/raw/ch_001_v1.md").write_text(PROSE_001, encoding="utf-8")

        print("\n=== 1. ch_001 全链路 ===")
        check("pack 装配", run(ws, "pack", "ch_001", "--write").returncode == 0)
        r = run(ws, "audit", "ch_001", "--write")
        check("audit 生成", r.returncode == 0)

        # BUG#4：首次登场角色本人泄密 → 必须当场判为确认级（而非疑似）
        audit_txt = (ws / "log/audit/ch_001.md").read_text(encoding="utf-8")
        check("BUG#4 首登场角色泄密即时判定为确认级",
              "确认级角色透视泄露" in audit_txt,
              f"实得: {[l for l in audit_txt.splitlines() if '认知盲区' in l]}")

        check("finalize", run(ws, "finalize", "ch_001").returncode == 0)
        check("sync", run(ws, "sync", "ch_001").returncode == 0)

        items = load(ws, "state/items.json")
        check("充能首次扣减正确 (3→2)", items["it_001"]["charges"] == 2, str(items["it_001"]["charges"]))

        # BUG#2：伏笔分类按 ID 前缀/显式字段
        lines = load(ws, "state/lines.json")
        check("BUG#2 GUN-001 type=GUN", lines["GUN-001"]["type"] == "GUN", lines["GUN-001"]["type"])
        check("BUG#2 MIS-001 type=MIS", lines["MIS-001"]["type"] == "MIS", lines["MIS-001"]["type"])
        check("BUG#2 KNO-001 type=KNO", lines["KNO-001"]["type"] == "KNO", lines["KNO-001"]["type"])

        print("\n=== 2. 幂等与重放 ===")
        r = run(ws, "sync", "ch_001")
        check("同稿重复 sync 幂等跳过", "幂等跳过" in r.stdout)
        for _ in range(3):
            run(ws, "sync", "ch_001", "--force")
        items = load(ws, "state/items.json")
        check("BUG#1 --force 重放 3 次后充能仍为 2", items["it_001"]["charges"] == 2, str(items["it_001"]["charges"]))
        debts = load(ws, "state/debts.json")
        check("BUG#6 无 id 恩怨重放不膨胀（仍 1 条）", len(debts) == 1, f"{len(debts)} 条")
        co = load(ws, "state/indices/co_occurrence.json")
        check("共现矩阵不虚增", co["p_001<->p_002"]["total_co_occurrences"] == 1)
        ledger = load(ws, "state/ledger.json")
        check("资金池重放不翻倍 (-200)", ledger["pools"]["现金"] == -200, str(ledger["pools"]))

        print("\n=== 3. Auditor 成果保护与涌现事实闭环 ===")
        a_path = ws / "log/audit/ch_002.md"
        (ws / "outlines/vol_01/beats/ch_002.md").write_text(BEATS_002, encoding="utf-8")
        (ws / "manuscript/vol_01/raw/ch_002_v1.md").write_text(PROSE_002, encoding="utf-8")
        run(ws, "audit", "ch_002", "--write")
        txt = a_path.read_text(encoding="utf-8")
        txt += """
- **修补配方**：
  - TargetContent:
  ```text
  表壳划痕密得像刮过砂纸。
  ```
  - ReplacementContent:
  ```text
  表壳上的划痕密得像被砂纸来回刮过。
  ```
  - 理由: 去 AI 味
- [新登场] 类型: person ｜ 名称: 巷口修鞋匠老崔 ｜ 描述: 目击者
"""
        a_path.write_text(txt, encoding="utf-8")

        r = run(ws, "audit", "ch_002", "--write")
        after = a_path.read_text(encoding="utf-8")
        check("BUG#5 重跑 audit 不覆盖 Auditor 配方", "表壳划痕密得像刮过砂纸。" in after)
        check("BUG#5 重跑 audit 不覆盖涌现事实", "巷口修鞋匠老崔" in after)
        check("BUG#5 保留时给出明确回执", "已保留既有质检报告" in r.stdout, r.stdout[:200])
        r = run(ws, "audit", "ch_002", "--write", "--force")
        check("BUG#5 --force 可重置并留 .bak",
              (ws / "log/audit/ch_002.md.bak").exists() and "巷口修鞋匠老崔" not in a_path.read_text(encoding="utf-8"))
        a_path.write_text(txt, encoding="utf-8")  # 还原 Auditor 成果继续流水线

        r = run(ws, "finalize", "ch_002")
        check("配方命中并应用", "配方 1/1 应用" in r.stdout, r.stdout[:200])
        check("正文已按配方替换",
              "被砂纸来回刮过" in (ws / "manuscript/vol_01/final/ch_002.md").read_text(encoding="utf-8"))

        check("proposal auto", run(ws, "proposal", "auto", "ch_002", "--write").returncode == 0)
        beats2 = (ws / "outlines/vol_01/beats/ch_002.md").read_text(encoding="utf-8")
        check("涌现新角色已回填细纲", "巷口修鞋匠老崔" in beats2)
        check("BUG#3 占位道具未被建档", "待填写道具名" not in beats2)

        check("sync ch_002", run(ws, "sync", "ch_002").returncode == 0)
        persons = load(ws, "state/persons.json")
        check("涌现角色已入台账", any(p.get("name") == "巷口修鞋匠老崔" for p in persons.values()))
        items = load(ws, "state/items.json")
        check("BUG#3 台账无幽灵道具",
              not any("待填写" in str(i.get("name", "")) for i in items.values()),
              str([i.get("name") for i in items.values()]))

        print("\n=== 4. 硬阻断守卫 ===")
        (ws / "outlines/vol_01/beats/ch_003.md").write_text(
            BEATS_002.replace("ch_002", "ch_003").replace('title: "三分钟的窟窿"', 'title: "空正文测试"'),
            encoding="utf-8")
        r = run(ws, "sync", "ch_003")
        check("空正文拒绝封存", r.returncode == 1 and "无任何有效正文" in r.stderr)

        (ws / "outlines/vol_01/beats/ch_004.md").write_text("""---
chapter_id: "ch_004"
volume_id: "vol_01"
title: "槽位未填"
location: "{{slot:location|核心场景名}}"
present_characters:
  - id: "p_001"
    name: "沈决"
new_entities: []
locked_facts: []
---
""", encoding="utf-8")
        (ws / "manuscript/vol_01/raw/ch_004_v1.md").write_text("沈决站着。", encoding="utf-8")
        r = run(ws, "sync", "ch_004")
        check("未填槽位拒绝入账", r.returncode == 1 and "未填占位符" in r.stderr)

        (ws / "outlines/vol_01/beats/ch_005.md").write_text("""---
chapter_id: "ch_002"
volume_id: "vol_01"
title: "错章号"
location: "西巷旧货店"
present_characters:
  - id: "p_001"
    name: "沈决"
new_entities: []
locked_facts: []
---
""", encoding="utf-8")
        (ws / "manuscript/vol_01/raw/ch_005_v1.md").write_text("沈决站着。", encoding="utf-8")
        r = run(ws, "sync", "ch_005")
        check("chapter_id 不一致拒绝合账", r.returncode == 1 and "不一致" in r.stderr)

        # 死者复活 + 充能透支（事务预检零写盘）
        (ws / "outlines/vol_01/beats/ch_006.md").write_text("""---
chapter_id: "ch_006"
volume_id: "vol_01"
title: "死者与透支"
location: "西巷旧货店"
present_characters:
  - id: "p_001"
    name: "沈决"
  - id: "p_003"
    name: "韩姨"
state_deltas:
  character_status:
    "p_003":
      life_status: "deceased"
      condition: "病故"
new_entities: []
locked_facts: []
---
""", encoding="utf-8")
        (ws / "manuscript/vol_01/raw/ch_006_v1.md").write_text("韩姨走了。沈决站在门口。", encoding="utf-8")
        check("死亡登记 sync", run(ws, "sync", "ch_006").returncode == 0)
        check("life_status 已置 deceased", load(ws, "state/persons.json")["p_003"]["life_status"] == "deceased")

        (ws / "outlines/vol_01/beats/ch_007.md").write_text("""---
chapter_id: "ch_007"
volume_id: "vol_01"
title: "死者复活"
location: "西巷旧货店"
present_characters:
  - id: "p_001"
    name: "沈决"
  - id: "p_003"
    name: "韩姨"
state_deltas:
  items:
    - id: "it_001"
      name: "灰烬打火机"
      charges_delta: -99
new_entities: []
locked_facts: []
---
""", encoding="utf-8")
        (ws / "manuscript/vol_01/raw/ch_007_v1.md").write_text("韩姨又出现了。", encoding="utf-8")
        before_items = json.dumps(load(ws, "state/items.json"), sort_keys=True)
        r = run(ws, "sync", "ch_007")
        check("死者登场硬阻断", r.returncode == 1 and "已于第" in r.stderr)
        check("充能透支同时被预检捕获", "充能已耗尽" in r.stderr or "不可透支" in r.stderr)
        check("阻断章零写盘（items 未变）",
              json.dumps(load(ws, "state/items.json"), sort_keys=True) == before_items)

        print("\n=== 5. 卷末与导出 ===")
        r = run(ws, "reconcile", "vol_01", "--write")
        check("reconcile 落盘", r.returncode == 0)
        rec = (ws / "log/review/reconcile_vol_01.md").read_text(encoding="utf-8")
        check("BUG#7 活跃伏笔按卷归属分列", "本卷埋设、仍活跃待回收伏笔" in rec)
        check("已回收伏笔入账 (MIS-001)", "MIS-001" in rec and "回收于: ch_002" in rec)
        check("rollup", run(ws, "state", "rollup", "vol_01").returncode == 0)
        r = run(ws, "export")
        check("export 成书", r.returncode == 0 and (ws / "export").exists())
        exported = next((ws / "export").glob("*.md")).read_text(encoding="utf-8")
        check("导出只含已封存章", "第 1 章" in exported and "槽位未填" not in exported)

        print("\n=== 6. 大盘与检索 ===")
        r = run(ws, "cockpit")
        check("cockpit 渲染", r.returncode == 0)
        check("BUG#8 恩怨双向展示", "`p_002` ➔ `p_001`" in r.stdout,
              [l for l in r.stdout.splitlines() if "grudge" in l])
        check("ask 检索命中", "灰烬打火机" in run(ws, "ask", "打火机").stdout)
        check("trace 道具", "灰烬打火机" in run(ws, "trace", "it_001").stdout)
        check("trace 伏笔分类正确", "[MIS]" in run(ws, "trace", "MIS-001").stdout,
              run(ws, "trace", "MIS-001").stdout[:160])
        check("id list", run(ws, "id", "list").returncode == 0)
        # BUG#10：死者登场错误曾被 ID 检查与姓名检查各报一次
        _c7 = run(ws, "check", "ch_007")
        check("BUG#10 死者登场错误不重复报告",
              _c7.stdout.count("已于第 ch_006 章阵亡") == 1,
              f"出现 {_c7.stdout.count('已于第 ch_006 章阵亡')} 次")

        # 清理测试期故意注入的违规细纲后，全书体检应当干净放行
        for stale in ("ch_003", "ch_004", "ch_005", "ch_007"):
            (ws / f"outlines/vol_01/beats/{stale}.md").unlink(missing_ok=True)
        _c = run(ws, "check")
        check("清理违规样本后 check 全书通过", _c.returncode == 0, _c.stdout[-800:])

        print("\n=== 7. 快照 ===")
        r = run(ws, "snapshot", "create", "rt")
        check("快照创建", r.returncode == 0)
        snap = sorted((ws / "snapshots").glob("rt_*.zip"))[-1].stem
        (ws / "manuscript/vol_01/final/ch_900.md").write_text("野文件", encoding="utf-8")
        r = run(ws, "snapshot", "rollback", snap)
        check("快照回滚", r.returncode == 0)
        check("回滚对齐清除未来文件", not (ws / "manuscript/vol_01/final/ch_900.md").exists())

        print("\n" + "=" * 60)
        print(f"通过 {len(PASS)} 项 ｜ 失败 {len(FAIL)} 项")
        if FAIL:
            print("\n失败清单：")
            for f in FAIL:
                print("  - " + f)
        return 1 if FAIL else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
