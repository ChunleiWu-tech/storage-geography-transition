@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"

rem R4 is isolated to TY2033_CHRONO_1H_OPTIMAL. Phase A fixes only the
rem 32 paired-observed legacy allocation coordinates and requires strict OPTIMAL.
rem Phase B restores every original OPTIMAL bound and solves the full case from
rem the complete feasible PStart. Other seven results are retained and untouched.
set "V17T2R5R4_SEED_TIME_LIMIT_SECONDS=43200"
set "V17T2R5R4_SEED_BAR_ITER_LIMIT=100000"
set "V17T2R5R4_FINAL_TIME_LIMIT_SECONDS=86400"
set "V17_SOLVER_THREADS=10"

%V17T2R5_PYTHON% tools\check_v17t2r5r4_continuation.py
if errorlevel 1 exit /b %ERRORLEVEL%

%V17T2R5_PYTHON% tools\run_targetyear_batch.py ^
  --scenario TY2033_CHRONO_1H_OPTIMAL ^
  --route r4_continuation ^
  --skip-prepare ^
  --force-rerun ^
  --julia "%V17T2R5_JULIA%"

set "V17T2R5R4_RC=%ERRORLEVEL%"
echo.
echo V17T2R5R4_RETURN_CODE=%V17T2R5R4_RC%
exit /b %V17T2R5R4_RC%
