#!/usr/bin/env python3
"""Fail-closed static and integrity audit for R12-HF7."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "base_model_v39" / "full8760_hf4_objective_continuation.jl"
CORE = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"
RUNNER = ROOT / "tools" / "run_targetyear_batch.py"
COORDINATOR = ROOT / "tools" / "run_hf7_unresolved_three_parallel.py"
LAUNCHER = ROOT / "RUN_V17T2R6R12_HF7_8760_UNRESOLVED_3X15.bat"
PREFLIGHT = ROOT / "CHECK_V17T2R6R12_HF7_8760.bat"
NOTES = ROOT / "RELEASE_NOTES_V17T2R6R12_HF7_RESTRICTED_FACE.md"
MANIFEST = ROOT / "HF7_PATCH_MANIFEST_SHA256.json"
OUT = ROOT / "audits" / "V17T2R6R12_HF7_RESTRICTED_FACE_AUDIT.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(text: str, tokens: tuple[str, ...], label: str, errors: list[str]) -> None:
    for token in tokens:
        if token not in text:
            errors.append(f"{label}: missing token: {token}")


def main() -> int:
    errors: list[str] = []
    required_files = (HELPER, CORE, RUNNER, COORDINATOR, LAUNCHER, PREFLIGHT, NOTES, MANIFEST)
    for path in required_files:
        if not path.is_file():
            errors.append(f"missing HF7 file: {path.relative_to(ROOT)}")
    if errors:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"version": "V17T2R6R12_HF7", "status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("V17T2R6R12-HF7 audit: FAIL")
        print("\n".join(errors))
        return 1

    helper, core, runner, coordinator, launcher, preflight = (
        p.read_text(encoding="utf-8") for p in (HELPER, CORE, RUNNER, COORDINATOR, LAUNCHER, PREFLIGHT)
    )
    for path, text in ((RUNNER, runner), (COORDINATOR, coordinator), (Path(__file__), Path(__file__).read_text(encoding="utf-8"))):
        try:
            ast.parse(text)
        except SyntaxError as exc:
            errors.append(f"Python syntax error in {path.name}: {exc}")

    require(helper, (
        "function _v17t2r6r12_run_hf7_restricted_face_setup!",
        '"TY2033_FULL8760_OPTIMAL" => "TY2033_FULL8760_OBSERVED"',
        '"TY2033_FULL8760_LDES_OBSERVED" => "TY2033_FULL8760_LDES_OBSERVED"',
        '"TY2033_FULL8760_LDES_OPTIMAL" => "TY2033_FULL8760_LDES_OBSERVED"',
        "JuMP.fix(release_vars[i], release_seed_values[i]; force=true)",
        "zeros(Float64, length(ldes_power_vars))",
        "zeros(Float64, length(ldes_energy_vars))",
        "seed_ldes_zero_values_pass",
        "JuMP.unfix(v)",
        "JuMP.set_lower_bound(v, bounds.lower)",
        "JuMP.set_upper_bound(v, bounds.upper)",
        "support_objective = release_original_objective .- release_reduced_cost",
        "function _v17t2r6r12_hf7_apply_complete_basis!",
        "function _v17t2r6r12_hf7_apply_restricted_basis_profile!",
        "function _v17t2r6r12_hf7_apply_bound_release_profile!",
        "restricted_starts = _v17t2r6r9_hf4_apply_dual_start_only!",
        "ldes_release_stage, current_vbasis, current_cbasis = release_stage!",
        "legacy_release_stage, current_vbasis, current_cbasis = release_stage!",
        "seed_ldes_zero_equals_original_lower_pass",
        "staged_release_order_pass",
        "stage_objective = release_original_objective .- (1.0 - theta) .* release_reduced_cost",
        '"Obj", release_columns, release_original_objective',
        "final_objective_restored",
        "restricted_basis_then_zero_ldes_then_legacy_dual_simplex_no_crossover",
        "method=1, crossover=0, crossover_basis=-1, numeric_focus=3",
        "lp_warm_start=2",
        "lp_warm_start=1",
        "primal_submitted_count=0",
    ), "helper", errors)
    start = helper.find("function _v17t2r6r12_run_hf7_restricted_face_setup!")
    stop = helper.find("function _v17t2r6r9_hf4_safe_gurobi_model_float", start)
    hf7_body = helper[start:stop]
    for forbidden in ("@constraint", "GRBchgcoeffs", "set_normalized_coefficient", "NormalizedRHS", "set_objective"):
        if forbidden in hf7_body:
            errors.append(f"HF7 helper changes forbidden model structure: {forbidden}")
    if '_v17t2r6r9_hf4_set_double_array!(grb, "PStart"' in hf7_body:
        errors.append("HF7 helper submits PStart")

    require(core, (
        'String(solver_profile) == "full8760_restricted_face_continuation"',
        '"TY2033_FULL8760_LDES_OBSERVED"',
        "LDES_POWER_BLD_YRS =",
        "LDES_ENERGY_BLD_YRS =",
        "_v17t2r6r12_run_hf7_restricted_face_setup!",
        "legacy_reallocation_active=LEGACY_OPTIMIZED_REALLOCATION",
        "hf4_state.release_legacy_count == expected_hf7_legacy_release_count",
        "hf4_state.release_ldes_power_count == expected_hf7_ldes_power_count",
        "hf4_state.release_ldes_energy_count == expected_hf7_ldes_energy_count",
        "hf4_state.support_objective_adjustment_count == expected_hf7_release_count",
        "hf4_state.restricted_basis_strict_optimal",
        "hf4_state.restricted_basis_lpwarmstart == 2",
        "hf4_state.staged_release_order_pass",
        "hf4_state.final_objective_restored_count == expected_hf7_release_count",
        "gurobi_V17T2R6R12_HF7_full8760_original_objective_optimal_after_restricted_face_continuation",
        ":hf4_seed_restricted_face_pass",
        ":hf4_seed_ldes_zero_values_pass",
        ":hf4_seed_ldes_zero_equals_original_lower_pass",
        ":hf4_restricted_basis_strict_optimal",
        ":hf4_ldes_release_stage_strict_optimal",
        ":hf4_legacy_release_stage_strict_optimal",
        ":hf4_staged_release_order_pass",
        ":hf4_release_total_count",
        "const SOLVER_FEASIBILITY_TOL = 1.0e-7",
        "const SOLVER_OPTIMALITY_TOL = 1.0e-7",
        "const SOLVER_BAR_CONV_TOL = 1.0e-8",
    ), "core", errors)

    require(runner, (
        "HF7_RESTRICTED_FACE_ROUTES",
        '"hf7_restricted_face": HF7_RESTRICTED_FACE_ROUTES',
        "__07_full8760_hf7_restricted_face_continuation",
        "full8760_restricted_face_continuation",
        "V17T2R6R12_HF7_full8760_restricted_face_exact_objective_continuation",
        "HF7 LDES zero-face seed was not requested",
        "HF7 restricted-basis DStart submitted count does not match raw rows",
        "HF7 LDES release stage was not strict optimal",
        "HF7 optimized legacy release stage was not strict optimal",
        "HF7 unexpectedly submitted PStart",
        "gurobi_V17T2R6R12_HF7_full8760_original_objective_optimal_after_restricted_face_continuation",
    ), "runner", errors)
    require(coordinator, (
        '"TY2033_FULL8760_OPTIMAL"',
        '"TY2033_FULL8760_LDES_OBSERVED"',
        '"TY2033_FULL8760_LDES_OPTIMAL"',
        "ThreadPoolExecutor(max_workers=3",
        "batch.HF7_RESTRICTED_FACE_ROUTES",
        '"force_rerun": False',
        "wait only; never delete or steal an active lease",
    ), "coordinator", errors)
    if coordinator.count('"TY2033_FULL8760_') != 3:
        errors.append("coordinator target scope is not exactly three scenarios")
    require(launcher, (
        'set "V17_SOLVER_THREADS=15"',
        'set "V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS=129600"',
        'set "V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS=86400"',
        "run_hf7_unresolved_three_parallel.py",
        "3 independent x 15 threads",
    ), "launcher", errors)
    require(preflight, (
        "Meta.parseall",
        "full8760_hf4_objective_continuation.jl",
        "cheer_power_storage_targetyear_v17t2r6_8760.jl",
        "audit_targetyear_pair_identity.py",
        "check_julia_8760_static.py",
        "check_v17t2r6r12_hf7_restricted_face.py",
    ), "preflight", errors)
    for forbidden in ("--force-rerun", "--clean-central", "rmdir", "remove-item", "finalize"):
        if forbidden in launcher.lower():
            errors.append(f"launcher contains destructive/scope-expanding token: {forbidden}")

    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        entries = manifest.get("files", [])
        if len(entries) < 8:
            errors.append("HF7 manifest covers fewer than eight payload files")
        for entry in entries:
            path = ROOT / entry["path"]
            if not path.is_file():
                errors.append(f"manifest file missing: {entry['path']}")
            elif sha256(path).lower() != str(entry["sha256"]).lower():
                errors.append(f"manifest hash mismatch: {entry['path']}")
    except Exception as exc:
        errors.append(f"HF7 manifest unreadable: {exc}")

    payload = {
        "version": "V17T2R6R12_HF7_RESTRICTED_FACE",
        "status": "PASS" if not errors else "FAIL",
        "scientific_change": False,
        "target_count": 3,
        "target_model_matrix_changed": False,
        "target_rhs_changed": False,
        "final_bounds_restored_exactly_required": True,
        "final_objective_restored_exactly_required": True,
        "strict_native_optimal_required_at_every_stage": True,
        "errors": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"V17T2R6R12-HF7 audit: {payload['status']}")
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
