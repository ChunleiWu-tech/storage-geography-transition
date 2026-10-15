@echo off
setlocal
cd /d "%~dp0"
call CHECK_V20_RUNTIME.bat
if errorlevel 1 exit /b %errorlevel%
call PREP_V20.bat
if errorlevel 1 exit /b %errorlevel%
call RUN_V20_PHASE1_CORE_8_1x10.bat
if errorlevel 1 exit /b %errorlevel%
call RUN_V20_REMAINING_18_1x10.bat
if errorlevel 1 exit /b %errorlevel%
echo ============================================================
echo V20 REQUIRED 26 SOLVES COMPLETED THROUGH ALL STRICT GATES.
echo Next: BUILD_V20_RESULTS.bat
echo ============================================================
exit /b 0
