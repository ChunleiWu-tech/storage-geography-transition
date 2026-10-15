@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"

rem R5 is isolated to TY2033_CHRONO_1H_OPTIMAL.
rem It keeps the R3 exact reduction and the original scientific model/tolerances.
rem A strict paired-observed optimum supplies complete primal/dual starts; a
rem dual-supported bridge creates a basis, then primal-simplex objective
rem continuation restores the original objective exactly before publication.
set "V17T2R5R4_SEED_TIME_LIMIT_SECONDS=43200"
set "V17T2R5R4_SEED_BAR_ITER_LIMIT=100000"
set "V17T2R5R5_BRIDGE_TIME_LIMIT_SECONDS=21600"
set "V17T2R5R5_STAGE_TIME_LIMIT_SECONDS=21600"
set "V17T2R5R5_FINAL_TIME_LIMIT_SECONDS=86400"
set "V17_SOLVER_THREADS=10"

%V17T2R5_PYTHON% tools\check_v17t2r5r5_continuation.py
if errorlevel 1 exit /b %ERRORLEVEL%

%V17T2R5_PYTHON% tools\run_targetyear_batch.py ^
  --scenario TY2033_CHRONO_1H_OPTIMAL ^
  --route r5_continuation ^
  --skip-prepare ^
  --force-rerun ^
  --julia "%V17T2R5_JULIA%"

set "V17T2R5R5_RC=%ERRORLEVEL%"
echo.
echo V17T2R5R5_RETURN_CODE=%V17T2R5R5_RC%
exit /b %V17T2R5R5_RC%
