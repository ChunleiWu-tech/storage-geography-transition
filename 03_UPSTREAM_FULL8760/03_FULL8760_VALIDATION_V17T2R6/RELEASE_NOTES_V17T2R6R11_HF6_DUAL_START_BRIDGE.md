# V17T2R6R11-HF6: DStart-only dual-simplex bridge

## Why HF6 replaces HF5

The ordinary `TY2033_FULL8760_OPTIMAL` case demonstrated that the R10-HF5
bridge was not numerically usable: its fixed-allocation seed reached native
Gurobi `OPTIMAL`, but the following `Method=0`, `LPWarmStart=2`, complete
`PStart`/`DStart` bridge reached its 21,600-second limit with an objective of
about `-2.38e30`, primal infeasibility about `3.05e2`, and dual infeasibility
about `9.4e34`.  That is an invalid crash-basis path, not a successful solve
and not evidence of scientific infeasibility.

HF6 removes that specific pathway.  It still captures and checks the complete
primal seed (including every restored target bound), but does **not** submit
`PStart`.  It submits only the complete captured `DStart`, uses `Method=1`
(dual simplex), `LPWarmStart=1` on the original unpresolved model,
`Presolve=Aggregate=PreSparsify=0`, and `Crossover=0` / `CrossoverBasis=-1`.
The temporary support objective remains the exact 32-coordinate
`c - reduced_cost` construction and must be restored exactly before the final
publication-eligible solve.

This follows Gurobi's documented warm-start semantics: without a basis,
dual simplex consumes `DStart` to refine a crash basis; `LPWarmStart=1` uses
the original model rather than the crushed presolved model.  HF6 makes no
claim of success unless the bridge, all eight continuation stages, and the
original final objective each independently return native `OPTIMAL` and every
existing publication gate passes.

## Scientific scope

No input, chronology, technology opportunity, scientific matrix, RHS,
constraint, target bound, final objective, tolerance, or acceptance standard
is relaxed or changed.  HF6 is restricted to:

- `TY2033_FULL8760_OPTIMAL`
- `TY2033_FULL8760_LDES_OPTIMAL`

It does not start, modify, clean, finalise, or release a lock for either
OBSERVED member.  It writes new `__06_...hf6...` attempts; all earlier HF3–HF5
logs and diagnostics remain retained.

## Run

After the current HF5 LDES-OPTIMAL worker has been stopped and its scenario
lease has disappeared, run:

`RUN_V17T2R6R11_HF6_8760_OPTIMIZED_PAIR_2X15.bat`

It starts only the two optimized cases at up to two workers of 15 solver
threads.  It never deletes a lock; if a live old lock remains, it waits rather
than accidentally running the same scenario twice.
