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
from typing import Any, Dict, List, Optional, Tuple

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


def collapse_similar_warnings(warnings: List[str], threshold: int = 3) -> List[str]:
    """同类提醒折叠（FIND-CT74 · 作者裁定：无人值守不要刷屏）。

    体检的提醒项常常是「同一类问题 × N 条」（七个地点都缺 sensory_anchor、
    五条伏笔都没排 target_ch）。逐条铺开会让报告长到没人看，无人值守日志更是
    每章刷几十行——**提醒一旦被淹没，就等于没有提醒**。

    处置：按「首个冒号前的类别名」分组，同组 ≥ threshold 条时只保留第一条的完整
    文案（含 💡 方案），并在其中插入「同类共 N 条 + 涉及对象清单」，其余折叠掉。
    单条/双条的提醒原样保留（信息量足够，不需要折叠）。
    本函数**不改判、不降级、不丢弃信息**——只是把重复文案压成一行可扫读的清单。
    """
    if not warnings:
        return warnings

    def _group_key(msg: str) -> str:
        head = re.split(r"[:：]", str(msg), 1)[0]
        return head.strip()[:40]

    groups: Dict[str, List[int]] = {}
    for i, w in enumerate(warnings):
        groups.setdefault(_group_key(w), []).append(i)

    keep: Dict[int, str] = {}
    for _key, idxs in groups.items():
        if len(idxs) < threshold:
            for i in idxs:
                keep[i] = warnings[i]
            continue
        first = warnings[idxs[0]]
        # 抽出每条里的对象标识（[p_001] / loc_006 / KNO-001 之类），压成清单
        objs: List[str] = []
        for i in idxs:
            m = re.findall(r"\[([^\]]{1,40})\]", warnings[i])
            objs.append(m[0] if m else re.split(r"[:：]", warnings[i], 1)[-1].strip()[:24])
        _uniq = list(dict.fromkeys(objs))
        _shown = "、".join(_uniq[:12]) + (f" …等 {len(_uniq)} 项" if len(_uniq) > 12 else "")
        summary = f"（📦 同类共 {len(idxs)} 条，涉及：{_shown}。提醒级，不阻断后续创作）"
        # 插到 💡 方案之前，保证「问题 + 规模 + 处置」在同一条里读完
        if "\n      💡" in first:
            head, tail = first.split("\n      💡", 1)
            keep[idxs[0]] = f"{head} {summary}\n      💡{tail}"
        else:
            keep[idxs[0]] = f"{first} {summary}"
    return [keep[i] for i in sorted(keep)]


def scan_ledger_integrity(workspace: Path) -> Tuple[List[str], List[str]]:
    """台账内部交叉引用自洽体检（v4.3.2 缺陷#20 / #24 · FIND-CT71 分级重构）。

    独立成函数供两处复用：
    - `run_full_check`（Stage 0C 主控体检）；
    - `reconcile_volume`（Stage 4D Librarian 的准跑命令——手册禁止它运行 check，
      若不在对账报告里给出结论，它就无从发现自己被要求上报的 Level 2 冲突）。

    返回 `(errors, warnings)` 两级人读结论；两者皆空表示台账自洽。本函数只读不写。

    FIND-CT71（作者裁定 · 判据不要太死板）：旧版把 a~j 十项交叉校验的**全部**结论
    一律当 error 抛出，直接后果是「伏笔缺 planted_ch」「道具持有者写了个没建档的名字」
    这类**选填/可自愈**的账面瑕疵，与「死人复活」这类**叙事硬矛盾**同罪——体检动辄
    十几条阻断，无人值守巡航里更是每章刷屏。现按「是否会让剧情讲不通」重新定级：
      · error（阻断）：只保留会直接产生叙事穿帮的**真矛盾**——生死状态自相矛盾
        （弧光记死却标在世）。
      · warning（提醒）：其余全部降级。它们要么可自愈（sync 会补/会改，标 🩹），
        要么是选填字段缺漏，要么只是统计口径受扰（时间线顺序、重复轨迹），
        都不该拦住作者写下一章。
    """
    _errs: List[str] = []
    _warns: List[str] = []

    def _err(msg: str) -> None:
        _errs.append(msg)

    def _warn(msg: str) -> None:
        _warns.append(msg)
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
        _factions = _sm.get_factions()
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
                _err(
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
            # FIND-CT36（FN-13·零存在性校验）：旧版对 loc_/fac_ 前缀 holder 全量豁免
            # （`not re.match(r"^(loc_|fac_)", _h)` 直接跳过）——势力/地点 ID 写错
            # （如 fac_099 拼错）永远查不出。按前缀分流到对应表做存在性校验。
            if _h and _h.startswith("loc_"):
                if _h not in _places:
                    _warn(
                        f"台账引用断裂: 道具 [{_iid}] {_ir.get('name')} 的持有地点 [{_h}] 不在 state/places.json 中。"
                        f"\n      💡 方案：请修正为该地点的已建档 ID，或在 state/places.json 补建该地点。"
                    )
            elif _h and _h.startswith("fac_"):
                if _h not in _factions:
                    _warn(
                        f"台账引用断裂: 道具 [{_iid}] {_ir.get('name')} 的持有势力 [{_h}] 不在 state/factions.json 中。"
                        f"\n      💡 方案：请修正为该势力的已建档 ID，或在 state/factions.json 补建该势力。"
                    )
            elif _h and not _known_person(_h):
                _warn(
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
                    _warn(
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
                    _warn(
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
                _warn(
                    f"台账伏笔字段残缺: 伏笔 [{_lid}] {_lr.get('name')} 状态已标记 resolved，"
                    f"但缺少回收章 resolved_ch。"
                    f"\n      💡 方案：请补填 resolved_ch（回收所在章号），"
                    f"或将 status 改回 active 交由后续章节正常回收。"
                )
            if not str(_lr.get("planted_ch", "")).strip():
                _warn(
                    f"台账伏笔字段残缺: 伏笔 [{_lid}] {_lr.get('name')} 缺少埋设章 planted_ch。"
                    f"\n      💡 方案：请补填 planted_ch 以支持卷末对账按卷归属统计。"
                )

        # f) 锁定事实指向的章节应当真实存在于时间线
        # FIND-CT20（FN-1）：旧版 `if _tl_chs:` 整体短路——timeline 为空时校验
        # 悄无声息地"通过"（假阴性）；而 timeline 条目若缺 chapter_id 键，_tl_chs
        # 为空串集合又会让所有锁定事实被批量误报（假阳性）。两种病先后治。
        _tl_all = _sm.get_timeline() or []
        _tl_chs = {str(t.get("chapter_id", "")) for t in _tl_all if isinstance(t, dict)}
        _tl_missing_id = sum(1 for t in _tl_all if isinstance(t, dict) and not str(t.get("chapter_id", "")).strip())
        if _tl_all and not _tl_chs:
            _warn(
                f"台账时间线数据残缺: state/timeline.json 全部 {len(_tl_all)} 条条目均缺失 chapter_id 字段，"
                f"锁定事实指向校验与节奏统计不可信。"
                f"\n      💡 方案：请检查 timeline 条目结构（每条应含 chapter_id/volume_id/title 等键），"
                f"或从快照恢复该表。"
            )
        if _tl_chs:
            for _lf in (_sm.get_locked_facts() or []):
                if not isinstance(_lf, dict):
                    continue
                _ech = str(_lf.get("established_ch", "")).strip()
                if _ech and _ech not in _tl_chs:
                    _warn(
                        f"台账锁定事实指向未入账章节: [{_lf.get('id')}] 确立于 {_ech}，"
                        f"但该章不在 state/timeline.json 中。"
                        f"\n      💡 方案：若该章已被回滚或删除，请一并清理此条锁定事实。"
                    )

        # g) 资金池负余额（FN-3·零实现位）：余额本身不设下限，透支消费会一路
        # 绿灯直到对账崩盘。基线+流水的恒等式保证了负值必为异常。
        _led = _sm.get_ledger() or {}
        for _pname, _bal in (_led.get("pools") or {}).items():
            try:
                _bal_n = float(_bal)
            except (TypeError, ValueError):
                _warn(
                    f"台账资金池数据非法: 池 [{_pname}] 余额为 {_bal!r}（非数值）。"
                    f"\n      💡 方案：请在 state/ledger.json 中将该池余额改为整数。"
                )
                continue
            if _bal_n < 0:
                _warn(
                    f"台账资金池透支: 池 [{_pname}] 当前余额 {_bal_n}（负值）。"
                    f"\n      💡 方案：收支流水已超出基线承载力，请调整后续章节的 ledger delta 安排收入，"
                    f"或修正 state/ledger.json 中该池的流水记录。"
                )

        # h) 恩怨双方同一实体（FN-7·零实现位）：自怨条目会让 cockpit/对账出现
        # 「p_001 欠 p_001」的幽灵关系。
        for _d in (_debts or []):
            if not isinstance(_d, dict):
                continue
            _src = str(_d.get("source_char", "")).strip()
            _tgt = str(_d.get("target_char", "")).strip()
            if _src and _tgt and _src == _tgt:
                _warn(
                    f"台账恩怨自指: 恩怨 [{_d.get('id', 'DEBT')}] 的发起方与承受方同为 [{_src}]。"
                    f"\n      💡 方案：请修正 source_char/target_char 之一，或删除该自怨条目。"
                )

        # i) 关系轨迹重复章（FN-6·零实现位）：sync 侧按 chapter 去重，但手工编辑/
        # 历史导入无校验，重复章让关系轨迹出现分叉。
        for _pair, _r in (_relations or {}).items():
            if not isinstance(_r, dict):
                continue
            _hist = _r.get("history") or []
            _seen_ch: Dict[str, int] = {}
            for _h in _hist:
                if isinstance(_h, dict):
                    _hc = str(_h.get("chapter", "")).strip()
                    if _hc:
                        _seen_ch[_hc] = _seen_ch.get(_hc, 0) + 1
            for _hc, _cnt in _seen_ch.items():
                if _cnt > 1:
                    _warn(
                        f"台账关系轨迹重复: 关系对 [{_pair}] 的 history 中第 {_hc} 章出现 {_cnt} 条记录。"
                        f"\n      💡 方案：请删除重复条目（sync 按章幂等，正常入账不会产生重复）。"
                    )

        # j) 时间线章节顺序倒置（FN-2·确定性子集位）：timeline 的自由文本时间
        # （如「新历47年·霜月三日」）无法确定性解析比对，但 chapter_id 数字序是
        # 结构化的——顺序倒置说明存在手工错插/跨卷漂移。
        _prev_num = None
        _prev_ch = ""
        for _t in (_sm.get_timeline() or []):
            if not isinstance(_t, dict):
                continue
            _tc = str(_t.get("chapter_id", "")).strip()
            _m = re.search(r"(\d+)$", _tc)
            if not _m:
                continue
            _n = int(_m.group(1))
            if _prev_num is not None and _n < _prev_num:
                _warn(
                    f"台账时间线顺序倒置: 第 {_prev_ch} 章之后出现更早的第 {_tc} 章。"
                    f"\n      💡 方案：请检查 state/timeline.json 的条目顺序（一般为手工插入或跨卷拷贝导致）；"
                    f"该顺序影响 cockpit 节奏遥测与卷末统计。"
                )
            _prev_num, _prev_ch = _n, _tc
    except RuntimeError:
        # 坏表/蒸发态交由调用方降级处置（check 已在 2.5 节以 error 报告过，
        # 此处若自行上抛 exit 4 会截断完整报告；reconcile 则记为一行说明）。
        raise
    except Exception as _e:
        # FIND-CT19（probes RB-2·假阴性绿灯）：旧版裸 except: pass——一行畸形数据
        # 即可让 b~j 全部七项交叉校验被静默卸载，reconcile 第五节却显示「自洽」。
        # 现在校验器自身故障也作为一条显式问题输出，绝不做假绿。
        _warn(
            f"台账交叉校验器自身异常（以下校验项结论不可信）: {type(_e).__name__}: {_e}。"
            f"\n      💡 方案：请检查 state/ 各表条目形态（非 dict 条目/类型错误字段），"
            f"修复后重跑 check。"
        )

    # FIND-CT73：凡是 sync 能自己修好的提醒项，统一挂一条 🩹 指引——
    # 让作者/Librarian 一眼看出「这条不用手工改表」，也避免无人值守时把
    # 可自愈的账面瑕疵误读成需要停工处置的重大冲突。
    _HEAL_HINTS = (
        ("台账伏笔字段残缺", "sync 会自动补 planted_ch / resolved_ch 并标注 `_source: inferred`"),
        ("台账引用断裂", "sync 会按姓名/别名自动规范 ID 或取号补建档案"),
        ("台账恩怨自指", "sync 会自动清除该幽灵恩怨条目"),
        ("台账关系轨迹重复", "sync 会按章去重（保留每章最后一条）"),
        ("台账时间线顺序倒置", "sync 会按章号数字序重排 timeline（CT23 已内建）"),
        ("台账资金池数据非法", "sync 会把非数值余额/流水消毒为整数并留痕"),
        ("台账资金池透支", "透支是剧情事实不是数据错误，引擎不阻断；如需回正请安排收入流水"),
        ("强类型枚举越界", "sync 会按同义词表归一 life_status 等枚举；归一不了的自造值引擎不擅自改判"),
        ("数值契约字段", "sync 会解析/夹取/摘除该字段"),
        ("地点数据残缺", "感官物象/环境规则是**选填**创作字段，缺失不阻断；引擎不会替你编造环境描写"),
    )
    _tagged: List[str] = []
    for _w in _warns:
        _h = next((h for k, h in _HEAL_HINTS if k in _w), "")
        if _h:
            _w = (_w + "\n      🩹 自愈/定性：" + _h +
                  "（可自愈项重跑 `python studio.py sync <章号> --force` 即自动修正，"
                  "每一步动作都记入 sync 报告的「🩹 自愈动作」清单）。")
        _tagged.append(_w)
    _warns = _tagged
    return _errs, _warns


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

    # 2.6 核心表缺失巡检（FN-10·零实现位）：旧版只查「存在但损坏」，缺表直接
    # continue——从未初始化的表与损坏表一样致命，却连 warning 都没有。
    # 按表的关键度分级：核心事实表缺失=error（台账不完整），扩展表缺失=warning。
    _CORE_TABLES = {
        "persons.json": "error", "items.json": "error", "lines.json": "error",
        "locked.json": "error", "current.json": "error", "timeline.json": "error",
        "ledger.json": "error", "debts.json": "error", "relations.json": "error",
        "factions.json": "warning", "places.json": "warning", "synopsis.json": "warning",
        "milestones.json": "warning", "sync_log.json": "warning",
        "indices/co_occurrence.json": "warning", "indices/entity_timeline.json": "warning",
    }
    for rel, _sev in _CORE_TABLES.items():
        if not (workspace / "state" / rel).exists():
            _msg = (
                f"核心状态表缺失: state/{rel} 不存在。"
                f"\n      💡 方案：若从未初始化，请运行 `python studio.py init` 重建工作区；"
                f"若曾损坏被隔离，请检查同目录 .corrupt-* 残骸并从快照恢复。"
            )
            if _sev == "error":
                errors.append(_msg)
            else:
                warnings.append(_msg)

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
            elif lrec.get("status") == "active" and not lrec.get("target_ch"):
                # FIND-CT30（FN-5）：无 target_ch 的 active 伏笔旧版永久静默——
                # 从不排程的伏笔事实上无人推进，全书零提醒直到烂尾。埋设章距今
                # 满 10 章仍无排期即提醒（与 Probes 契约一致：提醒级，不阻断）。
                _pl = str(lrec.get("planted_ch", "") or "")
                _mm = re.search(r"(\d+)$", _pl)
                if _mm and curr_num - int(_mm.group(1)) >= 10:
                    warnings.append(f"伏笔长期未排程: 伏笔 [{lid}] {lrec.get('name')} 自第 {_pl} 章埋设后一直是 active，且无 target_ch 回收排期。\n      💡 方案：请在细纲 foreshadowing_deltas 中为其声明 target_ch 排期，或规划 reveal/resolve 推进。")
    except Exception as _e:
        # FIND-CT19 同款：巡检器自身异常不得静默卸载（假阴性绿灯）
        warnings.append(f"伏笔时钟巡检器自身异常（伏笔超期结论不可信）: {type(_e).__name__}: {_e}。\n      💡 方案：请检查 state/lines.json 条目形态后重跑 check。")

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
        "life_status": {"alive", "deceased", "missing", "unknown"},
        "attitude": {"hostile", "neutral", "friendly", "allied"},
    }
    # FIND-CT9（假阳性）：items 的 status 枚举曾与 persons 共用 {active, retired}，
    # 而 state.py 同步侧合法写入 active/consumed/destroyed/lost（state.py:1031-1039）
    # ——凡有道具损毁/消耗的书，check 必打「status='consumed' 不在法定白名单」假
    # warning。按表拆分：道具 status 白名单 = sync 写入域全集。
    _ITEM_STATUS_ENUM = {"active", "consumed", "destroyed", "lost"}
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
                    _enum = _ITEM_STATUS_ENUM if (_k == "status" and _tname == "items") else _ENUMS[_k]
                    if _v_key not in _enum:
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
                            f"{sorted(_enum)} 内{_extra}。"
                            f"\n      💡 方案：{_tip}"
                        )
    except Exception:
        pass

    # 3.4b 数值契约字段类型/区间巡检（S-3·动态实证假阴性）
    # 实测 batch-B：细纲写 tier_rank: "三" / charges: "abc" / danger_tier: "高"
    # 全部静默落账，sync exit 0、check 0 errors 零告警——schema dataclass 无
    # __post_init__ 强制、枚举巡检只管字符串枚举不管数值。数值字段带错类型
    # （或越界）会让排序/比较/统计在下游悄悄退化（str 与 int 不可比即崩栈）。
    # 定级 warning（存量书不锁死），逐字段指出并给修正方案。
    # FIND-CT73：区间表不再在 check 侧复制一份——直接 import state.NUMERIC_FIELD_BOUNDS。
    # 「体检口径」与「自愈口径」必须是同一张表，否则两边漂移就会出现
    # 「体检报越界、自愈不认账」的自相矛盾（缺陷#15 的双份词表正是前车之鉴）。
    # 其中 items.charges / max_charges 下限按 -1 计（FIND-CT37：schema 默认值即 -1，
    # 表示非计数型无限耐久），若按文档字面 >=1 判会误报引擎自家默认值。
    from engine.state import NUMERIC_FIELD_BOUNDS as _NUM_FIELDS
    for _tname, _flds in _NUM_FIELDS.items():
        _tbl = {"persons": state_mgr.get_persons, "items": state_mgr.get_items,
                "factions": state_mgr.get_factions, "places": state_mgr.get_places}[_tname]()
        for _eid, _rec in (_tbl or {}).items():
            if not isinstance(_rec, dict):
                continue
            for _f, _bounds in _flds.items():
                _lo, _hi = (_bounds if isinstance(_bounds, tuple) else (None, None))
                _v = _rec.get(_f)
                if _v is None or _v == "":
                    continue
                if isinstance(_v, bool) or not isinstance(_v, int):
                    warnings.append(
                        f"数值契约字段类型非法（🩹 可自愈）: {_tname}/{_eid} 的 {_f} = {_v!r}（应为整数"
                        f"{f'，区间 {_lo}~{_hi}' if _lo is not None and _hi is not None else ''}）。"
                        f"字符串/浮点数值会让排序与统计悄悄退化。\n"
                        f"      🩹 自愈：重跑 `python studio.py sync <章号> --force`，引擎会解析/夹取该值"
                        f"（解析不出的直接摘除——选填字段留空比塞假值安全），动作记入报告「🩹 自愈动作」。\n"
                        f"      💡 方案：或直接在 state/{_tname}.json 中将该字段改为整数"
                        f"{f'（或从细纲 new_entities 修正声明后重跑 sync --force）' if True else ''}。"
                    )
                elif _lo is not None and _v < _lo:
                    warnings.append(
                        f"数值契约字段越界（🩹 可自愈，sync 会夹取到区间内）: {_tname}/{_eid} 的 {_f} = {_v} 低于下限 {_lo}。"
                        f"\n      💡 方案：请修正为区间内整数{'' if _hi is None else f'（{_lo}~{_hi}）'}。"
                    )
                elif _hi is not None and _v > _hi:
                    warnings.append(
                        f"数值契约字段越界（🩹 可自愈，sync 会夹取到区间内）: {_tname}/{_eid} 的 {_f} = {_v} 超出上限 {_hi}。"
                        f"\n      💡 方案：请修正为区间内整数（{_lo}~{_hi}）。"
                    )

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
        _led_errs, _led_warns = scan_ledger_integrity(workspace)
        errors.extend(_led_errs)
        warnings.extend(_led_warns)
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
                            # FIND-CT8（probes L1·契约归位）：未登记死亡从 error 降回
                            # warning——probes 契约「阻断级仅 2（空正文/确认级认知泄露）」，
                            # 死亡登记的第一责任链是 Auditor 第三节 + proposal auto 回写
                            # （下方 BUG#44 提醒与其互补），此处一句话提醒足够。
                            warnings.append(f"正文疑似未登记角色阵亡: {s['fatalities_and_entities']['detail']}。\n      💡 方案：请在 log/audit/{chapter_id}.md 第 3 节登记该死亡事实并跑 `proposal auto` 回写细纲，或在细纲 locked_facts / state_deltas 显式声明。")
                    # 提醒级汇总
                    # FIND-CT70（作者裁定 · 引擎退出文学性判断）：原「正文体量遥测」
                    # 提醒（severe_short / short / long 三档，源自 BUG#42）已整块撤销。
                    # 章节长短是创作自由：短章、番外、意识流章都合法，引擎不做审美裁决。
                    # 字数只作为**事实计量**出现在探针摘要与审计报告里（words.level 现仅
                    # ok / empty 两档，empty 属数据完整性问题：封存空章会让流水线失去意义）。
                    # v4.3.3 BUG#44：审计报告第 3 节的涌现事实（[阵亡]/[新登场]/[道具变动]）
                    # 由 `proposal auto` 负责吸收并回写细纲 new_entities/state_deltas，
                    # sync 只读细纲。若跳过 proposal auto 直接 sync，审计登记的角色死亡
                    # 会静默丢失且全程零提示——手册称为「严重审计失职」的防线形同虚设。
                    # 此处比对：审计报告有涌现事实、而细纲尚未承载对应声明时提醒。
                    if audit_txt:
                        try:
                            # 彻底剥离 HTML 注释（<!-- ... -->），避免将审计报告模板中的格式说明与示例误判为真实正文事实
                            _clean_audit_txt = re.sub(r"<!--[\s\S]*?-->", "", audit_txt)
                            _emg = []
                            for _rl in _clean_audit_txt.splitlines():
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

                    if s["epistemology"].get("suspected_count"):
                        warnings.append(f"认知盲区疑似命中 ×{s['epistemology']['suspected_count']}（非阻断，请 Auditor 复核）: {s['epistemology']['suspected']}")
                    if not s["grounding"]["passed"]:
                        warnings.append(f"物象落地提醒: {s['grounding']['detail']}")
                    if not s["address"]["passed"]:
                        warnings.append(f"称谓落地提醒: {s['address']['detail']}")
                    if s.get("fatalities_and_entities", {}).get("unregistered_speakers"):
                        warnings.append(f"未建档新出场角色提醒: {', '.join(s['fatalities_and_entities']['unregistered_speakers'])}（请 Auditor 确认是否需在审计报告第 3 节建档）")
                    # FIND-CT22：探针自身记录的前端形态 warning（epistemology/blind_spots
                    # 非法形态、姓名键未归一等）在此显式呈现，避免静默跳过。
                    for _fw in probe_results.get("form_warnings", []):
                        warnings.append(f"细纲形态提醒: {_fw}")


    passed = len(errors) == 0
    return {
        "passed": passed,
        "errors": errors,
        # FIND-CT74：同类提醒折叠后再交付（不改判、不丢信息，只压重复文案）
        "warnings": collapse_similar_warnings(warnings),
        "warnings_raw_count": len(warnings),
        "probe_results": probe_results,
        "unfilled_slots": slot_count,
        "config": {k: cfg[k] for k in ("words_per_chapter", "token_cap") if k in cfg},
    }
