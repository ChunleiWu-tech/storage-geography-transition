@echo off
setlocal
cd /d "%~dp0"
call V17T2R5_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
call CHECK_V17T2R5_RUNTIME.bat
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --stage cases
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\run_targetyear_batch.py" --pair TY2028_CHRONO --route auto --skip-prepare --force-rerun --julia "%V17T2R5_JULIA%"
exit /b %errorlevel%
