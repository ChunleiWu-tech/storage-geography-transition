@echo off
setlocal
cd /d "%~dp0"
call V20_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
set "PYTHONDONTWRITEBYTECODE=1"

echo === V20 Layer A: rebuild 8 matched 2033 correction cases ===
pushd "modules\correction2033"
call V18R1_ENV_DEFAULTS.bat
%V18R1_PYTHON% "tools\prepare_future_correction_cases.py" --reuse-fresh-base
set RC=%ERRORLEVEL%
popd
if not "%RC%"=="0" exit /b %RC%

echo === V20 Layer B: rebuild 16 evidence-direct dynamic-pathway cases ===
%V17_PYTHON% "tools\prepare_storage_cases.py" --official --reuse-base
if errorlevel 1 exit /b %errorlevel%

echo === V20 Layer C: build mandatory equal-evidence-horizon pair ===
%V17_PYTHON% "tools\prepare_v20_equal_horizon_pair.py"
if errorlevel 1 exit /b %errorlevel%

call CHECK_V20_STATIC.bat
exit /b %errorlevel%
