#!/usr/bin/env python3
"""Prepare eight single-target-year linked-SOC sensitivity cases.

Each case contains exactly:
- a 2023-labelled stock-only anchor for surviving historical assets and the 2025
  inherited-storage counterfactual; and
- one operating/investment period (2028 or 2033) with 12 month-specific
  representative days; the six original cases retain 72 four-hour timepoints,
  and the added 2033 pair uses 288 energy-preserving one-hour timepoints.

No endogenous build vintage before the selected target year is retained. This is
therefore a transparent static target-year capacity-and-dispatch re-optimization,
not a replacement for the frozen multi-period transition pathway.
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
OUTROOT = ROOT / "sensitivity_cases"
SCEN = ROOT / "storage_runner" / "scenarios_targetyear_linked.csv"
ANCHOR = 2023
ALLOWED_TARGETS = {2028, 2033}


def ensure_base(*, reuse_fresh_base: bool = False) -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    if BASE.exists() and reuse_fresh_base:
        from publication_source_common import validate_base_fingerprint
        ok, reasons = validate_base_fingerprint(ROOT, BASE)
        if ok:
            return
        print("Existing sensitivity base rejected by current source gate: " + "; ".join(reasons))
        shutil.rmtree(BASE)
    elif BASE.exists():
        shutil.rmtree(BASE)
    import build_storage_base_case
    build_storage_base_case.main()


def _bool(v: Any) -> bool:
    return str(v).strip().lower() in {"true", "1", "yes", "y", "t"}


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


def prune_to_target_year(case_dir: Path, target_year: int) -> dict[str, Any]:
    if target_year not in ALLOWED_TARGETS:
        raise ValueError(f"target_year must be one of {sorted(ALLOWED_TARGETS)}")
    inp = case_dir / "inputs"
    periods_keep = {ANCHOR, target_year}
    audit: dict[str, Any] = {"target_year": target_year, "anchor_period": ANCHOR, "files": {}}

    # Investment periods: retain stock anchor plus one target-year operating block.
    ppath = inp / "periods.csv"
    periods = _read(ppath)
    pcol = "INVESTMENT_PERIOD"
    pvals = pd.to_numeric(periods[pcol], errors="raise").astype(int)
    periods = periods.loc[pvals.isin(periods_keep)].copy()
    periods.loc[pd.to_numeric(periods[pcol]).eq(target_year), "period_prev"] = ANCHOR
    periods = periods.sort_values(pcol)
    if periods[pcol].astype(int).tolist() != [ANCHOR, target_year]:
        raise ValueError(f"Could not construct periods [2023, {target_year}]")
    _write(periods, ppath)
    audit["files"]["periods.csv"] = {"after": len(periods), "periods": [ANCHOR, target_year]}

    # Retain only the selected operating period's 12 representative months.
    tspath = inp / "timeseries.csv"
    ts = _read(tspath)
    ts_before = len(ts)
    ts_period = pd.to_numeric(ts["ts_period"], errors="raise").astype(int)
    ts = ts.loc[ts_period.eq(target_year)].copy()
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
            df = _read(path)
            before = len(df)
            df = df.loc[df["TIMEPOINT"].astype(str).isin(kept_tp)].copy()
            _write(df, path)
            audit["files"][filename] = {"before": before, "after": len(df)}

    vpath = inp / "variable_capacity_factors.csv"
    vcf = _read(vpath)
    before = len(vcf)
    vcf = vcf.loc[vcf["timepoint"].astype(str).isin(kept_tp)].copy()
    _write(vcf, vpath)
    audit["files"]["variable_capacity_factors.csv"] = {"before": before, "after": len(vcf)}

    hpath = inp / "hydro_timeseries.csv"
    hydro = _read(hpath)
    before = len(hydro)
    hydro = hydro.loc[hydro["timeseries"].astype(str).isin(kept_ts)].copy()
    _write(hydro, hpath)
    audit["files"]["hydro_timeseries.csv"] = {"before": before, "after": len(hydro)}

    # Period-indexed tables needed by the model for the anchor and target period.
    period_tables = {
        "build_tx_limits.csv": "period",
        "capacity_plans.csv": "period",
        "carbon_policies.csv": "PERIOD",
        "co2_injection_limits.csv": "PERIOD",
        "fuel cost.csv": "period",
        "fuel_cost.csv": "period",
        "fuel supply curves.csv": "period",
        "fuel_supply_curves.csv": "period",
        "gen_ccs_energy_load.csv": "period",
        "total_capacity_limits.csv": "period",
        "total_capacity_tech_limits.csv": "period",
        "zone_coincident_peak_demand.csv": "PERIOD",
    }
    for filename, column in period_tables.items():
        audit["files"][filename] = _filter_period_rows(inp, filename, column, periods_keep)

    # Historical predetermined vintages remain available if they survive to the
    # target year. New-build choices exist only in the target-year vintage.
    gpath = inp / "gen_build_costs.csv"
    gcost = _read(gpath)
    gbefore = len(gcost)
    years = pd.to_numeric(gcost["build_year"], errors="raise").astype(int)
    gcost = gcost.loc[years.le(ANCHOR) | years.eq(target_year)].copy()
    _write(gcost, gpath)
    retained_build_years = set(pd.to_numeric(gcost["build_year"], errors="raise").astype(int))
    audit["files"]["gen_build_costs.csv"] = {
        "before": gbefore, "after": len(gcost),
        "retained_build_years": sorted(retained_build_years),
        "new_build_vintages": [target_year],
    }

    cpath = inp / "ccs_install_costs.csv"
    ccs = _read(cpath)
    cbefore = len(ccs)
    build_year = pd.to_numeric(ccs["build_year"], errors="raise").astype(int)
    install_year = pd.to_numeric(ccs["install_year"], errors="raise").astype(int)
    ccs = ccs.loc[build_year.isin(retained_build_years) & install_year.isin(periods_keep)].copy()
    _write(ccs, cpath)
    audit["files"]["ccs_install_costs.csv"] = {"before": cbefore, "after": len(ccs)}

    # Strong structural checks before model construction.
    if len(ts) != 12:
        raise ValueError(f"Target {target_year}: expected 12 representative months, got {len(ts)}")
    if len(tp) != 72:
        raise ValueError(f"Target {target_year}: expected 72 timepoints, got {len(tp)}")
    counts = tp.groupby("timeseries").size()
    if not (counts == 6).all():
        raise ValueError("Every representative month-day must contain six four-hour timepoints")
    if not set(pd.to_numeric(gcost["build_year"]).astype(int).unique()) <= (set(range(0, ANCHOR + 1)) | {target_year}):
        raise ValueError("Unexpected non-target future build vintage retained")

    audit.update({
        "design": "single_target_year_capacity_and_dispatch_reoptimization",
        "transition_path_claim_supported": False,
        "full_8760_hour_claim_supported": False,
        "endogenous_pre_target_builds_carried_in": False,
        "historical_predetermined_assets_survive_by_model_lifetime_rule": True,
        "target_year_new_investment_allowed": True,
        "monthly_representative_days": 12,
        "four_hour_timepoints": 72,
        "scope_note": (
            "The target-year LP begins from surviving exogenous historical stock plus the 2025 inherited-storage "
            "counterfactual. It does not carry endogenous builds from earlier planning periods and therefore tests "
            "the robustness of the spatial mechanism, not the exact multi-period transition path."
        ),
    })
    return audit


def prepare_one(row: pd.Series) -> dict[str, Any]:
    scenario = str(row["scenario"])
    target_year = int(row["target_year"])
    dst = OUTROOT / scenario
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(BASE, dst)

    sys.path.insert(0, str(ROOT / "tools"))
    from apply_spatial_legacy import build_policy
    from publication_source_contract import DATA_VERSION, load_fingerprint, source_fingerprint_sha256
    legacy_audit = build_policy(dst, str(row["legacy_allocation_mode"]), cap_quantile=0.95)
    source_contract=load_fingerprint()
    source_contract_sha=source_fingerprint_sha256()
    prune_audit = prune_to_target_year(dst, target_year)

    # All target-year cases use the source-direct NLR 2025 mid trajectory for
    # a complete fixed four-hour lithium-ion system. The 2033 LDES pair then
    # receives a separate discrete technology-duration portfolio. The added 1 h
    # pair reconstructs bounded hourly values only after target-year pruning.
    from apply_nlr_2025_battery_costs import apply as apply_nlr_battery_costs
    battery_cost_audit = apply_nlr_battery_costs(dst, "NLR_2025_mid")
    ldes_portfolio_audit = None
    if str(row["ldes_proxy_mode"]) == "technology_portfolio_discrete":
        from apply_ldes_technology_portfolio import apply as apply_ldes_portfolio
        ldes_portfolio_audit = apply_ldes_portfolio(dst)
    one_hour_audit = None
    if int(row.get("time_resolution_h", 4)) == 1:
        from reconstruct_one_hour_repdays import reconstruct
        one_hour_audit = reconstruct(dst)

    meta = {k: (None if pd.isna(v) else v) for k, v in row.items()}
    meta.update({
        "base_case_copied_from": str(BASE.relative_to(ROOT)).replace("\\", "/"),
        "publication_source_data_version": DATA_VERSION,
        "publication_source_fingerprint_sha256": source_contract_sha,
        "publication_source_contract": source_contract,
        "scientific_design": "target_year_exact_linked_capacity_and_dispatch_reoptimization",
        "pair_identification_lock": (
            "Within each reference-versus-optimized pair, every non-geographic input is byte-identical. "
            "The controlled pair changes only the 2023-labelled inherited Battery allocation while holding national "
            "power, energy, standardized duration, technology, sunk-capital treatment and target-year assumptions fixed."
        ),
        "target_year_scope_lock": prune_audit["scope_note"],
        "battery_cost_application": battery_cost_audit,
        "ldes_interpretation": (
            "Discrete technology-specific PNNL portfolio: 10/24/100 h CAES, 10/24 h VRFB, 100 h hydrogen, "
            "and 10/24 h pumped-storage alternatives. Pumped-storage variants share the existing provincial "
            "resource ceiling; other candidates remain resource-unconstrained pressure tests."
            if ldes_portfolio_audit is not None else "LDES technology portfolio disabled."
        ),
        "ldes_portfolio_application": ldes_portfolio_audit,
        "one_hour_reconstruction": one_hour_audit,
        "legacy_policy_audit": legacy_audit,
        "target_year_pruning_audit": prune_audit,
    })
    (dst / "SENSITIVITY_SCENARIO_META.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8"
    )

    from validate_targetyear_case import validate_case
    validation = validate_case(dst, row.to_dict(), raise_on_error=True)
    meta["prepared_input_validation"] = validation
    (dst / "SENSITIVITY_SCENARIO_META.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8"
    )
    from publication_source_common import write_case_fingerprint
    cfp = write_case_fingerprint(ROOT, dst, scenario, "sensitivity", "SENSITIVITY_SCENARIO_META.json")
    return {
        "scenario": scenario,
        "pair_id": str(row["pair_id"]),
        "target_year": target_year,
        "case_dir": str(dst.relative_to(ROOT)).replace("\\", "/"),
        "validation_status": validation["status"],
        "meta_sha256": _sha256(dst / "SENSITIVITY_SCENARIO_META.json"),
        "source_fingerprint_sha256": cfp["source_fingerprint_sha256"],
        "input_manifest_sha256": cfp["input_manifest_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", help="Prepare one scenario; default prepares all eight")
    parser.add_argument("--reuse-fresh-base", action="store_true", help="Reuse only a base already built and source-gated in the current clean workflow")
    args = parser.parse_args()
    ensure_base(reuse_fresh_base=args.reuse_fresh_base)
    OUTROOT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(SCEN)
    if args.scenario:
        df = df.loc[df["scenario"].astype(str).eq(args.scenario)].copy()
        if len(df) != 1:
            raise SystemExit(f"Unknown scenario: {args.scenario}")
    rows = [prepare_one(r) for _, r in df.iterrows()]
    index_path = ROOT / "storage_runner" / "prepared_targetyear_cases_index.csv"
    pd.DataFrame(rows).to_csv(index_path, index=False)

    # Pair-level identity audit runs after all members needed for a pair exist.
    if not args.scenario:
        from audit_targetyear_pair_identity import audit_all_pairs
        pair_audit = audit_all_pairs(raise_on_error=True)
        print(json.dumps(pair_audit, ensure_ascii=False, indent=2))
    print(f"Prepared {len(rows)} V17T2R5 target-year cases under {OUTROOT}")


if __name__ == "__main__":
    main()
