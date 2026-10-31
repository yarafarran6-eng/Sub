@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Downloading the latest version...
if exist "%TEMP%\sub_update" rmdir /s /q "%TEMP%\sub_update"
mkdir "%TEMP%\sub_update"
curl.exe -L -f -s -o "%TEMP%\sub_update.zip" "https://github.com/yarafarran6-eng/Sub/archive/refs/heads/main.zip"
if errorlevel 1 goto fail
tar -xf "%TEMP%\sub_update.zip" -C "%TEMP%\sub_update"
if errorlevel 1 goto fail
robocopy "%TEMP%\sub_update\Sub-main" "%~dp0." /E /XD data /XF update.bat /NFL /NDL /NJH /NJS
if errorlevel 8 goto fail
echo.
echo Updated. Your data folder was not touched. Now run start.bat
pause
exit /b 0

:fail
echo.
echo Update failed. Check your internet connection and try again.
pause
exit /b 1
