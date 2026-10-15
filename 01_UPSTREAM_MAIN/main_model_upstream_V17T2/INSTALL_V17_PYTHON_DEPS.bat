@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% -m pip install -r requirements_v17.txt
if errorlevel 1 exit /b 1
echo V17 Python dependencies installed.
endlocal
