@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V18R1_ENV_DEFAULTS.bat"
%V18R1_PYTHON% -m pip install --upgrade pip
if errorlevel 1 exit /b %errorlevel%
%V18R1_PYTHON% -m pip install -r "requirements_v17.txt"
exit /b %errorlevel%
