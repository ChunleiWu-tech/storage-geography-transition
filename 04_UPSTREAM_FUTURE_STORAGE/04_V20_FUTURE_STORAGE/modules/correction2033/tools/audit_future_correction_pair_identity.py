#!/usr/bin/env python3
"""Audit matched-pair identification and the deliberate V18 correction intervention."""
from __future__ import annotations
from pathlib import Path
import hashlib, json
from typing import Any
import pandas as pd
from publication_source_contract import expected_storage_power_mw, expected_storage_energy_mwh

ROOT=Path(__file__).resolve().parents[1]
SCEN=ROOT/"storage_runner/scenarios_future_correction.csv"
OUT=ROOT/"audits/V19_LAYER_A_FUTURE_CORRECTION_IDENTIFICATION_AUDIT.json"
PAIR_ALLOWED={"legacy_storage_policy.csv","gen_build_predetermined.csv"}
ADAPTIVE_ALLOWED={"gen_info.csv","gen_build_costs.csv"}


def sha(p:Path)->str:
    h=hashlib.sha256();
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def canonical(df:pd.DataFrame)->list[dict[str,Any]]:
    cols=sorted(df.columns); w=df[cols].copy()
    for c in cols: w[c]=w[c].astype(str)
    return w.sort_values(cols).to_dict("records")


def semantic_canonical(df:pd.DataFrame)->list[dict[str,Any]]:
    cols=sorted(df.columns); w=df[cols].copy()
    def norm(v):
        if pd.isna(v): return ""
        t=str(v).strip()
        if t in {".","true","false","True","False"}: return t.lower() if t.lower() in {"true","false"} else t
        try:
            x=float(t)
            if x==x and abs(x)!=float("inf"):
                return f"{x:.12g}"
        except Exception:
            pass
        return t
    for c in cols: w[c]=w[c].map(norm)
    return w.sort_values(cols).to_dict("records")


def input_compare(a:Path,b:Path,allowed:set[str])->tuple[list[dict],list[str]]:
    errors=[]; rows=[]; af={p.name for p in a.glob("*.csv")}; bf={p.name for p in b.glob("*.csv")}
    if af!=bf: errors.append(f"Input file sets differ: A-only={sorted(af-bf)} B-only={sorted(bf-af)}")
    for name in sorted(af&bf):
        eq=sha(a/name)==sha(b/name); ok=name in allowed
        rows.append({"file":name,"byte_identical":eq,"difference_allowed":ok})
        if not eq and not ok: errors.append(f"Unexpected input difference: {name}")
    return rows,errors


def audit_pair(pair_id:str,obs:str,opt:str)->dict[str,Any]:
    oi=ROOT/"future_correction_cases"/obs/"inputs"; pi=ROOT/"future_correction_cases"/opt/"inputs"
    rows,errors=input_compare(oi,pi,PAIR_ALLOWED)
    gen=pd.read_csv(oi/"gen_info.csv"); batteries=set(gen.loc[gen.gen_tech.astype(str).eq("Battery"),"GENERATION_PROJECT"].astype(str))
    op=pd.read_csv(oi/"gen_build_predetermined.csv"); pp=pd.read_csv(pi/"gen_build_predetermined.csv")
    om=op.GENERATION_PROJECT.astype(str).isin(batteries)&pd.to_numeric(op.build_year,errors="raise").eq(2023)
    pm=pp.GENERATION_PROJECT.astype(str).isin(batteries)&pd.to_numeric(pp.build_year,errors="raise").eq(2023)
    if canonical(op.loc[~om])!=canonical(pp.loc[~pm]): errors.append("gen_build_predetermined differs outside 2023 Battery rows")
    p=float(pd.to_numeric(op.loc[om,"build_gen_predetermined"],errors="coerce").sum()); e=float(pd.to_numeric(op.loc[om,"build_gen_energy_predetermined"],errors="coerce").sum())
    if abs(p-expected_storage_power_mw())>0.1 or abs(e-expected_storage_energy_mwh())>0.1: errors.append("Observed inherited Battery totals do not close to source contract")
    if int(pm.sum())!=0: errors.append("Optimized member must not contain fixed 2023 Battery predetermined rows")
    ol=pd.read_csv(oi/"legacy_storage_policy.csv").sort_values("model_zone").reset_index(drop=True); pl=pd.read_csv(pi/"legacy_storage_policy.csv").sort_values("model_zone").reset_index(drop=True)
    invariant=["model_zone","battery_project","legacy_reference_case","national_power_target_mw","national_energy_target_mwh","standardized_duration_h","empirical_cap_quantile","empirical_cap_ratio_to_2023_peak","zone_peak_2023_mw","raw_empirical_power_cap_mw","legacy_power_cap_mw","observed_grandfathered_cap_floor","legacy_cap_scope","legacy_capex_treatment"]
    if canonical(ol[invariant])!=canonical(pl[invariant]): errors.append("Legacy identification constants differ within matched pair")
    return {"pair_id":pair_id,"observed_scenario":obs,"optimized_scenario":opt,"status":"PASS" if not errors else "FAIL","errors":errors,"allowed_input_differences":sorted(PAIR_ALLOWED),"file_comparison":rows,"observed_fixed_legacy_power_mw":p,"observed_fixed_legacy_energy_mwh":e,"optimized_fixed_2023_battery_row_count":int(pm.sum())}


def _strip_ldes_gen(df:pd.DataFrame)->pd.DataFrame:
    return df.loc[~df["gen_tech"].astype(str).str.startswith("LDES_")].copy()


def _strip_ldes_cost(df:pd.DataFrame)->pd.DataFrame:
    return df.loc[~df["GENERATION_PROJECT"].astype(str).str.contains("-LDES_",regex=False)].copy()


def audit_adaptive_intervention(base:str,adaptive:str)->dict[str,Any]:
    ai=ROOT/"future_correction_cases"/base/"inputs"; bi=ROOT/"future_correction_cases"/adaptive/"inputs"
    rows,errors=input_compare(ai,bi,ADAPTIVE_ALLOWED)
    # After removing only added LDES projects, the two allowed tables must be exactly identical.
    ag=_strip_ldes_gen(pd.read_csv(ai/"gen_info.csv")); bg=_strip_ldes_gen(pd.read_csv(bi/"gen_info.csv"))
    if semantic_canonical(ag)!=semantic_canonical(bg): errors.append("Adaptive gen_info differs beyond added LDES candidates")
    ac=_strip_ldes_cost(pd.read_csv(ai/"gen_build_costs.csv")); bc=_strip_ldes_cost(pd.read_csv(bi/"gen_build_costs.csv"))
    if semantic_canonical(ac)!=semantic_canonical(bc): errors.append("Adaptive gen_build_costs differs beyond added LDES candidates")
    return {"baseline_scenario":base,"adaptive_scenario":adaptive,"status":"PASS" if not errors else "FAIL","errors":errors,"allowed_deliberate_input_differences":sorted(ADAPTIVE_ALLOWED),"file_comparison":rows,"intervention_statement":"BASE versus ADAPTIVE changes only the declared 2033 storage technology-duration opportunity set; inherited geography, chronology, carbon policy and transmission policy are unchanged."}


def audit_all_pairs(raise_on_error:bool=True)->dict[str,Any]:
    df=pd.read_csv(SCEN); pairs=[]
    for pid,g in df.groupby("pair_id",sort=True):
        o=g.loc[g.legacy_allocation_mode.eq("observed_standardized"),"scenario"].astype(str).tolist(); p=g.loc[g.legacy_allocation_mode.eq("optimized_reallocation"),"scenario"].astype(str).tolist()
        if len(o)!=1 or len(p)!=1: pairs.append({"pair_id":pid,"status":"FAIL","errors":["Pair must have one observed and one optimized member"]})
        else: pairs.append(audit_pair(str(pid),o[0],p[0]))
    interventions=[audit_adaptive_intervention("FC01_BASE_OBSERVED","FC03_ADAPTIVE_OBSERVED"),audit_adaptive_intervention("FC02_BASE_OPTIMAL","FC04_ADAPTIVE_OPTIMAL")]
    status="PASS" if all(x["status"]=="PASS" for x in pairs+interventions) else "FAIL"
    report={"version":"V19_LAYER_A_MATCHED_PAIR_IDENTIFICATION_R1","status":status,"matched_pair_audits":pairs,"primary_adaptive_intervention_audits":interventions,"difference_in_differences_design":"Legacy penalty is measured within each matched geography pair; correction value is the reduction of that penalty when the evidence-bounded future storage opportunity set is enabled."}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if raise_on_error and status!="PASS": raise ValueError(json.dumps(report,ensure_ascii=False,indent=2))
    return report

if __name__=="__main__": print(json.dumps(audit_all_pairs(True),ensure_ascii=False,indent=2))
