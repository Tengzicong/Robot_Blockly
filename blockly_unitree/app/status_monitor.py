# -*- coding: utf-8 -*-
"""
实时状态监控: 通过 unitree_sdk2py 的 ChannelSubscriber 订阅 rt/lowstate,
在 DDS 后台线程回调中解析 IMU / 电池 / 电机状态, 经 Qt 信号推送到 UI。

设计:
  - ChannelFactoryInitialize 全进程只调用一次 (由 start() 首次触发)。
  - 切换机器人型号时重新订阅对应 LowState 类型。
  - watchdog QTimer 检测数据超时, 标记连接异常。
"""

import time

from PySide6.QtCore import QObject, QTimer, Signal

from .robot_profiles import get_profile, load_lowstate_class


class StatusMonitor(QObject):
    # state: dict { rpy:[r,p,y], power_v, power_a, motors:[...], t }
    stateUpdated = Signal(dict)
    # connected, message
    connectionChanged = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._factory_inited = False
        self._sub = None
        self._robot = None
        self._lowstate_cls = None
        self._last_msg_ts = 0.0
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(2000)
        self._watchdog.timeout.connect(self._check_alive)

    # ----------------------------------------------------------------
    @property
    def dds_inited(self) -> bool:
        """DDS ChannelFactory 是否已在本进程初始化 (全进程一次)。"""
        return self._factory_inited

    # ----------------------------------------------------------------
    def start(self, iface: str, robot: str) -> None:
        """初始化 DDS 并订阅 lowstate。可重复调用来切换型号。

        ChannelFactoryInitialize 可能阻塞数秒 (网卡 SPDP discovery), 放到
        后台线程执行避免卡 UI; 完成后回主线程做订阅 (QTimer 必须主线程)。
        """
        import threading
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize

        # 关闭旧订阅
        self._stop_subscriber()

        self._robot = robot
        self._lowstate_cls = load_lowstate_class(robot)
        if self._lowstate_cls is None:
            self.connectionChanged.emit(False, f"无法加载 {robot} 的 LowState 类型")
            return

        profile = get_profile(robot)
        # ChannelFactoryInitialize 全进程一次
        if not self._factory_inited:
            iface_arg = iface.strip() if iface else None
            self.connectionChanged.emit(True, "正在初始化 DDS 连接…")

            def _dds_init():
                try:
                    if iface_arg:
                        ChannelFactoryInitialize(0, iface_arg)
                    else:
                        ChannelFactoryInitialize(0)
                    self._factory_inited = True
                    # 回主线程完成订阅 + 启动 watchdog (QTimer 必须主线程)
                    QTimer.singleShot(0, lambda: self._finish_start(profile))
                except Exception as exc:  # noqa: BLE001
                    self.connectionChanged.emit(False, f"DDS 初始化失败: {exc}")

            threading.Thread(target=_dds_init, daemon=True).start()
            return

        self._finish_start(profile)

    def _finish_start(self, profile) -> None:
        """DDS 就绪后在主线程完成订阅 (由 start 直接调或经 QTimer 回调调)。"""
        from unitree_sdk2py.core.channel import ChannelSubscriber
        try:
            self._sub = ChannelSubscriber(profile["lowstate_topic"], self._lowstate_cls)
            self._sub.Init(self._handler, 10)
        except Exception as exc:  # noqa: BLE001
            self.connectionChanged.emit(False, f"订阅 lowstate 失败: {exc}")
            return

        self._last_msg_ts = time.time()
        self._watchdog.start()
        self.connectionChanged.emit(True, f"已订阅 {profile['label']} 状态")

    # ----------------------------------------------------------------
    def stop(self) -> None:
        self._watchdog.stop()
        self._stop_subscriber()
        self.connectionChanged.emit(False, "已断开状态监控")

    def _stop_subscriber(self) -> None:
        # SDK 的 ChannelSubscriber 无显式 close, 置空交由 GC
        self._sub = None

    # ----------------------------------------------------------------
    def _handler(self, msg) -> None:
        """DDS 后台线程回调: 解析并发射信号 (Qt 自动跨线程派发)。"""
        try:
            self._last_msg_ts = time.time()
            state = {"t": self._last_msg_ts, "robot": self._robot}

            # IMU
            imu = getattr(msg, "imu_state", None)
            rpy = None
            if imu is not None:
                rpy = getattr(imu, "rpy", None)
            if rpy is not None:
                try:
                    state["rpy"] = [float(rpy[0]), float(rpy[1]), float(rpy[2])]
                except Exception:  # noqa: BLE001
                    state["rpy"] = None
            # 电池
            for f in ("power_v", "power_a"):
                v = getattr(msg, f, None)
                if v is not None:
                    try:
                        state[f] = float(v)
                    except Exception:  # noqa: BLE001
                        pass
            # 电机关节角
            motors = getattr(msg, "motor_state", None)
            if motors is not None:
                qs = []
                n = len(motors)
                for i in range(min(n, 12)):
                    m = motors[i]
                    q = getattr(m, "q", None)
                    try:
                        qs.append(round(float(q), 3) if q is not None else 0.0)
                    except Exception:  # noqa: BLE001
                        qs.append(0.0)
                state["motors"] = qs
                state["motor_count"] = n

            self.stateUpdated.emit(state)
        except Exception as exc:  # noqa: BLE001
            # 回调中绝不让异常冒泡到 DDS
            print(f"[status] 解析状态出错: {exc}")

    # ----------------------------------------------------------------
    def _check_alive(self) -> None:
        if self._sub is None:
            return
        dt = time.time() - self._last_msg_ts
        if dt > 3.0:
            self.connectionChanged.emit(False, f"无状态数据 ({dt:.0f}s)")
