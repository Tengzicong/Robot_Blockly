# 构建与打包指南 (Building & Packaging)

本仓库采用**混合打包策略**，覆盖 Linux (x86_64 / arm64)、Windows、macOS。

> Windows 仅支持 **64 位**：PySide6 官方没有 32 位 wheel，32 位 Windows 无法运行本软件。

## 1. 一键构建所有平台（推荐，开源后用）

仓库已内置 GitHub Actions 工作流 [.github/workflows/build.yml](../.github/workflows/build.yml)：

1. 推送到 GitHub
2. 打一个 tag（如 `v0.1.0`）触发构建：

```bash
git tag v0.1.0
git push origin v0.1.0
```

或手动在 Actions 页面点 `Run workflow`。

自动产出 5 份 Artifacts：

| Artifact | 内容 |
|---|---|
| `linux-x64-deb` | `blockly-unitree_0.1.0_all.deb` |
| `linux-arm64-deb` | `blockly-unitree_0.1.0_all.deb` + aarch64 `cyclonedds` wheel |
| `windows-x64` | `RobotBlockly/` 单目录（含 `RobotBlockly.exe`） |
| `macos-arm64` | `RobotBlockly-0.1.0-arm64.dmg` |
| `macos-x86_64` | `RobotBlockly-0.1.0-x86_64.dmg` |

## 2. 各平台本地构建

### Linux (x86_64 或 arm64) — deb

deb 是 conda-based、`Architecture: all`，**同一 deb 两架构通用**（首次启动自动创建 `unitree` conda 环境并装依赖）。

```bash
cd blockly_unitree
bash packaging/build_deb.sh
# 产物: dist/blockly-unitree_0.1.0_all.deb
```

arm64 如需捆绑预编译 `cyclonedds==0.10.2` wheel（PyPI 无 aarch64 wheel，运行时会回退 conda-forge 0.10.5），需在装有 docker 的机器执行：

```bash
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
bash blockly_unitree/packaging/build_linux_arm64.sh
```

### Windows — 单目录 + exe

在 **Windows 10/11 x64** 机器上，装好 Python 3.10+（或 miniconda）：

```powershell
cd blockly_unitree
powershell -ExecutionPolicy Bypass -File packaging/build_win.ps1
# 产物: dist\RobotBlockly\  (含 RobotBlockly.exe)
```

如需 NSIS 安装程序（可选）：

```powershell
makensis packaging\installer_win.nsi
```

### macOS — dmg（arm64 / x86_64 各打各的）

在对应架构的 macOS 12+ 机器上（Apple Silicon 打 arm64，Intel 打 x86_64）：

```bash
cd blockly_unitree
brew install librsvg   # 首次需 rsvg-convert 生成 ICNS
bash packaging/build_mac.sh
# 产物: dist/RobotBlockly-0.1.0-<arch>.dmg
```

未签名分发说明：用户首次打开 `.app` 需 `右键 → 打开`，或执行：

```bash
xattr -dr com.apple.quarantine /Applications/RobotBlockly.app
```

## 3. 构建依赖

`requirements.txt`（构建机）：

```
PySide6>=6.5,<6.12
cyclonedds==0.10.2
numpy
pyinstaller>=6.0,<7.0
```

注意：`cyclonedds` **必须锁 0.10.2**（SDK 要求；更高版本会破坏与机器人的 DDS SPDP 发现）。

## 4. 安装使用

- **Linux**：`sudo apt install ./blockly-unitree_0.1.0_all.deb`，应用菜单「Robot Blockly」或终端 `blockly-unitree`
- **Windows**：运行 `RobotBlockly.exe`（首次启动会自动创建 conda 环境并装依赖，需联网）
- **macOS**：把 `RobotBlockly.app` 拖入 `/Applications`
