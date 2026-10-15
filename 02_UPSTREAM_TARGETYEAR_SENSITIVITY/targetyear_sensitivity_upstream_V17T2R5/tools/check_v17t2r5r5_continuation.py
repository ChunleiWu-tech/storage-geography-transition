#!/usr/bin/env python3
"""Static and input-contract gate for the isolated exact R5 continuation route."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import math
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r5.jl"
RUNNER = ROOT / "tools" / "run_targetyear_batch.py"
LAUNCHER = ROOT / "RUN_V17T2R5R5_2033_1H_OPTIMAL_ONLY.bat"
MANIFEST = ROOT / "PATCH_MANIFEST_SHA256_R5.json"
OBSERVED = "TY2033_CHRONO_1H_OBSERVED"
OPTIMAL = "TY2033_CHRONO_1H_OPTIMAL"
OBS_INPUTS = ROOT / "sensitivity_cases" / OBSERVED / "inputs"
OPT_INPUTS = ROOT / "sensitivity_cases" / OPTIMAL / "inputs"
ALLOWED_PAIR_DIFFERENCES = {"legacy_storage_policy.csv", "gen_build_predetermined.csv"}

errors: list[str] = []
checks: dict[str, object] = {}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require_tokens(label: str, text: str, tokens: list[str]) -> None:
    for token in tokens:
        present = token in text
        checks[f"{label}::{token}"] = present
        if not present:
            errors.append(f"{label} missing token: {token}")


if not MANIFEST.is_file():
    errors.append("missing PATCH_MANIFEST_SHA256_R5.json")
else:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_checks: dict[str, object] = {}
    for rel, expected in manifest.get("core_payload_sha256", {}).items():
        path = ROOT / rel
        actual = sha256(path) if path.is_file() else None
        passed = actual == expected
        manifest_checks[rel] = {
            "pass": passed,
            "expected_sha256": expected,
            "actual_sha256": actual,
        }
        if not passed:
            errors.append(f"R5 core payload hash mismatch: {rel}")
    checks["core_payload_hashes"] = manifest_checks

model = MODEL.read_text(encoding="utf-8")
require_tokens("model", model, [
    'String(solver_profile) == "r5_primal_dual_supported_objective_continuation"',
    'basename(case_dir) != "TY2033_CHRONO_1H_OPTIMAL"',
    'r4_seed_source_scenario = "TY2033_CHRONO_1H_OBSERVED"',
    "r4_seed_source_pair_identity_pass",
    "r4_seed_strict_optimal ||",
    '_v17_raw_get_double_array(r5_grb, "X"',
    '_v17_raw_get_double_array(r5_grb, "Pi"',
    '_v17_raw_get_double_array(r5_grb, "RC"',
    "r5_support_objective =",
    "r5_legacy_original_objective .- r5_legacy_reduced_costs",
    '_v17_raw_set_double_list!(\n                r5_grb, "Obj"',
    '_v17_raw_set_double_array!(grb, "PStart", primal_start)',
    '_v17_raw_set_double_array!(grb, "DStart", dual_start)',
    "apply_r5_bridge_profile!(mod)",
    'set_optimizer_attribute(mod, "LPWarmStart", 2)',
    'set_optimizer_attribute(mod, "Crossover", 3)',
    'set_optimizer_attribute(mod, "CrossoverBasis", 1)',
    '_v17_raw_get_int_array(\n                r5_grb, "VBasis"',
    '_v17_raw_get_int_array(\n                r5_grb, "CBasis"',
    "V17T2R5R5_OBJECTIVE_HOMOTOPY_LEVELS = (0.001, 0.003, 0.01, 0.03, 0.10, 0.25, 0.50, 0.75)",
    "(1.0 - theta) .* r5_legacy_reduced_costs",
    "apply_r5_continuation_profile!(mod; final_stage=false)",
    'set_optimizer_attribute(mod, "Method", settings.method)',
    'set_optimizer_attribute(mod, "Presolve", 0)',
    'set_optimizer_attribute(mod, "LPWarmStart", 1)',
    "r5_final_max_objective_coefficient_error == 0.0",
    "apply_r5_continuation_profile!(mod; final_stage=true)",
    '"gurobi_V17T2R5R5_full_optimal_primal_simplex_after_primal_dual_supported_objective_continuation"',
    "const SOLVER_FEASIBILITY_TOL = 1.0e-7",
    "const SOLVER_OPTIMALITY_TOL = 1.0e-7",
    "const SOLVER_BAR_CONV_TOL = 1.0e-8",
    '"V17T2R5R3_equivalent_hourly_coordinate_projection_v1"',
])

for forbidden in [
    "SOLVER_FEASIBILITY_TOL = 1.0e-3",
    "SOLVER_OPTIMALITY_TOL = 1.0e-3",
    "R5_PRIMAL_DUAL_SUPPORTED_OBJECTIVE_CONTINUATION_ACTIVE = true",
]:
    absent = forbidden not in model
    checks[f"model_forbidden_absent::{forbidden}"] = absent
    if not absent:
        errors.append(f"unsafe R5 model token remains: {forbidden}")

runner = RUNNER.read_text(encoding="utf-8")
require_tokens("runner", runner, [
    '"r5_continuation": R5_CONTINUATION_ROUTE',
    "11_targetyear_r5_primal_dual_supported_objective_continuation",
    'args.route in {"r3_reduced", "r4_continuation", "r5_continuation"}',
    'args.scenario != "TY2033_CHRONO_1H_OPTIMAL"',
    '"r5_primal_dual_start_set_pass": "true"',
    '"r5_bridge_strict_optimal": "true"',
    '"r5_bridge_basis_available": "true"',
    '"r5_homotopy_all_strict_optimal": "true"',
    '"r5_final_objective_restored": "true"',
    "r5 final objective coefficients were not restored exactly",
    "r5 homotopy schedule did not complete",
    "gurobi_V17T2R5R5_full_optimal_primal_simplex_after_primal_dual_supported_objective_continuation",
])

launcher = LAUNCHER.read_text(encoding="utf-8") if LAUNCHER.is_file() else ""
require_tokens("launcher", launcher, [
    "--scenario TY2033_CHRONO_1H_OPTIMAL",
    "--route r5_continuation",
    "--skip-prepare",
    "--force-rerun",
    "V17T2R5R4_SEED_TIME_LIMIT_SECONDS",
    "V17T2R5R5_BRIDGE_TIME_LIMIT_SECONDS",
    "V17T2R5R5_STAGE_TIME_LIMIT_SECONDS",
    "V17T2R5R5_FINAL_TIME_LIMIT_SECONDS",
])
for forbidden in ["--clean-central", "--pair ", "--continue-after-failure"]:
    absent = forbidden not in launcher
    checks[f"launcher_forbidden_absent::{forbidden}"] = absent
    if not absent:
        errors.append(f"isolated R5 launcher contains forbidden option: {forbidden}")

# The bridge seed may differ only in the declared matched-pair geography inputs.
obs_files = {p.name for p in OBS_INPUTS.glob("*.csv")}
opt_files = {p.name for p in OPT_INPUTS.glob("*.csv")}
pair_errors: list[str] = []
if obs_files != opt_files:
    pair_errors.append("paired input file sets differ")
for name in sorted(obs_files & opt_files):
    if name not in ALLOWED_PAIR_DIFFERENCES and sha256(OBS_INPUTS / name) != sha256(OPT_INPUTS / name):
        pair_errors.append(f"non-geographic paired input differs: {name}")
checks["paired_non_geographic_input_identity"] = {
    "status": "PASS" if not pair_errors else "FAIL",
    "errors": pair_errors,
    "allowed_differences": sorted(ALLOWED_PAIR_DIFFERENCES),
}
errors.extend(pair_errors)

obs = pd.read_csv(OBS_INPUTS / "legacy_storage_policy.csv")
opt = pd.read_csv(OPT_INPUTS / "legacy_storage_policy.csv")
merged = obs[["battery_project", "fixed_power_mw", "fixed_energy_mwh"]].merge(
    opt[["battery_project", "legacy_power_cap_mw"]],
    on="battery_project", validate="one_to_one",
)
power_target = float(opt["national_power_target_mw"].iloc[0])
energy_target = float(opt["national_energy_target_mwh"].iloc[0])
duration = float(opt["standardized_duration_h"].iloc[0])
power_residual = float(merged["fixed_power_mw"].sum() - power_target)
energy_residual = float(merged["fixed_energy_mwh"].sum() - energy_target)
duration_residual = float((merged["fixed_energy_mwh"] - duration * merged["fixed_power_mw"]).abs().max())
minimum_cap_slack = float((merged["legacy_power_cap_mw"] - merged["fixed_power_mw"]).min())
checks["seed_contract"] = {
    "rows": len(merged),
    "power_residual_mw": power_residual,
    "energy_residual_mwh": energy_residual,
    "maximum_duration_residual_mwh": duration_residual,
    "minimum_cap_slack_mw": minimum_cap_slack,
}
if len(merged) != 32:
    errors.append("R5 seed does not contain exactly 32 matched coordinates")
if set(obs["legacy_allocation_mode"].astype(str)) != {"observed_standardized"}:
    errors.append("R5 seed source is not observed_standardized")
if set(opt["legacy_allocation_mode"].astype(str)) != {"optimized_reallocation"}:
    errors.append("R5 target is not optimized_reallocation")
if not math.isfinite(power_residual) or abs(power_residual) > 1.0e-6:
    errors.append("R5 observed seed does not close national power")
if not math.isfinite(energy_residual) or abs(energy_residual) > 1.0e-6:
    errors.append("R5 observed seed does not close national energy")
if not math.isfinite(duration_residual) or duration_residual > 1.0e-6:
    errors.append("R5 observed seed violates common-duration identity")
if not math.isfinite(minimum_cap_slack) or minimum_cap_slack < -1.0e-6:
    errors.append("R5 observed seed violates a restored target upper bound")

scenarios = pd.read_csv(ROOT / "storage_runner" / "scenarios_targetyear_linked.csv")
pair = scenarios.loc[scenarios["scenario"].isin([OBSERVED, OPTIMAL])]
checks["scenario_lock"] = {
    "controlled_case_count": len(scenarios),
    "pair_rows": len(pair),
    "pair_ids": sorted(set(pair["pair_id"].astype(str))),
    "time_resolution_h": sorted(set(pd.to_numeric(pair["time_resolution_h"]).astype(int))),
    "chronology": sorted(set(pair["storage_chronology_mode"].astype(str))),
}
if len(scenarios) != 8 or len(pair) != 2:
    errors.append("controlled eight-case table or R5 pair is invalid")
if set(pair["pair_id"].astype(str)) != {"TY2033_CHRONO_1H"}:
    errors.append("R5 source and target are not the declared one-hour pair")
if set(pd.to_numeric(pair["time_resolution_h"]).astype(int)) != {1}:
    errors.append("R5 pair is not one-hour")
if set(pair["storage_chronology_mode"].astype(str)) != {"monthly_linked"}:
    errors.append("R5 chronology changed")

lex = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "audit_julia_lexical_v17t2r5.py")],
    cwd=ROOT, capture_output=True, text=True,
)
checks["julia_lexical_audit_return_code"] = lex.returncode
if lex.returncode != 0:
    errors.append("Julia lexical audit failed: " + (lex.stdout + lex.stderr)[-1500:])

result = {
    "version": "V17T2R5R5_PRIMAL_DUAL_SUPPORTED_EXACT_OBJECTIVE_CONTINUATION_20260814",
    "status": "PASS" if not errors else "FAIL",
    "errors": errors,
    "checks": checks,
    "scientific_inputs_changed": False,
    "final_constraints_or_rhs_changed": False,
    "final_bounds_changed": False,
    "final_objective_changed": False,
    "temporary_objective_continuation_only": True,
    "solver_tolerances_relaxed": False,
    "publication_gates_relaxed": False,
    "other_seven_cases_rerun_or_cleaned": False,
    "strict_seed_bridge_each_stage_and_final_optimal_required": True,
    "dynamic_julia_gurobi_solve_executed": False,
}
out = ROOT / "audits" / "V17T2R5R5_CONTINUATION_AUDIT.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["status"] == "PASS" else 1)
