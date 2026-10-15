@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"
if errorlevel 1 exit /b 1
rem Current publication solver budgets for the 2033 1 h robust ladder.
set "V17_ECONOMIC_BARRIER_TIME_LIMIT_SECONDS=43200"
set "V17_ECONOMIC_BAR_ITER_LIMIT=100000"
set "V17_ECONOMIC_FALLBACK_TIME_LIMIT_SECONDS=86400"
set "V17T1_HARD_LP_TIME_LIMIT_SECONDS=86400"
call "%~dp0CHECK_V17T2R5_PACKAGE.bat"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R5_RUNTIME.bat"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_PUBLICATION_SOURCE_GATE.bat" --stage cases
if errorlevel 1 exit /b 1

rem Same pre-specified numerical ladder is offered to both 1 h pair members.
rem A member stops immediately after the first strict solver-native OPTIMAL result.
%V17T2R5_PYTHON% "tools\run_targetyear_batch.py" --pair TY2033_CHRONO_1H --route one_hour_robust --skip-prepare --force-rerun --continue-after-failure --julia "%V17T2R5_JULIA%"
if errorlevel 1 exit /b 1

echo V17T2R5 current 2033 1H pair PASSED strict gates.
endlocal
exit /b 0
