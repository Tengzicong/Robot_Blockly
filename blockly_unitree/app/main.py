# -*- coding: utf-8 -*-
"""
应用入口。

运行:
    conda activate go2
    cd /home/zicong/Desktop/unitree/blockly_unitree
    python -m app.main
"""

import os
import sys


def _setup_sdk_path() -> None:
    """把 unitree_sdk2py 所在目录加入 sys.path (兼容开发/安装模式)。"""
    from ._paths import sdk_dir
    sdk = sdk_dir()
    if sdk and sdk not in sys.path:
        sys.path.insert(0, sdk)


def _setup_qtwebengine_env() -> None:
    """Qt / WebEngine 启动前环境变量。

    解决外接显示器高 DPI 缩放、Wayland 下字体模糊、WebEngine 字体/
    devicePixelRatio 不跟随窗口所在屏幕等问题, 并避免在容器/老旧显卡下崩溃。
    必须在 import Qt 模块之前设置。
    """
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    # WebEngine 沙箱 + Chromium 渲染开关
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--no-sandbox --disable-gpu --disable-software-rasterizer "
        "--disable-features=ColorTemperatureAnimation,ChromeAccessibilitySoda",
    )
    if sys.platform.startswith("linux"):
        # Wayland 下强制 xcb 渲染: 避免 Qt Wayland 合成器 DPR 信息不一致
        if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"


# 必须在 import Qt 之前
_setup_sdk_path()
_setup_qtwebengine_env()

# --run-script 子模式: frozen exe / deb 启动器复用自身跑生成脚本 (跳过 GUI)
# frozen 包已带 cyclonedds+unitree_sdk2py+numpy, 生成脚本可正常 import
if __name__ == "__main__" and "--run-script" in sys.argv:
    import runpy
    _argv = sys.argv[1:]
    _i = _argv.index("--run-script")
    _path = _argv[_i + 1] if _i + 1 < len(_argv) else ""
    if _path and os.path.isfile(_path):
        try:
            runpy.run_path(_path, run_name="__main__")
        except SystemExit:
            pass
    sys.exit(0)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer, QCoreApplication
from PySide6.QtGui import QIcon

from .main_window import MainWindow
from ._paths import icon_path
from .splash import SplashScreen
from .disclaimer import show_disclaimer_dialog


def _reexec_into(env_py: str) -> None:
    """以 unitree 环境的解释器重新启动应用 (替换当前进程)。"""
    env = os.environ.copy()
    env.pop("UNITREE_ENV_SETUP", None)
    # 把 app 包父目录放进 PYTHONPATH, 兼容开发/安装两种模式
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = pkg_parent + os.pathsep + env.get("PYTHONPATH", "")
    os.execve(env_py, [env_py, "-m", "app.main"], env)


def _first_run_setup(app, splash) -> str:
    """首次启动: 在加载画面中创建 unitree conda 环境并安装依赖。

    后台线程执行安装, 主循环以 processEvents 驱动加载动画并同步状态
    文字。环境就绪后满足加载页最短停留 3 秒, 再以该环境重启自身;
    失败则提示后继续以当前解释器进入主界面。
    返回 "reexec" (已切换进程, 不会返回) 或 "continue" (进入正常启动)。
    """
    import time as _time
    import threading
    from .env_setup import run_setup

    splash.set_status("首次启动: 正在准备 unitree 运行环境...")
    app.processEvents()
    start = _time.monotonic()

    state = {"done": False, "env_py": "", "status": ""}

    def _worker():
        conda_bin = os.environ.get("UNITREE_CONDA_BIN") or ""
        try:
            env_py = run_setup(conda_bin, lambda msg: state.__setitem__("status", msg)) \
                if conda_bin else ""
        except Exception as exc:  # noqa: BLE001
            state["status"] = f"环境准备异常: {exc}"
            env_py = ""
        state["env_py"] = env_py
        state["done"] = True

    threading.Thread(target=_worker, name="env-setup", daemon=True).start()

    # 手动驱动事件循环: 加载动画保持运行, 状态文字从后台线程取回
    while not state["done"]:
        if state["status"]:
            splash.set_status(state["status"])
            state["status"] = ""
        app.processEvents()
        _time.sleep(0.05)
    if state["status"]:
        splash.set_status(state["status"])

    elapsed_ms = (_time.monotonic() - start) * 1000.0
    if state["env_py"]:
        splash.set_status("环境就绪, 正在启动...")
        remain = 3000.0 - elapsed_ms   # 满足加载页最短停留 3 秒
        if remain > 0:
            _time.sleep(remain / 1000.0)
            app.processEvents()
        _reexec_into(state["env_py"])
        return "reexec"
    splash.set_status("环境准备失败, 即将进入主界面...")
    _time.sleep(2.0)
    app.processEvents()
    return "continue"


def main() -> int:
    # 高分屏 + 外接显示器 DPI 适配相关属性 (Qt6)
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("RobotBlockly")
    # 应用默认字体 10pt: 避免小屏/低分辨率下默认字号过大
    try:
        default_font = app.font()
        default_font.setPointSize(10)
        app.setFont(default_font)
    except Exception:  # noqa: BLE001
        pass
    # 设置窗口图标, 避免 Linux 下显示默认齿轮/设置图标
    _icon = icon_path()
    if _icon:
        app.setWindowIcon(QIcon(_icon))

    # ---- 首次使用: 先弹免责声明, 确认后才进入加载画面 ----
    if not show_disclaimer_dialog():
        return 1

    # ---- 启动加载动画: 先只显示 splash, 主窗口待加载完成后才显示 ----
    splash = SplashScreen()
    splash.center_on_cursor()
    splash.show()
    splash.set_status("正在创建主界面...")
    app.processEvents()

    # ---- 首次启动: 在加载画面中创建 unitree conda 环境并安装依赖 ----
    # frozen (PyInstaller 自包含) 时跳过 conda setup
    if os.environ.get("UNITREE_ENV_SETUP") == "1" and not getattr(sys, "frozen", False):
        if _first_run_setup(app, splash) == "reexec":
            return 0  # 已 execve 切换到 unitree 环境, 不会执行到这里

    window = MainWindow()          # 构建主窗口 (WebEngine 后台加载 Blockly), 但不显示
    _main_window_shown = {"shown": False}

    def _show_main_window():
        """splash 完全淡出后才显示主窗口, 避免两个窗口同时出现。"""
        if _main_window_shown["shown"]:
            return
        _main_window_shown["shown"] = True
        window.show()

    # 启动页最少停留 3 秒: 到达该时刻且 Blockly 已就绪后才收尾;
    # 超过 8 秒无论加载状态如何都强制进入主界面, 避免卡在启动页
    SPLASH_MIN_MS = 3000
    FORCE_ENTER_MS = 8000
    import time as _time
    _splash_start = _time.monotonic()
    _splash_ready = {"ready": False}

    def _maybe_close_splash(force: bool = False):
        """force=False: 需 Blockly 就绪且满 3 秒; force=True: 只要求满 3 秒即进入。"""
        if not force and not _splash_ready["ready"]:
            return
        elapsed = (_time.monotonic() - _splash_start) * 1000.0
        if elapsed < SPLASH_MIN_MS:
            QTimer.singleShot(
                max(1, int(SPLASH_MIN_MS - elapsed)),
                lambda: _maybe_close_splash(force=True),
            )
            return
        try:
            if splash.isVisible():
                # 淡出完成(关闭)后再显示主窗口
                splash.finish(_show_main_window)
            else:
                _show_main_window()
        except RuntimeError:
            _show_main_window()  # splash 已被销毁, 直接显示主窗口

    def _on_blockly_loaded(ok):
        # Blockly 就绪 (成功/降级都算), 由 _maybe_close_splash 决定实际收尾时刻
        _splash_ready["ready"] = True
        _maybe_close_splash()

    splash.set_status("正在加载积木引擎...")
    window.blockly.loadFinished.connect(_on_blockly_loaded)
    # 兜底: 某些环境下隐藏窗口的 WebEngine 不触发 loadFinished,
    # 8 秒后强制进入主界面, 绝不会一直停在启动页
    QTimer.singleShot(FORCE_ENTER_MS, lambda: _maybe_close_splash(force=True))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
