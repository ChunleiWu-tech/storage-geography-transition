#!/usr/bin/env python3
"""Fail-fast publication gate for V17T5 postprocessing.

Only solver-certified Stage-1 economic optima are accepted. Gross unit/timepoint
flows remain degeneracy-sensitive and are checked for explicit restrictions, but
are never used by the confirmatory V17T5 figures.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable

import pandas as pd

from v17t5_paths import AUDIT_DIR, MASTER, PROJECT_ROOT

TRUE = {"true", "1", "yes", "y"}
EXPECTED_NUMERICAL = (
    "V17_solver_certified_stage1_official_release_degeneracy_disclosure_"
    "cleanup_diagnostic_nonblocking_json_safe"
)
EXPECTED_CLEANUP = (
    "V17_stage1_official_release_optional_sparse_face_diagnostic_cleanup_nonblocking"
)
EXPECTED_SCENARIO_COUNT = 16
EXPECTED_REPRESENTATIVE_TIMEPOINTS = 504
EXPECTED_OPERATIONAL_PERIODS = 7
EXPECTED_STOCK_ANCHOR_PERIODS = 1

# Files needed either by the final tables/figures or by the publication audit.
REQUIRED = [
    "solve_status.csv",
    "scenario_config.json",
    "legacy_storage_allocation_audit.csv",
    "BuildGen.csv",
    "BuildStorageEnergy.csv",
    "BuildTx.csv",
    "electricity_cost.csv",
    "vre_curtailment_annual.csv",
    "physical_audit_summary.csv",
    "planning_reserve_coverage_audit.csv",
    "planning_reserve_margin_audit.csv",
    "planning_reserve_all_timepoints_screening.csv",
    "power_balance_closure_audit.csv",
    "carbon_cap_compliance_audit.csv",
    "independent_carbon_reconstruction_audit.csv",
    "time_weight_audit.csv",
    "RESULT_INTERPRETATION_POLICY.csv",
    # These are not used to make confirmatory figures, but their row-level
    # restriction labels must survive export.
    "storage_operation_audit.csv",
    "dispatch.csv",
    "DispatchTx.csv",
]

ACCEPTED_PROOF_SOURCES = {
    "gurobi_barrier_optimal_status_barconvtol_no_crossover",
    "gurobi_zero_iteration_optimal_under_barrier_configuration",
    "gurobi_deterministic_concurrent_optimal_status",
    "gurobi_dual_simplex_optimal_status",
    "gurobi_hard_deterministic_concurrent_simplex_optimal_status",
    "gurobi_hard_primal_simplex_optimal_status",
    "gurobi_hard_homogeneous_barrier_crossover_optimal_status",
    "gurobi_hard_homogeneous_barrier_no_crossover_optimal_status",
}


def truth(value: object) -> bool:
    return str(value).strip().lower() in TRUE


def number(value: object, default: float = float("nan")) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def select(master: pd.DataFrame, setname: str) -> pd.DataFrame:
    required = {"scenario", "v17_official_unique", "legacy_story_set"}
    missing = required.difference(master.columns)
    if missing:
        raise ValueError(f"Scenario master missing columns: {sorted(missing)}")
    mask = master["v17_official_unique"].astype(str).str.lower().isin(TRUE)
    if setname == "spatial_legacy_core":
        mask &= master["legacy_story_set"].eq("spatial_legacy_core")
    elif setname == "spatial_legacy_robustness":
        mask &= master["legacy_story_set"].eq("spatial_legacy_robustness")
    elif setname != "spatial_legacy_full":
        raise ValueError(setname)
    return master.loc[mask].copy()


def read_single(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    frame = pd.read_csv(path)
    if len(frame) != 1:
        return {}
    return frame.iloc[0].to_dict()


def require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = set(columns).difference(frame.columns)
    if missing:
        raise ValueError(f"{label} missing columns: {sorted(missing)}")


def batch_summary_gate(selected: pd.DataFrame) -> tuple[bool, str]:
    path = PROJECT_ROOT / "storage_runner" / "storage_batch_run_summary.csv"
    if not path.is_file():
        return False, "missing storage_batch_run_summary.csv"
    try:
        summary = pd.read_csv(path)
        require_columns(
            summary,
            [
                "scenario",
                "publication_strict_success",
                "stage1_termination_status",
                "publication_solution_source",
                "result_tier",
            ],
            path.name,
        )
    except Exception as exc:  # deterministic failure message in audit
        return False, str(exc)

    expected = selected["scenario"].astype(str).tolist()
    actual = summary["scenario"].astype(str).tolist()
    if len(actual) != len(set(actual)):
        return False, "duplicate scenarios in batch summary"
    if set(actual) != set(expected):
        return False, "batch summary scenario set mismatch"
    rows = summary.set_index("scenario").loc[expected]
    ok = (
        rows["publication_strict_success"].map(truth).all()
        and rows["stage1_termination_status"].eq("OPTIMAL").all()
        and rows["publication_solution_source"].eq(
            "stage1_solver_certified_economic_optimum"
        ).all()
        and rows["result_tier"].astype(str).str.startswith("official_stage1_economic_optimum").all()
    )
    return bool(ok), "" if ok else "batch summary contains a non-release row"


def policy_gate(directory: Path) -> tuple[bool, str]:
    path = directory / "RESULT_INTERPRETATION_POLICY.csv"
    if not path.is_file():
        return False, "missing interpretation policy"
    try:
        policy = pd.read_csv(path)
        require_columns(
            policy,
            [
                "output_family",
                "release_status",
                "degeneracy_sensitive",
                "operational_mechanism_interpretation_allowed",
                "allowed_use",
                "prohibited_use",
            ],
            path.name,
        )
    except Exception as exc:
        return False, str(exc)

    needed = {
        "investment_capacity_policy_annual_aggregates",
        "gross_dispatch_and_unit_timepoint_flows",
        "directional_transmission_and_reserve_flows",
        "storage_charge_discharge_components",
        "net_balances_and_accounting_closures",
    }
    if set(policy["output_family"]) != needed:
        return False, "interpretation policy family set is not exact"
    if policy["output_family"].duplicated().any():
        return False, "duplicate interpretation policy family"

    restricted = policy[
        policy["output_family"].isin(
            {
                "gross_dispatch_and_unit_timepoint_flows",
                "directional_transmission_and_reserve_flows",
                "storage_charge_discharge_components",
            }
        )
    ]
    investment = policy[
        policy["output_family"].eq("investment_capacity_policy_annual_aggregates")
    ]
    net = policy[
        policy["output_family"].eq("net_balances_and_accounting_closures")
    ]
    ok = (
        len(restricted) == 3
        and restricted["degeneracy_sensitive"].map(truth).all()
        and (~restricted["operational_mechanism_interpretation_allowed"].map(truth)).all()
        and restricted["release_status"].eq("exported_with_restriction").all()
        and len(investment) == 1
        and not investment["degeneracy_sensitive"].map(truth).iloc[0]
        and investment["operational_mechanism_interpretation_allowed"].map(truth).iloc[0]
        and investment["release_status"].eq("official_stage1_economic_result").iloc[0]
        and len(net) == 1
        and not net["degeneracy_sensitive"].map(truth).iloc[0]
        and not net["operational_mechanism_interpretation_allowed"].map(truth).iloc[0]
        and net["release_status"].eq("official_accounting_evidence").iloc[0]
    )
    return bool(ok), "" if ok else "interpretation policy values are invalid"


def row_label_gate(directory: Path) -> tuple[bool, str]:
    required = {
        "ResultSource",
        "DegeneracySensitive",
        "OperationalMechanismInterpretationAllowed",
        "AllowedUse",
    }
    for name in ["dispatch.csv", "DispatchTx.csv", "storage_operation_audit.csv"]:
        path = directory / name
        if not path.is_file():
            return False, f"missing {name}"
        row_count = 0
        try:
            for chunk in pd.read_csv(path, chunksize=100_000):
                row_count += len(chunk)
                if not required.issubset(chunk.columns):
                    return False, f"{name} missing restriction columns"
                if len(chunk):
                    if not chunk["ResultSource"].eq(
                        "stage1_solver_certified_economic_optimum"
                    ).all():
                        return False, f"{name} contains a non-official source"
                    if not chunk["DegeneracySensitive"].map(truth).all():
                        return False, f"{name} contains an unlabelled gross-flow row"
                    if chunk["OperationalMechanismInterpretationAllowed"].map(truth).any():
                        return False, f"{name} permits mechanism interpretation"
            if row_count == 0 and name != "DispatchTx.csv":
                return False, f"{name} is unexpectedly empty"
        except Exception as exc:
            return False, f"{name}: {exc}"
    return True, ""


def all_true_column(path: Path, column: str, *, hard_only: bool = False) -> tuple[bool, str]:
    try:
        frame = pd.read_csv(path)
        require_columns(frame, [column], path.name)
        if hard_only:
            require_columns(frame, ["hard_gate"], path.name)
            frame = frame[frame["hard_gate"].map(truth)]
        if frame.empty:
            return False, f"{path.name} has no audited rows"
        ok = frame[column].map(truth).all()
        return bool(ok), "" if ok else f"{path.name}::{column} contains false"
    except Exception as exc:
        return False, str(exc)


def stage1_release_gate(status: dict[str, object]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    checks = {
        "stage1 status": status.get("stage1_termination_status") == "OPTIMAL",
        "stage1 primal": status.get("stage1_primal_status") == "FEASIBLE_POINT",
        "stage1 dual": status.get("stage1_dual_status") == "FEASIBLE_POINT",
        "stage1 values": truth(status.get("stage1_has_values")),
        "native certificate": truth(status.get("stage1_native_solver_certificate_pass")),
        "strict certificate grade": status.get("stage1_certificate_grade") == "strict_solver_native",
        "accepted native proof source": status.get("stage1_economic_optimality_proof_source")
        in ACCEPTED_PROOF_SOURCES,
        "economic optimality": truth(status.get("stage1_economic_optimality_gate_pass")),
        "official route selected": truth(status.get("stage1_official_release_selected")),
        "official route passed": truth(status.get("stage1_official_release_pass")),
        "publication source": status.get("publication_solution_source")
        == "stage1_solver_certified_economic_optimum",
        "requested profile": status.get("requested_cleanup_profile") == "stage1_official_release",
        "resolved profile": status.get("cleanup_profile") == "stage1_official_release",
        "successful route": status.get("successful_cleanup_route") == "stage1_official_release",
        "cleanup nonblocking": truth(status.get("cleanup_diagnostic_nonblocking")),
        "cleanup not attempted": not truth(status.get("cleanup_diagnostic_attempted")),
        "gross flow sensitive": truth(status.get("gross_dispatch_degeneracy_sensitive")),
        "gross mechanism prohibited": not truth(
            status.get("gross_dispatch_operational_interpretation_allowed")
        ),
        "investment outputs eligible": truth(
            status.get("investment_capacity_policy_outputs_release_eligible")
        ),
        "release gate": truth(status.get("solve_gate_pass")),
        "strict physical audits": truth(status.get("strict_physical_audit_pass")),
        "complete export": truth(status.get("result_export_complete"))
        and truth(status.get("strict_export_pass")),
        "official result tier": status.get("audit_export_result_tier")
        == "official_stage1_economic_optimum",
        "numerical version": status.get("numerical_stability_version") == EXPECTED_NUMERICAL,
        "cleanup policy version": status.get("cleanup_strategy_version") == EXPECTED_CLEANUP,
        "pure LP": truth(status.get("model_is_pure_lp"))
        and number(status.get("model_binary_variable_count")) == 0
        and number(status.get("model_integer_variable_count")) == 0,
        "no CDR modules": truth(status.get("cdr_module_exclusion_gate_pass")),
        "representative timepoints": number(status.get("representative_timepoint_count"))
        == EXPECTED_REPRESENTATIVE_TIMEPOINTS,
        "operational periods": number(status.get("operational_period_count"))
        == EXPECTED_OPERATIONAL_PERIODS,
        "stock anchor periods": number(status.get("stock_anchor_period_count"))
        == EXPECTED_STOCK_ANCHOR_PERIODS,
        "no long-duration claim": not truth(status.get("storage_long_duration_claim_supported")),
        "planning reserve coverage": truth(status.get("planning_reserve_coverage_pass")),
        "legacy allocation audit": truth(status.get("legacy_allocation_audit_pass")),
        "primal feasibility": truth(status.get("primal_feasibility_gate_pass")),
    }
    for label, passed in checks.items():
        if not passed:
            failures.append(label)
    if not math.isfinite(number(status.get("stage1_economic_optimum"))):
        failures.append("finite stage1 economic optimum")
    return not failures, failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs-dir", default=str(PROJECT_ROOT / "outputs"))
    parser.add_argument(
        "--scenario-set",
        default="spatial_legacy_full",
        choices=["spatial_legacy_full", "spatial_legacy_core", "spatial_legacy_robustness"],
    )
    args = parser.parse_args()

    outputs = Path(args.outputs_dir).resolve()
    master = pd.read_csv(MASTER)
    selected = select(master, args.scenario_set)
    if args.scenario_set == "spatial_legacy_full" and len(selected) != EXPECTED_SCENARIO_COUNT:
        raise SystemExit(
            f"Expected {EXPECTED_SCENARIO_COUNT} official scenarios, found {len(selected)}"
        )

    batch_ok, batch_reason = batch_summary_gate(selected)
    records: list[dict[str, object]] = []

    for _, meta in selected.iterrows():
        scenario = str(meta["scenario"])
        directory = outputs / f"{scenario}__main"
        missing = [name for name in REQUIRED if not (directory / name).is_file()]
        status = read_single(directory / "solve_status.csv")
        stage_ok, stage_failures = stage1_release_gate(status)
        policy_ok, policy_reason = policy_gate(directory)
        labels_ok, labels_reason = row_label_gate(directory)
        physical_ok, physical_reason = all_true_column(
            directory / "physical_audit_summary.csv", "pass", hard_only=True
        )
        legacy_ok, legacy_reason = all_true_column(
            directory / "legacy_storage_allocation_audit.csv",
            "LegacyAllocationAuditPass",
        )
        reserve_ok, reserve_reason = all_true_column(
            directory / "planning_reserve_coverage_audit.csv", "CoveragePass"
        )

        expected_cap = 2.0e8 * number(meta.get("carbon_cap_multiplier"), 1.0)
        metadata_ok = (
            str(status.get("legacy_allocation_mode", ""))
            == str(meta["legacy_allocation_mode"])
            and abs(number(status.get("final_carbon_cap_tco2_per_yr")) - expected_cap)
            <= 1e-3
            and not truth(status.get("allow_nbccs"))
            and not truth(status.get("allow_daccs"))
            and not truth(status.get("allow_beccs"))
            and truth(status.get("official_cdr_disabled"))
        )

        passed = bool(
            batch_ok
            and directory.is_dir()
            and not missing
            and stage_ok
            and policy_ok
            and labels_ok
            and physical_ok
            and legacy_ok
            and reserve_ok
            and metadata_ok
        )
        records.append(
            {
                "scenario": scenario,
                "pass": passed,
                "batch_summary_gate_pass": batch_ok,
                "batch_summary_failure": batch_reason,
                "output_dir_exists": directory.is_dir(),
                "missing_files": ";".join(missing),
                "stage1_release_gate_pass": stage_ok,
                "stage1_failures": ";".join(stage_failures),
                "interpretation_policy_gate_pass": policy_ok,
                "interpretation_policy_failure": policy_reason,
                "row_label_gate_pass": labels_ok,
                "row_label_failure": labels_reason,
                "physical_hard_gate_pass": physical_ok,
                "physical_hard_gate_failure": physical_reason,
                "legacy_allocation_gate_pass": legacy_ok,
                "legacy_allocation_gate_failure": legacy_reason,
                "planning_reserve_coverage_gate_pass": reserve_ok,
                "planning_reserve_coverage_gate_failure": reserve_reason,
                "scenario_metadata_gate_pass": metadata_ok,
                "proof_source": status.get("stage1_economic_optimality_proof_source", ""),
                "diagnostic_degeneracy_review_pass": status.get(
                    "diagnostic_degeneracy_review_pass", ""
                ),
                "diagnostic_degeneracy_review_is_nonblocking": True,
            }
        )

    audit = pd.DataFrame(records)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_DIR / f"preflight_{args.scenario_set}.csv", index=False)
    summary = {
        "version": "V17T5R6R8R5",
        "release_source": "solver-certified stage-1 economic optimum",
        "confirmatory_figure_scope": (
            "investment, capacity, cost, annual aggregate and audited closure evidence only"
        ),
        "gross_flow_use": "restriction audit only; excluded from confirmatory figures",
        "scenario_set": args.scenario_set,
        "expected": len(audit),
        "passed": int(audit["pass"].sum()) if len(audit) else 0,
        "all_pass": bool(len(audit) and audit["pass"].all()),
    }
    (AUDIT_DIR / f"preflight_{args.scenario_set}.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary["all_pass"]:
        print(audit.loc[~audit["pass"]].to_string(index=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
