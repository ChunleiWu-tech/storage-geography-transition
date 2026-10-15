#!/usr/bin/env python3
"""Resume both full-8760 OPTIMAL members through the HF5 no-crossover bridge.

The coordinator is deliberately limited to the two optimized members.  It
never starts or changes either OBSERVED member.  Scenario leases make it safe
to launch while a pre-patch LDES OPTIMAL process remains alive: that task waits
without owning or deleting the live lease, then starts one distinct HF5 attempt
only after the old worker has exited and released it.
"""
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


TARGETS = (
    "TY2033_FULL8760_OPTIMAL",
    "TY2033_FULL8760_LDES_OPTIMAL",
)


def merge_summary(records: list[dict]) -> None:
    """Publish the two coordinator records atomically after all workers finish."""
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
    csv_tmp = batch.CENTRAL / f".V17T2R6_HF5_optimized_pair.{token}.csv.tmp"
    json_tmp = batch.CENTRAL / f".V17T2R6_HF5_optimized_pair.{token}.json.tmp"
    merged.to_csv(csv_tmp, index=False)
    json_tmp.write_text(json.dumps(merged.to_dict(orient="records"), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(csv_tmp, batch.SUMMARY_CSV)
    os.replace(json_tmp, batch.SUMMARY_JSON)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--julia", default=os.environ.get("JULIA_EXE", "julia"))
    args = parser.parse_args()

    configured_threads = int(os.environ.get("V17_SOLVER_THREADS", "15"))
    if configured_threads != 15:
        raise SystemExit("HF5 optimized-pair recovery requires V17_SOLVER_THREADS=15 exactly.")
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
        raise SystemExit("One or more declared HF5 optimized scenarios are missing from the registry.")

    print(json.dumps({
        "mode": "V17T2R6R10_HF5_optimized_pair_auto_resume",
        "scenarios": list(TARGETS),
        "max_new_hf5_workers": 2,
        "solver_threads_per_new_case": configured_threads,
        "scientific_change": False,
        "force_rerun": False,
        "scenario_leases": str(batch.RUN_LOCKS.relative_to(batch.ROOT)),
        "ldes_observed_changed": False,
        "lease_behavior": "a live pre-patch LDES_OPTIMAL lease is waited on, never removed",
    }, ensure_ascii=False, indent=2))

    records_by_name: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="hf5_optimized_pair") as pool:
        futures = {
            pool.submit(batch.run_one, args.julia, rows[name], batch.HF5_SIMPLEX_BRIDGE_ROUTES, False): name
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
        raise SystemExit(
            "One or more HF5 optimized cases failed strict publication validation. Existing promoted results and "
            "old HF4 diagnostics remain intact; see batch_logs, sensitivity_outputs/_attempts and failed_diagnostics."
        )
    print("Both HF5 optimized full-8760 cases passed strict publication validation.")


if __name__ == "__main__":
    main()
