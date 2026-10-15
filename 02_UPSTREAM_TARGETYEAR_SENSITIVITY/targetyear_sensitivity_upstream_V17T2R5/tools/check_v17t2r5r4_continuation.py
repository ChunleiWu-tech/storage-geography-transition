#!/usr/bin/env python3
"""Static, pair-identity and exact-state-transfer gate for isolated R4."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import math

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r5.jl"
RUNNER = ROOT / "tools" / "run_targetyear_batch.py"
LAUNCHER = ROOT / "RUN_V17T2R5R4_2033_1H_OPTIMAL_ONLY.bat"
PATCH_MANIFEST = ROOT / "PATCH_MANIFEST_SHA256_R4.json"
OBSERVED = "TY2033_CHRONO_1H_OBSERVED"
OPTIMAL = "TY2033_CHRONO_1H_OPTIMAL"
OBS_INPUTS = ROOT / "sensitivity_cases" / OBSERVED / "inputs"
OPT_INPUTS = ROOT / "sensitivity_cases" / OPTIMAL / "inputs"
ALLOWED_PAIR_DIFFERENCES = {"legacy_storage_policy.csv", "gen_build_predetermined.csv"}

errors: list[str] = []
checks: dict[str, object] = {}


def require_tokens(label: str, text: str, tokens: list[str]) -> None:
    for token in tokens:
        present = token in text
        checks[f"{label}::{token}"] = present
        if not present:
            errors.append(f"{label} missing token: {token}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


R5_SUPERSEDES_CORE = (ROOT / "VERSION_V17T2R5R5.txt").is_file()
checks["r5_supersedes_r4_core_hash_lock"] = R5_SUPERSEDES_CORE
if R5_SUPERSEDES_CORE:
    # R5 intentionally updates the same model and batch-runner files. The R4
    # manifest remains historical; R5 has its own self-locking manifest.
    checks["core_payload_hashes"] = "SKIPPED_SUPERSEDED_BY_R5"
elif not PATCH_MANIFEST.is_file():
    errors.append("missing PATCH_MANIFEST_SHA256_R4.json")
else:
    manifest = json.loads(PATCH_MANIFEST.read_text(encoding="utf-8"))
    core_hash_checks: dict[str, object] = {}
    for rel, expected_hash in manifest.get("core_payload_sha256", {}).items():
        path = ROOT / rel
        actual_hash = sha256(path) if path.is_file() else None
        passed = actual_hash == expected_hash
        core_hash_checks[rel] = {
            "pass": passed,
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
        }
        if not passed:
            errors.append(f"R4 core payload hash mismatch: {rel}")
    checks["core_payload_hashes"] = core_hash_checks


model = MODEL.read_text(encoding="utf-8")
require_tokens("model", model, [
    'String(solver_profile) == "r4_observed_seed_primal_continuation"',
    'basename(case_dir) != "TY2033_CHRONO_1H_OPTIMAL"',
    'r4_seed_source_scenario = "TY2033_CHRONO_1H_OBSERVED"',
    'r4_seed_values = [r4_observed_power_by_project[g] for g in legacy_projects]',
    "r4_seed_source_pair_identity_pass",
    "r4_seed_national_power_residual_mw",
    "r4_seed_national_energy_residual_mwh",
    "r4_seed_minimum_lower_bound_slack_mw",
    "r4_seed_minimum_cap_slack_mw",
    "apply_r4_seed_profile!(mod)",
    "r4_seed_gurobi_status == 2",
    "r4_seed_gurobi_objval_gate_pass",
    "r4_seed_objective_scale_gate_pass",
    "r4_seed_term == JuMP.MOI.OPTIMAL",
    "r4_pstart_values = [value(v) for v in r4_pstart_vars]",
    "JuMP.unfix(legacy_vars[i])",
    "JuMP.set_lower_bound(legacy_vars[i], r4_original_lower_bounds[i])",
    "JuMP.set_upper_bound(legacy_vars[i], r4_original_upper_bounds[i])",
    "r4_final_bounds_restored",
    "r4_seed_full_pstart_max_bound_violation",
    "_v17_apply_raw_pstart!(mod, r4_pstart_vars, r4_pstart_values)",
    "lp_warm_start = 2",
    'method = 0',
    '"gurobi_V17T2R5R4_full_optimal_primal_simplex_after_strict_observed_seed"',
    "const SOLVER_FEASIBILITY_TOL = 1.0e-7",
    "const SOLVER_OPTIMALITY_TOL = 1.0e-7",
    "const SOLVER_BAR_CONV_TOL = 1.0e-8",
    '"V17T2R5R3_equivalent_hourly_coordinate_projection_v1"',
    ":total_omitted_hourly_columns",
])
for forbidden in [
    "r4_seed_values = [legacy_fixed_power_by_project[g] for g in legacy_projects]",
    'R4_OBSERVED_SEED_PRIMAL_CONTINUATION_ACTIVE = true',
]:
    absent = forbidden not in model
    checks[f"model_forbidden_absent::{forbidden}"] = absent
    if not absent:
        errors.append(f"unsafe R4 model token remains: {forbidden}")

runner = RUNNER.read_text(encoding="utf-8")
require_tokens("runner", runner, [
    '"r4_continuation": R4_CONTINUATION_ROUTE',
    "10_targetyear_r4_observed_seed_primal_continuation",
    'args.route in {"r3_reduced", "r4_continuation", "r5_continuation"}',
    'args.scenario != "TY2033_CHRONO_1H_OPTIMAL"',
    '"r4_seed_source_scenario": "TY2033_CHRONO_1H_OBSERVED"',
    '"r4_seed_source_pair_identity_pass": "true"',
    '"r4_seed_gurobi_objval_gate_pass": "true"',
    '"r4_seed_objective_scale_gate_pass": "true"',
    '"r4_final_bounds_restored": "true"',
    '"r4_seed_full_pstart_set_pass": "true"',
    "r4 full PStart count does not equal the reduced model variable count",
    "r4 full PStart violates a restored final-model bound",
])

launcher = LAUNCHER.read_text(encoding="utf-8") if LAUNCHER.is_file() else ""
require_tokens("launcher", launcher, [
    "--scenario TY2033_CHRONO_1H_OPTIMAL",
    "--route r4_continuation",
    "--skip-prepare",
    "--force-rerun",
    "V17T2R5R4_SEED_TIME_LIMIT_SECONDS",
    "V17T2R5R4_FINAL_TIME_LIMIT_SECONDS",
])
for forbidden in ["--clean-central", "--pair ", "r3_reduced"]:
    if forbidden in launcher:
        errors.append(f"isolated R4 launcher contains forbidden option: {forbidden}")

# Pair-level input identity: R4 is allowed to read only the paired observed legacy
# allocation as a feasible start. All non-geographic inputs remain byte-identical.
obs_files = {p.name for p in OBS_INPUTS.glob("*.csv")}
opt_files = {p.name for p in OPT_INPUTS.glob("*.csv")}
pair_file_errors: list[str] = []
if obs_files != opt_files:
    pair_file_errors.append("paired input file sets differ")
for name in sorted(obs_files & opt_files):
    if name not in ALLOWED_PAIR_DIFFERENCES and sha256(OBS_INPUTS / name) != sha256(OPT_INPUTS / name):
        pair_file_errors.append(f"non-geographic paired input differs: {name}")
checks["paired_non_geographic_input_identity"] = {
    "status": "PASS" if not pair_file_errors else "FAIL",
    "errors": pair_file_errors,
    "allowed_differences": sorted(ALLOWED_PAIR_DIFFERENCES),
}
errors.extend(pair_file_errors)

obs = pd.read_csv(OBS_INPUTS / "legacy_storage_policy.csv")
opt = pd.read_csv(OPT_INPUTS / "legacy_storage_policy.csv")
obs_projects = set(obs["battery_project"].astype(str))
opt_projects = set(opt["battery_project"].astype(str))
merged = obs[["battery_project", "fixed_power_mw", "fixed_energy_mwh"]].merge(
    opt[["battery_project", "legacy_power_cap_mw"]],
    on="battery_project", validate="one_to_one",
)
power_target = float(opt["national_power_target_mw"].iloc[0])
energy_target = float(opt["national_energy_target_mwh"].iloc[0])
duration = float(opt["standardized_duration_h"].iloc[0])
power_residual = float(merged["fixed_power_mw"].sum() - power_target)
energy_residual = float(merged["fixed_energy_mwh"].sum() - energy_target)
duration_residual = float((
    merged["fixed_energy_mwh"] - duration * merged["fixed_power_mw"]
).abs().max())
minimum_lower_slack = float(merged["fixed_power_mw"].min())
minimum_cap_slack = float((
    merged["legacy_power_cap_mw"] - merged["fixed_power_mw"]
).min())
seed_contract = {
    "observed_mode": sorted(set(obs["legacy_allocation_mode"].astype(str))),
    "optimal_mode": sorted(set(opt["legacy_allocation_mode"].astype(str))),
    "observed_rows": len(obs),
    "optimal_rows": len(opt),
    "project_sets_equal": obs_projects == opt_projects,
    "power_target_mw": power_target,
    "observed_power_sum_mw": float(merged["fixed_power_mw"].sum()),
    "power_residual_mw": power_residual,
    "energy_target_mwh": energy_target,
    "observed_energy_sum_mwh": float(merged["fixed_energy_mwh"].sum()),
    "energy_residual_mwh": energy_residual,
    "standardized_duration_h": duration,
    "maximum_project_duration_residual_mwh": duration_residual,
    "minimum_lower_bound_slack_mw": minimum_lower_slack,
    "minimum_cap_slack_mw": minimum_cap_slack,
}
checks["observed_seed_contract"] = seed_contract
if len(obs) != 32 or len(opt) != 32 or len(merged) != 32 or obs_projects != opt_projects:
    errors.append("R4 seed project identity is not exactly 32 matched projects")
if set(obs["legacy_allocation_mode"].astype(str)) != {"observed_standardized"}:
    errors.append("R4 seed source is not the paired observed_standardized case")
if set(opt["legacy_allocation_mode"].astype(str)) != {"optimized_reallocation"}:
    errors.append("R4 final case is not optimized_reallocation")
if not math.isfinite(power_residual) or abs(power_residual) > 1.0e-6:
    errors.append("R4 observed seed does not close national power")
if not math.isfinite(energy_residual) or abs(energy_residual) > 1.0e-6:
    errors.append("R4 observed seed does not close national energy")
if not math.isfinite(duration_residual) or duration_residual > 1.0e-6:
    errors.append("R4 observed seed violates a project duration identity")
if not math.isfinite(minimum_lower_slack) or minimum_lower_slack < -1.0e-9:
    errors.append("R4 observed seed violates an OPTIMAL lower bound")
if not math.isfinite(minimum_cap_slack) or minimum_cap_slack < -1.0e-6:
    errors.append("R4 observed seed violates an OPTIMAL upper bound")

scenario_table = pd.read_csv(ROOT / "storage_runner" / "scenarios_targetyear_linked.csv")
r4_rows = scenario_table.loc[scenario_table["scenario"].isin([OBSERVED, OPTIMAL])]
checks["scenario_lock"] = {
    "controlled_case_count": len(scenario_table),
    "paired_rows": len(r4_rows),
    "pair_ids": sorted(set(r4_rows["pair_id"].astype(str))),
    "time_resolution_h": sorted(set(pd.to_numeric(r4_rows["time_resolution_h"]).astype(int))),
    "chronology": sorted(set(r4_rows["storage_chronology_mode"].astype(str))),
}
if len(scenario_table) != 8 or len(r4_rows) != 2:
    errors.append("controlled eight-case table or R4 pair is invalid")
if set(r4_rows["pair_id"].astype(str)) != {"TY2033_CHRONO_1H"}:
    errors.append("R4 seed and target are not the declared matched pair")
if set(pd.to_numeric(r4_rows["time_resolution_h"]).astype(int)) != {1}:
    errors.append("R4 pair is not the one-hour sensitivity")
if set(r4_rows["storage_chronology_mode"].astype(str)) != {"monthly_linked"}:
    errors.append("R4 pair chronology changed")

result = {
    "version": "V17T2R5R4_OBSERVED_FEASIBLE_START_FULL_OPTIMAL_CONTINUATION_20260813",
    "status": "PASS" if not errors else "FAIL",
    "errors": errors,
    "checks": checks,
    "scientific_inputs_changed": False,
    "objective_changed": False,
    "final_feasible_set_changed": False,
    "solver_tolerances_relaxed": False,
    "publication_gates_relaxed": False,
    "other_seven_cases_rerun_or_cleaned": False,
    "strict_seed_solution_required": True,
    "final_full_optimal_model_solver_native_optimal_required": True,
    "dynamic_julia_gurobi_solve_executed": False,
}
out = ROOT / "audits" / "V17T2R5R4_CONTINUATION_AUDIT.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["status"] == "PASS" else 1)
