@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo V20 RUN-FIRST PHASE 1: 8 decisive cases
echo A primary 4 + B dynamic core 2 + C equal-horizon 2
echo ============================================================
call CHECK_V20_RUNTIME.bat
if errorlevel 1 exit /b %errorlevel%
call RUN_V20_A4_PRIMARY_1x10.bat
if errorlevel 1 exit /b %errorlevel%
call RUN_V20_B2_CORE_1x10.bat
if errorlevel 1 exit /b %errorlevel%
call RUN_V20_C2_EQUAL_HORIZON_1x10.bat
if errorlevel 1 exit /b %errorlevel%
echo V20 PHASE 1 CORE 8: STRICT PASS
exit /b 0
