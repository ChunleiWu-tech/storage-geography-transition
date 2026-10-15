#!/usr/bin/env python3
"""Deterministic source/case/result fingerprint helpers for the publication package."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import hashlib, json

import pandas as pd

DATA_VERSION = "NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2"
EXPECTED_STORAGE_POWER_MW = 135930.0
EXPECTED_STORAGE_ENERGY_MWH = 351120.0
EXPECTED_VRE_PROVINCES = 31
EXPECTED_VRE_HOURS = 8760
EXPECTED_SWITCH_VERSION = "2.0.9"

LOCAL_SOURCE_FILES = [
    "data/raw/vre_cf/hourly_vre_capacity_factor_2024_CHN_province_withSP.csv.gz",
    "data/processed/vre_cf_hourly_by_province.csv",
    "data/processed/vre_cf_hourly_by_province_publication_calibrated.csv",
    "data/processed/vre_cf_validation_summary_2024.csv",
    "data/processed/vre_cf_validation_summary_publication_calibrated.csv",
    "data/processed/vre_cf_national_benchmark_2024.csv",
    "audits/vre_cf_ingest_audit.json",
    "audits/vre_cf_publication_calibration_audit.json",
    "data/processed/new_storage_existing_by_province_2025_nea_scope.csv",
    "data/processed/new_storage_existing_by_province_2025_nea_constrained_reconstruction.csv",
    "data/processed/existing_new_storage_allocated_to_model_zones_2025.csv",
    "data/processed/new_storage_existing_by_model_zone_2025_nea_scope.csv",
    "data/processed/new_storage_table_validation_summary.csv",
    "data/processed/nlr_2025_battery_4h_costs.csv",
    "data/processed/ldes_technology_portfolio_2033.csv",
    "data/raw/load/figshare_29832701_Data_output.xlsx",
    "data/processed/figshare_load_2024_31province_8760_nonleap.csv",
    "audits/FIGSHARE_2024_LOAD_DATA_QUALITY_AUDIT.csv",
    "data/source_registry/FULL8760_SOURCE_AND_METHOD_LEDGER.md",
    "data/source_registry/data_source_registry.csv",
    "data/source_registry/nea_wind_capacity_month_end_2024.csv",
    "data/source_registry/nea_wind_generation_utilization_2024.csv",
    "data/source_registry/nea_new_storage_national_regional_constraints_2025.csv",
    "data/source_registry/nea_new_storage_provincial_constraints_2025.csv",
    "data/source_registry/provincial_storage_source_ledger_2025.csv",
    "base_model_v39/storage_base_template_v17.zip",
]
PACKAGE_SOURCE_FILES = [
    "shared_source_snapshots/SWITCH_China_inputs_v2.0.9.zip",
    "shared_source_snapshots/hourly_vre_capacity_factor_2024_CHN_province_withSP.csv.gz",
    "shared_source_snapshots/NEA_2024_Renewable_Energy_Monitoring_Evaluation.doc",
    "shared_source_snapshots/NEA_China_New_Energy_Storage_Development_Report_2026.pdf",
    "shared_source_snapshots/official/PNNL_ESGC_Cost_Performance_Database_v2024.xlsx",
    "OFFICIAL_SOURCE_ARCHIVE_INDEX.csv",
    "OFFICIAL_SOURCE_ARCHIVE_INDEX.json",
    "SWITCH_CHINA_INPUT_LINEAGE_AUDIT.json",
    "SWITCH_CHINA_INPUT_LINEAGE_FILE_AUDIT.csv",
]


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_hash(obj: Any) -> str:
    payload=json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_paths(root: Path) -> dict[str, Path]:
    # V17T2R6 is deliberately standalone: the shared upstream snapshots are
    # bundled inside this module instead of being resolved from a parent folder.
    package_root=root
    out={rel:root/rel for rel in LOCAL_SOURCE_FILES}
    out.update({f"../{rel}":package_root/rel for rel in PACKAGE_SOURCE_FILES})
    return out


def build_source_fingerprint(root: Path) -> dict[str, Any]:
    paths=source_paths(root)
    missing=[name for name,path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing publication source files: "+", ".join(missing))
    files={name:{"sha256":sha256(path),"size_bytes":path.stat().st_size} for name,path in sorted(paths.items())}
    benchmark=pd.read_csv(root/"data/processed/vre_cf_national_benchmark_2024.csv")
    if len(benchmark)!=1:
        raise ValueError("VRE national benchmark must contain exactly one row")
    b=benchmark.iloc[0]
    zone=pd.read_csv(root/"data/processed/existing_new_storage_allocated_to_model_zones_2025.csv")
    lineage=json.loads((root/"SWITCH_CHINA_INPUT_LINEAGE_AUDIT.json").read_text(encoding="utf-8"))
    return {
        "schema_version":"publication_source_fingerprint_v2",
        "data_version":DATA_VERSION,
        "source_files":files,
        "raw_vre_gzip_sha256":files["../shared_source_snapshots/hourly_vre_capacity_factor_2024_CHN_province_withSP.csv.gz"]["sha256"],
        "official_source_archive":{
            "index_csv_sha256":files["../OFFICIAL_SOURCE_ARCHIVE_INDEX.csv"]["sha256"],
            "index_json_sha256":files["../OFFICIAL_SOURCE_ARCHIVE_INDEX.json"]["sha256"],
            "nea_2024_renewable_monitoring_document_sha256":files["../shared_source_snapshots/NEA_2024_Renewable_Energy_Monitoring_Evaluation.doc"]["sha256"],
            "nea_2026_storage_report_pdf_sha256":files["../shared_source_snapshots/NEA_China_New_Energy_Storage_Development_Report_2026.pdf"]["sha256"],
        },
        "wind_calibration":{
            "benchmark_year":int(b["benchmark_year"]),
            "final_wind_generation_twh":float(b["final_wind_generation_twh"]),
            "utilization_rate_fraction":float(b["reported_utilization_rate_fraction"]),
            "integrated_average_capacity_gw":float(b["integrated_average_wind_capacity_gw"]),
            "target_cf_8760":float(b["derived_gross_availability_cf"]),
            "raw_processed_profile_sha256":files["data/processed/vre_cf_hourly_by_province.csv"]["sha256"],
            "calibrated_profile_sha256":files["data/processed/vre_cf_hourly_by_province_publication_calibrated.csv"]["sha256"],
            "benchmark_sha256":files["data/processed/vre_cf_national_benchmark_2024.csv"]["sha256"],
            "audit_sha256":files["audits/vre_cf_publication_calibration_audit.json"]["sha256"],
            "method":"NEA-final national total-wind anchor; monotonic level correction of supplied province-level onshore profile",
            "scope_lock":"national proxy only; not province validation and not an official onshore-only statistic",
        },
        "storage_stock":{
            "cutoff_date":"2025-12-31",
            "national_power_mw":float(zone["existing_new_storage_power_mw"].sum()),
            "national_energy_mwh":float(zone["existing_new_storage_energy_mwh"].sum()),
            "zone_input_sha256":files["data/processed/existing_new_storage_allocated_to_model_zones_2025.csv"]["sha256"],
            "province_input_sha256":files["data/processed/new_storage_existing_by_province_2025_nea_scope.csv"]["sha256"],
            "province_ledger_sha256":files["data/source_registry/provincial_storage_source_ledger_2025.csv"]["sha256"],
            "model_input_interpretation":"NEA-constrained 31-province reconstruction with exact national common duration; not an official exact provincial census",
        },
        "engineering_cost_sources":{
            "nlr_2025_battery_table_sha256":files["data/processed/nlr_2025_battery_4h_costs.csv"]["sha256"],
            "pnnl_v2024_workbook_sha256":files["../shared_source_snapshots/official/PNNL_ESGC_Cost_Performance_Database_v2024.xlsx"]["sha256"],
            "ldes_2033_portfolio_sha256":files["data/processed/ldes_technology_portfolio_2033.csv"]["sha256"],
            "battery_policy":"NLR 2025 direct annual low/mid/high complete four-hour system costs; no arbitrary multiplier or reverse calibration",
            "ldes_policy":"PNNL v2024 technology-specific discrete duration portfolio; 2033 linearly interpolated from 2030 and 2035 Point values",
        },
        "full8760_chronology_sources":{
            "load_article_doi":"10.1038/s41597-026-07327-8",
            "load_data_doi":"10.6084/m9.figshare.29832701.v3",
            "load_license":"CC BY 4.0",
            "raw_load_workbook_sha256":files["data/raw/load/figshare_29832701_Data_output.xlsx"]["sha256"],
            "processed_nonleap_load_sha256":files["data/processed/figshare_load_2024_31province_8760_nonleap.csv"]["sha256"],
            "load_use":"normalized within-province hourly shape only; every 2033 model-zone annual MWh remains locked to its four-hour template",
            "vre_time_alignment":"ERA5 UTC to China Standard Time by deterministic circular +8 h shift",
            "hydro_time_alignment":"frozen monthly average/minimum flow envelope applied over all actual hours of each calendar month",
        },
        "switch_china":{
            "raw_inputs_version":str(lineage.get("switch_china_version","")),
            "raw_inputs_zip_sha256":files["../shared_source_snapshots/SWITCH_China_inputs_v2.0.9.zip"]["sha256"],
            "study_template_sha256":files["base_model_v39/storage_base_template_v17.zip"]["sha256"],
            "lineage_interpretation":"foundational source snapshot plus explicit study-derived aggregation/extension layer; no byte-identical claim",
        },
        "latest_context_not_used_as_model_input":{
            "as_of":"2026-03-31",
            "new_storage_power_status":">140 GW",
            "reason_excluded":"No nationally closed energy and province distribution were released for that cut-off; mixing it with end-2025 energy/geography would create an incoherent stock vector.",
        },
        "results_status":"RERUN_REQUIRED_FULL8760_FOUR_CASES",
        "publication_release_allowed":False,
    }


def write_source_fingerprint(root: Path) -> dict[str, Any]:
    fp=build_source_fingerprint(root)
    path=root/"audits/PUBLICATION_SOURCE_FINGERPRINT.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(fp,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return fp


def load_source_fingerprint(root: Path) -> dict[str, Any]:
    path=root/"audits/PUBLICATION_SOURCE_FINGERPRINT.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def source_fingerprint_sha(root: Path) -> str:
    return sha256(root/"audits/PUBLICATION_SOURCE_FINGERPRINT.json")


def _input_manifest(case_dir: Path) -> list[dict[str, Any]]:
    inp=case_dir/"inputs"
    if not inp.is_dir():
        raise FileNotFoundError(f"Missing case input directory: {inp}")
    rows=[]
    for path in sorted(p for p in inp.rglob("*") if p.is_file()):
        rows.append({"path":path.relative_to(case_dir).as_posix(),"sha256":sha256(path),"size_bytes":path.stat().st_size})
    if not rows:
        raise ValueError(f"No input files found in {inp}")
    return rows


def write_base_fingerprint(root: Path, base_dir: Path) -> dict[str, Any]:
    rows=_input_manifest(base_dir)
    obj={
        "schema_version":"publication_base_fingerprint_v1",
        "data_version":DATA_VERSION,
        "source_fingerprint_sha256":source_fingerprint_sha(root),
        "input_manifest_sha256":canonical_hash(rows),
        "input_files":rows,
    }
    path=base_dir/"audits/BASE_PUBLICATION_SOURCE_FINGERPRINT.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return obj


def validate_base_fingerprint(root: Path, base_dir: Path) -> tuple[bool,list[str]]:
    p=base_dir/"audits/BASE_PUBLICATION_SOURCE_FINGERPRINT.json"
    reasons=[]
    if not p.is_file(): return False,["missing base fingerprint"]
    try: obj=json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc: return False,[f"invalid base fingerprint: {exc}"]
    if obj.get("data_version")!=DATA_VERSION: reasons.append("base data_version mismatch")
    if obj.get("source_fingerprint_sha256")!=source_fingerprint_sha(root): reasons.append("base source fingerprint mismatch")
    try:
        rows=_input_manifest(base_dir)
        if obj.get("input_manifest_sha256")!=canonical_hash(rows): reasons.append("base input manifest mismatch")
    except Exception as exc: reasons.append(str(exc))
    return not reasons,reasons


def _scenario_registry_contract(root: Path, scenario: str, case_kind: str) -> dict[str, Any]:
    rel = "storage_runner/scenarios_targetyear_linked.csv" if case_kind == "sensitivity" else "storage_runner/scenarios_storage_master.csv"
    path = root / rel
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    rows = frame.loc[frame["scenario"].astype(str).eq(str(scenario))]
    if len(rows) != 1:
        raise ValueError(f"Expected one scenario-registry row for {scenario}; found {len(rows)}")
    record = {}
    for key, value in rows.iloc[0].to_dict().items():
        if pd.isna(value):
            value = None
        elif hasattr(value, "item"):
            value = value.item()
        record[str(key)] = value
    return {
        "scenario_registry_file": rel,
        "scenario_registry_sha256": sha256(path),
        "scenario_row_sha256": canonical_hash(record),
        "scenario_runtime_contract": record,
    }


def write_case_fingerprint(root: Path, case_dir: Path, scenario: str, case_kind: str, metadata_filename: str) -> dict[str, Any]:
    rows=_input_manifest(case_dir)
    meta=case_dir/metadata_filename
    registry=_scenario_registry_contract(root, scenario, case_kind)
    obj={
        "schema_version":"publication_case_fingerprint_v2",
        "data_version":DATA_VERSION,
        "scenario":scenario,
        "case_kind":case_kind,
        "source_fingerprint_sha256":source_fingerprint_sha(root),
        "input_manifest_sha256":canonical_hash(rows),
        "input_files":rows,
        "metadata_file":metadata_filename,
        "metadata_sha256":sha256(meta) if meta.is_file() else None,
        **registry,
    }
    p=case_dir/"audits/CASE_PUBLICATION_SOURCE_FINGERPRINT.json"
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return obj


def validate_case_fingerprint(root: Path, case_dir: Path, scenario: str|None=None) -> tuple[bool,list[str],dict[str,Any]|None]:
    p=case_dir/"audits/CASE_PUBLICATION_SOURCE_FINGERPRINT.json"
    reasons=[]
    if not p.is_file(): return False,["missing case fingerprint"],None
    try: obj=json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc: return False,[f"invalid case fingerprint: {exc}"],None
    if obj.get("schema_version")!="publication_case_fingerprint_v2": reasons.append("case fingerprint schema mismatch")
    if obj.get("data_version")!=DATA_VERSION: reasons.append("case data_version mismatch")
    current_scenario = str(scenario or obj.get("scenario", ""))
    if scenario and obj.get("scenario")!=scenario: reasons.append("case scenario mismatch")
    if obj.get("source_fingerprint_sha256")!=source_fingerprint_sha(root): reasons.append("case source fingerprint mismatch")
    try:
        rows=_input_manifest(case_dir)
        if obj.get("input_manifest_sha256")!=canonical_hash(rows): reasons.append("case input manifest mismatch")
    except Exception as exc: reasons.append(str(exc))
    meta=case_dir/str(obj.get("metadata_file",""))
    if not meta.is_file(): reasons.append("case metadata missing")
    elif obj.get("metadata_sha256")!=sha256(meta): reasons.append("case metadata hash mismatch")
    try:
        registry=_scenario_registry_contract(root,current_scenario,str(obj.get("case_kind","")))
        for key in ("scenario_registry_file","scenario_registry_sha256","scenario_row_sha256","scenario_runtime_contract"):
            if obj.get(key)!=registry.get(key): reasons.append(f"case {key} mismatch")
    except Exception as exc:
        reasons.append(f"scenario registry validation failed: {exc}")
    return not reasons,reasons,obj


def write_result_fingerprint(root: Path, result_dir: Path, case_dir: Path, scenario: str, case_kind: str) -> dict[str, Any]:
    ok,reasons,case_obj=validate_case_fingerprint(root,case_dir,scenario)
    if not ok:
        raise ValueError("Cannot stamp result; case fingerprint invalid: "+"; ".join(reasons))
    status=result_dir/"solve_status.csv"
    if not status.is_file(): raise FileNotFoundError(status)
    obj={
        "schema_version":"publication_result_fingerprint_v1",
        "data_version":DATA_VERSION,
        "scenario":scenario,
        "case_kind":case_kind,
        "source_fingerprint_sha256":source_fingerprint_sha(root),
        "case_fingerprint_sha256":sha256(case_dir/"audits/CASE_PUBLICATION_SOURCE_FINGERPRINT.json"),
        "case_input_manifest_sha256":case_obj["input_manifest_sha256"],
        "solve_status_sha256":sha256(status),
    }
    p=result_dir/"PUBLICATION_RESULT_SOURCE_FINGERPRINT.json"
    p.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return obj


def validate_result_fingerprint(root: Path, result_dir: Path, case_dir: Path, scenario: str) -> tuple[bool,list[str]]:
    p=result_dir/"PUBLICATION_RESULT_SOURCE_FINGERPRINT.json"
    reasons=[]
    if not p.is_file(): return False,["missing result fingerprint"]
    try: obj=json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc: return False,[f"invalid result fingerprint: {exc}"]
    ok,case_reasons,_=validate_case_fingerprint(root,case_dir,scenario)
    if not ok: reasons.extend("case: "+x for x in case_reasons)
    if obj.get("data_version")!=DATA_VERSION: reasons.append("result data_version mismatch")
    if obj.get("scenario")!=scenario: reasons.append("result scenario mismatch")
    if obj.get("source_fingerprint_sha256")!=source_fingerprint_sha(root): reasons.append("result source fingerprint mismatch")
    cp=case_dir/"audits/CASE_PUBLICATION_SOURCE_FINGERPRINT.json"
    if cp.is_file() and obj.get("case_fingerprint_sha256")!=sha256(cp): reasons.append("result case fingerprint mismatch")
    status=result_dir/"solve_status.csv"
    if not status.is_file(): reasons.append("result solve_status missing")
    elif obj.get("solve_status_sha256")!=sha256(status): reasons.append("result solve_status hash mismatch")
    return not reasons,reasons
