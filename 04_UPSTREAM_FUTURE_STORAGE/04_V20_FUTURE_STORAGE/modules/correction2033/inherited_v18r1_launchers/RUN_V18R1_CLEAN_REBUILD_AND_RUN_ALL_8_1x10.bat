@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0V18R1_ENV_DEFAULTS.bat"

echo === V18R1 clean rebuild: removing only generated runtime/derived artifacts ===
if exist "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV" rmdir /s /q "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV"
if exist "future_correction_cases" rmdir /s /q "future_correction_cases"
if exist "future_correction_outputs" rmdir /s /q "future_correction_outputs"
if exist "future_correction_batch_logs" rmdir /s /q "future_correction_batch_logs"
if exist "failed_diagnostics" rmdir /s /q "failed_diagnostics"
if exist "storage_runner\prepared_future_correction_cases_index.csv" del /q "storage_runner\prepared_future_correction_cases_index.csv"
if exist "audits\PUBLICATION_RESULT_LINEAGE_V18R1.json" del /q "audits\PUBLICATION_RESULT_LINEAGE_V18R1.json"
if exist "audits\PUBLICATION_SOURCE_GATE_CASES.json" del /q "audits\PUBLICATION_SOURCE_GATE_CASES.json"
if exist "audits\PUBLICATION_SOURCE_GATE_RESULTS.json" del /q "audits\PUBLICATION_SOURCE_GATE_RESULTS.json"

call "%~dp0RUN_V18R1_PREPARE_ALL_8.bat"
if errorlevel 1 exit /b %errorlevel%
call "%~dp0RUN_V18R1_ALL_8_1x10.bat"
if errorlevel 1 exit /b %errorlevel%
call "%~dp0RUN_V18R1_BUILD_SUMMARY_AND_FIG6.bat"
exit /b %errorlevel%
