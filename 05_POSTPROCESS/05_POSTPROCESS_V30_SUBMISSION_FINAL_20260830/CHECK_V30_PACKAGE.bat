@echo off
setlocal
cd /d "%~dp0"
py -3.11 CHECK_V30_PACKAGE.py --release-clean
if errorlevel 1 py -3 CHECK_V30_PACKAGE.py --release-clean
exit /b %errorlevel%
