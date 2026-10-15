#!/usr/bin/env python3
"""Write immutable result lineage after a complete strict solver batch."""
from __future__ import annotations
from pathlib import Path
import argparse
import json
import time

import pandas as pd

from publication_source_contract import DATA_VERSION, sha256, source_fingerprint_sha256

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["main", "sensitivity"], required=True)
    args = ap.parse_args()
    if args.kind == "main":
        scen = pd.read_csv(ROOT / "storage_runner/scenarios_storage_master.csv")
        mask = scen["v17_official_unique"].astype(str).str.lower().isin({"true", "1", "yes"})
        names = scen.loc[mask, "scenario"].astype(str).tolist()
        cases = ROOT / "storage_cases"
        outputs = ROOT / "outputs"
        summary = ROOT / "storage_runner/storage_batch_run_summary.csv"
    else:
        names = pd.read_csv(ROOT / "storage_runner/scenarios_targetyear_linked.csv")["scenario"].astype(str).tolist()
        cases = ROOT / "sensitivity_cases"
        outputs = ROOT / "sensitivity_outputs"
        summary = ROOT / "sensitivity_outputs/V17T2R6_FULL8760_run_summary.csv"
    if not summary.is_file():
        raise FileNotFoundError(summary)
    table = pd.read_csv(summary)
    ok_names = set(table.loc[table["publication_strict_success"].astype(str).str.lower().isin({"true", "1", "yes"}), "scenario"].astype(str))
    if ok_names != set(names):
        raise ValueError(f"Strict-success scenarios do not close: {sorted(ok_names)} != {sorted(names)}")
    rows = []
    for scenario in names:
        case = cases / scenario
        out = outputs / f"{scenario}__main"
        status = out / "solve_status.csv"
        if not status.is_file():
            raise FileNotFoundError(status)
        s = pd.read_csv(status)
        if len(s) != 1 or str(s.iloc[0].get("stage1_termination_status", "")) != "OPTIMAL":
            raise ValueError(f"{scenario} lacks a strict OPTIMAL solve status")
        meta_path = case / ("STORAGE_SCENARIO_META.json" if args.kind == "main" else "SENSITIVITY_SCENARIO_META.json")
        if not meta_path.is_file():
            raise FileNotFoundError(meta_path)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("publication_source_data_version") != DATA_VERSION:
            raise ValueError(f"{scenario} case metadata data version is stale")
        if meta.get("publication_source_fingerprint_sha256") != source_fingerprint_sha256():
            raise ValueError(f"{scenario} case metadata source fingerprint is stale")
        legacy_audit = case / "audits" / (
            "V17_SPATIAL_LEGACY_POLICY_AUDIT.json" if args.kind == "sensitivity"
            else "legacy_storage_allocation_audit.json"
        )
        row = {
            "scenario": scenario,
            "case_meta_sha256": sha256(meta_path),
            "legacy_policy_audit_sha256": sha256(legacy_audit),
            "vre_application_audit_sha256": sha256(case / "audits/vre_cf_application_audit.json"),
            "storage_application_audit_sha256": sha256(case / "audits/existing_storage_application_audit.json"),
            "solve_status_sha256": sha256(status),
        }
        if args.kind == "sensitivity":
            row.update({
                "full8760_input_validation_sha256": sha256(case / "audits/FULL8760_PREPARED_INPUT_VALIDATION.json"),
                "full8760_temporal_input_audit_sha256": sha256(case / "audits/FULL8760_TEMPORAL_INPUT_AUDIT.json"),
                "result_fingerprint_sha256": sha256(out / "PUBLICATION_RESULT_FINGERPRINT.json"),
            })
        rows.append(row)
    payload = {
        "status": "PASS",
        "package_kind": args.kind,
        "data_version": DATA_VERSION,
        "publication_source_fingerprint_sha256": source_fingerprint_sha256(),
        "generated_local_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scenario_count": len(names),
        "scenarios": names,
        "summary_sha256": sha256(summary),
        "scenario_lineage": rows,
    }
    out = ROOT / "audits/PUBLICATION_RESULT_LINEAGE.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
