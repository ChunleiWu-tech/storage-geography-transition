#!/usr/bin/env python3
"""Add a discrete, technology-specific 2033 LDES portfolio to one case.

The portfolio uses PNNL v2024 Point parameters at 100 MW. Values for 2033 are
linear interpolations between the packaged 2030 and 2035 rows. Each candidate
has a fixed duration, efficiency, lifetime, FOM and complete-system CAPEX.
Pumped-storage variants share the pre-existing provincial resource ceiling in
the Julia model; other technologies remain deliberately unconstrained pressure
tests because defensible province-level resource ledgers are unavailable.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "data" / "processed" / "ldes_technology_portfolio_2033.csv"
CPI_U_2010 = 218.056
CPI_U_2023 = 304.702
DEFLATOR_2023_TO_2010 = CPI_U_2010 / CPI_U_2023
TARGET_YEAR = 2033


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def apply(case_dir: str | Path) -> dict:
    case_dir = Path(case_dir)
    inp = case_dir / "inputs"
    spec = pd.read_csv(TABLE)
    if spec["portfolio_tech"].duplicated().any() or len(spec) != 8:
        raise ValueError("LDES portfolio must contain eight unique technology-duration candidates")

    gen_path = inp / "gen_info.csv"
    cost_path = inp / "gen_build_costs.csv"
    gen = pd.read_csv(gen_path)
    costs = pd.read_csv(cost_path)
    for col in ["gen_overnight_cost", "gen_storage_energy_overnight_cost", "gen_fixed_om"]:
        costs[col] = pd.to_numeric(costs[col].replace(".", pd.NA), errors="coerce")

    # Remove any prior portfolio rows to make the builder idempotent.
    gen = gen.loc[~gen["gen_tech"].astype(str).str.startswith("LDES_")].copy()
    costs = costs.loc[~costs["GENERATION_PROJECT"].astype(str).str.contains("-LDES_", regex=False)].copy()

    templates = {}
    for tech in ["CAS", "Battery", "Hydro_Pumped"]:
        x = gen.loc[gen["gen_tech"].astype(str).eq(tech)].copy()
        templates[tech] = x.set_index("gen_load_zone", drop=False)
    zones = sorted(set(templates["Battery"].index.astype(str)))
    if len(zones) != 32:
        raise ValueError(f"Expected 32 model zones, found {len(zones)}")

    new_gen = []
    new_costs = []
    for _, row in spec.iterrows():
        ptech = str(row["portfolio_tech"])
        base_tech = str(row["base_template_tech"])
        template = templates[base_tech]
        eligible_zones = zones if base_tech != "Hydro_Pumped" else sorted(template.index.astype(str).tolist())
        capex_2010_per_mw = float(row["total_installed_2023usd_per_kw"]) * DEFLATOR_2023_TO_2010 * 1000.0
        fom_2010_per_mw_y = float(row["fixed_om_2023usd_per_kw_year"]) * DEFLATOR_2023_TO_2010 * 1000.0
        for zone in eligible_zones:
            source = template.loc[zone].copy()
            project = f"{zone}-{ptech}"
            source["GENERATION_PROJECT"] = project
            source["gen_dbid"] = project
            source["gen_tech"] = ptech
            source["gen_energy_source"] = "Storage"
            source["gen_max_age"] = int(row["calendar_life_years"])
            source["gen_storage_efficiency"] = float(row["round_trip_efficiency"])
            source["gen_storage_energy_to_power_ratio"] = float(row["duration_h"])
            source["gen_capacity_limit_mw"] = "."
            source["gen_min_build_capacity"] = 0.0
            source["gen_connect_cost_per_mw"] = 0.0
            source["gen_variable_om"] = 0.0
            source["gen_is_pumped_hydro"] = False
            new_gen.append(source.to_dict())
            new_costs.append({
                "GENERATION_PROJECT": project,
                "build_year": TARGET_YEAR,
                "gen_overnight_cost": capex_2010_per_mw,
                "gen_storage_energy_overnight_cost": 0.0,
                "gen_fixed_om": fom_2010_per_mw_y,
                "gen_energy_source": "Storage",
            })
    gen = pd.concat([gen, pd.DataFrame(new_gen)], ignore_index=True)
    costs = pd.concat([costs, pd.DataFrame(new_costs)], ignore_index=True)
    if gen["GENERATION_PROJECT"].duplicated().any():
        raise ValueError("LDES portfolio created duplicate generation projects")
    if costs[["GENERATION_PROJECT", "build_year"]].duplicated().any():
        raise ValueError("LDES portfolio created duplicate build-cost rows")
    gen.to_csv(gen_path, index=False)
    costs.to_csv(cost_path, index=False)

    audit = {
        "status": "PASS",
        "version": "PNNL_V2024_DISCRETE_LDES_PORTFOLIO_2033_V1",
        "source": "PNNL Energy Storage Cost and Performance Database v2024 packaged in the user-supplied data archive",
        "source_url": "https://www.pnnl.gov/projects/esgc-cost-performance/download-reports",
        "source_table_sha256": _sha256(TABLE),
        "target_year": TARGET_YEAR,
        "source_currency_assumption": "2023 USD following the PNNL v2024 database description",
        "cpi_u_2010": CPI_U_2010,
        "cpi_u_2023": CPI_U_2023,
        "deflator_2023_to_2010": DEFLATOR_2023_TO_2010,
        "interpolation": "linear between packaged 2030 and 2035 Point rows",
        "candidate_count": int(len(spec)),
        "generation_project_rows_added": int(len(new_gen)),
        "technologies": spec.to_dict(orient="records"),
        "pumped_storage_resource_treatment": "10 h and 24 h variants share each zone's existing Hydro_Pumped capacity ceiling with the base pumped-storage project",
        "other_resource_treatment": "CAES, VRFB and hydrogen candidates have no province-specific resource ceiling and are pressure tests only",
        "reverse_calibration_used": False,
        "capacity_target_used": False,
        "continuous_generic_24_100h_proxy_used": False,
    }
    audits = case_dir / "audits"
    audits.mkdir(exist_ok=True)
    (audits / "ldes_technology_portfolio_application.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    args = ap.parse_args()
    print(json.dumps(apply(args.case_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
