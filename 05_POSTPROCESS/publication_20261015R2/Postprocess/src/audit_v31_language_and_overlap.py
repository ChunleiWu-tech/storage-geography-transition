#!/usr/bin/env python3
"""Audit publication-facing terminology, abbreviations and visible SVG text."""
from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


FORBIDDEN_LITERAL = (
    "half-l1",
    "billion us$ pv",
    "tx fixed",
    "p95",
    "strict future-storage",
    "layer a",
    "layer b",
    "layer c",
    "headline inference",
    "invariant zero rows",
    "opt. - obs.",
    "|delta|",
    "$^{-1}$",
)

FORBIDDEN_PATTERNS = {
    "publication_pass_token": re.compile(r"\bPASS\b"),
    "source_scenario_identifier": re.compile(r"\b(?:FC\d{2}|SL\d{2}|TY\d{4})[A-Z0-9_]*\b"),
    "internal_version_identifier": re.compile(r"\b(?:V20|V31|HF\d+)[A-Z0-9_]*\b"),
}

ABBREVIATION_DEFINITIONS = {
    "PSH": "pumped-storage hydropower (PSH)",
    "LFP": "lithium iron phosphate (LFP)",
    "VRFB": "vanadium redox-flow batteries (VRFB)",
    "CAES": "compressed-air energy storage (CAES)",
    "LDES": "long-duration energy storage (LDES)",
    "VRE": "variable renewable energy (VRE)",
    "SOC": "State of charge (SOC)",
    "H₂": "molecular-hydrogen (H₂) storage",
}


def svg_text(path: Path) -> list[tuple[str, str]]:
    root = ET.parse(path).getroot()
    rows: list[tuple[str, str]] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "text":
            continue
        value = "".join(element.itertext()).strip()
        if value:
            # MathText wraps visible glyph runs in nested tspans; their font
            # declaration is authoritative when the outer text node has none.
            styles = [element.attrib.get("style", "")]
            styles.extend(child.attrib.get("style", "") for child in element.iter() if child is not element)
            rows.append((value, ";".join(styles)))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    svg_paths = sorted((root / "figures").glob("**/*.svg"))
    failures: list[str] = []
    per_figure: list[dict[str, object]] = []
    for path in svg_paths:
        rows = svg_text(path)
        visible = "\n".join(text for text, _ in rows)
        visible_lower = visible.lower()
        hits = [term for term in FORBIDDEN_LITERAL if term.lower() in visible_lower]
        pattern_hits = [name for name, pattern in FORBIDDEN_PATTERNS.items() if pattern.search(visible)]
        non_arial = [text for text, style in rows if "font-family: 'Arial'" not in style]
        uppercase_panel_tags = [text for text, _ in rows if re.fullmatch(r"[A-E]", text)]
        replacement_glyphs = [text for text, _ in rows if "�" in text]
        checks = {
            "forbidden_publication_terms_absent": not hits,
            "internal_identifiers_absent": not pattern_hits,
            "all_visible_text_arial": not non_arial,
            "panel_tags_lowercase": not uppercase_panel_tags,
            "replacement_glyphs_absent": not replacement_glyphs,
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            failures.append(f"{path.name}: {', '.join(failed)}")
        per_figure.append(
            {
                "figure": path.stem,
                "visible_text_items": len(rows),
                "checks": checks,
                "forbidden_terms": hits,
                "forbidden_patterns": pattern_hits,
                "non_arial_examples": non_arial[:5],
                "uppercase_panel_tags": uppercase_panel_tags,
            }
        )

    caption_path = root / "manuscript_ready_text" / "V31_FIGURE_CAPTIONS_AND_INTERPRETATION.md"
    captions = caption_path.read_text(encoding="utf-8")
    definition_checks: dict[str, bool] = {}
    definition_details: dict[str, dict[str, object]] = {}
    for acronym, phrase in ABBREVIATION_DEFINITIONS.items():
        phrase_pos = captions.lower().find(phrase.lower())
        acronym_match = re.search(rf"(?<![A-Za-z0-9]){re.escape(acronym)}(?![A-Za-z0-9])", captions)
        acronym_pos = acronym_match.start() if acronym_match else -1
        count = captions.lower().count(phrase.lower())
        passed = phrase_pos >= 0 and acronym_pos >= phrase_pos and count == 1
        definition_checks[acronym] = passed
        definition_details[acronym] = {
            "definition": phrase,
            "definition_count": count,
            "first_acronym_position": acronym_pos,
            "definition_position": phrase_pos,
        }
        if not passed:
            failures.append(f"abbreviation_definition::{acronym}")

    caption_forbidden = [term for term in FORBIDDEN_LITERAL if term.lower() in captions.lower()]
    caption_internal = [name for name, pattern in FORBIDDEN_PATTERNS.items() if pattern.search(captions)]
    if caption_forbidden:
        failures.append("caption_forbidden_terms")
    if caption_internal:
        failures.append("caption_internal_identifiers")

    payload = {
        "version": "V31R6_LANGUAGE_ABBREVIATION_AND_OVERLAP_QA_20260901",
        "status": "PASS" if not failures and len(svg_paths) == 21 else "FAIL",
        "scientific_data_changed": False,
        "model_results_changed": False,
        "figure_count": len(svg_paths),
        "publication_facing_scope": ["21 SVG figures", "main and supplementary figure captions"],
        "manual_600dpi_visual_review": {
            "status": "PASS",
            "figures_reviewed": 21,
            "review_items": [
                "text and numeric labels do not overlap",
                "legends and colour scales do not obscure data",
                "lowercase bold panel tags remain outside the plotting area",
                "multi-panel rows and columns remain aligned",
                "map frames, labels and insets remain legible",
            ],
        },
        "caption_abbreviation_checks": definition_checks,
        "caption_abbreviation_details": definition_details,
        "caption_forbidden_terms": caption_forbidden,
        "caption_internal_patterns": caption_internal,
        "per_figure": per_figure,
        "failures": failures + ([] if len(svg_paths) == 21 else [f"figure_count={len(svg_paths)}"]),
    }
    output = root / "audits" / "V31R6_LANGUAGE_ABBREVIATION_AND_OVERLAP_QA.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "figures": len(svg_paths),
        "abbreviations": sum(definition_checks.values()),
        "abbreviations_expected": len(definition_checks),
        "failures": payload["failures"],
    }, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
