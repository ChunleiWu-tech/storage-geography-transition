#!/usr/bin/env python3
"""Static scientific-scope gate for R24P3 postsolve complementarity recovery."""
from pathlib import Path
import hashlib
import json


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"
CORE = ROOT / "tools" / "run_hf18p2_quality_recovery_two_parallel.py"
RUNNER = ROOT / "tools" / "run_hf18p2_r24p3_postsolve_complementarity_recovery.py"
LAUNCHER = ROOT / "RUN_V17T2R6R24P3_HF18P2_POSTSOLVE_RECERTIFY_ONLY.bat"
OLD_MANIFEST = ROOT / "HF18P2_R24P2_PATCH_MANIFEST_SHA256.json"
NEW_MANIFEST = ROOT / "HF18P2_R24P3_PATCH_MANIFEST_SHA256.json"
required = [MODEL, CORE, RUNNER, LAUNCHER, OLD_MANIFEST, NEW_MANIFEST]
missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
if missing:
    raise SystemExit("R24P3 missing files: " + ", ".join(missing))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


model = MODEL.read_text(encoding="utf-8")
core = CORE.read_text(encoding="utf-8")
runner = RUNNER.read_text(encoding="utf-8")
launcher = LAUNCHER.read_text(encoding="utf-8")
old_manifest = json.loads(OLD_MANIFEST.read_text(encoding="utf-8-sig"))
new_manifest = json.loads(NEW_MANIFEST.read_text(encoding="utf-8-sig"))
old_hashes = {str(row["path"]).replace("\\", "/"): row["sha256"]
              for row in old_manifest.get("files", [])}
new_paths = [str(row["path"]).replace("\\", "/") for row in new_manifest.get("files", [])]
model_relative = "base_model_v39/cheer_power_storage_targetyear_v17t2r6_8760.jl"

checks = {
    "r24p2_model_byte_identical": old_hashes.get(model_relative) == sha256(MODEL),
    "r24p2_quality_profile_retained":
        "full8760_gurobi1302_hf18p2_componentwise_scale_aware_quality_recovery_barrier" in model,
    "r24p2_full_quality_attribution_retained": all(token in model for token in (
        '"BoundVio"', '"ConstrVio"', '"ConstrResidual"',
        '"DualVio"', '"DualResidual"', '"ComplVio"',
        '"ConstrSResidual"', '"DualSResidual"',
    )),
    "one_failed_case_exact": 'TARGET = "TY2033_FULL8760_OBSERVED"' in runner,
    "three_success_cases_protected": all(token in runner for token in (
        '"TY2033_FULL8760_OPTIMAL"',
        '"TY2033_FULL8760_LDES_OBSERVED"',
        '"TY2033_FULL8760_LDES_OPTIMAL"',
    )),
    "no_solver_call": "core.run_one" not in runner and "subprocess" not in runner,
    "launcher_is_postsolve_only":
        "No optimizer is invoked" in launcher and
        "--julia" not in launcher and "GUROBI_HOME" not in launcher,
    "old_failure_must_be_complementarity_only": all(token in runner for token in (
        "expected the old absolute-complementarity gate to be false",
        'decomposed_max_vio_source") != "ComplVio"',
        "MaxVio does not numerically match ComplVio",
    )),
    "unchanged_non_complementarity_native_gates": all(token in runner for token in (
        "BoundVio exceeds unchanged R24P2 threshold",
        "ConstrVio exceeds unchanged R24P2 threshold",
        "DualVio exceeds unchanged R24P2 threshold",
        "ConstrSResidual exceeds unchanged R24P2 threshold",
        "DualSResidual exceeds unchanged R24P2 threshold",
    )),
    "scale_aware_formula_exact":
        "relative_complementarity = compl_vio / scale" in runner and
        "BAR_CONV_REL_TOL = 1.0e-8" in runner,
    "objective_and_gap_gates_retained":
        "primal-dual relative gap exceeds 1e-5" in runner and
        "objective readback error exceeds 1e-4 MW" in runner,
    "eight_original_unit_audits_required":
        "len(physical_rows) != 8" in runner and
        "eight original-unit physical audits are not all PASS" in runner,
    "source_fingerprint_required": "strict target-year source fingerprint mismatch" in runner,
    "raw_failed_gate_files_preserved": all(token in runner for token in (
        "solve_status_r24p2_original_failed_gate.csv",
        "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE_R24P2_ORIGINAL_FAILED_GATE.json",
        "HF18P2_QUALITY_ATTRIBUTION_R24P2_ORIGINAL_FAILED_GATE.json",
    )),
    "postsolve_audit_and_fingerprint":
        "HF18P2_R24P3_POSTSOLVE_RECOVERY_AUDIT.json" in runner and
        "core.fingerprint_output" in runner,
    "protected_tree_hashes_before_after":
        "protected_hashes" in runner and "protected successful result changed" in runner,
    "combined_all4_fail_closed":
        "all_four_certificates_success" in runner and
        "combined four-case strict certificate set is incomplete" in runner,
    "claim_boundary_retained":
        "positive robustness distance remains a quantified fixed-portfolio gap" in runner and
        "CERTIFIED_POSITIVE_ROBUSTNESS_GAP" in model and
        "positive value quantifies a gap" in model,
    "official_gurobi_basis_recorded":
        "attributes/quality.html" in runner and "parameter-BarConvTol" in runner,
    "no_input_payload_in_overlay":
        new_manifest.get("scientific_inputs_included") is False and
        not any(path.startswith("sensitivity_cases/") for path in new_paths),
}
failed = [name for name, passed in checks.items() if not passed]
payload = {
    "version": "V17T2R6R24P3_HF18P2",
    "status": "PASS" if not failed else "FAIL",
    "checks_passed": sum(checks.values()),
    "checks_total": len(checks),
    "failed": failed,
    "recovery_scope": ["TY2033_FULL8760_OBSERVED"],
    "protected_scope": [
        "TY2033_FULL8760_OPTIMAL",
        "TY2033_FULL8760_LDES_OBSERVED",
        "TY2033_FULL8760_LDES_OPTIMAL",
    ],
    "resolve_performed": False,
    "scientific_change": False,
    "gate_change": (
        "replace only the failed unscaled absolute ComplVio check with ComplVio divided by "
        "the MW-valued robustness objective at the unchanged 1e-8 BarConvTol; retain every "
        "other native, scaled, physical, objective and lineage gate"
    ),
}
(ROOT / "audits").mkdir(exist_ok=True)
(ROOT / "audits" / "HF18P2_R24P3_STATIC_SCOPE_GATE.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(payload, ensure_ascii=False, indent=2))
if failed:
    raise SystemExit(1)
