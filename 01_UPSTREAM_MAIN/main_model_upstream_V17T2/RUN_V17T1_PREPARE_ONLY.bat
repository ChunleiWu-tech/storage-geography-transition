@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
if exist "storage_cases" rmdir /s /q "storage_cases"
if exist "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV" rmdir /s /q "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV"
%V17_PYTHON% "tools\build_storage_base_case.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\prepare_storage_cases.py" --official --scenario-set spatial_legacy_full
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_v17t1_four_scenario_repairs.py"
if errorlevel 1 exit /b 1
echo V17T1 prepared 16 scenarios and passed the targeted four-scenario repair audit.
endlocal
