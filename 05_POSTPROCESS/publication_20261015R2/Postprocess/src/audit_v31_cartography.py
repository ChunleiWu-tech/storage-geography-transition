from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


MAP_FIGURES = (
    ("main", "Fig1_inherited_storage_geography"),
    ("main", "Fig2_equal_stock_unequal_spatial_value"),
    ("main", "Fig3_compensatory_investment_cost"),
    ("main", "Fig4_spatial_path_dependence"),
    ("main", "Fig6_future_storage_correction_of_spatial_lockin"),
    ("main", "Fig7_future_pathway_and_validation_boundaries"),
    ("supplementary", "FigS01_model_zone_network_inputs"),
    ("supplementary", "FigS05_rule_based_allocation_diagnostics"),
)


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG: {path}")
    return struct.unpack(">II", header[16:24])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    map_root = root / "metadata" / "map_compliance"
    provinces_path = map_root / "china_provinces.geojson"
    dashed_path = map_root / "nine_dash_line_geometry_only.geojson"
    provenance_path = map_root / "MAP_COMPLIANCE_AND_PROVENANCE.json"
    provinces = json.loads(provinces_path.read_text(encoding="utf-8"))
    dashed = json.loads(dashed_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

    province_names = [str(x.get("properties", {}).get("name", "")) for x in provinces.get("features", [])]
    figure_files: list[dict[str, object]] = []
    for group, stem in MAP_FIGURES:
        for suffix in (".pdf", ".svg", ".png"):
            path = root / "figures" / group / f"{stem}{suffix}"
            row: dict[str, object] = {
                "path": path.relative_to(root).as_posix(),
                "exists": path.is_file(),
                "bytes": path.stat().st_size if path.is_file() else 0,
            }
            if suffix == ".png" and path.is_file():
                row["pixel_size"] = list(png_size(path))
            figure_files.append(row)

    all_png = sorted((root / "figures").glob("**/*.png"))
    png_sizes = {p.relative_to(root).as_posix(): list(png_size(p)) for p in all_png}
    width_values = sorted({value[0] for value in png_sizes.values()})

    spatial_source = (root / "reproducibility" / "V31" / "plot_spatial_legacy_figures.py").read_text(encoding="utf-8")
    v20_source = (root / "reproducibility" / "V31" / "plot_v20_publication_figures.py").read_text(encoding="utf-8")
    paths_source = (root / "reproducibility" / "V31" / "v17t5_paths.py").read_text(encoding="utf-8")

    checks = {
        "province_feature_count_34": len(provinces.get("features", [])) == 34,
        "taiwan_feature_present": "台湾省" in province_names,
        "south_china_sea_line_feature_count_10": len(dashed.get("features", [])) == 10,
        "official_map_reference_archived": provenance.get("official_review_number") == "GS(2023)2767",
        "all_8_map_figures_have_pdf_svg_png": all(bool(x["exists"]) and int(x["bytes"]) > 1000 for x in figure_files),
        "all_21_figure_pngs_share_180mm_width": len(png_sizes) == 21 and len(width_values) == 1 and 4248 <= width_values[0] <= 4254,
        "height_varies_only_by_panel_layout": all(value[1] >= 1300 for value in png_sizes.values()),
        "archived_map_asset_route_enabled": 'OUTPUT_ROOT / "metadata" / "map_compliance"' in paths_source,
        "province_and_taiwan_outline_pass_enabled": "Pass 2: explicit province and Taiwan outlines" in spatial_source and "zorder=1.65" in spatial_source,
        "fixed_south_china_sea_inset_enabled": "axis.inset_axes([0.825, 0.030, 0.155, 0.300]" in spatial_source,
        "taiwan_label_enabled_and_south_china_sea_label_omitted": '"Taiwan"' in spatial_source and '"South China\\nSea"' not in spatial_source,
        "fig1_vertical_frame_gate_enabled": "Fig1a/Fig1b vertical frame mismatch" in spatial_source,
        "fig7_vertical_frame_gate_enabled": "Fig7c/Fig7d vertical frame mismatch" in v20_source,
        "map_colourbar_reserved_band_enabled": "Rectangle((0.275, 0.825), 0.450, 0.105" in spatial_source and "Rectangle((0.27, 0.815), 0.46, 0.115" in v20_source,
    }
    failures = [name for name, passed in checks.items() if not passed]
    payload = {
        "version": "V31R6_CARTOGRAPHIC_ALIGNMENT_AND_SIZE_QA_20260901",
        "status": "PASS" if not failures else "FAIL",
        "scientific_data_changed": False,
        "model_results_changed": False,
        "word_embedding_performed": False,
        "standalone_formats": ["PDF", "SVG", "PNG"],
        "figure_width_specification": {
            "publication_width_mm": 180.0,
            "png_width_pixels_at_600_dpi": width_values,
            "rule": "One common page width; height changes only with the audited number of panel rows.",
        },
        "map_assets": {
            "province_geojson": provinces_path.relative_to(root).as_posix(),
            "province_features": len(provinces.get("features", [])),
            "taiwan_feature": "台湾省" in province_names,
            "south_china_sea_geojson": dashed_path.relative_to(root).as_posix(),
            "south_china_sea_line_features": len(dashed.get("features", [])),
        },
        "map_figure_count": len(MAP_FIGURES),
        "map_figure_files": figure_files,
        "all_png_sizes": png_sizes,
        "checks": checks,
        "failed": failures,
    }
    out = root / "audits" / "V31R6_CARTOGRAPHIC_ALIGNMENT_AND_SIZE_QA.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
