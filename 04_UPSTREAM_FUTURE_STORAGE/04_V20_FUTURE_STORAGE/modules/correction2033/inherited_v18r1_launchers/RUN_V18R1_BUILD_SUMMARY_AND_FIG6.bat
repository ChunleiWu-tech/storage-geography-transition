@echo off
setlocal
cd /d "%~dp0"
call "%~dp0V18R1_ENV_DEFAULTS.bat"
%V18R1_PYTHON% "tools\publication_source_gate.py" --stage results
if errorlevel 1 exit /b %errorlevel%
%V18R1_PYTHON% "tools\write_future_correction_result_lineage.py"
if errorlevel 1 exit /b %errorlevel%
%V18R1_PYTHON% "tools\build_future_correction_summary.py"
if errorlevel 1 exit /b %errorlevel%
%V18R1_PYTHON% "postprocess\plot_future_correction_main_figure.py"
exit /b %errorlevel%
