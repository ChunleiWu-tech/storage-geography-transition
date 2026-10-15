#!/usr/bin/env python3
"""Build the V17 storage-spatial-legacy main and supplementary figure tables.

No missing solver result is replaced with zero. The script requires audited strict
outputs for every selected scenario and preserves period-resolved quantities. The
central spatial comparison is SL01_OBSERVED_STANDARDIZED versus
SL02_OPTIMAL_REALLOCATION: national legacy MW, MWh, duration, technology and sunk
capital treatment are identical; only model-zone allocation changes.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import zipfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCEN = ROOT / "storage_runner" / "scenarios_storage_master.csv"
TEMPLATE = ROOT / "base_model_v39" / "storage_base_template_v17.zip"
OUTROOT = ROOT / "postprocess_outputs"
TABLE_MAIN = OUTROOT / "tables" / "main"
TABLE_SUPP = OUTROOT / "tables" / "supplementary"
AUDIT_DIR = OUTROOT / "audits"
TRUE = {"true", "1", "yes"}
CORE = [
    "SL00_OBSERVED_ACTUAL", "SL01_OBSERVED_STANDARDIZED", "SL02_OPTIMAL_REALLOCATION",
    "SL03_NO_LEGACY", "SL04_RULE_LOAD", "SL05_RULE_VRE",
]
ROBUSTNESS_CONTEXT_ORDER = ["base", "tx_fixed", "ph_conservative", "carbon_tight", "battery_cost_low", "battery_cost_high"]


def _read_template_csv(name: str) -> pd.DataFrame:
    with zipfile.ZipFile(TEMPLATE) as zf:
        with zf.open(f"inputs/{name}") as handle:
            return pd.read_csv(handle)


def _scenario_dir(outputs: Path, scenario: str) -> Path:
    p = outputs / f"{scenario}__main"
    if not p.is_dir():
        raise FileNotFoundError(p)
    return p


def _read_output(outputs: Path, scenario: str, filename: str) -> pd.DataFrame:
    p = _scenario_dir(outputs, scenario) / filename
    if not p.is_file():
        raise FileNotFoundError(p)
    return pd.read_csv(p)


def _official(master: pd.DataFrame, scenario_set: str) -> pd.DataFrame:
    ok = master["v17_official_unique"].astype(str).str.lower().isin(TRUE)
    if scenario_set == "spatial_legacy_core":
        ok &= master["legacy_story_set"].astype(str).eq("spatial_legacy_core")
    elif scenario_set == "spatial_legacy_robustness":
        ok &= master["legacy_story_set"].astype(str).eq("spatial_legacy_robustness")
    elif scenario_set != "spatial_legacy_full":
        raise ValueError(scenario_set)
    return master.loc[ok].copy()


def _base_metadata() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    gen = _read_template_csv("gen_info.csv")
    pred = _read_template_csv("gen_build_predetermined.csv")
    peak = _read_template_csv("zone_coincident_peak_demand.csv")
    lines = _read_template_csv("transmission_lines.csv")
    periods = _read_template_csv("periods.csv")
    return gen, pred, peak, lines, periods


def _surviving_capacity(gen: pd.DataFrame, pred: pd.DataFrame, period: int, techs: list[str]) -> pd.DataFrame:
    meta = gen[["GENERATION_PROJECT", "gen_load_zone", "gen_tech", "gen_max_age"]]
    x = pred.merge(meta, on="GENERATION_PROJECT", how="left", validate="many_to_one")
    x["build_year"] = pd.to_numeric(x["build_year"], errors="raise")
    x["gen_max_age"] = pd.to_numeric(x["gen_max_age"], errors="raise")
    x["build_gen_predetermined"] = pd.to_numeric(x["build_gen_predetermined"], errors="raise").fillna(0.0)
    x = x[x.gen_tech.isin(techs)]
    x = x[(x.build_year <= period) & (period < x.build_year + x.gen_max_age)]
    return x.groupby(["gen_load_zone", "gen_tech"], as_index=False).build_gen_predetermined.sum()


def build_input_tables(master: pd.DataFrame) -> dict[str, pd.DataFrame]:
    gen, pred, peak, lines, periods = _base_metadata()
    coords = pd.read_csv(ROOT / "data" / "visualization" / "model_zone_coordinates.csv")
    observed = pd.read_csv(ROOT / "data" / "processed" / "existing_new_storage_allocated_to_model_zones_2025.csv")
    p23 = peak[pd.to_numeric(peak.PERIOD, errors="raise").eq(2023)][
        ["LOAD_ZONE", "zone_expected_coincident_peak_demand"]
    ].rename(columns={"LOAD_ZONE": "model_zone", "zone_expected_coincident_peak_demand": "coincident_peak_2023_mw"})
    vre = _surviving_capacity(gen, pred, 2023, ["Wind", "Solar_PV"])
    vre = vre.pivot(index="gen_load_zone", columns="gen_tech", values="build_gen_predetermined").fillna(0.0).reset_index()
    vre = vre.rename(columns={"gen_load_zone": "model_zone", "Wind": "wind_capacity_2023_mw", "Solar_PV": "solar_capacity_2023_mw"})
    for c in ["wind_capacity_2023_mw", "solar_capacity_2023_mw"]:
        if c not in vre: vre[c] = 0.0
    nodes = coords.merge(observed, on="model_zone", how="left", validate="one_to_one").merge(p23, on="model_zone", how="left", validate="one_to_one").merge(vre, on="model_zone", how="left", validate="one_to_one")
    nodes["existing_duration_h"] = nodes.existing_new_storage_energy_mwh / nodes.existing_new_storage_power_mw.replace(0, np.nan)
    nodes["storage_to_peak_ratio"] = nodes.existing_new_storage_power_mw / nodes.coincident_peak_2023_mw
    nodes["wind_solar_capacity_2023_mw"] = nodes.wind_capacity_2023_mw.fillna(0) + nodes.solar_capacity_2023_mw.fillna(0)
    edges = lines[["TRANSMISSION_LINE", "trans_lz1", "trans_lz2", "existing_trans_cap", "trans_new_build_cap", "trans_efficiency"]].copy()
    edges = edges.rename(columns={"trans_lz1": "zone_from", "trans_lz2": "zone_to", "existing_trans_cap": "existing_capacity_mw", "trans_new_build_cap": "new_build_cap_mw"})
    design = master[master.scenario.isin(CORE)][[
        "scenario", "legacy_allocation_mode", "legacy_pair_id", "legacy_context", "description", "v17_claim_scope"
    ]].copy()
    power = nodes.existing_new_storage_power_mw
    concentration = pd.DataFrame([{
        "national_power_mw": float(power.sum()),
        "national_energy_mwh": float(nodes.existing_new_storage_energy_mwh.sum()),
        "national_average_duration_h": float(nodes.existing_new_storage_energy_mwh.sum() / power.sum()),
        "top5_power_share": float(power.nlargest(5).sum() / power.sum()),
        "herfindahl_hirschman_index": float(((power / power.sum()) ** 2).sum()),
        "maximum_storage_to_peak_ratio": float(nodes.storage_to_peak_ratio.max()),
        "p95_storage_to_peak_ratio": float(nodes.storage_to_peak_ratio.quantile(0.95)),
    }])
    return {"fig1_nodes": nodes, "fig1_edges": edges, "fig1_scenario_design": design, "fig1_concentration": concentration}


def _installed_from_builds(build: pd.DataFrame, gen_meta: pd.DataFrame, periods: list[int]) -> pd.DataFrame:
    x = build.merge(gen_meta[["GENERATION_PROJECT", "gen_max_age"]], on="GENERATION_PROJECT", how="left", validate="many_to_one")
    x["build_year"] = pd.to_numeric(x.build_year, errors="raise").astype(int)
    x["gen_max_age"] = pd.to_numeric(x.gen_max_age, errors="raise")
    x["BuildGen"] = pd.to_numeric(x.BuildGen, errors="raise").fillna(0.0)
    rows=[]
    for p in periods:
        q=x[(x.build_year <= p) & (p < x.build_year + x.gen_max_age)].copy()
        for (province, tech), g in q.groupby(["province", "technology"]):
            rows.append({"period": p, "province": province, "technology": tech, "installed_power_mw": float(g.BuildGen.sum())})
    return pd.DataFrame(rows)


def _installed_energy(build_energy: pd.DataFrame, gen_meta: pd.DataFrame, periods: list[int]) -> pd.DataFrame:
    x = build_energy.merge(gen_meta[["GENERATION_PROJECT", "gen_max_age"]], on="GENERATION_PROJECT", how="left", validate="many_to_one")
    x["build_year"] = pd.to_numeric(x.build_year, errors="raise").astype(int)
    x["gen_max_age"] = pd.to_numeric(x.gen_max_age, errors="raise")
    col = "BuildStorageEnergy_MWh" if "BuildStorageEnergy_MWh" in x else "BuildStorageEnergy"
    x[col] = pd.to_numeric(x[col], errors="raise").fillna(0.0)
    rows=[]
    for p in periods:
        q=x[(x.build_year <= p) & (p < x.build_year + x.gen_max_age)].copy()
        for (province, tech), g in q.groupby(["province", "technology"]):
            rows.append({"period": p, "province": province, "technology": tech, "installed_energy_mwh": float(g[col].sum())})
    return pd.DataFrame(rows)


def _period_metrics(outputs: Path, scenario: str, gen_meta: pd.DataFrame, periods: list[int]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cost = _read_output(outputs, scenario, "electricity_cost.csv")
    cost["period"] = pd.to_numeric(cost.period, errors="raise").astype(int)
    build = _read_output(outputs, scenario, "BuildGen.csv")
    energy = _read_output(outputs, scenario, "BuildStorageEnergy.csv")
    tx = _read_output(outputs, scenario, "BuildTx.csv")
    curt = _read_output(outputs, scenario, "vre_curtailment_annual.csv")
    inst = _installed_from_builds(build, gen_meta, periods)
    inst_e = _installed_energy(energy, gen_meta, periods)
    national = inst.groupby(["period", "technology"], as_index=False).installed_power_mw.sum()
    national_e = inst_e.groupby(["period", "technology"], as_index=False).installed_energy_mwh.sum()
    wide = national.pivot(index="period", columns="technology", values="installed_power_mw").fillna(0.0)
    wide.columns = [f"installed_{str(c).lower()}_mw" for c in wide.columns]
    wide = wide.reset_index()
    ew = national_e.pivot(index="period", columns="technology", values="installed_energy_mwh").fillna(0.0)
    ew.columns = [f"installed_{str(c).lower()}_energy_mwh" for c in ew.columns]
    ew = ew.reset_index()
    tx["build_year"] = pd.to_numeric(tx.build_year, errors="raise").astype(int)
    tx["BuildTx"] = pd.to_numeric(tx.BuildTx, errors="raise").fillna(0.0)
    txp = pd.DataFrame({"period": periods})
    txp["cumulative_new_transmission_mw"] = [float(tx.loc[tx.build_year <= p, "BuildTx"].sum()) for p in periods]
    curt["period"] = pd.to_numeric(curt.period, errors="raise").astype(int)
    c = curt.groupby("period", as_index=False)[["Potential_GWh_typical_yr", "Gen_GWh_typical_yr", "Curtail_GWh_typical_yr"]].sum()
    c["curtailment_rate"] = c.Curtail_GWh_typical_yr / c.Potential_GWh_typical_yr.replace(0, np.nan)
    cols = [c for c in ["period", "SystemDemand_MWh", "SystemCost_annualized_usd_per_yr", "SystemCost_present_value_to_base_year", "NetAnnualEmissions_tCO2", "CarbonCap_tCO2_per_yr", "TotalGenCapacityCosts", "StorageEnergyFixedCost", "TxFixedCosts", "FuelCostsPerYear"] if c in cost.columns]
    pm = cost[cols].merge(wide, on="period", how="left").merge(ew, on="period", how="left").merge(txp, on="period", how="left").merge(c, on="period", how="left")
    pm.insert(0, "scenario", scenario)
    inst.insert(0, "scenario", scenario)
    inst_e.insert(0, "scenario", scenario)
    return pm, inst, inst_e


def _operation_metrics(outputs: Path, scenario: str) -> pd.DataFrame:
    op = _read_output(outputs, scenario, "storage_operation_audit.csv")
    lb = _read_output(outputs, scenario, "load_balance.csv")
    weights = lb[["load_zone", "timepoint", "period", "tp_weight_in_year_hrs", "zone_demand_mw"]].drop_duplicates()
    weights = weights.rename(columns={"load_zone":"province"})
    x = op.merge(weights, on=["province", "timepoint", "period"], how="left", validate="many_to_one")
    if x.tp_weight_in_year_hrs.isna().any():
        raise ValueError(f"Missing time weights for {scenario} storage operation")
    x["discharge_mwh_per_yr"] = pd.to_numeric(x.Discharge_MW, errors="raise") * pd.to_numeric(x.tp_weight_in_year_hrs, errors="raise")
    x["charge_mwh_per_yr"] = pd.to_numeric(x.Charge_MW, errors="raise") * pd.to_numeric(x.tp_weight_in_year_hrs, errors="raise")
    x["high_load_flag"] = x.groupby(["province","period"])["zone_demand_mw"].transform(lambda q: q >= q.quantile(0.90))
    x["high_load_discharge_mwh_per_yr"] = x.discharge_mwh_per_yr.where(x.high_load_flag, 0.0)
    g=x.groupby(["province","period","technology"],as_index=False).agg(
        annual_discharge_mwh=("discharge_mwh_per_yr","sum"), annual_charge_mwh=("charge_mwh_per_yr","sum"),
        high_load_discharge_mwh=("high_load_discharge_mwh_per_yr","sum"),
        energy_capacity_mwh=("EnergyCapacity_MWh","max"), power_capacity_mw=("AvailablePowerLimit_MW","max"),
        peak_planning_reserve_mw=("PlanningReserveAvailable_MW","max"), max_simultaneous_mw=("SimultaneousChargeDischarge_MW","max"))
    g["equivalent_discharge_cycles_per_yr"] = g.annual_discharge_mwh / g.energy_capacity_mwh.replace(0,np.nan)
    g["high_load_discharge_share"] = g.high_load_discharge_mwh / g.annual_discharge_mwh.replace(0,np.nan)
    g.insert(0,"scenario",scenario)
    return g


def build_result_tables(outputs: Path, master: pd.DataFrame, selected: pd.DataFrame) -> dict[str, pd.DataFrame]:
    gen, _, _, _, periods_df = _base_metadata()
    periods = sorted(pd.to_numeric(periods_df.INVESTMENT_PERIOD, errors="raise").astype(int).tolist())
    scenarios = selected.scenario.astype(str).tolist()
    alloc=[]; period_metrics=[]; installed=[]; installed_e=[]; operation=[]; solve=[]; physical=[]
    for sc in scenarios:
        a=_read_output(outputs,sc,"legacy_storage_allocation_audit.csv"); a.insert(0,"scenario",sc); alloc.append(a)
        pm,ip,ie=_period_metrics(outputs,sc,gen,periods); period_metrics.append(pm); installed.append(ip); installed_e.append(ie)
        operation.append(_operation_metrics(outputs,sc))
        st=_read_output(outputs,sc,"solve_status.csv"); st.insert(0,"scenario_key",sc); solve.append(st)
        ph=_read_output(outputs,sc,"physical_audit_summary.csv"); ph.insert(0,"scenario",sc); physical.append(ph)
    allocation=pd.concat(alloc,ignore_index=True)
    pm=pd.concat(period_metrics,ignore_index=True)
    inst=pd.concat(installed,ignore_index=True)
    inste=pd.concat(installed_e,ignore_index=True)
    op=pd.concat(operation,ignore_index=True)
    solve_df=pd.concat(solve,ignore_index=True)
    physical_df=pd.concat(physical,ignore_index=True)
    # Fig.2 allocation and spatial delta.
    ref=allocation[allocation.scenario.eq("SL01_OBSERVED_STANDARDIZED")][["model_zone","realized_legacy_power_mw","realized_legacy_energy_mwh"]].rename(columns={"realized_legacy_power_mw":"observed_standardized_power_mw","realized_legacy_energy_mwh":"observed_standardized_energy_mwh"})
    fig2=allocation[allocation.scenario.isin(CORE)].merge(ref,on="model_zone",how="left",validate="many_to_one")
    fig2["delta_power_vs_observed_standardized_mw"] = fig2.realized_legacy_power_mw - fig2.observed_standardized_power_mw
    fig2["delta_energy_vs_observed_standardized_mwh"] = fig2.realized_legacy_energy_mwh - fig2.observed_standardized_energy_mwh
    # Scenario-level metrics.
    rows=[]
    final=max(periods)
    for sc,g in pm.groupby("scenario"):
        q=g[g.period>=2028]
        last=q[q.period.eq(final)].iloc[0] if (q.period==final).any() else q.sort_values("period").iloc[-1]
        b=_read_output(outputs,sc,"BuildGen.csv")
        b["build_year"]=pd.to_numeric(b.build_year,errors="raise")
        b["BuildGen"]=pd.to_numeric(b.BuildGen,errors="raise").fillna(0)
        future=b[b.build_year>=2028]
        e=_read_output(outputs,sc,"BuildStorageEnergy.csv"); e["build_year"]=pd.to_numeric(e.build_year,errors="raise")
        ec="BuildStorageEnergy_MWh" if "BuildStorageEnergy_MWh" in e else "BuildStorageEnergy"; e[ec]=pd.to_numeric(e[ec],errors="raise").fillna(0)
        tx=_read_output(outputs,sc,"BuildTx.csv"); tx["BuildTx"]=pd.to_numeric(tx.BuildTx,errors="raise").fillna(0)
        rows.append({
            "scenario":sc,"final_period":int(last.period),
            "cumulative_system_cost_pv_usd":float(q.SystemCost_present_value_to_base_year.sum()),
            "final_annual_system_cost_usd_per_yr":float(last.get("SystemCost_annualized_usd_per_yr",np.nan)),
            "future_battery_build_mw":float(future.loc[future.technology.eq("Battery"),"BuildGen"].sum()),
            "future_pumped_hydro_build_mw":float(future.loc[future.technology.eq("Hydro_Pumped"),"BuildGen"].sum()),
            "future_battery_energy_build_mwh":float(e.loc[(e.build_year>=2028)&e.technology.eq("Battery"),ec].sum()),
            "future_transmission_build_mw":float(tx.BuildTx.sum()),
            "final_curtailment_gwh_per_yr":float(last.get("Curtail_GWh_typical_yr",np.nan)),
            "final_curtailment_rate":float(last.get("curtailment_rate",np.nan)),
            "final_net_emissions_tco2_per_yr":float(last.get("NetAnnualEmissions_tCO2",np.nan)),
        })
    fig3=pd.DataFrame(rows).merge(master[["scenario","legacy_allocation_mode","legacy_context","description"]],on="scenario",how="left")
    def val(sc,col): return float(fig3.loc[fig3.scenario.eq(sc),col].iloc[0])
    c_no=val("SL03_NO_LEGACY","cumulative_system_cost_pv_usd")
    c_obs=val("SL01_OBSERVED_STANDARDIZED","cumulative_system_cost_pv_usd")
    c_opt=val("SL02_OPTIMAL_REALLOCATION","cumulative_system_cost_pv_usd")
    denom=c_no-c_opt
    fig3["legacy_alignment_index"]=(c_no-c_obs)/denom if abs(denom)>1e-9 else np.nan
    fig3["spatial_misalignment_cost_usd"] = c_obs-c_opt
    fig3["observed_legacy_realized_value_usd"] = c_no-c_obs
    fig3["maximum_reallocated_legacy_value_usd"] = c_no-c_opt
    # Fig.4 zone battery service metrics for the spatial pair.
    fig4=op[(op.scenario.isin(["SL01_OBSERVED_STANDARDIZED","SL02_OPTIMAL_REALLOCATION"])) & op.technology.eq("Battery") & (op.period>=2028)].merge(
        allocation[["scenario","model_zone","realized_legacy_power_mw","realized_legacy_energy_mwh"]],
        left_on=["scenario","province"],right_on=["scenario","model_zone"],how="left",validate="many_to_one")
    # Fig.5 paths for reconstructed-standardized versus optimal.
    fig5=pm[pm.scenario.isin(["SL01_OBSERVED_STANDARDIZED","SL02_OPTIMAL_REALLOCATION"]) & (pm.period>=2028)].copy()
    # Fig.6 paired robustness, including base.
    pair_rows=[]
    pairs=[("base","SL01_OBSERVED_STANDARDIZED","SL02_OPTIMAL_REALLOCATION")]
    for ctx,g in master[master.legacy_story_set.eq("spatial_legacy_robustness")].groupby("legacy_context"):
        obs=g[g.legacy_allocation_mode.eq("observed_standardized")].scenario.astype(str).tolist()
        opt=g[g.legacy_allocation_mode.eq("optimized_reallocation")].scenario.astype(str).tolist()
        if len(obs)==1 and len(opt)==1: pairs.append((ctx,obs[0],opt[0]))
    metrics=["cumulative_system_cost_pv_usd","future_battery_build_mw","future_pumped_hydro_build_mw","future_battery_energy_build_mwh","future_transmission_build_mw","final_curtailment_gwh_per_yr","final_curtailment_rate"]
    f3=fig3.set_index("scenario")
    for ctx,obs,opt in pairs:
        for metric in metrics:
            ov=float(f3.loc[obs,metric]); pv=float(f3.loc[opt,metric]); d=ov-pv
            pair_rows.append({"legacy_context":ctx,"observed_scenario":obs,"optimal_scenario":opt,"metric":metric,"observed_value":ov,"optimal_value":pv,"observed_minus_optimal":d,"relative_penalty_fraction":d/abs(pv) if abs(pv)>1e-12 else np.nan})
    fig6=pd.DataFrame(pair_rows)
    fig6["context_order"] = fig6.legacy_context.map({v:i for i,v in enumerate(ROBUSTNESS_CONTEXT_ORDER)})
    # Supplementary tables.
    outputs_dict={
        "fig2_spatial_allocation":fig2,"fig3_system_value":fig3,"fig4_delivered_flexibility":fig4,
        "fig5_transition_paths":fig5,"fig6_robustness":fig6,
        "figS06_scenario_matrix":selected,
        "figS07_solver_audit":solve_df,
        "figS10_province_allocation_deltas":fig2[fig2.scenario.eq("SL02_OPTIMAL_REALLOCATION")].copy(),
        "figS11_cost_decomposition":pm[[c for c in pm.columns if c in {"scenario","period","TotalGenCapacityCosts","StorageEnergyFixedCost","TxFixedCosts","FuelCostsPerYear","SystemCost_annualized_usd_per_yr"}]],
        "figS12_curtailment_emissions":pm[[c for c in pm.columns if c in {"scenario","period","Curtail_GWh_typical_yr","curtailment_rate","NetAnnualEmissions_tCO2","CarbonCap_tCO2_per_yr"}]],
        "figS13_storage_operation":op,
        "figS14_transmission_sensitivity":fig6[fig6.legacy_context.eq("tx_fixed")],
        "figS15_ph_carbon_cost_robustness":fig6[fig6.legacy_context.isin(["ph_conservative","carbon_tight","battery_cost_low","battery_cost_high"])],
        "figS16_temporal_scope":pd.DataFrame([{"representative_timepoints":504,"dispatch_block_hours":4,"representative_days_per_period":12,"soc_linkage":"intraday cyclic within each representative day","supported_claim":"capacity expansion and intraday operation; core legacy fleet averages about 2.58 h","unsupported_claim":"chronological multi-day, weekly or seasonal shifting"}]),
        "physical_audit_detail":physical_df,"installed_power_by_zone_period":inst,"installed_energy_by_zone_period":inste,
    }
    return outputs_dict


def write_tables(tables: dict[str,pd.DataFrame], input_tables: dict[str,pd.DataFrame]) -> dict:
    TABLE_MAIN.mkdir(parents=True,exist_ok=True); TABLE_SUPP.mkdir(parents=True,exist_ok=True); AUDIT_DIR.mkdir(parents=True,exist_ok=True)
    mapping={
        "fig1_nodes":"fig1a_legacy_nodes.csv","fig1_edges":"fig1b_model_network_edges.csv","fig1_scenario_design":"fig1c_scenario_design.csv","fig1_concentration":"fig1d_legacy_concentration.csv",
        "fig2_spatial_allocation":"fig2_spatial_allocation.csv","fig3_system_value":"fig3_system_value.csv","fig4_delivered_flexibility":"fig4_delivered_flexibility.csv","fig5_transition_paths":"fig5_transition_paths.csv","fig6_robustness":"fig6_robustness.csv",
    }
    files=[]
    for k,df in input_tables.items():
        name=mapping[k]; df.to_csv(TABLE_MAIN/name,index=False); files.append(str(TABLE_MAIN/name))
    for k,df in tables.items():
        if k in mapping:
            p=TABLE_MAIN/mapping[k]
        else:
            p=TABLE_SUPP/f"{k}.csv"
        df.to_csv(p,index=False); files.append(str(p))
    audit={"version":"V17","generated_table_count":len(files),"generated_files":files,"all_nonempty_main":all(pd.read_csv(TABLE_MAIN/n).shape[0]>0 for n in mapping.values())}
    (AUDIT_DIR/"spatial_legacy_figure_table_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    if not audit["all_nonempty_main"]: raise RuntimeError("At least one main figure table is empty")
    return audit


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--outputs-dir",default=str(ROOT/"outputs")); ap.add_argument("--scenario-set",default="spatial_legacy_full",choices=["spatial_legacy_full","spatial_legacy_core","spatial_legacy_robustness"]); ap.add_argument("--input-only",action="store_true")
    args=ap.parse_args(); master=pd.read_csv(SCEN); selected=_official(master,args.scenario_set); inputs=build_input_tables(master)
    if args.input_only:
        TABLE_MAIN.mkdir(parents=True,exist_ok=True)
        names={"fig1_nodes":"fig1a_legacy_nodes.csv","fig1_edges":"fig1b_model_network_edges.csv","fig1_scenario_design":"fig1c_scenario_design.csv","fig1_concentration":"fig1d_legacy_concentration.csv"}
        for k,df in inputs.items(): df.to_csv(TABLE_MAIN/names[k],index=False)
        print(json.dumps({"input_only":True,"table_count":len(names)},ensure_ascii=False,indent=2)); return
    tables=build_result_tables(Path(args.outputs_dir),master,selected)
    summary=write_tables(tables,inputs); print(json.dumps({k:v for k,v in summary.items() if k!="generated_files"},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
