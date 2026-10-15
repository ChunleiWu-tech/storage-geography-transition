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

rem Delete generated target-year state only. Frozen science/model/source data remain immutable.
if exist "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV" rmdir /s /q "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV"
if exist "sensitivity_cases" rmdir /s /q "sensitivity_cases"
if exist "sensitivity_outputs" rmdir /s /q "sensitivity_outputs"
if exist "batch_logs" rmdir /s /q "batch_logs"
if exist "failed_diagnostics" rmdir /s /q "failed_diagnostics"
if exist "storage_runner\prepared_targetyear_cases_index.csv" del /q "storage_runner\prepared_targetyear_cases_index.csv"
if exist "audits\PUBLICATION_RESULT_LINEAGE.json" del /q "audits\PUBLICATION_RESULT_LINEAGE.json"
mkdir sensitivity_cases >nul 2>nul
mkdir sensitivity_outputs >nul 2>nul
mkdir batch_logs >nul 2>nul
mkdir failed_diagnostics >nul 2>nul

%V17T2R5_PYTHON% "tools\build_nea_storage_inputs.py"
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\ingest_vre_cf.py" "data\raw\vre_cf\hourly_vre_capacity_factor_2024_CHN_province_withSP.csv.gz"
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\build_publication_vre_cf.py" --force
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\rebuild_publication_source_fingerprint.py"
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\validate_storage_inputs.py"
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\audit_legacy_storage_provenance.py"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_PUBLICATION_SOURCE_GATE.bat" --stage source
if errorlevel 1 exit /b 1

%V17T2R5_PYTHON% "tools\prepare_targetyear_cases.py"
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\audit_targetyear_pair_identity.py"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_PUBLICATION_SOURCE_GATE.bat" --stage cases
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R5_PACKAGE.bat"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R5_RUNTIME.bat"
if errorlevel 1 exit /b 1

rem Ordinary 4 h and LDES pairs keep the audited exact-LP automatic routes.
%V17T2R5_PYTHON% "tools\run_targetyear_batch.py" --pair TY2028_CHRONO --route auto --skip-prepare --force-rerun --clean-central --julia "%V17T2R5_JULIA%"
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\run_targetyear_batch.py" --pair TY2033_CHRONO --route auto --skip-prepare --force-rerun --julia "%V17T2R5_JULIA%"
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\run_targetyear_batch.py" --pair TY2033_CHRONO_LDES --route auto --skip-prepare --force-rerun --julia "%V17T2R5_JULIA%"
if errorlevel 1 exit /b 1

rem Both 1 h pair members receive the same pre-specified robust solver ladder:
rem 12 h scaled Barrier/no crossover -> 24 h Dual Simplex -> 24 h concurrent simplex.
%V17T2R5_PYTHON% "tools\run_targetyear_batch.py" --pair TY2033_CHRONO_1H --route one_hour_robust --skip-prepare --force-rerun --continue-after-failure --julia "%V17T2R5_JULIA%"
if errorlevel 1 exit /b 1

%V17T2R5_PYTHON% "tools\write_publication_result_lineage.py" --kind sensitivity
if errorlevel 1 exit /b 1
call "%~dp0CHECK_PUBLICATION_SOURCE_GATE.bat" --stage results
if errorlevel 1 exit /b 1
call "%~dp0BUILD_V17T2R5_SUMMARY.bat"
if errorlevel 1 exit /b 1

echo.
echo CURRENT STANDALONE SENSITIVITY PASSED: 8/8 strict scenarios.
endlocal
exit /b 0
