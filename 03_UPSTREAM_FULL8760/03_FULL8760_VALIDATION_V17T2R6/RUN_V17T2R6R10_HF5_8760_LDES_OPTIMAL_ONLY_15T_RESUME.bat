@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

rem R10-HF5 companion: use only after the currently live legacy HF4 LDES
rem OPTIMAL worker has released its scenario lease.  No result is removed,
rem forced, finalized, or promoted unless every existing strict gate passes.
set "V17_SOLVER_THREADS=15"
set "V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS=129600"
set "V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS=21600"
set "V17T2R6R9_HF4_STAGE_TIME_LIMIT_SECONDS=21600"
set "V17T2R6R9_HF4_FINAL_TIME_LIMIT_SECONDS=129600"
set "V17T2R6_SCENARIO_LOCK_WAIT_SECONDS=604800"
set "V17T2R6_SCENARIO_LOCK_POLL_SECONDS=20"

call "%~dp0CHECK_V17T2R6R10_HF5_8760_OPTIMAL_ONLY.bat"
if errorlevel 1 exit /b 1

echo.
echo === R10-HF5: TY2033_FULL8760_LDES_OPTIMAL only, 15 Gurobi threads ===
echo Start this only after the pre-patch LDES OPTIMAL worker finishes or is safely stopped.
echo The new HF5 attempt is isolated from the old HF4 log and output directory.
echo.
%V17T2R6_PYTHON% "tools\run_targetyear_batch.py" --scenario TY2033_FULL8760_LDES_OPTIMAL --route hf5_simplex_bridge --skip-prepare --max-parallel 1 --julia "%V17T2R6_JULIA%"
exit /b %errorlevel%
