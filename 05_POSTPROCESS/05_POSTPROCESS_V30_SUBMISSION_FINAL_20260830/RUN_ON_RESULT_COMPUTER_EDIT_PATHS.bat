@echo off
setlocal
rem Edit only these four paths if the result computer uses a different project root.
set "DESKTOP_ROOT=C:\Users\Admin\Desktop"
set "PROJECT_ROOT=%DESKTOP_ROOT%\01_UPSTREAM_16PLUS8"
set "MAIN_ROOT=%PROJECT_ROOT%\main_model_upstream_V17T2"
set "SENS_ROOT=%PROJECT_ROOT%\targetyear_sensitivity_upstream_V17T2R5"
set "FULL8760_ROOT=%PROJECT_ROOT%\03_FULL8760_VALIDATION_V17T2R6"
set "V20_ROOT=%PROJECT_ROOT%\04_V20_FUTURE_STORAGE"
echo Reading four upstream packages from: %PROJECT_ROOT%
call "%~dp0RUN_V30_POSTPROCESS.bat" "%MAIN_ROOT%" "%SENS_ROOT%" "%FULL8760_ROOT%" "%V20_ROOT%"
exit /b %errorlevel%
