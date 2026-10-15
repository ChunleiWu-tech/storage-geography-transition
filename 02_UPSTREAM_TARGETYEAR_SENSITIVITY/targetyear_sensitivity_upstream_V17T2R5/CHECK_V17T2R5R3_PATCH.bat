@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"
set "PYTHONDONTWRITEBYTECODE=1"

%V17T2R5_PYTHON% tools\check_v17t2r5r3_projection.py
if errorlevel 1 exit /b %ERRORLEVEL%

%V17T2R5_PYTHON% tools\audit_julia_lexical_v17t2r5.py
if errorlevel 1 exit /b %ERRORLEVEL%

%V17T2R5_PYTHON% tools\check_v17t2r5_package.py
exit /b %ERRORLEVEL%
