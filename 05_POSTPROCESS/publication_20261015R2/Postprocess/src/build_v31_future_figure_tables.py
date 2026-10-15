#!/usr/bin/env python3
"""Build audited, figure-ready V31 tables from the frozen V30 real-data bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


LAYER_A_PAIRS = [
    ("FC_BASE", "Baseline", "FC01_BASE_OBSERVED", "FC02_BASE_OPTIMAL"),
    ("FC_ADAPTIVE", "Adaptive", "FC03_ADAPTIVE_OBSERVED", "FC04_ADAPTIVE_OPTIMAL"),
    ("FC_ADAPTIVE_TXFIXED", "Adaptive\nfixed transmission", "FC05_ADAPTIVE_TXFIXED_OBSERVED", "FC06_ADAPTIVE_TXFIXED_OPTIMAL"),
    ("FC_EXPANDED_PRESSURE", "Expanded*", "FC07_EXPANDED_OBSERVED", "FC08_EXPANDED_OPTIMAL"),
]

CONTEXT_PAIRS = [
    ("Core", "SL01_OBSERVED_STANDARDIZED", "SL02_OPTIMAL_REALLOCATION"),
    ("TX fixed", "SL06_TX_FIXED_OBSERVED", "SL07_TX_FIXED_OPTIMAL"),
    ("Conservative PSH", "SL08_PH_CONSERVATIVE_OBSERVED", "SL09_PH_CONSERVATIVE_OPTIMAL"),
    ("Tighter carbon cap", "SL10_CARBON_TIGHT_OBSERVED", "SL11_CARBON_TIGHT_OPTIMAL"),
    ("Low battery cost", "SL12_COST_LOW_OBSERVED", "SL13_COST_LOW_OPTIMAL"),
    ("High battery cost", "SL14_COST_HIGH_OBSERVED", "SL15_COST_HIGH_OPTIMAL"),
    ("Equal horizon", "V20EH01_OBSERVED", "V20EH02_OPTIMAL"),
]

CONTEXT_DISPLAY = {
    "Core": "Reference",
    "TX fixed": "Transmission fixed",
    "Conservative PSH": "Pumped-storage constraint",
}

SHORT_LABELS = {
    "FC01_BASE_OBSERVED": "2033 base, observed", "FC02_BASE_OPTIMAL": "2033 base, optimized",
    "FC03_ADAPTIVE_OBSERVED": "2033 adaptive, observed", "FC04_ADAPTIVE_OPTIMAL": "2033 adaptive, optimized",
    "FC05_ADAPTIVE_TXFIXED_OBSERVED": "2033 transmission fixed, observed", "FC06_ADAPTIVE_TXFIXED_OPTIMAL": "2033 transmission fixed, optimized",
    "FC07_EXPANDED_OBSERVED": "2033 expanded*, observed", "FC08_EXPANDED_OPTIMAL": "2033 expanded*, optimized",
    "SL00_OBSERVED_ACTUAL": "Actual inherited stock", "SL01_OBSERVED_STANDARDIZED": "Reference, observed",
    "SL02_OPTIMAL_REALLOCATION": "Reference, optimized", "SL03_NO_LEGACY": "Without inherited stock",
    "SL04_RULE_LOAD": "Load rule", "SL05_RULE_VRE": "Renewables rule",
    "SL06_TX_FIXED_OBSERVED": "Transmission fixed, observed", "SL07_TX_FIXED_OPTIMAL": "Transmission fixed, optimized",
    "SL08_PH_CONSERVATIVE_OBSERVED": "Pumped-storage constraint, observed", "SL09_PH_CONSERVATIVE_OPTIMAL": "Pumped-storage constraint, optimized",
    "SL10_CARBON_TIGHT_OBSERVED": "Carbon cap, observed", "SL11_CARBON_TIGHT_OPTIMAL": "Carbon cap, optimized",
    "SL12_COST_LOW_OBSERVED": "Low cost, observed", "SL13_COST_LOW_OPTIMAL": "Low cost, optimized",
    "SL14_COST_HIGH_OBSERVED": "High cost, observed", "SL15_COST_HIGH_OPTIMAL": "High cost, optimized",
    "V20EH01_OBSERVED": "Equal horizon, observed", "V20EH02_OPTIMAL": "Equal horizon, optimized",
}


def harmonize_technology(label: str) -> str:
    label = str(label)
    if label in {"LFP 4 h", "Li-ion 4 h"}:
        return "Li-ion/LFP 4 h"
    return label.replace("10h", "10 h").replace("24h", "24 h").replace("100h", "100 h")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Root containing tables/main and tables/future_storage")
    args = parser.parse_args()
    root = args.root.resolve()
    future = root / "tables" / "future_storage"
    out = root / "tables" / "future_storage_v31"
    audit_dir = root / "audits"
    out.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    builds_a = pd.read_csv(future / "v20_layer_a_storage_builds.csv")
    builds_b = pd.read_csv(future / "v20_evidence_direct_build_by_year_zone_tech.csv")
    builds_c = pd.read_csv(future / "v20_equal_horizon_build_by_year_zone_tech.csv")
    pair_costs = pd.read_csv(future / "v20_layer_a_pair_costs.csv").set_index("pair_id")
    context_costs = pd.read_csv(future / "v20_layer_b_context_penalties.csv").set_index("context")
    horizon_costs = pd.read_csv(future / "v20_evidence_horizon_penalty.csv").set_index("evidence_regime")
    nodes = pd.read_csv(root / "tables" / "main" / "fig1a_legacy_nodes.csv")

    failures: list[str] = []
    if builds_a.scenario.nunique() != 8 or builds_b.scenario.nunique() != 16 or builds_c.scenario.nunique() != 2:
        failures.append("source_case_count_not_8_16_2")

    # Layer-A pair metrics and zone geography.
    pair_rows = []
    for order, (pair_id, label, observed, optimized) in enumerate(LAYER_A_PAIRS):
        obs = builds_a.loc[builds_a.scenario.eq(observed)]
        opt = builds_a.loc[builds_a.scenario.eq(optimized)]
        obs_power, opt_power = float(obs.build_power_gw.sum()), float(opt.build_power_gw.sum())
        obs_energy, opt_energy = float(obs.build_energy_gwh.sum()), float(opt.build_energy_gwh.sum())
        obs_zone = obs.groupby("zone").build_power_gw.sum()
        opt_zone = opt.groupby("zone").build_power_gw.sum()
        difference = opt_zone.subtract(obs_zone, fill_value=0.0)
        pair_rows.append({
            "pair_order": order, "pair_id": pair_id, "pair_label": label,
            "observed_scenario": observed, "optimized_scenario": optimized,
            "observed_power_gw": obs_power, "optimized_power_gw": opt_power,
            "observed_energy_gwh": obs_energy, "optimized_energy_gwh": opt_energy,
            "observed_duration_h": obs_energy / obs_power, "optimized_duration_h": opt_energy / opt_power,
            "optimized_minus_observed_power_gw": opt_power - obs_power,
            "half_l1_reallocation_gw": 0.5 * float(difference.abs().sum()),
            "residual_penalty_million_usd_per_yr": float(pair_costs.loc[pair_id, "legacy_penalty_million_usd_per_yr"]),
        })
    pair_metrics = pd.DataFrame(pair_rows)
    pair_metrics.to_csv(out / "fig6_layer_a_pair_metrics.csv", index=False)

    adaptive = builds_a.loc[builds_a.scenario.isin(["FC03_ADAPTIVE_OBSERVED", "FC04_ADAPTIVE_OPTIMAL"])]
    zone = adaptive.groupby(["scenario", "zone"], as_index=False)[["build_power_gw", "build_energy_gwh"]].sum()
    parts = []
    for scenario, prefix in (("FC03_ADAPTIVE_OBSERVED", "observed"), ("FC04_ADAPTIVE_OPTIMAL", "optimized")):
        part = zone.loc[zone.scenario.eq(scenario), ["zone", "build_power_gw", "build_energy_gwh"]].copy()
        part = part.rename(columns={"build_power_gw": f"{prefix}_power_gw", "build_energy_gwh": f"{prefix}_energy_gwh"})
        parts.append(part)
    adaptive_zone = parts[0].merge(parts[1], on="zone", how="outer").fillna(0.0)
    for prefix in ("observed", "optimized"):
        adaptive_zone[f"{prefix}_duration_h"] = adaptive_zone[f"{prefix}_energy_gwh"].divide(
            adaptive_zone[f"{prefix}_power_gw"].replace(0.0, np.nan)
        )
    adaptive_zone["optimized_minus_observed_power_gw"] = adaptive_zone.optimized_power_gw - adaptive_zone.observed_power_gw
    adaptive_zone["abs_difference_gw"] = adaptive_zone.optimized_minus_observed_power_gw.abs()
    adaptive_zone = adaptive_zone.merge(nodes[["model_zone", "longitude", "latitude"]], left_on="zone", right_on="model_zone", how="left")
    if adaptive_zone[["longitude", "latitude"]].isna().any().any():
        failures.append("layer_a_zone_coordinate_missing")
    adaptive_zone.to_csv(out / "fig6_adaptive_zone_portfolios.csv", index=False)

    # Core Layer-B time and geography.
    core = builds_b.loc[builds_b.scenario.isin(["SL01_OBSERVED_STANDARDIZED", "SL02_OPTIMAL_REALLOCATION"])].copy()
    core["technology_group"] = core.technology_label.map(harmonize_technology)
    timing = core.groupby(["scenario", "build_year", "technology_group"], as_index=False).new_power_gw.sum()
    observed_timing = timing.loc[timing.scenario.eq("SL01_OBSERVED_STANDARDIZED")].rename(columns={"new_power_gw": "observed_power_gw"})
    optimized_timing = timing.loc[timing.scenario.eq("SL02_OPTIMAL_REALLOCATION")].rename(columns={"new_power_gw": "optimized_power_gw"})
    timing_wide = observed_timing[["build_year", "technology_group", "observed_power_gw"]].merge(
        optimized_timing[["build_year", "technology_group", "optimized_power_gw"]],
        on=["build_year", "technology_group"], how="outer",
    ).fillna(0.0)
    timing_wide["observed_minus_optimized_gw"] = timing_wide.observed_power_gw - timing_wide.optimized_power_gw
    timing_wide.to_csv(out / "fig7_core_timing_by_technology.csv", index=False)

    core_zone = core.groupby(["scenario", "zone"], as_index=False)[["new_power_gw", "new_energy_gwh"]].sum()
    core_parts = []
    for scenario, prefix in (("SL01_OBSERVED_STANDARDIZED", "observed"), ("SL02_OPTIMAL_REALLOCATION", "optimized")):
        part = core_zone.loc[core_zone.scenario.eq(scenario), ["zone", "new_power_gw", "new_energy_gwh"]].copy()
        part = part.rename(columns={"new_power_gw": f"{prefix}_power_gw", "new_energy_gwh": f"{prefix}_energy_gwh"})
        core_parts.append(part)
    core_zone_wide = core_parts[0].merge(core_parts[1], on="zone", how="outer").fillna(0.0)
    core_zone_wide["observed_minus_optimized_power_gw"] = core_zone_wide.observed_power_gw - core_zone_wide.optimized_power_gw
    core_zone_wide["abs_difference_gw"] = core_zone_wide.observed_minus_optimized_power_gw.abs()
    core_zone_wide = core_zone_wide.merge(nodes[["model_zone", "longitude", "latitude"]], left_on="zone", right_on="model_zone", how="left")
    if core_zone_wide[["longitude", "latitude"]].isna().any().any():
        failures.append("layer_b_zone_coordinate_missing")
    core_zone_wide.to_csv(out / "fig7_core_zone_difference.csv", index=False)

    # Seven matched contexts: 12 Layer-B cases plus both Layer-C cases.
    frames = {"B": builds_b, "C": builds_c}
    context_rows = []
    for order, (label, observed, optimized) in enumerate(CONTEXT_PAIRS):
        frame = frames["C"] if observed.startswith("V20EH") else frames["B"]
        obs = frame.loc[frame.scenario.eq(observed)]
        opt = frame.loc[frame.scenario.eq(optimized)]
        obs_power, opt_power = float(obs.new_power_gw.sum()), float(opt.new_power_gw.sum())
        obs_energy, opt_energy = float(obs.new_energy_gwh.sum()), float(opt.new_energy_gwh.sum())
        if label == "Equal horizon":
            penalty = float(horizon_costs.loc["Equal horizon", "legacy_penalty_billion_usd"])
        else:
            penalty = float(context_costs.loc[label, "legacy_penalty_billion_usd"])
        context_rows.append({
            "context_order": order, "context": CONTEXT_DISPLAY.get(label, label), "observed_scenario": observed, "optimized_scenario": optimized,
            "observed_power_gw": obs_power, "optimized_power_gw": opt_power,
            "observed_energy_gwh": obs_energy, "optimized_energy_gwh": opt_energy,
            "observed_duration_h": obs_energy / obs_power, "optimized_duration_h": opt_energy / opt_power,
            "observed_minus_optimized_power_gw": obs_power - opt_power,
            "legacy_penalty_billion_usd": penalty,
        })
    context_metrics = pd.DataFrame(context_rows)
    context_metrics.to_csv(out / "fig7_context_pair_metrics.csv", index=False)

    # All 26 strict cases on a common power/energy/technology/time basis.
    unified_parts = []
    for layer, frame, power, energy in (
        ("A", builds_a, "build_power_gw", "build_energy_gwh"),
        ("B", builds_b, "new_power_gw", "new_energy_gwh"),
        ("C", builds_c, "new_power_gw", "new_energy_gwh"),
    ):
        part = frame[["scenario", "build_year", "zone", "technology_label", power, energy]].copy()
        part = part.rename(columns={power: "power_gw", energy: "energy_gwh"})
        part["layer"] = layer
        part["technology_group"] = part.technology_label.map(harmonize_technology)
        unified_parts.append(part)
    unified = pd.concat(unified_parts, ignore_index=True)
    scenario_order = list(SHORT_LABELS)
    metrics = unified.groupby(["scenario", "layer"], as_index=False)[["power_gw", "energy_gwh"]].sum()
    metrics["duration_h"] = metrics.energy_gwh / metrics.power_gw.replace(0.0, np.nan)
    metrics["scenario_label"] = metrics.scenario.map(SHORT_LABELS)
    metrics["scenario_order"] = metrics.scenario.map({scenario: index for index, scenario in enumerate(scenario_order)})
    metrics = metrics.sort_values("scenario_order")
    metrics.to_csv(out / "figS14_all26_case_metrics.csv", index=False)

    technology = unified.groupby(["scenario", "layer", "technology_group"], as_index=False).power_gw.sum()
    technology = technology.merge(metrics[["scenario", "scenario_label", "scenario_order", "power_gw"]], on="scenario", suffixes=("", "_total"))
    technology["power_share_pct"] = 100.0 * technology.power_gw / technology.power_gw_total
    technology.sort_values(["scenario_order", "technology_group"]).to_csv(out / "figS14_all26_technology_shares.csv", index=False)

    timing_all = unified.groupby(["scenario", "layer", "build_year"], as_index=False).power_gw.sum()
    timing_all = timing_all.merge(metrics[["scenario", "scenario_label", "scenario_order", "power_gw"]], on="scenario", suffixes=("", "_total"))
    timing_all["power_share_pct"] = 100.0 * timing_all.power_gw / timing_all.power_gw_total
    timing_all.sort_values(["scenario_order", "build_year"]).to_csv(out / "figS14_all26_timing_shares.csv", index=False)

    if len(metrics) != 26 or metrics.scenario.nunique() != 26 or metrics.scenario_label.isna().any():
        failures.append("all26_case_identity_failed")
    if not np.isfinite(metrics[["power_gw", "energy_gwh", "duration_h"]].to_numpy(float)).all():
        failures.append("all26_metric_nonfinite")
    tech_closure = technology.groupby("scenario").power_share_pct.sum().sub(100.0).abs().max()
    time_closure = timing_all.groupby("scenario").power_share_pct.sum().sub(100.0).abs().max()
    if float(tech_closure) > 1.0e-8:
        failures.append(f"technology_share_closure:{tech_closure}")
    if float(time_closure) > 1.0e-8:
        failures.append(f"timing_share_closure:{time_closure}")

    report = {
        "version": "V31_FUTURE_STORAGE_FIGURE_TABLE_AUDIT_20260830",
        "status": "PASS" if not failures else "FAIL",
        "source_case_counts": {"layer_a": 8, "layer_b": 16, "layer_c": 2, "total": 26},
        "derived_tables": sorted(path.name for path in out.glob("*.csv")),
        "layer_a_pairs": len(pair_metrics), "matched_context_pairs": len(context_metrics),
        "all26_cases": len(metrics), "technology_share_max_closure_error_pct": float(tech_closure),
        "timing_share_max_closure_error_pct": float(time_closure),
        "source_values_modified": False, "unit_conversion_policy": "upstream GW/GWh retained; no repeated conversion",
        "failures": failures,
    }
    (audit_dir / "V31_FUTURE_STORAGE_FIGURE_TABLE_AUDIT.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
