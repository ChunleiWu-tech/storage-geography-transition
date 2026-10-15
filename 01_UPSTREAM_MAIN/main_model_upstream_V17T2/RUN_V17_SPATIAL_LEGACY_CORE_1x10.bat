@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
call CHECK_V17_RUNTIME.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\run_official_batch.py" --prepare --clean-previous --scenario-set spatial_legacy_core --max-workers 1 --julia "%JULIA_EXE%" --skip-postprocess --enable-controlled-fallback
if errorlevel 1 exit /b 1
echo V17 core scenario set official Stage-1 release PASSED.
endlocal
