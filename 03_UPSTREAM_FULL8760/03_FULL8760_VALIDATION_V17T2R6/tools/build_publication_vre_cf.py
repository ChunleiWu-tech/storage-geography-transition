#!/usr/bin/env python3
"""Build the publication VRE baseline from official NEA source anchors.

The supplied 2024 province-level ERA5 profile provides hourly spatial and temporal
shape. Solar is retained as supplied. Onshore-wind values receive one monotonic
national level correction, y = 1 - (1 - x)^alpha. The target is derived only from
National Energy Administration (NEA) data: finalized 2024 wind generation and
utilization, plus a piecewise-linear integral of official month-end wind capacity.

This is a national proxy correction. It is not province-specific validation and it
does not claim that the national wind statistic is an onshore-only observation.
"""
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, io, json, zipfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "processed" / "vre_cf_hourly_by_province.csv"
OUT = ROOT / "data" / "processed" / "vre_cf_hourly_by_province_publication_calibrated.csv"
SUMMARY = ROOT / "data" / "processed" / "vre_cf_validation_summary_publication_calibrated.csv"
BENCHMARK = ROOT / "data" / "processed" / "vre_cf_national_benchmark_2024.csv"
MONTHLY = ROOT / "data" / "source_registry" / "nea_wind_capacity_month_end_2024.csv"
ANCHOR = ROOT / "data" / "source_registry" / "nea_wind_generation_utilization_2024.csv"
MAPPING = ROOT / "data" / "processed" / "model_zone_to_province_mapping_v2.csv"
CASE_INPUT = ROOT / "base_model_v39" / "storage_base_noNBCCS_noDACCS_onshorePV" / "inputs"
TEMPLATE = ROOT / "base_model_v39" / "storage_base_template_v17.zip"
STORAGE = ROOT / "data" / "processed" / "existing_new_storage_allocated_to_model_zones_2025.csv"
LEDGER = ROOT / "data" / "source_registry" / "provincial_storage_source_ledger_2025.csv"
SHARED = ROOT.parent / "shared_source_snapshots"
DATA_VERSION = "NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2"
VRE_CF_NUMERICAL_ZERO_THRESHOLD = 1.0e-6


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _template_csv(name: str) -> pd.DataFrame:
    with zipfile.ZipFile(TEMPLATE) as archive:
        return pd.read_csv(archive.open(f"inputs/{name}"))


def predetermined_wind_weights() -> pd.Series:
    # Use the frozen study template only. Using a previously expanded base case here
    # would make calibration depend on run order and create a circular source chain.
    gen = _template_csv("gen_info.csv")
    pred = _template_csv("gen_build_predetermined.csv")
    mapping = pd.read_csv(MAPPING)
    z2p = dict(zip(mapping["model_zone"].astype(str), mapping["province_en"].astype(str)))
    wind = gen.loc[gen["gen_tech"].eq("Wind_Onshore"), ["GENERATION_PROJECT", "gen_load_zone"]].copy()
    wind["province_en"] = wind["gen_load_zone"].astype(str).map(lambda z: z2p.get(z, z))
    capacity = pred.groupby("GENERATION_PROJECT", as_index=False)["build_gen_predetermined"].sum()
    wind = wind.merge(capacity, on="GENERATION_PROJECT", how="left").fillna({"build_gen_predetermined": 0.0})
    weights = wind.groupby("province_en")["build_gen_predetermined"].sum().astype(float)
    if weights.sum() <= 0:
        raise ValueError("No predetermined onshore-wind capacity found for national weighting")
    weights.attrs["source"] = "retained_template_zip"
    return weights


def official_anchor() -> dict[str, object]:
    cap = pd.read_csv(MONTHLY)
    a = pd.read_csv(ANCHOR)
    if len(a) != 1:
        raise ValueError("NEA wind anchor must contain exactly one row")
    cap["observation_date"] = pd.to_datetime(cap["observation_date"], errors="raise")
    points = pd.Series(
        cap["wind_capacity_gw"].astype(float).to_numpy(),
        index=cap["observation_date"] + pd.Timedelta(days=1),
    ).sort_index()
    daily_index = pd.date_range("2024-01-01", "2025-01-01", freq="D")
    daily = points.reindex(daily_index).interpolate(method="time")
    if daily.isna().any():
        raise ValueError("Monthly wind-capacity anchors do not span the complete 2024 integration interval")
    trapezoid = getattr(np, "trapezoid", np.trapz)
    average_capacity_gw = float(trapezoid(daily.to_numpy(float), dx=1.0) / 366.0)
    generation_twh = float(a.iloc[0]["final_wind_generation_twh"])
    utilization = float(a.iloc[0]["national_wind_utilization_rate_fraction"])
    net_hours = generation_twh * 1000.0 / average_capacity_gw
    gross_hours = net_hours / utilization
    target_cf = gross_hours / 8760.0
    declared = float(a.iloc[0]["derived_gross_availability_cf_for_8760_model_year"])
    if abs(target_cf - declared) > 1e-12:
        raise ValueError(f"Recomputed NEA target {target_cf} differs from declared anchor {declared}")
    return {
        "average_capacity_gw": average_capacity_gw,
        "generation_twh": generation_twh,
        "utilization_rate_fraction": utilization,
        "net_full_load_hours": net_hours,
        "gross_availability_full_load_hours": gross_hours,
        "target_cf_8760": target_cf,
        "monthly_source_sha256": sha256(MONTHLY),
        "anchor_source_sha256": sha256(ANCHOR),
        "source_url": str(a.iloc[0]["generation_and_utilization_source_url"]),
        "source_status": str(a.iloc[0]["source_status"]),
        "scope_note": str(a.iloc[0]["scientific_scope_note"]),
    }


def weighted_mean(frame: pd.DataFrame, column: str, weights: pd.Series) -> float:
    means = frame.groupby("province_en")[column].mean()
    common = means.index.intersection(weights.index)
    if len(common) != len(weights[weights > 0]):
        missing = sorted(set(weights[weights > 0].index) - set(common))
        raise ValueError(f"VRE profile lacks weighted wind provinces: {missing}")
    return float(np.average(means.loc[common], weights=weights.loc[common]))


def solve_alpha(raw: pd.DataFrame, weights: pd.Series, target_cf: float) -> float:
    x = raw["onshore_wind_cf"].to_numpy(float)
    provinces = raw["province_en"].astype(str).to_numpy()
    hours_per_province = raw.groupby("province_en").size().to_dict()
    row_w = np.array([weights.get(p, 0.0) / hours_per_province.get(p, 1) for p in provinces], dtype=float)
    row_w /= row_w.sum()

    def f(alpha: float) -> float:
        y = 1.0 - np.power(1.0 - np.clip(x, 0.0, 1.0), alpha)
        y[(y > 0.0) & (y < VRE_CF_NUMERICAL_ZERO_THRESHOLD)] = 0.0
        return float(np.dot(row_w, y))

    lo, hi = 1.0e-4, 100.0
    if not (f(lo) <= target_cf <= f(hi)):
        raise ValueError(f"Target CF {target_cf:.12f} is outside monotonic-transform range")
    for _ in range(140):
        mid = (lo + hi) / 2.0
        if f(mid) < target_cf:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def build(*, force: bool = False) -> dict[str, object]:
    audit_path = ROOT / "audits" / "vre_cf_publication_calibration_audit.json"
    anchor = official_anchor()
    dependencies = {
        "raw_profile_sha256": sha256(RAW),
        "monthly_anchor_sha256": sha256(MONTHLY),
        "generation_utilization_anchor_sha256": sha256(ANCHOR),
        "zone_mapping_sha256": sha256(MAPPING),
        "template_sha256": sha256(TEMPLATE),
    }
    if not force and OUT.exists() and SUMMARY.exists() and BENCHMARK.exists() and audit_path.exists():
        old = json.loads(audit_path.read_text(encoding="utf-8"))
        reusable = (old.get("data_version") == DATA_VERSION
                    and old.get("calibration_dependency_sha256") == dependencies
                    and abs(float(old.get("derived_gross_availability_cf", -1)) - anchor["target_cf_8760"]) < 1e-14
                    and old.get("publication_file_sha256") == sha256(OUT)
                    and old.get("summary_file_sha256") == sha256(SUMMARY)
                    and old.get("benchmark_file_sha256") == sha256(BENCHMARK))
        if reusable:
            print(json.dumps({**old, "reused_existing_calibrated_profile": True}, ensure_ascii=False, indent=2))
            return old

    raw = pd.read_csv(RAW)
    required = {"province_en", "province_cn", "model_hour", "solar_cf", "onshore_wind_cf"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError("Raw VRE file missing columns: " + ", ".join(sorted(missing)))
    if len(raw) != 31 * 8760 or raw["province_en"].nunique() != 31 or raw["model_hour"].nunique() != 8760:
        raise ValueError("Raw VRE profile must contain 31 provinces x 8760 model hours")
    weights = predetermined_wind_weights()
    raw_weighted_cf = weighted_mean(raw, "onshore_wind_cf", weights)
    alpha = solve_alpha(raw, weights, float(anchor["target_cf_8760"]))
    calibrated = raw.copy()
    x = calibrated["onshore_wind_cf"].clip(0.0, 1.0).to_numpy(float)
    calibrated["onshore_wind_cf"] = 1.0 - np.power(1.0 - x, alpha)
    tiny_counts, tiny_sums = {}, {}
    for column in ["solar_cf", "onshore_wind_cf"]:
        mask = calibrated[column].between(0.0, VRE_CF_NUMERICAL_ZERO_THRESHOLD, inclusive="neither")
        tiny_counts[column] = int(mask.sum())
        tiny_sums[column] = float(calibrated.loc[mask, column].sum())
        calibrated.loc[mask, column] = 0.0
    calibrated.to_csv(OUT, index=False)
    calibrated_weighted_cf = weighted_mean(calibrated, "onshore_wind_cf", weights)
    if abs(calibrated_weighted_cf - float(anchor["target_cf_8760"])) > 2e-13:
        raise ValueError("Calibrated wind CF failed exact national closure after numerical-zero treatment")

    summary = calibrated.groupby(["province_en", "province_cn"], as_index=False).agg(
        solar_cf_mean=("solar_cf", "mean"), solar_cf_min=("solar_cf", "min"), solar_cf_max=("solar_cf", "max"),
        onshore_wind_cf_mean=("onshore_wind_cf", "mean"), onshore_wind_cf_min=("onshore_wind_cf", "min"), onshore_wind_cf_max=("onshore_wind_cf", "max"),
        hours=("model_hour", "count"),
    )
    summary["solar_full_load_hours"] = summary["solar_cf_mean"] * 8760.0
    summary["onshore_wind_full_load_hours"] = summary["onshore_wind_cf_mean"] * 8760.0
    summary["cf_scope"] = "raw solar; onshore wind nationally level-corrected with an NEA-only monotonic transform; offshore wind excluded"
    summary["data_version"] = DATA_VERSION
    summary.to_csv(SUMMARY, index=False)

    benchmark = pd.DataFrame([{
        "data_version": DATA_VERSION,
        "benchmark_year": 2024,
        "technology": "national_total_wind_proxy_applied_to_onshore_profile",
        "final_wind_generation_twh": anchor["generation_twh"],
        "integrated_average_wind_capacity_gw": anchor["average_capacity_gw"],
        "observed_net_full_load_hours": anchor["net_full_load_hours"],
        "reported_utilization_rate_fraction": anchor["utilization_rate_fraction"],
        "derived_gross_availability_full_load_hours": anchor["gross_availability_full_load_hours"],
        "derived_gross_availability_cf": anchor["target_cf_8760"],
        "raw_model_capacity_weighted_cf": raw_weighted_cf,
        "raw_model_capacity_weighted_full_load_hours": raw_weighted_cf * 8760.0,
        "calibrated_model_capacity_weighted_cf": calibrated_weighted_cf,
        "calibrated_model_capacity_weighted_full_load_hours": calibrated_weighted_cf * 8760.0,
        "monotonic_transform_alpha": alpha,
        "weight_source": weights.attrs.get("source"),
        "official_source": "National Energy Administration",
        "official_source_url": anchor["source_url"],
        "monthly_capacity_source_file": MONTHLY.relative_to(ROOT).as_posix(),
        "generation_utilization_source_file": ANCHOR.relative_to(ROOT).as_posix(),
        "source_accessed_date": "2026-08-03",
        "scientific_scope_note": anchor["scope_note"],
    }])
    benchmark.to_csv(BENCHMARK, index=False)

    audit = benchmark.iloc[0].to_dict() | {
        "raw_file": RAW.relative_to(ROOT).as_posix(),
        "publication_file": OUT.relative_to(ROOT).as_posix(),
        "summary_file": SUMMARY.relative_to(ROOT).as_posix(),
        "raw_file_sha256": sha256(RAW),
        "publication_file_sha256": sha256(OUT),
        "summary_file_sha256": sha256(SUMMARY),
        "benchmark_file_sha256": sha256(BENCHMARK),
        "monthly_source_sha256": anchor["monthly_source_sha256"],
        "anchor_source_sha256": anchor["anchor_source_sha256"],
        "template_sha256": sha256(TEMPLATE),
        "bounded_0_1": bool(calibrated["onshore_wind_cf"].between(0.0, 1.0).all()),
        "original_zero_hours_remain_zero": bool((calibrated.loc[raw["onshore_wind_cf"] == 0.0, "onshore_wind_cf"] == 0.0).all()),
        "support_change_policy": "Only original zeros and explicitly declared tiny positive values below the numerical CF threshold may be zero after calibration.",
        "hourly_rank_preserved_above_declared_zero_threshold": True,
        "numerical_cf_zero_threshold": VRE_CF_NUMERICAL_ZERO_THRESHOLD,
        "tiny_positive_rows_zeroed": tiny_counts,
        "tiny_positive_cf_sum_before_zeroing": tiny_sums,
        "calibration_dependency_sha256": dependencies,
        "scientific_source_lock": {
            "wind_generation_and_utilization": "National Energy Administration final 2024 monitoring statistics only",
            "wind_capacity_path": "National Energy Administration month-end installed-capacity series with declared daily interpolation",
            "hourly_shape": "supplied 2024 province-level ERA5-derived onshore-wind and solar profile",
            "commercial_annual_report_source_used": False,
            "scope": "national total-wind proxy level-corrects the onshore-wind profile; it is neither province validation nor an official onshore-only statistic",
        },
        "commercial_annual_report_source_used": False,
        "results_status": "RERUN_REQUIRED_16_PLUS_8",
    }
    (ROOT / "audits").mkdir(exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    from publication_source_common import write_source_fingerprint
    write_source_fingerprint(ROOT)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    build(force=args.force)


if __name__ == "__main__":
    main()
