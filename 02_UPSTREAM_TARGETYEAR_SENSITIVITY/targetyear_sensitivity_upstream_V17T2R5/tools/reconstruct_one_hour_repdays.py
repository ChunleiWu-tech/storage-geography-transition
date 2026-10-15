#!/usr/bin/env python3
"""Reconstruct bounded one-hour representative days from audited four-hour inputs.

Every four-hour load and capacity-factor value is treated as a block mean. A
centered within-block slope is added and automatically shrunk to retain physical
bounds. The four reconstructed hourly values have exactly the original mean.
This is a temporal-discretization sensitivity, not an observed 8760-hour trace.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json

import numpy as np
import pandas as pd

OFFSETS = np.array([-1.5, -0.5, 0.5, 1.5], dtype=float)
TOL = 1e-10


def _bounded_values(mean: float, slope: float, lower: float, upper: float | None) -> np.ndarray:
    delta = slope * OFFSETS
    alpha = 1.0
    neg = delta < 0
    if neg.any():
        alpha = min(alpha, float(np.min((mean - lower) / (-delta[neg]))))
    if upper is not None:
        pos = delta > 0
        if pos.any():
            alpha = min(alpha, float(np.min((upper - mean) / delta[pos])))
    alpha = max(0.0, min(1.0, alpha))
    values = mean + alpha * delta
    # Remove floating-point drift while preserving the exact block mean.
    values += mean - float(values.mean())
    values[np.abs(values) < 1e-14] = 0.0
    if upper is not None:
        values[np.abs(values - upper) < 1e-14] = upper
    if values.min() < lower - TOL or (upper is not None and values.max() > upper + TOL):
        raise ValueError("Bounded hourly reconstruction violated physical limits")
    return values


def _mapping(tp: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    map_rows = []
    for ts, group in tp.groupby("timeseries", sort=False):
        work = group.copy()
        work["_dt"] = pd.to_datetime(work["timestamp"], format="%Y-%m-%d_%H:%M")
        work = work.sort_values("_dt")
        if len(work) != 6:
            raise ValueError(f"Timeseries {ts} has {len(work)} four-hour blocks, expected 6")
        for _, old in work.iterrows():
            start = old["_dt"]
            new_ids = []
            for hour in range(4):
                stamp = start + pd.Timedelta(hours=hour)
                new_id = f"{str(ts)}.{stamp.hour:02d}"
                new_ids.append(new_id)
                rows.append({"timepoint_id": new_id,
                             "timestamp": stamp.strftime("%Y-%m-%d_%H:%M"),
                             "timeseries": ts})
            map_rows.append({"old_timepoint_id": str(old["timepoint_id"]), "timeseries": ts,
                             "new_tp_0": new_ids[0], "new_tp_1": new_ids[1],
                             "new_tp_2": new_ids[2], "new_tp_3": new_ids[3]})
    new_tp = pd.DataFrame(rows)
    mapping = pd.DataFrame(map_rows)
    if new_tp["timepoint_id"].duplicated().any() or len(new_tp) != 288:
        raise ValueError("Hourly timepoint IDs are not 288 unique values")
    return new_tp, mapping


def _expand_table(path: Path, id_col: str, entity_col: str, value_col: str,
                  tp_meta: pd.DataFrame, mapping: pd.DataFrame,
                  lower: float, upper: float | None) -> dict:
    src = pd.read_csv(path)
    src[id_col] = src[id_col].astype(str)
    meta = tp_meta[["timepoint_id", "timeseries", "timestamp"]].rename(columns={"timepoint_id": id_col})
    work = src.merge(meta, on=id_col, how="left", validate="many_to_one")
    if work["timeseries"].isna().any():
        raise ValueError(f"{path.name} contains timepoints absent from timepoints.csv")
    work["_dt"] = pd.to_datetime(work["timestamp"], format="%Y-%m-%d_%H:%M")
    map_index = mapping.set_index("old_timepoint_id")
    out = []
    max_mean_residual = 0.0
    nonflat_blocks = 0
    block_count = 0
    for (_, _), grp in work.groupby([entity_col, "timeseries"], sort=False):
        grp = grp.sort_values("_dt")
        means = pd.to_numeric(grp[value_col], errors="raise").to_numpy(dtype=float)
        if len(means) != 6:
            raise ValueError(f"{path.name} group does not contain six four-hour blocks")
        if np.min(means) < lower - TOL or (upper is not None and np.max(means) > upper + TOL):
            raise ValueError(f"{path.name} source values violate physical bounds")
        slopes = (np.roll(means, -1) - np.roll(means, 1)) / 8.0
        for old_id, mean, slope in zip(grp[id_col].astype(str), means, slopes):
            vals = _bounded_values(float(mean), float(slope), lower, upper)
            ids = map_index.loc[old_id, ["new_tp_0", "new_tp_1", "new_tp_2", "new_tp_3"]].tolist()
            nonflat_blocks += int(float(np.ptp(vals)) > 1e-12)
            block_count += 1
            max_mean_residual = max(max_mean_residual, abs(float(vals.mean()) - float(mean)))
            for new_id, value in zip(ids, vals):
                out.append({entity_col: grp[entity_col].iloc[0], id_col: new_id, value_col: float(value)})
    result = pd.DataFrame(out)
    result.to_csv(path, index=False)
    return {"source_rows": int(len(src)), "hourly_rows": int(len(result)),
            "four_hour_block_count": block_count, "nonflat_block_count": nonflat_blocks,
            "nonflat_block_share": nonflat_blocks / block_count if block_count else 0.0,
            "maximum_block_mean_residual": max_mean_residual,
            "minimum": float(result[value_col].min()), "maximum": float(result[value_col].max())}


def reconstruct(case_dir: str | Path) -> dict:
    case_dir = Path(case_dir)
    inp = case_dir / "inputs"
    tp_path = inp / "timepoints.csv"
    ts_path = inp / "timeseries.csv"
    tp = pd.read_csv(tp_path)
    ts = pd.read_csv(ts_path)
    if len(tp) != 72 or len(ts) != 12:
        raise ValueError("One-hour reconstruction requires a pruned 12-day, 72-timepoint four-hour case")
    if not pd.to_numeric(ts["ts_duration_of_tp"], errors="raise").eq(4).all():
        raise ValueError("Source timeseries are not uniformly four-hour")
    new_tp, mapping = _mapping(tp)

    file_audits = {}
    for filename in ["loads.csv", "loads_new.csv"]:
        path = inp / filename
        if path.exists():
            file_audits[filename] = _expand_table(
                path, "TIMEPOINT", "load_zone", "zone_demand_mw", tp, mapping, 0.0, None)
    file_audits["variable_capacity_factors.csv"] = _expand_table(
        inp / "variable_capacity_factors.csv", "timepoint", "GENERATION_PROJECT",
        "gen_max_capacity_factor", tp, mapping, 0.0, 1.0)

    ts["ts_duration_of_tp"] = 1
    ts["ts_num_tps"] = 24
    ts.to_csv(ts_path, index=False)
    new_tp.to_csv(tp_path, index=False)
    mapping.to_csv(case_dir / "audits" / "one_hour_timepoint_mapping.csv", index=False)

    report = {
        "status": "PASS",
        "version": "ENERGY_PRESERVING_BOUNDED_REPDAY_1H_V1",
        "source": "the current publication-calibrated four-hour case inputs",
        "observed_hourly_data_used": False,
        "full_8760_claim_supported": False,
        "claim_scope": "representative-day temporal-discretization sensitivity only",
        "method": "centered periodic within-block slope, shrunk to physical bounds; exact four-hour block-mean preservation",
        "timeseries_count": int(len(ts)),
        "timepoint_count": int(len(new_tp)),
        "timepoint_duration_h": 1,
        "timepoints_per_representative_day": 24,
        "files": file_audits,
    }
    if any(v["maximum_block_mean_residual"] > TOL for v in file_audits.values()):
        raise ValueError("One-hour reconstruction failed exact four-hour block-mean preservation")
    audits = case_dir / "audits"
    audits.mkdir(exist_ok=True)
    (audits / "one_hour_reconstruction_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    args = ap.parse_args()
    print(json.dumps(reconstruct(args.case_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
