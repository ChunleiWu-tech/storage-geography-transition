#!/usr/bin/env python3
"""Resume-safe serial runner for V20 Layer B required 16 evidence-direct cases."""
from pathlib import Path
import argparse, json, os, subprocess, sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
AUD=ROOT/'audits/v20/V20_LAYER_B_16_SOLVER_AUDIT.json'; SNAP=ROOT/'audits/v20/V20_LAYER_B_16_SOLVER_SUMMARY.csv'
CORE=['SL01_OBSERVED_STANDARDIZED','SL02_OPTIMAL_REALLOCATION']

def official_scenarios():
 d=pd.read_csv(ROOT/'storage_runner/scenarios_storage_master.csv'); m=d.v17_official_unique.astype(str).str.lower().isin({'true','1','yes'}); return d.loc[m,'scenario'].astype(str).tolist()

def valid_row(s):
 sys.path.insert(0,str(ROOT/'tools'))
 import run_official_batch as rb
 from publication_source_common import validate_result_fingerprint
 out=ROOT/'outputs'/f'{s}__main'; case=ROOT/'storage_cases'/s
 if not out.is_dir(): return None
 st=rb.read_status(str(out)); strict=rb.strict_success(st,0,True,str(out)); fp,_=validate_result_fingerprint(ROOT,out,case,s)
 if not (strict and fp): return None
 row={'scenario':s,'publication_strict_success':True,'result_tier':'official_stage1_economic_optimum_resume_validated'}; row.update(st); row['scenario']=s; return row

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--core-only', action='store_true', help='Run only the observed/optimized core pair as an early run-first gate. Full 16 runner later resumes and skips these if still valid.')
 args=ap.parse_args()
 all_scenarios=official_scenarios()
 if len(all_scenarios)!=16: raise SystemExit(f'Expected 16 official V20 Layer B scenarios, found {len(all_scenarios)}')
 scenarios=CORE if args.core_only else all_scenarios
 audit_path=(ROOT/'audits/v20/V20_LAYER_B_CORE2_SOLVER_AUDIT.json') if args.core_only else AUD
 snap_path=(ROOT/'audits/v20/V20_LAYER_B_CORE2_SOLVER_SUMMARY.csv') if args.core_only else SNAP
 existing={s:valid_row(s) for s in scenarios}; missing=[s for s in scenarios if existing[s] is None]
 rc=0
 if missing:
  print('V20 Layer B: solving missing/invalid cases:',', '.join(missing))
  cmd=[sys.executable,str(ROOT/'tools/run_official_batch.py'),'--max-workers','1','--julia',os.environ.get('JULIA_EXE','julia'),'--only',*missing,'--skip-validate','--skip-postprocess','--enable-controlled-fallback']
  rc=subprocess.run(cmd,cwd=ROOT).returncode
 rows=[]
 for s in scenarios:
  r=valid_row(s)
  if r is not None: rows.append(r)
 d=pd.DataFrame(rows); snap_path.parent.mkdir(parents=True,exist_ok=True); d.to_csv(snap_path,index=False)
 expected=len(scenarios)
 passed=(rc==0 and len(d)==expected and d.scenario.nunique()==expected and d.publication_strict_success.astype(bool).all())
 out={'version':'V20_LAYER_B_CORE2_HF3_RESUME_SAFE' if args.core_only else 'V20_LAYER_B_EVIDENCE_DIRECT_16_HF3_RESUME_SAFE','scope':'core2' if args.core_only else 'full16','cost_regime':'evidence_direct','chronology_regime':'intraday_cyclic_v17_native','portfolio_regime':'evidence_bounded','already_valid_before_run':expected-len(missing),'attempted_this_run':len(missing),'strict_rows_after_run':len(d),'all_solver_native_strict_success':bool(passed),'return_code':rc,'status':'PASS' if passed else 'FAIL'}
 audit_path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(out,ensure_ascii=False,indent=2))
 if not passed: raise SystemExit(1)
if __name__=='__main__': main()
