@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"
"%V17T2R5_JULIA%" -e "using Pkg; Pkg.add([\"JuMP\",\"Gurobi\",\"CSV\",\"DataFrames\",\"JSON\"]); Pkg.precompile()"
exit /b %errorlevel%
