# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Robot Blockly 自包含打包 (Windows / macOS)。

用法:
    # 构建机先装好依赖 (见 requirements.txt):
    pip install -r requirements.txt
    pip install -e ../unitree_sdk2_python   # editable 引入 SDK

    # Windows (PowerShell):
    powershell -ExecutionPolicy Bypass -File packaging/build_win.ps1

    # macOS:
    bash packaging/build_mac.sh

本 spec 由上述脚本调用; 也可手动:
    pyinstaller packaging/blockly_unitree.spec --noconfirm --distpath dist
"""

import os
import sys

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))  # blockly_unitree/
SDK_ROOT = os.path.normpath(os.path.join(ROOT, "..", "unitree_sdk2_python"))

# ------------------------------------------------------------------
# 数据文件: Blockly 资源 + 应用图标 SVG (放 _MEIPASS 根, 供 icon_path() 读取)
# ------------------------------------------------------------------
datas = [
    (os.path.join(ROOT, "resources"), "resources"),
    (os.path.join(ROOT, "blockly-unitree.svg"), "."),
]

# ------------------------------------------------------------------
# 隐式导入: unitree_sdk2py 全部子模块 (IDL 动态导入) + cyclonedds 扩展
# ------------------------------------------------------------------
hiddenimports = []
hiddenimports += collect_submodules("unitree_sdk2py")
hiddenimports += [
    "cyclonedds",
    "cyclonedds.core",
    "cyclonedds.sub",
    "cyclonedds.pub",
    "cyclonedds.topic",
    "numpy",
]

# ------------------------------------------------------------------
# 二进制数据: PySide6 Qt 插件/资源 (PyInstaller hook 通常自动处理,
# 显式声明以防遗漏)
# ------------------------------------------------------------------
datas += collect_data_files("PySide6")

# ------------------------------------------------------------------
# 路径搜索: SDK 源码目录 (editable install 时让 PyInstaller 找到包)
# ------------------------------------------------------------------
pathex = [ROOT, SDK_ROOT]

# ------------------------------------------------------------------
# 图标: Windows .ico / macOS .icns (由 packaging/icons/ 提供)
# ------------------------------------------------------------------
icon = None
if sys.platform == "win32":
    _ico = os.path.join(ROOT, "packaging", "icons", "blockly-unitree.ico")
    if os.path.isfile(_ico):
        icon = _ico
elif sys.platform == "darwin":
    _icns = os.path.join(ROOT, "packaging", "icons", "blockly-unitree.icns")
    if os.path.isfile(_icns):
        icon = _icns

# ------------------------------------------------------------------
# 排除: 测试模块、无关大包
# ------------------------------------------------------------------
excludes = [
    "matplotlib",
    "scipy",
    "pandas",
    "tkinter",
    "pytest",
    "IPython",
    "jupyterlab",
    "notebook",
]


a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=pathex,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

# ------------------------------------------------------------------
# Windows: 单目录 onedir (启动快, 无需解压临时目录)
# macOS:   .app bundle
# ------------------------------------------------------------------
if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="RobotBlockly",
        icon=icon or None,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,  # GUI 应用, 无控制台
    )
    app = BUNDLE(
        exe,
        a.binaries,
        a.datas,
        name="RobotBlockly.app",
        icon=icon or None,
        bundle_identifier="com.blocklyunitree.app",
        info_plist={
            "CFBundleDisplayName": "Robot Blockly",
            "CFBundleShortVersionString": "0.1.1",
            # 未签名分发, 由 Launch Services 依据此键拦截低于 12.0 的系统
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription": "用于与机器人交互",
            "NSCameraUsageDescription": "用于查看机器人摄像头图像",
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="RobotBlockly",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,  # GUI 应用, 无控制台窗口
        icon=icon or None,
    )
