# -*- coding: utf-8 -*-
"""
Deterministic State-Mutation Applier (state_apply.py) v2
=====================================================
P0 状态引擎：LLM 只产出“结构化变更提案”，由本工具**确定性地**校验并合并进
6 大状态真值文件，而不是让模型手写一堆 Markdown 表格（易漏/易错/费 Token）。

v2 变更：
- current_state 字段 realm（境界）通用化为 power_level（能力层级），适用于全题材
- 同时保留 realm 作为向后兼容（玄幻题材仍可使用）
- 文档示例更新为 v2 通用字段

设计原则（与 Novel-OS / ABook 等成熟方案一致）：
- Markdown/JSON 文件仍是面向人/LLM 的唯一真值源（SSOT），本工具在其上做
  幂等、可重放、带校验的合并；
- 余额、章节号等“派生字段”由流水/台账计算，不接受模型直接覆写；
- 所有写入走原子 rename，绝不留下写一半的损坏台账；
- 提案处理后归档到 state_inbox/processed/，失败的进 failed/ 并报原因。

变更提案为 JSON（放 novel_workspace/04_timeline_and_state/state_inbox/*.json）：
{
  "schema": "novel-studio.state-mutation/v1",
  "chapter": "ch_012",
  "current_state": {"time":..., "location":..., "present_characters":[...],
                    "power_level":..., "realm":...(向后兼容), "abilities":..., "injury":..., "assets":..., "situation":...},
  "guns": [{"id":"GUN-004","action":"plant","name":"...","target_ch":18,"plan":"..."},
           {"id":"GUN-001","action":"update","status":"Reminded"},
           {"id":"GUN-002","action":"resolve"}],
  "misunderstandings": [{"action":"plant","parties":"...","content":"...","truth":"...","level":"1 级","target_ch":15}],
  "growth_arcs": [{"name":"陈昂","action":"update","stage":"Stage 1【...】","inciting_event":"...","strategy":"..."}],
  "timeline": [{"time":"第三日·夜","event":"黑市交易破裂，主角反将一军"}],
  "transactions": [{"resource":"standard_currency","delta":-30,"type":"expense","subject":"购入情报","counterparty":"黑市掮客"}]
}

Usage:
    python tools/state_apply.py                     # 合并 inbox 中所有待处理提案
    python tools/state_apply.py -f proposal.json    # 合并指定提案
    python tools/state_apply.py --dry-run           # 只校验不写入
    python tools/state_apply.py --json
"""

import sys
import re
import json
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import (
    resolve_workspace, reconfigure_utf8, atomic_write_text,
    split_table_row, render_table_row, find_table_block, has_placeholder,
)

reconfigure_utf8()

MUTATION_SCHEMA = "novel-studio.state-mutation/v1"


# ─────────────────────────────────────────────────────────────────────
# Economy ledger (JSON) — double-entry, derived balances
# ─────────────────────────────────────────────────────────────────────
def apply_transactions(ledger_path: Path, transactions: list, chapter: str, report: dict):
    if not ledger_path.exists():
        report["errors"].append(f"账本文件不存在: {ledger_path.name}")
        return
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    pools = data.get("resource_pools")
    if not pools:
        report["errors"].append("economy_ledger.json 缺少 resource_pools，无法记账")
        return

    running = {k: v.get("initial", 0) for k, v in pools.items()}
    # 重放已有流水得到当前余额（权威值，不信 current 字段）
    existing = data.get("transactions", [])
    for t in existing:
        rk = t.get("resource")
        if rk not in running:
            report["warnings"].append(f"历史流水引用了未声明资源池 '{rk}'，已跳过")
            continue
        running[rk] += t.get("delta", t.get("inflow", 0) - t.get("outflow", 0))

    added = 0
    for idx, t in enumerate(transactions, 1):
        rk = t.get("resource")
        if rk is None:
            rk = next(iter(pools))  # 单币种默认归入第一个池
        if rk not in running:
            report["errors"].append(
                f"流水 #{idx} 引用了 resource_pools 中不存在的资源池 '{rk}'（请先在台账登记）")
            continue
        delta = t.get("delta")
        if delta is None:
            delta = t.get("inflow", 0) - t.get("outflow", 0)
        try:
            delta = int(delta)
        except (TypeError, ValueError):
            report["errors"].append(f"流水 #{idx} 的 delta 非整数: {t.get('delta')}")
            continue
        running[rk] += delta
        tx = {
            "chapter": t.get("chapter", chapter),
            "resource": rk,
            "type": t.get("type", "income" if delta > 0 else "expense"),
            "delta": delta,
            "subject": t.get("subject", ""),
            "counterparty": t.get("counterparty", ""),
            "balance_after": running[rk],
        }
        if t.get("note"):
            tx["note"] = t["note"]
        existing.append(tx)
        added += 1
        report["updated"].append(f"💰 流水: {rk} {delta:+} → 余额 {running[rk]}（{tx['subject']}）")

    data["transactions"] = existing
    # 回写派生余额
    for k, v in pools.items():
        v["current"] = running.get(k, v.get("initial", 0))
    atomic_write_text(ledger_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    report["updated"].append(f"🧮 账本已记账 {added} 笔，资源池余额已按流水重算")


# ─────────────────────────────────────────────────────────────────────
# Markdown table mergers (guns / misunderstandings / growth arcs)
# ─────────────────────────────────────────────────────────────────────
def _norm_id(cell: str) -> str:
    return re.sub(r"[*_`\s]", "", cell or "")

def _next_id(rows: list, prefix: str, width: int = 3) -> str:
    maxn = 0
    for r in rows:
        m = re.search(prefix + r"[-_]?(\d+)", _norm_id(r[0]) if r else "")
        if m:
            maxn = max(maxn, int(m.group(1)))
    return f"{prefix}-{maxn + 1:0{width}d}"

def _find_row_index(rows: list, target_id: str):
    t = _norm_id(target_id)
    for i, r in enumerate(rows):
        if r and _norm_id(r[0]) == t:
            return i
    return -1

def _merge_guns(content: str, guns: list, chapter: str, report: dict) -> str:
    if not guns:
        return content
    lines = content.splitlines()
    blk = find_table_block(lines, "伏笔 ID")
    if not blk:
        report["errors"].append("chekhov_guns.md 未找到伏笔表格")
        return content
    rows = blk["rows"]
    ch_num = re.search(r"(\d+)", chapter or "")
    here_ch = int(ch_num.group(1)) if ch_num else 0

    for g in guns:
        action = (g.get("action") or "plant").lower()
        gid = _norm_id(g.get("id", ""))
        if action == "plant":
            if not gid:
                gid = _next_id(rows, "GUN")
            if _find_row_index(rows, gid) >= 0:
                report["warnings"].append(f"伏笔 {gid} 已存在，plant 被忽略")
                continue
            name = g.get("name", "未命名伏笔")
            plant = g.get("plant_ch", here_ch) or here_ch
            target = g.get("target_ch", "全局贯穿")
            target_cell = f"第 {target} 章" if isinstance(target, int) else str(target)
            rows.append([
                f"**{gid}**", f"《{name}》", f"第 {plant} 章",
                "**Planted**", target_cell, g.get("plan", "待补充闭环规划")
            ])
            report["updated"].append(f"🕸️ 新伏笔 {gid}《{name}》（计划 {target_cell} 引爆）")
        else:
            idx = _find_row_index(rows, gid)
            if idx < 0:
                report["warnings"].append(f"伏笔 {gid} 不存在，无法 {action}")
                continue
            row = rows[idx]
            if action == "resolve":
                while len(row) < 6:
                    row.append("")
                row[3] = "**Resolved**"
                report["updated"].append(f"✅ 伏笔 {gid} 已回收/引爆")
            elif action == "update":
                while len(row) < 6:
                    row.append("")
                if g.get("status"):
                    row[3] = f"**{g['status']}**"
                if g.get("target_ch") is not None:
                    t = g["target_ch"]
                    row[4] = f"第 {t} 章" if isinstance(t, int) else str(t)
                if g.get("plan"):
                    row[5] = g["plan"]
                report["updated"].append(f"🔁 伏笔 {gid} 状态更新为 {row[3]}")

    # Re-render the block
    new_lines = lines[:blk["header_idx"]]
    new_lines.append(lines[blk["header_idx"]])
    new_lines.append(lines[blk["sep_idx"]])
    for r in rows:
        # pad to header column count
        while len(r) < len(blk["headers"]):
            r.append("")
        new_lines.append(render_table_row(r[:len(blk["headers"])]))
    new_lines.extend(lines[blk["data_end"]:])
    return "\n".join(new_lines)

def _merge_misunderstandings(content: str, items: list, chapter: str, report: dict) -> str:
    if not items:
        return content
    lines = content.splitlines()
    blk = find_table_block(lines, "ID")
    if not blk:
        report["errors"].append("misunderstandings.md 未找到误会台账表格")
        return content
    rows = blk["rows"]
    ch_num = re.search(r"(\d+)", chapter or "")
    here_ch = int(ch_num.group(1)) if ch_num else 0

    for m in items:
        action = (m.get("action") or "plant").lower()
        mid = _norm_id(m.get("id", ""))
        if action == "plant":
            if not mid:
                mid = _next_id(rows, "MIS")
            if _find_row_index(rows, mid) >= 0:
                report["warnings"].append(f"误会 {mid} 已存在，plant 被忽略")
                continue
            target = m.get("target_ch", here_ch + 3)
            target_cell = f"第 {target} 章" if isinstance(target, int) else str(target)
            rows.append([
                f"**{mid}**", m.get("parties", ""), m.get("content", ""),
                m.get("truth", ""), f"**{m.get('level', '1 级 (潜伏发酵)')}**", target_cell
            ])
            report["updated"].append(f"🎭 新误会 {mid}：{m.get('content','')[:20]}")
        else:
            idx = _find_row_index(rows, mid)
            if idx < 0:
                report["warnings"].append(f"误会 {mid} 不存在，无法 {action}")
                continue
            row = rows[idx]
            while len(row) < 6:
                row.append("")
            if action == "resolve":
                row[4] = "**已澄清**"
                report["updated"].append(f"✅ 误会 {mid} 已澄清")
            elif action == "update":
                if m.get("level"):
                    row[4] = f"**{m['level']}**"
                if m.get("content"):
                    row[2] = m["content"]
                report["updated"].append(f"🔁 误会 {mid} 已更新")

    new_lines = lines[:blk["header_idx"]]
    new_lines.append(lines[blk["header_idx"]])
    new_lines.append(lines[blk["sep_idx"]])
    for r in rows:
        while len(r) < len(blk["headers"]):
            r.append("")
        new_lines.append(render_table_row(r[:len(blk["headers"])]))
    new_lines.extend(lines[blk["data_end"]:])
    return "\n".join(new_lines)

def _merge_growth_arcs(content: str, arcs: list, chapter: str, report: dict) -> str:
    if not arcs:
        return content
    lines = content.splitlines()
    blk = find_table_block(lines, "角色")
    if not blk:
        report["errors"].append("character_growth_arcs.md 未找到心智台账表格")
        return content
    rows = blk["rows"]

    for a in arcs:
        name = (a.get("name") or "").strip()
        if not name:
            report["warnings"].append("成长弧线缺少 name，已跳过")
            continue
        idx = -1
        for i, r in enumerate(rows):
            if r and _norm_id(r[0]) == _norm_id(name):
                idx = i
                break
        stage = a.get("stage", "")
        if idx < 0:
            # 新角色：追加一行
            rows.append([
                f"**{name}**",
                a.get("baseline", stage or "Stage 0：初始基线"),
                f"**{stage}**" if stage else "待定",
                a.get("inciting_event", "待记录"),
                a.get("ultimate", "Stage 2+（长线成长）"),
            ])
            report["updated"].append(f"🧠 新建心智台账：{name} → {stage}")
        else:
            row = rows[idx]
            while len(row) < 5:
                row.append("")
            if stage:
                row[2] = f"**{stage}**"
            if a.get("inciting_event"):
                row[3] = a["inciting_event"]
            if a.get("strategy"):
                row[3] = (row[3] + "；" if row[3] else "") + a["strategy"]
            report["updated"].append(f"🧠 {name} 心智阶段 → {stage}")

    new_lines = lines[:blk["header_idx"]]
    new_lines.append(lines[blk["header_idx"]])
    new_lines.append(lines[blk["sep_idx"]])
    for r in rows:
        while len(r) < len(blk["headers"]):
            r.append("")
        new_lines.append(render_table_row(r[:len(blk["headers"])]))
    new_lines.extend(lines[blk["data_end"]:])
    return "\n".join(new_lines)


# ─────────────────────────────────────────────────────────────────────
# current_state.md — labeled bullets
# ─────────────────────────────────────────────────────────────────────
def _set_bullet_value(lines: list, label: str, value: str):
    """Sets the value after a '- **label**：' bullet; returns True if found."""
    for i, line in enumerate(lines):
        if line.strip().startswith("-") and f"**{label}" in line:
            m = re.match(r"^(\s*-\s*\*\*" + re.escape(label) + r"[^\*]*\*\*\s*[：:])\s*(.*)$", line)
            if m:
                lines[i] = m.group(1) + " " + value
                return True
    return False

def _merge_current_state(content: str, cs: dict, report: dict) -> str:
    if not cs:
        return content
    lines = content.splitlines()

    # v2: power_level 为通用字段（能力层级），realm 保留为向后兼容（玄幻境界）
    label_map = {
        "time": "当前时间节点",
        "location": "当前故事地点",
        "power_level": "当前能力层级",
        "realm": "当前境界",
        "abilities": "特殊机制/词条/能力",
        "injury": "生理负荷/暗伤",
        "assets": "随身流动资金",
        "equipment": "随身核心信物/关键装备",
    }
    for key, label in label_map.items():
        if cs.get(key):
            ok = _set_bullet_value(lines, label, str(cs[key]))
            if ok:
                report["updated"].append(f"📍 状态机 [{label}] 已更新")
            else:
                lines.append(f"- **{label}**：{cs[key]}")
                report["updated"].append(f"📍 状态机 [{label}] 新增")

    # 在场核心角色（多行子列表替换）
    pcs = cs.get("present_characters")
    if pcs:
        for i, line in enumerate(lines):
            if "在场核心角色" in line:
                # 删除其后连续的子项（缩进更深的 "- " 行）
                j = i + 1
                while j < len(lines) and (lines[j].strip().startswith("-") or lines[j].strip() == ""):
                    if lines[j].strip() == "" and j + 1 < len(lines) and not lines[j + 1].startswith("  "):
                        break
                    if lines[j].strip().startswith("-") and not lines[j].startswith("  "):
                        break
                    j += 1
                sub = [f"  - {c}" if isinstance(c, str) else f"  - {c.get('name','')}（{c.get('state','')}）" for c in pcs]
                lines[i + 1:j] = sub
                report["updated"].append(f"📍 在场角色更新为 {len(pcs)} 人")
                break

    # 局势/下一章引子：追加到该小节末尾
    if cs.get("situation"):
        inserted = False
        for i in range(len(lines) - 1, -1, -1):
            if "当前博弈局势" in lines[i] or "下一章引子" in lines[i]:
                lines.insert(i + 1, f"  - {cs['situation']}")
                inserted = True
                break
        if not inserted:
            lines.append(f"- **当前博弈局势与下一章引子**：")
            lines.append(f"  - {cs['situation']}")
        report["updated"].append("📍 局势/下一章引子已更新")

    return "\n".join(lines) + "\n"


def _merge_timeline(content: str, entries: list, report: dict) -> str:
    if not entries:
        return content
    existing = set(re.sub(r"\s", "", l) for l in content.splitlines())
    added = []
    for e in entries:
        time_lbl = e.get("time", "未标注时间")
        event = e.get("event", "").strip()
        if not event:
            continue
        bullet = f"- **【{time_lbl}】**：{event}"
        if re.sub(r"\s", "", event) in "\n".join(existing):
            continue  # 幂等去重
        added.append(bullet)
    if added:
        content = content.rstrip() + "\n" + "\n".join(added) + "\n"
        report["updated"].append(f"📜 编年史追加 {len(added)} 条事件")
    return content


# ─────────────────────────────────────────────────────────────────────
# Apply one proposal
# ─────────────────────────────────────────────────────────────────────
def apply_proposal(workspace: Path, proposal: dict, dry_run: bool = False) -> dict:
    state_dir = workspace / "04_timeline_and_state"
    report = {"updated": [], "warnings": [], "errors": [], "chapter": proposal.get("chapter")}

    if proposal.get("schema") != MUTATION_SCHEMA:
        report["warnings"].append(
            f"提案 schema 为 {proposal.get('schema')!r}，期望 {MUTATION_SCHEMA}（仍尝试合并）")

    chapter = proposal.get("chapter", "")

    # 安全闸：草稿提案（_draft:true）绝不合并——它只供 LLM 复核后另存为正式提案
    if proposal.get("_draft"):
        report["errors"].append(
            "这是 proposal_draft 生成的草稿（_draft:true），不能直接合并；"
            "请 LLM 复核补全后另存为去掉 _draft 的正式提案。")
        return report

    def _read(name):
        p = state_dir / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def _write(name, text):
        if dry_run:
            return
        atomic_write_text(state_dir / name, text)

    # current_state
    if proposal.get("current_state"):
        c = _read("current_state.md")
        if c:
            _write("current_state.md", _merge_current_state(c, proposal["current_state"], report))
    # guns
    if proposal.get("guns"):
        c = _read("chekhov_guns.md")
        if c:
            _write("chekhov_guns.md", _merge_guns(c, proposal["guns"], chapter, report))
    # misunderstandings
    if proposal.get("misunderstandings"):
        c = _read("misunderstandings.md")
        if c:
            _write("misunderstandings.md", _merge_misunderstandings(c, proposal["misunderstandings"], chapter, report))
    # growth arcs
    if proposal.get("growth_arcs"):
        c = _read("character_growth_arcs.md")
        if c:
            _write("character_growth_arcs.md", _merge_growth_arcs(c, proposal["growth_arcs"], chapter, report))
    # timeline
    if proposal.get("timeline"):
        c = _read("timeline.md")
        if c:
            _write("timeline.md", _merge_timeline(c, proposal["timeline"], report))
    # ledger
    if proposal.get("transactions"):
        ledger = state_dir / "economy_ledger.json"
        if not dry_run:
            apply_transactions(ledger, proposal["transactions"], chapter, report)
        else:
            report["updated"].append(f"💰 [dry-run] 将记账 {len(proposal['transactions'])} 笔")

    # chapter synopsis (P1 梗概脊柱)：提案可带本章 2~3 句人工/LLM 提炼梗概
    syn = proposal.get("synopsis")
    if syn:
        if not dry_run:
            _merge_synopsis(workspace, chapter, syn, proposal.get("chapter_title", ""), report)
        else:
            report["updated"].append(f"📖 [dry-run] 将登记章节梗概（{chapter}）")

    return report


def _merge_synopsis(workspace: Path, chapter: str, synopsis: str, title: str, report: dict):
    """把本章梗概 upsert 进 chapter_synopsis.json（source=manual，优先级高于 auto）。"""
    try:
        import memory_core
        data = memory_core.load_synopsis(workspace)
        num_m = re.search(r"(\d+)", chapter or "")
        num = int(num_m.group(1)) if num_m else len(data["chapters"]) + 1
        key = f"ch_{num:03d}"
        prev = data["chapters"].get(key, {})
        data["chapters"][key] = {
            "num": num,
            "title": title or prev.get("title", ""),
            "synopsis": str(synopsis).strip(),
            "source": "manual",
        }
        memory_core.save_synopsis(workspace, data)
        report["updated"].append(f"📖 章节梗概已登记（{key}，manual 覆盖 auto）")
    except Exception as e:
        report["warnings"].append(f"章节梗概登记失败: {e}")


def _gather_proposals(inbox: Path):
    if not inbox.exists():
        return []
    # 草稿提案（*.draft.json）与示例母版（*.template.json, *.sample.json）绝不参与合并
    return sorted(
        p for p in inbox.glob("*.json")
        if not (p.name.endswith(".draft.json") or p.name.endswith(".template.json") or p.name.endswith(".sample.json"))
    )


def main():
    parser = argparse.ArgumentParser(description="确定性状态变更合并器（State Mutation Applier）v2")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="工作区路径")
    parser.add_argument("--file", "-f", type=str, default=None, help="指定单个提案 JSON 文件")
    parser.add_argument("--dry-run", action="store_true", help="只校验与预演，不写入")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    workspace = resolve_workspace(args.workspace)
    state_dir = workspace / "04_timeline_and_state"
    inbox = state_dir / "state_inbox"
    processed = inbox / "processed"
    failed = inbox / "failed"

    if args.file:
        files = [Path(args.file)]
    else:
        files = _gather_proposals(inbox)

    if not files:
        msg = f"state_inbox 中没有待处理提案（{inbox}）"
        if args.json:
            print(json.dumps({"status": "EMPTY", "message": msg}, ensure_ascii=False, indent=2))
        else:
            print(f"ℹ️ {msg}")
        sys.exit(0)

    overall = {"applied": 0, "failed": 0, "results": []}
    for pf in files:
        try:
            proposal = json.loads(pf.read_text(encoding="utf-8"))
        except Exception as e:
            overall["failed"] += 1
            overall["results"].append({"file": pf.name, "errors": [f"提案 JSON 解析失败: {e}"]})
            if not args.dry_run:
                failed.mkdir(parents=True, exist_ok=True)
                pf.rename(failed / pf.name)
            continue

        rep = apply_proposal(workspace, proposal, dry_run=args.dry_run)
        rep["file"] = pf.name
        overall["results"].append(rep)
        if rep["errors"]:
            overall["failed"] += 1
            if not args.dry_run:
                failed.mkdir(parents=True, exist_ok=True)
                pf.rename(failed / pf.name)
        else:
            overall["applied"] += 1
            if not args.dry_run:
                processed.mkdir(parents=True, exist_ok=True)
                pf.rename(processed / pf.name)

    if args.json:
        print(json.dumps(overall, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print(f" 🔀 [状态变更合并器 v2] 工作区: {workspace.name}{'  [DRY-RUN]' if args.dry_run else ''}")
        print("=" * 72)
        for r in overall["results"]:
            print(f"\n📄 {r['file']}（章节 {r.get('chapter','-')}）")
            for u in r["updated"]:
                print(f"   {u}")
            for w in r["warnings"]:
                print(f"   ⚠️ {w}")
            for e in r["errors"]:
                print(f"   ❌ {e}")
        print("\n" + "=" * 72)
        print(f" ✅ 成功合并 {overall['applied']} 份 | ❌ 失败 {overall['failed']} 份")
        print("=" * 72)

    sys.exit(1 if overall["failed"] else 0)


if __name__ == "__main__":
    main()
