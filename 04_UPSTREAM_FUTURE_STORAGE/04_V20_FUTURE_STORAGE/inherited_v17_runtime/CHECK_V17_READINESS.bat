@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\check_v17_run_readiness.py"
if errorlevel 1 exit /b 1
echo V17 fast run-readiness validation PASSED.
endlocal
