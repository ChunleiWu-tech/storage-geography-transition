#!/usr/bin/env python3
"""Optional V20-HF3 chronology-isolation diagnostics for the Layer-B core pair.

This tool is NOT a publication runner and never promotes results to outputs/*__main.
It isolates three mechanisms without contaminating the headline Layer-B/C experiment:
(1) the V17-native intraday baseline with the V18/V20 portfolio disabled;
(2) linked-month chronology alone; and (3) linked-month chronology plus the evidence-bounded portfolio.
"""
from __future__ import annotations
from pathlib import Path
import argparse, json, os, shutil, subprocess, sys, time

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=['SL01_OBSERVED_STANDARDIZED','SL02_OPTIMAL_REALLOCATION']
MODES=[
    ('intraday_no_portfolio','intraday_cyclic','disabled'),
    ('monthly_no_portfolio','monthly_linked','disabled'),
    ('monthly_evidence_bounded','monthly_linked','evidence_bounded'),
]

def run_one(sc:str,label:str,chrono:str,portfolio:str,julia:str)->dict:
    suffix='__v18_pressure_test'
    local=ROOT/'storage_cases'/sc/'outputs'/f'{sc}{suffix}'
    if local.exists(): shutil.rmtree(local)
    logdir=ROOT/'batch_logs'/'v20_hf2_chronology_diagnostics'/sc
    logdir.mkdir(parents=True,exist_ok=True)
    log=logdir/f'{label}.log'
    cmd=[julia,'storage_runner/run_storage_one_solver_task.jl','--scenario',sc,
         '--solver_profile','scaled_barrier','--cleanup_profile','stage1_official_release',
         '--solver_output_suffix',suffix,'--storage_chronology_mode',chrono,
         '--v18_storage_portfolio_mode',portfolio]
    t0=time.time()
    with log.open('w',encoding='utf-8',errors='replace') as f:
        f.write('DIAGNOSTIC_ONLY: true\nCOMMAND: '+' '.join(cmd)+'\n\n'); f.flush()
        rc=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT).returncode
    dest=ROOT/'audits'/'v20'/'chronology_isolation'/sc/label
    if dest.exists(): shutil.rmtree(dest)
    dest.mkdir(parents=True,exist_ok=True)
    copied=[]
    if local.exists():
        for name in ['solve_status.csv','infeasibility_conflict_constraints.csv','infeasibility_context.json','scenario_config.json','solve_gate_diagnostics.json']:
            src=local/name
            if src.exists(): shutil.copy2(src,dest/name); copied.append(name)
    return {'scenario':sc,'diagnostic':label,'chronology_mode':chrono,'portfolio_mode':portfolio,
            'return_code':rc,'seconds':time.time()-t0,'evidence_files':copied,
            'publication_eligible':False}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--scenario',choices=SCENARIOS,action='append',help='Default: both core scenarios')
    ap.add_argument('--julia',default=os.environ.get('JULIA_EXE','julia'))
    a=ap.parse_args(); scenarios=a.scenario or SCENARIOS
    rows=[]
    for sc in scenarios:
        for label,chrono,portfolio in MODES:
            print(f'V20-HF3 diagnostic {sc}: {label}',flush=True)
            rows.append(run_one(sc,label,chrono,portfolio,a.julia))
    out=ROOT/'audits'/'v20'/'V20_HF2_CHRONOLOGY_ISOLATION_DIAGNOSTICS.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({'version':'V20_HF3_DIAGNOSTIC_R3','publication_eligible':False,'runs':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'DIAGNOSTIC_COMPLETE','runs':len(rows),'publication_eligible':False},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
