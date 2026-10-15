@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
if not exist "storage_runner\storage_batch_run_summary.csv" (
  echo ERROR: Existing V17T1 16-row batch summary is missing.
  echo Run this launcher inside the completed V17T1 result folder.
  exit /b 1
)
%V17_PYTHON% "tools\audit_v17t2_sl10_rescue.py" --require-existing-results
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\run_v17t2_sl10_rescue.py" --julia "%JULIA_EXE%"
if errorlevel 1 exit /b 1
%V17_PYTHON% "postprocess\preflight_spatial_legacy_outputs.py" --scenario-set spatial_legacy_full
if errorlevel 1 exit /b 1
echo V17T2 SL10-only rescue and 16-scenario preflight PASSED.
endlocal
