@echo off
setlocal EnableExtensions
cd /d "%~dp0"
py -3.11 -c "import sys" >nul 2>&1
if errorlevel 1 (
  python "tools\check_clean_package_manifest.py"
) else (
  py -3.11 "tools\check_clean_package_manifest.py"
)
exit /b %errorlevel%
