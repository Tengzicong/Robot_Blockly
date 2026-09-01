#!/usr/bin/env bash
# ============================================================================
# 机器人 Robot Blockly  Ubuntu deb 安装包构建脚本
#
# 用法:
#     chmod +x packaging/build_deb.sh
#     ./packaging/build_deb.sh
#
# 产物: dist/blockly-unitree_<version>_all.deb
#
# 说明:
#   - 在项目根目录 (blockly_unitree/) 执行
#   - 自包含: 把 unitree_sdk2py 与 Blockly 资源一并打进 /usr/lib/blockly-unitree
#   - 启动器自动查找装了 PySide6 + cyclonedds 的 Python (conda/系统)
# ============================================================================
set -euo pipefail

APP_NAME="blockly-unitree"
VERSION="0.1.0"
ARCH="all"
MAINTAINER="RobotBlockly <dev@example.com>"
DESC="机器人可视化积木编程桌面软件 (Go2 四足 / G1 人形)"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# 宇树 SDK 源码目录 (本项目上一级)
SDK_ROOT="$(cd "${ROOT_DIR}/../unitree_sdk2_python" && pwd)"

PKG_NAME="${APP_NAME}_${VERSION}_${ARCH}"
BUILD_DIR="${ROOT_DIR}/dist/${PKG_NAME}"
DIST_DIR="${ROOT_DIR}/dist"

echo "==> 项目根目录: ${ROOT_DIR}"
echo "==> SDK 目录:   ${SDK_ROOT}"
echo "==> 构建 deb:   ${PKG_NAME}.deb"

if [ ! -d "${SDK_ROOT}/unitree_sdk2py" ]; then
  echo "!! 找不到 ${SDK_ROOT}/unitree_sdk2py, 无法打包 SDK" >&2
  exit 1
fi

# ----------------------------- 清理旧产物 --------------------------------
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/DEBIAN"

# ----------------------------- 安装文件布局 ------------------------------
LIB_DIR="${BUILD_DIR}/usr/lib/${APP_NAME}"
mkdir -p "${LIB_DIR}"

# 1) Python 包 app/ 与资源 resources/
cp -r "${ROOT_DIR}/app" "${LIB_DIR}/"
cp -r "${ROOT_DIR}/resources" "${LIB_DIR}/"

# 2) 捆绑 unitree_sdk2py (自包含, 不依赖外部目录)
cp -r "${SDK_ROOT}/unitree_sdk2py" "${LIB_DIR}/unitree_sdk2py"

# 3) 运行时生成脚本目录 (可写; 运行时若不可写会自动改用 ~/.local/share)
mkdir -p "${LIB_DIR}/runtime"

# 3a) 预编译 wheels (linux aarch64 cyclonedds 0.10.2; 供首次安装补依赖)
if [ -d "${ROOT_DIR}/wheels" ]; then
  cp -r "${ROOT_DIR}/wheels" "${LIB_DIR}/wheels"
  _NWH=$(ls "${LIB_DIR}/wheels"/*.whl 2>/dev/null | wc -l)
  echo "    -> 捆绑 wheels (${_NWH} 个)"
fi

# 清理 pyc
find "${LIB_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${LIB_DIR}" -name "*.pyc" -delete 2>/dev/null || true

# 4) 启动器 -> /usr/bin/blockly-unitree
mkdir -p "${BUILD_DIR}/usr/bin"
cat > "${BUILD_DIR}/usr/bin/${APP_NAME}" <<'LAUNCHER'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Robot Blockly 系统启动器 (由 deb 安装到 /usr/bin/blockly-unitree)。

启动策略:
  1) unitree conda 环境已就绪 -> 直接以该环境启动应用;
  2) 未就绪 -> 用任意带 PySide6 的引导解释器启动应用 (设置
     UNITREE_ENV_SETUP=1), 由加载画面完成环境创建/依赖安装后
     自动切换到 unitree 环境重启自身;
  3) 找不到带 PySide6 的引导解释器 -> zenity 进度窗后台安装后再启动。
"""
import os
import sys
import shutil
import subprocess

# --- 外接显示器 / 高 DPI 缩放 环境变量 (必须在 import Qt 之前) ---
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

LIB_DIR = "/usr/lib/blockly-unitree"
sys.path.insert(0, LIB_DIR)

from app.env_setup import (  # noqa: E402
    ENV_NAME,
    PIP_PKGS,
    PY_SPEC,
    check_deps,
    conda_env_paths,
    find_conda,
    run_setup,
    unitree_env_python,
)


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _launch(py: str) -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = LIB_DIR + os.pathsep + env.get("PYTHONPATH", "")
    os.execve(py, [py, "-m", "app.main"], env)
    return 0


def _zenity_progress(text: str):
    """启动 zenity 脉冲进度窗口; 不可用时返回 (None, None)。"""
    zen = shutil.which("zenity")
    if not zen or not _has_display():
        return None, None
    try:
        p = subprocess.Popen(
            [zen, "--progress", "--title=Robot Blockly", "--width=480",
             "--pulsate", "--no-cancel", "--text=" + text],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, text=True,
        )
        return p, p.stdin
    except Exception:
        return None, None


def _bootstrap_python(conda_bin: str, extra: str) -> str:
    """找一个带 PySide6 的解释器用于显示加载画面 (首次安装时)。"""
    candidates = [sys.executable, "/usr/bin/python3", "/usr/local/bin/python3", extra]
    if conda_bin:
        for env_path in conda_env_paths(conda_bin):
            candidates.append(os.path.join(env_path, "bin", "python"))
    seen = set()
    for py in candidates:
        if not py or py in seen or not os.path.exists(py):
            continue
        seen.add(py)
        if check_deps(py)[0]:
            return py
    return ""


def _error(msg: str) -> None:
    zen = shutil.which("zenity")
    if zen and _has_display():
        try:
            subprocess.run([zen, "--error", "--title=Robot Blockly",
                            "--width=520", "--text=" + msg])
        except Exception:
            pass
    sys.stderr.write(msg + "\n")


def main() -> int:
    conda_bin = find_conda()
    # 1) unitree 环境已就绪 -> 直接启动
    env_py = unitree_env_python(conda_bin) if conda_bin else ""
    if env_py:
        pyside_ok, dds_ok = check_deps(env_py)
        if pyside_ok:
            if not dds_ok:
                sys.stderr.write(
                    "\n[警告] unitree 环境缺少 cyclonedds, "
                    "状态监控与运行 SDK 脚本将不可用。\n\n"
                )
            return _launch(env_py)
    # 2) 未就绪: 用带 PySide6 的引导解释器启动, 在加载画面里完成安装
    boot = _bootstrap_python(conda_bin, env_py)
    if boot:
        env = os.environ.copy()
        if conda_bin:
            env["UNITREE_ENV_SETUP"] = "1"
            env["UNITREE_CONDA_BIN"] = conda_bin
        env["PYTHONPATH"] = LIB_DIR + os.pathsep + env.get("PYTHONPATH", "")
        os.execve(boot, [boot, "-m", "app.main"], env)
        return 0
    # 3) 无图形引导能力: zenity 进度窗后台完成安装
    if conda_bin:
        proc, stdin = _zenity_progress("正在准备 unitree 运行环境...")

        def _rep(msg: str) -> None:
            if stdin is not None:
                try:
                    stdin.write("# " + msg + "\n")
                    stdin.flush()
                except Exception:
                    pass

        py = run_setup(conda_bin, _rep)
        if stdin is not None:
            try:
                stdin.write("100\n")
                stdin.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if py:
            return _launch(py)
        _error(
            f"unitree 环境准备失败, 请检查网络后重试, 或手动执行:\n"
            f"  conda create -n {ENV_NAME} python={PY_SPEC} -y\n"
            f"  conda activate {ENV_NAME} && pip install {' '.join(PIP_PKGS)}"
        )
        return 1
    _error(
        f"未找到 conda, 也没有带 PySide6 的解释器, 无法启动。\n"
        f"请先安装 miniconda 后重试, 或手动执行:\n"
        f"  conda create -n {ENV_NAME} python={PY_SPEC} -y\n"
        f"  conda activate {ENV_NAME} && pip install {' '.join(PIP_PKGS)}"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
LAUNCHER
chmod 755 "${BUILD_DIR}/usr/bin/${APP_NAME}"

# 5) desktop 文件
APP_DIR="${BUILD_DIR}/usr/share/applications"
mkdir -p "${APP_DIR}"
cp "${ROOT_DIR}/blockly-unitree.desktop" "${APP_DIR}/"

# 6) 图标
ICON_DIR="${BUILD_DIR}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${ICON_DIR}"
cp "${ROOT_DIR}/blockly-unitree.svg" "${ICON_DIR}/${APP_NAME}.svg"

# ----------------------------- DEBIAN/control ----------------------------
cat > "${BUILD_DIR}/DEBIAN/control" <<EOF
Package: ${APP_NAME}
Version: ${VERSION}
Section: devel
Priority: optional
Architecture: ${ARCH}
Depends: python3, libxcb-cursor0, libxcb-xinerama0, libnss3, libxkbcommon0, libasound2, libgl1, libegl1, libxcomposite1, libxdamage1, libxrandr2, libxtst6
Maintainer: ${MAINTAINER}
Description: ${DESC}
 机器人可视化积木编程桌面软件, 功能:
  * Blockly 积木编程, 拖拽搭建动作序列 (Go2 四足 / G1 人形)
  * 一键生成 Python 代码 (对接 unitree_sdk2py)
  * 一键运行生成的脚本, 实时捕获输出
  * 实时状态监控 (DDS 订阅 rt/lowstate, IMU/电池/电机)
  * 程序存取 (XML) 与导出 .py
 .
 内置 unitree_sdk2py 与 Blockly 资源 (离线可用)。
 首次启动时启动器会自动创建名为 unitree 的 conda 环境
 (python=3.10) 并安装 PySide6 / cyclonedds (需联网);
 也可提前手动创建:
   conda create -n unitree python=3.10 -y
   conda activate unitree && pip install PySide6 cyclonedds
 若 conda 不可用, 启动器会回退到本机已装 PySide6 的解释器。
EOF

# ----------------------------- DEBIAN/postinst ---------------------------
cat > "${BUILD_DIR}/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q || true
fi
echo "blockly-unitree 安装完成。"
echo "首次启动会自动检测本机 conda, 创建名为 unitree 的环境 (python=3.10)"
echo "并安装依赖 PySide6 / cyclonedds (需联网); 也可提前手动创建以加快首次启动:"
echo "  conda create -n unitree python=3.10 -y"
echo "  conda activate unitree && pip install PySide6 cyclonedds"
echo "运行: 应用菜单点击「Robot Blockly」, 或终端执行 blockly-unitree"
exit 0
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"

# ----------------------------- DEBIAN/prerm ------------------------------
cat > "${BUILD_DIR}/DEBIAN/prerm" <<'EOF'
#!/bin/bash
set -e
exit 0
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/prerm"

# ----------------------------- DEBIAN/postrm -----------------------------
cat > "${BUILD_DIR}/DEBIAN/postrm" <<'EOF'
#!/bin/bash
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q || true
fi
exit 0
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/postrm"

# ----------------------------- 权限 --------------------------------------
chmod 0644 "${BUILD_DIR}/DEBIAN/control"
find "${BUILD_DIR}" -type d -exec chmod 0755 {} \;

# ----------------------------- 构建 deb ----------------------------------
echo "==> 正在打包..."
if command -v fakeroot >/dev/null 2>&1; then
  fakeroot dpkg-deb --build --root-owner-group "${BUILD_DIR}" "${DIST_DIR}/${PKG_NAME}.deb"
else
  dpkg-deb --build --root-owner-group "${BUILD_DIR}" "${DIST_DIR}/${PKG_NAME}.deb"
fi

echo "==> 构建完成:"
ls -lh "${DIST_DIR}/${PKG_NAME}.deb"
echo
echo "==> 安装: sudo apt install ./${PKG_NAME}.deb"
echo "==> 卸载: sudo apt remove ${APP_NAME}"
