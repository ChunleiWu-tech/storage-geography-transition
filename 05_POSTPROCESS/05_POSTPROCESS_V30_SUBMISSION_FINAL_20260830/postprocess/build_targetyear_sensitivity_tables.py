#!/usr/bin/env python3
"""Build publication tables for eight exact target-year linked-SOC sensitivities."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from targetyear_sensitivity_common import (
    PAIR_LABELS,
    PAIR_ORDER,
    finite_columns,
    ldes_technology_mix,
    legacy_map,
    pair_delta,
    pair_members,
    registry,
    scenario_metrics,
)
from v17t5_paths import TABLE_TARGETYEAR


def write(frame: pd.DataFrame, name: str) -> None:
    TABLE_TARGETYEAR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(TABLE_TARGETYEAR / name, index=False)


def main() -> None:
    reg = registry()
    metric_rows: list[dict[str, Any]] = []
    gen_frames: list[pd.DataFrame] = []
    energy_frames: list[pd.DataFrame] = []
    legacy_frames: list[pd.DataFrame] = []
    ldes_mix_frames: list[pd.DataFrame] = []

    for _, expected in reg.iterrows():
        record, gen, energy = scenario_metrics(expected)
        metric_rows.append(record)
        gen_frames.append(gen)
        energy_frames.append(energy)
        legacy = legacy_map(str(expected["scenario"]))
        legacy.insert(0, "scenario", str(expected["scenario"]))
        legacy.insert(1, "pair_id", str(expected["pair_id"]))
        legacy.insert(2, "target_year", int(expected["target_year"]))
        legacy.insert(3, "legacy_allocation_mode", str(expected["legacy_allocation_mode"]))
        legacy_frames.append(legacy)
        mix = ldes_technology_mix(str(expected["scenario"]))
        if not mix.empty:
            mix.insert(0, "scenario", str(expected["scenario"]))
            mix.insert(1, "pair_id", str(expected["pair_id"]))
            mix.insert(2, "legacy_allocation_mode", str(expected["legacy_allocation_mode"]))
            ldes_mix_frames.append(mix)

    scenarios = pd.DataFrame(metric_rows)
    finite_columns(
        scenarios,
        [
            "annual_system_cost_usd_per_yr",
            "targetyear_system_cost_present_value_usd",
            "targetyear_present_value_factor",
            "stage1_economic_optimum_usd",
            "system_demand_mwh_per_yr",
            "average_system_cost_usd_per_mwh",
            "targetyear_battery_power_mw",
            "targetyear_battery_energy_mwh",
            "targetyear_transmission_build_mw",
            "max_abs_linkage_residual_mwh",
        ],
    )
    generation = pd.concat(gen_frames, ignore_index=True)
    storage_energy = pd.concat(energy_frames, ignore_index=True)
    legacy_all = pd.concat(legacy_frames, ignore_index=True)
    ldes_mix = pd.concat(ldes_mix_frames, ignore_index=True) if ldes_mix_frames else pd.DataFrame()

    pair_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    investment_rows: list[dict[str, Any]] = []
    operation_rows: list[dict[str, Any]] = []
    reallocation_rows: list[pd.DataFrame] = []

    delta_columns = [
        "annual_system_cost_usd_per_yr",
        "average_system_cost_usd_per_mwh",
        "generation_capacity_cost_usd_per_yr",
        "storage_energy_cost_usd_per_yr",
        "transmission_cost_usd_per_yr",
        "fuel_cost_usd_per_yr",
        "other_system_cost_usd_per_yr",
        "targetyear_battery_power_mw",
        "targetyear_battery_energy_mwh",
        "targetyear_pumped_hydro_power_mw",
        "targetyear_pumped_hydro_energy_mwh",
        "targetyear_ldes_power_mw",
        "targetyear_ldes_energy_mwh",
        "targetyear_transmission_build_mw",
        "vre_curtailment_gwh_per_yr",
        "vre_curtailment_rate",
        "all_storage_charge_gwh_per_yr",
        "all_storage_discharge_gwh_per_yr",
        "net_annual_emissions_tco2",
    ]

    for pair_id in PAIR_ORDER:
        observed, optimized = pair_members(scenarios, pair_id)
        penalty = pair_delta(observed, optimized, "annual_system_cost_usd_per_yr")
        opt_cost = float(optimized["annual_system_cost_usd_per_yr"])
        obs_scenario = str(observed["scenario"])
        opt_scenario = str(optimized["scenario"])
        obs_map = legacy_map(obs_scenario).set_index("model_zone")
        opt_map = legacy_map(opt_scenario).set_index("model_zone")
        if not obs_map.index.equals(opt_map.index):
            raise ValueError(f"{pair_id}: legacy maps do not share identical model-zone indices")
        reallocation = opt_map - obs_map
        equivalent_power = 0.5 * float(reallocation["realized_legacy_power_mw"].abs().sum())
        equivalent_energy = 0.5 * float(reallocation["realized_legacy_energy_mwh"].abs().sum())
        pair_row: dict[str, Any] = {
            "pair_id": pair_id,
            "pair_label": PAIR_LABELS[pair_id],
            "target_year": int(observed["target_year"]),
            "context": str(observed["context"]),
            "observed_scenario": obs_scenario,
            "optimized_scenario": opt_scenario,
            "observed_annual_system_cost_usd_per_yr": float(observed["annual_system_cost_usd_per_yr"]),
            "optimized_annual_system_cost_usd_per_yr": opt_cost,
            "annual_location_penalty_usd_per_yr": penalty,
            "annual_location_penalty_million_usd_per_yr": penalty / 1e6,
            "annual_location_penalty_billion_usd_per_yr": penalty / 1e9,
            "annual_location_penalty_fraction_of_optimized": penalty / opt_cost if abs(opt_cost) > 1e-12 else np.nan,
            "equivalent_legacy_power_reallocation_mw": equivalent_power,
            "equivalent_legacy_power_reallocation_gw": equivalent_power / 1000.0,
            "equivalent_legacy_energy_reallocation_mwh": equivalent_energy,
            "equivalent_legacy_energy_reallocation_gwh": equivalent_energy / 1000.0,
            "max_pair_soc_linkage_residual_mwh": max(
                float(observed["max_abs_linkage_residual_mwh"]),
                float(optimized["max_abs_linkage_residual_mwh"]),
            ),
            "max_pair_soc_bound_violation_mwh": max(
                float(observed["max_lower_bound_violation_mwh"]),
                float(observed["max_upper_bound_violation_mwh"]),
                float(optimized["max_lower_bound_violation_mwh"]),
                float(optimized["max_upper_bound_violation_mwh"]),
            ),
            "claim_scope": str(observed["claim_scope"]),
        }
        for column in delta_columns:
            pair_row[f"observed_minus_optimized__{column}"] = pair_delta(observed, optimized, column)
        pair_rows.append(pair_row)

        components = {
            "Generation capacity": pair_delta(observed, optimized, "generation_capacity_cost_usd_per_yr"),
            "Storage energy": pair_delta(observed, optimized, "storage_energy_cost_usd_per_yr"),
            "Transmission": pair_delta(observed, optimized, "transmission_cost_usd_per_yr"),
            "Fuel": pair_delta(observed, optimized, "fuel_cost_usd_per_yr"),
            "Other system": pair_delta(observed, optimized, "other_system_cost_usd_per_yr"),
        }
        for component, value in components.items():
            component_rows.append(
                {
                    "pair_id": pair_id,
                    "pair_label": PAIR_LABELS[pair_id],
                    "target_year": int(observed["target_year"]),
                    "component": component,
                    "observed_minus_optimized_usd_per_yr": value,
                    "observed_minus_optimized_million_usd_per_yr": value / 1e6,
                }
            )

        investment_specs = [
            ("Battery power", "GW", "targetyear_battery_power_mw", 1000.0),
            ("Battery energy", "GWh", "targetyear_battery_energy_mwh", 1000.0),
            ("Pumped-hydro power", "GW", "targetyear_pumped_hydro_power_mw", 1000.0),
            ("Pumped-hydro energy", "GWh", "targetyear_pumped_hydro_energy_mwh", 1000.0),
            ("LDES power", "GW", "targetyear_ldes_power_mw", 1000.0),
            ("LDES energy", "GWh", "targetyear_ldes_energy_mwh", 1000.0),
            ("Transmission build", "GW", "targetyear_transmission_build_mw", 1000.0),
        ]
        for metric, unit, column, scale in investment_specs:
            investment_rows.append(
                {
                    "pair_id": pair_id,
                    "pair_label": PAIR_LABELS[pair_id],
                    "target_year": int(observed["target_year"]),
                    "metric": metric,
                    "unit": unit,
                    "observed": float(observed[column]) / scale,
                    "optimized": float(optimized[column]) / scale,
                    "observed_minus_optimized": pair_delta(observed, optimized, column) / scale,
                }
            )

        operation_specs = [
            ("VRE curtailment", "TWh yr$^{-1}$", "vre_curtailment_gwh_per_yr", 1000.0),
            ("Storage charging", "TWh yr$^{-1}$", "all_storage_charge_gwh_per_yr", 1000.0),
            ("Storage discharge", "TWh yr$^{-1}$", "all_storage_discharge_gwh_per_yr", 1000.0),
            ("Net emissions", "MtCO$_2$ yr$^{-1}$", "net_annual_emissions_tco2", 1e6),
            ("Average system cost", "USD MWh$^{-1}$", "average_system_cost_usd_per_mwh", 1.0),
        ]
        for metric, unit, column, scale in operation_specs:
            operation_rows.append(
                {
                    "pair_id": pair_id,
                    "pair_label": PAIR_LABELS[pair_id],
                    "target_year": int(observed["target_year"]),
                    "metric": metric,
                    "unit": unit,
                    "observed": float(observed[column]) / scale,
                    "optimized": float(optimized[column]) / scale,
                    "observed_minus_optimized": pair_delta(observed, optimized, column) / scale,
                }
            )

        realloc = reallocation.reset_index().rename(
            columns={
                "realized_legacy_power_mw": "optimized_minus_observed_legacy_power_mw",
                "realized_legacy_energy_mwh": "optimized_minus_observed_legacy_energy_mwh",
            }
        )
        realloc.insert(0, "pair_id", pair_id)
        realloc.insert(1, "pair_label", PAIR_LABELS[pair_id])
        realloc.insert(2, "target_year", int(observed["target_year"]))
        reallocation_rows.append(realloc)

    pairs = pd.DataFrame(pair_rows)
    cost_components = pd.DataFrame(component_rows)
    investments = pd.DataFrame(investment_rows)
    operations = pd.DataFrame(operation_rows)
    reallocations = pd.concat(reallocation_rows, ignore_index=True)

    base = pairs.set_index("pair_id")
    p0 = float(base.loc["TY2033_CHRONO", "annual_location_penalty_usd_per_yr"])
    p1 = float(base.loc["TY2033_CHRONO_LDES", "annual_location_penalty_usd_per_yr"])
    attenuation = pd.DataFrame(
        [
            {
                "comparison": "2033 linked SOC vs linked SOC + technology-specific discrete LDES portfolio",
                "chronology_only_penalty_usd_per_yr": p0,
                "chronology_ldes_penalty_usd_per_yr": p1,
                "ldes_absolute_change_usd_per_yr": p1 - p0,
                "ldes_retention_fraction": p1 / p0 if abs(p0) > 1e-12 else np.nan,
                "ldes_attenuation_fraction": (p0 - p1) / p0 if abs(p0) > 1e-12 else np.nan,
                "interpretation": "technology-specific pressure test using CAES, VRFB, hydrogen and pumped-storage candidates; pumped storage shares the existing provincial resource ceiling, while CAES, VRFB and hydrogen remain unconstrained resource pressure tests",
            }
        ]
    )
    p_1h = float(base.loc["TY2033_CHRONO_1H", "annual_location_penalty_usd_per_yr"])
    temporal_discretization = pd.DataFrame([
        {
            "comparison": "2033 four-hour vs one-hour representative-day discretization",
            "four_hour_penalty_usd_per_yr": p0,
            "one_hour_penalty_usd_per_yr": p_1h,
            "one_hour_minus_four_hour_usd_per_yr": p_1h - p0,
            "one_hour_retention_fraction": p_1h / p0 if abs(p0) > 1e-12 else np.nan,
            "interpretation": "energy-preserving bounded within-block reconstruction; a temporal-discretization sensitivity, not observed hourly data or a full 8760-hour chronology",
        }
    ])

    generation_all = generation.copy()
    energy_all = storage_energy.copy()
    generation_pair = generation_all.pivot_table(
        index=["pair_id", "target_year", "technology"],
        columns="legacy_allocation_mode",
        values="build_power_mw",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()
    for column in ["observed_standardized", "optimized_reallocation"]:
        if column not in generation_pair:
            generation_pair[column] = 0.0
    generation_pair["observed_minus_optimized_build_power_mw"] = (
        generation_pair["observed_standardized"] - generation_pair["optimized_reallocation"]
    )

    energy_pair = energy_all.pivot_table(
        index=["pair_id", "target_year", "technology"],
        columns="legacy_allocation_mode",
        values="build_energy_mwh",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()
    for column in ["observed_standardized", "optimized_reallocation"]:
        if column not in energy_pair:
            energy_pair[column] = 0.0
    energy_pair["observed_minus_optimized_build_energy_mwh"] = (
        energy_pair["observed_standardized"] - energy_pair["optimized_reallocation"]
    )

    chronology = scenarios[
        [
            "scenario",
            "pair_id",
            "target_year",
            "legacy_allocation_mode",
            "max_abs_linkage_residual_mwh",
            "max_lower_bound_violation_mwh",
            "max_upper_bound_violation_mwh",
        ]
    ].copy()

    write(scenarios, "targetyear_all_scenario_metrics.csv")
    write(pairs, "targetyear_pairwise_observed_minus_optimal.csv")
    write(cost_components, "figS12b_cost_component_decomposition.csv")
    write(investments, "figS12c_compensatory_investment.csv")
    write(operations, "figS12d_operational_response.csv")
    write(pairs[
        [
            "pair_id",
            "pair_label",
            "target_year",
            "observed_annual_system_cost_usd_per_yr",
            "optimized_annual_system_cost_usd_per_yr",
            "annual_location_penalty_usd_per_yr",
            "annual_location_penalty_million_usd_per_yr",
            "annual_location_penalty_fraction_of_optimized",
            "max_pair_soc_linkage_residual_mwh",
            "max_pair_soc_bound_violation_mwh",
        ]
    ], "figS12a_targetyear_cost_penalty.csv")
    write(attenuation, "targetyear_ldes_attenuation.csv")
    write(temporal_discretization, "targetyear_one_hour_discretization.csv")
    write(ldes_mix, "figS12c_ldes_technology_mix.csv")
    write(reallocations, "targetyear_reallocation_by_zone.csv")
    write(generation_pair, "targetyear_generation_build_by_technology.csv")
    write(energy_pair, "targetyear_storage_energy_build_by_technology.csv")
    write(chronology, "targetyear_soc_chronology_summary.csv")
    write(legacy_all, "targetyear_legacy_allocation_all_scenarios.csv")

    report = {
        "version": "V17T5R6R8R5",
        "upstream_sensitivity_version": "V17T2R5",
        "design": "single-target-year exact linked-SOC capacity-and-dispatch re-optimization",
        "pairs": pairs.to_dict("records"),
        "ldes_pressure_test": attenuation.iloc[0].to_dict(),
        "one_hour_discretization": temporal_discretization.iloc[0].to_dict(),
        "scope_lock": (
            "Annual target-year sensitivity results remain separate from the frozen multi-period present-value main results. "
            "They test sign, mechanisms, compensatory investment and LDES attenuation; they are not added to or substituted for the main location penalty."
        ),
    }
    (TABLE_TARGETYEAR / "targetyear_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"version": "V17T5R6R8R5", "scenario_rows": len(scenarios), "pair_rows": len(pairs), "success": True}, indent=2))


if __name__ == "__main__":
    main()
