#!/usr/bin/env python3
"""Fail-closed static, input and patch-integrity audit for R9-HF4."""
from __future__ import annotations

from pathlib import Path
import ast
import csv
import hashlib
import json
import math
import re


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"
HELPER = ROOT / "base_model_v39" / "full8760_hf4_objective_continuation.jl"
RUNNER = ROOT / "tools" / "run_targetyear_batch.py"
LAUNCHER = ROOT / "RUN_V17T2R6R9_HF4_8760_FINISH_MISSING_SERIAL.bat"
MANIFEST = ROOT / "HF4_PATCH_MANIFEST_SHA256.json"
OUT = ROOT / "audits" / "V17T2R6R9_HF4_CONTINUATION_AUDIT.json"
TARGET_TO_SOURCE = {
    "TY2033_FULL8760_OPTIMAL": "TY2033_FULL8760_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL": "TY2033_FULL8760_LDES_OBSERVED",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def delimiter_errors(text: str) -> list[str]:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[tuple[str, int]] = []
    errors: list[str] = []
    i = 0
    in_string = False
    triple = False
    escaped = False
    while i < len(text):
        if in_string:
            if triple and text.startswith('"""', i):
                in_string = False
                triple = False
                i += 3
                continue
            if not triple:
                if escaped:
                    escaped = False
                elif text[i] == "\\":
                    escaped = True
                elif text[i] == '"':
                    in_string = False
            i += 1
            continue
        if text.startswith('"""', i):
            in_string = True
            triple = True
            i += 3
            continue
        char = text[i]
        if char == '"':
            in_string = True
        elif char == "#":
            newline = text.find("\n", i)
            i = len(text) if newline < 0 else newline + 1
            continue
        elif char in "([{":
            stack.append((char, i))
        elif char in pairs:
            if not stack or stack[-1][0] != pairs[char]:
                errors.append(f"mismatched {char} at byte {i}")
            else:
                stack.pop()
        i += 1
    if in_string:
        errors.append("unterminated double-quoted string")
    errors.extend(f"unclosed {char} at byte {pos}" for char, pos in stack[-20:])
    return errors


def read_policy(scenario: str) -> list[dict[str, str]]:
    path = ROOT / "sensitivity_cases" / scenario / "inputs" / "legacy_storage_policy.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: object) -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    model = MODEL.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    launcher = LAUNCHER.read_text(encoding="utf-8")

    syntax_errors: list[str] = []
    for path in (RUNNER, Path(__file__)):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_errors.append(f"{path.name}: {exc}")
    add("python_syntax", not syntax_errors, syntax_errors)
    delimiter_detail = {
        "model": delimiter_errors(model),
        "helper": delimiter_errors(helper),
    }
    add("julia_utf8_and_balanced_delimiters",
        not any(delimiter_detail.values()), delimiter_detail)

    numerical_tokens = [
        "const SOLVER_FEASIBILITY_TOL = 1.0e-7",
        "const SOLVER_OPTIMALITY_TOL = 1.0e-7",
        "const SOLVER_BAR_CONV_TOL = 1.0e-8",
        "const ECONOMIC_OBJECTIVE_SCALE_USD = 1.0e6",
        '"V17T2R6R8_HF3_equivalent_projected_legacy_allocation_v2"',
        "LEGACY_ENERGY_VARIABLE_PROJECTION_ACTIVE = LEGACY_OPTIMIZED_REALLOCATION",
    ]
    missing_numerical = [token for token in numerical_tokens if token not in model]
    add("scientific_formulation_and_tolerances_retained", not missing_numerical, missing_numerical)

    model_tokens = [
        'include(joinpath(@__DIR__, "full8760_hf4_objective_continuation.jl"))',
        'profile == "full8760_primal_dual_supported_objective_continuation"',
        '"V17T2R6R9_HF4_full8760_primal_dual_supported_exact_objective_continuation"',
        "HF4_PRIMAL_DUAL_SUPPORTED_OBJECTIVE_CONTINUATION_ACTIVE",
        '"TY2033_FULL8760_OPTIMAL"',
        '"TY2033_FULL8760_LDES_OPTIMAL"',
        "hf4_state.final_bounds_restored",
        "hf4_state.final_objective_restored",
        "hf4_state.final_max_objective_coefficient_error == 0.0",
        '"gurobi_V17T2R6R9_HF4_full8760_original_objective_optimal_after_primal_dual_supported_continuation"',
        ":hf4_homotopy_stage_records",
    ]
    missing_model = [token for token in model_tokens if token not in model]
    add("model_route_isolation_and_native_certificate", not missing_model, missing_model)

    helper_tokens = [
        "RC[j] = c[j] - A[:,j]'y",
        'Gurobi.GRBgetdblattrarray(grb, String(name)',
        'Gurobi.GRBsetdblattrarray(grb, String(name)',
        'Gurobi.GRBsetdblattrlist(grb, String(name)',
        'Gurobi.GRBreset(grb, Cint(0))',
        '"PStart"',
        '"DStart"',
        '"VBasis"',
        '"CBasis"',
        "JuMP.fix(legacy_vars[i], seed_values[i]; force=true)",
        "JuMP.unfix(legacy_vars[i])",
        "JuMP.set_lower_bound(legacy_vars[i], original_lower_bounds[i])",
        "JuMP.set_upper_bound(legacy_vars[i], original_upper_bounds[i])",
        "support_objective = legacy_original_objective .- legacy_reduced_cost",
        "V17T2R6R9_HF4_OBJECTIVE_HOMOTOPY_LEVELS",
        "stage.pass || error",
        '"Obj", legacy_columns, legacy_original_objective',
        "max_objective_error == 0.0",
        "final_objective_restored || error",
        "_v17t2r6r9_hf4_apply_continuation_profile!(mod; final_stage=true)",
    ]
    missing_helper = [token for token in helper_tokens if token not in helper]
    add("exact_primal_dual_supported_continuation_contract", not missing_helper, missing_helper)

    scope_helper_tokens = [
        "function _v17t2r6r9_hf4_safe_solve_float(f)",
        "function _v17t2r6r9_hf4_safe_gurobi_model_float(mod, attribute_name::AbstractString)",
        "function _v17t2r6r9_hf4_safe_gurobi_model_int(mod, attribute_name::AbstractString)",
        "function _v17t2r6r9_hf4_safe_result_count(mod)",
        "return Int(result_count(mod))",
    ]
    missing_scope_helpers = [token for token in scope_helper_tokens if token not in helper]
    unresolved_local_helper_calls = re.findall(
        r"(?<!v17t2r6r9_hf4)_safe_(?:solve_float|gurobi_model_float|gurobi_model_int|result_count)",
        helper,
    )
    add("hf4_scope_safe_postsolve_status_helpers",
        not missing_scope_helpers and not unresolved_local_helper_calls,
        {"missing": missing_scope_helpers, "unresolved": unresolved_local_helper_calls})

    forbidden_helper = [
        'GRBsetdblattrlist(grb, "RHS"',
        'GRBsetdblattrarray(grb, "RHS"',
        'GRBsetcharattrarray(grb, "Sense"',
        "set_normalized_rhs(",
        "set_normalized_coefficient(",
        "delete(mod,",
    ]
    forbidden_hits = [token for token in forbidden_helper if token in helper]
    add("no_matrix_rhs_or_constraint_intervention", not forbidden_hits, forbidden_hits)

    route_tokens = [
        '"hf4_continuation": HF4_CONTINUATION_ROUTES',
        '"__04_full8760_hf4_primal_dual_supported_objective_continuation"',
        '"full8760_primal_dual_supported_objective_continuation"',
        '"TY2033_FULL8760_OPTIMAL"',
        '"TY2033_FULL8760_LDES_OPTIMAL"',
        "HF4 final objective coefficients were not restored exactly",
        "HF4 homotopy schedule did not complete",
    ]
    missing_route = [token for token in route_tokens if token not in runner]
    add("orchestrator_fail_closed_hf4_gate", not missing_route, missing_route)

    launcher_required = [
        'set "V17_SOLVER_THREADS=10"',
        'set "V17T2R6_MAX_PARALLEL=1"',
        'set "V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS=129600"',
        'set "V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS=21600"',
        'set "V17T2R6R9_HF4_STAGE_TIME_LIMIT_SECONDS=21600"',
        'set "V17T2R6R9_HF4_FINAL_TIME_LIMIT_SECONDS=129600"',
        "--scenario TY2033_FULL8760_OBSERVED --route hf3 --skip-prepare --max-parallel 1",
        "--scenario TY2033_FULL8760_OPTIMAL --route hf4_continuation --skip-prepare --max-parallel 1",
        "--scenario TY2033_FULL8760_LDES_OBSERVED --route hf3 --skip-prepare --max-parallel 1",
        "--scenario TY2033_FULL8760_LDES_OPTIMAL --route hf4_continuation --skip-prepare --max-parallel 1",
    ]
    launcher_forbidden = ["--clean-central", "--force-rerun", "--max-parallel 2", "rmdir ", "Remove-Item"]
    missing_launcher = [token for token in launcher_required if token not in launcher]
    forbidden_launcher_hits = [token for token in launcher_forbidden if token in launcher]
    add("resume_safe_serial_launcher",
        not missing_launcher and not forbidden_launcher_hits,
        {"missing": missing_launcher, "forbidden": forbidden_launcher_hits})

    pair_details: dict[str, object] = {}
    pair_pass = True
    for target, source in TARGET_TO_SOURCE.items():
        target_meta = json.loads((ROOT / "sensitivity_cases" / target /
                                  "SENSITIVITY_SCENARIO_META.json").read_text(encoding="utf-8"))
        source_meta = json.loads((ROOT / "sensitivity_cases" / source /
                                  "SENSITIVITY_SCENARIO_META.json").read_text(encoding="utf-8"))
        target_policy = read_policy(target)
        source_policy = read_policy(source)
        target_by_project = {row["battery_project"]: row for row in target_policy}
        source_by_project = {row["battery_project"]: row for row in source_policy}
        source_power = sum(float(row["fixed_power_mw"]) for row in source_policy)
        source_energy = sum(float(row["fixed_energy_mwh"]) for row in source_policy)
        target_power = float(target_policy[0]["national_power_target_mw"])
        target_energy = float(target_policy[0]["national_energy_target_mwh"])
        duration = float(target_policy[0]["standardized_duration_h"])
        min_cap_slack = min(
            float(target_by_project[name]["legacy_power_cap_mw"]) - float(row["fixed_power_mw"])
            for name, row in source_by_project.items()
        )
        passed = bool(
            len(target_policy) == len(source_policy) == 32
            and set(target_by_project) == set(source_by_project)
            and {row["legacy_allocation_mode"] for row in target_policy} == {"optimized_reallocation"}
            and {row["legacy_allocation_mode"] for row in source_policy} == {"observed_standardized"}
            and target_meta["pair_id"] == source_meta["pair_id"]
            and target_meta["target_year"] == source_meta["target_year"] == 2033
            and target_meta["storage_chronology_mode"] == source_meta["storage_chronology_mode"] == "full_year_cyclic"
            and target_meta["ldes_proxy_mode"] == source_meta["ldes_proxy_mode"]
            and math.isclose(source_power, target_power, rel_tol=0.0, abs_tol=1.0e-6)
            and math.isclose(source_energy, target_energy, rel_tol=0.0, abs_tol=1.0e-6)
            and abs(target_energy - duration * target_power) <= 1.0e-6
            and min_cap_slack >= -1.0e-6
            and all(abs(float(row["fixed_energy_mwh"]) -
                        duration * float(row["fixed_power_mw"])) <= 1.0e-6
                    for row in source_policy)
        )
        pair_pass &= passed
        pair_details[target] = {
            "pass": passed,
            "source": source,
            "coordinates": len(target_policy),
            "source_power_mw": source_power,
            "source_energy_mwh": source_energy,
            "target_power_mw": target_power,
            "target_energy_mwh": target_energy,
            "duration_h": duration,
            "minimum_target_cap_slack_mw": min_cap_slack,
        }
    add("paired_observed_seed_feasible_for_both_targets", pair_pass, pair_details)

    pair_audit_path = ROOT / "audits" / "V17T2R6_FULL8760_PAIR_IDENTITY_AUDIT.json"
    pair_audit = json.loads(pair_audit_path.read_text(encoding="utf-8")) if pair_audit_path.is_file() else {}
    add("frozen_matched_pair_identity_audit",
        pair_audit.get("status") == "PASS", pair_audit.get("status", "MISSING"))

    fingerprint_errors: list[str] = []
    checked_input_files = 0
    for scenario in [*TARGET_TO_SOURCE.values(), *TARGET_TO_SOURCE.keys()]:
        case = ROOT / "sensitivity_cases" / scenario
        fingerprint_path = case / "audits" / "CASE_PUBLICATION_SOURCE_FINGERPRINT.json"
        if not fingerprint_path.is_file():
            fingerprint_errors.append(f"{scenario}: missing source fingerprint")
            continue
        fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
        for item in fingerprint.get("input_files", []):
            path = case / str(item["path"])
            checked_input_files += 1
            if not path.is_file():
                fingerprint_errors.append(f"{scenario}: missing {item['path']}")
            elif path.stat().st_size != int(item["size_bytes"]):
                fingerprint_errors.append(f"{scenario}: size {item['path']}")
            elif sha256(path) != str(item["sha256"]):
                fingerprint_errors.append(f"{scenario}: sha256 {item['path']}")
    add("all_four_scientific_inputs_match_frozen_fingerprints",
        checked_input_files > 0 and not fingerprint_errors,
        {"checked_input_files": checked_input_files, "errors": fingerprint_errors})

    manifest_errors: list[str] = []
    if not MANIFEST.is_file():
        manifest_errors.append("HF4 patch manifest missing")
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
    add("hf4_patch_files_match_manifest", not manifest_errors, manifest_errors)

    result = {
        "version": "V17T2R6R9_HF4P2_SCOPE_SAFE_FULL8760_PRIMAL_DUAL_SUPPORTED_OBJECTIVE_CONTINUATION",
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "scope": "static syntax, exact continuation, scientific invariance, frozen inputs, resume safety and patch integrity",
        "scientific_change": False,
        "final_target_model_changed": False,
        "target_cases": list(TARGET_TO_SOURCE),
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
