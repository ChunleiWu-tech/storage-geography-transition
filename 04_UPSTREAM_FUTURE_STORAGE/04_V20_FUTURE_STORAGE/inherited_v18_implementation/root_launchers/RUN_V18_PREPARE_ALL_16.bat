@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
call CHECK_V18_STATIC.bat
if errorlevel 1 exit /b 1
if exist "storage_cases" rmdir /s /q "storage_cases"
if exist "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV" rmdir /s /q "base_model_v39\storage_base_noNBCCS_noDACCS_onshorePV"
%V17_PYTHON% "tools\build_storage_base_case.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\prepare_storage_cases.py" --official --scenario-set spatial_legacy_full --reuse-base
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_v18_static.py" --phase cases
if errorlevel 1 exit /b 1
echo V18 PREPARED INPUTS PASSED: 16/16 CASES.
endlocal
exit /b 0
