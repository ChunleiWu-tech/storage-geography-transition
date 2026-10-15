#!/usr/bin/env python3
"""Strict preflight for the eight target-year official outputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from targetyear_sensitivity_common import (
    REQUIRED_RESULT_FILES,
    legacy_map,
    ldes_proxy_frame,
    output_dir,
    physical_pass,
    read_csv,
    _strict_physical_bool,
    registry,
    status_record,
    strict_status_failures,
)
from v17t5_paths import AUDIT_DIR, TARGETYEAR_OUTPUTS, TARGETYEAR_ROOT


def sha256(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_result_lineage(expected_scenarios: list[str]) -> dict[str, object]:
    """Revalidate or reconstruct the strict promoted-result lineage.

    ``PUBLICATION_RESULT_LINEAGE.json`` was written only by the final wrapper
    used in later V17T2R5 runs.  Earlier strict-success runs have the same
    promoted ``__main`` outputs, summary and case/source identity records but
    may not have this convenience index.  In that case we deterministically
    rebuild the index from those authoritative files; solver/physical gates are
    still re-applied to every output in ``main`` below.
    """
    lineage_path = TARGETYEAR_ROOT / "audits" / "PUBLICATION_RESULT_LINEAGE.json"
    source_path = TARGETYEAR_ROOT / "audits" / "PUBLICATION_SOURCE_FINGERPRINT.json"
    summary_path = TARGETYEAR_OUTPUTS / "V17T2R5_run_summary.csv"
    source = json.loads(source_path.read_text(encoding="utf-8-sig"))
    source_sha = sha256(source_path)
    summary_present = summary_path.is_file()
    summary_names: list[str] = []
    summary_strict_names: list[str] = []
    summary_parse_error = ""
    if summary_present:
        try:
            summary = pd.read_csv(summary_path)
            if "scenario" not in summary.columns or "publication_strict_success" not in summary.columns:
                raise ValueError("required scenario/publication_strict_success columns are absent")
            summary_names = summary["scenario"].astype(str).tolist()
            strict_mask = summary["publication_strict_success"].map(
                lambda value: str(value).strip().lower() in {"true", "1", "1.0", "yes"}
            )
            summary_strict_names = summary.loc[strict_mask, "scenario"].astype(str).tolist()
        except Exception as exc:
            summary_parse_error = str(exc)
    summary_exact_unique_strict_set = bool(
        not summary_parse_error
        and len(summary_names) == len(expected_scenarios)
        and len(summary_names) == len(set(summary_names))
        and set(summary_names) == set(expected_scenarios)
        and set(summary_strict_names) == set(expected_scenarios)
    )
    summary_audit = {
        "present": summary_present,
        "parse_error": summary_parse_error,
        "row_count": len(summary_names),
        "scenario_names": summary_names,
        "strict_success_names": summary_strict_names,
        "exact_unique_strict_scenario_set": summary_exact_unique_strict_set,
        "authoritative_for_release": False,
    }

    live_rows: list[dict[str, object]] = []
    optional_case_audits_complete = True
    for scenario in expected_scenarios:
        case = TARGETYEAR_ROOT / "sensitivity_cases" / scenario
        output = TARGETYEAR_OUTPUTS / f"{scenario}__main"
        required_hashes = {
            "case_meta_sha256": case / "SENSITIVITY_SCENARIO_META.json",
            "solve_status_sha256": output / "solve_status.csv",
        }
        optional_hashes = {
            "legacy_policy_audit_sha256": case / "audits" / "legacy_storage_allocation_audit.json",
            "vre_application_audit_sha256": case / "audits" / "vre_cf_application_audit.json",
            "storage_application_audit_sha256": case / "audits" / "existing_storage_application_audit.json",
        }
        meta = json.loads(required_hashes["case_meta_sha256"].read_text(encoding="utf-8-sig"))
        if (
            meta.get("publication_source_data_version") != source.get("data_version")
            or str(meta.get("publication_source_fingerprint_sha256", "")).lower() != source_sha
        ):
            raise ValueError(f"{scenario}: case metadata does not identify the active publication source")
        missing_optional = [field for field, path in optional_hashes.items() if not path.is_file()]
        optional_case_audits_complete = optional_case_audits_complete and not missing_optional
        live_rows.append({
            "scenario": scenario,
            **{field: sha256(path) for field, path in required_hashes.items()},
            **{field: sha256(path) for field, path in optional_hashes.items() if path.is_file()},
            "optional_case_input_audit_hashes_complete": not missing_optional,
            "missing_optional_case_input_audit_hash_fields": missing_optional,
        })

    if not lineage_path.is_file():
        return {
            "mode": "reconstructed_from_strict_summary_case_source_and_promoted_outputs",
            "path": "",
            "precomputed_lineage_present": False,
            "scenario_count": len(live_rows),
            "summary_sha256": sha256(summary_path) if summary_present else "",
            "summary_audit": summary_audit,
            "source_fingerprint_sha256": source_sha,
            "optional_case_input_audit_hashes_complete": optional_case_audits_complete,
            "scenario_lineage": live_rows,
        }

    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    rows = list(lineage.get("scenario_lineage", []))
    precomputed_identity_pass = bool(
        lineage.get("status") == "PASS"
        and lineage.get("package_kind") == "sensitivity"
        and int(lineage.get("scenario_count", -1)) == len(expected_scenarios)
        and set(lineage.get("scenarios", [])) == set(expected_scenarios)
        and str(lineage.get("publication_source_fingerprint_sha256", "")).lower() == source_sha
        and len(rows) == len(expected_scenarios)
        and {str(row.get("scenario", "")) for row in rows} == set(expected_scenarios)
    )
    precomputed_hashes_pass = precomputed_identity_pass and optional_case_audits_complete
    if precomputed_hashes_pass:
        by_scenario = {str(row["scenario"]): row for row in rows}
        for live in live_rows:
            declared = by_scenario[live["scenario"]]
            if any(
                str(declared.get(field, "")).lower() != value
                for field, value in live.items()
                if field.endswith("_sha256")
            ):
                precomputed_hashes_pass = False
                break
    precomputed_summary_hash_pass = bool(
        summary_present
        and str(lineage.get("summary_sha256", "")).lower() == sha256(summary_path)
    )
    if not (precomputed_identity_pass and precomputed_hashes_pass):
        return {
            "mode": "reconstructed_from_case_source_and_promoted_outputs_stale_optional_indices_ignored",
            "path": str(lineage_path),
            "precomputed_lineage_present": True,
            "precomputed_identity_pass": precomputed_identity_pass,
            "precomputed_result_hashes_pass": precomputed_hashes_pass,
            "precomputed_summary_hash_pass": precomputed_summary_hash_pass,
            "scenario_count": len(live_rows),
            "summary_sha256": sha256(summary_path) if summary_present else "",
            "summary_audit": summary_audit,
            "source_fingerprint_sha256": source_sha,
            "optional_case_input_audit_hashes_complete": optional_case_audits_complete,
            "scenario_lineage": live_rows,
        }
    return {
        "mode": "precomputed_lineage_revalidated",
        "path": str(lineage_path),
        "precomputed_lineage_present": True,
        "scenario_count": len(rows),
        "summary_sha256": sha256(summary_path) if summary_present else "",
        "precomputed_summary_hash_pass": precomputed_summary_hash_pass,
        "summary_audit": summary_audit,
        "source_fingerprint_sha256": source_sha,
        "optional_case_input_audit_hashes_complete": optional_case_audits_complete,
    }


def main() -> None:
    scenarios = registry()
    lineage_audit = validate_result_lineage(scenarios["scenario"].astype(str).tolist())
    upstream_audit_files = [
        TARGETYEAR_ROOT / "audits" / "V17T2R5_MODEL_LINEAGE.json",
        TARGETYEAR_ROOT / "audits" / "STATIC_PACKAGE_AUDIT_V17T2R5.json",
        TARGETYEAR_ROOT / "audits" / "V17T2R5_PAIR_IDENTITY_AUDIT.json",
    ]
    upstream_audit_failures = []
    for path in upstream_audit_files:
        if not path.is_file():
            upstream_audit_failures.append(f"missing:{path.name}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if str(payload.get("status", "")).upper() != "PASS":
            upstream_audit_failures.append(f"not_PASS:{path.name}")
    rows: list[dict[str, object]] = []
    for expected in scenarios.itertuples(index=False):
        row = pd.Series(expected._asdict())
        scenario = str(row["scenario"])
        folder = output_dir(scenario)
        missing = [name for name in REQUIRED_RESULT_FILES if not (folder / name).is_file()]
        status_failures: list[str] = []
        physical_failures: list[str] = []
        physical_soft_failures: list[str] = []
        identity_sources_json = ""
        zones = 0
        power_total = float("nan")
        energy_total = float("nan")
        ldes_proxy_rows = -1
        ldes_export_failures: list[str] = []
        if not missing:
            try:
                status = status_record(scenario)
                identity_sources_json = str(status.get("_identity_sources_json", ""))
                status_failures = strict_status_failures(status, row)
            except Exception as exc:
                status_failures = [str(exc)]
            try:
                ok, physical_failures = physical_pass(scenario)
                if not ok and not physical_failures:
                    physical_failures = ["physical audit failed"]
                physical_frame = read_csv(folder / "physical_audit_summary.csv")
                lower_to_actual = {str(c).strip().lower(): c for c in physical_frame.columns}
                if "hard_gate" in lower_to_actual and "pass" in lower_to_actual:
                    hard_col = lower_to_actual["hard_gate"]
                    pass_col = lower_to_actual["pass"]
                    for idx, audit_row in physical_frame.iterrows():
                        hard = _strict_physical_bool(audit_row[hard_col], field="hard_gate", row_index=int(idx))
                        passed_token = _strict_physical_bool(audit_row[pass_col], field="pass", row_index=int(idx))
                        if (not hard) and (not passed_token):
                            physical_soft_failures.append(
                                f"{audit_row.get('audit_file', 'unknown_audit_file')}:{audit_row.get('check', f'row_{idx}')}"
                            )
            except Exception as exc:
                physical_failures = [str(exc)]
            try:
                legacy = legacy_map(scenario)
                zones = len(legacy)
                power_total = float(legacy["realized_legacy_power_mw"].sum())
                energy_total = float(legacy["realized_legacy_energy_mwh"].sum())
            except Exception as exc:
                status_failures.append(f"legacy audit: {exc}")
            try:
                ldes_proxy_rows = len(ldes_proxy_frame(scenario))
            except Exception as exc:
                ldes_export_failures = [str(exc)]
        passed = folder.is_dir() and not missing and not status_failures and not physical_failures and not ldes_export_failures and zones == 32 and not upstream_audit_failures
        rows.append(
            {
                "scenario": scenario,
                "pair_id": str(row["pair_id"]),
                "target_year": int(row["target_year"]),
                "official_output_exists": folder.is_dir(),
                "missing_files": ";".join(missing),
                "status_failures": ";".join(status_failures),
                "identity_sources_json": identity_sources_json,
                "physical_failures": ";".join(physical_failures),
                "physical_soft_failures_disclosure_only": ";".join(physical_soft_failures),
                "legacy_zone_count": zones,
                "legacy_power_total_mw": power_total,
                "legacy_energy_total_mwh": energy_total,
                "ldes_proxy_rows": ldes_proxy_rows,
                "ldes_export_failures": ";".join(ldes_export_failures),
                "pass": passed,
            }
        )
    frame = pd.DataFrame(rows)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(AUDIT_DIR / "targetyear_preflight_scenario_audit.csv", index=False)
    summary = {
        "version": "V17T5R6R8R5",
        "targetyear_upstream_version": "V17T2R5",
        "targetyear_root": str(TARGETYEAR_ROOT),
        "targetyear_outputs": str(TARGETYEAR_OUTPUTS),
        "expected_scenarios": 8,
        "passed_scenarios": int(frame["pass"].sum()),
        "all_pass": bool(frame["pass"].all()),
        "scope": "separate single-target-year linked-SOC sensitivity; not merged into the V17T1 multi-period upstream",
        "strict_success_summary_and_result_lineage_revalidated": True,
        "attempt_directories_consulted": False,
        "result_lineage": lineage_audit,
        "upstream_audit_failures": upstream_audit_failures,
        "failed": frame.loc[~frame["pass"], "scenario"].tolist(),
    }
    (AUDIT_DIR / "targetyear_preflight.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["all_pass"]:
        print(frame.loc[~frame["pass"]].to_string(index=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
