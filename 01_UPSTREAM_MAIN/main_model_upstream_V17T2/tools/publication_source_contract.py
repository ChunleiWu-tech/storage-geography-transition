#!/usr/bin/env python3
"""Single source of truth for the publication data contract.

This module intentionally reads the immutable source fingerprint instead of
replicating national totals or file hashes across validators and launchers.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT_PATH = ROOT / "audits" / "PUBLICATION_SOURCE_FINGERPRINT.json"
DATA_VERSION = "NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2"


def sha256(path: str | Path) -> str:
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_fingerprint() -> dict[str, Any]:
    if not FINGERPRINT_PATH.is_file():
        raise FileNotFoundError(
            f"Missing {FINGERPRINT_PATH}. Run tools/build_publication_vre_cf.py first."
        )
    payload = json.loads(FINGERPRINT_PATH.read_text(encoding="utf-8"))
    if payload.get("data_version") != DATA_VERSION:
        raise ValueError(
            f"Publication data version mismatch: {payload.get('data_version')} != {DATA_VERSION}"
        )
    return payload


def expected_storage_power_mw() -> float:
    return float(load_fingerprint()["storage_stock"]["national_power_mw"])


def expected_storage_energy_mwh() -> float:
    return float(load_fingerprint()["storage_stock"]["national_energy_mwh"])


def source_fingerprint_sha256() -> str:
    return sha256(FINGERPRINT_PATH)
