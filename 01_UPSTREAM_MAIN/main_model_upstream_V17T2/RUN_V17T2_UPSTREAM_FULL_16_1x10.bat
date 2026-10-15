@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1

rem Rebuild the frozen official-source inputs before any case is prepared.
%V17_PYTHON% "tools\build_nea_storage_inputs.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\build_publication_vre_cf.py" --force
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\validate_storage_inputs.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_legacy_storage_provenance.py"
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat
if errorlevel 1 exit /b 1

call CHECK_V17_RELEASE.bat
if errorlevel 1 exit /b 1
call CHECK_V17_SOURCE_LOAD.bat
if errorlevel 1 exit /b 1
call CHECK_V17_RUNTIME.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_v17t2_sl10_rescue.py"
if errorlevel 1 exit /b 1

rem No pre-update expanded case, prepared case, result or postprocess output may survive.
if exist "batch_logs" rmdir /s /q "batch_logs"
if exist "outputs" rmdir /s /q "outputs"
if exist "failed_diagnostics" rmdir /s /q "failed_diagnostics"
if exist "postprocess_outputs" rmdir /s /q "postprocess_outputs"
if exist "storage_runner\storage_batch_run_summary.csv" del /q "storage_runner\storage_batch_run_summary.csv"
if exist "storage_runner\prepared_storage_cases_index.csv" del /q "storage_runner\prepared_storage_cases_index.csv"
if exist "storage_cases" rmdir /s /q "storage_cases"
if exist "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV" rmdir /s /q "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV"
if exist "audits\PUBLICATION_RESULT_LINEAGE.json" del /q "audits\PUBLICATION_RESULT_LINEAGE.json"

%V17_PYTHON% "tools\build_storage_base_case.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\prepare_storage_cases.py" --official --scenario-set spatial_legacy_full --reuse-base
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --require-prepared-cases
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_v17t1_four_scenario_repairs.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\run_official_batch.py" --scenario-set spatial_legacy_full --max-workers 1 --julia "%JULIA_EXE%" --skip-postprocess --enable-controlled-fallback --clean-previous
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\write_publication_result_lineage.py" --kind main
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --require-prepared-cases --require-results
if errorlevel 1 exit /b 1
echo V17T3 official-source full 16-scenario upstream solve PASSED.
endlocal
