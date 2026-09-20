"""Novel Studio 状态持久化与状态机统一入口 (engine/ledger.py)。

⚠️ FIND-CT50（L-1·身份澄清）：本模块是 **StateManager 的统一别名/导入转发层**，
**不是资金池账本入口，也不是死代码**：
- 资金池（ledger）台账的真入口是 `engine/state.py` 的 `StateManager.ledger_file`
  （`state/ledger.json`）与 `engine/schema.py` 的 `LedgerRecord`（pools/transactions）；
- ops.py / cruise.py 等约 15 处 `from engine.ledger import StateLedger` 依赖本路径，
  `StateLedger(workspace)` 即 StateManager 实例，提供全部八表读写能力；
- 历史上文件名 ledger.py 易被误读为"资金账本专属入口"（本次审计即因此生疑），
  保留转发层以兼容既有导入路径，不做收敛改写。
"""
from __future__ import annotations

from engine.state import (
    StateManager,
    _ensure_dir,
    _load_json,
    _save_json,
)

# 统一别名：StateLedger 即 StateManager（stats 全表入口），与资金池表无专属对应关系
StateLedger = StateManager
