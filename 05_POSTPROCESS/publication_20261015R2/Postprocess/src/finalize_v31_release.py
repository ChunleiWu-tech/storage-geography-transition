#!/usr/bin/env python3
"""Finalize and independently audit the V31 publication-figure release."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


VERSION = "V31R6_PUBLICATION_FIGURES_LAYOUT_AUDITED_20260902"

FIGURES = [
    ("Fig1", "main", "Fig1_inherited_storage_geography", "Where is inherited storage located, and how concentrated and demand-mismatched is it?", ["tables/main/fig1a_legacy_nodes.csv", "tables/main/fig1b_model_network_edges.csv", "tables/main/fig1c_scenario_design.csv", "tables/main/fig1d_legacy_concentration.csv"], "Input evidence and controlled counterfactual identification."),
    ("Fig2", "main", "Fig2_equal_stock_unequal_spatial_value", "What spatial reallocation and system value arise when the same national inherited fleet is relocated?", ["tables/main/fig2_spatial_allocation.csv", "tables/main/fig2b_legacy_value_ladder.csv"], "Equal-total spatial reallocation and system-value mechanism."),
    ("Fig3", "main", "Fig3_compensatory_investment_cost", "How does the system absorb inherited spatial misalignment?", ["tables/main/fig3a_compensatory_investment.csv", "tables/main/fig5_transition_paths.csv", "tables/main/fig4_future_storage_spatial_reconfiguration.csv"], "Annual cost components, battery power, non-storage capacity and spatial compensation."),
    ("Fig4", "main", "Fig4_spatial_path_dependence", "How quickly is inherited mismatch corrected, where does it persist, and which correction classes emerge?", ["tables/main/fig4a_mismatch_persistence.csv", "tables/main/fig4b_zone_period_deltas.csv", "tables/main/fig4c_zone_correction.csv"], "Temporal persistence and spatial correction, without interpreting ribbons as physical flows."),
    ("Fig5", "main", "Fig5_robustness_boundary_conditions", "Does the direction of the legacy effect persist under boundary uncertainty?", ["tables/main/fig5_robustness_effects.csv"], "Exact reconstructed-standardized versus optimized robustness pairs."),
    ("Fig6", "main", "Fig6_future_storage_correction_of_spatial_lockin", "How do 2033 future-storage options compensate for inherited spatial lock-in?", ["tables/future_storage_v31/fig6_layer_a_pair_metrics.csv", "tables/future_storage_v31/fig6_adaptive_zone_portfolios.csv"], "Annual target-year matched correction; Expanded is a pressure test, not the headline siting claim."),
    ("Fig7", "main", "Fig7_future_pathway_and_validation_boundaries", "When, where and under which contexts does future storage adapt, and what full-year hourly feasibility gap remains?", ["tables/future_storage_v31/fig7_core_timing_by_technology.csv", "tables/future_storage_v31/fig7_core_zone_difference.csv", "tables/future_storage_v31/fig7_context_pair_metrics.csv", "tables/full8760_validation/full8760_certificate_summary.csv"], "Representative-period pathway plus a separately labelled full-year hourly feasibility diagnostic."),
    ("FigS01", "supplementary", "FigS01_model_zone_network_inputs", "Which demand and VRE inputs underlie the model-zone geography?", ["tables/main/fig1a_legacy_nodes.csv", "tables/main/fig1b_model_network_edges.csv"], "Input evidence."),
    ("FigS02", "supplementary", "FigS02_storage_power_energy_duration_validation", "Is inherited power-energy-duration accounting internally consistent?", ["tables/main/fig1a_legacy_nodes.csv"], "Input validation."),
    ("FigS03", "supplementary", "FigS03_empirical_deployment_envelope", "How is the empirical deployment envelope constructed and used?", ["tables/main/fig1a_legacy_nodes.csv", "tables/main/fig2_spatial_allocation.csv"], "Empirical allocation boundary reconstructed directly from the audited node inventory and optimized allocation."),
    ("FigS04", "supplementary", "FigS04_full_scenario_matrix", "What is the complete confirmatory and robustness scenario design?", ["tables/supplementary/figS06_scenario_matrix.csv"], "Scenario design."),
    ("FigS05", "supplementary", "FigS05_rule_based_allocation_diagnostics", "How do transparent load and VRE allocation rules differ spatially from optimized reallocation?", ["tables/main/fig2_spatial_allocation.csv"], "Rule-based spatial benchmarks."),
    ("FigS06", "supplementary", "FigS06_full_reallocation_and_duration_deltas", "What are the complete zone-level power-reallocation and duration-standardization effects?", ["tables/main/fig2_spatial_allocation.csv"], "Full zone ranking."),
    ("FigS07", "supplementary", "FigS07_period_system_cost_penalties", "When do core-scenario cost penalties arise?", ["tables/main/fig5_transition_paths.csv"], "Period present-value evidence."),
    ("FigS08", "supplementary", "FigS08_technology_and_curtailment_adaptation", "Which non-battery capacity and curtailment responses accompany the storage legacy?", ["tables/supplementary/figS09_technology_capacity_differences.csv", "tables/main/fig5_transition_paths.csv"], "Adaptation evidence without repeated absolute trajectories."),
    ("FigS09", "supplementary", "FigS09_transmission_line_differences", "Which transmission additions differ between paired cases?", ["tables/supplementary/figS11_transmission_line_differences.csv"], "Transmission-investment evidence, not directional dispatch."),
    ("FigS10", "supplementary", "FigS10_final_storage_power_energy_duration", "Where is final storage power reallocated and how concentrated is that reallocation?", ["tables/main/fig4_future_storage_spatial_reconfiguration.csv"], "Signed zone changes and concentration; redundant exact-4-hour power-energy views are omitted."),
    ("FigS11", "supplementary", "FigS11_extended_robustness_metrics", "How do secondary transmission, curtailment and coupled network-curtailment responses vary?", ["tables/main/fig5_robustness_effects.csv"], "Secondary robustness diagnostics; repeated 4-hour points are replaced by a physical coupling view."),
    ("FigS12", "supplementary", "FigS12_targetyear_linked_chronology_ldes", "Does the location effect persist under linked chronology, technology-specific LDES and one-hour discretization?", ["tables/targetyear_sensitivity/targetyear_pairwise_observed_minus_optimal.csv", "tables/targetyear_sensitivity/figS12b_cost_component_decomposition.csv", "tables/targetyear_sensitivity/figS12c_compensatory_investment.csv", "tables/targetyear_sensitivity/figS12d_operational_response.csv"], "Annual single-target-year sensitivity evidence."),
    ("FigS13", "supplementary", "FigS13_full8760_robustness_certificates", "What minimum additional technology-neutral balancing capacity separates each fixed portfolio from full-year hourly feasibility?", ["tables/full8760_validation/full8760_certificate_summary.csv", "tables/full8760_validation/full8760_robustness_components.csv", "tables/full8760_validation/full8760_zone_robustness.csv", "tables/full8760_validation/full8760_certificate_gate_matrix.csv"], "Lower-bound hourly feasibility diagnostic; never an actual build or economic cost."),
    ("FigS14", "supplementary", "FigS14_future_storage_extended_robustness", "How do scale, duration, technology and timing vary across all 26 future-storage cases?", ["tables/future_storage_v31/figS14_all26_case_metrics.csv", "tables/future_storage_v31/figS14_all26_technology_shares.csv", "tables/future_storage_v31/figS14_all26_timing_shares.csv"], "Complete 8 + 16 + 2 future-storage evidence without duplicating headline panels."),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cleanup_stale_release_files(root: Path) -> None:
    provenance = root / "metadata" / "source_provenance"
    provenance.mkdir(parents=True, exist_ok=True)
    source_moves = [
        root / "V30_ALL_REAL_TABLES_BUNDLE_MANIFEST.json",
        root / "metadata" / "POSTPROCESS_SCIENTIFIC_CONTRACT_V30.json",
        root / "metadata" / "UPSTREAM_ALIGNMENT_AND_UNIT_AUDIT_V30.json",
        root / "metadata" / "UPSTREAM_ALIGNMENT_AND_UNIT_AUDIT_V30.md",
    ]
    for source in source_moves:
        if source.is_file():
            target = provenance / source.name
            if target.exists():
                target.unlink()
            shutil.move(str(source), str(target))
    stale = [
        root / "DELIVERY_MANIFEST_SHA256.json",
        root / "FIGURE_OUTPUT_MANIFEST_SHA256.json",
        root / "DELIVERY_MANIFEST_SHA256_V31.json",
        root / "FIGURE_OUTPUT_MANIFEST_SHA256_V31.json",
        root / "metadata" / "figure_output_registry_v30.csv",
        root / "metadata" / "FIGURE_TO_REAL_DATA_MAP_V30.json",
        root / "manuscript_ready_text" / "V30_NEW_EVIDENCE_RESULTS_DRAFT_EN.md",
        root / "audits" / "V31_FIGURE_RELEASE_QA.json",
        root / "audits" / "V31R1_SUBPANEL_STRICT_QA.csv",
        root / "audits" / "V31R1_SUBPANEL_STRICT_QA.json",
        root / "audits" / "V31R1_SUBPANEL_STRICT_QA.md",
        root / "DELIVERY_MANIFEST_SHA256_V31R2.json",
        root / "FIGURE_OUTPUT_MANIFEST_SHA256_V31R2.json",
        root / "audits" / "V31R2_FIGURE_RELEASE_QA.json",
        root / "audits" / "V31R2_SUBPANEL_STRICT_QA.csv",
        root / "audits" / "V31R2_SUBPANEL_STRICT_QA.json",
        root / "audits" / "V31R2_SUBPANEL_STRICT_QA.md",
        root / "DELIVERY_MANIFEST_SHA256_V31R3.json",
        root / "FIGURE_OUTPUT_MANIFEST_SHA256_V31R3.json",
        root / "audits" / "V31R3_FIGURE_RELEASE_QA.json",
        root / "audits" / "V31R3_SUBPANEL_STRICT_QA.csv",
        root / "audits" / "V31R3_SUBPANEL_STRICT_QA.json",
        root / "audits" / "V31R3_SUBPANEL_STRICT_QA.md",
        root / "DELIVERY_MANIFEST_SHA256_V31R4.json",
        root / "FIGURE_OUTPUT_MANIFEST_SHA256_V31R4.json",
        root / "audits" / "V31R4_FIGURE_RELEASE_QA.json",
        root / "audits" / "V31R4_SUBPANEL_STRICT_QA.csv",
        root / "audits" / "V31R4_SUBPANEL_STRICT_QA.json",
        root / "audits" / "V31R4_SUBPANEL_STRICT_QA.md",
        root / "DELIVERY_MANIFEST_SHA256_V31R5.json",
        root / "FIGURE_OUTPUT_MANIFEST_SHA256_V31R5.json",
        root / "audits" / "V31R5_FIGURE_RELEASE_QA.json",
        root / "audits" / "V31R5_SUBPANEL_STRICT_QA.csv",
        root / "audits" / "V31R5_SUBPANEL_STRICT_QA.json",
        root / "audits" / "V31R5_SUBPANEL_STRICT_QA.md",
    ]
    for path in stale:
        if path.is_file():
            path.unlink()


def copy_reproducibility(root: Path, work: Path) -> None:
    dest = root / "reproducibility" / "V31"
    dest.mkdir(parents=True, exist_ok=True)
    sources = [
        work / "build_v31_future_figure_tables.py",
        work / "audit_v31_subpanels.py",
        work / "finalize_v31_release.py",
        work / "ne_style.py",
        work / "plot_spatial_legacy_figures.py",
        work / "plot_targetyear_sensitivity_figure.py",
        work / "plot_full8760_validation.py",
        work / "plot_v20_publication_figures.py",
        work / "targetyear_sensitivity_common.py",
        work / "v17t5_paths.py",
    ]
    for source in sources:
        if not source.is_file():
            raise FileNotFoundError(source)
        target = dest / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
    (dest / "requirements_v31.txt").write_text(
        "matplotlib==3.10.3\nnumpy==2.2.6\npandas==2.2.3\nPillow>=10.0\n",
        encoding="utf-8",
    )
    (dest / "RUN_V31_REBUILD_FIGURES.ps1").write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "$root = (Resolve-Path (Join-Path $PSScriptRoot '..\\..')).Path\n"
        "$env:V17_POSTPROCESS_OUTPUT_ROOT = $root\n"
        "$env:V17_POSTPROCESS_SOURCE_ROOT = $root\n"
        "$python = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } elseif (Test-Path 'E:\\Python311\\python.exe') { 'E:\\Python311\\python.exe' } else { throw 'Python 3.10+ with V31 requirements is required.' }\n"
        "& $python (Join-Path $PSScriptRoot 'plot_spatial_legacy_figures.py') --group all\n"
        "& $python (Join-Path $PSScriptRoot 'plot_targetyear_sensitivity_figure.py')\n"
        "& $python (Join-Path $PSScriptRoot 'plot_full8760_validation.py')\n"
        "& $python (Join-Path $PSScriptRoot 'plot_v20_publication_figures.py')\n"
        "& $python (Join-Path $PSScriptRoot 'audit_v31_subpanels.py') --root $root\n",
        encoding="utf-8",
    )


def write_registry_and_contract(root: Path) -> None:
    registry = root / "metadata" / "figure_output_registry_v31.csv"
    registry.parent.mkdir(parents=True, exist_ok=True)
    with registry.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["figure_id", "kind", "file_stem", "scientific_question", "primary_table", "claim_scope"])
        writer.writeheader()
        for fig_id, kind, stem, question, tables, scope in FIGURES:
            writer.writerow({"figure_id": fig_id, "kind": kind, "file_stem": stem, "scientific_question": question, "primary_table": tables[0], "claim_scope": scope})
    data_map = {
        "version": VERSION,
        "status": "PASS",
        "figures": [
            {"figure_id": fig_id, "kind": kind, "file_stem": stem, "scientific_question": question,
             "source_tables": tables, "claim_scope": scope,
             "source_sha256": {table: sha256(root / table) for table in tables}}
            for fig_id, kind, stem, question, tables, scope in FIGURES
        ],
    }
    write_json(root / "metadata" / "FIGURE_TO_REAL_DATA_MAP_V31.json", data_map)
    contract = {
        "version": VERSION,
        "status": "PASS",
        "typography": {"family": "Arial", "panel_letters": "lowercase bold a/b/c/d/e", "panel_anchor": "outside axes, upper-left, common normalized position"},
        "unit_contract": {"power": "MW to GW once at plotting boundary", "energy": "MWh to GWh once at plotting boundary", "annual_cost": "USD/year to million or billion USD/year as labelled", "present_value_cost": "USD PV to billion USD PV as labelled"},
        "cartography_contract": {
            "official_reference": "Ministry of Natural Resources standard map GS(2023)2767",
            "territorial_elements": "Taiwan is displayed on every national map; South China Sea discontinuous lines are displayed in an unlabelled dedicated inset.",
            "model_scope": "Taiwan is a cartographic element only because the archived mainland model has no Taiwan model-zone result; no synthetic value is assigned.",
            "publication_caveat": "The archived official reference and hashes support provenance; obtain a new map-review number if required by the journal or public-release authority for the overlaid thematic map.",
        },
        "evidence_layers": {
            "main_16_case": "spatial legacy mechanism and multiyear adaptation",
            "targetyear_8_case": "linked chronology, LDES and one-hour sensitivity",
            "future_storage_26_case": "8 target-year correction + 16 evidence-direct pathway + 2 equal-horizon cases",
            "full8760_4_case": "fixed-portfolio minimum additional technology-neutral balancing capacity",
        },
        "claim_boundaries": [
            "A positive FULL8760 minimum additional balancing capacity is a lower-bound hourly feasibility gap, not an actual technology build, economic cost, or original fixed-portfolio feasibility pass.",
            "Layer-A annualized target-year costs are not added to Layer-B/C multiyear present-value costs.",
            "Expanded CAES/H2 portfolios are pressure tests and not headline province-siting evidence.",
            "Missing values are never imputed as scientific zero; true strict-success zero builds remain zero.",
            "V31R6 changes only figure layout and cartographic text: the Fig. 3d colour-scale position, Fig. 6 column spacing, Fig. S5 map spacing and omission of the South China Sea inset text label; inset geometry and all scientific inputs, constraints, objectives, solver results, plotted values and colour-scale domains remain unchanged.",
        ],
    }
    write_json(root / "metadata" / "POSTPROCESS_SCIENTIFIC_CONTRACT_V31.json", contract)


def make_contact_sheet(paths: list[Path], output: Path, columns: int = 2) -> None:
    tile_w, tile_h, header = 760, 560, 34
    rows = (len(paths) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * tile_w, rows * (tile_h + header)), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, path in enumerate(paths):
        row, col = divmod(index, columns)
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((tile_w - 20, tile_h - 20), Image.Resampling.LANCZOS)
            x = col * tile_w + (tile_w - image.width) // 2
            y = row * (tile_h + header) + header + (tile_h - image.height) // 2
            canvas.paste(image, (x, y))
        draw.text((col * tile_w + 8, row * (tile_h + header) + 8), path.stem, fill="black", font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, dpi=(150, 150))


def audit_figures(root: Path) -> dict:
    failures: list[str] = []
    expected_by_kind = {
        "main": {stem for _, kind, stem, *_ in FIGURES if kind == "main"},
        "supplementary": {stem for _, kind, stem, *_ in FIGURES if kind == "supplementary"},
    }
    dimensions = {}
    panel_counts = {}
    font_families: set[str] = set()
    numeric_bad = re.compile(r"(?<![A-Za-z0-9_])(?:nan|[+-]?inf)(?![A-Za-z0-9_])", re.IGNORECASE)
    for kind, expected in expected_by_kind.items():
        folder = root / "figures" / kind
        for extension in ("png", "pdf", "svg"):
            actual = {path.stem for path in folder.glob(f"*.{extension}")}
            if actual != expected:
                failures.append(f"{kind}_{extension}_set_mismatch")
        for stem in sorted(expected):
            png = folder / f"{stem}.png"
            pdf = folder / f"{stem}.pdf"
            svg = folder / f"{stem}.svg"
            with Image.open(png) as image:
                dimensions[f"{kind}/{stem}.png"] = {"pixels": list(image.size), "dpi": list(image.info.get("dpi", (0, 0)))}
                # Wide landscape supplements may legitimately be shallow; use
                # physical publication bounds instead of a square-image rule.
                if image.size[0] < 4200 or image.size[1] < 1200 or min(image.info.get("dpi", (0, 0))) < 590:
                    failures.append(f"png_resolution::{kind}/{stem}")
            if pdf.read_bytes()[:4] != b"%PDF":
                failures.append(f"pdf_header::{kind}/{stem}")
            try:
                tree = ET.parse(svg)
            except ET.ParseError:
                failures.append(f"svg_xml::{kind}/{stem}")
                continue
            text = svg.read_text(encoding="utf-8")
            font_families.update(re.findall(r"font-family: '([^']+)'", text))
            if numeric_bad.search(text):
                failures.append(f"nonfinite_svg_token::{kind}/{stem}")
            labels = ["".join(element.itertext()).strip() for element in tree.iter() if element.tag.endswith("text")]
            if any(label in {"A", "B", "C", "D", "E"} for label in labels):
                failures.append(f"uppercase_panel_tag::{kind}/{stem}")
            lower_count = sum(label in {"a", "b", "c", "d", "e"} for label in labels)
            panel_counts[f"{kind}/{stem}"] = lower_count
            if lower_count < 1:
                failures.append(f"missing_lowercase_panel_tag::{kind}/{stem}")
    if font_families != {"Arial"}:
        failures.append(f"font_family_set::{sorted(font_families)}")
    required_tables = sorted({table for *_, tables, _ in FIGURES for table in tables})
    for table in required_tables:
        if not (root / table).is_file():
            failures.append(f"missing_source_table::{table}")
    future_audit = json.loads((root / "audits" / "V31_FUTURE_STORAGE_FIGURE_TABLE_AUDIT.json").read_text(encoding="utf-8"))
    if future_audit.get("status") != "PASS":
        failures.append("future_storage_derived_table_audit_not_pass")
    subpanel_audit_path = root / "audits" / "V31R6_SUBPANEL_STRICT_QA.json"
    subpanel_audit = json.loads(subpanel_audit_path.read_text(encoding="utf-8")) if subpanel_audit_path.is_file() else {}
    if subpanel_audit.get("status") != "PASS" or subpanel_audit.get("subpanel_count") != 67:
        failures.append("strict_67_subpanel_qa_not_pass")
    map_dir = root / "metadata" / "map_compliance"
    map_audit_path = map_dir / "MAP_COMPLIANCE_AND_PROVENANCE.json"
    map_audit = json.loads(map_audit_path.read_text(encoding="utf-8")) if map_audit_path.is_file() else {}
    map_files = map_audit.get("files", {}) if isinstance(map_audit, dict) else {}
    map_hashes_pass = bool(map_files)
    for filename, expected_hash in map_files.items():
        path = map_dir / filename
        if not path.is_file() or sha256(path).upper() != str(expected_hash).upper():
            map_hashes_pass = False
            failures.append(f"map_asset_hash::{filename}")
    province_path = map_dir / "china_provinces.geojson"
    dash_path = map_dir / "nine_dash_line_geometry_only.geojson"
    taiwan_present = False
    dash_feature_count = 0
    if province_path.is_file():
        province_geojson = json.loads(province_path.read_text(encoding="utf-8"))
        province_names = {str(feature.get("properties", {}).get("name", "")) for feature in province_geojson.get("features", [])}
        taiwan_present = "台湾省" in province_names
    if dash_path.is_file():
        dash_geojson = json.loads(dash_path.read_text(encoding="utf-8"))
        dash_feature_count = len(dash_geojson.get("features", []))
    map_status_pass = map_audit.get("status") == "PASS" and map_audit.get("official_review_number") == "GS(2023)2767"
    if not map_status_pass:
        failures.append("map_compliance_status_not_pass")
    if not taiwan_present or dash_feature_count < 9:
        failures.append("taiwan_or_south_china_sea_geometry_missing")
    map_svg_paths = [
        root / "figures" / "main" / f"{stem}.svg"
        for stem in (
            "Fig1_inherited_storage_geography",
            "Fig2_equal_stock_unequal_spatial_value",
            "Fig3_compensatory_investment_cost",
            "Fig4_spatial_path_dependence",
            "Fig6_future_storage_correction_of_spatial_lockin",
            "Fig7_future_pathway_and_validation_boundaries",
        )
    ] + [
        root / "figures" / "supplementary" / f"{stem}.svg"
        for stem in ("FigS01_model_zone_network_inputs", "FigS05_rule_based_allocation_diagnostics")
    ]
    # Every map must retain the sea and frame colours in rendered SVG.  Land
    # and province borders can be alpha-composited or replaced by thematic
    # fills, so their invariant colours are verified in the shared renderer.
    required_rendered_map_tokens = {"#e3edf2", "#536169"}
    map_visual_hierarchy_pass = all(
        path.is_file() and required_rendered_map_tokens.issubset(set(re.findall(r"#[0-9a-fA-F]{6}", path.read_text(encoding="utf-8").lower())))
        for path in map_svg_paths
    )
    shared_map_renderer = (root / "reproducibility" / "V31" / "plot_spatial_legacy_figures.py").read_text(encoding="utf-8")
    map_visual_hierarchy_pass = map_visual_hierarchy_pass and all(
        token in shared_map_renderer for token in ('MAP_LAND_FACE = "#F4EFE4"', 'MAP_PROVINCE_EDGE = "#66757D"')
    )
    if not map_visual_hierarchy_pass:
        failures.append("map_visual_hierarchy_styles_missing")
    repro_dir = root / "reproducibility" / "V31"
    spatial_renderer = (repro_dir / "plot_spatial_legacy_figures.py").read_text(encoding="utf-8")
    future_renderer = (repro_dir / "plot_v20_publication_figures.py").read_text(encoding="utf-8")
    targetyear_renderer = (repro_dir / "plot_targetyear_sensitivity_figure.py").read_text(encoding="utf-8")
    full8760_renderer = (repro_dir / "plot_full8760_validation.py").read_text(encoding="utf-8")
    alignment_markers = (
        "Fig3d map/ranking", "Fig4a/Fig4c", "Fig4b/Fig4d",
        "Fig6a/Fig6c", "Fig6b/Fig6d", "Fig7a/Fig7c",
    )
    alignment_assertions_pass = all(
        marker in spatial_renderer + future_renderer for marker in alignment_markers
    )
    if not alignment_assertions_pass:
        failures.append("layout_alignment_assertions_missing")
    non_two_decimal_direct_format = re.compile(r":\+?\.(?:0|1|3|4|5|6|7|8|9)(?:f|%)")
    direct_label_precision_pass = not any(
        non_two_decimal_direct_format.search(text)
        for text in (spatial_renderer, future_renderer, targetyear_renderer, full8760_renderer)
    )
    if not direct_label_precision_pass:
        failures.append("direct_numeric_label_precision_not_two_decimals")
    checks = {
        "exact_7_main_and_14_supplementary_in_png_pdf_svg": not any("set_mismatch" in f for f in failures),
        "png_600dpi_and_publication_dimensions": not any(f.startswith("png_resolution") for f in failures),
        "valid_pdf_headers": not any(f.startswith("pdf_header") for f in failures),
        "valid_svg_xml": not any(f.startswith("svg_xml") for f in failures),
        "all_svg_text_arial": font_families == {"Arial"},
        "lowercase_panel_tags_only": not any("panel_tag" in f for f in failures),
        "no_nonfinite_svg_numeric_tokens": not any(f.startswith("nonfinite") for f in failures),
        "all_registered_source_tables_exist": not any(f.startswith("missing_source_table") for f in failures),
        "future_storage_26_case_table_audit_pass": future_audit.get("status") == "PASS",
        "strict_67_subpanel_semantic_visual_qa_pass": subpanel_audit.get("status") == "PASS" and subpanel_audit.get("subpanel_count") == 67,
        "official_standard_map_reference_and_hashes_pass": map_status_pass and map_hashes_pass,
        "taiwan_and_south_china_sea_geometry_present": taiwan_present and dash_feature_count >= 9,
        "map_sea_land_province_frame_visual_hierarchy_present": map_visual_hierarchy_pass,
        "fig3_fig4_fig6_fig7_frame_alignment_assertions_present": alignment_assertions_pass,
        "direct_numeric_annotations_use_two_decimal_places": direct_label_precision_pass,
    }
    return {"version": VERSION, "status": "PASS" if not failures else "FAIL", "checks_passed": sum(checks.values()), "checks_total": len(checks), "checks": checks, "failed": failures, "font_families": sorted(font_families), "panel_counts": panel_counts, "png_properties": dimensions, "map_compliance": {"official_review_number": map_audit.get("official_review_number"), "taiwan_present": taiwan_present, "south_china_sea_line_feature_count": dash_feature_count}}


def write_manifests(root: Path) -> None:
    figure_files = sorted((root / "figures").rglob("*"))
    figure_payload = []
    for path in figure_files:
        if not path.is_file():
            continue
        entry = {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}
        if path.suffix.lower() == ".png":
            with Image.open(path) as image:
                entry["pixels"] = list(image.size)
                entry["dpi"] = list(image.info.get("dpi", (0, 0)))
        figure_payload.append(entry)
    write_json(root / "FIGURE_OUTPUT_MANIFEST_SHA256_V31R6.json", {"version": VERSION, "file_count": len(figure_payload), "files": figure_payload})
    delivery_path = root / "DELIVERY_MANIFEST_SHA256_V31R6.json"
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != delivery_path:
            files.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json(delivery_path, {"version": VERSION, "manifest_scope": "all delivery files except this self-referential manifest", "file_count": len(files), "files": files})


def write_readme_and_captions(root: Path) -> None:
    readme = """# V31R6 投稿定稿成图、地图文字与严格对齐复核交付包

## 交付内容

- 主图 7 张（Fig1–Fig7），补充图 14 张（FigS01–FigS14）。
- 每张图均含 PDF、SVG、600 dpi PNG，共 63 个正式图文件。
- `tables/` 为成图使用的真实数据；`metadata/FIGURE_TO_REAL_DATA_MAP_V31.json` 给出逐图来源和 SHA256。
- `audits/V31R6_FIGURE_RELEASE_QA.json` 为最终文件、字体、图号、分辨率、来源表、术语与地图资产门控。
- `audits/V31R6_SUBPANEL_STRICT_QA.csv/json/md` 为 67 个子图的逐项重复、重叠、字体、密度和对齐审计。
- `metadata/map_compliance/` 保存自然资源部 GS(2023)2767 官方标准地图原始下载件、解析图件、绘图所用台湾/南海断续线几何和哈希审计。
- `audits/visual_qa/` 为全部 21 张图的最新接触表。
- `reproducibility/V31/` 为同一数据包上的重绘脚本。

## 统一版式

全部面板编号均为坐标轴外左上角的小写粗体 `a/b/c/d/e`；正文、图例、数学单位和面板编号均为 Arial。图例优先置于绘图区上方，地图引线只标注代表性位置，避免文字、点和图例相互遮挡。全国地图明确显示台湾，并以不含文字标签的独立附图显示南海断续线；台湾无模型数据时只作地理表示，不人工填值。

## 主线递进

1. Fig1：既有储能地理格局与需求错配。
2. Fig2：相同全国总量下，空间配置为何产生不同系统价值。
3. Fig3：系统通过成本、储能和非储能投资吸收空间错配。
4. Fig4：错配随规划期如何衰减、残留或反转。
5. Fig5：关键边界条件下结论是否稳健。
6. Fig6：2033 未来储能机会集如何补偿固定既有资产造成的空间锁定；不是移动或改造既有资产。
7. Fig7：未来储能建设的时间、技术、空间和情景响应，并以独立的全年逐小时可行性缺口明确验证边界。

## 科学边界

- 未来储能共有 8 + 16 + 2 = 26 个已求解配置，完整展示在 FigS14；Fig6/7只提炼不重复的主线信息。
- “最小附加技术中性平衡容量”是在原全年逐小时约束下，仅为诊断而加入并最小化的技术中性稳固供给容量与过剩吸收容量的全国总和。零值才表示未增广固定组合满足逐小时供需平衡；正值是可行性缺口的下界，不是实际建设量或经济成本。
- 2033 年度目标年成本与 2028–2058 年多期现值属于不同核算边界，不作加总。
- 扩展的压缩空气储能与氢储能配置用于检验技术边界，不作为省级选址主结论。
- 图表未改变任何上游输入、约束、目标函数、求解结果、数据值或色标范围。
- 官方标准图件作为地图合规参考保存；若期刊或公开发布机构要求对叠加后的专题地图重新送审，仍应按其流程取得相应审图号。

## 核验入口

- 最终成图门控：`audits/V31R6_FIGURE_RELEASE_QA.json`
- 67 子图严格门控：`audits/V31R6_SUBPANEL_STRICT_QA.json`
- 地图合规与来源：`metadata/map_compliance/MAP_COMPLIANCE_AND_PROVENANCE.json`
- 未来储能 26 案例派生表门控：`audits/V31_FUTURE_STORAGE_FIGURE_TABLE_AUDIT.json`
- 图—数据映射：`metadata/FIGURE_TO_REAL_DATA_MAP_V31.json`
- 科学合同：`metadata/POSTPROCESS_SCIENTIFIC_CONTRACT_V31.json`
- 图文件哈希：`FIGURE_OUTPUT_MANIFEST_SHA256_V31R6.json`
- 全包哈希：`DELIVERY_MANIFEST_SHA256_V31R6.json`
"""
    (root / "README_交付说明.md").write_text(readme, encoding="utf-8")
    captions = """# Figure captions

## Main figures

**Figure 1 | Inherited storage geography.** (a) Reconstructed provincial storage power; symbol area represents power and colour represents the reconstructed energy-to-power duration. (b) Provincial shares of inherited storage power plotted against shares of national coincident peak demand; colour gives the signed storage-share minus peak-share difference. (c) Lorenz curve and complementary concentration measures for the inherited fleet, including the top-five share, Herfindahl index and maximum provincial storage-to-peak ratio. (d) Counterfactual sequence that first standardizes duration while retaining provincial siting and then reallocates the same national power and energy totals. The no-inherited-storage, load-based and renewables-based configurations are transparent benchmarks and are not treated as observed assets.

**Figure 2 | Equal stock, unequal spatial value.** (a) Reconstructed standardized provincial allocation of the inherited fleet. (b) Cost-minimizing provincial allocation with the same national power, energy and common duration. (c) Signed optimized-minus-reconstructed power difference. (d) Provincial contributions to the equivalent spatial reallocation, defined as one-half of the sum of absolute provincial power differences; the total is 89.93 GW, or 66.16% of the fleet. (e) Present-value system benefit across the optimized allocation and five controlled benchmarks. Equal national stock therefore does not imply equal system value.

**Figure 3 | Compensatory investment and cost.** (a) Reconstructed-minus-optimized annual system-cost difference by component and planning period; the inset reports the aggregate present-value penalty. (b) Difference in new battery power. (c) Difference in non-storage generation capacity. (d) Provincial battery-power differences in 2028, with the largest absolute changes ranked below the map. The panels identify the investment channels through which the system accommodates inherited spatial misalignment under a common four-hour battery representation.

**Figure 4 | Spatial path dependence.** (a) Share of the initial power and energy mismatch remaining from the stock anchor through 2058. (b) Initial provincial power mismatch versus the residual mismatch in 2058. (c) Maps of the initial and residual provincial mismatches. (d) Classification of each inherited deficit or surplus as substantially corrected, partly corrected, sign-reversed, or persistent or amplified by 2058. Ribbon width represents the absolute mismatch used for classification and does not represent a physical transfer of capacity.

**Figure 5 | Robustness across boundary conditions.** (a) Present-value system-cost penalty under the reference assumptions and five alternative boundaries. (b) Reconstructed-minus-optimized battery-power response. (c) Corresponding battery-energy response. (d) Joint relationship between cost penalty and battery-energy response; marker area represents the absolute battery-power response. Pumped-storage hydropower (PSH) is evaluated through a conservative resource constraint. The signed investment responses can change direction even when the cost penalty remains positive.

**Figure 6 | Future storage correction of spatial lock-in in 2033.** (a) Provincial location, power and duration of new storage under the adaptive observed-siting configuration. (b) Optimized-minus-observed provincial reallocation for the matched adaptive configuration. (c) Observed and optimized national new-storage power for the baseline, adaptive, transmission-fixed adaptive and expanded boundary-condition configurations. (d) Equivalent spatial reallocation and residual annual location penalty for the same matched configurations. Future investment changes the location of new capacity around the inherited fleet; it does not relocate existing assets. The expanded configuration tests a wider technology boundary and is not used as the primary siting comparison.

**Figure 7 | Future pathway and hourly feasibility boundary.** The technology set includes lithium-ion batteries using lithium iron phosphate (LFP), vanadium redox-flow batteries (VRFB), PSH, compressed-air energy storage (CAES) and long-duration energy storage (LDES). (a) Timing and technology composition of new storage along the reference observed-siting pathway. (b) Observed-minus-optimized difference in build timing and technology. (c) Cumulative provincial difference in new storage power over 2028–2058. (d) Net capacity adaptation and present-value cost penalty across seven matched contexts. (e) Minimum additional technology-neutral balancing capacity required for four fixed 2033 portfolios under an unchanged full-year hourly chronology. The positive values in panel e quantify a feasibility gap; they are neither actual technology builds nor costs, and a value of zero alone would establish hourly feasibility without diagnostic balancing capacity.

## Supplementary figures

**Figure S1 | Model-zone inputs.** (a) Coincident peak demand. (b) Installed wind and solar capacity, used here as the variable renewable energy (VRE) indicator. (c) Ratio of inherited storage power to coincident peak demand. Symbol area is proportional to the mapped quantity; network connections and national cartographic context are held constant across panels.

**Figure S2 | Inherited power, energy and duration accounting.** (a) Provincial inherited energy versus power, coloured by reconstructed duration; the dashed line gives the national power-weighted mean duration of 2.58 h. (b) Independent accounting checks for zone coverage, common duration, duration spread and the energy identity after duration standardization.

**Figure S3 | Empirical deployment envelope.** (a) Inherited provincial storage power against coincident peak demand, with the 95th-percentile empirical envelope. (b) Optimized provincial allocation expressed as a percentage of that envelope. This envelope is an empirical plausibility diagnostic rather than an additional model constraint.

**Figure S4 | Scenario design matrix.** The matrix records the inherited-geography, duration, transmission, PSH, carbon-cap and battery-cost assumptions for all spatial counterfactuals. VRE and PSH follow the definitions above.

**Figure S5 | Rule-based allocation diagnostics.** (a,b) Provincial storage allocations under load-based and renewables-based rules. (c,d) Signed differences between each rule-based allocation and the optimized allocation. These heuristic rules provide transparent spatial benchmarks and are not interpreted as alternative optima.

**Figure S6 | Complete spatial reallocation and duration deltas.** (a) Optimized-minus-reconstructed storage-power difference for all model zones. (b) Difference between reconstructed inherited energy and the energy implied by the standardized common duration. Both panels retain the full provincial ordering rather than only the largest changes.

**Figure S7 | Period system-cost penalties.** Discounted period-specific cost penalties for reconstructed heterogeneous duration, reconstructed standardized duration, load-based allocation and renewables-based allocation, each measured against the optimized allocation.

**Figure S8 | Technology and curtailment adaptation.** (a) Reconstructed-minus-optimized capacity difference by non-battery technology and planning period. (b) Difference in curtailed electricity. (c) Difference in curtailment rate. The operational panels distinguish an energy-volume response from a percentage-point response.

**Figure S9 | Transmission reconfiguration.** (a) Largest corridor-level transmission-build differences, with direction and planning period retained. (b) Gross corridor reconfiguration and the net national transmission difference over time. Gross reconfiguration can remain substantial even when opposing corridor changes largely cancel nationally.

**Figure S10 | Final spatial reallocation.** (a) Largest signed optimized-minus-reconstructed provincial storage-power differences in 2058. (b) Cumulative share of absolute reallocation as zones are ranked by magnitude, including the top-five share and the number of zones required to reach 80%.

**Figure S11 | Extended robustness responses.** (a) Transmission-build response across six boundary conditions. (b) Final curtailment response. (c) Joint transmission-curtailment response; marker area represents the absolute battery-power response under the PSH resource constraint and other boundary conditions.

**Figure S12 | Chronology, long-duration storage and temporal-resolution sensitivities.** State of charge (SOC) is linked chronologically within each modeled year. (a) Annual location penalty for the 2028 and 2033 linked-SOC cases, the technology-specific LDES case and the one-hour temporal-resolution case. (b) Cost-component decomposition for the same four comparisons. (c) Material investment responses; metrics equal to zero in every configuration are omitted. (d) Curtailment, emissions and average-cost responses together with maximum SOC-linkage residuals and bound violations. The deployed options include CAES at 10 h and 24 h.

**Figure S13 | Full-year hourly feasibility-gap assessment.** (a) Minimum additional technology-neutral balancing capacity for four fixed 2033 portfolios. (b) Decomposition into firm-supply and surplus-absorption capacity. (c) Largest provincial contributions. (d) Availability and outcome of the optimality, feasibility, input-consistency and physical-quality checks. The metric is the minimum firm-supply plus surplus-absorption capacity required to restore hourly balance; positive values are diagnostic feasibility distances and not actual builds or costs. LDES denotes long-duration energy storage.

**Figure S14 | Future-storage evidence across 26 configurations.** Technology labels use LFP, VRFB, PSH and CAES as defined above; the expanded set also includes molecular-hydrogen (H₂) storage. (a) Total new storage power on a logarithmic scale. (b) Power-weighted duration. (c) Technology composition. (d) Build-timing composition. The same configurations and ordering are retained across all panels; annual 2033 configurations are distinguished from multi-period and equal-horizon pathways spanning 2028–2058. The expanded configuration is a boundary-condition scenario.
"""
    (root / "manuscript_ready_text" / "V31_FIGURE_CAPTIONS_AND_INTERPRETATION.md").write_text(captions, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    work = args.work.resolve()
    cleanup_stale_release_files(root)
    copy_reproducibility(root, work)
    write_registry_and_contract(root)
    write_readme_and_captions(root)
    main_pngs = [root / "figures" / "main" / f"{stem}.png" for _, kind, stem, *_ in FIGURES if kind == "main"]
    supp_pngs = [root / "figures" / "supplementary" / f"{stem}.png" for _, kind, stem, *_ in FIGURES if kind == "supplementary"]
    make_contact_sheet(main_pngs, root / "audits" / "visual_qa" / "CONTACT_SHEET_MAIN_7_V31R6.png")
    make_contact_sheet(supp_pngs[:7], root / "audits" / "visual_qa" / "CONTACT_SHEET_SUPPLEMENTARY_S01_S07_V31R6.png")
    make_contact_sheet(supp_pngs[7:], root / "audits" / "visual_qa" / "CONTACT_SHEET_SUPPLEMENTARY_S08_S14_V31R6.png")
    for stale in (root / "audits" / "visual_qa").glob("CONTACT_SHEET_*.png"):
        if "_V31R6" not in stale.stem:
            stale.unlink()
    qa = audit_figures(root)
    write_json(root / "audits" / "V31R6_FIGURE_RELEASE_QA.json", qa)
    if qa["status"] != "PASS":
        print(json.dumps(qa, ensure_ascii=False, indent=2))
        return 1
    write_manifests(root)
    print(json.dumps({"version": VERSION, "status": "PASS", "figures": 21, "formal_files": 63, "qa_checks": qa["checks_total"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
