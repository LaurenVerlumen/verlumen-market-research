@echo off
echo Starting Verlumen Market Research Tool...
cd /d "%~dp0"
call venv\Scripts\activate
python app.py
pause
