@echo off
setlocal
cd /d "%~dp0"
if "%~4"=="" (
  echo Usage: RUN_V30_POSTPROCESS.bat "MAIN_ROOT" "SENSITIVITY_ROOT" "FULL8760_ROOT" "V20_ROOT"
  exit /b 2
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_V30_POSTPROCESS.ps1" -MainUpstreamRoot "%~1" -TargetYearUpstreamRoot "%~2" -Full8760Root "%~3" -FutureStorageRoot "%~4"
exit /b %errorlevel%
