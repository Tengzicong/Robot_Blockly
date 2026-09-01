# -*- coding: utf-8 -*-
"""机器人型号配置: 决定 LowState 消息类型、电机数、动作客户端。"""

import sys

PROFILES = {
    "go2": {
        "label": "Go2 (四足)",
        "lowstate_topic": "rt/lowstate",
        "lowstate_module": "unitree_sdk2py.idl.unitree_go.msg.dds_",
        "lowstate_class": "LowState_",
        "num_motors": 12,
        "client_doc": "SportClient (高层动作)",
    },
    "g1": {
        "label": "G1 (人形)",
        "lowstate_topic": "rt/lowstate",
        "lowstate_module": "unitree_sdk2py.idl.unitree_hg.msg.dds_",
        "lowstate_class": "LowState_",
        "num_motors": 29,
        "client_doc": "LocoClient (步态) + ArmAction (手臂)",
    },
}


def _default_iface() -> str:
    """平台感知默认网卡名。win 网卡名随机, 留空让用户下拉选。"""
    if sys.platform.startswith("linux"):
        return "enp2s0"
    if sys.platform == "darwin":
        return "en0"
    return ""  # win32


def get_profile(robot: str) -> dict:
    p = dict(PROFILES.get(robot, PROFILES["go2"]))
    p["default_iface"] = _default_iface()
    return p


def load_lowstate_class(robot: str):
    """动态导入对应机器人的 LowState 消息类。失败返回 None。"""
    import importlib

    p = get_profile(robot)
    try:
        mod = importlib.import_module(p["lowstate_module"])
        return getattr(mod, p["lowstate_class"])
    except Exception as exc:  # noqa: BLE001
        print(f"[status] 无法导入 {robot} 的 LowState 类型: {exc}")
        return None
