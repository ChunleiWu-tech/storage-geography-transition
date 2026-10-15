@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
%V17T2R6_PYTHON% "tools\audit_targetyear_pair_identity.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_julia_8760_static.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_v17t2r6r9_hf4_continuation.py"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R6_8760_RUNTIME.bat"
exit /b %errorlevel%
