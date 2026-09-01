#!/usr/bin/env bash
# ============================================================================
# Robot Blockly  Linux arm64 (aarch64) deb 构建脚本
#
# 原理: 本机是 x86_64 时用 docker + buildx + qemu 模拟 arm64 环境, 在容器内:
#   1) 编译 cyclonedds==0.10.2 的 aarch64 wheel (PyPI 无此 wheel)
#   2) 复用 build_deb.sh 产出 deb (conda-based, 首次启动时 conda-forge 装
#      PySide6 + 本地 wheel 装 cyclonedds 0.10.2)
#
# 用法 (在仓库根 unitree/ 执行):
#     bash blockly_unitree/packaging/build_linux_arm64.sh
#
# 前置: 本机装 docker (含 buildx) 且已注册 binfmt (multarch/qemu):
#     docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
#
# 产物: blockly_unitree/dist/blockly-unitree_0.1.0_all.deb
#       blockly_unitree/wheels/*.whl  (aarch64 cyclonedds)
# ============================================================================
set -euo pipefail

# 仓库根 (unitree/) 与 blockly_unitree 根
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="${ROOT_DIR}/blockly_unitree"
IMAGE="blockly-unitree-arm64:latest"

echo "==> 仓库根: ${ROOT_DIR}"
echo "==> 应用根: ${APP_DIR}"

# ----------------------------- 0) 前置检查 ------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "!! 未找到 docker" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "!! docker 未运行或当前用户无权限" >&2
  exit 1
fi
# 本机已是 arm64 则无需 qemu
if [ "$(uname -m)" != "aarch64" ]; then
  echo "==> 本机为 $(uname -m), 依赖 qemu+binfmt 模拟 arm64..."
  # 幂等注册 binfmt
  docker run --rm --privileged multiarch/qemu-user-static --reset -p yes >/dev/null 2>&1 || {
    echo "!! 注册 qemu binfmt 失败; 请手动执行:" >&2
    echo "   docker run --rm --privileged multiarch/qemu-user-static --reset -p yes" >&2
    exit 1
  }
fi

# ----------------------------- 1) 构建镜像 ------------------------------
echo "==> 构建 arm64 构建镜像..."
docker build --platform linux/arm64 \
  -f "${APP_DIR}/packaging/Dockerfile.arm64" \
  -t "${IMAGE}" \
  "${ROOT_DIR}"

# ----------------------------- 2) 容器内编译 wheel + 打包 deb ------------
echo "==> 容器内编译 cyclonedds 0.10.2 (aarch64) 并构建 deb..."
mkdir -p "${APP_DIR}/wheels" "${APP_DIR}/dist"
docker run --rm --platform linux/arm64 \
  -v "${APP_DIR}/wheels:/workspace/blockly_unitree/wheels" \
  -v "${APP_DIR}/dist:/workspace/blockly_unitree/dist" \
  "${IMAGE}" bash -c '
    set -euo pipefail
    cd /workspace/blockly_unitree
    # 已有 wheel 则跳过编译
    if ls /workspace/blockly_unitree/wheels/*.whl >/dev/null 2>&1; then
      echo "==> 使用已有 wheel"
    else
      echo "==> 编译 cyclonedds==0.10.2 (aarch64)..."
      /venv/bin/python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --upgrade pip wheel >/dev/null
      /venv/bin/python -m pip wheel -i https://pypi.tuna.tsinghua.edu.cn/simple \
        --no-binary=cyclonedds --no-cache-dir \
        -w /workspace/blockly_unitree/wheels cyclonedds==0.10.2
    fi
    bash packaging/build_deb.sh
  '

echo ""
echo "==> 构建完成:"
ls -lh "${APP_DIR}"/dist/blockly-unitree_*.deb 2>/dev/null || echo "  (deb 未生成, 请检查日志)"
ls -lh "${APP_DIR}"/wheels/*.whl 2>/dev/null || echo "  (wheels 未生成)"
echo ""
echo "==> 在 arm64 机器安装:"
echo "    sudo apt install ./blockly-unitree_0.1.0_all.deb"
