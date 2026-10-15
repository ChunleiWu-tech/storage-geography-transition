@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo V20-HF3 targeted retest after HF2 Layer-B feasibility failure
echo B dynamic core 2 + C equal-evidence-horizon 2
echo No Layer-A rerun in this targeted retest.
echo ============================================================
call CHECK_V20_RUNTIME.bat
if errorlevel 1 exit /b %errorlevel%
call RUN_V20_B2_CORE_1x10.bat
if errorlevel 1 exit /b %errorlevel%
call RUN_V20_C2_EQUAL_HORIZON_1x10.bat
if errorlevel 1 exit /b %errorlevel%
echo V20-HF3 B2+C2 TARGETED RETEST: STRICT PASS
exit /b 0
