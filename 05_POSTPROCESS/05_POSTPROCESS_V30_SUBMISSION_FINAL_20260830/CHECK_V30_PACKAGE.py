#!/usr/bin/env python3
"""Static release gate for the clean V30 four-root postprocessor."""
from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
STYLE_SHA256 = "a01c76b4e43487a5df249b02214cb12d147c370cbbc3430acbe48b0ee8c157f6"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-clean", action="store_true")
    args = parser.parse_args()
    checks: list[dict] = []
    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    required = [
        "README_00_FIRST_ZH.md", "README_ZH.md", "RUN_V30_POSTPROCESS.bat", "RUN_V30_POSTPROCESS.ps1",
        "RUN_ON_RESULT_COMPUTER_EDIT_PATHS.bat", "RUN_V30_BUILD_ALL_REAL_TABLES_AND_PACK.bat",
        "CHECK_V30_PACKAGE.bat", "INSTALL_V30_PYTHON_DEPS.bat",
        "requirements.txt", "postprocess/run_v30_publication_postprocess.py",
        "postprocess/build_v30_all_real_tables_bundle.py",
        "postprocess/preflight_v30_extended_results.py", "postprocess/build_full8760_validation_tables.py",
        "postprocess/plot_full8760_validation.py", "postprocess/build_v20_publication_tables.py",
        "postprocess/plot_v20_publication_figures.py", "postprocess/write_v30_manuscript_text.py",
        "postprocess/validate_v30_release.py", "postprocess/figure_output_registry_v30.csv",
        "postprocess/ne_style.py", "postprocess_assets/map_assets/china_provinces.geojson",
        "postprocess_assets/map_assets/nine_dash_line_geometry_only.geojson", "STYLE_INHERITANCE_AUDIT.json",
        "POSTPROCESS_SCIENTIFIC_CONTRACT_V30.json", "UPSTREAM_ALIGNMENT_AND_UNIT_AUDIT_V30.md",
        "UPSTREAM_ALIGNMENT_AND_UNIT_AUDIT_V30.json", "UPSTREAM_SOURCE_SCHEMA_CROSSCHECK_V30.json",
        "LAYOUT_QA_V30.json", "PACKAGE_MANIFEST_SHA256_V30.json",
    ]
    for relative in required:
        add(f"required:{relative}", (ROOT / relative).is_file())
    compile_dir = ROOT / "_compile_tmp_v30"
    shutil.rmtree(compile_dir, ignore_errors=True); compile_dir.mkdir()
    for source in sorted((ROOT / "postprocess").glob("*.py")):
        try:
            py_compile.compile(str(source), cfile=str(compile_dir / f"{source.stem}.pyc"), doraise=True)
            add(f"compile:{source.name}", True)
        except Exception as exc:
            add(f"compile:{source.name}", False, str(exc))
    shutil.rmtree(compile_dir, ignore_errors=True)
    add("style:byte_identical_to_0809", sha(ROOT / "postprocess/ne_style.py") == STYLE_SHA256)
    registry = pd.read_csv(ROOT / "postprocess/figure_output_registry_v30.csv")
    add("registry:7_main_14_supplementary", len(registry) == 21 and (registry.kind == "main").sum() == 7 and (registry.kind == "supplementary").sum() == 14)
    add("registry:unique_ids", not registry.figure_id.duplicated().any() and not registry.file_stem.duplicated().any())
    runner = (ROOT / "postprocess/run_v30_publication_postprocess.py").read_text(encoding="utf-8")
    for token in ("--main-upstream-root", "--targetyear-upstream-root", "--full8760-root", "--future-storage-root"):
        add(f"runner:{token}", token in runner)
    add("runner:read_only_claim", '"upstream_write_performed": False' in runner)
    full = (ROOT / "postprocess/build_full8760_validation_tables.py").read_text(encoding="utf-8")
    add("scope:full8760_distance_only", "forbidden_interpretations" in full and "actual technology build" in full and "electricity_cost" not in full)
    v20 = (ROOT / "postprocess/build_v20_publication_tables.py").read_text(encoding="utf-8")
    add("scope:v20_cost_bases_separate", "annual_cost" in v20 and "present_value" in v20)
    common = (ROOT / "postprocess/v30_common.py").read_text(encoding="utf-8")
    layer_a_adapter = common[
        common.index("def resolve_layer_a_output"):
        common.index("def _validate_v20_layer_a_hf5_lineage_if_present")
    ]
    add("lineage:v20_source_case_result_sha256", "validate_v20_result_fingerprint" in common and "solve_status_sha256" in common)
    add("gate:v20_strict_publication_revalidated", "strict_v20_status" in common and "stage1_official_release_pass" in common)
    add(
        "gate:gurobi_native_status_schema_aliases_remain_strict",
        'status_aliases = {"gurobi_status", "stage1_gurobi_status"}' in common
        and "expected native OPTIMAL status 2" in common
        and '"stage1_gurobi_status_gate_pass", "stage1_gurobi_objval_gate_pass"' in common
        and '"stage1_objective_scale_gate_pass"' in common,
    )
    add(
        "full8760:mixed_r24p1_r24p2_r24p3_certificate_routes_validated",
        "def validate_full8760_promoted_certificate" in common
        and "enhanced_route = full8760_enhanced_diagnostic_route(record, scenario)" in common
        and '"HF18P2_RESULT_FINGERPRINT.json"' in common
        and "validate_full8760_promoted_certificate" in full,
    )
    add(
        "full8760:robustness_system_isolated_from_economic_reoptimization",
        'payload.get("version") != "V17T2R6R24P3_HF18P2_COMBINED_ALL4"' in common
        and '"robustness_distance_only"' in common
        and '"_attempts", "attempts"' in common
        and '"economic_reoptimization_outputs_used": False' in full,
    )
    add(
        "full8760:all_versioned_diagnostics_are_route_aware",
        "def full8760_enhanced_diagnostic_route" in common
        and "def full8760_route_diagnostic_number" in common
        and "required R24P2+ diagnostic is missing" in common
        and '"gurobi_constr_residual", "gurobi_constr_sresidual"' in common
        and '"max_soc_bound_violation_mwh", "max_soc_bound_tolerance_ratio"' in common
        and '"gurobi_constr_sresidual_available"' in full
        and '"missing_values_filled_with_zero": False' in full,
    )
    extended = (ROOT / "postprocess/preflight_v30_extended_results.py").read_text(encoding="utf-8")
    add(
        "preflight:all_30_case_failures_are_diagnostic",
        extended.count('"failure": str(exc)') == 3
        and '"failed": [row for row in checks if not row["passed"]]' in extended
        and "see failed records above" in extended,
    )
    add(
        "lineage:v20_layer_a_missing_summary_row_from_promoted_only",
        "reconstructed_from_strict_promoted_output_missing_upstream_summary_row" in common
        and "resolve_layer_a_output(root, scenario)" in common
        and 'module / "future_correction_cases" / scenario' in common
        and "_attempts" not in layer_a_adapter,
    )
    add(
        "lineage:v20_hf5_exact_projection_revalidated",
        "def _validate_v20_layer_a_hf5_lineage_if_present" in common
        and "V20HF5_equivalent_reduced_formulation_v1" in common
        and "HF5_REDUCED_MODEL_RESULT_LINEAGE.json" in common
        and "projected_model_sha256" in common
        and "projected_runner_sha256" in common,
    )
    add("scope:zero_storage_is_valid", "no declared storage-build rows found" not in v20)
    baseline_audit = (ROOT / "postprocess/audit_against_successful_baseline.py").read_text(encoding="utf-8")
    add(
        "audit:zero_denominator_relative_difference_semantics",
        "allowed_undefined" in baseline_audit
        and 'name != "robustness"' in baseline_audit
        and 'denominator.abs().le(1e-12)' in baseline_audit
        and 'core = numeric.drop(columns=["relative_difference_fraction"])' in baseline_audit,
    )
    consistency_audit = (ROOT / "postprocess/audit_scientific_consistency.py").read_text(encoding="utf-8")
    add(
        "audit:battery_robustness_direction_not_preconstrained",
        'f"{metric}_finite_in_all_contexts"' in consistency_audit
        and 'if metric == "cumulative_system_cost_pv_usd"' in consistency_audit
        and 'future_battery_build_mw_positive_in_all_contexts' not in consistency_audit,
    )
    spatial_plot = (ROOT / "postprocess/plot_spatial_legacy_figures.py").read_text(encoding="utf-8")
    targetyear_common = (ROOT / "postprocess/targetyear_sensitivity_common.py").read_text(encoding="utf-8")
    targetyear_preflight = (ROOT / "postprocess/preflight_targetyear_sensitivity.py").read_text(encoding="utf-8")
    add(
        "targetyear:headerless_ldes_empty_only_when_disabled",
        "def ldes_proxy_frame" in targetyear_common
        and "except pd.errors.EmptyDataError" in targetyear_common
        and "if scenario in LDES_SCENARIOS" in targetyear_common
        and "enabled-LDES export has no header or candidate rows" in targetyear_common
        and "disabled-LDES scenario unexpectedly exported" in targetyear_common,
    )
    add(
        "targetyear:ldes_export_semantics_preflighted",
        "ldes_proxy_frame," in targetyear_preflight
        and '"ldes_proxy_rows": ldes_proxy_rows' in targetyear_preflight
        and '"ldes_export_failures": ";".join(ldes_export_failures)' in targetyear_preflight,
    )
    add(
        "targetyear:strict_native_status_and_promoted_lineage_revalidated",
        '"stage1_gurobi_status_gate_pass"' in targetyear_common
        and '"stage1_gurobi_objval_gate_pass"' in targetyear_common
        and '"stage1_native_solver_certificate_pass"' in targetyear_common
        and "def validate_result_lineage" in targetyear_preflight
        and '"PUBLICATION_RESULT_LINEAGE.json"' in targetyear_preflight
        and "reconstructed_from_strict_summary_case_source_and_promoted_outputs" in targetyear_preflight
        and '"attempt_directories_consulted": False' in targetyear_preflight,
    )
    add(
        "plot:signed_battery_contrast_uses_absolute_marker_magnitude",
        'power_magnitude=wide["future_battery_build_mw"].abs()' in spatial_plot,
    )
    add(
        "plot:duration_point_mass_uses_no_artificial_bins",
        "def _duration_histogram" in spatial_plot
        and "resolution = 64.0 * np.finfo(float).eps * scale" in spatial_plot
        and 'axis.vlines(center, 0.0, len(numeric)' in spatial_plot
        and 'not np.isfinite(numeric).all()' in spatial_plot,
    )
    add("path:admin_desktop_default", "C:\\Users\\Admin\\Desktop" in (ROOT / "RUN_ON_RESULT_COMPUTER_EDIT_PATHS.bat").read_text(encoding="utf-8"))
    ps_runner = (ROOT / "RUN_V30_POSTPROCESS.ps1").read_text(encoding="utf-8")
    add("runtime:python_candidate_objects_not_flattened", "[pscustomobject]" in ps_runner and "$spec.Exe" in ps_runner and "$spec.Args" in ps_runner)
    add("runtime:python_version_probe_exits_cleanly", "sys.exit(1) if sys.version_info < (3,10) else print(sys.executable)" in ps_runner and "raise SystemExit(1) if" not in ps_runner)
    data_bundle = (ROOT / "postprocess/build_v30_all_real_tables_bundle.py").read_text(encoding="utf-8")
    bundle_entry = (ROOT / "RUN_V30_BUILD_ALL_REAL_TABLES_AND_PACK.bat").read_text(encoding="utf-8")
    add(
        "bundle:all_five_table_groups_and_21_figure_map",
        'expected_directories = ["main", "supplementary", "targetyear_sensitivity", "full8760_validation", "future_storage"]' in data_bundle
        and 'if len(registry) != 21' in data_bundle
        and 'FIGURE_TO_REAL_DATA_MAP_V30.json' in data_bundle,
    )
    add(
        "bundle:read_only_audited_four_root_lineage",
        '\"upstream_write_performed\": False' in data_bundle
        and '\"case_sets\": {\"main\": 16, \"targetyear\": 8, \"full8760\": 4, \"v20\": 26}' in data_bundle
        and 'check_upstream_source_fingerprints.py' in data_bundle
        and 'V30_ALL_REAL_TABLES_BUNDLE_MANIFEST.json' in data_bundle,
    )
    add(
        "bundle:data_only_no_plot_stage",
        "plot_spatial_legacy_figures.py" not in data_bundle
        and "plot_targetyear_sensitivity_figure.py" not in data_bundle
        and "plot_full8760_validation.py" not in data_bundle
        and "plot_v20_publication_figures.py" not in data_bundle,
    )
    add(
        "bundle:single_command_and_fixed_desktop_output",
        'call "%~dp0CHECK_V30_PACKAGE.bat"' in bundle_entry
        and 'sys.version_info ^< (3,10)' in bundle_entry
        and 'postprocess\\build_v30_all_real_tables_bundle.py' in bundle_entry
        and 'C:\\Users\\Admin\\Desktop\\V30_ALL_REAL_TABLES_AND_AUDITS_20260830.zip' in bundle_entry,
    )
    generated = [path for path in (ROOT / "postprocess_outputs").rglob("*") if path.is_file() and path.name != ".gitkeep"]
    add("release:outputs_clean" if args.release_clean else "outputs:clean_or_runtime", not generated if args.release_clean else True,
        ";".join(str(path) for path in generated[:5]))
    add("clean:no_pycache", not any(ROOT.rglob("__pycache__")))
    manifest_path = ROOT / "PACKAGE_MANIFEST_SHA256_V30.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            declared = {str(row["path"]): row for row in manifest["files"]}
            excluded_names = {"PACKAGE_MANIFEST_SHA256_V30.json", "STATIC_PACKAGE_CHECK_RESULT_V30.json"}
            actual = {
                path.relative_to(ROOT).as_posix(): path
                for path in ROOT.rglob("*")
                if path.is_file()
                and path.name not in excluded_names
                and "postprocess_outputs" not in path.relative_to(ROOT).parts
                and "__pycache__" not in path.relative_to(ROOT).parts
            }
            add("manifest:exact_file_set", set(actual) == set(declared),
                f"extra={sorted(set(actual)-set(declared))};missing={sorted(set(declared)-set(actual))}")
            bad = [name for name, row in declared.items()
                   if name not in actual or actual[name].stat().st_size != int(row["bytes"]) or sha(actual[name]) != str(row["sha256"]).lower()]
            add("manifest:all_hashes_and_sizes", not bad, ";".join(bad[:10]))
            actual_payload = sum(path.stat().st_size for path in actual.values())
            add(
                "manifest:declared_count_and_payload",
                int(manifest.get("file_count", -1)) == len(actual)
                and int(manifest.get("payload_bytes", -1)) == actual_payload,
                f"declared_count={manifest.get('file_count')};actual_count={len(actual)};"
                f"declared_payload={manifest.get('payload_bytes')};actual_payload={actual_payload}",
            )
            actual_max_path = max((len(name) for name in actual), default=0)
            add(
                "manifest:declared_max_relative_path",
                int(manifest.get("max_relative_path_chars", -1)) == actual_max_path,
                f"declared={manifest.get('max_relative_path_chars')};actual={actual_max_path}",
            )
        except Exception as exc:
            add("manifest:valid_json", False, repr(exc))
    else:
        add("manifest:present", False)
    passed = all(row["passed"] for row in checks)
    report = {"version": "V30_POSTPROCESS_SUBMISSION_20260830", "status": "PASS" if passed else "FAIL",
              "checks_passed": sum(row["passed"] for row in checks), "checks_total": len(checks),
              "failed": [row for row in checks if not row["passed"]]}
    (ROOT / "STATIC_PACKAGE_CHECK_RESULT_V30.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
