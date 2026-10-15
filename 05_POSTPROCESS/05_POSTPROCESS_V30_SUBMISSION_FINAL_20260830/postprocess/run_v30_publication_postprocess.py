#!/usr/bin/env python3
"""Transactional four-root publication postprocessor for the final submission."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def remove(path: Path) -> None:
    if path.is_dir(): shutil.rmtree(path)
    elif path.exists(): path.unlink()


def run(script: str, *args: str, env: dict[str, str], cwd: Path) -> None:
    command = [sys.executable, str(SOURCE_ROOT / "postprocess" / script), *args]
    print("RUN:", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{script} failed with return code {completed.returncode}")


def promote(working: Path, final: Path, previous: Path) -> None:
    remove(previous)
    if final.exists(): final.rename(previous)
    try:
        working.rename(final)
    except Exception:
        if previous.exists() and not final.exists(): previous.rename(final)
        raise
    remove(previous)


def require(root: Path, paths: list[str], label: str) -> None:
    if not root.is_dir():
        raise FileNotFoundError(f"{label} root is not a directory: {root}")
    missing = [str(root / item) for item in paths if not (root / item).exists()]
    if missing: raise FileNotFoundError(f"{label} root is incomplete: " + "; ".join(missing))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-upstream-root", required=True)
    parser.add_argument("--targetyear-upstream-root", required=True)
    parser.add_argument("--full8760-root", required=True)
    parser.add_argument("--future-storage-root", required=True)
    parser.add_argument("--output-root", default=str(SOURCE_ROOT / "postprocess_outputs"))
    args = parser.parse_args()
    roots = {
        "main": Path(args.main_upstream_root).expanduser().resolve(),
        "targetyear": Path(args.targetyear_upstream_root).expanduser().resolve(),
        "full8760": Path(args.full8760_root).expanduser().resolve(),
        "v20": Path(args.future_storage_root).expanduser().resolve(),
    }
    if len(set(roots.values())) != 4:
        raise ValueError("The four upstream roots must be distinct directories")
    require(roots["main"], ["storage_runner/storage_batch_run_summary.csv", "storage_runner/scenarios_storage_master.csv", "outputs"], "Main")
    require(roots["targetyear"], ["storage_runner/scenarios_targetyear_linked.csv", "sensitivity_outputs", "VERSION_V17T2R5.txt"], "Target-year")
    require(roots["full8760"], [
        "storage_runner/prepared_8760_cases_index.csv",
        "tools/run_hf18p2_r24p3_postsolve_complementarity_recovery.py",
        "robustness_distance_8760_quality_recovery_outputs/V17T2R6R24P3_HF18P2_COMBINED_ALL4_final_summary.json",
    ], "FULL8760")
    require(roots["v20"], [
        "storage_cases", "modules/correction2033",
        "audits/v20/V20_LAYER_B_16_SOLVER_SUMMARY.csv",
        "audits/v20/V20_LAYER_C_EQUAL_HORIZON_2_SOLVER_SUMMARY.csv",
        "modules/correction2033/future_correction_outputs/V19_LAYER_A_run_summary.csv",
    ], "V20")

    final = Path(args.output_root).expanduser().resolve()
    working = final.with_name(final.name + ".__v30_working__")
    previous = final.with_name(final.name + ".__previous__")
    remove(working); working.mkdir(parents=True)
    lineage_output = working / "audits" / "UPSTREAM_RESULT_LINEAGE_AUDIT.json"
    lineage = subprocess.run([
        sys.executable, str(SOURCE_ROOT / "postprocess" / "check_upstream_source_fingerprints.py"),
        str(roots["main"]), str(roots["targetyear"]), "--require-results", "--output", str(lineage_output),
    ], cwd=SOURCE_ROOT, check=False)
    if lineage.returncode != 0:
        raise RuntimeError("Main 16-case or target-year 8-case current-source strict result lineage is incomplete")

    started = time.time()
    env = os.environ.copy()
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "V17_PROJECT_ROOT": str(roots["main"]),
        "V17_TARGETYEAR_SENSITIVITY_ROOT": str(roots["targetyear"]),
        "V30_FULL8760_ROOT": str(roots["full8760"]),
        "V30_FUTURE_STORAGE_ROOT": str(roots["v20"]),
        "V17_POSTPROCESS_SOURCE_ROOT": str(SOURCE_ROOT),
        "V17_POSTPROCESS_OUTPUT_ROOT": str(working),
    })
    try:
        # Frozen 16-case main chain.
        for script, script_args, cwd in (
            ("audit_v17t5_postprocess_source.py", (), roots["main"]),
            ("preflight_spatial_legacy_outputs.py", ("--scenario-set", "spatial_legacy_full"), roots["main"]),
            ("build_spatial_legacy_tables.py", ("--scenario-set", "spatial_legacy_full"), roots["main"]),
            ("audit_against_successful_baseline.py", (), roots["main"]),
            ("audit_scientific_consistency.py", (), roots["main"]),
            ("plot_spatial_legacy_figures.py", (), roots["main"]),
            # Frozen 8-case target-year sensitivity chain.
            ("preflight_targetyear_sensitivity.py", (), roots["targetyear"]),
            ("build_targetyear_sensitivity_tables.py", (), roots["targetyear"]),
            ("audit_targetyear_sensitivity.py", (), roots["targetyear"]),
            ("plot_targetyear_sensitivity_figure.py", (), roots["targetyear"]),
            ("write_targetyear_manuscript_text.py", (), roots["targetyear"]),
            # Validate the frozen 5 + 12 subset before adding new figures.
            ("validate_spatial_legacy_release.py", ("--scenario-set", "spatial_legacy_full"), roots["main"]),
            # New strict four-root evidence chain.
            ("preflight_v30_extended_results.py", (), SOURCE_ROOT),
            ("build_full8760_validation_tables.py", (), SOURCE_ROOT),
            ("plot_full8760_validation.py", (), SOURCE_ROOT),
            ("build_v20_publication_tables.py", (), SOURCE_ROOT),
            ("plot_v20_publication_figures.py", (), SOURCE_ROOT),
            ("write_v30_manuscript_text.py", (), SOURCE_ROOT),
            ("validate_v30_release.py", (), SOURCE_ROOT),
        ):
            run(script, *script_args, env=env, cwd=cwd)
        audit = {
            "version": "V30_POSTPROCESS_SUBMISSION_20260830", "status": "PASS",
            "upstream_roots": {key: str(value) for key, value in roots.items()},
            "all_roots_distinct": True, "upstream_write_performed": False,
            "main_cases": 16, "targetyear_cases": 8, "full8760_certificates": 4, "v20_cases": 26,
            "main_figures": 7, "supplementary_figures": 14,
            "elapsed_seconds": time.time() - started,
            "scope_locks": [
                "Target-year annualized cost is not added to multi-period present value.",
                "FULL8760 robustness distance is not an actual build or economic result.",
                "V20 Layer B/C representative chronology is not described as seasonal or full-8760 operation.",
                "Expanded CAES/H2 portfolio is pressure-test-only.",
            ],
            "unit_alignment": {
                "power": "BuildGen upstream MW -> figure GW by one /1000 conversion",
                "energy": "BuildStorageEnergy_MWh upstream MWh -> figure GWh by one /1000 conversion",
                "duration": "MWh/MW = hours",
                "targetyear_cost": "annualized USD/yr; matched difference; never added to PV",
                "dynamic_cost": "stage1 economic objective in present-value USD",
                "full8760": "robustness distance in MW; GW figures use one /1000 conversion",
            },
        }
        (working / "audits").mkdir(parents=True, exist_ok=True)
        (working / "audits" / "transactional_run_audit_v30.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        promote(working, final, previous)
    except Exception as exc:
        (working / "FAILED_V30_POSTPROCESS.json").write_text(json.dumps({
            "version": "V30_POSTPROCESS_SUBMISSION_20260830", "status": "FAIL", "error": str(exc),
            "working_directory_retained": str(working), "previous_final_output_preserved": final.exists(),
            "elapsed_seconds": time.time() - started,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(1) from exc
    print("V30 FOUR-ROOT STRICT POSTPROCESSING PASSED")
    print(f"Output: {final}")


if __name__ == "__main__":
    main()
