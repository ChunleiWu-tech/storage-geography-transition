#!/usr/bin/env python3
"""Fail-closed input validation for V19 Layer-A future-correction cases."""
from __future__ import annotations

from pathlib import Path
import argparse, json
from typing import Any
import pandas as pd

from publication_source_contract import expected_storage_power_mw, expected_storage_energy_mwh

ANCHOR=2023
TARGET=2033
PRIMARY_TECHS={"LDES_VRFB_10h","LDES_VRFB_24h","LDES_PSH_10h","LDES_PSH_24h"}
EXPANDED_TECHS={
    "LDES_CAES_10h","LDES_CAES_24h","LDES_CAES_100h","LDES_VRFB_10h","LDES_VRFB_24h",
    "LDES_H2_100h","LDES_PSH_10h","LDES_PSH_24h",
}
REQUIRED=[
    "periods.csv","timeseries.csv","timepoints.csv","gen_info.csv","gen_build_costs.csv",
    "gen_build_predetermined.csv","legacy_storage_policy.csv","loads.csv","variable_capacity_factors.csv",
    "hydro_timeseries.csv","carbon_policies.csv","capacity_plans.csv","zone_coincident_peak_demand.csv",
    "build_tx_limits.csv","transmission_lines.csv",
]


def _bool(v: Any)->bool:
    return str(v).strip().lower() in {"true","1","yes","y","t"}


def validate_case(case_dir: str|Path, meta: dict|None=None, raise_on_error: bool=True)->dict[str,Any]:
    case_dir=Path(case_dir); inp=case_dir/"inputs"; errors=[]; checks={}
    for name in REQUIRED:
        ok=(inp/name).is_file(); checks[f"required_{name}"]=ok
        if not ok: errors.append(f"Missing inputs/{name}")
    if errors:
        res={"status":"FAIL","errors":errors,"checks":checks}
        if raise_on_error: raise ValueError(json.dumps(res,ensure_ascii=False,indent=2))
        return res

    periods=pd.read_csv(inp/"periods.csv")
    pvals=sorted(pd.to_numeric(periods["INVESTMENT_PERIOD"],errors="raise").astype(int).tolist())
    checks["periods"]=pvals
    if pvals != [ANCHOR,TARGET]: errors.append(f"V19 Layer-A periods must be [2023,2033], found {pvals}")
    if meta and int(meta.get("target_year",-1))!=TARGET: errors.append("V19 Layer-A target_year must be 2033")

    ts=pd.read_csv(inp/"timeseries.csv"); tp=pd.read_csv(inp/"timepoints.csv")
    checks["timeseries_rows"]=len(ts); checks["timepoint_rows"]=len(tp)
    if len(ts)!=12: errors.append(f"Expected 12 representative months, found {len(ts)}")
    if len(tp)!=72: errors.append(f"Expected 72 four-hour timepoints, found {len(tp)}")
    if not (tp.groupby("timeseries").size()==6).all(): errors.append("Each representative day must contain six timepoints")
    if set(pd.to_numeric(ts["ts_period"],errors="raise").astype(int))!={TARGET}: errors.append("timeseries.csv must contain only 2033")
    dur=pd.to_numeric(ts["ts_duration_of_tp"],errors="raise")
    if not dur.sub(4.0).abs().lt(1e-9).all(): errors.append("Every representative timepoint must represent 4 h")
    if meta and int(meta.get("time_resolution_h",-1))!=4: errors.append("V19 Layer-A time_resolution_h must be 4")
    plen=dict(zip(pd.to_numeric(periods["INVESTMENT_PERIOD"],errors="raise").astype(int),pd.to_numeric(periods["period_end"],errors="raise")-pd.to_numeric(periods["period_start"],errors="raise")+1))
    repeats=pd.to_numeric(ts["ts_scale_to_period"],errors="raise")/float(plen[TARGET])
    checks["representative_days_per_year"]=float(repeats.sum())
    if not all(x>0 and abs(x-round(x))<1e-8 for x in repeats): errors.append("Month repeat counts must be positive integers")
    if abs(float(repeats.sum())-365.0)>1e-8: errors.append(f"Representative days sum to {repeats.sum()}, not 365")

    tp_ids=set(tp["timepoint_id"].astype(str)); ts_ids=set(ts["TIMESERIES"].astype(str))
    loads=pd.read_csv(inp/"loads.csv")
    if not set(loads["TIMEPOINT"].astype(str))<=tp_ids: errors.append("loads.csv contains non-target timepoints")
    vcf=pd.read_csv(inp/"variable_capacity_factors.csv")
    if not set(vcf["timepoint"].astype(str))<=tp_ids: errors.append("variable_capacity_factors.csv contains non-target timepoints")
    cf=pd.to_numeric(vcf["gen_max_capacity_factor"],errors="coerce")
    if cf.isna().any() or not cf.between(0,1).all(): errors.append("Variable capacity factors must be numeric in [0,1]")
    hydro=pd.read_csv(inp/"hydro_timeseries.csv")
    if not set(hydro["timeseries"].astype(str))<=ts_ids: errors.append("hydro_timeseries.csv contains non-target timeseries")

    costs=pd.read_csv(inp/"gen_build_costs.csv")
    by=sorted(pd.to_numeric(costs["build_year"],errors="raise").astype(int).unique().tolist())
    future=[y for y in by if y>ANCHOR]; checks["future_build_vintages"]=future
    if future != [TARGET]: errors.append(f"Only 2033 may be an endogenous future build vintage, found {future}")

    period_tables={"build_tx_limits.csv":"period","capacity_plans.csv":"period","carbon_policies.csv":"PERIOD","co2_injection_limits.csv":"PERIOD","fuel_cost.csv":"period","fuel_supply_curves.csv":"period","gen_ccs_energy_load.csv":"period","total_capacity_limits.csv":"period","zone_coincident_peak_demand.csv":"PERIOD"}
    for filename,col in period_tables.items():
        p=inp/filename
        if not p.is_file(): continue
        df=pd.read_csv(p); vals=set(pd.to_numeric(df[col],errors="raise").astype(int)) if len(df) else set()
        checks[f"{filename}_periods"]=sorted(vals)
        if not vals<={ANCHOR,TARGET}: errors.append(f"{filename} contains periods outside [2023,2033]")
        if filename not in {"total_capacity_limits.csv"} and TARGET not in vals: errors.append(f"{filename} missing 2033")

    policy=pd.read_csv(inp/"legacy_storage_policy.csv")
    if len(policy)!=32 or policy["model_zone"].nunique()!=32: errors.append("legacy_storage_policy must contain exactly 32 unique model zones")
    mode=str(policy["legacy_allocation_mode"].iloc[0]); checks["legacy_mode"]=mode
    if mode not in {"observed_standardized","optimized_reallocation"}: errors.append(f"Unexpected legacy mode {mode}")
    if meta and mode!=str(meta.get("legacy_allocation_mode")): errors.append("Legacy mode differs from scenario registry")
    p=float(policy["national_power_target_mw"].iloc[0]); e=float(policy["national_energy_target_mwh"].iloc[0]); d=float(policy["standardized_duration_h"].iloc[0])
    checks.update({"legacy_power_target_mw":p,"legacy_energy_target_mwh":e,"legacy_standardized_duration_h":d})
    if abs(p-expected_storage_power_mw())>0.1: errors.append("Legacy power target does not match publication source contract")
    if abs(e-expected_storage_energy_mwh())>0.1: errors.append("Legacy energy target does not match publication source contract")
    if abs(d-e/p)>1e-10: errors.append("Legacy standardized duration does not equal national energy/power")

    scope=str(meta.get("portfolio_scope","")) if meta else ""
    proxy=str(meta.get("ldes_proxy_mode","")) if meta else ""
    gen=pd.read_csv(inp/"gen_info.csv")
    got=set(gen.loc[gen["gen_tech"].astype(str).str.startswith("LDES_"),"gen_tech"].astype(str))
    checks["ldes_portfolio_techs"]=sorted(got)
    if scope=="baseline":
        if proxy!="disabled": errors.append("Baseline V18 case must have ldes_proxy_mode=disabled")
        if got: errors.append(f"Baseline case contains LDES candidates: {sorted(got)}")
    elif scope=="evidence_bounded":
        if proxy!="technology_portfolio_discrete": errors.append("Adaptive primary case must use technology_portfolio_discrete")
        if got!=PRIMARY_TECHS: errors.append(f"Primary portfolio mismatch: {sorted(got)}")
        if float(meta.get("ldes_proxy_min_duration_h"))!=10 or float(meta.get("ldes_proxy_max_duration_h"))!=24: errors.append("Primary adaptive duration envelope must be 10-24 h")
    elif scope=="expanded_pressure_test":
        if proxy!="technology_portfolio_discrete": errors.append("Expanded pressure test must use technology_portfolio_discrete")
        if got!=EXPANDED_TECHS: errors.append(f"Expanded portfolio mismatch: {sorted(got)}")
        if float(meta.get("ldes_proxy_min_duration_h"))!=10 or float(meta.get("ldes_proxy_max_duration_h"))!=100: errors.append("Expanded duration envelope must be 10-100 h")
        if meta.get("main_claim_eligible") is True: errors.append("Expanded pressure test cannot be main-claim eligible")
    else:
        errors.append(f"Unknown portfolio_scope={scope}")
    if _bool(meta.get("allow_cas",False)) if meta else False: errors.append("Generic continuous CAS proxy must remain disabled")

    nlr=case_dir/"audits/nlr_2025_battery_cost_application.json"; checks["nlr_audit_present"]=nlr.is_file()
    if not nlr.is_file(): errors.append("Missing NLR 2025 battery cost application audit")
    if scope!="baseline":
        pa=case_dir/"audits/future_correction_portfolio_application.json"; checks["portfolio_audit_present"]=pa.is_file()
        if not pa.is_file(): errors.append("Missing future correction portfolio audit")
    ta=case_dir/"audits/future_correction_transmission_application.json"; checks["transmission_audit_present"]=ta.is_file()
    if not ta.is_file(): errors.append("Missing future correction transmission audit")

    txcase=str(meta.get("transmission_case","")) if meta else ""
    lim=pd.read_csv(inp/"build_tx_limits.csv"); lines=pd.read_csv(inp/"transmission_lines.csv")
    if txcase=="TX_fixed":
        maxlim=float(pd.to_numeric(lim["build_trans_limit_mw"],errors="coerce").fillna(0).max())
        maxcap=float(pd.to_numeric(lines["trans_new_build_cap"],errors="coerce").fillna(0).max())
        flags=lines["trans_new_build_allowed"].astype(str).str.strip().str.lower()
        checks.update({"tx_fixed_period_limit_max_mw":maxlim,"tx_fixed_line_cap_max_mw":maxcap})
        if abs(maxlim)>1e-9 or abs(maxcap)>1e-9 or not flags.isin({"false","0","no","n","f"}).all(): errors.append("TX_fixed case still permits new transmission")
    elif txcase!="TX_policy": errors.append(f"Unknown transmission_case={txcase}")

    if meta:
        if str(meta.get("storage_chronology_mode"))!="monthly_linked": errors.append("V19 Layer-A storage chronology must be monthly_linked")
        if not _bool(meta.get("allow_new_battery",True)): errors.append("V19 Layer-A must allow endogenous new battery investment")
        if not _bool(meta.get("allow_new_pumped_hydro",True)): errors.append("V19 Layer-A must allow endogenous pumped-storage investment")

    res={
        "status":"PASS" if not errors else "FAIL","errors":errors,"checks":checks,
        "scope":{
            "design":"single_target_year_2033_adaptive_future_correction_reoptimization",
            "capacity_choice_endogenous":True,"province_or_model_zone_choice_endogenous":True,
            "technology_choice_endogenous":scope!="baseline","duration_choice_discrete":scope!="baseline",
            "full_transition_path_claim_supported":False,"investment_timing_claim_supported":False,
            "full_8760_hour_claim_supported":False,"endogenous_pre_target_builds_carried_in":False,
            "representative_time_resolution_h":4,
        },
    }
    res=json.loads(json.dumps(res,ensure_ascii=False,default=lambda x:x.item() if hasattr(x,"item") else str(x)))
    if raise_on_error and errors: raise ValueError(json.dumps(res,ensure_ascii=False,indent=2))
    return res


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("case_dir"); ap.add_argument("--meta"); a=ap.parse_args()
    meta=json.loads(Path(a.meta).read_text(encoding="utf-8")) if a.meta else None
    r=validate_case(a.case_dir,meta,raise_on_error=False); print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(0 if r["status"]=="PASS" else 1)

if __name__=="__main__": main()
