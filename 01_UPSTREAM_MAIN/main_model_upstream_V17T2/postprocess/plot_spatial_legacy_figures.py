#!/usr/bin/env python3
"""Render Storage V17 main and supplementary figures in a Nature-family style."""
from __future__ import annotations
from pathlib import Path
import argparse, json, textwrap
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from matplotlib.colors import TwoSlopeNorm

from ne_style import configure, clean_axis, panel_label, save_figure, PALETTE, SCENARIO_COLORS, SCENARIO_LABELS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"postprocess_outputs"
TM=OUT/"tables"/"main"; TS=OUT/"tables"/"supplementary"
FM=OUT/"figures"/"main"; FS=OUT/"figures"/"supplementary"


def rd(path: Path)->pd.DataFrame:
    if not path.exists(): raise FileNotFoundError(path)
    return pd.read_csv(path)


def node_map(ax,nodes,edges,value,color_values=None,title="",delta=False,labels=5):
    xy=nodes.set_index("model_zone")[["longitude","latitude"]]
    for _,e in edges.iterrows():
        if e.zone_from in xy.index and e.zone_to in xy.index:
            a=xy.loc[e.zone_from]; b=xy.loc[e.zone_to]
            lw=0.2+0.8*np.sqrt(max(float(e.get("existing_capacity_mw",0)),0)/max(float(edges.existing_capacity_mw.max()),1))
            ax.plot([a.longitude,b.longitude],[a.latitude,b.latitude],color="#D0D0D0",lw=lw,zorder=1)
    v=pd.to_numeric(nodes[value],errors="coerce").fillna(0)
    size=12+180*np.sqrt(np.abs(v)/max(np.abs(v).max(),1))
    if color_values is None:
        color_values=v
    cv=pd.to_numeric(color_values,errors="coerce").fillna(0)
    if delta:
        norm=TwoSlopeNorm(vmin=min(cv.min(),-1),vcenter=0,vmax=max(cv.max(),1)); cmap="RdBu_r"
    else:
        norm=None; cmap="viridis"
    sc=ax.scatter(nodes.longitude,nodes.latitude,s=size,c=cv,cmap=cmap,norm=norm,edgecolor="white",linewidth=0.45,zorder=3)
    label_idx=np.abs(v).nlargest(labels).index
    label_offsets={
        "Xinjiang":(4,5), "West_Inner_Mongolia":(-58,10), "East_Inner_Mongolia":(-58,-10),
        "Hebei":(7,12), "Shandong":(7,-10), "Jiangsu":(7,-11), "Ningxia":(-38,7),
    }
    for i in label_idx:
        r=nodes.loc[i]; zone=str(r.model_zone); dx,dy=label_offsets.get(zone,(5,4))
        ax.annotate(zone.replace("_"," "),(r.longitude,r.latitude),xytext=(dx,dy),textcoords="offset points",fontsize=5.3,zorder=4,arrowprops=dict(arrowstyle="-",lw=.35,color="#AAAAAA"))
    ax.set_xlim(84,132); ax.set_ylim(18,49); ax.set_aspect(1.0)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_title(title,loc="left")
    for sp in ax.spines.values(): sp.set_visible(False)
    return sc


def fig1():
    nodes=rd(TM/"fig1a_legacy_nodes.csv"); edges=rd(TM/"fig1b_model_network_edges.csv"); design=rd(TM/"fig1c_scenario_design.csv"); conc=rd(TM/"fig1d_legacy_concentration.csv").iloc[0]
    fig=plt.figure(figsize=(7.08,6.3)); gs=fig.add_gridspec(2,2,height_ratios=[1,1.15],wspace=.30,hspace=.34)
    ax=fig.add_subplot(gs[0,0]); panel_label(ax,"a")
    ax.axis("off")
    boxes=[
        (.12,.72,.76,.18,"NEA-constrained 2025 reference","135.93 GW / 351.12 GWh constrained reference"),
        (.12,.43,.76,.18,"Equal-total counterfactuals","Reconstructed, optimized, load-rule and VRE-rule locations"),
        (.12,.14,.76,.18,"System consequences","Future storage, transmission, curtailment and cost"),
    ]
    for x,y,w,h,t,sub in boxes:
        p=FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.012,rounding_size=0.014",fc="white",ec=PALETTE["navy"],lw=.8,transform=ax.transAxes)
        ax.add_patch(p)
        ax.text(x+w/2,y+h*.66,t,ha="center",va="center",fontweight="bold",fontsize=6.5,transform=ax.transAxes)
        ax.text(x+w/2,y+h*.28,sub,ha="center",va="center",fontsize=5.5,transform=ax.transAxes)
    for y1,y2 in [(.72,.61),(.43,.32)]:
        ax.add_patch(FancyArrowPatch((.50,y1),(.50,y2),arrowstyle="-|>",mutation_scale=8,color=PALETTE["grey"],transform=ax.transAxes))
    ax.text(.50,.045,"Only model-zone location changes; national MW, MWh, duration, technology and sunk-capital treatment remain fixed.",ha="center",va="center",fontsize=5.5,color=PALETTE["dark"],transform=ax.transAxes,wrap=True)
    ax=fig.add_subplot(gs[0,1]); panel_label(ax,"b")
    sc=node_map(ax,nodes,edges,"existing_new_storage_power_mw",nodes.existing_duration_h,"Reconstructed storage power and duration")
    cb=fig.colorbar(sc,ax=ax,fraction=.04,pad=.02); cb.set_label("Duration (h)")
    ax=fig.add_subplot(gs[1,0]); panel_label(ax,"c")
    q=nodes.nlargest(12,"existing_new_storage_power_mw").sort_values("existing_new_storage_power_mw")
    ax.barh(q.model_zone.str.replace("_"," "),q.existing_new_storage_power_mw/1000,color=PALETTE["blue"],height=.65)
    clean_axis(ax,"x"); ax.set_xlabel("Reconstructed storage power (GW)"); ax.set_ylabel("")
    ax2=ax.twiny(); ax2.scatter(q.existing_duration_h,q.model_zone.str.replace("_"," "),s=13,color=PALETTE["orange"],zorder=4); ax2.set_xlabel("Duration (h)"); ax2.spines["top"].set_position(("outward",2)); ax2.spines["right"].set_visible(False); ax2.spines["bottom"].set_visible(False)
    ax=fig.add_subplot(gs[1,1]); panel_label(ax,"d")
    labels=[SCENARIO_LABELS.get(s,s) for s in design.scenario]
    features=np.array([[1,1,0,0],[1,1,1,0],[1,1,1,1],[0,0,0,0],[1,1,1,0],[1,1,1,0]])
    ax.imshow(features,aspect="auto",cmap="Blues",vmin=0,vmax=1)
    ax.set_yticks(range(len(labels)),labels); ax.set_xticks(range(4),["Legacy MW","Legacy MWh","Common duration","Endogenous location"],rotation=25,ha="right")
    for i in range(features.shape[0]):
        for j in range(features.shape[1]): ax.text(j,i,"●" if features[i,j] else "–",ha="center",va="center",color="white" if features[i,j] else PALETTE["grey"],fontsize=7)
    ax.set_title(f"Top-five provinces hold {conc.top5_power_share:.0%} of power",loc="left")
    for sp in ax.spines.values(): sp.set_visible(False)
    save_figure(fig,FM/"Fig1_storage_legacy_and_identification")


def fig2():
    nodes=rd(TM/"fig1a_legacy_nodes.csv"); edges=rd(TM/"fig1b_model_network_edges.csv"); a=rd(TM/"fig2_spatial_allocation.csv")
    obs=a[a.scenario.eq("SL01_OBSERVED_STANDARDIZED")].merge(nodes[["model_zone","longitude","latitude"]],on="model_zone")
    opt=a[a.scenario.eq("SL02_OPTIMAL_REALLOCATION")].merge(nodes[["model_zone","longitude","latitude"]],on="model_zone")
    d=opt.copy(); d["delta"]=d.delta_power_vs_observed_standardized_mw
    fig=plt.figure(figsize=(7.08,5.7)); gs=fig.add_gridspec(2,3,height_ratios=[1,.95],wspace=.28,hspace=.34)
    for j,(df,title,col,delta) in enumerate([(obs,"Reconstructed standardized","realized_legacy_power_mw",False),(opt,"Optimal reallocation","realized_legacy_power_mw",False),(d,"Optimal minus reconstructed","delta",True)]):
        ax=fig.add_subplot(gs[0,j]); panel_label(ax,chr(97+j)); sc=node_map(ax,df,edges,col,df[col],title,delta=delta,labels=3); cb=fig.colorbar(sc,ax=ax,fraction=.04,pad=.01); cb.set_label("GW" if not delta else "MW change")
    ax=fig.add_subplot(gs[1,:2]); panel_label(ax,"d",x=-.06)
    q=d.reindex(d.delta.abs().sort_values().index).tail(16)
    colors=[PALETTE["orange"] if x>0 else PALETTE["blue"] for x in q.delta]
    ax.barh(q.model_zone.str.replace("_"," "),q.delta/1000,color=colors,height=.68); ax.axvline(0,color=PALETTE["dark"],lw=.7); clean_axis(ax,"x"); ax.set_xlabel("Reallocation change (GW)")
    ax=fig.add_subplot(gs[1,2]); panel_label(ax,"e",x=-.20)
    totals=pd.DataFrame({"case":["Reconstructed","Optimal"],"power":[obs.realized_legacy_power_mw.sum()/1000,opt.realized_legacy_power_mw.sum()/1000],"energy":[obs.realized_legacy_energy_mwh.sum()/1000,opt.realized_legacy_energy_mwh.sum()/1000]})
    x=np.arange(2); ax.bar(x-.18,totals.power,.36,label="Power (GW)",color=PALETTE["blue"]); ax.bar(x+.18,totals.energy,.36,label="Energy (GWh)",color=PALETTE["orange"]); ax.set_xticks(x,totals.case); clean_axis(ax,"y"); ax.set_ylabel("National total"); ax.legend(frameon=False,loc="upper center")
    save_figure(fig,FM/"Fig2_observed_vs_optimal_spatial_allocation")


def fig3():
    d=rd(TM/"fig3_system_value.csv"); order=[s for s in SCENARIO_LABELS if s in set(d.scenario)]; q=d.set_index("scenario").loc[order].reset_index()
    opt=float(d.loc[d.scenario.eq("SL02_OPTIMAL_REALLOCATION"),"cumulative_system_cost_pv_usd"].iloc[0]);
    fig,axs=plt.subplots(2,2,figsize=(7.08,5.5)); axs=axs.ravel()
    panel_label(axs[0],"a"); vals=(q.cumulative_system_cost_pv_usd-opt)/1e9; axs[0].bar(range(len(q)),vals,color=[SCENARIO_COLORS[s] for s in q.scenario]); axs[0].set_xticks(range(len(q)),[SCENARIO_LABELS[s] for s in q.scenario],rotation=30,ha="right"); axs[0].set_ylabel("Cost above optimum (billion US$ PV)"); clean_axis(axs[0],"y")
    panel_label(axs[1],"b"); metrics=[("future_battery_build_mw","Battery power","GW"),("future_battery_energy_build_mwh","Battery energy","GWh"),("future_transmission_build_mw","Transmission","GW")]; width=.22; x=np.arange(len(q))
    for k,(m,l,u) in enumerate(metrics): axs[1].bar(x+(k-1)*width,q[m]/1000,width,label=l)
    axs[1].set_xticks(x,[SCENARIO_LABELS[s] for s in q.scenario],rotation=30,ha="right"); axs[1].set_ylabel("Future additions"); axs[1].legend(frameon=False,ncol=1); clean_axis(axs[1],"y")
    panel_label(axs[2],"c"); axs[2].bar(range(len(q)),q.final_curtailment_gwh_per_yr/1000,color=[SCENARIO_COLORS[s] for s in q.scenario]); axs[2].set_xticks(range(len(q)),[SCENARIO_LABELS[s] for s in q.scenario],rotation=30,ha="right"); axs[2].set_ylabel("Final-period curtailment (TWh yr$^{-1}$)"); clean_axis(axs[2],"y")
    panel_label(axs[3],"d"); r=d.iloc[0]; lai=float(r.legacy_alignment_index); axs[3].barh([0],[1],height=.34,color=PALETTE["light_grey"]); axs[3].barh([0],[lai],height=.34,color=PALETTE["orange"]); axs[3].set_xlim(0,1); axs[3].set_yticks([]); axs[3].set_xlabel("Legacy alignment index"); axs[3].text(lai/2,0,f"{lai:.2f}",ha="center",va="center",fontweight="bold"); axs[3].text(.02,-.35,f"Spatial misalignment cost\n{float(r.spatial_misalignment_cost_usd)/1e9:.1f} billion US$ PV",transform=axs[3].transAxes); clean_axis(axs[3],None)
    fig.tight_layout(); save_figure(fig,FM/"Fig3_system_cost_of_spatial_misalignment")


def fig4():
    d=rd(TM/"fig4_delivered_flexibility.csv"); periods=sorted(d.period.unique()); final=max(periods); q=d[d.period.eq(final)].copy()
    fig,axs=plt.subplots(2,2,figsize=(7.08,5.6),layout="constrained");
    for ax,sc,label,pl in [(axs[0,0],"SL01_OBSERVED_STANDARDIZED","Reconstructed standardized","a"),(axs[0,1],"SL02_OPTIMAL_REALLOCATION","Optimal reallocation","b")]:
        x=q[q.scenario.eq(sc)]; panel_label(ax,pl); s=15+100*np.sqrt(x.realized_legacy_power_mw/max(float(x.realized_legacy_power_mw.max()),1.0)); c=ax.scatter(x.realized_legacy_power_mw/1000,x.equivalent_discharge_cycles_per_yr,s=s,c=x.high_load_discharge_share,cmap="viridis",edgecolor="white",lw=.4); ax.set_xlabel("Legacy power (GW)"); ax.set_ylabel("Equivalent discharge cycles yr$^{-1}$"); ax.set_title(label,loc="left"); clean_axis(ax,"both");
        for _,r in x.nlargest(4,"realized_legacy_power_mw").iterrows(): ax.text(r.realized_legacy_power_mw/1000,r.equivalent_discharge_cycles_per_yr,str(r.province).replace("_"," "),fontsize=5.2)
    cb=fig.colorbar(c,ax=[axs[0,0],axs[0,1]],fraction=.025,pad=.02); cb.set_label("High-load discharge share")
    panel_label(axs[1,0],"c"); p=q.pivot(index="province",columns="scenario",values="equivalent_discharge_cycles_per_yr").dropna(); p["delta"]=p.get("SL02_OPTIMAL_REALLOCATION",0)-p.get("SL01_OBSERVED_STANDARDIZED",0); z=p.reindex(p.delta.abs().sort_values().index).tail(14); axs[1,0].barh(z.index.str.replace("_"," "),z.delta,color=[PALETTE["orange"] if v>0 else PALETTE["blue"] for v in z.delta]); axs[1,0].axvline(0,color=PALETTE["dark"],lw=.6); axs[1,0].set_xlabel("Change in equivalent cycles yr$^{-1}$"); clean_axis(axs[1,0],"x")
    panel_label(axs[1,1],"d"); h=q.groupby("scenario").agg(discharge=("annual_discharge_mwh","sum"),reserve=("peak_planning_reserve_mw","sum"),high=("high_load_discharge_mwh","sum")).loc[["SL01_OBSERVED_STANDARDIZED","SL02_OPTIMAL_REALLOCATION"]]; h["high_share"]=h.high/h.discharge; xx=np.arange(2); axs[1,1].bar(xx-.18,h.discharge/1e6,.36,label="Discharge (TWh yr$^{-1}$)",color=PALETTE["blue"]); axs[1,1].bar(xx+.18,h.reserve/1000,.36,label="Peak reserve (GW)",color=PALETTE["orange"]); axs[1,1].set_xticks(xx,["Reconstructed","Optimal"]); axs[1,1].legend(frameon=False); clean_axis(axs[1,1],"y")
    save_figure(fig,FM/"Fig4_installed_storage_and_delivered_flexibility")


def fig5():
    d=rd(TM/"fig5_transition_paths.csv"); fig,axs=plt.subplots(2,2,figsize=(7.08,5.3)); metrics=[("installed_battery_mw",1e3,"Battery power (GW)"),("installed_battery_energy_mwh",1e3,"Battery energy (GWh)"),("cumulative_new_transmission_mw",1e3,"New transmission (GW)"),("Curtail_GWh_typical_yr",1e3,"Curtailment (TWh yr$^{-1}$)")]
    for i,(m,scale,label) in enumerate(metrics):
        ax=axs.ravel()[i]; panel_label(ax,chr(97+i));
        for sc in ["SL01_OBSERVED_STANDARDIZED","SL02_OPTIMAL_REALLOCATION"]:
            q=d[d.scenario.eq(sc)].sort_values("period"); ax.plot(q.period,q.get(m,pd.Series(np.nan,index=q.index))/scale,marker="o",ms=3,lw=1.4,label=SCENARIO_LABELS[sc],color=SCENARIO_COLORS[sc])
        ax.set_ylabel(label); ax.set_xlabel("Planning period"); clean_axis(ax,"y")
    axs[0,0].legend(frameon=False); fig.tight_layout(); save_figure(fig,FM/"Fig5_storage_legacy_redirects_transition")


def fig6():
    d=rd(TM/"fig6_robustness.csv"); contexts=ROB=["base","tx_fixed","ph_conservative","carbon_tight","battery_cost_low","battery_cost_high"]; labels=["Base","Fixed transmission","Conservative pumped hydro","Tighter carbon cap","Low battery cost","High battery cost"]
    fig,axs=plt.subplots(2,2,figsize=(7.08,5.4)); metrics=[("cumulative_system_cost_pv_usd",1e9,"Spatial cost penalty (billion US$ PV)"),("future_battery_build_mw",1e3,"Avoided future battery power (GW)"),("future_transmission_build_mw",1e3,"Avoided transmission build (GW)"),("final_curtailment_gwh_per_yr",1e3,"Avoided final curtailment (TWh yr$^{-1}$)")]
    for i,(metric,scale,xlabel) in enumerate(metrics):
        ax=axs.ravel()[i]; panel_label(ax,chr(97+i)); q=d[d.metric.eq(metric)].set_index("legacy_context").reindex(contexts); vals=q.observed_minus_optimal/scale; y=np.arange(len(contexts)); ax.axvline(0,color=PALETTE["grey"],lw=.6); ax.hlines(y,0,vals,color=PALETTE["light_grey"],lw=1.2); ax.scatter(vals,y,s=26,color=PALETTE["orange"],zorder=3); ax.set_yticks(y,labels if i%2==0 else [""]*len(y)); ax.invert_yaxis(); ax.set_xlabel(xlabel); clean_axis(ax,"x")
    fig.tight_layout(); save_figure(fig,FM/"Fig6_robustness_of_spatial_legacy_effect")


def supplementary_inputs():
    nodes=rd(TM/"fig1a_legacy_nodes.csv"); edges=rd(TM/"fig1b_model_network_edges.csv"); design=rd(TM/"fig1c_scenario_design.csv")
    # S1 network schematic
    fig,ax=plt.subplots(figsize=(4.8,3.6)); node_map(ax,nodes,edges,"coincident_peak_2023_mw",nodes.wind_solar_capacity_2023_mw,"32-zone model network",labels=8); save_figure(fig,FS/"FigS01_model_zone_network")
    # S2 resource/load relationship
    fig,axs=plt.subplots(1,2,figsize=(6.6,3)); axs[0].scatter(nodes.coincident_peak_2023_mw/1000,nodes.existing_new_storage_power_mw/1000,s=18,c=nodes.wind_solar_capacity_2023_mw,cmap="viridis"); axs[0].set_xlabel("Coincident peak (GW)"); axs[0].set_ylabel("Reconstructed storage (GW)"); clean_axis(axs[0],"both"); axs[1].scatter(nodes.wind_solar_capacity_2023_mw/1000,nodes.existing_new_storage_power_mw/1000,s=18,c=nodes.storage_to_peak_ratio,cmap="viridis"); axs[1].set_xlabel("Wind and solar capacity (GW)"); axs[1].set_ylabel("Reconstructed storage (GW)"); clean_axis(axs[1],"both"); save_figure(fig,FS/"FigS02_storage_load_resource_inputs")
    # S3 power-energy validation
    fig,ax=plt.subplots(figsize=(4.6,3.2)); ax.scatter(nodes.existing_new_storage_power_mw/1000,nodes.existing_new_storage_energy_mwh/1000,s=20,c=nodes.existing_duration_h,cmap="viridis"); x=np.linspace(0,nodes.existing_new_storage_power_mw.max()/1000,100); ax.plot(x,x*nodes.existing_new_storage_energy_mwh.sum()/nodes.existing_new_storage_power_mw.sum(),ls="--",color=PALETTE["grey"]); ax.set_xlabel("Reconstructed power (GW)"); ax.set_ylabel("Reconstructed energy (GWh)"); clean_axis(ax,"both"); save_figure(fig,FS/"FigS03_observed_storage_power_energy_validation")
    # S4 duration distribution
    fig,ax=plt.subplots(figsize=(4.6,3.0)); ax.hist(nodes.existing_duration_h,bins=10,alpha=.75,color=PALETTE["blue"]); avg=nodes.existing_new_storage_energy_mwh.sum()/nodes.existing_new_storage_power_mw.sum(); ax.axvline(avg,color=PALETTE["orange"],lw=1.3,label=f"National average {avg:.2f} h"); ax.set_xlabel("Reconstructed duration (h)"); ax.set_ylabel("Model zones"); ax.legend(frameon=False); clean_axis(ax,"y"); save_figure(fig,FS/"FigS04_duration_composition")
    # S5 empirical cap
    fig,ax=plt.subplots(figsize=(5.0,3.2)); q=nodes.sort_values("storage_to_peak_ratio"); ratio=q.storage_to_peak_ratio.quantile(.95); exc=q.storage_to_peak_ratio>ratio+1e-12; ax.scatter(q.loc[~exc,"coincident_peak_2023_mw"]/1000,q.loc[~exc,"existing_new_storage_power_mw"]/1000,s=18,color=PALETTE["blue"],label="Within p95 envelope"); ax.scatter(q.loc[exc,"coincident_peak_2023_mw"]/1000,q.loc[exc,"existing_new_storage_power_mw"]/1000,s=24,color=PALETTE["orange"],edgecolor="white",linewidth=.4,label="Deployment floor retained"); xmax=q.coincident_peak_2023_mw.max()/1000; ax.plot([0,xmax],[0,xmax*ratio],color=PALETTE["grey"],ls="--",label=f"p95 rule ({ratio:.2f} × peak)"); ax.set_xlabel("2023 coincident peak (GW)"); ax.set_ylabel("Legacy power (GW)"); ax.legend(frameon=False,loc="upper left"); clean_axis(ax,"both"); save_figure(fig,FS/"FigS05_empirical_deployment_envelope")
    # S6 scenario matrix
    fig,ax=plt.subplots(figsize=(6.8,2.8)); ax.axis("off"); text="\n".join(f"{SCENARIO_LABELS.get(r.scenario,r.scenario)} — {r.legacy_allocation_mode.replace('_',' ')}" for _,r in design.iterrows()); ax.text(.02,.96,"Core spatial-legacy counterfactuals",fontweight="bold",va="top",transform=ax.transAxes); ax.text(.02,.84,text,va="top",linespacing=1.55,transform=ax.transAxes); save_figure(fig,FS/"FigS06_core_scenario_matrix")
    # S8 concentration curve (S7 requires outputs)
    fig,ax=plt.subplots(figsize=(4.6,3.1)); shares=np.sort(nodes.existing_new_storage_power_mw/nodes.existing_new_storage_power_mw.sum()); cum=np.r_[0,np.cumsum(shares)]; pop=np.linspace(0,1,len(cum)); ax.plot(pop,cum,color=PALETTE["blue"]); ax.plot([0,1],[0,1],ls="--",color=PALETTE["grey"]); ax.set_xlabel("Cumulative share of model zones"); ax.set_ylabel("Cumulative share of storage power"); clean_axis(ax,"both"); save_figure(fig,FS/"FigS08_storage_spatial_concentration")


def supplementary_results():
    nodes=rd(TM/"fig1a_legacy_nodes.csv"); edges=rd(TM/"fig1b_model_network_edges.csv")
    # S7 solver/audit
    s=rd(TS/"figS07_solver_audit.csv"); fig,ax=plt.subplots(figsize=(7.0,3.4)); cols=[c for c in ["strict_optimal","strict_physical_audit_pass","legacy_allocation_audit_pass","strict_export_pass"] if c in s]; mat=np.array([[str(v).lower() in {"true","1","yes"} for v in s[c]] for c in cols]).T; ax.imshow(mat,aspect="auto",cmap="Greens",vmin=0,vmax=1); ax.set_yticks(range(len(s)),s.scenario if "scenario" in s else s.scenario_key); ax.set_xticks(range(len(cols)),[c.replace("_"," ") for c in cols],rotation=25,ha="right"); save_figure(fig,FS/"FigS07_solver_and_physical_audits")
    a=rd(TM/"fig2_spatial_allocation.csv")
    # S9 allocation rules
    fig,axs=plt.subplots(1,3,figsize=(7.0,2.9));
    for ax,sc,t in zip(axs,["SL01_OBSERVED_STANDARDIZED","SL04_RULE_LOAD","SL05_RULE_VRE"],["Reconstructed","Load rule","VRE rule"]):
        q=a[a.scenario.eq(sc)].merge(nodes[["model_zone","longitude","latitude"]],on="model_zone"); node_map(ax,q,edges,"realized_legacy_power_mw",q.realized_legacy_power_mw,t,labels=2)
    save_figure(fig,FS/"FigS09_rule_based_allocations")
    # S10 delta ranking
    q=rd(TS/"figS10_province_allocation_deltas.csv").sort_values("delta_power_vs_observed_standardized_mw"); fig,ax=plt.subplots(figsize=(5.2,5)); ax.barh(q.model_zone.str.replace("_"," "),q.delta_power_vs_observed_standardized_mw/1000,color=[PALETTE["orange"] if v>0 else PALETTE["blue"] for v in q.delta_power_vs_observed_standardized_mw]); ax.axvline(0,color=PALETTE["dark"],lw=.6); ax.set_xlabel("Optimal minus reconstructed (GW)"); clean_axis(ax,"x"); save_figure(fig,FS/"FigS10_full_province_reallocation")
    # S11 cost decomposition
    q=rd(TS/"figS11_cost_decomposition.csv"); q=q[q.scenario.isin(["SL01_OBSERVED_STANDARDIZED","SL02_OPTIMAL_REALLOCATION"]) & (q.period>=2028)]; fig,axs=plt.subplots(2,2,figsize=(6.6,4.8)); metrics=["TotalGenCapacityCosts","StorageEnergyFixedCost","TxFixedCosts","FuelCostsPerYear"];
    for ax,m in zip(axs.ravel(),metrics):
        for sc in q.scenario.unique(): z=q[q.scenario.eq(sc)]; ax.plot(z.period,z[m]/1e9,marker="o",ms=2.5,label=SCENARIO_LABELS.get(sc,sc),color=SCENARIO_COLORS.get(sc)); ax.set_ylabel(m.replace("Costs"," cost").replace("PerYear"," (billion US$ yr$^{-1}$)")); clean_axis(ax,"y")
    axs[0,0].legend(frameon=False); save_figure(fig,FS/"FigS11_system_cost_decomposition")
    # S12 curtailment and emissions
    q=rd(TS/"figS12_curtailment_emissions.csv"); q=q[q.scenario.isin(["SL01_OBSERVED_STANDARDIZED","SL02_OPTIMAL_REALLOCATION"]) & (q.period>=2028)]; fig,axs=plt.subplots(1,2,figsize=(6.4,2.9));
    for sc in q.scenario.unique(): z=q[q.scenario.eq(sc)]; axs[0].plot(z.period,z.Curtail_GWh_typical_yr/1000,marker="o",label=SCENARIO_LABELS.get(sc,sc),color=SCENARIO_COLORS.get(sc)); axs[1].plot(z.period,z.NetAnnualEmissions_tCO2/1e9,marker="o",color=SCENARIO_COLORS.get(sc));
    axs[0].set_ylabel("Curtailment (TWh yr$^{-1}$)"); axs[1].set_ylabel("Net emissions (GtCO$_2$ yr$^{-1}$)"); [clean_axis(x,"y") for x in axs]; axs[0].legend(frameon=False); save_figure(fig,FS/"FigS12_curtailment_and_emissions")
    # S13 operation
    q=rd(TS/"figS13_storage_operation.csv"); q=q[(q.technology=="Battery") & q.scenario.isin(["SL01_OBSERVED_STANDARDIZED","SL02_OPTIMAL_REALLOCATION"]) & (q.period>=2028)]; fig,ax=plt.subplots(figsize=(5.2,3.2)); data=[q[q.scenario.eq(sc)].equivalent_discharge_cycles_per_yr.dropna() for sc in ["SL01_OBSERVED_STANDARDIZED","SL02_OPTIMAL_REALLOCATION"]]; ax.boxplot(data,tick_labels=["Reconstructed","Optimal"],showfliers=False); ax.set_ylabel("Zone-level equivalent cycles yr$^{-1}$"); clean_axis(ax,"y"); save_figure(fig,FS/"FigS13_storage_operation_distribution")
    # S14 and S15 forest subsets
    for num,file,title in [(14,"figS14_transmission_sensitivity.csv","Transmission sensitivity"),(15,"figS15_ph_carbon_cost_robustness.csv","Pumped-hydro, carbon and cost robustness")]:
        q=rd(TS/file); q=q[q.metric.eq("cumulative_system_cost_pv_usd")]; fig,ax=plt.subplots(figsize=(5.4,3.0)); y=np.arange(len(q)); ax.hlines(y,0,q.observed_minus_optimal/1e9,color=PALETTE["light_grey"]); ax.scatter(q.observed_minus_optimal/1e9,y,color=PALETTE["orange"]); ax.set_yticks(y,q.legacy_context.str.replace("_"," ")); ax.set_xlabel("Spatial cost penalty (billion US$ PV)"); clean_axis(ax,"x"); ax.set_title(title,loc="left"); save_figure(fig,FS/f"FigS{num:02d}_{title.lower().replace(' ','_').replace(',','')}")
    # S16 temporal scope diagram
    q=rd(TS/"figS16_temporal_scope.csv").iloc[0]; fig,ax=plt.subplots(figsize=(6.4,2.7)); ax.axis("off"); ax.add_patch(Rectangle((.05,.55),.24,.24,fc="#EAF1F5",ec=PALETTE["blue"],transform=ax.transAxes)); ax.add_patch(Rectangle((.38,.55),.24,.24,fc="#F8EFE6",ec=PALETTE["orange"],transform=ax.transAxes)); ax.add_patch(Rectangle((.71,.55),.24,.24,fc="#F2F2F2",ec=PALETTE["grey"],transform=ax.transAxes)); ax.text(.17,.67,"4-h blocks\n12 representative days",ha="center",va="center",transform=ax.transAxes); ax.text(.50,.67,"Intraday cyclic SOC\ncapacity-expansion evidence",ha="center",va="center",transform=ax.transAxes); ax.text(.83,.67,"No multi-day or\nseasonal-shifting claim",ha="center",va="center",transform=ax.transAxes); ax.add_patch(FancyArrowPatch((.29,.67),(.38,.67),arrowstyle="-|>",transform=ax.transAxes)); ax.add_patch(FancyArrowPatch((.62,.67),(.71,.67),arrowstyle="-|>",transform=ax.transAxes)); ax.text(.5,.28,q.supported_claim,ha="center",va="center",wrap=True,transform=ax.transAxes); save_figure(fig,FS/"FigS16_temporal_scope_and_claim_boundary")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input-only",action="store_true")
    ap.add_argument("--group",default="all",choices=["all","main","supplementary-input","supplementary-results"])
    args=ap.parse_args()
    family=configure()
    if args.group=="all":
        if args.input_only:
            fig1(); supplementary_inputs()
        else:
            fig1(); fig2(); fig3(); fig4(); fig5(); fig6(); supplementary_inputs(); supplementary_results()
    elif args.group=="main":
        fig1()
        if not args.input_only:
            fig2(); fig3(); fig4(); fig5(); fig6()
    elif args.group=="supplementary-input":
        supplementary_inputs()
    elif args.group=="supplementary-results":
        supplementary_results()
    files=[str(p) for p in sorted((OUT/"figures").rglob("*.pdf"))]
    audit={"font_family":family,"group":args.group,"input_only":args.input_only,"pdf_count":len(files),"pdf_files":files}
    (OUT/"audits").mkdir(parents=True,exist_ok=True)
    (OUT/"audits"/"figure_render_audit.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")
    print(json.dumps({"font_family":family,"group":args.group,"input_only":args.input_only,"pdf_count":len(files)},indent=2))
if __name__=="__main__": main()
