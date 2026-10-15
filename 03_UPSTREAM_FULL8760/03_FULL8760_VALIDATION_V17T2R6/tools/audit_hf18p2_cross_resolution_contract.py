#!/usr/bin/env python3
"""Read-only four-case audit of the HF18P2 cross-resolution contract."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import math
import os

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FULL_CASES = ROOT / "sensitivity_cases"
SOURCE_OUTPUTS = Path(os.environ.get(
    "V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT",
    str(ROOT.parent / "targetyear_sensitivity_upstream_V17T2R5" / "sensitivity_outputs"),
)).resolve()
TARGET_CASES = SOURCE_OUTPUTS.parent / "sensitivity_cases"
PAIRS = {
    "TY2033_FULL8760_OBSERVED": "TY2033_CHRONO_OBSERVED",
    "TY2033_FULL8760_OPTIMAL": "TY2033_CHRONO_OPTIMAL",
    "TY2033_FULL8760_LDES_OBSERVED": "TY2033_CHRONO_LDES_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL": "TY2033_CHRONO_LDES_OPTIMAL",
}
TEMPORAL = {
    "loads.csv", "loads_new.csv", "timepoints.csv", "timeseries.csv",
    "variable_capacity_factors.csv", "hydro_timeseries.csv",
    "zone_coincident_peak_demand.csv", "electricity_demand.csv",
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_hashes(case: Path) -> dict[str, str]:
    return {p.name: sha(p) for p in sorted((case / "inputs").glob("*.csv"))}


def load_energy(case: Path) -> tuple[int, float, dict[str, float]]:
    inputs = case / "inputs"
    timepoints = pd.read_csv(inputs / "timepoints.csv", usecols=["timepoint_id", "timeseries"])
    timeseries = pd.read_csv(inputs / "timeseries.csv",
                             usecols=["TIMESERIES", "ts_duration_of_tp", "ts_scale_to_period"])
    weights = timeseries.assign(
        weight=pd.to_numeric(timeseries["ts_duration_of_tp"], errors="raise") *
        pd.to_numeric(timeseries["ts_scale_to_period"], errors="raise") / 5.0
    ).set_index("TIMESERIES")["weight"]
    tp_weight = timepoints.assign(
        weight=timepoints["timeseries"].map(weights)
    ).set_index("timepoint_id")["weight"]
    loads = pd.read_csv(inputs / "loads.csv", usecols=["load_zone", "TIMEPOINT", "zone_demand_mw"])
    demand = pd.to_numeric(loads["zone_demand_mw"], errors="raise")
    if not demand.map(math.isfinite).all() or (demand < 0.0).any():
        raise RuntimeError(f"invalid load values: {case}")
    row_weights = loads["TIMEPOINT"].map(tp_weight)
    if row_weights.isna().any():
        raise RuntimeError(f"load/timepoint mapping is incomplete: {case}")
    energy = float((demand * row_weights).sum())
    zone_max = loads.assign(value=demand).groupby("load_zone")["value"].max().to_dict()
    return len(timepoints), energy, {str(k): float(v) for k, v in zone_max.items()}


def explicit_peaks(case: Path) -> dict[str, float]:
    frame = pd.read_csv(case / "inputs" / "zone_coincident_peak_demand.csv")
    frame = frame[pd.to_numeric(frame["PERIOD"], errors="raise").eq(2033)]
    return dict(zip(frame["LOAD_ZONE"].astype(str),
                    pd.to_numeric(frame["zone_expected_coincident_peak_demand"], errors="raise")))


def main() -> None:
    records: list[dict] = []
    failures: list[str] = []
    for full_name, target_name in PAIRS.items():
        full = FULL_CASES / full_name
        target = TARGET_CASES / target_name
        if not full.is_dir() or not target.is_dir():
            failures.append(f"missing case directory: {full} or {target}")
            continue
        target_tp, target_energy, _ = load_energy(target)
        full_tp, full_energy, full_zone_max = load_energy(full)
        energy_rel = abs(full_energy - target_energy) / max(1.0, abs(target_energy))
        target_peak = explicit_peaks(target)
        full_peak = explicit_peaks(full)
        zones_equal = set(target_peak) == set(full_peak) == set(full_zone_max)
        if not zones_equal:
            failures.append(f"zone-set mismatch: {full_name}")
        ratios = [full_peak[z] / max(1.0e-9, target_peak[z]) for z in target_peak] if zones_equal else []
        full_peak_matches_hourly_max = zones_equal and max(
            abs(full_peak[z] - full_zone_max[z]) for z in full_peak
        ) <= 1.0e-6
        target_hashes = input_hashes(target)
        full_hashes = input_hashes(full)
        changed_non_temporal = sorted(
            name for name in set(target_hashes) & set(full_hashes)
            if name not in TEMPORAL and target_hashes[name] != full_hashes[name]
        )
        passed = (target_tp == 72 and full_tp == 8760 and energy_rel <= 1.0e-10 and
                  zones_equal and full_peak_matches_hourly_max and not changed_non_temporal)
        if not passed:
            failures.append(f"cross-resolution contract failed: {full_name}")
        records.append({
            "full_scenario": full_name,
            "target_source_scenario": target_name,
            "pass": passed,
            "target_timepoints": target_tp,
            "full_timepoints": full_tp,
            "target_annual_energy_mwh": target_energy,
            "full_annual_energy_mwh": full_energy,
            "annual_energy_relative_difference": energy_rel,
            "zone_sets_equal": zones_equal,
            "full_peak_table_equals_full_hourly_zone_max": full_peak_matches_hourly_max,
            "full_to_target_peak_ratio_min": min(ratios) if ratios else None,
            "full_to_target_peak_ratio_max": max(ratios) if ratios else None,
            "changed_non_temporal_inputs": changed_non_temporal,
            "peak_semantics_note": (
                "The prepared full-8760 per-zone peak table is intentionally retained. "
                "HF18P2 does not replace it with the representative-timepoint source table."
            ),
        })
    payload = {
        "version": "V17T2R6R24_HF18P2",
        "status": "PASS" if not failures and len(records) == 4 else "FAIL",
        "source_case_root": str(TARGET_CASES),
        "full_case_root": str(FULL_CASES),
        "scientific_inputs_mutated": False,
        "full_8760_peak_policy_mutated": False,
        "records": records,
        "failures": failures,
    }
    (ROOT / "audits").mkdir(exist_ok=True)
    out = ROOT / "audits" / "HF18P2_CROSS_RESOLUTION_CONTRACT.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
