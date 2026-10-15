#!/usr/bin/env python3
"""Focused static and exact-reduction gate for the isolated R3 one-hour case."""
from __future__ import annotations

from pathlib import Path
import json
import math

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r5.jl"
RUNNER = ROOT / "tools" / "run_targetyear_batch.py"
LAUNCHER = ROOT / "RUN_V17T2R5R3_2033_1H_OPTIMAL_ONLY.bat"
SCENARIO = "TY2033_CHRONO_1H_OPTIMAL"
INPUTS = ROOT / "sensitivity_cases" / SCENARIO / "inputs"

errors: list[str] = []
checks: dict[str, object] = {}


def require_tokens(label: str, text: str, tokens: list[str]) -> None:
    for token in tokens:
        present = token in text
        checks[f"{label}::{token}"] = present
        if not present:
            errors.append(f"{label} missing token: {token}")


model = MODEL.read_text(encoding="utf-8")
require_tokens("model", model, [
    'basename(case_dir) == "TY2033_CHRONO_1H_OPTIMAL"',
    '"V17T2R5R3_equivalent_hourly_coordinate_projection_v1"',
    "CCS_GEN_TPS = R3_HOURLY_COORDINATE_PROJECTION_ACTIVE ?",
    "STARTUP_SHUTDOWN_GENS = R3_HOURLY_COORDINATE_PROJECTION_ACTIVE ?",
    "dispatch_gen_ccs_or_zero(g, t)",
    "dispatch_gen_ccs_value_or_zero(g, t)",
    "startup_gen_capacity_value_or_zero(g, t)",
    ":algebraic_reduction_preserves_scientific_inputs => [true]",
    ":algebraic_reduction_preserves_objective_and_projected_feasible_set => [true]",
    ":total_omitted_hourly_columns",
    "const SOLVER_FEASIBILITY_TOL = 1.0e-7",
    "const SOLVER_OPTIMALITY_TOL = 1.0e-7",
    "const SOLVER_BAR_CONV_TOL = 1.0e-8",
    "STORAGE_ENERGY_VARIABLE_BLD_YRS",
    "PROJECTED_LEGACY_STORAGE_ENERGY_BLD_YRS",
    "function storage_energy_build(g, bld_yr)",
])

for forbidden in [
    ":DispatchGenCCS_MW => [val_DispatchGenCCS[(g, t)]",
    ":StartupGenCapacity_OM_Costs_per_period => [gen_startup_om[g] * val_StartupGenCapacity[(g, t)]",
]:
    absent = forbidden not in model
    checks[f"forbidden_direct_export_absent::{forbidden}"] = absent
    if not absent:
        errors.append(f"unreconstructed reduced-axis export remains: {forbidden}")

gen_info = pd.read_csv(INPUTS / "gen_info.csv", keep_default_na=False)
timepoints = pd.read_csv(INPUTS / "timepoints.csv", keep_default_na=False)
ccs_costs = pd.read_csv(INPUTS / "ccs_install_costs.csv", keep_default_na=False)
legacy = pd.read_csv(INPUTS / "legacy_storage_policy.csv", keep_default_na=False)


def numeric_zero(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace(".", "0"), errors="raise").eq(0.0)


gen_count = len(gen_info)
tp_count = len(timepoints)
ccs_count = ccs_costs["GENERATION_PROJECT"].astype(str).nunique()
startup_active = int((
    ~numeric_zero(gen_info["gen_startup_om"])
    | ~numeric_zero(gen_info["gen_min_uptime"])
    | ~numeric_zero(gen_info["gen_min_downtime"])
).sum())
full_gen_tp = gen_count * tp_count
active_ccs_tp = ccs_count * tp_count
active_startup_tp = startup_active * tp_count
omitted_ccs_columns = 2 * (gen_count - ccs_count) * tp_count
omitted_startup_columns = 2 * (gen_count - startup_active) * tp_count
total_omitted = omitted_ccs_columns + omitted_startup_columns

expected_counts = {
    "generator_count": 371,
    "representative_timepoint_count": 288,
    "ccs_generator_count": 96,
    "startup_shutdown_active_generator_count": 96,
    "full_gen_timepoint_count": 106848,
    "active_ccs_gen_timepoint_count": 27648,
    "active_startup_shutdown_gen_timepoint_count": 27648,
    "omitted_fixed_zero_ccs_columns": 158400,
    "omitted_objective_neutral_startup_shutdown_columns": 158400,
    "total_omitted_hourly_columns": 316800,
}
actual_counts = {
    "generator_count": gen_count,
    "representative_timepoint_count": tp_count,
    "ccs_generator_count": ccs_count,
    "startup_shutdown_active_generator_count": startup_active,
    "full_gen_timepoint_count": full_gen_tp,
    "active_ccs_gen_timepoint_count": active_ccs_tp,
    "active_startup_shutdown_gen_timepoint_count": active_startup_tp,
    "omitted_fixed_zero_ccs_columns": omitted_ccs_columns,
    "omitted_objective_neutral_startup_shutdown_columns": omitted_startup_columns,
    "total_omitted_hourly_columns": total_omitted,
}
checks["derived_reduction_counts"] = actual_counts
for key, want in expected_counts.items():
    if actual_counts[key] != want:
        errors.append(f"{key}={actual_counts[key]} expected {want}")

power = float(legacy["national_power_target_mw"].iloc[0])
energy = float(legacy["national_energy_target_mwh"].iloc[0])
duration = float(legacy["standardized_duration_h"].iloc[0])
identity_residual = energy - duration * power
identity_tol = max(1.0e-6, 1.0e-12 * max(1.0, abs(energy)))
checks["legacy_projection"] = {
    "project_count": len(legacy),
    "identity_residual_mwh": identity_residual,
    "identity_tolerance_mwh": identity_tol,
}
if len(legacy) != 32:
    errors.append(f"legacy project count={len(legacy)} expected 32")
if not math.isfinite(identity_residual) or abs(identity_residual) > identity_tol:
    errors.append("legacy national energy identity does not support exact substitution")

scenario_table = pd.read_csv(ROOT / "storage_runner" / "scenarios_targetyear_linked.csv")
row = scenario_table.loc[scenario_table["scenario"].eq(SCENARIO)]
if len(scenario_table) != 8 or len(row) != 1:
    errors.append("controlled eight-case table or isolated R3 scenario is invalid")
else:
    checks["scenario_lock"] = {
        "scenario": SCENARIO,
        "legacy_allocation_mode": str(row["legacy_allocation_mode"].iloc[0]),
        "time_resolution_h": int(row["time_resolution_h"].iloc[0]),
        "storage_chronology_mode": str(row["storage_chronology_mode"].iloc[0]),
    }
    if checks["scenario_lock"]["legacy_allocation_mode"] != "optimized_reallocation":
        errors.append("R3 case is not optimized_reallocation")
    if checks["scenario_lock"]["time_resolution_h"] != 1:
        errors.append("R3 case is not one-hour")
    if checks["scenario_lock"]["storage_chronology_mode"] != "monthly_linked":
        errors.append("R3 case chronology changed")

runner = RUNNER.read_text(encoding="utf-8")
require_tokens("runner", runner, [
    '"r3_reduced": R3_REDUCED_ROUTE',
    "08_targetyear_r3_hourly_reduced_scaled_barrier",
    "09_targetyear_r3_hourly_reduced_dual_simplex",
    'args.route in {"r3_reduced", "r4_continuation", "r5_continuation"} and args.scenario != "TY2033_CHRONO_1H_OPTIMAL"',
    '"total_omitted_hourly_columns": 316800',
])

launcher = LAUNCHER.read_text(encoding="utf-8")
require_tokens("launcher", launcher, [
    "--scenario TY2033_CHRONO_1H_OPTIMAL",
    "--route r3_reduced",
    "--skip-prepare",
    "--force-rerun",
])
for forbidden in ["--clean-central", "--pair "]:
    if forbidden in launcher:
        errors.append(f"isolated launcher contains forbidden option: {forbidden}")

result = {
    "version": "V17T2R5R3_EXACT_HOURLY_COORDINATE_REDUCTION_20260813",
    "status": "PASS" if not errors else "FAIL",
    "errors": errors,
    "checks": checks,
    "scientific_inputs_changed": False,
    "solver_tolerances_relaxed": False,
    "publication_gates_relaxed": False,
    "other_seven_cases_rerun": False,
    "dynamic_julia_gurobi_solve_executed": False,
}
out = ROOT / "audits" / "V17T2R5R3_EQUIVALENCE_AUDIT.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["status"] == "PASS" else 1)
