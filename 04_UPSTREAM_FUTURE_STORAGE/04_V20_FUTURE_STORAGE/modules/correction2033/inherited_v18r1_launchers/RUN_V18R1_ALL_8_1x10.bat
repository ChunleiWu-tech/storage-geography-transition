@echo off
setlocal
cd /d "%~dp0"
call "%~dp0RUN_V18R1_PRIMARY_4_1x10.bat"
if errorlevel 1 exit /b %errorlevel%
call "%~dp0RUN_V18R1_ROBUSTNESS_4_1x10.bat"
exit /b %errorlevel%
