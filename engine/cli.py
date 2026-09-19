"""Novel Studio 极简确定性 CLI 入口 (engine/cli.py) · v4.2.2。

核心连载闭环命令（30，含无人值守巡航 cruise）：
- init, check, cockpit, status
- beats new（--write/--force 防覆盖守卫）, outline get, pack
- audit, finalize（配方命中/未命中回执）, proposal auto, sync（空正文阻断）
- milestone, calendar, ask, snapshot, reconcile（含逾期伏笔分级）, state rollup（真·归档）
- trace, id next/list/trace
- export（成书导出 md/txt）, style（跨章重复度）
- config get/set/guide（引擎配置中心）

退出码契约（AGENTS.md 铁律）：
- 0 正常通过 ｜ 1 业务/校验阻断 ｜ 2 CLI 参数语法错误 ｜ 3 环境依赖缺失 ｜ 4 系统级故障
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional

from engine import __version__
from engine.check import run_full_check
from engine.config import config_guide_text, get_config_value, load_config, set_config_value
from engine.cockpit import render_cockpit
from engine.errors import BusinessError, GuardError
from engine.ops import (
    ask_fact,
    audit_chapter,
    evidence_candidates,
    finalize_chapter,
    get_beats_scaffold,
    get_calendar,
    id_list,
    id_next,
    init_workspace,
    milestone_achieve,
    milestone_add,
    proposal_auto,
    reconcile_volume,
    rollup_volume,
    simulate_impact,
    snapshot_create,
    snapshot_list,
    snapshot_rollback,
    sync_chapter,
    trace_id,
)
from engine.pack import build_pack


class _StudioArgumentParser(argparse.ArgumentParser):
    """v4.3：argparse 语法错误统一走引擎错误盒（❌+💡 范式），退出码契约 exit 2。

    旧版裸 argparse 只吐干瘪的 usage 一行，与引擎其余阻断信息风格割裂。
    add_subparsers 的 parser_class 缺省继承父类，故全部子命令天然生效。
    """

    def error(self, message: str) -> None:
        sys.stderr.write(
            "\n============================================================\n"
            f"❌ 【CLI 参数语法错误】{message}\n"
            "💡 【解决方案】请核对命令名、必填位置参数与可选参数；完整契约可运行: python studio.py help\n"
            "============================================================\n\n"
        )
        raise SystemExit(2)


def _resolve_workspace(raw_w: Optional[str]) -> Optional[Path]:
    """定位书籍工作区。

    解析优先级：
    1. 显式指定 raw_w：直接解析（若为相对名且在 workspace/ 下存在则自愈定位）
    2. 当前执行目录 cwd 含 project.json（在书目录下执行）
    3. workspace 自身含 project.json（单书直接放 workspace/ 根下）
    4. workspace/<book> 包含且仅包含 1 本书（多书目录单书自动定位）
    5. workspace 存在多本书籍时返回 None（由 main 报错提示用户用 -w 指定）
    6. 尚未建档时默认指向 workspace/（避免污染代码仓库根目录）
    """
    cwd = Path.cwd().resolve()
    if raw_w:
        target = Path(raw_w).resolve()
        if not target.exists() and (cwd / "workspace" / raw_w).exists():
            return (cwd / "workspace" / raw_w).resolve()
        return target

    if (cwd / "project.json").exists():
        return cwd

    ws_dir = cwd / "workspace"
    if (ws_dir / "project.json").exists():
        return ws_dir

    if ws_dir.exists() and ws_dir.is_dir():
        books = [b for b in ws_dir.iterdir() if b.is_dir() and (b / "project.json").exists()]
        if len(books) == 1:
            return books[0]
        if len(books) > 1:
            return None

    return ws_dir if ws_dir.exists() else cwd


def _build_help_data() -> dict:
    return {
        "version": __version__,
        "contract": f"Novel Studio {__version__} 确定性长篇小说创作工业引擎官方 CLI 契约",
        "commands": {
            "init": {"usage": "python studio.py init -t <书名> -g <题材> -p <主角名> -w <工作区>", "desc": "工作区筑基初始化"},
            "check": {"usage": "python studio.py check [ch_XXX] [--json] -w <工作区>", "desc": "全书与单章合规体检（四探针矩阵 + 未填槽位闸门 + 损坏隔离残留巡检）"},
            "cockpit": {"usage": "python studio.py cockpit -w <工作区>", "desc": "主控大盘态势感知（含近10章节奏遥测）"},
            "beats new": {"usage": "python studio.py beats new <ch_XXX> --write [--force] -w <工作区>", "desc": "生成单章细纲任务卡（已有内容时拒写，--force 重置并自动 .bak）"},
            "outline get": {"usage": "python studio.py outline get <ch_XXX> -w <工作区>", "desc": "只读预览细纲脚手架注入结果（不落盘）"},
            "pack": {"usage": "python studio.py pack <ch_XXX> --write -w <工作区>", "desc": "装配细纲上下文生成自完备 pack.md"},
            "audit": {"usage": "python studio.py audit <ch_XXX> --write -w <工作区>", "desc": "运行机械探针生成质检报告骨架"},
            "finalize": {"usage": "python studio.py finalize <ch_XXX> -w <工作区>", "desc": "吸纳 Auditor 预制修补配方完成正文定稿（回执含命中/未命中）"},
            "proposal auto": {"usage": "python studio.py proposal auto <ch_XXX> --write --force -w <工作区>", "desc": "提取细纲状态变更提案（留档件）"},
            "sync": {"usage": "python studio.py sync <ch_XXX> -w <工作区>", "desc": "解析细纲量化数据，封存本章正文并原子同步台账（空正文拒绝封存）"},
            "calendar": {"usage": "python studio.py calendar [N] -w <工作区>", "desc": "查询未来 N 章剧情排产与到期伏笔"},
            "milestone add": {"usage": "python studio.py milestone add --title <标题> --target-ch <章号> --desc <描述> -w <工作区>", "desc": "里程碑规划"},
            "milestone achieve": {"usage": "python studio.py milestone achieve <ms_XXX> -w <工作区>", "desc": "标记里程碑达成"},
            "ask": {"usage": "python studio.py ask \"<关键词>\" -w <工作区>", "desc": "跨章与设定事实查证"},
            "evidence candidates": {"usage": "python studio.py evidence candidates <ch_XXX> -w <工作区>", "desc": "实体候选打捞（扫描当章细纲 frontmatter 声明，发现未登记实体；正文检索请用 ask）"},
            "reconcile": {"usage": "python studio.py reconcile [vol_XX] --write -w <工作区>", "desc": "卷末对账与长程审计（含逾期伏笔必清清单）"},
            "state rollup": {"usage": "python studio.py state rollup [vol_XX] -w <工作区>", "desc": "分卷归档：折叠时间线为 rollup JSON 防长篇膨胀"},
            "simulate impact": {"usage": "python studio.py simulate impact --entity <实体名> --action <动作> -w <工作区>", "desc": "剧情波及测算"},
            "snapshot create": {"usage": "python studio.py snapshot create <快照名> -w <工作区>", "desc": "创建安全备份快照（含 log/ 与 pack.md）"},
            "snapshot list": {"usage": "python studio.py snapshot list -w <工作区>", "desc": "查看历史安全快照清单"},
            "snapshot rollback": {"usage": "python studio.py snapshot rollback <快照名> -w <工作区>", "desc": "回滚工作区至指定快照（回滚前自动备份当前状态 + 对齐清除快照后新增文件）"},
            "trace": {"usage": "python studio.py trace <ID> -w <工作区>", "desc": "物理 ID 全生命周期穿透追踪"},
            "id next": {"usage": "python studio.py id next <类型> -w <工作区>", "desc": "确定性分配下一个不冲突物理 ID"},
            "id list": {"usage": "python studio.py id list [类型] -w <工作区>", "desc": "查看全书物理资产与设定 ID 清单"},
            "export": {"usage": "python studio.py export [--vol vol_XX] [--format md|txt] [--no-digest] -w <工作区>", "desc": "成书导出：final 定稿 → 读者可读书籍（含前情提要页）"},
            "style": {"usage": "python studio.py style [-w <工作区>]", "desc": "文风与招牌动作评估说明（语义交由 Stage 3A 与质检环节）"},
            "cruise": {"usage": "python studio.py cruise [ch_XXX] --until <ch_MMM> [--max-chapters K] [-w 工作区]", "desc": "无人值守巡航：装配细纲→监督机械链→单行心跳→卷末刹车"},
            "status": {"usage": "python studio.py status -w <工作区>", "desc": "查看全局连载状态看板大盘态势"},
            "id trace": {"usage": "python studio.py id trace <ID> -w <工作区>", "desc": "物理 ID 全生命周期穿透追踪"},
            "config get": {"usage": "python studio.py config get [key] -w <工作区>", "desc": "查看引擎配置当前值"},
            "config set": {"usage": "python studio.py config set <key> <value> -w <工作区>", "desc": "调参写入 project.json.engine"},
            "config guide": {"usage": "python studio.py config guide -w <工作区>", "desc": "全部引擎旋钮说明与当前值"},
        },
    }


def _chapter_num_arg(value: str) -> int:
    """argparse type 钩子：把 `ch_010` / `ch010` / `10` 统一解析为整数章号。"""
    s = str(value).strip()
    m = re.fullmatch(r"(?:ch[_-]?)?0*(\d+)", s, flags=re.IGNORECASE)
    if not m:
        raise argparse.ArgumentTypeError(
            f"章号格式非法: {value!r}。请使用 ch_010 或 10 这样的形式。")
    return int(m.group(1))


def main(argv: Optional[List[str]] = None) -> int:
    parser = _StudioArgumentParser(
        prog="studio.py",
        description=f"Novel Studio {__version__} 确定性长篇小说工业化创作引擎",
    )
    parser.add_argument("-w", "--workspace", help="书籍工作区路径", default=None)
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--version", action="version", version=f"Novel Studio {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # init
    p_init = subparsers.add_parser("init", help="初始化新书工作区")
    p_init.add_argument("-w", "--workspace", default=None)
    p_init.add_argument("-t", "--title", default="未命名小说")
    p_init.add_argument("-g", "--genre", default="都市玄幻")
    p_init.add_argument("-p", "--protagonist", default="主角")
    p_init.add_argument("--force", action="store_true", help="工作区已有工程档案时强制重置（覆盖 project.json）")

    # check
    p_check = subparsers.add_parser("check", help="全书静态合规与双轨体检")
    p_check.add_argument("chapter_id", nargs="?", default="")
    p_check.add_argument("-w", "--workspace", default=None)
    p_check.add_argument("--json", action="store_true")

    # cockpit
    p_cockpit = subparsers.add_parser("cockpit", help="主控大盘态势感知")
    p_cockpit.add_argument("-w", "--workspace", default=None)

    # beats
    p_beats = subparsers.add_parser("beats", help="细纲任务卡操作")
    p_beats_sub = p_beats.add_subparsers(dest="subcommand")
    p_b_new = p_beats_sub.add_parser("new", help="生成新细纲任务卡（已存在已填细纲时拒绝覆盖，--force 重置）")
    p_b_new.add_argument("chapter_id")
    p_b_new.add_argument("--write", action="store_true", help="落盘写入（缺省仅预览）")
    p_b_new.add_argument("--force", action="store_true", help="强制重置已有细纲（自动备份 .bak）")
    p_b_new.add_argument("-w", "--workspace", default=None)

    # outline (兼容 alias，只读预览)
    p_ot = subparsers.add_parser("outline", help="大纲操作")
    p_ot_sub = p_ot.add_subparsers(dest="subcommand")
    p_ot_get = p_ot_sub.add_parser("get", help="只读预览细纲脚手架（不落盘）")
    p_ot_get.add_argument("chapter_id")
    p_ot_get.add_argument("-w", "--workspace", default=None)

    # pack
    p_pack = subparsers.add_parser("pack", help="装配自完备上下文数据包")
    p_pack.add_argument("chapter_id")
    p_pack.add_argument("--write", action="store_true")
    p_pack.add_argument("-w", "--workspace", default=None)

    # audit
    p_audit = subparsers.add_parser("audit", help="运行探针生成质检报告")
    p_audit.add_argument("chapter_id")
    p_audit.add_argument("--write", action="store_true")
    p_audit.add_argument("--force", action="store_true", help="强制重置已含 Auditor 成果的质检报告（自动备份 .bak）")
    p_audit.add_argument("-w", "--workspace", default=None)

    # finalize
    p_fin = subparsers.add_parser("finalize", help="应用配方定稿正文")
    p_fin.add_argument("chapter_id")
    p_fin.add_argument("-w", "--workspace", default=None)

    # proposal
    p_prop = subparsers.add_parser("proposal", help="状态提案操作")
    p_prop_sub = p_prop.add_subparsers(dest="subcommand")
    p_prop_auto = p_prop_sub.add_parser("auto", help="自动提取提案")
    p_prop_auto.add_argument("chapter_id")
    p_prop_auto.add_argument("--write", action="store_true")
    p_prop_auto.add_argument("--force", action="store_true")
    p_prop_auto.add_argument("-w", "--workspace", default=None)

    # sync
    p_sync = subparsers.add_parser("sync", help="原子合账并封存本章（空正文拒绝封存）")
    p_sync.add_argument("chapter_id")
    p_sync.add_argument("-w", "--workspace", default=None)
    p_sync.add_argument("--force", action="store_true", help="正文已变化时强制按新版本重新入账")
    p_sync.add_argument("--refresh", action="store_true", help="纯文笔修订：只刷新同步指纹，不重复入账")

    # cruise 无人值守巡航
    p_cruise = subparsers.add_parser("cruise", help="无人值守巡航：装配细纲→监督机械链→单行心跳→卷末刹车")
    p_cruise.add_argument("start_ch", nargs="?", default=None, help="起始章节编号（可选，如 ch_001）")
    p_cruise.add_argument("--until", default=None, help="巡航终点章节（如 ch_010）")
    p_cruise.add_argument("--target", type=int, default=None, help="目标累计封存章数（自动被卷末钳制）")
    p_cruise.add_argument("--max-chapters", type=int, default=None, help="单批次最大连写章数上限")
    p_cruise.add_argument("--vol", default=None, help="卷号（默认取当前卷）")
    p_cruise.add_argument("--once", action="store_true", help="只处理稿件已就绪的章，不等待（测试/CI 用）")
    p_cruise.add_argument("--poll", type=float, default=2.0, help="轮询间隔秒数")
    p_cruise.add_argument("-w", "--workspace", default=None)

    # status
    p_stat = subparsers.add_parser("status", help="查看全局连载状态看板")
    p_stat.add_argument("-w", "--workspace", default=None)
    p_stat.add_argument("--json", action="store_true")

    # calendar
    p_cal = subparsers.add_parser("calendar", help="剧情排产日历")
    p_cal.add_argument("count", nargs="?", type=int, default=3)
    p_cal.add_argument("-w", "--workspace", default=None)

    # ask
    p_ask = subparsers.add_parser("ask", help="事实检索")
    p_ask.add_argument("query")
    p_ask.add_argument("-w", "--workspace", default=None)

    # milestone
    p_ms = subparsers.add_parser("milestone", help="里程碑操作")
    p_ms_sub = p_ms.add_subparsers(dest="subcommand")
    p_ms_add = p_ms_sub.add_parser("add", help="添加里程碑")
    p_ms_add.add_argument("--title", required=True)
    # v4.3.2 缺陷#16：旧版 type=int 只收裸数字，而全系统（细纲 chapter_id、check、
    # cruise、trace、cockpit 提示）统一使用 ch_XXX 章号形态，文档示例也两种写法混用。
    # Architect 按直觉传 --target-ch ch_010 会吃 exit 2 语法错误。改为两种都收，归一存储。
    p_ms_add.add_argument("--target-ch", type=_chapter_num_arg, required=True,
                          help="目标章号，支持 ch_010 或 10 两种写法")
    p_ms_add.add_argument("--desc", default="")
    p_ms_add.add_argument("-w", "--workspace", default=None)
    p_ms_ach = p_ms_sub.add_parser("achieve", help="达成里程碑")
    p_ms_ach.add_argument("milestone_id")
    p_ms_ach.add_argument("-c", "--chapter", default="")
    p_ms_ach.add_argument("-w", "--workspace", default=None)

    # snapshot
    p_snap = subparsers.add_parser("snapshot", help="快照操作")
    p_snap_sub = p_snap.add_subparsers(dest="subcommand")
    p_snap_cr = p_snap_sub.add_parser("create", help="创建快照")
    p_snap_cr.add_argument("name")
    p_snap_cr.add_argument("-w", "--workspace", default=None)
    p_snap_ls = p_snap_sub.add_parser("list", help="查看历史快照")
    p_snap_ls.add_argument("-w", "--workspace", default=None)
    p_snap_rb = p_snap_sub.add_parser("rollback", help="回滚至指定快照（回滚前自动备份当前状态）")
    p_snap_rb.add_argument("name")
    p_snap_rb.add_argument("-w", "--workspace", default=None)

    # reconcile
    p_rec = subparsers.add_parser("reconcile", help="卷末对账（含逾期伏笔分级）")
    p_rec.add_argument("volume_id", nargs="?", default="vol_01")
    p_rec.add_argument("--write", action="store_true")
    p_rec.add_argument("-w", "--workspace", default=None)

    # state
    p_st = subparsers.add_parser("state", help="状态操作")
    p_st_sub = p_st.add_subparsers(dest="subcommand")
    p_st_roll = p_st_sub.add_parser("rollup", help="分卷归档（折叠时间线为 rollup JSON）")
    p_st_roll.add_argument("volume_id", nargs="?", default="vol_01")
    p_st_roll.add_argument("-w", "--workspace", default=None)

    # evidence
    p_ev = subparsers.add_parser("evidence", help="实体打捞")
    p_ev_sub = p_ev.add_subparsers(dest="subcommand")
    p_ev_cand = p_ev_sub.add_parser("candidates", help="打捞候选")
    p_ev_cand.add_argument("chapter_id")
    p_ev_cand.add_argument("-w", "--workspace", default=None)

    # simulate
    p_sim = subparsers.add_parser("simulate", help="影响测算")
    p_sim_sub = p_sim.add_subparsers(dest="subcommand")
    p_sim_imp = p_sim_sub.add_parser("impact", help="波及测算")
    p_sim_imp.add_argument("--entity", default="")
    p_sim_imp.add_argument("--action", default="retcon", help="拟定动作（默认 retcon）")
    p_sim_imp.add_argument("-w", "--workspace", default=None)

    # trace (ID 全生命周期追踪)
    p_tr = subparsers.add_parser("trace", help="物理 ID 全生命周期穿透追踪")
    p_tr.add_argument("target_id", help="要追踪的物理 ID 或实体名称 (如 p_001, it_001, GUN-001, loc_001)")
    p_tr.add_argument("-w", "--workspace", default=None)

    # id (ID 治理与自动发号)
    p_id = subparsers.add_parser("id", help="物理 ID 治理与自动发号器")
    p_id_sub = p_id.add_subparsers(dest="subcommand")
    p_id_next = p_id_sub.add_parser("next", help="分配下一个可用 ID")
    p_id_next.add_argument("category", help="实体类型 (person, item, gun, kno, mis, location, faction, debt, lock, milestone)")
    p_id_next.add_argument("-w", "--workspace", default=None)
    p_id_list = p_id_sub.add_parser("list", help="查看全书物理 ID 清单")
    p_id_list.add_argument("filter_type", nargs="?", default=None, help="可选过滤类型 (如 person, item, line)")
    p_id_list.add_argument("-w", "--workspace", default=None)
    p_id_trace = p_id_sub.add_parser("trace", help="追踪指定物理 ID")
    p_id_trace.add_argument("target_id", help="目标 ID")
    p_id_trace.add_argument("-w", "--workspace", default=None)

    # export (成书导出)
    p_exp = subparsers.add_parser("export", help="成书导出：final 定稿 → 读者可读书籍")
    p_exp.add_argument("--vol", dest="volume", default=None, help="仅导出指定卷（缺省导出全书）")
    p_exp.add_argument("--format", choices=["md", "txt"], default="md", help="输出格式（默认 md）")
    p_exp.add_argument("--no-digest", action="store_true", help="不生成前情提要页")
    p_exp.add_argument("-w", "--workspace", default=None)

    # style (跨章文风重复度)
    # v4.3.2 缺陷#22：style 已于 v4.2 退役为说明性命令（语义评估交由 Stage 3A/4A），
    # 但 CLI 仍保留 --last N 参数且被完全忽略——调用方按参数语义以为"分析了最近 N 章"，
    # 实际一个文件都没读。保留参数以兼容既有调用，但显式标注已失效，帮助文本同步更正。
    p_style = subparsers.add_parser("style", help="文风评估说明（语义评估已交由 Stage 3A/4A）")
    p_style.add_argument("--last", dest="last", type=int, default=10,
                         help="[已失效] 该参数自 v4.2 起被忽略，本命令不再做统计分析")
    p_style.add_argument("-w", "--workspace", default=None)

    # config (引擎配置中心)
    p_conf = subparsers.add_parser("config", help="引擎配置中心")
    p_conf_sub = p_conf.add_subparsers(dest="subcommand")
    p_conf_get = p_conf_sub.add_parser("get", help="查看配置当前值")
    p_conf_get.add_argument("key", nargs="?", default=None)
    p_conf_get.add_argument("-w", "--workspace", default=None)
    p_conf_set = p_conf_sub.add_parser("set", help="调参写入 project.json.engine")
    p_conf_set.add_argument("key")
    p_conf_set.add_argument("value")
    p_conf_set.add_argument("-w", "--workspace", default=None)
    p_conf_guide = p_conf_sub.add_parser("guide", help="全部旋钮说明与当前值")
    p_conf_guide.add_argument("-w", "--workspace", default=None)

    # help
    p_hlp = subparsers.add_parser("help", help="查看官方接口契约")
    p_hlp.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "help":
        ws = None  # help 是纯契约查询，无需工作区
    elif args.command == "init":
        ws = Path(args.workspace).resolve() if args.workspace else (Path.cwd() / "workspace").resolve()
    else:
        ws = _resolve_workspace(args.workspace)
        if ws is None:
            book_list = []
            ws_dir = Path.cwd() / "workspace"
            if (ws_dir / "project.json").exists():
                book_list.append("   - workspace")
            if ws_dir.exists() and ws_dir.is_dir():
                for b in sorted(ws_dir.iterdir()):
                    if b.is_dir() and (b / "project.json").exists():
                        book_list.append(f"   - workspace/{b.name}")
            sys.stderr.write(
                "\n============================================================\n"
                "❌ 【工作区定位阻断】检测到存在多本书籍工作区，无法唯一定位。\n"
                "💡 【解决方案】请在命令中添加 -w 参数显式指定目标工作区，例如：\n"
                + "\n".join(book_list)
                + "\n============================================================\n\n"
            )
            return 2

        if args.command not in ("init", "help", "check") and not (ws / "project.json").exists():
            sys.stderr.write(
                "\n============================================================\n"
                f"❌ 【工作区未建档阻断】目标工作区缺失工程档案: {ws / 'project.json'}\n"
                f"💡 【解决方案】\n"
                f"   1. 若尚未建档，请先运行筑基初始化命令: python studio.py init -t <书名> -g <题材> -p <主角名> -w \"{ws}\"\n"
                f"   2. 若书籍位于其他目录，请使用 -w 参数显式指定，例如: python studio.py {args.command} -w workspace/<书名>\n"
                "============================================================\n\n"
            )
            return 1

    PARENT_COMMANDS = {
        "beats": "new",
        "outline": "get",
        "proposal": "auto",
        "milestone": "add | achieve",
        "snapshot": "create | list | rollback",
        "state": "rollup",
        "evidence": "candidates",
        "simulate": "impact",
        "id": "next | list | trace",
        "config": "get | set | guide",
    }
    if args.command in PARENT_COMMANDS and not getattr(args, "subcommand", None):
        sys.stderr.write(
            "\n============================================================\n"
            f"❌ 【CLI 语法错误】命令 '{args.command}' 缺少必要子命令。\n"
            f"💡 【解决方案】可用子命令为: {PARENT_COMMANDS[args.command]}。\n"
            f"   详情请查看: python studio.py help\n"
            "============================================================\n\n"
        )
        return 2


    try:
        if args.command == "help":
            help_data = _build_help_data()
            if getattr(args, "json", False):
                print(json.dumps(help_data, ensure_ascii=False, indent=2))
            else:
                print(f"📖 {help_data['contract']}:")
                for cmd, cinfo in help_data["commands"].items():
                    print(f"  - {cmd:22s} : {cinfo['desc']} (用法: {cinfo['usage']})")
            return 0

        elif args.command == "init":
            res = init_workspace(ws, args.title, args.genre, args.protagonist, force=getattr(args, "force", False))
            print(f"✅ 工作区初始化成功: 《{res['title']}》 ({res['genre']}) ➔ {res['workspace']}")
            return 0

        elif args.command == "check":
            ch = args.chapter_id if args.chapter_id else None
            chk = run_full_check(ws, ch)
            if getattr(args, "json", False):
                print(json.dumps(chk, ensure_ascii=False, indent=2))
            else:
                print(f"🩺 【全书与单章合规体检报告】")
                print(f"   状态：{'✅ 体检通过 (0 errors)' if chk['passed'] else '❌ 存在阻断性错误'}")
                if chk.get("unfilled_slots"):
                    print(f"   📝 未填槽位：{chk['unfilled_slots']} 处（Stage 0C 门禁要求全部填实，详见警告）")
                if chk["errors"]:
                    print("   ❌ 阻断错误与排错方案：")
                    for e in chk["errors"]:
                        print(f"      - {e}")
                if chk["warnings"]:
                    print("   ⚠️ 警告与待完善项：")
                    for w in chk["warnings"]:
                        print(f"      - {w}")

            return 0 if chk["passed"] else 1

        elif args.command == "cockpit":
            print(render_cockpit(ws))
            return 0

        elif args.command in ("beats", "outline"):
            ch_id = args.chapter_id
            write = bool(getattr(args, "write", False))
            force = bool(getattr(args, "force", False))
            b_res = get_beats_scaffold(ws, ch_id, write_file=write, force=force)
            if write:
                suffix = "（已强制重置，旧文件备份为 .bak）" if force else ""
                print(f"✅ 细纲任务卡已装配: {b_res['target_path']}{suffix}")
            else:
                print(f"👀 预览模式（未落盘）: {b_res['target_path']}")
                print(f"   卷: {b_res['volume_id']} ｜ 注入活跃伏笔提示: {b_res['active_foreshadows_injected']} 条")
                print(f"   加 --write 落盘；若目标已含填写内容需 --force 重置（自动 .bak）")
            return 0

        elif args.command == "pack":
            p_res = build_pack(ws, args.chapter_id, write_file=args.write)
            if args.write:
                print(f"📦 装配包已生成: {p_res['target_pack']} ({p_res['size_bytes']} 字节 ｜ 估算 Token: {p_res.get('estimated_tokens', 0)} / {load_config(ws).get('token_cap', 15000)} ｜ 状态: {p_res.get('status', '正常')})")
                if p_res.get("over_budget"):
                    print("   ⚠️ 装配包超出 token_cap 预算：Drafter 上下文可能被截断，建议拆分细纲或 `config set token_cap`。")
            else:
                print(f"👀 预览模式（未落盘）: {p_res['target_pack']} ｜ 估算 Token: {p_res.get('estimated_tokens', 0)}")
            return 0

        elif args.command == "audit":
            a_res = audit_chapter(ws, args.chapter_id, write_file=args.write,
                                  force=getattr(args, "force", False))
            if args.write:
                if a_res.get("preserved"):
                    print(f"🛡️ 已保留既有质检报告（含 Auditor 修补配方/涌现事实，未覆盖）: {a_res['target_audit']} (字数: {a_res['word_count']})")
                    print("   💡 如需按最新正文重置探针骨架，请追加 --force（旧报告自动备份为 .bak）。")
                else:
                    print(f"🔍 探针骨架已生成: {a_res['target_audit']} (字数: {a_res['word_count']})")
            else:
                print(f"👀 预览模式（未落盘）: 字数: {a_res['word_count']}")
            return 0

        elif args.command == "finalize":
            f_res = finalize_chapter(ws, args.chapter_id)
            print(f"🎯 正文定稿完成: {f_res['final_file']} ({f_res['word_count']} 字，配方 {f_res['replacements_applied']}/{f_res['recipes_total']} 应用)")
            if f_res.get("recipes_missed"):
                print(f"   ⚠️ {f_res['recipes_missed']} 条配方未命中正文（目标片段不在文中），请人工核对：")
                for t in f_res["missed_targets"][:5]:
                    print(f"      - {t}…")
            return 0

        elif args.command == "proposal":
            pr_res = proposal_auto(ws, args.chapter_id)
            print(f"📋 状态提案已生成: {pr_res['proposal_file']}")
            return 0

        elif args.command == "sync":
            s_res = sync_chapter(ws, args.chapter_id, force=getattr(args, "force", False), refresh=getattr(args, "refresh", False))
            if s_res.get("idempotent") or s_res.get("refreshed"):
                print(f"♻️ 第 {s_res['chapter_id']} 章 {s_res.get('note')}")
                return 0
            print(f"🎉 第 {s_res['chapter_id']} 章 《{s_res['title']}》 原子封存成功！字数：{s_res['word_count']} ｜ 累计：{s_res['total_published_words']}")
            for w in s_res.get("warnings", []) or []:
                print(f"   ⚠️ {w}")
            return 0
        elif args.command == "cruise":
            from engine.cruise import run_cruise, _chapter_num
            target_val = args.target
            if target_val is None and getattr(args, "until", None):
                t_num = _chapter_num(args.until)
                if t_num <= 0:
                    sys.stderr.write(f"\n❌ 无法从 --until 解析有效章节号: {args.until}\n\n")
                    return 2
                target_val = t_num
            report = run_cruise(
                ws, target_val, vol_id=args.vol, once=args.once,
                poll_seconds=args.poll, reporter=print,
                start_ch=getattr(args, "start_ch", None),
                max_chapters=getattr(args, "max_chapters", None),
            )
            # v4.3：等待超时同样视为阻断（此前只认 brake，超时会静默 exit 0）
            braked = any(r.get("status") in ("brake", "timeout") for r in report.get("results", []))
            print("🚢 巡航报告: " + json.dumps(report, ensure_ascii=False, default=str)[:1500])
            return 1 if braked else 0


        elif args.command == "status":
            print(render_cockpit(ws))
            return 0

        elif args.command == "calendar":
            c_list = get_calendar(ws, args.count)
            print(f"\n📅 【未来 {args.count} 章排产日历】")
            for c in c_list:
                print(f"   - {c.get('chapter_id')}: 《{c.get('title')}》 ➔ {c.get('event')}")
            print()
            return 0

        elif args.command == "ask":
            ans = ask_fact(ws, args.query)
            print(f"\n🔍 查证关键词: \"{args.query}\"")
            if ans:
                for a in ans:
                    print(f"   - {a}")
            else:
                print("   (未检索到直接匹配的事实)")
            print()
            return 0

        elif args.command == "milestone":
            if getattr(args, "subcommand", "") == "add":
                m = milestone_add(ws, args.title, args.target_ch, args.desc)
                print(f"🚩 里程碑已添加: [{m['id']}] 《{m['title']}》 目标章: 第 {m['target_ch']} 章")
            else:
                m = milestone_achieve(ws, args.milestone_id)
                if m:
                    print(f"🚩 里程碑已标记达成: [{m['id']}] 《{m['title']}》 (达成时间: {m.get('achieved_at')})")
                else:
                    sys.stderr.write(
                        "\n============================================================\n"
                        f"❌ 【业务阻断】未找到对应里程碑: '{args.milestone_id}'\n"
                        "💡 【解决方案】请运行 `python studio.py id list milestone` 查看已登记的里程碑 ID 列表。\n"
                        "============================================================\n\n"
                    )
                    return 1

            return 0

        elif args.command == "snapshot":
            subcmd = getattr(args, "subcommand", "create")
            if subcmd == "create":
                sp = snapshot_create(ws, args.name)
                print(f"💾 安全快照已建立: {sp}")
            elif subcmd == "list":
                snaps = snapshot_list(ws)
                print(f"💾 【历史快照清单】 (工作区: {ws})")
                if snaps:
                    for s in snaps:
                        print(f"   - [{s.get('created_at', '未知时间')}] {s.get('name')} ➔ {s.get('path')}")
                else:
                    print("   (当前工作区暂无历史快照)")
            elif subcmd == "rollback":
                rb_res = snapshot_rollback(ws, args.name)
                print(f"🔄 快照已安全回滚: {rb_res.get('name')} (时间: {rb_res.get('timestamp')})")
                print(f"   🛡️ 回滚前状态已自动备份: {rb_res.get('pre_rollback_snapshot')}")
                if rb_res.get("removed_files"):
                    print(f"   🧹 已对齐清除快照外未来文件 ×{len(rb_res['removed_files'])}: {', '.join(rb_res['removed_files'][:8])}"
                          + (" …" if len(rb_res["removed_files"]) > 8 else ""))
            return 0

        elif args.command == "reconcile":
            r_res = reconcile_volume(ws, args.volume_id, write_file=getattr(args, "write", False))
            if r_res.get("report_file"):
                print(f"📒 卷末对账完成并落盘: {r_res['report_file']}")
            else:
                print(f"📒 卷末对账完成 ({r_res['volume_id']}): 章节 {r_res['chapters_count']} 篇 ｜ 总字数 {r_res['total_words']} 字 ｜ 活跃伏笔 {r_res['active_lines']} 条 ｜ 已回收 {r_res['resolved_lines']} 条")
            if r_res.get("overdue_lines"):
                print(f"   ⛔ 逾期未回收伏笔 {len(r_res['overdue_lines'])} 条: {', '.join(r_res['overdue_lines'])}（本卷必清）")
            return 0

        elif args.command == "state":
            r_res = rollup_volume(ws, args.volume_id)
            print(f"📚 分卷归档完成: {r_res['volume_id']} ｜ 章节 {r_res['chapters_count']} 章 ｜ 总字数 {r_res['total_words']} ｜ 活跃伏笔 {r_res['active_lines']} 条")
            print(f"   归档文件: {r_res['archive_file']}")
            return 0

        elif args.command == "evidence":
            ev_res = evidence_candidates(ws, args.chapter_id)
            cands = ev_res.get("candidates", [])
            print(f"🔎 候选实体打捞结果 (第 {args.chapter_id} 章):")
            if cands:
                for c in cands:
                    print(f"   - [{c.get('type')}] {c.get('name')} (建议定位: {c.get('suggested_role')})")
            else:
                print(f"   ✅ {ev_res.get('message', '未发现未登记关键次要实体，台账完备')}")
            return 0

        elif args.command == "simulate":
            sim_res = simulate_impact(ws, getattr(args, "entity", ""), action=getattr(args, "action", "retcon") or "retcon")
            print(f"🔬 【因果波及与风险测算报告】")
            _ident = sim_res["entity"]
            if sim_res.get("entity_kind", "unknown") != "unknown":
                _ident = (f"{sim_res['resolved_name']} ({sim_res['resolved_id']}"
                          f" ｜ {sim_res['entity_kind']})")
            print(f"   - 测算实体：{_ident} ｜ 拟定动作：{sim_res['action']}")
            print(f"   - 风险等级：{sim_res['risk_level']}")
            if sim_res["affected_chapters"]:
                print(f"   - 波及章节 ({len(sim_res['affected_chapters'])})："
                      f"{', '.join(sim_res['affected_chapters'])}")
            for _label, _key in (
                ("关联伏笔", "affected_lines"),
                ("关联锁定事实", "affected_locked_facts"),
                ("关联恩怨链", "affected_debts"),
                ("关联关系网", "affected_relations"),
                ("关联道具", "affected_items"),
                ("关联地点", "affected_places"),
                ("关联里程碑", "affected_milestones"),
            ):
                _vals = sim_res.get(_key) or []
                if _vals:
                    print(f"   - {_label} ({len(_vals)})：")
                    for _v in _vals:
                        print(f"      · {_v}")
            print(f"   - 操作指引：{sim_res['recommendation']}")
            return 0

        elif args.command == "trace":
            t_res = trace_id(ws, args.target_id)
            print(t_res.get("human_readable", f"未找到 ID: {args.target_id}"))
            return 0

        elif args.command == "export":
            from engine.exporter import export_book
            e_res = export_book(ws, getattr(args, "volume", None), out_format=args.format,
                                include_digest=not args.no_digest)
            print(f"📚 成书导出完成: {e_res['outputs'][0]}")
            print(f"   格式: {e_res['format']} ｜ 章节 {e_res['chapters']} 章 ｜ 总字数 {e_res['total_words']} ｜ 卷: {', '.join(e_res['volumes_exported']) or '-'}")
            if e_res.get("unsealed_chapters"):
                print(f"   ⚠️ 已跳过 {len(e_res['unsealed_chapters'])} 个未封存章节（final 存在但 sync_log 未入账，不参与成书）: {', '.join(e_res['unsealed_chapters'])}")
            if e_res.get("empty_volumes"):
                print(f"   ⚠️ 以下卷无定稿章节已跳过: {', '.join(e_res['empty_volumes'])}")
            return 0

        elif args.command == "style":
            print("🎨 【文风与招牌动作评估说明】")
            print("   ℹ️ 本命令自 v4.2 起为说明性命令，不读取任何章节、不产出统计数据。")
            print("   跨章文风重复度与 AI 味招牌动作已全量交由 Stage 3A (Dehydrator) 与 Stage 4 (Auditor) 语义评估；")
            print("   确定性引擎已彻底移除死板的停用词表与粗粒度 n-gram 统计。")
            if getattr(args, "last", None) not in (None, 10):
                print(f"   ⚠️ 已忽略 --last {args.last}：该参数自 v4.2 起失效，本命令不做章节分析。")
            print("   💡 需要跨章文风体检，请派发 Stage 3A (novel-dehydrator) 或 Stage 4A (novel-auditor)。")
            return 0

        elif args.command == "config":
            subcmd = getattr(args, "subcommand", "guide")
            if subcmd == "get":
                if getattr(args, "key", None):
                    print(json.dumps(get_config_value(ws, args.key), ensure_ascii=False))
                else:
                    print(json.dumps(load_config(ws), ensure_ascii=False, indent=2))
            elif subcmd == "set":
                r = set_config_value(ws, args.key, args.value)
                print(f"🎛️ 配置已更新: {r['key']} = {json.dumps(r['value'], ensure_ascii=False)}")
                print(f"   已写入: {r['project_file']} (engine 节)")
            else:
                print(config_guide_text(ws))
            return 0

        elif args.command == "id":
            subcmd = getattr(args, "subcommand", "list")
            if subcmd == "next":
                n_res = id_next(ws, args.category)
                print(f"🆔 下一个可用物理 ID: {n_res['next_id']} (类型: {n_res['category']}, 当前已用最大编号: {n_res['current_max']:03d})")
            elif subcmd == "trace":
                t_res = trace_id(ws, args.target_id)
                print(t_res.get("human_readable", f"未找到 ID: {args.target_id}"))
            else:
                f_type = getattr(args, "filter_type", None)
                l_res = id_list(ws, f_type)
                print(f"📋 【Novel Studio 物理 ID 资产总账清册】 (工作区: {ws})")
                for cat, items in l_res.items():
                    if items:
                        print(f"\n📁 [{cat.upper()}] (共 {len(items)} 项):")
                        for it in items:
                            status_str = f" ｜ 状态: {it.get('status') or it.get('condition') or it.get('life_status')}" if (it.get('status') or it.get('condition') or it.get('life_status')) else ""
                            fact = it.get('fact')
                            name_val = it.get('name') or it.get('target_char') or ((fact[:25] + '...') if fact else '')
                            print(f"   - {str(it.get('id') or '?'):10s} : {name_val}{status_str}")
            return 0

    except (BusinessError, ValueError, FileExistsError, FileNotFoundError, KeyError) as e:
        if isinstance(e, GuardError):
            title = "守卫拦截 (Guard Block)"
        elif isinstance(e, BusinessError):
            title = "业务阻断 (Business Block)"
        elif isinstance(e, FileNotFoundError):
            title = "文件缺失阻断 (File Not Found)"
        elif isinstance(e, KeyError):
            title = "配置项未知 (Unknown Key)"
        else:
            title = "参数/格式校验阻断 (Validation Error)"

        solution = getattr(e, "solution", None)
        if solution:
            reason = getattr(e, "message", str(e))
        else:
            reason = str(e)
            if "💡" in reason:
                parts = reason.split("💡", 1)
                reason = parts[0].strip()
                solution = parts[1].lstrip(" 方案：").lstrip(" 解决方案：").strip()


        if not solution:
            if isinstance(e, FileNotFoundError):
                fn = getattr(e, "filename", None) or reason
                solution = f"请核对文件路径 `{fn}` 是否正确，或运行对应工步命令生成该文件。"
            elif isinstance(e, KeyError):
                solution = "请检查配置项名称拼写，或运行 `python studio.py config guide` 查看可用选项。"
            elif isinstance(e, ValueError):
                solution = "请检查输入参数的类型与格式是否符合命令规范（可运行 `python studio.py help` 查阅）。"

        box_lines = [
            "\n============================================================",
            f"❌ 【{title}】{reason}",
        ]
        if solution:
            box_lines.append(f"💡 【解决方案】{solution}")
        box_lines.append("============================================================\n")
        sys.stderr.write("\n".join(box_lines) + "\n")
        return 1

    except RuntimeError as e:
        reason = str(e)
        solution = "若涉及 JSON 坏表，请运行 `python studio.py snapshot rollback <快照名>` 恢复；若属权限问题请检查文件系统读写权限。"
        box_lines = [
            "\n============================================================",
            f"💥 【系统/数据完整性故障 (System Fault)】{reason}",
            f"💡 【解决方案】{solution}",
            "============================================================\n",
        ]
        sys.stderr.write("\n".join(box_lines) + "\n")
        return 4

    except Exception as e:  # noqa: BLE001
        reason = f"{type(e).__name__}: {e}"
        solution = "请检查工作区文件完整性；若属剧情因果冲突，可委派 Stage 4C (novel-evolution) 处理；无法自愈请停机联系人类。"
        box_lines = [
            "\n============================================================",
            f"💥 【未预期异常 (Unexpected Exception)】{reason}",
            f"💡 【解决方案】{solution}",
            "============================================================\n",
        ]
        sys.stderr.write("\n".join(box_lines) + "\n")
        return 4


    return 0


if __name__ == "__main__":
    sys.exit(main())
