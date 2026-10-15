#!/usr/bin/env python3
"""Build publication tables from the final R24P3 FULL8760 certificates.

The module deliberately exports robustness distance, never economic cost or
technology build.  Positive distance means that the fixed source portfolio
needs ideal local flexibility to become feasible under continuous 8760-hour
chronology.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from v17t5_paths import FULL8760_ROOT, TABLE_FULL8760
from v30_common import (
    FULL8760_SCENARIOS,
    full8760_enhanced_diagnostic_route,
    full8760_route_diagnostic_number,
    load_full8760_records,
    number,
    read_one_csv,
    resolve_full8760_output,
    validate_full8760_promoted_certificate,
    strict_solver_status,
    truth,
    write_json,
)

LABELS = {
    "TY2033_FULL8760_OBSERVED": "Observed inheritance",
    "TY2033_FULL8760_OPTIMAL": "Optimized inheritance",
    "TY2033_FULL8760_LDES_OBSERVED": "Observed + LDES",
    "TY2033_FULL8760_LDES_OPTIMAL": "Optimized + LDES",
}

def close(a: float, b: float, *, abs_tol: float = 1.0e-4, rel_tol: float = 1.0e-9) -> bool:
    return abs(a - b) <= max(abs_tol, rel_tol * max(1.0, abs(a), abs(b)))


def main() -> None:
    summary_path, records = load_full8760_records(FULL8760_ROOT)
    record_map = {str(row["scenario"]): row for row in records}
    summary_rows: list[dict] = []
    component_rows: list[dict] = []
    zone_frames: list[pd.DataFrame] = []
    quality_rows: list[dict] = []
    gate_rows: list[dict] = []

    for scenario in FULL8760_SCENARIOS:
        record = record_map[scenario]
        output = resolve_full8760_output(FULL8760_ROOT, summary_path, record)
        status = read_one_csv(output / "solve_status.csv")
        route_gates = validate_full8760_promoted_certificate(output, status, record, scenario)
        certificate_path = output / "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE.json"
        if not certificate_path.is_file():
            raise FileNotFoundError(certificate_path)
        certificate = json.loads(certificate_path.read_text(encoding="utf-8-sig"))
        if certificate.get("certificate_pass") is not True:
            raise ValueError(f"{scenario}: JSON certificate_pass=false")
        if certificate.get("scenario") != scenario or not str(certificate.get("source_manifest_sha256", "")).strip():
            raise ValueError(f"{scenario}: certificate scenario/source-manifest lineage is incomplete")

        classification = str(status.get("classification", ""))
        if classification != str(record["classification"]):
            raise ValueError(f"{scenario}: combined-summary/status classification mismatch")
        feasible = truth(status.get("original_fixed_portfolio_feasible"))
        if feasible != (record.get("original_fixed_portfolio_feasible") is True):
            raise ValueError(f"{scenario}: combined-summary/status feasibility mismatch")
        if certificate.get("classification") != classification or certificate.get("original_fixed_portfolio_feasible") is not feasible:
            raise ValueError(f"{scenario}: certificate/status classification or feasibility mismatch")
        total = number(status.get("total_ideal_flexibility_robustness_distance_mw"), field=f"{scenario}.total_distance")
        record_total = number(record.get("total_robustness_distance_mw"), field=f"{scenario}.record_distance")
        if not close(total, record_total):
            raise ValueError(f"{scenario}: combined-summary/status distance mismatch")
        firm = number(status.get("ideal_firm_capacity_repair_mw"), field=f"{scenario}.firm_distance")
        absorption = number(
            status.get("ideal_surplus_absorption_capacity_repair_mw"),
            field=f"{scenario}.absorption_distance",
        )
        if min(total, firm, absorption) < -1.0e-6 or not close(total, firm + absorption):
            raise ValueError(f"{scenario}: distance does not equal firm + absorption")

        zones_path = output / "hf18p2_robustness_distance_by_zone.csv"
        zones = pd.read_csv(zones_path)
        required_zone = {
            "LOAD_ZONE", "IdealFirmCapacityRepair_MW",
            "IdealSurplusAbsorptionCapacityRepair_MW",
            "CapacityLinkMaxViolation_MW", "AbsorptionLinkMaxViolation_MW",
        }
        if not required_zone.issubset(zones.columns) or zones["LOAD_ZONE"].astype(str).duplicated().any():
            raise ValueError(f"{scenario}: invalid zone robustness table")
        zone_firm = pd.to_numeric(zones["IdealFirmCapacityRepair_MW"], errors="raise")
        zone_abs = pd.to_numeric(zones["IdealSurplusAbsorptionCapacityRepair_MW"], errors="raise")
        if (zone_firm < -1.0e-6).any() or (zone_abs < -1.0e-6).any():
            raise ValueError(f"{scenario}: negative zone robustness distance")
        if not close(float(zone_firm.sum()), firm) or not close(float(zone_abs.sum()), absorption):
            raise ValueError(f"{scenario}: zone totals do not close to solve_status")
        zones.insert(0, "scenario", scenario)
        zones.insert(1, "case_label", LABELS[scenario])
        zones["TotalRobustnessDistance_MW"] = zone_firm + zone_abs
        zone_frames.append(zones)

        summary_rows.append({
            "scenario": scenario,
            "case_label": LABELS[scenario],
            "inheritance": "Observed" if "OBSERVED" in scenario else "Optimized",
            "ldes_enabled": "LDES" in scenario,
            "certificate_success": True,
            "classification": classification,
            "original_fixed_portfolio_feasible": feasible,
            "total_robustness_distance_mw": total,
            "ideal_firm_capacity_repair_mw": firm,
            "ideal_surplus_absorption_capacity_repair_mw": absorption,
            "source_scenario": str(status.get("source_scenario", certificate.get("source_scenario", ""))),
            "chronology": str(certificate.get("chronology", "unchanged_full_year_cyclic_8760_nonleap")),
            "certificate_origin": str(record.get("certificate_origin", "")),
            "output_directory": str(output),
        })
        for component, value in (("Ideal firm capacity", firm), ("Ideal surplus absorption", absorption)):
            component_rows.append({
                "scenario": scenario,
                "case_label": LABELS[scenario],
                "component": component,
                "robustness_distance_mw": value,
            })

        enhanced_diagnostics = full8760_enhanced_diagnostic_route(record, scenario)
        constr_sresidual = full8760_route_diagnostic_number(
            status, "gurobi_constr_sresidual", record, scenario
        )
        dual_sresidual = full8760_route_diagnostic_number(
            status, "gurobi_dual_sresidual", record, scenario
        )
        quality_values = {
            "objective_readback_error_mw": number(status.get("objective_readback_error_mw"), field=f"{scenario}.objective_readback_error_mw"),
            "primal_dual_relative_gap": number(status.get("primal_dual_relative_gap"), field=f"{scenario}.primal_dual_relative_gap"),
            "gurobi_constr_vio": number(status.get("gurobi_constr_vio"), field=f"{scenario}.gurobi_constr_vio"),
            "gurobi_bound_vio": number(status.get("gurobi_bound_vio"), field=f"{scenario}.gurobi_bound_vio"),
            "gurobi_dual_vio": number(status.get("gurobi_dual_vio"), field=f"{scenario}.gurobi_dual_vio"),
            "gurobi_compl_vio": number(status.get("gurobi_compl_vio"), field=f"{scenario}.gurobi_compl_vio"),
            "gurobi_constr_sresidual": constr_sresidual,
            "gurobi_constr_sresidual_available": constr_sresidual is not None,
            "gurobi_dual_sresidual": dual_sresidual,
            "gurobi_dual_sresidual_available": dual_sresidual is not None,
        }
        quality_rows.append({
            "scenario": scenario,
            "case_label": LABELS[scenario],
            "certificate_origin": str(record.get("certificate_origin", "")),
            "diagnostic_schema": "R24P2_PLUS_ENHANCED" if enhanced_diagnostics else "R24P1_COMMON",
            **quality_values,
        })
        gates = {
            "Native OPTIMAL": True,
            "Primal/dual feasible": truth(status.get("stage1_has_values")),
            "Route": truth(status.get("route_gate_pass")),
            "Source lineage": truth(status.get("source_lineage_gate_pass")),
            "Objective readback": truth(status.get("objective_gate_pass")),
            "Native quality": truth(status.get("native_quality_gate_pass")),
            "Pure LP": truth(status.get("pure_lp")),
            "Certificate": truth(status.get("robustness_distance_certificate_pass")),
        }
        optional_gate_labels = {
            "componentwise_native_quality_gate_pass": "Componentwise native quality",
            "maxvio_decomposition_gate_pass": "MaxVio decomposition",
            "scaled_residual_gate_pass": "Scaled residuals",
            "core_physical_quality_gate_pass": "Core physical audit",
            "physical_quality_gate_pass": "Physical audit",
        }
        for field, label in optional_gate_labels.items():
            if field in route_gates:
                gates[label] = route_gates[field]
        if not all(gates.values()):
            raise ValueError(f"{scenario}: one or more FULL8760 publication gates failed: {gates}")
        for gate, passed in gates.items():
            gate_rows.append({"scenario": scenario, "case_label": LABELS[scenario], "gate": gate, "passed": passed})

    TABLE_FULL8760.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(summary_rows)
    components = pd.DataFrame(component_rows)
    zones = pd.concat(zone_frames, ignore_index=True)
    quality = pd.DataFrame(quality_rows)
    gates = pd.DataFrame(gate_rows)
    summary.to_csv(TABLE_FULL8760 / "full8760_certificate_summary.csv", index=False)
    components.to_csv(TABLE_FULL8760 / "full8760_robustness_components.csv", index=False)
    zones.to_csv(TABLE_FULL8760 / "full8760_zone_robustness.csv", index=False)
    quality.to_csv(TABLE_FULL8760 / "full8760_numerical_quality.csv", index=False)
    gates.to_csv(TABLE_FULL8760 / "full8760_certificate_gate_matrix.csv", index=False)
    write_json(TABLE_FULL8760 / "FULL8760_PUBLICATION_CONTRACT.json", {
        "version": "V30_FULL8760_R24P3_PUBLICATION_CONTRACT",
        "status": "PASS",
        "scientific_system": "HF18 fixed-portfolio continuous-8760 minimum ideal-flexibility robustness certificate",
        "economic_reoptimization_outputs_used": False,
        "historical_attempt_directories_used": False,
        "route_versioned_diagnostic_policy": {
            "R24P1": "common native quality fields required; later scaled-residual fields exported blank with available=false",
            "R24P2_R24P3": "common and enhanced componentwise/scaled diagnostics required and finite",
            "missing_values_filled_with_zero": False,
        },
        "source_summary": str(summary_path),
        "scenario_count": 4,
        "all_certificates_success": True,
        "all_original_fixed_portfolios_feasible": bool(summary["original_fixed_portfolio_feasible"].all()),
        "metric": "minimum ideal local flexibility robustness distance (MW)",
        "unit_alignment": "Upstream MW is retained in tables and divided exactly once by 1000 only in GW-labelled figures.",
        "closure_checks": "Total MW = ideal firm MW + ideal absorption MW = sum of zone-level components.",
        "zero_interpretation": "The original fixed source portfolio is strictly feasible under continuous cyclic 8760 chronology.",
        "positive_interpretation": "A quantified lower-bound robustness gap to chronological feasibility.",
        "forbidden_interpretations": [
            "actual technology build", "economic system cost", "least-cost investment recommendation",
            "original fixed portfolio feasibility PASS when distance is positive",
        ],
    })
    print("V30 FULL8760 publication tables: PASS")


if __name__ == "__main__":
    main()
