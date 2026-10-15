@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"
%V17T2R5_PYTHON% -m pip install --upgrade pip
if errorlevel 1 exit /b %errorlevel%
%V17T2R5_PYTHON% -m pip install -r requirements_v17.txt
exit /b %errorlevel%
