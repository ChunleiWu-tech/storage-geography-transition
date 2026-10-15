@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% -c "import sys; print(sys.executable); print(sys.version)"
if errorlevel 1 exit /b 1
echo V17 Python runtime PASSED.
endlocal
