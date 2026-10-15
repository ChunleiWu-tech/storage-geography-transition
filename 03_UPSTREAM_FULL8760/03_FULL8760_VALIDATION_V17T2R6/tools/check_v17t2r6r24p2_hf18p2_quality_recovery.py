#!/usr/bin/env python3
"""Static scientific-scope gate for the R24P2 two-case quality recovery."""
from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"
HELPER = ROOT / "base_model_v39" / "full8760_hf18_fixed_portfolio_validation.jl"
RUNNER = ROOT / "tools" / "run_hf18p2_quality_recovery_two_parallel.py"
LAUNCHER = ROOT / "RUN_V17T2R6R24P2_HF18P2_QUALITY_RECOVERY_OBSERVED_2X10.bat"
RUNTIME = ROOT / "tools" / "check_hf18p2_gurobi1302_runtime.jl"
MANIFEST = ROOT / "HF18P2_R24P2_PATCH_MANIFEST_SHA256.json"
required = [MODEL, HELPER, RUNNER, LAUNCHER, RUNTIME, MANIFEST,
            ROOT / "storage_runner" / "run_targetyear_one.jl"]
missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
if missing:
    raise SystemExit("HF18P2 R24P2 missing files: " + ", ".join(missing))

model = MODEL.read_text(encoding="utf-8")
helper = HELPER.read_text(encoding="utf-8")
runner = RUNNER.read_text(encoding="utf-8")
launcher = LAUNCHER.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
manifest_paths = [str(row.get("path", "")).replace("\\", "/")
                  for row in manifest.get("files", [])]

observed_targets = (
    '"TY2033_FULL8760_LDES_OBSERVED"',
    '"TY2033_FULL8760_OBSERVED"',
)
protected_targets = (
    '"TY2033_FULL8760_OPTIMAL"',
    '"TY2033_FULL8760_LDES_OPTIMAL"',
)

checks = {
    "quality_recovery_profile_isolated":
        "full8760_gurobi1302_hf18p2_componentwise_scale_aware_quality_recovery_barrier" in model,
    "version_is_r24p2":
        "V17T2R6R24P2_HF18P2_fixed_portfolio_full8760_componentwise_scale_aware_quality_recovery" in model,
    "strict_source_gate_retained": "_hf18_strict_source_gate" in helper,
    "fixed_portfolio_retained": "_v17t2r6r22_hf18_apply_fixed_portfolio!" in model,
    "canonical_zero_audited":
        "canonicalized_value_count" in helper and "max_canonicalization_abs" in helper,
    "canonical_zero_tolerance_unchanged":
        "V17T2R6R24_HF18P2_CANONICAL_ZERO_TOL = 1.0e-7" in model,
    "ideal_firm_capacity_retained": "HF18P2FirmCapacityRepair" in model,
    "ideal_dispatch_retained": "HF18P2FirmDispatchRepair" in model,
    "ideal_spinning_reserve_retained": "HF18P2FirmSpinningReserveRepair" in model,
    "ideal_surplus_absorption_retained": "HF18P2SurplusAbsorptionCapacityRepair" in model,
    "original_balance_retained": "@constraint(mod, Zone_Energy_Balance" in model,
    "original_distributed_balance_retained": "@constraint(mod, Distributed_Energy_Balance" in model,
    "original_planning_reserve_retained":
        "Enforce_Planning_Reserve_Margin" in model and
        "Enforce_Explicit_Peak_Planning_Reserve_Margin" in model,
    "original_soc_constraints_retained":
        "State_Of_Charge_Upper_Limit" in model and "Track_State_Of_Charge" in model,
    "distance_objective_unchanged":
        "@objective(mod, Min, HF18P2TotalRobustnessDistanceMW)" in model,
    "zero_only_original_pass_unchanged":
        "V17T2R6R24_HF18P2_ORIGINAL_FEASIBILITY_TOL_MW = 1.0e-3" in model,
    "positive_gap_not_original_pass": "CERTIFIED_POSITIVE_ROBUSTNESS_GAP" in model,
    "separate_export_contract": "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE.json" in model,
    "separate_quality_attribution": "HF18P2_QUALITY_ATTRIBUTION.json" in model,
    "no_normal_economic_export": "return :hf18p2_complete" in model,
    "same_barrier_no_crossover_route": "method = 2" in model and "crossover = 0" in model,
    "gurobi_1302_locked": "GUROBI_RUNTIME_VERSION == (13, 0, 2)" in model,
    "maxvio_fully_attributed_for_lp": all(name in model for name in (
        '"BoundVio"', '"ConstrVio"', '"ConstrResidual"',
        '"DualVio"', '"DualResidual"', '"ComplVio"')),
    "scaled_residuals_gated":
        '"ConstrSResidual"' in model and '"DualSResidual"' in model and
        "hf18p2_scaled_residual_gate_pass" in model,
    "maxvio_decomposition_gated": "hf18p2_maxvio_decomposition_gate_pass" in model,
    "componentwise_native_gate": "hf18p2_componentwise_native_quality_gate_pass" in model,
    "core_physical_gate": "hf18p2_core_physical_gate_pass" in model,
    "eight_physical_audits": all(name in model for name in (
        'audit="zone_energy_balance"',
        'audit="distributed_energy_balance"',
        'audit="planning_reserve_shortfall"',
        'audit="explicit_peak_reserve_shortfall"',
        'audit="full8760_cyclic_soc_step_closure"',
        'audit="storage_soc_bounds"',
        'audit="ideal_firm_capacity_link"',
        'audit="ideal_absorption_capacity_link"')),
    "physical_tolerances_scale_aware":
        "physical_audit_power_tol" in model and "physical_audit_energy_tol" in model,
    "only_two_observed_targets":
        all(target in runner for target in observed_targets) and
        "TARGETS = (" in runner and
        "ThreadPoolExecutor(max_workers=2" in runner,
    "two_prior_successes_protected":
        all(target in runner for target in protected_targets) and
        "prior_success_record" in runner and "validate_result_fingerprint" in runner,
    "ten_threads_each":
        'env["V17_SOLVER_THREADS"] = "10"' in runner and
        'set "V17_SOLVER_THREADS=10"' in launcher,
    "exactly_two_parallel":
        'set "V17T2R6_MAX_PARALLEL=2"' in launcher and
        "ThreadPoolExecutor(max_workers=2" in runner,
    "independent_outputs": "robustness_distance_8760_quality_recovery_outputs" in runner,
    "independent_logs": "batch_logs_robustness_distance_quality_recovery" in runner,
    "independent_locks": "run_locks_hf18p2_quality_recovery" in runner,
    "old_results_not_overwritten":
        "robustness_distance_8760_outputs" in runner and
        "Protected R24P1 certificate" in runner,
    "combined_four_case_summary":
        "COMBINED_ALL4" in runner and "all_four_certificates_success" in runner,
    "objective_acceptance_explicit_and_capped":
        'set "V17_STAGE1_CERT_STRICT_REL_TOL=1.0e-6"' in launcher and
        'set "V17_STAGE1_CERT_ACCEPT_REL_TOL=1.0e-5"' in launcher and
        "STAGE1_CERT_ACCEPT_REL_TOL <= 1.0e-5" in model,
    "no_input_payload_in_overlay":
        manifest.get("scientific_inputs_included") is False and
        not any(path.startswith("sensitivity_cases/") for path in manifest_paths),
}

failed = [name for name, passed in checks.items() if not passed]
payload = {
    "version": "V17T2R6R24P2_HF18P2",
    "status": "PASS" if not failed else "FAIL",
    "checks_passed": sum(checks.values()),
    "checks_total": len(checks),
    "failed": failed,
    "rerun_scope": [target.strip('"') for target in observed_targets],
    "protected_success_scope": [target.strip('"') for target in protected_targets],
    "scientific_scope": (
        "unchanged fixed strict target-year portfolios, inputs, full-8760 chronology, "
        "original constraints, RHS and minimum-MW robustness-distance objective"
    ),
    "gate_correction": (
        "attribute unscaled MaxVio to all applicable continuous-LP quality components; "
        "require scaled residual limits and eight independent original-unit physical closures"
    ),
    "claim_boundary": (
        "zero distance certifies the original fixed portfolio; positive distance is a quantified "
        "robustness gap and never an original-model PASS or actual technology build"
    ),
}
(ROOT / "audits").mkdir(exist_ok=True)
(ROOT / "audits" / "HF18P2_R24P2_STATIC_SCOPE_GATE.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2))
if failed:
    raise SystemExit(1)
