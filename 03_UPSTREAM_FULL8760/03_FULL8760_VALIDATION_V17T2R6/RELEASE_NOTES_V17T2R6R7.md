# V17T2R6R7 full-8760 release notes

R7 is an operational concurrency hardening release built on R6. It does **not** change the scientific model, four scenario definitions, frozen inputs, objective, constraints, chronology, solver tolerances, solver routes, or publication acceptance gates.

## What changes in R7

- The canonical all-four launcher now executes **exactly two full-8760 cases simultaneously, with 10 Gurobi threads per case**.
- Execution is wave-based and pair-preserving:
  - Wave 1: `TY2033_FULL8760_OBSERVED` + `TY2033_FULL8760_OPTIMAL`.
  - Wave 2: `TY2033_FULL8760_LDES_OBSERVED` + `TY2033_FULL8760_LDES_OPTIMAL`.
- Each case retains the same pre-specified solver ladder: primary scaled Barrier without crossover, then the same controlled homogeneous-Barrier fallback if the primary route is not solver-certified `OPTIMAL`.
- The Python orchestrator owns summary aggregation after a wave completes. Worker processes write only scenario-specific logs, attempt directories, promoted outputs and diagnostics, avoiding concurrent writes to the shared run summary.
- A hard operational cap rejects `--max-parallel` values other than 1 or 2. In R7 parallel mode, `V17_SOLVER_THREADS` must be exactly 10.
- A Python-side worker exception is converted into a deterministic failed record rather than silently terminating the partner case.
- Result ordering remains deterministic regardless of which concurrent worker finishes first.
- R6 post-solve export hardening remains active: the stale undefined `REPRESENTATIVE_TIMEPOINT_COUNT_EXPECTED` token is forbidden.
- Python caches and bytecode are removed from the release archive and package QA fails closed if they reappear.

## Scientific invariance

The active Julia model, Julia scenario runner, four scenario registry rows, frozen source data, 4 h templates and all four prepared-case scientific inputs are byte-identical to R6. R7 changes only orchestration, launchers, documentation and release QA/manifest metadata.

## R7-HF1 — cross-platform manifest stability hotfix

- Packaging-only correction; scientific inputs, Julia model, scenario registry, solver routes, tolerances, and 2x10 scheduling are unchanged.
- Forces LF line endings for preflight-generated JSON audit/manifest writers so Windows reruns do not create false `SIZE`/`SHA256` manifest failures through CRLF translation.
- Adds a fail-closed package-QA regression check for explicit platform-independent LF output.
