#!/usr/bin/env python3
"""Run V17T2R5 target-year sensitivities with controlled exact LP routes.

Ordinary 4 h/LDES route 1: deterministic concurrent LP, 2 h default.
Ordinary 4 h/LDES route 2: homogeneous barrier + dual-cleanup crossover, 4 h default.
2033 one-hour robust ladder: scaled Barrier without crossover (12 h), then
direct Dual Simplex (24 h), then deterministic concurrent simplex (24 h).
R3 one-case route: exact legacy-energy and hourly-coordinate projection followed
by a fresh scaled Barrier attempt; it never cleans or reruns the other seven cases.
R5 one-case route: strict observed seed, complete primal+dual supported-basis
bridge, then exact objective continuation to the unchanged OPTIMAL target.

Every route starts in a fresh Julia process. Only a solver-native OPTIMAL solution
that passes all physical, chronology, identification and export gates is promoted.
TIME_LIMIT incumbents or intermediate feasible bases are never publication outputs.
"""
from __future__ import annotations

from pathlib import Path
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
SUMMARY_CSV = CENTRAL / "V17T2R5_run_summary.csv"
SUMMARY_JSON = CENTRAL / "V17T2R5_run_summary.json"
ROUTES = [
    ("targetyear_deterministic_concurrent", "__01_targetyear_concurrent_official", "01_targetyear_concurrent_official"),
    ("targetyear_homogeneous_dual_crossover", "__02_targetyear_homogeneous_dual_crossover_official", "02_targetyear_homogeneous_dual_crossover_official"),
]
ONE_H_ROUTES = [
    ("scaled_barrier", "__03_targetyear_scaled_barrier_nocrossover_rescue", "03_targetyear_scaled_barrier_nocrossover_rescue"),
    ("dual_simplex", "__04_targetyear_dual_simplex_rescue", "04_targetyear_dual_simplex_rescue"),
    ("hard_deterministic_concurrent_simplex", "__05_targetyear_concurrent_simplex_rescue", "05_targetyear_concurrent_simplex_rescue"),
]
PROJECTED_ROUTE = [
    ("scaled_barrier", "__07_targetyear_projected_scaled_barrier", "07_targetyear_projected_scaled_barrier"),
]
R3_REDUCED_ROUTE = [
    ("scaled_barrier", "__08_targetyear_r3_hourly_reduced_scaled_barrier", "08_targetyear_r3_hourly_reduced_scaled_barrier"),
    ("dual_simplex", "__09_targetyear_r3_hourly_reduced_dual_simplex", "09_targetyear_r3_hourly_reduced_dual_simplex"),
]
R4_CONTINUATION_ROUTE = [
    ("r4_observed_seed_primal_continuation", "__10_targetyear_r4_observed_seed_primal_continuation", "10_targetyear_r4_observed_seed_primal_continuation"),
]
R5_CONTINUATION_ROUTE = [
    ("r5_primal_dual_supported_objective_continuation", "__11_targetyear_r5_primal_dual_supported_objective_continuation", "11_targetyear_r5_primal_dual_supported_objective_continuation"),
]
ROUTE_SELECTIONS = {
    "auto": ROUTES,
    "primary": ROUTES[:1],
    "fallback": ROUTES[1:],
    "rescue": ONE_H_ROUTES[:1],
    "dual_rescue": ONE_H_ROUTES[1:2],
    "simplex_rescue": ONE_H_ROUTES[2:],
    "one_hour_robust": ONE_H_ROUTES,
    "reduced_rank": PROJECTED_ROUTE,
    "projected": PROJECTED_ROUTE,
    "r3_reduced": R3_REDUCED_ROUTE,
    "r4_continuation": R4_CONTINUATION_ROUTE,
    "r5_continuation": R5_CONTINUATION_ROUTE,
}


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


def local_output(scenario: str, suffix: str) -> Path:
    return ROOT / "sensitivity_cases" / scenario / "outputs" / f"{scenario}{suffix}"


def run_cmd(cmd: list[str], log: Path) -> tuple[int, float]:
    log.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    env = os.environ.copy()
    env.setdefault("V17_SOLVER_THREADS", "10")
    env.setdefault("V17T2R5_PRIMARY_TIME_LIMIT_SECONDS", "7200")
    env.setdefault("V17T2R5_FALLBACK_TIME_LIMIT_SECONDS", "14400")
    env.setdefault("V17T2R5_CROSSOVER_BASIS", "1")
    with log.open("w", encoding="utf-8", errors="replace") as fh:
        fh.write("COMMAND: " + " ".join(cmd) + "\n")
        fh.write("START: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
        fh.write("ENV: V17_SOLVER_THREADS=" + env["V17_SOLVER_THREADS"] +
                 " V17T2R5_PRIMARY_TIME_LIMIT_SECONDS=" + env["V17T2R5_PRIMARY_TIME_LIMIT_SECONDS"] +
                 " V17T2R5_FALLBACK_TIME_LIMIT_SECONDS=" + env["V17T2R5_FALLBACK_TIME_LIMIT_SECONDS"] + "\n\n")
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
    if profile == "targetyear_deterministic_concurrent":
        return bool(
            status.get("solver_method") in {"4", "4.0"}
            and status.get("solver_crossover") in {"0", "0.0"}
            and status.get("solver_route_role") == "V17T2R5_targetyear_primary_deterministic_concurrent"
            and fnum(status.get("solver_numeric_focus")) == 2.0
            and fnum(status.get("solver_scale_flag")) == -1.0
        )
    if profile == "targetyear_homogeneous_dual_crossover":
        return bool(
            status.get("solver_method") in {"2", "2.0"}
            and status.get("solver_crossover") in {"2", "2.0"}
            and status.get("solver_crossover_basis") in {"1", "1.0"}
            and status.get("solver_bar_homogeneous") in {"1", "1.0"}
            and status.get("solver_route_role") == "V17T2R5_targetyear_fallback_homogeneous_barrier_dual_cleanup"
            and fnum(status.get("solver_numeric_focus")) == 3.0
            and fnum(status.get("solver_scale_flag")) == 2.0
        )
    if profile == "scaled_barrier":
        return bool(
            status.get("solver_method") in {"2", "2.0"}
            and status.get("solver_crossover") in {"0", "0.0"}
            and status.get("solver_bar_homogeneous") in {"0", "0.0"}
            and status.get("solver_route_role") == "primary_scaled_barrier_no_crossover"
            and fnum(status.get("solver_numeric_focus")) == 2.0
            and fnum(status.get("solver_scale_flag")) == -1.0
        )
    if profile == "dual_simplex":
        return bool(
            status.get("solver_method") in {"1", "1.0"}
            and status.get("solver_crossover") in {"0", "0.0"}
            and status.get("solver_route_role") == "fallback_direct_dual_simplex"
            and fnum(status.get("solver_numeric_focus")) == 3.0
            and fnum(status.get("solver_scale_flag")) == 2.0
            and fnum(status.get("solver_aggregate")) == 0.0
            and fnum(status.get("solver_pre_sparsify")) == 0.0
            and fnum(status.get("solver_quad")) == 1.0
        )
    if profile == "hard_deterministic_concurrent_simplex":
        return bool(
            status.get("solver_method") in {"5", "5.0"}
            and status.get("solver_crossover") in {"0", "0.0"}
            and status.get("solver_route_role") == "hard_lp_deterministic_concurrent_simplex_gurobi10"
            and fnum(status.get("solver_numeric_focus")) == 3.0
            and fnum(status.get("solver_scale_flag")) == 2.0
            and fnum(status.get("solver_aggregate")) == 0.0
            and fnum(status.get("solver_pre_sparsify")) == 0.0
            and fnum(status.get("solver_quad")) == 1.0
        )
    if profile == "r4_observed_seed_primal_continuation":
        return bool(
            status.get("solver_method") in {"0", "0.0"}
            and status.get("solver_crossover") in {"0", "0.0"}
            and status.get("solver_lpwarmstart") in {"2", "2.0"}
            and status.get("solver_route_role") == "V17T2R5R4_observed_feasible_start_full_optimal_primal_simplex"
            and fnum(status.get("solver_numeric_focus")) == 3.0
            and fnum(status.get("solver_scale_flag")) == 2.0
            and fnum(status.get("solver_presolve")) == 2.0
        )
    if profile == "r5_primal_dual_supported_objective_continuation":
        return bool(
            status.get("solver_method") in {"0", "0.0"}
            and status.get("solver_crossover") in {"0", "0.0"}
            and status.get("solver_lpwarmstart") in {"1", "1.0"}
            and status.get("solver_route_role") == "V17T2R5R5_primal_dual_supported_exact_objective_continuation"
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
        "gurobi_V17T2R5_targetyear_deterministic_concurrent_optimal_status",
        "gurobi_V17T2R5_targetyear_homogeneous_barrier_dual_cleanup_optimal_status",
        "gurobi_barrier_optimal_status_barconvtol_no_crossover",
        "gurobi_zero_iteration_optimal_under_barrier_configuration",
        "gurobi_dual_simplex_optimal_status",
        "gurobi_hard_deterministic_concurrent_simplex_optimal_status",
        "gurobi_V17T2R5R4_full_optimal_primal_simplex_after_strict_observed_seed",
        "gurobi_V17T2R5R5_full_optimal_primal_simplex_after_primal_dual_supported_objective_continuation",
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
    if status.get("storage_chronology_mode") != "monthly_linked":
        reasons.append("storage_chronology_mode is not monthly_linked")
    if status.get("ldes_proxy_mode") != str(expected["ldes_proxy_mode"]):
        reasons.append(f"ldes_proxy_mode={status.get('ldes_proxy_mode')} expected {expected['ldes_proxy_mode']}")
    if not truth(status.get("storage_interperiod_soc_linked")):
        reasons.append("storage_interperiod_soc_linked=false")
    if truth(status.get("storage_full_chronological_claim_supported")):
        reasons.append("full chronological claim must remain false")
    p = outdir / "storage_chronology_audit.csv"
    if not p.is_file():
        reasons.append("missing storage_chronology_audit.csv")
    else:
        try:
            df = pd.read_csv(p)
            for col in ["linkage_residual_mwh", "lower_bound_violation_mwh", "upper_bound_violation_mwh"]:
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
        "numerical_stability_version": "V17T2R5_targetyear_exact_linked_reoptimization_stage1_official_release_json_safe",
        "solver_solution_target": "optimal_primal_dual_solution_no_basis_requirement",
        "publication_solution_source": "stage1_solver_certified_economic_optimum",
        "successful_cleanup_route": "stage1_official_release",
        "requested_cleanup_profile": "stage1_official_release",
    }
    for col, want in exact.items():
        if status.get(col) != want:
            reasons.append(f"{col}={status.get(col)} expected {want}")

    if str(expected.get("scenario", "")) == "TY2033_CHRONO_1H_OPTIMAL":
        reduced_rank_exact = {
            "legacy_reallocation_formulation_version": "V17T2R5R3_equivalent_hourly_coordinate_projection_v1",
            "legacy_national_energy_identity_pass": "true",
            "legacy_national_energy_closure_constraint_emitted": "false",
            "legacy_zone_caps_encoded_as_variable_bounds": "true",
            "legacy_energy_variable_projection_active": "true",
            "legacy_energy_variable_projection_count": "32",
            "legacy_common_duration_constraints_emitted": "false",
            "legacy_projected_energy_output_reconstruction": "true",
        }
        for col, want in reduced_rank_exact.items():
            if str(status.get(col, "")).strip().lower() != want.lower():
                reasons.append(f"{col}={status.get(col)} expected {want}")

        r3_reduction_text = {
            "algebraic_reduction_version": "V17T2R5R3_equivalent_hourly_coordinate_projection_v1",
            "algebraic_reduction_active": "true",
            "algebraic_reduction_preserves_scientific_inputs": "true",
            "algebraic_reduction_preserves_objective_and_projected_feasible_set": "true",
        }
        for col, want in r3_reduction_text.items():
            if str(status.get(col, "")).strip().lower() != want.lower():
                reasons.append(f"{col}={status.get(col)} expected {want}")
        r3_reduction_counts = {
            "full_gen_timepoint_count": 106848,
            "active_ccs_gen_timepoint_count": 27648,
            "omitted_fixed_zero_ccs_columns": 158400,
            "active_startup_shutdown_gen_timepoint_count": 27648,
            "omitted_objective_neutral_startup_shutdown_columns": 158400,
            "total_omitted_hourly_columns": 316800,
        }
        for col, want in r3_reduction_counts.items():
            if int(fnum(status.get(col), -1)) != want:
                reasons.append(f"{col}={status.get(col)} expected {want}")

        if status.get("solver_profile") == "r4_observed_seed_primal_continuation":
            r4_exact = {
                "r4_observed_seed_continuation_active": "true",
                "r4_seed_attempted": "true",
                "r4_seed_strict_optimal": "true",
                "r4_seed_termination_status": "OPTIMAL",
                "r4_seed_primal_status": "FEASIBLE_POINT",
                "r4_seed_dual_status": "FEASIBLE_POINT",
                "r4_seed_source_scenario": "TY2033_CHRONO_1H_OBSERVED",
                "r4_seed_source_pair_identity_pass": "true",
                "r4_seed_gurobi_objval_gate_pass": "true",
                "r4_seed_objective_scale_gate_pass": "true",
                "r4_seed_full_pstart_set_pass": "true",
                "r4_final_bounds_restored": "true",
            }
            for col, want in r4_exact.items():
                if str(status.get(col, "")).strip().lower() != want.lower():
                    reasons.append(f"{col}={status.get(col)} expected {want}")
            if int(fnum(status.get("r4_seed_gurobi_status"), -1)) != 2:
                reasons.append(f"r4_seed_gurobi_status={status.get('r4_seed_gurobi_status')} expected 2")
            if int(fnum(status.get("r4_seed_result_count"), -1)) < 1:
                reasons.append("r4_seed_result_count < 1")
            if int(fnum(status.get("r4_seed_allocation_count"), -1)) != 32:
                reasons.append(f"r4_seed_allocation_count={status.get('r4_seed_allocation_count')} expected 32")
            if int(fnum(status.get("r4_final_restored_bound_count"), -1)) != 32:
                reasons.append(f"r4_final_restored_bound_count={status.get('r4_final_restored_bound_count')} expected 32")
            if abs(fnum(status.get("r4_seed_national_power_residual_mw"), float("inf"))) > 1.0e-6:
                reasons.append("r4 seed national power residual exceeds 1e-6 MW")
            if abs(fnum(status.get("r4_seed_national_energy_residual_mwh"), float("inf"))) > 1.0e-6:
                reasons.append("r4 seed national energy residual exceeds 1e-6 MWh")
            if fnum(status.get("r4_seed_minimum_lower_bound_slack_mw"), float("-inf")) < -1.0e-9:
                reasons.append("r4 seed violates an optimized allocation lower bound")
            if fnum(status.get("r4_seed_minimum_cap_slack_mw"), float("-inf")) < -1.0e-6:
                reasons.append("r4 seed violates an optimized allocation cap")
            if fnum(status.get("r4_final_max_lower_bound_error_mw"), float("inf")) != 0.0:
                reasons.append("r4 final lower bounds were not restored exactly")
            if fnum(status.get("r4_final_max_upper_bound_error_mw"), float("inf")) != 0.0:
                reasons.append("r4 final upper bounds were not restored exactly")
            if int(fnum(status.get("r4_seed_full_pstart_count"), -1)) != int(fnum(status.get("model_variable_count_after_algebraic_reduction"), -2)):
                reasons.append("r4 full PStart count does not equal the reduced model variable count")
            if fnum(status.get("r4_seed_full_pstart_max_bound_violation"), float("inf")) > 1.0e-8:
                reasons.append("r4 full PStart violates a restored final-model bound")

        if status.get("solver_profile") == "r5_primal_dual_supported_objective_continuation":
            r5_exact = {
                "r4_seed_attempted": "true",
                "r4_seed_strict_optimal": "true",
                "r4_seed_termination_status": "OPTIMAL",
                "r4_seed_primal_status": "FEASIBLE_POINT",
                "r4_seed_dual_status": "FEASIBLE_POINT",
                "r4_seed_source_scenario": "TY2033_CHRONO_1H_OBSERVED",
                "r4_seed_source_pair_identity_pass": "true",
                "r4_seed_gurobi_objval_gate_pass": "true",
                "r4_seed_objective_scale_gate_pass": "true",
                "r4_final_bounds_restored": "true",
                "r5_primal_dual_supported_continuation_active": "true",
                "r5_seed_raw_primal_finite": "true",
                "r5_seed_raw_dual_finite": "true",
                "r5_seed_raw_reduced_cost_finite": "true",
                "r5_primal_dual_start_set_pass": "true",
                "r5_bridge_strict_optimal": "true",
                "r5_bridge_termination_status": "OPTIMAL",
                "r5_bridge_primal_status": "FEASIBLE_POINT",
                "r5_bridge_dual_status": "FEASIBLE_POINT",
                "r5_bridge_basis_available": "true",
                "r5_homotopy_all_strict_optimal": "true",
                "r5_final_objective_restored": "true",
            }
            for col, want in r5_exact.items():
                if str(status.get(col, "")).strip().lower() != want.lower():
                    reasons.append(f"{col}={status.get(col)} expected {want}")
            if int(fnum(status.get("r4_seed_gurobi_status"), -1)) != 2:
                reasons.append("r5 seed Gurobi status is not 2")
            if int(fnum(status.get("r5_bridge_gurobi_status"), -1)) != 2:
                reasons.append("r5 bridge Gurobi status is not 2")
            if int(fnum(status.get("r5_bridge_result_count"), -1)) < 1:
                reasons.append("r5 bridge result_count < 1")
            raw_vars = int(fnum(status.get("r5_seed_raw_variable_count"), -1))
            raw_rows = int(fnum(status.get("r5_seed_raw_constraint_count"), -1))
            if raw_vars != int(fnum(status.get("model_variable_count_after_algebraic_reduction"), -2)):
                reasons.append("r5 raw variable count does not match final model")
            if int(fnum(status.get("r5_bridge_vbasis_count"), -1)) != raw_vars:
                reasons.append("r5 VBasis count does not match raw variable count")
            if int(fnum(status.get("r5_bridge_cbasis_count"), -1)) != raw_rows:
                reasons.append("r5 CBasis count does not match raw constraint count")
            if int(fnum(status.get("r5_support_objective_adjustment_count"), -1)) != 32:
                reasons.append("r5 support-objective adjustment count is not 32")
            if int(fnum(status.get("r5_final_objective_restored_count"), -1)) != 32:
                reasons.append("r5 final objective restoration count is not 32")
            if fnum(status.get("r5_final_max_objective_coefficient_error"), float("inf")) != 0.0:
                reasons.append("r5 final objective coefficients were not restored exactly")
            requested = "0.001;0.003;0.01;0.03;0.1;0.25;0.5;0.75"
            if status.get("r5_homotopy_levels_requested") != requested:
                reasons.append("r5 homotopy schedule changed")
            if status.get("r5_homotopy_levels_completed") != requested:
                reasons.append("r5 homotopy schedule did not complete")

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
    expected_tp_count = 288 if int(expected.get("time_resolution_h", 4)) == 1 else 72
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
    return shutil.make_archive(str(dest / f"{scenario}_V17T2R5_failed_diagnostics"), "zip", root_dir=src)


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


def run_one(julia: str, row: dict[str, Any], routes: list[tuple[str, str, str]], force_rerun: bool = False) -> dict[str, Any]:
    scenario = str(row["scenario"])
    if not force_rerun:
        existing = existing_official_record(row)
        if existing is not None:
            print(json.dumps(existing, ensure_ascii=False, indent=2))
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
        if status.get("stage1_termination_status") == "OPTIMAL":
            stop_reason = "solver_optimal_but_downstream_gate_failed_stop_for_audit_repair"
            break
        stop_reason = "uncertified_route_try_next_prespecified_fallback"
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
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--julia", default=os.environ.get("JULIA_EXE", "julia"))
    ap.add_argument("--pair", choices=["TY2028_CHRONO", "TY2033_CHRONO", "TY2033_CHRONO_LDES", "TY2033_CHRONO_1H", "ALL"], default="ALL")
    ap.add_argument("--scenario", default="")
    ap.add_argument("--skip-prepare", action="store_true")
    ap.add_argument("--clean-central", action="store_true")
    ap.add_argument("--route", choices=sorted(ROUTE_SELECTIONS), default="auto",
                    help="auto: ordinary primary+fallback; one_hour_robust: legacy rescue ladder; r3_reduced: exact hourly reduction Barrier then Dual Simplex; r4_continuation: PStart diagnostic; r5_continuation: strict primal+dual supported-basis objective continuation; projected/reduced_rank retain the R2 log route")
    ap.add_argument("--force-rerun", action="store_true",
                    help="rerun even when a previously promoted output still passes every strict gate")
    ap.add_argument("--continue-after-failure", action="store_true",
                    help="continue to later scenarios after one scenario fails both selected exact routes")
    args = ap.parse_args()

    if args.route in {"r3_reduced", "r4_continuation", "r5_continuation"} and args.scenario != "TY2033_CHRONO_1H_OPTIMAL":
        raise SystemExit(
            f"The {args.route} route is isolated to --scenario TY2033_CHRONO_1H_OPTIMAL; "
            "it will not run or clean any other case."
        )

    if args.clean_central and CENTRAL.exists():
        shutil.rmtree(CENTRAL)
    CENTRAL.mkdir(parents=True, exist_ok=True)
    ATTEMPTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    if not args.skip_prepare:
        subprocess.check_call([sys.executable, str(ROOT / "tools" / "prepare_targetyear_cases.py")], cwd=ROOT)
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
    records: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        rec = run_one(args.julia, r.to_dict(), routes, force_rerun=args.force_rerun)
        records.append(rec)
        if not rec["publication_strict_success"] and not args.continue_after_failure:
            print("Stopping before later scenarios to conserve compute time. Use --continue-after-failure only for explicit diagnostics.")
            break

    merged = pd.DataFrame(records)
    if SUMMARY_CSV.is_file():
        prev = pd.read_csv(SUMMARY_CSV)
        merged = pd.concat([prev, merged], ignore_index=True).drop_duplicates(subset=["scenario"], keep="last")
    merged.to_csv(SUMMARY_CSV, index=False)
    SUMMARY_JSON.write_text(json.dumps(merged.to_dict(orient="records"), ensure_ascii=False, indent=2), encoding="utf-8")
    if not all(r["publication_strict_success"] for r in records):
        raise SystemExit("One or more target-year scenarios failed the selected exact route ladder or a downstream release gate. See batch_logs, sensitivity_outputs/_attempts and failed_diagnostics.")
    print(f"All {len(records)} requested V17T2R6-input scenarios passed strict publication validation.")


if __name__ == "__main__":
    main()
