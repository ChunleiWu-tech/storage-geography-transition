#!/usr/bin/env python3
"""Fail-closed static/integrity audit for the R11-HF6 numerical bridge."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "base_model_v39" / "full8760_hf4_objective_continuation.jl"
CORE = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"
RUNNER = ROOT / "tools" / "run_targetyear_batch.py"
COORDINATOR = ROOT / "tools" / "run_hf6_optimized_pair_parallel.py"
LAUNCHER = ROOT / "RUN_V17T2R6R11_HF6_8760_OPTIMIZED_PAIR_2X15.bat"
MANIFEST = ROOT / "HF6_PATCH_MANIFEST_SHA256.json"
OUT = ROOT / "audits" / "V17T2R6R11_HF6_DUAL_START_BRIDGE_AUDIT.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def required(text: str, tokens: tuple[str, ...], label: str, errors: list[str]) -> None:
    for token in tokens:
        if token not in text:
            errors.append(f"{label}: required token missing: {token}")


def balanced_julia(text: str, label: str, errors: list[str]) -> None:
    # A deliberately conservative structural check; Julia is parsed by the
    # existing check_julia_8760_static.py in the launcher's preflight.
    if not text.startswith("# V17T2R6R11-HF6 numerical continuation"):
        errors.append(f"{label}: HF6 continuation header is absent")
    if len(re.findall(r"^function\s+", text, flags=re.M)) < 10:
        errors.append(f"{label}: continuation helper has unexpectedly few functions")


def main() -> int:
    errors: list[str] = []
    for path in (HELPER, CORE, RUNNER, COORDINATOR, LAUNCHER, MANIFEST):
        if not path.is_file():
            errors.append(f"missing required HF6 file: {path.relative_to(ROOT)}")
    if errors:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"version": "V17T2R6R11_HF6", "status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("V17T2R6R11-HF6 audit: FAIL")
        print("\n".join(errors))
        return 1

    helper, core, runner, coordinator, launcher = (p.read_text(encoding="utf-8") for p in (HELPER, CORE, RUNNER, COORDINATOR, LAUNCHER))
    balanced_julia(helper, "helper", errors)
    try:
        ast.parse(runner)
        ast.parse(coordinator)
    except SyntaxError as exc:
        errors.append(f"Python syntax error: {exc}")

    required(helper, (
        "function _v17t2r6r9_hf4_apply_dual_start_only!",
        '"DStart"',
        "primal_submitted_count=0",
        "primal_not_submitted_by_design=true",
        "method=1, crossover=0, crossover_basis=-1, numeric_focus=3",
        "scale_flag=2, presolve=0, aggregate=0, pre_sparsify=0, quad=1",
        "lp_warm_start=1",
        "dual_simplex_unpresolved_dstart_only_no_crossover",
        "legacy_original_objective .- legacy_reduced_cost",
        "final_objective_restored_count=length(legacy_columns)",
        "final_max_objective_coefficient_error=max_objective_error",
        "V17T2R6R9_HF4_OBJECTIVE_HOMOTOPY_LEVELS",
    ), "helper", errors)
    if "_v17t2r6r9_hf4_apply_primal_dual_start!" in helper:
        errors.append("helper retains the obsolete HF5 primal/dual-start submission function")
    if re.search(r'_v17t2r6r9_hf4_set_double_array!\(grb, "PStart"', helper):
        errors.append("helper submits PStart; HF6 permits DStart only")

    required(core, (
        "V17T2R6R11_HF6_full8760_dual_start_only_dual_simplex_no_crossover_exact_objective_continuation",
        "bridge_dual_start_only_set_pass",
        "bridge_primal_start_not_submitted_by_design",
        "bridge_primal_start_submitted_count == 0",
        "bridge_method == 1",
        "bridge_lpwarmstart == 1",
        "bridge_presolve == 0",
        "gurobi_V17T2R6R11_HF6_full8760_original_objective_optimal_after_dual_start_only_no_crossover_dual_simplex_basis_continuation",
        ":hf4_bridge_dual_start_only_set_pass",
    ), "core", errors)
    required(runner, (
        "HF6_DUAL_SIMPLEX_BRIDGE_ROUTES",
        '"hf6_dual_simplex_bridge": HF6_DUAL_SIMPLEX_BRIDGE_ROUTES',
        "HF6 bridge method is not dual simplex (1)",
        "HF6 unexpectedly submitted PStart",
        "gurobi_V17T2R6R11_HF6_full8760_original_objective_optimal_after_dual_start_only_no_crossover_dual_simplex_basis_continuation",
    ), "runner", errors)
    required(coordinator, (
        "TY2033_FULL8760_OPTIMAL", "TY2033_FULL8760_LDES_OPTIMAL",
        "batch.HF6_DUAL_SIMPLEX_BRIDGE_ROUTES", "ThreadPoolExecutor(max_workers=2",
        "ldes_observed_changed\": False", "wait only; never remove or steal an active lease",
    ), "coordinator", errors)
    if "TY2033_FULL8760_OBSERVED" in coordinator or "TY2033_FULL8760_LDES_OBSERVED" in coordinator:
        errors.append("coordinator target scope contains an OBSERVED scenario")
    required(launcher, (
        'set "V17_SOLVER_THREADS=15"',
        "run_hf6_optimized_pair_parallel.py",
        "TY2033_FULL8760_LDES_OBSERVED are not altered",
    ), "launcher", errors)
    for forbidden in ("--force-rerun", "--clean-central", "rmdir", "Remove-Item", "FINALIZE"):
        if forbidden.lower() in launcher.lower():
            errors.append(f"launcher contains forbidden scope-expanding token: {forbidden}")

    manifest_errors: list[str] = []
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for entry in manifest.get("files", []):
            path = ROOT / entry["path"]
            if not path.is_file():
                manifest_errors.append(f"manifest file absent: {entry['path']}")
            elif digest(path).lower() != str(entry["sha256"]).lower():
                manifest_errors.append(f"manifest hash mismatch: {entry['path']}")
    except Exception as exc:
        manifest_errors.append(f"manifest unreadable: {exc}")
    if not manifest_errors and len(manifest.get("files", [])) < 7:
        manifest_errors.append("manifest covers fewer than seven HF6 payload files")
    errors.extend(manifest_errors)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "V17T2R6R11_HF6_DUAL_START_BRIDGE",
        "status": "PASS" if not errors else "FAIL",
        "scientific_change": False,
        "bridge": {
            "method": "dual simplex (1)", "warm_start": "DStart only", "lpwarmstart": 1,
            "presolve": 0, "crossover": 0, "pstart_submitted": False,
        },
        "checked_files": [str(p.relative_to(ROOT)) for p in (HELPER, CORE, RUNNER, COORDINATOR, LAUNCHER, MANIFEST)],
        "errors": errors,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"V17T2R6R11-HF6 audit: {payload['status']}")
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
