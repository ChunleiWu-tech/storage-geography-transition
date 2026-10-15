#!/usr/bin/env python3
"""Build V17T5 confirmatory and supplementary figure tables.

Scientific boundary
-------------------
Confirmatory tables use only solver-certified investment/capacity outputs,
annual cost/emissions/curtailment aggregates, and audited allocation metadata.
Degeneracy-sensitive gross dispatch, directional flow, reserve-transfer and
charge/discharge components are deliberately excluded from all confirmatory
figures.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from v17t5_paths import (
    AUDIT_DIR,
    MASTER,
    OUTPUT_ROOT,
    PROJECT_ROOT,
    TABLE_MAIN,
    TABLE_SUPP,
    TEMPLATE,
)

TRUE = {"true", "1", "yes", "y"}
CORE = [
    "SL00_OBSERVED_ACTUAL",
    "SL01_OBSERVED_STANDARDIZED",
    "SL02_OPTIMAL_REALLOCATION",
    "SL03_NO_LEGACY",
    "SL04_RULE_LOAD",
    "SL05_RULE_VRE",
]
PAIR_SCENARIOS = ["SL01_OBSERVED_STANDARDIZED", "SL02_OPTIMAL_REALLOCATION"]
ROBUSTNESS_CONTEXT_ORDER = [
    "base",
    "tx_fixed",
    "ph_conservative",
    "carbon_tight",
    "battery_cost_low",
    "battery_cost_high",
]


def _read_template_csv(name: str) -> pd.DataFrame:
    if not TEMPLATE.is_file():
        raise FileNotFoundError(TEMPLATE)
    with zipfile.ZipFile(TEMPLATE) as archive:
        with archive.open(f"inputs/{name}") as handle:
            return pd.read_csv(handle)


def _scenario_dir(outputs: Path, scenario: str) -> Path:
    directory = outputs / f"{scenario}__main"
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    return directory


def _read_output(outputs: Path, scenario: str, filename: str) -> pd.DataFrame:
    path = _scenario_dir(outputs, scenario) / filename
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def _require_columns(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = columns.difference(frame.columns)
    if missing:
        raise ValueError(f"{label} missing columns: {sorted(missing)}")


def _official(master: pd.DataFrame, scenario_set: str) -> pd.DataFrame:
    _require_columns(
        master,
        {"scenario", "v17_official_unique", "legacy_story_set"},
        "scenarios_storage_master.csv",
    )
    mask = master["v17_official_unique"].astype(str).str.lower().isin(TRUE)
    if scenario_set == "spatial_legacy_core":
        mask &= master["legacy_story_set"].eq("spatial_legacy_core")
    elif scenario_set == "spatial_legacy_robustness":
        mask &= master["legacy_story_set"].eq("spatial_legacy_robustness")
    elif scenario_set != "spatial_legacy_full":
        raise ValueError(scenario_set)
    return master.loc[mask].copy()


def _base_metadata() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        _read_template_csv("gen_info.csv"),
        _read_template_csv("gen_build_predetermined.csv"),
        _read_template_csv("zone_coincident_peak_demand.csv"),
        _read_template_csv("transmission_lines.csv"),
        _read_template_csv("periods.csv"),
    )


def _surviving_capacity(
    gen: pd.DataFrame, pred: pd.DataFrame, period: int, technologies: list[str]
) -> pd.DataFrame:
    meta = gen[["GENERATION_PROJECT", "gen_load_zone", "gen_tech", "gen_max_age"]]
    frame = pred.merge(meta, on="GENERATION_PROJECT", how="left", validate="many_to_one")
    frame["build_year"] = pd.to_numeric(frame["build_year"], errors="raise")
    frame["gen_max_age"] = pd.to_numeric(frame["gen_max_age"], errors="raise")
    frame["build_gen_predetermined"] = pd.to_numeric(
        frame["build_gen_predetermined"], errors="raise"
    ).fillna(0.0)
    frame = frame[frame["gen_tech"].isin(technologies)]
    frame = frame[
        (frame["build_year"] <= period)
        & (period < frame["build_year"] + frame["gen_max_age"])
    ]
    return (
        frame.groupby(["gen_load_zone", "gen_tech"], as_index=False)[
            "build_gen_predetermined"
        ]
        .sum()
        .copy()
    )


def _scenario_features(mode: str) -> dict[str, bool]:
    has_legacy = mode != "none"
    standardized = mode in {
        "observed_standardized",
        "optimized_reallocation",
        "rule_load",
        "rule_vre",
    }
    return {
        "legacy_power_present": has_legacy,
        "legacy_energy_present": has_legacy,
        "common_duration": standardized,
        "endogenous_location": mode == "optimized_reallocation",
        "rule_based_location": mode in {"rule_load", "rule_vre"},
    }


def build_input_tables(master: pd.DataFrame) -> dict[str, pd.DataFrame]:
    gen, pred, peak, lines, _ = _base_metadata()
    coordinates = pd.read_csv(
        PROJECT_ROOT / "data" / "visualization" / "model_zone_coordinates.csv"
    )
    observed = pd.read_csv(
        PROJECT_ROOT
        / "data"
        / "processed"
        / "existing_new_storage_allocated_to_model_zones_2025.csv"
    )
    _require_columns(
        coordinates, {"model_zone", "longitude", "latitude"}, "model_zone_coordinates.csv"
    )
    _require_columns(
        observed,
        {
            "model_zone",
            "existing_new_storage_power_mw",
            "existing_new_storage_energy_mwh",
        },
        "existing_new_storage_allocated_to_model_zones_2025.csv",
    )

    peak_2023 = peak[pd.to_numeric(peak["PERIOD"], errors="raise").eq(2023)][
        ["LOAD_ZONE", "zone_expected_coincident_peak_demand"]
    ].rename(
        columns={
            "LOAD_ZONE": "model_zone",
            "zone_expected_coincident_peak_demand": "coincident_peak_2023_mw",
        }
    )
    # Use the exact technology identifiers present in the frozen V17 input.
    # The older generic labels (Wind/Solar_PV) silently returned all-zero VRE
    # evidence and produced low-information plots.
    vre_raw = _surviving_capacity(
        gen,
        pred,
        2023,
        ["Wind_Onshore", "Wind_Offshore", "Solar_Distributed", "Solar_Utility"],
    )
    if vre_raw.empty:
        raise ValueError("No surviving 2023 VRE capacity found in frozen V17 inputs")
    vre_pivot = (
        vre_raw.pivot_table(
            index="gen_load_zone",
            columns="gen_tech",
            values="build_gen_predetermined",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
        .rename(columns={"gen_load_zone": "model_zone"})
    )
    for technology in ["Wind_Onshore", "Wind_Offshore", "Solar_Distributed", "Solar_Utility"]:
        if technology not in vre_pivot.columns:
            vre_pivot[technology] = 0.0
    vre = vre_pivot[["model_zone"]].copy()
    vre["wind_capacity_2023_mw"] = (
        vre_pivot["Wind_Onshore"] + vre_pivot["Wind_Offshore"]
    )
    vre["solar_capacity_2023_mw"] = (
        vre_pivot["Solar_Distributed"] + vre_pivot["Solar_Utility"]
    )

    nodes = (
        coordinates.merge(observed, on="model_zone", how="left", validate="one_to_one")
        .merge(peak_2023, on="model_zone", how="left", validate="one_to_one")
        .merge(vre, on="model_zone", how="left", validate="one_to_one")
    )
    critical = [
        "existing_new_storage_power_mw",
        "existing_new_storage_energy_mwh",
        "coincident_peak_2023_mw",
    ]
    if nodes[critical].isna().any().any():
        bad = nodes.loc[nodes[critical].isna().any(axis=1), "model_zone"].tolist()
        raise ValueError(f"Incomplete input evidence for model zones: {bad}")
    nodes["wind_capacity_2023_mw"] = nodes["wind_capacity_2023_mw"].fillna(0.0)
    nodes["solar_capacity_2023_mw"] = nodes["solar_capacity_2023_mw"].fillna(0.0)
    nodes["existing_duration_h"] = (
        nodes["existing_new_storage_energy_mwh"]
        / nodes["existing_new_storage_power_mw"].replace(0, np.nan)
    )
    nodes["storage_to_peak_ratio"] = (
        nodes["existing_new_storage_power_mw"] / nodes["coincident_peak_2023_mw"]
    )
    nodes["wind_solar_capacity_2023_mw"] = (
        nodes["wind_capacity_2023_mw"] + nodes["solar_capacity_2023_mw"]
    )

    edges = lines[
        [
            "TRANSMISSION_LINE",
            "trans_lz1",
            "trans_lz2",
            "existing_trans_cap",
            "trans_new_build_cap",
            "trans_efficiency",
        ]
    ].rename(
        columns={
            "trans_lz1": "zone_from",
            "trans_lz2": "zone_to",
            "existing_trans_cap": "existing_capacity_mw",
            "trans_new_build_cap": "new_build_cap_mw",
        }
    )

    design = master[master["scenario"].isin(CORE)][
        [
            "scenario",
            "legacy_allocation_mode",
            "legacy_pair_id",
            "legacy_context",
            "description",
            "v17_claim_scope",
        ]
    ].copy()
    design["scenario_order"] = design["scenario"].map({s: i for i, s in enumerate(CORE)})
    design = design.sort_values("scenario_order")
    features = design["legacy_allocation_mode"].map(_scenario_features).apply(pd.Series)
    design = pd.concat([design.reset_index(drop=True), features.reset_index(drop=True)], axis=1)

    power = nodes["existing_new_storage_power_mw"]
    total_power = float(power.sum())
    total_energy = float(nodes["existing_new_storage_energy_mwh"].sum())
    concentration = pd.DataFrame(
        [
            {
                "national_power_mw": total_power,
                "national_energy_mwh": total_energy,
                "national_average_duration_h": total_energy / total_power,
                "top5_power_share": float(power.nlargest(5).sum() / total_power),
                "herfindahl_hirschman_index": float(((power / total_power) ** 2).sum()),
                "maximum_storage_to_peak_ratio": float(nodes["storage_to_peak_ratio"].max()),
                "p95_storage_to_peak_ratio": float(
                    nodes["storage_to_peak_ratio"].quantile(0.95)
                ),
            }
        ]
    )
    return {
        "fig1_nodes": nodes,
        "fig1_edges": edges,
        "fig1_scenario_design": design,
        "fig1_concentration": concentration,
    }


def _installed_from_builds(
    build: pd.DataFrame, gen_meta: pd.DataFrame, periods: list[int]
) -> pd.DataFrame:
    _require_columns(
        build,
        {"GENERATION_PROJECT", "province", "technology", "build_year", "BuildGen"},
        "BuildGen.csv",
    )
    frame = build.merge(
        gen_meta[["GENERATION_PROJECT", "gen_max_age"]],
        on="GENERATION_PROJECT",
        how="left",
        validate="many_to_one",
    )
    if frame["gen_max_age"].isna().any():
        raise ValueError("BuildGen.csv contains projects absent from gen_info.csv")
    frame["build_year"] = pd.to_numeric(frame["build_year"], errors="raise").astype(int)
    frame["gen_max_age"] = pd.to_numeric(frame["gen_max_age"], errors="raise")
    frame["BuildGen"] = pd.to_numeric(frame["BuildGen"], errors="raise").fillna(0.0)
    rows: list[dict[str, object]] = []
    for period in periods:
        active = frame[
            (frame["build_year"] <= period)
            & (period < frame["build_year"] + frame["gen_max_age"])
        ]
        grouped = active.groupby(["province", "technology"], as_index=False)["BuildGen"].sum()
        for row in grouped.itertuples(index=False):
            rows.append(
                {
                    "period": period,
                    "province": row.province,
                    "technology": row.technology,
                    "installed_power_mw": float(row.BuildGen),
                }
            )
    return pd.DataFrame(rows)


def _installed_energy(
    build_energy: pd.DataFrame, gen_meta: pd.DataFrame, periods: list[int]
) -> pd.DataFrame:
    _require_columns(
        build_energy,
        {"GENERATION_PROJECT", "province", "technology", "build_year"},
        "BuildStorageEnergy.csv",
    )
    value_column = (
        "BuildStorageEnergy_MWh"
        if "BuildStorageEnergy_MWh" in build_energy.columns
        else "BuildStorageEnergy"
    )
    if value_column not in build_energy.columns:
        raise ValueError("BuildStorageEnergy.csv has no energy-build value column")
    frame = build_energy.merge(
        gen_meta[["GENERATION_PROJECT", "gen_max_age"]],
        on="GENERATION_PROJECT",
        how="left",
        validate="many_to_one",
    )
    if frame["gen_max_age"].isna().any():
        raise ValueError("BuildStorageEnergy.csv contains projects absent from gen_info.csv")
    frame["build_year"] = pd.to_numeric(frame["build_year"], errors="raise").astype(int)
    frame["gen_max_age"] = pd.to_numeric(frame["gen_max_age"], errors="raise")
    frame[value_column] = pd.to_numeric(frame[value_column], errors="raise").fillna(0.0)
    rows: list[dict[str, object]] = []
    for period in periods:
        active = frame[
            (frame["build_year"] <= period)
            & (period < frame["build_year"] + frame["gen_max_age"])
        ]
        grouped = active.groupby(["province", "technology"], as_index=False)[
            value_column
        ].sum()
        for row in grouped.itertuples(index=False):
            rows.append(
                {
                    "period": period,
                    "province": row.province,
                    "technology": row.technology,
                    "installed_energy_mwh": float(getattr(row, value_column)),
                }
            )
    return pd.DataFrame(rows)


def _period_metrics(
    outputs: Path, scenario: str, gen_meta: pd.DataFrame, periods: list[int]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cost = _read_output(outputs, scenario, "electricity_cost.csv")
    build = _read_output(outputs, scenario, "BuildGen.csv")
    energy = _read_output(outputs, scenario, "BuildStorageEnergy.csv")
    transmission = _read_output(outputs, scenario, "BuildTx.csv")
    curtailment = _read_output(outputs, scenario, "vre_curtailment_annual.csv")

    cost["period"] = pd.to_numeric(cost["period"], errors="raise").astype(int)
    installed = _installed_from_builds(build, gen_meta, periods)
    installed_energy = _installed_energy(energy, gen_meta, periods)

    national_power = installed.groupby(["period", "technology"], as_index=False)[
        "installed_power_mw"
    ].sum()
    national_energy = installed_energy.groupby(
        ["period", "technology"], as_index=False
    )["installed_energy_mwh"].sum()
    wide_power = national_power.pivot(
        index="period", columns="technology", values="installed_power_mw"
    ).fillna(0.0)
    wide_power.columns = [f"installed_{str(c).lower()}_mw" for c in wide_power.columns]
    wide_power = wide_power.reset_index()
    wide_energy = national_energy.pivot(
        index="period", columns="technology", values="installed_energy_mwh"
    ).fillna(0.0)
    wide_energy.columns = [
        f"installed_{str(c).lower()}_energy_mwh" for c in wide_energy.columns
    ]
    wide_energy = wide_energy.reset_index()

    _require_columns(transmission, {"build_year", "BuildTx"}, "BuildTx.csv")
    transmission["build_year"] = pd.to_numeric(
        transmission["build_year"], errors="raise"
    ).astype(int)
    transmission["BuildTx"] = pd.to_numeric(
        transmission["BuildTx"], errors="raise"
    ).fillna(0.0)
    transmission_path = pd.DataFrame({"period": periods})
    transmission_path["cumulative_new_transmission_mw"] = [
        float(
            transmission.loc[
                (transmission["build_year"] >= 2028)
                & (transmission["build_year"] <= period),
                "BuildTx",
            ].sum()
        )
        for period in periods
    ]

    _require_columns(
        curtailment,
        {
            "period",
            "Potential_GWh_typical_yr",
            "Gen_GWh_typical_yr",
            "Curtail_GWh_typical_yr",
        },
        "vre_curtailment_annual.csv",
    )
    curtailment["period"] = pd.to_numeric(
        curtailment["period"], errors="raise"
    ).astype(int)
    annual_curtailment = curtailment.groupby("period", as_index=False)[
        ["Potential_GWh_typical_yr", "Gen_GWh_typical_yr", "Curtail_GWh_typical_yr"]
    ].sum()
    annual_curtailment["curtailment_rate"] = annual_curtailment[
        "Curtail_GWh_typical_yr"
    ] / annual_curtailment["Potential_GWh_typical_yr"].replace(0, np.nan)

    cost_columns = [
        "period",
        "SystemDemand_MWh",
        "SystemCost_annualized_usd_per_yr",
        "SystemCost_present_value_to_base_year",
        "NetAnnualEmissions_tCO2",
        "CarbonCap_tCO2_per_yr",
        "TotalGenCapacityCosts",
        "StorageEnergyFixedCost",
        "TxFixedCosts",
        "FuelCostsPerYear",
    ]
    _require_columns(cost, set(cost_columns), "electricity_cost.csv")
    period_metrics = (
        cost[cost_columns]
        .merge(wide_power, on="period", how="left", validate="one_to_one")
        .merge(wide_energy, on="period", how="left", validate="one_to_one")
        .merge(transmission_path, on="period", how="left", validate="one_to_one")
        .merge(annual_curtailment, on="period", how="left", validate="one_to_one")
    )
    period_metrics.insert(0, "scenario", scenario)
    installed.insert(0, "scenario", scenario)
    installed_energy.insert(0, "scenario", scenario)
    return period_metrics, installed, installed_energy


def _temporal_scope_table() -> pd.DataFrame:
    timeseries = _read_template_csv("timeseries.csv")
    operational = timeseries[pd.to_numeric(timeseries["ts_period"], errors="raise") >= 2028]
    periods = sorted(pd.to_numeric(operational["ts_period"], errors="raise").unique())
    durations = pd.to_numeric(operational["ts_duration_of_tp"], errors="raise").unique()
    tps = pd.to_numeric(operational["ts_num_tps"], errors="raise")
    if len(durations) != 1:
        raise ValueError("Operational representative blocks do not share one duration")
    days_per_period = operational.groupby("ts_period").size()
    if days_per_period.nunique() != 1:
        raise ValueError("Representative-day count varies across operational periods")
    representative_timepoints = int(tps.sum())
    return pd.DataFrame(
        [
            {
                "representative_timepoints": representative_timepoints,
                "operational_period_count": len(periods),
                "dispatch_block_hours": float(durations[0]),
                "representative_days_per_period": int(days_per_period.iloc[0]),
                "soc_linkage": "intraday cyclic within each representative day",
                "supported_claim": (
                    "capacity expansion, annual aggregate accounting and intraday "
                    "representative-block feasibility"
                ),
                "unsupported_claim": (
                    "chronological multi-day, weekly or seasonal shifting and unique "
                    "operating-mechanism attribution"
                ),
            }
        ]
    )


def build_result_tables(
    outputs: Path, master: pd.DataFrame, selected: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    gen, _, _, _, periods_frame = _base_metadata()
    periods = sorted(
        pd.to_numeric(periods_frame["INVESTMENT_PERIOD"], errors="raise")
        .astype(int)
        .tolist()
    )
    scenarios = selected["scenario"].astype(str).tolist()

    allocations: list[pd.DataFrame] = []
    period_frames: list[pd.DataFrame] = []
    installed_frames: list[pd.DataFrame] = []
    energy_frames: list[pd.DataFrame] = []
    solve_frames: list[pd.DataFrame] = []
    physical_frames: list[pd.DataFrame] = []

    for scenario in scenarios:
        allocation = _read_output(outputs, scenario, "legacy_storage_allocation_audit.csv")
        allocation.insert(0, "scenario", scenario)
        allocations.append(allocation)
        metrics, installed, energy = _period_metrics(outputs, scenario, gen, periods)
        period_frames.append(metrics)
        installed_frames.append(installed)
        energy_frames.append(energy)
        solve = _read_output(outputs, scenario, "solve_status.csv")
        solve.insert(0, "scenario_key", scenario)
        solve_frames.append(solve)
        physical = _read_output(outputs, scenario, "physical_audit_summary.csv")
        physical.insert(0, "scenario", scenario)
        physical_frames.append(physical)

    allocation = pd.concat(allocations, ignore_index=True)
    period_metrics = pd.concat(period_frames, ignore_index=True)
    installed = pd.concat(installed_frames, ignore_index=True)
    installed_energy = pd.concat(energy_frames, ignore_index=True)
    solve_audit = pd.concat(solve_frames, ignore_index=True)
    physical_audit = pd.concat(physical_frames, ignore_index=True)

    # Fig. 2: equal-total legacy allocation and model-zone delta.
    reference = allocation[allocation["scenario"].eq("SL01_OBSERVED_STANDARDIZED")][
        ["model_zone", "realized_legacy_power_mw", "realized_legacy_energy_mwh"]
    ].rename(
        columns={
            "realized_legacy_power_mw": "observed_standardized_power_mw",
            "realized_legacy_energy_mwh": "observed_standardized_energy_mwh",
        }
    )
    figure2 = allocation[allocation["scenario"].isin(CORE)].merge(
        reference, on="model_zone", how="left", validate="many_to_one"
    )
    figure2["delta_power_vs_observed_standardized_mw"] = (
        figure2["realized_legacy_power_mw"]
        - figure2["observed_standardized_power_mw"]
    )
    figure2["delta_energy_vs_observed_standardized_mwh"] = (
        figure2["realized_legacy_energy_mwh"]
        - figure2["observed_standardized_energy_mwh"]
    )

    # Fig. 3: scenario-level system outcomes.
    rows: list[dict[str, object]] = []
    final_period = max(periods)
    for scenario, group in period_metrics.groupby("scenario"):
        operational = group[group["period"] >= 2028].sort_values("period")
        if operational.empty:
            raise ValueError(f"No operational periods for {scenario}")
        final = operational[operational["period"].eq(final_period)]
        last = final.iloc[0] if len(final) == 1 else operational.iloc[-1]
        build = _read_output(outputs, scenario, "BuildGen.csv")
        build["build_year"] = pd.to_numeric(build["build_year"], errors="raise")
        build["BuildGen"] = pd.to_numeric(build["BuildGen"], errors="raise").fillna(0.0)
        future_build = build[build["build_year"] >= 2028]
        energy = _read_output(outputs, scenario, "BuildStorageEnergy.csv")
        energy["build_year"] = pd.to_numeric(energy["build_year"], errors="raise")
        energy_column = (
            "BuildStorageEnergy_MWh"
            if "BuildStorageEnergy_MWh" in energy.columns
            else "BuildStorageEnergy"
        )
        energy[energy_column] = pd.to_numeric(
            energy[energy_column], errors="raise"
        ).fillna(0.0)
        transmission = _read_output(outputs, scenario, "BuildTx.csv")
        transmission["build_year"] = pd.to_numeric(
            transmission["build_year"], errors="raise"
        )
        transmission["BuildTx"] = pd.to_numeric(
            transmission["BuildTx"], errors="raise"
        ).fillna(0.0)
        rows.append(
            {
                "scenario": scenario,
                "final_period": int(last["period"]),
                "cumulative_system_cost_pv_usd": float(
                    operational["SystemCost_present_value_to_base_year"].sum()
                ),
                "final_annual_system_cost_usd_per_yr": float(
                    last["SystemCost_annualized_usd_per_yr"]
                ),
                "future_battery_build_mw": float(
                    future_build.loc[
                        future_build["technology"].eq("Battery"), "BuildGen"
                    ].sum()
                ),
                "future_pumped_hydro_build_mw": float(
                    future_build.loc[
                        future_build["technology"].eq("Hydro_Pumped"), "BuildGen"
                    ].sum()
                ),
                "future_battery_energy_build_mwh": float(
                    energy.loc[
                        (energy["build_year"] >= 2028)
                        & energy["technology"].eq("Battery"),
                        energy_column,
                    ].sum()
                ),
                "future_transmission_build_mw": float(
                    transmission.loc[
                        transmission["build_year"] >= 2028, "BuildTx"
                    ].sum()
                ),
                "final_curtailment_gwh_per_yr": float(
                    last["Curtail_GWh_typical_yr"]
                ),
                "final_curtailment_rate": float(last["curtailment_rate"]),
                "final_net_emissions_tco2_per_yr": float(
                    last["NetAnnualEmissions_tCO2"]
                ),
            }
        )
    figure3 = pd.DataFrame(rows).merge(
        master[["scenario", "legacy_allocation_mode", "legacy_context", "description"]],
        on="scenario",
        how="left",
        validate="one_to_one",
    )

    def scenario_value(scenario: str, column: str) -> float:
        match = figure3.loc[figure3["scenario"].eq(scenario), column]
        if len(match) != 1:
            raise ValueError(f"Missing or duplicate scenario metric: {scenario}::{column}")
        return float(match.iloc[0])

    no_legacy_cost = scenario_value("SL03_NO_LEGACY", "cumulative_system_cost_pv_usd")
    observed_cost = scenario_value(
        "SL01_OBSERVED_STANDARDIZED", "cumulative_system_cost_pv_usd"
    )
    optimized_cost = scenario_value(
        "SL02_OPTIMAL_REALLOCATION", "cumulative_system_cost_pv_usd"
    )
    denominator = no_legacy_cost - optimized_cost
    alignment = (
        (no_legacy_cost - observed_cost) / denominator
        if abs(denominator) > 1e-9
        else np.nan
    )
    figure3["legacy_alignment_index"] = alignment
    figure3["spatial_misalignment_cost_usd"] = observed_cost - optimized_cost
    figure3["observed_legacy_realized_value_usd"] = no_legacy_cost - observed_cost
    figure3["maximum_reallocated_legacy_value_usd"] = no_legacy_cost - optimized_cost

    # Fig. 4: robust final-period installed battery capacity, not gross operation.
    zones = sorted(allocation["model_zone"].astype(str).unique())
    grid = pd.MultiIndex.from_product(
        [PAIR_SCENARIOS, zones], names=["scenario", "model_zone"]
    ).to_frame(index=False)
    final_power = installed[
        installed["period"].eq(final_period)
        & installed["technology"].eq("Battery")
        & installed["scenario"].isin(PAIR_SCENARIOS)
    ][["scenario", "province", "installed_power_mw"]].rename(
        columns={"province": "model_zone", "installed_power_mw": "final_installed_battery_power_mw"}
    )
    final_energy = installed_energy[
        installed_energy["period"].eq(final_period)
        & installed_energy["technology"].eq("Battery")
        & installed_energy["scenario"].isin(PAIR_SCENARIOS)
    ][["scenario", "province", "installed_energy_mwh"]].rename(
        columns={"province": "model_zone", "installed_energy_mwh": "final_installed_battery_energy_mwh"}
    )
    legacy_pair = allocation[allocation["scenario"].isin(PAIR_SCENARIOS)][
        ["scenario", "model_zone", "realized_legacy_power_mw", "realized_legacy_energy_mwh"]
    ]
    figure4 = (
        grid.merge(final_power, on=["scenario", "model_zone"], how="left", validate="one_to_one")
        .merge(final_energy, on=["scenario", "model_zone"], how="left", validate="one_to_one")
        .merge(legacy_pair, on=["scenario", "model_zone"], how="left", validate="one_to_one")
    )
    for column in [
        "final_installed_battery_power_mw",
        "final_installed_battery_energy_mwh",
        "realized_legacy_power_mw",
        "realized_legacy_energy_mwh",
    ]:
        figure4[column] = figure4[column].fillna(0.0)
    figure4["final_installed_duration_h"] = (
        figure4["final_installed_battery_energy_mwh"]
        / figure4["final_installed_battery_power_mw"].replace(0, np.nan)
    )
    observed_final = figure4[
        figure4["scenario"].eq("SL01_OBSERVED_STANDARDIZED")
    ][["model_zone", "final_installed_battery_power_mw", "final_installed_battery_energy_mwh"]].rename(
        columns={
            "final_installed_battery_power_mw": "observed_final_power_mw",
            "final_installed_battery_energy_mwh": "observed_final_energy_mwh",
        }
    )
    figure4 = figure4.merge(
        observed_final, on="model_zone", how="left", validate="many_to_one"
    )
    figure4["delta_final_power_vs_observed_mw"] = (
        figure4["final_installed_battery_power_mw"] - figure4["observed_final_power_mw"]
    )
    figure4["delta_final_energy_vs_observed_mwh"] = (
        figure4["final_installed_battery_energy_mwh"] - figure4["observed_final_energy_mwh"]
    )
    figure4["final_period"] = final_period

    # Fig. 5: period-resolved national transition paths.
    figure5 = period_metrics[
        period_metrics["scenario"].isin(CORE)
        & (period_metrics["period"] >= 2028)
    ].copy()

    # Fig. 6: exact reconstructed-standardized versus optimized pairs.
    pairs: list[tuple[str, str, str]] = [
        ("base", "SL01_OBSERVED_STANDARDIZED", "SL02_OPTIMAL_REALLOCATION")
    ]
    robustness = master[master["legacy_story_set"].eq("spatial_legacy_robustness")]
    for context, group in robustness.groupby("legacy_context"):
        observed = group[
            group["legacy_allocation_mode"].eq("observed_standardized")
        ]["scenario"].astype(str).tolist()
        optimized = group[
            group["legacy_allocation_mode"].eq("optimized_reallocation")
        ]["scenario"].astype(str).tolist()
        if len(observed) != 1 or len(optimized) != 1:
            raise ValueError(f"Robustness context {context} is not an exact pair")
        pairs.append((str(context), observed[0], optimized[0]))
    if {context for context, _, _ in pairs} != set(ROBUSTNESS_CONTEXT_ORDER):
        raise ValueError("Robustness context set is incomplete")

    metrics = [
        "cumulative_system_cost_pv_usd",
        "future_battery_build_mw",
        "future_pumped_hydro_build_mw",
        "future_battery_energy_build_mwh",
        "future_transmission_build_mw",
        "final_curtailment_gwh_per_yr",
        "final_curtailment_rate",
        "final_net_emissions_tco2_per_yr",
    ]
    indexed = figure3.set_index("scenario")
    pair_rows: list[dict[str, object]] = []
    for context, observed, optimized in pairs:
        for metric in metrics:
            observed_value = float(indexed.loc[observed, metric])
            optimized_value = float(indexed.loc[optimized, metric])
            difference = observed_value - optimized_value
            pair_rows.append(
                {
                    "legacy_context": context,
                    "observed_scenario": observed,
                    "optimal_scenario": optimized,
                    "metric": metric,
                    "observed_value": observed_value,
                    "optimal_value": optimized_value,
                    "observed_minus_optimal": difference,
                    "relative_difference_fraction": (
                        difference / abs(optimized_value)
                        if abs(optimized_value) > 1e-12
                        else np.nan
                    ),
                }
            )
    figure6 = pd.DataFrame(pair_rows)
    figure6["context_order"] = figure6["legacy_context"].map(
        {value: index for index, value in enumerate(ROBUSTNESS_CONTEXT_ORDER)}
    )

    supplementary = {
        "figS06_scenario_matrix": selected,
        "figS07_solver_audit": solve_audit,
        "figS10_province_allocation_deltas": figure2[
            figure2["scenario"].eq("SL02_OPTIMAL_REALLOCATION")
        ].copy(),
        "figS11_cost_decomposition": period_metrics[
            [
                "scenario",
                "period",
                "TotalGenCapacityCosts",
                "StorageEnergyFixedCost",
                "TxFixedCosts",
                "FuelCostsPerYear",
                "SystemCost_annualized_usd_per_yr",
            ]
        ],
        "figS12_curtailment_emissions": period_metrics[
            [
                "scenario",
                "period",
                "Curtail_GWh_typical_yr",
                "curtailment_rate",
                "NetAnnualEmissions_tCO2",
                "CarbonCap_tCO2_per_yr",
            ]
        ],
        "figS13_storage_capacity_duration": figure4.copy(),
        "figS14_transmission_sensitivity": figure6[
            figure6["legacy_context"].eq("tx_fixed")
        ],
        "figS15_ph_carbon_cost_robustness": figure6[
            figure6["legacy_context"].isin(
                ["ph_conservative", "carbon_tight", "battery_cost_low", "battery_cost_high"]
            )
        ],
        "figS16_temporal_scope": _temporal_scope_table(),
        "physical_audit_detail": physical_audit,
        "installed_power_by_zone_period": installed,
        "installed_energy_by_zone_period": installed_energy,
    }

    return {
        "fig2_spatial_allocation": figure2,
        "fig3_system_value": figure3,
        "fig4_future_storage_spatial_reconfiguration": figure4,
        "fig5_transition_paths": figure5,
        "fig6_robustness": figure6,
        **supplementary,
    }



def enrich_v17t5_tables(
    outputs: Path,
    tables: dict[str, pd.DataFrame],
    input_tables: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Derive high-information V17T5 figure tables without changing model results."""
    result = dict(tables)
    nodes = input_tables["fig1_nodes"].copy()
    allocation = tables["fig2_spatial_allocation"].copy()
    system_value = tables["fig3_system_value"].copy()
    transition = tables["fig5_transition_paths"].copy()
    robustness = tables["fig6_robustness"].copy()
    installed_power = tables["installed_power_by_zone_period"].copy()
    installed_energy = tables["installed_energy_by_zone_period"].copy()

    # Fig. 1: matched national shares and Lorenz evidence.
    nodes["storage_power_share"] = (
        nodes["existing_new_storage_power_mw"]
        / nodes["existing_new_storage_power_mw"].sum()
    )
    nodes["peak_demand_share"] = (
        nodes["coincident_peak_2023_mw"] / nodes["coincident_peak_2023_mw"].sum()
    )
    nodes["vre_capacity_share"] = (
        nodes["wind_solar_capacity_2023_mw"]
        / nodes["wind_solar_capacity_2023_mw"].sum()
    )
    nodes["storage_minus_peak_share_pp"] = 100 * (
        nodes["storage_power_share"] - nodes["peak_demand_share"]
    )
    nodes["storage_minus_vre_share_pp"] = 100 * (
        nodes["storage_power_share"] - nodes["vre_capacity_share"]
    )
    result["fig1_match_scatter"] = nodes[
        [
            "model_zone",
            "existing_new_storage_power_mw",
            "existing_new_storage_energy_mwh",
            "existing_duration_h",
            "coincident_peak_2023_mw",
            "wind_solar_capacity_2023_mw",
            "storage_power_share",
            "peak_demand_share",
            "vre_capacity_share",
            "storage_minus_peak_share_pp",
            "storage_minus_vre_share_pp",
        ]
    ].copy()

    ordered = nodes.sort_values("existing_new_storage_power_mw").reset_index(drop=True)
    shares = ordered["storage_power_share"].to_numpy(dtype=float)
    lorenz = pd.DataFrame(
        {
            "population_share": np.linspace(0.0, 1.0, len(ordered) + 1),
            "cumulative_storage_power_share": np.r_[0.0, np.cumsum(shares)],
        }
    )
    result["fig1_lorenz"] = lorenz

    # Fig. 2: system-value ladder anchored to no-legacy and optimized cases.
    scenario_order = [
        "SL03_NO_LEGACY",
        "SL00_OBSERVED_ACTUAL",
        "SL01_OBSERVED_STANDARDIZED",
        "SL04_RULE_LOAD",
        "SL05_RULE_VRE",
        "SL02_OPTIMAL_REALLOCATION",
    ]
    value = system_value.set_index("scenario")
    no_legacy_cost = float(value.loc["SL03_NO_LEGACY", "cumulative_system_cost_pv_usd"])
    optimized_value = float(
        no_legacy_cost
        - value.loc["SL02_OPTIMAL_REALLOCATION", "cumulative_system_cost_pv_usd"]
    )
    ladder_rows: list[dict[str, object]] = []
    for order, scenario in enumerate(scenario_order):
        cost = float(value.loc[scenario, "cumulative_system_cost_pv_usd"])
        realized = no_legacy_cost - cost
        ladder_rows.append(
            {
                "scenario": scenario,
                "scenario_order": order,
                "cumulative_system_cost_pv_usd": cost,
                "legacy_system_value_usd": realized,
                "value_retention_fraction": (
                    realized / optimized_value if abs(optimized_value) > 1e-12 else np.nan
                ),
                "cost_penalty_vs_optimized_usd": (
                    cost
                    - float(
                        value.loc[
                            "SL02_OPTIMAL_REALLOCATION",
                            "cumulative_system_cost_pv_usd",
                        ]
                    )
                ),
            }
        )
    result["fig2_value_ladder"] = pd.DataFrame(ladder_rows)

    # Fig. 3: annual cost-component differences and period PV contributions.
    pair = transition[transition["scenario"].isin(PAIR_SCENARIOS)].copy()
    wide = pair.pivot(index="period", columns="scenario")
    cost_columns = [
        "TotalGenCapacityCosts",
        "StorageEnergyFixedCost",
        "TxFixedCosts",
        "FuelCostsPerYear",
    ]
    rows: list[dict[str, object]] = []
    for period in sorted(pair["period"].unique()):
        obs = pair[
            pair["scenario"].eq("SL01_OBSERVED_STANDARDIZED")
            & pair["period"].eq(period)
        ].iloc[0]
        opt = pair[
            pair["scenario"].eq("SL02_OPTIMAL_REALLOCATION")
            & pair["period"].eq(period)
        ].iloc[0]
        obs_known = sum(float(obs[column]) for column in cost_columns)
        opt_known = sum(float(opt[column]) for column in cost_columns)
        obs_other = float(obs["SystemCost_annualized_usd_per_yr"]) - obs_known
        opt_other = float(opt["SystemCost_annualized_usd_per_yr"]) - opt_known
        row = {
            "period": int(period),
            "generation_capacity_cost_delta_usd_per_yr": float(obs["TotalGenCapacityCosts"] - opt["TotalGenCapacityCosts"]),
            "storage_energy_fixed_cost_delta_usd_per_yr": float(obs["StorageEnergyFixedCost"] - opt["StorageEnergyFixedCost"]),
            "transmission_fixed_cost_delta_usd_per_yr": float(obs["TxFixedCosts"] - opt["TxFixedCosts"]),
            "fuel_cost_delta_usd_per_yr": float(obs["FuelCostsPerYear"] - opt["FuelCostsPerYear"]),
            "other_system_cost_delta_usd_per_yr": obs_other - opt_other,
            "annual_system_cost_delta_usd_per_yr": float(obs["SystemCost_annualized_usd_per_yr"] - opt["SystemCost_annualized_usd_per_yr"]),
            "present_value_cost_delta_usd": float(obs["SystemCost_present_value_to_base_year"] - opt["SystemCost_present_value_to_base_year"]),
            "battery_power_delta_mw": float(obs["installed_battery_mw"] - opt["installed_battery_mw"]),
            "battery_energy_delta_mwh": float(obs["installed_battery_energy_mwh"] - opt["installed_battery_energy_mwh"]),
            "transmission_delta_mw": float(obs["cumulative_new_transmission_mw"] - opt["cumulative_new_transmission_mw"]),
            "curtailment_delta_gwh_per_yr": float(obs["Curtail_GWh_typical_yr"] - opt["Curtail_GWh_typical_yr"]),
        }
        component_sum = sum(
            row[column]
            for column in [
                "generation_capacity_cost_delta_usd_per_yr",
                "storage_energy_fixed_cost_delta_usd_per_yr",
                "transmission_fixed_cost_delta_usd_per_yr",
                "fuel_cost_delta_usd_per_yr",
                "other_system_cost_delta_usd_per_yr",
            ]
        )
        row["component_closure_error_usd_per_yr"] = component_sum - row["annual_system_cost_delta_usd_per_yr"]
        rows.append(row)
    result["fig3_compensatory_investment"] = pd.DataFrame(rows)

    def paired_zone_period(frame: pd.DataFrame, value_column: str, period: int) -> pd.DataFrame:
        group = frame[
            frame["scenario"].isin(PAIR_SCENARIOS)
            & frame["technology"].eq("Battery")
            & frame["period"].eq(period)
        ][["scenario", "province", value_column]]
        pivot = group.pivot_table(
            index="province", columns="scenario", values=value_column, aggfunc="sum", fill_value=0.0
        )
        for scenario in PAIR_SCENARIOS:
            if scenario not in pivot.columns:
                pivot[scenario] = 0.0
        pivot = pivot.reset_index().rename(columns={"province": "model_zone"})
        pivot["observed"] = pivot["SL01_OBSERVED_STANDARDIZED"]
        pivot["optimized"] = pivot["SL02_OPTIMAL_REALLOCATION"]
        pivot["observed_minus_optimized"] = pivot["observed"] - pivot["optimized"]
        return pivot[["model_zone", "observed", "optimized", "observed_minus_optimized"]]

    power_2028 = paired_zone_period(installed_power, "installed_power_mw", 2028).rename(
        columns={
            "observed": "observed_power_mw",
            "optimized": "optimized_power_mw",
            "observed_minus_optimized": "power_delta_mw",
        }
    )
    energy_2028 = paired_zone_period(installed_energy, "installed_energy_mwh", 2028).rename(
        columns={
            "observed": "observed_energy_mwh",
            "optimized": "optimized_energy_mwh",
            "observed_minus_optimized": "energy_delta_mwh",
        }
    )
    result["fig3_spatial_burden_2028"] = power_2028.merge(
        energy_2028, on="model_zone", how="outer", validate="one_to_one"
    ).fillna(0.0)

    # Fig. 4: half-L1 spatial mismatch persistence and correction classes.
    initial_opt = allocation[
        allocation["scenario"].eq("SL02_OPTIMAL_REALLOCATION")
    ][["model_zone", "delta_power_vs_observed_standardized_mw", "delta_energy_vs_observed_standardized_mwh"]].copy()
    initial_opt = initial_opt.rename(
        columns={
            "delta_power_vs_observed_standardized_mw": "optimized_minus_observed_power_mw",
            "delta_energy_vs_observed_standardized_mwh": "optimized_minus_observed_energy_mwh",
        }
    )
    initial_power = 0.5 * float(initial_opt["optimized_minus_observed_power_mw"].abs().sum())
    initial_energy = 0.5 * float(initial_opt["optimized_minus_observed_energy_mwh"].abs().sum())
    persistence_rows: list[dict[str, object]] = [
        {
            "period": 2023,
            "power_half_l1_mw": initial_power,
            "energy_half_l1_mwh": initial_energy,
            "power_persistence_fraction": 1.0,
            "energy_persistence_fraction": 1.0,
        }
    ]
    initial_zone_period = initial_opt.copy()
    initial_zone_period["period"] = 2023
    zone_period_rows: list[pd.DataFrame] = [
        initial_zone_period[
            [
                "period",
                "model_zone",
                "optimized_minus_observed_power_mw",
                "optimized_minus_observed_energy_mwh",
            ]
        ]
    ]
    periods = sorted(
        period
        for period in set(
            installed_power.loc[
                installed_power["scenario"].isin(PAIR_SCENARIOS)
                & installed_power["technology"].eq("Battery"),
                "period",
            ].astype(int)
        )
        if period >= 2028
    )
    for period in periods:
        p = paired_zone_period(installed_power, "installed_power_mw", period)
        e = paired_zone_period(installed_energy, "installed_energy_mwh", period)
        zone = p.merge(e, on="model_zone", suffixes=("_power", "_energy"), validate="one_to_one")
        zone["period"] = int(period)
        zone["optimized_minus_observed_power_mw"] = -zone["observed_minus_optimized_power"]
        zone["optimized_minus_observed_energy_mwh"] = -zone["observed_minus_optimized_energy"]
        zone_period_rows.append(
            zone[
                [
                    "period",
                    "model_zone",
                    "optimized_minus_observed_power_mw",
                    "optimized_minus_observed_energy_mwh",
                ]
            ]
        )
        power_half_l1 = 0.5 * float(zone["optimized_minus_observed_power_mw"].abs().sum())
        energy_half_l1 = 0.5 * float(zone["optimized_minus_observed_energy_mwh"].abs().sum())
        persistence_rows.append(
            {
                "period": int(period),
                "power_half_l1_mw": power_half_l1,
                "energy_half_l1_mwh": energy_half_l1,
                "power_persistence_fraction": power_half_l1 / initial_power if initial_power > 0 else np.nan,
                "energy_persistence_fraction": energy_half_l1 / initial_energy if initial_energy > 0 else np.nan,
            }
        )
    result["fig4_mismatch_persistence"] = pd.DataFrame(persistence_rows)
    zone_period = pd.concat(zone_period_rows, ignore_index=True)
    result["fig4_zone_period_deltas"] = zone_period

    final_period = int(zone_period["period"].max())
    final = zone_period[zone_period["period"].eq(final_period)][
        ["model_zone", "optimized_minus_observed_power_mw", "optimized_minus_observed_energy_mwh"]
    ].rename(
        columns={
            "optimized_minus_observed_power_mw": "final_power_delta_mw",
            "optimized_minus_observed_energy_mwh": "final_energy_delta_mwh",
        }
    )
    correction = initial_opt.merge(final, on="model_zone", how="left", validate="one_to_one").fillna(0.0)
    tolerance = max(initial_power, 1.0) * 1e-6

    def category(initial: float, final_value: float) -> str:
        if abs(initial) <= tolerance:
            return "near zero initially"
        if abs(final_value) <= 0.1 * abs(initial):
            return "substantially corrected"
        if np.sign(initial) != np.sign(final_value):
            return "reversal"
        if abs(final_value) < abs(initial):
            return "partly corrected"
        return "persistent or amplified"

    correction["correction_class"] = [
        category(float(i), float(f))
        for i, f in zip(
            correction["optimized_minus_observed_power_mw"],
            correction["final_power_delta_mw"],
        )
    ]
    correction["initial_sign"] = np.where(
        correction["optimized_minus_observed_power_mw"] >= 0,
        "initial optimized surplus",
        "initial optimized deficit",
    )
    correction["initial_absolute_power_mw"] = correction[
        "optimized_minus_observed_power_mw"
    ].abs()
    correction["final_period"] = final_period
    result["fig4_zone_correction"] = correction

    # Fig. 5: compact, non-zero robustness metrics for forest plots.
    selected_metrics = [
        "cumulative_system_cost_pv_usd",
        "future_battery_build_mw",
        "future_battery_energy_build_mwh",
        "future_transmission_build_mw",
        "final_curtailment_gwh_per_yr",
    ]
    result["fig5_robustness_effects"] = robustness[
        robustness["metric"].isin(selected_metrics)
    ].copy()

    # Supplementary line-level transmission evidence.
    tx_frames: list[pd.DataFrame] = []
    for scenario in PAIR_SCENARIOS:
        frame = _read_output(outputs, scenario, "BuildTx.csv")
        _require_columns(frame, {"TRANSMISSION_LINE", "build_year", "BuildTx"}, f"{scenario}/BuildTx.csv")
        frame = frame.rename(columns={"build_year": "period", "BuildTx": "build_tx_mw"})
        frame["scenario"] = scenario
        tx_frames.append(frame[["scenario", "TRANSMISSION_LINE", "period", "build_tx_mw"]])
    tx = pd.concat(tx_frames, ignore_index=True)
    tx_wide = tx.pivot_table(
        index=["TRANSMISSION_LINE", "period"],
        columns="scenario",
        values="build_tx_mw",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()
    for scenario in PAIR_SCENARIOS:
        if scenario not in tx_wide.columns:
            tx_wide[scenario] = 0.0
    tx_wide["observed_minus_optimized_mw"] = (
        tx_wide["SL01_OBSERVED_STANDARDIZED"]
        - tx_wide["SL02_OPTIMAL_REALLOCATION"]
    )
    result["figS11_transmission_line_differences"] = tx_wide

    # Supplementary technology-period national capacity differences.
    tech = installed_power[
        installed_power["scenario"].isin(PAIR_SCENARIOS)
        & installed_power["period"].ge(2028)
    ].groupby(["scenario", "period", "technology"], as_index=False)["installed_power_mw"].sum()
    tech_wide = tech.pivot_table(
        index=["period", "technology"],
        columns="scenario",
        values="installed_power_mw",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()
    for scenario in PAIR_SCENARIOS:
        if scenario not in tech_wide.columns:
            tech_wide[scenario] = 0.0
    tech_wide["observed_minus_optimized_mw"] = (
        tech_wide["SL01_OBSERVED_STANDARDIZED"]
        - tech_wide["SL02_OPTIMAL_REALLOCATION"]
    )
    result["figS09_technology_capacity_differences"] = tech_wide

    return result


def write_tables(
    tables: dict[str, pd.DataFrame], input_tables: dict[str, pd.DataFrame]
) -> dict[str, object]:
    TABLE_MAIN.mkdir(parents=True, exist_ok=True)
    TABLE_SUPP.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    mapping = {
        "fig1_nodes": "fig1a_legacy_nodes.csv",
        "fig1_edges": "fig1b_model_network_edges.csv",
        "fig1_scenario_design": "fig1c_scenario_design.csv",
        "fig1_concentration": "fig1d_legacy_concentration.csv",
        "fig2_spatial_allocation": "fig2_spatial_allocation.csv",
        "fig3_system_value": "fig3_system_value.csv",
        "fig4_future_storage_spatial_reconfiguration": (
            "fig4_future_storage_spatial_reconfiguration.csv"
        ),
        "fig5_transition_paths": "fig5_transition_paths.csv",
        "fig6_robustness": "fig6_robustness.csv",
        "fig1_match_scatter": "fig1b_storage_demand_resource_match.csv",
        "fig1_lorenz": "fig1c_storage_lorenz.csv",
        "fig2_value_ladder": "fig2b_legacy_value_ladder.csv",
        "fig3_compensatory_investment": "fig3a_compensatory_investment.csv",
        "fig3_spatial_burden_2028": "fig3b_spatial_burden_2028.csv",
        "fig4_mismatch_persistence": "fig4a_mismatch_persistence.csv",
        "fig4_zone_period_deltas": "fig4b_zone_period_deltas.csv",
        "fig4_zone_correction": "fig4c_zone_correction.csv",
        "fig5_robustness_effects": "fig5_robustness_effects.csv",
    }
    generated: list[str] = []
    for key, frame in input_tables.items():
        path = TABLE_MAIN / mapping[key]
        frame.to_csv(path, index=False)
        generated.append(str(path))
    for key, frame in tables.items():
        path = TABLE_MAIN / mapping[key] if key in mapping else TABLE_SUPP / f"{key}.csv"
        frame.to_csv(path, index=False)
        generated.append(str(path))

    main_nonempty = {
        filename: pd.read_csv(TABLE_MAIN / filename).shape[0] > 0
        for filename in mapping.values()
    }
    audit = {
        "version": "V17T5R6R8R5",
        "generated_table_count": len(generated),
        "generated_files": generated,
        "main_table_nonempty": main_nonempty,
        "all_nonempty_main": all(main_nonempty.values()),
        "gross_operation_table_used_in_confirmatory_figures": False,
    }
    (AUDIT_DIR / "spatial_legacy_figure_table_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not audit["all_nonempty_main"]:
        raise RuntimeError("At least one main figure table is empty")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs-dir", default=str(PROJECT_ROOT / "outputs"))
    parser.add_argument(
        "--scenario-set",
        default="spatial_legacy_full",
        choices=["spatial_legacy_full", "spatial_legacy_core", "spatial_legacy_robustness"],
    )
    parser.add_argument("--input-only", action="store_true")
    args = parser.parse_args()

    master = pd.read_csv(MASTER)
    selected = _official(master, args.scenario_set)
    input_tables = build_input_tables(master)
    if args.input_only:
        TABLE_MAIN.mkdir(parents=True, exist_ok=True)
        names = {
            "fig1_nodes": "fig1a_legacy_nodes.csv",
            "fig1_edges": "fig1b_model_network_edges.csv",
            "fig1_scenario_design": "fig1c_scenario_design.csv",
            "fig1_concentration": "fig1d_legacy_concentration.csv",
        }
        for key, frame in input_tables.items():
            frame.to_csv(TABLE_MAIN / names[key], index=False)
        print(json.dumps({"input_only": True, "table_count": len(names)}, indent=2))
        return

    outputs = Path(args.outputs_dir).resolve()
    tables = build_result_tables(outputs, master, selected)
    tables = enrich_v17t5_tables(outputs, tables, input_tables)
    summary = write_tables(tables, input_tables)
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key != "generated_files"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
