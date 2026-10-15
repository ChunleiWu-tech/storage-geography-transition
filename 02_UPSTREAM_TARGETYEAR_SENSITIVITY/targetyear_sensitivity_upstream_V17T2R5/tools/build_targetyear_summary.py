#!/usr/bin/env python3
"""Build publication-ready paired summaries for V17T2R5 target-year sensitivities."""
from __future__ import annotations

from pathlib import Path
import json
import math

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sensitivity_outputs"
SCEN = pd.read_csv(ROOT / "storage_runner" / "scenarios_targetyear_linked.csv")


def outdir(name: str) -> Path:
    return OUT / f"{name}__main"


def one_row(path: Path) -> dict:
    df = pd.read_csv(path)
    if len(df) != 1:
        raise ValueError(f"Expected one row in {path}")
    return df.iloc[0].to_dict()


def strict_status(name: str) -> dict:
    s = one_row(outdir(name) / "solve_status.csv")
    needed = {
        "stage1_termination_status": "OPTIMAL",
        "stage1_primal_status": "FEASIBLE_POINT",
        "stage1_dual_status": "FEASIBLE_POINT",
    }
    for k, v in needed.items():
        if str(s.get(k)) != v:
            raise ValueError(f"{name}: {k}={s.get(k)}, expected {v}")
    if str(s.get("strict_export_pass")).lower() not in {"true", "1"}:
        raise ValueError(f"{name}: strict_export_pass is false")
    return s


def annual_cost(name: str, target_year: int) -> float:
    df = pd.read_csv(outdir(name) / "electricity_cost.csv")
    row = df.loc[pd.to_numeric(df["period"], errors="raise").eq(target_year)]
    if len(row) != 1:
        raise ValueError(f"{name}: expected one electricity_cost row for {target_year}")
    value = float(row["SystemCost_annualized_usd_per_yr"].iloc[0])
    if not math.isfinite(value):
        raise ValueError(f"{name}: annual system cost is not finite")
    return value


def build_gen(name: str, target_year: int, technology: str) -> float:
    df = pd.read_csv(outdir(name) / "BuildGen.csv")
    mask = pd.to_numeric(df["build_year"], errors="raise").eq(target_year) & df["technology"].astype(str).eq(technology)
    return float(pd.to_numeric(df.loc[mask, "BuildGen"], errors="coerce").sum())


def build_storage_energy(name: str, target_year: int, technology: str) -> float:
    df = pd.read_csv(outdir(name) / "BuildStorageEnergy.csv")
    mask = pd.to_numeric(df["build_year"], errors="raise").eq(target_year) & df["technology"].astype(str).eq(technology)
    return float(pd.to_numeric(df.loc[mask, "BuildStorageEnergy_MWh"], errors="coerce").sum())


def build_tx(name: str, target_year: int) -> float:
    df = pd.read_csv(outdir(name) / "BuildTx.csv")
    mask = pd.to_numeric(df["build_year"], errors="raise").eq(target_year)
    value_col = "BuildTx" if "BuildTx" in df.columns else next(c for c in df.columns if c.lower().startswith("buildtx"))
    return float(pd.to_numeric(df.loc[mask, value_col], errors="coerce").sum())


def ldes(name: str) -> tuple[float, float]:
    p = outdir(name) / "ldes_proxy_build.csv"
    if not p.is_file():
        return 0.0, 0.0
    df = pd.read_csv(p)
    if df.empty:
        return 0.0, 0.0
    return (
        float(pd.to_numeric(df["build_power_mw"], errors="coerce").sum()),
        float(pd.to_numeric(df["build_energy_mwh"], errors="coerce").sum()),
    )


def legacy_map(name: str) -> pd.Series:
    df = pd.read_csv(outdir(name) / "legacy_storage_allocation_audit.csv")
    return df.set_index("model_zone")["realized_legacy_power_mw"].astype(float).sort_index()


def main() -> None:
    missing = [s for s in SCEN["scenario"].astype(str) if not (outdir(s) / "solve_status.csv").is_file()]
    if missing:
        raise SystemExit("Missing official outputs: " + ", ".join(missing))
    for s in SCEN["scenario"].astype(str):
        strict_status(s)

    rows = []
    maps = []
    for pair_id, grp in SCEN.groupby("pair_id", sort=True):
        obs = str(grp.loc[grp["legacy_allocation_mode"].eq("observed_standardized"), "scenario"].iloc[0])
        opt = str(grp.loc[grp["legacy_allocation_mode"].eq("optimized_reallocation"), "scenario"].iloc[0])
        year = int(grp["target_year"].iloc[0])
        oc, pc = annual_cost(obs, year), annual_cost(opt, year)
        obp, pbp = build_gen(obs, year, "Battery"), build_gen(opt, year, "Battery")
        obe, pbe = build_storage_energy(obs, year, "Battery"), build_storage_energy(opt, year, "Battery")
        olp, ole = ldes(obs)
        plp, ple = ldes(opt)
        otx, ptx = build_tx(obs, year), build_tx(opt, year)
        om, pm = legacy_map(obs), legacy_map(opt)
        delta = pm - om
        rows.append({
            "pair_id": pair_id,
            "target_year": year,
            "observed_scenario": obs,
            "optimized_scenario": opt,
            "observed_annual_system_cost_usd_per_yr": oc,
            "optimized_annual_system_cost_usd_per_yr": pc,
            "annual_location_penalty_usd_per_yr": oc - pc,
            "annual_location_penalty_billion_usd_per_yr": (oc - pc) / 1e9,
            "equivalent_legacy_power_reallocation_gw": 0.5 * float(delta.abs().sum()) / 1000.0,
            "observed_targetyear_battery_build_gw": obp / 1000.0,
            "optimized_targetyear_battery_build_gw": pbp / 1000.0,
            "observed_minus_optimized_battery_build_gw": (obp - pbp) / 1000.0,
            "observed_targetyear_battery_energy_gwh": obe / 1000.0,
            "optimized_targetyear_battery_energy_gwh": pbe / 1000.0,
            "observed_minus_optimized_battery_energy_gwh": (obe - pbe) / 1000.0,
            "observed_ldes_power_gw": olp / 1000.0,
            "optimized_ldes_power_gw": plp / 1000.0,
            "observed_ldes_energy_gwh": ole / 1000.0,
            "optimized_ldes_energy_gwh": ple / 1000.0,
            "observed_minus_optimized_tx_build_gw": (otx - ptx) / 1000.0,
            "claim_scope": str(grp["claim_scope"].iloc[0]),
        })
        map_df = pd.DataFrame({
            "model_zone": delta.index,
            "pair_id": pair_id,
            "target_year": year,
            "optimized_minus_observed_legacy_power_mw": delta.values,
        })
        maps.append(map_df)

    pair_df = pd.DataFrame(rows)
    pair_df.to_csv(OUT / "V17T2R5_targetyear_pair_summary.csv", index=False)
    pd.concat(maps, ignore_index=True).to_csv(OUT / "V17T2R5_targetyear_reallocation_by_zone.csv", index=False)

    base = pair_df.set_index("pair_id")
    attenuation = None
    if {"TY2033_CHRONO", "TY2033_CHRONO_LDES"} <= set(base.index):
        p0 = float(base.loc["TY2033_CHRONO", "annual_location_penalty_usd_per_yr"])
        p1 = float(base.loc["TY2033_CHRONO_LDES", "annual_location_penalty_usd_per_yr"])
        attenuation = {
            "2033_chronology_only_penalty_usd_per_yr": p0,
            "2033_chronology_ldes_penalty_usd_per_yr": p1,
            "ldes_absolute_change_usd_per_yr": p1 - p0,
            "ldes_attenuation_fraction": (p0 - p1) / p0 if abs(p0) > 1e-12 else None,
        }
    report = {
        "version": "V17T2R5",
        "design": "single-target-year exact linked-SOC capacity-and-dispatch re-optimization",
        "pairs": rows,
        "ldes_pressure_test": attenuation,
        "interpretation_lock": (
            "These are annual target-year robustness results. They do not replace, add to, or directly equal the "
            "multi-period present-value location penalty from the frozen main model. They test sign, mechanism, "
            "compensatory investment and LDES attenuation under linked representative-month SOC."
        ),
    }
    (OUT / "V17T2R5_targetyear_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
