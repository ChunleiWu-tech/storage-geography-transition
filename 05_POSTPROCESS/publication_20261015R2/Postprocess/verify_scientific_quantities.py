from pathlib import Path
from manifest_paths import source_path
import json,hashlib
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parent
T=ROOT/'tables'
manifest=json.loads((ROOT/'SOURCE_TABLES_SHA256.json').read_text(encoding='utf-8'))
for name,expected in manifest.items():
 assert hashlib.sha256(source_path(ROOT,name).read_bytes()).hexdigest()==expected, name
def read(p):return pd.read_csv(T/p)
q={}
c=read('main/fig4c_zone_correction.csv');p=read('main/fig4a_mismatch_persistence.csv');z=read('main/fig4b_zone_period_deltas.csv')
initial=p.iloc[0];tol=max(initial.power_half_l1_mw,1)*1e-6
def classify(i,f):
 if abs(i)<=tol:return 'near zero initially'
 if abs(f)<=.1*abs(i):return 'substantially corrected'
 if np.sign(i)!=np.sign(f):return 'reversal'
 if abs(f)<abs(i):return 'partly corrected'
 return 'persistent or amplified'
c['recomputed_class']=[classify(i,f) for i,f in zip(c.optimized_minus_observed_power_mw,c.final_power_delta_mw)]
assert c.recomputed_class.eq(c.correction_class).all()
c['strict_sign_reversal']=c.optimized_minus_observed_power_mw*c.final_power_delta_mw<0
c['final_half_abs_gw']=.5*c.final_power_delta_mw.abs()/1000
q['fig4']={'class_tolerance_mw':tol,'initial_duration_h':initial.energy_half_l1_mwh/initial.power_half_l1_mw,'initial_power_half_abs_gw':initial.power_half_l1_mw/1000,'initial_energy_half_abs_gwh':initial.energy_half_l1_mwh/1000,'class_counts':c.correction_class.value_counts().to_dict(),'class_final_half_abs_gw':c.groupby('correction_class').final_half_abs_gw.sum().to_dict(),'strict_sign_reversal_count':int(c.strict_sign_reversal.sum()),'strict_sign_reversal_half_abs_gw':float(c.loc[c.strict_sign_reversal,'final_half_abs_gw'].sum()),'strict_same_sign_half_abs_gw':float(c.loc[~c.strict_sign_reversal,'final_half_abs_gw'].sum()),'reversed_but_substantially_corrected':c.loc[c.strict_sign_reversal & c.correction_class.eq('substantially corrected'),'model_zone'].tolist(),'late_energy_minus_4power_max_mwh':float((p.loc[p.period>=2038,'energy_half_l1_mwh']-4*p.loc[p.period>=2038,'power_half_l1_mw']).abs().max())}
for r in p.itertuples():
 g=z[z.period.eq(r.period)];assert np.isclose(g.optimized_minus_observed_power_mw.abs().sum()/2,r.power_half_l1_mw,rtol=1e-12)
 assert np.isclose(g.optimized_minus_observed_energy_mwh.abs().sum()/2,r.energy_half_l1_mwh,rtol=1e-12)


build=read('future_storage/v20_layer_a_storage_builds.csv');out=[]
for a,b in [('FC01_BASE_OBSERVED','FC03_ADAPTIVE_OBSERVED'),('FC02_BASE_OPTIMAL','FC04_ADAPTIVE_OPTIMAL')]:
 keys=['zone','technology','build_year'];v=['build_power_mw','build_energy_mwh']
 aa=build[build.scenario.eq(a)].groupby(keys)[v].sum();bb=build[build.scenario.eq(b)].groupby(keys)[v].sum()
 ix=aa.index.union(bb.index);diff=bb.reindex(ix,fill_value=0)-aa.reindex(ix,fill_value=0)
 other=build[build.scenario.eq(b)&~build.technology.isin(['Battery','Hydro_Pumped'])]
 out.append({'pair':[a,b],'max_absolute_zonal_power_difference_gw':float(diff.build_power_mw.abs().max()/1000),'max_absolute_zonal_energy_difference_gwh':float(diff.build_energy_mwh.abs().max()/1000),'nonbaseline_technology_power_gw':float(other.build_power_gw.sum()),'portfolio':build[build.scenario.eq(b)].groupby('technology')[['build_power_gw','build_energy_gwh']].sum().to_dict()})
q['fig6']=out
tim=read('future_storage_v31/fig7_core_timing_by_technology.csv');q['fig7']={'construction_half_abs_gw':float(tim.observed_minus_optimized_gw.abs().sum()/2),'construction_net_gw':float(tim.observed_minus_optimized_gw.sum()),'by_tech_half_abs_gw':tim.groupby('technology_group').observed_minus_optimized_gw.apply(lambda x:float(x.abs().sum()/2)).to_dict()}
con=read('main/fig1d_legacy_concentration.csv').iloc[0];lad=read('main/fig2b_legacy_value_ladder.csv');inv=read('main/fig3a_compensatory_investment.csv')
q['fig1']=con.to_dict();q['fig2_3']={'sum_cost_pv_usd':float(inv.present_value_cost_delta_usd.sum()),'value_ladder':lad.to_dict('records')}

assert q['fig4']['strict_sign_reversal_count']==17
assert q['fig4']['class_counts']['reversal']==12
assert np.isclose(q['fig4']['class_final_half_abs_gw']['reversal'],5.539091436355137)
assert np.isclose(q['fig4']['strict_sign_reversal_half_abs_gw'],7.11186722818)
assert q['fig4']['late_energy_minus_4power_max_mwh']<1e-6
assert all(v['nonbaseline_technology_power_gw']==0 for v in q['fig6'])
assert all(v['max_absolute_zonal_power_difference_gw']<0.005 for v in q['fig6'])
assert np.isclose(q['fig7']['construction_half_abs_gw'],99.8684048946)
assert np.isclose(q['fig7']['construction_net_gw'],7.00787657349)
assert np.isclose(q['fig2_3']['sum_cost_pv_usd']/1e9,6.281335202745)
print(json.dumps({'status':'PASS','scope':'frozen-table arithmetic only; not run recency or real-world validation','results':q},ensure_ascii=False,indent=2))
