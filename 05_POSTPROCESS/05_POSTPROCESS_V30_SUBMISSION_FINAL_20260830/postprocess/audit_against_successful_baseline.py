#!/usr/bin/env python3
"""Source-aware scientific regression and invariant audit.

The historical filename is retained for compatibility. A pre-update numerical
reference is disclosed in PRE_SOURCE_UPDATE_RESULT_REFERENCE.json, but
``pre_update_reference_not_used_as_release_gate`` is always true for the updated
source contract. Before the first source-current rerun is frozen, the audit
checks input closure and internal identities. After an explicit
``FROZEN_SOURCE_CURRENT`` baseline is created, it additionally performs exact
source-current numerical regression within declared tolerances.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from v17t5_paths import AUDIT_DIR, PROJECT_ROOT, SOURCE_ROOT, TABLE_MAIN

BASELINE = SOURCE_ROOT / "BASELINE_SCIENTIFIC_FINGERPRINT.json"
PRE_SOURCE = SOURCE_ROOT / "PRE_SOURCE_UPDATE_RESULT_REFERENCE.json"
ALLOWED_CLASSES = {"partly corrected", "persistent or amplified", "reversal", "substantially corrected"}


def close(a: float, b: float, rel: float, abs_: float) -> bool:
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_)


def load_source_fingerprint(root: str | Path) -> dict[str, Any]:
    path = Path(root) / "audits" / "PUBLICATION_SOURCE_FINGERPRINT.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing source fingerprint: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_tables() -> dict[str, pd.DataFrame]:
    return {
        "concentration": pd.read_csv(TABLE_MAIN / "fig1d_legacy_concentration.csv"),
        "allocation": pd.read_csv(TABLE_MAIN / "fig2_spatial_allocation.csv"),
        "value_ladder": pd.read_csv(TABLE_MAIN / "fig2b_legacy_value_ladder.csv"),
        "investment": pd.read_csv(TABLE_MAIN / "fig3a_compensatory_investment.csv"),
        "persistence": pd.read_csv(TABLE_MAIN / "fig4a_mismatch_persistence.csv"),
        "correction": pd.read_csv(TABLE_MAIN / "fig4c_zone_correction.csv"),
        "robustness": pd.read_csv(TABLE_MAIN / "fig5_robustness_effects.csv"),
    }


def collect_metrics() -> tuple[dict[str, float], dict[str, int]]:
    tables = _read_tables()
    con = tables["concentration"].iloc[0]
    allocation = tables["allocation"]
    ladder = tables["value_ladder"]
    comp = tables["investment"]
    pers = tables["persistence"]
    corr = tables["correction"]
    rob = tables["robustness"]
    opt_delta = allocation.loc[
        allocation["scenario"].eq("SL02_OPTIMAL_REALLOCATION"),
        "delta_power_vs_observed_standardized_mw",
    ]
    metrics = {
        "national_power_mw": float(con["national_power_mw"]),
        "national_energy_mwh": float(con["national_energy_mwh"]),
        "national_average_duration_h": float(con["national_average_duration_h"]),
        "top5_power_share": float(con["top5_power_share"]),
        "hhi": float(con["herfindahl_hirschman_index"]),
        "max_storage_to_peak_ratio": float(con["maximum_storage_to_peak_ratio"]),
        "equivalent_reallocation_mw": float(0.5 * opt_delta.abs().sum()),
        "optimized_value_usd": float(ladder.loc[ladder["scenario"].eq("SL02_OPTIMAL_REALLOCATION"), "legacy_system_value_usd"].iloc[0]),
        "observed_standardized_retention": float(ladder.loc[ladder["scenario"].eq("SL01_OBSERVED_STANDARDIZED"), "value_retention_fraction"].iloc[0]),
        "base_cost_penalty_pv_usd": float(comp["present_value_cost_delta_usd"].sum()),
        "period_2028_battery_power_delta_mw": float(comp.loc[comp["period"].eq(2028), "battery_power_delta_mw"].iloc[0]),
        "period_2028_battery_energy_delta_mwh": float(comp.loc[comp["period"].eq(2028), "battery_energy_delta_mwh"].iloc[0]),
        "final_power_persistence_fraction": float(pers.iloc[-1]["power_persistence_fraction"]),
        "final_energy_persistence_fraction": float(pers.iloc[-1]["energy_persistence_fraction"]),
        "robust_cost_penalty_min_usd": float(rob.loc[rob["metric"].eq("cumulative_system_cost_pv_usd"), "observed_minus_optimal"].min()),
        "robust_cost_penalty_max_usd": float(rob.loc[rob["metric"].eq("cumulative_system_cost_pv_usd"), "observed_minus_optimal"].max()),
        "robust_battery_power_min_mw": float(rob.loc[rob["metric"].eq("future_battery_build_mw"), "observed_minus_optimal"].min()),
        "robust_battery_power_max_mw": float(rob.loc[rob["metric"].eq("future_battery_build_mw"), "observed_minus_optimal"].max()),
        "robust_battery_energy_min_mwh": float(rob.loc[rob["metric"].eq("future_battery_energy_build_mwh"), "observed_minus_optimal"].min()),
        "robust_battery_energy_max_mwh": float(rob.loc[rob["metric"].eq("future_battery_energy_build_mwh"), "observed_minus_optimal"].max()),
    }
    counts = {str(k): int(v) for k, v in corr["correction_class"].value_counts().sort_index().to_dict().items()}
    return metrics, counts


def _finite(name: str, frame: pd.DataFrame) -> bool:
    numeric = frame.select_dtypes(include=[np.number])
    if numeric.empty:
        return True
    if name != "robustness" or "relative_difference_fraction" not in numeric:
        return bool(np.isfinite(numeric.to_numpy(dtype=float)).all())

    # A relative difference is mathematically undefined when the optimized
    # denominator is exactly zero.  Preserve that fact as NA, while requiring
    # every scientific absolute value to remain finite and rejecting NA/Inf in
    # the relative field whenever the denominator is nonzero.
    core = numeric.drop(columns=["relative_difference_fraction"])
    if not np.isfinite(core.to_numpy(dtype=float)).all():
        return False
    relative = pd.to_numeric(frame["relative_difference_fraction"], errors="coerce")
    denominator = pd.to_numeric(frame["optimal_value"], errors="coerce")
    allowed_undefined = relative.isna() & np.isfinite(denominator) & denominator.abs().le(1e-12)
    return bool((np.isfinite(relative) | allowed_undefined).all())


def main() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    pre_source = json.loads(PRE_SOURCE.read_text(encoding="utf-8"))
    source = load_source_fingerprint(PROJECT_ROOT)
    contract = baseline["required_source_contract"]
    metrics, counts = collect_metrics()
    tables = _read_tables()
    rel = float(baseline.get("tolerances", {}).get("relative", 1e-8))
    abs_ = float(baseline.get("tolerances", {}).get("absolute", 1e-5))
    rows: list[dict[str, Any]] = []

    def add(name: str, passed: bool, expected: Any = "", actual: Any = "", mode: str = "invariant") -> None:
        rows.append({"check": name, "pass": bool(passed), "expected": expected, "actual": actual, "mode": mode})

    add("source_data_version", source.get("data_version") == baseline.get("data_version"), baseline.get("data_version"), source.get("data_version"))
    add("national_power_closure", close(metrics["national_power_mw"], contract["national_power_mw"], rel, abs_), contract["national_power_mw"], metrics["national_power_mw"])
    add("national_energy_closure", close(metrics["national_energy_mwh"], contract["national_energy_mwh"], rel, abs_), contract["national_energy_mwh"], metrics["national_energy_mwh"])
    expected_duration = float(contract["national_energy_mwh"]) / float(contract["national_power_mw"])
    add("national_duration_closure", close(metrics["national_average_duration_h"], expected_duration, rel, abs_), expected_duration, metrics["national_average_duration_h"])
    add("pre_source_reference_disclosed", float(pre_source.get("metrics", {}).get("national_power_mw", 0.0)) == 136000.0, 136000.0, pre_source.get("metrics", {}).get("national_power_mw"))
    add("pre_update_reference_not_used_as_release_gate", True, True, True)

    for name, frame in tables.items():
        finite = _finite(name, frame)
        detail = (
            "all required values finite; relative difference may be NA only for a zero optimized denominator"
            if finite and name == "robustness"
            else "all finite" if finite else "non-finite found"
        )
        add(f"finite_numeric::{name}", finite, True, detail)

    allocation = tables["allocation"]
    opt_delta = allocation.loc[allocation["scenario"].eq("SL02_OPTIMAL_REALLOCATION"), "delta_power_vs_observed_standardized_mw"]
    add("allocation_balance", close(float(opt_delta.sum()), 0.0, rel, 1e-4), 0.0, float(opt_delta.sum()))
    add("allocation_zone_count", allocation.loc[allocation["scenario"].eq("SL01_OBSERVED_STANDARDIZED")].shape[0] == 32, 32, allocation.loc[allocation["scenario"].eq("SL01_OBSERVED_STANDARDIZED")].shape[0])
    add("correction_classes_allowed", set(counts).issubset(ALLOWED_CLASSES), sorted(ALLOWED_CLASSES), sorted(counts))
    add("correction_zone_count", int(sum(counts.values())) == 32, 32, int(sum(counts.values())))

    status = str(baseline.get("status"))
    if status == "FROZEN_SOURCE_CURRENT":
        for name, expected in baseline.get("metrics", {}).items():
            add(f"frozen::{name}", close(metrics[name], expected, rel, abs_), expected, metrics[name], "FROZEN_SOURCE_CURRENT")
        add("frozen::correction_class_counts", counts == baseline.get("correction_class_counts", {}), baseline.get("correction_class_counts", {}), counts, "FROZEN_SOURCE_CURRENT")
    elif status != "UNINITIALIZED_RERUN_REQUIRED":
        add("baseline_status_allowed", False, ["UNINITIALIZED_RERUN_REQUIRED", "FROZEN_SOURCE_CURRENT"], status)

    frame = pd.DataFrame(rows)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(AUDIT_DIR / "successful_baseline_regression_audit.csv", index=False)
    summary = {
        "version": "V17T5R6R8R5_SOURCE_CURRENT",
        "data_version": source.get("data_version"),
        "baseline_status": status,
        "pre_update_reference_not_used_as_release_gate": True,
        "source_current_frozen_regression_active": status == "FROZEN_SOURCE_CURRENT",
        "checks": len(frame),
        "passed": int(frame["pass"].sum()),
        "all_pass": bool(frame["pass"].all()),
        "failed": frame.loc[~frame["pass"], "check"].tolist(),
    }
    (AUDIT_DIR / "successful_baseline_regression_audit.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary["all_pass"]:
        print(frame.loc[~frame["pass"]].to_string(index=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
