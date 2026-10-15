@echo off
setlocal
cd /d "%~dp0"
call V20_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
set "V17_SOLVER_THREADS=10"
call CHECK_V20_STATIC.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\run_v20_layer_b16.py"
exit /b %errorlevel%
