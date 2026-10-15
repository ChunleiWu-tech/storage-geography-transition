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

rem Canonical R24P2 run contract: exactly two OBSERVED cases, parallel, 10 threads each.
set "V17_SOLVER_THREADS=10"
set "V17T2R6_MAX_PARALLEL=2"
set "V17_STAGE1_CERT_STRICT_REL_TOL=1.0e-6"
set "V17_STAGE1_CERT_ACCEPT_REL_TOL=1.0e-5"
if not defined V17T2R6R24_HF18P2_TIME_LIMIT_SECONDS set "V17T2R6R24_HF18P2_TIME_LIMIT_SECONDS=43200"
if not defined V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT set "V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT=%~dp0..\targetyear_sensitivity_upstream_V17T2R5\sensitivity_outputs"

for %%S in (TY2033_CHRONO_OBSERVED TY2033_CHRONO_LDES_OBSERVED TY2033_CHRONO_OPTIMAL TY2033_CHRONO_LDES_OPTIMAL) do (
  if not exist "%V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT%\%%S__main\solve_status.csv" (
    echo ERROR: strict target-year source is incomplete: %%S__main
    echo Source root: %V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT%
    exit /b 1
  )
)

for %%S in (TY2033_FULL8760_OPTIMAL TY2033_FULL8760_LDES_OPTIMAL) do (
  if not exist "%~dp0robustness_distance_8760_outputs\%%S__main\HF18P2_RESULT_FINGERPRINT.json" (
    echo ERROR: protected successful R24P1 certificate is missing: %%S
    echo R24P2 will not recompute or overwrite the two successful OPTIMAL cases.
    exit /b 1
  )
)

call "%~dp0CHECK_V17T2R6R24P2_HF18P2_QUALITY_RECOVERY.bat"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "%~dp0tools\run_hf18p2_quality_recovery_two_parallel.py" --julia "%V17T2R6_JULIA%"
exit /b %errorlevel%
