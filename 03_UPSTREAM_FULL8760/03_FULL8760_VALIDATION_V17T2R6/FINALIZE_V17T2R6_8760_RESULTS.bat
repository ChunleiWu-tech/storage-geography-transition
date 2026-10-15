@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"
%V17T2R6_PYTHON% "tools\write_publication_result_lineage.py" --kind sensitivity
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R6_8760_SOURCE_GATE.bat" --stage results
if errorlevel 1 exit /b 1
call "%~dp0BUILD_V17T2R6_8760_SUMMARY.bat"
if errorlevel 1 exit /b 1
echo V17T2R6R7-HF2 full-8760 result finalization PASSED.
exit /b 0
