#!/usr/bin/env python3
"""Build the Storage V17 publication-strict base case from a retained clean template.

The template contains only the storage-study input case. Legacy NBCCS scenario folders
are not needed in this release. Rebuilding is deterministic and idempotent.
"""
from __future__ import annotations
from pathlib import Path
import json
import shutil
import sys
import zipfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def portable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)

TEMPLATE = ROOT / "base_model_v39" / "storage_base_template_v17.zip"
OUT = ROOT / "base_model_v39" / "storage_base_noNBCCS_noDACCS_onshorePV"


def extract_template() -> None:
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Storage base template missing: {TEMPLATE}")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(TEMPLATE) as archive:
        archive.extractall(OUT)


def zero_offshore(case_dir: Path) -> dict[str, int]:
    inp = case_dir / "inputs"
    gen = pd.read_csv(inp / "gen_info.csv")
    offshore = set(gen.loc[gen["gen_tech"].eq("Wind_Offshore"), "GENERATION_PROJECT"])
    pred = pd.read_csv(inp / "gen_build_predetermined.csv")
    affected = int(pred["GENERATION_PROJECT"].isin(offshore).sum())
    pred.loc[pred["GENERATION_PROJECT"].isin(offshore),
             ["build_gen_predetermined", "build_gen_energy_predetermined"]] = 0.0
    pred.to_csv(inp / "gen_build_predetermined.csv", index=False)
    if "gen_capacity_limit_mw" in gen.columns:
        # pandas 3.x may infer this mixed blank/numeric template column as
        # StringDtype. Convert explicitly before assigning the numeric cap.
        gen["gen_capacity_limit_mw"] = pd.to_numeric(
            gen["gen_capacity_limit_mw"], errors="coerce"
        )
        gen.loc[gen["GENERATION_PROJECT"].isin(offshore), "gen_capacity_limit_mw"] = 0.0
        # Preserve the CHEER/SWITCH explicit "." sentinel for an optional
        # capacity limit.  pandas would otherwise serialize NaN as a blank,
        # which CSV.jl reads as `missing` rather than an unconstrained entry.
        gen.to_csv(inp / "gen_info.csv", index=False, na_rep=".")
    vcf = pd.read_csv(inp / "variable_capacity_factors.csv")
    vcf.loc[vcf["GENERATION_PROJECT"].isin(offshore), "gen_max_capacity_factor"] = 0.0
    vcf.to_csv(inp / "variable_capacity_factors.csv", index=False)
    return {"offshore_projects": len(offshore), "offshore_predetermined_rows_zeroed": affected}



def restrict_operational_horizon(case_dir: Path, minimum_period: int = 2028) -> dict[str, object]:
    """Use 2023 only as a predetermined-stock anchor; operations start in 2028.

    The original template contains representative dispatch for the 2021--2025
    transition block. Re-optimizing that historical block while fixing the
    observed end-2025 storage fleet can create an artificial feasibility conflict
    and, more importantly, permits the planning model to reinterpret historical
    operations. V17 therefore retains all 2023-labelled build stock but removes
    2023 operational timepoints. The publication evidence horizon is 2028--2058.
    """
    inp = case_dir / "inputs"
    ts_path = inp / "timeseries.csv"
    tp_path = inp / "timepoints.csv"
    ts = pd.read_csv(ts_path)
    tp = pd.read_csv(tp_path)
    ts["ts_period"] = pd.to_numeric(ts["ts_period"], errors="raise").astype(int)
    kept_ts = ts.loc[ts["ts_period"] >= minimum_period].copy()
    kept_names = set(kept_ts["TIMESERIES"].astype(str))
    kept_tp = tp.loc[tp["timeseries"].astype(str).isin(kept_names)].copy()
    kept_timepoints = set(kept_tp["timepoint_id"].astype(str))

    loads_rows = {}
    for name in ["loads.csv", "loads_new.csv"]:
        f = inp / name
        if f.exists():
            df = pd.read_csv(f)
            before = len(df)
            df = df.loc[df["TIMEPOINT"].astype(str).isin(kept_timepoints)].copy()
            df.to_csv(f, index=False)
            loads_rows[name] = {"before": before, "after": len(df)}

    vcf_path = inp / "variable_capacity_factors.csv"
    vcf = pd.read_csv(vcf_path)
    vcf_before = len(vcf)
    vcf = vcf.loc[vcf["timepoint"].astype(str).isin(kept_timepoints)].copy()
    vcf.to_csv(vcf_path, index=False)

    hydro_path = inp / "hydro_timeseries.csv"
    hydro = pd.read_csv(hydro_path)
    hydro_before = len(hydro)
    hydro = hydro.loc[hydro["timeseries"].astype(str).isin(kept_names)].copy()
    hydro.to_csv(hydro_path, index=False)

    kept_ts.to_csv(ts_path, index=False)
    kept_tp.to_csv(tp_path, index=False)
    audit = {
        "minimum_operational_period": minimum_period,
        "historical_stock_anchor_period": 2023,
        "timeseries_before": len(ts),
        "timeseries_after": len(kept_ts),
        "timepoints_before": len(tp),
        "timepoints_after": len(kept_tp),
        "expected_timeseries_after": 84,
        "expected_timepoints_after": 504,
        "loads_rows": loads_rows,
        "variable_cf_rows_before": vcf_before,
        "variable_cf_rows_after": len(vcf),
        "hydro_rows_before": hydro_before,
        "hydro_rows_after": len(hydro),
        "pass": bool(len(kept_ts) == 84 and len(kept_tp) == 504),
        "scope_note": "2023-labelled capacities remain as predetermined end-2025 stock; dispatch, reserve and carbon evidence begins in 2028.",
    }
    if not audit["pass"]:
        raise ValueError(f"Operational-horizon pruning failed: {audit}")
    return audit


def apply_deep_decarbonization_policy(case_dir: Path, final_cap_tco2_per_yr: float = 2.0e8) -> dict[str, object]:
    """Set a transparent no-CDR deep-decarbonization endpoint.

    The storage-spatial-legacy paper is not a carbon-removal study. Exact zero
    with NBCCS/DACCS disabled can make feasibility depend on an artificial BECCS
    lifecycle credit. V17 instead uses a 200 MtCO2 yr-1 power-sector residual
    cap in the 2056--2060 block (about 95% below the 4.2 Gt initial cap) and keeps
    the physical one-tonne denominator. The carbon-tight pair scales this same
    trajectory to 160 MtCO2 yr-1.
    """
    f = case_dir / "inputs" / "carbon_policies.csv"
    df = pd.read_csv(f)
    df["PERIOD"] = pd.to_numeric(df["PERIOD"], errors="raise").astype(int)
    df["carbon_cap_tco2_per_yr"] = pd.to_numeric(df["carbon_cap_tco2_per_yr"], errors="raise")
    final_period = int(df["PERIOD"].max())
    old = float(df.loc[df["PERIOD"].eq(final_period), "carbon_cap_tco2_per_yr"].iloc[0])
    df.loc[df["PERIOD"].eq(final_period), "carbon_cap_tco2_per_yr"] = float(final_cap_tco2_per_yr)
    df.to_csv(f, index=False)
    initial_cap = float(df.loc[df["PERIOD"].eq(df["PERIOD"].min()), "carbon_cap_tco2_per_yr"].iloc[0])
    return {
        "policy": "deep_decarbonization_without_cdr",
        "final_period": final_period,
        "old_final_cap_tco2_per_yr": old,
        "new_final_cap_tco2_per_yr": float(final_cap_tco2_per_yr),
        "initial_cap_tco2_per_yr": initial_cap,
        "abatement_fraction_vs_initial_cap": 1.0 - float(final_cap_tco2_per_yr) / initial_cap,
        "cdr_scope": "NBCCS_DACCS_BECCS_disabled_in_official_storage_scenarios",
        "physical_storage_denominator_retained": True,
    }

def main() -> None:
    extract_template()
    offshore_audit = zero_offshore(OUT)
    sys.path.insert(0, str(ROOT / "tools"))
    import apply_existing_storage_to_case
    import apply_vre_cf_to_case
    import build_publication_vre_cf

    # Recreate only when dependency hashes require it; then fail closed on the complete source chain.
    build_publication_vre_cf.build()
    from publication_source_common import write_source_fingerprint
    write_source_fingerprint(ROOT)
    from publication_source_gate import source_checks
    source_failures = [x for x in source_checks() if not x["passed"]]
    if source_failures:
        raise RuntimeError("Publication source gate failed before base construction: " + json.dumps(source_failures, ensure_ascii=False))
    apply_existing_storage_to_case.apply(OUT, remove_existing=False)
    apply_vre_cf_to_case.apply(OUT)
    horizon_audit = restrict_operational_horizon(OUT, minimum_period=2028)
    carbon_audit = apply_deep_decarbonization_policy(OUT, final_cap_tco2_per_yr=2.0e8)
    audit = {
        "base_case": portable_path(OUT),
        "template": portable_path(TEMPLATE),
        "scope": (
            "Storage V17 publication-strict base; NBCCS/DACCS disabled; generator CCS scenario-controlled; "
            "nationally bias-corrected onshore wind plus solar PV; offshore wind excluded; "
            "2023 is stock-only; operations start in 2028; no CDR in official storage scenarios; "
            "deep-decarbonization endpoint is 200 MtCO2/yr in the 2058-labelled block"
        ),
        "operational_horizon_audit": horizon_audit,
        "carbon_policy_audit": carbon_audit,
        **offshore_audit,
    }
    (OUT / "audits").mkdir(exist_ok=True)
    (OUT / "audits" / "storage_base_scope_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    from publication_source_common import write_base_fingerprint
    write_base_fingerprint(ROOT, OUT)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
