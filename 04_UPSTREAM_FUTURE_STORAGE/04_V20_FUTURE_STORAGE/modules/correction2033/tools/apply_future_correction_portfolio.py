#!/usr/bin/env python3
"""Apply the V19 Layer-A future-correction storage technology opportunity set.

Two scopes are supported:
- evidence_bounded: 10/24 h VRFB plus 10/24 h PSH. VRFB is treated as a
  generic electrochemical option without a province-specific natural-resource
  ceiling; PSH shares the existing zone-specific Hydro_Pumped resource ceiling
  enforced by the frozen Julia core.
- expanded_pressure_test: the full packaged PNNL 2033 portfolio, adding CAES
  and hydrogen candidates without province-specific resource bounds. This scope
  is explicitly a pressure test and is not eligible for province-level siting
  recommendations.

The underlying cost/performance rows are source-direct packaged inputs already
used in the V19 shared evidence ledger. No reverse calibration or
capacity target is introduced here.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRIMARY_TABLE = ROOT / "data" / "processed" / "future_correction_primary_portfolio_2033.csv"
EXPANDED_TABLE = ROOT / "data" / "processed" / "ldes_technology_portfolio_2033.csv"
CPI_U_2010 = 218.056
CPI_U_2023 = 304.702
DEFLATOR_2023_TO_2010 = CPI_U_2010 / CPI_U_2023
TARGET_YEAR = 2033
VALID_SCOPES = {"evidence_bounded", "expanded_pressure_test"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def apply(case_dir: str | Path, scope: str) -> dict:
    if scope not in VALID_SCOPES:
        raise ValueError(f"scope must be one of {sorted(VALID_SCOPES)}")
    case_dir = Path(case_dir)
    inp = case_dir / "inputs"
    table = PRIMARY_TABLE if scope == "evidence_bounded" else EXPANDED_TABLE
    spec = pd.read_csv(table)
    if spec["portfolio_tech"].duplicated().any():
        raise ValueError("Future-correction portfolio has duplicate technology-duration candidates")
    expected = 4 if scope == "evidence_bounded" else 8
    if len(spec) != expected:
        raise ValueError(f"Expected {expected} candidates for {scope}, found {len(spec)}")

    gen_path = inp / "gen_info.csv"
    cost_path = inp / "gen_build_costs.csv"
    gen = pd.read_csv(gen_path)
    costs = pd.read_csv(cost_path)
    for col in ["gen_overnight_cost", "gen_storage_energy_overnight_cost", "gen_fixed_om"]:
        costs[col] = pd.to_numeric(costs[col].replace(".", pd.NA), errors="coerce")

    # Idempotence: remove only correction-layer LDES rows, never the frozen base projects.
    gen = gen.loc[~gen["gen_tech"].astype(str).str.startswith("LDES_")].copy()
    costs = costs.loc[~costs["GENERATION_PROJECT"].astype(str).str.contains("-LDES_", regex=False)].copy()

    templates: dict[str, pd.DataFrame] = {}
    for tech in ["CAS", "Battery", "Hydro_Pumped"]:
        x = gen.loc[gen["gen_tech"].astype(str).eq(tech)].copy()
        templates[tech] = x.set_index("gen_load_zone", drop=False)
    zones = sorted(set(templates["Battery"].index.astype(str)))
    if len(zones) != 32:
        raise ValueError(f"Expected 32 model zones, found {len(zones)}")

    new_gen: list[dict] = []
    new_costs: list[dict] = []
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
        raise ValueError("Future-correction portfolio created duplicate generation projects")
    if costs[["GENERATION_PROJECT", "build_year"]].duplicated().any():
        raise ValueError("Future-correction portfolio created duplicate build-cost rows")
    gen.to_csv(gen_path, index=False)
    costs.to_csv(cost_path, index=False)

    audit = {
        "status": "PASS",
        "version": "V19_LAYER_A_FUTURE_CORRECTION_PORTFOLIO_2033",
        "scope": scope,
        "source": "PNNL Energy Storage Cost and Performance Database v2024 packaged source; 2033 non-LFP values conservatively hold the source-direct 2030 Point/100MW benchmark; no unsupported 2035 interpolation",
        "source_url": "https://www.pnnl.gov/projects/esgc-cost-performance",
        "source_table": table.relative_to(ROOT).as_posix(),
        "source_table_sha256": _sha256(table),
        "target_year": TARGET_YEAR,
        "candidate_count": int(len(spec)),
        "generation_project_rows_added": int(len(new_gen)),
        "candidate_technologies": spec.to_dict(orient="records"),
        "primary_claim_eligible": scope == "evidence_bounded",
        "unsupported_2035_interpolation_used": False,
        "post_2030_non_lfp_extrapolation_used": False,
        "siting_interpretation": (
            "VRFB is a generic electrochemical province-level option without a natural-resource ceiling; PSH shares the frozen zone-specific Hydro_Pumped ceiling."
            if scope == "evidence_bounded" else
            "Expanded CAES and hydrogen candidates lack province-specific resource ledgers and are pressure-test options only."
        ),
        "reverse_calibration_used": False,
        "capacity_target_used": False,
        "technology_choice_is_endogenous": True,
        "capacity_choice_is_endogenous": True,
        "province_choice_is_endogenous": True,
        "duration_choice_is_discrete_via_technology_duration_candidates": True,
    }
    audits = case_dir / "audits"
    audits.mkdir(exist_ok=True)
    (audits / "future_correction_portfolio_application.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return audit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    ap.add_argument("--scope", required=True, choices=sorted(VALID_SCOPES))
    args = ap.parse_args()
    print(json.dumps(apply(args.case_dir, args.scope), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
