"""Novel Studio 状态持久化与状态机统一入口 (engine/ledger.py)。"""
from __future__ import annotations

from engine.state import (
    StateManager,
    _ensure_dir,
    _load_json,
    _save_json,
)

# 统一别名
StateLedger = StateManager
