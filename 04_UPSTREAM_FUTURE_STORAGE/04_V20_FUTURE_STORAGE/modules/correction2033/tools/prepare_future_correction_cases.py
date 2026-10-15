#!/usr/bin/env python3
"""Prepare eight V19 Layer-A 2033 future-correction cases.

V19 Layer A is deliberately a *single-target-year* correction experiment layered on
an unchanged V17T2R5 scientific core.  It freezes the inherited 2025 storage
stock as the observed/optimized counterfactual, then allows the 2033 system to
choose incremental capacity, province/model-zone siting, technology and fixed
technology-specific duration from the declared opportunity set.

It does NOT claim a 2025-2050 investment timing pathway: no endogenous 2028
build is carried into 2033.  That scope lock is intentional and publication
facing.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "base_model_v39" / "storage_base_noNBCCS_noDACCS_onshorePV"
OUTROOT = ROOT / "future_correction_cases"
SCEN = ROOT / "storage_runner" / "scenarios_future_correction.csv"
ANCHOR = 2023
TARGET = 2033


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _write(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False)


def ensure_base(*, reuse_fresh_base: bool = False) -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    if BASE.exists() and reuse_fresh_base:
        from publication_source_common import validate_base_fingerprint
        ok, reasons = validate_base_fingerprint(ROOT, BASE)
        if ok:
            return
        print("Existing V18 base rejected by current source gate: " + "; ".join(reasons))
        shutil.rmtree(BASE)
    elif BASE.exists():
        shutil.rmtree(BASE)
    import build_storage_base_case
    build_storage_base_case.main()


def _filter_period_rows(inp: Path, filename: str, column: str, periods: set[int]) -> dict[str, int]:
    path = inp / filename
    if not path.exists():
        return {"before": 0, "after": 0}
    df = _read(path)
    before = len(df)
    if column not in df.columns:
        raise ValueError(f"{filename} missing period column {column}")
    values = pd.to_numeric(df[column], errors="raise").astype(int)
    df = df.loc[values.isin(periods)].copy()
    _write(df, path)
    return {"before": before, "after": len(df)}


def prune_to_2033(case_dir: Path) -> dict[str, Any]:
    inp = case_dir / "inputs"
    periods_keep = {ANCHOR, TARGET}
    audit: dict[str, Any] = {"target_year": TARGET, "anchor_period": ANCHOR, "files": {}}

    ppath = inp / "periods.csv"
    periods = _read(ppath)
    pcol = "INVESTMENT_PERIOD"
    pvals = pd.to_numeric(periods[pcol], errors="raise").astype(int)
    periods = periods.loc[pvals.isin(periods_keep)].copy()
    periods.loc[pd.to_numeric(periods[pcol]).eq(TARGET), "period_prev"] = ANCHOR
    periods = periods.sort_values(pcol)
    if periods[pcol].astype(int).tolist() != [ANCHOR, TARGET]:
        raise ValueError("Could not construct V19 Layer-A periods [2023, 2033]")
    _write(periods, ppath)
    audit["files"]["periods.csv"] = {"after": len(periods), "periods": [ANCHOR, TARGET]}

    tspath = inp / "timeseries.csv"
    ts = _read(tspath)
    ts_before = len(ts)
    ts = ts.loc[pd.to_numeric(ts["ts_period"], errors="raise").astype(int).eq(TARGET)].copy()
    kept_ts = set(ts["TIMESERIES"].astype(str))
    _write(ts, tspath)
    audit["files"]["timeseries.csv"] = {"before": ts_before, "after": len(ts)}

    tppath = inp / "timepoints.csv"
    tp = _read(tppath)
    tp_before = len(tp)
    tp = tp.loc[tp["timeseries"].astype(str).isin(kept_ts)].copy()
    kept_tp = set(tp["timepoint_id"].astype(str))
    _write(tp, tppath)
    audit["files"]["timepoints.csv"] = {"before": tp_before, "after": len(tp)}

    for filename in ["loads.csv", "loads_new.csv"]:
        path = inp / filename
        if path.exists():
            df = _read(path); before = len(df)
            df = df.loc[df["TIMEPOINT"].astype(str).isin(kept_tp)].copy()
            _write(df, path); audit["files"][filename] = {"before": before, "after": len(df)}

    vpath = inp / "variable_capacity_factors.csv"
    vcf = _read(vpath); before = len(vcf)
    vcf = vcf.loc[vcf["timepoint"].astype(str).isin(kept_tp)].copy()
    _write(vcf, vpath); audit["files"]["variable_capacity_factors.csv"] = {"before": before, "after": len(vcf)}

    hpath = inp / "hydro_timeseries.csv"
    hydro = _read(hpath); before = len(hydro)
    hydro = hydro.loc[hydro["timeseries"].astype(str).isin(kept_ts)].copy()
    _write(hydro, hpath); audit["files"]["hydro_timeseries.csv"] = {"before": before, "after": len(hydro)}

    period_tables = {
        "build_tx_limits.csv": "period", "capacity_plans.csv": "period",
        "carbon_policies.csv": "PERIOD", "co2_injection_limits.csv": "PERIOD",
        "fuel cost.csv": "period", "fuel_cost.csv": "period",
        "fuel supply curves.csv": "period", "fuel_supply_curves.csv": "period",
        "gen_ccs_energy_load.csv": "period", "total_capacity_limits.csv": "period",
        "total_capacity_tech_limits.csv": "period", "zone_coincident_peak_demand.csv": "PERIOD",
    }
    for filename, column in period_tables.items():
        audit["files"][filename] = _filter_period_rows(inp, filename, column, periods_keep)

    gpath = inp / "gen_build_costs.csv"
    gcost = _read(gpath); gbefore = len(gcost)
    years = pd.to_numeric(gcost["build_year"], errors="raise").astype(int)
    gcost = gcost.loc[years.le(ANCHOR) | years.eq(TARGET)].copy()
    _write(gcost, gpath)
    retained = set(pd.to_numeric(gcost["build_year"], errors="raise").astype(int))
    audit["files"]["gen_build_costs.csv"] = {
        "before": gbefore, "after": len(gcost), "retained_build_years": sorted(retained),
        "new_build_vintages": [TARGET],
    }

    cpath = inp / "ccs_install_costs.csv"
    ccs = _read(cpath); cbefore = len(ccs)
    by = pd.to_numeric(ccs["build_year"], errors="raise").astype(int)
    iy = pd.to_numeric(ccs["install_year"], errors="raise").astype(int)
    ccs = ccs.loc[by.isin(retained) & iy.isin(periods_keep)].copy()
    _write(ccs, cpath); audit["files"]["ccs_install_costs.csv"] = {"before": cbefore, "after": len(ccs)}

    if len(ts) != 12: raise ValueError(f"Expected 12 representative months, got {len(ts)}")
    if len(tp) != 72: raise ValueError(f"Expected 72 four-hour timepoints, got {len(tp)}")
    if not (tp.groupby("timeseries").size() == 6).all():
        raise ValueError("Every representative month-day must contain six four-hour timepoints")

    audit.update({
        "design": "single_target_year_2033_adaptive_future_correction_reoptimization",
        "full_transition_path_claim_supported": False,
        "full_8760_hour_claim_supported": False,
        "endogenous_pre_target_builds_carried_in": False,
        "historical_predetermined_assets_survive_by_model_lifetime_rule": True,
        "target_year_new_investment_allowed": True,
        "capacity_choice_endogenous": True,
        "province_or_model_zone_choice_endogenous": True,
        "technology_choice_endogenous_when_portfolio_enabled": True,
        "duration_choice_discrete_via_technology_duration_candidates": True,
        "monthly_representative_days": 12,
        "four_hour_timepoints": 72,
        "scope_note": (
            "V19 Layer-A starts from surviving historical stock plus the controlled 2025 inherited-storage geography and "
            "re-optimizes the 2033 system. It identifies where/how much/which declared storage option should be added "
            "to repair residual spatial lock-in. It does not identify investment timing between 2025 and 2033."
        ),
    })
    return audit


def prepare_one(row: pd.Series) -> dict[str, Any]:
    scenario = str(row["scenario"])
    if int(row["target_year"]) != TARGET or int(row["time_resolution_h"]) != 4:
        raise ValueError("V19 Layer A is locked to target_year=2033 and time_resolution_h=4")
    dst = OUTROOT / scenario
    if dst.exists(): shutil.rmtree(dst)
    shutil.copytree(BASE, dst)

    sys.path.insert(0, str(ROOT / "tools"))
    from apply_spatial_legacy import build_policy
    from publication_source_contract import DATA_VERSION, load_fingerprint, source_fingerprint_sha256
    from apply_nlr_2025_battery_costs import apply as apply_nlr_battery_costs
    from apply_future_correction_portfolio import apply as apply_portfolio
    from apply_future_correction_transmission import apply as apply_tx

    legacy_audit = build_policy(dst, str(row["legacy_allocation_mode"]), cap_quantile=0.95)
    source_contract = load_fingerprint(); source_contract_sha = source_fingerprint_sha256()
    pruning = prune_to_2033(dst)
    battery_audit = apply_nlr_battery_costs(dst, "NLR_2025_mid")

    scope = str(row["portfolio_scope"])
    portfolio_audit = None
    if scope != "baseline":
        portfolio_audit = apply_portfolio(dst, scope)
    tx_audit = apply_tx(dst, str(row["transmission_case"]))

    meta = {k: (None if pd.isna(v) else v) for k, v in row.items()}
    meta.update({
        "base_case_copied_from": str(BASE.relative_to(ROOT)).replace("\\", "/"),
        "publication_source_data_version": DATA_VERSION,
        "publication_source_fingerprint_sha256": source_contract_sha,
        "publication_source_contract": source_contract,
        "scientific_design": "V19_LAYER_A_2033_MATCHED_CORRECTION_ON_FROZEN_V17T2R5_CORE",
        "frozen_core_model": "base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl",
        "legacy_irreversibility_lock": (
            "The inherited 2025 storage stock is not relocated by the correction layer. The observed member fixes its "
            "standardized geography; the optimized member retains the original V17 counterfactual reallocation definition."
        ),
        "pair_identification_lock": (
            "Within each V19 observed-versus-optimized pair, every non-geographic scientific input is byte-identical; "
            "only the inherited 2023-labelled Battery geography treatment differs."
        ),
        "correction_intervention_lock": (
            "Across BASE versus ADAPTIVE experiments, the deliberate intervention is the declared future storage opportunity set. "
            "All members use the same target year, chronology, carbon policy and source lineage."
        ),
        "target_year_scope_lock": pruning["scope_note"],
        "battery_cost_application": battery_audit,
        "future_correction_portfolio_application": portfolio_audit,
        "future_correction_transmission_application": tx_audit,
        "legacy_policy_audit": legacy_audit,
        "target_year_pruning_audit": pruning,
        "main_claim_eligible": str(row["experiment_role"]) in {"reference", "primary_correction"},
    })
    mpath = dst / "FUTURE_CORRECTION_SCENARIO_META.json"
    mpath.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n", encoding="utf-8")

    from validate_future_correction_case import validate_case
    validation = validate_case(dst, meta, raise_on_error=True)
    meta["prepared_input_validation"] = validation
    mpath.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n", encoding="utf-8")

    from publication_source_common import write_case_fingerprint
    cfp = write_case_fingerprint(ROOT, dst, scenario, "future_correction", mpath.name)
    return {
        "scenario": scenario, "pair_id": str(row["pair_id"]), "target_year": TARGET,
        "portfolio_scope": scope, "transmission_case": str(row["transmission_case"]),
        "case_dir": str(dst.relative_to(ROOT)).replace("\\", "/"),
        "validation_status": validation["status"], "meta_sha256": _sha256(mpath),
        "source_fingerprint_sha256": cfp["source_fingerprint_sha256"],
        "input_manifest_sha256": cfp["input_manifest_sha256"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", help="Prepare one V19 Layer-A scenario; default prepares all eight")
    ap.add_argument("--reuse-fresh-base", action="store_true")
    args = ap.parse_args()
    ensure_base(reuse_fresh_base=args.reuse_fresh_base)
    OUTROOT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(SCEN)
    if args.scenario:
        df = df.loc[df["scenario"].astype(str).eq(args.scenario)].copy()
        if len(df) != 1: raise SystemExit(f"Unknown V19 Layer-A scenario: {args.scenario}")
    rows = [prepare_one(r) for _, r in df.iterrows()]
    pd.DataFrame(rows).to_csv(ROOT / "storage_runner" / "prepared_future_correction_cases_index.csv", index=False)
    if not args.scenario:
        from audit_future_correction_pair_identity import audit_all_pairs
        print(json.dumps(audit_all_pairs(raise_on_error=True), ensure_ascii=False, indent=2))
    print(f"Prepared {len(rows)} V19 Layer-A future-correction cases under {OUTROOT}")


if __name__ == "__main__": main()
