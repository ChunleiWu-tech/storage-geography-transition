@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0CHECK_CLEAN_PACKAGE_MANIFEST.bat"
if errorlevel 1 exit /b 1
call "%~dp0V20_ENV_DEFAULTS.bat"
if errorlevel 1 exit /b 1
set "V17_SOLVER_THREADS=10"
rem This package has isolated output directories, so unrelated Julia jobs need not block HF5.
if not defined V20_HF5_ALLOW_OTHER_JULIA set "V20_HF5_ALLOW_OTHER_JULIA=1"

call "%~dp0PREP_V20.bat"
if errorlevel 1 exit /b 1

set "V20_INITIAL_A_RC=0"
set "V20_INITIAL_B_RC=0"
set "V20_INITIAL_C_RC=0"

call "%~dp0RUN_V20_A8_1x10.bat"
set "V20_INITIAL_A_RC=%ERRORLEVEL%"
if not "%V20_INITIAL_A_RC%"=="0" echo WARNING: initial Layer A route incomplete; HF5 resume will retain strict successes and retry the supported missing target.

call "%~dp0RUN_V20_B16_1x10.bat"
set "V20_INITIAL_B_RC=%ERRORLEVEL%"
if not "%V20_INITIAL_B_RC%"=="0" echo WARNING: initial Layer B route incomplete; HF5 resume will solve missing cases serially.

call "%~dp0RUN_V20_C2_EQUAL_HORIZON_1x10.bat"
set "V20_INITIAL_C_RC=%ERRORLEVEL%"
if not "%V20_INITIAL_C_RC%"=="0" echo WARNING: initial Layer C route incomplete; HF5 resume will rerun/validate the equal-horizon pair.

call "%~dp0RUN_V20_HF5_RESUME_REQUIRED_26_1x10.bat"
if errorlevel 1 exit /b 1
call "%~dp0BUILD_V20_RESULTS.bat"
if errorlevel 1 exit /b 1
echo V20 FUTURE STORAGE PASSED: REQUIRED 26/26 STRICT CASES.
exit /b 0
