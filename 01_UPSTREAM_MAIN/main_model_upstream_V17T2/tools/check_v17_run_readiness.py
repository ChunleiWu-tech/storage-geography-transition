#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import json, sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
checks=[]
def add(name, ok, detail=''): checks.append({'check':name,'pass':bool(ok),'detail':str(detail)})
required=[
 'base_model_v39/cheer_power_storage_v1.jl','base_model_v39/storage_base_template_v17.zip',
 'storage_runner/run_storage_one_solver_task.jl','storage_runner/check_v17_runtime.jl',
 'storage_runner/scenarios_storage_master.csv','tools/run_official_batch.py',
 'tools/prepare_storage_cases.py','tools/build_storage_base_case.py']
for rel in required: add('exists:'+rel,(ROOT/rel).exists(),rel)
model=(ROOT/'base_model_v39/cheer_power_storage_v1.jl').read_text(encoding='utf-8')
for token in ['profile == "scaled_barrier"','crossover = 0','cleanup_profile="stage1_official_release"','publication_solution_source = "stage1_solver_certified_economic_optimum"','gross_dispatch_operational_interpretation_allowed = false','sparse_face_diagnostic_primal_pstart',
              'Gurobi.GRBsetdblattrarray','Gurobi.GRBreset','_write_json_safe',
              'stage1_dual_objective_diagnostic_only','fresh_julia_process_per_attempt']:
    add('model:'+token,token in model,token)
for token in ['VariableBasisStatus','ConstraintBasisStatus','"CrossoverBasis",','"DStart",','set_start_value(']:
    add('forbidden:'+token,token not in model,token)
master=pd.read_csv(ROOT/'storage_runner/scenarios_storage_master.csv')
off=master[master.v17_official_unique.astype(str).str.lower().isin({'true','1','yes'})]
add('official_scenario_count',len(off)==16,len(off))
add('no_cdr_official',(~off.allow_beccs.astype(bool)).all() and off.nbccs_dac_genccs.astype(str).str.contains('nbccs_daccs_beccs_disabled',case=False,regex=False).all(),'no-CDR')
summary={'version':'V17','python':sys.executable,'checks':len(checks),'passed':sum(x['pass'] for x in checks),'all_pass':all(x['pass'] for x in checks),'details':checks}
(ROOT/'audits').mkdir(exist_ok=True)
(ROOT/'audits/V17_RUN_READINESS_AUDIT.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:summary[k] for k in ['version','python','checks','passed','all_pass']},indent=2))
if not summary['all_pass']:
    for x in checks:
        if not x['pass']: print('FAILED:',x)
    raise SystemExit(1)
