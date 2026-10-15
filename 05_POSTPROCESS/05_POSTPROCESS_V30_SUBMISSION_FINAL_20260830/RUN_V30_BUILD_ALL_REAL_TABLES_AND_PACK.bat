@echo off
setlocal
cd /d "%~dp0"
call "%~dp0CHECK_V30_PACKAGE.bat"
if errorlevel 1 (
  echo ERROR: V30 package static gate failed; no data bundle was created.
  exit /b 1
)
set "PROJECT_ROOT=C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8"
set "PYEXE="
for /f "delims=" %%P in ('py -3.11 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%P"
if not defined PYEXE for /f "delims=" %%P in ('py -3 -c "import sys; sys.exit(1) if sys.version_info ^< (3,10) else print(sys.executable)" 2^>nul') do set "PYEXE=%%P"
if not defined PYEXE (
  echo ERROR: Python 3.10+ was not found.
  exit /b 2
)
echo Using Python: %PYEXE%
"%PYEXE%" "%~dp0postprocess\build_v30_all_real_tables_bundle.py" ^
  --main-upstream-root "%PROJECT_ROOT%\main_model_upstream_V17T2" ^
  --targetyear-upstream-root "%PROJECT_ROOT%\targetyear_sensitivity_upstream_V17T2R5" ^
  --full8760-root "%PROJECT_ROOT%\03_FULL8760_VALIDATION_V17T2R6" ^
  --future-storage-root "%PROJECT_ROOT%\04_V20_FUTURE_STORAGE" ^
  --bundle-path "C:\Users\Admin\Desktop\V30_ALL_REAL_TABLES_AND_AUDITS_20260830.zip"
exit /b %errorlevel%
