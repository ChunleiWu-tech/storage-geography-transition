#!/usr/bin/env python3
"""Fail-closed source, full-8760 prepared-case and solved-result gate."""
from __future__ import annotations
from pathlib import Path
import argparse, json
import pandas as pd
from publication_source_common import (
    DATA_VERSION, EXPECTED_STORAGE_POWER_MW, EXPECTED_STORAGE_ENERGY_MWH,
    EXPECTED_VRE_PROVINCES, EXPECTED_VRE_HOURS, EXPECTED_SWITCH_VERSION,
    build_source_fingerprint, load_source_fingerprint, validate_case_fingerprint,
    validate_result_fingerprint,
)
ROOT=Path(__file__).resolve().parents[1]


def kind() -> str:
    return "sensitivity" if (ROOT/"storage_runner/scenarios_targetyear_linked.csv").is_file() else "main"


def expected_scenarios() -> list[str]:
    if kind()=="sensitivity":
        return pd.read_csv(ROOT/"storage_runner/scenarios_targetyear_linked.csv")["scenario"].astype(str).tolist()
    full=pd.read_csv(ROOT/"storage_runner/spatial_legacy_full_scenarios.csv")
    return full["scenario"].astype(str).tolist()


def source_checks() -> list[dict]:
    checks=[]
    def add(name,passed,detail): checks.append({"check":name,"passed":bool(passed),"detail":detail})
    try:
        stored=load_source_fingerprint(ROOT); current=build_source_fingerprint(ROOT)
        add("source_fingerprint_exact_current_match",stored==current,"stored and recomputed canonical source fingerprint")
        add("data_version",stored.get("data_version")==DATA_VERSION,stored.get("data_version"))
    except Exception as exc:
        add("source_fingerprint_load_and_recompute",False,str(exc)); return checks
    raw=pd.read_csv(ROOT/"data/processed/vre_cf_hourly_by_province.csv")
    cal=pd.read_csv(ROOT/"data/processed/vre_cf_hourly_by_province_publication_calibrated.csv")
    add("raw_vre_shape",len(raw)==EXPECTED_VRE_PROVINCES*EXPECTED_VRE_HOURS and raw.province_en.nunique()==EXPECTED_VRE_PROVINCES and raw.model_hour.nunique()==EXPECTED_VRE_HOURS,raw.shape)
    add("calibrated_vre_shape",len(cal)==len(raw) and cal.province_en.nunique()==EXPECTED_VRE_PROVINCES and cal.model_hour.nunique()==EXPECTED_VRE_HOURS,cal.shape)
    add("vre_bounds",raw[["solar_cf","onshore_wind_cf"]].stack().between(0,1).all() and cal[["solar_cf","onshore_wind_cf"]].stack().between(0,1).all(),"all capacity factors within [0,1]")
    bench=pd.read_csv(ROOT/"data/processed/vre_cf_national_benchmark_2024.csv").iloc[0]
    add("final_nea_wind_generation",abs(float(bench.final_wind_generation_twh)-996.8)<1e-9,float(bench.final_wind_generation_twh))
    add("nea_wind_utilization",abs(float(bench.reported_utilization_rate_fraction)-0.959)<1e-12,float(bench.reported_utilization_rate_fraction))
    add("wind_calibration_exact_closure",abs(float(bench.calibrated_model_capacity_weighted_cf)-float(bench.derived_gross_availability_cf))<5e-12,float(bench.calibrated_model_capacity_weighted_cf))
    prov=pd.read_csv(ROOT/"data/processed/new_storage_existing_by_province_2025_nea_scope.csv")
    zone=pd.read_csv(ROOT/"data/processed/existing_new_storage_allocated_to_model_zones_2025.csv")
    add("province_storage_rows",len(prov)==31,len(prov))
    add("zone_storage_rows",len(zone)==32,len(zone))
    add("storage_power_closure",abs(float(zone.existing_new_storage_power_mw.sum())-EXPECTED_STORAGE_POWER_MW)<1e-6,float(zone.existing_new_storage_power_mw.sum()))
    add("storage_energy_closure",abs(float(zone.existing_new_storage_energy_mwh.sum())-EXPECTED_STORAGE_ENERGY_MWH)<1e-6,float(zone.existing_new_storage_energy_mwh.sum()))
    aliases=[c for c in prov.columns if "136GW" in c or "351GWh" in c or "adjusted_to_national" in c]
    add("no_legacy_storage_alias_columns",not aliases,aliases)
    reg=pd.read_csv(ROOT/"data/source_registry/data_source_registry.csv").fillna("")
    gold=reg.apply(lambda col:col.astype(str).str.contains("Goldwind",case=False,regex=False)).any(axis=1)
    add("no_goldwind_scientific_source",not gold.any(),reg.loc[gold,"dataset_id"].tolist() if gold.any() else [])
    weak_screenshot_files=[
        ROOT/"data/processed/renewable_utilization_by_region_2025_from_screenshot.csv",
        ROOT/"data/processed/renewable_utilization_by_province_2025_model.csv",
    ]
    remaining=[p.relative_to(ROOT).as_posix() for p in weak_screenshot_files if p.exists()]
    add("weak_screenshot_datasets_removed",not remaining,remaining if remaining else "all screenshot-derived utilization tables absent")
    audit=json.loads((ROOT/"audits/vre_cf_publication_calibration_audit.json").read_text(encoding="utf-8"))
    dep=audit.get("calibration_dependency_sha256",{})
    add("wind_calibration_dependency_lock",set(dep)=={"raw_profile_sha256","monthly_anchor_sha256","generation_utilization_anchor_sha256","zone_mapping_sha256","template_sha256"},sorted(dep))
    lock=audit.get("scientific_source_lock",{})
    add("wind_anchor_nea_only",lock.get("commercial_annual_report_source_used") is False and "National Energy Administration" in str(lock.get("wind_generation_and_utilization","")),lock)
    q1=reg.loc[reg["dataset_id"].astype(str).eq("latest_new_storage_context_2026_q1")]
    add("latest_q1_storage_context_explicitly_not_model_input",len(q1)==1 and q1["use"].astype(str).str.contains("not model input",case=False,regex=False).all(),q1[["dataset_id","use","notes"]].to_dict("records"))
    lineage_path = ROOT / "SWITCH_CHINA_INPUT_LINEAGE_AUDIT.json"
    lineage=json.loads(lineage_path.read_text(encoding="utf-8"))
    add("switch_china_version",str(lineage.get("switch_china_version"))==EXPECTED_SWITCH_VERSION,lineage.get("switch_china_version"))
    add("switch_lineage_not_byte_identical_claim",lineage.get("study_template_is_byte_identical_to_raw_snapshot") is False,lineage.get("lineage_interpretation",""))
    raw_load=ROOT/"data/raw/load/figshare_29832701_Data_output.xlsx"
    processed_load=ROOT/"data/processed/figshare_load_2024_31province_8760_nonleap.csv"
    import hashlib
    def sha256(path):
        h=hashlib.sha256()
        with path.open("rb") as fh:
            for block in iter(lambda:fh.read(1024*1024),b""): h.update(block)
        return h.hexdigest()
    add("figshare_load_workbook_sha256",raw_load.is_file() and sha256(raw_load)=="a93ff6d4a2f4f8c36538fdc4704e2e88bef16347d217c456a99a7a97d56a19e0",sha256(raw_load) if raw_load.is_file() else "missing")
    add("figshare_processed_8760_sha256",processed_load.is_file() and sha256(processed_load)=="74944cc8d707561ac1b6e3210cfa7035eaa5d0e84a391d42c012de17304291ab",sha256(processed_load) if processed_load.is_file() else "missing")
    if processed_load.is_file():
        load=pd.read_csv(processed_load)
        add("figshare_processed_8760_shape",len(load)==8760 and load.model_hour.tolist()==list(range(1,8761)) and len([c for c in load.columns if c.endswith("_load_gw")])==31,load.shape)
        add("figshare_processed_8760_positive",load[[c for c in load.columns if c.endswith("_load_gw")]].stack().gt(0).all(),"all 31 x 8760 load values positive")
    model=(ROOT/"base_model_v39/cheer_power_storage_targetyear_v17t2r6_8760.jl").read_text(encoding="utf-8")
    add("model_full8760_chronology_compiled",all(token in model for token in ["full_year_cyclic","FULL_YEAR_TPS_IN_PERIOD","8760","tp_previous_commit = copy(tp_previous)"]),"full-year SOC and commitment chronology tokens")
    return checks


def case_checks() -> list[dict]:
    checks=source_checks()
    scenarios=expected_scenarios()
    root=ROOT/("sensitivity_cases" if kind()=="sensitivity" else "storage_cases")
    for s in scenarios:
        ok,reasons,_=validate_case_fingerprint(ROOT,root/s,s)
        checks.append({"check":f"case_fingerprint::{s}","passed":ok,"detail":reasons if reasons else "current source and input manifest match"})
        validation=root/s/"audits/FULL8760_PREPARED_INPUT_VALIDATION.json"
        validation_status=json.loads(validation.read_text(encoding="utf-8")).get("status") if validation.is_file() else "MISSING"
        checks.append({"check":f"full8760_prepared_validation::{s}","passed":validation_status=="PASS","detail":validation_status})
    pair_audit=ROOT/"audits/V17T2R6_FULL8760_PAIR_IDENTITY_AUDIT.json"
    pair_status=json.loads(pair_audit.read_text(encoding="utf-8")).get("status") if pair_audit.is_file() else "MISSING"
    checks.append({"check":"full8760_pair_identity","passed":pair_status=="PASS","detail":pair_status})
    checks.append({"check":"expected_case_count","passed":len(scenarios)==(4 if kind()=="sensitivity" else 16),"detail":len(scenarios)})
    return checks


def result_checks() -> list[dict]:
    # Do not hash every prepared case twice. Result validation already validates
    # the linked case fingerprint whenever a result fingerprint exists; before
    # rerun, missing result fingerprints therefore fail immediately and cleanly.
    checks=source_checks(); scenarios=expected_scenarios()
    cases=ROOT/("sensitivity_cases" if kind()=="sensitivity" else "storage_cases")
    results=ROOT/("sensitivity_outputs" if kind()=="sensitivity" else "outputs")
    for s in scenarios:
        ok,reasons=validate_result_fingerprint(ROOT,results/f"{s}__main",cases/s,s)
        checks.append({"check":f"result_fingerprint::{s}","passed":ok,"detail":reasons if reasons else "current source/case/result chain matches"})
    checks.append({"check":"expected_result_count","passed":len(scenarios)==(4 if kind()=="sensitivity" else 16),"detail":len(scenarios)})
    return checks


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--stage",choices=["source","cases","results"],default="source"); args=ap.parse_args()
    checks={"source":source_checks,"cases":case_checks,"results":result_checks}[args.stage]()
    passed=all(x["passed"] for x in checks)
    report={"status":"PASS" if passed else ("FAIL_RERUN_REQUIRED" if args.stage=="results" else "FAIL"),"stage":args.stage,"kind":kind(),"data_version":DATA_VERSION,"checks":checks,"checks_passed":sum(x["passed"] for x in checks),"checks_total":len(checks)}
    out=ROOT/"audits"/f"PUBLICATION_SOURCE_GATE_{args.stage.upper()}.json"; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if passed else (3 if args.stage=="results" else 2))
if __name__=="__main__": main()
