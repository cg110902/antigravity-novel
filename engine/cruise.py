"""无人值守巡航监督器 (Cruise Supervisor) v4.2。

引擎没有创作能力——写作永远由作者（人或外部写作代理）完成。
cruise 的职责是"编排与安全"，而非代笔：

1. 装配：为计划章批量生成细纲脚手架（含伏笔雷达注入）；
2. 监督：等待作者把 raw_v3（或 final）落盘后，自动执行
   finalize → check → proposal → sync 的机械链；
3. 心跳：每章一行单行摘要（单行可被无人值守日志直接采集）；
4. 安全带：cruise_human_gate 每 K 章暂停，等 `.cruise_gate` 哨兵文件出现才继续；
   批次报告强制附伏笔雷达（§4.7 建议 b）；
5. 刹车：到达卷末章自动执行 state rollup + reconcile --write + export 后停止；
   任何 GuardError/BusinessError 立即刹车并输出批次报告。
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from engine.check import run_full_check
from engine.config import load_config
from engine.errors import BusinessError, GuardError
from engine.exporter import export_book
from engine.ops import (
    _count_words,
    _find_volume_outline,
    _load_json,
    get_beats_scaffold,
    finalize_chapter,
    proposal_auto,
    sync_chapter,
    reconcile_volume,
    rollup_volume,
)


def _chapter_num(chapter_id: str) -> int:
    m = re.search(r"(\d+)$", chapter_id)
    return int(m.group(1)) if m else 0


def _chapter_id(num: int) -> str:
    return f"ch_{num:03d}"


def _volume_last_chapter(workspace: Path, vol_id: str) -> Optional[str]:
    """从卷纲标题行解析卷内最大章号。

    v4.3 缺陷#C13：标题行右侧仍是未填槽位（{{slot:...}}）的"纯槽位章"不参与
    卷末判定——否则模板自带的占位行（如 ch_999 预留位）会把卷末钳到天外，
    让巡航永远踩不到卷末刹车链。
    """
    outline = workspace / "outlines" / vol_id / "outline.md"
    if not outline.exists():
        return None
    nums = []
    for line in outline.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        m = re.match(r"^###\s+ch_(\d+)[:\s]", line)
        if m and "{{slot:" not in line:
            nums.append(int(m.group(1)))
    return _chapter_id(max(nums)) if nums else None


def _sealed_chapters(workspace: Path, vol_id: str) -> List[str]:
    """已封存章（final 字数>0 且已入 sync_log——刹车章 final 无账，不算封存）。"""
    final_dir = workspace / "manuscript" / vol_id / "final"
    if not final_dir.exists():
        return []
    sync_log = _load_json(workspace / "state" / "sync_log.json", default={})
    out = []
    for f in final_dir.glob("ch_*.md"):
        if _count_words(f.read_text(encoding="utf-8-sig", errors="replace")) > 0 and f.stem in sync_log:
            out.append(f.stem)
    return sorted(out, key=_chapter_num)


def _draft_exists(workspace: Path, vol_id: str, chapter_id: str) -> Optional[Path]:
    """作者产出就绪的判定：raw_v3/v2/v1 或 final 任一存在。"""
    raw = workspace / "manuscript" / vol_id / "raw"
    for name in (f"{chapter_id}_v3.md", f"{chapter_id}_v2.md", f"{chapter_id}_v1.md"):
        p = raw / name
        if p.exists():
            return p
    p = workspace / "manuscript" / vol_id / "final" / f"{chapter_id}.md"
    return p if p.exists() else None


def plan_cruise(
    workspace: Path,
    target: Optional[int] = None,
    vol_id: Optional[str] = None,
    start_ch: Optional[str] = None,
) -> Dict[str, Any]:
    """计算巡航计划：从当前水位（或 start_ch）起，连续规划到 min(target, 卷末)。

    target 语义：希望达成的"累计封存章数"（非增量），自动被卷末章数钳制。
    若未指定 target，缺省规划至当前卷卷末。
    """
    if vol_id is None and start_ch:
        # 跨卷巡航定位：工程主档 current_vol 只在 sync 后刷新——0E 交付新卷卷纲后、
        # 首章 sync 之前，project.json 仍停留在旧卷。此时优先按 start_ch 在
        # outlines/ 中的实际所属卷定位，防止误把旧卷卷末当作巡航终点而提前触发
        # 卷末刹车链（rollup/reconcile/export）。
        _outline, vol_id = _find_volume_outline(workspace, start_ch)
    if vol_id is None:
        project = _load_json(workspace / "project.json", default={})
        vol_id = project.get("current_status", {}).get("current_vol") or "vol_01"
    sealed = _sealed_chapters(workspace, vol_id)
    last = _volume_last_chapter(workspace, vol_id)
    if last is None:
        raise BusinessError(
            f"分卷大纲 outlines/{vol_id}/outline.md 未找到任何 '### ch_XXX' 标题行，无法规划巡航。",
            solution=f"请检查分卷大纲文件是否存在且包含标准章节规划（例如 '### ch_001: 标题'）。",
        )

    m_last = _chapter_num(last)
    effective_target = int(target) if target is not None else m_last
    n_now = _chapter_num(sealed[-1]) if sealed else 0
    start_n = _chapter_num(start_ch) if start_ch else (n_now + 1)
    goal = min(effective_target, m_last)
    clamped = effective_target > m_last
    planned = [_chapter_id(i) for i in range(start_n, goal + 1)]
    return {
        "vol_id": vol_id,
        "sealed_now": n_now,
        "volume_last": m_last,
        "target": effective_target,
        "goal": goal,
        "clamped": clamped,
        "planned": planned,
        "is_volume_end": goal >= m_last,
    }


def _heartbeat(chapter_id: str, title: str, res: Dict[str, Any], sealed_total: int) -> str:
    """单行心跳：无人值守日志可直接采集。"""
    flag = "♻️ 幂等跳过" if res.get("idempotent") else "✅ 封存"
    warn = "" if not res.get("warnings") else f" | ⚠️x{len(res['warnings'])}"
    # FIND-CT73：自愈动作在无人值守日志里必须可见（🩹xN），否则引擎"悄悄把表改好了"
    heal = "" if not res.get("healed") else f" | 🩹x{len(res['healed'])}"
    return (
        f"🚢 [cruise] {datetime.now().strftime('%H:%M:%S')} {chapter_id} 《{title}》 {flag}"
        f" | {res.get('word_count', 0)}字 | check {res.get('check_errors', 0)}err"
        f"{warn}{heal} | 累计 {sealed_total} 章"
    )


def supervise_once(workspace: Path, chapter_id: str, force: bool = False) -> Dict[str, Any]:
    """对单章执行 finalize→check→proposal→sync 机械链，返回心跳数据。"""
    from engine.ops import audit_chapter
    audit_chapter(workspace, chapter_id, write_file=True)
    f_res = finalize_chapter(workspace, chapter_id)
    c_res = run_full_check(workspace, chapter_id)
    if c_res.get("errors"):
        # v4.2：体检有阻断错误 → 刹车，绝不带伤入账
        return {"status": "brake", "chapter_id": chapter_id,
                "error": f"check 阻断错误 {len(c_res['errors'])} 项: {c_res['errors'][0]}"}
    proposal_auto(workspace, chapter_id)
    try:
        s_res = sync_chapter(workspace, chapter_id, force=force)
    except GuardError:
        # 正文变化未 --force：巡航模式视同作者修订；先自动快照再按新版本重入账
        from engine.ops import snapshot_create
        snapshot_create(workspace, f"pre_force_sync_{chapter_id}")
        s_res = sync_chapter(workspace, chapter_id, force=True)
    out = dict(s_res)
    out["final_word_count"] = f_res.get("word_count", 0)
    out["check_errors"] = len(c_res.get("errors", []))
    out["recipe_applied"] = f_res.get("replacements_applied", 0)
    return out


def run_cruise(
    workspace: Path,
    target: Optional[int] = None,
    vol_id: Optional[str] = None,
    once: bool = False,
    poll_seconds: float = 2.0,
    reporter: Optional[Callable[[str], None]] = None,
    start_ch: Optional[str] = None,
    max_chapters: Optional[int] = None,
) -> Dict[str, Any]:
    """巡航主循环。once=True 时只处理"稿件已就绪"的章节，不等待（测试/CI 用）。"""
    say = reporter or (lambda s: None)
    # FIND-CT34（cruise L2·死飞）：下游等待循环 `waited += poll_seconds`，
    # poll_seconds ≤ 0 时 waited 永不增长 ⇒ `waited < wait_timeout` 恒真 ⇒
    # 循环退化为 100% CPU 自旋，900s 超时安全网彻底失效，只能靠外力杀进程。
    # 入口统一钳制到下限 0.5s（0/负数均无轮询意义）。
    if poll_seconds is None or poll_seconds <= 0:
        poll_seconds = 0.5
        say("🚢 [cruise] ⚠️ 轮询间隔 ≤ 0 会导致等待循环死飞（超时安全网失效），已钳制为 0.5s")
    cfg = load_config(workspace)
    max_ch = int(max_chapters) if max_chapters is not None else int(cfg.get("cruise_max_chapters", 10))
    gate_every = int(cfg.get("cruise_human_gate", 0) or 0)
    wait_timeout = float(cfg.get("cruise_wait_timeout", 900))

    plan = plan_cruise(workspace, target, vol_id, start_ch=start_ch)
    if len(plan["planned"]) > max_ch:
        plan["planned"] = plan["planned"][:max_ch]
        plan["clamped_by_batch_cap"] = True
    say(
        f"🚢 [cruise] 计划: vol={plan['vol_id']} 当前已封存 {plan['sealed_now']} 章"
        f" → 目标 {plan['goal']} 章 (目标值 {plan['target']}"
        f"{'，已被卷末钳制' if plan['clamped'] else ''})"
        f" | 待巡: {','.join(plan['planned']) or '无'}"
    )

    sealed_total = plan["sealed_now"]
    results: List[Dict[str, Any]] = []
    batch_start = sealed_total

    for i, chapter_id in enumerate(plan["planned"]):
        # 装配：缺细纲则生成脚手架（含伏笔雷达）
        outline_file, _ = _find_volume_outline(workspace, chapter_id)
        beats_file = (
            workspace / "outlines" / plan["vol_id"] / "beats" / f"{chapter_id}.md"
        )
        if not beats_file.exists():
            get_beats_scaffold(workspace, chapter_id, write_file=True)
            say(f"🚢 [cruise] {chapter_id} 细纲脚手架已装配（伏笔雷达注入）")

        # 监督：等待作者产出
        draft = _draft_exists(workspace, plan["vol_id"], chapter_id)
        if draft is None:
            if once:
                say(f"🚢 [cruise] {chapter_id} 等待作者产出（once 模式跳过）")
                continue
            waited = 0.0
            say(f"🚢 [cruise] {chapter_id} 等待作者落盘 raw_v3 …")
            while draft is None and waited < wait_timeout:
                time.sleep(poll_seconds)
                waited += poll_seconds
                draft = _draft_exists(workspace, plan["vol_id"], chapter_id)
            if draft is None:
                say(f"🚢 [cruise] ⏱️ {chapter_id} 等待超时({wait_timeout:.0f}s)，刹车。")
                # v4.3：超时留痕——批次报告标记 timeout，CLI 据此 exit 1（此前超时静默成功退出）
                results.append({"chapter_id": chapter_id, "status": "timeout",
                                "error": f"等待作者产出超时({wait_timeout:.0f}s)"})
                break

        try:
            res = supervise_once(workspace, chapter_id)
        except (GuardError, BusinessError) as e:
            say(f"🚢 [cruise] 🛑 {chapter_id} 引擎刹车: {e}")
            results.append({"chapter_id": chapter_id, "status": "brake", "error": str(e)})
            break
        if res.get("status") == "brake":
            say(f"🚢 [cruise] 🛑 {chapter_id} 体检未过，刹车: {res.get('error')}")
            results.append({"chapter_id": chapter_id, "status": "brake", "error": res.get("error")})
            break

        sealed_total += 0 if res.get("idempotent") else 1
        say(_heartbeat(chapter_id, res.get("title", ""), res, sealed_total))
        results.append({"chapter_id": chapter_id, "status": "sealed", "res": res})

        # 安全带 a)：human_gate 每 K 章暂停等哨兵文件
        if (
            gate_every > 0
            and (sealed_total - batch_start) % gate_every == 0
            and i < len(plan["planned"]) - 1
        ):
            gate = workspace / ".cruise_gate"
            if once:
                say(f"🚢 [cruise] 🎗️ human_gate：已巡 {sealed_total - batch_start} 章（once 模式不阻塞）")
            else:
                say(f"🚢 [cruise] 🎗️ human_gate：已巡 {sealed_total - batch_start} 章，等待 .cruise_gate 哨兵文件 …")
                while not gate.exists():
                    time.sleep(poll_seconds)
                # v4.2.1 缺陷#18：哨兵用过即删——旧版不删除，同批次后续 gate 直通失效
                gate.unlink(missing_ok=True)
                say("🚢 [cruise] 🎗️ 哨兵确认（已消费），继续巡航。")

    # 卷末刹车 + 批次报告（伏笔雷达）
    sealed_list = _sealed_chapters(workspace, plan["vol_id"])
    reached_end = plan["is_volume_end"] and plan["goal"] > 0 and _chapter_id(plan["goal"]) in sealed_list
    batch_report: Dict[str, Any] = {
        "vol_id": plan["vol_id"],
        "planned": plan["planned"],
        "sealed_total": sealed_list and len(sealed_list) or 0,
        "results": [
            {
                "chapter_id": r["chapter_id"],
                "status": r["status"],
                **({"error": r["error"]} if r.get("error") else {"word_count": r["res"].get("word_count", 0)}),
                # FIND-CT73：批次报告带上自愈条目，无人值守跑完能一眼看出引擎改过什么
                **({} if r.get("error") else {
                    "healed": (r["res"].get("healed") or [])[:8],
                    "healed_count": len(r["res"].get("healed") or []),
                }),
            }
            for r in results
        ],
    }
    if reached_end:
        say("🚢 [cruise] 🎬 卷末自动刹车：state rollup + reconcile + export")
        batch_report["rollup"] = rollup_volume(workspace, plan["vol_id"])
        batch_report["reconcile"] = reconcile_volume(workspace, plan["vol_id"], write_file=True)
        batch_report["export"] = export_book(workspace)
        say(f"🚢 [cruise] 🎬 卷末刹车完成，成书导出于: {batch_report['export'].get('outputs')}")
    else:
        active = _active_gun_line(workspace)
        say(f"🚢 [cruise] 批次结束：伏笔雷达 {active} 条活跃")
    return batch_report


def _active_gun_line(workspace: Path) -> int:
    """活跃伏笔计数（供批次摘要）。"""
    try:
        from engine.ledger import StateLedger

        return len(StateLedger(workspace).get_active_foreshadowings())
    except Exception:
        return -1
