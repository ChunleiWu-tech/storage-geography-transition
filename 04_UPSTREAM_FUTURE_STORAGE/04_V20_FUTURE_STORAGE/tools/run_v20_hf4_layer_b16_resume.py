#!/usr/bin/env python3
"""Resume V20 Layer B serially with the HF5 exact reduced formulation."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_official_batch as rb  # noqa: E402
import run_v20_layer_b16 as b16  # noqa: E402

FORMULATION = "V20HF5_equivalent_reduced_formulation_v1"
ALGEBRAIC_REDUCTION = "V20HF5_equivalent_hourly_coordinate_projection_v1"
MODEL = ROOT / "base_model_v39_hf4" / "cheer_power_storage_hf4_projected.jl"
RUNNER = ROOT / "storage_runner" / "run_storage_one_solver_task_hf4_projected.jl"
AUDIT = ROOT / "audits" / "v20" / "V20_LAYER_B_16_SOLVER_AUDIT.json"
SUMMARY = ROOT / "audits" / "v20" / "V20_LAYER_B_16_SOLVER_SUMMARY.csv"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def projected_gate(status: dict[str, str]) -> bool:
    if status.get("legacy_reallocation_formulation_version") != FORMULATION:
        return False
    if status.get("algebraic_reduction_version") != ALGEBRAIC_REDUCTION:
        return False
    try:
        expected_legacy_count = 32 if status.get("legacy_allocation_mode") == "optimized_reallocation" else 0
        if int(float(status.get("legacy_energy_variable_projection_count", "nan"))) != expected_legacy_count:
            return False
        if float(status.get("total_omitted_hourly_columns", "0")) <= 0:
            return False
    except ValueError:
        return False
    if not rb._true(status.get("algebraic_reduction_preserves_scientific_inputs")):
        return False
    if not rb._true(status.get("algebraic_reduction_preserves_objective_and_projected_feasible_set")):
        return False
    if status.get("legacy_allocation_mode") == "optimized_reallocation":
        return all(rb._true(status.get(k)) for k in [
            "legacy_national_energy_identity_pass",
            "legacy_zone_caps_encoded_as_variable_bounds",
            "legacy_energy_variable_projection_active",
            "legacy_projected_energy_output_reconstruction",
        ]) and not any(rb._true(status.get(k)) for k in [
            "legacy_national_energy_closure_constraint_emitted",
            "legacy_common_duration_constraints_emitted",
        ])
    return not rb._true(status.get("legacy_energy_variable_projection_active"))


def write_lineage(scenario: str, outdir: Path) -> None:
    status = outdir / "solve_status.csv"
    payload = {
        "schema_version": "v20_hf5_reduced_model_result_lineage_v1",
        "status": "PASS",
        "scenario": scenario,
        "formulation_version": FORMULATION,
        "equivalence_scope": "eliminate fixed-zero non-CCS and objective-neutral startup/shutdown hourly coordinates in every unfinished case; additionally eliminate exactly determined legacy-energy coordinates only in optimized cases",
        "projected_model": str(MODEL.relative_to(ROOT)).replace("\\", "/"),
        "projected_model_sha256": sha256(MODEL),
        "projected_runner": str(RUNNER.relative_to(ROOT)).replace("\\", "/"),
        "projected_runner_sha256": sha256(RUNNER),
        "solve_status_sha256": sha256(status),
        "generated_local_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (outdir / "HF5_REDUCED_MODEL_RESULT_LINEAGE.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def projected_solver_once(scenario: str, julia: str, stage1_profile: str, suffix: str, attempt_label: str, log_path: Path) -> dict[str, object]:
    suffix = "__hf5_reduced_scaled_barrier_official"
    attempt_label = "hf5_reduced_scaled_barrier_official"
    log_path = rb.LOGDIR / f"{scenario}__{attempt_label}.log"
    rb.clean_attempt_output(scenario, suffix)
    chronology_mode, portfolio_mode = rb.runtime_contract_for(scenario)
    cmd = [
        julia, str(RUNNER), "--scenario", scenario,
        "--solver_profile", stage1_profile,
        "--cleanup_profile", "stage1_official_release",
        "--solver_output_suffix", suffix,
        "--storage_chronology_mode", chronology_mode,
        "--v18_storage_portfolio_mode", portfolio_mode,
    ]
    rc, seconds = rb.run_cmd(cmd, log_path)
    attempt_dir, preserved = rb.preserve_attempt(scenario, attempt_label, suffix)
    status = rb.read_status(attempt_dir)
    success = rb.strict_success(status, rc, preserved, attempt_dir) and projected_gate(status)
    if success:
        canonical_dir, centralized = rb.promote_success(scenario, attempt_dir)
        write_lineage(scenario, Path(canonical_dir))
    else:
        canonical_dir, centralized = attempt_dir, preserved
    return {
        "return_code": rc,
        "seconds": seconds,
        "attempt_output_dir": attempt_dir,
        "central_output_dir": canonical_dir,
        "centralized": centralized,
        "status": status,
        "success": success,
        "attempt_label": attempt_label,
        "stage1_profile": stage1_profile,
    }


def main() -> None:
    # Give one continuous Barrier trajectory the same 60 h total budget that
    # HF4 divided among three fresh processes, so progress is not discarded.
    os.environ["V17_ECONOMIC_BARRIER_TIME_LIMIT_SECONDS"] = "216000"
    os.environ["V17_ECONOMIC_BAR_ITER_LIMIT"] = "500000"
    scenarios = b16.official_scenarios()
    if len(scenarios) != 16:
        raise SystemExit(f"Expected 16 official Layer-B scenarios, found {len(scenarios)}")
    before = {s: b16.valid_row(s) for s in scenarios}
    missing = [s for s in scenarios if before[s] is None]
    print(f"V20-HF5 Layer B: {16-len(missing)}/16 strict outputs retained; {len(missing)} remain.")

    run_records: dict[str, dict] = {}
    julia = os.environ.get("JULIA_EXE", "julia")
    for scenario in missing:
        print(f"\n=== HF5 Layer B next case: {scenario} ===")
        record = projected_solver_once(
            scenario, julia, "scaled_barrier", "__stage1_official",
            "hf5_reduced_scaled_barrier_official", rb.LOGDIR / f"{scenario}__hf5_reduced_scaled_barrier_official.log"
        )
        run_records[scenario] = record
        if not bool(record.get("success")):
            print(f"{scenario}: HF5 continuous Barrier did not produce a strict result; continuing to the next independent case.")

    rows = []
    for scenario in scenarios:
        row = b16.valid_row(scenario)
        if row is not None:
            rows.append(row)
    frame = pd.DataFrame(rows)
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(SUMMARY, index=False)
    # Retain the familiar storage batch summary format as a full strict snapshot.
    frame.to_csv(rb.SUMMARY, index=False)
    passed = len(frame) == 16 and frame["scenario"].nunique() == 16
    payload = {
        "version": "V20_LAYER_B_EVIDENCE_DIRECT_16_HF5_REDUCED_RESUME_SAFE",
        "scope": "full16",
        "cost_regime": "evidence_direct",
        "chronology_regime": "intraday_cyclic_v17_native",
        "portfolio_regime": "evidence_bounded",
        "already_valid_before_run": 16 - len(missing),
        "attempted_this_run": len(missing),
        "hf5_reduced_cases_attempted": missing,
        "strict_rows_after_run": len(frame),
        "all_solver_native_strict_success": passed,
        "status": "PASS" if passed else "INCOMPLETE",
    }
    AUDIT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
