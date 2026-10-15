@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"
"%V17T2R5_JULIA%" storage_runner\check_v17t2r5_runtime.jl
exit /b %errorlevel%
