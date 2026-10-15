#!/usr/bin/env python3
"""Static source audit for the integrated V17T5R6R8R5 postprocessor."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd

from v17t5_paths import AUDIT_DIR, SOURCE_ROOT


def main() -> None:
    postprocess = SOURCE_ROOT / "postprocess"
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    failures: list[str] = []
    for path in sorted(postprocess.glob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            failures.append(f"{path.name}: {exc}")
    add("all_python_sources_compile", not failures, ";".join(failures))

    registry_path = postprocess / "figure_output_registry_v17t5.csv"
    if registry_path.is_file():
        registry = pd.read_csv(registry_path)
        add("figure_registry_exact_17", len(registry) == 17 and not registry["figure_id"].duplicated().any(), f"rows={len(registry)}")
        add(
            "figure_registry_5_main_12_supplementary",
            int((registry.kind == "main").sum()) == 5 and int((registry.kind == "supplementary").sum()) == 12,
            registry.kind.value_counts().to_json(),
        )
        add("figure_registry_contains_figs12", set(registry.figure_id) >= {"FigS12"})
        fig12 = registry.loc[registry.figure_id.eq("FigS12")]
        add(
            "figs12_scope_is_targetyear_not_full_path",
            len(fig12) == 1
            and "single-target-year" in str(fig12.iloc[0].claim_scope)
            and "8760" in str(fig12.iloc[0].claim_scope),
        )
    else:
        add("figure_registry_exact_17", False, "missing")
        add("figure_registry_5_main_12_supplementary", False, "missing")
        add("figure_registry_contains_figs12", False, "missing")
        add("figs12_scope_is_targetyear_not_full_path", False, "missing")

    build_main = (postprocess / "build_spatial_legacy_tables.py").read_text(encoding="utf-8")
    plot_main = (postprocess / "plot_spatial_legacy_figures.py").read_text(encoding="utf-8")
    combined_main = build_main + "\n" + plot_main
    prohibited = [
        '"dispatch.csv"', "'dispatch.csv'", '"DispatchTx.csv"', "'DispatchTx.csv'",
        '"storage_operation_audit.csv"', "'storage_operation_audit.csv'",
        '"load_balance.csv"', "'load_balance.csv'",
    ]
    add("frozen_main_code_excludes_degeneracy_sensitive_operation", all(token not in combined_main for token in prohibited))
    add("exact_vre_technology_names_used", all(token in build_main for token in ["Wind_Onshore", "Wind_Offshore", "Solar_Distributed", "Solar_Utility"]))
    add("main_cost_components_close_to_annual_total", "component_closure_error_usd_per_yr" in build_main)
    add("main_spatial_persistence_uses_half_l1", "0.5 * float" in build_main and "power_half_l1_mw" in build_main)
    add("main_alluvial_not_physical_flow", "not a physical capacity flow" in plot_main)
    add("main_fixed_180mm_export", "7.0866" in plot_main)
    add("main_global_titles_removed", "suptitle(" not in plot_main and ".set_title(" not in plot_main)
    add("main_map_collision_control_present", "_place_nonoverlapping_map_labels" in plot_main and "box.overlaps" in plot_main)
    add("main_successful_baseline_regression_present", (postprocess / "audit_against_successful_baseline.py").is_file())
    add("main_scientific_audit_present", (postprocess / "audit_scientific_consistency.py").is_file())

    common = (postprocess / "targetyear_sensitivity_common.py").read_text(encoding="utf-8")
    preflight = (postprocess / "preflight_targetyear_sensitivity.py").read_text(encoding="utf-8")
    builder = (postprocess / "build_targetyear_sensitivity_tables.py").read_text(encoding="utf-8")
    audit = (postprocess / "audit_targetyear_sensitivity.py").read_text(encoding="utf-8")
    plot = (postprocess / "plot_targetyear_sensitivity_figure.py").read_text(encoding="utf-8")
    writer = (postprocess / "write_targetyear_manuscript_text.py").read_text(encoding="utf-8")
    runner = (postprocess / "run_v17t5_publication_postprocess.py").read_text(encoding="utf-8")
    validator = (postprocess / "validate_spatial_legacy_release.py").read_text(encoding="utf-8")
    paths = (postprocess / "v17t5_paths.py").read_text(encoding="utf-8")

    add("targetyear_exact_eight_scenarios_registered", all(name in common for name in [
        "TY2028_CHRONO_OBSERVED", "TY2028_CHRONO_OPTIMAL",
        "TY2033_CHRONO_OBSERVED", "TY2033_CHRONO_OPTIMAL",
        "TY2033_CHRONO_LDES_OBSERVED", "TY2033_CHRONO_LDES_OPTIMAL",
        "TY2033_CHRONO_1H_OBSERVED", "TY2033_CHRONO_1H_OPTIMAL",
    ]))
    add("targetyear_strict_optimality_gate", all(token in common for token in ["OPTIMAL", "FEASIBLE_POINT", "strict_export_pass"]))
    add(
        "targetyear_asymmetric_identity_sources_supported",
        all(token in common for token in [
            "def _identity_value_present", "status_present and config_present",
            "elif status_present", "elif config_present", "_identity_sources_json",
        ]),
    )
    add(
        "targetyear_identity_double_missing_hard_fails",
        "_identity_missing_fields" in common
        and "identity field missing from both solve_status and scenario_config" in common,
    )
    add(
        "targetyear_explicit_identity_conflict_hard_fails",
        "_scenario_config_identity_conflicts" in common
        and "solve_status/scenario_config identity conflict" in common,
    )
    add("targetyear_72_288_timepoint_scope_gate", "expected_timepoints" in common and "{4: 72, 1: 288}" in common)
    add("targetyear_full_8760_claim_rejected", "storage_full_chronological_claim_supported" in common and "must be false" in common)
    add("targetyear_transition_path_claim_rejected", "target_year_transition_path_claim_supported" in common and "must be false" in common)
    add("targetyear_cdr_exclusion_gate", all(token in common for token in ["allow_nbccs", "allow_daccs", "allow_beccs", "storage_cdr_modules_compiled"]))
    add("targetyear_physical_audit_gate", "physical_audit_summary.csv" in common and "physical_pass" in common)
    add("targetyear_chronology_audit_gate", "storage_chronology_audit.csv" in common and "max_abs_linkage_residual_mwh" in common)
    add("targetyear_pair_definition_observed_minus_optimized", "observed_minus_optimized" in builder and "pair_delta(observed, optimized" in builder)
    add("targetyear_signs_not_clipped", "sign_clipping_or_absolute_value_applied" in audit and "False" in audit)
    add("targetyear_ldes_isolation_audit", "targetyear_ldes_isolation_audit.json" in audit)
    add("targetyear_ldes_portfolio_coverage_audit", "targetyear_ldes_portfolio_coverage_audit.json" in audit)
    add("targetyear_one_hour_scope_audit", "targetyear_one_hour_scope_audit.json" in audit)
    add("targetyear_scope_separation_audit", "main_and_sensitivity_scope_separation_audit.json" in audit)
    add("targetyear_cost_recalculation_audit", "targetyear_cost_recalculation_audit.json" in audit)
    add("targetyear_cost_component_closure_audit", "targetyear_cost_component_closure_audit.csv" in audit)
    add("targetyear_soc_tolerance_not_relaxed", '"tolerance_mwh": 0.10' in audit or "tolerance_mwh\": 0.10" in audit)
    add("targetyear_figure_has_four_panels", all(token in plot for token in ['panel_label(axa, "a"', 'panel_label(axb, "b"', 'panel_label(axc, "c"', 'panel_label(axd, "d"']))
    add("targetyear_figure_uses_exact_labels_and_row_normalization", "maxabs" in plot and "observed_minus_optimized" in plot)
    add("targetyear_figure_omits_invariant_zero_rows", "invariant zero rows omitted" in plot and "no deployment in either member (0 GW)" in plot)
    add("targetyear_figure_fixed_180mm", "7.0866" in plot)
    add("targetyear_bilingual_text_generated", "targetyear_results_EN.md" in writer and "targetyear_results_ZH.md" in writer)
    add("targetyear_text_scope_lock", "not added to" in writer and "8760" in writer)

    add("distinct_targetyear_root_variable", "V17_TARGETYEAR_SENSITIVITY_ROOT" in paths and "TARGETYEAR_ROOT" in paths)
    add("transactional_runner_present", (postprocess / "run_v17t5_publication_postprocess.py").is_file())
    add("transactional_working_directory", ".__v17t5r6r8r5_working__" in runner and ".__previous__" in runner)
    add("runner_requires_two_distinct_upstreams", "--main-upstream-root" in runner and "--targetyear-upstream-root" in runner and "must be distinct directories" in runner)
    add("runner_does_not_modify_upstreams", "promote(working, final, previous)" in runner and "upstream_roots_distinct" in runner)
    for script in [
        "audit_v17t5_postprocess_source.py", "preflight_spatial_legacy_outputs.py", "build_spatial_legacy_tables.py",
        "audit_against_successful_baseline.py", "audit_scientific_consistency.py", "plot_spatial_legacy_figures.py",
        "preflight_targetyear_sensitivity.py", "build_targetyear_sensitivity_tables.py", "audit_targetyear_sensitivity.py",
        "plot_targetyear_sensitivity_figure.py", "write_targetyear_manuscript_text.py", "validate_spatial_legacy_release.py",
    ]:
        add(f"runner_pipeline_contains:{script}", script in runner)
    add("combined_release_exact_51_files", "len(actual_files) == 51" in validator and '"figure_formats_expected": 51' in validator)
    add("combined_release_requires_targetyear_audits", "targetyear_preflight_pass" in validator and "targetyear_scientific_pass" in validator)

    frame = pd.DataFrame(checks)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(AUDIT_DIR / "postprocess_source_audit.csv", index=False)
    summary = {
        "version": "V17T5R6R8R5",
        "checks": len(frame),
        "passed": int(frame["pass"].sum()),
        "all_pass": bool(frame["pass"].all()),
        "failed": frame.loc[~frame["pass"], "check"].tolist(),
    }
    (AUDIT_DIR / "postprocess_source_audit.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary["all_pass"]:
        print(frame.loc[~frame["pass"]].to_string(index=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
