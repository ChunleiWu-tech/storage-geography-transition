#!/usr/bin/env python3
"""Read-only verification of the immutable V17T2R6 release manifest."""
from __future__ import annotations

import hashlib
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PACKAGE_MANIFEST_SHA256.json"
JSON_NAME = "PACKAGE_MANIFEST_SHA256.json"
CSV_NAME = "PACKAGE_FILE_MANIFEST_SHA256.csv"
EXPECTED_VERSION = "V17T2R6R7_HF2P2_FULL8760"
GENERATED_DIRS = {
    "__pycache__",
    "batch_logs",
    "failed_diagnostics",
    "outputs",
    "sensitivity_outputs",
}
GENERATED_FILES = {
    "audits/FIGSHARE_2024_LOAD_DATA_QUALITY_AUDIT.csv",
    "audits/PUBLICATION_RESULT_LINEAGE.json",
    "audits/PUBLICATION_SOURCE_FINGERPRINT.json",
    "audits/PUBLICATION_SOURCE_GATE_CASES.json",
    "audits/PUBLICATION_SOURCE_GATE_RESULTS.json",
    "audits/PUBLICATION_SOURCE_GATE_SOURCE.json",
    "audits/V17T2R6_8760_JULIA_STATIC_AUDIT.json",
    "audits/V17T2R6_FULL8760_PACKAGE_QA.json",
    "audits/V17T2R6_FULL8760_PAIR_IDENTITY_AUDIT.json",
    "audits/V17T2R6R7_PARALLEL_SCHEDULER_AUDIT.json",
    "storage_runner/prepared_8760_cases_index.csv",
}
EXCLUDED_FILES = {JSON_NAME, CSV_NAME, *GENERATED_FILES}
GENERATED_CASE_RELATIVE_FILES = {
    "SENSITIVITY_SCENARIO_META.json",
    "audits/CASE_PUBLICATION_SOURCE_FINGERPRINT.json",
    "audits/FULL8760_PREPARED_INPUT_VALIDATION.json",
    "audits/FULL8760_TEMPORAL_INPUT_AUDIT.json",
    "inputs/loads.csv",
    "inputs/loads_new.csv",
    "inputs/zone_coincident_peak_demand.csv",
}


def is_in_scope(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    rel_posix = rel.as_posix()
    if path.name in {JSON_NAME, CSV_NAME} or rel_posix in EXCLUDED_FILES or path.suffix.lower() == ".pyc":
        return False
    if len(rel.parts) >= 3 and rel.parts[0] == "sensitivity_cases":
        case_relative = "/".join(rel.parts[2:])
        if case_relative in GENERATED_CASE_RELATIVE_FILES:
            return False
    return not any(part in GENERATED_DIRS for part in rel.parts)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors: list[str] = []
    if payload.get("version") != EXPECTED_VERSION:
        errors.append(f"MANIFEST_VERSION: expected {EXPECTED_VERSION}, got {payload.get('version')}")
    if set(payload.get("excluded_directories", [])) != GENERATED_DIRS:
        errors.append("MANIFEST_SCOPE: excluded_directories mismatch")
    if set(payload.get("excluded_files", [])) != EXCLUDED_FILES:
        errors.append("MANIFEST_SCOPE: excluded_files mismatch")
    if set(payload.get("excluded_case_relative_files", [])) != GENERATED_CASE_RELATIVE_FILES:
        errors.append("MANIFEST_SCOPE: excluded_case_relative_files mismatch")

    listed_paths = [str(item.get("path", "")) for item in payload.get("files", [])]
    listed_set = set(listed_paths)
    if payload.get("file_count") != len(listed_paths):
        errors.append("MANIFEST_FILE_COUNT_MISMATCH")
    listed_total_bytes = sum(int(item.get("bytes", -1)) for item in payload.get("files", []))
    if payload.get("total_bytes") != listed_total_bytes:
        errors.append("MANIFEST_TOTAL_BYTES_MISMATCH")
    if len(listed_paths) != len(listed_set):
        errors.append("MANIFEST_DUPLICATE_PATHS")

    csv_path = ROOT / CSV_NAME
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        csv_projection = [
            {"path": row["path"], "bytes": int(row["bytes"]), "sha256": row["sha256"]}
            for row in csv_rows
        ]
        json_projection = [
            {"path": item["path"], "bytes": int(item["bytes"]), "sha256": item["sha256"]}
            for item in payload.get("files", [])
        ]
        if csv_projection != json_projection:
            errors.append("CSV_JSON_MANIFEST_MISMATCH")
    except Exception as exc:
        errors.append(f"CSV_MANIFEST_READ: {exc}")
    actual_set = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and is_in_scope(path)
    }
    for rel in sorted(actual_set - listed_set):
        errors.append(f"UNTRACKED_IMMUTABLE_FILE: {rel}")
    for rel in sorted(listed_set - actual_set):
        errors.append(f"MANIFEST_ONLY_FILE: {rel}")

    for item in payload.get("files", []):
        path = ROOT / item["path"]
        if not path.is_file():
            errors.append(f"MISSING: {item['path']}")
            continue
        if path.stat().st_size != int(item["bytes"]):
            errors.append(f"SIZE: {item['path']}")
            continue
        if sha256(path) != item["sha256"]:
            errors.append(f"SHA256: {item['path']}")
    result = {
        "version": payload.get("version"),
        "checked_files": len(payload.get("files", [])),
        "immutable_scope_exact": actual_set == listed_set,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 2)


if __name__ == "__main__":
    main()
