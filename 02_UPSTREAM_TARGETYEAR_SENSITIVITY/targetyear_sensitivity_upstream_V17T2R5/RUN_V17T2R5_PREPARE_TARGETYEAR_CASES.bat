@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"
if errorlevel 1 exit /b 1

rem Never reuse an expanded base or a case prepared from an older source fingerprint.
if exist "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV" rmdir /s /q "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV"
if exist "sensitivity_cases" rmdir /s /q "sensitivity_cases"
if exist "sensitivity_outputs" rmdir /s /q "sensitivity_outputs"
if exist "batch_logs" rmdir /s /q "batch_logs"
if exist "failed_diagnostics" rmdir /s /q "failed_diagnostics"
if exist "storage_runner\prepared_targetyear_cases_index.csv" del /q "storage_runner\prepared_targetyear_cases_index.csv"
if exist "audits\PUBLICATION_RESULT_LINEAGE.json" del /q "audits\PUBLICATION_RESULT_LINEAGE.json"

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

echo V17T2R5 source-locked six target-year cases prepared without solving.
endlocal
exit /b 0
