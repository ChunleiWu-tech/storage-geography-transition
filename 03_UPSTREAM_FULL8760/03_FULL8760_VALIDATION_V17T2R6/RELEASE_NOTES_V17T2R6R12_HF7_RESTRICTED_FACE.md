# V17T2R6R12-HF7 restricted-face continuation

## Evidence-based diagnosis

Three unresolved cases have two different failure mechanisms.

1. `TY2033_FULL8760_OPTIMAL` has a strict native-optimal observed-allocation
   seed. HF4 then crashed inside Gurobi 10.0.1 crossover; HF5 avoided crossover
   but its crushed complete PStart/DStart basis became numerically invalid and
   timed out after 502,711 iterations with objective about `-2.38e30`, primal
   infeasibility about `3.05e2`, and dual infeasibility about `9.4e34`.
2. Both LDES cases were trying to solve a full LDES portfolio during their
   Barrier seed. Their primal and dual objectives remained roughly
   `0.8e6` apart near the 36-hour limit. The earlier seed fixed only legacy
   geography; it did not disable the new LDES build coordinates and therefore
   did not inherit the already tractable non-LDES face.

## HF7 correction

Each case is solved inside its own unchanged target model.

- Non-LDES OPTIMAL temporarily fixes the 32 endogenous legacy-location power
  coordinates to the audited observed allocation.
- LDES OBSERVED temporarily fixes every endogenous LDES power and energy build
  coordinate to zero.
- LDES OPTIMAL temporarily fixes both groups: observed legacy geography and
  all new LDES builds at zero.

The restricted seed is solved by the same strict scaled Barrier profile. In an
LDES target, zero build capacity forces every LDES hourly dispatch, charging,
SOC and reserve coordinate to zero; aggressive presolve can therefore remove
that inactive portfolio and solve the established non-LDES face. This is only
a temporary bound restriction inside the same target model.

After the Barrier seed is native `OPTIMAL`, HF7 remains on the restricted face
and submits only its complete `DStart` to dual simplex (`Method=1`,
`LPWarmStart=2`, `Presolve=2`, `Crossover=0`). This separate fail-closed stage
must return native `OPTIMAL` and a complete original-model VBasis/CBasis. It
therefore never repeats HF5's failed PStart crash-basis route.

HF7 then captures the simplex primal, dual and reduced-cost vectors and builds
a temporary supporting objective `c - reduced_cost` only on coordinates that
will be released. Bound restoration is ordered deliberately. Zero-LDES
coordinates are released first; their original lower bound is audited to be
exactly zero, and nonbasic fixed statuses are normalized to lower-bound status
so the inherited basis remains primal feasible. The 32 legacy-allocation
bounds, when present, are released second. A complete basis is explicitly
reinstalled before each unpresolved dual-simplex repair (`Method=1`,
`LPWarmStart=1`, `Presolve=0`, `Crossover=0`). Each release block must be strict
native `OPTIMAL` before eight guarded primal-simplex objective-continuation
stages begin. Every original bound and the exact original objective are
restored coefficient-for-coefficient before the sole publication-eligible
final solve.

## Scientific invariance and fail-closed rules

HF7 does not edit any prepared input, metadata, chronology, technology
opportunity, model row, matrix coefficient, RHS, final variable bound, final
economic objective, solver feasibility/optimality tolerance, physical audit or
publication threshold. Every seed, bridge, continuation stage and final solve
must return native Gurobi `OPTIMAL`; no time-limit incumbent is publishable.
Previous strict outputs are skipped, while every old HF3-HF6 log and diagnostic
is retained. New attempts use the `__07_full8760_hf7_...` suffix.

## Independent execution

`RUN_V17T2R6R12_HF7_8760_UNRESOLVED_3X15.bat` starts exactly the three
unresolved cases as three independent Julia processes, each with its own
scenario lease, log, attempt directory and 15-thread seed/final budget. It
never deletes a lock or cleans an existing result. A live older worker is
waited on until its owner releases the corresponding scenario.
