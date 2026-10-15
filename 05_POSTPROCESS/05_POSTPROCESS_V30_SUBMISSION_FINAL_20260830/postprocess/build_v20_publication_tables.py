#!/usr/bin/env python3
"""Build V20 Layer A/B/C publication contracts from strict promoted outputs."""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from v17t5_paths import TABLE_V20, V20_ROOT
from v30_common import (
    V20_LAYER_A_SCENARIOS,
    V20_LAYER_B_SCENARIOS,
    V20_LAYER_C_SCENARIOS,
    first_column,
    load_v20_layer_a_summary,
    load_v20_solver_summary,
    number,
    objective_column,
    read_one_csv,
    resolve_layer_a_output,
    resolve_v20_layer_a_root,
    resolve_v20_output,
    strict_v20_status,
    validate_v20_result_fingerprint,
    write_json,
)

TARGET_YEAR = 2033
PAIR_A = {
    "FC_BASE": ("FC01_BASE_OBSERVED", "FC02_BASE_OPTIMAL", "Baseline future set", True),
    "FC_ADAPTIVE": ("FC03_ADAPTIVE_OBSERVED", "FC04_ADAPTIVE_OPTIMAL", "Adaptive storage set", True),
    "FC_ADAPTIVE_TXFIXED": ("FC05_ADAPTIVE_TXFIXED_OBSERVED", "FC06_ADAPTIVE_TXFIXED_OPTIMAL", "Adaptive / TX fixed", False),
    "FC_EXPANDED_PRESSURE": ("FC07_EXPANDED_OBSERVED", "FC08_EXPANDED_OPTIMAL", "Expanded portfolio*", False),
}
PAIR_B = {
    "Core": ("SL01_OBSERVED_STANDARDIZED", "SL02_OPTIMAL_REALLOCATION"),
    "TX fixed": ("SL06_TX_FIXED_OBSERVED", "SL07_TX_FIXED_OPTIMAL"),
    "Conservative PSH": ("SL08_PH_CONSERVATIVE_OBSERVED", "SL09_PH_CONSERVATIVE_OPTIMAL"),
    "Tighter carbon cap": ("SL10_CARBON_TIGHT_OBSERVED", "SL11_CARBON_TIGHT_OPTIMAL"),
    "Low battery cost": ("SL12_COST_LOW_OBSERVED", "SL13_COST_LOW_OPTIMAL"),
    "High battery cost": ("SL14_COST_HIGH_OBSERVED", "SL15_COST_HIGH_OPTIMAL"),
}


def strict_output(path: Path, scenario: str, layer: str) -> dict:
    status = read_one_csv(path / "solve_status.csv")
    strict_v20_status(status, scenario, layer)
    if layer == "A":
        source_root = resolve_v20_layer_a_root(V20_ROOT)
        case_dir = source_root / "future_correction_cases" / scenario
    else:
        source_root = V20_ROOT
        case_dir = V20_ROOT / "storage_cases" / scenario
    validate_v20_result_fingerprint(source_root, path, case_dir, scenario)
    return status


def annual_cost(output: Path, scenario: str) -> float:
    frame = pd.read_csv(output / "electricity_cost.csv")
    period = first_column(frame, ["period", "PERIOD"])
    value = first_column(frame, ["SystemCost_annualized_usd_per_yr", "system_cost_annualized_usd_per_yr"])
    rows = frame.loc[pd.to_numeric(frame[period], errors="raise").eq(TARGET_YEAR)]
    if len(rows) != 1:
        raise ValueError(f"{scenario}: expected one {TARGET_YEAR} annual-cost row")
    return number(rows.iloc[0][value], field=f"{scenario}.annual_cost")


def technology_label(value: str) -> str:
    text = str(value)
    mapping = {"Battery": "Li-ion 4 h", "Hydro_Pumped": "Base PSH", "V18_LFP_4h": "LFP 4 h"}
    if text in mapping:
        return mapping[text]
    return (text.replace("LDES_VRFB_", "VRFB ").replace("LDES_PSH_", "PSH ")
            .replace("LDES_CAES_", "CAES ").replace("LDES_H2_", "H2 ")
            .replace("V18_VRFB_", "VRFB ").replace("V18_PSH_", "PSH ")
            .replace("V18_CAES_", "CAES ").replace("V18_H2_", "H2 "))


def is_declared_storage_technology(value: object) -> bool:
    text = str(value)
    return text in {"Battery", "Hydro_Pumped"} or text.startswith(("LDES_", "V18_LFP_", "V18_VRFB_", "V18_PSH_", "V18_CAES_", "V18_H2_"))


def layer_a_builds(output: Path, scenario: str) -> pd.DataFrame:
    module = resolve_v20_layer_a_root(V20_ROOT)
    gen_path = module / "future_correction_cases" / scenario / "inputs" / "gen_info.csv"
    if not gen_path.is_file():
        raise FileNotFoundError(f"{scenario}: prepared generator metadata missing: {gen_path}")
    gen_info = pd.read_csv(gen_path)
    g_project = first_column(gen_info, ["GENERATION_PROJECT", "generation_project"])
    g_tech = first_column(gen_info, ["gen_tech", "technology"])
    g_zone = first_column(gen_info, ["gen_load_zone", "province", "LOAD_ZONE"])
    lookup = gen_info[[g_project, g_tech, g_zone]].rename(columns={
        g_project: "GENERATION_PROJECT", g_tech: "technology", g_zone: "zone",
    })
    conflicts = lookup.groupby("GENERATION_PROJECT", dropna=False).agg(
        technologies=("technology", "nunique"), zones=("zone", "nunique")
    )
    if (conflicts[["technologies", "zones"]] > 1).any(axis=None):
        raise ValueError(f"{scenario}: generator project has conflicting technology/zone metadata")
    lookup = lookup.drop_duplicates("GENERATION_PROJECT")

    power = pd.read_csv(output / "BuildGen.csv")
    energy = pd.read_csv(output / "BuildStorageEnergy.csv")
    p_project = first_column(power, ["GENERATION_PROJECT", "generation_project"])
    p_year = first_column(power, ["build_year", "BUILD_YEAR", "period"])
    p_value = first_column(power, ["BuildGen", "build_gen", "value"])
    e_project = first_column(energy, ["GENERATION_PROJECT", "generation_project"])
    e_year = first_column(energy, ["build_year", "BUILD_YEAR", "period"])
    e_value = first_column(energy, ["BuildStorageEnergy_MWh", "BuildStorageEnergy", "build_storage_energy", "value"])
    p = power.loc[pd.to_numeric(power[p_year], errors="raise").eq(TARGET_YEAR), [p_project, p_year, p_value]].copy()
    e = energy.loc[pd.to_numeric(energy[e_year], errors="raise").eq(TARGET_YEAR), [e_project, e_year, e_value]].copy()
    p = p.rename(columns={p_project: "GENERATION_PROJECT", p_year: "build_year", p_value: "build_power_mw"})
    e = e.rename(columns={e_project: "GENERATION_PROJECT", e_year: "build_year", e_value: "build_energy_mwh"})
    keys = ["GENERATION_PROJECT", "build_year"]
    result = p.merge(e[[*keys, "build_energy_mwh"]], on=keys, how="outer", validate="one_to_one")
    result = result.merge(lookup, on="GENERATION_PROJECT", how="left", validate="many_to_one")
    if result[["technology", "zone"]].isna().any(axis=None):
        missing = result.loc[result[["technology", "zone"]].isna().any(axis=1), "GENERATION_PROJECT"].astype(str).unique().tolist()
        raise ValueError(f"{scenario}: project metadata lookup failed for {missing[:10]}")
    result[["build_power_mw", "build_energy_mwh"]] = result[["build_power_mw", "build_energy_mwh"]].fillna(0.0).apply(
        pd.to_numeric, errors="raise"
    )
    if (result[["build_power_mw", "build_energy_mwh"]] < -1.0e-6).any(axis=None):
        raise ValueError(f"{scenario}: materially negative storage build value")
    result[["build_power_mw", "build_energy_mwh"]] = result[["build_power_mw", "build_energy_mwh"]].clip(lower=0.0)
    result = result.loc[result["technology"].map(is_declared_storage_technology)].copy()
    result = result.loc[result["build_energy_mwh"].abs().gt(1e-9) | result["build_power_mw"].abs().gt(1e-9)].copy()
    result.insert(0, "scenario", scenario)
    result["technology_label"] = result["technology"].map(technology_label)
    result["build_power_gw"] = pd.to_numeric(result["build_power_mw"], errors="raise") / 1000.0
    result["build_energy_gwh"] = pd.to_numeric(result["build_energy_mwh"], errors="raise") / 1000.0
    result["duration_h"] = result["build_energy_mwh"] / result["build_power_mw"].where(result["build_power_mw"].abs().gt(1e-9))
    return result


def dynamic_builds(root: Path, scenarios: tuple[str, ...], label: str, layer: str) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for scenario in scenarios:
        output = resolve_v20_output(root, scenario)
        strict_output(output, scenario, layer)
        case = root / "storage_cases" / scenario
        gen_info = pd.read_csv(case / "inputs" / "gen_info.csv")
        power = pd.read_csv(output / "BuildGen.csv")
        energy = pd.read_csv(output / "BuildStorageEnergy.csv")
        gp = first_column(gen_info, ["GENERATION_PROJECT", "generation_project"])
        gt = first_column(gen_info, ["gen_tech", "technology"])
        gz = first_column(gen_info, ["gen_load_zone", "province", "LOAD_ZONE"])
        pp = first_column(power, ["GENERATION_PROJECT", "generation_project"])
        py = first_column(power, ["build_year", "BUILD_YEAR", "period"])
        pv = first_column(power, ["BuildGen", "build_gen", "value"])
        ep = first_column(energy, ["GENERATION_PROJECT", "generation_project"])
        ey = first_column(energy, ["build_year", "BUILD_YEAR", "period"])
        ev = first_column(energy, ["BuildStorageEnergy_MWh", "BuildStorageEnergy", "build_storage_energy", "value"])
        p = power[[pp, py, pv]].rename(columns={pp: "GENERATION_PROJECT", py: "build_year", pv: "new_power_mw"})
        e = energy[[ep, ey, ev]].rename(columns={ep: "GENERATION_PROJECT", ey: "build_year", ev: "new_energy_mwh"})
        lookup = gen_info[[gp, gt, gz]].rename(columns={gp: "GENERATION_PROJECT", gt: "technology", gz: "zone"})
        conflicts = lookup.groupby("GENERATION_PROJECT", dropna=False).agg(
            technologies=("technology", "nunique"), zones=("zone", "nunique")
        )
        if (conflicts[["technologies", "zones"]] > 1).any(axis=None):
            raise ValueError(f"{scenario}: generator project has conflicting technology/zone metadata")
        lookup = lookup.drop_duplicates("GENERATION_PROJECT")
        merged = p.merge(e, on=["GENERATION_PROJECT", "build_year"], how="outer", validate="one_to_one").merge(
            lookup, on="GENERATION_PROJECT", how="left", validate="many_to_one"
        )
        if merged[["technology", "zone"]].isna().any(axis=None):
            missing = merged.loc[merged[["technology", "zone"]].isna().any(axis=1), "GENERATION_PROJECT"].astype(str).unique().tolist()
            raise ValueError(f"{scenario}: project metadata lookup failed for {missing[:10]}")
        merged[["new_power_mw", "new_energy_mwh"]] = merged[["new_power_mw", "new_energy_mwh"]].fillna(0.0).apply(
            pd.to_numeric, errors="raise"
        )
        if (merged[["new_power_mw", "new_energy_mwh"]] < -1.0e-6).any(axis=None):
            raise ValueError(f"{scenario}: materially negative storage build value")
        merged[["new_power_mw", "new_energy_mwh"]] = merged[["new_power_mw", "new_energy_mwh"]].clip(lower=0.0)
        merged = merged.loc[merged["technology"].astype(str).str.startswith("V18_")].copy()
        merged = merged.loc[merged["new_power_mw"].abs().gt(1e-9) | merged["new_energy_mwh"].abs().gt(1e-9)].copy()
        years = pd.to_numeric(merged["build_year"], errors="raise")
        if not merged.empty and ((years < 2028) | (years > 2058)).any():
            raise ValueError(f"{scenario}: nonzero V18 build lies outside the declared 2028-2058 evidence horizon")
        merged.insert(0, "scenario", scenario); merged.insert(1, "evidence_regime", label)
        merged["technology_label"] = merged["technology"].map(technology_label)
        merged["new_power_gw"] = pd.to_numeric(merged["new_power_mw"], errors="raise") / 1000.0
        merged["new_energy_gwh"] = pd.to_numeric(merged["new_energy_mwh"], errors="raise") / 1000.0
        rows.append(merged)
    return pd.concat(rows, ignore_index=True)


def layer_a_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    outputs: dict[str, Path] = {}
    costs: dict[str, float] = {}
    builds: list[pd.DataFrame] = []
    for scenario in V20_LAYER_A_SCENARIOS:
        output = resolve_layer_a_output(V20_ROOT, scenario)
        strict_output(output, scenario, "A")
        outputs[scenario] = output
        costs[scenario] = annual_cost(output, scenario)
        builds.append(layer_a_builds(output, scenario))
    pair_rows: list[dict] = []
    for pair_id, (observed, optimal, label, eligible) in PAIR_A.items():
        penalty = costs[observed] - costs[optimal]
        pair_rows.append({
            "pair_id": pair_id, "pair_label": label, "observed_scenario": observed,
            "optimal_scenario": optimal, "observed_annual_cost_usd_per_yr": costs[observed],
            "optimal_annual_cost_usd_per_yr": costs[optimal], "legacy_penalty_usd_per_yr": penalty,
            "legacy_penalty_million_usd_per_yr": penalty / 1.0e6, "main_claim_eligible": eligible,
        })
    pairs = pd.DataFrame(pair_rows)
    base = float(pairs.loc[pairs.pair_id.eq("FC_BASE"), "legacy_penalty_usd_per_yr"].iloc[0])
    adaptive = float(pairs.loc[pairs.pair_id.eq("FC_ADAPTIVE"), "legacy_penalty_usd_per_yr"].iloc[0])
    if abs(base) <= 1e-12:
        raise ValueError("V20 Layer-A baseline legacy penalty is zero; repair fraction undefined")
    metrics = pd.DataFrame([
        {"metric": "Baseline residual legacy lock-in", "value": base / 1e6, "unit": "million USD yr-1"},
        {"metric": "Adaptive residual legacy lock-in", "value": adaptive / 1e6, "unit": "million USD yr-1"},
        {"metric": "Adaptive correction value", "value": (base - adaptive) / 1e6, "unit": "million USD yr-1"},
        {"metric": "Repair fraction", "value": (base - adaptive) / base, "unit": "fraction"},
    ])
    return pairs, pd.concat(builds, ignore_index=True), metrics


def main() -> None:
    layer_a_root = resolve_v20_layer_a_root(V20_ROOT)
    summary_a = load_v20_layer_a_summary(V20_ROOT)
    pairs_a, builds_a, metrics_a = layer_a_tables()
    summary_b = load_v20_solver_summary(V20_ROOT, "B")
    summary_c = load_v20_solver_summary(V20_ROOT, "C")
    obj_b = objective_column(summary_b); obj_c = objective_column(summary_c)
    map_b = {str(row["scenario"]): number(row[obj_b], field=f"{row['scenario']}.objective") for _, row in summary_b.iterrows()}
    map_c = {str(row["scenario"]): number(row[obj_c], field=f"{row['scenario']}.objective") for _, row in summary_c.iterrows()}
    pair_b_rows = []
    for label, (observed, optimal) in PAIR_B.items():
        penalty = map_b[observed] - map_b[optimal]
        pair_b_rows.append({"context": label, "observed_scenario": observed, "optimal_scenario": optimal,
                            "legacy_penalty_present_value_usd": penalty,
                            "legacy_penalty_billion_usd": penalty / 1.0e9})
    pair_b = pd.DataFrame(pair_b_rows)
    direct = map_b["SL01_OBSERVED_STANDARDIZED"] - map_b["SL02_OPTIMAL_REALLOCATION"]
    equal = map_c["V20EH01_OBSERVED"] - map_c["V20EH02_OPTIMAL"]
    horizon = pd.DataFrame([
        {"evidence_regime": "Evidence-direct", "legacy_penalty_present_value_usd": direct, "legacy_penalty_billion_usd": direct / 1.0e9},
        {"evidence_regime": "Equal horizon", "legacy_penalty_present_value_usd": equal, "legacy_penalty_billion_usd": equal / 1.0e9},
    ])
    builds_b = dynamic_builds(V20_ROOT, V20_LAYER_B_SCENARIOS, "evidence_direct", "B")
    builds_c = dynamic_builds(V20_ROOT, V20_LAYER_C_SCENARIOS, "equal_horizon", "C")

    presence_a = pd.DataFrame({"scenario": list(V20_LAYER_A_SCENARIOS)})
    counts = builds_a.groupby("scenario").size() if not builds_a.empty else pd.Series(dtype=int)
    presence_a["nonzero_storage_build_rows_2033"] = presence_a["scenario"].map(counts).fillna(0).astype(int)
    presence_a["zero_new_storage_is_valid"] = presence_a["nonzero_storage_build_rows_2033"].eq(0)

    TABLE_V20.mkdir(parents=True, exist_ok=True)
    pairs_a.to_csv(TABLE_V20 / "v20_layer_a_pair_costs.csv", index=False)
    builds_a.to_csv(TABLE_V20 / "v20_layer_a_storage_builds.csv", index=False)
    metrics_a.to_csv(TABLE_V20 / "v20_layer_a_correction_metrics.csv", index=False)
    summary_a.to_csv(TABLE_V20 / "v20_layer_a_8_strict_summary.csv", index=False)
    presence_a.to_csv(TABLE_V20 / "v20_layer_a_storage_build_presence.csv", index=False)
    summary_b.to_csv(TABLE_V20 / "v20_layer_b_16_strict_summary.csv", index=False)
    summary_c.to_csv(TABLE_V20 / "v20_layer_c_2_strict_summary.csv", index=False)
    pair_b.to_csv(TABLE_V20 / "v20_layer_b_context_penalties.csv", index=False)
    horizon.to_csv(TABLE_V20 / "v20_evidence_horizon_penalty.csv", index=False)
    builds_b.to_csv(TABLE_V20 / "v20_evidence_direct_build_by_year_zone_tech.csv", index=False)
    builds_c.to_csv(TABLE_V20 / "v20_equal_horizon_build_by_year_zone_tech.csv", index=False)
    write_json(TABLE_V20 / "V20_PUBLICATION_CONTRACT.json", {
        "version": "V30_V20_HF5_PUBLICATION_CONTRACT",
        "status": "PASS",
        "v20_root": str(V20_ROOT),
        "layer_a_root": str(layer_a_root),
        "required_cases": 26,
        "layer_a_strict": 8,
        "layer_b_strict": 16,
        "layer_c_strict": 2,
        "layer_a_cost_basis": "2033 annualized system cost; matched observed-minus-optimized comparison",
        "layer_b_cost_basis": "multi-period present-value objective; never added to Layer-A annualized cost",
        "chronology_boundary": "Layer A monthly-linked target year; Layer B/C V17-native intraday-cyclic representative chronology; FULL8760 handled only by the separate R24P3 certificate pipeline",
        "technology_claim_boundary": "Evidence-direct technology interpretation must remain qualitatively robust under equal-evidence-horizon and low/high battery-cost matched comparisons.",
        "expanded_portfolio_boundary": "CAES/H2 expanded case is pressure-test-only and not headline province siting evidence.",
        "unit_alignment": {
            "BuildGen": "upstream MW; divided exactly once by 1000 to report GW",
            "BuildStorageEnergy_MWh": "upstream MWh; divided exactly once by 1000 to report GWh",
            "duration": "upstream MWh divided by upstream MW, yielding hours",
            "layer_a_cost": "SystemCost_annualized_usd_per_yr; observed minus optimized; divided by 1e6 for million USD/yr",
            "layer_b_c_cost": "stage1_economic_objective_usd present value; observed minus optimized; divided by 1e9 for billion USD PV",
            "zero_build_policy": "A valid strict scenario with zero new storage remains an explicit zero, not missing data",
        },
    })
    print("V30 V20 publication tables: PASS")


if __name__ == "__main__":
    main()
