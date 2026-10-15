# V17T2R6R7-HF2P2 Full-8760 Validation Package — Equivalent Post-Solve Acceleration, Full Rerun Required

> HF2P2 status: the HF2P1 equivalent post-solve acceleration is unchanged. HF2P2 only corrects the release-manifest boundary after a clean case rebuild; see `RELEASE_NOTES_V17T2R6R7_HF2P2.md`. Immutable code, templates and source data remain SHA-256 locked, while regenerated cases remain fail-closed under chronology, source-fingerprint, pair-identity and runtime gates. Scientific inputs, model construction, objective, constraints, solver routes, result row order and publication gates are unchanged.

This package is the independent continuous-hour validation layer after the 16 main upstream cases and 8 target-year sensitivity cases. It contains exactly four 2033 static target-year capacity-and-dispatch LPs: CORE observed/optimized inherited-storage geography and LDES observed/optimized geography.

R7 retains all verified R6 runtime/solver fixes and adds operationally isolated pairwise parallel execution without changing scientific inputs or equations. HF2P1 additionally fixes a post-solve bottleneck shared by all four cases: membership tests over 832,200 storage-time keys now use an equivalent `Set`, while ordered output traversal still uses the original vectors. The package retains scaled Barrier with `Crossover=0` as the primary route (12 h), homogeneous numerically focused Barrier with `Crossover=0` as the single controlled fallback (24 h), both with `BarIterLimit=100000`; generic `string(x)` for CSV-inferred numeric TIMESERIES identifiers; explicit support for the real `yyyy-mm-dd_HH:MM` timestamp format; fail-closed chronology checks; resume-safe launchers; and a deterministic two-wave scheduler with at most two simultaneous cases and exactly 10 Gurobi threads per case.

Recommended Windows CMD workflow:

```cmd
cd /d "%USERPROFILE%\Desktop\01_UPSTREAM_16PLUS8\03_FULL8760_VALIDATION_V17T2R6"
set V17T2R6_PYTHON=py -3.11
set V17T2R6_JULIA=julia
set V17_SOLVER_THREADS=10
set V17T2R6_MAX_PARALLEL=2
call CHECK_V17T2R6_8760_PREFLIGHT.bat
call RUN_V17T2R6_8760_CLEAN_REBUILD_AND_RUN_ALL_4_2x10.bat
```

Only solver-native `OPTIMAL` results with feasible primal and dual solutions, strict physical/chronology/identification/export gates, and valid result lineage are publication-eligible. Time-limit or iteration-limit solutions are never promoted.

The release archive intentionally excludes generated outputs, logs, diagnostics, Python caches and superseded launchers. The clean launcher regenerates all four cases from frozen inputs, then runs the CORE observed/optimized pair concurrently followed by the LDES observed/optimized pair, with a hard maximum of two active full-8760 cases.


The preflight also runs a no-solver concurrency regression that verifies the exact two-worker cap, pair-preserving wave membership, wave barrier, and deterministic record ordering before any long Gurobi solve is launched.
