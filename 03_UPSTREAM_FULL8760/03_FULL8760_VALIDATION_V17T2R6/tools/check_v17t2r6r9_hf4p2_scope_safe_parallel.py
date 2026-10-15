#!/usr/bin/env python3
"""Fail-closed audit for the HF4P2 scope-safe 3x15 companion."""
from __future__ import annotations

from pathlib import Path
import ast
import hashlib
import json
import re


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"
HELPER = ROOT / "base_model_v39" / "full8760_hf4_objective_continuation.jl"
RUNNER = ROOT / "tools" / "run_targetyear_batch.py"
COMPANION = ROOT / "tools" / "run_hf4p2_remaining_three_parallel.py"
LAUNCHER = ROOT / "RUN_V17T2R6R9_HF4P2_8760_REMAINING_3X15.bat"
MANIFEST = ROOT / "HF4P2_PATCH_MANIFEST_SHA256.json"
OUT = ROOT / "audits" / "V17T2R6R9_HF4P2_SCOPE_SAFE_PARALLEL_AUDIT.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: object) -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    model = MODEL.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    companion = COMPANION.read_text(encoding="utf-8")
    launcher = LAUNCHER.read_text(encoding="utf-8")

    syntax_errors: list[str] = []
    for path in (RUNNER, COMPANION, Path(__file__)):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_errors.append(f"{path.name}: {exc}")
    add("python_syntax", not syntax_errors, syntax_errors)

    required_scope_helpers = [
        "function _v17t2r6r9_hf4_safe_solve_float(f)",
        "function _v17t2r6r9_hf4_safe_gurobi_model_float(mod, attribute_name::AbstractString)",
        "function _v17t2r6r9_hf4_safe_gurobi_model_int(mod, attribute_name::AbstractString)",
        "function _v17t2r6r9_hf4_safe_result_count(mod)",
        "return Int(result_count(mod))",
    ]
    missing_scope_helpers = [token for token in required_scope_helpers if token not in helper]
    unresolved_legacy_helpers = re.findall(
        r"(?<!v17t2r6r9_hf4)_safe_(?:solve_float|gurobi_model_float|gurobi_model_int|result_count)",
        helper,
    )
    add(
        "hf4_postsolve_helpers_are_file_scoped_and_resolved",
        not missing_scope_helpers and not unresolved_legacy_helpers,
        {"missing": missing_scope_helpers, "unresolved": unresolved_legacy_helpers},
    )

    invariant_model_tokens = [
        "const SOLVER_FEASIBILITY_TOL = 1.0e-7",
        "const SOLVER_OPTIMALITY_TOL = 1.0e-7",
        "const SOLVER_BAR_CONV_TOL = 1.0e-8",
        "const ECONOMIC_OBJECTIVE_SCALE_USD = 1.0e6",
        "LEGACY_ENERGY_VARIABLE_PROJECTION_ACTIVE = LEGACY_OPTIMIZED_REALLOCATION",
        'include(joinpath(@__DIR__, "full8760_hf4_objective_continuation.jl"))',
    ]
    missing_model = [token for token in invariant_model_tokens if token not in model]
    add("frozen_scientific_model_contract_retained", not missing_model, missing_model)

    forbidden_helper = [
        'GRBsetdblattrlist(grb, "RHS"',
        'GRBsetdblattrarray(grb, "RHS"',
        'GRBsetcharattrarray(grb, "Sense"',
        "set_normalized_rhs(",
        "set_normalized_coefficient(",
        "delete(mod,",
    ]
    helper_forbidden_hits = [token for token in forbidden_helper if token in helper]
    add("no_matrix_rhs_or_constraint_intervention", not helper_forbidden_hits, helper_forbidden_hits)

    companion_required = [
        '"TY2033_FULL8760_OPTIMAL": batch.HF4_CONTINUATION_ROUTES',
        '"TY2033_FULL8760_LDES_OBSERVED": batch.HF3_PROJECTED_ROUTES',
        '"TY2033_FULL8760_LDES_OPTIMAL": batch.HF4_CONTINUATION_ROUTES',
        "ThreadPoolExecutor(max_workers=3",
        "configured_threads != 15",
        "pool.submit(batch.run_one",
        "merge_summary(records)",
        "os.replace(csv_temp, batch.SUMMARY_CSV)",
        "os.replace(json_temp, batch.SUMMARY_JSON)",
        'all(record["publication_strict_success"] for record in records)',
    ]
    missing_companion = [token for token in companion_required if token not in companion]
    forbidden_companion = ["force_rerun=True", "--force-rerun", "--clean-central", "shutil.rmtree(batch.CENTRAL"]
    companion_forbidden_hits = [token for token in forbidden_companion if token in companion]
    add(
        "three_case_distinct_route_coordinator_and_resume_safety",
        not missing_companion and not companion_forbidden_hits,
        {"missing": missing_companion, "forbidden": companion_forbidden_hits},
    )

    launcher_required = [
        'set "V17_SOLVER_THREADS=15"',
        'set "V17T2R6_SCENARIO_LOCK_WAIT_SECONDS=604800"',
        'set "V17T2R6_SCENARIO_LOCK_POLL_SECONDS=20"',
        '"tools\\run_hf4p2_remaining_three_parallel.py"',
        "3 x 15 threads",
        "no scientific input is modified",
        'call "%~dp0FINALIZE_V17T2R6_8760_RESULTS.bat"',
    ]
    launcher_forbidden = ["Stop-Process", "taskkill", "--force-rerun", "--clean-central", "rmdir ", "Remove-Item"]
    missing_launcher = [token for token in launcher_required if token not in launcher]
    launcher_forbidden_hits = [token for token in launcher_forbidden if token in launcher]
    add(
        "launcher_is_exactly_3x15_and_non_destructive",
        not missing_launcher and not launcher_forbidden_hits,
        {"missing": missing_launcher, "forbidden": launcher_forbidden_hits},
    )

    lease_tokens = [
        'RUN_LOCKS = ROOT / "run_locks"',
        "def acquire_scenario_lease(",
        "lease.mkdir()",
        "def release_scenario_lease(",
        "finally:\n        release_scenario_lease(lease)",
    ]
    missing_lease = [token for token in lease_tokens if token not in runner]
    add("per_scenario_lease_contract_retained", not missing_lease, missing_lease)

    manifest_errors: list[str] = []
    if not MANIFEST.is_file():
        manifest_errors.append("HF4P2 patch manifest missing")
    else:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for item in manifest.get("files", []):
            path = ROOT / str(item["path"])
            if not path.is_file():
                manifest_errors.append(f"missing {item['path']}")
            elif path.stat().st_size != int(item["bytes"]):
                manifest_errors.append(f"size {item['path']}")
            elif sha256(path) != str(item["sha256"]):
                manifest_errors.append(f"sha256 {item['path']}")
    add("hf4p2_patch_files_match_manifest", not manifest_errors, manifest_errors)

    result = {
        "version": "V17T2R6R9_HF4P2_SCOPE_SAFE_3X15",
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "scope": "HF4 scope repair and operational 3x15 scheduling; scientific inputs, matrix, RHS, final bounds, final objective and strict gates unchanged",
        "scientific_change": False,
        "max_parallel_new_cases": 3,
        "solver_threads_per_new_case": 15,
        "checks": checks,
        "failed": [item["check"] for item in checks if not item["pass"]],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
