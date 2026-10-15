#!/usr/bin/env python3
"""Apply the Storage V18 future technology-duration portfolio to one prepared case.

Design principles
-----------------
1. Preserve the observed 2025 Battery / Hydro_Pumped / CAS rows and all
   predetermined MW/MWh exactly.  They remain legacy stock only.
2. Add separate future-only V18 technology-duration candidates so future
   performance assumptions never rewrite the observed legacy fleet.
3. Li-ion LFP uses the scenario-specific NREL 2025 4 h trajectory already
   applied to the case, scaled by PNNL v2024 2030 duration cost ratios.
4. VRFB, CAES, hydrogen and PSH use PNNL v2024 Point / 100 MW values.  The
   2028 build block is linearly interpolated to 2028 between the two packaged
   PNNL reference years; 2033+ is frozen at the 2030 benchmark rather than
   extrapolated beyond the source horizon.
5. V18_PSH candidates share the existing zone-specific Hydro_Pumped resource
   ceiling in the Julia model. CAES and hydrogen are included in the input
   portfolio but disabled in headline evidence-bounded runs; they can be
   enabled only as explicit resource-unconstrained pressure tests.

All model costs remain in the inherited CHEER/SWITCH study convention of
2010 USD. PNNL database values are deflated with the same CPI-U convention
already frozen in the V17T2R5 target-year sensitivity package.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = ROOT / "data" / "processed" / "v18_storage_technology_portfolio.csv"
PNNL_ROWS = ROOT / "data" / "processed" / "pnnl_v2024_point_100mw_selected_storage.csv"
PNNL_WORKBOOK = ROOT / "shared_source_snapshots" / "official" / "PNNL_ESGC_Cost_Performance_Database_v2024.xlsx"

# Same CPI-U annual-average convention used by the frozen V17T2R5 target-year package.
CPI_U_2010 = 218.056
CPI_U_2023 = 304.702
DEFLATOR_2023_TO_2010 = CPI_U_2010 / CPI_U_2023
FUTURE_BUILD_YEARS = (2028, 2033, 2038, 2043, 2048, 2053, 2058)
V18_PREFIX = "V18_"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _num(x) -> float:
    if pd.isna(x) or str(x).strip() in {"", "."}:
        return math.nan
    return float(x)


def _pnnl_value(raw: pd.DataFrame, candidate: str, year: int, parameter: str) -> float:
    q = raw[
        raw["candidate_tech"].astype(str).eq(candidate)
        & pd.to_numeric(raw["Year"], errors="raise").astype(int).eq(int(year))
        & raw["Parameter"].astype(str).eq(parameter)
    ]
    if len(q) != 1:
        raise ValueError(f"Expected exactly one PNNL row for {candidate}, {year}, {parameter}; found {len(q)}")
    return float(q.iloc[0]["Value"])


def _pnnl_project_value(raw: pd.DataFrame, candidate: str, build_year: int, parameter: str) -> tuple[float, str]:
    q = raw[
        raw["candidate_tech"].astype(str).eq(candidate)
        & raw["Parameter"].astype(str).eq(parameter)
    ].copy()
    years = sorted(pd.to_numeric(q["Year"], errors="raise").astype(int).unique().tolist())
    if len(years) < 1:
        raise ValueError(f"No PNNL years for {candidate}/{parameter}")
    hi = max(y for y in years if y <= 2030) if any(y <= 2030 for y in years) else max(years)
    lo_candidates = [y for y in years if y < hi]
    lo = max(lo_candidates) if lo_candidates else hi
    if build_year >= hi or lo == hi:
        return _pnnl_value(raw, candidate, hi, parameter), f"freeze_{hi}"
    if build_year <= lo:
        return _pnnl_value(raw, candidate, lo, parameter), f"use_{lo}"
    vlo = _pnnl_value(raw, candidate, lo, parameter)
    vhi = _pnnl_value(raw, candidate, hi, parameter)
    w = (build_year - lo) / (hi - lo)
    return vlo + w * (vhi - vlo), f"linear_interp_{lo}_{hi}_to_{build_year}"


def _template_by_zone(gen: pd.DataFrame, tech: str) -> pd.DataFrame:
    q = gen.loc[gen["gen_tech"].astype(str).eq(tech)].copy()
    if q.empty:
        raise ValueError(f"No template technology {tech} in gen_info.csv")
    if q["gen_load_zone"].astype(str).duplicated().any():
        dup = q.loc[q["gen_load_zone"].astype(str).duplicated(), "gen_load_zone"].astype(str).tolist()
        raise ValueError(f"Template {tech} has duplicate zone rows: {dup[:10]}")
    return q.set_index(q["gen_load_zone"].astype(str), drop=False)


def apply(case_dir: str | Path) -> dict:
    case_dir = Path(case_dir)
    inp = case_dir / "inputs"
    gen_path = inp / "gen_info.csv"
    cost_path = inp / "gen_build_costs.csv"
    if not gen_path.exists() or not cost_path.exists():
        raise FileNotFoundError(f"Missing gen_info/gen_build_costs in {inp}")

    spec = pd.read_csv(PORTFOLIO)
    raw = pd.read_csv(PNNL_ROWS)
    gen = pd.read_csv(gen_path)
    costs = pd.read_csv(cost_path)

    if spec["portfolio_tech"].astype(str).duplicated().any():
        raise ValueError("V18 portfolio contains duplicate technology names")
    if len(spec) != 12:
        raise ValueError(f"V18 portfolio must contain 12 frozen candidates; found {len(spec)}")

    # Idempotence: remove only V18-generated rows, never legacy source rows.
    v18_projects = gen["gen_tech"].astype(str).str.startswith(V18_PREFIX, na=False)
    gen = gen.loc[~v18_projects].copy()
    costs = costs.loc[~costs["GENERATION_PROJECT"].astype(str).str.contains(f"-{V18_PREFIX}", regex=False)].copy()

    templates = {
        "Battery": _template_by_zone(gen, "Battery"),
        "CAS": _template_by_zone(gen, "CAS"),
        "Hydro_Pumped": _template_by_zone(gen, "Hydro_Pumped"),
    }
    all_zones = sorted(templates["Battery"].index.astype(str).tolist())
    if len(all_zones) != 32:
        raise ValueError(f"Expected 32 model zones from Battery template; found {len(all_zones)}")

    # NREL battery rows have already been applied by apply_scenario_mutations.py.
    battery_costs = costs[costs["GENERATION_PROJECT"].astype(str).str.endswith("-Battery")].copy()
    if battery_costs.empty:
        raise ValueError("No Battery build-cost rows found after NREL cost application")
    battery_costs["build_year"] = pd.to_numeric(battery_costs["build_year"], errors="raise").astype(int)

    pnnl_lfp_4h_capex = _pnnl_value(raw, "V18_LFP_4h", 2030, "Total Installed Cost ($/kW)")
    pnnl_lfp_4h_fom = _pnnl_value(raw, "V18_LFP_4h", 2030, "Fixed O&M ($/kW-year)")

    new_gen_rows: list[dict] = []
    new_cost_rows: list[dict] = []
    trajectory_rows: list[dict] = []

    for _, s in spec.iterrows():
        candidate = str(s["portfolio_tech"])
        base_tech = str(s["base_template_tech"])
        duration = float(s["duration_h"])
        template = templates[base_tech]
        eligible_zones = all_zones if base_tech != "Hydro_Pumped" else sorted(template.index.astype(str).tolist())

        for zone in eligible_zones:
            source = template.loc[zone].copy()
            project = f"{zone}-{candidate}"
            source["GENERATION_PROJECT"] = project
            source["gen_dbid"] = project
            source["gen_tech"] = candidate
            source["gen_energy_source"] = "Storage"
            source["gen_max_age"] = int(round(float(s["calendar_life_years"])))
            source["gen_storage_efficiency"] = float(s["round_trip_efficiency"])
            source["gen_storage_energy_to_power_ratio"] = duration
            source["gen_capacity_limit_mw"] = "."
            source["gen_min_build_capacity"] = 0.0
            source["gen_variable_om"] = 0.0
            if "gen_is_pumped_hydro" in source.index:
                # V18 PSH is modeled through the generic storage equations and
                # receives its physical site ceiling through a separate shared cap.
                source["gen_is_pumped_hydro"] = False
            new_gen_rows.append(source.to_dict())

            for y in FUTURE_BUILD_YEARS:
                if candidate.startswith("V18_LFP_"):
                    base_project = f"{zone}-Battery"
                    q = battery_costs[
                        battery_costs["GENERATION_PROJECT"].astype(str).eq(base_project)
                        & battery_costs["build_year"].eq(y)
                    ]
                    if len(q) != 1:
                        raise ValueError(f"Missing unique NREL Battery cost row for {base_project}/{y}")
                    qrow = q.iloc[0]
                    capex4 = float(qrow["gen_overnight_cost"])
                    fom4 = float(qrow["gen_fixed_om"])
                    pnnl_capex = float(s["total_installed_reference_usd_per_kw"])
                    pnnl_fom = float(s["fixed_om_reference_usd_per_kw_year"])
                    capex = capex4 * (pnnl_capex / pnnl_lfp_4h_capex)
                    fom = fom4 * (pnnl_fom / pnnl_lfp_4h_fom)
                    method = "NREL_2025_4h_case_trajectory_x_PNNL_2030_duration_ratio"
                else:
                    capex_ref, cap_method = _pnnl_project_value(raw, candidate, y, "Total Installed Cost ($/kW)")
                    fom_ref, fom_method = _pnnl_project_value(raw, candidate, y, "Fixed O&M ($/kW-year)")
                    capex = capex_ref * DEFLATOR_2023_TO_2010 * 1000.0
                    fom = fom_ref * DEFLATOR_2023_TO_2010 * 1000.0
                    method = f"PNNL_Point_100MW_{cap_method};FOM_{fom_method};CPIU_2023_to_2010"
                new_cost_rows.append({
                    "GENERATION_PROJECT": project,
                    "build_year": y,
                    "gen_overnight_cost": capex,
                    "gen_storage_energy_overnight_cost": 0.0,
                    "gen_fixed_om": fom,
                    "gen_energy_source": "Storage",
                })
                trajectory_rows.append({
                    "GENERATION_PROJECT": project,
                    "model_zone": zone,
                    "portfolio_tech": candidate,
                    "build_year": y,
                    "duration_h": duration,
                    "gen_overnight_cost_2010usd_per_mw": capex,
                    "gen_fixed_om_2010usd_per_mw_year": fom,
                    "cost_method": method,
                    "headline_eligibility": str(s["headline_eligibility"]),
                    "resource_treatment": str(s["resource_treatment"]),
                })

    gen = pd.concat([gen, pd.DataFrame(new_gen_rows)], ignore_index=True)
    costs = pd.concat([costs, pd.DataFrame(new_cost_rows)], ignore_index=True)

    if gen["GENERATION_PROJECT"].astype(str).duplicated().any():
        bad = gen.loc[gen["GENERATION_PROJECT"].astype(str).duplicated(keep=False), "GENERATION_PROJECT"].astype(str).tolist()
        raise ValueError(f"Duplicate generation project after V18 portfolio application: {bad[:20]}")
    if costs[["GENERATION_PROJECT", "build_year"]].astype(str).duplicated().any():
        raise ValueError("Duplicate generation-project/build-year rows after V18 portfolio application")

    gen.to_csv(gen_path, index=False)
    costs.to_csv(cost_path, index=False)

    # Resource ledger consumed by Julia. Only PSH carries a hard evidence-bounded
    # zone ceiling in the current V18 release. Other entries are explicit scope labels.
    ph = gen.loc[gen["gen_tech"].astype(str).eq("Hydro_Pumped")].copy()
    resource_rows = []
    for _, r in ph.iterrows():
        cap = _num(r["gen_capacity_limit_mw"])
        if math.isfinite(cap):
            resource_rows.append({
                "model_zone": str(r["gen_load_zone"]),
                "resource_family": "psh",
                "max_total_power_mw": cap,
                "constraint_status": "hard_shared_ceiling",
                "source": "inherited V17 Hydro_Pumped zone resource ceiling",
            })
    pd.DataFrame(resource_rows).to_csv(inp / "storage_resource_limits_v18.csv", index=False)

    audits = case_dir / "audits"
    audits.mkdir(exist_ok=True)
    traj = pd.DataFrame(trajectory_rows)
    traj.to_csv(audits / "v18_storage_candidate_cost_trajectory.csv", index=False)

    audit = {
        "status": "PASS",
        "version": "STORAGE_V18_TECH_DURATION_PORTFOLIO_V1",
        "source_workbook": str(PNNL_WORKBOOK.relative_to(ROOT)).replace("\\", "/"),
        "source_workbook_sha256": _sha256(PNNL_WORKBOOK),
        "processed_pnnl_rows": str(PNNL_ROWS.relative_to(ROOT)).replace("\\", "/"),
        "processed_pnnl_rows_sha256": _sha256(PNNL_ROWS),
        "portfolio_table": str(PORTFOLIO.relative_to(ROOT)).replace("\\", "/"),
        "portfolio_table_sha256": _sha256(PORTFOLIO),
        "candidate_count": int(len(spec)),
        "generation_project_rows_added": int(len(new_gen_rows)),
        "build_cost_rows_added": int(len(new_cost_rows)),
        "future_build_years": list(FUTURE_BUILD_YEARS),
        "model_zones": int(len(all_zones)),
        "pumped_hydro_zones": int(len(resource_rows)),
        "legacy_storage_rows_modified": False,
        "legacy_predetermined_rows_modified": False,
        "post_2030_non_lfp_cost_extrapolation_used": False,
        "post_2030_non_lfp_cost_treatment": "freeze at PNNL 2030 Point benchmark",
        "lfp_cost_method": "scenario-specific NREL 2025 4h trajectory x PNNL 2030 duration ratios",
        "pnnl_cost_currency_assumption": "2023 USD inherited from frozen V17T2R5 PNNL application convention",
        "cpi_u_2010": CPI_U_2010,
        "cpi_u_2023": CPI_U_2023,
        "deflator_2023_to_2010": DEFLATOR_2023_TO_2010,
        "headline_portfolio": [str(x) for x in spec.loc[spec["headline_eligibility"].astype(str).eq("evidence_bounded"), "portfolio_tech"]],
        "pressure_test_only_portfolio": [str(x) for x in spec.loc[spec["headline_eligibility"].astype(str).eq("pressure_test_only"), "portfolio_tech"]],
        "resource_boundary": "V18_PSH shares existing zone PSH ceilings; CAES/H2 lack defensible province-level resource ledgers and are pressure-test-only; LFP/VRFB are model-zone siting candidates, not station-level GIS siting claims.",
    }
    (audits / "V18_STORAGE_PORTFOLIO_APPLICATION.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    args = ap.parse_args()
    print(json.dumps(apply(args.case_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
