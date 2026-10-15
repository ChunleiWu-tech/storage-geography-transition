@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
set "PYTHONDONTWRITEBYTECODE=1"
set "MPLBACKEND=Agg"
call CHECK_V17_RUNTIME.bat
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --stage source
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --stage cases
if errorlevel 1 exit /b 1

rem Reuse any canonical output that already passes every strict publication gate.
rem Only missing/failed scenarios are solved. S10/S13 use the proven scaled-Barrier route.
%V17_PYTHON% "tools\run_v17t4r3_empirical_full16.py" --julia "%JULIA_EXE%" --hard-route-seconds 21600
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\write_publication_result_lineage.py" --kind main
if errorlevel 1 exit /b 1
call CHECK_PUBLICATION_SOURCE_GATE.bat --stage results
if errorlevel 1 exit /b 1

echo.
echo V17T4R3 STANDALONE MAIN RESUME PASSED: 16/16 strict scenarios.
endlocal
exit /b 0
