@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
set "V17T2R6_MAX_PARALLEL=1"
%V17T2R6_PYTHON% "tools\run_targetyear_batch.py" --scenario TY2033_FULL8760_OBSERVED --route auto --skip-prepare --force-rerun --max-parallel 1 --julia "%V17T2R6_JULIA%"
exit /b %errorlevel%
