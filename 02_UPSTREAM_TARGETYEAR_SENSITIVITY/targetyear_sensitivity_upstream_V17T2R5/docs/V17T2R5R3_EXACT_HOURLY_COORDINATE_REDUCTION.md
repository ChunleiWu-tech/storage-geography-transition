# V17T2R5R3 exact hourly-coordinate reduction

## Scope

This reformulation is activated only when the prepared case basename is
`TY2033_CHRONO_1H_OPTIMAL`. All other target-year cases retain the original
full index sets.

## Exact reductions

The prepared case has 371 projects and 288 representative one-hour
timepoints. The model's CCS build index contains 96 projects. For the other
275 projects, CCS capacity is identically zero; their CCS dispatch and CCS
commitment coordinates were therefore fixed at zero in the original LP.
R3 omits these two families before model generation: 158,400 columns.

Exactly 275 projects have zero startup O&M and zero minimum up/down times.
Their nonnegative startup/shutdown pair appears only in the commitment
difference identity. Any commitment path has an extension obtained from the
positive and negative parts of each cyclic difference, so eliminating these
objective-neutral pairs preserves the projection onto every scientific
variable: another 158,400 columns.

Together with the existing exact 32-coordinate legacy-energy substitution,
R3 omits 316,800 hourly columns. Export helpers reconstruct the omitted CCS
dispatch and startup-cost fields as zero, preserving the established output
schema.

## Invariants

R3 does not alter prepared inputs, coefficients, policy switches, target year,
chronology, economic objective, solver tolerances (`FeasibilityTol=1e-7`,
`OptimalityTol=1e-7`, `BarConvTol=1e-8`), native optimality requirements,
post-solve physical audits, publication gates or result promotion rules.
`TIME_LIMIT` remains a failed attempt.

## Execution

The isolated route first attempts scaled Barrier without crossover. Only if it
fails the unchanged strict release gate does a fresh-process Dual Simplex
attempt run. No clean-central operation and no input preparation are performed.
