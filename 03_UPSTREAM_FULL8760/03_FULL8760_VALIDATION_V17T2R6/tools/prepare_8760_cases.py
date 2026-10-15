#!/usr/bin/env python3
"""Build four controlled 2033 full-8760 chronological validation cases.

Each case starts from its matching validated V17T2R5 four-hour template. Only
the temporal input layer is replaced. Within an observed/optimized pair, every
non-geographic input remains byte-identical; the inherited-storage allocation is
the sole controlled difference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "storage_runner" / "scenarios_targetyear_linked.csv"
TEMPLATES = ROOT / "template_cases_4h"
OUTROOT = ROOT / "sensitivity_cases"
LOAD_SHAPE = ROOT / "data" / "processed" / "figshare_load_2024_31province_8760_nonleap.csv"
VRE_PROFILE = ROOT / "data" / "processed" / "vre_cf_hourly_by_province_publication_calibrated.csv"
ZONE_MAP = ROOT / "data" / "processed" / "model_zone_to_province_mapping_v2.csv"
LOAD_WORKBOOK = ROOT / "data" / "raw" / "load" / "figshare_29832701_Data_output.xlsx"
TARGET_PERIOD = 2033
CALENDAR_YEAR = 2035
VRE_UTC_TO_CST_SHIFT_HOURS = 8
VRE_ZERO_THRESHOLD = 1.0e-6


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def annual_load_targets(template_inputs: Path, filename: str) -> pd.Series:
    periods = pd.read_csv(template_inputs / "periods.csv")
    prow = periods.loc[pd.to_numeric(periods["INVESTMENT_PERIOD"]).eq(TARGET_PERIOD)]
    if len(prow) != 1:
        raise ValueError(f"{filename}: target period {TARGET_PERIOD} is not unique")
    period_years = int(prow.iloc[0]["period_end"] - prow.iloc[0]["period_start"] + 1)
    ts = pd.read_csv(template_inputs / "timeseries.csv")
    tp = pd.read_csv(template_inputs / "timepoints.csv")
    ts["per_year_scale"] = pd.to_numeric(ts["ts_scale_to_period"], errors="raise") / period_years
    ts["duration_h"] = pd.to_numeric(ts["ts_duration_of_tp"], errors="raise")
    weights = tp[["timepoint_id", "timeseries"]].merge(
        ts[["TIMESERIES", "per_year_scale", "duration_h"]],
        left_on="timeseries", right_on="TIMESERIES", how="left", validate="many_to_one",
    )
    weights["annual_weight_h"] = weights["per_year_scale"] * weights["duration_h"]
    load = pd.read_csv(template_inputs / filename).merge(
        weights[["timepoint_id", "annual_weight_h"]],
        left_on="TIMEPOINT", right_on="timepoint_id", how="left", validate="many_to_one",
    )
    if load["annual_weight_h"].isna().any():
        raise ValueError(f"{filename}: unmapped representative timepoint")
    load["annual_mwh"] = pd.to_numeric(load["zone_demand_mw"], errors="raise") * load["annual_weight_h"]
    return load.groupby("load_zone", sort=True)["annual_mwh"].sum()


def calendar_tables(period_years: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DatetimeIndex]:
    stamps = pd.date_range(f"{CALENDAR_YEAR}-01-01 00:00", periods=8760, freq="h")
    ids = stamps.strftime("%Y.%m.%d.%H")
    month_ids = stamps.strftime("%Y.%m")
    timepoints = pd.DataFrame({
        "timepoint_id": ids,
        "timestamp": stamps.strftime("%Y-%m-%d_%H:%M"),
        "timeseries": month_ids,
    })
    counts = pd.Series(month_ids).value_counts(sort=False)
    timeseries = pd.DataFrame({
        "TIMESERIES": counts.index,
        "ts_period": TARGET_PERIOD,
        "ts_duration_of_tp": 1,
        "ts_num_tps": counts.to_numpy(dtype=int),
        "ts_scale_to_period": float(period_years),
    })
    return timepoints, timeseries, stamps


def build_loads(
    source: pd.DataFrame,
    targets: pd.Series,
    zone_to_province: dict[str, str],
    timepoint_ids: pd.Series,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    frames: list[pd.DataFrame] = []
    audits: list[dict[str, Any]] = []
    for zone, annual_target_mwh in targets.sort_index().items():
        province = zone_to_province.get(str(zone), str(zone))
        column = f"{province}_load_gw"
        if column not in source.columns:
            raise ValueError(f"No Figshare load shape for model zone {zone} -> {province}")
        source_mw = pd.to_numeric(source[column], errors="raise").to_numpy(float) * 1000.0
        denominator = float(source_mw.sum())
        scale = float(annual_target_mwh) / denominator
        values = source_mw * scale
        frames.append(pd.DataFrame({
            "load_zone": str(zone),
            "TIMEPOINT": timepoint_ids.to_numpy(),
            "zone_demand_mw": values,
        }))
        audits.append({
            "model_zone": str(zone),
            "source_province": province,
            "template_annual_energy_mwh": float(annual_target_mwh),
            "full8760_annual_energy_mwh": float(values.sum()),
            "shape_scaling_factor": scale,
            "minimum_load_mw": float(values.min()),
            "maximum_load_mw": float(values.max()),
            "annual_energy_residual_mwh": float(values.sum() - annual_target_mwh),
        })
    return pd.concat(frames, ignore_index=True), audits


def build_vcf(template_inputs: Path, timepoint_ids: pd.Series) -> tuple[pd.DataFrame, dict[str, Any]]:
    profile = pd.read_csv(
        VRE_PROFILE,
        usecols=["province_en", "model_hour", "solar_cf", "onshore_wind_cf"],
    ).sort_values(["province_en", "model_hour"])
    if profile.duplicated(["province_en", "model_hour"]).any():
        raise ValueError("Duplicate province-hour keys in calibrated VRE profile")
    counts = profile.groupby("province_en")["model_hour"].count()
    if len(counts) != 31 or not counts.eq(8760).all():
        raise ValueError("Calibrated VRE profile is not 31 provinces x 8760 hours")
    by_province = {
        province: group.sort_values("model_hour")[["solar_cf", "onshore_wind_cf"]].to_numpy(float)
        for province, group in profile.groupby("province_en", sort=False)
    }

    original_vcf = pd.read_csv(template_inputs / "variable_capacity_factors.csv")
    projects = original_vcf["GENERATION_PROJECT"].astype(str).drop_duplicates().tolist()
    gen = pd.read_csv(template_inputs / "gen_info.csv")
    meta = gen.set_index("GENERATION_PROJECT")[["gen_tech", "gen_load_zone"]]
    mapping = pd.read_csv(ZONE_MAP)
    zone_to_province = dict(zip(mapping["model_zone"].astype(str), mapping["province_en"].astype(str)))
    chunks: list[pd.DataFrame] = []
    offshore_rows = 0
    tiny_rows = 0
    for project in projects:
        technology = str(meta.loc[project, "gen_tech"])
        zone = str(meta.loc[project, "gen_load_zone"])
        province = zone_to_province.get(zone, zone)
        if province not in by_province:
            raise ValueError(f"No VRE province mapping for {project}: {zone} -> {province}")
        if technology in {"Solar_Distributed", "Solar_Utility"}:
            utc_values = by_province[province][:, 0]
        elif technology == "Wind_Onshore":
            utc_values = by_province[province][:, 1]
        elif technology == "Wind_Offshore":
            utc_values = np.zeros(8760, dtype=float)
            offshore_rows += 8760
        else:
            raise ValueError(f"Unsupported variable technology for {project}: {technology}")
        # ERA5 timestamps are UTC. Circular +8 h places UTC hour 00 at CST hour 08.
        values = np.roll(utc_values, VRE_UTC_TO_CST_SHIFT_HOURS)
        tiny = (values > 0.0) & (values < VRE_ZERO_THRESHOLD)
        tiny_rows += int(tiny.sum())
        values = values.copy()
        values[tiny] = 0.0
        if not np.logical_and(values >= 0.0, values <= 1.0).all():
            raise ValueError(f"Capacity factor outside [0,1] for {project}")
        chunks.append(pd.DataFrame({
            "GENERATION_PROJECT": project,
            "timepoint": timepoint_ids.to_numpy(),
            "gen_max_capacity_factor": values,
        }))
    out = pd.concat(chunks, ignore_index=True)
    return out, {
        "projects": len(projects),
        "rows": len(out),
        "timepoints": int(out["timepoint"].nunique()),
        "utc_to_cst_circular_shift_hours": VRE_UTC_TO_CST_SHIFT_HOURS,
        "offshore_rows_fixed_to_zero": offshore_rows,
        "offshore_scope": "unchanged from V17T2R5; no audited offshore hourly profile",
        "tiny_positive_rows_zeroed": tiny_rows,
        "numerical_zero_threshold": VRE_ZERO_THRESHOLD,
        "minimum_cf": float(out["gen_max_capacity_factor"].min()),
        "maximum_cf": float(out["gen_max_capacity_factor"].max()),
    }


def build_hydro(template_inputs: Path, new_timeseries: pd.DataFrame) -> pd.DataFrame:
    hydro = pd.read_csv(template_inputs / "hydro_timeseries.csv")
    hydro["month"] = hydro["timeseries"].astype(str).str.extract(r"^\d{4}\.(\d{2})", expand=False)
    if hydro["month"].isna().any() or hydro.duplicated(["hydro_project", "month"]).any():
        raise ValueError("Template hydro table is not unique by project and representative month")
    month_to_ts = {
        str(ts).split(".")[1]: str(ts)
        for ts in new_timeseries["TIMESERIES"].astype(str)
    }
    rows: list[dict[str, Any]] = []
    for _, row in hydro.iterrows():
        rows.append({
            "hydro_project": row["hydro_project"],
            "timeseries": month_to_ts[str(row["month"])],
            "hydro_avg_flow_per_mw": float(row["hydro_avg_flow_per_mw"]),
            "hydro_min_flow_per_mw": float(row["hydro_min_flow_per_mw"]),
        })
    return pd.DataFrame(rows)


def prepare_one(row: pd.Series) -> dict[str, Any]:
    scenario = str(row["scenario"])
    template_name = str(row["template_scenario"])
    template = TEMPLATES / template_name
    if not template.is_dir():
        raise FileNotFoundError(f"Missing frozen four-hour template: {template}")
    destination = OUTROOT / scenario
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(template, destination)
    inputs = destination / "inputs"

    periods = pd.read_csv(inputs / "periods.csv")
    target_row = periods.loc[pd.to_numeric(periods["INVESTMENT_PERIOD"]).eq(TARGET_PERIOD)]
    period_years = int(target_row.iloc[0]["period_end"] - target_row.iloc[0]["period_start"] + 1)
    timepoints, timeseries, _ = calendar_tables(period_years)
    source_load = pd.read_csv(LOAD_SHAPE)
    if len(source_load) != 8760 or source_load["model_hour"].tolist() != list(range(1, 8761)):
        raise ValueError("Processed Figshare load source is not a strict 1..8760 sequence")
    mapping = pd.read_csv(ZONE_MAP)
    zone_to_province = dict(zip(mapping["model_zone"].astype(str), mapping["province_en"].astype(str)))

    load_targets = annual_load_targets(inputs, "loads.csv")
    loads, load_audit = build_loads(source_load, load_targets, zone_to_province, timepoints["timepoint_id"])
    new_targets = annual_load_targets(inputs, "loads_new.csv")
    loads_new, load_new_audit = build_loads(source_load, new_targets, zone_to_province, timepoints["timepoint_id"])
    vcf, vcf_audit = build_vcf(inputs, timepoints["timepoint_id"])
    hydro = build_hydro(inputs, timeseries)

    timepoints.to_csv(inputs / "timepoints.csv", index=False)
    timeseries.to_csv(inputs / "timeseries.csv", index=False)
    loads.to_csv(inputs / "loads.csv", index=False)
    loads_new.to_csv(inputs / "loads_new.csv", index=False)
    vcf.to_csv(inputs / "variable_capacity_factors.csv", index=False)
    hydro.to_csv(inputs / "hydro_timeseries.csv", index=False)

    peaks = loads.groupby("load_zone", sort=True)["zone_demand_mw"].max()
    peak_path = inputs / "zone_coincident_peak_demand.csv"
    peak_table = pd.read_csv(peak_path)
    mask = pd.to_numeric(peak_table["PERIOD"], errors="raise").eq(TARGET_PERIOD)
    peak_table.loc[mask, "zone_expected_coincident_peak_demand"] = peak_table.loc[mask, "LOAD_ZONE"].map(peaks)
    if peak_table.loc[mask, "zone_expected_coincident_peak_demand"].isna().any():
        raise ValueError("Could not update every target-period coincident peak")
    peak_table.to_csv(peak_path, index=False)

    temporal_files = [
        "timepoints.csv", "timeseries.csv", "loads.csv", "loads_new.csv",
        "variable_capacity_factors.csv", "hydro_timeseries.csv",
        "zone_coincident_peak_demand.csv",
    ]
    audit = {
        "version": "V17T2R6_FULL8760",
        "scenario": scenario,
        "template_scenario": template_name,
        "chronology": "continuous 8760-hour non-leap year with year-end cyclic SOC and unit commitment",
        "target_period": TARGET_PERIOD,
        "calendar_timestamp_year": CALENDAR_YEAR,
        "source_load_year": 2024,
        "source_load_scope": "reconstructed provincial hourly curves; used only for normalized within-province shape",
        "source_load_workbook_sha256": sha256(LOAD_WORKBOOK),
        "processed_load_shape_sha256": sha256(LOAD_SHAPE),
        "source_vre_year": 2024,
        "source_vre_scope": "study-supplied ERA5-derived provincial solar and onshore-wind profiles; onshore wind nationally level-calibrated to the frozen NEA benchmark",
        "source_vre_sha256": sha256(VRE_PROFILE),
        "vre_alignment": "ERA5 UTC -> China Standard Time by deterministic +8 h circular shift",
        "hydro_scope": "V17T2R5 monthly hydro average and minimum flow envelopes held fixed and applied to every actual hour in each calendar month",
        "cross_source_limit": "Load and VRE are independently reconstructed 2024 sources; this is a chronological robustness test, not a single-dataset historical replay.",
        "annual_energy_lock": "Every model-zone annual demand is exactly preserved from its matching 2033 four-hour template.",
        "loads": load_audit,
        "loads_new_compatibility_table": load_new_audit,
        "vre": vcf_audit,
        "temporal_file_sha256": {name: sha256(inputs / name) for name in temporal_files},
    }
    audit_path = destination / "audits" / "FULL8760_TEMPORAL_INPUT_AUDIT.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    meta_path = destination / "SENSITIVITY_SCENARIO_META.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    for key, value in row.items():
        meta[key] = None if pd.isna(value) else (value.item() if hasattr(value, "item") else value)
    meta.update({
        "version": "V17T2R6_FULL8760",
        "scientific_design": "static_2033_exact_full_8760_capacity_and_dispatch_reoptimization",
        "full_8760_hour_claim_supported": True,
        "multi_period_transition_path_claim_supported": False,
        "temporal_input_audit": str(audit_path.relative_to(destination)).replace("\\", "/"),
        "pair_identification_lock": "Within each pair all non-geographic inputs are byte-identical; only the 2023-labelled inherited Battery allocation differs.",
    })
    # Replace the inherited four-hour template chronology claim instead of
    # leaving contradictory nested metadata in the full-8760 release.
    inherited_pruning = dict(meta.get("target_year_pruning_audit") or {})
    if inherited_pruning:
        inherited_pruning["provenance_role"] = "frozen four-hour template audit before full-8760 temporal expansion"
        meta["four_hour_template_pruning_audit"] = inherited_pruning
    meta["target_year_pruning_audit"] = {
        "target_year": int(row["target_year"]),
        "anchor_period": 2023,
        "design": "single_target_year_capacity_and_dispatch_reoptimization_full_8760",
        "transition_path_claim_supported": False,
        "full_8760_hour_claim_supported": True,
        "endogenous_pre_target_builds_carried_in": False,
        "historical_predetermined_assets_survive_by_model_lifetime_rule": True,
        "target_year_new_investment_allowed": True,
        "calendar_month_timeseries": 12,
        "hourly_timepoints": 8760,
        "time_resolution_h": 1,
        "storage_chronology": "one continuous cyclic year; SOC and unit commitment cross all month boundaries",
        "scope_note": "Static 2033 capacity-and-dispatch robustness test with full hourly chronology; not a multi-period transition pathway.",
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    from validate_8760_case import validate_case
    validation = validate_case(destination, row.to_dict(), raise_on_error=True)
    meta["prepared_input_validation"] = validation
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    from publication_source_common import write_case_fingerprint
    fingerprint = write_case_fingerprint(ROOT, destination, scenario, "sensitivity", "SENSITIVITY_SCENARIO_META.json")
    return {
        "scenario": scenario,
        "pair_id": str(row["pair_id"]),
        "template_scenario": template_name,
        "validation_status": validation["status"],
        "timepoints": 8760,
        "input_manifest_sha256": fingerprint["input_manifest_sha256"],
        "temporal_audit_sha256": sha256(audit_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", help="Prepare one scenario; default prepares all four")
    args = parser.parse_args()
    table = pd.read_csv(SCENARIOS)
    if args.scenario:
        table = table.loc[table["scenario"].astype(str).eq(args.scenario)]
        if len(table) != 1:
            raise SystemExit(f"Unknown scenario: {args.scenario}")
    OUTROOT.mkdir(parents=True, exist_ok=True)
    rows = [prepare_one(row) for _, row in table.iterrows()]
    pd.DataFrame(rows).to_csv(ROOT / "storage_runner" / "prepared_8760_cases_index.csv", index=False)
    if not args.scenario:
        from audit_targetyear_pair_identity import audit_all_pairs
        audit_all_pairs(raise_on_error=True)
    print(json.dumps({"status": "PASS", "prepared": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
