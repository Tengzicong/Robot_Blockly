# -*- coding: utf-8 -*-
"""PyInstaller 入口脚本 (Windows / macOS 自包含打包用)。

以绝对导入方式启动 app.main, 使 frozen 后的相对导入正常工作。
Linux deb 模式不使用此入口 (启动器直接 python -m app.main)。
"""

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
