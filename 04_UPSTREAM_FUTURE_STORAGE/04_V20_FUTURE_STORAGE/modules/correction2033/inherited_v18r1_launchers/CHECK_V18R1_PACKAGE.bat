@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V18R1_ENV_DEFAULTS.bat"
%V18R1_PYTHON% "tools\check_v18r1_package.py"
exit /b %errorlevel%
