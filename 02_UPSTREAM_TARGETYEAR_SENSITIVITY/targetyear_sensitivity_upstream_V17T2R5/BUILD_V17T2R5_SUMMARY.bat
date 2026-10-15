@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R5_ENV_DEFAULTS.bat"
%V17T2R5_PYTHON% tools\build_targetyear_summary.py
exit /b %errorlevel%
