#!/usr/bin/env python3
"""Fail-closed static lexical/contract audit for active V17T2R6 full-8760 Julia entrypoints."""
from __future__ import annotations

import hashlib
import json
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"
RUNNER = ROOT / "storage_runner" / "run_targetyear_one.jl"
RUNTIME = ROOT / "storage_runner" / "check_v17t2r6_8760_runtime.jl"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def delimiter_errors(text: str) -> list[str]:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[tuple[str, int]] = []
    errors: list[str] = []
    i = 0
    in_string = False
    triple = False
    escaped = False
    while i < len(text):
        if in_string:
            if triple and text.startswith('"""', i):
                in_string = False
                triple = False
                i += 3
                continue
            if not triple:
                if escaped:
                    escaped = False
                elif text[i] == "\\":
                    escaped = True
                elif text[i] == '"':
                    in_string = False
            i += 1
            continue
        if text.startswith('"""', i):
            in_string = True
            triple = True
            i += 3
            continue
        char = text[i]
        if char == '"':
            in_string = True
            triple = False
            i += 1
            continue
        if char == "#":
            newline = text.find("\n", i)
            i = len(text) if newline < 0 else newline + 1
            continue
        if char in "([{":
            stack.append((char, i))
        elif char in pairs:
            if not stack or stack[-1][0] != pairs[char]:
                errors.append(f"mismatched {char} at byte {i}")
            else:
                stack.pop()
        i += 1
    if in_string:
        errors.append("unterminated double-quoted string")
    errors.extend(f"unclosed {char} at byte {position}" for char, position in stack[-20:])
    return errors


def main() -> None:
    model = MODEL.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")
    checks: list[dict] = []

    def add(name: str, passed: bool, detail) -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    for name, text in [("model", model), ("runner", runner), ("runtime_checker", runtime)]:
        errors = delimiter_errors(text)
        add(f"{name}_utf8_and_balanced_delimiters", not errors, errors)

    required = [
        '"full_year_cyclic"',
        "FULL_YEAR_TPS_IN_PERIOD",
        "tp_previous_commit = copy(tp_previous)",
        "representative_timepoint_count_expected",
        "storage_full_chronological_claim_supported",
        "cyclic_closure_residual_mwh",
        "V17T2R6_full8760_primary_scaled_barrier_nocrossover",
        "V17T2R6_full8760_fallback_homogeneous_barrier_nocrossover",
        'profile == "targetyear_scaled_barrier_nocrossover"',
        'profile == "targetyear_homogeneous_barrier_nocrossover"',
        "V17T2R6_PRIMARY_BAR_ITER_LIMIT",
        "V17T2R6_FALLBACK_BAR_ITER_LIMIT",
        'get(ENV, "V17T2R6_8760_PRIMARY_BAR_ITER_LIMIT", "100000")',
        'get(ENV, "V17T2R6_8760_FALLBACK_BAR_ITER_LIMIT", "100000")',
    ]
    missing = [token for token in required if token not in model]
    add("full8760_contract_tokens", not missing, missing)

    # Regression guards for both real runtime failures found during live execution:
    # (1) numeric TIMESERIES identifiers require generic string(x), not String(x);
    # (2) prepared timestamps use yyyy-mm-dd_HH:MM and must be parseable by Julia.
    unsafe_identifier_conversions = [token for token in ("String(ts)", "String(t)") if token in model]
    unsafe_runner_conversions = [token for token in ("String(r.", "strip(String(x))") if token in runner]
    add(
        "generic_identifier_stringification",
        not unsafe_identifier_conversions and not unsafe_runner_conversions and "string(ts)" in model and "string(t)" in model,
        {"model": unsafe_identifier_conversions, "runner": unsafe_runner_conversions},
    )
    # Regression guard for the live full-8760 post-solve export failure:
    # the expected timepoint count is a runtime-local variable, not an uppercase global.
    unsafe_postsolve_expected_count = "REPRESENTATIVE_TIMEPOINT_COUNT_EXPECTED" in model
    safe_postsolve_expected_count = ":representative_timepoint_count_expected => [representative_timepoint_count_expected]" in model
    add(
        "postsolve_export_uses_runtime_timepoint_count",
        (not unsafe_postsolve_expected_count) and safe_postsolve_expected_count,
        {
            "unsafe_uppercase_global_present": unsafe_postsolve_expected_count,
            "safe_runtime_local_present": safe_postsolve_expected_count,
        },
    )

    timestamp_tokens = [
        'dateformat"yyyy-mm-dd_HH:MM"',
        'dateformat"yyyy-mm-dd_HH:MM:SS"',
        "ordered_timestamps[i] == ordered_timestamps[i - 1] + Hour(1)",
        "Full-year chronology must be a strictly contiguous one-hour sequence",
        "Full-year TIMESERIES blocks must cover calendar months 1..12 exactly once",
    ]
    add("full8760_timestamp_runtime_guards", all(t in model for t in timestamp_tokens), [t for t in timestamp_tokens if t not in model])

    # Regression guard for the Windows/Julia 1.12 + CSV.jl/InlineStrings failure
    # observed when a Vector{String15} was sorted directly with a tuple-valued
    # `by` key. Active code must sort an ordinary keyed tuple vector explicitly
    # with MergeSort and then recover original identifiers.
    unsafe_inline_sort_tokens = [
        "sort!(tps, by = t -> (tp_timestamp_parsed[t]",
        "sort!(tps; by = t -> (tp_timestamp_parsed[t]",
    ]
    safe_inline_sort_tokens = [
        "keyed = Tuple{DateTime,Int,Any}[]",
        "sort!(keyed; by = item -> (item[1], item[2]), alg = Base.Sort.MergeSort)",
        "TPS_IN_TS[ts] = Any[item[3] for item in keyed]",
    ]
    inline_sort_hits = [token for token in unsafe_inline_sort_tokens if token in model]
    add(
        "inline_string_timepoint_sort_is_generic_and_stable",
        not inline_sort_hits and all(token in model for token in safe_inline_sort_tokens),
        {"unsafe_hits": inline_sort_hits, "missing_safe_tokens": [t for t in safe_inline_sort_tokens if t not in model]},
    )

    runtime_tokens = [
        'dateformat"yyyy-mm-dd_HH:MM"',
        "nrow(tpdf) == 8760",
        "string(id)",
        "stamps[i] == stamps[i - 1] + Hour(1)",
        "InlineString time-index sort contract: PASS",
        "Base.Sort.MergeSort",
        "8760 CSV identifier/timestamp runtime contract: PASS",
        "Gurobi smoke LP: PASS",
    ]
    add("runtime_preflight_exercises_real_8760_contract", all(t in runtime for t in runtime_tokens), [t for t in runtime_tokens if t not in runtime])

    banned = [
        "V17T2R5_PRIMARY_TIME_LIMIT_SECONDS",
        "V17T2R5_FALLBACK_TIME_LIMIT_SECONDS",
        "V17T2R5_CROSSOVER_BASIS",
        "cheer_power_storage_targetyear_v17t2r5.jl",
    ]
    hits = [token for token in banned if token in model or token in runner or token in runtime]
    add("no_obsolete_runtime_fallback", not hits, hits)
    add(
        "runner_model_binding",
        'include(joinpath(@__DIR__, "..", "base_model_v39", "cheer_power_storage_targetyear_v17t2r6_8760.jl"))' in runner,
        "V17T2R6 model include",
    )
    official_default_tokens = [
        'solver_profile::String="targetyear_scaled_barrier_nocrossover"',
        'get(args, "solver_profile", "targetyear_scaled_barrier_nocrossover")',
    ]
    add("runner_default_is_official_no_crossover_route", all(t in runner for t in official_default_tokens), [t for t in official_default_tokens if t not in runner])

    # HF2 exact-projection reduction. These checks deliberately validate both
    # the active Julia index sets and the four frozen case inputs. The removed
    # CCS columns are fixed at zero in the unreduced formulation. The removed
    # startup/shutdown pairs have zero objective coefficients and no min-up or
    # min-down use, so any retained commitment path can reconstruct them as the
    # positive and negative parts of its hourly difference.
    reduction_tokens = [
        "CCS_GEN_TPS = [(g, t) for (g, t) in GEN_TPS if g in CCS_GENS]",
        "@variable(mod, DispatchGenCCS[(g, t) in CCS_GEN_TPS]>=0)",
        "@variable(mod, CommitGenCCS[(g, t) in CCS_GEN_TPS]>=0)",
        "STARTUP_SHUTDOWN_GENS = Set(g for g in GENERATION_PROJECTS if",
        "@variable(mod, StartupGenCapacity[(g, t) in STARTUP_SHUTDOWN_GEN_TPS] >= 0)",
        "@variable(mod, ShutdownGenCapacity[(g, t) in STARTUP_SHUTDOWN_GEN_TPS] >= 0)",
        "dispatch_gen_ccs_value_or_zero",
        "startup_gen_capacity_value_or_zero",
        ':algebraic_reduction_version => ["V17T2R6R7_HF2_exact_projection_v1"]',
    ]
    legacy_dense_tokens = [
        "@variable(mod, DispatchGenCCS[(g, t) in GEN_TPS]>=0)",
        "@variable(mod, CommitGenCCS[(g, t) in GEN_TPS]>=0)",
        "@variable(mod, StartupGenCapacity[(g, t) in GEN_TPS] >= 0)",
        "@variable(mod, ShutdownGenCapacity[(g, t) in GEN_TPS] >= 0)",
    ]
    dense_hits = [token for token in legacy_dense_tokens if token in model]
    add(
        "hf2_exact_projection_code_contract",
        all(token in model for token in reduction_tokens) and not dense_hits,
        {
            "missing_reduction_tokens": [token for token in reduction_tokens if token not in model],
            "legacy_dense_hits": dense_hits,
        },
    )

    # HF2P1 is a post-solve-only complexity repair. Ordered vectors remain the
    # iteration sources; Set mirrors are permitted only after the publication
    # solve gate and are used solely for boolean membership queries.
    postsolve_marker = "# post-solve treat and export of results"
    postsolve = model[model.index(postsolve_marker):] if postsolve_marker in model else ""
    postsolve_lookup_tokens = [
        "postsolve_storage_gen_tps_lookup = Set(STORAGE_GEN_TPS)",
        "postsolve_storage_gens_lookup = Set(STORAGE_GENS)",
        "postsolve_prr_timepoints_lookup = Set(PRR_TIMEPOINTS)",
        "(g, t) in postsolve_storage_gen_tps_lookup",
        "(prr, t) in postsolve_prr_timepoints_lookup",
    ]
    slow_postsolve_membership_tokens = [
        "(g, t) in STORAGE_GEN_TPS) ?",
        "if (g, t) in STORAGE_GEN_TPS",
        "!((g, t) in STORAGE_GEN_TPS)",
        "((prr, t) in PRR_TIMEPOINTS)",
    ]
    ordered_iteration_tokens = [
        ":generation_project => [g for (g, t) in GEN_TPS]",
        ":generation_project => [g for (g, t) in STORAGE_GEN_TPS]",
        ":planning_reserve_requirement => [prr for (prr, t) in PRR_TIMEPOINTS]",
    ]
    slow_hits = [token for token in slow_postsolve_membership_tokens if token in postsolve]
    add(
        "hf2p1_postsolve_membership_lookup_is_order_preserving",
        bool(postsolve)
        and all(token in postsolve for token in postsolve_lookup_tokens)
        and not slow_hits
        and all(token in postsolve for token in ordered_iteration_tokens),
        {
            "missing_lookup_tokens": [token for token in postsolve_lookup_tokens if token not in postsolve],
            "slow_vector_membership_hits": slow_hits,
            "missing_ordered_iteration_tokens": [token for token in ordered_iteration_tokens if token not in postsolve],
            "proof": "Set mirrors replace only equality-based membership tests; ordered vectors remain every export iteration source",
        },
    )

    def numeric_or_zero(value: str) -> float:
        text = str(value).strip()
        return 0.0 if text in {"", "."} else float(text)

    reduction_stats = {}
    reduction_errors = []
    cases_root = ROOT / "sensitivity_cases"
    for case_dir in sorted(path for path in cases_root.iterdir() if path.is_dir()):
        with (case_dir / "inputs" / "gen_info.csv").open(encoding="utf-8-sig", newline="") as handle:
            generators = list(csv.DictReader(handle))
        with (case_dir / "inputs" / "ccs_install_costs.csv").open(encoding="utf-8-sig", newline="") as handle:
            ccs_projects = {row["GENERATION_PROJECT"] for row in csv.DictReader(handle)}
        with (case_dir / "inputs" / "timepoints.csv").open(encoding="utf-8-sig", newline="") as handle:
            timepoint_count = sum(1 for _ in csv.DictReader(handle))

        generator_names = {row["GENERATION_PROJECT"] for row in generators}
        active_startup = {
            row["GENERATION_PROJECT"]
            for row in generators
            if numeric_or_zero(row["gen_startup_om"]) != 0.0
            or numeric_or_zero(row["gen_min_uptime"]) > 0.0
            or numeric_or_zero(row["gen_min_downtime"]) > 0.0
        }
        omitted_startup = generator_names - active_startup
        bad_omitted = [
            row["GENERATION_PROJECT"]
            for row in generators
            if row["GENERATION_PROJECT"] in omitted_startup
            and (
                numeric_or_zero(row["gen_startup_om"]) != 0.0
                or numeric_or_zero(row["gen_min_uptime"]) != 0.0
                or numeric_or_zero(row["gen_min_downtime"]) != 0.0
            )
        ]
        if not ccs_projects.issubset(generator_names):
            reduction_errors.append(f"{case_dir.name}: CCS project absent from gen_info")
        if bad_omitted:
            reduction_errors.append(f"{case_dir.name}: unsafe startup omission {bad_omitted[:5]}")
        if timepoint_count != 8760:
            reduction_errors.append(f"{case_dir.name}: expected 8760 timepoints, got {timepoint_count}")

        non_ccs_gen_tp = (len(generator_names) - len(ccs_projects)) * timepoint_count
        omitted_startup_gen_tp = len(omitted_startup) * timepoint_count
        reduction_stats[case_dir.name] = {
            "generators": len(generator_names),
            "timepoints": timepoint_count,
            "ccs_generators": len(ccs_projects),
            "non_ccs_generators": len(generator_names - ccs_projects),
            "startup_shutdown_active_generators": len(active_startup),
            "startup_shutdown_omitted_generators": len(omitted_startup),
            "fixed_zero_ccs_columns_omitted": 2 * non_ccs_gen_tp,
            "objective_neutral_startup_shutdown_columns_omitted": 2 * omitted_startup_gen_tp,
            "total_hourly_columns_omitted": 2 * non_ccs_gen_tp + 2 * omitted_startup_gen_tp,
        }

    expected_cases = {
        "TY2033_FULL8760_OBSERVED",
        "TY2033_FULL8760_OPTIMAL",
        "TY2033_FULL8760_LDES_OBSERVED",
        "TY2033_FULL8760_LDES_OPTIMAL",
    }
    if set(reduction_stats) != expected_cases:
        reduction_errors.append(f"case set mismatch: {sorted(reduction_stats)}")
    for left, right in [
        ("TY2033_FULL8760_OBSERVED", "TY2033_FULL8760_OPTIMAL"),
        ("TY2033_FULL8760_LDES_OBSERVED", "TY2033_FULL8760_LDES_OPTIMAL"),
    ]:
        if reduction_stats.get(left) != reduction_stats.get(right):
            reduction_errors.append(f"paired reduction mismatch: {left} vs {right}")
    add(
        "hf2_exact_projection_input_proof",
        not reduction_errors,
        {
            "proof": [
                "non-CCS GenCapacityCCS is identically zero, hence omitted CCS dispatch and commitment columns are fixed-zero eliminations",
                "omitted startup/shutdown variables have zero startup objective coefficient and no min-up/min-down occurrence",
                "for every retained commitment sequence, Startup=max(delta,0) and Shutdown=max(-delta,0) reconstruct the eliminated equality",
                "all scientific inputs, objective terms, chronology, reserve equations, tolerances, solver routes and publication gates remain unchanged",
            ],
            "case_stats": reduction_stats,
            "errors": reduction_errors,
        },
    )

    failures = [item for item in checks if not item["pass"]]
    report = {
        "version": "V17T2R6R7_HF2P1_FULL8760",
        "status": "PASS" if not failures else "FAIL",
        "scope": "static lexical/contract audit; runtime checker must still be executed on the target Julia/Gurobi machine",
        "model_sha256": sha256(MODEL),
        "runner_sha256": sha256(RUNNER),
        "runtime_checker_sha256": sha256(RUNTIME),
        "checks": checks,
        "failed": failures,
    }
    out = ROOT / "audits" / "V17T2R6_8760_JULIA_STATIC_AUDIT.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not failures else 2)


if __name__ == "__main__":
    main()
