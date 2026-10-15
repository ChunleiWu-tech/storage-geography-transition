#!/usr/bin/env python3
"""Static/additive-integrity gate for the V20 HF4 resume patch."""
from pathlib import Path
import csv
import hashlib
import json
import py_compile

ROOT = Path(__file__).resolve().parents[1]
FORMULATION = "V20HF4_equivalent_projected_legacy_allocation_v1"
FILES = [
    "base_model_v39_hf4/cheer_power_storage_hf4_projected.jl",
    "storage_runner/run_storage_one_solver_task_hf4_projected.jl",
    "tools/run_v20_hf4_layer_b16_resume.py",
    "modules/correction2033/base_model_v39_hf4/cheer_power_storage_targetyear_hf4_projected.jl",
    "modules/correction2033/storage_runner/run_future_correction_one_hf4_projected.jl",
    "modules/correction2033/tools/run_v20_hf4_fc08_resume.py",
    "RUN_V20_HF4_RESUME_REMAINING_15_1x10.bat",
    "CHECK_V20_HF4_PATCH.bat",
    "tools/check_v20_hf4_patch.py",
    "tools/check_v20_hf4_progress.py",
    "V20_HF4_README_ZH.txt",
    "V20_HF4_PATCH_FILE_MANIFEST_SHA256.csv",
]
PARENT_SHA256 = {
    "base_model_v39/cheer_power_storage_v1.jl": "9aefc85c850165b17d69d4a7a66c386c0adc1c1fac2ee622422a892008a6781a",
    "modules/correction2033/base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl": "2825377de801183dd624125d17d4f1541c70f724d48065b638026a774acd0a84",
}


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


def main() -> None:
    checks: list[dict] = []
    for rel in FILES:
        require((ROOT / rel).is_file(), f"file_exists::{rel}", checks)

    dynamic = (ROOT / FILES[0]).read_text(encoding="utf-8")
    target = (ROOT / FILES[3]).read_text(encoding="utf-8")
    for name, text in [("dynamic", dynamic), ("targetyear", target)]:
        require(FORMULATION in text, f"{name}::formulation_stamp", checks)
        require("STORAGE_ENERGY_VARIABLE_BLD_YRS" in text, f"{name}::projected_variable_index", checks)
        require("function storage_energy_build" in text, f"{name}::single_energy_accessor", checks)
        require("Legacy_Storage_National_Power_Closure" in text, f"{name}::power_closure_retained", checks)
        require("@constraint(mod, Legacy_Storage_National_Energy_Closure" not in text, f"{name}::dependent_energy_row_absent", checks)
        require("@constraint(mod, Legacy_Storage_Common_Duration" not in text, f"{name}::projected_duration_rows_absent", checks)
        require("@constraint(mod, Legacy_Storage_Zone_Deployment_Envelope" not in text, f"{name}::zone_caps_as_bounds", checks)
        require(":legacy_projected_energy_output_reconstruction" in text, f"{name}::output_reconstruction_audited", checks)

    for rel in [FILES[2], FILES[5]]:
        py_compile.compile(str(ROOT / rel), doraise=True)
        require(True, f"python_compile::{rel}", checks)

    parent_hashes = {rel: sha256(ROOT / rel) for rel in PARENT_SHA256}
    for rel, expected in PARENT_SHA256.items():
        require(parent_hashes[rel] == expected, f"hf3_parent_unchanged::{rel}", checks)

    manifest_path = ROOT / "V20_HF4_PATCH_FILE_MANIFEST_SHA256.csv"
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as fh:
        manifest = list(csv.DictReader(fh))
    require(bool(manifest), "patch_manifest_nonempty", checks)
    for row in manifest:
        rel = row["relative_path"]
        path = ROOT / rel
        require(path.is_file(), f"manifest_file_exists::{rel}", checks)
        require(sha256(path) == row["sha256"], f"manifest_sha256::{rel}", checks)
    projected_hashes = {rel: sha256(ROOT / rel) for rel in FILES if (ROOT / rel).is_file()}
    payload = {
        "status": "PASS",
        "version": "V20_HF4_EXACT_PROJECTED_RESUME_SAFE",
        "formulation": FORMULATION,
        "scope": "FC08 plus unfinished Layer-B cases; preexisting strict __main results remain authoritative and are skipped",
        "checks_passed": len(checks),
        "checks_total": len(checks),
        "parent_model_sha256": parent_hashes,
        "hf4_file_sha256": projected_hashes,
    }
    audit = ROOT / "audits" / "v20" / "V20_HF4_PATCH_STATIC_AUDIT.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
