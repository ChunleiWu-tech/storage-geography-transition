@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

rem HF4P2: three distinct remaining cases, each with exactly 15 Gurobi threads.
rem Scenario leases prevent duplicate work if an older serial coordinator is still open.
rem No clean operation and no force-rerun: promoted strict results are retained.
set "V17_SOLVER_THREADS=15"
set "V17T2R6_8760_PRIMARY_TIME_LIMIT_SECONDS=129600"
set "V17T2R6_8760_PRIMARY_BAR_ITER_LIMIT=100000"
set "V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS=129600"
set "V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS=21600"
set "V17T2R6R9_HF4_STAGE_TIME_LIMIT_SECONDS=21600"
set "V17T2R6R9_HF4_FINAL_TIME_LIMIT_SECONDS=129600"
set "V17T2R6_SCENARIO_LOCK_WAIT_SECONDS=604800"
set "V17T2R6_SCENARIO_LOCK_POLL_SECONDS=20"

call "%~dp0CHECK_V17T2R6R9_HF4P2_8760_3X15.bat"
if errorlevel 1 exit /b 1

echo.
echo === HF4P2 scope-safe remaining full-8760 cases: 3 x 15 threads ===
echo TY2033_FULL8760_OPTIMAL: HF4 exact continuation
echo TY2033_FULL8760_LDES_OBSERVED: unchanged HF3 exact projected route
echo TY2033_FULL8760_LDES_OPTIMAL: HF4 exact continuation
echo Strict existing outputs are skipped and retained; no scientific input is modified.
echo.
%V17T2R6_PYTHON% "tools\run_hf4p2_remaining_three_parallel.py" --julia "%V17T2R6_JULIA%"
if errorlevel 1 exit /b 1

call "%~dp0FINALIZE_V17T2R6_8760_RESULTS.bat"
exit /b %errorlevel%
