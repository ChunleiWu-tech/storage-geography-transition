#!/usr/bin/env python3
"""Validate the exact V30 7-main + 14-supplementary publication release."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from PIL import Image

from v17t5_paths import AUDIT_DIR, FIG_MAIN, FIG_SUPP, OUTPUT_ROOT, SOURCE_ROOT, TABLE_FULL8760, TABLE_V20, TEXT_DIR
from v30_common import write_json


def main() -> None:
    registry = pd.read_csv(SOURCE_ROOT / "postprocess" / "figure_output_registry_v30.csv")
    if len(registry) != 21 or (registry.kind == "main").sum() != 7 or (registry.kind == "supplementary").sum() != 14:
        raise ValueError("V30 figure registry must be exactly 7 main + 14 supplementary figures")
    failures: list[str] = []
    found: set[str] = set()
    for row in registry.itertuples(index=False):
        directory = FIG_MAIN if row.kind == "main" else FIG_SUPP
        for extension in ("pdf", "svg", "png"):
            path = directory / f"{row.file_stem}.{extension}"
            relative = path.relative_to(OUTPUT_ROOT).as_posix(); found.add(relative)
            if not path.is_file() or path.stat().st_size < 1000:
                failures.append(f"missing_or_small:{relative}")
                continue
            if extension == "png":
                with Image.open(path) as image:
                    width, height = image.size
                if width < 1500 or height < 1000:
                    failures.append(f"png_resolution:{relative}:{width}x{height}")
            elif extension == "svg":
                text = path.read_text(encoding="utf-8", errors="replace")
                if "<svg" not in text or "nan" in text.lower():
                    failures.append(f"invalid_svg:{relative}")
    actual = {
        path.relative_to(OUTPUT_ROOT).as_posix()
        for directory in (FIG_MAIN, FIG_SUPP) if directory.is_dir()
        for path in directory.iterdir() if path.is_file() and path.suffix.lower() in {".pdf", ".svg", ".png"}
    }
    if actual != found:
        failures.append(f"figure_file_set_mismatch:extra={sorted(actual-found)}:missing={sorted(found-actual)}")
    required_tables = [
        TABLE_FULL8760 / "full8760_certificate_summary.csv",
        TABLE_FULL8760 / "full8760_robustness_components.csv",
        TABLE_FULL8760 / "full8760_zone_robustness.csv",
        TABLE_V20 / "v20_layer_a_pair_costs.csv",
        TABLE_V20 / "v20_layer_b_context_penalties.csv",
        TABLE_V20 / "v20_evidence_horizon_penalty.csv",
        TABLE_V20 / "v20_evidence_direct_build_by_year_zone_tech.csv",
        TABLE_V20 / "v20_equal_horizon_build_by_year_zone_tech.csv",
    ]
    for path in required_tables:
        if not path.is_file() or pd.read_csv(path).empty:
            failures.append(f"missing_or_empty_table:{path}")
    full_contract = json.loads((TABLE_FULL8760 / "FULL8760_PUBLICATION_CONTRACT.json").read_text(encoding="utf-8"))
    v20_contract = json.loads((TABLE_V20 / "V20_PUBLICATION_CONTRACT.json").read_text(encoding="utf-8"))
    if full_contract.get("status") != "PASS" or v20_contract.get("status") != "PASS":
        failures.append("extended_publication_contract_not_PASS")
    text = (TEXT_DIR / "V30_NEW_EVIDENCE_RESULTS_DRAFT_EN.md").read_text(encoding="utf-8")
    for phrase in ("not an actual technology build", "not added to the annualized", "does not replace"):
        if phrase not in text:
            failures.append(f"claim_boundary_text_missing:{phrase}")
    report = {
        "version": "V30_POSTPROCESS_RELEASE_R1", "status": "PASS" if not failures else "FAIL",
        "main_figures": 7, "supplementary_figures": 14, "figure_formats": ["pdf", "svg", "png"],
        "figure_files_expected": 63, "figure_files_found": len(actual),
        "exact_figure_file_set": actual == found, "extended_tables_checked": len(required_tables),
        "failures": failures,
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(AUDIT_DIR / "V30_POSTPROCESS_RELEASE_SUMMARY.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
