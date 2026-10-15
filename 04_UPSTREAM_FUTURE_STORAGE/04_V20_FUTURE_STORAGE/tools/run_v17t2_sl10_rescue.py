#!/usr/bin/env python3
"""Rescue only SL10 in an existing V17T1 15/16 result tree.

The V17T1 SL10 homogeneous-barrier attempt reached a solver-reported optimal
barrier point before crossover, but crossover exhausted the time limit and
left no publishable result.  This script reruns exactly the original SL10 LP
with the same hard homogeneous-barrier numerical settings and Crossover=0,
then atomically replaces only the SL10 summary row after every strict release
gate passes.  The other fifteen official outputs are hashed before and after.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_official_batch as batch  # noqa: E402

SCENARIO = "SL10_CARBON_TIGHT_OBSERVED"
PROFILE = "hard_homogeneous_barrier_no_crossover"
SUFFIX = "__v17t2_homogeneous_barrier_nocrossover_official"
ATTEMPT = "04_v17t2_homogeneous_barrier_nocrossover_official"
LOG = ROOT / "batch_logs" / f"{SCENARIO}__v17t2_homogeneous_barrier_nocrossover.log"
REPORT = ROOT / "audits" / "V17T2_SL10_RESCUE_RUN.json"
SUMMARY_BACKUP = ROOT / "storage_runner" / "storage_batch_run_summary_before_V17T2_SL10_rescue.csv"
TRUE = {"true", "1", "yes"}


def _bool(v: object) -> bool:
    return str(v).strip().lower() in TRUE


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _tree_digest(path: Path) -> str:
    if not path.is_dir():
        raise FileNotFoundError(path)
    h = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = item.relative_to(path).as_posix().encode("utf-8")
        h.update(len(rel).to_bytes(8, "little"))
        h.update(rel)
        digest = bytes.fromhex(_sha256(item))
        h.update(digest)
    return h.hexdigest()


def _official_scenarios() -> list[str]:
    df = pd.read_csv(batch.SCEN)
    mask = df["v17_official_unique"].astype(str).str.lower().isin(TRUE)
    return list(df.loc[mask, "scenario"].astype(str))


def _read_existing_summary() -> pd.DataFrame:
    if not batch.SUMMARY.exists():
        raise SystemExit(f"Missing existing batch summary: {batch.SUMMARY}")
    frame = pd.read_csv(batch.SUMMARY)
    if "scenario" not in frame.columns or "publication_strict_success" not in frame.columns:
        raise SystemExit("Existing batch summary lacks required columns.")
    official = _official_scenarios()
    if len(frame) != 16 or frame["scenario"].astype(str).nunique() != 16:
        raise SystemExit("V17T2 rescue requires the completed 16-row V17T1 batch summary.")
    if set(frame["scenario"].astype(str)) != set(official):
        raise SystemExit("Existing summary scenario set does not match the 16 official scenarios.")
    failed = frame.loc[~frame["publication_strict_success"].map(_bool), "scenario"].astype(str).tolist()
    if failed != [SCENARIO]:
        raise SystemExit(f"V17T2 rescue requires SL10 to be the sole failed scenario; found {failed}")
    return frame


def _verify_reference_log() -> dict[str, object]:
    candidates = [
        ROOT / "batch_logs" / f"{SCENARIO}__hard_homogeneous_barrier_retry.log",
        ROOT / "batch_logs" / f"{SCENARIO}.log",
    ]
    selected = next((p for p in candidates if p.exists()), None)
    if selected is None:
        raise SystemExit("Missing V17T1 SL10 homogeneous-barrier diagnostic log.")
    text = selected.read_text(encoding="utf-8", errors="replace")
    barrier_optimal = "Barrier solved model" in text and "Optimal objective" in text
    crossover_started = "Crossover log..." in text
    timed_out = "Time limit reached" in text and "stage1_termination_status = TIME_LIMIT" in text
    if not (barrier_optimal and crossover_started and timed_out):
        raise SystemExit(
            "The supplied SL10 log does not show the required evidence: "
            "barrier optimality followed by crossover-only time-limit failure."
        )
    return {
        "path": str(selected),
        "barrier_optimal_before_crossover": barrier_optimal,
        "crossover_started": crossover_started,
        "final_time_limit": timed_out,
    }


def _reference_hashes(summary: pd.DataFrame) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for scenario in _official_scenarios():
        if scenario == SCENARIO:
            continue
        out = batch.OUTROOT / f"{scenario}__main"
        if not out.is_dir():
            raise SystemExit(f"Missing existing official output: {out}")
        status = batch.read_status(str(out))
        if not batch.stage1_certified(status) or not _bool(status.get("strict_physical_audit_pass")):
            raise SystemExit(f"Existing output is not a certified reference result: {scenario}")
        hashes[scenario] = _tree_digest(out)
    if len(hashes) != 15:
        raise SystemExit(f"Expected 15 protected reference outputs, found {len(hashes)}")
    return hashes


def _make_row(old_row: pd.Series, result: dict[str, object]) -> dict[str, object]:
    status = result["status"]
    assert isinstance(status, dict)
    warning = _bool(status.get("stage1_external_diagnostic_warning"))
    prior_attempts = str(old_row.get("stage1_attempts_used", "")).strip(";")
    prior_dirs = str(old_row.get("attempt_output_dirs", "")).strip(";")
    row: dict[str, object] = {
        "scenario": SCENARIO,
        "return_code": result["return_code"],
        "seconds": round(float(old_row.get("seconds", 0.0)) + float(result["seconds"]), 2),
        "central_output_dir": result["central_output_dir"],
        "centralized": result["centralized"],
        "stage1_attempts_used": ";".join(x for x in [prior_attempts, ATTEMPT] if x),
        "attempt_output_dirs": ";".join(x for x in [prior_dirs, str(result["attempt_output_dir"])] if x),
        "safe_retry_used": True,
        "fallback_stop_reason": "v17t2_homogeneous_barrier_no_crossover_success_after_crossover_stall",
        "successful_attempt": ATTEMPT,
        "publication_strict_success": True,
        "result_tier": (
            "official_stage1_economic_optimum_with_nonblocking_certificate_warning"
            if warning else "official_stage1_economic_optimum"
        ),
        "failed_diagnostic_archive": "",
        "v17t2_prior_failed_diagnostic_archive": old_row.get("failed_diagnostic_archive", ""),
        "v17t2_rescue_route": PROFILE,
        "v17t2_rescue_reason": "barrier_optimal_before_crossover_then_crossover_time_limit",
    }
    row.update(status)
    row["solver_output_scenario"] = status.get("scenario", "")
    row["scenario"] = SCENARIO
    row["publication_strict_success"] = True
    row["result_tier"] = (
        "official_stage1_economic_optimum_with_nonblocking_certificate_warning"
        if warning else "official_stage1_economic_optimum"
    )
    return row


def _write_summary_atomically(frame: pd.DataFrame) -> None:
    tmp = batch.SUMMARY.with_suffix(".V17T2.tmp.csv")
    frame.to_csv(tmp, index=False)
    os.replace(tmp, batch.SUMMARY)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--julia", default=os.environ.get("JULIA_EXE", "julia"))
    args = parser.parse_args()

    started = time.time()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    batch.LOGDIR.mkdir(parents=True, exist_ok=True)
    batch.OUTROOT.mkdir(parents=True, exist_ok=True)

    summary = _read_existing_summary()
    reference_log = _verify_reference_log()
    before_hashes = _reference_hashes(summary)
    shutil.copy2(batch.SUMMARY, SUMMARY_BACKUP)

    result = batch.run_solver_once(
        SCENARIO,
        args.julia,
        PROFILE,
        SUFFIX,
        ATTEMPT,
        LOG,
    )
    status = result["status"]
    success = bool(result["success"])

    report: dict[str, object] = {
        "version": "V17T2",
        "scenario": SCENARIO,
        "route": PROFILE,
        "reference_log_evidence": reference_log,
        "protected_reference_count": len(before_hashes),
        "solver_result": {
            "success": success,
            "return_code": result["return_code"],
            "seconds": result["seconds"],
            "attempt_output_dir": result["attempt_output_dir"],
            "central_output_dir": result["central_output_dir"],
            "stage1_termination_status": status.get("stage1_termination_status") if isinstance(status, dict) else None,
            "stage1_primal_status": status.get("stage1_primal_status") if isinstance(status, dict) else None,
            "stage1_dual_status": status.get("stage1_dual_status") if isinstance(status, dict) else None,
            "solver_profile": status.get("solver_profile") if isinstance(status, dict) else None,
            "solver_method": status.get("solver_method") if isinstance(status, dict) else None,
            "solver_crossover": status.get("solver_crossover") if isinstance(status, dict) else None,
            "solver_bar_homogeneous": status.get("solver_bar_homogeneous") if isinstance(status, dict) else None,
            "stage1_barrier_iterations": status.get("stage1_barrier_iterations") if isinstance(status, dict) else None,
            "stage1_simplex_iterations": status.get("stage1_simplex_iterations") if isinstance(status, dict) else None,
            "proof_source": status.get("stage1_economic_optimality_proof_source") if isinstance(status, dict) else None,
        },
        "summary_replaced": False,
        "protected_outputs_unchanged": False,
        "elapsed_seconds": round(time.time() - started, 2),
    }

    if not success:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("V17T2 SL10 RESCUE FAILED strict gates. Existing 15-result summary was not changed.")
        print("See:", LOG)
        raise SystemExit(1)

    old_sl10 = summary.loc[summary["scenario"].astype(str).eq(SCENARIO)].iloc[0]
    new_row = _make_row(old_sl10, result)
    rows: list[dict[str, object]] = []
    for _, old in summary.iterrows():
        if str(old["scenario"]) == SCENARIO:
            rows.append(new_row)
        else:
            rows.append(old.to_dict())
    merged = pd.DataFrame(rows)
    if len(merged) != 16 or merged["scenario"].astype(str).nunique() != 16:
        raise SystemExit("Internal V17T2 merge error: scenario cardinality changed.")
    if not merged["publication_strict_success"].map(_bool).all():
        raise SystemExit("Internal V17T2 merge error: not all 16 rows are strict successes.")

    after_hashes = _reference_hashes(merged)
    unchanged = before_hashes == after_hashes
    if not unchanged:
        raise SystemExit("Protected non-SL10 output digest changed; summary not replaced.")

    _write_summary_atomically(merged)
    report["summary_replaced"] = True
    report["protected_outputs_unchanged"] = True
    report["protected_output_digests"] = before_hashes
    report["elapsed_seconds"] = round(time.time() - started, 2)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("V17T2 SL10 RESCUE PASSED.")
    print("SL10 strict OPTIMAL result:", batch.OUTROOT / f"{SCENARIO}__main")
    print("Merged 16/16 summary:", batch.SUMMARY)
    print("The other fifteen official output directories are byte-identical.")


if __name__ == "__main__":
    main()
