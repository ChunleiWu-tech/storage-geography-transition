#!/usr/bin/env python3
"""Validate the exact V17T5 table and figure release set."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from v17t5_paths import AUDIT_DIR, FIG_MAIN, FIG_SUPP, OUTPUT_ROOT, PROJECT_ROOT, SOURCE_ROOT, TABLE_MAIN, TABLE_SUPP, TABLE_TARGETYEAR

REGISTRY = SOURCE_ROOT / "postprocess" / "figure_output_registry_v17t5.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_table_path(kind: str, table_name: str) -> Path:
    """Resolve a registry table without assuming figure and table subfolders match.

    Several supplementary input diagnostics intentionally reuse the audited
    main input-evidence table.  Prefer the main-table copy when present, then
    fall back to supplementary tables.
    """
    candidates = [TABLE_MAIN / table_name, TABLE_SUPP / table_name, TABLE_TARGETYEAR / table_name]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return (TABLE_MAIN if kind == "main" else TABLE_SUPP) / table_name


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-set", default="spatial_legacy_full")
    args = parser.parse_args()

    registry = pd.read_csv(REGISTRY)
    required_registry_columns = {
        "figure_id",
        "kind",
        "file_stem",
        "primary_table",
        "claim_scope",
    }
    missing = required_registry_columns.difference(registry.columns)
    if missing:
        raise SystemExit(f"Figure registry missing columns: {sorted(missing)}")
    if len(registry) != 17 or registry["figure_id"].duplicated().any():
        raise SystemExit("Figure registry must contain exactly 17 unique figures")

    rows: list[dict[str, object]] = []
    expected_files: set[Path] = set()
    for row in registry.itertuples(index=False):
        folder = FIG_MAIN if row.kind == "main" else FIG_SUPP
        base = folder / row.file_stem
        pdf = base.with_suffix(".pdf")
        svg = base.with_suffix(".svg")
        png = base.with_suffix(".png")
        table = expected_table_path(row.kind, row.primary_table)
        expected_files.update({pdf.resolve(), svg.resolve(), png.resolve()})
        record = {
            "figure_id": row.figure_id,
            "kind": row.kind,
            "file_stem": row.file_stem,
            "pdf_exists": pdf.is_file(),
            "svg_exists": svg.is_file(),
            "png_exists": png.is_file(),
            "primary_table_exists": table.is_file(),
            "pdf_bytes": pdf.stat().st_size if pdf.is_file() else 0,
            "pdf_width_mm": 0.0,
            "pdf_width_180mm": False,
            "svg_bytes": svg.stat().st_size if svg.is_file() else 0,
            "png_bytes": png.stat().st_size if png.is_file() else 0,
            "png_width_px": 0,
            "png_height_px": 0,
            "png_nonblank": False,
            "table_rows": 0,
        }
        if pdf.is_file():
            raw = pdf.read_bytes()
            match = re.search(rb"/MediaBox\s*\[\s*[-0-9.]+\s+[-0-9.]+\s+([0-9.]+)\s+([0-9.]+)\s*\]", raw)
            if match:
                width_mm = float(match.group(1)) * 25.4 / 72.0
                record["pdf_width_mm"] = width_mm
                record["pdf_width_180mm"] = abs(width_mm - 180.0) <= 0.20
        if png.is_file():
            with Image.open(png) as image:
                rgb = np.asarray(image.convert("RGB"))
                record["png_width_px"] = int(image.width)
                record["png_height_px"] = int(image.height)
                record["png_nonblank"] = bool(np.std(rgb.astype(float)) > 1.0)
        if table.is_file():
            record["table_rows"] = int(len(pd.read_csv(table)))
        record["pass"] = bool(
            record["pdf_exists"]
            and record["svg_exists"]
            and record["png_exists"]
            and record["primary_table_exists"]
            and record["pdf_bytes"] > 5_000
            and record["pdf_width_180mm"]
            and record["svg_bytes"] > 1_000
            and record["png_bytes"] > 10_000
            and record["png_width_px"] >= 1000
            and record["png_height_px"] >= 550
            and record["png_nonblank"]
            and record["table_rows"] > 0
        )
        rows.append(record)

    audit = pd.DataFrame(rows)
    actual_files = {
        path.resolve()
        for folder in [FIG_MAIN, FIG_SUPP]
        for path in folder.glob("*.*")
        if path.suffix.lower() in {".pdf", ".svg", ".png"}
    }
    extras = sorted(str(path) for path in actual_files - expected_files)
    missing_expected = sorted(str(path) for path in expected_files - actual_files)
    exact_file_set = not extras and not missing_expected and len(actual_files) == 51

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_DIR / "figure_file_release_audit.csv", index=False)

    manifest_rows = []
    for path in sorted(
        p for p in OUTPUT_ROOT.rglob("*") if p.is_file() and p.parent != AUDIT_DIR
    ):
        manifest_rows.append(
            {
                "relative_path": path.relative_to(OUTPUT_ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(AUDIT_DIR / "postprocess_output_manifest_sha256.csv", index=False)

    scientific_path = AUDIT_DIR / "scientific_consistency_audit.json"
    preflight_path = AUDIT_DIR / f"preflight_{args.scenario_set}.json"
    targetyear_preflight_path = AUDIT_DIR / "targetyear_preflight.json"
    targetyear_scientific_path = AUDIT_DIR / "targetyear_scientific_consistency_audit.json"
    scientific_pass = scientific_path.is_file() and json.loads(
        scientific_path.read_text(encoding="utf-8")
    ).get("all_pass") is True
    preflight_pass = preflight_path.is_file() and json.loads(
        preflight_path.read_text(encoding="utf-8")
    ).get("all_pass") is True
    targetyear_preflight_pass = targetyear_preflight_path.is_file() and json.loads(
        targetyear_preflight_path.read_text(encoding="utf-8")
    ).get("all_pass") is True
    targetyear_scientific_pass = targetyear_scientific_path.is_file() and json.loads(
        targetyear_scientific_path.read_text(encoding="utf-8")
    ).get("all_pass") is True

    summary = {
        "version": "V17T5R6R8R5",
        "scenario_set": args.scenario_set,
        "main_figures": int((registry["kind"] == "main").sum()),
        "supplementary_figures": int((registry["kind"] == "supplementary").sum()),
        "figure_formats_expected": 51,
        "figure_formats_found": len(actual_files),
        "exact_figure_file_set": exact_file_set,
        "extra_figure_files": extras,
        "missing_figure_files": missing_expected,
        "preflight_pass": preflight_pass,
        "scientific_consistency_pass": scientific_pass,
        "targetyear_preflight_pass": targetyear_preflight_pass,
        "targetyear_scientific_consistency_pass": targetyear_scientific_pass,
        "all_figure_files_pass": bool(audit["pass"].all()),
        "all_pdf_pages_180mm": bool(audit["pdf_width_180mm"].all()),
        "pdf_width_mm_min": float(audit["pdf_width_mm"].min()),
        "pdf_width_mm_max": float(audit["pdf_width_mm"].max()),
        "all_pass": bool(
            preflight_pass
            and scientific_pass
            and targetyear_preflight_pass
            and targetyear_scientific_pass
            and exact_file_set
            and audit["pass"].all()
        ),
        "failed_figures": audit.loc[~audit["pass"], "figure_id"].tolist(),
    }
    (AUDIT_DIR / "postprocess_release_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
