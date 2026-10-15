@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_v18_static.py" --phase source
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_julia_syntax_v17.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_julia_empty_collection_safety.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_numerical_stability_v17.py"
if errorlevel 1 exit /b 1
echo V18 STATIC SOURCE/MODEL AUDIT PASSED.
endlocal
exit /b 0
