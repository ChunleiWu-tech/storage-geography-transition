#!/usr/bin/env python3
"""Run V17T2R6 full-8760 validations with controlled exact LP routes.

R7 adds an operationally isolated two-scenario scheduler: at most two full-8760
Julia/Gurobi processes run simultaneously, each with exactly 10 solver threads
when --max-parallel=2. Pair members share the same pre-specified solver ladder.

Route 1: standard scaled barrier without crossover, 12 h default.
Route 2: homogeneous/numerically focused barrier without crossover, 24 h default.

The previous deterministic-concurrent and barrier-with-crossover routes remain in
the model for explicit diagnostics, but are not automatic publication routes.

Every route starts in a fresh Julia process. Only a solver-native OPTIMAL solution
that passes all physical, chronology, identification and export gates is promoted.
TIME_LIMIT incumbents or intermediate feasible bases are never publication outputs.

HF3 adds a distinct, primary-profile-only route label for the algebraically
projected formulation. Its canonical launcher runs serially and assigns the old
12 h + 24 h ladder budget to one uninterrupted 36 h primary barrier solve.
"""
from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCEN = ROOT / "storage_runner" / "scenarios_targetyear_linked.csv"
LOGS = ROOT / "batch_logs"
CENTRAL = ROOT / "sensitivity_outputs"
ATTEMPTS = CENTRAL / "_attempts"
RUN_LOCKS = ROOT / "run_locks"
SUMMARY_CSV = CENTRAL / "V17T2R6_FULL8760_run_summary.csv"
SUMMARY_JSON = CENTRAL / "V17T2R6_FULL8760_run_summary.json"
ROUTES = [
    ("targetyear_scaled_barrier_nocrossover", "__01_full8760_scaled_barrier_nocrossover", "01_full8760_scaled_barrier_nocrossover"),
    ("targetyear_homogeneous_barrier_nocrossover", "__02_full8760_homogeneous_barrier_nocrossover", "02_full8760_homogeneous_barrier_nocrossover"),
]
HF3_PROJECTED_ROUTES = [
    ("targetyear_scaled_barrier_nocrossover", "__03_full8760_hf3_projected_scaled_barrier", "03_full8760_hf3_projected_scaled_barrier"),
]
HF4_CONTINUATION_ROUTES = [
    ("full8760_primal_dual_supported_objective_continuation", "__04_full8760_hf4_primal_dual_supported_objective_continuation", "04_full8760_hf4_primal_dual_supported_objective_continuation"),
]
# HF5 retains the exact HF4 target-model continuation contract but writes to a
# separate attempt/output location.  Its only numerical change is a direct
# primal-simplex basis bridge from the complete seed PStart/DStart, avoiding
# the Gurobi 10.0.1 crossover routine that crashed after a certified seed.
HF5_SIMPLEX_BRIDGE_ROUTES = [
    ("full8760_primal_dual_supported_objective_continuation", "__05_full8760_hf5_primal_dual_start_simplex_basis_no_crossover", "05_full8760_hf5_primal_dual_start_simplex_basis_no_crossover"),
]
HF6_DUAL_SIMPLEX_BRIDGE_ROUTES = [
    ("full8760_primal_dual_supported_objective_continuation", "__06_full8760_hf6_dual_start_only_dual_simplex_no_crossover", "06_full8760_hf6_dual_start_only_dual_simplex_no_crossover"),
]
HF7_RESTRICTED_FACE_ROUTES = [
    ("full8760_restricted_face_continuation", "__07_full8760_hf7_restricted_face_continuation", "07_full8760_hf7_restricted_face_continuation"),
]
ROUTE_SELECTIONS = {
    "auto": ROUTES,
    "primary": ROUTES[:1],
    "fallback": ROUTES[1:],
    "hf3": HF3_PROJECTED_ROUTES,
    "hf4_continuation": HF4_CONTINUATION_ROUTES,
    "hf5_simplex_bridge": HF5_SIMPLEX_BRIDGE_ROUTES,
    "hf6_dual_simplex_bridge": HF6_DUAL_SIMPLEX_BRIDGE_ROUTES,
    "hf7_restricted_face": HF7_RESTRICTED_FACE_ROUTES,
}

# Operational-only concurrency plan. It does not alter any scientific input or
# solver parameter. Each wave contains the two members of one identification
# pair, so observed/optimized members receive the same wall-clock budget and
# the same 10-thread solver policy when launched by the R7 2x10 entry point.
PARALLEL_WAVES = [
    ["TY2033_FULL8760_OBSERVED", "TY2033_FULL8760_OPTIMAL"],
    ["TY2033_FULL8760_LDES_OBSERVED", "TY2033_FULL8760_LDES_OPTIMAL"],
]


def truth(v: Any) -> bool:
    return str(v).strip().lower() in {"true", "1", "yes", "y", "t"}


def fnum(v: Any, default: float = float("nan")) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def read_one_csv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        df = pd.read_csv(path)
        if len(df) != 1:
            return {}
        return {str(k): str(v) for k, v in df.iloc[0].to_dict().items()}
    except Exception:
        return {}


def acquire_scenario_lease(row: dict[str, Any], force_rerun: bool) -> tuple[Path | None, dict[str, Any] | None]:
    """Atomically claim one scenario or wait for its other process to promote.

    Directory creation is atomic on Windows.  This lets the serial HF4 launcher
    and the optional LDES parallel companion coexist without ever solving or
    promoting the same scenario twice.
    """
    scenario = str(row["scenario"])
    RUN_LOCKS.mkdir(parents=True, exist_ok=True)
    lease = RUN_LOCKS / f"{scenario}.lock"
    wait_limit = float(os.environ.get("V17T2R6_SCENARIO_LOCK_WAIT_SECONDS", "604800"))
    poll_seconds = max(2.0, float(os.environ.get("V17T2R6_SCENARIO_LOCK_POLL_SECONDS", "20")))
    started = time.time()
    announced = False
    while True:
        if not force_rerun:
            existing = existing_official_record(row)
            if existing is not None:
                return None, existing
        try:
            lease.mkdir()
            owner = {
                "scenario": scenario,
                "pid": os.getpid(),
                "acquired_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            (lease / "owner.json").write_text(
                json.dumps(owner, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            return lease, None
        except FileExistsError:
            if not announced:
                print(f"Scenario {scenario} is active in another coordinator; waiting for strict promotion.")
                announced = True
            if time.time() - started > wait_limit:
                raise TimeoutError(
                    f"Timed out waiting for scenario lease {lease}. Verify the owning Julia/Python process; "
                    "remove the lock only after confirming that process is no longer running."
                )
            time.sleep(poll_seconds)


def release_scenario_lease(lease: Path | None) -> None:
    if lease is None or not lease.is_dir():
        return
    owner_path = lease / "owner.json"
    try:
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
    except Exception:
        owner = {}
    if int(owner.get("pid", -1)) != os.getpid():
        raise RuntimeError(f"Refusing to release a scenario lease owned by another process: {lease}")
    shutil.rmtree(lease)


def local_output(scenario: str, suffix: str) -> Path:
    return ROOT / "sensitivity_cases" / scenario / "outputs" / f"{scenario}{suffix}"


def run_cmd(cmd: list[str], log: Path) -> tuple[int, float]:
    log.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    env = os.environ.copy()
    env.setdefault("V17_SOLVER_THREADS", "10")
    env.setdefault("V17T2R6_8760_PRIMARY_TIME_LIMIT_SECONDS", "43200")
    env.setdefault("V17T2R6_8760_FALLBACK_TIME_LIMIT_SECONDS", "86400")
    env.setdefault("V17T2R6_8760_PRIMARY_BAR_ITER_LIMIT", "100000")
    env.setdefault("V17T2R6_8760_FALLBACK_BAR_ITER_LIMIT", "100000")
    env.setdefault("V17T2R6_8760_CROSSOVER_BASIS", "1")
    env.setdefault("V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS", "129600")
    env.setdefault("V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS", "21600")
    env.setdefault("V17T2R6R9_HF4_STAGE_TIME_LIMIT_SECONDS", "21600")
    env.setdefault("V17T2R6R9_HF4_FINAL_TIME_LIMIT_SECONDS", "129600")
    with log.open("w", encoding="utf-8", errors="replace") as fh:
        fh.write("COMMAND: " + " ".join(cmd) + "\n")
        fh.write("START: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
        fh.write("ENV: V17_SOLVER_THREADS=" + env["V17_SOLVER_THREADS"] +
                 " V17T2R6_8760_PRIMARY_TIME_LIMIT_SECONDS=" + env["V17T2R6_8760_PRIMARY_TIME_LIMIT_SECONDS"] +
                 " V17T2R6_8760_FALLBACK_TIME_LIMIT_SECONDS=" + env["V17T2R6_8760_FALLBACK_TIME_LIMIT_SECONDS"] +
                 " V17T2R6_8760_PRIMARY_BAR_ITER_LIMIT=" + env["V17T2R6_8760_PRIMARY_BAR_ITER_LIMIT"] +
                 " V17T2R6_8760_FALLBACK_BAR_ITER_LIMIT=" + env["V17T2R6_8760_FALLBACK_BAR_ITER_LIMIT"] +
                 " V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS=" + env["V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS"] +
                 " V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS=" + env["V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS"] +
                 " V17T2R6R9_HF4_STAGE_TIME_LIMIT_SECONDS=" + env["V17T2R6R9_HF4_STAGE_TIME_LIMIT_SECONDS"] +
                 " V17T2R6R9_HF4_FINAL_TIME_LIMIT_SECONDS=" + env["V17T2R6R9_HF4_FINAL_TIME_LIMIT_SECONDS"] + "\n\n")
        fh.flush()
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, text=True, env=env)
        rc = proc.wait()
        fh.write("\nEND: " + time.strftime("%Y-%m-%d %H:%M:%S") + f"\nRETURN_CODE: {rc}\n")
    return rc, time.time() - start


def preserve_attempt(scenario: str, label: str, suffix: str) -> tuple[Path, bool]:
    src = local_output(scenario, suffix)
    dst = ATTEMPTS / scenario / label
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "NO_LOCAL_OUTPUT.txt").write_text("Julia process created no output directory.\n", encoding="utf-8")
        return dst, False
    shutil.copytree(src, dst)
    return dst, True


def promote_success(scenario: str, src: Path) -> Path:
    dst = CENTRAL / f"{scenario}__main"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    from publication_source_common import write_result_fingerprint
    write_result_fingerprint(ROOT, dst, ROOT / "sensitivity_cases" / scenario, scenario, "sensitivity")
    return dst


def profile_gate(status: dict[str, str]) -> bool:
    profile = status.get("solver_profile", "")
    if profile == "targetyear_scaled_barrier_nocrossover":
        return bool(
            status.get("solver_method") in {"2", "2.0"}
            and status.get("solver_crossover") in {"0", "0.0"}
            and status.get("solver_bar_homogeneous") in {"0", "0.0"}
            and status.get("solver_route_role") == "V17T2R6_full8760_primary_scaled_barrier_nocrossover"
            and fnum(status.get("solver_numeric_focus")) == 2.0
            and fnum(status.get("solver_scale_flag")) == -1.0
        )
    if profile == "targetyear_homogeneous_barrier_nocrossover":
        return bool(
            status.get("solver_method") in {"2", "2.0"}
            and status.get("solver_crossover") in {"0", "0.0"}
            and status.get("solver_bar_homogeneous") in {"1", "1.0"}
            and status.get("solver_route_role") == "V17T2R6_full8760_fallback_homogeneous_barrier_nocrossover"
            and fnum(status.get("solver_numeric_focus")) == 3.0
            and fnum(status.get("solver_scale_flag")) == 2.0
        )
    if profile == "full8760_primal_dual_supported_objective_continuation":
        return bool(
            status.get("solver_method") in {"0", "0.0"}
            and status.get("solver_crossover") in {"0", "0.0"}
            and status.get("solver_lpwarmstart") in {"1", "1.0"}
            and status.get("solver_route_role") in {
                "V17T2R6R9_HF4_full8760_primal_dual_supported_exact_objective_continuation",
                "V17T2R6R10_HF5_full8760_primal_dual_start_simplex_basis_no_crossover_exact_objective_continuation",
                "V17T2R6R11_HF6_full8760_dual_start_only_dual_simplex_no_crossover_exact_objective_continuation",
            }
            and fnum(status.get("solver_numeric_focus")) == 3.0
            and fnum(status.get("solver_scale_flag")) == 2.0
            and fnum(status.get("solver_presolve")) == 0.0
            and fnum(status.get("solver_aggregate")) == 0.0
            and fnum(status.get("solver_pre_sparsify")) == 0.0
            and fnum(status.get("solver_quad")) == 1.0
        )
    if profile == "full8760_restricted_face_continuation":
        return bool(
            status.get("solver_method") in {"0", "0.0"}
            and status.get("solver_crossover") in {"0", "0.0"}
            and status.get("solver_lpwarmstart") in {"1", "1.0"}
            and status.get("solver_route_role") ==
                "V17T2R6R12_HF7_full8760_restricted_face_exact_objective_continuation"
            and fnum(status.get("solver_numeric_focus")) == 3.0
            and fnum(status.get("solver_scale_flag")) == 2.0
            and fnum(status.get("solver_presolve")) == 0.0
            and fnum(status.get("solver_aggregate")) == 0.0
            and fnum(status.get("solver_pre_sparsify")) == 0.0
            and fnum(status.get("solver_quad")) == 1.0
        )
    return False


def native_certificate_gate(status: dict[str, str]) -> bool:
    accepted = {
        "gurobi_V17T2R6_full8760_targetyear_scaled_barrier_nocrossover_optimal_status",
        "gurobi_V17T2R6_full8760_targetyear_homogeneous_barrier_nocrossover_optimal_status",
        "gurobi_V17T2R6R9_HF4_full8760_original_objective_optimal_after_primal_dual_supported_continuation",
        "gurobi_V17T2R6R10_HF5_full8760_original_objective_optimal_after_primal_dual_start_no_crossover_simplex_basis_continuation",
        "gurobi_V17T2R6R11_HF6_full8760_original_objective_optimal_after_dual_start_only_no_crossover_dual_simplex_basis_continuation",
        "gurobi_V17T2R6R12_HF7_full8760_original_objective_optimal_after_restricted_face_continuation",
    }
    return bool(
        status.get("stage1_economic_optimality_proof_source") in accepted
        and status.get("stage1_certificate_grade") == "strict_solver_native"
        and truth(status.get("stage1_native_solver_certificate_pass"))
        and truth(status.get("stage1_native_algorithm_gate_pass"))
        and truth(status.get("stage1_objective_scale_gate_pass"))
        and truth(status.get("stage1_gurobi_status_gate_pass"))
        and truth(status.get("stage1_gurobi_objval_gate_pass"))
    )


def chronology_gate(outdir: Path, status: dict[str, str], expected: dict[str, Any]) -> tuple[bool, list[str], dict[str, float]]:
    reasons: list[str] = []
    maxima: dict[str, float] = {}
    if status.get("storage_chronology_mode") != "full_year_cyclic":
        reasons.append("storage_chronology_mode is not full_year_cyclic")
    if status.get("ldes_proxy_mode") != str(expected["ldes_proxy_mode"]):
        reasons.append(f"ldes_proxy_mode={status.get('ldes_proxy_mode')} expected {expected['ldes_proxy_mode']}")
    if not truth(status.get("storage_interperiod_soc_linked")):
        reasons.append("storage_interperiod_soc_linked=false")
    if not truth(status.get("storage_full_chronological_claim_supported")):
        reasons.append("storage_full_chronological_claim_supported=false")
    p = outdir / "storage_chronology_audit.csv"
    if not p.is_file():
        reasons.append("missing storage_chronology_audit.csv")
    else:
        try:
            df = pd.read_csv(p)
            for col in [
                "cyclic_closure_residual_mwh", "maximum_absolute_step_residual_mwh",
                "lower_bound_violation_mwh", "upper_bound_violation_mwh",
            ]:
                if col in df.columns:
                    val = float(pd.to_numeric(df[col], errors="coerce").abs().max())
                    maxima[col] = val
                    if not math.isfinite(val) or val > 0.10:
                        reasons.append(f"max {col}={val} MWh > 0.10")
        except Exception as exc:
            reasons.append(f"chronology audit read error: {exc}")
    return not reasons, reasons, maxima


def strict_success(status: dict[str, str], rc: int, preserved: bool, outdir: Path, expected: dict[str, Any]) -> tuple[bool, list[str], dict[str, float]]:
    reasons: list[str] = []
    required = [
        "solve_status.csv", "physical_audit_summary.csv", "storage_chronology_audit.csv",
        "storage_operation_audit.csv", "legacy_storage_allocation_audit.csv",
        "BuildGen.csv", "BuildStorageEnergy.csv", "BuildTx.csv", "ldes_proxy_build.csv",
        "electricity_cost.csv", "scenario_config.json", "RESULT_INTERPRETATION_POLICY.csv",
    ]
    if rc != 0:
        reasons.append(f"Julia return code {rc}")
    if not preserved:
        reasons.append("attempt output not preserved")
    for name in required:
        if not (outdir / name).is_file():
            reasons.append(f"missing {name}")
    if not status:
        reasons.append("solve_status.csv missing or invalid")
        return False, reasons, {}

    exact = {
        "stage1_termination_status": "OPTIMAL",
        "stage1_primal_status": "FEASIBLE_POINT",
        "stage1_dual_status": "FEASIBLE_POINT",
        "termination_status": "OPTIMAL",
        "primal_status": "FEASIBLE_POINT",
        "dual_status": "FEASIBLE_POINT",
        "audit_export_result_tier": "official_stage1_economic_optimum",
        "cleanup_strategy_version": "V17_stage1_official_release_optional_sparse_face_diagnostic_cleanup_nonblocking",
        "numerical_stability_version": "V17T2R6_full8760_targetyear_exact_reoptimization_stage1_official_release_json_safe",
        "solver_solution_target": "optimal_primal_dual_solution_no_basis_requirement",
        "publication_solution_source": "stage1_solver_certified_economic_optimum",
        "successful_cleanup_route": "stage1_official_release",
        "requested_cleanup_profile": "stage1_official_release",
    }
    for col, want in exact.items():
        if status.get(col) != want:
            reasons.append(f"{col}={status.get(col)} expected {want}")

    for col in [
        "has_primal_values", "stage1_status_gate_pass", "solve_gate_pass",
        "strict_physical_audit_pass", "result_export_complete", "strict_export_pass",
        "regularization_share_gate_pass", "lexicographic_economic_gate_pass",
        "model_is_pure_lp", "cdr_module_exclusion_gate_pass", "official_cdr_disabled",
        "legacy_allocation_audit_pass", "stage1_official_release_selected",
        "stage1_official_release_pass", "cleanup_diagnostic_nonblocking",
        "investment_capacity_policy_outputs_release_eligible", "target_year_static_reoptimization",
    ]:
        if not truth(status.get(col)):
            reasons.append(f"{col}=false")

    if truth(status.get("target_year_transition_path_claim_supported")):
        reasons.append("target_year_transition_path_claim_supported must be false")
    if fnum(status.get("stage1_result_count"), 0) < 1:
        reasons.append("stage1_result_count < 1")
    if fnum(status.get("model_binary_variable_count"), -1) != 0:
        reasons.append("binary variable count nonzero")
    if fnum(status.get("model_integer_variable_count"), -1) != 0:
        reasons.append("integer variable count nonzero")
    expected_tp_count = 8760
    if int(fnum(status.get("representative_timepoint_count"), -1)) != expected_tp_count:
        reasons.append(
            f"representative_timepoint_count={status.get('representative_timepoint_count')} expected {expected_tp_count}"
        )
    if status.get("operational_period_count") not in {"1", "1.0"}:
        reasons.append(f"operational_period_count={status.get('operational_period_count')}")
    if status.get("stock_anchor_period_count") not in {"1", "1.0"}:
        reasons.append(f"stock_anchor_period_count={status.get('stock_anchor_period_count')}")
    if int(fnum(status.get("target_year_operation_period"), -1)) != int(expected["target_year"]):
        reasons.append(f"target year status={status.get('target_year_operation_period')} expected {expected['target_year']}")
    if truth(status.get("allow_nbccs")) or truth(status.get("allow_daccs")) or truth(status.get("allow_beccs")):
        reasons.append("forbidden CDR enabled")
    if truth(status.get("storage_cdr_modules_compiled")):
        reasons.append("storage CDR modules compiled")
    optimized_legacy = str(expected.get("legacy_allocation_mode", "")) == "optimized_reallocation"
    if optimized_legacy:
        if status.get("legacy_reallocation_formulation_version") != "V17T2R6R8_HF3_equivalent_projected_legacy_allocation_v2":
            reasons.append("optimized legacy formulation is not the HF3 exact projection")
        for col in [
            "legacy_national_energy_identity_pass",
            "legacy_zone_caps_encoded_as_variable_bounds",
            "legacy_energy_variable_projection_active",
            "legacy_projected_energy_output_reconstruction",
        ]:
            if not truth(status.get(col)):
                reasons.append(f"{col}=false for optimized legacy case")
        if int(fnum(status.get("legacy_energy_variable_projection_count"), -1)) != 32:
            reasons.append("legacy_energy_variable_projection_count is not 32")
        if truth(status.get("legacy_national_energy_closure_constraint_emitted")):
            reasons.append("redundant legacy national-energy closure row was emitted")
        if truth(status.get("legacy_common_duration_constraints_emitted")):
            reasons.append("projected legacy common-duration rows were emitted")
        if status.get("solver_profile") == "full8760_primal_dual_supported_objective_continuation":
            expected_source = {
                "TY2033_FULL8760_OPTIMAL": "TY2033_FULL8760_OBSERVED",
                "TY2033_FULL8760_LDES_OPTIMAL": "TY2033_FULL8760_LDES_OBSERVED",
            }.get(str(expected.get("scenario", "")), "")
            hf4_exact = {
                "hf4_continuation_active": "true",
                "hf4_seed_attempted": "true",
                "hf4_seed_strict_optimal": "true",
                "hf4_seed_termination_status": "OPTIMAL",
                "hf4_seed_primal_status": "FEASIBLE_POINT",
                "hf4_seed_dual_status": "FEASIBLE_POINT",
                "hf4_seed_source_scenario": expected_source,
                "hf4_seed_source_pair_identity_pass": "true",
                "hf4_seed_gurobi_objval_gate_pass": "true",
                "hf4_seed_objective_scale_gate_pass": "true",
                "hf4_seed_raw_primal_finite": "true",
                "hf4_seed_raw_dual_finite": "true",
                "hf4_seed_raw_reduced_cost_finite": "true",
                "hf4_final_bounds_restored": "true",
                "hf4_bridge_strict_optimal": "true",
                "hf4_bridge_termination_status": "OPTIMAL",
                "hf4_bridge_primal_status": "FEASIBLE_POINT",
                "hf4_bridge_dual_status": "FEASIBLE_POINT",
                "hf4_bridge_basis_available": "true",
                "hf4_homotopy_all_strict_optimal": "true",
                "hf4_final_objective_restored": "true",
            }
            for col, want in hf4_exact.items():
                if str(status.get(col, "")).strip().lower() != str(want).lower():
                    reasons.append(f"{col}={status.get(col)} expected {want}")
            if int(fnum(status.get("hf4_seed_gurobi_status"), -1)) != 2:
                reasons.append("HF4 seed Gurobi status is not 2")
            if int(fnum(status.get("hf4_bridge_gurobi_status"), -1)) != 2:
                reasons.append("HF4 bridge Gurobi status is not 2")
            is_hf6 = status.get("solver_route_role") == (
                "V17T2R6R11_HF6_full8760_dual_start_only_dual_simplex_no_crossover_exact_objective_continuation"
            )
            is_hf5 = status.get("solver_route_role") == (
                "V17T2R6R10_HF5_full8760_primal_dual_start_simplex_basis_no_crossover_exact_objective_continuation"
            )
            if not is_hf6 and not truth(status.get("hf4_primal_dual_start_set_pass")):
                reasons.append("HF4/HF5 primal/dual start assignment failed")
            if is_hf6:
                hf6_exact = {
                    "hf4_bridge_strategy": "dual_simplex_unpresolved_dstart_only_no_crossover",
                    "hf4_bridge_no_crossover_gate_pass": "true",
                    "hf4_bridge_primal_start_not_submitted_by_design": "true",
                    "hf4_bridge_dual_start_only_set_pass": "true",
                }
                for col, want in hf6_exact.items():
                    if str(status.get(col, "")).strip().lower() != str(want).lower():
                        reasons.append(f"{col}={status.get(col)} expected {want}")
                if int(fnum(status.get("hf4_bridge_method"), -1)) != 1:
                    reasons.append("HF6 bridge method is not dual simplex (1)")
                if int(fnum(status.get("hf4_bridge_crossover"), -1)) != 0:
                    reasons.append("HF6 bridge crossover is not disabled (0)")
                if int(fnum(status.get("hf4_bridge_crossover_basis"), -2)) != -1:
                    reasons.append("HF6 bridge CrossoverBasis is not disabled (-1)")
                if int(fnum(status.get("hf4_bridge_lpwarmstart"), -1)) != 1:
                    reasons.append("HF6 bridge LPWarmStart is not 1")
                if int(fnum(status.get("hf4_bridge_presolve"), -1)) != 0:
                    reasons.append("HF6 bridge Presolve is not 0")
                if int(fnum(status.get("hf4_bridge_aggregate"), -1)) != 0:
                    reasons.append("HF6 bridge Aggregate is not 0")
                if int(fnum(status.get("hf4_bridge_pre_sparsify"), -1)) != 0:
                    reasons.append("HF6 bridge PreSparsify is not 0")
                if fnum(status.get("hf4_bridge_barrier_iterations"), float("inf")) != 0.0:
                    reasons.append("HF6 bridge unexpectedly recorded barrier iterations")
            elif is_hf5:
                hf5_exact = {
                    "hf4_bridge_strategy": "primal_simplex_crushed_pstart_full_dstart_audited_no_crossover",
                    "hf4_bridge_no_crossover_gate_pass": "true",
                }
                for col, want in hf5_exact.items():
                    if str(status.get(col, "")).strip().lower() != str(want).lower():
                        reasons.append(f"{col}={status.get(col)} expected {want}")
                if int(fnum(status.get("hf4_bridge_method"), -1)) != 0:
                    reasons.append("HF5 bridge method is not primal simplex (0)")
                if int(fnum(status.get("hf4_bridge_crossover"), -1)) != 0:
                    reasons.append("HF5 bridge crossover is not disabled (0)")
                if int(fnum(status.get("hf4_bridge_crossover_basis"), -2)) != -1:
                    reasons.append("HF5 bridge CrossoverBasis is not disabled (-1)")
                if int(fnum(status.get("hf4_bridge_lpwarmstart"), -1)) != 2:
                    reasons.append("HF5 bridge LPWarmStart is not 2")
                if int(fnum(status.get("hf4_bridge_presolve"), -1)) != 2:
                    reasons.append("HF5 bridge Presolve is not 2")
                if int(fnum(status.get("hf4_bridge_aggregate"), -1)) != 1:
                    reasons.append("HF5 bridge Aggregate is not 1")
                if int(fnum(status.get("hf4_bridge_pre_sparsify"), -1)) != 1:
                    reasons.append("HF5 bridge PreSparsify is not 1")
                if fnum(status.get("hf4_bridge_barrier_iterations"), float("inf")) != 0.0:
                    reasons.append("HF5 bridge unexpectedly recorded barrier iterations")
            if int(fnum(status.get("hf4_seed_allocation_count"), -1)) != 32:
                reasons.append("HF4 seed allocation count is not 32")
            if int(fnum(status.get("hf4_final_restored_bound_count"), -1)) != 32:
                reasons.append("HF4 restored-bound count is not 32")
            if int(fnum(status.get("hf4_support_objective_adjustment_count"), -1)) != 32:
                reasons.append("HF4 support-objective adjustment count is not 32")
            if int(fnum(status.get("hf4_final_objective_restored_count"), -1)) != 32:
                reasons.append("HF4 final objective restoration count is not 32")
            raw_vars = int(fnum(status.get("hf4_seed_raw_variable_count"), -1))
            raw_rows = int(fnum(status.get("hf4_seed_raw_constraint_count"), -1))
            if raw_vars != int(fnum(status.get("model_variable_count_after_algebraic_reduction"), -2)):
                reasons.append("HF4 raw variable count does not match the final model")
            if is_hf6:
                if int(fnum(status.get("hf4_bridge_primal_start_audit_count"), -1)) != raw_vars:
                    reasons.append("HF6 audited PStart count does not match raw variable count")
                if int(fnum(status.get("hf4_bridge_dual_start_audit_count"), -1)) != raw_rows:
                    reasons.append("HF6 audited DStart count does not match raw row count")
                if int(fnum(status.get("hf4_bridge_primal_start_submitted_count"), -1)) != 0:
                    reasons.append("HF6 unexpectedly submitted PStart")
                if int(fnum(status.get("hf4_bridge_dual_start_submitted_count"), -1)) != raw_rows:
                    reasons.append("HF6 submitted DStart count does not match raw row count")
            else:
                if int(fnum(status.get("hf4_primal_start_count"), -1)) != raw_vars:
                    reasons.append("HF4 PStart count does not match raw variable count")
                if int(fnum(status.get("hf4_dual_start_count"), -1)) != raw_rows:
                    reasons.append("HF4 DStart count does not match raw row count")
            if int(fnum(status.get("hf4_bridge_vbasis_count"), -1)) != raw_vars:
                reasons.append("HF4 VBasis count does not match raw variable count")
            if int(fnum(status.get("hf4_bridge_cbasis_count"), -1)) != raw_rows:
                reasons.append("HF4 CBasis count does not match raw row count")
            if abs(fnum(status.get("hf4_seed_national_power_residual_mw"), float("inf"))) > 1.0e-6:
                reasons.append("HF4 seed national power residual exceeds 1e-6 MW")
            if abs(fnum(status.get("hf4_seed_national_energy_residual_mwh"), float("inf"))) > 1.0e-6:
                reasons.append("HF4 seed national energy residual exceeds 1e-6 MWh")
            if fnum(status.get("hf4_seed_full_pstart_max_bound_violation"), float("inf")) > 1.0e-8:
                reasons.append("HF4 seed PStart violates a restored target bound")
            if fnum(status.get("hf4_final_max_lower_bound_error_mw"), float("inf")) != 0.0:
                reasons.append("HF4 final lower bounds were not restored exactly")
            if fnum(status.get("hf4_final_max_upper_bound_error_mw"), float("inf")) != 0.0:
                reasons.append("HF4 final upper bounds were not restored exactly")
            if fnum(status.get("hf4_final_max_objective_coefficient_error"), float("inf")) != 0.0:
                reasons.append("HF4 final objective coefficients were not restored exactly")
            requested = "0.001;0.003;0.01;0.03;0.1;0.25;0.5;0.75"
            if status.get("hf4_homotopy_levels_requested") != requested:
                reasons.append("HF4 homotopy schedule changed")
            if status.get("hf4_homotopy_levels_completed") != requested:
                reasons.append("HF4 homotopy schedule did not complete")
    else:
        if truth(status.get("legacy_energy_variable_projection_active")):
            reasons.append("legacy projection unexpectedly active for observed case")
        if int(fnum(status.get("legacy_energy_variable_projection_count"), -1)) != 0:
            reasons.append("observed case legacy projection count is not zero")
    if status.get("solver_profile") == "full8760_restricted_face_continuation":
        scenario = str(expected.get("scenario", ""))
        expected_source = {
            "TY2033_FULL8760_OPTIMAL": "TY2033_FULL8760_OBSERVED",
            "TY2033_FULL8760_LDES_OBSERVED": "TY2033_FULL8760_LDES_OBSERVED",
            "TY2033_FULL8760_LDES_OPTIMAL": "TY2033_FULL8760_LDES_OBSERVED",
        }.get(scenario, "")
        expected_mode = {
            "TY2033_FULL8760_OPTIMAL": "observed_legacy_inside_nonldes_optimal_target",
            "TY2033_FULL8760_LDES_OBSERVED": "zero_ldes_inside_ldes_observed_target",
            "TY2033_FULL8760_LDES_OPTIMAL": "observed_legacy_plus_zero_ldes_inside_ldes_optimal_target",
        }.get(scenario, "")
        hf7_exact = {
            "hf4_continuation_active": "true",
            "hf4_seed_attempted": "true",
            "hf4_seed_strict_optimal": "true",
            "hf4_seed_termination_status": "OPTIMAL",
            "hf4_seed_primal_status": "FEASIBLE_POINT",
            "hf4_seed_dual_status": "FEASIBLE_POINT",
            "hf4_seed_source_scenario": expected_source,
            "hf4_seed_source_pair_identity_pass": "true",
            "hf4_seed_restricted_face_mode": expected_mode,
            "hf4_seed_restricted_face_pass": "true",
            "hf4_seed_ldes_zero_values_pass": "true",
            "hf4_seed_ldes_zero_equals_original_lower_pass": "true",
            "hf4_seed_gurobi_objval_gate_pass": "true",
            "hf4_seed_objective_scale_gate_pass": "true",
            "hf4_seed_raw_primal_finite": "true",
            "hf4_seed_raw_dual_finite": "true",
            "hf4_seed_raw_reduced_cost_finite": "true",
            "hf4_restricted_basis_strict_optimal": "true",
            "hf4_restricted_basis_termination_status": "OPTIMAL",
            "hf4_restricted_basis_primal_status": "FEASIBLE_POINT",
            "hf4_restricted_basis_dual_status": "FEASIBLE_POINT",
            "hf4_restricted_basis_available": "true",
            "hf4_staged_release_order_pass": "true",
            "hf4_final_bounds_restored": "true",
            "hf4_bridge_dual_start_only_set_pass": "true",
            "hf4_bridge_primal_start_not_submitted_by_design": "true",
            "hf4_bridge_strict_optimal": "true",
            "hf4_bridge_termination_status": "OPTIMAL",
            "hf4_bridge_primal_status": "FEASIBLE_POINT",
            "hf4_bridge_dual_status": "FEASIBLE_POINT",
            "hf4_bridge_strategy": "restricted_basis_then_zero_ldes_then_legacy_dual_simplex_no_crossover",
            "hf4_bridge_no_crossover_gate_pass": "true",
            "hf4_bridge_basis_available": "true",
            "hf4_homotopy_all_strict_optimal": "true",
            "hf4_final_objective_restored": "true",
        }
        for col, want in hf7_exact.items():
            if str(status.get(col, "")).strip().lower() != str(want).lower():
                reasons.append(f"{col}={status.get(col)} expected {want}")
        legacy_release = int(fnum(status.get("hf4_release_legacy_count"), -1))
        ldes_power_release = int(fnum(status.get("hf4_release_ldes_power_count"), -1))
        ldes_energy_release = int(fnum(status.get("hf4_release_ldes_energy_count"), -1))
        total_release = int(fnum(status.get("hf4_release_total_count"), -1))
        if legacy_release != (32 if optimized_legacy else 0):
            reasons.append("HF7 legacy release count does not match scenario mode")
        is_ldes = str(expected.get("ldes_proxy_mode", "")) == "technology_portfolio_discrete"
        if is_ldes:
            if not truth(status.get("hf4_seed_ldes_zero_fix_requested")):
                reasons.append("HF7 LDES zero-face seed was not requested")
            if ldes_power_release <= 0 or ldes_energy_release != ldes_power_release:
                reasons.append("HF7 LDES power/energy release counts are invalid")
            if int(fnum(status.get("hf4_seed_ldes_zero_fix_count"), -1)) != ldes_power_release + ldes_energy_release:
                reasons.append("HF7 LDES zero-fix count does not match released LDES coordinates")
            if not truth(status.get("hf4_ldes_release_stage_attempted")):
                reasons.append("HF7 LDES release stage was not attempted")
            if not truth(status.get("hf4_ldes_release_stage_strict_optimal")):
                reasons.append("HF7 LDES release stage was not strict optimal")
            if int(fnum(status.get("hf4_ldes_release_stage_gurobi_status"), -1)) != 2:
                reasons.append("HF7 LDES release stage Gurobi status is not OPTIMAL")
            if int(fnum(status.get("hf4_ldes_release_stage_bound_count"), -1)) != ldes_power_release + ldes_energy_release:
                reasons.append("HF7 LDES release-stage bound count is inconsistent")
        else:
            if truth(status.get("hf4_seed_ldes_zero_fix_requested")):
                reasons.append("HF7 non-LDES scenario unexpectedly requested an LDES zero face")
            if ldes_power_release != 0 or ldes_energy_release != 0:
                reasons.append("HF7 non-LDES scenario has LDES release coordinates")
            if truth(status.get("hf4_ldes_release_stage_attempted")):
                reasons.append("HF7 non-LDES scenario unexpectedly ran an LDES release stage")
            if int(fnum(status.get("hf4_ldes_release_stage_bound_count"), -1)) != 0:
                reasons.append("HF7 non-LDES release-stage bound count is not zero")
        if optimized_legacy:
            if not truth(status.get("hf4_legacy_release_stage_attempted")):
                reasons.append("HF7 optimized legacy release stage was not attempted")
            if not truth(status.get("hf4_legacy_release_stage_strict_optimal")):
                reasons.append("HF7 optimized legacy release stage was not strict optimal")
            if int(fnum(status.get("hf4_legacy_release_stage_gurobi_status"), -1)) != 2:
                reasons.append("HF7 legacy release stage Gurobi status is not OPTIMAL")
            if int(fnum(status.get("hf4_legacy_release_stage_bound_count"), -1)) != 32:
                reasons.append("HF7 legacy release-stage bound count is not 32")
        else:
            if truth(status.get("hf4_legacy_release_stage_attempted")):
                reasons.append("HF7 observed legacy scenario unexpectedly ran legacy release stage")
            if int(fnum(status.get("hf4_legacy_release_stage_bound_count"), -1)) != 0:
                reasons.append("HF7 observed legacy release-stage bound count is not zero")
        if total_release <= 0 or total_release != legacy_release + ldes_power_release + ldes_energy_release:
            reasons.append("HF7 total release count is inconsistent")
        for col in [
            "hf4_final_restored_bound_count",
            "hf4_support_objective_adjustment_count",
            "hf4_final_objective_restored_count",
        ]:
            if int(fnum(status.get(col), -1)) != total_release:
                reasons.append(f"{col} does not match HF7 total release count")
        raw_vars = int(fnum(status.get("hf4_seed_raw_variable_count"), -1))
        raw_rows = int(fnum(status.get("hf4_seed_raw_constraint_count"), -1))
        if raw_vars != int(fnum(status.get("model_variable_count_after_algebraic_reduction"), -2)):
            reasons.append("HF7 raw variable count does not match final model")
        if int(fnum(status.get("hf4_bridge_primal_start_audit_count"), -1)) != raw_vars:
            reasons.append("HF7 audited PStart count does not match raw variable count")
        if int(fnum(status.get("hf4_bridge_dual_start_audit_count"), -1)) != raw_rows:
            reasons.append("HF7 audited DStart count does not match raw row count")
        if int(fnum(status.get("hf4_bridge_primal_start_submitted_count"), -1)) != 0:
            reasons.append("HF7 unexpectedly submitted PStart")
        if int(fnum(status.get("hf4_bridge_dual_start_submitted_count"), -1)) != raw_rows:
            reasons.append("HF7 submitted DStart count does not match raw rows")
        if int(fnum(status.get("hf4_bridge_vbasis_count"), -1)) != raw_vars:
            reasons.append("HF7 VBasis count does not match raw variables")
        if int(fnum(status.get("hf4_bridge_cbasis_count"), -1)) != raw_rows:
            reasons.append("HF7 CBasis count does not match raw rows")
        if int(fnum(status.get("hf4_restricted_basis_dstart_audit_count"), -1)) != raw_rows:
            reasons.append("HF7 restricted-basis DStart audit count does not match raw rows")
        if int(fnum(status.get("hf4_restricted_basis_dstart_submitted_count"), -1)) != raw_rows:
            reasons.append("HF7 restricted-basis DStart submitted count does not match raw rows")
        if int(fnum(status.get("hf4_restricted_basis_vbasis_count"), -1)) != raw_vars:
            reasons.append("HF7 restricted-basis VBasis count does not match raw variables")
        if int(fnum(status.get("hf4_restricted_basis_cbasis_count"), -1)) != raw_rows:
            reasons.append("HF7 restricted-basis CBasis count does not match raw rows")
        numeric_exact = {
            "hf4_seed_gurobi_status": 2,
            "hf4_restricted_basis_gurobi_status": 2,
            "hf4_restricted_basis_method": 1,
            "hf4_restricted_basis_crossover": 0,
            "hf4_restricted_basis_lpwarmstart": 2,
            "hf4_restricted_basis_presolve": 2,
            "hf4_bridge_gurobi_status": 2,
            "hf4_bridge_method": 1,
            "hf4_bridge_crossover": 0,
            "hf4_bridge_crossover_basis": -1,
            "hf4_bridge_lpwarmstart": 1,
            "hf4_bridge_presolve": 0,
            "hf4_bridge_aggregate": 0,
            "hf4_bridge_pre_sparsify": 0,
        }
        for col, want in numeric_exact.items():
            if int(fnum(status.get(col), -999)) != want:
                reasons.append(f"{col}={status.get(col)} expected {want}")
        if fnum(status.get("hf4_bridge_barrier_iterations"), float("inf")) != 0.0:
            reasons.append("HF7 bridge unexpectedly used Barrier")
        if fnum(status.get("hf4_restricted_basis_barrier_iterations"), float("inf")) != 0.0:
            reasons.append("HF7 restricted-basis bridge unexpectedly used Barrier")
        if int(fnum(status.get("hf4_seed_allocation_count"), -1)) != 32:
            reasons.append("HF7 observed legacy allocation audit count is not 32")
        if abs(fnum(status.get("hf4_seed_national_power_residual_mw"), float("inf"))) > 1.0e-6:
            reasons.append("HF7 seed national power residual exceeds 1e-6 MW")
        if abs(fnum(status.get("hf4_seed_national_energy_residual_mwh"), float("inf"))) > 1.0e-6:
            reasons.append("HF7 seed national energy residual exceeds 1e-6 MWh")
        if fnum(status.get("hf4_seed_full_pstart_max_bound_violation"), float("inf")) > 1.0e-8:
            reasons.append("HF7 captured seed violates a restored target bound")
        if fnum(status.get("hf4_final_max_lower_bound_error_mw"), float("inf")) != 0.0:
            reasons.append("HF7 final lower bounds were not restored exactly")
        if fnum(status.get("hf4_final_max_upper_bound_error_mw"), float("inf")) != 0.0:
            reasons.append("HF7 final upper bounds were not restored exactly")
        if fnum(status.get("hf4_final_max_objective_coefficient_error"), float("inf")) != 0.0:
            reasons.append("HF7 final objective coefficients were not restored exactly")
        requested = "0.001;0.003;0.01;0.03;0.1;0.25;0.5;0.75"
        if status.get("hf4_homotopy_levels_requested") != requested:
            reasons.append("HF7 homotopy schedule changed")
        if status.get("hf4_homotopy_levels_completed") != requested:
            reasons.append("HF7 homotopy schedule did not complete")
    if not profile_gate(status):
        reasons.append("solver profile gate failed")
    if not native_certificate_gate(status):
        reasons.append("solver-native optimality certificate failed")

    c_ok, c_reasons, maxima = chronology_gate(outdir, status, expected)
    if not c_ok:
        reasons.extend(c_reasons)
    return not reasons, reasons, maxima


def run_solver_once(julia: str, row: dict[str, Any], profile: str, suffix: str, label: str) -> dict[str, Any]:
    scenario = str(row["scenario"])
    local = local_output(scenario, suffix)
    if local.exists():
        shutil.rmtree(local)
    log = LOGS / scenario / f"{label}.log"
    cmd = [
        julia, str(ROOT / "storage_runner" / "run_targetyear_one.jl"),
        "--scenario", scenario,
        "--solver_profile", profile,
        "--cleanup_profile", "stage1_official_release",
        "--solver_output_suffix", suffix,
    ]
    rc, seconds = run_cmd(cmd, log)
    outdir, preserved = preserve_attempt(scenario, label, suffix)
    status = read_one_csv(outdir / "solve_status.csv")
    success, reasons, maxima = strict_success(status, rc, preserved, outdir, row)
    return {
        "scenario": scenario, "profile": profile, "suffix": suffix, "attempt_label": label,
        "return_code": rc, "seconds": seconds, "attempt_output_dir": str(outdir.relative_to(ROOT)),
        "log": str(log.relative_to(ROOT)), "status": status, "success": success,
        "failure_reasons": reasons, "chronology_maxima": maxima,
    }


def archive_failure(scenario: str) -> str:
    src = ATTEMPTS / scenario
    if not src.exists():
        return ""
    dest = ROOT / "failed_diagnostics"
    dest.mkdir(parents=True, exist_ok=True)
    return shutil.make_archive(str(dest / f"{scenario}_V17T2R6_FULL8760_failed_diagnostics"), "zip", root_dir=src)


def existing_official_record(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return a strict record for an already promoted official result, otherwise None."""
    scenario = str(row["scenario"])
    outdir = CENTRAL / f"{scenario}__main"
    from publication_source_common import validate_result_fingerprint
    fp_ok, _ = validate_result_fingerprint(ROOT, outdir, ROOT / "sensitivity_cases" / scenario, scenario)
    if not fp_ok:
        return None
    status = read_one_csv(outdir / "solve_status.csv")
    success, reasons, maxima = strict_success(status, 0, outdir.is_dir(), outdir, row)
    if not success:
        return None
    return {
        "scenario": scenario,
        "pair_id": row["pair_id"],
        "target_year": int(row["target_year"]),
        "context": row["context"],
        "publication_strict_success": True,
        "elapsed_seconds": 0.0,
        "stage1_attempts_used": "preexisting_official_output",
        "fallback_stop_reason": "preexisting_official_success_skipped",
        "successful_solver_profile": status.get("solver_profile", ""),
        "failure_reasons": "",
        "promoted_output": str(outdir.relative_to(ROOT)),
        "failed_diagnostic_archive": "",
        "stage1_termination_status": status.get("stage1_termination_status", ""),
        "stage1_primal_status": status.get("stage1_primal_status", ""),
        "stage1_dual_status": status.get("stage1_dual_status", ""),
        "stage1_economic_optimum": status.get("stage1_economic_optimum", ""),
        "chronology_maxima_json": json.dumps(maxima, ensure_ascii=False),
    }


def _run_one_with_lease(julia: str, row: dict[str, Any], routes: list[tuple[str, str, str]], force_rerun: bool = False) -> dict[str, Any]:
    scenario = str(row["scenario"])
    if not force_rerun:
        existing = existing_official_record(row)
        if existing is not None:
            return existing
    used: list[str] = []
    total = 0.0
    final: dict[str, Any] | None = None
    stop_reason = ""
    for profile, suffix, label in routes:
        used.append(label)
        attempt = run_solver_once(julia, row, profile, suffix, label)
        final = attempt
        total += float(attempt["seconds"])
        if attempt["success"]:
            stop_reason = "official_success" if len(used) == 1 else "official_success_after_controlled_fallback"
            break
        status = attempt["status"]
        # A missing/invalid solve_status means Julia failed before the solver could
        # produce a certifiable Stage-1 status. Repeating the same model with a
        # second solver profile cannot repair a preprocessing/runtime exception,
        # so stop immediately and preserve diagnostics instead of wasting compute.
        if not status:
            stop_reason = "runtime_or_pre_solve_failure_stop_for_repair"
            break
        if status.get("stage1_termination_status") == "OPTIMAL":
            stop_reason = "solver_optimal_but_downstream_gate_failed_stop_for_audit_repair"
            break
        stop_reason = "uncertified_primary_try_single_fallback"
    assert final is not None
    promoted = promote_success(scenario, ROOT / final["attempt_output_dir"]) if final["success"] else None
    archive = "" if final["success"] else archive_failure(scenario)
    status = final["status"]
    rec = {
        "scenario": scenario,
        "pair_id": row["pair_id"],
        "target_year": int(row["target_year"]),
        "context": row["context"],
        "publication_strict_success": bool(final["success"]),
        "elapsed_seconds": round(total, 3),
        "stage1_attempts_used": ";".join(used),
        "fallback_stop_reason": stop_reason,
        "successful_solver_profile": final["profile"] if final["success"] else "",
        "failure_reasons": ";".join(final["failure_reasons"]),
        "promoted_output": str(promoted.relative_to(ROOT)) if promoted else "",
        "failed_diagnostic_archive": str(Path(archive).relative_to(ROOT)) if archive else "",
        "stage1_termination_status": status.get("stage1_termination_status", ""),
        "stage1_primal_status": status.get("stage1_primal_status", ""),
        "stage1_dual_status": status.get("stage1_dual_status", ""),
        "stage1_economic_optimum": status.get("stage1_economic_optimum", ""),
        "chronology_maxima_json": json.dumps(final["chronology_maxima"], ensure_ascii=False),
    }
    return rec


def run_one(julia: str, row: dict[str, Any], routes: list[tuple[str, str, str]], force_rerun: bool = False) -> dict[str, Any]:
    scenario = str(row["scenario"])
    if not force_rerun:
        existing = existing_official_record(row)
        if existing is not None:
            return existing
    lease, completed_elsewhere = acquire_scenario_lease(row, force_rerun)
    if completed_elsewhere is not None:
        return completed_elsewhere
    try:
        return _run_one_with_lease(julia, row, routes, force_rerun=force_rerun)
    finally:
        release_scenario_lease(lease)


def exception_record(row: dict[str, Any], exc: Exception) -> dict[str, Any]:
    """Convert an orchestration exception into a deterministic failure record.

    Solver/runtime failures are normally captured by run_one. This guard is for
    Python-side orchestration errors so one worker cannot corrupt or silently
    terminate the partner worker in the same two-case wave.
    """
    return {
        "scenario": str(row["scenario"]),
        "pair_id": row["pair_id"],
        "target_year": int(row["target_year"]),
        "context": row["context"],
        "publication_strict_success": False,
        "elapsed_seconds": 0.0,
        "stage1_attempts_used": "orchestrator_exception",
        "fallback_stop_reason": "python_orchestrator_exception",
        "successful_solver_profile": "",
        "failure_reasons": f"{type(exc).__name__}: {exc}",
        "promoted_output": "",
        "failed_diagnostic_archive": "",
        "stage1_termination_status": "",
        "stage1_primal_status": "",
        "stage1_dual_status": "",
        "stage1_economic_optimum": "",
        "chronology_maxima_json": "{}",
    }


def selected_waves(rows: list[dict[str, Any]], max_parallel: int) -> list[list[dict[str, Any]]]:
    """Return deterministic waves with at most two simultaneous scenarios."""
    if max_parallel == 1:
        return [[row] for row in rows]
    if max_parallel != 2:
        raise ValueError("V17T2R6 permits max_parallel only 1 or 2; R7 canonical mode is 2.")
    by_name = {str(row["scenario"]): row for row in rows}
    waves: list[list[dict[str, Any]]] = []
    consumed: set[str] = set()
    for names in PARALLEL_WAVES:
        wave = [by_name[name] for name in names if name in by_name]
        if wave:
            waves.append(wave)
            consumed.update(str(row["scenario"]) for row in wave)
    # A scenario-specific invocation remains supported without weakening the
    # hard two-worker cap. Unknown scenarios are rejected earlier by argparse.
    for row in rows:
        name = str(row["scenario"])
        if name not in consumed:
            waves.append([row])
    return waves


def run_selected_rows(
    julia: str,
    rows: list[dict[str, Any]],
    routes: list[tuple[str, str, str]],
    force_rerun: bool,
    continue_after_failure: bool,
    max_parallel: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    waves = selected_waves(rows, max_parallel)
    for wave_index, wave in enumerate(waves, start=1):
        names = [str(row["scenario"]) for row in wave]
        print(json.dumps({
            "wave": wave_index,
            "max_parallel": max_parallel,
            "solver_threads_per_case": int(os.environ.get("V17_SOLVER_THREADS", "10")),
            "scenarios": names,
        }, ensure_ascii=False))
        if len(wave) == 1:
            row = wave[0]
            try:
                wave_records = [run_one(julia, row, routes, force_rerun=force_rerun)]
            except Exception as exc:  # fail closed, but preserve the partner-wave policy
                wave_records = [exception_record(row, exc)]
        else:
            wave_records_by_name: dict[str, dict[str, Any]] = {}
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="v17t2r6_8760") as pool:
                future_to_row = {
                    pool.submit(run_one, julia, row, routes, force_rerun): row
                    for row in wave
                }
                for future in as_completed(future_to_row):
                    row = future_to_row[future]
                    name = str(row["scenario"])
                    try:
                        wave_records_by_name[name] = future.result()
                    except Exception as exc:
                        wave_records_by_name[name] = exception_record(row, exc)
            # Preserve scenario-registry order regardless of which worker finishes first.
            wave_records = [wave_records_by_name[str(row["scenario"])] for row in wave]
        for rec in wave_records:
            print(json.dumps(rec, ensure_ascii=False, indent=2))
        records.extend(wave_records)
        if any(not rec["publication_strict_success"] for rec in wave_records) and not continue_after_failure:
            print("Stopping before the next wave after a failed strict release gate. "
                  "The already-running partner in this wave was allowed to finish safely.")
            break
    return records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--julia", default=os.environ.get("JULIA_EXE", "julia"))
    ap.add_argument("--pair", choices=["TY2033_FULL8760", "TY2033_FULL8760_LDES", "ALL"], default="ALL")
    ap.add_argument("--scenario", default="")
    ap.add_argument("--skip-prepare", action="store_true")
    ap.add_argument("--clean-central", action="store_true")
    ap.add_argument("--route", choices=sorted(ROUTE_SELECTIONS), default="auto",
                    help="auto: old two-route ladder; primary/fallback: old individual route; hf3: projected primary-only route; hf4_continuation: prior exact objective continuation; hf5_simplex_bridge: prior primal bridge; hf6_dual_simplex_bridge: OPTIMAL-only DStart dual-simplex bridge")
    ap.add_argument("--force-rerun", action="store_true",
                    help="rerun even when a previously promoted output still passes every strict gate")
    ap.add_argument("--continue-after-failure", action="store_true",
                    help="continue to later waves after one scenario fails both selected exact routes")
    ap.add_argument("--max-parallel", type=int, default=int(os.environ.get("V17T2R6_MAX_PARALLEL", "1")),
                    help="maximum simultaneous full-8760 scenarios; publication-supported values are 1 or 2")
    args = ap.parse_args()
    if args.max_parallel not in (1, 2):
        raise SystemExit("--max-parallel must be 1 or 2; R7 canonical mode is exactly 2.")
    if args.max_parallel == 2 and int(os.environ.get("V17_SOLVER_THREADS", "10")) != 10:
        raise SystemExit("R7 2x10 mode requires V17_SOLVER_THREADS=10 exactly.")

    if args.clean_central and CENTRAL.exists():
        shutil.rmtree(CENTRAL)
    CENTRAL.mkdir(parents=True, exist_ok=True)
    ATTEMPTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    if not args.skip_prepare:
        subprocess.check_call([sys.executable, str(ROOT / "tools" / "prepare_8760_cases.py")], cwd=ROOT)
    subprocess.check_call([sys.executable, str(ROOT / "tools" / "audit_targetyear_pair_identity.py")], cwd=ROOT)

    df = pd.read_csv(SCEN)
    if args.scenario:
        df = df.loc[df["scenario"].astype(str).eq(args.scenario)]
        if df.empty:
            raise SystemExit(f"Unknown target-year scenario: {args.scenario}")
    elif args.pair != "ALL":
        df = df.loc[df["pair_id"].astype(str).eq(args.pair)]
    routes = ROUTE_SELECTIONS[args.route]
    if not routes:
        raise SystemExit(f"No route selected for {args.route}")
    rows = [r.to_dict() for _, r in df.iterrows()]
    if args.route in {"hf4_continuation", "hf5_simplex_bridge", "hf6_dual_simplex_bridge"}:
        allowed_hf4 = {
            "TY2033_FULL8760_OPTIMAL",
            "TY2033_FULL8760_LDES_OPTIMAL",
        }
        selected_names = {str(row["scenario"]) for row in rows}
        if not selected_names or not selected_names.issubset(allowed_hf4):
            raise SystemExit(
                f"--route {args.route} is isolated to TY2033_FULL8760_OPTIMAL "
                "and TY2033_FULL8760_LDES_OPTIMAL; select one with --scenario."
            )
    if args.route == "hf7_restricted_face":
        allowed_hf7 = {
            "TY2033_FULL8760_OPTIMAL",
            "TY2033_FULL8760_LDES_OBSERVED",
            "TY2033_FULL8760_LDES_OPTIMAL",
        }
        selected_names = {str(row["scenario"]) for row in rows}
        if not selected_names or not selected_names.issubset(allowed_hf7):
            raise SystemExit(
                "--route hf7_restricted_face is isolated to the three unresolved full-8760 scenarios."
            )
    records = run_selected_rows(
        args.julia, rows, routes,
        force_rerun=args.force_rerun,
        continue_after_failure=args.continue_after_failure,
        max_parallel=args.max_parallel,
    )

    merged = pd.DataFrame(records)
    if SUMMARY_CSV.is_file():
        prev = pd.read_csv(SUMMARY_CSV)
        merged = pd.concat([prev, merged], ignore_index=True).drop_duplicates(subset=["scenario"], keep="last")
    scenario_order = list(pd.read_csv(SCEN)["scenario"].astype(str))
    order = {name: i for i, name in enumerate(scenario_order)}
    if not merged.empty and "scenario" in merged.columns:
        merged["__order"] = merged["scenario"].astype(str).map(order).fillna(10**9)
        merged = merged.sort_values("__order", kind="stable").drop(columns=["__order"]).reset_index(drop=True)
    merged.to_csv(SUMMARY_CSV, index=False)
    SUMMARY_JSON.write_text(json.dumps(merged.to_dict(orient="records"), ensure_ascii=False, indent=2), encoding="utf-8")
    if not all(r["publication_strict_success"] for r in records):
        raise SystemExit("One or more full-8760 scenarios failed both exact routes or a downstream release gate. See batch_logs, sensitivity_outputs/_attempts and failed_diagnostics.")
    print(f"All {len(records)} requested V17T2R6-input scenarios passed strict publication validation.")


if __name__ == "__main__":
    main()
