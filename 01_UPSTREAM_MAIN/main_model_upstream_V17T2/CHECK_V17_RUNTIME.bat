@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
call CHECK_V17_SOURCE_LOAD.bat
if errorlevel 1 exit /b 1
"%JULIA_EXE%" --startup-file=no "storage_runner\check_v17_runtime.jl"
if errorlevel 1 (
  echo V17 Julia/Gurobi runtime validation FAILED.
  exit /b 1
)
echo V17 Julia/Gurobi runtime validation PASSED.
endlocal
