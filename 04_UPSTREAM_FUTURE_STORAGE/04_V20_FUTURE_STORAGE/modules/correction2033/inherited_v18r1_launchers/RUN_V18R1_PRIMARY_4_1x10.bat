@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V18R1_ENV_DEFAULTS.bat"
%V18R1_PYTHON% "tools\publication_source_gate.py" --stage cases
if errorlevel 1 exit /b %errorlevel%

echo === V18R1 primary pair 1/2: FC_BASE ===
%V18R1_PYTHON% "tools\run_future_correction_batch.py" --pair FC_BASE --route robust --skip-prepare --julia "%V18R1_JULIA%"
if errorlevel 1 exit /b %errorlevel%

echo === V18R1 primary pair 2/2: FC_ADAPTIVE ===
%V18R1_PYTHON% "tools\run_future_correction_batch.py" --pair FC_ADAPTIVE --route robust --skip-prepare --julia "%V18R1_JULIA%"
exit /b %errorlevel%
