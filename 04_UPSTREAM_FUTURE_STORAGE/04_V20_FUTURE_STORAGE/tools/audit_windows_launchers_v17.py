#!/usr/bin/env python3
"""Audit Windows launchers for V17.

This check prevents two release-breaking regressions:
1. Python selection must not assume that Python 3.12 is installed merely
   because the Windows py launcher exists.
2. Batch files must not contain escaped control bytes such as \x08, \x0b,
   or embedded carriage returns created from Python string literals like
   "tools\\build...", "tools\\validate...", and "tools\\run...".
"""
from __future__ import annotations

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audits" / "V17_WINDOWS_LAUNCHER_AUDIT.json"

EXPECTED = {
    "V17_ENV_DEFAULTS.bat",
    "CHECK_V17_RELEASE.bat",
    "CHECK_V17_RUNTIME.bat",
    "RUN_V17_PREPARE_ONLY.bat",
    "RUN_V17_POSTPROCESS.bat",
    "RUN_V17_SL00_PRIMARY_ONLY_1x10.bat",
    "RUN_V17_SL00_CONTROLLED_1x10.bat",
    "RUN_V17_SL00_SPARSE_FACE_DIAGNOSTIC_1x10.bat",
    "RUN_V17_SPATIAL_LEGACY_CORE_1x10.bat",
    "RUN_V17_SPATIAL_LEGACY_ROBUSTNESS_1x10.bat",
    "RUN_V17_SPATIAL_LEGACY_FULL_1x10.bat",
    "RUN_V17T2_SL10_RESCUE_1x10.bat",
    "RUN_V17T2_UPSTREAM_FULL_16_1x10.bat",
    "RUN_V17T2_CLEAN_REBUILD_AND_RUN_ALL_16_1x10.bat",
    "RUN_V17T2_POSTPROCESS.bat",
}

checks: list[dict[str, object]] = []

def add(name: str, passed: bool, detail: str) -> None:
    checks.append({"check": name, "pass": bool(passed), "detail": detail})

present = {p.name for p in ROOT.glob("*.bat")}
add("expected_launcher_set", EXPECTED <= present, f"missing={sorted(EXPECTED-present)}")
add("no_obsolete_v17r2_launchers", not any("V17R2" in n for n in present), f"present={sorted(present)}")

for name in sorted(EXPECTED & present):
    path = ROOT / name
    data = path.read_bytes()
    forbidden = [(i, b) for i, b in enumerate(data) if b < 32 and b not in (9, 10, 13)]
    lone_cr = [i for i, b in enumerate(data) if b == 13 and (i + 1 >= len(data) or data[i + 1] != 10)]
    lone_lf = [i for i, b in enumerate(data) if b == 10 and (i == 0 or data[i - 1] != 13)]
    add(f"{name}:no_forbidden_control_bytes", not forbidden, f"forbidden={forbidden[:8]}")
    add(f"{name}:strict_crlf", not lone_cr and not lone_lf, f"lone_cr={lone_cr[:8]}, lone_lf={lone_lf[:8]}")
    try:
        text = data.decode("ascii")
        ascii_ok = True
    except UnicodeDecodeError as exc:
        text = data.decode("utf-8", errors="replace")
        ascii_ok = False
        decode_detail = str(exc)
    else:
        decode_detail = "ascii"
    add(f"{name}:ascii_safe", ascii_ok, decode_detail)
    if name != "V17_ENV_DEFAULTS.bat":
        add(f"{name}:calls_shared_environment", "call V17_ENV_DEFAULTS.bat" in text, "shared runtime selector")
        add(f"{name}:checks_environment_error", "if errorlevel 1 exit /b 1" in text, "abort on selector failure")

selector = (ROOT / "V17_ENV_DEFAULTS.bat").read_text(encoding="ascii")
for token in [
    "if defined V17_PYTHON",
    "call :try_python py -3.12",
    "call :try_python py -3.14",
    "call :try_python py -3",
    "call :try_python python",
    "sys.version_info >= (3,10)",
    "No working Python 3.10+ runtime was found",
]:
    add(f"python_selector:{token}", token in selector, token)
add(
    "python_selector:not_py_launcher_implies_312",
    'where py' not in selector and 'set "V17_PYTHON=py -3.12"' not in selector,
    "the selector tests each candidate instead of assuming py -3.12",
)

# Verify all explicitly referenced local scripts exist.
ref_pattern = re.compile(r'(?P<path>(?:tools|postprocess|storage_runner)\\[^"\s]+\.(?:py|jl))')
for path in sorted(ROOT.glob("*.bat")):
    text = path.read_text(encoding="ascii")
    for match in ref_pattern.finditer(text):
        rel = match.group("path").replace("\\", "/")
        add(f"reference:{path.name}:{rel}", (ROOT / rel).exists(), rel)

# The clean launcher prepares the 16 case directories before invoking the
# batch solver.  The batch call must not delete those directories again.
clean_launcher = (ROOT / "RUN_V17T2_CLEAN_REBUILD_AND_RUN_ALL_16_1x10.bat").read_text(encoding="ascii")
solve_line = next((line for line in clean_launcher.splitlines() if "run_official_batch.py" in line), "")
add(
    "clean_launcher:preserves_prepared_storage_cases",
    "--clean-previous" not in solve_line,
    solve_line,
)

summary = {
    "version": "V17",
    "checks": len(checks),
    "passed": sum(bool(x["pass"]) for x in checks),
    "all_pass": all(bool(x["pass"]) for x in checks),
    "checks_detail": checks,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: summary[k] for k in ["version", "checks", "passed", "all_pass"]}, indent=2))
if not summary["all_pass"]:
    for row in checks:
        if not row["pass"]:
            print("FAILED:", row)
    raise SystemExit(1)
