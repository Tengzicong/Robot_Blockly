#!/usr/bin/env bash
# 完全脱离终端运行 arm64 构建 (日志: /tmp/arm64_build7.log)
set -uo pipefail
cd /home/zicong/Desktop/unitree || exit 1
nohup sg docker -c 'bash blockly_unitree/packaging/build_linux_arm64.sh' \
  >/tmp/arm64_build7.log 2>&1 &
echo "launched pid=$!"
