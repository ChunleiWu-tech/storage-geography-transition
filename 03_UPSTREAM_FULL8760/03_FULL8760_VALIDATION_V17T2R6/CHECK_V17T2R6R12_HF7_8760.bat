@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
%V17T2R6_JULIA% --startup-file=no -e "for f in ARGS; Meta.parseall(read(f, String)); println(f); end" "base_model_v39\full8760_hf4_objective_continuation.jl" "base_model_v39\cheer_power_storage_targetyear_v17t2r6_8760.jl"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\audit_targetyear_pair_identity.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_julia_8760_static.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_v17t2r6r12_hf7_restricted_face.py"
exit /b %errorlevel%
