@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

rem HF6 changes only the numerical bridge for the two OPTIMAL full-8760 cases.
rem Do not run it while an old HF5 worker still owns either optimized scenario.
rem It never touches either OBSERVED case, and it never deletes a lease or output.
set "V17_SOLVER_THREADS=15"
set "V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS=129600"
set "V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS=43200"
set "V17T2R6R9_HF4_STAGE_TIME_LIMIT_SECONDS=21600"
set "V17T2R6R9_HF4_FINAL_TIME_LIMIT_SECONDS=129600"
set "V17T2R6_SCENARIO_LOCK_WAIT_SECONDS=604800"
set "V17T2R6_SCENARIO_LOCK_POLL_SECONDS=20"

call "%~dp0CHECK_V17T2R6R11_HF6_8760_OPTIMIZED_PAIR.bat"
if errorlevel 1 exit /b 1

echo.
echo === R11-HF6: two optimized full-8760 cases, at most 2 x 15 solver threads ===
echo This starts only TY2033_FULL8760_OPTIMAL and TY2033_FULL8760_LDES_OPTIMAL.
echo TY2033_FULL8760_OBSERVED and TY2033_FULL8760_LDES_OBSERVED are not altered.
echo.
%V17T2R6_PYTHON% "tools\run_hf6_optimized_pair_parallel.py" --julia "%V17T2R6_JULIA%"
exit /b %errorlevel%
