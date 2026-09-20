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
from engine.state import StateManager, _load_json

_SLOT_PATTERN = re.compile(r"\{\{slot:")
# v4.3.2 缺陷#29：反引号代码跨度内的 `{{slot:...}}` 是文档在**描述**槽位语法本身
# （如 templates/outlines/volume_outline.md 的「卷末判定契约」条款），并非待填槽位。
# 旧版裸匹配把它算作未填占位符 ⇒ 每本新书 init 后都凭空背一个永远消不掉的槽位，
# Stage 0C「全部填实」门禁在设计上就无法达成。此处先剥离行内代码跨度再计数。
_INLINE_CODE = re.compile(r"`+[^`\n]*`+")


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
        n = len(_SLOT_PATTERN.findall(_INLINE_CODE.sub("", txt)))
        if n:
            warnings.append(f"未填占位符 ×{n}: {p.relative_to(workspace)}（Stage 0C 门禁要求全部填实）")
            total += n
    if total:
        warnings.insert(0, f"全书共 {total} 个未填槽位 ({{{{slot:}}}}) 待消灭")
    return total


def scan_ledger_integrity(workspace: Path) -> List[str]:
    """台账内部交叉引用自洽体检（v4.3.2 缺陷#20 / #24）。

    独立成函数供两处复用：
    - `run_full_check`（Stage 0C 主控体检，命中即阻断错误）；
    - `reconcile_volume`（Stage 4D Librarian 的准跑命令——手册禁止它运行 check，
      若不在对账报告里给出结论，它就无从发现自己被要求上报的 Level 2 冲突）。

    返回人读结论列表；空列表表示台账自洽。本函数只读不写。
    """
    _out: List[str] = []
    _sm = StateManager(workspace)
    cfg = load_config(workspace)
    #
    # 背景：Stage 4C (novel-evolution) 处理作者中途改设定/改人设/砍角色/翻转生死时，
    # 手册给它的全部机器能力只有 simulate impact / snapshot / check / ask 四条，
    # 真正的台账改动**全靠手工编辑 state/*.json**——而此前 check 只校验
    # 「细纲 ➔ 台账」单向引用，对台账**内部**的交叉引用零设防。实测注入 5 类
    # 典型手改破绽（复活角色但遗留死亡弧光、删角色留引用、伏笔 resolved 无回收章、
    # 道具持有者指向幽灵 ID、恩怨双方指向幽灵 ID）全部 0 error 放行。
    # 这意味着 evolution 的唯一验收闸门形同虚设，平账结果没有任何机械兜底。
    try:
        _persons = _sm.get_persons()
        _items = _sm.get_items()
        _lines = _sm.get_lines()
        _places = _sm.get_places()
        _debts = _sm.get_debts()
        _relations = _sm.get_relations()
        # 复用 state.py 的唯一死亡语义判断——切勿在此内联复制一份，
        # 两处词表漂移正是缺陷#15 的成因（回归测试中「病故于旧货店」一例即因
        # check 侧内联词表未同步而漏判）。
        from engine.state import is_deceased, get_death_chapter

        # 引擎内置的泛指占位（pack.py/ops.py 均按此识别主角持有物），不算断裂引用
        _generic_refs = {"主角", "protagonist", "未知", "无", "-"}
        _proto_name = str(cfg.get("protagonist", "") or "").strip()

        def _known_person(ref: Any) -> bool:
            """判定人物引用是否可解析（接受物理 ID、姓名、别名或泛指占位）。"""
            s = str(ref or "").strip()
            if not s:
                return True  # 空引用交由各自的必填校验处理，此处不重复报
            if s in _generic_refs or (_proto_name and s == _proto_name):
                return True
            if s in _persons:
                return True
            for _pr in _persons.values():
                if not isinstance(_pr, dict):
                    continue
                if s == str(_pr.get("name", "")).strip():
                    return True
                if s in [str(a).strip() for a in (_pr.get("aliases") or [])]:
                    return True
            return False

        # a) 生死状态自洽：life_status 与 arc_history 死亡弧光互相打架
        for _pid, _pr in _persons.items():
            if not isinstance(_pr, dict):
                continue
            # v4.4.0 FIND-N：死亡弧光判据与 get_death_chapter 同源（该函数只把
            # 真·死亡语义 / 显式 deceased 契约对应的章节列为死亡章），不在外面
            # 再用裸词表预筛——预筛自身就是 FIND-N 假阳性的来源（「几乎死了」误判）。
            _death_ch = get_death_chapter(_pr)
            if _death_ch and not is_deceased(_pr):
                _out.append(
                    f"台账生死状态自相矛盾: 角色 [{_pr.get('name') or _pid}] ({_pid}) 的 "
                    f"life_status 为 '{_pr.get('life_status', '未标注')}'（在世），"
                    f"但弧光轨迹 arc_history 中第 {_death_ch} 章记录了死亡事实。"
                    f"\n      💡 方案：若剧情确为复活/假死翻转，请同步清理或改写该章 arc_history 的 "
                    f"status_out 并在 locked.json 登记翻转事实；若属误改，请将 life_status 改回 deceased。"
                )

        # b) 道具持有者引用
        for _iid, _ir in _items.items():
            if not isinstance(_ir, dict):
                continue
            _h = str(_ir.get("holder", "")).strip()
            if _h and not _known_person(_h) and not re.match(r"^(loc_|fac_)", _h):
                _out.append(
                    f"台账引用断裂: 道具 [{_iid}] {_ir.get('name')} 的持有者 [{_h}] "
                    f"在 state/persons.json 中不存在。"
                    f"\n      💡 方案：请修正 holder 为已建档的角色 ID/姓名，或为该角色补建人物档案。"
                )

        # c) 恩怨链双方引用
        for _d in (_debts or []):
            if not isinstance(_d, dict):
                continue
            for _role, _key in (("发起方", "source_char"), ("承受方", "target_char")):
                _ref = str(_d.get(_key, "")).strip()
                if _ref and not _known_person(_ref):
                    _out.append(
                        f"台账引用断裂: 恩怨 [{_d.get('id', 'DEBT')}] 的{_role} [{_ref}] "
                        f"在 state/persons.json 中不存在（事由: {_d.get('desc', '')}）。"
                        f"\n      💡 方案：请修正该恩怨条目的 {_key}，或为其补建人物档案；"
                        f"若该角色已被剧情移除，请一并删除此恩怨记录。"
                    )

        # d) 关系网双方引用
        for _pair, _r in (_relations or {}).items():
            if not isinstance(_r, dict):
                continue
            for _key in ("source_id", "target_id"):
                _ref = str(_r.get(_key, "")).strip()
                if _ref and not _known_person(_ref):
                    _out.append(
                        f"台账引用断裂: 关系对 [{_pair}] 的 {_key} [{_ref}] "
                        f"在 state/persons.json 中不存在。"
                        f"\n      💡 方案：请修正该关系条目，或为该角色补建档案；"
                        f"若角色已移除，请删除此关系记录。"
                    )

        # e) 伏笔闭环字段自洽
        for _lid, _lr in _lines.items():
            if not isinstance(_lr, dict):
                continue
            if _lr.get("status") == "resolved" and not str(_lr.get("resolved_ch", "")).strip():
                _out.append(
                    f"台账伏笔字段残缺: 伏笔 [{_lid}] {_lr.get('name')} 状态已标记 resolved，"
                    f"但缺少回收章 resolved_ch。"
                    f"\n      💡 方案：请补填 resolved_ch（回收所在章号），"
                    f"或将 status 改回 active 交由后续章节正常回收。"
                )
            if not str(_lr.get("planted_ch", "")).strip():
                _out.append(
                    f"台账伏笔字段残缺: 伏笔 [{_lid}] {_lr.get('name')} 缺少埋设章 planted_ch。"
                    f"\n      💡 方案：请补填 planted_ch 以支持卷末对账按卷归属统计。"
                )

        # f) 锁定事实指向的章节应当真实存在于时间线
        _tl_chs = {str(t.get("chapter_id", "")) for t in (_sm.get_timeline() or [])}
        if _tl_chs:
            for _lf in (_sm.get_locked_facts() or []):
                if not isinstance(_lf, dict):
                    continue
                _ech = str(_lf.get("established_ch", "")).strip()
                if _ech and _ech not in _tl_chs:
                    _out.append(
                        f"台账锁定事实指向未入账章节: [{_lf.get('id')}] 确立于 {_ech}，"
                        f"但该章不在 state/timeline.json 中。"
                        f"\n      💡 方案：若该章已被回滚或删除，请一并清理此条锁定事实。"
                    )
    except RuntimeError:
        # 坏表/蒸发态交由调用方降级处置（check 已在 2.5 节以 error 报告过，
        # 此处若自行上抛 exit 4 会截断完整报告；reconcile 则记为一行说明）。
        raise
    except Exception:
        pass

    return _out


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

    # 1.5 sync 事务哨兵巡检（v4.3.3 FIND-SYNC）
    # sync 入账是一次多表非事务写；哨兵若残留，说明上次 sync 在写盘中途
    # 中断/崩溃，台账可能处于跨表不一致状态。此时任何下游消费都可能读到
    # 半写数据，必须显著报错并给出补救命令。
    try:
        from engine.state import read_sync_sentinel as _rd_sent
        _sent = _rd_sent(workspace)
        if _sent is not None:
            _sent_ch = str(_sent.get("chapter_id", "未知"))
            errors.append(
                f"上次同步未完成：检测到 sync 中断哨兵残留（章节: {_sent_ch}，进程 {_sent.get('pid')}）。"
                f"台账可能处于跨表不一致的中间态。\n      💡 方案：请补跑 `python studio.py sync {_sent_ch} --force`（幂等重放）"
                f"完成入账；若该章已不需入账，可直接删除 state/ 下的哨兵文件。"
            )
    except Exception:
        pass

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
        # v4.3.2 缺陷#14：残骸一律 warning 的定级过轻。残骸分两类，
        # 「正主已恢复」才是历史遗迹（warning）；「正主仍缺席」意味着该表此刻正处于
        # 数据蒸发态，必须 error 阻断，否则体检对着一本丢了台账的书打出 ✅。
        _orphaned, _historic = [], []
        for name in corrupt_leftovers:
            origin = name.split(".corrupt-")[0]
            (_historic if (state_dir / origin).exists() else _orphaned).append(name)
        if _orphaned:
            errors.append(
                f"状态表损坏后未恢复 ×{len(_orphaned)}: {', '.join(_orphaned[:5])}"
                + (" …" if len(_orphaned) > 5 else "")
                + "。对应的正主状态表至今缺失，台账处于蒸发态。"
                  "\n      💡 方案：请立即用 `python studio.py snapshot list` + "
                  "`snapshot rollback <快照名>` 恢复；或修复隔离文件后改回原名。"
            )
        if _historic:
            warnings.append(
                f"状态表损坏隔离残留 ×{len(_historic)}: {', '.join(_historic[:5])}"
                + (" …" if len(_historic) > 5 else "")
                + "。\n      💡 方案：这些是历史上损坏被自动隔离的状态表副本（正主已恢复）。"
                  "若当前体检全域通过且无业务异常，确认无用后可手动删除；若需要取证请先归档再清理。"
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

        # v4.3.3 BUG#38：地点登记只按细纲 location 字面建号，无同名归并。
        # 「顺天府正堂」与「顺天府·正堂」仅差一个间隔号即被登记为两个 loc_ID，
        # 环境字段要各补一遍，细纲简报还可能取到错误的那一条。此处做归一化重名提示。
        _seen: Dict[str, List[str]] = {}
        for pid, prec in places_scan.items():
            _n = re.sub(r"[·・\s\-—_、]", "", str(prec.get("name", "")))
            if _n:
                _seen.setdefault(_n, []).append(f"[{pid}] {prec.get('name')}")
        for _n, _dups in _seen.items():
            if len(_dups) > 1:
                warnings.append(
                    f"地点重复登记: {' / '.join(_dups)} 归一化后同名，疑为同一地点被分配了多个 ID。\n"
                    f"      💡 方案：请在 state/places.json 中合并为单一 ID，并统一后续细纲 location 的写法。"
                )
    except Exception:
        pass

    # 3.4 强类型枚举白名单巡检（v4.3.2 缺陷#27）
    #
    # 背景：templates/README.md 九处宣称 type/role/status/life_status/attitude 为
    # 「严格枚举」，实测引擎**零校验**——把 life_status 改成 '半死不活'、
    # attitude 改成文档明令严禁的 'disposition'，check 依旧 0 errors 放行。
    # 危害不止于文档失信：engine/probes.py:376 的死亡探针按
    # `life in ("deceased","dead")` 判定，任何拼写变体（'已故'/'Deceased '/'dead人'）
    # 都会让已死角色被当作活人，继续触发死亡误报；cockpit 与 id_tracker 亦照原样展示。
    # 处置取向：报 warning 而非 error——存量书可能已有自造值，硬阻断会锁死工程；
    # 但必须让作者看见，且给出法定枚举以便收敛。
    _ENUMS = {
        "type": {"person", "item", "location", "place", "faction", "other"},
        "role": {"protagonist", "deuteragonist", "antagonist", "ally", "supporting"},
        "status": {"active", "retired"},
        "life_status": {"alive", "deceased", "missing"},
        "attitude": {"hostile", "neutral", "friendly", "allied"},
    }
    try:
        # v4.4.0 FIND-L3：显式生死契约经 L1 归一化，`_LIFE_STATUS_NORM` 是「中文显式
        # 声明 → 法定枚举」的唯一映射。用它识别「显式契约拼写非法」——与把自由文本
        # 误写进 life_status 的灰区口径区分开，给作者精确的修复提示。
        from engine.state import _LIFE_STATUS_NORM as _LSN
        for _tname, _tbl, _keys in (
            ("persons", state_mgr.get_persons(), ("type", "role", "status", "life_status", "attitude")),
            ("items", state_mgr.get_items(), ("type", "status")),
            ("factions", state_mgr.get_factions(), ("type", "attitude")),
            ("places", state_mgr.get_places(), ("type",)),
        ):
            for _eid, _rec in (_tbl or {}).items():
                if not isinstance(_rec, dict):
                    continue
                for _k in _keys:
                    _v = _rec.get(_k)
                    if _v in (None, ""):
                        continue
                    _v_key = str(_v).strip().lower()
                    if _v_key not in _ENUMS[_k]:
                        _extra = ""
                        _tip = f"请在 state/{_tname}.json 中改为法定枚举值。"
                        if _k == "life_status":
                            if str(_v).strip() in _LSN and _LSN[str(_v).strip()] in _ENUMS[_k]:
                                # 中文显式声明未被归一化直接落库——sync 之外的旧档
                                _extra = (
                                    "（该值属显式生死契约的中文写法，但未归一化为法定枚举——"
                                    "死亡相关硬裁决将按 **deceased** 生效，建议手工改为 'deceased' 或重跑 sync 归一）"
                                )
                            else:
                                _extra = (
                                    "（⚠️ 该字段被死亡探针按 deceased/dead 精确匹配消费，"
                                    "非法值会让已故角色被当作在世，持续触发死亡误报）"
                                )
                        if _k == "attitude" and _v_key == "disposition":
                            _extra = "（templates/README 明令严禁使用 `disposition`）"
                        warnings.append(
                            f"强类型枚举越界: {_tname}/{_eid} 的 {_k} = {_v!r} 不在法定白名单 "
                            f"{sorted(_ENUMS[_k])} 内{_extra}。"
                            f"\n      💡 方案：{_tip}"
                        )
    except Exception:
        pass

    # 3.5 定稿 ⇄ 合账对账巡检（v4.3.2 缺陷#28）
    #
    # 背景：单章 sync 依序写 14 张表，每张各自原子（_save_json 用 tmp+os.replace），
    # 但**整体无事务**。实测把 debts.json 替换为目录让第 4.5 节 os.replace 单点失败，
    # 前序的 items/ledger 已落盘（charges 7→6、灵石 -10→-20），而末尾的 sync_log
    # 未记录该章 —— 形成半提交。所幸 sync 本身幂等，重跑不会二次扣账。
    #
    # 真正无人兜底的是更普遍的一类：章节已定稿（final/ch_XXX.md 存在）却从未合账
    # （sync_log 无该章）。此前 `sync_log.json` 在 check 全文**只出现在坏表清单里**，
    # 零对账逻辑 —— 整章剧情的台账变更永久遗失且全链路零告警。
    try:
        _synced = _load_json(workspace / "state" / "sync_log.json", default={})
        _synced_keys = set(_synced.keys()) if isinstance(_synced, dict) else {
            (x.get("chapter_id") or x.get("chapter")) for x in _synced if isinstance(x, dict)
        }
        _ms_root = workspace / "manuscript"
        if _ms_root.is_dir():
            for _vd in sorted(_ms_root.iterdir()):
                _fdir = _vd / "final"
                if not _fdir.is_dir():
                    continue
                for _ff in sorted(_fdir.glob("ch_*.md")):
                    _cid = _ff.stem
                    if _cid not in _synced_keys:
                        warnings.append(
                            f"章节已定稿但未合账: {_vd.name}/final/{_ff.name} 已落盘，"
                            f"但 state/sync_log.json 中无 {_cid} 记录——该章的台账变更"
                            f"（人物/道具/伏笔/资金/恩怨）很可能整章遗失。"
                            f"\n      💡 方案：运行 `python studio.py sync {_cid}` 补合账"
                            f"（sync 幂等，已合账的章重跑不会二次扣账）。"
                        )
    except Exception:
        pass

    # 3.6 里程碑时钟超期巡检（v4.3.2 缺陷#25）
    #
    # 背景：伏笔有 3.2 节的超期告警，里程碑却零校验——`milestones.json` 此前
    # 全文只在坏表清单里出现过一次。Stage 0B/0E (Architect) 唯一的写命令就是
    # milestone add，排产的目标章一旦被剧情甩在身后，cockpit 仍永远显示
    # 「⏳ 待达成」，主控据此以为主线仍在轨，实为一张永不兑现的空头支票。
    try:
        _ms = _load_json(workspace / "state" / "milestones.json", default=[])
        _cur = state_mgr.get_current().get("current_ch", "ch_001")
        _mc = re.search(r"(\d+)$", _cur)
        _cur_num = int(_mc.group(1)) if _mc else 0
        for _m in (_ms if isinstance(_ms, list) else []):
            if not isinstance(_m, dict) or _m.get("status") == "achieved":
                continue
            _tc = _m.get("target_ch")
            _tn = int(_tc) if isinstance(_tc, int) else (
                int(re.search(r"(\d+)$", str(_tc)).group(1))
                if _tc and re.search(r"(\d+)$", str(_tc)) else None
            )
            if _tn is None:
                continue
            if _cur_num > _tn:
                warnings.append(
                    f"里程碑排产超期: [{_m.get('id')}] 《{_m.get('title')}》 目标为第 {_tn} 章，"
                    f"当前已推进至 {_cur} 仍未达成。"
                    f"\n      💡 方案：若已在剧情中兑现，请将其 status 改为 achieved；"
                    f"若仍要推进，请改排到未来章次。"
                )
    except Exception:
        pass

    # 3.7 台账内部交叉引用完整性巡检（v4.3.2 缺陷#20，实现见 scan_ledger_integrity）
    #
    # 背景：Stage 4C (novel-evolution) 平账时全靠手工编辑 state/*.json，而此前
    # check 只校验「细纲 ➔ 台账」单向引用，对台账内部交叉引用零设防——实测 5 类
    # 典型手改破绽全部 0 error 放行，evolution 的唯一验收闸门形同虚设。
    try:
        errors.extend(scan_ledger_integrity(workspace))
    except RuntimeError as e:
        warnings.append(
            f"台账交叉引用巡检因状态表不可用而跳过: {e}"
            "\n      💡 方案：请先按上文指引恢复状态表，再重新体检。"
        )
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
                    # BUG#42：体量偏离在体检阶段即提示，不必等 sync 入账后才告知。
                    _wlv = s["words"].get("level", "ok")
                    if _wlv in ("severe_short", "short", "long"):
                        _tip = ("请确认是否为有意短章；若正文被截断请补全后重新 finalize"
                                if _wlv != "long" else "请确认是否为有意长章，或考虑拆分")
                        warnings.append(f"正文体量遥测: {s['words']['detail']}。\n      💡 方案：{_tip}。")
                    # v4.3.3 BUG#44：审计报告第 3 节的涌现事实（[阵亡]/[新登场]/[道具变动]）
                    # 由 `proposal auto` 负责吸收并回写细纲 new_entities/state_deltas，
                    # sync 只读细纲。若跳过 proposal auto 直接 sync，审计登记的角色死亡
                    # 会静默丢失且全程零提示——手册称为「严重审计失职」的防线形同虚设。
                    # 此处比对：审计报告有涌现事实、而细纲尚未承载对应声明时提醒。
                    if audit_txt:
                        try:
                            _emg = []
                            for _rl in audit_txt.splitlines():
                                _l = re.sub(r"^[-*+]\s*", "", _rl.strip())
                                # 标签可写作组合形式（如模板默认的 [阵亡/死亡]），故按"标签内含关键词"匹配
                                _mt = re.match(r"^\[(.*?)\]|^【(.*?)】", _l)
                                _tg = ((_mt.group(1) or _mt.group(2)) if _mt else "") or ""
                                _m = _mt if any(_k in _tg for _k in (
                                    "阵亡", "死亡", "牺牲", "新登场", "新实体", "新角色",
                                    "新人物", "道具", "物品", "装备")) else None
                                if _m and not any(_ph in _l for _ph in
                                                  ("待修改原句", "待填写角色名", "待填写新角色名", "待填写道具名", "待填写")):
                                    _emg.append(_l[:60])
                            if _emg:
                                _prop = workspace / "state" / "inbox" / f"proposal_{chapter_id}.json"
                                # 判据须按「具体实体名」比对，而非「细纲是否有任何声明」——
                                # 细纲通常本就含主角 character_status，宽判据会永远误判为已消化。
                                _fm_ne = fm.get("new_entities") or []
                                _fm_sd = fm.get("state_deltas") or {}
                                _fm_blob = json.dumps(
                                    {"ne": _fm_ne if isinstance(_fm_ne, list) else [],
                                     "sd": _fm_sd if isinstance(_fm_sd, dict) else {}},
                                    ensure_ascii=False,
                                )
                                _undigested = []
                                for _el in _emg:
                                    # 从「名称: X」「角色: X」「道具: X」中取实体名
                                    _nm = re.search(r"(?:名称|角色|道具|物品|装备)\s*[:：]\s*([^｜|，,。;；]+)", _el)
                                    _nm_s = _nm.group(1).strip() if _nm else ""
                                    if _nm_s and _nm_s not in _fm_blob:
                                        _undigested.append(_el)
                                if _undigested and not _prop.exists():
                                    _emg = _undigested
                                    warnings.append(
                                        f"审计涌现事实未消化: log/audit/{chapter_id}.md 第 3 节登记了 {len(_emg)} 条涌现事实"
                                        f"（如 {_emg[0]}），但细纲未见对应声明且未生成状态提案。这些事实不会入账。\n"
                                        f"      💡 方案：请先运行 `python studio.py proposal auto {chapter_id} --write --force`"
                                        f" 将涌现事实回写细纲，再执行 sync。"
                                    )
                        except Exception:
                            pass

                    # BUG#43：对白占比遥测（dehydrator 手册第 5 节规定 25%~55%）
                    if not s.get("dialogue_ratio", {}).get("passed", True):
                        warnings.append(f"对白占比遥测: {s['dialogue_ratio']['detail']}。\n      💡 方案：对白与叙述配比失衡会影响阅读节奏，请 Stage 3A 调稿时留意（非阻断，体裁性偏离可忽略）。")
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
