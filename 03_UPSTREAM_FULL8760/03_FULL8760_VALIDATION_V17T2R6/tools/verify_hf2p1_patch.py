#!/usr/bin/env python3
"""Fail closed if HF2P1 changes the frozen solve/gate prefix or patch files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl"
MARKER = b"# post-solve treat and export of results"
EXPECTED_PRE_POSTSOLVE_SHA256 = "6e692da02ecea112f6527fce0552dedb49af033b10a256ca3b9de6881d7303ea"
MANIFEST = ROOT / "HF2P1_PATCH_MANIFEST_SHA256.json"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    model = MODEL.read_bytes()
    marker_position = model.find(MARKER)
    errors: list[str] = []
    if marker_position < 0:
        errors.append("post-solve marker missing")
        prefix_sha = ""
    else:
        prefix_sha = sha256_bytes(model[:marker_position])
        if prefix_sha != EXPECTED_PRE_POSTSOLVE_SHA256:
            errors.append("pre-postsolve solve/gate prefix changed")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for item in manifest.get("files", []):
        path = ROOT / item["path"]
        if not path.is_file():
            errors.append(f"missing patch file: {item['path']}")
        elif sha256_file(path) != item["sha256"]:
            errors.append(f"patch file hash mismatch: {item['path']}")

    result = {
        "version": "V17T2R6R7_HF2P1_FULL8760",
        "status": "PASS" if not errors else "FAIL",
        "pre_postsolve_solve_and_gate_prefix_sha256": prefix_sha,
        "expected_pre_postsolve_solve_and_gate_prefix_sha256": EXPECTED_PRE_POSTSOLVE_SHA256,
        "solve_and_gate_prefix_byte_equivalent_to_hf2": prefix_sha == EXPECTED_PRE_POSTSOLVE_SHA256,
        "checked_patch_files": len(manifest.get("files", [])),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 2)


if __name__ == "__main__":
    main()
