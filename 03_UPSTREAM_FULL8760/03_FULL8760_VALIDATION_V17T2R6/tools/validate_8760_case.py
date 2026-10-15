#!/usr/bin/env python3
"""Fail-closed structural and numerical validation for one full-8760 case."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_LOAD_WORKBOOK_SHA256 = "a93ff6d4a2f4f8c36538fdc4704e2e88bef16347d217c456a99a7a97d56a19e0"
EXPECTED_PROCESSED_LOAD_SHA256 = "74944cc8d707561ac1b6e3210cfa7035eaa5d0e84a391d42c012de17304291ab"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_case(case_dir: Path, scenario_row: dict[str, Any], raise_on_error: bool = True) -> dict[str, Any]:
    case_dir = Path(case_dir)
    inputs = case_dir / "inputs"
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    required = [
        "periods.csv", "timeseries.csv", "timepoints.csv", "loads.csv", "loads_new.csv",
        "variable_capacity_factors.csv", "hydro_timeseries.csv", "gen_info.csv",
        "legacy_storage_policy.csv", "gen_build_predetermined.csv", "zone_coincident_peak_demand.csv",
    ]
    missing = [name for name in required if not (inputs / name).is_file()]
    add("required_input_files", not missing, f"missing={missing}")
    if missing:
        report = {"status": "FAIL", "checks": checks}
        if raise_on_error:
            raise ValueError(json.dumps(report, ensure_ascii=False, indent=2))
        return report

    load_workbook = ROOT / "data" / "raw" / "load" / "figshare_29832701_Data_output.xlsx"
    processed_load = ROOT / "data" / "processed" / "figshare_load_2024_31province_8760_nonleap.csv"
    add("figshare_source_hash", sha256(load_workbook) == EXPECTED_LOAD_WORKBOOK_SHA256, sha256(load_workbook))
    add("processed_load_hash", sha256(processed_load) == EXPECTED_PROCESSED_LOAD_SHA256, sha256(processed_load))

    periods = pd.read_csv(inputs / "periods.csv")
    pvals = pd.to_numeric(periods["INVESTMENT_PERIOD"], errors="raise").astype(int).tolist()
    add("period_design", pvals == [2023, 2033], f"periods={pvals}")
    target = periods.loc[pd.to_numeric(periods["INVESTMENT_PERIOD"]).eq(2033)].iloc[0]
    period_years = int(target["period_end"] - target["period_start"] + 1)

    ts = pd.read_csv(inputs / "timeseries.csv")
    tp = pd.read_csv(inputs / "timepoints.csv")
    stamps = pd.to_datetime(tp["timestamp"], format="%Y-%m-%d_%H:%M", errors="raise")
    expected = pd.date_range("2035-01-01 00:00", periods=8760, freq="h")
    add("timepoint_count", len(tp) == 8760 and tp["timepoint_id"].nunique() == 8760, f"rows={len(tp)}")
    add("strict_hourly_sequence", np.array_equal(stamps.to_numpy(), expected.to_numpy()), f"first={stamps.iloc[0]}, last={stamps.iloc[-1]}")
    add("no_february_29", not ((stamps.dt.month == 2) & (stamps.dt.day == 29)).any(), "non-leap chronology")
    add("twelve_calendar_months", len(ts) == 12 and tp["timeseries"].nunique() == 12, f"timeseries={len(ts)}")
    durations = pd.to_numeric(ts["ts_duration_of_tp"], errors="raise")
    scales = pd.to_numeric(ts["ts_scale_to_period"], errors="raise")
    counts = tp.groupby("timeseries").size().sort_index()
    declared = ts.set_index("TIMESERIES")["ts_num_tps"].astype(int).sort_index()
    add("one_hour_duration", durations.eq(1.0).all(), f"durations={sorted(durations.unique())}")
    add("calendar_month_counts", counts.equals(declared), f"counts={counts.to_dict()}")
    add("period_scale", np.allclose(scales, period_years), f"scales={sorted(scales.unique())}, period_years={period_years}")
    normalized_hours = float((durations * scales / period_years * ts["ts_num_tps"]).sum())
    add("annual_hours_8760", abs(normalized_hours - 8760.0) <= 1e-9, f"hours={normalized_hours}")

    zones = pd.read_csv(inputs / "load_zones.csv")["LOAD_ZONE"].astype(str)
    timepoint_set = set(tp["timepoint_id"].astype(str))
    temporal_audit_path = case_dir / "audits" / "FULL8760_TEMPORAL_INPUT_AUDIT.json"
    temporal_audit = json.loads(temporal_audit_path.read_text(encoding="utf-8"))
    for filename, audit_key in [("loads.csv", "loads"), ("loads_new.csv", "loads_new_compatibility_table")]:
        load = pd.read_csv(inputs / filename)
        values = pd.to_numeric(load["zone_demand_mw"], errors="coerce")
        complete = (
            len(load) == len(zones) * 8760
            and load[["load_zone", "TIMEPOINT"]].drop_duplicates().shape[0] == len(load)
            and set(load["load_zone"].astype(str)) == set(zones)
            and set(load["TIMEPOINT"].astype(str)) == timepoint_set
        )
        add(f"{filename}_complete_cross_product", complete, f"rows={len(load)}, zones={load['load_zone'].nunique()}")
        add(f"{filename}_finite_positive", values.notna().all() and np.isfinite(values).all() and values.gt(0.0).all(), f"min={values.min()}, max={values.max()}")
        expected_energy = {str(x["model_zone"]): float(x["template_annual_energy_mwh"]) for x in temporal_audit[audit_key]}
        realized = load.assign(v=values).groupby("load_zone")["v"].sum()
        residual = max(abs(float(realized[z]) - expected_energy[z]) for z in expected_energy)
        add(f"{filename}_annual_energy_lock", residual <= 0.05, f"max_abs_residual_mwh={residual}")

    vcf = pd.read_csv(inputs / "variable_capacity_factors.csv")
    cf = pd.to_numeric(vcf["gen_max_capacity_factor"], errors="coerce")
    project_count = vcf["GENERATION_PROJECT"].nunique()
    complete_vcf = (
        len(vcf) == project_count * 8760
        and vcf[["GENERATION_PROJECT", "timepoint"]].drop_duplicates().shape[0] == len(vcf)
        and set(vcf["timepoint"].astype(str)) == timepoint_set
    )
    add("vcf_complete_cross_product", complete_vcf, f"rows={len(vcf)}, projects={project_count}")
    add("vcf_finite_bounded", cf.notna().all() and np.isfinite(cf).all() and cf.between(0.0, 1.0).all(), f"min={cf.min()}, max={cf.max()}")
    gen = pd.read_csv(inputs / "gen_info.csv").set_index("GENERATION_PROJECT")
    offshore = [g for g in vcf["GENERATION_PROJECT"].unique() if str(gen.loc[g, "gen_tech"]) == "Wind_Offshore"]
    offshore_values = vcf.loc[vcf["GENERATION_PROJECT"].isin(offshore), "gen_max_capacity_factor"]
    add("offshore_scope_isolated", len(offshore) == 21 and pd.to_numeric(offshore_values).eq(0.0).all(), f"projects={len(offshore)}")

    hydro = pd.read_csv(inputs / "hydro_timeseries.csv")
    hydro_projects = hydro["hydro_project"].nunique()
    hydro_complete = (
        len(hydro) == hydro_projects * 12
        and hydro[["hydro_project", "timeseries"]].drop_duplicates().shape[0] == len(hydro)
        and set(hydro["timeseries"].astype(str)) == set(ts["TIMESERIES"].astype(str))
    )
    havg = pd.to_numeric(hydro["hydro_avg_flow_per_mw"], errors="coerce")
    hmin = pd.to_numeric(hydro["hydro_min_flow_per_mw"], errors="coerce")
    add("hydro_monthly_envelope_complete", hydro_complete, f"rows={len(hydro)}, projects={hydro_projects}")
    add("hydro_flow_bounds", havg.notna().all() and hmin.notna().all() and (hmin >= 0).all() and (havg >= hmin).all() and (havg <= 1).all(), f"avg_range=({havg.min()},{havg.max()})")

    peaks = pd.read_csv(inputs / "zone_coincident_peak_demand.csv")
    target_peaks = peaks.loc[pd.to_numeric(peaks["PERIOD"]).eq(2033)].set_index("LOAD_ZONE")["zone_expected_coincident_peak_demand"].astype(float)
    model_load = pd.read_csv(inputs / "loads.csv")
    realized_peaks = model_load.groupby("load_zone")["zone_demand_mw"].max()
    peak_residual = float((target_peaks.sort_index() - realized_peaks.sort_index()).abs().max())
    add("coincident_peak_updated", peak_residual <= 1e-6, f"max_abs_residual_mw={peak_residual}")

    row_mode = str(scenario_row.get("storage_chronology_mode", ""))
    add("scenario_chronology_mode", row_mode == "full_year_cyclic", f"mode={row_mode}")
    add("temporal_audit_present", temporal_audit_path.is_file(), "audits/FULL8760_TEMPORAL_INPUT_AUDIT.json")
    add("timezone_alignment_declared", temporal_audit.get("vre_alignment") == "ERA5 UTC -> China Standard Time by deterministic +8 h circular shift", str(temporal_audit.get("vre_alignment")))

    failures = [x for x in checks if not x["pass"]]
    report = {
        "version": "V17T2R6_FULL8760",
        "scenario": str(scenario_row.get("scenario", case_dir.name)),
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failed": failures,
    }
    out = case_dir / "audits" / "FULL8760_PREPARED_INPUT_VALIDATION.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if raise_on_error and failures:
        raise ValueError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dir", type=Path)
    args = parser.parse_args()
    table = pd.read_csv(ROOT / "storage_runner" / "scenarios_targetyear_linked.csv")
    rows = table.loc[table["scenario"].astype(str).eq(args.case_dir.name)]
    if len(rows) != 1:
        raise SystemExit(f"No unique scenario row for {args.case_dir.name}")
    print(json.dumps(validate_case(args.case_dir, rows.iloc[0].to_dict(), True), ensure_ascii=False, indent=2))
