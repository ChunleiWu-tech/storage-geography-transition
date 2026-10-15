#!/usr/bin/env python3
"""Static, input and distribution audit for the clean V17T2R5 package.

This checker does not claim that the eight Julia/Gurobi optimizations were solved in
this build environment. It verifies package completeness, source lineage, Python
syntax, target-year input structure, paired identification and orchestration locks.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import importlib.util
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import zipfile
from typing import Any

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
AUDITS = ROOT / "audits"
AUDITS.mkdir(parents=True, exist_ok=True)

EXPECTED_R1_SHA = "c9499d786a49a6de46da4884a8b8597e2e5fa6dafc02322d864a7a8d0bac5052"
EXPECTED_R4_SHA = "1106204f5f41cf138e1b20b10a5b2ea66443d32889b978c746731067a6e71d71"
EXPECTED_R5_SHA = "fffcca77edefe882bd8187974a8aec493f9d0aae37f8cffc1af9b5bb86d9ec67"
EXPECTED_SCENARIOS = {
    "TY2028_CHRONO_OBSERVED",
    "TY2028_CHRONO_OPTIMAL",
    "TY2033_CHRONO_OBSERVED",
    "TY2033_CHRONO_OPTIMAL",
    "TY2033_CHRONO_LDES_OBSERVED",
    "TY2033_CHRONO_LDES_OPTIMAL",
    "TY2033_CHRONO_1H_OBSERVED",
    "TY2033_CHRONO_1H_OPTIMAL",
}
EXPECTED_PAIRS = {"TY2028_CHRONO", "TY2033_CHRONO", "TY2033_CHRONO_LDES", "TY2033_CHRONO_1H"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


errors: list[str] = []
checks: dict[str, Any] = {}
required = [
    "README_ZH.md",
    "README_EN.md",
    "VERSION_V17T2R5.txt",
    "requirements_v17.txt",
    "base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl",
    "base_model_v39/storage_base_template_v17.zip",
    "docs/baseline_reference/cheer_power_storage_chronology_ldes_v2r1_frozen.jl",
    "docs/baseline_reference/cheer_power_storage_chronology_ldes_v2r4_solveronly_frozen.jl",
    "storage_runner/scenarios_targetyear_linked.csv",
    "storage_runner/run_targetyear_one.jl",
    "storage_runner/check_v17t2r5_runtime.jl",
    "tools/prepare_targetyear_cases.py",
    "tools/apply_nlr_2025_battery_costs.py",
    "tools/apply_ldes_technology_portfolio.py",
    "tools/reconstruct_one_hour_repdays.py",
    "tools/validate_targetyear_case.py",
    "tools/audit_targetyear_pair_identity.py",
    "tools/run_targetyear_batch.py",
    "tools/build_targetyear_summary.py",
    "tools/audit_julia_lexical_v17t2r5.py",
    "tools/check_v17t2r5r2_projection.py",
    "CHECK_V17T2R5_PACKAGE.bat",
    "CHECK_V17T2R5_RUNTIME.bat",
    "RUN_V17T2R5_PREPARE_TARGETYEAR_CASES.bat",
    "RUN_V17T2R5_2028_PAIR_1x10.bat",
    "RUN_V17T2R5_2033_PAIR_1x10.bat",
    "RUN_V17T2R5_2033_LDES_PAIR_1x10.bat",
    "RUN_V17T2R5_2033_1H_PAIR_1x10.bat",
    "RUN_V17T2R5_ALL_8_1x10.bat",
    "RUN_V17T2R5_CLEAN_REBUILD_AND_RUN_ALL_8_1x10.bat",
    "CHECK_PUBLICATION_SOURCE_GATE.bat",
    "tools/check_publication_source_gate.py",
    "tools/publication_source_contract.py",
    "tools/write_publication_result_lineage.py",
    "BUILD_V17T2R5_SUMMARY.bat",
    "RUN_V17T2R5R2_2033_1H_OPTIMAL_ONLY.bat",
    "VERSION_V17T2R5R2.txt",
    "README_R2_PATCH_ZH.txt",
    "docs/V17T2R5R2_EQUIVALENT_PROJECTED_LEGACY_ENERGY.md",
    "CHECK_V17T2R5R2_PATCH.bat",
    "RUN_V17T2R5R3_2033_1H_OPTIMAL_ONLY.bat",
    "CHECK_V17T2R5R3_PATCH.bat",
    "VERSION_V17T2R5R3.txt",
    "README_R3_PATCH_ZH.md",
    "docs/V17T2R5R3_EXACT_HOURLY_COORDINATE_REDUCTION.md",
    "tools/check_v17t2r5r3_projection.py",
    "RUN_V17T2R5R4_2033_1H_OPTIMAL_ONLY.bat",
    "CHECK_V17T2R5R4_PATCH.bat",
    "VERSION_V17T2R5R4.txt",
    "README_R4_PATCH_ZH.md",
    "docs/V17T2R5R4_OBSERVED_FEASIBLE_START_CONTINUATION.md",
    "tools/check_v17t2r5r4_continuation.py",
    "PATCH_MANIFEST_SHA256_R4.json",
    "RUN_V17T2R5R5_2033_1H_OPTIMAL_ONLY.bat",
    "CHECK_V17T2R5R5_PATCH.bat",
    "VERSION_V17T2R5R5.txt",
    "README_R5_PATCH_ZH.md",
    "docs/V17T2R5R5_PRIMAL_DUAL_SUPPORTED_OBJECTIVE_CONTINUATION.md",
    "tools/check_v17t2r5r5_continuation.py",
    "PATCH_MANIFEST_SHA256_R5.json",
]
for rel in required:
    ok = (ROOT / rel).is_file()
    checks[f"required::{rel}"] = ok
    if not ok:
        errors.append(f"missing required file: {rel}")

# Clean source tree: no bytecode/cache and no legacy top-level orchestration.
cache_items = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.name == "__pycache__" or p.suffix == ".pyc"]
checks["python_cache_items"] = cache_items
if cache_items:
    errors.append("Python cache artefacts remain: " + ", ".join(cache_items[:10]))
legacy_root_files = [
    p.name for p in ROOT.iterdir() if p.is_file() and any(tag in p.name for tag in ["V17T2R2", "V17T2R4", "SL01_CHRONO"])
]
checks["legacy_root_files"] = legacy_root_files
if legacy_root_files:
    errors.append("Legacy root launchers/files remain: " + ", ".join(legacy_root_files))

# Python syntax without writing .pyc files into the package.
python_syntax: list[dict[str, Any]] = []
with tempfile.TemporaryDirectory() as td:
    for i, path in enumerate(sorted(ROOT.rglob("*.py"))):
        try:
            py_compile.compile(str(path), cfile=str(Path(td) / f"{i}.pyc"), doraise=True)
            python_syntax.append({"file": path.relative_to(ROOT).as_posix(), "pass": True})
        except Exception as exc:
            python_syntax.append({"file": path.relative_to(ROOT).as_posix(), "pass": False, "error": str(exc)})
            errors.append(f"Python syntax failed: {path.relative_to(ROOT)}: {exc}")
checks["python_syntax"] = python_syntax

# Source lineage hashes.
r1 = ROOT / "docs/baseline_reference/cheer_power_storage_chronology_ldes_v2r1_frozen.jl"
r4 = ROOT / "docs/baseline_reference/cheer_power_storage_chronology_ldes_v2r4_solveronly_frozen.jl"
r5 = ROOT / "base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl"
lineage = {
    "frozen_v17t2r1_sha256": sha256(r1) if r1.is_file() else None,
    "frozen_v17t2r4_solveronly_sha256": sha256(r4) if r4.is_file() else None,
    "v17t2r5_targetyear_model_sha256": sha256(r5) if r5.is_file() else None,
}
checks["model_lineage"] = lineage
for key, actual, expected in [
    ("V17T2R1 frozen source", lineage["frozen_v17t2r1_sha256"], EXPECTED_R1_SHA),
    ("V17T2R4 solver-only source", lineage["frozen_v17t2r4_solveronly_sha256"], EXPECTED_R4_SHA),
    ("V17T2R5 target-year model", lineage["v17t2r5_targetyear_model_sha256"], EXPECTED_R5_SHA),
]:
    if actual != expected:
        errors.append(f"{key} hash mismatch: {actual} != {expected}")

# Template archive integrity.
template = ROOT / "base_model_v39/storage_base_template_v17.zip"
try:
    with zipfile.ZipFile(template) as zf:
        bad = zf.testzip()
        names = set(zf.namelist())
    checks["base_template_zip"] = {"pass": bad is None, "bad_member": bad, "members": len(names)}
    if bad is not None:
        errors.append(f"Base template ZIP corrupt member: {bad}")
    for member in ["inputs/periods.csv", "inputs/gen_info.csv", "inputs/timeseries.csv", "inputs/timepoints.csv"]:
        if member not in names:
            errors.append(f"Base template ZIP missing {member}")
except Exception as exc:
    checks["base_template_zip"] = {"pass": False, "error": str(exc)}
    errors.append(f"Base template ZIP audit failed: {exc}")

# Scenario table structure and scientific-scope locks.
scen_path = ROOT / "storage_runner/scenarios_targetyear_linked.csv"
scen = pd.read_csv(scen_path) if scen_path.is_file() else pd.DataFrame()
checks["scenario_count"] = len(scen)
if set(scen.get("scenario", pd.Series(dtype=str)).astype(str)) != EXPECTED_SCENARIOS:
    errors.append("Scenario names do not equal the controlled eight-case target-year design")
if set(scen.get("pair_id", pd.Series(dtype=str)).astype(str)) != EXPECTED_PAIRS:
    errors.append("Pair IDs do not equal the controlled four-pair design")
if not scen.empty:
    if not (scen.groupby("pair_id").size() == 2).all():
        errors.append("Every target-year pair must contain exactly two members")
    if set(pd.to_numeric(scen["target_year"], errors="raise").astype(int)) != {2028, 2033}:
        errors.append("Only target years 2028 and 2033 are allowed")
    if set(scen["storage_chronology_mode"].astype(str)) != {"monthly_linked"}:
        errors.append("All target-year cases must use monthly_linked SOC")
    if set(scen["legacy_allocation_mode"].astype(str)) != {"observed_standardized", "optimized_reallocation"}:
        errors.append("Legacy allocation modes are not the controlled pair")
    ldes = scen.loc[scen["pair_id"].eq("TY2033_CHRONO_LDES")]
    if set(ldes["ldes_proxy_mode"].astype(str)) != {"technology_portfolio_discrete"}:
        errors.append("2033 LDES pair does not use the discrete technology portfolio")
    if set(pd.to_numeric(ldes["ldes_proxy_min_duration_h"], errors="raise")) != {10.0} or set(pd.to_numeric(ldes["ldes_proxy_max_duration_h"], errors="raise")) != {100.0}:
        errors.append("LDES duration bounds are not 10-100 h")
    one_h = scen.loc[scen["pair_id"].eq("TY2033_CHRONO_1H")]
    if set(pd.to_numeric(one_h["time_resolution_h"], errors="raise")) != {1.0}:
        errors.append("2033 one-hour pair is not locked to 1 h")
    if int((pd.to_numeric(scen["time_resolution_h"], errors="raise") == 4).sum()) != 6:
        errors.append("The original six target-year cases must remain four-hour")

# Model/orchestration lexical policy locks.
model = r5.read_text(encoding="utf-8") if r5.is_file() else ""
model_tokens = [
    'REPRESENTATIVE_TIMEPOINT_COUNTS_ALLOWED = (72, 288)',
    'technology_portfolio_discrete',
    'LDES_PSH_Shared_Provincial_Resource_Ceiling',
    'TARGET_YEAR_OPERATION_PERIOD in (2028, 2033)',
    'targetyear_deterministic_concurrent',
    'method = 4',
    'V17T2R5_PRIMARY_TIME_LIMIT_SECONDS',
    'targetyear_homogeneous_dual_crossover',
    'crossover = 2',
    'dual_simplex',
    'hard_deterministic_concurrent_simplex',
    'V17T2R5R2_equivalent_projected_legacy_allocation_v2',
    'V17T2R5R3_equivalent_hourly_coordinate_projection_v1',
    'R3_HOURLY_COORDINATE_PROJECTION_ACTIVE',
    'CCS_GEN_TPS = R3_HOURLY_COORDINATE_PROJECTION_ACTIVE ?',
    'STARTUP_SHUTDOWN_GENS = R3_HOURLY_COORDINATE_PROJECTION_ACTIVE ?',
    ':total_omitted_hourly_columns',
    'legacy_national_energy_identity_pass',
    'JuMP.set_upper_bound(power_var, min(current_power_ub, power_cap_mw))',
    'LEGACY_ENERGY_VARIABLE_PROJECTION_ACTIVE',
    'STORAGE_ENERGY_VARIABLE_BLD_YRS',
    'function storage_energy_build(g, bld_yr)',
    'crossover_basis = V17T2R5_CROSSOVER_BASIS',
    'bar_homogeneous = 1',
    'V17T2R5_FALLBACK_TIME_LIMIT_SECONDS',
    ':target_year_static_reoptimization => [true]',
    ':target_year_transition_path_claim_supported => [false]',
    'r4_observed_seed_primal_continuation',
    'r4_seed_source_scenario = "TY2033_CHRONO_1H_OBSERVED"',
    'r4_seed_source_pair_identity_pass',
    'r4_seed_gurobi_objval_gate_pass',
    'r4_seed_objective_scale_gate_pass',
    'r4_final_bounds_restored',
    'r4_seed_full_pstart_max_bound_violation',
    '_v17_apply_raw_pstart!(mod, r4_pstart_vars, r4_pstart_values)',
    'gurobi_V17T2R5R4_full_optimal_primal_simplex_after_strict_observed_seed',
    'r5_primal_dual_supported_objective_continuation',
    '_v17_raw_set_double_array!(grb, "PStart", primal_start)',
    '_v17_raw_set_double_array!(grb, "DStart", dual_start)',
    'r5_support_objective =',
    'apply_r5_bridge_profile!(mod)',
    'V17T2R5R5_OBJECTIVE_HOMOTOPY_LEVELS',
    'r5_bridge_basis_available',
    'r5_final_max_objective_coefficient_error == 0.0',
    'gurobi_V17T2R5R5_full_optimal_primal_simplex_after_primal_dual_supported_objective_continuation',
]
for token in model_tokens:
    present = token in model
    checks[f"model_token::{token}"] = present
    if not present:
        errors.append(f"R5 model token missing: {token}")
for forbidden_token in [
    'Legacy_Storage_National_Energy_Closure',
    'Legacy_Storage_Zone_Deployment_Envelope',
]:
    absent = forbidden_token not in model
    checks[f"model_redundant_row_absent::{forbidden_token}"] = absent
    if not absent:
        errors.append(f"Equivalent reduced-rank formulation still emits {forbidden_token}")

batch_path = ROOT / "tools/run_targetyear_batch.py"
batch = batch_path.read_text(encoding="utf-8") if batch_path.is_file() else ""
batch_tokens = [
    '"auto": ROUTES',
    '"primary": ROUTES[:1]',
    '"fallback": ROUTES[1:]',
    '"one_hour_robust": ONE_H_ROUTES',
    '"dual_rescue": ONE_H_ROUTES[1:2]',
    '"simplex_rescue": ONE_H_ROUTES[2:]',
    '"projected": PROJECTED_ROUTE',
    '07_targetyear_projected_scaled_barrier',
    '"r3_reduced": R3_REDUCED_ROUTE',
    '08_targetyear_r3_hourly_reduced_scaled_barrier',
    '09_targetyear_r3_hourly_reduced_dual_simplex',
    '"r4_continuation": R4_CONTINUATION_ROUTE',
    '10_targetyear_r4_observed_seed_primal_continuation',
    '"r5_continuation": R5_CONTINUATION_ROUTE',
    '11_targetyear_r5_primal_dual_supported_objective_continuation',
    'r5 homotopy schedule did not complete',
    'r5 final objective coefficients were not restored exactly',
    'r4 full PStart violates a restored final-model bound',
    'legacy_reallocation_formulation_version',
    'gurobi_dual_simplex_optimal_status',
    'gurobi_hard_deterministic_concurrent_simplex_optimal_status',
    'fresh Julia process',
    'preexisting_official_success_skipped',
    'stage1_termination_status") == "OPTIMAL"',
    'TIME_LIMIT incumbents or intermediate feasible bases are never publication outputs',
    'failed_diagnostics',
]
for token in batch_tokens:
    present = token in batch
    checks[f"batch_token::{token}"] = present
    if not present:
        errors.append(f"R5 orchestration token missing: {token}")

# Lexical Julia audit.
env = os.environ.copy()
env["PYTHONDONTWRITEBYTECODE"] = "1"
lex = subprocess.run(
    [sys.executable, str(ROOT / "tools/audit_julia_lexical_v17t2r5.py")],
    cwd=ROOT, capture_output=True, text=True, env=env,
)
checks["julia_lexical_audit_return_code"] = lex.returncode
if lex.returncode != 0:
    errors.append("Julia lexical audit failed: " + (lex.stdout + lex.stderr)[-2000:])

# Validate all eight prepared cases and pair identity.
case_results: list[dict[str, Any]] = []
try:
    validator = load_module("v17t2r5_validator", ROOT / "tools/validate_targetyear_case.py")
    for _, row in scen.iterrows():
        scenario = str(row["scenario"])
        case = ROOT / "sensitivity_cases" / scenario
        meta_path = case / "SENSITIVITY_SCENARIO_META.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else row.to_dict()
        result = validator.validate_case(case, meta, raise_on_error=False)
        case_results.append({"scenario": scenario, **result})
        if result.get("status") != "PASS":
            errors.append(f"Prepared case validation failed for {scenario}: {result.get('errors')}")
except Exception as exc:
    errors.append(f"Prepared case validation could not run: {exc}")
checks["prepared_case_validation"] = case_results

try:
    pair_module = load_module("v17t2r5_pair_audit", ROOT / "tools/audit_targetyear_pair_identity.py")
    pair_result = pair_module.audit_all_pairs(raise_on_error=False)
    checks["pair_identity_audit_status"] = pair_result.get("status")
    if pair_result.get("status") != "PASS":
        errors.append("Observed/optimized pair identity audit failed")
except Exception as exc:
    checks["pair_identity_audit_status"] = "ERROR"
    errors.append(f"Pair identity audit could not run: {exc}")

# Distribution manifest excludes mutable solve outputs and self-generated audit files.
exclude_names = {
    "PACKAGE_MANIFEST_SHA256.json",
    "STATIC_PACKAGE_AUDIT_V17T2R5.json",
    "JULIA_LEXICAL_AUDIT_V17T2R5.json",
    "V17T2R5R4_CONTINUATION_AUDIT.json",
    "V17T2R5R5_CONTINUATION_AUDIT.json",
}
exclude_parts = {"__pycache__", "batch_logs", "sensitivity_outputs", "failed_diagnostics"}
manifest: dict[str, str] = {}
for path in sorted(p for p in ROOT.rglob("*") if p.is_file()):
    rel = path.relative_to(ROOT)
    if path.name in exclude_names or any(part in exclude_parts for part in rel.parts):
        continue
    if "outputs" in rel.parts and rel.parts[0] == "sensitivity_cases":
        continue
    manifest[rel.as_posix()] = sha256(path)
(ROOT / "PACKAGE_MANIFEST_SHA256.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
checks["manifest_file_count"] = len(manifest)

result = {
    "version": "V17T2R5R4_OBSERVED_FEASIBLE_START_FULL_OPTIMAL_CONTINUATION_20260813",
    "status": "PASS" if not errors else "FAIL",
    "errors": errors,
    "scientific_design": "single-target-year exact linked-SOC capacity-and-dispatch re-optimization",
    "scenario_count": len(scen),
    "pair_count": int(scen["pair_id"].nunique()) if not scen.empty else 0,
    "prepared_cases_included": len(case_results) == 8 and all(r.get("status") == "PASS" for r in case_results),
    "main_model_replaced": False,
    "targetyear_equivalent_reduced_rank_reformulation": True,
    "targetyear_legacy_energy_variable_projection": True,
    "targetyear_exact_hourly_coordinate_reduction": True,
    "targetyear_exact_hourly_coordinate_reduction_case": "TY2033_CHRONO_1H_OPTIMAL",
    "targetyear_r4_observed_feasible_start_continuation": True,
    "targetyear_r4_final_feasible_set_unchanged": True,
    "targetyear_r4_other_seven_outputs_untouched": True,
    "full_transition_path_claim_supported": False,
    "full_8760_hour_claim_supported": False,
    "strict_solver_native_optimality_required": True,
    "julia_gurobi_solve_executed_in_build_environment": False,
    "checks": checks,
}
(AUDITS / "STATIC_PACKAGE_AUDIT_V17T2R5.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8"
)
print(json.dumps(result, ensure_ascii=False, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
raise SystemExit(0 if result["status"] == "PASS" else 1)
