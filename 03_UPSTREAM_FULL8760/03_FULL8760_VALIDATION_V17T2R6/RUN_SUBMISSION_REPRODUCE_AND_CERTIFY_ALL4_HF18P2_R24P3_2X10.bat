@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

call "%~dp0CHECK_CLEAN_PACKAGE_MANIFEST.bat"
if errorlevel 1 exit /b 1
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
if errorlevel 1 exit /b 1

if not defined V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT set "V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT=%~dp0..\targetyear_sensitivity_upstream_V17T2R5\sensitivity_outputs"
if not exist "%V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT%\TY2033_CHRONO_OBSERVED__main\solve_status.csv" (
  echo ERROR: complete the adjacent strict eight-case sensitivity package first.
  echo Missing source root: %V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT%
  exit /b 1
)

rem Destructive only to generated state in this fresh extraction; scientific inputs stay read-only.
for %%D in (sensitivity_cases sensitivity_outputs batch_logs failed_diagnostics robustness_distance_8760_outputs robustness_distance_8760_quality_recovery_outputs batch_logs_robustness_distance batch_logs_robustness_distance_quality_recovery run_locks_hf18p2_robustness run_locks_hf18p2_quality_recovery) do (
  if exist "%%D" rmdir /s /q "%%D"
)
if exist "storage_runner\prepared_8760_cases_index.csv" del /q "storage_runner\prepared_8760_cases_index.csv"

call "%~dp0PREPARE_V17T2R6_8760_CASES.bat"
if errorlevel 1 exit /b 1
set "V17_SOLVER_THREADS=10"
set "V17T2R6_MAX_PARALLEL=2"
set "V17_STAGE1_CERT_STRICT_REL_TOL=1.0e-6"
set "V17_STAGE1_CERT_ACCEPT_REL_TOL=1.0e-5"
if not defined V17T2R6R24_HF18P2_TIME_LIMIT_SECONDS set "V17T2R6R24_HF18P2_TIME_LIMIT_SECONDS=43200"

call "%~dp0CHECK_V17T2R6R24P3_HF18P2_POSTSOLVE_RECOVERY.bat"
if errorlevel 1 exit /b 1

echo === PHASE 1/3: reproduce two OPTIMAL-source robustness certificates ===
%V17T2R6_PYTHON% "%~dp0tools\run_hf18p2_prior_optimal_two_parallel.py" --julia "%V17T2R6_JULIA%"
if errorlevel 1 exit /b 1

echo === PHASE 2/3: solve and quality-audit two OBSERVED cases ===
%V17T2R6_PYTHON% "%~dp0tools\run_hf18p2_quality_recovery_two_parallel.py" --julia "%V17T2R6_JULIA%"
set "R24P2_RC=%errorlevel%"
if "%R24P2_RC%"=="0" goto :all_complete

echo === PHASE 3/3: fail-closed postsolve recovery for the sole scale-only complementarity failure ===
%V17T2R6_PYTHON% "%~dp0tools\run_hf18p2_r24p3_postsolve_complementarity_recovery.py"
if errorlevel 1 exit /b 1

:all_complete
echo SUBMISSION FULL8760 CERTIFICATE SET: ALL 4 COMPLETED.
echo Read robustness_distance_8760_quality_recovery_outputs\V17T2R6R24P3_HF18P2_COMBINED_ALL4_final_summary.json
exit /b 0
