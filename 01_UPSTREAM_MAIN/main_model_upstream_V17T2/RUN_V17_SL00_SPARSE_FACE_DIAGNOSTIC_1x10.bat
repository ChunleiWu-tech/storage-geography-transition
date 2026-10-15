@echo off
setlocal
cd /d "%~dp0"
call V17_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
call CHECK_V17_RUNTIME.bat
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\build_storage_base_case.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\prepare_storage_cases.py" --scenario SL00_OBSERVED_ACTUAL
if errorlevel 1 exit /b 1
"%JULIA_EXE%" "storage_runner\run_storage_one_solver_task.jl" --scenario SL00_OBSERVED_ACTUAL --solver_profile scaled_barrier --cleanup_profile sparse_face_diagnostic_primal_pstart --solver_output_suffix __sparse_face_primal_diagnostic
set RC=%ERRORLEVEL%
echo Diagnostic-only output: storage_cases\SL00_OBSERVED_ACTUAL\outputs\SL00_OBSERVED_ACTUAL__sparse_face_primal_diagnostic
echo This sparse-face cleanup experiment is non-blocking and is never promoted to the official output directory.
exit /b %RC%
