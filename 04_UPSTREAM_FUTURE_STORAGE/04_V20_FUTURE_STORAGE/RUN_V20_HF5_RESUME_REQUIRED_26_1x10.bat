@echo off
setlocal
cd /d "%~dp0"
call V20_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
set "V17_SOLVER_THREADS=10"

if /I "%V20_HF5_ALLOW_OTHER_JULIA%"=="1" goto :julia_guard_done
powershell -NoProfile -Command "if (Get-Process julia -ErrorAction SilentlyContinue) { exit 9 } else { exit 0 }"
if errorlevel 1 (
  echo ERROR: Julia is already running. If those jobs use other package/output directories,
  echo set V20_HF5_ALLOW_OTHER_JULIA=1 and run this launcher again.
  exit /b 9
)
:julia_guard_done

echo ============================================================
echo V20-HF5: retain every strict __main result; solve missing only
echo Exact reduced formulation; one uninterrupted Barrier per case
echo ============================================================
call CHECK_V20_HF5_PATCH.bat
if errorlevel 1 exit /b 1

set "HF5_RC_A=0"
set "HF5_RC_B=0"
set "HF5_RC_C=0"

echo === Layer A: retain FC01-FC07; solve FC08 if still missing ===
pushd "modules\correction2033"
call V18R1_ENV_DEFAULTS.bat
if errorlevel 1 (popd & exit /b 1)
%V18R1_PYTHON% "tools\run_v20_hf4_fc08_resume.py" "%V18R1_JULIA%"
set "HF5_RC_A=%ERRORLEVEL%"
popd

echo === Layer B: retain strict __main outputs; solve missing serially ===
%V17_PYTHON% "tools\run_v20_hf4_layer_b16_resume.py"
set "HF5_RC_B=%ERRORLEVEL%"

echo === Layer C: validate and retain the completed equal-horizon pair ===
%V17_PYTHON% "tools\run_v20_equal_horizon_pair.py"
set "HF5_RC_C=%ERRORLEVEL%"

echo === V20-HF5 strict 26-case progress ===
%V17_PYTHON% "tools\check_v20_hf5_progress.py"
set "HF5_RC_FINAL=%ERRORLEVEL%"

if not "%HF5_RC_A%"=="0" echo WARNING: Layer A remains incomplete. See modules\correction2033\future_correction_batch_logs.
if not "%HF5_RC_B%"=="0" echo WARNING: Layer B remains incomplete. See batch_logs and audits\v20.
if not "%HF5_RC_C%"=="0" echo WARNING: Layer C validation failed.
if not "%HF5_RC_FINAL%"=="0" exit /b 1
echo V20 REQUIRED 26: STRICT PASS
exit /b 0
