@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
set "V17_SOLVER_THREADS=10"
set "V17T2R6_MAX_PARALLEL=2"
call "%~dp0CHECK_V17T2R6_8760_PREFLIGHT.bat"
if errorlevel 1 exit /b 1
rem Run the two CORE identification-pair members simultaneously, 10 threads each.
%V17T2R6_PYTHON% "tools\run_targetyear_batch.py" --pair TY2033_FULL8760 --route auto --skip-prepare --max-parallel 2 --julia "%V17T2R6_JULIA%"
exit /b %errorlevel%
