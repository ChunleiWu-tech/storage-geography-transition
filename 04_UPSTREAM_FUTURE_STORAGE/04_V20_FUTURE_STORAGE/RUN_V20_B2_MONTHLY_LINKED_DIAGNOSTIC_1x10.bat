@echo off
setlocal
cd /d "%~dp0"
echo NOTE: This compatibility entry now runs the broader HF2 feasibility-isolation diagnostic.
call RUN_V20_B2_FEASIBILITY_ISOLATION_DIAGNOSTIC_1x10.bat
exit /b %errorlevel%
