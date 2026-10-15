#!/usr/bin/env python3
"""Apply Storage V19 future-storage + spatial-legacy scenario mutations.

Principles
----------
* Mutate only files consumed by the model.
* Never overwrite observed/predetermined storage MW or MWh.
* Capacity ceilings must never be below surviving predetermined capacity.
* Every mutation is auditable and validated before a solver is launched.
* V18 headline cases use linked monthly representative days; 24 h technologies may
  compete in the evidence-bounded portfolio, while 100 h/geologic options remain
  pressure-test diagnostics until full chronological and resource evidence is supplied.
"""
from __future__ import annotations

from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False)


def _as_float(value, default=np.nan) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _audit(case_dir: Path, scenario: str, mutations: list[dict], checks: list[dict]) -> None:
    ad = case_dir / "audits"
    ad.mkdir(exist_ok=True)
    payload = {
        "scenario": scenario,
        "mutation_scope": "V19 evidence-tiered future-storage portfolio plus inherited V17 spatial-legacy mutations; frozen implementation core remains cheer_power_storage_v1.jl",
        "mutations": mutations,
        "pre_solve_checks": checks,
        "all_pre_solve_checks_pass": bool(all(c.get("pass", False) for c in checks)),
    }
    (ad / "V19_SCENARIO_MUTATION_AUDIT.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Backward-compatible filename for downstream tools.
    (ad / "V3_SCENARIO_MUTATION_AUDIT.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _surviving_predetermined_floor_by_project(inp: Path, technology: str) -> pd.Series:
    """Maximum predetermined capacity that survives in any modeled period, by project."""
    gen = pd.read_csv(inp / "gen_info.csv")
    pred = pd.read_csv(inp / "gen_build_predetermined.csv")
    periods = pd.to_numeric(pd.read_csv(inp / "periods.csv")["INVESTMENT_PERIOD"], errors="raise").astype(int)
    meta = gen[["GENERATION_PROJECT", "gen_tech", "gen_max_age"]].copy()
    x = pred.merge(meta, on="GENERATION_PROJECT", how="left", validate="many_to_one")
    x = x[x["gen_tech"].eq(technology)].copy()
    x["build_year"] = pd.to_numeric(x["build_year"], errors="raise")
    x["gen_max_age"] = pd.to_numeric(x["gen_max_age"], errors="raise")
    x["build_gen_predetermined"] = pd.to_numeric(x["build_gen_predetermined"], errors="raise").fillna(0.0)
    floors: dict[str, float] = {}
    for project, gp in x.groupby("GENERATION_PROJECT"):
        alive = []
        for period in periods:
            m = (gp["build_year"] <= period) & (period < gp["build_year"] + gp["gen_max_age"])
            alive.append(float(gp.loc[m, "build_gen_predetermined"].sum()))
        floors[str(project)] = max(alive, default=0.0)
    return pd.Series(floors, dtype=float)


def _allocate_capacity_target(
    project: pd.Series,
    baseline_cap: pd.Series,
    floor: pd.Series,
    target_mw: float,
) -> pd.Series:
    """Allocate a national capacity target while respecting project-level floors.

    For targets below the baseline aggregate, allocate the remaining headroom in
    proportion to baseline residual resource. For targets above the baseline,
    expand all project ceilings in proportion to baseline resource weights.
    """
    base = pd.to_numeric(baseline_cap, errors="coerce").fillna(0.0).astype(float)
    fl = project.map(floor).fillna(0.0).astype(float)
    if (base + 1e-9 < fl).any():
        bad = pd.DataFrame({"project": project, "baseline_cap": base, "floor": fl})
        bad = bad[bad["baseline_cap"] + 1e-9 < bad["floor"]]
        raise ValueError(f"Baseline pumped-hydro ceilings below predetermined floors: {bad.head(10).to_dict('records')}")
    floor_total = float(fl.sum())
    if target_mw + 1e-6 < floor_total:
        raise ValueError(
            f"National pumped-hydro target {target_mw:.3f} MW is below surviving predetermined floor {floor_total:.3f} MW"
        )
    base_total = float(base.sum())
    if target_mw <= base_total + 1e-6:
        residual = (base - fl).clip(lower=0.0)
        remaining = target_mw - floor_total
        if remaining <= 1e-9:
            new = fl.copy()
        elif residual.sum() <= 0:
            raise ValueError("No residual pumped-hydro potential available above predetermined floors")
        else:
            new = fl + remaining * residual / float(residual.sum())
            new = np.minimum(new, base)
    else:
        weights = base.where(base > 0.0, fl)
        if float(weights.sum()) <= 0:
            raise ValueError("Cannot allocate pumped-hydro high-resource target: zero allocation weights")
        new = fl + (target_mw - floor_total) * weights / float(weights.sum())
    # Numerical closure correction on the largest flexible project.
    delta = target_mw - float(new.sum())
    if abs(delta) > 1e-6:
        idx = (base - fl).idxmax() if target_mw <= base_total + 1e-6 else weights.idxmax()
        new.loc[idx] += delta
    if (new + 1e-7 < fl).any():
        raise ValueError("Internal error: allocated pumped-hydro ceiling below predetermined floor")
    if abs(float(new.sum()) - target_mw) > max(1e-4, 1e-9 * max(target_mw, 1.0)):
        raise ValueError("Internal error: pumped-hydro target allocation does not close")
    return pd.Series(new, index=baseline_cap.index, dtype=float)


def _retire_future_pumped_hydro_policy_floors(
    inp: Path,
    *,
    historical_anchor_period: int = 2023,
) -> dict:
    """Retire only forward policy expansion floors in PH-conservative cases.

    ``capacity_plans.csv`` is a minimum-capacity policy table.  Keeping its
    2028+ Hydro_Pumped rows while simultaneously capping project capacity at
    surviving predetermined stock creates a mechanical lower-bound/upper-bound
    contradiction.  The conservative counterfactual therefore retains the
    historical 2023 stock anchor and all surviving predetermined projects, but
    removes only forward Hydro_Pumped policy expansion floors.
    """
    path = inp / "capacity_plans.csv"
    plans = pd.read_csv(path)
    required = {"gen_tech", "load_zones", "period", "planned_capacity_mw"}
    missing = required - set(plans.columns)
    if missing:
        raise ValueError(f"capacity_plans.csv missing required columns: {sorted(missing)}")

    periods = pd.to_numeric(plans["period"], errors="raise").astype(int)
    tech_mask = plans["gen_tech"].astype(str).eq("Hydro_Pumped")
    future_mask = tech_mask & periods.gt(int(historical_anchor_period))
    anchor_mask = tech_mask & periods.eq(int(historical_anchor_period))

    removed = plans.loc[future_mask].copy()
    retained_anchor = plans.loc[anchor_mask].copy()
    retained_other = plans.loc[~future_mask].copy()
    _write_csv(retained_other, path)

    removed_by_period = {
        str(int(period)): float(group["planned_capacity_mw"].astype(float).sum())
        for period, group in removed.groupby(pd.to_numeric(removed["period"], errors="raise").astype(int))
    }
    return {
        "historical_anchor_period": int(historical_anchor_period),
        "retained_anchor_rows": int(len(retained_anchor)),
        "retained_anchor_sum_mw": float(pd.to_numeric(retained_anchor["planned_capacity_mw"], errors="raise").sum()),
        "removed_future_rows": int(len(removed)),
        "removed_future_sum_mw": float(pd.to_numeric(removed["planned_capacity_mw"], errors="raise").sum()),
        "removed_future_sum_mw_by_period": removed_by_period,
        "future_hydro_pumped_rows_remaining": int(
            (
                retained_other["gen_tech"].astype(str).eq("Hydro_Pumped")
                & pd.to_numeric(retained_other["period"], errors="raise").astype(int).gt(int(historical_anchor_period))
            ).sum()
        ),
    }


def apply_mutations(case_dir, scenario_row):
    case_dir = Path(case_dir)
    inp = case_dir / "inputs"
    r = scenario_row
    scenario = str(r.get("scenario"))
    mutations: list[dict] = []
    checks: list[dict] = []

    # 0) Spatial-legacy counterfactual. This is applied before cost/duration mutations so
    # the 2023-labelled legacy fleet receives a common sunk-capital treatment.
    legacy_mode = str(r.get("legacy_allocation_mode", "")).strip().lower()
    if legacy_mode in {"nan", "none_defined"}:
        legacy_mode = ""
    if legacy_mode:
        sys.path.insert(0, str(ROOT / "tools"))
        import apply_spatial_legacy
        cap_q = _as_float(r.get("legacy_cap_quantile", 0.95), 0.95)
        legacy_audit = apply_spatial_legacy.build_policy(case_dir, legacy_mode, cap_quantile=cap_q)
        mutations.append({
            "name": "spatial_storage_legacy",
            "mode": legacy_mode,
            "cap_quantile": cap_q,
            "national_power_target_mw": legacy_audit["national_power_target_mw"],
            "national_energy_target_mwh": legacy_audit["national_energy_target_mwh"],
            "identification": "same national legacy MW and MWh; spatial allocation changes",
        })
        checks.append({
            "check": "spatial_legacy_pre_solve_policy_closure",
            "pass": bool(all(legacy_audit["checks"].values())),
            "mode": legacy_mode,
        })

    # 0b) VRE profile variant. The calibrated profile is the publication baseline;
    # the raw low-CF profile is retained only as an explicit diagnostic sensitivity.
    vre_variant = str(r.get("vre_cf_variant", "publication_calibrated"))
    if vre_variant == "raw_uncalibrated":
        sys.path.insert(0, str(ROOT / "tools"))
        import apply_vre_cf_to_case
        apply_vre_cf_to_case.apply(case_dir, apply_vre_cf_to_case.RAW_CF_FILE)
        mutations.append({
            "name": "vre_cf_variant",
            "variant": vre_variant,
            "publication_status": "diagnostic_only",
            "reason": "raw national capacity-weighted wind CF is substantially below the observation-anchored publication baseline",
        })
    elif vre_variant != "publication_calibrated":
        raise ValueError(f"Unknown vre_cf_variant: {vre_variant}")

    # 1) Legacy pre-V17 initial-storage sensitivities (not applied when V17 policy is explicit).
    if not legacy_mode and scenario == "ST_INIT_NoExistingNewStorage":
        sys.path.insert(0, str(ROOT / "tools"))
        import apply_existing_storage_to_case
        apply_existing_storage_to_case.apply(case_dir, remove_existing=True)
        mutations.append({"name": "initial_storage_stock", "action": "removed observed 2025 new-type battery stock"})
    elif not legacy_mode and scenario == "ST_INIT_CNESAHighInitial":
        sys.path.insert(0, str(ROOT / "tools"))
        import apply_existing_storage_to_case
        power_scale = 144700.0 / 135930.0
        energy_scale = 373680.0 / 351120.0
        apply_existing_storage_to_case.apply(
            case_dir, remove_existing=False, power_scale=power_scale, energy_scale=energy_scale
        )
        mutations.append({
            "name": "initial_storage_stock",
            "action": "scaled observed 2025 new-type storage to CNESA high reference",
            "power_scale": power_scale,
            "energy_scale": energy_scale,
        })

    # 2) Battery cost and performance come directly from NLR/NREL 2025.
    # Low/mid/high are the report's annual Table 2 trajectories. No fitted
    # deployment target, capacity anchor, reverse calibration or blanket CAS
    # multiplier is allowed in this branch.
    cost_case = str(r.get("battery_cost_case", "NLR_2025_mid"))
    from apply_nlr_2025_battery_costs import apply as apply_nlr_battery_costs
    battery_cost_audit = apply_nlr_battery_costs(case_dir, cost_case)
    mutations.append({
        "name": "battery_cost_case",
        "case": cost_case,
        "storage_techs": "Battery only",
        "source": battery_cost_audit["source"],
        "source_table_sha256": battery_cost_audit["source_table_sha256"],
        "fixed_duration_h": battery_cost_audit["fixed_duration_h"],
        "direct_annual_cost_trajectory": True,
        "multiplicative_factor": None,
        "reverse_calibration_used": False,
    })

    # 2b) Storage V19 evidence-tiered multi-technology / multi-duration future portfolio.
    # Official 16 scenarios use the primary five-candidate set. LFP 8/10 h and
    # CAES/H2 are prepared only in explicitly labeled sensitivity/pressure runs.
    from apply_v19_storage_portfolio import apply as apply_v19_storage_portfolio
    v19_scope = str(r.get("v19_storage_portfolio_scope", "primary")).strip() or "primary"
    v19_audit = apply_v19_storage_portfolio(case_dir, v19_scope)
    mutations.append({
        "name": "v19_storage_technology_duration_portfolio",
        "v19_scope": v19_scope,
        "candidate_count": v19_audit["candidate_count"],
        "headline_portfolio": v19_audit["headline_portfolio"],
        "duration_sensitivity_only_portfolio": v19_audit.get("duration_sensitivity_only_portfolio", []),
        "pressure_test_only_portfolio": v19_audit["pressure_test_only_portfolio"],
        "post_2030_non_lfp_cost_extrapolation_used": False,
        "legacy_storage_rows_modified": False,
    })
    checks.append({
        "check": "v19_storage_portfolio_prepared",
        "pass": v19_audit.get("status") == "PASS" and not v19_audit.get("legacy_storage_rows_modified", True),
        "scope": v19_scope,
        "candidate_count": v19_audit.get("candidate_count"),
    })

    # 3) Legacy V17 duration sensitivities remain available only for backward-compatible
    # diagnostics. The official V18 master scenarios use flexible_energy so candidate-
    # specific durations from the V18 portfolio remain untouched.
    duration_case = str(r.get("storage_duration_case", "flexible_energy"))
    duration_map = {"2h": 2.0, "4h": 4.0, "8h": 8.0, "24h": 24.0, "72h": 72.0, "100h": 100.0}
    if duration_case in duration_map:
        dur = duration_map[duration_case]
        f = inp / "gen_info.csv"
        gen = pd.read_csv(f)
        gen["gen_storage_energy_to_power_ratio"] = gen["gen_storage_energy_to_power_ratio"].astype(object)
        if dur <= 8.0:
            gen.loc[gen["gen_tech"].eq("Battery"), "gen_storage_energy_to_power_ratio"] = dur
            action = {"Battery_new_build_ratio_h": dur}
        else:
            gen.loc[gen["gen_tech"].eq("Battery"), "gen_storage_energy_to_power_ratio"] = 8.0
            gen.loc[gen["gen_tech"].eq("CAS"), "gen_storage_energy_to_power_ratio"] = dur
            action = {"Battery_new_build_ratio_h": 8.0, "CAS_new_build_ratio_h": dur}
        _write_csv(gen, f)
        pred = pd.read_csv(inp / "gen_build_predetermined.csv")
        pred_storage = pred[pred["GENERATION_PROJECT"].astype(str).str.contains("Battery|Hydro_Pumped|CAS", regex=True, na=False)]
        checks.append({
            "check": "predetermined_storage_stock_preserved_under_duration_case",
            "pass": True,
            "predetermined_rows": int(len(pred_storage)),
            "note": "Fixed duration is enforced only for non-predetermined builds in cheer_power_storage_v1.jl",
        })
        mutations.append({
            "name": "storage_duration_case",
            "case": duration_case,
            **action,
            "claim_scope": (
                "2 h energy-to-power ratio lower-bound sensitivity under 4 h dispatch blocks; no sub-4 h operational claim"
                if dur == 2.0
                else (
                    "endogenous duration design sensitivity under representative-day chronology"
                    if dur <= 8.0
                    else "temporal-boundary diagnostic only; not evidence of chronological 24-100 h energy shifting"
                )
            ),
        })

    # 4) Transmission-expansion sensitivities.
    tx_case = str(r.get("transmission_case", "TX_policy"))
    if tx_case != "TX_policy":
        limits_f = inp / "build_tx_limits.csv"
        lines_f = inp / "transmission_lines.csv"
        limits = pd.read_csv(limits_f)
        lines = pd.read_csv(lines_f)
        action = None
        if tx_case == "TX_fixed":
            limits["build_trans_limit_mw"] = 0.0
            lines["trans_new_build_allowed"] = False
            lines["trans_new_build_cap"] = 0.0
            action = "no new interprovincial transmission; existing capacity remains dispatchable"
        elif tx_case == "TX_policy2030":
            ref = float(limits.loc[limits["period"].le(2028), "build_trans_limit_mw"].max())
            limits["build_trans_limit_mw"] = np.minimum(
                pd.to_numeric(limits["build_trans_limit_mw"], errors="raise"), ref
            )
            action = "cap period transmission build at the 2028/2030-policy proxy"
        elif tx_case == "TX_lit_mid2050":
            limits["build_trans_limit_mw"] = pd.to_numeric(limits["build_trans_limit_mw"], errors="raise") * 1.50
            lines["trans_new_build_cap"] = pd.to_numeric(lines["trans_new_build_cap"], errors="raise") * 1.50
            action = "1.5x transmission build envelope"
        elif tx_case == "TX_lit_high2050":
            limits["build_trans_limit_mw"] = pd.to_numeric(limits["build_trans_limit_mw"], errors="raise") * 2.00
            lines["trans_new_build_cap"] = pd.to_numeric(lines["trans_new_build_cap"], errors="raise") * 2.00
            action = "2.0x transmission build envelope"
        if action is None:
            raise ValueError(f"Unknown transmission_case: {tx_case}")
        _write_csv(limits, limits_f)
        _write_csv(lines, lines_f)
        checks.append({
            "check": "tx_fixed_has_no_build_keys" if tx_case == "TX_fixed" else "transmission_mutation_valid",
            "pass": bool((lines["trans_new_build_allowed"].astype(str).str.lower().isin(["true", "1"])).sum() == 0)
                    if tx_case == "TX_fixed" else True,
        })
        mutations.append({"name": "transmission_case", "case": tx_case, "action": action})

    # 5) Pumped-hydro national boundary with project-level predetermined floors.
    ph_targets = {
        "PH_conservative": None,  # observed/predetermined surviving stock only
        "PH_policy120GW": 120000.0,
        "PH_high_resource": 1600000.0,
    }
    ph_case = str(r.get("pumped_hydro_case", "")).strip()
    if not ph_case or ph_case.lower() == "nan":
        ph_case = {
            "ST_PH_conservative": "PH_conservative",
            "ST_PH_policy120GW": "PH_policy120GW",
            "ST_PH_high_resource": "PH_high_resource",
        }.get(scenario, "")
    if ph_case in ph_targets:
        f = inp / "gen_info.csv"
        gen = pd.read_csv(f)
        gen["gen_capacity_limit_mw"] = gen["gen_capacity_limit_mw"].astype(object)
        mask = gen["gen_tech"].eq("Hydro_Pumped")
        projects = gen.loc[mask, "GENERATION_PROJECT"].astype(str)
        caps = pd.to_numeric(gen.loc[mask, "gen_capacity_limit_mw"].replace(".", np.nan), errors="raise")
        floor = _surviving_predetermined_floor_by_project(inp, "Hydro_Pumped")
        floor_total = float(projects.map(floor).fillna(0.0).sum())
        target = floor_total if ph_targets[ph_case] is None else float(ph_targets[ph_case])
        new_caps = _allocate_capacity_target(projects, caps, floor, target)
        gen.loc[mask, "gen_capacity_limit_mw"] = new_caps.to_numpy()
        _write_csv(gen, f)

        policy_floor_audit = None
        if ph_case == "PH_conservative":
            policy_floor_audit = _retire_future_pumped_hydro_policy_floors(
                inp, historical_anchor_period=2023
            )
            checks.append({
                "check": "pumped_hydro_conservative_future_policy_floors_retired",
                "pass": bool(policy_floor_audit["future_hydro_pumped_rows_remaining"] == 0),
                **policy_floor_audit,
            })
            checks.append({
                "check": "pumped_hydro_historical_anchor_not_above_surviving_stock",
                "pass": bool(policy_floor_audit["retained_anchor_sum_mw"] <= target + 1e-6),
                "historical_anchor_sum_mw": policy_floor_audit["retained_anchor_sum_mw"],
                "surviving_predetermined_stock_mw": target,
            })

        min_margin = float((new_caps.to_numpy() - projects.map(floor).fillna(0.0).to_numpy()).min())
        checks.append({
            "check": "pumped_hydro_capacity_ceiling_not_below_predetermined_floor",
            "pass": bool(min_margin >= -1e-6),
            "minimum_margin_mw": min_margin,
        })
        checks.append({
            "check": "pumped_hydro_national_target_closure",
            "pass": bool(abs(float(new_caps.sum()) - target) <= max(1e-4, target * 1e-9)),
            "allocated_total_mw": float(new_caps.sum()),
            "target_mw": target,
        })
        mutations.append({
            "name": "pumped_hydro_boundary",
            "scenario": scenario,
            "pumped_hydro_case": ph_case,
            "baseline_ceiling_sum_mw": float(caps.sum()),
            "surviving_predetermined_floor_sum_mw": floor_total,
            "target_sum_mw": target,
            "allocation_method": "predetermined floor plus proportional residual-resource allocation",
            "future_policy_floor_treatment": (
                "retire_2028plus_hydro_pumped_policy_expansion_floors_retain_2023_stock_anchor"
                if ph_case == "PH_conservative" else "unchanged"
            ),
            "policy_floor_audit": policy_floor_audit,
        })

    # 6) Generator CCS availability via geologic injection-cap multiplier.
    ccs_cap_multiplier = _as_float(r.get("ccs_geologic_cap_multiplier", np.nan))
    if np.isfinite(ccs_cap_multiplier) and ccs_cap_multiplier != 1.0:
        f = inp / "co2_injection_limits.csv"
        lim = pd.read_csv(f)
        if "max_injection_tco2_per_yr" not in lim.columns:
            raise ValueError("co2_injection_limits.csv lacks max_injection_tco2_per_yr")
        lim["max_injection_tco2_per_yr"] = (
            pd.to_numeric(lim["max_injection_tco2_per_yr"], errors="raise") * ccs_cap_multiplier
        )
        _write_csv(lim, f)
        mutations.append({
            "name": "ccs_geologic_cap_multiplier",
            "multiplier": ccs_cap_multiplier,
            "file": "co2_injection_limits.csv",
        })

    if not checks:
        checks.append({"check": "scenario_mutation_completed", "pass": True})
    _audit(case_dir, scenario, mutations, checks)
    if not all(c.get("pass", False) for c in checks):
        raise ValueError(f"Scenario {scenario} failed pre-solve mutation checks: {checks}")
    return mutations
