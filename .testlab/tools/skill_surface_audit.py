#!/usr/bin/env python3
"""10-SKILL 命令面与文件契约审计（第四轮）。

对 `.agents/skills/*/SKILL.md` 逐份做三类机械核验（全部黑盒，只跑官方 CLI）：

  1. **命令存在性**：手册里写到的每条 `python studio.py <sub> [<subsub>]` 必须真能跑
     （`--help` exit 0）。手册写了引擎没有的命令 = 主控照手册执行必吃 exit 2。
  2. **旗标存在性**：手册里跟在命令后的每个 `--flag` 必须出现在该命令的 help 里。
     旗标漂移（改名/删除）会让主控的 S5 短路链在某一环静默失效。
  3. **文件契约存在性**：手册声明的「准读输入 / 准写工件」路径（vol_XX/ch_XXX 占位）
     在真实建造出来的 30 章基座里必须存在——否则该角色单次全读就读空。
  4. **零命令红线自洽**：声称【绝对零命令】的角色，手册里不得出现任何 studio.py 命令。

用法：
    python .testlab/tools/skill_surface_audit.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WS = REPO / "workspace" / "long-lab"
STUDIO = [sys.executable, str(REPO / "studio.py")]
SKILLS = sorted((REPO / ".agents" / "skills").glob("*/SKILL.md"))

ROWS: list[dict] = []
HELP_CACHE: dict[str, tuple[int, str]] = {}


def rec(skill: str, kind: str, item: str, ok: bool, detail: str = "") -> None:
    ROWS.append({"skill": skill, "kind": kind, "item": item, "ok": ok, "detail": detail[:300]})
    print(f"{'✅' if ok else '❌'} [{skill}/{kind}] {item}" + (f" ｜ {detail[:160]}" if detail else ""))


def help_of(cmd: list[str]) -> tuple[int, str]:
    key = " ".join(cmd)
    if key not in HELP_CACHE:
        p = subprocess.run([*STUDIO, *cmd, "--help"], cwd=str(REPO),
                           capture_output=True, text=True, encoding="utf-8")
        HELP_CACHE[key] = (p.returncode, (p.stdout or "") + (p.stderr or ""))
    return HELP_CACHE[key]


# ── 抽取器 ────────────────────────────────────────────────────────────
# 手册里的命令行常常是 S5 短路链（`finalize … && proposal auto … --write --force && sync …`），
# 若整行抓旗标就会把后一条命令的旗标算到前一条头上（实测把 `--write/--force` 诬给
# finalize、把 `--entity/--action` 诬给 snapshot create）。故先按 `&& ; | ｜` 与
# 每个 `studio.py` 出现点切段，旗标只归属自己那一段。
SUBS2 = ("new", "add", "achieve", "auto", "create", "rollback", "list", "rollup",
         "candidates", "impact", "get", "set", "guide", "next", "trace")
SEG_RE = re.compile(r"studio\.py\s+([a-z][a-z\-]*)(?:\s+([a-z][a-z\-]*))?")
FLAG_RE = re.compile(r"(--[a-z][\w\-]*)")
# 工作区内的顶层目录（文件契约核验用）
WS_TOP = ("manuscript", "outlines", "log", "state", "bible", "characters", "entities", "snapshots")
PATH_RE = re.compile(
    r"`?((?:templates|workspace/(?:<书名>|[^/\s]+))/[A-Za-z0-9_./<>\-]+"
    r"|(?:manuscript|outlines|log|state|bible|characters|entities|snapshots)/[A-Za-z0-9_./<>\-]*"
    r"|pack\.md|dossier\.md)`?"
)
# 准写工件语境：这些路径由该角色自己落盘，基座里不存在属正常，不做存在性核验
WRITE_CTX = ("准写", "写入", "落盘", "产出路径", "write_to_file", "replace_file_content", "创建", "提纯为")


def extract_cmds(text: str) -> dict[tuple[str, ...], set[str]]:
    cmds: dict[tuple[str, ...], set[str]] = {}
    for m in SEG_RE.finditer(text):
        sub, subsub = m.group(1), m.group(2)
        key = (sub, subsub) if subsub in SUBS2 else (sub,)
        seg_end = len(text)
        for nxt in re.finditer(r"studio\.py|&&|;|\\||\n", text[m.end():]):
            seg_end = m.end() + nxt.start()
            break
        cmds.setdefault(key, set()).update(FLAG_RE.findall(text[m.end():seg_end]))
    return cmds


def extract_paths(text: str) -> list[tuple[str, bool]]:
    """返回 (路径, 是否准写工件)。逐行判定语境，避免把角色自己产出的报告当成缺失输入。"""
    out: list[tuple[str, bool]] = []
    for line in text.splitlines():
        is_write = any(k in line for k in WRITE_CTX)
        for m in PATH_RE.finditer(line):
            out.append((m.group(1), is_write))
    return out


def subst(p: str) -> str:
    p = re.sub(r"^workspace/(?:<书名>|[^/]+)/", "", p)
    p = p.replace("vol_XX", "vol_01").replace("ch_XXX", "ch_001").replace("vol_01", "vol_01")
    p = p.replace("XXX", "001")
    return p.strip("/")


def main() -> int:
    for f in SKILLS:
        skill = f.parent.name
        text = f.read_text(encoding="utf-8")
        zero_cmd = ("绝对零命令" in text) or ("零终端操作" in text)

        # ── 1&2 命令与旗标 ──
        cmds = extract_cmds(text)
        # 零命令红线只看该角色自己的「准跑命令」条款（手册里引用子代理的
        # 「绝对零命令」描述不算数——旧版据此把 director 诬为红线自相矛盾）
        zero_line = next((l for l in text.splitlines() if "准跑命令" in l), "")
        zero_cmd = ("绝对零命令" in zero_line) or ("零终端操作" in zero_line)

        if zero_cmd and cmds:
            rec(skill, "红线", "声称【绝对零命令】却写了 CLI 命令", False,
                "; ".join(" ".join(k) for k in cmds))
        elif zero_cmd:
            rec(skill, "红线", "零命令角色手册无任何 CLI 命令（自洽）", True, "")

        for key, flags in sorted(cmds.items()):
            cmd = list(key)
            code, out = help_of(cmd)
            exists = code == 0 and "invalid choice" not in out and "usage:" in out
            rec(skill, "命令", f"studio.py {' '.join(cmd)}", exists,
                f"help exit={code}" + ("" if exists else f" ｜ {out.strip().splitlines()[-1][:100] if out.strip() else ''}"))
            if not exists:
                continue
            bad = sorted(fl for fl in flags if fl not in out)
            rec(skill, "旗标", f"{' '.join(cmd)} 的 {sorted(flags) or '无旗标'}", not bad,
                f"help 里查无: {bad}" if bad else "")

        # ── 3 文件契约（准读输入才核验存在性；准写工件与仓库模板分开判定）──
        seen: set[str] = set()
        read_n = write_n = tmpl_n = 0
        for raw, is_write in extract_paths(text):
            if raw in seen:
                continue
            seen.add(raw)
            if raw.startswith("templates/"):
                tmpl_n += 1
                ok = (REPO / raw).exists()
                rec(skill, "模板", raw, ok, "" if ok else f"仓库内查无 {REPO / raw}")
                continue
            if is_write:
                write_n += 1
                continue                      # 角色自己落盘的工件，基座里没有属正常
            p = subst(raw)
            if not p or p == "pack.md":
                cand = WS / (p or "pack.md")
            else:
                cand = WS / p
            if cand.suffix == "" and "*" not in p:
                continue                      # 目录/字段名（如 state_deltas.ledger）不核验
            read_n += 1
            ok = cand.exists() if "*" not in p else bool(list(WS.glob(p)))
            if not ok and "ch_001" in p:      # 有些角色只碰后续章，退一步找任意章
                ok = bool(list(WS.glob(p.replace("ch_001", "ch_*"))))
            if not ok and "vol_01" in p:
                ok = bool(list(WS.glob(p.replace("vol_01", "vol_*"))))
            rec(skill, "路径", p, ok, "" if ok else f"基座内查无此文件（{cand}）")
        if read_n == 0:
            rec(skill, "路径", f"（无可核验的准读输入；准写工件 {write_n} 项已跳过）", True, "")

    fails = [r for r in ROWS if not r["ok"]]
    print(f"\n{'=' * 70}\n📊 SKILL 面审计：{len(ROWS)} 项 ｜ ✅ {len(ROWS) - len(fails)} ｜ ❌ {len(fails)}")
    for r in fails:
        print(f"   ❌ [{r['skill']}/{r['kind']}] {r['item']} ｜ {r['detail'][:180]}")
    (REPO / ".testlab" / "tools" / "skill_surface_result.json").write_text(
        json.dumps(ROWS, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
