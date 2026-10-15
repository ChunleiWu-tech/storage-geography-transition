@echo off
setlocal
cd /d "%~dp0"
call V20_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
set "PYTHONDONTWRITEBYTECODE=1"
%V17_PYTHON% "tools\verify_v20_manifest.py" --strict-set
exit /b %ERRORLEVEL%
