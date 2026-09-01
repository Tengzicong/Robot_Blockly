# -*- coding: utf-8 -*-
"""
代码运行器: 用 QProcess 执行生成的 Python 脚本, 实时转发 stdout/stderr 到日志。
PYTHONPATH 指向 unitree_sdk2_python, 使脚本可 import unitree_sdk2py。
"""

import os
import sys

from PySide6.QtCore import QObject, QProcess, Signal

from ._paths import sdk_dir

# unitree_sdk2py 所在目录 (兼容开发/安装模式)
_SDK_PATH = sdk_dir()


class CodeRunner(QObject):
    # level, text
    lineLogged = Signal(str, str)
    # finished, exit_code
    finished = Signal(bool, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self._script_path = None

    # ----------------------------------------------------------------
    def run(self, script_path: str, python_exec: str = None) -> bool:
        """启动脚本。返回是否成功启动。"""
        if self.is_running():
            self.lineLogged.emit("err", "已有程序在运行, 请先停止")
            return False

        if python_exec is None:
            python_exec = sys.executable

        env = os.environ.copy()
        # 确保 SDK 可被 import
        paths = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
        if _SDK_PATH not in paths:
            paths.insert(0, _SDK_PATH)
        env["PYTHONPATH"] = os.pathsep.join(paths)
        # 让生成的脚本能实时刷新输出
        env["PYTHONUNBUFFERED"] = "1"

        self._script_path = script_path
        self._proc = QProcess(self)
        self._proc.setProcessEnvironment(self._proc.processEnvironment())
        # 重新设置带 PYTHONPATH 的环境
        from PySide6.QtCore import QProcessEnvironment
        qenv = QProcessEnvironment()
        for k, v in env.items():
            qenv.insert(k, v)
        self._proc.setProcessEnvironment(qenv)

        self._proc.readyReadStandardOutput.connect(self._on_stdout)
        self._proc.readyReadStandardError.connect(self._on_stderr)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error)

        self.lineLogged.emit("info", f"运行: {python_exec} {script_path}")
        self.lineLogged.emit("info", f"PYTHONPATH={_SDK_PATH}")
        # frozen (PyInstaller): sys.executable 是 exe, 用 --run-script 子模式让 main.py 复用自身跑脚本
        # 非 frozen (deb/dev): sys.executable 是 python, 直接跑脚本 (python 不认 --run-script)
        args = ["--run-script", script_path] if getattr(sys, "frozen", False) else [script_path]
        self._proc.start(python_exec, args)
        ok = self._proc.waitForStarted(3000)
        if not ok:
            self.lineLogged.emit("err", "进程启动失败")
        return ok

    # ----------------------------------------------------------------
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.NotRunning

    def stop(self) -> None:
        if self.is_running():
            try:
                self._proc.kill()
                self.lineLogged.emit("warn", "已强制停止运行")
            except Exception:  # noqa: BLE001
                pass

    # ----------------------------------------------------------------
    def _on_stdout(self) -> None:
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in data.splitlines():
            self.lineLogged.emit("out", line)

    def _on_stderr(self) -> None:
        data = bytes(self._proc.readAllStandardError()).decode("utf-8", "replace")
        for line in data.splitlines():
            self.lineLogged.emit("err", line)

    def _on_finished(self, exit_code, exit_status) -> None:  # noqa: ARG002
        self.lineLogged.emit("info", f"程序结束 (exit={exit_code})")
        self.finished.emit(True, int(exit_code))
        self._proc = None

    def _on_error(self, error) -> None:
        self.lineLogged.emit("err", f"进程错误: {error}")
