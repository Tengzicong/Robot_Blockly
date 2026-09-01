#!/usr/bin/env bash
# ============================================================================
# 从 blockly-unitree.svg 生成 Windows .ico 与 macOS .icns
#
# 依赖: ImageMagick (magick) 或 rsvg-convert + iconutil(仅 mac) + sips
# 用法: bash packaging/icons/gen_icons.sh
# 产物: packaging/icons/blockly-unitree.ico / blockly-unitree.icns
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"
SVG="${ROOT}/blockly-unitree.svg"
OUT="${HERE}"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

[ -f "${SVG}" ] || { echo "!! 找不到 ${SVG}" >&2; exit 1; }

# ----------------------------- ICO (Windows) ----------------------------
ICO="${OUT}/blockly-unitree.ico"
if command -v magick >/dev/null 2>&1; then
  echo "==> 生成 ICO (ImageMagick)..."
  magick convert -background none "${SVG}" \
    -define icon:auto-resize=256,128,64,48,32,16 "${ICO}"
  echo "    -> ${ICO}"
elif command -v convert >/dev/null 2>&1; then
  echo "==> 生成 ICO (convert)..."
  convert -background none "${SVG}" \
    -define icon:auto-resize=256,128,64,48,32,16 "${ICO}"
  echo "    -> ${ICO}"
else
  echo "!! 未找到 ImageMagick, 跳过 ICO 生成" >&2
fi

# ----------------------------- ICNS (macOS) ------------------------------
ICNS="${OUT}/blockly-unitree.icns"
if command -v rsvg-convert >/dev/null 2>&1; then
  echo "==> 生成 ICNS (rsvg-convert + iconutil/sips)..."
  ICONSET="${TMP}/blockly-unitree.iconset"
  mkdir -p "${ICONSET}"
  for s in 16 32 128 256 512; do
    s2=$((s * 2))
    rsvg-convert -w "${s}" -h "${s}" -o "${ICONSET}/icon_${s}x${s}.png" "${SVG}"
    rsvg-convert -w "${s2}" -h "${s2}" -o "${ICONSET}/icon_${s}x${s}@2x.png" "${SVG}"
  done
  if command -v iconutil >/dev/null 2>&1; then
    iconutil -c icns "${ICONSET}" -o "${ICNS}"
    echo "    -> ${ICNS}"
  elif command -v sips >/dev/null 2>&1; then
    # 无 iconutil (非 macOS) 时退化为单尺寸 icns 容器
    sips -s format icns "${ICONSET}/icon_512x512@2x.png" --out "${ICNS}" >/dev/null
    echo "    -> ${ICNS} (单尺寸回退)"
  else
    echo "!! 缺少 iconutil/sips, 跳过 ICNS 生成" >&2
  fi
else
  echo "!! 未找到 rsvg-convert, 跳过 ICNS 生成" >&2
fi

echo "==> 完成"
