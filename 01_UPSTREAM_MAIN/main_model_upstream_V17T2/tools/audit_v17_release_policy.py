#!/usr/bin/env python3
"""Static audit that V17 publishes stage 1 and restricts degenerate gross flows."""
from __future__ import annotations
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
paths={
 'model':ROOT/'base_model_v39/cheer_power_storage_v1.jl',
 'runner':ROOT/'storage_runner/run_storage_one_solver_task.jl',
 'batch':ROOT/'tools/run_official_batch.py',
 'preflight':ROOT/'postprocess/preflight_spatial_legacy_outputs.py',
 'readme':ROOT/'README.md',
 'dictionary':ROOT/'docs/OUTPUT_DATA_DICTIONARY_V17_ZH.md',
}
texts={k:p.read_text(encoding='utf-8') for k,p in paths.items()}
checks=[]
def add(n,p,d): checks.append({'check':n,'pass':bool(p),'detail':d})
m=texts['model']; b=texts['batch']; p=texts['preflight']; r=texts['runner']
add('official_default', 'cleanup_profile="stage1_official_release"' in m and 'cleanup_profile::String="stage1_official_release"' in r, 'formal default')
add('official_source', 'publication_solution_source = "stage1_solver_certified_economic_optimum"' in m, 'source label')
add('single_stage1_source_label', 'stage1_solver_certified_economic_optimum_already_clean' not in m, 'all certified stage-1 points use one canonical source label')
add('release_gate_stage1', 'stage1_official_release_pass' in m[m.find('solve_gate_pass ='):m.find('pre_audit_result_tier')], 'formal gate')
add('cleanup_diagnostic_nonblocking', all(x in m for x in ['cleanup_diagnostic_attempted','cleanup_diagnostic_converged','cleanup_diagnostic_nonblocking']), 'separate diagnostic state')
add('no_cleanup_official_fallback', 'cleanup_fallbacks' not in b and 'retry_cleanup_for_certified_stage1' not in b, 'official route tree')
add('stage1_solver_fallbacks', all(x in b for x in ['deterministic_concurrent','dual_simplex','stage1_uncertified_try_next_solver_route']), 'controlled alternatives')
add('gross_dispatch_disclosure', all(x in m for x in ['gross_dispatch_degeneracy_sensitive = true','gross_dispatch_operational_interpretation_allowed = false']), 'interpretation restriction')
add('policy_file_exported', 'RESULT_INTERPRETATION_POLICY.csv' in m, 'machine-readable policy')
add('restricted_files_labeled', all(x in m for x in ['df_dispatch_full[!, :DegeneracySensitive]','df_DispatchTx[!, :DegeneracySensitive]','df_storage_operation_audit[!, :DegeneracySensitive]']), 'row labels')
add('preflight_policy_enforced', all(x in p for x in ['RESULT_INTERPRETATION_POLICY.csv','OperationalMechanismInterpretationAllowed','stage1_solver_certified_economic_optimum']), 'downstream enforcement')
add('docs_disclose_limits', '禁止用途' in texts['dictionary'] or '不得' in texts['dictionary'] and 'degenerate' in texts['readme'].lower(), 'human-readable interpretation boundary')
summary={'version':'V17','checks':len(checks),'passed':sum(x['pass'] for x in checks),'all_pass':all(x['pass'] for x in checks)}
out=ROOT/'audits/V17_RELEASE_POLICY_AUDIT.json'; out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({'summary':summary,'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'summary':summary,'failed':[x for x in checks if not x['pass']]},ensure_ascii=False,indent=2))
raise SystemExit(0 if summary['all_pass'] else 1)
