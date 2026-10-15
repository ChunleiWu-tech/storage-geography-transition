@echo off
setlocal
cd /d "%~dp0"
call V20_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
set "PYTHONDONTWRITEBYTECODE=1"

echo === Python runtime/dependencies ===
%V17_PYTHON% -c "import sys,numpy,pandas,matplotlib; print('Python',sys.version.split()[0]); print('numpy',numpy.__version__); print('pandas',pandas.__version__); print('matplotlib',matplotlib.__version__)"
if errorlevel 1 (
  echo ERROR: Python dependencies missing. Run INSTALL_V17_PYTHON_DEPS.bat first.
  exit /b 1
)

echo === Julia runtime ===
"%JULIA_EXE%" --version
if errorlevel 1 (
  echo ERROR: Julia runtime not found. Set JULIA_EXE, for example: set "JULIA_EXE=julia"
  exit /b 1
)

echo === Production source-load probe ===
call CHECK_V17_SOURCE_LOAD.bat
if errorlevel 1 (
  echo ERROR: frozen production Julia source failed to load.
  exit /b 1
)

echo === Julia/Gurobi production-route probe ===
"%JULIA_EXE%" --startup-file=no "storage_runner\check_v17_runtime.jl"
if errorlevel 1 (
  echo V20 Julia/Gurobi runtime validation FAILED.
  exit /b 1
)

echo ============================================================
echo V20 PYTHON + JULIA + GUROBI RUNTIME GATE: PASS
echo This is a small runtime probe; it does NOT solve the V20 study cases.
echo ============================================================
endlocal
exit /b 0
