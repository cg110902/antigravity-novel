"""生成一本多章测试书：卷纲 + 每章细纲 + 每章 raw_v3 草稿。"""
import sys, subprocess, json
from pathlib import Path

ROOT = Path("/home/user/antigravity-novel")
WS = Path(sys.argv[1])
NCH = int(sys.argv[2]) if len(sys.argv) > 2 else 10
VOL = sys.argv[3] if len(sys.argv) > 3 else "vol_01"
START = int(sys.argv[4]) if len(sys.argv) > 4 else 1

def sh(*a):
    return subprocess.run([sys.executable, str(ROOT/"studio.py"), *a, "-w", str(WS)],
                          capture_output=True, text=True, cwd=str(ROOT))

if START == 1:
    WS.parent.mkdir(parents=True, exist_ok=True)
    r = sh("init", "-t", "长程巡航测试", "-g", "玄幻", "-p", "陆青")
    assert r.returncode == 0, r.stderr

end = START + NCH - 1
# 卷纲
lines = [f"---\nid: \"outline-{VOL}\"\nvol: \"{VOL}\"\ntitle: \"{VOL} 长程测试卷\"\n---\n\n# {VOL}\n\n## 📋 分章航标大表\n"]
for i in range(START, end+1):
    lines.append(f"### ch_{i:03d}: 第{i}关\n- **核心事件与看点**：陆青闯第{i}关，与守关人交手。\n- **断章刀口**：第{i}关的门在身后合拢。\n")
(WS/"outlines"/VOL).mkdir(parents=True, exist_ok=True)
(WS/"outlines"/VOL/"outline.md").write_text("\n".join(lines), encoding="utf-8")

beats_dir = WS/"outlines"/VOL/"beats"; beats_dir.mkdir(parents=True, exist_ok=True)
raw_dir = WS/"manuscript"/VOL/"raw"; raw_dir.mkdir(parents=True, exist_ok=True)

for i in range(START, end+1):
    cid = f"ch_{i:03d}"
    # 每章：主角 + 一个新守关人；每章埋 1 伏笔，隔 2 章回收；每章耗 1 充能
    guard_id = f"p_{i+2:03d}"  # 从 p_003 起，避开 init 模板已占用的 p_001 主角 / p_002 核心反派
    fm = [
        "---",
        f'chapter_id: "{cid}"',
        f'volume_id: "{VOL}"',
        f'title: "第{i}关"',
        'chapter_type: "爆发"',
        f'timeline: "试炼第{i}日"',
        f'location: "第{i}关石殿"',
        "present_characters:",
        '  - id: "p_001"',
        '    name: "陆青"',
        '    role: "protagonist"',
        f'    want: "闯过第{i}关"',
        '    fear: "灯油耗尽"',
        f'  - id: "{guard_id}"',
        f'    name: "守关人{i}"',
        '    role: "antagonist"',
        '    want: "拦住陆青"',
        '    fear: "失职"',
        "foreshadowing_deltas:",
        f'  - id: "GUN-{i:03d}"',
        f'    name: "第{i}关的刻痕"',
        '    action: "plant"',
        f'    desc: "石门上有第{i}道刻痕"',
        '    tier: "B"',
        f'    target_ch: "ch_{i+2:03d}"',
    ]
    if i >= START+2:
        fm += [
            f'  - id: "GUN-{i-2:03d}"',
            f'    name: "第{i-2}关的刻痕"',
            '    action: "resolve"',
            f'    desc: "刻痕在第{i}关拼合"',
        ]
    fm += [
        "state_deltas:",
        "  character_status:",
        f'    "p_001": "灯油见底·第{i}关伤"',
        "  items:",
        '    - id: "it_001"',
        '      name: "长明灯"',
        "      charges_delta: -1",
        '      status: "active"',
        "  ledger:",
        '    pool: "灵石"',
        '    delta: "-10"',
        f'    reason: "第{i}关过路费"',
        "  debts:",
        '    - source: "p_001"',
        f'      target: "{guard_id}"',
        '      type: "grudge"',
        f'      desc: "第{i}关断臂之仇"',
        '      action: "record"',
        "relation_deltas:",
        '  - source: "p_001"',
        f'    target: "{guard_id}"',
        f"    tension: {50+i}",
        '    dynamic: "闯关者与守门人"',
        '    subtext: "谁都不肯先退"',
        "new_entities:",
        f'  - id: "{guard_id}"',
        '    type: "character"',
        f'    name: "守关人{i}"',
        '    role: "antagonist"',
        f'    summary: "第{i}关的守门者"',
        f'    sensory_anchor: "袖口第{i}道铜环"',
        f'  - id: "loc_{i:03d}"',
        '    type: "place"',
        f'    name: "第{i}关石殿"',
        '    danger_level: "争端前线"',
        f'    sensory_anchor: "石粉与第{i}声钟响"',
        f'    summary: "第{i}关"',
    ]
    if i == START:
        fm += [
            '  - id: "it_001"',
            '    type: "item"',
            '    name: "长明灯"',
            '    holder: "陆青"',
            f"    charges: {NCH+5}",
            '    status: "active"',
            '    summary: "照见关门刻痕"',
        ]
    fm += [
        "locked_facts:",
        f'  - id: "LOCK-{i:03d}"',
        f'    fact: "第{i}关只能由持灯者独自通过"',
        '    domain: "rule"',
        "---",
        "",
        f"# 第 {cid} 章 编剧细纲",
        "",
        "- **本章核心戏剧目标**：",
        f"  陆青闯过第{i}关。",
        "- **物理定格画面**：",
        f"  第{i}关的门在身后合拢。",
    ]
    (beats_dir/f"{cid}.md").write_text("\n".join(fm), encoding="utf-8")

    prose = f"""# 第{i}章 第{i}关

石殿的门在陆青身后吱呀一声。灯芯抖了抖，照出墙上第{i}道刻痕。

守关人{i}从阴影里走出来，袖口第{i}道铜环撞在石柱上，响得干脆。

“持灯的，报上名。”

“陆青。”他把长明灯往前递了半寸，火苗压低，映出对方半张脸。

守关人{i}没有再问。刀风贴着地面扫来，陆青侧身避开，左臂却被削掉一片衣袖。

他反手把灯按在石门上。刻痕吃进光，整道门发出闷响。

“过。”守关人{i}收刀，退回阴影，“下一关的灯油，够不够你走到头？”

陆青没答。门在他身后合拢，把第{i}关的钟声关在了里面。
"""
    (raw_dir/f"{cid}_v3.md").write_text(prose, encoding="utf-8")

print(f"generated {VOL} ch_{START:03d}..ch_{end:03d} in {WS}")
