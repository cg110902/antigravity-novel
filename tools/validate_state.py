# -*- coding: utf-8 -*-
"""
Workspace & State Health Validator (validate_state.py)
=====================================================
P0 健壮性：对工作区目录结构、6 大状态文件、economy_ledger.json 做确定性体检，
检查：缺文件、JSON 不可解析、台账不平衡、流水引用未声明资源池、未清理的模板
占位符、伏笔/误会编号不连续、快照可读性等。供 `studio.py doctor` 调用。

Usage:
    python tools/validate_state.py
    python tools/validate_state.py -w novel_workspace --json
"""

import sys
import json
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import (
    resolve_workspace, reconfigure_utf8, has_placeholder, find_table_block,
)

reconfigure_utf8()

REQUIRED_DIRS = [
    "00_meta", "01_world", "02_characters", "02_characters/profiles",
    "03_outlines", "04_timeline_and_state",
    "05_manuscript/vol_01/raw_drafts", "05_manuscript/vol_01/finalized",
]
REQUIRED_FILES = [
    "00_meta/project_bible.md",
    "01_world/world_rules.md",
    "02_characters/character_index.md",
    "04_timeline_and_state/current_state.md",
    "04_timeline_and_state/timeline.md",
    "04_timeline_and_state/chekhov_guns.md",
    "04_timeline_and_state/misunderstandings.md",
    "04_timeline_and_state/character_growth_arcs.md",
    "04_timeline_and_state/economy_ledger.json",
]


def _validate_ledger(state_dir: Path, errors: list, warnings: list):
    p = state_dir / "economy_ledger.json"
    if not p.exists():
        errors.append("缺少 economy_ledger.json")
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"economy_ledger.json 无法解析: {e}")
        return
    pools = data.get("resource_pools")
    if pools is None:
        warnings.append("economy_ledger.json 无 resource_pools（单币种旧格式，建议迁移）")
        return
    running = {k: v.get("initial", 0) for k, v in pools.items()}
    for i, t in enumerate(data.get("transactions", []), 1):
        rk = t.get("resource")
        if rk is None:
            rk = next(iter(pools))
        if rk not in running:
            errors.append(f"账本流水 #{i} 引用未声明资源池 '{rk}'（章节 {t.get('chapter','?')}）")
            continue
        delta = t.get("delta")
        if delta is None:
            delta = t.get("inflow", 0) - t.get("outflow", 0)
        try:
            running[rk] += int(delta)
        except (TypeError, ValueError):
            errors.append(f"账本流水 #{i} delta 非数值: {delta!r}")
            continue
        if t.get("balance_after") is not None and t["balance_after"] != running[rk]:
            warnings.append(
                f"流水 #{i}（{t.get('chapter','?')}/{rk}）记录结余 {t['balance_after']} 与流水累计 {running[rk]} 不符")
    for k, v in pools.items():
        declared = v.get("current", v.get("initial", 0))
        if declared != running.get(k):
            errors.append(
                f"资源池【{v.get('name', k)}】声明余额 {declared} 与流水累计 {running.get(k)} 不平衡")


def _check_id_sequence(lines: list, header_kw: str, prefix: str, errors: list, warnings: list, name: str):
    blk = find_table_block(lines, header_kw)
    if not blk:
        return
    ids = []
    for r in blk["rows"]:
        if not r or has_placeholder(" ".join(r)):
            continue  # 模板示例行
        import re
        m = re.search(prefix + r"[-_]?(\d+)", r[0] if r else "")
        if m:
            ids.append(int(m.group(1)))
    dup = {x for x in ids if ids.count(x) > 1}
    if dup:
        errors.append(f"{name} 存在重复编号: {sorted(dup)}")


def validate_workspace(workspace: Path):
    errors, warnings, ok_files = [], [], []

    # 1. 目录/文件结构
    for d in REQUIRED_DIRS:
        if not (workspace / d).is_dir():
            errors.append(f"缺少目录: {d}/")
    for f in REQUIRED_FILES:
        if (workspace / f).exists():
            ok_files.append(f)
        else:
            errors.append(f"缺少文件: {f}")

    state_dir = workspace / "04_timeline_and_state"

    # 2. 残留占位符：只统计“表格行/标题之外”的 [中文] 占位符。
    #    台账表头下保留的 [示例] 引导行是模板设计的一部分，不算残留。
    import re as _re
    for f in REQUIRED_FILES:
        pf = workspace / f
        if pf.exists() and pf.suffix == ".md" and not f.endswith("project_bible.md"):
            outside = []
            for line in pf.read_text(encoding="utf-8").splitlines():
                st = line.strip()
                if st.startswith("|") or st.startswith("#"):
                    continue
                outside += _re.findall(r"\[[^\[\]]*[\u4e00-\u9fa5][^\[\]]*\]", st)
            if outside:
                warnings.append(f"{f} 正文（非表格）仍含 {len(outside)} 处 [方括号] 占位符待填写")


    # 3. JSON 账本
    if (state_dir / "economy_ledger.json").exists():
        _validate_ledger(state_dir, errors, warnings)

    # 4. 表格编号连续性
    for fname, kw, prefix, label in [
        ("chekhov_guns.md", "伏笔 ID", "GUN", "伏笔台账"),
        ("misunderstandings.md", "ID", "MIS", "误会台账"),
    ]:
        p = state_dir / fname
        if p.exists():
            _check_id_sequence(p.read_text(encoding="utf-8").splitlines(),
                               kw, prefix, errors, warnings, label)

    # 5. 快照可读性
    snap_dir = state_dir / "snapshots"
    if snap_dir.exists():
        for d in snap_dir.iterdir():
            if d.is_dir() and not any(d.glob("*.md")) and not any(d.glob("*.json")):
                warnings.append(f"快照 {d.name} 为空目录")

    status_str = "ERRORS" if errors else ("WARNINGS" if warnings else "HEALTHY")
    report = {
        "workspace": str(workspace),
        "status": status_str,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "checked_files": ok_files,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="工作区与状态机健康自检 (doctor)")
    parser.add_argument("--workspace", "-w", type=str, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ws = resolve_workspace(args.workspace)
    if not ws.exists():
        rep = {"status": "MISSING", "errors": [f"工作区不存在: {ws}（请先 studio.py init）"]}
        if args.json:
            print(json.dumps(rep, ensure_ascii=False, indent=2))
        else:
            print(f"❌ {rep['errors'][0]}")
        sys.exit(1)

    rep = validate_workspace(ws)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print(f" 🩺 [工作区健康自检] {ws.name}")
        print("=" * 72)
        for e in rep["errors"]:
            print(f"   ❌ {e}")
        for w in rep["warnings"]:
            print(f"   ⚠️ {w}")
        if not rep["errors"] and not rep["warnings"]:
            print(f"   ✅ 结构完整、台账平衡、无占位符残留，工作区健康！")
        print("=" * 72)
        print(f" 结论: {rep['status']}（错误 {rep['error_count']} / 警告 {rep['warning_count']}）")
        print("=" * 72)
    sys.exit(1 if rep["errors"] else 0)


if __name__ == "__main__":
    main()
