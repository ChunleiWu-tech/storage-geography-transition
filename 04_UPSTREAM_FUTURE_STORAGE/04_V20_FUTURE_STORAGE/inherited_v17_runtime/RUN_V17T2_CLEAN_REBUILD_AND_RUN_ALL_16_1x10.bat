@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
call CHECK_V17_RUNTIME.bat
if errorlevel 1 exit /b 1

rem Remove every expanded case, stale result, result-lineage stamp and postprocess output.
if exist "batch_logs" rmdir /s /q "batch_logs"
if exist "outputs" rmdir /s /q "outputs"
if exist "failed_diagnostics" rmdir /s /q "failed_diagnostics"
if exist "postprocess_outputs" rmdir /s /q "postprocess_outputs"
if exist "storage_cases" rmdir /s /q "storage_cases"
if exist "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV" rmdir /s /q "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV"
if exist "storage_runner\storage_batch_run_summary.csv" del /q "storage_runner\storage_batch_run_summary.csv"
if exist "storage_runner\prepared_storage_cases_index.csv" del /q "storage_runner\prepared_storage_cases_index.csv"
if exist "audits\PUBLICATION_RESULT_LINEAGE.json" del /q "audits\PUBLICATION_RESULT_LINEAGE.json"

rem Rebuild the storage stock and VRE profile only from the frozen source snapshots.
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

rem Static scientific and launcher checks that do not solve or generate substitute results.
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

rem Build all sixteen source-locked cases and validate their complete input lineage.
%V17_PYTHON% "tools\build_storage_base_case.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\prepare_storage_cases.py" --official --scenario-set spatial_legacy_full --reuse-base
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --stage cases
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_v17t1_four_scenario_repairs.py"
if errorlevel 1 exit /b 1

rem Run Julia-Gurobi, stamp result lineage, and release only when all sixteen pass.
%V17_PYTHON% "tools\run_official_batch.py" --scenario-set spatial_legacy_full --max-workers 1 --julia "%JULIA_EXE%" --skip-postprocess --enable-controlled-fallback
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\write_publication_result_lineage.py" --kind main
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --stage results
if errorlevel 1 exit /b 1

echo V17T2 official-source full 16-scenario upstream solve PASSED.
endlocal
exit /b 0
