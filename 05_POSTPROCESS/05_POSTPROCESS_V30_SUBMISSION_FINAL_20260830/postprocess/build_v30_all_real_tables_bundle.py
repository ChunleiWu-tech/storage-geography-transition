#!/usr/bin/env python3
"""Build, audit, map, and bundle every real table required by V30 figures."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def require(root: Path, paths: list[str], label: str) -> None:
    if not root.is_dir():
        raise FileNotFoundError(f"{label} root is not a directory: {root}")
    missing = [str(root / relative) for relative in paths if not (root / relative).exists()]
    if missing:
        raise FileNotFoundError(f"{label} root is incomplete: " + "; ".join(missing))


def run(script: str, *args: str, env: dict[str, str], cwd: Path) -> None:
    command = [sys.executable, str(SOURCE_ROOT / "postprocess" / script), *args]
    print("RUN:", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{script} failed with return code {completed.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-upstream-root", required=True)
    parser.add_argument("--targetyear-upstream-root", required=True)
    parser.add_argument("--full8760-root", required=True)
    parser.add_argument("--future-storage-root", required=True)
    parser.add_argument("--bundle-path", required=True)
    args = parser.parse_args()
    roots = {
        "main": Path(args.main_upstream_root).resolve(),
        "targetyear": Path(args.targetyear_upstream_root).resolve(),
        "full8760": Path(args.full8760_root).resolve(),
        "v20": Path(args.future_storage_root).resolve(),
    }
    if len(set(roots.values())) != 4:
        raise ValueError("The four upstream roots must be distinct")
    require(roots["main"], ["storage_runner/storage_batch_run_summary.csv", "storage_runner/scenarios_storage_master.csv", "outputs"], "Main")
    require(roots["targetyear"], ["storage_runner/scenarios_targetyear_linked.csv", "sensitivity_outputs", "VERSION_V17T2R5.txt"], "Target-year")
    require(roots["full8760"], ["robustness_distance_8760_quality_recovery_outputs/V17T2R6R24P3_HF18P2_COMBINED_ALL4_final_summary.json"], "FULL8760")
    require(roots["v20"], ["storage_cases", "modules/correction2033", "audits/v20/V20_LAYER_B_16_SOLVER_SUMMARY.csv", "audits/v20/V20_LAYER_C_EQUAL_HORIZON_2_SOLVER_SUMMARY.csv"], "V20")

    bundle = Path(args.bundle_path).resolve()
    bundle.parent.mkdir(parents=True, exist_ok=True)
    remove(bundle)
    working = SOURCE_ROOT / "postprocess_outputs" / "_table_bundle_working"
    remove(working)
    working.mkdir(parents=True)
    started = time.time()
    env = os.environ.copy()
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "V17_PROJECT_ROOT": str(roots["main"]),
        "V17_TARGETYEAR_SENSITIVITY_ROOT": str(roots["targetyear"]),
        "V30_FULL8760_ROOT": str(roots["full8760"]),
        "V30_FUTURE_STORAGE_ROOT": str(roots["v20"]),
        "V17_POSTPROCESS_SOURCE_ROOT": str(SOURCE_ROOT),
        "V17_POSTPROCESS_OUTPUT_ROOT": str(working),
    })
    try:
        lineage_output = working / "audits" / "UPSTREAM_RESULT_LINEAGE_AUDIT.json"
        lineage_output.parent.mkdir(parents=True, exist_ok=True)
        lineage = subprocess.run([
            sys.executable, str(SOURCE_ROOT / "postprocess" / "check_upstream_source_fingerprints.py"),
            str(roots["main"]), str(roots["targetyear"]), "--require-results", "--output", str(lineage_output),
        ], cwd=SOURCE_ROOT, env=env, check=False)
        if lineage.returncode != 0:
            raise RuntimeError("Main 16-case or target-year 8-case result lineage is incomplete")

        steps = (
            ("audit_v17t5_postprocess_source.py", (), roots["main"]),
            ("preflight_spatial_legacy_outputs.py", ("--scenario-set", "spatial_legacy_full"), roots["main"]),
            ("build_spatial_legacy_tables.py", ("--scenario-set", "spatial_legacy_full"), roots["main"]),
            ("audit_against_successful_baseline.py", (), roots["main"]),
            ("audit_scientific_consistency.py", (), roots["main"]),
            ("preflight_targetyear_sensitivity.py", (), roots["targetyear"]),
            ("build_targetyear_sensitivity_tables.py", (), roots["targetyear"]),
            ("audit_targetyear_sensitivity.py", (), roots["targetyear"]),
            ("preflight_v30_extended_results.py", (), SOURCE_ROOT),
            ("build_full8760_validation_tables.py", (), SOURCE_ROOT),
            ("build_v20_publication_tables.py", (), SOURCE_ROOT),
        )
        for script, script_args, cwd in steps:
            run(script, *script_args, env=env, cwd=cwd)

        expected_directories = ["main", "supplementary", "targetyear_sensitivity", "full8760_validation", "future_storage"]
        missing_directories = [name for name in expected_directories if not (working / "tables" / name).is_dir()]
        if missing_directories:
            raise RuntimeError(f"Missing table groups: {missing_directories}")

        metadata = working / "metadata"
        metadata.mkdir()
        for name in ("POSTPROCESS_SCIENTIFIC_CONTRACT_V30.json", "UPSTREAM_ALIGNMENT_AND_UNIT_AUDIT_V30.json", "UPSTREAM_ALIGNMENT_AND_UNIT_AUDIT_V30.md"):
            shutil.copy2(SOURCE_ROOT / name, metadata / name)
        registry_path = SOURCE_ROOT / "postprocess" / "figure_output_registry_v30.csv"
        shutil.copy2(registry_path, metadata / registry_path.name)
        registry = pd.read_csv(registry_path)
        if len(registry) != 21 or registry["figure_id"].duplicated().any():
            raise RuntimeError("Figure registry is not the required unique 7 + 14 set")
        figure_map: list[dict] = []
        for row in registry.to_dict("records"):
            matches = sorted((working / "tables").rglob(str(row["primary_table"])))
            if len(matches) != 1:
                raise RuntimeError(f"{row['figure_id']}: expected exactly one {row['primary_table']}, found {len(matches)}")
            table = matches[0]
            frame = pd.read_csv(table)
            if frame.empty:
                raise RuntimeError(f"{row['figure_id']}: primary table is empty")
            figure_map.append({
                "figure_id": row["figure_id"], "kind": row["kind"], "file_stem": row["file_stem"],
                "primary_table": table.relative_to(working).as_posix(), "rows": len(frame),
                "bytes": table.stat().st_size, "sha256": sha256(table), "claim_scope": row["claim_scope"],
            })
        (metadata / "FIGURE_TO_REAL_DATA_MAP_V30.json").write_text(json.dumps(figure_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        files_before_manifest = sorted(path for path in working.rglob("*") if path.is_file())
        manifest = {
            "version": "V30_ALL_REAL_TABLES_AND_AUDITS_20260830",
            "status": "PASS",
            "source": "four strict read-only upstream result roots",
            "upstream_roots": {key: str(value) for key, value in roots.items()},
            "case_sets": {"main": 16, "targetyear": 8, "full8760": 4, "v20": 26},
            "figure_map_rows": 21,
            "csv_files": sum(path.suffix.lower() == ".csv" for path in files_before_manifest),
            "upstream_write_performed": False,
            "elapsed_seconds": time.time() - started,
            "files": [{"path": path.relative_to(working).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in files_before_manifest],
        }
        (working / "V30_ALL_REAL_TABLES_BUNDLE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        staging_zip = bundle.with_suffix(bundle.suffix + ".working")
        remove(staging_zip)
        archive_root = "V30_ALL_REAL_TABLES_AND_AUDITS_20260830"
        with zipfile.ZipFile(staging_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(item for item in working.rglob("*") if item.is_file()):
                archive.write(path, f"{archive_root}/{path.relative_to(working).as_posix()}")
        staging_zip.replace(bundle)
        print(json.dumps({
            "status": "PASS", "bundle": str(bundle), "bytes": bundle.stat().st_size,
            "sha256": sha256(bundle), "figure_data_maps": 21,
            "message": "ALL REAL TABLES + AUDITS + LINEAGE BUNDLED",
        }, ensure_ascii=False, indent=2))
        remove(working)
        return 0
    except Exception as exc:
        (working / "FAILED_V30_TABLE_BUNDLE.json").write_text(json.dumps({"status": "FAIL", "error": str(exc), "working_retained": str(working)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
