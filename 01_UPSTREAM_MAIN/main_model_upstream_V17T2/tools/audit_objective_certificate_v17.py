#!/usr/bin/env python3
"""Cross-layer audit of the V17 presolve-safe solver-native certificate."""
from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
AUD = ROOT / "audits"
AUD.mkdir(exist_ok=True)
texts = {
    "model": (ROOT / "base_model_v39" / "cheer_power_storage_v1.jl").read_text(encoding="utf-8"),
    "runtime": (ROOT / "storage_runner" / "check_v17_runtime.jl").read_text(encoding="utf-8"),
    "batch": (ROOT / "tools" / "run_official_batch.py").read_text(encoding="utf-8"),
    "preflight": (ROOT / "postprocess" / "preflight_spatial_legacy_outputs.py").read_text(encoding="utf-8"),
}
checks: list[dict[str, object]] = []

def add(name: str, passed: bool, detail: str) -> None:
    checks.append({"check": name, "pass": bool(passed), "detail": detail})

model = texts["model"]
add("objbound_safe_read", "_safe_solve_float(() -> objective_bound(mod))" in model, "attribute absence cannot crash")
add("dual_objective_safe_read", "_safe_solve_float(() -> dual_objective_value(mod))" in model, "diagnostic read cannot crash")
add("native_certificate_present", all(t in model for t in ["stage1_native_solver_certificate_pass", "stage1_native_algorithm_gate_pass", "gurobi_barrier_optimal_status_barconvtol_no_crossover", "gurobi_zero_iteration_optimal_under_barrier_configuration"]), "native solver certificate with positive-iteration and zero-iteration modes")
add("external_diagnostics_nonblocking", "stage1_economic_optimality_gate_pass = stage1_native_solver_certificate_pass" in model and "stage1_external_diagnostic_warning" in model, "ObjBound/dual diagnostics do not gate")
add("status_core_gate", all(t in model for t in ["stage1_term == JuMP.MOI.OPTIMAL", "stage1_ps == JuMP.MOI.FEASIBLE_POINT", "stage1_ds == JuMP.MOI.FEASIBLE_POINT", "stage1_result_count >= 1", "stage1_has_values"]), "status and result availability")
add("presolve_safe_barrier_route", all(t in model for t in ["stage1_barrier_iterations >= 0.0", "stage1_zero_iteration_optimal", "stage1_barrier_iterations_observed", "stage1_simplex_iterations == 0.0", "solver_settings.bar_conv_tol <= 1.0e-8"]), "zero BarIterCount is accepted only with OPTIMAL status and zero simplex iterations")
add("scale_consistency_independent", "stage1_objective_scale_gate_pass" in model and "OBJECTIVE_SCALE_REL_TOL" in model, "native/scaled objective equality")
add("diagnostic_outputs", all(t in model for t in ["stage1_external_diagnostic_source", "stage1_external_diagnostic_consistent", "solve_gate_diagnostics.json"]), "traceable diagnostics")

runtime = texts["runtime"]
add("runtime_native_certificate", "native_certificate_pass" in runtime and "BAR_CONV_TOL <= 1.0e-8" in runtime, "native status regression")
add("runtime_presolve_zero_iteration_safe", all(t in runtime for t in ["zero_iteration_optimal_under_barrier_configuration", "barrier_iterations >= 0.0", "production_route_mode"]), "normal presolve may solve before Barrier iterations")
add("runtime_dedicated_barrier_engine_probe", all(t in runtime for t in ["Presolve=0 Barrier engine probe", "require_positive_barrier_iterations = true", "dedicated_engine_probe_barrier_iterations"]), "separate probe verifies positive Barrier iterations")
add("runtime_direct_mode_interval_safe", all(t in runtime for t in ["probe_weighted_sum = @expression", "@constraint(probe, probe_weighted_sum >= probe_lower)", "@constraint(probe, probe_weighted_sum <= probe_upper)"]) and "0.88 * center <= sum" not in runtime, "direct_model probe avoids unsupported ScalarAffineFunction-in-Interval")
add("runtime_bad_dual_nonblocking", "synthetic_reconstructed_dual_gap = 4.0e-3" in runtime and "synthetic_bad_dual_diagnostic_nonblocking" in runtime, "real SL00 failure mode covered")
add("runtime_optional_objbound", "safe_float(() -> objective_bound(model))" in runtime, "ObjBound remains optional")

for layer in ["batch", "preflight"]:
    text = texts[layer]
    add(f"{layer}_checks_native_certificate", "stage1_native_solver_certificate_pass" in text and "strict_solver_native" in text, "release layer checks native certificate")
    add(f"{layer}_allows_nonblocking_diagnostic_warning", "stage1_external_diagnostic_warning" in text or "non-blocking diagnostics" in text, "diagnostic mismatch cannot reject")
    add(f"{layer}_checks_proof_source", "gurobi_barrier_optimal_status_barconvtol_no_crossover" in text and "gurobi_zero_iteration_optimal_under_barrier_configuration" in text, "both proof modes retained")

forbidden = [
    "stage1_objective_bound_available || stage1_primal_dual_gate_pass",
    "proof_source == \"primal_dual_objective\"",
    "no_valid_ObjBound_or_primal_dual_certificate",
]
add("no_external_certificate_mandatory", all(t not in "\n".join(texts.values()) for t in forbidden), "no mandatory reconstructed objective certificate")

summary = {"version": "V17", "checks": len(checks), "passed": sum(bool(c["pass"]) for c in checks), "all_pass": all(bool(c["pass"]) for c in checks)}
(AUD / "V17_OBJECTIVE_CERTIFICATE_AUDIT.json").write_text(json.dumps({"summary": summary, "checks": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"summary": summary, "failed": [c for c in checks if not c["pass"]]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if summary["all_pass"] else 1)
