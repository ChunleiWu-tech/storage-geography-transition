#!/usr/bin/env python3
"""Scientific and scope audits for V17T2R5 target-year sensitivity tables."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from targetyear_sensitivity_common import PAIR_ORDER, output_dir, registry, status_record, truth
from v17t5_paths import AUDIT_DIR, PROJECT_ROOT, TABLE_TARGETYEAR, TARGETYEAR_ROOT


def write_json(name: str, payload: dict[str, Any]) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def close(a: float, b: float, rel: float = 1e-8, abs_: float = 1.0) -> bool:
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_)


def main() -> None:
    reg = registry()
    scenarios = pd.read_csv(TABLE_TARGETYEAR / "targetyear_all_scenario_metrics.csv")
    pairs = pd.read_csv(TABLE_TARGETYEAR / "targetyear_pairwise_observed_minus_optimal.csv")
    components = pd.read_csv(TABLE_TARGETYEAR / "figS12b_cost_component_decomposition.csv")
    chronology = pd.read_csv(TABLE_TARGETYEAR / "targetyear_soc_chronology_summary.csv")
    legacy = pd.read_csv(TABLE_TARGETYEAR / "targetyear_legacy_allocation_all_scenarios.csv")
    attenuation = pd.read_csv(TABLE_TARGETYEAR / "targetyear_ldes_attenuation.csv")
    ldes_mix = pd.read_csv(TABLE_TARGETYEAR / "figS12c_ldes_technology_mix.csv")
    temporal = pd.read_csv(TABLE_TARGETYEAR / "targetyear_one_hour_discretization.csv")

    audits: dict[str, bool] = {}

    # Preserve the upstream model-lineage, package and pair-identity evidence.
    upstream_audit_specs = {
        "V17T2R5_MODEL_LINEAGE.json": "model_lineage",
        "STATIC_PACKAGE_AUDIT_V17T2R5.json": "static_package",
        "V17T2R5_PAIR_IDENTITY_AUDIT.json": "upstream_pair_identity",
    }
    upstream_rows = []
    for filename, key in upstream_audit_specs.items():
        path = TARGETYEAR_ROOT / "audits" / filename
        exists = path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8")) if exists else {}
        status_pass = str(payload.get("status", "")).upper() == "PASS"
        pair_pass = True
        if filename == "V17T2R5_PAIR_IDENTITY_AUDIT.json" and exists:
            pair_pass = len(payload.get("pairs", [])) == 4 and all(
                str(item.get("status", "")).upper() == "PASS" for item in payload.get("pairs", [])
            )
        passed = exists and status_pass and pair_pass
        upstream_rows.append({"file": filename, "exists": exists, "status": payload.get("status", ""), "pair_pass": pair_pass, "pass": passed})
        audits[key] = passed
    upstream_audit = pd.DataFrame(upstream_rows)
    upstream_audit.to_csv(AUDIT_DIR / "targetyear_upstream_lineage_and_identity_audit.csv", index=False)
    write_json("targetyear_upstream_lineage_and_identity_audit.json", {
        "all_pass": bool(upstream_audit["pass"].all()),
        "files": upstream_rows,
    })

    strict_rows: list[dict[str, Any]] = []
    for _, expected in reg.iterrows():
        scenario = str(expected["scenario"])
        status = status_record(scenario)
        pass_ = (
            str(status.get("stage1_termination_status")) == "OPTIMAL"
            and str(status.get("stage1_primal_status")) == "FEASIBLE_POINT"
            and str(status.get("stage1_dual_status")) == "FEASIBLE_POINT"
            and truth(status.get("strict_export_pass"))
            and truth(status.get("result_export_complete"))
        )
        strict_rows.append({
            "scenario": scenario,
            "termination_status": status.get("stage1_termination_status"),
            "primal_status": status.get("stage1_primal_status"),
            "dual_status": status.get("stage1_dual_status"),
            "strict_export_pass": truth(status.get("strict_export_pass")),
            "pass": pass_,
        })
    strict = pd.DataFrame(strict_rows)
    strict.to_csv(AUDIT_DIR / "targetyear_8_of_8_strict_success.csv", index=False)
    strict_summary = {
        "version": "V17T5R6R8R5",
        "expected": 8,
        "passed": int(strict["pass"].sum()),
        "all_pass": bool(strict["pass"].all()),
    }
    write_json("targetyear_8_of_8_strict_success.json", strict_summary)
    audits["eight_of_eight_strict_success"] = strict_summary["all_pass"]

    # Cost-basis reconciliation.  The stage-1 objective is the discounted
    # target-year block present value, whereas Fig. S12 reports the separate
    # nondiscounted annual target-year cost.  R8R4 incorrectly compared these
    # unlike bases directly.  R8R5 reconciles the solver objective only against
    # SystemCost_present_value_to_base_year and audits the annual/PV conversion
    # factor separately without changing any upstream result.
    cost_rows = []
    for row in scenarios.itertuples(index=False):
        objective = float(row.stage1_economic_optimum_usd)
        present_value = float(row.targetyear_system_cost_present_value_usd)
        annual = float(row.annual_system_cost_usd_per_yr)
        factor = float(row.targetyear_present_value_factor)
        objective_difference = objective - present_value
        reconstructed_present_value = annual * factor
        conversion_difference = reconstructed_present_value - present_value
        objective_tolerance = max(10.0, 1e-7 * max(1.0, abs(objective), abs(present_value)))
        conversion_tolerance = max(0.01, 1e-12 * max(1.0, abs(present_value)))
        objective_pass = abs(objective_difference) <= objective_tolerance
        conversion_pass = (
            math.isfinite(factor)
            and factor > 0.0
            and abs(conversion_difference) <= conversion_tolerance
        )
        passed = objective_pass and conversion_pass
        cost_rows.append({
            "scenario": row.scenario,
            "stage1_economic_optimum_present_value_usd": objective,
            "electricity_cost_present_value_usd": present_value,
            "annual_system_cost_usd_per_yr": annual,
            "present_value_factor": factor,
            "objective_minus_exported_present_value_usd": objective_difference,
            "annual_times_factor_minus_present_value_usd": conversion_difference,
            "objective_tolerance_usd": objective_tolerance,
            "conversion_tolerance_usd": conversion_tolerance,
            "objective_basis_pass": objective_pass,
            "annual_to_present_value_conversion_pass": conversion_pass,
            "pass": passed,
        })
    cost = pd.DataFrame(cost_rows)
    cost.to_csv(AUDIT_DIR / "targetyear_cost_recalculation_audit.csv", index=False)
    cost_summary = {
        "cost_basis_policy": {
            "stage1_objective": "discounted target-year block present value in USD",
            "figure_and_pair_penalty": "nondiscounted annual target-year cost in USD per year",
            "direct_objective_vs_annual_comparison_forbidden": True,
        },
        "all_pass": bool(cost["pass"].all()),
        "max_abs_objective_minus_present_value_usd": float(cost["objective_minus_exported_present_value_usd"].abs().max()),
        "max_abs_annual_conversion_error_usd": float(cost["annual_times_factor_minus_present_value_usd"].abs().max()),
    }
    write_json("targetyear_cost_recalculation_audit.json", cost_summary)
    audits["cost_recalculation"] = cost_summary["all_pass"]

    # Component decomposition closure.
    component_sum = components.groupby("pair_id")["observed_minus_optimized_usd_per_yr"].sum()
    pair_penalty = pairs.set_index("pair_id")["annual_location_penalty_usd_per_yr"]
    closure_rows = []
    for pair_id in PAIR_ORDER:
        error = float(component_sum.loc[pair_id] - pair_penalty.loc[pair_id])
        tolerance = max(1.0, abs(float(pair_penalty.loc[pair_id])) * 1e-10)
        closure_rows.append({"pair_id": pair_id, "closure_error_usd_per_yr": error, "tolerance_usd_per_yr": tolerance, "pass": abs(error) <= tolerance})
    closure = pd.DataFrame(closure_rows)
    closure.to_csv(AUDIT_DIR / "targetyear_cost_component_closure_audit.csv", index=False)
    audits["cost_component_closure"] = bool(closure["pass"].all())

    # Pair identity and equal national inherited stock.
    identity_rows = []
    national_totals = legacy.groupby(["scenario", "pair_id", "legacy_allocation_mode"], as_index=False).agg(
        legacy_power_mw=("realized_legacy_power_mw", "sum"),
        legacy_energy_mwh=("realized_legacy_energy_mwh", "sum"),
        zone_count=("model_zone", "nunique"),
    )
    for pair_id in PAIR_ORDER:
        grp = national_totals.loc[national_totals["pair_id"].eq(pair_id)]
        obs = grp.loc[grp["legacy_allocation_mode"].eq("observed_standardized")].iloc[0]
        opt = grp.loc[grp["legacy_allocation_mode"].eq("optimized_reallocation")].iloc[0]
        power_diff = float(obs.legacy_power_mw - opt.legacy_power_mw)
        energy_diff = float(obs.legacy_energy_mwh - opt.legacy_energy_mwh)
        passed = obs.zone_count == 32 and opt.zone_count == 32 and abs(power_diff) <= 1e-3 and abs(energy_diff) <= 1e-2
        identity_rows.append({
            "pair_id": pair_id,
            "observed_power_mw": float(obs.legacy_power_mw),
            "optimized_power_mw": float(opt.legacy_power_mw),
            "power_difference_mw": power_diff,
            "observed_energy_mwh": float(obs.legacy_energy_mwh),
            "optimized_energy_mwh": float(opt.legacy_energy_mwh),
            "energy_difference_mwh": energy_diff,
            "observed_zone_count": int(obs.zone_count),
            "optimized_zone_count": int(opt.zone_count),
            "pass": passed,
        })
    identity = pd.DataFrame(identity_rows)
    identity.to_csv(AUDIT_DIR / "targetyear_pair_identity_audit.csv", index=False)
    identity_summary = {"all_pass": bool(identity["pass"].all()), "pairs": identity.to_dict("records")}
    write_json("targetyear_pair_identity_audit.json", identity_summary)
    audits["pair_identity"] = identity_summary["all_pass"]

    # Chronology residual and bounds remain far below publication tolerance.
    chronology = chronology.copy()
    chronology["max_bound_violation_mwh"] = chronology[["max_lower_bound_violation_mwh", "max_upper_bound_violation_mwh"]].max(axis=1)
    chronology["linkage_pass"] = chronology["max_abs_linkage_residual_mwh"] <= 0.10
    chronology["bound_pass"] = chronology["max_bound_violation_mwh"] <= 0.10
    chronology["pass"] = chronology["linkage_pass"] & chronology["bound_pass"]
    chronology.to_csv(AUDIT_DIR / "targetyear_soc_chronology_audit.csv", index=False)
    chronology_summary = {
        "tolerance_mwh": 0.10,
        "max_linkage_residual_mwh": float(chronology["max_abs_linkage_residual_mwh"].max()),
        "max_bound_violation_mwh": float(chronology["max_bound_violation_mwh"].max()),
        "all_pass": bool(chronology["pass"].all()),
    }
    write_json("targetyear_soc_chronology_audit.json", chronology_summary)
    audits["soc_chronology"] = chronology_summary["all_pass"]

    # Unit and sign policy: preserve raw signs; no clipping of penalties/attenuation.
    unit_sign = {
        "annual_cost_unit": "USD per year",
        "location_penalty_definition": "reconstructed-standardized annual cost minus optimized-reallocation annual cost",
        "capacity_difference_definition": "reconstructed-standardized minus optimized-reallocation",
        "ldes_attenuation_definition": "(chronology-only penalty - chronology+LDES penalty) / chronology-only penalty",
        "sign_clipping_or_absolute_value_applied": False,
        "finite_pair_penalties": bool(np.isfinite(pairs["annual_location_penalty_usd_per_yr"]).all()),
        "finite_attenuation": bool(np.isfinite(attenuation["ldes_attenuation_fraction"]).all()),
    }
    unit_sign["all_pass"] = unit_sign["finite_pair_penalties"] and unit_sign["finite_attenuation"]
    write_json("targetyear_units_sign_audit.json", unit_sign)
    audits["units_and_sign"] = unit_sign["all_pass"]

    # LDES isolation.
    ldes_mask = scenarios["ldes_enabled"].map(truth)
    ldes_rows = scenarios.loc[ldes_mask]
    non_ldes = scenarios.loc[~ldes_mask]
    ldes_isolation = {
        "ldes_enabled_scenarios": ldes_rows["scenario"].tolist(),
        "ldes_enabled_count": int(len(ldes_rows)),
        "only_2033_ldes_pair_enabled": set(ldes_rows["scenario"]) == {"TY2033_CHRONO_LDES_OBSERVED", "TY2033_CHRONO_LDES_OPTIMAL"},
        "non_ldes_scenarios_have_zero_ldes_power": bool((non_ldes["targetyear_ldes_power_mw"].abs() <= 1e-6).all()),
        "non_ldes_scenarios_have_zero_ldes_energy": bool((non_ldes["targetyear_ldes_energy_mwh"].abs() <= 1e-6).all()),
    }
    ldes_isolation["all_pass"] = all(v for k, v in ldes_isolation.items() if k.endswith("enabled") or k.startswith("non_ldes") or k == "only_2033_ldes_pair_enabled")
    # explicit boolean above avoids depending on list fields
    ldes_isolation["all_pass"] = bool(
        ldes_isolation["only_2033_ldes_pair_enabled"]
        and ldes_isolation["non_ldes_scenarios_have_zero_ldes_power"]
        and ldes_isolation["non_ldes_scenarios_have_zero_ldes_energy"]
    )
    write_json("targetyear_ldes_isolation_audit.json", ldes_isolation)
    audits["ldes_isolation"] = ldes_isolation["all_pass"]

    expected_ldes = {
        "LDES_CAES_10h", "LDES_CAES_24h", "LDES_CAES_100h",
        "LDES_VRFB_10h", "LDES_VRFB_24h", "LDES_H2_100h",
        "LDES_PSH_10h", "LDES_PSH_24h",
    }
    mix_coverage = {
        "scenario_count": int(ldes_mix["scenario"].nunique()),
        "each_ldes_scenario_has_all_eight_candidates": bool(
            ldes_mix.groupby("scenario")["technology"].nunique().eq(8).all()
        ),
        "technology_set_exact": set(ldes_mix["technology"].astype(str)) == expected_ldes,
        "zero_deployment_is_explicit": bool("deployed" in ldes_mix.columns),
    }
    mix_coverage["all_pass"] = all(bool(v) for k, v in mix_coverage.items() if k != "scenario_count") and mix_coverage["scenario_count"] == 2
    write_json("targetyear_ldes_portfolio_coverage_audit.json", mix_coverage)
    audits["ldes_portfolio_coverage"] = mix_coverage["all_pass"]

    one_hour_rows = scenarios.loc[scenarios["time_resolution_h"].eq(1)]
    temporal_scope = {
        "one_hour_scenarios": one_hour_rows["scenario"].tolist(),
        "exact_one_hour_pair": set(one_hour_rows["scenario"]) == {"TY2033_CHRONO_1H_OBSERVED", "TY2033_CHRONO_1H_OPTIMAL"},
        "four_hour_scenario_count": int(scenarios["time_resolution_h"].eq(4).sum()),
        "comparison_row_count": int(len(temporal)),
        "full_8760_hour_claim_supported": False,
        "observed_hourly_input_claim_supported": False,
    }
    temporal_scope["all_pass"] = bool(
        temporal_scope["exact_one_hour_pair"]
        and temporal_scope["four_hour_scenario_count"] == 6
        and temporal_scope["comparison_row_count"] == 1
    )
    write_json("targetyear_one_hour_scope_audit.json", temporal_scope)
    audits["one_hour_scope"] = temporal_scope["all_pass"]

    # Main/sensitivity scope separation is a hard release condition.
    scope = {
        "main_upstream_root": str(PROJECT_ROOT.resolve()),
        "targetyear_upstream_root": str(TARGETYEAR_ROOT.resolve()),
        "roots_are_distinct": PROJECT_ROOT.resolve() != TARGETYEAR_ROOT.resolve(),
        "main_result_scope": "multi-period capacity-expansion present-value results",
        "targetyear_result_scope": "single-target-year annual linked-representative-month SOC re-optimization",
        "targetyear_added_to_main_present_value_penalty": False,
        "targetyear_replaces_main_result": False,
        "targetyear_claims_full_8760_hour_chronology": False,
        "ldes_claimed_as_resource-complete_deployment_forecast": False,
    }
    scope["all_pass"] = bool(scope["roots_are_distinct"])
    write_json("main_and_sensitivity_scope_separation_audit.json", scope)
    audits["scope_separation"] = scope["all_pass"]

    # Required source tables.
    required_tables = [
        "targetyear_all_scenario_metrics.csv",
        "targetyear_pairwise_observed_minus_optimal.csv",
        "figS12a_targetyear_cost_penalty.csv",
        "figS12b_cost_component_decomposition.csv",
        "figS12c_compensatory_investment.csv",
        "figS12d_operational_response.csv",
        "targetyear_ldes_attenuation.csv",
        "targetyear_one_hour_discretization.csv",
        "figS12c_ldes_technology_mix.csv",
        "targetyear_generation_build_by_technology.csv",
        "targetyear_storage_energy_build_by_technology.csv",
        "targetyear_soc_chronology_summary.csv",
    ]
    table_rows = []
    for name in required_tables:
        path = TABLE_TARGETYEAR / name
        exists = path.is_file()
        rows = len(pd.read_csv(path)) if exists else 0
        table_rows.append({"table": name, "exists": exists, "rows": rows, "pass": exists and rows > 0})
    table_audit = pd.DataFrame(table_rows)
    table_audit.to_csv(AUDIT_DIR / "targetyear_source_table_release_audit.csv", index=False)
    audits["source_tables"] = bool(table_audit["pass"].all())

    summary = {
        "version": "V17T5R6R8R5",
        "checks": len(audits),
        "passed": sum(bool(v) for v in audits.values()),
        "all_pass": all(bool(v) for v in audits.values()),
        "checks_detail": audits,
        "failed": [name for name, passed in audits.items() if not passed],
    }
    write_json("targetyear_scientific_consistency_audit.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
