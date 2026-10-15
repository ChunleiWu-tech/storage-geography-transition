@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

rem R9-HF4 is resume-safe: no clean, no force-rerun, one scenario at a time.
rem Existing strict __main outputs are validated and retained without re-solving.
set "V17_SOLVER_THREADS=10"
set "V17T2R6_MAX_PARALLEL=1"
set "V17T2R6_8760_PRIMARY_TIME_LIMIT_SECONDS=129600"
set "V17T2R6_8760_PRIMARY_BAR_ITER_LIMIT=100000"
set "V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS=129600"
set "V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS=21600"
set "V17T2R6R9_HF4_STAGE_TIME_LIMIT_SECONDS=21600"
set "V17T2R6R9_HF4_FINAL_TIME_LIMIT_SECONDS=129600"

call "%~dp0CHECK_V17T2R6R9_HF4_8760.bat"
if errorlevel 1 exit /b 1

echo.
echo === V17T2R6R9-HF4 FULL8760 resume-safe serial completion ===
echo OBSERVED cases: retain strict outputs or use the unchanged HF3 route.
echo OPTIMAL cases: exact paired-observed primal/dual supported objective continuation.
echo No scientific input, constraint, final bound, final objective, or release tolerance is changed.
echo.

set "HF4_FAILURE=0"

%V17T2R6_PYTHON% "tools\run_targetyear_batch.py" --scenario TY2033_FULL8760_OBSERVED --route hf3 --skip-prepare --max-parallel 1 --julia "%V17T2R6_JULIA%"
if errorlevel 1 set "HF4_FAILURE=1"

%V17T2R6_PYTHON% "tools\run_targetyear_batch.py" --scenario TY2033_FULL8760_OPTIMAL --route hf4_continuation --skip-prepare --max-parallel 1 --julia "%V17T2R6_JULIA%"
if errorlevel 1 set "HF4_FAILURE=1"

%V17T2R6_PYTHON% "tools\run_targetyear_batch.py" --scenario TY2033_FULL8760_LDES_OBSERVED --route hf3 --skip-prepare --max-parallel 1 --julia "%V17T2R6_JULIA%"
if errorlevel 1 set "HF4_FAILURE=1"

%V17T2R6_PYTHON% "tools\run_targetyear_batch.py" --scenario TY2033_FULL8760_LDES_OPTIMAL --route hf4_continuation --skip-prepare --max-parallel 1 --julia "%V17T2R6_JULIA%"
if errorlevel 1 set "HF4_FAILURE=1"

if not "%HF4_FAILURE%"=="0" (
    echo.
    echo One or more remaining FULL8760 cases did not pass the strict release gate.
    echo Existing strict results were retained. See batch_logs and sensitivity_outputs\_attempts.
    exit /b 1
)

call "%~dp0FINALIZE_V17T2R6_8760_RESULTS.bat"
exit /b %errorlevel%
