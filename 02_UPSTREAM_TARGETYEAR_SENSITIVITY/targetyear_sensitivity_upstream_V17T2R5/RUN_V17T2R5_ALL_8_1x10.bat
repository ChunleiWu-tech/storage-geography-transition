@echo off
setlocal
cd /d "%~dp0"
call "%~dp0RUN_CURRENT_RESUME_ALL_8_1x10.bat"
exit /b %errorlevel%
