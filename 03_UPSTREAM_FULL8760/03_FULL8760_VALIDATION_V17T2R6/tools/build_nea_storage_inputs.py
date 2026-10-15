#!/usr/bin/env python3
"""Rebuild the end-2025 inherited new-type-storage input from frozen evidence.

Scientific boundary
-------------------
The National Energy Administration (NEA) publishes exact national totals, exact
North/Northwest regional totals, exact power for the three largest provinces,
and a reported-above-5-GW set. Same-cutoff provincial-government or provincial
energy-authority releases add exact anchors for Gansu and Guizhou. No source
publishes a complete exact 31-province
inventory. This builder therefore creates a transparent *model reconstruction*:

* exact national power and energy are imposed;
* exact North and Northwest power totals are imposed;
* other regional powers close the national residual using the official rounded
  regional shares;
* exact province values and reported thresholds are imposed;
* all remaining power is allocated proportionally to a frozen, explicitly
  unverified study-supplied shape prior within each region;
* the primary spatial comparison uses a common exact national-average duration;
* a separate heterogeneous-duration sensitivity retains only the prior duration
  pattern and rescales it to the exact national energy total.

No row without an exact official province value is labelled as observed.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_VERSION = "NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2"
PRIOR = ROOT / "data/raw/storage/provincial_storage_prior_user_compiled_2025.csv"
REGIONAL = ROOT / "data/source_registry/nea_new_storage_national_regional_constraints_2025.csv"
PROVINCIAL = ROOT / "data/source_registry/nea_new_storage_provincial_constraints_2025.csv"
MAPPING = ROOT / "data/processed/model_zone_to_province_mapping_v2.csv"
TEMPLATE = ROOT / "base_model_v39/storage_base_template_v17.zip"
PROCESSED = ROOT / "data/processed"
REGISTRY = ROOT / "data/source_registry"
AUDITS = ROOT / "audits"

REGION_MAP = {
    "North": ["Beijing", "Tianjin", "Hebei", "Shanxi", "Shandong", "Inner_Mongolia"],
    "Northeast": ["Liaoning", "Jilin", "Heilongjiang"],
    "East": ["Shanghai", "Jiangsu", "Zhejiang", "Anhui", "Fujian"],
    "Central": ["Henan", "Hubei", "Hunan", "Jiangxi", "Sichuan", "Chongqing"],
    "Northwest": ["Shaanxi", "Gansu", "Qinghai", "Ningxia", "Xinjiang", "Tibet"],
    "South": ["Guangdong", "Guangxi", "Yunnan", "Guizhou", "Hainan"],
}
TOL_MW = 1.0e-6
TOL_MWH = 1.0e-5


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _one_value(df: pd.DataFrame, geography: str, metric: str) -> float:
    row = df.loc[df["geography"].eq(geography) & df["metric"].eq(metric), "value"]
    if len(row) != 1:
        raise ValueError(f"Expected one {geography}/{metric} constraint, found {len(row)}")
    return float(row.iloc[0])


def _allocate_region(
    frame: pd.DataFrame,
    target_mw: float,
    exact: dict[str, float],
    floors: dict[str, float],
) -> dict[str, float]:
    values: dict[str, float] = {}
    free = set(frame["province_en"].astype(str))
    remaining = float(target_mw)

    for province, value in exact.items():
        if province in free:
            values[province] = float(value)
            remaining -= float(value)
            free.remove(province)
    if remaining < -TOL_MW:
        raise ValueError(f"Exact province constraints exceed region target {target_mw}")

    while free:
        prior = (
            frame.set_index("province_en")
            .loc[sorted(free), "reconstruction_prior_power_mw"]
            .astype(float)
        )
        if (prior <= 0).any() or float(prior.sum()) <= 0:
            raise ValueError("Reconstruction prior must be strictly positive")
        proposed = prior / float(prior.sum()) * remaining
        violations = [
            province
            for province, value in proposed.items()
            if province in floors and value < floors[province] - TOL_MW
        ]
        if not violations:
            values.update({str(k): float(v) for k, v in proposed.items()})
            break
        for province in sorted(violations):
            values[province] = float(floors[province])
            remaining -= float(floors[province])
            free.remove(province)
        if remaining < -TOL_MW:
            raise ValueError("Reported province thresholds make regional reconstruction infeasible")

    if abs(sum(values.values()) - target_mw) > TOL_MW:
        raise ValueError("Regional allocation does not close")
    return values


def _inner_mongolia_split() -> dict[str, float]:
    with zipfile.ZipFile(TEMPLATE) as archive:
        gen = pd.read_csv(archive.open("inputs/gen_info.csv"))
        pred = pd.read_csv(archive.open("inputs/gen_build_predetermined.csv"))
    projects = gen.loc[
        gen["gen_tech"].isin(["Wind_Onshore", "Solar_Utility", "Solar_Distributed"]),
        ["GENERATION_PROJECT", "gen_load_zone"],
    ]
    cap = pred.groupby("GENERATION_PROJECT", as_index=False)["build_gen_predetermined"].sum()
    projects = projects.merge(cap, on="GENERATION_PROJECT", how="left").fillna(
        {"build_gen_predetermined": 0.0}
    )
    split = (
        projects.loc[
            projects["gen_load_zone"].isin(["East_Inner_Mongolia", "West_Inner_Mongolia"])
        ]
        .groupby("gen_load_zone")["build_gen_predetermined"]
        .sum()
    )
    if len(split) != 2 or float(split.sum()) <= 0:
        raise ValueError("Cannot derive the two-zone Inner Mongolia split from the retained template")
    return (split / float(split.sum())).to_dict()


def build() -> dict[str, object]:
    for path in [PRIOR, REGIONAL, PROVINCIAL, MAPPING, TEMPLATE]:
        if not path.exists():
            raise FileNotFoundError(path)

    prior = pd.read_csv(PRIOR)
    required_prior = {
        "province_en",
        "province_cn",
        "reconstruction_prior_power_mw",
        "reconstruction_prior_energy_mwh",
        "reconstruction_prior_duration_h",
        "data_version",
    }
    missing = required_prior - set(prior.columns)
    if missing:
        raise ValueError(f"Prior missing columns: {sorted(missing)}")
    if len(prior) != 31 or prior["province_en"].nunique() != 31:
        raise ValueError("Frozen reconstruction prior must contain 31 unique provinces")
    if set(prior["data_version"].astype(str)) != {DATA_VERSION}:
        raise ValueError("Reconstruction prior data_version mismatch")

    regional = pd.read_csv(REGIONAL)
    provincial = pd.read_csv(PROVINCIAL)
    for frame, label in [(regional, "regional"), (provincial, "provincial")]:
        if set(frame["data_version"].astype(str)) != {DATA_VERSION}:
            raise ValueError(f"{label} constraints data_version mismatch")

    national_power = _one_value(regional, "China", "power_mw")
    national_energy = _one_value(regional, "China", "energy_mwh")
    duration = national_energy / national_power
    region_targets = {
        region: _one_value(regional, region, "power_mw") for region in REGION_MAP
    }
    if abs(sum(region_targets.values()) - national_power) > TOL_MW:
        raise ValueError("Regional power constraints do not close to the national total")

    exact_rows = provincial.loc[provincial["constraint_type"].eq("official_exact_power_mw")]
    floor_rows = provincial.loc[
        provincial["constraint_type"].eq("official_reported_above_threshold_power_mw")
    ]
    exact = dict(zip(exact_rows["province_en"].astype(str), exact_rows["constraint_value_mw"].astype(float)))
    floors = dict(zip(floor_rows["province_en"].astype(str), floor_rows["constraint_value_mw"].astype(float)))

    p2r = {province: region for region, provinces in REGION_MAP.items() for province in provinces}
    prior["region"] = prior["province_en"].map(p2r)
    if prior["region"].isna().any():
        raise ValueError("At least one province is absent from REGION_MAP")

    allocation: dict[str, float] = {}
    for region, target in region_targets.items():
        allocation.update(
            _allocate_region(prior.loc[prior["region"].eq(region)].copy(), target, exact, floors)
        )

    province = prior.copy()
    province["new_storage_power_mw_model"] = province["province_en"].map(allocation).astype(float)
    province["new_storage_energy_mwh_standardized"] = (
        province["new_storage_power_mw_model"] * duration
    )
    heterogeneous_unscaled = (
        province["new_storage_power_mw_model"] * province["reconstruction_prior_duration_h"]
    )
    heterogeneous_scale = national_energy / float(heterogeneous_unscaled.sum())
    province["new_storage_energy_mwh_compiled_duration_sensitivity"] = (
        heterogeneous_unscaled * heterogeneous_scale
    )
    province["standardized_duration_h"] = duration
    province["compiled_duration_sensitivity_h"] = (
        province["new_storage_energy_mwh_compiled_duration_sensitivity"]
        / province["new_storage_power_mw_model"]
    )
    province["official_exact_power_mw"] = province["province_en"].map(exact)
    province["official_reported_threshold_power_mw"] = province["province_en"].map(floors)
    province["evidence_class"] = np.where(
        province["province_en"].isin(exact),
        "official_exact_power",
        np.where(
            province["province_en"].isin(floors),
            "official_threshold_plus_model_reconstruction",
            "model_reconstruction",
        ),
    )
    province["reconstruction_method"] = (
        "official-constrained regional proportional raking to a frozen unverified shape prior; "
        "exact national totals; exact North/Northwest totals; five same-cutoff exact province powers; "
        "conservative 5,000 MW floors for the seven remaining provinces officially reported above 5 GW"
    )
    province["inventory_interpretation"] = (
        "NEA-constrained model reconstruction; not an official exact 31-province inventory"
    )
    province["storage_scope"] = (
        "commissioned new-type storage at end-2025; pumped hydro excluded"
    )
    province["year"] = 2025
    province["data_version"] = DATA_VERSION
    province["use_in_main_model"] = "reconstructed_power_and_common_exact_national_duration"
    province = province.sort_values(
        ["region", "new_storage_power_mw_model"], ascending=[True, False]
    ).reset_index(drop=True)

    clean_columns = [
        "province_en",
        "province_cn",
        "region",
        "new_storage_power_mw_model",
        "new_storage_energy_mwh_standardized",
        "new_storage_energy_mwh_compiled_duration_sensitivity",
        "standardized_duration_h",
        "compiled_duration_sensitivity_h",
        "reconstruction_prior_power_mw",
        "reconstruction_prior_energy_mwh",
        "reconstruction_prior_duration_h",
        "official_exact_power_mw",
        "official_reported_threshold_power_mw",
        "evidence_class",
        "reconstruction_method",
        "inventory_interpretation",
        "storage_scope",
        "year",
        "data_version",
        "use_in_main_model",
    ]
    province = province[clean_columns]
    PROCESSED.mkdir(parents=True, exist_ok=True)
    province_path = PROCESSED / "new_storage_existing_by_province_2025_nea_constrained_reconstruction.csv"
    scope_alias = PROCESSED / "new_storage_existing_by_province_2025_nea_scope.csv"
    province.to_csv(province_path, index=False)
    province.to_csv(scope_alias, index=False)

    mapping = pd.read_csv(MAPPING)
    im_share = _inner_mongolia_split()
    zone_rows: list[dict[str, object]] = []
    for row in province.itertuples(index=False):
        zones = mapping.loc[mapping["province_en"].eq(row.province_en), "model_zone"].astype(str).tolist()
        if not zones:
            raise ValueError(f"No model-zone mapping for {row.province_en}")
        shares = im_share if row.province_en == "Inner_Mongolia" else {zones[0]: 1.0}
        if set(shares) != set(zones):
            raise ValueError(f"Model-zone split mismatch for {row.province_en}")
        for model_zone, share in shares.items():
            zone_rows.append(
                {
                    "model_zone": model_zone,
                    "province_en": row.province_en,
                    "province_cn": row.province_cn,
                    "region": row.region,
                    "existing_new_storage_power_mw": row.new_storage_power_mw_model * share,
                    "existing_new_storage_energy_mwh": row.new_storage_energy_mwh_standardized * share,
                    "existing_new_storage_energy_mwh_compiled_duration_sensitivity": row.new_storage_energy_mwh_compiled_duration_sensitivity * share,
                    "standardized_duration_h": duration,
                    "compiled_duration_sensitivity_h": row.compiled_duration_sensitivity_h,
                    "allocation_share": share,
                    "evidence_class": row.evidence_class,
                    "allocation_note": (
                        "Inner Mongolia split by retained-template predetermined onshore-wind plus solar capacity share"
                        if row.province_en == "Inner_Mongolia"
                        else "Province maps one-to-one to model zone"
                    ),
                    "inventory_interpretation": row.inventory_interpretation,
                    "data_version": DATA_VERSION,
                }
            )
    zone = pd.DataFrame(zone_rows).sort_values("model_zone").reset_index(drop=True)
    zone_path = PROCESSED / "existing_new_storage_allocated_to_model_zones_2025.csv"
    zone_alias = PROCESSED / "new_storage_existing_by_model_zone_2025_nea_scope.csv"
    zone.to_csv(zone_path, index=False)
    zone.to_csv(zone_alias, index=False)

    ledger = province[
        [
            "province_en",
            "province_cn",
            "region",
            "new_storage_power_mw_model",
            "official_exact_power_mw",
            "official_reported_threshold_power_mw",
            "evidence_class",
            "reconstruction_method",
            "inventory_interpretation",
            "data_version",
        ]
    ].copy()
    source_by_province = provincial.set_index("province_en")
    ledger["official_source_title"] = ledger["province_en"].map(
        source_by_province["source_title"]
    )
    ledger["official_source_url"] = ledger["province_en"].map(
        source_by_province["source_url"]
    )
    ledger["official_source_status"] = np.where(
        ledger["evidence_class"].eq("official_exact_power"),
        "exact province power is official",
        np.where(
            ledger["evidence_class"].str.contains("threshold"),
            "only membership in the officially reported above-5-GW set is official",
            "no exact province power is published in the national source",
        ),
    )
    ledger["official_source_title"] = ledger["official_source_title"].fillna(
        "China New Energy Storage Development Report 2026"
    )
    ledger["official_source_url"] = ledger["official_source_url"].fillna(
        regional.loc[regional["geography"].eq("China"), "source_url"].iloc[0]
    )
    ledger["cutoff_date"] = "2025-12-31"
    ledger["submission_language_lock"] = (
        "Model-reconstructed provincial allocation constrained by official national, regional, ranking and threshold evidence; not an official exact 31-province inventory."
    )
    ledger_path = REGISTRY / "provincial_storage_source_ledger_2025.csv"
    ledger.to_csv(ledger_path, index=False)

    regional_model = province.groupby("region", as_index=False)["new_storage_power_mw_model"].sum()
    regional_model["target_power_mw"] = regional_model["region"].map(region_targets)
    regional_model["difference_mw"] = (
        regional_model["new_storage_power_mw_model"] - regional_model["target_power_mw"]
    )
    summary_rows = [
        {
            "metric": "national_power_mw",
            "value": float(province["new_storage_power_mw_model"].sum()),
            "target": national_power,
            "pass": abs(float(province["new_storage_power_mw_model"].sum()) - national_power) <= TOL_MW,
            "note": "official exact end-2025 total",
        },
        {
            "metric": "national_standardized_energy_mwh",
            "value": float(province["new_storage_energy_mwh_standardized"].sum()),
            "target": national_energy,
            "pass": abs(float(province["new_storage_energy_mwh_standardized"].sum()) - national_energy) <= TOL_MWH,
            "note": "exact national energy with common duration",
        },
        {
            "metric": "national_compiled_duration_sensitivity_energy_mwh",
            "value": float(province["new_storage_energy_mwh_compiled_duration_sensitivity"].sum()),
            "target": national_energy,
            "pass": abs(float(province["new_storage_energy_mwh_compiled_duration_sensitivity"].sum()) - national_energy) <= TOL_MWH,
            "note": "prior duration pattern rescaled to exact national energy",
        },
        {"metric": "province_count", "value": float(province["province_en"].nunique()), "target": 31.0, "pass": province["province_en"].nunique() == 31, "note": ""},
        {"metric": "model_zone_count", "value": float(zone["model_zone"].nunique()), "target": 32.0, "pass": zone["model_zone"].nunique() == 32, "note": "Inner Mongolia split into two model zones"},
    ]
    for region_row in regional_model.itertuples(index=False):
        summary_rows.append(
            {
                "metric": f"region_{region_row.region}_power_mw",
                "value": float(region_row.new_storage_power_mw_model),
                "target": float(region_row.target_power_mw),
                "pass": abs(float(region_row.difference_mw)) <= TOL_MW,
                "note": "official exact for North/Northwest; normalized rounded-share closure for other regions",
            }
        )
    for province_name, value in exact.items():
        actual = float(
            province.loc[province["province_en"].eq(province_name), "new_storage_power_mw_model"].iloc[0]
        )
        summary_rows.append(
            {
                "metric": f"province_{province_name}_exact_power_mw",
                "value": actual,
                "target": value,
                "pass": abs(actual - value) <= TOL_MW,
                "note": "official exact",
            }
        )
    for province_name, floor in floors.items():
        actual = float(
            province.loc[province["province_en"].eq(province_name), "new_storage_power_mw_model"].iloc[0]
        )
        summary_rows.append(
            {
                "metric": f"province_{province_name}_reported_above_5gw_floor_mw",
                "value": actual,
                "target": floor,
                "pass": actual >= floor - TOL_MW,
                "note": "5,000 MW is a conservative model floor for an official above-5-GW statement",
            }
        )
    summary = pd.DataFrame(summary_rows)
    summary_path = PROCESSED / "new_storage_table_validation_summary.csv"
    summary.to_csv(summary_path, index=False)
    if not bool(summary["pass"].all()):
        raise ValueError("Storage reconstruction validation failed")

    audit = {
        "data_version": DATA_VERSION,
        "status": "PASS",
        "inventory_interpretation": "NEA-constrained model reconstruction; not an official exact 31-province inventory",
        "national_power_mw": national_power,
        "national_energy_mwh": national_energy,
        "national_average_duration_h": duration,
        "province_rows": len(province),
        "model_zone_rows": len(zone),
        "exact_province_count": len(exact),
        "official_threshold_province_count": len(floors),
        "model_reconstructed_province_count": int((province["evidence_class"] == "model_reconstruction").sum()),
        "files": {
            "province": {"path": province_path.relative_to(ROOT).as_posix(), "sha256": sha256(province_path)},
            "zone": {"path": zone_path.relative_to(ROOT).as_posix(), "sha256": sha256(zone_path)},
            "ledger": {"path": ledger_path.relative_to(ROOT).as_posix(), "sha256": sha256(ledger_path)},
            "validation": {"path": summary_path.relative_to(ROOT).as_posix(), "sha256": sha256(summary_path)},
            "prior": {"path": PRIOR.relative_to(ROOT).as_posix(), "sha256": sha256(PRIOR)},
            "regional_constraints": {"path": REGIONAL.relative_to(ROOT).as_posix(), "sha256": sha256(REGIONAL)},
            "provincial_constraints": {"path": PROVINCIAL.relative_to(ROOT).as_posix(), "sha256": sha256(PROVINCIAL)},
        },
        "results_status": "RERUN_REQUIRED_16_PLUS_8",
    }
    AUDITS.mkdir(exist_ok=True)
    audit_path = AUDITS / "NEA_STORAGE_INPUT_RECONSTRUCTION_AUDIT.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return audit


def main() -> None:
    build()


if __name__ == "__main__":
    main()
