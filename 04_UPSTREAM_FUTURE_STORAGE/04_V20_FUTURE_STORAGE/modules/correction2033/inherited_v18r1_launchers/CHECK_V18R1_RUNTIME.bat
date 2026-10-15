@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V18R1_ENV_DEFAULTS.bat"
"%V18R1_JULIA%" "storage_runner\check_v18r1_runtime.jl"
exit /b %errorlevel%
