# V17T2R6R9-HF4P2: scope-safe continuation and remaining-three 3x15 launcher

## Defect corrected

HF4 continuation functions are defined in a separately included Julia file.
They previously referenced four status helpers that were local to `run_model`,
which caused `UndefVarError: _safe_result_count not defined` after an otherwise
solver-certified seed solve.  HF4P2 defines private, read-only equivalents in
the included file and updates only the helper calls.  No solver outcome is
promoted unless every existing strict gate passes.

## Scientific invariance

No prepared input, scenario metadata, model constraint, coefficient, RHS,
final target bound, final economic objective, chronology rule, or tolerance is
changed.  HF4 still temporarily fixes the declared 32 observed coordinates and
temporarily supports them with a dual-derived objective only within its existing
continuation procedure; it restores the exact target bounds and objective before
the sole publishable final solve, as independently gated by the model.

## Operation

`RUN_V17T2R6R9_HF4P2_8760_REMAINING_3X15.bat` launches only:

- `TY2033_FULL8760_OPTIMAL` via HF4 exact continuation;
- `TY2033_FULL8760_LDES_OBSERVED` via the unchanged HF3 route; and
- `TY2033_FULL8760_LDES_OPTIMAL` via HF4 exact continuation.

The launcher runs at most three distinct cases concurrently, with exactly 15
Gurobi threads per case.  It never cleans outputs or force-reruns; existing
strictly promoted results are validated and retained.  Per-scenario leases
prevent duplicate execution if an older coordinator is still running.
