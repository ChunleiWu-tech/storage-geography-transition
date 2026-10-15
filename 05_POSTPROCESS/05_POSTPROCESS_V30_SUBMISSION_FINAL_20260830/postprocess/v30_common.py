"""Strict, read-only source adapters for V30 publication post-processing."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

FULL8760_SCENARIOS = (
    "TY2033_FULL8760_OBSERVED",
    "TY2033_FULL8760_OPTIMAL",
    "TY2033_FULL8760_LDES_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL",
)
V20_LAYER_A_SCENARIOS = (
    "FC01_BASE_OBSERVED",
    "FC02_BASE_OPTIMAL",
    "FC03_ADAPTIVE_OBSERVED",
    "FC04_ADAPTIVE_OPTIMAL",
    "FC05_ADAPTIVE_TXFIXED_OBSERVED",
    "FC06_ADAPTIVE_TXFIXED_OPTIMAL",
    "FC07_EXPANDED_OBSERVED",
    "FC08_EXPANDED_OPTIMAL",
)
V20_LAYER_B_SCENARIOS = (
    "SL00_OBSERVED_ACTUAL",
    "SL01_OBSERVED_STANDARDIZED",
    "SL02_OPTIMAL_REALLOCATION",
    "SL03_NO_LEGACY",
    "SL04_RULE_LOAD",
    "SL05_RULE_VRE",
    "SL06_TX_FIXED_OBSERVED",
    "SL07_TX_FIXED_OPTIMAL",
    "SL08_PH_CONSERVATIVE_OBSERVED",
    "SL09_PH_CONSERVATIVE_OPTIMAL",
    "SL10_CARBON_TIGHT_OBSERVED",
    "SL11_CARBON_TIGHT_OPTIMAL",
    "SL12_COST_LOW_OBSERVED",
    "SL13_COST_LOW_OPTIMAL",
    "SL14_COST_HIGH_OBSERVED",
    "SL15_COST_HIGH_OPTIMAL",
)
V20_LAYER_C_SCENARIOS = ("V20EH01_OBSERVED", "V20EH02_OPTIMAL")


def truth(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "1.0", "yes", "y", "t", "pass", "passed"}


def number(value: Any, *, field: str = "value") -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is not numeric: {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} is non-finite: {value!r}")
    return result


def first_column(frame: pd.DataFrame, candidates: Iterable[str], *, required: bool = True) -> str | None:
    lower = {str(column).lower(): str(column) for column in frame.columns}
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    if required:
        raise KeyError(f"None of the required columns exist: {list(candidates)}; found={list(frame.columns)}")
    return None


def read_one_csv(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    if len(frame) != 1:
        raise ValueError(f"Expected exactly one row in {path}; found {len(frame)}")
    return frame.iloc[0].to_dict()


def strict_solver_status(row: dict[str, Any], label: str) -> None:
    exact = {
        "stage1_termination_status": "OPTIMAL",
        "stage1_primal_status": "FEASIBLE_POINT",
        "stage1_dual_status": "FEASIBLE_POINT",
    }
    for field, expected in exact.items():
        if str(row.get(field, "")) != expected:
            raise ValueError(f"{label}: {field}={row.get(field)!r}; expected {expected}")
    status_aliases = {"gurobi_status", "stage1_gurobi_status"}
    observed = [(str(key), value) for key, value in row.items() if str(key).strip().lower() in status_aliases]
    if not observed:
        raise ValueError(f"{label}: neither gurobi_status nor stage1_gurobi_status is present")
    for field, value in observed:
        if number(value, field=f"{label}.{field}") != 2:
            raise ValueError(f"{label}: {field}={value!r}; expected native OPTIMAL status 2")


def sha256(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def strict_v20_status(row: dict[str, Any], label: str, layer: str) -> None:
    """Re-apply the publication subset common to the upstream strict runners.

    This is intentionally stricter than merely trusting the promoted-directory
    name.  Layer-specific chronology claims are checked separately.
    """
    strict_solver_status(row, label)
    exact = {
        "termination_status": "OPTIMAL",
        "primal_status": "FEASIBLE_POINT",
        "dual_status": "FEASIBLE_POINT",
        "audit_export_result_tier": "official_stage1_economic_optimum",
        "publication_solution_source": "stage1_solver_certified_economic_optimum",
        "successful_cleanup_route": "stage1_official_release",
        "requested_cleanup_profile": "stage1_official_release",
    }
    for field, expected in exact.items():
        if str(row.get(field, "")) != expected:
            raise ValueError(f"{label}: {field}={row.get(field)!r}; expected {expected}")
    for field in (
        "has_primal_values", "stage1_status_gate_pass", "solve_gate_pass",
        "stage1_native_solver_certificate_pass", "stage1_native_algorithm_gate_pass",
        "stage1_gurobi_status_gate_pass", "stage1_gurobi_objval_gate_pass",
        "stage1_objective_scale_gate_pass",
        "strict_physical_audit_pass", "result_export_complete", "strict_export_pass",
        "regularization_share_gate_pass", "lexicographic_economic_gate_pass",
        "stage1_official_release_selected", "stage1_official_release_pass",
        "cleanup_diagnostic_nonblocking", "investment_capacity_policy_outputs_release_eligible",
        "model_is_pure_lp", "cdr_module_exclusion_gate_pass", "official_cdr_disabled",
        "legacy_allocation_audit_pass",
    ):
        if not truth(row.get(field)):
            raise ValueError(f"{label}: required strict publication gate {field}=false or missing")
    if number(row.get("stage1_result_count"), field=f"{label}.stage1_result_count") < 1:
        raise ValueError(f"{label}: stage1_result_count < 1")
    if number(row.get("model_binary_variable_count"), field=f"{label}.binary_count") != 0:
        raise ValueError(f"{label}: model contains binary variables")
    if number(row.get("model_integer_variable_count"), field=f"{label}.integer_count") != 0:
        raise ValueError(f"{label}: model contains integer variables")
    if truth(row.get("storage_cdr_modules_compiled")):
        raise ValueError(f"{label}: storage CDR modules were compiled")
    if any(truth(row.get(field)) for field in ("allow_nbccs", "allow_daccs", "allow_beccs")):
        raise ValueError(f"{label}: a forbidden CDR option is enabled")

    if layer == "A":
        if str(row.get("storage_chronology_mode", "")) != "monthly_linked":
            raise ValueError(f"{label}: Layer-A chronology is not monthly_linked")
        if not truth(row.get("storage_interperiod_soc_linked")):
            raise ValueError(f"{label}: Layer-A interperiod SOC linkage is absent")
        if not truth(row.get("target_year_static_reoptimization")):
            raise ValueError(f"{label}: Layer-A target-year static reoptimization gate failed")
        if truth(row.get("storage_full_chronological_claim_supported")):
            raise ValueError(f"{label}: Layer-A cannot claim continuous FULL8760 chronology")
    elif layer in {"B", "C"}:
        if str(row.get("storage_chronology_mode", "")) != "intraday_cyclic":
            raise ValueError(f"{label}: Layer-{layer} chronology is not intraday_cyclic")
        if str(row.get("v18_storage_portfolio_mode", "")) != "evidence_bounded":
            raise ValueError(f"{label}: Layer-{layer} portfolio is not evidence_bounded")
        if number(row.get("representative_timepoint_count"), field=f"{label}.timepoints") != 504:
            raise ValueError(f"{label}: Layer-{layer} representative_timepoint_count != 504")
        for field in (
            "storage_intermonth_soc_linked", "storage_long_duration_claim_supported",
            "storage_full_chronological_claim_supported", "storage_multiweather_claim_supported",
        ):
            if truth(row.get(field)):
                raise ValueError(f"{label}: forbidden Layer-{layer} chronology claim {field}=true")
    else:
        raise ValueError(f"Unsupported V20 layer: {layer}")


def validate_v20_result_fingerprint(
    source_root: Path, result_dir: Path, case_dir: Path, scenario: str
) -> None:
    """Validate the immutable source/case/result chain stamped by the upstream."""
    result_fp_path = result_dir / "PUBLICATION_RESULT_SOURCE_FINGERPRINT.json"
    case_fp_path = case_dir / "audits" / "CASE_PUBLICATION_SOURCE_FINGERPRINT.json"
    source_fp_path = source_root / "audits" / "PUBLICATION_SOURCE_FINGERPRINT.json"
    for path in (result_fp_path, case_fp_path, source_fp_path, result_dir / "solve_status.csv"):
        if not path.is_file():
            raise FileNotFoundError(path)
    result_fp = json.loads(result_fp_path.read_text(encoding="utf-8-sig"))
    case_fp = json.loads(case_fp_path.read_text(encoding="utf-8-sig"))
    if result_fp.get("schema_version") != "publication_result_fingerprint_v1":
        raise ValueError(f"{scenario}: invalid result fingerprint schema")
    if case_fp.get("schema_version") != "publication_case_fingerprint_v2":
        raise ValueError(f"{scenario}: invalid case fingerprint schema")
    if result_fp.get("scenario") != scenario or case_fp.get("scenario") != scenario:
        raise ValueError(f"{scenario}: source-lineage scenario mismatch")
    expected = {
        "source_fingerprint_sha256": sha256(source_fp_path),
        "case_fingerprint_sha256": sha256(case_fp_path),
        "solve_status_sha256": sha256(result_dir / "solve_status.csv"),
    }
    for field, value in expected.items():
        if str(result_fp.get(field, "")).lower() != value:
            raise ValueError(f"{scenario}: result fingerprint mismatch for {field}")
    if result_fp.get("case_input_manifest_sha256") != case_fp.get("input_manifest_sha256"):
        raise ValueError(f"{scenario}: case input-manifest fingerprint mismatch")


def resolve_full8760_summary(root: Path) -> Path:
    candidates = [
        root / "robustness_distance_8760_quality_recovery_outputs" / "V17T2R6R24P3_HF18P2_COMBINED_ALL4_final_summary.json",
        root / "V17T2R6R24P3_HF18P2_COMBINED_ALL4_final_summary.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    found = sorted(root.glob("R24P3_FULL8760_POSTPROCESS_EVIDENCE_*/V17T2R6R24P3_HF18P2_COMBINED_ALL4_final_summary.json"))
    if len(found) == 1:
        return found[0]
    raise FileNotFoundError(
        "R24P3 combined four-case summary was not found. Point --full8760-root either to the actual "
        "03_FULL8760 root or to the extracted R24P3 evidence bundle."
    )


def load_full8760_records(root: Path) -> tuple[Path, list[dict[str, Any]]]:
    summary_path = resolve_full8760_summary(root)
    payload = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    if payload.get("version") != "V17T2R6R24P3_HF18P2_COMBINED_ALL4":
        raise ValueError(
            "FULL8760 source is not the final HF18 fixed-portfolio robustness-certificate system; "
            f"found version={payload.get('version')!r}"
        )
    if payload.get("status") != "PASS" or payload.get("all_four_certificates_success") is not True:
        raise ValueError("FULL8760 combined summary is not an R24P3 four-certificate PASS")
    invariant_flags = (
        "scientific_model_changed", "chronology_changed", "source_portfolios_changed",
        "protected_results_changed",
    )
    changed = [field for field in invariant_flags if payload.get(field) is not False]
    if changed:
        raise ValueError(f"FULL8760 final robustness summary did not preserve scientific invariants: {changed}")
    records = list(payload.get("records", []))
    names = [str(record.get("scenario", "")) for record in records]
    if len(records) != 4 or len(set(names)) != 4 or set(names) != set(FULL8760_SCENARIOS):
        raise ValueError(f"FULL8760 summary must contain exactly the four declared scenarios; found={names}")
    for record in records:
        if record.get("certificate_success") is not True:
            raise ValueError(f"FULL8760 certificate is not successful: {record.get('scenario')}")
        classification = str(record.get("classification", ""))
        if classification not in {"ORIGINAL_FIXED_PORTFOLIO_STRICTLY_FEASIBLE", "CERTIFIED_POSITIVE_ROBUSTNESS_GAP"}:
            raise ValueError(f"FULL8760 invalid classification: {classification}")
        distance = number(record.get("total_robustness_distance_mw"), field=f"{record.get('scenario')}.distance")
        feasible = record.get("original_fixed_portfolio_feasible") is True
        if feasible != (classification == "ORIGINAL_FIXED_PORTFOLIO_STRICTLY_FEASIBLE"):
            raise ValueError(f"FULL8760 feasibility/classification conflict: {record.get('scenario')}")
        if distance < -1.0e-6:
            raise ValueError(f"FULL8760 negative robustness distance: {record.get('scenario')}")
    return summary_path, records


def full8760_enhanced_diagnostic_route(record: dict[str, Any], scenario: str) -> bool:
    """Return whether the certificate must carry the R24P2+ diagnostic schema."""
    origin = str(record.get("certificate_origin", ""))
    if "R24P2" in origin or "R24P3" in origin:
        return True
    if "R24P1" in origin:
        return False
    raise ValueError(f"{scenario}: unrecognized FULL8760 certificate origin: {origin!r}")


def full8760_route_diagnostic_number(
    status: dict[str, Any], field: str, record: dict[str, Any], scenario: str
) -> float | None:
    """Read a post-R24P1 diagnostic without inventing a value for old schema.

    R24P2/R24P3 must contain a finite number.  R24P1 may omit the field because
    it did not yet exist; a present R24P1 value is still checked for finiteness.
    """
    required = full8760_enhanced_diagnostic_route(record, scenario)
    value = status.get(field)
    missing = value is None or str(value).strip().lower() in {"", "nan", "none", "null"}
    if missing:
        if required:
            raise ValueError(f"{scenario}: required R24P2+ diagnostic is missing: {field}")
        return None
    return number(value, field=f"{scenario}.{field}")


def validate_full8760_promoted_certificate(
    output: Path, status: dict[str, Any], record: dict[str, Any], scenario: str
) -> dict[str, bool]:
    """Validate one promoted FULL8760 certificate against its native route.

    The final R24P3 combined set intentionally protects two earlier R24P1
    certificates and combines them with R24P2/R24P3 quality-recovery results.
    Componentwise/scaled quality fields were introduced only in R24P2, so they
    are mandatory for R24P2/R24P3 and are checked when present in R24P1, while
    the original common certificate, lineage and fingerprint gates remain
    mandatory for all four cases.
    """
    strict_solver_status(status, scenario)
    if output.name != f"{scenario}__main":
        raise ValueError(f"{scenario}: resolved FULL8760 output is not the promoted __main directory")
    if any(part.lower() in {"_attempts", "attempts"} for part in output.parts):
        raise ValueError(f"{scenario}: historical attempt directory is not publication-eligible: {output}")
    if str(status.get("scenario", scenario)) != scenario:
        raise ValueError(f"{scenario}: solve_status scenario mismatch")

    common_fields = (
        "stage1_has_values", "route_gate_pass", "source_lineage_gate_pass",
        "objective_gate_pass", "native_quality_gate_pass", "pure_lp",
        "robustness_distance_certificate_pass",
    )
    gates: dict[str, bool] = {field: truth(status.get(field)) for field in common_fields}
    origin = str(record.get("certificate_origin", ""))
    enhanced_route = full8760_enhanced_diagnostic_route(record, scenario)
    enhanced_fields = (
        "componentwise_native_quality_gate_pass", "maxvio_decomposition_gate_pass",
        "scaled_residual_gate_pass", "core_physical_quality_gate_pass",
        "physical_quality_gate_pass",
    )
    for field in enhanced_fields:
        present = field in status and str(status.get(field, "")).strip().lower() not in {"", "nan"}
        if enhanced_route or present:
            gates[field] = truth(status.get(field))
    failed = [field for field, passed in gates.items() if not passed]
    if failed:
        raise ValueError(f"{scenario}: FULL8760 route-specific gates failed: {failed}; origin={origin!r}")

    enhanced_numeric_fields = (
        "gurobi_constr_residual", "gurobi_constr_sresidual",
        "gurobi_dual_residual", "gurobi_dual_sresidual",
        "decomposed_max_vio", "maxvio_decomposition_error",
        "max_zone_balance_residual_mw", "max_zone_balance_tolerance_ratio",
        "max_distributed_balance_residual_mw", "max_distributed_balance_tolerance_ratio",
        "max_planning_reserve_shortfall_mw", "max_planning_reserve_tolerance_ratio",
        "max_explicit_peak_shortfall_mw", "max_explicit_peak_tolerance_ratio",
        "max_soc_step_residual_mwh", "max_soc_step_tolerance_ratio",
        "max_soc_bound_violation_mwh", "max_soc_bound_tolerance_ratio",
    )
    for field in enhanced_numeric_fields:
        full8760_route_diagnostic_number(status, field, record, scenario)

    required = {
        "certificate": output / "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE.json",
        "lineage": output / "hf18_fixed_portfolio_lineage.json",
        "fingerprint": output / "HF18P2_RESULT_FINGERPRINT.json",
        "zone_distance": output / "hf18p2_robustness_distance_by_zone.csv",
    }
    for label, path in required.items():
        if not path.is_file():
            raise FileNotFoundError(f"{scenario}: missing {label}: {path}")

    certificate = json.loads(required["certificate"].read_text(encoding="utf-8-sig"))
    if (
        certificate.get("certificate_pass") is not True
        or certificate.get("scenario") != scenario
        or not str(certificate.get("source_manifest_sha256", "")).strip()
    ):
        raise ValueError(f"{scenario}: robustness certificate identity/pass gate failed")
    classification = str(status.get("classification", ""))
    feasible = truth(status.get("original_fixed_portfolio_feasible"))
    if (
        classification != str(record.get("classification", ""))
        or feasible != (record.get("original_fixed_portfolio_feasible") is True)
        or certificate.get("classification") != classification
        or certificate.get("original_fixed_portfolio_feasible") is not feasible
    ):
        raise ValueError(f"{scenario}: combined summary/status/certificate classification conflict")

    lineage = json.loads(required["lineage"].read_text(encoding="utf-8-sig"))
    if not lineage.get("pass") or not lineage.get("robustness_distance_only"):
        raise ValueError(f"{scenario}: fixed-portfolio robustness-only lineage gate failed")
    if number(lineage.get("max_canonicalization_abs", 0.0), field=f"{scenario}.max_canonicalization_abs") > 1.0e-7:
        raise ValueError(f"{scenario}: fixed-portfolio canonicalization exceeded 1e-7")

    fingerprint = json.loads(required["fingerprint"].read_text(encoding="utf-8-sig"))
    if fingerprint.get("scenario") != scenario:
        raise ValueError(f"{scenario}: result fingerprint scenario mismatch")
    fingerprint_rows = list(fingerprint.get("files", []))
    if not fingerprint_rows:
        raise ValueError(f"{scenario}: result fingerprint has no files")
    for item in fingerprint_rows:
        relative = Path(str(item.get("path", "")))
        candidate = (output / relative).resolve()
        try:
            candidate.relative_to(output.resolve())
        except ValueError as exc:
            raise ValueError(f"{scenario}: result fingerprint path escapes promoted output: {relative}") from exc
        if str(item.get("sha256", "")).lower() != sha256(candidate):
            raise ValueError(f"{scenario}: result fingerprint mismatch: {relative}")
    return gates


def resolve_full8760_output(root: Path, summary_path: Path, record: dict[str, Any]) -> Path:
    scenario = str(record["scenario"])
    relative = str(record.get("output", "")).strip()
    bases = [root, summary_path.parent, summary_path.parent.parent]
    candidates: list[Path] = []
    if relative:
        candidates.extend(base / relative for base in bases)
    candidates.extend([
        root / "certificate_outputs" / f"{scenario}__main",
        summary_path.parent / "certificate_outputs" / f"{scenario}__main",
        root / "robustness_distance_8760_quality_recovery_outputs" / f"{scenario}__main",
        root / "robustness_distance_8760_outputs" / f"{scenario}__main",
    ])
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if (
            resolved.name == f"{scenario}__main"
            and resolved.is_dir()
            and (resolved / "solve_status.csv").is_file()
        ):
            return resolved
    raise FileNotFoundError(f"FULL8760 certificate directory not found for {scenario}")


def resolve_v20_layer_a_root(root: Path) -> Path:
    direct = root / "modules" / "correction2033"
    if direct.is_dir():
        return direct
    if (root / "storage_runner" / "scenarios_future_correction.csv").is_file():
        return root
    raise FileNotFoundError("V20 Layer-A correction2033 module is missing")


def resolve_layer_a_output(root: Path, scenario: str) -> Path:
    module = resolve_v20_layer_a_root(root)
    candidates = [
        module / "future_correction_outputs" / f"{scenario}__main",
        module / "future_correction_cases" / scenario / "outputs" / f"{scenario}__main",
    ]
    for candidate in candidates:
        if (candidate / "solve_status.csv").is_file():
            return candidate
    raise FileNotFoundError(f"V20 Layer-A promoted output missing: {scenario}")


def resolve_v20_output(root: Path, scenario: str) -> Path:
    candidates = [
        root / "outputs" / f"{scenario}__main",
        root / "storage_cases" / scenario / "outputs" / f"{scenario}__main",
    ]
    for candidate in candidates:
        if (candidate / "solve_status.csv").is_file():
            return candidate
    raise FileNotFoundError(f"V20 promoted output missing: {scenario}")


def find_v20_solver_summary(root: Path, layer: str) -> Path:
    names = {
        "B": ("V20_LAYER_B_16_SOLVER_SUMMARY.csv",),
        "C": ("V20_LAYER_C_EQUAL_HORIZON_2_SOLVER_SUMMARY.csv", "V20_LAYER_C_2_SOLVER_SUMMARY.csv"),
    }[layer]
    bases = [root / "audits" / "v20", root / "v20_outputs" / "tables"]
    for base in bases:
        for name in names:
            candidate = base / name
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(f"V20 Layer-{layer} solver summary is missing")


def load_v20_solver_summary(root: Path, layer: str) -> pd.DataFrame:
    path = find_v20_solver_summary(root, layer)
    frame = pd.read_csv(path)
    expected = V20_LAYER_B_SCENARIOS if layer == "B" else V20_LAYER_C_SCENARIOS
    scenario_col = first_column(frame, ["scenario"])
    strict_col = first_column(frame, ["publication_strict_success", "strict_success", "solver_native_strict_success"])
    names = frame[scenario_col].astype(str).tolist()
    if len(frame) != len(expected) or set(names) != set(expected) or len(set(names)) != len(expected):
        raise ValueError(f"V20 Layer-{layer} summary scenario set mismatch: {names}")
    if not frame[strict_col].map(truth).all():
        failed = frame.loc[~frame[strict_col].map(truth), scenario_col].astype(str).tolist()
        raise ValueError(f"V20 Layer-{layer} contains non-strict results: {failed}")
    return frame


def load_v20_layer_a_summary(root: Path) -> pd.DataFrame:
    module = resolve_v20_layer_a_root(root)
    path = module / "future_correction_outputs" / "V19_LAYER_A_run_summary.csv"
    frame = pd.read_csv(path) if path.is_file() else pd.DataFrame(columns=["scenario"])
    scenario_col = first_column(frame, ["scenario"])
    names = frame[scenario_col].astype(str).tolist()
    unexpected = sorted(set(names).difference(V20_LAYER_A_SCENARIOS))
    if unexpected or len(names) != len(set(names)):
        raise ValueError(f"V20 Layer-A summary contains unexpected or duplicate scenarios: {names}")
    if not frame.empty:
        strict_col = first_column(frame, ["publication_strict_success"])
        if not frame[strict_col].map(truth).all():
            failed = frame.loc[~frame[strict_col].map(truth), scenario_col].astype(str).tolist()
            raise ValueError(f"V20 Layer-A summary contains an explicitly non-strict row: {failed}")

    registry_path = module / "storage_runner" / "scenarios_future_correction.csv"
    registry = pd.read_csv(registry_path)
    registry_scenario = first_column(registry, ["scenario"])
    registry_names = registry[registry_scenario].astype(str).tolist()
    if len(registry) != 8 or len(set(registry_names)) != 8 or set(registry_names) != set(V20_LAYER_A_SCENARIOS):
        raise ValueError(f"V20 Layer-A registry must contain the exact eight declared scenarios: {registry_names}")
    registry = registry.set_index(registry_scenario, drop=False)

    def present(value: Any) -> bool:
        if value is None:
            return False
        try:
            if pd.isna(value):
                return False
        except (TypeError, ValueError):
            pass
        return str(value).strip() != ""

    records: list[dict[str, Any]] = []
    for scenario in V20_LAYER_A_SCENARIOS:
        output = resolve_layer_a_output(root, scenario)
        status = read_one_csv(output / "solve_status.csv")
        strict_v20_status(status, scenario, "A")
        validate_v20_result_fingerprint(
            module, output, module / "future_correction_cases" / scenario, scenario
        )
        _validate_v20_layer_a_hf5_lineage_if_present(module, output, status, scenario)

        matches = frame.loc[frame[scenario_col].astype(str).eq(scenario)]
        if len(matches) > 1:
            raise ValueError(f"V20 Layer-A summary duplicates {scenario}")
        if len(matches) == 1:
            record = matches.iloc[0].to_dict()
            resolution = "upstream_summary_row_revalidated_against_strict_promoted_output"
            comparisons = {
                "successful_solver_profile": "solver_profile",
                "stage1_termination_status": "stage1_termination_status",
                "stage1_primal_status": "stage1_primal_status",
                "stage1_dual_status": "stage1_dual_status",
            }
            for summary_field, status_field in comparisons.items():
                if present(record.get(summary_field)) and str(record[summary_field]) != str(status.get(status_field, "")):
                    raise ValueError(
                        f"{scenario}: Layer-A summary {summary_field}={record[summary_field]!r} "
                        f"does not match promoted solve_status {status_field}={status.get(status_field)!r}"
                    )
        else:
            record = {}
            resolution = "reconstructed_from_strict_promoted_output_missing_upstream_summary_row"

        registry_row = registry.loc[scenario].to_dict()
        for field in ("pair_id", "target_year", "experiment_role", "portfolio_scope", "transmission_case"):
            if field in registry_row:
                if present(record.get(field)) and str(record[field]) != str(registry_row[field]):
                    raise ValueError(
                        f"{scenario}: Layer-A summary {field}={record[field]!r} "
                        f"does not match scenario registry {registry_row[field]!r}"
                    )
                record[field] = registry_row[field]
        record.update({
            "scenario": scenario,
            "publication_strict_success": True,
            "successful_solver_profile": status.get("solver_profile", ""),
            "stage1_termination_status": status.get("stage1_termination_status", ""),
            "stage1_primal_status": status.get("stage1_primal_status", ""),
            "stage1_dual_status": status.get("stage1_dual_status", ""),
            "stage1_economic_optimum": status.get(
                "stage1_economic_optimum", status.get("stage1_economic_objective_usd", "")
            ),
            "promoted_output": output.relative_to(module).as_posix(),
            "summary_row_present": len(matches) == 1,
            "summary_resolution_source": resolution,
            "canonical_solve_status_sha256": sha256(output / "solve_status.csv"),
            "canonical_result_fingerprint_sha256": sha256(
                output / "PUBLICATION_RESULT_SOURCE_FINGERPRINT.json"
            ),
        })
        records.append(record)
    return pd.DataFrame(records)


def _validate_v20_layer_a_hf5_lineage_if_present(
    module: Path, output: Path, status: dict[str, Any], scenario: str
) -> None:
    """Verify the FC08 HF5 exact-projection evidence when that route was used."""
    lineage_path = output / "HF5_REDUCED_MODEL_RESULT_LINEAGE.json"
    formulation = str(status.get("legacy_reallocation_formulation_version", "")).strip()
    hf5_used = lineage_path.is_file() or bool(formulation)
    if not hf5_used:
        return
    if scenario != "FC08_EXPANDED_OPTIMAL":
        raise ValueError(f"{scenario}: HF5 reduced-form lineage is only declared for FC08")
    expected_formulation = "V20HF5_equivalent_reduced_formulation_v1"
    if formulation != expected_formulation:
        raise ValueError(f"{scenario}: unexpected HF5 formulation {formulation!r}")
    exact = {
        "algebraic_reduction_version": "V20HF5_equivalent_hourly_coordinate_projection_v1",
        "legacy_energy_variable_projection_count": 32,
        "total_omitted_hourly_columns": 152352,
    }
    for field, expected in exact.items():
        actual = status.get(field)
        if isinstance(expected, int):
            if number(actual, field=f"{scenario}.{field}") != expected:
                raise ValueError(f"{scenario}: {field}={actual!r}; expected {expected}")
        elif str(actual) != expected:
            raise ValueError(f"{scenario}: {field}={actual!r}; expected {expected!r}")
    for field in (
        "legacy_national_energy_identity_pass",
        "legacy_zone_caps_encoded_as_variable_bounds",
        "legacy_energy_variable_projection_active",
        "legacy_projected_energy_output_reconstruction",
        "algebraic_reduction_preserves_scientific_inputs",
        "algebraic_reduction_preserves_objective_and_projected_feasible_set",
    ):
        if not truth(status.get(field)):
            raise ValueError(f"{scenario}: HF5 equivalence gate {field}=false or missing")
    if any(truth(status.get(field)) for field in (
        "legacy_national_energy_closure_constraint_emitted",
        "legacy_common_duration_constraints_emitted",
    )):
        raise ValueError(f"{scenario}: HF5 eliminated constraints were unexpectedly emitted")
    residual = abs(number(status.get("legacy_national_energy_identity_residual_mwh"), field=f"{scenario}.HF5_residual"))
    tolerance = number(status.get("legacy_national_energy_identity_tolerance_mwh"), field=f"{scenario}.HF5_tolerance")
    if residual > tolerance:
        raise ValueError(f"{scenario}: HF5 national-energy identity residual {residual} > {tolerance}")
    if not lineage_path.is_file():
        raise FileNotFoundError(f"{scenario}: HF5 result lineage is missing: {lineage_path}")
    lineage = json.loads(lineage_path.read_text(encoding="utf-8-sig"))
    if (
        lineage.get("schema_version") != "v20_hf5_reduced_model_result_lineage_v1"
        or lineage.get("status") != "PASS"
        or lineage.get("scenario") != scenario
        or lineage.get("formulation_version") != expected_formulation
        or str(lineage.get("solve_status_sha256", "")).lower() != sha256(output / "solve_status.csv")
    ):
        raise ValueError(f"{scenario}: HF5 result-lineage identity/hash gate failed")
    for path_field, hash_field in (
        ("projected_model", "projected_model_sha256"),
        ("projected_runner", "projected_runner_sha256"),
    ):
        relative = Path(str(lineage.get(path_field, "")))
        candidate = (module / relative).resolve()
        try:
            candidate.relative_to(module.resolve())
        except ValueError as exc:
            raise ValueError(f"{scenario}: HF5 lineage path escapes the module: {relative}") from exc
        if str(lineage.get(hash_field, "")).lower() != sha256(candidate):
            raise ValueError(f"{scenario}: HF5 lineage hash mismatch for {path_field}")


def objective_column(frame: pd.DataFrame) -> str:
    return first_column(frame, [
        "stage1_economic_objective_usd",
        "stage1_economic_optimum_usd",
        "economic_objective_usd",
        "objective_value",
        "stage1_objective",
    ])  # type: ignore[return-value]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Refusing to write an empty publication table: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
