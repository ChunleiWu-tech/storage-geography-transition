#!/usr/bin/env python3
"""Render candidate main Fig. 6: least-cost correction of inherited storage spatial lock-in.

The figure is intentionally separate from the V17 diagnostic figures.  Panels
(a-d) use only the BASE and evidence-bounded ADAPTIVE primary experiment;
TX-fixed and expanded-portfolio cases appear only as explicitly styled
robustness points.
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, TwoSlopeNorm

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[0]
sys.path.insert(0,str(HERE))
from ne_style import PALETTE, configure, clean_axis, panel_label, save_figure

TABLE=ROOT/"future_correction_outputs/publication_tables"
FIG=ROOT/"future_correction_outputs/publication_figures"


def read(name:str)->pd.DataFrame:
    p=TABLE/name
    if not p.is_file(): raise FileNotFoundError(p)
    return pd.read_csv(p)

def _fmt(v:float)->str:
    if abs(v)>=100: return f"{v:.0f}"
    if abs(v)>=10: return f"{v:.1f}"
    if abs(v)>=1: return f"{v:.2f}"
    return f"{v:.3f}"


def main()->None:
    configure()
    a=read("fig6a_lockin_repair.csv")
    b=read("fig6b_technology_mix.csv")
    c=read("fig6c_province_technology.csv")
    d=read("fig6d_province_duration.csv")
    e=read("fig6e_compensatory_shift.csv")
    f=read("fig6f_robustness.csv")
    metrics=read("future_correction_metrics.csv")
    repair=float(metrics.loc[metrics.metric.eq("Repair fraction"),"value"].iloc[0])

    fig=plt.figure(figsize=(7.0866,7.45))
    gs=fig.add_gridspec(3,2,left=0.145,right=0.975,bottom=0.085,top=0.955,wspace=0.43,hspace=0.54)
    axa=fig.add_subplot(gs[0,0]); axb=fig.add_subplot(gs[0,1]); axc=fig.add_subplot(gs[1,0]); axd=fig.add_subplot(gs[1,1]); axe=fig.add_subplot(gs[2,0]); axf=fig.add_subplot(gs[2,1])

    # a. Difference-in-differences lock-in repair.
    vals=a.legacy_penalty_million_usd_per_yr.to_numpy(float); yy=np.array([0,1])
    axa.plot(vals,yy,color=PALETTE["mid_grey"],lw=1.8,zorder=1)
    axa.scatter(vals,yy,s=[54,54],color=[PALETTE["navy"],PALETTE["teal"]],edgecolor="white",linewidth=0.8,zorder=3)
    axa.axvline(0,color=PALETTE["mid_grey"],lw=0.55)
    axa.set_yticks(yy,["Baseline future set","Adaptive storage set"]); axa.invert_yaxis()
    span=max(np.ptp(vals),np.max(np.abs(vals))*0.25,1.0); axa.set_xlim(min(0,vals.min())-0.10*span,max(0,vals.max())+0.33*span)
    for y,v in zip(yy,vals): axa.text(v+0.025*span,y,f"{v:+.1f}",ha="left",va="center",fontsize=5.9)
    axa.text(0.98,0.08,f"Repair = {100*repair:+.1f}%",transform=axa.transAxes,ha="right",va="bottom",fontsize=6.3,fontweight="bold",color=PALETTE["teal"] if repair>=0 else PALETTE["red"])
    axa.set_xlabel("Residual legacy penalty (million USD yr$^{-1}$)"); clean_axis(axa,"x")

    # b. What: adaptive technology mix, power with energy annotations.
    mat=b.groupby(["technology_label","scenario"],as_index=False)[["build_power_gw","build_energy_gwh"]].sum()
    total=mat.groupby("technology_label").build_power_gw.max().sort_values(ascending=True)
    techs=[t for t in total.index if total[t]>1e-5]
    if not techs: techs=["Li-ion 4 h"]
    y=np.arange(len(techs)); scenarios=[("FC03_ADAPTIVE_OBSERVED","Observed inheritance",PALETTE["navy"],-0.10),("FC04_ADAPTIVE_OPTIMAL","Optimized inheritance",PALETTE["orange"],0.10)]
    for sc,label,color,off in scenarios:
        sub=mat.loc[mat.scenario.eq(sc)].set_index("technology_label")
        p=np.array([float(sub.loc[t,"build_power_gw"]) if t in sub.index else 0.0 for t in techs])
        en=np.array([float(sub.loc[t,"build_energy_gwh"]) if t in sub.index else 0.0 for t in techs])
        axb.scatter(p,y+off,s=34,color=color,edgecolor="white",linewidth=0.6,label=label,zorder=3)
        for xi,yi,ei in zip(p,y+off,en):
            if xi>1e-4: axb.annotate(f"{ei:.1f} GWh",(xi,yi),xytext=(4,0),textcoords="offset points",fontsize=4.7,va="center")
    axb.set_yticks(y,techs); axb.set_xlabel("New storage power in 2033 (GW)"); clean_axis(axb,"x")
    xmax=max([0.0]+[float(x) for x in mat.build_power_gw.to_numpy(float)])
    axb.set_xlim(left=0,right=max(1.0,1.22*xmax))
    axb.legend(ncol=2,loc="lower center",bbox_to_anchor=(0.50,1.01),columnspacing=0.8,handletextpad=0.3)

    # c. Where x what: top provinces by adaptive observed build, exact GW heatmap.
    pivot=c.pivot_table(index="province",columns="technology_label",values="build_power_gw",aggfunc="sum",fill_value=0)
    if len(pivot):
        order=pivot.sum(axis=1).sort_values(ascending=False).head(12).index; pivot=pivot.loc[order]
        keep=[col for col in pivot.columns if pivot[col].abs().max()>1e-5]; pivot=pivot[keep] if keep else pivot.iloc[:,:1]
        arr=pivot.to_numpy(float); vmax=max(float(np.nanmax(arr)),1e-9)
        axc.imshow(arr,cmap="Blues",norm=Normalize(vmin=0,vmax=vmax),aspect="auto")
        for i in range(arr.shape[0]):
            for j in range(arr.shape[1]):
                v=arr[i,j]; txt="·" if abs(v)<=1e-5 else (_fmt(v))
                axc.text(j,i,txt,ha="center",va="center",fontsize=4.8,color="white" if v>0.55*vmax else PALETTE["dark"])
        axc.set_xticks(np.arange(len(pivot.columns)),pivot.columns,rotation=38,ha="right"); axc.set_yticks(np.arange(len(pivot.index)),pivot.index)
        axc.tick_params(length=0,labelsize=5.0,pad=2)
        for sp in axc.spines.values(): sp.set_visible(False)
        axc.set_xlabel("Technology-specific new power (GW); top provinces")
    else:
        axc.text(0.5,0.5,"No material new storage build",transform=axc.transAxes,ha="center",va="center"); axc.axis("off")

    # d. How long: province-weighted duration, marker area indicates GW.
    dd=d.sort_values("build_power_gw",ascending=False).head(12).sort_values("weighted_duration_h")
    if len(dd):
        y=np.arange(len(dd)); pw=dd.build_power_gw.to_numpy(float); duration=dd.weighted_duration_h.to_numpy(float)
        sizes=22+68*(pw/max(pw.max(),1e-9))
        for yi,x in zip(y,duration): axd.plot([0,x],[yi,yi],color=PALETTE["light_grey"],lw=1.4,zorder=1)
        axd.scatter(duration,y,s=sizes,color=PALETTE["purple"],edgecolor="white",linewidth=0.7,zorder=3)
        for x,yi,g in zip(duration,y,pw): axd.annotate(f"{g:.1f} GW",(x,yi),xytext=(4,0),textcoords="offset points",fontsize=4.9,va="center")
        axd.set_yticks(y,dd.province.tolist()); axd.set_xlabel("Power-weighted storage duration (h)"); clean_axis(axd,"x")
    else:
        axd.text(0.5,0.5,"No material new storage build",transform=axd.transAxes,ha="center",va="center"); axd.axis("off")

    # e. Compensatory reconfiguration: adaptive minus baseline.
    piv=e.pivot(index="metric",columns="legacy_case",values="adaptive_minus_baseline")
    material=piv.abs().max(axis=1).sort_values(ascending=True); mets=[m for m in material.index if material[m]>5e-4]
    if not mets: mets=[piv.index[0]]
    y=np.arange(len(mets)); allv=piv.loc[mets].to_numpy(float); lim=max(float(np.nanmax(np.abs(allv)))*1.30,1.0)
    axe.axvline(0,color=PALETTE["dark"],lw=0.6)
    for col,label,color,off in [("Observed inheritance","Observed",PALETTE["navy"],-0.10),("Optimized inheritance","Optimized",PALETTE["orange"],0.10)]:
        vv=piv.loc[mets,col].to_numpy(float); axe.scatter(vv,y+off,s=32,color=color,edgecolor="white",linewidth=0.6,label=label,zorder=3)
    axe.set_yticks(y,mets); axe.set_xlim(-lim,lim); axe.set_xlabel("Adaptive − baseline compensatory build (GW)"); clean_axis(axe,"x")
    axe.legend(ncol=2,loc="lower center",bbox_to_anchor=(0.50,1.01),columnspacing=0.8,handletextpad=0.3)

    # f. Robustness / substitution boundary. Expanded case is hollow pressure-test point.
    ff=f.copy(); y=np.arange(len(ff)); vals=ff.residual_lockin_million_usd_per_yr.to_numpy(float); reps=ff.repair_fraction_relative_to_baseline.to_numpy(float)
    axf.axvline(0,color=PALETTE["mid_grey"],lw=0.55)
    for i,row in ff.iterrows():
        eligible=str(row.main_claim_eligible).lower() in {"true","1"}
        color=PALETTE["teal"] if eligible else PALETTE["grey"]
        face=color if eligible else "white"
        axf.scatter(float(row.residual_lockin_million_usd_per_yr),i,s=48,facecolor=face,edgecolor=color,linewidth=1.1,zorder=3)
        axf.annotate(f"{100*float(row.repair_fraction_relative_to_baseline):+.1f}%",(float(row.residual_lockin_million_usd_per_yr),i),xytext=(5,0),textcoords="offset points",fontsize=5.2,va="center")
    short_labels=[]
    for name in ff.case.astype(str):
        if name=="Adaptive / TX policy": short_labels.append("TX policy")
        elif name=="Adaptive / TX fixed": short_labels.append("TX fixed")
        elif name=="Expanded portfolio / pressure test": short_labels.append("Expanded portfolio*")
        else: short_labels.append(name)
    axf.set_yticks(y,short_labels); axf.invert_yaxis(); span=max(np.ptp(vals),np.max(np.abs(vals))*0.25,1.0); axf.set_xlim(min(0,vals.min())-0.10*span,max(0,vals.max())+0.35*span)
    axf.set_xlabel("Residual legacy penalty (million USD yr$^{-1}$)"); clean_axis(axf,"x")
    axf.text(0.98,0.05,"*Pressure test only",transform=axf.transAxes,fontsize=4.9,ha="right",va="bottom",color=PALETTE["grey"])

    for ax,label in zip([axa,axb,axc,axd,axe,axf],list("abcdef")): panel_label(ax,label,x=-0.16,y=1.10)
    save_figure(fig,FIG/"Fig6_future_correction_of_storage_spatial_lockin")

if __name__=="__main__": main()
