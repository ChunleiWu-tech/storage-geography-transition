#!/usr/bin/env python3
"""Resume-safe serial runner for V20 mandatory equal-evidence-horizon pair."""
from pathlib import Path
import json, os, subprocess, sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
AUD=ROOT/'audits/v20/V20_LAYER_C_EQUAL_HORIZON_2_SOLVER_AUDIT.json'; SNAP=ROOT/'audits/v20/V20_LAYER_C_EQUAL_HORIZON_2_SOLVER_SUMMARY.csv'
SC=['V20EH01_OBSERVED','V20EH02_OPTIMAL']
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
 missing=[s for s in SC if valid_row(s) is None]; rc=0
 if missing:
  print('V20 Layer C: solving missing/invalid cases:',', '.join(missing))
  cmd=[sys.executable,str(ROOT/'tools/run_official_batch.py'),'--max-workers','1','--julia',os.environ.get('JULIA_EXE','julia'),'--only',*missing,'--skip-validate','--skip-postprocess','--enable-controlled-fallback']
  rc=subprocess.run(cmd,cwd=ROOT).returncode
 rows=[r for s in SC if (r:=valid_row(s)) is not None]; d=pd.DataFrame(rows); SNAP.parent.mkdir(parents=True,exist_ok=True); d.to_csv(SNAP,index=False)
 passed=(rc==0 and len(d)==2 and set(d.scenario)==set(SC) and d.publication_strict_success.astype(bool).all())
 out={'version':'V20_LAYER_C_EQUAL_EVIDENCE_HORIZON_PAIR_HF3_RESUME_SAFE','cost_regime':'equal_evidence_horizon_2030_hold','chronology_regime':'intraday_cyclic_v17_native','portfolio_regime':'evidence_bounded','already_valid_before_run':2-len(missing),'attempted_this_run':len(missing),'strict_rows_after_run':len(d),'all_solver_native_strict_success':bool(passed),'return_code':rc,'status':'PASS' if passed else 'FAIL'}
 AUD.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(out,ensure_ascii=False,indent=2))
 if not passed: raise SystemExit(1)
if __name__=='__main__': main()
