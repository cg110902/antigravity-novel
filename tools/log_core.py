# -*- coding: utf-8 -*-
"""
统一日志模块 (log_core.py)
=========================
基于标准库 ``logging``，为全工具链提供一致的日志接口与「可选模块降级」日志。

设计目标：
- 零第三方依赖；
- 所有工具通过 ``get_logger(__name__)`` 获取同一棵 logger 树（``novel_studio.*``）；
- 可选依赖（如 track_character_decay / memory_core）导入失败时，统一用
  ``degrade()`` 记录 WARNING，而不是 ``except Exception: pass`` 悄悄失效；
- 关键路径（配置解析、台账读写等）不允许静默吞异常，至少 ERROR 并抛出。

用法::

    from log_core import get_logger, degrade
    logger = get_logger(__name__)

    try:
        import some_optional_module
    except ImportError as e:
        degrade(logger, "some_optional_module", e)
"""
import sys
import logging

# 根 logger：所有 novel_studio.* 子 logger 都挂在这棵树上
_ROOT_LOGGER = logging.getLogger("novel_studio")
_ROOT_LOGGER.setLevel(logging.INFO)
_ROOT_LOGGER.propagate = False  # 避免重复输出到 root logger

# 标记是否已安装 handler，防止重复 import 时叠加
_HANDLER_INSTALLED = False


def _ensure_handler():
    """惰性安装 StreamHandler（stderr），可被 set_verbose/set_debug 调整级别。"""
    global _HANDLER_INSTALLED
    if not _HANDLER_INSTALLED:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        _ROOT_LOGGER.addHandler(handler)
        _HANDLER_INSTALLED = True


_ensure_handler()


def get_logger(name: str) -> logging.Logger:
    """获取一个 ``novel_studio.<name>`` 子 logger。

    传入 ``__name__`` 即可，例如 ``get_logger("package_context")``。
    """
    if name and not name.startswith("novel_studio"):
        # 去掉常见的 tools. 前缀，让日志名简短一致
        short = name.split(".")[-1] if "." in name else name
        return _ROOT_LOGGER.getChild(short)
    return _ROOT_LOGGER.getChild(name)


def set_verbose():
    """开启详细日志（DEBUG 级别）。"""
    _ROOT_LOGGER.setLevel(logging.DEBUG)


def set_debug():
    """开启调试日志（DEBUG 级别，与 set_verbose 等效，语义别名）。"""
    _ROOT_LOGGER.setLevel(logging.DEBUG)


def set_quiet():
    """静默：只保留 WARNING 及以上级别（供 --quiet 使用）。"""
    _ROOT_LOGGER.setLevel(logging.WARNING)


def degrade(logger, module_name: str, exc):
    """可选模块降级统一日志。

    当某个可选功能（如角色掉线提醒、RAG 资料员）导入或运行失败时调用，
    以 WARNING 级别记录模块名与异常信息，便于定位「功能悄悄失效」问题。

    :param logger: 调用方的 logger（get_logger 返回值）
    :param module_name: 降级的模块/功能名，如 "track_character_decay"
    :param exc: 捕获到的异常对象
    """
    logger.warning(
        "可选模块 %s 不可用，该功能已降级跳过（%s: %s）",
        module_name, type(exc).__name__, exc,
    )
