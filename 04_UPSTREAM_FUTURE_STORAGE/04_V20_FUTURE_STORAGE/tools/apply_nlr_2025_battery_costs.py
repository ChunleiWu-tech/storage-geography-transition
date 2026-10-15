#!/usr/bin/env python3
"""Apply source-direct NLR 2025 four-hour utility battery assumptions.

The official NLR/NREL Table 2 values are complete-system overnight costs in
2024 USD/kWh for a four-hour lithium-ion battery. They are converted to the
model's 2010 USD with annual CPI-U indices, not with a fitted capacity target.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "data" / "processed" / "nlr_2025_battery_4h_costs.csv"
CPI_U_2010 = 218.056
CPI_U_2024 = 313.689
DEFLATOR_2024_TO_2010 = CPI_U_2010 / CPI_U_2024
DURATION_H = 4.0
LIFETIME_Y = 15
ROUND_TRIP_EFFICIENCY = 0.85
FOM_SHARE_OF_POWER_CAPEX = 0.04
VALID_CASES = {"NLR_2025_low": "low", "NLR_2025_mid": "mid", "NLR_2025_high": "high"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def apply(case_dir: str | Path, cost_case: str = "NLR_2025_mid") -> dict:
    case_dir = Path(case_dir)
    inp = case_dir / "inputs"
    if cost_case not in VALID_CASES:
        raise ValueError(f"Unknown NLR cost case {cost_case}; expected {sorted(VALID_CASES)}")
    projection = VALID_CASES[cost_case]
    source = pd.read_csv(TABLE)
    if source["year"].duplicated().any() or source["year"].astype(int).tolist() != list(range(2024, 2061)):
        raise ValueError("NLR Table 2 transcription must contain one row for every year 2024-2060")

    gen_path = inp / "gen_info.csv"
    gen = pd.read_csv(gen_path)
    battery = gen["gen_tech"].astype(str).eq("Battery")
    if int(battery.sum()) != 32:
        raise ValueError(f"Expected 32 Battery projects, found {int(battery.sum())}")
    # These columns contain the literal "." for non-storage technologies in the
    # legacy Switch input schema.  pandas 3 keeps such columns as strict string
    # arrays, so cast them to object before assigning numeric storage values.
    for col in [
        "gen_storage_energy_to_power_ratio",
        "gen_storage_efficiency",
        "gen_max_age",
        "gen_variable_om",
    ]:
        gen[col] = gen[col].astype(object)
    gen.loc[battery, "gen_storage_energy_to_power_ratio"] = DURATION_H
    gen.loc[battery, "gen_storage_efficiency"] = ROUND_TRIP_EFFICIENCY
    gen.loc[battery, "gen_max_age"] = LIFETIME_Y
    gen.loc[battery, "gen_variable_om"] = 0.0
    gen.to_csv(gen_path, index=False)

    costs_path = inp / "gen_build_costs.csv"
    costs = pd.read_csv(costs_path)
    for col in ["gen_overnight_cost", "gen_storage_energy_overnight_cost", "gen_fixed_om"]:
        costs[col] = pd.to_numeric(costs[col].replace(".", pd.NA), errors="coerce")
    bmask = costs["GENERATION_PROJECT"].astype(str).str.endswith("-Battery")
    years = pd.to_numeric(costs["build_year"], errors="raise").astype(int)
    active = bmask & years.ge(2024)
    needed = sorted(years.loc[active].unique().tolist())
    missing = sorted(set(needed) - set(source["year"].astype(int)))
    if missing:
        raise ValueError(f"NLR direct table has no values for Battery build years {missing}")
    lookup = source.set_index("year")[f"{projection}_2024usd_per_kwh"].astype(float)
    cost_2024_per_kwh = years.loc[active].map(lookup)
    total_2010_per_mw = cost_2024_per_kwh * DEFLATOR_2024_TO_2010 * DURATION_H * 1000.0
    costs.loc[active, "gen_overnight_cost"] = total_2010_per_mw.to_numpy()
    costs.loc[active, "gen_storage_energy_overnight_cost"] = 0.0
    costs.loc[active, "gen_fixed_om"] = (total_2010_per_mw * FOM_SHARE_OF_POWER_CAPEX).to_numpy()
    costs.to_csv(costs_path, index=False)

    rows = []
    for year in needed:
        source_value = float(lookup.loc[year])
        total = source_value * DEFLATOR_2024_TO_2010 * DURATION_H * 1000.0
        rows.append({
            "build_year": year,
            "cost_case": cost_case,
            "source_2024usd_per_kwh": source_value,
            "model_2010usd_per_kw_complete_4h": total / 1000.0,
            "model_2010usd_per_mw": total,
            "model_fixed_om_2010usd_per_mw_year": total * FOM_SHARE_OF_POWER_CAPEX,
        })
    audits = case_dir / "audits"
    audits.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(audits / "nlr_2025_battery_cost_application.csv", index=False)
    report = {
        "status": "PASS",
        "version": "NLR_2025_DIRECT_4H_CPIU_2010USD_V1",
        "case": cost_case,
        "source": "Cole, Ramasamy and Turan (2025), NREL/TP-6A40-93281, Appendix Table 2",
        "doi": "10.2172/2583471",
        "source_units": "2024 USD/kWh, complete 4-hour utility-scale lithium-ion system",
        "model_units": "2010 USD/MW complete four-hour power block; energy CAPEX is zero to avoid double counting",
        "source_table_sha256": _sha256(TABLE),
        "cpi_u_2010": CPI_U_2010,
        "cpi_u_2024": CPI_U_2024,
        "deflator_2024_to_2010": DEFLATOR_2024_TO_2010,
        "battery_project_count": int(battery.sum()),
        "updated_cost_row_count": int(active.sum()),
        "updated_build_years": needed,
        "fixed_duration_h": DURATION_H,
        "lifetime_years": LIFETIME_Y,
        "round_trip_efficiency": ROUND_TRIP_EFFICIENCY,
        "fixed_om_share_of_power_capex": FOM_SHARE_OF_POWER_CAPEX,
        "reverse_calibration_used": False,
        "capacity_target_used": False,
        "arbitrary_cost_multiplier_used": False,
    }
    (audits / "nlr_2025_battery_cost_application.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    ap.add_argument("--cost-case", default="NLR_2025_mid", choices=sorted(VALID_CASES))
    args = ap.parse_args()
    print(json.dumps(apply(args.case_dir, args.cost_case), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
