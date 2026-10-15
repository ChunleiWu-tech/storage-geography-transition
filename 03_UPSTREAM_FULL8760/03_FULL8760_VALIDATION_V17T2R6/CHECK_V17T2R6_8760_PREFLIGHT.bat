@echo off
setlocal
cd /d "%~dp0"
call "%~dp0CHECK_V17T2R6_8760_JULIA_STATIC.bat"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R6R7_HF2P1_PATCH.bat"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R6_8760_PARALLEL_SCHEDULER.bat"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R6_8760_PACKAGE.bat"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R6_8760_RUNTIME.bat"
if errorlevel 1 exit /b 1
call "%~dp0CHECK_V17T2R6_8760_SOURCE_GATE.bat" --stage cases
if errorlevel 1 exit /b 1
echo V17T2R6R7-HF2P2 full-8760 preflight PASSED; solver-certified rerun still required.
exit /b 0
