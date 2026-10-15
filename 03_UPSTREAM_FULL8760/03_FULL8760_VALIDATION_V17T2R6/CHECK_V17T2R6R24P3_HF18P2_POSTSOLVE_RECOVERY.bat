@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call "%~dp0V17T2R6_8760_ENV_DEFAULTS.bat"

set "V17_SOLVER_THREADS=10"
set "PYTHONDONTWRITEBYTECODE=1"
%V17T2R6_PYTHON% "tools\verify_hf18p2_r24p3_patch_manifest.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_v17t2r6r24p2_hf18p2_quality_recovery.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_v17t2r6r24p3_hf18p2_postsolve_recovery.py"
if errorlevel 1 exit /b 1
%V17T2R6_PYTHON% "tools\check_julia_delimiters.py"
if errorlevel 1 exit /b 1
echo V17T2R6R24P3-HF18P2 postsolve recovery preflight: PASS
exit /b 0

