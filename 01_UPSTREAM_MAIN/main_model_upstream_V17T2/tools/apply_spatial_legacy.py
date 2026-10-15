#!/usr/bin/env python3
"""Construct auditable 2025 storage-spatial-legacy counterfactuals.

The central identification strategy holds national existing new-type storage power
and energy constant and changes only its provincial/model-zone allocation.

Modes
-----
observed_actual
    Compatibility name for a declared heterogeneous-duration sensitivity. Power
    follows the NEA-constrained provincial reconstruction; province duration
    ratios come from the frozen user-compiled prior and are nationally rescaled.
    This mode is not an official province-level energy inventory.
observed_standardized
    NEA-constrained reconstructed zone MW with the exact national-average duration.
    This is the primary spatial reference.
optimized_reallocation
    The model chooses the 2023-labelled legacy allocation subject to exactly the
    same national MW and MWh totals, a common duration and an empirically anchored
    zone deployment envelope. The 2023 legacy build is treated as sunk capital.
none
    No 2025 new-type storage legacy.
rule_load / rule_vre
    Same national MW and MWh allocated by 2023 coincident peak or surviving
    wind+solar capacity, respectively, under the same empirical envelope.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import math
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OBSERVED = ROOT / "data" / "processed" / "existing_new_storage_allocated_to_model_zones_2025.csv"
INITIALIZATION_PERIOD = 2023
DEFAULT_CAP_QUANTILE = 0.95
TOL_MW = 1e-5
TOL_MWH = 1e-4


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.replace(".", np.nan), errors="coerce")


def _battery_metadata(inp: Path) -> pd.DataFrame:
    gen = pd.read_csv(inp / "gen_info.csv")
    b = gen.loc[gen["gen_tech"].eq("Battery"), [
        "GENERATION_PROJECT", "gen_load_zone", "gen_max_age"
    ]].copy()
    b = b.rename(columns={"gen_load_zone": "model_zone"})
    if b["model_zone"].duplicated().any() or len(b) != 32:
        raise ValueError("Expected exactly one Battery project in each of 32 model zones")
    return b


def _peak_2023(inp: Path) -> pd.Series:
    peak = pd.read_csv(inp / "zone_coincident_peak_demand.csv")
    peak["PERIOD"] = pd.to_numeric(peak["PERIOD"], errors="raise").astype(int)
    x = peak.loc[peak["PERIOD"].eq(INITIALIZATION_PERIOD)].copy()
    if x["LOAD_ZONE"].duplicated().any():
        raise ValueError("Duplicate 2023 zone coincident peak rows")
    return pd.Series(
        pd.to_numeric(x["zone_expected_coincident_peak_demand"], errors="raise").to_numpy(),
        index=x["LOAD_ZONE"].astype(str), dtype=float,
    )


def _surviving_vre_capacity_2023(inp: Path) -> pd.Series:
    gen = pd.read_csv(inp / "gen_info.csv")
    pred = pd.read_csv(inp / "gen_build_predetermined.csv")
    meta = gen[["GENERATION_PROJECT", "gen_load_zone", "gen_tech", "gen_max_age"]].copy()
    x = pred.merge(meta, on="GENERATION_PROJECT", how="left", validate="many_to_one")
    x["build_year"] = pd.to_numeric(x["build_year"], errors="raise")
    x["gen_max_age"] = pd.to_numeric(x["gen_max_age"], errors="raise")
    x["build_gen_predetermined"] = pd.to_numeric(x["build_gen_predetermined"], errors="raise").fillna(0.0)
    x = x[x["gen_tech"].isin(["Wind", "Solar_PV"])]
    x = x[(x["build_year"] <= INITIALIZATION_PERIOD) &
          (INITIALIZATION_PERIOD < x["build_year"] + x["gen_max_age"])]
    return x.groupby("gen_load_zone")["build_gen_predetermined"].sum().astype(float)


def _capped_proportional(weights: pd.Series, caps: pd.Series, target: float) -> pd.Series:
    """Iterative capped proportional allocation with exact national closure."""
    w = weights.astype(float).clip(lower=0.0).copy()
    c = caps.astype(float).clip(lower=0.0).copy()
    if target < -TOL_MW or target > float(c.sum()) + TOL_MW:
        raise ValueError(f"Target {target} is outside feasible cap sum {float(c.sum())}")
    allocation = pd.Series(0.0, index=c.index)
    active = pd.Series(True, index=c.index)
    remaining = float(target)
    for _ in range(len(c) + 2):
        if remaining <= TOL_MW:
            break
        idx = active[active].index
        if len(idx) == 0:
            break
        ww = w.loc[idx]
        if float(ww.sum()) <= 0:
            ww = pd.Series(1.0, index=idx)
        proposal = remaining * ww / float(ww.sum())
        room = c.loc[idx] - allocation.loc[idx]
        hit = proposal >= room - TOL_MW
        if not bool(hit.any()):
            allocation.loc[idx] += proposal
            remaining = 0.0
            break
        hit_idx = hit[hit].index
        allocation.loc[hit_idx] = c.loc[hit_idx]
        active.loc[hit_idx] = False
        remaining = target - float(allocation.sum())
    delta = target - float(allocation.sum())
    if abs(delta) > TOL_MW:
        room = (c - allocation).clip(lower=0.0)
        idx = room.idxmax()
        if room.loc[idx] + TOL_MW < delta:
            raise ValueError("Capped proportional allocation failed national closure")
        allocation.loc[idx] += delta
    if (allocation < -TOL_MW).any() or (allocation - c > TOL_MW).any():
        raise ValueError("Allocation violates non-negativity or cap")
    return allocation


def _zero_legacy_capex(inp: Path) -> dict:
    """Treat the 2025 storage fleet as a sunk asset in all legacy counterfactuals."""
    f = inp / "gen_build_costs.csv"
    costs = pd.read_csv(f)
    mask = costs["GENERATION_PROJECT"].astype(str).str.endswith("-Battery") & \
           pd.to_numeric(costs["build_year"], errors="raise").eq(INITIALIZATION_PERIOD)
    count = int(mask.sum())
    for col in ["gen_overnight_cost", "gen_storage_energy_overnight_cost"]:
        # The template uses blank strings for inapplicable costs; pandas 3.x
        # may therefore infer StringDtype. Coerce before writing numeric zeros.
        costs[col] = pd.to_numeric(costs[col], errors="coerce")
        costs.loc[mask, col] = 0.0
    costs.to_csv(f, index=False)
    return {"rows": count, "power_capex_zero": True, "energy_capex_zero": True,
            "fixed_om_retained": True}


def _rewrite_predetermined(inp: Path, fixed: pd.DataFrame | None) -> int:
    meta = _battery_metadata(inp)
    battery_projects = set(meta["GENERATION_PROJECT"].astype(str))
    f = inp / "gen_build_predetermined.csv"
    pred = pd.read_csv(f)
    pred = pred[~(pred["GENERATION_PROJECT"].astype(str).isin(battery_projects) &
                  pd.to_numeric(pred["build_year"], errors="raise").eq(INITIALIZATION_PERIOD))].copy()
    rows = []
    if fixed is not None:
        mapping = meta.set_index("model_zone")["GENERATION_PROJECT"]
        for zone, r in fixed.set_index("model_zone").iterrows():
            rows.append({
                "GENERATION_PROJECT": mapping.loc[zone],
                "build_year": INITIALIZATION_PERIOD,
                "build_gen_predetermined": float(r["fixed_power_mw"]),
                "build_gen_energy_predetermined": float(r["fixed_energy_mwh"]),
            })
        pred = pd.concat([pred, pd.DataFrame(rows)], ignore_index=True)
    pred.to_csv(f, index=False)
    return len(rows)


def build_policy(case_dir: str | Path, mode: str, *, cap_quantile: float = DEFAULT_CAP_QUANTILE) -> dict:
    case_dir = Path(case_dir)
    inp = case_dir / "inputs"
    if not inp.exists():
        raise FileNotFoundError(inp)
    mode = str(mode).strip().lower()
    allowed = {"observed_actual", "observed_standardized", "optimized_reallocation",
               "none", "rule_load", "rule_vre"}
    if mode not in allowed:
        raise ValueError(f"Unknown legacy allocation mode {mode}; expected {sorted(allowed)}")

    meta = _battery_metadata(inp)
    obs = pd.read_csv(OBSERVED)[[
        "model_zone", "existing_new_storage_power_mw", "existing_new_storage_energy_mwh",
        "existing_new_storage_energy_mwh_compiled_duration_sensitivity", "data_version"
    ]].copy()
    zones = meta["model_zone"].astype(str).tolist()
    obs = obs.set_index("model_zone").reindex(zones)
    if obs.isna().any().any():
        raise ValueError("Observed legacy data do not cover all model zones")
    national_power = float(obs["existing_new_storage_power_mw"].sum())
    national_energy = float(obs["existing_new_storage_energy_mwh"].sum())
    compiled_duration_energy = float(obs["existing_new_storage_energy_mwh_compiled_duration_sensitivity"].sum())
    duration = national_energy / national_power
    if set(obs["data_version"].astype(str)) != {"NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2"}:
        raise ValueError("Storage allocation data_version does not match the publication source update")
    peak = _peak_2023(inp).reindex(zones)
    if peak.isna().any() or (peak <= 0).any():
        raise ValueError("Invalid 2023 coincident peak data for legacy envelope")
    observed_ratio = obs["existing_new_storage_power_mw"] / peak
    cap_ratio = float(observed_ratio.quantile(cap_quantile, interpolation="linear"))
    raw_caps = peak * cap_ratio
    # Fair identification requires the optimized feasible set to contain the observed
    # reference allocation. We therefore use a p95 empirical envelope with
    # grandfathered reconstructed-zone floors wherever the observed stock is higher.
    caps = pd.concat([raw_caps, obs["existing_new_storage_power_mw"]], axis=1).max(axis=1)
    cap_exception = obs["existing_new_storage_power_mw"] > raw_caps + TOL_MW

    weights = pd.Series(0.0, index=zones)
    fixed: pd.DataFrame | None = None
    if mode == "observed_actual":
        power = obs["existing_new_storage_power_mw"].copy()
        energy = obs["existing_new_storage_energy_mwh_compiled_duration_sensitivity"].copy()
        weights = power.copy()
        fixed = pd.DataFrame({"model_zone": zones, "fixed_power_mw": power.values,
                              "fixed_energy_mwh": energy.values})
    elif mode == "observed_standardized":
        power = obs["existing_new_storage_power_mw"].copy()
        energy = power * duration
        weights = power.copy()
        fixed = pd.DataFrame({"model_zone": zones, "fixed_power_mw": power.values,
                              "fixed_energy_mwh": energy.values})
    elif mode == "none":
        fixed = None
    elif mode in {"rule_load", "rule_vre"}:
        weights = peak.copy() if mode == "rule_load" else _surviving_vre_capacity_2023(inp).reindex(zones).fillna(0.0)
        power = _capped_proportional(weights, caps, national_power)
        energy = power * duration
        fixed = pd.DataFrame({"model_zone": zones, "fixed_power_mw": power.values,
                              "fixed_energy_mwh": energy.values})
    elif mode == "optimized_reallocation":
        # Endogenous 2023 legacy build; exact national totals and zone caps are imposed in Julia.
        fixed = None

    rows_added = _rewrite_predetermined(inp, fixed)
    sunk = _zero_legacy_capex(inp)
    policy = pd.DataFrame({
        "model_zone": zones,
        "battery_project": meta.set_index("model_zone").loc[zones, "GENERATION_PROJECT"].values,
        "legacy_allocation_mode": mode,
        "legacy_reference_case": "China_2025_NEA_constrained_provincial_reconstruction",
        "national_power_target_mw": 0.0 if mode == "none" else national_power,
        "national_energy_target_mwh": 0.0 if mode == "none" else national_energy,
        "standardized_duration_h": duration,
        "empirical_cap_quantile": float(cap_quantile),
        "empirical_cap_ratio_to_2023_peak": cap_ratio,
        "zone_peak_2023_mw": peak.values,
        "raw_empirical_power_cap_mw": raw_caps.values,
        "legacy_power_cap_mw": caps.values,
        "observed_grandfathered_cap_floor": cap_exception.astype(int).values,
        "fixed_power_mw": 0.0 if fixed is None else fixed.set_index("model_zone").loc[zones, "fixed_power_mw"].values,
        "fixed_energy_mwh": 0.0 if fixed is None else fixed.set_index("model_zone").loc[zones, "fixed_energy_mwh"].values,
        "allocation_weight": weights.reindex(zones).fillna(0.0).values,
        "allocation_source": {
            "observed_actual": "nea_constrained_power_plus_compiled_duration_pattern_sensitivity_not_official_province_energy",
            "observed_standardized": "nea_constrained_reconstructed_power_common_exact_national_duration",
            "optimized_reallocation": "endogenous_system_cost_minimization_same_national_totals",
            "none": "no_2025_new_type_storage_legacy",
            "rule_load": "2023_coincident_peak_proportional_capped",
            "rule_vre": "surviving_2023_wind_solar_capacity_proportional_capped",
        }[mode],
        "legacy_cap_scope": "2023_legacy_allocation_only_not_future_builds",
        "legacy_capex_treatment": "sunk_power_and_energy_capex_fixed_om_retained",
    })
    policy.to_csv(inp / "legacy_storage_policy.csv", index=False)

    checks = {
        "all_32_zones_present": len(policy) == 32 and policy["model_zone"].nunique() == 32,
        "national_power_closes_135930mw": abs(national_power - 135930.0) <= TOL_MW,
        "national_standardized_energy_closes_351120mwh": abs(national_energy - 351120.0) <= TOL_MWH,
        "compiled_duration_sensitivity_energy_closes_351120mwh": abs(compiled_duration_energy - 351120.0) <= TOL_MWH,
        "fixed_power_closure": True if fixed is None else abs(float(fixed["fixed_power_mw"].sum()) - national_power) <= TOL_MW,
        "fixed_energy_closure": True if fixed is None else abs(float(fixed["fixed_energy_mwh"].sum()) - national_energy) <= TOL_MWH,
        "fixed_allocation_nonnegative": True if fixed is None else bool((fixed[["fixed_power_mw", "fixed_energy_mwh"]] >= -TOL_MW).all().all()),
        "optimized_cap_feasible": float(caps.sum()) + TOL_MW >= national_power,
        "observed_reference_inside_optimized_envelope": bool((obs["existing_new_storage_power_mw"] <= caps + TOL_MW).all()),
        "sunk_capex_rows_complete": sunk["rows"] == 32,
    }
    if not all(checks.values()):
        raise ValueError(f"Legacy policy pre-solve checks failed: {checks}")
    audit = {
        "version": "V17",
        "mode": mode,
        "national_power_target_mw": national_power if mode != "none" else 0.0,
        "national_energy_target_mwh": national_energy if mode != "none" else 0.0,
        "compiled_duration_sensitivity_energy_mwh": compiled_duration_energy if mode != "none" else 0.0,
        "national_average_duration_h": duration,
        "data_version": "NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2",
        "province_inventory_status": "NEA-constrained model reconstruction; not an official 31-province inventory",
        "empirical_cap_quantile": cap_quantile,
        "empirical_cap_ratio_to_2023_peak": cap_ratio,
        "raw_empirical_cap_sum_mw": float(raw_caps.sum()),
        "publication_deployment_cap_sum_mw": float(caps.sum()),
        "grandfathered_zone_count": int(cap_exception.sum()),
        "maximum_observed_ratio_to_peak": float(observed_ratio.max()),
        "rows_added_to_predetermined": rows_added,
        "sunk_capex_mutation": sunk,
        "checks": checks,
        "identification_note": (
            "The primary reconstructed-standardized versus optimized-reallocation comparison holds exact national legacy MW, MWh, "
            "common duration, technology and sunk-capital treatment constant; only model-zone location changes. "
            "The optimized feasible envelope is the p95 storage-to-peak rule with reconstructed-zone "
            "floors, so the reconstructed reference is always feasible under the optimized counterfactual."
        ),
    }
    ad = case_dir / "audits"
    ad.mkdir(exist_ok=True)
    (ad / "V17_SPATIAL_LEGACY_POLICY_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return audit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    ap.add_argument("--mode", required=True,
                    choices=["observed_actual", "observed_standardized", "optimized_reallocation",
                             "none", "rule_load", "rule_vre"])
    ap.add_argument("--cap-quantile", type=float, default=DEFAULT_CAP_QUANTILE)
    args = ap.parse_args()
    print(json.dumps(build_policy(args.case_dir, args.mode, cap_quantile=args.cap_quantile),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
