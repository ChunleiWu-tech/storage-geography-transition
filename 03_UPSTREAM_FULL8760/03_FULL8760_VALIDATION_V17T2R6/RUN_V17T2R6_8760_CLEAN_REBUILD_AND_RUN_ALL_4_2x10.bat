@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
set "V17_SOLVER_THREADS=10"
set "V17T2R6_MAX_PARALLEL=2"
call "%~dp0CHECK_V17T2R6R7_HF2P1_PATCH.bat"
if errorlevel 1 exit /b 1
echo === HF2P2 CLEAN REBUILD: regenerate and rerun all four full-8760 cases ===
rem Delete only generated full-8760 cases/results/logs/diagnostics. Frozen templates and raw sources stay immutable.
if exist "sensitivity_cases" rmdir /s /q "sensitivity_cases"
if exist "sensitivity_outputs" rmdir /s /q "sensitivity_outputs"
if exist "batch_logs" rmdir /s /q "batch_logs"
if exist "failed_diagnostics" rmdir /s /q "failed_diagnostics"
if exist "storage_runner\prepared_8760_cases_index.csv" del /q "storage_runner\prepared_8760_cases_index.csv"
mkdir sensitivity_cases >nul 2>nul
call "%~dp0PREPARE_V17T2R6_8760_CASES.bat"
if errorlevel 1 exit /b 1
call "%~dp0RUN_V17T2R6_8760_ALL_4_2x10.bat"
exit /b %errorlevel%
