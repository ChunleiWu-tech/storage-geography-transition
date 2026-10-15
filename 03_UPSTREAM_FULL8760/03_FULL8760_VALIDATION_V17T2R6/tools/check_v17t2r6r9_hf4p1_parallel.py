#!/usr/bin/env python3
"""Fail-closed operational audit for the HF4P1 parallel companion."""
from __future__ import annotations

from pathlib import Path
import ast
import hashlib
import json


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_targetyear_batch.py"
COMPANION = ROOT / "tools" / "run_hf4_remaining_ldes_parallel.py"
LAUNCHER = ROOT / "RUN_V17T2R6R9_HF4P1_8760_REMAINING_LDES_2X10.bat"
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"
HELPER = ROOT / "base_model_v39" / "full8760_hf4_objective_continuation.jl"
MANIFEST = ROOT / "HF4P1_PATCH_MANIFEST_SHA256.json"
OUT = ROOT / "audits" / "V17T2R6R9_HF4P1_PARALLEL_AUDIT.json"
EXPECTED_MODEL_SHA256 = "6170c01dbecad8169203ff1d830ef17aa99616e32a21d85ae2c6b2d05b899391"
EXPECTED_HELPER_SHA256 = "f8dad259f7793b9e21cfc9c700173b3453f6b6c817d4485057e33ecd183c77d7"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: object) -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    runner = RUNNER.read_text(encoding="utf-8")
    companion = COMPANION.read_text(encoding="utf-8")
    launcher = LAUNCHER.read_text(encoding="utf-8")
    syntax_errors: list[str] = []
    for path in (RUNNER, COMPANION, Path(__file__)):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_errors.append(f"{path.name}: {exc}")
    add("python_syntax", not syntax_errors, syntax_errors)

    add(
        "scientific_julia_sources_byte_unchanged",
        sha256(MODEL) == EXPECTED_MODEL_SHA256 and sha256(HELPER) == EXPECTED_HELPER_SHA256,
        {"model": sha256(MODEL), "helper": sha256(HELPER)},
    )

    lease_tokens = [
        'RUN_LOCKS = ROOT / "run_locks"',
        "def acquire_scenario_lease(",
        "lease.mkdir()",
        "Scenario {scenario} is active in another coordinator; waiting for strict promotion.",
        "existing = existing_official_record(row)",
        "def release_scenario_lease(",
        "Refusing to release a scenario lease owned by another process",
        "finally:\n        release_scenario_lease(lease)",
    ]
    missing_lease = [token for token in lease_tokens if token not in runner]
    add("atomic_per_scenario_lease_and_wait_contract", not missing_lease, missing_lease)

    companion_tokens = [
        '"TY2033_FULL8760_LDES_OBSERVED": batch.HF3_PROJECTED_ROUTES',
        '"TY2033_FULL8760_LDES_OPTIMAL": batch.HF4_CONTINUATION_ROUTES',
        "ThreadPoolExecutor(max_workers=2",
        "pool.submit(batch.run_one",
        "merge_summary(records)",
        "os.replace(csv_temp, batch.SUMMARY_CSV)",
        "os.replace(json_temp, batch.SUMMARY_JSON)",
        'all(record["publication_strict_success"] for record in records)',
    ]
    missing_companion = [token for token in companion_tokens if token not in companion]
    add("heterogeneous_two_case_parallel_coordinator", not missing_companion, missing_companion)

    forbidden_companion = [
        "force_rerun=True",
        "--force-rerun",
        "--clean-central",
        "shutil.rmtree(batch.CENTRAL",
        "TY2033_FULL8760_OPTIMAL\":",
    ]
    forbidden_hits = [token for token in forbidden_companion if token in companion]
    add("current_optimal_case_not_touched_and_no_clean", not forbidden_hits, forbidden_hits)

    launcher_required = [
        'set "V17_SOLVER_THREADS=10"',
        'set "V17T2R6_MAX_PARALLEL=2"',
        'set "V17T2R6_SCENARIO_LOCK_WAIT_SECONDS=604800"',
        '"tools\\run_hf4_remaining_ldes_parallel.py"',
        "Keep the original FULL8760_OPTIMAL terminal running.",
    ]
    launcher_forbidden = ["Stop-Process", "taskkill", "--force-rerun", "--clean-central"]
    missing_launcher = [token for token in launcher_required if token not in launcher]
    forbidden_launcher_hits = [token for token in launcher_forbidden if token in launcher]
    add(
        "parallel_launcher_preserves_current_process",
        not missing_launcher and not forbidden_launcher_hits,
        {"missing": missing_launcher, "forbidden": forbidden_launcher_hits},
    )

    manifest_errors: list[str] = []
    if not MANIFEST.is_file():
        manifest_errors.append("HF4P1 patch manifest missing")
    else:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for item in manifest.get("files", []):
            path = ROOT / str(item["path"])
            if not path.is_file():
                manifest_errors.append(f"missing {item['path']}")
            elif path.stat().st_size != int(item["bytes"]):
                manifest_errors.append(f"size {item['path']}")
            elif sha256(path) != str(item["sha256"]):
                manifest_errors.append(f"sha256 {item['path']}")
    add("hf4p1_patch_files_match_manifest", not manifest_errors, manifest_errors)

    result = {
        "version": "V17T2R6R9_HF4P1_SAFE_PARALLEL_REMAINING_LDES",
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "scope": "operational concurrency only; scientific Julia sources and exact solver routes unchanged",
        "scientific_change": False,
        "max_parallel_new_cases": 2,
        "solver_threads_per_new_case": 10,
        "checks": checks,
        "failed": [item["check"] for item in checks if not item["pass"]],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
