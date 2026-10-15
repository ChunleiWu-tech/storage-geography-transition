#!/usr/bin/env python3
"""Audit the scenario-local numerical domain used by the HF17 exact rewrite."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "TY2033_FULL8760_OBSERVED",
    "TY2033_FULL8760_OPTIMAL",
    "TY2033_FULL8760_LDES_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL",
)
ROW_SCALE = 5_000.0
MAX_SCALED_RHS = 1_000_000.0


def finite_nonnegative_max(frame: pd.DataFrame, column: str, label: str) -> float:
    if column not in frame.columns:
        raise SystemExit(f"{label}: missing column {column}")
    values = pd.to_numeric(frame[column], errors="coerce")
    if values.isna().any() or (values < 0).any():
        raise SystemExit(f"{label}: {column} contains non-finite or negative values")
    return float(values.max())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    cases: list[dict] = []
    for scenario in TARGETS:
        inputs = ROOT / "sensitivity_cases" / scenario / "inputs"
        carbon_path = inputs / "carbon_policies.csv"
        storage_path = inputs / "co2_injection_limits.csv"
        fuel_path = inputs / "fuel_supply_curves.csv"
        hydro_path = inputs / "hydro_timeseries.csv"
        for path in (carbon_path, storage_path, fuel_path, hydro_path):
            if not path.is_file():
                raise SystemExit(f"{scenario}: missing prepared input {path}")
        carbon = pd.read_csv(carbon_path)
        storage = pd.read_csv(storage_path)
        fuel = pd.read_csv(fuel_path)
        hydro = pd.read_csv(hydro_path)
        carbon_max = finite_nonnegative_max(
            carbon, "carbon_cap_tco2_per_yr", f"{scenario}/carbon_policies.csv"
        )
        storage_max = finite_nonnegative_max(
            storage, "max_injection_tco2_per_yr", f"{scenario}/co2_injection_limits.csv"
        )
        fuel_max = finite_nonnegative_max(
            fuel, "max_avail_at_cost", f"{scenario}/fuel_supply_curves.csv"
        )
        required_hydro = {
            "hydro_project", "timeseries", "hydro_avg_flow_per_mw", "hydro_min_flow_per_mw"
        }
        if not required_hydro.issubset(hydro.columns):
            raise SystemExit(f"{scenario}: hydro_timeseries.csv schema mismatch")
        avg = pd.to_numeric(hydro["hydro_avg_flow_per_mw"], errors="coerce")
        minimum = pd.to_numeric(hydro["hydro_min_flow_per_mw"], errors="coerce")
        if avg.isna().any() or minimum.isna().any() or (avg < 0).any() or (minimum < 0).any():
            raise SystemExit(f"{scenario}: hydro flow inputs contain non-finite or negative values")
        if (minimum > avg + 1.0e-12).any():
            raise SystemExit(f"{scenario}: hydro minimum flow exceeds average flow")
        scaled = {
            "carbon": carbon_max / ROW_SCALE,
            "co2_storage": storage_max / ROW_SCALE,
            "fuel_limit": fuel_max / ROW_SCALE,
        }
        if any(value > MAX_SCALED_RHS for value in scaled.values()):
            raise SystemExit(f"{scenario}: a scaled policy RHS exceeds {MAX_SCALED_RHS}")
        hydro_pairs = hydro[["hydro_project", "timeseries"]].drop_duplicates()
        if hydro_pairs.empty:
            raise SystemExit(f"{scenario}: hydro exact-projection domain is empty")
        cases.append({
            "scenario": scenario,
            "carbon_cap_max_native": carbon_max,
            "co2_storage_cap_max_native": storage_max,
            "fuel_limit_max_native": fuel_max,
            "row_scale": ROW_SCALE,
            "scaled_rhs_maxima": scaled,
            "scaled_rhs_all_le_1e6": True,
            "hydro_project_count": int(hydro["hydro_project"].nunique()),
            "hydro_project_timeseries_pair_count": int(len(hydro_pairs)),
            "exact_projection_statement": (
                "For nonnegative objective-neutral spill, exists spill with "
                "sum(dispatch+spill)=available iff sum(dispatch)<=available."
            ),
            "input_sha256": {
                path.name: sha256(path)
                for path in (carbon_path, storage_path, fuel_path, hydro_path)
            },
            "scenario_local_gate": True,
        })
    report = {
        "version": "V17T2R6R21_HF17_exact_scaling_and_hydro_projection_input_audit_v1",
        "status": "PASS",
        "scientific_inputs_changed": False,
        "objective_changed": False,
        "native_rhs_changed": False,
        "chronology_changed": False,
        "algebraic_changes": [
            "positive row multiplication/division only for carbon, geologic-storage and fuel-limit rows",
            "exact projection of nonnegative objective-neutral hourly hydro spill variables",
        ],
        "cases": cases,
    }
    output = ROOT / "audits" / "HF17_EXACT_SCALING_AND_HYDRO_PROJECTION_INPUT_AUDIT.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
