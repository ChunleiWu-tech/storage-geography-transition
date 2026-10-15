@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"
set "PYTHONDONTWRITEBYTECODE=1"

%V17T2R5_PYTHON% tools\check_v17t2r5r2_projection.py
if errorlevel 1 exit /b %ERRORLEVEL%

%V17T2R5_PYTHON% tools\check_v17t2r5_package.py
exit /b %ERRORLEVEL%
