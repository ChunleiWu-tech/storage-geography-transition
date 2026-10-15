@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V18R1_ENV_DEFAULTS.bat"
"%V18R1_JULIA%" -e "using Pkg; Pkg.add([\"JuMP\",\"Gurobi\",\"CSV\",\"DataFrames\",\"JSON\"]); Pkg.precompile()"
exit /b %errorlevel%
