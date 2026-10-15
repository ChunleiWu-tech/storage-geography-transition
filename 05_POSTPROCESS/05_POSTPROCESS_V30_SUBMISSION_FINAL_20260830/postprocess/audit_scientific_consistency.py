#!/usr/bin/env python3
"""Scientific consistency and information-content audit for V17T5 figures."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from v17t5_paths import AUDIT_DIR, TABLE_MAIN, TABLE_SUPP

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONTRACT = json.loads((PACKAGE_ROOT / "BASELINE_SCIENTIFIC_FINGERPRINT.json").read_text(encoding="utf-8"))["required_source_contract"]
EXPECTED_STORAGE_POWER_MW = float(SOURCE_CONTRACT["national_power_mw"])
EXPECTED_STORAGE_ENERGY_MWH = float(SOURCE_CONTRACT["national_energy_mwh"])


def read(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def main() -> None:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": str(detail)})

    nodes = read(TABLE_MAIN / "fig1a_legacy_nodes.csv")
    allocation = read(TABLE_MAIN / "fig2_spatial_allocation.csv")
    ladder = read(TABLE_MAIN / "fig2b_legacy_value_ladder.csv")
    cost = read(TABLE_MAIN / "fig3a_compensatory_investment.csv")
    burden = read(TABLE_MAIN / "fig3b_spatial_burden_2028.csv")
    persistence = read(TABLE_MAIN / "fig4a_mismatch_persistence.csv")
    correction = read(TABLE_MAIN / "fig4c_zone_correction.csv")
    robustness = read(TABLE_MAIN / "fig5_robustness_effects.csv")
    system_value = read(TABLE_MAIN / "fig3_system_value.csv")
    temporal = read(TABLE_SUPP / "figS16_temporal_scope.csv")
    transition = read(TABLE_MAIN / "fig5_transition_paths.csv")
    scenario_matrix = read(TABLE_SUPP / "figS06_scenario_matrix.csv")
    tx_lines = read(TABLE_SUPP / "figS11_transmission_line_differences.csv")

    add("exact_32_model_zones", len(nodes) == 32 and nodes["model_zone"].nunique() == 32, f"rows={len(nodes)}")
    add("national_storage_power_135_93_gw", np.isclose(nodes["existing_new_storage_power_mw"].sum(), EXPECTED_STORAGE_POWER_MW, rtol=0, atol=1e-3), nodes["existing_new_storage_power_mw"].sum())
    add("national_storage_energy_351_12_gwh", np.isclose(nodes["existing_new_storage_energy_mwh"].sum(), EXPECTED_STORAGE_ENERGY_MWH, rtol=0, atol=1e-3), nodes["existing_new_storage_energy_mwh"].sum())
    add("vre_input_is_nonzero", float(nodes["wind_solar_capacity_2023_mw"].sum()) > 1.0 and int((nodes["wind_solar_capacity_2023_mw"] > 0).sum()) >= 24, f"sum={nodes['wind_solar_capacity_2023_mw'].sum():.3f};positive_zones={(nodes['wind_solar_capacity_2023_mw']>0).sum()}")
    add("load_input_is_nonzero", float(nodes["coincident_peak_2023_mw"].min()) > 0, f"min={nodes['coincident_peak_2023_mw'].min()}")

    pair = allocation[allocation["scenario"].isin(["SL01_OBSERVED_STANDARDIZED", "SL02_OPTIMAL_REALLOCATION"])]
    add("paired_allocation_exact_64_rows", len(pair) == 64, f"rows={len(pair)}")
    for scenario in ["SL01_OBSERVED_STANDARDIZED", "SL02_OPTIMAL_REALLOCATION"]:
        frame = allocation[allocation["scenario"].eq(scenario)]
        add(f"{scenario}_national_power_closure", np.isclose(frame["realized_legacy_power_mw"].sum(), EXPECTED_STORAGE_POWER_MW, atol=1e-3), frame["realized_legacy_power_mw"].sum())
        add(f"{scenario}_national_energy_closure", np.isclose(frame["realized_legacy_energy_mwh"].sum(), EXPECTED_STORAGE_ENERGY_MWH, atol=1e-3), frame["realized_legacy_energy_mwh"].sum())
    opt = allocation[allocation["scenario"].eq("SL02_OPTIMAL_REALLOCATION")]
    eq_reallocation = 0.5 * float(opt["delta_power_vs_observed_standardized_mw"].abs().sum())
    add("reallocation_is_material", eq_reallocation > 0.01 * EXPECTED_STORAGE_POWER_MW, f"equivalent_mw={eq_reallocation}")
    add("reallocation_power_change_closes_to_zero", abs(float(opt["delta_power_vs_observed_standardized_mw"].sum())) <= 1e-3, opt["delta_power_vs_observed_standardized_mw"].sum())
    add("reallocation_energy_change_closes_to_zero", abs(float(opt["delta_energy_vs_observed_standardized_mwh"].sum())) <= 1e-3, opt["delta_energy_vs_observed_standardized_mwh"].sum())

    indexed_ladder = ladder.set_index("scenario")
    add("value_ladder_contains_six_core_cases", set(indexed_ladder.index) == {"SL00_OBSERVED_ACTUAL", "SL01_OBSERVED_STANDARDIZED", "SL02_OPTIMAL_REALLOCATION", "SL03_NO_LEGACY", "SL04_RULE_LOAD", "SL05_RULE_VRE"}, sorted(indexed_ladder.index))
    optimized_value = float(indexed_ladder.loc["SL02_OPTIMAL_REALLOCATION", "legacy_system_value_usd"])
    observed_value = float(indexed_ladder.loc["SL01_OBSERVED_STANDARDIZED", "legacy_system_value_usd"])
    add("optimized_legacy_value_is_positive", optimized_value > 0, optimized_value)
    add("observed_value_retention_between_zero_and_one", 0 < observed_value / optimized_value < 1, observed_value / optimized_value)
    add("no_legacy_is_zero_value_anchor", abs(float(indexed_ladder.loc["SL03_NO_LEGACY", "legacy_system_value_usd"])) <= 1e-6, indexed_ladder.loc["SL03_NO_LEGACY", "legacy_system_value_usd"])

    closure = cost["component_closure_error_usd_per_yr"].abs().max()
    scale = max(cost["annual_system_cost_delta_usd_per_yr"].abs().max(), 1.0)
    add("cost_component_closure", closure <= 1e-8 * scale + 1e-2, f"max_error={closure};scale={scale}")
    cumulative_pair = system_value.set_index("scenario")
    total_cost_delta = float(cumulative_pair.loc["SL01_OBSERVED_STANDARDIZED", "cumulative_system_cost_pv_usd"] - cumulative_pair.loc["SL02_OPTIMAL_REALLOCATION", "cumulative_system_cost_pv_usd"])
    add("period_pv_cost_deltas_close_to_total", np.isclose(cost["present_value_cost_delta_usd"].sum(), total_cost_delta, rtol=1e-8, atol=1e3), f"period_sum={cost['present_value_cost_delta_usd'].sum()};total={total_cost_delta}")
    add("early_compensatory_power_nonzero", float(cost.loc[cost["period"].isin([2028, 2033]), "battery_power_delta_mw"].abs().max()) > 1000, cost.loc[cost["period"].isin([2028, 2033]), "battery_power_delta_mw"].tolist())
    add("early_compensatory_energy_nonzero", float(cost.loc[cost["period"].isin([2028, 2033]), "battery_energy_delta_mwh"].abs().max()) > 1000, cost.loc[cost["period"].isin([2028, 2033]), "battery_energy_delta_mwh"].tolist())
    add("2028_spatial_burden_has_positive_and_negative_zones", bool((burden["power_delta_mw"] > 1e-6).any() and (burden["power_delta_mw"] < -1e-6).any()), f"min={burden['power_delta_mw'].min()};max={burden['power_delta_mw'].max()}")

    p0 = persistence.sort_values("period").iloc[0]
    add("persistence_starts_at_2023", int(p0["period"]) == 2023, p0["period"])
    add("power_persistence_starts_at_one", np.isclose(p0["power_persistence_fraction"], 1.0, atol=1e-9), p0["power_persistence_fraction"])
    add("energy_persistence_starts_at_one", np.isclose(p0["energy_persistence_fraction"], 1.0, atol=1e-9), p0["energy_persistence_fraction"])
    add("mismatch_is_substantially_corrected_at_some_period", float(persistence[["power_persistence_fraction", "energy_persistence_fraction"]].min().min()) < 0.5, persistence[["power_persistence_fraction", "energy_persistence_fraction"]].min().to_dict())
    add("final_mismatch_is_not_falsely_zero", float(persistence.sort_values("period").iloc[-1]["power_persistence_fraction"]) > 1e-4, persistence.sort_values("period").iloc[-1]["power_persistence_fraction"])
    add("correction_classification_is_informative", correction["correction_class"].nunique() >= 2, correction["correction_class"].value_counts().to_dict())

    contexts = set(robustness["legacy_context"].astype(str))
    add("robustness_exact_six_contexts", contexts == {"base", "tx_fixed", "ph_conservative", "carbon_tight", "battery_cost_low", "battery_cost_high"}, sorted(contexts))
    for metric in ["cumulative_system_cost_pv_usd", "future_battery_build_mw", "future_battery_energy_build_mwh"]:
        values = robustness[robustness["metric"].eq(metric)]["observed_minus_optimal"]
        add(f"{metric}_finite_in_all_contexts", len(values) == 6 and bool(np.isfinite(values).all()), values.tolist())
        if metric == "cumulative_system_cost_pv_usd":
            add(f"{metric}_positive_in_all_contexts", bool((values > 0).all()), values.tolist())
        add(f"{metric}_not_constant", values.nunique() > 1, values.tolist())


    # Information-content checks for supplementary figures. These prevent a
    # syntactically valid but semantically empty scenario matrix or missing
    # period-series from passing the release gate.
    required_matrix_cols={"scenario","legacy_allocation_mode","transmission_case","pumped_hydro_case","carbon_cap_multiplier","battery_cost_case"}
    add("scenario_matrix_required_fields", required_matrix_cols.issubset(scenario_matrix.columns), sorted(required_matrix_cols.difference(scenario_matrix.columns)))
    add("scenario_matrix_exact_16_rows", len(scenario_matrix)==16 and scenario_matrix["scenario"].nunique()==16, f"rows={len(scenario_matrix)}")
    matrix_variation = {
        "legacy": scenario_matrix["legacy_allocation_mode"].nunique(dropna=True),
        "transmission": scenario_matrix["transmission_case"].nunique(dropna=True),
        "pumped_hydro": scenario_matrix["pumped_hydro_case"].fillna("baseline").nunique(),
        "carbon": scenario_matrix["carbon_cap_multiplier"].nunique(dropna=True),
        "battery_cost": scenario_matrix["battery_cost_case"].nunique(dropna=True),
    }
    add("scenario_matrix_is_informative", matrix_variation["legacy"]>=6 and all(matrix_variation[k]>=2 for k in ["transmission","pumped_hydro","carbon","battery_cost"]), matrix_variation)

    core_period_scenarios=["SL00_OBSERVED_ACTUAL","SL01_OBSERVED_STANDARDIZED","SL02_OPTIMAL_REALLOCATION","SL03_NO_LEGACY","SL04_RULE_LOAD","SL05_RULE_VRE"]
    period_counts=transition.groupby("scenario")["period"].nunique().to_dict()
    add("transition_table_contains_all_core_scenarios", set(core_period_scenarios).issubset(set(transition["scenario"])), sorted(set(core_period_scenarios).difference(set(transition["scenario"]))))
    add("transition_table_has_seven_periods_per_core_scenario", all(int(period_counts.get(s,0))==7 for s in core_period_scenarios), period_counts)
    cost_pivot=transition.pivot(index="period",columns="scenario",values="SystemCost_present_value_to_base_year")
    plotted=[s for s in ["SL00_OBSERVED_ACTUAL","SL01_OBSERVED_STANDARDIZED","SL04_RULE_LOAD","SL05_RULE_VRE"] if s in cost_pivot.columns]
    add("period_cost_penalty_has_four_finite_series", len(plotted)==4 and bool(np.isfinite(cost_pivot[plotted].to_numpy()).all()), plotted)

    gross_by_period=tx_lines.groupby("period")["observed_minus_optimized_mw"].apply(lambda x:0.5*float(np.abs(x).sum()))
    add("transmission_reconfiguration_is_informative", bool((gross_by_period>1e-3).any()), gross_by_period.to_dict())

    if {"representative_timepoints", "representative_block_hours", "operational_period_count"}.issubset(temporal.columns):
        add("temporal_scope_504_timepoints", int(temporal["representative_timepoints"].iloc[0]) == 504, temporal["representative_timepoints"].iloc[0])
        add("temporal_scope_four_hour_blocks", int(temporal["representative_block_hours"].iloc[0]) == 4, temporal["representative_block_hours"].iloc[0])
        add("temporal_scope_seven_operational_periods", int(temporal["operational_period_count"].iloc[0]) == 7, temporal["operational_period_count"].iloc[0])

    frame = pd.DataFrame(checks)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(AUDIT_DIR / "scientific_consistency_audit.csv", index=False)
    summary = {
        "version": "V17T5R6R8R5",
        "checks": len(frame),
        "passed": int(frame["pass"].sum()),
        "all_pass": bool(frame["pass"].all()),
        "failed": frame.loc[~frame["pass"], "check"].tolist(),
    }
    (AUDIT_DIR / "scientific_consistency_audit.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary["all_pass"]:
        print(frame.loc[~frame["pass"]].to_string(index=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
