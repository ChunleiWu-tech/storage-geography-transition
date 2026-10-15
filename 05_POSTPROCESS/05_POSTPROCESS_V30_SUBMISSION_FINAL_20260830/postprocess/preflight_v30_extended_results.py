#!/usr/bin/env python3
"""Fail-closed preflight for FULL8760 R24P3 and V20 HF5 promoted results."""
from __future__ import annotations

import json

from v17t5_paths import AUDIT_DIR, FULL8760_ROOT, V20_ROOT
from v30_common import (
    FULL8760_SCENARIOS, V20_LAYER_A_SCENARIOS, V20_LAYER_B_SCENARIOS, V20_LAYER_C_SCENARIOS,
    load_full8760_records, load_v20_layer_a_summary, load_v20_solver_summary, read_one_csv,
    resolve_full8760_output, resolve_layer_a_output, resolve_v20_output,
    resolve_v20_layer_a_root, strict_v20_status,
    validate_full8760_promoted_certificate,
    validate_v20_result_fingerprint, write_json,
)


def main() -> None:
    checks: list[dict] = []
    summary_path, records = load_full8760_records(FULL8760_ROOT)
    for record in records:
        scenario = str(record["scenario"])
        output = resolve_full8760_output(FULL8760_ROOT, summary_path, record)
        status = read_one_csv(output / "solve_status.csv")
        try:
            gates = validate_full8760_promoted_certificate(output, status, record, scenario)
            checks.append({
                "source": "FULL8760", "scenario": scenario, "passed": True,
                "certificate_origin": record.get("certificate_origin", ""),
                "route_specific_gates": gates, "failure": "", "output": str(output),
            })
        except Exception as exc:
            checks.append({
                "source": "FULL8760", "scenario": scenario, "passed": False,
                "certificate_origin": record.get("certificate_origin", ""),
                "route_specific_gates": {}, "failure": str(exc), "output": str(output),
            })
    if {row["scenario"] for row in checks if row["source"] == "FULL8760"} != set(FULL8760_SCENARIOS):
        raise ValueError("FULL8760 preflight scenario set mismatch")

    layer_a_summary = load_v20_layer_a_summary(V20_ROOT)
    load_v20_solver_summary(V20_ROOT, "B")
    load_v20_solver_summary(V20_ROOT, "C")
    layer_a_root = resolve_v20_layer_a_root(V20_ROOT)
    for scenario in V20_LAYER_A_SCENARIOS:
        output = resolve_layer_a_output(V20_ROOT, scenario)
        try:
            strict_v20_status(read_one_csv(output / "solve_status.csv"), scenario, "A")
            validate_v20_result_fingerprint(
                layer_a_root, output, layer_a_root / "future_correction_cases" / scenario, scenario
            )
            checks.append({"source": "V20_LAYER_A", "scenario": scenario, "passed": True, "failure": "", "output": str(output)})
        except Exception as exc:
            checks.append({"source": "V20_LAYER_A", "scenario": scenario, "passed": False, "failure": str(exc), "output": str(output)})
    for layer, scenarios in (("V20_LAYER_B", V20_LAYER_B_SCENARIOS), ("V20_LAYER_C", V20_LAYER_C_SCENARIOS)):
        layer_code = layer[-1]
        for scenario in scenarios:
            output = resolve_v20_output(V20_ROOT, scenario)
            try:
                strict_v20_status(read_one_csv(output / "solve_status.csv"), scenario, layer_code)
                validate_v20_result_fingerprint(
                    V20_ROOT, output, V20_ROOT / "storage_cases" / scenario, scenario
                )
                checks.append({"source": layer, "scenario": scenario, "passed": True, "failure": "", "output": str(output)})
            except Exception as exc:
                checks.append({"source": layer, "scenario": scenario, "passed": False, "failure": str(exc), "output": str(output)})

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    passed = len(checks) == 30 and all(row["passed"] for row in checks)
    report = {
        "version": "V30_EXTENDED_RESULT_PREFLIGHT_R3", "status": "PASS" if passed else "FAIL",
        "full8760_root": str(FULL8760_ROOT), "v20_root": str(V20_ROOT),
        "full8760_certificates": 4, "v20_strict_results": 26,
        "strict_solver_status_revalidated": True,
        "source_case_result_fingerprints_revalidated": True,
        "full8760_scientific_system": "HF18 fixed-portfolio continuous-8760 minimum ideal-flexibility robustness certificate",
        "full8760_economic_reoptimization_outputs_used": False,
        "historical_attempt_directories_used": False,
        "layer_a_upstream_summary_rows_present": int(layer_a_summary["summary_row_present"].sum()),
        "layer_a_rows_reconstructed_from_promoted_outputs": int((~layer_a_summary["summary_row_present"]).sum()),
        "layer_a_summary_is_non_authoritative_index": True,
        "attempt_directories_consulted": False,
        "upstream_write_performed": False,
        "failed": [row for row in checks if not row["passed"]],
        "checks": checks,
    }
    write_json(AUDIT_DIR / "V30_EXTENDED_RESULT_PREFLIGHT.json", report)
    if not passed:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise ValueError("Extended-result preflight did not close all 4 + 26 cases; see failed records above")
    print(json.dumps({"status": "PASS", "full8760": 4, "v20": 26}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
