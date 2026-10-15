#!/usr/bin/env python3
"""Lexical/static Julia audit for V17T2R5 without requiring a Julia runtime."""
from __future__ import annotations
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r5.jl",
    ROOT / "storage_runner" / "run_targetyear_one.jl",
    ROOT / "storage_runner" / "check_v17t2r5_runtime.jl",
]


def check_delimiters(path: Path) -> tuple[bool, str]:
    text = path.read_text(encoding="utf-8")
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    opens = set(pairs.values())
    mode = "code"
    block_depth = 0
    escaped = False
    line = 1
    i = 0
    while i < len(text):
        c = text[i]
        tri = text[i:i + 3]
        if c == "\n":
            line += 1
            if mode == "comment":
                mode = "code"
        if mode == "comment":
            i += 1
            continue
        if mode == "block":
            if text.startswith("#=", i):
                block_depth += 1
                i += 2
                continue
            if text.startswith("=#", i):
                block_depth -= 1
                i += 2
                if block_depth == 0:
                    mode = "code"
                continue
            i += 1
            continue
        if mode == "triple":
            if tri == '\"\"\"':
                mode = "code"
                i += 3
                continue
            i += 1
            continue
        if mode in {"string", "char", "cmd"}:
            ending = {"string": '"', "char": "'", "cmd": "`"}[mode]
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == ending:
                mode = "code"
            i += 1
            continue
        if text.startswith("#=", i):
            mode = "block"
            block_depth = 1
            i += 2
            continue
        if c == "#":
            mode = "comment"
            i += 1
            continue
        if tri == '\"\"\"':
            mode = "triple"
            i += 3
            continue
        if c == '"':
            mode = "string"
            i += 1
            continue
        if c == "'":
            mode = "char"
            i += 1
            continue
        if c == "`":
            mode = "cmd"
            i += 1
            continue
        if c in opens:
            stack.append((c, line))
        elif c in pairs:
            if not stack or stack[-1][0] != pairs[c]:
                return False, f"delimiter mismatch {c} at line {line}"
            stack.pop()
        i += 1
    if mode != "code" or stack:
        return False, f"unfinished mode={mode}; stack_tail={stack[-5:]}"
    return True, "balanced comments, literals and delimiters"


checks: list[dict[str, object]] = []
for path in FILES:
    if not path.is_file():
        checks.append({"file": str(path.relative_to(ROOT)), "pass": False, "detail": "missing"})
        continue
    ok, detail = check_delimiters(path)
    checks.append({"file": str(path.relative_to(ROOT)), "pass": ok, "detail": detail})

model_path = FILES[0]
model = model_path.read_text(encoding="utf-8") if model_path.is_file() else ""
required_model_tokens = [
    'NUMERICAL_STABILITY_VERSION = "V17T2R5_targetyear_exact_linked_reoptimization_stage1_official_release_json_safe"',
    'REPRESENTATIVE_TIMEPOINT_COUNTS_ALLOWED = (72, 288)',
    'targetyear_deterministic_concurrent',
    'targetyear_homogeneous_dual_crossover',
    'CrossoverBasis',
    'TARGET_YEAR_OPERATION_PERIOD in (2028, 2033)',
    '@variable(mod, InterdayStateOfCharge',
    'Link_Interperiod_State_Of_Charge',
    'technology_portfolio_discrete',
    'LDES_PSH_Shared_Provincial_Resource_Ceiling',
    'storage_chronology_audit.csv',
    'ldes_proxy_build.csv',
    'target_year_static_reoptimization',
    'target_year_transition_path_claim_supported',
]
for token in required_model_tokens:
    checks.append({
        "file": str(model_path.relative_to(ROOT)),
        "pass": token in model,
        "detail": f"required token: {token}",
    })

runner = FILES[1].read_text(encoding="utf-8") if FILES[1].is_file() else ""
for token in ["run_model(case_dir", "storage_chronology_mode = String(r.storage_chronology_mode)", "not full 8760 chronology"]:
    checks.append({
        "file": str(FILES[1].relative_to(ROOT)),
        "pass": token in runner,
        "detail": f"required runner token: {token}",
    })

result = {
    "version": "V17T2R5",
    "status": "PASS" if all(bool(x["pass"]) for x in checks) else "FAIL",
    "julia_runtime_used": False,
    "checks": checks,
}
out = ROOT / "audits" / "JULIA_LEXICAL_AUDIT_V17T2R5.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["status"] == "PASS" else 1)
