#!/usr/bin/env python3
"""Strict input validation for the 4 h and 1 h target-year linked-SOC cases."""
from __future__ import annotations

from pathlib import Path
import argparse
import json
from typing import Any

import pandas as pd

from publication_source_contract import expected_storage_power_mw, expected_storage_energy_mwh

ANCHOR = 2023
ALLOWED_TARGETS = {2028, 2033}
REQUIRED = [
    "periods.csv", "timeseries.csv", "timepoints.csv", "gen_info.csv",
    "gen_build_costs.csv", "gen_build_predetermined.csv", "legacy_storage_policy.csv",
    "loads.csv", "variable_capacity_factors.csv", "hydro_timeseries.csv",
    "carbon_policies.csv", "capacity_plans.csv", "zone_coincident_peak_demand.csv",
]


def _bool(v: Any) -> bool:
    return str(v).strip().lower() in {"true", "1", "yes", "y", "t"}


def validate_case(case_dir: str | Path, meta: dict | None = None, raise_on_error: bool = True) -> dict[str, Any]:
    case_dir = Path(case_dir)
    inp = case_dir / "inputs"
    errors: list[str] = []
    checks: dict[str, Any] = {}
    for name in REQUIRED:
        ok = (inp / name).is_file()
        checks[f"required_{name}"] = ok
        if not ok:
            errors.append(f"Missing inputs/{name}")
    if errors:
        result = {"status": "FAIL", "errors": errors, "checks": checks}
        if raise_on_error:
            raise ValueError(json.dumps(result, indent=2))
        return result

    periods = pd.read_csv(inp / "periods.csv")
    pvals = pd.to_numeric(periods["INVESTMENT_PERIOD"], errors="raise").astype(int).tolist()
    pvals = sorted(pvals)
    checks["periods"] = pvals
    if len(pvals) != 2 or pvals[0] != ANCHOR or pvals[1] not in ALLOWED_TARGETS:
        errors.append(f"Expected [2023, one of {sorted(ALLOWED_TARGETS)}], found {pvals}")
    target = pvals[1] if len(pvals) == 2 else None
    if meta and target is not None and int(meta.get("target_year")) != target:
        errors.append(f"Metadata target_year={meta.get('target_year')} does not match periods target={target}")

    ts = pd.read_csv(inp / "timeseries.csv")
    tp = pd.read_csv(inp / "timepoints.csv")
    checks["timeseries_rows"] = len(ts)
    checks["timepoint_rows"] = len(tp)
    if len(ts) != 12:
        errors.append(f"Expected 12 target-year timeseries, found {len(ts)}")
    expected_resolution_h = int(meta.get("time_resolution_h", 4)) if meta else int(round(float(pd.to_numeric(ts["ts_duration_of_tp"], errors="raise").iloc[0])))
    expected_tps_per_day = {4: 6, 1: 24}.get(expected_resolution_h)
    expected_timepoints = {4: 72, 1: 288}.get(expected_resolution_h)
    checks["time_resolution_h"] = expected_resolution_h
    if expected_timepoints is None:
        errors.append(f"Unsupported time resolution {expected_resolution_h} h")
        expected_timepoints = -1
        expected_tps_per_day = -1
    if len(tp) != expected_timepoints:
        errors.append(f"Expected {expected_timepoints} target-year timepoints, found {len(tp)}")
    if target is not None:
        ts_periods = sorted(pd.to_numeric(ts["ts_period"], errors="raise").astype(int).unique().tolist())
        checks["timeseries_periods"] = ts_periods
        if ts_periods != [target]:
            errors.append(f"Timeseries period must be only {target}, found {ts_periods}")
    counts = tp.groupby("timeseries").size()
    if not (counts == expected_tps_per_day).all():
        errors.append(f"Every representative day must contain exactly {expected_tps_per_day} timepoints")
    durations = pd.to_numeric(ts["ts_duration_of_tp"], errors="raise")
    if not durations.sub(float(expected_resolution_h)).abs().lt(1e-9).all():
        errors.append(f"Every timepoint must represent {expected_resolution_h} hours")
    plen = dict(zip(
        pd.to_numeric(periods["INVESTMENT_PERIOD"], errors="raise").astype(int),
        pd.to_numeric(periods["period_end"], errors="raise") - pd.to_numeric(periods["period_start"], errors="raise") + 1,
    ))
    if target is not None:
        repeats = pd.to_numeric(ts["ts_scale_to_period"], errors="raise") / float(plen[target])
        checks["representative_days_per_year"] = float(repeats.sum())
        if not all(x > 0 and abs(x - round(x)) < 1e-8 for x in repeats):
            errors.append("Month repeat counts must be positive integers")
        if abs(float(repeats.sum()) - 365.0) > 1e-8:
            errors.append(f"Representative days sum to {repeats.sum()}, not 365")

    # Time-dependent tables must contain no non-target timepoints or months.
    tp_ids = set(tp["timepoint_id"].astype(str))
    ts_ids = set(ts["TIMESERIES"].astype(str))
    loads = pd.read_csv(inp / "loads.csv")
    if not set(loads["TIMEPOINT"].astype(str)) <= tp_ids:
        errors.append("loads.csv contains non-target timepoints")
    vcf = pd.read_csv(inp / "variable_capacity_factors.csv")
    if not set(vcf["timepoint"].astype(str)) <= tp_ids:
        errors.append("variable_capacity_factors.csv contains non-target timepoints")
    cf = pd.to_numeric(vcf["gen_max_capacity_factor"], errors="coerce")
    if cf.isna().any() or not cf.between(0.0, 1.0).all():
        errors.append("variable_capacity_factors.csv must be numeric and bounded to [0,1]")
    hydro = pd.read_csv(inp / "hydro_timeseries.csv")
    if not set(hydro["timeseries"].astype(str)) <= ts_ids:
        errors.append("hydro_timeseries.csv contains non-target timeseries")

    # New capacity is allowed only in the selected target-year vintage.
    costs = pd.read_csv(inp / "gen_build_costs.csv")
    build_years = sorted(pd.to_numeric(costs["build_year"], errors="raise").astype(int).unique().tolist())
    future_vintages = [y for y in build_years if y > ANCHOR]
    checks["future_build_vintages"] = future_vintages
    if target is not None and future_vintages != [target]:
        errors.append(f"Expected only target-year new-build vintage [{target}], found {future_vintages}")

    # Period-indexed input tables must contain only anchor and target.
    period_tables = {
        "build_tx_limits.csv": "period",
        "capacity_plans.csv": "period",
        "carbon_policies.csv": "PERIOD",
        "co2_injection_limits.csv": "PERIOD",
        "fuel_cost.csv": "period",
        "fuel_supply_curves.csv": "period",
        "gen_ccs_energy_load.csv": "period",
        "total_capacity_limits.csv": "period",
        "zone_coincident_peak_demand.csv": "PERIOD",
    }
    allowed = {ANCHOR, target} if target is not None else {ANCHOR}
    for filename, column in period_tables.items():
        df = pd.read_csv(inp / filename)
        vals = set(pd.to_numeric(df[column], errors="raise").astype(int).unique()) if len(df) else set()
        checks[f"{filename}_periods"] = sorted(vals)
        if not vals <= allowed:
            errors.append(f"{filename} contains periods outside {sorted(allowed)}: {sorted(vals)}")
        if target is not None and filename not in {"total_capacity_limits.csv"} and target not in vals:
            errors.append(f"{filename} is missing target year {target}")

    policy = pd.read_csv(inp / "legacy_storage_policy.csv")
    checks["legacy_policy_rows"] = len(policy)
    if len(policy) != 32 or policy["model_zone"].nunique() != 32:
        errors.append("legacy_storage_policy.csv must contain exactly 32 unique model zones")
    mode = str(policy["legacy_allocation_mode"].iloc[0])
    target_p = float(policy["national_power_target_mw"].iloc[0])
    target_e = float(policy["national_energy_target_mwh"].iloc[0])
    duration = float(policy["standardized_duration_h"].iloc[0])
    checks.update({
        "legacy_mode": mode,
        "legacy_power_target_mw": target_p,
        "legacy_energy_target_mwh": target_e,
        "legacy_standardized_duration_h": duration,
    })
    if abs(target_p - expected_storage_power_mw()) > 0.1:
        errors.append(f"Legacy power target {target_p} does not match the publication power contract")
    if abs(target_e - expected_storage_energy_mwh()) > 0.1:
        errors.append(f"Legacy energy target {target_e} does not match the publication energy contract")
    if abs(duration - target_e / target_p) > 1e-10:
        errors.append("Standardized legacy duration does not equal national energy/power")

    if meta:
        if str(meta.get("storage_chronology_mode")) != "monthly_linked":
            errors.append("storage_chronology_mode must be monthly_linked")
        proxy = str(meta.get("ldes_proxy_mode"))
        allow_cas = _bool(meta.get("allow_cas", False))
        if proxy == "technology_portfolio_discrete":
            if allow_cas:
                errors.append("Original generic CAS must remain disabled in technology-portfolio mode")
            if float(meta.get("ldes_proxy_min_duration_h")) != 10.0:
                errors.append("LDES portfolio minimum duration must be 10 h")
            if float(meta.get("ldes_proxy_max_duration_h")) != 100.0:
                errors.append("LDES portfolio maximum duration must be 100 h")
        elif proxy != "disabled":
            errors.append(f"Unknown LDES proxy mode {proxy}")

    gen = pd.read_csv(inp / "gen_info.csv")
    ldes = gen.loc[gen["gen_tech"].astype(str).str.startswith("LDES_")]
    expected_ldes_techs = {
        "LDES_CAES_10h", "LDES_CAES_24h", "LDES_CAES_100h",
        "LDES_VRFB_10h", "LDES_VRFB_24h", "LDES_H2_100h",
        "LDES_PSH_10h", "LDES_PSH_24h",
    }
    if meta and str(meta.get("ldes_proxy_mode")) == "technology_portfolio_discrete":
        got = set(ldes["gen_tech"].astype(str))
        checks["ldes_portfolio_techs"] = sorted(got)
        if got != expected_ldes_techs:
            errors.append(f"LDES technology portfolio mismatch: {sorted(got)}")
    elif not ldes.empty:
        errors.append("Non-LDES case contains LDES_ technology projects")

    nlr_audit = case_dir / "audits" / "nlr_2025_battery_cost_application.json"
    checks["nlr_2025_battery_cost_audit_present"] = nlr_audit.is_file()
    if not nlr_audit.is_file():
        errors.append("Missing NLR 2025 battery cost application audit")
    if expected_resolution_h == 1:
        hourly_audit = case_dir / "audits" / "one_hour_reconstruction_audit.json"
        checks["one_hour_reconstruction_audit_present"] = hourly_audit.is_file()
        if not hourly_audit.is_file():
            errors.append("Missing one-hour reconstruction audit")

    result = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checks": checks,
        "scope": {
            "design": "single_target_year_capacity_and_dispatch_reoptimization",
            "full_transition_path_claim_supported": False,
            "full_8760_hour_claim_supported": False,
            "endogenous_pre_target_builds_carried_in": False,
            "representative_time_resolution_h": expected_resolution_h,
        },
    }
    # Normalize numpy/pandas scalar values before returning so both this CLI and
    # the package-level checker can serialize the complete evidence report.
    result = json.loads(json.dumps(
        result,
        ensure_ascii=False,
        default=lambda value: value.item() if hasattr(value, "item") else str(value),
    ))
    if raise_on_error and errors:
        raise ValueError(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    ap.add_argument("--meta")
    args = ap.parse_args()
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8")) if args.meta else None
    result = validate_case(args.case_dir, meta, raise_on_error=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
