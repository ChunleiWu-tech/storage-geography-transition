#!/usr/bin/env python3
"""Write V19 Layer-A result lineage after all eight strict solves."""
from __future__ import annotations
from pathlib import Path
import json, time
import pandas as pd
from publication_source_contract import DATA_VERSION, sha256, source_fingerprint_sha256
from publication_source_common import validate_case_fingerprint, validate_result_fingerprint

ROOT=Path(__file__).resolve().parents[1]
SCEN=ROOT/"storage_runner/scenarios_future_correction.csv"
CASES=ROOT/"future_correction_cases"
OUT=ROOT/"future_correction_outputs"
SUMMARY=OUT/"V19_LAYER_A_run_summary.csv"


def truth(v)->bool: return str(v).strip().lower() in {"true","1","yes","y","t"}

def main():
    names=pd.read_csv(SCEN).scenario.astype(str).tolist()
    if not SUMMARY.is_file(): raise FileNotFoundError(SUMMARY)
    tab=pd.read_csv(SUMMARY); ok=set(tab.loc[tab.publication_strict_success.astype(str).str.lower().isin({"true","1","yes"}),"scenario"].astype(str))
    if ok!=set(names): raise ValueError(f"Strict-success scenarios do not close: {sorted(ok)} != {sorted(names)}")
    rows=[]
    for s in names:
        case=CASES/s; out=OUT/f"{s}__main"; status=out/"solve_status.csv"; meta=case/"FUTURE_CORRECTION_SCENARIO_META.json"
        if not status.is_file() or not meta.is_file(): raise FileNotFoundError(f"Missing result/meta for {s}")
        st=pd.read_csv(status)
        if len(st)!=1 or str(st.iloc[0].get("stage1_termination_status",""))!="OPTIMAL" or not truth(st.iloc[0].get("strict_export_pass",False)): raise ValueError(f"{s} lacks strict OPTIMAL export")
        c_ok,c_reason,_=validate_case_fingerprint(ROOT,case,s); r_ok,r_reason=validate_result_fingerprint(ROOT,out,case,s)
        if not c_ok or not r_ok: raise ValueError(f"{s} fingerprint failure: {c_reason}; {r_reason}")
        m=json.loads(meta.read_text(encoding="utf-8"))
        if m.get("publication_source_data_version")!=DATA_VERSION or m.get("publication_source_fingerprint_sha256")!=source_fingerprint_sha256(): raise ValueError(f"{s} stale source lineage")
        record={"scenario":s,"case_meta_sha256":sha256(meta),"case_fingerprint_sha256":sha256(case/"audits/CASE_PUBLICATION_SOURCE_FINGERPRINT.json"),"result_fingerprint_sha256":sha256(out/"PUBLICATION_RESULT_SOURCE_FINGERPRINT.json"),"solve_status_sha256":sha256(status),"legacy_policy_audit_sha256":sha256(case/"audits/V17_SPATIAL_LEGACY_POLICY_AUDIT.json"),"transmission_application_audit_sha256":sha256(case/"audits/future_correction_transmission_application.json")}
        p=case/"audits/future_correction_portfolio_application.json"; record["portfolio_application_audit_sha256"]=sha256(p) if p.is_file() else None
        rows.append(record)
    payload={"status":"PASS","package_kind":"future_correction","version":"V19_LAYER_A_CORRECTION_2033","data_version":DATA_VERSION,"publication_source_fingerprint_sha256":source_fingerprint_sha256(),"generated_local_time":time.strftime("%Y-%m-%d %H:%M:%S"),"scenario_count":len(names),"scenarios":names,"summary_sha256":sha256(SUMMARY),"scenario_lineage":rows,"scope_lock":"2033 single-target-year correction experiment; no full transition timing claim"}
    p=ROOT/"audits/PUBLICATION_RESULT_LINEAGE_V19_LAYER_A.json"; p.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(payload,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
