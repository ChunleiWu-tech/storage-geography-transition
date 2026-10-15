@echo off
cd /d "%~dp0"
python render_ees.py all
if errorlevel 1 exit /b 1
python verify_tables.py
pause
