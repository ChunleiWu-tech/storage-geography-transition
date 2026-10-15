#!/usr/bin/env python3
"""V18 serial 16-case solve wrapper.

The scientific model is V18. Solver profiles/fallback mechanics are inherited from
V17 because they change numerical routing rather than the LP's scientific semantics.
No solver success is inferred: the wrapper requires the existing strict solver-native
publication gate for all 16 official scenarios.
"""
from __future__ import annotations
from pathlib import Path
import argparse, json, os, subprocess, sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SUMMARY=ROOT/'storage_runner/storage_batch_run_summary.csv'
REPORT=ROOT/'audits/V18_FULL16_SOLVER_WRAPPER_AUDIT.json'

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--julia', default=os.environ.get('JULIA_EXE','julia'))
    ap.add_argument('--continue-after-failure', action='store_true', help='Reserved; batch policy remains strict.')
    args=ap.parse_args()
    audit=subprocess.run([sys.executable, str(ROOT/'tools/audit_v18_static.py'), '--phase','cases'], cwd=ROOT)
    if audit.returncode != 0:
        raise SystemExit('V18 static/case audit failed before solve.')
    cmd=[sys.executable, str(ROOT/'tools/run_official_batch.py'), '--max-workers','1', '--julia',args.julia, '--skip-validate','--skip-postprocess','--enable-controlled-fallback']
    rc=subprocess.run(cmd,cwd=ROOT).returncode
    complete=False; passed=False; n=0
    if SUMMARY.exists():
        df=pd.read_csv(SUMMARY); n=len(df)
        complete=(n==16 and df['scenario'].astype(str).nunique()==16)
        passed=complete and df['publication_strict_success'].astype(str).str.lower().isin({'true','1','yes'}).all()
    payload={
        'version':'V18_FULL16_SERIAL_1x10_R1',
        'scientific_model':'V18_CHINA_FUTURE_STORAGE_PLANNING_TECH_DURATION_SITING_V1',
        'solver_route_lineage':'V17 numerical profiles/fallbacks reused; scientific LP is V18',
        'max_workers':1,
        'solver_threads':int(os.environ.get('V17_SOLVER_THREADS','10')),
        'batch_return_code':rc,
        'rows':n,
        'complete_16':complete,
        'all_solver_native_strict_success':passed,
        'status':'PASS' if rc==0 and passed else 'FAIL',
    }
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False,indent=2))
    if payload['status']!='PASS': raise SystemExit(1)

if __name__=='__main__': main()
