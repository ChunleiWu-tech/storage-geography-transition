@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
set "PYTHONDONTWRITEBYTECODE=1"
set "MPLBACKEND=Agg"
call CHECK_V17_RUNTIME.bat
if errorlevel 1 exit /b 1

rem Clean only generated state. Frozen data, model code and source snapshots are preserved.
if exist "batch_logs" rmdir /s /q "batch_logs"
if exist "outputs" rmdir /s /q "outputs"
if exist "failed_diagnostics" rmdir /s /q "failed_diagnostics"
if exist "postprocess_outputs" rmdir /s /q "postprocess_outputs"
if exist "storage_cases" rmdir /s /q "storage_cases"
if exist "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV" rmdir /s /q "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV"
if exist "storage_runner\storage_batch_run_summary.csv" del /q "storage_runner\storage_batch_run_summary.csv"
if exist "storage_runner\prepared_storage_cases_index.csv" del /q "storage_runner\prepared_storage_cases_index.csv"
if exist "audits\PUBLICATION_RESULT_LINEAGE.json" del /q "audits\PUBLICATION_RESULT_LINEAGE.json"

rem Rebuild the frozen official-source inputs and source fingerprint.
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

rem Static release checks. These do not solve the model.
%V17_PYTHON% "tools\check_v17_ne_config.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_windows_launchers_v17.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_julia_empty_collection_safety.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_julia_syntax_v17.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_numerical_stability_v17.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_objective_certificate_v17.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_v17_release_policy.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\check_v17_run_readiness.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_v17t2_sl10_rescue.py"
if errorlevel 1 exit /b 1

rem Rebuild and validate all sixteen source-locked cases.
%V17_PYTHON% "tools\build_storage_base_case.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\prepare_storage_cases.py" --official --scenario-set spatial_legacy_full --reuse-base
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --stage cases
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_v17t1_four_scenario_repairs.py"
if errorlevel 1 exit /b 1

rem Empirically validated solve policy: serial 1x10; S10/S13 use standard scaled Barrier, Crossover=0.
%V17_PYTHON% "tools\run_v17t4r3_empirical_full16.py" --julia "%JULIA_EXE%" --hard-route-seconds 21600 --force-rerun
if errorlevel 1 exit /b 1

rem Finalize the result lineage only after strict 16/16 success.
%V17_PYTHON% "tools\write_publication_result_lineage.py" --kind main
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --stage results
if errorlevel 1 exit /b 1

echo.
echo V17T4R3 STANDALONE MAIN UPSTREAM PASSED: 16/16 strict scenarios.
endlocal
exit /b 0
