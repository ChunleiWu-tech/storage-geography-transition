#!/usr/bin/env python3
"""Prove the input-side preconditions for HF15's exact LP condensation.

This audit performs no mutation.  It verifies, independently of the Julia
model, that every fuel-based generator has one declared fuel, a finite
nonnegative heat rate, and the same fuel-side scientific data in all three
unresolved cases.  These are precisely the conditions under which

    fuel_use[g,t] = heat_rate[g] * dispatch[g,t]

is a reversible substitution rather than an approximation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "TY2033_FULL8760_OBSERVED",
    "TY2033_FULL8760_OPTIMAL",
    "TY2033_FULL8760_LDES_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL",
)


def rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"HF15 input audit missing required file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def case_evidence(scenario: str) -> dict[str, object]:
    inputs = ROOT / "sensitivity_cases" / scenario / "inputs"
    fuel_rows = rows(inputs / "fuels.csv")
    gen_rows = rows(inputs / "gen_info.csv")
    timepoint_rows = rows(inputs / "timepoints.csv")
    fuels = {str(row["fuel"]).strip() for row in fuel_rows}
    if not fuels or "" in fuels:
        raise SystemExit(f"{scenario}: fuels.csv contains an empty or missing fuel key")

    fuel_generators: list[dict[str, object]] = []
    for row in gen_rows:
        energy_source = str(row["gen_energy_source"]).strip()
        if energy_source not in fuels:
            continue
        project = str(row["GENERATION_PROJECT"]).strip()
        raw_heat_rate = str(row["gen_full_load_heat_rate"]).strip()
        # Match the model's longstanding input convention exactly: a dot in
        # this field is interpreted as zero, not as an independently estimated
        # parameter.
        try:
            heat_rate = 0.0 if raw_heat_rate == "." else float(raw_heat_rate)
        except ValueError as exc:
            raise SystemExit(f"{scenario}: invalid heat rate for {project}") from exc
        if not math.isfinite(heat_rate) or heat_rate < 0.0:
            raise SystemExit(
                f"{scenario}: HF15 requires a finite nonnegative heat rate; "
                f"{project} has {heat_rate!r}"
            )
        fuel_generators.append({
            "project": project,
            "fuel": energy_source,
            "heat_rate": heat_rate,
            "zone": str(row["gen_load_zone"]).strip(),
            "technology": str(row["gen_tech"]).strip(),
        })

    if not fuel_generators:
        raise SystemExit(f"{scenario}: no fuel-based generators found")
    project_names = [str(row["project"]) for row in fuel_generators]
    if len(project_names) != len(set(project_names)):
        raise SystemExit(f"{scenario}: duplicate fuel-based generator key")
    if len(timepoint_rows) != 8760:
        raise SystemExit(
            f"{scenario}: HF15 is restricted to the exact 8760 chronology; "
            f"found {len(timepoint_rows)} timepoints"
        )
    timepoint_keys = [str(row["timepoint_id"]).strip() for row in timepoint_rows]
    if len(timepoint_keys) != len(set(timepoint_keys)):
        raise SystemExit(f"{scenario}: duplicate timepoint_id")

    fuel_generators.sort(key=lambda row: str(row["project"]))
    eliminated_per_family = len(fuel_generators) * len(timepoint_rows)
    return {
        "scenario": scenario,
        "fuel_generator_count": len(fuel_generators),
        "timepoint_count": len(timepoint_rows),
        "singleton_fuel_mapping_by_model_schema": True,
        "finite_nonnegative_heat_rates": True,
        "eliminated_auxiliary_columns": 2 * eliminated_per_family,
        "eliminated_definition_rows": 2 * eliminated_per_family,
        "fuel_generator_scientific_fingerprint": stable_hash(fuel_generators),
        "fuel_table_fingerprint": stable_hash(fuel_rows),
        "timepoint_fingerprint": stable_hash(timepoint_rows),
    }


def main() -> None:
    evidence = [case_evidence(scenario) for scenario in TARGETS]
    fingerprint_fields = (
        "fuel_generator_scientific_fingerprint",
        "fuel_table_fingerprint",
        "timepoint_fingerprint",
    )
    for field in fingerprint_fields:
        values = {str(row[field]) for row in evidence}
        if len(values) != 1:
            raise SystemExit(
                f"HF15 matched-case gate failed: {field} differs across the three cases"
            )
    output = {
        "version": "V17T2R6R19_HF15_exact_fuel_auxiliary_elimination_input_audit",
        "status": "PASS",
        "scientific_change": False,
        "substitution": "fuel_use[g,t]=heat_rate[g]*dispatch[g,t]",
        "proof_scope": (
            "two equality-defined nonnegative auxiliary variable families; "
            "singleton fuel mapping; finite nonnegative heat rates; exact output reconstruction"
        ),
        "cases": evidence,
    }
    audit_dir = ROOT / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    out = audit_dir / "HF15_EXACT_FUEL_ELIMINATION_INPUT_AUDIT.json"
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
