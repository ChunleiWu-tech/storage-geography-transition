@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
"%JULIA_EXE%" --startup-file=no "storage_runner\check_v17_source_load.jl"
if errorlevel 1 (
  echo V17 production source load validation FAILED.
  exit /b 1
)
echo V17 production source load validation PASSED.
endlocal
