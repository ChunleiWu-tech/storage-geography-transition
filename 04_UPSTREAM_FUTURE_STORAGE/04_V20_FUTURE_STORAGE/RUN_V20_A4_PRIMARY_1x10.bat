@echo off
setlocal
cd /d "%~dp0"
call V20_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
call CHECK_V20_STATIC.bat
if errorlevel 1 exit /b 1
pushd "modules\correction2033"
call V18R1_ENV_DEFAULTS.bat
set "V17_SOLVER_THREADS=10"
echo === V20 Layer A primary 1/2: BASE ===
%V18R1_PYTHON% "tools\run_future_correction_batch.py" --pair FC_BASE --route robust --skip-prepare --julia "%V18R1_JULIA%"
if errorlevel 1 (set RC=%ERRORLEVEL%& popd & exit /b %RC%)
echo === V20 Layer A primary 2/2: ADAPTIVE ===
%V18R1_PYTHON% "tools\run_future_correction_batch.py" --pair FC_ADAPTIVE --route robust --skip-prepare --julia "%V18R1_JULIA%"
set RC=%ERRORLEVEL%
popd
exit /b %RC%
