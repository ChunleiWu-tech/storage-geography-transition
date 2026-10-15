@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

if defined GUROBI1302_HOME set "GUROBI_HOME=%GUROBI1302_HOME%"
if not defined GUROBI_HOME if exist "%~dp0V17T2R6_HF17_GUROBI1302_HOME.txt" set /p GUROBI_HOME=<"%~dp0V17T2R6_HF17_GUROBI1302_HOME.txt"
if not defined GUROBI_HOME if exist "%~dp0V17T2R6_HF16_GUROBI1302_HOME.txt" set /p GUROBI_HOME=<"%~dp0V17T2R6_HF16_GUROBI1302_HOME.txt"
if not defined GUROBI_HOME if exist "C:\gurobi1302\win64\bin\gurobi130.dll" set "GUROBI_HOME=C:\gurobi1302\win64"
if not defined GUROBI_HOME if exist "C:\Program Files\gurobi1302\win64\bin\gurobi130.dll" set "GUROBI_HOME=C:\Program Files\gurobi1302\win64"
if not defined GUROBI_HOME (
  echo ERROR: local Gurobi 13.0.2 was not found. Set GUROBI1302_HOME first.
  exit /b 1
)
if not exist "%GUROBI_HOME%\bin\gurobi130.dll" (
  echo ERROR: missing "%GUROBI_HOME%\bin\gurobi130.dll".
  exit /b 1
)
set "PATH=%GUROBI_HOME%\bin;%PATH%"
set "GUROBI_JL_USE_GUROBI_JLL=false"
set "V17_SOLVER_THREADS=10"
set "V17T2R6_MAX_PARALLEL=2"
set "V17_STAGE1_CERT_STRICT_REL_TOL=1.0e-6"
set "V17_STAGE1_CERT_ACCEPT_REL_TOL=1.0e-5"

%V17T2R6_JULIA% --startup-file=no -e "for f in ARGS; Meta.parseall(read(f, String)); println(f); end" "base_model_v39\full8760_hf18_fixed_portfolio_validation.jl" "base_model_v39\cheer_power_storage_targetyear_v17t2r6_8760.jl" "storage_runner\run_targetyear_one.jl" "tools\check_hf18p2_gurobi1302_runtime.jl"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% -m py_compile "tools\run_hf18p2_quality_recovery_two_parallel.py" "tools\check_v17t2r6r24p2_hf18p2_quality_recovery.py" "tools\audit_hf18p2_cross_resolution_contract.py" "tools\check_julia_delimiters.py" "tools\verify_hf18p2_r24p2_patch_manifest.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\verify_hf18p2_r24p2_patch_manifest.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_julia_delimiters.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_v17t2r6r24p2_hf18p2_quality_recovery.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\audit_hf18p2_cross_resolution_contract.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\audit_targetyear_pair_identity.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\audit_hf15_exact_fuel_elimination_inputs.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\audit_hf16_exact_commitment_projection_inputs.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\audit_hf17_exact_scaling_and_hydro_projection_inputs.py"
if errorlevel 1 exit /b 1
%V17T2R6_JULIA% --startup-file=no "tools\check_hf18p2_gurobi1302_runtime.jl"
if errorlevel 1 exit /b 1
echo V17T2R6R24P2-HF18P2 quality-recovery preflight: PASS
exit /b 0
