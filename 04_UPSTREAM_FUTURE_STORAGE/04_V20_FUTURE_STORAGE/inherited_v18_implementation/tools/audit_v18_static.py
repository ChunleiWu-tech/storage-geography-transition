#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse, json, hashlib, math
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PORT=ROOT/'data/processed/v18_storage_technology_portfolio.csv'
RAW=ROOT/'data/processed/pnnl_v2024_point_100mw_selected_storage.csv'
NREL4H=ROOT/'data/processed/nlr_2025_battery_4h_costs.csv'
MASTER=ROOT/'storage_runner/scenarios_storage_master.csv'
JULIA=ROOT/'base_model_v39/cheer_power_storage_v1.jl'
REPORT=ROOT/'audits/V18_STATIC_AUDIT.json'

def sha(p):
 h=hashlib.sha256();
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--phase',choices=['source','cases','all'],default='all'); a=ap.parse_args()
 checks=[]
 def safe(o):
  if isinstance(o, np.generic): return o.item()
  if isinstance(o, dict): return {str(k): safe(v) for k,v in o.items()}
  if isinstance(o, (list,tuple,set)): return [safe(v) for v in o]
  return o
 def ck(name,ok,detail=''):
  checks.append({'check':name,'pass':bool(ok),'detail':safe(detail)})

 spec=pd.read_csv(PORT); raw=pd.read_csv(RAW); nrel4h=pd.read_csv(NREL4H); master=pd.read_csv(MASTER); code=JULIA.read_text(encoding='utf-8'); batch=(ROOT/'tools/run_official_batch.py').read_text(encoding='utf-8')
 ck('portfolio_12_unique_candidates', len(spec)==12 and spec.portfolio_tech.nunique()==12, {'rows':len(spec),'unique':spec.portfolio_tech.nunique()})
 ck('portfolio_has_required_families', {'battery','flow','caes','hydrogen','psh'} <= set(spec.technology_family), sorted(set(spec.technology_family)))
 ck('headline_vs_pressure_test_partition', set(spec.headline_eligibility)=={'evidence_bounded','pressure_test_only'}, spec.groupby('headline_eligibility').size().to_dict())
 ck('caes_h2_pressure_test_only', spec.loc[spec.technology_family.isin(['caes','hydrogen']),'headline_eligibility'].eq('pressure_test_only').all())
 ck('psh_evidence_bounded_shared_ceiling', spec.loc[spec.technology_family.eq('psh'),'resource_treatment'].eq('shared_existing_zone_psh_ceiling').all())
 ck('no_unsupported_2035_rows_in_pnnl_extract', 2035 not in set(pd.to_numeric(raw.Year,errors='coerce').dropna().astype(int)), sorted(pd.to_numeric(raw.Year,errors='coerce').dropna().astype(int).unique()))
 expected_years={'V18_H2_24h':{2021,2030},'V18_H2_100h':{2021,2030}}
 ok=True; yr_detail={}
 for c in spec.portfolio_tech:
  ys=set(pd.to_numeric(raw.loc[raw.candidate_tech.eq(c),'Year'],errors='raise').astype(int)); yr_detail[c]=sorted(ys)
  exp=expected_years.get(c,{2023,2030}); ok &= ys==exp
 ck('pnnl_candidate_source_years_exact',ok,yr_detail)
 # Reference fields must trace exactly to extracted source rows.
 params={'total_installed_reference_usd_per_kw':'Total Installed Cost ($/kW)','fixed_om_reference_usd_per_kw_year':'Fixed O&M ($/kW-year)','round_trip_efficiency':'RTE (%)','calendar_life_years':'Calendar Life (yrs)'}
 trace_ok=True; trace=[]
 for _,r in spec.iterrows():
  c=r.portfolio_tech; y=int(r.reference_year)
  for col,param in params.items():
   q=raw[(raw.candidate_tech==c)&(raw.Year.astype(int)==y)&(raw.Parameter==param)]
   if len(q)!=1: trace_ok=False; trace.append((c,param,'rowcount',len(q))); continue
   val=float(q.iloc[0].Value); target=float(r[col])
   # PNNL database represents round-trip efficiency as fraction in current workbook.
   if not math.isclose(val,target,rel_tol=1e-9,abs_tol=1e-9): trace_ok=False; trace.append((c,param,val,target))
 ck('portfolio_parameters_trace_to_pnnl_extract',trace_ok,trace[:20])
 # NLR/NREL 2025 Appendix Table 2 exact values at all V18 build years plus endpoints.
 nrel_expected={
  2024:(334,334,334), 2028:(231,293,360), 2033:(171,257,345),
  2038:(139,230,333), 2043:(126,209,322), 2048:(113,187,312),
  2053:(104,172,304), 2058:(97,161,299), 2060:(94,157,297),
 }
 nrel_ok=True; nrel_detail={}
 for y,vals in nrel_expected.items():
  q=nrel4h[nrel4h.year.astype(int).eq(y)]
  got=None if len(q)!=1 else tuple(int(q.iloc[0][c]) for c in ['low_2024usd_per_kwh','mid_2024usd_per_kwh','high_2024usd_per_kwh'])
  nrel_detail[str(y)]={'expected':vals,'got':got}
  nrel_ok &= (got==vals)
 ck('nrel_2025_4h_table2_selected_years_exact',nrel_ok,nrel_detail)
 # Guard the V18-added shared PSH maximum against empty collection reductions.
 ck('v18_psh_shared_ceiling_empty_safe','maximum((gen_capacity_limit_mw[g] for g in PUMPED_HYDRO_BUILD_GENS' in code and '; init=0.0)' in code)
 ck('all_16_master_scenarios_v18_evidence_bounded',len(master)==16 and master.v18_storage_portfolio_mode.eq('evidence_bounded').all(), {'rows':len(master)})
 ck('all_16_master_scenarios_monthly_linked',len(master)==16 and master.v18_storage_chronology_mode.eq('monthly_linked').all())
 required_code=['V18_STORAGE_GENS','V18_PSH_Shared_Provincial_Resource_Ceiling','V18_Disable_Unbounded_Geologic_Build','V18_Disable_Legacy_Battery_Future_Build','V18_Disable_Legacy_PSH_Future_Build','Link_Intermonth_State_Of_Charge_V18','Storage_Planning_Reserve_Energy_Limit_Last_Occurrence_V18','STORAGE_MULTIWEATHER_CLAIM_SUPPORTED = false']
 ck('julia_contains_v18_science_guards',all(x in code for x in required_code),[x for x in required_code if x not in code])
 ck('julia_default_portfolio_evidence_bounded','v18_storage_portfolio_mode="evidence_bounded"' in code)
 ck('julia_default_chronology_monthly_linked','storage_chronology_mode="monthly_linked"' in code)
 ck('linked_month_ldes_planning_claim_explicitly_enabled','STORAGE_LONG_DURATION_CLAIM_SUPPORTED = true' in code and 'storage_long_duration_claim_supported = STORAGE_LONG_DURATION_CLAIM_SUPPORTED && storage_intermonth_soc_linked' in code)
 ck('full_chronological_claim_explicitly_disabled','STORAGE_FULL_CHRONOLOGICAL_CLAIM_SUPPORTED = false' in code)
 ck('multiweather_claim_explicitly_disabled','STORAGE_MULTIWEATHER_CLAIM_SUPPORTED = false' in code)
 required_status_fields=[':storage_chronology_mode => [storage_chronology_mode]',':v18_storage_portfolio_mode => [v18_storage_portfolio_mode]',':storage_intermonth_soc_linked => [storage_intermonth_soc_linked]',':storage_long_duration_claim_supported => [storage_long_duration_claim_supported]',':storage_full_chronological_claim_supported => [storage_full_chronological_claim_supported]',':storage_multiweather_claim_supported => [storage_multiweather_claim_supported]']
 ck('solve_status_exports_v18_runtime_semantics',all(x in code for x in required_status_fields),[x for x in required_status_fields if x not in code])
 required_batch_gates=['status.get(\"storage_chronology_mode\") == \"monthly_linked\"','status.get(\"v18_storage_portfolio_mode\") == \"evidence_bounded\"','_true(status.get(\"storage_intermonth_soc_linked\"))','_true(status.get(\"storage_long_duration_claim_supported\"))','not _true(status.get(\"storage_full_chronological_claim_supported\"))','not _true(status.get(\"storage_multiweather_claim_supported\"))']
 ck('official_batch_gate_certifies_v18_runtime_semantics',all(x in batch for x in required_batch_gates),[x for x in required_batch_gates if x not in batch])
 apply=(ROOT/'tools/apply_v18_storage_portfolio.py').read_text(encoding='utf-8')
 ck('non_lfp_post2030_freeze_not_extrapolation','build_year >= hi' in apply and 'freeze_{hi}' in apply and '2035' not in apply)
 ck('lfp_uses_nrel_4h_trajectory_and_pnnl_duration_ratio','NREL_2025_4h_case_trajectory_x_PNNL_2030_duration_ratio' in apply)

 case_rows=[]
 if a.phase in ('cases','all'):
  official=master[master.v17_official_unique.astype(str).str.lower().isin(['true','1','yes'])]
  for sc in official.scenario.astype(str):
   cdir=ROOT/'storage_cases'/sc; inp=cdir/'inputs'; ad=cdir/'audits'
   if not cdir.exists(): case_rows.append((sc,False,'missing_case')); continue
   try:
    g=pd.read_csv(inp/'gen_info.csv'); bc=pd.read_csv(inp/'gen_build_costs.csv'); pred=pd.read_csv(inp/'gen_build_predetermined.csv')
    v=g[g.gen_tech.astype(str).str.startswith('V18_')]
    res=pd.read_csv(inp/'storage_resource_limits_v18.csv')
    audit=json.load(open(ad/'V18_STORAGE_PORTFOLIO_APPLICATION.json',encoding='utf-8'))
    ok=(len(v)==382 and v.GENERATION_PROJECT.nunique()==382 and not pred.GENERATION_PROJECT.astype(str).str.contains('-V18_',regex=False).any() and len(res)==31 and audit.get('status')=='PASS')
    # monthly repeat structure: 12 days/period and 365 day equivalents/year
    ts=pd.read_csv(inp/'timeseries.csv'); periods=pd.read_csv(inp/'periods.csv').set_index('INVESTMENT_PERIOD')
    for p,gp in ts.groupby('ts_period'):
      yrs=int(periods.loc[int(p),'period_end']-periods.loc[int(p),'period_start']+1)
      ok &= len(gp)==12 and math.isclose(float(gp.ts_scale_to_period.sum())/yrs,365.0,abs_tol=1e-9)
    case_rows.append((sc,bool(ok),{'v18_rows':len(v),'psh_resource_rows':len(res)}))
   except Exception as e: case_rows.append((sc,False,repr(e)))
  ck('all_official_prepared_cases_v18_ready',all(x[1] for x in case_rows) and len(case_rows)==16,case_rows)

 payload={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','version':'V18_STATIC_SCIENCE_AUDIT_R3','phase':a.phase,'checks_total':len(checks),'checks_passed':sum(x['pass'] for x in checks),'portfolio_sha256':sha(PORT),'pnnl_extract_sha256':sha(RAW),'nrel_4h_table_sha256':sha(NREL4H),'julia_sha256':sha(JULIA),'checks':checks}
 REPORT.parent.mkdir(exist_ok=True); REPORT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:payload[k] for k in ['status','version','phase','checks_total','checks_passed']},ensure_ascii=False,indent=2))
 if payload['status']!='PASS':
  for x in checks:
   if not x['pass']: print('FAIL',x['check'],x['detail'])
  raise SystemExit(1)

if __name__=='__main__': main()
