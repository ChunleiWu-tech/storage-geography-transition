#!/usr/bin/env python3
"""Static + prepared-input release audit for V18R1. Does not claim solver success."""
from __future__ import annotations
from pathlib import Path
import hashlib,importlib.util,json,os,py_compile,subprocess,sys,tempfile,zipfile
import pandas as pd
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]; AUD=ROOT/'audits'; AUD.mkdir(parents=True,exist_ok=True)
CORE_SHA='2825377de801183dd624125d17d4f1541c70f724d48065b638026a774acd0a84'
EXPECTED_SCEN={f'FC{i:02d}_'+n for i,n in []}  # populated explicitly below
EXPECTED_SCEN={'FC01_BASE_OBSERVED','FC02_BASE_OPTIMAL','FC03_ADAPTIVE_OBSERVED','FC04_ADAPTIVE_OPTIMAL','FC05_ADAPTIVE_TXFIXED_OBSERVED','FC06_ADAPTIVE_TXFIXED_OPTIMAL','FC07_EXPANDED_OBSERVED','FC08_EXPANDED_OPTIMAL'}
EXPECTED_PAIRS={'FC_BASE','FC_ADAPTIVE','FC_ADAPTIVE_TXFIXED','FC_EXPANDED_PRESSURE'}
PRIMARY={'LDES_VRFB_10h','LDES_VRFB_24h','LDES_PSH_10h','LDES_PSH_24h'}
EXPANDED={'LDES_CAES_10h','LDES_CAES_24h','LDES_CAES_100h','LDES_VRFB_10h','LDES_VRFB_24h','LDES_H2_100h','LDES_PSH_10h','LDES_PSH_24h'}
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def load(name,p):
 spec=importlib.util.spec_from_file_location(name,p); mod=importlib.util.module_from_spec(spec); sys.path.insert(0,str(ROOT/'tools')); spec.loader.exec_module(mod); return mod
errors=[]; checks={}
required=['README_ZH.md','README_EN.md','VERSION_V18R1.txt','requirements_v17.txt','base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl','base_model_v39/storage_base_template_v17.zip','storage_runner/scenarios_future_correction.csv','storage_runner/run_future_correction_one.jl','storage_runner/check_v18r1_runtime.jl','tools/prepare_future_correction_cases.py','tools/validate_future_correction_case.py','tools/audit_future_correction_pair_identity.py','tools/apply_future_correction_portfolio.py','tools/apply_future_correction_transmission.py','tools/run_future_correction_batch.py','tools/build_future_correction_summary.py','tools/write_future_correction_result_lineage.py','postprocess/ne_style.py','postprocess/plot_future_correction_main_figure.py','CHECK_V18R1_PACKAGE.bat','CHECK_V18R1_RUNTIME.bat','RUN_V18R1_PREPARE_ALL_8.bat','RUN_V18R1_PRIMARY_4_1x10.bat','RUN_V18R1_ALL_8_1x10.bat','RUN_V18R1_BUILD_SUMMARY_AND_FIG6.bat','RUN_V18R1_CLEAN_REBUILD_AND_RUN_ALL_8_1x10.bat','CHECK_PUBLICATION_SOURCE_GATE.bat','OFFICIAL_SOURCE_ARCHIVE_INDEX.csv','OFFICIAL_SOURCE_ARCHIVE_INDEX.json','SWITCH_CHINA_INPUT_LINEAGE_AUDIT.json','SWITCH_CHINA_INPUT_LINEAGE_FILE_AUDIT.csv','shared_source_snapshots/official/PNNL_ESGC_Cost_Performance_Database_v2024.xlsx']
for rel in required:
 ok=(ROOT/rel).is_file(); checks['required::'+rel]=ok
 if not ok: errors.append('missing required file: '+rel)
cache=[p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.name=='__pycache__' or p.suffix in {'.pyc','.pyo'}]; checks['cache_items']=cache
if cache: errors.append('Python cache artifacts remain')
# no solved outputs or logs shipped
for part in ['future_correction_outputs','future_correction_batch_logs','failed_diagnostics']:
 p=ROOT/part
 files=[x for x in p.rglob('*') if x.is_file()] if p.exists() else []
 checks['shipped_'+part+'_files']=len(files)
 if files: errors.append(f'{part} contains shipped runtime files')
# no machine-specific absolute paths in active source/config files
bad_paths=[]
for p in list(ROOT.rglob('*.py'))+list(ROOT.rglob('*.jl'))+list(ROOT.rglob('*.bat'))+list(ROOT.rglob('*.md')):
 try: txt=p.read_text(encoding='utf-8',errors='ignore')
 except Exception: continue
 win_user_a='C:'+'\\'+'Users'+'\\'; win_user_b='C:'+'/'+'Users'+'/'
 if win_user_a in txt or win_user_b in txt: bad_paths.append(p.relative_to(ROOT).as_posix())
checks['machine_specific_source_paths']=bad_paths
if bad_paths: errors.append('Machine-specific paths remain: '+', '.join(bad_paths[:10]))
# syntax
syntax=[]
with tempfile.TemporaryDirectory() as td:
 for i,p in enumerate(sorted(ROOT.rglob('*.py'))):
  try: py_compile.compile(str(p),cfile=str(Path(td)/f'{i}.pyc'),doraise=True); syntax.append({'file':p.relative_to(ROOT).as_posix(),'pass':True})
  except Exception as exc: syntax.append({'file':p.relative_to(ROOT).as_posix(),'pass':False,'error':str(exc)}); errors.append(f'Python syntax: {p}: {exc}')
checks['python_syntax']=syntax
core=ROOT/'base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl'; checks['frozen_core_sha256']=sha(core) if core.is_file() else None
if checks['frozen_core_sha256']!=CORE_SHA: errors.append('Frozen V17T2R5 scientific core hash drift')
# template
try:
 with zipfile.ZipFile(ROOT/'base_model_v39/storage_base_template_v17.zip') as z: bad=z.testzip(); names=set(z.namelist())
 checks['template_zip']={'bad_member':bad,'members':len(names)}
 if bad or not {'inputs/periods.csv','inputs/gen_info.csv','inputs/timeseries.csv','inputs/timepoints.csv'}<=names: errors.append('Base template ZIP failed integrity/required member check')
except Exception as exc: errors.append('Template ZIP error: '+str(exc))
# scenario locks
sc=pd.read_csv(ROOT/'storage_runner/scenarios_future_correction.csv'); checks['scenario_count']=len(sc)
if set(sc.scenario.astype(str))!=EXPECTED_SCEN: errors.append('Scenario names drift from eight-case V18R1 design')
if set(sc.pair_id.astype(str))!=EXPECTED_PAIRS or not (sc.groupby('pair_id').size()==2).all(): errors.append('V18R1 matched-pair structure invalid')
if set(pd.to_numeric(sc.target_year,errors='raise').astype(int))!={2033}: errors.append('V18R1 target year must be 2033 only')
if set(pd.to_numeric(sc.time_resolution_h,errors='raise').astype(int))!={4}: errors.append('V18R1 must use 4 h representative chronology')
if set(sc.storage_chronology_mode.astype(str))!={'monthly_linked'}: errors.append('V18R1 chronology must be monthly_linked')
if set(sc.legacy_allocation_mode.astype(str))!={'observed_standardized','optimized_reallocation'}: errors.append('Legacy allocation modes invalid')
# exact portfolio tables
pri=pd.read_csv(ROOT/'data/processed/future_correction_primary_portfolio_2033.csv'); exp=pd.read_csv(ROOT/'data/processed/ldes_technology_portfolio_2033.csv')
if set(pri.portfolio_tech.astype(str))!=PRIMARY or len(pri)!=4: errors.append('Primary evidence-bounded portfolio drift')
if set(exp.portfolio_tech.astype(str))!=EXPANDED or len(exp)!=8: errors.append('Expanded pressure-test portfolio drift')
checks['primary_portfolio']=sorted(PRIMARY); checks['expanded_portfolio']=sorted(EXPANDED)
# source gate
res=subprocess.run([sys.executable,str(ROOT/'tools/check_publication_source_gate.py'),'--stage','source'],cwd=ROOT,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
checks['source_gate_return_code']=res.returncode
if res.returncode!=0: errors.append('Publication source gate failed: '+(res.stdout+res.stderr)[-2000:])
# prepared cases + identity
try:
 val=load('v18validator',ROOT/'tools/validate_future_correction_case.py'); case_rows=[]
 for _,r in sc.iterrows():
  s=str(r.scenario); case=ROOT/'future_correction_cases'/s; mp=case/'FUTURE_CORRECTION_SCENARIO_META.json'; meta=json.loads(mp.read_text(encoding='utf-8')) if mp.is_file() else r.to_dict(); rr=val.validate_case(case,meta,False); case_rows.append({'scenario':s,**rr})
  if rr.get('status')!='PASS': errors.append(f'Prepared case validation failed: {s}: {rr.get("errors")}')
 checks['prepared_case_validation']=case_rows
except Exception as exc: errors.append('Prepared case validation exception: '+str(exc))
try:
 pair=load('v18pair',ROOT/'tools/audit_future_correction_pair_identity.py').audit_all_pairs(False); checks['identification_audit_status']=pair.get('status')
 if pair.get('status')!='PASS': errors.append('V18 matched-pair/intervention identity audit failed')
except Exception as exc: errors.append('Identification audit exception: '+str(exc))
# solver ladder and scope locks are lexical contracts around unchanged core
batch=(ROOT/'tools/run_future_correction_batch.py').read_text(encoding='utf-8')
for tok in ['targetyear_deterministic_concurrent','targetyear_homogeneous_dual_crossover','scaled_barrier','dual_simplex','hard_deterministic_concurrent_simplex','gurobi_dual_simplex_optimal_status','gurobi_hard_deterministic_concurrent_simplex_optimal_status','V17_ECONOMIC_BAR_ITER_LIMIT','100000']:
 if tok not in batch: errors.append('Solver ladder token missing: '+tok)
prep=(ROOT/'tools/prepare_future_correction_cases.py').read_text(encoding='utf-8')
for tok in ['full_transition_path_claim_supported": False','investment timing','technology_choice_endogenous_when_portfolio_enabled','province_or_model_zone_choice_endogenous']:
 checks['scope_token::'+tok]=tok.lower() in prep.lower()
 if not checks['scope_token::'+tok]: errors.append('Scope token missing: '+tok)
result={'version':'V18R1_FUTURE_CORRECTION_STANDALONE','status':'PASS' if not errors else 'FAIL','errors':errors,'scenario_count':len(sc),'pair_count':sc.pair_id.nunique(),'scientific_core_changed':False,'frozen_core_sha256':checks.get('frozen_core_sha256'),'design':'2033 single-target-year adaptive correction layer on frozen V17T2R5 core','capacity_type_siting_duration_optimization':True,'investment_timing_path_claim_supported':False,'full_8760_hour_claim_supported':False,'strict_solver_native_optimality_required':True,'julia_gurobi_solve_executed_in_build_environment':False,'checks':checks}
(AUD/'STATIC_PACKAGE_AUDIT_V18R1.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x))+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x)))
raise SystemExit(0 if result['status']=='PASS' else 1)
