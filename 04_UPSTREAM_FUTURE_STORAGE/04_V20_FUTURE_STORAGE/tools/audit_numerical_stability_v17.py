#!/usr/bin/env python3
"""Cross-layer audit of V17 stage-1-official numerical semantics."""
from __future__ import annotations
from pathlib import Path
import csv, json

ROOT = Path(__file__).resolve().parents[1]
MODEL = (ROOT/'base_model_v39/cheer_power_storage_v1.jl').read_text(encoding='utf-8')
RUNNER = (ROOT/'storage_runner/run_storage_one_solver_task.jl').read_text(encoding='utf-8')
BATCH = (ROOT/'tools/run_official_batch.py').read_text(encoding='utf-8')
PREFLIGHT = (ROOT/'postprocess/preflight_spatial_legacy_outputs.py').read_text(encoding='utf-8')
RUNTIME = (ROOT/'storage_runner/check_v17_runtime.jl').read_text(encoding='utf-8')
NUMVER='V17_solver_certified_stage1_official_release_degeneracy_disclosure_cleanup_diagnostic_nonblocking_json_safe'
CLEANVER='V17_stage1_official_release_optional_sparse_face_diagnostic_cleanup_nonblocking'
checks=[]
def add(n,p,d): checks.append({'check':n,'pass':bool(p),'detail':d})

add('economic_objective_scaled', 'ECONOMIC_OBJECTIVE_SCALE_USD = 1.0e6' in MODEL and '@objective(mod, Min, ScaledEconomicObjective)' in MODEL, 'economic objective scaling only')
add('stage1_barrier_no_crossover', all(t in MODEL for t in ['profile == "scaled_barrier"','method = 2','crossover = 0','lp_warm_start = 0']), 'primary stage-1 algorithm')
add('strict_solver_tolerances', all(t in MODEL for t in ['SOLVER_FEASIBILITY_TOL = 1.0e-7','SOLVER_OPTIMALITY_TOL = 1.0e-7','SOLVER_BAR_CONV_TOL = 1.0e-8']), 'no tolerance relaxation')
add('solver_native_certificate', all(t in MODEL for t in ['stage1_native_solver_certificate_pass','strict_solver_native','stage1_economic_optimality_gate_pass = stage1_native_solver_certificate_pass']), 'native certificate is formal proof')
add('external_diagnostics_nonblocking', all(t in MODEL for t in ['stage1_dual_objective_diagnostic_only','stage1_external_diagnostic_warning']), 'ObjBound and reconstructed dual are diagnostics')
add('official_profile_default', 'cleanup_profile="stage1_official_release"' in MODEL and 'cleanup_profile::String="stage1_official_release"' in RUNNER, 'formal run does not invoke cleanup')
add('official_route_branch', all(t in MODEL for t in ['String(cleanup_profile) == "stage1_official_release"','publication_solution_source = "stage1_solver_certified_economic_optimum"','stage1_official_release_selected = true']), 'stage 1 selected as publication result')
add('solve_gate_uses_stage1', 'regularization_share_gate_pass && stage1_official_release_pass' in MODEL and 'stage1_official_release_pass || push!(solve_gate_failure_reasons' in MODEL, 'cleanup convergence is not a release condition')
add('cleanup_nonblocking_fields', all(t in MODEL for t in ['cleanup_diagnostic_attempted','cleanup_diagnostic_converged','cleanup_diagnostic_nonblocking']), 'diagnostic state is explicit')
add('degeneracy_disclosure', all(t in MODEL for t in ['gross_dispatch_degeneracy_sensitive = true','gross_dispatch_operational_interpretation_allowed = false','RESULT_INTERPRETATION_POLICY.csv']), 'gross-flow interpretation is restricted')
add('diagnostic_audits_not_hard_gate', 'V17 NON-BLOCKING DEGENERACY DISCLOSURE' in MODEL and 'diagnostic_degeneracy_review_pass ||' not in MODEL[MODEL.find('solve_gate_pass ='):MODEL.find('pre_audit_result_tier')], 'degeneracy review cannot block release')
add('row_level_restrictions', all(t in MODEL for t in [':ResultSource',':DegeneracySensitive',':OperationalMechanismInterpretationAllowed',':AllowedUse']), 'labels survive downstream separation')
add('optional_cleanup_routes_retained', all(f'name == "{r}"' in MODEL for r in ['sparse_face_primal_pstart','sparse_face_concurrent_pstart','sparse_face_barrier','sparse_face_dual']), 'sparse-face experiments remain available')
add('pstart_ephemeral', all(t in MODEL for t in ['cleanup_pstart_vars = all_variables(mod)',':cleanup_raw_pstart_serialized => [false]']), 'diagnostic PStart is memory-only')
add('no_basis_or_dual_start', all(t not in MODEL for t in ['VariableBasisStatus','ConstraintBasisStatus','"CrossoverBasis",','"DStart",','set_start_value(']), 'basis-independent architecture')
add('official_batch_stage1_only', all(t in BATCH for t in ['"scaled_barrier", "__stage1_official"','"deterministic_concurrent", "__stage1_concurrent_official"','"dual_simplex", "__stage1_dual_official"']) and 'cleanup_fallbacks' not in BATCH, 'official fallback changes only stage-1 solver')
add('certified_stage1_stops_retry', 'stage1_certified_but_downstream_release_gate_failed' in BATCH, 'downstream failures are not hidden by algorithm changes')
add('batch_requires_interpretation_policy', 'RESULT_INTERPRETATION_POLICY.csv' in BATCH and 'gross_dispatch_operational_interpretation_allowed' in BATCH, 'promotion verifies restriction policy')
add('preflight_stage1_source', 'stage1_solver_certified_economic_optimum' in PREFLIGHT and 'stage1_official_release_pass' in PREFLIGHT, 'postprocessing accepts official stage 1 only')
add('preflight_gross_flow_labels', all(t in PREFLIGHT for t in ['dispatch.csv','DispatchTx.csv','storage_operation_audit.csv','OperationalMechanismInterpretationAllowed']), 'postprocessing validates row-level restrictions')
add('runtime_cleanup_is_probe', 'configure_sparse_face_primal_pstart!' in RUNTIME and 'apply_raw_pstart!' in RUNTIME, 'optional algorithm/API route remains testable')
add('numerical_version_synchronized', all(NUMVER in t for t in [MODEL,BATCH,PREFLIGHT]), 'cross-layer version string')
add('cleanup_policy_version_synchronized', all(CLEANVER in t for t in [MODEL,BATCH,PREFLIGHT]), 'cross-layer policy string')
add('pure_lp_and_no_cdr', all(t in MODEL for t in ['audit_model_integrality','STORAGE_CDR_MODULES_COMPILED = false','cdr_module_exclusion_gate_pass']), 'scope unchanged')
add('json_safe_diagnostics', '_write_json_safe' in MODEL, 'failed diagnostics cannot be masked by NaN serialization')

summary={'version':'V17','checks':len(checks),'passed':sum(x['pass'] for x in checks),'all_pass':all(x['pass'] for x in checks)}
aud=ROOT/'audits'; aud.mkdir(exist_ok=True)
with (aud/'V17_NUMERICAL_STABILITY_AUDIT.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['check','pass','detail']); w.writeheader(); w.writerows(checks)
(aud/'V17_NUMERICAL_STABILITY_AUDIT.json').write_text(json.dumps({'summary':summary,'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'summary':summary,'failed':[x for x in checks if not x['pass']]},ensure_ascii=False,indent=2))
raise SystemExit(0 if summary['all_pass'] else 1)
