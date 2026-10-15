@echo off
setlocal
cd /d "%~dp0"
call V20_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
set "V17_SOLVER_THREADS=10"
echo ============================================================
echo V20-HF2 OPTIONAL FEASIBILITY ISOLATION - NOT FOR PUBLICATION
echo 1) intraday_cyclic + portfolio disabled
echo 2) monthly_linked + portfolio disabled
echo 3) monthly_linked + evidence_bounded portfolio
echo Headline Layer B/C remains intraday_cyclic + evidence_bounded.
echo ============================================================
%V17_PYTHON% "tools\run_v20_chronology_isolation_diagnostics.py" --julia "%JULIA_EXE%"
exit /b %errorlevel%
