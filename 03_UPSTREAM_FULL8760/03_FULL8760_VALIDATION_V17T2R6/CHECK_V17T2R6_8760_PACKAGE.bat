@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
%V17T2R6_PYTHON% "tools\check_8760_package.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\verify_8760_package_manifest.py"
exit /b %errorlevel%
