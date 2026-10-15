@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V18R1_ENV_DEFAULTS.bat"
%V18R1_PYTHON% "tools\publication_source_gate.py" --stage source
if errorlevel 1 exit /b %errorlevel%
%V18R1_PYTHON% "tools\prepare_future_correction_cases.py" --reuse-fresh-base
if errorlevel 1 exit /b %errorlevel%
%V18R1_PYTHON% "tools\publication_source_gate.py" --stage cases
exit /b %errorlevel%
