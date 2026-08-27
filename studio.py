# -*- coding: utf-8 -*-
"""
Universal Novel Studio - 统一总控 CLI (studio.py)
Unified Command-Line Interface & Task Runner for AI Agents & Human Directors.

Usage:
    python studio.py status                 # 0. 查看当前项目核心数据指标仪表盘
    python studio.py pack ch_004            # 1. 一键装载指定章节的 7 层全量创作语境
    python studio.py lint [ch_004]          # 2. 一键运行反 AI 腔、句式骨架与断章 Linter (--voice 可选加测声纹)
    python studio.py diff ch_004            # 3. 一键初稿 vs 定稿脱水重铸质量对比
    python studio.py sync ch_004            # 4. 一键完成双台账校验、道具轨迹追踪并打下版本快照
    python studio.py radar [ch_004]         # 5. 一键运行全书 12 大工程雷达总控仪表盘
    python studio.py test                   # 6. 一键运行 tests/ 自动化测试套件
    python studio.py export [--txt]         # 7. 一键编译导出全书手稿 (Markdown / TXT)
    python studio.py clean                  # 8. 一键清空手稿与临时草稿
    python studio.py snapshot <name>        # 9. 状态机一键创建快照
    python studio.py snapshots              # 9.1 列出所有历史快照
    python studio.py rollback <name>        # 10. 状态机一键回滚快照 (--clean-drafts 可选清理孤立稿件)
"""

import sys
import json
import re
import subprocess
import argparse
from pathlib import Path

# Add tools directory to sys.path
_root_dir = Path(__file__).resolve().parent
_tools_dir = _root_dir / "tools"
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, reconfigure_utf8, find_manuscript_files

reconfigure_utf8()

def run_script(script_name: str, extra_args: list) -> int:
    """Executes a tool script from tools/ directory with given arguments."""
    script_path = _tools_dir / script_name
    if not script_path.exists():
        print(f"❌ [错误] 未找到工具脚本: {script_path}")
        return 1
    
    cmd = [sys.executable, str(script_path)] + extra_args
    res = subprocess.run(cmd)
    return res.returncode

def cmd_status(args):
    """View quick dashboard status of the novel workspace."""
    workspace_dir = resolve_workspace(args.workspace)
    state_dir = workspace_dir / "04_timeline_and_state"
    manuscript_dir = workspace_dir / "05_manuscript"
    
    # 1. Project Bible Info
    bible_file = workspace_dir / "00_meta" / "project_bible.md"
    title = "未命名小说"
    genre = "通用"
    if bible_file.exists():
        c = bible_file.read_text(encoding="utf-8")
        tm = re.search(r"-\s*\*\*书名.*?\*\*\s*[:：]\s*(.*)", c)
        if tm:
            title = re.sub(r"[《》]", "", tm.group(1).strip())
        gm = re.search(r"-\s*\*\*主类型.*?\*\*\s*[:：]\s*(.*)", c)
        if gm:
            genre = gm.group(1).strip()

    # 2. Manuscript Stats
    finalized_files = find_manuscript_files(manuscript_dir)
    total_words = 0
    for f in finalized_files:
        txt = f.read_text(encoding="utf-8")
        total_words += len(re.findall(r'[\u4e00-\u9fa5]', txt))

    # 3. Double Ledger Pools
    ledger_file = state_dir / "economy_ledger.json"
    pools_summary = []
    if ledger_file.exists():
        try:
            ldata = json.loads(ledger_file.read_text(encoding="utf-8"))
            if "resource_pools" in ldata:
                for k, v in ldata["resource_pools"].items():
                    pools_summary.append(f"{v.get('name', k)}: {v.get('current', 0)} {v.get('unit', '')}")
            elif "current_balance" in ldata:
                pools_summary.append(f"基础货币: {ldata.get('current_balance', 0)}")
        except Exception:
            pass

    # 4. Active Guns & Misunderstandings
    guns_file = state_dir / "chekhov_guns.md"
    active_guns = 0
    if guns_file.exists():
        gc = guns_file.read_text(encoding="utf-8")
        active_guns = len([l for l in gc.splitlines() if any(k in l for k in ["Planted", "Triggered", "In Hand", "Ready"]) and not l.startswith("| 伏笔 ID") and not l.startswith("|---")])

    print("=" * 64)
    print(f" 📊 Universal Novel Studio - 项目状态简报")
    print("=" * 64)
    print(f" 📖 书名: 《{title}》")
    print(f" 🎭 题材: {genre}")
    print(f" 📂 工作区: {workspace_dir.name}")
    print(f" 📝 定稿进度: {len(finalized_files)} 章 | 总字数: 约 {total_words:,} 字")
    print(f" 💰 量化资产池: {' | '.join(pools_summary) if pools_summary else '未建立'}")
    print(f" 🎯 活跃伏笔: {active_guns} 处")
    print("=" * 64)
    return 0

def cmd_pack(args):
    """Stage 2: Package full context for a chapter."""
    ch = args.chapter if args.chapter.startswith("ch_") else f"ch_{int(args.chapter):03d}"
    extra = ["-c", ch]
    if args.json:
        extra.append("--json")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("package_context.py", extra)

def cmd_lint(args):
    """Stage 3: Lint chapter for consistency, generic skeletons, AI clichés & tag leaks, then reader confusion check."""
    extra = []
    if args.chapter:
        ch = args.chapter if args.chapter.startswith("ch_") else f"ch_{int(args.chapter):03d}"
        extra.extend(["-c", ch])
    if args.json:
        extra.append("--json")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    
    rc = run_script("check_consistency.py", extra)
    
    # If --voice is requested and a chapter is specified, also run dialogue voice auditor
    if getattr(args, "voice", False) and args.chapter:
        print("\n" + "─" * 64)
        print(f" 🎙️ [台词声纹与防 OOC 专项诊断] 章节: {ch}")
        print("─" * 64)
        v_extra = ["-c", ch]
        if args.workspace:
            v_extra.extend(["-w", args.workspace])
        run_script("audit_dialogue_voice.py", v_extra)

    # Always run reader confusion check as final gate
    if args.chapter:
        print("\n" + "─" * 64)
        print(f" 👁️ [读者阅读卡点与懵逼检测] 章节: {ch}")
        print("─" * 64)
        c_extra = ["-c", ch]
        if args.workspace:
            c_extra.extend(["-w", args.workspace])
        rc2 = run_script("audit_reader_confusion.py", c_extra)
        if rc2 != 0:
            rc = rc2  # Propagate CRITICAL failure
        
    return rc

def cmd_confusion(args):
    """Stage 3: Detect reader confusion points and comprehension blockers."""
    ch = args.chapter if args.chapter.startswith("ch_") else f"ch_{int(args.chapter):03d}"
    extra = ["-c", ch]
    if args.json:
        extra.append("--json")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("audit_reader_confusion.py", extra)

def cmd_diff(args):
    """Stage 3: Diff raw draft vs finalized quality."""
    ch = args.chapter if args.chapter.startswith("ch_") else f"ch_{int(args.chapter):03d}"
    extra = ["-c", ch]
    if args.json:
        extra.append("--json")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("diff_draft_quality.py", extra)

def cmd_rx(args):
    """Stage 3: Generate layered surgical prescription for a draft."""
    ch_arg = args.chapter
    if ch_arg and ch_arg.isdigit():
        ch_arg = f"ch_{int(ch_arg):03d}"
    extra = ["-c", ch_arg] if ch_arg else []
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("suggest_micro_surgery.py", extra)

def cmd_facts(args):
    """Stage 4: Pre-scan chapter for transactions, injuries, props & active characters."""
    ch = args.chapter if args.chapter.startswith("ch_") else f"ch_{int(args.chapter):03d}"
    extra = ["-c", ch]
    if args.json:
        extra.append("--json")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("extract_chapter_facts.py", extra)

def cmd_apply(args):
    """Stage 4: Apply a structured state-mutation proposal (deterministic state engine)."""
    extra = []
    if getattr(args, "file", None):
        extra.extend(["-f", args.file])
    if getattr(args, "dry_run", False):
        extra.append("--dry-run")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("state_apply.py", extra)

def cmd_doctor(args):
    """Health check: validate workspace structure, ledgers, and state files."""
    extra = []
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("validate_state.py", extra)

def cmd_sync(args):
    """Stage 4: Verify ledgers, track continuity, and automatically snapshot."""
    ch = args.chapter if args.chapter.startswith("ch_") else f"ch_{int(args.chapter):03d}"
    w_arg = ["-w", args.workspace] if args.workspace else []
    
    print("=" * 72)
    print(f" 🔄 [Stage 4 · 状态自同步流水线] 目标章节: {ch}")
    print("=" * 72)

    # 0. Apply any pending structured state-mutation proposals (deterministic engine)
    print("\n[0/3] 正在合并状态变更提案 (state_apply)...")
    rc0 = run_script("state_apply.py", w_arg)
    # rc0 == 0 表示无提案或全部成功；非 0（有失败提案）不中断快照，但给出提示
    if rc0 != 0:
        print("⚠️ 部分状态变更提案未通过校验，请检查 state_inbox/failed/ 后重试。")

    # 1. Verify Double Ledgers
    print("\n[1/3] 正在校验双台账平衡 (verify_double_ledgers)...")
    rc1 = run_script("verify_double_ledgers.py", w_arg)
    if rc1 != 0:
        print("❌ 双台账校验未通过，中断同步！")
        return rc1

    # 2. Track Item Continuity
    print("\n[2/3] 正在核验道具流转轨迹 (track_item_continuity)...")
    rc2 = run_script("track_item_continuity.py", w_arg)
    if rc2 != 0:
        print("❌ 道具轨迹校验未通过，中断同步！")
        return rc2

    # 3. Snapshot
    snapshot_tag = f"{ch}_done"
    print(f"\n[3/3] 正在封存版本快照 ({snapshot_tag})...")
    rc3 = run_script("state_inspector.py", w_arg + ["--snapshot", snapshot_tag])
    
    print("\n" + "=" * 72)
    print(f" ✨ [同步完成] {ch} 状态自同步与版本快照全部就绪！")
    print("=" * 72)
    return rc3

def cmd_radar(args):
    """Run all 12 studio radars."""
    extra = []
    if args.chapter:
        ch = args.chapter if args.chapter.startswith("ch_") else f"ch_{int(args.chapter):03d}"
        extra.extend(["-c", ch])
    if args.json:
        extra.append("--json")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("studio_radar.py", extra)

def cmd_test(args):
    """Run test suite in tests/ directory."""
    print("=" * 72)
    print(" 🧪 [自动化工程测试套件 (Test Suite)] 启动中...")
    print("=" * 72)
    tests_dir = _root_dir / "tests"
    if not tests_dir.exists():
        print(f"❌ 未找到测试目录: {tests_dir}")
        return 1
    
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"]
    res = subprocess.run(cmd, cwd=str(_root_dir))
    return res.returncode

def cmd_export(args):
    """Export whole novel."""
    extra = []
    if args.txt:
        extra.extend(["--format", "txt"])
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("compile_novel.py", extra)

def cmd_init(args):
    """Stage 1: Initialize novel workspace scaffolding for ANY genre."""
    extra = ["--title", args.title, "--genre", args.genre, "--protagonist", args.protagonist]
    if args.clean:
        extra.append("--clean")
    if getattr(args, "force", False):
        extra.append("--force")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("init_new_novel.py", extra)

def cmd_snapshots(args):
    """List all state-machine snapshots."""
    extra = ["--list-snapshots"]
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("state_inspector.py", extra)

def cmd_clean(args):
    """Clean drafts or full manuscript."""
    extra = ["--clean"]
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("init_new_novel.py", extra)

def cmd_snapshot(args):
    """Create a named snapshot."""
    extra = ["--snapshot", args.name]
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("state_inspector.py", extra)

def cmd_rollback(args):
    """Rollback to a snapshot and optionally clean newer drafts."""
    extra = ["--rollback", args.name]
    if args.workspace:
        extra.extend(["-w", args.workspace])
    rc = run_script("state_inspector.py", extra)
    
    if rc == 0 and getattr(args, "clean_drafts", False):
        workspace_dir = resolve_workspace(args.workspace)
        ch_match = re.search(r"ch_(\d+)", args.name)
        if ch_match:
            base_num = int(ch_match.group(1))
            # Scan all manuscript directories (raw_drafts & finalized across all volumes)
            manuscript_dir = workspace_dir / "05_manuscript"
            for f in manuscript_dir.glob("**/ch_*.md"):
                fm = re.search(r"ch_(\d+)", f.name)
                if fm and int(fm.group(1)) > base_num:
                    f.unlink()
                    print(f"   🧹 [清理孤立手稿] 已删除超出快照版本的章节: {f.relative_to(workspace_dir)}")
            # Scan all beats directories across all volumes
            outlines_dir = workspace_dir / "03_outlines"
            for f in outlines_dir.glob("**/beats/ch_*_beats.md"):
                fm = re.search(r"ch_(\d+)", f.name)
                if fm and int(fm.group(1)) > base_num:
                    f.unlink()
                    print(f"   🧹 [清理孤立细纲] 已删除超出快照版本的细纲: {f.relative_to(workspace_dir)}")
    return rc

def main():
    parser = argparse.ArgumentParser(
        description="""
================================================================================
 🚀 Universal Novel Studio - 统一工程总控 CLI (studio.py)
 Agent-First 商业长篇网文全自动创作与质量巡检工程中枢
================================================================================
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
────────────────────────────────────────────────────────────────────────────────
 📖 4 阶段创作与质量门禁标准工作流 (Standard SOP for AI Agents & Humans):
────────────────────────────────────────────────────────────────────────────────
 0. 项目状态巡视 (Stage 0):
    python studio.py status                  # 查看项目进度、字数、资产池与活跃伏笔
    
 1. 单章语境装载 (Stage 2):
    python studio.py pack 6 --json           # 装载第6章全量创作语境 (供Beats细纲推演)
    
 2. 定稿质量门禁与微创诊断 (Stage 3):
     python studio.py lint 6                  # 读感·体验·造句·读者懵逼检测 体验金字塔门禁
     python studio.py lint 6 --voice          # 附带进行核心角色台词声纹指纹与防OOC分析
     python studio.py confusion 6             # 单独运行读者阅读卡点与懵逼检测
     python studio.py rx 6                    # (可选人工审阅) 生成分层靶向微创手术处方
     python studio.py diff 6                  # 初稿 vs 定稿脱水重铸质量对比
    
 3. 状态自同步与版本快照 (Stage 4):
    python studio.py sync 6                  # 双台账核验、道具流转追踪并自动封存版本快照
    
 4. 全维工程雷达与安全网:
    python studio.py radar                   # 一键运行全书 12 大工程雷达总控仪表盘
    python studio.py test                    # 运行自动化单元测试套件
    python studio.py export --txt            # 编译导出全书出版级手稿 (Markdown / TXT)
    python studio.py snapshot ch_006_done    # 手动创建状态机快照
    python studio.py rollback ch_005_done    # 一键回滚到历史快照 (--clean-drafts 清理孤立稿)
────────────────────────────────────────────────────────────────────────────────
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令 (输入 `python studio.py <cmd> -h` 查看单项帮助)")

    # status
    p_status = subparsers.add_parser("status", help="[Stage 0] 查看当前小说项目状态概览与资产指标")
    p_status.add_argument("-w", "--workspace", help="指定工作区路径")
    p_status.set_defaults(func=cmd_status)

    # pack
    p_pack = subparsers.add_parser("pack", help="[Stage 2] 一键装载单章全量创作语境 (用于Beats细纲推演)")
    p_pack.add_argument("chapter", help="目标章节 (如 6 或 ch_006)")
    p_pack.add_argument("-w", "--workspace", help="指定工作区路径")
    p_pack.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出 (Agent 首选用例)")
    p_pack.set_defaults(func=cmd_pack)

    # lint
    p_lint = subparsers.add_parser("lint", help="[Stage 3] 体验金字塔门禁: 读感·体验·造句·读者懵逼检测")
    p_lint.add_argument("chapter", nargs="?", help="目标章节 (如 6 或 ch_006，缺省时扫描全部)")
    p_lint.add_argument("-w", "--workspace", help="指定工作区路径")
    p_lint.add_argument("--voice", action="store_true", help="附带运行角色台词声纹指纹与防OOC分析")
    p_lint.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    p_lint.set_defaults(func=cmd_lint)

    # confusion
    p_confusion = subparsers.add_parser("confusion", help="[Stage 3] 读者阅读卡点与懵逼检测 (幽灵实体/代词迷雾/伏笔无召回/因果虚接)")
    p_confusion.add_argument("chapter", help="目标章节 (如 6 或 ch_006)")
    p_confusion.add_argument("-w", "--workspace", help="指定工作区路径")
    p_confusion.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    p_confusion.set_defaults(func=cmd_confusion)

    # diff
    p_diff = subparsers.add_parser("diff", help="[Stage 3] 初稿 vs 定稿脱水重铸质量对比与感官颗粒度分析")
    p_diff.add_argument("chapter", help="目标章节 (如 6 或 ch_006)")
    p_diff.add_argument("-w", "--workspace", help="指定工作区路径")
    p_diff.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_diff.set_defaults(func=cmd_diff)

    # rx / prescribe
    p_rx = subparsers.add_parser("rx", aliases=["prescribe"], help="[Stage 3] 生成单章分层靶向微创手术处方单 (前后文切片对照)")
    p_rx.add_argument("chapter", nargs="?", help="目标章节 (如 6 或 ch_006)")
    p_rx.add_argument("-w", "--workspace", help="指定工作区路径")
    p_rx.set_defaults(func=cmd_rx)

    # facts
    p_facts = subparsers.add_parser("facts", help="[Stage 4] 0-Token 快速预提取单章资金流水、伤势、重点道具与出场角色")
    p_facts.add_argument("chapter", help="目标章节 (如 12 或 ch_012)")
    p_facts.add_argument("-w", "--workspace", help="指定工作区路径")
    p_facts.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    p_facts.set_defaults(func=cmd_facts)

    # apply
    p_apply = subparsers.add_parser("apply", help="[Stage 4] 确定性合并 state_inbox 中的结构化状态变更提案")
    p_apply.add_argument("-f", "--file", help="指定单个提案 JSON 文件（默认处理整个 state_inbox/）")
    p_apply.add_argument("--dry-run", action="store_true", help="只校验预演，不写入")
    p_apply.add_argument("-w", "--workspace", help="指定工作区路径")
    p_apply.set_defaults(func=cmd_apply)

    # doctor
    p_doc = subparsers.add_parser("doctor", help="工作区健康自检（结构/台账/占位符/快照）")
    p_doc.add_argument("-w", "--workspace", help="指定工作区路径")
    p_doc.set_defaults(func=cmd_doctor)

    # sync
    p_sync = subparsers.add_parser("sync", help="[Stage 4] 双台账校验、道具流转核验与版本快照自同步")
    p_sync.add_argument("chapter", help="目标章节 (如 4 或 ch_004)")
    p_sync.add_argument("-w", "--workspace", help="指定工作区路径")
    p_sync.set_defaults(func=cmd_sync)

    # radar
    p_radar = subparsers.add_parser("radar", help="运行全维 12 大工程雷达总控仪表盘")
    p_radar.add_argument("chapter", nargs="?", help="指定章节 (可选)")
    p_radar.add_argument("-w", "--workspace", help="指定工作区路径")
    p_radar.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_radar.set_defaults(func=cmd_radar)

    # test
    p_test = subparsers.add_parser("test", help="运行自动化单元测试套件")
    p_test.set_defaults(func=cmd_test)

    # export
    p_export = subparsers.add_parser("export", help="编译并导出全书手稿")
    p_export.add_argument("--txt", action="store_true", help="导出为标准缩进 TXT 格式")
    p_export.add_argument("-w", "--workspace", help="指定工作区路径")
    p_export.set_defaults(func=cmd_export)

    # init
    p_init = subparsers.add_parser("init", help="[Stage 1] 初始化全题材新书脚手架工程资产")
    p_init.add_argument("--title", "-t", default="未命名新书", help="小说书名")
    p_init.add_argument("--genre", "-g", default="通用题材", help="小说题材分类")
    p_init.add_argument("--protagonist", "-p", default="主角名", help="主角姓名")
    p_init.add_argument("--clean", action="store_true", help="清空已有稿件与细纲，保留母版")
    p_init.add_argument("--force", action="store_true", help="工作区已有手稿/细纲时仍强制重建（危险）")
    p_init.add_argument("-w", "--workspace", help="指定工作区路径")
    p_init.set_defaults(func=cmd_init)

    # snapshots (list)
    p_snaps = subparsers.add_parser("snapshots", help="列出状态机所有历史版本快照")
    p_snaps.add_argument("-w", "--workspace", help="指定工作区路径")
    p_snaps.set_defaults(func=cmd_snapshots)

    # clean
    p_clean = subparsers.add_parser("clean", help="清空已有稿件与单章细纲")
    p_clean.add_argument("-w", "--workspace", help="指定工作区路径")
    p_clean.set_defaults(func=cmd_clean)

    # snapshot
    p_snap = subparsers.add_parser("snapshot", help="创建指定名称的状态机快照")
    p_snap.add_argument("name", help="快照名称 (如 ch_003_done)")
    p_snap.add_argument("-w", "--workspace", help="指定工作区路径")
    p_snap.set_defaults(func=cmd_snapshot)

    # rollback
    p_roll = subparsers.add_parser("rollback", help="回滚到指定快照")
    p_roll.add_argument("name", help="目标快照名称")
    p_roll.add_argument("--clean-drafts", action="store_true", help="自动清理大于该快照版本的孤立章节稿件")
    p_roll.add_argument("-w", "--workspace", help="指定工作区路径")
    p_roll.set_defaults(func=cmd_rollback)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    rc = args.func(args)
    sys.exit(rc or 0)

if __name__ == "__main__":
    main()
