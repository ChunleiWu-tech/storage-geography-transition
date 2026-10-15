@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
"%V17T2R6_JULIA%" storage_runner\check_v17t2r6_8760_runtime.jl
exit /b %errorlevel%
