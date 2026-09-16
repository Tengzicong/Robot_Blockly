#!/usr/bin/env bash
# ============================================================================
# Robot Blockly  macOS 构建脚本 (Apple Silicon arm64 或 Intel x86_64)
#
# 用法 (在项目根目录 blockly_unitree/ 执行):
#     bash packaging/build_mac.sh
#
# 产物: dist/RobotBlockly-<VERSION>-<arch>.dmg
#   - arm64 机跑 → _arm64.dmg; x86_64 机跑 → _x86_64.dmg (各打各的)
#
# 用法 (指定目标架构, 例如为 Intel Mac 出包):
#     TARGET_ARCH=x86_64 bash packaging/build_mac.sh
#
# 前置: macOS 12+; Python 3.10+ (推荐 homebrew/miniforge); Xcode CLT;
#       (可选) hdiutil 为系统自带。
#
# 签名: 本脚本不执行任何 codesign / notarize (无 Developer ID 证书)。
#       产物为未签名包, 用户首启需右键→打开, 见文末提示。
# ============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK_ROOT="${ROOT_DIR}/../unitree_sdk2_python"
DIST_DIR="${ROOT_DIR}/dist"
SPEC="${ROOT_DIR}/packaging/blockly_unitree.spec"
VERSION="0.1.1"

# 最低支持系统版本: 决定 Mach-O 的 LC_BUILD_VERSION.minos, 直接影响能否在旧系统运行
MIN_MACOS="${MIN_MACOS:-12.0}"
export MACOSX_DEPLOYMENT_TARGET="${MIN_MACOS}"

# 目标架构: PyInstaller 不支持交叉编译, 只能在本机架构上构建。
# 显式指定时做断言, 防止在 arm64 机器上产出名为 x86_64 的包。
ARCH="$(uname -m)"   # arm64 | x86_64
if [ -n "${TARGET_ARCH:-}" ] && [ "${TARGET_ARCH}" != "${ARCH}" ]; then
  echo "!! 架构不匹配: 本机为 ${ARCH}, 但 TARGET_ARCH=${TARGET_ARCH}" >&2
  echo "   PyInstaller 无法交叉编译。请在 ${TARGET_ARCH} 机器上构建, 或去掉 TARGET_ARCH。" >&2
  exit 1
fi

echo "==> 项目根: ${ROOT_DIR}"
echo "==> 构建架构: ${ARCH}"
echo "==> 最低系统: macOS ${MIN_MACOS}"

# SDK 仓库被 gitignore, CI/新机器上不存在时自动拉取
if [ ! -d "${SDK_ROOT}/unitree_sdk2py" ]; then
  echo "==> 未找到 SDK, 正在克隆 unitree_sdk2_python..."
  git clone --depth 1 https://github.com/unitreerobotics/unitree_sdk2_python.git "${SDK_ROOT}"
fi
SDK_ROOT="$(cd "${SDK_ROOT}" && pwd)"
echo "==> SDK 目录: ${SDK_ROOT}"

# ----------------------------- 1) Python --------------------------------
PY="$(command -v python3 || true)"
if [ -z "${PY}" ]; then
  echo "!! 找不到 python3, 请先安装 Python 3.10+" >&2
  exit 1
fi
echo "==> Python: $(${PY} --version 2>&1)"

# ----------------------------- 2) 依赖 --------------------------------
echo "==> 安装构建依赖 (requirements.txt)..."
"${PY}" -m pip install --disable-pip-version-check -r "${ROOT_DIR}/requirements.txt"
"${PY}" -m pip install --disable-pip-version-check -e "${SDK_ROOT}"

# ----------------------------- 3) 图标 (ICNS) ---------------------------
ICONS_DIR="${ROOT_DIR}/packaging/icons"
ICNS="${ICONS_DIR}/blockly-unitree.icns"
if [ ! -f "${ICNS}" ]; then
  echo "==> 尝试生成 ICNS 图标..."
  SVG="${ROOT_DIR}/blockly-unitree.svg"
  if command -v iconutil >/dev/null 2>&1 && command -v sips >/dev/null 2>&1 \
     && command -v rsvg-convert >/dev/null 2>&1; then
    TMPDIR_ICONS="$(mktemp -d)"
    ICONSET="${TMPDIR_ICONS}/blockly-unitree.iconset"
    mkdir -p "${ICONSET}"
    for s in 16 32 128 256 512; do
      rsvg-convert -w ${s} -h ${s} -o "${ICONSET}/icon_${s}x${s}.png" "${SVG}"
      s2=$((s * 2))
      rsvg-convert -w ${s2} -h ${s2} -o "${ICONSET}/icon_${s}x${s}@2x.png" "${SVG}"
    done
    iconutil -c icns "${ICONSET}" -o "${ICNS}"
    rm -rf "${TMPDIR_ICONS}"
    echo "    -> ICNS 已生成"
  else
    echo "    [跳过] 缺少 rsvg-convert; PyInstaller 将使用默认图标" >&2
  fi
fi

# ----------------------------- 4) PyInstaller ---------------------------
echo "==> PyInstaller 构建 (.app)..."
mkdir -p "${DIST_DIR}"
"${PY}" -m PyInstaller "${SPEC}" --noconfirm \
  --distpath "${DIST_DIR}" \
  --workpath "${DIST_DIR}/build_mac_${ARCH}"

APP="${DIST_DIR}/RobotBlockly.app"
if [ ! -d "${APP}" ]; then
  echo "!! 构建失败: ${APP} 不存在" >&2
  exit 1
fi

# 去除隔离属性 (未签名分发, 用户首启可双击; 长期应做 Developer ID 签名+公证)
xattr -dr com.apple.quarantine "${APP}" 2>/dev/null || true

# ----------------------------- 5) DMG --------------------------------
DMG_NAME="RobotBlockly-${VERSION}-${ARCH}.dmg"
DMG_PATH="${DIST_DIR}/${DMG_NAME}"
echo "==> 制作 DMG: ${DMG_NAME}..."
rm -f "${DMG_PATH}"
TMP_DMG="$(mktemp -d)/dmgbuild"
mkdir -p "${TMP_DMG}"
ln -sf /Applications "${TMP_DMG}/Applications"
cp -R "${APP}" "${TMP_DMG}/"
hdiutil create -volname "Robot Blockly" -srcfolder "${TMP_DMG}" \
  -ov -format UDZO "${DMG_PATH}" >/dev/null
rm -rf "${TMP_DMG}"

echo ""
echo "==> 构建完成: ${DMG_PATH}"

# ----------------------------- 6) 产物自校验 -----------------------------
# 确认架构与最低系统版本符合预期, 避免交付错误产物
BIN="${APP}/Contents/MacOS/RobotBlockly"
if command -v lipo >/dev/null 2>&1; then
  echo "==> 产物架构: $(lipo -archs "${BIN}" 2>/dev/null || echo '未知')"
fi
if command -v otool >/dev/null 2>&1; then
  MINOS="$(otool -l "${BIN}" 2>/dev/null | awk '/LC_BUILD_VERSION/{f=1} f&&/minos/{print $2; exit}')"
  echo "==> 最低系统 (LC_BUILD_VERSION.minos): ${MINOS:-未知}"
  if [ -n "${MINOS:-}" ] && [ "$(printf '%s\n%s\n' "${MIN_MACOS}" "${MINOS}" | sort -V | head -1)" != "${MIN_MACOS}" ]; then
    echo "   ⚠️ 实际下限 ${MINOS} 高于目标 ${MIN_MACOS}, 产物无法在 macOS ${MIN_MACOS} 运行。" >&2
    echo "      原因通常是依赖 wheel 本身要求更高系统版本, 请检查 PySide6 版本 (<6.10)。" >&2
  fi
fi

echo ""
echo "==> 分发说明: 用户挂载 dmg 后把 RobotBlockly.app 拖入 Applications;"
echo "    未签名分发首启需右键→打开, 或执行:"
echo "        xattr -dr com.apple.quarantine /Applications/RobotBlockly.app"
