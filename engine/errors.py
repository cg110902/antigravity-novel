"""Novel Studio 统一业务错误契约 (engine/errors.py)。

BusinessError：可预期的业务阻断（守卫拦截、文件缺失、校验不过）。
CLI 捕获后以退出码 1 输出人话提示；其余未预期异常以退出码 4 上报，
使调用方可机判区分「业务排错」与「系统故障」（对应 AGENTS.md 退出码铁律）。
"""
from __future__ import annotations


class BusinessError(Exception):
    """业务级阻断：调用方需对照提示排错修复后重试（退出码 1）。"""

    def __init__(self, message: str, solution: str | None = None):
        self.message = message.strip()
        self.solution = solution.strip() if solution else None
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.solution:
            if "💡" in self.message:
                return self.message
            return f"{self.message}\n💡 解决方案：{self.solution}"
        return self.message


class GuardError(BusinessError):
    """数据安全守卫触发（如拒绝覆盖 SSOT、空正文封存拦截）。"""

