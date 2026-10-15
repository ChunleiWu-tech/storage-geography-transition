#!/usr/bin/env python3
"""Build paired full-8760 results and an optional 4 h resolution comparison."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = pd.read_csv(ROOT / "storage_runner" / "scenarios_targetyear_linked.csv")
OUTROOT = ROOT / "sensitivity_outputs"


def outdir(root: Path, scenario: str) -> Path:
    return root / f"{scenario}__main"


def one_row(path: Path) -> dict:
    frame = pd.read_csv(path)
    if len(frame) != 1:
        raise ValueError(f"Expected one row in {path}")
    return frame.iloc[0].to_dict()


def strict_status(root: Path, scenario: str, full8760: bool) -> dict:
    status = one_row(outdir(root, scenario) / "solve_status.csv")
    expected = {
        "stage1_termination_status": "OPTIMAL",
        "stage1_primal_status": "FEASIBLE_POINT",
        "stage1_dual_status": "FEASIBLE_POINT",
    }
    for field, value in expected.items():
        if str(status.get(field)) != value:
            raise ValueError(f"{scenario}: {field}={status.get(field)}, expected {value}")
    if str(status.get("strict_export_pass")).lower() not in {"true", "1"}:
        raise ValueError(f"{scenario}: strict_export_pass is false")
    if full8760:
        if str(status.get("storage_chronology_mode")) != "full_year_cyclic":
            raise ValueError(f"{scenario}: not a full_year_cyclic solution")
        if int(float(status.get("representative_timepoint_count", -1))) != 8760:
            raise ValueError(f"{scenario}: not an 8760-timepoint solution")
    return status


def period_row(path: Path, target_year: int) -> dict:
    frame = pd.read_csv(path)
    column = "period" if "period" in frame.columns else "PERIOD"
    row = frame.loc[pd.to_numeric(frame[column], errors="raise").eq(target_year)]
    if len(row) != 1:
        raise ValueError(f"Expected one {target_year} row in {path}")
    return row.iloc[0].to_dict()


def build_value(root: Path, scenario: str, year: int, technology: str, energy: bool = False) -> float:
    filename = "BuildStorageEnergy.csv" if energy else "BuildGen.csv"
    frame = pd.read_csv(outdir(root, scenario) / filename)
    value_col = "BuildStorageEnergy_MWh" if energy else "BuildGen"
    mask = pd.to_numeric(frame["build_year"], errors="raise").eq(year) & frame["technology"].astype(str).eq(technology)
    return float(pd.to_numeric(frame.loc[mask, value_col], errors="coerce").sum())


def tx_value(root: Path, scenario: str, year: int) -> float:
    frame = pd.read_csv(outdir(root, scenario) / "BuildTx.csv")
    mask = pd.to_numeric(frame["build_year"], errors="raise").eq(year)
    col = "BuildTx" if "BuildTx" in frame.columns else next(c for c in frame if c.lower().startswith("buildtx"))
    return float(pd.to_numeric(frame.loc[mask, col], errors="coerce").sum())


def ldes_value(root: Path, scenario: str) -> tuple[float, float]:
    path = outdir(root, scenario) / "ldes_proxy_build.csv"
    frame = pd.read_csv(path)
    if frame.empty:
        return 0.0, 0.0
    return (
        float(pd.to_numeric(frame["build_power_mw"], errors="coerce").sum()),
        float(pd.to_numeric(frame["build_energy_mwh"], errors="coerce").sum()),
    )


def curtailment(root: Path, scenario: str, year: int) -> tuple[float, float, float]:
    frame = pd.read_csv(outdir(root, scenario) / "vre_curtailment_annual.csv")
    frame = frame.loc[pd.to_numeric(frame["period"], errors="raise").eq(year)]
    potential = float(pd.to_numeric(frame["Potential_GWh_typical_yr"], errors="coerce").sum())
    curtailed = float(pd.to_numeric(frame["Curtail_GWh_typical_yr"], errors="coerce").sum())
    return potential, curtailed, curtailed / potential if potential > 0.0 else math.nan


def chronology_maxima(root: Path, scenario: str) -> dict[str, float]:
    frame = pd.read_csv(outdir(root, scenario) / "storage_chronology_audit.csv")
    result: dict[str, float] = {}
    for column in [
        "cyclic_closure_residual_mwh", "maximum_absolute_step_residual_mwh",
        "lower_bound_violation_mwh", "upper_bound_violation_mwh",
    ]:
        if column in frame.columns:
            result[column] = float(pd.to_numeric(frame[column], errors="coerce").abs().max())
    return result


def scenario_metrics(root: Path, scenario: str, year: int, full8760: bool) -> dict:
    strict_status(root, scenario, full8760)
    cost = period_row(outdir(root, scenario) / "electricity_cost.csv", year)
    carbon = period_row(outdir(root, scenario) / "carbon_cap_compliance_audit.csv", year)
    ldes_power, ldes_energy = ldes_value(root, scenario)
    potential, curtailed, curtail_rate = curtailment(root, scenario, year)
    return {
        "scenario": scenario,
        "annual_system_cost_usd_per_yr": float(cost["SystemCost_annualized_usd_per_yr"]),
        "system_demand_mwh_per_yr": float(cost["SystemDemand_MWh"]),
        "net_emissions_tco2_per_yr": float(carbon["ReportedNetAnnualEmissions_tCO2"]),
        "carbon_cap_tco2_per_yr": float(carbon["CarbonCap_tCO2_per_yr"]),
        "battery_build_mw": build_value(root, scenario, year, "Battery"),
        "battery_energy_build_mwh": build_value(root, scenario, year, "Battery", energy=True),
        "ldes_build_mw": ldes_power,
        "ldes_energy_build_mwh": ldes_energy,
        "transmission_build_mw": tx_value(root, scenario, year),
        "vre_potential_gwh_per_yr": potential,
        "vre_curtailment_gwh_per_yr": curtailed,
        "vre_curtailment_rate": curtail_rate,
        "chronology_residual_maxima": chronology_maxima(root, scenario) if full8760 else {},
    }


def pair_metrics(root: Path, observed: str, optimized: str, year: int, full8760: bool) -> dict:
    obs = scenario_metrics(root, observed, year, full8760)
    opt = scenario_metrics(root, optimized, year, full8760)
    penalty = obs["annual_system_cost_usd_per_yr"] - opt["annual_system_cost_usd_per_yr"]
    return {
        "observed": obs,
        "optimized": opt,
        "annual_location_penalty_usd_per_yr": penalty,
        "annual_location_penalty_billion_usd_per_yr": penalty / 1e9,
        "observed_minus_optimized_battery_build_gw": (obs["battery_build_mw"] - opt["battery_build_mw"]) / 1000.0,
        "observed_minus_optimized_battery_energy_build_gwh": (obs["battery_energy_build_mwh"] - opt["battery_energy_build_mwh"]) / 1000.0,
        "observed_minus_optimized_ldes_build_gw": (obs["ldes_build_mw"] - opt["ldes_build_mw"]) / 1000.0,
        "observed_minus_optimized_transmission_build_gw": (obs["transmission_build_mw"] - opt["transmission_build_mw"]) / 1000.0,
        "observed_minus_optimized_curtailment_gwh_per_yr": obs["vre_curtailment_gwh_per_yr"] - opt["vre_curtailment_gwh_per_yr"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-root", type=Path, help="Optional V17T2R5 target-year package root containing sensitivity_outputs")
    args = parser.parse_args()
    missing = [s for s in SCENARIOS["scenario"].astype(str) if not (outdir(OUTROOT, s) / "solve_status.csv").is_file()]
    if missing:
        raise SystemExit("Missing official full-8760 outputs: " + ", ".join(missing))

    pairs: dict[str, dict] = {}
    flat_rows: list[dict] = []
    for pair_id, group in SCENARIOS.groupby("pair_id", sort=True):
        observed = str(group.loc[group["legacy_allocation_mode"].eq("observed_standardized"), "scenario"].iloc[0])
        optimized = str(group.loc[group["legacy_allocation_mode"].eq("optimized_reallocation"), "scenario"].iloc[0])
        metrics = pair_metrics(OUTROOT, observed, optimized, 2033, True)
        pairs[str(pair_id)] = metrics
        flat_rows.append({
            "pair_id": str(pair_id),
            "observed_scenario": observed,
            "optimized_scenario": optimized,
            **{k: v for k, v in metrics.items() if k not in {"observed", "optimized"}},
        })

    resolution: list[dict] = []
    if args.reference_root:
        reference_outputs = args.reference_root.resolve() / "sensitivity_outputs"
        mapping = {
            "TY2033_FULL8760": ("TY2033_CHRONO_OBSERVED", "TY2033_CHRONO_OPTIMAL"),
            "TY2033_FULL8760_LDES": ("TY2033_CHRONO_LDES_OBSERVED", "TY2033_CHRONO_LDES_OPTIMAL"),
        }
        for full_pair, (obs4, opt4) in mapping.items():
            reference = pair_metrics(reference_outputs, obs4, opt4, 2033, False)
            full = pairs[full_pair]
            p4 = float(reference["annual_location_penalty_usd_per_yr"])
            p8760 = float(full["annual_location_penalty_usd_per_yr"])
            resolution.append({
                "pair_id": full_pair,
                "four_hour_location_penalty_usd_per_yr": p4,
                "full8760_location_penalty_usd_per_yr": p8760,
                "full8760_minus_four_hour_usd_per_yr": p8760 - p4,
                "penalty_sign_preserved": (p4 == 0.0 and p8760 == 0.0) or (p4 * p8760 > 0.0),
                "full8760_to_four_hour_ratio": p8760 / p4 if abs(p4) > 1e-12 else None,
            })

    OUTROOT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(flat_rows).to_csv(OUTROOT / "V17T2R6_FULL8760_pair_summary.csv", index=False)
    pd.DataFrame(resolution).to_csv(OUTROOT / "V17T2R6_FULL8760_resolution_comparison.csv", index=False)
    report = {
        "version": "V17T2R6_FULL8760",
        "status": "PASS_OFFICIAL_RESULTS_SUMMARIZED",
        "pairs": pairs,
        "four_hour_resolution_comparison": resolution,
        "interpretation_lock": (
            "The full-8760 runs are a static 2033 chronological robustness test. They preserve each template's annual demand, "
            "technology costs, network, carbon policy and inherited-storage total. They do not replace the multi-period main "
            "model and are not a historical 2024 replay. The key test is whether the observed-versus-optimized location-penalty "
            "sign and compensatory-investment mechanism survive continuous chronology."
        ),
    }
    (OUTROOT / "V17T2R6_FULL8760_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
