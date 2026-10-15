#!/usr/bin/env python3
"""Static release validation for the 16-case V17T2 source package.

The default path is deliberately non-destructive: it validates the frozen
source contract and the already prepared, source-locked cases. Use
``--clean-rebuild-cases`` to regenerate the expanded base and all sixteen
cases before validation. This script never claims that Julia-Gurobi results
were produced; the separate publication result gate remains mandatory.
"""
from __future__ import annotations
from pathlib import Path
import argparse, json, shutil, subprocess, sys
from datetime import datetime, timezone
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("RUN:", " ".join(map(str, cmd)), flush=True)
    p=subprocess.run(cmd, cwd=ROOT)
    if p.returncode:
        raise SystemExit(p.returncode)


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument(
        "--clean-rebuild-cases",
        action="store_true",
        help="Delete and rebuild the expanded base and all 16 prepared cases before validation.",
    )
    ap.add_argument(
        "--with-input-figure-smoke",
        action="store_true",
        help="Also execute the optional input-only table/figure smoke test.",
    )
    args=ap.parse_args()

    for script in [
        "tools/check_v17_ne_config.py",
        "tools/audit_windows_launchers_v17.py",
        "tools/audit_julia_empty_collection_safety.py",
        "tools/audit_julia_syntax_v17.py",
        "tools/validate_storage_inputs.py",
        "tools/audit_legacy_storage_provenance.py",
        "tools/audit_numerical_stability_v17.py",
        "tools/audit_objective_certificate_v17.py",
        "tools/audit_v17_release_policy.py",
        "tools/check_v17_run_readiness.py",
        "tools/audit_v17t2_sl10_rescue.py",
        "tools/audit_v17t1_four_scenario_repairs.py",
    ]:
        run([sys.executable, script])

    run([sys.executable, "tools/publication_source_gate.py", "--stage", "source"])

    if args.clean_rebuild_cases:
        for path in [
            ROOT / "storage_cases",
            ROOT / "base_model_v39" / "storage_base_noNBCCS_noDACCS_onshorePV",
        ]:
            if path.exists():
                shutil.rmtree(path)
        index=ROOT / "storage_runner" / "prepared_storage_cases_index.csv"
        if index.exists():
            index.unlink()
        run([sys.executable, "tools/build_storage_base_case.py"])
        run([
            sys.executable,
            "tools/prepare_storage_cases.py",
            "--official",
            "--scenario-set",
            "spatial_legacy_full",
            "--reuse-base",
        ])

    # This is the authoritative prepared-input check and fails closed when a
    # case is absent or still points to an earlier source fingerprint.
    run([sys.executable, "tools/publication_source_gate.py", "--stage", "cases"])

    master=pd.read_csv(ROOT / "storage_runner/scenarios_storage_master.csv")
    official=master[master.v17_official_unique.astype(str).str.lower().isin({"true","1","yes"})]
    rows=[]
    for sc in official.scenario.astype(str):
        case=ROOT / "storage_cases" / sc
        pre=case / "audits" / "V17_PRE_SOLVE_VALIDATION.json"
        d=json.loads(pre.read_text(encoding="utf-8")) if pre.exists() else {"pass":False,"missing":str(pre)}
        pol=case / "audits" / "V17_SPATIAL_LEGACY_POLICY_AUDIT.json"
        pdct=json.loads(pol.read_text(encoding="utf-8")) if pol.exists() else {}
        cfp=case / "audits" / "CASE_PUBLICATION_SOURCE_FINGERPRINT.json"
        rows.append({
            "scenario":sc,
            "pre_solve_pass":bool(d.get("pass")),
            "case_fingerprint_present":cfp.is_file(),
            "legacy_mode":pdct.get("mode"),
            "target_power_mw":pdct.get("national_power_target_mw"),
            "target_energy_mwh":pdct.get("national_energy_target_mwh"),
            "deployment_cap_sum_mw":pdct.get("publication_deployment_cap_sum_mw"),
            "grandfathered_zone_count":pdct.get("grandfathered_zone_count"),
        })
    out=pd.DataFrame(rows)
    out.to_csv(ROOT / "audits/V17_PRE_SOLVE_CASE_SUMMARY.csv", index=False)
    summary={
        "version":"V17T2",
        "data_version":"NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2",
        "expected":16,
        "prepared":len(out),
        "pre_solve_passed":int(out.pre_solve_pass.sum()) if len(out) else 0,
        "case_fingerprints_present":int(out.case_fingerprint_present.sum()) if len(out) else 0,
        "all_pass":bool(len(out)==16 and out.pre_solve_pass.all() and out.case_fingerprint_present.all()),
    }
    (ROOT / "audits/V17_PRE_SOLVE_CASE_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8"
    )

    smoke_status="NOT_REQUESTED"
    if args.with_input_figure_smoke:
        pp=ROOT / "postprocess_outputs"
        if pp.exists(): shutil.rmtree(pp)
        run([sys.executable, "postprocess/build_spatial_legacy_tables.py", "--input-only"])
        run([sys.executable, "postprocess/plot_spatial_legacy_figures.py", "--input-only", "--group", "main"])
        smoke_status="PASS"
        if pp.exists(): shutil.rmtree(pp)

    component_files={
        "static_release":ROOT / "audits/V17_STATIC_RELEASE_AUDIT.json",
        "windows_launchers":ROOT / "audits/V17_WINDOWS_LAUNCHER_AUDIT.json",
        "empty_collection_safety":ROOT / "audits/V17_EMPTY_COLLECTION_SAFETY_AUDIT.json",
        "julia_lexical_architecture":ROOT / "audits/V17_JULIA_SYNTAX_AUDIT.json",
        "numerical_stability":ROOT / "audits/V17_NUMERICAL_STABILITY_AUDIT.json",
        "objective_certificate":ROOT / "audits/V17_OBJECTIVE_CERTIFICATE_AUDIT.json",
        "stage1_release_policy":ROOT / "audits/V17_RELEASE_POLICY_AUDIT.json",
        "run_readiness":ROOT / "audits/V17_RUN_READINESS_AUDIT.json",
        "input_validation":ROOT / "audits/storage_input_validation_report.json",
        "legacy_provenance":ROOT / "audits/V17_LEGACY_STORAGE_PROVENANCE_AUDIT.json",
        "publication_source":ROOT / "audits/PUBLICATION_SOURCE_GATE_SOURCE.json",
        "publication_cases":ROOT / "audits/PUBLICATION_SOURCE_GATE_CASES.json",
    }
    components={name:(json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"missing":str(path.relative_to(ROOT))}) for name,path in component_files.items()}
    report={
        "version":"V17T2",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "status":"PASS" if summary["all_pass"] else "FAIL",
        "pre_solve_summary":summary,
        "components":components,
        "input_only_figure_smoke":smoke_status,
        "julia_gurobi_runtime_check_executed_by_this_script":False,
        "solver_results_present":False,
        "publication_result_gate_status":"FAIL_RERUN_REQUIRED until the 16 current-source scenarios are solved locally",
        "validation_scope":"Current-source data closure, launcher and source checks, Julia lexical/static audits, sixteen prepared-case input fingerprints and pre-solve validations. No numerical result claim.",
        "required_local_next_step":"RUN_V17T2_CLEAN_REBUILD_AND_RUN_ALL_16_1x10.bat",
    }
    (ROOT / "audits/V17_RELEASE_BUILD_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not summary["all_pass"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
