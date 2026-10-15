@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
%V17T2R6_PYTHON% "tools\audit_targetyear_pair_identity.py" >nul
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_julia_8760_static.py" >nul
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_v17t2r6r9_hf4_continuation.py" >nul
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_v17t2r6r9_hf4p1_parallel.py"
exit /b %errorlevel%
