@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

rem Automatic HF5 recovery for both optimized members only. The ordinary
rem OPTIMAL case starts immediately if its lease is free. The LDES OPTIMAL
rem task waits safely for any live pre-patch worker; it never removes a lock.
rem Neither OBSERVED case is launched, altered, cleaned, or finalized here.
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
echo === R10-HF5: both optimized full-8760 cases, at most 2 new x 15 threads ===
echo TY2033_FULL8760_OPTIMAL starts now when its lease is free.
echo TY2033_FULL8760_LDES_OPTIMAL waits for a live old lease, then starts HF5 automatically.
echo TY2033_FULL8760_LDES_OBSERVED remains on its currently running HF3 route.
echo.
%V17T2R6_PYTHON% "tools\run_hf5_optimized_pair_auto_resume.py" --julia "%V17T2R6_JULIA%"
exit /b %errorlevel%
