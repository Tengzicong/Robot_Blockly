# -*- coding: utf-8 -*-
"""
主窗口: 工具栏(型号/接口/连接/生成/运行/停止/导出) + 中央 Blockly 与代码预览
+ 状态 Dock(IMU/电池/电机) + 日志 Dock(运行输出)。
"""

import os
import sys
import shutil
import subprocess

from PySide6.QtCore import Qt, QTimer, QEvent, QCoreApplication
from PySide6.QtGui import QAction, QFont, QGuiApplication
from PySide6.QtNetwork import QNetworkInterface
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QComboBox, QLabel, QPlainTextEdit,
    QTextBrowser, QDockWidget, QFileDialog, QMessageBox, QStatusBar,
)

from . import __app_name__
from ._paths import runtime_dir
from .blockly_view import BlocklyView
from .code_runner import CodeRunner
from .status_monitor import StatusMonitor
from .camera_view import CameraView
from .robot_profiles import get_profile, PROFILES

_RUNTIME_DIR = runtime_dir()
_RUN_SCRIPT = os.path.join(_RUNTIME_DIR, "generated_run.py")

# 教程 (tutorial_ws/lesson01) 网线直连组网参数:
# Go2 出厂固定 IP, 电脑端需在同网段静态配置 (机器人不提供 DHCP)
_ROBOT_FIXED_IP = "192.168.123.161"
_ROBOT_PC_ADDR = "192.168.123.241/24"


def _btn(text, color):
    b = QPushButton(text)
    b.setStyleSheet(
        f"QPushButton {{ background-color:{color}; color:white; padding:5px 9px;"
        " border:none; border-radius:4px; font-weight:bold; }"
        f"QPushButton:hover {{ background-color:{color}cc; }}"
        f"QPushButton:disabled {{ background-color:#555; }}"
    )
    return b


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 明确启用标题栏 + 最小化/最大化/关闭按钮 (部分 Linux X11 WM 会因窗口标志
        # 不完整导致外置屏上无法最大化, 这里强制声明以稳定行为)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle(__app_name__)
        # 不设置任何最大/最小尺寸限制: 允许用户任意缩放与最大化
        self.setMinimumSize(800, 500)
        # 根据当前屏幕可用区域 80% 居中初始化 (避免在外接屏上用硬编码 1280x820 导致
        # 窗口跨屏、最大化按钮可用但实际被 WM 拒绝)
        self._place_window_on_screen(0.8)

        self._current_code = ""
        self.blockly = BlocklyView(self)
        self.runner = CodeRunner(self)
        self.monitor = StatusMonitor(self)

        self._build_ui()
        self._connect_signals()

        # 默认机器人型号
        self.combo_robot.setCurrentText("go2")
        self._on_robot_changed(0)
        # 检测本机网卡填入下拉框, 并每 4 秒自动刷新 (插拔网线/USB 网卡无需手动刷新)
        self._selected_iface = ""
        self._iface_manual_refresh = False
        self._load_interfaces()
        self.iface_combo.activated.connect(self._on_iface_activated)
        # 手动输入/选中网卡时实时刷新下方状态标签
        line_edit = self.iface_combo.lineEdit()
        if line_edit is not None:
            line_edit.textChanged.connect(self._update_iface_state_label)
        self._iface_timer = QTimer(self)
        self._iface_timer.timeout.connect(lambda: self._load_interfaces())
        self._iface_timer.start(4000)

    # ----------------------------------------------------------------
    # 窗口几何: 按主屏/光标所在屏的 availableGeometry 居中放置
    # ----------------------------------------------------------------
    def _screen_for_initial_placement(self):
        """选择放置窗口的屏幕: 优先鼠标光标所在屏幕, 否则主屏。"""
        try:
            cursor_pos = QGuiApplication.primaryScreen().cursor().pos() \
                if QGuiApplication.primaryScreen() else None
        except Exception:  # noqa: BLE001
            cursor_pos = None
        screen = None
        if cursor_pos is not None:
            try:
                screen = QGuiApplication.screenAt(cursor_pos)
            except Exception:  # noqa: BLE001
                screen = None
        return screen or QGuiApplication.primaryScreen()

    def _place_window_on_screen(self, scale: float = 0.8):
        """根据目标屏幕可用区域以 scale 比例居中放置窗口。"""
        screen = self._screen_for_initial_placement()
        if screen is None:
            self.resize(1280, 820)
            return
        try:
            geo = screen.availableGeometry()
        except Exception:  # noqa: BLE001
            self.resize(1280, 820)
            return
        w = max(int(geo.width() * scale), 1024)
        h = max(int(geo.height() * scale), 640)
        x = geo.x() + max(0, (geo.width() - w) // 2)
        y = geo.y() + max(0, (geo.height() - h) // 2)
        self.setGeometry(x, y, w, h)

    # ----------------------------------------------------------------
    # 事件: 跨屏移动后若用户触发最大化, 确保窗口状态正确切换
    # ----------------------------------------------------------------
    def changeEvent(self, event):
        if event is not None and event.type() == QEvent.Type.WindowStateChange:
            # 窗口状态变化时不做任何强制几何/尺寸调整, 让 WM 自行处理最大化/还原,
            # 避免在外接屏 / 高分屏 场景下因人为 resize 把最大化按钮锁死。
            pass
        super().changeEvent(event)

    # ================================================================
    # UI 构建
    # ================================================================
    def _build_ui(self):
        # ---- 顶部工具栏 (单行紧凑, 文字精简避免截断) ----
        top = QWidget()
        tlay = QHBoxLayout(top)
        tlay.setContentsMargins(8, 5, 8, 5)
        tlay.setSpacing(5)

        tlay.addWidget(QLabel("机器人:"))
        self.combo_robot = QComboBox()
        for key, p in PROFILES.items():
            self.combo_robot.addItem(p["label"], key)
        tlay.addWidget(self.combo_robot)

        tlay.addSpacing(6)
        tlay.addWidget(QLabel("网卡:"))
        self.iface_combo = QComboBox()
        self.iface_combo.setEditable(True)
        # 只显示纯网卡名, 连接状态与 IP 显示在下方的状态标签里
        self.iface_combo.setFixedWidth(160)
        self.iface_combo.setToolTip(
            "选择/输入连接机器人的网卡 (如 enp2s0); 连接状态与 IP 显示在下方; 每4秒自动刷新"
        )
        tlay.addWidget(self.iface_combo)
        self.btn_refresh_iface = QPushButton("刷新")
        self.btn_refresh_iface.setStyleSheet(
            "QPushButton { padding:5px 9px; border:1px solid #3a3f4b;"
            " border-radius:4px; background:#3b4048; color:#dcdfe6; }"
            "QPushButton:hover { background:#4b5260; }"
        )
        self.btn_refresh_iface.clicked.connect(self._on_refresh_ifaces)
        tlay.addWidget(self.btn_refresh_iface)

        tlay.addSpacing(6)
        self.btn_connect = _btn("监控", "#61afef")
        self.btn_connect.setToolTip("连接并订阅 rt/lowstate 实时状态")
        tlay.addWidget(self.btn_connect)
        self.btn_disconnect = _btn("断开", "#56b6c2")
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.setToolTip("断开状态监控")
        tlay.addWidget(self.btn_disconnect)
        self.btn_camera = _btn("摄像头", "#61afef")
        self.btn_camera.setToolTip("开启/关闭 Go2 摄像头实时图像回传")
        tlay.addWidget(self.btn_camera)

        tlay.addSpacing(10)
        self.btn_generate = _btn("生成代码", "#98c379")
        tlay.addWidget(self.btn_generate)
        self.btn_run = _btn("运行", "#e5c07b")
        tlay.addWidget(self.btn_run)
        self.btn_stop = _btn("停止", "#e06c75")
        self.btn_stop.setEnabled(False)
        tlay.addWidget(self.btn_stop)

        tlay.addStretch(1)
        self.btn_export_py = _btn("导出 .py", "#c678dd")
        tlay.addWidget(self.btn_export_py)
        self.btn_save_xml = _btn("保存", "#61afef")
        tlay.addWidget(self.btn_save_xml)
        self.btn_load_xml = _btn("载入", "#61afef")
        tlay.addWidget(self.btn_load_xml)

        # ---- 中央: 左 Blockly + 右 代码预览 ----
        self.code_preview = QPlainTextEdit()
        self.code_preview.setReadOnly(True)
        self.code_preview.setFont(QFont("DejaVu Sans Mono", 10))
        self.code_preview.setStyleSheet(
            "QPlainTextEdit { background:#282c34; color:#abb2bf;"
            " border:1px solid #3a3f4b; }"
        )
        self.code_preview.setPlaceholderText("点击「生成代码」后此处显示生成的 Python…")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.blockly)
        splitter.addWidget(self.code_preview)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([760, 500])

        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)
        lbl = QLabel("生成的 Python 代码 (对接 unitree_sdk2_python):")
        lbl.setStyleSheet("color:#abb2bf; padding:2px 6px;")
        cl.addWidget(lbl)
        cl.addWidget(splitter, 1)

        # 外层: 顶部工具栏 + 中央工作区
        outer = QWidget()
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(0)
        ol.addWidget(top)
        # ---- 网卡连接状态 (显示在网卡下拉框下方, 不占用下拉框) ----
        self.lbl_iface_state = QLabel("")
        self.lbl_iface_state.setStyleSheet(
            "color:#7f848e; padding:0 10px 4px 10px; font-size:12px;"
        )
        ol.addWidget(self.lbl_iface_state)
        ol.addWidget(container, 1)
        self.setCentralWidget(outer)

        # ---- 状态 Dock ----
        self.status_view = QTextBrowser()
        self.status_view.setStyleSheet(
            "QTextBrowser { background:#1e2127; color:#dcdfe6;"
            " border:1px solid #3a3f4b; font-family:'DejaVu Sans Mono'; font-size:12px; }"
        )
        self._update_status_display(None)
        dock_state = QDockWidget("实时状态", self)
        dock_state.setWidget(self.status_view)
        dock_state.setFeatures(QDockWidget.DockWidgetMovable)

        # ---- 摄像头 Dock (与实时状态 tab 合并, 避免右侧拥挤) ----
        self.camera_view = CameraView()
        dock_cam = QDockWidget("摄像头", self)
        dock_cam.setWidget(self.camera_view)
        dock_cam.setFeatures(QDockWidget.DockWidgetMovable)
        # 右侧两个 Dock tab 化共用一块区域, 默认显示摄像头
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock_state)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock_cam)
        self.tabifyDockWidget(dock_state, dock_cam)
        dock_cam.raise_()  # 默认前置显示摄像头
        # 给右侧 Dock 区更宽的初始占比 (放图像)
        self.resizeDocks([dock_cam], [420], Qt.Orientation.Horizontal)

        # ---- 日志 Dock ----
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("DejaVu Sans Mono", 10))
        self.log_view.setStyleSheet(
            "QPlainTextEdit { background:#1b1e25; color:#abb2bf;"
            " border:1px solid #3a3f4b; }"
        )
        dock_log = QDockWidget("运行日志", self)
        dock_log.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock_log)

        self.setStatusBar(QStatusBar())

    # ================================================================
    def _connect_signals(self):
        self.combo_robot.currentIndexChanged.connect(self._on_robot_changed)
        self.btn_connect.clicked.connect(self._on_connect)
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        self.btn_camera.clicked.connect(self._on_camera)
        self.btn_generate.clicked.connect(self._on_generate)
        self.btn_run.clicked.connect(self._on_run)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_export_py.clicked.connect(self._on_export_py)
        self.btn_save_xml.clicked.connect(self._on_save_xml)
        self.btn_load_xml.clicked.connect(self._on_load_xml)

        self.runner.lineLogged.connect(self._on_log)
        self.runner.finished.connect(self._on_run_finished)
        self.monitor.stateUpdated.connect(self._update_status_display)
        self.monitor.connectionChanged.connect(self._on_monitor_conn)
        # 机器人型号切换 (工作区重建) 后自动重新生成代码, 保证代码跟随顶部型号
        self.blockly.robotChanged.connect(
            lambda: QTimer.singleShot(50, self._on_generate)
        )

    # ================================================================
    # 网卡检测
    # ================================================================
    def _iface_info(self, name):
        """查询单块网卡的 (是否连接, IPv4地址)。用 Qt 的 QNetworkInterface 实现。"""
        up = False
        ipv4 = ""
        try:
            for ni in QNetworkInterface.allInterfaces():
                if ni.name() != name:
                    continue
                if ni.flags() & QNetworkInterface.InterfaceFlag.IsUp:
                    up = True
                for entry in ni.addressEntries():
                    ip = entry.ip().toString()
                    if ip and ":" not in ip:  # 只要 IPv4
                        ipv4 = ip
                        break
                if up and ipv4:
                    break
        except Exception:  # noqa: BLE001
            pass
        return up, ipv4

    def _list_interfaces(self):
        """返回本机网卡列表 [(name, up, ipv4), ...], 过滤回环口。"""
        names = []
        if sys.platform.startswith("linux"):
            try:
                names = sorted(os.listdir("/sys/class/net"))
            except OSError:
                pass
        else:
            # win/mac: 用 QNetworkInterface 取网卡名, 过滤回环
            for ni in QNetworkInterface.allInterfaces():
                if ni.flags() & QNetworkInterface.InterfaceFlag.IsLoopBack:
                    continue
                nm = ni.name() or ni.humanReadableName()
                if nm:
                    names.append(nm)
            names = sorted(set(names))
        out = []
        for name in names:
            if name == "lo":
                continue
            up, ipv4 = self._iface_info(name)
            out.append((name, up, ipv4))
        return out

    @staticmethod
    def _iface_display(item):
        """下拉框显示文本: 只显示纯网卡名 (连接状态与 IP 显示在下方标签)。"""
        return str(item[0])

    def _load_interfaces(self):
        """读取本机网卡并填入下拉框; 自动刷新时保持用户当前选择不变。"""
        # 用户正在手动输入或展开下拉列表时跳过自动刷新, 避免打断操作
        line_edit = getattr(self.iface_combo, "lineEdit", lambda: None)()
        refresh_btn_clicked = getattr(self, "_iface_manual_refresh", False)
        if not refresh_btn_clicked:
            if (line_edit is not None and line_edit.hasFocus()) \
                    or self.iface_combo.view().isVisible():
                return
        self._iface_manual_refresh = False

        items = self._list_interfaces()
        prof = get_profile(self._robot_key())

        # 记住当前选择 (纯网卡名)
        cur_idx = self.iface_combo.currentIndex()
        prev_name = None
        if cur_idx >= 0:
            data = self.iface_combo.itemData(cur_idx)
            if data:
                prev_name = str(data)
        if not prev_name:
            text_now = self.iface_combo.currentText().strip()
            if text_now:
                prev_name = text_now.split(" ")[0]

        self.iface_combo.blockSignals(True)
        self.iface_combo.clear()
        for it in items:
            self.iface_combo.addItem(self._iface_display(it), it[0])
        if hasattr(self, "_selected_iface") and self._selected_iface:
            prev_name = self._selected_iface

        target = prev_name or prof["default_iface"]
        idx = self.iface_combo.findData(target)
        if idx < 0:
            # 目标不在新列表里 (例如手动输入的名字): 尝试按前缀匹配显示文本
            idx = -1
            for i in range(self.iface_combo.count()):
                if self.iface_combo.itemData(i) == target \
                        or self.iface_combo.itemText(i).startswith(target + " "):
                    idx = i
                    break
        if idx >= 0:
            self.iface_combo.setCurrentIndex(idx)
            self._selected_iface = target
        elif items:
            self.iface_combo.setCurrentIndex(0)
            self._selected_iface = str(self.iface_combo.itemData(0))
        else:
            # 没有检测到任何物理网卡 (罕见): 保留型号默认值供手动编辑
            self.iface_combo.setEditText(prof["default_iface"])
            self._selected_iface = ""
        self.iface_combo.blockSignals(False)
        self._update_iface_state_label()

    def _on_refresh_ifaces(self):
        """点击「刷新」按钮: 强制重新扫描网卡。"""
        self._iface_manual_refresh = True
        self._load_interfaces()

    def _on_iface_activated(self, idx):
        """用户从下拉框选中一项时记住纯网卡名。"""
        data = self.iface_combo.itemData(idx)
        if data:
            self._selected_iface = str(data)

    def _current_iface(self) -> str:
        """取当前选择的纯网卡名 (优先 itemData, 手动输入取第一个空格前的词)。"""
        idx = self.iface_combo.currentIndex()
        if idx >= 0:
            data = self.iface_combo.itemData(idx)
            if data:
                return str(data)
        txt = self.iface_combo.currentText().strip()
        return txt.split(" ")[0] if txt else ""

    def _update_iface_state_label(self):
        """在网卡下拉框下方显示当前网卡及 IP 的两行状态:
        网卡: enp2s0
        (192.168.3.1)
        """
        name = self._current_iface().strip()
        if not name:
            self.lbl_iface_state.setText("网卡: —\n(未选择)")
            return
        try:
            up, ipv4 = self._iface_info(name)
        except Exception:  # noqa: BLE001
            up, ipv4 = False, None
        if up and ipv4:
            state = f"({ipv4})"
        elif up:
            state = "(已启用, 无 IP)"
        else:
            state = "(未连接)"
        self.lbl_iface_state.setText(f"网卡: {name}\n{state}")

    def _apply_robot_static_ip(self, name: str) -> bool:
        """按教程给网卡静态配置 192.168.123.241/24。
        linux 用 pkexec 图形授权; win/mac 无法图形授权, 弹窗给手动命令指引。"""
        # win/mac: 无 pkexec, 弹窗给手动命令 (用户配置后点「刷新」)
        if not sys.platform.startswith("linux"):
            if sys.platform == "win32":
                cmd = (f'netsh interface ip set address name="{name}" '
                       f'static 192.168.123.241 255.255.255.0 192.168.123.1')
                tip = ("Windows 无法图形授权配置 IP, 请以管理员身份打开 cmd/PowerShell 执行:\n\n"
                       f"  {cmd}\n\n配置后点「刷新」重新检测网卡。")
            else:  # darwin
                cmd = f"sudo ifconfig {name} 192.168.123.241 netmask 255.255.255.0"
                tip = ("macOS 无法图形授权配置 IP, 请在终端执行:\n\n"
                       f"  {cmd}\n\n配置后点「刷新」重新检测网卡。")
            QMessageBox.information(self, "手动配置 IP", tip)
            self._append_log("info", f"[网络] 请手动执行: {cmd}")
            return False
        # linux: pkexec 图形授权 (原逻辑)
        ip_path = shutil.which("ip")
        if ip_path is None:
            QMessageBox.critical(
                self, "配置失败",
                f"未找到 ip 命令, 请在终端手动执行:\n"
                f"  sudo ip addr add {_ROBOT_PC_ADDR} dev {name}",
            )
            return False
        pkexec = shutil.which("pkexec")
        if pkexec is None:
            QMessageBox.critical(
                self, "无法授权",
                "未找到 pkexec (polkit), 无法在图形界面申请管理员权限。\n"
                f"请在终端手动执行:\n"
                f"  sudo ip addr add {_ROBOT_PC_ADDR} dev {name}",
            )
            return False
        try:
            proc = subprocess.run(
                [pkexec, ip_path, "addr", "add", _ROBOT_PC_ADDR, "dev", name],
                capture_output=True, text=True, timeout=180,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "配置失败", f"执行失败: {exc}")
            return False
        if proc.returncode != 0 and "File exists" not in (proc.stderr or ""):
            # File exists = 该 IP 已配置过, 视为成功; 其余为授权取消/执行失败
            QMessageBox.critical(
                self, "配置失败",
                (proc.stderr or "授权被取消或命令执行失败").strip(),
            )
            return False
        self._append_log("info", f"[网络] 已为 {name} 配置静态 IP {_ROBOT_PC_ADDR}")
        # 顺手探测机器人是否在线 (仅日志提示, 不阻断运行)
        try:
            ret = subprocess.run(
                ["ping", "-c", "1", "-W", "1", _ROBOT_FIXED_IP],
                capture_output=True, timeout=3,
            ).returncode
            if ret == 0:
                self._append_log("info", f"[网络] ping {_ROBOT_FIXED_IP} 通, 机器人在线")
            else:
                self._append_log(
                    "warn",
                    f"[网络] ping {_ROBOT_FIXED_IP} 不通, 请确认机器人已开机、网线插好",
                )
        except Exception:  # noqa: BLE001
            pass
        self._iface_manual_refresh = True
        self._load_interfaces()
        return True

    def _ensure_iface_ready(self, name: str) -> bool:
        """运行/监控前预检网卡: 存在且已配置 IPv4; 无 IP 时按教程提供一键配置。

        CycloneDDS 按网卡名匹配要求接口有可用地址, 网卡无 IP 时
        ChannelFactoryInitialize 会报 "does not match an available interface"。
        Go2 网线直连不给电脑分 DHCP (见 tutorial_ws/lesson01): 机器人固定
        192.168.123.161, 电脑需静态配置 192.168.123.241/24。
        返回是否可以继续 (True 时网卡已就绪)。
        """
        if not name:
            QMessageBox.warning(
                self, "无法继续",
                "未选择网卡, 请在顶部「网卡」下拉框中选择连接机器人的网卡。",
            )
            return False
        up, ipv4 = self._iface_info(name)
        if not up:
            QMessageBox.warning(
                self, "无法继续",
                f"网卡 {name} 不存在或未启用。\n"
                "请检查 USB 网卡/网线是否插好, 并在下拉框中重新选择。",
            )
            return False
        if not ipv4:
            ret = QMessageBox.question(
                self, "网卡未配置 IP",
                f"网卡 {name} 已连接但未配置 IP, DDS 无法初始化。\n\n"
                f"按教程 (Lesson01) Go2 网线直连组网 (机器人不提供 DHCP):\n"
                f"  电脑网卡: {_ROBOT_PC_ADDR}\n"
                f"  机器人:   {_ROBOT_FIXED_IP} (出厂固定)\n\n"
                "现在一键配置静态 IP? (需要输入管理员密码)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if ret != QMessageBox.Yes:
                return False
            if not self._apply_robot_static_ip(name):
                return False
            _up, ipv4 = self._iface_info(name)
            if not ipv4:
                QMessageBox.warning(
                    self, "仍未获取 IP",
                    "配置后仍检测不到 IP, 请检查网线与机器人状态后重试。",
                )
                return False
        return True

    # ================================================================
    # 机器人型号切换
    # ================================================================
    def _robot_key(self) -> str:
        return self.combo_robot.currentData()

    def _on_robot_changed(self, _idx):
        key = self._robot_key()
        # 若用户尚未选网卡, 按型号默认网卡填充
        if not self.iface_combo.currentText().strip():
            self.iface_combo.setEditText(get_profile(key)["default_iface"])
        # 等视图就绪后通知前端切换工具箱
        QTimer.singleShot(50, lambda: self.blockly.set_robot_type(key))

    # ================================================================
    # 状态监控
    # ================================================================
    def _on_connect(self):
        name = self._current_iface()
        # 预检: 网卡无 IP 时 DDS 初始化必然失败, 提前拦截并支持一键配置
        if not self._ensure_iface_ready(name):
            return
        key = self._robot_key()
        self.monitor.start(name, key)
        self.btn_connect.setEnabled(False)
        self.btn_disconnect.setEnabled(True)

    def _on_disconnect(self):
        self.monitor.stop()
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)

    # ================================================================
    # 摄像头实时图像回传
    # ================================================================
    def _on_camera(self):
        """切换摄像头视频流。复用 monitor 的 DDS 初始化路径。"""
        if self.camera_view.is_running():
            self.camera_view.stop()
            self.btn_camera.setText("摄像头")
            self.statusBar().showMessage("摄像头已关闭", 3000)
            return
        name = self._current_iface()
        # 预检: 网卡无 IP 时 DDS 必然失败, 与状态监控一致提前拦截
        if not self._ensure_iface_ready(name):
            return
        key = self._robot_key()
        # 若 DDS 尚未初始化, 异步启动 monitor (后台初始化, 不阻塞 UI);
        # camera 的取帧循环会在 DDS 就绪后自动开始成功
        if not self.monitor.dds_inited:
            self.monitor.start(name, key)
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
        # VideoClient.Init + 取帧循环都在后台线程, 主线程立即返回不卡 UI
        self.camera_view.start()
        self.btn_camera.setText("关闭摄像头")
        self.statusBar().showMessage("摄像头开启中…", 3000)

    def _on_monitor_conn(self, connected: bool, msg: str):
        self.statusBar().showMessage(f"监控: {msg}", 5000)
        self._append_log("info" if connected else "warn", f"[监控] {msg}")

    def _update_status_display(self, state):
        if state is None:
            self.status_view.setHtml(
                "<div style='color:#888'>未连接。点击「连接状态监控」订阅 rt/lowstate</div>"
            )
            return
        rpy = state.get("rpy")
        rpy_s = f"R={rpy[0]:.2f} P={rpy[1]:.2f} Y={rpy[2]:.2f}" if rpy else "—"
        pv = state.get("power_v")
        pa = state.get("power_a")
        batt = f"{pv:.2f} V  {pa:.2f} A" if pv is not None and pa is not None else "—"
        motors = state.get("motors", [])
        mcount = state.get("motor_count", len(motors))
        rows = "".join(
            f"<tr><td>M{i:02d}</td><td style='color:#61afef'>{q:+.3f}</td></tr>"
            for i, q in enumerate(motors)
        )
        html = (
            f"<div style='color:#98c379'><b>{state.get('robot','').upper()} 状态</b></div>"
            f"<div style='color:#888'>IMU RPY: <span style='color:#dcdfe6'>{rpy_s}</span></div>"
            f"<div style='color:#888'>电池: <span style='color:#dcdfe6'>{batt}</span></div>"
            f"<div style='color:#888'>电机总数: <span style='color:#dcdfe6'>{mcount}</span></div>"
            f"<hr style='border-color:#3a3f4b'/>"
            f"<table style='color:#888'>{rows}</table>"
        )
        self.status_view.setHtml(html)

    # ================================================================
    # 代码生成 / 运行
    # ================================================================
    def _on_generate(self):
        iface = self._current_iface()
        def _cb(code):
            if code is None:
                code = "# 生成失败:未获取到代码"
            text = str(code)
            # 未搭建程序 (缺少「程序开始」块或其后未连接动作块) 时不生成有效代码
            if "# NO_PROGRAM" in text:
                self._current_code = ""
                self.code_preview.setPlainText(
                    text.replace("# NO_PROGRAM:", "").strip()
                )
                self._append_log("warn", "未生成代码: 请先添加「程序开始」块并连接动作块")
                return
            self._current_code = text
            self.code_preview.setPlainText(text)
            self._append_log("info", f"代码已生成 ({len(text)} 字符)")
        self.blockly.generate_code(iface, _cb)

    def _on_run(self):
        # 点击运行总是先按当前积木重新生成最新代码, 再执行
        iface = self._current_iface()
        def _cb(code):
            text = str(code or "")
            if "# NO_PROGRAM" in text:
                self._current_code = ""
                QMessageBox.warning(
                    self, "提示",
                    "未生成代码: 请先添加「程序开始」块, 并在其后连接动作块",
                )
                return
            if text.strip() and not text.lstrip().startswith("# 页面未就绪"):
                self._current_code = text
                self.code_preview.setPlainText(self._current_code)
                self._do_run()
            else:
                QMessageBox.warning(self, "提示", "生成代码失败, 无法运行")
        self.blockly.generate_code(iface, _cb)

    def _do_run(self):
        if self.runner.is_running():
            QMessageBox.warning(self, "提示", "已有程序在运行")
            return
        # 预检: 网卡无 IP 时 DDS 初始化必然失败, 提前拦截并支持一键配置
        if not self._ensure_iface_ready(self._current_iface()):
            return
        # 运行前安全确认: 防止误触, 默认选中"否"
        _SAFE_MSG = (
            "即将运行程序, 向真实机器人发送指令。\n\n"
            "请确保机器人处在宽阔的空间, 且附近无人或物。\n"
            "高风险动作 (如空翻) 请务必清空场地后再执行。\n\n"
            "确认运行?"
        )
        if QMessageBox.question(
            self, "运行确认", _SAFE_MSG,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        os.makedirs(_RUNTIME_DIR, exist_ok=True)
        try:
            with open(_RUN_SCRIPT, "w", encoding="utf-8") as f:
                f.write(self._current_code)
        except OSError as exc:
            QMessageBox.critical(self, "写文件失败", str(exc))
            return
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.runner.run(_RUN_SCRIPT)

    def _on_stop(self):
        self.runner.stop()

    def _on_run_finished(self, _ok, _code):
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)

    # ================================================================
    # 导出 / 程序存取
    # ================================================================
    def _on_export_py(self):
        if not self._current_code.strip():
            QMessageBox.information(self, "提示", "请先生成代码")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Python 文件", "unitree_program.py", "Python (*.py)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._current_code)
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "已导出", path)

    def _on_save_xml(self):
        def _cb(xml):
            if not xml:
                QMessageBox.warning(self, "提示", "工作区为空")
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "保存 Blockly 程序", "program.xml", "XML (*.xml)"
            )
            if not path:
                return
            with open(path, "w", encoding="utf-8") as f:
                f.write(xml)
            QMessageBox.information(self, "已保存", path)
        self.blockly.export_xml(_cb)

    def _on_load_xml(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "载入 Blockly 程序", "", "XML (*.xml)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                xml = f.read()
        except OSError as exc:
            QMessageBox.critical(self, "读取失败", str(exc))
            return
        self.blockly.import_xml(xml, lambda ok: self._append_log(
            "info" if ok else "err", f"导入 XML {'成功' if ok else '失败'}"))

    # ================================================================
    # 日志
    # ================================================================
    def _append_log(self, level: str, text: str):
        color = {"out": "#abb2bf", "err": "#e06c75", "warn": "#e5c07b",
                  "info": "#61afef"}.get(level, "#abb2bf")
        self.log_view.appendHtml(
            f"<span style='color:{color}'>{text}</span>"
        )

    def _on_log(self, level: str, text: str):
        self._append_log(level, text)

    # ================================================================
    def closeEvent(self, event):
        self.runner.stop()
        self.camera_view.stop()
        self.monitor.stop()
        super().closeEvent(event)
