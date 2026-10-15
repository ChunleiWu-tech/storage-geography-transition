@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0CHECK_CLEAN_PACKAGE_MANIFEST.bat"
if errorlevel 1 exit /b 1
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
if errorlevel 1 exit /b 1

if exist "run_locks\*.lock" (
  echo ERROR: this directory contains scenario leases. Use a fresh extraction or finish the existing coordinator.
  exit /b 9
)

rem This is an explicit clean-run launcher; remove generated state in this package only.
if exist "sensitivity_cases" rmdir /s /q "sensitivity_cases"
if exist "sensitivity_outputs" rmdir /s /q "sensitivity_outputs"
if exist "batch_logs" rmdir /s /q "batch_logs"
if exist "failed_diagnostics" rmdir /s /q "failed_diagnostics"
if exist "storage_runner\prepared_8760_cases_index.csv" del /q "storage_runner\prepared_8760_cases_index.csv"

call "%~dp0PREPARE_V17T2R6_8760_CASES.bat"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R6R12_HF7_8760.bat"
if errorlevel 1 exit /b 1

echo === 1/4 TY2033_FULL8760_OBSERVED: verified HF3 ===
set "V17_SOLVER_THREADS=15"
set "V17T2R6_MAX_PARALLEL=1"
%V17T2R6_PYTHON% "tools\run_targetyear_batch.py" --scenario TY2033_FULL8760_OBSERVED --route hf3 --skip-prepare --force-rerun --max-parallel 1 --julia "%V17T2R6_JULIA%"
if errorlevel 1 exit /b 1

echo === 2-4/4 unresolved cases: HF7, 3 independent Julia x 15 threads ===
call "%~dp0RUN_V17T2R6R12_HF7_8760_UNRESOLVED_3X15.bat"
if errorlevel 1 exit /b 1

call "%~dp0FINALIZE_V17T2R6_8760_RESULTS.bat"
if errorlevel 1 exit /b 1
echo FULL8760 PASSED: 4/4 STRICT CASES.
exit /b 0
