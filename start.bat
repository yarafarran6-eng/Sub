@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "app.py" (
  echo.
  echo Cannot find app.py next to start.bat.
  echo Do NOT move start.bat alone to the desktop: keep it inside the site folder.
  echo To put the site on your desktop, run create_shortcut.bat from the site folder.
  echo.
  pause
  exit /b 1
)
python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo Python was not found. Install Python 3.10 or newer from python.org
  echo and tick "Add Python to PATH" in the first screen, then run this again.
  echo.
  pause
  exit /b 1
)
python -m pip install -r requirements.txt
set HOST=0.0.0.0
set OPEN_BROWSER=1
python app.py
pause
