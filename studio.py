#!/usr/bin/env python3
"""Novel Studio 薄壳入口：sys.path 注入后调用 engine.cli.main（业务逻辑一律在 engine/*）。

依赖缺失属于环境问题，不是业务阻断也不是用法错：此前 `engine.cli` 在 import 期
就抛 ModuleNotFoundError 裸 traceback，退出码 1（与「体检有 errors」同码），
调用方无法区分「书有问题」和「环境没装好」。这里在 import 期兜住，给人话提示
并用独立退出码 3（见 engine/README.md 退出码契约）。
"""
import os
import sys
from pathlib import Path

# 彻底解决 Windows 控制台默认 GBK 编码引发的中文乱码与 Unicode (Emoji/特殊标点) 编码报错
if sys.platform == "win32":
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    for _stream in (sys.stdout, sys.stderr, sys.stdin):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

ENV_EXIT_CODE = 3
 

try:
    from engine.cli import main  # noqa: E402
except SyntaxError as _exc:  # 引擎源码与本机 Python 版本不兼容
    sys.stderr.write(
        "\n❌ 引擎源码与本机 Python 版本不兼容，无法启动。\n"
        f"   当前解释器：{sys.executable} "
        f"(Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})\n"
        f"   错误详情：{_exc}\n"
        "   修复：请改用 Python 3.9+ 的解释器运行 studio.py（本引擎零三方依赖）。\n\n"
    )
    raise SystemExit(ENV_EXIT_CODE) from None
except ImportError as _exc:  # 依赖没装 / 装错解释器
    _missing = getattr(_exc, "name", None) or str(_exc)
    sys.stderr.write(
        "\n❌ 运行环境异常，引擎无法启动。\n"
        f"   缺失模块：{_missing}\n"
        f"   当前解释器：{sys.executable} "
        f"(Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})\n"
        "   说明：本引擎零三方依赖，仅需 Python >= 3.9 标准库。\n"
        "   修复：请用项目根目录的解释器直接运行 `python studio.py`；"
        "若在虚拟环境中，请先激活该环境。\n\n")
    raise SystemExit(ENV_EXIT_CODE) from None

if __name__ == "__main__":
    raise SystemExit(main())
