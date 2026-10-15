#!/usr/bin/env python3
"""Run the two remaining LDES cases concurrently under per-scenario leases."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time

import pandas as pd

import run_targetyear_batch as batch


ROUTES_BY_SCENARIO = {
    "TY2033_FULL8760_LDES_OBSERVED": batch.HF3_PROJECTED_ROUTES,
    "TY2033_FULL8760_LDES_OPTIMAL": batch.HF4_CONTINUATION_ROUTES,
}


def merge_summary(records: list[dict]) -> None:
    """Merge both records and atomically replace the shared summary files."""
    batch.CENTRAL.mkdir(parents=True, exist_ok=True)
    merged = pd.DataFrame(records)
    if batch.SUMMARY_CSV.is_file():
        previous = pd.read_csv(batch.SUMMARY_CSV)
        merged = pd.concat([previous, merged], ignore_index=True).drop_duplicates(
            subset=["scenario"], keep="last"
        )
    scenario_order = list(pd.read_csv(batch.SCEN)["scenario"].astype(str))
    order = {name: index for index, name in enumerate(scenario_order)}
    if not merged.empty:
        merged["__order"] = merged["scenario"].astype(str).map(order).fillna(10**9)
        merged = merged.sort_values("__order", kind="stable").drop(columns=["__order"]).reset_index(drop=True)
    token = f"{os.getpid()}_{time.time_ns()}"
    csv_temp = batch.CENTRAL / f".V17T2R6_FULL8760_run_summary.{token}.csv.tmp"
    json_temp = batch.CENTRAL / f".V17T2R6_FULL8760_run_summary.{token}.json.tmp"
    merged.to_csv(csv_temp, index=False)
    json_temp.write_text(
        json.dumps(merged.to_dict(orient="records"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(csv_temp, batch.SUMMARY_CSV)
    os.replace(json_temp, batch.SUMMARY_JSON)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--julia", default=os.environ.get("JULIA_EXE", "julia"))
    args = parser.parse_args()

    batch.CENTRAL.mkdir(parents=True, exist_ok=True)
    batch.ATTEMPTS.mkdir(parents=True, exist_ok=True)
    batch.LOGS.mkdir(parents=True, exist_ok=True)
    batch.RUN_LOCKS.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [sys.executable, str(batch.ROOT / "tools" / "audit_targetyear_pair_identity.py")],
        cwd=batch.ROOT,
    )
    registry = pd.read_csv(batch.SCEN)
    rows = {
        str(row["scenario"]): row.to_dict()
        for _, row in registry.iterrows()
        if str(row["scenario"]) in ROUTES_BY_SCENARIO
    }
    if set(rows) != set(ROUTES_BY_SCENARIO):
        raise SystemExit("The two declared LDES scenarios are not present in the registry.")

    print(json.dumps({
        "mode": "V17T2R6R9_HF4P1_safe_parallel_remaining_ldes",
        "max_parallel": 2,
        "solver_threads_per_case": int(os.environ.get("V17_SOLVER_THREADS", "10")),
        "scenarios": list(ROUTES_BY_SCENARIO),
        "scenario_leases": str(batch.RUN_LOCKS.relative_to(batch.ROOT)),
    }, ensure_ascii=False, indent=2))

    records_by_name: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="hf4p1_ldes") as pool:
        futures = {
            pool.submit(batch.run_one, args.julia, rows[name], routes, False): name
            for name, routes in ROUTES_BY_SCENARIO.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                records_by_name[name] = future.result()
            except Exception as exc:
                records_by_name[name] = batch.exception_record(rows[name], exc)
            print(json.dumps(records_by_name[name], ensure_ascii=False, indent=2))

    records = [records_by_name[name] for name in ROUTES_BY_SCENARIO]
    merge_summary(records)
    if not all(record["publication_strict_success"] for record in records):
        raise SystemExit(
            "One or both parallel LDES cases failed the strict gate. Existing strict outputs remain intact; "
            "see batch_logs, sensitivity_outputs/_attempts and failed_diagnostics."
        )
    print("Both remaining LDES cases passed strict publication validation. "
          "The original serial launcher will validate/skip them and perform finalization.")


if __name__ == "__main__":
    main()
