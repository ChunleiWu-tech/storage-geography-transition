@echo off
setlocal
cd /d "%~dp0"
call V17T2R5_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
%V17T2R5_PYTHON% "tools\publication_source_gate.py" %*
exit /b %errorlevel%
