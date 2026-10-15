@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: PREPARE_V18_ONE_PRESSURE_TEST_CASE.bat SCENARIO_ID
  exit /b 2
)
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\prepare_storage_cases.py" --scenario "%~1" --reuse-base
if errorlevel 1 exit /b 1
echo V18 pressure-test case prepared: %~1
echo NOTE: Headline semantics remain evidence_bounded. No solver has been run by this launcher.
endlocal
exit /b 0
