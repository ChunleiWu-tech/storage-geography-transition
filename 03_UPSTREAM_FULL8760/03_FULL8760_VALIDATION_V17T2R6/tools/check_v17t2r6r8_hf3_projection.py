#!/usr/bin/env python3
"""Fail-closed scientific-invariance audit for V17T2R6R8-HF3."""
from __future__ import annotations

from pathlib import Path
import ast
import csv
import hashlib
import json
import math


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"
ORCHESTRATOR = ROOT / "tools" / "run_targetyear_batch.py"
SCENARIOS = ROOT / "storage_runner" / "scenarios_targetyear_linked.csv"
LAUNCHER = ROOT / "RUN_V17T2R6R8_HF3_8760_ALL4_SERIAL_RESUME.bat"
PATCH_MANIFEST = ROOT / "HF3_PATCH_MANIFEST_SHA256.json"
OUT = ROOT / "audits" / "V17T2R6R8_HF3_PROJECTION_AUDIT.json"
EXPECTED = {
    "TY2033_FULL8760_OBSERVED": "observed_standardized",
    "TY2033_FULL8760_OPTIMAL": "optimized_reallocation",
    "TY2033_FULL8760_LDES_OBSERVED": "observed_standardized",
    "TY2033_FULL8760_LDES_OPTIMAL": "optimized_reallocation",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def truth(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y", "t"}


def main() -> None:
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: object) -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    model = MODEL.read_text(encoding="utf-8")
    orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")
    launcher = LAUNCHER.read_text(encoding="utf-8")
    ast_errors: list[str] = []
    for path in (ORCHESTRATOR, Path(__file__)):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            ast_errors.append(f"{path.name}: {exc}")
    add("python_syntax", not ast_errors, ast_errors)

    required_projection_tokens = [
        "LEGACY_ENERGY_VARIABLE_PROJECTION_ACTIVE = LEGACY_OPTIMIZED_REALLOCATION",
        '"V17T2R6R8_HF3_equivalent_projected_legacy_allocation_v2"',
        "legacy_national_energy_implied_mwh = legacy_standardized_duration_h * legacy_national_power_target_mw",
        "legacy_national_energy_identity_residual_mwh = legacy_national_energy_target_mwh - legacy_national_energy_implied_mwh",
        "if !legacy_national_energy_identity_pass",
        "PROJECTED_LEGACY_STORAGE_ENERGY_BLD_YRS = Set(",
        "STORAGE_ENERGY_VARIABLE_BLD_YRS = [",
        "@variable(mod, BuildStorageEnergy[(g, bld_yr) in STORAGE_ENERGY_VARIABLE_BLD_YRS]",
        "function storage_energy_build(g, bld_yr)",
        "return legacy_standardized_duration_h * BuildGen[(g, bld_yr)]",
        "JuMP.set_upper_bound(power_var, min(current_power_ub, power_cap_mw))",
        "sum(BuildGen[(g, y)] for (g, y) in LEGACY_BATTERY_BLD_YRS; init=0.0) == legacy_national_power_target_mw",
        "storage_energy_targets[key] = sum(value(storage_energy_build(idx...)) for idx in idxs; init=0.0)",
        "sum(storage_energy_build(idx...) for idx in idxs; init=0.0) <= target + tol",
        "(g, p) => value(storage_energy_build(g, p)) for (g, p) in STORAGE_GEN_BLD_YRS",
        ":legacy_energy_variable_projection_count => [length(PROJECTED_LEGACY_STORAGE_ENERGY_BLD_YRS)]",
        ":legacy_projected_energy_output_reconstruction => [LEGACY_ENERGY_VARIABLE_PROJECTION_ACTIVE]",
    ]
    missing = [token for token in required_projection_tokens if token not in model]
    add("exact_projection_code_contract", not missing, missing)

    forbidden_dependent_rows = [
        "@constraint(mod, Legacy_Storage_National_Energy_Closure",
        "@constraint(mod, Legacy_Storage_Common_Duration",
        "@constraint(mod, Legacy_Storage_Zone_Deployment_Envelope",
    ]
    dependent_hits = [token for token in forbidden_dependent_rows if token in model]
    add("dependent_legacy_rows_not_emitted", not dependent_hits, dependent_hits)

    unsafe_energy_access = [
        "@variable(mod, BuildStorageEnergy[(g, bld_yr) in STORAGE_GEN_BLD_YRS]",
        "storage_energy_targets[key] = sum(value(BuildStorageEnergy[idx])",
        "sum(BuildStorageEnergy[idx] for idx in idxs",
        "val_BuildStorageEnergy = value.(BuildStorageEnergy)",
    ]
    unsafe_hits = [token for token in unsafe_energy_access if token in model]
    add("projected_energy_used_by_cleanup_and_exports", not unsafe_hits, unsafe_hits)

    numerical_contract = {
        "feasibility_tol": "const SOLVER_FEASIBILITY_TOL = 1.0e-7",
        "optimality_tol": "const SOLVER_OPTIMALITY_TOL = 1.0e-7",
        "barrier_convergence_tol": "const SOLVER_BAR_CONV_TOL = 1.0e-8",
        "objective_scale_usd": "const ECONOMIC_OBJECTIVE_SCALE_USD = 1.0e6",
        "method": "method = 2",
        "crossover": "crossover = 0",
        "primary_profile": 'profile == "targetyear_scaled_barrier_nocrossover"',
    }
    missing_numerical = [name for name, token in numerical_contract.items() if token not in model]
    add("solver_and_acceptance_contract_unchanged", not missing_numerical, missing_numerical)

    route_tokens = [
        '"hf3": HF3_PROJECTED_ROUTES',
        '"__03_full8760_hf3_projected_scaled_barrier"',
        '"03_full8760_hf3_projected_scaled_barrier"',
        "optimized legacy formulation is not the HF3 exact projection",
        "legacy_energy_variable_projection_count is not 32",
    ]
    missing_route = [token for token in route_tokens if token not in orchestrator]
    add("hf3_route_and_fail_closed_result_gate", not missing_route, missing_route)

    launcher_required = [
        'set "V17_SOLVER_THREADS=10"',
        'set "V17T2R6_MAX_PARALLEL=1"',
        'set "V17T2R6_8760_PRIMARY_TIME_LIMIT_SECONDS=129600"',
        "--pair ALL --route hf3 --skip-prepare --continue-after-failure --max-parallel 1",
        "Get-Process julia",
    ]
    launcher_forbidden = ["--route auto", "--max-parallel 2", "--clean-central", "--force-rerun"]
    missing_launcher = [token for token in launcher_required if token not in launcher]
    forbidden_launcher_hits = [token for token in launcher_forbidden if token in launcher]
    add(
        "serial_uninterrupted_primary_launcher",
        not missing_launcher and not forbidden_launcher_hits,
        {"missing": missing_launcher, "forbidden": forbidden_launcher_hits},
    )

    with SCENARIOS.open("r", encoding="utf-8-sig", newline="") as handle:
        scenario_rows = list(csv.DictReader(handle))
    scenario_modes = {row["scenario"]: row["legacy_allocation_mode"] for row in scenario_rows}
    add("four_case_registry_and_modes", scenario_modes == EXPECTED, scenario_modes)

    case_proof: dict[str, dict] = {}
    all_case_checks_pass = True
    all_source_fingerprints_pass = True
    checked_input_files = 0
    for scenario, expected_mode in EXPECTED.items():
        case = ROOT / "sensitivity_cases" / scenario
        policy_path = case / "inputs" / "legacy_storage_policy.csv"
        with policy_path.open("r", encoding="utf-8-sig", newline="") as handle:
            policy = list(csv.DictReader(handle))
        modes = {row["legacy_allocation_mode"] for row in policy}
        power = float(policy[0]["national_power_target_mw"])
        energy = float(policy[0]["national_energy_target_mwh"])
        duration = float(policy[0]["standardized_duration_h"])
        residual = energy - duration * power
        tolerance = max(1.0e-6, 1.0e-12 * max(1.0, abs(energy)))
        cap_sum = sum(float(row["legacy_power_cap_mw"]) for row in policy)
        passed = bool(
            len(policy) == 32
            and modes == {expected_mode}
            and math.isclose(power, 135930.0, rel_tol=0.0, abs_tol=1.0e-6)
            and math.isclose(energy, 351120.0, rel_tol=0.0, abs_tol=1.0e-6)
            and abs(residual) <= tolerance
            and cap_sum + 1.0e-6 >= power
        )
        all_case_checks_pass &= passed
        case_proof[scenario] = {
            "pass": passed,
            "rows": len(policy),
            "mode": sorted(modes),
            "national_power_target_mw": power,
            "national_energy_target_mwh": energy,
            "standardized_duration_h": duration,
            "identity_residual_mwh": residual,
            "identity_tolerance_mwh": tolerance,
            "zone_power_cap_sum_mw": cap_sum,
            "projection_expected": expected_mode == "optimized_reallocation",
        }

        fingerprint_path = case / "audits" / "CASE_PUBLICATION_SOURCE_FINGERPRINT.json"
        fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
        fingerprint_errors: list[str] = []
        for item in fingerprint.get("input_files", []):
            rel = str(item["path"])
            path = case / rel
            checked_input_files += 1
            if not path.is_file():
                fingerprint_errors.append(f"missing {rel}")
            elif path.stat().st_size != int(item["size_bytes"]):
                fingerprint_errors.append(f"size {rel}")
            elif sha256(path) != str(item["sha256"]):
                fingerprint_errors.append(f"sha256 {rel}")
        all_source_fingerprints_pass &= not fingerprint_errors
        case_proof[scenario]["source_fingerprint_errors"] = fingerprint_errors
    add("legacy_identity_and_envelope_proof_all_four", all_case_checks_pass, case_proof)
    add(
        "all_prepared_scientific_inputs_match_frozen_case_fingerprints",
        all_source_fingerprints_pass and checked_input_files > 0,
        {"checked_input_files": checked_input_files},
    )

    pair_audit_path = ROOT / "audits" / "V17T2R6_FULL8760_PAIR_IDENTITY_AUDIT.json"
    pair_audit = json.loads(pair_audit_path.read_text(encoding="utf-8")) if pair_audit_path.is_file() else {}
    add("matched_pair_identity_audit", pair_audit.get("status") == "PASS", pair_audit.get("status", "MISSING"))

    manifest_errors: list[str] = []
    if not PATCH_MANIFEST.is_file():
        manifest_errors.append("HF3 patch manifest missing")
    else:
        manifest = json.loads(PATCH_MANIFEST.read_text(encoding="utf-8"))
        for item in manifest.get("files", []):
            path = ROOT / str(item["path"])
            if not path.is_file():
                manifest_errors.append(f"missing {item['path']}")
            elif path.stat().st_size != int(item["bytes"]):
                manifest_errors.append(f"size {item['path']}")
            elif sha256(path) != str(item["sha256"]):
                manifest_errors.append(f"sha256 {item['path']}")
    add("hf3_patch_files_match_manifest", not manifest_errors, manifest_errors)

    result = {
        "version": "V17T2R6R8_HF3_FULL8760_EQUIVALENT_PROJECTION_SERIAL_PRIMARY",
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "scope": "static scientific-invariance, exact-projection, input-fingerprint, route and patch-integrity audit",
        "scientific_change": False,
        "projection_active_cases": [name for name, mode in EXPECTED.items() if mode == "optimized_reallocation"],
        "projection_inactive_cases": [name for name, mode in EXPECTED.items() if mode != "optimized_reallocation"],
        "checks": checks,
        "failed": [item["check"] for item in checks if not item["pass"]],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
