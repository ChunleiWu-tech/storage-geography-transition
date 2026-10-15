#!/usr/bin/env python3
"""Static publication-release configuration audit for Storage V17."""
from __future__ import annotations

from pathlib import Path
import json
import py_compile

import pandas as pd

from publication_source_contract import expected_storage_power_mw, expected_storage_energy_mwh

ROOT = Path(__file__).resolve().parents[1]
AUD = ROOT / "audits"
AUD.mkdir(exist_ok=True)
MASTER = ROOT / "storage_runner" / "scenarios_storage_master.csv"
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_v1.jl"
RUNNER = ROOT / "storage_runner" / "run_storage_one_solver_task.jl"
BATCH = ROOT / "tools" / "run_official_batch.py"
SOURCE_LOAD = ROOT / "storage_runner" / "check_v17_source_load.jl"
RUNTIME_BAT = ROOT / "CHECK_V17_RUNTIME.bat"
REGISTRY = ROOT / "postprocess" / "figure_output_registry_v17.csv"
TRUE = {"true", "1", "yes"}


def main() -> None:
    rows: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: object = "", severity: str = "error") -> None:
        rows.append({"check": name, "pass": bool(passed), "detail": str(detail), "severity": severity})

    failures: list[str] = []
    pyfiles = sorted((ROOT / "tools").glob("*.py")) + sorted((ROOT / "postprocess").glob("*.py"))
    for path in pyfiles:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:  # pragma: no cover - diagnostic path
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
    add("python_compile", not failures, failures)

    master = pd.read_csv(MASTER)
    required_columns = {
        "scenario", "v17_official_unique", "legacy_story_set", "allow_beccs",
        "allow_genccs", "nbccs_dac_genccs", "v17_claim_scope",
    }
    add("scenario_master_columns", required_columns.issubset(master.columns), sorted(required_columns - set(master.columns)))
    official = master[master["v17_official_unique"].astype(str).str.lower().isin(TRUE)].copy()
    add("sixteen_official_scenarios", len(official) == 16, len(official))
    add("scenario_names_unique", official["scenario"].nunique() == len(official), official["scenario"].tolist())
    add("all_official_no_beccs", (~official["allow_beccs"].astype(bool)).all(), official.loc[official["allow_beccs"].astype(bool), "scenario"].tolist())
    add(
        "all_official_declare_no_cdr",
        official["nbccs_dac_genccs"].astype(str).str.contains("nbccs_daccs_beccs_disabled", case=False, regex=False).all(),
        "NBCCS, DACCS and BECCS disabled; fossil generator CCS remains separately declared",
    )
    add(
        "claim_scope_excludes_long_duration",
        official["v17_claim_scope"].astype(str).str.contains("no multi-day", case=False, regex=False).all(),
        "representative-day evidence boundary",
    )

    model = MODEL.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    batch = BATCH.read_text(encoding="utf-8")
    required_model_tokens = {
        "scaled_economic_objective": "ECONOMIC_OBJECTIVE_SCALE_USD = 1.0e6",
        "configurable_threads": "V17_SOLVER_THREADS",
        "barrier_primary": 'profile == "scaled_barrier"',
        "barrier_no_crossover": "crossover = 0",
        "native_solver_certificate": "stage1_native_solver_certificate_pass",
        "native_barrier_proof_source": "gurobi_barrier_optimal_status_barconvtol_no_crossover",
        "native_zero_iteration_proof_source": "gurobi_zero_iteration_optimal_under_barrier_configuration",
        "presolve_safe_iteration_mode": "stage1_zero_iteration_optimal",
        "native_gurobi_status": "stage1_gurobi_status_gate_pass",
        "native_gurobi_objval": "stage1_gurobi_objval_gate_pass",
        "external_diagnostic_tolerance": "STAGE1_CERT_ACCEPT_REL_TOL",
        "safe_objbound": "_safe_solve_float(() -> objective_bound(mod))",
        "safe_dual_objective": "_safe_solve_float(() -> dual_objective_value(mod))",
        "certificate_grade": "strict_solver_native",
        "external_diagnostic_only": "stage1_dual_objective_diagnostic_only",
        "single_cleanup_route": "cleanup_route_for_profile(cleanup_profile)",
        "economic_cost_band": "Enforce_Lexicographic_Economic_Cost_Band",
        "aggregate_generation_locks": "gen_build_groups",
        "aggregate_storage_energy_locks": "storage_energy_groups",
        "retirement_locks": "retirement_groups",
        "ccs_locks": "ccs_groups",
        "local_grid_locks": "BuildLocalTD[idx]",
        "explicit_gate_diagnostics": "solve_gate_diagnostics.json",
        "publication_gate": "PUBLICATION_SOLVE_GATE_FAILED",
        "cdr_compile_off": "STORAGE_CDR_MODULES_COMPILED = false",
        "raw_pstart_reset": "Gurobi.GRBreset",
        "raw_pstart_array": "Gurobi.GRBsetdblattrarray",
        "raw_pstart_list": "Gurobi.GRBsetdblattrlist",
        "raw_pstart_column_map": "Gurobi.c_column",
        "raw_pstart_not_serialized": ":cleanup_raw_pstart_serialized => [false]",
        "optional_diagnostic_cleanup_pstart": "diagnostic_primal_simplex_raw_pstart_sparse_face_selection",
    }
    for label, token in required_model_tokens.items():
        add(f"model:{label}", token in model, token)

    forbidden_tokens = {
        "crossover_basis_attribute_write": '"CrossoverBasis",',
        "price_basis": "price_basis",
        "capture_simplex_basis": "capture_simplex_basis",
        "restore_simplex_basis": "restore_simplex_basis!",
        "variable_basis_status": "VariableBasisStatus",
        "constraint_basis_status": "ConstraintBasisStatus",
        "dual_start_attribute_write": '"DStart",',
        "set_start_value": "set_start_value(",
        "old_cleanup_profile": "two_stage_physical_cleanup",
        "old_objbound_tolerance": "stage1_objective_bound_gap_tolerance_usd",
    }
    combined = "\n".join([model, runner, batch])
    for label, token in forbidden_tokens.items():
        add(f"forbidden_absent:{label}", token not in combined, token)

    add("runner_hard_disables_cdr", all(tok in runner for tok in ["allow_nbccs = false", "allow_daccs = false", "allow_beccs = false"]), "runner arguments")
    add("batch_fresh_process_attempts", "subprocess.Popen" in batch and "fresh_julia_process_per_attempt" in model, "fresh model per route")
    add("batch_no_stage1_primal_diagnostic", "primal_simplex_diagnostic" not in batch, "stage-1 primal simplex remains diagnostic only")
    add("bounded_stage1_route_tree", all(tok in batch for tok in ["stage1_uncertified_try_next_solver_route", "deterministic_concurrent", "dual_simplex"]), "official fallback changes only the stage-1 solver algorithm")
    add("stage1_official_primary", all(tok in batch for tok in ['"scaled_barrier", "__stage1_official"', '"stage1_official_release"']) and 'cleanup_profile::String="stage1_official_release"' in runner, "formal route publishes the certified stage-1 solution")
    add("cleanup_absent_from_official_fallback", "cleanup_fallbacks" not in batch and "retry_cleanup_for_certified_stage1" not in batch, "cleanup algorithms cannot replace or reject the official stage-1 result")
    add("raw_pstart_only_ephemeral", all(tok in combined for tok in ["cleanup_raw_pstart_serialized", "ephemeral_raw_gurobi_pstart_no_basis_not_serialized"]) and 'open("PStart' not in combined, "no PStart persistence")

    add("source_load_probe_present", SOURCE_LOAD.exists() and all(tok in SOURCE_LOAD.read_text(encoding="utf-8") for tok in ["include(model_file)", "isdefined(Main, :run_model)"]), "production source is actually included before solve")
    add("runtime_invokes_source_load", RUNTIME_BAT.exists() and "call CHECK_V17_SOURCE_LOAD.bat" in RUNTIME_BAT.read_text(encoding="utf-8"), "runtime validation cannot bypass production source lowering")
    add("grb_error_constant_top_level", model.index("const GRB_ERROR_DATA_NOT_AVAILABLE = 10005") < model.index("function run_model"), "no local const declaration")

    registry = pd.read_csv(REGISTRY)
    add("figure_registry_22", len(registry) == 22, len(registry))
    add("six_main_figures", int((registry["kind"].astype(str).str.lower() == "main").sum()) == 6, "main figures")
    add("figure_ids_unique", registry["figure_id"].nunique() == len(registry), registry["figure_id"].tolist())

    observed = pd.read_csv(ROOT / "data" / "processed" / "existing_new_storage_allocated_to_model_zones_2025.csv")
    add("legacy_32_zones", len(observed) == 32 and observed["model_zone"].nunique() == 32, {"rows": len(observed), "zones": observed["model_zone"].nunique()})
    add("legacy_power_closure", abs(observed["existing_new_storage_power_mw"].sum() - expected_storage_power_mw()) <= 1.0e-5, observed["existing_new_storage_power_mw"].sum())
    add("legacy_energy_closure", abs(observed["existing_new_storage_energy_mwh"].sum() - expected_storage_energy_mwh()) <= 1.0e-4, observed["existing_new_storage_energy_mwh"].sum())

    frame = pd.DataFrame(rows)
    hard = frame[frame["severity"].eq("error")]
    summary = {
        "version": "V17",
        "hard_checks": len(hard),
        "hard_passed": int(hard["pass"].sum()),
        "hard_all_pass": bool(len(hard) and hard["pass"].all()),
        "official_scenario_count": len(official),
        "python_file_count": len(pyfiles),
    }
    frame.to_csv(AUD / "V17_STATIC_RELEASE_AUDIT.csv", index=False)
    (AUD / "V17_STATIC_RELEASE_AUDIT.json").write_text(
        json.dumps({"summary": summary, "checks": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["hard_all_pass"]:
        print(frame[(frame["severity"] == "error") & ~frame["pass"]].to_string(index=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
