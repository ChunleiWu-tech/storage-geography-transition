#!/usr/bin/env python3
"""Focused static/equivalence gate for the R2 one-case projection."""
from __future__ import annotations

from pathlib import Path
import json
import math
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r5.jl"
SCENARIO = "TY2033_CHRONO_1H_OPTIMAL"
INPUTS = ROOT / "sensitivity_cases" / SCENARIO / "inputs"

errors: list[str] = []
checks: dict[str, object] = {}

model = MODEL.read_text(encoding="utf-8")
required_tokens = [
    'basename(case_dir) == "TY2033_CHRONO_1H_OPTIMAL"',
    '"V17T2R5R2_equivalent_projected_legacy_allocation_v2"',
    "STORAGE_ENERGY_VARIABLE_BLD_YRS",
    "PROJECTED_LEGACY_STORAGE_ENERGY_BLD_YRS",
    "function storage_energy_build(g, bld_yr)",
    "storage_energy_build(g, bld_yr)",
    ":legacy_energy_variable_projection_active",
    ":legacy_energy_variable_projection_count",
    ":legacy_projected_energy_output_reconstruction",
]
for token in required_tokens:
    present = token in model
    checks[f"model_token::{token}"] = present
    if not present:
        errors.append(f"missing R2 model token: {token}")

policy = pd.read_csv(INPUTS / "legacy_storage_policy.csv")
projects = int(len(policy))
power = float(policy["national_power_target_mw"].iloc[0])
energy = float(policy["national_energy_target_mwh"].iloc[0])
duration = float(policy["standardized_duration_h"].iloc[0])
caps = pd.to_numeric(policy["legacy_power_cap_mw"], errors="raise")
identity_residual = energy - duration * power
identity_tol = max(1.0e-6, 1.0e-12 * max(1.0, abs(energy)))

checks.update({
    "legacy_project_count": projects,
    "national_power_target_mw": power,
    "national_energy_target_mwh": energy,
    "standardized_duration_h": duration,
    "energy_identity_residual_mwh": identity_residual,
    "energy_identity_tolerance_mwh": identity_tol,
    "zone_power_cap_sum_mw": float(caps.sum()),
})
if projects != 32:
    errors.append(f"expected 32 legacy projects, found {projects}")
if not math.isfinite(identity_residual) or abs(identity_residual) > identity_tol:
    errors.append("national energy target is not exactly implied within controlled tolerance")
if float(caps.sum()) + 1.0e-9 < power:
    errors.append("sum of zone power caps is below the national power target")
if not (caps >= 0.0).all():
    errors.append("negative legacy zone power cap")

scenario_row = pd.read_csv(ROOT / "storage_runner" / "scenarios_targetyear_linked.csv")
scenario_row = scenario_row.loc[scenario_row["scenario"].eq(SCENARIO)]
if len(scenario_row) != 1:
    errors.append("R2 activation scenario is missing or duplicated")
else:
    checks["scenario_legacy_mode"] = str(scenario_row["legacy_allocation_mode"].iloc[0])
    checks["scenario_time_resolution_h"] = int(scenario_row["time_resolution_h"].iloc[0])
    if checks["scenario_legacy_mode"] != "optimized_reallocation":
        errors.append("R2 activation scenario is not optimized_reallocation")
    if checks["scenario_time_resolution_h"] != 1:
        errors.append("R2 activation scenario is not one-hour")

result = {
    "version": "V17T2R5R2_EQUIVALENT_PROJECTED_LEGACY_ENERGY_20260812",
    "status": "PASS" if not errors else "FAIL",
    "errors": errors,
    "checks": checks,
    "dynamic_julia_gurobi_solve_executed": False,
}
out = ROOT / "audits" / "V17T2R5R2_EQUIVALENCE_AUDIT.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["status"] == "PASS" else 1)
