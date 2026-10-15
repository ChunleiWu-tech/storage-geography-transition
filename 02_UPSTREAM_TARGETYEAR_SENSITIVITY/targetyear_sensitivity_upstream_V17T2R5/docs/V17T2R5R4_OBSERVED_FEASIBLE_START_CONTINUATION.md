# V17T2R5R4 observed-feasible-start continuation

## Scope

R4 is hard-locked to `TY2033_CHRONO_1H_OPTIMAL`. It retains the R3 exact
hourly-coordinate reduction and does not prepare, clean or rerun another case.

## Motivation

The R3 Barrier route approached small residuals but stalled, while the subsequent
Dual Simplex route repeatedly returned to very large primal infeasibility. This
indicates that a strict feasible primal state is more valuable than another cold
algorithm switch.

## Phase A: certified seed

The paired observed member differs from the optimized member only in the declared
legacy-storage geography. Its 32 fixed powers:

- sum to the identical 135,930 MW national target;
- imply the identical 351,120 MWh national energy at the common duration;
- lie inside every optimized member lower and upper bound.

R4 temporarily fixes the 32 optimized-allocation coordinates to this paired
observed allocation and solves with Barrier. Status `OPTIMAL`, feasible primal and
dual results, Gurobi `Status=2`, finite/consistent `ObjVal`, and scaled/native
objective consistency are all mandatory. A time-limit incumbent is rejected.

## Phase B: unchanged final model

R4 captures every variable value from Phase A, removes the 32 temporary fixes,
restores their saved lower and upper bounds exactly, and verifies zero restoration
error. It then supplies the complete feasible vector through Gurobi `PStart`, uses
`LPWarmStart=2`, and solves the full optimized-allocation LP with Primal Simplex.

The Phase A restriction does not remain in Phase B. Therefore the final objective,
constraints and feasible set are exactly the R3 OPTIMAL formulation. The usual
solver-native optimality, objective-consistency, physical, chronology, export and
publication gates remain authoritative.

## Scientific invariants

No prepared input, coefficient, policy switch, chronology, objective expression,
feasibility/optimality tolerance, physical audit tolerance, result schema or
publication criterion is relaxed. The observed allocation is used only as a
feasible computational starting state. R4 improves the numerical path, not the
scientific claim.
