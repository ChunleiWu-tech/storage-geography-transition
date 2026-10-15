#!/usr/bin/env python3
"""Resume FC08 with the V20-HF5 algebraically equivalent reduced LP."""
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
import run_future_correction_batch as base  # noqa: E402

SCENARIO = "FC08_EXPANDED_OPTIMAL"
FORMULATION = "V20HF5_equivalent_reduced_formulation_v1"
ALGEBRAIC_REDUCTION = "V20HF5_equivalent_hourly_coordinate_projection_v1"
MODEL = ROOT / "base_model_v39_hf4" / "cheer_power_storage_targetyear_hf4_projected.jl"
RUNNER = ROOT / "storage_runner" / "run_future_correction_one_hf4_projected.jl"
ROUTES = [
    ("scaled_barrier", "__hf5_reduced_scaled_barrier", "hf5_reduced_scaled_barrier"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def projected_gate(status: dict[str, str]) -> list[str]:
    reasons: list[str] = []
    exact = {
        "legacy_reallocation_formulation_version": FORMULATION,
        "legacy_energy_variable_projection_count": "32",
        "algebraic_reduction_version": ALGEBRAIC_REDUCTION,
        "total_omitted_hourly_columns": "152352",
    }
    for key, expected in exact.items():
        actual = status.get(key, "")
        if key.endswith("_count"):
            try:
                ok = int(float(actual)) == int(expected)
            except ValueError:
                ok = False
        else:
            ok = actual == expected
        if not ok:
            reasons.append(f"{key}={actual!r} expected {expected!r}")
    for key in [
        "legacy_national_energy_identity_pass",
        "legacy_zone_caps_encoded_as_variable_bounds",
        "legacy_energy_variable_projection_active",
        "legacy_projected_energy_output_reconstruction",
        "algebraic_reduction_preserves_scientific_inputs",
        "algebraic_reduction_preserves_objective_and_projected_feasible_set",
    ]:
        if not base.truth(status.get(key)):
            reasons.append(f"{key}=false")
    for key in [
        "legacy_national_energy_closure_constraint_emitted",
        "legacy_common_duration_constraints_emitted",
    ]:
        if base.truth(status.get(key)):
            reasons.append(f"{key}=true")
    try:
        residual = abs(float(status.get("legacy_national_energy_identity_residual_mwh", "nan")))
        tolerance = float(status.get("legacy_national_energy_identity_tolerance_mwh", "nan"))
        if not residual <= tolerance:
            reasons.append(f"national energy identity residual {residual} > {tolerance}")
    except ValueError:
        reasons.append("national energy identity residual unavailable")
    return reasons


def run_projected(julia: str, row: dict, profile: str, suffix: str, label: str) -> dict:
    scenario = str(row["scenario"])
    local = base.local_output(scenario, suffix)
    if local.exists():
        import shutil
        shutil.rmtree(local)
    log = base.LOGS / scenario / f"{label}.log"
    cmd = [
        julia, str(RUNNER), "--scenario", scenario,
        "--solver_profile", profile,
        "--cleanup_profile", "stage1_official_release",
        "--solver_output_suffix", suffix,
    ]
    rc, seconds = base.run_cmd(cmd, log)
    outdir, preserved = base.preserve_attempt(scenario, label, suffix)
    status = base.read_one_csv(outdir / "solve_status.csv")
    success, reasons, maxima = base.strict_success(status, rc, preserved, outdir, row)
    extra = projected_gate(status)
    if extra:
        success = False
        reasons.extend(extra)
    return {
        "scenario": scenario, "profile": profile, "suffix": suffix, "attempt_label": label,
        "return_code": rc, "seconds": seconds, "attempt_output_dir": str(outdir.relative_to(ROOT)),
        "log": str(log.relative_to(ROOT)), "status": status, "success": success,
        "failure_reasons": reasons, "chronology_maxima": maxima,
    }


def write_lineage(outdir: Path) -> None:
    status = outdir / "solve_status.csv"
    payload = {
        "schema_version": "v20_hf5_reduced_model_result_lineage_v1",
        "status": "PASS",
        "scenario": SCENARIO,
        "formulation_version": FORMULATION,
        "equivalence_scope": "eliminate 32 exactly determined legacy-energy coordinates plus fixed-zero non-CCS and objective-neutral startup/shutdown hourly coordinates; preserve inputs, objective, projected feasible set and exported schema",
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


def main() -> None:
    # One uninterrupted Barrier trajectory gets the full former 12+24+24 h
    # ladder budget. This changes no coefficient or tolerance and avoids
    # discarding numerical progress between fresh solver processes.
    os.environ["V17_ECONOMIC_BARRIER_TIME_LIMIT_SECONDS"] = "216000"
    os.environ["V17_ECONOMIC_BAR_ITER_LIMIT"] = "500000"
    base.CENTRAL.mkdir(parents=True, exist_ok=True)
    base.ATTEMPTS.mkdir(parents=True, exist_ok=True)
    base.LOGS.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(base.SCEN)
    selected = frame.loc[frame["scenario"].astype(str).eq(SCENARIO)]
    if len(selected) != 1:
        raise SystemExit(f"Expected exactly one {SCENARIO} row; found {len(selected)}")
    row = selected.iloc[0].to_dict()

    existing = base.existing_official_record(row)
    if existing is not None:
        rec = existing
        print(f"{SCENARIO}: existing strict __main retained; no HF5 solve needed.")
    else:
        original = base.run_solver_once
        base.run_solver_once = run_projected
        try:
            rec = base.run_one(sys.argv[1] if len(sys.argv) > 1 else "julia", row, ROUTES)
        finally:
            base.run_solver_once = original
        if rec["publication_strict_success"]:
            write_lineage(base.CENTRAL / f"{SCENARIO}__main")

    merged = pd.DataFrame([rec])
    if base.SUMMARY_CSV.is_file():
        previous = pd.read_csv(base.SUMMARY_CSV)
        merged = pd.concat([previous, merged], ignore_index=True).drop_duplicates("scenario", keep="last")
    merged.to_csv(base.SUMMARY_CSV, index=False)
    base.SUMMARY_JSON.write_text(
        json.dumps(merged.to_dict(orient="records"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not bool(rec["publication_strict_success"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
