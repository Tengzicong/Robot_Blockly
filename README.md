# Robot Blockly

宇树机器人可视化积木编程桌面软件 —— 拖拽积木即可生成 Python 代码，一键运行对接 [unitree_sdk2py](https://github.com/unitreerobotics/unitree_sdk2_python)。

支持 Go2 四足机器人与 G1 人形机器人，提供积木编程、代码生成、实时运行、状态监控、摄像头回传与激光雷达点云可视化。

> ⚠️ **请务必在使用前阅读 [免责声明](DISCLAIMER.md)。**

---

## 主要功能

- **积木编程** — 基于 [Blockly](https://developers.google.com/blockly)，拖拽搭建动作序列，支持循环/条件嵌套
- **代码生成** — 一键生成可读的 Python 代码，对接 unitree_sdk2py
- **一键运行** — 直接执行生成脚本，实时捕获输出到日志面板
- **实时状态监控** — DDS 订阅 `rt/lowstate`，显示 IMU / 电池 / 电机状态
- **摄像头回传** — 实时显示机器人摄像头画面
- **激光雷达点云** — 叠加显示 Go2 激光雷达点云，支持测距标尺
- **程序存取** — Blockly XML 工程文件保存 / 加载 / 导出 `.py`
- **跨平台** — Linux (x64 / arm64)、Windows 10+、macOS 12+ (Intel / Apple Silicon)
- ## (目前仅支持Linux amd版本)

## 快速开始

### 从源码运行

```bash
# 1. 创建 conda 环境 (Python 3.10)
conda create -n unitree python=3.10 -y
conda activate unitree

# 2. 安装依赖
cd blockly_unitree
pip install -r requirements.txt

# 3. 获取宇树官方 SDK (第三方组件, 见下方"第三方组件")
git clone https://github.com/unitreerobotics/unitree_sdk2_python.git ../unitree_sdk2_python
pip install -e ../unitree_sdk2_python

# 4. 启动
python -m app.main
```

### 网络配置（有线直连 Go2）

Go2 出厂固定 IP 为 `192.168.123.161`，不提供 DHCP。需将电脑网卡通配静态 IP `192.168.123.241/24`：

```bash
# Linux
sudo ip addr add 192.168.123.241/24 dev <网卡名>

# macOS
sudo ifconfig <网卡名> 192.168.123.241 netmask 255.255.255.0
```

软件内置网卡检测与一键配置（Linux），选择正确的有线网口即可。

### 固件要求

- Go2 固件 ≥ 1.1.6（MCF 模式）
- 运动控制需先调用 `BalanceStand()` 解锁，再发送 `Move` 指令

## 项目结构

```
unitree/
├── blockly_unitree/          # 本项目
│   ├── app/                  # Python 源码
│   │   ├── main.py           # 应用入口
│   │   ├── main_window.py    # 主窗口
│   │   ├── blockly_view.py   # Blockly WebEngine 视图
│   │   ├── code_runner.py    # 代码运行器
│   │   ├── status_monitor.py # 状态监控 (DDS)
│   │   ├── camera_view.py    # 摄像头 + 雷达点云
│   │   ├── splash.py         # 启动加载画面
│   │   ├── env_setup.py      # conda 环境自动管理
│   │   ├── robot_profiles.py # 机器人型号配置
│   │   └── _paths.py         # 跨平台路径解析
│   ├── resources/            # Blockly 资源 (JS/HTML/media)
│   ├── packaging/            # 打包脚本 (deb/dmg/Windows)
│   └── requirements.txt
├── .github/                  # GitHub Actions 自动构建
├── README.md
└── DISCLAIMER.md
```

> 注：`unitree_sdk2_python`（宇树官方 SDK）与 `tutorial_ws`（教程工作区）为第三方内容，不属于本仓库；打包脚本会在缺少 SDK 时从官方 GitHub 自动拉取。

## 第三方组件

| 组件 | 来源 | 协议 |
|---|---|---|
| [unitree_sdk2py](https://github.com/unitreerobotics/unitree_sdk2_python) | 宇树官方 Python SDK | BSD-3-Clause |
| [Blockly](https://developers.google.com/blockly) | Google 开源积木编辑器 | Apache-2.0 |

以上组件的版权归其各自作者所有，本软件仅在构建/运行时引用，不包含第三方代码的修改。

## 免责声明

本软件为作者独立创作，与宇树（Unitree）公司及其关联实体不存在任何隶属、合作或代理关系，亦未从该公司获得任何形式的授权、赞助或技术支持。

本软件仅用于技术研究、学习与交流目的。使用本工具操作任何机器人所产生的全部风险与后果，均由使用者自行承担。

详见 [DISCLAIMER.md](DISCLAIMER.md)。

## License

Copyright © ERROR-CORE Team. 保留所有权利。

本项目仅供研究学习用途，不构成任何商业授权。

## 许可证
MIT License