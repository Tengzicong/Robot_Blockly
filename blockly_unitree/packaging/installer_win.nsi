; ============================================================================
; Robot Blockly  Windows NSIS 安装器
;
; 用法 (先运行 packaging/build_win.ps1 生成 dist/RobotBlockly/):
;     makensis packaging/installer_win.nsi
;
; 产物: dist/RobotBlockly_Setup_<VERSION>.exe
; 特性: 免管理员安装到 %LOCALAPPDATA%, 开始菜单+桌面快捷方式, 卸载器
; ============================================================================

!include "MUI2.nsh"
!include "FileFunc.nsh"

; ----------------------------- 基础信息 --------------------------------
Name "Robot Blockly"
!define APP_NAME "Robot Blockly"
!define APP_ID "RobotBlockly"
!define VERSION "0.1.0"
!define ROOT_DIR "..\dist\RobotBlockly"
OutFile "..\dist\RobotBlockly_Setup_${VERSION}.exe"
Unicode True
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\${APP_ID}"

; ----------------------------- MUI 界面 --------------------------------
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; ----------------------------- 安装段 --------------------------------
Section "Install"
  SetOutPath "$INSTDIR"
  ; 拷贝整个单目录 (exe + dll + resources)
  File /r "${ROOT_DIR}\*.*"

  ; 开始菜单快捷方式
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\RobotBlockly.exe"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\卸载 ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"

  ; 桌面快捷方式
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\RobotBlockly.exe"

  ; 卸载信息
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "Publisher" "ERROR-CORE Team"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "DisplayIcon" "$INSTDIR\RobotBlockly.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "EstimatedSize" "$0"
SectionEnd

; ----------------------------- 卸载段 --------------------------------
Section "Uninstall"
  ; 关闭运行中的程序
  nsExec::ExecToLog 'taskkill /F /IM "RobotBlockly.exe"'

  ; 删除快捷方式
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\卸载 ${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"

  ; 删除安装目录 (保留用户数据目录 %APPDATA%\RobotBlockly)
  RMDir /r "$INSTDIR"

  ; 删除卸载注册表
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"
SectionEnd
