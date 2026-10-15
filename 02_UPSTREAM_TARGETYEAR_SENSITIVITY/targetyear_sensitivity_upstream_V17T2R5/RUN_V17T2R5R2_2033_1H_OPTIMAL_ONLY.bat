@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"

rem R2 exact variable projection; preserve and do not rerun the other seven cases.
set "V17_ECONOMIC_BARRIER_TIME_LIMIT_SECONDS=86400"
set "V17_ECONOMIC_BAR_ITER_LIMIT=50000"
set "V17_SOLVER_THREADS=10"

%V17T2R5_PYTHON% tools\run_targetyear_batch.py ^
  --scenario TY2033_CHRONO_1H_OPTIMAL ^
  --route projected ^
  --skip-prepare ^
  --force-rerun ^
  --julia "%V17T2R5_JULIA%"

set "V17T2R5R2_RC=%ERRORLEVEL%"
echo.
echo V17T2R5R2_RETURN_CODE=%V17T2R5R2_RC%
exit /b %V17T2R5R2_RC%
