@echo off
setlocal
cd /d "%~dp0"
call V20_ENV_DEFAULTS.bat
if errorlevel 1 exit /b 1
set "PYTHONDONTWRITEBYTECODE=1"

echo === V20 root publication source/case gate ===
%V17_PYTHON% "tools\publication_source_gate.py" --stage cases
if errorlevel 1 exit /b 1


echo === Frozen V17 scientific-input and solver-contract audits ===
%V17_PYTHON% "tools\validate_storage_inputs.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\check_v17_ne_config.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_julia_empty_collection_safety.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_numerical_stability_v17.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_objective_certificate_v17.py"
if errorlevel 1 exit /b 1
%V17_PYTHON% "tools\audit_v17_release_policy.py"
if errorlevel 1 exit /b 1

echo === V20 Layer A publication source/case gate ===
pushd "modules\correction2033"
%V17_PYTHON% "tools\publication_source_gate.py" --stage cases
if errorlevel 1 (set RC=%ERRORLEVEL%& popd & exit /b %RC%)
%V17_PYTHON% "tools\audit_future_correction_pair_identity.py"
set RC=%ERRORLEVEL%
popd
if not "%RC%"=="0" exit /b %RC%

echo === V20 evidence / equal-horizon / portability audit ===
%V17_PYTHON% "tools\check_v20_package.py"
if errorlevel 1 exit /b 1

echo ============================================================
echo V20 STATIC + SOURCE + MATCHED-PAIR + EVIDENCE GATE: PASS
echo This does NOT certify Julia/Gurobi numerical results.
echo ============================================================
exit /b 0
