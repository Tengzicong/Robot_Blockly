# -*- coding: utf-8 -*-
"""
Blockly 视图: QWebEngineView 加载本地 blockly.html, 提供 Python→JS 调用接口。

容错: WebEngine 初始化在某些环境会崩溃, 故延迟创建并在失败时降级为文本提示,
避免拖垮整个主窗口。
"""

import os

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QScreen, QGuiApplication
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextBrowser

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _WEBENGINE_AVAILABLE = False


class BlocklyView(QWidget):
    """Blockly 工作区视图, 封装 QWebEngineView 与 JS 交互。"""

    # 页面加载结束 (成功或失败/降级) 后发出, 启动页据此收尾
    loadFinished = Signal(bool)
    # 机器人型号已切换 (工作区已重建) 后发出, 主窗口据此重新生成代码预览
    robotChanged = Signal()


    def __init__(self, parent=None):
        super().__init__(parent)
        self.web_view = None
        self._tried = False
        self._failed = False
        self._fallback = None
        self._page_loaded = False
        self._pending_robot = None
        # 已绑定过 screenChanged 的 QWindow, 防止重复 connect
        self._bound_window_handle = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._placeholder = QLabel("正在加载 Blockly 积木编程环境...")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            "QLabel { background:#fff; color:#555; font-size:14px; }"
        )
        layout.addWidget(self._placeholder)

    # ----------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if not self._tried:
            self._tried = True
            self._try_init_webengine()
        # 首次 show 后窗口句柄才可用, 在此绑定 screenChanged (不同版本 PySide6
        # QWebEngineView 本身未必有 screenChanged 信号, 统一通过 windowHandle() 取)
        self._ensure_screen_changed_bound()
        self.apply_screen_dpr()

    def _ensure_screen_changed_bound(self):
        """若 windowHandle 已出现且尚未绑 screenChanged, 则绑定一次。"""
        if self._bound_window_handle is not None or self.web_view is None:
            return
        try:
            wh = self.web_view.windowHandle()
        except Exception:  # noqa: BLE001
            wh = None
        if wh is None:
            return
        try:
            if hasattr(wh, "screenChanged"):
                wh.screenChanged.connect(self.apply_screen_dpr)
            self._bound_window_handle = wh
        except Exception:  # noqa: BLE001
            pass

    def _try_init_webengine(self):
        if not _WEBENGINE_AVAILABLE:
            self._show_fallback("QtWebEngine 运行时未安装, 无法显示 Blockly。")
            return
        try:
            self.web_view = QWebEngineView()
            self.layout().removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._placeholder = None
            self.layout().addWidget(self.web_view)
            html_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "resources", "blockly.html",
            )
            self.web_view.load(QUrl.fromLocalFile(html_path))
            self.web_view.loadFinished.connect(self._on_load_finished)
            # 注: screenChanged 绑定放在 showEvent/_ensure_screen_changed_bound,
            # 因为当前 PySide6 的 QWebEngineView 没有该信号, 需要等 windowHandle()
            # 可用后从 QWindow 取。
            try:
                self.apply_screen_dpr()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            self._failed = True
            self.web_view = None
            self._show_fallback(
                f"Blockly 页面加载失败: {exc}\n"
                "可在浏览器直接打开 resources/blockly.html 使用。"
            )

    def _show_fallback(self, message: str):
        self._failed = True
        if self.web_view is not None:
            self.web_view.deleteLater()
            self.web_view = None
        if self._placeholder is not None:
            self.layout().removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._placeholder = None
        self._fallback = QTextBrowser()
        self._fallback.setPlainText(message)
        self._fallback.setStyleSheet(
            "QTextBrowser { background:#1e2127; color:#abb2bf;"
            " border:1px solid #3a3f4b; padding:12px; font-size:13px; }"
        )
        self.layout().addWidget(self._fallback)
        # 降级也算"加载结束", 让启动页能收尾
        self.loadFinished.emit(False)

    @property
    def available(self) -> bool:
        return self.web_view is not None

    def _on_load_finished(self, ok):
        self._page_loaded = bool(ok)
        self.loadFinished.emit(bool(ok))
        if ok and self._pending_robot is not None:
            robot = self._pending_robot
            self._pending_robot = None
            self._do_set_robot_type(robot)

    # ----------------------------------------------------------------
    # Python → JS 调用
    # ----------------------------------------------------------------
    def run_js(self, script: str, callback=None):
        """执行任意 JS, 可选回调。"""
        if self.web_view is None:
            if callback is not None:
                callback(None)
            return
        if callback is not None:
            self.web_view.page().runJavaScript(script, callback)
        else:
            self.web_view.page().runJavaScript(script)

    def _do_set_robot_type(self, robot: str):
        self.run_js(f"setRobotType({robot!r});")
        # 工作区已在 JS 中重建, 通知主窗口重新生成代码 (runJavaScript 按顺序排队,
        # 后续的生成调用必然在本调用之后执行, 无竞态)
        self.robotChanged.emit()

    def set_robot_type(self, robot: str):
        # 页面未就绪则缓存, 待 loadFinished 后应用
        if not self._page_loaded:
            self._pending_robot = robot
            return
        self._do_set_robot_type(robot)

    def generate_code(self, iface, callback):
        """注入网络接口后请求生成 Python 代码, 通过 callback(code:str) 返回。"""
        if self.web_view is None:
            callback("# Blockly 不可用 (WebEngine 加载失败)")
            return
        # 先注入 iface, 再生成 (单次 JS 调用保证顺序)
        safe_iface = (iface or "").replace("\\", "\\\\").replace("'", "\\'")
        js = (
            f"setIface('{safe_iface}');"
            " (typeof generatePythonCode === 'function') ? generatePythonCode()"
            " : '# 页面未就绪';"
        )
        self.web_view.page().runJavaScript(js, callback)

    def export_xml(self, callback):
        self.run_js("exportXml();", callback)

    def import_xml(self, xml_text: str, callback=None):
        safe = xml_text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        self.run_js(f"importXml('{safe}');", callback)

    def clear_workspace(self):
        self.run_js("clearWorkspace();")

    # ----------------------------------------------------------------
    # 外接显示器 DPR 缩放: Chromium 侧默认按主屏 DPR 渲染, 窗口拖到外接
    # 屏后字体会糊或过大。这里按当前屏幕 devicePixelRatio 主动修正
    # setZoomFactor, 使网页像素密度跟随目标屏幕。
    # ----------------------------------------------------------------
    def apply_screen_dpr(self, screen: QScreen = None):
        """按屏幕校正 WebEngine 页面缩放。

        注意: Qt 高分屏 (QT_ENABLE_HIGHDPI_SCALING=1) 已将 CSS 像素与屏幕像素做了
        初步映射, 此处不再按 devicePixelRatio 再放大一次 —— 否则会导致 Blockly
        内置组件 (垃圾桶 / zoom 按钮 / 工具箱折叠手柄) 显示成过大的占位图。
        统一把 zoomFactor 设为 1.0, 并在页面侧通过 zelos 渲染器 + 绝对 media
        路径保证 sprite 正确加载与尺寸正常。
        """
        if self.web_view is None:
            return
        try:
            self.web_view.setZoomFactor(1.0)
        except Exception:  # noqa: BLE001
            pass
