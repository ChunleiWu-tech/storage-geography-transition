@echo off
setlocal
cd /d "%~dp0"
call V20_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
"%JULIA_EXE%" --startup-file=no "storage_runner\check_v17_source_load.jl"
set RC=%ERRORLEVEL%
endlocal & exit /b %RC%
