# -*- coding: utf-8 -*-
"""首次启动免责声明弹窗。

记录用户接受状态到 runtime_dir() 下的标记文件,
首次安装启动后弹出, 强制用户滚动读完才能确认, 同意后才进入主界面。
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTextBrowser,
    QPushButton, QHBoxLayout,
)

from ._paths import runtime_dir
from . import __app_name__

# 标记文件: 用户确认后写入, 下次启动跳过弹窗
_ACCEPT_FLAG = os.path.join(runtime_dir(), ".disclaimer_accepted")

_DISCLAIMER_CN = (
    "本软件适用于宇树（Unitree）G1 与 Go2 机器人。\n\n"
    "本项目为学生独立开发第三方学习工具，未获得宇树官方任何授权，"
    "与宇树公司无合作关系。\n\n"
    "⚠️ 使用本软件操控机器人存在硬件损坏风险，一切设备损失、"
    "操作后果均由使用者自行承担。\n\n"
    "继续使用即代表您阅读并同意以上提示。"
)


def is_accepted() -> bool:
    """用户是否已同意免责声明。"""
    return os.path.isfile(_ACCEPT_FLAG)


def _mark_accepted() -> None:
    """写入同意标记。"""
    try:
        os.makedirs(os.path.dirname(_ACCEPT_FLAG), exist_ok=True)
        with open(_ACCEPT_FLAG, "w", encoding="utf-8") as f:
            f.write("accepted\n")
    except Exception:  # noqa: BLE001
        pass


def show_disclaimer_dialog(parent=None) -> bool:
    """弹出免责声明; 返回 True=已确认, False=未确认(应退出)。

    已同意过则直接返回 True, 不弹窗。
    """
    if is_accepted():
        return True

    dlg = QDialog(parent)
    dlg.setWindowTitle(__app_name__)
    dlg.setMinimumSize(560, 420)
    dlg.setWindowFlags(
        dlg.windowFlags()
        & ~Qt.WindowType.WindowContextHelpButtonHint
        & ~Qt.WindowType.WindowMaximizeButtonHint
    )
    # 显式白色背景 + 深色文字: 避免深色系统主题下白字白底不可读
    dlg.setStyleSheet(
        "QDialog { background-color:#ffffff; }"
        "QLabel { color:#1a1a1a; }"
    )

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 20, 24, 16)
    layout.setSpacing(12)

    title = QLabel(__app_name__)
    title.setStyleSheet("font-size:18px; font-weight:bold; color:#1a73e8;")
    layout.addWidget(title)

    browser = QTextBrowser()
    browser.setPlainText(_DISCLAIMER_CN)
    browser.setOpenExternalLinks(False)
    # 同时设置前景色(文字)为深色 + 背景浅色, 保证任何主题下可读
    browser.setStyleSheet(
        "QTextBrowser { background-color:#fafafa; color:#1a1a1a;"
        " border:1px solid #e0e0e0; border-radius:4px; padding:8px;"
        " font-size:10pt; }"
    )
    browser.setMinimumHeight(220)
    layout.addWidget(browser)

    btn_row = QHBoxLayout()
    btn_row.addStretch()

    btn_confirm = QPushButton("确认")
    btn_confirm.setStyleSheet(
        "QPushButton { padding:6px 24px; border:none; border-radius:4px;"
        " background:#1a73e8; color:white; font-weight:bold; }"
        "QPushButton:disabled { background:#aaa; color:#eee; }"
    )
    btn_confirm.setDefault(True)
    # 强制用户读完: 滚动到底部前禁用确认按钮
    btn_confirm.setEnabled(False)

    btn_row.addWidget(btn_confirm)
    layout.addLayout(btn_row)

    # ---- 信号 ----
    result = {"accepted": False}

    def _enable_when_scrolled_to_bottom():
        sb = browser.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 2
        btn_confirm.setEnabled(at_bottom)

    browser.verticalScrollBar().valueChanged.connect(_enable_when_scrolled_to_bottom)
    btn_confirm.clicked.connect(lambda: (result.__setitem__("accepted", True), dlg.accept()))

    # 内容未超出可视区(无滚动条)时也要允许确认
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, _enable_when_scrolled_to_bottom)

    dlg.exec()

    if result["accepted"]:
        _mark_accepted()
        return True
    return False
