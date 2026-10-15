#!/usr/bin/env python3
"""Fail-fast V17 gate for publication postprocessing.

The formal release source is the solver-certified stage-1 economic optimum.
Stage-2 sparse-face cleanup is optional, diagnostic, and non-blocking. Gross
unit/timepoint dispatch and directional flows are exported only with explicit
degeneracy restrictions and cannot support operating-mechanism claims.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "storage_runner" / "scenarios_storage_master.csv"
TRUE = {"true", "1", "yes", "y"}
EXPECTED_NUMERICAL = "V17_solver_certified_stage1_official_release_degeneracy_disclosure_cleanup_diagnostic_nonblocking_json_safe"
EXPECTED_CLEANUP = "V17_stage1_official_release_optional_sparse_face_diagnostic_cleanup_nonblocking"
REQUIRED = [
    "solve_status.csv", "legacy_storage_allocation_audit.csv", "BuildGen.csv",
    "BuildStorageEnergy.csv", "BuildTx.csv", "storage_operation_audit.csv",
    "dispatch.csv", "DispatchTx.csv", "load_balance.csv", "electricity_cost.csv",
    "vre_curtailment_annual.csv", "physical_audit_summary.csv",
    "RESULT_INTERPRETATION_POLICY.csv",
]


def truth(v: object) -> bool:
    return str(v).strip().lower() in TRUE


def number(v: object, default: float = float("nan")) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def select(df: pd.DataFrame, setname: str) -> pd.DataFrame:
    mask = df.v17_official_unique.astype(str).str.lower().isin(TRUE)
    if setname == "spatial_legacy_core":
        mask &= df.legacy_story_set.eq("spatial_legacy_core")
    elif setname == "spatial_legacy_robustness":
        mask &= df.legacy_story_set.eq("spatial_legacy_robustness")
    return df[mask]


def read_single(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    df = pd.read_csv(path)
    if len(df) != 1:
        return {}
    return df.iloc[0].to_dict()


def policy_gate(directory: Path) -> tuple[bool, str]:
    path = directory / "RESULT_INTERPRETATION_POLICY.csv"
    if not path.is_file():
        return False, "missing interpretation policy"
    policy = pd.read_csv(path)
    needed = {
        "investment_capacity_policy_annual_aggregates",
        "gross_dispatch_and_unit_timepoint_flows",
        "directional_transmission_and_reserve_flows",
        "storage_charge_discharge_components",
        "net_balances_and_accounting_closures",
    }
    if not needed.issubset(set(policy.get("output_family", []))):
        return False, "incomplete interpretation policy families"
    restricted = policy[policy["output_family"].isin({
        "gross_dispatch_and_unit_timepoint_flows",
        "directional_transmission_and_reserve_flows",
        "storage_charge_discharge_components",
    })]
    ok = (
        len(restricted) == 3
        and restricted["degeneracy_sensitive"].map(truth).all()
        and (~restricted["operational_mechanism_interpretation_allowed"].map(truth)).all()
        and restricted["release_status"].eq("exported_with_restriction").all()
    )
    return bool(ok), "" if ok else "gross-flow restriction policy invalid"


def row_label_gate(directory: Path) -> tuple[bool, str]:
    for name in ["dispatch.csv", "DispatchTx.csv", "storage_operation_audit.csv"]:
        path = directory / name
        if not path.is_file():
            return False, f"missing {name}"
        df = pd.read_csv(path, nrows=20)
        cols = {"ResultSource", "DegeneracySensitive", "OperationalMechanismInterpretationAllowed", "AllowedUse"}
        if not cols.issubset(df.columns):
            return False, f"{name} missing restriction columns"
        if len(df):
            if not df["ResultSource"].eq("stage1_solver_certified_economic_optimum").all():
                return False, f"{name} source is not official stage 1"
            if not df["DegeneracySensitive"].map(truth).all():
                return False, f"{name} is not marked degeneracy-sensitive"
            if df["OperationalMechanismInterpretationAllowed"].map(truth).any():
                return False, f"{name} incorrectly permits mechanism interpretation"
    return True, ""


# External certificate comparisons are non-blocking diagnostics.
def stage1_release_gate(s: dict[str, object]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    checks = {
        "stage1 status": s.get("stage1_termination_status") == "OPTIMAL",
        "stage1 primal": s.get("stage1_primal_status") == "FEASIBLE_POINT",
        "stage1 dual": s.get("stage1_dual_status") == "FEASIBLE_POINT",
        "stage1 values": truth(s.get("stage1_has_values")),
        "native certificate": truth(s.get("stage1_native_solver_certificate_pass")),
        "strict certificate grade": s.get("stage1_certificate_grade") == "strict_solver_native",
        "accepted native proof source": s.get("stage1_economic_optimality_proof_source") in {
            "gurobi_barrier_optimal_status_barconvtol_no_crossover",
            "gurobi_zero_iteration_optimal_under_barrier_configuration",
            "gurobi_deterministic_concurrent_optimal_status",
            "gurobi_dual_simplex_optimal_status",
            "gurobi_hard_deterministic_concurrent_simplex_optimal_status",
            "gurobi_hard_primal_simplex_optimal_status",
            "gurobi_hard_homogeneous_barrier_crossover_optimal_status",
            "gurobi_hard_homogeneous_barrier_no_crossover_optimal_status",
        },
        "economic optimality": truth(s.get("stage1_economic_optimality_gate_pass")),
        "official route selected": truth(s.get("stage1_official_release_selected")),
        "official route passed": truth(s.get("stage1_official_release_pass")),
        "publication source": s.get("publication_solution_source") == "stage1_solver_certified_economic_optimum",
        "requested profile": s.get("requested_cleanup_profile") == "stage1_official_release",
        "resolved profile": s.get("cleanup_profile") == "stage1_official_release",
        "successful route": s.get("successful_cleanup_route") == "stage1_official_release",
        "cleanup nonblocking": truth(s.get("cleanup_diagnostic_nonblocking")),
        "cleanup not attempted in official run": not truth(s.get("cleanup_diagnostic_attempted")),
        "gross flow sensitive": truth(s.get("gross_dispatch_degeneracy_sensitive")),
        "gross mechanism prohibited": not truth(s.get("gross_dispatch_operational_interpretation_allowed")),
        "release gate": truth(s.get("solve_gate_pass")),
        "strict physical audits": truth(s.get("strict_physical_audit_pass")),
        "complete export": truth(s.get("result_export_complete")) and truth(s.get("strict_export_pass")),
        "official result tier": s.get("audit_export_result_tier") == "official_stage1_economic_optimum",
        "numerical version": s.get("numerical_stability_version") == EXPECTED_NUMERICAL,
        "cleanup policy version": s.get("cleanup_strategy_version") == EXPECTED_CLEANUP,
        "pure LP": truth(s.get("model_is_pure_lp")) and number(s.get("model_binary_variable_count")) == 0 and number(s.get("model_integer_variable_count")) == 0,
        "no CDR modules": truth(s.get("cdr_module_exclusion_gate_pass")),
    }
    for label, passed in checks.items():
        if not passed:
            failures.append(label)
    if not math.isfinite(number(s.get("stage1_economic_optimum"))):
        failures.append("finite stage1 economic optimum")
    return not failures, failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs-dir", default=str(ROOT / "outputs"))
    parser.add_argument("--scenario-set", default="spatial_legacy_full", choices=[
        "spatial_legacy_full", "spatial_legacy_core", "spatial_legacy_robustness"
    ])
    args = parser.parse_args()
    outputs = Path(args.outputs_dir)
    master = pd.read_csv(MASTER)
    records: list[dict[str, object]] = []

    for _, meta in select(master, args.scenario_set).iterrows():
        scenario = str(meta.scenario)
        directory = outputs / f"{scenario}__main"
        missing = [f for f in REQUIRED if not (directory / f).is_file()]
        status = read_single(directory / "solve_status.csv")
        stage_ok, stage_fail = stage1_release_gate(status)
        policy_ok, policy_reason = policy_gate(directory)
        labels_ok, labels_reason = row_label_gate(directory)
        expected_cap = 2.0e8 * number(meta.get("carbon_cap_multiplier"), 1.0)
        metadata_ok = (
            str(status.get("legacy_allocation_mode", "")) == str(meta.legacy_allocation_mode)
            and abs(number(status.get("final_carbon_cap_tco2_per_yr")) - expected_cap) <= 1e-3
            and not truth(status.get("allow_nbccs"))
            and not truth(status.get("allow_daccs"))
            and not truth(status.get("allow_beccs"))
            and truth(status.get("official_cdr_disabled"))
        )
        passed = bool(directory.is_dir() and not missing and stage_ok and policy_ok and labels_ok and metadata_ok)
        records.append({
            "scenario": scenario,
            "pass": passed,
            "output_dir_exists": directory.is_dir(),
            "missing_files": ";".join(missing),
            "stage1_release_gate_pass": stage_ok,
            "stage1_failures": ";".join(stage_fail),
            "interpretation_policy_gate_pass": policy_ok,
            "interpretation_policy_failure": policy_reason,
            "row_label_gate_pass": labels_ok,
            "row_label_failure": labels_reason,
            "scenario_metadata_gate_pass": metadata_ok,
            "diagnostic_degeneracy_review_pass": status.get("diagnostic_degeneracy_review_pass", ""),
            "diagnostic_degeneracy_review_is_nonblocking": True,
        })

    audit = pd.DataFrame(records)
    destination = ROOT / "postprocess_outputs" / "audits"
    destination.mkdir(parents=True, exist_ok=True)
    audit.to_csv(destination / f"preflight_{args.scenario_set}.csv", index=False)
    summary = {
        "version": "V17",
        "release_source": "solver-certified stage-1 economic optimum",
        "stage2_cleanup_role": "optional non-blocking sparse-face diagnostic",
        "gross_dispatch_interpretation": "degeneracy-sensitive; operational-mechanism interpretation prohibited",
        "scenario_set": args.scenario_set,
        "expected": len(audit),
        "passed": int(audit["pass"].sum()) if len(audit) else 0,
        "all_pass": bool(len(audit) and audit["pass"].all()),
    }
    (destination / f"preflight_{args.scenario_set}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary["all_pass"]:
        print(audit[~audit["pass"]].to_string(index=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
