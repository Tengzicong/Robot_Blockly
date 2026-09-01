# -*- coding: utf-8 -*-
"""unitree conda 运行环境的自动创建与依赖安装。

纯标准库实现, 供系统启动器 (/usr/bin/blockly-unitree) 与主程序共用:
  - 启动器在环境已就绪时直接进入应用;
  - 未就绪时用任意带 PySide6 的引导解释器启动主程序, 由主程序在
    加载画面阶段调用 run_setup() 创建环境并安装依赖, 完成后重新以
    unitree 环境的解释器启动自身;
  - 无引导解释器时启动器回退为 zenity 进度窗后台安装。
"""

import os
import sys
import platform
import subprocess

ENV_NAME = "unitree"          # 专用 conda 环境名
PY_SPEC = "3.10"              # 环境 Python 版本
PIP_PKGS = ["PySide6", "cyclonedds==0.10.2", "numpy"]
JUPYTER_PKGS = ["jupyterlab"]  # 教程笔记本运行环境 (缺失不阻塞启动)
PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
SETUP_TIMEOUT = 1800          # conda create / pip install 超时 (秒)


def find_conda() -> str:
    """查找本机 conda 可执行文件, 找不到返回空串。"""
    cands = []
    if sys.platform == "win32":
        home = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        for d in ("miniconda3", "anaconda3", "miniforge3", "mambaforge"):
            cands.append(os.path.join(home, d, "Scripts", "conda.exe"))
        cands += [r"C:\ProgramData\miniconda3\Scripts\conda.exe",
                  r"C:\ProgramData\miniforge3\Scripts\conda.exe",
                  r"C:\ProgramData\anaconda3\Scripts\conda.exe"]
    else:
        for d in ("~/miniconda3", "~/anaconda3", "~/miniforge3", "~/mambaforge",
                  "/opt/conda", "/opt/homebrew/miniconda3", "/opt/homebrew/anaconda3"):
            cands.append(os.path.join(os.path.expanduser(d), "bin", "conda"))
    for b in cands:
        if os.path.exists(b):
            return b
    import shutil
    return shutil.which("conda") or shutil.which("conda.exe") or ""


def conda_env_paths(conda_bin: str):
    """列出 conda 所有环境的路径。"""
    try:
        import json
        r = subprocess.run([conda_bin, "env", "list", "--json"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return json.loads(r.stdout).get("envs", [])
    except Exception:  # noqa: BLE001
        pass
    return []


def unitree_env_python(conda_bin: str) -> str:
    """返回 unitree 环境的 python 路径; 环境不存在或损坏返回空串。"""
    py_name = "python.exe" if sys.platform == "win32" else "python"
    py_subdir = "" if sys.platform == "win32" else "bin"
    for env in conda_env_paths(conda_bin):
        if os.path.basename(env.rstrip(os.sep)) == ENV_NAME:
            p = os.path.join(env, py_subdir, py_name) if py_subdir else os.path.join(env, py_name)
            if os.path.exists(p):
                return p
    return ""


def check_deps(python_exe: str):
    """检查解释器能否导入 PySide6 与 cyclonedds。返回 (pyside_ok, dds_ok)。"""
    code = (
        "pyside = dds = False\n"
        "try:\n"
        "    import PySide6  # noqa: F401\n"
        "    pyside = True\n"
        "except Exception:\n"
        "    pass\n"
        "try:\n"
        "    import cyclonedds  # noqa: F401\n"
        "    dds = True\n"
        "except Exception:\n"
        "    pass\n"
        "print('PYSIDE=' + ('1' if pyside else '0') + ' DDS=' + ('1' if dds else '0'))"
    )
    try:
        r = subprocess.run([python_exe, "-c", code],
                           capture_output=True, text=True, timeout=60)
        out = (r.stdout or "").strip()
        return "PYSIDE=1" in out, "DDS=1" in out
    except Exception:  # noqa: BLE001
        return False, False


def _pip_install(env_py: str, pkgs, use_mirror: bool):
    cmd = [env_py, "-m", "pip", "install", "--disable-pip-version-check",
           "--timeout", "60"] + list(pkgs)
    if use_mirror:
        cmd += ["-i", PIP_MIRROR]
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=SETUP_TIMEOUT)


def _bundled_wheels_dir() -> str:
    """定位随 deb 分发的预编译 wheels 目录 (linux aarch64 cyclonedds 0.10.2)。"""
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (
        os.path.join(os.path.dirname(here), "wheels"),   # deb: /usr/lib/blockly-unitree/wheels
        os.path.normpath(os.path.join(here, "..", "wheels")),
    ):
        if os.path.isdir(cand):
            return cand
    return ""


def run_setup(conda_bin: str, report):
    """创建/补全 unitree 环境, 依赖齐全后返回环境 python 路径, 失败返回空串。

    report: 回调函数 report(str), 用于向加载画面/进度窗同步状态文字。
    """
    def rep(msg: str):
        try:
            report(msg)
        except Exception:  # noqa: BLE001
            pass

    env_py = unitree_env_python(conda_bin)
    if not env_py:
        rep(f"正在创建 conda 环境 {ENV_NAME} (python={PY_SPEC}), 首次需几分钟...")
        try:
            r = subprocess.run(
                [conda_bin, "create", "-n", ENV_NAME, "python=" + PY_SPEC, "-y"],
                capture_output=True, text=True, timeout=SETUP_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001
            rep(f"创建环境失败: {exc}")
            return ""
        if r.returncode != 0:
            lines = (r.stderr or r.stdout or "").strip().splitlines()
            rep("创建环境失败: " + (lines[-1] if lines else f"exit={r.returncode}"))
            return ""
        env_py = unitree_env_python(conda_bin)
        if not env_py:
            rep("创建环境后未找到解释器")
            return ""

    rep("正在检查运行依赖...")
    pyside_ok, dds_ok = check_deps(env_py)
    if not (pyside_ok and dds_ok):
        # linux aarch64: PyPI 无 PySide6/cyclonedds wheel → conda-forge + 本地预编译 wheel
        if sys.platform.startswith("linux") and platform.machine() == "aarch64":
            if not pyside_ok:
                rep("正在安装 PySide6 (conda-forge, linux aarch64)...")
                try:
                    r = subprocess.run(
                        [conda_bin, "install", "-n", ENV_NAME, "-c", "conda-forge",
                         "pyside6", "numpy", "-y"],
                        capture_output=True, text=True, timeout=SETUP_TIMEOUT)
                except Exception as exc:  # noqa: BLE001
                    rep(f"PySide6 安装失败: {exc}")
                    return ""
                if r.returncode != 0:
                    lines = (r.stderr or r.stdout or "").strip().splitlines()
                    rep("PySide6 安装失败: " + (lines[-1] if lines else f"exit={r.returncode}"))
                    return ""
            if not dds_ok:
                # cyclonedds 0.10.2: 优先本地预编译 wheel, 失败回退 conda-forge 0.10.5
                wheels_dir = _bundled_wheels_dir()
                installed_cyc = False
                if wheels_dir:
                    rep("正在安装 cyclonedds 0.10.2 (本地预编译 wheel)...")
                    try:
                        r = subprocess.run(
                            [env_py, "-m", "pip", "install", "--no-index",
                             "--find-links", wheels_dir, "cyclonedds==0.10.2"],
                            capture_output=True, text=True, timeout=SETUP_TIMEOUT)
                        installed_cyc = (r.returncode == 0)
                    except Exception:  # noqa: BLE001
                        installed_cyc = False
                if not installed_cyc:
                    rep("本地 wheel 不可用, 回退 cyclonedds 0.10.5 (conda-forge)...")
                    try:
                        r = subprocess.run(
                            [conda_bin, "install", "-n", ENV_NAME, "-c", "conda-forge",
                             "cyclonedds=0.10.5", "-y"],
                            capture_output=True, text=True, timeout=SETUP_TIMEOUT)
                    except Exception as exc:  # noqa: BLE001
                        rep(f"cyclonedds 安装失败: {exc}")
                        return ""
                    if r.returncode != 0:
                        lines = (r.stderr or r.stdout or "").strip().splitlines()
                        rep("cyclonedds 安装失败: " + (lines[-1] if lines else f"exit={r.returncode}"))
                        return ""
        else:
            missing = []
            if not pyside_ok:
                missing.append("PySide6")
            if not dds_ok:
                missing.append("cyclonedds")
            rep(f"正在安装依赖: {' / '.join(missing)} (清华镜像)...")
            try:
                r = _pip_install(env_py, PIP_PKGS, use_mirror=True)
            except Exception as exc:  # noqa: BLE001
                rep(f"依赖安装失败: {exc}")
                return ""
            if r.returncode != 0:
                rep("镜像安装失败, 改用官方源重试...")
                try:
                    r = _pip_install(env_py, PIP_PKGS, use_mirror=False)
                except Exception as exc:  # noqa: BLE001
                    rep(f"依赖安装失败: {exc}")
                    return ""
                if r.returncode != 0:
                    lines = (r.stderr or r.stdout or "").strip().splitlines()
                    rep("依赖安装失败: " + (lines[-1] if lines else f"exit={r.returncode}"))
                    return ""
        rep("正在验证环境...")
        pyside_ok, _dds_ok = check_deps(env_py)
        if not pyside_ok:
            rep("依赖安装后仍不可用")
            return ""

    # Jupyter (教程笔记本运行环境): 缺失则补装, 失败不阻塞启动
    # jupyterlab / notebook 任一已安装即视为已配置
    try:
        r = subprocess.run(
            [env_py, "-c", "try:\n import jupyterlab\nexcept ImportError:\n import notebook"],
            capture_output=True, timeout=60,
        )
        jupyter_ok = (r.returncode == 0)
    except Exception:  # noqa: BLE001
        jupyter_ok = False
    if not jupyter_ok:
        rep("正在安装 Jupyter (教程笔记本运行环境)...")
        try:
            r = _pip_install(env_py, JUPYTER_PKGS, use_mirror=True)
        except Exception as exc:  # noqa: BLE001
            rep(f"Jupyter 安装失败: {exc}")
            return env_py
        if r.returncode != 0:
            rep("镜像安装失败, 改用官方源重试...")
            try:
                r = _pip_install(env_py, JUPYTER_PKGS, use_mirror=False)
            except Exception as exc:  # noqa: BLE001
                rep(f"Jupyter 安装失败: {exc}")
                return env_py
    return env_py
