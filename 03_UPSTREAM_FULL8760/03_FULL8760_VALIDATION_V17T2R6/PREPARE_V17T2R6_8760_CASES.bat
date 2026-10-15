@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
%V17T2R6_PYTHON% "tools\extract_figshare_2024_load.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\rebuild_publication_source_fingerprint.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\prepare_8760_cases.py"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R6_8760_SOURCE_GATE.bat" --stage cases
exit /b %errorlevel%
