@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"

rem R3 is isolated to TY2033_CHRONO_1H_OPTIMAL. It preserves prepared inputs,
rem the promoted outputs of the other seven cases and every publication gate.
set "V17_ECONOMIC_BARRIER_TIME_LIMIT_SECONDS=86400"
set "V17_ECONOMIC_FALLBACK_TIME_LIMIT_SECONDS=86400"
set "V17_ECONOMIC_BAR_ITER_LIMIT=100000"
set "V17_SOLVER_THREADS=10"

%V17T2R5_PYTHON% tools\check_v17t2r5r3_projection.py
if errorlevel 1 exit /b %ERRORLEVEL%

%V17T2R5_PYTHON% tools\run_targetyear_batch.py ^
  --scenario TY2033_CHRONO_1H_OPTIMAL ^
  --route r3_reduced ^
  --skip-prepare ^
  --force-rerun ^
  --julia "%V17T2R5_JULIA%"

set "V17T2R5R3_RC=%ERRORLEVEL%"
echo.
echo V17T2R5R3_RETURN_CODE=%V17T2R5R3_RC%
exit /b %V17T2R5R3_RC%
