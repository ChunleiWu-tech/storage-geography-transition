#!/usr/bin/env python3
"""Build deterministic SHA-256 manifests for immutable V17T2R6 release files."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JSON_NAME = "PACKAGE_MANIFEST_SHA256.json"
CSV_NAME = "PACKAGE_FILE_MANIFEST_SHA256.csv"
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
    paths = sorted(
        (path for path in ROOT.rglob("*") if path.is_file() and is_in_scope(path)),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    files = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in paths
    ]
    payload = {
        "version": "V17T2R6R7_HF2P2_FULL8760",
        "algorithm": "SHA-256",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "immutable release files; regenerated cases, run state and reproducible audit artifacts are validated by semantic preflight gates",
        "excluded_directories": sorted(GENERATED_DIRS),
        "excluded_files": sorted(EXCLUDED_FILES),
        "excluded_case_relative_files": sorted(GENERATED_CASE_RELATIVE_FILES),
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }
    (ROOT / JSON_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    with (ROOT / CSV_NAME).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows(files)
    print(json.dumps({
        "version": payload["version"],
        "file_count": payload["file_count"],
        "total_bytes": payload["total_bytes"],
        "json": JSON_NAME,
        "csv": CSV_NAME,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
