@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

rem R10-HF5: rerun only the failed non-LDES OPTIMAL case.  Existing promoted
rem outputs, failed HF4 evidence, and the two live LDES coordinators are not
rem deleted, forced, finalized, or otherwise modified by this launcher.
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
echo === R10-HF5: TY2033_FULL8760_OPTIMAL only, 15 Gurobi threads ===
echo The final model is unchanged.  The temporary HF4 crossover bridge is replaced
echo by a complete PStart/DStart primal-simplex basis bridge with Crossover=0.
echo Existing logs and output attempts remain under their original HF4 locations.
echo.
%V17T2R6_PYTHON% "tools\run_targetyear_batch.py" --scenario TY2033_FULL8760_OPTIMAL --route hf5_simplex_bridge --skip-prepare --max-parallel 1 --julia "%V17T2R6_JULIA%"
exit /b %errorlevel%
