@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
call CHECK_V17_RELEASE.bat
if errorlevel 1 exit /b 1
call CHECK_V17_RUNTIME.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\run_official_batch.py" --prepare --clean-previous --only SL00_OBSERVED_ACTUAL --max-workers 1 --julia "%JULIA_EXE%" --skip-postprocess --enable-controlled-fallback
if errorlevel 1 exit /b 1
echo V17 SL00 controlled Stage-1 solver fallback tree PASSED.
endlocal
