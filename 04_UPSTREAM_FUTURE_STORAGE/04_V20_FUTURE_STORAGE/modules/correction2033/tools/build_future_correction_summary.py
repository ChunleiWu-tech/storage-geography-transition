#!/usr/bin/env python3
"""Build strict V19 Layer-A correction metrics and Figure-6 source tables.

All tables are created only from promoted strict-OPTIMAL results.  TIME_LIMIT,
NO_SOLUTION or incomplete exports are rejected.
"""
from __future__ import annotations
from pathlib import Path
import json, math
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"future_correction_outputs"
TABLE=OUT/"publication_tables"
SCEN=pd.read_csv(ROOT/"storage_runner/scenarios_future_correction.csv")
TARGET=2033


def outdir(s:str)->Path: return OUT/f"{s}__main"

def one_row(path:Path)->dict:
    df=pd.read_csv(path)
    if len(df)!=1: raise ValueError(f"Expected one row in {path}")
    return df.iloc[0].to_dict()

def truth(v)->bool: return str(v).strip().lower() in {"true","1","yes","y","t"}

def strict_status(s:str)->dict:
    d=one_row(outdir(s)/"solve_status.csv")
    for k,w in {"stage1_termination_status":"OPTIMAL","stage1_primal_status":"FEASIBLE_POINT","stage1_dual_status":"FEASIBLE_POINT"}.items():
        if str(d.get(k))!=w: raise ValueError(f"{s}: {k}={d.get(k)} expected {w}")
    for k in ["stage1_native_solver_certificate_pass","stage1_native_algorithm_gate_pass","strict_physical_audit_pass","result_export_complete","strict_export_pass"]:
        if not truth(d.get(k)): raise ValueError(f"{s}: {k}=false")
    return d

def annual_cost(s:str)->float:
    df=pd.read_csv(outdir(s)/"electricity_cost.csv"); row=df.loc[pd.to_numeric(df.period,errors="raise").eq(TARGET)]
    if len(row)!=1: raise ValueError(f"{s}: expected one electricity_cost row for {TARGET}")
    v=float(row["SystemCost_annualized_usd_per_yr"].iloc[0])
    if not math.isfinite(v): raise ValueError(f"{s}: nonfinite annual system cost")
    return v

def future_builds(s:str)->pd.DataFrame:
    g=pd.read_csv(outdir(s)/"BuildGen.csv"); e=pd.read_csv(outdir(s)/"BuildStorageEnergy.csv")
    g=g.loc[pd.to_numeric(g.build_year,errors="raise").eq(TARGET)].copy()
    e=e.loc[pd.to_numeric(e.build_year,errors="raise").eq(TARGET)].copy()
    storage_tech=set(e.technology.astype(str))
    g=g.loc[g.technology.astype(str).isin(storage_tech)].copy()
    keys=["GENERATION_PROJECT","province","technology","build_year"]
    x=g[keys+["BuildGen"]].merge(e[keys+["BuildStorageEnergy_MWh"]],on=keys,how="outer").fillna({"BuildGen":0.0,"BuildStorageEnergy_MWh":0.0})
    x["build_power_mw"]=pd.to_numeric(x.BuildGen,errors="coerce").fillna(0.0)
    x["build_energy_mwh"]=pd.to_numeric(x.BuildStorageEnergy_MWh,errors="coerce").fillna(0.0)
    x["duration_h"]=x.build_energy_mwh/x.build_power_mw.where(x.build_power_mw.abs()>1e-9)
    x.insert(0,"scenario",s)
    role=str(SCEN.loc[SCEN.scenario.eq(s),"experiment_role"].iloc[0])
    x["experiment_role"]=role
    x["main_claim_eligible"]=role in {"reference","primary_correction"}
    return x[["scenario","experiment_role","province","technology","build_year","build_power_mw","build_energy_mwh","duration_h","main_claim_eligible"]]

def tx_build(s:str)->float:
    df=pd.read_csv(outdir(s)/"BuildTx.csv"); df=df.loc[pd.to_numeric(df.build_year,errors="raise").eq(TARGET)]
    col="BuildTx" if "BuildTx" in df.columns else next(c for c in df.columns if c.lower().startswith("buildtx"))
    return float(pd.to_numeric(df[col],errors="coerce").fillna(0).sum())

def tech_label(t:str)->str:
    return {"Battery":"Li-ion 4 h","Hydro_Pumped":"Base PSH"}.get(t,t.replace("LDES_VRFB_","VRFB ").replace("LDES_PSH_","PSH ").replace("LDES_CAES_","CAES ").replace("LDES_H2_","H2 "))

def main()->None:
    missing=[s for s in SCEN.scenario.astype(str) if not (outdir(s)/"solve_status.csv").is_file()]
    if missing: raise SystemExit("Missing promoted V19 Layer-A outputs: "+", ".join(missing))
    for s in SCEN.scenario.astype(str): strict_status(s)
    from publication_source_gate import result_checks
    gate=result_checks(); bad=[x for x in gate if not x["passed"]]
    if bad: raise ValueError("V19 Layer-A result lineage gate failed: "+json.dumps(bad,ensure_ascii=False))

    TABLE.mkdir(parents=True,exist_ok=True)
    costs={s:annual_cost(s) for s in SCEN.scenario.astype(str)}
    builds=pd.concat([future_builds(s) for s in SCEN.scenario.astype(str)],ignore_index=True)
    builds["technology_label"]=builds.technology.map(tech_label)
    builds.to_csv(TABLE/"future_storage_build_by_zone_tech.csv",index=False)

    pair_rows=[]
    for pid,g in SCEN.groupby("pair_id",sort=True):
        obs=str(g.loc[g.legacy_allocation_mode.eq("observed_standardized"),"scenario"].iloc[0]); opt=str(g.loc[g.legacy_allocation_mode.eq("optimized_reallocation"),"scenario"].iloc[0])
        oc,pc=costs[obs],costs[opt]; pen=oc-pc
        pair_rows.append({"pair_id":pid,"observed_scenario":obs,"optimized_scenario":opt,"portfolio_scope":str(g.portfolio_scope.iloc[0]),"transmission_case":str(g.transmission_case.iloc[0]),"observed_annual_cost_usd_per_yr":oc,"optimized_annual_cost_usd_per_yr":pc,"legacy_penalty_usd_per_yr":pen,"legacy_penalty_million_usd_per_yr":pen/1e6,"legacy_penalty_fraction_of_optimized":pen/pc if abs(pc)>1e-12 else None,"main_claim_eligible":str(g.experiment_role.iloc[0]) in {"reference","primary_correction"}})
    pairs=pd.DataFrame(pair_rows); pairs.to_csv(TABLE/"future_correction_pair_costs.csv",index=False)
    ps=pairs.set_index("pair_id")
    l0=float(ps.loc["FC_BASE","legacy_penalty_usd_per_yr"]); l1=float(ps.loc["FC_ADAPTIVE","legacy_penalty_usd_per_yr"])
    correction=l0-l1; repair=correction/l0 if abs(l0)>1e-12 else None
    txfix=float(ps.loc["FC_ADAPTIVE_TXFIXED","legacy_penalty_usd_per_yr"]); expanded=float(ps.loc["FC_EXPANDED_PRESSURE","legacy_penalty_usd_per_yr"])
    metrics=pd.DataFrame([
        {"metric":"Baseline residual legacy lock-in","value":l0/1e6,"unit":"million USD yr-1","main_claim_eligible":True},
        {"metric":"Adaptive residual legacy lock-in","value":l1/1e6,"unit":"million USD yr-1","main_claim_eligible":True},
        {"metric":"Adaptive correction value","value":correction/1e6,"unit":"million USD yr-1","main_claim_eligible":True},
        {"metric":"Repair fraction","value":repair,"unit":"fraction","main_claim_eligible":True},
        {"metric":"Observed adaptive option value","value":(costs["FC01_BASE_OBSERVED"]-costs["FC03_ADAPTIVE_OBSERVED"])/1e6,"unit":"million USD yr-1","main_claim_eligible":True},
        {"metric":"Optimized adaptive option value","value":(costs["FC02_BASE_OPTIMAL"]-costs["FC04_ADAPTIVE_OPTIMAL"])/1e6,"unit":"million USD yr-1","main_claim_eligible":True},
        {"metric":"TX-fixed adaptive residual lock-in","value":txfix/1e6,"unit":"million USD yr-1","main_claim_eligible":False},
        {"metric":"Expanded-portfolio residual lock-in","value":expanded/1e6,"unit":"million USD yr-1","main_claim_eligible":False},
    ])
    metrics.to_csv(TABLE/"future_correction_metrics.csv",index=False)

    mix=(builds.groupby(["scenario","technology","technology_label"],as_index=False)[["build_power_mw","build_energy_mwh"]].sum())
    mix["build_power_gw"]=mix.build_power_mw/1000; mix["build_energy_gwh"]=mix.build_energy_mwh/1000
    mix.to_csv(TABLE/"future_correction_technology_mix.csv",index=False)

    tx=pd.DataFrame([{"scenario":s,"transmission_build_mw":tx_build(s),"transmission_build_gw":tx_build(s)/1000} for s in SCEN.scenario.astype(str)])
    tx.to_csv(TABLE/"future_correction_tx_build.csv",index=False)

    # Fig. 6a: strict correction of within-pair lock-in (difference-in-differences).
    pd.DataFrame([
        {"experiment":"Baseline future set","legacy_penalty_million_usd_per_yr":l0/1e6,"main_claim_eligible":True},
        {"experiment":"Adaptive storage set","legacy_penalty_million_usd_per_yr":l1/1e6,"main_claim_eligible":True},
    ]).to_csv(TABLE/"fig6a_lockin_repair.csv",index=False)

    # Fig. 6b: primary adaptive storage technology mix, observed vs optimized inheritance.
    mix.loc[mix.scenario.isin(["FC03_ADAPTIVE_OBSERVED","FC04_ADAPTIVE_OPTIMAL"])].to_csv(TABLE/"fig6b_technology_mix.csv",index=False)

    # Fig. 6c/d: where and duration under the real inherited geography (primary correction case).
    pbuild=builds.loc[builds.scenario.eq("FC03_ADAPTIVE_OBSERVED")].copy()
    provtech=pbuild.groupby(["province","technology_label"],as_index=False)[["build_power_mw","build_energy_mwh"]].sum()
    provtech["build_power_gw"]=provtech.build_power_mw/1000; provtech["build_energy_gwh"]=provtech.build_energy_mwh/1000
    provtech.to_csv(TABLE/"fig6c_province_technology.csv",index=False)
    prov=pbuild.groupby("province",as_index=False)[["build_power_mw","build_energy_mwh"]].sum(); prov=prov.loc[prov.build_power_mw>1e-6].copy(); prov["build_power_gw"]=prov.build_power_mw/1000; prov["weighted_duration_h"]=prov.build_energy_mwh/prov.build_power_mw
    prov.to_csv(TABLE/"fig6d_province_duration.csv",index=False)

    # Fig. 6e: how the adaptive opportunity set changes compensatory investment.
    categories=["Li-ion 4 h","Base PSH","VRFB 10h","VRFB 24h","PSH 10h","PSH 24h"]
    shift=[]
    for legacy,base_s,adapt_s in [("Observed inheritance","FC01_BASE_OBSERVED","FC03_ADAPTIVE_OBSERVED"),("Optimized inheritance","FC02_BASE_OPTIMAL","FC04_ADAPTIVE_OPTIMAL")]:
        for cat in categories:
            b=float(mix.loc[(mix.scenario.eq(base_s))&(mix.technology_label.eq(cat)),"build_power_gw"].sum()); a=float(mix.loc[(mix.scenario.eq(adapt_s))&(mix.technology_label.eq(cat)),"build_power_gw"].sum())
            shift.append({"legacy_case":legacy,"metric":cat,"adaptive_minus_baseline":a-b,"unit":"GW"})
        shift.append({"legacy_case":legacy,"metric":"Transmission","adaptive_minus_baseline":tx_build(adapt_s)/1000-tx_build(base_s)/1000,"unit":"GW"})
    pd.DataFrame(shift).to_csv(TABLE/"fig6e_compensatory_shift.csv",index=False)

    # Fig. 6f: robustness. Expanded portfolio is explicitly pressure-test only.
    robust=[]
    for pid,label,elig in [("FC_ADAPTIVE","Adaptive / TX policy",True),("FC_ADAPTIVE_TXFIXED","Adaptive / TX fixed",False),("FC_EXPANDED_PRESSURE","Expanded portfolio / pressure test",False)]:
        v=float(ps.loc[pid,"legacy_penalty_usd_per_yr"]); robust.append({"case":label,"residual_lockin_million_usd_per_yr":v/1e6,"repair_fraction_relative_to_baseline":(l0-v)/l0 if abs(l0)>1e-12 else None,"main_claim_eligible":elig})
    pd.DataFrame(robust).to_csv(TABLE/"fig6f_robustness.csv",index=False)

    report={"version":"V19_LAYER_A_CORRECTION_2033","status":"PASS","design":"2033 single-target-year least-cost correction of inherited storage spatial lock-in","baseline_residual_legacy_lockin_usd_per_yr":l0,"adaptive_residual_legacy_lockin_usd_per_yr":l1,"adaptive_correction_value_usd_per_yr":correction,"repair_fraction":repair,"interpretation_lock":"Repair fraction is the reduction in the matched observed-minus-optimized legacy penalty when the evidence-bounded 2033 adaptive storage opportunity set is enabled. It is not a historical causal estimate and is not a 2025-2050 investment-timing pathway.","expanded_pressure_test_main_claim_eligible":False}
    (TABLE/"V19_LAYER_A_future_correction_summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
