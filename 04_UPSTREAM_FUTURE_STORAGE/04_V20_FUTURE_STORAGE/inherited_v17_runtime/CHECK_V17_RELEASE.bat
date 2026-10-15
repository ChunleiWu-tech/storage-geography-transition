@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% -c "import numpy, pandas, matplotlib" >nul 2>nul
if errorlevel 1 (
  echo ERROR: Required Python packages are missing for %V17_PYTHON%.
  echo Install them with:
  echo   %V17_PYTHON% -m pip install -r requirements_v17.txt
  exit /b 1
)
%V17_PYTHON% "tools\validate_release_v17.py"
if errorlevel 1 (
  echo V17 release validation FAILED.
  exit /b 1
)
echo V17 release validation PASSED.
endlocal
