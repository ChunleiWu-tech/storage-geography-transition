@echo off
setlocal
cd /d "%~dp0"
call V20_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
set "V17_SOLVER_THREADS=10"

echo ============================================================
echo V20-HF4 RESUME: retain strict existing outputs; solve missing only
echo Expected starting point from current run: 11/26 strict, 15 remaining
echo ============================================================
call CHECK_V20_HF4_PATCH.bat
if errorlevel 1 exit /b 1

set "HF4_RC_A=0"
set "HF4_RC_B=0"
set "HF4_RC_C=0"

echo === Layer A: retain FC01-FC07; resume FC08 with exact projection ===
pushd "modules\correction2033"
call V18R1_ENV_DEFAULTS.bat
if errorlevel 1 (popd & exit /b 1)
%V18R1_PYTHON% "tools\run_v20_hf4_fc08_resume.py" "%V18R1_JULIA%"
set "HF4_RC_A=%ERRORLEVEL%"
popd

echo === Layer B: retain strict __main outputs; run remaining serially ===
%V17_PYTHON% "tools\run_v20_hf4_layer_b16_resume.py"
set "HF4_RC_B=%ERRORLEVEL%"

echo === Layer C: validate/retain the completed equal-horizon pair ===
%V17_PYTHON% "tools\run_v20_equal_horizon_pair.py"
set "HF4_RC_C=%ERRORLEVEL%"

echo === V20-HF4 strict 26-case progress ===
%V17_PYTHON% "tools\check_v20_hf4_progress.py"
set "HF4_RC_FINAL=%ERRORLEVEL%"

if not "%HF4_RC_A%"=="0" echo WARNING: Layer A remains incomplete. See modules\correction2033\future_correction_batch_logs.
if not "%HF4_RC_B%"=="0" echo WARNING: Layer B remains incomplete. See batch_logs and audits\v20.
if not "%HF4_RC_C%"=="0" echo WARNING: Layer C validation failed.
if not "%HF4_RC_FINAL%"=="0" exit /b 1
echo V20 REQUIRED 26: STRICT PASS
exit /b 0
