@echo off
setlocal
cd /d "%~dp0"
call V20_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
call CHECK_V20_STATIC.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\build_v20_result_tables.py"
exit /b %errorlevel%
