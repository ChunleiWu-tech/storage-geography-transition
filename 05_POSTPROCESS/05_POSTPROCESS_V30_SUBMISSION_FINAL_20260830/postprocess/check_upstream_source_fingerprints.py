#!/usr/bin/env python3
"""Verify that both upstream bundles use the same publication source contract.

The check is intentionally source-only by default. With ``--require-results`` it
also requires every declared scenario to have result lineage generated from the
current source fingerprint. The latter must fail before the user reruns Julia–
Gurobi; that failure is a release protection, not a package defect.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
from typing import Any


def _run_gate(root: Path, stage: str) -> dict[str, Any]:
    gate = root / "tools" / "publication_source_gate.py"
    if not gate.is_file():
        return {
            "passed": False,
            "return_code": 99,
            "gate": str(gate),
            "stdout": "",
            "stderr": "gate script is missing",
        }
    proc = subprocess.run(
        [sys.executable, str(gate), "--stage", stage],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return {
        "passed": proc.returncode == 0,
        "return_code": proc.returncode,
        "gate": str(gate),
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-12000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("main_root")
    parser.add_argument("sensitivity_root")
    parser.add_argument("--require-results", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    roots = [Path(args.main_root).resolve(), Path(args.sensitivity_root).resolve()]
    labels = ["main", "sensitivity"]
    fingerprints: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    stage = "results" if args.require_results else "source"

    for label, root in zip(labels, roots):
        fp_path = root / "audits" / "PUBLICATION_SOURCE_FINGERPRINT.json"
        exists = fp_path.is_file()
        checks.append(
            {
                "check": f"{label}_source_fingerprint_exists",
                "passed": exists,
                "detail": str(fp_path),
            }
        )
        if exists:
            try:
                fingerprints.append(json.loads(fp_path.read_text(encoding="utf-8")))
            except Exception as exc:  # pragma: no cover - defensive release check
                checks.append(
                    {
                        "check": f"{label}_source_fingerprint_is_valid_json",
                        "passed": False,
                        "detail": repr(exc),
                    }
                )

        gate_result = _run_gate(root, stage)
        checks.append(
            {
                "check": f"{label}_{stage}_gate",
                "passed": gate_result["passed"],
                "detail": gate_result,
            }
        )

    if len(fingerprints) == 2:
        checks.append(
            {
                "check": "same_data_version",
                "passed": fingerprints[0].get("data_version")
                == fingerprints[1].get("data_version"),
                "detail": [
                    fingerprints[0].get("data_version"),
                    fingerprints[1].get("data_version"),
                ],
            }
        )
        checks.append(
            {
                "check": "same_source_file_hashes",
                "passed": fingerprints[0].get("source_files")
                == fingerprints[1].get("source_files"),
                "detail": "canonical source-file maps compared",
            }
        )

    passed = all(item["passed"] for item in checks)
    if passed:
        status = "PASS"
    elif args.require_results:
        status = "FAIL_RERUN_REQUIRED"
    else:
        status = "FAIL"

    report = {
        "status": status,
        "mode": stage,
        "interpretation": (
            "Source lineage is synchronized and ready for post-processing."
            if passed and not args.require_results
            else (
                "Current-source result lineage is incomplete. Run all 16 main and "
                "8 sensitivity scenarios before post-processing."
                if args.require_results and not passed
                else "Source lineage is not synchronized."
            )
        ),
        "checks": checks,
    }
    output_name = (
        "UPSTREAM_RESULT_LINEAGE_AUDIT.json"
        if args.require_results
        else "UPSTREAM_SOURCE_FINGERPRINT_AUDIT.json"
    )
    output = Path(args.output).expanduser().resolve() if args.output else Path(__file__).resolve().parents[1] / output_name
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
