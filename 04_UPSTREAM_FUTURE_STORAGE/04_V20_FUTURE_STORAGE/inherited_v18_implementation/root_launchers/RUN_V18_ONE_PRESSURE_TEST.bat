@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: RUN_V18_ONE_PRESSURE_TEST.bat SCENARIO_ID
  exit /b 2
)
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
call CHECK_V17_RUNTIME.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\prepare_storage_cases.py" --scenario "%~1" --reuse-base
if errorlevel 1 exit /b 1
"%JULIA_EXE%" "storage_runner\run_storage_one_solver_task.jl" --scenario "%~1" --solver_profile scaled_barrier --cleanup_profile stage1_official_release --solver_output_suffix __v18_pressure_test --storage_chronology_mode monthly_linked --v18_storage_portfolio_mode full_pressure_test
if errorlevel 1 exit /b 1
echo.
echo V18 PRESSURE TEST SOLVE COMPLETED: %~1
echo Output suffix: __v18_pressure_test
echo CAES/H2 results are diagnostic pressure-test evidence only and are excluded from headline V18 certification.
endlocal
exit /b 0
