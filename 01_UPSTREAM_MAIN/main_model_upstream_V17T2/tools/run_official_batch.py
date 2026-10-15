#!/usr/bin/env python3
"""Run Storage V17 publication scenarios with a stage-1-official policy.

Each attempt launches a fresh Julia process and rebuilds the model. The formal
result is always the solver-certified stage-1 economic optimum. Optional sparse-
face cleanup remains available only through explicit diagnostic launchers and is
never part of the official batch fallback tree.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCEN = ROOT / "storage_runner" / "scenarios_storage_master.csv"
LOGDIR = ROOT / "batch_logs"
OUTROOT = ROOT / "outputs"
SUMMARY = ROOT / "storage_runner" / "storage_batch_run_summary.csv"
HARD_LP_SCENARIOS = {
    "SL10_CARBON_TIGHT_OBSERVED",
    "SL13_COST_LOW_OPTIMAL",
}
SL10_BARRIER_RESCUE_SCENARIOS = {
    "SL10_CARBON_TIGHT_OBSERVED",
}


def _true(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def run_cmd(cmd: list[str], log_path: Path) -> tuple[int, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("COMMAND: " + " ".join(map(str, cmd)) + "\n")
        log.write("START: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
        log.flush()
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, text=True)
        rc = proc.wait()
        log.write("\nEND: " + time.strftime("%Y-%m-%d %H:%M:%S") + f"\nRETURN_CODE: {rc}\n")
    return rc, time.time() - start


def scenario_rows(only: list[str] | None, include_all_defined: bool, scenario_set: str) -> pd.DataFrame:
    df = pd.read_csv(SCEN)
    if only:
        wanted = set(only)
        selected = df[df["scenario"].astype(str).isin(wanted)].copy()
        missing = wanted - set(selected["scenario"].astype(str))
        if missing:
            raise SystemExit("Unknown scenario(s): " + ", ".join(sorted(missing)))
        return selected
    official = df["v17_official_unique"].astype(str).str.lower().isin({"true", "1", "yes"})
    if include_all_defined or scenario_set == "spatial_legacy_full":
        return df[official].copy()
    story = {
        "spatial_legacy_core": "spatial_legacy_core",
        "spatial_legacy_robustness": "spatial_legacy_robustness",
    }[scenario_set]
    return df[official & df["legacy_story_set"].astype(str).eq(story)].copy()


def local_output_dir(scenario: str, suffix: str) -> Path:
    return ROOT / "storage_cases" / scenario / "outputs" / f"{scenario}{suffix}"


def clean_attempt_output(scenario: str, suffix: str) -> None:
    path = local_output_dir(scenario, suffix)
    if path.exists():
        shutil.rmtree(path)


def attempt_central_dir(scenario: str, attempt_label: str) -> Path:
    return OUTROOT / "_attempts" / scenario / attempt_label


def preserve_attempt(scenario: str, attempt_label: str, suffix: str) -> tuple[str, bool]:
    src = local_output_dir(scenario, suffix)
    dst = attempt_central_dir(scenario, attempt_label)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        return str(dst), False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return str(dst), True


def promote_success(scenario: str, attempt_dir: str) -> tuple[str, bool]:
    src = Path(attempt_dir)
    dst = OUTROOT / f"{scenario}__main"
    OUTROOT.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        return str(dst), False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    from publication_source_common import write_result_fingerprint
    write_result_fingerprint(ROOT, dst, ROOT / "storage_cases" / scenario, scenario, "main")
    return str(dst), True


def read_status(outdir: str) -> dict[str, str]:
    status_file = Path(outdir) / "solve_status.csv"
    if not status_file.exists():
        return {"status_read_error": "solve_status.csv missing"}
    try:
        frame = pd.read_csv(status_file)
        if len(frame) != 1:
            return {"status_read_error": f"expected one solve_status row; found {len(frame)}"}
        return {str(k): str(v) for k, v in frame.iloc[0].to_dict().items()}
    except Exception as exc:
        return {"status_read_error": f"solve_status read error: {exc}"}


def stage1_profile_gate(status: dict[str, str]) -> bool:
    profile = status.get("solver_profile", "")
    expected = {
        "scaled_barrier": {
            "method": {"2", "2.0"},
            "role": "primary_scaled_barrier_no_crossover",
            "numeric_focus": 2.0,
            "scale_flag": -1.0,
        },
        "deterministic_concurrent": {
            "method": {"4", "4.0"},
            "role": "fallback_deterministic_concurrent_lp",
            "numeric_focus": 2.0,
            "scale_flag": -1.0,
        },
        "dual_simplex": {
            "method": {"1", "1.0"},
            "role": "fallback_direct_dual_simplex",
            "numeric_focus": 3.0,
            "scale_flag": 2.0,
        },
        "hard_deterministic_concurrent_simplex": {
            "method": {"5", "5.0"},
            "role": "hard_lp_deterministic_concurrent_simplex_gurobi10",
            "numeric_focus": 3.0,
            "scale_flag": 2.0,
        },
        "hard_primal_simplex": {
            "method": {"0", "0.0"},
            "role": "hard_lp_direct_primal_simplex",
            "numeric_focus": 3.0,
            "scale_flag": 2.0,
        },
        "hard_homogeneous_barrier": {
            "method": {"2", "2.0"},
            "role": "hard_lp_homogeneous_barrier_with_crossover",
            "numeric_focus": 3.0,
            "scale_flag": 2.0,
            "crossover": {"1", "1.0"},
            "bar_homogeneous": {"1", "1.0"},
        },
        "hard_homogeneous_barrier_no_crossover": {
            "method": {"2", "2.0"},
            "role": "hard_lp_homogeneous_barrier_no_crossover",
            "numeric_focus": 3.0,
            "scale_flag": 2.0,
            "crossover": {"0", "0.0"},
            "bar_homogeneous": {"1", "1.0"},
        },
    }.get(profile)
    if expected is None:
        return False
    bar_homogeneous_ok = (
        "bar_homogeneous" not in expected
        or status.get("solver_bar_homogeneous") in expected["bar_homogeneous"]
    )
    return bool(
        status.get("solver_method") in expected["method"]
        and status.get("solver_route_role") == expected["role"]
        and status.get("solver_crossover") in expected.get("crossover", {"0", "0.0"})
        and bar_homogeneous_ok
        and status.get("solver_lpwarmstart") in {"0", "0.0"}
        and status.get("solver_presolve") in {"2", "2.0"}
        and _float(status.get("solver_numeric_focus")) == expected["numeric_focus"]
        and _float(status.get("solver_scale_flag")) == expected["scale_flag"]
        and _float(status.get("solver_bar_conv_tol")) <= 1.0e-8
    )


def stage1_optimality_proof_gate(status: dict[str, str]) -> bool:
    source = status.get("stage1_economic_optimality_proof_source", "")
    accepted = {
        "gurobi_barrier_optimal_status_barconvtol_no_crossover",
        "gurobi_zero_iteration_optimal_under_barrier_configuration",
        "gurobi_deterministic_concurrent_optimal_status",
        "gurobi_dual_simplex_optimal_status",
        "gurobi_hard_deterministic_concurrent_simplex_optimal_status",
        "gurobi_hard_primal_simplex_optimal_status",
        "gurobi_hard_homogeneous_barrier_crossover_optimal_status",
        "gurobi_hard_homogeneous_barrier_no_crossover_optimal_status",
    }
    return bool(
        source in accepted
        and status.get("stage1_certificate_grade") == "strict_solver_native"
        and _true(status.get("stage1_native_solver_certificate_pass"))
        and _true(status.get("stage1_native_algorithm_gate_pass"))
        and _true(status.get("stage1_objective_scale_gate_pass"))
        and _true(status.get("stage1_gurobi_status_gate_pass"))
        and _true(status.get("stage1_gurobi_objval_gate_pass"))
    )


def stage1_certified(status: dict[str, str]) -> bool:
    return bool(
        status.get("stage1_termination_status") == "OPTIMAL"
        and status.get("stage1_primal_status") == "FEASIBLE_POINT"
        and status.get("stage1_dual_status") == "FEASIBLE_POINT"
        and _float(status.get("stage1_result_count")) >= 1.0
        and _true(status.get("stage1_status_gate_pass"))
        and stage1_optimality_proof_gate(status)
        and stage1_profile_gate(status)
    )


def official_release_policy_gate(status: dict[str, str], outdir: str) -> bool:
    policy_file = Path(outdir) / "RESULT_INTERPRETATION_POLICY.csv"
    return bool(
        status.get("requested_cleanup_profile") == "stage1_official_release"
        and status.get("cleanup_profile") == "stage1_official_release"
        and status.get("successful_cleanup_route") == "stage1_official_release"
        and status.get("cleanup_route_role") == "official_stage1_economic_solution_cleanup_not_required_for_release"
        and status.get("publication_solution_source") == "stage1_solver_certified_economic_optimum"
        and _true(status.get("stage1_official_release_selected"))
        and _true(status.get("stage1_official_release_pass"))
        and _true(status.get("cleanup_diagnostic_nonblocking"))
        and not _true(status.get("cleanup_diagnostic_attempted"))
        and _true(status.get("gross_dispatch_degeneracy_sensitive"))
        and not _true(status.get("gross_dispatch_operational_interpretation_allowed"))
        and status.get("gross_dispatch_allowed_use") == "accounting_reconstruction_and_aggregate_balance_only"
        and _true(status.get("investment_capacity_policy_outputs_release_eligible"))
        and policy_file.exists()
    )


def strict_success(status: dict[str, str], rc: int, preserved: bool, outdir: str) -> bool:
    return bool(
        rc == 0 and preserved
        and stage1_certified(status)
        and status.get("termination_status") == "OPTIMAL"
        and status.get("primal_status") == "FEASIBLE_POINT"
        and status.get("dual_status") == "FEASIBLE_POINT"
        and _true(status.get("has_primal_values"))
        and _true(status.get("solve_gate_pass"))
        and _true(status.get("strict_physical_audit_pass"))
        and _true(status.get("result_export_complete"))
        and _true(status.get("strict_export_pass"))
        and status.get("audit_export_result_tier") == "official_stage1_economic_optimum"
        and _true(status.get("regularization_share_gate_pass"))
        and _true(status.get("lexicographic_economic_gate_pass"))
        and status.get("cleanup_strategy_version") == "V17_stage1_official_release_optional_sparse_face_diagnostic_cleanup_nonblocking"
        and status.get("numerical_stability_version") == "V17_solver_certified_stage1_official_release_degeneracy_disclosure_cleanup_diagnostic_nonblocking_json_safe"
        and status.get("economic_objective_scale_usd") in {"1000000.0", "1000000"}
        and status.get("solver_solution_target") == "optimal_primal_dual_solution_no_basis_requirement"
        and official_release_policy_gate(status, outdir)
        and _true(status.get("model_is_pure_lp"))
        and _float(status.get("model_binary_variable_count")) == 0.0
        and _float(status.get("model_integer_variable_count")) == 0.0
        and _true(status.get("cdr_module_exclusion_gate_pass"))
        and not _true(status.get("storage_cdr_modules_compiled"))
        and _float(status.get("nbccs_compiled_project_count")) == 0.0
        and _float(status.get("nbccs_compiled_build_index_count")) == 0.0
        and _float(status.get("nbccs_compiled_period_index_count")) == 0.0
        and not _true(status.get("dac_module_enabled"))
        and status.get("representative_timepoint_count") in {"504", "504.0"}
        and not _true(status.get("storage_long_duration_claim_supported"))
        and not _true(status.get("allow_nbccs"))
        and not _true(status.get("allow_daccs"))
        and not _true(status.get("allow_beccs"))
        and _true(status.get("official_cdr_disabled"))
        and _true(status.get("legacy_allocation_audit_pass"))
    )


def run_solver_once(
    scenario: str,
    julia: str,
    stage1_profile: str,
    suffix: str,
    attempt_label: str,
    log_path: Path,
) -> dict[str, object]:
    clean_attempt_output(scenario, suffix)
    cmd = [
        julia,
        "storage_runner/run_storage_one_solver_task.jl",
        "--scenario", scenario,
        "--solver_profile", stage1_profile,
        "--cleanup_profile", "stage1_official_release",
        "--solver_output_suffix", suffix,
    ]
    rc, seconds = run_cmd(cmd, log_path)
    attempt_dir, preserved = preserve_attempt(scenario, attempt_label, suffix)
    status = read_status(attempt_dir)
    success = strict_success(status, rc, preserved, attempt_dir)
    canonical_dir, centralized = promote_success(scenario, attempt_dir) if success else (attempt_dir, preserved)
    return {
        "return_code": rc,
        "seconds": seconds,
        "attempt_output_dir": attempt_dir,
        "central_output_dir": canonical_dir,
        "centralized": centralized,
        "status": status,
        "success": success,
        "attempt_label": attempt_label,
        "stage1_profile": stage1_profile,
    }


def _archive_failed_diagnostics(scenario: str) -> str:
    source = OUTROOT / "_attempts" / scenario
    if not source.exists():
        return ""
    archive_root = ROOT / "failed_diagnostics"
    archive_root.mkdir(parents=True, exist_ok=True)
    archive_base = archive_root / f"{scenario}_V17_failed_diagnostics"
    return shutil.make_archive(str(archive_base), "zip", root_dir=source)


def run_one(scenario: str, julia: str, auto_safe_retry: bool = False) -> dict[str, object]:
    if scenario in SL10_BARRIER_RESCUE_SCENARIOS:
        # V17T2: exact same SL10 LP and hard homogeneous-barrier settings as
        # the converged V17T1 barrier phase, but without the crossover phase
        # that alone exhausted the 6-hour limit.
        routes = [
            ("hard_homogeneous_barrier_no_crossover", "__v17t2_homogeneous_barrier_nocrossover_official", "01_v17t2_homogeneous_barrier_nocrossover_official", LOGDIR / f"{scenario}__v17t2_homogeneous_barrier_nocrossover.log"),
        ]
        if auto_safe_retry:
            routes.extend([
                ("hard_deterministic_concurrent_simplex", "__hard_concurrent_simplex_official", "02_hard_concurrent_simplex_official", LOGDIR / f"{scenario}__hard_concurrent_simplex_retry.log"),
                ("hard_primal_simplex", "__hard_primal_simplex_official", "03_hard_primal_simplex_official", LOGDIR / f"{scenario}__hard_primal_simplex_retry.log"),
                ("hard_homogeneous_barrier", "__hard_homogeneous_barrier_official", "04_hard_homogeneous_barrier_official", LOGDIR / f"{scenario}__hard_homogeneous_barrier_retry.log"),
            ])
    elif scenario in HARD_LP_SCENARIOS:
        routes = [
            ("hard_deterministic_concurrent_simplex", "__hard_concurrent_simplex_official", "01_hard_concurrent_simplex_official", LOGDIR / f"{scenario}.log"),
        ]
        if auto_safe_retry:
            routes.extend([
                ("hard_primal_simplex", "__hard_primal_simplex_official", "02_hard_primal_simplex_official", LOGDIR / f"{scenario}__hard_primal_simplex_retry.log"),
                ("hard_homogeneous_barrier", "__hard_homogeneous_barrier_official", "03_hard_homogeneous_barrier_official", LOGDIR / f"{scenario}__hard_homogeneous_barrier_retry.log"),
            ])
    else:
        # Exact V17 standard route.  No hard-LP parameter is visible here.
        routes = [
            ("scaled_barrier", "__stage1_official", "01_stage1_barrier_official", LOGDIR / f"{scenario}.log"),
        ]
        if auto_safe_retry:
            routes.extend([
                ("deterministic_concurrent", "__stage1_concurrent_official", "02_stage1_concurrent_official", LOGDIR / f"{scenario}__stage1_concurrent_retry.log"),
                ("dual_simplex", "__stage1_dual_official", "03_stage1_dual_official", LOGDIR / f"{scenario}__stage1_dual_retry.log"),
            ])

    total_seconds = 0.0
    attempts_used: list[str] = []
    attempt_dirs: list[str] = []
    final: dict[str, object] | None = None
    fallback_stop_reason = "controlled_fallback_disabled"

    for i, (profile, suffix, label, log_path) in enumerate(routes):
        attempts_used.append(label)
        final = run_solver_once(scenario, julia, profile, suffix, label, log_path)
        total_seconds += float(final["seconds"])
        attempt_dirs.append(str(final.get("attempt_output_dir", "")))
        if bool(final["success"]):
            fallback_stop_reason = "official_stage1_release_success" if i == 0 else "official_stage1_release_success_after_solver_retry"
            break
        status = final.get("status", {})
        if isinstance(status, dict) and stage1_certified(status):
            # A certified stage 1 with a downstream export/audit failure must be fixed,
            # not hidden by changing the optimization algorithm.
            fallback_stop_reason = "stage1_certified_but_downstream_release_gate_failed"
            break
        fallback_stop_reason = "stage1_uncertified_try_next_solver_route" if auto_safe_retry else "controlled_fallback_disabled"
    else:
        fallback_stop_reason = "all_stage1_solver_routes_uncertified"

    assert final is not None
    status = final["status"]
    assert isinstance(status, dict)
    diagnostic_archive = "" if bool(final["success"]) else _archive_failed_diagnostics(scenario)
    diagnostic_warning = _true(status.get("stage1_external_diagnostic_warning"))
    result_tier = (
        "official_stage1_economic_optimum_with_nonblocking_certificate_warning"
        if final["success"] and diagnostic_warning
        else "official_stage1_economic_optimum" if final["success"]
        else "failed_publication_gate"
    )
    row: dict[str, object] = {
        "scenario": scenario,
        "return_code": final["return_code"],
        "seconds": round(total_seconds, 2),
        "central_output_dir": final["central_output_dir"],
        "centralized": final["centralized"],
        "stage1_attempts_used": ";".join(attempts_used),
        "attempt_output_dirs": ";".join(attempt_dirs),
        "safe_retry_used": len(attempts_used) > 1,
        "fallback_stop_reason": fallback_stop_reason,
        "successful_attempt": final.get("attempt_label", ""),
        "publication_strict_success": final["success"],
        "result_tier": result_tier,
        "failed_diagnostic_archive": diagnostic_archive,
    }
    status_scenario_label = status.get("scenario", "")
    row.update(status)
    # solve_status.csv stores the solver output tag, which may include an attempt
    # suffix. Preserve it separately and keep the batch scenario key canonical.
    row["solver_output_scenario"] = status_scenario_label
    row["scenario"] = scenario
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--julia", default=os.environ.get("JULIA_EXE", "julia"))
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--all-defined", action="store_true")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--skip-validate", action="store_true")
    parser.add_argument(
        "--scenario-set", default="spatial_legacy_full",
        choices=["spatial_legacy_full", "spatial_legacy_core", "spatial_legacy_robustness"],
    )
    parser.add_argument(
        "--enable-controlled-fallback", action="store_true",
        help="After an uncertified primary stage-1 solve, retry Method=4 then Method=1 in fresh Julia processes. Cleanup algorithms are not part of the official fallback tree.",
    )
    parser.add_argument("--clean-previous", action="store_true")
    parser.add_argument("--skip-postprocess", action="store_true")
    args = parser.parse_args()

    if args.clean_previous:
        for path in [LOGDIR, OUTROOT, ROOT / "storage_cases", ROOT / "failed_diagnostics"]:
            if path.exists():
                shutil.rmtree(path)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    OUTROOT.mkdir(parents=True, exist_ok=True)

    if args.prepare:
        rc, _ = run_cmd([sys.executable, "tools/build_storage_base_case.py"], LOGDIR / "_00_build_storage_base_case.log")
        if rc != 0:
            raise SystemExit("Base-case build failed. See batch_logs/_00_build_storage_base_case.log")
        if not args.skip_validate:
            checks = [
                ([sys.executable, "tools/validate_storage_inputs.py"], "_01_validate_storage_inputs.log"),
                ([sys.executable, "tools/check_v17_ne_config.py"], "_02_check_v17_config.log"),
                ([sys.executable, "tools/audit_julia_empty_collection_safety.py"], "_02b_empty_collection_safety.log"),
                ([sys.executable, "tools/audit_numerical_stability_v17.py"], "_02c_numerical_stability.log"),
                ([sys.executable, "tools/audit_objective_certificate_v17.py"], "_02d_objective_certificate.log"),
                ([sys.executable, "tools/audit_julia_syntax_v17.py"], "_02e_julia_syntax.log"),
                ([sys.executable, "tools/audit_v17_release_policy.py"], "_02f_stage1_release_policy.log"),
            ]
            for cmd, name in checks:
                rc, _ = run_cmd(cmd, LOGDIR / name)
                if rc != 0:
                    raise SystemExit(f"Pre-run validation failed. See batch_logs/{name}")
        prep = [sys.executable, "tools/prepare_storage_cases.py"]
        if args.only:
            for scenario in args.only:
                rc, _ = run_cmd(prep + ["--scenario", scenario], LOGDIR / f"_03_prepare_{scenario}.log")
                if rc != 0:
                    raise SystemExit(f"Case preparation failed for {scenario}")
        elif args.all_defined:
            rc, _ = run_cmd(prep + ["--all"], LOGDIR / "_03_prepare_all_defined.log")
            if rc != 0:
                raise SystemExit("Case preparation failed for all-defined scenarios")
        else:
            rc, _ = run_cmd(prep + ["--official", "--scenario-set", args.scenario_set], LOGDIR / f"_03_prepare_{args.scenario_set}.log")
            if rc != 0:
                raise SystemExit(f"Case preparation failed for {args.scenario_set}")

    selected = scenario_rows(args.only, args.all_defined, args.scenario_set)
    scenarios = list(selected["scenario"].astype(str))
    if not scenarios:
        raise SystemExit("No scenarios selected")
    print(f"Running {len(scenarios)} scenario(s), max_workers={args.max_workers}")
    print("Scenario set:", ", ".join(scenarios))
    print("V17T2 official route: exact V17 standard solver tree; SL10 uses evidence-selected homogeneous barrier without crossover; SL13 retains isolated hard-LP routes; sparse-face cleanup is diagnostic-only and non-blocking")

    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = {pool.submit(run_one, sc, args.julia, args.enable_controlled_fallback): sc for sc in scenarios}
        for future in as_completed(futures):
            scenario = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    "scenario": scenario,
                    "return_code": -999,
                    "seconds": 0.0,
                    "publication_strict_success": False,
                    "result_tier": "batch_exception",
                    "status_read_error": repr(exc),
                }
            rows.append(row)
            pd.DataFrame(rows).sort_values("scenario").to_csv(SUMMARY, index=False)
            print(
                f"[{scenario}] success={row.get('publication_strict_success')} "
                f"stage1={row.get('stage1_termination_status', '')} "
                f"source={row.get('publication_solution_source', '')} tier={row.get('result_tier')}"
            )

    summary = pd.DataFrame(rows).sort_values("scenario")
    summary.to_csv(SUMMARY, index=False)
    failures = summary[~summary["publication_strict_success"].astype(bool)]
    if not failures.empty:
        print("PUBLICATION BATCH FAILED:", len(failures), "scenario(s) did not pass strict gates")
        display = [c for c in ["scenario", "stage1_termination_status", "publication_solution_source", "result_tier", "status_read_error"] if c in failures.columns]
        print(failures[display].to_string(index=False))
        raise SystemExit(1)

    if not args.skip_postprocess:
        print("SOLVER BATCH PASSED. Running strict V17 postprocessing.")
        post_steps = [
            ([sys.executable, "postprocess/preflight_spatial_legacy_outputs.py", "--scenario-set", args.scenario_set], "_90_postprocess_preflight.log"),
            ([sys.executable, "postprocess/build_spatial_legacy_tables.py", "--scenario-set", args.scenario_set], "_91_postprocess_tables.log"),
            ([sys.executable, "postprocess/plot_spatial_legacy_figures.py"], "_92_postprocess_figures.log"),
            ([sys.executable, "postprocess/validate_spatial_legacy_release.py", "--scenario-set", args.scenario_set], "_93_postprocess_release_validation.log"),
        ]
        for cmd, name in post_steps:
            rc, _ = run_cmd(cmd, LOGDIR / name)
            if rc != 0:
                raise SystemExit(f"Strict postprocessing failed. See batch_logs/{name}")
        print("V17 STRICT POSTPROCESSING PASSED.")
    print("PUBLICATION BATCH PASSED. Summary:", SUMMARY)


if __name__ == "__main__":
    main()
