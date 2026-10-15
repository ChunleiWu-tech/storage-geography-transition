@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

rem HF3 canonical policy: one uninterrupted primary Barrier solve at a time.
rem 129600 s equals the former 43200 s primary + 86400 s fallback budget.
set "V17_SOLVER_THREADS=10"
set "V17T2R6_MAX_PARALLEL=1"
set "V17T2R6_8760_PRIMARY_TIME_LIMIT_SECONDS=129600"
set "V17T2R6_8760_PRIMARY_BAR_ITER_LIMIT=100000"

rem Fail closed if another Julia job would contaminate the timing/resource budget.
powershell -NoProfile -Command "if (Get-Process julia -ErrorAction SilentlyContinue) { Write-Host 'ERROR: another Julia process is running. Finish or stop all other Julia jobs before HF3.'; exit 2 }"
if errorlevel 1 exit /b 2

call "%~dp0CHECK_V17T2R6R8_HF3_8760.bat"
if errorlevel 1 exit /b 1

echo.
echo === V17T2R6R8-HF3 FULL8760: 4 cases, serial, 10 threads, 36 h maximum per case ===
echo Route: unchanged scaled Barrier without crossover; no homogeneous restart.
echo Existing official outputs are preserved until a new strict-success result is promoted.
echo.
%V17T2R6_PYTHON% "tools\run_targetyear_batch.py" --pair ALL --route hf3 --skip-prepare --continue-after-failure --max-parallel 1 --julia "%V17T2R6_JULIA%"
if errorlevel 1 exit /b 1
call "%~dp0FINALIZE_V17T2R6_8760_RESULTS.bat"
exit /b %errorlevel%
