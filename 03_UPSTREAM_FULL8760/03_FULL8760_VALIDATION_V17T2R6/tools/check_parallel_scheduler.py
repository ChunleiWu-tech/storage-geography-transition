#!/usr/bin/env python3
"""No-solver regression test for the R7 pair-preserving 2x10 scheduler."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import threading
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_targetyear_batch.py"
SCEN = ROOT / "storage_runner" / "scenarios_targetyear_linked.csv"
OUT = ROOT / "audits" / "V17T2R6R7_PARALLEL_SCHEDULER_AUDIT.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    spec = importlib.util.spec_from_file_location("v17t2r6_batch_r7_test", RUNNER)
    if spec is None or spec.loader is None:
        raise SystemExit("Could not load run_targetyear_batch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    rows = [r.to_dict() for _, r in pd.read_csv(SCEN).iterrows()]
    waves = mod.selected_waves(rows, 2)
    wave_names = [[str(row["scenario"]) for row in wave] for wave in waves]
    expected = [
        ["TY2033_FULL8760_OBSERVED", "TY2033_FULL8760_OPTIMAL"],
        ["TY2033_FULL8760_LDES_OBSERVED", "TY2033_FULL8760_LDES_OPTIMAL"],
    ]

    lock = threading.Lock()
    active = 0
    max_active = 0
    events: list[dict[str, object]] = []
    original_run_one = mod.run_one

    def fake_run_one(julia, row, routes, force_rerun=False):
        nonlocal active, max_active
        name = str(row["scenario"])
        with lock:
            active += 1
            max_active = max(max_active, active)
            events.append({"event": "start", "scenario": name, "t": time.perf_counter()})
        time.sleep(0.08)
        with lock:
            events.append({"event": "end", "scenario": name, "t": time.perf_counter()})
            active -= 1
        return {
            "scenario": name,
            "pair_id": row["pair_id"],
            "target_year": int(row["target_year"]),
            "context": row["context"],
            "publication_strict_success": True,
        }

    mod.run_one = fake_run_one
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            records = mod.run_selected_rows(
                "julia", rows, mod.ROUTES,
                force_rerun=False,
                continue_after_failure=True,
                max_parallel=2,
            )
    finally:
        mod.run_one = original_run_one

    record_order = [str(r["scenario"]) for r in records]
    start = {str(e["scenario"]): float(e["t"]) for e in events if e["event"] == "start"}
    end = {str(e["scenario"]): float(e["t"]) for e in events if e["event"] == "end"}
    wave_barrier_ok = (
        min(start[name] for name in expected[1]) >= max(end[name] for name in expected[0])
    )

    cap_rejects_three = False
    try:
        mod.selected_waves(rows, 3)
    except ValueError:
        cap_rejects_three = True

    checks = {
        "wave_membership_exact": wave_names == expected,
        "maximum_simultaneous_workers_exactly_two": max_active == 2,
        "wave2_waits_for_wave1_completion": wave_barrier_ok,
        "result_order_deterministic": record_order == [name for wave in expected for name in wave],
        "parallel_cap_rejects_three": cap_rejects_three,
    }
    payload = {
        "version": "V17T2R6R7_FULL8760",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "runner_sha256": sha256(RUNNER),
        "checks": checks,
        "wave_names": wave_names,
        "max_active_observed": max_active,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
