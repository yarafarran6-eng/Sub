@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -r requirements.txt
set HOST=0.0.0.0
start "" http://127.0.0.1:7860
python app.py
pause
