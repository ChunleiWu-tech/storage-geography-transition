#!/usr/bin/env python3
"""Recertify one R24P2 barrier solution with an audited relative complementarity gate."""
from __future__ import annotations

from pathlib import Path
import argparse
import csv
import json
import math
import os
import shutil
import time
from typing import Any

import run_hf18p2_quality_recovery_two_parallel as core


TARGET = "TY2033_FULL8760_OBSERVED"
PROTECTED_SCENARIOS = (
    "TY2033_FULL8760_OPTIMAL",
    "TY2033_FULL8760_LDES_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL",
)
ALL_SCENARIOS = (
    "TY2033_FULL8760_OBSERVED",
    "TY2033_FULL8760_OPTIMAL",
    "TY2033_FULL8760_LDES_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL",
)
VERSION = "V17T2R6R24P3_HF18P2_scale_aware_complementarity_postsolve_recovery"
BAR_CONV_REL_TOL = 1.0e-8
R24P2_ABSOLUTE_COMPL_VIO_TOL = 1.0e-4
RECOVERY_ATTEMPTS = core.CENTRAL / "_r24p3_postsolve_attempts"
SUMMARY_JSON = core.CENTRAL / "V17T2R6R24P3_HF18P2_POSTSOLVE_RECOVERY_summary.json"
SUMMARY_CSV = core.CENTRAL / "V17T2R6R24P3_HF18P2_POSTSOLVE_RECOVERY_summary.csv"
COMBINED_JSON = core.CENTRAL / "V17T2R6R24P3_HF18P2_COMBINED_ALL4_final_summary.json"
COMBINED_CSV = core.CENTRAL / "V17T2R6R24P3_HF18P2_COMBINED_ALL4_final_summary.csv"


def truth(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "1.0", "yes", "y", "t"}


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_one_csv(path: Path, row: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def inspect_exact_r24p2_failure(path: Path) -> tuple[dict[str, str], dict[str, Any], dict[str, Any], dict[str, Any]]:
    required = (
        "solve_status.csv",
        "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE.json",
        "HF18P2_QUALITY_ATTRIBUTION.json",
        "hf18p2_core_physical_quality_audit.csv",
        "hf18p2_robustness_distance_by_zone.csv",
        "hf18_fixed_portfolio_family_audit.csv",
        "hf18_fixed_portfolio_lineage.json",
    )
    missing = [name for name in required if not (path / name).is_file()]
    if missing:
        raise ValueError(f"missing R24P2 files: {missing}")
    rows = read_rows(path / "solve_status.csv")
    if len(rows) != 1:
        raise ValueError(f"solve_status row count={len(rows)} expected=1")
    status = rows[0]
    cert = json.loads((path / "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE.json").read_text(encoding="utf-8"))
    quality = json.loads((path / "HF18P2_QUALITY_ATTRIBUTION.json").read_text(encoding="utf-8"))
    lineage = json.loads((path / "hf18_fixed_portfolio_lineage.json").read_text(encoding="utf-8"))

    exact = {
        "scenario": TARGET,
        "stage1_termination_status": "OPTIMAL",
        "stage1_primal_status": "FEASIBLE_POINT",
        "stage1_dual_status": "FEASIBLE_POINT",
        "solver_profile": core.PROFILE,
        "classification": "CERTIFICATE_FAILED",
        "source_scenario": core.SOURCE_MAP[TARGET],
    }
    for key, expected in exact.items():
        if status.get(key) != expected:
            raise ValueError(f"{key}={status.get(key)!r} expected={expected!r}")
    for key in (
        "stage1_has_values", "route_gate_pass", "source_lineage_gate_pass",
        "objective_gate_pass", "maxvio_decomposition_gate_pass",
        "scaled_residual_gate_pass", "core_physical_quality_gate_pass",
        "physical_quality_gate_pass", "pure_lp",
    ):
        if not truth(status.get(key)):
            raise ValueError(f"required pre-existing gate is false: {key}")
    for key in (
        "robustness_distance_certificate_pass", "native_quality_gate_pass",
        "componentwise_native_quality_gate_pass",
    ):
        if truth(status.get(key)):
            raise ValueError(f"expected the old absolute-complementarity gate to be false: {key}")
    if number(status.get("gurobi_status")) != 2.0:
        raise ValueError(f"gurobi_status={status.get('gurobi_status')} expected=2")
    if number(status.get("solver_threads")) != 10.0:
        raise ValueError(f"solver_threads={status.get('solver_threads')} expected=10")
    if number(status.get("primal_dual_relative_gap")) > 1.0e-5:
        raise ValueError("primal-dual relative gap exceeds 1e-5")
    if number(status.get("objective_readback_error_mw")) > 1.0e-4:
        raise ValueError("objective readback error exceeds 1e-4 MW")

    thresholds = quality.get("thresholds", {})
    components = quality.get("unscaled_components", {})
    scaled = quality.get("scaled_residuals", {})
    bound_vio = number(components.get("BoundVio"))
    constr_vio = number(components.get("ConstrVio"))
    dual_vio = number(components.get("DualVio"))
    compl_vio = number(components.get("ComplVio"))
    max_vio = number(quality.get("max_vio"))
    objective = number(status.get("total_ideal_flexibility_robustness_distance_mw"))
    finite = (bound_vio, constr_vio, dual_vio, compl_vio, max_vio, objective)
    if not all(math.isfinite(value) for value in finite):
        raise ValueError("one or more required native quality values are non-finite")
    if bound_vio > number(thresholds.get("BoundVio")):
        raise ValueError("BoundVio exceeds unchanged R24P2 threshold")
    if constr_vio > number(thresholds.get("ConstrVio")):
        raise ValueError("ConstrVio exceeds unchanged R24P2 threshold")
    if dual_vio > number(thresholds.get("DualVio")):
        raise ValueError("DualVio exceeds unchanged R24P2 threshold")
    scaled_tol = number(thresholds.get("scaled_residual"))
    if number(scaled.get("ConstrSResidual")) > scaled_tol:
        raise ValueError("ConstrSResidual exceeds unchanged R24P2 threshold")
    if number(scaled.get("DualSResidual")) > scaled_tol:
        raise ValueError("DualSResidual exceeds unchanged R24P2 threshold")
    if compl_vio <= R24P2_ABSOLUTE_COMPL_VIO_TOL:
        raise ValueError("the attempt did not fail solely on the declared absolute ComplVio threshold")
    if quality.get("decomposed_max_vio_source") != "ComplVio":
        raise ValueError("MaxVio is not attributed to ComplVio")
    if abs(max_vio - compl_vio) > 1.0e-10 * max(1.0, abs(max_vio), abs(compl_vio)):
        raise ValueError("MaxVio does not numerically match ComplVio")

    scale = max(1.0, abs(objective))
    relative_complementarity = compl_vio / scale
    if relative_complementarity > BAR_CONV_REL_TOL:
        raise ValueError(
            f"relative complementarity={relative_complementarity} exceeds {BAR_CONV_REL_TOL}"
        )
    physical_rows = read_rows(path / "hf18p2_core_physical_quality_audit.csv")
    if len(physical_rows) != 8 or any(not truth(row.get("pass")) for row in physical_rows):
        raise ValueError("the eight original-unit physical audits are not all PASS")
    if not lineage.get("pass") or not lineage.get("robustness_distance_only"):
        raise ValueError("fixed-portfolio lineage is not strict robustness-distance-only")
    expected_source_sha = core.source_fingerprint(TARGET)
    if cert.get("source_manifest_sha256") != expected_source_sha:
        raise ValueError("strict target-year source fingerprint mismatch")
    if cert.get("scenario") != TARGET or quality.get("scenario") != TARGET:
        raise ValueError("scenario mismatch in R24P2 audit JSON")
    return status, cert, quality, {
        "objective_scale_mw": scale,
        "compl_vio_objective_units": compl_vio,
        "relative_complementarity": relative_complementarity,
        "relative_complementarity_tolerance": BAR_CONV_REL_TOL,
        "r24p2_absolute_complementarity_tolerance": R24P2_ABSOLUTE_COMPL_VIO_TOL,
    }


def choose_attempt(explicit: str | None) -> tuple[Path, tuple[dict[str, str], dict[str, Any], dict[str, Any], dict[str, Any]]]:
    if explicit:
        path = Path(explicit).resolve()
        path.relative_to(core.ROOT.resolve())
        return path, inspect_exact_r24p2_failure(path)
    parent = core.ATTEMPTS / TARGET
    candidates = sorted(
        (path for path in parent.glob("*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    failures: list[str] = []
    for path in candidates:
        try:
            return path, inspect_exact_r24p2_failure(path)
        except Exception as exc:
            failures.append(f"{path.name}: {exc}")
    raise RuntimeError(
        "No exact R24P2 single-threshold failure was found. Checked: " + "; ".join(failures[:8])
    )


def protected_record(scenario: str) -> dict[str, Any]:
    current = core.existing_certificate(scenario)
    if current is not None:
        return current
    return core.prior_success_record(scenario)


def recover(source: Path, parsed: tuple[dict[str, str], dict[str, Any], dict[str, Any], dict[str, Any]]) -> Path:
    status, cert, quality, metric = parsed
    token = time.strftime("%Y%m%d_%H%M%S")
    stage = RECOVERY_ATTEMPTS / TARGET / f"r24p3_scale_aware_complementarity__{token}"
    stage.parent.mkdir(parents=True, exist_ok=True)
    if stage.exists():
        raise RuntimeError(f"unique recovery path already exists: {stage}")
    shutil.copytree(source, stage)
    shutil.copy2(stage / "solve_status.csv", stage / "solve_status_r24p2_original_failed_gate.csv")
    shutil.copy2(
        stage / "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE.json",
        stage / "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE_R24P2_ORIGINAL_FAILED_GATE.json",
    )
    shutil.copy2(
        stage / "HF18P2_QUALITY_ATTRIBUTION.json",
        stage / "HF18P2_QUALITY_ATTRIBUTION_R24P2_ORIGINAL_FAILED_GATE.json",
    )

    recovered_status: dict[str, Any] = dict(status)
    recovered_status.update({
        "version": VERSION,
        "classification": "CERTIFIED_POSITIVE_ROBUSTNESS_GAP",
        "robustness_distance_certificate_pass": True,
        "native_quality_gate_pass": True,
        "componentwise_native_quality_gate_pass": True,
        "r24p2_original_native_quality_gate_pass": False,
        "r24p2_original_componentwise_native_quality_gate_pass": False,
        "r24p3_scale_aware_complementarity_gate_pass": True,
        "r24p3_compl_vio_objective_units": metric["compl_vio_objective_units"],
        "r24p3_objective_scale_mw": metric["objective_scale_mw"],
        "r24p3_relative_complementarity": metric["relative_complementarity"],
        "r24p3_relative_complementarity_tolerance": metric["relative_complementarity_tolerance"],
        "r24p3_postsolve_only": True,
        "r24p3_resolve_performed": False,
    })
    write_one_csv(stage / "solve_status.csv", recovered_status)

    recovered_quality = dict(quality)
    recovered_quality["version"] = VERSION
    recovered_quality["r24p2_original_gates"] = dict(quality.get("gates", {}))
    recovered_quality["gates"] = {
        **dict(quality.get("gates", {})),
        "componentwise_native_quality_gate_pass": True,
        "scale_aware_complementarity_gate_pass": True,
    }
    recovered_quality["scale_aware_complementarity"] = metric
    recovered_quality["interpretation"] = (
        "R24P3 preserves every raw R24P2 quality value. The only old failure was the "
        "unscaled interior-point complementarity product. It is normalized by the MW-valued "
        "robustness objective and gated at the unchanged 1e-8 BarConvTol, while all native "
        "feasibility, scaled residual, dual and eight original-unit physical gates remain mandatory."
    )
    (stage / "HF18P2_QUALITY_ATTRIBUTION.json").write_text(
        json.dumps(recovered_quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    recovered_cert = dict(cert)
    recovered_cert.update({
        "version": VERSION,
        "classification": "CERTIFIED_POSITIVE_ROBUSTNESS_GAP",
        "certificate_pass": True,
        "original_fixed_portfolio_feasible": False,
        "r24p3_postsolve_only": True,
        "r24p3_resolve_performed": False,
        "r24p2_original_certificate_pass": False,
        "scale_aware_complementarity": metric,
    })
    gates = dict(recovered_cert.get("gates", {}))
    recovered_cert["r24p2_original_gates"] = gates
    recovered_cert["gates"] = {
        **gates,
        "native_quality_gate_pass": True,
        "componentwise_native_quality_gate_pass": True,
        "scale_aware_complementarity_gate_pass": True,
    }
    (stage / "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE.json").write_text(
        json.dumps(recovered_cert, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    audit = {
        "version": VERSION,
        "status": "PASS",
        "scenario": TARGET,
        "source_failed_attempt": str(source.relative_to(core.ROOT)),
        "postsolve_only": True,
        "resolve_performed": False,
        "scientific_model_changed": False,
        "scientific_inputs_changed": False,
        "objective_or_constraint_changed": False,
        "chronology_changed": False,
        "raw_r24p2_artifacts_preserved": True,
        "metric": metric,
        "mandatory_evidence": {
            "gurobi_status_optimal": True,
            "primal_and_dual_feasible_point": True,
            "objective_gate_pass": True,
            "non_complementarity_native_components_pass": True,
            "scaled_primal_and_dual_residuals_pass": True,
            "eight_original_unit_physical_audits_pass": True,
            "source_lineage_gate_pass": True,
        },
        "official_definition_basis": {
            "quality_attributes": "https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/quality.html",
            "barrier_convergence": "https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter-BarConvTol",
        },
        "claim_boundary": (
            "positive robustness distance remains a quantified fixed-portfolio gap; it is not "
            "an original-portfolio feasibility PASS or an actual technology build"
        ),
    }
    (stage / "HF18P2_R24P3_POSTSOLVE_RECOVERY_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    reasons = core.validate_result(stage, TARGET, 0)
    if reasons:
        raise RuntimeError(f"R24P3 recovered result failed strict validation: {reasons}")
    core.fingerprint_output(stage, TARGET)
    destination = core.CENTRAL / f"{TARGET}__main"
    core.promote_preserving_previous(stage, destination, token)
    core.fingerprint_output(destination, TARGET)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", help="optional explicit R24P2 attempt directory")
    args = parser.parse_args()
    if int(os.environ.get("V17_SOLVER_THREADS", "10")) != 10:
        raise SystemExit("R24P3 provenance contract expects the original 10-thread R24P2 solve")
    core.TARGETS = (TARGET,)
    registry = core.read_registry()
    core.validate_sources(registry)
    for path in (core.CENTRAL, core.ATTEMPTS, core.SUPERSEDED, RECOVERY_ATTEMPTS):
        path.mkdir(parents=True, exist_ok=True)

    protected = [protected_record(scenario) for scenario in PROTECTED_SCENARIOS]
    protected_hashes = {
        record["scenario"]: core.tree_sha(core.ROOT / str(record["output"]))
        for record in protected
    }
    source, parsed = choose_attempt(args.attempt)
    destination = recover(source, parsed)
    recovered = core.existing_certificate(TARGET)
    if recovered is None:
        raise RuntimeError("promoted R24P3 result did not pass the unchanged strict output validator")
    recovered["certificate_origin"] = "V17T2R6R24P3_HF18P2_POSTSOLVE"
    for record in protected:
        after = core.tree_sha(core.ROOT / str(record["output"]))
        if after != protected_hashes[record["scenario"]]:
            raise RuntimeError(f"protected successful result changed: {record['scenario']}")

    one = {
        "version": VERSION,
        "status": "PASS",
        "scenario": TARGET,
        "source_attempt": str(source.relative_to(core.ROOT)),
        "promoted_output": str(destination.relative_to(core.ROOT)),
        "record": recovered,
    }
    SUMMARY_JSON.write_text(json.dumps(one, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core.write_csv(SUMMARY_CSV, [recovered])

    records_by_scenario = {record["scenario"]: record for record in protected + [recovered]}
    combined_records = [records_by_scenario[scenario] for scenario in ALL_SCENARIOS]
    combined = {
        "version": "V17T2R6R24P3_HF18P2_COMBINED_ALL4",
        "status": "PASS",
        "all_four_certificates_success": all(record["certificate_success"] for record in combined_records),
        "all_four_original_portfolios_feasible": all(record["original_fixed_portfolio_feasible"] for record in combined_records),
        "scientific_model_changed": False,
        "chronology_changed": False,
        "source_portfolios_changed": False,
        "protected_results_changed": False,
        "records": combined_records,
    }
    if not combined["all_four_certificates_success"]:
        raise RuntimeError("combined four-case strict certificate set is incomplete")
    core.write_csv(COMBINED_CSV, combined_records)
    COMBINED_JSON.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(one, ensure_ascii=False, indent=2), flush=True)
    print("V17T2R6R24P3 HF18P2: POSTSOLVE COMPLEMENTARITY RECOVERY PASS", flush=True)
    print("V17T2R6R24P3 HF18P2: COMBINED ALL FOUR CERTIFICATES COMPLETED", flush=True)


if __name__ == "__main__":
    main()
