#!/usr/bin/env python3
"""Build result contracts only after all required V20 solves are strict PASS.
No publication figure is locked here; Fig.6 vs Fig.6+Fig.7 is decided from real information density.
"""
from pathlib import Path
import json, subprocess, sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v20_outputs'; TAB=OUT/'tables'
def strict_summary(path,n):
 if not path.is_file(): return False,None
 d=pd.read_csv(path); ok=len(d)==n and d.publication_strict_success.astype(str).str.lower().isin({'true','1','yes'}).all(); return ok,d

def storage_builds(scenarios):
 rows=[]
 for s in scenarios:
  out=ROOT/'outputs'/f'{s}__main'; case=ROOT/'storage_cases'/s
  bg=out/'BuildGen.csv'; be=out/'BuildStorageEnergy.csv'; gi=case/'inputs/gen_info.csv'
  if not (bg.exists() and be.exists() and gi.exists()): continue
  a=pd.read_csv(bg); b=pd.read_csv(be); g=pd.read_csv(gi)[['GENERATION_PROJECT','gen_tech','gen_load_zone']]
  def fc(df,cands):
   for c in cands:
    if c in df.columns:return c
  pc,yc,vc=fc(a,['GENERATION_PROJECT','generation_project']),fc(a,['build_year','BUILD_YEAR','period']),fc(a,['BuildGen','build_gen','value'])
  ep,ey,ev=fc(b,['GENERATION_PROJECT','generation_project']),fc(b,['build_year','BUILD_YEAR','period']),fc(b,['BuildStorageEnergy','build_storage_energy','value'])
  if None in [pc,yc,vc,ep,ey,ev]: continue
  aa=a[[pc,yc,vc]].rename(columns={pc:'GENERATION_PROJECT',yc:'build_year',vc:'new_power_mw'}); bb=b[[ep,ey,ev]].rename(columns={ep:'GENERATION_PROJECT',ey:'build_year',ev:'new_energy_mwh'})
  x=aa.merge(bb,on=['GENERATION_PROJECT','build_year'],how='outer').merge(g,on='GENERATION_PROJECT',how='left'); x=x[x.gen_tech.astype(str).str.startswith('V18_')].copy(); x['scenario']=s; rows.append(x)
 return pd.concat(rows,ignore_index=True) if rows else pd.DataFrame()

def objective_from_summary(d):
 for c in ['stage1_economic_objective_usd','economic_objective_usd','objective_value','stage1_objective']:
  if c in d.columns: return c
 return None

def main():
 aroot=ROOT/'modules/correction2033'
 # Layer A summary is produced by inherited strict builder, but only after its 8 cases have solved.
 try:
  subprocess.run([sys.executable,str(aroot/'tools/build_future_correction_summary.py')],cwd=aroot,check=True)
  layerA=True
 except Exception as e:
  print('Layer A result builder failed:',e); layerA=False
 b_ok,b=strict_summary(ROOT/'audits/v20/V20_LAYER_B_16_SOLVER_SUMMARY.csv',16)
 c_ok,c=strict_summary(ROOT/'audits/v20/V20_LAYER_C_EQUAL_HORIZON_2_SOLVER_SUMMARY.csv',2)
 if not (layerA and b_ok and c_ok):
  raise SystemExit('V20 REQUIRED RESULT GATE FAILED: Layer A 8 + Layer B 16 + Layer C 2 must all be solver-native strict PASS before integrated tables are built.')
 TAB.mkdir(parents=True,exist_ok=True)
 # Preserve solver summaries as tables.
 b.to_csv(TAB/'V20_LAYER_B_16_SOLVER_SUMMARY.csv',index=False); c.to_csv(TAB/'V20_LAYER_C_2_SOLVER_SUMMARY.csv',index=False)
 # Build storage investment data contracts.
 official=b.scenario.astype(str).tolist(); eh=c.scenario.astype(str).tolist()
 bd=storage_builds(official); cd=storage_builds(eh)
 if not bd.empty: bd.to_csv(TAB/'V20_EVIDENCE_DIRECT_BUILD_BY_YEAR_ZONE_TECH.csv',index=False)
 if not cd.empty: cd.to_csv(TAB/'V20_EQUAL_HORIZON_BUILD_BY_YEAR_ZONE_TECH.csv',index=False)
 # Cost-horizon comparison for core pair if objective is exposed in summaries.
 bc=objective_from_summary(b); cc=objective_from_summary(c); comp=[]
 if bc and cc:
  bm={r.scenario:float(getattr(r,bc)) for r in b.itertuples(index=False)}; cm={r.scenario:float(getattr(r,cc)) for r in c.itertuples(index=False)}
  if all(k in bm for k in ['SL01_OBSERVED_STANDARDIZED','SL02_OPTIMAL_REALLOCATION']) and all(k in cm for k in ['V20EH01_OBSERVED','V20EH02_OPTIMAL']):
   l_direct=bm['SL01_OBSERVED_STANDARDIZED']-bm['SL02_OPTIMAL_REALLOCATION']; l_equal=cm['V20EH01_OBSERVED']-cm['V20EH02_OPTIMAL']
   comp=[{'metric':'legacy_penalty_evidence_direct','value_usd':l_direct},{'metric':'legacy_penalty_equal_horizon','value_usd':l_equal},{'metric':'evidence_horizon_delta','value_usd':l_direct-l_equal}]
   pd.DataFrame(comp).to_csv(TAB/'V20_COST_EVIDENCE_HORIZON_COMPARISON.csv',index=False)
 status={'version':'V20_INTEGRATED_RESULT_CONTRACT_R1','status':'PASS','required_solves':26,'layer_A_8_strict':True,'layer_B_16_strict':True,'layer_C_2_strict':True,'figure_policy':'RUN-FIRST. Decide after inspecting real result information density: one Fig.6 if readable; otherwise Fig.6 correction + Fig.7 dynamic pathway/robustness.','technology_winner_claim_gate':'Post-2030 technology winner is headline-eligible only if evidence-direct interpretation remains qualitatively robust under equal-evidence-horizon pair and existing low/high battery cost sensitivity.'}
 (OUT/'V20_RESULTS_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
