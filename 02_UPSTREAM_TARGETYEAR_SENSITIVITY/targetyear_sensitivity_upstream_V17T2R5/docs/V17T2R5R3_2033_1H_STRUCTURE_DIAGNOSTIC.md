# 2033 1H optimized case: structural non-convergence diagnostic

## Technical summary

The repeated stagnation of `TY2033_CHRONO_1H_OPTIMAL` is not adequately
explained by a poor choice among Barrier, dual simplex, or concurrent simplex.
The supplied logs show that all three independent routes time out on the same
LP, while the Barrier route remains far outside the configured convergence
tolerances.  The current R2 patch is mathematically valid, but removes only 32
variables from a 1,032,659-variable model and therefore does not address the
dominant hourly degeneracy.

Static inspection of the model and the prepared 1 h case identifies 316,800
hourly columns that can be omitted by exact substitution without changing the
scientific feasible set or economic objective:

- 79,200 non-CCS `DispatchGenCCS` columns that are identically zero;
- 79,200 non-CCS `CommitGenCCS` columns whose upper bound is identically zero;
- 158,400 `StartupGenCapacity`/`ShutdownGenCapacity` columns for generators
  with zero startup cost, zero minimum uptime, and zero minimum downtime.

This is 9,900 times the 32-coordinate R2 reduction before presolve.  It is the
highest-confidence structural cause found in the available code and logs.

## Evidence from the supplied logs

The original one-hour optimized LP contains 1,733,793 rows, 1,032,659 columns,
and 15,837,846 nonzeros.  Scaled Barrier presolve leaves 620,595 rows and
598,172 columns.  The coefficients span:

- matrix: `1e-07` to `2e+02`;
- objective: `8e-07` to `5e-01` after the declared `1e6` objective scale;
- variable bounds and RHS: up to `1e+07`.

The supplied 12 h Barrier run ends after 15,234 iterations with primal residual
`8.35e-03`, dual residual `7.44e-02`, and complementarity `8.40e-05`.  It is
therefore not merely waiting for the final optimal-status declaration.  Direct
dual simplex also times out after 1,606,513 iterations, and deterministic
concurrent/simplex attempts show the same lack of a solver-native optimal
certificate.  The route-independent failure is evidence against an
algorithm-only explanation.

The newer R2 screen capture shows a lower primal residual but a persistently
large and oscillatory dual residual.  That is qualitatively consistent with a
large, nearly rank-deficient or highly degenerate dual system; a stable-looking
primal objective is not an optimality certificate.

## Code-level diagnosis

### Fixed-zero CCS coordinates

The current target-year model defines `DispatchGenCCS` and `CommitGenCCS` over
all `GEN_TPS`.  For this prepared case there are 371 generators and 288 time
points, but only 96 generators are CCS-eligible.  The other 275 generators have
zero CCS capacity by construction, so both CCS families are fixed at zero
through their upper-limit constraints.  The exact removable count is:

`275 non-CCS generators * 288 timepoints * 2 families = 158,400 columns`.

### Objective-neutral startup/shutdown directions

The model defines one startup and one shutdown column for every generator and
timepoint.  For exactly the same 275 generators, startup cost, minimum uptime,
and minimum downtime are all zero.  Their only remaining role is the equality

`previous commitment + startup - shutdown = current commitment`.

For any commitment sequence this equality has nonnegative extensions, and
adding the same positive amount to startup and shutdown preserves the equality
and the objective.  Eliminating those auxiliary coordinates therefore preserves
the projection onto every scientific variable.  The exact removable count is:

`275 neutral generators * 288 timepoints * 2 families = 158,400 columns`.

### Why the optimized member is harder than the observed member

The matched pair holds national legacy power and energy fixed.  In the observed
member, all 32 provincial legacy battery capacities are fixed.  In the optimized
member, those 32 provincial power allocations are endogenous under individual
caps plus one national closure equality.  This adds a 31-dimensional allocation
face and couples it to 288 hourly storage/reserve/network constraints.  It does
not create the common degeneracy above, but it exposes and amplifies it.  This
explains why only the optimized member can fail even though both members share
the same chronology and most inputs.

## What is verified, likely, and unresolved

### Verified

- The model is a continuous LP; the failure is not MIP search.
- Multiple algorithms fail on the same numerical LP.
- R2 removes 32 exact legacy-energy coordinates but leaves the dominant hourly
  structure intact.
- The 316,800 hourly columns above are exactly omittable by substitution for
  this input and can be reconstructed as zero on export.
- Feasibility, optimality, and Barrier convergence tolerances need not be
  loosened to implement that reduction.

### Likely

- The large degenerate hourly block is the main reason Barrier dual feasibility
  oscillates and simplex performs very large numbers of pivots without a native
  optimal certificate.
- Endogenous provincial legacy allocation makes the optimized case the member
  most sensitive to that common degeneracy.

### Unresolved until the next numerical run

- Whether removing these two exact coordinate families alone is sufficient for
  Gurobi status 2 within the available time budget.
- Whether another exact redundant block, such as a fixed-zero disabled
  technology family, remains material after the reduced model is presolved.

## Recommended next step

Do not treat the current run as publication-ready unless it reaches Gurobi
status 2, JuMP `OPTIMAL`, primal and dual `FEASIBLE_POINT`, and all existing
publication gates.  If it is still active, its log can be retained for diagnosis,
but extending the same formulation is low-value while the dual residual remains
on a plateau.

The scientifically conservative update is a one-case R3 formulation that:

1. creates CCS dispatch/commit variables only for CCS-eligible generator-time
   pairs and returns zero for omitted pairs in expressions and exports;
2. creates startup/shutdown variables only for generators with a nonzero startup
   cost or positive minimum up/down time and reconstructs zeros in exports;
3. retains the R2 legacy-energy projection;
4. leaves every input file, target-year chronology, objective coefficient,
   physical constraint, tolerance, publication gate, and existing seven
   promoted outputs unchanged;
5. records the exact omitted-coordinate counts in `solve_status.csv` and is
   accepted only after static equivalence checks plus a new solver-native strict
   solve.

This same reduction already exists in the separately audited 8760/V20 model
line, providing a concrete implementation pattern, but it must be ported and
re-audited in this target-year package rather than assumed equivalent by file
copy alone.

## Sources inspected

- `base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl`
- `sensitivity_cases/TY2033_CHRONO_1H_OPTIMAL/inputs/gen_info.csv`
- `sensitivity_cases/TY2033_CHRONO_1H_OPTIMAL/inputs/ccs_install_costs.csv`
- `sensitivity_cases/TY2033_CHRONO_1H_OPTIMAL/inputs/timepoints.csv`
- supplied attempt logs `01` through `04`
- R1/R2 formulation notes and R2 static-equivalence audit
- the audited exact hourly-coordinate reduction in the 8760/V20 model line
