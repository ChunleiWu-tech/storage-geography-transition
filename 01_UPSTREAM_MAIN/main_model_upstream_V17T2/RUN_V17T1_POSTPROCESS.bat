@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
if exist "postprocess_outputs" rmdir /s /q "postprocess_outputs"
%V17_PYTHON% "postprocess\preflight_spatial_legacy_outputs.py" --scenario-set spatial_legacy_full
if errorlevel 1 exit /b 1
%V17_PYTHON% "postprocess\build_spatial_legacy_tables.py" --scenario-set spatial_legacy_full
if errorlevel 1 exit /b 1
%V17_PYTHON% "postprocess\plot_spatial_legacy_figures.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "postprocess\validate_spatial_legacy_release.py" --scenario-set spatial_legacy_full
if errorlevel 1 exit /b 1
echo V17T1 strict postprocessing PASSED.
endlocal
