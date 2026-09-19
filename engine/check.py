"""Novel Studio 机械硬闸门与全书体检引擎 (engine/check.py) · v4.3。

双轨深度检查：
1. 配置完整性（project.json 存在性、关键字段与损坏硬失败）
2. 未填占位符闸门 ({{slot:...}}) —— bible/characters/entities/outlines 全量扫描（warning 级清单）
3. 实体 ID 唯一性与因果引用校验（id_tracker.check_id_integrity）
4. 单章确定性物理/事实探针体检（四探针矩阵：字数遥测/认知盲区/法定称谓/物象落地）：
   - 阻断级（errors）：空正文（0字）、确认级角色认知泄露
   - 提醒级（warnings）：疑似泄露、伏笔/道具物象未落地、称谓缺位、细纲 chapter_id 与文件名不一致
5.5 状态表损坏隔离残留巡检（.corrupt-* 文件 warning 显形）
5. 状态表数据异常巡检（如 charges 非法值）
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.config import load_config
from engine.id_tracker import check_id_integrity
from engine.parser import parse_frontmatter
from engine.probes import run_all_probes
from engine.state import StateManager

_SLOT_PATTERN = re.compile(r"\{\{slot:")


def _scan_unfilled_slots(workspace: Path, warnings: List[str]) -> int:
    """扫描模板型文档中的未填槽位，输出逐文件计数（Stage 0C 验收依据）。"""
    scan_targets: List[Path] = []
    for sub in ("bible", "characters", "entities", "outlines"):
        d = workspace / sub
        if d.exists():
            scan_targets.extend(p for p in d.rglob("*.md") if p.is_file())

    total = 0
    for p in scan_targets:
        try:
            txt = p.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            continue
        n = len(_SLOT_PATTERN.findall(txt))
        if n:
            warnings.append(f"未填占位符 ×{n}: {p.relative_to(workspace)}（Stage 0C 门禁要求全部填实）")
            total += n
    if total:
        warnings.insert(0, f"全书共 {total} 个未填槽位 ({{{{slot:}}}}) 待消灭")
    return total


def run_full_check(workspace: Path, chapter_id: Optional[str] = None) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    workspace = Path(workspace)
    try:
        cfg = load_config(workspace)
    except RuntimeError as e:
        # project.json 损坏：体检的职责是报告而非崩溃
        return {
            "passed": False,
            "errors": [f"project.json 损坏，无法解析配置: {e}。\n      💡 方案：请检查该文件 JSON 语法或运行 `python studio.py snapshot rollback <快照名>` 恢复。"],
            "warnings": warnings,
            "probe_results": None,
            "unfilled_slots": 0,
            "config": {},
        }

    # 1. 检查 project.json
    project_file = workspace / "project.json"
    if not project_file.exists():
        errors.append(
            f"书籍工作区未初始化或缺失 project.json（检测路径: {workspace}）。\n"
            f"      💡 方案：请先运行初始化命令: python studio.py init -t <书名> -g <题材> -p <主角名> -w \"{workspace}\""
        )
    else:
        try:
            with open(project_file, "r", encoding="utf-8-sig") as f:
                pdata = json.load(f)
            if not pdata.get("title"):
                warnings.append("project.json 中书名 title 为空。\n      💡 方案：请在 project.json 中补齐 title 字段。")
            if not pdata.get("protagonist"):
                warnings.append("project.json 中主角名 protagonist 为空。\n      💡 方案：请在 project.json 中补齐 protagonist 字段。")
        except Exception as e:
            errors.append(f"project.json 解析失败: {e}。\n      💡 方案：请检查 project.json 的语法格式，或从快照恢复。")

    # 2. 未填占位符闸门（此前 templates/README 承诺但未实现，v4.1 落地）
    slot_count = _scan_unfilled_slots(workspace, warnings)

    # 2.5 状态表完整性巡检（v4.2.1 缺陷#7 落地）：损坏的 JSON 必须报错而非让体检崩溃
    _state_tables = [
        "persons.json", "items.json", "factions.json", "places.json", "lines.json",
        "locked.json", "ledger.json", "current.json", "timeline.json", "synopsis.json",
        "debts.json", "relations.json", "milestones.json", "sync_log.json",
        "indices/co_occurrence.json", "indices/entity_timeline.json",
    ]
    for rel in _state_tables:
        f = workspace / "state" / rel
        if not f.exists():
            continue
        try:
            json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception as e:
            errors.append(f"状态表损坏: state/{rel}（{e}）。\n      💡 方案：请用 `python studio.py snapshot rollback <快照名>` 恢复最近快照。")

    # v4.3：损坏隔离残留显形——.corrupt-* 文件是硬失败机制的历史遗迹，
    # 长期堆积说明曾发生过状态表损坏且未处置，须以 warning 提醒审计。
    state_dir = workspace / "state"
    if state_dir.exists():
        corrupt_leftovers = sorted(p.name for p in state_dir.glob("*.corrupt-*"))
        if corrupt_leftovers:
            warnings.append(
                f"状态表损坏隔离残留 ×{len(corrupt_leftovers)}: {', '.join(corrupt_leftovers[:5])}"
                + (" …" if len(corrupt_leftovers) > 5 else "")
                + "。\n      💡 方案：这些是历史上损坏被自动隔离的状态表副本。若当前体检全域通过且无业务异常，"
                  "确认无用后可手动删除；若需要取证请先归档再清理。"
            )

    # 3. 状态表数据异常巡检（只读告警，不静默改数）
    state_mgr = StateManager(workspace)
    try:
        items_scan = state_mgr.get_items()
    except RuntimeError as e:
        errors.append(str(e))
        items_scan = {}
    for iid, it in items_scan.items():
        charges = it.get("charges", -1)
        if not isinstance(charges, int) or charges < -1:
            warnings.append(f"道具 [{iid}] charges 值非法: {charges!r}（合法范围: >= -1，-1 为非计数型）。\n      💡 方案：请在 state/items.json 中将 charges 修正为合法整数。")

    # 3.1 道具归属与死者平账巡检
    try:
        persons_scan = state_mgr.get_persons()
        from engine.state import is_deceased
        for iid, it in items_scan.items():
            if it.get("status", "active") == "active":
                h = it.get("holder", "")
                for pid, prec in persons_scan.items():
                    if is_deceased(prec):
                        pnames = {prec.get("name", ""), pid}
                        if h in pnames:
                            warnings.append(f"道具归属异常: 活跃道具 [{iid}] {it.get('name')} 的持有者 [{h}] ({pid}) 已阵亡。\n      💡 方案：请在剧情或细纲中声明该道具转移、掉落拾取或损毁。")
    except Exception:
        pass

    # 3.2 伏笔时钟超期巡检
    try:
        lines_scan = state_mgr.get_lines()
        curr_ch = state_mgr.get_current().get("current_ch", "ch_001")
        m_curr = re.search(r"(\d+)$", curr_ch)
        curr_num = int(m_curr.group(1)) if m_curr else 0
        for lid, lrec in lines_scan.items():
            if lrec.get("status") == "active" and lrec.get("target_ch"):
                m_t = re.search(r"(\d+)$", lrec["target_ch"])
                if m_t and curr_num > int(m_t.group(1)):
                    warnings.append(f"伏笔超期未决: 伏笔 [{lid}] {lrec.get('name')} 预排目标为第 {lrec['target_ch']} 章，当前已推进至 {curr_ch} 仍未闭环。\n      💡 方案：请在后续细纲中规划伏笔推进 (reveal) 或回收 (resolve)。")
    except Exception:
        pass

    # 3.3 地点残缺巡检
    try:
        places_scan = state_mgr.get_places()
        for pid, prec in places_scan.items():
            if not prec.get("sensory_anchor") and not prec.get("environment_rules") and not prec.get("summary"):
                warnings.append(f"地点数据残缺: 地点 [{pid}] {prec.get('name')} 缺少感官物象 (sensory_anchor) 与环境规则 (environment_rules)。\n      💡 方案：请在 state/places.json 中补充环境物象以支持写手渲染空间感。")
    except Exception:
        pass

    # 4. 实体与线索 ID 因果引用（损坏表已在 2.5 报告，此处兜底防崩溃）
    try:
        id_res = check_id_integrity(workspace, chapter_id)
    except RuntimeError as e:
        errors.append(f"ID 完整性校验被损坏状态表阻断: {e}。\n      💡 方案：请检查或恢复对应的 state/ JSON 文件。")
        id_res = {"errors": [], "warnings": []}
    errors.extend(id_res.get("errors", []))
    warnings.extend(id_res.get("warnings", []))

    # 5. 若指定了章节，进行单章物理探针体检（字数遥测/认知泄露/称谓落地/物象落地）
    probe_results = None
    if chapter_id:
        curr_vol = state_mgr.get_current().get("current_vol", "vol_01")
        beats_candidates = [workspace / "outlines" / curr_vol / "beats" / f"{chapter_id}.md"]
        if (workspace / "outlines").exists():
            beats_candidates.extend(sorted((workspace / "outlines").glob(f"**/beats/{chapter_id}.md")))
        beats_candidates.append(workspace / "outlines" / f"{chapter_id}.md")
        beats_file = next((b for b in beats_candidates if b.exists()), None)

        if not beats_file:
            errors.append(f"第 {chapter_id} 章细纲文件不存在。\n      💡 方案：请运行 `python studio.py beats new {chapter_id} --write` 装配该章细纲任务卡。")
        else:
            b_txt = beats_file.read_text(encoding="utf-8-sig", errors="replace")
            fm, _ = parse_frontmatter(b_txt)
            if not fm:
                errors.append(f"第 {chapter_id} 章细纲未包含有效 YAML Front-matter 结构体。\n      💡 方案：请检查 {beats_file.name} 顶部是否包含以 '---' 包裹的 YAML 元数据区块。")
            else:
                fm_ch = str(fm.get("chapter_id", "")).strip()
                if fm_ch and fm_ch != chapter_id:
                    warnings.append(f"细纲 front-matter chapter_id={fm_ch} 与文件名/参数 {chapter_id} 不一致。\n      💡 方案：请将细纲中的 chapter_id 统一修改为 {chapter_id}。")
                raw_candidates = [
                    workspace / "manuscript" / curr_vol / "final" / f"{chapter_id}.md",
                    workspace / "manuscript" / curr_vol / "raw" / f"{chapter_id}_v3.md",
                    workspace / "manuscript" / curr_vol / "raw" / f"{chapter_id}_v2.md",
                    workspace / "manuscript" / curr_vol / "raw" / f"{chapter_id}_v1.md",
                ]
                # 回退：跨卷查找 final
                if not raw_candidates[0].exists() and (workspace / "manuscript").exists():
                    for cand in sorted((workspace / "manuscript").glob(f"*/final/{chapter_id}.md")):
                        raw_candidates[0] = cand
                        break
                target_prose = next((r for r in raw_candidates if r.exists()), None)

                if target_prose is None:
                    warnings.append(f"第 {chapter_id} 章尚无正文草稿/定稿，跳过正文探针。\n      💡 方案：如需体检正文，请先派发 Stage 2 (novel-drafter) 起草正文。")
                else:
                    p_txt = target_prose.read_text(encoding="utf-8-sig", errors="replace")
                    audit_file = workspace / "log" / "audit" / f"{chapter_id}.md"
                    audit_txt = audit_file.read_text(encoding="utf-8-sig", errors="replace") if audit_file.exists() else ""
                    probe_results = run_all_probes(p_txt, fm, persons_db=state_mgr.get_persons(), config=cfg, audit_text=audit_txt)
                    s = probe_results["summary"]
                    if not probe_results["all_passed"]:
                        if not s["words"]["passed"]:
                            errors.append(f"正文内容为空（0 字）。\n      💡 方案：请派发 Stage 2 (novel-drafter) 起草正文 {target_prose.name}。")
                        if not s["epistemology"]["passed"]:
                            errors.append(f"正文发生确认级角色认知泄露: {s['epistemology']['leaks']}。\n      💡 方案：角色知晓了不该知道的信息，请修改泄露段落，或在 log/audit/{chapter_id}.md 中写入替换配方。")
                        if not s.get("fatalities_and_entities", {}).get("passed", True):
                            errors.append(f"正文发生未登记角色阵亡: {s['fatalities_and_entities']['detail']}。\n      💡 方案：请在细纲 locked_facts、state_deltas 或 log/audit/{chapter_id}.md 第 3 节中显式登记该死亡事实，杜绝死者幽灵复活！")
                    # 提醒级汇总
                    if s["epistemology"].get("suspected_count"):
                        warnings.append(f"认知盲区疑似命中 ×{s['epistemology']['suspected_count']}（非阻断，请 Auditor 复核）: {s['epistemology']['suspected']}")
                    if not s["grounding"]["passed"]:
                        warnings.append(f"物象落地提醒: {s['grounding']['detail']}")
                    if not s["address"]["passed"]:
                        warnings.append(f"称谓落地提醒: {s['address']['detail']}")
                    if s.get("fatalities_and_entities", {}).get("unregistered_speakers"):
                        warnings.append(f"未建档新出场角色提醒: {', '.join(s['fatalities_and_entities']['unregistered_speakers'])}（请 Auditor 确认是否需在审计报告第 3 节建档）")


    passed = len(errors) == 0
    return {
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "probe_results": probe_results,
        "unfilled_slots": slot_count,
        "config": {k: cfg[k] for k in ("words_per_chapter", "token_cap") if k in cfg},
    }
