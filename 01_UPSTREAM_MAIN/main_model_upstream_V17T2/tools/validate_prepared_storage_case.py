#!/usr/bin/env python3
"""Publication pre-solve validation for one prepared Storage V17 case."""
from __future__ import annotations
from pathlib import Path
import argparse, json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _bool_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "yes", "y"])


def _predetermined_floor(inp: Path, tech: str) -> pd.Series:
    gen = pd.read_csv(inp / "gen_info.csv")
    pred = pd.read_csv(inp / "gen_build_predetermined.csv")
    periods = pd.to_numeric(pd.read_csv(inp / "periods.csv")["INVESTMENT_PERIOD"], errors="raise").astype(int)
    x = pred.merge(gen[["GENERATION_PROJECT", "gen_tech", "gen_max_age"]], on="GENERATION_PROJECT", how="left")
    x = x[x.gen_tech.eq(tech)].copy()
    x["build_year"] = pd.to_numeric(x.build_year, errors="raise")
    x["gen_max_age"] = pd.to_numeric(x.gen_max_age, errors="raise")
    x["build_gen_predetermined"] = pd.to_numeric(x.build_gen_predetermined, errors="raise")
    out = {}
    for g, q in x.groupby("GENERATION_PROJECT"):
        out[g] = max((q.loc[(q.build_year <= p) & (p < q.build_year + q.gen_max_age), "build_gen_predetermined"].sum() for p in periods), default=0.0)
    return pd.Series(out, dtype=float)


def validate_case(case_dir: Path | str, scenario_row: dict | None = None, raise_on_error: bool = False) -> dict:
    case_dir = Path(case_dir)
    inp = case_dir / "inputs"
    if scenario_row is None:
        meta_path = case_dir / "STORAGE_SCENARIO_META.json"
        scenario_row = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"scenario": case_dir.name}
    sc = str(scenario_row.get("scenario", case_dir.name))
    checks = []
    def add(name, passed, detail=""):
        checks.append({"check": name, "pass": bool(passed), "detail": str(detail)})

    required = ["gen_info.csv", "gen_build_predetermined.csv", "gen_build_costs.csv", "periods.csv", "timeseries.csv", "timepoints.csv", "transmission_lines.csv", "build_tx_limits.csv"]
    missing = [x for x in required if not (inp / x).exists()]
    add("required_input_files", not missing, missing)
    if missing:
        payload = {"scenario": sc, "pass": False, "checks": checks}
        if raise_on_error: raise ValueError(payload)
        return payload

    legacy_mode = str(scenario_row.get("legacy_allocation_mode", "")).strip().lower()
    if legacy_mode and legacy_mode not in {"nan", "none_defined"}:
        policy_file = inp / "legacy_storage_policy.csv"
        add("legacy_policy_file_present", policy_file.exists(), policy_file)
        if policy_file.exists():
            policy = pd.read_csv(policy_file)
            required_policy = {"model_zone", "battery_project", "legacy_allocation_mode",
                               "national_power_target_mw", "national_energy_target_mwh",
                               "standardized_duration_h", "legacy_power_cap_mw",
                               "fixed_power_mw", "fixed_energy_mwh"}
            add("legacy_policy_required_columns", required_policy.issubset(policy.columns),
                sorted(required_policy.difference(policy.columns)))
            add("legacy_policy_32_unique_zones", len(policy) == 32 and policy.model_zone.nunique() == 32,
                {"rows": len(policy), "zones": policy.model_zone.nunique()})
            add("legacy_policy_single_mode", policy.legacy_allocation_mode.astype(str).nunique() == 1 and
                policy.legacy_allocation_mode.astype(str).iloc[0] == legacy_mode,
                policy.legacy_allocation_mode.astype(str).unique().tolist())
            ptarget = float(pd.to_numeric(policy.national_power_target_mw, errors="raise").iloc[0])
            etarget = float(pd.to_numeric(policy.national_energy_target_mwh, errors="raise").iloc[0])
            caps = pd.to_numeric(policy.legacy_power_cap_mw, errors="raise")
            add("legacy_zone_caps_nonnegative", (caps >= -1e-9).all(), float(caps.min()))
            add("legacy_optimized_target_feasible_under_caps", legacy_mode != "optimized_reallocation" or float(caps.sum()) + 1e-6 >= ptarget,
                {"cap_sum_mw": float(caps.sum()), "target_mw": ptarget})
            pred = pd.read_csv(inp / "gen_build_predetermined.csv")
            gen_tmp = pd.read_csv(inp / "gen_info.csv")
            battery_projects = set(gen_tmp.loc[gen_tmp.gen_tech.eq("Battery"), "GENERATION_PROJECT"].astype(str))
            bp = pred[pred.GENERATION_PROJECT.astype(str).isin(battery_projects) &
                      pd.to_numeric(pred.build_year, errors="raise").eq(2023)].copy()
            pred_p = float(pd.to_numeric(bp.build_gen_predetermined, errors="raise").sum()) if len(bp) else 0.0
            pred_e = float(pd.to_numeric(bp.build_gen_energy_predetermined, errors="raise").sum()) if len(bp) else 0.0
            fixed_modes = {"observed_actual", "observed_standardized", "rule_load", "rule_vre"}
            if legacy_mode in fixed_modes:
                add("legacy_fixed_predetermined_32_rows", len(bp) == 32, len(bp))
                add("legacy_fixed_power_national_closure", abs(pred_p - ptarget) <= 1e-5, {"pred": pred_p, "target": ptarget})
                add("legacy_fixed_energy_national_closure", abs(pred_e - etarget) <= 1e-4, {"pred": pred_e, "target": etarget})
            elif legacy_mode in {"optimized_reallocation", "none"}:
                add("legacy_endogenous_or_none_has_no_predetermined_2023_battery", len(bp) == 0, len(bp))
            costs = pd.read_csv(inp / "gen_build_costs.csv")
            cm = costs.GENERATION_PROJECT.astype(str).isin(battery_projects) & pd.to_numeric(costs.build_year, errors="raise").eq(2023)
            power_cost = pd.to_numeric(costs.loc[cm, "gen_overnight_cost"], errors="coerce").fillna(0.0)
            energy_cost = pd.to_numeric(costs.loc[cm, "gen_storage_energy_overnight_cost"], errors="coerce").fillna(0.0)
            add("legacy_2023_power_and_energy_capex_are_sunk", len(power_cost) == 32 and power_cost.abs().max() <= 1e-12 and energy_cost.abs().max() <= 1e-12,
                {"rows": len(power_cost), "max_power_cost": float(power_cost.abs().max() if len(power_cost) else -1),
                 "max_energy_cost": float(energy_cost.abs().max() if len(energy_cost) else -1)})

    ts = pd.read_csv(inp / "timeseries.csv")
    tp = pd.read_csv(inp / "timepoints.csv")
    add("representative_timepoint_count_504", len(tp) == 504, len(tp))
    add("timeseries_count_84", len(ts) == 84, len(ts))
    add("six_timepoints_per_representative_day", pd.to_numeric(ts.ts_num_tps, errors="coerce").eq(6).all(), sorted(pd.to_numeric(ts.ts_num_tps, errors="coerce").dropna().unique()))
    add("four_hour_timepoints", pd.to_numeric(ts.ts_duration_of_tp, errors="coerce").eq(4).all(), sorted(pd.to_numeric(ts.ts_duration_of_tp, errors="coerce").dropna().unique()))
    ts_period = pd.to_numeric(ts.ts_period, errors="raise").astype(int)
    add("operations_start_in_2028", int(ts_period.min()) == 2028, sorted(ts_period.unique().tolist()))
    add("no_2023_operational_timeseries", not ts_period.eq(2023).any(), sorted(ts_period.unique().tolist()))
    annual_hours = ts.assign(h=pd.to_numeric(ts.ts_duration_of_tp)*pd.to_numeric(ts.ts_num_tps)*pd.to_numeric(ts.ts_scale_to_period)).groupby("ts_period").h.sum()
    # The timeseries scale is for a five-year planning period; normalization in the model divides by period length.
    add("representative_weights_positive", (annual_hours > 0).all(), annual_hours.to_dict())
    add("seven_operational_planning_periods", len(annual_hours) == 7, annual_hours.index.tolist())

    carbon = pd.read_csv(inp / "carbon_policies.csv")
    carbon["PERIOD"] = pd.to_numeric(carbon["PERIOD"], errors="raise").astype(int)
    carbon["carbon_cap_tco2_per_yr"] = pd.to_numeric(carbon["carbon_cap_tco2_per_yr"], errors="raise")
    final_cap = float(carbon.loc[carbon.PERIOD.eq(carbon.PERIOD.max()), "carbon_cap_tco2_per_yr"].iloc[0])
    multiplier = float(scenario_row.get("carbon_cap_multiplier", 1.0))
    expected_final = 2.0e8 * multiplier
    add("deep_decarbonization_final_cap_matches_scenario", abs(final_cap - 2.0e8) <= 1e-6,
        {"input_final_cap": final_cap, "solver_multiplier": multiplier, "effective_expected_final_cap": expected_final})
    add("official_storage_scenario_has_no_cdr",
        str(scenario_row.get("allow_beccs", False)).strip().lower() not in {"true","1","yes"},
        {"allow_beccs": scenario_row.get("allow_beccs"), "NBCCS": False, "DACCS": False})

    gen = pd.read_csv(inp / "gen_info.csv")
    ph = gen[gen.gen_tech.eq("Hydro_Pumped")].copy()
    floor = _predetermined_floor(inp, "Hydro_Pumped")
    ph["floor"] = ph.GENERATION_PROJECT.map(floor).fillna(0.0)
    ph["cap"] = pd.to_numeric(ph.gen_capacity_limit_mw.replace(".", np.nan), errors="coerce")
    bad = ph[ph.cap + 1e-6 < ph.floor]
    add("pumped_hydro_ceiling_above_predetermined_floor", bad.empty, bad[["GENERATION_PROJECT", "cap", "floor"]].head(20).to_dict("records"))

    tx_case = str(scenario_row.get("transmission_case", "TX_policy"))
    if tx_case == "TX_fixed":
        lines = pd.read_csv(inp / "transmission_lines.csv")
        limits = pd.read_csv(inp / "build_tx_limits.csv")
        add("tx_fixed_all_new_build_disabled", (~_bool_series(lines.trans_new_build_allowed)).all(), int(_bool_series(lines.trans_new_build_allowed).sum()))
        add("tx_fixed_line_caps_zero", pd.to_numeric(lines.trans_new_build_cap, errors="coerce").fillna(0).abs().max() <= 1e-9, pd.to_numeric(lines.trans_new_build_cap, errors="coerce").max())
        add("tx_fixed_period_limits_zero", pd.to_numeric(limits.build_trans_limit_mw, errors="coerce").fillna(0).abs().max() <= 1e-9, pd.to_numeric(limits.build_trans_limit_mw, errors="coerce").max())

    duration = str(scenario_row.get("storage_duration_case", "flexible_energy"))
    if duration in {"2h", "4h", "8h", "24h", "72h", "100h"}:
        d = float(duration[:-1])
        batt = pd.to_numeric(gen.loc[gen.gen_tech.eq("Battery"), "gen_storage_energy_to_power_ratio"], errors="coerce")
        exp_b = min(d, 8.0)
        add("battery_new_build_duration_ratio", batt.notna().all() and np.allclose(batt, exp_b), {"expected": exp_b, "values": sorted(batt.dropna().unique())})
        if d > 8:
            cas = pd.to_numeric(gen.loc[gen.gen_tech.eq("CAS"), "gen_storage_energy_to_power_ratio"], errors="coerce")
            add("cas_new_build_duration_ratio", cas.notna().all() and np.allclose(cas, d), {"expected": d, "values": sorted(cas.dropna().unique())})
            add("long_duration_claim_is_diagnostic", str(scenario_row.get("v3_scenario_set", "")).startswith("diagnostic_temporal"), scenario_row.get("v3_scenario_set", ""))

    # Input numeric sanity.
    raw_cap = gen.gen_capacity_limit_mw.astype("string").str.strip()
    add("generation_capacity_limit_uses_explicit_unset_sentinel",
        raw_cap.notna().all() and (~raw_cap.eq("")).all(),
        {"missing_or_blank": int((raw_cap.isna() | raw_cap.eq("")).sum())})
    cap = pd.to_numeric(gen.gen_capacity_limit_mw.replace(".", np.nan), errors="coerce")
    add("nonnegative_generation_capacity_limits", (cap.dropna() >= -1e-9).all(), float(cap.min(skipna=True)))
    vcf = pd.read_csv(inp / "variable_capacity_factors.csv")
    cf = pd.to_numeric(vcf.gen_max_capacity_factor, errors="coerce")
    add("capacity_factors_in_unit_interval", cf.notna().all() and (cf >= -1e-10).all() and (cf <= 1 + 1e-10).all(), {"min": float(cf.min()), "max": float(cf.max())})

    passed = all(x["pass"] for x in checks)
    payload = {"scenario": sc, "case_dir": str(case_dir), "pass": passed, "checks": checks}
    ad = case_dir / "audits"; ad.mkdir(exist_ok=True)
    (ad / "V17_PRE_SOLVE_VALIDATION.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(checks).to_csv(ad / "V17_PRE_SOLVE_VALIDATION.csv", index=False)
    if raise_on_error and not passed:
        raise ValueError(f"Prepared case validation failed for {sc}: {[x for x in checks if not x['pass']]}")
    return payload


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("case_dir")
    args = ap.parse_args()
    result = validate_case(args.case_dir, raise_on_error=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["pass"] else 1)

if __name__ == "__main__":
    main()
