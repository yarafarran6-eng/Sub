@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Downloading the latest version...
powershell -NoProfile -Command "$ErrorActionPreference=Stop; Invoke-WebRequest -Uri https://github.com/yarafarran6-eng/Sub/archive/refs/heads/main.zip -OutFile \"$env:TEMP\sub_update.zip\"; if (Test-Path \"$env:TEMP\sub_update\") { Remove-Item -Recurse -Force \"$env:TEMP\sub_update\" }; Expand-Archive -Path \"$env:TEMP\sub_update.zip\" -DestinationPath \"$env:TEMP\sub_update\" -Force"
if errorlevel 1 (
  echo Download failed. Check your internet and try again.
  pause
  exit /b 1
)
robocopy "%TEMP%\sub_update\Sub-main" "%~dp0." /E /XD data /XF update.bat /NFL /NDL /NJH /NJS
echo.
echo Updated. Your data folder was not touched. Now run start.bat
pause
