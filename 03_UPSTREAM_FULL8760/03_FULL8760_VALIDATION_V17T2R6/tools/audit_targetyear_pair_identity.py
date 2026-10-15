#!/usr/bin/env python3
"""Audit that each V17T2R6 full-8760 observed/optimized pair changes geography only."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
from typing import Any

import pandas as pd

from publication_source_contract import expected_storage_power_mw, expected_storage_energy_mwh

ROOT = Path(__file__).resolve().parents[1]
SCEN = ROOT / "storage_runner" / "scenarios_targetyear_linked.csv"
OUT = ROOT / "audits" / "V17T2R6_FULL8760_PAIR_IDENTITY_AUDIT.json"
ALLOWED_DIFFERENT_INPUT_FILES = {"legacy_storage_policy.csv", "gen_build_predetermined.csv"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for b in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def canonical_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    cols = sorted(df.columns)
    work = df[cols].copy()
    for c in cols:
        work[c] = work[c].astype(str)
    return work.sort_values(cols).to_dict(orient="records")


def audit_pair(pair_id: str, observed: str, optimized: str) -> dict[str, Any]:
    obs = ROOT / "sensitivity_cases" / observed / "inputs"
    opt = ROOT / "sensitivity_cases" / optimized / "inputs"
    errors: list[str] = []
    file_rows: list[dict[str, Any]] = []
    obs_files = {p.name for p in obs.glob("*.csv")}
    opt_files = {p.name for p in opt.glob("*.csv")}
    if obs_files != opt_files:
        errors.append(f"Input file sets differ: observed-only={sorted(obs_files-opt_files)}, optimized-only={sorted(opt_files-obs_files)}")
    for name in sorted(obs_files & opt_files):
        equal = sha(obs / name) == sha(opt / name)
        allowed = name in ALLOWED_DIFFERENT_INPUT_FILES
        file_rows.append({"file": name, "byte_identical": equal, "difference_allowed": allowed})
        if not equal and not allowed:
            errors.append(f"Non-geographic input differs: {name}")

    # Predetermined table: only 2023 Battery rows may differ.
    gen = pd.read_csv(obs / "gen_info.csv")
    batteries = set(gen.loc[gen["gen_tech"].astype(str).eq("Battery"), "GENERATION_PROJECT"].astype(str))
    op = pd.read_csv(obs / "gen_build_predetermined.csv")
    pp = pd.read_csv(opt / "gen_build_predetermined.csv")
    omask = op["GENERATION_PROJECT"].astype(str).isin(batteries) & pd.to_numeric(op["build_year"], errors="raise").eq(2023)
    pmask = pp["GENERATION_PROJECT"].astype(str).isin(batteries) & pd.to_numeric(pp["build_year"], errors="raise").eq(2023)
    if canonical_rows(op.loc[~omask]) != canonical_rows(pp.loc[~pmask]):
        errors.append("gen_build_predetermined.csv differs outside 2023 Battery rows")
    obs_legacy_power = float(pd.to_numeric(op.loc[omask, "build_gen_predetermined"], errors="coerce").sum())
    obs_legacy_energy = float(pd.to_numeric(op.loc[omask, "build_gen_energy_predetermined"], errors="coerce").sum())
    if abs(obs_legacy_power - expected_storage_power_mw()) > 0.1 or abs(obs_legacy_energy - expected_storage_energy_mwh()) > 0.1:
        errors.append("Reference 2023-labelled Battery predetermined totals do not close to the publication source contract")
    if int(pmask.sum()) != 0:
        errors.append("Optimized reallocation case must not contain fixed 2023 Battery predetermined rows")

    # Policy table: identification constants and feasible envelope must be identical.
    ol = pd.read_csv(obs / "legacy_storage_policy.csv").sort_values("model_zone").reset_index(drop=True)
    pl = pd.read_csv(opt / "legacy_storage_policy.csv").sort_values("model_zone").reset_index(drop=True)
    invariant = [
        "model_zone", "battery_project", "legacy_reference_case",
        "national_power_target_mw", "national_energy_target_mwh", "standardized_duration_h",
        "empirical_cap_quantile", "empirical_cap_ratio_to_2023_peak", "zone_peak_2023_mw",
        "raw_empirical_power_cap_mw", "legacy_power_cap_mw", "observed_grandfathered_cap_floor",
        "legacy_cap_scope", "legacy_capex_treatment",
    ]
    if canonical_rows(ol[invariant]) != canonical_rows(pl[invariant]):
        errors.append("legacy_storage_policy identification constants differ within pair")
    if set(ol["legacy_allocation_mode"].astype(str)) != {"observed_standardized"}:
        errors.append("Reference member is not observed_standardized")
    if set(pl["legacy_allocation_mode"].astype(str)) != {"optimized_reallocation"}:
        errors.append("Optimized member is not optimized_reallocation")

    result = {
        "pair_id": pair_id,
        "observed_scenario": observed,
        "optimized_scenario": optimized,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "allowed_input_differences": sorted(ALLOWED_DIFFERENT_INPUT_FILES),
        "file_comparison": file_rows,
        "observed_fixed_legacy_power_mw": obs_legacy_power,
        "observed_fixed_legacy_energy_mwh": obs_legacy_energy,
        "optimized_fixed_2023_battery_row_count": int(pmask.sum()),
        "identification_statement": (
            "All non-geographic inputs are byte-identical. The reference member fixes the standardized "
            "2025 inherited Battery stock by model zone; the optimized member endogenizes only that same-total "
            "2023-labelled allocation under the identical empirical deployment envelope."
        ),
    }
    return result


def audit_all_pairs(raise_on_error: bool = True) -> dict[str, Any]:
    df = pd.read_csv(SCEN)
    results = []
    for pair_id, grp in df.groupby("pair_id", sort=True):
        obs_rows = grp.loc[grp["legacy_allocation_mode"].eq("observed_standardized"), "scenario"].astype(str).tolist()
        opt_rows = grp.loc[grp["legacy_allocation_mode"].eq("optimized_reallocation"), "scenario"].astype(str).tolist()
        if len(obs_rows) != 1 or len(opt_rows) != 1:
            results.append({"pair_id": pair_id, "status": "FAIL", "errors": ["Pair must contain one observed and one optimized member"]})
            continue
        results.append(audit_pair(str(pair_id), obs_rows[0], opt_rows[0]))
    report = {
        "version": "V17T2R6_FULL8760",
        "status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
        "pairs": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    if raise_on_error and report["status"] != "PASS":
        raise ValueError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    print(json.dumps(audit_all_pairs(raise_on_error=True), ensure_ascii=False, indent=2))
