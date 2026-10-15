#!/usr/bin/env python3
"""Verify the clean-package source manifest without third-party dependencies."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "CLEAN_PACKAGE_MANIFEST_SHA256.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    if not MANIFEST.is_file():
        print(f"CLEAN PACKAGE MANIFEST: FAIL (missing {MANIFEST.name})")
        return 1
    errors: list[str] = []
    rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8-sig", newline="")))
    if not rows:
        errors.append("manifest has no file rows")
    seen: set[str] = set()
    for row in rows:
        relative = str(row.get("relative_path", "")).replace("\\", "/")
        if not relative or relative.startswith("/") or ":" in relative or ".." in Path(relative).parts:
            errors.append(f"unsafe relative path: {relative!r}")
            continue
        if relative in seen:
            errors.append(f"duplicate path: {relative}")
            continue
        seen.add(relative)
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing file: {relative}")
            continue
        expected_size = int(row.get("size_bytes", "-1"))
        if path.stat().st_size != expected_size:
            errors.append(f"size mismatch: {relative}")
        if sha256(path) != str(row.get("sha256", "")).upper():
            errors.append(f"sha256 mismatch: {relative}")
    print(f"CLEAN PACKAGE MANIFEST: {'PASS' if not errors else 'FAIL'}")
    print(f"files_verified={len(rows)}")
    for error in errors:
        print(error)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
