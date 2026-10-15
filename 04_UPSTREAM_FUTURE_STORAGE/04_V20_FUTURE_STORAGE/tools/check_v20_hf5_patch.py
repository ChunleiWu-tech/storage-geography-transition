#!/usr/bin/env python3
"""Static, equivalence, source-integrity, and resume-safety gate for V20-HF5."""
from pathlib import Path
import csv
import hashlib
import json
import py_compile
import re

ROOT = Path(__file__).resolve().parents[1]
FORMULATION = "V20HF5_equivalent_reduced_formulation_v1"
REDUCTION = "V20HF5_equivalent_hourly_coordinate_projection_v1"
FILES = [
    "base_model_v39_hf4/cheer_power_storage_hf4_projected.jl",
    "storage_runner/run_storage_one_solver_task_hf4_projected.jl",
    "tools/run_v20_hf4_layer_b16_resume.py",
    "modules/correction2033/base_model_v39_hf4/cheer_power_storage_targetyear_hf4_projected.jl",
    "modules/correction2033/storage_runner/run_future_correction_one_hf4_projected.jl",
    "modules/correction2033/tools/run_v20_hf4_fc08_resume.py",
    "RUN_V20_HF5_RESUME_REQUIRED_26_1x10.bat",
    "CHECK_V20_HF5_PATCH.bat",
    "tools/check_v20_hf5_patch.py",
    "tools/check_v20_hf5_progress.py",
    "V20_HF5_ROOT_CAUSE_TECHNICAL_AUDIT.md",
    "V20_HF5_PATCH_FILE_MANIFEST_SHA256.csv",
]
PARENT_SHA256 = {
    "base_model_v39/cheer_power_storage_v1.jl": "9aefc85c850165b17d69d4a7a66c386c0adc1c1fac2ee622422a892008a6781a",
    "modules/correction2033/base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl": "2825377de801183dd624125d17d4f1541c70f724d48065b638026a774acd0a84",
}
TOLERANCE_CONSTANTS = [
    "STRICT_ABSOLUTE_PRIMAL_FEASIBILITY_TOL",
    "STRICT_OBJECTIVE_SCALED_PRIMAL_FEASIBILITY_TOL",
    "SOLVER_FEASIBILITY_TOL", "SOLVER_OPTIMALITY_TOL", "SOLVER_BAR_CONV_TOL",
    "POWER_BALANCE_ABS_TOL_MW", "POWER_BALANCE_REL_TOL",
    "PHYSICAL_AUDIT_POWER_ABS_TOL_MW", "PHYSICAL_AUDIT_ENERGY_ABS_TOL_MWH",
    "PHYSICAL_AUDIT_FUEL_ABS_TOL_MMBTU", "PHYSICAL_AUDIT_REL_TOL",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require(condition: bool, message: str, checks: list[dict]) -> None:
    checks.append({"check": message, "passed": bool(condition)})
    if not condition:
        raise SystemExit(json.dumps({"status": "FAIL", "failed": message, "checks": checks}, ensure_ascii=False, indent=2))


def constant_value(text: str, name: str) -> str:
    match = re.search(rf"(?m)^const\s+{re.escape(name)}\s*=\s*([^\r\n#]+)", text)
    return match.group(1).strip() if match else ""


def input_counts(case_dir: Path) -> dict[str, int]:
    inputs = case_dir / "inputs"
    with (inputs / "gen_info.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        gens = list(csv.DictReader(fh))
    with (inputs / "ccs_install_costs.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        ccs = {r["GENERATION_PROJECT"] for r in csv.DictReader(fh)}
    with (inputs / "timepoints.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        timepoints = sum(1 for _ in csv.DictReader(fh))
    def num(v: str) -> float:
        return float("0" if str(v).strip() in {"", "."} else v)
    active = sum(1 for g in gens if num(g["gen_startup_om"]) != 0 or num(g["gen_min_uptime"]) > 0 or num(g["gen_min_downtime"]) > 0)
    omitted = 2 * ((len(gens) - len(ccs)) + (len(gens) - active)) * timepoints
    return {"generators": len(gens), "timepoints": timepoints, "ccs": len(ccs), "startup_active": active, "omitted": omitted}


def main() -> None:
    checks: list[dict] = []
    for rel in FILES:
        require((ROOT / rel).is_file(), f"file_exists::{rel}", checks)

    parent_hashes = {rel: sha256(ROOT / rel) for rel in PARENT_SHA256}
    for rel, expected in PARENT_SHA256.items():
        require(parent_hashes[rel] == expected, f"frozen_parent_unchanged::{rel}", checks)

    model_pairs = [
        ("dynamic", ROOT / "base_model_v39/cheer_power_storage_v1.jl", ROOT / FILES[0]),
        ("targetyear", ROOT / "modules/correction2033/base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl", ROOT / FILES[3]),
    ]
    for name, parent_path, reduced_path in model_pairs:
        parent = parent_path.read_text(encoding="utf-8")
        reduced = reduced_path.read_text(encoding="utf-8")
        require(FORMULATION in reduced, f"{name}::formulation_stamp", checks)
        require(REDUCTION in reduced, f"{name}::reduction_stamp", checks)
        require("CCS_GEN_TPS" in reduced and "STARTUP_SHUTDOWN_GEN_TPS" in reduced, f"{name}::reduced_indices", checks)
        require("@variable(mod, DispatchGenCCS[(g, t) in GEN_TPS]" not in reduced, f"{name}::full_nonccs_dispatch_absent", checks)
        require("@variable(mod, CommitGenCCS[(g, t) in GEN_TPS]" not in reduced, f"{name}::full_nonccs_commit_absent", checks)
        require("@variable(mod, StartupGenCapacity[(g, t) in GEN_TPS]" not in reduced, f"{name}::neutral_startup_absent", checks)
        require("dispatch_gen_ccs_value_or_zero" in reduced and "startup_gen_capacity_value_or_zero" in reduced, f"{name}::full_schema_reconstruction", checks)
        require("function storage_energy_build" in reduced, f"{name}::legacy_energy_accessor", checks)
        for constant in TOLERANCE_CONSTANTS:
            require(constant_value(parent, constant) == constant_value(reduced, constant) != "", f"{name}::tolerance_unchanged::{constant}", checks)

    fc08 = input_counts(ROOT / "modules/correction2033/future_correction_cases/FC08_EXPANDED_OPTIMAL")
    require(fc08 == {"generators": 625, "timepoints": 72, "ccs": 96, "startup_active": 96, "omitted": 152352}, "fc08::exact_projection_count", checks)
    layer_b_counts = [input_counts(p) for p in sorted((ROOT / "storage_cases").glob("SL*")) if p.is_dir()]
    require(len(layer_b_counts) == 16, "layer_b::sixteen_prepared_cases", checks)
    require(all(x["omitted"] == 872928 for x in layer_b_counts), "layer_b::exact_projection_count_each", checks)

    for rel in [FILES[2], FILES[5], FILES[8], FILES[9]]:
        py_compile.compile(str(ROOT / rel), doraise=True)
        require(True, f"python_compile::{rel}", checks)

    a_runner = (ROOT / FILES[5]).read_text(encoding="utf-8")
    b_runner = (ROOT / FILES[2]).read_text(encoding="utf-8")
    for name, runner in [("layer_a", a_runner), ("layer_b", b_runner)]:
        require('"216000"' in runner, f"{name}::continuous_60h_budget", checks)
        require("scaled_barrier" in runner, f"{name}::barrier_route", checks)
        require("dual_simplex" not in runner, f"{name}::no_progress_discarding_dual_restart", checks)

    launcher = (ROOT / "RUN_V20_HF5_RESUME_REQUIRED_26_1x10.bat").read_text(encoding="utf-8")
    require("V20_HF5_ALLOW_OTHER_JULIA" in launcher, "launcher::explicit_parallel_julia_override", checks)

    manifest_path = ROOT / "V20_HF5_PATCH_FILE_MANIFEST_SHA256.csv"
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as fh:
        manifest = list(csv.DictReader(fh))
    require(bool(manifest), "patch_manifest_nonempty", checks)
    for row in manifest:
        rel = row["relative_path"]
        path = ROOT / rel
        require(path.is_file(), f"manifest_file_exists::{rel}", checks)
        require(sha256(path) == row["sha256"], f"manifest_sha256::{rel}", checks)

    payload = {
        "status": "PASS",
        "version": "V20_HF5_EQUIVALENT_REDUCED_RESUME_SAFE",
        "formulation": FORMULATION,
        "algebraic_reduction": REDUCTION,
        "scope": "all unfinished Layer-A/B cases; strict existing __main outputs remain authoritative and are skipped",
        "scientific_change": False,
        "solver_certified": False,
        "solver_note": "Static and algebraic audit only; publication still requires local Julia/Gurobi OPTIMAL plus all existing release gates.",
        "fc08_exact_counts": fc08,
        "layer_b_omitted_hourly_columns_each": 872928,
        "checks_passed": len(checks), "checks_total": len(checks),
        "parent_model_sha256": parent_hashes,
    }
    audit = ROOT / "audits" / "v20" / "V20_HF5_PATCH_STATIC_AUDIT.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
