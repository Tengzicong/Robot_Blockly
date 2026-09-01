# ============================================================================
# 宇树 Blockly  Windows 构建脚本 (PowerShell)
#
# 用法 (在项目根目录 blockly_unitree/ 执行):
#     powershell -ExecutionPolicy Bypass -File packaging/build_win.ps1
#
# 产物: dist/RobotBlockly/ (单目录, 含 RobotBlockly.exe)
#
# 前置: 本机已装 Python 3.10+ (或 miniconda), 且能 pip install 联网。
# ============================================================================
$ErrorActionPreference = "Stop"

$ROOT = Split-Path -Parent $PSScriptRoot        # blockly_unitree/
$SDK_ROOT = Join-Path $ROOT "..\unitree_sdk2_python"
$DIST = Join-Path $ROOT "dist"
$SPEC = Join-Path $PSScriptRoot "blockly_unitree.spec"

Write-Host "==> 项目根: $ROOT" -ForegroundColor Cyan
Write-Host "==> SDK 目录: $SDK_ROOT" -ForegroundColor Cyan

# ------------------------------------------------------------------
# 1) 检查 Python
# ------------------------------------------------------------------
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { $pyExe = "py" } else { $pyExe = "" }
} else {
    $pyExe = "python"
}
if (-not $pyExe) {
    Write-Host "!! 找不到 Python, 请先安装 Python 3.10+ 或 miniconda" -ForegroundColor Red
    exit 1
}
Write-Host "==> Python: $(& $pyExe --version 2>&1)"

# ------------------------------------------------------------------
# 2) 安装构建依赖
# ------------------------------------------------------------------
Write-Host "==> 安装构建依赖 (requirements.txt)..." -ForegroundColor Yellow
& $pyExe -m pip install --disable-pip-version-check -r (Join-Path $ROOT "requirements.txt")
if ($LASTEXITCODE -ne 0) { Write-Host "!! 依赖安装失败" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------------
# 3) editable 安装 SDK
# ------------------------------------------------------------------
$sdkInit = Join-Path $SDK_ROOT "unitree_sdk2py\__init__.py"
if (-not (Test-Path $sdkInit)) {
    Write-Host "!! 找不到 $sdkInit, 无法安装 SDK" -ForegroundColor Red
    exit 1
}
Write-Host "==> 安装 unitree_sdk2py (editable)..." -ForegroundColor Yellow
& $pyExe -m pip install --disable-pip-version-check -e $SDK_ROOT
if ($LASTEXITCODE -ne 0) { Write-Host "!! SDK 安装失败" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------------
# 4) 生成图标 (如有 SVG → ICO 转换工具)
# ------------------------------------------------------------------
$iconsDir = Join-Path $PSScriptRoot "icons"
$icoFile = Join-Path $iconsDir "blockly-unitree.ico"
if (-not (Test-Path $icoFile)) {
    Write-Host "==> 尝试生成 ICO 图标..." -ForegroundColor Yellow
    $svg = Join-Path $ROOT "blockly-unitree.svg"
    $magick = Get-Command magick -ErrorAction SilentlyContinue
    if ($magick -and (Test-Path $svg)) {
        & magick convert -background none $svg `
            (Join-Path $iconsDir "blockly-unitree.ico")
        Write-Host "    -> ICO 已生成"
    } else {
        Write-Host "    [跳过] 未找到 ImageMagick; PyInstaller 将使用默认图标" -ForegroundColor DarkGray
    }
}

# ------------------------------------------------------------------
# 5) PyInstaller 构建
# ------------------------------------------------------------------
Write-Host "==> PyInstaller 构建..." -ForegroundColor Yellow
& $pyExe -m PyInstaller $SPEC --noconfirm --distpath $DIST --workpath (Join-Path $DIST "build_win")
if ($LASTEXITCODE -ne 0) { Write-Host "!! PyInstaller 构建失败" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------------
# 6) 结果
# ------------------------------------------------------------------
$outDir = Join-Path $DIST "RobotBlockly"
Write-Host ""
Write-Host "==> 构建完成: $outDir" -ForegroundColor Green
Write-Host "==> 可执行文件: $(Join-Path $outDir 'RobotBlockly.exe')"
Write-Host ""
Write-Host "==> 如需制作安装程序 (NSIS):"
Write-Host "    makensis packaging\installer_win.nsi"
