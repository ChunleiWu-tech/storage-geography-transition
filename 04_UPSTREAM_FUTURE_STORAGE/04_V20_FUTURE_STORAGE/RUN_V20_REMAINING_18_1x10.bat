@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo V20 RUN-FIRST PHASE 2: complete required set resume-safely
echo Layer A full 8 and Layer B full 16; valid Phase-1 cases skip.
echo ============================================================
call RUN_V20_A8_1x10.bat
if errorlevel 1 exit /b %errorlevel%
call RUN_V20_B16_1x10.bat
if errorlevel 1 exit /b %errorlevel%
call RUN_V20_C2_EQUAL_HORIZON_1x10.bat
if errorlevel 1 exit /b %errorlevel%
echo V20 REQUIRED 26: STRICT PASS
exit /b 0
