@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

rem Safe companion for a currently running FULL8760_OPTIMAL serial solve.
rem Two distinct scenario leases prevent duplicate work when the original
rem serial launcher later reaches the same LDES cases.
set "V17_SOLVER_THREADS=10"
set "V17T2R6_MAX_PARALLEL=2"
set "V17T2R6_8760_PRIMARY_TIME_LIMIT_SECONDS=129600"
set "V17T2R6_8760_PRIMARY_BAR_ITER_LIMIT=100000"
set "V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS=129600"
set "V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS=21600"
set "V17T2R6R9_HF4_STAGE_TIME_LIMIT_SECONDS=21600"
set "V17T2R6R9_HF4_FINAL_TIME_LIMIT_SECONDS=129600"
set "V17T2R6_SCENARIO_LOCK_WAIT_SECONDS=604800"
set "V17T2R6_SCENARIO_LOCK_POLL_SECONDS=20"

call "%~dp0CHECK_V17T2R6R9_HF4P1_PARALLEL.bat"
if errorlevel 1 exit /b 1

echo.
echo === HF4P1 safe parallel companion: remaining two LDES cases, 2 x 10 threads ===
echo Keep the original FULL8760_OPTIMAL terminal running.
echo Per-scenario leases prevent the original serial launcher from duplicating these cases.
echo.
%V17T2R6_PYTHON% "tools\run_hf4_remaining_ldes_parallel.py" --julia "%V17T2R6_JULIA%"
exit /b %errorlevel%
