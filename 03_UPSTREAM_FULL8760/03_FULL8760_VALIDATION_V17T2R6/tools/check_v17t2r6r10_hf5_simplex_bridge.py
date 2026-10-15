#!/usr/bin/env python3
"""Fail-closed static and integrity audit for the R10-HF5 no-crossover bridge."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"
HELPER = ROOT / "base_model_v39" / "full8760_hf4_objective_continuation.jl"
RUNNER = ROOT / "tools" / "run_targetyear_batch.py"
LAUNCHER = ROOT / "RUN_V17T2R6R10_HF5_8760_OPTIMAL_ONLY_15T_RESUME.bat"
LDES_LAUNCHER = ROOT / "RUN_V17T2R6R10_HF5_8760_LDES_OPTIMAL_ONLY_15T_RESUME.bat"
PAIR_LAUNCHER = ROOT / "RUN_V17T2R6R10_HF5_8760_OPTIMIZED_PAIR_AUTO_RESUME_2X15.bat"
PAIR_COORDINATOR = ROOT / "tools" / "run_hf5_optimized_pair_auto_resume.py"
MANIFEST = ROOT / "HF5_PATCH_MANIFEST_SHA256.json"
OUT = ROOT / "audits" / "V17T2R6R10_HF5_NO_CROSSOVER_SIMPLEX_BRIDGE_AUDIT.json"


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
    quoted = False
    triple = False
    escaped = False
    while i < len(text):
        if quoted:
            if triple and text.startswith('"""', i):
                quoted = False
                triple = False
                i += 3
                continue
            if not triple:
                if escaped:
                    escaped = False
                elif text[i] == "\\":
                    escaped = True
                elif text[i] == '"':
                    quoted = False
            i += 1
            continue
        if text.startswith('"""', i):
            quoted = True
            triple = True
            i += 3
            continue
        char = text[i]
        if char == '"':
            quoted = True
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
    if quoted:
        errors.append("unterminated double-quoted string")
    errors.extend(f"unclosed {char} at byte {position}" for char, position in stack[-20:])
    return errors


def main() -> None:
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: object) -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    model = MODEL.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    launcher = LAUNCHER.read_text(encoding="utf-8")
    ldes_launcher = LDES_LAUNCHER.read_text(encoding="utf-8")
    pair_launcher = PAIR_LAUNCHER.read_text(encoding="utf-8")
    pair_coordinator = PAIR_COORDINATOR.read_text(encoding="utf-8")

    syntax_errors: list[str] = []
    for path in (RUNNER, PAIR_COORDINATOR, Path(__file__)):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            syntax_errors.append(f"{path.name}: {exc}")
    add("python_syntax", not syntax_errors, syntax_errors)
    delimiters = {"model": delimiter_errors(model), "helper": delimiter_errors(helper)}
    add("julia_utf8_and_balanced_delimiters", not any(delimiters.values()), delimiters)

    scientific_tokens = [
        "const SOLVER_FEASIBILITY_TOL = 1.0e-7",
        "const SOLVER_OPTIMALITY_TOL = 1.0e-7",
        "const SOLVER_BAR_CONV_TOL = 1.0e-8",
        "const ECONOMIC_OBJECTIVE_SCALE_USD = 1.0e6",
        '"V17T2R6R8_HF3_equivalent_projected_legacy_allocation_v2"',
        "LEGACY_ENERGY_VARIABLE_PROJECTION_ACTIVE = LEGACY_OPTIMIZED_REALLOCATION",
    ]
    add("scientific_tolerances_and_exact_projection_retained",
        all(token in model for token in scientific_tokens),
        [token for token in scientific_tokens if token not in model])

    bridge_tokens = [
        "function _v17t2r6r9_hf4_apply_bridge_profile!(mod)",
        "method=0, crossover=0, crossover_basis=-1, numeric_focus=3",
        "lp_warm_start=2, time_limit_seconds=V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS",
        "primal_simplex_crushed_pstart_full_dstart_audited_no_crossover",
        "bridge.barrier_iterations == 0.0",
        '"PStart"', '"DStart"', '"VBasis"', '"CBasis"',
        "support_objective = legacy_original_objective .- legacy_reduced_cost",
        '"Obj", legacy_columns, legacy_original_objective',
        "final_objective_restored || error",
        "V17T2R6R9_HF4_OBJECTIVE_HOMOTOPY_LEVELS",
        "stage.pass || error",
    ]
    old_bridge = "method=2, crossover=3, crossover_basis=1, numeric_focus=3"
    add("hf5_direct_simplex_bridge_is_present_and_crossover_path_removed",
        all(token in helper for token in bridge_tokens) and old_bridge not in helper,
        {"missing": [token for token in bridge_tokens if token not in helper],
         "old_barrier_crossover_profile_present": old_bridge in helper})

    forbidden_helper = [
        'GRBsetdblattrlist(grb, "RHS"',
        'GRBsetdblattrarray(grb, "RHS"',
        'GRBsetcharattrarray(grb, "Sense"',
        "set_normalized_rhs(",
        "set_normalized_coefficient(",
        "delete(mod,",
    ]
    forbidden_hits = [token for token in forbidden_helper if token in helper]
    add("no_matrix_rhs_constraint_or_final_objective_intervention",
        not forbidden_hits, forbidden_hits)

    exact_restore_tokens = [
        "JuMP.fix(legacy_vars[i], seed_values[i]; force=true)",
        "JuMP.unfix(legacy_vars[i])",
        "JuMP.set_lower_bound(legacy_vars[i], original_lower_bounds[i])",
        "JuMP.set_upper_bound(legacy_vars[i], original_upper_bounds[i])",
        "max_lower_error == 0.0 && max_upper_error == 0.0",
        "max_objective_error == 0.0",
        "length(legacy_columns) == 32",
    ]
    add("32_coordinate_temporary_bridge_and_exact_restoration_retained",
        all(token in helper for token in exact_restore_tokens),
        [token for token in exact_restore_tokens if token not in helper])

    model_tokens = [
        "V17T2R6R10_HF5_full8760_primal_dual_start_simplex_basis_no_crossover_exact_objective_continuation",
        "gurobi_V17T2R6R10_HF5_full8760_original_objective_optimal_after_primal_dual_start_no_crossover_simplex_basis_continuation",
        "hf4_state.bridge_method == 0",
        "hf4_state.bridge_crossover == 0",
        "hf4_state.bridge_no_crossover_gate_pass",
        ":hf4_bridge_strategy => [hf4_state.bridge_strategy]",
        ":hf4_bridge_no_crossover_gate_pass => [hf4_state.bridge_no_crossover_gate_pass]",
    ]
    add("model_final_release_requires_hf5_no_crossover_evidence",
        all(token in model for token in model_tokens),
        [token for token in model_tokens if token not in model])

    runner_tokens = [
        "HF5_SIMPLEX_BRIDGE_ROUTES",
        '"hf5_simplex_bridge": HF5_SIMPLEX_BRIDGE_ROUTES',
        "__05_full8760_hf5_primal_dual_start_simplex_basis_no_crossover",
        "HF5 bridge crossover is not disabled (0)",
        "HF5 bridge unexpectedly recorded barrier iterations",
        "gurobi_V17T2R6R10_HF5_full8760_original_objective_optimal_after_primal_dual_start_no_crossover_simplex_basis_continuation",
    ]
    add("orchestrator_records_separate_hf5_attempt_and_fails_closed",
        all(token in runner for token in runner_tokens),
        [token for token in runner_tokens if token not in runner])

    launcher_required = [
        'set "V17_SOLVER_THREADS=15"',
        "--scenario TY2033_FULL8760_OPTIMAL",
        "--route hf5_simplex_bridge",
        "--skip-prepare",
        "--max-parallel 1",
        "CHECK_V17T2R6R10_HF5_8760_OPTIMAL_ONLY.bat",
    ]
    launcher_forbidden = ["--clean-central", "--force-rerun", "rmdir ", "Remove-Item", "FINALIZE_"]
    add("resume_launcher_is_single_case_and_non_destructive",
        all(token in launcher for token in launcher_required) and
        not any(token in launcher for token in launcher_forbidden),
        {"missing": [token for token in launcher_required if token not in launcher],
         "forbidden": [token for token in launcher_forbidden if token in launcher]})

    ldes_required = [
        'set "V17_SOLVER_THREADS=15"',
        "--scenario TY2033_FULL8760_LDES_OPTIMAL",
        "--route hf5_simplex_bridge",
        "--skip-prepare",
        "--max-parallel 1",
        "only after the pre-patch LDES OPTIMAL worker finishes or is safely stopped",
    ]
    add("ldes_hf5_resume_launcher_is_explicitly_deferred_and_non_destructive",
        all(token in ldes_launcher for token in ldes_required) and
        not any(token in ldes_launcher for token in launcher_forbidden),
        {"missing": [token for token in ldes_required if token not in ldes_launcher],
         "forbidden": [token for token in launcher_forbidden if token in ldes_launcher]})

    pair_required = [
        '"TY2033_FULL8760_OPTIMAL"',
        '"TY2033_FULL8760_LDES_OPTIMAL"',
        "batch.HF5_SIMPLEX_BRIDGE_ROUTES",
        "ThreadPoolExecutor(max_workers=2",
        "ldes_observed_changed\": False",
        "live pre-patch LDES_OPTIMAL lease is waited on, never removed",
        "force_rerun\": False",
    ]
    add("optimized_pair_coordinator_uses_hf5_only_and_waits_for_live_ldes_lease",
        all(token in pair_coordinator for token in pair_required),
        [token for token in pair_required if token not in pair_coordinator])
    pair_launcher_required = [
        'set "V17_SOLVER_THREADS=15"',
        "run_hf5_optimized_pair_auto_resume.py",
        "TY2033_FULL8760_LDES_OBSERVED remains on its currently running HF3 route",
        "waits for a live old lease",
    ]
    add("optimized_pair_launcher_is_non_destructive_and_does_not_start_observed_cases",
        all(token in pair_launcher for token in pair_launcher_required) and
        not any(token in pair_launcher for token in launcher_forbidden),
        {"missing": [token for token in pair_launcher_required if token not in pair_launcher],
         "forbidden": [token for token in launcher_forbidden if token in pair_launcher]})

    manifest_errors: list[str] = []
    if not MANIFEST.is_file():
        manifest_errors.append("HF5 patch manifest missing")
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
    add("hf5_payload_files_match_manifest", not manifest_errors, manifest_errors)

    result = {
        "version": "V17T2R6R10_HF5_NO_CROSSOVER_SIMPLEX_BRIDGE",
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "scope": "only the temporary basis-construction algorithm is changed; the final 8760 target LP, inputs, constraints, RHS, bounds, objective and strict release gate remain unchanged",
        "scientific_change": False,
        "final_target_model_changed": False,
        "checks": checks,
        "failed": [item["check"] for item in checks if not item["pass"]],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
