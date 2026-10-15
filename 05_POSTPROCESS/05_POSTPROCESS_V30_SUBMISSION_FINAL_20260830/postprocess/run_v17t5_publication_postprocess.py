#!/usr/bin/env python3
"""Transactional integrated runner for source-current main and sensitivity results.

The 16-scenario multi-period main results and the separate eight-scenario
single-target-year linked-SOC results are read from distinct roots. Both roots
must pass the current publication result-lineage gate before any table or figure
is generated. Upstream files are never modified by this postprocessor.
"""
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
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def run(script: str, *args: str, env: dict[str, str], cwd: Path) -> None:
    command = [sys.executable, str(SOURCE_ROOT / "postprocess" / script), *args]
    print("RUN:", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{script} failed with return code {completed.returncode}")


def promote(working: Path, final: Path, previous: Path) -> None:
    remove(previous)
    if final.exists():
        final.rename(previous)
    try:
        working.rename(final)
    except Exception:
        if previous.exists() and not final.exists():
            previous.rename(final)
        raise
    remove(previous)


def validate_main_upstream(upstream: Path) -> None:
    required = [
        upstream / "storage_runner" / "storage_batch_run_summary.csv",
        upstream / "storage_runner" / "scenarios_storage_master.csv",
        upstream / "base_model_v39" / "storage_base_template_v17.zip",
        upstream / "outputs",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("The selected V17T1 main upstream is incomplete: " + "; ".join(missing))


def validate_targetyear_upstream(upstream: Path) -> None:
    required = [
        upstream / "storage_runner" / "scenarios_targetyear_linked.csv",
        upstream / "sensitivity_outputs",
        upstream / "VERSION_V17T2R5.txt",
        upstream / "audits" / "V17T2R5_MODEL_LINEAGE.json",
        upstream / "audits" / "STATIC_PACKAGE_AUDIT_V17T2R5.json",
        upstream / "audits" / "V17T2R5_PAIR_IDENTITY_AUDIT.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("The selected V17T2R5 sensitivity upstream is incomplete: " + "; ".join(missing))
    if upstream.resolve() == Path(os.environ.get("V17_PROJECT_ROOT", upstream)).resolve():
        # This condition is only informative here; the strict distinct-root gate
        # is written and checked after both roots are available below.
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-upstream-root", required=True, help="main upstream root containing 16/16 current-source strict multi-period outputs")
    parser.add_argument("--targetyear-upstream-root", required=True, help="target-year upstream root containing 8/8 current-source strict target-year outputs")
    parser.add_argument("--output-root", default=str(SOURCE_ROOT / "postprocess_outputs"))
    args = parser.parse_args()

    main_upstream = Path(args.main_upstream_root).expanduser().resolve()
    targetyear_upstream = Path(args.targetyear_upstream_root).expanduser().resolve()
    if main_upstream == targetyear_upstream:
        raise ValueError("Main and target-year upstream roots must be distinct directories")

    lineage_check = SOURCE_ROOT / "postprocess" / "check_upstream_source_fingerprints.py"
    completed = subprocess.run(
        [sys.executable, str(lineage_check), str(main_upstream), str(targetyear_upstream), "--require-results"],
        cwd=SOURCE_ROOT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Current-source result lineage is incomplete. Clean-rerun all 16 main and 8 sensitivity scenarios before post-processing."
        )

    validate_main_upstream(main_upstream)
    validate_targetyear_upstream(targetyear_upstream)

    final = Path(args.output_root).expanduser().resolve()
    working = final.with_name(final.name + ".__v17t5r6r8r5_working__")
    previous = final.with_name(final.name + ".__previous__")
    start = time.time()
    remove(working)
    working.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["V17_PROJECT_ROOT"] = str(main_upstream)
    env["V17_TARGETYEAR_SENSITIVITY_ROOT"] = str(targetyear_upstream)
    env["V17_POSTPROCESS_SOURCE_ROOT"] = str(SOURCE_ROOT)
    env["V17_POSTPROCESS_OUTPUT_ROOT"] = str(working)

    try:
        # Frozen main-model pipeline.
        run("audit_v17t5_postprocess_source.py", env=env, cwd=main_upstream)
        run("preflight_spatial_legacy_outputs.py", "--scenario-set", "spatial_legacy_full", env=env, cwd=main_upstream)
        run("build_spatial_legacy_tables.py", "--scenario-set", "spatial_legacy_full", env=env, cwd=main_upstream)
        run("audit_against_successful_baseline.py", env=env, cwd=main_upstream)
        run("audit_scientific_consistency.py", env=env, cwd=main_upstream)
        run("plot_spatial_legacy_figures.py", env=env, cwd=main_upstream)

        # Separate target-year sensitivity pipeline.
        run("preflight_targetyear_sensitivity.py", env=env, cwd=targetyear_upstream)
        run("build_targetyear_sensitivity_tables.py", env=env, cwd=targetyear_upstream)
        run("audit_targetyear_sensitivity.py", env=env, cwd=targetyear_upstream)
        run("plot_targetyear_sensitivity_figure.py", env=env, cwd=targetyear_upstream)
        run("write_targetyear_manuscript_text.py", env=env, cwd=targetyear_upstream)

        # Exact combined release set: 5 main + 12 supplementary figures.
        run("validate_spatial_legacy_release.py", "--scenario-set", "spatial_legacy_full", env=env, cwd=main_upstream)

        audit_dir = working / "audits"
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / "transactional_run_audit.json").write_text(
            json.dumps(
                {
                    "version": "V17T5R6R8R5",
                    "standalone_postprocessor": True,
                    "main_upstream_root": str(main_upstream),
                    "targetyear_upstream_root": str(targetyear_upstream),
                    "upstream_roots_distinct": main_upstream != targetyear_upstream,
                    "source_root": str(SOURCE_ROOT),
                    "final_directory": str(final),
                    "elapsed_seconds": time.time() - start,
                    "success": True,
                    "main_figures": 5,
                    "supplementary_figures": 12,
                    "scope_lock": "V17T2R5 annual target-year results are not added to or substituted for V17T1 multi-period present-value results",
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        promote(working, final, previous)
    except Exception as exc:
        failure = {
            "version": "V17T5R6R8R5",
            "success": False,
            "error": str(exc),
            "working_directory_retained": str(working),
            "previous_final_output_preserved": final.exists(),
            "elapsed_seconds": time.time() - start,
        }
        (working / "FAILED_V17T5R6R8R5_POSTPROCESS.json").write_text(
            json.dumps(failure, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(failure, indent=2, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc

    print("V17T5R6R8R5 INTEGRATED STRICT POSTPROCESSING PASSED.")
    print(f"Main upstream results: {main_upstream}")
    print(f"Target-year sensitivity results: {targetyear_upstream}")
    print(f"Final output: {final}")


if __name__ == "__main__":
    main()
