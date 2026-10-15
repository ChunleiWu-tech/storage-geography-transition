@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

rem No optimizer is invoked. The original R24P2 solve and raw failed-gate files are preserved.
set "V17_SOLVER_THREADS=10"
if not defined V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT set "V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT=%~dp0..\targetyear_sensitivity_upstream_V17T2R5\sensitivity_outputs"

if not exist "%V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT%\TY2033_CHRONO_OBSERVED__main\solve_status.csv" (
  echo ERROR: strict source TY2033_CHRONO_OBSERVED__main is incomplete.
  echo Source root: %V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT%
  exit /b 1
)

call "%~dp0CHECK_V17T2R6R24P3_HF18P2_POSTSOLVE_RECOVERY.bat"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "%~dp0tools\run_hf18p2_r24p3_postsolve_complementarity_recovery.py"
exit /b %errorlevel%

