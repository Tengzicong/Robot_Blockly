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
- **跨平台** — Linux (x64 / arm64)、Windows 10+、macOS 12+ (Intel / Apple Silicon)目前仅支持Linux amd64版本

## 快速开始

### 使用安装包安装
[Linux x64](https://github.com/Tengzicong/Robot_Blockly/releases/latest/download/Robot-blockly_0.1.2_amd64.deb)
[mac intel](https://github.com/Tengzicong/Robot_Blockly/releases/latest/download/RobotBlockly-0.1.1-x86_64.dmg)


### 从源码运行(不建议)

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

## 打包构建

各平台构建脚本位于 `blockly_unitree/packaging/`。**PyInstaller 不支持交叉编译**，产物必须在同架构、同系统的机器上构建。

| 平台 | 脚本 | 产物 | 构建机要求 |
|---|---|---|---|
| Linux (x64/arm64) | `build_deb.sh` | `blockly-unitree_<ver>_all.deb` | 任意 Linux |
| Windows x64 | `build_win.ps1` | `dist/RobotBlockly/` | Windows x64 |
| macOS Intel | `build_mac.sh` | `RobotBlockly-<ver>-x86_64.dmg` | **Intel Mac** |
| macOS Silicon | `build_mac.sh` | `RobotBlockly-<ver>-arm64.dmg` | **Apple Silicon** |

### macOS 构建（最低支持 macOS 12）

```bash
# 前置: Xcode 命令行工具 + Python 3.10+
xcode-select --install

git clone https://gitee.com/tengzicong/robot_blockly.git
cd robot_blockly

# Intel Mac 出包（脚本会断言本机架构，不匹配直接报错）
TARGET_ARCH=x86_64 bash blockly_unitree/packaging/build_mac.sh
```

产物输出到 `blockly_unitree/dist/`，脚本结束时自动打印架构与系统下限校验：

```bash
lipo -archs  RobotBlockly.app/Contents/MacOS/RobotBlockly        # 期望 x86_64
otool -l     RobotBlockly.app/Contents/MacOS/RobotBlockly \
  | grep -A3 LC_BUILD_VERSION                                    # 期望 minos 12.0
```

> **macOS 12 兼容的关键约束**：PySide6 6.10+ 的 wheel 标签为 `macosx_13_0`，会把产物下限抬到 macOS 13。`requirements.txt` 已在 darwin 平台锁定 `PySide6<6.10`，请勿放宽。

### 安装说明（macOS）

本软件**未做 Apple 开发者签名与公证**（无证书），首次打开会被 Gatekeeper 拦截。任选一种方式：

1. **右键**应用图标 → **打开** → 弹窗中再点**打开**（仅需一次）
2. 系统设置 → 隐私与安全性 → 底部提示处点击**仍要打开**
3. 终端移除隔离属性：
   ```bash
   xattr -dr com.apple.quarantine /Applications/RobotBlockly.app
   ```

安装步骤：双击挂载 `.dmg` → 将 `RobotBlockly.app` 拖入 `Applications` → 弹出磁盘。

要求：**macOS 12 Monterey 及以上**。

## 反馈
如果您有任何反馈。您可以在体验后进入[issues](https://gitee.com/tengzicong/robot_blockly/issues)进行反馈!您的每一份宝贵建议我们都会认真阅读!

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
