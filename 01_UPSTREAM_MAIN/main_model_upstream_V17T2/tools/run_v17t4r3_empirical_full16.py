#!/usr/bin/env python3
"""Run the 16 official Storage V17 scenarios using the empirically validated route policy.

Scientific model/input semantics are unchanged. Solver routing only:
- 14 standard scenarios: existing audited scaled-Barrier primary, then the existing
  controlled concurrent/dual fallbacks if the primary is uncertified.
- SL10_CARBON_TIGHT_OBSERVED and SL13_COST_LOW_OPTIMAL: standard scaled Barrier,
  Crossover=0, 10 threads, up to 6 h. This is the route that produced the final
  strict solutions in the completed Windows run and avoids repeating exhausted
  hard/crossover-heavy routes.

Every attempt starts in a fresh Julia process. Only solver-native OPTIMAL results
that pass the existing strict physical/export/publication gates are promoted.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import sys
import time
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_official_batch as batch  # noqa: E402

HARD_EMPIRICAL = {
    "SL10_CARBON_TIGHT_OBSERVED",
    "SL13_COST_LOW_OPTIMAL",
}
REPORT = ROOT / "audits" / "V17T4R3_EMPIRICAL_ROUTE_RUN.json"


def _existing_strict_row(scenario: str) -> dict[str, Any] | None:
    outdir = batch.OUTROOT / f"{scenario}__main"
    status = batch.read_status(str(outdir))
    if not batch.strict_success(status, 0, outdir.is_dir(), str(outdir)):
        return None
    row: dict[str, Any] = {
        "scenario": scenario,
        "return_code": 0,
        "seconds": 0.0,
        "central_output_dir": str(outdir),
        "centralized": True,
        "stage1_attempts_used": "preexisting_strict_output",
        "attempt_output_dirs": str(outdir),
        "safe_retry_used": False,
        "fallback_stop_reason": "preexisting_strict_success_skipped",
        "successful_attempt": "preexisting_strict_output",
        "publication_strict_success": True,
        "result_tier": "official_stage1_economic_optimum",
        "failed_diagnostic_archive": "",
    }
    solver_output_scenario = status.get("scenario", "")
    row.update(status)
    row["solver_output_scenario"] = solver_output_scenario
    row["scenario"] = scenario
    row["publication_strict_success"] = True
    return row


def _set_or_restore(name: str, old: str | None) -> None:
    if old is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = old


def _run_empirical_hard(scenario: str, julia: str, seconds: int) -> dict[str, Any]:
    # The completed run established standard scaled Barrier / no crossover as the
    # successful route for both hard cases. Keep the LP, tolerances and gates fixed.
    env_names = [
        "V17_ECONOMIC_BARRIER_TIME_LIMIT_SECONDS",
        "V17_ECONOMIC_FALLBACK_TIME_LIMIT_SECONDS",
        "V17_ECONOMIC_BAR_ITER_LIMIT",
        "V17_SOLVER_THREADS",
    ]
    old = {k: os.environ.get(k) for k in env_names}
    try:
        os.environ["V17_ECONOMIC_BARRIER_TIME_LIMIT_SECONDS"] = str(seconds)
        os.environ["V17_ECONOMIC_FALLBACK_TIME_LIMIT_SECONDS"] = str(seconds)
        os.environ["V17_ECONOMIC_BAR_ITER_LIMIT"] = "5000"
        os.environ.setdefault("V17_SOLVER_THREADS", "10")
        label = "v17t4r3_empirical_scaled_barrier_nocrossover"
        result = batch.run_solver_once(
            scenario,
            julia,
            "scaled_barrier",
            "__stage1_official",
            label,
            batch.LOGDIR / f"{scenario}__v17t4r3_scaled_barrier.log",
        )
    finally:
        for k, v in old.items():
            _set_or_restore(k, v)

    status = result["status"]
    assert isinstance(status, dict)
    archive = "" if bool(result["success"]) else batch._archive_failed_diagnostics(scenario)
    diagnostic_warning = batch._true(status.get("stage1_external_diagnostic_warning"))
    result_tier = (
        "official_stage1_economic_optimum_with_nonblocking_certificate_warning"
        if result["success"] and diagnostic_warning
        else "official_stage1_economic_optimum" if result["success"]
        else "failed_publication_gate"
    )
    row: dict[str, Any] = {
        "scenario": scenario,
        "return_code": result["return_code"],
        "seconds": round(float(result["seconds"]), 2),
        "central_output_dir": result["central_output_dir"],
        "centralized": result["centralized"],
        "stage1_attempts_used": label,
        "attempt_output_dirs": result.get("attempt_output_dir", ""),
        "safe_retry_used": False,
        "fallback_stop_reason": (
            "empirically_validated_scaled_barrier_success"
            if result["success"] else "empirically_validated_scaled_barrier_uncertified"
        ),
        "successful_attempt": label if result["success"] else "",
        "publication_strict_success": bool(result["success"]),
        "result_tier": result_tier,
        "failed_diagnostic_archive": archive,
        "v17t4r3_empirical_route": True,
        "v17t4r3_model_or_input_change": False,
    }
    solver_output_scenario = status.get("scenario", "")
    row.update(status)
    row["solver_output_scenario"] = solver_output_scenario
    row["scenario"] = scenario
    row["publication_strict_success"] = bool(result["success"])
    return row


def _official_scenarios() -> list[str]:
    frame = pd.read_csv(batch.SCEN)
    mask = frame["v17_official_unique"].astype(str).str.lower().isin({"true", "1", "yes"})
    scenarios = frame.loc[mask, "scenario"].astype(str).tolist()
    if len(scenarios) != 16 or len(set(scenarios)) != 16:
        raise SystemExit(f"Expected exactly 16 official scenarios; got {len(scenarios)}")
    return scenarios


def _write_summary(rows: list[dict[str, Any]]) -> None:
    batch.SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values("scenario")
    frame.to_csv(batch.SUMMARY, index=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--julia", default=os.environ.get("JULIA_EXE", "julia"))
    ap.add_argument("--hard-route-seconds", type=int, default=21600)
    ap.add_argument("--force-rerun", action="store_true")
    ap.add_argument("--continue-after-failure", action="store_true")
    args = ap.parse_args()
    if args.hard_route_seconds < 7200:
        raise SystemExit("Refusing hard-pair route time limit below 7200 seconds.")

    os.environ.setdefault("V17_SOLVER_THREADS", "10")
    batch.LOGDIR.mkdir(parents=True, exist_ok=True)
    batch.OUTROOT.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    rows: list[dict[str, Any]] = []
    route_record: list[dict[str, Any]] = []
    for scenario in _official_scenarios():
        if not args.force_rerun:
            existing = _existing_strict_row(scenario)
            if existing is not None:
                rows.append(existing)
                route_record.append({"scenario": scenario, "route": "preexisting_strict_output", "success": True})
                _write_summary(rows)
                print(f"[{scenario}] strict existing output reused; no solve performed")
                continue

        if scenario in HARD_EMPIRICAL:
            row = _run_empirical_hard(scenario, args.julia, args.hard_route_seconds)
            route = "scaled_barrier_no_crossover_empirically_validated"
        else:
            row = batch.run_one(scenario, args.julia, auto_safe_retry=True)
            route = "standard_scaled_barrier_then_controlled_fallback_if_needed"
        rows.append(row)
        ok = bool(row.get("publication_strict_success"))
        route_record.append({"scenario": scenario, "route": route, "success": ok})
        _write_summary(rows)
        print(
            f"[{scenario}] success={ok} stage1={row.get('stage1_termination_status','')} "
            f"profile={row.get('solver_profile','')}"
        )
        if not ok and not args.continue_after_failure:
            break

    frame = pd.DataFrame(rows)
    failures = frame.loc[~frame["publication_strict_success"].astype(bool)] if not frame.empty else frame
    complete = len(frame) == 16 and frame["scenario"].astype(str).nunique() == 16
    success = complete and failures.empty
    report = {
        "version": "V17T4R3_STANDALONE_EMPIRICAL_ROUTE",
        "science_changed": False,
        "model_or_input_changed": False,
        "solver_threads": int(os.environ.get("V17_SOLVER_THREADS", "10")),
        "hard_pair": sorted(HARD_EMPIRICAL),
        "hard_pair_route": "scaled_barrier_method2_crossover0",
        "hard_pair_time_limit_seconds": args.hard_route_seconds,
        "standard_case_route": "existing V17 scaled_barrier primary with controlled fallbacks",
        "scenario_rows_written": len(frame),
        "complete_16": complete,
        "all_strict_success": success,
        "elapsed_seconds": round(time.time() - started, 2),
        "routes": route_record,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not success:
        print("V17T4R3 robust 16-case run is not 16/16 strict success. See summary and failed_diagnostics.")
        raise SystemExit(1)
    print("V17T4R3 robust 16-case solver stage PASSED: 16/16 strict success.")
    print("Summary:", batch.SUMMARY)


if __name__ == "__main__":
    main()
