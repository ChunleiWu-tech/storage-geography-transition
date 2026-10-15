@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
%V17T2R6_PYTHON% "tools\build_8760_summary.py" %*
exit /b %errorlevel%
