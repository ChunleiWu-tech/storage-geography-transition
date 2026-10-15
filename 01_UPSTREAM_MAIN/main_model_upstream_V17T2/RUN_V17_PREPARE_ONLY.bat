@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1

rem Preparing new source-locked cases invalidates every pre-existing result.
if exist "storage_cases" rmdir /s /q "storage_cases"
if exist "outputs" rmdir /s /q "outputs"
if exist "batch_logs" rmdir /s /q "batch_logs"
if exist "failed_diagnostics" rmdir /s /q "failed_diagnostics"
if exist "postprocess_outputs" rmdir /s /q "postprocess_outputs"
if exist "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV" rmdir /s /q "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV"
if exist "storage_runner\prepared_storage_cases_index.csv" del /q "storage_runner\prepared_storage_cases_index.csv"
if exist "storage_runner\storage_batch_run_summary.csv" del /q "storage_runner\storage_batch_run_summary.csv"
if exist "audits\PUBLICATION_RESULT_LINEAGE.json" del /q "audits\PUBLICATION_RESULT_LINEAGE.json"

%V17_PYTHON% "tools\build_nea_storage_inputs.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\ingest_vre_cf.py" "data\raw\vre_cf\hourly_vre_capacity_factor_2024_CHN_province_withSP.csv.gz"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\build_publication_vre_cf.py" --force
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\rebuild_publication_source_fingerprint.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\validate_storage_inputs.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_legacy_storage_provenance.py"
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --stage source
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\build_storage_base_case.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\prepare_storage_cases.py" --official --scenario-set spatial_legacy_full --reuse-base
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --stage cases
if errorlevel 1 exit /b 1

echo V17T2 source-locked 16 official cases prepared without solving.
endlocal
exit /b 0
