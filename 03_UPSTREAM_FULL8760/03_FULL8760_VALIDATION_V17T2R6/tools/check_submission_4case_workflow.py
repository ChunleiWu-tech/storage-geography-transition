#!/usr/bin/env python3
"""Fail-closed static gate for the two-phase submission reproduction workflow."""
from pathlib import Path
import ast
import json


ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / "tools" / "run_hf18p2_prior_optimal_two_parallel.py"
RECOVERY = ROOT / "tools" / "run_hf18p2_quality_recovery_two_parallel.py"
LAUNCHER = ROOT / "RUN_SUBMISSION_REPRODUCE_ALL4_HF18P2_2X10.bat"
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"


def assigned_tuple(path: Path, name: str) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                value = ast.literal_eval(node.value)
                return tuple(str(item) for item in value)
    raise RuntimeError(f"{name} not found in {path}")


prior_targets = assigned_tuple(PRIOR, "TARGETS")
recovery_targets = assigned_tuple(RECOVERY, "TARGETS")
prior_text = PRIOR.read_text(encoding="utf-8")
recovery_text = RECOVERY.read_text(encoding="utf-8")
launcher_text = LAUNCHER.read_text(encoding="utf-8")
model_text = MODEL.read_text(encoding="utf-8")

expected_prior = {
    "TY2033_FULL8760_OPTIMAL",
    "TY2033_FULL8760_LDES_OPTIMAL",
}
expected_recovery = {
    "TY2033_FULL8760_OBSERVED",
    "TY2033_FULL8760_LDES_OBSERVED",
}
checks = {
    "prior_targets_exact": set(prior_targets) == expected_prior and len(prior_targets) == 2,
    "recovery_targets_exact": set(recovery_targets) == expected_recovery and len(recovery_targets) == 2,
    "partition_is_disjoint_complete":
        set(prior_targets).isdisjoint(recovery_targets) and
        len(set(prior_targets) | set(recovery_targets)) == 4,
    "prior_profile_is_proven_r24p1":
        "full8760_gurobi1302_hf18p2_fixed_portfolio_minimum_ideal_firm_capacity_distance_barrier" in prior_text,
    "recovery_profile_is_r24p2":
        "full8760_gurobi1302_hf18p2_componentwise_scale_aware_quality_recovery_barrier" in recovery_text,
    "both_phases_two_by_ten":
        "ThreadPoolExecutor(max_workers=2" in prior_text and
        "ThreadPoolExecutor(max_workers=2" in recovery_text and
        'env["V17_SOLVER_THREADS"] = "10"' in prior_text and
        'env["V17_SOLVER_THREADS"] = "10"' in recovery_text,
    "phase_order_is_prior_then_recovery":
        launcher_text.find("run_hf18p2_prior_optimal_two_parallel.py") <
        launcher_text.find("run_hf18p2_quality_recovery_two_parallel.py"),
    "each_phase_fail_closed": launcher_text.count("if errorlevel 1 exit /b 1") >= 5,
    "strict_source_dependency_declared": "V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT" in launcher_text,
    "prior_results_fingerprinted": "fingerprint_output" in prior_text,
    "recovery_validates_prior_fingerprint":
        "prior_success_record" in recovery_text and "validate_result_fingerprint" in recovery_text,
    "combined_all4_summary_required":
        "COMBINED_ALL4" in recovery_text and "all_four_certificates_success" in recovery_text,
    "quality_attributes_complete": all(name in model_text for name in (
        '"ConstrResidual"', '"ConstrSResidual"',
        '"DualResidual"', '"DualSResidual"')),
    "eight_physical_audits_present": model_text.count("maximum_tolerance_ratio=") >= 8,
    "positive_gap_claim_boundary_retained": "CERTIFIED_POSITIVE_ROBUSTNESS_GAP" in model_text,
}
failed = [name for name, passed in checks.items() if not passed]
payload = {
    "version": "SUBMISSION_FULL8760_R24P2_TWO_PHASE",
    "status": "PASS" if not failed else "FAIL",
    "checks_passed": sum(checks.values()),
    "checks_total": len(checks),
    "failed": failed,
    "prior_targets": prior_targets,
    "recovery_targets": recovery_targets,
    "solver_threads_per_case": 10,
    "max_parallel_per_phase": 2,
    "scientific_model_changed_by_workflow": False,
    "numerical_evidence_status": "PENDING_R24P2_OBSERVED_SERVER_CERTIFICATES",
}
(ROOT / "audits").mkdir(exist_ok=True)
(ROOT / "audits" / "SUBMISSION_FULL8760_WORKFLOW_GATE.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2))
if failed:
    raise SystemExit(1)
