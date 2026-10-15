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

rem Existing strict official outputs are revalidated and skipped.
%V17T2R5_PYTHON% "tools\run_targetyear_batch.py" --pair TY2028_CHRONO --route auto --skip-prepare --julia "%V17T2R5_JULIA%"
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\run_targetyear_batch.py" --pair TY2033_CHRONO --route auto --skip-prepare --julia "%V17T2R5_JULIA%"
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\run_targetyear_batch.py" --pair TY2033_CHRONO_LDES --route auto --skip-prepare --julia "%V17T2R5_JULIA%"
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\run_targetyear_batch.py" --pair TY2033_CHRONO_1H --route one_hour_robust --skip-prepare --continue-after-failure --julia "%V17T2R5_JULIA%"
if errorlevel 1 exit /b 1

%V17T2R5_PYTHON% "tools\write_publication_result_lineage.py" --kind sensitivity
if errorlevel 1 exit /b 1
call "%~dp0CHECK_PUBLICATION_SOURCE_GATE.bat" --stage results
if errorlevel 1 exit /b 1
call "%~dp0BUILD_V17T2R5_SUMMARY.bat"
if errorlevel 1 exit /b 1

echo.
echo CURRENT STANDALONE SENSITIVITY RESUME PASSED: 8/8 strict scenarios.
endlocal
exit /b 0
