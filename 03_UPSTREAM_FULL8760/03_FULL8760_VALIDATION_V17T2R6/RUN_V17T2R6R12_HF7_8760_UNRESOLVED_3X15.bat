@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

rem Three scientifically unchanged, process-isolated HF7 target solves.
rem Existing strict outputs are skipped; old logs and attempts are retained.
rem Active old scenario leases are waited on and are never removed here.
set "V17_SOLVER_THREADS=15"
set "V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS=129600"
set "V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS=86400"
set "V17T2R6R9_HF4_STAGE_TIME_LIMIT_SECONDS=43200"
set "V17T2R6R9_HF4_FINAL_TIME_LIMIT_SECONDS=129600"
set "V17T2R6_SCENARIO_LOCK_WAIT_SECONDS=604800"
set "V17T2R6_SCENARIO_LOCK_POLL_SECONDS=20"

call "%~dp0CHECK_V17T2R6R12_HF7_8760.bat"
if errorlevel 1 exit /b 1

echo.
echo === R12-HF7: three unresolved full-8760 cases, 3 independent x 15 threads ===
echo Each case uses its own Julia process, scenario lease, log and __07 attempt output.
echo No scientific input, final bound, final objective, constraint or tolerance is relaxed.
echo.
%V17T2R6_PYTHON% "tools\run_hf7_unresolved_three_parallel.py" --julia "%V17T2R6_JULIA%"
exit /b %errorlevel%
