"""Novel Studio 引擎配置中心 (engine/config.py)。

所有可调旋钮（每章字数参考标尺、Token 预算、通用资金池、巡航上限与安全带等）
统一收敛于此：默认值 ← project.json.scope（字数）← project.json.engine（覆盖）。

配置优先级（高 → 低）：
1. project.json.engine.*       —— 本书显式调参（`studio.py config set <key> <value>`）
2. project.json.scope.words_per_chapter —— 项目体量设定
3. DEFAULT_CONFIG              —— 引擎内置默认

设计动机：
统一全书字数参考标尺、Token 预算、巡航守卫等全局确定性旋钮，消除散落各处的硬编码，
本模块作为配置唯一事实源（SSOT），全引擎统一自此读取。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.errors import BusinessError

DEFAULT_CONFIG: Dict[str, Any] = {
    # 正文字数指引（每章推荐参考体量，用于细纲与写手提示词参考，不做硬性拦截）
    "words_per_chapter": [1500, 2600],
    # v4.3.3 BUG#43：对白行占比区间（dehydrator 手册第 5 节规定 25%~55%）
    "dialogue_ratio": [25, 55],
    # 装配包 Token 预算上限
    "token_cap": 15000,
    # 细纲 state_deltas.ledger 未声明 pool 时使用的默认货币池名（全题材中性，可按书改为 灵石/人民币/积分…）
    "default_pool": "通用资金池",
    # 无人值守巡航单批次上限（章）
    "cruise_max_chapters": 10,
    "cruise_human_gate": 0,
    "cruise_wait_timeout": 900,
}

# config guide 展示用的旋钮说明
CONFIG_GUIDE: Dict[str, str] = {
    "words_per_chapter": "每章正文参考体量区间 [min, max]（作为提示词体量指引，不做代码硬性拦截）",
    "dialogue_ratio": "对白行占比参考区间 [min%, max%]（探针 warning 级遥测，体裁性偏离可忽略）",
    "token_cap": "装配包 pack.md Token 预算上限",
    "default_pool": "细纲 ledger 未声明货币池时的默认池名（全题材可按书覆盖）",
    "cruise_max_chapters": "无人值守巡航单批次最大章数",
    "cruise_human_gate": "巡航安全带：每巡 N 章暂停等待 .cruise_gate 哨兵（0=关闭）",
    "cruise_wait_timeout": "巡航等待作者单章产出的超时秒数",
}


def _read_project(workspace: Path) -> Dict[str, Any]:
    p = Path(workspace) / "project.json"
    if not p.exists():
        return {}
    # v4.2.1 缺陷#15：损坏的 project.json 不得静默吞掉（旧版返回 {}，
    # 下一次 config set 会用空表覆盖真实工程档案，造成无痕配置蒸发）
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"project.json 损坏: {p}（{e}）。引擎拒绝以空配置继续；"
            f"请用 `snapshot rollback` 恢复或手工修复该文件。"
        ) from e
    except OSError as e:
        raise RuntimeError(f"project.json 不可读: {p}（{e}）。请检查磁盘与权限。") from e
    return data if isinstance(data, dict) else {}


def load_config(workspace: Path) -> Dict[str, Any]:
    """解析全书生效配置：默认值 ← scope.words_per_chapter ← engine.* 覆盖。"""
    cfg: Dict[str, Any] = dict(DEFAULT_CONFIG)
    pdata = _read_project(Path(workspace))

    scope = pdata.get("scope") or {}
    if isinstance(scope, dict):
        wpc = scope.get("words_per_chapter")
        if isinstance(wpc, (list, tuple)) and len(wpc) == 2:
            try:
                cfg["words_per_chapter"] = [int(wpc[0]), int(wpc[1])]
            except (TypeError, ValueError):
                pass

    engine_cfg = pdata.get("engine") or {}
    if isinstance(engine_cfg, dict):
        for k, v in engine_cfg.items():
            if k in DEFAULT_CONFIG:
                cfg[k] = v
    return cfg


def get_config_value(workspace: Path, key: str) -> Any:
    cfg = load_config(workspace)
    if key in cfg:
        return cfg[key]
    raise BusinessError(
        f"未知配置项: '{key}'",
        solution="请运行 `python studio.py config guide` 查看所有可用配置项及其当前值。",
    )


def set_config_value(workspace: Path, key: str, value: Any) -> Dict[str, Any]:
    """把调参写入 project.json.engine（合法键校验 + JSON 值解析）。"""
    if key not in DEFAULT_CONFIG:
        raise BusinessError(
            f"未知配置项: '{key}'",
            solution="请运行 `python studio.py config guide` 查看所有可用配置项及其含义。",
        )
    # 类型对齐默认值
    default = DEFAULT_CONFIG[key]
    if isinstance(default, list):
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                parsed = [x.strip() for x in value.split(",") if x.strip()]
        else:
            parsed = value
        if not isinstance(parsed, list):
            raise BusinessError(
                f"配置项 '{key}' 格式错误: 应为列表（如 '[1500, 2600]' 或逗号分隔）",
                solution=f"正确示例: python studio.py config set {key} \"[1500, 2600]\"",
            )
        value = parsed

    elif isinstance(default, (int, float)) and not isinstance(default, bool):
        value = type(default)(value)
    elif isinstance(default, bool):
        if isinstance(value, str):
            value = value.strip().lower() in ("1", "true", "yes", "on")

    p = Path(workspace) / "project.json"
    pdata = _read_project(p.parent)
    if not pdata:
        pdata = {"engine": {}}
    eng = pdata.setdefault("engine", {})
    eng[key] = value
    # v4.2.1：改用原子写盘（临时文件 + os.replace），断电不再产生半截 project.json
    from engine.state import _save_json as _atomic_save
    _atomic_save(p, pdata)
    return {"key": key, "value": load_config(p.parent)[key], "project_file": str(p)}


def config_guide_text(workspace: Path) -> str:
    cfg = load_config(workspace)
    lines = [
        "🎛️ 【Novel Studio 引擎配置指南 (config guide)】",
        "   配置优先级：project.json.engine > project.json.scope > 内置默认",
        f"   调参命令：python studio.py config set <key> <value>   ｜ 查看当前值：python studio.py config get [key]",
        "",
    ]
    for k, desc in CONFIG_GUIDE.items():
        lines.append(f"   - {k}")
        lines.append(f"       说明: {desc}")
        lines.append(f"       当前值: {json.dumps(cfg[k], ensure_ascii=False)}")
    return "\n".join(lines)
