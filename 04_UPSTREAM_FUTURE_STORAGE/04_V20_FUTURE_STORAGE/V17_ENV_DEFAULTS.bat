@echo off
rem Shared V17 runtime defaults.
rem V17_PYTHON may be an executable command such as: py -3.14
rem It may also be a quoted absolute path such as: "C:\Python312\python.exe"
set "V17_ENV_ERROR="

if defined V17_PYTHON (
  %V17_PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
  if errorlevel 1 (
    echo ERROR: V17_PYTHON is set but is not a working Python 3.10+ command: %V17_PYTHON%
    echo Run: py -0p
    echo Then set, for example: set "V17_PYTHON=py -3.14"
    set "V17_ENV_ERROR=1"
    exit /b 1
  )
  goto :python_ready
)

call :try_python py -3.12
if defined V17_PYTHON goto :python_ready
call :try_python py -3.13
if defined V17_PYTHON goto :python_ready
call :try_python py -3.11
if defined V17_PYTHON goto :python_ready
call :try_python py -3.10
if defined V17_PYTHON goto :python_ready
call :try_python py -3.14
if defined V17_PYTHON goto :python_ready
call :try_python py -3
if defined V17_PYTHON goto :python_ready
call :try_python python
if defined V17_PYTHON goto :python_ready
call :try_python python3
if defined V17_PYTHON goto :python_ready

echo ERROR: No working Python 3.10+ runtime was found.
echo Run: py -0p
echo Then set V17_PYTHON to an installed runtime, for example:
echo   set "V17_PYTHON=py -3.14"
echo or in PowerShell:
echo   $env:V17_PYTHON = "py -3.14"
set "V17_ENV_ERROR=1"
exit /b 1

:python_ready
for /f "delims=" %%P in ('%V17_PYTHON% -c "import sys; print(sys.executable)"') do set "V17_PYTHON_RESOLVED=%%P"
for /f "delims=" %%V in ('%V17_PYTHON% -c "import sys; print('.'.join(map(str,sys.version_info[:3])))"') do set "V17_PYTHON_VERSION=%%V"
echo V17 Python runtime: %V17_PYTHON% ^| %V17_PYTHON_RESOLVED% ^| version %V17_PYTHON_VERSION%

if not defined JULIA_EXE set "JULIA_EXE=julia"
if not defined V17_SOLVER_THREADS set "V17_SOLVER_THREADS=10"
set "PYTHONDONTWRITEBYTECODE=1"
set "MPLBACKEND=Agg"
if not defined V17_ECONOMIC_BARRIER_TIME_LIMIT_SECONDS set "V17_ECONOMIC_BARRIER_TIME_LIMIT_SECONDS=7200"
if not defined V17_ECONOMIC_FALLBACK_TIME_LIMIT_SECONDS set "V17_ECONOMIC_FALLBACK_TIME_LIMIT_SECONDS=7200"
if not defined V17_ECONOMIC_BAR_ITER_LIMIT set "V17_ECONOMIC_BAR_ITER_LIMIT=1500"
if not defined V17T1_HARD_LP_TIME_LIMIT_SECONDS set "V17T1_HARD_LP_TIME_LIMIT_SECONDS=21600"
if not defined V17T1_HARD_LP_BAR_ITER_LIMIT set "V17T1_HARD_LP_BAR_ITER_LIMIT=5000"
if not defined V17T2_SL10_BARRIER_TIME_LIMIT_SECONDS set "V17T2_SL10_BARRIER_TIME_LIMIT_SECONDS=21600"
if not defined V17_CLEANUP_BARRIER_TIME_LIMIT_SECONDS set "V17_CLEANUP_BARRIER_TIME_LIMIT_SECONDS=1800"
if not defined V17_CLEANUP_PRIMAL_TIME_LIMIT_SECONDS set "V17_CLEANUP_PRIMAL_TIME_LIMIT_SECONDS=3600"
if not defined V17_CLEANUP_DUAL_TIME_LIMIT_SECONDS set "V17_CLEANUP_DUAL_TIME_LIMIT_SECONDS=1800"
if not defined V17_CLEANUP_CONCURRENT_TIME_LIMIT_SECONDS set "V17_CLEANUP_CONCURRENT_TIME_LIMIT_SECONDS=3600"
if not defined V17_CLEANUP_BAR_ITER_LIMIT set "V17_CLEANUP_BAR_ITER_LIMIT=1200"
rem External objective-diagnostic thresholds; the native Barrier certificate remains BarConvTol=1e-8.
set "V17_STAGE1_CERT_STRICT_REL_TOL=1.0e-7"
set "V17_STAGE1_CERT_ACCEPT_REL_TOL=1.0e-6"
set "V17_CLEANUP_ECONOMIC_REL_TOL=1.0e-6"
exit /b 0

:try_python
%* -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 set "V17_PYTHON=%*"
exit /b 0
