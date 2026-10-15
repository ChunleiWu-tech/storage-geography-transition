#!/usr/bin/env python3
"""Static and live-input audit for the V17T2 SL10 rescue route."""
from __future__ import annotations
from pathlib import Path
import argparse
import json
import py_compile
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audits" / "V17T2_SL10_RESCUE_AUDIT.json"
TRUE = {"true", "1", "yes"}
SCENARIO = "SL10_CARBON_TIGHT_OBSERVED"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-existing-results", action="store_true")
    args = parser.parse_args()

    model = (ROOT / "base_model_v39" / "cheer_power_storage_v1.jl").read_text(encoding="utf-8")
    runner = (ROOT / "storage_runner" / "run_storage_one_solver_task.jl").read_text(encoding="utf-8")
    batch = (ROOT / "tools" / "run_official_batch.py").read_text(encoding="utf-8")
    rescue = (ROOT / "tools" / "run_v17t2_sl10_rescue.py").read_text(encoding="utf-8")
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: object) -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": str(detail)})

    for p in [ROOT / "tools" / "run_official_batch.py", ROOT / "tools" / "run_v17t2_sl10_rescue.py", ROOT / "tools" / "audit_v17t2_sl10_rescue.py"]:
        try:
            py_compile.compile(str(p), doraise=True)
            add(f"python_compile:{p.name}", True, p)
        except Exception as exc:
            add(f"python_compile:{p.name}", False, exc)

    profile_block = re.search(
        r'elseif profile == "hard_homogeneous_barrier_no_crossover"(?P<body>.*?)elseif profile == "primal_simplex_diagnostic"',
        model,
        flags=re.S,
    )
    body = profile_block.group("body") if profile_block else ""
    add("profile_present", profile_block is not None, "dedicated profile")
    for token in [
        "method = 2", "crossover = 0", "numeric_focus = 3", "scale_flag = 2",
        "aggregate = 0", "pre_sparsify = 0", "quad = 1", "bar_homogeneous = 1",
        "bar_iter_limit = HARD_LP_BAR_ITER_LIMIT",
        "time_limit_seconds = V17T2_SL10_BARRIER_TIME_LIMIT_SECONDS",
        'route_role = "hard_lp_homogeneous_barrier_no_crossover"',
    ]:
        add(f"profile_setting:{token}", token in body, token)

    gate_tokens = [
        'solver_settings.profile == "hard_homogeneous_barrier_no_crossover"',
        "solver_settings.crossover == 0",
        "solver_settings.bar_homogeneous == 1",
        "stage1_simplex_iterations == 0.0",
        '"gurobi_hard_homogeneous_barrier_no_crossover_optimal_status"',
    ]
    add("model_native_gate", all(t in model for t in gate_tokens), gate_tokens)
    add("runner_profile_and_suffix", all(t in runner for t in ["hard_homogeneous_barrier_no_crossover", "__v17t2_homogeneous_barrier_nocrossover_official"]), "runner whitelist")
    add("batch_profile_gate", all(t in batch for t in ["hard_homogeneous_barrier_no_crossover", "hard_lp_homogeneous_barrier_no_crossover", "gurobi_hard_homogeneous_barrier_no_crossover_optimal_status"]), "outer gate")
    preflight = (ROOT / "postprocess" / "preflight_spatial_legacy_outputs.py").read_text(encoding="utf-8")
    add("postprocess_accepts_all_hard_native_sources", all(t in preflight for t in [
        "gurobi_hard_deterministic_concurrent_simplex_optimal_status",
        "gurobi_hard_primal_simplex_optimal_status",
        "gurobi_hard_homogeneous_barrier_crossover_optimal_status",
        "gurobi_hard_homogeneous_barrier_no_crossover_optimal_status",
    ]), "hard-route certificates remain strict and postprocessable")
    add("sl10_route_isolated", 'if scenario in SL10_BARRIER_RESCUE_SCENARIOS' in batch and '"SL10_CARBON_TIGHT_OBSERVED"' in batch, "SL10 only")
    add("sl13_original_routes_retained", all(t in batch for t in ["SL13_COST_LOW_OPTIMAL", "hard_deterministic_concurrent_simplex", "hard_primal_simplex", "hard_homogeneous_barrier"]), "SL13 unchanged")
    add("no_model_or_scenario_relaxation", all(t not in rescue for t in ["carbon_cap_multiplier =", "FeasRelax", "feasRelax", "set_normalized_rhs", "set_upper_bound", "set_lower_bound"]), "rescue changes solver route only")
    add("atomic_summary_replace", "os.replace(tmp, batch.SUMMARY)" in rescue, "atomic summary replacement")
    add("protects_fifteen_outputs", all(t in rescue for t in ["_reference_hashes", "before_hashes == after_hashes", "Expected 15 protected reference outputs"]), "byte-level protection")
    add("does_not_clean_outputs", all(t not in rescue for t in ["shutil.rmtree(batch.OUTROOT", "--clean-previous"]), "no global clean")
    add("requires_barrier_then_crossover_evidence", all(t in rescue for t in ["Barrier solved model", "Crossover log...", "Time limit reached"]), "evidence-selected route")

    if args.require_existing_results:
        summary_path = ROOT / "storage_runner" / "storage_batch_run_summary.csv"
        add("existing_summary", summary_path.exists(), summary_path)
        if summary_path.exists():
            df = pd.read_csv(summary_path)
            failed = df.loc[~df["publication_strict_success"].astype(str).str.lower().isin(TRUE), "scenario"].astype(str).tolist()
            add("existing_summary_16_rows", len(df) == 16 and df["scenario"].nunique() == 16, len(df))
            add("only_sl10_failed", failed == [SCENARIO], failed)
        log = ROOT / "batch_logs" / f"{SCENARIO}__hard_homogeneous_barrier_retry.log"
        add("reference_log_exists", log.exists(), log)
        if log.exists():
            text = log.read_text(encoding="utf-8", errors="replace")
            add("reference_barrier_optimal", "Barrier solved model" in text and "Optimal objective" in text, log)
            add("reference_crossover_timeout", "Crossover log..." in text and "Time limit reached" in text, log)

    summary = {
        "version": "V17T2",
        "checks": len(checks),
        "passed": sum(bool(x["pass"]) for x in checks),
        "all_pass": all(bool(x["pass"]) for x in checks),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": summary, "checks": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "failed": [x for x in checks if not x["pass"]]}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if summary["all_pass"] else 1)


if __name__ == "__main__":
    main()
