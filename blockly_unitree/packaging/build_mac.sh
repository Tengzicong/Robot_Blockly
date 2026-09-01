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
# 前置: macOS 12+; Python 3.10+ (推荐 homebrew/miniforge); Xcode CLT;
#       (可选) hdiutil 为系统自带。
# ============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK_ROOT="$(cd "${ROOT_DIR}/../unitree_sdk2_python" && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
SPEC="${ROOT_DIR}/packaging/blockly_unitree.spec"
VERSION="0.1.0"
ARCH="$(uname -m)"   # arm64 | x86_64

echo "==> 项目根: ${ROOT_DIR}"
echo "==> SDK 目录: ${SDK_ROOT}"
echo "==> 构建架构: ${ARCH}"

if [ ! -d "${SDK_ROOT}/unitree_sdk2py" ]; then
  echo "!! 找不到 ${SDK_ROOT}/unitree_sdk2py" >&2
  exit 1
fi

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
echo "==> 分发说明: 用户挂载 dmg 后把 RobotBlockly.app 拖入 Applications;"
echo "    未签名分发首启需右键→打开, 或执行:"
echo "        xattr -dr com.apple.quarantine /Applications/RobotBlockly.app"
