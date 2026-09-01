# -*- coding: utf-8 -*-
"""路径解析: 兼容开发模式与 deb 安装模式, 定位 unitree_sdk2py。

布局:
  开发:  .../unitree/blockly_unitree/app/_paths.py, SDK 在 ../../unitree_sdk2_python
  安装:  /usr/lib/blockly-unitree/app/_paths.py, SDK 打包在 /usr/lib/blockly-unitree/unitree_sdk2py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))  # app 目录


def sdk_dir() -> str:
    """返回应加入 sys.path/PYTHONPATH 以便 import unitree_sdk2py 的目录。"""
    # 0) PyInstaller frozen: unitree_sdk2py 已被 collect 进 _MEIPASS, 直接 import
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        try:
            import unitree_sdk2py  # noqa: F401
            return os.path.dirname(os.path.dirname(os.path.abspath(unitree_sdk2py.__file__)))
        except Exception:  # noqa: BLE001
            pass
    # 1) 安装模式: 与 app 同级的打包 SDK
    bundled = os.path.join(os.path.dirname(HERE), "unitree_sdk2py")
    if os.path.isfile(os.path.join(bundled, "__init__.py")):
        return os.path.dirname(bundled)
    # 2) 开发模式: 项目上层的 unitree_sdk2_python
    dev = os.path.normpath(os.path.join(HERE, "..", "..", "unitree_sdk2_python"))
    if os.path.isfile(os.path.join(dev, "unitree_sdk2py", "__init__.py")):
        return dev
    # 3) 回退: 若已可 import, 取其实际位置
    try:
        import unitree_sdk2py  # noqa: F401
        return os.path.dirname(os.path.dirname(os.path.abspath(unitree_sdk2py.__file__)))
    except Exception:  # noqa: BLE001
        return dev


def runtime_dir() -> str:
    """生成脚本的可写目录: 安装到 /usr/lib 后普通用户不可写, 故用用户数据目录。"""
    if os.access(os.path.dirname(HERE), os.W_OK):
        return os.path.normpath(os.path.join(HERE, "..", "runtime"))
    # 跨平台用户数据目录
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(base, "RobotBlockly")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "RobotBlockly")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "blockly-unitree")


def icon_path() -> str:
    """应用图标 SVG 路径 (开发: resources/, 安装: 打包后的 resources/)。"""
    # PyInstaller frozen: 图标打包在 _MEIPASS 根
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        cand = os.path.join(sys._MEIPASS, "blockly-unitree.svg")
        if os.path.isfile(cand):
            return cand
    for cand in (
        os.path.join(HERE, "..", "resources", "blockly-unitree.svg"),
        "/usr/share/icons/hicolor/scalable/apps/blockly-unitree.svg",
    ):
        if os.path.isfile(cand):
            return cand
    return ""
