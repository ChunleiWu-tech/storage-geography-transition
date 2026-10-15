@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
rem R7 canonical resource policy: exactly two simultaneous 8760 cases, 10 Gurobi threads each.
set "V17_SOLVER_THREADS=10"
set "V17T2R6_MAX_PARALLEL=2"
call "%~dp0CHECK_V17T2R6_8760_PREFLIGHT.bat"
if errorlevel 1 exit /b 1
echo.
echo === V17T2R6R7-HF2P2 FULL8760 PARALLEL POLICY: 2 concurrent cases x 10 solver threads ===
echo Wave 1: TY2033_FULL8760_OBSERVED + TY2033_FULL8760_OPTIMAL
echo Wave 2: TY2033_FULL8760_LDES_OBSERVED + TY2033_FULL8760_LDES_OPTIMAL
echo.
rem Resume-safe: existing strict official outputs are revalidated and skipped.
rem --continue-after-failure finishes the second pair even if one first-wave case fails;
rem finalization still occurs only when all requested cases pass strict release gates.
%V17T2R6_PYTHON% "tools\run_targetyear_batch.py" --pair ALL --route auto --skip-prepare --continue-after-failure --max-parallel 2 --julia "%V17T2R6_JULIA%"
if errorlevel 1 exit /b 1
call "%~dp0FINALIZE_V17T2R6_8760_RESULTS.bat"
exit /b %errorlevel%
