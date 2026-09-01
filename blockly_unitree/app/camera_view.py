# -*- coding: utf-8 -*-
"""
摄像头实时图像回传 + 雷达点云俯视图叠加。

摄像头: 通过 unitree_sdk2py 的 VideoClient 循环调用 GetImageSample() 获取
JPEG 字节流, 后台线程拉取, Qt 信号推送到主线程解码显示。

雷达: 订阅 rt/utlidar/cloud_deskewed (sensor_msgs/PointCloud2_, 10Hz), 取离地
5~60cm 高度切片 (传感器离地 0.40m), 投影成俯视图叠加在摄像头画面右上角。

依赖: DDS ChannelFactoryInitialize 必须已由 StatusMonitor 首次调用完成
(全进程只初始化一次)。
"""

import time
import threading

from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
import numpy as np


# --- 雷达点云参数 ---
LIDAR_TOPIC = "rt/utlidar/cloud_deskewed"  # 去畸变点云 (10791点/帧, 稠密连续不抽搐; DDS 订阅不阻塞, 延迟稳定不受 RPC 抖动影响)
LIDAR_RANGE = 8.0        # 俯视图显示半径 (米, 覆盖避障感知范围)
LIDAR_SIZE = 128         # 雷达图边长 (像素, 叠加在画面右上角)
Z_FLOOR_MIN = 0.05       # 取离地 5cm 以上 (z 已是离地高度)
Z_FLOOR_MAX = 0.60       # 取离地 60cm 以下 (避开地面与高处干扰)
# overlay 样式: 无图时半透明黑底显诊断文字; 有图时透明叠加不挡画面
_OVERLAY_BLANK = ("QLabel { background: rgba(0,0,0,170); color:#4dd0e1; "
                  "font-size:11px; border:1px solid rgba(77,208,225,180); "
                  "border-radius:3px; }")
_OVERLAY_IMG = ("QLabel { background: transparent; "
                "border:1px solid rgba(77,208,225,120); border-radius:3px; }")
# PointField datatype -> numpy 格式
_PF_DT = {1: "i1", 2: "u1", 3: "i2", 4: "u2", 5: "i4", 6: "u4", 7: "f4", 8: "f8"}

# 预计算雷达图同心圆刻度掩码 (1/2/3m) 与中心十字, 避免每帧重算 O(size²)
_LIDAR_CX = _LIDAR_CY = LIDAR_SIZE // 2
_LIDAR_SCALE = (LIDAR_SIZE / 2 - 4) / LIDAR_RANGE
_yy, _xx = np.indices((LIDAR_SIZE, LIDAR_SIZE))
_dist = np.sqrt((_xx - _LIDAR_CX) ** 2 + (_yy - _LIDAR_CY) ** 2)
_LIDAR_RINGS = np.zeros((LIDAR_SIZE, LIDAR_SIZE), dtype=bool)
for _r_m in (2, 4, 6):  # 2m/4m/6m 刻度环
    _r_px = int(_r_m * _LIDAR_SCALE)
    _LIDAR_RINGS |= np.abs(_dist - _r_px) < 1
del _yy, _xx, _dist  # 释放临时数组


class CameraStream(QObject):
    """后台拉取 JPEG 视频帧, 存最新帧供主线程定时取用 (平滑 RPC 抖动)。"""

    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._client = None
        self._thread = None
        self._running = False
        self._latest_bytes = None  # 后台写, 主线程读 (GIL 下原子)

    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """启动视频流拉取。复用已初始化的 client 直接拉帧, 首次才创建+Init。"""
        if self._running:
            return
        self._running = True
        self._latest_bytes = None  # 清旧帧, 避免重启闪上一帧
        if self._client is not None:
            # 复用 client, 直接拉帧 (重启秒出画面, 不重新 Init)
            self._thread = threading.Thread(target=self._loop, daemon=True)
        else:
            self._thread = threading.Thread(target=self._init_then_loop, daemon=True)
        self._thread.start()

    def _init_then_loop(self) -> None:
        from unitree_sdk2py.go2.video.video_client import VideoClient
        try:
            self._client = VideoClient()
            self._client.SetTimeout(1.5)  # 直连局域网 <500ms, 失败不必等 3s
            self._client.Init()
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"摄像头客户端初始化失败: {exc}")
            self._client = None
            self._running = False
            return
        self._loop()

    def stop(self) -> None:
        self._running = False
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=5.0)
        self._thread = None
        # 保留 _client 复用, 避免重启摄像头重新 Init (秒级延迟)

    def _loop(self) -> None:
        consec_fail = 0
        while self._running:
            try:
                # GetImageSample 是阻塞 RPC, 成功本身耗时 (SDK 上限 ~10fps)
                code, data = self._client.GetImageSample()
                if code == 0 and data:
                    self._latest_bytes = bytes(data)  # 存最新, 主线程定时取
                    consec_fail = 0
                    # 不 sleep: GetImageSample 阻塞已限速, 让 RPC 尽快填 latest
                else:
                    consec_fail += 1
                    if consec_fail == 5:
                        self.error.emit(
                            f"未获取到画面 (code={code}), 请检查机器人连接与网卡配置"
                        )
                    time.sleep(0.3)  # 失败退避, 防止快速返回空转打满 CPU
            except Exception as exc:  # noqa: BLE001
                self.error.emit(f"取帧异常: {exc}")
                time.sleep(1.0)
                continue


class LidarStream(QObject):
    """订阅 Go2 雷达点云, 解析为俯视图 QImage 推送到主线程。

    回调在 DDS 线程触发: numpy 解析 + 切片 + 生成 QImage, 通过 Qt 信号
    (自动 Queued) 派发到主线程显示。
    """

    lidarReady = Signal(QImage)
    status = Signal(str)  # 诊断状态: 订阅中/收到N帧/渲染None 等
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sub = None
        self._thread = None
        self._running = False
        self._msg_seen = False
        self._count = 0

    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._subscribe, daemon=True)
        self._thread.start()

    def _subscribe(self) -> None:
        from unitree_sdk2py.core.channel import ChannelSubscriber
        from unitree_sdk2py.idl.sensor_msgs.msg.dds_ import PointCloud2_
        # DDS 可能还在后台初始化 (monitor.start 异步); 且 ChannelSubscriber.Init
        # 在 factory 未就绪时可能静默成功但 reader 无效收不到数据。故订阅后做
        # 健康检查: 4 秒内未收到数据则销毁重订阅, 直到收到为止。
        while self._running:
            self.status.emit("雷达订阅中…")
            try:
                sub = ChannelSubscriber(LIDAR_TOPIC, PointCloud2_)
                sub.Init(self._handle, 5)
                self._sub = sub
                self._msg_seen = False
                self.status.emit("已订阅, 等待点云…")
                # 健康检查: 4 秒内收到数据则订阅有效
                for _ in range(80):
                    if not self._running:
                        return
                    if self._msg_seen:
                        self.status.emit("订阅有效, 开始出图")
                        return  # 收到数据, 订阅有效, 后续由 DDS 回调驱动
                    time.sleep(0.05)
                # 4 秒无数据: DDS 未就绪或订阅静默失败, 销毁重订阅
                self.status.emit("4秒无数据, 重新订阅…")
                self._sub = None
            except Exception as exc:  # noqa: BLE001
                self.status.emit(f"订阅异常: {exc}")
                time.sleep(0.5)  # factory 未就绪, 等待重试

    def stop(self) -> None:
        self._running = False
        self._sub = None  # 旧订阅随对象回收; _handle 首行 check 阻止后续处理
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _handle(self, msg) -> None:
        if not self._running:
            return
        self._msg_seen = True  # 健康检查: 已收到数据, 订阅有效
        self._count += 1
        if self._count % 2:  # 跳帧: 15Hz -> ~7.5Hz, 降 CPU (deskewed 点密集, 7.5Hz 仍连续)
            return
        try:
            img = self._render_topdown(msg)
            if img is not None:
                self.status.emit(f"收到 {self._count} 帧, 出图")
                self.lidarReady.emit(img)
            else:
                self.status.emit(f"收到 {self._count} 帧但渲染返回 None")
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"点云处理异常: {exc}")
            self.status.emit(f"渲染异常: {exc}")

    @staticmethod
    def _render_topdown(msg) -> QImage | None:
        data = bytes(msg.data)
        step = msg.point_step
        if not data or step == 0:
            return None
        endian = ">" if msg.is_bigendian else "<"
        names, fmts, offs = [], [], []
        for f in msg.fields:
            names.append(f.name)
            fmts.append(endian + _PF_DT.get(f.datatype, "f4"))
            offs.append(f.offset)
        try:
            dtype = np.dtype(
                {"names": names, "formats": fmts, "offsets": offs, "itemsize": step}
            )
            arr = np.frombuffer(data, dtype=dtype)
            if not {"x", "y", "z"}.issubset(arr.dtype.names):
                return None
            x = np.asarray(arr["x"], dtype=np.float32)
            y = np.asarray(arr["y"], dtype=np.float32)
            z = np.asarray(arr["z"], dtype=np.float32)
        except Exception:  # noqa: BLE001
            return None
        # z 已是离地高度, 取 5~60cm 障碍层; 点过少则兜底用全部点
        m = (z > Z_FLOOR_MIN) & (z < Z_FLOOR_MAX)
        xc, yc = x[m], y[m]
        if len(xc) < 50:
            xc, yc = x, y
        m = (np.abs(xc) < LIDAR_RANGE) & (np.abs(yc) < LIDAR_RANGE)
        x, y = xc[m], yc[m]
        size = LIDAR_SIZE
        cx, cy = _LIDAR_CX, _LIDAR_CY
        scale = _LIDAR_SCALE
        buf = np.zeros((size, size, 4), dtype=np.uint8)  # RGBA 透明底
        # 坐标系: x 前向(上), y 左向(左)
        sx = (cx - y * scale).astype(np.int32)
        sy = (cy - x * scale).astype(np.int32)
        ok = (sx >= 0) & (sx < size) & (sy >= 0) & (sy < size)
        sx, sy = sx[ok], sy[ok]
        buf[sy, sx] = (0x4d, 0xd0, 0xe1, 255)  # 青色点
        # 中心红色十字 + 同心圆刻度 (掩码预计算, 不每帧重算)
        for k in range(-3, 4):
            buf[cy + k, cx] = (0xff, 0x60, 0x60, 255)
            buf[cy, cx + k] = (0xff, 0x60, 0x60, 255)
        buf[_LIDAR_RINGS] = (0x33, 0x66, 0x88, 120)
        img = QImage(buf.tobytes(), size, size, size * 4, QImage.Format_RGBA8888)
        return img.copy()  # 深拷贝脱离 numpy buffer 生命周期


class CameraView(QWidget):
    """摄像头画面 + 右上角雷达点云俯视图叠加。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stream = CameraStream(self)
        self.stream.error.connect(self._on_error)
        # 显示用独立定时器 (10fps), 不跟 RPC 抖动 → 画面稳定不忽快忽慢
        self._disp_timer = QTimer(self)
        self._disp_timer.setInterval(100)
        self._disp_timer.timeout.connect(self._display_latest)
        self._last_jpeg = None  # 上次显示的 bytes, is 比较避免重复解码

        self.lidar = LidarStream(self)
        self.lidar.lidarReady.connect(self._on_lidar)
        self.lidar.status.connect(self._on_lidar_status)
        self.lidar.error.connect(lambda m: self.overlay.setToolTip(m))
        self._has_lidar_pixmap = False

        self.label = QLabel("点击「摄像头」按钮开启实时图像回传")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(480, 360)
        self.label.setStyleSheet(
            "QLabel { background:#000; color:#888; font-size:13px; }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label, 1)

        # 右上角雷达俯视图叠加层 (浮在摄像头画面上)
        self.overlay = QLabel("雷达", self)
        self.overlay.setFixedSize(LIDAR_SIZE, LIDAR_SIZE)
        self.overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay.setWordWrap(True)
        self.overlay.setStyleSheet(_OVERLAY_BLANK)
        self.overlay.raise_()
        self.overlay.move(8, 8)

        self._pixmap = None

    def start(self) -> None:
        self.label.setText("正在获取画面…")
        self.stream.start()
        self._disp_timer.start()
        self.overlay.setText("雷达")
        self.lidar.start()

    def stop(self) -> None:
        self._disp_timer.stop()
        self.stream.stop()
        self.lidar.stop()
        self.overlay.clear()
        self.overlay.setText("雷达")
        self.overlay.setStyleSheet(_OVERLAY_BLANK)
        self._has_lidar_pixmap = False
        self.label.clear()
        self._pixmap = None
        self._last_jpeg = None
        self.label.setText("摄像头已停止")
        self.label.setStyleSheet(
            "QLabel { background:#000; color:#888; font-size:13px; }"
        )

    def is_running(self) -> bool:
        return self.stream.is_running()

    def _display_latest(self) -> None:
        # 主线程定时 (10fps) 取后台最新 JPEG 解码显示, 不跟 RPC 抖动
        b = self.stream._latest_bytes
        if b is None or b is self._last_jpeg:
            return  # 无新帧, 保持上一帧 (避免闪烁)
        pix = QPixmap()
        if not pix.loadFromData(b, "JPEG"):
            return
        self._pixmap = pix
        self._last_jpeg = b
        self.label.setStyleSheet(
            "QLabel { background:#000; color:#888; font-size:13px; }"
        )
        self._render()

    def _on_lidar(self, img: QImage) -> None:
        # 切到透明背景样式, 让点云叠加在画面上不遮挡
        self.overlay.setStyleSheet(_OVERLAY_IMG)
        self.overlay.setText("")
        pix = QPixmap.fromImage(img).scaled(
            self.overlay.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.overlay.setPixmap(pix)
        self._has_lidar_pixmap = True

    def _on_lidar_status(self, msg: str) -> None:
        # 无图时 overlay 显示诊断状态; 有图后状态仅放 tooltip
        if not self._has_lidar_pixmap:
            self.overlay.setStyleSheet(_OVERLAY_BLANK)
            self.overlay.setText(msg)
        self.overlay.setToolTip(msg)

    def _on_error(self, msg: str) -> None:
        self.label.setText(f"摄像头错误: {msg}")
        self.label.setStyleSheet(
            "QLabel { background:#200; color:#f88; font-size:13px; }"
        )

    def _render(self) -> None:
        if self._pixmap is None:
            return
        scaled = self._pixmap.scaled(
            self.label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.label.setPixmap(scaled)

    def resizeEvent(self, event):  # noqa: N802 - Qt 命名
        # overlay 固定在右上角
        self.overlay.move(self.width() - self.overlay.width() - 8, 8)
        if self._pixmap is not None:
            self._render()
        super().resizeEvent(event)
