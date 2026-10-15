"""Common readers and audited aggregations for V17T2R5 target-year results."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from v17t5_paths import TARGETYEAR_OUTPUTS, TARGETYEAR_REGISTRY

EXPECTED_SCENARIOS = [
    "TY2028_CHRONO_OBSERVED",
    "TY2028_CHRONO_OPTIMAL",
    "TY2033_CHRONO_OBSERVED",
    "TY2033_CHRONO_OPTIMAL",
    "TY2033_CHRONO_LDES_OBSERVED",
    "TY2033_CHRONO_LDES_OPTIMAL",
    "TY2033_CHRONO_1H_OBSERVED",
    "TY2033_CHRONO_1H_OPTIMAL",
]
PAIR_ORDER = ["TY2028_CHRONO", "TY2033_CHRONO", "TY2033_CHRONO_LDES", "TY2033_CHRONO_1H"]
LDES_SCENARIOS = {
    "TY2033_CHRONO_LDES_OBSERVED",
    "TY2033_CHRONO_LDES_OPTIMAL",
}
LDES_PROXY_COLUMNS = [
    "generation_project",
    "technology",
    "province",
    "build_year",
    "build_power_mw",
    "build_energy_mwh",
    "implied_duration_h",
    "ldes_proxy_mode",
]
PAIR_LABELS = {
    "TY2028_CHRONO": "2028 linked SOC",
    "TY2033_CHRONO": "2033 linked SOC",
    "TY2033_CHRONO_LDES": "2033 linked SOC + technology-specific LDES",
    "TY2033_CHRONO_1H": "2033 linked SOC, 1 h discretization",
}

REQUIRED_RESULT_FILES = [
    "solve_status.csv",
    "scenario_config.json",
    "electricity_cost.csv",
    "BuildGen.csv",
    "BuildStorageEnergy.csv",
    "BuildTx.csv",
    "legacy_storage_allocation_audit.csv",
    "storage_chronology_audit.csv",
    "physical_audit_summary.csv",
    "dispatch.csv",
    "vre_curtailment_annual.csv",
    "carbon_cap_compliance_audit.csv",
    "ldes_proxy_build.csv",
]


def truth(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y", "t"}


def number(value: Any, default: float = float("nan")) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result


def read_csv(path: Path, *, required: bool = True) -> pd.DataFrame:
    if not path.is_file():
        if required:
            raise FileNotFoundError(path)
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"Required CSV has no header or columns: {path}") from exc


def ldes_proxy_frame(scenario: str) -> pd.DataFrame:
    """Read the scenario-declared LDES export without inventing missing data.

    The frozen Julia exporter builds ``DataFrame(NamedTuple[])`` when the LDES
    opportunity set is disabled. CSV.jl writes that zero-row, zero-column table
    as a zero-byte file. That exact representation means "not applicable" for
    the six non-LDES scenarios. It is not accepted for either LDES scenario,
    where candidate rows and the complete schema are required.
    """
    path = output_dir(scenario) / "ldes_proxy_build.csv"
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        if scenario in LDES_SCENARIOS:
            raise ValueError(f"{scenario}: enabled-LDES export has no header or candidate rows: {path}")
        return pd.DataFrame(columns=LDES_PROXY_COLUMNS)
    missing = set(LDES_PROXY_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"{scenario}: ldes_proxy_build.csv missing {sorted(missing)}")
    if scenario in LDES_SCENARIOS and frame.empty:
        raise ValueError(f"{scenario}: enabled-LDES export has a header but no candidate rows")
    if scenario not in LDES_SCENARIOS and not frame.empty:
        raise ValueError(f"{scenario}: disabled-LDES scenario unexpectedly exported {len(frame)} candidate rows")
    return frame


def read_one_row(path: Path) -> dict[str, Any]:
    frame = read_csv(path)
    if len(frame) != 1:
        raise ValueError(f"Expected exactly one row in {path}; found {len(frame)}")
    return frame.iloc[0].to_dict()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def output_dir(scenario: str) -> Path:
    return TARGETYEAR_OUTPUTS / f"{scenario}__main"


def registry() -> pd.DataFrame:
    frame = read_csv(TARGETYEAR_REGISTRY)
    needed = {
        "scenario",
        "pair_id",
        "target_year",
        "context",
        "legacy_allocation_mode",
        "allow_cas",
        "storage_chronology_mode",
        "ldes_proxy_mode",
        "time_resolution_h",
        "temporal_input_variant",
        "claim_scope",
    }
    missing = needed.difference(frame.columns)
    if missing:
        raise ValueError(f"Target-year registry missing columns: {sorted(missing)}")
    scenarios = frame["scenario"].astype(str).tolist()
    if scenarios != EXPECTED_SCENARIOS:
        raise ValueError(f"Target-year registry scenario order/content mismatch: {scenarios}")
    if frame["scenario"].duplicated().any() or len(frame) != 8:
        raise ValueError("Target-year registry must contain exactly eight unique scenarios")
    return frame.copy()


def scenario_config_record(scenario: str) -> dict[str, Any]:
    """Read the authoritative per-run scenario identity record.

    V17T2R5 writes a frozen traceability record to ``scenario_config.json``.
    The successful-export branch and ``solve_status.csv`` have asymmetric
    identity schemas, so both files are read without treating an omitted field
    as ``false`` or as an automatic conflict.
    """
    return read_json(output_dir(scenario) / "scenario_config.json")


def _identity_value_present(mapping: dict[str, Any], key: str) -> bool:
    """Return True only when an identity field is explicitly present and nonblank."""
    if key not in mapping:
        return False
    value = mapping.get(key)
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip() != ""


def status_record(scenario: str) -> dict[str, Any]:
    """Merge identity fields from the two frozen V17T2R5 release records.

    Successful V17T2R5 outputs have an asymmetric schema by design/history:

    * ``allow_cas`` is written to ``scenario_config.json`` but is not guaranteed
      to exist in the frozen ``solve_status.csv`` schema;
    * ``storage_chronology_mode`` and ``ldes_proxy_mode`` are written to
      ``solve_status.csv`` but the successful-export branch of the frozen model
      may omit them from ``scenario_config.json``.

    Therefore, a missing value in one file is *not* interpreted as ``false`` or
    as a conflict.  The field is taken from the other explicit source.  A hard
    conflict is raised only when both sources explicitly contain the field and
    disagree.  A field missing from both sources is also hard-failed downstream.
    """
    status = read_one_row(output_dir(scenario) / "solve_status.csv")
    config = scenario_config_record(scenario)
    conflicts: list[str] = []
    missing_fields: list[str] = []
    identity_sources: dict[str, str] = {}

    for key in ["allow_cas", "storage_chronology_mode", "ldes_proxy_mode"]:
        status_present = _identity_value_present(status, key)
        config_present = _identity_value_present(config, key)
        status_value = status.get(key)
        config_value = config.get(key)

        if status_present and config_present:
            if key == "allow_cas":
                same = truth(status_value) == truth(config_value)
            else:
                same = str(status_value).strip() == str(config_value).strip()
            if not same:
                conflicts.append(
                    f"{key}:solve_status={status_value!r},scenario_config={config_value!r}"
                )
            identity_sources[key] = "solve_status+scenario_config"
        elif status_present:
            identity_sources[key] = "solve_status"
        elif config_present:
            status[key] = config_value
            identity_sources[key] = "scenario_config"
        else:
            status[key] = None
            identity_sources[key] = "missing"
            missing_fields.append(key)

    status["_scenario_config_identity_conflicts"] = ";".join(conflicts)
    status["_identity_missing_fields"] = ";".join(missing_fields)
    status["_identity_sources_json"] = json.dumps(identity_sources, sort_keys=True)
    return status


def strict_status_failures(status: dict[str, Any], expected: pd.Series) -> list[str]:
    failures: list[str] = []
    exact = {
        "stage1_termination_status": "OPTIMAL",
        "stage1_primal_status": "FEASIBLE_POINT",
        "stage1_dual_status": "FEASIBLE_POINT",
        "termination_status": "OPTIMAL",
        "primal_status": "FEASIBLE_POINT",
        "dual_status": "FEASIBLE_POINT",
        "storage_chronology_mode": "monthly_linked",
        "ldes_proxy_mode": str(expected["ldes_proxy_mode"]),
        "audit_export_result_tier": "official_stage1_economic_optimum",
        "publication_solution_source": "stage1_solver_certified_economic_optimum",
        "successful_cleanup_route": "stage1_official_release",
        "requested_cleanup_profile": "stage1_official_release",
    }
    for key, value in exact.items():
        if str(status.get(key, "")) != value:
            failures.append(f"{key}={status.get(key)!r}, expected {value!r}")
    true_fields = [
        "has_primal_values",
        "stage1_status_gate_pass",
        "solve_gate_pass",
        "strict_physical_audit_pass",
        "result_export_complete",
        "strict_export_pass",
        "model_is_pure_lp",
        "cdr_module_exclusion_gate_pass",
        "official_cdr_disabled",
        "legacy_allocation_audit_pass",
        "stage1_official_release_selected",
        "stage1_official_release_pass",
        "stage1_native_solver_certificate_pass",
        "stage1_native_algorithm_gate_pass",
        "stage1_objective_scale_gate_pass",
        "stage1_gurobi_status_gate_pass",
        "stage1_gurobi_objval_gate_pass",
        "stage1_economic_optimality_gate_pass",
        "regularization_share_gate_pass",
        "lexicographic_economic_gate_pass",
        "cleanup_diagnostic_nonblocking",
        "investment_capacity_policy_outputs_release_eligible",
        "target_year_static_reoptimization",
        "storage_interperiod_soc_linked",
    ]
    for key in true_fields:
        if not truth(status.get(key)):
            failures.append(f"{key}=false")
    if number(status.get("stage1_gurobi_status"), -1) != 2:
        failures.append(f"stage1_gurobi_status={status.get('stage1_gurobi_status')!r}, expected 2")
    if number(status.get("stage1_result_count"), 0) < 1:
        failures.append("stage1_result_count < 1")
    if truth(status.get("target_year_transition_path_claim_supported")):
        failures.append("target_year_transition_path_claim_supported must be false")
    if truth(status.get("storage_full_chronological_claim_supported")):
        failures.append("storage_full_chronological_claim_supported must be false")
    if int(number(status.get("target_year_operation_period"), -1)) != int(expected["target_year"]):
        failures.append("target_year_operation_period mismatch")
    resolution_h = int(number(expected.get("time_resolution_h"), -1))
    expected_timepoints = {4: 72, 1: 288}.get(resolution_h)
    if expected_timepoints is None:
        failures.append(f"unsupported time_resolution_h={resolution_h}")
    elif int(number(status.get("representative_timepoint_count"), -1)) != expected_timepoints:
        failures.append(f"representative_timepoint_count must equal {expected_timepoints} for {resolution_h} h discretization")
    if int(number(status.get("operational_period_count"), -1)) != 1:
        failures.append("operational_period_count must equal 1")
    if int(number(status.get("stock_anchor_period_count"), -1)) != 1:
        failures.append("stock_anchor_period_count must equal 1")
    if int(number(status.get("model_binary_variable_count"), -1)) != 0:
        failures.append("binary variable count must equal zero")
    if int(number(status.get("model_integer_variable_count"), -1)) != 0:
        failures.append("integer variable count must equal zero")
    for field in ["allow_nbccs", "allow_daccs", "allow_beccs", "storage_cdr_modules_compiled"]:
        if truth(status.get(field)):
            failures.append(f"{field} must be false")
    identity_conflicts = str(status.get("_scenario_config_identity_conflicts", "")).strip()
    if identity_conflicts:
        failures.append("solve_status/scenario_config identity conflict: " + identity_conflicts)
    identity_missing = str(status.get("_identity_missing_fields", "")).strip()
    if identity_missing:
        failures.append("identity field missing from both solve_status and scenario_config: " + identity_missing)
    expected_cas = truth(expected["allow_cas"])
    if truth(status.get("allow_cas")) != expected_cas:
        failures.append(
            f"allow_cas mismatch: scenario_config/solve_status={status.get('allow_cas')!r}, registry={expected_cas!r}"
        )
    return failures


def annual_cost_row(scenario: str, target_year: int) -> pd.Series:
    """Return the unique target-year electricity-cost row.

    V17T2R5 deliberately exports two different cost bases:

    * ``SystemCost_annualized_usd_per_yr`` is the nondiscounted annual target-year
      system cost used for Fig. S12 and annual observed-minus-optimized penalties;
    * ``SystemCost_present_value_to_base_year`` is the discounted block present
      value that is actually minimized by the stage-1 solver objective.

    They must never be equated directly.  The postprocessor therefore requires
    both columns and keeps them as separate audited quantities.
    """
    frame = read_csv(output_dir(scenario) / "electricity_cost.csv")
    required = {
        "period",
        "SystemCost_annualized_usd_per_yr",
        "SystemCost_present_value_to_base_year",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{scenario}: electricity_cost.csv lacks required columns {sorted(missing)}")
    period = pd.to_numeric(frame["period"], errors="raise").astype(int)
    rows = frame.loc[period.eq(int(target_year))]
    if len(rows) != 1:
        raise ValueError(f"{scenario}: expected one electricity_cost row for {target_year}; found {len(rows)}")
    return rows.iloc[0]


def grouped_target_build(scenario: str, target_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    gen = read_csv(output_dir(scenario) / "BuildGen.csv")
    energy = read_csv(output_dir(scenario) / "BuildStorageEnergy.csv")
    for frame, year_col in [(gen, "build_year"), (energy, "build_year")]:
        frame[year_col] = pd.to_numeric(frame[year_col], errors="raise").astype(int)
    gen["BuildGen"] = pd.to_numeric(gen["BuildGen"], errors="coerce").fillna(0.0)
    energy_col = "BuildStorageEnergy_MWh" if "BuildStorageEnergy_MWh" in energy.columns else "BuildStorageEnergy"
    energy[energy_col] = pd.to_numeric(energy[energy_col], errors="coerce").fillna(0.0)
    g = (
        gen.loc[gen["build_year"].eq(int(target_year))]
        .groupby("technology", as_index=False)["BuildGen"]
        .sum()
        .rename(columns={"BuildGen": "build_power_mw"})
    )
    e = (
        energy.loc[energy["build_year"].eq(int(target_year))]
        .groupby("technology", as_index=False)[energy_col]
        .sum()
        .rename(columns={energy_col: "build_energy_mwh"})
    )
    return g, e


def tx_build_mw(scenario: str, target_year: int) -> float:
    frame = read_csv(output_dir(scenario) / "BuildTx.csv")
    frame["build_year"] = pd.to_numeric(frame["build_year"], errors="raise").astype(int)
    column = "BuildTx" if "BuildTx" in frame.columns else next(
        (c for c in frame.columns if c.lower().startswith("buildtx")), None
    )
    if column is None:
        raise ValueError(f"{scenario}: BuildTx.csv lacks a build column")
    return float(pd.to_numeric(frame.loc[frame["build_year"].eq(int(target_year)), column], errors="coerce").sum())


def legacy_map(scenario: str) -> pd.DataFrame:
    frame = read_csv(output_dir(scenario) / "legacy_storage_allocation_audit.csv")
    needed = {"model_zone", "realized_legacy_power_mw", "realized_legacy_energy_mwh"}
    missing = needed.difference(frame.columns)
    if missing:
        raise ValueError(f"{scenario}: legacy allocation audit missing {sorted(missing)}")
    result = frame[list(needed)].copy()
    result["model_zone"] = result["model_zone"].astype(str)
    for column in ["realized_legacy_power_mw", "realized_legacy_energy_mwh"]:
        result[column] = pd.to_numeric(result[column], errors="raise")
    if result["model_zone"].duplicated().any():
        raise ValueError(f"{scenario}: duplicate model zones in legacy audit")
    return result.sort_values("model_zone").reset_index(drop=True)


def chronology_summary(scenario: str) -> dict[str, float]:
    frame = read_csv(output_dir(scenario) / "storage_chronology_audit.csv")
    needed = ["linkage_residual_mwh", "lower_bound_violation_mwh", "upper_bound_violation_mwh"]
    missing = set(needed).difference(frame.columns)
    if missing:
        raise ValueError(f"{scenario}: chronology audit missing {sorted(missing)}")
    if frame.empty:
        raise ValueError(f"{scenario}: chronology audit is empty")
    return {
        "max_abs_linkage_residual_mwh": float(pd.to_numeric(frame["linkage_residual_mwh"], errors="raise").abs().max()),
        "max_lower_bound_violation_mwh": float(pd.to_numeric(frame["lower_bound_violation_mwh"], errors="raise").max()),
        "max_upper_bound_violation_mwh": float(pd.to_numeric(frame["upper_bound_violation_mwh"], errors="raise").max()),
    }


def ldes_build(scenario: str) -> dict[str, float]:
    frame = ldes_proxy_frame(scenario)
    if frame.empty:
        return {"ldes_power_mw": 0.0, "ldes_energy_mwh": 0.0, "ldes_weighted_duration_h": float("nan")}
    power = pd.to_numeric(frame["build_power_mw"], errors="coerce").fillna(0.0)
    energy = pd.to_numeric(frame["build_energy_mwh"], errors="coerce").fillna(0.0)
    p = float(power.sum())
    e = float(energy.sum())
    return {"ldes_power_mw": p, "ldes_energy_mwh": e, "ldes_weighted_duration_h": e / p if p > 1e-9 else float("nan")}


def ldes_technology_mix(scenario: str) -> pd.DataFrame:
    """Return every discrete LDES candidate, including explicit zero builds."""
    frame = ldes_proxy_frame(scenario)
    columns = ["technology", "duration_h", "build_power_mw", "build_energy_mwh", "deployed"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    required = {"technology", "build_power_mw", "build_energy_mwh"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{scenario}: ldes_proxy_build.csv missing {sorted(missing)}")
    work = frame.copy()
    work["build_power_mw"] = pd.to_numeric(work["build_power_mw"], errors="raise")
    work["build_energy_mwh"] = pd.to_numeric(work["build_energy_mwh"], errors="raise")
    if "implied_duration_h" in work:
        work["duration_h"] = pd.to_numeric(work["implied_duration_h"], errors="coerce")
    else:
        work["duration_h"] = np.where(
            work["build_power_mw"].abs() > 1e-9,
            work["build_energy_mwh"] / work["build_power_mw"],
            np.nan,
        )
    encoded_duration = pd.to_numeric(
        work["technology"].astype(str).str.extract(r"_(\d+)h$")[0], errors="coerce"
    )
    work["duration_h"] = work["duration_h"].fillna(encoded_duration)
    grouped = work.groupby("technology", as_index=False).agg(
        duration_h=("duration_h", "max"),
        build_power_mw=("build_power_mw", "sum"),
        build_energy_mwh=("build_energy_mwh", "sum"),
    )
    grouped["deployed"] = grouped["build_power_mw"].abs() > 1e-6
    return grouped[columns]


def storage_operation(scenario: str) -> dict[str, float]:
    frame = read_csv(output_dir(scenario) / "dispatch.csv")
    if "is_storage" not in frame.columns:
        raise ValueError(f"{scenario}: dispatch.csv lacks is_storage")
    storage = frame.loc[frame["is_storage"].map(truth)].copy()
    result: dict[str, float] = {}
    if storage.empty:
        return result
    for technology, group in storage.groupby("gen_tech"):
        tech = str(technology)
        result[f"{tech}_charge_gwh_per_yr"] = float(pd.to_numeric(group["Store_GWh_typical_yr"], errors="coerce").fillna(0.0).sum())
        result[f"{tech}_discharge_gwh_per_yr"] = float(pd.to_numeric(group["Discharge_GWh_typical_yr"], errors="coerce").fillna(0.0).sum())
    result["all_storage_charge_gwh_per_yr"] = float(pd.to_numeric(storage["Store_GWh_typical_yr"], errors="coerce").fillna(0.0).sum())
    result["all_storage_discharge_gwh_per_yr"] = float(pd.to_numeric(storage["Discharge_GWh_typical_yr"], errors="coerce").fillna(0.0).sum())
    return result


def vre_metrics(scenario: str) -> dict[str, float]:
    frame = read_csv(output_dir(scenario) / "vre_curtailment_annual.csv")
    if frame.empty:
        return {"vre_potential_gwh_per_yr": 0.0, "vre_curtailment_gwh_per_yr": 0.0, "vre_curtailment_rate": 0.0}
    potential = float(pd.to_numeric(frame["Potential_GWh_typical_yr"], errors="coerce").fillna(0.0).sum())
    curtailed = float(pd.to_numeric(frame["Curtail_GWh_typical_yr"], errors="coerce").fillna(0.0).sum())
    return {
        "vre_potential_gwh_per_yr": potential,
        "vre_curtailment_gwh_per_yr": curtailed,
        "vre_curtailment_rate": curtailed / potential if potential > 1e-12 else float("nan"),
    }


def _strict_physical_bool(value: Any, *, field: str, row_index: int) -> bool:
    """Parse a frozen physical-audit boolean/status token strictly.

    The upstream Julia model writes boolean ``hard_gate`` and ``pass`` fields,
    while CSV readers may surface them as booleans, 0/1, or strings.  PASS/PASSED
    are accepted only for the ``pass`` field.  Blank and unknown tokens are hard
    errors rather than silently becoming false.
    """
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and int(value) in (0, 1):
        return bool(int(value))
    if isinstance(value, (float, np.floating)) and np.isfinite(value) and float(value) in (0.0, 1.0):
        return bool(int(value))
    token = str(value).strip().lower()
    true_tokens = {"true", "1", "yes", "y", "t"}
    false_tokens = {"false", "0", "no", "n", "f"}
    if field == "pass":
        true_tokens |= {"pass", "passed"}
        false_tokens |= {"fail", "failed"}
    if token in true_tokens:
        return True
    if token in false_tokens:
        return False
    raise ValueError(
        f"physical_audit_summary.csv row {row_index}: unrecognized {field} token {value!r}"
    )


def physical_pass(scenario: str) -> tuple[bool, list[str]]:
    """Recompute the upstream strict physical gate exactly.

    V17T2R5 defines the official release gate as
    ``all(row.pass || !row.hard_gate)``.  Disclosure-only degeneracy diagnostics
    are intentionally allowed to have ``pass=false`` when ``hard_gate=false``.
    Requiring every row to pass would therefore falsely reject solver-certified
    outputs.  This reader blocks only failed hard-gate rows and preserves all
    soft diagnostic failures for downstream disclosure.
    """
    frame = read_csv(output_dir(scenario) / "physical_audit_summary.csv")
    if frame.empty:
        return False, ["physical_audit_summary.csv empty"]
    lower_to_actual = {str(c).strip().lower(): c for c in frame.columns}
    missing = [name for name in ("hard_gate", "pass") if name not in lower_to_actual]
    if missing:
        return False, [f"physical_audit_summary.csv missing columns: {missing}"]
    hard_col = lower_to_actual["hard_gate"]
    pass_col = lower_to_actual["pass"]
    hard_values: list[bool] = []
    pass_values: list[bool] = []
    try:
        for i, row in frame.iterrows():
            hard_values.append(_strict_physical_bool(row[hard_col], field="hard_gate", row_index=int(i)))
            pass_values.append(_strict_physical_bool(row[pass_col], field="pass", row_index=int(i)))
    except ValueError as exc:
        return False, [str(exc)]
    hard = pd.Series(hard_values, index=frame.index, dtype=bool)
    passed = pd.Series(pass_values, index=frame.index, dtype=bool)
    failed_hard = frame.loc[hard & ~passed]
    failures: list[str] = []
    if not failed_hard.empty:
        for idx, row in failed_hard.iterrows():
            audit_file = str(row.get("audit_file", "unknown_audit_file"))
            check = str(row.get("check", f"row_{idx}"))
            failures.append(f"hard_gate_failed:{audit_file}:{check}")
    return not failures, failures


def cost_component_values(row: pd.Series) -> dict[str, float]:
    def get(name: str) -> float:
        return number(row.get(name), 0.0)
    known = {
        "generation_capacity": get("TotalGenCapacityCosts"),
        "storage_energy": get("StorageEnergyFixedCost"),
        "transmission": get("TxFixedCosts"),
        "fuel": get("FuelCostsPerYear") + get("OtherBiomassFuelCostsPerYear"),
    }
    total = number(row.get("SystemCost_annualized_usd_per_yr"))
    known_sum = sum(known.values())
    known["other_system"] = total - known_sum
    known["system_total"] = total
    return known


def scenario_metrics(expected: pd.Series) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    scenario = str(expected["scenario"])
    year = int(expected["target_year"])
    status = status_record(scenario)
    failures = strict_status_failures(status, expected)
    if failures:
        raise ValueError(f"{scenario}: strict status failures: {'; '.join(failures)}")
    physical_ok, physical_failures = physical_pass(scenario)
    if not physical_ok:
        raise ValueError(f"{scenario}: physical audit failures: {'; '.join(physical_failures)}")
    cost = annual_cost_row(scenario, year)
    gen, energy = grouped_target_build(scenario, year)
    gen_map = dict(zip(gen["technology"].astype(str), pd.to_numeric(gen["build_power_mw"], errors="raise")))
    energy_map = dict(zip(energy["technology"].astype(str), pd.to_numeric(energy["build_energy_mwh"], errors="raise")))
    chronology = chronology_summary(scenario)
    ldes = ldes_build(scenario)
    vre = vre_metrics(scenario)
    operation = storage_operation(scenario)
    components = cost_component_values(cost)
    demand = number(cost.get("SystemDemand_MWh"))
    emissions = number(cost.get("NetAnnualEmissions_tCO2"))
    carbon_cap = number(cost.get("CarbonCap_tCO2_per_yr"))
    annual_system_cost = components["system_total"]
    present_value_system_cost = number(cost.get("SystemCost_present_value_to_base_year"))
    present_value_factor = (
        present_value_system_cost / annual_system_cost
        if math.isfinite(present_value_system_cost) and abs(annual_system_cost) > 1e-12
        else float("nan")
    )
    record: dict[str, Any] = {
        "scenario": scenario,
        "pair_id": str(expected["pair_id"]),
        "pair_label": PAIR_LABELS[str(expected["pair_id"])],
        "target_year": year,
        "context": str(expected["context"]),
        "legacy_allocation_mode": str(expected["legacy_allocation_mode"]),
        "ldes_enabled": str(expected["ldes_proxy_mode"]) == "technology_portfolio_discrete",
        "ldes_proxy_mode": str(expected["ldes_proxy_mode"]),
        "time_resolution_h": int(expected["time_resolution_h"]),
        "temporal_input_variant": str(expected["temporal_input_variant"]),
        "claim_scope": str(expected["claim_scope"]),
        "solver_profile": str(status.get("solver_profile", "")),
        "annual_system_cost_usd_per_yr": annual_system_cost,
        "annual_system_cost_billion_usd_per_yr": annual_system_cost / 1e9,
        "targetyear_system_cost_present_value_usd": present_value_system_cost,
        "targetyear_present_value_factor": present_value_factor,
        "system_demand_mwh_per_yr": demand,
        "average_system_cost_usd_per_mwh": annual_system_cost / demand if demand > 0 else float("nan"),
        "stage1_economic_optimum_usd": number(status.get("stage1_economic_optimum")),
        "generation_capacity_cost_usd_per_yr": components["generation_capacity"],
        "storage_energy_cost_usd_per_yr": components["storage_energy"],
        "transmission_cost_usd_per_yr": components["transmission"],
        "fuel_cost_usd_per_yr": components["fuel"],
        "other_system_cost_usd_per_yr": components["other_system"],
        "targetyear_battery_power_mw": float(gen_map.get("Battery", 0.0)),
        "targetyear_battery_energy_mwh": float(energy_map.get("Battery", 0.0)),
        "targetyear_pumped_hydro_power_mw": float(gen_map.get("Hydro_Pumped", 0.0)),
        "targetyear_pumped_hydro_energy_mwh": float(energy_map.get("Hydro_Pumped", 0.0)),
        "targetyear_ldes_power_mw": float(ldes["ldes_power_mw"]),
        "targetyear_ldes_energy_mwh": float(ldes["ldes_energy_mwh"]),
        "targetyear_ldes_duration_h": float(ldes["ldes_weighted_duration_h"]),
        "targetyear_transmission_build_mw": tx_build_mw(scenario, year),
        "net_annual_emissions_tco2": emissions,
        "carbon_cap_tco2_per_yr": carbon_cap,
        **chronology,
        **vre,
        **operation,
    }
    gen = gen.assign(scenario=scenario, pair_id=record["pair_id"], target_year=year, legacy_allocation_mode=record["legacy_allocation_mode"])
    energy = energy.assign(scenario=scenario, pair_id=record["pair_id"], target_year=year, legacy_allocation_mode=record["legacy_allocation_mode"])
    return record, gen, energy


def pair_members(frame: pd.DataFrame, pair_id: str) -> tuple[pd.Series, pd.Series]:
    group = frame.loc[frame["pair_id"].eq(pair_id)]
    observed = group.loc[group["legacy_allocation_mode"].eq("observed_standardized")]
    optimized = group.loc[group["legacy_allocation_mode"].eq("optimized_reallocation")]
    if len(observed) != 1 or len(optimized) != 1:
        raise ValueError(f"{pair_id}: expected one observed and one optimized row")
    return observed.iloc[0], optimized.iloc[0]


def pair_delta(observed: pd.Series, optimized: pd.Series, column: str) -> float:
    return number(observed[column]) - number(optimized[column])


def finite_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if not np.isfinite(values).all():
            bad = frame.loc[~np.isfinite(values), ["scenario", column]].to_dict("records")
            raise ValueError(f"Non-finite values in {column}: {bad}")
