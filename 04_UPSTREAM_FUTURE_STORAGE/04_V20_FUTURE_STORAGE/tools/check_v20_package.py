#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json, re, subprocess, sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'audits/v20/V20_STATIC_PACKAGE_AUDIT.json'
EXPECTED_DYNAMIC_SHA='9aefc85c850165b17d69d4a7a66c386c0adc1c1fac2ee622422a892008a6781a'
PARENT_HF2_DYNAMIC_SHA='da8e22f538b3fdcfb536b265a598fffd4ec51091246397191d23c742d67efdbf'
EXPECTED_TARGET_SHA='2825377de801183dd624125d17d4f1541c70f724d48065b638026a774acd0a84'
EH={'V20EH01_OBSERVED':'SL01_OBSERVED_STANDARDIZED','V20EH02_OPTIMAL':'SL02_OPTIMAL_REALLOCATION'}


def sha(p:Path)->str:
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--release-clean', action='store_true', help='Also enforce distribution-only cleanliness: no solver outputs, caches, or machine-specific absolute paths. Do not use this flag during normal resume runs.')
 args=ap.parse_args()
 checks=[]
 def ck(name,ok,detail=''): checks.append({'check':name,'pass':bool(ok),'detail':detail})
 # Core package files
 for rel in ['README_00_V20_RUN_FIRST_ZH.md','docs/V20_EVIDENCE_POLICY_ZH.md','docs/V20_RUN_FIRST_DESIGN_ZH.md','docs/V20_MODEL_AND_CLAIM_CONTRACT_ZH.md','data/processed/v20_authoritative_evidence_ledger.csv','data/processed/v20_layer_b_runtime_contract.csv','tools/prepare_v20_equal_horizon_pair.py','tools/run_v20_chronology_isolation_diagnostics.py','V20_HF3_PSH_CAPACITY_PLAN_COMPATIBILITY_FIX.md','audits/v20/V20_HF3_CHANGE_SCOPE_AUDIT.json','audits/v20/V20_HF3_PSH_CAPACITY_PLAN_COMPATIBILITY_AUDIT.json','audits/v20/V20_HF3_PSH_CAPACITY_PLAN_COMPATIBILITY_AUDIT.csv','audits/v20/V20_HF3_DYNAMIC_CORE.diff']:
  ck('exists::'+rel,(ROOT/rel).is_file(),rel)
 # Frozen-source fingerprint must match the final packaged authoritative archive index.
 try:
  from publication_source_common import build_source_fingerprint, load_source_fingerprint
  stored_fp=load_source_fingerprint(ROOT); current_fp=build_source_fingerprint(ROOT)
  ck('source_fingerprint_exact_current_match',stored_fp==current_fp,'final packaged source archive index and frozen source fingerprint synchronized')
 except Exception as e:
  ck('source_fingerprint_exact_current_match',False,repr(e))
 # Scientific-core immutability
 p=ROOT/'base_model_v39/cheer_power_storage_v1.jl'; q=ROOT/'modules/correction2033/base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl'
 ck('dynamic_julia_core_hf3_bounded_fix_locked',p.is_file() and sha(p)==EXPECTED_DYNAMIC_SHA,{'current':sha(p) if p.is_file() else 'missing','parent_hf2':PARENT_HF2_DYNAMIC_SHA})
 ck('layerA_targetyear_core_frozen',q.is_file() and sha(q)==EXPECTED_TARGET_SHA,sha(q) if q.is_file() else 'missing')
 # NLR authoritative transcription anchors from packaged report Appendix Table 2
 nlr=pd.read_csv(ROOT/'data/processed/nlr_2025_battery_4h_costs.csv')
 def row(y): return nlr.loc[pd.to_numeric(nlr.year).astype(int).eq(y)].iloc[0]
 anchors={2030:(207,279,354),2035:(147,243,339),2050:(108,178,307),2058:(97,161,299)}
 ok=True; detail={}
 for y,vals in anchors.items():
  r=row(y); got=(float(r.low_2024usd_per_kwh),float(r.mid_2024usd_per_kwh),float(r.high_2024usd_per_kwh)); detail[str(y)]=got; ok &= got==tuple(map(float,vals))
 ck('nlr_2025_appendix_table2_anchor_values',ok,detail)
 ck('nlr_annual_2024_2060_complete',nlr.year.astype(int).tolist()==list(range(2024,2061)),[int(nlr.year.min()),int(nlr.year.max()),len(nlr)])
 # Evidence ledger hashes and role firewall
 led=pd.read_csv(ROOT/'data/processed/v20_authoritative_evidence_ledger.csv').fillna('')
 missing=[]; hash_bad=[]
 for _,r in led.iterrows():
  fp=ROOT/str(r.document)
  if not fp.is_file(): missing.append(str(r.document)); continue
  if str(r.sha256) and sha(fp)!=str(r.sha256): hash_bad.append(str(r.source_id))
 ck('authoritative_evidence_files_present',not missing,missing)
 ck('authoritative_evidence_sha256_match',not hash_bad,hash_bad)
 idxp=ROOT/'OFFICIAL_SOURCE_ARCHIVE_INDEX.csv'
 try:
  idx=pd.read_csv(idxp,encoding='utf-8-sig').fillna('')
  idx_ok=(len(idx)==len(led) and set(idx.source_id.astype(str))==set(led.source_id.astype(str)))
  if idx_ok:
   im=idx.set_index('source_id'); lm=led.set_index('source_id')
   idx_ok=all(str(im.loc[k,'sha256'])==str(lm.loc[k,'sha256']) and str(im.loc[k,'archive_path'])==str(lm.loc[k,'document']) for k in lm.index)
 except Exception:
  idx_ok=False
 ck('official_source_archive_index_matches_evidence_ledger',idx_ok,{'ledger_rows':len(led),'index_rows':len(idx) if 'idx' in locals() else None})
 ldes=' '.join(led.loc[led.source_id.astype(str).str.contains('DOE_',regex=False),'v20_model_use'].astype(str).tolist())+' '.join(led.loc[led.source_id.astype(str).str.contains('DOE_',regex=False),'claim_boundary'].astype(str).tolist())
 ck('doe_si2030_not_direct_capex_forecast','not' in ldes.lower() and 'capex' in ldes.lower(),ldes[:1000])
 # Portfolio scope
 prim=pd.read_csv(ROOT/'data/processed/v19_dynamic_primary_portfolio.csv')
 headline=set(prim.portfolio_tech.astype(str))
 ck('headline_portfolio_exact_5',headline=={'V18_LFP_4h','V18_VRFB_10h','V18_VRFB_24h','V18_PSH_10h','V18_PSH_24h'},sorted(headline))
 ck('caes_h2_not_headline',not any(('CAES' in x or '_H2_' in x) for x in headline),sorted(headline))
 # Required 16 official cases remain distinct from two V20 evidence-horizon cases
 reg=pd.read_csv(ROOT/'storage_runner/scenarios_storage_master.csv')
 official=reg.loc[reg.v17_official_unique.astype(str).str.lower().isin({'true','1','yes'}),'scenario'].astype(str).tolist()
 ck('official_dynamic_scenarios_still_16',len(official)==16 and len(set(official))==16,official)
 # HF2 scenario-registry claim contract must agree with the explicit runtime contract.
 offreg=reg.loc[reg.scenario.astype(str).isin(official)].copy()
 registry_runtime_ok=(len(offreg)==16 and
     offreg.v18_storage_chronology_mode.astype(str).eq('intraday_cyclic').all() and
     offreg.v18_storage_portfolio_mode.astype(str).eq('evidence_bounded').all() and
     offreg.v18_claim_scope.astype(str).str.contains('no intermonth, seasonal, full-8760, or multiweather operational claim',case=False,regex=False).all() and
    offreg.v19_claim_scope.astype(str).str.contains('no intermonth, seasonal, full-8760, or multiweather operational claim',case=False,regex=False).all())
 ck('hf2_official_registry_runtime_and_claim_contract',registry_runtime_ok,
    offreg[['scenario','v18_storage_chronology_mode','v18_storage_portfolio_mode']].to_dict('records'))
 meta_bad=[]
 for sc in official:
  mp=ROOT/'storage_cases'/sc/'STORAGE_SCENARIO_META.json'
  try:
   md=json.loads(mp.read_text(encoding='utf-8'))
   if str(md.get('v18_storage_chronology_mode'))!='intraday_cyclic' or str(md.get('v18_storage_portfolio_mode'))!='evidence_bounded' or 'no intermonth, seasonal, full-8760, or multiweather operational claim' not in str(md.get('v18_claim_scope','')).lower() or 'no intermonth, seasonal, full-8760, or multiweather operational claim' not in str(md.get('v19_claim_scope','')).lower():
    meta_bad.append([sc,md.get('v18_storage_chronology_mode'),md.get('v18_storage_portfolio_mode'),md.get('v18_claim_scope')])
  except Exception as e:
   meta_bad.append([sc,repr(e)])
 ck('hf2_prepared_case_metadata_matches_runtime_contract',not meta_bad,meta_bad)
 ehrows=reg.loc[reg.scenario.astype(str).isin(EH)]
 ck('equal_horizon_registry_two_rows',len(ehrows)==2 and not ehrows.v17_official_unique.astype(str).str.lower().isin({'true','1','yes'}).any(),ehrows.scenario.astype(str).tolist())
 # V20-HF2 explicit Layer-B/C runtime contract: preserve V17 intraday chronology.
 try:
  rc=pd.read_csv(ROOT/'data/processed/v20_layer_b_runtime_contract.csv').fillna('')
  expected_runtime=set(official)|set(EH)
  contract_ok=(len(rc)==18 and set(rc.scenario.astype(str))==expected_runtime and
               rc.storage_chronology_mode.astype(str).eq('intraday_cyclic').all() and
               rc.v18_storage_portfolio_mode.astype(str).eq('evidence_bounded').all())
 except Exception:
  contract_ok=False
 ck('hf2_layer_b_c_runtime_contract_exact_18_intraday_evidence_bounded',contract_ok,{'rows':len(rc) if 'rc' in locals() else None})
 # Equal-horizon scientific identity checks
 eh_ok=True; eh_detail=[]
 for new,src in EH.items():
  nd=ROOT/'storage_cases'/new; sd=ROOT/'storage_cases'/src
  if not nd.is_dir() or not sd.is_dir(): eh_ok=False; eh_detail.append({'case':new,'error':'missing case'}); continue
  nf={p.name:sha(p) for p in (nd/'inputs').iterdir() if p.is_file()}; sf={p.name:sha(p) for p in (sd/'inputs').iterdir() if p.is_file()}
  drift=sorted(k for k in sf if k!='gen_build_costs.csv' and nf.get(k)!=sf[k])
  c=pd.read_csv(nd/'inputs/gen_build_costs.csv'); y=pd.to_numeric(c.build_year).astype(int); m=c.GENERATION_PROJECT.astype(str).str.endswith('-V18_LFP_4h') & y.ge(2033)
  vals=sorted(set(round(float(x),6) for x in pd.to_numeric(c.loc[m,'gen_overnight_cost'])))
  audit=nd/'audits/V20_EQUAL_HORIZON_COST_AUDIT.json'; a=json.loads(audit.read_text(encoding='utf-8')) if audit.exists() else {}
  caseok=(not drift and int(m.sum())==192 and len(vals)==1 and a.get('status')=='PASS' and a.get('post2030_lfp_extrapolation_used') is False and a.get('invented_vrfb_or_psh_learning_curve_used') is False)
  eh_ok &= caseok; eh_detail.append({'case':new,'source':src,'non_cost_drift':drift,'changed_rows':int(m.sum()),'held_costs':vals,'audit_status':a.get('status')})
 ck('equal_horizon_pair_strict_intervention_scope',eh_ok,eh_detail)
 # Cell-level intervention audit: gen_build_costs may differ only on the declared LFP rows.
 eh_cells_ok=True; eh_cells=[]
 for new,src in EH.items():
  a=pd.read_csv(ROOT/'storage_cases'/src/'inputs/gen_build_costs.csv').reset_index(drop=True)
  b=pd.read_csv(ROOT/'storage_cases'/new/'inputs/gen_build_costs.csv').reset_index(drop=True)
  if list(a.columns)!=list(b.columns) or len(a)!=len(b):
   eh_cells_ok=False; eh_cells.append({'case':new,'error':'table geometry drift'}); continue
  neq=(a.astype(str)!=b.astype(str))
  rows=sorted(set(int(i) for i in neq.index[neq.any(axis=1)]))
  q=b.loc[rows] if rows else b.iloc[0:0]
  scope=(len(rows)==192 and q['GENERATION_PROJECT'].astype(str).str.endswith('-V18_LFP_4h').all() and pd.to_numeric(q['build_year'],errors='raise').astype(int).ge(2033).all())
  allowed_cols={'gen_overnight_cost','gen_storage_energy_overnight_cost','gen_fixed_om'}
  changed_cols={str(c) for c in a.columns if bool(neq[c].any())}
  scope &= changed_cols<=allowed_cols
  eh_cells_ok &= scope; eh_cells.append({'case':new,'changed_rows':len(rows),'changed_columns':sorted(changed_cols),'scope_pass':bool(scope)})
 ck('equal_horizon_gen_build_costs_cell_scope',eh_cells_ok,eh_cells)
 # Existing V17 low/mid/high battery-cost scenarios must propagate to the future LFP candidate.
 def unique_future_lfp_cost(case,year=2058):
  d=pd.read_csv(ROOT/'storage_cases'/case/'inputs/gen_build_costs.csv')
  m=d.GENERATION_PROJECT.astype(str).str.endswith('-V18_LFP_4h') & pd.to_numeric(d.build_year,errors='raise').astype(int).eq(year)
  vals=sorted(set(round(float(x),9) for x in pd.to_numeric(d.loc[m,'gen_overnight_cost'],errors='raise')))
  return vals
 lfp_case_costs={
  'low':unique_future_lfp_cost('SL12_COST_LOW_OBSERVED'),
  'mid':unique_future_lfp_cost('SL01_OBSERVED_STANDARDIZED'),
  'high':unique_future_lfp_cost('SL14_COST_HIGH_OBSERVED'),
 }
 lfp_cost_ok=all(len(v)==1 for v in lfp_case_costs.values()) and lfp_case_costs['low'][0] < lfp_case_costs['mid'][0] < lfp_case_costs['high'][0]
 ck('future_lfp_low_mid_high_cost_sensitivity_propagates',lfp_cost_ok,lfp_case_costs)
 # Static physics/claim guardrails for PSH and duration interpretation.
 model=p.read_text(encoding='utf-8')
 ck('psh_duration_designs_share_single_zone_resource_ceiling','V18_PSH_Shared_Provincial_Resource_Ceiling' in model and 'union(PUMPED_HYDRO_BUILD_GENS, V18_PSH_GENS)' in model,'shared existing + V18 PSH provincial ceiling')
 ck('hf3_hydro_pumped_capacity_plan_counts_v18_psh_family',
    'capacity_plan_project_set' in model and
    'tc == "Hydro_Pumped" && v18_storage_portfolio_mode != "disabled"' in model and
    'return union(GENS_BY_TECHNOLOGY[tc], V18_PSH_GENS)' in model,
    'inherited Hydro_Pumped planning floor is met by legacy PSH + explicit V18 PSH duration designs')
 # The inherited pumped-hydro plan must be physically satisfiable under the same
 # provincial resource ceiling used by the V18 PSH duration designs.
 psh_floor_bad=[]
 for sc in list(official)+list(EH):
  ip=ROOT/'storage_cases'/sc/'inputs'
  try:
   gi=pd.read_csv(ip/'gen_info.csv')
   cp=pd.read_csv(ip/'capacity_plans.csv')
   legacy=gi.loc[gi.gen_tech.astype(str).eq('Hydro_Pumped')].copy()
   lim={str(r.gen_load_zone):float(r.gen_capacity_limit_mw) for _,r in legacy.iterrows()}
   for _,r in cp.loc[cp.gen_tech.astype(str).eq('Hydro_Pumped') & pd.to_numeric(cp.period,errors='coerce').ge(2028)].iterrows():
    z=str(r.load_zones); floor=float(r.planned_capacity_mw); ceiling=float(lim[z])
    if floor>ceiling+1e-6: psh_floor_bad.append([sc,z,int(r.period),floor,ceiling])
  except Exception as e:
   psh_floor_bad.append([sc,'ERROR',repr(e)])
 ck('hf3_hydro_pumped_plan_floor_within_shared_resource_ceiling',not psh_floor_bad,psh_floor_bad[:20])
 try:
  pa=json.loads((ROOT/'audits/v20/V20_HF3_PSH_CAPACITY_PLAN_COMPATIBILITY_AUDIT.json').read_text(encoding='utf-8'))
  pa_ok=(pa.get('status')=='PASS' and pa.get('all_floors_within_shared_resource_ceiling') is True and pa.get('all_zones_have_10h_and_24h_candidates') is True and int(pa.get('rows_requiring_future_psh_to_meet_floor',0))>0)
 except Exception as e:
  pa_ok=False; pa={'error':repr(e)}
 ck('hf3_psh_capacity_plan_compatibility_audit_pass',pa_ok,pa)
 ck('future_duration_is_discrete_design_not_continuous_ep_optimization',all(x in headline for x in ['V18_LFP_4h','V18_VRFB_10h','V18_VRFB_24h','V18_PSH_10h','V18_PSH_24h']) and len(headline)==5,'headline technology-duration designs are discrete candidates')
 ck('hf2_future_build_constraints_exclude_stock_anchor',
    model.count('y > INITIALIZATION_TRANSITION_PERIOD') >= 4 and
    'V18_Disable_Legacy_Battery_Future_Build' in model and
    'V18_Disable_Legacy_Battery_Future_Energy_Build' in model,
    'future-only Battery/PSH exclusions do not touch 2023 stock anchor')
 ck('hf2_optimized_legacy_exception_preserved_in_generic_battery_disable',
    model.count('!(LEGACY_OPTIMIZED_REALLOCATION && y == INITIALIZATION_TRANSITION_PERIOD)') >= 2,
    'generic Battery disable constraints preserve the 2023 optimized legacy allocation')
 ck('hf2_runtime_chronology_scope_not_hardcoded_monthly',
    ':storage_chronology_scope => [storage_chronology_scope]' in model and
    '2028_2060_representative_days_intraday_cyclic_2023_stock_only' in model,
    'solve_status chronology scope follows actual runtime mode')
 batch=(ROOT/'tools/run_official_batch.py').read_text(encoding='utf-8')
 ck('hf2_headline_runner_explicit_intraday_contract',
    'V20_RUNTIME_CONTRACT' in batch and 'runtime_contract_for(scenario)' in batch and
    'not _true(status.get("storage_intermonth_soc_linked"))' in batch and
    'not _true(status.get("storage_long_duration_claim_supported"))' in batch,
    'Layer B/C strict gate forbids intermonth/seasonal claim promotion')
 # Python syntax for active V20 tools
 active=['check_v20_package.py','prepare_v20_equal_horizon_pair.py','run_v20_layer_b16.py','run_v20_equal_horizon_pair.py','run_v20_chronology_isolation_diagnostics.py','build_v20_result_tables.py','verify_v20_manifest.py']
 bad=[]
 for name in active:
  fp=ROOT/'tools'/name
  try: compile(fp.read_text(encoding='utf-8'),str(fp),'exec')
  except Exception as e: bad.append([name,repr(e)])
 ck('active_v20_python_syntax',not bad,bad)
 # Windows launcher integrity for the run-first release.
 active_bats=['V20_ENV_DEFAULTS.bat','CHECK_V20_MANIFEST.bat','CHECK_V20_STATIC.bat','CHECK_V20_RUNTIME.bat','PREP_V20.bat','RUN_V20_A4_PRIMARY_1x10.bat','RUN_V20_A8_1x10.bat','RUN_V20_B2_CORE_1x10.bat','RUN_V20_B16_1x10.bat','RUN_V20_C2_EQUAL_HORIZON_1x10.bat','RUN_V20_B2_MONTHLY_LINKED_DIAGNOSTIC_1x10.bat','RUN_V20_B2_FEASIBILITY_ISOLATION_DIAGNOSTIC_1x10.bat','RUN_V20_HF3_RETEST_B2C2_4_1x10.bat','RUN_V20_PHASE1_CORE_8_1x10.bat','RUN_V20_REMAINING_18_1x10.bat','RUN_V20_REQUIRED_26_1x10.bat','BUILD_V20_RESULTS.bat']
 bat_missing=[]; bat_ctrl=[]
 for name in active_bats:
  fp=ROOT/name
  if not fp.is_file(): bat_missing.append(name); continue
  raw=fp.read_bytes()
  badctrl=[x for x in raw if x<32 and x not in (9,10,13)]
  if badctrl: bat_ctrl.append([name,sorted(set(badctrl))])
 ck('active_v20_windows_launchers_present',not bat_missing,bat_missing)
 ck('active_v20_windows_launchers_no_control_byte_corruption',not bat_ctrl,bat_ctrl)
 rt=(ROOT/'CHECK_V20_RUNTIME.bat').read_text(encoding='utf-8') if (ROOT/'CHECK_V20_RUNTIME.bat').is_file() else ''
 ck('v20_runtime_checks_production_source_and_gurobi','call CHECK_V17_SOURCE_LOAD.bat' in rt and 'check_v17_runtime.jl' in rt and 'import sys,numpy,pandas,matplotlib' in rt,'Python deps + production Julia source load + JuMP/Gurobi native-route probe')
 phase=(ROOT/'RUN_V20_PHASE1_CORE_8_1x10.bat').read_text(encoding='utf-8') if (ROOT/'RUN_V20_PHASE1_CORE_8_1x10.bat').is_file() else ''
 ck('run_first_phase1_is_exactly_A4_B2_C2',all(x in phase for x in ['RUN_V20_A4_PRIMARY_1x10.bat','RUN_V20_B2_CORE_1x10.bat','RUN_V20_C2_EQUAL_HORIZON_1x10.bat']) and 'CHECK_V20_RUNTIME.bat' in phase,'8 decisive cases before remaining 18')
 matrixp=ROOT/'docs/V20_REQUIRED_26_CASE_MATRIX.csv'
 try:
  mx=pd.read_csv(matrixp,encoding='utf-8-sig')
  matrix_ok=(len(mx)==26 and mx.scenario.astype(str).nunique()==26 and int((mx.run_phase=='PHASE1_CORE8').sum())==8 and int((mx.run_phase=='PHASE2_REMAINING18').sum())==18)
 except Exception:
  matrix_ok=False
 ck('required_26_case_matrix_exact_8_plus_18',matrix_ok,{'rows':len(mx) if 'mx' in locals() else None})
 # Distribution cleanliness is a *release-build* property, not a runtime property.
 # CHECK_V20_STATIC.bat is intentionally re-runnable after Layer A/B/C outputs exist,
 # so normal runs do not fail merely because strict results have already been created.
 if args.release_clean:
  forbidden=[]
  for p in ROOT.rglob('*'):
   if p.is_file() and (p.suffix.lower() in {'.pyc','.pyo'} or '__pycache__' in p.parts): forbidden.append(p.relative_to(ROOT).as_posix())
  ck('release_no_python_cache',not forbidden,forbidden[:20])
  solver_dirs=[x for x in [ROOT/'outputs',ROOT/'batch_logs',ROOT/'failed_diagnostics',ROOT/'v20_outputs',ROOT/'modules/correction2033/future_correction_outputs',ROOT/'modules/correction2033/future_correction_batch_logs',ROOT/'modules/correction2033/batch_logs'] if x.exists() and any(x.iterdir())]
  ck('release_no_shipped_solver_or_result_outputs',not solver_dirs,[x.relative_to(ROOT).as_posix() for x in solver_dirs])
  machine=[]
  pats=[re.compile('/mnt/' + 'data/'), re.compile(r'(?i)[A-Z]:[\\/]Users[\\/]')]
  text_suffixes={'.txt','.md','.csv','.json','.py','.jl','.bat','.ps1','.toml','.yaml','.yml','.ini','.cfg'}
  for p in ROOT.rglob('*'):
   if not p.is_file() or p.suffix.lower() not in text_suffixes: continue
   try: txt=p.read_text(encoding='utf-8')
   except Exception: continue
   if any(rx.search(txt) for rx in pats): machine.append(p.relative_to(ROOT).as_posix())
  ck('release_no_machine_specific_absolute_paths',not machine,machine[:30])
 # File-name portability and source-package path budget measured from the short
 # V20 root. Normal resume runs intentionally retain solver outputs and logs;
 # those runtime artifacts are already governed by --release-clean above and
 # must not retroactively change the portability verdict of the frozen package.
 # In particular, attempt labels plus exported diagnostic filenames can exceed
 # the distribution budget even though no distributed source path does.
 runtime_dir_names={
  'outputs','batch_logs','failed_diagnostics','v20_outputs',
  'future_correction_outputs','future_correction_batch_logs','__pycache__'
 }
 all_paths=list(ROOT.rglob('*'))
 source_paths=[p for p in all_paths if not any(part in runtime_dir_names for part in p.relative_to(ROOT).parts)]
 paths=[p.relative_to(ROOT).as_posix() for p in source_paths]
 longnames=[x for x in paths if len(Path(x).name)>100]
 ck('portable_filename_length_le_100',not longnames,longnames[:10])
 maxrel=max(map(len,paths),default=0)
 ck('relative_path_budget_le_180',maxrel<=180,maxrel)
 status='PASS' if all(x['pass'] for x in checks) else 'FAIL'
 out={'version':'V20_HF4A_RUNTIME_PATH_BUDGET_AUDIT_FIX','status':status,'solver_certified':False,'solver_note':'Static/prepared package gate only. Numerical claims require local Julia/Gurobi strict certificates. Runtime outputs/logs are governed by --release-clean and excluded from the source-package path budget.','checks_total':len(checks),'checks_passed':sum(x['pass'] for x in checks),'checks':checks}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':status,'checks_passed':out['checks_passed'],'checks_total':out['checks_total']},ensure_ascii=False,indent=2))
 if status!='PASS':
  for x in checks:
   if not x['pass']: print('FAIL',x['check'],x['detail'])
  raise SystemExit(1)
if __name__=='__main__': main()
