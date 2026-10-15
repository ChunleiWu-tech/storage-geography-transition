#!/usr/bin/env python3
"""Targeted pre-solve audit for the V17T1 four-scenario repair.

This audit checks only the declared repair boundary.  It does not introduce a
new global model/input regression gate and does not modify any prepared case.
"""
from __future__ import annotations

from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "storage_cases"
OUT = ROOT / "audits" / "V17T1_FOUR_SCENARIO_REPAIR_AUDIT.json"
PH = ["SL08_PH_CONSERVATIVE_OBSERVED", "SL09_PH_CONSERVATIVE_OPTIMAL"]
HARD = ["SL10_CARBON_TIGHT_OBSERVED", "SL13_COST_LOW_OPTIMAL"]
STANDARD = [
    "SL00_OBSERVED_ACTUAL", "SL01_OBSERVED_STANDARDIZED",
    "SL02_OPTIMAL_REALLOCATION", "SL03_NO_LEGACY", "SL04_RULE_LOAD",
    "SL05_RULE_VRE", "SL06_TX_FIXED_OBSERVED", "SL07_TX_FIXED_OPTIMAL",
    "SL11_CARBON_TIGHT_OPTIMAL", "SL12_COST_LOW_OBSERVED",
    "SL14_COST_HIGH_OBSERVED", "SL15_COST_HIGH_OPTIMAL",
]


def add(rows, name, passed, detail):
    rows.append({"check": name, "pass": bool(passed), "detail": detail})


def main():
    rows = []
    expected = set(PH + HARD + STANDARD)
    prepared = {p.name for p in CASES.iterdir() if p.is_dir()} if CASES.exists() else set()
    add(rows, "sixteen_declared_cases_prepared", expected <= prepared, {"missing": sorted(expected - prepared)})

    for sc in PH:
        inp = CASES / sc / "inputs"
        plans = pd.read_csv(inp / "capacity_plans.csv")
        period = pd.to_numeric(plans["period"], errors="raise").astype(int)
        tech = plans["gen_tech"].astype(str)
        future = plans[tech.eq("Hydro_Pumped") & period.gt(2023)]
        anchor = plans[tech.eq("Hydro_Pumped") & period.eq(2023)]
        gen = pd.read_csv(inp / "gen_info.csv")
        ph_cap = pd.to_numeric(
            gen.loc[gen["gen_tech"].astype(str).eq("Hydro_Pumped"), "gen_capacity_limit_mw"],
            errors="raise",
        ).sum()
        pred = pd.read_csv(inp / "gen_build_predetermined.csv")
        pred_sum = pd.to_numeric(
            pred.loc[pred["GENERATION_PROJECT"].astype(str).str.endswith("-Hydro_Pumped"), "build_gen_predetermined"],
            errors="raise",
        ).sum()
        mutation = json.loads((CASES / sc / "audits" / "V17_SCENARIO_MUTATION_AUDIT.json").read_text(encoding="utf-8"))
        add(rows, f"{sc}:no_future_pumped_hydro_policy_floor", future.empty, {"remaining_rows": len(future)})
        add(rows, f"{sc}:historical_anchor_retained", len(anchor) > 0, {"rows": len(anchor), "sum_mw": float(anchor.planned_capacity_mw.sum())})
        add(rows, f"{sc}:capacity_ceiling_equals_predetermined_stock", abs(float(ph_cap) - float(pred_sum)) <= 1e-4, {"ceiling_mw": float(ph_cap), "predetermined_mw": float(pred_sum)})
        add(rows, f"{sc}:mutation_audit_pass", bool(mutation.get("all_pre_solve_checks_pass")), mutation.get("pre_solve_checks"))

    batch = (ROOT / "tools" / "run_official_batch.py").read_text(encoding="utf-8")
    model = (ROOT / "base_model_v39" / "cheer_power_storage_v1.jl").read_text(encoding="utf-8")
    add(rows, "hard_scenario_set_exact", all(x in batch for x in HARD) and "HARD_LP_SCENARIOS" in batch, HARD)
    add(rows, "standard_v17_routes_retained", all(x in batch for x in ["scaled_barrier", "deterministic_concurrent", "dual_simplex"]), "standard route tree")
    add(rows, "hard_routes_isolated", all(x in batch and x in model for x in ["hard_deterministic_concurrent_simplex", "hard_primal_simplex", "hard_homogeneous_barrier"]), "three hard profiles")
    add(rows, "no_cleanup_in_official_fallback", "cleanup_fallbacks" not in batch, "stage 2 remains diagnostic-only")

    all_pass = all(r["pass"] for r in rows)
    payload = {"version": "V17T1", "checks": len(rows), "passed": sum(r["pass"] for r in rows), "all_pass": all_pass, "checks_detail": rows}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ["version", "checks", "passed", "all_pass"]}, ensure_ascii=False, indent=2))
    if not all_pass:
        print(pd.DataFrame(rows)[lambda x: ~x["pass"]].to_string(index=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
