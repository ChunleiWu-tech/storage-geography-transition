#!/usr/bin/env python3
"""Lightweight delimiter check used when Julia is unavailable on the packaging host."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    ROOT / "base_model_v39" / "cheer_power_storage_targetyear_v17t2r6_8760.jl",
    ROOT / "base_model_v39" / "full8760_hf18_fixed_portfolio_validation.jl",
    ROOT / "storage_runner" / "run_targetyear_one.jl",
    ROOT / "tools" / "check_hf18p2_gurobi1302_runtime.jl",
)
PAIRS = {"(": ")", "[": "]", "{": "}"}

for path in FILES:
    source = path.read_text(encoding="utf-8")
    stack: list[tuple[str, int]] = []
    quote: str | None = None
    escaped = False
    comment = False
    for offset, char in enumerate(source):
        if comment:
            if char == "\n":
                comment = False
            continue
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char == "#":
            comment = True
        elif char in {'"', "'"}:
            quote = char
        elif char in PAIRS:
            stack.append((char, offset))
        elif char in PAIRS.values():
            if not stack or PAIRS[stack[-1][0]] != char:
                raise SystemExit(f"{path}: mismatched {char} at byte {offset}")
            stack.pop()
    if quote is not None or stack:
        raise SystemExit(f"{path}: unclosed quote/delimiter: quote={quote} stack={stack[-5:]}")
    print(f"{path.relative_to(ROOT)}: DELIMITERS PASS")
