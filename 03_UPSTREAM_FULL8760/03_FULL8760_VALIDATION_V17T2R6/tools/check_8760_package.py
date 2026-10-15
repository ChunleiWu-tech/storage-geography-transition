#!/usr/bin/env python3
"""Static release QA for the standalone V17T2R6 full-8760 module."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    checks: list[dict] = []

    def add(name: str, passed: bool, detail) -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    required = [
        "README_ZH.md", "README_EN.md", "VERSION_V17T2R6_FULL8760.txt",
        "RELEASE_NOTES_V17T2R6R7.md", "RELEASE_NOTES_V17T2R6R7_HF2.md",
        "RELEASE_NOTES_V17T2R6R7_HF2P1.md", "RELEASE_NOTES_V17T2R6R7_HF2P2.md",
        "RUN_V17T2R6_8760_OBSERVED_ONLY_HF2P1.bat",
        "CHECK_V17T2R6R7_HF2P1_PATCH.bat", "HF2P1_PATCH_MANIFEST_SHA256.json",
        "PREPARE_V17T2R6_8760_CASES.bat", "RUN_V17T2R6_8760_ALL_4_2x10.bat",
        "RUN_V17T2R6_8760_CORE_PAIR_2x10.bat", "RUN_V17T2R6_8760_LDES_PAIR_2x10.bat",
        "RUN_V17T2R6_8760_CLEAN_REBUILD_AND_RUN_ALL_4_2x10.bat",
        "FINALIZE_V17T2R6_8760_RESULTS.bat",
        "CHECK_V17T2R6_8760_SOURCE_GATE.bat", "CHECK_V17T2R6_8760_PREFLIGHT.bat",
        "CHECK_V17T2R6_8760_PARALLEL_SCHEDULER.bat", "tools/check_parallel_scheduler.py",
        "audits/V17T2R6R7_PARALLEL_SCHEDULER_AUDIT.json",
        "BUILD_V17T2R6_8760_SUMMARY.bat",
        "base_model_v39/cheer_power_storage_targetyear_v17t2r6_8760.jl",
        "data/raw/load/figshare_29832701_Data_output.xlsx",
        "data/processed/figshare_load_2024_31province_8760_nonleap.csv",
        "tools/build_8760_package_manifest.py",
        "tools/verify_8760_package_manifest.py",
        "tools/verify_hf2p1_patch.py",
        "audits/V17T2R6R7_RELEASE_DELTA_AUDIT.json",
        "CHECK_V17T2R6_8760_JULIA_STATIC.bat",
    ]
    missing = [rel for rel in required if not (ROOT / rel).is_file()]
    add("required_release_files", not missing, missing)

    python_errors = []
    for path in sorted((ROOT / "tools").glob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            python_errors.append(f"{path.name}: {exc}")
    add("python_syntax", not python_errors, python_errors if python_errors else "all tools parsed")

    caches = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.name == "__pycache__" or p.suffix.lower() in {".pyc", ".pyo"}]
    add("no_python_cache", not caches, caches)
    generated_state = []
    for name in ("batch_logs", "failed_diagnostics", "sensitivity_outputs"):
        if (ROOT / name).exists():
            generated_state.append(name)
    generated_state.extend(p.relative_to(ROOT).as_posix() for p in ROOT.glob("sensitivity_cases/*/outputs") if p.exists())
    release_junk = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.name in {".DS_Store", "Thumbs.db"}]
    add("no_generated_release_state", not generated_state, generated_state)
    add("no_platform_junk", not release_junk, release_junk)

    manifest_builder = (ROOT / "tools" / "build_8760_package_manifest.py").read_text(encoding="utf-8")
    manifest_verifier = (ROOT / "tools" / "verify_8760_package_manifest.py").read_text(encoding="utf-8")
    manifest_scope_tokens = [
        '"sensitivity_cases"',
        '"storage_runner/prepared_8760_cases_index.csv"',
        '"audits/PUBLICATION_SOURCE_FINGERPRINT.json"',
        '"V17T2R6R7_HF2P2_FULL8760"',
    ]
    add(
        "hf2p2_immutable_manifest_scope",
        all(token in manifest_builder and token in manifest_verifier for token in manifest_scope_tokens)
        and "UNTRACKED_IMMUTABLE_FILE" in manifest_verifier,
        [token for token in manifest_scope_tokens if token not in manifest_builder or token not in manifest_verifier],
    )

    # R7-HF1: preflight-generated JSON reports are part of the immutable release
    # manifest. Their writers must force LF explicitly so rerunning checks on
    # Windows does not change byte sizes/hashes solely through CRLF translation.
    lf_writer_scripts = [
        "tools/check_parallel_scheduler.py",
        "tools/check_julia_8760_static.py",
        "tools/check_8760_package.py",
        "tools/publication_source_gate.py",
        "tools/audit_targetyear_pair_identity.py",
        "tools/build_8760_package_manifest.py",
        "tools/normalize_release_audit_paths.py",
    ]
    lf_missing = []
    for rel in lf_writer_scripts:
        body = (ROOT / rel).read_text(encoding="utf-8")
        if 'newline="\\n"' not in body:
            lf_missing.append(rel)
    add("preflight_audit_writers_force_platform_independent_lf", not lf_missing, lf_missing)

    scenarios = pd.read_csv(ROOT / "storage_runner" / "scenarios_targetyear_linked.csv")
    expected = {
        "TY2033_FULL8760_OBSERVED", "TY2033_FULL8760_OPTIMAL",
        "TY2033_FULL8760_LDES_OBSERVED", "TY2033_FULL8760_LDES_OPTIMAL",
    }
    actual = set(scenarios["scenario"].astype(str))
    add("four_scenarios_exact", actual == expected and len(scenarios) == 4, sorted(actual))
    expected_order = [
        "TY2033_FULL8760_OBSERVED", "TY2033_FULL8760_OPTIMAL",
        "TY2033_FULL8760_LDES_OBSERVED", "TY2033_FULL8760_LDES_OPTIMAL",
    ]
    add("scenario_registry_pairwise_wave_order", list(scenarios["scenario"].astype(str)) == expected_order, list(scenarios["scenario"].astype(str)))
    case_dirs = {path.name for path in (ROOT / "sensitivity_cases").iterdir() if path.is_dir()}
    add("clean_case_directory_scope", case_dirs == expected, sorted(case_dirs))
    expected_templates = {
        "TY2033_CHRONO_OBSERVED", "TY2033_CHRONO_OPTIMAL",
        "TY2033_CHRONO_LDES_OBSERVED", "TY2033_CHRONO_LDES_OPTIMAL",
    }
    template_dirs = {path.name for path in (ROOT / "template_cases_4h").iterdir() if path.is_dir()}
    add("four_frozen_templates_exact", template_dirs == expected_templates, sorted(template_dirs))
    add("full_year_mode_only", set(scenarios["storage_chronology_mode"].astype(str)) == {"full_year_cyclic"}, sorted(scenarios["storage_chronology_mode"].unique()))

    # Directly re-read the frozen prepared temporal inputs rather than trusting
    # only previously generated validation JSON. This is a lightweight release
    # regression for the exact underscore timestamp format and 8760 continuity.
    temporal_runtime_contract = {}
    for scenario in sorted(expected):
        inputs = ROOT / "sensitivity_cases" / scenario / "inputs"
        try:
            tsdf = pd.read_csv(inputs / "timeseries.csv")
            tpdf = pd.read_csv(inputs / "timepoints.csv")
            stamps = pd.to_datetime(tpdf["timestamp"], format="%Y-%m-%d_%H:%M", errors="raise")
            steps = stamps.diff().dropna()
            key_match = set(tpdf["timeseries"].astype(str)) == set(tsdf["TIMESERIES"].astype(str))
            ok = bool(
                len(tsdf) == 12
                and len(tpdf) == 8760
                and tpdf["timepoint_id"].astype(str).nunique() == 8760
                and stamps.nunique() == 8760
                and steps.eq(pd.Timedelta(hours=1)).all()
                and stamps.iloc[0].month == 1 and stamps.iloc[0].day == 1 and stamps.iloc[0].hour == 0
                and stamps.iloc[-1].month == 12 and stamps.iloc[-1].day == 31 and stamps.iloc[-1].hour == 23
                and key_match
            )
            temporal_runtime_contract[scenario] = {
                "pass": ok, "rows": len(tpdf), "timeseries": len(tsdf),
                "first": str(stamps.iloc[0]), "last": str(stamps.iloc[-1]),
                "timeseries_key_match": key_match,
            }
        except Exception as exc:
            temporal_runtime_contract[scenario] = {"pass": False, "error": str(exc)}
    add("direct_full8760_temporal_runtime_contract", all(v.get("pass") for v in temporal_runtime_contract.values()), temporal_runtime_contract)

    validation_status = {}
    chronology_claims = {}
    for scenario in sorted(expected):
        path = ROOT / "sensitivity_cases" / scenario / "audits" / "FULL8760_PREPARED_INPUT_VALIDATION.json"
        status = json.loads(path.read_text(encoding="utf-8")).get("status") if path.is_file() else "MISSING"
        validation_status[scenario] = status
        meta_path = ROOT / "sensitivity_cases" / scenario / "SENSITIVITY_SCENARIO_META.json"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            nested = meta.get("target_year_pruning_audit", {})
            chronology_claims[scenario] = {
                "top_level": meta.get("full_8760_hour_claim_supported"),
                "nested": nested.get("full_8760_hour_claim_supported"),
                "hourly_timepoints": nested.get("hourly_timepoints"),
                "old_four_hour_key_present": "four_hour_timepoints" in nested,
                "old_template_file_counts_present": "files" in nested,
                "template_audit_separated": isinstance(meta.get("four_hour_template_pruning_audit"), dict),
            }
        else:
            chronology_claims[scenario] = {"missing": True}
    add("all_prepared_cases_validated", set(validation_status.values()) == {"PASS"}, validation_status)
    add(
        "chronology_metadata_consistent",
        all(
            value.get("top_level") is True
            and value.get("nested") is True
            and value.get("hourly_timepoints") == 8760
            and value.get("old_four_hour_key_present") is False
            and value.get("old_template_file_counts_present") is False
            and value.get("template_audit_separated") is True
            for value in chronology_claims.values()
        ),
        chronology_claims,
    )
    pair_path = ROOT / "audits" / "V17T2R6_FULL8760_PAIR_IDENTITY_AUDIT.json"
    pair_status = json.loads(pair_path.read_text(encoding="utf-8")).get("status") if pair_path.is_file() else "MISSING"
    add("pair_identity", pair_status == "PASS", pair_status)

    model = (ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl").read_text(encoding="utf-8")
    tokens = [
        '"full_year_cyclic"', "FULL_YEAR_TPS_IN_PERIOD", "tp_previous_commit = copy(tp_previous)",
        "cyclic_closure_residual_mwh", "representative_timepoint_count_expected", "8760",
    ]
    add("full8760_model_tokens", all(token in model for token in tokens), [t for t in tokens if t not in model])
    postsolve_marker = "# post-solve treat and export of results"
    postsolve = model[model.index(postsolve_marker):] if postsolve_marker in model else ""
    postsolve_lookup_tokens = [
        "postsolve_storage_gen_tps_lookup = Set(STORAGE_GEN_TPS)",
        "postsolve_storage_gens_lookup = Set(STORAGE_GENS)",
        "postsolve_prr_timepoints_lookup = Set(PRR_TIMEPOINTS)",
    ]
    slow_postsolve_membership_tokens = [
        "(g, t) in STORAGE_GEN_TPS) ?",
        "if (g, t) in STORAGE_GEN_TPS",
        "!((g, t) in STORAGE_GEN_TPS)",
        "((prr, t) in PRR_TIMEPOINTS)",
    ]
    add(
        "hf2p1_postsolve_lookup_acceleration",
        bool(postsolve)
        and all(token in postsolve for token in postsolve_lookup_tokens)
        and not any(token in postsolve for token in slow_postsolve_membership_tokens),
        {
            "missing_lookup_tokens": [token for token in postsolve_lookup_tokens if token not in postsolve],
            "slow_membership_hits": [token for token in slow_postsolve_membership_tokens if token in postsolve],
        },
    )
    add(
        "postsolve_export_uses_runtime_timepoint_count",
        "REPRESENTATIVE_TIMEPOINT_COUNT_EXPECTED" not in model
        and ":representative_timepoint_count_expected => [representative_timepoint_count_expected]" in model,
        {
            "unsafe_uppercase_global_present": "REPRESENTATIVE_TIMEPOINT_COUNT_EXPECTED" in model,
            "safe_runtime_local_present": ":representative_timepoint_count_expected => [representative_timepoint_count_expected]" in model,
        },
    )
    unsafe_inline_sort = "sort!(tps, by = t -> (tp_timestamp_parsed[t]" in model or "sort!(tps; by = t -> (tp_timestamp_parsed[t]" in model
    safe_inline_sort_tokens = [
        "keyed = Tuple{DateTime,Int,Any}[]",
        "sort!(keyed; by = item -> (item[1], item[2]), alg = Base.Sort.MergeSort)",
        "TPS_IN_TS[ts] = Any[item[3] for item in keyed]",
    ]
    add(
        "active_timepoint_sort_avoids_inline_string_dispatch",
        not unsafe_inline_sort and all(token in model for token in safe_inline_sort_tokens),
        {"unsafe_direct_sort": unsafe_inline_sort, "missing_safe_tokens": [t for t in safe_inline_sort_tokens if t not in model]},
    )
    solver_budget_tokens = [
        "V17T2R6_PRIMARY_BAR_ITER_LIMIT",
        "V17T2R6_FALLBACK_BAR_ITER_LIMIT",
        'get(ENV, "V17T2R6_8760_PRIMARY_BAR_ITER_LIMIT", "100000")',
        'get(ENV, "V17T2R6_8760_FALLBACK_BAR_ITER_LIMIT", "100000")',
        "bar_iter_limit = V17T2R6_PRIMARY_BAR_ITER_LIMIT",
        "bar_iter_limit = V17T2R6_FALLBACK_BAR_ITER_LIMIT",
    ]
    add("full8760_extended_barrier_budget", all(token in model for token in solver_budget_tokens), [t for t in solver_budget_tokens if t not in model])
    runner = (ROOT / "storage_runner" / "run_targetyear_one.jl").read_text(encoding="utf-8")
    add("runner_uses_v17t2r6_model", "cheer_power_storage_targetyear_v17t2r6_8760.jl" in runner, "runner include")
    static_audit_path = ROOT / "audits" / "V17T2R6_8760_JULIA_STATIC_AUDIT.json"
    static_audit = json.loads(static_audit_path.read_text(encoding="utf-8")) if static_audit_path.is_file() else {}
    add(
        "julia_static_audit_current",
        static_audit.get("status") == "PASS"
        and static_audit.get("model_sha256") == sha256(ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl")
        and static_audit.get("runner_sha256") == sha256(ROOT / "storage_runner" / "run_targetyear_one.jl")
        and static_audit.get("runtime_checker_sha256") == sha256(ROOT / "storage_runner" / "check_v17t2r6_8760_runtime.jl"),
        static_audit.get("status", "MISSING"),
    )
    static_checks = {item.get("check"): item for item in static_audit.get("checks", [])}
    hf2_code = static_checks.get("hf2_exact_projection_code_contract", {})
    hf2_proof = static_checks.get("hf2_exact_projection_input_proof", {})
    add(
        "hf2_exact_projection_reduction_current_and_proven",
        static_audit.get("version") == "V17T2R6R7_HF2P1_FULL8760"
        and hf2_code.get("pass") is True
        and hf2_proof.get("pass") is True,
        {
            "static_audit_version": static_audit.get("version"),
            "code_contract": hf2_code.get("pass"),
            "input_proof": hf2_proof.get("pass"),
        },
    )

    add("figshare_source_hash", sha256(ROOT / "data/raw/load/figshare_29832701_Data_output.xlsx") == "a93ff6d4a2f4f8c36538fdc4704e2e88bef16347d217c456a99a7a97d56a19e0", sha256(ROOT / "data/raw/load/figshare_29832701_Data_output.xlsx"))
    add("processed_load_hash", sha256(ROOT / "data/processed/figshare_load_2024_31province_8760_nonleap.csv") == "74944cc8d707561ac1b6e3210cfa7035eaa5d0e84a391d42c012de17304291ab", sha256(ROOT / "data/processed/figshare_load_2024_31province_8760_nonleap.csv"))

    canonical_launchers = [
        ROOT / "RUN_V17T2R6_8760_CORE_PAIR_2x10.bat",
        ROOT / "RUN_V17T2R6_8760_LDES_PAIR_2x10.bat",
        ROOT / "RUN_V17T2R6_8760_ALL_4_2x10.bat",
    ]
    force_hits = []
    for launcher in canonical_launchers:
        text = launcher.read_text(encoding="utf-8", errors="ignore") if launcher.is_file() else ""
        if "--force-rerun" in text or "--clean-central" in text:
            force_hits.append(launcher.name)
    add("canonical_launchers_resume_safe", not force_hits, force_hits)

    all4 = (ROOT / "RUN_V17T2R6_8760_ALL_4_2x10.bat").read_text(encoding="utf-8", errors="ignore")
    env_defaults = (ROOT / "V17T2R6_8760_ENV_DEFAULTS.bat").read_text(encoding="utf-8", errors="ignore")
    batch_runner = (ROOT / "tools" / "run_targetyear_batch.py").read_text(encoding="utf-8", errors="ignore")
    parallel_tokens = [
        'set "V17_SOLVER_THREADS=10"',
        'set "V17T2R6_MAX_PARALLEL=2"',
        "--max-parallel 2",
        "--pair ALL",
        "--route auto",
    ]
    add("r7_all4_launcher_exact_2x10", all(token in all4 for token in parallel_tokens), [t for t in parallel_tokens if t not in all4])
    clean_launcher = (ROOT / "RUN_V17T2R6_8760_CLEAN_REBUILD_AND_RUN_ALL_4_2x10.bat").read_text(encoding="utf-8", errors="ignore")
    preflight_launcher = (ROOT / "CHECK_V17T2R6_8760_PREFLIGHT.bat").read_text(encoding="utf-8", errors="ignore")
    clean_tokens = [
        'call "%~dp0CHECK_V17T2R6R7_HF2P1_PATCH.bat"',
        'if exist "sensitivity_cases" rmdir /s /q "sensitivity_cases"',
        'if exist "sensitivity_outputs" rmdir /s /q "sensitivity_outputs"',
        'if exist "batch_logs" rmdir /s /q "batch_logs"',
        'if exist "failed_diagnostics" rmdir /s /q "failed_diagnostics"',
        'call "%~dp0PREPARE_V17T2R6_8760_CASES.bat"',
        'call "%~dp0RUN_V17T2R6_8760_ALL_4_2x10.bat"',
    ]
    patch_check_position = clean_launcher.find('call "%~dp0CHECK_V17T2R6R7_HF2P1_PATCH.bat"')
    first_delete_position = clean_launcher.find('rmdir /s /q')
    add(
        "hf2p1_clean_all4_launcher_contract",
        all(token in clean_launcher for token in clean_tokens)
        and patch_check_position >= 0
        and first_delete_position > patch_check_position
        and 'call "%~dp0CHECK_V17T2R6R7_HF2P1_PATCH.bat"' in preflight_launcher,
        {
            "missing_tokens": [token for token in clean_tokens if token not in clean_launcher],
            "patch_check_precedes_deletion": patch_check_position >= 0 and first_delete_position > patch_check_position,
            "preflight_includes_patch_check": 'call "%~dp0CHECK_V17T2R6R7_HF2P1_PATCH.bat"' in preflight_launcher,
        },
    )
    add(
        "r7_environment_defaults_2x10",
        'if not defined V17_SOLVER_THREADS set "V17_SOLVER_THREADS=10"' in env_defaults
        and 'if not defined V17T2R6_MAX_PARALLEL set "V17T2R6_MAX_PARALLEL=2"' in env_defaults,
        {"threads10": 'V17_SOLVER_THREADS=10' in env_defaults, "parallel2": 'V17T2R6_MAX_PARALLEL=2' in env_defaults},
    )
    scheduler_tokens = [
        "ThreadPoolExecutor(max_workers=2",
        "PARALLEL_WAVES",
        "selected_waves",
        "run_selected_rows",
        "--max-parallel",
        "R7 2x10 mode requires V17_SOLVER_THREADS=10 exactly.",
        "Preserve scenario-registry order regardless of which worker finishes first.",
    ]
    add("r7_parallel_scheduler_contract", all(token in batch_runner for token in scheduler_tokens), [t for t in scheduler_tokens if t not in batch_runner])
    scheduler_audit_path = ROOT / "audits" / "V17T2R6R7_PARALLEL_SCHEDULER_AUDIT.json"
    scheduler_audit = json.loads(scheduler_audit_path.read_text(encoding="utf-8")) if scheduler_audit_path.is_file() else {}
    add(
        "r7_parallel_scheduler_regression_pass",
        scheduler_audit.get("status") == "PASS"
        and scheduler_audit.get("runner_sha256") == sha256(ROOT / "tools" / "run_targetyear_batch.py")
        and scheduler_audit.get("max_active_observed") == 2,
        {"status": scheduler_audit.get("status"), "max_active_observed": scheduler_audit.get("max_active_observed")},
    )
    # Shared summaries must be written only after run_selected_rows returns in the parent.
    run_selected_pos = batch_runner.find("records = run_selected_rows(")
    summary_write_pos = batch_runner.find("merged.to_csv(SUMMARY_CSV")
    add("parallel_summary_parent_only", run_selected_pos >= 0 and summary_write_pos > run_selected_pos, {"run_selected_pos": run_selected_pos, "summary_write_pos": summary_write_pos})

    old_parallel_launchers = sorted(
        p.name for p in ROOT.glob("RUN_V17T2R6_8760_*1x10.bat")
    )
    add("no_stale_1x10_launchers", not old_parallel_launchers, old_parallel_launchers)
    superseded = sorted(
        p.name
        for pattern in (
            "RUN_V17T2R6R1_*.bat", "RUN_V17T2R6R2_*.bat", "RUN_V17T2R6R3_*.bat",
            "RUN_V17T2R6R4_*.bat", "RUN_V17T2R6R5_*.bat", "RUN_V17T2R6R6_*.bat"
        )
        for p in ROOT.glob(pattern)
    )
    add("no_superseded_versioned_launchers", not superseded, superseded)

    obsolete = [p.name for p in ROOT.glob("*V17T2R5*.bat")]
    add("no_obsolete_v17t2r5_launchers", not obsolete, obsolete)
    obsolete_helpers = [
        "audit_julia_lexical_v17t2r5.py", "build_targetyear_summary.py",
        "check_v17t2r5_package.py", "prepare_targetyear_cases.py",
        "reconstruct_one_hour_repdays.py", "validate_targetyear_case.py",
    ]
    remaining_helpers = [name for name in obsolete_helpers if (ROOT / "tools" / name).exists()]
    add("no_obsolete_targetyear_helpers", not remaining_helpers, remaining_helpers)
    machine_paths = []
    for suffix in ("*.json", "*.csv", "*.md"):
        for path in ROOT.rglob(suffix):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "C:\\Users\\" in text or "C:/Users/" in text:
                machine_paths.append(path.relative_to(ROOT).as_posix())
    add("no_machine_specific_release_paths", not machine_paths, sorted(set(machine_paths)))
    goldwind_hits = []
    for path in [ROOT / "README_ZH.md", ROOT / "README_EN.md", ROOT / "data/source_registry/data_source_registry.csv"]:
        if path.is_file() and "goldwind" in path.read_text(encoding="utf-8", errors="ignore").lower():
            goldwind_hits.append(path.relative_to(ROOT).as_posix())
    add("no_goldwind_release_source", not goldwind_hits, goldwind_hits)

    delta_path = ROOT / "audits" / "V17T2R6R7_RELEASE_DELTA_AUDIT.json"
    delta = json.loads(delta_path.read_text(encoding="utf-8")) if delta_path.is_file() else {}
    add(
        "historical_r7_baseline_scientific_inputs_byte_identical_to_r6",
        delta.get("science_inputs_unchanged") is True
        and delta.get("scientific_byte_drift_count") == 0
        and delta.get("active_julia_model_byte_identical") is True
        and delta.get("julia_scenario_runner_byte_identical") is True
        and not delta.get("missing_from_r7")
        and not delta.get("new_scientific_files"),
        {
            "science_inputs_unchanged": delta.get("science_inputs_unchanged"),
            "scientific_byte_drift_count": delta.get("scientific_byte_drift_count"),
            "active_julia_model_byte_identical": delta.get("active_julia_model_byte_identical"),
            "julia_scenario_runner_byte_identical": delta.get("julia_scenario_runner_byte_identical"),
        },
    )

    failures = [item for item in checks if not item["pass"]]
    report = {
        "version": "V17T2R6R7_HF2P2_FULL8760",
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failed": failures,
    }
    out = ROOT / "audits" / "V17T2R6_FULL8760_PACKAGE_QA.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not failures else 2)


if __name__ == "__main__":
    main()
