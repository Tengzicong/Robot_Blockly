# -*- coding: utf-8 -*-
"""启动加载动画页 (Splash Screen)。

无边框置顶小窗: 深色圆角卡片 + 旋转圆环 + 扫描进度条 + 呼吸标题,
标题固定显示 "ERROR-CORE Team", 状态文字由主程序各加载阶段更新。
"""

import math

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QGuiApplication
from PySide6.QtWidgets import QWidget


class SplashScreen(QWidget):
    """启动页动画窗口。用法:

        splash = SplashScreen()
        splash.show()
        ...
        splash.set_status("正在加载 Blockly...")
        ...
        splash.finish()   # 淡出并关闭
    """

    _CARD_BG = QColor(20, 22, 28, 245)
    _CARD_BORDER = QColor(64, 72, 92)
    _ACCENT = QColor(97, 175, 239)      # 蓝 #61afef
    _TEXT_MAIN = QColor(235, 240, 248)
    _TEXT_SUB = QColor(150, 160, 178)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFixedSize(480, 320)

        self._title = "Robot Blockly"
        self._subtitle = "机器人开发平台"
        self._status = "正在初始化..."
        self._angle = 0.0        # 旋转圆环角度
        self._tick_count = 0     # 用于标题呼吸与扫描条相位
        self._progress = 0.05    # 视觉进度 (渐近 0.98, 不可信不用于真实进度)
        self._closing = False

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30fps
        self._timer.timeout.connect(self._on_tick)

    # ----------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def center_on_cursor(self):
        """把启动页居中到鼠标光标所在屏幕。"""
        try:
            cursor_pos = QGuiApplication.primaryScreen().cursor().pos()
            screen = QGuiApplication.screenAt(cursor_pos) \
                or QGuiApplication.primaryScreen()
            if screen is None:
                return
            geo = screen.availableGeometry()
            x = geo.x() + max(0, (geo.width() - self.width()) // 2)
            y = geo.y() + max(0, (geo.height() - self.height()) // 2)
            self.move(x, y)
        except Exception:  # noqa: BLE001
            pass  # 默认位置兜底

    # ----------------------------------------------------------------
    def set_status(self, text: str):
        if text != self._status:
            self._status = text
            self.update()

    def finish(self, on_closed=None):
        """淡出后关闭 (幂等), 关闭完成后再调用 on_closed() (例如显示主窗口)。"""
        if on_closed is not None:
            self._on_finish_closed = on_closed
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        try:
            anim = QPropertyAnimation(self, b"windowOpacity", self)
            anim.setDuration(280)
            anim.setStartValue(self.windowOpacity())
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(self._finish_done)
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        except Exception:  # noqa: BLE001
            self._finish_done()

    def _finish_done(self):
        self.close()
        cb = getattr(self, "_on_finish_closed", None)
        self._on_finish_closed = None
        if cb is not None:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    # ----------------------------------------------------------------
    def _on_tick(self):
        self._tick_count += 1
        self._angle = (self._angle + 9.0) % 360.0
        # 渐近推进视觉进度, 制造"快好了但永不撒谎满格"的效果
        self._progress = min(0.98, self._progress + (0.99 - self._progress) * 0.02)
        self.update()

    # ----------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing, True
        )
        w, h = self.width(), self.height()

        # ---- 卡片背景 ----
        radius = 18.0
        painter.setPen(QPen(self._CARD_BORDER, 1))
        painter.setBrush(self._CARD_BG)
        painter.drawRoundedRect(8, 8, w - 16, h - 16, radius, radius)

        # ---- 标题 (呼吸透明度) ----
        breath = 0.5 + 0.5 * math.sin(self._tick_count * 0.07)
        title_alpha = int(190 + 65 * breath)
        title_color = QColor(self._TEXT_MAIN)
        title_color.setAlpha(title_alpha)
        f_title = QFont()
        f_title.setPointSize(26)
        f_title.setBold(True)
        painter.setFont(f_title)
        painter.setPen(title_color)
        painter.drawText(0, 84, w, 44,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         self._title)

        # ---- 副标题 ----
        f_sub = QFont()
        f_sub.setPointSize(11)
        painter.setFont(f_sub)
        painter.setPen(self._TEXT_SUB)
        painter.drawText(0, 130, w, 26,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         self._subtitle)

        # ---- 状态文字 ----
        f_status = QFont()
        f_status.setPointSize(10)
        painter.setFont(f_status)
        painter.setPen(self._TEXT_SUB)
        painter.drawText(0, 168, w, 24,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         self._status)

        # ---- 终端风格 "Hello,World!" (等宽绿字 + 淡入淡出循环) ----
        fade = 0.5 + 0.5 * math.sin(self._tick_count * 0.05)
        hello_alpha = int(40 + 215 * fade)
        hello_color = QColor(51, 255, 102)  # 终端绿 #33ff66
        hello_color.setAlpha(hello_alpha)
        f_hello = QFont("DejaVu Sans Mono", 12)
        f_hello.setBold(False)
        painter.setFont(f_hello)
        painter.setPen(hello_color)
        painter.drawText(0, 208, w, 30,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         "Hello,World!")

        # ---- 版权信息 ----
        copyright_color = QColor(105, 115, 135)
        f_copy = QFont()
        f_copy.setPointSize(8)
        painter.setFont(f_copy)
        painter.setPen(copyright_color)
        painter.drawText(0, h - 58, w, 18,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         "Copyright © ERROR-CORE Team · 保留所有权利")

        # ---- 适用范围 (最底部小字) ----
        f_dis = QFont()
        f_dis.setPointSize(7)
        painter.setFont(f_dis)
        painter.setPen(QColor(120, 128, 142))
        painter.drawText(0, h - 26, w, 18,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         "本软件适用于宇树(Unitree)Go2与G1机器人")

        # ---- 底部扫描进度条 ----
        bar_h, bar_y = 4, h - 40
        margin = 48
        bar_w = w - margin * 2
        bar_rect_x = margin
        bar_rect_y = bar_y
        # 轨道
        painter.setPen(Qt.PenStyle.NoPen)
        track = QColor(52, 58, 74)
        painter.drawRoundedRect(bar_rect_x, bar_rect_y, bar_w, bar_h, 2, 2)
        # 扫描段: 进度前沿后拖一段高亮尾巴
        head = self._progress
        tail = max(0.0, head - 0.12)
        seg_x = int(bar_rect_x + tail * bar_w)
        seg_w = max(6, int((head - tail) * bar_w))
        glow = QColor(self._ACCENT)
        glow.setAlpha(200)
        painter.setBrush(glow)
        painter.drawRoundedRect(seg_x, bar_rect_y, seg_w, bar_h, 2, 2)
