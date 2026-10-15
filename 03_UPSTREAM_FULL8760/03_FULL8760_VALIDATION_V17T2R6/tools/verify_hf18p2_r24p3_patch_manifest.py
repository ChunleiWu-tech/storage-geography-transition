#!/usr/bin/env python3
"""Verify every file listed in the immutable R24P3 overlay manifest."""
from pathlib import Path
import hashlib
import json


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "HF18P2_R24P3_PATCH_MANIFEST_SHA256.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


payload = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
failures: list[str] = []
seen: set[str] = set()
for record in payload.get("files", []):
    relative = str(record["path"]).replace("\\", "/")
    if relative in seen:
        failures.append(f"duplicate manifest path: {relative}")
        continue
    seen.add(relative)
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        failures.append(f"path escaped package root: {path}")
        continue
    if not path.is_file():
        failures.append(f"missing: {relative}")
        continue
    if path.stat().st_size != int(record["size_bytes"]):
        failures.append(f"size mismatch: {relative}")
    if sha256(path) != record["sha256"]:
        failures.append(f"SHA256 mismatch: {relative}")
print(json.dumps({
    "version": payload.get("version"),
    "status": "PASS" if not failures else "FAIL",
    "verified_files": len(payload.get("files", [])),
    "failures": failures,
}, ensure_ascii=False, indent=2))
if failures:
    raise SystemExit(1)

