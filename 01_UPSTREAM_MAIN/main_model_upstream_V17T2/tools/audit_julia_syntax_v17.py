#!/usr/bin/env python3
"""V17 Julia lexical, scope-legality, and solver-architecture audit.

This intentionally checks Julia declarations that are only legal at top level.  It
would have rejected the V15R1 local `const` before publication.
"""
from __future__ import annotations
from pathlib import Path
import json, re

ROOT = Path(__file__).resolve().parents[1]
AUD = ROOT / "audits"
AUD.mkdir(exist_ok=True)
MODEL = ROOT / "base_model_v39" / "cheer_power_storage_v1.jl"
RUNNER = ROOT / "storage_runner" / "run_storage_one_solver_task.jl"
RUNTIME = ROOT / "storage_runner" / "check_v17_runtime.jl"
SOURCE_LOAD = ROOT / "storage_runner" / "check_v17_source_load.jl"
FILES = sorted(ROOT.rglob("*.jl"))


def lexical(path: Path) -> tuple[bool, str]:
    text = path.read_text(encoding="utf-8")
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    opens = set(pairs.values())
    mode = "code"
    block_comment_depth = 0
    escaped = False
    i = 0
    line = 1
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
        if mode == "block_comment":
            if text.startswith("#=", i):
                block_comment_depth += 1
                i += 2
                continue
            if text.startswith("=#", i):
                block_comment_depth -= 1
                i += 2
                if block_comment_depth == 0:
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
            end_char = {"string": '"', "char": "'", "cmd": "`"}[mode]
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == end_char:
                mode = "code"
            i += 1
            continue
        if text.startswith("#=", i):
            mode = "block_comment"
            block_comment_depth = 1
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
                return False, f"delimiter mismatch {c!r} at line {line}"
            stack.pop()
        i += 1
    ok = mode == "code" and not stack
    return ok, f"mode={mode}, unclosed_delimiters={stack[-5:]}"


def sanitize(text: str) -> str:
    """Replace comments and literals with spaces while preserving newlines."""
    out = list(text)
    mode = "code"
    block_depth = 0
    escaped = False
    i = 0
    while i < len(text):
        c = text[i]
        tri = text[i:i + 3]
        if mode == "comment":
            if c == "\n":
                mode = "code"
            else:
                out[i] = " "
            i += 1
            continue
        if mode == "block":
            if text.startswith("#=", i):
                out[i:i + 2] = [" ", " "]
                block_depth += 1
                i += 2
                continue
            if text.startswith("=#", i):
                out[i:i + 2] = [" ", " "]
                block_depth -= 1
                i += 2
                if block_depth == 0:
                    mode = "code"
                continue
            if c != "\n":
                out[i] = " "
            i += 1
            continue
        if mode == "triple":
            if tri == '\"\"\"':
                out[i:i + 3] = [" ", " ", " "]
                mode = "code"
                i += 3
                continue
            if c != "\n":
                out[i] = " "
            i += 1
            continue
        if mode in {"string", "char", "cmd"}:
            end_char = {"string": '"', "char": "'", "cmd": "`"}[mode]
            if c != "\n":
                out[i] = " "
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == end_char:
                mode = "code"
            i += 1
            continue
        if text.startswith("#=", i):
            out[i:i + 2] = [" ", " "]
            mode = "block"
            block_depth = 1
            i += 2
            continue
        if c == "#":
            out[i] = " "
            mode = "comment"
            i += 1
            continue
        if tri == '\"\"\"':
            out[i:i + 3] = [" ", " ", " "]
            mode = "triple"
            i += 3
            continue
        if c == '"':
            out[i] = " "
            mode = "string"
            i += 1
            continue
        if c == "'":
            out[i] = " "
            mode = "char"
            i += 1
            continue
        if c == "`":
            out[i] = " "
            mode = "cmd"
            i += 1
            continue
        i += 1
    return "".join(out)


def illegal_local_top_level_declarations(path: Path) -> list[dict[str, object]]:
    """Find top-level-only Julia declarations nested in a function.

    The scanner tracks block keywords only outside (), [], and {}, so `A[end]`
    and comprehension filters do not corrupt the block stack.
    """
    code = sanitize(path.read_text(encoding="utf-8"))
    token_re = re.compile(r"[A-Za-z_][A-Za-z_0-9!]*|[()\[\]{};\n]")
    tokens = [(m.group(0), code.count("\n", 0, m.start()) + 1) for m in token_re.finditer(code)]
    block_stack: list[tuple[str, int]] = []
    paren = bracket = brace = 0
    violations: list[dict[str, object]] = []
    openers = {"function", "if", "for", "while", "let", "begin", "try", "quote", "do", "struct", "macro", "module", "baremodule"}
    forbidden = {"const", "struct", "macro", "module", "baremodule", "using", "import", "export", "public"}
    i = 0
    while i < len(tokens):
        tok, line = tokens[i]
        if tok == "(": paren += 1
        elif tok == ")": paren = max(0, paren - 1)
        elif tok == "[": bracket += 1
        elif tok == "]": bracket = max(0, bracket - 1)
        elif tok == "{": brace += 1
        elif tok == "}": brace = max(0, brace - 1)
        elif paren == 0 and bracket == 0 and brace == 0:
            in_function = any(kind == "function" for kind, _ in block_stack)
            nxt = tokens[i + 1][0] if i + 1 < len(tokens) else ""
            pair_decl = (tok == "abstract" and nxt == "type") or (tok == "primitive" and nxt == "type")
            if in_function and (tok in forbidden or pair_decl):
                declaration = f"{tok} {nxt}" if pair_decl else tok
                violations.append({"file": str(path.relative_to(ROOT)), "line": line, "declaration": declaration})
            if tok == "end":
                if block_stack:
                    block_stack.pop()
            elif pair_decl:
                block_stack.append((f"{tok} type", line))
                i += 1
            elif tok in openers:
                block_stack.append((tok, line))
        i += 1
    return violations


rows: list[dict[str, object]] = []
for p in FILES:
    ok, detail = lexical(p)
    rows.append({"check": f"lexical:{p.relative_to(ROOT)}", "pass": ok, "detail": detail})

scope_violations: list[dict[str, object]] = []
for p in FILES:
    scope_violations.extend(illegal_local_top_level_declarations(p))
rows.append({
    "check": "no_top_level_only_declarations_inside_functions",
    "pass": not scope_violations,
    "detail": scope_violations,
})

model = MODEL.read_text(encoding="utf-8")
runner = RUNNER.read_text(encoding="utf-8")
runtime = RUNTIME.read_text(encoding="utf-8")
source_load = SOURCE_LOAD.read_text(encoding="utf-8")
prod = model[model.index("# JuMP invalidates solution queries"):model.index("cleanup_clock = time()")]
firstmod = min(prod.index("@constraint"), prod.index("@objective"))
lastquery = prod.rfind("value(")
rt = runtime[runtime.index("# Capture every stage-1 value"):runtime.index("optimize!(model)", runtime.index("# Capture every stage-1 value"))]
rtfirst = min(rt.index("@constraint"), rt.index("@objective"))
rtlast = rt.rfind("value(")


def add(name: str, passed: bool, detail: object) -> None:
    rows.append({"check": name, "pass": bool(passed), "detail": detail})


add("grb_error_constant_is_top_level",
    model.index("const GRB_ERROR_DATA_NOT_AVAILABLE = 10005") < model.index("function run_model"),
    "Gurobi 10005 constant precedes run_model")
add("production_source_load_probe",
    all(t in source_load for t in ["include(model_file)", "isdefined(Main, :run_model)", "V17 PRODUCTION SOURCE LOAD CHECK PASSED"]),
    "real include/lowering smoke test")
add("four_cleanup_routes", all(f'name == "{r}"' in model for r in ["sparse_face_primal_pstart", "sparse_face_concurrent_pstart", "sparse_face_barrier", "sparse_face_dual"]), "approved routes")
add("one_route_per_process", "route = cleanup_route_for_profile(cleanup_profile)" in model and "for route in" not in model[model.find("lexicographic_cleanup_attempted = true"):model.find('println("Finish to solve the model")')], "no internal cascade")
add("result_count_guards", "stage1_result_count >= 1" in model and "this_result_count >= 1" in model, "safe result reads")
add("production_queries_before_modification", lastquery >= 0 and lastquery < firstmod, "capture stage-1 values first")
add("runtime_queries_before_modification", rtlast >= 0 and rtlast < rtfirst, "runtime query discipline")
add("no_basis_or_generic_start", all(t not in model for t in ["VariableBasisStatus", "ConstraintBasisStatus", '"CrossoverBasis",', "set_start_value(", '"DStart",']), "no basis/DStart/generic API")
add("raw_pstart_present", all(t in model for t in ["GRBsetdblattrarray", "GRBsetdblattrlist", '"PStart"', "GRBreset", "Gurobi.c_column"]), "explicit C API")
add("pstart_after_modification", model.index("Enforce_Lexicographic_Economic_Cost_Band") < model.rindex("_v17_apply_raw_pstart!(mod"), "start matches modified model")
add("pstart_not_serialized", ":cleanup_raw_pstart_serialized => [false]" in model, "ephemeral only")
add("scaled_stage1", "@objective(mod, Min, ScaledEconomicObjective)" in model, "scaled objective")
add("solver_native_certificate", all(t in model for t in ["stage1_native_solver_certificate_pass", "strict_solver_native", "gurobi_barrier_optimal_status_barconvtol_no_crossover"]), "native certificate")
add("presolve_safe_zero_iteration", all(t in model for t in ["stage1_zero_iteration_optimal", "stage1_barrier_iterations_observed", "stage1_barrier_iterations >= 0.0"]), "presolve safe")
add("safe_external_diagnostics", all(t in model for t in ["_safe_solve_float(() -> objective_bound(mod))", "_safe_solve_float(() -> dual_objective_value(mod))", "stage1_dual_objective_diagnostic_only"]), "non-blocking")
add("runner_default_stage1_official", 'cleanup_profile::String="stage1_official_release"' in runner and 'cleanup_profile = get(parsed, "cleanup_profile", "stage1_official_release")' in runner, "formal default is the certified stage-1 release")
add("runtime_raw_pstart", all(t in runtime for t in ["apply_raw_pstart!", "configure_sparse_face_primal_pstart!", '"LPWarmStart", 2', '"Method", 0']), "runtime route")
add("runtime_reset", runtime.index("GRBreset") < runtime.index('"PStart"'), "discard hidden state first")
add("pstart_readback_10005_nonblocking", all(x in model for x in ["GRB_ERROR_DATA_NOT_AVAILABLE = 10005", "readback_available = false", "assignment API succeeded and cleanup solve will validate consumption"]) and all(x in runtime for x in ["GRB_ERROR_DATA_NOT_AVAILABLE = 10005", "pre-solve PStart readback is unavailable", "assignment return code is authoritative"]), "Gurobi 10.0.1 readback is diagnostic only")
add("runtime_barrier_probe", all(t in runtime for t in ["Presolve=0 Barrier engine probe", "require_positive_barrier_iterations = true"]), "dedicated engine probe")
add("direct_mode_interval_safe", all(t in runtime for t in ["probe_weighted_sum = @expression", "@constraint(probe, probe_weighted_sum >= probe_lower)", "@constraint(probe, probe_weighted_sum <= probe_upper)"]) and not re.search(r"@constraint\(\s*probe\s*,[^\n]*<=.*<=", runtime), "native separate rows")

summary = {
    "version": "V17",
    "julia_files_scanned": len(FILES),
    "checks": len(rows),
    "passed": sum(bool(r["pass"]) for r in rows),
    "all_pass": all(bool(r["pass"]) for r in rows),
}
(AUD / "V17_JULIA_SYNTAX_AUDIT.json").write_text(json.dumps({"summary": summary, "checks": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"summary": summary, "failed": [r for r in rows if not r["pass"]]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if summary["all_pass"] else 1)
