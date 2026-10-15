#!/usr/bin/env python3
"""Replace inherited machine-specific audit paths with package-relative paths."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MARKERS = (
    "audits/",
    "base_model_v39/",
    "data/",
    "docs/",
    "notebooks/",
    "sensitivity_cases/",
    "shared_source_snapshots/",
    "storage_runner/",
    "template_cases_4h/",
    "tools/",
)


def portable(value: str) -> str:
    normalized = value.replace("\\", "/")
    # Only touch absolute Windows paths. Scientific prose and version labels
    # containing directory-like text are intentionally left unchanged.
    if not re.match(r"^[A-Za-z]:/", normalized):
        return value
    lower = normalized.lower()
    matches = [(lower.rfind(marker.lower()), marker) for marker in MARKERS]
    matches = [(index, marker) for index, marker in matches if index >= 0]
    if matches:
        index, _ = max(matches, key=lambda item: item[0])
        return normalized[index:]
    return Path(normalized).name


def transform(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: transform(item) for key, item in value.items()}
    if isinstance(value, list):
        return [transform(item) for item in value]
    if isinstance(value, str):
        return portable(value)
    return value


def main() -> None:
    changed: list[str] = []
    for path in sorted(ROOT.rglob("*.json")):
        if any(part in {"sensitivity_outputs", "batch_logs", "failed_diagnostics"} for part in path.parts):
            continue
        original = json.loads(path.read_text(encoding="utf-8"))
        revised = transform(original)
        if revised != original:
            path.write_text(json.dumps(revised, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            changed.append(path.relative_to(ROOT).as_posix())
    print(json.dumps({"status": "PASS", "changed_files": changed}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
