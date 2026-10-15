#!/usr/bin/env python3
"""Run the three unresolved full-8760 cases independently through HF7."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import json
import os
import subprocess
import sys
import time

import pandas as pd

import run_targetyear_batch as batch


TARGETS = (
    "TY2033_FULL8760_OPTIMAL",
    "TY2033_FULL8760_LDES_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL",
)


def merge_summary(records: list[dict]) -> None:
    batch.CENTRAL.mkdir(parents=True, exist_ok=True)
    merged = pd.DataFrame(records)
    if batch.SUMMARY_CSV.is_file():
        previous = pd.read_csv(batch.SUMMARY_CSV)
        merged = pd.concat([previous, merged], ignore_index=True).drop_duplicates(
            subset=["scenario"], keep="last"
        )
    order = {name: index for index, name in enumerate(pd.read_csv(batch.SCEN)["scenario"].astype(str))}
    if not merged.empty:
        merged["__order"] = merged["scenario"].astype(str).map(order).fillna(10**9)
        merged = merged.sort_values("__order", kind="stable").drop(columns=["__order"]).reset_index(drop=True)
    token = f"{os.getpid()}_{time.time_ns()}"
    csv_tmp = batch.CENTRAL / f".V17T2R6R12_HF7_unresolved_three.{token}.csv.tmp"
    json_tmp = batch.CENTRAL / f".V17T2R6R12_HF7_unresolved_three.{token}.json.tmp"
    merged.to_csv(csv_tmp, index=False)
    json_tmp.write_text(json.dumps(merged.to_dict(orient="records"), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(csv_tmp, batch.SUMMARY_CSV)
    os.replace(json_tmp, batch.SUMMARY_JSON)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--julia", default=os.environ.get("JULIA_EXE", "julia"))
    args = parser.parse_args()
    threads = int(os.environ.get("V17_SOLVER_THREADS", "15"))
    if threads != 15:
        raise SystemExit("HF7 three-case recovery requires V17_SOLVER_THREADS=15 exactly.")
    for directory in (batch.CENTRAL, batch.ATTEMPTS, batch.LOGS, batch.RUN_LOCKS):
        directory.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [sys.executable, str(batch.ROOT / "tools" / "audit_targetyear_pair_identity.py")], cwd=batch.ROOT
    )
    registry = pd.read_csv(batch.SCEN)
    rows = {
        str(row["scenario"]): row.to_dict()
        for _, row in registry.iterrows()
        if str(row["scenario"]) in TARGETS
    }
    if set(rows) != set(TARGETS):
        raise SystemExit("One or more HF7 scenarios are missing from the registry.")
    print(json.dumps({
        "mode": "V17T2R6R12_HF7_restricted_face_three_case_parallel",
        "scenarios": list(TARGETS),
        "max_parallel": 3,
        "solver_threads_per_case": threads,
        "total_solver_threads": 3 * threads,
        "scientific_change": False,
        "force_rerun": False,
        "scenario_isolation": "one Julia process, one lease, one __07 attempt directory per case",
        "lease_behavior": "wait only; never delete or steal an active lease",
        "preexisting_strict_results": "skip without overwrite",
    }, ensure_ascii=False, indent=2))

    records_by_name: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="hf7_full8760") as pool:
        futures = {
            pool.submit(batch.run_one, args.julia, rows[name], batch.HF7_RESTRICTED_FACE_ROUTES, False): name
            for name in TARGETS
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                records_by_name[name] = future.result()
            except Exception as exc:
                records_by_name[name] = batch.exception_record(rows[name], exc)
            print(json.dumps(records_by_name[name], ensure_ascii=False, indent=2))

    records = [records_by_name[name] for name in TARGETS]
    merge_summary(records)
    if not all(record["publication_strict_success"] for record in records):
        raise SystemExit("At least one HF7 case failed strict publication validation; prior promoted outputs remain unchanged.")
    print("All three HF7 full-8760 cases passed strict publication validation.")


if __name__ == "__main__":
    main()
