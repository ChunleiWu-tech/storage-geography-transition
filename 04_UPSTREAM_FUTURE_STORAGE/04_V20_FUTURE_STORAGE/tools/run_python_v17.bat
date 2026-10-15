@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem Robust Python launcher for Storage V17.
rem Usage: call tools\run_python_v17.bat script.py [arguments]
rem Optional override: set V17_PYTHON_EXE=C:\full\path\python.exe

if "%~1"=="" (
  echo ERROR: No Python script was supplied to run_python_v17.bat.
  exit /b 64
)

if defined V17_PYTHON_EXE (
  if exist "%V17_PYTHON_EXE%" (
    "%V17_PYTHON_EXE%" -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
    if not errorlevel 1 (
      "%V17_PYTHON_EXE%" %*
      exit /b !errorlevel!
    )
  )
  echo ERROR: V17_PYTHON_EXE is defined but is not a working Python 3.10+ executable:
  echo        %V17_PYTHON_EXE%
  exit /b 9009
)

for %%P in (
  "%LocalAppData%\Programs\Python\Python314\python.exe"
  "%LocalAppData%\Programs\Python\Python313\python.exe"
  "%LocalAppData%\Programs\Python\Python312\python.exe"
  "%LocalAppData%\Programs\Python\Python311\python.exe"
  "%LocalAppData%\Programs\Python\Python310\python.exe"
  "%ProgramFiles%\Python314\python.exe"
  "%ProgramFiles%\Python313\python.exe"
  "%ProgramFiles%\Python312\python.exe"
  "%ProgramFiles%\Python311\python.exe"
  "%ProgramFiles%\Python310\python.exe"
) do (
  if exist "%%~P" (
    "%%~P" -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
    if not errorlevel 1 (
      "%%~P" %*
      exit /b !errorlevel!
    )
  )
)

where python.exe >nul 2>nul
if not errorlevel 1 (
  python.exe -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
  if not errorlevel 1 (
    python.exe %*
    exit /b !errorlevel!
  )
)

where python3.exe >nul 2>nul
if not errorlevel 1 (
  python3.exe -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
  if not errorlevel 1 (
    python3.exe %*
    exit /b !errorlevel!
  )
)

where py.exe >nul 2>nul
if not errorlevel 1 (
  for %%V in (-3.14 -3.13 -3.12 -3.11 -3.10 -3) do (
    py.exe %%V -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
    if not errorlevel 1 (
      py.exe %%V %*
      exit /b !errorlevel!
    )
  )
)

echo ERROR: Storage V17 could not find a working Python 3.10+ runtime.
echo.
echo Detection attempted:
echo   1. V17_PYTHON_EXE override
echo   2. Standard per-user and Program Files Python 3.10-3.14 paths
echo   3. python.exe and python3.exe on PATH
echo   4. py.exe with -3.14, -3.13, -3.12, -3.11, -3.10, and -3
echo.
echo To set an explicit interpreter in PowerShell:
echo   $env:V17_PYTHON_EXE = 'C:\Path\To\Python\python.exe'
echo Then rerun the requested V17 batch file.
where python.exe 2>nul
where python3.exe 2>nul
where py.exe 2>nul
if exist "%LocalAppData%\Programs\Python" dir /b "%LocalAppData%\Programs\Python" 2>nul
exit /b 9009
