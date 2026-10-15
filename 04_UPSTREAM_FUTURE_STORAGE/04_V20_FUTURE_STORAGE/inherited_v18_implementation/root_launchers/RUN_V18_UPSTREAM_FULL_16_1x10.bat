@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
call CHECK_V17_RUNTIME.bat
if errorlevel 1 exit /b 1
call RUN_V18_PREPARE_ALL_16.bat
if errorlevel 1 exit /b 1
if exist "batch_logs" rmdir /s /q "batch_logs"
if exist "outputs" rmdir /s /q "outputs"
if exist "failed_diagnostics" rmdir /s /q "failed_diagnostics"
if exist "storage_runner\storage_batch_run_summary.csv" del /q "storage_runner\storage_batch_run_summary.csv"
%V17_PYTHON% "tools\run_v18_full16.py" --julia "%JULIA_EXE%"
if errorlevel 1 exit /b 1
echo.
echo V18 MAIN UPSTREAM SOLVER-CERTIFIED PASS: 16/16 STRICT SCENARIOS.
endlocal
exit /b 0
